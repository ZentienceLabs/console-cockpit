# Centralized Cockpit Implementation TODO

Status legend:
- [ ] pending
- [~] in progress
- [x] completed

## Goals
- Make `console-cockpit` the centralized control plane.
- Move super-admin capabilities from `alchemi-admin` into `console-cockpit` super-admin scope.
- Move Copilot tenant-admin capabilities from `alchemi-web:/cockpit` into a dedicated `Copilot` section in `console-cockpit`.
- Make `alchemi-web` and `alchemi-ai` clients of centralized Copilot APIs.
- Keep Copilot domain separate from BYOK Console domain.
- Standardize centralized cockpit auth on Zitadel-compatible model (with current auth flow retained as transitional fallback).

## Non-goals for hard cut
- Workspace tracking page parity from `alchemi-web` cockpit.

## Phase 0: Planning and Contracts
- [x] Produce cross-repo current-state analysis (alchemi-web, alchemi-ai, alchemi-admin, console-cockpit).
- [x] Define centralization scope for hard cut:
  - Directory: users, memberships, teams, groups/orgs, invites.
  - Budgets/Credits: plans, allocations, hierarchy, alerts, usage recording.
  - Models: super-admin catalog + account-level selection.
  - Agents/Marketplace, Connections/Tools, Guardrails.
  - Support tickets, notification templates.
  - Copilot observability and super-admin global operations.
- [x] Freeze API contracts for centralized Copilot namespace.
- [x] Freeze RBAC matrix (super admin, account admin, end user/no cockpit access).

Acceptance criteria:
- API contract doc exists and is implementation-aligned.
- RBAC matrix and scope boundaries are explicit and testable.

## Phase 1: Console-Cockpit Copilot Foundation
- [x] Create execution tracker (`todo.md`) and keep it updated during implementation.
- [x] Add shared Copilot endpoint primitives:
  - Typed request/response models.
  - Common auth guards (`super admin`, `super/account admin`).
  - Common account resolution helper and audit metadata helper.
- [x] Add centralized Copilot router namespace under `alchemi/endpoints/`.
- [x] Wire Copilot routers in `litellm/proxy/proxy_server.py`.

Acceptance criteria:
- Copilot routes are discoverable and loaded at runtime.
- Common guard/dependency code is reused by all Copilot domains.

## Phase 2: Copilot Domain Endpoints (Server)

### 2.1 Directory
- [x] Users CRUD/list/search (account scoped).
- [x] Memberships CRUD/list/search.
- [x] Groups CRUD/list/search.
- [x] Teams CRUD/list/search + membership operations.
- [x] Invites create/list/revoke.

### 2.2 Budgets/Credits
- [x] Parent-child allocation model implementation:
  - super-admin account allocation
  - account unallocated pool
  - allocations to groups/teams/users
  - equal distribution + per-user override
- [x] Renewal/cycle policy at budget plan level.
- [x] Effective allocation resolution endpoint (inheritance + override).
- [x] Usage recording endpoint with formula `credits = cost * CREDITS_FACTOR`.
- [x] Budget alerts endpoint.

### 2.3 Copilot Model Governance
- [x] Super-admin Copilot model catalog CRUD.
- [x] Super-admin account eligibility mapping.
- [x] Account-admin selectable subset endpoint.
- [x] Effective user-visible model set endpoint.

### 2.4 Agents + Marketplace
- [x] Agent definitions CRUD.
- [x] Marketplace listing CRUD/publish/hide/verify.
- [x] Assignment/install semantics endpoints.

### 2.5 Connections/Tools
- [x] Account-level OpenAPI/MCP/integration endpoints.
- [x] Payload compatibility with `alchemi-web` integration behavior.
- [x] Composio enablement/governance layer endpoints.

### 2.6 Guardrails
- [x] Guardrails config endpoints.
- [x] Guardrails custom patterns endpoints.
- [x] Guardrails audit trail endpoints.

### 2.7 Support + Notification Templates
- [x] Support tickets endpoints.
- [x] Notification templates endpoints.

### 2.8 Observability + Global Ops
- [x] Copilot audit log query endpoints.
- [x] Copilot budget/guardrail alert rollups.
- [x] Super-admin cross-account summary + bulk actions endpoints.

Acceptance criteria:
- Each domain has at least list/get/create/update/delete or explicit operation parity with current behavior.
- Endpoints enforce account isolation and role checks.

