"""
Credit Budget Management endpoints.
CRUD for credit budgets and budget plans, plus usage recording and hierarchical allocation.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_audit_helpers import log_copilot_audit_event
from alchemi.endpoints.copilot_auth import require_copilot_admin_access
from alchemi.endpoints.copilot_types import (
    BudgetAllocateRequest,
    BudgetAllocationStrategy,
    BudgetDistributeEqualRequest,
    BudgetPlanRenewRequest,
    BudgetRenewalCadence,
    BudgetPlanCreate,
    BudgetPlanUpdate,
    BudgetScopeType,
    BudgetUsageRecord,
    CreditBudgetCreate,
    CreditBudgetUpdate,
)

router = APIRouter(prefix="/copilot/budgets", tags=["Copilot - Credit Budgets"])


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _num_int(value, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(float(value))
    except Exception:
        return default


def _to_utc_start_of_day(value: datetime) -> datetime:
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=year, month=month)


def _resolve_cycle_bounds(
    cadence: BudgetRenewalCadence,
    renewal_day_of_month: int,
    anchor: Optional[datetime] = None,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    if cadence == BudgetRenewalCadence.MANUAL:
        return None, None

    now = _to_utc_start_of_day(anchor or datetime.now(timezone.utc))
    renewal_day = max(1, min(int(renewal_day_of_month or 1), 28))

    cycle_start = now.replace(day=renewal_day)
    if now.day < renewal_day:
        cycle_start = _add_months(cycle_start, -1)

    months = 1
    if cadence == BudgetRenewalCadence.QUARTERLY:
        months = 3
    elif cadence == BudgetRenewalCadence.YEARLY:
        months = 12

    next_cycle_start = _add_months(cycle_start, months)
    cycle_end = next_cycle_start - timedelta(seconds=1)
    return cycle_start, cycle_end


def _get_plan_distribution_defaults(distribution: Optional[dict]) -> dict:
    def _as_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    base = _as_dict(distribution)
    renewal = _as_dict(base.get("renewal_policy"))
    account_policy = _as_dict(base.get("account_policy"))
    billing = _as_dict(base.get("billing"))
    return {
        **base,
        "renewal_policy": {
            "cadence": renewal.get("cadence") or BudgetRenewalCadence.MONTHLY.value,
            "day_of_month": _num_int(renewal.get("day_of_month"), 1) or 1,
        },
        "account_policy": {
            "allocation": _num_int(account_policy.get("allocation"), 0),
            "limit_amount": _num_int(account_policy.get("limit_amount"), _num_int(account_policy.get("allocation"), 0)),
            "overflow_cap": (
                None
                if account_policy.get("overflow_cap") is None
                else _num_int(account_policy.get("overflow_cap"), 0)
            ),
        },
        "billing": {
            "overflow_billing_enabled": bool(billing.get("overflow_billing_enabled", True)),
            "overflow_billing_note": str(billing.get("overflow_billing_note") or "").strip()
            or "Overflow credits are billed separately after usage.",
        },
    }


async def _apply_budget_plan_cycle(
    account_id: str,
    plan: dict,
    *,
    cycle_anchor: Optional[datetime] = None,
    force: bool = False,
) -> Dict[str, Any]:
    distribution = _get_plan_distribution_defaults(plan.get("distribution"))
    renewal = distribution.get("renewal_policy") or {}
    account_policy = distribution.get("account_policy") or {}

    cadence_raw = str(renewal.get("cadence") or BudgetRenewalCadence.MONTHLY.value).lower()
    cadence = (
        BudgetRenewalCadence(cadence_raw)
        if cadence_raw in [c.value for c in BudgetRenewalCadence]
        else BudgetRenewalCadence.MONTHLY
    )
    cycle_start, cycle_end = _resolve_cycle_bounds(
        cadence=cadence,
        renewal_day_of_month=_num_int(renewal.get("day_of_month"), 1),
        anchor=cycle_anchor,
    )
    if not cycle_start or not cycle_end:
        raise HTTPException(
            status_code=400,
            detail="Budget plan renewal cadence is manual; explicit cycle creation is required.",
        )

    allocation = max(0, _num_int(account_policy.get("allocation"), 0))
    limit_amount = _num_int(account_policy.get("limit_amount"), allocation)
    if limit_amount <= 0:
        limit_amount = allocation
    overflow_cap = account_policy.get("overflow_cap")
    overflow_cap = None if overflow_cap is None else max(0, _num_int(overflow_cap, 0))

    existing = await _find_scope_budget_in_cycle(
        account_id,
        BudgetScopeType.ACCOUNT,
        account_id,
        cycle_start,
        cycle_end,
    )

    payload = {
        "allocated": allocation,
        "limit_amount": max(limit_amount, allocation),
        "overflow_cap": overflow_cap,
        "budget_plan_id": str(plan.get("id")),
        "allocation_strategy": BudgetAllocationStrategy.MANUAL.value,
    }

    if existing and not force:
        return {"budget": existing, "created": False, "cycle_start": cycle_start, "cycle_end": cycle_end}

    if existing and force:
        updated = await copilot_db.credit_budgets.update(str(existing.get("id")), payload)
        return {"budget": updated, "created": False, "cycle_start": cycle_start, "cycle_end": cycle_end}

    created = await copilot_db.credit_budgets.create(
        data={
            "account_id": account_id,
            "scope_type": BudgetScopeType.ACCOUNT.value,
            "scope_id": account_id,
            "cycle_start": cycle_start,
            "cycle_end": cycle_end,
            **payload,
        }
    )
    return {"budget": created, "created": True, "cycle_start": cycle_start, "cycle_end": cycle_end}


def _is_active_budget(budget: dict, now: datetime) -> bool:
    cycle_start = _parse_ts(budget.get("cycle_start"))
    cycle_end = _parse_ts(budget.get("cycle_end"))
    if not cycle_start or not cycle_end:
        return False
    return cycle_start <= now <= cycle_end


def _same_cycle(budget: dict, cycle_start: datetime, cycle_end: datetime) -> bool:
    row_start = _parse_ts(budget.get("cycle_start"))
    row_end = _parse_ts(budget.get("cycle_end"))
    if not row_start or not row_end:
        return False
    return row_start == cycle_start and row_end == cycle_end


def _latest_budget(rows: Sequence[dict]) -> Optional[dict]:
    if not rows:
        return None

    def _sort_key(row: dict):
        cycle_start = _parse_ts(row.get("cycle_start")) or datetime.min.replace(tzinfo=timezone.utc)
        updated_at = _parse_ts(row.get("updated_at")) or _parse_ts(row.get("created_at")) or datetime.min.replace(
            tzinfo=timezone.utc
        )
        return (cycle_start, updated_at)

    return sorted(rows, key=_sort_key, reverse=True)[0]


def _cycle_key(row: dict) -> Tuple[str, str, str]:
    return (
        str(row.get("account_id") or ""),
        str(row.get("cycle_start") or ""),
        str(row.get("cycle_end") or ""),
    )


def _decorate_with_unallocated(rows: Sequence[dict]) -> List[dict]:
    by_parent: Dict[str, int] = defaultdict(int)
    legacy_children_by_account_cycle: Dict[Tuple[str, str, str], int] = defaultdict(int)

    for row in rows:
        allocated = _num_int(row.get("allocated"), 0)
        parent_id = row.get("parent_budget_id")
        if parent_id:
            by_parent[str(parent_id)] += allocated
        elif str(row.get("scope_type") or "") != BudgetScopeType.ACCOUNT.value:
            legacy_children_by_account_cycle[_cycle_key(row)] += allocated

    output: List[dict] = []
    for row in rows:
        distributed = by_parent.get(str(row.get("id")), 0)
        if str(row.get("scope_type") or "") == BudgetScopeType.ACCOUNT.value:
            distributed += legacy_children_by_account_cycle.get(_cycle_key(row), 0)
        allocated = _num_int(row.get("allocated"), 0)
        enriched = dict(row)
        enriched["distributed_allocated"] = distributed
        enriched["unallocated"] = max(0, allocated - distributed)
        output.append(enriched)

    return output


def _resolve_optional_account_filter(requested_account_id: Optional[str]) -> Optional[str]:
    from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

    if is_super_admin():
        if requested_account_id:
            return requested_account_id
        return get_current_account_id()

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return account_id


def _resolve_required_account_for_write(requested_account_id: Optional[str]) -> str:
    resolved = _resolve_optional_account_filter(requested_account_id)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for this super admin write operation.",
        )
    return resolved


async def _find_scope_budget_in_cycle(
    account_id: str,
    scope_type: BudgetScopeType,
    scope_id: str,
    cycle_start: datetime,
    cycle_end: datetime,
) -> Optional[dict]:
    candidates = await copilot_db.credit_budgets.find_many(
        where={"account_id": account_id, "scope_type": scope_type.value, "scope_id": scope_id},
        order_by="updated_at DESC",
        limit=50,
    )
    exact = [row for row in candidates if _same_cycle(row, cycle_start, cycle_end)]
    return _latest_budget(exact)


async def _find_active_scope_budget(
    account_id: str,
    scope_type: BudgetScopeType,
    scope_id: str,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    now = now or datetime.now(timezone.utc)
    candidates = await copilot_db.credit_budgets.find_many(
        where={"account_id": account_id, "scope_type": scope_type.value, "scope_id": scope_id},
        order_by="updated_at DESC",
        limit=50,
    )
    active = [row for row in candidates if _is_active_budget(row, now)]
    return _latest_budget(active)


async def _resolve_team_group(account_id: str, team_id: Optional[str]) -> Optional[str]:
    if not team_id:
        return None

    # Copilot-local directory first
    team_row = await copilot_db.teams.find_by_id(str(team_id))
    if team_row and str(team_row.get("account_id") or "") == account_id:
        return str(team_row.get("group_id") or "") or None

    # Identity source fallback
    try:
        from litellm.proxy.proxy_server import prisma_client

        if prisma_client is None:
            return None

        team = await prisma_client.db.litellm_teamtable.find_first(
            where={"account_id": account_id, "team_id": str(team_id)}
        )
        if team and getattr(team, "organization_id", None):
            return str(team.organization_id)
    except Exception:
        return None

    return None


async def _resolve_user_hierarchy(account_id: str, user_id: str) -> Tuple[Optional[str], Optional[str]]:
    # Copilot-local memberships first
    try:
        memberships = await copilot_db.account_memberships.find_many(
            where={"account_id": account_id, "user_id": user_id, "is_active": True},
            order_by="updated_at DESC",
            limit=1,
        )
        if memberships:
            team_id = str(memberships[0].get("team_id") or "") or None
            group_id = await _resolve_team_group(account_id, team_id)
            return team_id, group_id
    except Exception:
        memberships = []

    # Identity source fallback
    try:
        from litellm.proxy.proxy_server import prisma_client

        if prisma_client is None:
            return None, None

        identity_user = await prisma_client.db.litellm_usertable.find_first(
            where={"account_id": account_id, "user_id": user_id}
        )
        if not identity_user:
            return None, None

        teams = getattr(identity_user, "teams", None) or []
        team_id = str(teams[0]) if len(teams) > 0 else None
        group_id = await _resolve_team_group(account_id, team_id)
        return team_id, group_id
    except Exception:
        return None, None


async def _resolve_effective_budget(
    account_id: str,
    scope_type: BudgetScopeType,
    scope_id: str,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    now = now or datetime.now(timezone.utc)

    if scope_type == BudgetScopeType.ACCOUNT:
        return await _find_active_scope_budget(account_id, BudgetScopeType.ACCOUNT, scope_id, now)

    if scope_type == BudgetScopeType.GROUP:
        direct = await _find_active_scope_budget(account_id, BudgetScopeType.GROUP, scope_id, now)
        if direct:
            return direct
        return await _find_active_scope_budget(account_id, BudgetScopeType.ACCOUNT, account_id, now)

    if scope_type == BudgetScopeType.TEAM:
        direct = await _find_active_scope_budget(account_id, BudgetScopeType.TEAM, scope_id, now)
        if direct:
            return direct
        group_id = await _resolve_team_group(account_id, scope_id)
        if group_id:
            group_budget = await _find_active_scope_budget(account_id, BudgetScopeType.GROUP, group_id, now)
            if group_budget:
                return group_budget
        return await _find_active_scope_budget(account_id, BudgetScopeType.ACCOUNT, account_id, now)

    # User hierarchy: user -> team -> group -> account
    direct = await _find_active_scope_budget(account_id, BudgetScopeType.USER, scope_id, now)
    if direct:
        return direct

    team_id, group_id = await _resolve_user_hierarchy(account_id, scope_id)
    if team_id:
        team_budget = await _find_active_scope_budget(account_id, BudgetScopeType.TEAM, team_id, now)
        if team_budget:
            return team_budget

    if group_id:
        group_budget = await _find_active_scope_budget(account_id, BudgetScopeType.GROUP, group_id, now)
        if group_budget:
            return group_budget

    return await _find_active_scope_budget(account_id, BudgetScopeType.ACCOUNT, account_id, now)


async def _resolve_parent_budget_for_cycle(
    account_id: str,
    scope_type: BudgetScopeType,
    scope_id: str,
    cycle_start: datetime,
    cycle_end: datetime,
) -> Optional[dict]:
    if scope_type == BudgetScopeType.ACCOUNT:
        return None

    # Group budgets are direct children of account budget.
    if scope_type == BudgetScopeType.GROUP:
        return await _find_scope_budget_in_cycle(
            account_id,
            BudgetScopeType.ACCOUNT,
            account_id,
            cycle_start,
            cycle_end,
        )

    # Team budgets prefer group parent for same cycle, else account.
    if scope_type == BudgetScopeType.TEAM:
        group_id = await _resolve_team_group(account_id, scope_id)
        if group_id:
            group_parent = await _find_scope_budget_in_cycle(
                account_id,
                BudgetScopeType.GROUP,
                group_id,
                cycle_start,
                cycle_end,
            )
            if group_parent:
                return group_parent
        return await _find_scope_budget_in_cycle(
            account_id,
            BudgetScopeType.ACCOUNT,
            account_id,
            cycle_start,
            cycle_end,
        )

    # User budgets prefer team -> group -> account for same cycle.
    team_id, group_id = await _resolve_user_hierarchy(account_id, scope_id)
    if team_id:
        team_parent = await _find_scope_budget_in_cycle(
            account_id,
            BudgetScopeType.TEAM,
            team_id,
            cycle_start,
            cycle_end,
        )
        if team_parent:
            return team_parent

    if group_id:
        group_parent = await _find_scope_budget_in_cycle(
            account_id,
            BudgetScopeType.GROUP,
            group_id,
            cycle_start,
            cycle_end,
        )
        if group_parent:
            return group_parent

    return await _find_scope_budget_in_cycle(
        account_id,
        BudgetScopeType.ACCOUNT,
        account_id,
        cycle_start,
        cycle_end,
    )


async def _children_for_parent(account_id: str, parent_budget: dict) -> List[dict]:
    cycle_start = _parse_ts(parent_budget.get("cycle_start"))
    cycle_end = _parse_ts(parent_budget.get("cycle_end"))
    if not cycle_start or not cycle_end:
        return []

    children = await copilot_db.credit_budgets.find_many(
        where={"account_id": account_id, "parent_budget_id": parent_budget["id"]},
        order_by="created_at DESC",
        limit=2000,
    )
    children = [row for row in children if _same_cycle(row, cycle_start, cycle_end)]

    if str(parent_budget.get("scope_type") or "") == BudgetScopeType.ACCOUNT.value:
        # Legacy compatibility: existing rows without parent relationship are considered direct account allocations.
        legacy = await copilot_db.credit_budgets.find_many(
            where={"account_id": account_id, "parent_budget_id": None},
            order_by="created_at DESC",
            limit=5000,
        )
        for row in legacy:
            if str(row.get("scope_type") or "") == BudgetScopeType.ACCOUNT.value:
                continue
            if _same_cycle(row, cycle_start, cycle_end):
                children.append(row)

    dedup: Dict[str, dict] = {}
    for child in children:
        dedup[str(child.get("id"))] = child
    return list(dedup.values())


async def _ensure_parent_capacity(
    account_id: str,
    parent_budget: dict,
    requested_allocated: int,
    exclude_budget_id: Optional[str] = None,
) -> None:
    if requested_allocated < 0:
        raise HTTPException(status_code=400, detail="allocated must be >= 0")

    children = await _children_for_parent(account_id, parent_budget)
    distributed_other = 0
    for row in children:
        row_id = str(row.get("id") or "")
        if exclude_budget_id and row_id == str(exclude_budget_id):
            continue
        distributed_other += _num_int(row.get("allocated"), 0)

    parent_allocated = _num_int(parent_budget.get("allocated"), 0)
    available = max(0, parent_allocated - distributed_other)
    if requested_allocated > available:
        raise HTTPException(
            status_code=400,
            detail=(
                "Insufficient unallocated credits on parent budget. "
                f"requested={requested_allocated}, available={available}"
            ),
        )


async def _ensure_account_capacity_for_update(account_budget: dict, requested_allocated: int) -> None:
    account_id = str(account_budget.get("account_id") or "")
    children = await _children_for_parent(account_id, account_budget)
    distributed = sum(_num_int(row.get("allocated"), 0) for row in children)

    if requested_allocated < distributed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Account allocated credits cannot be lower than already distributed credits. "
                f"distributed={distributed}, requested={requested_allocated}"
            ),
        )


async def _is_child_within_parent_scope(
    account_id: str,
    parent_budget: dict,
    child_scope_type: BudgetScopeType,
    child_scope_id: str,
) -> bool:
    parent_scope_type = str(parent_budget.get("scope_type") or "")
    parent_scope_id = str(parent_budget.get("scope_id") or "")

    if parent_scope_type == BudgetScopeType.ACCOUNT.value:
        return child_scope_type in {BudgetScopeType.GROUP, BudgetScopeType.TEAM, BudgetScopeType.USER}

    if parent_scope_type == BudgetScopeType.GROUP.value:
        if child_scope_type == BudgetScopeType.USER:
            _, group_id = await _resolve_user_hierarchy(account_id, child_scope_id)
            return bool(group_id and str(group_id) == parent_scope_id)
        if child_scope_type == BudgetScopeType.TEAM:
            group_id = await _resolve_team_group(account_id, child_scope_id)
            return bool(group_id and str(group_id) == parent_scope_id)
        return False

    if parent_scope_type == BudgetScopeType.TEAM.value:
        if child_scope_type != BudgetScopeType.USER:
            return False
        team_id, _ = await _resolve_user_hierarchy(account_id, child_scope_id)
        return bool(team_id and str(team_id) == parent_scope_id)

    return False


async def _list_user_ids_for_distribution(account_id: str, parent_budget: dict) -> List[str]:
    parent_scope_type = str(parent_budget.get("scope_type") or "")
    parent_scope_id = str(parent_budget.get("scope_id") or "")

    user_ids: Set[str] = set()

    # Copilot-local memberships
    memberships = await copilot_db.account_memberships.find_many(
        where={"account_id": account_id, "is_active": True},
        order_by="updated_at DESC",
        limit=5000,
    )

    if parent_scope_type == BudgetScopeType.ACCOUNT.value:
        for m in memberships:
            uid = str(m.get("user_id") or "")
            if uid:
                user_ids.add(uid)
    elif parent_scope_type == BudgetScopeType.TEAM.value:
        for m in memberships:
            uid = str(m.get("user_id") or "")
            tid = str(m.get("team_id") or "")
            if uid and tid == parent_scope_id:
                user_ids.add(uid)
    elif parent_scope_type == BudgetScopeType.GROUP.value:
        team_ids = {
            str(t.get("id") or "")
            for t in await copilot_db.teams.find_many(where={"account_id": account_id, "group_id": parent_scope_id}, limit=5000)
        }
        for m in memberships:
            uid = str(m.get("user_id") or "")
            tid = str(m.get("team_id") or "")
            if uid and tid and tid in team_ids:
                user_ids.add(uid)

    # Identity source memberships fallback
    try:
        from litellm.proxy.proxy_server import prisma_client

        if prisma_client is not None:
            identity_users = await prisma_client.db.litellm_usertable.find_many(
                where={"account_id": account_id},
                take=5000,
            )
            for u in identity_users:
                uid = str(getattr(u, "user_id", "") or "")
                if not uid:
                    continue
                teams = [str(t) for t in (getattr(u, "teams", None) or []) if str(t)]
                if parent_scope_type == BudgetScopeType.ACCOUNT.value:
                    user_ids.add(uid)
                elif parent_scope_type == BudgetScopeType.TEAM.value:
                    if parent_scope_id in teams:
                        user_ids.add(uid)
                elif parent_scope_type == BudgetScopeType.GROUP.value:
                    for team_id in teams:
                        group_id = await _resolve_team_group(account_id, team_id)
                        if group_id and str(group_id) == parent_scope_id:
                            user_ids.add(uid)
                            break
    except Exception:
        pass

    return sorted(user_ids)


# ============================================
# Credit Budgets - List & Create
# ============================================

@router.get("/")
async def list_budgets(
    request: Request,
    account_id: Optional[str] = None,
    scope_type: Optional[BudgetScopeType] = None,
    scope_id: Optional[str] = None,
    active_only: bool = True,
    resolve_inherited: bool = True,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_admin_access),
):
    """List credit budgets for the current account."""
    resolved_account_id = _resolve_optional_account_filter(account_id)

    where = {}
    if scope_type:
        where["scope_type"] = scope_type.value
    if scope_id:
        where["scope_id"] = scope_id
    if resolved_account_id:
        where["account_id"] = resolved_account_id

    budgets = await copilot_db.credit_budgets.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )

    if active_only:
        now = datetime.now(timezone.utc)
        budgets = [b for b in budgets if _is_active_budget(b, now)]

    budgets = _decorate_with_unallocated(budgets)

    total = await copilot_db.credit_budgets.count(where=where if where else None)

    if (
        resolve_inherited
        and scope_type is not None
        and scope_id
        and resolved_account_id
        and len(budgets) == 0
        and active_only
    ):
        effective = await _resolve_effective_budget(resolved_account_id, scope_type, scope_id)
        if effective:
            inherited = dict(_decorate_with_unallocated([effective])[0])
            inherited["is_effective_inherited"] = True
            inherited["effective_for_scope_type"] = scope_type.value
            inherited["effective_for_scope_id"] = scope_id
            budgets = [inherited]
            total = 1

    return {"data": budgets, "budgets": budgets, "total": total}


@router.post("/")
async def create_budget(
    request: Request,
    data: CreditBudgetCreate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a new credit budget."""
    resolved_account_id = _resolve_required_account_for_write(account_id)

    allocation_strategy = _enum_value(data.allocation_strategy)
    if data.scope_type == BudgetScopeType.ACCOUNT:
        allocation_strategy = BudgetAllocationStrategy.MANUAL.value

    parent_budget_id = data.parent_budget_id
    parent_budget = None

    if data.scope_type != BudgetScopeType.ACCOUNT:
        if parent_budget_id:
            parent_budget = await copilot_db.credit_budgets.find_by_id(parent_budget_id)
            if not parent_budget:
                raise HTTPException(status_code=404, detail="Parent budget not found.")
            if str(parent_budget.get("account_id") or "") != resolved_account_id:
                raise HTTPException(status_code=403, detail="Parent budget belongs to a different account.")
        else:
            parent_budget = await _resolve_parent_budget_for_cycle(
                resolved_account_id,
                data.scope_type,
                data.scope_id,
                data.cycle_start,
                data.cycle_end,
            )

        if not parent_budget:
            raise HTTPException(
                status_code=400,
                detail="No parent budget found for this scope and cycle. Create account/group/team parent budget first.",
            )

        if not await _is_child_within_parent_scope(
            resolved_account_id,
            parent_budget,
            data.scope_type,
            data.scope_id,
        ):
            raise HTTPException(status_code=400, detail="Target scope is not within the selected parent scope.")

        await _ensure_parent_capacity(
            resolved_account_id,
            parent_budget,
            _num_int(data.allocated, 0),
        )
        parent_budget_id = str(parent_budget.get("id"))

    budget = await copilot_db.credit_budgets.create(
        data={
            "account_id": resolved_account_id,
            "scope_type": data.scope_type.value,
            "scope_id": data.scope_id,
            "allocated": data.allocated,
            "limit_amount": data.limit_amount,
            "overflow_cap": data.overflow_cap,
            "cycle_start": data.cycle_start,
            "cycle_end": data.cycle_end,
            "budget_plan_id": data.budget_plan_id,
            "parent_budget_id": parent_budget_id,
            "allocation_strategy": allocation_strategy,
        }
    )
    await log_copilot_audit_event(
        account_id=resolved_account_id,
        event_type="copilot_budget",
        resource_type="credit_budget",
        resource_id=str(budget.get("id") or ""),
        action="create",
        message=f"Created budget for scope {data.scope_type.value}:{data.scope_id}.",
        details={
            "scope_type": data.scope_type.value,
            "scope_id": data.scope_id,
            "allocated": data.allocated,
            "limit_amount": data.limit_amount,
        },
        request=request,
    )
    budget = _decorate_with_unallocated([budget])[0]
    return {"data": budget}


