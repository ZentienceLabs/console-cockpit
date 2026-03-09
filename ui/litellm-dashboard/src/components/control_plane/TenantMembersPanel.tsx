"use client";

import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import {
  ControlPlaneContext,
  ControlPlaneMember,
  formatMembershipRole,
  isAdminMembership,
  requestControlPlane,
} from "@/components/control_plane/api";
import { ReloadOutlined, SafetyOutlined, TeamOutlined, UserAddOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
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
import { useCallback, useEffect, useMemo, useState } from "react";

const { Paragraph, Text, Title } = Typography;

const productGrantOptions = [
  { label: "Console", value: "console" },
  { label: "Copilot", value: "copilot" },
];

type MembersResponse = {
  members: ControlPlaneMember[];
};

type MemberGrantResponse = {
  message: string;
  user: ControlPlaneMember;
  membership: ControlPlaneMember;
  directory?: {
    managed: boolean;
    reused_existing_user: boolean;
    temporary_password?: string | null;
    invite_code?: string | null;
    warnings?: string[];
    zitadel_sub?: string | null;
  };
};

type ModalPayload = {
  title: string;
  body: React.ReactNode;
};

export default function TenantMembersPanel() {
  const { token, activeAccountId, isSuperAdmin } = useAuthorized();
  const [form] = Form.useForm();
  const [context, setContext] = useState<ControlPlaneContext | null>(null);
  const [members, setMembers] = useState<ControlPlaneMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [modalPayload, setModalPayload] = useState<ModalPayload | null>(null);

  const activeMembership = useMemo(() => {
    const memberships = context?.memberships || [];
    const preferredAccountId = context?.active_account_id || activeAccountId;
    return (
      memberships.find((membership) => membership.account_id === preferredAccountId) ||
      memberships[0] ||
      null
    );
  }, [activeAccountId, context]);

  const resolvedAccountId = activeMembership?.account_id || context?.active_account_id || activeAccountId || null;

  const fetchMembers = useCallback(
    async (accountId: string, sessionToken: string) => {
      const response = await requestControlPlane<MembersResponse>(
        sessionToken,
        `/control-plane/accounts/${accountId}/members`,
      );
      setMembers(response.members || []);
    },
    [],
  );

  const fetchData = useCallback(async () => {
    if (!token) {
      return;
    }

    setLoading(true);
    try {
      const nextContext = await requestControlPlane<ControlPlaneContext>(token, "/control-plane/me/context");
      setContext(nextContext);

      const nextAccountId = nextContext.active_account_id || activeAccountId || null;
      if (nextAccountId) {
        await fetchMembers(nextAccountId, token);
      } else {
        setMembers([]);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load members");
    } finally {
      setLoading(false);
    }
  }, [activeAccountId, fetchMembers, token]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const handleGrantAccess = async (values: {
    user_email: string;
    display_name?: string;
    membership_role: string;
    product_grants?: string[];
  }) => {
    if (!token || !resolvedAccountId) {
      message.error("No active account selected");
      return;
    }

    setSaving(true);
    try {
      const response = await requestControlPlane<MemberGrantResponse>(
        token,
        `/control-plane/accounts/${resolvedAccountId}/members/invite`,
        {
          method: "POST",
          body: JSON.stringify({
            user_email: values.user_email,
            display_name: values.display_name || values.user_email,
            membership_role: values.membership_role,
            product_grants: values.product_grants?.length ? values.product_grants : ["console", "copilot"],
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
          setModalPayload({
            title: "Member Provisioned",
            body: (
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
              </Space>
            ),
          });
        }
      } else {
        message.success("Account access updated");
      }
      form.resetFields();
      await fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to update member");
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveMember = async (member: ControlPlaneMember) => {
    if (!token || !resolvedAccountId) {
      message.error("No active account selected");
      return;
    }

    try {
      await requestControlPlane(
        token,
        `/control-plane/accounts/${resolvedAccountId}/members/${encodeURIComponent(member.user_email)}`,
        {
          method: "DELETE",
        },
      );
      message.success("Member removed from account");
      await fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to remove member");
    }
  };

  const adminCount = members.filter((member) => isAdminMembership(member.membership_role)).length;

  const columns = [
    {
      title: "Member",
      key: "member",
      render: (_: unknown, member: ControlPlaneMember) => (
        <Space direction="vertical" size={0}>
          <Text strong>{member.display_name || member.user_email}</Text>
          <Text type="secondary">{member.user_email}</Text>
        </Space>
      ),
    },
    {
      title: "Role",
      key: "membership_role",
      render: (_: unknown, member: ControlPlaneMember) => (
        <Tag color={isAdminMembership(member.membership_role) ? "blue" : "default"}>
          {formatMembershipRole(member.membership_role)}
        </Tag>
      ),
    },
    {
      title: "Status",
      key: "membership_status",
      render: (_: unknown, member: ControlPlaneMember) => (
        <Tag color={member.membership_status === "active" ? "green" : "orange"}>
          {String(member.membership_status || "unknown").toUpperCase()}
        </Tag>
      ),
    },
    {
      title: "Identity",
      key: "identity",
      render: (_: unknown, member: ControlPlaneMember) =>
        member.zitadel_sub ? <Tag color="purple">Directory Linked</Tag> : <Tag>Pending Setup</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, member: ControlPlaneMember) => (
        <Popconfirm
          title="Remove member?"
          description="This removes the account membership in Console/Copilot. It does not delete the user's underlying identity."
          onConfirm={() => void handleRemoveMember(member)}
          disabled={member.user_email === context?.user?.user_email}
        >
          <Button danger disabled={member.user_email === context?.user?.user_email}>
            Remove
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <div>
          <Title level={3} style={{ marginBottom: 8 }}>
            Members
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            Manage who can access the active account, what role they have, and which products they can use.
          </Paragraph>
        </div>

        {isSuperAdmin ? (
          <Alert
            type="info"
            message="Super admins should use the Tenant Admin portal for cross-account operations."
            description="This page is the tenant-scoped account-access view."
            showIcon
          />
        ) : null}

        <Alert
          type="info"
          showIcon
          icon={<SafetyOutlined />}
          message="Console is the account admin surface"
          description="For Zitadel-linked tenants, adding a member here will create or reuse the underlying user in the tenant organization first, then grant Console/Copilot account access."
        />

        {!activeMembership ? (
          <Alert
            type="warning"
            showIcon
            message="No active account context"
            description="Your session does not currently resolve to an account. Re-login after selecting or assigning an account."
          />
        ) : (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={8}>
                <Card loading={loading}>
                  <Statistic title="Active Account" value={activeMembership.account_name} prefix={<TeamOutlined />} />
                  <Text type="secondary">{formatMembershipRole(activeMembership.membership_role)}</Text>
                </Card>
              </Col>
              <Col xs={12} md={8}>
                <Card loading={loading}>
                  <Statistic title="Members" value={members.length} />
                </Card>
              </Col>
              <Col xs={12} md={8}>
                <Card loading={loading}>
                  <Statistic title="Admins" value={adminCount} />
                </Card>
              </Col>
            </Row>

            <Card
              title="Grant Account Access"
              extra={
                <Space>
                  <Button href="?page=admin-panel">
                    Open Directory &amp; SSO
                  </Button>
                  <Button icon={<ReloadOutlined />} onClick={() => void fetchData()}>
                    Refresh
                  </Button>
                </Space>
              }
            >
              <Paragraph>
                For a Zitadel-linked tenant, this will provision the user in the tenant directory if they do not already exist, then grant Console and Copilot account access.
              </Paragraph>
              <Form
                form={form}
                layout="vertical"
                initialValues={{
                  membership_role: "member",
                  product_grants: ["console", "copilot"],
                }}
                onFinish={(values) => void handleGrantAccess(values)}
              >
                <Row gutter={16}>
                  <Col xs={24} md={10}>
                    <Form.Item
                      label="User Email"
                      name="user_email"
                      rules={[{ required: true, message: "Email is required" }]}
                    >
                      <Input placeholder="user@example.com" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item label="Display Name" name="display_name">
                      <Input placeholder="Optional display name" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item
                      label="Account Role"
                      name="membership_role"
                      rules={[{ required: true, message: "Role is required" }]}
                    >
                      <Select
                        options={[
                          { label: "Member", value: "member" },
                          { label: "Viewer", value: "viewer" },
                          { label: "Admin", value: "admin" },
                          { label: "Owner", value: "owner" },
                        ]}
                      />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item label="Product Access" name="product_grants">
                  <Checkbox.Group options={productGrantOptions} />
                </Form.Item>
                <Button type="primary" icon={<UserAddOutlined />} htmlType="submit" loading={saving}>
                  Provision and Grant Access
                </Button>
              </Form>
            </Card>

            <Card title={`Members in ${activeMembership.account_name}`}>
              <Table
                dataSource={members}
                columns={columns}
                rowKey="membership_id"
                loading={loading}
                pagination={{ pageSize: 10 }}
              />
            </Card>
          </>
        )}
      </Space>
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
    </>
  );
}