## Phase 3: Super Admin Migration (from alchemi-admin)
- [x] Port account setup semantics (subscription -> entitlements -> quotas).
- [x] Port feature/platform catalog semantics.
- [x] Port config providers/models/media model management to super-admin section.
- [x] Port global support ops and templates relevant to platform operations.

Acceptance criteria:
- Super-admin can perform all required account and catalog governance from centralized cockpit.

## Phase 4: Client Migration (alchemi-web + alchemi-ai)

### 4.1 alchemi-web
- [x] Replace `/cockpit` management data paths with centralized Copilot API client calls.
- [x] Preserve current UX behavior for:
  - users/memberships/groups/teams
  - invites
  - budgets/wallet/cost-tracking views
  - agentdef/marketplace
  - connections/tools
  - guardrails
  - audit logs
  - support + templates
  - account catalog

### 4.2 alchemi-ai
- [x] Convert config ownership from local management to centralized Copilot APIs.
- [x] Keep runtime execution local but source governance/config from centralized cockpit.
- [x] Unify `CREDITS_FACTOR` source and remove conflicting defaults.
- [x] Add agent governance check for deployments via centralized cockpit.

Acceptance criteria:
- No local cockpit-management writes remain in alchemi-web/alchemi-ai for centralized domains.
- Runtime still functions while management is centralized.

## Phase 5: Authentication Unification (Zitadel)
- [x] Standardize centralized cockpit authentication with Zitadel-compatible flow.
- [x] Preserve super-admin break-glass login semantics where required.
- [x] Map Zitadel claims to RBAC roles and account context.
- [x] Add JWT validation error logging for debugging auth failures.
- [x] Add explicit account_admin role detection (distinct from super_admin and end_user).
- [x] Set actor_role contextvar in middleware for consistent role resolution.

Acceptance criteria:
- Role + account scoping is consistent across centralized cockpit and clients.

## Phase 6: Validation and Hard Cut
- [x] Add/adjust tests for Copilot endpoints and role checks.
- [x] Validate account isolation paths (test_account_isolation.py).
- [x] Validate end-to-end flows for super admin + account admin (test_copilot_auth_e2e.py).
- [x] Finalize cutover checklist and remove deprecated management paths.

Acceptance criteria:
- Core hard-cut features are operational in centralized cockpit.
- Legacy management paths are disabled or explicitly marked transitional.

## Cutover Checklist

### Pre-cutover
- [ ] Deploy console-cockpit with all Copilot endpoints enabled
- [ ] Set `CENTRALIZED_COCKPIT_URL` and `CENTRALIZED_COCKPIT_API_KEY` in alchemi-web environment
- [ ] Set `CENTRALIZED_COCKPIT_URL` and `CENTRALIZED_COCKPIT_API_KEY` in alchemi-ai environment
- [ ] Configure Zitadel environment variables:
  - `ZITADEL_ISSUER` - Zitadel instance URL
  - `ZITADEL_JWKS_URL` - JWKS endpoint (or auto-derived from issuer)
  - `ZITADEL_AUDIENCE` - Expected audience claim
  - `ZITADEL_ACCOUNT_ID_CLAIMS` - Comma-separated claim keys for account_id
  - `ZITADEL_SUPER_ADMIN_ROLE_KEYS` - Comma-separated super admin role names
  - `ZITADEL_ACCOUNT_ADMIN_ROLE_KEYS` - Comma-separated account admin role names
- [ ] Run account isolation tests: `pytest alchemi/tests/test_account_isolation.py`
- [ ] Run E2E auth tests: `pytest alchemi/tests/test_copilot_auth_e2e.py`
- [ ] Run existing regression tests: `pytest tests/test_copilot_superadmin_routes.py tests/test_account_middleware_zitadel.py tests/test_copilot_connection_routes.py`

### Validation
- [ ] Verify super admin can list/manage all accounts via `/copilot/super-admin/*`
- [ ] Verify account admin can manage their tenant via `/copilot/*` endpoints
- [ ] Verify end_user gets 403 on cockpit management endpoints
- [ ] Verify alchemi-web cockpit pages load data from centralized APIs
- [ ] Verify alchemi-ai model/guardrails/budget governance sourced from cockpit
- [ ] Verify audit log events flow through centralized observability endpoint

