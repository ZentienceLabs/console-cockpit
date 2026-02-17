"""Custom SSO handler for per-account SSO configuration."""
from typing import Optional, Dict, Any


class AlchemiCustomSSOHandler:
    """Handles custom SSO authentication for per-account SSO configs."""

    @staticmethod
    async def get_sso_config_for_account(
        account_id: str,
        prisma_client=None,
    ) -> Optional[Dict[str, Any]]:
        if prisma_client is None:
            return None
        try:
            sso_config = await prisma_client.db.alchemi_accountssoconfig.find_first(
                where={"account_id": account_id, "enabled": True}
            )
            if sso_config:
                return {
                    "provider": sso_config.sso_provider,
                    "settings": sso_config.sso_settings,
                    "account_id": account_id,
                }
        except Exception:
            pass
        return None

    @staticmethod
    async def handle_sso_callback(
        account_id: str,
        auth_code: str,
        prisma_client=None,
    ) -> Optional[Dict[str, Any]]:
        sso_config = await AlchemiCustomSSOHandler.get_sso_config_for_account(
            account_id, prisma_client
        )
        if not sso_config:
            return None
        return sso_config