# ============================================
# Fixed-path routes (must be before /{budget_id})
# ============================================

@router.get("/allocation-overview")
async def budget_allocation_overview(
    request: Request,
    account_id: Optional[str] = None,
    active_only: bool = True,
    _auth=Depends(require_copilot_admin_access),
):
    """Get hierarchical allocation overview including account unallocated credits."""
    resolved_account_id = _resolve_optional_account_filter(account_id)
    if not resolved_account_id:
        raise HTTPException(status_code=400, detail="account_id is required.")

    rows = await copilot_db.credit_budgets.find_many(
        where={"account_id": resolved_account_id},
        order_by="created_at DESC",
        limit=5000,
    )
    if active_only:
        now = datetime.now(timezone.utc)
        rows = [r for r in rows if _is_active_budget(r, now)]

    rows = _decorate_with_unallocated(rows)

    account_budget = _latest_budget(
        [r for r in rows if str(r.get("scope_type") or "") == BudgetScopeType.ACCOUNT.value and str(r.get("scope_id") or "") == resolved_account_id]
    )
    parent_rows = [
        r
        for r in rows
        if str(r.get("scope_type") or "")
        in {BudgetScopeType.ACCOUNT.value, BudgetScopeType.GROUP.value, BudgetScopeType.TEAM.value}
    ]
    child_rows = [r for r in rows if str(r.get("scope_type") or "") == BudgetScopeType.USER.value]

    return {
        "data": {
            "account_budget": account_budget,
            "parent_budgets": parent_rows,
            "user_budgets": child_rows,
            "all_budgets": rows,
        }
    }


