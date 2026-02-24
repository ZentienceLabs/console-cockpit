"""
Account entitlements management endpoints.
Super-admin-only: manage per-account entitlements stored in
Alchemi_AccountTable.metadata.entitlements.
"""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from prisma import Json
from pydantic import BaseModel

router = APIRouter(prefix="/copilot/entitlements", tags=["Copilot - Entitlements"])


class EntitlementsUpdate(BaseModel):
    max_models: Optional[int] = None
    max_keys: Optional[int] = None
    max_teams: Optional[int] = None
    max_budget: Optional[float] = None
    features: Optional[Dict[str, bool]] = None


async def _require_super_admin(request: Request):
    """Dependency to verify super admin access."""
    from alchemi.middleware.tenant_context import is_super_admin
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    if not is_super_admin():
        resolve_tenant_from_request(request)

    if not is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only accessible to super admins.",
        )


@router.get("/{account_id}")
async def get_entitlements(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Get entitlements for a specific account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    meta = account.metadata if isinstance(account.metadata, dict) else {}
    entitlements = meta.get("entitlements", {})

    return {
        "account_id": account_id,
        "entitlements": entitlements,
    }


@router.put("/{account_id}")
async def update_entitlements(
    account_id: str,
    data: EntitlementsUpdate,
    request: Request,
    _=Depends(_require_super_admin),
):
    """Update entitlements for a specific account."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    meta = account.metadata if isinstance(account.metadata, dict) else {}
    entitlements = meta.get("entitlements", {})

    # Merge provided fields into existing entitlements
    update_data = data.model_dump(exclude_none=True)
    for key, value in update_data.items():
        if key == "features" and isinstance(value, dict):
            existing_features = entitlements.get("features", {})
            existing_features.update(value)
            entitlements["features"] = existing_features
        else:
            entitlements[key] = value

    meta["entitlements"] = entitlements

    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data={"metadata": Json(meta)},
    )

    return {
        "account_id": account_id,
        "entitlements": entitlements,
        "status": "updated",
    }
