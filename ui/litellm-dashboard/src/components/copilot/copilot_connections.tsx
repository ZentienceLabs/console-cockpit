import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Space, Tag, Typography } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  copilotConnectionList,
  copilotConnectionCreate,
  copilotConnectionUpdate,
  copilotConnectionDelete,
} from "../networking";
import NotificationsManager from "../molecules/notifications_manager";

const { TextArea } = Input;
const { Title } = Typography;

interface Connection {
  id: string;
  name: string;
  type?: string;
  status?: string;
  workspace_id?: string;
  account_id?: string;
  config?: any;
  created_at?: string;
  updated_at?: string;
}

interface CopilotConnectionsProps {
  accessToken: string | null;
  userRole?: string;
  userID?: string | null;
}

const CopilotConnections: React.FC<CopilotConnectionsProps> = ({ accessToken }) => {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConnection, setEditingConnection] = useState<Connection | null>(null);
  const [form] = Form.useForm();

  const fetchConnections = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const data = await copilotConnectionList(accessToken);
      setConnections(data.connections || data || []);
    } catch (error) {
      console.error("Error fetching connections:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConnections();
  }, [accessToken]);

  const handleCreate = () => {
    setEditingConnection(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (conn: Connection) => {
    setEditingConnection(conn);
    form.setFieldsValue({
      name: conn.name,
      type: conn.type,
      status: conn.status || "ACTIVE",
      workspace_id: conn.workspace_id,
      config: conn.config ? JSON.stringify(conn.config, null, 2) : "",
    });
    setModalVisible(true);
  };

  const handleDelete = async (connectionId: string, name: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: `Delete connection "${name}"?`,
      content: "This action cannot be undone.",
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        try {
          await copilotConnectionDelete(accessToken, connectionId);
          NotificationsManager.success(`Connection "${name}" deleted`);
          fetchConnections();
        } catch (error) {
          console.error("Error deleting connection:", error);
        }
      },
    });
  };

  const handleSubmit = async () => {
    if (!accessToken) return;
    try {
      const values = await form.validateFields();
      const payload: any = { ...values };
      if (values.config) {
        try {
          payload.config = JSON.parse(values.config);
        } catch {
          NotificationsManager.error("Config must be valid JSON");
          return;
        }
      }

      if (editingConnection) {
        await copilotConnectionUpdate(accessToken, editingConnection.id, payload);
        NotificationsManager.success(`Connection "${values.name}" updated`);
      } else {
        await copilotConnectionCreate(accessToken, payload);
        NotificationsManager.success(`Connection "${values.name}" created`);
      }
      setModalVisible(false);
      fetchConnections();
    } catch (error) {
      console.error("Error saving connection:", error);
    }
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (text: string) => <span className="font-medium">{text}</span>,
    },
    {
      title: "Type",
      dataIndex: "type",
      key: "type",
      render: (text: string) => <Tag>{text || "-"}</Tag>,
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
      title: "Workspace",
      dataIndex: "workspace_id",
      key: "workspace_id",
      render: (text: string) => text ? <span className="text-xs font-mono">{text.slice(0, 8)}...</span> : "-",
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: Connection) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id, record.name)} />
        </Space>
      ),
    },
  ];

  return (
    <div className="w-full mx-auto max-w-[1200px] p-6">
      <div className="flex justify-between items-center mb-4">
        <Title level={4} className="mb-0">Connections</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchConnections} loading={loading}>Refresh</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>Add Connection</Button>
        </Space>
      </div>

      <Table
        dataSource={connections}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        size="small"
      />

      <Modal
        title={editingConnection ? "Edit Connection" : "Create Connection"}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        okText={editingConnection ? "Update" : "Create"}
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="Connection name" />
          </Form.Item>
          <Form.Item name="type" label="Type">
            <Input placeholder="Connection type (e.g. API, OAuth)" />
          </Form.Item>
          <Form.Item name="workspace_id" label="Workspace ID">
            <Input placeholder="Associated workspace ID (optional)" />
          </Form.Item>
          <Form.Item name="status" label="Status" initialValue="ACTIVE">
            <Select options={[
              { value: "ACTIVE", label: "Active" },
              { value: "INACTIVE", label: "Inactive" },
            ]} />
          </Form.Item>
          <Form.Item name="config" label="Config (JSON)">
            <TextArea rows={4} placeholder='{"key": "value"}' />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotConnections;
