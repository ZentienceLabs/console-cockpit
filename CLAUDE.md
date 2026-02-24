# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Identity

This is **Alchemi Studio Console** -- a multi-tenant enterprise AI gateway built on top of LiteLLM (MIT-licensed). The project adds an Account (tenant) layer above LiteLLM's existing Organization > Team > User hierarchy, making every feature tenant-scoped.

**Critical rules:**
- The `enterprise/` directory has been removed. Never reference or import from it.
- All enterprise features live in the `alchemi/` directory.
- `premium_user` is forced to `True` everywhere -- all enterprise features are always enabled.
- There is NO `config.yaml` loaded by default. Every account manages their own models, guardrails, and settings from the database (`STORE_MODEL_IN_DB=True`).
- The UI brand is "Alchemi Studio Console", not "LiteLLM". Never introduce new LiteLLM branding in user-visible text.
- Any user-visible text, UI labels, API params, payload properties, placeholder text, tooltips, code examples, or documentation that says "litellm" or "LiteLLM" must be changed to say "alchemi" or "Alchemi". This includes MCP `server_label` values, `$LITELLM_VIRTUAL_KEY` in examples, footer text, and help text. Exceptions: backend protocol headers (`x-litellm-*`), backend route paths (`/litellm/...`, `litellm_proxy/...`), config key references (`litellm_settings.*`), and internal variable names -- these are functional and must not be changed without corresponding backend changes.
- Minimize changes to LiteLLM base code (`litellm/` directory). Build features in `alchemi/` instead.

## Development Commands

### Installation (Poetry)
```bash
poetry install -E proxy -E extra_proxy                  # Core + proxy deps
poetry install -E proxy -E extra_proxy --with dev,proxy-dev  # Full dev setup
```

### Running the Proxy
```bash
poetry run python litellm/proxy/proxy_cli.py            # Dev mode
poetry run litellm --port 4000                           # CLI entrypoint
```

### Database
```bash
./scripts/deploy.sh migrate                              # Standard: sync + migrate
cp schema.prisma litellm/proxy/schema.prisma             # Manual: sync schema
poetry run prisma generate --schema=./schema.prisma       # Manual: generate client
```

### Deploying to Environments
```bash
DATABASE_URL="postgresql://..." ./scripts/deploy.sh migrate   # Any environment
./scripts/deploy.sh build-ui                                  # Rebuild admin UI
./scripts/deploy.sh start                                     # Start server
./scripts/deploy.sh                                           # Full deploy (all steps)
```

### Building the UI
```bash
cd ui/litellm-dashboard
npm install
npm run dev                                               # Dev (hot reload)
npm run build                                             # Production build
cp -r out/ ../../litellm/proxy/_experimental/out/         # Deploy to proxy
```

### Testing
```bash
poetry run pytest tests/test_litellm/ -v --numprocesses=4  # Python unit tests
cd ui/litellm-dashboard && npm test                        # Frontend tests
make lint                                                  # Linting (Ruff, MyPy, Black)
make format                                                # Auto-format
```

### Single Test Files
```bash
poetry run pytest tests/path/to/test_file.py -v
poetry run pytest tests/path/to/test_file.py::test_function -v
```

### Docker
```bash
docker compose up -d          # Start proxy + postgres + prometheus
docker compose logs -f litellm
docker compose down
```

## Architecture Overview

### Multi-Tenant Hierarchy
```
Super Admin (UI_USERNAME/UI_PASSWORD)
  └── Account (tenant, scoped by account_id + email domain)
        ├── Organizations → Teams → Users → Virtual Keys
        ├── Models, Agents, MCP Servers
        ├── Guardrails, Policies, Access Groups
        ├── Budgets, Spend Tracking
        └── Per-Account SSO Config
```

### Core Components

#### LiteLLM Base (`litellm/`)
- **`proxy/proxy_server.py`** -- Main FastAPI application (~12,500 lines)
- **`proxy/auth/`** -- Authentication handlers (JWT, API key, SSO)
- **`proxy/management_endpoints/`** -- Admin APIs for keys, teams, models
- **`proxy/management_endpoints/ui_sso.py`** -- SSO callback flow (includes account_id resolution at line ~2384)
- **`llms/`** -- 100+ LLM provider implementations
- **`router.py`** + **`router_utils/`** -- Load balancing and fallback logic
- **`types/`** -- Pydantic type definitions
- **`proxy/_experimental/out/`** -- Next.js compiled UI (served statically)

