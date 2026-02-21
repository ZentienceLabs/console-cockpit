"""
Platform configuration endpoints.
CRUD for providers, model configs, default model assignments,
and sandbox pricing, scoped to the caller's account via tenant context.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prisma import Json
import uuid
from datetime import datetime

from alchemi.auth.service_auth import require_account_access, require_super_admin

router = APIRouter(prefix="/alchemi/config", tags=["Platform Config"])


# ── Request Models ───────────────────────────────────────────────────────────


class ProviderCreateRequest(BaseModel):
    name: str
    display_label: Optional[str] = None
    endpoint_env_var: Optional[str] = None
    api_key_env_var: Optional[str] = None
    is_active: Optional[bool] = True


class ProviderUpdateRequest(BaseModel):
    name: Optional[str] = None
    display_label: Optional[str] = None
    endpoint_env_var: Optional[str] = None
    api_key_env_var: Optional[str] = None
    is_active: Optional[bool] = None


class ModelConfigCreateRequest(BaseModel):
    provider_id: str
    deployment_name: str
    display_name: Optional[str] = None
    capability: Optional[str] = None
    input_cost_per_million: Optional[float] = 0.0
    output_cost_per_million: Optional[float] = 0.0
    content_capabilities: Optional[Dict[str, Any]] = None
    extra_body: Optional[Dict[str, Any]] = None
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True


class ModelConfigUpdateRequest(BaseModel):
    provider_id: Optional[str] = None
    deployment_name: Optional[str] = None
    display_name: Optional[str] = None
    capability: Optional[str] = None
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    content_capabilities: Optional[Dict[str, Any]] = None
    extra_body: Optional[Dict[str, Any]] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DefaultModelUpdateRequest(BaseModel):
    model_id: str


class SandboxPricingCreateRequest(BaseModel):
    resource_type: str
    unit: str
    cost_usd: float
    description: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


# ── Provider CRUD ─────────────────────────────────────────────────────────────


@router.post("/provider/new")
async def create_provider(
    data: ProviderCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new provider config."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    now = datetime.utcnow()
    provider = await prisma_client.db.alchemi_configprovidertable.create(
        data={
            "id": str(uuid.uuid4()),
            "name": data.name,
            "display_label": data.display_label,
            "endpoint_env_var": data.endpoint_env_var,
            "api_key_env_var": data.api_key_env_var,
            "is_active": data.is_active if data.is_active is not None else True,
            "account_id": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": provider.id,
        "name": provider.name,
        "message": "Provider created successfully",
    }


@router.get("/provider/list")
async def list_providers(
    request: Request,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    _=Depends(require_account_access),
):
    """List providers for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if is_active is not None:
        where["is_active"] = is_active

    providers = await prisma_client.db.alchemi_configprovidertable.find_many(
        where=where,
        order={"created_at": "desc"},
    )

    return {"providers": providers}


