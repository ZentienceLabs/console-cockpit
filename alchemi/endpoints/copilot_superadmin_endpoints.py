"""Copilot super-admin migration endpoints.

Ports super-admin management semantics from alchemi-admin:
- subscription/account setup -> entitlements -> quotas
- feature/platform catalogs
- config providers/models/media models
- global support ops + platform notification templates
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import append_audit_event, kv_delete, kv_get, kv_list, kv_put
from alchemi.endpoints.copilot_auth import get_actor_email_or_id, require_super_admin


router = APIRouter(
    prefix="/copilot/super-admin",
    tags=["Copilot Super Admin"],
    dependencies=[Depends(require_super_admin)],
)


SOURCE_PRIORITY = {
    "PLAN": 1,
    "ADDON": 2,
    "TRIAL": 3,
    "PROMOTION": 4,
    "SUPER_ADMIN": 5,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches_text_filter(value: Optional[str], q: Optional[str]) -> bool:
    if q is None:
        return True
    return q.lower() in str(value or "").lower()


def _matches_optional(value: Optional[str], expected: Optional[str]) -> bool:
    if expected is None:
        return True
    return (value or "") == expected


async def _audit(
    request: Request,
    event_type: str,
    data: Dict[str, Any],
    account_id: Optional[str] = None,
) -> None:
    target_account = account_id or "global"
    await append_audit_event(
        target_account,
        {
            "account_id": target_account,
            "event_type": event_type,
            "actor": get_actor_email_or_id(request),
            "data": data,
        },
    )


class SubscriptionPlanIn(BaseModel):
    name: str
    system_plan_id: str
    base_price: float = 0.0
    description: Optional[str] = None
    billing_period: str = "MONTHLY"
    plan_type: str = "BASE"
    modules: Dict[str, Any] = Field(default_factory=dict)
    trial_days: int = 0
    status: str = "COMING_SOON"
    is_active: bool = True


class SubscriptionPlanPatch(BaseModel):
    name: Optional[str] = None
    system_plan_id: Optional[str] = None
    base_price: Optional[float] = None
    description: Optional[str] = None
    billing_period: Optional[str] = None
    plan_type: Optional[str] = None
    modules: Optional[Dict[str, Any]] = None
    trial_days: Optional[int] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class AccountSubscriptionIn(BaseModel):
    plan_id: str
    system_subscription_id: Optional[str] = None
    quantity: int = 1
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: bool = True
    status: str = "ACTIVE"
    payment_response: Dict[str, Any] = Field(default_factory=dict)


class EntitlementIn(BaseModel):
    entitlement_id: Optional[str] = None
    subscription_id: Optional[str] = None
    product_code: str
    feature_code: Optional[str] = None
    entity_code: Optional[str] = None
    source: str = "PLAN"
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None


class EntitlementPatch(BaseModel):
    source: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None


class QuotaIn(BaseModel):
    quota_id: Optional[str] = None
    subscription_id: Optional[str] = None
    product_code: str
    feature_code: Optional[str] = None
    unit: str = "CREDITS"
    included: float
    used: float = 0.0
    overage_used: float = 0.0
    overage_limit: float = 0.0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    is_active: bool = True


class QuotaPatch(BaseModel):
    included: Optional[float] = None
    used: Optional[float] = None
    overage_used: Optional[float] = None
    overage_limit: Optional[float] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    is_active: Optional[bool] = None


class QuotaUsageIn(BaseModel):
    amount: float


class QuotaResetIn(BaseModel):
    period_start: str
    period_end: str
    included: Optional[float] = None


class AccountSetupIn(BaseModel):
    subscription: AccountSubscriptionIn
    entitlements: List[EntitlementIn] = Field(default_factory=list)
    quotas: List[QuotaIn] = Field(default_factory=list)


class FeatureCatalogIn(BaseModel):
    product_code: str
    feature_code: Optional[str] = None
    entity_code: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: str
    default_config: Dict[str, Any] = Field(default_factory=dict)
    plan_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class FeatureCatalogPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    default_config: Optional[Dict[str, Any]] = None
    plan_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class PlatformCatalogIn(BaseModel):
    code: str
    name: str
    category: str
    parent_code: Optional[str] = None
    value_config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    display_order: int = 0


class PlatformCatalogPatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    parent_code: Optional[str] = None
    value_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class ConfigProviderIn(BaseModel):
    id: str
    name: str
    display_label: str
    endpoint_env_var: Optional[str] = None
    api_key_env_var: Optional[str] = None
    is_active: bool = True


class ConfigProviderPatch(BaseModel):
    name: Optional[str] = None
    display_label: Optional[str] = None
    endpoint_env_var: Optional[str] = None
    api_key_env_var: Optional[str] = None
    is_active: Optional[bool] = None


class ConfigModelIn(BaseModel):
    id: str
    provider_id: str
    deployment_name: str
    display_name: str
    capability: str
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0
    content_capabilities: Dict[str, Any] = Field(default_factory=dict)
    extra_body: Dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    is_active: bool = True


class ConfigModelPatch(BaseModel):
    provider_id: Optional[str] = None
    deployment_name: Optional[str] = None
    display_name: Optional[str] = None
    capability: Optional[str] = None
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    content_capabilities: Optional[Dict[str, Any]] = None
    extra_body: Optional[Dict[str, Any]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ConfigMediaModelIn(BaseModel):
    id: str
    model_id: str
    provider_id: Optional[str] = None
    display_name: Optional[str] = None
    model_type: str
    description: Optional[str] = None
    is_active: bool = True


class ConfigMediaModelPatch(BaseModel):
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    display_name: Optional[str] = None
    model_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PlatformTemplateIn(BaseModel):
    key: str
    channel: str = "email"
    subject_template: Optional[str] = None
    body_template: str
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlatformTemplatePatch(BaseModel):
    channel: Optional[str] = None
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class BulkTicketUpdateIn(BaseModel):
    ticket_ids: List[str]
    status: Optional[str] = None
    assignee: Optional[str] = None
    resolution: Optional[str] = None


@router.get("/subscription-plans")
async def list_subscription_plans(
    request: Request,
    name: Optional[str] = Query(default=None),
    system_plan_id: Optional[str] = Query(default=None),
    product_code: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    status: Optional[str] = Query(default=None),
    plan_type: Optional[str] = Query(default=None),
):
    rows = await kv_list("sa-subscription-plan")
    items = [r["value"] for r in rows]

    def _matches(item: Dict[str, Any]) -> bool:
        if not _matches_text_filter(item.get("name"), name):
            return False
        if not _matches_optional(item.get("system_plan_id"), system_plan_id):
            return False
        if is_active is not None and bool(item.get("is_active")) != is_active:
            return False
        if not _matches_optional(item.get("status"), status):
            return False
        if not _matches_optional(item.get("plan_type"), plan_type):
            return False
        if product_code and product_code not in (item.get("modules") or {}):
            return False
        return True

    filtered = [i for i in items if _matches(i)]
    filtered.sort(key=lambda x: (x.get("base_price") or 0.0, x.get("name") or ""))
    return {"items": filtered, "total": len(filtered)}


@router.post("/subscription-plans")
async def create_subscription_plan(body: SubscriptionPlanIn, request: Request):
    plan_id = str(uuid.uuid4())
    now = _now_iso()
    payload = {
        "plan_id": plan_id,
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-subscription-plan", payload, object_id=plan_id)
    await _audit(request, "copilot.super_admin.subscription_plan.create", {"plan_id": plan_id})
    return {"item": payload}


@router.get("/subscription-plans/{plan_id}")
async def get_subscription_plan(plan_id: str, request: Request):
    row = await kv_get("sa-subscription-plan", object_id=plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    return {"item": row["value"]}


@router.put("/subscription-plans/{plan_id}")
async def update_subscription_plan(plan_id: str, body: SubscriptionPlanPatch, request: Request):
    current = await get_subscription_plan(plan_id, request)
    payload = {
        **current["item"],
        **body.model_dump(exclude_none=True),
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-subscription-plan", payload, object_id=plan_id)
    await _audit(request, "copilot.super_admin.subscription_plan.update", {"plan_id": plan_id})
    return {"item": payload}


@router.delete("/subscription-plans/{plan_id}")
async def delete_subscription_plan(plan_id: str, request: Request):
    current = await get_subscription_plan(plan_id, request)
    payload = {
        **current["item"],
        "is_active": False,
        "status": "INACTIVE",
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-subscription-plan", payload, object_id=plan_id)
    await _audit(request, "copilot.super_admin.subscription_plan.deactivate", {"plan_id": plan_id})
    return {"deleted": True}


@router.get("/accounts/{account_id}/setup")
async def get_account_setup(account_id: str, request: Request):
    subscription = await kv_get("sa-account-subscription", account_id=account_id, object_id="current")
    entitlements = [r["value"] for r in await kv_list("sa-account-entitlement", account_id=account_id)]
    quotas = [r["value"] for r in await kv_list("sa-account-quota", account_id=account_id)]

    entitlements.sort(key=lambda x: (x.get("product_code") or "", x.get("feature_code") or "", x.get("entity_code") or ""))
    quotas.sort(key=lambda x: (x.get("product_code") or "", x.get("feature_code") or "", x.get("unit") or ""))

    return {
        "account_id": account_id,
        "subscription": (subscription or {}).get("value"),
        "entitlements": entitlements,
        "quotas": quotas,
    }


@router.put("/accounts/{account_id}/setup")
async def upsert_account_setup(
    account_id: str,
    body: AccountSetupIn,
    request: Request,
    replace_existing: bool = Query(default=True),
):
    now = _now_iso()
    actor = get_actor_email_or_id(request)

    plan = await kv_get("sa-subscription-plan", object_id=body.subscription.plan_id)
    if plan is None:
        raise HTTPException(status_code=400, detail="subscription.plan_id does not exist")

    subscription_payload = {
        "account_id": account_id,
        "subscription_id": str(uuid.uuid4()),
        **body.subscription.model_dump(),
        "start_date": body.subscription.start_date or now,
        "end_date": body.subscription.end_date,
        "updated_at": now,
        "updated_by": actor,
        "created_at": now,
        "created_by": actor,
    }
    await kv_put("sa-account-subscription", subscription_payload, account_id=account_id, object_id="current")

    existing_entitlement_rows = await kv_list("sa-account-entitlement", account_id=account_id)
    existing_entitlement_ids = {str(r["value"].get("entitlement_id")) for r in existing_entitlement_rows}
    incoming_entitlement_ids: set[str] = set()

    for ent in body.entitlements:
        ent_id = ent.entitlement_id or str(uuid.uuid4())
        incoming_entitlement_ids.add(ent_id)
        payload = {
            "entitlement_id": ent_id,
            "account_id": account_id,
            "subscription_id": ent.subscription_id or subscription_payload["subscription_id"],
            **ent.model_dump(exclude={"entitlement_id", "subscription_id"}),
            "valid_from": ent.valid_from or now,
            "updated_at": now,
            "updated_by": actor,
        }
        await kv_put("sa-account-entitlement", payload, account_id=account_id, object_id=ent_id)

    if replace_existing:
        stale_ids = existing_entitlement_ids.difference(incoming_entitlement_ids)
        for stale_id in stale_ids:
            await kv_delete("sa-account-entitlement", account_id=account_id, object_id=stale_id)

    existing_quota_rows = await kv_list("sa-account-quota", account_id=account_id)
    existing_quota_ids = {str(r["value"].get("quota_id")) for r in existing_quota_rows}
    incoming_quota_ids: set[str] = set()

    for quota in body.quotas:
        quota_id = quota.quota_id or str(uuid.uuid4())
        incoming_quota_ids.add(quota_id)
        payload = {
            "quota_id": quota_id,
            "account_id": account_id,
            "subscription_id": quota.subscription_id or subscription_payload["subscription_id"],
            **quota.model_dump(exclude={"quota_id", "subscription_id"}),
            "period_start": quota.period_start or now,
            "period_end": quota.period_end or now,
            "updated_at": now,
            "updated_by": actor,
        }
        await kv_put("sa-account-quota", payload, account_id=account_id, object_id=quota_id)

    if replace_existing:
        stale_ids = existing_quota_ids.difference(incoming_quota_ids)
        for stale_id in stale_ids:
            await kv_delete("sa-account-quota", account_id=account_id, object_id=stale_id)

    await _audit(
        request,
        "copilot.super_admin.account.setup.upsert",
        {
            "account_id": account_id,
            "plan_id": body.subscription.plan_id,
            "entitlements": len(body.entitlements),
            "quotas": len(body.quotas),
            "replace_existing": replace_existing,
        },
        account_id=account_id,
    )

    return await get_account_setup(account_id, request)


@router.get("/accounts/{account_id}/entitlements")
async def list_account_entitlements(
    account_id: str,
    request: Request,
    product_code: Optional[str] = Query(default=None),
    feature_code: Optional[str] = Query(default=None),
    entity_code: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    enabled: Optional[bool] = Query(default=None),
    include_expired: bool = Query(default=False),
):
    now = datetime.now(timezone.utc)
    rows = await kv_list("sa-account-entitlement", account_id=account_id)
    items = [r["value"] for r in rows]

    def _valid(item: Dict[str, Any]) -> bool:
        if not include_expired:
            valid_from = item.get("valid_from")
            valid_until = item.get("valid_until")
            if valid_from:
                try:
                    if datetime.fromisoformat(str(valid_from).replace("Z", "+00:00")) > now:
                        return False
                except Exception:
                    pass
            if valid_until:
                try:
                    if datetime.fromisoformat(str(valid_until).replace("Z", "+00:00")) <= now:
                        return False
                except Exception:
                    pass
        return True

    filtered = []
    for item in items:
        if not _matches_optional(item.get("product_code"), product_code):
            continue
        if not _matches_optional(item.get("feature_code"), feature_code):
            continue
        if not _matches_optional(item.get("entity_code"), entity_code):
            continue
        if not _matches_optional(item.get("source"), source):
            continue
        if enabled is not None and bool(item.get("enabled", False)) != enabled:
            continue
        if not _valid(item):
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: (x.get("product_code") or "", x.get("feature_code") or "", x.get("entity_code") or ""))
    return {"items": filtered, "total": len(filtered)}


@router.post("/accounts/{account_id}/entitlements")
async def create_account_entitlement(account_id: str, body: EntitlementIn, request: Request):
    now = _now_iso()
    ent_id = body.entitlement_id or str(uuid.uuid4())
    payload = {
        "entitlement_id": ent_id,
        "account_id": account_id,
        **body.model_dump(exclude={"entitlement_id"}),
        "valid_from": body.valid_from or now,
        "updated_at": now,
        "updated_by": get_actor_email_or_id(request),
        "created_at": now,
        "created_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-account-entitlement", payload, account_id=account_id, object_id=ent_id)
    await _audit(
        request,
        "copilot.super_admin.entitlement.create",
        {"account_id": account_id, "entitlement_id": ent_id},
        account_id=account_id,
    )
    return {"item": payload}


@router.put("/accounts/{account_id}/entitlements/{entitlement_id}")
async def update_account_entitlement(
    account_id: str,
    entitlement_id: str,
    body: EntitlementPatch,
    request: Request,
):
    row = await kv_get("sa-account-entitlement", account_id=account_id, object_id=entitlement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Entitlement not found")

    payload = {
        **row["value"],
        **body.model_dump(exclude_none=True),
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-account-entitlement", payload, account_id=account_id, object_id=entitlement_id)
    await _audit(
        request,
        "copilot.super_admin.entitlement.update",
        {"account_id": account_id, "entitlement_id": entitlement_id},
        account_id=account_id,
    )
    return {"item": payload}


@router.delete("/accounts/{account_id}/entitlements/{entitlement_id}")
async def delete_account_entitlement(account_id: str, entitlement_id: str, request: Request):
    deleted = await kv_delete("sa-account-entitlement", account_id=account_id, object_id=entitlement_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entitlement not found")
    await _audit(
        request,
        "copilot.super_admin.entitlement.delete",
        {"account_id": account_id, "entitlement_id": entitlement_id},
        account_id=account_id,
    )
    return {"deleted": True}


@router.get("/accounts/{account_id}/entitlements/effective-config")
async def get_effective_entitlement_config(
    account_id: str,
    request: Request,
    product_code: str = Query(...),
    feature_code: Optional[str] = Query(default=None),
):
    # Baseline from feature catalog default config.
    catalog_rows = await kv_list("sa-feature-catalog")
    base_config: Dict[str, Any] = {}
    for row in catalog_rows:
        item = row["value"]
        if item.get("product_code") != product_code:
            continue
        if (item.get("feature_code") or None) != (feature_code or None):
            continue
        base_config = dict(item.get("default_config") or {})
        break

    ent_rows = await kv_list("sa-account-entitlement", account_id=account_id)
    matched = []
    for row in ent_rows:
        ent = row["value"]
        if not ent.get("enabled", True):
            continue
        if ent.get("product_code") != product_code:
            continue
        if feature_code is not None and (ent.get("feature_code") or None) != feature_code:
            continue
        matched.append(ent)

    matched.sort(key=lambda x: SOURCE_PRIORITY.get(str(x.get("source", "PLAN")).upper(), 0))

    effective = dict(base_config)
    for ent in matched:
        effective.update(ent.get("config") or {})

    return {
        "account_id": account_id,
        "product_code": product_code,
        "feature_code": feature_code,
        "base_config": base_config,
        "effective_config": effective,
        "sources": [
            {
                "entitlement_id": e.get("entitlement_id"),
                "source": e.get("source"),
                "config": e.get("config") or {},
            }
            for e in matched
        ],
    }


@router.get("/accounts/{account_id}/quotas")
async def list_account_quotas(
    account_id: str,
    request: Request,
    product_code: Optional[str] = Query(default=None),
    feature_code: Optional[str] = Query(default=None),
    unit: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
):
    rows = await kv_list("sa-account-quota", account_id=account_id)
    items = [r["value"] for r in rows]
    filtered = []
    for item in items:
        if not _matches_optional(item.get("product_code"), product_code):
            continue
        if not _matches_optional(item.get("feature_code"), feature_code):
            continue
        if not _matches_optional(item.get("unit"), unit):
            continue
        if is_active is not None and bool(item.get("is_active", False)) != is_active:
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: (x.get("product_code") or "", x.get("feature_code") or "", x.get("unit") or ""))
    return {"items": filtered, "total": len(filtered)}


@router.post("/accounts/{account_id}/quotas")
async def create_account_quota(account_id: str, body: QuotaIn, request: Request):
    now = _now_iso()
    quota_id = body.quota_id or str(uuid.uuid4())
    payload = {
        "quota_id": quota_id,
        "account_id": account_id,
        **body.model_dump(exclude={"quota_id"}),
        "period_start": body.period_start or now,
        "period_end": body.period_end or now,
        "updated_at": now,
        "updated_by": get_actor_email_or_id(request),
        "created_at": now,
        "created_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-account-quota", payload, account_id=account_id, object_id=quota_id)
    await _audit(
        request,
        "copilot.super_admin.quota.create",
        {"account_id": account_id, "quota_id": quota_id},
        account_id=account_id,
    )
    return {"item": payload}


@router.put("/accounts/{account_id}/quotas/{quota_id}")
async def update_account_quota(account_id: str, quota_id: str, body: QuotaPatch, request: Request):
    row = await kv_get("sa-account-quota", account_id=account_id, object_id=quota_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Quota not found")

    payload = {
        **row["value"],
        **body.model_dump(exclude_none=True),
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-account-quota", payload, account_id=account_id, object_id=quota_id)
    await _audit(
        request,
        "copilot.super_admin.quota.update",
        {"account_id": account_id, "quota_id": quota_id},
        account_id=account_id,
    )
    return {"item": payload}


@router.post("/accounts/{account_id}/quotas/{quota_id}/usage")
async def record_quota_usage(
    account_id: str,
    quota_id: str,
    body: QuotaUsageIn,
    request: Request,
):
    row = await kv_get("sa-account-quota", account_id=account_id, object_id=quota_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Quota not found")

    current = row["value"]
    included = float(current.get("included") or 0.0)
    used = float(current.get("used") or 0.0)
    overage_used = float(current.get("overage_used") or 0.0)

    amount = float(body.amount)
    remaining = max(0.0, included - used)
    if amount <= remaining:
        used += amount
    else:
        used = included
        overage_used += amount - remaining

    payload = {
        **current,
        "used": used,
        "overage_used": overage_used,
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-account-quota", payload, account_id=account_id, object_id=quota_id)
    await _audit(
        request,
        "copilot.super_admin.quota.usage.record",
        {"account_id": account_id, "quota_id": quota_id, "amount": amount},
        account_id=account_id,
    )
    return {"item": payload}


@router.post("/accounts/{account_id}/quotas/{quota_id}/reset")
async def reset_quota_period(
    account_id: str,
    quota_id: str,
    body: QuotaResetIn,
    request: Request,
):
    row = await kv_get("sa-account-quota", account_id=account_id, object_id=quota_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Quota not found")

    current = row["value"]
    payload = {
        **current,
        "period_start": body.period_start,
        "period_end": body.period_end,
        "included": body.included if body.included is not None else current.get("included"),
        "used": 0.0,
        "overage_used": 0.0,
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-account-quota", payload, account_id=account_id, object_id=quota_id)
    await _audit(
        request,
        "copilot.super_admin.quota.reset",
        {"account_id": account_id, "quota_id": quota_id},
        account_id=account_id,
    )
    return {"item": payload}


@router.delete("/accounts/{account_id}/quotas/{quota_id}")
async def delete_account_quota(account_id: str, quota_id: str, request: Request):
    deleted = await kv_delete("sa-account-quota", account_id=account_id, object_id=quota_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Quota not found")
    await _audit(
        request,
        "copilot.super_admin.quota.delete",
        {"account_id": account_id, "quota_id": quota_id},
        account_id=account_id,
    )
    return {"deleted": True}


@router.get("/feature-catalog")
async def list_feature_catalog(
    request: Request,
    product_code: Optional[str] = Query(default=None),
    feature_code: Optional[str] = Query(default=None),
    entity_code: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
):
    rows = await kv_list("sa-feature-catalog")
    items = [r["value"] for r in rows]
    filtered = []
    for item in items:
        if not _matches_optional(item.get("product_code"), product_code):
            continue
        if not _matches_optional(item.get("feature_code"), feature_code):
            continue
        if not _matches_optional(item.get("entity_code"), entity_code):
            continue
        if not _matches_optional(item.get("category"), category):
            continue
        if is_active is not None and bool(item.get("is_active", False)) != is_active:
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: (x.get("product_code") or "", x.get("feature_code") or "", x.get("entity_code") or "", x.get("name") or ""))
    return {"items": filtered, "total": len(filtered)}


@router.get("/feature-catalog/hierarchy")
async def feature_catalog_hierarchy(request: Request):
    rows = [r["value"] for r in await kv_list("sa-feature-catalog") if r["value"].get("is_active", True)]
    modules = [r for r in rows if not r.get("feature_code")]

    out = []
    for module in sorted(modules, key=lambda x: x.get("name") or ""):
        module_features = [
            r for r in rows
            if r.get("product_code") == module.get("product_code") and r.get("feature_code")
            and not r.get("entity_code")
        ]
        features = []
        for feature in sorted(module_features, key=lambda x: x.get("name") or ""):
            entities = [
                r for r in rows
                if r.get("product_code") == module.get("product_code")
                and r.get("feature_code") == feature.get("feature_code")
                and r.get("entity_code")
            ]
            features.append({
                **feature,
                "entities": sorted(entities, key=lambda x: x.get("name") or ""),
            })

        out.append({
            **module,
            "features": features,
        })

    return {"modules": out}


@router.post("/feature-catalog")
async def create_feature_catalog_item(body: FeatureCatalogIn, request: Request):
    entry_id = str(uuid.uuid4())
    now = _now_iso()
    payload = {
        "entry_id": entry_id,
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-feature-catalog", payload, object_id=entry_id)
    await _audit(request, "copilot.super_admin.feature_catalog.create", {"entry_id": entry_id})
    return {"item": payload}


@router.get("/feature-catalog/{entry_id}")
async def get_feature_catalog_item(entry_id: str, request: Request):
    row = await kv_get("sa-feature-catalog", object_id=entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Feature catalog entry not found")
    return {"item": row["value"]}


@router.put("/feature-catalog/{entry_id}")
async def update_feature_catalog_item(entry_id: str, body: FeatureCatalogPatch, request: Request):
    current = await get_feature_catalog_item(entry_id, request)
    payload = {
        **current["item"],
        **body.model_dump(exclude_none=True),
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-feature-catalog", payload, object_id=entry_id)
    await _audit(request, "copilot.super_admin.feature_catalog.update", {"entry_id": entry_id})
    return {"item": payload}


@router.delete("/feature-catalog/{entry_id}")
async def delete_feature_catalog_item(entry_id: str, request: Request):
    deleted = await kv_delete("sa-feature-catalog", object_id=entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feature catalog entry not found")
    await _audit(request, "copilot.super_admin.feature_catalog.delete", {"entry_id": entry_id})
    return {"deleted": True}


@router.get("/platform-catalog")
async def list_platform_catalog(
    request: Request,
    code: Optional[str] = Query(default=None),
    name: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    parent_code: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
):
    rows = [r["value"] for r in await kv_list("sa-platform-catalog")]
    filtered = []
    for item in rows:
        if code and not _matches_text_filter(item.get("code"), code):
            continue
        if name and not _matches_text_filter(item.get("name"), name):
            continue
        if not _matches_optional(item.get("category"), category):
            continue
        if parent_code is not None and (item.get("parent_code") or None) != parent_code:
            continue
        if is_active is not None and bool(item.get("is_active", False)) != is_active:
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: (x.get("display_order") or 0, x.get("name") or ""))
    return {"items": filtered, "total": len(filtered)}


@router.get("/platform-catalog/hierarchy")
async def platform_catalog_hierarchy(request: Request):
    rows = [r["value"] for r in await kv_list("sa-platform-catalog") if r["value"].get("is_active", True)]
    modules = [r for r in rows if str(r.get("category", "")).upper() == "MODULE"]

    out = []
    for module in sorted(modules, key=lambda x: (x.get("display_order") or 0, x.get("name") or "")):
        features = [
            r for r in rows
            if str(r.get("category", "")).upper() == "FEATURE"
            and (r.get("parent_code") or None) == module.get("code")
        ]
        feature_items = []
        for feature in sorted(features, key=lambda x: (x.get("display_order") or 0, x.get("name") or "")):
            entities = [
                r for r in rows
                if str(r.get("category", "")).upper() == "ENTITY"
                and (r.get("parent_code") or None) == feature.get("code")
            ]
            feature_items.append({
                **feature,
                "entities": sorted(entities, key=lambda x: (x.get("display_order") or 0, x.get("name") or "")),
            })

        out.append({
            **module,
            "features": feature_items,
        })

    return {"modules": out}


@router.post("/platform-catalog")
async def create_platform_catalog_item(body: PlatformCatalogIn, request: Request):
    now = _now_iso()
    payload = {
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-platform-catalog", payload, object_id=body.code)
    await _audit(request, "copilot.super_admin.platform_catalog.create", {"code": body.code})
    return {"item": payload}


@router.get("/platform-catalog/{code}")
async def get_platform_catalog_item(code: str, request: Request):
    row = await kv_get("sa-platform-catalog", object_id=code)
    if row is None:
        raise HTTPException(status_code=404, detail="Platform catalog entry not found")
    return {"item": row["value"]}


@router.put("/platform-catalog/{code}")
async def update_platform_catalog_item(code: str, body: PlatformCatalogPatch, request: Request):
    current = await get_platform_catalog_item(code, request)
    payload = {
        **current["item"],
        **body.model_dump(exclude_none=True),
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-platform-catalog", payload, object_id=code)
    await _audit(request, "copilot.super_admin.platform_catalog.update", {"code": code})
    return {"item": payload}


@router.delete("/platform-catalog/{code}")
async def delete_platform_catalog_item(code: str, request: Request):
    deleted = await kv_delete("sa-platform-catalog", object_id=code)
    if not deleted:
        raise HTTPException(status_code=404, detail="Platform catalog entry not found")
    await _audit(request, "copilot.super_admin.platform_catalog.delete", {"code": code})
    return {"deleted": True}


@router.get("/config/providers")
async def list_config_providers(
    request: Request,
    is_active: Optional[bool] = Query(default=None),
):
    rows = [r["value"] for r in await kv_list("sa-config-provider")]
    if is_active is not None:
        rows = [r for r in rows if bool(r.get("is_active", False)) == is_active]
    rows.sort(key=lambda x: x.get("name") or x.get("id") or "")
    return {"items": rows, "total": len(rows)}


@router.post("/config/providers")
async def create_config_provider(body: ConfigProviderIn, request: Request):
    now = _now_iso()
    payload = {
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-config-provider", payload, object_id=body.id)
    await _audit(request, "copilot.super_admin.config_provider.upsert", {"provider_id": body.id})
    return {"item": payload}


@router.put("/config/providers/{provider_id}")
async def update_config_provider(provider_id: str, body: ConfigProviderPatch, request: Request):
    row = await kv_get("sa-config-provider", object_id=provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Config provider not found")

    payload = {
        **row["value"],
        **body.model_dump(exclude_none=True),
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-config-provider", payload, object_id=provider_id)
    await _audit(request, "copilot.super_admin.config_provider.update", {"provider_id": provider_id})
    return {"item": payload}


@router.delete("/config/providers/{provider_id}")
async def delete_config_provider(provider_id: str, request: Request):
    deleted = await kv_delete("sa-config-provider", object_id=provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Config provider not found")
    await _audit(request, "copilot.super_admin.config_provider.delete", {"provider_id": provider_id})
    return {"deleted": True}


@router.get("/config/models")
async def list_config_models(
    request: Request,
    provider_id: Optional[str] = Query(default=None),
    capability: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
):
    rows = [r["value"] for r in await kv_list("sa-config-model")]
    filtered = []
    for item in rows:
        if not _matches_optional(item.get("provider_id"), provider_id):
            continue
        if not _matches_optional(item.get("capability"), capability):
            continue
        if is_active is not None and bool(item.get("is_active", False)) != is_active:
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: (x.get("provider_id") or "", x.get("sort_order") or 0, x.get("display_name") or ""))
    return {"items": filtered, "total": len(filtered)}


@router.post("/config/models")
async def create_config_model(body: ConfigModelIn, request: Request):
    provider = await kv_get("sa-config-provider", object_id=body.provider_id)
    if provider is None:
        raise HTTPException(status_code=400, detail="provider_id does not exist")

    now = _now_iso()
    payload = {
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-config-model", payload, object_id=body.id)
    await _audit(request, "copilot.super_admin.config_model.upsert", {"model_id": body.id})
    return {"item": payload}


@router.put("/config/models/{model_id}")
async def update_config_model(model_id: str, body: ConfigModelPatch, request: Request):
    row = await kv_get("sa-config-model", object_id=model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Config model not found")

    patch = body.model_dump(exclude_none=True)
    if patch.get("provider_id"):
        provider = await kv_get("sa-config-provider", object_id=str(patch["provider_id"]))
        if provider is None:
            raise HTTPException(status_code=400, detail="provider_id does not exist")

    payload = {
        **row["value"],
        **patch,
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-config-model", payload, object_id=model_id)
    await _audit(request, "copilot.super_admin.config_model.update", {"model_id": model_id})
    return {"item": payload}


@router.delete("/config/models/{model_id}")
async def delete_config_model(model_id: str, request: Request):
    deleted = await kv_delete("sa-config-model", object_id=model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Config model not found")
    await _audit(request, "copilot.super_admin.config_model.delete", {"model_id": model_id})
    return {"deleted": True}


@router.get("/config/media-models")
async def list_config_media_models(
    request: Request,
    provider_id: Optional[str] = Query(default=None),
    model_type: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
):
    rows = [r["value"] for r in await kv_list("sa-config-media-model")]
    filtered = []
    for item in rows:
        if not _matches_optional(item.get("provider_id"), provider_id):
            continue
        if not _matches_optional(item.get("model_type"), model_type):
            continue
        if is_active is not None and bool(item.get("is_active", False)) != is_active:
            continue
        filtered.append(item)

    filtered.sort(key=lambda x: (x.get("provider_id") or "", x.get("model_type") or "", x.get("display_name") or x.get("model_id") or ""))
    return {"items": filtered, "total": len(filtered)}


@router.post("/config/media-models")
async def create_config_media_model(body: ConfigMediaModelIn, request: Request):
    if body.provider_id:
        provider = await kv_get("sa-config-provider", object_id=body.provider_id)
        if provider is None:
            raise HTTPException(status_code=400, detail="provider_id does not exist")

    now = _now_iso()
    payload = {
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-config-media-model", payload, object_id=body.id)
    await _audit(request, "copilot.super_admin.config_media_model.upsert", {"media_model_id": body.id})
    return {"item": payload}


@router.put("/config/media-models/{media_model_id}")
async def update_config_media_model(media_model_id: str, body: ConfigMediaModelPatch, request: Request):
    row = await kv_get("sa-config-media-model", object_id=media_model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Config media model not found")

    patch = body.model_dump(exclude_none=True)
    if patch.get("provider_id"):
        provider = await kv_get("sa-config-provider", object_id=str(patch["provider_id"]))
        if provider is None:
            raise HTTPException(status_code=400, detail="provider_id does not exist")

    payload = {
        **row["value"],
        **patch,
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-config-media-model", payload, object_id=media_model_id)
    await _audit(request, "copilot.super_admin.config_media_model.update", {"media_model_id": media_model_id})
    return {"item": payload}


@router.delete("/config/media-models/{media_model_id}")
async def delete_config_media_model(media_model_id: str, request: Request):
    deleted = await kv_delete("sa-config-media-model", object_id=media_model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Config media model not found")
    await _audit(request, "copilot.super_admin.config_media_model.delete", {"media_model_id": media_model_id})
    return {"deleted": True}


@router.get("/support/tickets")
async def list_all_support_tickets(
    request: Request,
    account_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    if account_id:
        rows = await kv_list("support-ticket", account_id=account_id)
    else:
        rows = await kv_list("support-ticket")

    items = [r["value"] for r in rows]
    if status:
        items = [i for i in items if str(i.get("status", "")).lower() == status.lower()]

    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/support/tickets/bulk-update")
async def bulk_update_support_tickets(body: BulkTicketUpdateIn, request: Request):
    if not body.ticket_ids:
        raise HTTPException(status_code=400, detail="ticket_ids is required")

    now = _now_iso()
    updated = 0
    for ticket_id in body.ticket_ids:
        row = await kv_get("support-ticket", object_id=ticket_id)
        if row is None:
            continue

        current = row["value"]
        account_id = str(current.get("account_id") or "")
        if not account_id:
            continue

        payload = {
            **current,
            "updated_at": now,
            "updated_by": get_actor_email_or_id(request),
        }
        if body.status is not None:
            payload["status"] = body.status
        if body.assignee is not None:
            payload["assignee"] = body.assignee
        if body.resolution is not None:
            payload["resolution"] = body.resolution

        await kv_put("support-ticket", payload, account_id=account_id, object_id=ticket_id)
        updated += 1

    await _audit(request, "copilot.super_admin.support.ticket.bulk_update", {"updated": updated})
    return {"updated": updated}


@router.get("/platform-notification-templates")
async def list_platform_notification_templates(
    request: Request,
):
    rows = [r["value"] for r in await kv_list("sa-platform-notification-template")]
    rows.sort(key=lambda x: x.get("key") or "")
    return {"items": rows, "total": len(rows)}


@router.post("/platform-notification-templates")
async def create_platform_notification_template(body: PlatformTemplateIn, request: Request):
    template_id = str(uuid.uuid4())
    now = _now_iso()
    payload = {
        "template_id": template_id,
        **body.model_dump(),
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-platform-notification-template", payload, object_id=template_id)
    await _audit(request, "copilot.super_admin.notification_template.create", {"template_id": template_id})
    return {"item": payload}


@router.put("/platform-notification-templates/{template_id}")
async def update_platform_notification_template(
    template_id: str,
    body: PlatformTemplatePatch,
    request: Request,
):
    row = await kv_get("sa-platform-notification-template", object_id=template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")

    payload = {
        **row["value"],
        **body.model_dump(exclude_none=True),
        "updated_at": _now_iso(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("sa-platform-notification-template", payload, object_id=template_id)
    await _audit(request, "copilot.super_admin.notification_template.update", {"template_id": template_id})
    return {"item": payload}


@router.delete("/platform-notification-templates/{template_id}")
async def delete_platform_notification_template(template_id: str, request: Request):
    deleted = await kv_delete("sa-platform-notification-template", object_id=template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    await _audit(request, "copilot.super_admin.notification_template.delete", {"template_id": template_id})
    return {"deleted": True}