#### Alchemi Extension (`alchemi/`)
- **`auth/account_resolver.py`** -- Resolves `account_id` from email domain lookup + Zitadel claims
- **`auth/sso_router.py`** -- Per-account SSO routing (determines SSO vs password login)
- **`auth/super_admin.py`** -- Super admin verification (password + email-based)
- **`auth/zitadel_oidc.py`** -- Zitadel OIDC PKCE flow (`/zitadel/authorize`, `/zitadel/callback`)
- **`auth/zitadel_webhook.py`** -- Zitadel user provisioning webhook
- **`config/settings.py`** -- AlchemiProxyConfig (master key, UI credentials)
- **`db/tenant_scoped_prisma.py`** -- `TenantScopedPrismaClient` that auto-injects `WHERE account_id = ?`
- **`db/copilot_db.py`** -- `CopilotDB` async wrapper for `copilot.*` schema tables (asyncpg)
- **`endpoints/account_endpoints.py`** -- Account CRUD REST API (super admin only)
- **`endpoints/audit_log_endpoints.py`** -- Audit log query endpoints
- **`endpoints/copilot_budget_endpoints.py`** -- Credit budget CRUD + usage recording (`/copilot/budgets`)
- **`endpoints/copilot_agent_endpoints.py`** -- Agent definitions + groups (`/copilot/agents`)
- **`endpoints/copilot_marketplace_endpoints.py`** -- Marketplace items CRUD (`/copilot/marketplace`)
- **`endpoints/copilot_connection_endpoints.py`** -- Account connections CRUD (`/copilot/connections`)
- **`endpoints/copilot_guardrails_endpoints.py`** -- Guardrails config, patterns, audit log (`/copilot/guardrails`)
- **`endpoints/copilot_entitlements_endpoints.py`** -- Per-account entitlements (super admin, `/copilot/entitlements`)
- **`endpoints/copilot_types.py`** -- Shared Pydantic models and enums for copilot endpoints
- **`hooks/audit_logger.py`** -- Captures audit events and sends to OpenObserve
- **`hooks/secret_detection.py`** -- PII/secret masking in LLM requests
- **`hooks/batch_cost.py`** -- Batch processing cost tracking
- **`hooks/responses_cost.py`** -- Response API cost calculation
- **`enterprise_features/`** -- Guardrails, moderation, email notifications, SSO handler, blocklists
- **`integrations/openobserve.py`** -- OpenObserve HTTP client for audit logging
- **`middleware/account_middleware.py`** -- FastAPI middleware that resolves account from JWT/API key
- **`middleware/tenant_context.py`** -- `contextvars.ContextVar` holding current `account_id`
- **`scripts/migrate_copilot_data.py`** -- One-time migration from alchemi-web Sequelize tables to `copilot.*`

#### Admin Dashboard (`ui/litellm-dashboard/`)
- **Next.js 16** with React 18, Tailwind CSS, Ant Design
- **`src/app/login/LoginPage.tsx`** -- Email-first login with SSO routing + Zitadel SSO button
- **`src/app/(dashboard)/tenant-admin/page.tsx`** -- Super admin tenant management page (Accounts, Billing, Models, Entitlements tabs)
- **`src/components/networking.tsx`** -- API client functions (includes `accountCreateCall`, `accountListCall`, `accountUpdateCall`, `accountDeleteCall`, `accountAdminAddCall`, `accountAdminRemoveCall`, `loginResolveCall`, copilot CRUD functions)
- **`src/components/leftnav.tsx`** -- Sidebar navigation (customized for Alchemi, includes COPILOT nav group)
- **`src/components/navbar.tsx`** -- Top navigation bar (Alchemi-branded)
- **`src/components/copilot/`** -- Copilot feature pages (Budgets, Agents, Connections, Guardrails)
- **`src/components/tenant-admin/`** -- Super admin sub-pages (BillingOverview, ModelRegistry, AccountEntitlements)
- **`src/app/(dashboard)/hooks/copilot/`** -- React Query hooks for copilot API calls

