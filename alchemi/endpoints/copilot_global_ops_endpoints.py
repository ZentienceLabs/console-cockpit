"""
Global Copilot operations endpoints for super-admin analytics and bulk actions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_auth import require_copilot_admin_access
from alchemi.endpoints.copilot_types import NotificationTemplateType, SupportTicketPriority, SupportTicketStatus
from alchemi.middleware.tenant_context import is_super_admin

router = APIRouter(prefix="/copilot/ops", tags=["Copilot - Global Ops"])


class GlobalTicketBulkActionRequest(BaseModel):
    account_ids: List[str] = Field(default_factory=list)
    current_status: Optional[SupportTicketStatus] = None
    search_text: Optional[str] = None
    status: Optional[SupportTicketStatus] = None
    priority: Optional[SupportTicketPriority] = None
    assigned_to: Optional[str] = None
    limit: int = 1000


class GlobalTemplateBulkDeleteRequest(BaseModel):
    account_ids: List[str] = Field(default_factory=list)
    event_ids: List[str] = Field(default_factory=list)
    types: List[NotificationTemplateType] = Field(default_factory=list)
    template_ids: List[str] = Field(default_factory=list)
    limit: int = 1000
    dry_run: bool = False


def _require_super_admin() -> None:
    if not is_super_admin():
        raise HTTPException(status_code=403, detail="Super admin access required.")


def _normalize_uuid_like_list(values: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text:
            normalized.append(text)
    return list(dict.fromkeys(normalized))


def _normalize_text_list(values: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text:
            normalized.append(text)
    return list(dict.fromkeys(normalized))


@router.get("/global/summary")
async def copilot_global_summary(
    request: Request,
    account_ids: List[str] = Query(default_factory=list),
    _auth=Depends(require_copilot_admin_access),
):
    """
    Aggregate Copilot operational metrics across all accounts (or selected accounts).
    """
    _require_super_admin()

    normalized_account_ids = _normalize_uuid_like_list(account_ids)
    params: List[Any] = []
    account_filter = ""
    if normalized_account_ids:
        params.append(normalized_account_ids)
        account_filter = "WHERE a.account_id::text = ANY($1::text[])"

    by_account_sql = f"""
        SELECT
            a.account_id::text AS account_id,
            a.account_name AS account_name,
            a.status AS account_status,
            (
                SELECT COUNT(*)
                FROM copilot.credit_budget cb
                WHERE cb.account_id::text = a.account_id::text
            )::int AS budget_count,
            (
                SELECT COUNT(*)
                FROM copilot.v_budget_alerts ba
                WHERE ba.account_id::text = a.account_id::text
            )::int AS budget_alert_count,
            (
                SELECT COALESCE(SUM(v.total_allocated), 0)
                FROM copilot.v_budget_summary v
                WHERE v.account_id::text = a.account_id::text
            )::float AS credits_allocated,
            (
                SELECT COALESCE(SUM(v.total_used), 0)
                FROM copilot.v_budget_summary v
                WHERE v.account_id::text = a.account_id::text
            )::float AS credits_used,
            (
                SELECT COUNT(*)
                FROM copilot.agents_def ad
                WHERE ad.account_id::text = a.account_id::text
            )::int AS agent_count,
            (
                SELECT COUNT(*)
                FROM copilot.marketplace_items mi
                WHERE mi.account_id::text = a.account_id::text OR mi.account_id IS NULL
            )::int AS marketplace_count,
            (
                SELECT COUNT(*)
                FROM copilot.account_connections ac
                WHERE ac.account_id::text = a.account_id::text
            )::int AS connection_count,
            (
                SELECT COUNT(*)
                FROM copilot.notification_templates nt
                WHERE nt.account_id::text = a.account_id::text
            )::int AS notification_template_count,
            (
                SELECT COUNT(*)
                FROM copilot.support_tickets st
                WHERE st.account_id::text = a.account_id::text
                  AND st.status IN ('OPEN','IN_PROGRESS','PENDING')
            )::int AS open_ticket_count,
            (
                SELECT COUNT(*)
                FROM copilot.support_tickets st
                WHERE st.account_id::text = a.account_id::text
            )::int AS ticket_count,
            (
                SELECT COUNT(*)
                FROM copilot.users u
                WHERE u.account_id::text = a.account_id::text
            )::int AS user_count,
            (
                SELECT COUNT(*)
                FROM copilot.groups g
                WHERE g.account_id::text = a.account_id::text
            )::int AS group_count,
            (
                SELECT COUNT(*)
                FROM copilot.teams t
                WHERE t.account_id::text = a.account_id::text
            )::int AS team_count,
            (
                SELECT COUNT(*)
                FROM copilot.user_invites i
                WHERE i.account_id::text = a.account_id::text
                  AND i.status = 'PENDING'
            )::int AS pending_invite_count,
            (
                SELECT COUNT(*)
                FROM copilot.guardrails_audit_log ga
                WHERE ga.account_id::text = a.account_id::text
                  AND ga.changed_at >= (NOW() - INTERVAL '7 days')
            )::int AS guardrail_audit_7d_count,
            CASE
                WHEN (
                    SELECT GREATEST(
                        COALESCE(jsonb_array_length((a.metadata->'entitlements'->'copilot_model_super_allowlist')), 0),
                        COALESCE(jsonb_array_length((a.metadata->'entitlements'->'copilot_model_tenant_allowlist')), 0),
                        COALESCE(jsonb_array_length((a.metadata->'entitlements'->'copilot_model_allowlist')), 0)
                    )
                ) > 0
                THEN 'allowlist'
                ELSE 'all_catalog'
            END AS model_selection_mode
        FROM "Alchemi_AccountTable" a
        {account_filter}
        ORDER BY a.account_name ASC
    """

    rows = await copilot_db.credit_budgets.execute_raw(by_account_sql, *params)
    by_account = [dict(r) for r in rows]

    totals = {
        "account_count": len(by_account),
        "budget_count": sum(int(r.get("budget_count") or 0) for r in by_account),
        "budget_alert_count": sum(int(r.get("budget_alert_count") or 0) for r in by_account),
        "credits_allocated": sum(float(r.get("credits_allocated") or 0) for r in by_account),
        "credits_used": sum(float(r.get("credits_used") or 0) for r in by_account),
        "agent_count": sum(int(r.get("agent_count") or 0) for r in by_account),
        "marketplace_count": sum(int(r.get("marketplace_count") or 0) for r in by_account),
        "connection_count": sum(int(r.get("connection_count") or 0) for r in by_account),
        "notification_template_count": sum(
            int(r.get("notification_template_count") or 0) for r in by_account
        ),
        "open_ticket_count": sum(int(r.get("open_ticket_count") or 0) for r in by_account),
        "ticket_count": sum(int(r.get("ticket_count") or 0) for r in by_account),
        "user_count": sum(int(r.get("user_count") or 0) for r in by_account),
        "group_count": sum(int(r.get("group_count") or 0) for r in by_account),
        "team_count": sum(int(r.get("team_count") or 0) for r in by_account),
        "pending_invite_count": sum(int(r.get("pending_invite_count") or 0) for r in by_account),
        "guardrail_audit_7d_count": sum(
            int(r.get("guardrail_audit_7d_count") or 0) for r in by_account
        ),
        "allowlist_mode_accounts": sum(
            1 for r in by_account if str(r.get("model_selection_mode") or "") == "allowlist"
        ),
    }
    totals["all_catalog_mode_accounts"] = totals["account_count"] - totals["allowlist_mode_accounts"]

    return {
        "data": {
            "totals": totals,
            "by_account": by_account,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    }


@router.post("/global/bulk/tickets")
async def copilot_global_bulk_update_tickets(
    data: GlobalTicketBulkActionRequest,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """
    Bulk update support tickets across one or more accounts.
    """
    _require_super_admin()

    has_update = any(
        [
            data.status is not None,
            data.priority is not None,
            data.assigned_to is not None,
        ]
    )
    if not has_update:
        raise HTTPException(
            status_code=400,
            detail="At least one update field is required (status, priority, assigned_to).",
        )

    account_ids = _normalize_uuid_like_list(data.account_ids)
    where_parts: List[str] = []
    params: List[Any] = []

    if account_ids:
        params.append(account_ids)
        where_parts.append(f"account_id::text = ANY(${len(params)}::text[])")

    if data.current_status is not None:
        params.append(data.current_status.value)
        where_parts.append(f"status = ${len(params)}")

    if data.search_text and data.search_text.strip():
        params.append(f"%{data.search_text.strip()}%")
        where_parts.append(f"(subject ILIKE ${len(params)} OR description ILIKE ${len(params)})")

    params.append(max(1, min(data.limit, 5000)))
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    selection_sql = f"""
        SELECT id::text AS id
        FROM copilot.support_tickets
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ${len(params)}
    """
    selected_rows = await copilot_db.support_tickets.execute_raw(selection_sql, *params)
    ticket_ids = [str(r.get("id")) for r in selected_rows if r.get("id")]
    if not ticket_ids:
        return {
            "data": {
                "matched_count": 0,
                "updated_count": 0,
                "updated_ids": [],
            }
        }

    update_sets: List[str] = []
    update_params: List[Any] = []

    if data.status is not None:
        update_params.append(data.status.value)
        update_sets.append(f"status = ${len(update_params)}")
    if data.priority is not None:
        update_params.append(data.priority.value)
        update_sets.append(f"priority = ${len(update_params)}")
    if data.assigned_to is not None:
        update_params.append(data.assigned_to)
        update_sets.append(f"assigned_to = ${len(update_params)}")

    actor_id = str((_auth or {}).get("user_id") or "super_admin")
    update_params.append(actor_id)
    update_sets.append(f"updated_by = ${len(update_params)}")
    update_sets.append("updated_at = now()")

    update_params.append(ticket_ids)
    update_sql = f"""
        UPDATE copilot.support_tickets
        SET {', '.join(update_sets)}
        WHERE id::text = ANY(${len(update_params)}::text[])
        RETURNING id::text AS id
    """
    updated_rows = await copilot_db.support_tickets.execute_raw(update_sql, *update_params)
    updated_ids = [str(r.get("id")) for r in updated_rows if r.get("id")]

    return {
        "data": {
            "matched_count": len(ticket_ids),
            "updated_count": len(updated_ids),
            "updated_ids": updated_ids,
            "applied": {
                "status": data.status.value if data.status is not None else None,
                "priority": data.priority.value if data.priority is not None else None,
                "assigned_to": data.assigned_to,
            },
        }
    }


@router.post("/global/bulk/notification-templates/delete")
async def copilot_global_bulk_delete_notification_templates(
    data: GlobalTemplateBulkDeleteRequest,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """
    Bulk delete notification templates across one or more accounts.
    """
    _require_super_admin()

    account_ids = _normalize_uuid_like_list(data.account_ids)
    event_ids = _normalize_text_list(data.event_ids)
    template_ids = _normalize_uuid_like_list(data.template_ids)
    types = [t.value for t in data.types if t is not None]

    where_parts: List[str] = []
    params: List[Any] = []

    if account_ids:
        params.append(account_ids)
        where_parts.append(f"account_id::text = ANY(${len(params)}::text[])")

    if event_ids:
        params.append(event_ids)
        where_parts.append(f"event_id = ANY(${len(params)}::text[])")

    if types:
        params.append(types)
        where_parts.append(f"type = ANY(${len(params)}::text[])")

    if template_ids:
        params.append(template_ids)
        where_parts.append(f"id::text = ANY(${len(params)}::text[])")

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    params.append(max(1, min(data.limit, 5000)))
    selection_sql = f"""
        SELECT id::text AS id
        FROM copilot.notification_templates
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ${len(params)}
    """
    selected_rows = await copilot_db.notification_templates.execute_raw(selection_sql, *params)
    matched_ids = [str(r.get("id")) for r in selected_rows if r.get("id")]

    if data.dry_run:
        return {
            "data": {
                "dry_run": True,
                "matched_count": len(matched_ids),
                "matched_ids": matched_ids,
                "deleted_count": 0,
                "deleted_ids": [],
            }
        }

    if not matched_ids:
        return {
            "data": {
                "dry_run": False,
                "matched_count": 0,
                "deleted_count": 0,
                "matched_ids": [],
                "deleted_ids": [],
            }
        }

    delete_sql = """
        DELETE FROM copilot.notification_templates
        WHERE id::text = ANY($1::text[])
        RETURNING id::text AS id
    """
    deleted_rows = await copilot_db.notification_templates.execute_raw(delete_sql, matched_ids)
    deleted_ids = [str(r.get("id")) for r in deleted_rows if r.get("id")]

    return {
        "data": {
            "dry_run": False,
            "matched_count": len(matched_ids),
            "deleted_count": len(deleted_ids),
            "matched_ids": matched_ids,
            "deleted_ids": deleted_ids,
        }
    }
