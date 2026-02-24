"""
Guardrails configuration and custom pattern management endpoints.
Supports per-guard-type config, custom detection patterns, and immutable audit logging.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_auth import require_copilot_admin_access
from alchemi.endpoints.copilot_types import (
    ActionOnFail,
    GuardType,
    GuardrailsConfigUpsert,
    GuardrailsPatternCreate,
    GuardrailsPatternUpdate,
)

router = APIRouter(prefix="/copilot/guardrails", tags=["Copilot - Guardrails"])


def _get_user_id(request: Request) -> Optional[str]:
    """Extract user_id from JWT token."""
    from alchemi.middleware.account_middleware import decode_jwt_token, extract_token_from_request, _get_master_key

    token = extract_token_from_request(request)
    if token:
        decoded = decode_jwt_token(token, _get_master_key())
        if decoded:
            return decoded.get("user_id")
    return None


def _resolve_account_scope(
    account_id: Optional[str],
    require_for_super_admin: bool = False,
) -> Optional[str]:
    from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

    if is_super_admin():
        if account_id:
            return account_id
        current = get_current_account_id()
        if current:
            return current
        if require_for_super_admin:
            raise HTTPException(
                status_code=400,
                detail="account_id is required for this super admin operation.",
            )
        return None

    current = get_current_account_id()
    if not current:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return current


# ============================================
# Guard Configuration
# ============================================


@router.get("/config")
async def list_guardrails_config(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """List all guardrail configs for the current account."""
    resolved_account_id = _resolve_account_scope(account_id)
    where = {"account_id": resolved_account_id} if resolved_account_id else None
    configs = await copilot_db.guardrails_config.find_many(
        where=where,
        order_by="execution_order ASC",
    )
    return {"data": configs}


@router.get("/config/{guard_type}")
async def get_guardrails_config(
    guard_type: GuardType,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Get config for a specific guard type."""
    resolved_account_id = _resolve_account_scope(account_id, require_for_super_admin=True)
    configs = await copilot_db.guardrails_config.find_many(
        where={"account_id": resolved_account_id, "guard_type": guard_type.value},
    )
    if not configs:
        # Return default config if none exists
        return {
            "data": {
                "guard_type": guard_type.value,
                "enabled": False,
                "execution_order": 1,
                "action_on_fail": ActionOnFail.LOG_ONLY.value,
                "config": {},
            }
        }
    return {"data": configs[0]}


