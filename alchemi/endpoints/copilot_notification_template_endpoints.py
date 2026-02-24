"""
Notification template management endpoints for copilot cockpit features.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_auth import (
    require_copilot_admin_access,
    require_copilot_read_access,
)
from alchemi.endpoints.copilot_types import (
    NotificationTemplateCreate,
    NotificationTemplateType,
    NotificationTemplateUpdate,
)
from alchemi.middleware.account_middleware import (
    _get_master_key,
    decode_jwt_token,
    extract_token_from_request,
)
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

router = APIRouter(
    prefix="/copilot/notification-templates",
    tags=["Copilot - Notification Templates"],
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


def _normalize_where_account(account_id: Optional[str]) -> Optional[str]:
    if is_super_admin():
        if account_id:
            return account_id
        return get_current_account_id()

    resolved = get_current_account_id()
    if not resolved:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return resolved


def _resolve_required_account_for_write(account_id: Optional[str]) -> str:
    resolved = _normalize_where_account(account_id)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for this super admin write operation.",
        )
    return resolved


@router.get("/")
async def list_notification_templates(
    request: Request,
    account_id: Optional[str] = None,
    template_id: Optional[str] = None,
    event_id: Optional[str] = None,
    type: Optional[NotificationTemplateType] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    """List notification templates for the current account."""
    where: Dict[str, Any] = {}

    resolved_account = _normalize_where_account(account_id)
    if resolved_account:
        where["account_id"] = resolved_account

    if template_id:
        where["template_id"] = template_id
    if event_id:
        where["event_id"] = event_id
    if type:
        where["type"] = type.value

    templates = await copilot_db.notification_templates.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.notification_templates.count(where=where if where else None)

    return {"data": templates, "templates": templates, "total": total}


@router.post("/")
async def create_notification_template(
    data: NotificationTemplateCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a notification template."""
    payload = _model_dump(data)

    title_line = (payload.get("title_line") or "").strip()
    template_content = (payload.get("template_content") or "").strip()

    if not title_line:
        raise HTTPException(status_code=400, detail="title_line is required.")
    if not template_content:
        raise HTTPException(status_code=400, detail="template_content is required.")

    payload["title_line"] = title_line
    payload["template_content"] = template_content

    template_type = payload.get("type")
    if hasattr(template_type, "value"):
        payload["type"] = template_type.value

    for key in ("template_id", "event_id"):
        if isinstance(payload.get(key), str):
            payload[key] = payload[key].strip() or None

    payload["account_id"] = _resolve_required_account_for_write(account_id)

    user_id = _user_id_from_request(request)
    if user_id:
        payload.setdefault("created_by", user_id)
        payload.setdefault("updated_by", user_id)

    try:
        created = await copilot_db.notification_templates.create(data=payload)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "unique" in msg:
            raise HTTPException(
                status_code=409,
                detail="A notification template with this template_id already exists.",
            ) from exc
        raise

    return {"data": created}


@router.get("/summary")
async def notification_template_summary(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_read_access),
):
    """Get aggregated template counts by account/type/event."""
    resolved_account = _normalize_where_account(account_id)
    params: List[Any] = []
    where_clause = ""
    if resolved_account:
        params.append(resolved_account)
        where_clause = "WHERE account_id = $1"

    totals_sql = f"SELECT COUNT(*)::int AS total FROM copilot.notification_templates {where_clause}"
    by_account_sql = (
        f"SELECT account_id, COUNT(*)::int AS total "
        f"FROM copilot.notification_templates {where_clause} "
        f"GROUP BY account_id ORDER BY total DESC"
    )
    by_type_sql = (
        f"SELECT type, COUNT(*)::int AS total "
        f"FROM copilot.notification_templates {where_clause} "
        f"GROUP BY type ORDER BY total DESC"
    )
    by_event_sql = (
        f"SELECT event_id, COUNT(*)::int AS total "
        f"FROM copilot.notification_templates {where_clause} "
        f"GROUP BY event_id ORDER BY total DESC"
    )

    totals = (await copilot_db.notification_templates.execute_raw(totals_sql, *params))[0]
    by_account = await copilot_db.notification_templates.execute_raw(by_account_sql, *params)
    by_type = await copilot_db.notification_templates.execute_raw(by_type_sql, *params)
    by_event = await copilot_db.notification_templates.execute_raw(by_event_sql, *params)

    return {
        "data": {
            "totals": totals,
            "by_account": by_account,
            "by_type": by_type,
            "by_event": by_event,
        }
    }


