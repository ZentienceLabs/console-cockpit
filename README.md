# Alchemi Studio Console

Multi-tenant enterprise AI gateway and control plane built on LiteLLM.

Alchemi Studio Console adds an **Account (tenant) layer** on top of LiteLLM's existing Organization > Team > User hierarchy, making every feature tenant-scoped. Each account gets their own isolated instance of models, keys, guardrails, policies, agents, MCP servers, budgets, and audit logs.

## Architecture

```
Super Admin (UI_USERNAME/UI_PASSWORD)
  └── Account (tenant, scoped by account_id + email domain)
        ├── Organizations
        │     └── Teams
        │           └── Users / Virtual Keys
        ├── Models + Endpoints
        ├── Guardrails & Policies
        ├── Agents & MCP Servers
        ├── Budgets & Spend Tracking
        ├── Audit Logs (OpenObserve)
        └── Per-Account SSO Config
```

**Key design principles:**
- Minimal changes to the LiteLLM base code; enterprise features live in `alchemi/`
- `TenantScopedPrismaClient` auto-injects `WHERE account_id = ?` on every query
- `contextvars.ContextVar` carries the current `account_id` per request
- Super admins bypass tenant scoping and only see the Tenant Management page
- No `config.yaml` loaded by default -- every account manages their own models/config from the database

## Project Structure

```
console-cockpit/
├── alchemi/                    # Enterprise multi-tenant extension
│   ├── auth/                   #   Account resolution, SSO routing, super admin
│   ├── config/                 #   Settings and constants
│   ├── db/                     #   TenantScopedPrismaClient wrapper
│   ├── endpoints/              #   Account CRUD, audit log queries
│   ├── enterprise_features/    #   Guardrails, moderation, email, SSO handler
│   ├── hooks/                  #   Audit logger, cost tracking, secret detection
│   ├── integrations/           #   OpenObserve client
│   └── middleware/             #   Account middleware, tenant context
├── litellm/                    # LiteLLM base (MIT licensed)
│   ├── proxy/                  #   FastAPI proxy server
│   │   ├── proxy_server.py     #   Main server (~12,500 lines)
│   │   ├── schema.prisma       #   Original LiteLLM schema (reference)
│   │   ├── auth/               #   Auth handlers
│   │   └── management_endpoints/ # Admin APIs
│   └── llms/                   #   100+ provider implementations
├── ui/litellm-dashboard/       # Next.js admin dashboard (Alchemi-branded)
│   └── src/
│       ├── app/login/          #   Email-first login with SSO routing
│       ├── app/(dashboard)/    #   Dashboard pages inc. tenant-admin
│       └── components/         #   UI components (networking, navbar, etc.)
├── schema.prisma               # Active schema with Alchemi tables + account_id columns
├── docker-compose.yml          # Proxy + PostgreSQL + Prometheus
├── pyproject.toml              # Poetry config
└── Dockerfile                  # Production container (Chainguard Wolfi)
```

## Prerequisites

- Python 3.9+
- Node.js 18.17+ and npm 8.3+
- PostgreSQL 16+
- Poetry (Python package manager)

## Setup & Installation

### 1. Install Python Dependencies (Poetry)

```bash
cd /workspaces/console-cockpit

# Install Poetry if not present
pip install poetry

# Install core + proxy dependencies
poetry install -E proxy -E extra_proxy

# Or install everything for development
poetry install -E proxy -E extra_proxy --with dev,proxy-dev
```

### 2. Environment Variables

Create a `.env` file in the project root:

```bash
# --- Required ---
DATABASE_URL="postgresql://llmproxy:dbpassword9090@localhost:5432/litellm"
STORE_MODEL_IN_DB="True"
LITELLM_MASTER_KEY="sk-change-me-in-production"

# --- Super Admin UI credentials ---
UI_USERNAME="admin"
UI_PASSWORD="your-super-admin-password"

# --- Optional: Audit Logging (OpenObserve) ---
OPENOBSERVE_URL="http://your-openobserve:5080"
OPENOBSERVE_ORG="default"
OPENOBSERVE_STREAM="alchemi_audit"
OPENOBSERVE_USER=""
OPENOBSERVE_PASSWORD=""
ALCHEMI_AUDIT_LOG_RETENTION_DAYS="90"

# --- Optional: Provider API Keys ---
# Each account adds their own models via the UI/API.
# These are only needed if you want system-level defaults.
# OPENAI_API_KEY=""
# ANTHROPIC_API_KEY=""
# AZURE_API_KEY=""
# AZURE_API_BASE=""
# AZURE_API_VERSION=""
```

**Important:** There is no default `config.yaml` to load. Each tenant configures their own models, guardrails, and settings through the database. Set `STORE_MODEL_IN_DB=True` to enable this.

### 3. Database Setup

```bash
# Start PostgreSQL (via Docker or local install)
docker run -d --name litellm_db \
  -e POSTGRES_DB=litellm \
  -e POSTGRES_USER=llmproxy \
  -e POSTGRES_PASSWORD=dbpassword9090 \
  -p 5432:5432 \
  postgres:16

# Generate the Prisma client from the root schema
cd /workspaces/console-cockpit
cp schema.prisma litellm/proxy/schema.prisma  # Sync the active schema
poetry run prisma generate --schema=./schema.prisma
poetry run prisma db push --schema=./schema.prisma
```

### 4. Run the Proxy Server

```bash
# Development mode
poetry run python litellm/proxy/proxy_cli.py

# Or using the litellm CLI entrypoint
poetry run litellm --port 4000

# The proxy starts at http://localhost:4000
# Admin dashboard is served at http://localhost:4000/ui
```

