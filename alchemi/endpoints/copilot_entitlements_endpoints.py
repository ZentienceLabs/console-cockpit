"""Copilot feature entitlements endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import kv_delete, kv_get, kv_list, kv_put
from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    require_account_admin_or_super_admin,
    require_account_context,
    require_super_admin,
)


router = APIRouter(prefix="/copilot/entitlements", tags=["Copilot Entitlements"])


class FeatureCatalogItem(BaseModel):
    key: str
    name: str
    description: str = ""
    enabled_by_default: bool = False


class AccountEntitlementsRequest(BaseModel):
    features: List[str] = Field(default_factory=list)


@router.get("/catalog")
async def list_feature_catalog(
    request: Request,
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("feature-catalog")
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("key") or "")
    return {"items": items, "total": len(items)}


@router.put("/catalog/{feature_key}")
async def upsert_feature_catalog_item(
    feature_key: str,
    body: FeatureCatalogItem,
    request: Request,
    _=Depends(require_super_admin),
):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        **body.model_dump(),
        "key": feature_key,
        "updated_at": now,
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("feature-catalog", payload, object_id=feature_key)
    return {"item": payload}


@router.delete("/catalog/{feature_key}")
async def delete_feature_catalog_item(
    feature_key: str,
    request: Request,
    _=Depends(require_super_admin),
):
    deleted = await kv_delete("feature-catalog", object_id=feature_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Feature not found")
    return {"deleted": True}


@router.get("/account")
async def get_account_entitlements(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("account-entitlements", account_id=account_id, object_id="current")
    if row is None:
        return {"item": {"account_id": account_id, "features": []}}
    return {"item": row["value"]}


@router.put("/account")
async def set_account_entitlements(
    body: AccountEntitlementsRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_super_admin),
):
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "account_id": account_id,
        "features": body.features,
        "updated_at": now,
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("account-entitlements", payload, account_id=account_id, object_id="current")
    return {"item": payload}
