"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Table, Button, Modal, Form, Input, Select, Card, Tabs, message, Space, Drawer, Tag, Row, Col, Badge } from "antd";
import { PlusOutlined, DeleteOutlined, EditOutlined, AppstoreOutlined, ShopOutlined } from "@ant-design/icons";
import {
  useCopilotAgents,
  useCreateCopilotAgent,
  useUpdateCopilotAgent,
  useDeleteCopilotAgent,
  useCopilotAgentGroups,
  useCreateCopilotAgentGroup,
  useUpdateCopilotAgentGroup,
  useDeleteCopilotAgentGroup,
  useCopilotMarketplace,
  useCreateCopilotMarketplaceItem,
  useUpdateCopilotMarketplaceItem,
  useDeleteCopilotMarketplaceItem,
  useInstallCopilotMarketplaceItem,
} from "@/app/(dashboard)/hooks/copilot/useCopilotAgents";
import { useCopilotUsers } from "@/app/(dashboard)/hooks/copilot/useCopilotDirectory";
import { useCopilotGroups, useCopilotMemberships, useCopilotTeams } from "@/app/(dashboard)/hooks/copilot/useCopilotOverview";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";

const { TabPane } = Tabs;
const { TextArea } = Input;

const CopilotAgentsPage: React.FC = () => {
  const { isSuperAdmin, accountId } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>(accountId || undefined);
  const [agentDrawerOpen, setAgentDrawerOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<any>(null);
  const [groupModalOpen, setGroupModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<any>(null);
  const [marketplaceFilter, setMarketplaceFilter] = useState<string | undefined>();
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [installingItem, setInstallingItem] = useState<any>(null);
  const [form] = Form.useForm();
  const [groupForm] = Form.useForm();
  const [installForm] = Form.useForm();

  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();
  const { data: agentsData, isLoading: agentsLoading } = useCopilotAgents({ account_id: accountFilter });
  const { data: groupsData, isLoading: groupsLoading } = useCopilotAgentGroups({ account_id: accountFilter });
  const { data: marketplaceData, isLoading: marketplaceLoading } = useCopilotMarketplace({ account_id: accountFilter, entity_type: marketplaceFilter });
  const { data: directoryUsersData } = useCopilotUsers({
    account_id: accountFilter,
    source: "identity",
    include_memberships: true,
    limit: 500,
    offset: 0,
  });
  const { data: directoryGroupsData } = useCopilotGroups({ account_id: accountFilter, source: "identity", include_teams: false, limit: 500 });
  const { data: directoryTeamsData } = useCopilotTeams({ account_id: accountFilter, source: "identity", include_group: true, limit: 500 });
  const { data: directoryMembershipsData } = useCopilotMemberships({ account_id: accountFilter, source: "identity", limit: 500 });

  const createAgent = useCreateCopilotAgent();
  const updateAgent = useUpdateCopilotAgent();
  const deleteAgent = useDeleteCopilotAgent();
  const createGroup = useCreateCopilotAgentGroup();
  const updateGroup = useUpdateCopilotAgentGroup();
  const deleteGroup = useDeleteCopilotAgentGroup();
  const installItem = useInstallCopilotMarketplaceItem();

  const agents = agentsData?.data ?? [];
  const groups = groupsData?.data ?? [];
  const marketplaceItems = marketplaceData?.data ?? [];
  const accounts = accountData?.accounts ?? [];
  const directoryUsersFromUsersApi = directoryUsersData?.data?.users ?? [];
  const directoryGroups = directoryGroupsData?.data ?? [];
  const directoryTeams = directoryTeamsData?.data ?? [];
  const directoryMemberships = directoryMembershipsData?.data ?? [];
  const directoryUsers = useMemo(() => {
    const byId: Record<string, any> = {};
    directoryUsersFromUsersApi.forEach((u: any) => {
      if (u?.id) byId[u.id] = u;
    });
    directoryMemberships.forEach((membership: any) => {
      const user = membership?.user;
      if (user?.id && !byId[user.id]) {
        byId[user.id] = user;
      }
    });
    return Object.values(byId);
  }, [directoryMemberships, directoryUsersFromUsersApi]);

  useEffect(() => {
    if (isSuperAdmin && !selectedAccountId && accounts.length > 0) {
      setSelectedAccountId(accounts[0].account_id);
    }
  }, [accounts, isSuperAdmin, selectedAccountId]);

  const ensureAccountForSuperAdminWrite = () => {
    if (isSuperAdmin && !accountFilter) {
      message.warning("Select an account before creating Copilot agents or groups.");
      return false;
    }
    return true;
  };

  const encodeAssignmentValue = (scopeType: string, scopeId: string) => JSON.stringify({ scope_type: scopeType, scope_id: scopeId });
  const decodeAssignmentValue = (value: string): { scope_type: string; scope_id: string } | null => {
    try {
      const parsed = JSON.parse(value);
      if (!parsed || typeof parsed !== "object") return null;
      const scopeType = String((parsed as any).scope_type || "").trim();
      const scopeId = String((parsed as any).scope_id || "").trim();
      if (!scopeType || !scopeId) return null;
      return { scope_type: scopeType, scope_id: scopeId };
    } catch {
      return null;
    }
  };

  const installAssignmentOptions = useMemo(() => {
    const options: Array<{ label: string; value: string }> = [];
    if (isSuperAdmin) {
      options.push({
        label: "All Accounts",
        value: encodeAssignmentValue("account", "*"),
      });
      accounts.forEach((a: any) => {
        options.push({
          label: `Account: ${a.account_name} (${a.status})`,
          value: encodeAssignmentValue("account", a.account_id),
        });
      });
    } else {
      const current = accountFilter || accountId;
      if (current) {
        options.push({
          label: "Account: Current Account",
          value: encodeAssignmentValue("account", current),
        });
      }
    }
    directoryGroups.forEach((g: any) => {
      options.push({
        label: `Organization: ${g.name}`,
        value: encodeAssignmentValue("group", g.id),
      });
    });
    directoryTeams.forEach((t: any) => {
      options.push({
        label: `Team: ${t.group?.name ? `${t.name} (${t.group.name})` : t.name}`,
        value: encodeAssignmentValue("team", t.id),
      });
    });
    directoryUsers.forEach((u: any) => {
      options.push({
        label: `User: ${u.email ? `${u.name || "User"} (${u.email})` : (u.name || u.id)}`,
        value: encodeAssignmentValue("user", u.id),
      });
    });
    return options;
  }, [accountFilter, accountId, accounts, directoryGroups, directoryTeams, directoryUsers, isSuperAdmin]);

  const openInstallModal = (item: any) => {
    if (isSuperAdmin && !accountFilter) {
      message.warning("Select an account before installing and assigning marketplace items.");
      return;
    }
    setInstallingItem(item);
    const current = accountFilter || accountId;
    installForm.setFieldsValue({
      assignment_targets: current ? [encodeAssignmentValue("account", current)] : [],
    });
    setInstallModalOpen(true);
  };

  const handleInstall = async () => {
    if (!installingItem) return;
    try {
      const values = await installForm.validateFields();
      const rawTargets: string[] = Array.isArray(values.assignment_targets) ? values.assignment_targets : [];
      const dedupe = new Set<string>();
      const assignments: Array<{ scope_type: string; scope_id: string }> = [];
      rawTargets.forEach((target) => {
        const parsed = decodeAssignmentValue(target);
        if (!parsed) return;
        const key = `${parsed.scope_type}:${parsed.scope_id}`;
        if (dedupe.has(key)) return;
        dedupe.add(key);
        assignments.push(parsed);
      });
      const installId = installingItem.marketplace_id || installingItem.id;
      if (!installId) {
        message.error("Marketplace item id is missing.");
        return;
      }
      await installItem.mutateAsync({
        id: installId,
        data: { assignments },
        account_id: accountFilter,
      });
      message.success("Installed and assignments updated");
      setInstallModalOpen(false);
      setInstallingItem(null);
      installForm.resetFields();
    } catch (err) {
      // validation / request errors handled by query layer
    }
  };

  const handleAgentSave = async () => {
    try {
      const values = await form.validateFields();
      if (editingAgent) {
        await updateAgent.mutateAsync({ agentId: editingAgent.agent_id, data: values });
        message.success("Agent updated");
      } else {
        if (!ensureAccountForSuperAdminWrite()) return;
        await createAgent.mutateAsync({ data: values, account_id: accountFilter });
        message.success("Agent created");
      }
      setAgentDrawerOpen(false);
      setEditingAgent(null);
      form.resetFields();
    } catch (err) { /* validation */ }
  };

  const handleGroupSave = async () => {
    try {
      const values = await groupForm.validateFields();
      if (editingGroup) {
        await updateGroup.mutateAsync({ id: editingGroup.id, data: values });
        message.success("Group updated");
      } else {
        if (!ensureAccountForSuperAdminWrite()) return;
        await createGroup.mutateAsync({ data: values, account_id: accountFilter });
        message.success("Group created");
      }
      setGroupModalOpen(false);
      setEditingGroup(null);
      groupForm.resetFields();
    } catch (err) { /* validation */ }
  };

  const agentColumns = [
    { title: "Name", dataIndex: "name", key: "name", sorter: (a: any, b: any) => a.name?.localeCompare(b.name) },
    { title: "Description", dataIndex: "description", key: "description", ellipsis: true },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (v: string) => <Tag color={v === "active" ? "green" : "default"}>{v}</Tag>,
    },
    { title: "Provider", dataIndex: "provider", key: "provider" },
    {
      title: "Tags",
      dataIndex: "tags",
      key: "tags",
      render: (tags: string[]) => tags?.map((t: string) => <Tag key={t}>{t}</Tag>) ?? null,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingAgent(record);
              form.setFieldsValue(record);
              setAgentDrawerOpen(true);
            }}
          />
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            onClick={() => {
              Modal.confirm({
                title: "Delete Agent",
                content: `Delete agent "${record.name}"?`,
                onOk: async () => {
                  await deleteAgent.mutateAsync(record.agent_id);
                  message.success("Agent deleted");
                },
              });
            }}
          />
        </Space>
      ),
    },
  ];

  const groupColumns = [
    { title: "Code", dataIndex: "group_code", key: "group_code" },
    { title: "Name", dataIndex: "name", key: "name" },
    { title: "Type", dataIndex: "group_type", key: "group_type" },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (v: string) => <Tag color={v === "active" ? "green" : "default"}>{v}</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingGroup(record);
              groupForm.setFieldsValue(record);
              setGroupModalOpen(true);
            }}
          />
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            onClick={() => {
              Modal.confirm({
                title: "Delete Group",
                content: `Delete group "${record.name}"?`,
                onOk: async () => {
                  await deleteGroup.mutateAsync(record.id);
                  message.success("Group deleted");
                },
              });
            }}
          />
        </Space>
      ),
    },
  ];

  return (
    <div style={{ width: "100%" }}>
      {isSuperAdmin && (
        <div style={{ marginBottom: 16 }}>
          <Select
            placeholder="Filter by account"
            allowClear
            style={{ width: 320 }}
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
      <Tabs defaultActiveKey="agents">
        <TabPane tab={<span><AppstoreOutlined /> Agents</span>} key="agents">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "flex-end" }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingAgent(null);
                form.resetFields();
                setAgentDrawerOpen(true);
              }}
            >
              Create Agent
            </Button>
          </div>
          <Table dataSource={agents} columns={agentColumns} rowKey="agent_id" loading={agentsLoading} />
        </TabPane>
        <TabPane tab={<span><AppstoreOutlined /> Groups</span>} key="groups">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "flex-end" }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingGroup(null);
                groupForm.resetFields();
                setGroupModalOpen(true);
              }}
            >
              Create Group
            </Button>
          </div>
          <Table dataSource={groups} columns={groupColumns} rowKey="id" loading={groupsLoading} />
        </TabPane>
        <TabPane tab={<span><ShopOutlined /> Marketplace</span>} key="marketplace">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
            <Select
              placeholder="Filter by type"
              allowClear
              style={{ width: 200 }}
              options={[
                { label: "Agent", value: "agent" },
                { label: "MCP Server", value: "mcp_server" },
                { label: "OpenAPI Spec", value: "openapi_spec" },
                { label: "Integration", value: "integration" },
                { label: "Workflow", value: "workflow" },
                { label: "Prompt Template", value: "prompt_template" },
              ]}
              onChange={(v) => setMarketplaceFilter(v)}
            />
          </div>
          <Row gutter={[16, 16]}>
            {marketplaceItems.map((item: any) => (
              <Col key={item.marketplace_id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  cover={item.icon_url ? <img alt={item.title} src={item.icon_url} style={{ height: 120, objectFit: "cover" }} /> : null}
                  actions={[
                    <Button
                      key="install"
                      size="small"
                      type="link"
                      onClick={() => {
                        openInstallModal(item);
                      }}
                    >
                      Install / Assign ({item.installation_count ?? 0})
                    </Button>,
                  ]}
                >
                  <Card.Meta
                    title={
                      <Space>
                        {item.title}
                        {item.is_featured && <Badge count="Featured" style={{ backgroundColor: "#faad14" }} />}
                      </Space>
                    }
                    description={item.short_description}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Tag>{item.entity_type}</Tag>
                    <Tag color={item.pricing_model === "free" ? "green" : "gold"}>{item.pricing_model}</Tag>
                    {item.is_verified && <Tag color="blue">Verified</Tag>}
                    {(item?.metadata?.assignments || []).slice(0, 2).map((a: any) => (
                      <Tag key={`${a.scope_type}:${a.scope_id}`} color="geekblue">
                        {a.scope_type}:{a.scope_id === "*" ? "all" : a.scope_id}
                      </Tag>
                    ))}
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
        </TabPane>
      </Tabs>

      <Drawer
        title={editingAgent ? "Edit Agent" : "Create Agent"}
        open={agentDrawerOpen}
        onClose={() => { setAgentDrawerOpen(false); setEditingAgent(null); }}
        width={520}
        extra={
          <Button type="primary" onClick={handleAgentSave} loading={createAgent.isPending || updateAgent.isPending}>
            {editingAgent ? "Update" : "Create"}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="prompt" label="System Prompt">
            <TextArea rows={4} />
          </Form.Item>
          <Form.Item name="status" label="Status" initialValue="active">
            <Select options={[{ label: "Active", value: "active" }, { label: "Inactive", value: "inactive" }, { label: "Draft", value: "draft" }]} />
          </Form.Item>
          <Form.Item name="provider" label="Provider" initialValue="PLATFORM">
            <Input />
          </Form.Item>
          <Form.Item name="tags" label="Tags">
            <Select mode="tags" placeholder="Add tags" />
          </Form.Item>
        </Form>
      </Drawer>

      <Modal
        title={`Install ${installingItem?.title || "Item"} and Assign Access`}
        open={installModalOpen}
        onOk={handleInstall}
        onCancel={() => { setInstallModalOpen(false); setInstallingItem(null); }}
        confirmLoading={installItem.isPending}
      >
        <Form form={installForm} layout="vertical">
          <Form.Item
            name="assignment_targets"
            label="Assign To"
            rules={[{ required: true, message: "Select at least one assignment target." }]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              options={installAssignmentOptions}
              placeholder="Select accounts, organizations, teams, or users"
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingGroup ? "Edit Group" : "Create Group"}
        open={groupModalOpen}
        onOk={handleGroupSave}
        onCancel={() => { setGroupModalOpen(false); setEditingGroup(null); }}
        confirmLoading={createGroup.isPending || updateGroup.isPending}
      >
        <Form form={groupForm} layout="vertical">
          <Form.Item name="group_code" label="Group Code" rules={[{ required: !editingGroup }]}>
            <Input disabled={!!editingGroup} />
          </Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="group_type" label="Group Type" initialValue="custom">
            <Select options={[{ label: "Custom", value: "custom" }, { label: "System", value: "system" }, { label: "Category", value: "category" }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotAgentsPage;
