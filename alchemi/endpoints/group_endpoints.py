"""
Group management endpoints.
CRUD for groups, scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, get_request_context

router = APIRouter(prefix="/alchemi/group", tags=["Group Management"])


# ── Request Models ───────────────────────────────────────────────────────────


class GroupCreateRequest(BaseModel):
    account_id: str
    name: str
    description: Optional[str] = None
    is_default: Optional[bool] = False
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None
    created_by: Optional[str] = None


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None
    updated_by: Optional[str] = None


# ── Group CRUD ───────────────────────────────────────────────────────────────


@router.post("/new")
async def create_group(
    data: GroupCreateRequest,
    request: Request,
    _=require_scope("groups:write"),
):
    """Create a new group for the given account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    group_id = str(uuid.uuid4())
    now = datetime.utcnow()

    context = get_request_context(request)
    created_by = data.created_by or context.get("account_id")

    group = await prisma_client.db.alchemi_grouptable.create(
        data={
            "id": group_id,
            "account_id": data.account_id,
            "name": data.name,
            "description": data.description,
            "is_default": data.is_default or False,
            "owner_id": data.owner_id,
            "contact_email": data.contact_email,
            "created_by": created_by,
            "updated_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": group.id,
        "name": group.name,
        "account_id": group.account_id,
        "is_default": group.is_default,
        "message": "Group created successfully",
    }


@router.get("/list")
async def list_groups(
    request: Request,
    account_id: str = Query(..., description="Account ID to list groups for"),
    is_default: Optional[bool] = Query(default=None, description="Filter by default status"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    _=require_scope("groups:read"),
):
    """List groups for the given account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    where: Dict[str, Any] = {"account_id": account_id}
    if is_default is not None:
        where["is_default"] = is_default

    groups = await prisma_client.db.alchemi_grouptable.find_many(
        where=where,
        order={"created_at": "desc"},
        take=limit,
        skip=offset,
    )

    return {"groups": groups}


@router.get("/default")
async def get_default_group(
    request: Request,
    account_id: str = Query(..., description="Account ID to get default group for"),
    _=require_scope("groups:read"),
):
    """Get the default group for the given account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    group = await prisma_client.db.alchemi_grouptable.find_first(
        where={"account_id": account_id, "is_default": True},
    )

    if not group:
        raise HTTPException(status_code=404, detail="No default group found for this account")

    return group


@router.get("/count")
async def get_group_count(
    request: Request,
    account_id: str = Query(..., description="Account ID to count groups for"),
    _=require_scope("groups:read"),
):
    """Get the total number of groups for the given account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    count = await prisma_client.db.alchemi_grouptable.count(
        where={"account_id": account_id},
    )

    return {"account_id": account_id, "count": count}


@router.get("/{group_id}")
async def get_group(
    group_id: str,
    request: Request,
    _=require_scope("groups:read"),
):
    """Get a group by its ID."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    group = await prisma_client.db.alchemi_grouptable.find_first(
        where={"id": group_id},
    )

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    return group


@router.put("/{group_id}")
async def update_group(
    group_id: str,
    data: GroupUpdateRequest,
    request: Request,
    _=require_scope("groups:write"),
):
    """Update a group."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_grouptable.find_first(
        where={"id": group_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Group not found")

    context = get_request_context(request)
    updated_by = data.updated_by or context.get("account_id")

    update_data: Dict[str, Any] = {"updated_by": updated_by, "updated_at": datetime.utcnow()}

    if data.name is not None:
        update_data["name"] = data.name
    if data.description is not None:
        update_data["description"] = data.description
    if data.owner_id is not None:
        update_data["owner_id"] = data.owner_id
    if data.contact_email is not None:
        update_data["contact_email"] = data.contact_email

    group = await prisma_client.db.alchemi_grouptable.update(
        where={"id": group_id},
        data=update_data,
    )

    return group


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    request: Request,
    _=require_scope("groups:write"),
):
    """Delete a group."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_grouptable.find_first(
        where={"id": group_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Group not found")

    await prisma_client.db.alchemi_grouptable.delete(
        where={"id": group_id},
    )

    return {
        "message": f"Group '{existing.name}' deleted",
        "id": group_id,
    }
