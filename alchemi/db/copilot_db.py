"""Copilot persistence helpers.

Uses LiteLLM_Config as a namespaced KV store for Copilot-specific data where
we do not yet have dedicated normalized tables.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


COPILOT_NS = "copilot"


def _require_prisma():
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise RuntimeError("Database not connected")
    return prisma_client


def make_key(resource: str, account_id: Optional[str] = None, object_id: Optional[str] = None) -> str:
    parts = [COPILOT_NS, resource]
    if account_id:
        parts.append(account_id)
    if object_id:
        parts.append(object_id)
    return ":".join(parts)


async def kv_put(
    resource: str,
    payload: Dict[str, Any],
    *,
    account_id: Optional[str] = None,
    object_id: Optional[str] = None,
) -> Dict[str, Any]:
    prisma = _require_prisma()
    key = make_key(resource, account_id, object_id)
    data = {
        "param_name": key,
        "param_value": payload,
        "account_id": account_id,
    }

    existing = await prisma.db.litellm_config.find_unique(where={"param_name": key})
    if existing:
        row = await prisma.db.litellm_config.update(
            where={"param_name": key},
            data={"param_value": payload, "account_id": account_id},
        )
    else:
        row = await prisma.db.litellm_config.create(data=data)
    return {"key": row.param_name, "value": row.param_value, "account_id": row.account_id}


async def kv_get(
    resource: str,
    *,
    account_id: Optional[str] = None,
    object_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    prisma = _require_prisma()
    key = make_key(resource, account_id, object_id)
    row = await prisma.db.litellm_config.find_unique(where={"param_name": key})
    if row is None:
        return None
    return {"key": row.param_name, "value": row.param_value, "account_id": row.account_id}


async def kv_delete(
    resource: str,
    *,
    account_id: Optional[str] = None,
    object_id: Optional[str] = None,
) -> bool:
    prisma = _require_prisma()
    key = make_key(resource, account_id, object_id)
    row = await prisma.db.litellm_config.find_unique(where={"param_name": key})
    if row is None:
        return False
    await prisma.db.litellm_config.delete(where={"param_name": key})
    return True


async def kv_list(
    resource: str,
    *,
    account_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    prisma = _require_prisma()

    prefix = make_key(resource, account_id)
    rows = await prisma.db.litellm_config.find_many(
        where={"account_id": account_id} if account_id is not None else None,
        order={"param_name": "asc"},
    )

    out: List[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row.param_name, str) and row.param_name.startswith(prefix):
            out.append({
                "key": row.param_name,
                "value": row.param_value,
                "account_id": row.account_id,
            })
    return out


async def append_audit_event(account_id: str, event: Dict[str, Any]) -> None:
    """Append a Copilot audit event to account-scoped audit namespace."""
    from datetime import datetime, timezone
    import uuid

    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    await kv_put("audit-event", payload, account_id=account_id, object_id=event_id)
