"use client";

import React, { useMemo, useState } from "react";
import { Button, Card, Col, Drawer, Form, Input, Modal, Row, Select, Space, Statistic, Table, Tag, message } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import {
  useCopilotSupportTickets,
  useCopilotSupportTicketSummary,
  useBulkUpdateCopilotSupportTickets,
  useCreateCopilotSupportTicket,
  useDeleteCopilotSupportTicket,
  useUpdateCopilotSupportTicket,
} from "@/app/(dashboard)/hooks/copilot/useCopilotSupportTickets";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

const { TextArea } = Input;

const statusOptions = [
  { label: "Open", value: "OPEN" },
  { label: "In Progress", value: "IN_PROGRESS" },
  { label: "Pending", value: "PENDING" },
  { label: "Resolved", value: "RESOLVED" },
  { label: "Closed", value: "CLOSED" },
  { label: "Cancelled", value: "CANCELLED" },
];

const priorityOptions = [
  { label: "Low", value: "LOW" },
  { label: "Medium", value: "MEDIUM" },
  { label: "Urgent", value: "URGENT" },
  { label: "Important", value: "IMPORTANT" },
];

const statusColorMap: Record<string, string> = {
  OPEN: "blue",
  IN_PROGRESS: "processing",
  PENDING: "gold",
  RESOLVED: "green",
  CLOSED: "default",
  CANCELLED: "red",
};

const priorityColorMap: Record<string, string> = {
  LOW: "default",
  MEDIUM: "gold",
  URGENT: "red",
  IMPORTANT: "orange",
};

const CopilotSupportTicketsPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>(accountId || undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [priorityFilter, setPriorityFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState<string | undefined>();
  const [bulkStatus, setBulkStatus] = useState<string | undefined>();
  const [bulkPriority, setBulkPriority] = useState<string | undefined>();
  const [selectedTicketIds, setSelectedTicketIds] = useState<React.Key[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingTicket, setEditingTicket] = useState<any>(null);
  const [form] = Form.useForm();

  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();
  const { data: ticketsData, isLoading } = useCopilotSupportTickets({
    account_id: accountFilter,
    status: statusFilter,
    priority: priorityFilter,
    search_text: searchText,
    include_user_profile: true,
    include_assigned_to: true,
  });
  const { data: summaryData } = useCopilotSupportTicketSummary({ account_id: accountFilter });
  const createTicket = useCreateCopilotSupportTicket();
  const updateTicket = useUpdateCopilotSupportTicket();
  const deleteTicket = useDeleteCopilotSupportTicket();
  const bulkUpdate = useBulkUpdateCopilotSupportTickets();

  const tickets = ticketsData?.data ?? [];
  const accounts = accountData?.accounts ?? [];
  const summary = summaryData?.data;
  const ensureAccountForSuperAdminWrite = () => {
    if (isSuperAdmin && !accountFilter) {
      message.warning("Select an account before creating or updating support tickets.");
      return false;
    }
    return true;
  };

  const stats = useMemo(() => {
    if (summary?.totals) {
      return {
        open: Number(summary.totals.active || 0),
        in_progress: tickets.filter((t: any) => t.status === "IN_PROGRESS").length,
        resolved: tickets.filter((t: any) => t.status === "RESOLVED").length,
        urgent: Number(summary.totals.urgent || 0),
      };
    }
    return tickets.reduce(
      (acc: { open: number; in_progress: number; resolved: number; urgent: number }, ticket: any) => {
        if (ticket.status === "OPEN") acc.open += 1;
        if (ticket.status === "IN_PROGRESS") acc.in_progress += 1;
        if (ticket.status === "RESOLVED") acc.resolved += 1;
        if (ticket.priority === "URGENT") acc.urgent += 1;
        return acc;
      },
      { open: 0, in_progress: 0, resolved: 0, urgent: 0 },
    );
  }, [tickets]);

  const handleSave = async () => {
    if (!ensureAccountForSuperAdminWrite()) {
      return;
    }
    try {
      const values = await form.validateFields();
      if (editingTicket) {
        await updateTicket.mutateAsync({ id: editingTicket.id, data: values, account_id: accountFilter });
        message.success("Support ticket updated");
      } else {
        await createTicket.mutateAsync({ data: values, account_id: accountFilter });
        message.success("Support ticket created");
      }
      setDrawerOpen(false);
      setEditingTicket(null);
      form.resetFields();
    } catch {
      // Form validation or API error is surfaced by antd/NotificationsManager.
    }
  };

  const handleBulkUpdate = async () => {
    if (!ensureAccountForSuperAdminWrite()) {
      return;
    }
    if (selectedTicketIds.length === 0) {
      message.warning("Select at least one ticket.");
      return;
    }
    if (!bulkStatus && !bulkPriority) {
      message.warning("Choose a bulk status and/or priority.");
      return;
    }
    await bulkUpdate.mutateAsync({
      ticket_ids: selectedTicketIds.map((id) => String(id)),
      status: bulkStatus,
      priority: bulkPriority,
      account_id: accountFilter,
    });
    message.success("Bulk ticket update applied.");
    setSelectedTicketIds([]);
  };

  const columns = [
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
      render: (value: string) => <Tag color={statusColorMap[value] || "default"}>{value}</Tag>,
    },
    {
      title: "Priority",
      dataIndex: "priority",
      key: "priority",
      render: (value: string) => <Tag color={priorityColorMap[value] || "default"}>{value}</Tag>,
    },
    {
      title: "Requester",
      key: "user_profile",
      render: (_: any, record: any) => record.userProfile?.displayName || record.user_profile_id || "-",
    },
    {
      title: "Assigned",
      key: "assigned_to",
      render: (_: any, record: any) => record.assignedTo?.displayName || record.assigned_to || "-",
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (value: string) => (value ? new Date(value).toLocaleString() : "-"),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingTicket(record);
              form.setFieldsValue({
                user_profile_id: record.user_profile_id,
                subject: record.subject,
                description: record.description,
                status: record.status,
                priority: record.priority,
                assigned_to: record.assigned_to,
              });
              setDrawerOpen(true);
            }}
          />
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            onClick={() => {
              Modal.confirm({
                title: "Delete Ticket",
                content: `Delete "${record.subject}"?`,
                onOk: async () => {
                  if (!ensureAccountForSuperAdminWrite()) {
                    return;
                  }
                  await deleteTicket.mutateAsync({ id: record.id, account_id: accountFilter });
                  message.success("Support ticket deleted");
                },
              });
            }}
          />
        </Space>
      ),
    },
  ];

  return (
    <div style={{ width: "100%" }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="Open" value={stats.open} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="In Progress" value={stats.in_progress} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="Resolved" value={stats.resolved} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="Urgent" value={stats.urgent} valueStyle={{ color: stats.urgent > 0 ? "#cf1322" : undefined }} /></Card>
        </Col>
      </Row>

      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", gap: 12 }}>
        <Space wrap>
          {isSuperAdmin && (
            <Select
              placeholder="Filter by account"
              allowClear
              style={{ minWidth: 280 }}
              loading={accountLoading}
              value={selectedAccountId}
              onChange={(value) => setSelectedAccountId(value)}
              options={accounts.map((a: any) => ({
                label: `${a.account_name} (${a.status})`,
                value: a.account_id,
              }))}
            />
          )}
          <Select
            placeholder="Filter by status"
            allowClear
            options={statusOptions}
            style={{ minWidth: 180 }}
            onChange={(value) => setStatusFilter(value)}
          />
          <Select
            placeholder="Filter by priority"
            allowClear
            options={priorityOptions}
            style={{ minWidth: 180 }}
            onChange={(value) => setPriorityFilter(value)}
          />
          <Input
            placeholder="Search subject or description"
            allowClear
            style={{ minWidth: 260 }}
            onChange={(e) => setSearchText(e.target.value || undefined)}
          />
          <Select
            placeholder="Bulk status"
            allowClear
            options={statusOptions}
            style={{ minWidth: 180 }}
            value={bulkStatus}
            onChange={(value) => setBulkStatus(value)}
          />
          <Select
            placeholder="Bulk priority"
            allowClear
            options={priorityOptions}
            style={{ minWidth: 180 }}
            value={bulkPriority}
            onChange={(value) => setBulkPriority(value)}
          />
          <Button onClick={handleBulkUpdate} loading={bulkUpdate.isPending}>
            Bulk Update Selected
          </Button>
        </Space>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            if (!ensureAccountForSuperAdminWrite()) {
              return;
            }
            setEditingTicket(null);
            form.resetFields();
            form.setFieldsValue({ status: "OPEN", priority: "MEDIUM" });
            setDrawerOpen(true);
          }}
        >
          Create Ticket
        </Button>
      </div>

      <Table
        dataSource={tickets}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        pagination={{ pageSize: 20 }}
        rowSelection={{
          selectedRowKeys: selectedTicketIds,
          onChange: (keys) => setSelectedTicketIds(keys),
        }}
      />

      <Drawer
        title={editingTicket ? "Edit Support Ticket" : "Create Support Ticket"}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setEditingTicket(null);
        }}
        width={560}
        extra={
          <Button type="primary" onClick={handleSave} loading={createTicket.isPending || updateTicket.isPending}>
            {editingTicket ? "Update" : "Create"}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="user_profile_id" label="Requester User ID">
            <Input placeholder="Optional copilot user profile id" />
          </Form.Item>
          <Form.Item name="subject" label="Subject" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description" rules={[{ required: true }]}>
            <TextArea rows={6} />
          </Form.Item>
          <Form.Item name="status" label="Status" rules={[{ required: true }]}>
            <Select options={statusOptions} />
          </Form.Item>
          <Form.Item name="priority" label="Priority" rules={[{ required: true }]}>
            <Select options={priorityOptions} />
          </Form.Item>
          <Form.Item name="assigned_to" label="Assigned User ID">
            <Input placeholder="Optional copilot user id for assignment" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default CopilotSupportTicketsPage;
