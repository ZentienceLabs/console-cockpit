i am trying to build agentic ai control plane (ai gateway) for enterprise as part of alchemi Studio Console. It is a mulittenant saas platform. I want to use litellm as my base code and add an enterprise saas wrapper around it provide enterprise functionalities.


there are 6 projects in this repo aclhemi-bootstrap:
alchemi-ai is the backed for related product called copilot, its like chatgpt for enterprise and enterprise controlled
alchemi-web is the frontend for the copilot.
aibox-api is the backend for the Compute, an compute runtime for agents. aibox-web is the frontend for the Compute. aibox-images is the repo for docker images for the Compute.

You only have to focus on /workspaces/alchemi-bootstrap/console-cockpit which is a fresh clone of litellm. Use this repo as the base code for the Console. We will build our enterprise features on top of this codebase while keeping it modular and maintainable. We will also make sure to comply with the MIT license of litellm while adding our own license for our enterprise features.

* All content that resides under the "enterprise/" directory of litellm, is licensed under the license defined in "enterprise/LICENSE". So don't use any content from that directory without complying with that license.
* Content outside of the above mentioned directories or restrictions above is available under the MIT license.



This is what i want you to build: Alchemi Studio Console, which is the control plane for managing and monitoring the agentic AI infra. The Console will allow enterprise admins and users to manage their account (tenant), teams, users, llms, guardrails, policies, agents and other things related to their agentic AI. The Console will also provide advanced key management, key/team-based guardrails and logging, and advanced logging features for audit logs and maximum retention period on logs. The Console will use open observe for logs and audits. The Console will also have a customized UI that is based on the Console dashboard but with alchemi branding and enterprise features.


this is what i mean by enterprise saas wrapper: 
1. There needs to be different accounts (managed by account-id), each account is a different tenant. Within an account there are orgs, teams and users like how its there in litellm. Basically take the existing litellm code and make it multi-tenant by adding an account or tenant layer on top of the existing org/team/user structure. We need to make sure that all features in litellm are scoped to the account/tenant level so that each tenant can only see and manage their own data and resources. We also need to make sure that the super admin can manage all tenants/accounts but regular users can only manage their own tenant/account.
2. Each account admin will manage their org, teams, users, llms they add, guardrails, policies, agents and other things....
(kind of like their own litellm)
3. The account admin should also be able to allocate budget to orgs, not just teams, and org admin should be able to allocate within their teams and team admins should be able to create virtual keys and add members to their teams.
4. Ensure these features are added as our wrapper on top of litellm under Alchemi folder
Security
✅ SSO for Admin UI
✅ Audit Logs with retention policy
✅ JWT-Auth
✅ Control available public, private routes
✅ Secret Managers - AWS Key Manager, Google Secret Manager, Azure Key, Hashicorp Vault
✅ [BETA] AWS Key Manager v2 - Key Decryption
✅ IP address‑based access control lists
✅ Track Request IP Address
✅ Set Max Request Size / File Size on Requests
✅ Enforce Required Params for LLM Requests (ex. Reject requests missing ["metadata"]["generation_name"])
✅ Key Rotations
Customize Logging, Guardrails, Caching per project
✅ Team Based Logging - Allow each team to use their own Langfuse Project / custom callbacks
✅ Disable Logging for a Team - Switch off all logging for a team/project (GDPR Compliance)
Spend Tracking & Data Exports
✅ Set USD Budgets Spend for Custom Tags
✅ Set Model budgets for Virtual Keys
✅ Exporting LLM Logs to GCS Bucket, Azure Blob Storage
✅ /spend/report API endpoint
Control Guardrails per API Key/Team
Custom Branding
✅ Custom Branding + Routes on Swagger Docs
✅ Custom Email Branding

5. Advanced Key Management (Organizations,
Team/Org Admins, etc.)
6. Key/Team-based Guardrails + Logging
7. Advanced Logging (Audit Logs for Management
Ops, Maximum Retention Period on Logs) . Use open observe for logs and audits. (check env) 
8. We need to use the same ui sections, pages and components as litellm dashboard but customize them to fit our enterprise features and also remove any litellm branding and replace it with alchemi branding. install whatever dependencies are needed for the litellm dashboard to work and make sure it works with our backend.
9. Build all enterprise features missed in the litellm community edition. You can /workspaces/alchemi-bootstrap/console-cockpit/ui/litellm-dashboard/src/components/molecules/notifications_manager.tsx as reference to see what features are enterprise features and missed out to come up with a list of features that we need to build for the Console apart from the ones mentioned above.
10. there are accounts, which are tenants, and each and every account has their own instance of the complete set of litellm features including everything in, i.e they can set all these independently to themselves from other accounts. first of all do we support this? if not we need to , thats the point of this entire exercise. Making every feature truly per-account, do this methodically.
SETTINGS
Settings
Router Settings
Logging & Alerts
Admin Settings
Cost Tracking
UI Theme

DEVELOPER TOOLS
Experimental
Caching
Prompts
API Playground
Tag Management
Claude Code Plugins
Old Usage

ACCESS CONTROL
Internal Users
Teams
Organizations
Access Groups
New
Budgets

AI GATEWAY
Virtual Keys
Playground
Models + Endpoints
Agents
MCP Servers
Guardrails
Policies
Tools
Search Tools
Vector Stores

OBSERVABILITY
Usage
Logs
11. As a super admin who is only there to manage tenants or accounts configuration i.e be able to add or edit or remove teanants (Accounts), be able to add account admins for those accounts by mentioning their mail id. Create a new page called tenant admin and do only this. 

Let the super admin login via `UI_USERNAME` / `UI_PASSWORD` , and when they login they should only see this tenant management page nothing else. Check the users page in litellm for this, we need to add proxy admin but only for that account

12. Hide these by default. And comment them out in the code.

Hide New Feature Indicators
Hide All Prompts
Hide Usage Indicator

13. Comment out "Learning Resources" from the side bar
14. Remove all references to LiteLLM from the UI. 
15. http://localhost:3000/get_image replace the image with alchemi image (copy from /workspaces/alchemi-web/public/assets/alchemi_logo2.png)
16. Each account manages their own llms, agents, guardrails, policies etc. Make sure to scope all these features to the account level and not have any cross-account visibility or management except for the super admin who can see all accounts but not manage their resources (except for account configuration like domains and zitadel org ID). So no config.yaml to be loaded
17. The enterprise folder in console-cockpit is commercially licensed, so make sure to not use any code from that folder without complying with the license defined in enterprise/LICENSE. Remove that folder completely from the codebase but ensure nothing we need is being used from that folder. If so build our own enterprise version in a new folder called Alchemi and make sure to comply with the MIT license of litellm for any code we use from litellm.
18. Remember if each account will set their SSO in page=admin-panel, in that case how will this work? We may need to have a separate login page that we reirect to the right SSO based on the email domain or something. What is the best approach for this, we need to make sure that the login flow is smooth and secure for all accounts.

Remember: some features like tenants and orgs are not part of litellm community, we need to add them. Also when litellm is updated we need to make sure our custom features are not broken. So we need to be careful about how we integrate and customize litellm and we want to be extendable and maintainable. Make the litellm part as modular as possible so that we can easily update it without breaking our custom features. As much as possible make minimal to no changes to the litellm base code and build our enterprise features around it. 

Note: Make not of all the customizations and changes in a document so that we can keep track of them and also for future reference when we need to update litellm or add new features.