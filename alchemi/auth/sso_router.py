"""Per-account SSO routing - resolves SSO configuration based on email domain."""
from typing import Optional, Dict, Any

from alchemi.auth.zitadel import get_zitadel_settings


def _is_account_zitadel_enabled(account: Any) -> bool:
    """
    Check whether this account should use Zitadel-based SSO.

    This lets login resolve route to SSO without requiring legacy per-account
    SSO rows, as long as account metadata has Zitadel enabled and global
    Zitadel runtime credentials are configured.
    """
    try:
        metadata = getattr(account, "metadata", None) or {}
        if not isinstance(metadata, dict):
            metadata = dict(metadata)
        zitadel_cfg = metadata.get("zitadel", {}) or {}
        if not isinstance(zitadel_cfg, dict):
            return False

        enabled = zitadel_cfg.get("enabled")
        if enabled is False:
            return False

        settings = get_zitadel_settings()
        return bool(
            settings.enabled
            and settings.issuer
            and settings.client_id
            and settings.client_secret
        )
    except Exception:
        return False


async def resolve_sso_for_email(
    email: str,
    prisma_client=None,
) -> Dict[str, Any]:
    """
    Given an email, determine the login method:
    - If account has SSO enabled: return SSO URL
    - Otherwise: return password method
    """
    if not email or "@" not in email:
        return {"method": "password", "account_id": None, "sso_enabled": False}

    domain = email.split("@")[-1]

    if prisma_client is None:
        return {"method": "password", "account_id": None, "sso_enabled": False}

    try:
        account = await prisma_client.db.alchemi_accounttable.find_first(
            where={"domain": domain, "status": "active"},
            include={"sso_config": True},
        )

        if account is None:
            return {"method": "password", "account_id": None, "sso_enabled": False}

        if (
            account.sso_config
            and account.sso_config.enabled
            and account.sso_config.sso_settings
        ):
            return {
                "method": "sso",
                "account_id": account.account_id,
                "sso_url": f"/sso/key/generate?account_id={account.account_id}",
                "sso_provider": account.sso_config.sso_provider,
                "sso_enabled": True,
            }

        # Zitadel-first fallback: if account metadata enables Zitadel, route
        # login to SSO even when legacy account SSO settings are absent.
        if _is_account_zitadel_enabled(account):
            return {
                "method": "sso",
                "account_id": account.account_id,
                "sso_url": f"/sso/key/generate?account_id={account.account_id}",
                "sso_provider": "zitadel",
                "sso_enabled": True,
            }

        return {"method": "password", "account_id": account.account_id, "sso_enabled": False}

    except Exception:
        return {"method": "password", "account_id": None, "sso_enabled": False}
