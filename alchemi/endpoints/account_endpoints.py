"""
Account (tenant) management endpoints - Super admin only.
Includes account CRUD, admin management with password support, and per-account SSO config.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
import json

router = APIRouter(prefix="/account", tags=["Account Management"])


class AccountCreateRequest(BaseModel):
    account_name: str
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    max_budget: Optional[float] = None
    metadata: Optional[dict] = {}
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None  # Password for the initial admin


class AccountUpdateRequest(BaseModel):
    account_name: Optional[str] = None
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None
    max_budget: Optional[float] = None
    metadata: Optional[dict] = None


class AccountAdminRequest(BaseModel):
    user_email: str
    password: Optional[str] = None  # Password for the admin
    role: Optional[str] = "account_admin"


class AccountAdminPasswordUpdateRequest(BaseModel):
    password: str


class AccountAdminUpdateRequest(BaseModel):
    new_email: Optional[str] = None
    password: Optional[str] = None


class AccountDeleteConfirmRequest(BaseModel):
    account_name: str  # Must match exactly to confirm deletion


class AccountSSOConfigRequest(BaseModel):
    sso_provider: Optional[str] = None  # "google", "microsoft", "okta", "generic"
    enabled: bool = False
    sso_settings: Optional[Dict[str, Any]] = None  # Provider-specific settings


def _hash_password(password: str) -> str:
    """Hash a password using SHA-256 (same as LiteLLM's hash_token)."""
    from litellm.proxy._types import hash_token
    return hash_token(password)


async def _require_super_admin(request: Request):
    """Dependency to verify super admin access."""
    from alchemi.middleware.tenant_context import is_super_admin
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    # Resolve tenant context directly from request (in case middleware contextvar didn't propagate)
    if not is_super_admin():
        resolve_tenant_from_request(request)

    if not is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only accessible to super admins.",
        )


async def _require_super_admin_or_account_admin(request: Request):
    """Dependency to verify super admin or account admin access."""
    from alchemi.middleware.tenant_context import is_super_admin, get_current_account_id
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    # Resolve tenant context directly from request (in case middleware contextvar didn't propagate)
    if not is_super_admin() and get_current_account_id() is None:
        resolve_tenant_from_request(request)

    if is_super_admin():
        return
    account_id = get_current_account_id()
    if account_id is None:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Super admin or account admin required.",
        )
    # If they have an account_id, they are an account admin for that account


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
            "metadata": Json(data.metadata or {}),
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

        # Hash password if provided
        hashed_password = _hash_password(data.admin_password) if data.admin_password else None

        existing_user = await prisma_client.db.litellm_usertable.find_first(
            where={"user_email": data.admin_email}
        )
        if not existing_user:
            user_data = {
                "user_id": str(uuid.uuid4()),
                "user_email": data.admin_email,
                "user_role": "proxy_admin",
                "account_id": account.account_id,
            }
            if hashed_password:
                user_data["password"] = hashed_password
            await prisma_client.db.litellm_usertable.create(data=user_data)
        else:
            update_data = {"user_role": "proxy_admin", "account_id": account.account_id}
            if hashed_password:
                update_data["password"] = hashed_password
            await prisma_client.db.litellm_usertable.update(
                where={"user_id": existing_user.user_id},
                data=update_data,
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
        include={"admins": True, "sso_config": True},
        order={"created_at": "desc"},
    )
    return {"accounts": accounts}


# ── Per-account UI theme ─────────────────────────────────────────────────────
# These MUST be defined before /{account_id} parametric routes to avoid
# "theme" being matched as an account_id.


class AccountThemeRequest(BaseModel):
    logo_url: Optional[str] = None


@router.get("/theme")
async def get_account_theme(request: Request):
    """
    Get UI theme for the caller's account.
    Returns account-specific theme if set, otherwise falls back to global theme.
    """
    from alchemi.middleware.tenant_context import get_current_account_id
    from alchemi.middleware.account_middleware import resolve_tenant_from_request
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    resolve_tenant_from_request(request)
    account_id = get_current_account_id()

    theme_config = {}

    if account_id:
        account = await prisma_client.db.alchemi_accounttable.find_unique(
            where={"account_id": account_id}
        )
        if account and account.metadata:
            meta = account.metadata if isinstance(account.metadata, dict) else {}
            theme_config = meta.get("ui_theme_config", {})

    # Fall back to global theme settings if account has none
    if not theme_config:
        try:
            from litellm.proxy.proxy_server import proxy_config
            config = await proxy_config.get_config()
            litellm_settings = config.get("litellm_settings", {}) or {}
            theme_config = litellm_settings.get("ui_theme_config", {})
        except Exception:
            pass

    return {
        "values": theme_config,
        "account_id": account_id,
    }


