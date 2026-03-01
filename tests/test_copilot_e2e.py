"""
End-to-end tests for all copilot endpoints.

Runs against a live proxy server at http://localhost:4000.
Uses a tenant-scoped JWT for CRUD operations and master key for super admin endpoints.

Usage:
    poetry run pytest tests/test_copilot_e2e.py -v -p no:retry
"""
import os
import uuid

import httpx
import jwt
import pytest

BASE_URL = os.getenv("COPILOT_TEST_BASE_URL", "http://localhost:4000")
API_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-alchemi-master-2026")
SUPER_ADMIN_HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
TEST_ACCOUNT_ID = os.getenv("COPILOT_TEST_ACCOUNT_ID", "")


def _get_account_id(client: httpx.Client) -> str:
    global TEST_ACCOUNT_ID
    if TEST_ACCOUNT_ID:
        return TEST_ACCOUNT_ID
    resp = client.get("/account/list", headers=SUPER_ADMIN_HEADERS)
    assert resp.status_code == 200, f"Failed to list accounts: {resp.text}"
    accounts = resp.json().get("accounts", [])
    if len(accounts) == 0:
        create_resp = client.post(
            "/account/new",
            headers=SUPER_ADMIN_HEADERS,
            json={"account_name": "Copilot E2E Account"},
        )
        assert create_resp.status_code in (200, 201), f"Failed to create test account: {create_resp.text}"
        resp = client.get("/account/list", headers=SUPER_ADMIN_HEADERS)
        assert resp.status_code == 200, f"Failed to list accounts after create: {resp.text}"
        accounts = resp.json().get("accounts", [])
    assert len(accounts) > 0, "No accounts in system for testing"
    TEST_ACCOUNT_ID = accounts[0]["account_id"]
    return TEST_ACCOUNT_ID


def _mint_tenant_jwt(account_id: str) -> str:
    """Mint a JWT for a specific account (tenant-scoped)."""
    return jwt.encode(
        {
            "user_id": "e2e-test-user",
            "user_email": "test@alchemi.co",
            "user_role": "proxy_admin",
            "account_id": account_id,
            "is_super_admin": False,
            "key": API_KEY,
            "login_method": "test",
        },
        API_KEY,
        algorithm="HS256",
    )