### Database Schema

**Prisma schema:** `/workspaces/console-cockpit/schema.prisma` (1083 lines)
**Reference schema:** `/workspaces/console-cockpit/litellm/proxy/schema.prisma` (976 lines, original LiteLLM)

The active schema extends LiteLLM's with:
- `account_id String?` column + `@@index([account_id])` on all major tables
- 3 new Alchemi tables: `Alchemi_AccountTable`, `Alchemi_AccountAdminTable`, `Alchemi_AccountSSOConfig`

**Copilot schema** (`copilot.*` PostgreSQL schema, managed via asyncpg, not Prisma):
- Migration: `prisma/migrations/20260221200000_copilot_schema/migration.sql`
- 10 tables: `credit_budget`, `budget_plans`, `agents_def`, `agent_groups`, `agent_group_members`, `marketplace_items`, `account_connections`, `guardrails_config`, `guardrails_custom_patterns`, `guardrails_audit_log`
- 2 views: `v_budget_summary`, `v_budget_alerts`
- All tables have `account_id` for tenant scoping, UUID primary keys, TIMESTAMPTZ timestamps
- Accessed via `CopilotDB` class in `alchemi/db/copilot_db.py` (connection pool initialized at proxy startup)

**Important:** Always edit the root `schema.prisma`, then sync to `litellm/proxy/schema.prisma`. Copilot tables are raw SQL -- do not add them to the Prisma schema.

### Tenant Scoping Flow
1. Request arrives → `AccountMiddleware` extracts `account_id` from JWT cookie or API key
2. `set_current_account_id()` sets the `contextvars.ContextVar`
3. `TenantScopedPrismaClient` reads from ContextVar and auto-injects `WHERE account_id = ?`
4. Super admins (no `account_id`) bypass filtering and see all data

### SSO Login Flow
1. `LoginPage.tsx` collects email → calls `/v2/login/resolve`
2. Backend checks email domain → looks up `Alchemi_AccountTable.domain`
3. If account has SSO config → returns SSO redirect URL
4. User completes SSO → `/sso/callback` → `resolve_account_for_user()` sets `account_id` in JWT
5. Middleware extracts `account_id` from JWT on subsequent requests

## Key Patterns

### Adding Features to alchemi/
When building new enterprise features:
1. Create the module in the appropriate `alchemi/` subdirectory
2. Use `from alchemi.middleware.tenant_context import get_current_account_id` for tenant scoping
3. Register endpoints in `proxy_server.py` if needed (use `app.include_router()`)
4. Register hooks/callbacks in the proxy startup sequence

### Modifying the Database Schema
1. Edit `/workspaces/console-cockpit/schema.prisma` (the root one)
2. Add `account_id String?` + `@@index([account_id])` to any new table
3. Create an idempotent migration SQL in `prisma/migrations/<YYYYMMDDHHMMSS>_<description>/migration.sql`
4. Use `IF NOT EXISTS` guards for all DDL statements
5. Run `./scripts/deploy.sh migrate` to test locally
6. Commit the migration and deploy to other environments with `DATABASE_URL=... ./scripts/deploy.sh migrate`

### Migration Architecture
- Alchemi migrations live in `prisma/migrations/` (checked into git, source of truth)
- `scripts/deploy.sh migrate` copies them into `litellm_proxy_extras/migrations/` and syncs `schema.prisma`
- `prisma migrate deploy` applies only pending migrations (tracked in `_prisma_migrations` table)
- The Dockerfile does this sync at build time, so Docker containers are self-contained
- All migration SQL must be idempotent (`IF NOT EXISTS`, `DO $$ BEGIN ... END $$` blocks)

### UI Development
- Tremor is DEPRECATED -- do not use in new features (exception: Tremor Table)
- Use common components from `src/components/common_components/`
- Use Vitest + React Testing Library for tests
- All test names must start with "should"
- Use `screen` queries, not destructured from `render()`
- Never introduce new LiteLLM branding -- use "Alchemi Studio Console"
- External documentation links should use `href="#"` (no docs.litellm.ai links)

