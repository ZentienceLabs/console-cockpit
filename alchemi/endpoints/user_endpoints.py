"""
User management endpoints.
CRUD for users in the Alchemi_UserTable,
including search, lookup by email/AD user ID, preferences merge, and bulk create.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope

router = APIRouter(prefix="/alchemi/user", tags=["User Management"])


# -- Request Models -----------------------------------------------------------


class UserCreateRequest(BaseModel):
    email: str
    name: str
    profile_image: Optional[str] = None
    ad_user_id: Optional[str] = None
    is_active: Optional[bool] = True
    email_verified: Optional[bool] = False
    global_preferences: Optional[Dict[str, Any]] = None


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    profile_image: Optional[str] = None
    is_active: Optional[bool] = None
    email_verified: Optional[bool] = None
    global_preferences: Optional[Dict[str, Any]] = None
    ad_user_id: Optional[str] = None


class UserPreferencesRequest(BaseModel):
    preferences: Dict[str, Any]


class UserBulkCreateRequest(BaseModel):
    users: List[UserCreateRequest]


# -- User CRUD Routes --------------------------------------------------------


@router.post("/new")
async def create_user(
    data: UserCreateRequest,
    request: Request,
    _=require_scope("users:write"),
):
    """Create a new user."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # Check for duplicate email
    existing = await prisma_client.db.alchemi_usertable.find_first(
        where={"email": data.email},
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists",
        )

    user_id = str(uuid.uuid4())
    now = datetime.utcnow()

    create_data: Dict[str, Any] = {
        "id": user_id,
        "email": data.email,
        "name": data.name,
        "is_active": data.is_active if data.is_active is not None else True,
        "email_verified": data.email_verified if data.email_verified is not None else False,
        "global_preferences": Json(data.global_preferences or {}),
        "created_at": now,
        "updated_at": now,
    }

    if data.profile_image is not None:
        create_data["profile_image"] = data.profile_image
    if data.ad_user_id is not None:
        create_data["ad_user_id"] = data.ad_user_id

    user = await prisma_client.db.alchemi_usertable.create(
        data=create_data,
    )

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "message": "User created successfully",
    }


@router.get("/list")
async def list_users(
    request: Request,
    account_id: Optional[str] = Query(default=None, description="Filter by account membership"),
    email: Optional[str] = Query(default=None, description="Filter by email"),
    name: Optional[str] = Query(default=None, description="Filter by name"),
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    limit: int = Query(default=50, description="Max results to return"),
    offset: int = Query(default=0, description="Number of results to skip"),
    _=require_scope("users:read"),
):
    """List users with optional filters."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    where: Dict[str, Any] = {}

    if email:
        where["email"] = email
    if name:
        where["name"] = name
    if is_active is not None:
        where["is_active"] = is_active

    # If account_id is provided, first fetch user IDs from memberships
    if account_id:
        memberships = await prisma_client.db.alchemi_accountmembershiptable.find_many(
            where={"account_id": account_id, "is_active": True},
        )
        user_ids = [m.user_id for m in memberships]
        if not user_ids:
            return {"users": [], "total": 0}
        where["id"] = {"in": user_ids}

    users = await prisma_client.db.alchemi_usertable.find_many(
        where=where,
        order={"created_at": "desc"},
        take=limit,
        skip=offset,
    )

    total = await prisma_client.db.alchemi_usertable.count(
        where=where,
    )

    return {"users": users, "total": total}


@router.get("/search")
async def search_users(
    request: Request,
    q: str = Query(description="Search query for name or email"),
    limit: int = Query(default=50, description="Max results to return"),
    offset: int = Query(default=0, description="Number of results to skip"),
    _=require_scope("users:read"),
):
    """Search users by name or email (case-insensitive partial match)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    where: Dict[str, Any] = {
        "OR": [
            {"name": {"contains": q, "mode": "insensitive"}},
            {"email": {"contains": q, "mode": "insensitive"}},
        ]
    }

    users = await prisma_client.db.alchemi_usertable.find_many(
        where=where,
        order={"created_at": "desc"},
        take=limit,
        skip=offset,
    )

    total = await prisma_client.db.alchemi_usertable.count(
        where=where,
    )

    return {"users": users, "total": total}


