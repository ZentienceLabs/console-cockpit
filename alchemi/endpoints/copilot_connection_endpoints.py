"""
Account connection management endpoints.
Supports MCP, OpenAPI, and Integration connection types.
Also exposes Composio integration visibility catalog + account enablement controls.
"""

import copy
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_audit_helpers import log_copilot_audit_event
from alchemi.endpoints.copilot_auth import (
    require_copilot_admin_access,
    require_copilot_user_access,
)
from alchemi.endpoints.copilot_policy_utils import (
    is_admin_claims,
    normalize_scope_type,
    resolve_scope_chain,
)
from alchemi.endpoints.copilot_types import (
    ConnectionCreate,
    ConnectionType,
    ConnectionUpdate,
)
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

router = APIRouter(prefix="/copilot/connections", tags=["Copilot - Connections"])

# Fields to mask in connection_data when reading
_SECRET_FIELDS = {
    "api_key", "bearer_token", "password", "client_secret",
    "token", "secret", "credentials", "api_key_value",
}
_CONNECTION_POLICY_TYPES = {"all", "mcp", "openapi", "integration"}
_CONNECTION_PERMISSION_MODES = {"admin_managed_use_only", "self_managed_allowed"}


class IntegrationCatalogCreate(BaseModel):
    integration_key: str
    provider: str = "composio"
    name: str
    description: Optional[str] = None
    toolkit: Optional[str] = None
    auth_config_id: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntegrationCatalogUpdate(BaseModel):
    integration_key: Optional[str] = None
    provider: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    toolkit: Optional[str] = None
    auth_config_id: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class IntegrationEnabledUpdate(BaseModel):
    integration_ids: List[str] = Field(default_factory=list)
    account_id: Optional[str] = None


class ConnectionPermissionPolicyUpsert(BaseModel):
    scope_type: str
    scope_id: str
    connection_type: str = "all"
    permission_mode: str = "admin_managed_use_only"
    allow_use_admin_connections: bool = True
    notes: Optional[str] = None
    account_id: Optional[str] = None


class ConnectionPermissionPolicyDelete(BaseModel):
    scope_type: str
    scope_id: str
    connection_type: str = "all"
    account_id: Optional[str] = None


def _resolve_optional_account_filter(account_id: Optional[str]) -> Optional[str]:
    if is_super_admin():
        if account_id:
            return account_id
        return get_current_account_id()

    resolved = get_current_account_id()
    if not resolved:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return resolved


def _resolve_required_account_for_write(account_id: Optional[str]) -> str:
    resolved = _resolve_optional_account_filter(account_id)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for this super admin write operation.",
        )
    return resolved


def _require_super_admin() -> None:
    if not is_super_admin():
        raise HTTPException(status_code=403, detail="Super admin access required.")


def _normalize_list(values: List[str]) -> List[str]:
    return list(dict.fromkeys([str(v).strip() for v in values if str(v).strip()]))


def _get_enabled_integrations_from_metadata(metadata: Any) -> List[str]:
    parsed = metadata if isinstance(metadata, dict) else {}
    entitlements = parsed.get("entitlements", {})
    raw = entitlements.get("copilot_enabled_integrations", [])
    if not isinstance(raw, list):
        raw = []
    return _normalize_list([str(x) for x in raw])


