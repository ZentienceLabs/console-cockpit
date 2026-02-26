"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Tabs,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Switch,
  Card,
  Row,
  Col,
  Button,
  Tag,
  message,
} from "antd";
import { GlobalOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import { globalOpsApi, superAdminApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CopilotGlobalOpsPage() {
  const { accessToken } = useAuthorized();

  // ------- Summary -------
  const [summary, setSummary] = useState<any>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // ------- Bulk ops -------
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [eligibilityForm] = Form.useForm();
  const [creditsForm] = Form.useForm();
  const [statusForm] = Form.useForm();

  // ------- Config Providers -------
  const [providers, setProviders] = useState<any[]>([]);
  const [providersLoading, setProvidersLoading] = useState(false);
  const [providerModal, setProviderModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [providerForm] = Form.useForm();

  // ------- Config Models -------
  const [models, setModels] = useState<any[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelModal, setModelModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [modelForm] = Form.useForm();

  // ------- Platform Catalog -------
  const [catalog, setCatalog] = useState<any[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogModal, setCatalogModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [catalogForm] = Form.useForm();

  // =========================================================================
  // Data loaders
  // =========================================================================

  const loadSummary = useCallback(async () => {
    if (!accessToken) return;
    setSummaryLoading(true);
    try {
      setSummary(await globalOpsApi.getAccountsSummary(accessToken));
    } catch {
      setSummary(null);
    } finally {
      setSummaryLoading(false);
    }
  }, [accessToken]);

  const loadProviders = useCallback(async () => {
    if (!accessToken) return;
    setProvidersLoading(true);
    try {
      const d = await superAdminApi.listConfigProviders(accessToken);
      setProviders(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load config providers");
    } finally {
      setProvidersLoading(false);
    }
  }, [accessToken]);

  const loadModels = useCallback(async () => {
    if (!accessToken) return;
    setModelsLoading(true);
    try {
      const d = await superAdminApi.listConfigModels(accessToken);
      setModels(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load config models");
    } finally {
      setModelsLoading(false);
    }
  }, [accessToken]);

  const loadCatalog = useCallback(async () => {
    if (!accessToken) return;
    setCatalogLoading(true);
    try {
      const d = await superAdminApi.listPlatformCatalog(accessToken);
      setCatalog(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load platform catalog");
    } finally {
      setCatalogLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadSummary();
    loadProviders();
    loadModels();
    loadCatalog();
  }, [loadSummary, loadProviders, loadModels, loadCatalog]);

  const handleRefresh = () => {
    loadSummary();
    loadProviders();
    loadModels();
    loadCatalog();
  };

  // =========================================================================
  // Bulk operations handlers
  // =========================================================================

  const handleBulkEligibility = async () => {
    if (!accessToken) return;
    try {
      const values = await eligibilityForm.validateFields();
      setSubmitting("eligibility");
      await globalOpsApi.bulkModelEligibility(accessToken, values);
      message.success("Bulk model eligibility updated");
      eligibilityForm.resetFields();
      loadSummary();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Operation failed");
    } finally {
      setSubmitting(null);
    }
  };

  const handleBulkCredits = async () => {
    if (!accessToken) return;
    try {
      const values = await creditsForm.validateFields();
      setSubmitting("credits");
      await globalOpsApi.bulkCredits(accessToken, values);
      message.success("Bulk credits allocated");
      creditsForm.resetFields();
      loadSummary();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Operation failed");
    } finally {
      setSubmitting(null);
    }
  };

  const handleBulkStatus = async () => {
    if (!accessToken) return;
    try {
      const values = await statusForm.validateFields();
      setSubmitting("status");
      await globalOpsApi.bulkStatus(accessToken, values);
      message.success("Bulk status updated");
      statusForm.resetFields();
      loadSummary();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Operation failed");
    } finally {
      setSubmitting(null);
    }
  };

  // =========================================================================
  // Config Providers CRUD
  // =========================================================================

  const handleProviderSave = async () => {
    if (!accessToken) return;
    try {
      const values = await providerForm.validateFields();
      if (providerModal.editing) {
        await superAdminApi.updateConfigProvider(accessToken, providerModal.editing.id, values);
      } else {
        await superAdminApi.createConfigProvider(accessToken, values);
      }
      message.success("Config provider saved");
      setProviderModal({ open: false, editing: null });
      providerForm.resetFields();
      loadProviders();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  // =========================================================================
  // Config Models CRUD
  // =========================================================================

  const handleModelSave = async () => {
    if (!accessToken) return;
    try {
      const values = await modelForm.validateFields();
      if (modelModal.editing) {
        await superAdminApi.updateConfigModel(accessToken, modelModal.editing.id, values);
      } else {
        await superAdminApi.createConfigModel(accessToken, values);
      }
      message.success("Config model saved");
      setModelModal({ open: false, editing: null });
      modelForm.resetFields();
      loadModels();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  // =========================================================================
  // Platform Catalog CRUD
  // =========================================================================

  const handleCatalogSave = async () => {
    if (!accessToken) return;
    try {
      const values = await catalogForm.validateFields();
      if (catalogModal.editing) {
        await superAdminApi.updatePlatformCatalogItem(accessToken, catalogModal.editing.code, values);
      } else {
        await superAdminApi.createPlatformCatalogItem(accessToken, values);
      }
      message.success("Platform catalog item saved");
      setCatalogModal({ open: false, editing: null });
      catalogForm.resetFields();
      loadCatalog();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  // =========================================================================
  // Render
  // =========================================================================

  return (
    <CopilotPageShell
      title="Global Ops"
      subtitle="Account summaries, bulk operations, and platform configuration. (Super Admin only)"
      icon={<GlobalOutlined />}
      onRefresh={handleRefresh}
    >
      {/* Stats row */}
      <CopilotStatsRow
        stats={[
          { title: "Total Accounts", value: summary?.total_accounts ?? 0, loading: summaryLoading },
          { title: "Active Accounts", value: summary?.active_accounts ?? 0, loading: summaryLoading },
          { title: "Total Credits Allocated", value: summary?.total_credits ?? 0, loading: summaryLoading },
          { title: "Total Users", value: summary?.total_users ?? 0, loading: summaryLoading },
        ]}
      />

      <Tabs
        defaultActiveKey="bulk"
        items={[
          // ---------------------------------------------------------------
          // Bulk Operations
          // ---------------------------------------------------------------
          {
            key: "bulk",
            label: "Bulk Operations",
            children: (
              <Row gutter={16}>
                <Col span={8}>
                  <Card title="Bulk Model Eligibility" size="small">
                    <Form form={eligibilityForm} layout="vertical">
                      <Form.Item name="model_codes" label="Model Codes" rules={[{ required: true }]}>
                        <Select mode="tags" placeholder="Enter model codes" />
                      </Form.Item>
                      <Form.Item name="account_ids" label="Account IDs (optional)">
                        <Select mode="tags" placeholder="Leave empty for all accounts" />
                      </Form.Item>
                      <Form.Item name="action" label="Action" initialValue="add">
                        <Select
                          options={[
                            { value: "add", label: "add" },
                            { value: "remove", label: "remove" },
                            { value: "set", label: "set" },
                          ]}
                        />
                      </Form.Item>
                      <Button
                        type="primary"
                        block
                        onClick={handleBulkEligibility}
                        loading={submitting === "eligibility"}
                      >
                        Apply Eligibility
                      </Button>
                    </Form>
                  </Card>
                </Col>
                <Col span={8}>
                  <Card title="Bulk Credits" size="small">
                    <Form form={creditsForm} layout="vertical">
                      <Form.Item name="credits" label="Credits" rules={[{ required: true }]}>
                        <InputNumber min={0} style={{ width: "100%" }} />
                      </Form.Item>
                      <Form.Item name="account_ids" label="Account IDs (optional)">
                        <Select mode="tags" placeholder="Leave empty for all accounts" />
                      </Form.Item>
                      <Form.Item name="operation" label="Operation" initialValue="add">
                        <Select
                          options={[
                            { value: "add", label: "add" },
                            { value: "set", label: "set" },
                          ]}
                        />
                      </Form.Item>
                      <Button
                        type="primary"
                        block
                        onClick={handleBulkCredits}
                        loading={submitting === "credits"}
                      >
                        Apply Credits
                      </Button>
                    </Form>
                  </Card>
                </Col>
                <Col span={8}>
                  <Card title="Bulk Status" size="small">
                    <Form form={statusForm} layout="vertical">
                      <Form.Item name="status" label="Status" rules={[{ required: true }]}>
                        <Select
                          options={[
                            { value: "active", label: "active" },
                            { value: "suspended", label: "suspended" },
                            { value: "inactive", label: "inactive" },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item name="account_ids" label="Account IDs" rules={[{ required: true }]}>
                        <Select mode="tags" placeholder="Enter account IDs" />
                      </Form.Item>
                      <Form.Item name="reason" label="Reason">
                        <Input.TextArea rows={2} />
                      </Form.Item>
                      <Button
                        type="primary"
                        block
                        onClick={handleBulkStatus}
                        loading={submitting === "status"}
                      >
                        Apply Status
                      </Button>
                    </Form>
                  </Card>
                </Col>
              </Row>
            ),
          },

          // ---------------------------------------------------------------
          // Config Providers
          // ---------------------------------------------------------------
          {
            key: "providers",
            label: `Config Providers (${providers.length})`,
            children: (
              <>
                <CopilotCrudTable
                  dataSource={providers}
                  rowKey="id"
                  loading={providersLoading}
                  searchFields={["name", "display_label"]}
                  addLabel="Add Provider"
                  onAdd={() => {
                    providerForm.resetFields();
                    setProviderModal({ open: true, editing: null });
                  }}
                  onEdit={(r) => {
                    providerForm.setFieldsValue(r);
                    setProviderModal({ open: true, editing: r });
                  }}
                  onDelete={async (r) => {
                    if (accessToken) await superAdminApi.deleteConfigProvider(accessToken, r.id);
                    loadProviders();
                  }}
                  columns={[
                    { title: "ID", dataIndex: "id", key: "id", width: 80 },
                    { title: "Name", dataIndex: "name", key: "name" },
                    { title: "Display Label", dataIndex: "display_label", key: "display_label" },
                    {
                      title: "Active",
                      dataIndex: "is_active",
                      key: "is_active",
                      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "Yes" : "No"}</Tag>,
                    },
                  ]}
                />
                <Modal
                  title={providerModal.editing ? "Edit Config Provider" : "Add Config Provider"}
                  open={providerModal.open}
                  onOk={handleProviderSave}
                  onCancel={() => setProviderModal({ open: false, editing: null })}
                  width={600}
                >
                  <Form form={providerForm} layout="vertical">
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                      <Input placeholder="e.g. openai, anthropic" />
                    </Form.Item>
                    <Form.Item name="display_label" label="Display Label" rules={[{ required: true }]}>
                      <Input placeholder="e.g. OpenAI, Anthropic" />
                    </Form.Item>
                    <Form.Item name="endpoint_env_var" label="Endpoint Env Var">
                      <Input placeholder="e.g. OPENAI_API_BASE" />
                    </Form.Item>
                    <Form.Item name="api_key_env_var" label="API Key Env Var">
                      <Input placeholder="e.g. OPENAI_API_KEY" />
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked" initialValue={true}>
                      <Switch />
                    </Form.Item>
                  </Form>
                </Modal>
              </>
            ),
          },

          // ---------------------------------------------------------------
          // Config Models
          // ---------------------------------------------------------------
          {
            key: "models",
            label: `Config Models (${models.length})`,
            children: (
              <>
                <CopilotCrudTable
                  dataSource={models}
                  rowKey="id"
                  loading={modelsLoading}
                  searchFields={["deployment_name", "display_name", "capability"]}
                  addLabel="Add Model"
                  onAdd={() => {
                    modelForm.resetFields();
                    setModelModal({ open: true, editing: null });
                  }}
                  onEdit={(r) => {
                    modelForm.setFieldsValue(r);
                    setModelModal({ open: true, editing: r });
                  }}
                  onDelete={async (r) => {
                    if (accessToken) await superAdminApi.deleteConfigModel(accessToken, r.id);
                    loadModels();
                  }}
                  columns={[
                    { title: "ID", dataIndex: "id", key: "id", width: 80 },
                    { title: "Provider", dataIndex: "provider_id", key: "provider_id", width: 100 },
                    { title: "Deployment Name", dataIndex: "deployment_name", key: "deployment_name" },
                    { title: "Display Name", dataIndex: "display_name", key: "display_name" },
                    {
                      title: "Capability",
                      dataIndex: "capability",
                      key: "capability",
                      render: (v: string) => v ? <Tag color="blue">{v}</Tag> : "—",
                    },
                    { title: "Input $/1M", dataIndex: "input_cost_per_1m", key: "input_cost_per_1m" },
                    { title: "Output $/1M", dataIndex: "output_cost_per_1m", key: "output_cost_per_1m" },
                    {
                      title: "Active",
                      dataIndex: "is_active",
                      key: "is_active",
                      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "Yes" : "No"}</Tag>,
                    },
                  ]}
                />
                <Modal
                  title={modelModal.editing ? "Edit Config Model" : "Add Config Model"}
                  open={modelModal.open}
                  onOk={handleModelSave}
                  onCancel={() => setModelModal({ open: false, editing: null })}
                  width={640}
                >
                  <Form form={modelForm} layout="vertical">
                    <Form.Item name="provider_id" label="Provider" rules={[{ required: true }]}>
                      <Select
                        placeholder="Select a provider"
                        options={providers.map((p) => ({ value: p.id, label: p.display_label || p.name }))}
                      />
                    </Form.Item>
                    <Form.Item name="deployment_name" label="Deployment Name">
                      <Input placeholder="e.g. gpt-4o-2024-08-06" />
                    </Form.Item>
                    <Form.Item name="display_name" label="Display Name" rules={[{ required: true }]}>
                      <Input placeholder="e.g. GPT-4o" />
                    </Form.Item>
                    <Form.Item name="capability" label="Capability" initialValue="chat">
                      <Select
                        options={[
                          { value: "chat", label: "chat" },
                          { value: "completion", label: "completion" },
                          { value: "embedding", label: "embedding" },
                          { value: "image", label: "image" },
                        ]}
                      />
                    </Form.Item>
                    <Row gutter={16}>
                      <Col span={12}>
                        <Form.Item name="input_cost_per_1m" label="Input Cost / 1M tokens">
                          <InputNumber min={0} step={0.01} style={{ width: "100%" }} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name="output_cost_per_1m" label="Output Cost / 1M tokens">
                          <InputNumber min={0} step={0.01} style={{ width: "100%" }} />
                        </Form.Item>
                      </Col>
                    </Row>
                    <Form.Item name="sort_order" label="Sort Order">
                      <InputNumber min={0} style={{ width: "100%" }} />
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked" initialValue={true}>
                      <Switch />
                    </Form.Item>
                  </Form>
                </Modal>
              </>
            ),
          },

          // ---------------------------------------------------------------
          // Platform Catalog
          // ---------------------------------------------------------------
          {
            key: "catalog",
            label: `Platform Catalog (${catalog.length})`,
            children: (
              <>
                <CopilotCrudTable
                  dataSource={catalog}
                  rowKey="code"
                  loading={catalogLoading}
                  searchFields={["code", "name", "category", "parent_code"]}
                  addLabel="Add Item"
                  onAdd={() => {
                    catalogForm.resetFields();
                    setCatalogModal({ open: true, editing: null });
                  }}
                  onEdit={(r) => {
                    catalogForm.setFieldsValue(r);
                    setCatalogModal({ open: true, editing: r });
                  }}
                  onDelete={async (r) => {
                    if (accessToken) await superAdminApi.deletePlatformCatalogItem(accessToken, r.code);
                    loadCatalog();
                  }}
                  columns={[
                    { title: "Code", dataIndex: "code", key: "code" },
                    { title: "Name", dataIndex: "name", key: "name" },
                    { title: "Category", dataIndex: "category", key: "category" },
                    { title: "Parent Code", dataIndex: "parent_code", key: "parent_code" },
                    {
                      title: "Active",
                      dataIndex: "is_active",
                      key: "is_active",
                      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "Yes" : "No"}</Tag>,
                    },
                    { title: "Display Order", dataIndex: "display_order", key: "display_order" },
                  ]}
                />
                <Modal
                  title={catalogModal.editing ? "Edit Catalog Item" : "Add Catalog Item"}
                  open={catalogModal.open}
                  onOk={handleCatalogSave}
                  onCancel={() => setCatalogModal({ open: false, editing: null })}
                  width={600}
                >
                  <Form form={catalogForm} layout="vertical">
                    <Form.Item name="code" label="Code" rules={[{ required: true }]}>
                      <Input disabled={!!catalogModal.editing} placeholder="e.g. feature-analytics" />
                    </Form.Item>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                      <Input placeholder="e.g. Analytics Dashboard" />
                    </Form.Item>
                    <Form.Item name="category" label="Category">
                      <Input placeholder="e.g. features, integrations" />
                    </Form.Item>
                    <Form.Item name="parent_code" label="Parent Code">
                      <Input placeholder="Leave empty for top-level items" />
                    </Form.Item>
                    <Form.Item name="display_order" label="Display Order">
                      <InputNumber min={0} style={{ width: "100%" }} />
                    </Form.Item>
                    <Form.Item name="is_active" label="Active" valuePropName="checked" initialValue={true}>
                      <Switch />
                    </Form.Item>
                  </Form>
                </Modal>
              </>
            ),
          },
        ]}
      />
    </CopilotPageShell>
  );
}
