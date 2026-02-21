import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Space, Tag, Tooltip, Typography, Tabs } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, TeamOutlined } from "@ant-design/icons";
import {
  copilotWorkspaceList,
  copilotWorkspaceCreate,
  copilotWorkspaceUpdate,
  copilotWorkspaceDelete,
  copilotWorkspaceMemberList,
  copilotWorkspaceMemberAdd,
  copilotWorkspaceMemberRemove,
} from "../networking";
import NotificationsManager from "../molecules/notifications_manager";

const { TextArea } = Input;
const { Title } = Typography;

interface Workspace {
  id: string;
  name: string;
  description?: string;
  status?: string;
  account_id?: string;
  current_analysis_state?: string;
  is_mvp_ready?: boolean;
  created_at?: string;
  updated_at?: string;
}

interface WorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  status?: string;
  role_id?: string;
}

interface CopilotWorkspacesProps {
  accessToken: string | null;
  userRole?: string;
  userID?: string | null;
}

const CopilotWorkspaces: React.FC<CopilotWorkspacesProps> = ({ accessToken }) => {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingWorkspace, setEditingWorkspace] = useState<Workspace | null>(null);
  const [form] = Form.useForm();
  const [selectedWorkspace, setSelectedWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [memberModalVisible, setMemberModalVisible] = useState(false);
  const [memberForm] = Form.useForm();

  const fetchWorkspaces = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const data = await copilotWorkspaceList(accessToken);
      setWorkspaces(data.workspaces || data || []);
    } catch (error) {
      console.error("Error fetching workspaces:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkspaces();
  }, [accessToken]);

  const fetchMembers = async (workspaceId: string) => {
    if (!accessToken) return;
    setMembersLoading(true);
    try {
      const data = await copilotWorkspaceMemberList(accessToken, workspaceId);
      setMembers(data.members || data || []);
    } catch (error) {
      console.error("Error fetching members:", error);
    } finally {
      setMembersLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingWorkspace(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (workspace: Workspace) => {
    setEditingWorkspace(workspace);
    form.setFieldsValue({
      name: workspace.name,
      description: workspace.description,
      status: workspace.status || "ACTIVE",
    });
    setModalVisible(true);
  };

  const handleDelete = async (workspaceId: string, name: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: `Delete workspace "${name}"?`,
      content: "This will archive the workspace and all its data.",
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        try {
          await copilotWorkspaceDelete(accessToken, workspaceId);
          NotificationsManager.success(`Workspace "${name}" deleted`);
          fetchWorkspaces();
        } catch (error) {
          console.error("Error deleting workspace:", error);
        }
      },
    });
  };

  const handleSubmit = async () => {
    if (!accessToken) return;
    try {
      const values = await form.validateFields();
      if (editingWorkspace) {
        await copilotWorkspaceUpdate(accessToken, editingWorkspace.id, values);
        NotificationsManager.success(`Workspace "${values.name}" updated`);
      } else {
        await copilotWorkspaceCreate(accessToken, values);
        NotificationsManager.success(`Workspace "${values.name}" created`);
      }
      setModalVisible(false);
      fetchWorkspaces();
    } catch (error) {
      console.error("Error saving workspace:", error);
    }
  };

  const handleViewMembers = (workspace: Workspace) => {
    setSelectedWorkspace(workspace);
    fetchMembers(workspace.id);
  };

  const handleAddMember = async () => {
    if (!accessToken || !selectedWorkspace) return;
    try {
      const values = await memberForm.validateFields();
      await copilotWorkspaceMemberAdd(accessToken, selectedWorkspace.id, values);
      NotificationsManager.success("Member added");
      memberForm.resetFields();
      setMemberModalVisible(false);
      fetchMembers(selectedWorkspace.id);
    } catch (error) {
      console.error("Error adding member:", error);
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    if (!accessToken || !selectedWorkspace) return;
    try {
      await copilotWorkspaceMemberRemove(accessToken, selectedWorkspace.id, memberId);
      NotificationsManager.success("Member removed");
      fetchMembers(selectedWorkspace.id);
    } catch (error) {
      console.error("Error removing member:", error);
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
      title: "Description",
      dataIndex: "description",
      key: "description",
      render: (text: string) => text || "-",
      ellipsis: true,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status: string) => (
        <Tag color={status === "ACTIVE" ? "green" : "default"}>{status || "ACTIVE"}</Tag>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: Workspace) => (
        <Space>
          <Button type="link" icon={<TeamOutlined />} onClick={() => handleViewMembers(record)}>Members</Button>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id, record.name)} />
        </Space>
      ),
    },
  ];

  const memberColumns = [
    { title: "User ID", dataIndex: "user_id", key: "user_id" },
    { title: "Status", dataIndex: "status", key: "status", render: (s: string) => <Tag>{s || "ACTIVE"}</Tag> },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: WorkspaceMember) => (
        <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleRemoveMember(record.id)}>
          Remove
        </Button>
      ),
    },
  ];

  return (
    <div className="w-full mx-auto max-w-[1200px] p-6">
      <div className="flex justify-between items-center mb-4">
        <Title level={4} className="mb-0">Workspaces</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchWorkspaces} loading={loading}>Refresh</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>Add Workspace</Button>
        </Space>
      </div>

      <Table
        dataSource={workspaces}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        size="small"
      />

      {selectedWorkspace && (
        <div className="mt-6 border rounded-lg p-4">
          <div className="flex justify-between items-center mb-3">
            <Title level={5} className="mb-0">Members of "{selectedWorkspace.name}"</Title>
            <Space>
              <Button size="small" onClick={() => setSelectedWorkspace(null)}>Close</Button>
              <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => { memberForm.resetFields(); setMemberModalVisible(true); }}>
                Add Member
              </Button>
            </Space>
          </div>
          <Table dataSource={members} columns={memberColumns} rowKey="id" loading={membersLoading} pagination={false} size="small" />
        </div>
      )}

      <Modal
        title={editingWorkspace ? "Edit Workspace" : "Create Workspace"}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        okText={editingWorkspace ? "Update" : "Create"}
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="Workspace name" />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} placeholder="Description" />
          </Form.Item>
          <Form.Item name="status" label="Status" initialValue="ACTIVE">
            <Select options={[
              { value: "ACTIVE", label: "Active" },
              { value: "ARCHIVED", label: "Archived" },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Add Member"
        open={memberModalVisible}
        onOk={handleAddMember}
        onCancel={() => setMemberModalVisible(false)}
        okText="Add"
      >
        <Form form={memberForm} layout="vertical" className="mt-4">
          <Form.Item name="user_id" label="User ID" rules={[{ required: true }]}>
            <Input placeholder="User ID" />
          </Form.Item>
          <Form.Item name="status" label="Status" initialValue="ACTIVE">
            <Select options={[
              { value: "ACTIVE", label: "Active" },
              { value: "INVITED", label: "Invited" },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotWorkspaces;
