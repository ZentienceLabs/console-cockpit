"""
Subscription plan and subscription management endpoints.
Plans are global (super admin managed), subscriptions are per-account.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access, require_super_admin

router = APIRouter(prefix="/alchemi/subscription", tags=["Subscriptions"])


# ── Request Models ───────────────────────────────────────────────────────────


class PlanCreateRequest(BaseModel):
    plan_name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None
    currency: Optional[str] = "USD"
    features: Optional[Dict[str, Any]] = None
    limits: Optional[Dict[str, Any]] = None


class PlanUpdateRequest(BaseModel):
    plan_name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None
    currency: Optional[str] = None
    features: Optional[Dict[str, Any]] = None
    limits: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class SubscriptionCreateRequest(BaseModel):
    plan_id: str
    system_subscription_id: Optional[str] = None
    quantity: Optional[int] = 1
    start_date: datetime
    end_date: Optional[datetime] = None
    razorpay_response: Optional[Dict[str, Any]] = None


class SubscriptionUpdateRequest(BaseModel):
    plan_id: Optional[str] = None
    system_subscription_id: Optional[str] = None
    quantity: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    razorpay_response: Optional[Dict[str, Any]] = None


# ── Plan Routes (super admin) ───────────────────────────────────────────────


@router.post("/plan/new")
async def create_plan(
    data: PlanCreateRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    """Create a new subscription plan (super admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # Check for duplicate plan name
    existing = await prisma_client.db.alchemi_subscriptionplantable.find_first(
        where={"plan_name": data.plan_name},
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Plan '{data.plan_name}' already exists",
        )

    now = datetime.utcnow()
    plan = await prisma_client.db.alchemi_subscriptionplantable.create(
        data={
            "id": str(uuid.uuid4()),
            "plan_name": data.plan_name,
            "display_name": data.display_name,
            "description": data.description,
            "price_monthly": data.price_monthly,
            "price_yearly": data.price_yearly,
            "currency": data.currency or "USD",
            "features": Json(data.features or {}),
            "limits": Json(data.limits or {}),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": plan.id,
        "plan_name": plan.plan_name,
        "message": "Plan created successfully",
    }


@router.get("/plan/list")
async def list_plans(
    request: Request,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    _=Depends(require_account_access),
):
    """List subscription plans. Optionally filter by active status."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    where: Dict[str, Any] = {}
    if is_active is not None:
        where["is_active"] = is_active

    plans = await prisma_client.db.alchemi_subscriptionplantable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"plans": plans}


@router.put("/plan/{plan_id}")
async def update_plan(
    plan_id: str,
    data: PlanUpdateRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    """Update a subscription plan (super admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_subscriptionplantable.find_unique(
        where={"id": plan_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.plan_name is not None:
        update_data["plan_name"] = data.plan_name
    if data.display_name is not None:
        update_data["display_name"] = data.display_name
    if data.description is not None:
        update_data["description"] = data.description
    if data.price_monthly is not None:
        update_data["price_monthly"] = data.price_monthly
    if data.price_yearly is not None:
        update_data["price_yearly"] = data.price_yearly
    if data.currency is not None:
        update_data["currency"] = data.currency
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.features is not None:
        update_data["features"] = Json(data.features)
    if data.limits is not None:
        update_data["limits"] = Json(data.limits)

    plan = await prisma_client.db.alchemi_subscriptionplantable.update(
        where={"id": plan_id},
        data=update_data,
    )

    return plan


@router.delete("/plan/{plan_id}")
async def deactivate_plan(
    plan_id: str,
    request: Request,
    _=Depends(require_super_admin),
):
    """Deactivate a subscription plan (soft delete, super admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_subscriptionplantable.find_unique(
        where={"id": plan_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found")

    await prisma_client.db.alchemi_subscriptionplantable.update(
        where={"id": plan_id},
        data={"is_active": False, "updated_at": datetime.utcnow()},
    )

    return {
        "message": f"Plan '{existing.plan_name}' deactivated",
        "id": plan_id,
    }


# ── Subscription Routes (account admin) ─────────────────────────────────────


@router.post("/new")
async def create_subscription(
    data: SubscriptionCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new subscription for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify plan exists and is active
    plan = await prisma_client.db.alchemi_subscriptionplantable.find_unique(
        where={"id": data.plan_id},
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if not plan.is_active:
        raise HTTPException(status_code=400, detail="Plan is not active")

    now = datetime.utcnow()
    subscription = await prisma_client.db.alchemi_subscriptiontable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "plan_id": data.plan_id,
            "system_subscription_id": data.system_subscription_id,
            "quantity": data.quantity or 1,
            "start_date": data.start_date,
            "end_date": data.end_date,
            "is_active": True,
            "razorpay_response": Json(data.razorpay_response) if data.razorpay_response else None,
            "created_by": account_id,
            "updated_by": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": subscription.id,
        "plan_id": subscription.plan_id,
        "message": "Subscription created successfully",
    }


@router.get("/list")
async def list_subscriptions(
    request: Request,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    _=Depends(require_account_access),
):
    """List subscriptions for the current account. Optionally filter by active status."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if is_active is not None:
        where["is_active"] = is_active

    subscriptions = await prisma_client.db.alchemi_subscriptiontable.find_many(
        where=where,
        include={"plan": True},
        order={"created_at": "desc"},
    )

    return {"subscriptions": subscriptions}


@router.get("/{subscription_id}")
async def get_subscription(
    subscription_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get subscription detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    subscription = await prisma_client.db.alchemi_subscriptiontable.find_first(
        where={"id": subscription_id, "account_id": account_id},
        include={"plan": True},
    )

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return subscription


@router.put("/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    data: SubscriptionUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a subscription."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_subscriptiontable.find_first(
        where={"id": subscription_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Subscription not found")

    update_data: Dict[str, Any] = {"updated_by": account_id, "updated_at": datetime.utcnow()}

    if data.plan_id is not None:
        # Verify new plan exists and is active
        plan = await prisma_client.db.alchemi_subscriptionplantable.find_unique(
            where={"id": data.plan_id},
        )
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        if not plan.is_active:
            raise HTTPException(status_code=400, detail="Plan is not active")
        update_data["plan_id"] = data.plan_id
    if data.system_subscription_id is not None:
        update_data["system_subscription_id"] = data.system_subscription_id
    if data.quantity is not None:
        update_data["quantity"] = data.quantity
    if data.start_date is not None:
        update_data["start_date"] = data.start_date
    if data.end_date is not None:
        update_data["end_date"] = data.end_date
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.razorpay_response is not None:
        update_data["razorpay_response"] = Json(data.razorpay_response)

    subscription = await prisma_client.db.alchemi_subscriptiontable.update(
        where={"id": subscription_id},
        data=update_data,
    )

    return subscription


@router.delete("/{subscription_id}")
async def deactivate_subscription(
    subscription_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Deactivate a subscription (soft delete)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_subscriptiontable.find_first(
        where={"id": subscription_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Subscription not found")

    await prisma_client.db.alchemi_subscriptiontable.update(
        where={"id": subscription_id},
        data={
            "is_active": False,
            "end_date": datetime.utcnow(),
            "updated_by": account_id,
            "updated_at": datetime.utcnow(),
        },
    )

    return {
        "message": "Subscription deactivated",
        "id": subscription_id,
    }
