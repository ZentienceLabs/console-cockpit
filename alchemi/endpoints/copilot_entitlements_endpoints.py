"""
Account entitlements + scoped feature-flag policy endpoints.

- Super-admin-only: manage per-account entitlements in Alchemi_AccountTable.metadata.entitlements
- Account-admin: manage scoped feature flags (account/group/team/user) in copilot.feature_flag_policies
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from prisma import Json
from pydantic import BaseModel, Field

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_audit_helpers import log_copilot_audit_event
from alchemi.endpoints.copilot_auth import (
    require_copilot_admin_access,
    require_copilot_user_access,
)
from alchemi.endpoints.copilot_policy_utils import (
    normalize_scope_type,
    resolve_account_scope,
    resolve_scope_chain,
)

router = APIRouter(prefix="/copilot/entitlements", tags=["Copilot - Entitlements"])


DEFAULT_FEATURE_FLAGS: Dict[str, bool] = {
    "can_create_connections_openapi": True,
    "can_create_connections_mcp": True,
    "can_create_connections_composio": True,
    "can_create_agents": True,
    "can_generate_images": True,
    "can_access_models": True,
}


class EntitlementsUpdate(BaseModel):
    max_models: Optional[int] = None
    max_keys: Optional[int] = None
    max_teams: Optional[int] = None
    max_budget: Optional[float] = None
    features: Optional[Dict[str, bool]] = None


class FeaturePolicyUpsert(BaseModel):
    scope_type: str
    scope_id: str
    flags: Dict[str, Optional[bool]] = Field(default_factory=dict)
    notes: Optional[str] = None
    account_id: Optional[str] = None


class FeaturePolicyDelete(BaseModel):
    scope_type: str
    scope_id: str
    account_id: Optional[str] = None


async def _require_super_admin(request: Request):
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


def _normalize_feature_flags(flags: Dict[str, Any]) -> Dict[str, bool]:
    output: Dict[str, bool] = {}
    for key, value in (flags or {}).items():
        key_str = str(key or "").strip()
        if not key_str:
            continue
        if value is None:
            continue
        if isinstance(value, bool):
            output[key_str] = value
            continue
        if isinstance(value, str):
            lower = value.strip().lower()
            if lower in {"true", "1", "yes", "enabled", "on"}:
                output[key_str] = True
                continue
            if lower in {"false", "0", "no", "disabled", "off"}:
                output[key_str] = False
                continue
        if isinstance(value, (int, float)):
            output[key_str] = bool(value)
    return output


def _coerce_flags_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _account_feature_baseline(metadata: Any) -> Dict[str, bool]:
    baseline = dict(DEFAULT_FEATURE_FLAGS)
    parsed = metadata if isinstance(metadata, dict) else {}
    entitlements = parsed.get("entitlements", {})
    if not isinstance(entitlements, dict):
        return baseline

    raw_features = entitlements.get("features", {})
    if isinstance(raw_features, dict):
        baseline.update(_normalize_feature_flags(raw_features))

        # Backward compatibility aliases
        if "copilot_agents" in raw_features:
            baseline["can_create_agents"] = bool(raw_features.get("copilot_agents"))
        if "copilot_connections" in raw_features:
            v = bool(raw_features.get("copilot_connections"))
            baseline["can_create_connections_openapi"] = v
            baseline["can_create_connections_mcp"] = v
            baseline["can_create_connections_composio"] = v
        if "model_management" in raw_features:
            baseline["can_access_models"] = bool(raw_features.get("model_management"))
        if "playground" in raw_features:
            baseline["can_generate_images"] = bool(raw_features.get("playground"))

    return baseline


async def _get_account_or_404(account_id: str):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


async def _resolve_effective_feature_flags(
    account_id: str,
    scope_type: str,
    scope_id: str,
    actor_claims: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    account = await _get_account_or_404(account_id)
    effective = _account_feature_baseline(account.metadata)

    chain = await resolve_scope_chain(
        account_id=account_id,
        scope_type=scope_type,
        scope_id=scope_id,
        claims=actor_claims,
    )

    rows = await copilot_db.feature_flag_policies.find_many(
        where={"account_id": account_id},
        order_by="updated_at DESC",
        limit=5000,
    )
    row_by_scope = {
        f"{str(r.get('scope_type') or '')}:{str(r.get('scope_id') or '')}": r for r in rows
    }

    applied: List[Dict[str, Any]] = []
    # Apply broad -> specific (account ... user)
    for item in reversed(chain):
        key = f"{item['scope_type']}:{item['scope_id']}"
        row = row_by_scope.get(key)
        if not row:
            continue
        flags = _normalize_feature_flags(_coerce_flags_payload(row.get("flags")))
        if flags:
            effective.update(flags)
        applied.append(
            {
                "scope_type": item["scope_type"],
                "scope_id": item["scope_id"],
                "flags": flags,
                "notes": row.get("notes"),
                "updated_at": row.get("updated_at"),
                "updated_by": row.get("updated_by"),
            }
        )

    return {
        "account_id": account_id,
        "resolved_scope": {"scope_type": scope_type, "scope_id": scope_id},
        "scope_chain": chain,
        "applied_policies": applied,
        "effective_features": effective,
    }


@router.get("/features/policies")
async def list_feature_policies(
    request: Request,
    account_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """List scoped feature policies for an account."""
    resolved_account_id = resolve_account_scope(account_id, require_for_super_admin=True)

    where: Dict[str, Any] = {"account_id": resolved_account_id}
    if scope_type:
        where["scope_type"] = normalize_scope_type(scope_type)
    if scope_id:
        where["scope_id"] = str(scope_id)

    rows = await copilot_db.feature_flag_policies.find_many(
        where=where,
        order_by="scope_type ASC, scope_id ASC",
        limit=5000,
    )
    for row in rows:
        row["flags"] = _normalize_feature_flags(_coerce_flags_payload(row.get("flags")))
    return {"data": rows, "total": len(rows)}


@router.put("/features/policies")
async def upsert_feature_policy(
    data: FeaturePolicyUpsert,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Upsert scoped feature flags for account/group/team/user."""
    resolved_account_id = resolve_account_scope(data.account_id, require_for_super_admin=True)
    scope_type = normalize_scope_type(data.scope_type)
    scope_id = str(data.scope_id or "").strip()
    if not scope_id:
        raise HTTPException(status_code=400, detail="scope_id is required.")
    if scope_type == "account" and scope_id != str(resolved_account_id):
        raise HTTPException(status_code=400, detail="Account scope_id must match account_id.")

    normalized_flags = _normalize_feature_flags(data.flags)
    actor_user_id = str((_auth or {}).get("user_id") or "").strip() or None

    existing_rows = await copilot_db.feature_flag_policies.find_many(
        where={
            "account_id": resolved_account_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
        },
        limit=1,
    )
    if existing_rows:
        updated = await copilot_db.feature_flag_policies.update(
            existing_rows[0]["id"],
            {
                "flags": normalized_flags,
                "notes": data.notes,
                "updated_by": actor_user_id,
            },
        )
        row = updated
        action = "update"
    else:
        row = await copilot_db.feature_flag_policies.create(
            {
                "account_id": resolved_account_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "flags": normalized_flags,
                "notes": data.notes,
                "created_by": actor_user_id,
                "updated_by": actor_user_id,
            }
        )
        action = "create"

    await log_copilot_audit_event(
        account_id=resolved_account_id,
        event_type="copilot_feature_policy",
        resource_type="feature_policy",
        resource_id=str(row.get("id") or ""),
        action=action,
        message=f"{action.title()}d scoped feature policy for {scope_type}:{scope_id}.",
        details={"scope_type": scope_type, "scope_id": scope_id, "flags": normalized_flags},
        request=request,
    )

    resolved = await _resolve_effective_feature_flags(
        account_id=resolved_account_id,
        scope_type=scope_type,
        scope_id=scope_id,
        actor_claims=_auth,
    )
    return {"data": row, "resolved": resolved}


