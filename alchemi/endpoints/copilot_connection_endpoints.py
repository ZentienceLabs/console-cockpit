"""Copilot connections/tools endpoints (OpenAPI/MCP/composio governance)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import append_audit_event, kv_delete, kv_get, kv_list, kv_put
from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    require_account_admin_or_super_admin,
    require_account_context,
    require_super_admin,
)
from alchemi.endpoints.copilot_helpers import mark_copilot_meta, require_prisma


router = APIRouter(prefix="/copilot/connections", tags=["Copilot Connections"])


class MCPServerCreate(BaseModel):
    server_name: str
    alias: Optional[str] = None
    description: Optional[str] = None
    transport: str = "sse"
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, Any] = Field(default_factory=dict)
    credentials: Dict[str, Any] = Field(default_factory=dict)
    mcp_access_groups: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)


class MCPServerUpdate(BaseModel):
    server_name: Optional[str] = None
    alias: Optional[str] = None
    description: Optional[str] = None
    transport: Optional[str] = None
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, Any]] = None
    credentials: Optional[Dict[str, Any]] = None
    mcp_access_groups: Optional[List[str]] = None
    allowed_tools: Optional[List[str]] = None


class OpenAPIConnectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    base_url: Optional[str] = None
    spec_url: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None
    spec_text: Optional[str] = None
    auth: Optional[Dict[str, Any]] = None
    auth_type: Optional[str] = None
    auth_config: Dict[str, Any] = Field(default_factory=dict)
    default_headers: Dict[str, Any] = Field(default_factory=dict)
    secrets: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OpenAPIConnectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    base_url: Optional[str] = None
    spec_url: Optional[str] = None
    spec_json: Optional[Dict[str, Any]] = None
    spec_text: Optional[str] = None
    auth: Optional[Dict[str, Any]] = None
    auth_type: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None
    default_headers: Optional[Dict[str, Any]] = None
    secrets: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class ToolEnablementUpsert(BaseModel):
    integration_id: str
    scope_type: str = "ACCOUNT"  # ACCOUNT|ORG|TEAM|USER
    scope_id: Optional[str] = None
    enabled: bool = True
    tool_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntegrationConnectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    provider: str
    toolkit: Optional[str] = None
    connected_account_id: Optional[str] = None
    composio_user_id: Optional[str] = None
    connection_data: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntegrationConnectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    provider: Optional[str] = None
    toolkit: Optional[str] = None
    connected_account_id: Optional[str] = None
    composio_user_id: Optional[str] = None
    connection_data: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("/mcp")
async def list_mcp_servers(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = require_prisma()
    rows = await prisma.db.litellm_mcpservertable.find_many(
        where={"account_id": account_id},
        order={"updated_at": "desc"},
    )

    items = []
    for row in rows:
        info = row.mcp_info if isinstance(row.mcp_info, dict) else {}
        if info.get("alchemi_domain") == "copilot":
            items.append(row)

    return {"items": items, "total": len(items)}


@router.post("/mcp")
async def create_mcp_server(
    body: MCPServerCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = require_prisma()
    server_id = str(uuid.uuid4())

    row = await prisma.db.litellm_mcpservertable.create(
        data={
            "server_id": server_id,
            "server_name": body.server_name,
            "alias": body.alias,
            "description": body.description,
            "transport": body.transport,
            "url": body.url,
            "command": body.command,
            "args": body.args,
            "env": body.env,
            "credentials": body.credentials,
            "mcp_access_groups": body.mcp_access_groups,
            "allowed_tools": body.allowed_tools,
            "mcp_info": mark_copilot_meta({}),
            "created_by": get_actor_email_or_id(request),
            "updated_by": get_actor_email_or_id(request),
            "account_id": account_id,
        }
    )

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.connections.mcp.create",
            "actor": get_actor_email_or_id(request),
            "data": {"server_id": server_id, "server_name": body.server_name},
        },
    )
    return {"item": row}


@router.put("/mcp/{server_id}")
async def update_mcp_server(
    server_id: str,
    body: MCPServerUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = require_prisma()
    existing = await prisma.db.litellm_mcpservertable.find_unique(where={"server_id": server_id})
    if existing is None or getattr(existing, "account_id", None) != account_id:
        raise HTTPException(status_code=404, detail="MCP server not found")

    patch = body.model_dump(exclude_none=True)
    row = await prisma.db.litellm_mcpservertable.update(
        where={"server_id": server_id},
        data={
            **patch,
            "updated_by": get_actor_email_or_id(request),
            "mcp_info": mark_copilot_meta(existing.mcp_info if isinstance(existing.mcp_info, dict) else {}),
        },
    )
    return {"item": row}


@router.delete("/mcp/{server_id}")
async def delete_mcp_server(
    server_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = require_prisma()
    existing = await prisma.db.litellm_mcpservertable.find_unique(where={"server_id": server_id})
    if existing is None or getattr(existing, "account_id", None) != account_id:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await prisma.db.litellm_mcpservertable.delete(where={"server_id": server_id})
    return {"deleted": True}


@router.get("/openapi")
async def list_openapi_connections(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("openapi-connection", account_id=account_id)
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/openapi")
async def create_openapi_connection(
    body: OpenAPIConnectionCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    connection_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    auth_config = body.auth_config or {}
    if body.auth and not auth_config:
        auth_config = body.auth
    auth_type = body.auth_type or (auth_config.get("type") if isinstance(auth_config, dict) else None)

    metadata = dict(body.metadata or {})
    if body.base_url is not None:
        metadata.setdefault("base_url", body.base_url)
    if body.default_headers:
        metadata.setdefault("default_headers", body.default_headers)
    if body.secrets:
        metadata.setdefault("secrets", body.secrets)
    if body.description_for_agent is not None:
        metadata.setdefault("description_for_agent", body.description_for_agent)
    if body.spec_text is not None:
        metadata.setdefault("spec_text", body.spec_text)

    payload = {
        "connection_id": connection_id,
        "account_id": account_id,
        **body.model_dump(),
        "auth_type": auth_type,
        "auth_config": auth_config,
        "metadata": mark_copilot_meta(metadata),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("openapi-connection", payload, account_id=account_id, object_id=connection_id)
    return {"item": payload}


@router.put("/openapi/{connection_id}")
async def update_openapi_connection(
    connection_id: str,
    body: OpenAPIConnectionUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("openapi-connection", account_id=account_id, object_id=connection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="OpenAPI connection not found")
    current = row["value"]
    patch = body.model_dump(exclude_none=True)
    auth_config = patch.get("auth_config")
    if auth_config is None and patch.get("auth") is not None:
        auth_config = patch.get("auth")
    if auth_config is None:
        auth_config = current.get("auth_config") or {}

    auth_type = patch.get("auth_type")
    if auth_type is None and isinstance(auth_config, dict):
        auth_type = auth_config.get("type")
    if auth_type is None:
        auth_type = current.get("auth_type")

    metadata = dict(current.get("metadata") or {})
    if patch.get("metadata"):
        metadata.update(patch.get("metadata") or {})
    for compat_key in ["base_url", "default_headers", "secrets", "description_for_agent", "spec_text"]:
        if compat_key in patch:
            metadata[compat_key] = patch.get(compat_key)

    payload = {
        **current,
        **patch,
        "auth_type": auth_type,
        "auth_config": auth_config,
        "metadata": mark_copilot_meta(metadata),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("openapi-connection", payload, account_id=account_id, object_id=connection_id)
    return {"item": payload}


@router.delete("/openapi/{connection_id}")
async def delete_openapi_connection(
    connection_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("openapi-connection", account_id=account_id, object_id=connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="OpenAPI connection not found")
    return {"deleted": True}


@router.get("/enablements")
async def list_tool_enablements(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("tool-enablement", account_id=account_id)
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("integration_id") or "")
    return {"items": items, "total": len(items)}


@router.put("/enablements")
async def upsert_tool_enablement(
    body: ToolEnablementUpsert,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    scope_type = body.scope_type.upper().strip()
    if scope_type not in {"ACCOUNT", "ORG", "TEAM", "USER"}:
        raise HTTPException(status_code=400, detail="Invalid scope_type")

    object_id = f"{body.integration_id}:{scope_type}:{body.scope_id or account_id}"
    payload = {
        "enablement_id": object_id,
        "account_id": account_id,
        **body.model_dump(),
        "scope_type": scope_type,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("tool-enablement", payload, account_id=account_id, object_id=object_id)
    return {"item": payload}


@router.delete("/enablements/{enablement_id}")
async def delete_tool_enablement(
    enablement_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("tool-enablement", account_id=account_id, object_id=enablement_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Enablement not found")
    return {"deleted": True}


@router.get("/integration-catalog")
async def list_integration_catalog(
    request: Request,
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("integration-catalog")
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("name") or x.get("integration_id") or "")
    return {"items": items, "total": len(items)}


@router.put("/integration-catalog/{integration_id}")
async def upsert_integration_catalog(
    integration_id: str,
    payload: Dict[str, Any],
    request: Request,
    _=Depends(require_super_admin),
):
    now = datetime.now(timezone.utc).isoformat()
    existing = await kv_get("integration-catalog", object_id=integration_id)
    row = {
        **(existing["value"] if existing else {}),
        "integration_id": integration_id,
        **payload,
        "updated_at": now,
        "updated_by": get_actor_email_or_id(request),
    }
    if existing is None:
        row["created_at"] = now
        row["created_by"] = get_actor_email_or_id(request)
    await kv_put("integration-catalog", row, object_id=integration_id)
    return {"item": row}


@router.get("/integrations")
async def list_integration_connections(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("integration-connection", account_id=account_id)
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/integrations")
async def create_integration_connection(
    body: IntegrationConnectionCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    integration_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "integration_id": integration_id,
        "account_id": account_id,
        **body.model_dump(),
        "metadata": mark_copilot_meta(body.metadata),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("integration-connection", payload, account_id=account_id, object_id=integration_id)
    return {"item": payload}


@router.put("/integrations/{integration_id}")
async def update_integration_connection(
    integration_id: str,
    body: IntegrationConnectionUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("integration-connection", account_id=account_id, object_id=integration_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    current = row["value"]
    patch = body.model_dump(exclude_none=True)
    payload = {
        **current,
        **patch,
        "metadata": mark_copilot_meta((patch.get("metadata") or current.get("metadata") or {})),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("integration-connection", payload, account_id=account_id, object_id=integration_id)
    return {"item": payload}


@router.delete("/integrations/{integration_id}")
async def delete_integration_connection(
    integration_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("integration-connection", account_id=account_id, object_id=integration_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return {"deleted": True}
