"""
Account membership management endpoints.
CRUD for account memberships scoped to the caller's account.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/membership", tags=["Account Membership"])


# -- Request Models -----------------------------------------------------------


class MembershipCreateRequest(BaseModel):
    user_id: str
    app_role: Optional[str] = "member"
    team_id: Optional[str] = None
    invited_by: Optional[str] = None
    tenant_preferences: Optional[Dict[str, Any]] = None


class MembershipUpdateRequest(BaseModel):
    app_role: Optional[str] = None
    is_active: Optional[bool] = None
    team_id: Optional[str] = None
    tenant_preferences: Optional[Dict[str, Any]] = None


# -- Membership Routes --------------------------------------------------------


@router.post("/new")
async def create_membership(
    data: MembershipCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Add a member to the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Check for existing membership
    existing = await prisma_client.db.alchemi_accountmembershiptable.find_first(
        where={"account_id": account_id, "user_id": data.user_id},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"User '{data.user_id}' is already a member of this account",
        )

    membership_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": membership_id,
        "account_id": account_id,
        "user_id": data.user_id,
        "app_role": data.app_role or "member",
        "is_active": True,
    }

    if data.team_id is not None:
        create_data["team_id"] = data.team_id
    if data.invited_by is not None:
        create_data["invited_by"] = data.invited_by
    if data.tenant_preferences is not None:
        create_data["tenant_preferences"] = Json(data.tenant_preferences)

    membership = await prisma_client.db.alchemi_accountmembershiptable.create(
        data=create_data,
    )

    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "app_role": membership.app_role,
        "message": "Membership created successfully",
    }


@router.get("/list")
async def list_memberships(
    request: Request,
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    app_role: Optional[str] = Query(default=None, description="Filter by role"),
    _=Depends(require_account_access),
):
    """List all memberships for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if is_active is not None:
        where["is_active"] = is_active
    if app_role:
        where["app_role"] = app_role

    memberships = await prisma_client.db.alchemi_accountmembershiptable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"memberships": memberships}


@router.get("/user/{user_id}")
async def get_membership_by_user(
    user_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get membership for a specific user in the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    membership = await prisma_client.db.alchemi_accountmembershiptable.find_first(
        where={"account_id": account_id, "user_id": user_id},
    )

    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    return membership


@router.get("/{membership_id}")
async def get_membership(
    membership_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get membership detail by ID."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    membership = await prisma_client.db.alchemi_accountmembershiptable.find_first(
        where={"id": membership_id, "account_id": account_id},
    )

    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")

    return membership


@router.put("/{membership_id}")
async def update_membership(
    membership_id: str,
    data: MembershipUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a membership (role, active status, team, preferences)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accountmembershiptable.find_first(
        where={"id": membership_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Membership not found")

    update_data: Dict[str, Any] = {}

    if data.app_role is not None:
        update_data["app_role"] = data.app_role
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.team_id is not None:
        update_data["team_id"] = data.team_id
    if data.tenant_preferences is not None:
        update_data["tenant_preferences"] = Json(data.tenant_preferences)

    membership = await prisma_client.db.alchemi_accountmembershiptable.update(
        where={"id": membership_id},
        data=update_data,
    )

    return membership


@router.delete("/{membership_id}")
async def remove_membership(
    membership_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Remove a membership (soft-delete by setting is_active=False)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accountmembershiptable.find_first(
        where={"id": membership_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Membership not found")

    await prisma_client.db.alchemi_accountmembershiptable.update(
        where={"id": membership_id},
        data={"is_active": False},
    )

    return {
        "message": f"Membership for user '{existing.user_id}' deactivated",
        "id": membership_id,
    }
