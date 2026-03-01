"""
Legacy /alchemi/* compatibility endpoints.

These routes proxy old list-style endpoints to the new /copilot data model,
so existing clients can continue to function during migration.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_connection_endpoints import (
    _connection_management_mode,
    _connection_owner_user_id,
    _mask_secrets,
    _resolve_connection_permission,
)
from alchemi.endpoints.copilot_auth import require_copilot_read_access
from alchemi.endpoints.copilot_policy_utils import is_admin_claims

router = APIRouter(prefix="/alchemi", tags=["Alchemi Legacy Compatibility"])


def _is_active_budget(budget: Dict[str, Any], now: datetime) -> bool:
    cycle_start = budget.get("cycle_start")
    cycle_end = budget.get("cycle_end")
    if not cycle_start or not cycle_end:
        return False

    def _parse(ts: str) -> datetime:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    try:
        return _parse(cycle_start) <= now <= _parse(cycle_end)
    except Exception:
        return False


@router.get("/budget/list")
async def legacy_budget_list(
    request: Request,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
    active_only: bool = True,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    where: Dict[str, Any] = {}
    if scope_type:
        where["scope_type"] = scope_type
    if scope_id:
        where["scope_id"] = scope_id

    rows = await copilot_db.credit_budgets.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    if active_only:
        now = datetime.now(timezone.utc)
        rows = [r for r in rows if _is_active_budget(r, now)]

    total = await copilot_db.credit_budgets.count(where=where if where else None)
    return {
        "data": rows,
        "list": rows,
        "budgets": rows,
        "total": total,
    }


@router.get("/budget/plan/list")
async def legacy_budget_plan_list(
    request: Request,
    _auth=Depends(require_copilot_read_access),
):
    rows = await copilot_db.budget_plans.find_many(order_by="created_at DESC")
    return {
        "data": rows,
        "list": rows,
        "plans": rows,
        "total": len(rows),
    }


@router.get("/group/list")
async def legacy_group_list(
    request: Request,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    rows = await copilot_db.groups.find_many(order_by="created_at DESC", limit=limit, offset=offset)
    total = await copilot_db.groups.count()
    return {
        "data": rows,
        "list": rows,
        "groups": rows,
        "total": total,
    }


@router.get("/team/list")
async def legacy_team_list(
    request: Request,
    group_id: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    where: Dict[str, Any] = {}
    if group_id:
        where["group_id"] = group_id

    rows = await copilot_db.teams.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.teams.count(where=where if where else None)
    return {
        "data": rows,
        "list": rows,
        "teams": rows,
        "total": total,
    }


@router.get("/connection/list")
async def legacy_connection_list(
    request: Request,
    connection_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    where: Dict[str, Any] = {}
    if connection_type:
        where["connection_type"] = connection_type
    if is_active is not None:
        where["is_active"] = is_active

    rows = await copilot_db.account_connections.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.account_connections.count(where=where if where else None)

    if not is_admin_claims(_auth):
        actor_user_id = str((_auth or {}).get("user_id") or "").strip()
        permission_cache: Dict[str, Dict[str, Any]] = {}
        filtered: List[Dict[str, Any]] = []
        for row in rows:
            ctype = str(row.get("connection_type") or "").strip().lower()
            if ctype not in {"mcp", "openapi", "integration"}:
                continue
            if ctype not in permission_cache:
                permission_cache[ctype] = await _resolve_connection_permission(
                    account_id=str(row.get("account_id") or ""),
                    connection_type=ctype,
                    actor_claims=_auth,
                )
            permission = permission_cache[ctype]
            mgmt_mode = _connection_management_mode(row)
            owner_user_id = _connection_owner_user_id(row)
            if mgmt_mode == "self_managed":
                if (
                    actor_user_id
                    and owner_user_id == actor_user_id
                    and permission.get("permission_mode") == "self_managed_allowed"
                ):
                    filtered.append(row)
                continue
            if permission.get("allow_use_admin_connections", True):
                filtered.append(row)
        rows = filtered
        total = len(rows)

    for row in rows:
        if row.get("connection_data"):
            row["connection_data"] = _mask_secrets(row["connection_data"])
    return {
        "data": rows,
        "list": rows,
        "connections": rows,
        "total": total,
    }


@router.get("/marketplace/list")
async def legacy_marketplace_list(
    request: Request,
    entity_type: Optional[str] = None,
    marketplace_status: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    where: Dict[str, Any] = {}
    if entity_type:
        where["entity_type"] = entity_type
    if marketplace_status:
        where["marketplace_status"] = marketplace_status

    rows = await copilot_db.marketplace_items.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.marketplace_items.count(where=where if where else None)
    return {
        "data": rows,
        "list": rows,
        "marketplace": rows,
        "total": total,
    }


@router.get("/workspace/list")
async def legacy_workspace_list(
    request: Request,
    _auth=Depends(require_copilot_read_access),
):
    # Workspace management is intentionally not centralized into copilot yet.
    rows: list[dict[str, Any]] = []
    return {
        "data": rows,
        "list": rows,
        "workspaces": rows,
        "total": 0,
        "note": "Workspace management remains outside centralized copilot for now.",
    }
