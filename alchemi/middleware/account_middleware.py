"""
FastAPI middleware that resolves the current account (tenant) for each request.
Sets the account_id in contextvars so the tenant-scoped Prisma wrapper
can auto-filter all DB queries.

Uses a pure ASGI middleware (not BaseHTTPMiddleware) to avoid the known
Starlette issue where contextvars set in dispatch() don't propagate
to route handlers via call_next().
"""
import os
import jwt as pyjwt
from typing import Optional
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request

from alchemi.middleware.tenant_context import (
    set_current_account_id,
    set_super_admin,
    set_current_roles,
    set_current_scopes,
    set_current_product_domains,
    set_current_auth_provider,
)
from alchemi.auth.zitadel import (
    verify_zitadel_token,
    decode_unverified as decode_unverified_token,
    claims_to_context as zitadel_claims_to_context,
    get_zitadel_settings,
)

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
    """Decode a JWT token, returning the claims dict or None."""
    try:
        return pyjwt.decode(
            token,
            master_key,
            algorithms=["HS256"],
            options={"verify_exp": False},
        )
    except Exception:
        return None


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
    set_current_roles([])
    set_current_scopes([])
    set_current_product_domains([])
    set_current_auth_provider(None)

    token = extract_token_from_request(request)
    if not token:
        return

    master_key = _get_master_key()

    # Allow explicit account scoping for service-to-service calls using master key.
    # This lets trusted backend services act within a tenant context.
    requested_account_id = request.headers.get("x-account-id") or request.headers.get("X-Account-Id")

    # Check if token IS the master key (API calls with master key = super admin)
    if token == master_key:
        set_super_admin(True)
        set_current_account_id(requested_account_id or None)
        set_current_auth_provider("litellm_master_key")
        return

    # Also check against env var in case config key differs
    env_master_key = os.getenv("LITELLM_MASTER_KEY", "")
    if env_master_key and token == env_master_key:
        set_super_admin(True)
        set_current_account_id(requested_account_id or None)
        set_current_auth_provider("litellm_master_key")
        return

    # Try to decode as JWT
    decoded = decode_jwt_token(token, master_key)
    provider = "litellm_jwt" if decoded else None

    # Try verified Zitadel token when enabled
    if decoded is None:
        zitadel_claims = verify_zitadel_token(token)
        if zitadel_claims:
            context = zitadel_claims_to_context(zitadel_claims)
            set_current_roles(context["roles"])
            set_current_scopes(context["scopes"])
            set_current_product_domains(context["domains"])
            set_super_admin(bool(context["is_super_admin"]))
            set_current_account_id(requested_account_id or context["account_id"])
            set_current_auth_provider("zitadel")
            return

        # Optional fallback for development if enabled
        allow_unverified = os.getenv("ZITADEL_ALLOW_UNVERIFIED_DECODE", "false").strip().lower() in {"1", "true", "yes", "on"}
        if allow_unverified and get_zitadel_settings().enabled:
            unverified = decode_unverified_token(token)
            if unverified:
                context = zitadel_claims_to_context(unverified)
                set_current_roles(context["roles"])
                set_current_scopes(context["scopes"])
                set_current_product_domains(context["domains"])
                set_super_admin(bool(context["is_super_admin"]))
                set_current_account_id(requested_account_id or context["account_id"])
                set_current_auth_provider("zitadel_unverified")
                return

    if decoded:
        roles = decoded.get("roles") or decoded.get("role") or []
        if isinstance(roles, str):
            roles = [roles]
        scopes = decoded.get("scopes") or decoded.get("scope") or []
        if isinstance(scopes, str):
            scopes = [s for s in scopes.split(" ") if s]
        domains = (
            decoded.get("product_domains_allowed")
            or decoded.get("product_domains")
            or []
        )
        if isinstance(domains, str):
            domains = [domains]

        set_current_roles(roles)
        set_current_scopes(scopes)
        set_current_product_domains(domains)

        if decoded.get("is_super_admin", False):
            set_super_admin(True)
            set_current_account_id(None)
        elif decoded.get("account_id"):
            set_current_account_id(decoded["account_id"])
        set_current_auth_provider(provider)


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
