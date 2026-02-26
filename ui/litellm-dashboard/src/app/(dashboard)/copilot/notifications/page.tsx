"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Modal, Form, Input, Select, Tag, Button, Space, message } from "antd";
import { BellOutlined, EyeOutlined, SendOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import CopilotTemplatePreview from "@/components/copilot/CopilotTemplatePreview";
import { notificationApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

const channelColors: Record<string, string> = {
  email: "blue",
  push: "green",
  sms: "orange",
};

const SAMPLE_VARIABLES: Record<string, string> = {
  user_name: "John Doe",
  user_email: "john@example.com",
  account_name: "Acme Corp",
  amount: "$500.00",
  threshold: "80%",
};

export default function CopilotNotificationsPage() {
  const { accessToken } = useAuthorized();

  const [templates, setTemplates] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Create / Edit modal
  const [modal, setModal] = useState<{ open: boolean; editing: any | null }>({
    open: false,
    editing: null,
  });
  const [form] = Form.useForm();

  // Preview modal
  const [previewModal, setPreviewModal] = useState<{
    open: boolean;
    subjectTemplate: string;
    bodyTemplate: string;
  }>({ open: false, subjectTemplate: "", bodyTemplate: "" });

  // Test Send modal
  const [testSendModal, setTestSendModal] = useState<{
    open: boolean;
    templateId: string | null;
  }>({ open: false, templateId: null });
  const [testSendForm] = Form.useForm();
  const [testSending, setTestSending] = useState(false);

  // ---- Data loading ----

  const loadTemplates = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const d = await notificationApi.list(accessToken);
      setTemplates(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load templates");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  // ---- Stats ----

  const emailCount = templates.filter((t) => t.channel === "email").length;
  const enabledCount = templates.filter(
    (t) => t.status === "active" || t.enabled === true,
  ).length;

  // ---- CRUD handlers ----

  const handleSave = async () => {
    if (!accessToken) return;
    try {
      const values = await form.validateFields();

      // Parse metadata JSON if provided
      if (values.metadata && typeof values.metadata === "string") {
        try {
          values.metadata = JSON.parse(values.metadata);
        } catch {
          message.error("Metadata must be valid JSON");
          return;
        }
      }

      // Convert enabled string to boolean
      if (values.enabled !== undefined) {
        values.enabled = values.enabled === "true" || values.enabled === true;
      }

      if (modal.editing) {
        await notificationApi.update(
          accessToken,
          modal.editing.template_id,
          values,
        );
        message.success("Template updated");
      } else {
        await notificationApi.create(accessToken, values);
        message.success("Template created");
      }
      setModal({ open: false, editing: null });
      form.resetFields();
      loadTemplates();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  const handleDelete = async (record: any) => {
    if (!accessToken) return;
    await notificationApi.delete(accessToken, record.template_id);
    loadTemplates();
  };

  const handleEdit = (record: any) => {
    const values = { ...record };
    // Stringify metadata for the TextArea
    if (values.metadata && typeof values.metadata === "object") {
      values.metadata = JSON.stringify(values.metadata, null, 2);
    }
    // Convert enabled boolean to string for Select
    if (values.enabled !== undefined) {
      values.enabled = String(values.enabled);
    }
    form.setFieldsValue(values);
    setModal({ open: true, editing: record });
  };

  // ---- Preview handler ----

  const handlePreview = async (record: any) => {
    setPreviewModal({
      open: true,
      subjectTemplate: record.subject_template ?? "",
      bodyTemplate: record.body_template ?? "",
    });

    // Also call the API preview endpoint with sample variables
    if (accessToken && record.template_id) {
      try {
        await notificationApi.preview(accessToken, record.template_id, {
          variables: SAMPLE_VARIABLES,
        });
      } catch {
        // Preview API call is best-effort; the local preview is still shown
      }
    }
  };

  // ---- Test Send handler ----

  const handleTestSendOpen = (record: any) => {
    testSendForm.resetFields();
    setTestSendModal({ open: true, templateId: record.template_id });
  };

  const handleTestSendSubmit = async () => {
    if (!accessToken || !testSendModal.templateId) return;
    setTestSending(true);
    try {
      const values = await testSendForm.validateFields();
      await notificationApi.sendTest(
        accessToken,
        testSendModal.templateId,
        values,
      );
      message.success("Test notification sent");
      setTestSendModal({ open: false, templateId: null });
      testSendForm.resetFields();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Test send failed");
    } finally {
      setTestSending(false);
    }
  };

  // ---- Render ----

  return (
    <CopilotPageShell
      title="Notifications"
      subtitle="Manage notification templates and delivery settings."
      icon={<BellOutlined />}
      onRefresh={loadTemplates}
    >
      <CopilotStatsRow
        stats={[
          { title: "Total Templates", value: templates.length, loading },
          { title: "Email Templates", value: emailCount, loading },
          { title: "Enabled", value: enabledCount, loading },
        ]}
      />

      <CopilotCrudTable
        dataSource={templates}
        rowKey="template_id"
        loading={loading}
        searchFields={["key", "channel", "subject_template"]}
        addLabel="Create Template"
        onAdd={() => {
          form.resetFields();
          setModal({ open: true, editing: null });
        }}
        onEdit={handleEdit}
        onDelete={handleDelete}
        columns={[
          {
            title: "Template ID",
            dataIndex: "template_id",
            key: "template_id",
          },
          {
            title: "Key",
            dataIndex: "key",
            key: "key",
          },
          {
            title: "Channel",
            dataIndex: "channel",
            key: "channel",
            render: (v: string) => (
              <Tag color={channelColors[v] ?? "default"}>{v}</Tag>
            ),
          },
          {
            title: "Subject",
            dataIndex: "subject_template",
            key: "subject_template",
            ellipsis: true,
          },
          {
            title: "Enabled",
            dataIndex: "enabled",
            key: "enabled",
            render: (v: boolean) => (
              <Tag color={v ? "green" : "default"}>
                {v ? "Yes" : "No"}
              </Tag>
            ),
          },
          {
            title: "Updated At",
            dataIndex: "updated_at",
            key: "updated_at",
            render: (v: string) =>
              v ? new Date(v).toLocaleDateString() : "\u2014",
          },
          {
            title: "",
            key: "_extra_actions",
            width: 200,
            render: (_: unknown, record: any) => (
              <Space>
                <Button
                  type="link"
                  size="small"
                  icon={<EyeOutlined />}
                  onClick={() => handlePreview(record)}
                >
                  Preview
                </Button>
                <Button
                  type="link"
                  size="small"
                  icon={<SendOutlined />}
                  onClick={() => handleTestSendOpen(record)}
                >
                  Test Send
                </Button>
              </Space>
            ),
          },
        ]}
      />

      {/* Create / Edit modal */}
      <Modal
        title={modal.editing ? "Edit Template" : "Create Template"}
        open={modal.open}
        onOk={handleSave}
        onCancel={() => setModal({ open: false, editing: null })}
        width={700}
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="key"
            label="Key"
            rules={[{ required: true, message: "Template key is required" }]}
          >
            <Input placeholder="e.g. welcome_email" />
          </Form.Item>
          <Form.Item name="channel" label="Channel" initialValue="email">
            <Select
              options={[
                { label: "Email", value: "email" },
                { label: "Push", value: "push" },
                { label: "SMS", value: "sms" },
              ]}
            />
          </Form.Item>
          <Form.Item name="subject_template" label="Subject Template">
            <Input placeholder="e.g. Hello {{user_name}}, your account update" />
          </Form.Item>
          <Form.Item name="body_template" label="Body Template">
            <Input.TextArea
              rows={6}
              placeholder={"Template body (supports {{variables}})"}
            />
          </Form.Item>
          <Form.Item name="enabled" label="Enabled" initialValue="true">
            <Select
              options={[
                { label: "True", value: "true" },
                { label: "False", value: "false" },
              ]}
            />
          </Form.Item>
          <Form.Item name="metadata" label="Metadata (JSON)">
            <Input.TextArea
              rows={4}
              placeholder={'{\n  "priority": "high"\n}'}
              style={{ fontFamily: "monospace", fontSize: 12 }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Preview modal */}
      <CopilotTemplatePreview
        open={previewModal.open}
        title="Template Preview"
        subjectTemplate={previewModal.subjectTemplate}
        bodyTemplate={previewModal.bodyTemplate}
        variables={SAMPLE_VARIABLES}
        onClose={() =>
          setPreviewModal({ open: false, subjectTemplate: "", bodyTemplate: "" })
        }
      />

      {/* Test Send modal */}
      <Modal
        title="Send Test Notification"
        open={testSendModal.open}
        onOk={handleTestSendSubmit}
        onCancel={() => {
          setTestSendModal({ open: false, templateId: null });
          testSendForm.resetFields();
        }}
        confirmLoading={testSending}
        width={420}
        destroyOnClose
      >
        <Form form={testSendForm} layout="vertical" preserve={false}>
          <Form.Item
            name="recipient_email"
            label="Recipient Email"
            rules={[
              { required: true, message: "Recipient email is required" },
              { type: "email", message: "Please enter a valid email address" },
            ]}
          >
            <Input placeholder="test@example.com" />
          </Form.Item>
        </Form>
      </Modal>
    </CopilotPageShell>
  );
}
