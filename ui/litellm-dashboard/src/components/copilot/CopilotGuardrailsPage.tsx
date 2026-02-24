"use client";

import React, { useState } from "react";
import { Table, Button, Modal, Form, Input, Select, Card, Tabs, message, Space, Switch, Tag, Row, Col, Drawer, DatePicker } from "antd";
import { PlusOutlined, DeleteOutlined, EditOutlined, CheckCircleOutlined, CloseCircleOutlined } from "@ant-design/icons";
import {
  useCopilotGuardrailsConfig,
  useUpsertCopilotGuardrailsConfig,
  useToggleCopilotGuardrailsConfig,
  useCopilotGuardrailsPatterns,
  useCreateCopilotGuardrailsPattern,
  useUpdateCopilotGuardrailsPattern,
  useDeleteCopilotGuardrailsPattern,
  useCopilotGuardrailsAudit,
} from "@/app/(dashboard)/hooks/copilot/useCopilotGuardrails";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";

const { TabPane } = Tabs;
const { TextArea } = Input;

const guardTypes = [
  { key: "pii", label: "PII Detection", description: "Detect and mask personally identifiable information" },
  { key: "toxic", label: "Toxicity Filter", description: "Block toxic, harmful, or offensive content" },
  { key: "jailbreak", label: "Jailbreak Prevention", description: "Prevent prompt injection and jailbreak attempts" },
];

const actionOptions = [
  { label: "Block", value: "block" },
  { label: "Flag", value: "flag" },
  { label: "Log Only", value: "log_only" },
];

const patternTypeOptions = [
  { label: "Detect", value: "detect" },
  { label: "Block", value: "block" },
  { label: "Allow", value: "allow" },
];

const patternActionOptions = [
  { label: "Mask", value: "mask" },
  { label: "Redact", value: "redact" },
  { label: "Hash", value: "hash" },
  { label: "Block", value: "block" },
];

const severityOptions = [
  { label: "Low", value: "low" },
  { label: "Medium", value: "medium" },
  { label: "High", value: "high" },
  { label: "Critical", value: "critical" },
];

const CopilotGuardrailsPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>(accountId || undefined);
  const [configModalOpen, setConfigModalOpen] = useState(false);
  const [editingGuardType, setEditingGuardType] = useState<string | null>(null);
  const [patternDrawerOpen, setPatternDrawerOpen] = useState(false);
  const [editingPattern, setEditingPattern] = useState<any>(null);
  const [patternGuardFilter, setPatternGuardFilter] = useState<string | undefined>();
  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();
  const [configForm] = Form.useForm();
  const [patternForm] = Form.useForm();

  const { data: configData, isLoading: configLoading } = useCopilotGuardrailsConfig({ account_id: accountFilter });
  const upsertConfig = useUpsertCopilotGuardrailsConfig();
  const toggleConfig = useToggleCopilotGuardrailsConfig();

  const { data: patternsData, isLoading: patternsLoading } = useCopilotGuardrailsPatterns({ account_id: accountFilter, guard_type: patternGuardFilter });
  const createPattern = useCreateCopilotGuardrailsPattern();
  const updatePattern = useUpdateCopilotGuardrailsPattern();
  const deletePattern = useDeleteCopilotGuardrailsPattern();

  const { data: auditData, isLoading: auditLoading } = useCopilotGuardrailsAudit({ account_id: accountFilter });

  const configs = configData?.data ?? [];
  const patterns = patternsData?.data ?? [];
  const auditEntries = auditData?.data ?? [];
  const accounts = accountData?.accounts ?? [];
  const ensureAccountForSuperAdminWrite = () => {
    if (isSuperAdmin && !accountFilter) {
      message.warning("Select an account before updating guardrails.");
      return false;
    }
    return true;
  };

  const getConfigForType = (guardType: string) => {
    return configs.find((c: any) => c.guard_type === guardType);
  };

  const handleConfigSave = async () => {
    if (!ensureAccountForSuperAdminWrite()) {
      return;
    }
    try {
      const values = await configForm.validateFields();
      await upsertConfig.mutateAsync({ guardType: editingGuardType!, data: values, account_id: accountFilter });
      message.success("Config updated");
      setConfigModalOpen(false);
      configForm.resetFields();
    } catch (err) { /* validation */ }
  };

  const handlePatternSave = async () => {
    if (!ensureAccountForSuperAdminWrite()) {
      return;
    }
    try {
      const values = await patternForm.validateFields();
      if (editingPattern) {
        await updatePattern.mutateAsync({ id: editingPattern.id, data: values, account_id: accountFilter });
        message.success("Pattern updated");
      } else {
        await createPattern.mutateAsync({ data: values, account_id: accountFilter });
        message.success("Pattern created");
      }
      setPatternDrawerOpen(false);
      setEditingPattern(null);
      patternForm.resetFields();
    } catch (err) { /* validation */ }
  };

  const patternColumns = [
    { title: "Name", dataIndex: "pattern_name", key: "pattern_name" },
    {
      title: "Guard Type",
      dataIndex: "guard_type",
      key: "guard_type",
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    { title: "Regex", dataIndex: "pattern_regex", key: "pattern_regex", ellipsis: true },
    {
      title: "Type",
      dataIndex: "pattern_type",
      key: "pattern_type",
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: "Action",
      dataIndex: "action",
      key: "action",
      render: (v: string) => <Tag color="orange">{v}</Tag>,
    },
    {
      title: "Severity",
      dataIndex: "severity",
      key: "severity",
      render: (v: string) => {
        const colors: Record<string, string> = { low: "default", medium: "gold", high: "orange", critical: "red" };
        return <Tag color={colors[v] || "default"}>{v}</Tag>;
      },
    },
    {
      title: "Enabled",
      dataIndex: "enabled",
      key: "enabled",
      render: (v: boolean) => v ? <CheckCircleOutlined style={{ color: "#52c41a" }} /> : <CloseCircleOutlined style={{ color: "#bbb" }} />,
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
              setEditingPattern(record);
              patternForm.setFieldsValue(record);
              setPatternDrawerOpen(true);
            }}
          />
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            onClick={() => {
              Modal.confirm({
                title: "Delete Pattern",
                content: `Delete pattern "${record.pattern_name}"?`,
                onOk: async () => {
                  if (!ensureAccountForSuperAdminWrite()) {
                    return;
                  }
                  await deletePattern.mutateAsync({ id: record.id, account_id: accountFilter });
                  message.success("Pattern deleted");
                },
              });
            }}
          />
        </Space>
      ),
    },
  ];

  const auditColumns = [
    {
      title: "Time",
      dataIndex: "changed_at",
      key: "changed_at",
      render: (v: string) => v ? new Date(v).toLocaleString() : "-",
    },
    {
      title: "Guard Type",
      dataIndex: "guard_type",
      key: "guard_type",
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    { title: "Action", dataIndex: "action", key: "action" },
    { title: "Changed By", dataIndex: "changed_by", key: "changed_by" },
  ];

  return (
    <div style={{ width: "100%" }}>
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
      <Tabs defaultActiveKey="config">
        <TabPane tab="Guard Configuration" key="config">
          <Row gutter={[16, 16]}>
            {guardTypes.map((gt) => {
              const config = getConfigForType(gt.key);
              const enabled = config?.enabled ?? false;
              return (
                <Col key={gt.key} xs={24} md={8}>
                  <Card
                    title={gt.label}
                    extra={
                      <Switch
                        checked={enabled}
                        onChange={() => {
                          if (!ensureAccountForSuperAdminWrite()) {
                            return;
                          }
                          toggleConfig.mutate({ guardType: gt.key, account_id: accountFilter });
                        }}
                        loading={toggleConfig.isPending}
                      />
                    }
                  >
                    <p style={{ color: "#666", marginBottom: 12 }}>{gt.description}</p>
                    <p><strong>Action on fail:</strong> {config?.action_on_fail ?? "log_only"}</p>
                    <p><strong>Execution order:</strong> {config?.execution_order ?? 0}</p>
                    <Button
                      size="small"
                      type="link"
                      onClick={() => {
                        setEditingGuardType(gt.key);
                        configForm.setFieldsValue({
                          enabled: config?.enabled ?? false,
                          execution_order: config?.execution_order ?? 0,
                          action_on_fail: config?.action_on_fail ?? "log_only",
                        });
                        setConfigModalOpen(true);
                      }}
                    >
                      Configure
                    </Button>
                  </Card>
                </Col>
              );
            })}
          </Row>
        </TabPane>

        <TabPane tab="Custom Patterns" key="patterns">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
            <Select
              placeholder="Filter by guard type"
              allowClear
              style={{ width: 200 }}
              options={guardTypes.map((gt) => ({ label: gt.label, value: gt.key }))}
              onChange={(v) => setPatternGuardFilter(v)}
            />
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                if (!ensureAccountForSuperAdminWrite()) {
                  return;
                }
                setEditingPattern(null);
                patternForm.resetFields();
                setPatternDrawerOpen(true);
              }}
            >
              Create Pattern
            </Button>
          </div>
          <Table dataSource={patterns} columns={patternColumns} rowKey="id" loading={patternsLoading} />
        </TabPane>

        <TabPane tab="Audit Log" key="audit">
          <Table dataSource={auditEntries} columns={auditColumns} rowKey="id" loading={auditLoading} pagination={{ pageSize: 20 }} />
        </TabPane>
      </Tabs>

      <Modal
        title={`Configure ${editingGuardType?.toUpperCase()} Guard`}
        open={configModalOpen}
        onOk={handleConfigSave}
        onCancel={() => { setConfigModalOpen(false); }}
        confirmLoading={upsertConfig.isPending}
      >
        <Form form={configForm} layout="vertical">
          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="execution_order" label="Execution Order">
            <Select options={[{ label: "1 (First)", value: 1 }, { label: "2", value: 2 }, { label: "3 (Last)", value: 3 }]} />
          </Form.Item>
          <Form.Item name="action_on_fail" label="Action on Fail">
            <Select options={actionOptions} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={editingPattern ? "Edit Pattern" : "Create Pattern"}
        open={patternDrawerOpen}
        onClose={() => { setPatternDrawerOpen(false); setEditingPattern(null); }}
        width={520}
        extra={
          <Button type="primary" onClick={handlePatternSave} loading={createPattern.isPending || updatePattern.isPending}>
            {editingPattern ? "Update" : "Create"}
          </Button>
        }
      >
        <Form form={patternForm} layout="vertical">
          <Form.Item name="guard_type" label="Guard Type" rules={[{ required: !editingPattern }]}>
            <Select
              options={guardTypes.map((gt) => ({ label: gt.label, value: gt.key }))}
              disabled={!!editingPattern}
            />
          </Form.Item>
          <Form.Item name="pattern_name" label="Pattern Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="pattern_regex" label="Regex Pattern" rules={[{ required: true }]}>
            <Input placeholder="\\b\\d{3}-\\d{2}-\\d{4}\\b" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="pattern_type" label="Pattern Type" initialValue="detect">
            <Select options={patternTypeOptions} />
          </Form.Item>
          <Form.Item name="action" label="Action" initialValue="mask">
            <Select options={patternActionOptions} />
          </Form.Item>
          <Form.Item name="severity" label="Severity" initialValue="medium">
            <Select options={severityOptions} />
          </Form.Item>
          <Form.Item name="category" label="Category">
            <Input placeholder="e.g., financial, healthcare" />
          </Form.Item>
          <Form.Item name="enabled" label="Enabled" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
};

export default CopilotGuardrailsPage;
