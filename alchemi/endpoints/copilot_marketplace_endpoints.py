"""
Marketplace item management endpoints.
"""
from datetime import datetime
import json
import uuid
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_audit_helpers import log_copilot_audit_event
from alchemi.endpoints.copilot_auth import (
    require_copilot_admin_access,
    require_copilot_marketplace_access,
)
from alchemi.endpoints.copilot_types import (
    MarketplaceAssignment,
    MarketplaceEntityType,
    MarketplaceInstallRequest,
    MarketplaceItemCreate,
    MarketplaceItemUpdate,
    MarketplaceStatus,
    PricingModel,
)
from alchemi.middleware.tenant_context import is_super_admin

router = APIRouter(prefix="/copilot/marketplace", tags=["Copilot - Marketplace"])

_COPILOT_ADMIN_ROLES = {
    "proxy_admin",
    "app_admin",
    "org_admin",
    "app_owner",
    "demo_app_owner",
}


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


def _resolve_required_account_for_write(account_id: Optional[str]) -> str:
    resolved = _resolve_optional_account_filter(account_id)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="account_id is required for this super admin write operation.",
        )
    return resolved


async def _get_marketplace_item_for_read(
    item_id: str,
    resolved_account_id: Optional[str],
) -> Optional[dict]:
    """
    Tenant reads can access both account-owned and global marketplace items.
    Super-admin without account filter can access any row by id.
    """
    if resolved_account_id and not is_super_admin():
        rows = await copilot_db.marketplace_items.execute_raw(
            """
            SELECT *
            FROM copilot.marketplace_items
            WHERE marketplace_id = $1
              AND (account_id = $2 OR account_id IS NULL)
            LIMIT 1
            """,
            item_id,
            resolved_account_id,
        )
        return rows[0] if rows else None

    item = await copilot_db.marketplace_items.find_by_id(item_id)
    return item


async def _ensure_account_agent_install(
    marketplace_item: dict,
    account_id: str,
) -> Optional[dict]:
    """
    Install semantics for agent marketplace items:
    - Resolve source agent definition by entity_id
    - Create account-scoped copy if one does not already exist
    """
    entity_type = str(marketplace_item.get("entity_type") or "").strip().lower()
    source_agent_id = str(marketplace_item.get("entity_id") or "").strip()
    if entity_type != "agent" or not source_agent_id:
        return None

    source_rows = await copilot_db.agents_def.execute_raw(
        """
        SELECT *
        FROM copilot.agents_def
        WHERE agent_id = $1
        LIMIT 1
        """,
        source_agent_id,
    )
    if not source_rows:
        # Backward-compatible behavior: allow install count/assignment updates even if
        # the source definition has not been synced yet.
        return None
    source = source_rows[0]

    source_account_id = source.get("account_id")
    if source_account_id and str(source_account_id) != str(account_id) and not is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="Cannot install an agent definition owned by another account.",
        )

    existing_rows = await copilot_db.agents_def.execute_raw(
        """
        SELECT *
        FROM copilot.agents_def
        WHERE account_id = $1
          AND provider = 'ACCOUNT'
          AND name = $2
          AND prompt = $3
        ORDER BY created_at DESC
        LIMIT 1
        """,
        account_id,
        source.get("name"),
        source.get("prompt"),
    )
    if existing_rows:
        return existing_rows[0]

    from alchemi.db.copilot_db import PgArray

    tags = source.get("tags") if isinstance(source.get("tags"), list) else []
    builtin_tools = (
        source.get("builtin_tools") if isinstance(source.get("builtin_tools"), list) else []
    )
    tools_mcp_ids = (
        source.get("tools_mcp_ids") if isinstance(source.get("tools_mcp_ids"), list) else []
    )
    tools_openapi_ids = (
        source.get("tools_openapi_ids")
        if isinstance(source.get("tools_openapi_ids"), list)
        else []
    )
    availability = (
        source.get("availability") if isinstance(source.get("availability"), list) else []
    )

    create_data = {
        "agent_id": str(uuid.uuid4()),
        "account_id": account_id,
        "name": source.get("name"),
        "description": source.get("description"),
        "prompt": source.get("prompt"),
        "page": source.get("page"),
        "categories": source.get("categories"),
        "tags": PgArray(tags),
        "builtin_tools": PgArray(builtin_tools),
        "tools_mcp_ids": PgArray(tools_mcp_ids),
        "tools_openapi_ids": PgArray(tools_openapi_ids),
        "links": source.get("links"),
        "is_singleton": bool(source.get("is_singleton", False)),
        "is_non_conversational": bool(source.get("is_non_conversational", False)),
        "status": "active",
        "availability": PgArray(availability),
        "provider": "ACCOUNT",
    }
    installed = await copilot_db.agents_def.create(create_data)
    return installed


