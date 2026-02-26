/**
 * Copilot API client — wraps fetch calls to /copilot/* backend endpoints.
 *
 * Follows the same patterns as networking.tsx:
 *   - Uses getProxyBaseUrl() for base URL
 *   - Uses globalLitellmHeaderName for auth header
 *   - Bearer token auth via accessToken
 */
import { getProxyBaseUrl, getGlobalLitellmHeaderName } from "@/components/networking";

// ---------------------------------------------------------------------------
// Generic helpers
// ---------------------------------------------------------------------------

interface CopilotFetchOptions extends Omit<RequestInit, "headers"> {
  params?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const base = getProxyBaseUrl();
  const url = new URL(`${base}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) url.searchParams.set(k, String(v));
    });
  }
  return url.toString();
}

async function copilotFetch<T = unknown>(
  path: string,
  accessToken: string,
  options: CopilotFetchOptions = {},
): Promise<T> {
  const { params, ...fetchOpts } = options;
  const url = buildUrl(path, params);

  const res = await fetch(url, {
    ...fetchOpts,
    headers: {
      [getGlobalLitellmHeaderName()]: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err?.detail ?? err?.message ?? `Request failed: ${res.status}`);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Convenience wrappers
function get<T>(path: string, token: string, params?: Record<string, string | number | boolean | undefined>) {
  return copilotFetch<T>(path, token, { method: "GET", params });
}
function post<T>(path: string, token: string, body?: unknown) {
  return copilotFetch<T>(path, token, { method: "POST", body: body ? JSON.stringify(body) : undefined });
}
function put<T>(path: string, token: string, body?: unknown) {
  return copilotFetch<T>(path, token, { method: "PUT", body: body ? JSON.stringify(body) : undefined });
}
function del<T = void>(path: string, token: string, params?: Record<string, string | number | boolean | undefined>) {
  return copilotFetch<T>(path, token, { method: "DELETE", params });
}

// ---------------------------------------------------------------------------
// Directory
// ---------------------------------------------------------------------------
export const directoryApi = {
  listUsers: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/directory/users", t, params),
  createUser: (t: string, body: any) => post("/copilot/directory/users", t, body),
  getUser: (t: string, userId: string) => get(`/copilot/directory/users/${userId}`, t),
  updateUser: (t: string, userId: string, body: any) => put(`/copilot/directory/users/${userId}`, t, body),
  deleteUser: (t: string, userId: string) => del(`/copilot/directory/users/${userId}`, t),

  listOrganizations: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/directory/organizations", t, params),
  createOrganization: (t: string, body: any) => post("/copilot/directory/organizations", t, body),
  getOrganization: (t: string, orgId: string) => get(`/copilot/directory/organizations/${orgId}`, t),
  updateOrganization: (t: string, orgId: string, body: any) => put(`/copilot/directory/organizations/${orgId}`, t, body),
  deleteOrganization: (t: string, orgId: string) => del(`/copilot/directory/organizations/${orgId}`, t),

  listTeams: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/directory/teams", t, params),
  createTeam: (t: string, body: any) => post("/copilot/directory/teams", t, body),
  getTeam: (t: string, teamId: string) => get(`/copilot/directory/teams/${teamId}`, t),
  updateTeam: (t: string, teamId: string, body: any) => put(`/copilot/directory/teams/${teamId}`, t, body),
  deleteTeam: (t: string, teamId: string) => del(`/copilot/directory/teams/${teamId}`, t),

  listTeamMembers: (t: string, teamId: string) => get<any[]>(`/copilot/directory/teams/${teamId}/members`, t),
  addTeamMember: (t: string, teamId: string, body: any) => post(`/copilot/directory/teams/${teamId}/members`, t, body),
  removeTeamMember: (t: string, teamId: string, params: Record<string, string>) => del(`/copilot/directory/teams/${teamId}/members`, t, params),

  listAccountMemberships: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/directory/memberships/account", t, params),
  upsertAccountMembership: (t: string, body: any) => post("/copilot/directory/memberships/account", t, body),
  deleteAccountMembership: (t: string, params: Record<string, string>) => del("/copilot/directory/memberships/account", t, params),

  listOrgMemberships: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/directory/memberships/organization", t, params),
  upsertOrgMembership: (t: string, body: any) => post("/copilot/directory/memberships/organization", t, body),
  deleteOrgMembership: (t: string, params: Record<string, string>) => del("/copilot/directory/memberships/organization", t, params),

  listTeamMemberships: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/directory/memberships/team", t, params),
  upsertTeamMembership: (t: string, body: any) => post("/copilot/directory/memberships/team", t, body),
  deleteTeamMembership: (t: string, params: Record<string, string>) => del("/copilot/directory/memberships/team", t, params),

  listInvites: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/directory/invites", t, params),
  createInvite: (t: string, body: any) => post("/copilot/directory/invites", t, body),
  getInvite: (t: string, inviteId: string) => get(`/copilot/directory/invites/${inviteId}`, t),
  updateInvite: (t: string, inviteId: string, body: any) => put(`/copilot/directory/invites/${inviteId}`, t, body),
  deleteInvite: (t: string, inviteId: string) => del(`/copilot/directory/invites/${inviteId}`, t),
};

// ---------------------------------------------------------------------------
// Budgets / Credits
// ---------------------------------------------------------------------------
export const budgetApi = {
  getPlan: (t: string) => get("/copilot/budgets/plan", t),
  upsertPlan: (t: string, body: any) => put("/copilot/budgets/plan", t, body),
  listAllocations: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/budgets/allocations", t, params),
  upsertAllocation: (t: string, body: any) => put("/copilot/budgets/allocations", t, body),
  deleteAllocation: (t: string, allocationId: string) => del(`/copilot/budgets/allocations/${allocationId}`, t),
  distribute: (t: string, body: any) => post("/copilot/budgets/allocations/distribute", t, body),
  getEffective: (t: string, params: Record<string, string>) => get("/copilot/budgets/effective", t, params),
  recordUsage: (t: string, body: any) => post("/copilot/budgets/usage", t, body),
  listUsage: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/budgets/usage", t, params),
  upsertAlertRule: (t: string, body: any) => post("/copilot/budgets/alerts/rules", t, body),
  listAlerts: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/budgets/alerts", t, params),
  allocateAccountCredits: (t: string, body: any) => post("/copilot/budgets/allocate-account-credits", t, body),
};

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------
export const modelApi = {
  listCatalog: (t: string) => get<any[]>("/copilot/models/catalog", t),
  upsertCatalog: (t: string, body: any) => post("/copilot/models/catalog", t, body),
  deleteCatalog: (t: string, modelCode: string) => del(`/copilot/models/catalog/${modelCode}`, t),
  getEligibility: (t: string) => get("/copilot/models/eligibility", t),
  setEligibility: (t: string, body: any) => put("/copilot/models/eligibility", t, body),
  getSelection: (t: string) => get("/copilot/models/selection", t),
  setSelection: (t: string, body: any) => put("/copilot/models/selection", t, body),
  getEffective: (t: string, params?: Record<string, string>) => get("/copilot/models/effective", t, params),
};

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------
export const agentApi = {
  list: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/agents", t, params),
  create: (t: string, body: any) => post("/copilot/agents", t, body),
  get: (t: string, agentId: string) => get(`/copilot/agents/${agentId}`, t),
  update: (t: string, agentId: string, body: any) => put(`/copilot/agents/${agentId}`, t, body),
  delete: (t: string, agentId: string) => del(`/copilot/agents/${agentId}`, t),
};

// ---------------------------------------------------------------------------
// Marketplace
// ---------------------------------------------------------------------------
export const marketplaceApi = {
  listListings: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/marketplace/listings", t, params),
  createListing: (t: string, body: any) => post("/copilot/marketplace/listings", t, body),
  updateListing: (t: string, listingId: string, body: any) => put(`/copilot/marketplace/listings/${listingId}`, t, body),
  deleteListing: (t: string, listingId: string) => del(`/copilot/marketplace/listings/${listingId}`, t),
  publishListing: (t: string, listingId: string) => post(`/copilot/marketplace/listings/${listingId}/publish`, t),
  hideListing: (t: string, listingId: string) => post(`/copilot/marketplace/listings/${listingId}/hide`, t),
  listAssignments: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/marketplace/assignments", t, params),
  createAssignment: (t: string, body: any) => post("/copilot/marketplace/assignments", t, body),
  deleteAssignment: (t: string, assignmentId: string) => del(`/copilot/marketplace/assignments/${assignmentId}`, t),
  getEffective: (t: string, params?: Record<string, string>) => get("/copilot/marketplace/effective", t, params),
};

// ---------------------------------------------------------------------------
// Connections
// ---------------------------------------------------------------------------
export const connectionApi = {
  listMcp: (t: string) => get<any[]>("/copilot/connections/mcp", t),
  createMcp: (t: string, body: any) => post("/copilot/connections/mcp", t, body),
  updateMcp: (t: string, serverId: string, body: any) => put(`/copilot/connections/mcp/${serverId}`, t, body),
  deleteMcp: (t: string, serverId: string) => del(`/copilot/connections/mcp/${serverId}`, t),

  listOpenapi: (t: string) => get<any[]>("/copilot/connections/openapi", t),
  createOpenapi: (t: string, body: any) => post("/copilot/connections/openapi", t, body),
  updateOpenapi: (t: string, connId: string, body: any) => put(`/copilot/connections/openapi/${connId}`, t, body),
  deleteOpenapi: (t: string, connId: string) => del(`/copilot/connections/openapi/${connId}`, t),

  listEnablements: (t: string) => get<any[]>("/copilot/connections/enablements", t),
  upsertEnablement: (t: string, body: any) => put("/copilot/connections/enablements", t, body),
  deleteEnablement: (t: string, enablementId: string) => del(`/copilot/connections/enablements/${enablementId}`, t),

  listIntegrationCatalog: (t: string) => get<any[]>("/copilot/connections/integration-catalog", t),
  upsertIntegrationCatalog: (t: string, integrationId: string, body: any) => put(`/copilot/connections/integration-catalog/${integrationId}`, t, body),
  listIntegrations: (t: string) => get<any[]>("/copilot/connections/integrations", t),
  createIntegration: (t: string, body: any) => post("/copilot/connections/integrations", t, body),
  updateIntegration: (t: string, integrationId: string, body: any) => put(`/copilot/connections/integrations/${integrationId}`, t, body),
  deleteIntegration: (t: string, integrationId: string) => del(`/copilot/connections/integrations/${integrationId}`, t),
};

// ---------------------------------------------------------------------------
// Guardrails
// ---------------------------------------------------------------------------
export const guardrailApi = {
  listConfigs: (t: string) => get<any[]>("/copilot/guardrails/configs", t),
  getConfig: (t: string, guardType?: string) => get(guardType ? `/copilot/guardrails/config/${guardType}` : "/copilot/guardrails/config", t),
  upsertConfig: (t: string, body: any, guardType?: string) => put(guardType ? `/copilot/guardrails/config/${guardType}` : "/copilot/guardrails/config", t, body),
  listPatterns: (t: string) => get<any[]>("/copilot/guardrails/patterns", t),
  createPattern: (t: string, body: any) => post("/copilot/guardrails/patterns", t, body),
  updatePattern: (t: string, patternId: string, body: any) => put(`/copilot/guardrails/patterns/${patternId}`, t, body),
  deletePattern: (t: string, patternId: string) => del(`/copilot/guardrails/patterns/${patternId}`, t),
  listEvents: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/guardrails/events", t, params),
  getAudit: (t: string, params?: Record<string, string>) => get("/copilot/guardrails/audit", t, params),
};

// ---------------------------------------------------------------------------
// Observability
// ---------------------------------------------------------------------------
export const observabilityApi = {
  listAuditLogs: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/observability/audit-logs", t, params),
  getUsageRollups: (t: string, params?: Record<string, string>) => get("/copilot/observability/usage-rollups", t, params),
  listAlerts: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/observability/alerts", t, params),
  getSummary: (t: string) => get("/copilot/observability/summary", t),
};

// ---------------------------------------------------------------------------
// Notification Templates
// ---------------------------------------------------------------------------
export const notificationApi = {
  list: (t: string) => get<any[]>("/copilot/notification-templates", t),
  create: (t: string, body: any) => post("/copilot/notification-templates", t, body),
  update: (t: string, templateId: string, body: any) => put(`/copilot/notification-templates/${templateId}`, t, body),
  delete: (t: string, templateId: string) => del(`/copilot/notification-templates/${templateId}`, t),
  preview: (t: string, templateId: string, body: any) => post(`/copilot/notification-templates/${templateId}/preview`, t, body),
  sendTest: (t: string, templateId: string, body: any) => post(`/copilot/notification-templates/${templateId}/send-test`, t, body),
};

// ---------------------------------------------------------------------------
// Support Tickets
// ---------------------------------------------------------------------------
export const supportApi = {
  listTickets: (t: string, params?: Record<string, string>) => get<any[]>("/copilot/support/tickets", t, params),
  createTicket: (t: string, body: any) => post("/copilot/support/tickets", t, body),
  getTicket: (t: string, ticketId: string) => get(`/copilot/support/tickets/${ticketId}`, t),
  updateTicket: (t: string, ticketId: string, body: any) => put(`/copilot/support/tickets/${ticketId}`, t, body),
  addComment: (t: string, ticketId: string, body: any) => post(`/copilot/support/tickets/${ticketId}/comments`, t, body),
  closeTicket: (t: string, ticketId: string) => post(`/copilot/support/tickets/${ticketId}/close`, t),
};

// ---------------------------------------------------------------------------
// Entitlements
// ---------------------------------------------------------------------------
export const entitlementApi = {
  listCatalog: (t: string) => get<any[]>("/copilot/entitlements/catalog", t),
  upsertCatalog: (t: string, featureKey: string, body: any) => put(`/copilot/entitlements/catalog/${featureKey}`, t, body),
  deleteCatalog: (t: string, featureKey: string) => del(`/copilot/entitlements/catalog/${featureKey}`, t),
  getAccountEntitlements: (t: string) => get("/copilot/entitlements/account", t),
  setAccountEntitlements: (t: string, body: any) => put("/copilot/entitlements/account", t, body),
};

// ---------------------------------------------------------------------------
// Global Ops (super admin)
// ---------------------------------------------------------------------------
export const globalOpsApi = {
  getAccountsSummary: (t: string) => get("/copilot/global-ops/accounts/summary", t),
  bulkModelEligibility: (t: string, body: any) => post("/copilot/global-ops/accounts/bulk/model-eligibility", t, body),
  bulkCredits: (t: string, body: any) => post("/copilot/global-ops/accounts/bulk/credits", t, body),
  bulkStatus: (t: string, body: any) => post("/copilot/global-ops/accounts/bulk/status", t, body),
};

// ---------------------------------------------------------------------------
// Super Admin
// ---------------------------------------------------------------------------
export const superAdminApi = {
  // Subscription plans
  listSubscriptionPlans: (t: string) => get<any[]>("/copilot/super-admin/subscription-plans", t),
  createSubscriptionPlan: (t: string, body: any) => post("/copilot/super-admin/subscription-plans", t, body),
  getSubscriptionPlan: (t: string, planId: string) => get(`/copilot/super-admin/subscription-plans/${planId}`, t),
  updateSubscriptionPlan: (t: string, planId: string, body: any) => put(`/copilot/super-admin/subscription-plans/${planId}`, t, body),
  deleteSubscriptionPlan: (t: string, planId: string) => del(`/copilot/super-admin/subscription-plans/${planId}`, t),

  // Account setup
  getAccountSetup: (t: string, accountId: string) => get(`/copilot/super-admin/accounts/${accountId}/setup`, t),
  upsertAccountSetup: (t: string, accountId: string, body: any) => put(`/copilot/super-admin/accounts/${accountId}/setup`, t, body),

  // Account entitlements
  listAccountEntitlements: (t: string, accountId: string) => get<any[]>(`/copilot/super-admin/accounts/${accountId}/entitlements`, t),
  createAccountEntitlement: (t: string, accountId: string, body: any) => post(`/copilot/super-admin/accounts/${accountId}/entitlements`, t, body),
  updateAccountEntitlement: (t: string, accountId: string, entitlementId: string, body: any) => put(`/copilot/super-admin/accounts/${accountId}/entitlements/${entitlementId}`, t, body),
  deleteAccountEntitlement: (t: string, accountId: string, entitlementId: string) => del(`/copilot/super-admin/accounts/${accountId}/entitlements/${entitlementId}`, t),

  // Account quotas
  listAccountQuotas: (t: string, accountId: string) => get<any[]>(`/copilot/super-admin/accounts/${accountId}/quotas`, t),
  createAccountQuota: (t: string, accountId: string, body: any) => post(`/copilot/super-admin/accounts/${accountId}/quotas`, t, body),
  updateAccountQuota: (t: string, accountId: string, quotaId: string, body: any) => put(`/copilot/super-admin/accounts/${accountId}/quotas/${quotaId}`, t, body),
  deleteAccountQuota: (t: string, accountId: string, quotaId: string) => del(`/copilot/super-admin/accounts/${accountId}/quotas/${quotaId}`, t),

  // Feature catalog
  listFeatureCatalog: (t: string) => get<any[]>("/copilot/super-admin/feature-catalog", t),
  createFeatureCatalogItem: (t: string, body: any) => post("/copilot/super-admin/feature-catalog", t, body),
  updateFeatureCatalogItem: (t: string, entryId: string, body: any) => put(`/copilot/super-admin/feature-catalog/${entryId}`, t, body),
  deleteFeatureCatalogItem: (t: string, entryId: string) => del(`/copilot/super-admin/feature-catalog/${entryId}`, t),

  // Platform catalog
  listPlatformCatalog: (t: string) => get<any[]>("/copilot/super-admin/platform-catalog", t),
  createPlatformCatalogItem: (t: string, body: any) => post("/copilot/super-admin/platform-catalog", t, body),
  updatePlatformCatalogItem: (t: string, code: string, body: any) => put(`/copilot/super-admin/platform-catalog/${code}`, t, body),
  deletePlatformCatalogItem: (t: string, code: string) => del(`/copilot/super-admin/platform-catalog/${code}`, t),

  // Config providers & models
  listConfigProviders: (t: string) => get<any[]>("/copilot/super-admin/config/providers", t),
  createConfigProvider: (t: string, body: any) => post("/copilot/super-admin/config/providers", t, body),
  updateConfigProvider: (t: string, providerId: string, body: any) => put(`/copilot/super-admin/config/providers/${providerId}`, t, body),
  deleteConfigProvider: (t: string, providerId: string) => del(`/copilot/super-admin/config/providers/${providerId}`, t),

  listConfigModels: (t: string) => get<any[]>("/copilot/super-admin/config/models", t),
  createConfigModel: (t: string, body: any) => post("/copilot/super-admin/config/models", t, body),
  updateConfigModel: (t: string, modelId: string, body: any) => put(`/copilot/super-admin/config/models/${modelId}`, t, body),
  deleteConfigModel: (t: string, modelId: string) => del(`/copilot/super-admin/config/models/${modelId}`, t),
};
