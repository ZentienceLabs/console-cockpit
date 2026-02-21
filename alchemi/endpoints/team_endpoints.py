"""
Team management endpoints.
CRUD for teams, scoped via group_id (and optionally account_id through groups).
"""
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, get_request_context

router = APIRouter(prefix="/alchemi/team", tags=["Team Management"])


# ── Request Models ───────────────────────────────────────────────────────────


class TeamCreateRequest(BaseModel):
    group_id: str
    name: str
    description: Optional[str] = None
    is_default: Optional[bool] = False
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None
    created_by: Optional[str] = None


class TeamUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    contact_email: Optional[str] = None
    updated_by: Optional[str] = None


# ── Team CRUD ────────────────────────────────────────────────────────────────


@router.post("/new")
async def create_team(
    data: TeamCreateRequest,
    request: Request,
    _=require_scope("teams:write"),
):
    """Create a new team for the given group."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    context = get_request_context(request)
    created_by = data.created_by or context.get("account_id")

    team_id = str(uuid.uuid4())
    now = datetime.utcnow()

    team = await prisma_client.db.alchemi_teamtable.create(
        data={
            "id": team_id,
            "group_id": data.group_id,
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
        "id": team.id,
        "name": team.name,
        "group_id": team.group_id,
        "is_default": team.is_default,
        "message": "Team created successfully",
    }


@router.get("/list")
async def list_teams(
    request: Request,
    group_id: Optional[str] = Query(default=None, description="Filter by group ID"),
    account_id: Optional[str] = Query(default=None, description="Filter by account ID (joins through groups)"),
    is_default: Optional[bool] = Query(default=None, description="Filter by default status"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    _=require_scope("teams:read"),
):
    """List teams, optionally filtered by group or account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # When account_id is provided, find teams through groups belonging to that account
    if account_id and not group_id:
        groups = await prisma_client.db.alchemi_grouptable.find_many(
            where={"account_id": account_id},
        )
        group_ids = [g.id for g in groups]

        if not group_ids:
            return {"teams": []}

        where: Dict[str, Any] = {"group_id": {"in": group_ids}}
        if is_default is not None:
            where["is_default"] = is_default

        teams = await prisma_client.db.alchemi_teamtable.find_many(
            where=where,
            order={"created_at": "desc"},
            take=limit,
            skip=offset,
        )

        return {"teams": teams}

    # Direct group_id filter
    where = {}
    if group_id:
        where["group_id"] = group_id
    if is_default is not None:
        where["is_default"] = is_default

    teams = await prisma_client.db.alchemi_teamtable.find_many(
        where=where,
        order={"created_at": "desc"},
        take=limit,
        skip=offset,
    )

    return {"teams": teams}


@router.get("/default")
async def get_default_team(
    request: Request,
    group_id: str = Query(..., description="Group ID to get default team for"),
    _=require_scope("teams:read"),
):
    """Get the default team for the given group."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    team = await prisma_client.db.alchemi_teamtable.find_first(
        where={"group_id": group_id, "is_default": True},
    )

    if not team:
        raise HTTPException(status_code=404, detail="No default team found for this group")

    return team


@router.get("/{team_id}")
async def get_team(
    team_id: str,
    request: Request,
    _=require_scope("teams:read"),
):
    """Get a team by its ID."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    team = await prisma_client.db.alchemi_teamtable.find_first(
        where={"id": team_id},
    )

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    return team


@router.put("/{team_id}")
async def update_team(
    team_id: str,
    data: TeamUpdateRequest,
    request: Request,
    _=require_scope("teams:write"),
):
    """Update a team."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_teamtable.find_first(
        where={"id": team_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")

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

    team = await prisma_client.db.alchemi_teamtable.update(
        where={"id": team_id},
        data=update_data,
    )

    return team


@router.delete("/{team_id}")
async def delete_team(
    team_id: str,
    request: Request,
    _=require_scope("teams:write"),
):
    """Delete a team."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_teamtable.find_first(
        where={"id": team_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Team not found")

    await prisma_client.db.alchemi_teamtable.delete(
        where={"id": team_id},
    )

    return {
        "message": f"Team '{existing.name}' deleted",
        "id": team_id,
    }
