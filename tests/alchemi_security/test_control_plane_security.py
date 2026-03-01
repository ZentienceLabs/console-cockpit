import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from alchemi.middleware.account_middleware import resolve_tenant_from_request
from alchemi.middleware.tenant_context import (
    get_current_account_id,
    get_current_product_domains,
    get_current_roles,
    get_current_scopes,
    is_super_admin,
    set_current_account_id,
    set_current_product_domains,
    set_current_roles,
    set_current_scopes,
    set_super_admin,
)
from alchemi.policy.control_plane_policy import (
    require_account_admin,
    require_domain_admin,
    require_super_admin,
)


def _reset_context() -> None:
    set_current_account_id(None)
    set_super_admin(False)
    set_current_roles([])
    set_current_scopes([])
    set_current_product_domains([])


def _make_request(path: str = "/v1/copilot/orgs", headers: dict[str, str] | None = None) -> Request:
    encoded_headers = []
    for key, value in (headers or {}).items():
        encoded_headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": encoded_headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _clean_context():
    _reset_context()
    yield
    _reset_context()


def test_require_domain_admin_blocks_wrong_domain_membership():
    set_current_account_id("acc-1")
    set_current_roles(["account_admin"])
    set_current_product_domains(["console"])

    with pytest.raises(HTTPException) as err:
        require_domain_admin("copilot")

    assert err.value.status_code == 403
    assert "Domain access denied" in str(err.value.detail)


def test_require_domain_admin_allows_scope_override():
    set_current_account_id("acc-1")
    set_current_scopes(["copilot:admin"])

    account_id = require_domain_admin("copilot")
    assert account_id == "acc-1"


def test_require_account_admin_rejects_missing_account_context():
    with pytest.raises(HTTPException) as err:
        require_account_admin()

    assert err.value.status_code == 403
    assert err.value.detail == "Account context required"


def test_require_super_admin_rejects_non_super_user():
    set_current_account_id("acc-1")
    set_current_roles(["account_admin"])

    with pytest.raises(HTTPException) as err:
        require_super_admin()

    assert err.value.status_code == 403
    assert err.value.detail == "Super admin access required"


def test_resolve_tenant_accepts_master_key_with_explicit_account(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "master-secret")
    request = _make_request(
        headers={
            "authorization": "Bearer master-secret",
            "x-account-id": "acc-master-scoped",
        }
    )

    resolve_tenant_from_request(request)

    assert is_super_admin() is True
    assert get_current_account_id() == "acc-master-scoped"


def test_resolve_tenant_rejects_tampered_jwt(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LITELLM_MASTER_KEY", "expected-secret")
    monkeypatch.setenv("ZITADEL_ENABLED", "false")
    tampered_token = jwt.encode({"account_id": "acc-evil", "roles": ["super_admin"]}, "wrong-secret", algorithm="HS256")
    request = _make_request(headers={"authorization": f"Bearer {tampered_token}"})

    resolve_tenant_from_request(request)

    assert is_super_admin() is False
    assert get_current_account_id() is None
    assert get_current_roles() == []
    assert get_current_scopes() == []
    assert get_current_product_domains() == []
