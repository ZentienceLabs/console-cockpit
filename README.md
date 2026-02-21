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
│   ├── endpoints/              #   30 REST endpoint files (account, agents, workspace, etc.)
│   ├── enterprise_features/    #   Guardrails, moderation, email, SSO handler
│   ├── hooks/                  #   Audit logger, cost tracking, secret detection
│   ├── integrations/           #   OpenObserve client
│   └── middleware/             #   Account middleware, tenant context
├── litellm/                    # LiteLLM base (MIT licensed)
│   ├── proxy/                  #   FastAPI proxy server
│   │   ├── proxy_server.py     #   Main server (~12,500 lines)
│   │   ├── schema.prisma       #   Synced copy of root schema (don't edit directly)
│   │   ├── auth/               #   Auth handlers
│   │   └── management_endpoints/ # Admin APIs
│   └── llms/                   #   100+ provider implementations
├── prisma/                     # Alchemi database migrations (source of truth)
│   └── migrations/
│       └── 20260217100000_alchemi_multi_tenant/
│           └── migration.sql
├── scripts/
│   └── deploy.sh               # Standard deployment script (migrate, build-ui, start)
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

### Environment Variables
The frontend uses very few env vars. Only two matter at runtime:

Variable	Dev Value	Prod Value	Purpose
NODE_ENV	development	production	Controls whether API calls go to http://localhost:4000 (dev) or the same-origin proxy (prod)
NEXT_PUBLIC_BASE_URL	""	"ui/"	Route prefix -- dev serves at /, prod at /ui/


### 3. Database Setup

```bash
# Start PostgreSQL (via Docker or local install)
docker run -d --name litellm_db \
  -e POSTGRES_DB=litellm \
  -e POSTGRES_USER=llmproxy \
  -e POSTGRES_PASSWORD=dbpassword9090 \
  -p 5432:5432 \
  postgres:16

# Sync schema + run migrations (standard way)
./scripts/deploy.sh migrate
```

The deploy script handles everything: syncing `schema.prisma` to all required locations, copying Alchemi migrations into `litellm_proxy_extras`, and running `prisma migrate deploy`.

If you prefer manual steps:
```bash
# 1. Sync schema everywhere
cp schema.prisma litellm/proxy/schema.prisma
cp schema.prisma "$(python3 -c 'import litellm_proxy_extras,os;print(os.path.dirname(litellm_proxy_extras.__file__))')/schema.prisma"

# 2. Copy Alchemi migrations into litellm_proxy_extras
cp -r prisma/migrations/* "$(python3 -c 'import litellm_proxy_extras,os;print(os.path.dirname(litellm_proxy_extras.__file__))')/migrations/"

# 3. Generate Prisma client
poetry run prisma generate --schema=./schema.prisma

# 4. Apply migrations
cd "$(python3 -c 'import litellm_proxy_extras,os;print(os.path.dirname(litellm_proxy_extras.__file__))')"
poetry run prisma migrate deploy --schema=./schema.prisma
cd /workspaces/console-cockpit
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

**Quick rebuild (one-liner):**
```bash
cd ui/litellm-dashboard && npm run build && rm -rf ../../litellm/proxy/_experimental/out && cp -r out ../../litellm/proxy/_experimental/out
```

Then restart the server:
```bash
# Kill existing server (Ctrl+C or pkill -f litellm)
poetry run litellm --port 4000
```

Or use the deploy script:
```bash
./scripts/deploy.sh build-ui     # Build + copy
./scripts/deploy.sh start        # Start server
```

**Full UI development workflow:**
```bash
# Terminal 1: Start the proxy server (backend)
poetry run litellm --port 4000

# Terminal 2: Start Next.js dev server (frontend hot reload on :3000)
cd ui/litellm-dashboard
npm install
npm run dev

# When done making changes, build and deploy to the proxy:
npm run build
rm -rf ../../litellm/proxy/_experimental/out
cp -r out ../../litellm/proxy/_experimental/out

