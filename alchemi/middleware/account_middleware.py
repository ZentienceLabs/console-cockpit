"""
FastAPI middleware that resolves the current account (tenant) for each request.
Sets the account_id in contextvars so the tenant-scoped Prisma wrapper
can auto-filter all DB queries.

Uses a pure ASGI middleware (not BaseHTTPMiddleware) to avoid the known
Starlette issue where contextvars set in dispatch() don't propagate
to route handlers via call_next().
"""
import os
import logging
from functools import lru_cache
import jwt as pyjwt
from typing import Optional
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request

from alchemi.middleware.tenant_context import (
    set_current_account_id,
    set_super_admin,
    set_actor_role,
)

logger = logging.getLogger(__name__)

# Paths that do NOT require tenant context
PUBLIC_PATHS = {
    "/health",
    "/health/readiness",
    "/health/liveliness",
    "/v2/login",
    "/v2/login/resolve",
    "/sso/key/generate",
    "/sso/callback",
    "/get_image",
    "/.well-known/litellm-ui-config",
    "/litellm/.well-known/litellm-ui-config",
}


def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract token from cookie or Authorization header."""
    # Try cookie first (UI sessions)
    token = request.cookies.get("token")
    if token:
        return token

    # Try Authorization header (API calls)
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth_header:
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return auth_header

    # Try custom header name
    litellm_header = request.headers.get("x-litellm-api-key")
    if litellm_header:
        return litellm_header

    return None


def decode_jwt_token(token: str, master_key: str) -> Optional[dict]:
    """Decode JWT claims from HS256 master-key tokens or Zitadel OIDC tokens."""
    # First: existing LiteLLM-style HS256 token support
    try:
        return pyjwt.decode(
            token,
            master_key,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except Exception:
        pass

    # Second: Zitadel / OIDC RS256 support
    return _decode_zitadel_token(token)


@lru_cache(maxsize=4)
def _get_jwks_client(jwks_url: str):
    return pyjwt.PyJWKClient(jwks_url)


def _decode_zitadel_token(token: str) -> Optional[dict]:
    """Decode and validate a Zitadel-issued token when configured."""
    issuer = os.getenv("ZITADEL_ISSUER", "").strip().rstrip("/")
    if not issuer:
        return None

    jwks_url = os.getenv("ZITADEL_JWKS_URL", "").strip() or f"{issuer}/oauth/v2/keys"
    audience = os.getenv("ZITADEL_AUDIENCE", "").strip()

    try:
        signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        options = {"verify_aud": bool(audience)}
        kwargs = {
            "algorithms": ["RS256", "RS384", "RS512"],
            "issuer": issuer,
            "options": options,
        }
        if audience:
            kwargs["audience"] = audience
        return pyjwt.decode(token, signing_key, **kwargs)
    except pyjwt.ExpiredSignatureError:
        logger.warning("Zitadel JWT validation failed: token expired")
        return None
    except pyjwt.InvalidIssuerError:
        logger.warning("Zitadel JWT validation failed: invalid issuer")
        return None
    except pyjwt.InvalidAudienceError:
        logger.warning("Zitadel JWT validation failed: invalid audience")
        return None
    except pyjwt.DecodeError as e:
        logger.warning("Zitadel JWT validation failed: decode error - %s", e)
        return None
    except Exception as e:
        logger.warning("Zitadel JWT validation failed: %s", e)
        return None


def _extract_account_id_from_claims(claims: dict) -> Optional[str]:
    claim_keys = os.getenv(
        "ZITADEL_ACCOUNT_ID_CLAIMS",
        "account_id,tenant_id,urn:alchemi:account_id,urn:alchemi:tenant_id",
    )
    for key in [c.strip() for c in claim_keys.split(",") if c.strip()]:
        value = claims.get(key)
        if value:
            return str(value)
    return None


def _collect_role_candidates(claims: dict) -> list[str]:
    """Collect all role values from JWT claims into a normalized list."""
    role_candidates = []
    for role_field in [
        "roles",
        "role",
        "user_role",
        "urn:zitadel:iam:org:project:roles",
    ]:
        role_claim = claims.get(role_field)
        if isinstance(role_claim, list):
            role_candidates.extend([str(r).lower() for r in role_claim])
        elif isinstance(role_claim, dict):
            role_candidates.extend([str(k).lower() for k in role_claim.keys()])
        elif isinstance(role_claim, str):
            role_candidates.append(role_claim.lower())
    return role_candidates


def _is_super_admin_claims(claims: dict) -> bool:
    if claims.get("is_super_admin", False):
        return True

    role_candidates = _collect_role_candidates(claims)

    super_roles = [
        r.strip().lower()
        for r in os.getenv(
            "ZITADEL_SUPER_ADMIN_ROLE_KEYS",
            "super_admin,platform_admin,alchemi_super_admin",
        ).split(",")
        if r.strip()
    ]
    return any(role in super_roles for role in role_candidates)


def _is_account_admin_claims(claims: dict) -> bool:
    """Check if the JWT claims contain an account_admin role."""
    role_candidates = _collect_role_candidates(claims)

    admin_roles = [
        r.strip().lower()
        for r in os.getenv(
            "ZITADEL_ACCOUNT_ADMIN_ROLE_KEYS",
            "account_admin,org_admin,tenant_admin,admin",
        ).split(",")
        if r.strip()
    ]
    return any(role in admin_roles for role in role_candidates)


def _resolve_actor_role(claims: dict) -> str:
    """Determine the actor's role from JWT claims: super_admin > account_admin > end_user."""
    if _is_super_admin_claims(claims):
        return "super_admin"
    if _is_account_admin_claims(claims):
        return "account_admin"
    return "end_user"


