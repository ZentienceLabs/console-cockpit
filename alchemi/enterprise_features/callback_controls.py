"""Callback controls for Alchemi enterprise hooks."""

from typing import Any, Dict, List, Optional, Set

import litellm
from litellm.constants import X_LITELLM_DISABLE_CALLBACKS
from litellm.integrations.custom_logger import CustomLogger
from litellm.litellm_core_utils.llm_request_utils import (
    get_proxy_server_request_headers,
)


class AlchemiCallbackControls:
    """Controls which callbacks are active for specific teams/keys."""

    _LOGGER_NAME_MAP = {
        "langfusepromptmanagement": "langfuse",
        "langfuselogger": "langfuse",
        "datadoglogger": "datadog",
        "s3logger": "s3_v2",
    }

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

    @staticmethod
    def _should_allow_dynamic_callback_disabling() -> bool:
        if getattr(litellm, "allow_dynamic_callback_disabling", True) is False:
            return False

        try:
            from litellm.proxy.proxy_server import premium_user

            return bool(premium_user)
        except Exception:
            return True

    @classmethod
    def _resolve_callback_name(cls, callback: Any) -> Optional[str]:
        if isinstance(callback, str):
            return callback.strip().lower()

        if isinstance(callback, CustomLogger):
            class_name = callback.__class__.__name__.strip().lower()
            if class_name in cls._LOGGER_NAME_MAP:
                return cls._LOGGER_NAME_MAP[class_name]

            if class_name.endswith("logger"):
                class_name = class_name[: -len("logger")]
            return class_name or None

        return None

    @staticmethod
    def _parse_disabled_callbacks(
        litellm_params: Optional[dict],
        standard_callback_dynamic_params: Optional[Any],
    ) -> Set[str]:
        disabled_callbacks: Set[str] = set()

        request_headers = get_proxy_server_request_headers(litellm_params)
        header_value = request_headers.get(X_LITELLM_DISABLE_CALLBACKS)
        if isinstance(header_value, str):
            disabled_callbacks.update(
                {
                    part.strip().lower()
                    for part in header_value.split(",")
                    if part.strip()
                }
            )

        request_body_callbacks = getattr(
            standard_callback_dynamic_params,
            "litellm_disabled_callbacks",
            None,
        )
        if isinstance(request_body_callbacks, list):
            disabled_callbacks.update(
                {
                    str(part).strip().lower()
                    for part in request_body_callbacks
                    if str(part).strip()
                }
            )

        return disabled_callbacks

    @classmethod
    def is_callback_disabled_dynamically(
        cls,
        callback: Any,
        litellm_params: Optional[dict],
        standard_callback_dynamic_params: Optional[Any],
    ) -> bool:
        """
        LiteLLM compatibility shim for dynamically disabling selected callbacks.

        This keeps the auth failure path from exploding when the enterprise callback
        controls module is present but does not implement the expected interface.
        """

        try:
            if not cls._should_allow_dynamic_callback_disabling():
                return False

            callback_name = cls._resolve_callback_name(callback)
            if not callback_name:
                return False

            disabled_callbacks = cls._parse_disabled_callbacks(
                litellm_params,
                standard_callback_dynamic_params,
            )
            return callback_name in disabled_callbacks
        except Exception:
            return False
