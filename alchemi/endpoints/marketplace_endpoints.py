"""
Agent marketplace management endpoints.
CRUD for marketplace listings scoped to the caller's account.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access

router = APIRouter(prefix="/alchemi/marketplace", tags=["Agent Marketplace"])


# -- Request Models -----------------------------------------------------------


class ListingCreateRequest(BaseModel):
    agent_id: str
    listing_status: Optional[str] = "draft"
    listing_data: Optional[Dict[str, Any]] = None


class ListingUpdateRequest(BaseModel):
    listing_status: Optional[str] = None
    listing_data: Optional[Dict[str, Any]] = None


# -- Marketplace Listing Routes -----------------------------------------------


@router.post("/new")
async def create_listing(
    data: ListingCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new marketplace listing for an agent."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    listing_id = str(uuid.uuid4())

    listing = await prisma_client.db.alchemi_agentmarketplacetable.create(
        data={
            "id": listing_id,
            "account_id": account_id,
            "agent_id": data.agent_id,
            "listing_status": data.listing_status or "draft",
            "listing_data": Json(data.listing_data or {}),
        },
    )

    return {
        "id": listing.id,
        "agent_id": listing.agent_id,
        "listing_status": listing.listing_status,
        "message": "Marketplace listing created successfully",
    }


@router.get("/list")
async def list_listings(
    request: Request,
    listing_status: Optional[str] = Query(default=None, description="Filter by listing status"),
    agent_id: Optional[str] = Query(default=None, description="Filter by agent ID"),
    _=Depends(require_account_access),
):
    """List marketplace listings for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if listing_status:
        where["listing_status"] = listing_status
    if agent_id:
        where["agent_id"] = agent_id

    listings = await prisma_client.db.alchemi_agentmarketplacetable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"listings": listings}


@router.get("/{listing_id}")
async def get_listing(
    listing_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Get marketplace listing detail."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    listing = await prisma_client.db.alchemi_agentmarketplacetable.find_first(
        where={"id": listing_id, "account_id": account_id},
    )

    if not listing:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")

    return listing


@router.put("/{listing_id}")
async def update_listing(
    listing_id: str,
    data: ListingUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a marketplace listing."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_agentmarketplacetable.find_first(
        where={"id": listing_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")

    update_data: Dict[str, Any] = {}

    if data.listing_status is not None:
        update_data["listing_status"] = data.listing_status
    if data.listing_data is not None:
        update_data["listing_data"] = Json(data.listing_data)

    listing = await prisma_client.db.alchemi_agentmarketplacetable.update(
        where={"id": listing_id},
        data=update_data,
    )

    return listing


@router.delete("/{listing_id}")
async def delete_listing(
    listing_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete a marketplace listing."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_agentmarketplacetable.find_first(
        where={"id": listing_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")

    await prisma_client.db.alchemi_agentmarketplacetable.delete(
        where={"id": listing_id},
    )

    return {
        "message": "Marketplace listing deleted",
        "id": listing_id,
        "agent_id": existing.agent_id,
    }
