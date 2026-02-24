"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  InputNumber,
  Tag,
  Space,
  Popconfirm,
  message,
  Drawer,
  Typography,
  Card,
  Statistic,
  Row,
  Col,
  Tooltip,
  Divider,
  Select,
  Switch,
  Tabs,
  Alert,
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  StopOutlined,
  CheckCircleOutlined,
  TeamOutlined,
  DeleteOutlined,
  ReloadOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  ExclamationCircleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import PriceDataReload from "@/components/price_data_reload";

const BillingOverview = React.lazy(() => import("@/components/tenant-admin/BillingOverview"));
const ModelRegistry = React.lazy(() => import("@/components/tenant-admin/ModelRegistry"));
const AccountEntitlements = React.lazy(() => import("@/components/tenant-admin/AccountEntitlements"));
const CopilotSupportTicketsPage = React.lazy(() => import("@/components/copilot/CopilotSupportTicketsPage"));
const CopilotNotificationTemplatesPage = React.lazy(() => import("@/components/copilot/CopilotNotificationTemplatesPage"));
const CopilotModelsPage = React.lazy(() => import("@/components/copilot/CopilotModelsPage"));
const CopilotDirectoryPage = React.lazy(() => import("@/components/copilot/CopilotDirectoryPage"));
const CopilotGlobalOpsPage = React.lazy(() => import("@/components/copilot/CopilotGlobalOpsPage"));

const { Title, Text } = Typography;
const { TabPane } = Tabs;

interface Account {
  account_id: string;
  account_name: string;
  account_alias?: string;
  domain?: string;
  status: string;
  metadata: Record<string, any>;
  max_budget?: number;
  spend: number;
  created_at: string;
  created_by?: string;
  admins?: AccountAdmin[];
  sso_config?: AccountSSOConfig | null;
}

interface AccountAdmin {
  id: string;
  account_id: string;
  user_email: string;
  role: string;
  created_at: string;
}

interface AccountSSOConfig {
  id: string;
  account_id: string;
  sso_provider?: string;
  enabled: boolean;
  sso_settings: Record<string, any>;
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

function normalizeAuthOrgId(value: unknown): string | undefined {
  const normalized = String(value ?? "").trim();
  return normalized.length > 0 ? normalized : undefined;
}

function mergeAccountMetadata(
  existingMetadata: Record<string, any> | undefined,
  authOrgIdValue: unknown
): Record<string, any> {
  const metadata =
    existingMetadata && typeof existingMetadata === "object"
      ? { ...existingMetadata }
      : {};
  const authOrgId = normalizeAuthOrgId(authOrgIdValue);
  if (authOrgId) {
    metadata.auth_org_id = authOrgId;
  } else {
    delete metadata.auth_org_id;
  }
  return metadata;
}

export default function TenantAdminPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [adminDrawerOpen, setAdminDrawerOpen] = useState(false);
  const [ssoDrawerOpen, setSsoDrawerOpen] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [adminForm] = Form.useForm();
  const [ssoForm] = Form.useForm();
  const [editAdminModalOpen, setEditAdminModalOpen] = useState(false);
  const [editAdminForm] = Form.useForm();
  const [selectedAdminEmail, setSelectedAdminEmail] = useState("");
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [accountToDelete, setAccountToDelete] = useState<Account | null>(null);
  const [ssoConfig, setSsoConfig] = useState<Record<string, any> | null>(null);
  const [ssoLoading, setSsoLoading] = useState(false);

