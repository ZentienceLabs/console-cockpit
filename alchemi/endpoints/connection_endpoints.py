"""
Connection and integration management endpoints.
CRUD for connections, integration connections, and integration definitions,
scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/connection", tags=["Connections"])


# ── Request Models ───────────────────────────────────────────────────────────


class ConnectionCreateRequest(BaseModel):
    workspace_id: Optional[str] = None
    name: str
    type: str
    status: Optional[str] = "ACTIVE"
    config: Optional[Dict[str, Any]] = None
    mvp_version_id: Optional[str] = None


class ConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    mvp_version_id: Optional[str] = None


class IntegrationCreateRequest(BaseModel):
    workspace_id: str
    user_id: Optional[str] = None
    connection_level: Optional[str] = "WORKSPACE"
    name: str
    description_for_agent: Optional[str] = None
    integration_type: str
    app_name: str
    composio_entity_id: str
    composio_connected_account_id: Optional[str] = None
    status: Optional[str] = "active"
    connected_by_user_id: str


# ── Connection CRUD ──────────────────────────────────────────────────────────


@router.post("/new")
async def create_connection(
    data: ConnectionCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new connection for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()
    connection = await prisma_client.db.alchemi_connectiontable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "workspace_id": data.workspace_id,
            "name": data.name,
            "type": data.type,
            "status": data.status or "ACTIVE",
            "config": Json(data.config or {}),
            "mvp_version_id": data.mvp_version_id,
            "created_by": account_id,
            "updated_by": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": connection.id,
        "name": connection.name,
        "message": "Connection created successfully",
    }


@router.get("/list")
async def list_connections(
    request: Request,
    workspace_id: Optional[str] = Query(None, description="Filter by workspace"),
    type: Optional[str] = Query(None, description="Filter by connection type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    _=Depends(require_account_access),
):
    """List connections for the current account with optional filters."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if workspace_id:
        where["workspace_id"] = workspace_id
    if type:
        where["type"] = type
    if status:
        where["status"] = status

    connections = await prisma_client.db.alchemi_connectiontable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"connections": connections}


@router.get("/{connection_id}")
async def get_connection(
    connection_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get connection detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    connection = await prisma_client.db.alchemi_connectiontable.find_first(
        where={"id": connection_id, "account_id": account_id},
    )

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    return connection


@router.put("/{connection_id}")
async def update_connection(
    connection_id: str,
    data: ConnectionUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a connection."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_connectiontable.find_first(
        where={"id": connection_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Connection not found")

    update_data: Dict[str, Any] = {"updated_by": account_id, "updated_at": datetime.utcnow()}

    if data.name is not None:
        update_data["name"] = data.name
    if data.type is not None:
        update_data["type"] = data.type
    if data.status is not None:
        update_data["status"] = data.status
    if data.config is not None:
        update_data["config"] = Json(data.config)
    if data.mvp_version_id is not None:
        update_data["mvp_version_id"] = data.mvp_version_id

    connection = await prisma_client.db.alchemi_connectiontable.update(
        where={"id": connection_id},
        data=update_data,
    )

    return connection


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete a connection."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_connectiontable.find_first(
        where={"id": connection_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Connection not found")

    await prisma_client.db.alchemi_connectiontable.delete(
        where={"id": connection_id},
    )

    return {
        "message": f"Connection '{existing.name}' deleted",
        "id": connection_id,
    }


# ── Integration Connection Management ────────────────────────────────────────


@router.post("/integration/new")
async def create_integration(
    data: IntegrationCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new integration connection."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Check for duplicate workspace_id + app_name + user_id
    existing = await prisma_client.db.alchemi_integrationconnectiontable.find_first(
        where={
            "workspace_id": data.workspace_id,
            "app_name": data.app_name,
            "user_id": data.user_id,
        },
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Integration for '{data.app_name}' already exists in this workspace",
        )

    now = datetime.utcnow()
    integration = await prisma_client.db.alchemi_integrationconnectiontable.create(
        data={
            "id": str(uuid.uuid4()),
            "workspace_id": data.workspace_id,
            "user_id": data.user_id,
            "connection_level": data.connection_level or "WORKSPACE",
            "name": data.name,
            "description_for_agent": data.description_for_agent,
            "integration_type": data.integration_type,
            "app_name": data.app_name,
            "composio_entity_id": data.composio_entity_id,
            "composio_connected_account_id": data.composio_connected_account_id,
            "status": data.status or "active",
            "connected_at": now,
            "connected_by_user_id": data.connected_by_user_id,
            "account_id": account_id,
            "updated_at": now,
        }
    )

    return {
        "id": integration.id,
        "name": integration.name,
        "app_name": integration.app_name,
        "message": "Integration created successfully",
    }


@router.get("/integration/list")
async def list_integrations(
    request: Request,
    workspace_id: Optional[str] = Query(None, description="Filter by workspace"),
    _=Depends(require_account_access),
):
    """List integration connections for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if workspace_id:
        where["workspace_id"] = workspace_id

    integrations = await prisma_client.db.alchemi_integrationconnectiontable.find_many(
        where=where,
        order={"connected_at": "desc"},
    )

    return {"integrations": integrations}


@router.delete("/integration/{integration_id}")
async def delete_integration(
    integration_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete an integration connection."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_integrationconnectiontable.find_first(
        where={"id": integration_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")

    await prisma_client.db.alchemi_integrationconnectiontable.delete(
        where={"id": integration_id},
    )

    return {
        "message": f"Integration '{existing.name}' deleted",
        "id": integration_id,
    }


# ── Integration Definitions (global read-only) ──────────────────────────────


@router.get("/integration-def/list")
async def list_integration_definitions(
    request: Request,
    toolkit: Optional[str] = Query(None, description="Filter by toolkit"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    _=Depends(require_account_access),
):
    """List integration definitions (global, no account filter)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    where: Dict[str, Any] = {}
    if toolkit:
        where["toolkit"] = toolkit
    if enabled is not None:
        where["enabled"] = enabled

    definitions = await prisma_client.db.alchemi_integrationsdeftable.find_many(
        where=where,
        order={"display_order": "asc"},
    )

    return {"definitions": definitions}
