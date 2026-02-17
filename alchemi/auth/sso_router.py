"""Per-account SSO routing - resolves SSO configuration based on email domain."""
from typing import Optional, Dict, Any


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

        return {"method": "password", "account_id": account.account_id, "sso_enabled": False}

    except Exception:
        return {"method": "password", "account_id": None, "sso_enabled": False}