@router.put("/provider/{provider_id}")
async def update_provider(
    provider_id: str,
    data: ProviderUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a provider config."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_configprovidertable.find_first(
        where={"id": provider_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Provider not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.name is not None:
        update_data["name"] = data.name
    if data.display_label is not None:
        update_data["display_label"] = data.display_label
    if data.endpoint_env_var is not None:
        update_data["endpoint_env_var"] = data.endpoint_env_var
    if data.api_key_env_var is not None:
        update_data["api_key_env_var"] = data.api_key_env_var
    if data.is_active is not None:
        update_data["is_active"] = data.is_active

    provider = await prisma_client.db.alchemi_configprovidertable.update(
        where={"id": provider_id},
        data=update_data,
    )

    return provider


@router.delete("/provider/{provider_id}")
async def deactivate_provider(
    provider_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Deactivate a provider (soft delete by setting is_active to False)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_configprovidertable.find_first(
        where={"id": provider_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Provider not found")

    await prisma_client.db.alchemi_configprovidertable.update(
        where={"id": provider_id},
        data={"is_active": False, "updated_at": datetime.utcnow()},
    )

    return {
        "message": f"Provider '{existing.name}' deactivated",
        "id": provider_id,
    }


# ── Model Config CRUD ────────────────────────────────────────────────────────


@router.post("/model/new")
async def create_model_config(
    data: ModelConfigCreateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Create a new model config."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    # Verify provider exists and belongs to this account
    provider = await prisma_client.db.alchemi_configprovidertable.find_first(
        where={"id": data.provider_id, "account_id": account_id},
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    now = datetime.utcnow()
    model = await prisma_client.db.alchemi_configmodeltable.create(
        data={
            "id": str(uuid.uuid4()),
            "provider_id": data.provider_id,
            "deployment_name": data.deployment_name,
            "display_name": data.display_name,
            "capability": data.capability,
            "input_cost_per_million": data.input_cost_per_million or 0.0,
            "output_cost_per_million": data.output_cost_per_million or 0.0,
            "content_capabilities": Json(data.content_capabilities or {}),
            "extra_body": Json(data.extra_body or {}),
            "sort_order": data.sort_order or 0,
            "is_active": data.is_active if data.is_active is not None else True,
            "account_id": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": model.id,
        "deployment_name": model.deployment_name,
        "message": "Model config created successfully",
    }


@router.get("/model/list")
async def list_model_configs(
    request: Request,
    provider_id: Optional[str] = Query(None, description="Filter by provider"),
    capability: Optional[str] = Query(None, description="Filter by capability"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    _=Depends(require_account_access),
):
    """List model configs for the current account with optional filters."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if provider_id:
        where["provider_id"] = provider_id
    if capability:
        where["capability"] = capability
    if is_active is not None:
        where["is_active"] = is_active

    models = await prisma_client.db.alchemi_configmodeltable.find_many(
        where=where,
        include={"provider": True},
        order={"sort_order": "asc"},
    )

    return {"models": models}


@router.put("/model/{model_id}")
async def update_model_config(
    model_id: str,
    data: ModelConfigUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a model config."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_configmodeltable.find_first(
        where={"id": model_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Model config not found")

    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

    if data.provider_id is not None:
        # Verify new provider exists and belongs to this account
        provider = await prisma_client.db.alchemi_configprovidertable.find_first(
            where={"id": data.provider_id, "account_id": account_id},
        )
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        update_data["provider_id"] = data.provider_id
    if data.deployment_name is not None:
        update_data["deployment_name"] = data.deployment_name
    if data.display_name is not None:
        update_data["display_name"] = data.display_name
    if data.capability is not None:
        update_data["capability"] = data.capability
    if data.input_cost_per_million is not None:
        update_data["input_cost_per_million"] = data.input_cost_per_million
    if data.output_cost_per_million is not None:
        update_data["output_cost_per_million"] = data.output_cost_per_million
    if data.content_capabilities is not None:
        update_data["content_capabilities"] = Json(data.content_capabilities)
    if data.extra_body is not None:
        update_data["extra_body"] = Json(data.extra_body)
    if data.sort_order is not None:
        update_data["sort_order"] = data.sort_order
    if data.is_active is not None:
        update_data["is_active"] = data.is_active

    model = await prisma_client.db.alchemi_configmodeltable.update(
        where={"id": model_id},
        data=update_data,
    )

    return model


@router.delete("/model/{model_id}")
async def deactivate_model_config(
    model_id: str,
    request: Request,
    _=Depends(require_account_access),
):
    """Deactivate a model config (soft delete by setting is_active to False)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_configmodeltable.find_first(
        where={"id": model_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Model config not found")

    await prisma_client.db.alchemi_configmodeltable.update(
        where={"id": model_id},
        data={"is_active": False, "updated_at": datetime.utcnow()},
    )

    return {
        "message": f"Model config '{existing.deployment_name}' deactivated",
        "id": model_id,
    }


# ── Default Model Assignments ────────────────────────────────────────────────


@router.get("/defaults")
async def list_default_models(
    request: Request,
    _=Depends(require_account_access),
):
    """List default model assignments for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    defaults = await prisma_client.db.alchemi_configdefaultmodeltable.find_many(
        where={"account_id": account_id},
        order={"created_at": "desc"},
    )

    return {"defaults": defaults}


@router.put("/defaults/{default_id}")
async def update_default_model(
    default_id: str,
    data: DefaultModelUpdateRequest,
    request: Request,
    _=Depends(require_account_access),
):
    """Update a default model assignment."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    existing = await prisma_client.db.alchemi_configdefaultmodeltable.find_first(
        where={"id": default_id, "account_id": account_id},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Default model assignment not found")

    # Verify the new model exists and belongs to this account
    model = await prisma_client.db.alchemi_configmodeltable.find_first(
        where={"id": data.model_id, "account_id": account_id},
    )
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    default = await prisma_client.db.alchemi_configdefaultmodeltable.update(
        where={"id": default_id},
        data={
            "model_id": data.model_id,
            "updated_at": datetime.utcnow(),
        },
    )

    return default


# ── Sandbox Pricing ──────────────────────────────────────────────────────────


@router.get("/sandbox-pricing/list")
async def list_sandbox_pricing(
    request: Request,
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    _=Depends(require_account_access),
):
    """List sandbox pricing entries for the current account."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    where: Dict[str, Any] = {"account_id": account_id}
    if resource_type:
        where["resource_type"] = resource_type

    pricing = await prisma_client.db.alchemi_configsandboxpricingtable.find_many(
        where=where,
        order={"effective_from": "desc"},
    )

    return {"pricing": pricing}


@router.post("/sandbox-pricing/new")
async def create_sandbox_pricing(
    data: SandboxPricingCreateRequest,
    request: Request,
    _=Depends(require_super_admin),
):
    """Create a sandbox pricing entry (super admin only)."""
    from litellm.proxy.proxy_server import prisma_client
    from alchemi.middleware.tenant_context import get_current_account_id

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account_id = get_current_account_id()

    now = datetime.utcnow()
    pricing = await prisma_client.db.alchemi_configsandboxpricingtable.create(
        data={
            "id": str(uuid.uuid4()),
            "resource_type": data.resource_type,
            "unit": data.unit,
            "cost_usd": data.cost_usd,
            "description": data.description,
            "effective_from": data.effective_from or now,
            "effective_to": data.effective_to,
            "account_id": account_id,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {
        "id": pricing.id,
        "resource_type": pricing.resource_type,
        "message": "Sandbox pricing entry created successfully",
    }
