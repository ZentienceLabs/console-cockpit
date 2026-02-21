"""
Agent definition management endpoints.
CRUD for agent definitions scoped to the caller's account,
plus a bulk sync endpoint for upserting agents.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/agent-def", tags=["Agent Definitions"])


# -- Request Models -----------------------------------------------------------


class AgentCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    page: Optional[str] = None
    categories: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    builtin_tools: Optional[List[str]] = None
    tools_mcp_ids: Optional[List[str]] = None
    tools_openapi_ids: Optional[List[str]] = None
    links: Optional[Dict[str, Any]] = None
    is_singleton: Optional[bool] = False
    is_non_conversational: Optional[bool] = False
    availability: Optional[List[str]] = None
    provider: Optional[str] = "PLATFORM"


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    page: Optional[str] = None
    categories: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    builtin_tools: Optional[List[str]] = None
    tools_mcp_ids: Optional[List[str]] = None
    tools_openapi_ids: Optional[List[str]] = None
    links: Optional[Dict[str, Any]] = None
    is_singleton: Optional[bool] = None
    is_non_conversational: Optional[bool] = None
    status: Optional[str] = None
    availability: Optional[List[str]] = None
    provider: Optional[str] = None


class AgentSyncItem(BaseModel):
    agent_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    page: Optional[str] = None
    categories: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    builtin_tools: Optional[List[str]] = None
    tools_mcp_ids: Optional[List[str]] = None
    tools_openapi_ids: Optional[List[str]] = None
    links: Optional[Dict[str, Any]] = None
    is_singleton: Optional[bool] = False
    is_non_conversational: Optional[bool] = False
    availability: Optional[List[str]] = None
    provider: Optional[str] = "PLATFORM"


# -- Agent Definition Routes --------------------------------------------------


@router.post("/new")
async def create_agent_def(
    data: AgentCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new agent definition."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    agent_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "agent_id": agent_id,
        "account_id": account_id,
        "name": data.name,
        "categories": Json(data.categories or {}),
        "links": Json(data.links or {}),
        "is_singleton": data.is_singleton if data.is_singleton is not None else False,
        "is_non_conversational": data.is_non_conversational if data.is_non_conversational is not None else False,
        "provider": data.provider or "PLATFORM",
    }

    if data.description is not None:
        create_data["description"] = data.description
    if data.prompt is not None:
        create_data["prompt"] = data.prompt
    if data.page is not None:
        create_data["page"] = data.page
    if data.tags is not None:
        create_data["tags"] = data.tags
    if data.builtin_tools is not None:
        create_data["builtin_tools"] = data.builtin_tools
    if data.tools_mcp_ids is not None:
        create_data["tools_mcp_ids"] = data.tools_mcp_ids
    if data.tools_openapi_ids is not None:
        create_data["tools_openapi_ids"] = data.tools_openapi_ids
    if data.availability is not None:
        create_data["availability"] = data.availability

    agent = await prisma_client.db.alchemi_agentdeftable.create(
        data=create_data,
    )

    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "message": "Agent definition created successfully",
    }


@router.get("/list")
async def list_agent_defs(
    request: Request,
    status: Optional[str] = Query(default=None, description="Filter by status"),
    provider: Optional[str] = Query(default=None, description="Filter by provider"),
    page: Optional[str] = Query(default=None, description="Filter by page"),
    _=Depends(require_account_access),
):
    """List agent definitions for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if status:
        where["status"] = status
    if provider:
        where["provider"] = provider
    if page:
        where["page"] = page

    agents = await prisma_client.db.alchemi_agentdeftable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"agents": agents}


