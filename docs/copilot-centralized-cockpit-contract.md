# Copilot Centralized Cockpit API Contract (Hard Cut)

Date: 2026-02-24

## Scope Boundary

- Control plane host: `console-cockpit`
- Copilot management namespace: `/copilot/*`
- BYOK Console governance remains separate and unchanged for enterprise-provided gateway endpoints.

## Role Model

- `super_admin`
- `account_admin`
- `end_user` (no direct cockpit access; runtime writes allowed only for usage/guardrail event ingestion with account context)

## Authentication Model

- Primary admin auth for centralized cockpit: Zitadel-issued OIDC JWTs.
- `console-cockpit` validates Zitadel tokens via issuer + JWKS + optional audience.
- Claim mapping resolves:
  - super-admin by configured role keys
  - account scope from configured account-id claims (or explicit `account_id` context when allowed)
- Transitional + service auth is retained:
  - master-key bearer access for service-to-service clients (`alchemi-web`, `alchemi-ai`)
  - break-glass super-admin semantics remain available until full UI auth cutover is complete.

## RBAC Matrix

| Domain | Super Admin | Account Admin | End User |
|---|---|---|---|
| Directory | full | account scoped | no cockpit access |
| Budget/Credits | full + account allocation | account scoped allocations | runtime usage writes only |
| Models (Copilot) | catalog + eligibility | selection + read effective | no cockpit access |
| Agent Definitions + Marketplace | full | account scoped | no cockpit access |
| Connections/Tools | full | account scoped | no cockpit access |
| Guardrails | full | account scoped | runtime event writes only |
| Support + Templates | full | account scoped | no cockpit access |
| Observability | global/account | account scoped | no cockpit access |
| Global Ops | full | no | no |

## Namespaces and Endpoints

- Directory: `/copilot/directory/*`
- Budgets/Credits: `/copilot/budgets/*`
- Copilot Models: `/copilot/models/*`
- Agent Definitions: `/copilot/agents/*`
- Marketplace: `/copilot/marketplace/*`
- Connections/Tools: `/copilot/connections/*`
- Guardrails: `/copilot/guardrails/*`
- Support: `/copilot/support/*`
- Notification Templates: `/copilot/notification-templates/*`
- Observability: `/copilot/observability/*`
- Super-Admin Global Ops: `/copilot/global-ops/*`
- Copilot Entitlements: `/copilot/entitlements/*`
- Super-Admin Migration Surface: `/copilot/super-admin/*`
  - account setup lifecycle: subscription -> entitlements -> quotas
  - feature/platform catalogs
  - config providers/models/media models
  - global support bulk ops + platform notification templates

## Budget/Credits Methodology

- Parent-child allocation model:
  1. super admin sets account-level credits (`/copilot/budgets/plan`, super-only fields)
  2. account starts with unallocated pool
  3. account admin allocates to org/team/user
  4. equal distribution + per-user overrides supported
  5. cycle is set at plan level
  6. effective allocation endpoint resolves user/team/org inheritance
  7. usage credits formula: `credits = cost * CREDITS_FACTOR`

## Model Governance (Copilot vs BYOK)

- BYOK models continue in Console model routes.
- Copilot model governance is separate:
  - super admin maintains Copilot catalog
  - super admin sets per-account eligible subset
  - account admin chooses user-visible subset
  - effective endpoint computes final visible set

## Persistence Notes

- Existing normalized LiteLLM/Alchemi tables are used where available (users/orgs/teams/MCP/spend logs).
- Copilot-specific hard-cut entities use namespaced `LiteLLM_Config` KV records (`copilot:*`) for rapid modular delivery.
- All Copilot management writes append audit entries under `copilot:audit-event:*`.

## Cross-Product Integration Contract

- `alchemi-web` and `alchemi-ai` must consume centralized `/copilot/*` APIs for management writes.
- `/cockpit` in `alchemi-web` becomes API client UI for centralized control plane.
- end-user runtime remains in product services; management source of truth is centralized cockpit.
