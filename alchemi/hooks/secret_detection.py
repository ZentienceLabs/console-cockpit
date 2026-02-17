"""
Secret detection guardrail - scans prompts and responses for PII/secrets.
Clean-room re-implementation.
"""
import re
from typing import Optional, List, Dict, Any
from litellm.proxy.guardrails.guardrail_helpers import CustomGuardrail
from litellm.proxy._types import UserAPIKeyAuth

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "API_KEY"),
    (r'(?i)(secret|password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']{8,})["\']?', "PASSWORD"),
    (r'(?i)bearer\s+[a-zA-Z0-9_\-\.]+', "BEARER_TOKEN"),
    (r'sk-[a-zA-Z0-9]{20,}', "OPENAI_API_KEY"),
    (r'(?i)aws[_\-]?(access|secret)[_\-]?key[_\-]?(id)?\s*[=:]\s*["\']?([A-Z0-9]{16,})["\']?', "AWS_KEY"),
    (r'ghp_[a-zA-Z0-9]{36}', "GITHUB_TOKEN"),
    (r'(?i)(postgres|mysql|mongodb)://[^\s]+', "DATABASE_URL"),
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "EMAIL"),
    (r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b', "SSN"),
    (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', "CREDIT_CARD"),
]


class AlchemiSecretDetection(CustomGuardrail):
    """Guardrail that detects secrets and PII in prompts and responses."""

    GUARDRAIL_NAME = "hide_secrets"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.compiled_patterns = [
            (re.compile(pattern), name) for pattern, name in SECRET_PATTERNS
        ]

    def _detect_secrets(self, text: str) -> List[Dict[str, str]]:
        findings = []
        for pattern, secret_type in self.compiled_patterns:
            matches = pattern.findall(text)
            if matches:
                findings.append({
                    "type": secret_type,
                    "count": len(matches) if isinstance(matches, list) else 1,
                })
        return findings

    def _mask_secrets(self, text: str) -> str:
        masked = text
        for pattern, secret_type in self.compiled_patterns:
            masked = pattern.sub(f"[REDACTED_{secret_type}]", masked)
        return masked

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache,
        data: dict,
        call_type: str,
    ) -> Optional[dict]:
        messages = data.get("messages", [])
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                findings = self._detect_secrets(content)
                if findings:
                    message["content"] = self._mask_secrets(content)
        return data

    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: UserAPIKeyAuth,
        response,
    ):
        if hasattr(response, "choices"):
            for choice in response.choices:
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    content = choice.message.content
                    if content:
                        findings = self._detect_secrets(content)
                        if findings:
                            choice.message.content = self._mask_secrets(content)
        return response
