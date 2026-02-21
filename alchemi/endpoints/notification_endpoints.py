"""
Notification management endpoints.
CRUD for notifications, platform templates, and account template overrides.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, require_account_access, require_super_admin

router = APIRouter(prefix="/alchemi/notification", tags=["Notifications"])


# -- Request Models -----------------------------------------------------------


class NotificationCreateRequest(BaseModel):
    recipient_id: str
    type: str
    title: str
    content: str
    status: Optional[str] = "PENDING"
    metadata: Optional[Dict[str, Any]] = None


class NotificationTemplateCreateRequest(BaseModel):
    name: str
    type: str
    subject: Optional[str] = None
    body: Optional[str] = None
    channel: Optional[str] = None
    template_config: Optional[Dict[str, Any]] = None


class AccountNotificationTemplateCreateRequest(BaseModel):
    template_id: Optional[str] = None
    name: str
    type: str
    subject: Optional[str] = None
    body: Optional[str] = None
    channel: Optional[str] = None
    template_config: Optional[Dict[str, Any]] = None


# -- Notification Routes ------------------------------------------------------


@router.post("/new")
async def create_notification(
    data: NotificationCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new notification."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    notification_id = str(uuid.uuid4())
    now = datetime.utcnow()

    notification = await prisma_client.db.alchemi_notificationtable.create(
        data={
            "id": notification_id,
            "account_id": account_id,
            "recipient_id": data.recipient_id,
            "type": data.type,
            "title": data.title,
            "content": data.content,
            "status": data.status or "PENDING",
            "metadata": Json(data.metadata or {}),
        }
    )

    return {
        "id": notification.id,
        "title": notification.title,
        "message": "Notification created successfully",
    }


@router.get("/list")
async def list_notifications(
    request: Request,
    recipient_id: Optional[str] = Query(default=None, description="Filter by recipient"),
    type: Optional[str] = Query(default=None, description="Filter by type"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    _=Depends(require_account_access),
):
    """List notifications for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if recipient_id:
        where["recipient_id"] = recipient_id
    if type:
        where["type"] = type
    if status:
        where["status"] = status

    notifications = await prisma_client.db.alchemi_notificationtable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"notifications": notifications}


@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Mark a notification as read."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_notificationtable.find_first(
        where={"id": notification_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Notification not found")

    now = datetime.utcnow()
    notification = await prisma_client.db.alchemi_notificationtable.update(
        where={"id": notification_id},
        data={
            "read_at": now,
            "status": "READ",
        },
    )

    return notification


@router.get("/unread-count")
async def get_unread_count(
    request: Request,
    recipient_id: str = Query(description="Recipient ID to count unread notifications for"),
    _=Depends(require_account_access),
):
    """Get the count of unread notifications for a recipient."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    count = await prisma_client.db.alchemi_notificationtable.count(
        where={
            "account_id": account_id,
            "recipient_id": recipient_id,
            "read_at": None,
        },
    )

    return {"count": count}


# -- Platform Notification Template Routes (super admin) ----------------------


@router.get("/template/list")
async def list_notification_templates(
    request: Request,
    _=Depends(require_account_access),
):
    """List platform notification templates."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    templates = await prisma_client.db.alchemi_notificationtemplatetable.find_many(
        order={"created_at": "desc"},
    )

    return {"templates": templates}


@router.post("/template/new")
async def create_notification_template(
    data: NotificationTemplateCreateRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    """Create a new platform notification template (super admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    template_id = str(uuid.uuid4())

    template = await prisma_client.db.alchemi_notificationtemplatetable.create(
        data={
            "id": template_id,
            "name": data.name,
            "type": data.type,
            "subject": data.subject,
            "body": data.body,
            "channel": data.channel,
            "template_config": Json(data.template_config or {}),
        }
    )

    return {
        "id": template.id,
        "name": template.name,
        "message": "Notification template created successfully",
    }


# -- Account Notification Template Overrides ----------------------------------


@router.post("/account-template/new")
async def create_account_notification_template(
    data: AccountNotificationTemplateCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create an account-level notification template override."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    template_id = str(uuid.uuid4())

    template = await prisma_client.db.alchemi_accountnotificationtemplatetable.create(
        data={
            "id": template_id,
            "account_id": account_id,
            "template_id": data.template_id,
            "name": data.name,
            "type": data.type,
            "subject": data.subject,
            "body": data.body,
            "channel": data.channel,
            "template_config": Json(data.template_config or {}),
        }
    )

    return {
        "id": template.id,
        "name": template.name,
        "message": "Account notification template created successfully",
    }


@router.get("/account-template/list")
async def list_account_notification_templates(
    request: Request,
    _=Depends(require_account_access),
):
    """List account notification template overrides."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    templates = await prisma_client.db.alchemi_accountnotificationtemplatetable.find_many(
        where={"account_id": account_id},
        order={"created_at": "desc"},
    )

    return {"templates": templates}
