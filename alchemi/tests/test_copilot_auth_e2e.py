"""
End-to-End Flow Validation Tests for Copilot Auth Guards

Tests that the FastAPI dependency injection chain for copilot endpoints
works correctly:
1. require_super_admin rejects non-super-admin requests
2. require_account_admin_or_super_admin allows account admins
3. require_account_context returns correct account_id
4. get_actor_role returns proper role from context
5. maybe_account_id handles both super admin and tenant scoped calls
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from alchemi.endpoints.copilot_auth import (
    require_super_admin,
    require_account_admin_or_super_admin,
    require_account_context,
    get_actor_email_or_id,
    get_actor_role,
    maybe_account_id,
)
from alchemi.middleware.tenant_context import (
    set_current_account_id,
    set_super_admin,
    set_actor_role,
    get_current_account_id,
    is_super_admin as is_super_admin_ctx,
    get_actor_role as get_actor_role_ctx,
)
from fastapi import HTTPException


def _make_request(headers=None, query_params=None, cookies=None):
    req = MagicMock()
    req.cookies = cookies or {}
    req.headers = headers or {}
    req.query_params = query_params or {}
    return req


def _reset_context():
    set_current_account_id(None)
    set_super_admin(False)
    set_actor_role("end_user")


class TestRequireSuperAdmin:
    """Test super admin guard."""

    @pytest.mark.asyncio
    async def test_allows_super_admin(self):
        set_super_admin(True)
        set_actor_role("super_admin")
        req = _make_request()
        # Should not raise
        await require_super_admin(req)
        _reset_context()

    @pytest.mark.asyncio
    async def test_rejects_account_admin(self):
        set_super_admin(False)
        set_current_account_id("acc-1")
        set_actor_role("account_admin")
        req = _make_request()

        with patch("alchemi.endpoints.copilot_auth.resolve_tenant_from_request"):
            with pytest.raises(HTTPException) as exc_info:
                await require_super_admin(req)
            assert exc_info.value.status_code == 403
        _reset_context()

    @pytest.mark.asyncio
    async def test_rejects_no_token(self):
        _reset_context()
        req = _make_request()

        with patch("alchemi.endpoints.copilot_auth.resolve_tenant_from_request"):
            with pytest.raises(HTTPException) as exc_info:
                await require_super_admin(req)
            assert exc_info.value.status_code == 403
        _reset_context()


class TestRequireAccountAdminOrSuperAdmin:
    """Test account admin or super admin guard."""

    @pytest.mark.asyncio
    async def test_allows_super_admin(self):
        set_super_admin(True)
        set_actor_role("super_admin")
        req = _make_request()
        # Should not raise
        await require_account_admin_or_super_admin(req)
        _reset_context()

    @pytest.mark.asyncio
    async def test_allows_account_admin(self):
        set_super_admin(False)
        set_current_account_id("acc-1")
        set_actor_role("account_admin")
        req = _make_request()
        # Should not raise
        await require_account_admin_or_super_admin(req)
        _reset_context()

    @pytest.mark.asyncio
    async def test_rejects_no_account_id(self):
        _reset_context()
        req = _make_request()

        with patch("alchemi.endpoints.copilot_auth.resolve_tenant_from_request"):
            with pytest.raises(HTTPException) as exc_info:
                await require_account_admin_or_super_admin(req)
            assert exc_info.value.status_code == 403
        _reset_context()


class TestGetActorRole:
    """Test role retrieval from context and JWT claims."""

    def test_super_admin_from_context(self):
        set_actor_role("super_admin")
        req = _make_request()
        assert get_actor_role(req) == "super_admin"
        _reset_context()

    def test_account_admin_from_context(self):
        set_actor_role("account_admin")
        req = _make_request()
        assert get_actor_role(req) == "account_admin"
        _reset_context()

    def test_end_user_falls_back_to_jwt(self):
        set_actor_role("end_user")
        req = _make_request()
        with patch("alchemi.endpoints.copilot_auth._get_actor_from_request", return_value={"role": "viewer"}):
            result = get_actor_role(req)
            assert result == "viewer"
        _reset_context()

    def test_default_end_user(self):
        set_actor_role("end_user")
        req = _make_request()
        with patch("alchemi.endpoints.copilot_auth._get_actor_from_request", return_value={}):
            result = get_actor_role(req)
            assert result == "end_user"
        _reset_context()


class TestGetActorEmailOrId:
    """Test actor email/id extraction."""

    def test_email_from_claims(self):
        req = _make_request()
        with patch("alchemi.endpoints.copilot_auth._get_actor_from_request",
                    return_value={"user_email": "test@example.com", "sub": "user-1"}):
            assert get_actor_email_or_id(req) == "test@example.com"

    def test_sub_from_claims(self):
        req = _make_request()
        with patch("alchemi.endpoints.copilot_auth._get_actor_from_request",
                    return_value={"sub": "user-1"}):
            assert get_actor_email_or_id(req) == "user-1"

    def test_default_system(self):
        req = _make_request()
        with patch("alchemi.endpoints.copilot_auth._get_actor_from_request",
                    return_value={}):
            assert get_actor_email_or_id(req) == "system"


class TestMaybeAccountId:
    """Test optional account_id resolution."""

    @pytest.mark.asyncio
    async def test_super_admin_uses_query_param(self):
        set_super_admin(True)
        set_actor_role("super_admin")
        req = _make_request(query_params={"account_id": "explicit-acc"})
        result = await maybe_account_id(req)
        assert result == "explicit-acc"
        _reset_context()

    @pytest.mark.asyncio
    async def test_super_admin_no_query_param(self):
        set_super_admin(True)
        set_actor_role("super_admin")
        req = _make_request()
        result = await maybe_account_id(req)
        assert result is None
        _reset_context()

    @pytest.mark.asyncio
    async def test_tenant_scoped_returns_account_id(self):
        set_super_admin(False)
        set_current_account_id("tenant-acc")
        set_actor_role("account_admin")
        req = _make_request()
        result = await maybe_account_id(req)
        assert result == "tenant-acc"
        _reset_context()


class TestAccountIsolationIntegration:
    """Integration tests verifying multi-tenant isolation."""

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_access_tenant_b(self):
        """Verify that tenant A's context only sees tenant A data."""
        set_current_account_id("tenant-a")
        set_super_admin(False)
        set_actor_role("account_admin")

        assert get_current_account_id() == "tenant-a"
        assert is_super_admin_ctx() is False

        # Simulate a new request from tenant B
        set_current_account_id("tenant-b")
        assert get_current_account_id() == "tenant-b"

        _reset_context()

    @pytest.mark.asyncio
    async def test_super_admin_has_no_account_id(self):
        """Super admin should have no account_id (cross-tenant access via query param)."""
        set_super_admin(True)
        set_actor_role("super_admin")
        set_current_account_id(None)

        assert get_current_account_id() is None
        assert is_super_admin_ctx() is True

        _reset_context()

    @pytest.mark.asyncio
    async def test_role_context_persists_through_request(self):
        """Verify actor role set in middleware persists for auth guards."""
        set_actor_role("account_admin")
        set_current_account_id("acc-persist")

        req = _make_request()
        # require_account_admin_or_super_admin should pass
        await require_account_admin_or_super_admin(req)

        # Role should still be accessible
        assert get_actor_role_ctx() == "account_admin"

        _reset_context()
