"""Callback controls - manage per-team/key callback configurations."""
from typing import Optional, Dict, Any, List


class AlchemiCallbackControls:
    """Controls which callbacks are active for specific teams/keys."""

    @staticmethod
    def get_callbacks_for_team(
        team_id: str,
        team_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        if team_metadata and "callbacks" in team_metadata:
            return team_metadata["callbacks"]
        return None

    @staticmethod
    def get_callbacks_for_key(
        key_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[str]]:
        if key_metadata and "callbacks" in key_metadata:
            return key_metadata["callbacks"]
        return None
