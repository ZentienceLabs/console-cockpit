"""
Access token management endpoints.
Create, list, update, revoke, and validate API access tokens.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
import secrets
import hashlib
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/token", tags=["Access Tokens"])


# -- Request Models -----------------------------------------------------------


class TokenCreateRequest(BaseModel):
    name: str
    workspace_ids: list = []
    client_id: Optional[str] = None
    scopes: list = []
    expires_at: Optional[datetime] = None


class TokenUpdateRequest(BaseModel):
    name: Optional[str] = None
    scopes: Optional[List[str]] = None
    workspace_ids: Optional[List[str]] = None
    expires_at: Optional[datetime] = None


class TokenValidateRequest(BaseModel):
    token: str


# -- Access Token Routes ------------------------------------------------------


@router.post("/new")
async def create_access_token(
    data: TokenCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new access token. Returns the raw token once; it cannot be retrieved again."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    token_id = str(uuid.uuid4())
    raw_token = "alt_" + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    create_data: Dict[str, Any] = {
        "id": token_id,
        "account_id": account_id,
        "name": data.name,
        "workspace_ids": data.workspace_ids or [],
        "token_hash": token_hash,
        "scopes": data.scopes or [],
        "revoked": False,
    }

    if data.client_id is not None:
        create_data["client_id"] = data.client_id
    if data.expires_at is not None:
        create_data["expires_at"] = data.expires_at

    token_record = await prisma_client.db.alchemi_accesstokentable.create(
        data=create_data,
    )

    return {
        "id": token_record.id,
        "name": token_record.name,
        "token": raw_token,
        "expires_at": token_record.expires_at,
        "message": "Access token created successfully. Save the token now; it cannot be retrieved again.",
    }


@router.get("/list")
async def list_access_tokens(
    request: Request,
    revoked: Optional[bool] = Query(default=None, description="Filter by revoked status"),
    _=Depends(require_account_access),
):
    """List access tokens for the current account (masked, no full hashes)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if revoked is not None:
        where["revoked"] = revoked

    tokens = await prisma_client.db.alchemi_accesstokentable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    # Return masked info, show last 8 chars of token_hash with "..." prefix
    result = []
    for t in tokens:
        masked_hash = "..." + t.token_hash[-8:] if t.token_hash else None
        result.append({
            "id": t.id,
            "name": t.name,
            "token_hash": masked_hash,
            "workspace_ids": t.workspace_ids,
            "client_id": t.client_id,
            "scopes": t.scopes,
            "last_used_at": t.last_used_at,
            "expires_at": t.expires_at,
            "revoked": t.revoked,
            "created_at": t.created_at,
        })

    return {"tokens": result}


@router.put("/{token_id}")
async def update_access_token(
    token_id: str,
    data: TokenUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update an access token (name, scopes, workspace_ids, expires_at)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accesstokentable.find_first(
        where={"id": token_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Access token not found")

    update_data: Dict[str, Any] = {}

    if data.name is not None:
        update_data["name"] = data.name
    if data.scopes is not None:
        update_data["scopes"] = data.scopes
    if data.workspace_ids is not None:
        update_data["workspace_ids"] = data.workspace_ids
    if data.expires_at is not None:
        update_data["expires_at"] = data.expires_at

    token_record = await prisma_client.db.alchemi_accesstokentable.update(
        where={"id": token_id},
        data=update_data,
    )

    return {
        "id": token_record.id,
        "name": token_record.name,
        "scopes": token_record.scopes,
        "workspace_ids": token_record.workspace_ids,
        "expires_at": token_record.expires_at,
        "message": "Access token updated successfully",
    }


@router.delete("/{token_id}")
async def revoke_access_token(
    token_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Revoke an access token (set revoked=true)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accesstokentable.find_first(
        where={"id": token_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Access token not found")

    await prisma_client.db.alchemi_accesstokentable.update(
        where={"id": token_id},
        data={"revoked": True},
    )

    return {
        "message": f"Access token '{existing.name}' revoked",
        "id": token_id,
    }


@router.post("/update-last-used")
async def update_last_used(
    request: Request,
    _=Depends(require_account_access),
):
    """Update the last_used_at timestamp for a token identified by its hash."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    body = await request.json()
    token_hash = body.get("token_hash")
    if not token_hash:
        raise HTTPException(status_code=400, detail="token_hash is required")

    token_record = await prisma_client.db.alchemi_accesstokentable.find_first(
        where={"token_hash": token_hash},
    )
    if not token_record:
        raise HTTPException(status_code=404, detail="Token not found")

    now = datetime.utcnow()
    await prisma_client.db.alchemi_accesstokentable.update(
        where={"id": token_record.id},
        data={"last_used_at": now},
    )

    return {"message": "last_used_at updated", "id": token_record.id}


@router.post("/cleanup")
async def cleanup_expired_tokens(
    request: Request,
    _=Depends(require_account_access),
):
    """Delete expired and revoked tokens for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()

    deleted = await prisma_client.db.alchemi_accesstokentable.delete_many(
        where={
            "account_id": account_id,
            "OR": [
                {"revoked": True},
                {"expires_at": {"lt": now}},
            ],
        },
    )

    return {"deleted_count": deleted}


@router.post("/validate")
async def validate_access_token(
    data: TokenValidateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Validate an access token."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    token_hash = hashlib.sha256(data.token.encode()).hexdigest()

    token_record = await prisma_client.db.alchemi_accesstokentable.find_first(
        where={"token_hash": token_hash},
    )

    if not token_record:
        return {"valid": False}

    if token_record.revoked:
        return {"valid": False}

    now = datetime.utcnow()
    if token_record.expires_at and token_record.expires_at < now:
        return {"valid": False}

    # Update last_used_at
    await prisma_client.db.alchemi_accesstokentable.update(
        where={"id": token_record.id},
        data={"last_used_at": now},
    )

    return {
        "valid": True,
        "account_id": token_record.account_id,
        "scopes": token_record.scopes,
        "workspace_ids": token_record.workspace_ids,
    }
