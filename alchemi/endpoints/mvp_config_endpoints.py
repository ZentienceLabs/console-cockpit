"""
MVP configuration management endpoints.
CRUD for MVP configs scoped to the caller's account.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/mvp", tags=["MVP Configuration"])


# -- Request Models -----------------------------------------------------------


class MvpConfigCreateRequest(BaseModel):
    workspace_id: Optional[str] = None
    name: str
    description: str = ""
    creation_type: Optional[str] = "default"
    mvp_type: Optional[str] = "simple"
    framework: Optional[str] = "nextjs"
    commit_count: Optional[int] = 0
    connections: Optional[Dict[str, Any]] = None
    base_versions: list = []
    config: Optional[Dict[str, Any]] = None
    access_token: Optional[str] = None


class MvpConfigUpdateRequest(BaseModel):
    workspace_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    creation_type: Optional[str] = None
    mvp_type: Optional[str] = None
    framework: Optional[str] = None
    commit_count: Optional[int] = None
    connections: Optional[Dict[str, Any]] = None
    base_versions: Optional[list] = None
    config: Optional[Dict[str, Any]] = None
    access_token: Optional[str] = None


# -- MVP Config Routes --------------------------------------------------------


@router.post("/new")
async def create_mvp_config(
    data: MvpConfigCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new MVP configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    mvp_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": mvp_id,
        "account_id": account_id,
        "name": data.name,
        "description": data.description,
        "creation_type": data.creation_type or "default",
        "mvp_type": data.mvp_type or "simple",
        "framework": data.framework or "nextjs",
        "commit_count": data.commit_count or 0,
        "connections": Json(data.connections or {}),
        "base_versions": Json(data.base_versions or []),
        "config": Json(data.config or {}),
    }

    if data.workspace_id is not None:
        create_data["workspace_id"] = data.workspace_id
    if data.access_token is not None:
        create_data["access_token"] = data.access_token

    mvp = await prisma_client.db.alchemi_mvpconfigtable.create(
        data=create_data,
    )

    return {
        "id": mvp.id,
        "name": mvp.name,
        "message": "MVP config created successfully",
    }


@router.get("/list")
async def list_mvp_configs(
    request: Request,
    workspace_id: Optional[str] = Query(default=None, description="Filter by workspace"),
    _=Depends(require_account_access),
):
    """List MVP configurations for the current account."""
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

    configs = await prisma_client.db.alchemi_mvpconfigtable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"mvp_configs": configs}


@router.get("/{mvp_id}")
async def get_mvp_config(
    mvp_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get MVP configuration detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    mvp = await prisma_client.db.alchemi_mvpconfigtable.find_first(
        where={"id": mvp_id, "account_id": account_id},
    )

    if not mvp:
        raise HTTPException(status_code=404, detail="MVP config not found")

    return mvp


@router.put("/{mvp_id}")
async def update_mvp_config(
    mvp_id: str,
    data: MvpConfigUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update an MVP configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_mvpconfigtable.find_first(
        where={"id": mvp_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="MVP config not found")

    update_data: Dict[str, Any] = {}

    if data.workspace_id is not None:
        update_data["workspace_id"] = data.workspace_id
    if data.name is not None:
        update_data["name"] = data.name
    if data.description is not None:
        update_data["description"] = data.description
    if data.creation_type is not None:
        update_data["creation_type"] = data.creation_type
    if data.mvp_type is not None:
        update_data["mvp_type"] = data.mvp_type
    if data.framework is not None:
        update_data["framework"] = data.framework
    if data.commit_count is not None:
        update_data["commit_count"] = data.commit_count
    if data.access_token is not None:
        update_data["access_token"] = data.access_token
    if data.connections is not None:
        update_data["connections"] = Json(data.connections)
    if data.base_versions is not None:
        update_data["base_versions"] = Json(data.base_versions)
    if data.config is not None:
        update_data["config"] = Json(data.config)

    mvp = await prisma_client.db.alchemi_mvpconfigtable.update(
        where={"id": mvp_id},
        data=update_data,
    )

    return mvp


@router.delete("/{mvp_id}")
async def delete_mvp_config(
    mvp_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete an MVP configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_mvpconfigtable.find_first(
        where={"id": mvp_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="MVP config not found")

    await prisma_client.db.alchemi_mvpconfigtable.delete(
        where={"id": mvp_id},
    )

    return {
        "message": f"MVP config '{existing.name}' deleted",
        "id": mvp_id,
    }