  const accessToken = getCookie("token") || "";

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/account/list", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setAccounts(data.accounts || []);
      } else {
        message.error("Failed to load accounts");
      }
    } catch (error) {
      message.error("Error loading accounts");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const handleCreateAccount = async (values: any) => {
    try {
      const { auth_org_id, ...rest } = values;
      const payload = {
        ...rest,
        metadata: mergeAccountMetadata(values?.metadata, auth_org_id),
      };
      const response = await fetch("/account/new", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        message.success("Account created successfully");
        setCreateModalOpen(false);
        createForm.resetFields();
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to create account");
      }
    } catch (error) {
      message.error("Error creating account");
    }
  };

  const handleUpdateAccount = async (values: any) => {
    if (!selectedAccount) return;
    try {
      const { auth_org_id, ...rest } = values;
      const payload = {
        ...rest,
        metadata: mergeAccountMetadata(selectedAccount.metadata, auth_org_id),
      };
      const response = await fetch(`/account/${selectedAccount.account_id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        message.success("Account updated successfully");
        setEditModalOpen(false);
        editForm.resetFields();
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to update account");
      }
    } catch (error) {
      message.error("Error updating account");
    }
  };

  const handleToggleStatus = async (account: Account) => {
    const newStatus = account.status === "active" ? "suspended" : "active";
    try {
      if (newStatus === "suspended") {
        const response = await fetch(`/account/${account.account_id}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (response.ok) {
          message.success("Account suspended");
          fetchAccounts();
        }
      } else {
        const response = await fetch(`/account/${account.account_id}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ status: "active" }),
        });
        if (response.ok) {
          message.success("Account activated");
          fetchAccounts();
        }
      }
    } catch (error) {
      message.error("Error updating account status");
    }
  };

  const handleAddAdmin = async (values: { user_email: string; password?: string }) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(
        `/account/${selectedAccount.account_id}/admin`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify(values),
        }
      );
      if (response.ok) {
        message.success("Admin added successfully");
        adminForm.resetFields();
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to add admin");
      }
    } catch (error) {
      message.error("Error adding admin");
    }
  };

  const handleRemoveAdmin = async (email: string) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(
        `/account/${selectedAccount.account_id}/admin/${encodeURIComponent(email)}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${accessToken}` },
        }
      );
      if (response.ok) {
        message.success("Admin removed");
        fetchAccounts();
      } else {
        message.error("Failed to remove admin");
      }
    } catch (error) {
      message.error("Error removing admin");
    }
  };

  const handleUpdateAdmin = async (values: { new_email?: string; password?: string }) => {
    if (!selectedAccount || !selectedAdminEmail) return;
    const payload: Record<string, string> = {};
    if (values.new_email && values.new_email !== selectedAdminEmail) {
      payload.new_email = values.new_email;
    }
    if (values.password) {
      payload.password = values.password;
    }
    if (Object.keys(payload).length === 0) {
      message.info("No changes to save");
      return;
    }
    try {
      const response = await fetch(
        `/account/${selectedAccount.account_id}/admin/${encodeURIComponent(selectedAdminEmail)}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify(payload),
        }
      );
      if (response.ok) {
        message.success("Admin updated successfully");
        setEditAdminModalOpen(false);
        editAdminForm.resetFields();
        setSelectedAdminEmail("");
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to update admin");
      }
    } catch (error) {
      message.error("Error updating admin");
    }
  };

  const handleDeleteAccount = async () => {
    if (!accountToDelete) return;
    if (deleteConfirmName !== accountToDelete.account_name) {
      message.error("Account name does not match");
      return;
    }
    try {
      const response = await fetch(
        `/account/${accountToDelete.account_id}/delete`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ account_name: deleteConfirmName }),
        }
      );
      if (response.ok) {
        message.success(`Account '${accountToDelete.account_name}' permanently deleted`);
        setDeleteModalOpen(false);
        setDeleteConfirmName("");
        setAccountToDelete(null);
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to delete account");
      }
    } catch (error) {
      message.error("Error deleting account");
    }
  };

  // SSO Config handlers
  const fetchSSOConfig = async (accountId: string) => {
    setSsoLoading(true);
    try {
      const response = await fetch(`/account/${accountId}/sso`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setSsoConfig(data);
        ssoForm.setFieldsValue({
          sso_provider: data.sso_provider || undefined,
          enabled: data.enabled || false,
          ...flattenSSOSettings(data.sso_settings || {}),
        });
      }
    } catch (error) {
      message.error("Error loading SSO config");
    } finally {
      setSsoLoading(false);
    }
  };

  const flattenSSOSettings = (settings: Record<string, any>) => {
    return {
      google_client_id: settings.google_client_id || "",
      google_client_secret: settings.google_client_secret || "",
      microsoft_client_id: settings.microsoft_client_id || "",
      microsoft_client_secret: settings.microsoft_client_secret || "",
      microsoft_tenant: settings.microsoft_tenant || "",
      generic_client_id: settings.generic_client_id || "",
      generic_client_secret: settings.generic_client_secret || "",
      generic_authorization_endpoint: settings.generic_authorization_endpoint || "",
      generic_token_endpoint: settings.generic_token_endpoint || "",
      generic_userinfo_endpoint: settings.generic_userinfo_endpoint || "",
    };
  };

  const handleSaveSSOConfig = async (values: any) => {
    if (!selectedAccount) return;
    const { sso_provider, enabled, ...settingsFields } = values;

    // Build sso_settings from the form fields
    const sso_settings: Record<string, any> = {};
    for (const [key, val] of Object.entries(settingsFields)) {
      if (val) sso_settings[key] = val;
    }

    try {
      const response = await fetch(
        `/account/${selectedAccount.account_id}/sso`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            sso_provider: sso_provider || null,
            enabled: enabled || false,
            sso_settings,
          }),
        }
      );
      if (response.ok) {
        message.success("SSO configuration saved successfully");
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to save SSO config");
      }
    } catch (error) {
      message.error("Error saving SSO config");
    }
  };

  const handleDeleteSSOConfig = async () => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(
        `/account/${selectedAccount.account_id}/sso`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${accessToken}` },
        }
      );
      if (response.ok) {
        message.success("SSO configuration deleted");
        ssoForm.resetFields();
        setSsoConfig(null);
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to delete SSO config");
      }
    } catch (error) {
      message.error("Error deleting SSO config");
    }
  };

  // Watch sso_provider to show/hide provider-specific fields
  const ssoProvider = Form.useWatch("sso_provider", ssoForm);

  const columns = [
    {
      title: "Account Name",
      dataIndex: "account_name",
      key: "account_name",
      render: (text: string, record: Account) => (
        <Space direction="vertical" size={0}>
          <Text strong>{text}</Text>
          {record.account_alias && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.account_alias}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: "Domain",
      dataIndex: "domain",
      key: "domain",
      render: (domain: string) =>
        domain ? <Tag color="blue">{domain}</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: "Zitadel Org ID",
      key: "auth_org_id",
      render: (_: any, record: Account) => {
        const authOrgId = normalizeAuthOrgId(record?.metadata?.auth_org_id);
        return authOrgId ? <Text code>{authOrgId}</Text> : <Text type="secondary">-</Text>;
      },
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status: string) => (
        <Tag color={status === "active" ? "green" : status === "suspended" ? "red" : "default"}>
          {status.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: "SSO",
      key: "sso",
      render: (_: any, record: Account) => {
        if (record.sso_config && record.sso_config.enabled) {
          return (
            <Tag color="green" icon={<SafetyCertificateOutlined />}>
              {record.sso_config.sso_provider?.toUpperCase() || "Enabled"}
            </Tag>
          );
        }
        return <Text type="secondary">Off</Text>;
      },
    },
    {
      title: "Admins",
      key: "admins",
      render: (_: any, record: Account) => (
        <Space wrap>
          {(record.admins || []).map((admin) => (
            <Tag key={admin.id} color="purple">
              {admin.user_email}
            </Tag>
          ))}
          {(!record.admins || record.admins.length === 0) && (
            <Text type="secondary">No admins</Text>
          )}
        </Space>
      ),
    },
    {
      title: "Budget",
      key: "budget",
      render: (_: any, record: Account) => (
        <Space direction="vertical" size={0}>
          <Text>
            ${record.spend.toFixed(2)} / ${record.max_budget?.toFixed(2) || "Unlimited"}
          </Text>
        </Space>
      ),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (date: string) => new Date(date).toLocaleDateString(),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: Account) => (
        <Space>
          <Tooltip title="Edit">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => {
                setSelectedAccount(record);
                editForm.setFieldsValue({
                  account_name: record.account_name,
                  account_alias: record.account_alias,
                  domain: record.domain,
                  auth_org_id: normalizeAuthOrgId(record?.metadata?.auth_org_id),
                  max_budget: record.max_budget,
                });
                setEditModalOpen(true);
              }}
            />
          </Tooltip>
          <Tooltip title="Manage Admins">
            <Button
              type="text"
              icon={<TeamOutlined />}
              onClick={() => {
                setSelectedAccount(record);
                setAdminDrawerOpen(true);
              }}
            />
          </Tooltip>
          <Tooltip title="SSO Config">
            <Button
              type="text"
              icon={<SafetyCertificateOutlined />}
              onClick={() => {
                setSelectedAccount(record);
                setSsoDrawerOpen(true);
                fetchSSOConfig(record.account_id);
              }}
            />
          </Tooltip>
          <Popconfirm
            title={
              record.status === "active"
                ? "Suspend this account?"
                : "Activate this account?"
            }
            onConfirm={() => handleToggleStatus(record)}
          >
            <Tooltip title={record.status === "active" ? "Suspend" : "Activate"}>
              <Button
                type="text"
                danger={record.status === "active"}
                icon={
                  record.status === "active" ? (
                    <StopOutlined />
                  ) : (
                    <CheckCircleOutlined />
                  )
                }
              />
            </Tooltip>
          </Popconfirm>
          <Tooltip title="Delete permanently">
            <Button
              type="text"
              danger
              icon={<DeleteOutlined />}
              onClick={() => {
                setAccountToDelete(record);
                setDeleteConfirmName("");
                setDeleteModalOpen(true);
              }}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const activeAccounts = accounts.filter((a) => a.status === "active").length;
  const totalSpend = accounts.reduce((sum, a) => sum + a.spend, 0);

  // Keep selectedAccount in sync when accounts refresh
  useEffect(() => {
    if (selectedAccount) {
      const updated = accounts.find(
        (a) => a.account_id === selectedAccount.account_id
      );
      if (updated) setSelectedAccount(updated);
    }
  }, [accounts]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={2} style={{ marginBottom: 4 }}>
          Tenant Management
        </Title>
        <Text type="secondary">
          Manage tenant accounts, admins, SSO configuration, and resource allocation
        </Text>
      </div>

      <Tabs defaultActiveKey="accounts" size="large">
        <TabPane tab="Accounts" key="accounts">
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="Total Accounts" value={accounts.length} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Active Accounts"
              value={activeAccounts}
              valueStyle={{ color: "#3f8600" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Total Spend"
              value={totalSpend}
              precision={2}
              prefix="$"
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Suspended"
              value={accounts.length - activeAccounts}
              valueStyle={
                accounts.length - activeAccounts > 0
                  ? { color: "#cf1322" }
                  : undefined
              }
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 16,
          }}
        >
          <Title level={4} style={{ margin: 0 }}>
            Accounts
          </Title>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchAccounts}>
              Refresh
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateModalOpen(true)}
            >
              Create Account
            </Button>
          </Space>
        </div>

        <Table
          columns={columns}
          dataSource={accounts}
          rowKey="account_id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* System Settings - Price Data Reload */}
      <Card style={{ marginTop: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>
            <SettingOutlined style={{ marginRight: 8 }} />
            System Settings
          </Title>
          <Text type="secondary">
            Global system configuration for all tenants
          </Text>
        </div>
        <Divider />
        <div>
          <Title level={5}>Price Data Management</Title>
          <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
            Manage model pricing data and configure automatic reload schedules
          </Text>
          <PriceDataReload
            accessToken={accessToken}
            onReloadSuccess={() => {}}
            buttonText="Reload Price Data"
            size="middle"
            type="primary"
            className="w-full"
          />
        </div>
      </Card>
        </TabPane>

        <TabPane tab="Billing" key="billing">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <BillingOverview />
          </Suspense>
        </TabPane>

        <TabPane tab="Gateway Models" key="models">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <ModelRegistry />
          </Suspense>
        </TabPane>

        <TabPane tab="Entitlements" key="entitlements">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <AccountEntitlements />
          </Suspense>
        </TabPane>

        <TabPane tab="Copilot Ticket Ops" key="copilot-ticket-ops">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <CopilotSupportTicketsPage />
          </Suspense>
        </TabPane>

        <TabPane tab="Copilot Notification Ops" key="copilot-notification-ops">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <CopilotNotificationTemplatesPage />
          </Suspense>
        </TabPane>

        <TabPane tab="Copilot Model Governance" key="copilot-model-governance">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <CopilotModelsPage />
          </Suspense>
        </TabPane>

        <TabPane tab="Copilot Directory Ops" key="copilot-directory-ops">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <CopilotDirectoryPage />
          </Suspense>
        </TabPane>
        <TabPane tab="Copilot Global Ops" key="copilot-global-ops">
          <Suspense fallback={<div style={{ textAlign: "center", padding: 48 }}>Loading...</div>}>
            <CopilotGlobalOpsPage />
          </Suspense>
        </TabPane>
      </Tabs>

      {/* Create Account Modal */}
      <Modal
        title="Create New Account"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          createForm.resetFields();
        }}
        onOk={() => createForm.submit()}
        okText="Create"
        width={560}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreateAccount}>
          <Form.Item
            name="account_name"
            label="Account Name"
            rules={[{ required: true, message: "Please enter account name" }]}
          >
            <Input placeholder="e.g., Acme Corporation" />
          </Form.Item>
          <Form.Item name="domain" label="Email Domain (for SSO routing)">
            <Input placeholder="e.g., acme.com" />
          </Form.Item>
          <Form.Item
            name="auth_org_id"
            label="Zitadel Organization ID"
            extra="Optional. Map this tenant to a specific Zitadel org ID for reliable account resolution."
          >
            <Input placeholder="e.g., 2814390123422307" />
          </Form.Item>
          <Divider orientation="left" plain>
            Initial Admin
          </Divider>
          <Form.Item name="admin_email" label="Admin Email">
            <Input placeholder="e.g., admin@acme.com" />
          </Form.Item>
          <Form.Item
            name="admin_password"
            label="Admin Password"
            extra="Set a password so the admin can log in. They can also use SSO if configured."
          >
            <Input.Password
              placeholder="Set initial password for admin"
              prefix={<LockOutlined />}
            />
          </Form.Item>
          <Divider orientation="left" plain>
            Budget
          </Divider>
          <Form.Item name="max_budget" label="Max Budget (USD)">
            <InputNumber
              style={{ width: "100%" }}
              min={0}
              step={100}
              placeholder="Leave empty for unlimited"
            />
          </Form.Item>
          <Form.Item name="account_alias" label="Account Alias (optional)">
            <Input placeholder="Optional display name" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Account Modal */}
      <Modal
        title={`Edit Account: ${selectedAccount?.account_name || ""}`}
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false);
          editForm.resetFields();
        }}
        onOk={() => editForm.submit()}
        okText="Save"
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdateAccount}>
          <Form.Item name="account_name" label="Account Name">
            <Input />
          </Form.Item>
          <Form.Item name="account_alias" label="Account Alias">
            <Input />
          </Form.Item>
          <Form.Item name="domain" label="Email Domain">
            <Input />
          </Form.Item>
          <Form.Item
            name="auth_org_id"
            label="Zitadel Organization ID"
            extra="If set, Zitadel users from this org resolve directly to this tenant."
          >
            <Input />
          </Form.Item>
          <Form.Item name="max_budget" label="Max Budget (USD)">
            <InputNumber style={{ width: "100%" }} min={0} step={100} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Admin Management Drawer */}
      <Drawer
        title={`Manage Admins: ${selectedAccount?.account_name || ""}`}
        open={adminDrawerOpen}
        onClose={() => {
          setAdminDrawerOpen(false);
          adminForm.resetFields();
        }}
        width={520}
      >
        <div style={{ marginBottom: 24 }}>
          <Text strong>Add New Admin</Text>
          <Form
            form={adminForm}
            layout="vertical"
            onFinish={handleAddAdmin}
            style={{ marginTop: 8 }}
          >
            <Form.Item
              name="user_email"
              label="Email"
              rules={[{ required: true, message: "Email is required" }]}
            >
              <Input placeholder="admin@example.com" />
            </Form.Item>
            <Form.Item
              name="password"
              label="Password (optional)"
              extra="Set a password for username/password login. Leave blank if admin will only use SSO."
            >
              <Input.Password
                placeholder="Set initial password"
                prefix={<LockOutlined />}
              />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<PlusOutlined />}>
                Add Admin
              </Button>
            </Form.Item>
          </Form>
        </div>

        <Divider />

        <Text strong>Current Admins</Text>
        <div style={{ marginTop: 12 }}>
          {(selectedAccount?.admins || []).length === 0 ? (
            <Text type="secondary">No admins assigned</Text>
          ) : (
            (selectedAccount?.admins || []).map((admin) => (
              <div
                key={admin.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "8px 0",
                  borderBottom: "1px solid #f0f0f0",
                }}
              >
                <Space direction="vertical" size={0}>
                  <Text>{admin.user_email}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {admin.role} - Added{" "}
                    {new Date(admin.created_at).toLocaleDateString()}
                  </Text>
                </Space>
                <Space>
                  <Tooltip title="Edit email / password">
                    <Button
                      type="text"
                      icon={<EditOutlined />}
                      size="small"
                      onClick={() => {
                        setSelectedAdminEmail(admin.user_email);
                        editAdminForm.setFieldsValue({
                          new_email: admin.user_email,
                          password: "",
                        });
                        setEditAdminModalOpen(true);
                      }}
                    />
                  </Tooltip>
                  <Popconfirm
                    title="Remove this admin?"
                    onConfirm={() => handleRemoveAdmin(admin.user_email)}
                  >
                    <Button
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      size="small"
                    />
                  </Popconfirm>
                </Space>
              </div>
            ))
          )}
        </div>
      </Drawer>

      {/* Edit Admin Modal */}
      <Modal
        title={`Edit Admin: ${selectedAdminEmail}`}
        open={editAdminModalOpen}
        onCancel={() => {
          setEditAdminModalOpen(false);
          editAdminForm.resetFields();
          setSelectedAdminEmail("");
        }}
        onOk={() => editAdminForm.submit()}
        okText="Save Changes"
      >
        <Form form={editAdminForm} layout="vertical" onFinish={handleUpdateAdmin}>
          <Form.Item
            name="new_email"
            label="Email"
            rules={[
              { required: true, message: "Email is required" },
              { type: "email", message: "Please enter a valid email" },
            ]}
          >
            <Input placeholder="admin@example.com" />
          </Form.Item>
          <Form.Item
            name="password"
            label="New Password"
            extra="Leave blank to keep the current password."
            rules={[
              { min: 8, message: "Password must be at least 8 characters" },
            ]}
          >
            <Input.Password
              placeholder="Enter new password (optional)"
              prefix={<LockOutlined />}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Delete Account Confirmation Modal */}
      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: "#ff4d4f" }} />
            <span>Delete Account Permanently</span>
          </Space>
        }
        open={deleteModalOpen}
        onCancel={() => {
          setDeleteModalOpen(false);
          setDeleteConfirmName("");
          setAccountToDelete(null);
        }}
        okText="Delete Permanently"
        okButtonProps={{
          danger: true,
          disabled: deleteConfirmName !== accountToDelete?.account_name,
        }}
        onOk={handleDeleteAccount}
      >
        <Alert
          message="This action cannot be undone"
          description="Deleting this account will permanently remove it along with all its admins and SSO configuration. This cannot be reversed."
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Text>
          To confirm, type the account name{" "}
          <Text strong code>{accountToDelete?.account_name}</Text>{" "}
          below:
        </Text>
        <Input
          style={{ marginTop: 8 }}
          placeholder="Type account name to confirm"
          value={deleteConfirmName}
          onChange={(e) => setDeleteConfirmName(e.target.value)}
        />
      </Modal>

      {/* SSO Configuration Drawer */}
      <Drawer
        title={`SSO Configuration: ${selectedAccount?.account_name || ""}`}
        open={ssoDrawerOpen}
        onClose={() => {
          setSsoDrawerOpen(false);
          ssoForm.resetFields();
          setSsoConfig(null);
        }}
        width={560}
      >
        <Alert
          message="SSO Configuration"
          description="Configure Single Sign-On for this account. Users with matching email domains will be redirected to the SSO provider during login. Account admins can also configure this from their Admin Settings page."
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Form
          form={ssoForm}
          layout="vertical"
          onFinish={handleSaveSSOConfig}
          initialValues={{ enabled: false }}
        >
          <Form.Item
            name="sso_provider"
            label="SSO Provider"
          >
            <Select
              placeholder="Select SSO provider"
              allowClear
              options={[
                { value: "google", label: "Google" },
                { value: "microsoft", label: "Microsoft / Azure AD" },
                { value: "okta", label: "Okta" },
                { value: "generic", label: "Generic OIDC" },
              ]}
            />
          </Form.Item>

          <Form.Item
            name="enabled"
            label="Enable SSO"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          {/* Google fields */}
          {ssoProvider === "google" && (
            <>
              <Form.Item name="google_client_id" label="Google Client ID">
                <Input placeholder="Enter Google OAuth Client ID" />
              </Form.Item>
              <Form.Item name="google_client_secret" label="Google Client Secret">
                <Input.Password placeholder="Enter Google OAuth Client Secret" />
              </Form.Item>
            </>
          )}

          {/* Microsoft fields */}
          {ssoProvider === "microsoft" && (
            <>
              <Form.Item name="microsoft_client_id" label="Microsoft Client ID">
                <Input placeholder="Enter Microsoft Client ID" />
              </Form.Item>
              <Form.Item name="microsoft_client_secret" label="Microsoft Client Secret">
                <Input.Password placeholder="Enter Microsoft Client Secret" />
              </Form.Item>
              <Form.Item name="microsoft_tenant" label="Microsoft Tenant">
                <Input placeholder="Enter Microsoft Tenant ID" />
              </Form.Item>
            </>
          )}

          {/* Okta / Generic OIDC fields */}
          {(ssoProvider === "okta" || ssoProvider === "generic") && (
            <>
              <Form.Item name="generic_client_id" label="Client ID">
                <Input placeholder="Enter OIDC Client ID" />
              </Form.Item>
              <Form.Item name="generic_client_secret" label="Client Secret">
                <Input.Password placeholder="Enter OIDC Client Secret" />
              </Form.Item>
              <Form.Item name="generic_authorization_endpoint" label="Authorization Endpoint">
                <Input placeholder="https://your-provider.com/authorize" />
              </Form.Item>
              <Form.Item name="generic_token_endpoint" label="Token Endpoint">
                <Input placeholder="https://your-provider.com/token" />
              </Form.Item>
              <Form.Item name="generic_userinfo_endpoint" label="User Info Endpoint">
                <Input placeholder="https://your-provider.com/userinfo" />
              </Form.Item>
            </>
          )}

          <Space style={{ marginTop: 16 }}>
            <Button type="primary" htmlType="submit" loading={ssoLoading}>
              Save SSO Config
            </Button>
            {ssoConfig && ssoConfig.sso_provider && (
              <Popconfirm
                title="Remove SSO configuration for this account?"
                onConfirm={handleDeleteSSOConfig}
              >
                <Button danger>Delete SSO Config</Button>
              </Popconfirm>
            )}
          </Space>
        </Form>
      </Drawer>
    </div>
  );
}
