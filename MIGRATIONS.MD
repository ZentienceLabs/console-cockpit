# Centralized Cockpit Migration Plan (Fresh Start)

Last updated: 2026-02-24  
Primary platform target: `console-cockpit` (LiteLLM + Alchemi extensions)  
Client products: `alchemi-web`, `alchemi-ai`  
Reference context: migration implementation + audit learnings through 2026-02-24

---

## 1) Objective

Build a single centralized management plane in `console-cockpit` for all Copilot admin workflows currently spread across:
- `alchemi-web` `/cockpit/*`
- `alchemi-admin`

Keep Copilot management isolated under a dedicated `Copilot` section in console-cockpit, while preserving existing LiteLLM/BYOK console behavior for non-Copilot workloads.

---

## 2) Product and Role Model

### 2.1 Product boundaries

- `console-cockpit`:
  - Source of truth for management APIs and admin UI.
  - Hosts two distinct management domains:
    - Console domain (enterprise-managed model endpoints).
    - Copilot domain (centrally governed models, budgets, agents, connections, guardrails, directory, observability).
- `alchemi-web` and `alchemi-ai`:
  - Client applications for end users.
  - Must consume centralized cockpit APIs for management-derived decisions (model allowlist, agent visibility, budget enforcement, guardrails behavior, connection availability).

### 2.2 Roles

- Super Admin:
  - Global across all accounts.
  - Controls platform-level model catalog/governance, account entitlements, global operations dashboards.
- Account/Tenant Admin:
  - Scoped to one account.
  - Manages users/teams/orgs, budgets/allocations, marketplace assignments, connections/integrations, guardrails.
- End User:
  - Uses `alchemi-web` / `alchemi-ai` only.
  - Does not need cockpit UI access.
  - Must be constrained by account admin selections and super-admin guardrails.

---

## 3) Target Architecture (Non-Negotiable)

### 3.1 Identity and auth

- Canonical identity provider: Zitadel.
- Console must accept:
  - LiteLLM JWT / master-key auth for service/admin operations.
  - Zitadel identity tokens for user-scoped Copilot endpoints.
- Mandatory account resolution precedence:
  1. Resolve by Zitadel org mapping (`auth_org_id`) and/or domain/email account resolution.
  2. Use resolved account for Copilot APIs.
  3. Do not trust stale local app membership account IDs from client session blindly.

### 3.2 Data domains

- Copilot data lives in `copilot.*` schema (separate from Prisma core tables).
- BYOK / gateway runtime remains in LiteLLM core tables.
- Copilot model governance must use dedicated Copilot catalog (not gateway router/BYOK list).

### 3.3 API ownership

- Management source of truth: `/copilot/*`.
- Temporary backward compatibility: `/alchemi/*` wrappers behind feature flag.
- Long-term: clients call only `/copilot/*`.

---

## 4) Scope to Migrate (Fresh Start Baseline)

Must migrate and centralize:
- Directory: users, memberships, teams, groups/orgs, invites.
- Budgets/Credits: plans, allocations, hierarchy, alerts, usage recording.
- Models: super-admin catalog + account-level selection.
- Agents + Marketplace: definitions, publication, assignment/install semantics.
- Connections/Tools: OpenAPI/MCP configuration, integration catalog enablement.
- Guardrails: config, custom patterns, audit trail.
- Support tickets and notification templates (high-value admin ops).
- Copilot observability: budget alerts + guardrail alerts + copilot audit logs + usage rollups.
- Super-admin global operations: cross-account summaries + bulk actions.

Out of scope for initial hard cut:
- Workspace tracking page parity from `alchemi-web` cockpit.

---

## 5) Copilot Credits/Budget Methodology (Required Design)

Use a parent-child allocation model:

1. Super admin allocates account-level credits.
2. At account start, credits remain **Unallocated**.
3. Account admin allocates from Unallocated to:
   - organizations/groups
   - teams
   - users
