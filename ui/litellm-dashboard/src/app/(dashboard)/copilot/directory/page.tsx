"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Tabs, Modal, Form, Input, Select, Tag, message } from "antd";
import { UsergroupAddOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import { directoryApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

export default function CopilotDirectoryPage() {
  const { accessToken } = useAuthorized();

  const [users, setUsers] = useState<any[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [userModal, setUserModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [userForm] = Form.useForm();

  const [orgs, setOrgs] = useState<any[]>([]);
  const [orgsLoading, setOrgsLoading] = useState(false);
  const [orgModal, setOrgModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [orgForm] = Form.useForm();

  const [teams, setTeams] = useState<any[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [teamModal, setTeamModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [teamForm] = Form.useForm();

  const [invites, setInvites] = useState<any[]>([]);
  const [invitesLoading, setInvitesLoading] = useState(false);
  const [inviteModal, setInviteModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [inviteForm] = Form.useForm();

  const loadUsers = useCallback(async () => {
    if (!accessToken) return;
    setUsersLoading(true);
    try {
      const resp = await directoryApi.listUsers(accessToken);
      setUsers(Array.isArray(resp) ? resp : (resp as any)?.items ?? []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load users");
    } finally {
      setUsersLoading(false);
    }
  }, [accessToken]);

  const loadOrgs = useCallback(async () => {
    if (!accessToken) return;
    setOrgsLoading(true);
    try {
      const resp = await directoryApi.listOrganizations(accessToken);
      setOrgs(Array.isArray(resp) ? resp : (resp as any)?.items ?? []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load organizations");
    } finally {
      setOrgsLoading(false);
    }
  }, [accessToken]);

  const loadTeams = useCallback(async () => {
    if (!accessToken) return;
    setTeamsLoading(true);
    try {
      const resp = await directoryApi.listTeams(accessToken);
      setTeams(Array.isArray(resp) ? resp : (resp as any)?.items ?? []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load teams");
    } finally {
      setTeamsLoading(false);
    }
  }, [accessToken]);

  const loadInvites = useCallback(async () => {
    if (!accessToken) return;
    setInvitesLoading(true);
    try {
      const resp = await directoryApi.listInvites(accessToken);
      setInvites(Array.isArray(resp) ? resp : (resp as any)?.items ?? []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load invites");
    } finally {
      setInvitesLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadUsers(); loadOrgs(); loadTeams(); loadInvites();
  }, [loadUsers, loadOrgs, loadTeams, loadInvites]);

  const handleRefresh = () => { loadUsers(); loadOrgs(); loadTeams(); loadInvites(); };

  const handleUserSave = async () => {
    if (!accessToken) return;
    try {
      const values = await userForm.validateFields();
      if (userModal.editing) {
        await directoryApi.updateUser(accessToken, userModal.editing.user_id, values);
        message.success("User updated");
      } else {
        await directoryApi.createUser(accessToken, values);
        message.success("User created");
      }
      setUserModal({ open: false, editing: null }); userForm.resetFields(); loadUsers();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleOrgSave = async () => {
    if (!accessToken) return;
    try {
      const values = await orgForm.validateFields();
      if (orgModal.editing) {
        await directoryApi.updateOrganization(accessToken, orgModal.editing.organization_id, values);
        message.success("Organization updated");
      } else {
        await directoryApi.createOrganization(accessToken, values);
        message.success("Organization created");
      }
      setOrgModal({ open: false, editing: null }); orgForm.resetFields(); loadOrgs();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleTeamSave = async () => {
    if (!accessToken) return;
    try {
      const values = await teamForm.validateFields();
      if (teamModal.editing) {
        await directoryApi.updateTeam(accessToken, teamModal.editing.team_id, values);
        message.success("Team updated");
      } else {
        await directoryApi.createTeam(accessToken, values);
        message.success("Team created");
      }
      setTeamModal({ open: false, editing: null }); teamForm.resetFields(); loadTeams();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleInviteSave = async () => {
    if (!accessToken) return;
    try {
      const values = await inviteForm.validateFields();
      await directoryApi.createInvite(accessToken, values);
      message.success("Invite sent");
      setInviteModal({ open: false, editing: null }); inviteForm.resetFields(); loadInvites();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const pendingInvites = invites.filter((i) => (i.status ?? "").toLowerCase() === "pending");

  return (
    <CopilotPageShell title="Directory" subtitle="Manage copilot users, organizations, teams, and invites." icon={<UsergroupAddOutlined />} onRefresh={handleRefresh}>
      <CopilotStatsRow stats={[
        { title: "Total Users", value: users.length, loading: usersLoading },
        { title: "Organizations", value: orgs.length, loading: orgsLoading },
        { title: "Teams", value: teams.length, loading: teamsLoading },
        { title: "Pending Invites", value: pendingInvites.length, loading: invitesLoading },
      ]} />
      <Tabs defaultActiveKey="users" items={[
        { key: "users", label: `Users (${users.length})`, children: (
          <>
            <CopilotCrudTable dataSource={users} rowKey="user_id" loading={usersLoading}
              searchFields={["user_id", "email", "display_name", "role"]}
              addLabel="Add User"
              onAdd={() => { userForm.resetFields(); setUserModal({ open: true, editing: null }); }}
              onEdit={(r) => { userForm.setFieldsValue(r); setUserModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await directoryApi.deleteUser(accessToken, r.user_id); loadUsers(); } }}
              columns={[
                { title: "User ID", dataIndex: "user_id", key: "user_id", ellipsis: true, width: 200 },
                { title: "Email", dataIndex: "email", key: "email", ellipsis: true },
                { title: "Display Name", dataIndex: "display_name", key: "display_name" },
                { title: "Role", dataIndex: "role", key: "role", render: (v: string) => <Tag color="blue">{v ?? "—"}</Tag> },
                { title: "Organization", dataIndex: "organization_id", key: "organization_id", ellipsis: true, render: (v: string) => orgs.find((o) => o.organization_id === v)?.name || v || "—" },
                { title: "Status", dataIndex: "status", key: "status", render: (v: string) => <Tag color={v === "active" ? "green" : "default"}>{v ?? "—"}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
              ]}
            />
            <Modal title={userModal.editing ? "Edit User" : "Add User"} open={userModal.open} onOk={handleUserSave} onCancel={() => setUserModal({ open: false, editing: null })} width={500}>
              <Form form={userForm} layout="vertical">
                <Form.Item name="email" label="Email" rules={[{ required: !userModal.editing, type: "email" }]}><Input /></Form.Item>
                <Form.Item name="display_name" label="Display Name"><Input /></Form.Item>
                <Form.Item name="role" label="Role"><Select options={[{ value: "copilot_admin", label: "Copilot Admin" }, { value: "copilot_user", label: "Copilot User" }, { value: "copilot_viewer", label: "Copilot Viewer" }]} /></Form.Item>
                <Form.Item name="organization_id" label="Organization"><Select allowClear placeholder="Select organization" options={orgs.map((o) => ({ value: o.organization_id, label: o.name || o.organization_id }))} /></Form.Item>
                <Form.Item name="status" label="Status" initialValue="active"><Select options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }]} /></Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "organizations", label: `Organizations (${orgs.length})`, children: (
          <>
            <CopilotCrudTable dataSource={orgs} rowKey="organization_id" loading={orgsLoading}
              searchFields={["organization_id", "name", "description"]}
              addLabel="Add Organization"
              onAdd={() => { orgForm.resetFields(); setOrgModal({ open: true, editing: null }); }}
              onEdit={(r) => { orgForm.setFieldsValue(r); setOrgModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await directoryApi.deleteOrganization(accessToken, r.organization_id); loadOrgs(); } }}
              columns={[
                { title: "Organization ID", dataIndex: "organization_id", key: "organization_id", ellipsis: true, width: 200 },
                { title: "Name", dataIndex: "name", key: "name" },
                { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
                { title: "Status", dataIndex: "status", key: "status", render: (v: string) => <Tag color={v === "active" ? "green" : "default"}>{v ?? "—"}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
              ]}
            />
            <Modal title={orgModal.editing ? "Edit Organization" : "Add Organization"} open={orgModal.open} onOk={handleOrgSave} onCancel={() => setOrgModal({ open: false, editing: null })} width={500}>
              <Form form={orgForm} layout="vertical">
                <Form.Item name="name" label="Organization Name" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
                <Form.Item name="status" label="Status" initialValue="active"><Select options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }]} /></Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "teams", label: `Teams (${teams.length})`, children: (
          <>
            <CopilotCrudTable dataSource={teams} rowKey="team_id" loading={teamsLoading}
              searchFields={["team_id", "name", "organization_id"]}
              addLabel="Add Team"
              onAdd={() => { teamForm.resetFields(); setTeamModal({ open: true, editing: null }); }}
              onEdit={(r) => { teamForm.setFieldsValue(r); setTeamModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await directoryApi.deleteTeam(accessToken, r.team_id); loadTeams(); } }}
              columns={[
                { title: "Team ID", dataIndex: "team_id", key: "team_id", ellipsis: true, width: 200 },
                { title: "Name", dataIndex: "name", key: "name" },
                { title: "Organization", dataIndex: "organization_id", key: "organization_id", ellipsis: true, render: (v: string) => orgs.find((o) => o.organization_id === v)?.name || v || "—" },
                { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
                { title: "Status", dataIndex: "status", key: "status", render: (v: string) => <Tag color={v === "active" ? "green" : "default"}>{v ?? "—"}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
              ]}
            />
            <Modal title={teamModal.editing ? "Edit Team" : "Add Team"} open={teamModal.open} onOk={handleTeamSave} onCancel={() => setTeamModal({ open: false, editing: null })} width={500}>
              <Form form={teamForm} layout="vertical">
                <Form.Item name="name" label="Team Name" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="organization_id" label="Organization"><Select allowClear placeholder="Select organization" options={orgs.map((o) => ({ value: o.organization_id, label: o.name || o.organization_id }))} /></Form.Item>
                <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
                <Form.Item name="status" label="Status" initialValue="active"><Select options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }]} /></Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "invites", label: `Invites (${invites.length})`, children: (
          <>
            <CopilotCrudTable dataSource={invites} rowKey="invite_id" loading={invitesLoading}
              searchFields={["invite_id", "email", "role", "status"]}
              addLabel="Send Invite"
              onAdd={() => { inviteForm.resetFields(); setInviteModal({ open: true, editing: null }); }}
              onDelete={async (r) => { if (accessToken) { await directoryApi.deleteInvite(accessToken, r.invite_id); loadInvites(); } }}
              columns={[
                { title: "Invite ID", dataIndex: "invite_id", key: "invite_id", ellipsis: true, width: 200 },
                { title: "Email", dataIndex: "email", key: "email" },
                { title: "Role", dataIndex: "role", key: "role", render: (v: string) => <Tag color="blue">{v ?? "—"}</Tag> },
                { title: "Status", dataIndex: "status", key: "status", render: (v: string) => {
                  const s = (v ?? "").toLowerCase();
                  const color = s === "accepted" ? "green" : s === "pending" ? "orange" : "red";
                  return <Tag color={color}>{v ?? "—"}</Tag>;
                }},
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
                { title: "Expires", dataIndex: "expires_at", key: "expires_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "—" },
              ]}
            />
            <Modal title="Send Invite" open={inviteModal.open} onOk={handleInviteSave} onCancel={() => setInviteModal({ open: false, editing: null })} width={500}>
              <Form form={inviteForm} layout="vertical">
                <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}><Input /></Form.Item>
                <Form.Item name="role" label="Role"><Select options={[{ value: "copilot_admin", label: "Copilot Admin" }, { value: "copilot_user", label: "Copilot User" }, { value: "copilot_viewer", label: "Copilot Viewer" }]} /></Form.Item>
                <Form.Item name="organization_id" label="Organization"><Select allowClear placeholder="Select organization" options={orgs.map((o) => ({ value: o.organization_id, label: o.name || o.organization_id }))} /></Form.Item>
                <Form.Item name="team_id" label="Team"><Select allowClear placeholder="Select team" options={teams.map((t) => ({ value: t.team_id, label: t.name || t.team_id }))} /></Form.Item>
              </Form>
            </Modal>
          </>
        )},
      ]} />
    </CopilotPageShell>
  );
}
