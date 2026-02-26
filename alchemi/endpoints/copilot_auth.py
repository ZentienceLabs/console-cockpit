"""Shared Copilot auth and tenant guard helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request

from alchemi.middleware.account_middleware import (
    extract_token_from_request,
    decode_jwt_token,
    _get_master_key,
    resolve_tenant_from_request,
)
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin, get_actor_role as _get_ctx_role


def _get_actor_from_request(request: Request) -> Dict[str, Any]:
    token = extract_token_from_request(request)
    if not token:
        return {}
    decoded = decode_jwt_token(token, _get_master_key())
    return decoded or {}


async def require_super_admin(request: Request):
    if not is_super_admin():
        resolve_tenant_from_request(request)
    if not is_super_admin():
        raise HTTPException(status_code=403, detail="Super admin access required")


async def require_account_admin_or_super_admin(request: Request):
    if not is_super_admin() and get_current_account_id() is None:
        resolve_tenant_from_request(request)

    if is_super_admin():
        return

    account_id = get_current_account_id()
    if account_id is None:
        raise HTTPException(status_code=403, detail="Account admin or super admin access required")


async def require_account_context(
    request: Request,
    _=Depends(require_account_admin_or_super_admin),
) -> str:
    """Return current account_id; for super admin allow explicit query param."""
    if is_super_admin():
        explicit = request.query_params.get("account_id")
        if explicit:
            return explicit
        raise HTTPException(status_code=400, detail="account_id query parameter required for super admin")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")
    return account_id


def get_actor_email_or_id(request: Request) -> str:
    actor = _get_actor_from_request(request)
    return str(
        actor.get("user_email")
        or actor.get("sub")
        or actor.get("user_id")
        or "system"
    )


def get_actor_role(request: Request) -> str:
    # Prefer role resolved by middleware context
    ctx_role = _get_ctx_role()
    if ctx_role and ctx_role != "end_user":
        return ctx_role
    # Fallback to JWT claim extraction
    actor = _get_actor_from_request(request)
    if actor.get("is_super_admin"):
        return "super_admin"
    return str(actor.get("user_role") or actor.get("role") or "end_user")


async def maybe_account_id(request: Request) -> Optional[str]:
    if not is_super_admin() and get_current_account_id() is None:
        resolve_tenant_from_request(request)
    if is_super_admin():
        return request.query_params.get("account_id")
    return get_current_account_id()
