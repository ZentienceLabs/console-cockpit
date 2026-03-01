# Centralized Cockpit TODO

Last updated: 2026-03-01

## 0) Baseline + DB

- [x] Audit current state across `console-cockpit`, `alchemi-web`, `alchemi-ai`, `alchemi-admin`
- [x] Reset `console-cockpit` DB and apply fresh schema (`public` + `copilot`)
- [x] Reset `alchemi-web` DB and recreate required app tables
- [x] Initialize `alchemi-ai` APP DB required tables (`workspace_api_keys`, `integration_connections`, `agents_def`)
- [x] Add reproducible reset/bootstrap script:
  - [scripts/db/reset_and_bootstrap_all.sh](/workspaces/console-cockpit/scripts/db/reset_and_bootstrap_all.sh)
- [x] Add `alchemi-web` force-sync helper:
  - [scripts/db/force-sync-app-db.mjs](/workspaces/alchemi-web/scripts/db/force-sync-app-db.mjs)
- [x] Validate end-to-end bootstrap run (all steps pass with verification queries)

## 1) Contracts (Source of Truth)

- [x] Freeze centralized API contracts for all Copilot management modules:
  - directory, budgets, agents, marketplace, connections, guardrails, models, observability
- [x] Publish a single schema contract doc for client teams (`alchemi-web`, `alchemi-ai`)
  - Added [docs/copilot_api_contracts.md](/workspaces/console-cockpit/docs/copilot_api_contracts.md)
- [x] Define versioning/deprecation policy for legacy `/alchemi/*` endpoints
  - Added policy section in [docs/copilot_api_contracts.md](/workspaces/console-cockpit/docs/copilot_api_contracts.md)
- [x] Seed Copilot model catalog from provider env lists (Azure OpenAI/Anthropic/xAI, Vertex)
  - Added [scripts/dev/seed_copilot_model_catalog_from_env.py](/workspaces/console-cockpit/scripts/dev/seed_copilot_model_catalog_from_env.py)

## 2) Identity + Tenant Resolution

- [x] Make Zitadel account resolution deterministic for all cockpit and user-runtime calls
  - Login + OIDC now backfill `LiteLLM_UserTable.account_id` for resolved users
- [x] Enforce account context reconciliation (token/account mismatch handling)
  - Added identity-directory reconciliation for unlinked users (`/copilot/users/reconcile-identity`) and auto-run on identity reads
  - Added generic SSO callback backfill + reconciliation and a Directory UI action (`Reconcile Identity Users`)
- [x] Add SCIM data quality checks (org/team mapping completeness)
  - Added `GET /copilot/observability/scim-quality`

## 3) Copilot Policy Model (Missing Pieces)

- [x] Add scoped model-access policy (`account/group/team/user`) for Copilot models
- [x] Add scoped guardrail policy (`account/group/team/user`) + per-agent override
  - Added guardrail scope policy APIs + UI tab in Copilot Guardrails
- [x] Add scoped feature flag policy:
  - create connections
  - create agents
  - image generation
  - model access
- [x] Add connection permission modes:
  - admin-managed use-only
  - self-managed allowed
- [x] Fix scoped policy JSON decoding from `copilot_db` reads
  - `feature_flag_policies.flags` now parsed correctly in entitlements, models, and connections resolution paths
- [x] Standardize default org to explicit `global`
  - New default directory entities are now created as `Global` org/team (is_default=true)

## 4) Credits/Budget Completion

- [ ] Move credits-factor to centralized per-account config (remove env-only dependency)
- [x] Implement monthly renewal job at budget-plan level
  - Added renewal cadence/day + plan cycle apply endpoint (`/copilot/budgets/plans/{id}/renew`)
- [ ] Implement overflow billing ledger and settlement tracking
  - Implemented overflow policy + account-admin billing notice; ledger settlement still pending
- [ ] Add effective allocation API that resolves inheritance and overrides clearly

## 5) Agent/Marketplace + Tools

- [ ] Complete assignment semantics for agents/connections across all scopes
- [ ] Ensure admin-created assets appear consistently in user marketplace discovery
- [ ] Port wizard/integration creation flows from `alchemi-web`/`alchemi-ai` to centralized APIs

## 6) Observability + Cost Analytics

- [ ] Add full cost attribution dimensions:
  - by org/team/user
  - by agent/model/connection/guardrail
- [ ] Expand Copilot observability dashboards to include attribution and anomaly views
- [ ] Normalize audit event taxonomy across modules

## 7) Client Cutover

### `alchemi-web`
- [ ] Replace remaining local cockpit management paths with `console-cockpit` API client calls
- [ ] Keep workspace runtime features local where intended, but enforce centralized policy decisions
- [ ] Remove stale local management services/actions after parity
- [x] Add auth bridge for `alchemi-web` login using `console-cockpit` UI token
  - Added `console-cockpit` NextAuth credentials provider and auto-bridge on `/login`

### `alchemi-ai`
- [ ] Expand centralized client usage beyond budgets/guardrails/connections
- [ ] Enforce centralized model selection in runtime path
- [ ] Enforce centralized assignment/permissions in agent + tool runtime decisions

## 8) Super Admin Consolidation

- [ ] Complete migration of super-admin workflows into `console-cockpit`
- [ ] Keep `alchemi-admin` fully decommissioned (no production dependencies)
- [ ] Finalize account entitlement controls and SSO admin UX in one place

## 9) QA + Hardening

- [ ] Add contract tests for all `/copilot/*` modules
- [x] Add scoped-policy e2e coverage (model policies, feature policies, connection permission modes)
- [ ] Add tenant isolation tests (read/write boundaries)
- [ ] Add end-to-end flows:
  - super admin -> account admin -> end user policy propagation
- [ ] Add runbook smoke checks after DB bootstrap
- [x] Run Copilot e2e regression sweep after scoped-policy rollout
  - Full suite pass: `tests/test_copilot_e2e.py` against `http://127.0.0.1:4001`

## 10) Cutover + Cleanup

- [ ] Enable phased traffic cutover toggles
- [ ] Remove legacy compatibility endpoints after stable window
- [ ] Final cleanup pass for dead code and duplicate management surfaces

## 11) Dev UX Hardening

- [x] Keep localhost login redirects on UI origin for split-port mode (`4000` UI + `4001` backend)
- [x] Add hybrid dev runner (backend dev + UI prod):
  - [scripts/dev/run_backend_dev_ui_prod.sh](/workspaces/console-cockpit/scripts/dev/run_backend_dev_ui_prod.sh)