@router.delete("/features/policies")
async def delete_feature_policy(
    data: FeaturePolicyDelete,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete scoped feature policy row."""
    resolved_account_id = resolve_account_scope(data.account_id, require_for_super_admin=True)
    scope_type = normalize_scope_type(data.scope_type)
    scope_id = str(data.scope_id or "").strip()
    if not scope_id:
        raise HTTPException(status_code=400, detail="scope_id is required.")
    if scope_type == "account" and scope_id != str(resolved_account_id):
        raise HTTPException(status_code=400, detail="Account scope_id must match account_id.")

    rows = await copilot_db.feature_flag_policies.find_many(
        where={
            "account_id": resolved_account_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
        },
        limit=1,
    )
    if not rows:
        return {"status": "ok", "deleted": False}

    row = rows[0]
    deleted = await copilot_db.feature_flag_policies.delete(row["id"])
    if deleted:
        await log_copilot_audit_event(
            account_id=resolved_account_id,
            event_type="copilot_feature_policy",
            resource_type="feature_policy",
            resource_id=str(row.get("id") or ""),
            action="delete",
            severity="warning",
            message=f"Deleted scoped feature policy for {scope_type}:{scope_id}.",
            details={"scope_type": scope_type, "scope_id": scope_id},
            request=request,
        )

    return {"status": "ok", "deleted": bool(deleted)}


@router.get("/features/resolve")
async def resolve_feature_flags(
    request: Request,
    account_id: Optional[str] = None,
    scope_type: Optional[str] = Query(default=None),
    scope_id: Optional[str] = Query(default=None),
    _auth=Depends(require_copilot_user_access),
):
    """
    Resolve effective feature flags for a scope with inheritance:
    account <- group <- team <- user.
    """
    resolved_account_id = resolve_account_scope(account_id, require_for_super_admin=True)

    if scope_type is None or scope_id is None:
        # Default to current caller user scope when available.
        actor_user_id = str((_auth or {}).get("user_id") or "").strip()
        if actor_user_id:
            scope_type = "user"
            scope_id = actor_user_id
        else:
            scope_type = "account"
            scope_id = str(resolved_account_id)

    resolved = await _resolve_effective_feature_flags(
        account_id=resolved_account_id,
        scope_type=normalize_scope_type(scope_type),
        scope_id=str(scope_id),
        actor_claims=_auth,
    )
    return resolved


@router.get("/{account_id}")
async def get_entitlements(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Get entitlements for a specific account."""
    account = await _get_account_or_404(account_id)
    meta = account.metadata if isinstance(account.metadata, dict) else {}
    entitlements = meta.get("entitlements", {})

    return {
        "account_id": account_id,
        "entitlements": entitlements,
    }


@router.put("/{account_id}")
async def update_entitlements(
    account_id: str,
    data: EntitlementsUpdate,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Update entitlements for a specific account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await _get_account_or_404(account_id)
    meta = account.metadata if isinstance(account.metadata, dict) else {}
    entitlements = meta.get("entitlements", {})

    # Merge provided fields into existing entitlements
    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        if key == "features" and isinstance(value, dict):
            existing_features = entitlements.get("features", {})
            existing_features.update(value)
            entitlements["features"] = existing_features
        else:
            entitlements[key] = value

    meta["entitlements"] = entitlements

    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data={"metadata": Json(meta)},
    )

    return {
        "account_id": account_id,
        "entitlements": entitlements,
        "status": "updated",
    }
