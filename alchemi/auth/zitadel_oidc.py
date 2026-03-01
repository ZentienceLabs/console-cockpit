"""
Zitadel OIDC authentication endpoint.
Handles the OAuth2 Authorization Code flow with PKCE for Zitadel.

Mints the same HS256 JWT format as existing password-based login,
so downstream middleware (AccountContextMiddleware) needs no changes.
"""
import os
import secrets
import hashlib
import base64
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError

router = APIRouter(tags=["Zitadel Authentication"])

# Cache the OIDC discovery document by issuer
_oidc_config_cache: Dict[str, dict] = {}
_oidc_config_fetched_at: Dict[str, float] = {}
_OIDC_CACHE_TTL = 3600  # 1 hour
_jwks_client_cache: Dict[str, PyJWKClient] = {}


def _get_zitadel_config():
    """Read Zitadel configuration from environment variables."""
    issuer = (
        os.getenv("ZITADEL_ISSUER_URL")
        or os.getenv("NEXT_PUBLIC_ZITADEL_ISSUER")
        or ""
    ).rstrip("/")
    client_id = os.getenv("ZITADEL_CLIENT_ID") or os.getenv("NEXT_PUBLIC_ZITADEL_CLIENT_ID", "")
    client_secret = os.getenv("ZITADEL_CLIENT_SECRET") or os.getenv(
        "NEXT_PUBLIC_ZITADEL_CLIENT_SECRET", ""
    )
    callback_url = os.getenv("ZITADEL_CALLBACK_URL", "")
    if not issuer or not client_id:
        return None
    return {
        "issuer": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "callback_url": callback_url,
    }


async def _get_oidc_discovery(issuer: str) -> dict:
    """Fetch and cache the OIDC discovery document."""
    now = time.time()
    cached_doc = _oidc_config_cache.get(issuer)
    fetched_at = _oidc_config_fetched_at.get(issuer, 0)
    if cached_doc and (now - fetched_at) < _OIDC_CACHE_TTL:
        return cached_doc

    url = f"{issuer}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        discovery = resp.json()
        _oidc_config_cache[issuer] = discovery
        _oidc_config_fetched_at[issuer] = now
        return discovery


