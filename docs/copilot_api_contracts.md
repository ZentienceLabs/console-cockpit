# Copilot API Contracts (Centralized Cockpit)

Last updated: 2026-03-01

## Scope
These APIs are the source of truth for Copilot management in `console-cockpit`.
Client apps (`alchemi-web`, `alchemi-ai`) should consume these APIs and not maintain duplicate management logic.

## Core API Groups
- `GET/POST/PUT/PATCH/DELETE /copilot/users`, `/copilot/memberships`, `/copilot/groups`, `/copilot/teams`, `/copilot/invites`
- `GET/POST/PUT/DELETE /copilot/budgets`, `/copilot/budgets/*`, `/copilot/budgets/plans/*`
- `GET/POST/PUT/DELETE /copilot/agents`, `/copilot/agents/groups/*`
- `GET/POST/PUT/DELETE /copilot/marketplace/*`
- `GET/POST/PUT/DELETE /copilot/connections/*`
- `GET/PUT/DELETE /copilot/guardrails/policies`
- `GET/PUT /copilot/guardrails/config`
- `GET/POST/PUT/DELETE /copilot/guardrails/patterns`
- `GET /copilot/guardrails/audit`
- `GET/PUT /copilot/models/selection`
- `GET /copilot/observability/*`

## Product Boundary
- `users`, `teams`, `organizations` in `users/teams/groups` (console access-control) remain separate from Copilot directory objects.
- Copilot-side directory is managed only under `/copilot/*` APIs.

## Auth + Tenant Contract
- UI/API auth token must resolve to exactly one account context unless caller is super admin.
- If account context is missing on legacy UI JWT, backend resolves account from `user_email` domain/admin mapping.
- Super admin calls may pass `account_id` query param for target account operations.

## Versioning + Deprecation Policy
- Backward-compatible changes:
  - additive fields
  - additive endpoints
  - additive enum values (only if clients tolerate unknown values)
- Breaking changes require:
  - new versioned endpoint namespace (e.g. `/copilot/v2/...`) or explicit dual-field compatibility window
  - deprecation notice in release notes + migration note in this doc
  - at least one full release cycle with compatibility shim

## Legacy Compatibility
- Existing `/alchemi/*` compatibility endpoints remain behind `ALCHEMI_ENABLE_LEGACY_COMPAT=true`.
- New feature work must land in `/copilot/*` first.
