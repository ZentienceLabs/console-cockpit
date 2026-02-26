# Console-Cockpit Migration Audit

**Date:** 2026-02-25
**Scope:** Copilot UI implementation for console-cockpit admin dashboard

---

## What Was Changed

### Phase 1: Role Visibility Fix (P0 Blocker)

| File | Change | Why |
|------|--------|-----|
| `ui/litellm-dashboard/src/utils/roles.ts` | Added "App Owner", "Account Admin" to `all_admin_roles`; added `copilot_admin_roles`, `super_admin_only_roles` exports; updated `rolesAllowedToSeeUsage` and `rolesWithWriteAccess` | `account_admin` JWT role mapped to "Account Admin" which wasn't in any role array, making the sidebar empty |
| `ui/litellm-dashboard/src/app/(dashboard)/hooks/useAuthorized.ts` | Added `case "account_admin": return "Account Admin"` to `formatUserRole` switch | Missing case caused `account_admin` to map to "Unknown Role" |
| `ui/litellm-dashboard/src/app/(dashboard)/components/Sidebar2.tsx` | Added 12 copilot route cases to `routeFor()`, added Copilot submenu group with 12 children, added Tenant Admin menu item, imported copilot role arrays and new icons | No copilot section existed in the sidebar |
| `ui/litellm-dashboard/src/app/(dashboard)/layout.tsx` | Removed super-admin-only TenantAdminPage render; gave super admins the full sidebar layout with `effectiveRole = "proxy_admin"` | Super admins were locked to only seeing TenantAdminPage with no sidebar |

### Phase 2: Copilot API Client + Shared Components

| File | Description |
|------|-------------|
| `ui/litellm-dashboard/src/lib/copilotApi.ts` | Full API client covering all 13 copilot backend routers (directory, budgets, models, agents, marketplace, connections, guardrails, observability, notifications, support, entitlements, global-ops, super-admin) |
| `ui/litellm-dashboard/src/components/copilot/CopilotPageShell.tsx` | Page wrapper with title, subtitle, icon, refresh button, and actions slot |
| `ui/litellm-dashboard/src/components/copilot/CopilotStatsRow.tsx` | Row of stat cards using Ant Design Statistic component |
| `ui/litellm-dashboard/src/components/copilot/CopilotCrudTable.tsx` | Generic CRUD table with search, pagination, edit/delete actions, and Popconfirm |

### Phase 3: 12 Copilot Pages

| Page | Route | Features |
|------|-------|----------|
| Directory | `/copilot/directory` | 5 tabs: Users, Organizations, Teams, Memberships, Invites with full CRUD |
| Credit Budgets | `/copilot/credits` | Stats row, plan summary, 3 tabs: Allocations (CRUD), Usage History, Alert Rules |
| Model Governance | `/copilot/models` | 3 tabs: Catalog (CRUD), Eligibility (multi-select), Selection (multi-select) |
| Agents | `/copilot/agents` | Single CRUD table with name, model, status, tags |
| Marketplace | `/copilot/marketplace` | 2 tabs: Listings (CRUD), Assignments (create/delete) |
| Connections | `/copilot/connections` | 3 tabs: MCP Servers, OpenAPI, Integrations (all CRUD) |
| Guardrails | `/copilot/guardrails` | 2 tabs: Configs (read-only), Patterns (CRUD) |
| Observability | `/copilot/observability` | Stats row + 2 read-only tabs: Audit Logs, Usage Rollups |
| Notifications | `/copilot/notifications` | Single CRUD table for templates |
| Support | `/copilot/support` | CRUD table for tickets with close action |
| Entitlements | `/copilot/entitlements` | 2 tabs: Feature Catalog (CRUD), Account Entitlements (read-only). Super admin only |
| Global Ops | `/copilot/global-ops` | Stats row + 3 bulk operation cards. Super admin only |

### Phase 4: Super Admin Layout

- Super admins now see the full sidebar (all admin items + Copilot section + Tenant Admin)
- "Tenant Admin" added as a sidebar menu item at the bottom, restricted to `super_admin_only_roles`

### Phase 5: Data Seeding

| File | Description |
|------|-------------|
| `scripts/seed_copilot_data.py` | Seeds 15 models to catalog, 10 features to entitlements catalog, 5 marketplace listings |

---

## What's Complete

- [x] Account admin (`account_admin` JWT role) can see the sidebar and copilot section
- [x] App owner (`app_owner` JWT role) can see admin items
- [x] 12 copilot pages built with full CRUD against backend APIs
- [x] Super admin sees full sidebar with all copilot items + Tenant Admin
- [x] Entitlements and Global Ops restricted to super admin only
- [x] API client covers all 13 copilot backend routers
- [x] Seed script for model catalog, feature catalog, and marketplace
- [x] Build succeeds (48 static pages, 0 errors)

## What's Pending / Not Yet Implemented

- [ ] **Real-time data in Credit Budgets**: Usage history and alert rules may be empty until the budget system is wired to the LLM proxy's spend tracking
- [ ] **Marketplace data porting**: Existing marketplace data from alchemi-web needs to be migrated via the seed script or manual import
- [ ] **Directory data**: Directory pages will show data once users/orgs/teams are created via the copilot API (or migrated from existing data)
- [ ] **Credits reflected to copilot user**: The copilot chat UI (alchemi-ai) needs to call `GET /copilot/budgets/effective` to show remaining credits to users
- [ ] **Overflow/pool credits**: The overage_limit and pool credit logic exists in the budget backend but isn't fully surfaced in the Credits UI
- [ ] **Super admin subscription plan management**: The super-admin subscription plan CRUD (`/copilot/super-admin/subscription-plans`) has no dedicated UI yet — currently accessible only via API
- [ ] **Config providers/models management**: Super admin config for providers and models (`/copilot/super-admin/config/providers`, `/copilot/super-admin/config/models`) has no UI yet
- [ ] **Platform catalog and media models**: Backend endpoints exist but no dedicatedUI
- [ ] **Dark mode**: Copilot pages use Ant Design defaults; should inherit from the UI theme settings

## Improvements

1. **Type safety**: The copilotApi.ts uses `any` types — should add TypeScript interfaces matching Pydantic models from the backend
2. **Error boundaries**: Each copilot page should have an error boundary to gracefully handle API failures
3. **Optimistic updates**: CRUD operations currently refetch the full list — could use optimistic updates for better UX
4. **Search debouncing**: CopilotCrudTable search is instant — should debounce for large datasets
5. **Responsive design**: Sidebar + copilot pages could be more responsive at mobile breakpoints
6. **Form validation**: Current forms have minimal validation — should match backend Pydantic model constraints