# Restart the proxy server to serve the updated UI
```

**Important:** The proxy serves the UI from `litellm/proxy/_experimental/out/`. Changes to files in `ui/litellm-dashboard/src/` are not reflected until you run `npm run build` and copy the output. The `npm run dev` hot-reload server runs separately on port 3000 for development convenience only.

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

## Deployment

### Deploy Script

The `scripts/deploy.sh` script is the standard way to deploy to any environment. It handles schema sync, database migration, UI build, and server startup in one command.

```bash
./scripts/deploy.sh              # Full deploy: migrate + build UI + start
./scripts/deploy.sh migrate      # DB only: sync schema + apply migrations
./scripts/deploy.sh build-ui     # UI only: npm build + copy output
./scripts/deploy.sh start        # Server only: start proxy on $PORT (default 4000)
```

### Deploying to Different Environments

Each environment needs its own `DATABASE_URL`. Set it before running the deploy script:

```bash
# Dev (local)
export DATABASE_URL="postgresql://llmproxy:dbpassword@localhost:5432/litellm"
./scripts/deploy.sh migrate

# Devtest
export DATABASE_URL="postgresql://user:pass@devtest-db.example.com:5432/consoledb"
./scripts/deploy.sh migrate

# Staging
export DATABASE_URL="postgresql://user:pass@stage-db.example.com:5432/consoledb"
./scripts/deploy.sh migrate

# Production
export DATABASE_URL="postgresql://user:pass@prod-db.example.com:5432/consoledb"
./scripts/deploy.sh migrate
```

The migration is **idempotent** -- every statement uses `IF NOT EXISTS` guards. You can safely run it multiple times against the same database.

### How Migrations Work

Alchemi uses Prisma Migrate under the hood. Here's the flow:

```
prisma/migrations/                     (repo: source of truth for Alchemi migrations)
  └── 20260217100000_alchemi_multi_tenant/
        └── migration.sql

        ↓  deploy.sh copies into  ↓

litellm_proxy_extras/migrations/       (package: where Prisma looks for migrations)
  ├── 20250326162113_baseline/         (80 base LiteLLM migrations from the package)
  ├── ...
  └── 20260217100000_alchemi_multi_tenant/   (our Alchemi migration, copied in)

        ↓  prisma migrate deploy  ↓

PostgreSQL _prisma_migrations table    (tracks which migrations have been applied)
```

**Key points:**
- `litellm_proxy_extras` ships with ~80 base LiteLLM migrations. Our Alchemi migrations are additive.
- `prisma migrate deploy` checks the `_prisma_migrations` table and only applies pending migrations.
- The `schema.prisma` must also be synced into `litellm_proxy_extras/` (the deploy script does this) so the post-migration sanity check doesn't try to revert our columns.
- At server startup, `litellm_proxy_extras` also runs `prisma migrate deploy` automatically, so even without running the script first, the server will self-heal.

### Adding New Migrations

When you modify the database schema:

1. Edit the root `schema.prisma`
2. Create a new migration SQL file:
   ```
   prisma/migrations/<YYYYMMDDHHMMSS>_<description>/migration.sql
   ```
3. Write idempotent SQL (use `IF NOT EXISTS`, `DO $$ BEGIN ... END $$` blocks)
4. Run `./scripts/deploy.sh migrate` to test locally
5. Commit the migration to the repo
6. Deploy to each environment: `DATABASE_URL=... ./scripts/deploy.sh migrate`

### Docker Deployment

#### Using Docker Compose

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

#### Building the Docker Image

```bash
docker build -t alchemi-console:latest .
```

The Dockerfile automatically syncs the Alchemi schema and migrations into `litellm_proxy_extras` at build time. When the container starts, `litellm_proxy_extras` runs `prisma migrate deploy` to apply pending migrations to the target database.

#### Pre-Migrate Before Deploy (Recommended for Prod)

For production, run migrations as a separate step before deploying the new container:

```bash
# Build the image
docker build -t alchemi-console:v1.2.3 .

