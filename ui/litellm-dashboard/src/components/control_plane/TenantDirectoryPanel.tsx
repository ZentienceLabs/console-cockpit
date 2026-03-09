"use client";

import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import {
  ControlPlaneContext,
  DirectorySummary,
  requestControlPlane,
} from "@/components/control_plane/api";
import {
  CloudSyncOutlined,
  LockOutlined,
  ReloadOutlined,
  SafetyOutlined,
  SettingOutlined,
  UserAddOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

const { Paragraph, Text, Title } = Typography;

type BootstrapResponse = {
  message: string;
  bootstrap: {
    org_id?: string;
    temporary_password?: string | null;
    invite_code?: string | null;
    scim?: {
      endpoint?: string;
      token?: string | null;
      expiration_date?: string;
    } | null;
    warnings?: string[];
  };
};

type ProviderResponse = {
  message: string;
};

type SettingsResponse = {
  message: string;
  settings: {
    domains?: string[];
    warnings?: string[];
    login_policy?: {
      allowUsernamePassword?: boolean;
      allowExternalIdp?: boolean;
      allowRegister?: boolean;
      allowDomainDiscovery?: boolean;
    };
  };
};

type ScimResponse = {
  message: string;
  scim: {
    endpoint?: string;
    token?: string | null;
    expiration_date?: string;
    group_sync_note?: string;
  };
};

type CreateDirectoryUserResponse = {
  message: string;
  result: {
    temporary_password?: string | null;
    invite_code?: string | null;
    reused_existing_user?: boolean;
    warnings?: string[];
  };
};

type ModalPayload = {
  title: string;
  body: React.ReactNode;
};

const providerPresets: Record<
  string,
  {
    label: string;
    issuerPlaceholder: string;
    scopes: string[];
    groupClaim: string;
  }
> = {
  entra_oidc: {
    label: "Microsoft Entra ID",
    issuerPlaceholder: "https://login.microsoftonline.com/<tenant-id>/v2.0",
    scopes: ["openid", "profile", "email", "offline_access"],
    groupClaim: "groups",
  },
  okta_oidc: {
    label: "Okta",
    issuerPlaceholder: "https://your-domain.okta.com/oauth2/default",
    scopes: ["openid", "profile", "email", "groups"],
    groupClaim: "groups",
  },
  google_oidc: {
    label: "Google Workspace",
    issuerPlaceholder: "https://accounts.google.com",
    scopes: ["openid", "profile", "email"],
    groupClaim: "groups",
  },
  generic_oidc: {
    label: "Generic OIDC",
    issuerPlaceholder: "https://idp.example.com",
    scopes: ["openid", "profile", "email"],
    groupClaim: "groups",
  },
};

export default function TenantDirectoryPanel() {
  const { token, activeAccountId, isSuperAdmin } = useAuthorized();
  const [bootstrapForm] = Form.useForm();
  const [providerForm] = Form.useForm();
  const [settingsForm] = Form.useForm();
  const [scimForm] = Form.useForm();
  const [userForm] = Form.useForm();

  const [context, setContext] = useState<ControlPlaneContext | null>(null);
  const [summary, setSummary] = useState<DirectorySummary | null>(null);
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

  const resolvedAccountId =
    activeMembership?.account_id || context?.active_account_id || activeAccountId || null;

  const fetchData = useCallback(async () => {
    if (!token) {
      return;
    }

    setLoading(true);
    try {
      const nextContext = await requestControlPlane<ControlPlaneContext>(
        token,
        "/control-plane/me/context",
      );
      setContext(nextContext);

      const nextAccountId = nextContext.active_account_id || activeAccountId || null;
      if (!nextAccountId) {
        setSummary(null);
        return;
      }

      const nextSummary = await requestControlPlane<DirectorySummary>(
        token,
        `/control-plane/accounts/${nextAccountId}/directory`,
      );
      setSummary(nextSummary);

      const provider = nextSummary.directory.provider || {};
      providerForm.setFieldsValue({
        provider_type: provider.type || "entra_oidc",
        provider_name: provider.name || "",
        issuer: provider.issuer || "",
        client_id: provider.client_id || "",
        scopes: provider.scopes || providerPresets.entra_oidc.scopes,
        auto_register: provider.auto_register ?? true,
        group_claim: provider.group_claim || "groups",
        default_role: provider.default_role || "member",
        sync_mode: provider.sync_mode || "oidc_claim_mapping",
      });
      settingsForm.setFieldsValue({
        primary_domain:
          nextSummary.directory.primary_domain || nextSummary.account.domain || "",
        additional_domains: nextSummary.directory.additional_domains || [],
        login_mode: nextSummary.directory.login_policy?.login_mode || "hybrid",
        allow_register: nextSummary.directory.login_policy?.allow_register ?? false,
        allow_domain_discovery:
          nextSummary.directory.login_policy?.allow_domain_discovery ??
          Boolean(nextSummary.directory.primary_domain),
      });
      scimForm.setFieldsValue({
        expiration_days: 365,
      });
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to load directory settings");
    } finally {
      setLoading(false);
    }
  }, [activeAccountId, providerForm, scimForm, settingsForm, token]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const showSecrets = (title: string, body: React.ReactNode) => {
    setModalPayload({ title, body });
  };

  const handleBootstrap = async (values: {
    first_admin_email: string;
    first_admin_display_name?: string;
    membership_role: string;
    bootstrap_mode: string;
    temporary_password?: string;
    create_scim_service_user?: boolean;
  }) => {
    if (!token || !resolvedAccountId) {
      message.error("No active account selected");
      return;
    }

    setSaving(true);
    try {
      const response = await requestControlPlane<BootstrapResponse>(
        token,
        `/control-plane/accounts/${resolvedAccountId}/directory/bootstrap`,
        {
          method: "POST",
          body: JSON.stringify(values),
        },
      );
      message.success("Directory bootstrapped");
      showSecrets(
        "Directory Bootstrap Complete",
        <Space direction="vertical" style={{ width: "100%" }}>
          <Text>Organization ID: {response.bootstrap.org_id || "Not returned"}</Text>
          {response.bootstrap.temporary_password ? (
            <Card size="small">
              <Text strong>Initial admin temporary password</Text>
              <Paragraph copyable style={{ marginBottom: 0 }}>
                {response.bootstrap.temporary_password}
              </Paragraph>
            </Card>
          ) : null}
          {response.bootstrap.invite_code ? (
            <Card size="small">
              <Text strong>Invite code</Text>
              <Paragraph copyable style={{ marginBottom: 0 }}>
                {response.bootstrap.invite_code}
              </Paragraph>
            </Card>
          ) : null}
          {response.bootstrap.scim?.token ? (
            <Card size="small">
              <Text strong>Initial SCIM token</Text>
              <Paragraph copyable style={{ marginBottom: 0 }}>
                {response.bootstrap.scim.token}
              </Paragraph>
              <Text type="secondary">
                Endpoint: {response.bootstrap.scim.endpoint}
              </Text>
            </Card>
          ) : null}
          {(response.bootstrap.warnings || []).length ? (
            <Alert
              type="warning"
              showIcon
              message="Bootstrap warnings"
              description={(response.bootstrap.warnings || []).join("\n")}
            />
          ) : null}
        </Space>,
      );
      bootstrapForm.resetFields(["temporary_password"]);
      await fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to bootstrap directory");
    } finally {
      setSaving(false);
    }
  };

  const handleConfigureProvider = async (values: {
    provider_type: string;
    provider_name: string;
    issuer: string;
    client_id: string;
    client_secret: string;
    scopes: string[];
    auto_register: boolean;
    group_claim?: string;
    default_role: string;
    sync_mode: string;
  }) => {
    if (!token || !resolvedAccountId) {
      message.error("No active account selected");
      return;
    }

    setSaving(true);
    try {
      await requestControlPlane<ProviderResponse>(
        token,
        `/control-plane/accounts/${resolvedAccountId}/directory/provider`,
        {
          method: "POST",
          body: JSON.stringify(values),
        },
      );
      message.success("Directory provider configured");
      providerForm.resetFields(["client_secret"]);
      await fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to configure provider");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveSettings = async (values: {
    primary_domain?: string;
    additional_domains?: string[];
    login_mode: string;
    allow_register: boolean;
    allow_domain_discovery: boolean;
  }) => {
    if (!token || !resolvedAccountId) {
      message.error("No active account selected");
      return;
    }

    setSaving(true);
    try {
      const response = await requestControlPlane<SettingsResponse>(
        token,
        `/control-plane/accounts/${resolvedAccountId}/directory/settings`,
        {
          method: "POST",
          body: JSON.stringify(values),
        },
      );
      message.success("Tenant login settings updated");
      if ((response.settings.warnings || []).length) {
        showSecrets(
          "Directory Settings Warnings",
          <Alert
            type="warning"
            showIcon
            message="Some settings were saved with warnings"
            description={(response.settings.warnings || []).join("\n")}
          />,
        );
      }
      await fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to update tenant login settings");
    } finally {
      setSaving(false);
    }
  };

  const handleIssueScim = async (values: { expiration_days: number }) => {
    if (!token || !resolvedAccountId) {
      message.error("No active account selected");
      return;
    }

    setSaving(true);
    try {
      const response = await requestControlPlane<ScimResponse>(
        token,
        `/control-plane/accounts/${resolvedAccountId}/directory/scim/bootstrap`,
        {
          method: "POST",
          body: JSON.stringify(values),
        },
      );
      message.success("SCIM credentials issued");
      showSecrets(
        "SCIM Credentials",
        <Space direction="vertical" style={{ width: "100%" }}>
          <Card size="small">
            <Text strong>SCIM endpoint</Text>
            <Paragraph copyable style={{ marginBottom: 0 }}>
              {response.scim.endpoint || ""}
            </Paragraph>
          </Card>
          {response.scim.token ? (
            <Card size="small">
              <Text strong>SCIM bearer token</Text>
              <Paragraph copyable style={{ marginBottom: 0 }}>
                {response.scim.token}
              </Paragraph>
              <Text type="secondary">
                Expires: {response.scim.expiration_date || "Unknown"}
              </Text>
            </Card>
          ) : null}
          <Alert
            type="info"
            showIcon
            message="SCIM scope"
            description={response.scim.group_sync_note}
          />
        </Space>,
      );
      await fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to issue SCIM credentials");
    } finally {
      setSaving(false);
    }
  };

  const handleCreateUser = async (values: {
    user_email: string;
    display_name?: string;
    membership_role: string;
    product_grants: string[];
    bootstrap_mode: string;
    temporary_password?: string;
  }) => {
    if (!token || !resolvedAccountId) {
      message.error("No active account selected");
      return;
    }

    setSaving(true);
    try {
      const response = await requestControlPlane<CreateDirectoryUserResponse>(
        token,
        `/control-plane/accounts/${resolvedAccountId}/directory/users`,
        {
          method: "POST",
          body: JSON.stringify(values),
        },
      );
      message.success("Directory user created");
      showSecrets(
        "Directory User Created",
        <Space direction="vertical" style={{ width: "100%" }}>
          {response.result.temporary_password ? (
            <Card size="small">
              <Text strong>Temporary password</Text>
              <Paragraph copyable style={{ marginBottom: 0 }}>
                {response.result.temporary_password}
              </Paragraph>
            </Card>
          ) : null}
          {response.result.invite_code ? (
            <Card size="small">
              <Text strong>Invite code</Text>
              <Paragraph copyable style={{ marginBottom: 0 }}>
                {response.result.invite_code}
              </Paragraph>
            </Card>
          ) : null}
          {response.result.reused_existing_user ? (
            <Alert
              type="info"
              showIcon
              message="Existing tenant directory user reused"
              description="Console found an existing user in this tenant’s Zitadel organization and only refreshed their account access."
            />
          ) : null}
          {(response.result.warnings || []).length ? (
            <Alert
              type="warning"
              showIcon
              message="User grant warnings"
              description={(response.result.warnings || []).join("\n")}
            />
          ) : null}
        </Space>,
      );
      userForm.resetFields(["user_email", "display_name", "temporary_password"]);
      await fetchData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "Failed to create directory user");
    } finally {
      setSaving(false);
    }
  };

  const activeProviderType =
    Form.useWatch("provider_type", providerForm) || "entra_oidc";
  const providerPreset = providerPresets[activeProviderType] || providerPresets.generic_oidc;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Title level={3} style={{ marginBottom: 8 }}>
          Directory &amp; SSO
        </Title>
        <Paragraph style={{ marginBottom: 0 }}>
          Configure tenant login, external identity providers, SCIM user provisioning, and
          directory-backed user onboarding without exposing Zitadel directly to account admins.
        </Paragraph>
      </div>

      {isSuperAdmin ? (
        <Alert
          type="info"
          showIcon
          message="Super admins should use the Tenant Admin portal for cross-account setup."
          description="This screen is account-scoped and reflects the currently active tenant context."
        />
      ) : null}

      <Alert
        type="info"
        showIcon
        icon={<SafetyOutlined />}
        message="Zitadel is the directory admin surface"
        description="Tenant users, domains, IdP configuration, SSO, and SCIM are managed directly in Zitadel. Console only reflects the linked tenant organization and account access context."
      />

      {!activeMembership ? (
        <Alert
          type="warning"
          showIcon
          message="No active account context"
          description="Your session does not currently resolve to an account. Re-login after selecting or assigning an account."
        />
      ) : null}

      {summary && !summary.management.configured ? (
        <Alert
          type="warning"
          showIcon
          message="Zitadel management credentials are not configured for Console"
          description={
            summary.management.error ||
            "Set ALCHEMI_ZITADEL_PAT or service-account credentials on the backend before using tenant identity linking."
          }
        />
      ) : null}

      <Row gutter={16}>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic title="Directory Org" value={summary?.directory.org_id ? "Linked" : "Pending"} />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic title="SSO" value={summary?.directory.sso_enabled ? "Linked" : "Not Linked"} />
          </Card>
        </Col>
        <Col span={8}>
          <Card loading={loading}>
            <Statistic
              title="Directory Control"
              value={summary?.directory.org_id ? "Zitadel" : "Pending"}
            />
          </Card>
        </Col>
      </Row>

      <Card
        loading={loading}
        title="Current Status"
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void fetchData()}>
            Refresh
          </Button>
        }
      >
        <Descriptions column={1} size="small">
          <Descriptions.Item label="Account">
            {summary?.account.account_name || activeMembership?.account_name || "Unknown"}
          </Descriptions.Item>
          <Descriptions.Item label="Directory Organization">
            {summary?.directory.org_id || <Tag color="orange">Not linked</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="Primary Domain">
            {summary?.directory.primary_domain || (
              <Text type="secondary">Not configured</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Login Mode">
            {summary?.directory.login_policy?.login_mode || "Not configured"}
          </Descriptions.Item>
          <Descriptions.Item label="External Provider">
            {summary?.directory.providers?.length ? (
              <Space>
                {summary.directory.providers.map((provider) => (
                  <Tag key={provider.idp_id || `${provider.type}:${provider.name}`} color="blue">
                    {provider.name || provider.type}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Text type="secondary">No external provider configured yet</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="SCIM">
            {summary?.directory.scim?.endpoint ? (
              <Text copyable>{summary.directory.scim.endpoint}</Text>
            ) : (
              <Text type="secondary">SCIM not issued yet</Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Managed In">
            {summary?.directory.management_url ? (
              <Button type="link" href={summary.directory.management_url} target="_blank">
                Open Zitadel
              </Button>
            ) : (
              <Text type="secondary">Zitadel</Text>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      {!summary?.directory.org_id ? (
        <Alert
          type="warning"
          showIcon
          message={isSuperAdmin ? "This tenant is not linked to a Zitadel organization yet" : "This tenant is not linked to a Zitadel organization yet"}
          description={
            isSuperAdmin
              ? "Create the organization directly in Zitadel first, then link it from the super-admin Tenant Admin portal."
              : "Ask your platform super admin to link this account to the correct Zitadel organization."
          }
        />
      ) : (
        <Card title="Directory Management" loading={loading}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Paragraph>
              Users, groups, domains, IdP connections, SSO policy, and SCIM are managed directly in
              Zitadel for this tenant.
            </Paragraph>
            <Alert
              type="info"
              showIcon
              message="Manage tenant directory in Zitadel"
              description="Console only stores the account-to-organization link and product access mapping. Make all directory and identity changes in Zitadel."
            />
            {summary?.directory.management_url ? (
              <Button type="primary" href={summary.directory.management_url} target="_blank">
                Open Tenant In Zitadel
              </Button>
            ) : null}
          </Space>
        </Card>
      )}

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
    </Space>
  );
}
