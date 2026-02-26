"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Modal, Form, Input, Select, Tag, message } from "antd";
import { RobotOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import CopilotJsonModal from "@/components/copilot/CopilotJsonModal";
import { agentApi, modelApi, guardrailApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

const statusColors: Record<string, string> = {
  active: "green",
  inactive: "default",
  draft: "orange",
};

export default function CopilotAgentsPage() {
  const { accessToken } = useAuthorized();

  const [agents, setAgents] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [guardrails, setGuardrails] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const [modal, setModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [jsonModal, setJsonModal] = useState<{ open: boolean; data: any }>({ open: false, data: null });
  const [form] = Form.useForm();

  // ---- Data loading ----

  const loadAgents = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const d = await agentApi.list(accessToken);
      setAgents(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  const loadReferenceData = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [catalogResp, guardrailResp] = await Promise.all([
        modelApi.listCatalog(accessToken),
        guardrailApi.listConfigs(accessToken),
      ]);
      setModels(Array.isArray(catalogResp) ? catalogResp : []);
      setGuardrails(Array.isArray(guardrailResp) ? guardrailResp : []);
    } catch {
      // Reference data is non-critical; silently degrade
    }
  }, [accessToken]);

  useEffect(() => {
    loadAgents();
    loadReferenceData();
  }, [loadAgents, loadReferenceData]);

  // ---- Stats ----

  const activeCount = agents.filter((a) => a.status === "active").length;
  const inactiveCount = agents.filter((a) => a.status !== "active").length;

  // ---- CRUD handlers ----

  const handleSave = async () => {
    if (!accessToken) return;
    try {
      const values = await form.validateFields();

      // Parse config JSON if provided
      if (values.config && typeof values.config === "string") {
        try {
          values.config = JSON.parse(values.config);
        } catch {
          message.error("Config must be valid JSON");
          return;
        }
      }

      if (modal.editing) {
        await agentApi.update(accessToken, modal.editing.agent_id, values);
        message.success("Agent updated");
      } else {
        await agentApi.create(accessToken, values);
        message.success("Agent created");
      }
      setModal({ open: false, editing: null });
      form.resetFields();
      loadAgents();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  const handleDelete = async (record: any) => {
    if (!accessToken) return;
    await agentApi.delete(accessToken, record.agent_id);
    loadAgents();
  };

  const handleEdit = (record: any) => {
    const values = { ...record };
    // Stringify config for the TextArea
    if (values.config && typeof values.config === "object") {
      values.config = JSON.stringify(values.config, null, 2);
    }
    form.setFieldsValue(values);
    setModal({ open: true, editing: record });
  };

  const handleRowClick = (record: any) => {
    setJsonModal({ open: true, data: record });
  };

  // ---- Select options ----

  const modelOptions = models.map((m: any) => ({
    label: m.model_name ?? m.model_code ?? m.name ?? m.id,
    value: m.model_code ?? m.model_name ?? m.name ?? m.id,
  }));

  const guardrailOptions = guardrails.map((g: any) => ({
    label: g.name ?? g.guard_type ?? g.guardrail_id ?? g.id,
    value: g.guardrail_id ?? g.guard_type ?? g.id,
  }));

  // ---- Render ----

  return (
    <CopilotPageShell
      title="Agents"
      subtitle="Configure and manage AI agents with custom models, tools, guardrails, and system prompts."
      icon={<RobotOutlined />}
      onRefresh={loadAgents}
    >
      <CopilotStatsRow
        stats={[
          { title: "Total Agents", value: agents.length, loading },
          { title: "Active", value: activeCount, loading },
          { title: "Inactive", value: inactiveCount, loading },
        ]}
      />

      <CopilotCrudTable
        dataSource={agents}
        rowKey="agent_id"
        loading={loading}
        searchFields={["agent_id", "name", "description", "status", "default_model"]}
        addLabel="Create Agent"
        onAdd={() => {
          form.resetFields();
          setModal({ open: true, editing: null });
        }}
        onEdit={handleEdit}
        onDelete={handleDelete}
        columns={[
          {
            title: "Agent ID",
            dataIndex: "agent_id",
            key: "agent_id",
            render: (v: string, record: any) => (
              <a onClick={() => handleRowClick(record)}>{v}</a>
            ),
          },
          { title: "Name", dataIndex: "name", key: "name" },
          { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
          {
            title: "Status",
            dataIndex: "status",
            key: "status",
            render: (v: string) => (
              <Tag color={statusColors[v] ?? "default"}>{v ?? "draft"}</Tag>
            ),
          },
          { title: "Default Model", dataIndex: "default_model", key: "default_model" },
          {
            title: "Tools",
            dataIndex: "tools",
            key: "tools",
            render: (v: any) => (Array.isArray(v) ? v.length : 0),
          },
          {
            title: "Guardrails",
            dataIndex: "guardrail_ids",
            key: "guardrail_ids",
            render: (v: any) =>
              Array.isArray(v) && v.length > 0
                ? v.map((g: string) => (
                    <Tag key={g} color="blue">
                      {g}
                    </Tag>
                  ))
                : "—",
          },
          {
            title: "Created",
            dataIndex: "created_at",
            key: "created_at",
            render: (v: string) => (v ? new Date(v).toLocaleDateString() : "—"),
          },
        ]}
      />

      {/* Create / Edit modal */}
      <Modal
        title={modal.editing ? "Edit Agent" : "Create Agent"}
        open={modal.open}
        onOk={handleSave}
        onCancel={() => setModal({ open: false, editing: null })}
        width={700}
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label="Name" rules={[{ required: true, message: "Agent name is required" }]}>
            <Input placeholder="e.g. Code Assistant" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} placeholder="Brief description of the agent" />
          </Form.Item>
          <Form.Item name="status" label="Status" initialValue="draft">
            <Select
              options={[
                { label: "Active", value: "active" },
                { label: "Inactive", value: "inactive" },
                { label: "Draft", value: "draft" },
              ]}
            />
          </Form.Item>
          <Form.Item name="default_model" label="Default Model">
            <Select
              showSearch
              allowClear
              placeholder="Select a model"
              options={modelOptions}
              filterOption={(input, option) =>
                String(option?.label ?? "")
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item name="system_prompt" label="System Prompt">
            <Input.TextArea rows={5} placeholder="System prompt for the agent" />
          </Form.Item>
          <Form.Item name="tools" label="Tools">
            <Select mode="tags" placeholder="Enter tool identifiers" tokenSeparators={[","]} />
          </Form.Item>
          <Form.Item name="guardrail_ids" label="Guardrails">
            <Select
              mode="multiple"
              allowClear
              placeholder="Select guardrails"
              options={guardrailOptions}
              filterOption={(input, option) =>
                String(option?.label ?? "")
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item name="knowledge_file_ids" label="Knowledge File IDs">
            <Select mode="tags" placeholder="Enter knowledge file IDs" tokenSeparators={[","]} />
          </Form.Item>
          <Form.Item name="config" label="Config (JSON)">
            <Input.TextArea
              rows={4}
              placeholder={'{\n  "temperature": 0.7,\n  "max_tokens": 4096\n}'}
              style={{ fontFamily: "monospace", fontSize: 12 }}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Detail JSON modal */}
      <CopilotJsonModal
        open={jsonModal.open}
        title="Agent Configuration"
        data={jsonModal.data}
        onClose={() => setJsonModal({ open: false, data: null })}
      />
    </CopilotPageShell>
  );
}
