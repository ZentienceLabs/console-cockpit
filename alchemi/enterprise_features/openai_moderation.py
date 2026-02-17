"""OpenAI Moderation guardrail - checks content via OpenAI's moderation API."""
from litellm.integrations.custom_guardrail import CustomGuardrail


class _ENTERPRISE_OpenAI_Moderation(CustomGuardrail):
    """Guardrail that uses OpenAI's moderation endpoint to check content."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def async_moderation_hook(self, data: dict, call_type: str, **kwargs):
        """Check content against OpenAI moderation API."""
        import litellm

        messages = data.get("messages", [])
        if not messages:
            return

        # Get the last user message
        last_message = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_message = msg.get("content", "")
                break

        if not last_message or not isinstance(last_message, str):
            return

        try:
            response = await litellm.amoderation(
                input=last_message,
                model="text-moderation-latest",
            )
            if hasattr(response, "results") and response.results:
                for result in response.results:
                    if result.flagged:
                        raise ValueError(
                            f"Content flagged by OpenAI Moderation API: {result.categories}"
                        )
        except ValueError:
            raise
        except Exception:
            pass  # Don't block on moderation API errors
