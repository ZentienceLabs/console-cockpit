import pytest
from fastapi import HTTPException
from starlette.requests import Request

from alchemi.endpoints.copilot_auth import (
    require_account_admin_or_super_admin,
    require_account_context,
)


def _request(path: str = "/copilot/budgets/plan", query: str = "") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": query.encode("utf-8"),
        "client": ("127.0.0.1", 8000),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_require_account_context_for_super_admin_uses_query_param(monkeypatch):
    request = _request(query="account_id=acct-001")

    monkeypatch.setattr("alchemi.endpoints.copilot_auth.is_super_admin", lambda: True)

    account_id = await require_account_context(request)
    assert account_id == "acct-001"


@pytest.mark.asyncio
async def test_require_account_context_super_admin_without_query_raises(monkeypatch):
    request = _request()

    monkeypatch.setattr("alchemi.endpoints.copilot_auth.is_super_admin", lambda: True)

    with pytest.raises(HTTPException) as exc:
        await require_account_context(request)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_require_account_context_account_admin_uses_tenant_context(monkeypatch):
    request = _request()

    monkeypatch.setattr("alchemi.endpoints.copilot_auth.is_super_admin", lambda: False)
    monkeypatch.setattr("alchemi.endpoints.copilot_auth.get_current_account_id", lambda: "acct-xyz")

    account_id = await require_account_context(request)
    assert account_id == "acct-xyz"


@pytest.mark.asyncio
async def test_require_account_admin_or_super_admin_rejects_without_context(monkeypatch):
    request = _request()

    monkeypatch.setattr("alchemi.endpoints.copilot_auth.is_super_admin", lambda: False)
    monkeypatch.setattr("alchemi.endpoints.copilot_auth.get_current_account_id", lambda: None)
    monkeypatch.setattr("alchemi.endpoints.copilot_auth.resolve_tenant_from_request", lambda _r: None)

    with pytest.raises(HTTPException) as exc:
        await require_account_admin_or_super_admin(request)

    assert exc.value.status_code == 403