@router.patch("/theme")
async def update_account_theme(
    data: AccountThemeRequest,
    request: Request,
    _=Depends(_require_super_admin_or_account_admin),
):
    """
    Update UI theme for the caller's account.
    Stores theme config in the account's metadata.ui_theme_config.
    """
    from alchemi.middleware.tenant_context import get_current_account_id
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    meta = account.metadata if isinstance(account.metadata, dict) else {}
    theme_data = data.model_dump(exclude_none=True)

    if data.logo_url is None or data.logo_url == "":
        meta.pop("ui_theme_config", None)
    else:
        meta["ui_theme_config"] = theme_data

    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data={"metadata": Json(meta)},
    )

    return {
        "message": "Account theme updated successfully",
        "status": "success",
        "theme_config": theme_data,
        "account_id": account_id,
    }


# ── Per-account SMTP config ─────────────────────────────────────────────────
# These MUST be defined before /{account_id} parametric routes.


class AccountSmtpConfigRequest(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None


@router.get("/smtp")
async def get_account_smtp(
    request: Request,
    _=Depends(_require_super_admin_or_account_admin),
):
    """Get SMTP configuration for the caller's account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    if get_current_account_id() is None:
        resolve_tenant_from_request(request)
    account_id = get_current_account_id()

    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    meta = account.metadata if isinstance(account.metadata, dict) else {}
    smtp_config = meta.get("smtp_config", {})

    # Mask the password in the response
    if smtp_config and smtp_config.get("smtp_password"):
        smtp_config = dict(smtp_config)
        smtp_config["smtp_password"] = "••••••••"

    return {"smtp_config": smtp_config, "account_id": account_id}


@router.patch("/smtp")
async def update_account_smtp(
    data: AccountSmtpConfigRequest,
    request: Request,
    _=Depends(_require_super_admin_or_account_admin),
):
    """Update SMTP configuration for the caller's account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    if get_current_account_id() is None:
        resolve_tenant_from_request(request)
    account_id = get_current_account_id()

    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    meta = account.metadata if isinstance(account.metadata, dict) else {}
    existing_config = meta.get("smtp_config", {}) if isinstance(meta.get("smtp_config"), dict) else {}

    # Merge: only update provided fields, keep existing ones
    new_config = dict(existing_config)
    update_data = data.model_dump(exclude_none=True)
    # If password is the masked placeholder, don't overwrite
    if update_data.get("smtp_password") == "••••••••":
        update_data.pop("smtp_password", None)
    new_config.update(update_data)

    # If smtp_host is cleared, remove the entire config
    if not new_config.get("smtp_host"):
        meta.pop("smtp_config", None)
    else:
        meta["smtp_config"] = new_config

    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data={"metadata": Json(meta)},
    )

    return {
        "message": "Account SMTP config updated successfully",
        "status": "success",
        "account_id": account_id,
    }


