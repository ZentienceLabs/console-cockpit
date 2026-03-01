# Control Plane V1 (Implemented Foundation)

This document tracks the initial implementation for the unified Console + Copilot control plane.

## Implemented in this change

- Multi-domain context propagation in middleware:
  - `account_id`
  - `roles`
  - `scopes`
  - `product_domains_allowed`

- New policy layer:
  - `alchemi/policy/control_plane_policy.py`

- New control-plane APIs (`/v1`) in `alchemi/endpoints/control_plane_v1.py`:
  - `GET /v1/me/context`
  - `POST /v1/accounts`
  - `GET /v1/accounts`
  - `GET /v1/accounts/{account_id}`
  - `PATCH /v1/accounts/{account_id}`
  - `POST /v1/accounts/{account_id}/status`
  - `DELETE /v1/accounts/{account_id}` (soft suspend or hard delete with confirmation)
  - `GET /v1/accounts/{account_id}/admins`
  - `POST /v1/accounts/{account_id}/admins`
  - `PATCH /v1/accounts/{account_id}/admins/{email}`
  - `DELETE /v1/accounts/{account_id}/admins/{email}`
  - `POST /v1/accounts/{account_id}/sso`
  - `GET /v1/accounts/{account_id}/sso`
  - `DELETE /v1/accounts/{account_id}/sso`
  - `GET/PUT /v1/accounts/{account_id}/feature-pack`
  - `GET/PUT /v1/accounts/{account_id}/console-model-policy`
  - `GET /v1/auth/zitadel/status`
  - `GET/PUT /v1/accounts/{account_id}/zitadel/config`
  - `POST /v1/accounts/{account_id}/zitadel/provision/user-grant`
  - `POST /v1/accounts/{account_id}/zitadel/provision/project-role`
  - `GET /v1/accounts/{account_id}/zitadel/provision/plan`
  - `POST /v1/accounts/{account_id}/zitadel/provision/sync-roles`
  - `POST /v1/accounts/{account_id}/zitadel/provision/sync-admin-grants`
  - `POST /v1/accounts/{account_id}/zitadel/provision/bootstrap`
  - `GET/POST /v1/copilot/orgs`
  - `GET/POST /v1/copilot/teams`
  - `GET/POST /v1/copilot/users`
  - `GET/POST /v1/console/orgs`
  - `GET/POST /v1/console/teams`
  - `GET/POST /v1/console/users`
  - `POST /v1/budgets/account-allocation`
  - `GET /v1/budgets/account-allocation`
  - `GET /v1/budgets/copilot/account-allocation`
  - `POST /v1/budgets/copilot/plans`
  - `GET /v1/budgets/copilot/plans/active`
  - `PATCH /v1/budgets/copilot/plans/{plan_id}`
  - `POST /v1/budgets/copilot/allocations/upsert`
  - `DELETE /v1/budgets/copilot/allocations`
  - `POST /v1/budgets/copilot/distribute/equal`
  - `POST /v1/budgets/copilot/overrides`
  - `GET /v1/budgets/copilot/effective-allocation`
  - `GET /v1/budgets/copilot/usage-by-scope`
  - `GET /v1/budgets/copilot/alerts`
  - `GET /v1/budgets/copilot/cost-breakdown`
  - `GET/POST /v1/copilot/agents`
  - `GET/PUT/DELETE /v1/copilot/agents/{agent_id}`
  - `GET/POST/DELETE /v1/copilot/agents/{agent_id}/grants`
  - `GET /v1/copilot/connections`
  - `POST /v1/copilot/connections/{connection_type}`
  - `GET/PATCH/DELETE /v1/copilot/connections/{connection_id}`
  - `POST /v1/copilot/connections/{connection_id}/grants`
  - `GET/POST /v1/copilot/guardrails/presets`
  - `GET/POST /v1/copilot/guardrails/assignments`
  - `GET/POST /v1/copilot/guardrails/patterns`
  - `GET/PUT/DELETE /v1/copilot/guardrails/patterns/{pattern_id}`
  - `GET /v1/copilot/guardrails/effective`
  - `GET/POST /v1/copilot/models/grants`
  - `GET /v1/copilot/models/effective`
  - `GET/POST /v1/console/models/grants`
  - `GET /v1/console/models/effective`
  - `GET/POST /v1/features/entitlements`
  - `GET /v1/features/effective`
  - `GET/POST /v1/copilot/marketplace`
  - `GET /v1/copilot/marketplace/discover`
  - `POST/GET/DELETE /v1/copilot/marketplace/{marketplace_id}/grants`
  - `GET/PATCH/DELETE /v1/copilot/marketplace/{marketplace_id}`
  - `POST /v1/copilot/marketplace/{marketplace_id}/publish`
  - `GET /v1/audit`
  - `GET /v1/costs/breakdown`

- Proxy integration:
  - `litellm/proxy/proxy_server.py` includes `alchemi_control_plane_v1_router`.

- Default Copilot global org bootstrap on account creation.

- New control-plane schema migration:
  - `prisma/migrations/20260226113000_control_plane_v1/migration.sql`

## Notes

- This is a foundation slice. It establishes contracts and storage for the full roadmap.
- Existing LiteLLM features remain active; this layer is additive.
- The full `deploy.sh migrate` path may fail on DBs with pre-existing baseline objects. In that case, apply only the control-plane migration SQL directly.
- Secret handling contract for Copilot connections is enforced in API responses (`secret_json` is always masked for read/write responses).
- Scope validation is strict on writes (account/domain/scope ownership checks).
- Copilot agent create/update enforces mandatory guardrails:
  - `guardrail_preset_ids` must include at least one preset.
  - Presets are materialized as agent-scoped rows in `Alchemi_CopilotGuardrailAssignmentTable`.
- Copilot agent grants are now first-class:
  - create-time grants on `POST /v1/copilot/agents`,
  - mutable grants on `PUT /v1/copilot/agents/{agent_id}` with `grants`,
  - incremental grant CRUD on `/v1/copilot/agents/{agent_id}/grants`.
- Copilot marketplace now supports scope-based visibility grants (org/team/user) and discovery filtering through `/v1/copilot/marketplace/discover`.
- Copilot marketplace supports featured/verified flags, install counters, rating fields, and metadata updates via `PATCH /v1/copilot/marketplace/{marketplace_id}`.
- Zitadel token verification supports:
  - `ZITADEL_ISSUER_URL` / `ZITADEL_ISSUER`
  - `ZITADEL_AUDIENCE` (optional)
  - `ZITADEL_JWKS_URI` (optional override)
  - claims-based context extraction (`account_id`, roles/scopes/domains)
- Zitadel management provisioning supports:
  - direct bearer token via `ZITADEL_MGMT_API_TOKEN`, or
  - OAuth client-credentials via `ZITADEL_CLIENT_ID` + `ZITADEL_CLIENT_SECRET`.
- Zitadel lifecycle automation supports:
  - one-shot bootstrap (default role mappings + project-role sync + account-admin grant sync),
  - dry-run mode for change planning,
  - optional user-id resolution by email via Zitadel management search API.
