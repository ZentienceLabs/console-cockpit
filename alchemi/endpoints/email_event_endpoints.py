"""
Per-account email event notification settings.
Matches the /email/event_settings API shape expected by the UI,
but stores settings in Alchemi_AccountTable.metadata.email_settings
so each tenant has isolated configuration.
"""
import enum
import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from litellm._logging import verbose_proxy_logger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.auth.user_api_key_auth import user_api_key_auth
from prisma import Json

router = APIRouter(tags=["Email Event Settings"])


# ── Types (mirror litellm_enterprise types) ───────────────────────────────


class EmailEvent(str, enum.Enum):
    virtual_key_created = "Virtual Key Created"
    new_user_invitation = "New User Invitation"
    virtual_key_rotated = "Virtual Key Rotated"
    soft_budget_crossed = "Soft Budget Crossed"
    max_budget_alert = "Max Budget Alert"


class EmailEventSetting(BaseModel):
    event: EmailEvent
    enabled: bool


class EmailEventSettingsUpdateRequest(BaseModel):
    settings: List[EmailEventSetting]


class EmailEventSettingsResponse(BaseModel):
    settings: List[EmailEventSetting]


_DEFAULTS: Dict[str, bool] = {
    EmailEvent.virtual_key_created.value: True,
    EmailEvent.new_user_invitation.value: True,
    EmailEvent.virtual_key_rotated.value: True,
    EmailEvent.soft_budget_crossed.value: True,
    EmailEvent.max_budget_alert.value: True,
}


# ── Helpers ───────────────────────────────────────────────────────────────


async def _get_account_email_settings(account_id: Optional[str]) -> Dict[str, bool]:
    """Read email_settings from account metadata, falling back to defaults."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    settings = dict(_DEFAULTS)

    if account_id:
        account = await prisma_client.db.alchemi_accounttable.find_unique(
            where={"account_id": account_id}
        )
        if account and account.metadata:
            meta = account.metadata if isinstance(account.metadata, dict) else {}
            stored = meta.get("email_settings")
            if stored and isinstance(stored, dict):
                for k, v in stored.items():
                    settings[k] = v

    return settings


async def _save_account_email_settings(
    account_id: str, settings: Dict[str, bool]
) -> None:
    """Persist email_settings into account metadata."""
    from litellm.proxy.proxy_server import prisma_client

    if prisma_client is None:
        raise HTTPException(status_code=500, detail="Database not connected")

    account = await prisma_client.db.alchemi_accounttable.find_unique(
        where={"account_id": account_id}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    meta = account.metadata if isinstance(account.metadata, dict) else {}
    meta["email_settings"] = settings

    await prisma_client.db.alchemi_accounttable.update(
        where={"account_id": account_id},
        data={"metadata": Json(meta)},
    )


def _resolve_account_id(request: Request) -> Optional[str]:
    """Resolve account_id using tenant middleware."""
    from alchemi.middleware.tenant_context import get_current_account_id
    from alchemi.middleware.account_middleware import resolve_tenant_from_request

    if get_current_account_id() is None:
        resolve_tenant_from_request(request)
    return get_current_account_id()


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get(
    "/email/event_settings",
    response_model=EmailEventSettingsResponse,
    dependencies=[Depends(user_api_key_auth)],
)
async def get_email_event_settings(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """Get email event notification settings for the caller's account."""
    account_id = _resolve_account_id(request)

    settings_dict = await _get_account_email_settings(account_id)

    response_settings = []
    for event in EmailEvent:
        enabled = settings_dict.get(event.value, False)
        response_settings.append(EmailEventSetting(event=event, enabled=enabled))

    return EmailEventSettingsResponse(settings=response_settings)


@router.patch(
    "/email/event_settings",
    dependencies=[Depends(user_api_key_auth)],
)
async def update_email_event_settings(
    data: EmailEventSettingsUpdateRequest,
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """Update email event notification settings for the caller's account."""
    account_id = _resolve_account_id(request)
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    settings_dict = await _get_account_email_settings(account_id)

    for setting in data.settings:
        settings_dict[setting.event.value] = setting.enabled

    await _save_account_email_settings(account_id, settings_dict)

    return {"message": "Email event settings updated successfully"}


@router.post(
    "/email/event_settings/reset",
    dependencies=[Depends(user_api_key_auth)],
)
async def reset_email_event_settings(
    request: Request,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),
):
    """Reset email event notification settings to defaults for the caller's account."""
    account_id = _resolve_account_id(request)
    if not account_id:
        raise HTTPException(status_code=400, detail="No account context found")

    await _save_account_email_settings(account_id, dict(_DEFAULTS))

    return {"message": "Email event settings reset to defaults"}
