"""
Effective access computation endpoints.
Computes hierarchical effective access for a user within an account by
merging override configs across scope levels: Account > Group > Team > User.
"""
from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional, List, Dict, Any
from datetime import datetime

from alchemi.auth.service_auth import require_scope, get_request_context

router = APIRouter(prefix="/alchemi/effective-access", tags=["Effective Access"])


# ── Constants ────────────────────────────────────────────────────────────────

# Scope specificity order (lower = more specific = higher priority)
SCOPE_PRIORITY = {
    "USER": 1,
    "TEAM": 2,
    "GROUP": 3,
    "ACCOUNT": 4,
}

SCOPE_DISPLAY_NAMES = {
    "USER": "User",
    "TEAM": "Team",
    "GROUP": "Group",
    "ACCOUNT": "Account",
}

# Sentinel ID used when a hierarchy level does not apply
_NIL_UUID = "00000000-0000-0000-0000-000000000000"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_value_config(raw: Any) -> dict:
    """Normalise a value_config column that may be a string, dict, or None."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        import json
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def _scope_priority(scope_type: str) -> int:
    """Return numeric priority for a scope type (lower = more specific)."""
    return SCOPE_PRIORITY.get(scope_type, 5)


def _scope_display_name(scope_type: str) -> str:
    """Return a human-readable label for a scope type."""
    return SCOPE_DISPLAY_NAMES.get(scope_type, scope_type)


def _is_config_active(config: Any) -> bool:
    """Check whether an override config is currently within its validity window."""
    now = datetime.utcnow()
    if config.valid_from is not None and config.valid_from > now:
        return False
    if config.valid_until is not None and config.valid_until <= now:
        return False
    return True


def _merge_items_restrictive(
    rows: List[Any],
) -> List[Dict[str, Any]]:
    """
    Merge items from multiple scope-level override rows using RESTRICTIVE logic.

    An item is considered disabled if ANY scope in the hierarchy disables it.
    The ``restrictedBy`` field records the first scope that disabled the item.
    """
    items_map: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        value_config = _parse_value_config(row.value_config)
        items = value_config.get("items", [])

        for item in items:
            code = item.get("code")
            if not code:
                continue

            item_enabled = item.get("enabled", True) is not False

            if code not in items_map:
                items_map[code] = {
                    "name": item.get("name") or code,
                    "enabled": item_enabled,
                    "restrictedBy": (
                        _scope_display_name(row.scope_type) if not item_enabled else None
                    ),
                }
            else:
                existing = items_map[code]
                if not item_enabled and existing["enabled"]:
                    existing["enabled"] = False
                    existing["restrictedBy"] = _scope_display_name(row.scope_type)
                # Keep name from whichever row provides one
                if item.get("name") and not existing.get("name"):
                    existing["name"] = item["name"]

    return [
        {"code": code, **data}
        for code, data in items_map.items()
    ]


def _serialise_config(config: Any) -> Dict[str, Any]:
    """Convert a Prisma config record into a plain dict for JSON responses."""
    return {
        "id": config.id,
        "account_id": config.account_id,
        "product_code": config.product_code,
        "feature_code": config.feature_code,
        "entity_code": config.entity_code,
        "category": config.category,
        "name": config.name,
        "action": config.action,
        "inherit": config.inherit,
        "value_config": _parse_value_config(config.value_config),
        "scope_type": config.scope_type,
        "scope_id": config.scope_id,
        "restriction_json": config.restriction_json,
        "reason": config.reason,
        "valid_from": config.valid_from.isoformat() if config.valid_from else None,
        "valid_until": config.valid_until.isoformat() if config.valid_until else None,
    }


# ── Endpoint ─────────────────────────────────────────────────────────────────


@router.get("/compute")
async def compute_effective_access(
    request: Request,
    account_id: str = Query(..., description="Account ID to compute access for"),
    user_id: str = Query(..., description="User ID to compute access for"),
    _=require_scope("access:read"),
):
    """
    Compute the effective access configuration for a user within an account.

    The algorithm walks the organisational hierarchy
    (Account -> Group -> Team -> User) and merges override configs so that
    more-specific scopes win over less-specific ones.  Within items lists
    the merge is *restrictive*: an item is disabled if ANY scope disables it.

    Returns:
        configs  -- merged list of effective override configurations
        scope_chain -- raw configs found at each hierarchy level
    """
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # ── Step 1: Resolve the user's membership to find team_id ────────────
    membership = await prisma_client.db.alchemi_accountmembershiptable.find_first(
        where={
            "account_id": account_id,
            "user_id": user_id,
            "is_active": True,
        },
    )

    if not membership:
        raise HTTPException(
            status_code=404,
            detail=f"No active membership found for user '{user_id}' in account '{account_id}'",
        )

    team_id: Optional[str] = getattr(membership, "team_id", None)
    group_id: Optional[str] = None

    # ── Step 2: If user belongs to a team, resolve the team's group_id ───
    if team_id:
        team = await prisma_client.db.alchemi_teamtable.find_first(
            where={"id": team_id},
        )
        if team:
            group_id = getattr(team, "group_id", None)

    # ── Step 3: Fetch all applicable override configs ────────────────────
    # Build the list of (scope_type, scope_id) pairs to query.
    scope_filters: List[Dict[str, str]] = [
        {"scope_type": "ACCOUNT", "scope_id": account_id},
    ]
    if group_id:
        scope_filters.append({"scope_type": "GROUP", "scope_id": group_id})
    if team_id:
        scope_filters.append({"scope_type": "TEAM", "scope_id": team_id})
    scope_filters.append({"scope_type": "USER", "scope_id": user_id})

    all_overrides = await prisma_client.db.alchemi_accountoverrideconfigtable.find_many(
        where={
            "account_id": account_id,
            "OR": scope_filters,
        },
    )

    # Filter to only currently-valid configs
    active_overrides = [cfg for cfg in all_overrides if _is_config_active(cfg)]

    # ── Step 4: Bucket overrides by scope level for the scope_chain ──────
    scope_chain: Dict[str, List[Dict[str, Any]]] = {
        "account": [],
        "group": [],
        "team": [],
        "user": [],
    }

    for cfg in active_overrides:
        bucket = cfg.scope_type.lower() if cfg.scope_type else "account"
        if bucket in scope_chain:
            scope_chain[bucket].append(_serialise_config(cfg))

    # ── Step 5: Merge configs — more-specific scope wins ─────────────────
    # Group overrides by their entity key (product:feature:entity).
    entity_groups: Dict[str, List[Any]] = {}

    for cfg in active_overrides:
        key = (
            f"{cfg.product_code or ''}:"
            f"{cfg.feature_code or ''}:"
            f"{cfg.entity_code or ''}"
        )
        entity_groups.setdefault(key, []).append(cfg)

    # Within each entity key, sort by specificity (most specific first).
    for rows in entity_groups.values():
        rows.sort(key=lambda r: _scope_priority(r.scope_type))

    merged_configs: List[Dict[str, Any]] = []

    for key, rows in entity_groups.items():
        # The most-specific row determines the top-level config values.
        most_specific = rows[0]
        value_config = _parse_value_config(most_specific.value_config)

        is_enabled = (
            value_config.get("enabled", True) is not False
            and most_specific.action != "DENY"
        )
        restricted_by = (
            _scope_display_name(most_specific.scope_type) if not is_enabled else None
        )

        # Merge item-level lists with restrictive logic across all scopes.
        merged_items = _merge_items_restrictive(rows)

        merged_configs.append({
            "product_code": most_specific.product_code,
            "feature_code": most_specific.feature_code,
            "entity_code": most_specific.entity_code,
            "category": most_specific.category,
            "name": most_specific.name,
            "action": most_specific.action,
            "inherit": most_specific.inherit,
            "enabled": is_enabled,
            "restrictedBy": restricted_by,
            "resolved_scope_type": most_specific.scope_type,
            "value_config": value_config,
            "items": merged_items,
        })

    return {
        "configs": merged_configs,
        "scope_chain": scope_chain,
        "hierarchy": {
            "account_id": account_id,
            "group_id": group_id,
            "team_id": team_id,
            "user_id": user_id,
        },
        "computed_at": datetime.utcnow().isoformat(),
    }
