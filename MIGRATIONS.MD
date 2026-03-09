# Unified Cockpit and Platform Consolidation Plan

We currently have two major product areas:

## 1. Product Areas

### Copilot

This includes **alchemi-web** and **alchemi-ai**.

Copilot is the end-user-facing agentic workspace where users from different tenants (that is, different company or enterprise accounts) interact with AI agents. These agents may be created by tenant admins, configured with tools, and shared with users. In some cases, users can also create their own agents and connect tools.

### Console

This is primarily represented by the **console-cockpit** repository.

Console is used by developers and technical teams within a company or enterprise. It provides API access to multiple LLM vendors and related platform capabilities such as:

* model access
* guardrails
* MCP
* logs
* usage visibility
* cost visibility
* budget controls

## 2. Admin Surfaces

### alchemi-admin

This is the fourth repository and is used by the **platform super admin** to manage:

* accounts / tenants
* credit allocation
* global policies

At present, **alchemi-admin only covers the Copilot side**. For the Console side, super-admin capabilities are currently embedded directly inside **console-cockpit**.

---

# Current Product and Admin Structure

## 3. Copilot Scope

### alchemi-web

This is the **Copilot UI** and the primary end-user experience.

It currently includes:

* the end-user agentic workspace
* a `/cockpit` section that provides Copilot administration capabilities inside alchemi-web
* agent creation UI
* integrations UI
* other Copilot management pages

### alchemi-ai

This is the **Copilot backend and orchestration layer**.

It is responsible for:

* agent wizard conversation logic
* tool calling and orchestration
* guardrail enforcement, or routing through guardrail services
* APIs used by alchemi-web for agent creation, tool connections, and agent execution

---

# Copilot Roles

## 4. Roles in the Copilot Tenant / Account Context

### Super Admin (platform-level)

Responsible for:

* creating accounts / tenants
* setting `CREDITS_FACTOR`
* allocating account credits
* managing overflow credits

### Account Admin (tenant-level IT admin)

Responsible for managing Copilot administration for their account through the cockpit section currently embedded in alchemi-web. This includes:

* organizations, teams, and users
* agents and access policies
* connections and sharing policies
* guardrail defaults and enforcement
* model access at org / team / user level
* budget / credit allocation and reporting
* audit logs

---

# Copilot Functional Areas

## 5. Copilot Cockpit in alchemi-web

The Copilot cockpit is currently embedded inside alchemi-web and includes the following functional areas.

### Agent management

* `/cockpit/agentdef`
* `/cockpit/marketplace`

### Connections management

* `/cockpit/connections`
* user-side integrations UI (`IntegrationsSection`)
* supports MCP, OpenAPI, and Composio
* supports both OAuth and API key flows

### Guardrails settings

* preset guardrails such as:

  * PII
  * content moderation
  * jailbreak protection
* applied at:

  * agent level
  * user level
  * team level
  * org level

### Audit logs

* `/cockpit/audit-logs/page.tsx`

### Other Copilot cockpit areas to be migrated

These are the current cockpit routes in alchemi-web that will need to be centralized into console-cockpit:

* `/cockpit/agentdef`
* `/cockpit/marketplace`
* `/cockpit/guardrails`
* `/cockpit/audit-logs`
* `/cockpit/account-catalog`
* `/cockpit/connections`
* `/cockpit/workflow`
* `/cockpit/access-policy/account`
* `/cockpit/groups`
* `/cockpit/wallet`
* `/cockpit/budgets`
* `/cockpit/cost-tracking`
* `/cockpit/requests`

---

## 6. Agent Wizard Creation Flow

This flow spans both alchemi-web and alchemi-ai.

### In alchemi-web

* `agent-wizard-conversational.tsx`

### In alchemi-ai

* `agent_wizard_conversation_v2.py`

### Expected outcome

The wizard should produce:

* an agent definition
* tool bindings
* likely model selection
* guardrail selection

---

## 7. Workflow Automation

Copilot also includes workflow automation capabilities for multi-step execution involving multiple agents, tools, and actions in a defined sequence or logical flow.

This includes:

* visual workflow builder (DAG editor)
* workflow execution and monitoring
* RBAC and governance controls for workflow creation and execution
* cost controls and auditability for workflow runs

---

# Consolidation Goal

## 8. Target State

The goal is to **centralize all admin and management features for both Console and Copilot into console-cockpit**.

This means:

