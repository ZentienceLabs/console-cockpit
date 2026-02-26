from unittest.mock import patch

from starlette.requests import Request

from alchemi.middleware.account_middleware import (
    _extract_account_id_from_claims,
    _is_super_admin_claims,
    resolve_tenant_from_request,
)
from alchemi.middleware.tenant_context import get_current_account_id, is_super_admin


def _request_with_auth(token: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/copilot/budgets/plan",
        "headers": [(b"authorization", f"Bearer {token}".encode("utf-8"))],
        "query_string": b"",
        "client": ("127.0.0.1", 8000),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_extract_account_id_from_claims_prefers_known_keys() -> None:
    claims = {
        "tenant_id": "tenant-123",
        "account_id": "acct-001",
    }
    assert _extract_account_id_from_claims(claims) == "acct-001"


def test_super_admin_claims_from_zitadel_project_roles() -> None:
    claims = {
        "urn:zitadel:iam:org:project:roles": {
            "platform_admin": {},
            "viewer": {},
        }
    }
    assert _is_super_admin_claims(claims) is True


def test_break_glass_master_key_sets_super_admin_context() -> None:
    request = _request_with_auth("sk-break-glass")

    with patch("alchemi.middleware.account_middleware._get_master_key", return_value="sk-break-glass"):
        resolve_tenant_from_request(request)

    assert is_super_admin() is True
    assert get_current_account_id() is None


def test_regular_jwt_claim_sets_account_context() -> None:
    request = _request_with_auth("jwt-token")
    decoded_claims = {"sub": "user-1", "account_id": "acct-123"}

    with (
        patch("alchemi.middleware.account_middleware._get_master_key", return_value="sk-master"),
        patch("alchemi.middleware.account_middleware.decode_jwt_token", return_value=decoded_claims),
    ):
        resolve_tenant_from_request(request)

    assert is_super_admin() is False
    assert get_current_account_id() == "acct-123"
