"""Shared helpers for Copilot endpoint modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

DOMAIN_KEY = "alchemi_domain"
COPILOT_DOMAIN = "copilot"


def require_prisma():
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    return prisma_client


def is_copilot_meta(metadata: Any) -> bool:
    return isinstance(metadata, dict) and metadata.get(DOMAIN_KEY) == COPILOT_DOMAIN


def mark_copilot_meta(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(metadata or {})
    out[DOMAIN_KEY] = COPILOT_DOMAIN
    return out


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
