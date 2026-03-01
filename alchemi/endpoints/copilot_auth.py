"""
Shared auth dependencies for copilot management endpoints.
"""
from typing import Any, Dict

import asyncpg
import jwt as pyjwt
import os
from fastapi import HTTPException, Request

from alchemi.auth.super_admin import is_super_admin_zitadel
from alchemi.middleware.account_middleware import (
    _get_master_key,
    decode_jwt_token,
    extract_token_from_request,
    resolve_tenant_from_request,
)
from alchemi.middleware.tenant_context import (
    get_current_account_id,
    is_super_admin,
    set_current_account_id,
    set_super_admin,
)

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

_COPILOT_READ_ONLY_ROLES = {
    "proxy_admin_viewer",
    "proxy_admin_view_only",
    "read_only",
    "viewer",
}

_COPILOT_END_USER_ROLES = {
    "internal_user",
    "internal_user_viewer",
    "user",
    "member",
    "viewer",
    "guest",
    "end_user",
    "app_user",
    "account_user",
}

_identity_pool: asyncpg.Pool | None = None


def _decode_unverified_identity_token(token: str) -> Dict[str, Any]:
    try:
        claims = pyjwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


async def _resolve_identity_token_to_copilot_claims(token: str) -> Dict[str, Any]:
    """
    Resolve non-LiteLLM JWTs (e.g. Zitadel access tokens) to a copilot auth context.
    """
    claims = _decode_unverified_identity_token(token)
    if not claims:
        return {}

    raw_email = (
        claims.get("email")
        or claims.get("urn:zitadel:iam:user:email")
        or claims.get("urn:zitadel:iam:user:preferred_username")
        or claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("username")
    )
    email = str(raw_email or "").strip().lower()
    sub = str(
        claims.get("sub")
        or claims.get("urn:zitadel:iam:user:id")
        or claims.get("user_id")
        or claims.get("uid")
        or ""
    ).strip()

    from litellm.proxy.proxy_server import prisma_client

    user_row: Dict[str, Any] = {}

    if prisma_client is not None:
        user = None
        if sub:
            try:
                user = await prisma_client.db.litellm_usertable.find_unique(
                    where={"user_id": sub}
                )
            except Exception:
                user = None

        if user is None and sub:
            try:
                user = await prisma_client.db.litellm_usertable.find_unique(
                    where={"sso_user_id": sub}
                )
            except Exception:
                user = None

        if user is None and email:
            try:
                user = await prisma_client.db.litellm_usertable.find_first(
                    where={"user_email": {"equals": email, "mode": "insensitive"}}
                )
            except Exception:
                user = None

        if user is not None:
            user_row = {
                "user_id": getattr(user, "user_id", None),
                "user_email": getattr(user, "user_email", None),
                "user_role": getattr(user, "user_role", None),
                "account_id": getattr(user, "account_id", None),
                "teams": getattr(user, "teams", None),
                "team_id": getattr(user, "team_id", None),
                "organization_id": getattr(user, "organization_id", None),
            }

    if not user_row:
        db_url = os.getenv("DATABASE_URL", "").strip()
        if not db_url:
            return {}
        global _identity_pool
        if _identity_pool is None:
            try:
                _identity_pool = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=5)
            except Exception:
                return {}

        where_sql = ""
        params = []
        idx = 1
        if sub:
            where_sql = f"user_id = ${idx}"
            params.append(sub)
            idx += 1
            where_sql += f" OR sso_user_id = ${idx}"
            params.append(sub)
            idx += 1
        if email:
            if where_sql:
                where_sql += f" OR lower(user_email) = lower(${idx})"
            else:
                where_sql = f"lower(user_email) = lower(${idx})"
            params.append(email)
        if not where_sql:
            return {}

        query = (
            'SELECT user_id, user_email, user_role, account_id, teams, team_id, organization_id '
            'FROM "LiteLLM_UserTable" '
            f"WHERE {where_sql} "
            "ORDER BY updated_at DESC "
            "LIMIT 1"
        )
        try:
            async with _identity_pool.acquire() as conn:
                row = await conn.fetchrow(query, *params)
        except Exception:
            return {}
        if row:
            user_row = dict(row)

    if not user_row:
        return {}

    resolved_email = (str(user_row.get("user_email") or "") or email).strip().lower()
    resolved_account_id = user_row.get("account_id")
    resolved_role = str(user_row.get("user_role", "") or "").strip().lower() or "user"
    resolved_teams = [
        str(team_id).strip()
        for team_id in (user_row.get("teams") or [])
        if str(team_id).strip()
    ]

    # Derive organization scope ids from team membership for SCIM-backed identities.
    # LiteLLM_UserTable.organization_id is often null even when teams are linked to orgs.
    organization_ids: list[str] = []
    raw_org_id = str(user_row.get("organization_id") or "").strip()
    if raw_org_id:
        organization_ids.append(raw_org_id)

    if resolved_account_id and resolved_teams:
        if prisma_client is not None:
            try:
                team_rows = await prisma_client.db.litellm_teamtable.find_many(
                    where={
                        "account_id": resolved_account_id,
                        "team_id": {"in": resolved_teams},
                    }
                )
                for team_row in team_rows:
                    org_id = str(getattr(team_row, "organization_id", "") or "").strip()
                    if org_id:
                        organization_ids.append(org_id)
            except Exception:
                pass
        elif _identity_pool is not None:
            try:
                async with _identity_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT organization_id
                        FROM "LiteLLM_TeamTable"
                        WHERE account_id = $1
                          AND team_id = ANY($2::text[])
                        """,
                        resolved_account_id,
                        resolved_teams,
                    )
                for row in rows:
                    org_id = str(row.get("organization_id") or "").strip()
                    if org_id:
                        organization_ids.append(org_id)
            except Exception:
                pass

    organization_ids = list(dict.fromkeys([org for org in organization_ids if org]))
    resolved_org_id = raw_org_id or (organization_ids[0] if organization_ids else None)
    is_super = bool(resolved_email and is_super_admin_zitadel(resolved_email))

    if is_super:
        set_super_admin(True)
        set_current_account_id(None)
    else:
        set_current_account_id(resolved_account_id)

    return {
        "user_id": user_row.get("user_id"),
        "user_email": resolved_email,
        "user_role": resolved_role,
        "account_id": resolved_account_id,
        "teams": resolved_teams,
        "team_id": user_row.get("team_id"),
        "organization_id": resolved_org_id,
        "organization_ids": organization_ids,
        "is_super_admin": is_super,
        "login_method": "identity_token",
    }


async def _decode_request_token(request: Request) -> Dict[str, Any]:
    token = extract_token_from_request(request)
    if not token:
        raise HTTPException(status_code=403, detail="Authentication required.")

    # Accept raw LiteLLM master key as super-admin auth for service-to-service calls.
    master_key = _get_master_key()
    env_master_key = os.getenv("LITELLM_MASTER_KEY", "").strip()
    if (master_key and token == master_key) or (env_master_key and token == env_master_key):
        set_super_admin(True)
        set_current_account_id(None)
        return {
            "user_role": "proxy_admin",
            "is_super_admin": True,
            "login_method": "master_key",
        }

    decoded = decode_jwt_token(token, master_key)
    if decoded:
        if decoded.get("is_super_admin", False):
            set_super_admin(True)
            set_current_account_id(None)
        elif decoded.get("account_id"):
            set_current_account_id(decoded.get("account_id"))
        return decoded

    decoded = await _resolve_identity_token_to_copilot_claims(token)
    if not decoded:
        raise HTTPException(status_code=403, detail="Invalid authentication token.")
    return decoded


async def _require_copilot_access(
    request: Request,
    allow_read_only: bool,
    allow_end_user: bool = False,
) -> Dict[str, Any]:
    """
    Require super admin or tenant-scoped copilot admin role.
    """
    if not is_super_admin() and get_current_account_id() is None:
        resolve_tenant_from_request(request)

    decoded = await _decode_request_token(request)
    if is_super_admin() or bool(decoded.get("is_super_admin", False)):
        return decoded

    if get_current_account_id() is None:
        decoded_account_id = decoded.get("account_id")
        if decoded_account_id:
            set_current_account_id(str(decoded_account_id))
        else:
            # Backward compatibility: older UI JWTs may not carry account_id.
            # Resolve by email before rejecting.
            decoded_email = str(decoded.get("user_email") or "").strip().lower()
            if decoded_email:
                try:
                    from alchemi.auth.account_resolver import resolve_account_for_user
                    from litellm.proxy.proxy_server import prisma_client

                    fallback_account_id = await resolve_account_for_user(
                        decoded_email, prisma_client
                    )
                    if fallback_account_id:
                        set_current_account_id(str(fallback_account_id))
                        decoded["account_id"] = str(fallback_account_id)
                except Exception:
                    pass

            if get_current_account_id() is None:
                raise HTTPException(status_code=403, detail="Authentication required.")

    user_role = str(decoded.get("user_role", "")).strip().lower()
    if user_role in _COPILOT_ADMIN_ROLES:
        return decoded
    if allow_read_only and user_role in _COPILOT_READ_ONLY_ROLES:
        return decoded
    if allow_end_user and user_role in _COPILOT_END_USER_ROLES:
        return decoded

    raise HTTPException(
        status_code=403,
        detail="Copilot management requires account admin privileges.",
    )


async def require_copilot_admin_access(request: Request) -> Dict[str, Any]:
    return await _require_copilot_access(request, allow_read_only=False)


async def require_copilot_read_access(request: Request) -> Dict[str, Any]:
    return await _require_copilot_access(request, allow_read_only=True)


async def require_copilot_marketplace_access(request: Request) -> Dict[str, Any]:
    """
    Marketplace read/install endpoints are used by end users from alchemi-web.
    Allow tenant end-user roles while still requiring valid tenant auth.
    """
    return await _require_copilot_access(
        request,
        allow_read_only=True,
        allow_end_user=True,
    )


async def require_copilot_user_access(request: Request) -> Dict[str, Any]:
    """
    Any authenticated tenant user (admin/viewer/end-user) can access user-facing
    Copilot read endpoints.
    """
    return await _require_copilot_access(
        request,
        allow_read_only=True,
        allow_end_user=True,
    )