@router.get("/by-email/{email}")
async def get_user_by_email(
    email: str,
    request: Request,
    include_memberships: bool = Query(default=False, description="Include account memberships with account details"),
    _=require_scope("users:read"),
):
    """Find a user by email address."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    user = await prisma_client.db.alchemi_usertable.find_first(
        where={"email": email},
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        result = user.model_dump()
    except Exception:
        result = {"id": user.id, "email": user.email, "name": user.name, "ad_user_id": user.ad_user_id, "is_active": user.is_active, "email_verified": user.email_verified, "global_preferences": user.global_preferences, "profile_image": user.profile_image, "created_at": str(user.created_at), "updated_at": str(user.updated_at)}

    if include_memberships:
        memberships = await prisma_client.db.alchemi_accountmembershiptable.find_many(
            where={"user_id": user.id, "is_active": True},
        )
        memberships_list = []
        for m in memberships:
            try:
                m_data = m.model_dump()
            except Exception:
                m_data = {"id": m.id, "account_id": m.account_id, "user_id": m.user_id, "role": getattr(m, 'role', None), "is_active": m.is_active}
            account = await prisma_client.db.alchemi_accounttable.find_first(
                where={"account_id": m.account_id},
            )
            if account:
                try:
                    m_data["account"] = account.model_dump()
                except Exception:
                    m_data["account"] = {"id": account.account_id, "name": account.account_name, "status": account.status, "domain": getattr(account, 'domain', None)}
            memberships_list.append(m_data)
        result["memberships"] = memberships_list

    return result


@router.get("/by-ad-user/{ad_user_id}")
async def get_user_by_ad_user_id(
    ad_user_id: str,
    request: Request,
    include_memberships: bool = Query(default=False, description="Include account memberships with account details"),
    _=require_scope("users:read"),
):
    """Find a user by AD user ID, optionally including memberships."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    user = await prisma_client.db.alchemi_usertable.find_first(
        where={"ad_user_id": ad_user_id},
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = dict(user) if hasattr(user, '__iter__') else user.__dict__.copy() if hasattr(user, '__dict__') else {}
    # Prisma models can be serialized via model_dump or dict-like access
    try:
        result = user.model_dump()
    except Exception:
        result = {k: getattr(user, k) for k in user.__fields_set__} if hasattr(user, '__fields_set__') else {"id": user.id, "email": user.email, "name": user.name, "ad_user_id": user.ad_user_id, "is_active": user.is_active, "email_verified": user.email_verified, "global_preferences": user.global_preferences, "profile_image": user.profile_image, "created_at": str(user.created_at), "updated_at": str(user.updated_at)}

    if include_memberships:
        memberships = await prisma_client.db.alchemi_accountmembershiptable.find_many(
            where={"user_id": user.id, "is_active": True},
        )
        memberships_list = []
        for m in memberships:
            try:
                m_data = m.model_dump()
            except Exception:
                m_data = {"id": m.id, "account_id": m.account_id, "user_id": m.user_id, "role": getattr(m, 'role', None), "is_active": m.is_active}
            # Fetch the account details for each membership
            account = await prisma_client.db.alchemi_accounttable.find_first(
                where={"account_id": m.account_id},
            )
            if account:
                try:
                    m_data["account"] = account.model_dump()
                except Exception:
                    m_data["account"] = {"id": account.account_id, "name": account.account_name, "status": account.status, "domain": getattr(account, 'domain', None)}
            memberships_list.append(m_data)
        result["memberships"] = memberships_list

    return result


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    _=require_scope("users:read"),
):
    """Get user detail by ID."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    user = await prisma_client.db.alchemi_usertable.find_first(
        where={"id": user_id},
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    data: UserUpdateRequest,
    request: Request,
    _=require_scope("users:write"),
):
    """Update a user."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_usertable.find_first(
        where={"id": user_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.name is not None:
        update_data["name"] = data.name
    if data.profile_image is not None:
        update_data["profile_image"] = data.profile_image
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.email_verified is not None:
        update_data["email_verified"] = data.email_verified
    if data.global_preferences is not None:
        update_data["global_preferences"] = Json(data.global_preferences)
    if data.ad_user_id is not None:
        update_data["ad_user_id"] = data.ad_user_id

    user = await prisma_client.db.alchemi_usertable.update(
        where={"id": user_id},
        data=update_data,
    )

    return user


@router.put("/{user_id}/preferences")
async def update_user_preferences(
    user_id: str,
    data: UserPreferencesRequest,
    request: Request,
    _=require_scope("users:write"),
):
    """Merge preferences into the user's global_preferences JSONB field."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_usertable.find_first(
        where={"id": user_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    # Merge incoming preferences into existing ones
    current_preferences = existing.global_preferences or {}
    if isinstance(current_preferences, str):
        import json
        current_preferences = json.loads(current_preferences)

    merged_preferences = {**current_preferences, **data.preferences}

    user = await prisma_client.db.alchemi_usertable.update(
        where={"id": user_id},
        data={
            "global_preferences": Json(merged_preferences),
            "updated_at": datetime.utcnow(),
        },
    )

    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    _=require_scope("users:write"),
):
    """Delete a user."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_usertable.find_first(
        where={"id": user_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    await prisma_client.db.alchemi_usertable.delete(
        where={"id": user_id},
    )

    return {
        "message": f"User '{existing.name}' deleted",
        "id": user_id,
    }


@router.post("/bulk")
async def bulk_create_users(
    data: UserBulkCreateRequest,
    request: Request,
    _=require_scope("users:write"),
):
    """Bulk create users. Skips users whose email already exists."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    created = 0
    skipped = 0
    created_users = []

    for user_data in data.users:
        # Check for duplicate email
        existing = await prisma_client.db.alchemi_usertable.find_first(
            where={"email": user_data.email},
        )
        if existing:
            skipped += 1
            continue

        user_id = str(uuid.uuid4())
        now = datetime.utcnow()

        create_data: Dict[str, Any] = {
            "id": user_id,
            "email": user_data.email,
            "name": user_data.name,
            "is_active": user_data.is_active if user_data.is_active is not None else True,
            "email_verified": user_data.email_verified if user_data.email_verified is not None else False,
            "global_preferences": Json(user_data.global_preferences or {}),
            "created_at": now,
            "updated_at": now,
        }

        if user_data.profile_image is not None:
            create_data["profile_image"] = user_data.profile_image
        if user_data.ad_user_id is not None:
            create_data["ad_user_id"] = user_data.ad_user_id

        user = await prisma_client.db.alchemi_usertable.create(
            data=create_data,
        )

        created_users.append({
            "id": user.id,
            "email": user.email,
            "name": user.name,
        })
        created += 1

    return {
        "message": f"Bulk create complete: {created} created, {skipped} skipped (duplicate email)",
        "created": created,
        "skipped": skipped,
        "users": created_users,
    }