# Run migrations only (doesn't start the server)
docker run --rm \
  -e DATABASE_URL="postgresql://user:pass@prod-db:5432/consoledb" \
  alchemi-console:v1.2.3 \
  bash -c "cd /app && python3 -c \"
import litellm_proxy_extras,os,subprocess
d=os.path.dirname(litellm_proxy_extras.__file__)
subprocess.run(['prisma','migrate','deploy','--schema',d+'/schema.prisma'],cwd=d,check=True)
\""

# Then deploy the new container (migrations already applied)
docker compose up -d
```

Or with Kubernetes init containers:
```yaml
initContainers:
  - name: migrate
    image: alchemi-console:v1.2.3
    command: ["bash", "-c"]
    args:
      - |
        cd /app
        EXTRAS=$(python3 -c "import litellm_proxy_extras,os;print(os.path.dirname(litellm_proxy_extras.__file__))")
        prisma migrate deploy --schema="$EXTRAS/schema.prisma"
    env:
      - name: DATABASE_URL
        valueFrom:
          secretKeyRef:
            name: db-credentials
            key: url
containers:
  - name: app
    image: alchemi-console:v1.2.3
    args: ["--port", "4000"]
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

### Centralized Management API (`/alchemi/*`)

These endpoints serve as the centralized data layer for both **alchemi-web** (Next.js) and **alchemi-ai** (FastAPI). Both applications have been migrated from direct database access (Sequelize/asyncpg) to calling these REST endpoints via HTTP clients, with `x-account-id` header for tenant scoping and `LITELLM_MASTER_KEY` for authentication.

| Prefix | Endpoint File | Description |
|--------|--------------|-------------|
| `/alchemi/token` | `access_token_endpoints.py` | Access token CRUD, validation, update-last-used, cleanup |
| `/alchemi/account-connection` | `account_connection_endpoints.py` | Account-level connection bindings |
| `/alchemi/account` | `account_endpoints.py` | Account CRUD (super admin) |
| `/alchemi/agentdef` | `agent_def_endpoints.py` | Agent definition CRUD, search, activate/deactivate |
| `/alchemi/agentgroup` | `agent_group_endpoints.py` | Agent group management |
| `/alchemi/audit` | `audit_log_endpoints.py` | Audit log queries |
| `/alchemi/config` | `config_endpoints.py` | System configuration |
| `/alchemi/connection` | `connection_endpoints.py` | Integration connection management |
| `/alchemi/cost` | `cost_tracking_endpoints.py` | Cost tracking and spend reports |
| `/alchemi/credit-budget` | `credit_budget_endpoints.py` | Credit budget management |
| `/alchemi/discussion` | `discussion_endpoints.py` | Discussion threads and messages |
| `/alchemi/effective-access` | `effective_access_endpoints.py` | User effective access queries |
| `/alchemi/email-event` | `email_event_endpoints.py` | Email event tracking |
| `/alchemi/group` | `group_endpoints.py` | User group management |
| `/alchemi/guardrails` | `guardrails_config_endpoints.py` | Guardrail configuration CRUD |
| `/alchemi/invite` | `invite_endpoints.py` | User invitation management |
| `/alchemi/marketplace` | `marketplace_endpoints.py` | Marketplace listing CRUD |
| `/alchemi/mcp` | `mcp_config_endpoints.py` | MCP server configuration |
| `/alchemi/mvp` | `mvp_config_endpoints.py` | MVP configuration |
| `/alchemi/membership` | `membership_endpoints.py` | Account membership management |
| `/alchemi/notification` | `notification_endpoints.py` | Notification management |
| `/alchemi/override-config` | `override_config_endpoints.py` | Account override configuration |
| `/alchemi/quota` | `quota_endpoints.py` | Account quota management |
| `/alchemi/role` | `role_permission_endpoints.py` | Role and permission management |
| `/alchemi/subscription` | `subscription_endpoints.py` | Subscription management |
| `/alchemi/ticket` | `support_ticket_endpoints.py` | Support ticket CRUD |
| `/alchemi/team` | `team_endpoints.py` | Team management |
| `/alchemi/user` | `user_endpoints.py` | User profile management |
| `/alchemi/workspace` | `workspace_endpoints.py` | Workspace CRUD and member management |

