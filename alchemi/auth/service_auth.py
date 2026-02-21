"""
Service authentication utilities for Alchemi endpoints.

Provides reusable FastAPI dependencies for auth:
- require_scope(scope): validates caller has account access (scope reserved for future fine-grained RBAC)
- get_request_context(): extracts account_id and user info from request context
"""
from fastapi import Depends, HTTPException, Request


def require_scope(scope: str):
    """
    FastAPI dependency factory that validates the caller has account-level access.

    Currently checks super_admin or account_admin status via tenant context.
    The `scope` parameter is recorded for future fine-grained permission checks
    but not enforced yet.

    Usage:
        @router.get("/data")
        async def get_data(request: Request, _=require_scope("data:read")):
            ...
    """
    async def _dependency(request: Request):
        from alchemi.middleware.tenant_context import is_super_admin, get_current_account_id
        from alchemi.middleware.account_middleware import resolve_tenant_from_request

        if not is_super_admin() and get_current_account_id() is None:
            resolve_tenant_from_request(request)

        if is_super_admin():
            return

        account_id = get_current_account_id()
        if account_id is None:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Valid authentication required.",
            )

    return Depends(_dependency)


async def require_super_admin(request: Request):
    """Dependency to verify super admin access."""
    from alchemi.middleware.tenant_context import is_super_admin
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    if not is_super_admin():
        resolve_tenant_from_request(request)

    if not is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only accessible to super admins.",
        )


async def require_account_access(request: Request):
    """Dependency to verify super admin or account admin access."""
    from alchemi.middleware.tenant_context import is_super_admin, get_current_account_id
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    if not is_super_admin() and get_current_account_id() is None:
        resolve_tenant_from_request(request)

    if is_super_admin():
        return

    account_id = get_current_account_id()
    if account_id is None:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin or account admin required.",
        )


def get_request_context(request: Request) -> dict:
    """
    Extract account context from the current request.
    Returns dict with account_id and is_super_admin.
    """
    from alchemi.middleware.tenant_context import is_super_admin, get_current_account_id

    return {
        "account_id": get_current_account_id(),
        "is_super_admin": is_super_admin(),
    }
