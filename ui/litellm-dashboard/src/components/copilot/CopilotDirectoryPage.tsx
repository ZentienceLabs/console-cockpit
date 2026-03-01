"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  message,
} from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  useAcceptCopilotInvite,
  useCopilotDirectoryGroups,
  useCopilotDirectoryInvites,
  useCopilotDirectoryTeams,
  useCopilotUsers,
  useCreateCopilotDirectoryGroup,
  useCreateCopilotDirectoryTeam,
  useCreateCopilotInvite,
  useCreateCopilotUser,
  useDeleteCopilotDirectoryGroup,
  useDeleteCopilotDirectoryTeam,
  useRejectCopilotInvite,
  useReconcileCopilotIdentityUsers,
  useUpdateCopilotDirectoryGroup,
  useUpdateCopilotDirectoryTeam,
  useUpdateCopilotMembership,
  useUpdateCopilotUser,
} from "@/app/(dashboard)/hooks/copilot/useCopilotDirectory";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

const roleOptions = [
  { label: "Admin", value: "ADMIN" },
  { label: "User", value: "USER" },
  { label: "Member", value: "MEMBER" },
  { label: "Viewer", value: "VIEWER" },
  { label: "Guest", value: "GUEST" },
];

const inviteStatusColors: Record<string, string> = {
  PENDING: "processing",
  ACCEPTED: "green",
  DECLINED: "red",
  EXPIRED: "orange",
  CANCELLED: "default",
};

const CopilotDirectoryPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>(accountId || undefined);
  const [directorySource, setDirectorySource] = useState<"identity" | "copilot">("identity");

  const [userDrawerOpen, setUserDrawerOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<any>(null);
  const [userForm] = Form.useForm();

  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<any>(null);
  const [groupForm] = Form.useForm();

  const [teamModalOpen, setTeamModalOpen] = useState(false);
  const [editingTeam, setEditingTeam] = useState<any>(null);
  const [teamForm] = Form.useForm();

  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteForm] = Form.useForm();
  const [inviteStatusFilter, setInviteStatusFilter] = useState<string | undefined>();

  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();
  const accounts = accountData?.accounts ?? [];

  useEffect(() => {
    if (isSuperAdmin && !selectedAccountId && accounts.length > 0) {
      setSelectedAccountId(accounts[0].account_id);
    }
  }, [accounts, isSuperAdmin, selectedAccountId]);

  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;

  const usersQuery = useCopilotUsers({
    account_id: accountFilter,
    source: directorySource,
    include_memberships: true,
    limit: 500,
    offset: 0,
  });
  const groupsQuery = useCopilotDirectoryGroups({
    account_id: accountFilter,
    source: directorySource,
    include_teams: true,
    limit: 500,
    offset: 0,
  });
  const teamsQuery = useCopilotDirectoryTeams({
    account_id: accountFilter,
    source: directorySource,
    include_group: true,
    limit: 500,
    offset: 0,
  });
  const invitesQuery = useCopilotDirectoryInvites({
    account_id: accountFilter,
    status: inviteStatusFilter,
    limit: 500,
    offset: 0,
  });

  const createUser = useCreateCopilotUser();
  const updateUser = useUpdateCopilotUser();
  const updateMembership = useUpdateCopilotMembership();

  const createGroup = useCreateCopilotDirectoryGroup();
  const updateGroup = useUpdateCopilotDirectoryGroup();
  const deleteGroup = useDeleteCopilotDirectoryGroup();

  const createTeam = useCreateCopilotDirectoryTeam();
  const updateTeam = useUpdateCopilotDirectoryTeam();
  const deleteTeam = useDeleteCopilotDirectoryTeam();

  const createInvite = useCreateCopilotInvite();
  const acceptInvite = useAcceptCopilotInvite();
  const rejectInvite = useRejectCopilotInvite();
  const reconcileIdentityUsers = useReconcileCopilotIdentityUsers();

  const users = usersQuery.data?.data?.users ?? [];
  const groups = groupsQuery.data?.data ?? [];
  const teams = teamsQuery.data?.data ?? [];
  const invites = invitesQuery.data?.data ?? [];

  const stats = useMemo(
    () => ({
      users: users.length,
      organizations: groups.length,
      teams: teams.length,
      pendingInvites: invites.filter((i: any) => i.status === "PENDING").length,
    }),
    [groups.length, invites, teams.length, users.length],
  );

  const ensureWriteScope = () => {
    if (directorySource === "identity") {
      message.warning("Identity source is read-only. Switch source to Copilot to edit local directory.");
      return false;
    }
    if (!isSuperAdmin) return true;
    if (!selectedAccountId) {
      message.warning("Select an account before making changes.");
      return false;
    }
    return true;
  };

  const handleSaveUser = async () => {
    if (!ensureWriteScope()) return;
    const values = await userForm.validateFields();
    try {
      if (editingUser) {
        await updateUser.mutateAsync({
          userId: editingUser.id,
          data: {
            name: values.name,
            profile_image: values.profile_image || null,
            is_active: values.is_active,
          },
          account_id: accountFilter,
        });

        await updateMembership.mutateAsync({
          userId: editingUser.id,
          data: {
            app_role: values.app_role,
            team_id: values.team_id || null,
          },
          account_id: accountFilter,
        });
        message.success("Copilot user updated.");
      } else {
        await createUser.mutateAsync({
          data: {
            email: values.email,
            name: values.name,
            profile_image: values.profile_image || null,
            app_role: values.app_role,
          },
          account_id: accountFilter,
        });
        message.success("Copilot user created.");
      }
      setUserDrawerOpen(false);
      setEditingUser(null);
      userForm.resetFields();
    } catch (e: any) {
      message.error(e?.message || "Failed to save user");
    }
  };

  const handleSaveGroup = async () => {
    if (!ensureWriteScope()) return;
    const values = await groupForm.validateFields();
    try {
      if (editingGroup) {
        await updateGroup.mutateAsync({
          groupId: editingGroup.id,
          data: values,
          account_id: accountFilter,
        });
        message.success("Organization updated.");
      } else {
        await createGroup.mutateAsync({
          data: values,
          account_id: accountFilter,
        });
        message.success("Organization created.");
      }
      setGroupModalOpen(false);
      setEditingGroup(null);
      groupForm.resetFields();
    } catch (e: any) {
      message.error(e?.message || "Failed to save organization");
    }
  };

  const handleSaveTeam = async () => {
    if (!ensureWriteScope()) return;
    const values = await teamForm.validateFields();
    try {
      if (editingTeam) {
        await updateTeam.mutateAsync({
          teamId: editingTeam.id,
          data: values,
          account_id: accountFilter,
        });
        message.success("Team updated.");
      } else {
        await createTeam.mutateAsync({
          data: values,
          account_id: accountFilter,
        });
        message.success("Team created.");
      }
      setTeamModalOpen(false);
      setEditingTeam(null);
      teamForm.resetFields();
    } catch (e: any) {
      message.error(e?.message || "Failed to save team");
    }
  };

  const handleCreateInvite = async () => {
    if (!ensureWriteScope()) return;
    const values = await inviteForm.validateFields();
    try {
      await createInvite.mutateAsync({
        data: values,
        account_id: accountFilter,
      });
      message.success("Invite created.");
      setInviteModalOpen(false);
      inviteForm.resetFields();
    } catch (e: any) {
      message.error(e?.message || "Failed to create invite");
    }
  };

  const accountFilterControl = (
    <Select
      placeholder="Select account"
      style={{ minWidth: 300 }}
      value={selectedAccountId}
      loading={accountLoading}
      onChange={(value) => setSelectedAccountId(value)}
      options={accounts.map((a: any) => ({
        label: `${a.account_name} (${a.status})`,
        value: a.account_id,
      }))}
    />
  );

  const userColumns = [
    {
      title: "User",
      key: "user",
      render: (_: any, record: any) => (
        <Space direction="vertical" size={0}>
          <span>{record.name}</span>
          <span style={{ color: "#6b7280" }}>{record.email}</span>
        </Space>
      ),
    },
    {
      title: "Role",
      key: "role",
      render: (_: any, record: any) => {
        const membership = record.memberships?.[0];
        return <Tag>{membership?.app_role || "-"}</Tag>;
      },
    },
    {
      title: "Team",
      key: "team",
      render: (_: any, record: any) => {
        const membership = record.memberships?.[0];
        return membership?.team?.name || "-";
      },
    },
    {
      title: "Status",
      dataIndex: "is_active",
      key: "is_active",
      render: (value: boolean) => <Tag color={value ? "green" : "default"}>{value ? "ACTIVE" : "INACTIVE"}</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => {
        const membership = record.memberships?.[0];
        return (
          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={directorySource === "identity"}
            onClick={() => {
              setEditingUser(record);
              userForm.setFieldsValue({
                name: record.name,
                email: record.email,
                profile_image: record.profile_image,
                is_active: record.is_active,
                app_role: membership?.app_role || "USER",
                team_id: membership?.team_id || undefined,
              });
              setUserDrawerOpen(true);
            }}
          />
        );
      },
    },
  ];

  const groupColumns = [
    { title: "Name", dataIndex: "name", key: "name" },
    {
      title: "Teams",
      dataIndex: "team_count",
      key: "team_count",
      render: (value: any) => Number(value || 0),
    },
    { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={record.is_default || directorySource === "identity"}
            onClick={() => {
              setEditingGroup(record);
              groupForm.setFieldsValue({
                name: record.name,
                description: record.description,
                owner_id: record.owner_id,
                contact_email: record.contact_email,
              });
              setGroupModalOpen(true);
            }}
          />
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            disabled={record.is_default || directorySource === "identity"}
            onClick={() =>
              Modal.confirm({
                title: "Delete Organization",
                content: `Delete "${record.name}"?`,
                onOk: async () => {
                  await deleteGroup.mutateAsync({ groupId: record.id, account_id: accountFilter });
                  message.success("Organization deleted.");
                },
              })
            }
          />
        </Space>
      ),
    },
  ];

  const teamColumns = [
    { title: "Team", dataIndex: "name", key: "name" },
    {
      title: "Organization",
      key: "group",
      render: (_: any, record: any) => record.group?.name || "-",
    },
    {
      title: "Members",
      dataIndex: "member_count",
      key: "member_count",
      render: (value: any) => Number(value || 0),
    },
    { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={record.is_default || directorySource === "identity"}
            onClick={() => {
              setEditingTeam(record);
              teamForm.setFieldsValue({
                name: record.name,
                description: record.description,
                group_id: record.group_id,
                owner_id: record.owner_id,
                contact_email: record.contact_email,
              });
              setTeamModalOpen(true);
            }}
          />
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            disabled={record.is_default || directorySource === "identity"}
            onClick={() =>
              Modal.confirm({
                title: "Delete Team",
                content: `Delete "${record.name}"? Members will move to default team.`,
                onOk: async () => {
                  await deleteTeam.mutateAsync({ teamId: record.id, account_id: accountFilter });
                  message.success("Team deleted.");
                },
              })
            }
          />
        </Space>
      ),
    },
  ];

  const inviteColumns = [
    { title: "Email", dataIndex: "email", key: "email" },
    { title: "Role", dataIndex: "role", key: "role", render: (value: string) => <Tag>{value}</Tag> },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={inviteStatusColors[value] || "default"}>{value}</Tag>,
    },
    {
      title: "Expires",
      dataIndex: "expires_at",
      key: "expires_at",
      render: (value: string) => (value ? new Date(value).toLocaleString() : "-"),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<CheckOutlined />}
            disabled={record.status !== "PENDING" || directorySource === "identity"}
            onClick={async () => {
              await acceptInvite.mutateAsync({ inviteId: record.id, account_id: accountFilter });
              message.success("Invite accepted.");
            }}
          />
          <Button
            size="small"
            icon={<CloseOutlined />}
            danger
            disabled={record.status !== "PENDING" || directorySource === "identity"}
            onClick={async () => {
              await rejectInvite.mutateAsync({ inviteId: record.id, account_id: accountFilter });
              message.success("Invite rejected.");
            }}
          />
        </Space>
      ),
    },
  ];

  return (
    <div style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Copilot Directory"
        description="Manage Copilot users, organizations, teams, and invites in an account-scoped directory."
      />

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="Users" value={stats.users} loading={usersQuery.isLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="Organizations" value={stats.organizations} loading={groupsQuery.isLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="Teams" value={stats.teams} loading={teamsQuery.isLoading} /></Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card><Statistic title="Pending Invites" value={stats.pendingInvites} loading={invitesQuery.isLoading} /></Card>
        </Col>
      </Row>

      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", gap: 12 }}>
        <Space>
          {isSuperAdmin && accountFilterControl}
          <Select
            style={{ minWidth: 240 }}
            value={directorySource}
            onChange={(value) => setDirectorySource(value)}
            options={[
              { label: "Identity (Zitadel + SCIM)", value: "identity" },
              { label: "Copilot Local Directory", value: "copilot" },
            ]}
          />
        </Space>
        {directorySource === "identity" && (
          <Button
            icon={<SyncOutlined />}
            loading={reconcileIdentityUsers.isPending}
            onClick={async () => {
              try {
                const response = await reconcileIdentityUsers.mutateAsync({ account_id: accountFilter });
                const updatedCount = response?.data?.updated_count ?? 0;
                message.success(`Identity reconciliation complete. Updated ${updatedCount} user(s).`);
                await Promise.all([usersQuery.refetch(), groupsQuery.refetch(), teamsQuery.refetch()]);
              } catch (e: any) {
                message.error(e?.message || "Failed to reconcile identity users");
              }
            }}
          >
            Reconcile Identity Users
          </Button>
        )}
      </div>

      {directorySource === "identity" && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Identity Source Mode"
          description="Users are read from account-scoped SSO identities and teams/groups are read from SCIM-managed teams/organizations. This mode is read-only."
        />
      )}

      {isSuperAdmin && !selectedAccountId && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="Select an account to start managing Copilot directory data."
        />
      )}

      <Tabs
        defaultActiveKey="users"
        items={[
          {
            key: "users",
            label: "Users",
            children: (
              <>
                <div style={{ marginBottom: 12, textAlign: "right" }}>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    disabled={directorySource === "identity"}
                    onClick={() => {
                      setEditingUser(null);
                      userForm.resetFields();
                      userForm.setFieldsValue({ app_role: "USER", is_active: true });
                      setUserDrawerOpen(true);
                    }}
                  >
                    Add User
                  </Button>
                </div>
                <Table
                  rowKey="id"
                  dataSource={users}
                  loading={usersQuery.isLoading}
                  columns={userColumns}
                  pagination={{ pageSize: 20 }}
                />
              </>
            ),
          },
          {
            key: "groups",
            label: "Organizations",
            children: (
              <>
                <div style={{ marginBottom: 12, textAlign: "right" }}>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    disabled={directorySource === "identity"}
                    onClick={() => {
                      setEditingGroup(null);
                      groupForm.resetFields();
                      setGroupModalOpen(true);
                    }}
                  >
                    Add Organization
                  </Button>
                </div>
                <Table
                  rowKey="id"
                  dataSource={groups}
                  loading={groupsQuery.isLoading}
                  columns={groupColumns}
                  pagination={{ pageSize: 20 }}
                />
              </>
            ),
          },
          {
            key: "teams",
            label: "Teams",
            children: (
              <>
                <div style={{ marginBottom: 12, textAlign: "right" }}>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    disabled={directorySource === "identity"}
                    onClick={() => {
                      setEditingTeam(null);
                      teamForm.resetFields();
                      setTeamModalOpen(true);
                    }}
                  >
                    Add Team
                  </Button>
                </div>
                <Table
                  rowKey="id"
                  dataSource={teams}
                  loading={teamsQuery.isLoading}
                  columns={teamColumns}
                  pagination={{ pageSize: 20 }}
                />
              </>
            ),
          },
          {
            key: "invites",
            label: "Invites",
            children: (
              <>
                <div style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <Select
                    placeholder="Filter status"
                    allowClear
                    style={{ minWidth: 200 }}
                    value={inviteStatusFilter}
                    onChange={(value) => setInviteStatusFilter(value)}
                    options={[
                      { label: "Pending", value: "PENDING" },
                      { label: "Accepted", value: "ACCEPTED" },
                      { label: "Declined", value: "DECLINED" },
                      { label: "Expired", value: "EXPIRED" },
                      { label: "Cancelled", value: "CANCELLED" },
                    ]}
                  />
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    disabled={directorySource === "identity"}
                    onClick={() => {
                      inviteForm.resetFields();
                      inviteForm.setFieldsValue({ role: "USER", expires_in_days: 7 });
                      setInviteModalOpen(true);
                    }}
                  >
                    Send Invite
                  </Button>
                </div>
                <Table
                  rowKey="id"
                  dataSource={invites}
                  loading={invitesQuery.isLoading}
                  columns={inviteColumns}
                  pagination={{ pageSize: 20 }}
                />
              </>
            ),
          },
        ]}
      />

      <Drawer
        title={editingUser ? "Edit Copilot User" : "Create Copilot User"}
        open={userDrawerOpen}
        onClose={() => {
          setUserDrawerOpen(false);
          setEditingUser(null);
        }}
        width={560}
        extra={
          <Button
            type="primary"
            onClick={handleSaveUser}
            loading={
              createUser.isPending ||
              updateUser.isPending ||
              updateMembership.isPending
            }
          >
            {editingUser ? "Save" : "Create"}
          </Button>
        }
      >
        <Form form={userForm} layout="vertical">
          <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
            <Input disabled={Boolean(editingUser)} />
          </Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="profile_image" label="Profile Image URL">
            <Input />
          </Form.Item>
          <Form.Item name="app_role" label="Role" rules={[{ required: true }]}>
            <Select options={roleOptions} />
          </Form.Item>
          <Form.Item name="team_id" label="Team">
            <Select
              allowClear
              options={teams.map((t: any) => ({
                label: t.group?.name ? `${t.name} (${t.group.name})` : t.name,
                value: t.id,
              }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="is_active" label="Active">
            <Select options={[{ label: "Active", value: true }, { label: "Inactive", value: false }]} />
          </Form.Item>
        </Form>
      </Drawer>

      <Modal
        title={editingGroup ? "Edit Organization" : "Create Organization"}
        open={groupModalOpen}
        onCancel={() => {
          setGroupModalOpen(false);
          setEditingGroup(null);
        }}
        onOk={handleSaveGroup}
        confirmLoading={createGroup.isPending || updateGroup.isPending}
      >
        <Form form={groupForm} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="owner_id" label="Owner User ID">
            <Input />
          </Form.Item>
          <Form.Item name="contact_email" label="Contact Email">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingTeam ? "Edit Team" : "Create Team"}
        open={teamModalOpen}
        onCancel={() => {
          setTeamModalOpen(false);
          setEditingTeam(null);
        }}
        onOk={handleSaveTeam}
        confirmLoading={createTeam.isPending || updateTeam.isPending}
      >
        <Form form={teamForm} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="group_id" label="Organization" rules={[{ required: true }]}>
            <Select
              options={groups.map((g: any) => ({ label: g.name, value: g.id }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="owner_id" label="Owner User ID">
            <Input />
          </Form.Item>
          <Form.Item name="contact_email" label="Contact Email">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Send Copilot Invite"
        open={inviteModalOpen}
        onCancel={() => setInviteModalOpen(false)}
        onOk={handleCreateInvite}
        confirmLoading={createInvite.isPending}
      >
        <Form form={inviteForm} layout="vertical">
          <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="Role" rules={[{ required: true }]}>
            <Select options={roleOptions} />
          </Form.Item>
          <Form.Item name="expires_in_days" label="Expires In (Days)" rules={[{ required: true }]}>
            <InputNumber min={1} max={90} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotDirectoryPage;
