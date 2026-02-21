"""
Account connection management endpoints.
CRUD for account-level connections (MCP, OpenAPI, integrations, etc.),
scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, get_request_context

router = APIRouter(prefix="/alchemi/account-connection", tags=["Account Connections"])


# ── Request Models ───────────────────────────────────────────────────────────


class AccountConnectionCreateRequest(BaseModel):
    account_id: str
    connection_type: str
    name: str
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    connection_data: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = True
    is_default: Optional[bool] = False
    metadata: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None


class AccountConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    description_for_agent: Optional[str] = None
    connection_data: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    updated_by: Optional[str] = None


# ── Account Connection CRUD ──────────────────────────────────────────────────


@router.post("/new")
async def create_account_connection(
    data: AccountConnectionCreateRequest,
    request: Request,
    _=require_scope("connections:write"),
):
    """Create a new account connection."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Check for duplicate account_id + name
    existing = await prisma_client.db.alchemi_accountconnectiontable.find_first(
        where={
            "account_id": data.account_id,
            "name": data.name,
        },
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Connection with name '{data.name}' already exists for this account",
        )

    now = datetime.utcnow()
    connection = await prisma_client.db.alchemi_accountconnectiontable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": data.account_id,
            "connection_type": data.connection_type,
            "name": data.name,
            "description": data.description,
            "description_for_agent": data.description_for_agent,
            "connection_data": Json(data.connection_data or {}),
            "is_active": data.is_active if data.is_active is not None else True,
            "is_default": data.is_default if data.is_default is not None else False,
            "metadata": Json(data.metadata or {}),
            "created_by": data.created_by,
            "updated_by": data.created_by,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": connection.id,
        "name": connection.name,
        "connection_type": connection.connection_type,
        "message": "Account connection created successfully",
    }


@router.get("/list")
async def list_account_connections(
    request: Request,
    account_id: str = Query(..., description="Account ID to list connections for"),
    connection_type: Optional[str] = Query(None, description="Filter by connection type (mcp, openapi, integration)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    name: Optional[str] = Query(None, description="Filter by connection name"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    _=require_scope("connections:read"),
):
    """List account connections with optional filters."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    where: Dict[str, Any] = {"account_id": account_id}
    if connection_type:
        where["connection_type"] = connection_type
    if is_active is not None:
        where["is_active"] = is_active
    if name:
        where["name"] = name

    connections = await prisma_client.db.alchemi_accountconnectiontable.find_many(
        where=where,
        order={"created_at": "desc"},
        take=limit,
        skip=offset,
    )

    total = await prisma_client.db.alchemi_accountconnectiontable.count(
        where=where,
    )

    return {
        "connections": connections,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{connection_id}")
async def get_account_connection(
    connection_id: str,
    request: Request,
    _=require_scope("connections:read"),
):
    """Get account connection detail by ID."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    connection = await prisma_client.db.alchemi_accountconnectiontable.find_first(
        where={"id": connection_id, "account_id": account_id},
    )

    if not connection:
        raise HTTPException(status_code=404, detail="Account connection not found")

    return connection


@router.put("/{connection_id}")
async def update_account_connection(
    connection_id: str,
    data: AccountConnectionUpdateRequest,
    request: Request,
    _=require_scope("connections:write"),
):
    """Update an account connection."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accountconnectiontable.find_first(
        where={"id": connection_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Account connection not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.name is not None:
        update_data["name"] = data.name
    if data.description is not None:
        update_data["description"] = data.description
    if data.description_for_agent is not None:
        update_data["description_for_agent"] = data.description_for_agent
    if data.connection_data is not None:
        update_data["connection_data"] = Json(data.connection_data)
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.is_default is not None:
        update_data["is_default"] = data.is_default
    if data.metadata is not None:
        update_data["metadata"] = Json(data.metadata)
    if data.updated_by is not None:
        update_data["updated_by"] = data.updated_by

    connection = await prisma_client.db.alchemi_accountconnectiontable.update(
        where={"id": connection_id},
        data=update_data,
    )

    return connection


@router.delete("/{connection_id}")
async def delete_account_connection(
    connection_id: str,
    request: Request,
    _=require_scope("connections:write"),
):
    """Delete an account connection."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accountconnectiontable.find_first(
        where={"id": connection_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Account connection not found")

    await prisma_client.db.alchemi_accountconnectiontable.delete(
        where={"id": connection_id},
    )

    return {
        "message": f"Account connection '{existing.name}' deleted",
        "id": connection_id,
    }
