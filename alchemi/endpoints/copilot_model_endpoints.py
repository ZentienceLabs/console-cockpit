"""Copilot model governance endpoints (catalog, eligibility, selection)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.db.copilot_db import append_audit_event, kv_get, kv_list, kv_put, kv_delete
from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    require_account_admin_or_super_admin,
    require_account_context,
    require_super_admin,
)
from alchemi.endpoints.copilot_helpers import require_prisma


router = APIRouter(prefix="/copilot/models", tags=["Copilot Models"])


class CopilotCatalogModel(BaseModel):
    code: str
    display_name: str
    provider: str
    capability: str = "chat"
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelListRequest(BaseModel):
    model_codes: List[str]


async def _catalog_items() -> List[Dict[str, Any]]:
    rows = await kv_list("model-catalog")
    return [r["value"] for r in rows]


async def _eligible_codes(account_id: str) -> List[str]:
    row = await kv_get("model-eligibility", account_id=account_id, object_id="current")
    if row is None:
        return []
    return list(row["value"].get("model_codes") or [])


async def _selected_codes(account_id: str) -> List[str]:
    row = await kv_get("model-selection", account_id=account_id, object_id="current")
    if row is None:
        return []
    return list(row["value"].get("model_codes") or [])


def _as_catalog_map(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(i.get("code")): i for i in items if i.get("code")}


@router.get("/catalog")
async def list_catalog(
    request: Request,
    _=Depends(require_account_admin_or_super_admin),
):
    items = await _catalog_items()
    items.sort(key=lambda x: x.get("display_name") or x.get("code") or "")
    return {"items": items, "total": len(items)}


@router.post("/catalog")
async def upsert_catalog_model(
    body: CopilotCatalogModel,
    request: Request,
    _=Depends(require_super_admin),
):
    payload = {
        **body.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    existing = await kv_get("model-catalog", object_id=body.code)
    if existing is None:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        payload["created_by"] = get_actor_email_or_id(request)
    else:
        payload["created_at"] = existing["value"].get("created_at")
        payload["created_by"] = existing["value"].get("created_by")

    await kv_put("model-catalog", payload, object_id=body.code)
    return {"item": payload}


@router.delete("/catalog/{model_code}")
async def delete_catalog_model(
    model_code: str,
    request: Request,
    _=Depends(require_super_admin),
):
    deleted = await kv_delete("model-catalog", object_id=model_code)
    if not deleted:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"deleted": True}


@router.get("/eligibility")
async def get_eligibility(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    codes = await _eligible_codes(account_id)
    return {"account_id": account_id, "model_codes": codes}


@router.put("/eligibility")
async def set_eligibility(
    body: ModelListRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_super_admin),
):
    payload = {
        "account_id": account_id,
        "model_codes": body.model_codes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("model-eligibility", payload, account_id=account_id, object_id="current")
    return {"item": payload}


@router.get("/selection")
async def get_selection(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    codes = await _selected_codes(account_id)
    return {"account_id": account_id, "model_codes": codes}


@router.put("/selection")
async def set_selection(
    body: ModelListRequest,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    eligible = set(await _eligible_codes(account_id))
    if eligible:
        disallowed = [m for m in body.model_codes if m not in eligible]
        if disallowed:
            raise HTTPException(
                status_code=400,
                detail=f"Model(s) not in eligible set: {', '.join(disallowed)}",
            )

    payload = {
        "account_id": account_id,
        "model_codes": body.model_codes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }
    await kv_put("model-selection", payload, account_id=account_id, object_id="current")

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.models.selection.update",
            "actor": get_actor_email_or_id(request),
            "data": payload,
        },
    )
    return {"item": payload}


@router.get("/effective")
async def get_effective_models(
    request: Request,
    account_id: str = Depends(require_account_context),
    user_id: Optional[str] = Query(default=None),
    team_id: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    _=Depends(require_account_admin_or_super_admin),
):
    catalog = _as_catalog_map(await _catalog_items())
    eligible = set(await _eligible_codes(account_id))
    selected = set(await _selected_codes(account_id))

    # Account-visible set = selected subset if configured, otherwise eligible set.
    if selected:
        visible = eligible.intersection(selected) if eligible else selected
    else:
        visible = eligible if eligible else set(catalog.keys())

    # Optional user/team/org narrowing, using built-in model lists from user/team/org rows.
    prisma = require_prisma()

    user_models: Optional[List[str]] = None
    team_models: Optional[List[str]] = None
    org_models: Optional[List[str]] = None

    if user_id:
        user_row = await prisma.db.litellm_usertable.find_unique(where={"user_id": user_id})
        if user_row and getattr(user_row, "account_id", None) == account_id and user_row.models:
            user_models = list(user_row.models)

    if team_id:
        team_row = await prisma.db.litellm_teamtable.find_unique(where={"team_id": team_id})
        if team_row and getattr(team_row, "account_id", None) == account_id and team_row.models:
            team_models = list(team_row.models)

    if organization_id:
        org_row = await prisma.db.litellm_organizationtable.find_unique(where={"organization_id": organization_id})
        if org_row and getattr(org_row, "account_id", None) == account_id and org_row.models:
            org_models = list(org_row.models)

    for model_set in [org_models, team_models, user_models]:
        if model_set:
            visible = visible.intersection(set(model_set))

    items = [catalog[code] for code in visible if code in catalog and catalog[code].get("enabled", True)]
    items.sort(key=lambda x: x.get("display_name") or x.get("code") or "")

    return {
        "items": items,
        "total": len(items),
        "resolved_from": {
            "eligible": sorted(list(eligible)),
            "selected": sorted(list(selected)),
            "user_models": user_models,
            "team_models": team_models,
            "org_models": org_models,
        },
    }
