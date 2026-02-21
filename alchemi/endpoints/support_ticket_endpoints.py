"""
Support ticket management endpoints.
CRUD for support tickets scoped to the caller's account.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/ticket", tags=["Support Tickets"])


# -- Request Models -----------------------------------------------------------


class TicketCreateRequest(BaseModel):
    user_profile_id: Optional[str] = None
    subject: str
    description: str
    priority: Optional[str] = "MEDIUM"
    assigned_to: Optional[str] = None


class TicketUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None


# -- Support Ticket Routes ----------------------------------------------------


@router.post("/new")
async def create_ticket(
    data: TicketCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new support ticket."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    ticket_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": ticket_id,
        "account_id": account_id,
        "subject": data.subject,
        "description": data.description,
        "status": "OPEN",
        "priority": data.priority or "MEDIUM",
    }

    if data.user_profile_id is not None:
        create_data["user_profile_id"] = data.user_profile_id
    if data.assigned_to is not None:
        create_data["assigned_to"] = data.assigned_to

    ticket = await prisma_client.db.alchemi_supporttickettable.create(
        data=create_data,
    )

    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status,
        "message": "Ticket created successfully",
    }


@router.get("/list")
async def list_tickets(
    request: Request,
    status: Optional[str] = Query(default=None, description="Filter by status"),
    priority: Optional[str] = Query(default=None, description="Filter by priority"),
    _=Depends(require_account_access),
):
    """List support tickets for the current account."""
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
    if priority:
        where["priority"] = priority

    tickets = await prisma_client.db.alchemi_supporttickettable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"tickets": tickets}


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get support ticket detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    ticket = await prisma_client.db.alchemi_supporttickettable.find_first(
        where={"id": ticket_id, "account_id": account_id},
    )

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return ticket


@router.put("/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    data: TicketUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a support ticket (status, priority, assigned_to)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_supporttickettable.find_first(
        where={"id": ticket_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Ticket not found")

    update_data: Dict[str, Any] = {}

    if data.status is not None:
        update_data["status"] = data.status
    if data.priority is not None:
        update_data["priority"] = data.priority
    if data.assigned_to is not None:
        update_data["assigned_to"] = data.assigned_to

    ticket = await prisma_client.db.alchemi_supporttickettable.update(
        where={"id": ticket_id},
        data=update_data,
    )

    return ticket


@router.delete("/{ticket_id}")
async def close_ticket(
    ticket_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Close a support ticket (set status to CLOSED)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_supporttickettable.find_first(
        where={"id": ticket_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await prisma_client.db.alchemi_supporttickettable.update(
        where={"id": ticket_id},
        data={"status": "CLOSED"},
    )

    return {
        "message": f"Ticket '{existing.subject}' closed",
        "id": ticket_id,
    }
