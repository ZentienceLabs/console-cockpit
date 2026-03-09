"""
Control-plane endpoints for canonical account, identity, membership, and
projection management across Console and Copilot.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from alchemi.control_plane.service import (
    delete_account_membership,
    ensure_account_membership,
    ensure_group,
    ensure_product_grant,
    ensure_role_binding,
    ensure_team,
    get_account_by_id,
    get_account_identity_binding,
    get_copilot_projection,
    get_user_context,
    list_account_members,
    list_accounts,
    upsert_account,
    upsert_control_plane_user,
    upsert_identity_binding,
)
from alchemi.identity.service import (
    bootstrap_account_directory,
    configure_account_directory,
    configure_account_directory_settings,
    create_directory_user,
    get_directory_summary,
    issue_scim_token,
    link_existing_account_directory,
    list_available_zitadel_organizations,
    sync_zitadel_organizations_to_accounts,
)
from alchemi.identity.zitadel_client import (
    ZitadelAPIError,
    ZitadelConfigurationError,
)

router = APIRouter(prefix="/control-plane", tags=["Control Plane"])


def _actor_name(request: Request) -> str:
    state = _decode_request_state(request)
    if state.get("is_super_admin"):
        return "super_admin"
    return state.get("user_id") or state.get("user_email") or "control_plane"


def _decode_request_state(request: Request) -> Dict[str, Any]:
    from alchemi.middleware.account_middleware import (
        _get_master_key,
        decode_jwt_token,
        extract_token_from_request,
    )

    token = extract_token_from_request(request)
    if not token:
        return {}

    master_key = _get_master_key()
    claims = decode_jwt_token(token, master_key)
    return claims or {}


async def _require_super_admin(request: Request):
    from alchemi.middleware.account_middleware import resolve_tenant_from_request
    from alchemi.middleware.tenant_context import is_super_admin

    if not is_super_admin():
        resolve_tenant_from_request(request)

    if not is_super_admin():
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only accessible to super admins.",
        )


async def _require_account_operator(request: Request, account_id: Optional[str] = None):
    from alchemi.middleware.account_middleware import resolve_tenant_from_request
    from alchemi.middleware.tenant_context import (
        get_current_account_id,
        is_super_admin,
        set_current_account_id,
    )
    from litellm.proxy.proxy_server import prisma_client

    if not is_super_admin() and get_current_account_id() is None:
        resolve_tenant_from_request(request)

    if is_super_admin():
        return

    current_account_id = get_current_account_id()
    requested_account_id = account_id or current_account_id
    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    claims = _decode_request_state(request)
    claim_user_id = claims.get("user_id")
    claim_user_email = claims.get("user_email")
    if claim_user_email is None and isinstance(claim_user_id, str) and "@" in claim_user_id:
        claim_user_email = claim_user_id.lower()
        claim_user_id = None

    context = await get_user_context(
        prisma_client,
        user_email=claim_user_email,
        user_id=claim_user_id,
        zitadel_sub=claims.get("sub"),
        active_account_id=requested_account_id or claims.get("active_account_id") or claims.get("account_id"),
    )

    platform_roles = set(context.get("platform_roles") or [])
    if "platform_admin" in platform_roles or "platform_super_admin" in platform_roles:
        if requested_account_id:
            set_current_account_id(requested_account_id)
        return

    allowed_roles = {"owner", "admin", "account_admin"}
    memberships = context.get("memberships") or []
    target_membership = None
    if requested_account_id is not None:
        target_membership = next(
            (
                membership
                for membership in memberships
                if membership.get("account_id") == requested_account_id
            ),
            None,
        )
    elif memberships:
        target_membership = next(
            (
                membership
                for membership in memberships
                if str(membership.get("membership_role") or "").lower() in allowed_roles
            ),
            memberships[0],
        )

    if target_membership is None:
        raise HTTPException(status_code=403, detail="Account admin access required.")

    membership_role = str(target_membership.get("membership_role") or "").lower()
    if membership_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Account admin access required.")

    set_current_account_id(target_membership.get("account_id"))


class AccountOwnerRequest(BaseModel):
    user_id: Optional[str] = None
    user_email: str
    display_name: Optional[str] = None
    zitadel_sub: Optional[str] = None
    membership_role: str = "owner"
    is_default: bool = True
    platform_roles: List[str] = Field(default_factory=list)
    product_grants: List[str] = Field(default_factory=lambda: ["console", "copilot"])
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ControlPlaneAccountCreateRequest(BaseModel):
    account_id: Optional[str] = None
    account_name: str
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    max_budget: Optional[float] = None
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    owner: Optional[AccountOwnerRequest] = None
    directory_bootstrap: Optional["DirectoryBootstrapRequest"] = None


class ControlPlaneAccountUpdateRequest(BaseModel):
    account_name: Optional[str] = None
    account_alias: Optional[str] = None
    domain: Optional[str] = None
    max_budget: Optional[float] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class IdentityBootstrapRequest(BaseModel):
    provider: str = "zitadel"
    zitadel_org_id: Optional[str] = None
    issuer_url: Optional[str] = None
    client_id: Optional[str] = None
    default_redirect_url: Optional[str] = None
    sso_enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemberInviteRequest(BaseModel):
    user_id: Optional[str] = None
    user_email: str
    display_name: Optional[str] = None
    zitadel_sub: Optional[str] = None
    membership_role: str = "member"
    membership_status: str = "active"
    is_default: bool = False
    platform_roles: List[str] = Field(default_factory=list)
    product_grants: List[str] = Field(default_factory=lambda: ["console", "copilot"])
    bootstrap_mode: str = "temporary_password"
    temporary_password: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GroupCreateRequest(BaseModel):
    group_name: str
    group_kind: str = "org"
    group_slug: Optional[str] = None
    parent_group_id: Optional[str] = None
    default_team_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RoleBindingRequest(BaseModel):
    principal_type: str
    principal_id: str
    role_code: str
    scope_type: str = "account"
    scope_id: Optional[str] = None
    product_code: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DirectoryBootstrapRequest(BaseModel):
    first_admin_email: str
    first_admin_display_name: Optional[str] = None
    membership_role: str = "owner"
    bootstrap_mode: str = "temporary_password"
    temporary_password: Optional[str] = None
    create_scim_service_user: bool = True


class DirectoryProviderConfigRequest(BaseModel):
    provider_type: str = "entra_oidc"
    provider_name: str
    issuer: str
    client_id: str
    client_secret: str
    scopes: List[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    auto_register: bool = True
    group_claim: Optional[str] = "groups"
    default_role: str = "member"
    sync_mode: str = "oidc_claim_mapping"


class DirectoryScimBootstrapRequest(BaseModel):
    expiration_days: int = 365


class DirectorySettingsRequest(BaseModel):
    primary_domain: Optional[str] = None
    additional_domains: List[str] = Field(default_factory=list)
    login_mode: str = "hybrid"
    allow_register: bool = False
    allow_domain_discovery: bool = True


class ExistingDirectoryLinkRequest(BaseModel):
    zitadel_org_id: str
    admin_user_id: Optional[str] = None
    admin_user_email: Optional[str] = None
    admin_display_name: Optional[str] = None
    membership_role: str = "owner"
    product_grants: List[str] = Field(default_factory=lambda: ["console", "copilot"])


class DirectoryUserCreateRequest(BaseModel):
    user_email: str
    display_name: Optional[str] = None
    membership_role: str = "member"
    product_grants: List[str] = Field(default_factory=lambda: ["console", "copilot"])
    bootstrap_mode: str = "temporary_password"
    temporary_password: Optional[str] = None


ControlPlaneAccountCreateRequest.model_rebuild()


@router.get("/accounts")
async def control_plane_list_accounts(
    request: Request,
    _=Depends(_require_super_admin),
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        await sync_zitadel_organizations_to_accounts(
            prisma_client,
            actor=_actor_name(request),
        )
    except ZitadelConfigurationError:
        pass
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {"accounts": await list_accounts(prisma_client)}


@router.get("/zitadel/organizations")
async def control_plane_list_zitadel_organizations(
    request: Request,
    _=Depends(_require_super_admin),
):
    try:
        organizations = await list_available_zitadel_organizations()
    except ZitadelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {"organizations": organizations}


@router.post("/accounts")
async def control_plane_create_account(
    data: ControlPlaneAccountCreateRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    actor = _actor_name(request)
    account = await upsert_account(
        prisma_client,
        account_id=data.account_id,
        account_name=data.account_name,
        account_alias=data.account_alias,
        domain=data.domain,
        max_budget=data.max_budget,
        metadata=data.metadata,
        status=data.status,
        actor=actor,
    )

    owner_payload = None
    if data.owner is not None:
        owner = await upsert_control_plane_user(
            prisma_client,
            user_id=data.owner.user_id,
            user_email=data.owner.user_email,
            display_name=data.owner.display_name,
            zitadel_sub=data.owner.zitadel_sub,
            primary_account_id=account["account_id"],
            metadata=data.owner.metadata,
            actor=actor,
        )
        owner_payload = owner

        await ensure_account_membership(
            prisma_client,
            account_id=account["account_id"],
            user_id=owner["user_id"],
            membership_role=data.owner.membership_role,
            membership_status="active",
            is_default=data.owner.is_default,
            metadata={"source": "control-plane-create"},
            actor=actor,
        )

        default_roles = list(data.owner.platform_roles)
        if data.owner.membership_role in ("owner", "admin", "account_admin"):
            default_roles.append("account_admin")
        for role_code in sorted(set(default_roles)):
            await ensure_role_binding(
                prisma_client,
                account_id=account["account_id"],
                principal_type="user",
                principal_id=owner["user_id"],
                role_code=role_code,
                product_code="platform-admin" if role_code == "platform_admin" else None,
                scope_type="account",
                scope_id=account["account_id"],
                metadata={"source": "control-plane-create"},
                actor=actor,
            )
        for product_code in sorted(set(data.owner.product_grants)):
            await ensure_product_grant(
                prisma_client,
                account_id=account["account_id"],
                user_id=owner["user_id"],
                product_code=product_code,
                grant_status="active",
                metadata={"source": "control-plane-create"},
                actor=actor,
            )

    default_group = await ensure_group(
        prisma_client,
        account_id=account["account_id"],
        group_name="Default Organization",
        group_kind="org",
        group_slug="default-organization",
        parent_group_id=None,
        metadata={"is_default": True},
        actor=actor,
    )
    await ensure_team(
        prisma_client,
        account_id=account["account_id"],
        team_name="Default Team",
        group_id=default_group["group_id"],
        team_slug="default-team",
        metadata={"is_default": True},
        actor=actor,
    )

    response = {
        "message": "Control-plane account created successfully",
        "account": account,
        "owner": owner_payload,
    }
    if data.directory_bootstrap is not None:
        try:
            response["directory_bootstrap"] = await bootstrap_account_directory(
                prisma_client,
                account_id=account["account_id"],
                first_admin_email=data.directory_bootstrap.first_admin_email,
                first_admin_display_name=data.directory_bootstrap.first_admin_display_name,
                membership_role=data.directory_bootstrap.membership_role,
                bootstrap_mode=data.directory_bootstrap.bootstrap_mode,
                temporary_password=data.directory_bootstrap.temporary_password,
                create_scim_service_user=data.directory_bootstrap.create_scim_service_user,
                actor=actor,
            )
        except (ValueError, ZitadelConfigurationError, ZitadelAPIError) as exc:
            response["directory_bootstrap"] = {
                "status": "failed",
                "error": str(exc),
                "detail": getattr(exc, "detail", None),
            }
    return response


@router.get("/accounts/{account_id}")
async def control_plane_get_account(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin),
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    account["members"] = await list_account_members(prisma_client, account_id)
    return account


@router.put("/accounts/{account_id}")
async def control_plane_update_account(
    account_id: str,
    data: ControlPlaneAccountUpdateRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    updated = await upsert_account(
        prisma_client,
        account_id=account_id,
        account_name=data.account_name or account["account_name"],
        account_alias=data.account_alias if data.account_alias is not None else account.get("account_alias"),
        domain=data.domain if data.domain is not None else account.get("domain"),
        max_budget=data.max_budget if data.max_budget is not None else account.get("max_budget"),
        metadata=data.metadata if data.metadata is not None else account.get("metadata", {}),
        status=data.status or account["status"],
        actor=_actor_name(request),
    )
    return {"message": "Account updated successfully", "account": updated}


@router.delete("/accounts/{account_id}")
async def control_plane_suspend_account(
    account_id: str,
    request: Request,
    _=Depends(_require_super_admin),
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    updated = await upsert_account(
        prisma_client,
        account_id=account_id,
        account_name=account["account_name"],
        account_alias=account.get("account_alias"),
        domain=account.get("domain"),
        max_budget=account.get("max_budget"),
        metadata=account.get("metadata", {}),
        status="suspended" if account["status"] == "active" else "active",
        actor=_actor_name(request),
    )
    return {"message": "Account status updated", "account": updated}


@router.get("/accounts/{account_id}/members")
async def control_plane_list_members(
    account_id: str,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)
    return {"members": await list_account_members(prisma_client, account_id)}


@router.get("/accounts/{account_id}/identity")
async def control_plane_get_identity(
    account_id: str,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    return {
        "account": {
            "account_id": account["account_id"],
            "account_name": account["account_name"],
            "account_alias": account.get("account_alias"),
            "domain": account.get("domain"),
            "status": account["status"],
        },
        "identity_binding": await get_account_identity_binding(prisma_client, account_id),
    }


@router.get("/accounts/{account_id}/directory")
async def control_plane_get_directory(
    account_id: str,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    try:
        return await get_directory_summary(prisma_client, account_id=account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/identity/bootstrap")
async def control_plane_bootstrap_identity(
    account_id: str,
    data: IdentityBootstrapRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    binding = await upsert_identity_binding(
        prisma_client,
        account_id=account_id,
        provider=data.provider,
        zitadel_org_id=data.zitadel_org_id,
        issuer_url=data.issuer_url,
        client_id=data.client_id,
        default_redirect_url=data.default_redirect_url,
        sso_enabled=data.sso_enabled,
        config=data.config,
        metadata=data.metadata,
        actor=_actor_name(request),
    )
    return {
        "message": "Identity binding updated successfully",
        "account_id": account_id,
        "identity_binding": binding,
    }


@router.post("/accounts/{account_id}/directory/bootstrap")
async def control_plane_bootstrap_directory(
    account_id: str,
    data: DirectoryBootstrapRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    try:
        bootstrap = await bootstrap_account_directory(
            prisma_client,
            account_id=account_id,
            first_admin_email=data.first_admin_email,
            first_admin_display_name=data.first_admin_display_name,
            membership_role=data.membership_role,
            bootstrap_mode=data.bootstrap_mode,
            temporary_password=data.temporary_password,
            create_scim_service_user=data.create_scim_service_user,
            actor=_actor_name(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ZitadelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {"message": "Directory bootstrapped successfully", "bootstrap": bootstrap}


@router.post("/accounts/{account_id}/directory/link-existing")
async def control_plane_link_existing_directory(
    account_id: str,
    data: ExistingDirectoryLinkRequest,
    request: Request,
    _=Depends(_require_super_admin),
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    try:
        result = await link_existing_account_directory(
            prisma_client,
            account_id=account_id,
            zitadel_org_id=data.zitadel_org_id,
            admin_user_id=data.admin_user_id,
            admin_user_email=data.admin_user_email,
            admin_display_name=data.admin_display_name,
            membership_role=data.membership_role,
            product_grants=data.product_grants,
            actor=_actor_name(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZitadelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {"message": "Existing Zitadel organization linked successfully", "result": result}


@router.post("/accounts/{account_id}/directory/provider")
async def control_plane_configure_directory_provider(
    account_id: str,
    data: DirectoryProviderConfigRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    try:
        binding = await configure_account_directory(
            prisma_client,
            account_id=account_id,
            actor=_actor_name(request),
            provider_type=data.provider_type,
            provider_name=data.provider_name,
            issuer=data.issuer,
            client_id=data.client_id,
            client_secret=data.client_secret,
            scopes=data.scopes,
            auto_register=data.auto_register,
            group_claim=data.group_claim,
            default_role=data.default_role,
            sync_mode=data.sync_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZitadelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {
        "message": "Directory provider configured successfully",
        "identity_binding": binding,
    }


@router.post("/accounts/{account_id}/directory/settings")
async def control_plane_configure_directory_settings(
    account_id: str,
    data: DirectorySettingsRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    try:
        result = await configure_account_directory_settings(
            prisma_client,
            account_id=account_id,
            actor=_actor_name(request),
            primary_domain=data.primary_domain,
            additional_domains=data.additional_domains,
            login_mode=data.login_mode,
            allow_register=data.allow_register,
            allow_domain_discovery=data.allow_domain_discovery,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZitadelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {
        "message": "Directory settings updated successfully",
        "settings": result,
    }


@router.post("/accounts/{account_id}/directory/scim/bootstrap")
async def control_plane_bootstrap_scim(
    account_id: str,
    data: DirectoryScimBootstrapRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    try:
        scim = await issue_scim_token(
            prisma_client,
            account_id=account_id,
            actor=_actor_name(request),
            expiration_days=data.expiration_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZitadelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {"message": "SCIM credentials issued successfully", "scim": scim}


@router.post("/accounts/{account_id}/directory/users")
async def control_plane_create_directory_user(
    account_id: str,
    data: DirectoryUserCreateRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    try:
        result = await create_directory_user(
            prisma_client,
            account_id=account_id,
            user_email=data.user_email,
            display_name=data.display_name,
            membership_role=data.membership_role,
            product_grants=data.product_grants,
            bootstrap_mode=data.bootstrap_mode,
            temporary_password=data.temporary_password,
            actor=_actor_name(request),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ZitadelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ZitadelAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "status_code": exc.status_code,
                "upstream": exc.detail,
            },
        ) from exc

    return {"message": "Directory user created successfully", "result": result}


@router.post("/accounts/{account_id}/members/invite")
async def control_plane_invite_member(
    account_id: str,
    data: MemberInviteRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    actor = _actor_name(request)
    identity_binding = await get_account_identity_binding(prisma_client, account_id)
    if identity_binding is not None and identity_binding.get("zitadel_org_id"):
        try:
            directory_result = await create_directory_user(
                prisma_client,
                account_id=account_id,
                user_email=data.user_email,
                display_name=data.display_name,
                membership_role=data.membership_role,
                product_grants=data.product_grants,
                bootstrap_mode=data.bootstrap_mode,
                temporary_password=data.temporary_password,
                actor=actor,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ZitadelConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ZitadelAPIError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": str(exc),
                    "status_code": exc.status_code,
                    "upstream": exc.detail,
                },
            ) from exc

        return {
            "message": "Member provisioned in Zitadel and synced into control plane",
            "user": directory_result["user"],
            "membership": directory_result["membership"],
            "directory": {
                "managed": True,
                "reused_existing_user": directory_result.get("reused_existing_user", False),
                "temporary_password": directory_result.get("temporary_password"),
                "invite_code": directory_result.get("invite_code"),
                "warnings": directory_result.get("warnings", []),
                "zitadel_sub": directory_result["user"].get("zitadel_sub"),
            },
        }

    user = await upsert_control_plane_user(
        prisma_client,
        user_id=data.user_id,
        user_email=data.user_email,
        display_name=data.display_name,
        zitadel_sub=data.zitadel_sub,
        primary_account_id=account_id,
        metadata=data.metadata,
        actor=actor,
    )
    membership = await ensure_account_membership(
        prisma_client,
        account_id=account_id,
        user_id=user["user_id"],
        membership_role=data.membership_role,
        membership_status=data.membership_status,
        is_default=data.is_default,
        metadata=data.metadata,
        actor=actor,
    )

    role_codes = list(data.platform_roles)
    if data.membership_role in ("owner", "admin", "account_admin"):
        role_codes.append("account_admin")
    for role_code in sorted(set(role_codes)):
        await ensure_role_binding(
            prisma_client,
            account_id=account_id,
            principal_type="user",
            principal_id=user["user_id"],
            role_code=role_code,
            product_code="platform-admin" if role_code == "platform_admin" else None,
            scope_type="account",
            scope_id=account_id,
            metadata={"source": "member-invite"},
            actor=actor,
        )

    for product_code in sorted(set(data.product_grants)):
        await ensure_product_grant(
            prisma_client,
            account_id=account_id,
            user_id=user["user_id"],
            product_code=product_code,
            grant_status="active",
            metadata={"source": "member-invite"},
            actor=actor,
        )

    return {
        "message": "Member synced into control plane",
        "user": user,
        "membership": membership,
        "directory": {
            "managed": False,
            "reused_existing_user": False,
            "temporary_password": None,
            "invite_code": None,
            "warnings": [],
            "zitadel_sub": user.get("zitadel_sub"),
        },
    }


@router.delete("/accounts/{account_id}/members/{user_email:path}")
async def control_plane_remove_member(
    account_id: str,
    user_email: str,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    deleted = await delete_account_membership(
        prisma_client,
        account_id=account_id,
        user_email=user_email,
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"message": "Member removed from account", "deleted": deleted}


@router.post("/accounts/{account_id}/groups")
async def control_plane_create_group(
    account_id: str,
    data: GroupCreateRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    actor = _actor_name(request)
    group = await ensure_group(
        prisma_client,
        account_id=account_id,
        group_name=data.group_name,
        group_kind=data.group_kind,
        group_slug=data.group_slug,
        parent_group_id=data.parent_group_id,
        metadata=data.metadata,
        actor=actor,
    )
    team = None
    if data.default_team_name:
        team = await ensure_team(
            prisma_client,
            account_id=account_id,
            team_name=data.default_team_name,
            group_id=group["group_id"],
            team_slug=None,
            metadata={"source": "group-create"},
            actor=actor,
        )

    return {
        "message": "Group created successfully",
        "group": group,
        "team": team,
    }


@router.post("/accounts/{account_id}/role-bindings")
async def control_plane_create_role_binding(
    account_id: str,
    data: RoleBindingRequest,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    binding = await ensure_role_binding(
        prisma_client,
        account_id=account_id,
        principal_type=data.principal_type,
        principal_id=data.principal_id,
        role_code=data.role_code,
        product_code=data.product_code,
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        metadata=data.metadata,
        actor=_actor_name(request),
    )
    return {"message": "Role binding created successfully", "role_binding": binding}


@router.get("/me/context")
async def control_plane_me_context(request: Request):
    from litellm.proxy.proxy_server import prisma_client

    claims = _decode_request_state(request)
    claim_user_id = claims.get("user_id")
    claim_user_email = claims.get("user_email")
    if claim_user_email is None and isinstance(claim_user_id, str) and "@" in claim_user_id:
        claim_user_email = claim_user_id.lower()
        claim_user_id = None

    if claims.get("is_super_admin"):
        return {
            "user": {
                "user_id": claims.get("user_id"),
                "user_email": claim_user_email,
            },
            "memberships": [],
            "platform_roles": ["platform_super_admin"],
            "product_grants": ["console", "copilot", "platform-admin"],
            "active_account_id": None,
            "is_break_glass": bool(claims.get("is_break_glass")),
        }

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    context = await get_user_context(
        prisma_client,
        user_email=claim_user_email,
        user_id=claim_user_id,
        zitadel_sub=claims.get("sub"),
        active_account_id=claims.get("active_account_id") or claims.get("account_id"),
    )
    context["is_break_glass"] = bool(claims.get("is_break_glass"))
    return context


@router.get("/accounts/{account_id}/projection/copilot")
async def control_plane_copilot_projection(
    account_id: str,
    request: Request,
):
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    await _require_account_operator(request, account_id)

    try:
        return await get_copilot_projection(prisma_client, account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
