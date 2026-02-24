"""
Helpers for writing Copilot-scoped audit events.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request

from alchemi.db import copilot_db


def _parse_actor_from_request(request: Optional[Request]) -> Dict[str, Optional[str]]:
    if request is None:
        return {"user_id": None, "user_email": None}

    try:
        from alchemi.middleware.account_middleware import (
            _get_master_key,
            decode_jwt_token,
            extract_token_from_request,
        )

        token = extract_token_from_request(request)
        if not token:
            return {"user_id": None, "user_email": None}

        decoded = decode_jwt_token(token, _get_master_key())
        if not decoded:
            return {"user_id": None, "user_email": None}

        user_id = decoded.get("user_id") or decoded.get("sub")
        user_email = decoded.get("user_email") or decoded.get("email")
        return {
            "user_id": str(user_id) if user_id else None,
            "user_email": str(user_email) if user_email else None,
        }
    except Exception:
        return {"user_id": None, "user_email": None}


async def log_copilot_audit_event(
    *,
    account_id: Optional[str],
    event_type: str,
    message: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    severity: str = "info",
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    """Best-effort audit write. Never raises to callers."""
    try:
        actor = _parse_actor_from_request(request)
        payload: Dict[str, Any] = {
            "event_type": str(event_type or "copilot_event")[:64],
            "severity": str(severity or "info").lower(),
            "resource_type": str(resource_type)[:64] if resource_type else None,
            "resource_id": str(resource_id) if resource_id else None,
            "action": str(action)[:64] if action else None,
            "actor_id": actor.get("user_id"),
            "actor_email": actor.get("user_email"),
            "message": message,
            "details": details or {},
        }
        if account_id:
            payload["account_id"] = account_id

        await copilot_db.audit_log.create(payload)
    except Exception:
        # Observability should never block business flow.
        return