@router.put("/config/{guard_type}")
async def upsert_guardrails_config(
    guard_type: GuardType,
    data: GuardrailsConfigUpsert,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create or update config for a guard type. Auto-creates audit entry."""
    user_id = _get_user_id(request)
    resolved_account_id = _resolve_account_scope(account_id, require_for_super_admin=True)

    # Check if config already exists
    existing = await copilot_db.guardrails_config.find_many(
        where={"account_id": resolved_account_id, "guard_type": guard_type.value},
    )

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "action_on_fail" in update_data:
        update_data["action_on_fail"] = update_data["action_on_fail"].value

    if existing:
        old_config = existing[0]

        # Create audit entry before updating
        await copilot_db.guardrails_audit_log.create(
            data={
                "account_id": resolved_account_id,
                "guard_type": guard_type.value,
                "action": "update",
                "old_config": _safe_serialize(old_config),
                "new_config": _safe_serialize(update_data),
                "changed_by": user_id,
            }
        )

        config = await copilot_db.guardrails_config.update(
            old_config["id"], update_data
        )
    else:
        create_data = {
            "account_id": resolved_account_id,
            "guard_type": guard_type.value,
            "enabled": data.enabled if data.enabled is not None else False,
            "execution_order": data.execution_order if data.execution_order is not None else 1,
            "action_on_fail": data.action_on_fail.value if data.action_on_fail else ActionOnFail.LOG_ONLY.value,
            "config": data.config if data.config is not None else {},
        }

        # Create audit entry
        await copilot_db.guardrails_audit_log.create(
            data={
                "account_id": resolved_account_id,
                "guard_type": guard_type.value,
                "action": "create",
                "old_config": None,
                "new_config": _safe_serialize(create_data),
                "changed_by": user_id,
            }
        )

        config = await copilot_db.guardrails_config.create(data=create_data)

    return {"data": config}


@router.patch("/config/{guard_type}/toggle")
async def toggle_guardrails_config(
    guard_type: GuardType,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Toggle enabled/disabled for a guard type."""
    user_id = _get_user_id(request)
    resolved_account_id = _resolve_account_scope(account_id, require_for_super_admin=True)

    existing = await copilot_db.guardrails_config.find_many(
        where={"account_id": resolved_account_id, "guard_type": guard_type.value},
    )

    if not existing:
        # Create a new config in enabled state
        config = await copilot_db.guardrails_config.create(
            data={
                "account_id": resolved_account_id,
                "guard_type": guard_type.value,
                "enabled": True,
                "execution_order": 1,
                "action_on_fail": ActionOnFail.LOG_ONLY.value,
                "config": {},
            }
        )
        await copilot_db.guardrails_audit_log.create(
            data={
                "account_id": resolved_account_id,
                "guard_type": guard_type.value,
                "action": "enable",
                "old_config": None,
                "new_config": {"enabled": True},
                "changed_by": user_id,
            }
        )
        return {"data": config}

    old = existing[0]
    new_enabled = not old.get("enabled", False)

    await copilot_db.guardrails_audit_log.create(
        data={
            "account_id": resolved_account_id,
            "guard_type": guard_type.value,
            "action": f"{'enable' if new_enabled else 'disable'}",
            "old_config": {"enabled": old.get("enabled")},
            "new_config": {"enabled": new_enabled},
            "changed_by": user_id,
        }
    )

    config = await copilot_db.guardrails_config.update(
        old["id"], {"enabled": new_enabled}
    )
    return {"data": config}


# ============================================
# Custom Patterns
# ============================================


@router.get("/patterns")
async def list_patterns(
    request: Request,
    account_id: Optional[str] = None,
    guard_type: Optional[GuardType] = None,
    enabled: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_admin_access),
):
    """List custom detection patterns with optional filters."""
    where = {}
    resolved_account_id = _resolve_account_scope(account_id)
    if resolved_account_id:
        where["account_id"] = resolved_account_id
    if guard_type:
        where["guard_type"] = guard_type.value
    if enabled is not None:
        where["enabled"] = enabled

    patterns = await copilot_db.guardrails_custom_patterns.find_many(
        where=where if where else None,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.guardrails_custom_patterns.count(
        where=where if where else None
    )

    return {"data": patterns, "total": total}


@router.post("/patterns")
async def create_pattern(
    data: GuardrailsPatternCreate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Create a custom detection pattern."""
    user_id = _get_user_id(request)
    resolved_account_id = _resolve_account_scope(account_id, require_for_super_admin=True)

    create_data = data.model_dump()
    # Convert enums to string values
    create_data["account_id"] = resolved_account_id
    create_data["guard_type"] = create_data["guard_type"].value
    create_data["pattern_type"] = create_data["pattern_type"].value
    create_data["action"] = create_data["action"].value
    create_data["severity"] = create_data["severity"].value
    create_data["created_by"] = user_id

    pattern = await copilot_db.guardrails_custom_patterns.create(data=create_data)

    # Audit log
    await copilot_db.guardrails_audit_log.create(
        data={
            "account_id": resolved_account_id,
            "guard_type": data.guard_type.value,
            "action": "create",
            "old_config": None,
            "new_config": {"pattern_name": data.pattern_name},
            "changed_by": user_id,
        }
    )

    return {"data": pattern}


@router.put("/patterns/{pattern_id}")
async def update_pattern(
    pattern_id: str,
    data: GuardrailsPatternUpdate,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Update a custom detection pattern."""
    existing = await copilot_db.guardrails_custom_patterns.find_by_id(pattern_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pattern not found.")
    expected_account_id = _resolve_account_scope(
        account_id, require_for_super_admin=True
    )
    if existing.get("account_id") != expected_account_id:
        raise HTTPException(status_code=404, detail="Pattern not found.")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    # Convert enums to string values
    for field in ("pattern_type", "action", "severity"):
        if field in update_data and hasattr(update_data[field], "value"):
            update_data[field] = update_data[field].value

    user_id = _get_user_id(request)

    pattern = await copilot_db.guardrails_custom_patterns.update(
        pattern_id, update_data
    )
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found.")

    # Audit log
    await copilot_db.guardrails_audit_log.create(
        data={
            "account_id": existing.get("account_id"),
            "guard_type": existing.get("guard_type", "unknown"),
            "action": "update",
            "old_config": {"pattern_name": existing.get("pattern_name")},
            "new_config": _safe_serialize(update_data),
            "changed_by": user_id,
        }
    )

    return {"data": pattern}


@router.delete("/patterns/{pattern_id}")
async def delete_pattern(
    pattern_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """Delete a custom detection pattern."""
    existing = await copilot_db.guardrails_custom_patterns.find_by_id(pattern_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pattern not found.")
    expected_account_id = _resolve_account_scope(
        account_id, require_for_super_admin=True
    )
    if existing.get("account_id") != expected_account_id:
        raise HTTPException(status_code=404, detail="Pattern not found.")

    user_id = _get_user_id(request)

    deleted = await copilot_db.guardrails_custom_patterns.delete(pattern_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pattern not found.")

    # Audit log
    await copilot_db.guardrails_audit_log.create(
        data={
            "account_id": existing.get("account_id"),
            "guard_type": existing.get("guard_type", "unknown"),
            "action": "delete",
            "old_config": {"pattern_name": existing.get("pattern_name")},
            "new_config": None,
            "changed_by": user_id,
        }
    )

    return {"status": "ok"}


# ============================================
# Audit Log
# ============================================


@router.get("/audit")
async def list_audit_log(
    request: Request,
    account_id: Optional[str] = None,
    guard_type: Optional[GuardType] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    _auth=Depends(require_copilot_admin_access),
):
    """List guardrail audit log entries with pagination and optional date range."""
    resolved_account_id = _resolve_account_scope(account_id)

    # Build raw query for date range support
    conditions = []
    params = []
    idx = 1

    if resolved_account_id:
        conditions.append(f"account_id = ${idx}")
        params.append(resolved_account_id)
        idx += 1

    if guard_type:
        conditions.append(f"guard_type = ${idx}")
        params.append(guard_type.value)
        idx += 1

    if date_from:
        conditions.append(f"changed_at >= ${idx}::timestamptz")
        params.append(date_from)
        idx += 1

    if date_to:
        conditions.append(f"changed_at <= ${idx}::timestamptz")
        params.append(date_to)
        idx += 1

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Count query
    count_query = f"SELECT COUNT(*) FROM copilot.guardrails_audit_log {where_clause}"
    total = await copilot_db.guardrails_audit_log.execute_raw_val(
        count_query, *params
    )

    # Data query
    params.append(limit)
    params.append(offset)
    data_query = (
        f"SELECT * FROM copilot.guardrails_audit_log {where_clause} "
        f"ORDER BY changed_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    )
    entries = await copilot_db.guardrails_audit_log.execute_raw(
        data_query, *params
    )

    return {"data": entries, "total": total}


# ============================================
# Helpers
# ============================================


def _safe_serialize(obj: dict) -> dict:
    """Make a dict JSON-serializable by converting non-standard types."""
    result = {}
    for k, v in obj.items():
        if isinstance(v, datetime):
            result[k] = v.isoformat()
        elif hasattr(v, "value"):
            result[k] = v.value
        else:
            result[k] = v
    return result
