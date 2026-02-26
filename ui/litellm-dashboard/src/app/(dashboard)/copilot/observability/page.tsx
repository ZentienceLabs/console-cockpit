"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Tabs, Tag, message } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import { observabilityApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(v: string | undefined | null): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return String(v);
  }
}

function formatUsd(v: number | undefined | null): string {
  if (v == null) return "—";
  return `$${Number(v).toFixed(2)}`;
}

const SEVERITY_COLORS: Record<string, string> = {
  info: "blue",
  warning: "orange",
  critical: "red",
};

const STATUS_COLORS: Record<string, string> = {
  open: "red",
  acknowledged: "orange",
  resolved: "green",
};

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CopilotObservabilityPage() {
  const { accessToken } = useAuthorized();

  const [summary, setSummary] = useState<any>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const [rollups, setRollups] = useState<any[]>([]);
  const [rollupsLoading, setRollupsLoading] = useState(false);

  const [alerts, setAlerts] = useState<any[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);

  // ---- data loaders -------------------------------------------------------

  const loadSummary = useCallback(async () => {
    if (!accessToken) return;
    setSummaryLoading(true);
    try {
      setSummary(await observabilityApi.getSummary(accessToken));
    } catch {
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, [accessToken]);

  const loadAuditLogs = useCallback(async () => {
    if (!accessToken) return;
    setAuditLoading(true);
    try {
      const d = await observabilityApi.listAuditLogs(accessToken);
      setAuditLogs(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load audit logs");
    } finally {
      setAuditLoading(false);
    }
  }, [accessToken]);

  const loadRollups = useCallback(async () => {
    if (!accessToken) return;
    setRollupsLoading(true);
    try {
      const d = await observabilityApi.getUsageRollups(accessToken);
      const arr = Array.isArray(d) ? d : (d as any)?.rollups ?? [];
      setRollups(Array.isArray(arr) ? arr : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load usage rollups");
    } finally {
      setRollupsLoading(false);
    }
  }, [accessToken]);

  const loadAlerts = useCallback(async () => {
    if (!accessToken) return;
    setAlertsLoading(true);
    try {
      const d = await observabilityApi.listAlerts(accessToken);
      setAlerts(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load alerts");
    } finally {
      setAlertsLoading(false);
    }
  }, [accessToken]);

  // ---- effects & refresh --------------------------------------------------

  useEffect(() => {
    loadSummary();
    loadAuditLogs();
    loadRollups();
    loadAlerts();
  }, [loadSummary, loadAuditLogs, loadRollups, loadAlerts]);

  const handleRefresh = () => {
    loadSummary();
    loadAuditLogs();
    loadRollups();
    loadAlerts();
  };

  // ---- render -------------------------------------------------------------

  return (
    <CopilotPageShell
      title="Observability"
      subtitle="Audit logs, usage rollups, and alert monitoring."
      icon={<EyeOutlined />}
      onRefresh={handleRefresh}
    >
      {/* Stats Row */}
      <CopilotStatsRow
        stats={[
          {
            title: "Total Events",
            value: summary?.total_events ?? 0,
            loading: summaryLoading,
          },
          {
            title: "Active Alerts",
            value: summary?.active_alerts ?? 0,
            loading: summaryLoading,
          },
          {
            title: "Total Usage Credits",
            value: summary?.total_usage_credits ?? 0,
            loading: summaryLoading,
          },
          {
            title: "Last Activity",
            value: summary?.last_activity
              ? formatTimestamp(summary.last_activity)
              : "—",
            loading: summaryLoading,
          },
        ]}
      />

      {/* Tabs */}
      <Tabs
        defaultActiveKey="audit"
        items={[
          // ---- Audit Logs -------------------------------------------------
          {
            key: "audit",
            label: `Audit Logs (${auditLogs.length})`,
            children: (
              <CopilotCrudTable
                dataSource={auditLogs}
                rowKey="log_id"
                loading={auditLoading}
                searchFields={["action", "user_id", "resource_type"]}
                showActions={false}
                expandable={{
                  expandedRowRender: (record: any) => (
                    <pre
                      style={{
                        fontFamily: "monospace",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-all",
                        margin: 0,
                        padding: 12,
                        background: "#f5f5f5",
                        borderRadius: 4,
                      }}
                    >
                      {JSON.stringify(record, null, 2)}
                    </pre>
                  ),
                }}
                columns={[
                  {
                    title: "Timestamp",
                    dataIndex: "timestamp",
                    key: "timestamp",
                    width: 190,
                    render: (v: string) => formatTimestamp(v),
                  },
                  {
                    title: "Event Type",
                    dataIndex: "event_type",
                    key: "event_type",
                    width: 140,
                    render: (v: string) =>
                      v ? <Tag color="blue">{v}</Tag> : "—",
                  },
                  {
                    title: "Actor",
                    dataIndex: "user_id",
                    key: "user_id",
                    ellipsis: true,
                    width: 180,
                  },
                  {
                    title: "Summary",
                    key: "summary",
                    ellipsis: true,
                    render: (_: unknown, record: any) => {
                      const parts = [record.action, record.resource_type].filter(Boolean);
                      return parts.length > 0 ? parts.join(" on ") : "—";
                    },
                  },
                ]}
              />
            ),
          },

          // ---- Usage Rollups -----------------------------------------------
          {
            key: "rollups",
            label: `Usage Rollups (${rollups.length})`,
            children: (
              <CopilotCrudTable
                dataSource={rollups}
                rowKey="period"
                loading={rollupsLoading}
                searchFields={["period", "scope_type"]}
                showActions={false}
                columns={[
                  {
                    title: "Period",
                    dataIndex: "period",
                    key: "period",
                  },
                  {
                    title: "Scope Type",
                    dataIndex: "scope_type",
                    key: "scope_type",
                    render: (v: string) =>
                      v ? <Tag>{v}</Tag> : "—",
                  },
                  {
                    title: "Scope ID",
                    dataIndex: "scope_id",
                    key: "scope_id",
                    ellipsis: true,
                  },
                  {
                    title: "Credits Used",
                    dataIndex: "credits_used",
                    key: "credits_used",
                  },
                  {
                    title: "Raw Cost (USD)",
                    dataIndex: "raw_cost_usd",
                    key: "raw_cost_usd",
                    render: (v: number) => formatUsd(v),
                  },
                  {
                    title: "Request Count",
                    dataIndex: "request_count",
                    key: "request_count",
                  },
                ]}
              />
            ),
          },

          // ---- Alerts ------------------------------------------------------
          {
            key: "alerts",
            label: `Alerts (${alerts.length})`,
            children: (
              <CopilotCrudTable
                dataSource={alerts}
                rowKey="alert_id"
                loading={alertsLoading}
                searchFields={["alert_type", "severity", "status"]}
                showActions={false}
                columns={[
                  {
                    title: "Alert ID",
                    dataIndex: "alert_id",
                    key: "alert_id",
                    ellipsis: true,
                    width: 160,
                  },
                  {
                    title: "Alert Type",
                    dataIndex: "alert_type",
                    key: "alert_type",
                    width: 140,
                    render: (v: string) =>
                      v ? <Tag color="purple">{v}</Tag> : "—",
                  },
                  {
                    title: "Severity",
                    dataIndex: "severity",
                    key: "severity",
                    width: 110,
                    render: (v: string) =>
                      v ? (
                        <Tag color={SEVERITY_COLORS[v] ?? "default"}>{v}</Tag>
                      ) : (
                        "—"
                      ),
                  },
                  {
                    title: "Message",
                    dataIndex: "message",
                    key: "message",
                    ellipsis: true,
                  },
                  {
                    title: "Status",
                    dataIndex: "status",
                    key: "status",
                    width: 130,
                    render: (v: string) =>
                      v ? (
                        <Tag color={STATUS_COLORS[v] ?? "default"}>{v}</Tag>
                      ) : (
                        "—"
                      ),
                  },
                  {
                    title: "Created At",
                    dataIndex: "created_at",
                    key: "created_at",
                    width: 190,
                    render: (v: string) => formatTimestamp(v),
                  },
                ]}
              />
            ),
          },
        ]}
      />
    </CopilotPageShell>
  );
}
