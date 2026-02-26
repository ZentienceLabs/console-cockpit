"""Copilot observability endpoints (audit logs, alerts, rollups)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query, Request

from alchemi.db.copilot_db import kv_list
from alchemi.endpoints.copilot_auth import (
    require_account_admin_or_super_admin,
    require_account_context,
)
from alchemi.endpoints.copilot_helpers import as_float, is_copilot_meta, require_prisma


router = APIRouter(prefix="/copilot/observability", tags=["Copilot Observability"])


@router.get("/audit-logs")
async def list_copilot_audit_logs(
    request: Request,
    account_id: str = Depends(require_account_context),
    limit: int = Query(default=500, ge=1, le=5000),
    _=Depends(require_account_admin_or_super_admin),
):
    rows = await kv_list("audit-event", account_id=account_id)
    items = [r["value"] for r in rows]
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.get("/usage-rollups")
async def usage_rollups(
    request: Request,
    account_id: str = Depends(require_account_context),
    days: int = Query(default=30, ge=1, le=365),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = require_prisma()
    start = datetime.now(timezone.utc) - timedelta(days=days)

    logs = await prisma.db.litellm_spendlogs.find_many(
        where={
            "account_id": account_id,
            "startTime": {"gte": start},
        }
    )

    by_day: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "requests": 0,
            "spend": 0.0,
            "tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
    )

    for row in logs:
        key = row.startTime.date().isoformat()
        agg = by_day[key]
        agg["requests"] += 1
        agg["spend"] += as_float(getattr(row, "spend", 0.0), 0.0)
        agg["tokens"] += int(getattr(row, "total_tokens", 0) or 0)
        agg["prompt_tokens"] += int(getattr(row, "prompt_tokens", 0) or 0)
        agg["completion_tokens"] += int(getattr(row, "completion_tokens", 0) or 0)

    usage_rows = await kv_list("budget-usage", account_id=account_id)
    credits_by_day: Dict[str, float] = defaultdict(float)
    for row in usage_rows:
        value = row["value"]
        ts = value.get("recorded_at")
        if isinstance(ts, str) and len(ts) >= 10:
            day = ts[:10]
            credits_by_day[day] += as_float(value.get("credits"), 0.0)

    items = []
    for day, agg in by_day.items():
        items.append(
            {
                "date": day,
                **agg,
                "credits": credits_by_day.get(day, 0.0),
            }
        )

    items.sort(key=lambda x: x["date"], reverse=True)
    return {"items": items, "total": len(items)}


@router.get("/alerts")
async def list_alert_rollups(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    budget_alerts = []
    budget_alloc_rows = await kv_list("budget-allocation", account_id=account_id)
    for row in budget_alloc_rows:
        value = row["value"]
        allocated = as_float(value.get("allocated_credits"), 0.0)
        used = as_float(value.get("used_credits"), 0.0)
        if allocated > 0 and used / allocated >= 0.8:
            budget_alerts.append(
                {
                    "kind": "budget",
                    "scope_type": value.get("scope_type"),
                    "scope_id": value.get("scope_id"),
                    "usage_pct": used / allocated,
                }
            )

    guardrail_alerts = []
    guardrail_rows = await kv_list("guardrail-event", account_id=account_id)
    for row in guardrail_rows:
        value = row["value"]
        sev = str(value.get("severity", "")).lower()
        if sev in {"high", "critical"}:
            guardrail_alerts.append(
                {
                    "kind": "guardrail",
                    "event_id": value.get("event_id"),
                    "severity": sev,
                    "action": value.get("action"),
                    "recorded_at": value.get("recorded_at"),
                }
            )

    items = budget_alerts + guardrail_alerts
    items.sort(
        key=lambda x: x.get("recorded_at") or x.get("usage_pct") or 0,
        reverse=True,
    )
    return {
        "items": items,
        "total": len(items),
        "budget_alerts": len(budget_alerts),
        "guardrail_alerts": len(guardrail_alerts),
    }


@router.get("/summary")
async def copilot_summary(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = require_prisma()

    user_count = await prisma.db.litellm_usertable.count(where={"account_id": account_id})

    orgs = await prisma.db.litellm_organizationtable.find_many(where={"account_id": account_id})
    teams = await prisma.db.litellm_teamtable.find_many(where={"account_id": account_id})

    copilot_orgs = [o for o in orgs if is_copilot_meta(getattr(o, "metadata", None))]
    copilot_teams = [t for t in teams if is_copilot_meta(getattr(t, "metadata", None))]

    spend_logs = await prisma.db.litellm_spendlogs.find_many(where={"account_id": account_id})
    total_spend = sum(as_float(getattr(r, "spend", 0.0), 0.0) for r in spend_logs)

    budget_usage_rows = await kv_list("budget-usage", account_id=account_id)
    total_credits_used = sum(as_float(r["value"].get("credits"), 0.0) for r in budget_usage_rows)

    return {
        "item": {
            "account_id": account_id,
            "users": user_count,
            "organizations": len(copilot_orgs),
            "teams": len(copilot_teams),
            "total_spend": total_spend,
            "total_credits_used": total_credits_used,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    }
