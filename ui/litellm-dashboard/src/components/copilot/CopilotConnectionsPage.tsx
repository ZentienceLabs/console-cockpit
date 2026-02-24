"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  LoadingOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  useCopilotConnections,
  useCopilotEnabledIntegrations,
  useCopilotIntegrationCatalog,
  useCreateCopilotConnection,
  useCreateCopilotIntegrationCatalogEntry,
  useDeleteCopilotConnection,
  useDeleteCopilotIntegrationCatalogEntry,
  useTestCopilotConnection,
  useUpdateCopilotConnection,
  useUpdateCopilotEnabledIntegrations,
  useUpdateCopilotIntegrationCatalogEntry,
} from "@/app/(dashboard)/hooks/copilot/useCopilotConnections";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";

const { TabPane } = Tabs;
const { TextArea } = Input;

type PairRow = { key?: string; value?: string };
type OpenApiSecretRow = { key?: string; value?: string; location?: "header" | "query" | "body" | "url" };

const mcpModeOptions = [
  { label: "Streamable HTTP", value: "streamable-http" },
  { label: "SSE", value: "sse" },
  { label: "STDIO", value: "stdio" },
];

const openApiAuthOptions = [
  { label: "None", value: "none" },
  { label: "Bearer", value: "bearer" },
  { label: "API Key", value: "api_key" },
  { label: "Basic", value: "basic" },
  { label: "OAuth2", value: "oauth2" },
];

const openApiSecretLocationOptions = [
  { label: "Header", value: "header" },
  { label: "Query", value: "query" },
  { label: "URL Path", value: "url" },
  { label: "Body", value: "body" },
];

function parseJsonField(raw: string | undefined, fieldLabel: string, fallback: any) {
  if (!raw || !raw.trim()) return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error(`${fieldLabel} must be valid JSON.`);
  }
}

function toPrettyJson(value: any, fallback: string) {
  if (value === undefined || value === null) return fallback;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return fallback;
  }
}

function objectToPairs(value: any): PairRow[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.entries(value).map(([k, v]) => ({ key: String(k), value: v == null ? "" : String(v) }));
}

function pairsToObject(value: PairRow[] | undefined): Record<string, string> {
  const rows = Array.isArray(value) ? value : [];
  return rows.reduce((acc, row) => {
    const k = String(row?.key || "").trim();
    if (!k) return acc;
    acc[k] = String(row?.value || "");
    return acc;
  }, {} as Record<string, string>);
}

function openApiSecretsToRows(value: any): OpenApiSecretRow[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  const rows: OpenApiSecretRow[] = [];
  for (const [key, raw] of Object.entries(value)) {
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      const rec = raw as any;
      rows.push({
        key,
        value: rec.value == null ? "" : String(rec.value),
        location: rec.location || rec.usage || "header",
      });
      continue;
    }
    rows.push({ key, value: raw == null ? "" : String(raw), location: "header" });
  }
  return rows;
}

function openApiRowsToSecrets(value: OpenApiSecretRow[] | undefined): Record<string, { value: string; location: string }> {
  const rows = Array.isArray(value) ? value : [];
  return rows.reduce((acc, row) => {
    const k = String(row?.key || "").trim();
    if (!k) return acc;
    acc[k] = {
      value: String(row?.value || ""),
      location: row?.location || "header",
    };
    return acc;
  }, {} as Record<string, { value: string; location: string }>);
}

function parseArgsText(input: string | undefined): string[] {
  const raw = String(input || "").trim();
  if (!raw) return [];
  if (raw.startsWith("[")) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.map((v) => String(v));
      }
    } catch {
      // fallback to line parsing
    }
  }
  return raw
    .split(/\n|,/) 
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatArgsText(input: any): string {
  if (!Array.isArray(input)) return "";
  return input.map((v) => String(v)).join("\n");
}

const CopilotConnectionsPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();

  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>(accountId || undefined);
  const [activeTab, setActiveTab] = useState("mcp");

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingConnection, setEditingConnection] = useState<any>(null);
  const [testResults, setTestResults] = useState<Record<string, any>>({});

  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importConfigText, setImportConfigText] = useState("");

  const [integrationModalOpen, setIntegrationModalOpen] = useState(false);
  const [editingIntegrationCatalogItem, setEditingIntegrationCatalogItem] = useState<any>(null);

  const [form] = Form.useForm();
  const [catalogForm] = Form.useForm();

  const connectionType = Form.useWatch("connection_type", form) || (activeTab === "openapi" ? "openapi" : "mcp");
  const mcpMode = Form.useWatch("mcp_mode", form) || "streamable-http";
  const openApiAuthType = Form.useWatch("openapi_auth_type", form) || "none";
  const openApiSpecMode = Form.useWatch("openapi_spec_mode", form) || "url";

  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();
  const accounts = accountData?.accounts ?? [];

  useEffect(() => {
    if (isSuperAdmin && !selectedAccountId && accounts.length > 0) {
      setSelectedAccountId(accounts[0].account_id);
    }
  }, [isSuperAdmin, selectedAccountId, accounts]);

  const { data: connectionsData, isLoading: connectionsLoading, refetch: refetchConnections } = useCopilotConnections({
    account_id: accountFilter,
    connection_type: activeTab === "mcp" || activeTab === "openapi" ? activeTab : undefined,
  });

  const { data: catalogData, isLoading: catalogLoading, refetch: refetchCatalog } = useCopilotIntegrationCatalog(
    isSuperAdmin ? { include_inactive: true } : undefined,
  );

  const { data: enabledData, isLoading: enabledLoading, refetch: refetchEnabled } = useCopilotEnabledIntegrations(
    { account_id: accountFilter },
    !isSuperAdmin || Boolean(accountFilter),
  );

  const createConnection = useCreateCopilotConnection();
  const updateConnection = useUpdateCopilotConnection();
  const deleteConnection = useDeleteCopilotConnection();
  const testConnection = useTestCopilotConnection();

  const createCatalogEntry = useCreateCopilotIntegrationCatalogEntry();
  const updateCatalogEntry = useUpdateCopilotIntegrationCatalogEntry();
  const deleteCatalogEntry = useDeleteCopilotIntegrationCatalogEntry();
  const updateEnabledIntegrations = useUpdateCopilotEnabledIntegrations();

  const rawConnections = connectionsData?.data ?? [];
  const connections = rawConnections.filter((row: any) => row.connection_type === "mcp" || row.connection_type === "openapi");

  const integrationCatalog = catalogData?.data ?? [];
  const enabledIntegrationIds: string[] = enabledData?.data?.enabled_integration_ids ?? [];

  const canWriteAccountScoped = useMemo(() => {
    if (!isSuperAdmin) return true;
    return Boolean(accountFilter);
  }, [isSuperAdmin, accountFilter]);

  const ensureAccountForSuperAdminWrite = () => {
    if (isSuperAdmin && !accountFilter) {
      message.warning("Select an account before writing account-scoped Copilot settings.");
      return false;
    }
    return true;
  };

  const toggleEnabledIntegration = async (integrationId: string, enabled: boolean) => {
    if (!ensureAccountForSuperAdminWrite()) return;
    const current = new Set(enabledIntegrationIds);
    if (enabled) current.add(integrationId);
    else current.delete(integrationId);

    await updateEnabledIntegrations.mutateAsync({
      integration_ids: Array.from(current),
      account_id: isSuperAdmin ? accountFilter : undefined,
    });

    await refetchEnabled();
    message.success("Integration visibility updated.");
  };

  const openCreateConnectionDrawer = () => {
    const type = activeTab === "openapi" ? "openapi" : "mcp";
    setEditingConnection(null);
    form.resetFields();
    form.setFieldsValue({
      connection_type: type,
      is_active: true,
      is_default: false,
      mcp_mode: "streamable-http",
      timeout: 30000,
      args_text: "",
      env_pairs: [],
      header_pairs: [],
      openapi_auth_type: "none",
      openapi_spec_mode: "url",
      openapi_header_pairs: [],
      openapi_secret_pairs: [],
      metadata_json: "{}",
    });
    setDrawerOpen(true);
  };

  const openForEdit = (record: any) => {
    const connData = record.connection_data || {};
    const auth = connData.auth || {};

    setEditingConnection(record);
    form.resetFields();
    form.setFieldsValue({
      connection_type: record.connection_type,
      name: record.name,
      description: record.description,
      description_for_agent: record.description_for_agent,
      is_active: record.is_active,
      is_default: record.is_default,

      mcp_mode: connData.type || (connData.command ? "stdio" : "streamable-http"),
      url: connData.url,
      command: connData.command,
      timeout: connData.timeout,
      args_text: formatArgsText(connData.args),
      env_pairs: objectToPairs(connData.env),
      header_pairs: objectToPairs(connData.headers),
      auth_header_name: "Authorization",
      mcp_api_key: connData.api_key,

      base_url: connData.base_url,
      openapi_spec_mode: connData.spec_text ? "text" : "url",
      spec_url: connData.spec_url,
      spec_text: connData.spec_text,
      openapi_auth_type: auth.type || "none",
      bearer_token: auth.bearer_token,
      api_key_header: auth.api_key_header,
      api_key: auth.api_key,
      username: auth.username,
      password: auth.password,
      client_id: auth.client_id,
      client_secret: auth.client_secret,
      token_url: auth.token_url,
      scopes: auth.scopes,
      openapi_header_pairs: objectToPairs(connData.default_headers),
      openapi_secret_pairs: openApiSecretsToRows(connData.secrets),

      metadata_json: toPrettyJson(record.metadata, "{}"),
    });

    setDrawerOpen(true);
  };

  const handleImportMcpConfig = () => {
    try {
      const parsed = JSON.parse(importConfigText);
      let inferredName = String(form.getFieldValue("name") || "").trim();
      let serverConfig: any = parsed;

      if (parsed?.mcpServers && typeof parsed.mcpServers === "object") {
        const names = Object.keys(parsed.mcpServers);
        if (names.length !== 1) {
          throw new Error("Expected exactly one MCP server in mcpServers.");
        }
        inferredName = inferredName || names[0];
        serverConfig = parsed.mcpServers[names[0]];
      } else {
        const keys = Object.keys(parsed || {});
        if (
          keys.length === 1 &&
          parsed[keys[0]] &&
          typeof parsed[keys[0]] === "object" &&
          (parsed[keys[0]].command || parsed[keys[0]].url)
        ) {
          inferredName = inferredName || keys[0];
          serverConfig = parsed[keys[0]];
        }
      }

      if (!serverConfig || (typeof serverConfig !== "object")) {
        throw new Error("Invalid MCP configuration payload.");
      }

      if (!serverConfig.command && !serverConfig.url) {
        throw new Error("Imported config must include either command (stdio) or url (HTTP/SSE).");
      }

      const inferredMode = serverConfig.url ? (serverConfig.type || "streamable-http") : "stdio";
      const nextMode = inferredMode === "stdio" || inferredMode === "sse" || inferredMode === "streamable-http"
        ? inferredMode
        : "streamable-http";

      form.setFieldsValue({
        connection_type: "mcp",
        name: inferredName,
        mcp_mode: nextMode,
        command: serverConfig.command,
        args_text: formatArgsText(serverConfig.args),
        env_pairs: objectToPairs(serverConfig.env),
        url: serverConfig.url,
        timeout: serverConfig.timeout,
        header_pairs: objectToPairs(serverConfig.headers),
      });

      setImportModalOpen(false);
      setImportConfigText("");
      message.success("MCP config imported.");
    } catch (error: any) {
      message.error(error?.message || "Invalid MCP JSON configuration.");
    }
  };

  const buildConnectionPayload = async () => {
    const values = await form.validateFields();
    const type = values.connection_type;

    if (type !== "mcp" && type !== "openapi") {
      throw new Error("Only MCP and OpenAPI connections are supported here.");
    }

    let connectionData: Record<string, any> = {};

    if (type === "mcp") {
      const mode = values.mcp_mode || "streamable-http";
      connectionData.type = mode;

      if (mode === "stdio") {
        if (values.command) connectionData.command = values.command;

        const args = parseArgsText(values.args_text);
        if (args.length > 0) connectionData.args = args;

        const env = pairsToObject(values.env_pairs);
        if (Object.keys(env).length > 0) connectionData.env = env;
      } else {
        if (values.url) connectionData.url = values.url;
        if (values.timeout) connectionData.timeout = values.timeout;

        const headers = pairsToObject(values.header_pairs);
        if (values.mcp_api_key) {
          const headerName = String(values.auth_header_name || "Authorization").trim() || "Authorization";
          const tokenValue = String(values.mcp_api_key);
          headers[headerName] = headerName.toLowerCase() === "authorization" && !tokenValue.toLowerCase().startsWith("bearer ")
            ? `Bearer ${tokenValue}`
            : tokenValue;
        }
        if (Object.keys(headers).length > 0) connectionData.headers = headers;
      }
    }

    if (type === "openapi") {
      if (values.base_url) connectionData.base_url = values.base_url;
      const specMode = values.openapi_spec_mode || "url";
      if (specMode === "url" && values.spec_url) connectionData.spec_url = values.spec_url;
      if (specMode === "text" && values.spec_text) connectionData.spec_text = values.spec_text;

      const authType = values.openapi_auth_type || "none";
      if (authType !== "none") {
        const auth: Record<string, any> = { type: authType };
        if (values.bearer_token) auth.bearer_token = values.bearer_token;
        if (values.api_key) auth.api_key = values.api_key;
        if (values.api_key_header) auth.api_key_header = values.api_key_header;
        if (values.username) auth.username = values.username;
        if (values.password) auth.password = values.password;
        if (values.client_id) auth.client_id = values.client_id;
        if (values.client_secret) auth.client_secret = values.client_secret;
        if (values.token_url) auth.token_url = values.token_url;
        if (values.scopes) auth.scopes = values.scopes;
        connectionData.auth = auth;
      }

      const secrets = openApiRowsToSecrets(values.openapi_secret_pairs);
      if (Object.keys(secrets).length > 0) connectionData.secrets = secrets;

      const defaultHeaders = pairsToObject(values.openapi_header_pairs);
      if (Object.keys(defaultHeaders).length > 0) connectionData.default_headers = defaultHeaders;
    }

    return {
      name: values.name,
      description: values.description,
      description_for_agent: values.description_for_agent,
      connection_type: type,
      connection_data: connectionData,
      is_active: values.is_active ?? true,
      is_default: values.is_default ?? false,
      metadata: parseJsonField(values.metadata_json, "Metadata", {}),
    };
  };

  const handleSaveConnection = async () => {
    try {
      const payload = await buildConnectionPayload();
      if (editingConnection) {
        await updateConnection.mutateAsync({ id: editingConnection.id, data: payload });
        message.success("Connection updated");
      } else {
        if (!ensureAccountForSuperAdminWrite()) return;
        await createConnection.mutateAsync({ data: payload, account_id: accountFilter });
        message.success("Connection created");
      }
      setDrawerOpen(false);
      setEditingConnection(null);
      form.resetFields();
      await refetchConnections();
    } catch (err: any) {
      if (err?.message) message.error(err.message);
    }
  };

  const handleTest = async (id: string) => {
    setTestResults((prev) => ({ ...prev, [id]: { status: "testing" } }));
    try {
      const result = await testConnection.mutateAsync(id);
      setTestResults((prev) => ({ ...prev, [id]: result }));
      if (result?.status === "ok") message.success("Connection test succeeded.");
      else message.warning(result?.message || "Connection test completed with warnings.");
    } catch {
      setTestResults((prev) => ({ ...prev, [id]: { status: "error", message: "Test failed" } }));
      message.error("Connection test failed.");
    }
  };

  const openCreateCatalogModal = () => {
    setEditingIntegrationCatalogItem(null);
    catalogForm.resetFields();
    catalogForm.setFieldsValue({
      integration_key: "",
      provider: "composio",
      name: "",
      description: "",
      toolkit: "",
      auth_config_id: "",
      icon: "",
      color: "",
      is_active: true,
    });
    setIntegrationModalOpen(true);
  };

  const openEditCatalogModal = (record: any) => {
    setEditingIntegrationCatalogItem(record);
    catalogForm.resetFields();
    catalogForm.setFieldsValue({
      integration_key: record.integration_key,
      provider: record.provider,
      name: record.name,
      description: record.description,
      toolkit: record.toolkit,
      auth_config_id: record.auth_config_id,
      icon: record.icon,
      color: record.color,
      is_active: record.is_active,
    });
    setIntegrationModalOpen(true);
  };

  const saveCatalogEntry = async () => {
    const values = await catalogForm.validateFields();
    if (editingIntegrationCatalogItem?.id) {
      await updateCatalogEntry.mutateAsync({ id: editingIntegrationCatalogItem.id, data: values });
      message.success("Integration catalog entry updated.");
    } else {
      await createCatalogEntry.mutateAsync(values);
      message.success("Integration catalog entry created.");
    }
    setIntegrationModalOpen(false);
    setEditingIntegrationCatalogItem(null);
    catalogForm.resetFields();
    await refetchCatalog();
    await refetchEnabled();
  };

  const connectionColumns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      sorter: (a: any, b: any) => String(a.name || "").localeCompare(String(b.name || "")),
    },
    {
      title: "Type",
      key: "type",
      render: (_: any, record: any) => (
        <Space>
          <Tag color={record.connection_type === "mcp" ? "blue" : "green"}>{record.connection_type}</Tag>
          {record.connection_type === "mcp" && record.connection_data?.type && (
            <Tag color="cyan">{record.connection_data.type}</Tag>
          )}
        </Space>
      ),
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      ellipsis: true,
      render: (v: any) => v || "-",
    },
    {
      title: "Active",
      dataIndex: "is_active",
      key: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "Active" : "Inactive"}</Tag>,
    },
    {
      title: "Test",
      key: "test",
      render: (_: any, record: any) => {
        const result = testResults[record.id];
        if (result?.status === "testing") return <LoadingOutlined />;
        if (result?.status === "ok") return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
        return (
          <Button size="small" onClick={() => handleTest(record.id)}>
            Test
          </Button>
        );
      },
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openForEdit(record)} />
          <Popconfirm
            title="Delete Connection"
            description={`Delete "${record.name}"?`}
            onConfirm={async () => {
              await deleteConnection.mutateAsync(record.id);
              message.success("Connection deleted");
              await refetchConnections();
            }}
          >
            <Button size="small" icon={<DeleteOutlined />} danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const integrationColumns = [
    { title: "Name", dataIndex: "name", key: "name" },
    { title: "Key", dataIndex: "integration_key", key: "integration_key" },
    { title: "Toolkit", dataIndex: "toolkit", key: "toolkit", render: (v: string) => v || "-" },
    {
      title: "Catalog Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "active" : "inactive"}</Tag>,
    },
    {
      title: "Visible in Copilot",
      key: "enabled",
      render: (_: any, record: any) => {
        const id = String(record.id || "");
        const enabled = enabledIntegrationIds.includes(id);
        return (
          <Switch
            checked={enabled}
            disabled={!canWriteAccountScoped || !record.is_active || updateEnabledIntegrations.isPending}
            onChange={(checked) => toggleEnabledIntegration(id, checked)}
          />
        );
      },
    },
  ];

  if (isSuperAdmin) {
    integrationColumns.push({
      title: "Catalog Actions",
      key: "catalog_actions",
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" onClick={() => openEditCatalogModal(record)}>Edit</Button>
          <Popconfirm
            title="Disable integration"
            description="Disable this integration in catalog?"
            onConfirm={async () => {
              await deleteCatalogEntry.mutateAsync({ id: record.id, hardDelete: false });
              message.success("Integration catalog entry disabled.");
              await refetchCatalog();
              await refetchEnabled();
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    } as any);
  }

  return (
    <div style={{ width: "100%" }}>
      {isSuperAdmin && (
        <div style={{ marginBottom: 16 }}>
          <Select
            placeholder="Filter by account"
            allowClear
            style={{ width: 360 }}
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

      <Alert
        type="info"
        showIcon
        message="Connections & Tools"
        description="This page follows alchemi-web integrations behavior: MCP and OpenAPI are configured as account tools, while Composio integrations are visibility toggles (catalog + enable/disable), not runtime OAuth connections here."
        style={{ marginBottom: 16 }}
      />

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab="MCP" key="mcp">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "flex-end" }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateConnectionDrawer}>
              Add MCP Tool
            </Button>
          </div>
          <Table dataSource={connections} columns={connectionColumns as any} rowKey="id" loading={connectionsLoading} />
        </TabPane>

        <TabPane tab="OpenAPI" key="openapi">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "flex-end" }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateConnectionDrawer}>
              Add OpenAPI Spec
            </Button>
          </div>
          <Table dataSource={connections} columns={connectionColumns as any} rowKey="id" loading={connectionsLoading} />
        </TabPane>

        <TabPane tab="Integrations" key="integrations">
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            {!canWriteAccountScoped && (
              <Alert
                type="warning"
                showIcon
                message="Select an account"
                description="Choose an account to manage which Composio integrations are visible to Copilot users."
              />
            )}

            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <Space>
                <Button onClick={() => { refetchCatalog(); refetchEnabled(); }}>Refresh</Button>
                {isSuperAdmin && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={openCreateCatalogModal}>
                    Add Catalog Integration
                  </Button>
                )}
              </Space>
            </div>

            <Table
              rowKey="id"
              loading={catalogLoading || enabledLoading}
              dataSource={integrationCatalog}
              columns={integrationColumns as any}
              pagination={{ pageSize: 10 }}
            />

            <Alert
              type="success"
              showIcon
              message="Composio is enablement-only in Cockpit"
              description="OAuth connection happens in product clients (alchemi-web/alchemi-ai workspaces). Cockpit controls which integrations are exposed to each account."
            />
          </Space>
        </TabPane>
      </Tabs>

      <Drawer
        title={editingConnection ? "Edit Connection" : "Create Connection"}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setEditingConnection(null);
        }}
        width={760}
        extra={
          <Button type="primary" onClick={handleSaveConnection} loading={createConnection.isPending || updateConnection.isPending}>
            {editingConnection ? "Update" : "Create"}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="connection_type" label="Type" initialValue={activeTab === "openapi" ? "openapi" : "mcp"}>
            <Select
              options={[{ label: "MCP", value: "mcp" }, { label: "OpenAPI", value: "openapi" }]}
              disabled={!!editingConnection}
            />
          </Form.Item>

          <Form.Item name="name" label="Name" rules={[{ required: true }]}> 
            <Input placeholder={connectionType === "mcp" ? "e.g. File System Tool" : "e.g. CRM API"} />
          </Form.Item>

          <Form.Item name="description_for_agent" label="Description for Agent">
            <TextArea rows={2} placeholder="How the AI agent should use this connection" />
          </Form.Item>

          <Form.Item name="description" label="Internal Description">
            <TextArea rows={2} />
          </Form.Item>

          <Space size={24} style={{ width: "100%", justifyContent: "space-between" }}>
            <Form.Item name="is_active" label="Active" valuePropName="checked" initialValue>
              <Switch />
            </Form.Item>
            <Form.Item name="is_default" label="Default" valuePropName="checked" initialValue={false}>
              <Switch />
            </Form.Item>
          </Space>

          {connectionType === "mcp" && (
            <>
              <Space style={{ width: "100%", justifyContent: "space-between" }}>
                <Form.Item name="mcp_mode" label="MCP Mode" initialValue="streamable-http" style={{ flex: 1 }}>
                  <Select options={mcpModeOptions} />
                </Form.Item>
                <Button style={{ marginTop: 30 }} onClick={() => setImportModalOpen(true)}>
                  Import MCP JSON
                </Button>
              </Space>

              {mcpMode === "stdio" ? (
                <>
                  <Form.Item name="command" label="Command" rules={[{ required: true }]}> 
                    <Input placeholder="npx" />
                  </Form.Item>

                  <Form.Item name="args_text" label="Arguments (one per line or JSON array)">
                    <TextArea rows={3} placeholder={`-y\n@modelcontextprotocol/server-filesystem\n/workspace`} />
                  </Form.Item>

                  <Form.Item label="Environment Variables">
                    <Form.List name="env_pairs">
                      {(fields, { add, remove }) => (
                        <Space direction="vertical" style={{ width: "100%" }}>
                          {fields.map((field) => (
                            <Space key={field.key} align="start" style={{ display: "flex" }}>
                              <Form.Item name={[field.name, "key"]} style={{ width: 220 }}>
                                <Input placeholder="API_KEY" />
                              </Form.Item>
                              <Form.Item name={[field.name, "value"]} style={{ width: 320 }}>
                                <Input.Password placeholder="value" />
                              </Form.Item>
                              <Button danger onClick={() => remove(field.name)}>Remove</Button>
                            </Space>
                          ))}
                          <Button icon={<PlusOutlined />} onClick={() => add({ key: "", value: "" })}>
                            Add Variable
                          </Button>
                        </Space>
                      )}
                    </Form.List>
                  </Form.Item>
                </>
              ) : (
                <>
                  <Form.Item name="url" label="Server URL" rules={[{ required: true }]}> 
                    <Input placeholder="https://mcp-server.example.com/mcp" />
                  </Form.Item>

                  <Form.Item name="timeout" label="Timeout (ms)">
                    <InputNumber min={1000} step={1000} style={{ width: "100%" }} />
                  </Form.Item>

                  <Form.Item name="auth_header_name" label="Auth Header Name" initialValue="Authorization">
                    <Input placeholder="Authorization" />
                  </Form.Item>

                  <Form.Item name="mcp_api_key" label="API Key / Token (optional helper field)">
                    <Input.Password placeholder="Stored securely; masked on reads" />
                  </Form.Item>

                  <Form.Item label="Headers">
                    <Form.List name="header_pairs">
                      {(fields, { add, remove }) => (
                        <Space direction="vertical" style={{ width: "100%" }}>
                          {fields.map((field) => (
                            <Space key={field.key} align="start" style={{ display: "flex" }}>
                              <Form.Item name={[field.name, "key"]} style={{ width: 220 }}>
                                <Input placeholder="Header name" />
                              </Form.Item>
                              <Form.Item name={[field.name, "value"]} style={{ width: 320 }}>
                                <Input placeholder="Header value" />
                              </Form.Item>
                              <Button danger onClick={() => remove(field.name)}>Remove</Button>
                            </Space>
                          ))}
                          <Button icon={<PlusOutlined />} onClick={() => add({ key: "", value: "" })}>
                            Add Header
                          </Button>
                        </Space>
                      )}
                    </Form.List>
                  </Form.Item>
                </>
              )}
            </>
          )}

          {connectionType === "openapi" && (
            <>
              <Form.Item name="base_url" label="Base URL" rules={[{ required: true }]}> 
                <Input placeholder="https://api.example.com" />
              </Form.Item>

              <Form.Item name="openapi_spec_mode" label="Spec Source" initialValue="url">
                <Select options={[{ label: "Spec URL", value: "url" }, { label: "Spec Text", value: "text" }]} />
              </Form.Item>

              {openApiSpecMode === "url" ? (
                <Form.Item name="spec_url" label="Spec URL">
                  <Input placeholder="https://api.example.com/openapi.json" />
                </Form.Item>
              ) : (
                <Form.Item name="spec_text" label="Spec Text (JSON/YAML)">
                  <TextArea rows={5} placeholder="Paste OpenAPI JSON or YAML" />
                </Form.Item>
              )}

              <Form.Item name="openapi_auth_type" label="Auth Type" initialValue="none">
                <Select options={openApiAuthOptions} />
              </Form.Item>

              {openApiAuthType === "bearer" && (
                <Form.Item name="bearer_token" label="Bearer Token">
                  <Input.Password />
                </Form.Item>
              )}

              {openApiAuthType === "api_key" && (
                <>
                  <Form.Item name="api_key_header" label="API Key Header" initialValue="X-API-Key">
                    <Input />
                  </Form.Item>
                  <Form.Item name="api_key" label="API Key">
                    <Input.Password />
                  </Form.Item>
                </>
              )}

              {openApiAuthType === "basic" && (
                <>
                  <Form.Item name="username" label="Username">
                    <Input />
                  </Form.Item>
                  <Form.Item name="password" label="Password">
                    <Input.Password />
                  </Form.Item>
                </>
              )}

              {openApiAuthType === "oauth2" && (
                <>
                  <Form.Item name="client_id" label="Client ID">
                    <Input />
                  </Form.Item>
                  <Form.Item name="client_secret" label="Client Secret">
                    <Input.Password />
                  </Form.Item>
                  <Form.Item name="token_url" label="Token URL">
                    <Input />
                  </Form.Item>
                  <Form.Item name="scopes" label="Scopes">
                    <Input placeholder="read write" />
                  </Form.Item>
                </>
              )}

              <Form.Item label="Secrets & Variables">
                <Form.List name="openapi_secret_pairs">
                  {(fields, { add, remove }) => (
                    <Space direction="vertical" style={{ width: "100%" }}>
                      {fields.map((field) => (
                        <Space key={field.key} align="start" style={{ display: "flex" }}>
                          <Form.Item name={[field.name, "key"]} style={{ width: 180 }}>
                            <Input placeholder="SECRET_NAME" />
                          </Form.Item>
                          <Form.Item name={[field.name, "value"]} style={{ width: 220 }}>
                            <Input.Password placeholder="secret value" />
                          </Form.Item>
                          <Form.Item name={[field.name, "location"]} style={{ width: 140 }} initialValue="header">
                            <Select options={openApiSecretLocationOptions} />
                          </Form.Item>
                          <Button danger onClick={() => remove(field.name)}>Remove</Button>
                        </Space>
                      ))}
                      <Button icon={<PlusOutlined />} onClick={() => add({ key: "", value: "", location: "header" })}>
                        Add Secret
                      </Button>
                    </Space>
                  )}
                </Form.List>
              </Form.Item>

              <Form.Item label="Default Headers">
                <Form.List name="openapi_header_pairs">
                  {(fields, { add, remove }) => (
                    <Space direction="vertical" style={{ width: "100%" }}>
                      {fields.map((field) => (
                        <Space key={field.key} align="start" style={{ display: "flex" }}>
                          <Form.Item name={[field.name, "key"]} style={{ width: 220 }}>
                            <Input placeholder="Header name" />
                          </Form.Item>
                          <Form.Item name={[field.name, "value"]} style={{ width: 320 }}>
                            <Input placeholder="Header value" />
                          </Form.Item>
                          <Button danger onClick={() => remove(field.name)}>Remove</Button>
                        </Space>
                      ))}
                      <Button icon={<PlusOutlined />} onClick={() => add({ key: "", value: "" })}>
                        Add Header
                      </Button>
                    </Space>
                  )}
                </Form.List>
              </Form.Item>
            </>
          )}

          <Form.Item name="metadata_json" label="Metadata (JSON object)" initialValue="{}">
            <TextArea rows={3} placeholder='{"source":"copilot-ui"}' />
          </Form.Item>
        </Form>
      </Drawer>

      <Modal
        title="Import MCP Config"
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        onOk={handleImportMcpConfig}
        okText="Import"
      >
        <p style={{ marginBottom: 8 }}>
          Paste standard MCP JSON (`mcpServers` format) or a single server config object.
        </p>
        <TextArea
          rows={12}
          value={importConfigText}
          onChange={(e) => setImportConfigText(e.target.value)}
          placeholder={`{\n  "mcpServers": {\n    "filesystem": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],\n      "env": { "API_KEY": "..." }\n    }\n  }\n}`}
        />
      </Modal>

      <Modal
        title={editingIntegrationCatalogItem ? "Edit Integration Catalog Entry" : "Add Integration Catalog Entry"}
        open={integrationModalOpen}
        onCancel={() => {
          setIntegrationModalOpen(false);
          setEditingIntegrationCatalogItem(null);
        }}
        onOk={saveCatalogEntry}
        okText={editingIntegrationCatalogItem ? "Update" : "Create"}
        confirmLoading={createCatalogEntry.isPending || updateCatalogEntry.isPending}
      >
        <Form form={catalogForm} layout="vertical">
          <Form.Item name="integration_key" label="Integration Key" rules={[{ required: true }]}> 
            <Input placeholder="gmail" />
          </Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}> 
            <Input placeholder="Gmail" />
          </Form.Item>
          <Form.Item name="provider" label="Provider" initialValue="composio">
            <Input placeholder="composio" />
          </Form.Item>
          <Form.Item name="toolkit" label="Toolkit">
            <Input placeholder="GMAIL" />
          </Form.Item>
          <Form.Item name="auth_config_id" label="Auth Config ID">
            <Input placeholder="ac_xxxxx" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="icon" label="Icon">
            <Input placeholder="Mail" />
          </Form.Item>
          <Form.Item name="color" label="Color">
            <Input placeholder="text-red-500" />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotConnectionsPage;