@router.post("/{budget_id}/allocate")
async def allocate_from_budget(
    budget_id: str,
    data: BudgetAllocateRequest,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Allocate credits from a parent budget to group/team/user within the same cycle."""
    parent_budget = await copilot_db.credit_budgets.find_by_id(budget_id)
    if not parent_budget:
        raise HTTPException(status_code=404, detail="Parent budget not found.")

    parent_scope_type = str(parent_budget.get("scope_type") or "")
    if parent_scope_type == BudgetScopeType.USER.value:
        raise HTTPException(status_code=400, detail="User budget cannot have child allocations.")

    if data.target_scope_type == BudgetScopeType.ACCOUNT:
        raise HTTPException(status_code=400, detail="Cannot allocate account scope from a parent budget.")

    if not await _is_child_within_parent_scope(
        str(parent_budget.get("account_id") or ""),
        parent_budget,
        data.target_scope_type,
        data.target_scope_id,
    ):
        raise HTTPException(status_code=400, detail="Target scope is not within parent scope.")

    cycle_start = _parse_ts(parent_budget.get("cycle_start"))
    cycle_end = _parse_ts(parent_budget.get("cycle_end"))
    if not cycle_start or not cycle_end:
        raise HTTPException(status_code=400, detail="Parent budget cycle is invalid.")

    account_id = str(parent_budget.get("account_id") or "")
    existing = await _find_scope_budget_in_cycle(
        account_id,
        data.target_scope_type,
        data.target_scope_id,
        cycle_start,
        cycle_end,
    )

    requested_allocated = _num_int(data.allocated, 0)
    await _ensure_parent_capacity(
        account_id,
        parent_budget,
        requested_allocated,
        exclude_budget_id=str(existing.get("id")) if existing else None,
    )

    payload = {
        "scope_type": data.target_scope_type.value,
        "scope_id": data.target_scope_id,
        "allocated": requested_allocated,
        "limit_amount": _num_int(data.limit_amount, requested_allocated),
        "overflow_cap": data.overflow_cap,
        "parent_budget_id": str(parent_budget.get("id")),
        "allocation_strategy": _enum_value(data.allocation_strategy),
        "budget_plan_id": parent_budget.get("budget_plan_id"),
    }

    if existing:
        budget = await copilot_db.credit_budgets.update(str(existing.get("id")), payload)
    else:
        budget = await copilot_db.credit_budgets.create(
            data={
                **payload,
                "account_id": account_id,
                "cycle_start": cycle_start,
                "cycle_end": cycle_end,
            }
        )

    budget = _decorate_with_unallocated([budget])[0]
    return {"data": budget}


@router.post("/{budget_id}/distribute-equal")
async def distribute_equal_from_budget(
    budget_id: str,
    data: BudgetDistributeEqualRequest,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Distribute a parent budget equally across child users, preserving optional user overrides."""
    if data.target_scope_type != BudgetScopeType.USER:
        raise HTTPException(status_code=400, detail="Only user distribution is supported.")

    parent_budget = await copilot_db.credit_budgets.find_by_id(budget_id)
    if not parent_budget:
        raise HTTPException(status_code=404, detail="Parent budget not found.")

    parent_scope_type = str(parent_budget.get("scope_type") or "")
    if parent_scope_type not in {
        BudgetScopeType.ACCOUNT.value,
        BudgetScopeType.GROUP.value,
        BudgetScopeType.TEAM.value,
    }:
        raise HTTPException(status_code=400, detail="Equal distribution is only valid for account/group/team budgets.")

    account_id = str(parent_budget.get("account_id") or "")
    cycle_start = _parse_ts(parent_budget.get("cycle_start"))
    cycle_end = _parse_ts(parent_budget.get("cycle_end"))
    if not cycle_start or not cycle_end:
        raise HTTPException(status_code=400, detail="Parent budget cycle is invalid.")

    target_user_ids = await _list_user_ids_for_distribution(account_id, parent_budget)
    if not target_user_ids:
        raise HTTPException(status_code=400, detail="No eligible users found for this parent budget.")

    existing_user_rows = await copilot_db.credit_budgets.find_many(
        where={"account_id": account_id, "scope_type": BudgetScopeType.USER.value},
        order_by="updated_at DESC",
        limit=5000,
    )
    existing_user_rows = [r for r in existing_user_rows if _same_cycle(r, cycle_start, cycle_end)]

    existing_for_targets: Dict[str, dict] = {}
    for row in existing_user_rows:
        if str(row.get("scope_id") or "") in target_user_ids:
            existing_for_targets[str(row.get("scope_id"))] = row

    override_reserved = 0
    locked_override_users: Set[str] = set()
    if not data.include_override_users:
        for user_id, row in existing_for_targets.items():
            strategy = str(row.get("allocation_strategy") or "manual")
            if strategy == BudgetAllocationStrategy.OVERRIDE.value:
                locked_override_users.add(user_id)
                override_reserved += _num_int(row.get("allocated"), 0)

    distributable_users = [uid for uid in target_user_ids if uid not in locked_override_users]
    if len(distributable_users) == 0:
        return {
            "data": {
                "updated": 0,
                "created": 0,
                "deleted": 0,
                "total_users": len(target_user_ids),
                "locked_override_users": len(locked_override_users),
                "share_per_user": 0,
                "remainder": 0,
            }
        }

    parent_allocated = _num_int(parent_budget.get("allocated"), 0)
    distributable_pool = max(0, parent_allocated - override_reserved)

    base_share = distributable_pool // len(distributable_users)
    remainder = distributable_pool % len(distributable_users)

    created = 0
    updated = 0

    for index, user_id in enumerate(distributable_users):
        share = base_share + (1 if index < remainder else 0)
        existing = existing_for_targets.get(user_id)
        payload = {
            "allocated": share,
            "limit_amount": share,
            "overflow_cap": 0,
            "parent_budget_id": str(parent_budget.get("id")),
            "allocation_strategy": BudgetAllocationStrategy.EQUAL_DISTRIBUTION.value,
            "budget_plan_id": parent_budget.get("budget_plan_id"),
        }

        if existing:
            await copilot_db.credit_budgets.update(str(existing.get("id")), payload)
            updated += 1
        else:
            await copilot_db.credit_budgets.create(
                data={
                    **payload,
                    "account_id": account_id,
                    "scope_type": BudgetScopeType.USER.value,
                    "scope_id": user_id,
                    "cycle_start": cycle_start,
                    "cycle_end": cycle_end,
                }
            )
            created += 1

    # Cleanup stale equal-distribution rows from this parent that are no longer eligible.
    stale_rows = [
        r
        for r in existing_user_rows
        if str(r.get("parent_budget_id") or "") == str(parent_budget.get("id"))
        and str(r.get("allocation_strategy") or "") == BudgetAllocationStrategy.EQUAL_DISTRIBUTION.value
        and str(r.get("scope_id") or "") not in set(target_user_ids)
    ]
    deleted = 0
    for row in stale_rows:
        if await copilot_db.credit_budgets.delete(str(row.get("id"))):
            deleted += 1

    return {
        "data": {
            "updated": updated,
            "created": created,
            "deleted": deleted,
            "total_users": len(target_user_ids),
            "locked_override_users": len(locked_override_users),
            "share_per_user": base_share,
            "remainder": remainder,
        }
    }


@router.get("/summary")
async def budget_summary(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Get budget summary aggregation from the view."""
    resolved_account_id = _resolve_optional_account_filter(account_id)
    if resolved_account_id:
        rows = await copilot_db.credit_budgets.execute_raw(
            "SELECT * FROM copilot.v_budget_summary WHERE account_id = $1 ORDER BY scope_type",
            resolved_account_id,
        )
    else:
        rows = await copilot_db.credit_budgets.execute_raw(
            "SELECT * FROM copilot.v_budget_summary ORDER BY account_id, scope_type"
        )
    return {"data": rows}


@router.get("/alerts")
async def budget_alerts(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Get budget alert notifications (entities at 80%+ usage)."""
    resolved_account_id = _resolve_optional_account_filter(account_id)
    if resolved_account_id:
        rows = await copilot_db.credit_budgets.execute_raw(
            "SELECT * FROM copilot.v_budget_alerts WHERE account_id = $1 ORDER BY usage_pct DESC",
            resolved_account_id,
        )
    else:
        rows = await copilot_db.credit_budgets.execute_raw(
            "SELECT * FROM copilot.v_budget_alerts ORDER BY usage_pct DESC"
        )
    return {"data": rows}


@router.post("/record-usage")
async def record_usage(
    data: BudgetUsageRecord,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """
    Record credit usage atomically. Called by alchemi-ai after inference.
    Resolves effective hierarchy budget when explicit budget_id is not provided.
    """
    budget = None
    now = datetime.now(timezone.utc)

    if data.budget_id:
        budget = await copilot_db.credit_budgets.find_by_id(data.budget_id)
        if not budget:
            raise HTTPException(status_code=404, detail="Budget not found.")
        if not _is_active_budget(budget, now):
            raise HTTPException(status_code=404, detail="Budget is not active.")
    else:
        if data.scope_type is None or data.scope_id is None:
            raise HTTPException(
                status_code=400,
                detail="scope_type and scope_id are required when budget_id is not provided.",
            )

        account_id = _resolve_optional_account_filter(None)
        if not account_id:
            raise HTTPException(status_code=400, detail="Unable to resolve account context for usage record.")

        budget = await _resolve_effective_budget(
            account_id,
            data.scope_type,
            data.scope_id,
            now=now,
        )
        if not budget:
            raise HTTPException(status_code=404, detail="No active budget found for this entity hierarchy.")

    budget_id = budget["id"]

    # Try atomic increment within limit
    result = await copilot_db.credit_budgets.atomic_increment(
        budget_id, "used", _num_int(data.amount, 0), max_field="limit_amount"
    )

    if result:
        await log_copilot_audit_event(
            account_id=str(result.get("account_id") or "") or None,
            event_type="copilot_budget_usage",
            resource_type="credit_budget",
            resource_id=str(budget_id),
            action="record_usage",
            message=f"Recorded budget usage amount={_num_int(data.amount, 0)}.",
            details={"amount": _num_int(data.amount, 0), "overflow": False},
            request=request,
        )
        return {"data": result, "overflow": False}

    # Limit reached - try overflow
    overflow_cap = budget.get("overflow_cap")
    if overflow_cap is None:
        # Unlimited overflow
        result = await copilot_db.credit_budgets.atomic_increment(
            budget_id, "overflow_used", _num_int(data.amount, 0)
        )
    elif _num_int(overflow_cap, 0) == 0:
        raise HTTPException(status_code=429, detail="Budget limit reached. No overflow allowed.")
    else:
        result = await copilot_db.credit_budgets.atomic_increment(
            budget_id, "overflow_used", _num_int(data.amount, 0), max_field="overflow_cap"
        )

    if not result:
        raise HTTPException(status_code=429, detail="Budget and overflow limit reached.")

    await log_copilot_audit_event(
        account_id=str(result.get("account_id") or "") or None,
        event_type="copilot_budget_usage",
        resource_type="credit_budget",
        resource_id=str(budget_id),
        action="record_usage",
        severity="warning",
        message=f"Recorded overflow budget usage amount={_num_int(data.amount, 0)}.",
        details={"amount": _num_int(data.amount, 0), "overflow": True},
        request=request,
    )
    return {"data": result, "overflow": True}


# ============================================
# Budget Plans (fixed-path, before /{budget_id})
# ============================================

@router.get("/plans")
async def list_plans(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """List budget plans for the current account."""
    resolved_account_id = _resolve_optional_account_filter(account_id)
    where = {"account_id": resolved_account_id} if resolved_account_id else None
    plans = await copilot_db.budget_plans.find_many(where=where, order_by="created_at DESC")
    for plan in plans:
        plan["distribution"] = _get_plan_distribution_defaults(plan.get("distribution"))
    return {"data": plans, "plans": plans}


@router.post("/plans")
async def create_plan(
    data: BudgetPlanCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a new budget plan."""
    resolved_account_id = _resolve_required_account_for_write(account_id)
    distribution = _get_plan_distribution_defaults(data.distribution)
    distribution["renewal_policy"] = {
        "cadence": data.renewal_cadence.value,
        "day_of_month": _num_int(data.renewal_day_of_month, 1),
    }
    distribution["account_policy"] = {
        "allocation": max(0, _num_int(data.account_allocation, 0)),
        "limit_amount": _num_int(data.account_limit_amount, _num_int(data.account_allocation, 0)),
        "overflow_cap": (
            None
            if data.account_overflow_cap is None
            else max(0, _num_int(data.account_overflow_cap, 0))
        ),
    }
    distribution["billing"] = {
        "overflow_billing_enabled": bool(data.overflow_billing_enabled),
        "overflow_billing_note": (
            str(data.overflow_billing_note or "").strip()
            or "Overflow credits are billed separately after usage."
        ),
    }

    plan = await copilot_db.budget_plans.create(
        data={
            "account_id": resolved_account_id,
            "name": data.name,
            "is_active": data.is_active,
            "distribution": distribution,
        }
    )
    renewal_result = None
    if bool(data.is_active):
        try:
            renewal_result = await _apply_budget_plan_cycle(
                account_id=resolved_account_id,
                plan=plan,
                force=False,
            )
        except HTTPException:
            renewal_result = None

    return {"data": plan, "renewal": renewal_result}


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    data: BudgetPlanUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Update a budget plan."""
    existing = await copilot_db.budget_plans.find_by_id(plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found.")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data and "distribution" not in update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    merged_distribution = _get_plan_distribution_defaults(existing.get("distribution"))
    if data.distribution is not None:
        merged_distribution = _get_plan_distribution_defaults(
            {**merged_distribution, **(data.distribution or {})}
        )

    if data.renewal_cadence is not None or data.renewal_day_of_month is not None:
        renewal = dict(merged_distribution.get("renewal_policy") or {})
        if data.renewal_cadence is not None:
            renewal["cadence"] = data.renewal_cadence.value
        if data.renewal_day_of_month is not None:
            renewal["day_of_month"] = _num_int(data.renewal_day_of_month, 1)
        merged_distribution["renewal_policy"] = renewal

    if (
        data.account_allocation is not None
        or data.account_limit_amount is not None
        or data.account_overflow_cap is not None
    ):
        account_policy = dict(merged_distribution.get("account_policy") or {})
        if data.account_allocation is not None:
            account_policy["allocation"] = max(0, _num_int(data.account_allocation, 0))
        if data.account_limit_amount is not None:
            account_policy["limit_amount"] = max(0, _num_int(data.account_limit_amount, 0))
        if data.account_overflow_cap is not None:
            account_policy["overflow_cap"] = max(0, _num_int(data.account_overflow_cap, 0))
        merged_distribution["account_policy"] = account_policy

    if data.overflow_billing_enabled is not None or data.overflow_billing_note is not None:
        billing = dict(merged_distribution.get("billing") or {})
        if data.overflow_billing_enabled is not None:
            billing["overflow_billing_enabled"] = bool(data.overflow_billing_enabled)
        if data.overflow_billing_note is not None:
            billing["overflow_billing_note"] = (
                str(data.overflow_billing_note or "").strip()
                or "Overflow credits are billed separately after usage."
            )
        merged_distribution["billing"] = billing

    payload = {k: v for k, v in update_data.items() if k != "distribution"}
    payload["distribution"] = merged_distribution

    plan = await copilot_db.budget_plans.update(plan_id, payload)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    should_refresh_cycle = bool(plan.get("is_active")) and any(
        [
            data.renewal_cadence is not None,
            data.renewal_day_of_month is not None,
            data.account_allocation is not None,
            data.account_limit_amount is not None,
            data.account_overflow_cap is not None,
            data.is_active is True,
        ]
    )
    renewal = None
    if should_refresh_cycle:
        renewal = await _apply_budget_plan_cycle(
            account_id=str(plan.get("account_id") or ""),
            plan=plan,
            force=True,
        )
    return {"data": plan, "renewal": renewal}


@router.post("/plans/{plan_id}/renew")
async def renew_plan_cycle(
    plan_id: str,
    data: BudgetPlanRenewRequest,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """
    Apply budget plan cycle renewal by creating/updating the account scope budget for the active cycle.
    """
    plan = await copilot_db.budget_plans.find_by_id(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    account_id = str(plan.get("account_id") or "")
    if not account_id:
        raise HTTPException(status_code=400, detail="Plan has no account_id.")

    anchor = data.cycle_anchor
    result = await _apply_budget_plan_cycle(
        account_id=account_id,
        plan=plan,
        cycle_anchor=anchor,
        force=bool(data.force),
    )

    await log_copilot_audit_event(
        account_id=account_id,
        event_type="copilot_budget_plan",
        resource_type="budget_plan",
        resource_id=str(plan_id),
        action="renew",
        message="Executed budget plan cycle renewal.",
        details={
            "cycle_start": str(result.get("cycle_start")),
            "cycle_end": str(result.get("cycle_end")),
            "created": bool(result.get("created")),
            "force": bool(data.force),
        },
        request=request,
    )
    return {"data": result}


@router.delete("/plans/{plan_id}")
async def delete_plan(
    plan_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete a budget plan."""
    deleted = await copilot_db.budget_plans.delete(plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return {"status": "ok"}


# ============================================
# Single Budget CRUD (dynamic path, must be last)
# ============================================

@router.get("/{budget_id}")
async def get_budget(
    budget_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Get a single credit budget."""
    budget = await copilot_db.credit_budgets.find_by_id(budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found.")
    budget = _decorate_with_unallocated([budget])[0]
    return {"data": budget}


@router.put("/{budget_id}")
async def update_budget(
    budget_id: str,
    data: CreditBudgetUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Update a credit budget."""
    existing = await copilot_db.credit_budgets.find_by_id(budget_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Budget not found.")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    requested_allocated = _num_int(update_data.get("allocated"), _num_int(existing.get("allocated"), 0))
    scope_type = str(existing.get("scope_type") or "")

    if scope_type == BudgetScopeType.ACCOUNT.value and "allocated" in update_data:
        await _ensure_account_capacity_for_update(existing, requested_allocated)
    elif scope_type != BudgetScopeType.ACCOUNT.value and "allocated" in update_data:
        parent_id = update_data.get("parent_budget_id") or existing.get("parent_budget_id")
        parent = None
        if parent_id:
            parent = await copilot_db.credit_budgets.find_by_id(str(parent_id))
        if not parent:
            cycle_start = _parse_ts(existing.get("cycle_start"))
            cycle_end = _parse_ts(existing.get("cycle_end"))
            if cycle_start and cycle_end:
                parent = await _resolve_parent_budget_for_cycle(
                    str(existing.get("account_id") or ""),
                    BudgetScopeType(scope_type),
                    str(existing.get("scope_id") or ""),
                    cycle_start,
                    cycle_end,
                )
        if parent:
            await _ensure_parent_capacity(
                str(existing.get("account_id") or ""),
                parent,
                requested_allocated,
                exclude_budget_id=budget_id,
            )
            if "parent_budget_id" not in update_data:
                update_data["parent_budget_id"] = str(parent.get("id"))

    if "allocation_strategy" in update_data:
        update_data["allocation_strategy"] = _enum_value(update_data["allocation_strategy"])

    budget = await copilot_db.credit_budgets.update(budget_id, update_data)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found.")
    await log_copilot_audit_event(
        account_id=str(budget.get("account_id") or "") or None,
        event_type="copilot_budget",
        resource_type="credit_budget",
        resource_id=str(budget_id),
        action="update",
        message=f"Updated budget for scope {budget.get('scope_type')}:{budget.get('scope_id')}.",
        details={"changes": list(update_data.keys())},
        request=request,
    )
    budget = _decorate_with_unallocated([budget])[0]
    return {"data": budget}


@router.delete("/{budget_id}")
async def delete_budget(
    budget_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete a credit budget."""
    existing = await copilot_db.credit_budgets.find_by_id(budget_id)
    deleted = await copilot_db.credit_budgets.delete(budget_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Budget not found.")
    await log_copilot_audit_event(
        account_id=str((existing or {}).get("account_id") or "") or None,
        event_type="copilot_budget",
        resource_type="credit_budget",
        resource_id=str(budget_id),
        action="delete",
        severity="warning",
        message=f"Deleted budget for scope {(existing or {}).get('scope_type')}:{(existing or {}).get('scope_id')}.",
        request=request,
    )
    return {"status": "ok"}