@router.get("/{agent_id}")
async def get_agent_def(
    agent_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get agent definition detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    agent = await prisma_client.db.alchemi_agentdeftable.find_first(
        where={"agent_id": agent_id, "account_id": account_id},
    )

    if not agent:
        raise HTTPException(status_code=404, detail="Agent definition not found")

    return agent


@router.put("/{agent_id}")
async def update_agent_def(
    agent_id: str,
    data: AgentUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update an agent definition."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_agentdeftable.find_first(
        where={"agent_id": agent_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Agent definition not found")

    update_data: Dict[str, Any] = {}

    if data.name is not None:
        update_data["name"] = data.name
    if data.description is not None:
        update_data["description"] = data.description
    if data.prompt is not None:
        update_data["prompt"] = data.prompt
    if data.page is not None:
        update_data["page"] = data.page
    if data.status is not None:
        update_data["status"] = data.status
    if data.is_singleton is not None:
        update_data["is_singleton"] = data.is_singleton
    if data.is_non_conversational is not None:
        update_data["is_non_conversational"] = data.is_non_conversational
    if data.provider is not None:
        update_data["provider"] = data.provider
    if data.categories is not None:
        update_data["categories"] = Json(data.categories)
    if data.links is not None:
        update_data["links"] = Json(data.links)
    if data.tags is not None:
        update_data["tags"] = data.tags
    if data.builtin_tools is not None:
        update_data["builtin_tools"] = data.builtin_tools
    if data.tools_mcp_ids is not None:
        update_data["tools_mcp_ids"] = data.tools_mcp_ids
    if data.tools_openapi_ids is not None:
        update_data["tools_openapi_ids"] = data.tools_openapi_ids
    if data.availability is not None:
        update_data["availability"] = data.availability

    agent = await prisma_client.db.alchemi_agentdeftable.update(
        where={"agent_id": agent_id},
        data=update_data,
    )

    return agent


@router.delete("/{agent_id}")
async def deactivate_agent_def(
    agent_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Soft-delete an agent definition by setting status to inactive."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_agentdeftable.find_first(
        where={"agent_id": agent_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Agent definition not found")

    await prisma_client.db.alchemi_agentdeftable.update(
        where={"agent_id": agent_id},
        data={"status": "inactive"},
    )

    return {
        "message": f"Agent '{existing.name}' deactivated",
        "agent_id": agent_id,
    }


@router.post("/sync")
async def sync_agent_defs(
    data: List[AgentSyncItem],
    request: Request,
    _=Depends(require_account_access),
):
    """Bulk upsert agent definitions for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    created = 0
    updated = 0

    for item in data:
        agent_id = item.agent_id or str(uuid.uuid4())

        upsert_data: Dict[str, Any] = {
            "name": item.name,
            "categories": Json(item.categories or {}),
            "links": Json(item.links or {}),
            "is_singleton": item.is_singleton if item.is_singleton is not None else False,
            "is_non_conversational": item.is_non_conversational if item.is_non_conversational is not None else False,
            "provider": item.provider or "PLATFORM",
        }

        if item.description is not None:
            upsert_data["description"] = item.description
        if item.prompt is not None:
            upsert_data["prompt"] = item.prompt
        if item.page is not None:
            upsert_data["page"] = item.page
        if item.tags is not None:
            upsert_data["tags"] = item.tags
        if item.builtin_tools is not None:
            upsert_data["builtin_tools"] = item.builtin_tools
        if item.tools_mcp_ids is not None:
            upsert_data["tools_mcp_ids"] = item.tools_mcp_ids
        if item.tools_openapi_ids is not None:
            upsert_data["tools_openapi_ids"] = item.tools_openapi_ids
        if item.availability is not None:
            upsert_data["availability"] = item.availability

        existing = await prisma_client.db.alchemi_agentdeftable.find_first(
            where={"agent_id": agent_id, "account_id": account_id},
        )

        if existing:
            await prisma_client.db.alchemi_agentdeftable.update(
                where={"agent_id": agent_id},
                data=upsert_data,
            )
            updated += 1
        else:
            upsert_data["agent_id"] = agent_id
            upsert_data["account_id"] = account_id
            await prisma_client.db.alchemi_agentdeftable.create(
                data=upsert_data,
            )
            created += 1

    return {
        "message": f"Sync complete: {created} created, {updated} updated",
        "created": created,
        "updated": updated,
    }