@router.delete("/smtp")
async def delete_account_smtp(
    request: Request,
    _=Depends(_require_super_admin_or_account_admin),
):
    """Remove SMTP configuration from the caller's account (reverts to central email)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    if get_current_account_id() is None:
        resolve_tenant_from_request(request)
    account_id = get_current_account_id()

    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    meta = account.metadata if isinstance(account.metadata, dict) else {}
    meta.pop("smtp_config", None)

    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data={"metadata": Json(meta)},
    )

    return {
        "message": "Account SMTP config removed",
        "status": "success",
        "account_id": account_id,
    }


# ── Parametric {account_id} routes ───────────────────────────────────────────


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


# ─── Admin Management ───────────────────────────────────────────────────────

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

    # Hash password if provided
    hashed_password = _hash_password(data.password) if data.password else None

    existing_user = await prisma_client.db.litellm_usertable.find_first(
        where={"user_email": data.user_email}
    )
    if not existing_user:
        user_data = {
            "user_id": str(uuid.uuid4()),
            "user_email": data.user_email,
            "user_role": "proxy_admin",
            "account_id": account_id,
        }
        if hashed_password:
            user_data["password"] = hashed_password
        await prisma_client.db.litellm_usertable.create(data=user_data)
    else:
        update_data = {"account_id": account_id}
        if hashed_password:
            update_data["password"] = hashed_password
        await prisma_client.db.litellm_usertable.update(
            where={"user_id": existing_user.user_id},
            data=update_data,
        )

    return {"message": f"Admin '{data.user_email}' added to account", "admin": admin}


@router.put("/{account_id}/admin/{email}/password")
async def update_admin_password(
    account_id: str,
    email: str,
    data: AccountAdminPasswordUpdateRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Update an admin's password."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # Verify admin exists for this account
    admin = await prisma_client.db.alchemi_accountadmintable.find_first(
        where={"account_id": account_id, "user_email": email}
    )
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found for this account")

    # Find user in LiteLLM_UserTable
    user = await prisma_client.db.litellm_usertable.find_first(
        where={"user_email": email}
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed_password = _hash_password(data.password)
    await prisma_client.db.litellm_usertable.update(
        where={"user_id": user.user_id},
        data={"password": hashed_password},
    )

    return {"message": f"Password updated for admin '{email}'"}


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


@router.put("/{account_id}/admin/{email}")
async def update_account_admin(
    account_id: str,
    email: str,
    data: AccountAdminUpdateRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Update an admin's email and/or password."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    if not data.new_email and not data.password:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Find existing admin record
    admin = await prisma_client.db.alchemi_accountadmintable.find_first(
        where={"account_id": account_id, "user_email": email}
    )
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found for this account")

    # Find user in LiteLLM_UserTable
    user = await prisma_client.db.litellm_usertable.find_first(
        where={"user_email": email}
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # If changing email, check for conflicts
    if data.new_email and data.new_email != email:
        existing_admin = await prisma_client.db.alchemi_accountadmintable.find_first(
            where={"account_id": account_id, "user_email": data.new_email}
        )
        if existing_admin:
            raise HTTPException(
                status_code=400,
                detail=f"'{data.new_email}' is already an admin for this account",
            )

        # Update admin table email
        await prisma_client.db.alchemi_accountadmintable.update(
            where={"id": admin.id},
            data={"user_email": data.new_email},
        )

        # Update user table email
        await prisma_client.db.litellm_usertable.update(
            where={"user_id": user.user_id},
            data={"user_email": data.new_email},
        )

    # Update password if provided
    if data.password:
        hashed_password = _hash_password(data.password)
        await prisma_client.db.litellm_usertable.update(
            where={"user_id": user.user_id},
            data={"password": hashed_password},
        )

    final_email = data.new_email if data.new_email else email
    return {"message": f"Admin '{final_email}' updated successfully"}


@router.post("/{account_id}/delete")
async def permanently_delete_account(
    account_id: str,
    data: AccountDeleteConfirmRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Permanently delete an account. Requires account name confirmation."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Confirm the name matches exactly
    if data.account_name != account.account_name:
        raise HTTPException(
            status_code=400,
            detail="Account name does not match. Deletion cancelled.",
        )

    # Delete in order: SSO config -> admins -> account
    await prisma_client.db.alchemi_accountssoconfig.delete_many(
        where={"account_id": account_id}
    )
    await prisma_client.db.alchemi_accountadmintable.delete_many(
        where={"account_id": account_id}
    )
    await prisma_client.db.alchemi_accounttable.delete(
        where={"account_id": account_id}
    )

    return {
        "message": f"Account '{account.account_name}' permanently deleted",
        "account_id": account_id,
    }


# ─── Per-Account SSO Configuration ──────────────────────────────────────────

@router.get("/{account_id}/sso")
async def get_account_sso_config(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin_or_account_admin),
):
    """Get SSO configuration for an account. Accessible by super admin or account admin."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import is_super_admin, get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # Account admins can only access their own account's SSO config
    if not is_super_admin():
        current_account_id = get_current_account_id()
        if current_account_id != account_id:
            raise HTTPException(
                status_code=403,
                detail="You can only access SSO settings for your own account.",
            )

    sso_config = await prisma_client.db.alchemi_accountssoconfig.find_first(
        where={"account_id": account_id}
    )

    if not sso_config:
        return {
            "account_id": account_id,
            "sso_provider": None,
            "enabled": False,
            "sso_settings": {},
        }

    # Parse sso_settings if it's a string
    settings = sso_config.sso_settings
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except (json.JSONDecodeError, TypeError):
            settings = {}

    # Mask secrets in the response
    masked_settings = _mask_sso_secrets(settings or {})

    return {
        "id": sso_config.id,
        "account_id": sso_config.account_id,
        "sso_provider": sso_config.sso_provider,
        "enabled": sso_config.enabled,
        "sso_settings": masked_settings,
    }