def _get_master_key() -> str:
    """Get the master key used by the proxy server (may differ from env var if set in config)."""
    try:
        from litellm.proxy.proxy_server import master_key
        if master_key:
            return master_key
    except (ImportError, AttributeError):
        pass
    return os.getenv("LITELLM_MASTER_KEY", "")


def resolve_tenant_from_request(request: Request) -> None:
    """
    Resolve tenant context from a request and set contextvars.
    Can be called from middleware or directly from route dependencies.
    """
    set_current_account_id(None)
    set_super_admin(False)
    set_actor_role("end_user")

    token = extract_token_from_request(request)
    if not token:
        return

    master_key = _get_master_key()

    # Check if token IS the master key (API calls with master key = super admin)
    if token == master_key:
        set_super_admin(True)
        set_actor_role("super_admin")
        set_current_account_id(None)
        return

    # Also check against env var in case config key differs
    env_master_key = os.getenv("LITELLM_MASTER_KEY", "")
    if env_master_key and token == env_master_key:
        set_super_admin(True)
        set_actor_role("super_admin")
        set_current_account_id(None)
        return

    # Try to decode as JWT
    decoded = decode_jwt_token(token, master_key)
    if decoded:
        role = _resolve_actor_role(decoded)
        set_actor_role(role)

        if role == "super_admin":
            set_super_admin(True)
            set_current_account_id(None)
            return

        account_id = (
            decoded.get("account_id")
            or _extract_account_id_from_claims(decoded)
            or request.headers.get("x-account-id")
            or request.query_params.get("account_id")
        )
        if account_id:
            set_current_account_id(str(account_id))


class AccountContextMiddleware:
    """
    Pure ASGI middleware that extracts account_id from the request context
    (JWT cookie for UI sessions, Authorization header for API calls)
    and sets it in the async context variable.

    Uses raw ASGI protocol instead of BaseHTTPMiddleware to ensure
    contextvars propagate correctly to downstream handlers.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path.rstrip("/")

        # Skip tenant resolution for public paths and static assets
        if path in PUBLIC_PATHS or path.startswith("/assets") or path.startswith("/_next"):
            await self.app(scope, receive, send)
            return

        # Resolve tenant context and set contextvars
        resolve_tenant_from_request(request)

        await self.app(scope, receive, send)
