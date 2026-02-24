"""
Support ticket management endpoints for copilot cockpit features.
"""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_auth import (
    require_copilot_admin_access,
    require_copilot_read_access,
)
from alchemi.endpoints.copilot_types import (
    SupportTicketBulkUpdate,
    SupportTicketCreate,
    SupportTicketPriority,
    SupportTicketStatus,
    SupportTicketUpdate,
)
from alchemi.middleware.account_middleware import (
    _get_master_key,
    decode_jwt_token,
    extract_token_from_request,
)
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

router = APIRouter(
    prefix="/copilot/support-tickets",
    tags=["Copilot - Support Tickets"],
)


def _model_dump(data: Any) -> Dict[str, Any]:
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)


def _user_id_from_request(request: Request) -> Optional[str]:
    token = extract_token_from_request(request)
    if not token:
        return None
    decoded = decode_jwt_token(token, _get_master_key())
    if not decoded:
        return None
    user_id = decoded.get("user_id")
    if user_id is None:
        return None
    return str(user_id)


def _resolve_account_filter(account_id: Optional[str]) -> Optional[str]:
    if is_super_admin():
        if account_id:
            return account_id
        return get_current_account_id()

    resolved = get_current_account_id()
    if not resolved:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return resolved


def _resolve_required_account_for_write(account_id: Optional[str]) -> str:
    resolved = _resolve_account_filter(account_id)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for this super admin write operation.",
        )
    return resolved


