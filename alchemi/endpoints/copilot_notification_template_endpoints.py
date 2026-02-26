"""Copilot notification template endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from string import Template
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import append_audit_event, kv_delete, kv_get, kv_list, kv_put
from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    require_account_admin_or_super_admin,
    require_account_context,
)


router = APIRouter(prefix="/copilot/notification-templates", tags=["Copilot Notification Templates"])


class NotificationTemplateCreate(BaseModel):
    key: str
    channel: str = "email"
    subject_template: Optional[str] = None
    body_template: str
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NotificationTemplateUpdate(BaseModel):
    channel: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class NotificationPreviewRequest(BaseModel):
    variables: Dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_templates(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("notification-template", account_id=account_id)
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("key") or "")
    return {"items": items, "total": len(items)}


@router.post("")
async def create_template(
    body: NotificationTemplateCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "template_id": template_id,
        "account_id": account_id,
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("notification-template", payload, account_id=account_id, object_id=template_id)
    return {"item": payload}


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    body: NotificationTemplateUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("notification-template", account_id=account_id, object_id=template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")

    current = row["value"]
    patch = body.model_dump(exclude_none=True)
    payload = {
        **current,
        **patch,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("notification-template", payload, account_id=account_id, object_id=template_id)
    return {"item": payload}


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("notification-template", account_id=account_id, object_id=template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"deleted": True}


@router.post("/{template_id}/preview")
async def preview_template(
    template_id: str,
    body: NotificationPreviewRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("notification-template", account_id=account_id, object_id=template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")

    item = row["value"]
    subject_t = Template(item.get("subject_template") or "")
    body_t = Template(item.get("body_template") or "")

    variables = {k: str(v) for k, v in body.variables.items()}
    rendered_subject = subject_t.safe_substitute(variables)
    rendered_body = body_t.safe_substitute(variables)

    return {
        "item": {
            "subject": rendered_subject,
            "body": rendered_body,
            "channel": item.get("channel"),
        }
    }


@router.post("/{template_id}/send-test")
async def send_test_notification(
    template_id: str,
    body: NotificationPreviewRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rendered = await preview_template(template_id, body, request, account_id, _)
    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.notification_template.send_test",
            "actor": get_actor_email_or_id(request),
            "data": {"template_id": template_id, "preview": rendered["item"]},
        },
    )
    return {"sent": True, "preview": rendered["item"]}
