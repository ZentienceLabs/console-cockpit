"""Copilot budget/credits endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import append_audit_event, kv_delete, kv_get, kv_list, kv_put
from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    require_account_admin_or_super_admin,
    require_account_context,
    require_super_admin,
)
from alchemi.endpoints.copilot_helpers import as_float
from alchemi.middleware.tenant_context import is_super_admin


router = APIRouter(prefix="/copilot/budgets", tags=["Copilot Budgets"])


class BudgetPlanUpsertRequest(BaseModel):
    cycle: str = "monthly"
    credits_factor: Optional[float] = None
    account_allocated_credits: Optional[float] = None


class BudgetAllocationUpsertRequest(BaseModel):
    allocation_id: Optional[str] = None
    scope_type: str = Field(description="ORG|TEAM|USER")
    scope_id: str
    scope_name: Optional[str] = None
    allocated_credits: float
    overflow_cap: Optional[float] = None
    parent_scope_type: Optional[str] = None
    parent_scope_id: Optional[str] = None


class EqualDistributionRequest(BaseModel):
    parent_scope_type: str = "ACCOUNT"
    parent_scope_id: Optional[str] = None
    user_ids: List[str]
    total_credits: Optional[float] = None
    per_user_overrides: Dict[str, float] = Field(default_factory=dict)


class UsageRecordRequest(BaseModel):
    model: str
    cost: float
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    organization_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BudgetAlertRuleRequest(BaseModel):
    scope_type: str
    scope_id: str
    threshold_pct: float = 0.8
    notification_channels: List[str] = Field(default_factory=lambda: ["email"])


def _scope_rank(scope_type: str) -> int:
    ordering = {"ACCOUNT": 0, "ORG": 1, "TEAM": 2, "USER": 3}
    return ordering.get(scope_type.upper(), -1)


def _normalize_scope(scope_type: str) -> str:
    normalized = scope_type.upper().strip()
    mapping = {
        "ORGANIZATION": "ORG",
        "GROUP": "ORG",
        "ACCOUNT": "ACCOUNT",
        "TEAM": "TEAM",
        "USER": "USER",
        "ORG": "ORG",
    }
    out = mapping.get(normalized)
    if out is None:
        raise HTTPException(status_code=400, detail=f"Invalid scope_type: {scope_type}")
    return out


async def _get_plan(account_id: str) -> Dict[str, Any]:
    row = await kv_get("budget-plan", account_id=account_id, object_id="current")
    if row is None:
        factor = as_float(os.getenv("CREDITS_FACTOR"), 1.0)
        return {
            "plan_id": "current",
            "account_id": account_id,
            "cycle": "monthly",
            "credits_factor": factor,
            "account_allocated_credits": 0.0,
            "unallocated_credits": 0.0,
            "unallocated_used_credits": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    return row["value"]


async def _save_plan(account_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    return await kv_put("budget-plan", plan, account_id=account_id, object_id="current")


async def _list_allocations(account_id: str) -> List[Dict[str, Any]]:
    rows = await kv_list("budget-allocation", account_id=account_id)
    items = [r["value"] for r in rows]
    for item in items:
        item["scope_type"] = _normalize_scope(item.get("scope_type", "USER"))
        item["allocated_credits"] = as_float(item.get("allocated_credits"), 0.0)
        item["used_credits"] = as_float(item.get("used_credits"), 0.0)
    return items


def _compute_unallocated(plan: Dict[str, Any], allocations: List[Dict[str, Any]]) -> float:
    assigned = 0.0
    for row in allocations:
        if _scope_rank(row["scope_type"]) >= _scope_rank("ORG"):
            assigned += as_float(row.get("allocated_credits"), 0.0)
    return max(0.0, as_float(plan.get("account_allocated_credits"), 0.0) - assigned)


@router.get("/plan")
async def get_budget_plan(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    plan = await _get_plan(account_id)
    allocations = await _list_allocations(account_id)
    plan["unallocated_credits"] = _compute_unallocated(plan, allocations)
    await _save_plan(account_id, plan)
    return {"item": plan}


@router.put("/plan")
async def upsert_budget_plan(
    body: BudgetPlanUpsertRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    plan = await _get_plan(account_id)

    if body.cycle:
        plan["cycle"] = body.cycle

    if body.credits_factor is not None:
        if not is_super_admin():
            raise HTTPException(status_code=403, detail="Only super admin can set credits_factor")
        plan["credits_factor"] = body.credits_factor

    if body.account_allocated_credits is not None:
        if not is_super_admin():
            raise HTTPException(status_code=403, detail="Only super admin can set account allocation")
        plan["account_allocated_credits"] = body.account_allocated_credits

    allocations = await _list_allocations(account_id)
    plan["unallocated_credits"] = _compute_unallocated(plan, allocations)
    saved = await _save_plan(account_id, plan)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.budget.plan.upsert",
            "actor": get_actor_email_or_id(request),
            "data": {"plan": saved["value"]},
        },
    )
    return {"item": saved["value"]}


@router.get("/allocations")
async def list_allocations(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await _list_allocations(account_id)
    rows.sort(key=lambda x: (_scope_rank(x["scope_type"]), x.get("scope_name") or x.get("scope_id") or ""))
    return {"items": rows, "total": len(rows)}


@router.put("/allocations")
async def upsert_allocation(
    body: BudgetAllocationUpsertRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    scope_type = _normalize_scope(body.scope_type)
    if scope_type == "ACCOUNT":
        raise HTTPException(status_code=400, detail="Use /plan for account-level allocation")

    existing_rows = await _list_allocations(account_id)
    existing = None
    if body.allocation_id:
        existing = next((r for r in existing_rows if r.get("allocation_id") == body.allocation_id), None)
    else:
        existing = next(
            (
                r
                for r in existing_rows
                if r.get("scope_type") == scope_type and str(r.get("scope_id")) == str(body.scope_id)
            ),
            None,
        )

    allocation_id = (existing or {}).get("allocation_id") or body.allocation_id or str(uuid.uuid4())
    payload = {
        "allocation_id": allocation_id,
        "account_id": account_id,
        "scope_type": scope_type,
        "scope_id": body.scope_id,
        "scope_name": body.scope_name,
        "allocated_credits": body.allocated_credits,
        "used_credits": 0.0,
        "overflow_cap": body.overflow_cap,
        "parent_scope_type": _normalize_scope(body.parent_scope_type) if body.parent_scope_type else "ACCOUNT",
        "parent_scope_id": body.parent_scope_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }

    if existing:
        payload["used_credits"] = as_float(existing.get("used_credits"), 0.0)
        payload["created_at"] = existing.get("created_at")
        payload["created_by"] = existing.get("created_by")
    else:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        payload["created_by"] = get_actor_email_or_id(request)

    saved = await kv_put("budget-allocation", payload, account_id=account_id, object_id=allocation_id)

    plan = await _get_plan(account_id)
    all_allocations = await _list_allocations(account_id)
    plan["unallocated_credits"] = _compute_unallocated(plan, all_allocations)
    await _save_plan(account_id, plan)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.budget.allocation.upsert",
            "actor": get_actor_email_or_id(request),
            "data": payload,
        },
    )

    return {"item": saved["value"]}


@router.delete("/allocations/{allocation_id}")
async def delete_allocation(
    allocation_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("budget-allocation", account_id=account_id, object_id=allocation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Allocation not found")

    plan = await _get_plan(account_id)
    allocations = await _list_allocations(account_id)
    plan["unallocated_credits"] = _compute_unallocated(plan, allocations)
    await _save_plan(account_id, plan)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.budget.allocation.delete",
            "actor": get_actor_email_or_id(request),
            "data": {"allocation_id": allocation_id},
        },
    )
    return {"deleted": True}


@router.post("/allocations/distribute")
async def distribute_allocations(
    body: EqualDistributionRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    if not body.user_ids:
        raise HTTPException(status_code=400, detail="user_ids is required")

    plan = await _get_plan(account_id)
    allocations = await _list_allocations(account_id)

    total = body.total_credits
    if total is None:
        total = _compute_unallocated(plan, allocations)

    remaining = total - sum(as_float(v) for v in body.per_user_overrides.values())
    if remaining < 0:
        raise HTTPException(status_code=400, detail="Overrides exceed total credits")

    default_each = remaining / len(body.user_ids)
    created = []

    for user_id in body.user_ids:
        value = as_float(body.per_user_overrides.get(user_id), default_each)
        allocation_id = str(uuid.uuid4())
        payload = {
            "allocation_id": allocation_id,
            "account_id": account_id,
            "scope_type": "USER",
            "scope_id": user_id,
            "scope_name": user_id,
            "allocated_credits": value,
            "used_credits": 0.0,
            "parent_scope_type": _normalize_scope(body.parent_scope_type),
            "parent_scope_id": body.parent_scope_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": get_actor_email_or_id(request),
            "updated_by": get_actor_email_or_id(request),
        }
        await kv_put("budget-allocation", payload, account_id=account_id, object_id=allocation_id)
        created.append(payload)

    allocations = await _list_allocations(account_id)
    plan["unallocated_credits"] = _compute_unallocated(plan, allocations)
    await _save_plan(account_id, plan)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.budget.allocation.distribute",
            "actor": get_actor_email_or_id(request),
            "data": {
                "count": len(created),
                "total_credits": total,
                "parent_scope_type": body.parent_scope_type,
                "parent_scope_id": body.parent_scope_id,
            },
        },
    )
    return {"items": created, "total": len(created)}


@router.get("/effective")
async def get_effective_allocation(
    request: Request,
    account_id: str = Depends(require_account_context),
    user_id: Optional[str] = Query(default=None),
    team_id: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    _=Depends(require_account_admin_or_super_admin),
):
    plan = await _get_plan(account_id)
    allocations = await _list_allocations(account_id)

    chain = [
        ("USER", user_id),
        ("TEAM", team_id),
        ("ORG", organization_id),
    ]

    matched = []
    effective = None
    for scope_type, scope_id in chain:
        if not scope_id:
            continue
        row = next(
            (
                a
                for a in allocations
                if a.get("scope_type") == scope_type and str(a.get("scope_id")) == str(scope_id)
            ),
            None,
        )
        if row:
            matched.append(row)
            if effective is None:
                effective = row

    if effective is None:
        effective = {
            "scope_type": "ACCOUNT_UNALLOCATED",
            "scope_id": account_id,
            "allocated_credits": _compute_unallocated(plan, allocations),
            "used_credits": as_float(plan.get("unallocated_used_credits"), 0.0),
        }

    return {
        "item": {
            "account_id": account_id,
            "requested": {
                "user_id": user_id,
                "team_id": team_id,
                "organization_id": organization_id,
            },
            "effective": effective,
            "matched": matched,
        }
    }


@router.post("/usage")
async def record_usage(
    body: UsageRecordRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
):
    # End-user write path is intentionally available if account context is valid.
    plan = await _get_plan(account_id)
    factor = as_float(plan.get("credits_factor"), as_float(os.getenv("CREDITS_FACTOR"), 1.0))
    credits = body.cost * factor

    effective_payload = await get_effective_allocation(  # type: ignore[misc]
        request=request,
        account_id=account_id,
        user_id=body.user_id,
        team_id=body.team_id,
        organization_id=body.organization_id,
        _=None,
    )
    effective = effective_payload["item"]["effective"]

    usage_id = str(uuid.uuid4())
    usage_payload = {
        "usage_id": usage_id,
        "account_id": account_id,
        "model": body.model,
        "cost": body.cost,
        "credits": credits,
        "credits_factor": factor,
        "user_id": body.user_id,
        "team_id": body.team_id,
        "organization_id": body.organization_id,
        "effective_scope_type": effective.get("scope_type"),
        "effective_scope_id": effective.get("scope_id"),
        "metadata": body.metadata,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "recorded_by": get_actor_email_or_id(request),
    }

    await kv_put("budget-usage", usage_payload, account_id=account_id, object_id=usage_id)

    if effective.get("scope_type") in {"ORG", "TEAM", "USER"}:
        allocations = await _list_allocations(account_id)
        target = next(
            (
                a
                for a in allocations
                if a.get("scope_type") == effective.get("scope_type")
                and str(a.get("scope_id")) == str(effective.get("scope_id"))
            ),
            None,
        )
        if target:
            target["used_credits"] = as_float(target.get("used_credits"), 0.0) + credits
            target["updated_at"] = datetime.now(timezone.utc).isoformat()
            target["updated_by"] = get_actor_email_or_id(request)
            await kv_put(
                "budget-allocation",
                target,
                account_id=account_id,
                object_id=target.get("allocation_id"),
            )
    else:
        plan["unallocated_used_credits"] = as_float(plan.get("unallocated_used_credits"), 0.0) + credits
        await _save_plan(account_id, plan)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.budget.usage.record",
            "actor": get_actor_email_or_id(request),
            "data": usage_payload,
        },
    )

    return {"item": usage_payload}


@router.get("/usage")
async def list_usage(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    limit: int = Query(default=200, ge=1, le=5000),
):
    rows = await kv_list("budget-usage", account_id=account_id)
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("recorded_at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.post("/alerts/rules")
async def upsert_alert_rule(
    body: BudgetAlertRuleRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    scope_type = _normalize_scope(body.scope_type)
    rule_id = f"{scope_type}:{body.scope_id}"
    payload = {
        "rule_id": rule_id,
        "scope_type": scope_type,
        "scope_id": body.scope_id,
        "threshold_pct": body.threshold_pct,
        "notification_channels": body.notification_channels,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("budget-alert-rule", payload, account_id=account_id, object_id=rule_id)
    return {"item": payload}


@router.get("/alerts")
async def list_budget_alerts(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rules_rows = await kv_list("budget-alert-rule", account_id=account_id)
    rules = {r["value"]["rule_id"]: r["value"] for r in rules_rows}
    allocations = await _list_allocations(account_id)

    alerts = []
    for allocation in allocations:
        allocated = as_float(allocation.get("allocated_credits"), 0.0)
        if allocated <= 0:
            continue
        used = as_float(allocation.get("used_credits"), 0.0)
        scope_type = allocation.get("scope_type")
        scope_id = allocation.get("scope_id")
        rule = rules.get(f"{scope_type}:{scope_id}")
        threshold = as_float((rule or {}).get("threshold_pct"), 0.8)
        ratio = used / allocated if allocated > 0 else 0.0
        if ratio >= threshold:
            alerts.append(
                {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "allocated_credits": allocated,
                    "used_credits": used,
                    "usage_pct": ratio,
                    "threshold_pct": threshold,
                    "channels": (rule or {}).get("notification_channels") or ["email"],
                }
            )

    plan = await _get_plan(account_id)
    account_allocated = as_float(plan.get("account_allocated_credits"), 0.0)
    if account_allocated > 0:
        unallocated_used = as_float(plan.get("unallocated_used_credits"), 0.0)
        ratio = unallocated_used / account_allocated
        if ratio >= 0.8:
            alerts.append(
                {
                    "scope_type": "ACCOUNT",
                    "scope_id": account_id,
                    "allocated_credits": account_allocated,
                    "used_credits": unallocated_used,
                    "usage_pct": ratio,
                    "threshold_pct": 0.8,
                    "channels": ["email"],
                }
            )

    alerts.sort(key=lambda x: x["usage_pct"], reverse=True)
    return {"items": alerts, "total": len(alerts)}


@router.post("/allocate-account-credits")
async def super_admin_allocate_account_credits(
    body: BudgetPlanUpsertRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_super_admin),
):
    plan = await _get_plan(account_id)
    if body.account_allocated_credits is None:
        raise HTTPException(status_code=400, detail="account_allocated_credits is required")
    plan["account_allocated_credits"] = body.account_allocated_credits
    if body.credits_factor is not None:
        plan["credits_factor"] = body.credits_factor
    if body.cycle:
        plan["cycle"] = body.cycle
    plan["unallocated_credits"] = _compute_unallocated(plan, await _list_allocations(account_id))
    await _save_plan(account_id, plan)
    return {"item": plan}
