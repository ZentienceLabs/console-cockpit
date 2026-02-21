"""
Agent group management endpoints.
CRUD for agent groups and group member assignments,
scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/agent-group", tags=["Agent Groups"])


# -- Request Models -----------------------------------------------------------


class GroupCreateRequest(BaseModel):
    group_code: str
    name: str
    description: Optional[str] = None
    group_type: str
    metadata: Optional[Dict[str, Any]] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    group_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class GroupMemberRequest(BaseModel):
    agent_id: str
    display_order: Optional[int] = 0
    metadata: Optional[Dict[str, Any]] = None


# -- Agent Group Routes -------------------------------------------------------


@router.post("/new")
async def create_agent_group(
    data: GroupCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new agent group."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    group_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": group_id,
        "account_id": account_id,
        "group_code": data.group_code,
        "name": data.name,
        "group_type": data.group_type,
        "metadata": Json(data.metadata or {}),
    }

    if data.description is not None:
        create_data["description"] = data.description

    group = await prisma_client.db.alchemi_agentgrouptable.create(
        data=create_data,
    )

    return {
        "id": group.id,
        "group_code": group.group_code,
        "name": group.name,
        "message": "Agent group created successfully",
    }


@router.get("/list")
async def list_agent_groups(
    request: Request,
    group_type: Optional[str] = Query(default=None, description="Filter by group type"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    _=Depends(require_account_access),
):
    """List agent groups for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if group_type:
        where["group_type"] = group_type
    if status:
        where["status"] = status

    groups = await prisma_client.db.alchemi_agentgrouptable.find_many(
        where=where,
        include={"members": True},
        order={"created_at": "desc"},
    )

    result = []
    for group in groups:
        group_dict = {
            "id": group.id,
            "group_code": group.group_code,
            "name": group.name,
            "description": group.description,
            "group_type": group.group_type,
            "metadata": group.metadata,
            "status": group.status,
            "account_id": group.account_id,
            "created_at": group.created_at,
            "updated_at": group.updated_at,
            "member_count": len(group.members) if group.members else 0,
        }
        result.append(group_dict)

    return {"groups": result}


@router.put("/{group_id}")
async def update_agent_group(
    group_id: str,
    data: GroupUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update an agent group."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_agentgrouptable.find_first(
        where={"id": group_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Agent group not found")

    update_data: Dict[str, Any] = {}

    if data.name is not None:
        update_data["name"] = data.name
    if data.description is not None:
        update_data["description"] = data.description
    if data.group_type is not None:
        update_data["group_type"] = data.group_type
    if data.status is not None:
        update_data["status"] = data.status
    if data.metadata is not None:
        update_data["metadata"] = Json(data.metadata)

    group = await prisma_client.db.alchemi_agentgrouptable.update(
        where={"id": group_id},
        data=update_data,
    )

    return group


@router.delete("/{group_id}")
async def delete_agent_group(
    group_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete an agent group and its member associations."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_agentgrouptable.find_first(
        where={"id": group_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Agent group not found")

    await prisma_client.db.alchemi_agentgrouptable.delete(
        where={"id": group_id},
    )

    return {
        "message": f"Agent group '{existing.name}' deleted",
        "id": group_id,
    }


# -- Agent Group Member Management -------------------------------------------


@router.post("/{group_id}/member")
async def add_group_member(
    group_id: str,
    data: GroupMemberRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Add an agent to a group."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify group belongs to this account
    group = await prisma_client.db.alchemi_agentgrouptable.find_first(
        where={"id": group_id, "account_id": account_id},
    )
    if not group:
        raise HTTPException(status_code=404, detail="Agent group not found")

    # Check for duplicate membership
    existing_member = await prisma_client.db.alchemi_agentgroupmembertable.find_first(
        where={"group_id": group_id, "agent_id": data.agent_id},
    )
    if existing_member:
        raise HTTPException(
            status_code=400,
            detail="Agent is already a member of this group",
        )

    member = await prisma_client.db.alchemi_agentgroupmembertable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "group_id": group_id,
            "agent_id": data.agent_id,
            "display_order": data.display_order if data.display_order is not None else 0,
            "metadata": Json(data.metadata or {}),
        },
    )

    return {
        "id": member.id,
        "group_id": member.group_id,
        "agent_id": member.agent_id,
        "message": "Agent added to group successfully",
    }


@router.delete("/{group_id}/member/{agent_id}")
async def remove_group_member(
    group_id: str,
    agent_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Remove an agent from a group."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify membership exists and belongs to this account
    existing = await prisma_client.db.alchemi_agentgroupmembertable.find_first(
        where={
            "group_id": group_id,
            "agent_id": agent_id,
            "account_id": account_id,
        },
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Group membership not found")

    await prisma_client.db.alchemi_agentgroupmembertable.delete(
        where={"id": existing.id},
    )

    return {
        "message": "Agent removed from group",
        "group_id": group_id,
        "agent_id": agent_id,
    }
