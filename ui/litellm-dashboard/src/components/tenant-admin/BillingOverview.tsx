"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Table,
  Card,
  Statistic,
  Row,
  Col,
  Progress,
  Button,
  Typography,
  Tag,
  message,
} from "antd";
import { DownloadOutlined, ReloadOutlined } from "@ant-design/icons";

const { Text } = Typography;

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

interface BudgetSummary {
  account_id: string;
  scope_type: string;
  scope_id: string;
  total_allocated: number;
  total_used: number;
  total_overflow_used: number;
  total_limit: number;
  usage_pct: number;
  latest_cycle_end: string;
}

export default function BillingOverview() {
  const [data, setData] = useState<BudgetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const accessToken = getCookie("token") || "";

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/copilot/budgets/summary", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const result = await response.json();
        setData(result.data || []);
      } else {
        message.error("Failed to load budget summary");
      }
    } catch {
      message.error("Error loading budget summary");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const totalAllocated = data.reduce((sum, r) => sum + (r.total_allocated || 0), 0);
  const totalUsed = data.reduce((sum, r) => sum + (r.total_used || 0), 0);
  const totalRemaining = totalAllocated - totalUsed;
  const uniqueAccounts = new Set(data.map((r) => r.account_id)).size;

  const handleExportCSV = () => {
    if (data.length === 0) {
      message.warning("No data to export");
      return;
    }
    const headers = [
      "Account ID",
      "Scope Type",
      "Scope ID",
      "Allocated",
      "Used",
      "Remaining",
      "Usage %",
      "Next Cycle End",
    ];
    const rows = data.map((r) => [
      r.account_id,
      r.scope_type,
      r.scope_id,
      r.total_allocated,
      r.total_used,
      r.total_allocated - r.total_used,
      (r.usage_pct || 0).toFixed(1),
      r.latest_cycle_end,
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `billing_overview_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const columns = [
    {
      title: "Account ID",
      dataIndex: "account_id",
      key: "account_id",
      ellipsis: true,
      width: 200,
    },
    {
      title: "Scope",
      key: "scope",
      render: (_: any, record: BudgetSummary) => (
        <>
          <Tag color="blue">{record.scope_type}</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.scope_id}
          </Text>
        </>
      ),
    },
    {
      title: "Allocated",
      dataIndex: "total_allocated",
      key: "allocated",
      render: (v: number) => `$${(v || 0).toFixed(2)}`,
      sorter: (a: BudgetSummary, b: BudgetSummary) => a.total_allocated - b.total_allocated,
    },
    {
      title: "Used",
      dataIndex: "total_used",
      key: "used",
      render: (v: number) => `$${(v || 0).toFixed(2)}`,
      sorter: (a: BudgetSummary, b: BudgetSummary) => a.total_used - b.total_used,
    },
    {
      title: "Remaining",
      key: "remaining",
      render: (_: any, record: BudgetSummary) => {
        const remaining = (record.total_allocated || 0) - (record.total_used || 0);
        return (
          <Text type={remaining < 0 ? "danger" : undefined}>
            ${remaining.toFixed(2)}
          </Text>
        );
      },
    },
    {
      title: "Usage",
      key: "usage",
      width: 180,
      render: (_: any, record: BudgetSummary) => {
        const pct = Math.min(100, record.usage_pct || 0);
        const status = pct >= 90 ? "exception" : pct >= 70 ? "normal" : "success";
        return <Progress percent={Math.round(pct)} status={status} size="small" />;
      },
      sorter: (a: BudgetSummary, b: BudgetSummary) => {
        return (a.usage_pct || 0) - (b.usage_pct || 0);
      },
    },
    {
      title: "Cycle",
      key: "cycle",
      render: (_: any, record: BudgetSummary) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          Next reset:{" "}
          {record.latest_cycle_end
            ? new Date(record.latest_cycle_end).toLocaleDateString()
            : "-"}
        </Text>
      ),
    },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="Accounts with Budgets" value={uniqueAccounts} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Allocated"
              value={totalAllocated}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Used"
              value={totalUsed}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Remaining"
              value={totalRemaining}
              precision={2}
              prefix="$"
              valueStyle={totalRemaining < 0 ? { color: "#cf1322" } : { color: "#3f8600" }}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 16,
          }}
        >
          <Text strong>Budget Summary (All Accounts)</Text>
          <div>
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchSummary}
              style={{ marginRight: 8 }}
            >
              Refresh
            </Button>
            <Button icon={<DownloadOutlined />} onClick={handleExportCSV}>
              Export CSV
            </Button>
          </div>
        </div>
        <Table
          dataSource={data}
          columns={columns}
          rowKey={(record) =>
            `${record.account_id}-${record.scope_type}-${record.scope_id}`
          }
          loading={loading}
          pagination={{ pageSize: 20 }}
        />
      </Card>
    </div>
  );
}