def _is_admin_actor(auth_ctx: Optional[Dict[str, Any]]) -> bool:
    role = str((auth_ctx or {}).get("user_role") or "").strip().lower()
    return is_super_admin() or role in _COPILOT_ADMIN_ROLES


def _item_assignments(item: Dict[str, Any]) -> List[Dict[str, str]]:
    metadata = item.get("metadata")
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                metadata = parsed
        except Exception:
            metadata = None
    if not isinstance(metadata, dict):
        return []
    assignments = metadata.get("assignments")
    if not isinstance(assignments, list):
        return []

    normalized: List[Dict[str, str]] = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        scope_type = str(assignment.get("scope_type") or "").strip().lower()
        scope_id = str(assignment.get("scope_id") or "").strip()
        if scope_type in {"account", "group", "team", "user"} and scope_id:
            normalized.append({"scope_type": scope_type, "scope_id": scope_id})
    return normalized


def _normalize_marketplace_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item)
    metadata = normalized.get("metadata")
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                normalized["metadata"] = parsed
        except Exception:
            pass
    return normalized


def _marketplace_override_key(item: Dict[str, Any]) -> str:
    entity_type = str(item.get("entity_type") or "").strip().lower()
    entity_id = str(item.get("entity_id") or "").strip().lower()
    provider = str(item.get("provider") or "").strip().lower()
    return f"{entity_type}:{entity_id}:{provider}"


def _prefer_account_items_over_global(
    items: List[Dict[str, Any]],
    account_id: Optional[str],
) -> List[Dict[str, Any]]:
    """
    If an account-scoped marketplace copy exists for an entity/provider, hide the
    global row for that same key. This makes assignment overrides effective.
    """
    if not account_id:
        return items

    account_keys: Set[str] = set()
    for item in items:
        item_account_id = str(item.get("account_id") or "").strip()
        if item_account_id and item_account_id == str(account_id):
            account_keys.add(_marketplace_override_key(item))

    filtered: List[Dict[str, Any]] = []
    for item in items:
        item_account_id = str(item.get("account_id") or "").strip()
        key = _marketplace_override_key(item)
        if not item_account_id and key in account_keys:
            continue
        filtered.append(item)
    return filtered


def _extract_assignment_candidates(
    auth_ctx: Optional[Dict[str, Any]],
    resolved_account_id: Optional[str],
    subject_overrides: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, Set[str]]:
    teams_raw = (auth_ctx or {}).get("teams") or []
    teams = [str(team_id).strip() for team_id in teams_raw if str(team_id).strip()]
    team_id = str((auth_ctx or {}).get("team_id") or "").strip()
    if team_id:
        teams.append(team_id)

    organization_id = str((auth_ctx or {}).get("organization_id") or "").strip()
    organization_ids_raw = (auth_ctx or {}).get("organization_ids") or []
    organization_ids = {
        str(org_id).strip()
        for org_id in organization_ids_raw
        if str(org_id).strip()
    }
    user_id = str((auth_ctx or {}).get("user_id") or "").strip()
    user_email = str((auth_ctx or {}).get("user_email") or "").strip().lower()
    account = str(resolved_account_id or "").strip()

    group_ids: Set[str] = set()
    if organization_id:
        group_ids.add(organization_id)
    group_ids.update(organization_ids)

    candidates = {
        "account": {account} if account else set(),
        "team": set(teams),
        "group": group_ids,
        "user": {v for v in [user_id, user_email] if v},
    }
    if subject_overrides:
        for scope in ("account", "team", "group", "user"):
            extra = {
                str(v).strip()
                for v in (subject_overrides.get(scope) or set())
                if str(v).strip()
            }
            if not extra:
                continue
            if scope == "account":
                candidates[scope] = extra
            else:
                candidates[scope].update(extra)
    return candidates


