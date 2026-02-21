"""
Override configuration endpoints.
Platform catalog management (super admin) and account-level override configs.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_scope, require_account_access, require_super_admin

router = APIRouter(prefix="/alchemi/override", tags=["Override Configs"])


# -- Request Models -----------------------------------------------------------


class PlatformCatalogCreateRequest(BaseModel):
    code: str
    name: str
    category: Optional[str] = None
    parent_code: Optional[str] = None
    value_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = True
    display_order: Optional[int] = 0


class PlatformCatalogUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    parent_code: Optional[str] = None
    value_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class OverrideConfigCreateRequest(BaseModel):
    product_code: Optional[str] = None
    feature_code: Optional[str] = None
    entity_code: Optional[str] = None
    name: str
    category: Optional[str] = None
    parent_entity_code: Optional[str] = None
    distribution_kind: Optional[str] = None
    action: Optional[str] = "RESTRICT"
    inherit: Optional[bool] = False
    value_config: Optional[Dict[str, Any]] = None
    scope_type: Optional[str] = "ACCOUNT"
    scope_id: Optional[str] = None
    restriction_json: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class OverrideConfigUpdateRequest(BaseModel):
    product_code: Optional[str] = None
    feature_code: Optional[str] = None
    entity_code: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    parent_entity_code: Optional[str] = None
    distribution_kind: Optional[str] = None
    action: Optional[str] = None
    inherit: Optional[bool] = None
    value_config: Optional[Dict[str, Any]] = None
    scope_type: Optional[str] = None
    scope_id: Optional[str] = None
    restriction_json: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


# -- Platform Catalog Routes (super admin) ------------------------------------


@router.get("/catalog/list")
async def list_catalog_entries(
    request: Request,
    category: Optional[str] = Query(default=None, description="Filter by category"),
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    _=Depends(require_account_access),
):
    """List platform catalog entries."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {}
    if category:
        where["category"] = category
    if is_active is not None:
        where["is_active"] = is_active

    entries = await prisma_client.db.alchemi_platformcatalogtable.find_many(
        where=where,
        order={"display_order": "asc"},
    )

    return {"catalog_entries": entries}


