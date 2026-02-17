"""Audit logger hook - captures management operations and sends to OpenObserve."""
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from litellm.integrations.custom_logger import CustomLogger
from alchemi.middleware.tenant_context import get_current_account_id


class AlchemiAuditLogger(CustomLogger):
    """Custom logger that captures audit events and forwards them to OpenObserve."""

    def __init__(self):
        super().__init__()
        self._openobserve_client = None

    @property
    def openobserve_client(self):
        if self._openobserve_client is None:
            from alchemi.integrations.openobserve import OpenObserveClient
            self._openobserve_client = OpenObserveClient()
        return self._openobserve_client

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        """Log successful LLM API calls."""
        try:
            account_id = get_current_account_id()
            event = {
                "event_type": "llm_api_call",
                "status": "success",
                "account_id": account_id,
                "model": kwargs.get("model", ""),
                "user": kwargs.get("user", ""),
                "team_id": kwargs.get("metadata", {}).get("team_id", ""),
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "timestamp": datetime.utcnow().isoformat(),
            }
            if self.openobserve_client.is_configured():
                await self.openobserve_client.log_event(event)
        except Exception:
            pass

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        """Log failed LLM API calls."""
        try:
            account_id = get_current_account_id()
            event = {
                "event_type": "llm_api_call",
                "status": "failure",
                "account_id": account_id,
                "model": kwargs.get("model", ""),
                "error": str(kwargs.get("exception", "")),
                "timestamp": datetime.utcnow().isoformat(),
            }
            if self.openobserve_client.is_configured():
                await self.openobserve_client.log_event(event)
        except Exception:
            pass


async def log_management_audit_event(
    action: str,
    table_name: str,
    object_id: str,
    changed_by: Optional[str] = None,
    changed_by_api_key: Optional[str] = None,
    before_value: Optional[Dict[str, Any]] = None,
    updated_values: Optional[Dict[str, Any]] = None,
):
    """Log a management operation audit event to OpenObserve."""
    try:
        from alchemi.integrations.openobserve import OpenObserveClient
        account_id = get_current_account_id()
        event = {
            "event_type": "management_operation",
            "action": action,
            "table_name": table_name,
            "object_id": object_id,
            "changed_by": changed_by,
            "changed_by_api_key": changed_by_api_key,
            "account_id": account_id,
            "before_value": before_value,
            "updated_values": updated_values,
            "timestamp": datetime.utcnow().isoformat(),
        }
        client = OpenObserveClient()
        if client.is_configured():
            await client.log_event(event)
    except Exception:
        traceback.print_exc()
