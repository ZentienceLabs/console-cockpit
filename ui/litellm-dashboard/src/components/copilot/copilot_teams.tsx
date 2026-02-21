import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Space, Tag, Typography, Tabs } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  copilotTeamList,
  copilotTeamCreate,
  copilotTeamUpdate,
  copilotTeamDelete,
  copilotGroupList,
  copilotGroupCreate,
  copilotGroupUpdate,
  copilotGroupDelete,
} from "../networking";
import NotificationsManager from "../molecules/notifications_manager";

const { TextArea } = Input;
const { Title } = Typography;

interface CopilotTeam {
  id: string;
  name: string;
  description?: string;
  status?: string;
  account_id?: string;
  created_at?: string;
  updated_at?: string;
}

interface CopilotGroup {
  id: string;
  name: string;
  group_code?: string;
  description?: string;
  group_type?: string;
  status?: string;
  account_id?: string;
  created_at?: string;
}

interface CopilotTeamsProps {
  accessToken: string | null;
  userRole?: string;
  userID?: string | null;
}

const CopilotTeams: React.FC<CopilotTeamsProps> = ({ accessToken }) => {
  const [teams, setTeams] = useState<CopilotTeam[]>([]);
  const [groups, setGroups] = useState<CopilotGroup[]>([]);
  const [loadingTeams, setLoadingTeams] = useState(false);
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [teamModalVisible, setTeamModalVisible] = useState(false);
  const [groupModalVisible, setGroupModalVisible] = useState(false);
  const [editingTeam, setEditingTeam] = useState<CopilotTeam | null>(null);
  const [editingGroup, setEditingGroup] = useState<CopilotGroup | null>(null);
  const [teamForm] = Form.useForm();
  const [groupForm] = Form.useForm();

  const fetchTeams = async () => {
    if (!accessToken) return;
    setLoadingTeams(true);
    try {
      const data = await copilotTeamList(accessToken);
      setTeams(data.teams || data || []);
    } catch (error) {
      console.error("Error fetching teams:", error);
    } finally {
      setLoadingTeams(false);
    }
  };

  const fetchGroups = async () => {
    if (!accessToken) return;
    setLoadingGroups(true);
    try {
      const data = await copilotGroupList(accessToken);
      setGroups(data.groups || data || []);
    } catch (error) {
      console.error("Error fetching groups:", error);
    } finally {
      setLoadingGroups(false);
    }
  };

  useEffect(() => {
    fetchTeams();
    fetchGroups();
  }, [accessToken]);

  // Teams CRUD
  const handleCreateTeam = () => { setEditingTeam(null); teamForm.resetFields(); setTeamModalVisible(true); };
  const handleEditTeam = (team: CopilotTeam) => {
    setEditingTeam(team);
    teamForm.setFieldsValue({ name: team.name, description: team.description, status: team.status || "ACTIVE" });
    setTeamModalVisible(true);
  };
  const handleDeleteTeam = (teamId: string, name: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: `Delete team "${name}"?`,
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        await copilotTeamDelete(accessToken, teamId);
        NotificationsManager.success(`Team "${name}" deleted`);
        fetchTeams();
      },
    });
  };
  const handleSubmitTeam = async () => {
    if (!accessToken) return;
    const values = await teamForm.validateFields();
    if (editingTeam) {
      await copilotTeamUpdate(accessToken, editingTeam.id, values);
      NotificationsManager.success(`Team "${values.name}" updated`);
    } else {
      await copilotTeamCreate(accessToken, values);
      NotificationsManager.success(`Team "${values.name}" created`);
    }
    setTeamModalVisible(false);
    fetchTeams();
  };

  // Groups CRUD
  const handleCreateGroup = () => { setEditingGroup(null); groupForm.resetFields(); setGroupModalVisible(true); };
  const handleEditGroup = (group: CopilotGroup) => {
    setEditingGroup(group);
    groupForm.setFieldsValue({ name: group.name, group_code: group.group_code, description: group.description, group_type: group.group_type, status: group.status || "ACTIVE" });
    setGroupModalVisible(true);
  };
  const handleDeleteGroup = (groupId: string, name: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: `Delete group "${name}"?`,
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        await copilotGroupDelete(accessToken, groupId);
        NotificationsManager.success(`Group "${name}" deleted`);
        fetchGroups();
      },
    });
  };
  const handleSubmitGroup = async () => {
    if (!accessToken) return;
    const values = await groupForm.validateFields();
    if (editingGroup) {
      await copilotGroupUpdate(accessToken, editingGroup.id, values);
      NotificationsManager.success(`Group "${values.name}" updated`);
    } else {
      await copilotGroupCreate(accessToken, values);
      NotificationsManager.success(`Group "${values.name}" created`);
    }
    setGroupModalVisible(false);
    fetchGroups();
  };

  const teamColumns = [
    { title: "Name", dataIndex: "name", key: "name", render: (t: string) => <span className="font-medium">{t}</span> },
    { title: "Description", dataIndex: "description", key: "description", ellipsis: true, render: (t: string) => t || "-" },
    { title: "Status", dataIndex: "status", key: "status", render: (s: string) => <Tag color={s === "ACTIVE" ? "green" : "default"}>{s || "ACTIVE"}</Tag> },
    {
      title: "Actions", key: "actions",
      render: (_: any, r: CopilotTeam) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEditTeam(r)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteTeam(r.id, r.name)} />
        </Space>
      ),
    },
  ];

  const groupColumns = [
    { title: "Name", dataIndex: "name", key: "name", render: (t: string) => <span className="font-medium">{t}</span> },
    { title: "Code", dataIndex: "group_code", key: "group_code", render: (t: string) => <Tag>{t || "-"}</Tag> },
    { title: "Type", dataIndex: "group_type", key: "group_type", render: (t: string) => t || "-" },
    { title: "Status", dataIndex: "status", key: "status", render: (s: string) => <Tag color={s === "ACTIVE" ? "green" : "default"}>{s || "ACTIVE"}</Tag> },
    {
      title: "Actions", key: "actions",
      render: (_: any, r: CopilotGroup) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEditGroup(r)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteGroup(r.id, r.name)} />
        </Space>
      ),
    },
  ];

  const tabItems = [
    {
      key: "teams",
      label: "Teams",
      children: (
        <>
          <div className="flex justify-end mb-3">
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchTeams} loading={loadingTeams}>Refresh</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateTeam}>Add Team</Button>
            </Space>
          </div>
          <Table dataSource={teams} columns={teamColumns} rowKey="id" loading={loadingTeams} pagination={{ pageSize: 20 }} size="small" />
        </>
      ),
    },
    {
      key: "groups",
      label: "Groups",
      children: (
        <>
          <div className="flex justify-end mb-3">
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchGroups} loading={loadingGroups}>Refresh</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateGroup}>Add Group</Button>
            </Space>
          </div>
          <Table dataSource={groups} columns={groupColumns} rowKey="id" loading={loadingGroups} pagination={{ pageSize: 20 }} size="small" />
        </>
      ),
    },
  ];

  return (
    <div className="w-full mx-auto max-w-[1200px] p-6">
      <Title level={4}>Teams & Groups</Title>
      <Tabs items={tabItems} />

      {/* Team Modal */}
      <Modal title={editingTeam ? "Edit Team" : "Create Team"} open={teamModalVisible} onOk={handleSubmitTeam} onCancel={() => setTeamModalVisible(false)} okText={editingTeam ? "Update" : "Create"}>
        <Form form={teamForm} layout="vertical" className="mt-4">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input placeholder="Team name" /></Form.Item>
          <Form.Item name="description" label="Description"><TextArea rows={2} placeholder="Description" /></Form.Item>
          <Form.Item name="status" label="Status" initialValue="ACTIVE">
            <Select options={[{ value: "ACTIVE", label: "Active" }, { value: "INACTIVE", label: "Inactive" }]} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Group Modal */}
      <Modal title={editingGroup ? "Edit Group" : "Create Group"} open={groupModalVisible} onOk={handleSubmitGroup} onCancel={() => setGroupModalVisible(false)} okText={editingGroup ? "Update" : "Create"}>
        <Form form={groupForm} layout="vertical" className="mt-4">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input placeholder="Group name" /></Form.Item>
          <Form.Item name="group_code" label="Group Code"><Input placeholder="Unique group code" /></Form.Item>
          <Form.Item name="description" label="Description"><TextArea rows={2} /></Form.Item>
          <Form.Item name="group_type" label="Group Type"><Input placeholder="e.g. AGENT, USER" /></Form.Item>
          <Form.Item name="status" label="Status" initialValue="ACTIVE">
            <Select options={[{ value: "ACTIVE", label: "Active" }, { value: "INACTIVE", label: "Inactive" }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotTeams;
