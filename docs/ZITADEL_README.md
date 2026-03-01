# Zitadel Guide for Console-Cockpit

This guide is the source of truth for Zitadel onboarding and operations in `console-cockpit`.

It covers:
- exact tenant onboarding steps,
- how a tenant maps to Zitadel objects,
- why `project_id` is required,
- what fields are optional and when,
- one-click onboarding vs advanced controls,
- local dev run commands for Python + Next.js.

## Quick Answer: What is a tenant in this system?

In `console-cockpit`, a tenant is an Alchemi **Account** (`account_id` in DB).

In Zitadel, that tenant is mapped primarily by:
1. token claim `alchemi:account_id` (runtime authorization context), and
2. provisioning target `project_id` (where roles/grants are created).

So:
- Tenant identity in runtime = **claim value** (`alchemi:account_id`).
- Tenant provisioning scope = **Zitadel Project** (required in current implementation).
- Zitadel Organization / IdP are optional layers depending on your identity strategy.

## Architecture Layers (Current Implementation)

## 1) Global runtime auth configuration (server env)
Configured from backend `.env`:
- `ZITADEL_ISSUER_URL` / `ZITADEL_ISSUER`
- `ZITADEL_CLIENT_ID`
- `ZITADEL_CLIENT_SECRET`
- optional `ZITADEL_AUDIENCE`
- optional `ZITADEL_JWKS_URI`
- management auth: `ZITADEL_MGMT_API_TOKEN` or client credentials

This layer is used for token verification and management API access.

## 2) Account-level Zitadel metadata/provisioning defaults
Stored per account in account metadata:
- `enabled`
- `issuer`
- `audience`
- `project_id`
- `organization_id`
- `account_id_claim`
- `product_domains_claim`
- `role_mappings`

This layer is used by provisioning workflows and account-level identity metadata.

Important:
- Runtime token verification currently uses **global** issuer/env settings.
- Account-level issuer is metadata/provisioning context.

## 3) Super-admin onboarding defaults (shared)
Stored globally in `LiteLLM_Config` as:
- `param_name = alchemi_zitadel_onboarding_defaults`

Used to prefill Create Account and One-Click onboarding forms for all super-admin users.

---

## Tenant Mapping Models (Project vs Org vs IdP)

## How Zitadel objects relate (important)

- `Instance`: top-level Zitadel deployment/issuer.
- `Organization`: administrative/customer boundary inside an instance.
- `Project`: where applications and project roles live.
- `Application`: OIDC/SAML client inside a project.
- `IdP`: external login source (Entra/Google/etc), attachable at instance/org level.

In pure Zitadel terms, many teams treat `Organization` as the tenant boundary.
In our current console-cockpit implementation, provisioning and role orchestration are project-centric, so `project_id` is the operational anchor for onboarding.

## Recommended (default)
- **One Zitadel Project per tenant account**
- Optional Zitadel Organization per tenant
- Optional IdP config per tenant domain

Why this is best:
- clean role isolation,
- no role-key collisions,
- simpler audits and troubleshooting.

## Alternative (shared project)
- Multiple tenant accounts use one project
- use role prefix per tenant (`zentience_...`)

This works, but adds operational complexity and role namespace management.

## IdP mapping
An IdP is **not** the tenant itself. It is only login/federation configuration.
Example: `zentience.co` using Microsoft Entra as external IdP.

## Should tenant = new org or new project?

For this implementation, tenant onboarding is optimized around **project-per-tenant**.
You may also create a separate org per tenant for broader identity isolation, but onboarding still needs `project_id` because provisioning APIs write project roles/grants.

Recommended practical pattern:
1. One project per tenant account.
2. Optional one org per tenant (if you need org-level separation in Zitadel admin/federation).
3. Optional tenant-specific IdP if domain-specific federation is required.

## How many projects can be created?

There is no fixed project-count limit hardcoded in console-cockpit.
Actual limits are controlled by your Zitadel deployment/plan/policies.
If you are on Zitadel Cloud, verify limits in your subscription/instance policy or with Zitadel support.

---

## Why `project_id` is required

Current provisioning endpoints create project roles and user grants in Zitadel project APIs.
Those APIs need a target project.

Without `project_id`, bootstrap cannot know where to create:
- `account_admin`
- `console_org_admin`
- `console_team_admin`
- `copilot_org_admin`
- `copilot_team_admin`
- `end_user`

That is why onboarding fails if `project_id` is missing.

## Why other fields are optional

`organization_id`:
- optional because user grants can be project-scoped without org-scoped grant context.

`role_prefix`:
- optional; only needed when sharing a project across multiple tenants.

`user_id_by_email_json`:
- optional; needed only when email lookup cannot resolve users reliably.

`audience`, `issuer` (account-level metadata):
- optional for account provisioning metadata.
- runtime verifier currently reads global env config.

`account_id_claim`, `product_domains_claim` (account-level metadata):
- optional in form because defaults are applied.
- runtime extraction currently uses configured/global claim resolution.

---

## Exact Steps: Onboard a New Tenant (Fastest Path)

Precondition (done once per environment):
1. Zitadel project/app exists.
2. Backend global `ZITADEL_*` env is configured.
3. Management API auth is configured.