### 5. Build and Deploy UI Changes

The admin dashboard is a Next.js app. After modifying UI source files, you must rebuild and copy the output to the proxy's static directory.

```bash
cd /workspaces/console-cockpit/ui/litellm-dashboard

# Install frontend dependencies
npm install

# Development mode (hot reload)
npm run dev

# Production build
npm run build

# Copy built output to proxy's static directory
cp -r out/ ../../litellm/proxy/_experimental/out/
```

After copying, restart the proxy server to serve the updated UI.

### 6. Run Tests

```bash
# Python unit tests
poetry run pytest tests/test_litellm/ -v --numprocesses=4

# Frontend tests
cd ui/litellm-dashboard
npm test

# Linting
make lint
```

## Docker Deployment

### Using Docker Compose

```bash
cd /workspaces/console-cockpit

# Create .env with your secrets (see Environment Variables above)

# Start all services (proxy + postgres + prometheus)
docker compose up -d

# Check status
docker compose ps
docker compose logs -f litellm

# Stop
docker compose down
```

Services:
| Service | URL | Description |
|---------|-----|-------------|
| Proxy / Dashboard | http://localhost:4000 | AI gateway + admin UI |
| PostgreSQL | localhost:5432 | Database |
| Prometheus | http://localhost:9090 | Metrics |

### Building the Docker Image

```bash
docker build -t alchemi-console:latest .
```

## Login Flow

The login page uses an email-first flow for per-account SSO routing:

1. User enters their email/username and clicks "Continue"
2. The backend `/v2/login/resolve` endpoint checks the email domain
3. If the domain maps to an account with SSO configured, the user is redirected to the SSO provider
4. Otherwise, the user sees a password field for standard login
5. Super admins (using `UI_USERNAME`) go directly to password login and see only the Tenant Management page

## Multi-Tenant Data Model

### Alchemi Tables (in `schema.prisma`)

| Table | Purpose |
|-------|---------|
| `Alchemi_AccountTable` | Tenant accounts with name, domain, status, budget |
| `Alchemi_AccountAdminTable` | Account administrators (by email) |
| `Alchemi_AccountSSOConfig` | Per-account SSO provider configuration |

### Tenant Scoping

Every existing LiteLLM table has an `account_id` column added (nullable, indexed). The `TenantScopedPrismaClient` in `alchemi/db/tenant_scoped_prisma.py` intercepts all database queries and automatically filters by the current account's `account_id`, which is set per-request via middleware.

Scoped tables include: organizations, teams, users, verification tokens (keys), models, agents, MCP servers, guardrails, policies, budgets, spend logs, audit logs, access groups, and more.

## API Endpoints

### Account Management (Super Admin Only)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/account/new` | Create a new tenant account |
| GET | `/account/list` | List all accounts |
| GET | `/account/{id}` | Get account details |
| PUT | `/account/{id}` | Update account settings |
| DELETE | `/account/{id}` | Suspend account (soft delete) |
| POST | `/account/{id}/admin` | Add account admin |
| DELETE | `/account/{id}/admin/{email}` | Remove account admin |

### Login

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v2/login/resolve` | Resolve email to SSO or password login |

All standard LiteLLM API endpoints (`/chat/completions`, `/key/generate`, `/team/new`, etc.) are available and automatically scoped to the caller's account.

## Alchemi Module Reference

| Module | Purpose |
|--------|---------|
| `alchemi.auth.account_resolver` | Resolves `account_id` from email domain |
| `alchemi.auth.sso_router` | Per-account SSO routing logic |
| `alchemi.auth.super_admin` | Super admin verification |
| `alchemi.config.settings` | Proxy configuration (master key, UI creds) |
| `alchemi.db.tenant_scoped_prisma` | Multi-tenant Prisma wrapper |
| `alchemi.endpoints.account_endpoints` | Account CRUD REST API |
| `alchemi.endpoints.audit_log_endpoints` | Audit log query API |
| `alchemi.hooks.audit_logger` | Audit event capture to OpenObserve |
| `alchemi.hooks.secret_detection` | PII/secret masking in requests |
| `alchemi.hooks.batch_cost` | Batch processing cost tracking |
| `alchemi.hooks.responses_cost` | Response cost calculation |
| `alchemi.enterprise_features.*` | Guardrails, moderation, email, SSO, blocklists |
| `alchemi.integrations.openobserve` | OpenObserve HTTP client |
| `alchemi.middleware.account_middleware` | FastAPI middleware for account resolution |
| `alchemi.middleware.tenant_context` | ContextVar for per-request account_id |

## Key Customizations from LiteLLM Base

1. **`enterprise/` directory removed** -- replaced by `alchemi/` (MIT-compatible)
2. **`premium_user` forced to `True`** -- all enterprise features enabled
3. **All UI references to "LiteLLM" replaced** with "Alchemi Studio Console"
4. **External docs.litellm.ai links removed** from user-facing UI
5. **Login page redesigned** with email-first flow for SSO routing
6. **Super admin role added** -- sees only Tenant Management page
7. **`account_id` column added** to all major database tables
8. **Tenant-scoped Prisma wrapper** auto-filters queries per account
9. **SSO callback wired** to resolve `account_id` from email domain
10. **Sidebar customized** -- Learning Resources, survey prompts, and community links removed

## License

- LiteLLM base code: [MIT License](https://opensource.org/licenses/MIT)
- `alchemi/` directory: Proprietary (Alchemi)
- The original LiteLLM `enterprise/` directory has been removed from this codebase
