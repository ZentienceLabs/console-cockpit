"""OpenObserve client for sending audit logs and querying log data."""
import os
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx


class OpenObserveClient:
    """Client for interacting with OpenObserve API."""

    def __init__(self):
        self.url = os.getenv("OPENOBSERVE_URL", "")
        self.org = os.getenv("OPENOBSERVE_ORG", "default")
        self.stream = os.getenv("OPENOBSERVE_STREAM", "alchemi_audit")
        self.user = os.getenv("OPENOBSERVE_USER", "")
        self.password = os.getenv("OPENOBSERVE_PASSWORD", "")
        self.retention_days = int(os.getenv("ALCHEMI_AUDIT_LOG_RETENTION_DAYS", "90"))

    def is_configured(self) -> bool:
        return bool(self.url and self.user and self.password)

    def _get_auth_header(self) -> str:
        credentials = f"{self.user}:{self.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def log_event(self, event: Dict[str, Any]) -> bool:
        if not self.is_configured():
            return False
        try:
            event["_timestamp"] = datetime.utcnow().isoformat() + "Z"
            url = f"{self.url}/{self.org}/{self.stream}/_json"
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=[event], headers=headers)
                return response.status_code == 200
        except Exception:
            return False

    async def log_events(self, events: List[Dict[str, Any]]) -> bool:
        if not self.is_configured() or not events:
            return False
        try:
            for event in events:
                if "_timestamp" not in event:
                    event["_timestamp"] = datetime.utcnow().isoformat() + "Z"
            url = f"{self.url}/{self.org}/{self.stream}/_json"
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=events, headers=headers)
                return response.status_code == 200
        except Exception:
            return False

    async def search(
        self,
        query: str = "*",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            return {"hits": [], "total": 0}
        try:
            if not end_time:
                end_time = datetime.utcnow().isoformat() + "Z"
            if not start_time:
                start_dt = datetime.utcnow() - timedelta(days=self.retention_days)
                start_time = start_dt.isoformat() + "Z"
            search_url = f"{self.url}/{self.org}/_search"
            headers = {
                "Authorization": self._get_auth_header(),
                "Content-Type": "application/json",
            }
            search_payload = {
                "query": {
                    "sql": f'SELECT * FROM "{self.stream}" WHERE {query} ORDER BY _timestamp DESC LIMIT {limit}',
                    "start_time": start_time,
                    "end_time": end_time,
                    "from": 0,
                    "size": limit,
                },
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(search_url, json=search_payload, headers=headers)
                if response.status_code == 200:
                    return response.json()
                return {"hits": [], "total": 0, "error": response.text}
        except Exception as e:
            return {"hits": [], "total": 0, "error": str(e)}
