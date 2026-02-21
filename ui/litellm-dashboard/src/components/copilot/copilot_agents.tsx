import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Switch, Space, Tag, Tooltip, Typography } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  copilotAgentDefList,
  copilotAgentDefCreate,
  copilotAgentDefUpdate,
  copilotAgentDefDelete,
} from "../networking";
import NotificationsManager from "../molecules/notifications_manager";

const { TextArea } = Input;
const { Title } = Typography;

interface AgentDef {
  id: string;
  agent_id: string;
  name: string;
  description?: string;
  prompt?: string;
  page?: string;
  categories?: any;
  tags?: string[];
  status?: string;
  availability?: string[];
  provider?: string;
  account_id?: string;
  is_singleton?: boolean;
  is_non_conversational?: boolean;
  created_at?: string;
  updated_at?: string;
}

interface CopilotAgentsProps {
  accessToken: string | null;
  userRole?: string;
  userID?: string | null;
}

const CopilotAgents: React.FC<CopilotAgentsProps> = ({ accessToken, userRole }) => {
  const [agents, setAgents] = useState<AgentDef[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentDef | null>(null);
  const [form] = Form.useForm();

  const fetchAgents = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const data = await copilotAgentDefList(accessToken);
      setAgents(data.agents || data || []);
    } catch (error) {
      console.error("Error fetching copilot agents:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, [accessToken]);

  const handleCreate = () => {
    setEditingAgent(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (agent: AgentDef) => {
    setEditingAgent(agent);
    form.setFieldsValue({
      name: agent.name,
      description: agent.description,
      prompt: agent.prompt,
      page: agent.page,
      status: agent.status || "ACTIVE",
      provider: agent.provider || "PLATFORM",
      is_singleton: agent.is_singleton || false,
      is_non_conversational: agent.is_non_conversational || false,
      tags: agent.tags?.join(", ") || "",
    });
    setModalVisible(true);
  };

  const handleDelete = async (agentId: string, name: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: `Delete agent "${name}"?`,
      content: "This action cannot be undone.",
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        try {
          await copilotAgentDefDelete(accessToken, agentId);
          NotificationsManager.success(`Agent "${name}" deleted`);
          fetchAgents();
        } catch (error) {
          console.error("Error deleting agent:", error);
        }
      },
    });
  };

  const handleSubmit = async () => {
    if (!accessToken) return;
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        tags: values.tags ? values.tags.split(",").map((t: string) => t.trim()).filter(Boolean) : [],
      };

      if (editingAgent) {
        await copilotAgentDefUpdate(accessToken, editingAgent.agent_id || editingAgent.id, payload);
        NotificationsManager.success(`Agent "${values.name}" updated`);
      } else {
        await copilotAgentDefCreate(accessToken, payload);
        NotificationsManager.success(`Agent "${values.name}" created`);
      }
      setModalVisible(false);
      fetchAgents();
    } catch (error) {
      console.error("Error saving agent:", error);
    }
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (text: string, record: AgentDef) => (
        <span className="font-medium">{text}</span>
      ),
    },
    {
      title: "Agent ID",
      dataIndex: "agent_id",
      key: "agent_id",
      render: (text: string) => (
        <Tooltip title={text}>
          <span className="text-xs text-gray-500 font-mono">{text?.slice(0, 12)}...</span>
        </Tooltip>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status: string) => (
        <Tag color={status === "ACTIVE" ? "green" : status === "INACTIVE" ? "red" : "default"}>
          {status || "ACTIVE"}
        </Tag>
      ),
    },
    {
      title: "Provider",
      dataIndex: "provider",
      key: "provider",
      render: (provider: string) => (
        <Tag color={provider === "PLATFORM" ? "blue" : "purple"}>
          {provider || "PLATFORM"}
        </Tag>
      ),
    },
    {
      title: "Page",
      dataIndex: "page",
      key: "page",
      render: (page: string) => page || "-",
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: AgentDef) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.agent_id || record.id, record.name)} />
        </Space>
      ),
    },
  ];

  return (
    <div className="w-full mx-auto max-w-[1200px] p-6">
      <div className="flex justify-between items-center mb-4">
        <Title level={4} className="mb-0">Agent Definitions</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchAgents} loading={loading}>
            Refresh
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            Add Agent
          </Button>
        </Space>
      </div>

      <Table
        dataSource={agents}
        columns={columns}
        rowKey={(record) => record.agent_id || record.id}
        loading={loading}
        pagination={{ pageSize: 20 }}
        size="small"
      />

      <Modal
        title={editingAgent ? "Edit Agent Definition" : "Create Agent Definition"}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={640}
        okText={editingAgent ? "Update" : "Create"}
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="name" label="Name" rules={[{ required: true, message: "Name is required" }]}>
            <Input placeholder="Agent name" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} placeholder="Brief description" />
          </Form.Item>
          <Form.Item name="prompt" label="System Prompt">
            <TextArea rows={4} placeholder="System prompt for this agent" />
          </Form.Item>
          <Form.Item name="page" label="Page">
            <Input placeholder="Page identifier (e.g. chat, code)" />
          </Form.Item>
          <Form.Item name="status" label="Status" initialValue="ACTIVE">
            <Select options={[
              { value: "ACTIVE", label: "Active" },
              { value: "INACTIVE", label: "Inactive" },
              { value: "DRAFT", label: "Draft" },
            ]} />
          </Form.Item>
          <Form.Item name="provider" label="Provider" initialValue="PLATFORM">
            <Select options={[
              { value: "PLATFORM", label: "Platform" },
              { value: "ACCOUNT", label: "Account" },
            ]} />
          </Form.Item>
          <Form.Item name="tags" label="Tags (comma-separated)">
            <Input placeholder="tag1, tag2, tag3" />
          </Form.Item>
          <Form.Item name="is_singleton" label="Singleton" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="is_non_conversational" label="Non-conversational" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotAgents;
