"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  EditOutlined,
  LockOutlined,
  ReloadOutlined,
  TeamOutlined,
} from "@ant-design/icons";

const { Paragraph, Text, Title } = Typography;

type IdentityBinding = {
  identity_binding_id?: string;
  provider?: string;
  zitadel_org_id?: string;
  issuer_url?: string;
  client_id?: string;
  default_redirect_url?: string;
  sso_enabled?: boolean;
  config?: Record<string, any>;
  metadata?: Record<string, any>;
};

type AccountAdmin = {
  user_id: string;
  user_email: string;
  display_name?: string;
  membership_role?: string;
  role_code?: string;
};

type Account = {
  account_id: string;
  account_name: string;
  account_alias?: string;
  domain?: string;
  status: string;
  metadata: Record<string, any>;
  max_budget?: number | null;
  created_at: string;
  admins: AccountAdmin[];
  identity_binding?: IdentityBinding | null;
};

type Member = {
  user_id: string;
  user_email: string;
  display_name?: string;
  membership_role: string;
  membership_status: string;
  zitadel_sub?: string;
};

type DirectorySummary = {
  account: {
    account_id: string;
    account_name: string;
    account_alias?: string | null;
    domain?: string | null;
    status: string;
  };
  identity_binding: IdentityBinding | null;
  management: {
    configured: boolean;
    issuer?: string | null;
    mode?: string | null;
    error?: string | null;
    console_url?: string | null;
  };
  directory: {
    org_id?: string | null;
    bootstrap_status?: string | null;
    provider_status?: string | null;
    managed_via_console: boolean;
    bootstrap_login?: string | null;
    sso_enabled: boolean;
    provider?: Record<string, any> | null;
    providers?: Record<string, any>[] | null;
    scim?: Record<string, any> | null;
    supports_group_scim: boolean;
    group_sync_strategy: string;
    management_url?: string | null;
    primary_domain?: string | null;
    additional_domains?: string[];
    domains?: Array<Record<string, any>>;
    login_policy?: Record<string, any> | null;
  };
  capabilities: {
    can_bootstrap: boolean;
    can_manage_users: boolean;
    scim_support: string;
  };
};

type ModalPayload = {
  title: string;
  body: React.ReactNode;
};

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getCookie("token") || "";
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const data = await response.json();
      detail = data?.detail || data?.error || detail;
    } catch {
      // Keep fallback detail.
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json();
}

