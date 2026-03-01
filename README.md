# Alchemi Studio Console (console-cockpit)

Centralized multi-tenant control plane and AI gateway, built on LiteLLM.

This repo is the source of truth for:
- super-admin account lifecycle,
- account admin controls for both `console` and `copilot` domains,
- centralized `/v1` control-plane APIs.

Detailed operational runbook: [README_UNIFIED_OPERATIONS.md](./README_UNIFIED_OPERATIONS.md)
Zitadel field-level guide: [docs/ZITADEL_README.md](./docs/ZITADEL_README.md)

## What Runs Here

- LiteLLM proxy + Alchemi extensions (Python/FastAPI)
- Tenant middleware and policy enforcement under `alchemi/`
- Dashboard UI under `ui/litellm-dashboard`
- DB migrations in `prisma/migrations`

## Local Development (Verified)

Prereqs:
- Python `3.11+`
- Node.js `18.17+` (20 recommended)
- PostgreSQL
- Redis

1. Install dependencies:

```bash
cd /workspaces/console-cockpit
poetry install -E proxy -E extra_proxy --with dev,proxy-dev
cd ui/litellm-dashboard && npm install && cd ../..
```

2. Set required env vars in `.env`:
- `DATABASE_URL`
- `LITELLM_MASTER_KEY`
- `STORE_MODEL_IN_DB=True`
- `REDIS_URL`
- `UI_USERNAME`
- `UI_PASSWORD`

3. Run migrations:

```bash
./scripts/deploy.sh migrate
```

4. Start backend (proxy + APIs):

```bash
poetry run litellm --port 4000
```

5. Optional UI hot reload:

```bash
cd /workspaces/console-cockpit/ui/litellm-dashboard
npm run dev -- --port 4001
```

Use:
- proxy-served UI: `http://localhost:4000/ui`
- hot-reload UI: `http://localhost:4001`

Notes:
- Hot-reload UI is separate from proxy static UI.
- To update proxy-served UI after TS/React changes:

```bash
cd /workspaces/console-cockpit
./scripts/deploy.sh build-ui
```

## Production

Standard deployment command:

```bash
cd /workspaces/console-cockpit
./scripts/deploy.sh all
```

Or split by stage:

```bash
./scripts/deploy.sh migrate
./scripts/deploy.sh build-ui
./scripts/deploy.sh start
```

`deploy.sh` is located at `scripts/deploy.sh` (not repo root).

## Authentication and Identity

- Runtime Zitadel token verification is configured from global env (`ZITADEL_*` in server env).
- Account-level Zitadel fields in Tenant Admin are stored as account metadata/provisioning defaults.
- Zitadel provisioning endpoints are under:
  - `POST /v1/accounts/{id}/zitadel/provision/user-grant`
  - `POST /v1/accounts/{id}/zitadel/provision/project-role`
  - `POST /v1/accounts/{id}/zitadel/provision/bootstrap`

## API and Data Model

- Unified control plane API entry: `alchemi/endpoints/control_plane_v1.py`
- Tenant scoping wrapper: `alchemi/db/tenant_scoped_prisma.py`
- Request account context: `alchemi/middleware/account_middleware.py`

Console and Copilot trees remain separate in the centralized model (org/team/user tables and grants), but are managed from one cockpit surface.