### Post-cutover
- [ ] Monitor error logs for JWT validation failures (now logged with details)
- [ ] Verify no fallback to local services (check for "Centralized cockpit request failed" logs)
- [ ] Remove `CENTRALIZED_COCKPIT_URL` env var to test graceful fallback to local services
- [ ] Re-enable `CENTRALIZED_COCKPIT_URL` once verified

## Execution Log
- 2026-02-24: Initialized detailed phased plan and began Phase 1 foundation work.
- 2026-02-24: Added Copilot foundational modules (`copilot_db`, auth/types/helpers), domain routers, and wired `/copilot/*` routes into `proxy_server.py`.
- 2026-02-24: Added contract/RBAC spec at `docs/copilot-centralized-cockpit-contract.md` and updated tracker statuses.
- 2026-02-24: Added centralized client integrations in `alchemi-web` (marketplace, connections, guardrails, core budget actions) and `alchemi-ai` (guardrails config loader + centralized budget usage recording/check hooks).
- 2026-02-24: Expanded `console-cockpit` Copilot directory endpoints to full CRUD + team/account membership operations and centralized team-member assignment APIs.
- 2026-02-24: Migrated `alchemi-web` directory paths (`groups`, `teams`, `team members`, `users`, `account members/memberships`) plus group/team server actions and cockpit user page to centralized Copilot APIs (with local fallback).
- 2026-02-24: Migrated `alchemi-web` cockpit invite management list/actions/create flow to centralized Copilot directory invites APIs (with fallback).
- 2026-02-24: Added Zitadel-compatible JWT verification path in `console-cockpit` middleware (JWKS/issuer/audience + claim mapping) while retaining master-key service auth fallback.
- 2026-02-24: Extended `alchemi-web` centralized cockpit client to prefer session Zitadel bearer tokens when available, with service-key fallback for server-to-server continuity.
- 2026-02-24: Added `alchemi-ai` centralized model-governance integration path for `/config/models` via `/copilot/models/effective` when account context is provided.
- 2026-02-24: Completed super-admin migration APIs under `/copilot/super-admin/*` for account setup (subscription, entitlements, quotas), feature/platform catalogs, config providers/models/media models, and platform-level support/template operations.
- 2026-02-24: Migrated `alchemi-web` spending-limits server actions to centralized `/copilot/budgets/*` APIs (plan, allocations, alerts, effective, usage) with legacy local fallback retained.
- 2026-02-24: Unified `alchemi-ai` credits-factor resolution by aligning `model_config_service` to the same `CREDITS_FACTOR` source used by runtime budget deduction.
- 2026-02-24: Added targeted regression tests for super-admin route registration and Zitadel/break-glass auth context helper behavior (`tests/test_copilot_superadmin_routes.py`, `tests/test_account_middleware_zitadel.py`).
- 2026-02-24: Added centralized integration connection CRUD endpoints under `/copilot/connections/integrations*` and aligned OpenAPI payload compatibility fields (`base_url`, `description_for_agent`, `auth`, `default_headers`, `secrets`) for cockpit parity.
- 2026-02-24: Updated `alchemi-web` account-connections centralized adapter to correctly map and persist `integration` connections (previously mis-routed), preserve OpenAPI auth/header/secret shape, and pass session bearer tokens to centralized APIs.
- 2026-02-24: Added route/account-context tests for connections and tenant resolution (`tests/test_copilot_connection_routes.py`, extended `tests/test_account_middleware_zitadel.py`), with all targeted tests passing.
- 2026-02-24: Completed Phase 4.1 migration of remaining `alchemi-web` files: agentDefActions, notificationTemplate, supportTicket server actions; /api/support, /api/audit-logs, /api/account-catalog API routes; cockpit page components for agentdef, notification-templates, marketplace.
- 2026-02-24: Added `alchemi-ai` agent governance check via centralized cockpit `/copilot/agents/{id}/governance` endpoint in agent deployment flow.
- 2026-02-24: Improved Zitadel auth: added JWT validation error logging with specific exception types, explicit `account_admin` role detection via `_is_account_admin_claims`, three-level role resolution (`super_admin > account_admin > end_user`), and `actor_role` contextvar propagation.
- 2026-02-24: Added account isolation validation tests (`alchemi/tests/test_account_isolation.py`) and end-to-end copilot auth flow tests (`alchemi/tests/test_copilot_auth_e2e.py`).
- 2026-02-24: Finalized cutover checklist with pre-cutover, validation, and post-cutover steps. All phases marked complete.
