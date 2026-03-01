"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  message,
  Switch,
  Popconfirm,
} from "antd";
import { DeleteOutlined, DownloadOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

type ContextResp = {
  account_id: string | null;
  is_super_admin: boolean;
  roles: string[];
  scopes: string[];
  product_domains_allowed: string[];
};

type OrgItem = { id: string; name: string; description?: string; is_default_global?: boolean };
type TeamItem = { id: string; org_id: string; name: string; description?: string };
type UserItem = { id: string; email?: string; display_name?: string; identity_user_id?: string };

type AgentItem = {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  mandatory_guardrail_preset_ids?: string[];
};
type ConnectionItem = {
  id: string;
  connection_type: string;
  name: string;
  description?: string;
  credential_visibility?: string;
  allow_user_self_manage?: boolean;
  created_at?: string;
};
type GuardrailPreset = { id: string; code: string; name: string; preset_json?: Record<string, any>; created_at?: string };
type GuardrailAssignment = { id: string; preset_id: string; scope_type: string; scope_id: string; created_at?: string };
type GuardrailPattern = {
  id: string;
  guard_type: string;
  pattern_name: string;
  pattern_regex: string;
  pattern_type: string;
  enabled: boolean;
};
type ModelGrant = {
  id: string;
  domain: string;
  model_name: string;
  scope_type: string;
  scope_id: string;
  access_mode: string;
  created_at?: string;
};
type FeatureEntitlement = {
  id: string;
  domain: string;
  feature_code: string;
  scope_type: string;
  scope_id: string;
  enabled: boolean;
  created_at?: string;
};
type MarketplaceItem = {
  id: string;
  entity_type: string;
  entity_id: string;
  title: string;
  description?: string;
  is_published: boolean;
  grants?: Array<{ scope_type: string; scope_id: string }>;
  created_at?: string;
};
type AuditItem = {
  id: string;
  action: string;
  table_name?: string;
  object_id?: string;
  updated_at?: string;
  updated_values?: Record<string, any>;
};

type BudgetAllocationItem = {
  scope_type: string;
  scope_id: string;
  base_allocated: number;
  effective_allocated: number;
  override_applied: boolean;
  overflow_cap?: number | null;
};

type UsageByScopeItem = {
  scope_type: string;
  scope_id: string;
  allocated_credits: number;
  used: number;
  usage_percentage: number;
  overflow_cap?: number | null;
  overflow_used?: number;
};

type BudgetAlertItem = {
  entity_name: string;
  usage_percentage: number;
  alert_level: string;
  budget?: { entity_type?: string; entity_id?: string };
};

type CostBreakdownItem = {
  key?: string | null;
  raw_cost?: number;
  credits?: number;
};

type CopilotControlViewProps = {
  routeTab?: string;
  syncWithQuery?: boolean;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.detail || data?.error || `Request failed: ${res.status}`);
  }
  return data as T;
}

type CsvPrimitive = string | number | boolean | null | undefined;
type CsvColumn<T> = { header: string; value: (row: T) => CsvPrimitive };

