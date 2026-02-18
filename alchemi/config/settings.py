"""
Alchemi proxy configuration - replaces EnterpriseProxyConfig.
"""
from typing import Optional, Dict, Any
import os


class AlchemiProxyConfig:
    """
    Alchemi-specific proxy configuration.
    Replaces the enterprise EnterpriseProxyConfig class.
    """

    def __init__(self):
        self.master_key = os.getenv("LITELLM_MASTER_KEY")
        self.ui_username = os.getenv("UI_USERNAME")
        self.ui_password = os.getenv("UI_PASSWORD")

    async def load_enterprise_config(self, general_settings: dict) -> None:
        """Load enterprise/Alchemi-specific configuration from general_settings."""
        return None

    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Return Alchemi-specific configuration."""
        return {
            "premium_user": True,
            "brand_name": "Alchemi Studio Console",
        }