@router.post("/bulk-delete")
async def bulk_delete_notification_templates(
    data: Dict[str, Any],
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Bulk delete templates for global notification operations."""
    template_ids = [str(tid).strip() for tid in (data.get("template_ids") or []) if str(tid).strip()]
    if not template_ids:
        raise HTTPException(status_code=400, detail="template_ids is required.")

    requested_account_id = data.get("account_id")
    if is_super_admin() and requested_account_id:
        expected_account_id = str(requested_account_id)
    elif is_super_admin():
        expected_account_id = None
    else:
        expected_account_id = _resolve_required_account_for_write(None)

    deleted_ids: List[str] = []
    skipped_ids: List[str] = []
    for template_id in dict.fromkeys(template_ids):
        row = await copilot_db.notification_templates.find_by_id(template_id)
        if not row:
            skipped_ids.append(template_id)
            continue
        if expected_account_id and row.get("account_id") != expected_account_id:
            skipped_ids.append(template_id)
            continue
        deleted = await copilot_db.notification_templates.delete(template_id)
        if deleted:
            deleted_ids.append(template_id)
        else:
            skipped_ids.append(template_id)

    return {
        "data": {
            "deleted_count": len(deleted_ids),
            "skipped_count": len(skipped_ids),
            "deleted_ids": deleted_ids,
            "skipped_ids": skipped_ids,
        }
    }


@router.get("/{template_db_id}")
async def get_notification_template(
    template_db_id: str,
    request: Request,
    _auth=Depends(require_copilot_read_access),
):
    """Get a notification template by database id."""
    template = await copilot_db.notification_templates.find_by_id(template_db_id)
    if not template:
        raise HTTPException(status_code=404, detail="Notification template not found.")
    return {"data": template}


@router.put("/{template_db_id}")
async def update_notification_template(
    template_db_id: str,
    data: NotificationTemplateUpdate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Update a notification template."""
    existing = await copilot_db.notification_templates.find_by_id(template_db_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Notification template not found.")
    expected_account_id = _resolve_required_account_for_write(account_id)
    if existing.get("account_id") != expected_account_id:
        raise HTTPException(status_code=404, detail="Notification template not found.")

    update_data = {k: v for k, v in _model_dump(data).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    if "title_line" in update_data:
        update_data["title_line"] = str(update_data["title_line"]).strip()
        if not update_data["title_line"]:
            raise HTTPException(status_code=400, detail="title_line cannot be empty.")

    if "template_content" in update_data:
        update_data["template_content"] = str(update_data["template_content"]).strip()
        if not update_data["template_content"]:
            raise HTTPException(status_code=400, detail="template_content cannot be empty.")

    if "type" in update_data and hasattr(update_data["type"], "value"):
        update_data["type"] = update_data["type"].value

    for key in ("template_id", "event_id"):
        if key in update_data and isinstance(update_data[key], str):
            update_data[key] = update_data[key].strip() or None

    user_id = _user_id_from_request(request)
    if user_id:
        update_data.setdefault("updated_by", user_id)

    try:
        updated = await copilot_db.notification_templates.update(template_db_id, update_data)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "unique" in msg:
            raise HTTPException(
                status_code=409,
                detail="A notification template with this template_id already exists.",
            ) from exc
        raise

    if not updated:
        raise HTTPException(status_code=404, detail="Notification template not found.")

    return {"data": updated}


@router.delete("/{template_db_id}")
async def delete_notification_template(
    template_db_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete a notification template."""
    existing = await copilot_db.notification_templates.find_by_id(template_db_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Notification template not found.")
    expected_account_id = _resolve_required_account_for_write(account_id)
    if existing.get("account_id") != expected_account_id:
        raise HTTPException(status_code=404, detail="Notification template not found.")

    deleted = await copilot_db.notification_templates.delete(template_db_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Notification template not found.")
    return {"status": "ok"}
