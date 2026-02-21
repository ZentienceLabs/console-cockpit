"""
Account quota management endpoints.
Tracks included credits, usage, overage, and rollover per account.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, require_account_access

router = APIRouter(prefix="/alchemi/quota", tags=["Account Quotas"])


# ── Request Models ───────────────────────────────────────────────────────────


class QuotaCreateRequest(BaseModel):
    subscription_id: Optional[str] = None
    product_code: Optional[str] = None
    feature_code: Optional[str] = None
    unit: Optional[str] = "credits"
    included: float = 0.0
    used: float = 0.0
    overage_used: float = 0.0
    overage_limit: float = 0.0
    reset_policy: Optional[str] = "MONTHLY"
    rollover_enabled: bool = False
    rollover_cap: float = 0.0
    rollover_from_previous: float = 0.0
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    is_active: bool = True


class QuotaUpdateRequest(BaseModel):
    subscription_id: Optional[str] = None
    product_code: Optional[str] = None
    feature_code: Optional[str] = None
    unit: Optional[str] = None
    included: Optional[float] = None
    used: Optional[float] = None
    overage_used: Optional[float] = None
    overage_limit: Optional[float] = None
    reset_policy: Optional[str] = None
    rollover_enabled: Optional[bool] = None
    rollover_cap: Optional[float] = None
    rollover_from_previous: Optional[float] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    is_active: Optional[bool] = None


class QuotaCheckRequest(BaseModel):
    unit: str = "credits"
    amount: float


class QuotaDeductRequest(BaseModel):
    unit: str = "credits"
    amount: float


class QuotaResetRequest(BaseModel):
    quota_id: str
    new_period_start: datetime
    new_period_end: datetime


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post("/new")
async def create_quota(
    data: QuotaCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new account quota."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()
    quota = await prisma_client.db.alchemi_accountquotatable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "subscription_id": data.subscription_id,
            "product_code": data.product_code,
            "feature_code": data.feature_code,
            "unit": data.unit or "credits",
            "included": data.included,
            "used": data.used,
            "overage_used": data.overage_used,
            "overage_limit": data.overage_limit,
            "reset_policy": data.reset_policy or "MONTHLY",
            "rollover_enabled": data.rollover_enabled,
            "rollover_cap": data.rollover_cap,
            "rollover_from_previous": data.rollover_from_previous,
            "period_start": data.period_start,
            "period_end": data.period_end,
            "is_active": data.is_active,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": quota.id,
        "account_id": quota.account_id,
        "message": "Quota created successfully",
    }


@router.get("/list")
async def list_quotas(
    request: Request,
    unit: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    product_code: Optional[str] = Query(None),
    _=Depends(require_account_access),
):
    """List quotas for the current account with optional filters."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if unit is not None:
        where["unit"] = unit
    if is_active is not None:
        where["is_active"] = is_active
    if product_code is not None:
        where["product_code"] = product_code

    quotas = await prisma_client.db.alchemi_accountquotatable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"quotas": quotas}


@router.get("/balance")
async def get_balance(
    request: Request,
    _=Depends(require_account_access),
):
    """Get balance summary for all active quotas of the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    quotas = await prisma_client.db.alchemi_accountquotatable.find_many(
        where={"account_id": account_id, "is_active": True},
    )

    balances = []
    for q in quotas:
        included = q.included or 0.0
        used = q.used or 0.0
        rollover = q.rollover_from_previous or 0.0
        available = included - used + rollover
        balances.append({
            "unit": q.unit,
            "included": included,
            "used": used,
            "available": available,
            "overage_used": q.overage_used or 0.0,
            "overage_limit": q.overage_limit or 0.0,
        })

    return {"balances": balances}


@router.post("/check")
async def check_quota(
    data: QuotaCheckRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """HOT-PATH: Check if the requested amount of credits is available."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    quota = await prisma_client.db.alchemi_accountquotatable.find_first(
        where={"account_id": account_id, "unit": data.unit, "is_active": True},
    )

    if not quota:
        return {"available": False, "remaining": 0.0}

    included = quota.included or 0.0
    used = quota.used or 0.0
    rollover = quota.rollover_from_previous or 0.0
    overage_used = quota.overage_used or 0.0
    overage_limit = quota.overage_limit or 0.0

    remaining_included = included - used + rollover
    remaining_overage = overage_limit - overage_used
    total_remaining = remaining_included + remaining_overage

    return {
        "available": total_remaining >= data.amount,
        "remaining": total_remaining,
    }


