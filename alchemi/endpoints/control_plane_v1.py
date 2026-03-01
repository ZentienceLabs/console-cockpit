"""Unified control plane v1 APIs for Console + Copilot."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from prisma import Json

from alchemi.policy.control_plane_policy import (
    require_account_admin,
    require_domain_admin,
    require_super_admin,
)
from alchemi.middleware.tenant_context import (
    get_current_account_id,
    get_current_auth_provider,
    get_current_product_domains,
    get_current_roles,
    get_current_scopes,
    is_super_admin,
)
from alchemi.auth.zitadel import ZitadelManagementClient
from alchemi.auth.zitadel import get_zitadel_settings

router = APIRouter(prefix="/v1", tags=["Control Plane v1"])

VALID_SCOPE_TYPES = {"account", "org", "team", "user"}
VALID_BUDGET_SCOPE_TYPES = {"org", "team", "user", "pool"}
VALID_ACCESS_MODES = {"allow", "deny"}
VALID_CONNECTION_TYPES = {"openapi", "mcp", "composio"}
VALID_CONNECTION_VISIBILITY = {"use_only", "self_managed"}
VALID_GUARD_TYPES = {"pii", "toxic", "jailbreak"}
VALID_PATTERN_TYPES = {"detect", "block", "allow"}

DEFAULT_ZITADEL_ROLE_DEFINITIONS = [
    {"key": "account_admin", "display_name": "Account Admin", "group": "account"},
    {"key": "console_org_admin", "display_name": "Console Org Admin", "group": "console"},
    {"key": "console_team_admin", "display_name": "Console Team Admin", "group": "console"},
    {"key": "copilot_org_admin", "display_name": "Copilot Org Admin", "group": "copilot"},
    {"key": "copilot_team_admin", "display_name": "Copilot Team Admin", "group": "copilot"},
    {"key": "end_user", "display_name": "End User", "group": "common"},
]

DEFAULT_ZITADEL_ROLE_MAPPINGS = {
    "account_admin": "account_admin",
    "console_org_admin": "console_org_admin",
    "console_team_admin": "console_team_admin",
    "copilot_org_admin": "copilot_org_admin",
    "copilot_team_admin": "copilot_team_admin",
    "end_user": "end_user",
}
ZITADEL_ONBOARDING_DEFAULTS_PARAM_NAME = "alchemi_zitadel_onboarding_defaults"

SUPER_MODEL_PROVIDER_DEFAULTS: Dict[str, Dict[str, Optional[str]]] = {
    "azure_openai": {
        "litellm_provider": "azure",
        "api_base_env_var": "AZURE_OPENAI_ENDPOINT",
        "api_key_env_var": "AZURE_OPENAI_API_KEY",
    },
    "azure_anthropic": {
        "litellm_provider": "anthropic",
        "api_base_env_var": "AZURE_ANTHROPIC_ENDPOINT",
        "api_key_env_var": "AZURE_ANTHROPIC_API_KEY",
    },
    "azure_xai": {
        "litellm_provider": "openai",
        "api_base_env_var": "AZURE_XAI_ENDPOINT",
        "api_key_env_var": "AZURE_XAI_API_KEY",
    },
    "vertex_ai": {
        "litellm_provider": "gemini",
        "api_base_env_var": None,
        "api_key_env_var": "GOOGLE_API_KEY",
    },
}


def _normalize_copilot_scope_type(scope_type: str) -> str:
    normalized = (scope_type or "").strip().lower()
    if normalized in {"group", "org"}:
        return "org"
    if normalized in {"team", "user", "account", "pool"}:
        return normalized
    return normalized


def _normalize_connection_type(connection_type: str) -> str:
    normalized = (connection_type or "").strip().lower()
    if normalized == "integration":
        return "composio"
    return normalized


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


async def _db():
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    return prisma_client.db


async def _audit_event(
    db: Any,
    action: str,
    table_name: str,
    object_id: str,
    before_value: Optional[Dict[str, Any]],
    updated_values: Optional[Dict[str, Any]],
    domain: str,
    changed_by: str = "account_admin",
) -> None:
    account_id = get_current_account_id()
    payload = dict(updated_values or {})
    payload.setdefault("domain", domain)
    try:
        before_payload = _to_jsonable(before_value or {})
        updated_payload = _to_jsonable(payload)
        await db.query_raw(
            'INSERT INTO "LiteLLM_AuditLog" (id, updated_at, changed_by, changed_by_api_key, action, table_name, object_id, before_value, updated_values, account_id) '
            'VALUES ($1, CURRENT_TIMESTAMP, $2, $3, $4, $5, $6, $7, $8, $9)',
            str(uuid.uuid4()),
            changed_by,
            "",
            action,
            table_name,
            object_id,
            Json(before_payload),
            Json(updated_payload),
            account_id,
        )
    except Exception:
        # Audit failures should not break control-plane writes.
        return


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    return value


def _record_to_dict(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()  # type: ignore[no-any-return]
    try:
        return dict(value)
    except Exception:
        return None


def _hash_password(password: str) -> str:
    from litellm.proxy._types import hash_token

    return hash_token(password)


def _mask_sso_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    masked = dict(settings or {})
    secret_keys = {
        "google_client_secret",
        "microsoft_client_secret",
        "generic_client_secret",
        "client_secret",
        "secret",
    }
    for key in secret_keys:
        if masked.get(key):
            masked[key] = "••••••••"
    return masked


def _merge_sso_settings(old_settings: Dict[str, Any], new_settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(old_settings or {})
    for key, value in (new_settings or {}).items():
        if value in (None, ""):
            continue
        # Keep existing secret when UI posts a masked placeholder
        if isinstance(value, str) and value == "••••••••" and key.endswith("secret"):
            continue
        merged[key] = value
    return merged


def _decode_json_field(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        import json

        return json.loads(value)
    except Exception:
        return default


def _env_ref(env_var: Optional[str]) -> Optional[str]:
    if not env_var:
        return None
    return f"os.environ/{env_var}"


def _build_super_model_payload(req: "SuperModelUpsertRequest", existing_model_id: Optional[str] = None) -> Dict[str, Any]:
    provider_defaults = SUPER_MODEL_PROVIDER_DEFAULTS.get((req.provider_id or "").strip().lower(), {})
    litellm_provider = (req.litellm_provider or provider_defaults.get("litellm_provider") or "").strip()
    deployment_name = (req.deployment_name or "").strip()
    if not deployment_name:
        raise HTTPException(status_code=400, detail="deployment_name is required")

    if litellm_provider:
        litellm_model = f"{litellm_provider}/{deployment_name}"
    else:
        litellm_model = deployment_name

    api_base_env_var = req.api_base_env_var or provider_defaults.get("api_base_env_var")
    api_key_env_var = req.api_key_env_var or provider_defaults.get("api_key_env_var")
    litellm_params: Dict[str, Any] = {"model": litellm_model}
    api_base_ref = _env_ref(api_base_env_var)
    api_key_ref = _env_ref(api_key_env_var)
    if api_base_ref:
        litellm_params["api_base"] = api_base_ref
    if api_key_ref:
        litellm_params["api_key"] = api_key_ref
    if req.extra_body:
        litellm_params["extra_body"] = req.extra_body

    model_id = existing_model_id or req.model_id or str(uuid.uuid4())
    model_info: Dict[str, Any] = {
        "id": model_id,
        "display_name": req.display_name or req.model_name,
        "provider_id": req.provider_id,
        "deployment_name": deployment_name,
        "capability": req.capability,
        "is_active": req.is_active,
        "sort_order": req.sort_order,
        "source": "super_admin_catalog",
        "api_base_env_var": api_base_env_var,
        "api_key_env_var": api_key_env_var,
        "input_cost_per_token": (float(req.input_cost_per_million) / 1_000_000.0) if req.input_cost_per_million is not None else None,
        "output_cost_per_token": (float(req.output_cost_per_million) / 1_000_000.0) if req.output_cost_per_million is not None else None,
    }
    if req.content_capabilities:
        model_info["content_capabilities"] = req.content_capabilities
    if req.extra_body:
        model_info["extra_body"] = req.extra_body

    # Drop null values to keep payloads compact.
    model_info = {k: v for k, v in model_info.items() if v is not None}

    return {
        "model_id": model_id,
        "litellm_params": litellm_params,
        "model_info": model_info,
    }


async def _refresh_proxy_deployments() -> None:
    try:
        from litellm.proxy.proxy_server import proxy_config, prisma_client, proxy_logging_obj
    except Exception:
        return
    if prisma_client is None:
        return
    try:
        await proxy_config.add_deployment(
            prisma_client=prisma_client,
            proxy_logging_obj=proxy_logging_obj,
        )
    except Exception:
        return


def _domain_tables(domain: str) -> Dict[str, str]:
    if domain == "copilot":
        return {
            "org": '"Alchemi_CopilotOrgTable"',
            "team": '"Alchemi_CopilotTeamTable"',
            "user": '"Alchemi_CopilotUserTable"',
            "membership": '"Alchemi_CopilotTeamMembershipTable"',
        }
    if domain == "console":
        return {
            "org": '"Alchemi_ConsoleOrgTable"',
            "team": '"Alchemi_ConsoleTeamTable"',
            "user": '"Alchemi_ConsoleUserTable"',
            "membership": '"Alchemi_ConsoleTeamMembershipTable"',
        }
    raise HTTPException(status_code=400, detail=f"Invalid domain: {domain}")


def _validate_scope_type(scope_type: str, allowed: set[str]) -> None:
    if scope_type not in allowed:
        allowed_values = ",".join(sorted(allowed))
        raise HTTPException(status_code=400, detail=f"scope_type must be one of: {allowed_values}")


def _mask_connection_secrets(row: Any) -> Dict[str, Any]:
    item = dict(row)
    item["secret_json"] = {"masked": True}
    return item


def _pattern_from_raw(pattern: Dict[str, Any], account_id: str, guard_type: str) -> Dict[str, Any]:
    return {
        "id": pattern.get("id"),
        "account_id": account_id,
        "guard_type": guard_type,
        "pattern_name": pattern.get("pattern_name"),
        "pattern_regex": pattern.get("pattern_regex"),
        "pattern_type": pattern.get("pattern_type"),
        "action": pattern.get("action"),
        "enabled": bool(pattern.get("enabled", True)),
        "is_system": bool(pattern.get("is_system", False)),
        "created_at": pattern.get("created_at"),
        "updated_at": pattern.get("updated_at"),
    }


async def _ensure_domain_scope_exists(db: Any, domain: str, scope_type: str, scope_id: str, account_id: str) -> None:
    if scope_type == "account":
        if scope_id != account_id:
            raise HTTPException(status_code=400, detail="account scope_id must match current account_id")
        return
    if scope_type == "pool":
        return

    t = _domain_tables(domain)
    if scope_type == "org":
        rows = await db.query_raw(f"SELECT id FROM {t['org']} WHERE id = $1 AND account_id = $2 LIMIT 1", scope_id, account_id)
    elif scope_type == "team":
        rows = await db.query_raw(f"SELECT id FROM {t['team']} WHERE id = $1 AND account_id = $2 LIMIT 1", scope_id, account_id)
    elif scope_type == "user":
        rows = await db.query_raw(f"SELECT id FROM {t['user']} WHERE id = $1 AND account_id = $2 LIMIT 1", scope_id, account_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported scope_type: {scope_type}")

    if not rows:
        raise HTTPException(status_code=404, detail=f"{domain} {scope_type} not found")


async def _ensure_copilot_agent_exists(db: Any, account_id: str, agent_id: str) -> None:
    rows = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotAgentTable" WHERE id = $1 AND account_id = $2 LIMIT 1',
        agent_id,
        account_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Copilot agent not found")


async def _ensure_guardrail_presets_exist(db: Any, account_id: str, preset_ids: List[str]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for preset_id in preset_ids:
        value = str(preset_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="At least one guardrail preset is required for agent creation/update",
        )

    rows = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotGuardrailPresetTable" WHERE account_id = $1 AND id = ANY($2::text[])',
        account_id,
        normalized,
    )
    existing_ids = {str(_row_get(r, "id")) for r in rows}
    missing = [preset_id for preset_id in normalized if preset_id not in existing_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Guardrail preset not found: {','.join(missing)}")

    return normalized


async def _set_agent_guardrail_assignments(db: Any, account_id: str, agent_id: str, preset_ids: List[str]) -> None:
    await db.query_raw(
        'DELETE FROM "Alchemi_CopilotGuardrailAssignmentTable" WHERE account_id = $1 AND scope_type = $2 AND scope_id = $3',
        account_id,
        "agent",
        agent_id,
    )
    for preset_id in preset_ids:
        await db.query_raw(
            'INSERT INTO "Alchemi_CopilotGuardrailAssignmentTable" (id, account_id, preset_id, scope_type, scope_id, created_by) VALUES ($1,$2,$3,$4,$5,$6)',
            str(uuid.uuid4()),
            account_id,
            preset_id,
            "agent",
            agent_id,
            "account_admin",
        )


async def _get_agent_guardrail_preset_ids(db: Any, account_id: str, agent_id: str) -> List[str]:
    rows = await db.query_raw(
        'SELECT preset_id FROM "Alchemi_CopilotGuardrailAssignmentTable" WHERE account_id = $1 AND scope_type = $2 AND scope_id = $3 ORDER BY created_at ASC',
        account_id,
        "agent",
        agent_id,
    )
    return [str(_row_get(r, "preset_id")) for r in rows if _row_get(r, "preset_id")]


async def _set_agent_grants(
    db: Any,
    account_id: str,
    agent_id: str,
    grants: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    seen: set[str] = set()
    for grant in grants:
        scope_type = str((grant or {}).get("scope_type") or "").strip()
        scope_id = str((grant or {}).get("scope_id") or "").strip()
        _validate_scope_type(scope_type, {"org", "team", "user"})
        if not scope_id:
            raise HTTPException(status_code=400, detail="scope_id is required for agent grants")
        key = f"{scope_type}:{scope_id}"
        if key in seen:
            continue
        seen.add(key)
        await _ensure_domain_scope_exists(db, "copilot", scope_type, scope_id, account_id)
        normalized.append({"scope_type": scope_type, "scope_id": scope_id})

    await db.query_raw(
        'DELETE FROM "Alchemi_CopilotAgentGrantTable" WHERE account_id = $1 AND agent_id = $2',
        account_id,
        agent_id,
    )

    for grant in normalized:
        await db.query_raw(
            'INSERT INTO "Alchemi_CopilotAgentGrantTable" (id, account_id, agent_id, scope_type, scope_id, created_by) VALUES ($1,$2,$3,$4,$5,$6)',
            str(uuid.uuid4()),
            account_id,
            agent_id,
            grant["scope_type"],
            grant["scope_id"],
            "account_admin",
        )

    return normalized


async def _list_agent_grants(db: Any, account_id: str, agent_id: str) -> List[Dict[str, str]]:
    rows = await db.query_raw(
        'SELECT scope_type, scope_id FROM "Alchemi_CopilotAgentGrantTable" WHERE account_id = $1 AND agent_id = $2 ORDER BY created_at ASC',
        account_id,
        agent_id,
    )
    return [{"scope_type": str(_row_get(r, "scope_type")), "scope_id": str(_row_get(r, "scope_id"))} for r in rows]


async def _set_marketplace_grants(db: Any, account_id: str, marketplace_id: str, grants: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    seen: set[str] = set()
    for grant in grants:
        scope_type = str((grant or {}).get("scope_type") or "").strip()
        scope_id = str((grant or {}).get("scope_id") or "").strip()
        _validate_scope_type(scope_type, {"org", "team", "user"})
        if not scope_id:
            raise HTTPException(status_code=400, detail="scope_id is required for marketplace grants")
        key = f"{scope_type}:{scope_id}"
        if key in seen:
            continue
        seen.add(key)
        await _ensure_domain_scope_exists(db, "copilot", scope_type, scope_id, account_id)
        normalized.append({"scope_type": scope_type, "scope_id": scope_id})

    await db.query_raw(
        'DELETE FROM "Alchemi_CopilotMarketplaceGrantTable" WHERE account_id = $1 AND marketplace_id = $2',
        account_id,
        marketplace_id,
    )

    for grant in normalized:
        await db.query_raw(
            'INSERT INTO "Alchemi_CopilotMarketplaceGrantTable" (id, account_id, marketplace_id, scope_type, scope_id, created_by) VALUES ($1,$2,$3,$4,$5,$6)',
            str(uuid.uuid4()),
            account_id,
            marketplace_id,
            grant["scope_type"],
            grant["scope_id"],
            "account_admin",
        )

    return normalized


async def _list_marketplace_grants(db: Any, account_id: str, marketplace_id: str) -> List[Dict[str, str]]:
    rows = await db.query_raw(
        'SELECT scope_type, scope_id FROM "Alchemi_CopilotMarketplaceGrantTable" WHERE account_id = $1 AND marketplace_id = $2 ORDER BY created_at ASC',
        account_id,
        marketplace_id,
    )
    return [{"scope_type": str(_row_get(r, "scope_type")), "scope_id": str(_row_get(r, "scope_id"))} for r in rows]


async def _get_or_create_guardrail_preset_by_code(db: Any, account_id: str, code: str) -> Dict[str, Any]:
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotGuardrailPresetTable" WHERE account_id = $1 AND code = $2 LIMIT 1',
        account_id,
        code,
    )
    if rows:
        return dict(rows[0])

    created = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotGuardrailPresetTable" (id, account_id, code, name, preset_json, created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        code,
        code.upper(),
        Json({"config": {}, "custom_patterns": []}),
        "account_admin",
    )
    return dict(created[0])


def _scope_chain(org_id: Optional[str], team_id: Optional[str], user_id: Optional[str]) -> List[tuple[str, str]]:
    chain: List[tuple[str, str]] = []
    if user_id:
        chain.append(("user", user_id))
    if team_id:
        chain.append(("team", team_id))
    if org_id:
        chain.append(("org", org_id))
    chain.append(("account", get_current_account_id()))
    return chain


async def _ensure_default_copilot_global_org(db: Any, account_id: str, created_by: Optional[str]) -> None:
    exists = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotOrgTable" WHERE account_id = $1 AND is_default_global = TRUE LIMIT 1',
        account_id,
    )
    if exists:
        return
    await db.query_raw(
        'INSERT INTO "Alchemi_CopilotOrgTable" (id, account_id, name, description, is_default_global, created_by) VALUES ($1, $2, $3, $4, TRUE, $5)',
        str(uuid.uuid4()),
        account_id,
        "global",
        "Default global organization",
        created_by,
    )


async def _fetch_account_bundle(db: Any, account_id: str) -> Optional[Dict[str, Any]]:
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        return None
    admins = await db.alchemi_accountadmintable.find_many(where={"account_id": account_id}, order={"created_at": "desc"})
    sso = await db.alchemi_accountssoconfig.find_first(where={"account_id": account_id})
    allocation = await db.query_raw(
        'SELECT monthly_credits, overflow_limit, credit_factor, effective_from, updated_at '
        'FROM "Alchemi_AccountAllocationTable" WHERE account_id = $1 LIMIT 1',
        account_id,
    )

    item = _to_jsonable(_record_to_dict(account) or {})
    item["admins"] = [_to_jsonable(_record_to_dict(a) or {}) for a in admins]
    if sso:
        sso_dict = _to_jsonable(_record_to_dict(sso) or {})
        settings = _decode_json_field(sso_dict.get("sso_settings"), {})
        sso_dict["sso_settings"] = _mask_sso_settings(settings)
        item["sso_config"] = sso_dict
    else:
        item["sso_config"] = None
    item["allocation"] = _to_jsonable(dict(allocation[0])) if allocation else None
    metadata = _decode_json_field(item.get("metadata"), {})
    item["feature_pack"] = metadata.get("feature_pack", {"features": [], "config": {}})
    item["console_model_policy"] = metadata.get(
        "console_model_policy",
        {"allow_models": [], "deny_models": []},
    )
    item["zitadel_config"] = metadata.get("zitadel", {})
    return item


class AccountCreateRequest(BaseModel):
    account_name: str
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    max_budget: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None


class AccountAdminRequest(BaseModel):
    user_email: str
    password: Optional[str] = None
    role: str = "account_admin"


class AccountUpdateRequest(BaseModel):
    account_name: Optional[str] = None
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    status: Optional[str] = None
    max_budget: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class AccountStatusRequest(BaseModel):
    status: str


class AccountAdminUpdateRequest(BaseModel):
    new_email: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None


class AccountFeaturePackRequest(BaseModel):
    features: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)


class AccountConsoleModelPolicyRequest(BaseModel):
    allow_models: List[str] = Field(default_factory=list)
    deny_models: List[str] = Field(default_factory=list)


class SuperModelUpsertRequest(BaseModel):
    model_id: Optional[str] = None
    model_name: str
    provider_id: Optional[str] = None
    deployment_name: str
    display_name: Optional[str] = None
    capability: Optional[str] = None
    input_cost_per_million: Optional[float] = None
    output_cost_per_million: Optional[float] = None
    content_capabilities: Dict[str, Any] = Field(default_factory=dict)
    extra_body: Dict[str, Any] = Field(default_factory=dict)
    api_base_env_var: Optional[str] = None
    api_key_env_var: Optional[str] = None
    litellm_provider: Optional[str] = None
    is_active: bool = True
    sort_order: int = 100


class ZitadelAccountConfigRequest(BaseModel):
    enabled: bool = True
    issuer: Optional[str] = None
    audience: Optional[str] = None
    project_id: Optional[str] = None
    organization_id: Optional[str] = None
    role_mappings: Dict[str, str] = Field(default_factory=dict)
    account_id_claim: Optional[str] = None
    product_domains_claim: Optional[str] = None


class ZitadelProvisionGrantRequest(BaseModel):
    user_id: str
    role_keys: List[str] = Field(default_factory=list)
    project_id: Optional[str] = None
    organization_id: Optional[str] = None


class ZitadelProjectRoleRequest(BaseModel):
    key: str
    display_name: str
    group: Optional[str] = None
    project_id: Optional[str] = None


class ZitadelSyncRolesRequest(BaseModel):
    project_id: Optional[str] = None
    role_prefix: Optional[str] = None
    skip_existing: bool = True


class ZitadelSyncAdminGrantsRequest(BaseModel):
    project_id: Optional[str] = None
    organization_id: Optional[str] = None
    role_prefix: Optional[str] = None
    user_id_by_email: Dict[str, str] = Field(default_factory=dict)
    resolve_user_ids_from_zitadel: bool = False
    default_role_keys: List[str] = Field(default_factory=list)
    skip_existing: bool = True


class ZitadelBootstrapRequest(BaseModel):
    project_id: Optional[str] = None
    organization_id: Optional[str] = None
    role_prefix: Optional[str] = None
    apply_default_role_mappings: bool = True
    create_project_roles: bool = True
    grant_existing_account_admins: bool = True
    user_id_by_email: Dict[str, str] = Field(default_factory=dict)
    resolve_user_ids_from_zitadel: bool = False
    default_role_keys: List[str] = Field(default_factory=list)
    skip_existing: bool = True
    dry_run: bool = False


class ZitadelOnboardingDefaultsRequest(BaseModel):
    project_id: Optional[str] = None
    organization_id: Optional[str] = None
    role_prefix: Optional[str] = None
    resolve_user_ids_from_zitadel: bool = True


class AccountSsoRequest(BaseModel):
    sso_provider: Optional[str] = None
    enabled: bool = False
    sso_settings: Dict[str, Any] = Field(default_factory=dict)


class DomainOrgCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class DomainTeamCreateRequest(BaseModel):
    org_id: str
    name: str
    description: Optional[str] = None


class DomainUserCreateRequest(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    identity_user_id: Optional[str] = None
    team_ids: List[str] = Field(default_factory=list)


class AccountAllocationRequest(BaseModel):
    account_id: str
    monthly_credits: float = 0
    overflow_limit: float = 0
    credit_factor: float = 1


class BudgetPlanRequest(BaseModel):
    name: str
    cycle: str = "monthly"


class BudgetPlanUpdateRequest(BaseModel):
    name: str


class BudgetAllocationUpsertRequest(BaseModel):
    plan_id: str
    scope_type: str
    scope_id: str
    allocated_credits: float
    overflow_cap: Optional[float] = None
    source: str = "manual"


class EqualDistributeRequest(BaseModel):
    plan_id: str
    scope_type: str
    scope_ids: List[str]
    total_credits: float
    overflow_cap: Optional[float] = None


class BudgetOverrideRequest(BaseModel):
    plan_id: str
    scope_type: str
    scope_id: str
    override_credits: float
    reason: Optional[str] = None


class BudgetCycleRenewRequest(BaseModel):
    cycle_start: datetime
    cycle_end: datetime
    new_plan_name: Optional[str] = None
    rollover_cap: Optional[float] = None
    copy_overrides: bool = False


class UsageRecordRequest(BaseModel):
    org_id: Optional[str] = None
    team_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    model_name: Optional[str] = None
    connection_id: Optional[str] = None
    guardrail_code: Optional[str] = None
    raw_cost: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CopilotAgentRequest(BaseModel):
    name: str
    description: Optional[str] = None
    definition_json: Dict[str, Any] = Field(default_factory=dict)
    grants: List[Dict[str, str]] = Field(default_factory=list)
    guardrail_preset_ids: List[str] = Field(default_factory=list)


class CopilotAgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    definition_json: Optional[Dict[str, Any]] = None
    guardrail_preset_ids: Optional[List[str]] = None
    grants: Optional[List[Dict[str, str]]] = None


class CopilotConnectionRequest(BaseModel):
    name: str
    description: Optional[str] = None
    credential_visibility: str = "use_only"
    allow_user_self_manage: bool = False
    config_json: Dict[str, Any] = Field(default_factory=dict)
    secret_json: Dict[str, Any] = Field(default_factory=dict)


class CopilotConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    credential_visibility: Optional[str] = None
    allow_user_self_manage: Optional[bool] = None
    config_json: Optional[Dict[str, Any]] = None
    secret_json: Optional[Dict[str, Any]] = None


class CopilotConnectionGrantRequest(BaseModel):
    scope_type: str
    scope_id: str
    can_manage: bool = False


class CopilotAgentGrantRequest(BaseModel):
    scope_type: str
    scope_id: str


class GuardrailPresetRequest(BaseModel):
    code: str
    name: str
    preset_json: Dict[str, Any] = Field(default_factory=dict)


class GuardrailAssignRequest(BaseModel):
    preset_id: str
    scope_type: str
    scope_id: str


class GuardrailPatternCreateRequest(BaseModel):
    guard_type: str
    pattern_name: str
    pattern_regex: str
    pattern_type: str
    action: Optional[str] = None
    enabled: bool = True


class GuardrailPatternUpdateRequest(BaseModel):
    pattern_name: Optional[str] = None
    pattern_regex: Optional[str] = None
    pattern_type: Optional[str] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None


class ModelGrantRequest(BaseModel):
    domain: str
    model_name: str
    scope_type: str
    scope_id: str
    access_mode: str = "allow"


class FeatureEntitlementRequest(BaseModel):
    domain: str
    feature_code: str
    scope_type: str
    scope_id: str
    enabled: bool = True
    config_json: Dict[str, Any] = Field(default_factory=dict)


class CopilotMarketplaceRequest(BaseModel):
    entity_type: str
    entity_id: str
    title: str
    description: Optional[str] = None
    is_published: bool = True
    is_featured: bool = False
    is_verified: bool = False
    pricing_model: str = "free"
    version: str = "1.0.0"
    author: Optional[str] = None
    installation_count: int = 0
    rating_avg: float = 0
    rating_count: int = 0
    grants: List[Dict[str, str]] = Field(default_factory=list)


class CopilotMarketplaceUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_published: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_verified: Optional[bool] = None
    pricing_model: Optional[str] = None
    version: Optional[str] = None
    author: Optional[str] = None
    installation_count: Optional[int] = None
    rating_avg: Optional[float] = None
    rating_count: Optional[int] = None
    grants: Optional[List[Dict[str, str]]] = None


class CopilotMarketplaceGrantRequest(BaseModel):
    scope_type: str
    scope_id: str


@router.get("/me/context")
async def get_me_context():
    return {
        "account_id": get_current_account_id(),
        "is_super_admin": is_super_admin(),
        "auth_provider": get_current_auth_provider(),
        "roles": get_current_roles(),
        "scopes": get_current_scopes(),
        "product_domains_allowed": get_current_product_domains(),
    }


@router.post("/accounts")
async def create_account(req: AccountCreateRequest, _: None = Depends(require_super_admin)):
    db = await _db()

    existing = await db.alchemi_accounttable.find_first(where={"account_name": req.account_name})
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists")

    if req.domain:
        existing_domain = await db.alchemi_accounttable.find_first(where={"domain": req.domain})
        if existing_domain:
            raise HTTPException(status_code=409, detail="Domain already assigned to another account")

    account_id = str(uuid.uuid4())
    await db.alchemi_accounttable.create(
        data={
            "account_id": account_id,
            "account_name": req.account_name,
            "account_alias": req.account_alias,
            "domain": req.domain,
            "max_budget": req.max_budget,
            "metadata": Json(req.metadata),
            "status": "active",
            "created_by": "super_admin",
        }
    )

    if req.admin_email:
        await db.alchemi_accountadmintable.create(
            data={
                "id": str(uuid.uuid4()),
                "account_id": account_id,
                "user_email": req.admin_email,
                "role": "account_admin",
                "created_by": "super_admin",
            }
        )

        existing_user = await db.litellm_usertable.find_first(where={"user_email": req.admin_email})
        user_payload: Dict[str, Any] = {"account_id": account_id, "user_role": "proxy_admin"}
        if req.admin_password:
            user_payload["password"] = _hash_password(req.admin_password)
        if existing_user:
            await db.litellm_usertable.update(where={"user_id": _row_get(existing_user, "user_id")}, data=user_payload)
        else:
            user_payload.update({"user_id": str(uuid.uuid4()), "user_email": req.admin_email})
            await db.litellm_usertable.create(data=user_payload)

        await _audit_event(
            db=db,
            action="upsert",
            table_name="Alchemi_AccountAdminTable",
            object_id=account_id,
            before_value=None,
            updated_values={"account_id": account_id, "user_email": req.admin_email, "role": "account_admin"},
            domain="iam",
            changed_by="super_admin",
        )

    await _ensure_default_copilot_global_org(db, account_id, "super_admin")
    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_AccountTable",
        object_id=account_id,
        before_value=None,
        updated_values={
            "account_id": account_id,
            "account_name": req.account_name,
            "account_alias": req.account_alias,
            "domain": req.domain,
            "max_budget": req.max_budget,
            "metadata": req.metadata,
        },
        domain="iam",
        changed_by="super_admin",
    )

    item = await _fetch_account_bundle(db, account_id)
    return {"account_id": account_id, "status": "created", "item": item}


@router.get("/accounts")
async def list_accounts(status: Optional[str] = None, _: None = Depends(require_super_admin)):
    db = await _db()
    where: Dict[str, Any] = {}
    if status:
        where["status"] = status
    accounts = await db.alchemi_accounttable.find_many(where=where, order={"created_at": "desc"})
    items: List[Dict[str, Any]] = []
    for account in accounts:
        account_id = str(_row_get(account, "account_id"))
        bundle = await _fetch_account_bundle(db, account_id)
        if bundle:
            items.append(bundle)
    return {"items": items}


@router.get("/accounts/{account_id}")
async def get_account(account_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    item = await _fetch_account_bundle(db, account_id)
    if not item:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"item": item}


@router.patch("/accounts/{account_id}")
async def update_account(account_id: str, req: AccountUpdateRequest, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data: Dict[str, Any] = {}
    if req.account_name is not None:
        update_data["account_name"] = req.account_name
    if req.account_alias is not None:
        update_data["account_alias"] = req.account_alias
    if req.domain is not None:
        if req.domain:
            existing_domain = await db.alchemi_accounttable.find_first(where={"domain": req.domain})
            if existing_domain and str(_row_get(existing_domain, "account_id")) != account_id:
                raise HTTPException(status_code=409, detail="Domain already assigned to another account")
        update_data["domain"] = req.domain
    if req.status is not None:
        if req.status not in {"active", "suspended"}:
            raise HTTPException(status_code=400, detail="status must be active or suspended")
        update_data["status"] = req.status
    if req.max_budget is not None:
        if req.max_budget < 0:
            raise HTTPException(status_code=400, detail="max_budget must be >= 0")
        update_data["max_budget"] = req.max_budget
    if req.metadata is not None:
        update_data["metadata"] = Json(req.metadata)

    if not update_data:
        raise HTTPException(status_code=400, detail="No update fields provided")

    updated = await db.alchemi_accounttable.update(where={"account_id": account_id}, data=update_data)
    await _audit_event(
        db=db,
        action="update",
        table_name="Alchemi_AccountTable",
        object_id=account_id,
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values=_to_jsonable(_record_to_dict(updated)),
        domain="iam",
        changed_by="super_admin",
    )
    item = await _fetch_account_bundle(db, account_id)
    return {"item": item}


@router.post("/accounts/{account_id}/status")
async def set_account_status(account_id: str, req: AccountStatusRequest, _: None = Depends(require_super_admin)):
    req.status = (req.status or "").strip().lower()
    if req.status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="status must be active or suspended")
    return await update_account(account_id, AccountUpdateRequest(status=req.status), _)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    hard_delete: bool = False,
    confirm_name: Optional[str] = None,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")

    if not hard_delete:
        updated = await db.alchemi_accounttable.update(where={"account_id": account_id}, data={"status": "suspended"})
        await _audit_event(
            db=db,
            action="update",
            table_name="Alchemi_AccountTable",
            object_id=account_id,
            before_value=_to_jsonable(_record_to_dict(existing)),
            updated_values=_to_jsonable(_record_to_dict(updated)),
            domain="iam",
            changed_by="super_admin",
        )
        return {"status": "suspended", "account_id": account_id}

    if confirm_name != _row_get(existing, "account_name"):
        raise HTTPException(status_code=400, detail="confirm_name must match account_name for hard delete")

    # Delete account-scoped data. Some control-plane tables are raw SQL tables without FK-to-account.
    tables = [
        "Alchemi_CopilotUsageLedgerTable",
        "Alchemi_CopilotMarketplaceTable",
        "Alchemi_FeatureEntitlementTable",
        "Alchemi_ModelGrantTable",
        "Alchemi_CopilotAgentGrantTable",
        "Alchemi_CopilotAgentTable",
        "Alchemi_CopilotGuardrailAssignmentTable",
        "Alchemi_CopilotGuardrailPresetTable",
        "Alchemi_CopilotConnectionGrantTable",
        "Alchemi_CopilotConnectionTable",
        "Alchemi_CopilotBudgetCycleTable",
        "Alchemi_CopilotBudgetOverrideTable",
        "Alchemi_CopilotBudgetAllocationTable",
        "Alchemi_CopilotBudgetPlanTable",
        "Alchemi_AccountAllocationTable",
        "Alchemi_CopilotTeamMembershipTable",
        "Alchemi_CopilotUserTable",
        "Alchemi_CopilotTeamTable",
        "Alchemi_CopilotOrgTable",
        "Alchemi_ConsoleTeamMembershipTable",
        "Alchemi_ConsoleUserTable",
        "Alchemi_ConsoleTeamTable",
        "Alchemi_ConsoleOrgTable",
        "Alchemi_AccountSSOConfig",
        "Alchemi_AccountAdminTable",
    ]
    for table in tables:
        try:
            await db.query_raw(f'DELETE FROM "{table}" WHERE account_id = $1', account_id)
        except Exception:
            continue

    await db.alchemi_accounttable.delete(where={"account_id": account_id})
    await _audit_event(
        db=db,
        action="delete",
        table_name="Alchemi_AccountTable",
        object_id=account_id,
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values={"hard_delete": True},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "deleted", "account_id": account_id}


@router.get("/accounts/{account_id}/admins")
async def list_account_admins(account_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    rows = await db.alchemi_accountadmintable.find_many(where={"account_id": account_id}, order={"created_at": "desc"})
    return {"items": [_to_jsonable(_record_to_dict(r) or {}) for r in rows]}


@router.post("/accounts/{account_id}/admins")
async def add_account_admin(account_id: str, req: AccountAdminRequest, _: None = Depends(require_super_admin)):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    existing = await db.alchemi_accountadmintable.find_first(where={"account_id": account_id, "user_email": req.user_email})
    await db.alchemi_accountadmintable.upsert(
        where={"account_id_user_email": {"account_id": account_id, "user_email": req.user_email}},
        data={
            "create": {
                "id": str(uuid.uuid4()),
                "account_id": account_id,
                "user_email": req.user_email,
                "role": req.role,
                "created_by": "super_admin",
            },
            "update": {"role": req.role},
        },
    )
    existing_user = await db.litellm_usertable.find_first(where={"user_email": req.user_email})
    user_payload: Dict[str, Any] = {"account_id": account_id, "user_role": "proxy_admin"}
    if req.password:
        user_payload["password"] = _hash_password(req.password)
    if existing_user:
        await db.litellm_usertable.update(where={"user_id": _row_get(existing_user, "user_id")}, data=user_payload)
    else:
        user_payload.update({"user_id": str(uuid.uuid4()), "user_email": req.user_email})
        await db.litellm_usertable.create(data=user_payload)

    await _audit_event(
        db=db,
        action="upsert",
        table_name="Alchemi_AccountAdminTable",
        object_id=account_id,
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values={"account_id": account_id, "user_email": req.user_email, "role": req.role},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok"}


@router.patch("/accounts/{account_id}/admins/{email}")
async def update_account_admin(
    account_id: str,
    email: str,
    req: AccountAdminUpdateRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    existing = await db.alchemi_accountadmintable.find_first(where={"account_id": account_id, "user_email": email})
    if not existing:
        raise HTTPException(status_code=404, detail="Admin not found")

    target_email = req.new_email or email
    if req.new_email and req.new_email != email:
        duplicate = await db.alchemi_accountadmintable.find_first(where={"account_id": account_id, "user_email": req.new_email})
        if duplicate:
            raise HTTPException(status_code=409, detail="new_email already exists for this account")

    admin_update_data: Dict[str, Any] = {}
    if req.new_email and req.new_email != email:
        admin_update_data["user_email"] = req.new_email
    if req.role:
        admin_update_data["role"] = req.role
    if admin_update_data:
        await db.alchemi_accountadmintable.update(where={"id": _row_get(existing, "id")}, data=admin_update_data)

    user = await db.litellm_usertable.find_first(where={"user_email": email})
    if user:
        user_update_data: Dict[str, Any] = {"account_id": account_id, "user_role": "proxy_admin"}
        if req.new_email and req.new_email != email:
            user_update_data["user_email"] = req.new_email
        if req.password:
            user_update_data["password"] = _hash_password(req.password)
        await db.litellm_usertable.update(where={"user_id": _row_get(user, "user_id")}, data=user_update_data)
    elif req.password or req.new_email:
        create_data: Dict[str, Any] = {
            "user_id": str(uuid.uuid4()),
            "user_email": target_email,
            "user_role": "proxy_admin",
            "account_id": account_id,
        }
        if req.password:
            create_data["password"] = _hash_password(req.password)
        await db.litellm_usertable.create(data=create_data)

    updated = await db.alchemi_accountadmintable.find_first(where={"account_id": account_id, "user_email": target_email})
    await _audit_event(
        db=db,
        action="update",
        table_name="Alchemi_AccountAdminTable",
        object_id=str(_row_get(existing, "id")),
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values=_to_jsonable(_record_to_dict(updated)),
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "item": _to_jsonable(_record_to_dict(updated) or {})}


@router.delete("/accounts/{account_id}/admins/{email}")
async def delete_account_admin(account_id: str, email: str, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.alchemi_accountadmintable.find_first(where={"account_id": account_id, "user_email": email})
    if not existing:
        raise HTTPException(status_code=404, detail="Admin not found")
    await db.alchemi_accountadmintable.delete(where={"id": _row_get(existing, "id")})
    await _audit_event(
        db=db,
        action="delete",
        table_name="Alchemi_AccountAdminTable",
        object_id=str(_row_get(existing, "id")),
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values={"account_id": account_id, "user_email": email},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok"}


@router.post("/accounts/{account_id}/sso")
async def set_account_sso(account_id: str, req: AccountSsoRequest, _: None = Depends(require_super_admin)):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    existing = await db.alchemi_accountssoconfig.find_first(where={"account_id": account_id})
    merged_sso_settings = _merge_sso_settings(
        _decode_json_field(_row_get(existing, "sso_settings"), {}) if existing else {},
        req.sso_settings,
    )
    await db.alchemi_accountssoconfig.upsert(
        where={"account_id": account_id},
        data={
            "create": {
                "id": str(uuid.uuid4()),
                "account_id": account_id,
                "sso_provider": req.sso_provider,
                "enabled": req.enabled,
                "sso_settings": Json(merged_sso_settings),
            },
            "update": {
                "sso_provider": req.sso_provider,
                "enabled": req.enabled,
                "sso_settings": Json(merged_sso_settings),
            },
        },
    )
    await _audit_event(
        db=db,
        action="upsert",
        table_name="Alchemi_AccountSSOConfig",
        object_id=account_id,
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values={"account_id": account_id, "sso_provider": req.sso_provider, "enabled": req.enabled, "sso_settings": _mask_sso_settings(merged_sso_settings)},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok"}


@router.get("/accounts/{account_id}/sso")
async def get_account_sso(account_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    row = await db.alchemi_accountssoconfig.find_first(where={"account_id": account_id})
    if not row:
        return {"id": None, "account_id": account_id, "sso_provider": None, "enabled": False, "sso_settings": {}}
    item = _to_jsonable(_record_to_dict(row) or {})
    item["sso_settings"] = _mask_sso_settings(_decode_json_field(item.get("sso_settings"), {}))
    return item


@router.delete("/accounts/{account_id}/sso")
async def delete_account_sso(account_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.alchemi_accountssoconfig.find_first(where={"account_id": account_id})
    if not existing:
        return {"status": "ok", "deleted": False}
    await db.alchemi_accountssoconfig.delete(where={"account_id": account_id})
    await _audit_event(
        db=db,
        action="delete",
        table_name="Alchemi_AccountSSOConfig",
        object_id=account_id,
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values={"account_id": account_id},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "deleted": True}


@router.put("/accounts/{account_id}/feature-pack")
async def set_account_feature_pack(account_id: str, req: AccountFeaturePackRequest, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(existing, "metadata"), {})
    metadata["feature_pack"] = {"features": req.features, "config": req.config}
    updated = await db.alchemi_accounttable.update(where={"account_id": account_id}, data={"metadata": Json(metadata)})
    await _audit_event(
        db=db,
        action="update",
        table_name="Alchemi_AccountTable",
        object_id=account_id,
        before_value={"feature_pack": _decode_json_field(_row_get(existing, "metadata"), {}).get("feature_pack")},
        updated_values={"feature_pack": metadata["feature_pack"]},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "feature_pack": _decode_json_field(_row_get(updated, "metadata"), {}).get("feature_pack")}


@router.get("/accounts/{account_id}/feature-pack")
async def get_account_feature_pack(account_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(existing, "metadata"), {})
    return {"feature_pack": metadata.get("feature_pack", {"features": [], "config": {}})}


@router.put("/accounts/{account_id}/console-model-policy")
async def set_account_console_model_policy(
    account_id: str,
    req: AccountConsoleModelPolicyRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(existing, "metadata"), {})
    metadata["console_model_policy"] = {"allow_models": req.allow_models, "deny_models": req.deny_models}
    updated = await db.alchemi_accounttable.update(where={"account_id": account_id}, data={"metadata": Json(metadata)})
    await _audit_event(
        db=db,
        action="update",
        table_name="Alchemi_AccountTable",
        object_id=account_id,
        before_value={"console_model_policy": _decode_json_field(_row_get(existing, "metadata"), {}).get("console_model_policy")},
        updated_values={"console_model_policy": metadata["console_model_policy"]},
        domain="console",
        changed_by="super_admin",
    )
    return {"status": "ok", "console_model_policy": _decode_json_field(_row_get(updated, "metadata"), {}).get("console_model_policy")}


@router.get("/accounts/{account_id}/console-model-policy")
async def get_account_console_model_policy(account_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(existing, "metadata"), {})
    return {"console_model_policy": metadata.get("console_model_policy", {"allow_models": [], "deny_models": []})}


@router.get("/super/models")
async def list_super_models(include_inactive: bool = True, _: None = Depends(require_super_admin)):
    db = await _db()
    rows = await db.query_raw(
        'SELECT model_id, model_name, litellm_params, model_info, created_at, updated_at, created_by, updated_by '
        'FROM "LiteLLM_ProxyModelTable" '
        'WHERE account_id IS NULL '
        'ORDER BY model_name ASC'
    )
    items: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        model_info = _decode_json_field(item.get("model_info"), {})
        litellm_params = _decode_json_field(item.get("litellm_params"), {})
        is_active = bool(model_info.get("is_active", True))
        if not include_inactive and not is_active:
            continue
        item["model_info"] = model_info
        item["litellm_params"] = litellm_params
        item["is_active"] = is_active
        item["display_name"] = model_info.get("display_name") or item.get("model_name")
        item["provider_id"] = model_info.get("provider_id")
        item["deployment_name"] = model_info.get("deployment_name")
        item["capability"] = model_info.get("capability")
        item["sort_order"] = model_info.get("sort_order")
        item["input_cost_per_million"] = (
            float(model_info["input_cost_per_token"]) * 1_000_000.0
            if model_info.get("input_cost_per_token") is not None
            else None
        )
        item["output_cost_per_million"] = (
            float(model_info["output_cost_per_token"]) * 1_000_000.0
            if model_info.get("output_cost_per_token") is not None
            else None
        )
        item["api_base_env_var"] = model_info.get("api_base_env_var")
        item["api_key_env_var"] = model_info.get("api_key_env_var")
        items.append(_to_jsonable(item))

    def _sort_order(item: Dict[str, Any]) -> int:
        raw = item.get("sort_order")
        try:
            return int(raw)
        except Exception:
            return 9999

    items.sort(
        key=lambda x: (
            _sort_order(x),
            str(x.get("display_name") or x.get("model_name") or ""),
        )
    )
    return {"items": items}


@router.post("/super/models/upsert")
async def upsert_super_model(req: SuperModelUpsertRequest, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = None
    if req.model_id:
        existing = await db.litellm_proxymodeltable.find_unique(where={"model_id": req.model_id})
    if existing is None:
        existing = await db.litellm_proxymodeltable.find_first(
            where={"model_name": req.model_name, "account_id": None}
        )

    payload = _build_super_model_payload(req, existing_model_id=_row_get(existing, "model_id"))
    before_value = _to_jsonable(_record_to_dict(existing))

    if existing:
        updated = await db.litellm_proxymodeltable.update(
            where={"model_id": payload["model_id"]},
            data={
                "model_name": req.model_name,
                "litellm_params": Json(payload["litellm_params"]),
                "model_info": Json(payload["model_info"]),
                "updated_by": "super_admin",
            },
        )
        action = "update"
    else:
        updated = await db.litellm_proxymodeltable.create(
            data={
                "model_id": payload["model_id"],
                "model_name": req.model_name,
                "litellm_params": Json(payload["litellm_params"]),
                "model_info": Json(payload["model_info"]),
                "created_by": "super_admin",
                "updated_by": "super_admin",
                "account_id": None,
            }
        )
        action = "create"

    await _audit_event(
        db=db,
        action=action,
        table_name="LiteLLM_ProxyModelTable",
        object_id=payload["model_id"],
        before_value=before_value,
        updated_values=_to_jsonable(_record_to_dict(updated)),
        domain="console",
        changed_by="super_admin",
    )
    await _refresh_proxy_deployments()

    return {"status": "ok", "item": _to_jsonable(_record_to_dict(updated))}


@router.delete("/super/models/{model_id}")
async def delete_super_model(model_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.litellm_proxymodeltable.find_unique(where={"model_id": model_id})
    if not existing or _row_get(existing, "account_id") is not None:
        raise HTTPException(status_code=404, detail="Model not found")

    await db.litellm_proxymodeltable.delete(where={"model_id": model_id})
    await _audit_event(
        db=db,
        action="delete",
        table_name="LiteLLM_ProxyModelTable",
        object_id=model_id,
        before_value=_to_jsonable(_record_to_dict(existing)),
        updated_values={"model_id": model_id},
        domain="console",
        changed_by="super_admin",
    )
    await _refresh_proxy_deployments()
    return {"status": "ok", "deleted": True}


@router.get("/auth/zitadel/status")
async def get_zitadel_status():
    settings = get_zitadel_settings()
    return {
        "enabled": bool(get_current_auth_provider() and get_current_auth_provider().startswith("zitadel")),
        "zitadel_configured": bool(settings.enabled),
        "issuer": settings.issuer,
        "auth_provider": get_current_auth_provider(),
        "account_id": get_current_account_id(),
        "roles": get_current_roles(),
        "scopes": get_current_scopes(),
        "product_domains_allowed": get_current_product_domains(),
    }


@router.get("/super/zitadel/onboarding-defaults")
async def get_super_zitadel_onboarding_defaults(_: None = Depends(require_super_admin)):
    db = await _db()
    row = await db.litellm_config.find_unique(where={"param_name": ZITADEL_ONBOARDING_DEFAULTS_PARAM_NAME})
    raw = _decode_json_field(_row_get(row, "param_value"), {})
    item = _normalize_zitadel_onboarding_defaults(raw)
    return {"item": item}


@router.put("/super/zitadel/onboarding-defaults")
async def set_super_zitadel_onboarding_defaults(
    req: ZitadelOnboardingDefaultsRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    existing = await db.litellm_config.find_unique(where={"param_name": ZITADEL_ONBOARDING_DEFAULTS_PARAM_NAME})
    before_value = _normalize_zitadel_onboarding_defaults(_decode_json_field(_row_get(existing, "param_value"), {}))
    item = _normalize_zitadel_onboarding_defaults(req.model_dump())

    if existing:
        await db.litellm_config.update(
            where={"param_name": ZITADEL_ONBOARDING_DEFAULTS_PARAM_NAME},
            data={"param_value": Json(item), "account_id": None},
        )
    else:
        await db.litellm_config.create(
            data={
                "param_name": ZITADEL_ONBOARDING_DEFAULTS_PARAM_NAME,
                "param_value": Json(item),
                "account_id": None,
            }
        )

    await _audit_event(
        db=db,
        action="upsert",
        table_name="LiteLLM_Config",
        object_id=ZITADEL_ONBOARDING_DEFAULTS_PARAM_NAME,
        before_value={"value": before_value},
        updated_values={"value": item},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "item": item}


@router.get("/accounts/{account_id}/zitadel/config")
async def get_account_zitadel_config(account_id: str, _: None = Depends(require_super_admin)):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(existing, "metadata"), {})
    return {"zitadel_config": metadata.get("zitadel", {})}


@router.put("/accounts/{account_id}/zitadel/config")
async def set_account_zitadel_config(
    account_id: str,
    req: ZitadelAccountConfigRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    existing = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Account not found")

    metadata = _decode_json_field(_row_get(existing, "metadata"), {})
    previous = metadata.get("zitadel", {})
    metadata["zitadel"] = {
        "enabled": req.enabled,
        "issuer": req.issuer,
        "audience": req.audience,
        "project_id": req.project_id,
        "organization_id": req.organization_id,
        "role_mappings": req.role_mappings,
        "account_id_claim": req.account_id_claim,
        "product_domains_claim": req.product_domains_claim,
    }
    await db.alchemi_accounttable.update(where={"account_id": account_id}, data={"metadata": Json(metadata)})
    await _audit_event(
        db=db,
        action="update",
        table_name="Alchemi_AccountTable",
        object_id=account_id,
        before_value={"zitadel": previous},
        updated_values={"zitadel": metadata["zitadel"]},
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "zitadel_config": metadata["zitadel"]}


def _resolved_zitadel_config(account_metadata: Dict[str, Any], req_project_id: Optional[str], req_org_id: Optional[str]) -> Dict[str, Any]:
    zitadel_cfg = (account_metadata or {}).get("zitadel", {}) or {}
    return {
        "project_id": req_project_id or zitadel_cfg.get("project_id"),
        "organization_id": req_org_id or zitadel_cfg.get("organization_id"),
    }


def _normalize_role_prefix(role_prefix: Optional[str]) -> str:
    prefix = (role_prefix or "").strip()
    return prefix


def _prefixed_role_definitions(role_prefix: Optional[str]) -> List[Dict[str, Optional[str]]]:
    prefix = _normalize_role_prefix(role_prefix)
    items: List[Dict[str, Optional[str]]] = []
    for role in DEFAULT_ZITADEL_ROLE_DEFINITIONS:
        key = str(role.get("key") or "").strip()
        if not key:
            continue
        items.append(
            {
                "key": f"{prefix}{key}" if prefix else key,
                "display_name": str(role.get("display_name") or key),
                "group": role.get("group"),
                "base_key": key,
            }
        )
    return items


def _default_role_mappings(role_prefix: Optional[str]) -> Dict[str, str]:
    prefix = _normalize_role_prefix(role_prefix)
    if not prefix:
        return dict(DEFAULT_ZITADEL_ROLE_MAPPINGS)
    return {k: f"{prefix}{v}" for k, v in DEFAULT_ZITADEL_ROLE_MAPPINGS.items()}


def _normalize_zitadel_onboarding_defaults(value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    project_id = str(raw.get("project_id") or "").strip()
    organization_id = str(raw.get("organization_id") or "").strip()
    role_prefix = str(raw.get("role_prefix") or "").strip()
    resolve_users = raw.get("resolve_user_ids_from_zitadel")
    if isinstance(resolve_users, bool):
        resolve_user_ids = resolve_users
    else:
        resolve_user_ids = True
    return {
        "project_id": project_id or None,
        "organization_id": organization_id or None,
        "role_prefix": role_prefix or None,
        "resolve_user_ids_from_zitadel": resolve_user_ids,
    }


def _role_keys_for_admin_row(
    admin_role: Optional[str],
    role_mappings: Dict[str, str],
    default_role_keys: List[str],
) -> List[str]:
    role = (admin_role or "").strip()
    keys: List[str] = []
    if role and role_mappings.get(role):
        keys.append(str(role_mappings[role]))
    elif role_mappings.get("account_admin"):
        keys.append(str(role_mappings["account_admin"]))
    elif role:
        keys.append(role)

    keys.extend([k for k in default_role_keys if k])

    deduped: List[str] = []
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _is_zitadel_already_exists_error(error: Exception) -> bool:
    text = str(error).lower()
    markers = [
        "already exists",
        "alreadyexists",
        "already_exists",
        '"code": 6',
        "'code': 6",
        "status_code=409",
    ]
    return any(marker in text for marker in markers)


def _split_by_status(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"created": 0, "exists": 0, "skipped": 0, "failed": 0}
    for item in items:
        status = str(item.get("status") or "").strip().lower()
        if status in counts:
            counts[status] += 1
        else:
            counts["failed"] += 1
    return counts


async def _sync_zitadel_project_roles(
    *,
    client: ZitadelManagementClient,
    project_id: str,
    role_prefix: Optional[str],
    skip_existing: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    roles = _prefixed_role_definitions(role_prefix)
    results: List[Dict[str, Any]] = []
    for role in roles:
        key = str(role.get("key") or "")
        payload = {"key": key, "display_name": role.get("display_name"), "group": role.get("group")}
        if dry_run:
            results.append({"key": key, "status": "skipped", "reason": "dry_run", "request": payload})
            continue
        try:
            response = await client.add_project_role(
                project_id=project_id,
                key=key,
                display_name=str(role.get("display_name") or key),
                group=str(role.get("group")) if role.get("group") else None,
            )
            results.append({"key": key, "status": "created", "response": _to_jsonable(response)})
        except Exception as exc:
            if skip_existing and _is_zitadel_already_exists_error(exc):
                results.append({"key": key, "status": "exists", "message": str(exc)})
            else:
                results.append({"key": key, "status": "failed", "message": str(exc)})
    return {"roles": roles, "results": results, "summary": _split_by_status(results)}


async def _sync_zitadel_account_admin_grants(
    *,
    db: Any,
    account_id: str,
    project_id: str,
    organization_id: Optional[str],
    role_mappings: Dict[str, str],
    user_id_by_email: Dict[str, str],
    resolve_user_ids_from_zitadel: bool,
    default_role_keys: List[str],
    skip_existing: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    rows = await db.alchemi_accountadmintable.find_many(where={"account_id": account_id}, order={"created_at": "asc"})
    admins = [_to_jsonable(_record_to_dict(row) or {}) for row in rows]

    lookup: Dict[str, str] = {}
    for key, value in (user_id_by_email or {}).items():
        k = str(key or "").strip().lower()
        v = str(value or "").strip()
        if k and v:
            lookup[k] = v

    client = ZitadelManagementClient()
    if not dry_run and not client.is_configured():
        raise HTTPException(status_code=400, detail="Zitadel management client is not configured")
    resolved_user_ids: Dict[str, str] = {}
    unresolved_admins: List[Dict[str, Any]] = []
    grants: List[Dict[str, Any]] = []

    for admin in admins:
        email = str(admin.get("user_email") or "").strip().lower()
        admin_role = str(admin.get("role") or "account_admin")
        role_keys = _role_keys_for_admin_row(admin_role, role_mappings, default_role_keys)
        if not role_keys:
            unresolved_admins.append({"email": email, "role": admin_role, "reason": "no_role_keys"})
            continue

        user_id = lookup.get(email)
        if not user_id and resolve_user_ids_from_zitadel and email and client.is_configured():
            try:
                resolved = await client.find_user_id_by_email(email=email)
                if resolved:
                    user_id = resolved
                    lookup[email] = resolved
                    resolved_user_ids[email] = resolved
            except Exception:
                user_id = None

        if not user_id:
            unresolved_admins.append({"email": email, "role": admin_role, "reason": "user_id_not_found", "role_keys": role_keys})
            continue

        if dry_run:
            grants.append(
                {
                    "email": email,
                    "user_id": user_id,
                    "role": admin_role,
                    "role_keys": role_keys,
                    "status": "skipped",
                    "reason": "dry_run",
                }
            )
            continue

        try:
            result = await client.add_user_grant(
                user_id=user_id,
                project_id=project_id,
                role_keys=role_keys,
                organization_id=organization_id,
            )
            grants.append(
                {
                    "email": email,
                    "user_id": user_id,
                    "role": admin_role,
                    "role_keys": role_keys,
                    "status": "created",
                    "result": _to_jsonable(result),
                }
            )
        except Exception as exc:
            if skip_existing and _is_zitadel_already_exists_error(exc):
                grants.append(
                    {
                        "email": email,
                        "user_id": user_id,
                        "role": admin_role,
                        "role_keys": role_keys,
                        "status": "exists",
                        "message": str(exc),
                    }
                )
            else:
                grants.append(
                    {
                        "email": email,
                        "user_id": user_id,
                        "role": admin_role,
                        "role_keys": role_keys,
                        "status": "failed",
                        "message": str(exc),
                    }
                )

    return {
        "admins_total": len(admins),
        "grants": grants,
        "grants_summary": _split_by_status(grants),
        "unresolved_admins": unresolved_admins,
        "resolved_user_ids": resolved_user_ids,
    }


@router.post("/accounts/{account_id}/zitadel/provision/user-grant")
async def provision_account_user_grant(
    account_id: str,
    req: ZitadelProvisionGrantRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(account, "metadata"), {})
    cfg = _resolved_zitadel_config(metadata, req.project_id, req.organization_id)
    if not cfg["project_id"]:
        raise HTTPException(status_code=400, detail="project_id missing in request and account zitadel config")
    if not req.role_keys:
        raise HTTPException(status_code=400, detail="role_keys cannot be empty")

    client = ZitadelManagementClient()
    try:
        result = await client.add_user_grant(
            user_id=req.user_id,
            project_id=str(cfg["project_id"]),
            role_keys=req.role_keys,
            organization_id=str(cfg["organization_id"]) if cfg["organization_id"] else None,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to provision Zitadel user grant: {e}") from e

    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_ZitadelProvision",
        object_id=account_id,
        before_value=None,
        updated_values={
            "operation": "user_grant",
            "user_id": req.user_id,
            "project_id": cfg["project_id"],
            "organization_id": cfg["organization_id"],
            "role_keys": req.role_keys,
            "result": _to_jsonable(result),
        },
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "result": result}


@router.post("/accounts/{account_id}/zitadel/provision/project-role")
async def provision_account_project_role(
    account_id: str,
    req: ZitadelProjectRoleRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(account, "metadata"), {})
    cfg = _resolved_zitadel_config(metadata, req.project_id, None)
    if not cfg["project_id"]:
        raise HTTPException(status_code=400, detail="project_id missing in request and account zitadel config")

    client = ZitadelManagementClient()
    try:
        result = await client.add_project_role(
            project_id=str(cfg["project_id"]),
            key=req.key,
            display_name=req.display_name,
            group=req.group,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to provision Zitadel project role: {e}") from e

    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_ZitadelProvision",
        object_id=account_id,
        before_value=None,
        updated_values={
            "operation": "project_role",
            "project_id": cfg["project_id"],
            "key": req.key,
            "display_name": req.display_name,
            "group": req.group,
            "result": _to_jsonable(result),
        },
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "result": result}


@router.get("/accounts/{account_id}/zitadel/provision/plan")
async def get_account_zitadel_provision_plan(
    account_id: str,
    role_prefix: Optional[str] = None,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(account, "metadata"), {})
    cfg = _resolved_zitadel_config(metadata, None, None)
    zitadel_cfg = metadata.get("zitadel", {}) or {}
    prefix = _normalize_role_prefix(role_prefix)
    mappings = dict(zitadel_cfg.get("role_mappings") or {})
    if not mappings:
        mappings = _default_role_mappings(prefix)

    admins = await db.alchemi_accountadmintable.find_many(where={"account_id": account_id}, order={"created_at": "asc"})
    admin_items = []
    for row in admins:
        item = _to_jsonable(_record_to_dict(row) or {})
        admin_role = str(item.get("role") or "account_admin")
        item["resolved_role_keys"] = _role_keys_for_admin_row(admin_role, mappings, [])
        admin_items.append(item)

    return {
        "account_id": account_id,
        "zitadel_config": {
            "enabled": bool(zitadel_cfg.get("enabled", True)),
            "issuer": zitadel_cfg.get("issuer"),
            "audience": zitadel_cfg.get("audience"),
            "project_id": cfg.get("project_id"),
            "organization_id": cfg.get("organization_id"),
            "account_id_claim": zitadel_cfg.get("account_id_claim"),
            "product_domains_claim": zitadel_cfg.get("product_domains_claim"),
            "role_mappings": mappings,
        },
        "standard_roles": _prefixed_role_definitions(prefix),
        "account_admins": admin_items,
    }


@router.post("/accounts/{account_id}/zitadel/provision/sync-roles")
async def sync_account_zitadel_project_roles(
    account_id: str,
    req: ZitadelSyncRolesRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(account, "metadata"), {})
    cfg = _resolved_zitadel_config(metadata, req.project_id, None)
    if not cfg["project_id"]:
        raise HTTPException(status_code=400, detail="project_id missing in request and account zitadel config")

    client = ZitadelManagementClient()
    if not client.is_configured():
        raise HTTPException(status_code=400, detail="Zitadel management client is not configured")

    result = await _sync_zitadel_project_roles(
        client=client,
        project_id=str(cfg["project_id"]),
        role_prefix=req.role_prefix,
        skip_existing=req.skip_existing,
        dry_run=False,
    )

    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_ZitadelProvision",
        object_id=account_id,
        before_value=None,
        updated_values={
            "operation": "sync_roles",
            "project_id": cfg["project_id"],
            "role_prefix": req.role_prefix,
            "summary": result.get("summary"),
        },
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "result": result}


@router.post("/accounts/{account_id}/zitadel/provision/sync-admin-grants")
async def sync_account_zitadel_admin_grants(
    account_id: str,
    req: ZitadelSyncAdminGrantsRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    metadata = _decode_json_field(_row_get(account, "metadata"), {})
    cfg = _resolved_zitadel_config(metadata, req.project_id, req.organization_id)
    if not cfg["project_id"]:
        raise HTTPException(status_code=400, detail="project_id missing in request and account zitadel config")

    prefix = _normalize_role_prefix(req.role_prefix)
    mappings = dict((metadata.get("zitadel", {}) or {}).get("role_mappings") or {})
    if not mappings:
        mappings = _default_role_mappings(prefix)

    result = await _sync_zitadel_account_admin_grants(
        db=db,
        account_id=account_id,
        project_id=str(cfg["project_id"]),
        organization_id=str(cfg["organization_id"]) if cfg["organization_id"] else None,
        role_mappings=mappings,
        user_id_by_email=req.user_id_by_email,
        resolve_user_ids_from_zitadel=req.resolve_user_ids_from_zitadel,
        default_role_keys=req.default_role_keys,
        skip_existing=req.skip_existing,
        dry_run=False,
    )

    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_ZitadelProvision",
        object_id=account_id,
        before_value=None,
        updated_values={
            "operation": "sync_admin_grants",
            "project_id": cfg["project_id"],
            "organization_id": cfg["organization_id"],
            "role_prefix": req.role_prefix,
            "summary": result.get("grants_summary"),
            "unresolved_count": len(result.get("unresolved_admins") or []),
        },
        domain="iam",
        changed_by="super_admin",
    )
    return {"status": "ok", "result": result}


@router.post("/accounts/{account_id}/zitadel/provision/bootstrap")
async def bootstrap_account_zitadel_provisioning(
    account_id: str,
    req: ZitadelBootstrapRequest,
    _: None = Depends(require_super_admin),
):
    db = await _db()
    account = await db.alchemi_accounttable.find_first(where={"account_id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    metadata = _decode_json_field(_row_get(account, "metadata"), {})
    zitadel_cfg = dict((metadata or {}).get("zitadel") or {})
    cfg = _resolved_zitadel_config(metadata, req.project_id, req.organization_id)
    if not cfg["project_id"]:
        raise HTTPException(status_code=400, detail="project_id missing in request and account zitadel config")

    role_prefix = _normalize_role_prefix(req.role_prefix)
    config_before = _to_jsonable(dict(zitadel_cfg))
    role_mappings = dict(zitadel_cfg.get("role_mappings") or {})

    config_changed = False
    if req.apply_default_role_mappings:
        if not role_mappings:
            role_mappings = _default_role_mappings(role_prefix)
            config_changed = True
        if not zitadel_cfg.get("account_id_claim"):
            zitadel_cfg["account_id_claim"] = "alchemi:account_id"
            config_changed = True
        if not zitadel_cfg.get("product_domains_claim"):
            zitadel_cfg["product_domains_claim"] = "product_domains_allowed"
            config_changed = True

    if zitadel_cfg.get("project_id") != cfg["project_id"]:
        zitadel_cfg["project_id"] = cfg["project_id"]
        config_changed = True
    if cfg["organization_id"] is not None and zitadel_cfg.get("organization_id") != cfg["organization_id"]:
        zitadel_cfg["organization_id"] = cfg["organization_id"]
        config_changed = True
    if role_mappings and zitadel_cfg.get("role_mappings") != role_mappings:
        zitadel_cfg["role_mappings"] = role_mappings
        config_changed = True
    if "enabled" not in zitadel_cfg:
        zitadel_cfg["enabled"] = True
    metadata["zitadel"] = zitadel_cfg

    roles_result: Dict[str, Any] = {"summary": {"created": 0, "exists": 0, "skipped": 0, "failed": 0}, "results": []}
    grants_result: Dict[str, Any] = {
        "admins_total": 0,
        "grants": [],
        "grants_summary": {"created": 0, "exists": 0, "skipped": 0, "failed": 0},
        "unresolved_admins": [],
        "resolved_user_ids": {},
    }

    if req.create_project_roles:
        client = ZitadelManagementClient()
        if not client.is_configured():
            raise HTTPException(status_code=400, detail="Zitadel management client is not configured")
        roles_result = await _sync_zitadel_project_roles(
            client=client,
            project_id=str(cfg["project_id"]),
            role_prefix=role_prefix,
            skip_existing=req.skip_existing,
            dry_run=req.dry_run,
        )

    if req.grant_existing_account_admins:
        grants_result = await _sync_zitadel_account_admin_grants(
            db=db,
            account_id=account_id,
            project_id=str(cfg["project_id"]),
            organization_id=str(cfg["organization_id"]) if cfg["organization_id"] else None,
            role_mappings=role_mappings or _default_role_mappings(role_prefix),
            user_id_by_email=req.user_id_by_email,
            resolve_user_ids_from_zitadel=req.resolve_user_ids_from_zitadel,
            default_role_keys=req.default_role_keys,
            skip_existing=req.skip_existing,
            dry_run=req.dry_run,
        )

    if config_changed and not req.dry_run:
        await db.alchemi_accounttable.update(where={"account_id": account_id}, data={"metadata": Json(metadata)})

    summary = {
        "account_id": account_id,
        "dry_run": req.dry_run,
        "project_id": cfg["project_id"],
        "organization_id": cfg["organization_id"],
        "config_updated": bool(config_changed and not req.dry_run),
        "role_sync_summary": roles_result.get("summary"),
        "admin_grant_summary": grants_result.get("grants_summary"),
        "unresolved_admins": grants_result.get("unresolved_admins"),
    }

    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_ZitadelProvision",
        object_id=account_id,
        before_value={"zitadel_config": config_before},
        updated_values={
            "operation": "bootstrap",
            "summary": summary,
            "roles": roles_result.get("summary"),
            "admin_grants": grants_result.get("grants_summary"),
        },
        domain="iam",
        changed_by="super_admin",
    )

    return {
        "status": "ok",
        "summary": summary,
        "result": {
            "zitadel_config": zitadel_cfg,
            "roles": roles_result,
            "admin_grants": grants_result,
        },
    }


async def _list_orgs(domain: str):
    require_domain_admin(domain)
    account_id = get_current_account_id()
    db = await _db()
    t = _domain_tables(domain)
    rows = await db.query_raw(f"SELECT * FROM {t['org']} WHERE account_id = $1 ORDER BY created_at DESC", account_id)
    return {"items": rows}


async def _create_org(domain: str, req: DomainOrgCreateRequest):
    require_domain_admin(domain)
    account_id = get_current_account_id()
    db = await _db()
    t = _domain_tables(domain)
    row = await db.query_raw(
        f'INSERT INTO {t["org"]} (id, account_id, name, description, created_by) VALUES ($1,$2,$3,$4,$5) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.name,
        req.description,
        "api",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name=t["org"].replace('"', ""),
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values=_to_jsonable(dict(item)),
            domain=domain,
            changed_by="account_admin",
        )
    return {"item": item}


async def _list_teams(domain: str, org_id: Optional[str]):
    require_domain_admin(domain)
    account_id = get_current_account_id()
    db = await _db()
    t = _domain_tables(domain)
    if org_id:
        rows = await db.query_raw(f"SELECT * FROM {t['team']} WHERE account_id = $1 AND org_id = $2 ORDER BY created_at DESC", account_id, org_id)
    else:
        rows = await db.query_raw(f"SELECT * FROM {t['team']} WHERE account_id = $1 ORDER BY created_at DESC", account_id)
    return {"items": rows}


async def _create_team(domain: str, req: DomainTeamCreateRequest):
    require_domain_admin(domain)
    account_id = get_current_account_id()
    db = await _db()
    t = _domain_tables(domain)
    await _ensure_domain_scope_exists(db, domain, "org", req.org_id, account_id)
    row = await db.query_raw(
        f'INSERT INTO {t["team"]} (id, account_id, org_id, name, description, created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.org_id,
        req.name,
        req.description,
        "api",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name=t["team"].replace('"', ""),
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values=_to_jsonable(dict(item)),
            domain=domain,
            changed_by="account_admin",
        )
    return {"item": item}


async def _list_users(domain: str):
    require_domain_admin(domain)
    account_id = get_current_account_id()
    db = await _db()
    t = _domain_tables(domain)
    rows = await db.query_raw(f"SELECT * FROM {t['user']} WHERE account_id = $1 ORDER BY created_at DESC", account_id)
    return {"items": rows}


async def _create_user(domain: str, req: DomainUserCreateRequest):
    require_domain_admin(domain)
    account_id = get_current_account_id()
    db = await _db()
    t = _domain_tables(domain)

    email = (req.email or "").strip().lower() or None
    display_name = (req.display_name or "").strip() or None
    identity_user_id = (req.identity_user_id or "").strip() or None

    if not email and not identity_user_id:
        raise HTTPException(
            status_code=400,
            detail="Either email or identity_user_id is required",
        )

    # Resolve identity_user_id from Zitadel by email when omitted.
    if not identity_user_id and email:
        try:
            client = ZitadelManagementClient()
            if client.is_configured():
                identity_user_id = await client.find_user_id_by_email(email=email)
        except Exception:
            # Keep user creation non-blocking if Zitadel lookup fails.
            identity_user_id = None

    existing = await db.query_raw(
        f"SELECT * FROM {t['user']} WHERE account_id = $1 AND ("
        "($2::text IS NOT NULL AND lower(email) = lower($2::text)) OR "
        "($3::text IS NOT NULL AND identity_user_id = $3::text)"
        ") LIMIT 1",
        account_id,
        email,
        identity_user_id,
    )

    audit_action = "create"
    if existing:
        existing_row = existing[0]
        user_id = (
            existing_row.get("id")
            if isinstance(existing_row, dict)
            else getattr(existing_row, "id", None)
        )
        if not user_id:
            raise HTTPException(status_code=500, detail="Existing user row missing id")
        row = await db.query_raw(
            f"UPDATE {t['user']} SET "
            "email = COALESCE($2::text, email), "
            "identity_user_id = COALESCE($3::text, identity_user_id), "
            "display_name = COALESCE($4::text, display_name), "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE id = $1 RETURNING *",
            str(user_id),
            email,
            identity_user_id,
            display_name,
        )
        audit_action = "update"
    else:
        user_id = str(uuid.uuid4())
        row = await db.query_raw(
            f'INSERT INTO {t["user"]} (id, account_id, identity_user_id, email, display_name, created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
            user_id,
            account_id,
            identity_user_id,
            email,
            display_name,
            "api",
        )

    for team_id in req.team_ids:
        await _ensure_domain_scope_exists(db, domain, "team", team_id, account_id)
        await db.query_raw(
            f'INSERT INTO {t["membership"]} (id, account_id, team_id, user_id, role) VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING',
            str(uuid.uuid4()),
            account_id,
            team_id,
            user_id,
            "member",
        )

    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action=audit_action,
            table_name=t["user"].replace('"', ""),
            object_id=str(user_id),
            before_value=None,
            updated_values={
                **_to_jsonable(dict(item)),
                "team_ids": req.team_ids,
                "identity_user_id_resolved": bool(identity_user_id),
            },
            domain=domain,
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/orgs")
async def list_copilot_orgs():
    return await _list_orgs("copilot")


@router.post("/copilot/orgs")
async def create_copilot_org(req: DomainOrgCreateRequest):
    return await _create_org("copilot", req)


@router.get("/copilot/teams")
async def list_copilot_teams(org_id: Optional[str] = None):
    return await _list_teams("copilot", org_id)


@router.post("/copilot/teams")
async def create_copilot_team(req: DomainTeamCreateRequest):
    return await _create_team("copilot", req)


@router.get("/copilot/users")
async def list_copilot_users():
    return await _list_users("copilot")


@router.post("/copilot/users")
async def create_copilot_user(req: DomainUserCreateRequest):
    return await _create_user("copilot", req)


@router.get("/console/orgs")
async def list_console_orgs():
    return await _list_orgs("console")


@router.post("/console/orgs")
async def create_console_org(req: DomainOrgCreateRequest):
    return await _create_org("console", req)


@router.get("/console/teams")
async def list_console_teams(org_id: Optional[str] = None):
    return await _list_teams("console", org_id)


@router.post("/console/teams")
async def create_console_team(req: DomainTeamCreateRequest):
    return await _create_team("console", req)


@router.get("/console/users")
async def list_console_users():
    return await _list_users("console")


@router.post("/console/users")
async def create_console_user(req: DomainUserCreateRequest):
    return await _create_user("console", req)


@router.post("/budgets/account-allocation")
async def set_account_allocation(req: AccountAllocationRequest, _: None = Depends(require_super_admin)):
    db = await _db()
    if req.monthly_credits < 0 or req.overflow_limit < 0 or req.credit_factor <= 0:
        raise HTTPException(status_code=400, detail="Invalid allocation values")
    account = await db.alchemi_accounttable.find_first(where={"account_id": req.account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    existing = await db.query_raw(
        'SELECT monthly_credits, overflow_limit, credit_factor FROM "Alchemi_AccountAllocationTable" WHERE account_id = $1 LIMIT 1',
        req.account_id,
    )
    await db.query_raw(
        'INSERT INTO "Alchemi_AccountAllocationTable" (id, account_id, monthly_credits, overflow_limit, credit_factor, updated_by) VALUES ($1,$2,$3,$4,$5,$6) '
        'ON CONFLICT (account_id) DO UPDATE SET monthly_credits = EXCLUDED.monthly_credits, overflow_limit = EXCLUDED.overflow_limit, credit_factor = EXCLUDED.credit_factor, updated_at = CURRENT_TIMESTAMP, updated_by = EXCLUDED.updated_by',
        str(uuid.uuid4()),
        req.account_id,
        req.monthly_credits,
        req.overflow_limit,
        req.credit_factor,
        "super_admin",
    )
    await _audit_event(
        db=db,
        action="upsert",
        table_name="Alchemi_AccountAllocationTable",
        object_id=req.account_id,
        before_value=_to_jsonable(dict(existing[0])) if existing else None,
        updated_values={
            "account_id": req.account_id,
            "monthly_credits": req.monthly_credits,
            "overflow_limit": req.overflow_limit,
            "credit_factor": req.credit_factor,
        },
        domain="billing",
        changed_by="super_admin",
    )
    return {"status": "ok"}


@router.get("/budgets/account-allocation")
async def list_account_allocations(account_id: Optional[str] = None, _: None = Depends(require_super_admin)):
    db = await _db()
    if account_id:
        rows = await db.query_raw(
            'SELECT account_id, monthly_credits, overflow_limit, credit_factor, effective_from, updated_at '
            'FROM "Alchemi_AccountAllocationTable" WHERE account_id = $1 LIMIT 1',
            account_id,
        )
        return {"item": rows[0] if rows else None}
    rows = await db.query_raw(
        'SELECT account_id, monthly_credits, overflow_limit, credit_factor, effective_from, updated_at '
        'FROM "Alchemi_AccountAllocationTable" ORDER BY updated_at DESC'
    )
    return {"items": rows}


@router.get("/budgets/copilot/account-allocation")
async def get_account_allocation():
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT monthly_credits, overflow_limit, credit_factor, effective_from, updated_at FROM "Alchemi_AccountAllocationTable" WHERE account_id = $1 LIMIT 1',
        account_id,
    )
    return rows[0] if rows else {"monthly_credits": 0, "overflow_limit": 0, "credit_factor": 1}


@router.post("/budgets/copilot/plans")
async def create_copilot_budget_plan(req: BudgetPlanRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    previous_active = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotBudgetPlanTable" WHERE account_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT 1',
        account_id,
        "active",
    )
    await db.query_raw(
        'UPDATE "Alchemi_CopilotBudgetPlanTable" SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE account_id = $2 AND status = $3',
        "inactive",
        account_id,
        "active",
    )
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotBudgetPlanTable" (id, account_id, name, cycle, created_by) VALUES ($1,$2,$3,$4,$5) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.name,
        req.cycle,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_CopilotBudgetPlanTable",
            object_id=str(_row_get(item, "id")),
            before_value=_to_jsonable(dict(previous_active[0])) if previous_active else None,
            updated_values={"new_active_plan": _to_jsonable(dict(item))},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/budgets/copilot/plans/active")
async def get_active_copilot_budget_plan():
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotBudgetPlanTable" WHERE account_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT 1',
        account_id,
        "active",
    )
    return {"item": rows[0] if rows else None}


@router.patch("/budgets/copilot/plans/{plan_id}")
async def update_copilot_budget_plan(plan_id: str, req: BudgetPlanUpdateRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotBudgetPlanTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        plan_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Budget plan not found")

    row = await db.query_raw(
        'UPDATE "Alchemi_CopilotBudgetPlanTable" SET name = $1, updated_at = CURRENT_TIMESTAMP WHERE account_id = $2 AND id = $3 RETURNING *',
        name,
        account_id,
        plan_id,
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="update",
            table_name="Alchemi_CopilotBudgetPlanTable",
            object_id=plan_id,
            before_value=_to_jsonable(dict(existing[0])),
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.post("/budgets/copilot/allocations/upsert")
async def upsert_copilot_allocation(req: BudgetAllocationUpsertRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    req.scope_type = _normalize_copilot_scope_type(req.scope_type)
    _validate_scope_type(req.scope_type, VALID_BUDGET_SCOPE_TYPES)
    if req.allocated_credits < 0:
        raise HTTPException(status_code=400, detail="allocated_credits cannot be negative")
    if req.overflow_cap is not None and req.overflow_cap < 0:
        raise HTTPException(status_code=400, detail="overflow_cap cannot be negative")

    plan_exists = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotBudgetPlanTable" WHERE id = $1 AND account_id = $2 LIMIT 1',
        req.plan_id,
        account_id,
    )
    if not plan_exists:
        raise HTTPException(status_code=404, detail="Budget plan not found")

    if req.scope_type != "pool":
        await _ensure_domain_scope_exists(db, "copilot", req.scope_type, req.scope_id, account_id)

    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotBudgetAllocationTable" WHERE account_id = $1 AND plan_id = $2 AND scope_type = $3 AND scope_id = $4 LIMIT 1',
        account_id,
        req.plan_id,
        req.scope_type,
        req.scope_id,
    )
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotBudgetAllocationTable" '
        '(id, account_id, plan_id, scope_type, scope_id, allocated_credits, overflow_cap, source, created_by) '
        'VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) '
        'ON CONFLICT (plan_id, scope_type, scope_id) DO UPDATE SET '
        'allocated_credits = EXCLUDED.allocated_credits, overflow_cap = EXCLUDED.overflow_cap, source = EXCLUDED.source, updated_at = CURRENT_TIMESTAMP '
        'RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.plan_id,
        req.scope_type,
        req.scope_id,
        req.allocated_credits,
        req.overflow_cap,
        req.source,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="upsert",
            table_name="Alchemi_CopilotBudgetAllocationTable",
            object_id=str(_row_get(item, "id")),
            before_value=_to_jsonable(dict(existing[0])) if existing else None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.delete("/budgets/copilot/allocations")
async def delete_copilot_allocation(
    plan_id: str,
    scope_type: str,
    scope_id: str,
):
    account_id = require_domain_admin("copilot")
    db = await _db()
    scope_type = _normalize_copilot_scope_type(scope_type)
    _validate_scope_type(scope_type, VALID_BUDGET_SCOPE_TYPES)
    rows = await db.query_raw(
        'DELETE FROM "Alchemi_CopilotBudgetAllocationTable" WHERE account_id = $1 AND plan_id = $2 AND scope_type = $3 AND scope_id = $4 RETURNING *',
        account_id,
        plan_id,
        scope_type,
        scope_id,
    )
    if rows:
        await _audit_event(
            db=db,
            action="delete",
            table_name="Alchemi_CopilotBudgetAllocationTable",
            object_id=str(_row_get(rows[0], "id")),
            before_value=_to_jsonable(dict(rows[0])),
            updated_values={"plan_id": plan_id, "scope_type": scope_type, "scope_id": scope_id},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"deleted": bool(rows)}


@router.post("/budgets/copilot/distribute/equal")
async def equal_distribute_copilot(req: EqualDistributeRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    req.scope_type = _normalize_copilot_scope_type(req.scope_type)
    _validate_scope_type(req.scope_type, VALID_BUDGET_SCOPE_TYPES)
    if not req.scope_ids:
        raise HTTPException(status_code=400, detail="scope_ids cannot be empty")
    if req.total_credits < 0:
        raise HTTPException(status_code=400, detail="total_credits cannot be negative")

    plan_exists = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotBudgetPlanTable" WHERE id = $1 AND account_id = $2 LIMIT 1',
        req.plan_id,
        account_id,
    )
    if not plan_exists:
        raise HTTPException(status_code=404, detail="Budget plan not found")

    if req.scope_type != "pool":
        for sid in req.scope_ids:
            await _ensure_domain_scope_exists(db, "copilot", req.scope_type, sid, account_id)

    per = req.total_credits / len(req.scope_ids)

    changed_ids: List[str] = []
    for sid in req.scope_ids:
        existing = await db.query_raw(
            'SELECT * FROM "Alchemi_CopilotBudgetAllocationTable" WHERE account_id = $1 AND plan_id = $2 AND scope_type = $3 AND scope_id = $4 LIMIT 1',
            account_id,
            req.plan_id,
            req.scope_type,
            sid,
        )
        row = await db.query_raw(
            'INSERT INTO "Alchemi_CopilotBudgetAllocationTable" (id, account_id, plan_id, scope_type, scope_id, allocated_credits, overflow_cap, source, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) '
            'ON CONFLICT (plan_id, scope_type, scope_id) DO UPDATE SET allocated_credits = EXCLUDED.allocated_credits, overflow_cap = EXCLUDED.overflow_cap, source = EXCLUDED.source, updated_at = CURRENT_TIMESTAMP RETURNING *',
            str(uuid.uuid4()),
            account_id,
            req.plan_id,
            req.scope_type,
            sid,
            per,
            req.overflow_cap,
            "equal",
            "account_admin",
        )
        if row:
            changed_ids.append(str(_row_get(row[0], "id")))
            await _audit_event(
                db=db,
                action="upsert",
                table_name="Alchemi_CopilotBudgetAllocationTable",
                object_id=str(_row_get(row[0], "id")),
                before_value=_to_jsonable(dict(existing[0])) if existing else None,
                updated_values=_to_jsonable(dict(row[0])),
                domain="copilot",
                changed_by="account_admin",
            )
    return {"status": "ok", "per_scope": per, "allocation_ids": changed_ids}


@router.post("/budgets/copilot/overrides")
async def set_copilot_overrides(req: BudgetOverrideRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    req.scope_type = _normalize_copilot_scope_type(req.scope_type)
    _validate_scope_type(req.scope_type, VALID_BUDGET_SCOPE_TYPES)
    if req.override_credits < 0:
        raise HTTPException(status_code=400, detail="override_credits cannot be negative")

    plan_exists = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotBudgetPlanTable" WHERE id = $1 AND account_id = $2 LIMIT 1',
        req.plan_id,
        account_id,
    )
    if not plan_exists:
        raise HTTPException(status_code=404, detail="Budget plan not found")

    if req.scope_type != "pool":
        await _ensure_domain_scope_exists(db, "copilot", req.scope_type, req.scope_id, account_id)

    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotBudgetOverrideTable" (id, account_id, plan_id, scope_type, scope_id, override_credits, reason, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.plan_id,
        req.scope_type,
        req.scope_id,
        req.override_credits,
        req.reason,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_CopilotBudgetOverrideTable",
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/budgets/copilot/effective-allocation")
async def get_effective_copilot_allocation(plan_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    plan_exists = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotBudgetPlanTable" WHERE id = $1 AND account_id = $2 LIMIT 1',
        plan_id,
        account_id,
    )
    if not plan_exists:
        raise HTTPException(status_code=404, detail="Budget plan not found")

    alloc = await db.query_raw(
        'SELECT scope_type, scope_id, allocated_credits, overflow_cap FROM "Alchemi_CopilotBudgetAllocationTable" WHERE account_id = $1 AND plan_id = $2',
        account_id,
        plan_id,
    )
    ov = await db.query_raw(
        'SELECT scope_type, scope_id, override_credits FROM "Alchemi_CopilotBudgetOverrideTable" WHERE account_id = $1 AND plan_id = $2',
        account_id,
        plan_id,
    )

    override_map = {(str(_row_get(r, "scope_type")), str(_row_get(r, "scope_id"))): float(_row_get(r, "override_credits", 0) or 0) for r in ov}

    resolved = []
    total_allocated = 0.0
    for r in alloc:
        key = (str(_row_get(r, "scope_type")), str(_row_get(r, "scope_id")))
        base = float(_row_get(r, "allocated_credits", 0) or 0)
        eff = override_map.get(key, base)
        total_allocated += eff
        resolved.append(
            {
                "scope_type": key[0],
                "scope_id": key[1],
                "base_allocated": base,
                "effective_allocated": eff,
                "override_applied": key in override_map,
                "overflow_cap": _row_get(r, "overflow_cap"),
            }
        )

    acct = await db.query_raw('SELECT monthly_credits, overflow_limit, credit_factor FROM "Alchemi_AccountAllocationTable" WHERE account_id = $1 LIMIT 1', account_id)
    account_cfg = acct[0] if acct else {}
    monthly_credits = float(_row_get(account_cfg, "monthly_credits", 0) or 0)

    return {
        "plan_id": plan_id,
        "account_id": account_id,
        "monthly_credits": monthly_credits,
        "distributed": total_allocated,
        "unallocated": monthly_credits - total_allocated,
        "credit_factor": _row_get(account_cfg, "credit_factor", 1),
        "overflow_limit": _row_get(account_cfg, "overflow_limit", 0),
        "items": resolved,
    }


@router.get("/budgets/copilot/cost-breakdown")
async def get_copilot_cost_breakdown(by: str = Query(default="agent")):
    account_id = require_domain_admin("copilot")
    db = await _db()
    col_map = {
        "agent": "agent_id",
        "llm": "model_name",
        "connection": "connection_id",
        "guardrail": "guardrail_code",
    }
    if by not in col_map:
        raise HTTPException(status_code=400, detail="by must be one of: agent,llm,connection,guardrail")

    col = col_map[by]
    rows = await db.query_raw(
        f'SELECT {col} AS key, SUM(raw_cost) AS raw_cost, SUM(credits_incurred) AS credits FROM "Alchemi_CopilotUsageLedgerTable" WHERE account_id = $1 GROUP BY {col} ORDER BY SUM(credits_incurred) DESC',
        account_id,
    )
    return {"by": by, "items": rows}


@router.get("/budgets/copilot/usage-by-scope")
async def get_copilot_usage_by_scope(plan_id: Optional[str] = None):
    account_id = require_domain_admin("copilot")
    db = await _db()

    if not plan_id:
        active = await db.query_raw(
            'SELECT id FROM "Alchemi_CopilotBudgetPlanTable" WHERE account_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT 1',
            account_id,
            "active",
        )
        plan_id = str(_row_get(active[0], "id")) if active else None

    if not plan_id:
        return {"plan_id": None, "items": []}

    allocations = await db.query_raw(
        'SELECT scope_type, scope_id, allocated_credits, overflow_cap FROM "Alchemi_CopilotBudgetAllocationTable" WHERE account_id = $1 AND plan_id = $2',
        account_id,
        plan_id,
    )

    usage = await db.query_raw(
        'SELECT org_id, team_id, user_id, SUM(credits_incurred) AS used '
        'FROM "Alchemi_CopilotUsageLedgerTable" WHERE account_id = $1 GROUP BY org_id, team_id, user_id',
        account_id,
    )

    used_by_scope: Dict[tuple[str, str], float] = {}
    for u in usage:
        org_id = _row_get(u, "org_id")
        team_id = _row_get(u, "team_id")
        user_id = _row_get(u, "user_id")
        used = float(_row_get(u, "used", 0) or 0)
        if user_id:
            used_by_scope[("user", str(user_id))] = used_by_scope.get(("user", str(user_id)), 0.0) + used
        if team_id:
            used_by_scope[("team", str(team_id))] = used_by_scope.get(("team", str(team_id)), 0.0) + used
        if org_id:
            used_by_scope[("org", str(org_id))] = used_by_scope.get(("org", str(org_id)), 0.0) + used

    items = []
    for a in allocations:
        scope_type = str(_row_get(a, "scope_type"))
        scope_id = str(_row_get(a, "scope_id"))
        allocated = float(_row_get(a, "allocated_credits", 0) or 0)
        used = float(used_by_scope.get((scope_type, scope_id), 0.0))
        overflow_cap = _row_get(a, "overflow_cap")
        usage_pct = (used / allocated * 100.0) if allocated > 0 else 0.0
        overflow_used = max(0.0, used - allocated)
        items.append(
            {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "allocated_credits": allocated,
                "used": used,
                "usage_percentage": usage_pct,
                "overflow_cap": overflow_cap,
                "overflow_used": overflow_used,
            }
        )

    return {"plan_id": plan_id, "items": items}


@router.get("/budgets/copilot/alerts")
async def get_copilot_budget_alerts(threshold: float = Query(default=80.0, ge=0, le=1000)):
    account_id = require_domain_admin("copilot")
    db = await _db()
    usage = await get_copilot_usage_by_scope()
    items = usage.get("items", [])

    alerts = []
    for item in items:
        usage_pct = float(item.get("usage_percentage", 0) or 0)
        if usage_pct < threshold:
            continue
        level = "warning"
        if usage_pct >= 100:
            level = "exceeded"
        elif usage_pct >= 90:
            level = "critical"
        scope_type = item["scope_type"]
        scope_id = item["scope_id"]
        name = scope_id
        if scope_type in {"org", "team", "user"}:
            t = _domain_tables("copilot")
            table = t["org"] if scope_type == "org" else t["team"] if scope_type == "team" else t["user"]
            name_rows = await db.query_raw(f"SELECT name, display_name, email FROM {table} WHERE account_id = $1 AND id = $2 LIMIT 1", account_id, scope_id)
            if name_rows:
                name = str(_row_get(name_rows[0], "name") or _row_get(name_rows[0], "display_name") or _row_get(name_rows[0], "email") or scope_id)
        alerts.append(
            {
                "entity_name": name,
                "usage_percentage": usage_pct,
                "alert_level": level,
                "budget": {"entity_type": scope_type.upper(), "entity_id": scope_id},
            }
        )
    alerts.sort(key=lambda x: x["usage_percentage"], reverse=True)
    return {"items": alerts}


@router.post("/budgets/copilot/usage/record")
async def record_copilot_usage(req: UsageRecordRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if req.raw_cost < 0:
        raise HTTPException(status_code=400, detail="raw_cost cannot be negative")
    acct = await db.query_raw(
        'SELECT credit_factor FROM "Alchemi_AccountAllocationTable" WHERE account_id = $1 LIMIT 1',
        account_id,
    )
    credit_factor = float(_row_get(acct[0], "credit_factor", 1) or 1) if acct else 1.0
    credits_incurred = float(req.raw_cost) * credit_factor
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotUsageLedgerTable" '
        '(id, account_id, org_id, team_id, user_id, agent_id, model_name, connection_id, guardrail_code, raw_cost, credit_factor, credits_incurred, metadata) '
        'VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.org_id,
        req.team_id,
        req.user_id,
        req.agent_id,
        req.model_name,
        req.connection_id,
        req.guardrail_code,
        float(req.raw_cost),
        credit_factor,
        credits_incurred,
        Json(req.metadata),
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_CopilotUsageLedgerTable",
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="system",
        )
    return {"item": item}


@router.post("/budgets/copilot/cycles/renew")
async def renew_copilot_budget_cycle(req: BudgetCycleRenewRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if req.cycle_end <= req.cycle_start:
        raise HTTPException(status_code=400, detail="cycle_end must be after cycle_start")

    active_plan_rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotBudgetPlanTable" WHERE account_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT 1',
        account_id,
        "active",
    )
    if not active_plan_rows:
        raise HTTPException(status_code=404, detail="No active budget plan found")
    active_plan = active_plan_rows[0]
    source_plan_id = str(_row_get(active_plan, "id"))

    effective = await get_effective_copilot_allocation(source_plan_id)
    monthly_credits = float(effective.get("monthly_credits", 0) or 0)
    unallocated = float(effective.get("unallocated", 0) or 0)

    usage_rows = await db.query_raw(
        'SELECT SUM(credits_incurred) AS used FROM "Alchemi_CopilotUsageLedgerTable" WHERE account_id = $1 AND created_at >= $2 AND created_at < $3',
        account_id,
        req.cycle_start,
        req.cycle_end,
    )
    used_credits = float(_row_get(usage_rows[0], "used", 0) or 0) if usage_rows else 0
    overflow_charge_credits = max(0.0, used_credits - monthly_credits)
    rollover_cap = req.rollover_cap if req.rollover_cap is not None else max(0.0, unallocated)
    rollover_credits = max(0.0, min(max(0.0, unallocated), max(0.0, rollover_cap)))

    await db.query_raw(
        'UPDATE "Alchemi_CopilotBudgetPlanTable" SET status = $1, updated_at = CURRENT_TIMESTAMP WHERE account_id = $2 AND id = $3',
        "inactive",
        account_id,
        source_plan_id,
    )

    new_plan_id = str(uuid.uuid4())
    new_plan_name = req.new_plan_name or f"{_row_get(active_plan, 'name', 'Budget Plan')} ({req.cycle_end.date().isoformat()})"
    new_plan_row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotBudgetPlanTable" (id, account_id, name, cycle, status, created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
        new_plan_id,
        account_id,
        new_plan_name,
        _row_get(active_plan, "cycle", "monthly"),
        "active",
        "account_admin",
    )

    old_allocations = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotBudgetAllocationTable" WHERE account_id = $1 AND plan_id = $2',
        account_id,
        source_plan_id,
    )
    for alloc in old_allocations:
        await db.query_raw(
            'INSERT INTO "Alchemi_CopilotBudgetAllocationTable" (id, account_id, plan_id, scope_type, scope_id, allocated_credits, overflow_cap, source, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)',
            str(uuid.uuid4()),
            account_id,
            new_plan_id,
            _row_get(alloc, "scope_type"),
            _row_get(alloc, "scope_id"),
            float(_row_get(alloc, "allocated_credits", 0) or 0),
            _row_get(alloc, "overflow_cap"),
            _row_get(alloc, "source", "renewal_copy"),
            "account_admin",
        )

    if rollover_credits > 0:
        await db.query_raw(
            'INSERT INTO "Alchemi_CopilotBudgetAllocationTable" (id, account_id, plan_id, scope_type, scope_id, allocated_credits, overflow_cap, source, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) '
            'ON CONFLICT (plan_id, scope_type, scope_id) DO UPDATE SET allocated_credits = EXCLUDED.allocated_credits, source = EXCLUDED.source, updated_at = CURRENT_TIMESTAMP',
            str(uuid.uuid4()),
            account_id,
            new_plan_id,
            "pool",
            "pool",
            rollover_credits,
            None,
            "cycle_rollover",
            "account_admin",
        )

    if req.copy_overrides:
        old_overrides = await db.query_raw(
            'SELECT * FROM "Alchemi_CopilotBudgetOverrideTable" WHERE account_id = $1 AND plan_id = $2',
            account_id,
            source_plan_id,
        )
        for ov in old_overrides:
            await db.query_raw(
                'INSERT INTO "Alchemi_CopilotBudgetOverrideTable" (id, account_id, plan_id, scope_type, scope_id, override_credits, reason, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)',
                str(uuid.uuid4()),
                account_id,
                new_plan_id,
                _row_get(ov, "scope_type"),
                _row_get(ov, "scope_id"),
                float(_row_get(ov, "override_credits", 0) or 0),
                f"copied_from:{source_plan_id}",
                "account_admin",
            )

    cycle_id = str(uuid.uuid4())
    summary = {
        "source_plan_id": source_plan_id,
        "new_plan_id": new_plan_id,
        "used_credits": used_credits,
        "monthly_credits": monthly_credits,
        "overflow_charge_credits": overflow_charge_credits,
        "rollover_credits": rollover_credits,
    }
    await db.query_raw(
        'INSERT INTO "Alchemi_CopilotBudgetCycleTable" (id, account_id, source_plan_id, new_plan_id, cycle_start, cycle_end, rollover_credits, overflow_charge_credits, summary_json, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',
        cycle_id,
        account_id,
        source_plan_id,
        new_plan_id,
        req.cycle_start,
        req.cycle_end,
        rollover_credits,
        overflow_charge_credits,
        Json(summary),
        "account_admin",
    )

    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_CopilotBudgetCycleTable",
        object_id=cycle_id,
        before_value=None,
        updated_values={"domain": "copilot", **summary},
        domain="copilot",
        changed_by="account_admin",
    )

    return {
        "cycle_id": cycle_id,
        "item": new_plan_row[0] if new_plan_row else None,
        "summary": summary,
    }


@router.get("/budgets/copilot/cycles/history")
async def get_copilot_budget_cycle_history(limit: int = 50, offset: int = 0):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotBudgetCycleTable" WHERE account_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3',
        account_id,
        limit,
        offset,
    )
    return {"items": rows}


@router.post("/copilot/agents")
async def create_copilot_agent(req: CopilotAgentRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    guardrail_preset_ids = await _ensure_guardrail_presets_exist(db, account_id, req.guardrail_preset_ids)
    agent_id = str(uuid.uuid4())

    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotAgentTable" (id, account_id, name, description, definition_json, created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
        agent_id,
        account_id,
        req.name,
        req.description,
        Json(req.definition_json),
        "account_admin",
    )

    created_grants = await _set_agent_grants(db, account_id, agent_id, req.grants)

    await _set_agent_guardrail_assignments(db, account_id, agent_id, guardrail_preset_ids)

    item = row[0] if row else None
    if item:
        item = {
            **dict(item),
            "mandatory_guardrail_preset_ids": guardrail_preset_ids,
            "grants": created_grants,
        }
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_CopilotAgentTable",
            object_id=agent_id,
            before_value=None,
            updated_values={
                **_to_jsonable(dict(item)),
                "grants": created_grants,
                "mandatory_guardrail_preset_ids": guardrail_preset_ids,
            },
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/agents")
async def list_copilot_agents(include_grants: bool = False):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotAgentTable" WHERE account_id = $1 ORDER BY created_at DESC',
        account_id,
    )
    items: List[Dict[str, Any]] = []
    for row in rows:
        agent = dict(row)
        agent_id = str(_row_get(agent, "id"))
        agent["mandatory_guardrail_preset_ids"] = await _get_agent_guardrail_preset_ids(db, account_id, agent_id)
        if include_grants:
            agent["grants"] = await _list_agent_grants(db, account_id, agent_id)
        items.append(agent)
    return {"items": items}


@router.get("/copilot/agents/{agent_id}")
async def get_copilot_agent(agent_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotAgentTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        agent_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Agent not found")
    item = dict(rows[0])
    item["mandatory_guardrail_preset_ids"] = await _get_agent_guardrail_preset_ids(db, account_id, agent_id)
    item["grants"] = await _list_agent_grants(db, account_id, agent_id)
    return {"item": item}


@router.put("/copilot/agents/{agent_id}")
async def update_copilot_agent(agent_id: str, req: CopilotAgentUpdateRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotAgentTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        agent_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Agent not found")
    ex = existing[0]
    name = req.name if req.name is not None else _row_get(ex, "name")
    description = req.description if req.description is not None else _row_get(ex, "description")
    definition_json = req.definition_json if req.definition_json is not None else _row_get(ex, "definition_json", {})
    row = await db.query_raw(
        'UPDATE "Alchemi_CopilotAgentTable" SET name = $1, description = $2, definition_json = $3, updated_at = CURRENT_TIMESTAMP WHERE account_id = $4 AND id = $5 RETURNING *',
        name,
        description,
        Json(definition_json),
        account_id,
        agent_id,
    )
    guardrail_preset_ids: Optional[List[str]] = None
    if req.guardrail_preset_ids is not None:
        guardrail_preset_ids = await _ensure_guardrail_presets_exist(db, account_id, req.guardrail_preset_ids)
        await _set_agent_guardrail_assignments(db, account_id, agent_id, guardrail_preset_ids)
    current_guardrail_preset_ids = guardrail_preset_ids or await _get_agent_guardrail_preset_ids(db, account_id, agent_id)
    current_grants = await _list_agent_grants(db, account_id, agent_id)
    if req.grants is not None:
        current_grants = await _set_agent_grants(db, account_id, agent_id, req.grants)
    item = row[0] if row else None
    if item:
        item = {
            **dict(item),
            "mandatory_guardrail_preset_ids": current_guardrail_preset_ids,
            "grants": current_grants,
        }
        await _audit_event(
            db=db,
            action="update",
            table_name="Alchemi_CopilotAgentTable",
            object_id=agent_id,
            before_value=_to_jsonable(dict(ex)),
            updated_values={
                **_to_jsonable(dict(item)),
                "mandatory_guardrail_preset_ids": current_guardrail_preset_ids,
                "grants": current_grants,
            },
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.delete("/copilot/agents/{agent_id}")
async def delete_copilot_agent(agent_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'DELETE FROM "Alchemi_CopilotAgentTable" WHERE account_id = $1 AND id = $2 RETURNING *',
        account_id,
        agent_id,
    )
    if rows:
        await _audit_event(
            db=db,
            action="delete",
            table_name="Alchemi_CopilotAgentTable",
            object_id=agent_id,
            before_value=_to_jsonable(dict(rows[0])),
            updated_values={"id": agent_id},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"deleted": bool(rows)}


@router.post("/copilot/agents/{agent_id}/grants")
async def upsert_copilot_agent_grant(agent_id: str, req: CopilotAgentGrantRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    await _ensure_copilot_agent_exists(db, account_id, agent_id)
    _validate_scope_type(req.scope_type, {"org", "team", "user"})
    await _ensure_domain_scope_exists(db, "copilot", req.scope_type, req.scope_id, account_id)
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotAgentGrantTable" WHERE account_id = $1 AND agent_id = $2 AND scope_type = $3 AND scope_id = $4 LIMIT 1',
        account_id,
        agent_id,
        req.scope_type,
        req.scope_id,
    )
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotAgentGrantTable" (id, account_id, agent_id, scope_type, scope_id, created_by) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (agent_id, scope_type, scope_id) DO NOTHING RETURNING *',
        str(uuid.uuid4()),
        account_id,
        agent_id,
        req.scope_type,
        req.scope_id,
        "account_admin",
    )
    if row:
        item = row[0]
    else:
        existing_after = await db.query_raw(
            'SELECT * FROM "Alchemi_CopilotAgentGrantTable" WHERE account_id = $1 AND agent_id = $2 AND scope_type = $3 AND scope_id = $4 LIMIT 1',
            account_id,
            agent_id,
            req.scope_type,
            req.scope_id,
        )
        item = existing_after[0] if existing_after else None
    if item:
        await _audit_event(
            db=db,
            action="upsert",
            table_name="Alchemi_CopilotAgentGrantTable",
            object_id=str(_row_get(item, "id")),
            before_value=_to_jsonable(dict(existing[0])) if existing else None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/agents/{agent_id}/grants")
async def list_copilot_agent_grants(agent_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    await _ensure_copilot_agent_exists(db, account_id, agent_id)
    return {"items": await _list_agent_grants(db, account_id, agent_id)}


@router.delete("/copilot/agents/{agent_id}/grants")
async def delete_copilot_agent_grant(
    agent_id: str,
    scope_type: str,
    scope_id: str,
):
    account_id = require_domain_admin("copilot")
    db = await _db()
    _validate_scope_type(scope_type, {"org", "team", "user"})
    await _ensure_copilot_agent_exists(db, account_id, agent_id)
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotAgentGrantTable" WHERE account_id = $1 AND agent_id = $2 AND scope_type = $3 AND scope_id = $4 LIMIT 1',
        account_id,
        agent_id,
        scope_type,
        scope_id,
    )
    rows = await db.query_raw(
        'DELETE FROM "Alchemi_CopilotAgentGrantTable" WHERE account_id = $1 AND agent_id = $2 AND scope_type = $3 AND scope_id = $4 RETURNING *',
        account_id,
        agent_id,
        scope_type,
        scope_id,
    )
    if rows:
        await _audit_event(
            db=db,
            action="delete",
            table_name="Alchemi_CopilotAgentGrantTable",
            object_id=str(_row_get(rows[0], "id")),
            before_value=_to_jsonable(dict(existing[0])) if existing else _to_jsonable(dict(rows[0])),
            updated_values={"agent_id": agent_id, "scope_type": scope_type, "scope_id": scope_id},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"deleted": bool(rows)}


@router.post("/copilot/connections/{connection_type}")
async def create_copilot_connection(connection_type: str, req: CopilotConnectionRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    connection_type = _normalize_connection_type(connection_type)
    if connection_type not in VALID_CONNECTION_TYPES:
        raise HTTPException(status_code=400, detail="connection_type must be openapi|mcp|composio")
    if req.credential_visibility not in VALID_CONNECTION_VISIBILITY:
        raise HTTPException(status_code=400, detail="credential_visibility must be use_only|self_managed")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if connection_type == "composio":
        auth_mode = str(req.config_json.get("auth_mode") or "").strip().lower()
        if auth_mode not in {"oauth", "api_key"}:
            raise HTTPException(status_code=400, detail="composio config_json.auth_mode must be oauth|api_key")
        if auth_mode == "api_key" and not str(req.secret_json.get("api_key") or "").strip():
            raise HTTPException(status_code=400, detail="composio api_key mode requires secret_json.api_key")

    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotConnectionTable" (id, account_id, connection_type, name, description, credential_visibility, allow_user_self_manage, config_json, secret_json, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        connection_type,
        req.name,
        req.description,
        req.credential_visibility,
        req.allow_user_self_manage,
        Json(req.config_json),
        Json(req.secret_json),
        "account_admin",
    )

    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_CopilotConnectionTable",
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values={
                **_to_jsonable(dict(item)),
                "secret_json": {"masked": True},
            },
            domain="copilot",
            changed_by="account_admin",
        )
    if item:
        item = _mask_connection_secrets(item)

    return {"item": item}


@router.get("/copilot/connections")
async def list_copilot_connections(connection_type: Optional[str] = None):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if connection_type:
        connection_type = _normalize_connection_type(connection_type)
        if connection_type not in VALID_CONNECTION_TYPES:
            raise HTTPException(status_code=400, detail="connection_type must be openapi|mcp|composio")
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_CopilotConnectionTable" WHERE account_id = $1 AND connection_type = $2 ORDER BY created_at DESC',
            account_id,
            connection_type,
        )
    else:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_CopilotConnectionTable" WHERE account_id = $1 ORDER BY created_at DESC',
            account_id,
        )
    return {"items": [_mask_connection_secrets(r) for r in rows]}


@router.get("/copilot/connections/{connection_id}")
async def get_copilot_connection(connection_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotConnectionTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        connection_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"item": _mask_connection_secrets(rows[0])}


@router.patch("/copilot/connections/{connection_id}")
async def update_copilot_connection(connection_id: str, req: CopilotConnectionUpdateRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotConnectionTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        connection_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Connection not found")
    name = req.name if req.name is not None else _row_get(existing[0], "name")
    description = req.description if req.description is not None else _row_get(existing[0], "description")
    credential_visibility = req.credential_visibility if req.credential_visibility is not None else _row_get(existing[0], "credential_visibility")
    allow_user_self_manage = req.allow_user_self_manage if req.allow_user_self_manage is not None else _row_get(existing[0], "allow_user_self_manage")
    config_json = req.config_json if req.config_json is not None else _row_get(existing[0], "config_json", {})
    secret_json_update = req.secret_json if req.secret_json is not None else None
    effective_secret_json = secret_json_update if secret_json_update is not None else _row_get(existing[0], "secret_json", {})
    connection_type = _normalize_connection_type(str(_row_get(existing[0], "connection_type") or ""))

    if credential_visibility not in VALID_CONNECTION_VISIBILITY:
        raise HTTPException(status_code=400, detail="credential_visibility must be use_only|self_managed")
    if not str(name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if connection_type == "composio":
        auth_mode = str(config_json.get("auth_mode") or "").strip().lower()
        if auth_mode not in {"oauth", "api_key"}:
            raise HTTPException(status_code=400, detail="composio config_json.auth_mode must be oauth|api_key")
        if auth_mode == "api_key" and not str(effective_secret_json.get("api_key") or "").strip():
            raise HTTPException(status_code=400, detail="composio api_key mode requires secret_json.api_key")

    row = await db.query_raw(
        'UPDATE "Alchemi_CopilotConnectionTable" '
        'SET name = $1, description = $2, credential_visibility = $3, allow_user_self_manage = $4, config_json = $5, '
        'secret_json = CASE WHEN jsonb_typeof($6::jsonb) = \'object\' AND $6::jsonb <> \'{}\'::jsonb THEN $6 ELSE secret_json END, '
        'updated_at = CURRENT_TIMESTAMP '
        'WHERE account_id = $7 AND id = $8 RETURNING *',
        name,
        description,
        credential_visibility,
        allow_user_self_manage,
        Json(config_json),
        Json(secret_json_update or {}),
        account_id,
        connection_id,
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="update",
            table_name="Alchemi_CopilotConnectionTable",
            object_id=connection_id,
            before_value={**_to_jsonable(dict(existing[0])), "secret_json": {"masked": True}},
            updated_values={**_to_jsonable(dict(item)), "secret_json": {"masked": True}},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": _mask_connection_secrets(item) if item else None}


@router.delete("/copilot/connections/{connection_id}")
async def delete_copilot_connection(connection_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'DELETE FROM "Alchemi_CopilotConnectionTable" WHERE account_id = $1 AND id = $2 RETURNING *',
        account_id,
        connection_id,
    )
    if rows:
        await _audit_event(
            db=db,
            action="delete",
            table_name="Alchemi_CopilotConnectionTable",
            object_id=connection_id,
            before_value={**_to_jsonable(dict(rows[0])), "secret_json": {"masked": True}},
            updated_values={"id": connection_id},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"deleted": bool(rows)}


@router.post("/copilot/connections/{connection_id}/grants")
async def grant_copilot_connection(connection_id: str, req: CopilotConnectionGrantRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    _validate_scope_type(req.scope_type, {"org", "team", "user"})
    await _ensure_domain_scope_exists(db, "copilot", req.scope_type, req.scope_id, account_id)
    conn_exists = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotConnectionTable" WHERE id = $1 AND account_id = $2 LIMIT 1',
        connection_id,
        account_id,
    )
    if not conn_exists:
        raise HTTPException(status_code=404, detail="Connection not found")
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotConnectionGrantTable" WHERE account_id = $1 AND connection_id = $2 AND scope_type = $3 AND scope_id = $4 LIMIT 1',
        account_id,
        connection_id,
        req.scope_type,
        req.scope_id,
    )
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotConnectionGrantTable" (id, account_id, connection_id, scope_type, scope_id, can_manage, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (connection_id, scope_type, scope_id) DO UPDATE SET can_manage = EXCLUDED.can_manage RETURNING *',
        str(uuid.uuid4()),
        account_id,
        connection_id,
        req.scope_type,
        req.scope_id,
        req.can_manage,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="upsert",
            table_name="Alchemi_CopilotConnectionGrantTable",
            object_id=str(_row_get(item, "id")),
            before_value=_to_jsonable(dict(existing[0])) if existing else None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.post("/copilot/guardrails/presets")
async def create_guardrail_preset(req: GuardrailPresetRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if not req.code.strip() or not req.name.strip():
        raise HTTPException(status_code=400, detail="code and name are required")
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotGuardrailPresetTable" WHERE account_id = $1 AND code = $2 LIMIT 1',
        account_id,
        req.code,
    )
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotGuardrailPresetTable" (id, account_id, code, name, preset_json, created_by) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (account_id, code) DO UPDATE SET name = EXCLUDED.name, preset_json = EXCLUDED.preset_json RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.code,
        req.name,
        Json(req.preset_json),
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="upsert",
            table_name="Alchemi_CopilotGuardrailPresetTable",
            object_id=str(_row_get(item, "id")),
            before_value=_to_jsonable(dict(existing[0])) if existing else None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/guardrails/presets")
async def list_guardrail_presets():
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotGuardrailPresetTable" WHERE account_id = $1 ORDER BY created_at DESC',
        account_id,
    )
    return {"items": rows}


@router.post("/copilot/guardrails/assignments")
async def assign_guardrail(req: GuardrailAssignRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    _validate_scope_type(req.scope_type, {"account", "org", "team", "user", "agent"})
    if req.scope_type == "agent":
        await _ensure_copilot_agent_exists(db, account_id, req.scope_id)
    else:
        await _ensure_domain_scope_exists(db, "copilot", req.scope_type, req.scope_id, account_id)

    preset_exists = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotGuardrailPresetTable" WHERE id = $1 AND account_id = $2 LIMIT 1',
        req.preset_id,
        account_id,
    )
    if not preset_exists:
        raise HTTPException(status_code=404, detail="Guardrail preset not found")

    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotGuardrailAssignmentTable" (id, account_id, preset_id, scope_type, scope_id, created_by) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.preset_id,
        req.scope_type,
        req.scope_id,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_CopilotGuardrailAssignmentTable",
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/guardrails/assignments")
async def list_guardrail_assignments(scope_type: Optional[str] = None, scope_id: Optional[str] = None):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if scope_type and not scope_id:
        raise HTTPException(status_code=400, detail="scope_id is required when scope_type is provided")
    if scope_type:
        _validate_scope_type(scope_type, {"org", "team", "user", "agent", "account"})
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_CopilotGuardrailAssignmentTable" WHERE account_id = $1 AND scope_type = $2 AND scope_id = $3 ORDER BY created_at DESC',
            account_id,
            scope_type,
            scope_id,
        )
    else:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_CopilotGuardrailAssignmentTable" WHERE account_id = $1 ORDER BY created_at DESC',
            account_id,
        )
    return {"items": rows}


@router.get("/copilot/guardrails/patterns")
async def list_guardrail_patterns(
    guard_type: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if guard_type and guard_type not in VALID_GUARD_TYPES:
        raise HTTPException(status_code=400, detail="guard_type must be one of: pii,toxic,jailbreak")

    target_codes = [guard_type] if guard_type else list(VALID_GUARD_TYPES)
    patterns: List[Dict[str, Any]] = []
    for code in target_codes:
        preset = await _get_or_create_guardrail_preset_by_code(db, account_id, code)
        preset_json = _row_get(preset, "preset_json", {}) or {}
        for p in (preset_json.get("custom_patterns") or []):
            normalized = _pattern_from_raw(p, account_id, code)
            if enabled is not None and bool(normalized["enabled"]) != enabled:
                continue
            patterns.append(normalized)

    patterns.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
    paged = patterns[offset : offset + limit]
    return {"items": paged, "total": len(patterns)}


@router.post("/copilot/guardrails/patterns")
async def create_guardrail_pattern(req: GuardrailPatternCreateRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    guard_type = (req.guard_type or "").strip().lower()
    if guard_type not in VALID_GUARD_TYPES:
        raise HTTPException(status_code=400, detail="guard_type must be one of: pii,toxic,jailbreak")
    if req.pattern_type not in VALID_PATTERN_TYPES:
        raise HTTPException(status_code=400, detail="pattern_type must be one of: detect,block,allow")
    if not req.pattern_name.strip() or not req.pattern_regex.strip():
        raise HTTPException(status_code=400, detail="pattern_name and pattern_regex are required")

    preset = await _get_or_create_guardrail_preset_by_code(db, account_id, guard_type)
    preset_json = _row_get(preset, "preset_json", {}) or {}
    patterns = list(preset_json.get("custom_patterns") or [])

    pattern = {
        "id": str(uuid.uuid4()),
        "pattern_name": req.pattern_name,
        "pattern_regex": req.pattern_regex,
        "pattern_type": req.pattern_type,
        "action": req.action,
        "enabled": req.enabled,
        "is_system": False,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    patterns.append(pattern)
    preset_json["custom_patterns"] = patterns

    await db.query_raw(
        'UPDATE "Alchemi_CopilotGuardrailPresetTable" SET preset_json = $1 WHERE account_id = $2 AND id = $3',
        Json(preset_json),
        account_id,
        _row_get(preset, "id"),
    )
    await _audit_event(
        db=db,
        action="create",
        table_name="Alchemi_CopilotGuardrailPattern",
        object_id=str(pattern["id"]),
        before_value=None,
        updated_values={"guard_type": guard_type, **_pattern_from_raw(pattern, account_id, guard_type)},
        domain="copilot",
        changed_by="account_admin",
    )
    return {"item": _pattern_from_raw(pattern, account_id, guard_type)}


@router.get("/copilot/guardrails/patterns/{pattern_id}")
async def get_guardrail_pattern(pattern_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    for code in VALID_GUARD_TYPES:
        preset = await _get_or_create_guardrail_preset_by_code(db, account_id, code)
        preset_json = _row_get(preset, "preset_json", {}) or {}
        for p in (preset_json.get("custom_patterns") or []):
            if str(p.get("id")) == pattern_id:
                return {"item": _pattern_from_raw(p, account_id, code)}
    raise HTTPException(status_code=404, detail="Pattern not found")


@router.put("/copilot/guardrails/patterns/{pattern_id}")
async def update_guardrail_pattern(pattern_id: str, req: GuardrailPatternUpdateRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if req.pattern_type is not None and req.pattern_type not in VALID_PATTERN_TYPES:
        raise HTTPException(status_code=400, detail="pattern_type must be one of: detect,block,allow")

    for code in VALID_GUARD_TYPES:
        preset = await _get_or_create_guardrail_preset_by_code(db, account_id, code)
        preset_json = _row_get(preset, "preset_json", {}) or {}
        patterns = list(preset_json.get("custom_patterns") or [])
        changed = False
        updated_item: Optional[Dict[str, Any]] = None
        for p in patterns:
            if str(p.get("id")) != pattern_id:
                continue
            before_pattern = dict(p)
            if p.get("is_system"):
                if req.enabled is None:
                    raise HTTPException(status_code=400, detail="System patterns can only toggle enabled")
                p["enabled"] = req.enabled
            else:
                if req.pattern_name is not None:
                    p["pattern_name"] = req.pattern_name
                if req.pattern_regex is not None:
                    p["pattern_regex"] = req.pattern_regex
                if req.pattern_type is not None:
                    p["pattern_type"] = req.pattern_type
                if req.action is not None:
                    p["action"] = req.action
                if req.enabled is not None:
                    p["enabled"] = req.enabled
            p["updated_at"] = datetime.utcnow().isoformat()
            changed = True
            updated_item = p
            break
        if changed:
            preset_json["custom_patterns"] = patterns
            await db.query_raw(
                'UPDATE "Alchemi_CopilotGuardrailPresetTable" SET preset_json = $1 WHERE account_id = $2 AND id = $3',
                Json(preset_json),
                account_id,
                _row_get(preset, "id"),
            )
            await _audit_event(
                db=db,
                action="update",
                table_name="Alchemi_CopilotGuardrailPattern",
                object_id=pattern_id,
                before_value={"guard_type": code, **_pattern_from_raw(before_pattern, account_id, code)},
                updated_values={"guard_type": code, **_pattern_from_raw(updated_item or {}, account_id, code)},
                domain="copilot",
                changed_by="account_admin",
            )
            return {"item": _pattern_from_raw(updated_item or {}, account_id, code)}
    raise HTTPException(status_code=404, detail="Pattern not found")


@router.delete("/copilot/guardrails/patterns/{pattern_id}")
async def delete_guardrail_pattern(pattern_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    for code in VALID_GUARD_TYPES:
        preset = await _get_or_create_guardrail_preset_by_code(db, account_id, code)
        preset_json = _row_get(preset, "preset_json", {}) or {}
        patterns = list(preset_json.get("custom_patterns") or [])
        kept: List[Dict[str, Any]] = []
        found = False
        for p in patterns:
            if str(p.get("id")) == pattern_id:
                if p.get("is_system"):
                    raise HTTPException(status_code=403, detail="System patterns cannot be deleted")
                found = True
                deleted_pattern = dict(p)
                continue
            kept.append(p)
        if found:
            preset_json["custom_patterns"] = kept
            await db.query_raw(
                'UPDATE "Alchemi_CopilotGuardrailPresetTable" SET preset_json = $1 WHERE account_id = $2 AND id = $3',
                Json(preset_json),
                account_id,
                _row_get(preset, "id"),
            )
            await _audit_event(
                db=db,
                action="delete",
                table_name="Alchemi_CopilotGuardrailPattern",
                object_id=pattern_id,
                before_value={"guard_type": code, **_pattern_from_raw(deleted_pattern, account_id, code)},
                updated_values={"id": pattern_id, "guard_type": code},
                domain="copilot",
                changed_by="account_admin",
            )
            return {"deleted": True}
    raise HTTPException(status_code=404, detail="Pattern not found")


@router.post("/copilot/models/grants")
async def grant_copilot_model(req: ModelGrantRequest):
    account_id = require_domain_admin("copilot")
    if req.domain != "copilot":
        raise HTTPException(status_code=400, detail="domain must be copilot")
    _validate_scope_type(req.scope_type, VALID_SCOPE_TYPES)
    db = await _db()
    await _ensure_domain_scope_exists(db, "copilot", req.scope_type, req.scope_id, account_id)
    if req.access_mode not in VALID_ACCESS_MODES:
        raise HTTPException(status_code=400, detail="access_mode must be allow|deny")
    row = await db.query_raw(
        'INSERT INTO "Alchemi_ModelGrantTable" (id, account_id, domain, model_name, scope_type, scope_id, access_mode, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.domain,
        req.model_name,
        req.scope_type,
        req.scope_id,
        req.access_mode,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_ModelGrantTable",
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.post("/console/models/grants")
async def grant_console_model(req: ModelGrantRequest):
    account_id = require_domain_admin("console")
    if req.domain != "console":
        raise HTTPException(status_code=400, detail="domain must be console")
    _validate_scope_type(req.scope_type, VALID_SCOPE_TYPES)
    db = await _db()
    await _ensure_domain_scope_exists(db, "console", req.scope_type, req.scope_id, account_id)
    if req.access_mode not in VALID_ACCESS_MODES:
        raise HTTPException(status_code=400, detail="access_mode must be allow|deny")
    row = await db.query_raw(
        'INSERT INTO "Alchemi_ModelGrantTable" (id, account_id, domain, model_name, scope_type, scope_id, access_mode, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.domain,
        req.model_name,
        req.scope_type,
        req.scope_id,
        req.access_mode,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_ModelGrantTable",
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values=_to_jsonable(dict(item)),
            domain="console",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/models/grants")
async def list_copilot_model_grants(model_name: Optional[str] = None):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if model_name:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_ModelGrantTable" WHERE account_id = $1 AND domain = $2 AND model_name = $3 ORDER BY created_at DESC',
            account_id,
            "copilot",
            model_name,
        )
    else:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_ModelGrantTable" WHERE account_id = $1 AND domain = $2 ORDER BY created_at DESC',
            account_id,
            "copilot",
        )
    return {"items": rows}


@router.get("/console/models/grants")
async def list_console_model_grants(model_name: Optional[str] = None):
    account_id = require_domain_admin("console")
    db = await _db()
    if model_name:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_ModelGrantTable" WHERE account_id = $1 AND domain = $2 AND model_name = $3 ORDER BY created_at DESC',
            account_id,
            "console",
            model_name,
        )
    else:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_ModelGrantTable" WHERE account_id = $1 AND domain = $2 ORDER BY created_at DESC',
            account_id,
            "console",
        )
    return {"items": rows}


@router.post("/features/entitlements")
async def set_feature_entitlement(req: FeatureEntitlementRequest):
    account_id = require_domain_admin(req.domain)
    _validate_scope_type(req.scope_type, VALID_SCOPE_TYPES)
    db = await _db()
    await _ensure_domain_scope_exists(db, req.domain, req.scope_type, req.scope_id, account_id)
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_FeatureEntitlementTable" WHERE account_id = $1 AND domain = $2 AND feature_code = $3 AND scope_type = $4 AND scope_id = $5 LIMIT 1',
        account_id,
        req.domain,
        req.feature_code,
        req.scope_type,
        req.scope_id,
    )
    row = await db.query_raw(
        'INSERT INTO "Alchemi_FeatureEntitlementTable" (id, account_id, domain, feature_code, scope_type, scope_id, enabled, config_json, created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) '
        'ON CONFLICT (account_id, domain, feature_code, scope_type, scope_id) DO UPDATE SET enabled = EXCLUDED.enabled, config_json = EXCLUDED.config_json RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.domain,
        req.feature_code,
        req.scope_type,
        req.scope_id,
        req.enabled,
        Json(req.config_json),
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="upsert",
            table_name="Alchemi_FeatureEntitlementTable",
            object_id=str(_row_get(item, "id")),
            before_value=_to_jsonable(dict(existing[0])) if existing else None,
            updated_values=_to_jsonable(dict(item)),
            domain=req.domain,
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/features/entitlements")
async def list_feature_entitlements(
    domain: str = Query(pattern="^(console|copilot)$"),
    feature_code: Optional[str] = None,
):
    account_id = require_domain_admin(domain)
    db = await _db()
    if feature_code:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_FeatureEntitlementTable" WHERE account_id = $1 AND domain = $2 AND feature_code = $3 ORDER BY created_at DESC',
            account_id,
            domain,
            feature_code,
        )
    else:
        rows = await db.query_raw(
            'SELECT * FROM "Alchemi_FeatureEntitlementTable" WHERE account_id = $1 AND domain = $2 ORDER BY created_at DESC',
            account_id,
            domain,
        )
    return {"domain": domain, "items": rows}


@router.get("/audit")
async def get_audit(domain: str = Query(default="all", pattern="^(console|copilot|all)$"), limit: int = 100, offset: int = 0):
    account_id = require_account_admin()
    db = await _db()

    if domain == "all":
        rows = await db.query_raw(
            'SELECT * FROM "LiteLLM_AuditLog" WHERE account_id = $1 ORDER BY updated_at DESC LIMIT $2 OFFSET $3',
            account_id,
            limit,
            offset,
        )
    else:
        rows = await db.query_raw(
            'SELECT * FROM "LiteLLM_AuditLog" WHERE account_id = $1 AND COALESCE((updated_values::jsonb->>\'domain\'),(changed_values::jsonb->>\'domain\')) = $2 ORDER BY updated_at DESC LIMIT $3 OFFSET $4',
            account_id,
            domain,
            limit,
            offset,
        )

    return {"domain": domain, "items": rows}


@router.get("/costs/breakdown")
async def get_cost_breakdown(
    domain: str = Query(default="copilot", pattern="^(console|copilot)$"),
    org_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    account_id = require_domain_admin(domain)
    db = await _db()

    where = 'account_id = $1'
    params: List[Any] = [account_id]
    idx = 2
    if org_id:
        where += f' AND org_id = ${idx}'
        params.append(org_id)
        idx += 1
    if team_id:
        where += f' AND team_id = ${idx}'
        params.append(team_id)
        idx += 1
    if user_id:
        where += f' AND user_id = ${idx}'
        params.append(user_id)

    rows = await db.query_raw(
        f'SELECT model_name, agent_id, connection_id, guardrail_code, SUM(raw_cost) as raw_cost, SUM(credits_incurred) as credits_incurred FROM "Alchemi_CopilotUsageLedgerTable" WHERE {where} GROUP BY model_name, agent_id, connection_id, guardrail_code ORDER BY SUM(credits_incurred) DESC',
        *params,
    )
    return {"domain": domain, "items": rows}


@router.get("/copilot/guardrails/effective")
async def get_effective_guardrails(
    org_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if org_id:
        await _ensure_domain_scope_exists(db, "copilot", "org", org_id, account_id)
    if team_id:
        await _ensure_domain_scope_exists(db, "copilot", "team", team_id, account_id)
    if user_id:
        await _ensure_domain_scope_exists(db, "copilot", "user", user_id, account_id)
    if agent_id:
        await _ensure_copilot_agent_exists(db, account_id, agent_id)

    chain = _scope_chain(org_id, team_id, user_id)
    if agent_id:
        chain.insert(0, ("agent", agent_id))

    items: List[Dict[str, Any]] = []
    for scope_type, scope_id in chain:
        rows = await db.query_raw(
            'SELECT a.scope_type, a.scope_id, p.id as preset_id, p.code, p.name, p.preset_json '
            'FROM "Alchemi_CopilotGuardrailAssignmentTable" a '
            'JOIN "Alchemi_CopilotGuardrailPresetTable" p ON p.id = a.preset_id '
            'WHERE a.account_id = $1 AND a.scope_type = $2 AND a.scope_id = $3',
            account_id,
            scope_type,
            scope_id,
        )
        for r in rows:
            item = dict(r)
            item["source_scope_type"] = scope_type
            item["source_scope_id"] = scope_id
            items.append(item)

    return {"items": items, "resolution_order": [{"scope_type": s, "scope_id": i} for s, i in chain]}


async def _resolve_effective_model_access(
    domain: str,
    model_name: str,
    org_id: Optional[str],
    team_id: Optional[str],
    user_id: Optional[str],
) -> Dict[str, Any]:
    account_id = require_domain_admin(domain)
    db = await _db()
    if org_id:
        await _ensure_domain_scope_exists(db, domain, "org", org_id, account_id)
    if team_id:
        await _ensure_domain_scope_exists(db, domain, "team", team_id, account_id)
    if user_id:
        await _ensure_domain_scope_exists(db, domain, "user", user_id, account_id)

    chain = _scope_chain(org_id, team_id, user_id)
    for scope_type, scope_id in chain:
        rows = await db.query_raw(
            'SELECT id, access_mode, scope_type, scope_id, created_at '
            'FROM "Alchemi_ModelGrantTable" '
            'WHERE account_id = $1 AND domain = $2 AND model_name = $3 AND scope_type = $4 AND scope_id = $5 '
            'ORDER BY created_at DESC',
            account_id,
            domain,
            model_name,
            scope_type,
            scope_id,
        )
        if rows:
            denies = [r for r in rows if _row_get(r, "access_mode") == "deny"]
            winner = denies[0] if denies else rows[0]
            mode = _row_get(winner, "access_mode")
            return {
                "model_name": model_name,
                "effective_access": mode,
                "allowed": mode == "allow",
                "resolved_from": {"scope_type": scope_type, "scope_id": scope_id},
                "candidates": rows,
                "resolution_order": [{"scope_type": s, "scope_id": i} for s, i in chain],
            }

    return {
        "model_name": model_name,
        "effective_access": "deny",
        "allowed": False,
        "resolved_from": None,
        "candidates": [],
        "resolution_order": [{"scope_type": s, "scope_id": i} for s, i in chain],
    }


@router.get("/copilot/models/effective")
async def get_effective_copilot_model_access(
    model_name: str,
    org_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    return await _resolve_effective_model_access("copilot", model_name, org_id, team_id, user_id)


@router.get("/console/models/effective")
async def get_effective_console_model_access(
    model_name: str,
    org_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    return await _resolve_effective_model_access("console", model_name, org_id, team_id, user_id)


@router.get("/features/effective")
async def get_effective_feature_entitlement(
    domain: str = Query(pattern="^(console|copilot)$"),
    feature_code: str = Query(min_length=1),
    org_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    account_id = require_domain_admin(domain)
    db = await _db()
    if org_id:
        await _ensure_domain_scope_exists(db, domain, "org", org_id, account_id)
    if team_id:
        await _ensure_domain_scope_exists(db, domain, "team", team_id, account_id)
    if user_id:
        await _ensure_domain_scope_exists(db, domain, "user", user_id, account_id)

    chain = _scope_chain(org_id, team_id, user_id)
    for scope_type, scope_id in chain:
        rows = await db.query_raw(
            'SELECT id, enabled, config_json, scope_type, scope_id, created_at '
            'FROM "Alchemi_FeatureEntitlementTable" '
            'WHERE account_id = $1 AND domain = $2 AND feature_code = $3 AND scope_type = $4 AND scope_id = $5 '
            'ORDER BY created_at DESC',
            account_id,
            domain,
            feature_code,
            scope_type,
            scope_id,
        )
        if rows:
            winner = rows[0]
            return {
                "domain": domain,
                "feature_code": feature_code,
                "effective_enabled": bool(_row_get(winner, "enabled")),
                "effective_config": _row_get(winner, "config_json", {}) or {},
                "resolved_from": {"scope_type": scope_type, "scope_id": scope_id},
                "candidates": rows,
                "resolution_order": [{"scope_type": s, "scope_id": i} for s, i in chain],
            }

    return {
        "domain": domain,
        "feature_code": feature_code,
        "effective_enabled": False,
        "effective_config": {},
        "resolved_from": None,
        "candidates": [],
        "resolution_order": [{"scope_type": s, "scope_id": i} for s, i in chain],
    }


@router.get("/copilot/marketplace")
async def list_copilot_marketplace(
    published_only: bool = False,
    title: Optional[str] = None,
    entity_type: Optional[str] = None,
    include_grants: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    account_id = require_domain_admin("copilot")
    db = await _db()
    where = "account_id = $1"
    params: List[Any] = [account_id]
    idx = 2
    if published_only:
        where += f" AND is_published = ${idx}"
        params.append(True)
        idx += 1
    if title:
        where += f" AND title ILIKE ${idx}"
        params.append(f"%{title}%")
        idx += 1
    if entity_type:
        where += f" AND entity_type = ${idx}"
        params.append(entity_type)
        idx += 1
    rows = await db.query_raw(
        f'SELECT * FROM "Alchemi_CopilotMarketplaceTable" WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}',
        *params,
        limit,
        offset,
    )
    total_rows = await db.query_raw(
        f'SELECT COUNT(*)::int AS count FROM "Alchemi_CopilotMarketplaceTable" WHERE {where}',
        *params,
    )
    total = int(_row_get(total_rows[0], "count", 0) or 0) if total_rows else 0
    items = rows
    if include_grants:
        enriched: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["grants"] = await _list_marketplace_grants(db, account_id, str(_row_get(row, "id")))
            enriched.append(item)
        items = enriched
    return {"items": items, "total": total}


@router.post("/copilot/marketplace")
async def create_copilot_marketplace(req: CopilotMarketplaceRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if not req.entity_type.strip() or not req.entity_id.strip() or not req.title.strip():
        raise HTTPException(status_code=400, detail="entity_type, entity_id, and title are required")
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND entity_type = $2 AND entity_id = $3 LIMIT 1',
        account_id,
        req.entity_type,
        req.entity_id,
    )
    if existing:
        ex = existing[0]
        current_is_featured = bool(_row_get(ex, "is_featured", False))
        current_is_verified = bool(_row_get(ex, "is_verified", False))
        current_pricing_model = _row_get(ex, "pricing_model", "free")
        current_version = _row_get(ex, "version", "1.0.0")
        current_author = _row_get(ex, "author")
        current_installation_count = int(_row_get(ex, "installation_count", 0) or 0)
        current_rating_avg = float(_row_get(ex, "rating_avg", 0) or 0)
        current_rating_count = int(_row_get(ex, "rating_count", 0) or 0)
        row = await db.query_raw(
            'UPDATE "Alchemi_CopilotMarketplaceTable" '
            'SET title = $1, description = $2, is_published = $3, is_featured = $4, is_verified = $5, pricing_model = $6, version = $7, author = $8, installation_count = $9, rating_avg = $10, rating_count = $11, updated_at = CURRENT_TIMESTAMP '
            'WHERE account_id = $12 AND id = $13 RETURNING *',
            req.title,
            req.description,
            req.is_published,
            req.is_featured if req.is_featured is not None else current_is_featured,
            req.is_verified if req.is_verified is not None else current_is_verified,
            req.pricing_model or current_pricing_model,
            req.version or current_version,
            req.author if req.author is not None else current_author,
            req.installation_count if req.installation_count is not None else current_installation_count,
            req.rating_avg if req.rating_avg is not None else current_rating_avg,
            req.rating_count if req.rating_count is not None else current_rating_count,
            account_id,
            _row_get(existing[0], "id"),
        )
        item = row[0] if row else None
        updated_grants = await _set_marketplace_grants(db, account_id, str(_row_get(existing[0], "id")), req.grants)
        if item:
            item = {**dict(item), "grants": updated_grants}
            await _audit_event(
                db=db,
                action="update",
                table_name="Alchemi_CopilotMarketplaceTable",
                object_id=str(_row_get(item, "id")),
                before_value=_to_jsonable(dict(existing[0])),
                updated_values={**_to_jsonable(dict(item)), "grants": updated_grants},
                domain="copilot",
                changed_by="account_admin",
            )
        return {"item": item}
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotMarketplaceTable" '
        '(id, account_id, entity_type, entity_id, title, description, is_published, is_featured, is_verified, pricing_model, version, author, installation_count, rating_avg, rating_count, created_by) '
        'VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) RETURNING *',
        str(uuid.uuid4()),
        account_id,
        req.entity_type,
        req.entity_id,
        req.title,
        req.description,
        req.is_published,
        req.is_featured,
        req.is_verified,
        req.pricing_model,
        req.version,
        req.author,
        req.installation_count,
        req.rating_avg,
        req.rating_count,
        "account_admin",
    )
    item = row[0] if row else None
    created_grants = await _set_marketplace_grants(db, account_id, str(_row_get(item, "id")), req.grants) if item else []
    if item:
        item = {**dict(item), "grants": created_grants}
        await _audit_event(
            db=db,
            action="create",
            table_name="Alchemi_CopilotMarketplaceTable",
            object_id=str(_row_get(item, "id")),
            before_value=None,
            updated_values={**_to_jsonable(dict(item)), "grants": created_grants},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/marketplace/discover")
async def discover_copilot_marketplace(
    org_id: Optional[str] = None,
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
    title: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    account_id = require_domain_admin("copilot")
    db = await _db()
    if org_id:
        await _ensure_domain_scope_exists(db, "copilot", "org", org_id, account_id)
    if team_id:
        await _ensure_domain_scope_exists(db, "copilot", "team", team_id, account_id)
    if user_id:
        await _ensure_domain_scope_exists(db, "copilot", "user", user_id, account_id)

    where = "account_id = $1 AND is_published = TRUE"
    params: List[Any] = [account_id]
    idx = 2
    if title:
        where += f" AND title ILIKE ${idx}"
        params.append(f"%{title}%")
        idx += 1
    if entity_type:
        where += f" AND entity_type = ${idx}"
        params.append(entity_type)
        idx += 1
    rows = await db.query_raw(
        f'SELECT * FROM "Alchemi_CopilotMarketplaceTable" WHERE {where} ORDER BY created_at DESC',
        *params,
    )
    if not rows:
        return {"items": [], "total": 0}

    marketplace_ids = [str(_row_get(r, "id")) for r in rows]
    grant_rows = await db.query_raw(
        'SELECT marketplace_id, scope_type, scope_id FROM "Alchemi_CopilotMarketplaceGrantTable" WHERE account_id = $1 AND marketplace_id = ANY($2::text[])',
        account_id,
        marketplace_ids,
    )
    grants_by_marketplace: Dict[str, List[Dict[str, str]]] = {}
    for grant in grant_rows:
        mid = str(_row_get(grant, "marketplace_id"))
        grants_by_marketplace.setdefault(mid, []).append(
            {
                "scope_type": str(_row_get(grant, "scope_type")),
                "scope_id": str(_row_get(grant, "scope_id")),
            }
        )

    scope_chain: set[str] = set()
    if org_id:
        scope_chain.add(f"org:{org_id}")
    if team_id:
        scope_chain.add(f"team:{team_id}")
    if user_id:
        scope_chain.add(f"user:{user_id}")

    visible_items: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        listing_id = str(_row_get(row, "id"))
        grants = grants_by_marketplace.get(listing_id, [])
        if not grants:
            item["visibility"] = {"mode": "global", "matched_scope": "global"}
            visible_items.append(item)
            continue
        matched_scope: Optional[str] = None
        for grant in grants:
            scope_key = f"{grant['scope_type']}:{grant['scope_id']}"
            if scope_key in scope_chain:
                matched_scope = scope_key
                break
        if matched_scope:
            item["visibility"] = {"mode": "granted", "matched_scope": matched_scope}
            visible_items.append(item)

    total = len(visible_items)
    paged_items = visible_items[offset : offset + limit]
    return {"items": paged_items, "total": total}


@router.post("/copilot/marketplace/{marketplace_id}/grants")
async def upsert_copilot_marketplace_grant(marketplace_id: str, req: CopilotMarketplaceGrantRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    _validate_scope_type(req.scope_type, {"org", "team", "user"})
    await _ensure_domain_scope_exists(db, "copilot", req.scope_type, req.scope_id, account_id)
    existing_listing = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        marketplace_id,
    )
    if not existing_listing:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")
    existing_grant = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotMarketplaceGrantTable" WHERE account_id = $1 AND marketplace_id = $2 AND scope_type = $3 AND scope_id = $4 LIMIT 1',
        account_id,
        marketplace_id,
        req.scope_type,
        req.scope_id,
    )
    row = await db.query_raw(
        'INSERT INTO "Alchemi_CopilotMarketplaceGrantTable" (id, account_id, marketplace_id, scope_type, scope_id, created_by) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (marketplace_id, scope_type, scope_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP RETURNING *',
        str(uuid.uuid4()),
        account_id,
        marketplace_id,
        req.scope_type,
        req.scope_id,
        "account_admin",
    )
    item = row[0] if row else None
    if item:
        await _audit_event(
            db=db,
            action="upsert",
            table_name="Alchemi_CopilotMarketplaceGrantTable",
            object_id=str(_row_get(item, "id")),
            before_value=_to_jsonable(dict(existing_grant[0])) if existing_grant else None,
            updated_values=_to_jsonable(dict(item)),
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.get("/copilot/marketplace/{marketplace_id}/grants")
async def list_copilot_marketplace_grants(marketplace_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    existing_listing = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        marketplace_id,
    )
    if not existing_listing:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotMarketplaceGrantTable" WHERE account_id = $1 AND marketplace_id = $2 ORDER BY created_at DESC',
        account_id,
        marketplace_id,
    )
    return {"items": rows}


@router.delete("/copilot/marketplace/{marketplace_id}/grants")
async def delete_copilot_marketplace_grants(
    marketplace_id: str,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
):
    account_id = require_domain_admin("copilot")
    db = await _db()
    existing_listing = await db.query_raw(
        'SELECT id FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        marketplace_id,
    )
    if not existing_listing:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")
    if bool(scope_type) ^ bool(scope_id):
        raise HTTPException(status_code=400, detail="scope_type and scope_id must be provided together")
    if scope_type:
        _validate_scope_type(scope_type, {"org", "team", "user"})
        rows = await db.query_raw(
            'DELETE FROM "Alchemi_CopilotMarketplaceGrantTable" WHERE account_id = $1 AND marketplace_id = $2 AND scope_type = $3 AND scope_id = $4 RETURNING *',
            account_id,
            marketplace_id,
            scope_type,
            scope_id,
        )
    else:
        rows = await db.query_raw(
            'DELETE FROM "Alchemi_CopilotMarketplaceGrantTable" WHERE account_id = $1 AND marketplace_id = $2 RETURNING *',
            account_id,
            marketplace_id,
        )
    if rows:
        await _audit_event(
            db=db,
            action="delete",
            table_name="Alchemi_CopilotMarketplaceGrantTable",
            object_id=marketplace_id,
            before_value={"deleted_count": len(rows)},
            updated_values={"deleted_count": len(rows), "scope_type": scope_type, "scope_id": scope_id},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"deleted": len(rows)}


@router.get("/copilot/marketplace/{marketplace_id}")
async def get_copilot_marketplace_item(marketplace_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        marketplace_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")
    item = dict(rows[0])
    item["grants"] = await _list_marketplace_grants(db, account_id, marketplace_id)
    return {"item": item}


@router.patch("/copilot/marketplace/{marketplace_id}")
async def update_copilot_marketplace_item(marketplace_id: str, req: CopilotMarketplaceUpdateRequest):
    account_id = require_domain_admin("copilot")
    db = await _db()
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        marketplace_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")
    ex = existing[0]
    title = req.title if req.title is not None else _row_get(ex, "title")
    description = req.description if req.description is not None else _row_get(ex, "description")
    is_published = req.is_published if req.is_published is not None else bool(_row_get(ex, "is_published"))
    is_featured = req.is_featured if req.is_featured is not None else bool(_row_get(ex, "is_featured", False))
    is_verified = req.is_verified if req.is_verified is not None else bool(_row_get(ex, "is_verified", False))
    pricing_model = req.pricing_model if req.pricing_model is not None else _row_get(ex, "pricing_model", "free")
    version = req.version if req.version is not None else _row_get(ex, "version", "1.0.0")
    author = req.author if req.author is not None else _row_get(ex, "author")
    installation_count = req.installation_count if req.installation_count is not None else int(_row_get(ex, "installation_count", 0) or 0)
    rating_avg = req.rating_avg if req.rating_avg is not None else float(_row_get(ex, "rating_avg", 0) or 0)
    rating_count = req.rating_count if req.rating_count is not None else int(_row_get(ex, "rating_count", 0) or 0)
    row = await db.query_raw(
        'UPDATE "Alchemi_CopilotMarketplaceTable" '
        'SET title = $1, description = $2, is_published = $3, is_featured = $4, is_verified = $5, pricing_model = $6, version = $7, author = $8, installation_count = $9, rating_avg = $10, rating_count = $11, updated_at = CURRENT_TIMESTAMP '
        'WHERE account_id = $12 AND id = $13 RETURNING *',
        title,
        description,
        is_published,
        is_featured,
        is_verified,
        pricing_model,
        version,
        author,
        installation_count,
        rating_avg,
        rating_count,
        account_id,
        marketplace_id,
    )
    updated_grants = await _set_marketplace_grants(db, account_id, marketplace_id, req.grants) if req.grants is not None else await _list_marketplace_grants(db, account_id, marketplace_id)
    item = row[0] if row else None
    if item:
        item = {**dict(item), "grants": updated_grants}
        await _audit_event(
            db=db,
            action="update",
            table_name="Alchemi_CopilotMarketplaceTable",
            object_id=marketplace_id,
            before_value=_to_jsonable(dict(ex)),
            updated_values={**_to_jsonable(dict(item)), "grants": updated_grants},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"item": item}


@router.post("/copilot/marketplace/{marketplace_id}/publish")
async def publish_copilot_marketplace_item(marketplace_id: str, publish: bool = True):
    account_id = require_domain_admin("copilot")
    db = await _db()
    existing = await db.query_raw(
        'SELECT * FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND id = $2 LIMIT 1',
        account_id,
        marketplace_id,
    )
    row = await db.query_raw(
        'UPDATE "Alchemi_CopilotMarketplaceTable" SET is_published = $1 WHERE account_id = $2 AND id = $3 RETURNING *',
        publish,
        account_id,
        marketplace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Marketplace listing not found")
    await _audit_event(
        db=db,
        action="update",
        table_name="Alchemi_CopilotMarketplaceTable",
        object_id=marketplace_id,
        before_value=_to_jsonable(dict(existing[0])) if existing else None,
        updated_values=_to_jsonable(dict(row[0])),
        domain="copilot",
        changed_by="account_admin",
    )
    return {"item": row[0]}


@router.delete("/copilot/marketplace/{marketplace_id}")
async def delete_copilot_marketplace_item(marketplace_id: str):
    account_id = require_domain_admin("copilot")
    db = await _db()
    rows = await db.query_raw(
        'DELETE FROM "Alchemi_CopilotMarketplaceTable" WHERE account_id = $1 AND id = $2 RETURNING *',
        account_id,
        marketplace_id,
    )
    if rows:
        await _audit_event(
            db=db,
            action="delete",
            table_name="Alchemi_CopilotMarketplaceTable",
            object_id=marketplace_id,
            before_value=_to_jsonable(dict(rows[0])),
            updated_values={"id": marketplace_id},
            domain="copilot",
            changed_by="account_admin",
        )
    return {"deleted": bool(rows)}