### Provider Implementation
- Providers inherit from base classes in `litellm/llms/base.py`
- Each provider has transformation functions for input/output formatting
- Support both sync and async operations
- Handle streaming responses and function calling

### Error Handling
- Provider-specific exceptions mapped to OpenAI-compatible errors
- Fallback logic handled by Router system
- Use `handle_error()` from networking.tsx for API errors in UI

### Configuration
- YAML config files are NOT used (database-driven per account)
- Environment variables for system-level secrets and settings
- Database schema managed via Prisma

## Environment Variables

### Required
| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `STORE_MODEL_IN_DB` | Must be `"True"` (accounts manage models from DB) |
| `LITELLM_MASTER_KEY` | Master API key for the proxy |
| `UI_USERNAME` | Super admin login username |
| `UI_PASSWORD` | Super admin login password |

### Optional
| Variable | Description |
|----------|-------------|
| `ZITADEL_ISSUER_URL` | Zitadel issuer URL for OIDC authentication |
| `ZITADEL_CLIENT_ID` | Zitadel OIDC client ID |
| `ZITADEL_CLIENT_SECRET` | Zitadel OIDC client secret |
| `ZITADEL_CALLBACK_URL` | Zitadel callback URL (default: `{PROXY_BASE_URL}/zitadel/callback`) |
| `SUPER_ADMIN_EMAILS` | Comma-separated emails for Zitadel-based super admin access |
| `OPENOBSERVE_URL` | OpenObserve endpoint for audit logging |
| `OPENOBSERVE_ORG` | OpenObserve organization (default: "default") |
| `OPENOBSERVE_STREAM` | OpenObserve stream name (default: "alchemi_audit") |
| `OPENOBSERVE_USER` | OpenObserve username |
| `OPENOBSERVE_PASSWORD` | OpenObserve password |
| `ALCHEMI_AUDIT_LOG_RETENTION_DAYS` | Audit log retention (default: "90") |
| `EMAIL_REDIS_HOST` | alchemi-worker Redis host for email queue (Azure Managed Redis, cluster mode) |
| `EMAIL_REDIS_PORT` | alchemi-worker Redis port (default: "10000") |
| `EMAIL_REDIS_PASSWORD` | alchemi-worker Redis password |
| `EMAIL_REDIS_TLS` | Enable TLS for email Redis (default: "true") |
| `EMAIL_REDIS_ENVIRONMENT` | BullMQ prefix environment, e.g. "dev" or "prod" |
| `EMAIL_MODE` | `central` (default) or `tenant_first` (try tenant SMTP config, fall back to central) |
| `EMAIL_LOGO_URL` | Logo URL used in invitation emails |
| `EMAIL_SUPPORT_CONTACT` | Support email shown in invitation emails |
| `PROXY_BASE_URL` | Base URL of the proxy (used in invitation links) |
| `ALCHEMI_WEB_DATABASE_URL` | Source DB for copilot data migration script (alchemi-web) |

## Files Modified from LiteLLM Base

### Python (Backend)
- `litellm/proxy/proxy_server.py` -- Alchemi middleware registration, account router, copilot routers, copilot DB pool lifecycle, premium_user override, docs link removal
- `litellm/proxy/auth/user_api_key_auth.py` -- Account context from API key
- `litellm/proxy/auth/login_utils.py` -- Docs link removal from error messages
- `litellm/proxy/management_endpoints/ui_sso.py` -- Account resolution in SSO callback (line ~2384), docs link removal
- `litellm/proxy/proxy_cli.py` -- Alchemi branding in CLI output
- `litellm/proxy/common_utils/html_forms/ui_login.py` -- Alchemi branding in HTML login
- `litellm/proxy/common_utils/admin_ui_utils.py` -- Help page branding
- `litellm/_version.py` -- Premium user forced to True
- `litellm/proxy/utils.py` -- Premium user forced to True

