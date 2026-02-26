"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Tabs, Card, Row, Col, Modal, Form, Input, InputNumber, Select, Tag,
  Progress, Button, Switch, message,
} from "antd";
import { DollarOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotBudgetTree from "@/components/copilot/CopilotBudgetTree";
import { budgetApi, directoryApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

export default function CopilotCreditsPage() {
  const { accessToken } = useAuthorized();

  // Budget plan
  const [plan, setPlan] = useState<any>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planForm] = Form.useForm();

  // Allocations
  const [allocations, setAllocations] = useState<any[]>([]);
  const [allocLoading, setAllocLoading] = useState(false);
  const [allocModal, setAllocModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [allocForm] = Form.useForm();
  const [treeView, setTreeView] = useState(false);

  // Usage
  const [usage, setUsage] = useState<any[]>([]);
  const [usageLoading, setUsageLoading] = useState(false);

  // Alert rules
  const [alerts, setAlerts] = useState<any[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertModal, setAlertModal] = useState<{ open: boolean }>({ open: false });
  const [alertForm] = Form.useForm();

  // Directory data for scope selectors
  const [orgs, setOrgs] = useState<any[]>([]);
  const [teams, setTeams] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);

  // Distribute modal
  const [distributeModal, setDistributeModal] = useState(false);
  const [distributeForm] = Form.useForm();

  const loadPlan = useCallback(async () => {
    if (!accessToken) return;
    setPlanLoading(true);
    try {
      const d = await budgetApi.getPlan(accessToken);
      setPlan(d);
      if (d) planForm.setFieldsValue(d);
    } catch { setPlan(null); }
    finally { setPlanLoading(false); }
  }, [accessToken, planForm]);

  const loadAllocations = useCallback(async () => {
    if (!accessToken) return;
    setAllocLoading(true);
    try { const d = await budgetApi.listAllocations(accessToken); setAllocations(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load allocations"); }
    finally { setAllocLoading(false); }
  }, [accessToken]);

  const loadUsage = useCallback(async () => {
    if (!accessToken) return;
    setUsageLoading(true);
    try {
      const d = await budgetApi.listUsage(accessToken);
      const arr = Array.isArray(d) ? d : [];
      setUsage(arr.map((r: any, i: number) => ({ ...r, _key: r.usage_id ?? `${r.timestamp}-${r.scope_id}-${i}` })));
    }
    catch (e: any) { message.error(e?.message ?? "Failed to load usage"); }
    finally { setUsageLoading(false); }
  }, [accessToken]);

  const loadAlerts = useCallback(async () => {
    if (!accessToken) return;
    setAlertsLoading(true);
    try { const d = await budgetApi.listAlerts(accessToken); setAlerts(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load alerts"); }
    finally { setAlertsLoading(false); }
  }, [accessToken]);

  const loadDirectory = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [o, t, u] = await Promise.all([
        directoryApi.listOrganizations(accessToken).catch(() => []),
        directoryApi.listTeams(accessToken).catch(() => []),
        directoryApi.listUsers(accessToken).catch(() => []),
      ]);
      setOrgs(Array.isArray(o) ? o : []);
      setTeams(Array.isArray(t) ? t : []);
      setUsers(Array.isArray(u) ? u : []);
    } catch {}
  }, [accessToken]);

  useEffect(() => {
    loadPlan(); loadAllocations(); loadUsage(); loadAlerts(); loadDirectory();
  }, [loadPlan, loadAllocations, loadUsage, loadAlerts, loadDirectory]);

  const handleRefresh = () => { loadPlan(); loadAllocations(); loadUsage(); loadAlerts(); };

  const handlePlanSave = async () => {
    if (!accessToken) return;
    try {
      const values = await planForm.validateFields();
      await budgetApi.upsertPlan(accessToken, values);
      message.success("Budget plan saved");
      loadPlan();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleAllocSave = async () => {
    if (!accessToken) return;
    try {
      const values = await allocForm.validateFields();
      await budgetApi.upsertAllocation(accessToken, values);
      message.success("Allocation saved");
      setAllocModal({ open: false, editing: null }); allocForm.resetFields(); loadAllocations();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleAlertSave = async () => {
    if (!accessToken) return;
    try {
      const values = await alertForm.validateFields();
      await budgetApi.upsertAlertRule(accessToken, values);
      message.success("Alert rule saved");
      setAlertModal({ open: false }); alertForm.resetFields(); loadAlerts();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleDistribute = async () => {
    if (!accessToken) return;
    try {
      const values = await distributeForm.validateFields();
      await budgetApi.distribute(accessToken, values);
      message.success("Credits distributed");
      setDistributeModal(false); distributeForm.resetFields(); loadAllocations();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Distribution failed"); }
  };

  // Scope options based on scope_type
  const scopeTypeValue = Form.useWatch("scope_type", allocForm);
  const getScopeOptions = (scopeType: string) => {
    if (scopeType === "ORG") return orgs.map(o => ({ value: o.organization_id, label: o.name || o.organization_id }));
    if (scopeType === "TEAM") return teams.map(t => ({ value: t.team_id, label: t.name || t.team_id }));
    if (scopeType === "USER") return users.map(u => ({ value: u.user_id, label: u.display_name || u.email || u.user_id }));
    return [];
  };

  const totalAllocated = allocations.reduce((s, a) => s + (a.allocated_credits ?? 0), 0);
  const accountCredits = plan?.account_allocated_credits ?? 0;
  const unallocated = accountCredits - totalAllocated;

  return (
    <CopilotPageShell title="Credit Budgets" subtitle="Manage credit allocation, distribution, and usage across the hierarchy." icon={<DollarOutlined />} onRefresh={handleRefresh}>
      <CopilotStatsRow stats={[
        { title: "Account Credits", value: accountCredits, loading: planLoading },
        { title: "Allocated", value: totalAllocated, loading: allocLoading },
        { title: "Unallocated", value: unallocated, loading: allocLoading },
        { title: "Credits Factor", value: plan?.credits_factor != null ? `${plan.credits_factor}x` : "1x", loading: planLoading },
        { title: "Cycle", value: plan?.cycle ?? "monthly", loading: planLoading },
      ]} />
      <Tabs defaultActiveKey="plan" items={[
        { key: "plan", label: "Budget Plan", children: (
          <Card size="small">
            <Form form={planForm} layout="vertical" style={{ maxWidth: 500 }}>
              <Form.Item name="cycle" label="Billing Cycle" initialValue="monthly">
                <Select options={[{ value: "monthly", label: "Monthly" }, { value: "weekly", label: "Weekly" }, { value: "daily", label: "Daily" }]} />
              </Form.Item>
              <Form.Item name="credits_factor" label="Credits Factor" extra="Multiplier applied to raw USD cost to get credits.">
                <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder="e.g. 1.0" />
              </Form.Item>
              <Form.Item name="account_allocated_credits" label="Account Allocated Credits">
                <InputNumber min={0} step={100} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="overflow_credits" label="Overflow Credits" extra="Pay-later credits available after allocation exhausted.">
                <InputNumber min={0} step={100} style={{ width: "100%" }} />
              </Form.Item>
              <Button type="primary" onClick={handlePlanSave} loading={planLoading}>Save Plan</Button>
            </Form>
          </Card>
        )},
        { key: "allocations", label: `Allocations (${allocations.length})`, children: (
          <>
            <Row style={{ marginBottom: 12 }} justify="end" gutter={8}>
              <Col>
                <span style={{ marginRight: 8 }}>Tree View</span>
                <Switch checked={treeView} onChange={setTreeView} size="small" />
              </Col>
              <Col>
                <Button onClick={() => { distributeForm.resetFields(); setDistributeModal(true); }}>Distribute Equally</Button>
              </Col>
            </Row>
            {treeView ? (
              <CopilotBudgetTree accountCredits={accountCredits} allocations={allocations} orgs={orgs} teams={teams} />
            ) : (
              <CopilotCrudTable dataSource={allocations} rowKey="allocation_id" loading={allocLoading}
                searchFields={["scope_type", "scope_id", "scope_name"]}
                addLabel="Add Allocation"
                onAdd={() => { allocForm.resetFields(); setAllocModal({ open: true, editing: null }); }}
                onEdit={(r) => { allocForm.setFieldsValue(r); setAllocModal({ open: true, editing: r }); }}
                onDelete={async (r) => { if (accessToken) { await budgetApi.deleteAllocation(accessToken, r.allocation_id); loadAllocations(); } }}
                columns={[
                  { title: "Scope Type", dataIndex: "scope_type", key: "scope_type", render: (v: string) => <Tag color="blue">{v}</Tag> },
                  { title: "Scope ID", dataIndex: "scope_id", key: "scope_id", ellipsis: true },
                  { title: "Scope Name", dataIndex: "scope_name", key: "scope_name" },
                  { title: "Allocated", dataIndex: "allocated_credits", key: "allocated_credits" },
                  { title: "Used", dataIndex: "used_credits", key: "used_credits" },
                  { title: "Overflow Cap", dataIndex: "overflow_cap", key: "overflow_cap", render: (v: number) => v ?? "—" },
                  { title: "Utilization", key: "util", render: (_: unknown, r: any) => {
                    if (!r.allocated_credits) return "—";
                    const pct = Math.round(((r.used_credits ?? 0) / r.allocated_credits) * 100);
                    return <Progress percent={pct} size="small" status={pct > 90 ? "exception" : pct > 70 ? "active" : "normal"} />;
                  }},
                ]}
              />
            )}
            <Modal title={allocModal.editing ? "Edit Allocation" : "Add Allocation"} open={allocModal.open} onOk={handleAllocSave} onCancel={() => setAllocModal({ open: false, editing: null })} width={500}>
              <Form form={allocForm} layout="vertical">
                <Form.Item name="scope_type" label="Scope Type" rules={[{ required: true }]}>
                  <Select options={[{ value: "ORG", label: "Organization" }, { value: "TEAM", label: "Team" }, { value: "USER", label: "User" }]} />
                </Form.Item>
                <Form.Item name="scope_id" label="Scope" rules={[{ required: true }]}>
                  <Select showSearch optionFilterProp="label" placeholder="Select scope" options={getScopeOptions(scopeTypeValue)} />
                </Form.Item>
                <Form.Item name="allocated_credits" label="Allocated Credits" rules={[{ required: true }]}>
                  <InputNumber min={0} step={100} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="overflow_cap" label="Overflow Cap">
                  <InputNumber min={0} step={50} style={{ width: "100%" }} />
                </Form.Item>
              </Form>
            </Modal>
            <Modal title="Distribute Credits Equally" open={distributeModal} onOk={handleDistribute} onCancel={() => setDistributeModal(false)} width={400}>
              <Form form={distributeForm} layout="vertical">
                <Form.Item name="scope_type" label="Distribute Among" rules={[{ required: true }]}>
                  <Select options={[{ value: "ORG", label: "Organizations" }, { value: "TEAM", label: "Teams" }, { value: "USER", label: "Users" }]} />
                </Form.Item>
                <Form.Item name="total_credits" label="Total Credits to Distribute" rules={[{ required: true }]}>
                  <InputNumber min={0} step={100} style={{ width: "100%" }} />
                </Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "usage", label: `Usage History (${usage.length})`, children: (
          <CopilotCrudTable dataSource={usage} rowKey="_key" loading={usageLoading}
            searchFields={["scope_type", "scope_id", "description"]}
            showActions={false}
            columns={[
              { title: "Timestamp", dataIndex: "timestamp", key: "timestamp", render: (v: string) => v ? new Date(v).toLocaleString() : "—" },
              { title: "Scope Type", dataIndex: "scope_type", key: "scope_type", render: (v: string) => <Tag color="blue">{v}</Tag> },
              { title: "Scope ID", dataIndex: "scope_id", key: "scope_id", ellipsis: true },
              { title: "Amount", dataIndex: "amount", key: "amount" },
              { title: "Raw Cost (USD)", dataIndex: "raw_cost_usd", key: "raw_cost_usd", render: (v: number) => v != null ? `$${v.toFixed(4)}` : "—" },
              { title: "Credits Factor", dataIndex: "credits_factor", key: "credits_factor" },
              { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
            ]}
          />
        )},
        { key: "alerts", label: `Alert Rules (${alerts.length})`, children: (
          <>
            <CopilotCrudTable dataSource={alerts} rowKey="rule_id" loading={alertsLoading}
              searchFields={["rule_id", "scope_type", "scope_id"]}
              addLabel="Add Alert Rule"
              onAdd={() => { alertForm.resetFields(); setAlertModal({ open: true }); }}
              showActions={false}
              columns={[
                { title: "Rule ID", dataIndex: "rule_id", key: "rule_id", ellipsis: true },
                { title: "Threshold %", dataIndex: "threshold_pct", key: "threshold_pct", render: (v: number) => v != null ? `${v}%` : "—" },
                { title: "Scope Type", dataIndex: "scope_type", key: "scope_type", render: (v: string) => v ? <Tag>{v}</Tag> : "All" },
                { title: "Scope ID", dataIndex: "scope_id", key: "scope_id", ellipsis: true },
                { title: "Enabled", dataIndex: "enabled", key: "enabled", render: (v: boolean) => <Tag color={v !== false ? "green" : "default"}>{v !== false ? "Yes" : "No"}</Tag> },
              ]}
            />
            <Modal title="Add Alert Rule" open={alertModal.open} onOk={handleAlertSave} onCancel={() => setAlertModal({ open: false })} width={450}>
              <Form form={alertForm} layout="vertical">
                <Form.Item name="threshold_pct" label="Threshold (%)" rules={[{ required: true }]}>
                  <InputNumber min={1} max={100} style={{ width: "100%" }} placeholder="e.g. 80" />
                </Form.Item>
                <Form.Item name="scope_type" label="Scope Type">
                  <Select allowClear placeholder="All scopes" options={[{ value: "ORG", label: "Organization" }, { value: "TEAM", label: "Team" }, { value: "USER", label: "User" }]} />
                </Form.Item>
                <Form.Item name="scope_id" label="Scope ID">
                  <Input placeholder="Leave empty for all" />
                </Form.Item>
              </Form>
            </Modal>
          </>
        )},
      ]} />
    </CopilotPageShell>
  );
}
