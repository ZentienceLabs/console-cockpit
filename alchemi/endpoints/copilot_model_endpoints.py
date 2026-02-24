"""
Copilot model governance endpoints.

- Super admins manage a centralized Copilot model catalog.
- Account admins enable/disable visibility per account (allowlist mode).
- Catalog is separated from generic gateway BYOK model registry.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from prisma import Json

from alchemi.db import copilot_db
from alchemi.endpoints.copilot_audit_helpers import log_copilot_audit_event
from alchemi.endpoints.copilot_auth import (
    require_copilot_admin_access,
    require_copilot_user_access,
)
from alchemi.middleware.account_middleware import resolve_tenant_from_request
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin

router = APIRouter(prefix="/copilot/models", tags=["Copilot - Models"])


class CopilotModelSelectionUpdate(BaseModel):
    selected_models: List[str] = Field(default_factory=list)
    account_id: Optional[str] = None
    scope: Optional[str] = None


class CopilotModelSelectionBulkUpdate(BaseModel):
    account_ids: List[str] = Field(default_factory=list)
    selected_models: List[str] = Field(default_factory=list)
    scope: Optional[str] = None


class CopilotModelCatalogCreate(BaseModel):
    model_name: str
    display_name: Optional[str] = None
    provider: Optional[str] = None
    upstream_model_name: Optional[str] = None
    credits_per_1k_tokens: float = 0.0
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CopilotModelCatalogUpdate(BaseModel):
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    provider: Optional[str] = None
    upstream_model_name: Optional[str] = None
    credits_per_1k_tokens: Optional[float] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class CopilotModelCatalogImportRequest(BaseModel):
    model_names: List[str] = Field(default_factory=list)


async def _resolve_target_account_id(request: Request, requested_account_id: Optional[str]) -> str:
    if not is_super_admin() and get_current_account_id() is None:
        resolve_tenant_from_request(request)

    if is_super_admin():
        if requested_account_id:
            return requested_account_id
        current = get_current_account_id()
        if current:
            return current
        raise HTTPException(status_code=400, detail="account_id is required for super admin requests.")

    current = get_current_account_id()
    if not current:
        raise HTTPException(status_code=403, detail="Tenant account context not found.")
    if requested_account_id and requested_account_id != current:
        raise HTTPException(status_code=403, detail="Cannot manage model selection for a different account.")
    return current


def _normalize_model_list(models: List[str]) -> List[str]:
    values = [m.strip() for m in models if isinstance(m, str) and m.strip()]
    return sorted(set(values))


def _require_super_admin() -> None:
    if not is_super_admin():
        raise HTTPException(status_code=403, detail="Super admin access required.")


async def _catalog_rows(include_inactive: bool = False) -> List[Dict[str, Any]]:
    rows = await copilot_db.model_catalog.find_many(
        where=None if include_inactive else {"is_active": True},
        order_by="lower(model_name) ASC",
        limit=2000,
    )
    return [dict(r) for r in rows]


async def _catalog_model_names() -> List[str]:
    rows = await _catalog_rows(include_inactive=False)
    names = [str(r.get("model_name") or "").strip() for r in rows]
    return sorted(set([name for name in names if name]))


def _router_model_names() -> List[str]:
    """Runtime gateway model names, exposed as optional bootstrap suggestions only."""
    from litellm.proxy.proxy_server import llm_router

    if llm_router is None:
        return []
    names = llm_router.get_model_names()
    return sorted(set([str(n).strip() for n in names if str(n).strip()]))


async def _catalog_exists_with_name(model_name: str, exclude_id: Optional[str] = None) -> bool:
    target = model_name.strip().lower()
    if not target:
        return False

    rows = await copilot_db.model_catalog.find_many(order_by="created_at DESC", limit=5000)
    for row in rows:
        row_name = str(row.get("model_name") or "").strip().lower()
        row_id = str(row.get("id") or "")
        if exclude_id and row_id == str(exclude_id):
            continue
        if row_name == target:
            return True
    return False


_LEGACY_ALLOWLIST_KEY = "copilot_model_allowlist"
_SUPER_ALLOWLIST_KEY = "copilot_model_super_allowlist"
_TENANT_ALLOWLIST_KEY = "copilot_model_tenant_allowlist"


def _get_allowlist_from_metadata(metadata: Any, key: str) -> List[str]:
    parsed = metadata if isinstance(metadata, dict) else {}
    entitlements = parsed.get("entitlements", {})
    stored_selection = entitlements.get(key, [])
    if not isinstance(stored_selection, list):
        stored_selection = []
    return _normalize_model_list(stored_selection)


def _set_allowlist_on_metadata(metadata: Any, key: str, allowlist: List[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = metadata if isinstance(metadata, dict) else {}
    entitlements = parsed.get("entitlements", {})
    entitlements[key] = allowlist
    parsed["entitlements"] = entitlements
    return parsed


def _read_model_allowlists(metadata: Any, catalog_set: set[str]) -> Dict[str, List[str]]:
    super_allowlist = [
        m for m in _get_allowlist_from_metadata(metadata, _SUPER_ALLOWLIST_KEY) if m in catalog_set
    ]
    tenant_allowlist = [
        m for m in _get_allowlist_from_metadata(metadata, _TENANT_ALLOWLIST_KEY) if m in catalog_set
    ]
    legacy_allowlist = [
        m for m in _get_allowlist_from_metadata(metadata, _LEGACY_ALLOWLIST_KEY) if m in catalog_set
    ]

    # Backward compatibility: if only the legacy key is populated, treat it as tenant selection.
    if not super_allowlist and not tenant_allowlist and legacy_allowlist:
        tenant_allowlist = legacy_allowlist

    return {
        "super": super_allowlist,
        "tenant": tenant_allowlist,
        "legacy": legacy_allowlist,
    }


def _compute_effective_model_sets(
    catalog: List[str],
    super_allowlist: List[str],
    tenant_allowlist: List[str],
) -> Dict[str, Any]:
    catalog_set = set(catalog)
    super_set = set([m for m in super_allowlist if m in catalog_set])
    tenant_set = set([m for m in tenant_allowlist if m in catalog_set])

    available_for_tenant = sorted(super_set) if super_set else catalog
    available_set = set(available_for_tenant)

    if tenant_set:
        effective_models = sorted(list(tenant_set.intersection(available_set)))
    else:
        effective_models = available_for_tenant

    if len(catalog) == 0:
        selection_mode = "no_catalog"
    elif super_set and tenant_set:
        selection_mode = "layered_allowlist"
    elif super_set:
        selection_mode = "super_allowlist"
    elif tenant_set:
        selection_mode = "tenant_allowlist"
    else:
        selection_mode = "all_catalog"

    return {
        "available_for_tenant_models": available_for_tenant,
        "effective_models": effective_models,
        "selection_mode": selection_mode,
        "super_scope_mode": "allowlist" if super_set else ("no_catalog" if len(catalog) == 0 else "all_catalog"),
        "tenant_scope_mode": "allowlist" if tenant_set else "all_available",
    }


def _normalize_scope_for_request(requested_scope: Optional[str]) -> str:
    if is_super_admin():
        scope = str(requested_scope or "super_admin").strip().lower()
        if scope not in {"super_admin", "tenant_admin"}:
            raise HTTPException(status_code=400, detail="scope must be 'super_admin' or 'tenant_admin'.")
        return scope

    if requested_scope and str(requested_scope).strip().lower() != "tenant_admin":
        raise HTTPException(status_code=403, detail="Tenant admins can only update tenant scope selection.")
    return "tenant_admin"


@router.get("/catalog")
async def list_model_catalog(
    request: Request,
    include_inactive: bool = False,
    _auth=Depends(require_copilot_admin_access),
):
    if not is_super_admin():
        include_inactive = False

    rows = await _catalog_rows(include_inactive=include_inactive)
    response: Dict[str, Any] = {
        "data": rows,
        "total": len(rows),
        "can_manage": bool(is_super_admin()),
    }
    if is_super_admin():
        response["router_suggestions"] = _router_model_names()
    return response


@router.post("/catalog")
async def create_model_catalog_entry(
    data: CopilotModelCatalogCreate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    _require_super_admin()

    model_name = str(data.model_name or "").strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="model_name is required.")

    if await _catalog_exists_with_name(model_name):
        raise HTTPException(status_code=409, detail="Model already exists in Copilot catalog.")

    payload = data.model_dump()
    payload["model_name"] = model_name
    if payload.get("display_name") is None:
        payload["display_name"] = model_name

    created = await copilot_db.model_catalog.create(payload)
    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_model_catalog",
        resource_type="model_catalog",
        resource_id=str(created.get("id") or ""),
        action="create",
        message=f"Created Copilot model catalog entry '{model_name}'.",
        details={"model_name": model_name, "provider": created.get("provider")},
        request=request,
    )
    return {"data": created}


@router.put("/catalog/{catalog_id}")
async def update_model_catalog_entry(
    catalog_id: str,
    data: CopilotModelCatalogUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    _require_super_admin()

    existing = await copilot_db.model_catalog.find_by_id(catalog_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Catalog model not found.")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "model_name" in update_data:
        model_name = str(update_data["model_name"] or "").strip()
        if not model_name:
            raise HTTPException(status_code=400, detail="model_name cannot be empty.")
        if await _catalog_exists_with_name(model_name, exclude_id=catalog_id):
            raise HTTPException(status_code=409, detail="Model already exists in Copilot catalog.")
        update_data["model_name"] = model_name

    updated = await copilot_db.model_catalog.update(catalog_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Catalog model not found.")

    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_model_catalog",
        resource_type="model_catalog",
        resource_id=str(catalog_id),
        action="update",
        message=f"Updated Copilot model catalog entry '{updated.get('model_name')}'.",
        details={"changes": list(update_data.keys())},
        request=request,
    )
    return {"data": updated}


@router.delete("/catalog/{catalog_id}")
async def delete_model_catalog_entry(
    catalog_id: str,
    request: Request,
    hard_delete: bool = False,
    _auth=Depends(require_copilot_admin_access),
):
    _require_super_admin()

    existing = await copilot_db.model_catalog.find_by_id(catalog_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Catalog model not found.")

    if hard_delete:
        deleted = await copilot_db.model_catalog.delete(catalog_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Catalog model not found.")
    else:
        await copilot_db.model_catalog.update(catalog_id, {"is_active": False})

    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_model_catalog",
        resource_type="model_catalog",
        resource_id=str(catalog_id),
        action="delete" if hard_delete else "disable",
        severity="warning",
        message=f"{'Deleted' if hard_delete else 'Disabled'} Copilot model catalog entry '{existing.get('model_name')}'.",
        details={"hard_delete": hard_delete},
        request=request,
    )
    return {"status": "ok"}


@router.post("/catalog/import/router")
async def import_model_catalog_from_router(
    data: CopilotModelCatalogImportRequest,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    _require_super_admin()

    router_names = _router_model_names()
    if not router_names:
        return {"data": {"imported": 0, "skipped": 0, "imported_models": []}}

    requested = _normalize_model_list(data.model_names)
    target_names = requested if requested else router_names
    router_set = set(router_names)
    target_names = [n for n in target_names if n in router_set]

    imported: List[str] = []
    skipped = 0

    for model_name in target_names:
        if await _catalog_exists_with_name(model_name):
            skipped += 1
            continue

        provider = model_name.split("/", 1)[0] if "/" in model_name else None
        await copilot_db.model_catalog.create(
            {
                "model_name": model_name,
                "display_name": model_name,
                "provider": provider,
                "source": "router_import",
                "upstream_model_name": model_name,
                "is_active": True,
                "metadata": {},
            }
        )
        imported.append(model_name)

    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_model_catalog",
        resource_type="model_catalog",
        action="import",
        message="Imported Copilot model catalog entries from gateway model registry.",
        details={"imported": imported, "skipped": skipped},
        request=request,
    )

    return {
        "data": {
            "imported": len(imported),
            "skipped": skipped,
            "imported_models": imported,
        }
    }


@router.get("/selection")
async def get_model_selection(
    request: Request,
    account_id: Optional[str] = None,
    _auth=Depends(require_copilot_user_access),
):
    # Super admins can inspect catalog globally without selecting account.
    if is_super_admin() and not account_id and get_current_account_id() is None:
        catalog = await _catalog_model_names()
        return {
            "account_id": None,
            "catalog_models": catalog,
            "available_for_tenant_models": catalog,
            "super_admin_selected_models": [],
            "tenant_selected_models": [],
            "selected_models": [],
            "effective_models": catalog,
            "selection_mode": "no_catalog" if len(catalog) == 0 else "all_catalog",
            "super_scope_mode": "no_catalog" if len(catalog) == 0 else "all_catalog",
            "tenant_scope_mode": "all_available",
        }

    target_account_id = await _resolve_target_account_id(request, account_id)

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": target_account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    metadata = account.metadata if isinstance(account.metadata, dict) else {}
    catalog = await _catalog_model_names()
    catalog_set = set(catalog)
    allowlists = _read_model_allowlists(metadata, catalog_set)
    super_selected_models = allowlists["super"]
    tenant_selected_models = allowlists["tenant"]
    computed = _compute_effective_model_sets(catalog, super_selected_models, tenant_selected_models)
    available_for_tenant_models = computed["available_for_tenant_models"]
    effective_models = computed["effective_models"]
    selection_mode = computed["selection_mode"]

    return {
        "account_id": target_account_id,
        "catalog_models": catalog,
        "available_for_tenant_models": available_for_tenant_models,
        "super_admin_selected_models": super_selected_models,
        "tenant_selected_models": tenant_selected_models,
        "selected_models": tenant_selected_models,
        "effective_models": effective_models,
        "selection_mode": selection_mode,
        "super_scope_mode": computed["super_scope_mode"],
        "tenant_scope_mode": computed["tenant_scope_mode"],
    }


@router.put("/selection")
async def update_model_selection(
    data: CopilotModelSelectionUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    target_account_id = await _resolve_target_account_id(request, data.account_id)

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": target_account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    scope = _normalize_scope_for_request(data.scope)
    catalog = await _catalog_model_names()
    catalog_set = set(catalog)
    requested = _normalize_model_list(data.selected_models)
    invalid = [m for m in requested if m not in catalog_set]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Some selected models are not in the Copilot catalog.",
                "invalid_models": invalid,
            },
        )

    metadata = account.metadata if isinstance(account.metadata, dict) else {}
    allowlists = _read_model_allowlists(metadata, catalog_set)

    if scope == "super_admin":
        super_selected_models = requested
        available_for_tenant = set(super_selected_models) if super_selected_models else set(catalog)
        tenant_selected_models = [m for m in allowlists["tenant"] if m in available_for_tenant]
        metadata = _set_allowlist_on_metadata(metadata, _SUPER_ALLOWLIST_KEY, super_selected_models)
        metadata = _set_allowlist_on_metadata(metadata, _TENANT_ALLOWLIST_KEY, tenant_selected_models)
        metadata = _set_allowlist_on_metadata(metadata, _LEGACY_ALLOWLIST_KEY, tenant_selected_models)
    else:
        available_for_tenant = set(allowlists["super"]) if allowlists["super"] else set(catalog)
        out_of_scope = [m for m in requested if m not in available_for_tenant]
        if out_of_scope:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Some selected models are not available for this account.",
                    "invalid_models": out_of_scope,
                },
            )
        super_selected_models = allowlists["super"]
        tenant_selected_models = requested
        metadata = _set_allowlist_on_metadata(metadata, _TENANT_ALLOWLIST_KEY, tenant_selected_models)
        metadata = _set_allowlist_on_metadata(metadata, _LEGACY_ALLOWLIST_KEY, tenant_selected_models)

    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": target_account_id},
        data={"metadata": Json(metadata)},
    )

    await log_copilot_audit_event(
        account_id=target_account_id,
        event_type="copilot_model_selection",
        resource_type="account",
        resource_id=target_account_id,
        action="update",
        message=f"Updated Copilot model visibility ({scope}).",
        details={
            "scope": scope,
            "selected_models": requested,
            "selected_count": len(requested),
        },
        request=request,
    )

    computed = _compute_effective_model_sets(
        catalog,
        super_selected_models,
        tenant_selected_models,
    )

    return {
        "status": "updated",
        "account_id": target_account_id,
        "scope": scope,
        "selected_models": tenant_selected_models,
        "super_admin_selected_models": super_selected_models,
        "tenant_selected_models": tenant_selected_models,
        "available_for_tenant_models": computed["available_for_tenant_models"],
        "effective_models": computed["effective_models"],
        "selection_mode": computed["selection_mode"],
    }


@router.get("/selection/accounts")
async def list_model_selection_accounts(
    request: Request,
    account_id: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    _auth=Depends(require_copilot_admin_access),
):
    """List account-level Copilot model selection state for global governance."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    catalog = await _catalog_model_names()
    catalog_set = set(catalog)

    where: Dict[str, Any] = {}
    if is_super_admin():
        if account_id:
            where["account_id"] = account_id
    else:
        target_account_id = await _resolve_target_account_id(request, account_id)
        where["account_id"] = target_account_id

    rows = await prisma_client.db.alchemi_accounttable.find_many(
        where=where if where else None,
        skip=offset,
        take=limit,
    )
    total = await prisma_client.db.alchemi_accounttable.count(where=where if where else None)

    data_rows: List[Dict[str, Any]] = []
    for account in rows:
        allowlists = _read_model_allowlists(account.metadata, catalog_set)
        super_selected_models = allowlists["super"]
        tenant_selected_models = allowlists["tenant"]
        computed = _compute_effective_model_sets(catalog, super_selected_models, tenant_selected_models)
        available_for_tenant_models = computed["available_for_tenant_models"]
        effective_models = computed["effective_models"]
        selection_mode = computed["selection_mode"]
        data_rows.append(
            {
                "account_id": account.account_id,
                "account_name": account.account_name,
                "status": account.status,
                "super_admin_selected_models": super_selected_models,
                "tenant_selected_models": tenant_selected_models,
                "selected_models": tenant_selected_models,
                "super_selected_count": len(super_selected_models),
                "tenant_selected_count": len(tenant_selected_models),
                "selected_count": len(tenant_selected_models),
                "available_count": len(available_for_tenant_models),
                "effective_count": len(effective_models),
                "selection_mode": selection_mode,
                "super_scope_mode": computed["super_scope_mode"],
                "tenant_scope_mode": computed["tenant_scope_mode"],
            }
        )

    return {"data": data_rows, "total": total}


