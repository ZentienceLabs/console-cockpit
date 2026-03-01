"""
Async context variables for multi-tenant request scoping.
Stores the current account_id and super admin flag for the duration of each request.
"""
import contextvars
from typing import Optional, List

_current_account_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_account_id", default=None
)
_is_super_admin: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "is_super_admin", default=False
)
_current_roles: contextvars.ContextVar[List[str]] = contextvars.ContextVar(
    "current_roles", default=[]
)
_current_scopes: contextvars.ContextVar[List[str]] = contextvars.ContextVar(
    "current_scopes", default=[]
)
_current_product_domains: contextvars.ContextVar[List[str]] = contextvars.ContextVar(
    "current_product_domains", default=[]
)
_current_auth_provider: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_auth_provider", default=None
)


def get_current_account_id() -> Optional[str]:
    """Get the account_id for the current request context."""
    return _current_account_id.get()


def set_current_account_id(account_id: Optional[str]) -> None:
    """Set the account_id for the current request context."""
    _current_account_id.set(account_id)


def is_super_admin() -> bool:
    """Check if the current request is from a super admin."""
    return _is_super_admin.get()


def set_super_admin(value: bool) -> None:
    """Set the super admin flag for the current request context."""
    _is_super_admin.set(value)


def get_current_roles() -> List[str]:
    """Get resolved roles from JWT claims for current request."""
    return _current_roles.get()


def set_current_roles(roles: Optional[List[str]]) -> None:
    """Set resolved roles from JWT claims for current request."""
    _current_roles.set(roles or [])


def get_current_scopes() -> List[str]:
    """Get resolved scopes from JWT claims for current request."""
    return _current_scopes.get()


def set_current_scopes(scopes: Optional[List[str]]) -> None:
    """Set resolved scopes from JWT claims for current request."""
    _current_scopes.set(scopes or [])


def get_current_product_domains() -> List[str]:
    """Get product domains allowed for current request."""
    return _current_product_domains.get()


def set_current_product_domains(domains: Optional[List[str]]) -> None:
    """Set product domains allowed for current request."""
    _current_product_domains.set(domains or [])


def get_current_auth_provider() -> Optional[str]:
    """Get auth provider resolved for current request."""
    return _current_auth_provider.get()


def set_current_auth_provider(provider: Optional[str]) -> None:
    """Set auth provider resolved for current request."""
    _current_auth_provider.set(provider)