def _build_ticket_where(
    resolved_account: Optional[str],
    ticket_id: Optional[str] = None,
    user_profile_id: Optional[str] = None,
    status: Optional[SupportTicketStatus] = None,
    priority: Optional[SupportTicketPriority] = None,
    assigned_to: Optional[str] = None,
    search_text: Optional[str] = None,
) -> Tuple[List[str], List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if resolved_account:
        params.append(resolved_account)
        clauses.append(f"st.account_id = ${len(params)}")

    if ticket_id:
        params.append(ticket_id)
        clauses.append(f"st.id = ${len(params)}")

    if user_profile_id:
        params.append(user_profile_id)
        clauses.append(f"st.user_profile_id = ${len(params)}")

    if status:
        params.append(status.value)
        clauses.append(f"st.status = ${len(params)}")

    if priority:
        params.append(priority.value)
        clauses.append(f"st.priority = ${len(params)}")

    if assigned_to is not None:
        if str(assigned_to).strip().lower() == "null":
            clauses.append("st.assigned_to IS NULL")
        else:
            params.append(assigned_to)
            clauses.append(f"st.assigned_to = ${len(params)}")

    if search_text:
        query = f"%{search_text.strip()}%"
        params.append(query)
        clauses.append(
            f"(st.subject ILIKE ${len(params)} OR st.description ILIKE ${len(params)})"
        )

    return clauses, params


def _hydrate_ticket_row(
    row: Dict[str, Any],
    include_user_profile: bool,
    include_assigned_to: bool,
) -> Dict[str, Any]:
    ticket: Dict[str, Any] = {
        "id": row.get("id"),
        "account_id": row.get("account_id"),
        "user_profile_id": row.get("user_profile_id"),
        "subject": row.get("subject"),
        "description": row.get("description"),
        "status": row.get("status"),
        "priority": row.get("priority"),
        "assigned_to": row.get("assigned_to"),
        "created_by": row.get("created_by"),
        "updated_by": row.get("updated_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }

    if include_user_profile and row.get("profile_user_id"):
        ticket["userProfile"] = {
            "id": row.get("profile_user_id"),
            "displayName": row.get("profile_user_name"),
            "name": row.get("profile_user_name"),
            "email": row.get("profile_user_email"),
            "profile_image": row.get("profile_user_profile_image"),
            "is_active": row.get("profile_user_is_active"),
        }

    if include_assigned_to and row.get("assigned_user_id"):
        ticket["assignedTo"] = {
            "id": row.get("assigned_user_id"),
            "displayName": row.get("assigned_user_name"),
            "name": row.get("assigned_user_name"),
            "email": row.get("assigned_user_email"),
            "profile_image": row.get("assigned_user_profile_image"),
            "is_active": row.get("assigned_user_is_active"),
        }

    return ticket


async def _query_tickets(
    resolved_account: Optional[str],
    ticket_id: Optional[str] = None,
    user_profile_id: Optional[str] = None,
    status: Optional[SupportTicketStatus] = None,
    priority: Optional[SupportTicketPriority] = None,
    assigned_to: Optional[str] = None,
    search_text: Optional[str] = None,
    include_user_profile: bool = False,
    include_assigned_to: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    clauses, params = _build_ticket_where(
        resolved_account=resolved_account,
        ticket_id=ticket_id,
        user_profile_id=user_profile_id,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        search_text=search_text,
    )

    select_fields = ["st.*"]
    joins: List[str] = []

    if include_user_profile:
        joins.append("LEFT JOIN copilot.users pu ON pu.id::text = st.user_profile_id")
        select_fields.extend(
            [
                "pu.id::text AS profile_user_id",
                "pu.name AS profile_user_name",
                "pu.email AS profile_user_email",
                "pu.profile_image AS profile_user_profile_image",
                "pu.is_active AS profile_user_is_active",
            ]
        )

    if include_assigned_to:
        joins.append("LEFT JOIN copilot.users au ON au.id::text = st.assigned_to")
        select_fields.extend(
            [
                "au.id::text AS assigned_user_id",
                "au.name AS assigned_user_name",
                "au.email AS assigned_user_email",
                "au.profile_image AS assigned_user_profile_image",
                "au.is_active AS assigned_user_is_active",
            ]
        )

    sql = f"SELECT {', '.join(select_fields)} FROM copilot.support_tickets st"
    if joins:
        sql += " " + " ".join(joins)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY st.created_at DESC"

    page_params = list(params)
    page_params.append(limit)
    sql += f" LIMIT ${len(page_params)}"
    page_params.append(offset)
    sql += f" OFFSET ${len(page_params)}"

    rows = await copilot_db.support_tickets.execute_raw(sql, *page_params)
    tickets = [
        _hydrate_ticket_row(
            row,
            include_user_profile=include_user_profile,
            include_assigned_to=include_assigned_to,
        )
        for row in rows
    ]

    count_sql = "SELECT COUNT(*) FROM copilot.support_tickets st"
    if clauses:
        count_sql += " WHERE " + " AND ".join(clauses)

    total_val = await copilot_db.support_tickets.execute_raw_val(count_sql, *params)
    total = int(total_val or 0)

    return tickets, total


@router.get("/")
async def list_support_tickets(
    request: Request,
    account_id: Optional[str] = None,
    user_profile_id: Optional[str] = None,
    status: Optional[SupportTicketStatus] = None,
    priority: Optional[SupportTicketPriority] = None,
    assigned_to: Optional[str] = None,
    search_text: Optional[str] = None,
    include_user_profile: bool = False,
    include_assigned_to: bool = False,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    """List support tickets for the current account."""
    resolved_account = _resolve_account_filter(account_id)
    tickets, total = await _query_tickets(
        resolved_account=resolved_account,
        user_profile_id=user_profile_id,
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        search_text=search_text,
        include_user_profile=include_user_profile,
        include_assigned_to=include_assigned_to,
        limit=limit,
        offset=offset,
    )
    return {"data": tickets, "tickets": tickets, "total": total}


@router.post("/")
async def create_support_ticket(
    data: SupportTicketCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a support ticket."""
    payload = _model_dump(data)

    subject = str(payload.get("subject") or "").strip()
    description = str(payload.get("description") or "").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="subject is required.")
    if not description:
        raise HTTPException(status_code=400, detail="description is required.")

    payload["subject"] = subject
    payload["description"] = description

    if "status" in payload and hasattr(payload["status"], "value"):
        payload["status"] = payload["status"].value
    if "priority" in payload and hasattr(payload["priority"], "value"):
        payload["priority"] = payload["priority"].value

    if "assigned_to" in payload and isinstance(payload.get("assigned_to"), str):
        payload["assigned_to"] = payload["assigned_to"].strip() or None

    payload["account_id"] = _resolve_required_account_for_write(account_id)

    user_id = _user_id_from_request(request)
    if user_id:
        payload.setdefault("created_by", user_id)
        payload.setdefault("updated_by", user_id)

    created = await copilot_db.support_tickets.create(data=payload)
    return {"data": created}


@router.get("/summary")
async def support_ticket_summary(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_read_access),
):
    """Get aggregated support ticket metrics by account/status/priority."""
    resolved_account = _resolve_account_filter(account_id)
    params: List[Any] = []
    where_clause = ""
    if resolved_account:
        params.append(resolved_account)
        where_clause = "WHERE account_id = $1"

    totals_sql = (
        f"SELECT COUNT(*)::int AS total, "
        f"COUNT(*) FILTER (WHERE status IN ('OPEN','IN_PROGRESS','PENDING'))::int AS active, "
        f"COUNT(*) FILTER (WHERE priority = 'URGENT')::int AS urgent "
        f"FROM copilot.support_tickets {where_clause}"
    )
    totals = (await copilot_db.support_tickets.execute_raw(totals_sql, *params))[0]

    by_account_sql = (
        f"SELECT account_id, COUNT(*)::int AS total "
        f"FROM copilot.support_tickets {where_clause} "
        f"GROUP BY account_id ORDER BY total DESC"
    )
    by_status_sql = (
        f"SELECT status, COUNT(*)::int AS total "
        f"FROM copilot.support_tickets {where_clause} "
        f"GROUP BY status ORDER BY total DESC"
    )
    by_priority_sql = (
        f"SELECT priority, COUNT(*)::int AS total "
        f"FROM copilot.support_tickets {where_clause} "
        f"GROUP BY priority ORDER BY total DESC"
    )
    by_account = await copilot_db.support_tickets.execute_raw(by_account_sql, *params)
    by_status = await copilot_db.support_tickets.execute_raw(by_status_sql, *params)
    by_priority = await copilot_db.support_tickets.execute_raw(by_priority_sql, *params)

    return {
        "data": {
            "totals": totals,
            "by_account": by_account,
            "by_status": by_status,
            "by_priority": by_priority,
        }
    }


@router.post("/bulk-update")
async def bulk_update_support_tickets(
    data: SupportTicketBulkUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Bulk update support tickets for global/super-admin operations."""
    ticket_ids = [str(tid).strip() for tid in data.ticket_ids if str(tid).strip()]
    if not ticket_ids:
        raise HTTPException(status_code=400, detail="ticket_ids is required.")

    update_data: Dict[str, Any] = {}
    if data.status is not None:
        update_data["status"] = data.status.value
    if data.priority is not None:
        update_data["priority"] = data.priority.value
    if data.assigned_to is not None:
        update_data["assigned_to"] = str(data.assigned_to).strip() or None
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="At least one of status, priority, or assigned_to must be provided.",
        )

    if is_super_admin() and data.account_id:
        expected_account_id = data.account_id
    elif is_super_admin():
        expected_account_id = None
    else:
        expected_account_id = _resolve_required_account_for_write(None)

    updated_ids: List[str] = []
    skipped_ids: List[str] = []
    for ticket_id in dict.fromkeys(ticket_ids):
        existing = await copilot_db.support_tickets.find_by_id(ticket_id)
        if not existing:
            skipped_ids.append(ticket_id)
            continue
        if expected_account_id and existing.get("account_id") != expected_account_id:
            skipped_ids.append(ticket_id)
            continue
        updated = await copilot_db.support_tickets.update(ticket_id, update_data)
        if updated:
            updated_ids.append(ticket_id)
        else:
            skipped_ids.append(ticket_id)

    return {
        "data": {
            "updated_count": len(updated_ids),
            "skipped_count": len(skipped_ids),
            "updated_ids": updated_ids,
            "skipped_ids": skipped_ids,
        }
    }


@router.get("/{ticket_id}")
async def get_support_ticket(
    ticket_id: str,
    request: Request,
    account_id: Optional[str] = None,
    include_user_profile: bool = True,
    include_assigned_to: bool = True,
    _auth=Depends(require_copilot_read_access),
):
    """Get a support ticket by id."""
    resolved_account = _resolve_account_filter(account_id)
    tickets, _ = await _query_tickets(
        resolved_account=resolved_account,
        ticket_id=ticket_id,
        include_user_profile=include_user_profile,
        include_assigned_to=include_assigned_to,
        limit=1,
        offset=0,
    )
    if not tickets:
        raise HTTPException(status_code=404, detail="Support ticket not found.")
    return {"data": tickets[0]}


@router.put("/{ticket_id}")
async def update_support_ticket(
    ticket_id: str,
    data: SupportTicketUpdate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Update a support ticket."""
    existing = await copilot_db.support_tickets.find_by_id(ticket_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Support ticket not found.")
    expected_account_id = _resolve_required_account_for_write(account_id)
    if existing.get("account_id") != expected_account_id:
        raise HTTPException(status_code=404, detail="Support ticket not found.")

    update_data = {k: v for k, v in _model_dump(data).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    if "subject" in update_data:
        update_data["subject"] = str(update_data["subject"]).strip()
        if not update_data["subject"]:
            raise HTTPException(status_code=400, detail="subject cannot be empty.")

    if "description" in update_data:
        update_data["description"] = str(update_data["description"]).strip()
        if not update_data["description"]:
            raise HTTPException(status_code=400, detail="description cannot be empty.")

    if "status" in update_data and hasattr(update_data["status"], "value"):
        update_data["status"] = update_data["status"].value

    if "priority" in update_data and hasattr(update_data["priority"], "value"):
        update_data["priority"] = update_data["priority"].value

    if "assigned_to" in update_data and isinstance(update_data["assigned_to"], str):
        update_data["assigned_to"] = update_data["assigned_to"].strip() or None

    user_id = _user_id_from_request(request)
    if user_id:
        update_data.setdefault("updated_by", user_id)

    updated = await copilot_db.support_tickets.update(ticket_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Support ticket not found.")

    return {"data": updated}


@router.delete("/{ticket_id}")
async def delete_support_ticket(
    ticket_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete a support ticket."""
    existing = await copilot_db.support_tickets.find_by_id(ticket_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Support ticket not found.")
    expected_account_id = _resolve_required_account_for_write(account_id)
    if existing.get("account_id") != expected_account_id:
        raise HTTPException(status_code=404, detail="Support ticket not found.")

    deleted = await copilot_db.support_tickets.delete(ticket_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Support ticket not found.")
    return {"status": "ok"}
