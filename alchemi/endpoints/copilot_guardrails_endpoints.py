"""Copilot guardrails management endpoints."""

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


router = APIRouter(prefix="/copilot/guardrails", tags=["Copilot Guardrails"])


class GuardrailConfigUpdate(BaseModel):
    enabled: bool = True
    action: str = "block"  # block|flag|allow_with_warning
    providers: List[str] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)


class GuardrailPatternCreate(BaseModel):
    guard_type: str = "pii"
    name: str
    pattern: str
    severity: str = "high"
    action: str = "block"
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GuardrailPatternUpdate(BaseModel):
    guard_type: Optional[str] = None
    name: Optional[str] = None
    pattern: Optional[str] = None
    severity: Optional[str] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class GuardrailEventCreate(BaseModel):
    event_type: str = "guardrail_violation"
    severity: str = "high"
    action: str = "blocked"
    model: Optional[str] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    organization_id: Optional[str] = None
    matched_patterns: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _normalize_guard_type(guard_type: str) -> str:
    value = guard_type.lower().strip()
    if value not in {"pii", "toxic", "jailbreak"}:
        raise HTTPException(status_code=400, detail="guard_type must be pii|toxic|jailbreak")
    return value


@router.get("/configs")
async def list_guardrail_configs(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("guardrail-config-type", account_id=account_id)
    items = [r["value"] for r in rows]
    if not items:
        default = {
            "enabled": True,
            "action": "block",
            "providers": [],
            "settings": {},
        }
        for guard_type in ["pii", "toxic", "jailbreak"]:
            payload = {
                "guard_type": guard_type,
                "account_id": account_id,
                **default,
            }
            await kv_put("guardrail-config-type", payload, account_id=account_id, object_id=guard_type)
            items.append(payload)
    items.sort(key=lambda x: x.get("guard_type") or "")
    return {"items": items, "total": len(items)}


@router.get("/config")
async def get_guardrail_config(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("guardrail-config", account_id=account_id, object_id="current")
    if row is None:
        return {
            "item": {
                "account_id": account_id,
                "enabled": True,
                "action": "block",
                "providers": [],
                "settings": {},
            }
        }
    return {"item": row["value"]}


@router.get("/config/{guard_type}")
async def get_guardrail_config_by_type(
    guard_type: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    normalized = _normalize_guard_type(guard_type)
    row = await kv_get("guardrail-config-type", account_id=account_id, object_id=normalized)
    if row is None:
        return {
            "item": {
                "account_id": account_id,
                "guard_type": normalized,
                "enabled": True,
                "action": "block",
                "providers": [],
                "settings": {},
            }
        }
    return {"item": row["value"]}


@router.put("/config")
async def upsert_guardrail_config(
    body: GuardrailConfigUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    now = datetime.now(timezone.utc).isoformat()
    current = await kv_get("guardrail-config", account_id=account_id, object_id="current")
    payload = {
        **(current["value"] if current else {}),
        "account_id": account_id,
        **body.model_dump(),
        "updated_at": now,
        "updated_by": get_actor_email_or_id(request),
    }
    if current is None:
        payload["created_at"] = now
        payload["created_by"] = get_actor_email_or_id(request)

    await kv_put("guardrail-config", payload, account_id=account_id, object_id="current")
    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.guardrails.config.upsert",
            "actor": get_actor_email_or_id(request),
            "data": payload,
        },
    )
    return {"item": payload}


@router.put("/config/{guard_type}")
async def upsert_guardrail_config_by_type(
    guard_type: str,
    body: GuardrailConfigUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    normalized = _normalize_guard_type(guard_type)
    now = datetime.now(timezone.utc).isoformat()
    current = await kv_get("guardrail-config-type", account_id=account_id, object_id=normalized)
    payload = {
        **(current["value"] if current else {}),
        "account_id": account_id,
        "guard_type": normalized,
        **body.model_dump(),
        "updated_at": now,
        "updated_by": get_actor_email_or_id(request),
    }
    if current is None:
        payload["created_at"] = now
        payload["created_by"] = get_actor_email_or_id(request)

    await kv_put("guardrail-config-type", payload, account_id=account_id, object_id=normalized)
    return {"item": payload}


@router.get("/patterns")
async def list_patterns(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("guardrail-pattern", account_id=account_id)
    items = [r["value"] for r in rows]
    guard_type = request.query_params.get("guard_type")
    if guard_type:
        normalized = _normalize_guard_type(guard_type)
        items = [item for item in items if item.get("guard_type") == normalized]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/patterns")
async def create_pattern(
    body: GuardrailPatternCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    pattern_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "pattern_id": pattern_id,
        "account_id": account_id,
        "guard_type": _normalize_guard_type(body.guard_type),
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("guardrail-pattern", payload, account_id=account_id, object_id=pattern_id)
    return {"item": payload}


@router.put("/patterns/{pattern_id}")
async def update_pattern(
    pattern_id: str,
    body: GuardrailPatternUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("guardrail-pattern", account_id=account_id, object_id=pattern_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern not found")

    current = row["value"]
    patch = body.model_dump(exclude_none=True)
    payload = {
        **current,
        **patch,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("guardrail-pattern", payload, account_id=account_id, object_id=pattern_id)
    return {"item": payload}


@router.delete("/patterns/{pattern_id}")
async def delete_pattern(
    pattern_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("guardrail-pattern", account_id=account_id, object_id=pattern_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return {"deleted": True}


@router.post("/events")
async def record_guardrail_event(
    body: GuardrailEventCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
):
    # Runtime writes are allowed with account context.
    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "account_id": account_id,
        **body.model_dump(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "recorded_by": get_actor_email_or_id(request),
    }
    await kv_put("guardrail-event", payload, account_id=account_id, object_id=event_id)
    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.guardrails.event.record",
            "actor": get_actor_email_or_id(request),
            "data": payload,
        },
    )
    return {"item": payload}


@router.get("/events")
async def list_guardrail_events(
    request: Request,
    account_id: str = Depends(require_account_context),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("guardrail-event", account_id=account_id)
    items = [r["value"] for r in rows]
    if severity:
        items = [i for i in items if str(i.get("severity", "")).lower() == severity.lower()]
    items.sort(key=lambda x: x.get("recorded_at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.get("/audit")
async def guardrail_audit_trail(
    request: Request,
    account_id: str = Depends(require_account_context),
    limit: int = Query(default=200, ge=1, le=5000),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("audit-event", account_id=account_id)
    items = [
        r["value"]
        for r in rows
        if str(r["value"].get("event_type", "")).startswith("copilot.guardrails.")
    ]
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}
