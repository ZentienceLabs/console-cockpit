"""Control-plane policy checks for unified console-cockpit APIs."""

from fastapi import HTTPException

from alchemi.middleware.tenant_context import (
    get_current_account_id,
    get_current_product_domains,
    get_current_roles,
    get_current_scopes,
    is_super_admin,
)


SUPER_ROLES = {"super_admin"}
ACCOUNT_ADMIN_ROLES = {"account_admin"}
COPILOT_ADMIN_ROLES = {"copilot_org_admin", "copilot_team_admin", "account_admin"}
CONSOLE_ADMIN_ROLES = {"console_org_admin", "console_team_admin", "account_admin"}


def _has_any_role(required: set[str]) -> bool:
    roles = set(get_current_roles() or [])
    return bool(roles.intersection(required))


def _has_scope(scope: str) -> bool:
    scopes = set(get_current_scopes() or [])
    return scope in scopes or "*" in scopes


def require_super_admin() -> None:
    if is_super_admin() or _has_any_role(SUPER_ROLES):
        return
    raise HTTPException(status_code=403, detail="Super admin access required")


def require_account_admin() -> str:
    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=403, detail="Account context required")
    if is_super_admin() or _has_any_role(ACCOUNT_ADMIN_ROLES.union(SUPER_ROLES)):
        return account_id
    raise HTTPException(status_code=403, detail="Account admin access required")


def require_domain_admin(domain: str) -> str:
    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=403, detail="Account context required")

    if is_super_admin():
        return account_id

    allowed_domains = set(get_current_product_domains() or [])
    if allowed_domains and domain not in allowed_domains and "all" not in allowed_domains:
        raise HTTPException(status_code=403, detail=f"Domain access denied: {domain}")

    if domain == "copilot" and _has_any_role(COPILOT_ADMIN_ROLES.union(SUPER_ROLES)):
        return account_id
    if domain == "console" and _has_any_role(CONSOLE_ADMIN_ROLES.union(SUPER_ROLES)):
        return account_id

    if _has_scope(f"{domain}:admin") or _has_scope("control_plane:admin"):
        return account_id

    raise HTTPException(status_code=403, detail=f"{domain} admin access required")