@router.put("/selection/bulk")
async def bulk_update_model_selection(
    data: CopilotModelSelectionBulkUpdate,
    request: Request,
    _auth=Depends(require_copilot_admin_access),
):
    """Apply one allowlist to multiple accounts (super-admin global action)."""
    _require_super_admin()

    scope = str(data.scope or "super_admin").strip().lower()
    if scope not in {"super_admin", "tenant_admin"}:
        raise HTTPException(status_code=400, detail="scope must be 'super_admin' or 'tenant_admin'.")

    account_ids = [aid.strip() for aid in data.account_ids if isinstance(aid, str) and aid.strip()]
    if not account_ids:
        raise HTTPException(status_code=400, detail="account_ids is required.")

    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    catalog = await _catalog_model_names()
    catalog_set = set(catalog)
    requested = _normalize_model_list(data.selected_models)
    invalid = [m for m in requested if m not in catalog_set]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Some selected models are not in the Copilot catalog.",
                "invalid_models": invalid,
            },
        )

    updated_ids: List[str] = []
    skipped_ids: List[str] = []
    for account_id in dict.fromkeys(account_ids):
        account = await prisma_client.db.alchemi_accounttable.find_unique(
            where={"account_id": account_id}
        )
        if not account:
            skipped_ids.append(account_id)
            continue

        metadata = account.metadata if isinstance(account.metadata, dict) else {}
        allowlists = _read_model_allowlists(metadata, catalog_set)

        if scope == "super_admin":
            super_selected_models = requested
            available_for_tenant = set(super_selected_models) if super_selected_models else set(catalog)
            tenant_selected_models = [m for m in allowlists["tenant"] if m in available_for_tenant]
            metadata = _set_allowlist_on_metadata(metadata, _SUPER_ALLOWLIST_KEY, super_selected_models)
            metadata = _set_allowlist_on_metadata(metadata, _TENANT_ALLOWLIST_KEY, tenant_selected_models)
            metadata = _set_allowlist_on_metadata(metadata, _LEGACY_ALLOWLIST_KEY, tenant_selected_models)
        else:
            available_for_tenant = set(allowlists["super"]) if allowlists["super"] else set(catalog)
            if any(m not in available_for_tenant for m in requested):
                skipped_ids.append(account_id)
                continue
            tenant_selected_models = requested
            metadata = _set_allowlist_on_metadata(metadata, _TENANT_ALLOWLIST_KEY, tenant_selected_models)
            metadata = _set_allowlist_on_metadata(metadata, _LEGACY_ALLOWLIST_KEY, tenant_selected_models)

        await prisma_client.db.alchemi_accounttable.update(
            where={"account_id": account_id},
            data={"metadata": Json(metadata)},
        )
        updated_ids.append(account_id)

    await log_copilot_audit_event(
        account_id=None,
        event_type="copilot_model_selection",
        resource_type="account",
        action="bulk_update",
        message=f"Bulk-updated Copilot model allowlist across accounts ({scope}).",
        details={
            "scope": scope,
            "updated_accounts": updated_ids,
            "skipped_accounts": skipped_ids,
            "selected_models": requested,
        },
        request=request,
    )

    return {
        "data": {
            "scope": scope,
            "updated_count": len(updated_ids),
            "skipped_count": len(skipped_ids),
            "updated_accounts": updated_ids,
            "skipped_accounts": skipped_ids,
            "selected_models": requested,
            "effective_models": requested if requested else catalog,
        }
    }
