"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, PlusOutlined, ReloadOutlined, SaveOutlined } from "@ant-design/icons";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import {
  useBulkUpdateCopilotModelSelection,
  useCopilotModelCatalog,
  useCopilotModelSelectionAccounts,
  useCopilotModelSelection,
  useCreateCopilotModelCatalogEntry,
  useDeleteCopilotModelCatalogEntry,
  useImportCopilotModelCatalogFromRouter,
  useUpdateCopilotModelCatalogEntry,
  useUpdateCopilotModelSelection,
} from "@/app/(dashboard)/hooks/copilot/useCopilotModels";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";

const CopilotModelsPage: React.FC = () => {
  const { isSuperAdmin } = useAuthorized();
  const { data: accountData, isLoading: accountsLoading } = useCopilotAccounts();

  const [targetAccountId, setTargetAccountId] = useState<string | undefined>();
  const [superSelectedModels, setSuperSelectedModels] = useState<string[]>([]);
  const [tenantSelectedModels, setTenantSelectedModels] = useState<string[]>([]);
  const [bulkAccountIds, setBulkAccountIds] = useState<string[]>([]);
  const [catalogModalOpen, setCatalogModalOpen] = useState(false);
  const [editingCatalogItem, setEditingCatalogItem] = useState<any | null>(null);
  const [catalogForm] = Form.useForm();

  const accounts = accountData?.accounts || [];

  useEffect(() => {
    if (isSuperAdmin && !targetAccountId && accounts.length > 0) {
      setTargetAccountId(accounts[0].account_id);
    }
  }, [accounts, isSuperAdmin, targetAccountId]);

  const selectionParams = useMemo(() => {
    if (isSuperAdmin) {
      return targetAccountId ? { account_id: targetAccountId } : undefined;
    }
    return undefined;
  }, [isSuperAdmin, targetAccountId]);

  const { data, isLoading, refetch } = useCopilotModelSelection(selectionParams);
  const { data: catalogData, isLoading: catalogLoading, refetch: refetchCatalog } = useCopilotModelCatalog(
    isSuperAdmin ? { include_inactive: true } : undefined,
  );

  const updateSelection = useUpdateCopilotModelSelection();
  const bulkUpdateSelection = useBulkUpdateCopilotModelSelection();
  const createCatalogEntry = useCreateCopilotModelCatalogEntry();
  const updateCatalogEntry = useUpdateCopilotModelCatalogEntry();
  const deleteCatalogEntry = useDeleteCopilotModelCatalogEntry();
  const importCatalogFromRouter = useImportCopilotModelCatalogFromRouter();

  const { data: accountSelectionData, isLoading: accountSelectionLoading } = useCopilotModelSelectionAccounts({
    limit: 500,
    offset: 0,
  });

  useEffect(() => {
    const incomingSuper = data?.super_admin_selected_models;
    const incomingTenant = data?.tenant_selected_models || data?.selected_models;
    if (Array.isArray(incomingSuper)) {
      setSuperSelectedModels(incomingSuper);
    } else {
      setSuperSelectedModels([]);
    }
    if (Array.isArray(incomingTenant)) {
      setTenantSelectedModels(incomingTenant);
    } else {
      setTenantSelectedModels([]);
    }
  }, [data?.super_admin_selected_models, data?.tenant_selected_models, data?.selected_models]);

  const catalogModels: string[] = data?.catalog_models || [];
  const availableForTenantModels: string[] = data?.available_for_tenant_models || catalogModels;
  const effectiveModels: string[] = data?.effective_models || [];
  const superSelectedCount = superSelectedModels.length;
  const tenantSelectedCount = tenantSelectedModels.length;

  const canSave = Boolean(!isSuperAdmin || targetAccountId);
  const selectionMode = data?.selection_mode;

  const handleSaveSuperSelection = async () => {
    if (!canSave) {
      message.error("Select an account first.");
      return;
    }
    try {
      await updateSelection.mutateAsync({
        selected_models: superSelectedModels,
        account_id: isSuperAdmin ? targetAccountId : undefined,
        scope: "super_admin",
      });
      message.success("Super-admin model access updated.");
      refetch();
    } catch (e: any) {
      message.error(e?.message || "Failed to save super-admin model access");
    }
  };

  const handleSaveTenantSelection = async () => {
    if (!canSave) {
      message.error("Select an account first.");
      return;
    }
    try {
      await updateSelection.mutateAsync({
        selected_models: tenantSelectedModels,
        account_id: isSuperAdmin ? targetAccountId : undefined,
        scope: "tenant_admin",
      });
      message.success("Tenant model selection updated.");
      refetch();
    } catch (e: any) {
      message.error(e?.message || "Failed to save tenant model selection");
    }
  };

  const handleBulkApply = async () => {
    if (bulkAccountIds.length === 0) {
      message.warning("Select at least one account.");
      return;
    }
    await bulkUpdateSelection.mutateAsync({
      account_ids: bulkAccountIds,
      selected_models: superSelectedModels,
      scope: "super_admin",
    });
    message.success("Super-admin model allowlist applied to selected accounts.");
  };

  const openCreateCatalogModal = () => {
    setEditingCatalogItem(null);
    catalogForm.resetFields();
    catalogForm.setFieldsValue({
      model_name: "",
      display_name: "",
      provider: "",
      upstream_model_name: "",
      credits_per_1k_tokens: 0,
      is_active: true,
    });
    setCatalogModalOpen(true);
  };

  const openEditCatalogModal = (record: any) => {
    setEditingCatalogItem(record);
    catalogForm.setFieldsValue({
      model_name: record.model_name,
      display_name: record.display_name,
      provider: record.provider,
      upstream_model_name: record.upstream_model_name,
      credits_per_1k_tokens: record.credits_per_1k_tokens ?? 0,
      is_active: record.is_active ?? true,
    });
    setCatalogModalOpen(true);
  };

  const saveCatalogEntry = async () => {
    try {
      const values = await catalogForm.validateFields();
      const payload = {
        ...values,
        model_name: String(values.model_name || "").trim(),
      };
      if (!payload.model_name) {
        message.error("Model name is required.");
        return;
      }

      if (editingCatalogItem?.id) {
        await updateCatalogEntry.mutateAsync({ id: editingCatalogItem.id, data: payload });
        message.success("Catalog entry updated.");
      } else {
        await createCatalogEntry.mutateAsync(payload);
        message.success("Catalog entry created.");
      }
      setCatalogModalOpen(false);
      setEditingCatalogItem(null);
      catalogForm.resetFields();
      refetchCatalog();
      refetch();
    } catch (e: any) {
      if (e?.message) message.error(e.message);
    }
  };

  const handleDeleteCatalogEntry = async (record: any) => {
    await deleteCatalogEntry.mutateAsync({ id: record.id, hardDelete: false });
    message.success("Catalog entry disabled.");
    refetchCatalog();
    refetch();
  };

  const handleImportFromRouter = async () => {
    const result = await importCatalogFromRouter.mutateAsync({});
    const imported = Number(result?.data?.imported || 0);
    const skipped = Number(result?.data?.skipped || 0);
    message.success(`Imported ${imported} models from gateway suggestions (skipped ${skipped}).`);
    refetchCatalog();
    refetch();
  };

  const accountSelectionRows = accountSelectionData?.data || [];
  const totalAccountRows = accountSelectionData?.total || 0;
  const catalogRows = catalogData?.data || [];
  const routerSuggestions = catalogData?.router_suggestions || [];

  return (
    <div style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="Copilot Model Governance"
        description="Layered governance: super admins define per-account allowed models from catalog, then tenant admins choose user-visible models from that allowed subset."
        style={{ marginBottom: 16 }}
      />

      {isSuperAdmin && (
        <Card
          title="Copilot Model Catalog (Super Admin)"
          style={{ marginBottom: 16 }}
          extra={
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => refetchCatalog()}>Refresh</Button>
              <Button onClick={handleImportFromRouter} loading={importCatalogFromRouter.isPending}>Import Gateway Suggestions</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreateCatalogModal}>Add Model</Button>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            <Typography.Text type="secondary">
              Router suggestions available: {Array.isArray(routerSuggestions) ? routerSuggestions.length : 0}
            </Typography.Text>
            <Table
              rowKey="id"
              loading={catalogLoading}
              dataSource={catalogRows}
              pagination={{ pageSize: 10 }}
              columns={[
                { title: "Model", dataIndex: "model_name", key: "model_name" },
                { title: "Display", dataIndex: "display_name", key: "display_name" },
                { title: "Provider", dataIndex: "provider", key: "provider", render: (v: string) => v || "-" },
                {
                  title: "Status",
                  dataIndex: "is_active",
                  key: "is_active",
                  render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "active" : "inactive"}</Tag>,
                },
                { title: "Credits / 1k", dataIndex: "credits_per_1k_tokens", key: "credits_per_1k_tokens" },
                {
                  title: "Actions",
                  key: "actions",
                  render: (_: any, record: any) => (
                    <Space>
                      <Button size="small" onClick={() => openEditCatalogModal(record)}>Edit</Button>
                      <Popconfirm
                        title="Disable catalog model"
                        description="Disable this model from Copilot catalog?"
                        onConfirm={() => handleDeleteCatalogEntry(record)}
                      >
                        <Button size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          </Space>
        </Card>
      )}

      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: "100%" }} size={16}>
          {isSuperAdmin && (
            <div>
              <div style={{ marginBottom: 8 }}>Target Account</div>
              <Select
                showSearch
                optionFilterProp="label"
                style={{ width: 420 }}
                loading={accountsLoading}
                value={targetAccountId}
                onChange={(v) => setTargetAccountId(v)}
                placeholder="Select account"
                options={accounts.map((a) => ({
                  value: a.account_id,
                  label: `${a.account_name} (${a.status})`,
                }))}
              />
            </div>
          )}

          <Row gutter={16}>
            <Col span={6}>
              <Card><Statistic title="Catalog Models" value={catalogModels.length} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="Super Allowlist" value={superSelectedCount} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="Tenant Allowlist" value={tenantSelectedCount} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="Effective Visible" value={effectiveModels.length} /></Card>
            </Col>
          </Row>

          {selectionMode === "no_catalog" && (
            <Alert
              type="warning"
              showIcon
              message="No Copilot model catalog configured"
              description="Super admin must add models in Copilot Model Catalog before account visibility can be configured."
            />
          )}

          {!canSave ? (
            <Empty description="Select an account to edit Copilot model visibility." />
          ) : isLoading ? (
            <div style={{ textAlign: "center", padding: 24 }}><Spin /></div>
          ) : (
            <>
              {isSuperAdmin && (
                <div>
                  <div style={{ marginBottom: 8 }}>Super Admin Account Allowlist</div>
                  <Select
                    mode="multiple"
                    showSearch
                    optionFilterProp="label"
                    style={{ width: "100%" }}
                    placeholder="Select models this account can access. Leave empty to allow full catalog."
                    value={superSelectedModels}
                    onChange={(vals) => setSuperSelectedModels(vals)}
                    options={catalogModels.map((m) => ({ label: m, value: m }))}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Tag color={superSelectedCount > 0 ? "blue" : "green"}>
                      {superSelectedCount > 0 ? "Super Allowlist Mode" : "All Catalog Allowed"}
                    </Tag>
                  </div>
                  <Space style={{ marginTop: 12 }}>
                    <Button onClick={() => setSuperSelectedModels([])}>Allow Full Catalog For Account</Button>
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      loading={updateSelection.isPending}
                      onClick={handleSaveSuperSelection}
                    >
                      Save Super Selection
                    </Button>
                  </Space>
                </div>
              )}

              <div>
                <div style={{ marginBottom: 8 }}>
                  {isSuperAdmin ? "Tenant Admin User-Facing Selection" : "User-Facing Model Selection"}
                </div>
                <Select
                  mode="multiple"
                  showSearch
                  optionFilterProp="label"
                  style={{ width: "100%" }}
                  placeholder="Select models users can use. Leave empty to expose all available models."
                  value={tenantSelectedModels}
                  onChange={(vals) => setTenantSelectedModels(vals)}
                  options={availableForTenantModels.map((m) => ({ label: m, value: m }))}
                />
                <div style={{ marginTop: 8 }}>
                  <Tag color={tenantSelectedCount > 0 ? "blue" : "green"}>
                    {tenantSelectedCount > 0 ? "Tenant Allowlist Mode" : "All Available Models"}
                  </Tag>
                  {isSuperAdmin && (
                    <Tag color="default" style={{ marginLeft: 8 }}>
                      Available From Super Scope: {availableForTenantModels.length}
                    </Tag>
                  )}
                </div>
              </div>

              <Space>
                <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
                  Refresh
                </Button>
                <Button onClick={() => setTenantSelectedModels([])}>Use All Available Models</Button>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  loading={updateSelection.isPending}
                  onClick={handleSaveTenantSelection}
                >
                  Save Tenant Selection
                </Button>
              </Space>
            </>
          )}
        </Space>
      </Card>

      <Card title="Effective Visible Models">
        <Table
          dataSource={effectiveModels.map((name) => ({ name }))}
          rowKey="name"
          pagination={{ pageSize: 20 }}
          columns={[
            {
              title: "Model",
              dataIndex: "name",
              key: "name",
            },
          ]}
        />
      </Card>

      {isSuperAdmin && (
        <Card
          title="Account Selection Governance"
          style={{ marginTop: 16 }}
          extra={<Typography.Text type="secondary">Accounts in scope: {totalAccountRows}</Typography.Text>}
        >
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Space wrap>
              <Select
                mode="multiple"
                style={{ minWidth: 420 }}
                placeholder="Select accounts for bulk super-allowlist apply"
                value={bulkAccountIds}
                onChange={(vals) => setBulkAccountIds(vals)}
                options={accounts.map((a) => ({
                  value: a.account_id,
                  label: `${a.account_name} (${a.status})`,
                }))}
                optionFilterProp="label"
                showSearch
              />
              <Button
                type="primary"
                loading={bulkUpdateSelection.isPending}
                onClick={handleBulkApply}
              >
                Bulk Apply Super Selection
              </Button>
            </Space>

            <Table
              rowKey="account_id"
              loading={accountSelectionLoading}
              dataSource={accountSelectionRows}
              pagination={{ pageSize: 20 }}
              columns={[
                {
                  title: "Account",
                  key: "account",
                  render: (_: any, record: any) =>
                    `${record.account_name || record.account_id} (${record.status || "-"})`,
                },
                {
                  title: "Mode",
                  dataIndex: "selection_mode",
                  key: "selection_mode",
                  render: (value: string) => {
                    if (value === "no_catalog") return <Tag color="orange">{value}</Tag>;
                    if (value === "layered_allowlist") return <Tag color="purple">{value}</Tag>;
                    if (value === "super_allowlist" || value === "tenant_allowlist") return <Tag color="blue">{value}</Tag>;
                    return <Tag color="green">{value}</Tag>;
                  },
                },
                { title: "Super", dataIndex: "super_selected_count", key: "super_selected_count" },
                { title: "Tenant", dataIndex: "tenant_selected_count", key: "tenant_selected_count" },
                { title: "Available", dataIndex: "available_count", key: "available_count" },
                { title: "Effective", dataIndex: "effective_count", key: "effective_count" },
              ]}
            />
          </Space>
        </Card>
      )}

      <Modal
        title={editingCatalogItem ? "Edit Catalog Model" : "Add Catalog Model"}
        open={catalogModalOpen}
        onCancel={() => {
          setCatalogModalOpen(false);
          setEditingCatalogItem(null);
        }}
        onOk={saveCatalogEntry}
        okText={editingCatalogItem ? "Update" : "Create"}
        confirmLoading={createCatalogEntry.isPending || updateCatalogEntry.isPending}
      >
        <Form form={catalogForm} layout="vertical">
          <Form.Item name="model_name" label="Model Name" rules={[{ required: true }]}> 
            <Input placeholder="gpt-4o-mini" />
          </Form.Item>
          <Form.Item name="display_name" label="Display Name">
            <Input placeholder="GPT-4o Mini" />
          </Form.Item>
          <Form.Item name="provider" label="Provider">
            <Input placeholder="openai" />
          </Form.Item>
          <Form.Item name="upstream_model_name" label="Upstream Model Name">
            <Input placeholder="openai/gpt-4o-mini" />
          </Form.Item>
          <Form.Item name="credits_per_1k_tokens" label="Credits Per 1K Tokens">
            <InputNumber min={0} step={0.001} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotModelsPage;