def _generate_pkce_pair():
    """Generate PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _get_master_key() -> str:
    """Get the master key for JWT signing."""
    try:
        from litellm.proxy.proxy_server import master_key

        if master_key:
            return master_key
    except (ImportError, AttributeError):
        pass
    return os.getenv("LITELLM_MASTER_KEY", "")


def _is_super_admin_email(email: str) -> bool:
    """Check if email is in SUPER_ADMIN_EMAILS."""
    from alchemi.auth.super_admin import is_super_admin_zitadel

    return is_super_admin_zitadel(email)


def _get_jwks_client(jwks_uri: str) -> PyJWKClient:
    """Get a cached JWKS client for the issuer."""
    if jwks_uri not in _jwks_client_cache:
        _jwks_client_cache[jwks_uri] = PyJWKClient(jwks_uri)
    return _jwks_client_cache[jwks_uri]


def _verify_id_token(id_token: str, discovery: Dict[str, Any], config: Dict[str, str]) -> Dict[str, Any]:
    """Verify and decode Zitadel ID token using issuer JWKS."""
    jwks_uri = discovery.get("jwks_uri")
    if not jwks_uri:
        raise HTTPException(status_code=502, detail="OIDC discovery missing jwks_uri.")

    try:
        jwk_client = _get_jwks_client(jwks_uri)
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
        return pyjwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            audience=config["client_id"],
            issuer=config["issuer"],
        )
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Zitadel id_token: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to verify id_token: {e}")


@router.get("/zitadel/authorize")
async def zitadel_authorize(request: Request):
    """
    Initiate Zitadel OIDC login.
    Generates PKCE challenge, stores verifier + state in cookies,
    and redirects to Zitadel authorization endpoint.
    """
    config = _get_zitadel_config()
    if not config:
        raise HTTPException(
            status_code=500,
            detail="Zitadel is not configured. Set ZITADEL_ISSUER_URL and ZITADEL_CLIENT_ID.",
        )

    discovery = await _get_oidc_discovery(config["issuer"])
    authorization_endpoint = discovery["authorization_endpoint"]

    # Generate PKCE pair and state
    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    # Build callback URL - use configured or derive from request
    callback_url = config["callback_url"]
    if not callback_url:
        callback_url = str(request.base_url).rstrip("/") + "/zitadel/callback"

    # Build authorization URL
    params = {
        "client_id": config["client_id"],
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": callback_url,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{authorization_endpoint}?{urlencode(params)}"

    # Store code_verifier and state in short-lived httpOnly cookies
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie(
        key="zitadel_cv",
        value=code_verifier,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,  # 10 minutes
        path="/",
    )
    response.set_cookie(
        key="zitadel_state",
        value=state,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@router.get("/zitadel/callback")
async def zitadel_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """
    Handle Zitadel OIDC callback.
    Exchanges authorization code for tokens, resolves account,
    mints HS256 JWT (same format as password login), and redirects to UI.
    """
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"Zitadel authentication error: {error} - {error_description or ''}",
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter.")

    # Validate state
    stored_state = request.cookies.get("zitadel_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter.")

    # Retrieve code_verifier
    code_verifier = request.cookies.get("zitadel_cv")
    if not code_verifier:
        raise HTTPException(
            status_code=400, detail="Missing PKCE verifier. Please try logging in again."
        )

    config = _get_zitadel_config()
    if not config:
        raise HTTPException(status_code=500, detail="Zitadel is not configured.")

    discovery = await _get_oidc_discovery(config["issuer"])
    token_endpoint = discovery["token_endpoint"]

    # Build callback URL (same as used in authorize)
    callback_url = config["callback_url"]
    if not callback_url:
        callback_url = str(request.base_url).rstrip("/") + "/zitadel/callback"

    # Exchange authorization code for tokens
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": callback_url,
        "client_id": config["client_id"],
        "code_verifier": code_verifier,
    }
    if config["client_secret"]:
        token_data["client_secret"] = config["client_secret"]

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            token_endpoint,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange failed: {token_resp.text}",
        )

    tokens = token_resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="No id_token in Zitadel response.")

    id_claims = _verify_id_token(id_token=id_token, discovery=discovery, config=config)

    email = str(id_claims.get("email", "")).strip().lower()
    zitadel_sub = id_claims.get("sub", "")
    zitadel_org_id = id_claims.get("urn:zitadel:iam:org:id", None)

    if not email:
        raise HTTPException(status_code=400, detail="No email in Zitadel ID token.")

    # Resolve account and role
    is_admin = _is_super_admin_email(email)

    account_id = None
    prisma_client = None
    user_role = "proxy_admin" if is_admin else "internal_user"

    if not is_admin:
        # Resolve account from Zitadel claims
        from alchemi.auth.account_resolver import resolve_account_from_zitadel_claims

        try:
            from litellm.proxy.proxy_server import prisma_client

            account_id = await resolve_account_from_zitadel_claims(
                zitadel_sub=zitadel_sub,
                email=email,
                zitadel_org_id=zitadel_org_id,
                prisma_client=prisma_client,
            )
        except Exception:
            account_id = None
    else:
        from litellm.proxy.proxy_server import prisma_client

    # Best-effort: keep LiteLLM_UserTable linked to account for directory visibility.
    if prisma_client is not None:
        try:
            existing_user = await prisma_client.db.litellm_usertable.find_first(
                where={
                    "OR": [
                        {"user_email": email},
                        {"sso_user_id": zitadel_sub},
                    ]
                }
            )
            role_to_store = "proxy_admin" if is_admin else "internal_user"
            if existing_user:
                update_data: Dict[str, Any] = {
                    "user_email": email,
                    "user_role": role_to_store,
                }
                if zitadel_sub:
                    update_data["sso_user_id"] = zitadel_sub
                if account_id and not getattr(existing_user, "account_id", None):
                    update_data["account_id"] = account_id
                await prisma_client.db.litellm_usertable.update(
                    where={"user_id": existing_user.user_id},
                    data=update_data,
                )
            else:
                await prisma_client.db.litellm_usertable.create(
                    data={
                        "user_id": email,
                        "user_email": email,
                        "user_alias": str(id_claims.get("name") or email),
                        "user_role": role_to_store,
                        "sso_user_id": zitadel_sub,
                        "account_id": account_id,
                        "spend": 0.0,
                        "models": [],
                        "teams": [],
                    }
                )

            if account_id:
                from alchemi.auth.account_resolver import reconcile_identity_account_links

                await reconcile_identity_account_links(
                    account_id=account_id,
                    prisma_client=prisma_client,
                    max_scan=2000,
                )
        except Exception:
            # Login should not fail due to reconciliation drift.
            pass

    # Generate an API key for the session (reuse existing helper)
    user_id = email if not is_admin else os.getenv("UI_USERNAME", email)
    api_key = None
    try:
        from litellm.proxy.management_endpoints.key_management_endpoints import (
            generate_key_helper_fn,
        )
        from litellm.proxy.proxy_server import prisma_client

        key_data = await generate_key_helper_fn(
            request_type="key",
            duration="24hr",
            models=[],
            aliases={},
            config={},
            spend=0,
            max_budget=None,
            token=None,
            user_id=user_id,
            team_id=None,
            user_role=user_role,
            user_email=email,
            max_parallel_requests=None,
            metadata={
                "login_method": "zitadel_oidc",
                "zitadel_sub": zitadel_sub,
            },
            tpm_limit=None,
            rpm_limit=None,
            budget_duration=None,
            allowed_cache_controls=[],
            permissions={},
            model_max_budget={},
            model_rpm_limit={},
            model_tpm_limit={},
            guardrails=[],
            tags=None,
        )
        api_key = key_data.get("token", key_data.get("key", None))
    except Exception:
        # If key generation fails, proceed without embedded API key
        api_key = None

    # Mint consolidated JWT (same structure as password login)
    master_key = _get_master_key()
    jwt_payload = {
        "user_id": user_id,
        "key": api_key or "",
        "user_email": email,
        "user_role": user_role,
        "login_method": "zitadel_oidc",
        "premium_user": True,
        "auth_header_name": "Authorization",
        "account_id": account_id,
        "is_super_admin": is_admin,
    }

    token = pyjwt.encode(jwt_payload, master_key, algorithm="HS256")

    # Redirect to UI with token cookie
    ui_url = str(request.base_url).rstrip("/") + "/ui/"
    response = RedirectResponse(url=ui_url, status_code=302)
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    # Clean up PKCE cookies
    response.delete_cookie("zitadel_cv", path="/")
    response.delete_cookie("zitadel_state", path="/")
    return response


@router.get("/zitadel/logout")
async def zitadel_logout(request: Request):
    """
    Logout from Zitadel and clear session.
    Redirects to Zitadel end_session endpoint.
    """
    config = _get_zitadel_config()
    response = RedirectResponse(url="/ui/login", status_code=302)
    response.delete_cookie("token", path="/")

    if config:
        try:
            discovery = await _get_oidc_discovery(config["issuer"])
            end_session_endpoint = discovery.get("end_session_endpoint")
            if end_session_endpoint:
                post_logout_uri = str(request.base_url).rstrip("/") + "/ui/login"
                logout_url = (
                    f"{end_session_endpoint}?"
                    f"{urlencode({'client_id': config['client_id'], 'post_logout_redirect_uri': post_logout_uri})}"
                )
                response = RedirectResponse(url=logout_url, status_code=302)
                response.delete_cookie("token", path="/")
        except Exception:
            pass

    return response
