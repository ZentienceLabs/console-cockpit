"""Banned keywords guardrail - blocks requests containing banned keywords."""
from litellm.integrations.custom_guardrail import CustomGuardrail


class _ENTERPRISE_BannedKeywords(CustomGuardrail):
    """Guardrail that blocks requests containing banned keywords."""

    def __init__(self, banned_keywords=None, **kwargs):
        super().__init__(**kwargs)
        self.banned_keywords = banned_keywords or []

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        """Check if request contains banned keywords."""
        messages = data.get("messages", [])
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                content_lower = content.lower()
                for keyword in self.banned_keywords:
                    if keyword.lower() in content_lower:
                        raise ValueError(
                            f"Request contains banned keyword: '{keyword}'"
                        )
