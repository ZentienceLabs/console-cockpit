"""Copilot directory endpoints.

Provides isolated Copilot directory management (users, orgs, teams, memberships, invites)
separate from general Console BYOK management.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from alchemi.endpoints.copilot_auth import (
    get_actor_email_or_id,
    require_account_admin_or_super_admin,
    require_account_context,
)
from alchemi.db.copilot_db import append_audit_event, kv_delete, kv_get, kv_list, kv_put


router = APIRouter(prefix="/copilot/directory", tags=["Copilot Directory"])

DOMAIN_KEY = "alchemi_domain"
COPILOT_DOMAIN = "copilot"


def _require_prisma():
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    return prisma_client


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if hasattr(row, "model_dump"):
        return row.model_dump()
    if hasattr(row, "dict"):
        return row.dict()
    return {k: v for k, v in vars(row).items() if not k.startswith("_")}


def _is_copilot_meta(metadata: Any) -> bool:
    return isinstance(metadata, dict) and metadata.get(DOMAIN_KEY) == COPILOT_DOMAIN


def _mark_copilot_meta(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(metadata or {})
    out[DOMAIN_KEY] = COPILOT_DOMAIN
    return out


def _user_is_active(user_row: Any) -> bool:
    user = _row_to_dict(user_row)
    metadata = user.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("is_active") is False:
        return False
    return (user.get("user_role") or "").lower() != "disabled"


def _membership_id(user_id: str, account_id: str) -> str:
    return f"{user_id}:{account_id}"


def _user_to_account_membership(user_row: Any, account_id: str, team_id: Optional[str] = None) -> Dict[str, Any]:
    user = _row_to_dict(user_row)
    metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
    app_role = (
        str(metadata.get("app_role"))
        if metadata and metadata.get("app_role")
        else str(user.get("user_role") or "member")
    )
    return {
        "id": _membership_id(str(user.get("user_id")), account_id),
        "account_id": account_id,
        "user_id": user.get("user_id"),
        "app_role": app_role,
        "is_active": _user_is_active(user),
        "team_id": team_id,
        "tenant_preferences": (metadata or {}).get("tenant_preferences", {}),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "user": {
            "id": user.get("user_id"),
            "name": user.get("user_alias"),
            "email": user.get("user_email"),
            "profile_image": None,
        },
    }


class DirectoryUserCreate(BaseModel):
    user_email: str
    user_alias: Optional[str] = None
    user_role: str = "member"
    password: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DirectoryUserUpdate(BaseModel):
    user_email: Optional[str] = None
    user_alias: Optional[str] = None
    user_role: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class OrgCreate(BaseModel):
    organization_alias: str
    models: List[str] = Field(default_factory=list)
    budget_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrgUpdate(BaseModel):
    organization_alias: Optional[str] = None
    models: Optional[List[str]] = None
    budget_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TeamCreate(BaseModel):
    team_alias: str
    organization_id: Optional[str] = None
    models: List[str] = Field(default_factory=list)
    admins: List[str] = Field(default_factory=list)
    members: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TeamUpdate(BaseModel):
    team_alias: Optional[str] = None
    organization_id: Optional[str] = None
    models: Optional[List[str]] = None
    admins: Optional[List[str]] = None
    members: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class OrgMembershipCreate(BaseModel):
    user_id: str
    organization_id: str
    user_role: str = "member"


class TeamMembershipCreate(BaseModel):
    user_id: str
    team_id: str


class AccountMembershipUpsert(BaseModel):
    user_id: str
    app_role: Optional[str] = None
    is_active: Optional[bool] = None
    tenant_preferences: Optional[Dict[str, Any]] = None
    team_id: Optional[str] = None


class InviteCreate(BaseModel):
    email: str
    role: str = "member"
    team_id: Optional[str] = None
    organization_id: Optional[str] = None
    expires_in_days: int = 7


class InviteUpdate(BaseModel):
    status: Optional[str] = None
    role: Optional[str] = None
    team_id: Optional[str] = None
    organization_id: Optional[str] = None
    expires_in_days: Optional[int] = None


def _normalize_invite_status(value: Optional[str]) -> str:
    status = (value or "PENDING").strip().upper()
    if status == "REJECTED":
        status = "DECLINED"
    allowed = {"PENDING", "ACCEPTED", "DECLINED", "EXPIRED", "REVOKED"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid invite status: {value}")
    return status


@router.get("/users")
async def list_users(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    search: Optional[str] = None,
    email: Optional[str] = None,
    user_role: Optional[str] = None,
    is_active: Optional[bool] = None,
    include_memberships: bool = False,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    prisma = _require_prisma()
    rows = await prisma.db.litellm_usertable.find_many(
        where={"account_id": account_id},
        order={"updated_at": "desc"},
    )
    users = [_row_to_dict(r) for r in rows]

    if email:
        email_l = email.lower()
        users = [u for u in users if str(u.get("user_email") or "").lower() == email_l]
    if search:
        q = search.lower()
        users = [
            u
            for u in users
            if q in str(u.get("user_email") or "").lower()
            or q in str(u.get("user_alias") or "").lower()
            or q in str(u.get("user_id") or "").lower()
        ]
    if user_role:
        users = [u for u in users if str(u.get("user_role") or "") == user_role]
    if is_active is not None:
        users = [u for u in users if _user_is_active(u) == is_active]

    total = len(users)
    users = users[offset : offset + limit]

    if include_memberships and users:
        user_ids = [str(u.get("user_id")) for u in users if u.get("user_id")]
        org_memberships = await prisma.db.litellm_organizationmembership.find_many(
            where={"account_id": account_id}
        )
        team_memberships = await prisma.db.litellm_teammembership.find_many(
            where={"account_id": account_id}
        )
        org_map: Dict[str, List[Dict[str, Any]]] = {uid: [] for uid in user_ids}
        team_map: Dict[str, List[Dict[str, Any]]] = {uid: [] for uid in user_ids}

        for row in org_memberships:
            item = _row_to_dict(row)
            uid = str(item.get("user_id"))
            if uid in org_map:
                org_map[uid].append(item)
        for row in team_memberships:
            item = _row_to_dict(row)
            uid = str(item.get("user_id"))
            if uid in team_map:
                team_map[uid].append(item)

        for user in users:
            uid = str(user.get("user_id"))
            user["memberships"] = {
                "organization": org_map.get(uid, []),
                "team": team_map.get(uid, []),
            }

    return {"items": users, "total": total}


@router.post("/users")
async def create_user(
    body: DirectoryUserCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    existing = await prisma.db.litellm_usertable.find_first(
        where={"user_email": body.user_email.lower().strip(), "account_id": account_id}
    )

    metadata = _mark_copilot_meta(body.metadata)
    data: Dict[str, Any] = {
        "user_alias": body.user_alias,
        "user_email": body.user_email.lower().strip(),
        "user_role": body.user_role,
        "account_id": account_id,
        "metadata": metadata,
    }
    if body.password:
        from litellm.proxy._types import hash_token

        data["password"] = hash_token(body.password)

    if existing:
        row = await prisma.db.litellm_usertable.update(
            where={"user_id": existing.user_id},
            data=data,
        )
    else:
        row = await prisma.db.litellm_usertable.create(
            data={
                "user_id": str(uuid.uuid4()),
                **data,
            }
        )

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.user.upsert",
            "actor": get_actor_email_or_id(request),
            "data": {"user_id": row.user_id, "user_email": row.user_email},
        },
    )

    return {"item": _row_to_dict(row)}


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    include_memberships: bool = False,
):
    prisma = _require_prisma()
    row = await prisma.db.litellm_usertable.find_unique(where={"user_id": user_id})
    if row is None or row.account_id != account_id:
        raise HTTPException(status_code=404, detail="User not found")

    user = _row_to_dict(row)
    if include_memberships:
        org_memberships = await prisma.db.litellm_organizationmembership.find_many(
            where={"account_id": account_id, "user_id": user_id}
        )
        team_memberships = await prisma.db.litellm_teammembership.find_many(
            where={"account_id": account_id, "user_id": user_id}
        )
        user["memberships"] = {
            "organization": [_row_to_dict(m) for m in org_memberships],
            "team": [_row_to_dict(m) for m in team_memberships],
        }

    return {"item": user}


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    body: DirectoryUserUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    existing = await prisma.db.litellm_usertable.find_unique(where={"user_id": user_id})
    if existing is None or existing.account_id != account_id:
        raise HTTPException(status_code=404, detail="User not found")

    update_data: Dict[str, Any] = {}
    if body.user_email is not None:
        update_data["user_email"] = body.user_email.lower().strip()
    if body.user_alias is not None:
        update_data["user_alias"] = body.user_alias
    if body.user_role is not None:
        update_data["user_role"] = body.user_role

    existing_metadata = (
        dict(existing.metadata) if isinstance(existing.metadata, dict) else {}
    )
    if body.metadata is not None:
        existing_metadata.update(body.metadata)
    if body.is_active is not None:
        existing_metadata["is_active"] = body.is_active
        if body.is_active is False:
            update_data["user_role"] = "disabled"
    if existing_metadata:
        update_data["metadata"] = _mark_copilot_meta(existing_metadata)

    if body.password:
        from litellm.proxy._types import hash_token

        update_data["password"] = hash_token(body.password)

    row = await prisma.db.litellm_usertable.update(
        where={"user_id": user_id},
        data=update_data,
    )

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.user.update",
            "actor": get_actor_email_or_id(request),
            "data": {"user_id": user_id, "updated_fields": list(update_data.keys())},
        },
    )
    return {"item": _row_to_dict(row)}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    existing = await prisma.db.litellm_usertable.find_unique(where={"user_id": user_id})
    if existing is None or existing.account_id != account_id:
        raise HTTPException(status_code=404, detail="User not found")

    metadata = dict(existing.metadata) if isinstance(existing.metadata, dict) else {}
    metadata["is_active"] = False
    metadata["deactivated_at"] = datetime.now(timezone.utc).isoformat()
    await prisma.db.litellm_usertable.update(
        where={"user_id": user_id},
        data={"metadata": _mark_copilot_meta(metadata), "user_role": "disabled"},
    )

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.user.deactivate",
            "actor": get_actor_email_or_id(request),
            "data": {"user_id": user_id},
        },
    )
    return {"deleted": True}


@router.get("/organizations")
async def list_organizations(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    include_teams: bool = False,
):
    prisma = _require_prisma()
    rows = await prisma.db.litellm_organizationtable.find_many(
        where={"account_id": account_id},
        order={"updated_at": "desc"},
    )
    organizations = [_row_to_dict(r) for r in rows if _is_copilot_meta(_row_to_dict(r).get("metadata"))]

    if include_teams and organizations:
        teams = await prisma.db.litellm_teamtable.find_many(where={"account_id": account_id})
        teams_by_org: Dict[str, List[Dict[str, Any]]] = {}
        for team_row in teams:
            team = _row_to_dict(team_row)
            if not _is_copilot_meta(team.get("metadata")):
                continue
            org_id = str(team.get("organization_id") or "")
            teams_by_org.setdefault(org_id, []).append(team)
        for org in organizations:
            org["teams"] = teams_by_org.get(str(org.get("organization_id")), [])

    return {"items": organizations, "total": len(organizations)}


@router.post("/organizations")
async def create_organization(
    body: OrgCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()

    row = await prisma.db.litellm_organizationtable.create(
        data={
            "organization_id": str(uuid.uuid4()),
            "organization_alias": body.organization_alias,
            "budget_id": body.budget_id,
            "metadata": _mark_copilot_meta(body.metadata),
            "models": body.models,
            "created_by": get_actor_email_or_id(request),
            "updated_by": get_actor_email_or_id(request),
            "account_id": account_id,
        }
    )

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.organization.create",
            "actor": get_actor_email_or_id(request),
            "data": {
                "organization_id": row.organization_id,
                "organization_alias": row.organization_alias,
            },
        },
    )

    return {"item": _row_to_dict(row)}


@router.get("/organizations/{organization_id}")
async def get_organization(
    organization_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    include_teams: bool = False,
):
    prisma = _require_prisma()
    row = await prisma.db.litellm_organizationtable.find_unique(
        where={"organization_id": organization_id}
    )
    if row is None or row.account_id != account_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    item = _row_to_dict(row)
    if not _is_copilot_meta(item.get("metadata")):
        raise HTTPException(status_code=404, detail="Organization not found")

    if include_teams:
        teams = await prisma.db.litellm_teamtable.find_many(
            where={"account_id": account_id, "organization_id": organization_id}
        )
        item["teams"] = [
            _row_to_dict(t) for t in teams if _is_copilot_meta(_row_to_dict(t).get("metadata"))
        ]

    return {"item": item}


@router.put("/organizations/{organization_id}")
async def update_organization(
    organization_id: str,
    body: OrgUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    existing = await prisma.db.litellm_organizationtable.find_unique(
        where={"organization_id": organization_id}
    )
    if existing is None or existing.account_id != account_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    data: Dict[str, Any] = {"updated_by": get_actor_email_or_id(request)}
    if body.organization_alias is not None:
        data["organization_alias"] = body.organization_alias
    if body.models is not None:
        data["models"] = body.models
    if body.budget_id is not None:
        data["budget_id"] = body.budget_id
    if body.metadata is not None:
        current_meta = dict(existing.metadata) if isinstance(existing.metadata, dict) else {}
        current_meta.update(body.metadata)
        data["metadata"] = _mark_copilot_meta(current_meta)

    row = await prisma.db.litellm_organizationtable.update(
        where={"organization_id": organization_id},
        data=data,
    )
    return {"item": _row_to_dict(row)}


@router.delete("/organizations/{organization_id}")
async def delete_organization(
    organization_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    org = await prisma.db.litellm_organizationtable.find_unique(
        where={"organization_id": organization_id}
    )
    if org is None or org.account_id != account_id:
        raise HTTPException(status_code=404, detail="Organization not found")

    teams = await prisma.db.litellm_teamtable.find_many(
        where={"organization_id": organization_id, "account_id": account_id}
    )
    for team in teams:
        await prisma.db.litellm_teammembership.delete_many(
            where={"team_id": team.team_id, "account_id": account_id}
        )
    await prisma.db.litellm_teamtable.delete_many(
        where={"organization_id": organization_id, "account_id": account_id}
    )
    await prisma.db.litellm_organizationmembership.delete_many(
        where={"organization_id": organization_id, "account_id": account_id}
    )
    await prisma.db.litellm_organizationtable.delete(
        where={"organization_id": organization_id}
    )

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.organization.delete",
            "actor": get_actor_email_or_id(request),
            "data": {"organization_id": organization_id},
        },
    )
    return {"deleted": True}


@router.get("/teams")
async def list_teams(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    organization_id: Optional[str] = None,
    include_members: bool = False,
    include_organization: bool = False,
):
    prisma = _require_prisma()
    where: Dict[str, Any] = {"account_id": account_id}
    if organization_id:
        where["organization_id"] = organization_id

    rows = await prisma.db.litellm_teamtable.find_many(
        where=where,
        order={"updated_at": "desc"},
    )
    teams = [_row_to_dict(r) for r in rows if _is_copilot_meta(_row_to_dict(r).get("metadata"))]

    if include_members and teams:
        team_ids = [str(t.get("team_id")) for t in teams]
        memberships = await prisma.db.litellm_teammembership.find_many(
            where={"account_id": account_id}
        )
        users = await prisma.db.litellm_usertable.find_many(where={"account_id": account_id})
        users_by_id = {str(u.user_id): _row_to_dict(u) for u in users}
        by_team: Dict[str, List[Dict[str, Any]]] = {tid: [] for tid in team_ids}
        for membership in memberships:
            item = _row_to_dict(membership)
            team_id = str(item.get("team_id"))
            if team_id not in by_team:
                continue
            user = users_by_id.get(str(item.get("user_id")))
            by_team[team_id].append(
                {
                    **item,
                    "user": {
                        "id": user.get("user_id") if user else item.get("user_id"),
                        "name": user.get("user_alias") if user else None,
                        "email": user.get("user_email") if user else None,
                        "profile_image": None,
                    },
                }
            )
        for team in teams:
            team["memberships"] = by_team.get(str(team.get("team_id")), [])
            team["member_count"] = len(team["memberships"])

    if include_organization and teams:
        orgs = await prisma.db.litellm_organizationtable.find_many(where={"account_id": account_id})
        org_map = {str(org.organization_id): _row_to_dict(org) for org in orgs}
        for team in teams:
            org_id = str(team.get("organization_id") or "")
            team["organization"] = org_map.get(org_id)

    return {"items": teams, "total": len(teams)}


@router.post("/teams")
async def create_team(
    body: TeamCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    row = await prisma.db.litellm_teamtable.create(
        data={
            "team_id": str(uuid.uuid4()),
            "team_alias": body.team_alias,
            "organization_id": body.organization_id,
            "admins": body.admins,
            "members": body.members,
            "models": body.models,
            "metadata": _mark_copilot_meta(body.metadata),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "account_id": account_id,
        }
    )

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.team.create",
            "actor": get_actor_email_or_id(request),
            "data": {"team_id": row.team_id, "team_alias": row.team_alias},
        },
    )
    return {"item": _row_to_dict(row)}


@router.get("/teams/{team_id}")
async def get_team(
    team_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    include_members: bool = False,
    include_organization: bool = False,
):
    prisma = _require_prisma()
    row = await prisma.db.litellm_teamtable.find_unique(where={"team_id": team_id})
    if row is None or row.account_id != account_id:
        raise HTTPException(status_code=404, detail="Team not found")

    team = _row_to_dict(row)
    if not _is_copilot_meta(team.get("metadata")):
        raise HTTPException(status_code=404, detail="Team not found")

    if include_members:
        memberships = await prisma.db.litellm_teammembership.find_many(
            where={"account_id": account_id, "team_id": team_id}
        )
        users = await prisma.db.litellm_usertable.find_many(where={"account_id": account_id})
        users_by_id = {str(u.user_id): _row_to_dict(u) for u in users}
        mapped = []
        for membership in memberships:
            item = _row_to_dict(membership)
            user = users_by_id.get(str(item.get("user_id")))
            mapped.append(
                {
                    **item,
                    "user": {
                        "id": user.get("user_id") if user else item.get("user_id"),
                        "name": user.get("user_alias") if user else None,
                        "email": user.get("user_email") if user else None,
                        "profile_image": None,
                    },
                }
            )
        team["memberships"] = mapped
        team["member_count"] = len(mapped)

    if include_organization and team.get("organization_id"):
        org = await prisma.db.litellm_organizationtable.find_unique(
            where={"organization_id": team["organization_id"]}
        )
        team["organization"] = _row_to_dict(org) if org else None

    return {"item": team}


@router.put("/teams/{team_id}")
async def update_team(
    team_id: str,
    body: TeamUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    existing = await prisma.db.litellm_teamtable.find_unique(where={"team_id": team_id})
    if existing is None or existing.account_id != account_id:
        raise HTTPException(status_code=404, detail="Team not found")

    data: Dict[str, Any] = {}
    if body.team_alias is not None:
        data["team_alias"] = body.team_alias
    if body.organization_id is not None:
        data["organization_id"] = body.organization_id
    if body.models is not None:
        data["models"] = body.models
    if body.admins is not None:
        data["admins"] = body.admins
    if body.members is not None:
        data["members"] = body.members
    if body.metadata is not None:
        current_meta = dict(existing.metadata) if isinstance(existing.metadata, dict) else {}
        current_meta.update(body.metadata)
        data["metadata"] = _mark_copilot_meta(current_meta)

    row = await prisma.db.litellm_teamtable.update(where={"team_id": team_id}, data=data)
    return {"item": _row_to_dict(row)}


@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    existing = await prisma.db.litellm_teamtable.find_unique(where={"team_id": team_id})
    if existing is None or existing.account_id != account_id:
        raise HTTPException(status_code=404, detail="Team not found")

    await prisma.db.litellm_teammembership.delete_many(
        where={"team_id": team_id, "account_id": account_id}
    )
    await prisma.db.litellm_teamtable.delete(where={"team_id": team_id})

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.team.delete",
            "actor": get_actor_email_or_id(request),
            "data": {"team_id": team_id},
        },
    )
    return {"deleted": True}


@router.get("/teams/{team_id}/members")
async def list_team_members(
    team_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    available: bool = False,
):
    prisma = _require_prisma()
    team = await prisma.db.litellm_teamtable.find_unique(where={"team_id": team_id})
    if team is None or team.account_id != account_id:
        raise HTTPException(status_code=404, detail="Team not found")

    users = await prisma.db.litellm_usertable.find_many(where={"account_id": account_id})
    users_by_id = {str(u.user_id): _row_to_dict(u) for u in users}
    memberships = await prisma.db.litellm_teammembership.find_many(where={"account_id": account_id})
    current_ids = {str(m.user_id) for m in memberships if str(m.team_id) == team_id}

    if available:
        items = []
        for uid, user in users_by_id.items():
            if uid in current_ids:
                continue
            if not _user_is_active(user):
                continue
            items.append(
                {
                    "id": _membership_id(uid, account_id),
                    "user_id": uid,
                    "team_id": None,
                    "user": {
                        "id": uid,
                        "name": user.get("user_alias"),
                        "email": user.get("user_email"),
                        "profile_image": None,
                    },
                }
            )
        return {"items": items, "total": len(items)}

    rows = [m for m in memberships if str(m.team_id) == team_id]
    items = []
    for row in rows:
        membership = _row_to_dict(row)
        user = users_by_id.get(str(membership.get("user_id")))
        items.append(
            {
                **membership,
                "user": {
                    "id": user.get("user_id") if user else membership.get("user_id"),
                    "name": user.get("user_alias") if user else None,
                    "email": user.get("user_email") if user else None,
                    "profile_image": None,
                },
            }
        )
    return {"items": items, "total": len(items)}


@router.post("/teams/{team_id}/members")
async def add_team_member(
    team_id: str,
    body: TeamMembershipCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    team = await prisma.db.litellm_teamtable.find_unique(where={"team_id": team_id})
    if team is None or team.account_id != account_id:
        raise HTTPException(status_code=404, detail="Team not found")

    user = await prisma.db.litellm_usertable.find_unique(where={"user_id": body.user_id})
    if user is None or user.account_id != account_id:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await prisma.db.litellm_teammembership.find_first(
        where={"user_id": body.user_id, "team_id": team_id}
    )
    if existing:
        row = await prisma.db.litellm_teammembership.update(
            where={"user_id_team_id": {"user_id": body.user_id, "team_id": team_id}},
            data={"account_id": account_id},
        )
    else:
        row = await prisma.db.litellm_teammembership.create(
            data={"user_id": body.user_id, "team_id": team_id, "account_id": account_id}
        )
    return {"item": _row_to_dict(row)}


@router.delete("/teams/{team_id}/members")
async def remove_team_member(
    team_id: str,
    user_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    deleted_count = await prisma.db.litellm_teammembership.delete_many(
        where={"team_id": team_id, "user_id": user_id, "account_id": account_id}
    )
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Team membership not found")
    return {"deleted": True}


@router.get("/memberships/account")
async def list_account_memberships(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    user_id: Optional[str] = None,
    app_role: Optional[str] = None,
    is_active: Optional[bool] = None,
    include_user: bool = True,
):
    prisma = _require_prisma()
    users = await prisma.db.litellm_usertable.find_many(where={"account_id": account_id})
    memberships = await prisma.db.litellm_teammembership.find_many(where={"account_id": account_id})
    user_team: Dict[str, str] = {}
    for membership in memberships:
        user_team[str(membership.user_id)] = str(membership.team_id)

    items: List[Dict[str, Any]] = []
    for row in users:
        membership = _user_to_account_membership(
            row,
            account_id=account_id,
            team_id=user_team.get(str(row.user_id)),
        )
        if user_id and membership["user_id"] != user_id:
            continue
        if app_role and str(membership["app_role"]).lower() != app_role.lower():
            continue
        if is_active is not None and bool(membership["is_active"]) != is_active:
            continue
        if not include_user:
            membership.pop("user", None)
        items.append(membership)

    return {"items": items, "total": len(items)}


@router.post("/memberships/account")
async def upsert_account_membership(
    body: AccountMembershipUpsert,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    user = await prisma.db.litellm_usertable.find_unique(where={"user_id": body.user_id})
    if user is None or user.account_id != account_id:
        raise HTTPException(status_code=404, detail="User not found")

    metadata = dict(user.metadata) if isinstance(user.metadata, dict) else {}
    if body.tenant_preferences is not None:
        metadata["tenant_preferences"] = body.tenant_preferences
    if body.app_role is not None:
        metadata["app_role"] = body.app_role
    if body.is_active is not None:
        metadata["is_active"] = body.is_active

    update_data: Dict[str, Any] = {"metadata": _mark_copilot_meta(metadata)}
    if body.app_role is not None:
        update_data["user_role"] = body.app_role
    if body.is_active is False:
        update_data["user_role"] = "disabled"

    updated = await prisma.db.litellm_usertable.update(
        where={"user_id": body.user_id},
        data=update_data,
    )

    if body.team_id:
        existing_team_membership = await prisma.db.litellm_teammembership.find_first(
            where={"user_id": body.user_id, "team_id": body.team_id}
        )
        if existing_team_membership:
            await prisma.db.litellm_teammembership.update(
                where={"user_id_team_id": {"user_id": body.user_id, "team_id": body.team_id}},
                data={"account_id": account_id},
            )
        else:
            await prisma.db.litellm_teammembership.create(
                data={"user_id": body.user_id, "team_id": body.team_id, "account_id": account_id}
            )

    membership = _user_to_account_membership(updated, account_id=account_id, team_id=body.team_id)
    return {"item": membership}


@router.put("/memberships/account")
async def update_account_membership(
    body: AccountMembershipUpsert,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    return await upsert_account_membership(body, request, account_id)


@router.delete("/memberships/account")
async def delete_account_membership(
    user_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    user = await prisma.db.litellm_usertable.find_unique(where={"user_id": user_id})
    if user is None or user.account_id != account_id:
        raise HTTPException(status_code=404, detail="Membership not found")

    metadata = dict(user.metadata) if isinstance(user.metadata, dict) else {}
    metadata["is_active"] = False
    metadata["deactivated_at"] = datetime.now(timezone.utc).isoformat()

    await prisma.db.litellm_usertable.update(
        where={"user_id": user_id},
        data={"metadata": _mark_copilot_meta(metadata), "user_role": "disabled"},
    )
    return {"deleted": True}


@router.get("/memberships/account/{membership_id}")
async def get_account_membership(
    membership_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    user_id, _, membership_account_id = membership_id.partition(":")
    if not user_id or not membership_account_id or membership_account_id != account_id:
        raise HTTPException(status_code=400, detail="Invalid membership_id")

    prisma = _require_prisma()
    user = await prisma.db.litellm_usertable.find_unique(where={"user_id": user_id})
    if user is None or user.account_id != account_id:
        raise HTTPException(status_code=404, detail="Membership not found")

    team_membership = await prisma.db.litellm_teammembership.find_first(
        where={"account_id": account_id, "user_id": user_id}
    )
    return {
        "item": _user_to_account_membership(
            user,
            account_id=account_id,
            team_id=str(team_membership.team_id) if team_membership else None,
        )
    }


@router.put("/memberships/account/{membership_id}")
async def update_account_membership_by_id(
    membership_id: str,
    body: AccountMembershipUpsert,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    user_id, _, membership_account_id = membership_id.partition(":")
    if membership_account_id != account_id:
        raise HTTPException(status_code=400, detail="Invalid membership_id")
    payload = AccountMembershipUpsert(**{**body.model_dump(), "user_id": user_id})
    return await upsert_account_membership(payload, request, account_id)


@router.delete("/memberships/account/{membership_id}")
async def delete_account_membership_by_id(
    membership_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    user_id, _, membership_account_id = membership_id.partition(":")
    if membership_account_id != account_id:
        raise HTTPException(status_code=400, detail="Invalid membership_id")
    return await delete_account_membership(user_id, request, account_id)


@router.get("/memberships/organization")
async def list_org_memberships(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    prisma = _require_prisma()
    where: Dict[str, Any] = {"account_id": account_id}
    if organization_id:
        where["organization_id"] = organization_id
    if user_id:
        where["user_id"] = user_id
    rows = await prisma.db.litellm_organizationmembership.find_many(where=where)
    return {"items": [_row_to_dict(r) for r in rows], "total": len(rows)}


@router.post("/memberships/organization")
async def upsert_org_membership(
    body: OrgMembershipCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()

    existing = await prisma.db.litellm_organizationmembership.find_first(
        where={"user_id": body.user_id, "organization_id": body.organization_id}
    )

    if existing:
        row = await prisma.db.litellm_organizationmembership.update(
            where={
                "user_id_organization_id": {
                    "user_id": body.user_id,
                    "organization_id": body.organization_id,
                }
            },
            data={"user_role": body.user_role, "account_id": account_id},
        )
    else:
        row = await prisma.db.litellm_organizationmembership.create(
            data={
                "user_id": body.user_id,
                "organization_id": body.organization_id,
                "user_role": body.user_role,
                "account_id": account_id,
            }
        )

    return {"item": _row_to_dict(row)}


@router.delete("/memberships/organization")
async def delete_org_membership(
    user_id: str,
    organization_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    deleted_count = await prisma.db.litellm_organizationmembership.delete_many(
        where={
            "user_id": user_id,
            "organization_id": organization_id,
            "account_id": account_id,
        }
    )
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Organization membership not found")
    return {"deleted": True}


@router.get("/memberships/team")
async def list_team_memberships(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    prisma = _require_prisma()
    where: Dict[str, Any] = {"account_id": account_id}
    if team_id:
        where["team_id"] = team_id
    if user_id:
        where["user_id"] = user_id
    rows = await prisma.db.litellm_teammembership.find_many(where=where)
    return {"items": [_row_to_dict(r) for r in rows], "total": len(rows)}


@router.post("/memberships/team")
async def upsert_team_membership(
    body: TeamMembershipCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()

    existing = await prisma.db.litellm_teammembership.find_first(
        where={"user_id": body.user_id, "team_id": body.team_id}
    )
    if existing:
        row = await prisma.db.litellm_teammembership.update(
            where={"user_id_team_id": {"user_id": body.user_id, "team_id": body.team_id}},
            data={"account_id": account_id},
        )
    else:
        row = await prisma.db.litellm_teammembership.create(
            data={"user_id": body.user_id, "team_id": body.team_id, "account_id": account_id}
        )

    return {"item": _row_to_dict(row)}


@router.delete("/memberships/team")
async def delete_team_membership(
    user_id: str,
    team_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    prisma = _require_prisma()
    deleted_count = await prisma.db.litellm_teammembership.delete_many(
        where={"user_id": user_id, "team_id": team_id, "account_id": account_id}
    )
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Team membership not found")
    return {"deleted": True}


@router.get("/invites")
async def list_invites(
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
    status: Optional[str] = None,
    email: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    rows = await kv_list("invite", account_id=account_id)
    invites = [r["value"] for r in rows]

    for invite in invites:
        invite["status"] = _normalize_invite_status(invite.get("status"))

    if status:
        target = _normalize_invite_status(status)
        invites = [invite for invite in invites if invite.get("status") == target]
    if email:
        email_l = email.lower().strip()
        invites = [invite for invite in invites if str(invite.get("email") or "").lower() == email_l]

    invites.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    total = len(invites)
    invites = invites[offset : offset + limit]
    return {"items": invites, "total": total}


@router.post("/invites")
async def create_invite(
    body: InviteCreate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    invite_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=body.expires_in_days)

    payload = {
        "invite_id": invite_id,
        "account_id": account_id,
        "email": body.email.lower().strip(),
        "role": body.role,
        "team_id": body.team_id,
        "organization_id": body.organization_id,
        "status": "PENDING",
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "created_by": get_actor_email_or_id(request),
    }

    await kv_put("invite", payload, account_id=account_id, object_id=invite_id)
    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.invite.create",
            "actor": get_actor_email_or_id(request),
            "data": payload,
        },
    )

    return {"item": payload}


@router.get("/invites/{invite_id}")
async def get_invite(
    invite_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("invite", account_id=account_id, object_id=invite_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    invite = dict(row["value"])
    invite["status"] = _normalize_invite_status(invite.get("status"))
    return {"item": invite}


@router.put("/invites/{invite_id}")
async def update_invite(
    invite_id: str,
    body: InviteUpdate,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    row = await kv_get("invite", account_id=account_id, object_id=invite_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Invite not found")

    current = dict(row["value"])
    if body.status is not None:
        current["status"] = _normalize_invite_status(body.status)
    if body.role is not None:
        current["role"] = body.role
    if body.team_id is not None:
        current["team_id"] = body.team_id
    if body.organization_id is not None:
        current["organization_id"] = body.organization_id
    if body.expires_in_days is not None:
        current["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)
        ).isoformat()

    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    current["updated_by"] = get_actor_email_or_id(request)

    await kv_put("invite", current, account_id=account_id, object_id=invite_id)
    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.invite.update",
            "actor": get_actor_email_or_id(request),
            "data": {"invite_id": invite_id, "status": current.get("status")},
        },
    )
    return {"item": current}


@router.delete("/invites/{invite_id}")
async def delete_invite(
    invite_id: str,
    request: Request,
    account_id: str = Depends(require_account_context),
    _=Depends(require_account_admin_or_super_admin),
):
    deleted = await kv_delete("invite", account_id=account_id, object_id=invite_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Invite not found")

    await append_audit_event(
        account_id,
        {
            "account_id": account_id,
            "event_type": "copilot.directory.invite.delete",
            "actor": get_actor_email_or_id(request),
            "data": {"invite_id": invite_id},
        },
    )
    return {"deleted": True}