@pytest.fixture(scope="module")
def sa_client():
    """Super admin client (master key)."""
    with httpx.Client(base_url=BASE_URL, headers=SUPER_ADMIN_HEADERS, timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def account_id(sa_client: httpx.Client) -> str:
    return _get_account_id(sa_client)


@pytest.fixture(scope="module")
def client(account_id: str):
    """Tenant-scoped client (JWT with account_id)."""
    token = _mint_tenant_jwt(account_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=30) as c:
        yield c


# ============================================================
# 1. Credit Budget Endpoints
# ============================================================


class TestCopilotBudgets:
    """Test /copilot/budgets/* endpoints."""

    budget_id: str = ""
    child_budget_id: str = ""
    plan_id: str = ""
    scope_id: str = str(uuid.uuid4())

    def test_list_budgets(self, client: httpx.Client):
        resp = client.get("/copilot/budgets/")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "total" in data

    def test_create_budget(self, client: httpx.Client):
        payload = {
            "scope_type": "account",
            "scope_id": TestCopilotBudgets.scope_id,
            "allocated": 1000,
            "limit_amount": 500,
            "cycle_start": "2026-01-01T00:00:00Z",
            "cycle_end": "2026-12-31T23:59:59Z",
        }
        resp = client.post("/copilot/budgets/", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotBudgets.budget_id = data["data"]["id"]

    def test_get_budget(self, client: httpx.Client):
        assert TestCopilotBudgets.budget_id, "No budget_id from create"
        resp = client.get(f"/copilot/budgets/{TestCopilotBudgets.budget_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["id"] == TestCopilotBudgets.budget_id

    def test_update_budget(self, client: httpx.Client):
        assert TestCopilotBudgets.budget_id
        resp = client.put(
            f"/copilot/budgets/{TestCopilotBudgets.budget_id}",
            json={"allocated": 2000, "limit_amount": 1000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["allocated"] == 2000

    def test_budget_summary(self, client: httpx.Client):
        resp = client.get("/copilot/budgets/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_budget_alerts(self, client: httpx.Client):
        resp = client.get("/copilot/budgets/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_budget_allocation_overview(self, client: httpx.Client):
        resp = client.get("/copilot/budgets/allocation-overview")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data

    def test_allocate_budget_child(self, client: httpx.Client):
        assert TestCopilotBudgets.budget_id
        user_scope_id = str(uuid.uuid4())
        resp = client.post(
            f"/copilot/budgets/{TestCopilotBudgets.budget_id}/allocate",
            json={
                "target_scope_type": "user",
                "target_scope_id": user_scope_id,
                "allocated": 100,
                "limit_amount": 100,
                "allocation_strategy": "manual",
            },
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotBudgets.child_budget_id = data["data"]["id"]

    def test_record_usage(self, client: httpx.Client):
        assert TestCopilotBudgets.budget_id
        resp = client.post(
            "/copilot/budgets/record-usage",
            json={
                "scope_type": "account",
                "scope_id": TestCopilotBudgets.scope_id,
                "amount": 10,
            },
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data

    def test_create_budget_plan(self, client: httpx.Client):
        payload = {
            "name": "Test Plan " + uuid.uuid4().hex[:6],
            "is_active": True,
            "distribution": {"groups": [], "teams": [], "users": []},
        }
        resp = client.post("/copilot/budgets/plans", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotBudgets.plan_id = data["data"]["id"]

    def test_list_budget_plans(self, client: httpx.Client):
        resp = client.get("/copilot/budgets/plans")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_update_budget_plan(self, client: httpx.Client):
        assert TestCopilotBudgets.plan_id
        resp = client.put(
            f"/copilot/budgets/plans/{TestCopilotBudgets.plan_id}",
            json={"name": "Updated Plan"},
        )
        assert resp.status_code == 200

    def test_delete_budget_plan(self, client: httpx.Client):
        assert TestCopilotBudgets.plan_id
        resp = client.delete(f"/copilot/budgets/plans/{TestCopilotBudgets.plan_id}")
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

    def test_delete_budget(self, client: httpx.Client):
        if TestCopilotBudgets.child_budget_id:
            resp_child = client.delete(f"/copilot/budgets/{TestCopilotBudgets.child_budget_id}")
            assert resp_child.status_code == 200
        assert TestCopilotBudgets.budget_id
        resp = client.delete(f"/copilot/budgets/{TestCopilotBudgets.budget_id}")
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"


# ============================================================
# 2. Agent Endpoints
# ============================================================


class TestCopilotAgents:
    """Test /copilot/agents/* endpoints."""

    agent_id: str = ""
    group_id: str = ""

    def test_list_agents(self, client: httpx.Client):
        resp = client.get("/copilot/agents/")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_create_agent(self, client: httpx.Client):
        payload = {
            "name": "Test Agent " + uuid.uuid4().hex[:6],
            "description": "E2E test agent",
            "prompt": "You are a test agent.",
            "status": "active",
            "provider": "PLATFORM",
        }
        resp = client.post("/copilot/agents/", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotAgents.agent_id = data["data"]["agent_id"]

    def test_get_agent(self, client: httpx.Client):
        assert TestCopilotAgents.agent_id
        resp = client.get(f"/copilot/agents/{TestCopilotAgents.agent_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["agent_id"] == TestCopilotAgents.agent_id

    def test_update_agent(self, client: httpx.Client):
        assert TestCopilotAgents.agent_id
        resp = client.put(
            f"/copilot/agents/{TestCopilotAgents.agent_id}",
            json={"description": "Updated description"},
        )
        assert resp.status_code == 200

    def test_create_agent_group(self, client: httpx.Client):
        payload = {
            "group_code": "test-group-" + uuid.uuid4().hex[:6],
            "name": "Test Group",
            "description": "E2E test group",
            "group_type": "custom",
        }
        resp = client.post("/copilot/agents/groups", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotAgents.group_id = data["data"]["id"]

    def test_list_agent_groups(self, client: httpx.Client):
        resp = client.get("/copilot/agents/groups")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_update_agent_group(self, client: httpx.Client):
        assert TestCopilotAgents.group_id
        resp = client.put(
            f"/copilot/agents/groups/{TestCopilotAgents.group_id}",
            json={"name": "Updated Group"},
        )
        assert resp.status_code == 200

    def test_add_group_member(self, client: httpx.Client):
        assert TestCopilotAgents.group_id and TestCopilotAgents.agent_id
        resp = client.post(
            f"/copilot/agents/groups/{TestCopilotAgents.group_id}/members",
            json={"agent_id": TestCopilotAgents.agent_id, "display_order": 1},
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"

    def test_remove_group_member(self, client: httpx.Client):
        assert TestCopilotAgents.group_id and TestCopilotAgents.agent_id
        resp = client.delete(
            f"/copilot/agents/groups/{TestCopilotAgents.group_id}/members/{TestCopilotAgents.agent_id}"
        )
        assert resp.status_code == 200

    def test_delete_agent_group(self, client: httpx.Client):
        assert TestCopilotAgents.group_id
        resp = client.delete(f"/copilot/agents/groups/{TestCopilotAgents.group_id}")
        assert resp.status_code == 200

    def test_delete_agent(self, client: httpx.Client):
        assert TestCopilotAgents.agent_id
        resp = client.delete(f"/copilot/agents/{TestCopilotAgents.agent_id}")
        assert resp.status_code == 200


# ============================================================
# 3. Marketplace Endpoints
# ============================================================


class TestCopilotMarketplace:
    """Test /copilot/marketplace/* endpoints."""

    item_id: str = ""

    def test_list_marketplace(self, client: httpx.Client):
        resp = client.get("/copilot/marketplace/")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_featured_items(self, client: httpx.Client):
        resp = client.get("/copilot/marketplace/featured")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_marketplace_item(self, client: httpx.Client):
        payload = {
            "entity_id": str(uuid.uuid4()),
            "entity_type": "agent",
            "provider": "PLATFORM",
            "title": "Test Marketplace Item " + uuid.uuid4().hex[:6],
            "short_description": "An E2E test item",
            "pricing_model": "free",
        }
        resp = client.post("/copilot/marketplace/", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        # marketplace_items uses marketplace_id as id_column
        TestCopilotMarketplace.item_id = data["data"].get("marketplace_id") or data["data"].get("id")

    def test_get_marketplace_item(self, client: httpx.Client):
        assert TestCopilotMarketplace.item_id
        resp = client.get(f"/copilot/marketplace/{TestCopilotMarketplace.item_id}")
        assert resp.status_code == 200

    def test_update_marketplace_item(self, client: httpx.Client):
        assert TestCopilotMarketplace.item_id
        resp = client.put(
            f"/copilot/marketplace/{TestCopilotMarketplace.item_id}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200

    def test_install_marketplace_item(self, client: httpx.Client):
        assert TestCopilotMarketplace.item_id
        resp = client.post(
            f"/copilot/marketplace/{TestCopilotMarketplace.item_id}/install"
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"

    def test_install_marketplace_item_with_assignments(self, client: httpx.Client, account_id: str):
        assert TestCopilotMarketplace.item_id
        payload = {
            "assignments": [
                {"scope_type": "account", "scope_id": account_id},
                {"scope_type": "user", "scope_id": "test@alchemi.co"},
            ]
        }
        resp = client.post(
            f"/copilot/marketplace/{TestCopilotMarketplace.item_id}/install",
            json=payload,
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        metadata = data.get("data", {}).get("metadata") or {}
        assignments = metadata.get("assignments") or []
        assert len(assignments) >= 1

    def test_delete_marketplace_item(self, client: httpx.Client):
        assert TestCopilotMarketplace.item_id
        resp = client.delete(
            f"/copilot/marketplace/{TestCopilotMarketplace.item_id}"
        )
        assert resp.status_code == 200


# ============================================================
# 4. Connection Endpoints
# ============================================================


class TestCopilotConnections:
    """Test /copilot/connections/* endpoints."""

    conn_id: str = ""

    def test_list_connections(self, client: httpx.Client):
        resp = client.get("/copilot/connections/")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_connection(self, client: httpx.Client):
        payload = {
            "connection_type": "mcp",
            "name": "Test MCP Connection " + uuid.uuid4().hex[:6],
            "description": "E2E test MCP connection",
            "connection_data": {
                "url": "http://localhost:3000/mcp",
                "auth_type": "none",
            },
            "is_active": True,
        }
        resp = client.post("/copilot/connections/", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotConnections.conn_id = data["data"]["id"]

    def test_get_connection(self, client: httpx.Client):
        assert TestCopilotConnections.conn_id
        resp = client.get(f"/copilot/connections/{TestCopilotConnections.conn_id}")
        assert resp.status_code == 200

    def test_update_connection(self, client: httpx.Client):
        assert TestCopilotConnections.conn_id
        resp = client.put(
            f"/copilot/connections/{TestCopilotConnections.conn_id}",
            json={"description": "Updated connection"},
        )
        assert resp.status_code == 200

    def test_test_connection(self, client: httpx.Client):
        assert TestCopilotConnections.conn_id
        resp = client.post(
            f"/copilot/connections/{TestCopilotConnections.conn_id}/test"
        )
        # Endpoint should respond (MCP server may not exist, so accept error status too)
        assert resp.status_code == 200

    def test_delete_connection(self, client: httpx.Client):
        assert TestCopilotConnections.conn_id
        resp = client.delete(
            f"/copilot/connections/{TestCopilotConnections.conn_id}"
        )
        assert resp.status_code == 200


# ============================================================
# 5. Guardrails Endpoints
# ============================================================


class TestCopilotGuardrails:
    """Test /copilot/guardrails/* endpoints."""

    pattern_id: str = ""

    def test_list_guardrails_config(self, client: httpx.Client):
        resp = client.get("/copilot/guardrails/config")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_upsert_guardrails_config(self, client: httpx.Client):
        payload = {
            "enabled": True,
            "action_on_fail": "flag",
            "config": {"sensitivity": "medium"},
        }
        resp = client.put("/copilot/guardrails/config/pii", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"

    def test_get_guardrails_config(self, client: httpx.Client):
        resp = client.get("/copilot/guardrails/config/pii")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_toggle_guardrail(self, client: httpx.Client):
        resp = client.patch(
            "/copilot/guardrails/config/pii/toggle",
            json={"enabled": False},
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"

    def test_create_guardrail_pattern(self, client: httpx.Client):
        payload = {
            "guard_type": "pii",
            "pattern_name": "SSN Pattern " + uuid.uuid4().hex[:6],
            "pattern_regex": r"\d{3}-\d{2}-\d{4}",
            "pattern_type": "detect",
            "action": "mask",
            "severity": "high",
        }
        resp = client.post("/copilot/guardrails/patterns", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotGuardrails.pattern_id = data["data"]["id"]

    def test_list_guardrail_patterns(self, client: httpx.Client):
        resp = client.get("/copilot/guardrails/patterns")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_update_guardrail_pattern(self, client: httpx.Client):
        assert TestCopilotGuardrails.pattern_id
        resp = client.put(
            f"/copilot/guardrails/patterns/{TestCopilotGuardrails.pattern_id}",
            json={"severity": "critical"},
        )
        assert resp.status_code == 200

    def test_guardrail_audit_log(self, client: httpx.Client):
        resp = client.get("/copilot/guardrails/audit")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_delete_guardrail_pattern(self, client: httpx.Client):
        assert TestCopilotGuardrails.pattern_id
        resp = client.delete(
            f"/copilot/guardrails/patterns/{TestCopilotGuardrails.pattern_id}"
        )
        assert resp.status_code == 200


# ============================================================
# 6. Entitlements Endpoints
# ============================================================


class TestCopilotEntitlements:
    """Test /copilot/entitlements/* endpoints (super admin only)."""

    def test_get_entitlements(self, sa_client: httpx.Client, account_id: str):
        resp = sa_client.get(f"/copilot/entitlements/{account_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "account_id" in data
        assert "entitlements" in data

    def test_update_entitlements(self, sa_client: httpx.Client, account_id: str):
        payload = {
            "max_models": 50,
            "max_keys": 100,
            "features": {
                "copilot_budgets": True,
                "copilot_agents": True,
                "playground": True,
            },
        }
        resp = sa_client.put(
            f"/copilot/entitlements/{account_id}", json=payload
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data["entitlements"]["max_models"] == 50
        assert data["entitlements"]["features"]["copilot_budgets"] is True

    def test_get_updated_entitlements(self, sa_client: httpx.Client, account_id: str):
        resp = sa_client.get(f"/copilot/entitlements/{account_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entitlements"]["max_models"] == 50


# ============================================================
# 7. Copilot Directory Endpoints
# ============================================================


class TestCopilotDirectory:
    """Test /copilot/{users,memberships,groups,teams,invites} endpoints."""

    user_id: str = ""
    group_id: str = ""
    team_id: str = ""
    invite_accept_id: str = ""
    invite_reject_id: str = ""

    def test_list_users(self, client: httpx.Client):
        resp = client.get("/copilot/users")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        assert "users" in data["data"]

    def test_create_user(self, client: httpx.Client):
        payload = {
            "email": f"copilot-e2e-{uuid.uuid4().hex[:8]}@example.com",
            "name": "Copilot E2E User",
            "app_role": "USER",
        }
        resp = client.post("/copilot/users", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        created = resp.json().get("data", {})
        user = created.get("user", {})
        assert user.get("id")
        TestCopilotDirectory.user_id = user["id"]

    def test_create_group(self, client: httpx.Client):
        payload = {
            "name": "E2E Group " + uuid.uuid4().hex[:6],
            "description": "Directory group test",
        }
        resp = client.post("/copilot/groups", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotDirectory.group_id = data["data"]["id"]

    def test_create_team(self, client: httpx.Client):
        assert TestCopilotDirectory.group_id
        payload = {
            "group_id": TestCopilotDirectory.group_id,
            "name": "E2E Team " + uuid.uuid4().hex[:6],
            "description": "Directory team test",
        }
        resp = client.post("/copilot/teams", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        TestCopilotDirectory.team_id = data["data"]["id"]

    def test_assign_team_member(self, client: httpx.Client):
        assert TestCopilotDirectory.team_id and TestCopilotDirectory.user_id
        resp = client.post(
            f"/copilot/teams/{TestCopilotDirectory.team_id}/members",
            json={"user_id": TestCopilotDirectory.user_id},
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"

    def test_list_memberships(self, client: httpx.Client):
        resp = client.get("/copilot/memberships?limit=200&offset=0")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_create_invites(self, client: httpx.Client):
        accept_payload = {
            "email": f"copilot-accept-{uuid.uuid4().hex[:8]}@example.com",
            "role": "USER",
            "expires_in_days": 7,
        }
        reject_payload = {
            "email": f"copilot-reject-{uuid.uuid4().hex[:8]}@example.com",
            "role": "USER",
            "expires_in_days": 7,
        }

        accept_resp = client.post("/copilot/invites", json=accept_payload)
        reject_resp = client.post("/copilot/invites", json=reject_payload)

        assert accept_resp.status_code == 200, f"Failed: {accept_resp.text}"
        assert reject_resp.status_code == 200, f"Failed: {reject_resp.text}"

        TestCopilotDirectory.invite_accept_id = accept_resp.json()["data"]["id"]
        TestCopilotDirectory.invite_reject_id = reject_resp.json()["data"]["id"]

    def test_accept_and_reject_invites(self, client: httpx.Client):
        assert TestCopilotDirectory.invite_accept_id
        assert TestCopilotDirectory.invite_reject_id

        accept_resp = client.post(
            f"/copilot/invites/{TestCopilotDirectory.invite_accept_id}/accept"
        )
        reject_resp = client.post(
            f"/copilot/invites/{TestCopilotDirectory.invite_reject_id}/reject"
        )

        assert accept_resp.status_code == 200, f"Failed: {accept_resp.text}"
        assert reject_resp.status_code == 200, f"Failed: {reject_resp.text}"

    def test_list_team_members(self, client: httpx.Client):
        assert TestCopilotDirectory.team_id
        resp = client.get(f"/copilot/teams/{TestCopilotDirectory.team_id}/members")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data

    def test_remove_team_member(self, client: httpx.Client):
        assert TestCopilotDirectory.team_id and TestCopilotDirectory.user_id
        resp = client.delete(
            f"/copilot/teams/{TestCopilotDirectory.team_id}/members/{TestCopilotDirectory.user_id}"
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"

    def test_delete_team_and_group(self, client: httpx.Client):
        assert TestCopilotDirectory.team_id and TestCopilotDirectory.group_id
        team_resp = client.delete(f"/copilot/teams/{TestCopilotDirectory.team_id}")
        group_resp = client.delete(f"/copilot/groups/{TestCopilotDirectory.group_id}")
        assert team_resp.status_code == 200, f"Failed: {team_resp.text}"
        assert group_resp.status_code == 200, f"Failed: {group_resp.text}"


# ============================================================
# 8. Notification Template Endpoints
# ============================================================


class TestCopilotNotificationTemplates:
    """Test /copilot/notification-templates/* endpoints."""

    template_id: str = ""

    def test_list_notification_templates(self, client: httpx.Client):
        resp = client.get("/copilot/notification-templates/")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_create_notification_template(self, client: httpx.Client):
        payload = {
            "template_id": "copilot-template-" + uuid.uuid4().hex[:8],
            "title_line": "Welcome {{user_name}}",
            "template_content": "<p>Hello {{user_name}}</p>",
            "event_id": "USER_WELCOME",
            "type": "EMAIL",
        }
        resp = client.post("/copilot/notification-templates/", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        created = resp.json().get("data", {})
        assert created.get("id")
        TestCopilotNotificationTemplates.template_id = created["id"]

    def test_notification_template_summary(self, client: httpx.Client):
        resp = client.get("/copilot/notification-templates/summary")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert "totals" in data
        assert "by_type" in data

    def test_get_notification_template(self, client: httpx.Client):
        assert TestCopilotNotificationTemplates.template_id
        resp = client.get(
            f"/copilot/notification-templates/{TestCopilotNotificationTemplates.template_id}"
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert data.get("id") == TestCopilotNotificationTemplates.template_id

    def test_update_notification_template(self, client: httpx.Client):
        assert TestCopilotNotificationTemplates.template_id
        resp = client.put(
            f"/copilot/notification-templates/{TestCopilotNotificationTemplates.template_id}",
            json={"title_line": "Updated title", "type": "IN_APP"},
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert data.get("title_line") == "Updated title"
        assert data.get("type") == "IN_APP"

    def test_bulk_delete_notification_templates(self, client: httpx.Client):
        payload = {
            "template_id": "copilot-template-bulk-" + uuid.uuid4().hex[:8],
            "title_line": "Bulk Delete Template",
            "template_content": "<p>bulk delete</p>",
            "event_id": "BULK_DELETE",
            "type": "EMAIL",
        }
        create_resp = client.post("/copilot/notification-templates/", json=payload)
        assert create_resp.status_code == 200, f"Failed: {create_resp.text}"
        created_id = create_resp.json().get("data", {}).get("id")
        assert created_id

        bulk_resp = client.post(
            "/copilot/notification-templates/bulk-delete",
            json={"template_ids": [created_id]},
        )
        assert bulk_resp.status_code == 200, f"Failed: {bulk_resp.text}"
        result = bulk_resp.json().get("data", {})
        assert result.get("deleted_count") == 1

    def test_delete_notification_template(self, client: httpx.Client):
        assert TestCopilotNotificationTemplates.template_id
        resp = client.delete(
            f"/copilot/notification-templates/{TestCopilotNotificationTemplates.template_id}"
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        assert resp.json().get("status") == "ok"


# ============================================================
# 9. Support Ticket Endpoints
# ============================================================


class TestCopilotSupportTickets:
    """Test /copilot/support-tickets/* endpoints."""

    ticket_id: str = ""
    user_profile_id: str = str(uuid.uuid4())

    def test_list_support_tickets(self, client: httpx.Client):
        resp = client.get("/copilot/support-tickets/")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_create_support_ticket(self, client: httpx.Client):
        payload = {
            "user_profile_id": TestCopilotSupportTickets.user_profile_id,
            "subject": "E2E Support Ticket " + uuid.uuid4().hex[:6],
            "description": "This is a support ticket from E2E test.",
            "priority": "MEDIUM",
            "status": "OPEN",
        }
        resp = client.post("/copilot/support-tickets/", json=payload)
        assert resp.status_code == 200, f"Failed: {resp.text}"
        created = resp.json().get("data", {})
        assert created.get("id")
        TestCopilotSupportTickets.ticket_id = created["id"]

    def test_support_ticket_summary(self, client: httpx.Client):
        resp = client.get("/copilot/support-tickets/summary")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert "totals" in data
        assert "by_status" in data

    def test_get_support_ticket(self, client: httpx.Client):
        assert TestCopilotSupportTickets.ticket_id
        resp = client.get(
            f"/copilot/support-tickets/{TestCopilotSupportTickets.ticket_id}"
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert data.get("id") == TestCopilotSupportTickets.ticket_id

    def test_update_support_ticket(self, client: httpx.Client):
        assert TestCopilotSupportTickets.ticket_id
        resp = client.put(
            f"/copilot/support-tickets/{TestCopilotSupportTickets.ticket_id}",
            json={"status": "IN_PROGRESS", "priority": "IMPORTANT"},
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert data.get("status") == "IN_PROGRESS"
        assert data.get("priority") == "IMPORTANT"

    def test_bulk_update_support_tickets(self, client: httpx.Client):
        assert TestCopilotSupportTickets.ticket_id
        resp = client.post(
            "/copilot/support-tickets/bulk-update",
            json={
                "ticket_ids": [TestCopilotSupportTickets.ticket_id],
                "status": "PENDING",
                "priority": "URGENT",
            },
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert data.get("updated_count") == 1

    def test_list_support_tickets_by_profile(self, client: httpx.Client):
        resp = client.get(
            "/copilot/support-tickets/",
            params={
                "user_profile_id": TestCopilotSupportTickets.user_profile_id,
                "include_user_profile": True,
                "include_assigned_to": True,
            },
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_delete_support_ticket(self, client: httpx.Client):
        assert TestCopilotSupportTickets.ticket_id
        resp = client.delete(
            f"/copilot/support-tickets/{TestCopilotSupportTickets.ticket_id}"
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        assert resp.json().get("status") == "ok"


# ============================================================
# 10. Legacy /alchemi Compatibility Endpoints
# ============================================================


class TestAlchemiLegacyCompatibility:
    """Verify legacy /alchemi/* list routes are available during migration."""

    LEGACY_ENABLED = os.getenv("ALCHEMI_ENABLE_LEGACY_COMPAT", "true").strip().lower() == "true"

    def test_legacy_budget_list(self, client: httpx.Client):
        resp = client.get("/alchemi/budget/list")
        if not self.LEGACY_ENABLED:
            assert resp.status_code == 404
            return
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "list" in data
        assert "total" in data

    def test_legacy_budget_plan_list(self, client: httpx.Client):
        resp = client.get("/alchemi/budget/plan/list")
        if not self.LEGACY_ENABLED:
            assert resp.status_code == 404
            return
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "plans" in data

    def test_legacy_group_list(self, client: httpx.Client):
        resp = client.get("/alchemi/group/list")
        if not self.LEGACY_ENABLED:
            assert resp.status_code == 404
            return
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "groups" in data

    def test_legacy_team_list(self, client: httpx.Client):
        resp = client.get("/alchemi/team/list")
        if not self.LEGACY_ENABLED:
            assert resp.status_code == 404
            return
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "teams" in data

    def test_legacy_connection_list(self, client: httpx.Client):
        resp = client.get("/alchemi/connection/list")
        if not self.LEGACY_ENABLED:
            assert resp.status_code == 404
            return
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "connections" in data

    def test_legacy_marketplace_list(self, client: httpx.Client):
        resp = client.get("/alchemi/marketplace/list")
        if not self.LEGACY_ENABLED:
            assert resp.status_code == 404
            return
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "marketplace" in data

    def test_legacy_workspace_list(self, client: httpx.Client):
        resp = client.get("/alchemi/workspace/list")
        if not self.LEGACY_ENABLED:
            assert resp.status_code == 404
            return
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "workspaces" in data
        assert isinstance(data["workspaces"], list)


# ============================================================
# 11. Copilot Model Selection Endpoints
# ============================================================


class TestCopilotModelSelection:
    def test_get_model_selection_super_admin(
        self, sa_client: httpx.Client, account_id: str
    ):
        resp = sa_client.get(
            "/copilot/models/selection", params={"account_id": account_id}
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "catalog_models" in data
        assert "selected_models" in data
        assert "effective_models" in data

    def test_get_model_selection_tenant(self, client: httpx.Client):
        resp = client.get("/copilot/models/selection")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "catalog_models" in data
        assert "effective_models" in data

    def test_update_model_selection_super_admin(
        self, sa_client: httpx.Client, account_id: str
    ):
        before = sa_client.get(
            "/copilot/models/selection", params={"account_id": account_id}
        )
        assert before.status_code == 200, f"Failed: {before.text}"
        catalog = before.json().get("catalog_models", [])
        selected = catalog[:1] if catalog else []

        resp = sa_client.put(
            "/copilot/models/selection",
            json={"account_id": account_id, "selected_models": selected},
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert data.get("selected_models") == selected

    def test_list_model_selection_accounts(
        self, sa_client: httpx.Client
    ):
        resp = sa_client.get("/copilot/models/selection/accounts")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        assert "total" in data

    def test_bulk_update_model_selection_super_admin(
        self, sa_client: httpx.Client, account_id: str
    ):
        before = sa_client.get(
            "/copilot/models/selection", params={"account_id": account_id}
        )
        assert before.status_code == 200, f"Failed: {before.text}"
        catalog = before.json().get("catalog_models", [])
        selected = catalog[:2] if len(catalog) > 1 else catalog

        resp = sa_client.put(
            "/copilot/models/selection/bulk",
            json={"account_ids": [account_id], "selected_models": selected},
        )
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json().get("data", {})
        assert data.get("updated_count") == 1

    def test_reject_invalid_model_selection(
        self, sa_client: httpx.Client, account_id: str
    ):
        resp = sa_client.put(
            "/copilot/models/selection",
            json={
                "account_id": account_id,
                "selected_models": ["non-existent-model-for-copilot-selection"],
            },
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


# ============================================================
# 12. Copilot Scoped Policy Endpoints
# ============================================================


class TestCopilotScopedPolicies:
    def test_model_policy_crud_and_resolve(
        self, sa_client: httpx.Client, account_id: str
    ):
        selection_resp = sa_client.get(
            "/copilot/models/selection", params={"account_id": account_id}
        )
        assert selection_resp.status_code == 200, f"Failed: {selection_resp.text}"
        catalog = selection_resp.json().get("catalog_models", [])
        if len(catalog) == 0:
            pytest.skip("No copilot model catalog configured for scoped policy test")

        selected = [catalog[0]]
        upsert_resp = sa_client.put(
            "/copilot/models/policies",
            json={
                "account_id": account_id,
                "scope_type": "account",
                "scope_id": account_id,
                "mode": "allowlist",
                "selected_models": selected,
            },
        )
        assert upsert_resp.status_code == 200, f"Failed: {upsert_resp.text}"

        list_resp = sa_client.get(
            "/copilot/models/policies",
            params={"account_id": account_id, "scope_type": "account", "scope_id": account_id},
        )
        assert list_resp.status_code == 200, f"Failed: {list_resp.text}"
        rows = list_resp.json().get("data", [])
        assert any(str(r.get("scope_id")) == account_id for r in rows)

        resolve_resp = sa_client.get(
            "/copilot/models/policies/resolve",
            params={"account_id": account_id, "scope_type": "account", "scope_id": account_id},
        )
        assert resolve_resp.status_code == 200, f"Failed: {resolve_resp.text}"
        effective = resolve_resp.json().get("effective_models", [])
        assert all(m in selected for m in effective), "effective models should respect account allowlist"

        delete_resp = sa_client.request(
            "DELETE",
            "/copilot/models/policies",
            json={"account_id": account_id, "scope_type": "account", "scope_id": account_id},
        )
        assert delete_resp.status_code == 200, f"Failed: {delete_resp.text}"

    def test_feature_policy_crud_and_resolve(
        self, sa_client: httpx.Client, account_id: str
    ):
        upsert_resp = sa_client.put(
            "/copilot/entitlements/features/policies",
            json={
                "account_id": account_id,
                "scope_type": "account",
                "scope_id": account_id,
                "flags": {"can_create_agents": False, "can_generate_images": True},
            },
        )
        assert upsert_resp.status_code == 200, f"Failed: {upsert_resp.text}"

        list_resp = sa_client.get(
            "/copilot/entitlements/features/policies",
            params={"account_id": account_id, "scope_type": "account", "scope_id": account_id},
        )
        assert list_resp.status_code == 200, f"Failed: {list_resp.text}"
        rows = list_resp.json().get("data", [])
        assert any(str(r.get("scope_id")) == account_id for r in rows)

        resolve_resp = sa_client.get(
            "/copilot/entitlements/features/resolve",
            params={"account_id": account_id, "scope_type": "account", "scope_id": account_id},
        )
        assert resolve_resp.status_code == 200, f"Failed: {resolve_resp.text}"
        effective = resolve_resp.json().get("effective_features", {})
        assert effective.get("can_create_agents") is False

        delete_resp = sa_client.request(
            "DELETE",
            "/copilot/entitlements/features/policies",
            json={"account_id": account_id, "scope_type": "account", "scope_id": account_id},
        )
        assert delete_resp.status_code == 200, f"Failed: {delete_resp.text}"

    def test_connection_permission_mode_crud_and_resolve(
        self, sa_client: httpx.Client, account_id: str
    ):
        upsert_resp = sa_client.put(
            "/copilot/connections/permission-modes",
            json={
                "account_id": account_id,
                "scope_type": "account",
                "scope_id": account_id,
                "connection_type": "mcp",
                "permission_mode": "self_managed_allowed",
                "allow_use_admin_connections": False,
            },
        )
        assert upsert_resp.status_code == 200, f"Failed: {upsert_resp.text}"

        list_resp = sa_client.get(
            "/copilot/connections/permission-modes",
            params={
                "account_id": account_id,
                "scope_type": "account",
                "scope_id": account_id,
                "connection_type": "mcp",
            },
        )
        assert list_resp.status_code == 200, f"Failed: {list_resp.text}"
        rows = list_resp.json().get("data", [])
        assert any(str(r.get("scope_id")) == account_id for r in rows)

        resolve_resp = sa_client.get(
            "/copilot/connections/permission-modes/resolve",
            params={
                "account_id": account_id,
                "scope_type": "account",
                "scope_id": account_id,
                "connection_type": "mcp",
            },
        )
        assert resolve_resp.status_code == 200, f"Failed: {resolve_resp.text}"
        data = resolve_resp.json()
        assert data.get("permission_mode") == "self_managed_allowed"
        assert data.get("allow_use_admin_connections") is False

        delete_resp = sa_client.request(
            "DELETE",
            "/copilot/connections/permission-modes",
            json={
                "account_id": account_id,
                "scope_type": "account",
                "scope_id": account_id,
                "connection_type": "mcp",
            },
        )
        assert delete_resp.status_code == 200, f"Failed: {delete_resp.text}"


# ============================================================
# 13. Copilot Global Ops Endpoints
# ============================================================


class TestCopilotGlobalOps:
    ticket_id: str = ""
    template_id: str = ""

    def test_get_global_summary(self, sa_client: httpx.Client):
        resp = sa_client.get("/copilot/ops/global/summary")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        payload = resp.json().get("data", {})
        assert "totals" in payload
        assert "by_account" in payload
        assert "generated_at" in payload

    def test_bulk_ticket_action(self, sa_client: httpx.Client, account_id: str):
        unique_subject = "Global Ops Ticket " + uuid.uuid4().hex[:8]
        create_resp = sa_client.post(
            "/copilot/support-tickets/",
            params={"account_id": account_id},
            json={
                "user_profile_id": "global-ops-user",
                "subject": unique_subject,
                "description": "Global ops bulk update test",
                "status": "OPEN",
                "priority": "LOW",
            },
        )
        assert create_resp.status_code == 200, f"Failed: {create_resp.text}"
        TestCopilotGlobalOps.ticket_id = create_resp.json().get("data", {}).get("id", "")
        assert TestCopilotGlobalOps.ticket_id

        bulk_resp = sa_client.post(
            "/copilot/ops/global/bulk/tickets",
            json={
                "account_ids": [account_id],
                "search_text": unique_subject,
                "status": "IN_PROGRESS",
                "priority": "URGENT",
                "limit": 50,
            },
        )
        assert bulk_resp.status_code == 200, f"Failed: {bulk_resp.text}"
        bulk_data = bulk_resp.json().get("data", {})
        assert bulk_data.get("matched_count", 0) >= 1
        assert bulk_data.get("updated_count", 0) >= 1

        verify_resp = sa_client.get(
            f"/copilot/support-tickets/{TestCopilotGlobalOps.ticket_id}",
            params={"account_id": account_id},
        )
        assert verify_resp.status_code == 200, f"Failed: {verify_resp.text}"
        ticket_data = verify_resp.json().get("data", {})
        assert ticket_data.get("status") == "IN_PROGRESS"
        assert ticket_data.get("priority") == "URGENT"

    def test_bulk_template_delete_with_dry_run(self, sa_client: httpx.Client, account_id: str):
        create_resp = sa_client.post(
            "/copilot/notification-templates/",
            params={"account_id": account_id},
            json={
                "template_id": "global-ops-template-" + uuid.uuid4().hex[:8],
                "event_id": "global-ops-event",
                "type": "EMAIL",
                "title_line": "Global Ops Template",
                "template_content": "Global Ops Content",
            },
        )
        assert create_resp.status_code == 200, f"Failed: {create_resp.text}"
        TestCopilotGlobalOps.template_id = create_resp.json().get("data", {}).get("id", "")
        assert TestCopilotGlobalOps.template_id

        dry_run_resp = sa_client.post(
            "/copilot/ops/global/bulk/notification-templates/delete",
            json={
                "account_ids": [account_id],
                "template_ids": [TestCopilotGlobalOps.template_id],
                "dry_run": True,
            },
        )
        assert dry_run_resp.status_code == 200, f"Failed: {dry_run_resp.text}"
        dry_run_data = dry_run_resp.json().get("data", {})
        assert dry_run_data.get("dry_run") is True
        assert dry_run_data.get("matched_count", 0) >= 1
        assert dry_run_data.get("deleted_count") == 0

        delete_resp = sa_client.post(
            "/copilot/ops/global/bulk/notification-templates/delete",
            json={
                "account_ids": [account_id],
                "template_ids": [TestCopilotGlobalOps.template_id],
                "dry_run": False,
            },
        )
        assert delete_resp.status_code == 200, f"Failed: {delete_resp.text}"
        delete_data = delete_resp.json().get("data", {})
        assert delete_data.get("dry_run") is False
        assert delete_data.get("deleted_count", 0) >= 1


# ============================================================
# 13. Integration Client Smoke Tests
# ============================================================


class TestConsoleClientImport:
    """Verify alchemi-ai console_client.py can be imported and structured correctly."""

    def test_import_console_client(self):
        import sys
        sys.path.insert(0, "/workspaces/alchemi-ai")
        from gen_ui_backend.utils.console_client import (
            ConsoleClient,
            ConsoleClientError,
            get_console_client,
        )
        # Verify class structure
        c = ConsoleClient(base_url="http://localhost:4000", api_key="test")
        assert c.base_url == "http://localhost:4000"
        assert c.api_key == "test"
        assert c.timeout == 30.0

        # Verify singleton
        client1 = get_console_client()
        client2 = get_console_client()
        assert client1 is client2

        # Verify error class
        err = ConsoleClientError(status_code=404, message="Not found")
        assert err.status_code == 404
        assert "404" in str(err)

    def test_console_client_methods_exist(self):
        import sys
        sys.path.insert(0, "/workspaces/alchemi-ai")
        from gen_ui_backend.utils.console_client import ConsoleClient

        c = ConsoleClient()
        assert callable(getattr(c, "check_budget", None))
        assert callable(getattr(c, "record_usage", None))
        assert callable(getattr(c, "get_budget_summary", None))
        assert callable(getattr(c, "get_guardrails_config", None))
        assert callable(getattr(c, "list_connections", None))
        assert callable(getattr(c, "list_agents", None))
        assert callable(getattr(c, "list_marketplace_items", None))
        assert callable(getattr(c, "list_users", None))
        assert callable(getattr(c, "list_groups", None))
        assert callable(getattr(c, "list_teams", None))
        assert callable(getattr(c, "list_invites", None))
        assert callable(getattr(c, "list_notification_templates", None))
        assert callable(getattr(c, "list_support_tickets", None))
        assert callable(getattr(c, "get_model_selection", None))
        assert callable(getattr(c, "get_global_ops_summary", None))


class TestConsoleApiClientImport:
    """Verify alchemi-web console_api/client.ts exists and has correct structure."""

    def test_client_file_exists(self):
        path = "/workspaces/alchemi-web/src/lib/console_api/client.ts"
        assert os.path.isfile(path), f"Console API client not found at {path}"

    def test_client_exports(self):
        path = "/workspaces/alchemi-web/src/lib/console_api/client.ts"
        with open(path) as f:
            content = f.read()

        # Check key exports exist
        expected_exports = [
            "export async function consoleGet",
            "export async function consolePost",
            "export async function consolePut",
            "export async function consoleDelete",
            "export async function consolePatch",
            "export const listBudgets",
            "export const listAgents",
            "export const listConnections",
            "export const listNotificationTemplates",
            "export const listSupportTickets",
            "export const listGuardrailsConfig",
            "export const listMarketplaceItems",
        ]
        for export in expected_exports:
            assert export in content, f"Missing export: {export}"

    def test_client_has_server_only(self):
        path = "/workspaces/alchemi-web/src/lib/console_api/client.ts"
        with open(path) as f:
            first_lines = "".join(f.readline() for _ in range(5))
        assert 'import "server-only"' in first_lines


# ============================================================
# 14. Migration Script Structure Test
# ============================================================


class TestMigrationScript:
    """Verify migration script structure and importability."""

    def test_migration_script_exists(self):
        path = "/workspaces/console-cockpit/alchemi/scripts/migrate_copilot_data.py"
        assert os.path.isfile(path)

    def test_migration_script_importable(self):
        import sys
        sys.path.insert(0, "/workspaces/console-cockpit")
        from alchemi.scripts.migrate_copilot_data import run_migration, main
        assert callable(run_migration)
        assert callable(main)

    def test_migration_script_tables(self):
        path = "/workspaces/console-cockpit/alchemi/scripts/migrate_copilot_data.py"
        with open(path) as f:
            content = f.read()

        expected_tables = [
            "copilot.credit_budget",
            "copilot.budget_plans",
            "copilot.agents_def",
            "copilot.agent_groups",
            "copilot.agent_group_members",
            "copilot.marketplace_items",
            "copilot.account_connections",
            "copilot.guardrails_config",
            "copilot.guardrails_custom_patterns",
            "copilot.guardrails_audit_log",
            "copilot.users",
            "copilot.groups",
            "copilot.teams",
            "copilot.account_memberships",
            "copilot.user_invites",
            "copilot.notification_templates",
            "copilot.support_tickets",
        ]
        for table in expected_tables:
            assert table in content, f"Missing table reference: {table}"
