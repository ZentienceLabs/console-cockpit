"""Blocked user list guardrail - blocks requests from specific users."""
from litellm.integrations.custom_guardrail import CustomGuardrail


class _ENTERPRISE_BlockedUserList(CustomGuardrail):
    """Guardrail that blocks requests from users on a blocklist."""

    def __init__(self, prisma_client=None, **kwargs):
        super().__init__(**kwargs)
        self.prisma_client = prisma_client

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        """Check if user is blocked before processing request."""
        if self.prisma_client is None:
            return

        user_id = user_api_key_dict.get("user_id")
        if not user_id:
            return

        try:
            end_user = data.get("metadata", {}).get("user_api_key_end_user_id")
            if end_user:
                end_user_record = await self.prisma_client.db.litellm_endusertable.find_first(
                    where={"user_id": end_user}
                )
                if end_user_record and getattr(end_user_record, "blocked", False):
                    raise ValueError(f"User {end_user} is blocked.")
        except ValueError:
            raise
        except Exception:
            pass