@router.put("/{account_id}/sso")
async def update_account_sso_config(
    account_id: str,
    data: AccountSSOConfigRequest,
    request: Request,
    _=Depends(_require_super_admin_or_account_admin),
):
    """Update SSO configuration for an account. Accessible by super admin or account admin."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import is_super_admin, get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    # Account admins can only update their own account's SSO config
    if not is_super_admin():
        current_account_id = get_current_account_id()
        if current_account_id != account_id:
            raise HTTPException(
                status_code=403,
                detail="You can only update SSO settings for your own account.",
            )

    # Verify account exists
    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    sso_settings_json = json.dumps(data.sso_settings or {})

    existing = await prisma_client.db.alchemi_accountssoconfig.find_first(
        where={"account_id": account_id}
    )

    if existing:
        # Merge: if a secret field is masked (ends with ***), keep the old value
        if data.sso_settings and existing.sso_settings:
            old_settings = existing.sso_settings
            if isinstance(old_settings, str):
                try:
                    old_settings = json.loads(old_settings)
                except (json.JSONDecodeError, TypeError):
                    old_settings = {}
            merged_settings = _merge_sso_settings(old_settings or {}, data.sso_settings)
            sso_settings_json = json.dumps(merged_settings)

        sso_config = await prisma_client.db.alchemi_accountssoconfig.update(
            where={"id": existing.id},
            data={
                "sso_provider": data.sso_provider,
                "enabled": data.enabled,
                "sso_settings": sso_settings_json,
            },
        )
    else:
        sso_config = await prisma_client.db.alchemi_accountssoconfig.create(
            data={
                "id": str(uuid.uuid4()),
                "account_id": account_id,
                "sso_provider": data.sso_provider,
                "enabled": data.enabled,
                "sso_settings": sso_settings_json,
            },
        )

    return {
        "message": "SSO configuration updated successfully",
        "account_id": account_id,
        "sso_provider": sso_config.sso_provider,
        "enabled": sso_config.enabled,
    }


@router.delete("/{account_id}/sso")
async def delete_account_sso_config(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin_or_account_admin),
):
    """Delete SSO configuration for an account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import is_super_admin, get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    if not is_super_admin():
        current_account_id = get_current_account_id()
        if current_account_id != account_id:
            raise HTTPException(
                status_code=403,
                detail="You can only delete SSO settings for your own account.",
            )

    deleted = await prisma_client.db.alchemi_accountssoconfig.delete_many(
        where={"account_id": account_id}
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="No SSO configuration found for this account")

    return {"message": "SSO configuration deleted", "account_id": account_id}


def _mask_sso_secrets(settings: dict) -> dict:
    """Mask sensitive fields in SSO settings for display."""
    secret_fields = {"client_secret", "google_client_secret", "microsoft_client_secret",
                     "generic_client_secret"}
    masked = {}
    for key, value in settings.items():
        if key in secret_fields and value and isinstance(value, str) and len(value) > 4:
            masked[key] = value[:4] + "****" + value[-4:]
        else:
            masked[key] = value
    return masked


def _merge_sso_settings(old_settings: dict, new_settings: dict) -> dict:
    """Merge new SSO settings with old, preserving secrets that are masked."""
    merged = dict(new_settings)
    for key, value in merged.items():
        if isinstance(value, str) and "****" in value:
            # Keep old value if the new one is masked
            if key in old_settings:
                merged[key] = old_settings[key]
    return merged