export default function TenantAdminPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [membersLoading, setMembersLoading] = useState(false);
  const [directoryLoading, setDirectoryLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [selectedDirectory, setSelectedDirectory] = useState<DirectorySummary | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [directoryOpen, setDirectoryOpen] = useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [modalPayload, setModalPayload] = useState<ModalPayload | null>(null);
  const [editForm] = Form.useForm();
  const [directoryLinkForm] = Form.useForm();
  const [memberForm] = Form.useForm();

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await requestJson<{ accounts: Account[] }>("/control-plane/accounts");
      setAccounts(data.accounts || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load accounts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAccounts();
  }, [fetchAccounts]);

  const showModal = (title: string, body: React.ReactNode) => {
    setModalPayload({ title, body });
  };

  const fetchDirectorySummary = useCallback(
    async (account: Account) => {
      setDirectoryLoading(true);
      try {
        const summary = await requestJson<DirectorySummary>(
          `/control-plane/accounts/${account.account_id}/directory`,
        );
        const resolvedOrgId =
          summary.directory.org_id || account.metadata?.zitadel_org_id || undefined;
        setSelectedDirectory(summary);
        directoryLinkForm.setFieldsValue({
          zitadel_org_id: resolvedOrgId,
          admin_user_email:
            summary.identity_binding?.metadata?.directory?.tenant_admin_email ||
            account.admins?.[0]?.user_email ||
            "",
          admin_user_id:
            summary.identity_binding?.metadata?.directory?.tenant_admin_user_id || "",
          admin_display_name:
            account.admins?.find(
              (admin) =>
                admin.user_email ===
                summary.identity_binding?.metadata?.directory?.tenant_admin_email,
            )?.display_name ||
            account.admins?.[0]?.display_name ||
            "",
          membership_role: "owner",
          product_grants: ["console", "copilot"],
        });
      } catch (error) {
        message.error(error instanceof Error ? error.message : "Failed to load directory");
      } finally {
        setDirectoryLoading(false);
      }
    },
    [directoryLinkForm],
  );

  const openMembers = async (account: Account) => {
    setSelectedAccount(account);
    setMembersOpen(true);
    setMembersLoading(true);
    try {
      const data = await requestJson<{ members: Member[] }>(
        `/control-plane/accounts/${account.account_id}/members`,
      );
      setMembers(data.members || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load members");
    } finally {
      setMembersLoading(false);
    }
  };

  const openDirectory = async (account: Account) => {
    setSelectedAccount(account);
    setDirectoryOpen(true);
    await fetchDirectorySummary(account);
  };

  const handleEditAccount = async (values: any) => {
    if (!selectedAccount) return;
    setSaving(true);
    try {
      await requestJson(`/control-plane/accounts/${selectedAccount.account_id}`, {
        method: "PUT",
        body: JSON.stringify(values),
      });
      message.success("Account updated");
      setEditOpen(false);
      editForm.resetFields();
      await fetchAccounts();
      if (directoryOpen) {
        await fetchDirectorySummary(selectedAccount);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to update account");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = async (account: Account) => {
    try {
      await requestJson(`/control-plane/accounts/${account.account_id}`, {
        method: "DELETE",
      });
      message.success(account.status === "active" ? "Account suspended" : "Account activated");
      await fetchAccounts();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to update account");
    }
  };

  const handleLinkDirectory = async (values: any) => {
    if (!selectedAccount) return;
    setSaving(true);
    try {
      const response = await requestJson<any>(
        `/control-plane/accounts/${selectedAccount.account_id}/directory/link-existing`,
        {
          method: "POST",
          body: JSON.stringify(values),
        },
      );
      message.success("Zitadel organization linked");
      await fetchAccounts();
      await fetchDirectorySummary(selectedAccount);
      showModal(
        "Zitadel Link Complete",
        <Space direction="vertical" style={{ width: "100%" }}>
          <Text>
            Organization ID:{" "}
            {response.result?.organization?.organization_id || values.zitadel_org_id}
          </Text>
          <Text>
            Tenant Admin:{" "}
            {response.result?.tenant_admin?.user_email ||
              values.admin_user_email ||
              values.admin_user_id}
          </Text>
          {(response.result?.warnings || []).length ? (
            <Alert
              type="warning"
              showIcon
              message="Link warnings"
              description={(response.result.warnings || []).join("\n")}
            />
          ) : null}
        </Space>,
      );
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to link Zitadel organization");
    } finally {
      setSaving(false);
    }
  };

  const handleInviteMember = async (values: any) => {
    if (!selectedAccount) return;
    try {
      const response = await requestJson<any>(
        `/control-plane/accounts/${selectedAccount.account_id}/members/invite`,
        {
          method: "POST",
          body: JSON.stringify({
            user_email: values.user_email,
            display_name: values.display_name || values.user_email,
            membership_role: values.membership_role,
            product_grants: values.product_grants,
            platform_roles:
              values.membership_role === "admin" || values.membership_role === "owner"
                ? ["account_admin"]
                : [],
          }),
        },
      );
      if (response.directory?.managed) {
        message.success(
          response.directory.reused_existing_user
            ? "Existing Zitadel user granted account access"
            : "User created in Zitadel and granted account access",
        );
        if (
          response.directory.temporary_password ||
          response.directory.invite_code ||
          (response.directory.warnings || []).length
        ) {
          showModal(
            "Member Provisioned",
            <Space direction="vertical" style={{ width: "100%" }}>
              <Paragraph style={{ marginBottom: 0 }}>
                The tenant member now exists in Zitadel and has been granted account access in
                Console.
              </Paragraph>
              {response.directory.temporary_password ? (
                <Card size="small">
                  <Text strong>Temporary Password</Text>
                  <Paragraph copyable style={{ marginBottom: 0 }}>
                    {response.directory.temporary_password}
                  </Paragraph>
                </Card>
              ) : null}
              {response.directory.invite_code ? (
                <Card size="small">
                  <Text strong>Invite Code</Text>
                  <Paragraph copyable style={{ marginBottom: 0 }}>
                    {response.directory.invite_code}
                  </Paragraph>
                </Card>
              ) : null}
              {(response.directory.warnings || []).length ? (
                <Alert
                  type="warning"
                  showIcon
                  message="Provisioning warnings"
                  description={(response.directory.warnings || []).join("\n")}
                />
              ) : null}
            </Space>,
          );
        }
      } else {
        message.success("Member synced");
      }
      memberForm.resetFields();
      await openMembers(selectedAccount);
      await fetchAccounts();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to sync member");
    }
  };

  const handleRemoveMember = async (member: Member) => {
    if (!selectedAccount) return;
    try {
      await requestJson(
        `/control-plane/accounts/${selectedAccount.account_id}/members/${encodeURIComponent(member.user_email)}`,
        {
          method: "DELETE",
        },
      );
      message.success("Member removed");
      await openMembers(selectedAccount);
      await fetchAccounts();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to remove member");
    }
  };

  const summary = useMemo(() => {
    const activeAccounts = accounts.filter((account) => account.status === "active").length;
    const linkedDirectories = accounts.filter(
      (account) =>
        Boolean(
          account.identity_binding?.metadata?.directory?.tenant_admin_user_id ||
            account.identity_binding?.metadata?.directory?.tenant_admin_email,
        ),
    ).length;
    const adminCount = accounts.reduce(
      (total, account) => total + (account.admins?.length || 0),
      0,
    );
    return { activeAccounts, linkedDirectories, adminCount };
  }, [accounts]);

  const accountColumns = [
    {
      title: "Account",
      key: "account",
      render: (_: any, account: Account) => (
        <Space direction="vertical" size={0}>
          <Text strong>{account.account_name}</Text>
          <Text type="secondary">{account.account_alias || account.domain || "No alias"}</Text>
        </Space>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (value: string) => (
        <Tag color={value === "active" ? "green" : "orange"}>{value.toUpperCase()}</Tag>
      ),
    },
    {
      title: "Directory",
      key: "identity",
      render: (_: any, account: Account) => {
        const orgId =
          account.identity_binding?.zitadel_org_id || account.metadata?.zitadel_org_id;
        const tenantAdmin =
          account.identity_binding?.metadata?.directory?.tenant_admin_email ||
          account.identity_binding?.metadata?.directory?.tenant_admin_user_id;
        return orgId ? (
          <Space direction="vertical" size={0}>
            <Tag color={tenantAdmin ? "blue" : "gold"}>
              {tenantAdmin ? "LINKED" : "DISCOVERED"}
            </Tag>
            <Text type="secondary">
              {orgId}
              {account.domain ? ` · ${account.domain}` : ""}
            </Text>
          </Space>
        ) : (
          <Tag>Not linked</Tag>
        );
      },
    },
    {
      title: "Admins",
      key: "admins",
      render: (_: any, account: Account) => account.admins?.length || 0,
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (value: string) => new Date(value).toLocaleDateString(),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, account: Account) => (
        <Space wrap>
          <Button
            icon={<EditOutlined />}
            onClick={() => {
              setSelectedAccount(account);
              editForm.setFieldsValue({
                account_name: account.account_name,
                account_alias: account.account_alias,
                domain: account.domain,
                max_budget: account.max_budget,
                status: account.status,
              });
              setEditOpen(true);
            }}
          >
            Edit
          </Button>
          <Button icon={<LockOutlined />} onClick={() => void openDirectory(account)}>
            Directory &amp; SSO
          </Button>
          <Button icon={<TeamOutlined />} onClick={() => void openMembers(account)}>
            Members
          </Button>
          <Popconfirm
            title={account.status === "active" ? "Suspend this account?" : "Reactivate this account?"}
            onConfirm={() => handleToggleStatus(account)}
          >
            <Button danger={account.status === "active"}>
              {account.status === "active" ? "Suspend" : "Activate"}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const memberColumns = [
    {
      title: "User",
      key: "user",
      render: (_: any, member: Member) => (
        <Space direction="vertical" size={0}>
          <Text strong>{member.display_name || member.user_email}</Text>
          <Text type="secondary">{member.user_email}</Text>
        </Space>
      ),
    },
    {
      title: "Role",
      dataIndex: "membership_role",
      key: "membership_role",
      render: (value: string) => (
        <Tag color={value === "admin" || value === "owner" ? "blue" : "default"}>{value}</Tag>
      ),
    },
    {
      title: "Status",
      dataIndex: "membership_status",
      key: "membership_status",
      render: (value: string) => (
        <Tag color={value === "active" ? "green" : "orange"}>{value}</Tag>
      ),
    },
    {
      title: "Identity",
      key: "identity",
      render: (_: any, member: Member) =>
        member.zitadel_sub ? (
          <Text type="secondary">{member.zitadel_sub}</Text>
        ) : (
          <Text type="secondary">Local account access only</Text>
        ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, member: Member) => (
        <Popconfirm title="Remove this member?" onConfirm={() => handleRemoveMember(member)}>
          <Button danger size="small">
            Remove
          </Button>
        </Popconfirm>
      ),
    },
  ];

  const tenantAdminAssigned = Boolean(
    selectedDirectory?.identity_binding?.metadata?.directory?.tenant_admin_user_id ||
      selectedDirectory?.identity_binding?.metadata?.directory?.tenant_admin_email,
  );
  return (
    <div className="p-6">
      <Space direction="vertical" size="large" className="w-full">
        <div className="flex items-center justify-between">
          <div>
            <Title level={2} style={{ marginBottom: 0 }}>
              Platform Control Plane
            </Title>
            <Text type="secondary">
              Console reflects shared accounts and links them to tenant organizations that already
              exist in Zitadel.
            </Text>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void fetchAccounts()}>
              Refresh
            </Button>
          </Space>
        </div>

        <Alert
          type="info"
          showIcon
          message="Zitadel-managed tenant identity"
          description="Create the organization, domains, IdPs, SCIM setup, and tenant users in Zitadel. Console mirrors those tenant organizations automatically and is used only to assign the tenant admin and manage shared product grants."
        />

        <Row gutter={16}>
          <Col span={8}>
            <Card>
              <Statistic title="Accounts" value={accounts.length} />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic title="Active Accounts" value={summary.activeAccounts} />
            </Card>
          </Col>
          <Col span={8}>
            <Card>
              <Statistic
                title="Linked Directories"
                value={summary.linkedDirectories}
                suffix={`/ ${accounts.length || 1}`}
              />
            </Card>
          </Col>
        </Row>

        <Card>
          <Table
            rowKey="account_id"
            dataSource={accounts}
            columns={accountColumns}
            loading={loading}
            pagination={{ pageSize: 10 }}
          />
        </Card>
      </Space>

      <Modal
        title={`Edit ${selectedAccount?.account_name || "Account"}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form layout="vertical" form={editForm} onFinish={handleEditAccount}>
          <Form.Item name="account_name" label="Account Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="account_alias" label="Alias">
            <Input />
          </Form.Item>
          <Form.Item name="domain" label="Primary Domain">
            <Input />
          </Form.Item>
          <Form.Item name="max_budget" label="Max Budget">
            <InputNumber className="w-full" min={0} />
          </Form.Item>
          <Form.Item name="status" label="Status">
            <Select
              options={[
                { label: "Active", value: "active" },
                { label: "Suspended", value: "suspended" },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block loading={saving}>
              Save
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={`Directory & SSO: ${selectedAccount?.account_name || ""}`}
        open={directoryOpen}
        width={720}
        onClose={() => setDirectoryOpen(false)}
        destroyOnClose
      >
        <Space direction="vertical" size="large" className="w-full">
          {selectedDirectory && !selectedDirectory.management.configured ? (
            <Alert
              type="warning"
              showIcon
              message="Zitadel management credentials are not configured for Console"
              description={
                selectedDirectory.management.error ||
                "Set ALCHEMI_ZITADEL_PAT or service-account credentials on the backend before linking tenant directories."
              }
            />
          ) : null}

          <Card loading={directoryLoading} title="Current Status">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Organization ID">
                {selectedDirectory?.directory.org_id || "Not linked"}
              </Descriptions.Item>
              <Descriptions.Item label="Primary Domain">
                {selectedDirectory?.directory.primary_domain ||
                  selectedDirectory?.account.domain ||
                  "Not configured"}
              </Descriptions.Item>
              <Descriptions.Item label="Tenant Admin">
                {selectedDirectory?.identity_binding?.metadata?.directory?.tenant_admin_email ||
                  selectedAccount?.admins?.[0]?.user_email ||
                  "Not set"}
              </Descriptions.Item>
              <Descriptions.Item label="Directory Owner">
                {selectedDirectory?.directory.managed_via_console
                  ? "Console"
                  : "Zitadel"}
              </Descriptions.Item>
              <Descriptions.Item label="Management URL">
                {selectedDirectory?.directory.management_url ||
                  selectedDirectory?.management.console_url ||
                  "Not available"}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {!tenantAdminAssigned ? (
            <Card title="Assign Tenant Admin" loading={directoryLoading}>
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <Paragraph>
                  This account was discovered from Zitadel. Assign which existing Zitadel user
                  should be treated as the tenant admin in Console and receive shared product
                  grants here.
                </Paragraph>
                <Alert
                  type="info"
                  showIcon
                  message="Zitadel remains the source of truth"
                  description="Domains, login policy, IdP setup, SCIM, and user lifecycle are managed in Zitadel. Console only stores the account-to-organization link and shared account access."
                />
                {selectedDirectory?.management.console_url ? (
                  <Button href={selectedDirectory.management.console_url} target="_blank">
                    Open Zitadel Console
                  </Button>
                ) : null}
                <Form layout="vertical" form={directoryLinkForm} onFinish={handleLinkDirectory}>
                  <Form.Item
                    name="zitadel_org_id"
                    label="Zitadel Organization"
                    rules={[{ required: true, message: "Organization is required" }]}
                  >
                    <Input disabled />
                  </Form.Item>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="admin_user_email" label="Tenant Admin Email">
                        <Input placeholder="admin@customer.com" />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="admin_user_id" label="Tenant Admin User ID">
                        <Input placeholder="Optional Zitadel user id" />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="admin_display_name" label="Tenant Admin Name">
                        <Input />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="membership_role" label="Account Role" initialValue="owner">
                        <Select
                          options={[
                            { label: "Owner", value: "owner" },
                            { label: "Admin", value: "admin" },
                          ]}
                        />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item
                    name="product_grants"
                    label="Product Access"
                    initialValue={["console", "copilot"]}
                  >
                    <Select
                      mode="multiple"
                      options={[
                        { label: "Console", value: "console" },
                        { label: "Copilot", value: "copilot" },
                      ]}
                    />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={saving}>
                    Save Tenant Admin
                  </Button>
                </Form>
              </Space>
            </Card>
          ) : (
            <Card title="Zitadel Managed Directory" loading={directoryLoading}>
              <Space direction="vertical" style={{ width: "100%" }}>
                <Alert
                  type="success"
                  showIcon
                  message="This tenant directory is linked"
                  description="Tenant admins should manage users, groups, domains, IdPs, login policy, and SCIM directly in Zitadel."
                />
                <Paragraph>
                  Console keeps the account linkage, tenant admin mapping, and shared product
                  access. It does not own the tenant directory configuration.
                </Paragraph>
                {selectedDirectory?.directory.management_url ? (
                  <Button
                    type="primary"
                    href={selectedDirectory.directory.management_url}
                    target="_blank"
                  >
                    Open Tenant In Zitadel
                  </Button>
                ) : null}
              </Space>
            </Card>
          )}
        </Space>
      </Drawer>

      <Drawer
        title={`Members: ${selectedAccount?.account_name || ""}`}
        open={membersOpen}
        width={720}
        onClose={() => setMembersOpen(false)}
        destroyOnClose
      >
        <Space direction="vertical" size="large" className="w-full">
          <Alert
            type="info"
            showIcon
            message="Account access mapping"
            description="For Zitadel-linked tenants, adding a member here will create or reuse the underlying user in the tenant organization first, then grant Console/Copilot account access."
          />

          <Form layout="vertical" form={memberForm} onFinish={handleInviteMember}>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="user_email" label="User Email" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="display_name" label="Display Name">
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item
                  name="membership_role"
                  label="Membership Role"
                  initialValue="member"
                  rules={[{ required: true }]}
                >
                  <Select
                    options={[
                      { label: "Member", value: "member" },
                      { label: "Admin", value: "admin" },
                      { label: "Owner", value: "owner" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="product_grants"
                  label="Product Grants"
                  initialValue={["console", "copilot"]}
                >
                  <Select
                    mode="multiple"
                    options={[
                      { label: "Console", value: "console" },
                      { label: "Copilot", value: "copilot" },
                      { label: "Platform Admin", value: "platform-admin" },
                    ]}
                  />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item>
              <Button type="primary" htmlType="submit">
                Add or Sync Member
              </Button>
            </Form.Item>
          </Form>

          <Table
            rowKey="user_id"
            dataSource={members}
            columns={memberColumns}
            loading={membersLoading}
            pagination={false}
          />
        </Space>
      </Drawer>

      <Modal
        open={Boolean(modalPayload)}
        title={modalPayload?.title}
        onCancel={() => setModalPayload(null)}
        footer={[
          <Button key="close" type="primary" onClick={() => setModalPayload(null)}>
            Close
          </Button>,
        ]}
      >
        {modalPayload?.body}
      </Modal>
    </div>
  );
}
