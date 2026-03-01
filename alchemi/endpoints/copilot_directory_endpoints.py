"""
Copilot directory endpoints for account-scoped user management.
Includes users, memberships, groups, teams, team membership assignment, and invites.
"""
from datetime import datetime, timedelta, timezone
import secrets
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_auth import (
    require_copilot_admin_access,
    require_copilot_read_access,
)
from alchemi.endpoints.copilot_types import (
    CopilotGroupCreate,
    CopilotGroupUpdate,
    CopilotInviteCreate,
    CopilotInviteStatus,
    CopilotMembershipRole,
    CopilotMembershipUpdate,
    CopilotTeamCreate,
    CopilotTeamMemberAssign,
    CopilotTeamUpdate,
    CopilotUserCreate,
    CopilotUserUpdate,
)
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

router = APIRouter(prefix="/copilot", tags=["Copilot - Directory"])


def _model_dump(data: Any) -> Dict[str, Any]:
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_account_id(account_id: Optional[str]) -> str:
    if is_super_admin():
        if account_id:
            return account_id
        current = get_current_account_id()
        if current:
            return current
        raise HTTPException(
            status_code=400,
            detail="account_id is required for super admin requests.",
        )

    current = get_current_account_id()
    if not current:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    return current


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _user_name_from_email(email: str) -> str:
    left = email.split("@")[0].strip()
    if not left:
        return "User"
    return left.replace(".", " ").replace("_", " ").title()


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _is_identity_source(source: Optional[str]) -> bool:
    return str(source or "").strip().lower() in {"identity", "zitadel", "scim"}


def _map_identity_role_to_copilot(user_role: Optional[str]) -> str:
    role = str(user_role or "").strip().lower()
    if role in {"proxy_admin", "app_admin", "org_admin"}:
        return CopilotMembershipRole.ADMIN.value
    if role in {"proxy_admin_viewer", "internal_user_viewer", "internal_viewer"}:
        return CopilotMembershipRole.VIEWER.value
    if role in {"guest"}:
        return CopilotMembershipRole.GUEST.value
    return CopilotMembershipRole.USER.value


def _identity_unassigned_group_id(account_id: str) -> str:
    return f"identity:ungrouped:{account_id}"


