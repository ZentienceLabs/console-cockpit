# Console-Cockpit Operations Guide

This is the centralized control plane for the suite. It manages both:

- `Console` domain: gateway/org/team/user, model access, guardrails, keys, spend visibility.
- `Copilot` domain: copilot org/team/user, budgets, agents, connections, guardrails, marketplace, audit.

It is the source of truth for account-level administration.

## How It Works

- Runs on LiteLLM proxy base with Alchemi extensions under `alchemi/`.
- Exposes unified `/v1` control-plane APIs from `alchemi/endpoints/control_plane_v1.py`.
- Enforces tenant context through middleware (`account_id`, roles, scopes, domains).
- Keeps Console and Copilot org/team/user trees separate in storage and APIs.
- Auto-creates default Copilot org `global` when an account is created.

## Local Development Setup

## Prerequisites

- Python `3.11+`
- Node.js `20+`
- PostgreSQL
- Redis

## Environment

Use `.env` (not `.env.example`).

Minimum required keys:

- `DATABASE_URL`
- `LITELLM_MASTER_KEY`
- `STORE_MODEL_IN_DB=True`
- `REDIS_URL`
- `UI_USERNAME`
- `UI_PASSWORD`
- `ZITADEL_ISSUER_URL`
- `ZITADEL_CLIENT_ID`
- `ZITADEL_CLIENT_SECRET`
- `ZITADEL_CALLBACK_URL`
- `OPENOBSERVE_URL`
- `OPENOBSERVE_USER`
- `OPENOBSERVE_PASSWORD`
- `OPENOBSERVE_ORG`
- `OPENOBSERVE_STREAM`

For your current dev target, keep `DATABASE_URL` pointed to `devconsolev2_db` as configured in your `.env`.

## Install and Run

```bash
cd /workspaces/console-cockpit
poetry install --with dev,proxy-dev --extras proxy
cd ui/litellm-dashboard && npm install && cd ../..
./scripts/deploy.sh migrate
poetry run litellm --port 4000
```

Optional UI hot-reload:

```bash
cd /workspaces/console-cockpit/ui/litellm-dashboard
npm run dev
```

If you need to rebuild bundled UI for proxy-served static pages:

```bash
cd /workspaces/console-cockpit
./scripts/deploy.sh build-ui
```

## Production Setup

## Option A: Docker Compose

```bash
cd /workspaces/console-cockpit
docker compose up -d --build
```

## Option B: Container Deployment

- Build image using `Dockerfile`.
- Provide environment variables from secret manager.
- Ensure DB migration step runs (`./scripts/deploy.sh migrate`) before or during rollout.
- Start service with default entrypoint (`docker/prod_entrypoint.sh`), port `4000`.

## External Systems Setup

## Zitadel

1. Create a Zitadel project and app integration for cockpit.
2. Configure `.env`:
- `ZITADEL_ISSUER_URL`
- `ZITADEL_CLIENT_ID`
- `ZITADEL_CLIENT_SECRET`
- `ZITADEL_CALLBACK_URL`
3. Optional management auth:
- `ZITADEL_MGMT_API_TOKEN`, or
- management through client credentials (`ZITADEL_CLIENT_ID` + `ZITADEL_CLIENT_SECRET`).
4. Verify:
- `GET /v1/auth/zitadel/status`

Detailed field-level guide for Tenant Admin Zitadel tab:
- `docs/ZITADEL_README.md`

## OpenObserve

Configure:

- `OPENOBSERVE_URL`
- `OPENOBSERVE_USER`
- `OPENOBSERVE_PASSWORD`
- `OPENOBSERVE_ORG`
- `OPENOBSERVE_STREAM`

Used for audit and operational logging paths.

## Database and Redis

- PostgreSQL via `DATABASE_URL`
- Redis via `REDIS_URL`

## Tenant Provisioning Runbook

Use super-admin credentials/token.

1. Create account:

```bash
curl -X POST http://localhost:4000/v1/accounts \
  -H "Authorization: Bearer <MASTER_OR_SUPERADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"account_name":"acme","email_domain":"acme.com"}'
```

2. Add account admin:

```bash
curl -X POST http://localhost:4000/v1/accounts/<account_id>/admins \
  -H "Authorization: Bearer <MASTER_OR_SUPERADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"user_email":"admin@acme.com","role":"account_admin"}'
```

3. Set SSO for account:

```bash
curl -X POST http://localhost:4000/v1/accounts/<account_id>/sso \
  -H "Authorization: Bearer <MASTER_OR_SUPERADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"provider":"zitadel","settings":{"issuer":"https://<issuer>"}}'
```