All management endpoints use Prisma (via `prisma_client`) for database access and are registered in `proxy_server.py` via `app.include_router()`.

### Database Schema

The Prisma schema (`schema.prisma`) contains **91 models** total:
- **48 `LiteLLM_*` tables** -- base LiteLLM models (keys, teams, organizations, models, spend logs, etc.)
- **43 `Alchemi_*` tables** -- tenant management tables migrated from alchemi-web and alchemi-ai (accounts, agents, workspaces, connections, guardrails, marketplace, etc.)

All tables include `account_id` for tenant scoping. See `schema.prisma` for the full model list.

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

## Production Deployment (Azure Kubernetes Service)

### Prerequisites

- Azure CLI (`az`) authenticated
- `kubectl` configured for your AKS cluster
- `docker` CLI
- `helm` v3+
- Azure Container Registry (ACR) — e.g. `myacr.azurecr.io`
- Azure Database for PostgreSQL — connection string ready
- GitHub repo with Actions enabled

Set these once per shell session:

```bash
ACR_NAME="myacr"                  # your ACR name (without .azurecr.io)
AKS_CLUSTER="my-aks"
AKS_RESOURCE_GROUP="my-rg"
IMAGE_TAG="v1.0.0"                # or git SHA, date, etc.
```

---

### Step 1: Build and Push the Container Image

The root `Dockerfile` is a multi-stage build:
1. **Builder stage** — installs Python build deps, compiles the pip wheel, builds the Next.js admin UI
2. **Runtime stage** — installs the wheel, generates the Prisma client, syncs Alchemi schema/migrations, sets up supervisor

```bash
# Login to ACR
az acr login --name $ACR_NAME

# Build
docker build -t $ACR_NAME.azurecr.io/alchemi-console:$IMAGE_TAG .

# Push
docker push $ACR_NAME.azurecr.io/alchemi-console:$IMAGE_TAG
```

The admin UI (Next.js) is compiled during the Docker build and embedded into the image. There is no separate frontend container.

---

### Step 2: Building the Web Frontend (UI)

The admin dashboard lives in `ui/litellm-dashboard/` (Next.js 16, React 18, Tailwind, Ant Design). It is built **inside** the Docker image automatically, but you can also build it standalone.

**Inside Docker (default, no action needed):**

The `Dockerfile` runs `docker/build_admin_ui.sh` during the builder stage, which runs `npm install && npm run build` and bundles the output into the image at `/app/litellm/proxy/_experimental/out/`.

**Standalone build (for local dev or debugging):**

```bash
cd ui/litellm-dashboard
npm install
npm run build                     # produces out/ directory (static export)

# Deploy to the proxy's static file directory
rm -rf ../../litellm/proxy/_experimental/out
cp -r out ../../litellm/proxy/_experimental/out
```

**Dev mode with hot-reload:**

```bash
# Terminal 1: backend
poetry run litellm --port 4000

# Terminal 2: frontend (hot-reload on port 3000)
cd ui/litellm-dashboard && npm run dev
```

---

### Step 3: Create Kubernetes Secrets

