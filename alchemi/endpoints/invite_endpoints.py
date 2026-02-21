"""
User invitation management endpoints.
Create, list, revoke, and accept workspace invitations.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime, timedelta

from alchemi.auth.service_auth import require_scope, require_account_access, require_super_admin

router = APIRouter(prefix="/alchemi/invite", tags=["User Invitations"])


# -- Request Models -----------------------------------------------------------


class InviteCreateRequest(BaseModel):
    workspace_id: Optional[str] = None
    email: str
    role_id: Optional[str] = None
    expires_in_hours: Optional[int] = 72
    invitation_data: Optional[Dict[str, Any]] = None


class InviteAcceptRequest(BaseModel):
    token: str


# -- Invitation Routes --------------------------------------------------------


@router.post("/new")
async def create_invitation(
    data: InviteCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new user invitation."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    invite_id = str(uuid.uuid4())
    token = str(uuid.uuid4())
    now = datetime.utcnow()
    expires_hours = data.expires_in_hours if data.expires_in_hours else 72
    expires_at = now + timedelta(hours=expires_hours)

    create_data: Dict[str, Any] = {
        "id": invite_id,
        "account_id": account_id,
        "email": data.email,
        "status": "PENDING",
        "token": token,
        "expires_at": expires_at,
        "invitation_data": Json(data.invitation_data or {}),
    }

    if data.workspace_id is not None:
        create_data["workspace_id"] = data.workspace_id
    if data.role_id is not None:
        create_data["role_id"] = data.role_id

    invitation = await prisma_client.db.alchemi_userinvitetable.create(
        data=create_data,
    )

    return {
        "id": invitation.id,
        "email": invitation.email,
        "token": invitation.token,
        "expires_at": invitation.expires_at,
        "message": "Invitation created successfully",
    }


@router.get("/list")
async def list_invitations(
    request: Request,
    status: Optional[str] = Query(default=None, description="Filter by status"),
    workspace_id: Optional[str] = Query(default=None, description="Filter by workspace"),
    email: Optional[str] = Query(default=None, description="Filter by email"),
    _=Depends(require_account_access),
):
    """List invitations for the current account."""
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
    if workspace_id:
        where["workspace_id"] = workspace_id
    if email:
        where["email"] = email

    invitations = await prisma_client.db.alchemi_userinvitetable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"invitations": invitations}


@router.delete("/{invite_id}")
async def revoke_invitation(
    invite_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Revoke an invitation by deleting it."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_userinvitetable.find_first(
        where={"id": invite_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Invitation not found")

    await prisma_client.db.alchemi_userinvitetable.delete(
        where={"id": invite_id},
    )

    return {
        "message": "Invitation revoked",
        "id": invite_id,
    }


@router.post("/accept")
async def accept_invitation(
    data: InviteAcceptRequest,
    request: Request,
):
    """Accept an invitation using a token. No auth required."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    invitation = await prisma_client.db.alchemi_userinvitetable.find_first(
        where={"token": data.token},
    )

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.status == "ACCEPTED":
        raise HTTPException(status_code=400, detail="Invitation has already been accepted")

    now = datetime.utcnow()

    if invitation.expires_at and invitation.expires_at < now:
        raise HTTPException(status_code=400, detail="Invitation has expired")

    updated = await prisma_client.db.alchemi_userinvitetable.update(
        where={"id": invitation.id},
        data={
            "status": "ACCEPTED",
            "accepted_at": now,
        },
    )

    return {
        "id": updated.id,
        "email": updated.email,
        "account_id": updated.account_id,
        "workspace_id": updated.workspace_id,
        "role_id": updated.role_id,
        "message": "Invitation accepted successfully",
    }
