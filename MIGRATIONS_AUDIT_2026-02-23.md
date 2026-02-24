# Centralized Cockpit Audit (2026-02-23)

## Scope
- Re-audit against `MIGRATIONS.MD` across:
  - `console-cockpit`
  - `alchemi-web`
  - `alchemi-ai`
  - `alchemi-admin`

## 1) Current Delivery Status vs `MIGRATIONS.MD`

### A. Centralized Copilot section in `console-cockpit`
- Status: **Partially complete (high-value core + global ops foundation delivered)**
- Delivered:
  - Copilot backend modules under `/copilot/*`:
    - budgets, agents/groups, marketplace, connections, guardrails, directory, invites, notifications templates, support tickets, model selection, entitlements
  - Copilot UI nav/pages:
    - Overview, Directory, Credit Budgets, Agents & Marketplace, Connections & Tools, Model Visibility, Guardrails, Observability, Notification Templates, Support Tickets
  - Legacy compatibility endpoints under `/alchemi/*` (list endpoints now available).
  - Super-admin account admin tabs include Copilot ops and governance tabs.
  - Global Ops foundations:
    - Backend: `/copilot/ops/global/summary`, `/copilot/ops/global/bulk/tickets`, `/copilot/ops/global/bulk/notification-templates/delete`
    - UI: `copilot-global-ops` page in Copilot nav + tenant-admin tab
  - Tenant-scoped DB layer for `copilot.*` schema.

- Gaps:
  - Full product parity with all legacy alchemi-admin workflows is not complete.
  - Global “all accounts” operations exist, but still need broader parity modules and richer cross-module analytics.
  - Observability is Copilot-scoped but currently focused on budget alerts + guardrails + support activity; not full Copilot log/audit analytics parity.

### B. `alchemi-web` as client of centralized cockpit
- Status: **Partial migration completed**
- Delivered:
  - `src/lib/console_api/client.ts` points to `/copilot/*`.
  - Cockpit pages are already consuming centralized calls for key management modules.
  - Workspace tracking remains separate as requested.

- Gaps:
  - Legacy/local service paths still coexist in codebase; full cutover cleanup still pending.
  - Some flows still depend on local app DB/session assumptions and are not purely console-driven.

### C. `alchemi-ai` as client of centralized cockpit
- Status: **Foundational integration only**
- Delivered:
  - `gen_ui_backend/utils/console_client.py` wired for budgets, guardrails, connections.

- Gaps:
  - Missing broader client coverage for full cockpit parity (agents/marketplace/directory/support/notifications/model governance workflows).

### D. `alchemi-admin` parity into `console-cockpit` super-admin
- Status: **Partial parity**
- Delivered:
  - `tenant-admin` tabs for accounts, billing, models, entitlements, copilot ticket/notification/model/directory ops.

- Gaps:
  - `alchemi-admin` still has many standalone workflows (feature catalog, role/permission matrix, subscription/charge management, deeper account setup/overrides) not fully cut over.

## 2) Data Migration Audit

## Command run
- `python -m alchemi.scripts.migrate_copilot_data` with:
  - source: `alchemi-web` `POSTGRES_URL` (`devapp_db`)
  - target: `console-cockpit` `DATABASE_URL` (`devconsoledb`)

- Result:
  - Migration completed successfully and idempotently.
  - Inserted `0` new rows this run (target already populated / conflicts skipped).

## Source vs target counts snapshot
- Source (`devapp_db`, public):
  - `credit_budget=71`, `budget_plans=20`, `agents_def=15`, `agent_groups=5`, `agent_group_members=11`, `marketplace_items=14`, `account_connections=8`, `guardrails_config=13`, `guardrails_custom_patterns=30`, `guardrails_audit_log=16`, `users=85`, `groups=64`, `teams=68`, `account_memberships=98`, `userinvites=100`, `account_notification_templates=4`, `supporttickets=26`
- Target (`devconsoledb`, copilot):
  - `credit_budget=68`, `budget_plans=20`, `agents_def=15`, `agent_groups=5`, `agent_group_members=11`, `marketplace_items=14`, `account_connections=13`, `guardrails_config=14`, `guardrails_custom_patterns=32`, `guardrails_audit_log=142`, `users=134`, `groups=65`, `teams=69`, `account_memberships=134`, `user_invites=136`, `notification_templates=25`, `support_tickets=27`

## Notes
- Migration script intentionally skipped some source budget rows with `null account_id`.
- Target has additional console-native/copilot-generated records beyond migrated source data.

## 3) Identity/Zitadel/SCIM Audit

- Delivered:
  - `auth_org_id` mapping path exists:
    - account metadata index migration
    - account update/create support
    - tenant-admin create/edit fields for Zitadel Org ID
  - Directory identity mode (`source=identity`) uses:
    - users from `LiteLLM_UserTable`
    - teams from `LiteLLM_TeamTable`
    - orgs from `LiteLLM_OrganizationTable`

- New fix in this pass:
  - When SCIM teams exist but org rows are missing, identity directory now synthesizes an org bucket:
    - `Unassigned (No SCIM Organization)`
  - This prevents empty organization UX for identity mode.

- Remaining data reality gaps:
  - Current DB has very sparse SCIM org rows; many identity users/teams are still limited by upstream sync completeness.
  - Some identity rows have weak account linkage quality (historical data quality issue, not table-drop related).