```bash
# Get AKS credentials
az aks get-credentials --resource-group $AKS_RESOURCE_GROUP --name $AKS_CLUSTER

# Create namespace (optional)
kubectl create namespace alchemi

# Create secrets
kubectl create secret generic alchemi-db-credentials \
  --namespace alchemi \
  --from-literal=DATABASE_URL="postgresql://user:pass@your-pg-server.postgres.database.azure.com:5432/consoledb?sslmode=require" \
  --from-literal=username="user" \
  --from-literal=password="your-db-password"

kubectl create secret generic alchemi-env-secrets \
  --namespace alchemi \
  --from-literal=LITELLM_MASTER_KEY="sk-your-production-master-key" \
  --from-literal=UI_USERNAME="admin" \
  --from-literal=UI_PASSWORD="your-secure-password" \
  --from-literal=REDIS_URL="rediss://default:password@your-redis.redis.cache.windows.net:6380/0" \
  --from-literal=EMAIL_REDIS_HOST="your-email-redis.redis.azure.net" \
  --from-literal=EMAIL_REDIS_PORT="10000" \
  --from-literal=EMAIL_REDIS_PASSWORD="your-email-redis-password" \
  --from-literal=EMAIL_REDIS_TLS="true" \
  --from-literal=EMAIL_REDIS_ENVIRONMENT="prod" \
  --from-literal=OPENOBSERVE_URL="https://openobserve.example.com/api/default" \
  --from-literal=OPENOBSERVE_USER="admin@example.com" \
  --from-literal=OPENOBSERVE_PASSWORD="your-oo-password"
```

---

### Step 4: Create Production Helm Values

Create `deploy/values-prod.yaml`:

```yaml
replicaCount: 2

image:
  repository: myacr.azurecr.io/alchemi-console    # your ACR image
  pullPolicy: Always
  tag: "v1.0.0"                                    # overridden by CI

# Reference existing secrets instead of deploying a bundled database
db:
  useExisting: true
  deployStandalone: false
  endpoint: your-pg-server.postgres.database.azure.com
  database: consoledb
  secret:
    name: alchemi-db-credentials
    usernameKey: username
    passwordKey: password

# Inject secrets as env vars into the pod
environmentSecrets:
  - alchemi-env-secrets

# Proxy config (models managed via DB, not config file)
proxy_config:
  model_list:
    - model_name: placeholder
      litellm_params:
        model: openai/placeholder
        api_key: managed-via-db
  general_settings:
    store_model_in_db: true
    master_key: os.environ/LITELLM_MASTER_KEY

# Extra env vars (non-secret)
envVars:
  STORE_MODEL_IN_DB: "True"
  DOCS_URL: "/api-docs"
  ROOT_REDIRECT_URL: "/ui"
  PROXY_BASE_URL: "https://console.example.com"
  EMAIL_SUPPORT_CONTACT: "hello@example.com"
  OPENOBSERVE_ORG: "default"
  OPENOBSERVE_STREAM: "alchemi_audit"
  ALCHEMI_AUDIT_LOG_RETENTION_DAYS: "90"

# Ingress (adjust for your domain and cert)
ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
  hosts:
    - host: console.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: alchemi-console-tls
      hosts:
        - console.example.com

# Resources
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi

# Autoscaling
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

# Pod disruption budget
pdb:
  enabled: true
  maxUnavailable: 1

# Database migration job (runs before deploy)
migrationJob:
  enabled: true
  retries: 3
  hooks:
    argocd:
      enabled: false
    helm:
      enabled: true    # run as Helm pre-install/pre-upgrade hook

# Prometheus metrics
serviceMonitor:
  enabled: false       # set true if using kube-prometheus-stack
```

---

### Step 5: Deploy with Helm

```bash
# Attach ACR to AKS (one-time, allows AKS to pull images from ACR)
az aks update --name $AKS_CLUSTER --resource-group $AKS_RESOURCE_GROUP \
  --attach-acr $ACR_NAME

# Build Helm dependencies (PostgreSQL/Redis subcharts — skipped when using external DB)
helm dependency build deploy/charts/litellm-helm/

# Deploy
helm upgrade --install alchemi-console deploy/charts/litellm-helm/ \
  --namespace alchemi \
  --create-namespace \
  -f deploy/values-prod.yaml \
  --set image.tag=$IMAGE_TAG

# Watch rollout
kubectl rollout status deployment/litellm -n alchemi
kubectl get pods -n alchemi
```

---

### Step 6: Verify