4. Support equal distribution + per-user override.
5. Periodic renewal/cycle logic at budget plan level.
6. Effective allocation view must show inheritance and override resolution.
7. Credit accounting formula is tied to Copilot model cost policy (`cost * CREDITS_FACTOR`).

Avoid fragmented UX terms. Standardize into:
- Budget Plans
- Credit Pools (Unallocated + Scoped allocations)
- User Overrides
- Effective Allocation

---

## 6) Model Governance Requirements (Copilot vs BYOK)

### 6.1 Separation

- Core console Models tab (BYOK): enterprise-supplied endpoints for gateway usage.
- Copilot model governance:
  - Super admin maintains centralized Copilot catalog.
  - Super admin selects account-eligible subset.
  - Account admin selects user-visible subset from that eligible set.
  - End users in `alchemi-web` / `alchemi-ai` see only effective subset.

### 6.2 Data source

- Copilot catalog comes from Copilot config tables/catalog APIs, not runtime gateway router names by default.
- Gateway import may bootstrap catalog, but catalog remains canonical.

---

## 7) Agent/Marketplace Assignment Semantics (Required)

- Assignment scopes must support:
  - account
  - organization/group
  - team
  - user (id or email)
- End-user agent visibility is strict assignment-filtered where required by product UX.
- “Install” semantics must be clear:
  - install as account availability vs user/team/org assignment are separate actions.
- Tenant admin should be able to target all users in account or selected orgs/teams/users.

---

## 8) Connections and Tools Requirements

- OpenAPI/MCP configuration UX and payloads must align with `alchemi-web` integrations behavior (`/spaces/<id>?section=integrations`) for practical parity.
- Composio in cockpit is primarily a feature-toggle/enablement governance layer for what end users can access, not forcing per-tenant raw connection setup unless explicitly needed.

---

## 9) Migration Execution Plan (Start Fresh)

## Phase 0: Foundations and Freeze
- Finalize target API/data contracts for all modules.
- Define canonical account/user identity mapping rules.
- Inventory all legacy endpoints and UI dependencies.
- Add feature flags for dual-read/dual-write and compatibility endpoints.

Exit criteria:
- Signed interface contract for `/copilot/*`.
- Explicit deprecation map for `/alchemi/*`.

## Phase 1: Identity and Tenant Resolution First
- Complete Zitadel integration in console.
- Ensure account resolution endpoint always returns account where resolvable.
- Implement first-login membership reconciliation:
  - user exists in IdP but missing local app membership should be auto-created/reconciled.

Exit criteria:
- No login dead-ends for valid SSO users.
- No stale-account-induced 403/404 in Copilot APIs.

## Phase 2: Data Schema and Migration
- Create/validate `copilot.*` schema and indexes.
- Run idempotent migration scripts from source DBs.
- Never drop shared production tables.
- Track source-to-target row counts and anomaly report.

Exit criteria:
- Migration repeatable and safe.
- Count variance documented with reasons.

## Phase 3: Core Copilot Modules
- Budget hierarchy and allocation workflow.
- Directory from identity source (Zitadel + SCIM teams/orgs).
- Agents/marketplace assignment model.
- Connections/tools catalog + enablement.
- Guardrails + audit storage.

Exit criteria:
- Tenant admin can complete all critical workflows end-to-end.

## Phase 4: Client Cutover (`alchemi-web`, `alchemi-ai`)
- Replace local cockpit management calls with console client adapters.
- Enforce model allowlist and marketplace visibility in user runtime paths.
- Keep workspace tracking separate (as agreed).

Exit criteria:
- User runtime (`/spaces`, new conversation, thread page) reflects selected models/agents.

## Phase 5: Super Admin Parity
- Port high-value `alchemi-admin` workflows:
  - global ticket operations
  - notification operations
  - platform catalog/model governance
- Add account-scoped filters across all modules.

