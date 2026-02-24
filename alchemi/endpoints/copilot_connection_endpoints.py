"""
Account connection management endpoints.
Supports MCP, OpenAPI, and Integration connection types.
Also exposes Composio integration visibility catalog + account enablement controls.
"""

import copy
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_audit_helpers import log_copilot_audit_event
from alchemi.endpoints.copilot_auth import require_copilot_admin_access
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
    _auth=Depends(require_copilot_admin_access),
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
    _auth=Depends(require_copilot_admin_access),
):
    """Create a new connection."""
    from alchemi.middleware.account_middleware import decode_jwt_token, extract_token_from_request

    # Get user info for created_by
    token = extract_token_from_request(request)
    user_id = None
    if token:
        from alchemi.middleware.account_middleware import _get_master_key

        decoded = decode_jwt_token(token, _get_master_key())
        if decoded:
            user_id = decoded.get("user_id")

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
    _auth=Depends(require_copilot_admin_access),
):
    """Get a single connection (secrets masked)."""
    connection = await copilot_db.account_connections.find_by_id(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

    if connection.get("connection_data"):
        connection["connection_data"] = _mask_secrets(connection["connection_data"])

    return {"data": connection}


@router.put("/{connection_id}")
async def update_connection(
    connection_id: str,
    data: ConnectionUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Update a connection. Masked secret values (********) are preserved."""
    existing = await copilot_db.account_connections.find_by_id(connection_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Connection not found.")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}

    # Merge connection_data to preserve masked secrets
    if "connection_data" in update_data and existing.get("connection_data"):
        update_data["connection_data"] = _merge_connection_data(
            existing["connection_data"], update_data["connection_data"]
        )

    # Get user info for updated_by
    from alchemi.middleware.account_middleware import decode_jwt_token, extract_token_from_request, _get_master_key

    token = extract_token_from_request(request)
    if token:
        decoded = decode_jwt_token(token, _get_master_key())
        if decoded:
            update_data["updated_by"] = decoded.get("user_id")

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
    _auth=Depends(require_copilot_admin_access),
):
    """Delete a connection."""
    existing = await copilot_db.account_connections.find_by_id(connection_id)
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
    _auth=Depends(require_copilot_admin_access),
):
    """Test connectivity for a connection."""
    connection = await copilot_db.account_connections.find_by_id(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found.")

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
