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
  useCopilotModelPolicies,
  useCopilotModelSelectionAccounts,
  useCopilotModelSelection,
  useCreateCopilotModelCatalogEntry,
  useDeleteCopilotModelCatalogEntry,
  useDeleteCopilotModelPolicy,
  useImportCopilotModelCatalogFromRouter,
  useResolveCopilotModelPolicy,
  useUpsertCopilotModelPolicy,
  useUpdateCopilotModelCatalogEntry,
  useUpdateCopilotModelSelection,
} from "@/app/(dashboard)/hooks/copilot/useCopilotModels";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";
import {
  useCopilotDirectoryGroups,
  useCopilotDirectoryTeams,
  useCopilotUsers,
} from "@/app/(dashboard)/hooks/copilot/useCopilotDirectory";

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
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<any | null>(null);
  const [policyForm] = Form.useForm();
  const [resolveScopeType, setResolveScopeType] = useState<string>("account");
  const [resolveScopeId, setResolveScopeId] = useState<string>("");

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

  const accountScopedParams = useMemo(() => {
    if (isSuperAdmin) {
      return targetAccountId ? { account_id: targetAccountId } : undefined;
    }
    return undefined;
  }, [isSuperAdmin, targetAccountId]);

  const canSave = Boolean(!isSuperAdmin || targetAccountId);

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
  const { data: modelPolicyData, isLoading: modelPolicyLoading, refetch: refetchModelPolicies } = useCopilotModelPolicies(accountScopedParams);
  const upsertModelPolicy = useUpsertCopilotModelPolicy();
  const deleteModelPolicy = useDeleteCopilotModelPolicy();

  const { data: directoryGroupsData } = useCopilotDirectoryGroups(
    canSave ? { ...(accountScopedParams || {}), limit: 500, offset: 0 } : undefined,
  );
  const { data: directoryTeamsData } = useCopilotDirectoryTeams(
    canSave ? { ...(accountScopedParams || {}), include_group: true, limit: 500, offset: 0 } : undefined,
  );
  const { data: directoryUsersData } = useCopilotUsers(
    canSave ? { ...(accountScopedParams || {}), include_memberships: false, limit: 500, offset: 0 } : undefined,
  );

  const resolveEnabled = Boolean(canSave && resolveScopeType && resolveScopeId);
  const { data: resolvedPolicyData, refetch: refetchResolvedPolicy, isFetching: resolvingPolicy } = useResolveCopilotModelPolicy(
    resolveEnabled
      ? {
          ...(accountScopedParams || {}),
          scope_type: resolveScopeType,
          scope_id: resolveScopeId,
        }
      : undefined,
    resolveEnabled,
  );

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

  useEffect(() => {
    const accountScopeId = String(data?.account_id || targetAccountId || "").trim();
    if (!accountScopeId) return;
    if (resolveScopeType === "account") {
      setResolveScopeId(accountScopeId);
    } else if (!resolveScopeId) {
      setResolveScopeId(accountScopeId);
    }
  }, [data?.account_id, targetAccountId, resolveScopeType, resolveScopeId]);

  const catalogModels: string[] = data?.catalog_models || [];
  const availableForTenantModels: string[] = data?.available_for_tenant_models || catalogModels;
  const effectiveModels: string[] = data?.effective_models || [];
  const superSelectedCount = superSelectedModels.length;
  const tenantSelectedCount = tenantSelectedModels.length;

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

  const directoryGroups = directoryGroupsData?.data || [];
  const directoryTeams = directoryTeamsData?.data || [];
  const directoryUsers = directoryUsersData?.data?.users || [];
  const modelPolicies = modelPolicyData?.data || [];

  const accountScopeId = String(data?.account_id || targetAccountId || "").trim();
  const policyScopeType = Form.useWatch("scope_type", policyForm) || "account";
  const policyMode = Form.useWatch("mode", policyForm) || "inherit";
  const policyScopeOptions = useMemo(() => {
    if (policyScopeType === "account") {
      return accountScopeId ? [{ label: accountScopeId, value: accountScopeId }] : [];
    }
    if (policyScopeType === "group") {
      return directoryGroups.map((g: any) => ({ label: g.name || g.id, value: g.id }));
    }
    if (policyScopeType === "team") {
      return directoryTeams.map((t: any) => ({ label: t.name || t.id, value: t.id }));
    }
    if (policyScopeType === "user") {
      return directoryUsers.map((u: any) => ({ label: u.email || u.name || u.id, value: u.id }));
    }
    return [];
  }, [policyScopeType, accountScopeId, directoryGroups, directoryTeams, directoryUsers]);

  const resolveScopeOptions = useMemo(() => {
    if (resolveScopeType === "account") {
      return accountScopeId ? [{ label: accountScopeId, value: accountScopeId }] : [];
    }
    if (resolveScopeType === "group") {
      return directoryGroups.map((g: any) => ({ label: g.name || g.id, value: g.id }));
    }
    if (resolveScopeType === "team") {
      return directoryTeams.map((t: any) => ({ label: t.name || t.id, value: t.id }));
    }
    if (resolveScopeType === "user") {
      return directoryUsers.map((u: any) => ({ label: u.email || u.name || u.id, value: u.id }));
    }
    return [];
  }, [resolveScopeType, accountScopeId, directoryGroups, directoryTeams, directoryUsers]);

  const openCreatePolicyModal = () => {
    setEditingPolicy(null);
    policyForm.resetFields();
    policyForm.setFieldsValue({
      scope_type: "account",
      scope_id: accountScopeId || undefined,
      mode: "inherit",
      selected_models: [],
      notes: "",
    });
    setPolicyModalOpen(true);
  };

  const openEditPolicyModal = (row: any) => {
    setEditingPolicy(row);
    policyForm.setFieldsValue({
      scope_type: row.scope_type,
      scope_id: row.scope_id,
      mode: row.mode || "inherit",
      selected_models: row.selected_models || [],
      notes: row.notes || "",
    });
    setPolicyModalOpen(true);
  };

  const savePolicy = async () => {
    try {
      const values = await policyForm.validateFields();
      const payload = {
        ...values,
        account_id: isSuperAdmin ? targetAccountId : undefined,
      };
      if (payload.mode !== "allowlist") {
        payload.selected_models = [];
      }
      await upsertModelPolicy.mutateAsync(payload);
      message.success("Scoped model policy saved.");
      setPolicyModalOpen(false);
      setEditingPolicy(null);
      policyForm.resetFields();
      refetchModelPolicies();
      refetchResolvedPolicy();
      refetch();
    } catch (e: any) {
      if (e?.message) message.error(e.message);
    }
  };

  const handleDeletePolicy = async (row: any) => {
    await deleteModelPolicy.mutateAsync({
      scope_type: row.scope_type,
      scope_id: row.scope_id,
      account_id: isSuperAdmin ? targetAccountId : undefined,
    });
    message.success("Scoped model policy deleted.");
    refetchModelPolicies();
    refetchResolvedPolicy();
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

      <Card
        title="Scoped Model Access Policies"
        style={{ marginTop: 16 }}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => { refetchModelPolicies(); refetchResolvedPolicy(); }}>
              Refresh
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreatePolicyModal} disabled={!canSave}>
              Add Policy
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {!canSave ? (
            <Empty description="Select account first to manage scoped policies." />
          ) : (
            <Table
              rowKey={(r: any) => `${r.scope_type}:${r.scope_id}`}
              loading={modelPolicyLoading}
              dataSource={modelPolicies}
              pagination={{ pageSize: 10 }}
              columns={[
                { title: "Scope Type", dataIndex: "scope_type", key: "scope_type" },
                { title: "Scope ID", dataIndex: "scope_id", key: "scope_id" },
                { title: "Mode", dataIndex: "mode", key: "mode", render: (v: string) => <Tag color="blue">{v || "inherit"}</Tag> },
                {
                  title: "Selected Models",
                  dataIndex: "selected_models",
                  key: "selected_models",
                  render: (v: string[]) => Array.isArray(v) && v.length > 0 ? v.join(", ") : "-",
                },
                {
                  title: "Actions",
                  key: "actions",
                  render: (_: any, row: any) => (
                    <Space>
                      <Button size="small" onClick={() => openEditPolicyModal(row)}>Edit</Button>
                      <Popconfirm
                        title="Delete scoped policy"
                        description={`Remove policy for ${row.scope_type}:${row.scope_id}?`}
                        onConfirm={() => handleDeletePolicy(row)}
                      >
                        <Button size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          )}

          <Alert
            type="info"
            showIcon
            message="Policy Resolution Tester"
            description="Resolve effective model access for a specific scope and inspect inheritance + overrides."
          />

          <Space wrap style={{ width: "100%" }}>
            <Select
              style={{ width: 170 }}
              value={resolveScopeType}
              onChange={(value) => {
                setResolveScopeType(value);
                const fallback = value === "account" ? accountScopeId : "";
                setResolveScopeId(fallback || "");
              }}
              options={[
                { label: "Account", value: "account" },
                { label: "Group", value: "group" },
                { label: "Team", value: "team" },
                { label: "User", value: "user" },
              ]}
            />
            <Select
              showSearch
              optionFilterProp="label"
              style={{ minWidth: 380 }}
              value={resolveScopeId || undefined}
              onChange={(value) => setResolveScopeId(value)}
              options={resolveScopeOptions}
              placeholder="Select scope entity"
            />
            <Button onClick={() => refetchResolvedPolicy()} loading={resolvingPolicy} disabled={!resolveEnabled}>
              Resolve
            </Button>
          </Space>

          <Table
            rowKey="name"
            dataSource={(resolvedPolicyData?.effective_models || []).map((name: string) => ({ name }))}
            pagination={{ pageSize: 10 }}
            columns={[{ title: "Resolved Effective Models", dataIndex: "name", key: "name" }]}
          />
          <Typography.Text type="secondary">
            Model access feature gate: {resolvedPolicyData?.model_access_enabled === false ? "disabled" : "enabled"}
            {resolvedPolicyData?.model_access_resolved_from ? ` (${resolvedPolicyData.model_access_resolved_from})` : ""}
          </Typography.Text>
        </Space>
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

      <Modal
        title={editingPolicy ? "Edit Scoped Model Policy" : "Add Scoped Model Policy"}
        open={policyModalOpen}
        onCancel={() => {
          setPolicyModalOpen(false);
          setEditingPolicy(null);
        }}
        onOk={savePolicy}
        okText={editingPolicy ? "Update" : "Create"}
        confirmLoading={upsertModelPolicy.isPending}
      >
        <Form form={policyForm} layout="vertical">
          <Form.Item name="scope_type" label="Scope Type" rules={[{ required: true }]}>
            <Select
              options={[
                { label: "Account", value: "account" },
                { label: "Group", value: "group" },
                { label: "Team", value: "team" },
                { label: "User", value: "user" },
              ]}
            />
          </Form.Item>
          <Form.Item name="scope_id" label="Scope Entity" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={policyScopeOptions}
              placeholder="Select scope entity"
            />
          </Form.Item>
          <Form.Item name="mode" label="Mode" rules={[{ required: true }]}>
            <Select
              options={[
                { label: "Inherit", value: "inherit" },
                { label: "Allowlist", value: "allowlist" },
                { label: "All Available", value: "all_available" },
                { label: "Deny All", value: "deny_all" },
              ]}
            />
          </Form.Item>
          {policyMode === "allowlist" && (
            <Form.Item name="selected_models" label="Selected Models">
              <Select
                mode="multiple"
                showSearch
                optionFilterProp="label"
                options={availableForTenantModels.map((m) => ({ label: m, value: m }))}
                placeholder="Choose allowed models for this scope"
              />
            </Form.Item>
          )}
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotModelsPage;