@router.post("/deduct")
async def deduct_quota(
    data: QuotaDeductRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """HOT-PATH: Deduct credits from the account quota. Excess goes to overage."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    quota = await prisma_client.db.alchemi_accountquotatable.find_first(
        where={"account_id": account_id, "unit": data.unit, "is_active": True},
    )

    if not quota:
        raise HTTPException(status_code=404, detail="No active quota found for this unit")

    included = quota.included or 0.0
    used = quota.used or 0.0
    rollover = quota.rollover_from_previous or 0.0
    overage_used = quota.overage_used or 0.0
    overage_limit = quota.overage_limit or 0.0

    remaining_included = included - used + rollover
    amount = data.amount
    new_used = used
    new_overage_used = overage_used

    if amount <= remaining_included:
        # Fully covered by included balance
        new_used = used + amount
    else:
        # Use up remaining included, put excess in overage
        new_used = used + remaining_included
        excess = amount - remaining_included
        new_overage_used = overage_used + min(excess, overage_limit - overage_used)

        if excess > (overage_limit - overage_used):
            raise HTTPException(
                status_code=400,
                detail="Insufficient quota: amount exceeds included balance and overage limit",
            )

    updated = await prisma_client.db.alchemi_accountquotatable.update(
        where={"id": quota.id},
        data={
            "used": new_used,
            "overage_used": new_overage_used,
            "updated_at": datetime.utcnow(),
        },
    )

    return updated


@router.post("/reset")
async def reset_quota(
    data: QuotaResetRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Reset a quota for a new period. Handles rollover if enabled."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    quota = await prisma_client.db.alchemi_accountquotatable.find_first(
        where={"id": data.quota_id, "account_id": account_id},
    )

    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")

    included = quota.included or 0.0
    used = quota.used or 0.0
    rollover = quota.rollover_from_previous or 0.0
    rollover_cap = quota.rollover_cap or 0.0

    new_rollover = 0.0
    if quota.rollover_enabled:
        remaining = included - used + rollover
        if remaining > 0:
            new_rollover = min(remaining, rollover_cap)

    updated = await prisma_client.db.alchemi_accountquotatable.update(
        where={"id": quota.id},
        data={
            "used": 0.0,
            "overage_used": 0.0,
            "rollover_from_previous": new_rollover,
            "period_start": data.new_period_start,
            "period_end": data.new_period_end,
            "updated_at": datetime.utcnow(),
        },
    )

    return updated


@router.put("/{quota_id}")
async def update_quota(
    quota_id: str,
    data: QuotaUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update quota fields."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accountquotatable.find_first(
        where={"id": quota_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Quota not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.subscription_id is not None:
        update_data["subscription_id"] = data.subscription_id
    if data.product_code is not None:
        update_data["product_code"] = data.product_code
    if data.feature_code is not None:
        update_data["feature_code"] = data.feature_code
    if data.unit is not None:
        update_data["unit"] = data.unit
    if data.included is not None:
        update_data["included"] = data.included
    if data.used is not None:
        update_data["used"] = data.used
    if data.overage_used is not None:
        update_data["overage_used"] = data.overage_used
    if data.overage_limit is not None:
        update_data["overage_limit"] = data.overage_limit
    if data.reset_policy is not None:
        update_data["reset_policy"] = data.reset_policy
    if data.rollover_enabled is not None:
        update_data["rollover_enabled"] = data.rollover_enabled
    if data.rollover_cap is not None:
        update_data["rollover_cap"] = data.rollover_cap
    if data.rollover_from_previous is not None:
        update_data["rollover_from_previous"] = data.rollover_from_previous
    if data.period_start is not None:
        update_data["period_start"] = data.period_start
    if data.period_end is not None:
        update_data["period_end"] = data.period_end
    if data.is_active is not None:
        update_data["is_active"] = data.is_active

    quota = await prisma_client.db.alchemi_accountquotatable.update(
        where={"id": quota_id},
        data=update_data,
    )

    return quota