@router.post("/catalog/new")
async def create_catalog_entry(
    data: PlatformCatalogCreateRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    """Create a new platform catalog entry (super admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_platformcatalogtable.find_unique(
        where={"code": data.code},
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Catalog entry with code '{data.code}' already exists",
        )

    entry = await prisma_client.db.alchemi_platformcatalogtable.create(
        data={
            "code": data.code,
            "name": data.name,
            "category": data.category,
            "parent_code": data.parent_code,
            "value_config": Json(data.value_config or {}),
            "is_active": data.is_active if data.is_active is not None else True,
            "display_order": data.display_order or 0,
        }
    )

    return {
        "code": entry.code,
        "name": entry.name,
        "message": "Catalog entry created successfully",
    }


@router.put("/catalog/{code}")
async def update_catalog_entry(
    code: str,
    data: PlatformCatalogUpdateRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    """Update a platform catalog entry (super admin only)."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    existing = await prisma_client.db.alchemi_platformcatalogtable.find_unique(
        where={"code": code},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Catalog entry not found")

    update_data: Dict[str, Any] = {}

    if data.name is not None:
        update_data["name"] = data.name
    if data.category is not None:
        update_data["category"] = data.category
    if data.parent_code is not None:
        update_data["parent_code"] = data.parent_code
    if data.is_active is not None:
        update_data["is_active"] = data.is_active
    if data.display_order is not None:
        update_data["display_order"] = data.display_order
    if data.value_config is not None:
        update_data["value_config"] = Json(data.value_config)

    entry = await prisma_client.db.alchemi_platformcatalogtable.update(
        where={"code": code},
        data=update_data,
    )

    return entry


# -- Account Override Config Routes -------------------------------------------


@router.post("/new")
async def create_override_config(
    data: OverrideConfigCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new account override configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    override_id = str(uuid.uuid4())
    now = datetime.utcnow()

    create_data: Dict[str, Any] = {
        "id": override_id,
        "account_id": account_id,
        "name": data.name,
        "action": data.action or "RESTRICT",
        "inherit": data.inherit if data.inherit is not None else False,
        "scope_type": data.scope_type or "ACCOUNT",
        "value_config": Json(data.value_config or {}),
        "valid_from": data.valid_from or now,
    }

    if data.product_code is not None:
        create_data["product_code"] = data.product_code
    if data.feature_code is not None:
        create_data["feature_code"] = data.feature_code
    if data.entity_code is not None:
        create_data["entity_code"] = data.entity_code
    if data.category is not None:
        create_data["category"] = data.category
    if data.parent_entity_code is not None:
        create_data["parent_entity_code"] = data.parent_entity_code
    if data.distribution_kind is not None:
        create_data["distribution_kind"] = data.distribution_kind
    if data.scope_id is not None:
        create_data["scope_id"] = data.scope_id
    if data.restriction_json is not None:
        create_data["restriction_json"] = Json(data.restriction_json)
    if data.reason is not None:
        create_data["reason"] = data.reason
    if data.valid_until is not None:
        create_data["valid_until"] = data.valid_until

    override = await prisma_client.db.alchemi_accountoverrideconfigtable.create(
        data=create_data,
    )

    return {
        "id": override.id,
        "name": override.name,
        "message": "Override config created successfully",
    }


@router.get("/list")
async def list_override_configs(
    request: Request,
    category: Optional[str] = Query(default=None, description="Filter by category"),
    entity_code: Optional[str] = Query(default=None, description="Filter by entity code"),
    scope_type: Optional[str] = Query(default=None, description="Filter by scope type"),
    _=Depends(require_account_access),
):
    """List account override configurations."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if category:
        where["category"] = category
    if entity_code:
        where["entity_code"] = entity_code
    if scope_type:
        where["scope_type"] = scope_type

    overrides = await prisma_client.db.alchemi_accountoverrideconfigtable.find_many(
        where=where,
        order={"valid_from": "desc"},
    )

    return {"overrides": overrides}


@router.put("/{override_id}")
async def update_override_config(
    override_id: str,
    data: OverrideConfigUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update an account override configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accountoverrideconfigtable.find_first(
        where={"id": override_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Override config not found")

    update_data: Dict[str, Any] = {}

    if data.product_code is not None:
        update_data["product_code"] = data.product_code
    if data.feature_code is not None:
        update_data["feature_code"] = data.feature_code
    if data.entity_code is not None:
        update_data["entity_code"] = data.entity_code
    if data.name is not None:
        update_data["name"] = data.name
    if data.category is not None:
        update_data["category"] = data.category
    if data.parent_entity_code is not None:
        update_data["parent_entity_code"] = data.parent_entity_code
    if data.distribution_kind is not None:
        update_data["distribution_kind"] = data.distribution_kind
    if data.action is not None:
        update_data["action"] = data.action
    if data.inherit is not None:
        update_data["inherit"] = data.inherit
    if data.scope_type is not None:
        update_data["scope_type"] = data.scope_type
    if data.scope_id is not None:
        update_data["scope_id"] = data.scope_id
    if data.reason is not None:
        update_data["reason"] = data.reason
    if data.valid_from is not None:
        update_data["valid_from"] = data.valid_from
    if data.valid_until is not None:
        update_data["valid_until"] = data.valid_until
    if data.value_config is not None:
        update_data["value_config"] = Json(data.value_config)
    if data.restriction_json is not None:
        update_data["restriction_json"] = Json(data.restriction_json)

    override = await prisma_client.db.alchemi_accountoverrideconfigtable.update(
        where={"id": override_id},
        data=update_data,
    )

    return override


@router.delete("/{override_id}")
async def delete_override_config(
    override_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Delete an account override configuration."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_accountoverrideconfigtable.find_first(
        where={"id": override_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Override config not found")

    await prisma_client.db.alchemi_accountoverrideconfigtable.delete(
        where={"id": override_id},
    )

    return {
        "message": "Override config deleted",
        "id": override_id,
    }
