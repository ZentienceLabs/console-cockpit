"use client";

import React, { useMemo } from "react";
import { Alert, Card, Col, Row, Select, Statistic, Table, Tabs, Tag } from "antd";
import { useCopilotSupportTickets } from "@/app/(dashboard)/hooks/copilot/useCopilotSupportTickets";
import {
  useCopilotObservabilityAlerts,
  useCopilotObservabilityAudit,
  useCopilotObservabilitySummary,
} from "@/app/(dashboard)/hooks/copilot/useCopilotObservability";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";

const { TabPane } = Tabs;

const CopilotObservabilityPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = React.useState<string | undefined>(accountId || undefined);
  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();

  const { data: alertsData, isLoading: alertsLoading } = useCopilotObservabilityAlerts({ account_id: accountFilter, limit: 500 });
  const { data: summaryData } = useCopilotObservabilitySummary({ account_id: accountFilter });
  const { data: auditData, isLoading: auditLoading } = useCopilotObservabilityAudit({ account_id: accountFilter, limit: 500, offset: 0 });
  const { data: ticketData, isLoading: ticketsLoading } = useCopilotSupportTickets({ account_id: accountFilter, limit: 200, offset: 0 });

  const budgetAlerts = alertsData?.data?.budget_alerts ?? [];
  const guardrailAlerts = alertsData?.data?.guardrail_alerts ?? [];
  const auditLogs = auditData?.data ?? [];
  const tickets = ticketData?.data ?? [];
  const accounts = accountData?.accounts || [];

  const stats = useMemo(() => {
    const criticalBudgetAlerts = budgetAlerts.filter((a: any) => ["critical", "at_limit"].includes(String(a.alert_level || "").toLowerCase())).length;
    const openTickets = tickets.filter((t: any) => ["OPEN", "IN_PROGRESS", "PENDING"].includes(t.status)).length;
    return {
      budgetAlerts: Number(summaryData?.data?.budget_alerts ?? budgetAlerts.length ?? 0),
      criticalBudgetAlerts,
      guardrailAlerts: Number(summaryData?.data?.guardrail_alerts ?? guardrailAlerts.length ?? 0),
      auditEvents7d: Number(summaryData?.data?.audit_events_7d ?? auditLogs.length ?? 0),
      openTickets,
    };
  }, [budgetAlerts, guardrailAlerts, auditLogs, tickets, summaryData]);

  return (
    <div style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Copilot Observability"
        description="Copilot-only operational visibility: budget alerts, guardrail risk alerts, support activity, and Copilot audit logs."
      />
      {isSuperAdmin && (
        <div style={{ marginBottom: 16 }}>
          <Select
            placeholder="Filter by account"
            allowClear
            style={{ width: 360 }}
            loading={accountLoading}
            value={selectedAccountId}
            onChange={(value) => setSelectedAccountId(value)}
            options={accounts.map((a: any) => ({
              label: `${a.account_name} (${a.status})`,
              value: a.account_id,
            }))}
          />
        </div>
      )}

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={5}><Card><Statistic title="Budget Alerts" value={stats.budgetAlerts} /></Card></Col>
        <Col span={5}><Card><Statistic title="Critical Budget" value={stats.criticalBudgetAlerts} /></Card></Col>
        <Col span={5}><Card><Statistic title="Guardrail Alerts" value={stats.guardrailAlerts} /></Card></Col>
        <Col span={5}><Card><Statistic title="Audit Events (7d)" value={stats.auditEvents7d} /></Card></Col>
        <Col span={4}><Card><Statistic title="Open Tickets" value={stats.openTickets} /></Card></Col>
      </Row>

      <Tabs defaultActiveKey="budget-alerts">
        <TabPane tab="Budget Alerts" key="budget-alerts">
          <Table
            rowKey={(r: any) => `${r.scope_type}:${r.scope_id}:${r.cycle_end}`}
            loading={alertsLoading}
            dataSource={budgetAlerts}
            columns={[
              {
                title: "Entity",
                key: "entity",
                render: (_: any, r: any) => `${r.scope_type}:${r.scope_id}`,
              },
              { title: "Used", dataIndex: "used", key: "used" },
              { title: "Limit", dataIndex: "limit_amount", key: "limit_amount" },
              { title: "Usage %", dataIndex: "usage_pct", key: "usage_pct" },
              {
                title: "Level",
                key: "level",
                render: (_: any, r: any) => {
                  const lvl = String(r.alert_level || "ok").toLowerCase();
                  const color = lvl === "critical" || lvl === "at_limit" ? "red" : lvl === "warning" ? "orange" : "green";
                  return <Tag color={color}>{lvl}</Tag>;
                },
              },
            ]}
            pagination={{ pageSize: 20 }}
          />
        </TabPane>

        <TabPane tab="Guardrail Alerts" key="guardrail-alerts">
          <Table
            rowKey={(r: any, idx?: number) => `${r.id || idx || ""}`}
            loading={alertsLoading}
            dataSource={guardrailAlerts}
            columns={[
              { title: "Time", dataIndex: "changed_at", key: "changed_at" },
              { title: "Guard", dataIndex: "guard_type", key: "guard_type" },
              {
                title: "Alert",
                key: "alert",
                render: (_: any, r: any) => {
                  const action = String(r.action || "").toLowerCase();
                  const color = action === "delete" || action === "disabled" || action === "disable" ? "red" : "orange";
                  return <Tag color={color}>{action || r.alert_type || "alert"}</Tag>;
                },
              },
              { title: "Changed By", dataIndex: "changed_by", key: "changed_by" },
              { title: "Type", dataIndex: "alert_type", key: "alert_type" },
            ]}
            pagination={{ pageSize: 20 }}
          />
        </TabPane>

        <TabPane tab="Copilot Audit" key="copilot-audit">
          <Table
            rowKey={(r: any) => r.id}
            loading={auditLoading}
            dataSource={auditLogs}
            columns={[
              { title: "Time", dataIndex: "created_at", key: "created_at" },
              { title: "Event", dataIndex: "event_type", key: "event_type" },
              {
                title: "Severity",
                dataIndex: "severity",
                key: "severity",
                render: (value: string) => {
                  const v = String(value || "info").toLowerCase();
                  const color = v === "error" || v === "critical" ? "red" : v === "warning" ? "orange" : "blue";
                  return <Tag color={color}>{v}</Tag>;
                },
              },
              { title: "Action", dataIndex: "action", key: "action" },
              { title: "Resource", key: "resource", render: (_: any, r: any) => `${r.resource_type || "-"}:${r.resource_id || "-"}` },
              { title: "Actor", dataIndex: "actor_email", key: "actor_email" },
              { title: "Message", dataIndex: "message", key: "message" },
            ]}
            pagination={{ pageSize: 20 }}
          />
        </TabPane>

        <TabPane tab="Support Activity" key="support">
          <Table
            rowKey={(r: any) => r.id}
            loading={ticketsLoading}
            dataSource={tickets}
            columns={[
              { title: "Subject", dataIndex: "subject", key: "subject" },
              {
                title: "Status",
                dataIndex: "status",
                key: "status",
                render: (v: string) => <Tag color={["OPEN", "IN_PROGRESS", "PENDING"].includes(v) ? "blue" : "default"}>{v}</Tag>,
              },
              { title: "Priority", dataIndex: "priority", key: "priority", render: (v: string) => <Tag>{v}</Tag> },
              { title: "Updated", dataIndex: "updated_at", key: "updated_at" },
            ]}
            pagination={{ pageSize: 20 }}
          />
        </TabPane>
      </Tabs>
    </div>
  );
};

export default CopilotObservabilityPage;