Per-tenant onboarding steps:
1. Open `Tenant Admin`.
2. Click `Create Account`.
3. Fill account basics:
- `Account Name`
- `Email Domain`
- initial admin email (recommended)
4. Keep `Enable auto-onboarding` = ON.
5. Fill onboarding fields:
- `Project ID` (required)
- `Organization ID` (optional)
- `Role Key Prefix` (optional)
- `Resolve user IDs from Zitadel email search` (recommended ON)
- optional advanced `User ID by Email JSON`
6. Keep `Save as global defaults` ON if you want reuse for future tenants.
7. Click `Create + Onboard`.
8. Check result summary/warnings.

What happens automatically:
1. account is created,
2. Zitadel account config defaults are saved,
3. bootstrap runs (roles + admin grants),
4. unresolved admins (if any) are reported.

---

## One-Time Setup in Zitadel (Fresh Setup)

1. Create project (recommended one per tenant, or shared if you intentionally choose that model).
2. Create OIDC Web app.
3. Add redirect URI:
- `http://localhost:4000/sso/callback`
4. Add post-logout URI:
- `http://localhost:4000/ui/login`
5. Ensure role claims are included in ID token.
6. Configure token claim enrichment so tokens include:
- `alchemi:account_id`
- `product_domains_allowed` (example: `[
  "console",
  "copilot"
]`)
7. If using O365, add Entra as external IdP and map emails correctly.

---

## Field-by-Field (Create Account Auto-Onboarding)

`Project ID` (required)
- Zitadel project where role/grant provisioning is executed.

`Organization ID` (optional)
- Used only if you need org-scoped user grants.

`Role Key Prefix` (optional)
- Prefix for generated role keys.
- Use when multiple tenants share one project.

`Resolve user IDs from Zitadel email search`
- If ON, backend attempts email -> Zitadel user ID resolution for admin grants.

`User ID by Email JSON` (advanced, optional)
- explicit map used when lookup is unavailable or ambiguous.
- Example:
```json
{
  "admin@zentience.co": "123456789"
}
```

`Save as global defaults`
- Stores defaults in server config for all super-admin users.
- Prefills future Create Account onboarding forms.

---

## Policies & Budget -> Zitadel Tab

Use this when you need per-account edits after creation.

## One-Click Tenant Onboarding
Same orchestration as create-flow onboarding, but executed from account policy drawer.

## Advanced Zitadel Controls
- Account Zitadel Config
- Provision User Grant
- Provision Project Role
- Bootstrap / Sync Workflow

Use advanced mode only for exceptions/troubleshooting.

---

## Role Keys (Canonical)

- `account_admin`
- `console_org_admin`
- `console_team_admin`
- `copilot_org_admin`
- `copilot_team_admin`
- `end_user`

Canonical role mappings JSON:

```json
{
  "account_admin": "account_admin",
  "console_org_admin": "console_org_admin",
  "console_team_admin": "console_team_admin",
  "copilot_org_admin": "copilot_org_admin",
  "copilot_team_admin": "copilot_team_admin",
  "end_user": "end_user"
}
```

---

## Claims Required in Tokens

Minimum required claims for correct authorization context:
- `alchemi:account_id` -> maps identity to tenant account
- `product_domains_allowed` -> controls domain access (`console`, `copilot`)
- roles (in ID token)

Validation endpoint:
- `GET /v1/me/context`

Expected output includes:
- `account_id`
- `roles`
- `product_domains_allowed`

---

## Dev Mode: Python + Node (hot reload loop)

## Backend (Python / proxy API)

From repo root:

```bash
cd /workspaces/console-cockpit
poetry install -E proxy -E extra_proxy --with dev,proxy-dev
poetry run litellm --port 4000
```

Backend runs at `http://localhost:4000`.

## Frontend (Next.js dashboard hot reload)

In a second terminal:

```bash
cd /workspaces/console-cockpit/ui/litellm-dashboard
npm install
npm run dev -- --port 4001
```

Hot-reload UI runs at `http://localhost:4001`.

How they connect:
- Python backend serves APIs on `:4000`.
- Next dev UI calls those APIs (same local environment/cookies).
- For static proxy-served UI (`/ui` on 4000), build UI assets:

```bash
cd /workspaces/console-cockpit
./scripts/deploy.sh build-ui
```

Note: `deploy.sh` is at `scripts/deploy.sh`, not repo root.

---

## Common Issues

`project_id missing in request and account zitadel config`
- Set project ID in auto-onboarding or account Zitadel config.

`Zitadel management client is not configured`
- Configure `ZITADEL_MGMT_API_TOKEN` or client credentials.

Unresolved admins in onboarding summary
- Turn on resolve-by-email or provide explicit `User ID by Email JSON`.

Login works but wrong account/domain in app
- Validate token contains required claims and role data.

---

## API Reference (used by UI)

- `GET /v1/auth/zitadel/status`
- `GET /v1/me/context`
- `GET /v1/super/zitadel/onboarding-defaults`
- `PUT /v1/super/zitadel/onboarding-defaults`
- `GET /v1/accounts/{account_id}/zitadel/config`
- `PUT /v1/accounts/{account_id}/zitadel/config`
- `POST /v1/accounts/{account_id}/zitadel/provision/user-grant`
- `POST /v1/accounts/{account_id}/zitadel/provision/project-role`
- `GET /v1/accounts/{account_id}/zitadel/provision/plan`
- `POST /v1/accounts/{account_id}/zitadel/provision/sync-roles`
- `POST /v1/accounts/{account_id}/zitadel/provision/sync-admin-grants`
- `POST /v1/accounts/{account_id}/zitadel/provision/bootstrap`
