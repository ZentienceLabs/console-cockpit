Take the code bases alchemi-web, alchemi-ai and console-cockpit.

In alchemi-web and alchemi-ai is basically about giving agentic workspaces to enterprise users, in a fashion where the admin can have a centralized control over the users (in in /cockpit/ path in alchemi-web), where they can set who can access what agents (through marketplace), who can use how many credits (budget allocation), and how can use what tools (through marketplace), being able to see audit logs.All this with multi-tenancy in mind, so that different accounts can have their own isolated environments, with their own users, agents, tools, and budgets. There is a also a super admin portal for the platform, where we can manage the accounts (tenants), and have a global view of the usage across all accounts. alchemi-admin is the portal for the super admins to manage the platform, and alchemi-web and alchemi-ai are the portals for the enterprise users to access their agentic workspaces. This has part called /cockpit in the alchemi-web path that helps account admins (Tenant admins) to manage their users, agents, tools, budgets, see audit logs and manage other things.

in console-cockpit we have built on top of litellm with more enterprise features, such as user management, role-based access control, account based multi-tenancy. This is a separate product where enterprise IT admins can give access to development teams vairous LLMS from different providers, agents, guardrails, finops.... This also has a super admin portal for the platform, where we can manage the accounts (tenants), and have a global view of the usage across all accounts.

I think we should have a centralized cockpit and I think we should make the console-cockpit as this centralized cockpit. I think much of the functionality in console-cockpit can be reused in alchemi-web and alchemi-ai for the management layer, such as user management, role-based access control, account based multi-tenancy, audit logs, cost tracking and budget management. And for the rest of the feature. Check the alchemi-web path in /cockpit/ for the current features in alchemi-web and alchemi-ai, and see how we can integrate them into a centralized cockpit that can serve both alchemi-web and alchemi-ai, and potentially other products in the future. 
Instead of having cost management inside alchemi-web and alchemi-ai, we should use the budget tracking features inside console-cockpit, for example we can have a budget allocation feature in the centralized cockpit per user, team and organization, where the admin can set a budget for each user, team or organization and as the use the models through this centralized cockpit, the costs will be tracked against their allocated budget, and the admin can have a clear view of how much budget is being used and how much is left. This way we can have a more consistent and centralized way of managing budgets across all products, and also provide more granular control to the admins over how the budgets are allocated and used.
And some features I think we need to port from alchemi-web and alchemi-ai to the centralized cockpit include:
- Agent management: We can have a centralized agent management system in the cockpit, where admins can create, edit and delete agents, and assign them to specific users or teams. alchemi-web path in /cockpit/marketplace and alchemi-web path in /cockpit/agentdef in alchemi-web.
- Tool management: Similar to agent management, we can have a centralized tool management system in the cockpit, where admins can manage the tools that are available to the users, and assign them to specific users or teams. alchemi-web path in /cockpit/connections  in alchemi-web.
- Basically we need to move all of the management in /cockpit in alchemi-web to the console-cockpit, and make the /cockpit in alchemi-web and alchemi-ai as clients that call the centralized cockpit APIs to manage these features. 
- Guardrails and audit logs


One important think to remember, for alchemi-web and alchemi-ai features we port and also to control them we sould have a separate section called copilot in console-cockpit that manages these, it can reuse backend but needs to have separate, orgs and teams that need to be managed separately from the main console-cockpit orgs and teams, manage budgets, managent marketplace of agents, and tools and even audit logs as they are specific to alchemi-web and alchemi-ai. Also the llms (models) that are used in alchemi-web and alchemi-ai are specific to those products, so we need to have a way to manage them separately in the centralized cockpit. Basically for the AI gateway in  console-cockpit version, enterprises (accounts) bring their own llms, so we need to have a way to manage those llms separately from the ones used in alchemi-web and alchemi-ai, which are more focused on providing agentic workspaces for enterprise users. The llms for copilot (aclhemi-web and alchemi-ai) are centrally managed by super admins meaning there is a central places to enable these llms (check the alchemi-admin), and the enterprises can choose from the available llms in their account admin page, and the mangement of these are tracked as credits (cost * CREDITS_FACTOR) and this is what is tracked in the budget allocation and cost management features in the centralized cockpit for management of copilot. 