4. Set monthly credits, overflow, credit factor:

```bash
curl -X POST http://localhost:4000/v1/budgets/account-allocation \
  -H "Authorization: Bearer <MASTER_OR_SUPERADMIN_TOKEN>" \
  -H "X-Account-Id: <account_id>" \
  -H "Content-Type: application/json" \
  -d '{"account_id":"<account_id>","monthly_credits":10000,"overflow_limit":2000,"credit_factor":1.25}'
```

5. Optional super-admin account controls:
- `PUT /v1/accounts/{id}/feature-pack`
- `PUT /v1/accounts/{id}/console-model-policy`
- `PUT /v1/accounts/{id}/zitadel/config`

## Account Admin Operations (Copilot)

- Create org/team/user:
  - `POST /v1/copilot/orgs`
  - `POST /v1/copilot/teams`
  - `POST /v1/copilot/users`
- Budgeting:
  - `POST /v1/budgets/copilot/plans`
  - `POST /v1/budgets/copilot/distribute/equal`
  - `POST /v1/budgets/copilot/overrides`
  - `GET /v1/budgets/copilot/effective-allocation`
- Agents:
  - `POST /v1/copilot/agents`
  - `PUT /v1/copilot/agents/{id}` (includes optional `grants` replacement)
  - `GET /v1/copilot/agents/{id}/grants`
  - `POST /v1/copilot/agents/{id}/grants`
  - `DELETE /v1/copilot/agents/{id}/grants?scope_type=...&scope_id=...`
  - `guardrail_preset_ids` is required on create/update (at least one preset per agent).
  - optional grants in payload by org/team/user scope.
- Connections (OpenAPI/MCP/Composio):
  - `POST /v1/copilot/connections/{connection_type}`
  - `POST /v1/copilot/connections/{id}/grants`
  - admin-managed secrets are masked in API responses.
  - Composio requires `config_json.auth_mode` (`oauth` or `api_key`); `api_key` mode requires `secret_json.api_key`.
- Guardrails:
  - `POST /v1/copilot/guardrails/presets`
  - `POST /v1/copilot/guardrails/assignments`
  - `GET /v1/copilot/guardrails/effective`
- Models:
  - `POST /v1/copilot/models/grants`
  - `GET /v1/copilot/models/effective`
- Features:
  - `POST /v1/features/entitlements`
  - `GET /v1/features/effective`
- Marketplace:
  - `POST /v1/copilot/marketplace`
  - `POST /v1/copilot/marketplace/{id}/publish`
  - `POST /v1/copilot/marketplace/{id}/grants` (org/team/user visibility)
  - `GET /v1/copilot/marketplace/discover` (scope-filtered discovery)
- Audit and costs:
  - `GET /v1/audit?domain=copilot|console|all`
  - `GET /v1/costs/breakdown`

## Account Admin Operations (Console Domain)

- Separate hierarchy:
  - `POST /v1/console/orgs`
  - `POST /v1/console/teams`
  - `POST /v1/console/users`
- Model access:
  - `POST /v1/console/models/grants`
  - `GET /v1/console/models/effective`

## User and Role Provisioning with Zitadel

Per account:

1. Save account-level Zitadel config:
- `PUT /v1/accounts/{id}/zitadel/config`
2. Provision project roles:
- `POST /v1/accounts/{id}/zitadel/provision/project-role`
3. Grant users:
- `POST /v1/accounts/{id}/zitadel/provision/user-grant`
4. Lifecycle automation:
- `GET /v1/accounts/{id}/zitadel/provision/plan`
- `POST /v1/accounts/{id}/zitadel/provision/sync-roles`
- `POST /v1/accounts/{id}/zitadel/provision/sync-admin-grants`
- `POST /v1/accounts/{id}/zitadel/provision/bootstrap`

## Troubleshooting

- `403 Account context required`: pass valid token and `X-Account-Id` where needed.
- `403 Super admin access required`: use master key or super-admin role claim.
- `Database not connected`: check `DATABASE_URL` and startup logs.
- Zitadel verification failures: verify issuer, audience, and callback/client settings.
- Missing UI updates in proxy-hosted UI: rebuild with `./scripts/deploy.sh build-ui`.

## Hardening Checklist

Use the launch acceptance checklist in:

- `docs/HARDENING_ACCEPTANCE.md`
- `scripts/run_hardening_campaign.sh`
- `docs/HARDENING_EXECUTION_REPORT.md` (latest execution evidence)
- `docs/ORIGINAL_ASK_AUDIT.md` (requirement-by-requirement closure map)
