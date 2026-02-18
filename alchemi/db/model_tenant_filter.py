"""
Tenant-aware model filtering utilities.

Filters in-memory Router model lists by account_id so that each tenant
only sees their own models. Super admins bypass filtering and see all models.
"""
from typing import Dict, List, Optional, Union

from fastapi import HTTPException

from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin


def _get_model_account_id(model: Dict) -> Optional[str]:
    """Extract account_id from a model dict's model_info."""
    model_info = model.get("model_info", {})
    if isinstance(model_info, dict):
        return model_info.get("account_id")
    return getattr(model_info, "account_id", None)


def filter_models_by_tenant(models: List[Dict]) -> List[Dict]:
    """
    Filter model dicts by model_info.account_id vs current request context.

    - Super admins see all models.
    - If no account_id is in context (background job), returns all models.
    - Otherwise, returns only models whose account_id matches the current tenant,
      plus models with no account_id (config-based models).
    """
    if is_super_admin():
        return models

    account_id = get_current_account_id()
    if account_id is None:
        return models

    return [
        m for m in models
        if _get_model_account_id(m) in (account_id, None)
    ]


def filter_model_names_by_tenant(
    names: List[str], router
) -> List[str]:
    """
    Filter model names by checking router deployments' account_id.

    For each model name, checks if any deployment with that name belongs
    to the current tenant. Config-based models (no account_id) are always included.
    """
    if is_super_admin():
        return names

    account_id = get_current_account_id()
    if account_id is None:
        return names

    if router is None:
        return names

    allowed_names = set()
    for model_name in names:
        deployments = router.get_model_list(model_name=model_name)
        if deployments is None:
            # No deployments found — include it (could be wildcard, access group, etc.)
            allowed_names.add(model_name)
            continue
        for deployment in deployments:
            dep_account_id = _get_model_account_id(deployment)
            if dep_account_id in (account_id, None):
                allowed_names.add(model_name)
                break

    return [name for name in names if name in allowed_names]


def validate_model_for_tenant(model_name: str, router) -> None:
    """
    Validate that a model belongs to the current tenant before allowing inference.

    Raises 404 if the model exists but doesn't belong to this tenant.
    Does nothing for super admins or when no account context.
    """
    if is_super_admin():
        return

    account_id = get_current_account_id()
    if account_id is None:
        return

    if router is None:
        return

    deployments = router.get_model_list(model_name=model_name)
    if deployments is None:
        # Model not found in router at all — let the normal 404 flow handle it
        return

    # Check if any deployment for this model belongs to the current tenant
    for deployment in deployments:
        dep_account_id = _get_model_account_id(deployment)
        if dep_account_id in (account_id, None):
            return  # At least one deployment is accessible

    # All deployments belong to other tenants
    raise HTTPException(
        status_code=404,
        detail={
            "error": f"Model '{model_name}' not found. Please check the model name and try again."
        },
    )


def filter_deployments_by_tenant(
    healthy_deployments: Union[List[Dict], Dict],
) -> Union[List[Dict], Dict]:
    """
    Filter Router deployments by tenant at the routing level.

    Called during deployment selection to ensure a tenant's request is ONLY
    routed to that tenant's deployments (correct API key). This prevents
    cross-tenant routing when two tenants add the same model name.

    - Super admins: see all deployments.
    - No account context (background jobs): all deployments.
    - Dict input (specific deployment): validate it belongs to tenant.
    - List input: filter to only this tenant's deployments.
    """
    if is_super_admin():
        return healthy_deployments

    account_id = get_current_account_id()
    if account_id is None:
        return healthy_deployments

    # Specific deployment (dict) — validate it belongs to tenant
    if isinstance(healthy_deployments, dict):
        dep_account_id = _get_model_account_id(healthy_deployments)
        if dep_account_id is not None and dep_account_id != account_id:
            return []  # Return empty list to trigger "no deployments" error
        return healthy_deployments

    # List of deployments — filter to this tenant's only
    return [
        d for d in healthy_deployments
        if _get_model_account_id(d) in (account_id, None)
    ]