## 4) Additional Issues Found (not explicit in `MIGRATIONS.MD`)

- `deploy.sh` env loading fragility:
  - Prior logic used `source .env`, which can break on `$` in env values.
  - Fixed by safe, non-interpolating `.env` parser in script.

- Runtime startup process behavior:
  - Proxy startup repeatedly generates/applies baseline diff migrations at boot in this environment, creating migration churn/noise.
  - Needs stabilization policy (disable repeated baseline generation in normal start path).

- `alchemi-web` login/profile deadlock risk:
  - Profile fetch could stall and leave users on loader.
  - Hardened with timeout + recovery signout path in provider.

- Super-admin write-scope hardening gaps:
  - Some update/delete paths were not explicitly account-scoped for super-admin.
  - Fixed backend + UI/hook scoping for support tickets, notification templates, and guardrails patterns.

## 5) Completion Plan (aligned to `MIGRATIONS.MD`)

### Phase 1: Close parity-critical admin ops (short-term)
- Port remaining high-value `alchemi-admin` workflows into `console-cockpit` super-admin:
  - platform/feature catalog governance parity
  - deeper notification operations parity
  - broader ticket bulk workflows and account-scoped ops consistency
- Ensure all Copilot modules support strict account filters + super-admin account selector behavior.

### Phase 2: Global operations parity
- Add explicit “all accounts” aggregation endpoints for Copilot ops:
  - cross-account ticket KPIs, notification KPIs, budget risk rollups, directory health metrics
- Add super-admin bulk actions with audit trails.

### Phase 3: Client cutover and cleanup
- `alchemi-web`:
  - remove residual local management API/service paths once parity confirmed
  - keep workspace pages separate per requirement
- `alchemi-ai`:
  - expand console client integration beyond budget/guardrails/connections to full management coverage needed by product.
- Keep `/alchemi/*` compatibility behind flag during transition, then retire after client cutover validation.

### Phase 4: Hardening and CI gates
- Add Copilot UI regression tests for:
  - role gating
  - tenant isolation
  - identity source behavior (Zitadel/SCIM-backed views)
  - critical create/update/delete flows
- Add CI smoke/E2E for deploy + core Copilot flows on every merge.

## 6) Current Practical Readiness
- Centralized cockpit foundation is working and materially ahead of initial baseline.
- Full end-state from `MIGRATIONS.MD` still requires additional parity phases (especially super-admin deep parity and full client cutover cleanup).

## 7) Latest Validation Snapshot
- Backend E2E:
  - `poetry run pytest tests/test_copilot_e2e.py -q -p no:retry` -> **98 passed**
- UI tests:
  - `npm run test -- src/components/leftnav.test.tsx` -> **7 passed**
- UI build + static export:
  - `./scripts/deploy.sh build-ui` -> **success**
- Live smoke (local `:4000`):
  - `/copilot/ops/global/*` -> **200**
  - `/alchemi/*` compatibility list endpoints -> **200**
  - `/ui/?login=success&page=copilot-global-ops` -> **200**

## 8) Delta Update (2026-02-23 evening pass)

### Closed gaps from current migration review
- Copilot model governance separation:
  - Added dedicated centralized catalog table: `copilot.model_catalog`.
  - Added super-admin catalog APIs:
    - `GET/POST /copilot/models/catalog`
    - `PUT/DELETE /copilot/models/catalog/{id}`
    - `POST /copilot/models/catalog/import/router`
  - Updated account model visibility to validate against this catalog (not direct runtime BYOK list fallback).
- Copilot observability scope expansion:
  - Added `copilot.audit_log` table for Copilot management/usage events.
  - Added observability APIs:
    - `GET /copilot/observability/alerts`
    - `GET /copilot/observability/audit`
    - `GET /copilot/observability/summary`
  - Updated UI observability page to show:
    - Budget alerts
    - Guardrail alerts
    - Copilot audit log feed
    - Support activity
- Connections/tools alignment (Composio semantics):
  - Added centralized integration catalog table: `copilot.integration_catalog`.
  - Added APIs:
    - `GET/POST /copilot/connections/integrations/catalog`
    - `PUT/DELETE /copilot/connections/integrations/catalog/{id}`
    - `GET/PUT /copilot/connections/integrations/enabled`
  - Updated Connections UI integration tab to manage account-level visibility toggles from catalog.
  - MCP/OpenAPI forms retained and aligned with structured payload fields (`secrets`, auth config, MCP mode).
- Added audit emission in high-value flows:
  - model catalog + model selection
  - integration catalog + enabled integrations updates
  - connection CRUD/test
  - budget create/update/delete + usage record
  - marketplace install/assignment updates

### New migration applied
- `prisma/migrations/20260224010000_copilot_catalog_observability/migration.sql`

### Additional validation in this pass
- `poetry run pytest -q tests/test_copilot_e2e.py` -> **101 passed**
- `./scripts/deploy.sh build-ui` -> **success**
- `./scripts/deploy.sh migrate` -> **success**
- API smoke (`localhost:4000`) for new endpoints:
  - `/copilot/models/catalog` -> **200**
  - `/copilot/connections/integrations/catalog` -> **200**
  - `/copilot/connections/integrations/enabled` -> **200**
  - `/copilot/observability/alerts` -> **200**
  - `/copilot/observability/audit` -> **200**
