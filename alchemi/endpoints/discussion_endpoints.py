"""
Discussion management endpoints.
CRUD for threaded discussions with resolve workflow,
scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, require_account_access, require_super_admin

router = APIRouter(prefix="/alchemi/discussion", tags=["Discussions"])


# -- Request Models -----------------------------------------------------------


class DiscussionCreateRequest(BaseModel):
    workspace_id: Optional[str] = None
    type: Optional[str] = None
    content: str
    parent_object_type: Optional[str] = None
    parent_object_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    mentions: Optional[List[str]] = None
    attachments: Optional[List[str]] = None
    reactions: Optional[Dict[str, Any]] = None


class DiscussionUpdateRequest(BaseModel):
    content: Optional[str] = None
    mentions: Optional[List[str]] = None
    attachments: Optional[List[str]] = None


# -- Discussion Routes --------------------------------------------------------


@router.post("/new")
async def create_discussion(
    data: DiscussionCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new discussion."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    discussion_id = str(uuid.uuid4())

    create_data: Dict[str, Any] = {
        "id": discussion_id,
        "account_id": account_id,
        "content": data.content,
        "resolved": False,
        "mentions": data.mentions or [],
        "attachments": data.attachments or [],
        "reactions": Json(data.reactions or {}),
    }

    if data.workspace_id is not None:
        create_data["workspace_id"] = data.workspace_id
    if data.type is not None:
        create_data["type"] = data.type
    if data.parent_object_type is not None:
        create_data["parent_object_type"] = data.parent_object_type
    if data.parent_object_id is not None:
        create_data["parent_object_id"] = data.parent_object_id
    if data.parent_message_id is not None:
        create_data["parent_message_id"] = data.parent_message_id

    discussion = await prisma_client.db.alchemi_discussiontable.create(
        data=create_data,
    )

    return {
        "id": discussion.id,
        "message": "Discussion created successfully",
    }


@router.get("/list")
async def list_discussions(
    request: Request,
    workspace_id: Optional[str] = Query(default=None, description="Filter by workspace"),
    parent_object_type: Optional[str] = Query(default=None, description="Filter by parent object type"),
    parent_object_id: Optional[str] = Query(default=None, description="Filter by parent object ID"),
    resolved: Optional[bool] = Query(default=None, description="Filter by resolved status"),
    _=Depends(require_account_access),
):
    """List discussions for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if workspace_id:
        where["workspace_id"] = workspace_id
    if parent_object_type:
        where["parent_object_type"] = parent_object_type
    if parent_object_id:
        where["parent_object_id"] = parent_object_id
    if resolved is not None:
        where["resolved"] = resolved

    discussions = await prisma_client.db.alchemi_discussiontable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"discussions": discussions}


@router.get("/{discussion_id}")
async def get_discussion(
    discussion_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get discussion detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    discussion = await prisma_client.db.alchemi_discussiontable.find_first(
        where={"id": discussion_id, "account_id": account_id},
    )

    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")

    return discussion


@router.put("/{discussion_id}")
async def update_discussion(
    discussion_id: str,
    data: DiscussionUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a discussion (content, mentions, attachments)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_discussiontable.find_first(
        where={"id": discussion_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Discussion not found")

    update_data: Dict[str, Any] = {}

    if data.content is not None:
        update_data["content"] = data.content
    if data.mentions is not None:
        update_data["mentions"] = data.mentions
    if data.attachments is not None:
        update_data["attachments"] = data.attachments

    discussion = await prisma_client.db.alchemi_discussiontable.update(
        where={"id": discussion_id},
        data=update_data,
    )

    return discussion


@router.delete("/{discussion_id}")
async def delete_discussion(
    discussion_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete a discussion."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_discussiontable.find_first(
        where={"id": discussion_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Discussion not found")

    await prisma_client.db.alchemi_discussiontable.delete(
        where={"id": discussion_id},
    )

    return {
        "message": "Discussion deleted",
        "id": discussion_id,
    }


@router.post("/{discussion_id}/resolve")
async def resolve_discussion(
    discussion_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Resolve a discussion."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_discussiontable.find_first(
        where={"id": discussion_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Discussion not found")

    now = datetime.utcnow()
    discussion = await prisma_client.db.alchemi_discussiontable.update(
        where={"id": discussion_id},
        data={
            "resolved": True,
            "resolved_at": now,
            "resolved_by": account_id,
        },
    )

    return discussion
