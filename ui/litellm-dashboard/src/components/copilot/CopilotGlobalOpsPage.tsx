"use client";

import React, { useMemo, useState } from "react";
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
  Statistic,
  Switch,
  Table,
  Tag,
  message,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";
import {
  useCopilotGlobalBulkDeleteTemplates,
  useCopilotGlobalBulkUpdateTickets,
  useCopilotGlobalOpsSummary,
} from "@/app/(dashboard)/hooks/copilot/useCopilotGlobalOps";

const ticketStatusOptions = [
  { label: "Open", value: "OPEN" },
  { label: "In Progress", value: "IN_PROGRESS" },
  { label: "Pending", value: "PENDING" },
  { label: "Resolved", value: "RESOLVED" },
  { label: "Closed", value: "CLOSED" },
  { label: "Cancelled", value: "CANCELLED" },
];

const ticketPriorityOptions = [
  { label: "Low", value: "LOW" },
  { label: "Medium", value: "MEDIUM" },
  { label: "Urgent", value: "URGENT" },
  { label: "Important", value: "IMPORTANT" },
];

const templateTypeOptions = [
  { label: "Email", value: "EMAIL" },
  { label: "SMS", value: "SMS" },
  { label: "In App", value: "IN_APP" },
];

const CopilotGlobalOpsPage: React.FC = () => {
  const { isSuperAdmin } = useAuthorized();
  const { data: accountData, isLoading: accountsLoading } = useCopilotAccounts();
  const accounts = accountData?.accounts || [];
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [ticketBulkForm] = Form.useForm();
  const [templateBulkForm] = Form.useForm();
  const [lastActionSummary, setLastActionSummary] = useState<string>("");

  const summaryQuery = useCopilotGlobalOpsSummary({
    account_ids: selectedAccountIds.length > 0 ? selectedAccountIds : undefined,
  });
  const bulkUpdateTickets = useCopilotGlobalBulkUpdateTickets();
  const bulkDeleteTemplates = useCopilotGlobalBulkDeleteTemplates();

  const totals = summaryQuery.data?.data?.totals || {};
  const byAccount = summaryQuery.data?.data?.by_account || [];

  const accountOptions = useMemo(
    () =>
      accounts.map((a: any) => ({
        label: `${a.account_name} (${a.status})`,
        value: a.account_id,
      })),
    [accounts],
  );

  if (!isSuperAdmin) {
    return (
      <Alert
        type="warning"
        showIcon
        message="Super admin only"
        description="Global Copilot operations are only available to super admins."
      />
    );
  }

  const onRunTicketBulkAction = async () => {
    const values = await ticketBulkForm.validateFields();
    if (!values.status && !values.priority && values.assigned_to === undefined) {
      message.warning("Set status, priority, or assigned_to for the bulk action.");
      return;
    }
    const payload = {
      account_ids: values.account_ids || selectedAccountIds,
      current_status: values.current_status || undefined,
      search_text: values.search_text || undefined,
      status: values.status || undefined,
      priority: values.priority || undefined,
      assigned_to: values.assigned_to,
      limit: values.limit || 1000,
    };
    const result = await bulkUpdateTickets.mutateAsync(payload);
    const stats = result?.data || {};
    setLastActionSummary(
      `Ticket bulk action: matched=${stats.matched_count || 0}, updated=${stats.updated_count || 0}`,
    );
    message.success("Global ticket bulk action completed.");
    summaryQuery.refetch();
  };

  const onRunTemplateBulkDelete = async () => {
    const values = await templateBulkForm.validateFields();
    const payload = {
      account_ids: values.account_ids || selectedAccountIds,
      event_ids: values.event_ids
        ? String(values.event_ids)
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean)
        : undefined,
      types: values.types || undefined,
      template_ids: values.template_ids
        ? String(values.template_ids)
            .split(",")
            .map((v) => v.trim())
            .filter(Boolean)
        : undefined,
      limit: values.limit || 1000,
      dry_run: Boolean(values.dry_run),
    };
    const result = await bulkDeleteTemplates.mutateAsync(payload);
    const stats = result?.data || {};
    const verb = stats.dry_run ? "previewed" : "deleted";
    setLastActionSummary(
      `Template bulk action: matched=${stats.matched_count || 0}, ${verb}=${stats.deleted_count || 0}`,
    );
    message.success(stats.dry_run ? "Dry run complete." : "Global template delete completed.");
    summaryQuery.refetch();
  };

  return (
    <div style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Global Copilot Operations"
        description="Cross-account summary and bulk operations for support tickets and notification templates."
      />

      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          mode="multiple"
          style={{ minWidth: 420 }}
          placeholder="Filter to specific accounts (leave empty for all)"
          optionFilterProp="label"
          showSearch
          loading={accountsLoading}
          value={selectedAccountIds}
          onChange={(values) => setSelectedAccountIds(values)}
          options={accountOptions}
        />
        <Button icon={<ReloadOutlined />} onClick={() => summaryQuery.refetch()} loading={summaryQuery.isLoading}>
          Refresh
        </Button>
      </Space>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="Accounts" value={totals.account_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="Open Tickets" value={totals.open_ticket_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="Pending Invites" value={totals.pending_invite_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="Budget Alerts" value={totals.budget_alert_count || 0} /></Card></Col>
      </Row>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="Credits Allocated" value={totals.credits_allocated || 0} precision={2} /></Card></Col>
        <Col span={6}><Card><Statistic title="Credits Used" value={totals.credits_used || 0} precision={2} /></Card></Col>
        <Col span={6}><Card><Statistic title="Notification Templates" value={totals.notification_template_count || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="Guardrail Audits (7d)" value={totals.guardrail_audit_7d_count || 0} /></Card></Col>
      </Row>

      <Card title="Per-Account Operational Summary" style={{ marginBottom: 16 }}>
        <Table
          rowKey="account_id"
          loading={summaryQuery.isLoading}
          dataSource={byAccount}
          pagination={{ pageSize: 20 }}
          columns={[
            { title: "Account", dataIndex: "account_name", key: "account_name" },
            { title: "Status", dataIndex: "account_status", key: "account_status" },
            { title: "Open Tickets", dataIndex: "open_ticket_count", key: "open_ticket_count" },
            { title: "Templates", dataIndex: "notification_template_count", key: "notification_template_count" },
            { title: "Budget Alerts", dataIndex: "budget_alert_count", key: "budget_alert_count" },
            { title: "Users", dataIndex: "user_count", key: "user_count" },
            { title: "Teams", dataIndex: "team_count", key: "team_count" },
            {
              title: "Model Mode",
              key: "model_selection_mode",
              render: (_: any, r: any) => (
                <Tag color={r.model_selection_mode === "allowlist" ? "blue" : "green"}>
                  {r.model_selection_mode}
                </Tag>
              ),
            },
          ]}
        />
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card title="Bulk Ticket Action">
            <Form form={ticketBulkForm} layout="vertical">
              <Form.Item label="Account Scope" name="account_ids">
                <Select mode="multiple" options={accountOptions} optionFilterProp="label" showSearch />
              </Form.Item>
              <Form.Item label="Current Status Filter" name="current_status">
                <Select allowClear options={ticketStatusOptions} />
              </Form.Item>
              <Form.Item label="Search Text Filter" name="search_text">
                <Input allowClear placeholder="subject or description contains..." />
              </Form.Item>
              <Form.Item label="Set Status" name="status">
                <Select allowClear options={ticketStatusOptions} />
              </Form.Item>
              <Form.Item label="Set Priority" name="priority">
                <Select allowClear options={ticketPriorityOptions} />
              </Form.Item>
              <Form.Item label="Set Assigned To (user id/email/string)" name="assigned_to">
                <Input allowClear placeholder="leave blank to skip assignment update" />
              </Form.Item>
              <Form.Item label="Limit" name="limit" initialValue={1000}>
                <InputNumber min={1} max={5000} style={{ width: "100%" }} />
              </Form.Item>
              <Button type="primary" onClick={onRunTicketBulkAction} loading={bulkUpdateTickets.isPending}>
                Apply Ticket Bulk Action
              </Button>
            </Form>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="Bulk Template Delete">
            <Form form={templateBulkForm} layout="vertical" initialValues={{ dry_run: true, limit: 1000 }}>
              <Form.Item label="Account Scope" name="account_ids">
                <Select mode="multiple" options={accountOptions} optionFilterProp="label" showSearch />
              </Form.Item>
              <Form.Item label="Event IDs (comma-separated)" name="event_ids">
                <Input allowClear placeholder="event_a,event_b" />
              </Form.Item>
              <Form.Item label="Template Types" name="types">
                <Select mode="multiple" options={templateTypeOptions} />
              </Form.Item>
              <Form.Item label="Template DB IDs (comma-separated)" name="template_ids">
                <Input allowClear placeholder="uuid1,uuid2" />
              </Form.Item>
              <Form.Item label="Limit" name="limit">
                <InputNumber min={1} max={5000} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item label="Dry Run" name="dry_run" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Button danger type="primary" onClick={onRunTemplateBulkDelete} loading={bulkDeleteTemplates.isPending}>
                Run Template Bulk Delete
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>

      {lastActionSummary ? (
        <Alert
          style={{ marginTop: 16 }}
          type="success"
          showIcon
          message={lastActionSummary}
        />
      ) : null}
    </div>
  );
};

export default CopilotGlobalOpsPage;