Remember there are three important roles here, the super admin who manages the whole platform and has access to all features and data across all accounts, the account admin who manages a specific account (tenant) and has access to the features and data of that account along with budget tracking user management, observability, marketplace for that account, and the end users who have access to the agentic workspaces and can use the agents and tools that are assigned to them by their account admin. We need to make sure that the centralized cockpit has a clear role-based access control system that allows us to define what each role can see and do in the cockpit, and also make sure that the user experience is tailored to each role, so that they can easily find and access the features that are relevant to them. The end users of copilot do not have access to the centralized cockpit, they only have access to the agentic workspaces in alchemi-web and alchemi-ai.

Do a thorough analysis of the current features in alchemi-web, alchemi-ai, alchemi-admin and console-cockpit and see how we can integrate them into the centralized cockpit. We should also consider the user experience and design of the centralized cockpit, to ensure that it is intuitive and easy to use for both admins and users. I think we need not worry about legacy code or migration as this will be a fresh production.

Come up with a detailed plan and roadmap for the development of the centralized cockpit, changes to alchemi-web and alchemi-ai, and the integration between them. This will require diligent attention to detail and careful planning to ensure a smooth transition and successful implementation of the centralized cockpit. 

Its not about just merging codebases, but basically want the alchemi-web and alchemi-ai to be clients of the centralized cockpit, where they can call the APIs of the centralized cockpit to manage users, agents, tools, budgets, and other features. This way we can have a more modular and scalable architecture, where the centralized cockpit can serve multiple products and clients, and we can also have a more consistent and unified experience for the users across all products.

Note: console-cockpit is built on top of litellm, so we need to maintain the modularity as mentioned in the instructions.md file. 

One last thing, alchemi-web uses zitadel for authentication and user management, while console-cockpit has its own user management system using litelle. We need to go with zitadel for the centralized cockpit as well, to have a consistent authentication and user management system across all products. This means we need to integrate zitadel with the centralized cockpit, and also make sure that the user management features in the centralized cockpit are compatible with zitadel.

As a first step come up with a detailed analysis of the current features in alchemi-web, alchemi-ai, alchemi-admin and console-cockpit that needs to be centralized meaning check /cockpit in alchemi-web and alchemi-admin to see how they are currently managed, write it down, and then study how this is done in console-cockpit propose a detailed plan and how this has to be centralized.  Keep the completel management of alchemi-web (copilot) as a separate section in the centralized cockpit. See what from alchemi-admin needs to be ported to super admin portal in console-cockpit. I am not too keen workspace management in /cockpit in alchemi-web, but more on the agent, connections, guardrails, tool, user management and budget management.

Basically lets completely move alchemi-admin and the /cockpit in alchemi-web to the centralized cockpit, and make them as clients that call the centralized cockpit APIs to manage these features. The super admin portal in console-cockpit will have all the features of alchemi-admin, and the account admin portal in console-cockpit will have all. 

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

For Copilot Credits/Budget Methodology

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

Avoid fragmented UX terms. Standardize 

Model Governance Requirements (Copilot vs BYOK)

### 6.1 Separation

- Console Models tab (BYOK): enterprise-supplied endpoints for gateway usage.
- Copilot model governance:
  - Super admin maintains centralized Copilot catalog.
  - Super admin selects account-eligible subset.
  - Account admin selects user-visible subset from that eligible set.
  - End users in `alchemi-web` / `alchemi-ai` see only effective subset.

Data source

- Copilot catalog comes from Copilot config tables/catalog APIs, not runtime gateway router names by default.
- Gateway import may bootstrap catalog, but catalog remains canonical.
 "items": [],
Connections and Tools Requirements

- OpenAPI/MCP configuration UX and payloads must align with `alchemi-web` integrations behavior (`/spaces/<id>?section=integrations`) for practical parity.
- Composio in cockpit is primarily a feature-toggle/enablement governance layer for what end users can access, not forcing per-tenant raw connection setup unless explicitly needed.




