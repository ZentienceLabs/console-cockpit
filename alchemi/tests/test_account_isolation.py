"""
Account Isolation Validation Tests

Tests that middleware and auth guards correctly enforce:
1. Account context resolution from JWT claims
2. Super admin vs account_admin vs end_user role detection
3. Account-scoped query isolation (account_id propagation)
4. JWT validation error logging
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from alchemi.middleware.account_middleware import (
    _decode_zitadel_token,
    _extract_account_id_from_claims,
    _is_super_admin_claims,
    _is_account_admin_claims,
    _resolve_actor_role,
    _collect_role_candidates,
    resolve_tenant_from_request,
    extract_token_from_request,
    decode_jwt_token,
)
from alchemi.middleware.tenant_context import (
    get_current_account_id,
    is_super_admin,
    get_actor_role,
    set_current_account_id,
    set_super_admin,
    set_actor_role,
)


class TestExtractAccountIdFromClaims:
    """Test account_id extraction from various JWT claim formats."""

    def test_direct_account_id(self):
        claims = {"account_id": "acc-123"}
        assert _extract_account_id_from_claims(claims) == "acc-123"

    def test_tenant_id_fallback(self):
        claims = {"tenant_id": "tenant-456"}
        assert _extract_account_id_from_claims(claims) == "tenant-456"

    def test_urn_format(self):
        claims = {"urn:alchemi:account_id": "acc-urn-789"}
        assert _extract_account_id_from_claims(claims) == "acc-urn-789"

    def test_no_account_id(self):
        claims = {"sub": "user-1", "email": "user@example.com"}
        assert _extract_account_id_from_claims(claims) is None

    def test_custom_claim_keys(self):
        with patch.dict(os.environ, {"ZITADEL_ACCOUNT_ID_CLAIMS": "custom_field"}):
            claims = {"custom_field": "custom-acc-1"}
            assert _extract_account_id_from_claims(claims) == "custom-acc-1"


class TestCollectRoleCandidates:
    """Test role collection from various JWT claim shapes."""

    def test_list_roles(self):
        claims = {"roles": ["super_admin", "viewer"]}
        result = _collect_role_candidates(claims)
        assert "super_admin" in result
        assert "viewer" in result

    def test_dict_roles_zitadel_format(self):
        claims = {"urn:zitadel:iam:org:project:roles": {"super_admin": {"org": "123"}}}
        result = _collect_role_candidates(claims)
        assert "super_admin" in result

    def test_string_role(self):
        claims = {"role": "account_admin"}
        result = _collect_role_candidates(claims)
        assert "account_admin" in result

    def test_user_role_field(self):
        claims = {"user_role": "Admin"}
        result = _collect_role_candidates(claims)
        assert "admin" in result

    def test_empty_claims(self):
        result = _collect_role_candidates({})
        assert result == []


class TestSuperAdminDetection:
    """Test super admin detection from JWT claims."""

    def test_explicit_is_super_admin(self):
        assert _is_super_admin_claims({"is_super_admin": True}) is True

    def test_role_super_admin(self):
        assert _is_super_admin_claims({"roles": ["super_admin"]}) is True

    def test_role_platform_admin(self):
        assert _is_super_admin_claims({"role": "platform_admin"}) is True

    def test_zitadel_roles_super_admin(self):
        claims = {"urn:zitadel:iam:org:project:roles": {"alchemi_super_admin": {}}}
        assert _is_super_admin_claims(claims) is True

    def test_not_super_admin(self):
        assert _is_super_admin_claims({"roles": ["account_admin"]}) is False

    def test_custom_super_admin_roles(self):
        with patch.dict(os.environ, {"ZITADEL_SUPER_ADMIN_ROLE_KEYS": "god_mode"}):
            assert _is_super_admin_claims({"roles": ["god_mode"]}) is True
            assert _is_super_admin_claims({"roles": ["super_admin"]}) is False


class TestAccountAdminDetection:
    """Test account_admin role detection from JWT claims."""

    def test_role_account_admin(self):
        assert _is_account_admin_claims({"roles": ["account_admin"]}) is True

    def test_role_org_admin(self):
        assert _is_account_admin_claims({"role": "org_admin"}) is True

    def test_role_tenant_admin(self):
        assert _is_account_admin_claims({"user_role": "tenant_admin"}) is True

    def test_role_admin(self):
        assert _is_account_admin_claims({"role": "admin"}) is True

    def test_not_admin(self):
        assert _is_account_admin_claims({"roles": ["viewer"]}) is False

    def test_custom_admin_roles(self):
        with patch.dict(os.environ, {"ZITADEL_ACCOUNT_ADMIN_ROLE_KEYS": "manager"}):
            assert _is_account_admin_claims({"roles": ["manager"]}) is True
            assert _is_account_admin_claims({"roles": ["account_admin"]}) is False


class TestResolveActorRole:
    """Test role resolution priority: super_admin > account_admin > end_user."""

    def test_super_admin_priority(self):
        claims = {"is_super_admin": True, "roles": ["account_admin"]}
        assert _resolve_actor_role(claims) == "super_admin"

    def test_account_admin(self):
        claims = {"roles": ["account_admin"]}
        assert _resolve_actor_role(claims) == "account_admin"

    def test_end_user_default(self):
        claims = {"sub": "user-1"}
        assert _resolve_actor_role(claims) == "end_user"

    def test_viewer_maps_to_end_user(self):
        claims = {"roles": ["viewer"]}
        assert _resolve_actor_role(claims) == "end_user"


class TestExtractTokenFromRequest:
    """Test token extraction from various request sources."""

    def _make_request(self, cookies=None, headers=None):
        req = MagicMock()
        req.cookies = cookies or {}
        req.headers = headers or {}
        return req

    def test_cookie_token(self):
        req = self._make_request(cookies={"token": "cookie-jwt"})
        assert extract_token_from_request(req) == "cookie-jwt"

    def test_bearer_header(self):
        req = self._make_request(headers={"authorization": "Bearer header-jwt"})
        assert extract_token_from_request(req) == "header-jwt"

    def test_litellm_header(self):
        req = self._make_request(headers={"x-litellm-api-key": "litellm-key"})
        assert extract_token_from_request(req) == "litellm-key"

    def test_cookie_takes_priority_over_header(self):
        req = self._make_request(
            cookies={"token": "cookie-jwt"},
            headers={"authorization": "Bearer header-jwt"},
        )
        assert extract_token_from_request(req) == "cookie-jwt"

    def test_no_token(self):
        req = self._make_request()
        assert extract_token_from_request(req) is None


class TestTenantContextVars:
    """Test that contextvars are set correctly."""

    def test_account_id_set_and_read(self):
        set_current_account_id("test-acc")
        assert get_current_account_id() == "test-acc"
        set_current_account_id(None)

    def test_super_admin_set_and_read(self):
        set_super_admin(True)
        assert is_super_admin() is True
        set_super_admin(False)

    def test_actor_role_set_and_read(self):
        set_actor_role("account_admin")
        assert get_actor_role() == "account_admin"
        set_actor_role("end_user")

    def test_default_values(self):
        set_current_account_id(None)
        set_super_admin(False)
        set_actor_role("end_user")
        assert get_current_account_id() is None
        assert is_super_admin() is False
        assert get_actor_role() == "end_user"


class TestResolveTenantFromRequest:
    """Test full tenant resolution flow."""

    def _make_request(self, cookies=None, headers=None, query_params=None):
        req = MagicMock()
        req.cookies = cookies or {}
        req.headers = headers or {}
        req.query_params = query_params or {}
        return req

    @patch("alchemi.middleware.account_middleware._get_master_key", return_value="test-master-key")
    def test_master_key_sets_super_admin(self, _mock_key):
        req = self._make_request(headers={"authorization": "Bearer test-master-key"})
        resolve_tenant_from_request(req)
        assert is_super_admin() is True
        assert get_actor_role() == "super_admin"
        assert get_current_account_id() is None
        # Reset
        set_super_admin(False)
        set_actor_role("end_user")

    @patch("alchemi.middleware.account_middleware._get_master_key", return_value="other-key")
    @patch("alchemi.middleware.account_middleware.decode_jwt_token")
    def test_jwt_with_account_id(self, mock_decode, _mock_key):
        mock_decode.return_value = {
            "sub": "user-1",
            "account_id": "acc-xyz",
            "roles": ["account_admin"],
        }
        req = self._make_request(headers={"authorization": "Bearer some-jwt"})
        resolve_tenant_from_request(req)
        assert get_current_account_id() == "acc-xyz"
        assert is_super_admin() is False
        assert get_actor_role() == "account_admin"
        # Reset
        set_current_account_id(None)
        set_actor_role("end_user")

    def test_no_token_resets_context(self):
        set_current_account_id("old-acc")
        set_super_admin(True)
        set_actor_role("super_admin")
        req = self._make_request()
        resolve_tenant_from_request(req)
        assert get_current_account_id() is None
        assert is_super_admin() is False
        assert get_actor_role() == "end_user"
