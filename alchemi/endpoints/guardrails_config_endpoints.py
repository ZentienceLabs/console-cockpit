"""
Guardrails configuration endpoints.
CRUD for guardrail configs, custom patterns, and audit log queries,
scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/guardrails", tags=["Guardrails Config"])


# ── Request Models ───────────────────────────────────────────────────────────


class GuardrailConfigCreateRequest(BaseModel):
    guard_type: str
    enabled: Optional[bool] = True
    execution_order: Optional[int] = 1
    action_on_fail: Optional[str] = "block"
    config: Optional[Dict[str, Any]] = None


class GuardrailConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    execution_order: Optional[int] = None
    action_on_fail: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class CustomPatternCreateRequest(BaseModel):
    guard_type: str
    pattern_name: str
    pattern: str
    description: Optional[str] = None
    enabled: Optional[bool] = True


class GuardrailAuditCreateRequest(BaseModel):
    guard_type: str
    action: str  # "pass", "block", "flag", "log_only", "error"
    result: Optional[str] = None  # "pass" or "fail"
    request_data: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None


# ── Guardrail Config CRUD ────────────────────────────────────────────────────


@router.post("/new")
async def create_guardrail_config(
    data: GuardrailConfigCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new guardrail config for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Check for duplicate account_id + guard_type
    existing = await prisma_client.db.alchemi_guardrailsconfigtable.find_first(
        where={"account_id": account_id, "guard_type": data.guard_type},
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Guardrail config for '{data.guard_type}' already exists",
        )

    now = datetime.utcnow()
    config = await prisma_client.db.alchemi_guardrailsconfigtable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "guard_type": data.guard_type,
            "enabled": data.enabled if data.enabled is not None else True,
            "execution_order": data.execution_order or 1,
            "action_on_fail": data.action_on_fail or "block",
            "config": Json(data.config or {}),
            "version": 1,
            "created_by": account_id,
            "updated_by": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": config.id,
        "guard_type": config.guard_type,
        "message": "Guardrail config created successfully",
    }


@router.get("/list")
async def list_guardrail_configs(
    request: Request,
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    _=Depends(require_account_access),
):
    """List guardrail configs for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if enabled is not None:
        where["enabled"] = enabled

    configs = await prisma_client.db.alchemi_guardrailsconfigtable.find_many(
        where=where,
        order={"execution_order": "asc"},
    )

    return {"configs": configs}


@router.put("/{config_id}")
async def update_guardrail_config(
    config_id: str,
    data: GuardrailConfigUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a guardrail config."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_guardrailsconfigtable.find_first(
        where={"id": config_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Guardrail config not found")

    update_data: Dict[str, Any] = {"updated_by": account_id, "updated_at": datetime.utcnow()}

    if data.enabled is not None:
        update_data["enabled"] = data.enabled
    if data.execution_order is not None:
        update_data["execution_order"] = data.execution_order
    if data.action_on_fail is not None:
        update_data["action_on_fail"] = data.action_on_fail
    if data.config is not None:
        update_data["config"] = Json(data.config)

    config = await prisma_client.db.alchemi_guardrailsconfigtable.update(
        where={"id": config_id},
        data=update_data,
    )

    return config


@router.delete("/{config_id}")
async def delete_guardrail_config(
    config_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete a guardrail config."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_guardrailsconfigtable.find_first(
        where={"id": config_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Guardrail config not found")

    await prisma_client.db.alchemi_guardrailsconfigtable.delete(
        where={"id": config_id},
    )

    return {
        "message": f"Guardrail config '{existing.guard_type}' deleted",
        "id": config_id,
    }


# ── Custom Pattern Management ────────────────────────────────────────────────


@router.post("/pattern/new")
async def create_custom_pattern(
    data: CustomPatternCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a custom pattern for a guardrail type."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()
    pattern = await prisma_client.db.alchemi_guardrailscustompatterntable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "guard_type": data.guard_type,
            "pattern_name": data.pattern_name,
            "pattern": data.pattern,
            "description": data.description,
            "enabled": data.enabled if data.enabled is not None else True,
            "created_by": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": pattern.id,
        "pattern_name": pattern.pattern_name,
        "message": "Custom pattern created successfully",
    }


@router.get("/pattern/list")
async def list_custom_patterns(
    request: Request,
    guard_type: Optional[str] = Query(None, description="Filter by guard type"),
    include_system: bool = Query(True, description="Include system patterns (account_id IS NULL)"),
    _=Depends(require_account_access),
):
    """List custom patterns for the current account, optionally including system patterns."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where_conditions = [{"account_id": account_id}]
    if include_system:
        where_conditions.append({"account_id": None})
    where: Dict[str, Any] = {"OR": where_conditions}
    if guard_type:
        where["guard_type"] = guard_type

    patterns = await prisma_client.db.alchemi_guardrailscustompatterntable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"patterns": patterns}


@router.delete("/pattern/{pattern_id}")
async def delete_custom_pattern(
    pattern_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete a custom pattern."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_guardrailscustompatterntable.find_first(
        where={"id": pattern_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Custom pattern not found")

    await prisma_client.db.alchemi_guardrailscustompatterntable.delete(
        where={"id": pattern_id},
    )

    return {
        "message": f"Custom pattern '{existing.pattern_name}' deleted",
        "id": pattern_id,
    }


# ── Audit Log ─────────────────────────────────────────────────────────────────


@router.get("/audit")
async def list_audit_logs(
    request: Request,
    guard_type: Optional[str] = Query(None, description="Filter by guard type"),
    start_date: Optional[str] = Query(None, description="ISO date string"),
    end_date: Optional[str] = Query(None, description="ISO date string"),
    limit: Optional[int] = Query(100, description="Max records to return"),
    _=Depends(require_account_access),
):
    """Query guardrails audit log for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if guard_type:
        where["guard_type"] = guard_type

    # Date range filter
    date_filter: Dict[str, Any] = {}
    if start_date:
        try:
            date_filter["gte"] = datetime.fromisoformat(start_date)
        except (ValueError, TypeError):
            pass
    if end_date:
        try:
            date_filter["lte"] = datetime.fromisoformat(end_date)
        except (ValueError, TypeError):
            pass
    if date_filter:
        where["created_at"] = date_filter

    logs = await prisma_client.db.alchemi_guardrailsauditlogtable.find_many(
        where=where,
        order={"created_at": "desc"},
        take=limit or 100,
    )

    return {"audit_logs": logs, "count": len(logs)}


@router.post("/audit/new")
async def create_audit_log(
    data: GuardrailAuditCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a guardrails audit log entry."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()
    log_entry = await prisma_client.db.alchemi_guardrailsauditlogtable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "guard_type": data.guard_type,
            "action": data.action,
            "result": data.result,
            "request_data": Json(data.request_data) if data.request_data else None,
            "response_data": Json(data.response_data) if data.response_data else None,
            "user_id": data.user_id,
            "created_at": now,
        }
    )

    return {
        "id": log_entry.id,
        "message": "Audit log entry created successfully",
    }
