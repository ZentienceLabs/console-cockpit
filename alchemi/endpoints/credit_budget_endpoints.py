"""
Credit budget management endpoints.
Budget plans define allocation strategies; credit budgets track per-scope usage.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, require_account_access

router = APIRouter(prefix="/alchemi/budget", tags=["Credit Budgets"])


# ── Request Models ───────────────────────────────────────────────────────────


class BudgetPlanCreateRequest(BaseModel):
    name: str
    is_active: bool = True
    distribution: Optional[Dict[str, Any]] = None


class BudgetPlanUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    distribution: Optional[Dict[str, Any]] = None


class CreditBudgetCreateRequest(BaseModel):
    budget_plan_id: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    allocated: float = 0.0
    limit_amount: float = 0.0
    overflow_cap: Optional[float] = None
    used: float = 0.0
    overflow_used: float = 0.0
    cycle_start: Optional[datetime] = None
    cycle_end: Optional[datetime] = None


class CreditBudgetUpdateRequest(BaseModel):
    budget_plan_id: Optional[str] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    allocated: Optional[float] = None
    limit_amount: Optional[float] = None
    overflow_cap: Optional[float] = None
    used: Optional[float] = None
    overflow_used: Optional[float] = None
    cycle_start: Optional[datetime] = None
    cycle_end: Optional[datetime] = None


# ── Budget Plan Routes ───────────────────────────────────────────────────────


@router.post("/plan/new")
async def create_budget_plan(
    data: BudgetPlanCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new budget plan."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()
    plan = await prisma_client.db.alchemi_budgetplantable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "name": data.name,
            "is_active": data.is_active,
            "distribution": Json(data.distribution or {}),
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": plan.id,
        "name": plan.name,
        "message": "Budget plan created successfully",
    }


@router.get("/plan/list")
async def list_budget_plans(
    request: Request,
    _=Depends(require_account_access),
):
    """List budget plans for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    plans = await prisma_client.db.alchemi_budgetplantable.find_many(
        where={"account_id": account_id},
        order={"created_at": "desc"},
    )

    return {"plans": plans}


@router.put("/plan/{plan_id}")
async def update_budget_plan(
    plan_id: str,
    data: BudgetPlanUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a budget plan."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_budgetplantable.find_first(
        where={"id": plan_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Budget plan not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.name is not None:
        update_data["name"] = data.name
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.distribution is not None:
        update_data["distribution"] = Json(data.distribution)

    plan = await prisma_client.db.alchemi_budgetplantable.update(
        where={"id": plan_id},
        data=update_data,
    )

    return plan


@router.delete("/plan/{plan_id}")
async def delete_budget_plan(
    plan_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete a budget plan (soft delete)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_budgetplantable.find_first(
        where={"id": plan_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Budget plan not found")

    await prisma_client.db.alchemi_budgetplantable.update(
        where={"id": plan_id},
        data={"is_active": False, "updated_at": datetime.utcnow()},
    )

    return {
        "message": f"Budget plan '{existing.name}' deleted",
        "id": plan_id,
    }


# ── Credit Budget Routes ────────────────────────────────────────────────────


@router.post("/new")
async def create_credit_budget(
    data: CreditBudgetCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new credit budget."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()
    budget = await prisma_client.db.alchemi_creditbudgettable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "budget_plan_id": data.budget_plan_id,
            "scope_type": data.scope_type,
            "scope_id": data.scope_id,
            "allocated": data.allocated,
            "limit_amount": data.limit_amount,
            "overflow_cap": data.overflow_cap,
            "used": data.used,
            "overflow_used": data.overflow_used,
            "cycle_start": data.cycle_start,
            "cycle_end": data.cycle_end,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": budget.id,
        "account_id": budget.account_id,
        "message": "Credit budget created successfully",
    }


@router.get("/list")
async def list_credit_budgets(
    request: Request,
    scope_type: Optional[str] = Query(None),
    scope_id: Optional[str] = Query(None),
    _=Depends(require_account_access),
):
    """List credit budgets for the current account with optional filters."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if scope_type is not None:
        where["scope_type"] = scope_type
    if scope_id is not None:
        where["scope_id"] = scope_id

    budgets = await prisma_client.db.alchemi_creditbudgettable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"budgets": budgets}


@router.get("/{budget_id}")
async def get_credit_budget(
    budget_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get credit budget detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    budget = await prisma_client.db.alchemi_creditbudgettable.find_first(
        where={"id": budget_id, "account_id": account_id},
    )

    if not budget:
        raise HTTPException(status_code=404, detail="Credit budget not found")

    return budget


@router.put("/{budget_id}")
async def update_credit_budget(
    budget_id: str,
    data: CreditBudgetUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a credit budget."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_creditbudgettable.find_first(
        where={"id": budget_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Credit budget not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.budget_plan_id is not None:
        update_data["budget_plan_id"] = data.budget_plan_id
    if data.scope_type is not None:
        update_data["scope_type"] = data.scope_type
    if data.scope_id is not None:
        update_data["scope_id"] = data.scope_id
    if data.allocated is not None:
        update_data["allocated"] = data.allocated
    if data.limit_amount is not None:
        update_data["limit_amount"] = data.limit_amount
    if data.overflow_cap is not None:
        update_data["overflow_cap"] = data.overflow_cap
    if data.used is not None:
        update_data["used"] = data.used
    if data.overflow_used is not None:
        update_data["overflow_used"] = data.overflow_used
    if data.cycle_start is not None:
        update_data["cycle_start"] = data.cycle_start
    if data.cycle_end is not None:
        update_data["cycle_end"] = data.cycle_end

    budget = await prisma_client.db.alchemi_creditbudgettable.update(
        where={"id": budget_id},
        data=update_data,
    )

    return budget


@router.delete("/{budget_id}")
async def delete_credit_budget(
    budget_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete a credit budget."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_creditbudgettable.find_first(
        where={"id": budget_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Credit budget not found")

    await prisma_client.db.alchemi_creditbudgettable.delete(
        where={"id": budget_id},
    )

    return {
        "message": "Credit budget deleted",
        "id": budget_id,
    }