function csvCell(value: CsvPrimitive): string {
  const text = value == null ? "" : String(value);
  if (/["\n,]/.test(text)) {
    return `"${text.replace(/"/g, "\"\"")}"`;
  }
  return text;
}

function downloadCsv<T>(filename: string, columns: CsvColumn<T>[], rows: T[]) {
  const headerLine = columns.map((col) => csvCell(col.header)).join(",");
  const dataLines = rows.map((row) => columns.map((col) => csvCell(col.value(row))).join(",")).join("\n");
  const csv = `${headerLine}\n${dataLines}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export function CopilotControlView({ routeTab, syncWithQuery = true }: CopilotControlViewProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const validTabs = useMemo(
    () =>
      new Set([
        "overview",
        "global-ops",
        "directory",
        "budgets",
        "agents",
        "connections",
        "guardrails",
        "models",
        "entitlements",
        "marketplace",
        "observability",
        "notifications",
        "support",
        "audit",
      ]),
    []
  );
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [ctx, setCtx] = useState<ContextResp | null>(null);

  const [orgs, setOrgs] = useState<OrgItem[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [users, setUsers] = useState<UserItem[]>([]);

  const [activePlan, setActivePlan] = useState<{ id: string; name: string } | null>(null);
  const [accountAllocation, setAccountAllocation] = useState<{ monthly_credits: number; overflow_limit: number; credit_factor: number } | null>(null);
  const [effectiveAllocations, setEffectiveAllocations] = useState<BudgetAllocationItem[]>([]);

  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [connections, setConnections] = useState<ConnectionItem[]>([]);
  const [guardrailPresets, setGuardrailPresets] = useState<GuardrailPreset[]>([]);
  const [guardrailAssignments, setGuardrailAssignments] = useState<GuardrailAssignment[]>([]);
  const [guardrailPatterns, setGuardrailPatterns] = useState<GuardrailPattern[]>([]);
  const [copilotModelGrants, setCopilotModelGrants] = useState<ModelGrant[]>([]);
  const [consoleModelGrants, setConsoleModelGrants] = useState<ModelGrant[]>([]);
  const [featureEntitlements, setFeatureEntitlements] = useState<FeatureEntitlement[]>([]);
  const [marketplace, setMarketplace] = useState<MarketplaceItem[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditItem[]>([]);
  const [usageByScope, setUsageByScope] = useState<UsageByScopeItem[]>([]);
  const [budgetAlerts, setBudgetAlerts] = useState<BudgetAlertItem[]>([]);
  const [costByAgent, setCostByAgent] = useState<CostBreakdownItem[]>([]);
  const [costByModel, setCostByModel] = useState<CostBreakdownItem[]>([]);
  const [costByConnection, setCostByConnection] = useState<CostBreakdownItem[]>([]);
  const [costByGuardrail, setCostByGuardrail] = useState<CostBreakdownItem[]>([]);
  const [costBreakdownRows, setCostBreakdownRows] = useState<
    Array<{ model_name?: string; agent_id?: string; connection_id?: string; guardrail_code?: string; raw_cost?: number; credits_incurred?: number }>
  >([]);

  const [orgForm] = Form.useForm();
  const [teamForm] = Form.useForm();
  const [userForm] = Form.useForm();
  const [allocationForm] = Form.useForm();
  const [planForm] = Form.useForm();
  const [equalForm] = Form.useForm();
  const [overrideForm] = Form.useForm();
  const [agentForm] = Form.useForm();
  const [connectionForm] = Form.useForm();
  const [connectionGrantForm] = Form.useForm();
  const [guardrailPresetForm] = Form.useForm();
  const [guardrailAssignForm] = Form.useForm();
  const [guardrailPatternForm] = Form.useForm();
  const [modelGrantForm] = Form.useForm();
  const [featureForm] = Form.useForm();
  const [marketForm] = Form.useForm();
  const [marketGrantForm] = Form.useForm();

  const scopeOptions = useMemo(() => {
    const opts: Array<{ label: string; value: string }> = [];
    orgs.forEach((o) => opts.push({ label: `org:${o.name}`, value: `org:${o.id}` }));
    teams.forEach((t) => opts.push({ label: `team:${t.name}`, value: `team:${t.id}` }));
    users.forEach((u) => opts.push({ label: `user:${u.display_name || u.email || u.id}`, value: `user:${u.id}` }));
    return opts;
  }, [orgs, teams, users]);

  const splitScope = (value: string): { scope_type: string; scope_id: string } => {
    const [scope_type, ...rest] = value.split(":");
    return { scope_type, scope_id: rest.join(":") };
  };

  const refreshAll = async () => {
    setLoading(true);
    try {
      const me = await api<ContextResp>("/v1/me/context").catch(() => null);
      if (me) {
        setCtx(me);
      }

      const [
        orgResp,
        teamResp,
        userResp,
        allocResp,
        planResp,
        agentsResp,
        connectionsResp,
        presetResp,
        assignResp,
        patternResp,
        copilotModelsResp,
        consoleModelsResp,
        featureResp,
        marketplaceResp,
        auditResp,
        usageResp,
        alertsResp,
        costByAgentResp,
        costByModelResp,
        costByConnectionResp,
        costByGuardrailResp,
        costBreakdownResp,
      ] = await Promise.all([
        api<{ items: OrgItem[] }>("/v1/copilot/orgs"),
        api<{ items: TeamItem[] }>("/v1/copilot/teams"),
        api<{ items: UserItem[] }>("/v1/copilot/users"),
        api<{ monthly_credits: number; overflow_limit: number; credit_factor: number }>("/v1/budgets/copilot/account-allocation").catch(
          () => ({ monthly_credits: 0, overflow_limit: 0, credit_factor: 1 })
        ),
        api<{ item: { id: string; name: string } | null }>("/v1/budgets/copilot/plans/active"),
        api<{ items: AgentItem[] }>("/v1/copilot/agents"),
        api<{ items: ConnectionItem[] }>("/v1/copilot/connections"),
        api<{ items: GuardrailPreset[] }>("/v1/copilot/guardrails/presets"),
        api<{ items: GuardrailAssignment[] }>("/v1/copilot/guardrails/assignments"),
        api<{ items: GuardrailPattern[] }>("/v1/copilot/guardrails/patterns?limit=200"),
        api<{ items: ModelGrant[] }>("/v1/copilot/models/grants"),
        api<{ items: ModelGrant[] }>("/v1/console/models/grants"),
        api<{ items: FeatureEntitlement[] }>("/v1/features/entitlements?domain=copilot"),
        api<{ items: MarketplaceItem[] }>("/v1/copilot/marketplace?limit=100&include_grants=true"),
        api<{ items: AuditItem[] }>("/v1/audit?domain=copilot&limit=100"),
        api<{ items: UsageByScopeItem[] }>("/v1/budgets/copilot/usage-by-scope"),
        api<{ items: BudgetAlertItem[] }>("/v1/budgets/copilot/alerts?threshold=80"),
        api<{ items: CostBreakdownItem[] }>("/v1/budgets/copilot/cost-breakdown?by=agent"),
        api<{ items: CostBreakdownItem[] }>("/v1/budgets/copilot/cost-breakdown?by=llm"),
        api<{ items: CostBreakdownItem[] }>("/v1/budgets/copilot/cost-breakdown?by=connection"),
        api<{ items: CostBreakdownItem[] }>("/v1/budgets/copilot/cost-breakdown?by=guardrail"),
        api<{
          items: Array<{
            model_name?: string;
            agent_id?: string;
            connection_id?: string;
            guardrail_code?: string;
            raw_cost?: number;
            credits_incurred?: number;
          }>;
        }>("/v1/costs/breakdown?domain=copilot"),
      ]);

      setOrgs(orgResp.items || []);
      setTeams(teamResp.items || []);
      setUsers(userResp.items || []);
      setAccountAllocation(allocResp);
      setActivePlan(planResp.item);
      setAgents(agentsResp.items || []);
      setConnections(connectionsResp.items || []);
      setGuardrailPresets(presetResp.items || []);
      setGuardrailAssignments(assignResp.items || []);
      setGuardrailPatterns(patternResp.items || []);
      setCopilotModelGrants(copilotModelsResp.items || []);
      setConsoleModelGrants(consoleModelsResp.items || []);
      setFeatureEntitlements(featureResp.items || []);
      setMarketplace(marketplaceResp.items || []);
      setAuditLogs(auditResp.items || []);
      setUsageByScope(usageResp.items || []);
      setBudgetAlerts(alertsResp.items || []);
      setCostByAgent(costByAgentResp.items || []);
      setCostByModel(costByModelResp.items || []);
      setCostByConnection(costByConnectionResp.items || []);
      setCostByGuardrail(costByGuardrailResp.items || []);
      setCostBreakdownRows(costBreakdownResp.items || []);

      if (planResp.item?.id) {
        const effective = await api<{ items: BudgetAllocationItem[] }>(
          `/v1/budgets/copilot/effective-allocation?plan_id=${encodeURIComponent(planResp.item.id)}`
        );
        setEffectiveAllocations(effective.items || []);
      } else {
        setEffectiveAllocations([]);
      }
    } catch (e: any) {
      message.error(e.message || "Failed to load control-plane data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  useEffect(() => {
    const fromRoute = (routeTab || "").trim().toLowerCase();
    const normalizedRouteTab = fromRoute === "access" ? "models" : fromRoute;
    if (normalizedRouteTab && validTabs.has(normalizedRouteTab)) {
      setActiveTab(normalizedRouteTab);
      return;
    }
    const tab = (searchParams.get("tab") || "").trim().toLowerCase();
    const normalizedQueryTab = tab === "access" ? "models" : tab;
    if (validTabs.has(normalizedQueryTab)) {
      setActiveTab(normalizedQueryTab);
      return;
    }
    setActiveTab("overview");
  }, [routeTab, searchParams, validTabs]);

  const onTabChange = (key: string) => {
    setActiveTab(key);
    if (!syncWithQuery) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", key);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  const createOrg = async (values: { name: string; description?: string }) => {
    await api("/v1/copilot/orgs", { method: "POST", body: JSON.stringify(values) });
    orgForm.resetFields();
    await refreshAll();
  };

  const createTeam = async (values: { org_id: string; name: string; description?: string }) => {
    await api("/v1/copilot/teams", { method: "POST", body: JSON.stringify(values) });
    teamForm.resetFields();
    await refreshAll();
  };

  const createUser = async (values: { email?: string; display_name?: string; identity_user_id?: string; team_ids?: string[] }) => {
    await api("/v1/copilot/users", { method: "POST", body: JSON.stringify(values) });
    userForm.resetFields();
    await refreshAll();
  };

  const setAllocation = async (values: { account_id: string; monthly_credits: number; overflow_limit: number; credit_factor: number }) => {
    await api("/v1/budgets/account-allocation", { method: "POST", body: JSON.stringify(values) });
    await refreshAll();
  };

  const createPlan = async (values: { name: string; cycle?: string }) => {
    await api("/v1/budgets/copilot/plans", { method: "POST", body: JSON.stringify(values) });
    planForm.resetFields();
    await refreshAll();
  };

  const equalDistribute = async (values: { scope_type: string; ids: string; total_credits: number; overflow_cap?: number }) => {
    if (!activePlan?.id) throw new Error("Create an active plan first");
    const ids = values.ids
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    await api("/v1/budgets/copilot/distribute/equal", {
      method: "POST",
      body: JSON.stringify({
        plan_id: activePlan.id,
        scope_type: values.scope_type,
        scope_ids: ids,
        total_credits: values.total_credits,
        overflow_cap: values.overflow_cap,
      }),
    });
    equalForm.resetFields();
    await refreshAll();
  };

  const setOverride = async (values: { scope: string; override_credits: number; reason?: string }) => {
    if (!activePlan?.id) throw new Error("Create an active plan first");
    const { scope_type, scope_id } = splitScope(values.scope);
    await api("/v1/budgets/copilot/overrides", {
      method: "POST",
      body: JSON.stringify({
        plan_id: activePlan.id,
        scope_type,
        scope_id,
        override_credits: values.override_credits,
        reason: values.reason,
      }),
    });
    overrideForm.resetFields();
    await refreshAll();
  };

  const createAgent = async (values: {
    name: string;
    description?: string;
    definition_json?: string;
    guardrail_preset_ids: string[];
  }) => {
    const parsed = values.definition_json ? JSON.parse(values.definition_json) : {};
    await api("/v1/copilot/agents", {
      method: "POST",
      body: JSON.stringify({
        name: values.name,
        description: values.description,
        definition_json: parsed,
        grants: [],
        guardrail_preset_ids: values.guardrail_preset_ids || [],
      }),
    });
    agentForm.resetFields();
    await refreshAll();
  };

  const createConnection = async (values: {
    connection_type: string;
    name: string;
    description?: string;
    credential_visibility?: string;
    allow_user_self_manage?: boolean;
    config_json?: string;
    secret_json?: string;
  }) => {
    await api(`/v1/copilot/connections/${values.connection_type}`, {
      method: "POST",
      body: JSON.stringify({
        name: values.name,
        description: values.description,
        credential_visibility: values.credential_visibility || "use_only",
        allow_user_self_manage: values.allow_user_self_manage || false,
        config_json: values.config_json ? JSON.parse(values.config_json) : {},
        secret_json: values.secret_json ? JSON.parse(values.secret_json) : {},
      }),
    });
    connectionForm.resetFields();
    await refreshAll();
  };

  const grantConnection = async (values: { connection_id: string; scope: string; can_manage?: boolean }) => {
    const { scope_type, scope_id } = splitScope(values.scope);
    await api(`/v1/copilot/connections/${values.connection_id}/grants`, {
      method: "POST",
      body: JSON.stringify({ scope_type, scope_id, can_manage: values.can_manage || false }),
    });
    connectionGrantForm.resetFields();
    message.success("Connection grant saved");
  };

  const createPreset = async (values: { code: string; name: string; preset_json?: string }) => {
    await api("/v1/copilot/guardrails/presets", {
      method: "POST",
      body: JSON.stringify({
        code: values.code,
        name: values.name,
        preset_json: values.preset_json ? JSON.parse(values.preset_json) : {},
      }),
    });
    guardrailPresetForm.resetFields();
    await refreshAll();
  };

  const assignPreset = async (values: { preset_id: string; scope: string }) => {
    const { scope_type, scope_id } = splitScope(values.scope);
    await api("/v1/copilot/guardrails/assignments", {
      method: "POST",
      body: JSON.stringify({ preset_id: values.preset_id, scope_type, scope_id }),
    });
    guardrailAssignForm.resetFields();
    await refreshAll();
  };

  const createPattern = async (values: {
    guard_type: string;
    pattern_name: string;
    pattern_regex: string;
    pattern_type: string;
    action?: string;
    enabled?: boolean;
  }) => {
    await api("/v1/copilot/guardrails/patterns", {
      method: "POST",
      body: JSON.stringify({ ...values, enabled: values.enabled ?? true }),
    });
    guardrailPatternForm.resetFields();
    await refreshAll();
  };

  const grantModel = async (values: { domain: "copilot" | "console"; model_name: string; scope: string; access_mode: "allow" | "deny" }) => {
    const { scope_type, scope_id } = splitScope(values.scope);
    const path = values.domain === "copilot" ? "/v1/copilot/models/grants" : "/v1/console/models/grants";
    await api(path, {
      method: "POST",
      body: JSON.stringify({
        domain: values.domain,
        model_name: values.model_name,
        scope_type,
        scope_id,
        access_mode: values.access_mode,
      }),
    });
    modelGrantForm.resetFields();
    await refreshAll();
  };

  const setFeatureEntitlement = async (values: { feature_code: string; scope: string; enabled: boolean; config_json?: string }) => {
    const { scope_type, scope_id } = splitScope(values.scope);
    await api("/v1/features/entitlements", {
      method: "POST",
      body: JSON.stringify({
        domain: "copilot",
        feature_code: values.feature_code,
        scope_type,
        scope_id,
        enabled: values.enabled,
        config_json: values.config_json ? JSON.parse(values.config_json) : {},
      }),
    });
    featureForm.resetFields();
    await refreshAll();
  };

  const createMarketplace = async (values: { entity_type: string; entity_id: string; title: string; description?: string; is_published?: boolean }) => {
    await api("/v1/copilot/marketplace", {
      method: "POST",
      body: JSON.stringify({
        entity_type: values.entity_type,
        entity_id: values.entity_id,
        title: values.title,
        description: values.description,
        is_published: values.is_published ?? false,
      }),
    });
    marketForm.resetFields();
    await refreshAll();
  };

  const grantMarketplace = async (values: { marketplace_id: string; scope: string }) => {
    const { scope_type, scope_id } = splitScope(values.scope);
    await api(`/v1/copilot/marketplace/${values.marketplace_id}/grants`, {
      method: "POST",
      body: JSON.stringify({ scope_type, scope_id }),
    });
    marketGrantForm.resetFields();
    await refreshAll();
  };

  const publishMarketplace = async (id: string, publish: boolean) => {
    await api(`/v1/copilot/marketplace/${id}/publish?publish=${publish}`, { method: "POST" });
    await refreshAll();
  };

  const deleteAgent = async (id: string) => {
    await api(`/v1/copilot/agents/${id}`, { method: "DELETE" });
    await refreshAll();
  };

  const deleteConnection = async (id: string) => {
    await api(`/v1/copilot/connections/${id}`, { method: "DELETE" });
    await refreshAll();
  };

  const deleteMarketplace = async (id: string) => {
    await api(`/v1/copilot/marketplace/${id}`, { method: "DELETE" });
    await refreshAll();
  };

  const notificationRows = useMemo(() => {
    const budget = (budgetAlerts || []).map((alert, idx) => ({
      id: `budget-${idx}-${alert?.budget?.entity_id || "scope"}`,
      type: "budget",
      severity: alert.alert_level || "warning",
      title: `Budget ${alert.alert_level || "warning"}: ${alert.entity_name || "scope"}`,
      description: `Usage at ${Number(alert.usage_percentage || 0).toFixed(1)}%`,
      time: "",
    }));

    const audit = (auditLogs || []).slice(0, 30).map((entry) => ({
      id: `audit-${entry.id}`,
      type: "audit",
      severity: "info",
      title: `${entry.action || "event"} on ${entry.table_name || "resource"}`,
      description: entry.object_id ? `Object: ${entry.object_id}` : "Control-plane update",
      time: entry.updated_at || "",
    }));

    return [...budget, ...audit]
      .sort((a, b) => (a.time < b.time ? 1 : -1))
      .slice(0, 100);
  }, [budgetAlerts, auditLogs]);

  const highUsageScopes = useMemo(
    () =>
      usageByScope
        .filter((scope) => Number(scope.usage_percentage || 0) >= 80)
        .sort((a, b) => Number(b.usage_percentage || 0) - Number(a.usage_percentage || 0)),
    [usageByScope]
  );

  const severeAlerts = useMemo(
    () => budgetAlerts.filter((alert) => ["critical", "exceeded"].includes(String(alert.alert_level || "").toLowerCase())),
    [budgetAlerts]
  );

  const totalAllocatedCredits = useMemo(
    () => usageByScope.reduce((sum, row) => sum + Number(row.allocated_credits || 0), 0),
    [usageByScope]
  );
  const totalUsedCredits = useMemo(() => usageByScope.reduce((sum, row) => sum + Number(row.used || 0), 0), [usageByScope]);
  const totalUsagePct = totalAllocatedCredits > 0 ? (totalUsedCredits / totalAllocatedCredits) * 100 : 0;

  const exportBudgetAlertsCsv = () =>
    downloadCsv(
      "copilot_budget_alerts.csv",
      [
        { header: "entity_name", value: (r: BudgetAlertItem) => r.entity_name || "" },
        { header: "usage_percentage", value: (r: BudgetAlertItem) => Number(r.usage_percentage || 0).toFixed(2) },
        { header: "alert_level", value: (r: BudgetAlertItem) => r.alert_level || "" },
        { header: "scope_type", value: (r: BudgetAlertItem) => r?.budget?.entity_type || "" },
        { header: "scope_id", value: (r: BudgetAlertItem) => r?.budget?.entity_id || "" },
      ],
      budgetAlerts
    );

  const exportUsageByScopeCsv = () =>
    downloadCsv(
      "copilot_usage_by_scope.csv",
      [
        { header: "scope_type", value: (r: UsageByScopeItem) => r.scope_type || "" },
        { header: "scope_id", value: (r: UsageByScopeItem) => r.scope_id || "" },
        { header: "allocated_credits", value: (r: UsageByScopeItem) => r.allocated_credits ?? 0 },
        { header: "used", value: (r: UsageByScopeItem) => r.used ?? 0 },
        { header: "usage_percentage", value: (r: UsageByScopeItem) => Number(r.usage_percentage || 0).toFixed(2) },
        { header: "overflow_used", value: (r: UsageByScopeItem) => r.overflow_used ?? 0 },
      ],
      usageByScope
    );

  const exportDetailedCostsCsv = () =>
    downloadCsv(
      "copilot_cost_breakdown_detailed.csv",
      [
        { header: "model_name", value: (r) => r.model_name || "" },
        { header: "agent_id", value: (r) => r.agent_id || "" },
        { header: "connection_id", value: (r) => r.connection_id || "" },
        { header: "guardrail_code", value: (r) => r.guardrail_code || "" },
        { header: "raw_cost", value: (r) => r.raw_cost ?? 0 },
        { header: "credits_incurred", value: (r) => r.credits_incurred ?? 0 },
      ],
      costBreakdownRows
    );

  const exportCostSummaryCsv = (filename: string, rows: CostBreakdownItem[]) =>
    downloadCsv(
      filename,
      [
        { header: "key", value: (r: CostBreakdownItem) => r.key || "" },
        { header: "raw_cost", value: (r: CostBreakdownItem) => r.raw_cost ?? 0 },
        { header: "credits", value: (r: CostBreakdownItem) => r.credits ?? 0 },
      ],
      rows
    );

  const exportNotificationsCsv = () =>
    downloadCsv(
      "copilot_notifications_feed.csv",
      [
        { header: "time", value: (r) => r.time || "" },
        { header: "severity", value: (r) => r.severity || "" },
        { header: "type", value: (r) => r.type || "" },
        { header: "title", value: (r) => r.title || "" },
        { header: "description", value: (r) => r.description || "" },
      ],
      notificationRows
    );

  const orgOptions = orgs.map((o) => ({ label: o.name, value: o.id }));

  return (
    <div style={{ padding: 16 }}>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0 }}>Copilot Control Plane</h2>
          <p style={{ margin: 0, color: "#666" }}>
            Unified admin experience for Copilot entities, budgets, agents, tools, guardrails, model access, marketplace, and audit.
          </p>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={refreshAll}>
          Refresh
        </Button>
      </Space>

      <Alert
        type="info"
        showIcon
        message="Context"
        description={
          <Space wrap>
            <Tag>account_id: {ctx?.account_id || "none"}</Tag>
            <Tag color={ctx?.is_super_admin ? "gold" : "blue"}>super_admin: {String(!!ctx?.is_super_admin)}</Tag>
            <Tag>roles: {(ctx?.roles || []).join(",") || "-"}</Tag>
            <Tag>domains: {(ctx?.product_domains_allowed || []).join(",") || "-"}</Tag>
          </Space>
        }
        style={{ marginBottom: 16 }}
      />

      <Tabs
        activeKey={activeTab}
        onChange={onTabChange}
        items={[
          {
            key: "overview",
            label: "Overview",
            children: (
              <Row gutter={16}>
                <Col span={6}><Card title="Orgs">{orgs.length}</Card></Col>
                <Col span={6}><Card title="Teams">{teams.length}</Card></Col>
                <Col span={6}><Card title="Users">{users.length}</Card></Col>
                <Col span={6}><Card title="Agents">{agents.length}</Card></Col>
                <Col span={6} style={{ marginTop: 16 }}><Card title="Connections">{connections.length}</Card></Col>
                <Col span={6} style={{ marginTop: 16 }}><Card title="Guardrails">{guardrailPresets.length}</Card></Col>
                <Col span={6} style={{ marginTop: 16 }}><Card title="Marketplace">{marketplace.length}</Card></Col>
                <Col span={6} style={{ marginTop: 16 }}><Card title="Audit Entries">{auditLogs.length}</Card></Col>
              </Row>
            ),
          },
          {
            key: "global-ops",
            label: "Global Ops",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Alert
                  type="info"
                  showIcon
                  message="Copilot global operations dashboard"
                  description="Cross-scope posture for usage, budget pressure, and operational escalation. Use this page to triage before moving to detailed tabs."
                />
                <Row gutter={16}>
                  <Col span={6}><Card title="Active Plan">{activePlan?.name || "None"}</Card></Col>
                  <Col span={6}><Card title="Total Allocated">{totalAllocatedCredits.toFixed(2)}</Card></Col>
                  <Col span={6}><Card title="Total Used">{totalUsedCredits.toFixed(2)}</Card></Col>
                  <Col span={6}><Card title="Portfolio Usage">{totalUsagePct.toFixed(1)}%</Card></Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}><Card title="High Usage Scopes (>=80%)">{highUsageScopes.length}</Card></Col>
                  <Col span={8}><Card title="Severe Alerts">{severeAlerts.length}</Card></Col>
                  <Col span={8}><Card title="Notification Items">{notificationRows.length}</Card></Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Top High-Usage Scopes">
                      <Table
                        rowKey={(r) => `${r.scope_type}:${r.scope_id}`}
                        size="small"
                        dataSource={highUsageScopes.slice(0, 12)}
                        pagination={false}
                        columns={[
                          { title: "Scope", render: (_, r) => `${r.scope_type}:${r.scope_id}` },
                          { title: "Used", dataIndex: "used" },
                          { title: "Allocated", dataIndex: "allocated_credits" },
                          { title: "Usage %", render: (_, r) => Number(r.usage_percentage || 0).toFixed(1) },
                        ]}
                      />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Severe Budget Alerts">
                      <Table
                        rowKey={(r, idx) => `${r.entity_name || "scope"}-${idx}`}
                        size="small"
                        dataSource={severeAlerts.slice(0, 12)}
                        pagination={false}
                        columns={[
                          { title: "Entity", dataIndex: "entity_name" },
                          { title: "Usage %", render: (_, r) => Number(r.usage_percentage || 0).toFixed(1) },
                          { title: "Level", dataIndex: "alert_level" },
                          { title: "Scope", render: (_, r) => `${r?.budget?.entity_type || "-"}:${r?.budget?.entity_id || "-"}` },
                        ]}
                      />
                    </Card>
                  </Col>
                </Row>
                <Card title="Quick Navigation">
                  <Space wrap>
                    <Button onClick={() => onTabChange("budgets")}>Open Budgets</Button>
                    <Button onClick={() => onTabChange("observability")}>Open Observability</Button>
                    <Button onClick={() => onTabChange("notifications")}>Open Notifications</Button>
                    <Button onClick={() => onTabChange("support")}>Open Support</Button>
                    <Button onClick={() => onTabChange("audit")}>Open Audit</Button>
                  </Space>
                </Card>
              </Space>
            ),
          },
          {
            key: "directory",
            label: "Directory",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card title="Create Org">
                      <Form form={orgForm} layout="vertical" onFinish={createOrg}>
                        <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
                        <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>Create</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Create Team">
                      <Form form={teamForm} layout="vertical" onFinish={createTeam}>
                        <Form.Item name="org_id" label="Org" rules={[{ required: true }]}><Select options={orgOptions} /></Form.Item>
                        <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
                        <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>Create</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Create User">
                      <Form form={userForm} layout="vertical" onFinish={createUser}>
                        <Form.Item name="email" label="Email"><Input /></Form.Item>
                        <Form.Item name="display_name" label="Display Name"><Input /></Form.Item>
                        <Form.Item
                          name="identity_user_id"
                          label="Identity User ID (optional)"
                          extra="Optional. If omitted, cockpit will try to resolve this from Zitadel using the email."
                        >
                          <Input placeholder="Auto-resolved from email when possible" />
                        </Form.Item>
                        <Form.Item name="team_ids" label="Team Memberships"><Select mode="multiple" options={teams.map((t) => ({ label: t.name, value: t.id }))} /></Form.Item>
                        <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>Create</Button>
                      </Form>
                    </Card>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card title="Orgs">
                      <Table rowKey="id" size="small" dataSource={orgs} pagination={{ pageSize: 6 }} columns={[{ title: "Name", dataIndex: "name" }, { title: "Global", render: (_, r) => (r.is_default_global ? <Tag color="green">yes</Tag> : <Tag>no</Tag>) }]} />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Teams">
                      <Table rowKey="id" size="small" dataSource={teams} pagination={{ pageSize: 6 }} columns={[{ title: "Name", dataIndex: "name" }, { title: "Org", dataIndex: "org_id" }]} />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Users">
                      <Table rowKey="id" size="small" dataSource={users} pagination={{ pageSize: 6 }} columns={[{ title: "Name", render: (_, u) => u.display_name || u.email || u.id }, { title: "Email", dataIndex: "email" }]} />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: "budgets",
            label: "Budgets",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card title="Super Admin Allocation">
                      <Form
                        form={allocationForm}
                        layout="vertical"
                        initialValues={{
                          account_id: ctx?.account_id || "",
                          monthly_credits: accountAllocation?.monthly_credits || 0,
                          overflow_limit: accountAllocation?.overflow_limit || 0,
                          credit_factor: accountAllocation?.credit_factor || 1,
                        }}
                        onFinish={setAllocation}
                      >
                        <Form.Item name="account_id" label="Account ID" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="monthly_credits" label="Monthly Credits" rules={[{ required: true }]}><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
                        <Form.Item name="overflow_limit" label="Overflow Limit" rules={[{ required: true }]}><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
                        <Form.Item name="credit_factor" label="Credit Factor" rules={[{ required: true }]}><InputNumber min={0.01} step={0.1} style={{ width: "100%" }} /></Form.Item>
                        <Button type="primary" htmlType="submit">Save</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title={`Active Plan: ${activePlan?.name || "None"}`}>
                      <Form form={planForm} layout="vertical" onFinish={createPlan}>
                        <Form.Item name="name" label="Plan Name" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="cycle" label="Cycle" initialValue="monthly"><Select options={[{ label: "Monthly", value: "monthly" }, { label: "Quarterly", value: "quarterly" }]} /></Form.Item>
                        <Button type="primary" htmlType="submit">Create / Activate</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Equal Distribution">
                      <Form form={equalForm} layout="vertical" onFinish={equalDistribute}>
                        <Form.Item name="scope_type" label="Scope Type" rules={[{ required: true }]}>
                          <Select options={[{ label: "Org", value: "org" }, { label: "Team", value: "team" }, { label: "User", value: "user" }]} />
                        </Form.Item>
                        <Form.Item name="ids" label="Scope IDs (comma separated)" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="total_credits" label="Total Credits" rules={[{ required: true }]}><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
                        <Form.Item name="overflow_cap" label="Overflow Cap"><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
                        <Button type="primary" htmlType="submit">Distribute</Button>
                      </Form>
                    </Card>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card title="Override Allocation">
                      <Form form={overrideForm} layout="vertical" onFinish={setOverride}>
                        <Form.Item name="scope" label="Scope" rules={[{ required: true }]}><Select options={scopeOptions} /></Form.Item>
                        <Form.Item name="override_credits" label="Override Credits" rules={[{ required: true }]}><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
                        <Form.Item name="reason" label="Reason"><Input /></Form.Item>
                        <Button type="primary" htmlType="submit">Save Override</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={16}>
                    <Card title="Effective Allocation">
                      <Table
                        rowKey={(r) => `${r.scope_type}:${r.scope_id}`}
                        size="small"
                        dataSource={effectiveAllocations}
                        pagination={{ pageSize: 8 }}
                        columns={[
                          { title: "Scope", render: (_, r) => `${r.scope_type}:${r.scope_id}` },
                          { title: "Base", dataIndex: "base_allocated" },
                          { title: "Effective", dataIndex: "effective_allocated" },
                          { title: "Override", render: (_, r) => (r.override_applied ? <Tag color="orange">yes</Tag> : <Tag>no</Tag>) },
                          { title: "Overflow", dataIndex: "overflow_cap" },
                        ]}
                      />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: "agents",
            label: "Agents",
            children: (
              <Row gutter={16}>
                <Col span={10}>
                  <Card title="Create Agent">
                    <Form form={agentForm} layout="vertical" onFinish={createAgent}>
                      <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                      <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
                      <Form.Item
                        name="guardrail_preset_ids"
                        label="Mandatory Guardrails"
                        rules={[{ required: true, type: "array", min: 1, message: "Select at least one preset" }]}
                      >
                        <Select
                          mode="multiple"
                          placeholder="Choose one or more guardrail presets"
                          options={guardrailPresets.map((p) => ({ label: `${p.code} (${p.name})`, value: p.id }))}
                        />
                      </Form.Item>
                      <Form.Item name="definition_json" label="Definition JSON"><Input.TextArea rows={5} placeholder='{"system_prompt":"..."}' /></Form.Item>
                      <Button type="primary" htmlType="submit">Create</Button>
                    </Form>
                  </Card>
                </Col>
                <Col span={14}>
                  <Card title="Agents">
                    <Table
                      rowKey="id"
                      size="small"
                      dataSource={agents}
                      pagination={{ pageSize: 8 }}
                      columns={[
                        { title: "Name", dataIndex: "name" },
                        { title: "Description", dataIndex: "description" },
                        {
                          title: "Guardrails",
                          render: (_, a) =>
                            (a.mandatory_guardrail_preset_ids || []).length ? (
                              <Tag color="blue">{(a.mandatory_guardrail_preset_ids || []).length}</Tag>
                            ) : (
                              <Tag color="red">0</Tag>
                            ),
                        },
                        { title: "Created", dataIndex: "created_at" },
                        {
                          title: "Actions",
                          render: (_, a) => (
                            <Popconfirm title="Delete this agent?" onConfirm={() => deleteAgent(a.id)}>
                              <Button danger size="small" icon={<DeleteOutlined />} />
                            </Popconfirm>
                          ),
                        },
                      ]}
                    />
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "connections",
            label: "Connections",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Create Connection">
                      <Form form={connectionForm} layout="vertical" onFinish={createConnection}>
                        <Form.Item name="connection_type" label="Type" rules={[{ required: true }]}>
                          <Select options={[{ label: "OpenAPI", value: "openapi" }, { label: "MCP", value: "mcp" }, { label: "Composio", value: "composio" }]} />
                        </Form.Item>
                        <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="description" label="Description"><Input /></Form.Item>
                        <Form.Item name="credential_visibility" label="Credential Visibility" initialValue="use_only">
                          <Select options={[{ label: "Use Only", value: "use_only" }, { label: "Self Managed", value: "self_managed" }]} />
                        </Form.Item>
                        <Form.Item name="allow_user_self_manage" label="Allow User Self Manage" valuePropName="checked"><Switch /></Form.Item>
                        <Form.Item name="config_json" label="Config JSON"><Input.TextArea rows={3} /></Form.Item>
                        <Form.Item name="secret_json" label="Secret JSON"><Input.TextArea rows={3} /></Form.Item>
                        <Button type="primary" htmlType="submit">Create</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Grant Connection Access">
                      <Form form={connectionGrantForm} layout="vertical" onFinish={grantConnection}>
                        <Form.Item name="connection_id" label="Connection" rules={[{ required: true }]}>
                          <Select options={connections.map((c) => ({ label: `${c.name} (${c.connection_type})`, value: c.id }))} />
                        </Form.Item>
                        <Form.Item name="scope" label="Scope" rules={[{ required: true }]}><Select options={scopeOptions} /></Form.Item>
                        <Form.Item name="can_manage" label="Can Manage" valuePropName="checked"><Switch /></Form.Item>
                        <Button type="primary" htmlType="submit">Grant</Button>
                      </Form>
                    </Card>
                  </Col>
                </Row>
                <Card title="Connections">
                  <Table
                    rowKey="id"
                    size="small"
                    dataSource={connections}
                    pagination={{ pageSize: 8 }}
                    columns={[
                      { title: "Name", dataIndex: "name" },
                      { title: "Type", dataIndex: "connection_type" },
                      { title: "Visibility", dataIndex: "credential_visibility" },
                      { title: "Self Manage", render: (_, c) => (c.allow_user_self_manage ? <Tag color="green">yes</Tag> : <Tag>no</Tag>) },
                      {
                        title: "Actions",
                        render: (_, c) => (
                          <Popconfirm title="Delete this connection?" onConfirm={() => deleteConnection(c.id)}>
                            <Button danger size="small" icon={<DeleteOutlined />} />
                          </Popconfirm>
                        ),
                      },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
          {
            key: "guardrails",
            label: "Guardrails",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card title="Preset">
                      <Form form={guardrailPresetForm} layout="vertical" onFinish={createPreset}>
                        <Form.Item name="code" label="Code" rules={[{ required: true }]}><Input placeholder="pii" /></Form.Item>
                        <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="preset_json" label="Preset JSON"><Input.TextArea rows={4} /></Form.Item>
                        <Button type="primary" htmlType="submit">Save</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Assignment">
                      <Form form={guardrailAssignForm} layout="vertical" onFinish={assignPreset}>
                        <Form.Item name="preset_id" label="Preset" rules={[{ required: true }]}>
                          <Select options={guardrailPresets.map((p) => ({ label: `${p.code} (${p.name})`, value: p.id }))} />
                        </Form.Item>
                        <Form.Item name="scope" label="Scope" rules={[{ required: true }]}><Select options={scopeOptions} /></Form.Item>
                        <Button type="primary" htmlType="submit">Assign</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Pattern">
                      <Form form={guardrailPatternForm} layout="vertical" onFinish={createPattern}>
                        <Form.Item name="guard_type" label="Guard Type" rules={[{ required: true }]}>
                          <Select options={[{ label: "PII", value: "pii" }, { label: "Jailbreak", value: "jailbreak" }, { label: "Toxic", value: "toxic" }]} />
                        </Form.Item>
                        <Form.Item name="pattern_name" label="Pattern Name" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="pattern_regex" label="Regex" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="pattern_type" label="Type" rules={[{ required: true }]}>
                          <Select options={[{ label: "Detect", value: "detect" }, { label: "Block", value: "block" }, { label: "Allow", value: "allow" }]} />
                        </Form.Item>
                        <Form.Item name="enabled" label="Enabled" valuePropName="checked"><Switch defaultChecked /></Form.Item>
                        <Button type="primary" htmlType="submit">Create</Button>
                      </Form>
                    </Card>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card title="Presets">
                      <Table rowKey="id" size="small" dataSource={guardrailPresets} pagination={{ pageSize: 6 }} columns={[{ title: "Code", dataIndex: "code" }, { title: "Name", dataIndex: "name" }]} />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Assignments">
                      <Table rowKey="id" size="small" dataSource={guardrailAssignments} pagination={{ pageSize: 6 }} columns={[{ title: "Preset", dataIndex: "preset_id" }, { title: "Scope", render: (_, a) => `${a.scope_type}:${a.scope_id}` }]} />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Patterns">
                      <Table rowKey="id" size="small" dataSource={guardrailPatterns} pagination={{ pageSize: 6 }} columns={[{ title: "Guard", dataIndex: "guard_type" }, { title: "Name", dataIndex: "pattern_name" }, { title: "Type", dataIndex: "pattern_type" }]} />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: "models",
            label: "Models",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Grant Model Access">
                      <Form form={modelGrantForm} layout="vertical" onFinish={grantModel}>
                        <Form.Item name="domain" label="Domain" rules={[{ required: true }]} initialValue="copilot">
                          <Select options={[{ label: "Copilot", value: "copilot" }, { label: "Console", value: "console" }]} />
                        </Form.Item>
                        <Form.Item name="model_name" label="Model" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="scope" label="Scope" rules={[{ required: true }]}><Select options={scopeOptions} /></Form.Item>
                        <Form.Item name="access_mode" label="Access" rules={[{ required: true }]} initialValue="allow">
                          <Select options={[{ label: "Allow", value: "allow" }, { label: "Deny", value: "deny" }]} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit">Grant</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Console Model Grants (read-only)">
                      <Table rowKey="id" size="small" dataSource={consoleModelGrants} pagination={{ pageSize: 6 }} columns={[{ title: "Model", dataIndex: "model_name" }, { title: "Scope", render: (_, r) => `${r.scope_type}:${r.scope_id}` }, { title: "Mode", dataIndex: "access_mode" }]} />
                    </Card>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Copilot Model Grants">
                      <Table rowKey="id" size="small" dataSource={copilotModelGrants} pagination={{ pageSize: 6 }} columns={[{ title: "Model", dataIndex: "model_name" }, { title: "Scope", render: (_, r) => `${r.scope_type}:${r.scope_id}` }, { title: "Mode", dataIndex: "access_mode" }]} />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: "entitlements",
            label: "Feature Access",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Set Feature Entitlement">
                      <Form form={featureForm} layout="vertical" onFinish={setFeatureEntitlement}>
                        <Form.Item name="feature_code" label="Feature Code" rules={[{ required: true }]}>
                          <Select
                            options={[
                              { label: "create_agents", value: "create_agents" },
                              { label: "create_connections_openapi", value: "create_connections_openapi" },
                              { label: "create_connections_mcp", value: "create_connections_mcp" },
                              { label: "create_connections_composio", value: "create_connections_composio" },
                              { label: "image_generation", value: "image_generation" },
                              { label: "model_access", value: "model_access" },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item name="scope" label="Scope" rules={[{ required: true }]}><Select options={scopeOptions} /></Form.Item>
                        <Form.Item name="enabled" label="Enabled" valuePropName="checked"><Switch defaultChecked /></Form.Item>
                        <Form.Item name="config_json" label="Config JSON"><Input.TextArea rows={3} /></Form.Item>
                        <Button type="primary" htmlType="submit">Save</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Feature Entitlements">
                      <Table rowKey="id" size="small" dataSource={featureEntitlements} pagination={{ pageSize: 8 }} columns={[{ title: "Feature", dataIndex: "feature_code" }, { title: "Scope", render: (_, r) => `${r.scope_type}:${r.scope_id}` }, { title: "Enabled", render: (_, r) => (r.enabled ? <Tag color="green">yes</Tag> : <Tag color="red">no</Tag>) }]} />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: "marketplace",
            label: "Marketplace",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Create / Update Listing">
                      <Form form={marketForm} layout="vertical" onFinish={createMarketplace}>
                        <Row gutter={16}>
                          <Col span={12}><Form.Item name="entity_type" label="Entity Type" rules={[{ required: true }]} initialValue="agent"><Select options={[{ label: "Agent", value: "agent" }, { label: "Connection", value: "connection" }]} /></Form.Item></Col>
                          <Col span={12}><Form.Item name="entity_id" label="Entity ID" rules={[{ required: true }]}><Input /></Form.Item></Col>
                        </Row>
                        <Row gutter={16}>
                          <Col span={12}><Form.Item name="title" label="Title" rules={[{ required: true }]}><Input /></Form.Item></Col>
                          <Col span={12}><Form.Item name="is_published" label="Published" valuePropName="checked"><Switch /></Form.Item></Col>
                        </Row>
                        <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
                        <Button type="primary" htmlType="submit">Save Listing</Button>
                      </Form>
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Grant Listing Visibility">
                      <Form form={marketGrantForm} layout="vertical" onFinish={grantMarketplace}>
                        <Form.Item name="marketplace_id" label="Listing" rules={[{ required: true }]}>
                          <Select options={marketplace.map((m) => ({ label: `${m.title} (${m.entity_type})`, value: m.id }))} />
                        </Form.Item>
                        <Form.Item name="scope" label="Scope" rules={[{ required: true }]}>
                          <Select options={scopeOptions} />
                        </Form.Item>
                        <Button type="primary" htmlType="submit">Grant Visibility</Button>
                      </Form>
                    </Card>
                  </Col>
                </Row>
                <Card title="Listings">
                  <Table
                    rowKey="id"
                    size="small"
                    dataSource={marketplace}
                    pagination={{ pageSize: 8 }}
                    columns={[
                      { title: "Title", dataIndex: "title" },
                      { title: "Type", dataIndex: "entity_type" },
                      { title: "Entity", dataIndex: "entity_id" },
                      { title: "Grants", render: (_, item) => <Tag>{(item.grants || []).length}</Tag> },
                      {
                        title: "Published",
                        render: (_, item) => (
                          <Switch checked={!!item.is_published} onChange={(checked) => publishMarketplace(item.id, checked)} />
                        ),
                      },
                      {
                        title: "Actions",
                        render: (_, item) => (
                          <Popconfirm title="Delete this listing?" onConfirm={() => deleteMarketplace(item.id)}>
                            <Button danger size="small" icon={<DeleteOutlined />} />
                          </Popconfirm>
                        ),
                      },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
          {
            key: "observability",
            label: "Observability",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Row gutter={16}>
                  <Col span={6}><Card title="Budget Alerts">{budgetAlerts.length}</Card></Col>
                  <Col span={6}><Card title="Usage Scopes">{usageByScope.length}</Card></Col>
                  <Col span={6}><Card title="Cost Drivers">{costBreakdownRows.length}</Card></Col>
                  <Col span={6}><Card title="Audit Events">{auditLogs.length}</Card></Col>
                </Row>
                <Card title="Budget Alerts">
                  <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                    <Button
                      size="small"
                      icon={<DownloadOutlined />}
                      disabled={!budgetAlerts.length}
                      onClick={exportBudgetAlertsCsv}
                    >
                      Export CSV
                    </Button>
                  </Space>
                  <Table
                    rowKey={(r) => `${r?.budget?.entity_id || "scope"}-${r.entity_name}-${r.alert_level}`}
                    size="small"
                    dataSource={budgetAlerts}
                    pagination={{ pageSize: 8 }}
                    columns={[
                      { title: "Entity", dataIndex: "entity_name" },
                      { title: "Usage %", render: (_, r) => Number(r.usage_percentage || 0).toFixed(1) },
                      {
                        title: "Level",
                        render: (_, r) => {
                          const level = (r.alert_level || "warning").toLowerCase();
                          const color = level === "exceeded" ? "red" : level === "critical" ? "orange" : "gold";
                          return <Tag color={color}>{level}</Tag>;
                        },
                      },
                      { title: "Scope", render: (_, r) => `${r?.budget?.entity_type || "-"}:${r?.budget?.entity_id || "-"}` },
                    ]}
                  />
                </Card>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Usage By Scope">
                      <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          disabled={!usageByScope.length}
                          onClick={exportUsageByScopeCsv}
                        >
                          Export CSV
                        </Button>
                      </Space>
                      <Table
                        rowKey={(r) => `${r.scope_type}:${r.scope_id}`}
                        size="small"
                        dataSource={usageByScope}
                        pagination={{ pageSize: 8 }}
                        columns={[
                          { title: "Scope", render: (_, r) => `${r.scope_type}:${r.scope_id}` },
                          { title: "Allocated", dataIndex: "allocated_credits" },
                          { title: "Used", dataIndex: "used" },
                          { title: "Usage %", render: (_, r) => Number(r.usage_percentage || 0).toFixed(1) },
                          { title: "Overflow Used", dataIndex: "overflow_used" },
                        ]}
                      />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Cost Breakdown (Detailed)">
                      <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          disabled={!costBreakdownRows.length}
                          onClick={exportDetailedCostsCsv}
                        >
                          Export CSV
                        </Button>
                      </Space>
                      <Table
                        rowKey={(r, idx) => `${r.model_name || "-"}-${r.agent_id || "-"}-${idx}`}
                        size="small"
                        dataSource={costBreakdownRows}
                        pagination={{ pageSize: 8 }}
                        columns={[
                          { title: "Model", dataIndex: "model_name" },
                          { title: "Agent", dataIndex: "agent_id" },
                          { title: "Connection", dataIndex: "connection_id" },
                          { title: "Guardrail", dataIndex: "guardrail_code" },
                          { title: "Credits", dataIndex: "credits_incurred" },
                        ]}
                      />
                    </Card>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Top Agents By Credits">
                      <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          disabled={!costByAgent.length}
                          onClick={() => exportCostSummaryCsv("copilot_cost_by_agent.csv", costByAgent)}
                        >
                          Export CSV
                        </Button>
                      </Space>
                      <Table
                        rowKey={(r, idx) => `${r.key || "none"}-${idx}`}
                        size="small"
                        dataSource={costByAgent}
                        pagination={{ pageSize: 6 }}
                        columns={[
                          { title: "Agent", dataIndex: "key" },
                          { title: "Raw Cost", dataIndex: "raw_cost" },
                          { title: "Credits", dataIndex: "credits" },
                        ]}
                      />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Top Models By Credits">
                      <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          disabled={!costByModel.length}
                          onClick={() => exportCostSummaryCsv("copilot_cost_by_model.csv", costByModel)}
                        >
                          Export CSV
                        </Button>
                      </Space>
                      <Table
                        rowKey={(r, idx) => `${r.key || "none"}-${idx}`}
                        size="small"
                        dataSource={costByModel}
                        pagination={{ pageSize: 6 }}
                        columns={[
                          { title: "Model", dataIndex: "key" },
                          { title: "Raw Cost", dataIndex: "raw_cost" },
                          { title: "Credits", dataIndex: "credits" },
                        ]}
                      />
                    </Card>
                  </Col>
                </Row>
                <Row gutter={16}>
                  <Col span={12}>
                    <Card title="Top Connections By Credits">
                      <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          disabled={!costByConnection.length}
                          onClick={() => exportCostSummaryCsv("copilot_cost_by_connection.csv", costByConnection)}
                        >
                          Export CSV
                        </Button>
                      </Space>
                      <Table
                        rowKey={(r, idx) => `${r.key || "none"}-${idx}`}
                        size="small"
                        dataSource={costByConnection}
                        pagination={{ pageSize: 6 }}
                        columns={[
                          { title: "Connection", dataIndex: "key" },
                          { title: "Raw Cost", dataIndex: "raw_cost" },
                          { title: "Credits", dataIndex: "credits" },
                        ]}
                      />
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card title="Top Guardrails By Credits">
                      <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          disabled={!costByGuardrail.length}
                          onClick={() => exportCostSummaryCsv("copilot_cost_by_guardrail.csv", costByGuardrail)}
                        >
                          Export CSV
                        </Button>
                      </Space>
                      <Table
                        rowKey={(r, idx) => `${r.key || "none"}-${idx}`}
                        size="small"
                        dataSource={costByGuardrail}
                        pagination={{ pageSize: 6 }}
                        columns={[
                          { title: "Guardrail", dataIndex: "key" },
                          { title: "Raw Cost", dataIndex: "raw_cost" },
                          { title: "Credits", dataIndex: "credits" },
                        ]}
                      />
                    </Card>
                  </Col>
                </Row>
              </Space>
            ),
          },
          {
            key: "notifications",
            label: "Notifications",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Alert
                  type="info"
                  showIcon
                  message="Operational notifications"
                  description="Budget alerts are prioritized and merged with recent control-plane audit events for Copilot."
                />
                <Card title="Notification Feed">
                  <Space style={{ marginBottom: 12, width: "100%", justifyContent: "flex-end" }}>
                    <Button
                      size="small"
                      icon={<DownloadOutlined />}
                      disabled={!notificationRows.length}
                      onClick={exportNotificationsCsv}
                    >
                      Export CSV
                    </Button>
                  </Space>
                  <Table
                    rowKey="id"
                    size="small"
                    dataSource={notificationRows}
                    pagination={{ pageSize: 12 }}
                    columns={[
                      { title: "Time", dataIndex: "time" },
                      {
                        title: "Severity",
                        render: (_, r) => {
                          const sev = (r.severity || "info").toLowerCase();
                          const color = sev === "exceeded" ? "red" : sev === "critical" ? "orange" : sev === "warning" ? "gold" : "blue";
                          return <Tag color={color}>{sev}</Tag>;
                        },
                      },
                      { title: "Type", dataIndex: "type" },
                      { title: "Title", dataIndex: "title" },
                      { title: "Description", dataIndex: "description" },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
          {
            key: "support",
            label: "Support",
            children: (
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <Alert
                  type="info"
                  showIcon
                  message="Copilot support center"
                  description="Use this area for operational triage. Review recent alerts, audit history, and high-usage scopes before escalating incidents."
                />
                <Row gutter={16}>
                  <Col span={8}>
                    <Card title="Current Alerts">
                      <div style={{ fontSize: 28, fontWeight: 600 }}>{budgetAlerts.length}</div>
                      <div style={{ color: "#666" }}>Budget/usage alerts requiring review.</div>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="Recent Audit Events">
                      <div style={{ fontSize: 28, fontWeight: 600 }}>{auditLogs.length}</div>
                      <div style={{ color: "#666" }}>Most recent Copilot control-plane changes.</div>
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card title="High Usage Scopes">
                      <div style={{ fontSize: 28, fontWeight: 600 }}>
                        {usageByScope.filter((i) => Number(i.usage_percentage || 0) >= 90).length}
                      </div>
                      <div style={{ color: "#666" }}>Scopes currently above 90% utilization.</div>
                    </Card>
                  </Col>
                </Row>
                <Card title="Escalation Checklist">
                  <ol style={{ margin: 0, paddingLeft: 18 }}>
                    <li>Validate affected scope in <strong>Observability</strong> and confirm usage trend.</li>
                    <li>Check <strong>Notifications</strong> feed for correlated budget and policy events.</li>
                    <li>Review <strong>Audit</strong> for recent grant/policy/guardrail changes.</li>
                    <li>Apply temporary budget overrides or feature controls if user impact is ongoing.</li>
                    <li>Document incident with account, scope, timestamp, and mitigation applied.</li>
                  </ol>
                </Card>
              </Space>
            ),
          },
          {
            key: "audit",
            label: "Audit",
            children: (
              <Card title="Copilot Audit Log">
                <Table
                  rowKey="id"
                  size="small"
                  dataSource={auditLogs}
                  pagination={{ pageSize: 10 }}
                  columns={[
                    { title: "Time", dataIndex: "updated_at" },
                    { title: "Action", dataIndex: "action" },
                    { title: "Table", dataIndex: "table_name" },
                    { title: "Object", dataIndex: "object_id" },
                    {
                      title: "Domain",
                      render: (_, item) => {
                        const domain = item?.updated_values?.domain || "copilot";
                        return <Tag>{domain}</Tag>;
                      },
                    },
                  ]}
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}

export default function CopilotControlPage() {
  return <CopilotControlView syncWithQuery />;
}