async def _list_identity_users(
    account_id: str,
    is_active: Optional[bool],
    include_memberships: bool,
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected.")

    where: Dict[str, Any] = {"account_id": account_id}
    if is_active is None:
        users = await prisma_client.db.litellm_usertable.find_many(
            where=where,
            skip=offset,
            take=limit,
            order={"created_at": "desc"},
        )
        total = await prisma_client.db.litellm_usertable.count(where=where)
    else:
        all_users = await prisma_client.db.litellm_usertable.find_many(
            where=where,
            order={"created_at": "desc"},
        )
        filtered_users = []
        for user in all_users:
            metadata = user.metadata if isinstance(user.metadata, dict) else {}
            active = metadata.get("scim_active")
            if not isinstance(active, bool):
                active = True
            if active == is_active:
                filtered_users.append(user)
        total = len(filtered_users)
        users = filtered_users[offset : offset + limit]

    team_ids: List[str] = []
    for user in users:
        for team_id in (user.teams or []):
            if isinstance(team_id, str) and team_id.strip():
                team_ids.append(team_id.strip())
    team_ids = list(dict.fromkeys(team_ids))

    teams_by_id: Dict[str, Any] = {}
    if team_ids:
        teams = await prisma_client.db.litellm_teamtable.find_many(
            where={"account_id": account_id, "team_id": {"in": team_ids}}
        )
        teams_by_id = {str(t.team_id): t for t in teams}

    normalized_users: List[Dict[str, Any]] = []
    for user in users:
        metadata = user.metadata if isinstance(user.metadata, dict) else {}
        active = metadata.get("scim_active")
        if not isinstance(active, bool):
            active = True

        normalized: Dict[str, Any] = {
            "id": str(user.user_id),
            "account_id": user.account_id,
            "email": user.user_email or user.user_id,
            "name": user.user_alias or user.user_email or user.user_id,
            "profile_image": None,
            "is_active": active,
            "source": "identity",
            "sso_user_id": user.sso_user_id,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

        if include_memberships:
            memberships: List[Dict[str, Any]] = []
            user_team_ids = [tid for tid in (user.teams or []) if isinstance(tid, str)]
            for team_id in user_team_ids:
                team = teams_by_id.get(str(team_id))
                memberships.append(
                    {
                        "id": f"identity:{user.user_id}:{team_id}",
                        "account_id": account_id,
                        "user_id": str(user.user_id),
                        "app_role": _map_identity_role_to_copilot(user.user_role),
                        "team_id": str(team_id),
                        "is_active": active,
                        "joined_at": user.created_at,
                        "last_active_at": user.updated_at,
                        "created_at": user.created_at,
                        "updated_at": user.updated_at,
                        "team": {
                            "id": str(team.team_id),
                            "name": team.team_alias or str(team.team_id),
                            "group_id": team.organization_id,
                            "is_default": False,
                            "group": {
                                "id": team.organization_id,
                                "name": None,
                                "is_default": False,
                            }
                            if team and team.organization_id
                            else None,
                        }
                        if team
                        else None,
                    }
                )
            normalized["memberships"] = memberships

        normalized_users.append(normalized)

    return {"users": normalized_users, "total": total}


async def _reconcile_identity_users_for_account(account_id: str) -> int:
    """
    Best-effort backfill for identity users using domain/admin mapping.
    Also reassigns mismatched account_id rows to the resolved account.
    """
    from alchemi.auth.account_resolver import reconcile_identity_account_links
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        return 0
    updated = await reconcile_identity_account_links(
        account_id=account_id,
        prisma_client=prisma_client,
        reassign_mismatched=True,
    )
    return len(updated)


async def _list_identity_groups(
    account_id: str,
    search: Optional[str],
    include_teams: bool,
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected.")

    search_term = (search or "").strip().lower()
    unassigned_group_id = _identity_unassigned_group_id(account_id)

    orgs = await prisma_client.db.litellm_organizationtable.find_many(
        where={"account_id": account_id},
        order={"created_at": "desc"},
    )
    teams = await prisma_client.db.litellm_teamtable.find_many(
        where={"account_id": account_id},
        order={"created_at": "desc"},
    )

    org_rows: Dict[str, Dict[str, Any]] = {}
    teams_by_org: Dict[str, List[Dict[str, Any]]] = {}

    for org in orgs:
        org_id = str(org.organization_id)
        org_rows[org_id] = {
            "id": org_id,
            "account_id": org.account_id,
            "name": org.organization_alias or org_id,
            "description": None,
            "is_default": False,
            "status": "active",
            "source": "scim",
            "created_at": org.created_at,
            "updated_at": org.updated_at,
        }
        teams_by_org.setdefault(org_id, [])

    for team in teams:
        team_org_id = str(team.organization_id).strip() if team.organization_id else ""
        normalized_org_id = team_org_id or unassigned_group_id
        if normalized_org_id not in org_rows:
            org_rows[normalized_org_id] = {
                "id": normalized_org_id,
                "account_id": account_id,
                "name": team_org_id or "Unassigned (No SCIM Organization)",
                "description": None,
                "is_default": False,
                "status": "active",
                "source": "scim",
                "created_at": team.created_at,
                "updated_at": team.updated_at,
            }
        team_entry = {
            "id": str(team.team_id),
            "account_id": team.account_id,
            "group_id": normalized_org_id,
            "name": team.team_alias or str(team.team_id),
            "description": None,
            "is_default": False,
            "status": "active",
            "member_count": len(team.members or []),
        }
        teams_by_org.setdefault(normalized_org_id, []).append(team_entry)

    group_rows: List[Dict[str, Any]] = []
    for group_id, group_row in org_rows.items():
        if search_term and search_term not in str(group_row.get("name", "")).lower():
            continue
        team_items = teams_by_org.get(group_id, [])
        row: Dict[str, Any] = {
            **group_row,
            "team_count": len(team_items),
        }
        if include_teams:
            row["teams"] = team_items
        group_rows.append(row)

    group_rows.sort(
        key=lambda r: (
            r["id"] == unassigned_group_id,
            str(r.get("name") or "").lower(),
        )
    )
    total = len(group_rows)
    return {"groups": group_rows[offset : offset + limit], "total": total}


async def _list_identity_teams(
    account_id: str,
    group_id: Optional[str],
    search: Optional[str],
    include_members: bool,
    include_group: bool,
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected.")

    where: Dict[str, Any] = {"account_id": account_id}
    unassigned_group_id = _identity_unassigned_group_id(account_id)
    if group_id:
        if group_id == unassigned_group_id:
            where["organization_id"] = None
        else:
            where["organization_id"] = group_id
    if search and search.strip():
        where["team_alias"] = {"contains": search.strip(), "mode": "insensitive"}

    rows = await prisma_client.db.litellm_teamtable.find_many(
        where=where,
        skip=offset,
        take=limit,
        order={"created_at": "desc"},
    )
    total = await prisma_client.db.litellm_teamtable.count(where=where)

    org_map: Dict[str, Any] = {}
    if include_group:
        org_ids = list(
            dict.fromkeys([str(t.organization_id) for t in rows if t.organization_id])
        )
        if org_ids:
            orgs = await prisma_client.db.litellm_organizationtable.find_many(
                where={"account_id": account_id, "organization_id": {"in": org_ids}}
            )
            org_map = {str(o.organization_id): o for o in orgs}

    users_map: Dict[str, Any] = {}
    derived_team_members: Dict[str, List[str]] = {}
    if include_members:
        # Some SCIM sync paths only populate user.teams (not team.members).
        # Build membership from both sources and merge.
        users = await prisma_client.db.litellm_usertable.find_many(
            where={"account_id": account_id}
        )
        users_map = {str(u.user_id): u for u in users}
        for user in users:
            for team_id in (user.teams or []):
                if not isinstance(team_id, str) or not team_id.strip():
                    continue
                derived_team_members.setdefault(team_id.strip(), []).append(str(user.user_id))

    data: List[Dict[str, Any]] = []
    for team in rows:
        org_id = str(team.organization_id) if team.organization_id else None
        response_group_id = org_id or unassigned_group_id
        group = None
        if include_group:
            if org_id:
                org = org_map.get(org_id)
                group = {
                    "id": org_id,
                    "name": (org.organization_alias if org else None) or org_id,
                    "account_id": account_id,
                    "is_default": False,
                }
            else:
                group = {
                    "id": unassigned_group_id,
                    "name": "Unassigned (No SCIM Organization)",
                    "account_id": account_id,
                    "is_default": False,
                }

        members = None
        member_ids: List[str] = []
        if include_members:
            team_id_str = str(team.team_id)
            members_with_roles = (
                team.members_with_roles
                if isinstance(team.members_with_roles, list)
                else []
            )
            role_by_user_id: Dict[str, str] = {}
            mwr_ids: List[str] = []
            for item in members_with_roles:
                if not isinstance(item, dict):
                    continue
                uid = str(item.get("user_id") or "").strip()
                if not uid:
                    continue
                mwr_ids.append(uid)
                role_text = str(item.get("role") or "").strip().lower()
                if role_text:
                    role_by_user_id[uid] = role_text

            explicit_ids = [
                str(uid).strip()
                for uid in (team.members or [])
                if isinstance(uid, str) and str(uid).strip()
            ]
            derived_ids = derived_team_members.get(team_id_str, [])
            member_ids = list(dict.fromkeys(explicit_ids + mwr_ids + derived_ids))

            members = []
            for uid in member_ids:
                if not isinstance(uid, str):
                    continue
                user = users_map.get(uid)
                explicit_role = role_by_user_id.get(uid)
                if explicit_role == "admin":
                    app_role = CopilotMembershipRole.ADMIN.value
                elif explicit_role == "viewer":
                    app_role = CopilotMembershipRole.VIEWER.value
                elif explicit_role == "guest":
                    app_role = CopilotMembershipRole.GUEST.value
                elif explicit_role in {"member", "user"}:
                    app_role = CopilotMembershipRole.USER.value
                else:
                    app_role = _map_identity_role_to_copilot(
                        user.user_role if user else None
                    )
                members.append(
                    {
                        "id": f"identity:{uid}:{team.team_id}",
                        "account_id": account_id,
                        "user_id": uid,
                        "app_role": app_role,
                        "team_id": str(team.team_id),
                        "is_active": True,
                        "joined_at": team.created_at,
                        "last_active_at": team.updated_at,
                        "created_at": team.created_at,
                        "updated_at": team.updated_at,
                        "user": {
                            "id": uid,
                            "name": (user.user_alias if user else None) or uid,
                            "email": (user.user_email if user else None) or uid,
                            "profile_image": None,
                            "is_active": True,
                        },
                    }
                )

        data.append(
            {
                "id": str(team.team_id),
                "account_id": account_id,
                "group_id": response_group_id,
                "name": team.team_alias or str(team.team_id),
                "description": None,
                "is_default": False,
                "status": "active",
                "member_count": len(member_ids) if include_members else len(team.members or []),
                "source": "scim",
                "created_at": team.created_at,
                "updated_at": team.updated_at,
                "group": group,
                "members": members,
            }
        )

    return {"teams": data, "total": total}


async def _ensure_default_group_and_team(
    account_id: str,
    acting_user: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    default_groups = await copilot_db.groups.find_many(
        where={"account_id": account_id, "is_default": True},
        limit=1,
    )
    if default_groups:
        group = default_groups[0]
    else:
        group = await copilot_db.groups.create(
            data={
                "account_id": account_id,
                "name": "Global",
                "description": "Global default organization for all users",
                "is_default": True,
                "created_by": acting_user,
                "updated_by": acting_user,
            }
        )

    default_teams = await copilot_db.teams.find_many(
        where={"account_id": account_id, "group_id": group["id"], "is_default": True},
        limit=1,
    )
    if default_teams:
        team = default_teams[0]
    else:
        team = await copilot_db.teams.create(
            data={
                "account_id": account_id,
                "group_id": group["id"],
                "name": "Global",
                "description": "Global default team for all users",
                "is_default": True,
                "created_by": acting_user,
                "updated_by": acting_user,
            }
        )

    return {"group": group, "team": team}


async def _get_membership_for_user(
    account_id: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    rows = await copilot_db.account_memberships.execute_raw(
        """
        SELECT *
        FROM copilot.account_memberships
        WHERE account_id = $1 AND user_id = $2
        LIMIT 1
        """,
        account_id,
        user_id,
    )
    return rows[0] if rows else None


async def _get_user_by_email(account_id: str, email: str) -> Optional[Dict[str, Any]]:
    rows = await copilot_db.users.execute_raw(
        """
        SELECT *
        FROM copilot.users
        WHERE account_id = $1 AND lower(email) = lower($2)
        LIMIT 1
        """,
        account_id,
        email,
    )
    return rows[0] if rows else None


def _build_team_lookup(teams: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(t["id"]): t for t in teams}


def _parse_uuid_list(values: List[str]) -> List[uuid.UUID]:
    result: List[uuid.UUID] = []
    for v in values:
        try:
            result.append(uuid.UUID(str(v)))
        except Exception:
            continue
    return result


async def _list_memberships_with_joins(
    account_id: str,
    user_ids: Optional[List[str]] = None,
    team_id: Optional[str] = None,
    exclude_team_id: Optional[str] = None,
    active_only: Optional[bool] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    params: List[Any] = [account_id]
    where = ["m.account_id = $1"]

    if user_ids is not None:
        parsed_user_ids = _parse_uuid_list(user_ids)
        params.append(parsed_user_ids)
        where.append(f"m.user_id = ANY(${len(params)}::uuid[])")

    if team_id is not None:
        params.append(team_id)
        where.append(f"m.team_id = ${len(params)}")

    if exclude_team_id is not None:
        params.append(exclude_team_id)
        where.append(f"(m.team_id IS NULL OR m.team_id <> ${len(params)})")

    if active_only is not None:
        params.append(active_only)
        where.append(f"m.is_active = ${len(params)}")

    params.extend([limit, offset])
    sql = f"""
        SELECT
            m.*,
            u.id AS u_id,
            u.name AS u_name,
            u.email AS u_email,
            u.profile_image AS u_profile_image,
            u.is_active AS u_is_active,
            t.id AS t_id,
            t.name AS t_name,
            t.group_id AS t_group_id,
            t.is_default AS t_is_default,
            g.id AS g_id,
            g.name AS g_name,
            g.is_default AS g_is_default
        FROM copilot.account_memberships m
        LEFT JOIN copilot.users u ON u.id = m.user_id
        LEFT JOIN copilot.teams t ON t.id = m.team_id
        LEFT JOIN copilot.groups g ON g.id = t.group_id
        WHERE {' AND '.join(where)}
        ORDER BY m.joined_at ASC
        LIMIT ${len(params) - 1}
        OFFSET ${len(params)}
    """
    rows = await copilot_db.account_memberships.execute_raw(sql, *params)

    memberships: List[Dict[str, Any]] = []
    for row in rows:
        membership = {
            "id": row["id"],
            "account_id": row["account_id"],
            "user_id": row["user_id"],
            "app_role": row["app_role"],
            "team_id": row.get("team_id"),
            "is_active": row["is_active"],
            "joined_at": row["joined_at"],
            "last_active_at": row["last_active_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "user": {
                "id": row.get("u_id"),
                "name": row.get("u_name"),
                "email": row.get("u_email"),
                "profile_image": row.get("u_profile_image"),
                "is_active": row.get("u_is_active"),
            }
            if row.get("u_id")
            else None,
            "team": {
                "id": row.get("t_id"),
                "name": row.get("t_name"),
                "group_id": row.get("t_group_id"),
                "is_default": row.get("t_is_default"),
                "group": {
                    "id": row.get("g_id"),
                    "name": row.get("g_name"),
                    "is_default": row.get("g_is_default"),
                }
                if row.get("g_id")
                else None,
            }
            if row.get("t_id")
            else None,
        }
        memberships.append(membership)
    return memberships


# ============================================
# Users + Memberships
# ============================================


@router.get("/users")
async def list_users(
    request: Request,
    account_id: Optional[str] = None,
    source: Optional[str] = Query(default=None, description="Directory data source: identity/zitadel/scim or default copilot"),
    is_active: Optional[bool] = None,
    include_memberships: bool = False,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    if _is_identity_source(source):
        await _reconcile_identity_users_for_account(resolved_account_id)
        identity = await _list_identity_users(
            account_id=resolved_account_id,
            is_active=is_active,
            include_memberships=include_memberships,
            limit=limit,
            offset=offset,
        )
        return {"data": {"users": identity["users"], "total": identity["total"]}}

    where: Dict[str, Any] = {"account_id": resolved_account_id}
    if is_active is not None:
        where["is_active"] = is_active

    users = await copilot_db.users.find_many(
        where=where,
        order_by="created_at DESC",
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.users.count(where=where)

    if include_memberships and users:
        user_ids = [str(u["id"]) for u in users]
        memberships = await _list_memberships_with_joins(
            account_id=resolved_account_id,
            user_ids=user_ids,
            limit=5000,
            offset=0,
        )
        by_user: Dict[str, List[Dict[str, Any]]] = {}
        for membership in memberships:
            by_user.setdefault(str(membership["user_id"]), []).append(membership)

        for user in users:
            user["memberships"] = by_user.get(str(user["id"]), [])

    return {"data": {"users": users, "total": total}}


@router.get("/users/{user_id}")
async def get_user(
    request: Request,
    user_id: str,
    account_id: Optional[str] = None,
    source: Optional[str] = Query(default=None, description="Directory data source: identity/zitadel/scim or default copilot"),
    include_memberships: bool = False,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)

    if _is_identity_source(source):
        await _reconcile_identity_users_for_account(resolved_account_id)
        identity_users = await _list_identity_users(
            account_id=resolved_account_id,
            is_active=None,
            include_memberships=include_memberships,
            limit=5000,
            offset=0,
        )
        user = next(
            (
                u
                for u in identity_users.get("users", [])
                if str(u.get("id")) == str(user_id)
            ),
            None,
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        return {"data": {"user": user}}

    user = await copilot_db.users.find_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if str(user.get("account_id")) != str(resolved_account_id):
        raise HTTPException(status_code=404, detail="User not found.")

    if include_memberships:
        memberships = await _list_memberships_with_joins(
            account_id=resolved_account_id,
            user_ids=[user_id],
            limit=5000,
            offset=0,
        )
        user["memberships"] = memberships

    return {"data": {"user": user}}


@router.post("/users")
async def create_user(
    request: Request,
    data: CopilotUserCreate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    payload = _model_dump(data)
    email = _normalize_email(payload["email"])
    acting_user = (_auth or {}).get("user_id")

    existing = await _get_user_by_email(resolved_account_id, email)
    if existing:
        raise HTTPException(status_code=409, detail="User with this email already exists.")

    defaults = await _ensure_default_group_and_team(resolved_account_id, acting_user)

    user = await copilot_db.users.create(
        data={
            "account_id": resolved_account_id,
            "email": email,
            "name": payload["name"].strip(),
            "profile_image": payload.get("profile_image"),
            "is_active": True,
        }
    )

    membership = await copilot_db.account_memberships.create(
        data={
            "account_id": resolved_account_id,
            "user_id": user["id"],
            "app_role": _enum_value(payload["app_role"]),
            "team_id": defaults["team"]["id"],
            "is_active": True,
            "created_by": acting_user,
            "updated_by": acting_user,
        }
    )

    return {"data": {"user": user, "membership": membership}}


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    request: Request,
    data: CopilotUserUpdate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    user = await copilot_db.users.find_by_id(user_id)
    if not user or str(user["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="User not found.")

    update_data = {
        k: v for k, v in _model_dump(data).items() if v is not None
    }
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    updated = await copilot_db.users.update(user_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"data": updated}


@router.patch("/users/{user_id}/membership")
async def update_user_membership(
    user_id: str,
    request: Request,
    data: CopilotMembershipUpdate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    membership = await _get_membership_for_user(resolved_account_id, user_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found.")

    update_data = {k: v for k, v in _model_dump(data).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update.")

    if "team_id" in update_data and update_data["team_id"]:
        team = await copilot_db.teams.find_by_id(update_data["team_id"])
        if not team or str(team["account_id"]) != resolved_account_id:
            raise HTTPException(status_code=404, detail="Target team not found.")
    if "app_role" in update_data:
        update_data["app_role"] = _enum_value(update_data["app_role"])

    update_data["updated_by"] = acting_user
    updated = await copilot_db.account_memberships.update(membership["id"], update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Membership not found.")

    rows = await _list_memberships_with_joins(
        account_id=resolved_account_id,
        user_ids=[user_id],
        limit=1,
        offset=0,
    )
    return {"data": rows[0] if rows else updated}


@router.get("/memberships")
async def list_memberships(
    request: Request,
    account_id: Optional[str] = None,
    user_id: Optional[str] = None,
    source: Optional[str] = Query(default=None, description="Directory data source: identity/zitadel/scim or default copilot"),
    is_active: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)

    if _is_identity_source(source):
        await _reconcile_identity_users_for_account(resolved_account_id)
        identity_users = await _list_identity_users(
            account_id=resolved_account_id,
            is_active=is_active,
            include_memberships=True,
            limit=5000,
            offset=0,
        )
        memberships: List[Dict[str, Any]] = []
        for identity_user in identity_users.get("users", []):
            rows = identity_user.get("memberships", []) or []
            for row in rows:
                if user_id and str(row.get("user_id")) != str(user_id):
                    continue
                if is_active is not None and bool(row.get("is_active")) != bool(is_active):
                    continue
                memberships.append(row)

        total = len(memberships)
        paginated = memberships[offset : offset + limit]
        return {"data": paginated, "total": total}

    memberships = await _list_memberships_with_joins(
        account_id=resolved_account_id,
        user_ids=[user_id] if user_id else None,
        active_only=is_active,
        limit=limit,
        offset=offset,
    )
    total = await copilot_db.account_memberships.execute_raw_val(
        """
        SELECT COUNT(*)
        FROM copilot.account_memberships
        WHERE account_id = $1
          AND ($2::uuid IS NULL OR user_id = $2)
          AND ($3::boolean IS NULL OR is_active = $3)
        """,
        resolved_account_id,
        user_id,
        is_active,
    )
    return {"data": memberships, "total": int(total or 0)}


# ============================================
# Groups
# ============================================


@router.get("/groups")
async def list_groups(
    request: Request,
    account_id: Optional[str] = None,
    source: Optional[str] = Query(default=None, description="Directory data source: identity/zitadel/scim or default copilot"),
    search: Optional[str] = None,
    include_teams: bool = False,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    if _is_identity_source(source):
        await _reconcile_identity_users_for_account(resolved_account_id)
        identity = await _list_identity_groups(
            account_id=resolved_account_id,
            search=search,
            include_teams=include_teams,
            limit=limit,
            offset=offset,
        )
        return {"data": identity["groups"], "total": int(identity["total"])}

    rows = await copilot_db.groups.execute_raw(
        """
        SELECT g.*,
               (
                   SELECT COUNT(*)
                   FROM copilot.teams t
                   WHERE t.group_id = g.id
               ) AS team_count
        FROM copilot.groups g
        WHERE g.account_id = $1
          AND ($2::text IS NULL OR g.name ILIKE $2)
        ORDER BY g.is_default DESC, g.name ASC
        LIMIT $3 OFFSET $4
        """,
        resolved_account_id,
        f"%{search.strip()}%" if search and search.strip() else None,
        limit,
        offset,
    )
    total = await copilot_db.groups.execute_raw_val(
        """
        SELECT COUNT(*)
        FROM copilot.groups g
        WHERE g.account_id = $1
          AND ($2::text IS NULL OR g.name ILIKE $2)
        """,
        resolved_account_id,
        f"%{search.strip()}%" if search and search.strip() else None,
    )

    groups = [dict(r) for r in rows]
    if include_teams and groups:
        group_ids = _parse_uuid_list([str(g["id"]) for g in groups])
        teams = await copilot_db.teams.execute_raw(
            """
            SELECT *
            FROM copilot.teams
            WHERE account_id = $1
              AND group_id = ANY($2::uuid[])
            ORDER BY is_default DESC, name ASC
            """,
            resolved_account_id,
            group_ids,
        )
        teams_by_group: Dict[str, List[Dict[str, Any]]] = {}
        for t in teams:
            teams_by_group.setdefault(str(t["group_id"]), []).append(t)
        for group in groups:
            group["teams"] = teams_by_group.get(str(group["id"]), [])

    return {"data": groups, "total": int(total or 0)}


@router.post("/groups")
async def create_group(
    request: Request,
    data: CopilotGroupCreate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    payload = _model_dump(data)

    existing = await copilot_db.groups.execute_raw(
        """
        SELECT id
        FROM copilot.groups
        WHERE account_id = $1 AND lower(name) = lower($2)
        LIMIT 1
        """,
        resolved_account_id,
        payload["name"].strip(),
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A group with this name already exists.",
        )

    group = await copilot_db.groups.create(
        data={
            "account_id": resolved_account_id,
            "name": payload["name"].strip(),
            "description": payload.get("description"),
            "owner_id": payload.get("owner_id"),
            "contact_email": payload.get("contact_email"),
            "created_by": acting_user,
            "updated_by": acting_user,
        }
    )
    return {"data": group}


@router.get("/groups/{group_id}")
async def get_group(
    group_id: str,
    request: Request,
    account_id: Optional[str] = None,
    include_teams: bool = False,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    group = await copilot_db.groups.find_by_id(group_id)
    if not group or str(group["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Group not found.")

    if include_teams:
        teams = await copilot_db.teams.find_many(
            where={"account_id": resolved_account_id, "group_id": group_id},
            order_by="is_default DESC, name ASC",
            limit=500,
            offset=0,
        )
        group["teams"] = teams
    return {"data": group}


@router.put("/groups/{group_id}")
async def update_group(
    group_id: str,
    request: Request,
    data: CopilotGroupUpdate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    existing = await copilot_db.groups.find_by_id(group_id)
    if not existing or str(existing["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Group not found.")
    if existing.get("is_default"):
        raise HTTPException(status_code=400, detail="Cannot modify the default group.")

    payload = {k: v for k, v in _model_dump(data).items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update.")

    if "name" in payload:
        taken = await copilot_db.groups.execute_raw(
            """
            SELECT id
            FROM copilot.groups
            WHERE account_id = $1
              AND lower(name) = lower($2)
              AND id <> $3
            LIMIT 1
            """,
            resolved_account_id,
            payload["name"].strip(),
            group_id,
        )
        if taken:
            raise HTTPException(
                status_code=409,
                detail="A group with this name already exists.",
            )
        payload["name"] = payload["name"].strip()

    payload["updated_by"] = acting_user
    updated = await copilot_db.groups.update(group_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Group not found.")
    return {"data": updated}


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    existing = await copilot_db.groups.find_by_id(group_id)
    if not existing or str(existing["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Group not found.")
    if existing.get("is_default"):
        raise HTTPException(status_code=400, detail="Cannot delete the default group.")

    team_count = await copilot_db.teams.execute_raw_val(
        "SELECT COUNT(*) FROM copilot.teams WHERE account_id = $1 AND group_id = $2",
        resolved_account_id,
        group_id,
    )
    if int(team_count or 0) > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete group with teams. Delete or move teams first.",
        )

    deleted = await copilot_db.groups.delete(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found.")
    return {"status": "ok"}


# ============================================
# Teams
# ============================================


@router.get("/teams")
async def list_teams(
    request: Request,
    account_id: Optional[str] = None,
    source: Optional[str] = Query(default=None, description="Directory data source: identity/zitadel/scim or default copilot"),
    group_id: Optional[str] = None,
    search: Optional[str] = None,
    include_members: bool = False,
    include_group: bool = True,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    if _is_identity_source(source):
        await _reconcile_identity_users_for_account(resolved_account_id)
        identity = await _list_identity_teams(
            account_id=resolved_account_id,
            group_id=group_id,
            search=search,
            include_members=include_members,
            include_group=include_group,
            limit=limit,
            offset=offset,
        )
        return {"data": identity["teams"], "total": int(identity["total"])}

    rows = await copilot_db.teams.execute_raw(
        """
        SELECT
            t.*,
            g.id AS g_id,
            g.name AS g_name,
            g.account_id AS g_account_id,
            g.is_default AS g_is_default,
            (
                SELECT COUNT(*)
                FROM copilot.account_memberships m
                WHERE m.account_id = t.account_id AND m.team_id = t.id
            ) AS member_count
        FROM copilot.teams t
        LEFT JOIN copilot.groups g ON g.id = t.group_id
        WHERE t.account_id = $1
          AND ($2::uuid IS NULL OR t.group_id = $2)
          AND ($3::text IS NULL OR t.name ILIKE $3)
        ORDER BY t.is_default DESC, t.name ASC
        LIMIT $4 OFFSET $5
        """,
        resolved_account_id,
        group_id,
        f"%{search.strip()}%" if search and search.strip() else None,
        limit,
        offset,
    )
    total = await copilot_db.teams.execute_raw_val(
        """
        SELECT COUNT(*)
        FROM copilot.teams t
        WHERE t.account_id = $1
          AND ($2::uuid IS NULL OR t.group_id = $2)
          AND ($3::text IS NULL OR t.name ILIKE $3)
        """,
        resolved_account_id,
        group_id,
        f"%{search.strip()}%" if search and search.strip() else None,
    )

    teams: List[Dict[str, Any]] = []
    for row in rows:
        team = dict(row)
        if include_group:
            team["group"] = {
                "id": row.get("g_id"),
                "name": row.get("g_name"),
                "account_id": row.get("g_account_id"),
                "is_default": row.get("g_is_default"),
            } if row.get("g_id") else None
        teams.append(team)

    if include_members and teams:
        team_ids = [str(t["id"]) for t in teams]
        memberships = await _list_memberships_with_joins(
            account_id=resolved_account_id,
            team_id=None,
            limit=5000,
            offset=0,
        )
        by_team: Dict[str, List[Dict[str, Any]]] = {}
        for membership in memberships:
            m_team_id = membership.get("team_id")
            if m_team_id and str(m_team_id) in team_ids:
                by_team.setdefault(str(m_team_id), []).append(membership)
        for team in teams:
            team["members"] = by_team.get(str(team["id"]), [])

    return {"data": teams, "total": int(total or 0)}


@router.post("/users/reconcile-identity")
async def reconcile_identity_users(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    """
    Manually reconcile identity users missing account_id into the current account.
    """
    resolved_account_id = await _resolve_account_id(account_id)
    updated = await _reconcile_identity_users_for_account(resolved_account_id)
    return {"data": {"account_id": resolved_account_id, "updated_count": updated}}


@router.post("/teams")
async def create_team(
    request: Request,
    data: CopilotTeamCreate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    payload = _model_dump(data)

    group = await copilot_db.groups.find_by_id(payload["group_id"])
    if not group or str(group["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Group not found.")

    existing = await copilot_db.teams.execute_raw(
        """
        SELECT id
        FROM copilot.teams
        WHERE account_id = $1
          AND group_id = $2
          AND lower(name) = lower($3)
        LIMIT 1
        """,
        resolved_account_id,
        payload["group_id"],
        payload["name"].strip(),
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A team with this name already exists in this group.",
        )

    team = await copilot_db.teams.create(
        data={
            "account_id": resolved_account_id,
            "group_id": payload["group_id"],
            "name": payload["name"].strip(),
            "description": payload.get("description"),
            "owner_id": payload.get("owner_id"),
            "contact_email": payload.get("contact_email"),
            "created_by": acting_user,
            "updated_by": acting_user,
        }
    )
    return {"data": team}


@router.get("/teams/{team_id}")
async def get_team(
    team_id: str,
    request: Request,
    account_id: Optional[str] = None,
    include_members: bool = False,
    include_group: bool = False,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    team = await copilot_db.teams.find_by_id(team_id)
    if not team or str(team["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Team not found.")

    if include_group:
        group = await copilot_db.groups.find_by_id(str(team["group_id"]))
        team["group"] = group
    if include_members:
        members = await _list_memberships_with_joins(
            account_id=resolved_account_id,
            team_id=team_id,
            limit=1000,
            offset=0,
        )
        team["members"] = members
    return {"data": team}


@router.put("/teams/{team_id}")
async def update_team(
    team_id: str,
    request: Request,
    data: CopilotTeamUpdate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    existing = await copilot_db.teams.find_by_id(team_id)
    if not existing or str(existing["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Team not found.")
    if existing.get("is_default"):
        raise HTTPException(status_code=400, detail="Cannot modify the default team.")

    payload = {k: v for k, v in _model_dump(data).items() if v is not None}
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update.")

    if "name" in payload:
        taken = await copilot_db.teams.execute_raw(
            """
            SELECT id
            FROM copilot.teams
            WHERE account_id = $1
              AND group_id = $2
              AND lower(name) = lower($3)
              AND id <> $4
            LIMIT 1
            """,
            resolved_account_id,
            existing["group_id"],
            payload["name"].strip(),
            team_id,
        )
        if taken:
            raise HTTPException(
                status_code=409,
                detail="A team with this name already exists in this group.",
            )
        payload["name"] = payload["name"].strip()

    payload["updated_by"] = acting_user
    updated = await copilot_db.teams.update(team_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Team not found.")
    return {"data": updated}


@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    team = await copilot_db.teams.find_by_id(team_id)
    if not team or str(team["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Team not found.")
    if team.get("is_default"):
        raise HTTPException(status_code=400, detail="Cannot delete the default team.")

    defaults = await _ensure_default_group_and_team(resolved_account_id, acting_user)
    default_team_id = defaults["team"]["id"]

    moved_count = await copilot_db.account_memberships.execute_raw_val(
        """
        WITH moved AS (
            UPDATE copilot.account_memberships
            SET team_id = $1, updated_at = now(), updated_by = $2
            WHERE account_id = $3 AND team_id = $4
            RETURNING id
        )
        SELECT COUNT(*) FROM moved
        """,
        default_team_id,
        acting_user,
        resolved_account_id,
        team_id,
    )

    deleted = await copilot_db.teams.delete(team_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Team not found.")
    return {"status": "ok", "moved_members_count": int(moved_count or 0)}


@router.get("/teams/{team_id}/members")
async def list_team_members(
    team_id: str,
    request: Request,
    account_id: Optional[str] = None,
    available: bool = False,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    team = await copilot_db.teams.find_by_id(team_id)
    if not team or str(team["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Team not found.")

    if available:
        data = await _list_memberships_with_joins(
            account_id=resolved_account_id,
            exclude_team_id=team_id,
            active_only=True,
            limit=1000,
            offset=0,
        )
    else:
        data = await _list_memberships_with_joins(
            account_id=resolved_account_id,
            team_id=team_id,
            limit=1000,
            offset=0,
        )
    return {"data": data, "total": len(data)}


@router.post("/teams/{team_id}/members")
async def add_team_member(
    team_id: str,
    request: Request,
    data: CopilotTeamMemberAssign,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    team = await copilot_db.teams.find_by_id(team_id)
    if not team or str(team["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Team not found.")

    membership = await _get_membership_for_user(resolved_account_id, data.user_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found.")

    updated = await copilot_db.account_memberships.update(
        membership["id"],
        {"team_id": team_id, "updated_by": acting_user, "last_active_at": _now_utc()},
    )
    return {"data": updated}


@router.delete("/teams/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str,
    user_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    team = await copilot_db.teams.find_by_id(team_id)
    if not team or str(team["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Team not found.")

    membership = await _get_membership_for_user(resolved_account_id, user_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found.")

    defaults = await _ensure_default_group_and_team(resolved_account_id, acting_user)
    updated = await copilot_db.account_memberships.update(
        membership["id"],
        {
            "team_id": defaults["team"]["id"],
            "updated_by": acting_user,
            "last_active_at": _now_utc(),
        },
    )
    return {"data": updated}


# ============================================
# Invites
# ============================================


@router.get("/invites")
async def list_invites(
    request: Request,
    account_id: Optional[str] = None,
    email: Optional[str] = None,
    status: Optional[CopilotInviteStatus] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_read_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    now = _now_utc()

    await copilot_db.user_invites.execute_raw(
        """
        UPDATE copilot.user_invites
        SET status = 'EXPIRED', updated_at = now()
        WHERE account_id = $1
          AND status = 'PENDING'
          AND expires_at < $2
        """,
        resolved_account_id,
        now,
    )

    rows = await copilot_db.user_invites.execute_raw(
        """
        SELECT *
        FROM copilot.user_invites
        WHERE account_id = $1
          AND ($2::text IS NULL OR lower(email) LIKE lower($2))
          AND ($3::text IS NULL OR status = $3)
        ORDER BY created_at DESC
        LIMIT $4 OFFSET $5
        """,
        resolved_account_id,
        f"%{email.strip()}%" if email and email.strip() else None,
        status.value if status else None,
        limit,
        offset,
    )
    total = await copilot_db.user_invites.execute_raw_val(
        """
        SELECT COUNT(*)
        FROM copilot.user_invites
        WHERE account_id = $1
          AND ($2::text IS NULL OR lower(email) LIKE lower($2))
          AND ($3::text IS NULL OR status = $3)
        """,
        resolved_account_id,
        f"%{email.strip()}%" if email and email.strip() else None,
        status.value if status else None,
    )
    return {"data": rows, "total": int(total or 0)}


@router.post("/invites")
async def create_invite(
    request: Request,
    data: CopilotInviteCreate,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    payload = _model_dump(data)
    email = _normalize_email(payload["email"])

    expires_at = _now_utc() + timedelta(days=max(1, int(payload.get("expires_in_days", 7))))
    invite = await copilot_db.user_invites.create(
        data={
            "account_id": resolved_account_id,
            "email": email,
            "role": _enum_value(payload.get("role", CopilotMembershipRole.USER)),
            "role_id": payload.get("role_id"),
            "workspace_id": payload.get("workspace_id"),
            "status": CopilotInviteStatus.PENDING.value,
            "token": secrets.token_hex(32),
            "invitation_data": payload.get("invitation_data", {}),
            "created_by": acting_user,
            "expires_at": expires_at,
        }
    )
    return {"data": invite}


@router.post("/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    acting_user = (_auth or {}).get("user_id")
    invite = await copilot_db.user_invites.find_by_id(invite_id)
    if not invite or str(invite["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Invite not found.")

    if invite["status"] != CopilotInviteStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Invite is not pending.")
    if invite["expires_at"] and datetime.fromisoformat(
        str(invite["expires_at"]).replace("Z", "+00:00")
    ) < _now_utc():
        await copilot_db.user_invites.update(
            invite_id,
            {"status": CopilotInviteStatus.EXPIRED.value},
        )
        raise HTTPException(status_code=409, detail="Invite has expired.")

    defaults = await _ensure_default_group_and_team(resolved_account_id, acting_user)
    email = _normalize_email(str(invite["email"]))
    user = await _get_user_by_email(resolved_account_id, email)
    if not user:
        user = await copilot_db.users.create(
            data={
                "account_id": resolved_account_id,
                "email": email,
                "name": _user_name_from_email(email),
                "is_active": True,
            }
        )

    membership = await _get_membership_for_user(resolved_account_id, user["id"])
    if membership:
        membership = await copilot_db.account_memberships.update(
            membership["id"],
            {
                "is_active": True,
                "app_role": invite.get("role") or CopilotMembershipRole.USER.value,
                "team_id": membership.get("team_id") or defaults["team"]["id"],
                "updated_by": acting_user,
                "last_active_at": _now_utc(),
            },
        )
    else:
        membership = await copilot_db.account_memberships.create(
            data={
                "account_id": resolved_account_id,
                "user_id": user["id"],
                "app_role": invite.get("role") or CopilotMembershipRole.USER.value,
                "team_id": defaults["team"]["id"],
                "is_active": True,
                "created_by": acting_user,
                "updated_by": acting_user,
            }
        )

    updated_invite = await copilot_db.user_invites.update(
        invite_id,
        {
            "status": CopilotInviteStatus.ACCEPTED.value,
            "accepted_by": acting_user,
            "accepted_at": _now_utc(),
        },
    )
    return {"data": {"invite": updated_invite, "user": user, "membership": membership}}


@router.post("/invites/{invite_id}/reject")
async def reject_invite(
    invite_id: str,
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_admin_access),
):
    resolved_account_id = await _resolve_account_id(account_id)
    invite = await copilot_db.user_invites.find_by_id(invite_id)
    if not invite or str(invite["account_id"]) != resolved_account_id:
        raise HTTPException(status_code=404, detail="Invite not found.")

    updated = await copilot_db.user_invites.update(
        invite_id,
        {"status": CopilotInviteStatus.DECLINED.value},
    )
    return {"data": updated}
