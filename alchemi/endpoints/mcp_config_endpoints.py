"""
MCP configuration management endpoints.
CRUD for MCP server configs scoped to the caller's account.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/mcp-config", tags=["MCP Configuration"])


# -- Request Models -----------------------------------------------------------


class McpConfigCreateRequest(BaseModel):
    workspace_id: Optional[str] = None
    name: str
    server_name: str
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = True
    mvp_version_id: Optional[str] = None


class McpConfigUpdateRequest(BaseModel):
    workspace_id: Optional[str] = None
    name: Optional[str] = None
    server_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    mvp_version_id: Optional[str] = None


# -- MCP Config Routes --------------------------------------------------------


@router.post("/new")
async def create_mcp_config(
    data: McpConfigCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new MCP configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    config_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": config_id,
        "account_id": account_id,
        "name": data.name,
        "server_name": data.server_name,
        "config": Json(data.config or {}),
        "is_active": data.is_active if data.is_active is not None else True,
    }

    if data.workspace_id is not None:
        create_data["workspace_id"] = data.workspace_id
    if data.mvp_version_id is not None:
        create_data["mvp_version_id"] = data.mvp_version_id

    mcp_config = await prisma_client.db.alchemi_mcpconfigtable.create(
        data=create_data,
    )

    return {
        "id": mcp_config.id,
        "name": mcp_config.name,
        "message": "MCP config created successfully",
    }


@router.get("/list")
async def list_mcp_configs(
    request: Request,
    workspace_id: Optional[str] = Query(default=None, description="Filter by workspace"),
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    server_name: Optional[str] = Query(default=None, description="Filter by server name"),
    _=Depends(require_account_access),
):
    """List MCP configurations for the current account."""
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
    if is_active is not None:
        where["is_active"] = is_active
    if server_name:
        where["server_name"] = server_name

    configs = await prisma_client.db.alchemi_mcpconfigtable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"mcp_configs": configs}


@router.get("/{config_id}")
async def get_mcp_config(
    config_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get MCP configuration detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    mcp_config = await prisma_client.db.alchemi_mcpconfigtable.find_first(
        where={"id": config_id, "account_id": account_id},
    )

    if not mcp_config:
        raise HTTPException(status_code=404, detail="MCP config not found")

    return mcp_config


@router.put("/{config_id}")
async def update_mcp_config(
    config_id: str,
    data: McpConfigUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update an MCP configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_mcpconfigtable.find_first(
        where={"id": config_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="MCP config not found")

    update_data: Dict[str, Any] = {}

    if data.workspace_id is not None:
        update_data["workspace_id"] = data.workspace_id
    if data.name is not None:
        update_data["name"] = data.name
    if data.server_name is not None:
        update_data["server_name"] = data.server_name
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.mvp_version_id is not None:
        update_data["mvp_version_id"] = data.mvp_version_id
    if data.config is not None:
        update_data["config"] = Json(data.config)

    mcp_config = await prisma_client.db.alchemi_mcpconfigtable.update(
        where={"id": config_id},
        data=update_data,
    )

    return mcp_config


@router.delete("/{config_id}")
async def delete_mcp_config(
    config_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete an MCP configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_mcpconfigtable.find_first(
        where={"id": config_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="MCP config not found")

    await prisma_client.db.alchemi_mcpconfigtable.delete(
        where={"id": config_id},
    )

    return {
        "message": f"MCP config '{existing.name}' deleted",
        "id": config_id,
    }
