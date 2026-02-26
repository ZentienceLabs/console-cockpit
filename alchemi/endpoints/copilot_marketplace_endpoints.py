"""Copilot marketplace endpoints for publication and assignment semantics."""

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
from alchemi.middleware.tenant_context import is_super_admin


router = APIRouter(prefix="/copilot/marketplace", tags=["Copilot Marketplace"])


class MarketplaceListingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    listing_type: str = Field(description="agent|tool|bundle")
    reference_id: str = Field(description="agent_id/tool_id/bundle_id")
    tags: List[str] = Field(default_factory=list)
    visibility: str = "account"  # account|global
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MarketplaceListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    visibility: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MarketplaceAssignmentCreate(BaseModel):
    listing_id: str
    scope_type: str = Field(description="ORG|TEAM|USER")
    scope_id: str


def _norm_scope(scope_type: str) -> str:
    v = scope_type.upper().strip()
    if v in {"ORGANIZATION", "GROUP"}:
        return "ORG"
    if v in {"ORG", "TEAM", "USER"}:
        return v
    raise HTTPException(status_code=400, detail=f"Invalid scope_type: {scope_type}")


async def _listings_for_account(account_id: str) -> List[Dict[str, Any]]:
    account_rows = await kv_list("marketplace-listing", account_id=account_id)
    items = [r["value"] for r in account_rows]

    global_rows = await kv_list("marketplace-listing")
    for row in global_rows:
        value = row["value"]
        if value.get("visibility") == "global":
            items.append(value)

    dedup: Dict[str, Dict[str, Any]] = {}
    for i in items:
        lid = str(i.get("listing_id"))
        if lid:
            dedup[lid] = i
    return list(dedup.values())


@router.get("/listings")
async def list_listings(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    items = await _listings_for_account(account_id)
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/listings")
async def create_listing(
    body: MarketplaceListingCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    listing_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    visibility = body.visibility.lower().strip()
    if visibility == "global" and not is_super_admin():
        raise HTTPException(status_code=403, detail="Only super admin can create global listings")
    if visibility not in {"account", "global"}:
        raise HTTPException(status_code=400, detail="visibility must be 'account' or 'global'")

    payload = {
        "listing_id": listing_id,
        "account_id": account_id,
        "owner_account_id": account_id,
        "title": body.title,
        "description": body.description,
        "listing_type": body.listing_type,
        "reference_id": body.reference_id,
        "tags": body.tags,
        "visibility": visibility,
        "status": "draft",
        "metadata": body.metadata,
        "created_at": now,
        "updated_at": now,
        "created_by": get_actor_email_or_id(request),
        "updated_by": get_actor_email_or_id(request),
    }

    if visibility == "global":
        await kv_put("marketplace-listing", payload, object_id=listing_id)
    else:
        await kv_put("marketplace-listing", payload, account_id=account_id, object_id=listing_id)

    return {"item": payload}


@router.put("/listings/{listing_id}")
async def update_listing(
    listing_id: str,
    body: MarketplaceListingUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("marketplace-listing", account_id=account_id, object_id=listing_id)
    global_row = await kv_get("marketplace-listing", object_id=listing_id)

    current = None
    write_global = False
    if row is not None:
        current = row["value"]
    elif global_row is not None:
        current = global_row["value"]
        write_global = True
        if not is_super_admin():
            raise HTTPException(status_code=403, detail="Only super admin can modify global listings")

    if current is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    patch = body.model_dump(exclude_none=True)
    payload = {
        **current,
        **patch,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": get_actor_email_or_id(request),
    }

    if write_global:
        await kv_put("marketplace-listing", payload, object_id=listing_id)
    else:
        await kv_put("marketplace-listing", payload, account_id=account_id, object_id=listing_id)

    return {"item": payload}


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("marketplace-listing", account_id=account_id, object_id=listing_id)
    if not deleted and is_super_admin():
        deleted = await kv_delete("marketplace-listing", object_id=listing_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Listing not found")
    return {"deleted": True}


@router.post("/listings/{listing_id}/publish")
async def publish_listing(
    listing_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    return await update_listing(
        listing_id,
        MarketplaceListingUpdate(status="published"),
        request,
        account_id,
        _,
    )


@router.post("/listings/{listing_id}/hide")
async def hide_listing(
    listing_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    return await update_listing(
        listing_id,
        MarketplaceListingUpdate(status="hidden"),
        request,
        account_id,
        _,
    )


@router.get("/assignments")
async def list_assignments(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("marketplace-assignment", account_id=account_id)
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.post("/assignments")
async def create_assignment(
    body: MarketplaceAssignmentCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    assignment_id = str(uuid.uuid4())
    listing = await kv_get("marketplace-listing", account_id=account_id, object_id=body.listing_id)
    if listing is None:
        listing = await kv_get("marketplace-listing", object_id=body.listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")

    payload = {
        "assignment_id": assignment_id,
        "account_id": account_id,
        "listing_id": body.listing_id,
        "scope_type": _norm_scope(body.scope_type),
        "scope_id": body.scope_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": get_actor_email_or_id(request),
    }
    await kv_put("marketplace-assignment", payload, account_id=account_id, object_id=assignment_id)

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.marketplace.assignment.create",
            "actor": get_actor_email_or_id(request),
            "data": payload,
        },
    )
    return {"item": payload}


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("marketplace-assignment", account_id=account_id, object_id=assignment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"deleted": True}


@router.get("/effective")
async def effective_marketplace_items(
    request: Request,
    account_id: str = Depends(require_account_context),
    user_id: Optional[str] = Query(default=None),
    team_id: Optional[str] = Query(default=None),
    organization_id: Optional[str] = Query(default=None),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("marketplace-assignment", account_id=account_id)
    assignments = [r["value"] for r in rows]

    def _match(a: Dict[str, Any]) -> bool:
        st = str(a.get("scope_type", "")).upper()
        sid = str(a.get("scope_id", ""))
        if st == "USER" and user_id and sid == str(user_id):
            return True
        if st == "TEAM" and team_id and sid == str(team_id):
            return True
        if st == "ORG" and organization_id and sid == str(organization_id):
            return True
        return False

    matched = [a for a in assignments if _match(a)]
    listing_ids = {str(a.get("listing_id")) for a in matched if a.get("listing_id")}

    listings = await _listings_for_account(account_id)
    by_id = {str(listing.get("listing_id")): listing for listing in listings}
    effective = [by_id[i] for i in listing_ids if i in by_id]
    effective.sort(key=lambda x: x.get("title") or "")

    return {"items": effective, "total": len(effective), "assignments": matched}
