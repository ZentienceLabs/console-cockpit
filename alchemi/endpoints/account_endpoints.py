"""
Account (tenant) management endpoints - Super admin only.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/account", tags=["Account Management"])


class AccountCreateRequest(BaseModel):
    account_name: str
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    max_budget: Optional[float] = None
    metadata: Optional[dict] = {}
    admin_email: Optional[str] = None


class AccountUpdateRequest(BaseModel):
    account_name: Optional[str] = None
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None
    max_budget: Optional[float] = None
    metadata: Optional[dict] = None


class AccountAdminRequest(BaseModel):
    user_email: str
    role: Optional[str] = "account_admin"


async def _require_super_admin(request: Request):
    """Dependency to verify super admin access."""
    from alchemi.middleware.tenant_context import is_super_admin
    if not is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only accessible to super admins.",
        )


@router.post("/new")
async def create_account(
    data: AccountCreateRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Create a new tenant account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_accounttable.find_first(
        where={"account_name": data.account_name}
    )
    if existing:
        raise HTTPException(
            status_code=400, detail=f"Account '{data.account_name}' already exists"
        )

    if data.domain:
        existing_domain = await prisma_client.db.alchemi_accounttable.find_first(
            where={"domain": data.domain}
        )
        if existing_domain:
            raise HTTPException(
                status_code=400,
                detail=f"Domain '{data.domain}' is already assigned to another account",
            )

    account = await prisma_client.db.alchemi_accounttable.create(
        data={
            "account_id": str(uuid.uuid4()),
            "account_name": data.account_name,
            "account_alias": data.account_alias,
            "domain": data.domain,
            "max_budget": data.max_budget,
            "metadata": data.metadata or {},
            "status": "active",
            "created_by": "super_admin",
        }
    )

    if data.admin_email:
        await prisma_client.db.alchemi_accountadmintable.create(
            data={
                "id": str(uuid.uuid4()),
                "account_id": account.account_id,
                "user_email": data.admin_email,
                "role": "account_admin",
                "created_by": "super_admin",
            }
        )

        existing_user = await prisma_client.db.litellm_usertable.find_first(
            where={"user_email": data.admin_email}
        )
        if not existing_user:
            await prisma_client.db.litellm_usertable.create(
                data={
                    "user_id": str(uuid.uuid4()),
                    "user_email": data.admin_email,
                    "user_role": "proxy_admin",
                    "account_id": account.account_id,
                }
            )
        else:
            await prisma_client.db.litellm_usertable.update(
                where={"user_id": existing_user.user_id},
                data={"user_role": "proxy_admin", "account_id": account.account_id},
            )

    return {
        "account_id": account.account_id,
        "account_name": account.account_name,
        "domain": account.domain,
        "status": account.status,
        "message": "Account created successfully",
    }


@router.get("/list")
async def list_accounts(
    request: Request,
    _=Depends(_require_super_admin),
):
    """List all tenant accounts."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    accounts = await prisma_client.db.alchemi_accounttable.find_many(
        include={"admins": True},
        order={"created_at": "desc"},
    )
    return {"accounts": accounts}


@router.get("/{account_id}")
async def get_account(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Get account details."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id},
        include={"admins": True, "sso_config": True},
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.put("/{account_id}")
async def update_account(
    account_id: str,
    data: AccountUpdateRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Update account settings."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    update_data = {k: v for k, v in data.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    account = await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data=update_data,
    )
    return account


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Suspend an account (soft delete)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data={"status": "suspended"},
    )
    return {"message": f"Account '{account.account_name}' suspended", "account_id": account_id}


@router.post("/{account_id}/admin")
async def add_account_admin(
    account_id: str,
    data: AccountAdminRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Add an admin to an account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    existing = await prisma_client.db.alchemi_accountadmintable.find_first(
        where={"account_id": account_id, "user_email": data.user_email}
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"User '{data.user_email}' is already an admin for this account",
        )

    admin = await prisma_client.db.alchemi_accountadmintable.create(
        data={
            "id": str(uuid.uuid4()),
            "account_id": account_id,
            "user_email": data.user_email,
            "role": data.role or "account_admin",
            "created_by": "super_admin",
        }
    )

    existing_user = await prisma_client.db.litellm_usertable.find_first(
        where={"user_email": data.user_email}
    )
    if not existing_user:
        await prisma_client.db.litellm_usertable.create(
            data={
                "user_id": str(uuid.uuid4()),
                "user_email": data.user_email,
                "user_role": "proxy_admin",
                "account_id": account_id,
            }
        )

    return {"message": f"Admin '{data.user_email}' added to account", "admin": admin}


@router.delete("/{account_id}/admin/{email}")
async def remove_account_admin(
    account_id: str,
    email: str,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Remove an admin from an account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    deleted = await prisma_client.db.alchemi_accountadmintable.delete_many(
        where={"account_id": account_id, "user_email": email}
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Admin not found")

    return {"message": f"Admin '{email}' removed from account"}