def _is_item_visible_to_subject(
    item: Dict[str, Any],
    auth_ctx: Optional[Dict[str, Any]],
    resolved_account_id: Optional[str],
    strict_assignments: bool = False,
    subject_overrides: Optional[Dict[str, Set[str]]] = None,
) -> bool:
    assignments = _item_assignments(item)
    if not assignments:
        # Default behavior is backward-compatible open visibility.
        # Strict mode is used by user-facing Copilot surfaces that require explicit mapping.
        return not strict_assignments

    candidates = _extract_assignment_candidates(
        auth_ctx,
        resolved_account_id,
        subject_overrides=subject_overrides,
    )
    for assignment in assignments:
        scope_type = assignment["scope_type"]
        scope_id = assignment["scope_id"]
        if scope_id == "*":
            return True
        if scope_type == "user":
            # Email assignments should match regardless of casing.
            if scope_id.strip().lower() in {
                str(candidate).strip().lower()
                for candidate in candidates.get("user", set())
                if str(candidate).strip()
            }:
                return True
            continue
        if scope_id in candidates.get(scope_type, set()):
            return True
    return False


def _normalize_assignments(
    assignments: Optional[List[MarketplaceAssignment]],
    account_id: Optional[str],
) -> List[Dict[str, str]]:
    if not assignments:
        return []

    normalized: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for assignment in assignments:
        scope_type = str(assignment.scope_type).strip().lower()
        scope_id = str(assignment.scope_id or "").strip()
        if not scope_id:
            continue
        key = f"{scope_type}:{scope_id}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"scope_type": scope_type, "scope_id": scope_id})

    # If admin did not include account assignment explicitly, keep assignments as-is.
    # Caller can choose to provide strict user/team/org mapping only.
    if account_id:
        pass
    return normalized


def _parse_csv_values(raw: Optional[str]) -> Set[str]:
    if not raw:
        return set()
    return {
        part.strip()
        for part in str(raw).split(",")
        if part and part.strip()
    }


