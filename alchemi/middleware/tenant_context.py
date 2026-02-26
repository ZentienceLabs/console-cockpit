"""
Async context variables for multi-tenant request scoping.
Stores the current account_id, super admin flag, and actor role for the duration of each request.
"""
import contextvars
from typing import Optional

_current_account_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_account_id", default=None
)
_is_super_admin: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "is_super_admin", default=False
)
_actor_role: contextvars.ContextVar[str] = contextvars.ContextVar(
    "actor_role", default="end_user"
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


def get_actor_role() -> str:
    """Get the actor role for the current request context (super_admin, account_admin, end_user)."""
    return _actor_role.get()


def set_actor_role(role: str) -> None:
    """Set the actor role for the current request context."""
    _actor_role.set(role)
