"use client";

import React, { useMemo } from "react";
import { Alert, Card, Col, Row, Select, Space, Statistic, Table, Tag } from "antd";
import {
  useCopilotBudgetSummary,
} from "@/app/(dashboard)/hooks/copilot/useCopilotBudgets";
import {
  useCopilotGroups,
  useCopilotInvites,
  useCopilotMemberships,
  useCopilotTeams,
} from "@/app/(dashboard)/hooks/copilot/useCopilotOverview";
import { useCopilotSupportTickets } from "@/app/(dashboard)/hooks/copilot/useCopilotSupportTickets";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";

const CopilotOverviewPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = React.useState<string | undefined>(accountId || undefined);
  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();

  const { data: budgetSummaryData, isLoading: budgetLoading } = useCopilotBudgetSummary({ account_id: accountFilter });
  const { data: membershipsData, isLoading: membershipsLoading } = useCopilotMemberships({
    account_id: accountFilter,
    is_active: true,
    limit: 1000,
    offset: 0,
  });
  const { data: groupsData, isLoading: groupsLoading } = useCopilotGroups({ account_id: accountFilter, limit: 500, offset: 0 });
  const { data: teamsData, isLoading: teamsLoading } = useCopilotTeams({ account_id: accountFilter, limit: 1000, offset: 0 });
  const { data: invitesData, isLoading: invitesLoading } = useCopilotInvites({ account_id: accountFilter, limit: 1000, offset: 0 });
  const { data: ticketsData, isLoading: ticketsLoading } = useCopilotSupportTickets({ account_id: accountFilter, limit: 200, offset: 0 });
  const accounts = accountData?.accounts || [];

  const summaryRows = budgetSummaryData?.data ?? [];
  const memberships = membershipsData?.data ?? [];
  const groups = groupsData?.data ?? [];
  const teams = teamsData?.data ?? [];
  const invites = invitesData?.data ?? [];
  const tickets = ticketsData?.data ?? [];

  const stats = useMemo(() => {
    const totalAllocated = summaryRows.reduce((sum: number, row: any) => sum + Number(row.total_allocated || 0), 0);
    const totalUsed = summaryRows.reduce((sum: number, row: any) => sum + Number(row.total_used || 0), 0);
    const accountCount = new Set(summaryRows.map((row: any) => String(row.account_id || ""))).size || 1;
    const openTicketCount = tickets.filter((t: any) => t.status === "OPEN" || t.status === "IN_PROGRESS").length;
    const pendingInviteCount = invites.filter((i: any) => i.status === "PENDING").length;
    return {
      totalAllocated,
      totalUsed,
      accountCount,
      openTicketCount,
      pendingInviteCount,
    };
  }, [summaryRows, tickets, invites]);

  const recentTickets = useMemo(() => {
    return [...tickets]
      .sort((a: any, b: any) => {
        const at = new Date(a.created_at || 0).getTime();
        const bt = new Date(b.created_at || 0).getTime();
        return bt - at;
      })
      .slice(0, 8);
  }, [tickets]);

  const recentInvites = useMemo(() => {
    return [...invites]
      .sort((a: any, b: any) => {
        const at = new Date(a.created_at || 0).getTime();
        const bt = new Date(b.created_at || 0).getTime();
        return bt - at;
      })
      .slice(0, 8);
  }, [invites]);

  const ticketColumns = [
    {
      title: "Subject",
      dataIndex: "subject",
      key: "subject",
      ellipsis: true,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (value: string) => (
        <Tag color={value === "OPEN" ? "blue" : value === "IN_PROGRESS" ? "processing" : value === "RESOLVED" ? "green" : "default"}>
          {value}
        </Tag>
      ),
    },
    {
      title: "Priority",
      dataIndex: "priority",
      key: "priority",
      render: (value: string) => <Tag color={value === "URGENT" ? "red" : value === "IMPORTANT" ? "orange" : "default"}>{value}</Tag>,
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (value: string) => (value ? new Date(value).toLocaleString() : "-"),
    },
  ];

  const inviteColumns = [
    { title: "Email", dataIndex: "email", key: "email" },
    {
      title: "Role",
      dataIndex: "role",
      key: "role",
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={value === "PENDING" ? "gold" : value === "ACCEPTED" ? "green" : "default"}>{value}</Tag>,
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (value: string) => (value ? new Date(value).toLocaleString() : "-"),
    },
  ];

  return (
    <div style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Copilot management overview"
        description="Workspace tracking remains outside centralized Copilot, as requested. Teams are shown as workspace proxies for operational monitoring."
      />
      {isSuperAdmin && (
        <div style={{ marginBottom: 16 }}>
          <Select
            placeholder="Filter by account"
            allowClear
            style={{ width: 320 }}
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
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Accounts (In Scope)" value={stats.accountCount} loading={budgetLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Active Members" value={memberships.length} loading={membershipsLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Groups" value={groups.length} loading={groupsLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Teams (Workspace Proxies)" value={teams.length} loading={teamsLoading} /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Open Tickets" value={stats.openTicketCount} loading={ticketsLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Pending Invites" value={stats.pendingInviteCount} loading={invitesLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Credits Allocated" value={stats.totalAllocated} precision={2} loading={budgetLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Card><Statistic title="Credits Used" value={stats.totalUsed} precision={2} loading={budgetLoading} /></Card>
        </Col>
      </Row>

      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Card title="Recent Support Tickets">
          <Table
            dataSource={recentTickets}
            columns={ticketColumns}
            rowKey="id"
            loading={ticketsLoading}
            pagination={false}
          />
        </Card>
        <Card title="Recent Invites">
          <Table
            dataSource={recentInvites}
            columns={inviteColumns}
            rowKey="id"
            loading={invitesLoading}
            pagination={false}
          />
        </Card>
      </Space>
    </div>
  );
};

export default CopilotOverviewPage;
