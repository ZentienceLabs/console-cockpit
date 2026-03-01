# Hardening Acceptance Checks

Run these checks before production launch.

## 1. Control-Plane Security Unit Tests

Validates:

- claim tampering rejection
- super-admin gating
- domain separation enforcement
- account context requirement

Run:

```bash
cd /workspaces/console-cockpit
poetry run pytest tests/alchemi_security/test_control_plane_security.py -q
```

## 1b. Concurrent Load Smoke

```bash
cd /workspaces/console-cockpit
poetry run pytest tests/alchemi_security/test_control_plane_load_smoke.py -q
```

## 2. Type and Syntax Safety

```bash
cd /workspaces/console-cockpit
python -m py_compile alchemi/endpoints/control_plane_v1.py
cd ui/litellm-dashboard
pnpm exec tsc --noEmit
```

## 3. Multi-Tenant Isolation Smoke

Use two different account contexts and verify cross-account access is denied:

1. Create resources under account A.
2. Query same resources under account B.
3. Expect `404`/`403` for account B reads/writes.

Minimum endpoints to validate:

- `/v1/copilot/orgs`, `/v1/copilot/teams`, `/v1/copilot/users`
- `/v1/copilot/agents`
- `/v1/copilot/connections`
- `/v1/copilot/marketplace`

## 4. Auth Escalation Smoke

- Tampered JWT without valid signature must not set context.
- Missing `account_id` context should fail account-admin endpoints.
- Console-only admin claims should fail Copilot-admin endpoints and vice versa.

## 5. Load and Pen Test Entry Criteria

- P95 latency budget for list endpoints with pagination under expected tenant load.
- No high/critical findings from authz and secret exposure checks.
- Verify admin-managed OpenAPI/MCP credentials remain masked on all API responses.

## One-command campaign

```bash
cd /workspaces/console-cockpit
bash scripts/run_hardening_campaign.sh
```
