"use client";

import React, { useState } from "react";
import { Button, Card, Col, Drawer, Form, Input, Modal, Row, Select, Space, Statistic, Table, Tag, message } from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import {
  useBulkDeleteCopilotNotificationTemplates,
  useCopilotNotificationTemplateSummary,
  useCopilotNotificationTemplates,
  useCreateCopilotNotificationTemplate,
  useDeleteCopilotNotificationTemplate,
  useUpdateCopilotNotificationTemplate,
} from "@/app/(dashboard)/hooks/copilot/useCopilotNotificationTemplates";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

const { TextArea } = Input;

const templateTypeOptions = [
  { label: "Email", value: "EMAIL" },
  { label: "Push", value: "PUSH" },
  { label: "SMS", value: "SMS" },
  { label: "In App", value: "IN_APP" },
];

const CopilotNotificationTemplatesPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>(accountId || undefined);
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [eventFilter, setEventFilter] = useState<string | undefined>();
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<React.Key[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<any>(null);
  const [form] = Form.useForm();

  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();
  const { data: templatesData, isLoading } = useCopilotNotificationTemplates({
    account_id: accountFilter,
    type: typeFilter,
    event_id: eventFilter,
  });
  const { data: summaryData } = useCopilotNotificationTemplateSummary({ account_id: accountFilter });
  const createTemplate = useCreateCopilotNotificationTemplate();
  const updateTemplate = useUpdateCopilotNotificationTemplate();
  const deleteTemplate = useDeleteCopilotNotificationTemplate();
  const bulkDeleteTemplates = useBulkDeleteCopilotNotificationTemplates();

  const templates = templatesData?.data ?? [];
  const accounts = accountData?.accounts ?? [];
  const totalTemplates = Number(summaryData?.data?.totals?.total || 0);
  const ensureAccountForSuperAdminWrite = () => {
    if (isSuperAdmin && !accountFilter) {
      message.warning("Select an account before creating or updating notification templates.");
      return false;
    }
    return true;
  };

  const handleSave = async () => {
    if (!ensureAccountForSuperAdminWrite()) {
      return;
    }
    try {
      const values = await form.validateFields();
      if (editingTemplate) {
        await updateTemplate.mutateAsync({ id: editingTemplate.id, data: values, account_id: accountFilter });
        message.success("Notification template updated");
      } else {
        await createTemplate.mutateAsync({ data: values, account_id: accountFilter });
        message.success("Notification template created");
      }
      setDrawerOpen(false);
      setEditingTemplate(null);
      form.resetFields();
    } catch {
      // Form validation or API error is surfaced by antd/NotificationsManager.
    }
  };

  const handleBulkDelete = async () => {
    if (!ensureAccountForSuperAdminWrite()) {
      return;
    }
    if (selectedTemplateIds.length === 0) {
      message.warning("Select at least one template.");
      return;
    }
    await bulkDeleteTemplates.mutateAsync({
      template_ids: selectedTemplateIds.map((id) => String(id)),
      account_id: accountFilter,
    });
    message.success("Selected templates deleted.");
    setSelectedTemplateIds([]);
  };

  const columns = [
    {
      title: "Title",
      dataIndex: "title_line",
      key: "title_line",
    },
    {
      title: "Type",
      dataIndex: "type",
      key: "type",
      render: (value: string) => <Tag color="blue">{value}</Tag>,
    },
    {
      title: "Event",
      dataIndex: "event_id",
      key: "event_id",
      render: (value: string) => value || "-",
    },
    {
      title: "Template ID",
      dataIndex: "template_id",
      key: "template_id",
      render: (value: string) => value || "-",
    },
    {
      title: "Updated",
      dataIndex: "updated_at",
      key: "updated_at",
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
              setEditingTemplate(record);
              form.setFieldsValue({
                template_id: record.template_id,
                title_line: record.title_line,
                template_content: record.template_content,
                event_id: record.event_id,
                type: record.type,
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
                title: "Delete Template",
                content: `Delete "${record.title_line}"?`,
                onOk: async () => {
                  if (!ensureAccountForSuperAdminWrite()) {
                    return;
                  }
                  await deleteTemplate.mutateAsync({ id: record.id, account_id: accountFilter });
                  message.success("Notification template deleted");
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
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="Templates" value={totalTemplates} /></Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card><Statistic title="Filtered Rows" value={templates.length} /></Card>
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
            placeholder="Filter by type"
            allowClear
            options={templateTypeOptions}
            style={{ minWidth: 180 }}
            onChange={(value) => setTypeFilter(value)}
          />
          <Input
            placeholder="Filter by event id"
            allowClear
            style={{ minWidth: 240 }}
            onChange={(e) => setEventFilter(e.target.value || undefined)}
          />
          <Button onClick={handleBulkDelete} loading={bulkDeleteTemplates.isPending}>
            Bulk Delete Selected
          </Button>
        </Space>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            if (!ensureAccountForSuperAdminWrite()) {
              return;
            }
            setEditingTemplate(null);
            form.resetFields();
            form.setFieldsValue({ type: "EMAIL" });
            setDrawerOpen(true);
          }}
        >
          Create Template
        </Button>
      </div>

      <Table
        dataSource={templates}
        columns={columns}
        rowKey="id"
        loading={isLoading}
        pagination={{ pageSize: 20 }}
        rowSelection={{
          selectedRowKeys: selectedTemplateIds,
          onChange: (keys) => setSelectedTemplateIds(keys),
        }}
      />

      <Drawer
        title={editingTemplate ? "Edit Notification Template" : "Create Notification Template"}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setEditingTemplate(null);
        }}
        width={560}
        extra={
          <Button type="primary" onClick={handleSave} loading={createTemplate.isPending || updateTemplate.isPending}>
            {editingTemplate ? "Update" : "Create"}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="template_id" label="Template ID">
            <Input placeholder="Optional stable key (e.g. ticket_created_email)" />
          </Form.Item>
          <Form.Item name="event_id" label="Event ID">
            <Input placeholder="Optional event id (e.g. support_ticket_created)" />
          </Form.Item>
          <Form.Item name="type" label="Template Type" rules={[{ required: true }]}>
            <Select options={templateTypeOptions} />
          </Form.Item>
          <Form.Item name="title_line" label="Title" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="template_content" label="Content" rules={[{ required: true }]}>
            <TextArea rows={8} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default CopilotNotificationTemplatesPage;
