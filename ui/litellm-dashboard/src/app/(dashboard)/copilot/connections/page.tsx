"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Tabs, Modal, Form, Input, Select, Tag, message } from "antd";
import { LinkOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import { connectionApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

export default function CopilotConnectionsPage() {
  const { accessToken } = useAuthorized();

  // MCP Servers
  const [mcpServers, setMcpServers] = useState<any[]>([]);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [mcpModal, setMcpModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [mcpForm] = Form.useForm();

  // OpenAPI
  const [openapi, setOpenapi] = useState<any[]>([]);
  const [openapiLoading, setOpenapiLoading] = useState(false);
  const [openapiModal, setOpenapiModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [openapiForm] = Form.useForm();

  // Integrations
  const [integrations, setIntegrations] = useState<any[]>([]);
  const [integrationsLoading, setIntegrationsLoading] = useState(false);
  const [integrationModal, setIntegrationModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [integrationForm] = Form.useForm();

  // Enablements
  const [enablements, setEnablements] = useState<any[]>([]);
  const [enablementsLoading, setEnablementsLoading] = useState(false);
  const [enablementModal, setEnablementModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [enablementForm] = Form.useForm();

  const loadMcp = useCallback(async () => {
    if (!accessToken) return;
    setMcpLoading(true);
    try { const d = await connectionApi.listMcp(accessToken); setMcpServers(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load MCP servers"); }
    finally { setMcpLoading(false); }
  }, [accessToken]);

  const loadOpenapi = useCallback(async () => {
    if (!accessToken) return;
    setOpenapiLoading(true);
    try { const d = await connectionApi.listOpenapi(accessToken); setOpenapi(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load OpenAPI connections"); }
    finally { setOpenapiLoading(false); }
  }, [accessToken]);

  const loadIntegrations = useCallback(async () => {
    if (!accessToken) return;
    setIntegrationsLoading(true);
    try { const d = await connectionApi.listIntegrations(accessToken); setIntegrations(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load integrations"); }
    finally { setIntegrationsLoading(false); }
  }, [accessToken]);

  const loadEnablements = useCallback(async () => {
    if (!accessToken) return;
    setEnablementsLoading(true);
    try { const d = await connectionApi.listEnablements(accessToken); setEnablements(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load enablements"); }
    finally { setEnablementsLoading(false); }
  }, [accessToken]);

  useEffect(() => { loadMcp(); loadOpenapi(); loadIntegrations(); loadEnablements(); }, [loadMcp, loadOpenapi, loadIntegrations, loadEnablements]);

  const handleRefresh = () => { loadMcp(); loadOpenapi(); loadIntegrations(); loadEnablements(); };

  const handleMcpSave = async () => {
    if (!accessToken) return;
    try {
      const values = await mcpForm.validateFields();
      if (mcpModal.editing) { await connectionApi.updateMcp(accessToken, mcpModal.editing.server_id, values); message.success("MCP server updated"); }
      else { await connectionApi.createMcp(accessToken, values); message.success("MCP server created"); }
      setMcpModal({ open: false, editing: null }); mcpForm.resetFields(); loadMcp();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleOpenapiSave = async () => {
    if (!accessToken) return;
    try {
      const values = await openapiForm.validateFields();
      if (openapiModal.editing) { await connectionApi.updateOpenapi(accessToken, openapiModal.editing.connection_id, values); message.success("OpenAPI connection updated"); }
      else { await connectionApi.createOpenapi(accessToken, values); message.success("OpenAPI connection created"); }
      setOpenapiModal({ open: false, editing: null }); openapiForm.resetFields(); loadOpenapi();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleIntegrationSave = async () => {
    if (!accessToken) return;
    try {
      const values = await integrationForm.validateFields();
      if (integrationModal.editing) { await connectionApi.updateIntegration(accessToken, integrationModal.editing.integration_id, values); message.success("Integration updated"); }
      else { await connectionApi.createIntegration(accessToken, values); message.success("Integration created"); }
      setIntegrationModal({ open: false, editing: null }); integrationForm.resetFields(); loadIntegrations();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleEnablementSave = async () => {
    if (!accessToken) return;
    try {
      const values = await enablementForm.validateFields();
      await connectionApi.upsertEnablement(accessToken, values);
      message.success("Enablement saved");
      setEnablementModal({ open: false, editing: null }); enablementForm.resetFields(); loadEnablements();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const transportType = Form.useWatch("transport_type", mcpForm);

  return (
    <CopilotPageShell title="Connections" subtitle="Manage MCP servers, OpenAPI specs, integrations, and enablements." icon={<LinkOutlined />} onRefresh={handleRefresh}>
      <CopilotStatsRow stats={[
        { title: "MCP Servers", value: mcpServers.length, loading: mcpLoading },
        { title: "OpenAPI Connections", value: openapi.length, loading: openapiLoading },
        { title: "Integrations", value: integrations.length, loading: integrationsLoading },
        { title: "Enablements", value: enablements.length, loading: enablementsLoading },
      ]} />
      <Tabs defaultActiveKey="mcp" items={[
        { key: "mcp", label: `MCP Servers (${mcpServers.length})`, children: (
          <>
            <CopilotCrudTable dataSource={mcpServers} rowKey="server_id" loading={mcpLoading}
              searchFields={["server_id", "name", "transport_type", "url"]}
              addLabel="Add MCP Server"
              onAdd={() => { mcpForm.resetFields(); setMcpModal({ open: true, editing: null }); }}
              onEdit={(r) => { mcpForm.setFieldsValue(r); setMcpModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await connectionApi.deleteMcp(accessToken, r.server_id); loadMcp(); } }}
              columns={[
                { title: "Server ID", dataIndex: "server_id", key: "server_id", ellipsis: true, width: 200 },
                { title: "Name", dataIndex: "name", key: "name" },
                { title: "Transport", dataIndex: "transport_type", key: "transport_type", render: (v: string) => <Tag color="blue">{v ?? "stdio"}</Tag> },
                { title: "URL / Command", key: "endpoint", render: (_: unknown, r: any) => r.url || r.command || "—" },
                { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
                { title: "Active", dataIndex: "is_active", key: "is_active", render: (v: boolean) => <Tag color={v !== false ? "green" : "default"}>{v !== false ? "Yes" : "No"}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
              ]}
            />
            <Modal title={mcpModal.editing ? "Edit MCP Server" : "Add MCP Server"} open={mcpModal.open} onOk={handleMcpSave} onCancel={() => setMcpModal({ open: false, editing: null })} width={600}>
              <Form form={mcpForm} layout="vertical">
                <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
                <Form.Item name="description_for_agent" label="Description for Agent" extra="Describes what this MCP server does, shown to the agent."><Input.TextArea rows={2} /></Form.Item>
                <Form.Item name="transport_type" label="Transport Type" initialValue="stdio">
                  <Select options={[{ value: "stdio", label: "stdio" }, { value: "sse", label: "SSE" }, { value: "streamable-http", label: "Streamable HTTP" }]} />
                </Form.Item>
                {(transportType === "sse" || transportType === "streamable-http") && (
                  <Form.Item name="url" label="URL" rules={[{ required: true }]}><Input placeholder="https://mcp-server.example.com" /></Form.Item>
                )}
                {transportType === "stdio" && (
                  <>
                    <Form.Item name="command" label="Command"><Input placeholder="e.g. npx -y @mcp/server" /></Form.Item>
                    <Form.Item name="args" label="Arguments"><Select mode="tags" placeholder="Command arguments" /></Form.Item>
                  </>
                )}
                <Form.Item name="env" label="Environment Variables" extra="JSON object of key-value pairs."><Input.TextArea rows={2} placeholder='{"KEY": "value"}' /></Form.Item>
                <Form.Item name="is_active" label="Active" initialValue={true}>
                  <Select options={[{ value: true, label: "Active" }, { value: false, label: "Inactive" }]} />
                </Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "openapi", label: `OpenAPI (${openapi.length})`, children: (
          <>
            <CopilotCrudTable dataSource={openapi} rowKey="connection_id" loading={openapiLoading}
              searchFields={["connection_id", "name", "base_url", "auth_type"]}
              addLabel="Add OpenAPI Connection"
              onAdd={() => { openapiForm.resetFields(); setOpenapiModal({ open: true, editing: null }); }}
              onEdit={(r) => { openapiForm.setFieldsValue(r); setOpenapiModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await connectionApi.deleteOpenapi(accessToken, r.connection_id); loadOpenapi(); } }}
              columns={[
                { title: "Connection ID", dataIndex: "connection_id", key: "connection_id", ellipsis: true, width: 200 },
                { title: "Name", dataIndex: "name", key: "name" },
                { title: "Base URL", dataIndex: "base_url", key: "base_url", ellipsis: true },
                { title: "Auth Type", dataIndex: "auth_type", key: "auth_type", render: (v: string) => <Tag>{v ?? "none"}</Tag> },
                { title: "Active", dataIndex: "is_active", key: "is_active", render: (v: boolean) => <Tag color={v !== false ? "green" : "default"}>{v !== false ? "Yes" : "No"}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
              ]}
            />
            <Modal title={openapiModal.editing ? "Edit OpenAPI Connection" : "Add OpenAPI Connection"} open={openapiModal.open} onOk={handleOpenapiSave} onCancel={() => setOpenapiModal({ open: false, editing: null })} width={600}>
              <Form form={openapiForm} layout="vertical">
                <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="description" label="Description"><Input.TextArea rows={2} /></Form.Item>
                <Form.Item name="base_url" label="Base URL" rules={[{ required: true }]}><Input placeholder="https://api.example.com" /></Form.Item>
                <Form.Item name="spec_url" label="Spec URL"><Input placeholder="https://api.example.com/openapi.json" /></Form.Item>
                <Form.Item name="auth_type" label="Auth Type" initialValue="none">
                  <Select options={[{ value: "none" }, { value: "api_key" }, { value: "bearer" }, { value: "oauth2" }]} />
                </Form.Item>
                <Form.Item name="auth_config" label="Auth Config (JSON)"><Input.TextArea rows={2} placeholder='{"api_key": "..."}' /></Form.Item>
                <Form.Item name="is_active" label="Active" initialValue={true}>
                  <Select options={[{ value: true, label: "Active" }, { value: false, label: "Inactive" }]} />
                </Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "integrations", label: `Integrations (${integrations.length})`, children: (
          <>
            <CopilotCrudTable dataSource={integrations} rowKey="integration_id" loading={integrationsLoading}
              searchFields={["integration_id", "provider", "name"]}
              addLabel="Add Integration"
              onAdd={() => { integrationForm.resetFields(); setIntegrationModal({ open: true, editing: null }); }}
              onEdit={(r) => { integrationForm.setFieldsValue(r); setIntegrationModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await connectionApi.deleteIntegration(accessToken, r.integration_id); loadIntegrations(); } }}
              columns={[
                { title: "Integration ID", dataIndex: "integration_id", key: "integration_id", ellipsis: true, width: 200 },
                { title: "Provider", dataIndex: "provider", key: "provider", render: (v: string) => <Tag color="blue">{v}</Tag> },
                { title: "Name", dataIndex: "name", key: "name" },
                { title: "Active", dataIndex: "is_active", key: "is_active", render: (v: boolean) => <Tag color={v !== false ? "green" : "default"}>{v !== false ? "Yes" : "No"}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
              ]}
            />
            <Modal title={integrationModal.editing ? "Edit Integration" : "Add Integration"} open={integrationModal.open} onOk={handleIntegrationSave} onCancel={() => setIntegrationModal({ open: false, editing: null })} width={600}>
              <Form form={integrationForm} layout="vertical">
                <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
                  <Select options={[{ value: "composio", label: "Composio" }, { value: "nango", label: "Nango" }]} />
                </Form.Item>
                <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="config" label="Config (JSON)"><Input.TextArea rows={3} placeholder='{"key": "value"}' /></Form.Item>
                <Form.Item name="is_active" label="Active" initialValue={true}>
                  <Select options={[{ value: true, label: "Active" }, { value: false, label: "Inactive" }]} />
                </Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "enablements", label: `Enablements (${enablements.length})`, children: (
          <>
            <CopilotCrudTable dataSource={enablements} rowKey="enablement_id" loading={enablementsLoading}
              searchFields={["enablement_id", "scope_type", "scope_id", "connection_type", "connection_id"]}
              addLabel="Add Enablement"
              onAdd={() => { enablementForm.resetFields(); setEnablementModal({ open: true, editing: null }); }}
              onEdit={(r) => { enablementForm.setFieldsValue(r); setEnablementModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await connectionApi.deleteEnablement(accessToken, r.enablement_id); loadEnablements(); } }}
              columns={[
                { title: "Enablement ID", dataIndex: "enablement_id", key: "enablement_id", ellipsis: true, width: 200 },
                { title: "Scope Type", dataIndex: "scope_type", key: "scope_type", render: (v: string) => <Tag color="blue">{v}</Tag> },
                { title: "Scope ID", dataIndex: "scope_id", key: "scope_id", ellipsis: true },
                { title: "Connection Type", dataIndex: "connection_type", key: "connection_type", render: (v: string) => <Tag>{v}</Tag> },
                { title: "Connection ID", dataIndex: "connection_id", key: "connection_id", ellipsis: true },
                { title: "Enabled", dataIndex: "enabled", key: "enabled", render: (v: boolean) => <Tag color={v !== false ? "green" : "default"}>{v !== false ? "Yes" : "No"}</Tag> },
              ]}
            />
            <Modal title="Manage Enablement" open={enablementModal.open} onOk={handleEnablementSave} onCancel={() => setEnablementModal({ open: false, editing: null })} width={500}>
              <Form form={enablementForm} layout="vertical">
                <Form.Item name="scope_type" label="Scope Type" rules={[{ required: true }]}>
                  <Select options={[{ value: "ORG", label: "Organization" }, { value: "TEAM", label: "Team" }, { value: "USER", label: "User" }]} />
                </Form.Item>
                <Form.Item name="scope_id" label="Scope ID" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="connection_type" label="Connection Type" rules={[{ required: true }]}>
                  <Select options={[{ value: "mcp", label: "MCP Server" }, { value: "openapi", label: "OpenAPI" }, { value: "integration", label: "Integration" }]} />
                </Form.Item>
                <Form.Item name="connection_id" label="Connection ID" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="enabled" label="Enabled" initialValue={true}>
                  <Select options={[{ value: true, label: "Enabled" }, { value: false, label: "Disabled" }]} />
                </Form.Item>
              </Form>
            </Modal>
          </>
        )},
      ]} />
    </CopilotPageShell>
  );
}