* console-cockpit becomes the single unified cockpit for administration and management
* the Copilot `/cockpit` section in alchemi-web will be fully sunset
* all relevant Copilot cockpit sections will be migrated into console-cockpit

The resulting experience should provide a single place for customers to manage both products while preserving the product-specific controls each one requires.

---

# Authentication, Authorization and Access Control Unification

## 9. Current State

* **Copilot** currently uses **Zitadel** for authentication
* **Console** currently uses an **internal access control system**

These need to be unified into a single authentication and access control system managed through cockpit. This will also determine how accounts, roles, and permissions are handled across both products moving forward. 

## 10. Required Work

Investigate both systems and propose the best unification strategy. This may involve:

* migrating one system to the other
* building a new unified authentication, authorization and access control layer that supports both products
* defining a common RBAC / policy model for tenants, admins, users, teams, agents, workflows, and resources

While doing this, review the following codebases for all current access-control usage and update them to use the unified model:

* alchemi-web
* console-cockpit
* alchemi-admin

The goal is to have one consistent authentication, authorization and access-control model across both Console and Copilot.

---

# Guardrails Unification

## 11. Current State

Guardrails exist in both Copilot and Console, but they are not yet unified.

The actual guardrail APIs are in the **alchemi-guardrails** repository. Investigate how both products currently integrate with this repository.

## 12. Required Work

Investigate:

* how guardrails are configured in Copilot
* how guardrails are configured in Console
* how they are enforced in each product
* where policy storage and rule application happen today

Then propose a unification plan.

Current preference is to **unify on the console-cockpit guardrail system**, because it appears more flexible and better able to accommodate the needs of both products.

The end goal is one shared guardrail system for:

* configuration
* enforcement
* policy visibility
* scope inheritance across org / team / user / agent / workflow where relevant

---

# Cost Tracking and Budgeting Unification

## 13. Current State

The two products currently use different cost-management models.

### Copilot model

Copilot uses a **credit-based system**:

* models are centrally managed by the super admin
* only the super admin can define which models Copilot can use
* the super admin sets `CREDITS_FACTOR` to convert credits into actual cost
* the super admin allocates credits to accounts
* account admins can see credits, not actual cost
* account admins can allocate credits to users or teams under their account

### Console model

Console uses a **traditional cost tracking model**:

* account admins can add their own models
* account admins can see actual cost
* account admins can allocate budgets to users or teams
* super admins currently do not manage Console models or budgets

## 14. Required Work

Investigate how cost tracking and budgeting are currently implemented in both products, then propose a plan to unify them into one system.

Current preference is to **unify on the console-cockpit system**, because it is more comprehensive.

However, the new unified design must preserve the necessary differences in visibility and control:

* super admins still need centralized control for Copilot models and credits
* account admins still need appropriate visibility and budget control
* Console’s direct-cost model must continue to work
* Copilot’s credit abstraction must continue to work where needed

The unified system should support both:

* a credit-based abstraction for Copilot
* direct cost tracking and budget management for Console

This will likely require a layered model where:

* actual cost exists at the platform level
* credits remain a tenant-facing abstraction for Copilot
* Console can continue exposing actual cost directly to account admins where appropriate

---

# Phased Execution Plan

## Phase 1: Unify Access Control

Investigate Zitadel and the internal access control system, then define and implement a single access-control approach for both Console and Copilot.

This phase should include:

* identifying all access-control usage in:

  * alchemi-web
  * console-cockpit
  * alchemi-admin
* updating all such places to use the new unified access-control system

## Phase 2: Centralize Copilot Management into console-cockpit

Migrate Copilot cockpit functionality from alchemi-web into console-cockpit.

This includes:

* migrating relevant files and components
* moving Copilot management sections into console-cockpit under cockpit
* updating navigation, routing, and links
* sunsetting `/cockpit` in alchemi-web

## Phase 3: Unify Guardrails

Investigate how guardrails are implemented in both products and define a unified approach.

This may involve:

* migrating one implementation to the other
* or designing a common shared guardrail framework used by both

## Phase 4: Unify Cost Tracking and Budgeting

Investigate both systems and implement a unified approach to:

* cost tracking (for console features)
* credit management (for Copilot features)
* budgeting
* model governance
* visibility and reporting

This unified design must support both super-admin and account-admin needs.

---

# UI / Component Migration Guidance

## 15. Frontend Framework Considerations

* **console-cockpit** uses **Ant Design**
* **alchemi-web** uses **shadcn/ui**

When migrating components from alchemi-web to console-cockpit:

* use both Ant Design and shadcn/ui where necessary to reduce migration complexity
* avoid unnecessary rewrites during migration
* maintain as much design consistency as possible
* preserve a coherent visual language and user experience across the unified cockpit

---

# Database Workstream

## 16. Important Rule for Database Setup

Do **not** rely on existing migration scripts, because they are outdated and contain dead code.

Instead:

* inspect the codebase directly
* identify the database tables actually required by each project
* identify the relationships actually used by the application
* define clean init scripts based on real usage

## 17. Required Database Deliverable

Create an **idempotent init script for each project** that:

* creates the required tables
* creates the required relationships
* can be run multiple times safely
* does not duplicate data
* does not delete existing data
* does not fail if run again

---

# Current Database Setup

## alchemi-ai

```env
POSTGRES_URI="postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com:5432/devaistore?application_name=alchemi-dev-ai"
APP_POSTGRES_URI="postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com:5432/devapp_db?application_name=alchemi-dev-ai-app"
```

## alchemi-web

```env
DB_HOST="alchemi-nonprod-ai.postgres.database.azure.com"
DB_PORT="5432"
DB_USER="postgres"
DB_PASSWORD="dJRC22sVAuyj"
DB_NAME="devapp_db"
DB_SSL="true"
```

## console-cockpit

```env
DATABASE_URL=postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com/devconsolev2_db?application_name=alchemi-console
```

## alchemi-admin

```env
DB_HOST="alchemi-nonprod-ai.postgres.database.azure.com"
DB_PORT="5432"
DB_USER="postgres"
DB_PASSWORD="dJRC22sVAuyj"
DB_NAME="devapp_db"
DB_SSL="true"
POSTGRES_URL="postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com:6432/devapp_db?application_name=alchemi-web"
```

---

# New Database Setup

The new databases below should be used going forward.

Before initializing them:

* completely clear the existing tables in the new databases
* then run the new init scripts
* then migrate only the necessary data

## alchemi-ai

```env
POSTGRES_URI="postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com:5432/devaiv2_db?application_name=alchemi-dev-ai"
APP_POSTGRES_URI="postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com:5432/devappv2_db?application_name=alchemi-dev-ai-app"
```

## alchemi-web

```env
DB_HOST="alchemi-nonprod-ai.postgres.database.azure.com"
DB_PORT="5432"
DB_USER="postgres"
DB_PASSWORD="dJRC22sVAuyj"
DB_NAME="devappv2_db"
DB_SSL="true"
```

## alchemi-admin

```env
DB_HOST="alchemi-nonprod-ai.postgres.database.azure.com"
DB_PORT="5432"
DB_USER="postgres"
DB_PASSWORD="dJRC22sVAuyj"
DB_NAME="devappv2_db"
DB_SSL="true"
POSTGRES_URL="postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com:5432/devappv2_db?application_name=alchemi-admin"
```

## console-cockpit

```env
DATABASE_URL=postgresql://postgres:dJRC22sVAuyj@alchemi-nonprod-ai.postgres.database.azure.com:5432/devconsolev2_db?application_name=alchemi-console
```

---

# Database Migration Requirements

## 18. Migration Approach

After initializing the new databases:

1. update the `.env` files in each project to point to the new databases
2. migrate only the data necessary for application functionality
3. avoid migrating dead, obsolete, or unused data

## 19. Data That May Need Migration

Only migrate data required for the new unified platform, such as:

* accounts
* tenants
* users
* agents
* connections
* guardrails
* audit logs
* models
* budgets
* costs
* any other actively used operational records required by the applications

Do **not** migrate:

* dead data
* obsolete records
* legacy fields not required by the new functionality
* unused tables or stale migration artifacts

## 20. Parallel Execution Requirement

The database setup and migration work should happen **in parallel with the platform consolidation phases**, because schema changes will likely be needed as access control, guardrails, and cost systems are unified.

---

# Final Objective

The final objective is to create a **single unified cockpit experience** for both Console and Copilot, centered in **console-cockpit**, while preserving the necessary role separation and operational controls for:

* super admins
* account admins
* developers
* end users

This unified cockpit should provide:

* centralized administration
* unified access control
* unified guardrails
* unified cost tracking and budgeting
* centralized Copilot management
* cleaner tenant and account operations
* a more consistent experience for customers across both products

Note: 
1. Anywhere you need any details ask me directly, do not make assumptions. The goal is to be as precise as possible in the migration plan and execution.

2. console-cockpit is built on top of litellm, so we need to maintain the modularity 