# Unified Console-Cockpit Closure Audit

Date: `2026-02-26`

This audit maps the original ask to implemented artifacts and current closure state.

## Copilot + Console Control Plane Requirements

| Requirement | Status | Evidence |
| --- | --- | --- |
| Separate Console and Copilot domains under one cockpit | Done | `alchemi/endpoints/control_plane_v1.py` (`/v1/console/*`, `/v1/copilot/*`), separate tables in `prisma/migrations/20260226113000_control_plane_v1/migration.sql` |
| Copilot org/team/user management | Done | `/v1/copilot/orgs`, `/v1/copilot/teams`, `/v1/copilot/users` in `control_plane_v1.py` |
| Console org/team/user management (separate tree) | Done | `/v1/console/orgs`, `/v1/console/teams`, `/v1/console/users` in `control_plane_v1.py` |
| Default Copilot global org | Done | `_ensure_default_copilot_global_org()` in `control_plane_v1.py` |
| Credits model (`cost * CREDITS_FACTOR`) + account allocation + overflow | Done | `/v1/budgets/account-allocation`, `/v1/budgets/copilot/*` endpoints in `control_plane_v1.py` |
| Equal distribution + overrides + effective allocation view | Done | `/v1/budgets/copilot/distribute/equal`, `/v1/budgets/copilot/overrides`, `/v1/budgets/copilot/effective-allocation` |
| Budget cycles/renewal | Done | `/v1/budgets/copilot/cycles/*` in `control_plane_v1.py` |
| Agent management with tool config + scoped access + mandatory guardrails | Done | `/v1/copilot/agents`, `/v1/copilot/agents/{id}`, `/v1/copilot/agents/{id}/grants`; guardrail validation via `_ensure_guardrail_presets_exist()` |
| Guardrails at org/team/user/agent scope | Done | `/v1/copilot/guardrails/presets`, `/assignments`, `/effective` |
| Connections (OpenAPI/MCP/Composio), grants, secret masking | Done | `/v1/copilot/connections/*` + `_mask_connection_secrets()` + grants endpoint |
| Composio OAuth/API key policy validation | Done | composio validation in `create_copilot_connection()` / `update_copilot_connection()` |
| Feature toggles by scope | Done | `/v1/features/entitlements`, `/v1/features/effective` |
| Model access by scope (Copilot and Console separate) | Done | `/v1/copilot/models/*`, `/v1/console/models/*` |
| Marketplace for admin-created agents/connections with grants/discovery | Done | `/v1/copilot/marketplace*`, grants + discover endpoints |
| Copilot audit visibility | Done | `/v1/audit?domain=copilot|console|all` |
| Cost breakdown by agent/model/connection/guardrail | Done | `/v1/budgets/copilot/cost-breakdown`, `/v1/costs/breakdown` |
| Workspace lifecycle out of scope | Done | No workspace lifecycle added to control-plane scope |

## Client Cutover Requirements

| Requirement | Status | Evidence |
| --- | --- | --- |
| `alchemi-web` uses centralized cockpit APIs for management surfaces | Done | `src/lib/central-cockpit/*`, `src/app/api/central-cockpit/[...path]/route.ts`, centralized cockpit page in `src/app/(private)/(cockpit)/cockpit/centralized-copilot/page.tsx` |
| `alchemi-ai` admin-path centralized (runtime stays local) | Done | `gen_ui_backend/api/config.py` `/config/admin/*` read/write/grants endpoints; `central_cockpit_proxy.py`; runtime APIs unchanged |
| Strict central sync for mirrored connections | Done | `CENTRALIZE_COPILOT_CONNECTIONS_STRICT` handling in `gen_ui_backend/api/config.py` |

## UX/IA Unification Requirements

| Requirement | Status | Evidence |
| --- | --- | --- |
| Unified cockpit navigation with explicit Copilot section | Done | `ui/litellm-dashboard/src/app/(dashboard)/components/Sidebar2.tsx` |
| Page-by-page Copilot IA routes under centralized cockpit | Done | `ui/litellm-dashboard/src/app/(dashboard)/copilot/*` + `copilot-control/page.tsx` |

## Super Admin + Zitadel Requirements

| Requirement | Status | Evidence |
| --- | --- | --- |
| Super admin account controls consolidated in console-cockpit | Done | `/v1/accounts*`, feature-pack, model-policy, SSO/Zitadel endpoints in `control_plane_v1.py` |
| Zitadel token verification + claims context enforcement | Done | `alchemi/auth/zitadel.py`, middleware/context usage in control-plane |
| Zitadel provisioning lifecycle (roles/grants/bootstrap) | Done | `/v1/accounts/{id}/zitadel/provision/*` endpoints in `control_plane_v1.py` |

## Alchemi-Admin Decommission

| Requirement | Status | Evidence |
| --- | --- | --- |
| App-level decommission (redirect UI, API gone) | Done | `alchemi-admin/src/middleware.ts`, `alchemi-admin/src/app/page.tsx` |
| Operational decommission runbook | Done | `alchemi-admin/DECOMMISSION_PRODUCTION.md` (+ ingress/network policy/DNS snippets) |
| Decommission verification script | Done | `alchemi-admin/scripts/decommission/cutover_check.sh` |

## Hardening and Launch Evidence

| Requirement | Status | Evidence |
| --- | --- | --- |
| Security/authz test campaign execution | Done (local campaign) | `scripts/run_hardening_campaign.sh`, `tests/alchemi_security/*`, execution report `docs/HARDENING_EXECUTION_REPORT.md` |
| Type/syntax validation across repos | Done | `pnpm exec tsc --noEmit` (web/admin/console UI), `python -m py_compile` checks |

## Manual External Closure Items

These are operational tasks outside repository code and must be executed in deployment infrastructure:

1. DNS/ingress/public-access cutover to fully retire `alchemi-admin` endpoint in production.
2. External penetration test against deployed staging/prod environment.
3. Production-scale load test using real infra sizing and observed traffic profile.

