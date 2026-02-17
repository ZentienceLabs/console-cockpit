"""
Alchemi guardrail helpers - tag-based guardrail filtering.
Clean-room replacement of enterprise EnterpriseCustomGuardrailHelper.
"""
from typing import Any, Optional


class AlchemiCustomGuardrailHelper:
    """Helper for tag-based guardrail execution decisions."""

    @staticmethod
    def _should_run_if_mode_by_tag(
        data: dict,
        event_hook: Any,
    ) -> Optional[bool]:
        """
        Determine if a guardrail should run based on request tags and mode settings.

        Returns:
            True if guardrail should run, False if not, None if no decision.
        """
        request_tags = data.get("metadata", {}).get("tags", [])
        if not request_tags:
            request_tags = []

        # If the event_hook has required_tags, check if any match
        required_tags = getattr(event_hook, "required_tags", None)
        if required_tags:
            if any(tag in required_tags for tag in request_tags):
                return True
            return False

        # If the event_hook has excluded_tags, check if any match
        excluded_tags = getattr(event_hook, "excluded_tags", None)
        if excluded_tags:
            if any(tag in excluded_tags for tag in request_tags):
                return False

        return None
