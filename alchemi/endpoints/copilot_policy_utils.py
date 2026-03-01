"""
Shared helpers for Copilot scoped policy resolution.

These helpers keep inheritance semantics consistent across model access,
feature flags, and connection permission policies.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from alchemi.db import copilot_db
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

ALLOWED_SCOPE_TYPES = {"account", "group", "team", "user"}

_COPILOT_ADMIN_ROLES = {
    "proxy_admin",
    "app_admin",
    "org_admin",
    "app_owner",
    "demo_app_owner",
    "admin",
    "tenant_admin",
    "owner",
}


def _is_uuid_like(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def is_admin_claims(claims: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(claims, dict):
        return False
    if bool(claims.get("is_super_admin")):
        return True
    role = str(claims.get("user_role") or "").strip().lower()
    return role in _COPILOT_ADMIN_ROLES


def normalize_scope_type(scope_type: str) -> str:
    value = str(scope_type or "").strip().lower()
    if value not in ALLOWED_SCOPE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="scope_type must be one of: account, group, team, user.",
        )
    return value


def resolve_account_scope(
    account_id: Optional[str],
    require_for_super_admin: bool = False,
) -> Optional[str]:
    """
    Resolve account scope from tenant context + optional query/body account_id.
    """
    if is_super_admin():
        if account_id:
            return str(account_id)
        current = get_current_account_id()
        if current:
            return str(current)
        if require_for_super_admin:
            raise HTTPException(
                status_code=400,
                detail="account_id is required for this super admin operation.",
            )
        return None

    current = get_current_account_id()
    if not current:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    if account_id and str(account_id) != str(current):
        raise HTTPException(status_code=403, detail="Cannot access a different account scope.")
    return str(current)


async def resolve_team_group(account_id: str, team_id: Optional[str]) -> Optional[str]:
    if not team_id:
        return None
    tid = str(team_id).strip()
    if not tid:
        return None

    # Copilot-local directory first
    local_team = await copilot_db.teams.find_by_id(tid)
    if local_team and str(local_team.get("account_id") or "") == str(account_id):
        gid = str(local_team.get("group_id") or "").strip()
        if gid:
            return gid

    # Identity source fallback
    try:
        from litellm.proxy.proxy_server import prisma_client

        if prisma_client is None:
            return None
        team = await prisma_client.db.litellm_teamtable.find_first(
            where={"account_id": str(account_id), "team_id": tid}
        )
        org_id = str(getattr(team, "organization_id", "") or "").strip() if team else ""
        return org_id or None
    except Exception:
        return None


async def resolve_user_hierarchy(
    account_id: str,
    user_id: str,
    claims: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    uid = str(user_id or "").strip()
    if not uid:
        return None, None

    # Prefer explicit claim hierarchy when the requested user matches actor.
    if isinstance(claims, dict) and str(claims.get("user_id") or "").strip() == uid:
        team_candidates: List[str] = []
        claim_team_id = str(claims.get("team_id") or "").strip()
        if claim_team_id:
            team_candidates.append(claim_team_id)
        for team_id in (claims.get("teams") or []):
            parsed = str(team_id or "").strip()
            if parsed:
                team_candidates.append(parsed)
        if team_candidates:
            team_id = list(dict.fromkeys(team_candidates))[0]
            group_id = await resolve_team_group(account_id, team_id)
            if not group_id:
                org_candidates = []
                org_direct = str(claims.get("organization_id") or "").strip()
                if org_direct:
                    org_candidates.append(org_direct)
                for org_id in (claims.get("organization_ids") or []):
                    parsed = str(org_id or "").strip()
                    if parsed:
                        org_candidates.append(parsed)
                if org_candidates:
                    group_id = list(dict.fromkeys(org_candidates))[0]
            return team_id, group_id

    # Copilot-local memberships store user_id as UUID in current schema.
    # Skip this lookup for non-UUID user IDs to avoid asyncpg type errors.
    memberships: List[Dict[str, Any]] = []
    if _is_uuid_like(uid):
        memberships = await copilot_db.account_memberships.find_many(
            where={"account_id": str(account_id), "user_id": uid, "is_active": True},
            order_by="updated_at DESC",
            limit=1,
        )
    if memberships:
        team_id = str(memberships[0].get("team_id") or "").strip() or None
        group_id = await resolve_team_group(account_id, team_id)
        return team_id, group_id

    # Identity source fallback
    try:
        from litellm.proxy.proxy_server import prisma_client

        if prisma_client is None:
            return None, None

        identity_user = await prisma_client.db.litellm_usertable.find_first(
            where={"account_id": str(account_id), "user_id": uid}
        )
        if not identity_user:
            identity_user = await prisma_client.db.litellm_usertable.find_first(
                where={"account_id": str(account_id), "user_email": {"equals": uid, "mode": "insensitive"}}
            )
        if not identity_user:
            return None, None

        teams = getattr(identity_user, "teams", None) or []
        team_id = str(teams[0]).strip() if len(teams) > 0 and str(teams[0]).strip() else None
        group_id = await resolve_team_group(account_id, team_id)
        if not group_id:
            group_id = str(getattr(identity_user, "organization_id", "") or "").strip() or None
        return team_id, group_id
    except Exception:
        return None, None


async def resolve_scope_chain(
    account_id: str,
    scope_type: str,
    scope_id: str,
    claims: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """
    Resolve inheritance chain for a requested scope.

    Returned order is specific -> broader:
    user -> team -> group -> account
    team -> group -> account
    group -> account
    account
    """
    st = normalize_scope_type(scope_type)
    sid = str(scope_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="scope_id is required.")

    chain: List[Tuple[str, str]] = []

    if st == "account":
        if sid != str(account_id):
            raise HTTPException(status_code=400, detail="Account scope_id must match account_id.")
        chain = [("account", sid)]
    elif st == "group":
        chain = [("group", sid), ("account", str(account_id))]
    elif st == "team":
        chain = [("team", sid)]
        group_id = await resolve_team_group(account_id, sid)
        if group_id:
            chain.append(("group", group_id))
        chain.append(("account", str(account_id)))
    else:
        chain = [("user", sid)]
        team_id, group_id = await resolve_user_hierarchy(account_id, sid, claims=claims)
        if team_id:
            chain.append(("team", str(team_id)))
        if group_id:
            chain.append(("group", str(group_id)))
        chain.append(("account", str(account_id)))

    seen = set()
    deduped: List[Dict[str, str]] = []
    for scope_t, scope_i in chain:
        key = f"{scope_t}:{scope_i}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"scope_type": scope_t, "scope_id": str(scope_i)})
    return deduped
