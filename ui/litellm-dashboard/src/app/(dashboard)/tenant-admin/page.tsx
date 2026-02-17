"use client";

import React, { useState, useEffect, useCallback } from "react";
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
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  StopOutlined,
  CheckCircleOutlined,
  TeamOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from "@ant-design/icons";

const { Title, Text } = Typography;

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
}

interface AccountAdmin {
  id: string;
  account_id: string;
  user_email: string;
  role: string;
  created_at: string;
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

export default function TenantAdminPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [adminDrawerOpen, setAdminDrawerOpen] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [adminEmail, setAdminEmail] = useState("");

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
      const response = await fetch("/account/new", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(values),
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
      const response = await fetch(`/account/${selectedAccount.account_id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(values),
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

  const handleAddAdmin = async () => {
    if (!selectedAccount || !adminEmail) return;
    try {
      const response = await fetch(
        `/account/${selectedAccount.account_id}/admin`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ user_email: adminEmail }),
        }
      );
      if (response.ok) {
        message.success("Admin added successfully");
        setAdminEmail("");
        fetchAccounts();
        // Refresh selected account
        const updated = accounts.find(
          (a) => a.account_id === selectedAccount.account_id
        );
        if (updated) setSelectedAccount(updated);
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
        </Space>
      ),
    },
  ];

  const activeAccounts = accounts.filter((a) => a.status === "active").length;
  const totalSpend = accounts.reduce((sum, a) => sum + a.spend, 0);

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={2} style={{ marginBottom: 4 }}>
          Tenant Management
        </Title>
        <Text type="secondary">
          Manage tenant accounts, admins, and resource allocation
        </Text>
      </div>

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
          <Form.Item name="admin_email" label="Initial Admin Email">
            <Input placeholder="e.g., admin@acme.com" />
          </Form.Item>
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
          setAdminEmail("");
        }}
        width={480}
      >
        <div style={{ marginBottom: 16 }}>
          <Text strong>Add New Admin</Text>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <Input
              placeholder="admin@example.com"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              onPressEnter={handleAddAdmin}
            />
            <Button type="primary" onClick={handleAddAdmin}>
              Add
            </Button>
          </div>
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
              </div>
            ))
          )}
        </div>
      </Drawer>
    </div>
  );
}
