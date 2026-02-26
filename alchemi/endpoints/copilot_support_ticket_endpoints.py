"""Copilot support ticket endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import append_audit_event, kv_get, kv_list, kv_put
from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    maybe_account_id,
    require_account_admin_or_super_admin,
)
from alchemi.middleware.tenant_context import is_super_admin


router = APIRouter(prefix="/copilot/support", tags=["Copilot Support"])


class TicketCreate(BaseModel):
    subject: str
    description: str
    severity: str = "medium"
    category: str = "general"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    assignee: Optional[str] = None
    resolution: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TicketComment(BaseModel):
    comment: str


async def _list_all_tickets() -> List[Dict[str, Any]]:
    rows = await kv_list("support-ticket")
    return [r["value"] for r in rows]


@router.get("/tickets")
async def list_tickets(
    request: Request,
    account_id: Optional[str] = Depends(maybe_account_id),
    status: Optional[str] = Query(default=None),
    _=Depends(require_account_admin_or_super_admin),
):
    if account_id:
        rows = await kv_list("support-ticket", account_id=account_id)
        items = [r["value"] for r in rows]
    elif is_super_admin():
        items = await _list_all_tickets()
    else:
        raise HTTPException(status_code=400, detail="No account context found")

    if status:
        items = [i for i in items if str(i.get("status", "")).lower() == status.lower()]

    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/tickets")
async def create_ticket(
    body: TicketCreate,
    request: Request,
    account_id: Optional[str] = Depends(maybe_account_id),
    _=Depends(require_account_admin_or_super_admin),
):
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")

    ticket_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "ticket_id": ticket_id,
        "account_id": account_id,
        **body.model_dump(),
        "status": "open",
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("support-ticket", payload, account_id=account_id, object_id=ticket_id)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.support.ticket.create",
            "actor": get_actor_email_or_id(request),
            "data": {"ticket_id": ticket_id, "subject": body.subject},
        },
    )

    return {"item": payload}


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    request: Request,
    account_id: Optional[str] = Depends(maybe_account_id),
    _=Depends(require_account_admin_or_super_admin),
):
    if account_id:
        row = await kv_get("support-ticket", account_id=account_id, object_id=ticket_id)
    elif is_super_admin():
        row = await kv_get("support-ticket", object_id=ticket_id)
    else:
        row = None

    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"item": row["value"]}


@router.put("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    body: TicketUpdate,
    request: Request,
    account_id: Optional[str] = Depends(maybe_account_id),
    _=Depends(require_account_admin_or_super_admin),
):
    current_res = await get_ticket(ticket_id, request, account_id, _)
    current = current_res["item"]

    patch = body.model_dump(exclude_none=True)
    payload = {
        **current,
        **patch,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }

    actual_account_id = payload.get("account_id")
    if not actual_account_id:
        raise HTTPException(status_code=400, detail="Ticket is missing account_id")

    await kv_put("support-ticket", payload, account_id=actual_account_id, object_id=ticket_id)
    return {"item": payload}


@router.post("/tickets/{ticket_id}/comments")
async def add_ticket_comment(
    ticket_id: str,
    body: TicketComment,
    request: Request,
    account_id: Optional[str] = Depends(maybe_account_id),
    _=Depends(require_account_admin_or_super_admin),
):
    current_res = await get_ticket(ticket_id, request, account_id, _)
    current = current_res["item"]
    comments = list(current.get("comments") or [])
    comments.append(
        {
            "comment_id": str(uuid.uuid4()),
            "comment": body.comment,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": get_actor_email_or_id(request),
        }
    )
    payload = {
        **current,
        "comments": comments,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    actual_account_id = payload.get("account_id")
    await kv_put("support-ticket", payload, account_id=actual_account_id, object_id=ticket_id)
    return {"item": payload}


@router.post("/tickets/{ticket_id}/close")
async def close_ticket(
    ticket_id: str,
    request: Request,
    account_id: Optional[str] = Depends(maybe_account_id),
    _=Depends(require_account_admin_or_super_admin),
):
    return await update_ticket(
        ticket_id,
        TicketUpdate(status="closed"),
        request,
        account_id,
        _,
    )