async def _save_assignments_on_item(
    item_id: str,
    current_item: Dict[str, Any],
    assignments: List[Dict[str, str]],
) -> Dict[str, Any]:
    metadata = current_item.get("metadata")
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                metadata = parsed
        except Exception:
            metadata = None
    merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    merged_metadata["assignments"] = assignments
    updated = await copilot_db.marketplace_items.update(
        item_id,
        {"metadata": merged_metadata},
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    return updated


async def _upsert_account_marketplace_item_copy(
    source_item: Dict[str, Any],
    account_id: str,
    assignments: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Keep global marketplace items immutable for tenant admins by creating/updating
    an account-scoped copy with account-specific assignment metadata.
    """
    entity_id = source_item.get("entity_id")
    if not entity_id:
        raise HTTPException(status_code=400, detail="Marketplace item has no entity_id.")
    provider = source_item.get("provider")
    existing_rows = await copilot_db.marketplace_items.execute_raw(
        """
        SELECT *
        FROM copilot.marketplace_items
        WHERE account_id = $1
          AND entity_id = $2::uuid
          AND provider = $3
        ORDER BY created_at DESC
        LIMIT 1
        """,
        account_id,
        str(entity_id),
        provider,
    )

    metadata = source_item.get("metadata")
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            metadata = parsed if isinstance(parsed, dict) else {}
        except Exception:
            metadata = {}
    merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    merged_metadata["assignments"] = assignments

    if existing_rows:
        existing = _normalize_marketplace_item(existing_rows[0])
        updated = await copilot_db.marketplace_items.update(
            existing["marketplace_id"],
            {"metadata": merged_metadata},
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Marketplace item not found.")
        return _normalize_marketplace_item(updated)

    clone_data = {
        "account_id": account_id,
        "entity_id": source_item.get("entity_id"),
        "entity_type": source_item.get("entity_type"),
        "connection_id": source_item.get("connection_id"),
        "provider": source_item.get("provider") or "PLATFORM",
        "metadata": merged_metadata,
        "title": source_item.get("title"),
        "short_description": source_item.get("short_description"),
        "long_description": source_item.get("long_description"),
        "icon_url": source_item.get("icon_url"),
        "banner_url": source_item.get("banner_url"),
        "screenshots": source_item.get("screenshots") or [],
        "demo_video_url": source_item.get("demo_video_url"),
        "author": source_item.get("author"),
        "author_url": source_item.get("author_url"),
        "version": source_item.get("version") or "1.0.0",
        "pricing_model": source_item.get("pricing_model") or "free",
        "price": source_item.get("price"),
        "is_featured": bool(source_item.get("is_featured", False)),
        "is_verified": bool(source_item.get("is_verified", False)),
        "marketplace_status": source_item.get("marketplace_status") or "published",
        "capabilities": source_item.get("capabilities") or [],
        "requirements": source_item.get("requirements") or [],
        "published_at": source_item.get("published_at"),
    }
    created = await copilot_db.marketplace_items.create(clone_data)
    return _normalize_marketplace_item(created)


@router.get("/")
async def list_items(
    request: Request,
    account_id: Optional[str] = None,
    entity_type: Optional[MarketplaceEntityType] = None,
    marketplace_status: Optional[MarketplaceStatus] = None,
    pricing_model: Optional[PricingModel] = None,
    is_featured: Optional[bool] = None,
    force_assignment_filter: bool = False,
    strict_assignments: bool = False,
    subject_user_id: Optional[str] = None,
    subject_email: Optional[str] = None,
    subject_team_ids: Optional[str] = None,
    subject_group_ids: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    _auth=Depends(require_copilot_marketplace_access),
):
    """List marketplace items with filters."""
    where: Dict[str, Any] = {}
    resolved_account_id = _resolve_optional_account_filter(account_id)
    is_admin = _is_admin_actor(_auth)
    has_subject_override = any(
        [
            bool(subject_user_id and str(subject_user_id).strip()),
            bool(subject_email and str(subject_email).strip()),
            bool(subject_team_ids and str(subject_team_ids).strip()),
            bool(subject_group_ids and str(subject_group_ids).strip()),
        ]
    )
    if has_subject_override and not (is_super_admin() or bool((_auth or {}).get("is_super_admin"))):
        raise HTTPException(status_code=403, detail="Subject override requires super admin access.")
    subject_overrides: Dict[str, Set[str]] = {
        "account": {str(resolved_account_id).strip()} if resolved_account_id else set(),
        "team": _parse_csv_values(subject_team_ids),
        "group": _parse_csv_values(subject_group_ids),
        "user": {
            v
            for v in [
                str(subject_user_id or "").strip(),
                str(subject_email or "").strip().lower(),
            ]
            if v
        },
    }

    if not is_admin and marketplace_status is None:
        marketplace_status = MarketplaceStatus.PUBLISHED

    # Tenant users (and super admin subject-override calls in forced-assignment mode)
    # should see account-scoped listings plus global listings.
    if resolved_account_id and (not is_super_admin() or force_assignment_filter):
        conditions = ["(account_id = $1 OR account_id IS NULL)"]
        params = [resolved_account_id]
        idx = 2
        if entity_type:
            conditions.append(f"entity_type = ${idx}")
            params.append(entity_type.value)
            idx += 1
        if marketplace_status:
            conditions.append(f"marketplace_status = ${idx}")
            params.append(marketplace_status.value)
            idx += 1
        if pricing_model:
            conditions.append(f"pricing_model = ${idx}")
            params.append(pricing_model.value)
            idx += 1
        if is_featured is not None:
            conditions.append(f"is_featured = ${idx}")
            params.append(is_featured)
            idx += 1

        where_sql = " AND ".join(conditions)
        items = await copilot_db.marketplace_items.execute_raw(
            f"""
            SELECT *
            FROM copilot.marketplace_items
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
            limit,
            offset,
        )
        items = [_normalize_marketplace_item(item) for item in items]
        items = _prefer_account_items_over_global(items, resolved_account_id)
        total = await copilot_db.marketplace_items.execute_raw_val(
            f"""
            SELECT COUNT(*)
            FROM copilot.marketplace_items
            WHERE {where_sql}
            """,
            *params,
        )
        if force_assignment_filter or not is_admin:
            filtered_items = [
                item
                for item in items
                if _is_item_visible_to_subject(
                    item,
                    _auth,
                    resolved_account_id,
                    strict_assignments=strict_assignments,
                    subject_overrides=subject_overrides if has_subject_override else None,
                )
            ]
            return {"data": filtered_items, "items": filtered_items, "total": len(filtered_items)}
        return {"data": items, "items": items, "total": len(items)}

    if resolved_account_id:
        where["account_id"] = resolved_account_id
    if entity_type:
        where["entity_type"] = entity_type.value
    if marketplace_status:
        where["marketplace_status"] = marketplace_status.value
    if pricing_model:
        where["pricing_model"] = pricing_model.value
    if is_featured is not None:
        where["is_featured"] = is_featured

    items = await copilot_db.marketplace_items.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    items = [_normalize_marketplace_item(item) for item in items]
    if resolved_account_id and not is_super_admin():
        items = _prefer_account_items_over_global(items, resolved_account_id)
    if force_assignment_filter or not is_admin:
        items = [
            item
            for item in items
            if _is_item_visible_to_subject(
                item,
                _auth,
                resolved_account_id,
                strict_assignments=strict_assignments,
                subject_overrides=subject_overrides if has_subject_override else None,
            )
        ]
    total = len(items) if not is_admin else await copilot_db.marketplace_items.count(where=where if where else None)
    return {"data": items, "items": items, "total": total}


@router.get("/featured")
async def featured_items(
    request: Request,
    account_id: Optional[str] = None,
    force_assignment_filter: bool = False,
    strict_assignments: bool = False,
    limit: int = Query(default=20, le=50),
    _auth=Depends(require_copilot_marketplace_access),
):
    """Get featured marketplace items."""
    where = {"is_featured": True, "marketplace_status": "published"}
    resolved_account_id = _resolve_optional_account_filter(account_id)

    if resolved_account_id and not is_super_admin():
        items = await copilot_db.marketplace_items.execute_raw(
            """
            SELECT *
            FROM copilot.marketplace_items
            WHERE (account_id = $1 OR account_id IS NULL)
              AND is_featured = TRUE
              AND marketplace_status = 'published'
            ORDER BY rating_avg DESC NULLS LAST
            LIMIT $2
            """,
            resolved_account_id,
            limit,
        )
        items = [_normalize_marketplace_item(item) for item in items]
        items = _prefer_account_items_over_global(items, resolved_account_id)
        if force_assignment_filter or not _is_admin_actor(_auth):
            items = [
                item
                for item in items
                if _is_item_visible_to_subject(
                    item,
                    _auth,
                    resolved_account_id,
                    strict_assignments=strict_assignments,
                )
            ]
        return {"data": items}

    if resolved_account_id:
        where["account_id"] = resolved_account_id
    items = await copilot_db.marketplace_items.find_many(
        where=where,
        order_by="rating_avg DESC NULLS LAST",
        limit=limit,
    )
    items = [_normalize_marketplace_item(item) for item in items]
    if force_assignment_filter or not _is_admin_actor(_auth):
        items = [
            item
            for item in items
            if _is_item_visible_to_subject(
                item,
                _auth,
                resolved_account_id,
                strict_assignments=strict_assignments,
            )
        ]
    return {"data": items}


@router.post("/")
async def create_item(
    data: MarketplaceItemCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a new marketplace listing."""
    create_data = data.model_dump()
    create_data["account_id"] = _resolve_required_account_for_write(account_id)
    # Convert enums to string values
    create_data["entity_type"] = create_data["entity_type"].value
    create_data["pricing_model"] = create_data["pricing_model"].value
    item = await copilot_db.marketplace_items.create(
        data=create_data
    )
    return {"data": item}


@router.get("/{item_id}")
async def get_item(
    item_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_marketplace_access),
):
    """Get a single marketplace item."""
    resolved_account_id = _resolve_optional_account_filter(account_id)
    item = await _get_marketplace_item_for_read(item_id, resolved_account_id)
    if not item:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    item = _normalize_marketplace_item(item)
    if not _is_admin_actor(_auth) and not _is_item_visible_to_subject(
        item, _auth, resolved_account_id
    ):
        raise HTTPException(status_code=403, detail="Marketplace item is not assigned to this user.")
    return {"data": item}


@router.get("/{item_id}/assignments")
async def get_item_assignments(
    item_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_marketplace_access),
):
    """Return explicit marketplace visibility assignments for a listing."""
    resolved_account_id = _resolve_optional_account_filter(account_id)
    item = await _get_marketplace_item_for_read(item_id, resolved_account_id)
    if not item:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    item = _normalize_marketplace_item(item)
    if not _is_admin_actor(_auth) and not _is_item_visible_to_subject(
        item, _auth, resolved_account_id
    ):
        raise HTTPException(status_code=403, detail="Marketplace item is not assigned to this user.")
    return {"data": {"assignments": _item_assignments(item)}}


@router.put("/{item_id}/assignments")
async def set_item_assignments(
    item_id: str,
    request: Request,
    payload: MarketplaceInstallRequest,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Replace assignment rules on a marketplace listing."""
    resolved_account_id = _resolve_optional_account_filter(account_id)
    item = await _get_marketplace_item_for_read(item_id, resolved_account_id)
    if not item:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    item = _normalize_marketplace_item(item)
    assignments = _normalize_assignments(payload.assignments, resolved_account_id)
    if resolved_account_id and not is_super_admin() and not item.get("account_id"):
        updated = await _upsert_account_marketplace_item_copy(
            source_item=item,
            account_id=resolved_account_id,
            assignments=assignments,
        )
    else:
        updated = await _save_assignments_on_item(item_id, item, assignments)
    await log_copilot_audit_event(
        account_id=resolved_account_id,
        event_type="copilot_marketplace_assignment",
        resource_type="marketplace_item",
        resource_id=str(item_id),
        action="update",
        message=f"Updated marketplace assignments for '{item.get('title') or item_id}'.",
        details={"assignments": assignments},
        request=request,
    )
    return {"data": {"assignments": _item_assignments(updated)}}


@router.put("/{item_id}")
async def update_item(
    item_id: str,
    data: MarketplaceItemUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Update a marketplace item."""
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    # Convert enums to string values
    for field in ("pricing_model", "marketplace_status"):
        if field in update_data and hasattr(update_data[field], "value"):
            update_data[field] = update_data[field].value

    # Handle publish action
    if update_data.get("marketplace_status") == "published":
        update_data["published_at"] = datetime.utcnow()

    item = await copilot_db.marketplace_items.update(item_id, update_data)
    if not item:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    return {"data": item}


@router.delete("/{item_id}")
async def delete_item(
    item_id: str,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete a marketplace item."""
    deleted = await copilot_db.marketplace_items.delete(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    return {"status": "ok"}


@router.post("/{item_id}/install")
async def install_item(
    item_id: str,
    request: Request,
    payload: Optional[MarketplaceInstallRequest] = None,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_marketplace_access),
):
    """
    Install a marketplace item into tenant scope.
    For agent entities, creates an account-scoped agent definition copy (idempotent).
    Always increments installation_count on the listing.
    """
    from alchemi.db.copilot_db import get_pool

    resolved_account_id = _resolve_optional_account_filter(account_id)
    item = await _get_marketplace_item_for_read(item_id, resolved_account_id)
    if not item:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    item = _normalize_marketplace_item(item)
    is_admin = _is_admin_actor(_auth)
    if not is_admin and not _is_item_visible_to_subject(item, _auth, resolved_account_id):
        raise HTTPException(status_code=403, detail="Marketplace item is not assigned to this user.")

    installed_agent = None
    if resolved_account_id and is_admin:
        installed_agent = await _ensure_account_agent_install(item, resolved_account_id)

    assignments = _normalize_assignments(
        payload.assignments if payload else None,
        resolved_account_id,
    )
    effective_item_id = item_id
    if assignments:
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only account admins can update marketplace assignments.",
            )
        if resolved_account_id and not is_super_admin() and not item.get("account_id"):
            item = await _upsert_account_marketplace_item_copy(
                source_item=item,
                account_id=resolved_account_id,
                assignments=assignments,
            )
            effective_item_id = item["marketplace_id"]
        else:
            item = _normalize_marketplace_item(
                await _save_assignments_on_item(item_id, item, assignments)
            )
            effective_item_id = item.get("marketplace_id", item_id)

    pool = await get_pool()
    if resolved_account_id and not is_super_admin():
        row = await pool.fetchrow(
            """
            UPDATE copilot.marketplace_items
            SET installation_count = COALESCE(installation_count, 0) + 1,
                updated_at = now()
            WHERE marketplace_id = $1
              AND (account_id = $2 OR account_id IS NULL)
            RETURNING *
            """,
            effective_item_id,
            resolved_account_id,
        )
    else:
        row = await pool.fetchrow(
            """
            UPDATE copilot.marketplace_items
            SET installation_count = COALESCE(installation_count, 0) + 1,
                updated_at = now()
            WHERE marketplace_id = $1
            RETURNING *
            """,
            effective_item_id,
        )
    result = dict(row) if row else None
    if not result:
        raise HTTPException(status_code=404, detail="Marketplace item not found.")
    result = _normalize_marketplace_item(result)
    await log_copilot_audit_event(
        account_id=resolved_account_id,
        event_type="copilot_marketplace_install",
        resource_type="marketplace_item",
        resource_id=str(effective_item_id),
        action="install",
        message=f"Installed marketplace item '{item.get('title') or item_id}'.",
        details={
            "assignments_updated": bool(assignments),
            "installed_agent_id": (installed_agent or {}).get("agent_id") if isinstance(installed_agent, dict) else None,
        },
        request=request,
    )
    if assignments:
        result["metadata"] = item.get("metadata")
    return {"data": result, "installed_agent": installed_agent}
