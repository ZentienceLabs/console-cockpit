"""
Copilot observability endpoints.
Provides Copilot-only alerts + audit event feeds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_auth import require_copilot_admin_access

router = APIRouter(prefix="/copilot/observability", tags=["Copilot - Observability"])


def _resolve_optional_account_filter(account_id: Optional[str]) -> Optional[str]:
    from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

    if is_super_admin():
        if account_id:
            return account_id
        return get_current_account_id()

    resolved = get_current_account_id()
    if not resolved:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return resolved


@router.get("/scim-quality")
async def get_scim_data_quality(
    request: Request,
    account_id: Optional[str] = None,
    sample_limit: int = Query(default=25, ge=1, le=200),
    _auth=Depends(require_copilot_admin_access),
):
    """
    SCIM/identity data quality checks for Copilot directory readiness.

    Highlights common issues:
    - identity users without team assignments
    - identity users referencing non-existent teams
    - teams without org mapping
    - teams mapped to non-existent orgs
    - orgs with zero teams
    """
    resolved_account_id = _resolve_optional_account_filter(account_id)
    if not resolved_account_id:
        raise HTTPException(
            status_code=400,
            detail="account_id is required when no tenant context is available.",
        )

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected.")

    users = await prisma_client.db.litellm_usertable.find_many(
        where={"account_id": resolved_account_id},
        order={"created_at": "desc"},
    )
    teams = await prisma_client.db.litellm_teamtable.find_many(
        where={"account_id": resolved_account_id},
        order={"created_at": "desc"},
    )
    orgs = await prisma_client.db.litellm_organizationtable.find_many(
        where={"account_id": resolved_account_id},
        order={"created_at": "desc"},
    )

    team_ids = {
        str(t.team_id).strip()
        for t in teams
        if str(getattr(t, "team_id", "") or "").strip()
    }
    org_ids = {
        str(o.organization_id).strip()
        for o in orgs
        if str(getattr(o, "organization_id", "") or "").strip()
    }

    users_without_teams: List[Dict[str, Any]] = []
    users_with_missing_team_refs: List[Dict[str, Any]] = []
    missing_team_ref_count = 0

    for user in users:
        user_teams = [
            str(t).strip()
            for t in (getattr(user, "teams", None) or [])
            if str(t).strip()
        ]
        if not user_teams:
            users_without_teams.append(
                {
                    "user_id": str(user.user_id),
                    "user_email": user.user_email,
                    "user_role": user.user_role,
                }
            )
            continue

        missing_refs = [t for t in user_teams if t not in team_ids]
        if missing_refs:
            missing_team_ref_count += len(missing_refs)
            users_with_missing_team_refs.append(
                {
                    "user_id": str(user.user_id),
                    "user_email": user.user_email,
                    "missing_team_ids": missing_refs,
                }
            )

    teams_without_org: List[Dict[str, Any]] = []
    teams_with_missing_org: List[Dict[str, Any]] = []
    teams_per_org: Dict[str, int] = {}

    for team in teams:
        team_id = str(team.team_id)
        org_id = str(team.organization_id or "").strip()
        if not org_id:
            teams_without_org.append(
                {
                    "team_id": team_id,
                    "team_alias": getattr(team, "team_alias", None),
                }
            )
            continue

        teams_per_org[org_id] = teams_per_org.get(org_id, 0) + 1
        if org_id not in org_ids:
            teams_with_missing_org.append(
                {
                    "team_id": team_id,
                    "team_alias": getattr(team, "team_alias", None),
                    "organization_id": org_id,
                }
            )

    orgs_without_teams: List[Dict[str, Any]] = []
    for org in orgs:
        org_id = str(org.organization_id)
        if teams_per_org.get(org_id, 0) == 0:
            orgs_without_teams.append(
                {
                    "organization_id": org_id,
                    "organization_alias": getattr(org, "organization_alias", None),
                }
            )

    score_denominator = max(1, len(users) + len(teams))
    score_penalty = (
        len(users_without_teams)
        + len(users_with_missing_team_refs)
        + len(teams_without_org)
        + len(teams_with_missing_org)
    )
    health_score = max(0.0, round(100.0 * (1.0 - (score_penalty / score_denominator)), 2))

    return {
        "data": {
            "account_id": resolved_account_id,
            "health_score": health_score,
            "counts": {
                "users_total": len(users),
                "teams_total": len(teams),
                "orgs_total": len(orgs),
                "users_without_teams": len(users_without_teams),
                "users_with_missing_team_refs": len(users_with_missing_team_refs),
                "missing_team_refs_total": missing_team_ref_count,
                "teams_without_org": len(teams_without_org),
                "teams_with_missing_org": len(teams_with_missing_org),
                "orgs_without_teams": len(orgs_without_teams),
            },
            "samples": {
                "users_without_teams": users_without_teams[:sample_limit],
                "users_with_missing_team_refs": users_with_missing_team_refs[:sample_limit],
                "teams_without_org": teams_without_org[:sample_limit],
                "teams_with_missing_org": teams_with_missing_org[:sample_limit],
                "orgs_without_teams": orgs_without_teams[:sample_limit],
            },
        }
    }


@router.get("/alerts")
async def get_copilot_alerts(
    request: Request,
    account_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = _resolve_optional_account_filter(account_id)

    if resolved_account_id:
        budget_alerts = await copilot_db.credit_budgets.execute_raw(
            "SELECT * FROM copilot.v_budget_alerts WHERE account_id = $1 ORDER BY usage_pct DESC LIMIT $2",
            resolved_account_id,
            limit,
        )
    else:
        budget_alerts = await copilot_db.credit_budgets.execute_raw(
            "SELECT * FROM copilot.v_budget_alerts ORDER BY usage_pct DESC LIMIT $1",
            limit,
        )

    guardrail_params: List[Any] = []
    guardrail_where: List[str] = []
    if resolved_account_id:
        guardrail_params.append(resolved_account_id)
        guardrail_where.append(f"account_id = ${len(guardrail_params)}")

    where_clause = f"WHERE {' AND '.join(guardrail_where)}" if guardrail_where else ""

    # Alert 1: explicit disable/delete actions in guardrail audit history.
    guardrail_audit_query = (
        "SELECT id::text AS id, account_id, guard_type, action, changed_by, changed_at, "
        "'audit_action'::text AS alert_type "
        "FROM copilot.guardrails_audit_log "
        f"{where_clause} "
        f"{'AND' if where_clause else 'WHERE'} action IN ('disable','delete') "
        "ORDER BY changed_at DESC "
        f"LIMIT ${len(guardrail_params) + 1}"
    )
    guardrail_audit_alerts = await copilot_db.guardrails_audit_log.execute_raw(
        guardrail_audit_query,
        *guardrail_params,
        limit,
    )

    # Alert 2: currently disabled guardrails in active config state.
    disabled_guard_params = list(guardrail_params)
    disabled_where = list(guardrail_where)
    disabled_where.append("enabled = false")
    disabled_clause = f"WHERE {' AND '.join(disabled_where)}"
    disabled_guard_query = (
        "SELECT id::text AS id, account_id, guard_type, "
        "'disabled'::text AS action, updated_by AS changed_by, updated_at AS changed_at, "
        "'disabled_state'::text AS alert_type "
        "FROM copilot.guardrails_config "
        f"{disabled_clause} "
        "ORDER BY updated_at DESC "
        f"LIMIT ${len(disabled_guard_params) + 1}"
    )
    disabled_guard_alerts = await copilot_db.guardrails_config.execute_raw(
        disabled_guard_query,
        *disabled_guard_params,
        limit,
    )

    guardrail_alerts = [*guardrail_audit_alerts, *disabled_guard_alerts]
    guardrail_alerts = sorted(
        [dict(a) for a in guardrail_alerts],
        key=lambda r: str(r.get("changed_at") or ""),
        reverse=True,
    )[:limit]

    return {
        "data": {
            "budget_alerts": [dict(r) for r in budget_alerts],
            "guardrail_alerts": guardrail_alerts,
            "counts": {
                "budget_alerts": len(budget_alerts),
                "guardrail_alerts": len(guardrail_alerts),
            },
        }
    }


@router.get("/audit")
async def list_copilot_audit_events(
    request: Request,
    account_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = _resolve_optional_account_filter(account_id)

    where_parts: List[str] = []
    params: List[Any] = []

    if resolved_account_id:
        params.append(resolved_account_id)
        where_parts.append(f"account_id = ${len(params)}")

    if event_type and event_type.strip():
        params.append(event_type.strip())
        where_parts.append(f"event_type = ${len(params)}")

    if severity and severity.strip():
        params.append(severity.strip().lower())
        where_parts.append(f"severity = ${len(params)}")

    if date_from and date_from.strip():
        params.append(datetime.fromisoformat(date_from.strip()))
        where_parts.append(f"created_at >= ${len(params)}")

    if date_to and date_to.strip():
        params.append(datetime.fromisoformat(date_to.strip()))
        where_parts.append(f"created_at <= ${len(params)}")

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    total = await copilot_db.audit_log.execute_raw_val(
        f"SELECT COUNT(*) FROM copilot.audit_log {where_clause}",
        *params,
    )

    paged_params = [*params, limit, offset]
    data = await copilot_db.audit_log.execute_raw(
        f"SELECT * FROM copilot.audit_log {where_clause} "
        f"ORDER BY created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
        *paged_params,
    )

    return {
        "data": [dict(r) for r in data],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/summary")
async def get_copilot_observability_summary(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = _resolve_optional_account_filter(account_id)

    if resolved_account_id:
        budget_alert_count = await copilot_db.credit_budgets.execute_raw_val(
            "SELECT COUNT(*) FROM copilot.v_budget_alerts WHERE account_id = $1",
            resolved_account_id,
        )
        guardrail_alert_count = await copilot_db.guardrails_audit_log.execute_raw_val(
            "SELECT COUNT(*) FROM copilot.guardrails_audit_log WHERE account_id = $1 AND action IN ('disable','delete')",
            resolved_account_id,
        )
        audit_count_7d = await copilot_db.audit_log.execute_raw_val(
            "SELECT COUNT(*) FROM copilot.audit_log WHERE account_id = $1 AND created_at >= (now() - interval '7 days')",
            resolved_account_id,
        )
    else:
        budget_alert_count = await copilot_db.credit_budgets.execute_raw_val(
            "SELECT COUNT(*) FROM copilot.v_budget_alerts"
        )
        guardrail_alert_count = await copilot_db.guardrails_audit_log.execute_raw_val(
            "SELECT COUNT(*) FROM copilot.guardrails_audit_log WHERE action IN ('disable','delete')"
        )
        audit_count_7d = await copilot_db.audit_log.execute_raw_val(
            "SELECT COUNT(*) FROM copilot.audit_log WHERE created_at >= (now() - interval '7 days')"
        )

    return {
        "data": {
            "budget_alerts": int(budget_alert_count or 0),
            "guardrail_alerts": int(guardrail_alert_count or 0),
            "audit_events_7d": int(audit_count_7d or 0),
        }
    }