```bash
# Port-forward to test before exposing via ingress
kubectl port-forward svc/litellm 4000:4000 -n alchemi

# Liveness (no auth)
curl http://localhost:4000/health/liveliness

# Full health (requires master key)
curl -H "Authorization: Bearer sk-your-production-master-key" http://localhost:4000/health

# Admin UI
open http://localhost:4000/ui
```

Once ingress is configured: `https://console.example.com/` redirects to the admin UI.

---

### GitHub Actions CI/CD

Add the following secrets to your GitHub repo (`Settings > Secrets and variables > Actions`):

| Secret | Value |
|--------|-------|
| `AZURE_CREDENTIALS` | Service principal JSON (`az ad sp create-for-rbac --sdk-auth`) |
| `ACR_NAME` | Your ACR name (e.g. `myacr`) |
| `AKS_CLUSTER_NAME` | AKS cluster name |
| `AKS_RESOURCE_GROUP` | AKS resource group |

Create `.github/workflows/deploy.yml`:

```yaml
name: Build and Deploy to AKS

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      image_tag:
        description: "Image tag (defaults to git SHA)"
        required: false

env:
  IMAGE_TAG: ${{ github.event.inputs.image_tag || github.sha }}

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Login to ACR
        uses: azure/docker-login@v1
        with:
          login-server: ${{ secrets.ACR_NAME }}.azurecr.io
          username: ${{ secrets.AZURE_CREDENTIALS && fromJson(secrets.AZURE_CREDENTIALS).clientId }}
          password: ${{ secrets.AZURE_CREDENTIALS && fromJson(secrets.AZURE_CREDENTIALS).clientSecret }}

      - name: Build and push image
        run: |
          docker build -t ${{ secrets.ACR_NAME }}.azurecr.io/alchemi-console:${{ env.IMAGE_TAG }} .
          docker push ${{ secrets.ACR_NAME }}.azurecr.io/alchemi-console:${{ env.IMAGE_TAG }}

      - name: Set AKS context
        uses: azure/aks-set-context@v3
        with:
          resource-group: ${{ secrets.AKS_RESOURCE_GROUP }}
          cluster-name: ${{ secrets.AKS_CLUSTER_NAME }}
          admin: false
        env:
          AZURE_CREDENTIALS: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Deploy with Helm
        run: |
          helm dependency build deploy/charts/litellm-helm/
          helm upgrade --install alchemi-console deploy/charts/litellm-helm/ \
            --namespace alchemi \
            --create-namespace \
            -f deploy/values-prod.yaml \
            --set image.tag=${{ env.IMAGE_TAG }} \
            --wait --timeout 10m
```

**Pipeline flow:**
1. Push to `main` (or manual trigger with a tag)
2. Builds the Docker image (Python backend + Next.js UI in one image)
3. Pushes to ACR
4. Sets AKS kubectl context
5. Helm upgrade runs the migration job (pre-upgrade hook), then rolls out new pods
6. `--wait` ensures the deploy only succeeds if pods become healthy

---

### Upgrading

```bash
# 1. Build new image
docker build -t $ACR_NAME.azurecr.io/alchemi-console:v1.1.0 .
docker push $ACR_NAME.azurecr.io/alchemi-console:v1.1.0

# 2. Deploy (migration job runs automatically as Helm pre-upgrade hook)
helm upgrade alchemi-console deploy/charts/litellm-helm/ \
  --namespace alchemi \
  -f deploy/values-prod.yaml \
  --set image.tag=v1.1.0

# 3. Watch rollout
kubectl rollout status deployment/litellm -n alchemi
```

Or just push to `main` and let GitHub Actions handle it.

---

### Health Check Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `/health/liveliness` | None | Liveness probe (for k8s) |
| `/health/readiness` | None | Readiness probe (for k8s) |
| `/health` | Master key | Full health with per-model status |
| `/api-docs` | None | Swagger/OpenAPI documentation |

---

## License

- LiteLLM base code: [MIT License](https://opensource.org/licenses/MIT)
- `alchemi/` directory: Proprietary (Alchemi)
- The original LiteLLM `enterprise/` directory has been removed from this codebase
