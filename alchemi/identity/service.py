import json
import os
import re
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from alchemi.control_plane.service import (
    ensure_account_membership,
    ensure_product_grant,
    ensure_role_binding,
    get_account_by_id,
    get_account_identity_binding,
    get_account_by_zitadel_org_id,
    upsert_account,
    upsert_control_plane_user,
    upsert_identity_binding,
)
from alchemi.identity.zitadel_client import (
    ZitadelAPIError,
    ZitadelClient,
    ZitadelConfigurationError,
)


def _coerce_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "account"


def _split_name(display_name: Optional[str], email: str) -> Tuple[str, str, str]:
    if display_name:
        parts = [part for part in display_name.strip().split(" ") if part]
    else:
        parts = []

    if not parts:
        local = email.split("@", 1)[0]
        parts = [local]

    given_name = parts[0]
    family_name = " ".join(parts[1:]) or "User"
    resolved_display_name = display_name or " ".join(parts)
    return given_name, family_name, resolved_display_name


def _generate_temp_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(ch.islower() for ch in candidate)
            and any(ch.isupper() for ch in candidate)
            and any(ch.isdigit() for ch in candidate)
            and any(ch in "!@#$%^&*()-_=+" for ch in candidate)
        ):
            return candidate


def _normalize_domain(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized.startswith("*."):
        normalized = normalized[2:]
    return normalized or None


def _merge_dict(base: Optional[Dict[str, Any]], update: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (update or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _console_scope(org_id: Optional[str]) -> str:
    scope = ["openid", "email", "profile"]
    if org_id:
        scope.append(f"urn:zitadel:iam:org:id:{org_id}")
    return " ".join(scope)


def _zitadel_console_url(org_id: Optional[str] = None) -> Optional[str]:
    explicit = os.getenv("ALCHEMI_ZITADEL_CONSOLE_URL")
    issuer = (
        os.getenv("ALCHEMI_ZITADEL_API_URL")
        or os.getenv("ALCHEMI_ZITADEL_ISSUER")
        or os.getenv("ZITADEL_ISSUER")
        or os.getenv("ZITADEL_ISSUER_URL")
    )
    base = explicit or (f"{issuer.rstrip('/')}/ui/console" if issuer else None)
    if not base:
        return None
    if org_id:
        return f"{base.rstrip('/')}/organizations/{org_id}"
    return base


def _management_available() -> bool:
    try:
        client = ZitadelClient.from_env()
        return client.configured
    except ZitadelConfigurationError:
        return False


def _login_mode_to_policy(login_mode: Optional[str]) -> Tuple[bool, bool]:
    normalized = str(login_mode or "hybrid").strip().lower()
    if normalized == "local_only":
        return True, False
    if normalized == "federated_only":
        return False, True
    return True, True


def _policy_to_login_mode(
    *,
    allow_username_password: bool,
    allow_external_idp: bool,
) -> str:
    if allow_username_password and not allow_external_idp:
        return "local_only"
    if allow_external_idp and not allow_username_password:
        return "federated_only"
    return "hybrid"


def _merge_provider_entry(
    providers: list[Dict[str, Any]],
    entry: Dict[str, Any],
) -> list[Dict[str, Any]]:
    updated: list[Dict[str, Any]] = []
    matched = False
    entry_id = entry.get("idp_id")
    for provider in providers:
        provider_id = provider.get("idp_id")
        same_provider = False
        if entry_id and provider_id:
            same_provider = provider_id == entry_id
        elif provider.get("name") and entry.get("name"):
            same_provider = (
                provider.get("type") == entry.get("type")
                and str(provider.get("name")).lower() == str(entry.get("name")).lower()
            )
        if same_provider:
            updated.append(_merge_dict(provider, entry))
            matched = True
        else:
            updated.append(provider)
    if not matched:
        updated.append(entry)
    return updated


async def _ensure_zitadel_user_grants(
    client: ZitadelClient,
    *,
    user_id: str,
    product_grants: List[str],
) -> List[str]:
    warnings: List[str] = []
    env_map = {
        "console": "ALCHEMI_ZITADEL_CONSOLE_PROJECT_ID",
        "copilot": "ALCHEMI_ZITADEL_COPILOT_PROJECT_ID",
    }
    for product_code in sorted(set(product_grants)):
        project_env = env_map.get(product_code)
        if not project_env:
            continue
        project_id = os.getenv(project_env)
        if not project_id:
            continue
        try:
            await client.add_user_grant(user_id=user_id, project_id=project_id)
        except ZitadelAPIError as exc:
            warnings.append(f"{product_code} user grant: {exc}")
    return warnings


def management_status() -> Dict[str, Any]:
    try:
        client = ZitadelClient.from_env()
        return {
            "configured": client.configured,
            "issuer": client.issuer,
            "mode": "pat" if client.pat else "client_credentials",
            "console_url": _zitadel_console_url(),
        }
    except ZitadelConfigurationError as exc:
        return {
            "configured": False,
            "issuer": (
                os.getenv("ALCHEMI_ZITADEL_API_URL")
                or os.getenv("ALCHEMI_ZITADEL_ISSUER")
                or os.getenv("ZITADEL_ISSUER")
                or os.getenv("ZITADEL_ISSUER_URL")
            ),
            "mode": None,
            "error": str(exc),
            "console_url": _zitadel_console_url(),
        }


async def list_available_zitadel_organizations() -> List[Dict[str, Any]]:
    client = ZitadelClient.from_env()
    return await client.list_organizations()


async def sync_zitadel_organizations_to_accounts(
    prisma_client,
    *,
    actor: str,
) -> List[Dict[str, Any]]:
    client = ZitadelClient.from_env()
    organizations = await client.list_organizations()
    synced_accounts: List[Dict[str, Any]] = []

    for organization in organizations:
        org_id = str(organization.get("organization_id") or "").strip()
        if not org_id:
            continue

        state = str(organization.get("state") or "")
        if state and state != "ORG_STATE_ACTIVE":
            continue

        existing = await get_account_by_zitadel_org_id(prisma_client, org_id)
        account_name = str(organization.get("name") or org_id).strip()
        account_alias = existing.get("account_alias") if existing else None
        max_budget = existing.get("max_budget") if existing else None
        status = "active"
        metadata = _merge_dict(
            existing.get("metadata") if existing else {},
            {
                "source": "zitadel_sync",
                "zitadel_org_id": org_id,
                "zitadel_state": state,
                "zitadel_sync": {
                    "organization_id": org_id,
                    "organization_name": account_name,
                    "primary_domain": _normalize_domain(organization.get("primary_domain")),
                    "state": state,
                    "synced_at": datetime.now(UTC).isoformat(),
                },
            },
        )

        account = await upsert_account(
            prisma_client,
            account_id=existing.get("account_id") if existing else None,
            account_name=account_name,
            account_alias=account_alias,
            domain=_normalize_domain(organization.get("primary_domain")),
            max_budget=max_budget,
            metadata=metadata,
            status=status,
            actor=actor,
        )
        synced_accounts.append(account)

    return synced_accounts


async def link_existing_account_directory(
    prisma_client,
    *,
    account_id: str,
    zitadel_org_id: str,
    admin_user_id: Optional[str],
    admin_user_email: Optional[str],
    admin_display_name: Optional[str],
    membership_role: str,
    product_grants: List[str],
    actor: str,
) -> Dict[str, Any]:
    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise ValueError("Account not found")

    client = ZitadelClient.from_env()
    org = await client.get_organization(org_id=zitadel_org_id)
    org_id = org.get("organization_id")
    if not org_id:
        raise ValueError("Zitadel organization not found")

    if not admin_user_id and not admin_user_email:
        raise ValueError("Provide an admin user id or admin user email.")

    if admin_user_id:
        user = await client.get_user_by_id(user_id=admin_user_id)
        if str(user.get("resource_owner") or "") != str(org_id):
            raise ValueError("The supplied admin user does not belong to the selected Zitadel organization.")
    else:
        users = await client.search_users_by_email(email=str(admin_user_email), org_id=org_id)
        if len(users) != 1:
            raise ValueError("Expected exactly one tenant admin user in the selected Zitadel organization for this email.")
        user = users[0]

    resolved_user_id = user.get("user_id")
    resolved_email = str(user.get("email") or admin_user_email or "").strip().lower()
    if not resolved_user_id or not resolved_email:
        raise ValueError("Unable to resolve the tenant admin identity from Zitadel.")

    warnings: List[str] = []
    try:
        await client.add_org_member(org_id=org_id, user_id=resolved_user_id, roles=["ORG_OWNER"])
    except ZitadelAPIError as exc:
        if exc.status_code == 409:
            warnings.append("The selected tenant admin is already an organization owner in Zitadel.")
        else:
            raise

    for project_env in (
        "ALCHEMI_ZITADEL_CONSOLE_PROJECT_ID",
        "ALCHEMI_ZITADEL_COPILOT_PROJECT_ID",
    ):
        project_id = os.getenv(project_env)
        if not project_id:
            continue
        try:
            await client.add_project_grant(project_id=project_id, granted_org_id=org_id)
        except ZitadelAPIError as exc:
            warnings.append(f"{project_env}: {exc}")

    synced = await _sync_member_access(
        prisma_client,
        account_id=account_id,
        user_email=resolved_email,
        display_name=admin_display_name or user.get("display_name") or resolved_email,
        zitadel_sub=resolved_user_id,
        membership_role=membership_role,
        product_grants=product_grants,
        actor=actor,
    )
    warnings.extend(
        await _ensure_zitadel_user_grants(
            client,
            user_id=resolved_user_id,
            product_grants=product_grants,
        )
    )

    existing_binding = await get_account_identity_binding(prisma_client, account_id)
    defaults = _default_identity_binding(org_id=org_id, existing_binding=existing_binding)
    config = _merge_dict(
        _coerce_json(existing_binding.get("config")) if existing_binding else {},
        _merge_dict(
            defaults["config"],
            {
                "directory": {
                    "managed_via_console": False,
                    "managed_in_zitadel": True,
                    "bootstrap_login": "zitadel_managed",
                },
                "management": {
                    "console_url": _zitadel_console_url(org_id),
                    "owner_model": "zitadel_org_owner",
                },
            },
        ),
    )
    metadata = _merge_dict(
        _coerce_json(existing_binding.get("metadata")) if existing_binding else {},
        {
            "directory": {
                "bootstrap_status": "linked",
                "provider_status": "managed_in_zitadel",
                "linked_by": actor,
                "linked_at": datetime.now(UTC).isoformat(),
                "tenant_admin_email": resolved_email,
                "tenant_admin_user_id": resolved_user_id,
            }
        },
    )

    binding = await upsert_identity_binding(
        prisma_client,
        account_id=account_id,
        provider=defaults["provider"],
        zitadel_org_id=org_id,
        issuer_url=defaults["issuer_url"],
        client_id=defaults["client_id"],
        default_redirect_url=defaults["default_redirect_url"],
        sso_enabled=defaults["sso_enabled"],
        config=config,
        metadata=metadata,
        actor=actor,
    )

    primary_domain = _normalize_domain(org.get("primary_domain"))
    if primary_domain and primary_domain != account.get("domain"):
        await upsert_account(
            prisma_client,
            account_id=account["account_id"],
            account_name=account["account_name"],
            account_alias=account.get("account_alias"),
            domain=primary_domain,
            max_budget=account.get("max_budget"),
            metadata=account.get("metadata"),
            status=account.get("status") or "active",
            actor=actor,
        )

    return {
        "identity_binding": binding,
        "organization": org,
        "tenant_admin": {
            "user_id": synced["user"]["user_id"],
            "user_email": synced["user"]["user_email"],
            "zitadel_sub": resolved_user_id,
            "display_name": synced["user"].get("display_name"),
        },
        "warnings": warnings,
    }


def _default_identity_binding(
    *,
    org_id: str,
    existing_binding: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    issuer = (
        os.getenv("ALCHEMI_ZITADEL_ISSUER")
        or os.getenv("ZITADEL_ISSUER")
        or os.getenv("ZITADEL_ISSUER_URL")
    )
    client_id = (
        os.getenv("ALCHEMI_ZITADEL_CLIENT_ID")
        or os.getenv("ZITADEL_CLIENT_ID")
    )
    callback_url = os.getenv("ZITADEL_CALLBACK_URL") or os.getenv("PROXY_BASE_URL")

    existing_config = _coerce_json(existing_binding.get("config")) if existing_binding else {}
    updated_config = _merge_dict(
        existing_config,
        {
            "generic_authorization_endpoint": f"{issuer.rstrip('/')}/oauth/v2/authorize" if issuer else None,
            "generic_token_endpoint": f"{issuer.rstrip('/')}/oauth/v2/token" if issuer else None,
            "generic_userinfo_endpoint": f"{issuer.rstrip('/')}/oidc/v1/userinfo" if issuer else None,
            "generic_scope": _console_scope(org_id),
            "generic_include_client_id": "false",
            "directory": {
                "managed_via_console": True,
                "bootstrap_login": "zitadel_local_password",
            },
        },
    )
    return {
        "provider": "zitadel",
        "zitadel_org_id": org_id,
        "issuer_url": issuer,
        "client_id": client_id,
        "default_redirect_url": callback_url,
        "sso_enabled": bool(issuer and client_id),
        "config": {key: value for key, value in updated_config.items() if value is not None},
    }


async def _sync_member_access(
    prisma_client,
    *,
    account_id: str,
    user_email: str,
    display_name: str,
    zitadel_sub: Optional[str],
    membership_role: str,
    product_grants: List[str],
    actor: str,
) -> Dict[str, Any]:
    user = await upsert_control_plane_user(
        prisma_client,
        user_id=None,
        user_email=user_email,
        display_name=display_name,
        zitadel_sub=zitadel_sub,
        primary_account_id=account_id,
        metadata={"source": "identity-orchestrator"},
        actor=actor,
    )
    membership = await ensure_account_membership(
        prisma_client,
        account_id=account_id,
        user_id=user["user_id"],
        membership_role=membership_role,
        membership_status="active",
        is_default=False,
        metadata={"source": "identity-orchestrator"},
        actor=actor,
    )

    role_codes: List[str] = []
    if membership_role in {"owner", "admin", "account_admin"}:
        role_codes.append("account_admin")
    if membership_role == "owner":
        role_codes.append("account_owner")

    for role_code in sorted(set(role_codes)):
        await ensure_role_binding(
            prisma_client,
            account_id=account_id,
            principal_type="user",
            principal_id=user["user_id"],
            role_code=role_code,
            product_code=None,
            scope_type="account",
            scope_id=account_id,
            metadata={"source": "identity-orchestrator"},
            actor=actor,
        )

    for product_code in sorted(set(product_grants)):
        await ensure_product_grant(
            prisma_client,
            account_id=account_id,
            user_id=user["user_id"],
            product_code=product_code,
            grant_status="active",
            metadata={"source": "identity-orchestrator"},
            actor=actor,
        )

    return {"user": user, "membership": membership}


async def _sync_directory_settings(
    prisma_client,
    *,
    account_id: str,
    org_id: str,
    actor: str,
    primary_domain: Optional[str],
    secondary_domains: Optional[List[str]],
    login_mode: str,
    allow_register: bool,
    allow_domain_discovery: bool,
) -> Dict[str, Any]:
    existing_binding = await get_account_identity_binding(prisma_client, account_id)
    if existing_binding is None:
        raise ValueError("Directory must be bootstrapped before configuring settings.")

    client = ZitadelClient.from_env()
    current_domains = await client.search_org_domains(org_id=org_id)
    current_domain_names = {
        _normalize_domain(domain.get("domainName"))
        for domain in current_domains
        if _normalize_domain(domain.get("domainName"))
    }

    requested_primary = _normalize_domain(primary_domain)
    requested_secondary = [
        domain
        for domain in (_normalize_domain(value) for value in (secondary_domains or []))
        if domain and domain != requested_primary
    ]
    requested_domains = [domain for domain in [requested_primary, *requested_secondary] if domain]

    warnings: List[str] = []
    for domain in requested_domains:
        if domain in current_domain_names:
            continue
        try:
            await client.add_org_domain(org_id=org_id, domain=domain)
            current_domain_names.add(domain)
        except ZitadelAPIError as exc:
            warnings.append(f"domain {domain}: {exc}")

    if requested_primary:
        try:
            await client.set_primary_org_domain(org_id=org_id, domain=requested_primary)
        except ZitadelAPIError as exc:
            warnings.append(f"primary domain {requested_primary}: {exc}")

    allow_username_password, allow_external_idp = _login_mode_to_policy(login_mode)
    if login_mode == "federated_only":
        existing_config = _coerce_json(existing_binding.get("config"))
        providers = [
            provider
            for provider in existing_config.get("providers", [])
            if isinstance(provider, dict)
        ]
        if not providers and not _coerce_json(existing_config.get("provider")):
            raise ValueError(
                "Configure at least one external identity provider before switching to federated-only login."
            )

    await client.update_login_policy(
        org_id=org_id,
        allow_username_password=allow_username_password,
        allow_external_idp=allow_external_idp,
        allow_register=allow_register,
        allow_domain_discovery=allow_domain_discovery,
    )
    login_policy = await client.get_login_policy(org_id=org_id)

    config = _merge_dict(
        _coerce_json(existing_binding.get("config")),
        {
            "domains": {
                "primary_domain": requested_primary,
                "additional_domains": requested_secondary,
            },
            "directory": {
                "login_mode": _policy_to_login_mode(
                    allow_username_password=bool(login_policy.get("allowUsernamePassword")),
                    allow_external_idp=bool(login_policy.get("allowExternalIdp")),
                ),
                "allow_register": bool(login_policy.get("allowRegister")),
                "allow_domain_discovery": bool(login_policy.get("allowDomainDiscovery")),
            },
        },
    )
    metadata = _merge_dict(
        _coerce_json(existing_binding.get("metadata")),
        {
            "directory": {
                "settings_updated_at": datetime.now(UTC).isoformat(),
                "settings_updated_by": actor,
            }
        },
    )

    binding = await upsert_identity_binding(
        prisma_client,
        account_id=account_id,
        provider=existing_binding.get("provider") or "zitadel",
        zitadel_org_id=org_id,
        issuer_url=existing_binding.get("issuer_url"),
        client_id=existing_binding.get("client_id"),
        default_redirect_url=existing_binding.get("default_redirect_url"),
        sso_enabled=bool(existing_binding.get("sso_enabled")),
        config=config,
        metadata=metadata,
        actor=actor,
    )

    account = await get_account_by_id(prisma_client, account_id)
    if account is not None and requested_primary and requested_primary != account.get("domain"):
        await upsert_account(
            prisma_client,
            account_id=account["account_id"],
            account_name=account["account_name"],
            account_alias=account.get("account_alias"),
            domain=requested_primary,
            max_budget=account.get("max_budget"),
            metadata=account.get("metadata"),
            status=account.get("status") or "active",
            actor=actor,
        )

    return {
        "identity_binding": binding,
        "domains": requested_domains,
        "login_policy": login_policy,
        "warnings": warnings,
    }


async def bootstrap_account_directory(
    prisma_client,
    *,
    account_id: str,
    first_admin_email: str,
    first_admin_display_name: Optional[str],
    membership_role: str,
    bootstrap_mode: str,
    temporary_password: Optional[str],
    create_scim_service_user: bool,
    actor: str,
) -> Dict[str, Any]:
    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise ValueError("Account not found")

    client = ZitadelClient.from_env()
    existing_binding = await get_account_identity_binding(prisma_client, account_id)
    config = _coerce_json(existing_binding.get("config")) if existing_binding else {}
    metadata = _coerce_json(existing_binding.get("metadata")) if existing_binding else {}
    warnings: List[str] = []

    org_id = existing_binding.get("zitadel_org_id") if existing_binding else None
    if not org_id:
        try:
            org_response = await client.create_organization(name=account["account_name"])
            org_id = org_response.get("organization_id")
        except ZitadelAPIError as exc:
            if exc.status_code != 409:
                raise
            existing_orgs = await client.search_organizations_by_name(
                name=account["account_name"]
            )
            if len(existing_orgs) != 1:
                raise
            org_id = existing_orgs[0].get("organization_id")
            warnings.append(
                "Reused an existing Zitadel organization with the same tenant name."
            )
        if not org_id:
            raise ZitadelAPIError(
                "Zitadel organization creation did not return an organization_id."
            )

    for project_env in (
        "ALCHEMI_ZITADEL_CONSOLE_PROJECT_ID",
        "ALCHEMI_ZITADEL_COPILOT_PROJECT_ID",
    ):
        project_id = os.getenv(project_env)
        if not project_id:
            continue
        try:
            await client.add_project_grant(
                project_id=project_id,
                granted_org_id=org_id,
            )
        except ZitadelAPIError as exc:
            warnings.append(f"{project_env}: {exc}")

    given_name, family_name, resolved_display_name = _split_name(
        first_admin_display_name,
        first_admin_email,
    )
    existing_users = await client.search_users_by_email(email=first_admin_email)
    existing_in_org = [
        user
        for user in existing_users
        if str(user.get("resource_owner") or "") == str(org_id)
    ]
    if not existing_in_org:
        existing_in_org = await client.search_users_by_email(
            email=first_admin_email,
            org_id=org_id,
        )
    existing_in_other_orgs = [
        user
        for user in existing_users
        if str(user.get("resource_owner") or "") != str(org_id)
    ]
    if len(existing_in_org) > 1:
        raise ValueError(
            "Multiple existing directory users already use this email inside the tenant organization. Resolve the duplicate in Zitadel before bootstrapping this tenant."
        )
    if existing_in_other_orgs and not existing_in_org:
        raise ValueError(
            "This email already exists in another Zitadel organization. Choose a tenant admin who belongs to this account for the initial bootstrap, or add a future link/external-user-grant flow for the existing identity instead of creating a second password-based identity."
        )
    resolved_password = None
    invite_code = None
    if bootstrap_mode == "temporary_password":
        resolved_password = temporary_password or _generate_temp_password()

    if existing_in_org:
        zitadel_sub = existing_in_org[0].get("user_id")
    else:
        try:
            created_user = await client.create_human_user(
                org_id=org_id,
                email=first_admin_email,
                given_name=given_name,
                family_name=family_name,
                display_name=resolved_display_name,
                password=resolved_password,
            )
            zitadel_sub = created_user.get("user_id")
        except ZitadelAPIError as exc:
            if exc.status_code != 409:
                raise
            existing_in_org = await client.search_users_by_email(
                email=first_admin_email,
                org_id=org_id,
            )
            if len(existing_in_org) != 1:
                raise
            zitadel_sub = existing_in_org[0].get("user_id")
            warnings.append(
                "Reused an existing Zitadel user inside the tenant organization."
            )
    if not zitadel_sub:
        raise ZitadelAPIError("Zitadel did not return a user_id for the bootstrapped admin.")

    if bootstrap_mode != "temporary_password" and not existing_in_org:
        invite = await client.create_invite_code(user_id=zitadel_sub)
        invite_code = invite.get("invite_code")

    synced = await _sync_member_access(
        prisma_client,
        account_id=account_id,
        user_email=first_admin_email,
        display_name=resolved_display_name,
        zitadel_sub=zitadel_sub,
        membership_role=membership_role,
        product_grants=["console", "copilot"],
        actor=actor,
    )
    warnings.extend(
        await _ensure_zitadel_user_grants(
            client,
            user_id=zitadel_sub,
            product_grants=["console", "copilot"],
        )
    )

    identity_defaults = _default_identity_binding(org_id=org_id, existing_binding=existing_binding)
    config = _merge_dict(
        config,
        identity_defaults["config"],
    )
    metadata = _merge_dict(
        metadata,
        {
            "directory": {
                "bootstrap_status": "ready",
                "bootstrapped_by": actor,
                "bootstrapped_at": datetime.now(UTC).isoformat(),
                "first_admin_email": first_admin_email,
            }
        },
    )

    binding = await upsert_identity_binding(
        prisma_client,
        account_id=account_id,
        provider=identity_defaults["provider"],
        zitadel_org_id=org_id,
        issuer_url=identity_defaults["issuer_url"],
        client_id=identity_defaults["client_id"],
        default_redirect_url=identity_defaults["default_redirect_url"],
        sso_enabled=identity_defaults["sso_enabled"],
        config=config,
        metadata=metadata,
        actor=actor,
    )

    scim_result = None
    if create_scim_service_user:
        try:
            scim_result = await issue_scim_token(
                prisma_client,
                account_id=account_id,
                actor=actor,
            )
        except Exception as exc:  # pragma: no cover - best effort bootstrap
            warnings.append(f"SCIM bootstrap failed: {exc}")

    account_domain = _normalize_domain(account.get("domain"))
    if account_domain:
        try:
            settings_result = await _sync_directory_settings(
                prisma_client,
                account_id=account_id,
                org_id=org_id,
                actor=actor,
                primary_domain=account_domain,
                secondary_domains=[],
                login_mode="hybrid",
                allow_register=False,
                allow_domain_discovery=True,
            )
            warnings.extend(settings_result.get("warnings") or [])
        except Exception as exc:  # pragma: no cover - best effort bootstrap
            warnings.append(f"Directory settings bootstrap failed: {exc}")

    return {
        "identity_binding": binding,
        "org_id": org_id,
        "first_admin": {
            "user_id": synced["user"]["user_id"],
            "user_email": synced["user"]["user_email"],
            "zitadel_sub": zitadel_sub,
            "display_name": synced["user"].get("display_name"),
        },
        "bootstrap_mode": bootstrap_mode,
        "temporary_password": resolved_password,
        "invite_code": invite_code,
        "scim": scim_result,
        "warnings": warnings,
    }


async def configure_account_directory(
    prisma_client,
    *,
    account_id: str,
    actor: str,
    provider_type: str,
    provider_name: str,
    issuer: str,
    client_id: str,
    client_secret: str,
    scopes: List[str],
    auto_register: bool,
    group_claim: Optional[str],
    default_role: str,
    sync_mode: str,
) -> Dict[str, Any]:
    existing_binding = await get_account_identity_binding(prisma_client, account_id)
    if existing_binding is None or not existing_binding.get("zitadel_org_id"):
        raise ValueError("Directory must be bootstrapped before configuring SSO.")

    org_id = existing_binding["zitadel_org_id"]
    client = ZitadelClient.from_env()

    provider = await client.add_org_oidc_provider(
        org_id=org_id,
        name=provider_name,
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
        username_mapping="OIDC_MAPPING_FIELD_EMAIL",
        display_name_mapping="OIDC_MAPPING_FIELD_PREFERRED_USERNAME",
        auto_register=auto_register,
    )
    if provider.get("idp_id"):
        await client.add_idp_to_login_policy(
            org_id=org_id,
            idp_id=provider["idp_id"],
        )

    provider_entry = {
        "type": provider_type,
        "name": provider_name,
        "issuer": issuer,
        "client_id": client_id,
        "scopes": scopes,
        "group_claim": group_claim,
        "default_role": default_role,
        "sync_mode": sync_mode,
        "auto_register": auto_register,
        "idp_id": provider.get("idp_id"),
    }
    existing_config = _coerce_json(existing_binding.get("config"))
    existing_providers = [
        item for item in existing_config.get("providers", []) if isinstance(item, dict)
    ]
    merged_providers = _merge_provider_entry(existing_providers, provider_entry)

    config = _merge_dict(
        existing_config,
        {
            "provider": provider_entry,
            "providers": merged_providers,
        },
    )
    metadata = _merge_dict(
        _coerce_json(existing_binding.get("metadata")),
        {
            "directory": {
                "provider_status": "configured",
                "provider_configured_at": datetime.now(UTC).isoformat(),
                "provider_configured_by": actor,
            }
        },
    )

    return await upsert_identity_binding(
        prisma_client,
        account_id=account_id,
        provider=existing_binding.get("provider") or "zitadel",
        zitadel_org_id=org_id,
        issuer_url=existing_binding.get("issuer_url"),
        client_id=existing_binding.get("client_id"),
        default_redirect_url=existing_binding.get("default_redirect_url"),
        sso_enabled=True,
        config=config,
        metadata=metadata,
        actor=actor,
    )


async def configure_account_directory_settings(
    prisma_client,
    *,
    account_id: str,
    actor: str,
    primary_domain: Optional[str],
    additional_domains: List[str],
    login_mode: str,
    allow_register: bool,
    allow_domain_discovery: bool,
) -> Dict[str, Any]:
    existing_binding = await get_account_identity_binding(prisma_client, account_id)
    if existing_binding is None or not existing_binding.get("zitadel_org_id"):
        raise ValueError("Directory must be bootstrapped before configuring tenant login settings.")

    return await _sync_directory_settings(
        prisma_client,
        account_id=account_id,
        org_id=existing_binding["zitadel_org_id"],
        actor=actor,
        primary_domain=primary_domain,
        secondary_domains=additional_domains,
        login_mode=login_mode,
        allow_register=allow_register,
        allow_domain_discovery=allow_domain_discovery,
    )


async def issue_scim_token(
    prisma_client,
    *,
    account_id: str,
    actor: str,
    expiration_days: int = 365,
) -> Dict[str, Any]:
    existing_binding = await get_account_identity_binding(prisma_client, account_id)
    if existing_binding is None or not existing_binding.get("zitadel_org_id"):
        raise ValueError("Directory must be bootstrapped before SCIM can be configured.")

    org_id = existing_binding["zitadel_org_id"]
    client = ZitadelClient.from_env()
    config = _coerce_json(existing_binding.get("config"))
    scim_config = _coerce_json(config.get("scim"))
    machine_user_id = scim_config.get("machine_user_id")

    if not machine_user_id:
        account = await get_account_by_id(prisma_client, account_id)
        account_name = account["account_name"] if account else "account"
        machine = await client.create_machine_user(
            org_id=org_id,
            username=f"{_slugify(account_name)}-scim",
            name=f"{account_name} SCIM",
        )
        machine_user_id = machine.get("user_id")
        if not machine_user_id:
            raise ZitadelAPIError("Zitadel did not return a machine user id for SCIM bootstrap.")
        await client.add_org_member(
            org_id=org_id,
            user_id=machine_user_id,
            roles=["ORG_OWNER"],
        )

    expiration_date = (
        datetime.now(UTC) + timedelta(days=max(expiration_days, 1))
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    token_result = await client.add_personal_access_token(
        user_id=machine_user_id,
        token_name=f"{_slugify(account_id)}-scim",
        expiration_date=expiration_date,
    )

    scim_endpoint = f"{client.issuer}/scim/v2/{org_id}/Users"
    updated_config = _merge_dict(
        config,
        {
            "scim": {
                "enabled": True,
                "machine_user_id": machine_user_id,
                "token_id": token_result.get("token_id"),
                "endpoint": scim_endpoint,
                "last_issued_at": datetime.now(UTC).isoformat(),
                "last_issued_by": actor,
                "token_expires_at": expiration_date,
                "supports_groups": False,
                "group_sync_mode": "console_claim_mapping",
            }
        },
    )
    updated_metadata = _merge_dict(
        _coerce_json(existing_binding.get("metadata")),
        {
            "directory": {
                "scim_status": "configured",
            }
        },
    )

    await upsert_identity_binding(
        prisma_client,
        account_id=account_id,
        provider=existing_binding.get("provider") or "zitadel",
        zitadel_org_id=org_id,
        issuer_url=existing_binding.get("issuer_url"),
        client_id=existing_binding.get("client_id"),
        default_redirect_url=existing_binding.get("default_redirect_url"),
        sso_enabled=bool(existing_binding.get("sso_enabled")),
        config=updated_config,
        metadata=updated_metadata,
        actor=actor,
    )

    return {
        "endpoint": scim_endpoint,
        "token": token_result.get("token"),
        "token_id": token_result.get("token_id"),
        "machine_user_id": machine_user_id,
        "expiration_date": expiration_date,
        "supports_groups": False,
        "group_sync_note": (
            "Zitadel SCIM provisions users. Group and team mapping remains in Console "
            "and should be driven by OIDC claims or a future provider-specific sync job."
        ),
    }


async def create_directory_user(
    prisma_client,
    *,
    account_id: str,
    user_email: str,
    display_name: Optional[str],
    membership_role: str,
    product_grants: List[str],
    bootstrap_mode: str,
    temporary_password: Optional[str],
    actor: str,
) -> Dict[str, Any]:
    binding = await get_account_identity_binding(prisma_client, account_id)
    if binding is None or not binding.get("zitadel_org_id"):
        raise ValueError("Directory must be bootstrapped before creating users.")

    org_id = binding["zitadel_org_id"]
    client = ZitadelClient.from_env()
    given_name, family_name, resolved_display_name = _split_name(display_name, user_email)

    existing_users = await client.search_users_by_email(email=user_email)
    existing_in_org = [
        user
        for user in existing_users
        if str(user.get("resource_owner") or "") == str(org_id)
    ]
    if len(existing_in_org) > 1:
        raise ValueError(
            "Multiple existing directory users already use this email inside the tenant organization. Resolve the duplicate in Zitadel before granting access from Console."
        )
    reused_existing_user = len(existing_in_org) == 1

    resolved_password = None
    invite_code = None
    zitadel_sub = existing_in_org[0]["user_id"] if reused_existing_user else None
    if bootstrap_mode == "temporary_password" and not reused_existing_user:
        resolved_password = temporary_password or _generate_temp_password()

    if not reused_existing_user:
        created_user = await client.create_human_user(
            org_id=org_id,
            email=user_email,
            given_name=given_name,
            family_name=family_name,
            display_name=resolved_display_name,
            password=resolved_password,
        )
        zitadel_sub = created_user.get("user_id")
    if not zitadel_sub:
        raise ZitadelAPIError("Zitadel did not return a user id for the new directory user.")

    if bootstrap_mode != "temporary_password" and not reused_existing_user:
        invite = await client.create_invite_code(user_id=zitadel_sub)
        invite_code = invite.get("invite_code")

    synced = await _sync_member_access(
        prisma_client,
        account_id=account_id,
        user_email=user_email,
        display_name=resolved_display_name,
        zitadel_sub=zitadel_sub,
        membership_role=membership_role,
        product_grants=product_grants,
        actor=actor,
    )
    warnings = await _ensure_zitadel_user_grants(
        client,
        user_id=zitadel_sub,
        product_grants=product_grants,
    )

    return {
        "user": synced["user"],
        "membership": synced["membership"],
        "temporary_password": resolved_password,
        "invite_code": invite_code,
        "reused_existing_user": reused_existing_user,
        "warnings": warnings,
    }


async def get_directory_summary(prisma_client, *, account_id: str) -> Dict[str, Any]:
    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise ValueError("Account not found")

    binding = await get_account_identity_binding(prisma_client, account_id)
    account_metadata = _coerce_json(account.get("metadata"))
    binding_config = _coerce_json(binding.get("config")) if binding else {}
    binding_metadata = _coerce_json(binding.get("metadata")) if binding else {}
    provider_config = _coerce_json(binding_config.get("provider"))
    provider_list = [
        provider
        for provider in binding_config.get("providers", [])
        if isinstance(provider, dict)
    ]
    if not provider_list and provider_config:
        provider_list = [provider_config]
    scim_config = _coerce_json(binding_config.get("scim"))
    directory_config = _coerce_json(binding_config.get("directory"))
    domain_config = _coerce_json(binding_config.get("domains"))
    live_domains: List[Dict[str, Any]] = []
    login_policy: Dict[str, Any] = {}
    resolved_org_id = (
        binding.get("zitadel_org_id")
        if binding and binding.get("zitadel_org_id")
        else account_metadata.get("zitadel_org_id")
    )

    if resolved_org_id and _management_available():
        try:
            client = ZitadelClient.from_env()
            live_domains = await client.search_org_domains(org_id=resolved_org_id)
            login_policy = await client.get_login_policy(org_id=resolved_org_id)
        except Exception:
            live_domains = []
            login_policy = {}

    current_primary_domain = next(
        (
            _normalize_domain(domain.get("domainName"))
            for domain in live_domains
            if domain.get("isPrimary")
        ),
        domain_config.get("primary_domain") or _normalize_domain(account.get("domain")),
    )
    additional_domains = [
        domain_name
        for domain_name in (
            _normalize_domain(domain.get("domainName")) for domain in live_domains
        )
        if domain_name and domain_name != current_primary_domain
    ]
    if not additional_domains:
        additional_domains = [
            domain
            for domain in (
                _normalize_domain(value)
                for value in domain_config.get("additional_domains", [])
            )
            if domain and domain != current_primary_domain
        ]

    resolved_login_mode = directory_config.get("login_mode")
    if login_policy:
        resolved_login_mode = _policy_to_login_mode(
            allow_username_password=bool(login_policy.get("allowUsernamePassword")),
            allow_external_idp=bool(login_policy.get("allowExternalIdp")),
        )
    if not resolved_login_mode:
        resolved_login_mode = "hybrid"

    managed_via_console = bool(
        directory_config.get("managed_via_console", False if resolved_org_id else True)
    )
    management_config = _coerce_json(binding_config.get("management"))
    directory_metadata = _coerce_json(binding_metadata.get("directory"))

    return {
        "account": {
            "account_id": account["account_id"],
            "account_name": account["account_name"],
            "account_alias": account.get("account_alias"),
            "domain": account.get("domain"),
            "status": account["status"],
        },
        "identity_binding": binding,
        "management": management_status(),
        "directory": {
            "org_id": resolved_org_id,
            "bootstrap_status": directory_metadata.get("bootstrap_status")
            or ("discovered" if resolved_org_id and not binding else None),
            "provider_status": directory_metadata.get("provider_status")
            or ("managed_in_zitadel" if resolved_org_id else None),
            "managed_via_console": managed_via_console,
            "management_url": management_config.get("console_url") or _zitadel_console_url(
                resolved_org_id
            ),
            "bootstrap_login": directory_config.get("bootstrap_login") or "zitadel_local_password",
            "sso_enabled": bool(binding.get("sso_enabled")) if binding else False,
            "provider": provider_config or None,
            "providers": provider_list,
            "scim": scim_config or None,
            "supports_group_scim": False,
            "group_sync_strategy": "claim_mapping_or_provider_sync",
            "primary_domain": current_primary_domain,
            "additional_domains": additional_domains,
            "domains": live_domains,
            "login_policy": {
                "login_mode": resolved_login_mode,
                "allow_register": bool(
                    login_policy.get("allowRegister", directory_config.get("allow_register", False))
                ),
                "allow_domain_discovery": bool(
                    login_policy.get(
                        "allowDomainDiscovery",
                        directory_config.get("allow_domain_discovery", bool(current_primary_domain)),
                    )
                ),
                "allow_username_password": bool(
                    login_policy.get(
                        "allowUsernamePassword",
                        _login_mode_to_policy(resolved_login_mode)[0],
                    )
                ),
                "allow_external_idp": bool(
                    login_policy.get(
                        "allowExternalIdp",
                        _login_mode_to_policy(resolved_login_mode)[1],
                    )
                ),
            },
        },
        "capabilities": {
            "can_bootstrap": _management_available(),
            "can_manage_users": bool(resolved_org_id and not managed_via_console),
            "scim_support": "users_only",
        },
    }