def _set_enabled_integrations_on_metadata(metadata: Any, integration_ids: List[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = metadata if isinstance(metadata, dict) else {}
    entitlements = parsed.get("entitlements", {})
    entitlements["copilot_enabled_integrations"] = _normalize_list(integration_ids)
    parsed["entitlements"] = entitlements
    return parsed


async def _integration_catalog_rows(include_inactive: bool = False) -> List[Dict[str, Any]]:
    rows = await copilot_db.integration_catalog.find_many(
        where=None if include_inactive else {"is_active": True},
        order_by="lower(name) ASC",
        limit=2000,
    )
    return [dict(r) for r in rows]


async def _integration_key_exists(integration_key: str, exclude_id: Optional[str] = None) -> bool:
    target = str(integration_key or "").strip().lower()
    if not target:
        return False

    rows = await copilot_db.integration_catalog.find_many(order_by="created_at DESC", limit=5000)
    for row in rows:
        row_id = str(row.get("id") or "")
        if exclude_id and row_id == str(exclude_id):
            continue
        if str(row.get("integration_key") or "").strip().lower() == target:
            return True
    return False


def _is_secret_key(key: str, parent_key: Optional[str] = None) -> bool:
    lowered = str(key or "").lower()
    if lowered in _SECRET_FIELDS:
        return True
    if lowered in {"authorization", "x-api-key"}:
        return True
    if lowered in {"token", "access_token", "refresh_token"}:
        return True
    if lowered in {"password", "passphrase", "private_key"}:
        return True
    if lowered in {"value"} and str(parent_key or "").lower() in {"secrets", "credentials"}:
        return True
    return False


def _mask_recursive(value: Any, parent_key: Optional[str] = None) -> Any:
    if isinstance(value, dict):
        masked: Dict[str, Any] = {}
        for k, v in value.items():
            if _is_secret_key(k, parent_key=parent_key) and v:
                masked[k] = "********"
            else:
                masked[k] = _mask_recursive(v, parent_key=str(k))
        return masked
    if isinstance(value, list):
        return [_mask_recursive(v, parent_key=parent_key) for v in value]
    return value


def _mask_secrets(connection_data) -> dict:
    """Mask sensitive fields in connection_data."""
    import json as _json

    if isinstance(connection_data, str):
        try:
            connection_data = _json.loads(connection_data)
        except (ValueError, TypeError):
            return connection_data
    return _mask_recursive(copy.deepcopy(connection_data))


def _deep_merge_preserving_masked(existing: Any, incoming: Any) -> Any:
    if incoming == "********":
        return existing

    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = copy.deepcopy(existing)
        for key, value in incoming.items():
            if key in merged:
                merged[key] = _deep_merge_preserving_masked(merged[key], value)
            else:
                merged[key] = value
        return merged

    if isinstance(existing, list) and isinstance(incoming, list):
        return incoming

    return incoming


def _merge_connection_data(existing, incoming) -> dict:
    """Merge connection_data, keeping existing secrets where incoming has masked values."""
    import json as _json

    if isinstance(existing, str):
        try:
            existing = _json.loads(existing)
        except (ValueError, TypeError):
            existing = {}
    if isinstance(incoming, str):
        try:
            incoming = _json.loads(incoming)
        except (ValueError, TypeError):
            incoming = {}

    return _deep_merge_preserving_masked(existing, incoming)


def _normalize_connection_policy_type(value: str) -> str:
    parsed = str(value or "all").strip().lower()
    if parsed not in _CONNECTION_POLICY_TYPES:
        raise HTTPException(
            status_code=400,
            detail="connection_type must be one of: all, mcp, openapi, integration.",
        )
    return parsed


def _normalize_connection_permission_mode(value: str) -> str:
    parsed = str(value or "admin_managed_use_only").strip().lower()
    if parsed not in _CONNECTION_PERMISSION_MODES:
        raise HTTPException(
            status_code=400,
            detail="permission_mode must be one of: admin_managed_use_only, self_managed_allowed.",
        )
    return parsed


def _connection_owner_user_id(connection: Dict[str, Any]) -> Optional[str]:
    metadata = connection.get("metadata")
    owner_from_meta = None
    if isinstance(metadata, dict):
        owner_from_meta = metadata.get("owner_user_id")
    owner = str(owner_from_meta or connection.get("created_by") or "").strip()
    return owner or None


def _connection_management_mode(connection: Dict[str, Any]) -> str:
    metadata = connection.get("metadata")
    mode = None
    if isinstance(metadata, dict):
        mode = metadata.get("management_mode")
    parsed = str(mode or "").strip().lower()
    if parsed in {"self_managed", "admin_managed"}:
        return parsed
    owner = _connection_owner_user_id(connection)
    return "self_managed" if owner else "admin_managed"


def _normalize_feature_flags(raw: Any) -> Dict[str, bool]:
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            raw = parsed if isinstance(parsed, dict) else {}
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    output: Dict[str, bool] = {}
    for key, value in raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        if isinstance(value, bool):
            output[k] = value
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "enabled", "on"}:
                output[k] = True
            elif lowered in {"false", "0", "no", "disabled", "off"}:
                output[k] = False
    return output


def _base_connection_feature_flags(account_metadata: Any) -> Dict[str, bool]:
    defaults = {
        "can_create_connections_openapi": True,
        "can_create_connections_mcp": True,
        "can_create_connections_composio": True,
    }
    parsed = account_metadata if isinstance(account_metadata, dict) else {}
    entitlements = parsed.get("entitlements", {})
    if not isinstance(entitlements, dict):
        return defaults
    features = _normalize_feature_flags(entitlements.get("features"))
    defaults.update({k: v for k, v in features.items() if k in defaults})
    if "copilot_connections" in features:
        allowed = bool(features.get("copilot_connections"))
        defaults["can_create_connections_openapi"] = allowed
        defaults["can_create_connections_mcp"] = allowed
        defaults["can_create_connections_composio"] = allowed
    return defaults


async def _resolve_connection_permission(
    account_id: str,
    connection_type: str,
    actor_claims: Optional[Dict[str, Any]],
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_scope_type = normalize_scope_type(scope_type) if scope_type else None
    resolved_scope_id = str(scope_id or "").strip() if scope_id else None
    if resolved_scope_type and not resolved_scope_id:
        raise HTTPException(status_code=400, detail="scope_id is required when scope_type is provided.")

    if not resolved_scope_type:
        actor_user_id = str((actor_claims or {}).get("user_id") or "").strip()
        if actor_user_id:
            resolved_scope_type = "user"
            resolved_scope_id = actor_user_id
        else:
            resolved_scope_type = "account"
            resolved_scope_id = str(account_id)

    chain = await resolve_scope_chain(
        account_id=account_id,
        scope_type=resolved_scope_type,
        scope_id=str(resolved_scope_id),
        claims=actor_claims,
    )

    rows = await copilot_db.connection_permission_policies.find_many(
        where={"account_id": account_id},
        order_by="updated_at DESC",
        limit=5000,
    )
    by_scope_and_type: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = f"{str(row.get('scope_type') or '')}:{str(row.get('scope_id') or '')}:{str(row.get('connection_type') or '')}"
        if key not in by_scope_and_type:
            by_scope_and_type[key] = row

    mode = "admin_managed_use_only"
    allow_use_admin_connections = True
    resolved_from = "default"

    for scope_item in reversed(chain):  # account -> ... -> specific
        for ctype in ("all", connection_type):
            key = f"{scope_item['scope_type']}:{scope_item['scope_id']}:{ctype}"
            row = by_scope_and_type.get(key)
            if not row:
                continue
            mode = _normalize_connection_permission_mode(str(row.get("permission_mode") or mode))
            allow_use_admin_connections = bool(row.get("allow_use_admin_connections", allow_use_admin_connections))
            resolved_from = f"{scope_item['scope_type']}:{scope_item['scope_id']}:{ctype}"

    return {
        "resolved_scope": {"scope_type": resolved_scope_type, "scope_id": str(resolved_scope_id)},
        "scope_chain": chain,
        "permission_mode": mode,
        "allow_use_admin_connections": allow_use_admin_connections,
        "resolved_from": resolved_from,
    }


async def _resolve_connection_create_feature_gate(
    account_id: str,
    account_metadata: Any,
    connection_type: str,
    actor_claims: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    key_map = {
        "mcp": "can_create_connections_mcp",
        "openapi": "can_create_connections_openapi",
        "integration": "can_create_connections_composio",
    }
    feature_key = key_map.get(connection_type, "can_create_connections_openapi")
    features = _base_connection_feature_flags(account_metadata)

    actor_user_id = str((actor_claims or {}).get("user_id") or "").strip()
    if actor_user_id:
        scope_type = "user"
        scope_id = actor_user_id
    else:
        scope_type = "account"
        scope_id = str(account_id)

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
    by_scope: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = f"{str(row.get('scope_type') or '')}:{str(row.get('scope_id') or '')}"
        if key not in by_scope:
            by_scope[key] = row

    resolved_from = "account_entitlements_default"
    for scope_item in reversed(chain):
        row = by_scope.get(f"{scope_item['scope_type']}:{scope_item['scope_id']}")
        if not row:
            continue
        flags = _normalize_feature_flags(row.get("flags"))
        if feature_key in flags:
            features[feature_key] = bool(flags[feature_key])
            resolved_from = f"{scope_item['scope_type']}:{scope_item['scope_id']}"

    return {
        "feature_key": feature_key,
        "enabled": bool(features.get(feature_key, True)),
        "resolved_from": resolved_from,
    }


@router.get("/permission-modes")
async def list_connection_permission_modes(
    request: Request,
    account_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    connection_type: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """List scoped connection permission mode policies."""
    resolved_account_id = _resolve_required_account_for_write(account_id)
    where: Dict[str, Any] = {"account_id": resolved_account_id}
    if scope_type:
        where["scope_type"] = normalize_scope_type(scope_type)
    if scope_id:
        where["scope_id"] = str(scope_id)
    if connection_type:
        where["connection_type"] = _normalize_connection_policy_type(connection_type)

    rows = await copilot_db.connection_permission_policies.find_many(
        where=where,
        order_by="scope_type ASC, scope_id ASC, connection_type ASC",
        limit=5000,
    )
    return {"data": rows, "total": len(rows)}


@router.put("/permission-modes")
async def upsert_connection_permission_mode(
    data: ConnectionPermissionPolicyUpsert,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Upsert scoped connection permission mode policy."""
    resolved_account_id = _resolve_required_account_for_write(data.account_id)
    scope_type = normalize_scope_type(data.scope_type)
    scope_id = str(data.scope_id or "").strip()
    if not scope_id:
        raise HTTPException(status_code=400, detail="scope_id is required.")
    if scope_type == "account" and scope_id != str(resolved_account_id):
        raise HTTPException(status_code=400, detail="Account scope_id must match account_id.")

    policy_connection_type = _normalize_connection_policy_type(data.connection_type)
    permission_mode = _normalize_connection_permission_mode(data.permission_mode)
    actor_user_id = str((_auth or {}).get("user_id") or "").strip() or None

    rows = await copilot_db.connection_permission_policies.find_many(
        where={
            "account_id": resolved_account_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "connection_type": policy_connection_type,
        },
        limit=1,
    )
    if rows:
        row = await copilot_db.connection_permission_policies.update(
            rows[0]["id"],
            {
                "permission_mode": permission_mode,
                "allow_use_admin_connections": bool(data.allow_use_admin_connections),
                "notes": data.notes,
                "updated_by": actor_user_id,
            },
        )
        action = "update"
    else:
        row = await copilot_db.connection_permission_policies.create(
            {
                "account_id": resolved_account_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "connection_type": policy_connection_type,
                "permission_mode": permission_mode,
                "allow_use_admin_connections": bool(data.allow_use_admin_connections),
                "notes": data.notes,
                "created_by": actor_user_id,
                "updated_by": actor_user_id,
            }
        )
        action = "create"

    await log_copilot_audit_event(
        account_id=resolved_account_id,
        event_type="copilot_connection_permission_policy",
        resource_type="connection_permission_policy",
        resource_id=str(row.get("id") or ""),
        action=action,
        message=f"{action.title()}d connection permission mode for {scope_type}:{scope_id} ({policy_connection_type}).",
        details={
            "scope_type": scope_type,
            "scope_id": scope_id,
            "connection_type": policy_connection_type,
            "permission_mode": permission_mode,
            "allow_use_admin_connections": bool(data.allow_use_admin_connections),
        },
        request=request,
    )
    return {"data": row}


@router.delete("/permission-modes")
async def delete_connection_permission_mode(
    data: ConnectionPermissionPolicyDelete,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete scoped connection permission mode policy."""
    resolved_account_id = _resolve_required_account_for_write(data.account_id)
    scope_type = normalize_scope_type(data.scope_type)
    scope_id = str(data.scope_id or "").strip()
    if not scope_id:
        raise HTTPException(status_code=400, detail="scope_id is required.")
    if scope_type == "account" and scope_id != str(resolved_account_id):
        raise HTTPException(status_code=400, detail="Account scope_id must match account_id.")

    policy_connection_type = _normalize_connection_policy_type(data.connection_type)
    rows = await copilot_db.connection_permission_policies.find_many(
        where={
            "account_id": resolved_account_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "connection_type": policy_connection_type,
        },
        limit=1,
    )
    if not rows:
        return {"status": "ok", "deleted": False}

    row = rows[0]
    deleted = await copilot_db.connection_permission_policies.delete(row["id"])
    if deleted:
        await log_copilot_audit_event(
            account_id=resolved_account_id,
            event_type="copilot_connection_permission_policy",
            resource_type="connection_permission_policy",
            resource_id=str(row.get("id") or ""),
            action="delete",
            severity="warning",
            message=f"Deleted connection permission mode for {scope_type}:{scope_id} ({policy_connection_type}).",
            details={
                "scope_type": scope_type,
                "scope_id": scope_id,
                "connection_type": policy_connection_type,
            },
            request=request,
        )
    return {"status": "ok", "deleted": bool(deleted)}


@router.get("/permission-modes/resolve")
async def resolve_connection_permission_mode(
    request: Request,
    account_id: Optional[str] = None,
    connection_type: str = Query(default="mcp"),
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    _auth=Depends(require_copilot_user_access),
):
    """Resolve effective connection permission mode for actor scope."""
    resolved_account_id = _resolve_required_account_for_write(account_id)
    parsed_connection_type = _normalize_connection_policy_type(connection_type)
    if parsed_connection_type == "all":
        parsed_connection_type = "mcp"

    resolved = await _resolve_connection_permission(
        account_id=resolved_account_id,
        connection_type=parsed_connection_type,
        actor_claims=_auth,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return {
        "account_id": resolved_account_id,
        "connection_type": parsed_connection_type,
        **resolved,
    }


@router.get("/integrations/catalog")
async def list_integration_catalog(
    request: Request,
    include_inactive: bool = False,
    _auth=Depends(require_copilot_admin_access),
):
    if not is_super_admin():
        include_inactive = False
    rows = await _integration_catalog_rows(include_inactive=include_inactive)
    return {"data": rows, "total": len(rows), "can_manage": bool(is_super_admin())}


@router.post("/integrations/catalog")
async def create_integration_catalog(
    data: IntegrationCatalogCreate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    _require_super_admin()

    key = str(data.integration_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="integration_key is required.")
    if await _integration_key_exists(key):
        raise HTTPException(status_code=409, detail="Integration key already exists in catalog.")

    payload = data.model_dump()
    payload["integration_key"] = key
    created = await copilot_db.integration_catalog.create(payload)

    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_integration_catalog",
        resource_type="integration_catalog",
        resource_id=str(created.get("id") or ""),
        action="create",
        message=f"Created integration catalog entry '{created.get('name')}'.",
        details={"integration_key": key, "provider": created.get("provider")},
        request=request,
    )
    return {"data": created}


@router.put("/integrations/catalog/{integration_id}")
async def update_integration_catalog(
    integration_id: str,
    data: IntegrationCatalogUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    _require_super_admin()

    existing = await copilot_db.integration_catalog.find_by_id(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration catalog entry not found.")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "integration_key" in update_data:
        key = str(update_data["integration_key"] or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="integration_key cannot be empty.")
        if await _integration_key_exists(key, exclude_id=integration_id):
            raise HTTPException(status_code=409, detail="Integration key already exists in catalog.")
        update_data["integration_key"] = key

    updated = await copilot_db.integration_catalog.update(integration_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Integration catalog entry not found.")

    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_integration_catalog",
        resource_type="integration_catalog",
        resource_id=str(integration_id),
        action="update",
        message=f"Updated integration catalog entry '{updated.get('name')}'.",
        details={"changes": list(update_data.keys())},
        request=request,
    )
    return {"data": updated}


@router.delete("/integrations/catalog/{integration_id}")
async def delete_integration_catalog(
    integration_id: str,
    request: Request,
    hard_delete: bool = False,
    _auth=Depends(require_copilot_admin_access),
):
    _require_super_admin()

    existing = await copilot_db.integration_catalog.find_by_id(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration catalog entry not found.")

    if hard_delete:
        deleted = await copilot_db.integration_catalog.delete(integration_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Integration catalog entry not found.")
    else:
        await copilot_db.integration_catalog.update(integration_id, {"is_active": False})

    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_integration_catalog",
        resource_type="integration_catalog",
        resource_id=str(integration_id),
        action="delete" if hard_delete else "disable",
        severity="warning",
        message=f"{'Deleted' if hard_delete else 'Disabled'} integration catalog entry '{existing.get('name')}'.",
        details={"hard_delete": hard_delete},
        request=request,
    )
    return {"status": "ok"}


@router.get("/integrations/enabled")
async def get_enabled_integrations(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = _resolve_required_account_for_write(account_id)

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": resolved_account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    catalog = await _integration_catalog_rows(include_inactive=False)
    active_ids = set([str(c.get("id")) for c in catalog if c.get("id")])

    enabled_ids = [
        i for i in _get_enabled_integrations_from_metadata(account.metadata)
        if i in active_ids
    ]

    return {
        "data": {
            "account_id": resolved_account_id,
            "enabled_integration_ids": enabled_ids,
            "catalog": catalog,
        }
    }


@router.put("/integrations/enabled")
async def update_enabled_integrations(
    data: IntegrationEnabledUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = _resolve_required_account_for_write(data.account_id)

    from litellm.proxy.proxy_server import prisma_client
    from prisma import Json

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": resolved_account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    requested_ids = _normalize_list(data.integration_ids)

    catalog = await _integration_catalog_rows(include_inactive=False)
    active_ids = set([str(c.get("id")) for c in catalog if c.get("id")])

    invalid = [iid for iid in requested_ids if iid not in active_ids]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Some integration ids are not active in the integration catalog.",
                "invalid_ids": invalid,
            },
        )

    metadata = _set_enabled_integrations_on_metadata(account.metadata, requested_ids)
    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": resolved_account_id},
        data={"metadata": Json(metadata)},
    )

    await log_copilot_audit_event(
        account_id=resolved_account_id,
        event_type="copilot_integration_visibility",
        resource_type="account",
        resource_id=resolved_account_id,
        action="update",
        message="Updated enabled Copilot integrations for account.",
        details={"enabled_integration_ids": requested_ids, "count": len(requested_ids)},
        request=request,
    )

    return {
        "data": {
            "account_id": resolved_account_id,
            "enabled_integration_ids": requested_ids,
        }
    }


@router.get("/")
async def list_connections(
    request: Request,
    account_id: Optional[str] = None,
    connection_type: Optional[ConnectionType] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_user_access),
):
    """List connections with optional filters."""
    where = {}
    resolved_account_id = _resolve_optional_account_filter(account_id)
    if resolved_account_id:
        where["account_id"] = resolved_account_id
    if connection_type:
        where["connection_type"] = connection_type.value
    if is_active is not None:
        where["is_active"] = is_active

    connections = await copilot_db.account_connections.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.account_connections.count(where=where if where else None)

    is_admin = is_admin_claims(_auth)
    if not is_admin:
        actor_user_id = str((_auth or {}).get("user_id") or "").strip()
        permission_cache: Dict[str, Dict[str, Any]] = {}
        filtered: List[Dict[str, Any]] = []
        for conn in connections:
            ctype = str(conn.get("connection_type") or "").strip().lower()
            if ctype not in {"mcp", "openapi", "integration"}:
                continue
            if ctype not in permission_cache:
                permission_cache[ctype] = await _resolve_connection_permission(
                    account_id=str(conn.get("account_id") or resolved_account_id or ""),
                    connection_type=ctype,
                    actor_claims=_auth,
                )
            permission = permission_cache[ctype]
            mgmt_mode = _connection_management_mode(conn)
            owner_user_id = _connection_owner_user_id(conn)

            if mgmt_mode == "self_managed":
                if (
                    actor_user_id
                    and owner_user_id == actor_user_id
                    and permission.get("permission_mode") == "self_managed_allowed"
                ):
                    filtered.append(conn)
                continue

            if permission.get("allow_use_admin_connections", True):
                filtered.append(conn)

        connections = filtered
        total = len(connections)

    # Mask secrets in response
    for conn in connections:
        if "connection_data" in conn and conn["connection_data"]:
            conn["connection_data"] = _mask_secrets(conn["connection_data"])

    return {"data": connections, "connections": connections, "total": total}


@router.post("/")
async def create_connection(
    data: ConnectionCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_user_access),
):
    """Create a new connection."""
    user_id = str((_auth or {}).get("user_id") or "").strip() or None
    is_admin = is_admin_claims(_auth)
    create_data = data.model_dump()
    create_data["account_id"] = _resolve_required_account_for_write(account_id)
    create_data["connection_type"] = create_data["connection_type"].value
    create_data["created_by"] = user_id
    create_data["updated_by"] = user_id

    if create_data["connection_type"] == "integration":
        raise HTTPException(
            status_code=400,
            detail=(
                "Composio integrations are visibility-managed in Cockpit. "
                "Use /copilot/connections/integrations/enabled for account enablement."
            ),
        )

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": create_data["account_id"]}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if not is_admin:
        permission = await _resolve_connection_permission(
            account_id=create_data["account_id"],
            connection_type=create_data["connection_type"],
            actor_claims=_auth,
        )
        if permission.get("permission_mode") != "self_managed_allowed":
            raise HTTPException(
                status_code=403,
                detail="Connection creation is restricted to admin-managed use-only mode for your scope.",
            )
        feature_gate = await _resolve_connection_create_feature_gate(
            account_id=create_data["account_id"],
            account_metadata=account.metadata,
            connection_type=create_data["connection_type"],
            actor_claims=_auth,
        )
        if not feature_gate.get("enabled", True):
            raise HTTPException(
                status_code=403,
                detail=f"Feature '{feature_gate.get('feature_key')}' is disabled for your scope.",
            )

    metadata = create_data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    if is_admin:
        metadata["management_mode"] = "admin_managed"
    else:
        metadata["management_mode"] = "self_managed"
        if user_id:
            metadata["owner_user_id"] = user_id
    create_data["metadata"] = metadata

    connection = await copilot_db.account_connections.create(
        data=create_data
    )

    await log_copilot_audit_event(
        account_id=create_data["account_id"],
        event_type="copilot_connection",
        resource_type="connection",
        resource_id=str(connection.get("id") or ""),
        action="create",
        message=f"Created {create_data.get('connection_type')} connection '{create_data.get('name')}'.",
        details={
            "connection_type": create_data.get("connection_type"),
            "is_active": create_data.get("is_active", True),
        },
        request=request,
    )

    # Mask secrets in response
    if connection.get("connection_data"):
        connection["connection_data"] = _mask_secrets(connection["connection_data"])

    return {"data": connection}


@router.get("/{connection_id}")
async def get_connection(
    connection_id: str,
    request: Request,
    _auth=Depends(require_copilot_user_access),
):
    """Get a single connection (secrets masked)."""
    connection = await copilot_db.account_connections.find_by_id(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if not is_admin_claims(_auth):
        actor_user_id = str((_auth or {}).get("user_id") or "").strip()
        ctype = str(connection.get("connection_type") or "").strip().lower()
        permission = await _resolve_connection_permission(
            account_id=str(connection.get("account_id") or ""),
            connection_type=ctype,
            actor_claims=_auth,
        )
        mgmt_mode = _connection_management_mode(connection)
        owner_user_id = _connection_owner_user_id(connection)
        if mgmt_mode == "self_managed":
            if owner_user_id != actor_user_id:
                raise HTTPException(status_code=403, detail="Not allowed to view this self-managed connection.")
            if permission.get("permission_mode") != "self_managed_allowed":
                raise HTTPException(status_code=403, detail="Self-managed connections are disabled for your scope.")
        else:
            if not permission.get("allow_use_admin_connections", True):
                raise HTTPException(status_code=403, detail="Admin-managed connections are disabled for your scope.")

    if connection.get("connection_data"):
        connection["connection_data"] = _mask_secrets(connection["connection_data"])

    return {"data": connection}


@router.put("/{connection_id}")
async def update_connection(
    connection_id: str,
    data: ConnectionUpdate,
    request: Request,
    _auth=Depends(require_copilot_user_access),
):
    """Update a connection. Masked secret values (********) are preserved."""
    existing = await copilot_db.account_connections.find_by_id(connection_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Connection not found.")

    actor_user_id = str((_auth or {}).get("user_id") or "").strip()
    if not is_admin_claims(_auth):
        ctype = str(existing.get("connection_type") or "").strip().lower()
        permission = await _resolve_connection_permission(
            account_id=str(existing.get("account_id") or ""),
            connection_type=ctype,
            actor_claims=_auth,
        )
        mgmt_mode = _connection_management_mode(existing)
        owner_user_id = _connection_owner_user_id(existing)
        if mgmt_mode != "self_managed" or owner_user_id != actor_user_id:
            raise HTTPException(status_code=403, detail="Only your own self-managed connections can be edited.")
        if permission.get("permission_mode") != "self_managed_allowed":
            raise HTTPException(status_code=403, detail="Self-managed connections are disabled for your scope.")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}

    # Merge connection_data to preserve masked secrets
    if "connection_data" in update_data and existing.get("connection_data"):
        update_data["connection_data"] = _merge_connection_data(
            existing["connection_data"], update_data["connection_data"]
        )

    if actor_user_id:
        update_data["updated_by"] = actor_user_id

    connection = await copilot_db.account_connections.update(connection_id, update_data)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

    await log_copilot_audit_event(
        account_id=str(connection.get("account_id") or "") or None,
        event_type="copilot_connection",
        resource_type="connection",
        resource_id=str(connection_id),
        action="update",
        message=f"Updated connection '{connection.get('name')}'.",
        details={"changes": list(update_data.keys())},
        request=request,
    )

    if connection.get("connection_data"):
        connection["connection_data"] = _mask_secrets(connection["connection_data"])

    return {"data": connection}


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: str,
    request: Request,
    _auth=Depends(require_copilot_user_access),
):
    """Delete a connection."""
    existing = await copilot_db.account_connections.find_by_id(connection_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if not is_admin_claims(_auth):
        actor_user_id = str((_auth or {}).get("user_id") or "").strip()
        ctype = str(existing.get("connection_type") or "").strip().lower()
        permission = await _resolve_connection_permission(
            account_id=str(existing.get("account_id") or ""),
            connection_type=ctype,
            actor_claims=_auth,
        )
        mgmt_mode = _connection_management_mode(existing)
        owner_user_id = _connection_owner_user_id(existing)
        if mgmt_mode != "self_managed" or owner_user_id != actor_user_id:
            raise HTTPException(status_code=403, detail="Only your own self-managed connections can be deleted.")
        if permission.get("permission_mode") != "self_managed_allowed":
            raise HTTPException(status_code=403, detail="Self-managed connections are disabled for your scope.")

    deleted = await copilot_db.account_connections.delete(connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found.")

    await log_copilot_audit_event(
        account_id=str((existing or {}).get("account_id") or "") or None,
        event_type="copilot_connection",
        resource_type="connection",
        resource_id=str(connection_id),
        action="delete",
        severity="warning",
        message=f"Deleted connection '{(existing or {}).get('name')}'.",
        request=request,
    )
    return {"status": "ok"}


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: str,
    request: Request,
    _auth=Depends(require_copilot_user_access),
):
    """Test connectivity for a connection."""
    connection = await copilot_db.account_connections.find_by_id(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if not is_admin_claims(_auth):
        actor_user_id = str((_auth or {}).get("user_id") or "").strip()
        ctype = str(connection.get("connection_type") or "").strip().lower()
        permission = await _resolve_connection_permission(
            account_id=str(connection.get("account_id") or ""),
            connection_type=ctype,
            actor_claims=_auth,
        )
        mgmt_mode = _connection_management_mode(connection)
        owner_user_id = _connection_owner_user_id(connection)
        if mgmt_mode != "self_managed" or owner_user_id != actor_user_id:
            raise HTTPException(status_code=403, detail="Only your own self-managed connections can be tested.")
        if permission.get("permission_mode") != "self_managed_allowed":
            raise HTTPException(status_code=403, detail="Self-managed connections are disabled for your scope.")

    conn_type = connection.get("connection_type")
    conn_data = connection.get("connection_data", {})
    if isinstance(conn_data, str):
        import json as _json

        try:
            conn_data = _json.loads(conn_data)
        except (ValueError, TypeError):
            conn_data = {}

    result: Dict[str, Any]
    severity = "info"
    try:
        import httpx

        if conn_type == "mcp":
            url = conn_data.get("url")
            if url:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, timeout=10)
                result = {"status": "ok", "http_status": resp.status_code}
            else:
                result = {"status": "ok", "message": "Stdio connections cannot be tested remotely."}

        elif conn_type == "openapi":
            base_url = conn_data.get("base_url") or conn_data.get("spec_url")
            if base_url:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(base_url, timeout=10)
                result = {"status": "ok", "http_status": resp.status_code}
            else:
                result = {"status": "error", "message": "No base_url or spec_url configured."}
                severity = "warning"

        elif conn_type == "integration":
            result = {"status": "ok", "message": "Integration connections require provider-specific tests."}

        else:
            result = {"status": "unknown", "message": f"Unknown connection type: {conn_type}"}
            severity = "warning"

    except Exception as e:
        result = {"status": "error", "message": str(e)}
        severity = "warning"

    await log_copilot_audit_event(
        account_id=str(connection.get("account_id") or "") or None,
        event_type="copilot_connection_test",
        resource_type="connection",
        resource_id=str(connection_id),
        action="test",
        severity=severity,
        message=f"Tested connection '{connection.get('name')}' with status={result.get('status')}",
        details=result,
        request=request,
    )

    return result
