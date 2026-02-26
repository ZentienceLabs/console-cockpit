"""Copilot agent definition endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import append_audit_event, kv_delete, kv_get, kv_list, kv_put
from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    require_account_admin_or_super_admin,
    require_account_context,
)


router = APIRouter(prefix="/copilot/agents", tags=["Copilot Agents"])


class AgentDefCreate(BaseModel):
    name: str
    description: Optional[str] = None
    instructions: str
    model_code: Optional[str] = None
    tool_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentDefUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    model_code: Optional[str] = None
    tool_ids: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("")
async def list_agents(
    request: Request,
    account_id: str = Depends(require_account_context),
    status: Optional[str] = Query(default=None),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("agent-def", account_id=account_id)
    items = [r["value"] for r in rows]
    if status:
        items = [i for i in items if str(i.get("status", "draft")).lower() == status.lower()]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("")
async def create_agent(
    body: AgentDefCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "agent_id": agent_id,
        "account_id": account_id,
        "name": body.name,
        "description": body.description,
        "instructions": body.instructions,
        "model_code": body.model_code,
        "tool_ids": body.tool_ids,
        "tags": body.tags,
        "status": "draft",
        "metadata": body.metadata,
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("agent-def", payload, account_id=account_id, object_id=agent_id)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.agent.create",
            "actor": get_actor_email_or_id(request),
            "data": {"agent_id": agent_id, "name": body.name},
        },
    )

    return {"item": payload}


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("agent-def", account_id=account_id, object_id=agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"item": row["value"]}


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentDefUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("agent-def", account_id=account_id, object_id=agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    current = row["value"]
    patch = body.model_dump(exclude_none=True)
    payload = {
        **current,
        **patch,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }

    await kv_put("agent-def", payload, account_id=account_id, object_id=agent_id)
    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.agent.update",
            "actor": get_actor_email_or_id(request),
            "data": {"agent_id": agent_id, "fields": list(patch.keys())},
        },
    )
    return {"item": payload}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("agent-def", account_id=account_id, object_id=agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.agent.delete",
            "actor": get_actor_email_or_id(request),
            "data": {"agent_id": agent_id},
        },
    )
    return {"deleted": True}
