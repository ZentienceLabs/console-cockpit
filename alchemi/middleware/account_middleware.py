"""
FastAPI middleware that resolves the current account (tenant) for each request.
Sets the account_id in contextvars so the tenant-scoped Prisma wrapper
can auto-filter all DB queries.
"""
import os
import jwt
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from alchemi.middleware.tenant_context import (
    set_current_account_id,
    set_super_admin,
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


class AccountContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts account_id from the request context
    (JWT cookie for UI sessions, API key lookup for API calls)
    and sets it in the async context variable.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Reset context for this request
        set_current_account_id(None)
        set_super_admin(False)

        path = request.url.path.rstrip("/")

        # Skip tenant resolution for public paths
        if path in PUBLIC_PATHS or path.startswith("/assets") or path.startswith("/_next"):
            return await call_next(request)

        # Try to resolve account from JWT cookie (UI sessions)
        account_id = self._resolve_from_jwt(request)
        if account_id is not None:
            set_current_account_id(account_id)

        # Check for super admin
        is_sa = self._check_super_admin(request)
        if is_sa:
            set_super_admin(True)
            set_current_account_id(None)  # Super admin has no account scope

        response = await call_next(request)
        return response

    def _resolve_from_jwt(self, request: Request) -> Optional[str]:
        """Extract account_id from JWT token in cookie."""
        token = request.cookies.get("token")
        if not token:
            return None

        try:
            master_key = os.getenv("LITELLM_MASTER_KEY", "")
            decoded = jwt.decode(
                token,
                master_key,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            return decoded.get("account_id")
        except Exception:
            return None

    def _check_super_admin(self, request: Request) -> bool:
        """Check if the current request is from a super admin (via JWT)."""
        token = request.cookies.get("token")
        if not token:
            return False

        try:
            master_key = os.getenv("LITELLM_MASTER_KEY", "")
            decoded = jwt.decode(
                token,
                master_key,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            return decoded.get("is_super_admin", False)
        except Exception:
            return False