Exit criteria:
- Super admin can operate all targeted Copilot governance from console.

## Phase 6: Global Operations
- Add explicit all-account aggregation APIs and dashboards.
- Add safe bulk actions with audit trails and guardrails.

Exit criteria:
- Cross-account operational visibility and action parity achieved.

## Phase 7: Cutover and Retirement
- Remove residual legacy client calls.
- Keep compatibility routes behind flag for rollback window.
- Retire compatibility routes after stable period.

Exit criteria:
- No production dependency on legacy cockpit APIs.

## Phase 8: Hardening
- UI regression tests for Copilot pages.
- Role-gating and tenant-isolation tests.
- Deploy smoke + E2E in CI per merge.

Exit criteria:
- CI gate blocks merges on Copilot regressions.

---

## 10) Acceptance Criteria (Definition of Done)

- Auth/account mapping:
  - No “invalid token” for valid Zitadel sessions on Copilot read APIs.
  - No account mismatch between client session and resolved console account.
- Models:
  - Super-admin selection -> account admin selection -> end-user visible models works deterministically.
- Marketplace:
  - Tenant-admin assignment to user/team/group/account is reflected in end-user agent lists.
- Budgets:
  - Account credits, unallocated pool, scoped allocations, user overrides, and effective views are consistent.
- Observability:
  - Copilot-only alerts and audit logs are queryable and visible in Copilot observability UI.
- Directory:
  - Users from Zitadel and groups/teams from SCIM/identity source are visible and actionable.
- No critical legacy dependency in `alchemi-web`/`alchemi-ai` management paths.

---

## 11) Operational Runbook

### 11.1 Required env vars
- `DATABASE_URL` (console-cockpit target DB)
- `ALCHEMI_WEB_DATABASE_URL` (source DB for migration/backfill)
- Zitadel vars (`ZITADEL_*`, `NEXT_PUBLIC_ZITADEL_*` where applicable)

### 11.2 Migration command
- `python -m alchemi.scripts.migrate_copilot_data`

### 11.3 Deployment
- `./scripts/deploy.sh migrate`
- `./scripts/deploy.sh build-ui`
- `./scripts/deploy.sh start`

### 11.4 Validation checklist
- Account resolution API returns account_id for known emails.
- `/copilot/models/selection` returns 200 for resolved account.
- Marketplace strict assignment queries return expected agents for test users.
- Budget summary/effective allocation APIs align with expected hierarchy.

---

## 12) Learnings From This Migration (Do This)

- Resolve account by email/org via console APIs at runtime; treat client-stored account as hint only.
- Keep Copilot model catalog separate from BYOK models from day one.
- Implement identity-source directory adapters early (users/teams/orgs).
- Enforce explicit assignment semantics for marketplace and test with real users.
- Build observability and audit trails as first-class features, not afterthoughts.
- Keep migration scripts idempotent and count-verified.
- Add compatibility endpoints only with clear expiry plan and feature flags.
- Validate with real cross-product flows (`console -> alchemi-web/alchemi-ai`) every sprint.

---

## 13) What To Avoid

- Do not mix Copilot and BYOK model governance concepts in one table/UX.
- Do not rely only on local `session.accountId` in clients.
- Do not require manual scope IDs in UI where searchable selectors are required.
- Do not expose installation as the only marketplace action when assignment is the real control plane.
- Do not hide failures behind silent fallbacks that make wrong data look “fine”.
- Do not auto-generate/apply schema diffs on every startup in shared environments.
- Do not perform destructive DB operations in shared databases.
- Do not ship without tenant-isolation and role-gating regression tests.

---

## 14) Remaining Strategic Work After Current Foundation

- Full product-level parity for every legacy `alchemi-admin` workflow.
- Deeper global operations analytics and bulk tooling coverage.
- Complete cutover retirement of all compatibility routes.
- CI-enforced E2E and regression suites for Copilot governance and runtime reflection.
