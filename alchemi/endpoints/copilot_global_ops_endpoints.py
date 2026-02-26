"""Copilot super-admin global operations endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from alchemi.db.copilot_db import kv_put
from alchemi.endpoints.copilot_auth import get_actor_email_or_id, require_super_admin
from alchemi.endpoints.copilot_helpers import as_float, require_prisma


router = APIRouter(prefix="/copilot/global-ops", tags=["Copilot Global Ops"])


class BulkModelEligibilityRequest(BaseModel):
    account_ids: List[str]
    model_codes: List[str]


class BulkCreditAllocationRequest(BaseModel):
    account_ids: List[str]
    account_allocated_credits: float
    credits_factor: float = 1.0
    cycle: str = "monthly"


@router.get("/accounts/summary")
async def accounts_summary(
    request: Request,
    _=Depends(require_super_admin),
):
    prisma = require_prisma()

    accounts = await prisma.db.alchemi_accounttable.find_many(order={"created_at": "desc"})
    spend_logs = await prisma.db.litellm_spendlogs.find_many()

    spend_by_account: Dict[str, float] = {}
    req_by_account: Dict[str, int] = {}
    for row in spend_logs:
        account_id = getattr(row, "account_id", None)
        if not account_id:
            continue
        spend_by_account[account_id] = spend_by_account.get(account_id, 0.0) + as_float(getattr(row, "spend", 0.0), 0.0)
        req_by_account[account_id] = req_by_account.get(account_id, 0) + 1

    items = []
    for account in accounts:
        account_id = account.account_id
        users = await prisma.db.litellm_usertable.count(where={"account_id": account_id})
        teams = await prisma.db.litellm_teamtable.count(where={"account_id": account_id})
        orgs = await prisma.db.litellm_organizationtable.count(where={"account_id": account_id})
        items.append(
            {
                "account_id": account_id,
                "account_name": account.account_name,
                "status": account.status,
                "users": users,
                "teams": teams,
                "organizations": orgs,
                "requests": req_by_account.get(account_id, 0),
                "spend": spend_by_account.get(account_id, 0.0),
            }
        )

    return {"items": items, "total": len(items)}


@router.post("/accounts/bulk/model-eligibility")
async def bulk_set_model_eligibility(
    body: BulkModelEligibilityRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    if not body.account_ids:
        raise HTTPException(status_code=400, detail="account_ids is required")

    now = datetime.now(timezone.utc).isoformat()
    actor = get_actor_email_or_id(request)
    for account_id in body.account_ids:
        await kv_put(
            "model-eligibility",
            {
                "account_id": account_id,
                "model_codes": body.model_codes,
                "updated_at": now,
                "updated_by": actor,
            },
            account_id=account_id,
            object_id="current",
        )

    return {"updated_accounts": len(body.account_ids)}


@router.post("/accounts/bulk/credits")
async def bulk_allocate_credits(
    body: BulkCreditAllocationRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    if not body.account_ids:
        raise HTTPException(status_code=400, detail="account_ids is required")

    now = datetime.now(timezone.utc).isoformat()
    actor = get_actor_email_or_id(request)

    for account_id in body.account_ids:
        await kv_put(
            "budget-plan",
            {
                "plan_id": "current",
                "account_id": account_id,
                "cycle": body.cycle,
                "credits_factor": body.credits_factor,
                "account_allocated_credits": body.account_allocated_credits,
                "unallocated_credits": body.account_allocated_credits,
                "unallocated_used_credits": 0.0,
                "updated_at": now,
                "updated_by": actor,
            },
            account_id=account_id,
            object_id="current",
        )

    return {"updated_accounts": len(body.account_ids)}


@router.post("/accounts/bulk/status")
async def bulk_update_account_status(
    payload: Dict[str, Any],
    request: Request,
    _=Depends(require_super_admin),
):
    account_ids = payload.get("account_ids") or []
    status = payload.get("status")
    if not account_ids or status is None:
        raise HTTPException(status_code=400, detail="account_ids and status are required")

    prisma = require_prisma()
    updated = 0
    for account_id in account_ids:
        await prisma.db.alchemi_accounttable.update(
            where={"account_id": account_id},
            data={
                "status": str(status),
                "updated_by": get_actor_email_or_id(request),
            },
        )
        updated += 1

    return {"updated_accounts": updated}