### TypeScript/React (Frontend)
- `ui/litellm-dashboard/src/app/login/LoginPage.tsx` -- Email-first login flow
- `ui/litellm-dashboard/src/app/(dashboard)/tenant-admin/page.tsx` -- New tenant management page
- `ui/litellm-dashboard/src/components/networking.tsx` -- Account management API functions
- `ui/litellm-dashboard/src/components/leftnav.tsx` -- Sidebar customization
- `ui/litellm-dashboard/src/components/navbar.tsx` -- Branding, community links removed
- ~40 additional UI files with LiteLLM text replaced with Alchemi branding
- ~32 additional UI files with external docs.litellm.ai links replaced with "#"

### Schema
- `/schema.prisma` (root) -- Added 3 Alchemi tables + account_id to all existing tables
- `prisma/migrations/20260221200000_copilot_schema/migration.sql` -- Copilot schema (10 tables, 2 views)

### Copilot API Surface

All copilot endpoints are tenant-scoped (account_id auto-injected from JWT/API key context).

| Prefix | Endpoints | Purpose |
|--------|-----------|---------|
| `/copilot/budgets` | CRUD + `/summary`, `/alerts`, `/record-usage`, `/plans` | Credit budgets and usage recording |
| `/copilot/agents` | CRUD + `/groups`, `/groups/{id}/members` | Agent definitions and groups |
| `/copilot/marketplace` | CRUD + `/featured`, `/{id}/install` | Marketplace item listings |
| `/copilot/connections` | CRUD + `/{id}/test` | MCP/OpenAPI/integration connections |
| `/copilot/guardrails` | `/config`, `/config/{type}/toggle`, `/patterns`, `/audit` | Guard configs, patterns, audit log |
| `/copilot/entitlements` | `GET/PUT /{account_id}` (super admin only) | Per-account feature flags and limits |

### Integration Clients (External Repos)

**alchemi-web** (`/workspaces/alchemi-web/src/lib/console_api/client.ts`):
- TypeScript HTTP client using `fetch` with 30s timeout
- `import "server-only"` (Next.js server components only)
- Functions: `consoleGet`, `consolePost`, `consolePut`, `consoleDelete`, `consolePatch` + ~50 domain-specific exports
- Config: `CONSOLE_API_URL` env var (default: `http://localhost:4000`)

**alchemi-ai** (`/workspaces/alchemi-ai/gen_ui_backend/utils/console_client.py`):
- Python async httpx client with singleton pattern
- Methods: `check_budget`, `record_usage`, `get_budget_summary`, `get_guardrails_config`, `list_connections`
- Config: `CONSOLE_API_URL`, `CONSOLE_API_KEY`, `CONSOLE_TIMEOUT` env vars

### Data Migration

**Script:** `python -m alchemi.scripts.migrate_copilot_data`
- Migrates data from alchemi-web Sequelize tables (public schema) to `copilot.*` tables
- Requires: `ALCHEMI_WEB_DATABASE_URL` (source) + `DATABASE_URL` (target)
- All INSERTs use `ON CONFLICT DO NOTHING` for safe re-runs
- Migrates 10 tables: credit_budget, budget_plans, agents_def, agent_groups, agent_group_members, marketplace_items (from agent_marketplace), account_connections, guardrails_config, guardrails_custom_patterns, guardrails_audit_log

## Common Pitfalls

1. **Wrong schema file** -- Always edit the root `schema.prisma`, not `litellm/proxy/schema.prisma`
2. **Re-introducing LiteLLM branding** -- Check user-visible strings before committing
3. **Importing from enterprise/** -- This directory no longer exists; use `alchemi/` equivalents
4. **Missing account_id on new tables** -- Every new table needs `account_id String?` + index
5. **config.yaml assumptions** -- The proxy does NOT load config.yaml; all config is per-account from DB
6. **Breaking LiteLLM base** -- Keep changes to `litellm/` minimal; extend in `alchemi/` instead
7. **UI build not deployed** -- After changing UI files, run `./scripts/deploy.sh build-ui`
8. **Schema not synced to litellm_proxy_extras** -- The extras package has its own `schema.prisma`; if it's out of sync, the post-migration sanity check will revert Alchemi columns. Always use `./scripts/deploy.sh migrate` which handles this.
9. **Non-idempotent migration SQL** -- Migrations must use `IF NOT EXISTS` guards so they can be safely re-run. `prisma migrate deploy` will skip already-applied migrations, but the sanity check may re-execute SQL.
