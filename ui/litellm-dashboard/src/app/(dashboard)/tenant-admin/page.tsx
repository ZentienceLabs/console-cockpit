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
  Select,
  Switch,
  Tabs,
  Alert,
  Collapse,
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

const { Title, Text } = Typography;
const { TabPane } = Tabs;
const DEFAULT_ZITADEL_ACCOUNT_ID_CLAIM = "alchemi:account_id";
const DEFAULT_ZITADEL_PRODUCT_DOMAINS_CLAIM = "product_domains_allowed";
const DEFAULT_ZITADEL_ROLE_MAPPINGS: Record<string, string> = {
  account_admin: "account_admin",
  console_org_admin: "console_org_admin",
  console_team_admin: "console_team_admin",
  copilot_org_admin: "copilot_org_admin",
  copilot_team_admin: "copilot_team_admin",
  end_user: "end_user",
};

function buildDefaultZitadelRoleMappings(rolePrefix?: string): Record<string, string> {
  const normalizedPrefix = (rolePrefix || "").trim();
  if (!normalizedPrefix) {
    return { ...DEFAULT_ZITADEL_ROLE_MAPPINGS };
  }
  const mappings: Record<string, string> = {};
  Object.entries(DEFAULT_ZITADEL_ROLE_MAPPINGS).forEach(([appRole, zitadelRole]) => {
    mappings[appRole] = `${normalizedPrefix}${zitadelRole}`;
  });
  return mappings;
}

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
  feature_pack?: {
    features: string[];
    config: Record<string, any>;
  };
  console_model_policy?: {
    allow_models: string[];
    deny_models: string[];
  };
  allocation?: {
    monthly_credits: number;
    overflow_limit: number;
    credit_factor: number;
    effective_from?: string;
    updated_at?: string;
  } | null;
  zitadel_config?: {
    enabled?: boolean;
    issuer?: string;
    audience?: string;
    project_id?: string;
    organization_id?: string;
    account_id_claim?: string;
    product_domains_claim?: string;
    role_mappings?: Record<string, string>;
  };
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

interface SuperModelCatalogItem {
  model_id: string;
  model_name: string;
  display_name?: string;
  provider_id?: string;
  deployment_name?: string;
  capability?: string;
  input_cost_per_million?: number | null;
  output_cost_per_million?: number | null;
  api_base_env_var?: string | null;
  api_key_env_var?: string | null;
  sort_order?: number | null;
  is_active?: boolean;
}

interface ZitadelOnboardingDefaults {
  project_id?: string | null;
  organization_id?: string | null;
  role_prefix?: string | null;
  resolve_user_ids_from_zitadel?: boolean;
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
  const [createSubmitting, setCreateSubmitting] = useState(false);
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
  const [policyDrawerOpen, setPolicyDrawerOpen] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [featurePackForm] = Form.useForm();
  const [modelPolicyForm] = Form.useForm();
  const [allocationForm] = Form.useForm();
  const [superModelForm] = Form.useForm();
  const [zitadelConfigForm] = Form.useForm();
  const [zitadelGrantForm] = Form.useForm();
  const [zitadelRoleForm] = Form.useForm();
  const [zitadelBootstrapForm] = Form.useForm();
  const [zitadelQuickOnboardForm] = Form.useForm();
  const [zitadelOnboardLoading, setZitadelOnboardLoading] = useState(false);
  const [zitadelStatus, setZitadelStatus] = useState<{
    auth_provider?: string;
    account_id?: string;
    roles?: string[];
    zitadel_configured?: boolean;
    issuer?: string;
  } | null>(null);
  const [isZitadelConfigured, setIsZitadelConfigured] = useState(false);
  const [zitadelOnboardingDefaults, setZitadelOnboardingDefaults] = useState<ZitadelOnboardingDefaults>({});
  const [modelCatalog, setModelCatalog] = useState<SuperModelCatalogItem[]>([]);
  const [modelCatalogLoading, setModelCatalogLoading] = useState(false);

  const accessToken = getCookie("token") || "";

  const parseJsonInput = (raw: string | undefined, fieldLabel: string): Record<string, any> => {
    if (!raw || raw.trim() === "") return {};
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed;
      }
      throw new Error("JSON value must be an object");
    } catch (error) {
      throw new Error(`${fieldLabel} must be valid JSON object`);
    }
  };

  const openCreateAccountModal = () => {
    const defaults = zitadelOnboardingDefaults || {};
    createForm.resetFields();
    createForm.setFieldsValue({
      auto_onboard_zitadel: isZitadelConfigured,
      zitadel_project_id: defaults.project_id || "",
      zitadel_organization_id: defaults.organization_id || "",
      zitadel_role_prefix: defaults.role_prefix || "",
      zitadel_resolve_user_ids_from_zitadel: defaults.resolve_user_ids_from_zitadel ?? true,
      zitadel_save_defaults: true,
      zitadel_user_id_by_email_json: "{}",
    });
    setCreateModalOpen(true);
  };

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/v1/accounts", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setAccounts(data.items || []);
      } else {
        message.error("Failed to load accounts");
      }
    } catch (error) {
      message.error("Error loading accounts");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  const fetchSuperModels = useCallback(async () => {
    setModelCatalogLoading(true);
    try {
      const response = await fetch("/v1/super/models", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setModelCatalog(data.items || []);
      } else {
        message.error("Failed to load super-admin model catalog");
      }
    } catch (error) {
      message.error("Error loading super-admin model catalog");
    } finally {
      setModelCatalogLoading(false);
    }
  }, [accessToken]);

  const fetchZitadelAuthStatus = useCallback(async () => {
    try {
      const statusRes = await fetch("/v1/auth/zitadel/status", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!statusRes.ok) {
        setZitadelStatus(null);
        setIsZitadelConfigured(false);
        return;
      }
      const statusData = await statusRes.json();
      setZitadelStatus(statusData);
      setIsZitadelConfigured(Boolean(statusData.zitadel_configured || statusData.enabled));
    } catch (error) {
      setZitadelStatus(null);
      setIsZitadelConfigured(false);
    }
  }, [accessToken]);

  const fetchZitadelOnboardingDefaults = useCallback(async () => {
    try {
      const response = await fetch("/v1/super/zitadel/onboarding-defaults", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      const item = data?.item || {};
      setZitadelOnboardingDefaults({
        project_id: item.project_id || "",
        organization_id: item.organization_id || "",
        role_prefix: item.role_prefix || "",
        resolve_user_ids_from_zitadel: item.resolve_user_ids_from_zitadel ?? true,
      });
    } catch (error) {
      // Keep defaults empty if unavailable.
    }
  }, [accessToken]);

  const persistZitadelOnboardingDefaults = useCallback(
    async (values: ZitadelOnboardingDefaults) => {
      const response = await fetch("/v1/super/zitadel/onboarding-defaults", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          project_id: values.project_id || null,
          organization_id: values.organization_id || null,
          role_prefix: values.role_prefix || null,
          resolve_user_ids_from_zitadel: values.resolve_user_ids_from_zitadel ?? true,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to save onboarding defaults");
      }
      const item = payload?.item || {};
      setZitadelOnboardingDefaults({
        project_id: item.project_id || "",
        organization_id: item.organization_id || "",
        role_prefix: item.role_prefix || "",
        resolve_user_ids_from_zitadel: item.resolve_user_ids_from_zitadel ?? true,
      });
    },
    [accessToken]
  );

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  useEffect(() => {
    fetchSuperModels();
  }, [fetchSuperModels]);

  useEffect(() => {
    fetchZitadelAuthStatus();
  }, [fetchZitadelAuthStatus]);

  useEffect(() => {
    fetchZitadelOnboardingDefaults();
  }, [fetchZitadelOnboardingDefaults]);

  const runAutoZitadelOnboarding = async (
    accountId: string,
    values: {
      zitadel_project_id?: string;
      zitadel_organization_id?: string;
      zitadel_role_prefix?: string;
      zitadel_resolve_user_ids_from_zitadel?: boolean;
      zitadel_user_id_by_email_json?: string;
      zitadel_save_defaults?: boolean;
    }
  ) => {
    const projectId = (values.zitadel_project_id || "").trim();
    if (!projectId) {
      throw new Error("Project ID is required when auto-onboarding Zitadel is enabled");
    }
    const organizationId = (values.zitadel_organization_id || "").trim() || null;
    const rolePrefix = (values.zitadel_role_prefix || "").trim();
    const roleMappings = buildDefaultZitadelRoleMappings(rolePrefix);
    const userIdByEmail = parseJsonInput(values.zitadel_user_id_by_email_json, "User ID by email map");

    const configResponse = await fetch(`/v1/accounts/${accountId}/zitadel/config`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        enabled: true,
        issuer: zitadelStatus?.issuer || null,
        audience: null,
        project_id: projectId,
        organization_id: organizationId,
        account_id_claim: DEFAULT_ZITADEL_ACCOUNT_ID_CLAIM,
        product_domains_claim: DEFAULT_ZITADEL_PRODUCT_DOMAINS_CLAIM,
        role_mappings: roleMappings,
      }),
    });
    const configPayload = await configResponse.json().catch(() => ({}));
    if (!configResponse.ok) {
      throw new Error(configPayload.detail || "Failed to save Zitadel config during account onboarding");
    }

    const bootstrapResponse = await fetch(`/v1/accounts/${accountId}/zitadel/provision/bootstrap`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        project_id: projectId,
        organization_id: organizationId,
        role_prefix: rolePrefix || null,
        apply_default_role_mappings: true,
        create_project_roles: true,
        grant_existing_account_admins: true,
        resolve_user_ids_from_zitadel: values.zitadel_resolve_user_ids_from_zitadel ?? true,
        default_role_keys: [],
        user_id_by_email: userIdByEmail,
        dry_run: false,
        skip_existing: true,
      }),
    });
    const bootstrapPayload = await bootstrapResponse.json().catch(() => ({}));
    if (!bootstrapResponse.ok) {
      throw new Error(bootstrapPayload.detail || "Failed to bootstrap Zitadel during account onboarding");
    }

    if (values.zitadel_save_defaults) {
      await persistZitadelOnboardingDefaults({
        project_id: projectId,
        organization_id: organizationId || "",
        role_prefix: rolePrefix,
        resolve_user_ids_from_zitadel: values.zitadel_resolve_user_ids_from_zitadel ?? true,
      });
    }

    return bootstrapPayload.summary || {};
  };

  const handleCreateAccount = async (values: any) => {
    try {
      setCreateSubmitting(true);
      const createPayload = {
        account_name: values.account_name,
        account_alias: values.account_alias,
        domain: values.domain,
        max_budget: values.max_budget,
        admin_email: values.admin_email,
        admin_password: values.admin_password,
      };
      const response = await fetch("/v1/accounts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(createPayload),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        message.error(payload.detail || "Failed to create account");
        return;
      }

      const accountId = payload.account_id || payload?.item?.account_id;
      if (values.auto_onboard_zitadel) {
        if (!accountId) {
          message.warning("Account created, but account ID was missing so auto-onboarding was skipped");
        } else {
          const summary = await runAutoZitadelOnboarding(accountId, values);
          const unresolvedCount = Array.isArray(summary.unresolved_admins) ? summary.unresolved_admins.length : 0;
          message.success("Account created and Zitadel onboarding completed");
          if (unresolvedCount > 0) {
            Modal.warning({
              title: "Account created, onboarding completed with unresolved admins",
              content: `Unresolved admins: ${unresolvedCount}. Add explicit user-id mapping in Zitadel onboarding if needed.`,
            });
          }
        }
      } else {
        message.success("Account created successfully");
      }

      setCreateModalOpen(false);
      createForm.resetFields();
      fetchAccounts();
    } catch (error: any) {
      message.error(error?.message || "Error creating account");
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleUpdateAccount = async (values: any) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(`/v1/accounts/${selectedAccount.account_id}`, {
        method: "PATCH",
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
      const response = await fetch(`/v1/accounts/${account.account_id}/status`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ status: newStatus }),
      });
      if (response.ok) {
        message.success(newStatus === "suspended" ? "Account suspended" : "Account activated");
        fetchAccounts();
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to update account status");
      }
    } catch (error) {
      message.error("Error updating account status");
    }
  };

  const handleAddAdmin = async (values: { user_email: string; password?: string }) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(
        `/v1/accounts/${selectedAccount.account_id}/admins`,
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
        `/v1/accounts/${selectedAccount.account_id}/admins/${encodeURIComponent(email)}`,
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
        `/v1/accounts/${selectedAccount.account_id}/admins/${encodeURIComponent(selectedAdminEmail)}`,
        {
          method: "PATCH",
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
        `/v1/accounts/${accountToDelete.account_id}?hard_delete=true&confirm_name=${encodeURIComponent(deleteConfirmName)}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${accessToken}` },
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
      const response = await fetch(`/v1/accounts/${accountId}/sso`, {
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
        `/v1/accounts/${selectedAccount.account_id}/sso`,
        {
          method: "POST",
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
        `/v1/accounts/${selectedAccount.account_id}/sso`,
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

  const loadPolicyBundle = async (accountId: string) => {
    setPolicyLoading(true);
    try {
      const response = await fetch(`/v1/accounts/${accountId}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to load account policy bundle");
        return;
      }

      const data = await response.json();
      const item: Account = data.item || data;
      setSelectedAccount(item);

      const statusRes = await fetch("/v1/auth/zitadel/status", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setZitadelStatus(statusData);
        setIsZitadelConfigured(Boolean(statusData.zitadel_configured || statusData.enabled));
      } else {
        setZitadelStatus(null);
        setIsZitadelConfigured(false);
      }

      const featurePack = item.feature_pack || { features: [], config: {} };
      featurePackForm.setFieldsValue({
        features: featurePack.features || [],
        config_json: JSON.stringify(featurePack.config || {}, null, 2),
      });

      const modelPolicy = item.console_model_policy || { allow_models: [], deny_models: [] };
      modelPolicyForm.setFieldsValue({
        allow_models: modelPolicy.allow_models || [],
      });

      const allocation = item.allocation || { monthly_credits: 0, overflow_limit: 0, credit_factor: 1 };
      allocationForm.setFieldsValue({
        monthly_credits: Number(allocation.monthly_credits || 0),
        overflow_limit: Number(allocation.overflow_limit || 0),
        credit_factor: Number(allocation.credit_factor || 1),
      });

      const zitadel = item.zitadel_config || {};
      const defaultProjectId = zitadelOnboardingDefaults.project_id || "";
      const defaultOrganizationId = zitadelOnboardingDefaults.organization_id || "";
      const defaultRolePrefix = zitadelOnboardingDefaults.role_prefix || "";
      const defaultResolveUsers = zitadelOnboardingDefaults.resolve_user_ids_from_zitadel ?? true;
      zitadelConfigForm.setFieldsValue({
        enabled: typeof zitadel.enabled === "boolean" ? zitadel.enabled : true,
        issuer: zitadel.issuer || "",
        audience: zitadel.audience || "",
        project_id: zitadel.project_id || defaultProjectId,
        organization_id: zitadel.organization_id || defaultOrganizationId,
        account_id_claim: zitadel.account_id_claim || "",
        product_domains_claim: zitadel.product_domains_claim || "",
        role_mappings_json: JSON.stringify(zitadel.role_mappings || {}, null, 2),
      });
      zitadelBootstrapForm.setFieldsValue({
        project_id: zitadel.project_id || defaultProjectId,
        organization_id: zitadel.organization_id || defaultOrganizationId,
      });
      zitadelQuickOnboardForm.setFieldsValue({
        project_id: zitadel.project_id || defaultProjectId,
        organization_id: zitadel.organization_id || defaultOrganizationId,
        role_prefix: defaultRolePrefix,
        default_role_keys: [],
        user_id_by_email_json: "{}",
        resolve_user_ids_from_zitadel: defaultResolveUsers,
        dry_run: true,
      });
    } catch (error) {
      message.error("Error loading account policy bundle");
    } finally {
      setPolicyLoading(false);
    }
  };

  const handleSaveFeaturePack = async (values: { features?: string[]; config_json?: string }) => {
    if (!selectedAccount) return;
    try {
      const config = parseJsonInput(values.config_json, "Feature config");
      const response = await fetch(`/v1/accounts/${selectedAccount.account_id}/feature-pack`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          features: values.features || [],
          config,
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to save feature pack");
        return;
      }
      message.success("Feature pack saved");
      fetchAccounts();
      await loadPolicyBundle(selectedAccount.account_id);
    } catch (error: any) {
      message.error(error?.message || "Error saving feature pack");
    }
  };

  const handleSaveModelPolicy = async (values: { allow_models?: string[] }) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(`/v1/accounts/${selectedAccount.account_id}/console-model-policy`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          allow_models: values.allow_models || [],
          deny_models: [],
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to save console model policy");
        return;
      }
      message.success("Console model policy saved");
      fetchAccounts();
      await loadPolicyBundle(selectedAccount.account_id);
    } catch (error) {
      message.error("Error saving console model policy");
    }
  };

  const handleUpsertSuperModel = async (values: {
    model_id?: string;
    model_name: string;
    display_name?: string;
    provider_id?: string;
    deployment_name: string;
    capability?: string;
    input_cost_per_million?: number;
    output_cost_per_million?: number;
    api_base_env_var?: string;
    api_key_env_var?: string;
    litellm_provider?: string;
    sort_order?: number;
    is_active?: boolean;
    content_capabilities_json?: string;
    extra_body_json?: string;
  }) => {
    try {
      const content_capabilities = parseJsonInput(values.content_capabilities_json, "Content capabilities");
      const extra_body = parseJsonInput(values.extra_body_json, "Extra body");
      const response = await fetch("/v1/super/models/upsert", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          model_id: values.model_id || undefined,
          model_name: values.model_name,
          display_name: values.display_name || null,
          provider_id: values.provider_id || null,
          deployment_name: values.deployment_name,
          capability: values.capability || null,
          input_cost_per_million:
            values.input_cost_per_million !== undefined ? Number(values.input_cost_per_million) : null,
          output_cost_per_million:
            values.output_cost_per_million !== undefined ? Number(values.output_cost_per_million) : null,
          api_base_env_var: values.api_base_env_var || null,
          api_key_env_var: values.api_key_env_var || null,
          litellm_provider: values.litellm_provider || null,
          sort_order: values.sort_order !== undefined ? Number(values.sort_order) : 100,
          is_active: values.is_active ?? true,
          content_capabilities,
          extra_body,
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to save model");
        return;
      }
      message.success("Model saved");
      superModelForm.resetFields(["model_id", "model_name", "display_name", "provider_id", "deployment_name", "capability"]);
      await fetchSuperModels();
    } catch (error: any) {
      message.error(error?.message || "Error saving model");
    }
  };

  const handleDeleteSuperModel = async (modelId: string) => {
    try {
      const response = await fetch(`/v1/super/models/${modelId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to delete model");
        return;
      }
      message.success("Model deleted");
      await fetchSuperModels();
    } catch (error) {
      message.error("Error deleting model");
    }
  };

  const handleSaveAllocation = async (values: {
    monthly_credits: number;
    overflow_limit: number;
    credit_factor: number;
  }) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch("/v1/budgets/account-allocation", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          account_id: selectedAccount.account_id,
          monthly_credits: Number(values.monthly_credits || 0),
          overflow_limit: Number(values.overflow_limit || 0),
          credit_factor: Number(values.credit_factor || 1),
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to save account allocation");
        return;
      }
      message.success("Account allocation saved");
      fetchAccounts();
      await loadPolicyBundle(selectedAccount.account_id);
    } catch (error) {
      message.error("Error saving account allocation");
    }
  };

  const handleSaveZitadelConfig = async (values: {
    enabled?: boolean;
    issuer?: string;
    audience?: string;
    project_id?: string;
    organization_id?: string;
    account_id_claim?: string;
    product_domains_claim?: string;
    role_mappings_json?: string;
  }) => {
    if (!selectedAccount) return;
    try {
      const role_mappings = parseJsonInput(values.role_mappings_json, "Role mappings");
      const response = await fetch(`/v1/accounts/${selectedAccount.account_id}/zitadel/config`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          enabled: values.enabled ?? true,
          issuer: values.issuer || null,
          audience: values.audience || null,
          project_id: values.project_id || null,
          organization_id: values.organization_id || null,
          account_id_claim: values.account_id_claim || null,
          product_domains_claim: values.product_domains_claim || null,
          role_mappings,
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to save Zitadel config");
        return;
      }
      message.success("Zitadel config saved");
      await loadPolicyBundle(selectedAccount.account_id);
    } catch (error: any) {
      message.error(error?.message || "Error saving Zitadel config");
    }
  };

  const handleProvisionZitadelGrant = async (values: {
    user_id: string;
    role_keys: string[];
    project_id?: string;
    organization_id?: string;
  }) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(`/v1/accounts/${selectedAccount.account_id}/zitadel/provision/user-grant`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          user_id: values.user_id,
          role_keys: values.role_keys || [],
          project_id: values.project_id || null,
          organization_id: values.organization_id || null,
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to provision user grant");
        return;
      }
      message.success("User grant provisioned in Zitadel");
      zitadelGrantForm.resetFields();
    } catch (error) {
      message.error("Error provisioning user grant");
    }
  };

  const handleProvisionZitadelRole = async (values: {
    key: string;
    display_name: string;
    group?: string;
    project_id?: string;
  }) => {
    if (!selectedAccount) return;
    try {
      const response = await fetch(`/v1/accounts/${selectedAccount.account_id}/zitadel/provision/project-role`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          key: values.key,
          display_name: values.display_name,
          group: values.group || null,
          project_id: values.project_id || null,
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        message.error(err.detail || "Failed to provision project role");
        return;
      }
      message.success("Project role provisioned in Zitadel");
      zitadelRoleForm.resetFields();
    } catch (error) {
      message.error("Error provisioning project role");
    }
  };

  const handleBootstrapZitadel = async (values: {
    project_id?: string;
    organization_id?: string;
    role_prefix?: string;
    apply_default_role_mappings?: boolean;
    create_project_roles?: boolean;
    grant_existing_account_admins?: boolean;
    resolve_user_ids_from_zitadel?: boolean;
    default_role_keys?: string[];
    user_id_by_email_json?: string;
    dry_run?: boolean;
  }) => {
    if (!selectedAccount) return;
    try {
      const userIdByEmail = parseJsonInput(values.user_id_by_email_json, "User ID by email map");
      const response = await fetch(`/v1/accounts/${selectedAccount.account_id}/zitadel/provision/bootstrap`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          project_id: values.project_id || null,
          organization_id: values.organization_id || null,
          role_prefix: values.role_prefix || null,
          apply_default_role_mappings: values.apply_default_role_mappings ?? true,
          create_project_roles: values.create_project_roles ?? true,
          grant_existing_account_admins: values.grant_existing_account_admins ?? true,
          resolve_user_ids_from_zitadel: values.resolve_user_ids_from_zitadel ?? false,
          default_role_keys: values.default_role_keys || [],
          user_id_by_email: userIdByEmail,
          dry_run: values.dry_run ?? false,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        message.error(payload.detail || "Failed to run Zitadel bootstrap");
        return;
      }

      const summary = payload.summary || {};
      const roleSummary = summary.role_sync_summary || {};
      const grantSummary = summary.admin_grant_summary || {};
      const unresolvedCount = Array.isArray(summary.unresolved_admins) ? summary.unresolved_admins.length : 0;
      const mode = summary.dry_run ? "Dry-run" : "Applied";

      Modal.info({
        title: `Zitadel Bootstrap ${mode}`,
        width: 680,
        content: (
          <div>
            <p>Project: {summary.project_id || "-"}</p>
            <p>Organization: {summary.organization_id || "-"}</p>
            <p>
              Roles - created: {Number(roleSummary.created || 0)}, exists: {Number(roleSummary.exists || 0)}, failed:{" "}
              {Number(roleSummary.failed || 0)}
            </p>
            <p>
              Admin grants - created: {Number(grantSummary.created || 0)}, exists: {Number(grantSummary.exists || 0)}, failed:{" "}
              {Number(grantSummary.failed || 0)}
            </p>
            <p>Unresolved admins: {unresolvedCount}</p>
          </div>
        ),
      });

      if (!summary.dry_run) {
        await loadPolicyBundle(selectedAccount.account_id);
      }
    } catch (error: any) {
      message.error(error?.message || "Error running Zitadel bootstrap");
    }
  };

  const handleQuickOnboardZitadel = async (values: {
    project_id: string;
    organization_id?: string;
    role_prefix?: string;
    default_role_keys?: string[];
    user_id_by_email_json?: string;
    resolve_user_ids_from_zitadel?: boolean;
    dry_run?: boolean;
    save_as_global_defaults?: boolean;
  }) => {
    if (!selectedAccount) return;
    const rolePrefix = (values.role_prefix || "").trim();
    try {
      setZitadelOnboardLoading(true);
      const userIdByEmail = parseJsonInput(values.user_id_by_email_json, "User ID by email map");
      const roleMappings = buildDefaultZitadelRoleMappings(rolePrefix);

      const configResponse = await fetch(`/v1/accounts/${selectedAccount.account_id}/zitadel/config`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          enabled: true,
          issuer: selectedAccount?.zitadel_config?.issuer || null,
          audience: selectedAccount?.zitadel_config?.audience || null,
          project_id: values.project_id || null,
          organization_id: values.organization_id || null,
          account_id_claim: DEFAULT_ZITADEL_ACCOUNT_ID_CLAIM,
          product_domains_claim: DEFAULT_ZITADEL_PRODUCT_DOMAINS_CLAIM,
          role_mappings: roleMappings,
        }),
      });

      const configPayload = await configResponse.json().catch(() => ({}));
      if (!configResponse.ok) {
        message.error(configPayload.detail || "Failed to save Zitadel config");
        return;
      }

      const bootstrapResponse = await fetch(`/v1/accounts/${selectedAccount.account_id}/zitadel/provision/bootstrap`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          project_id: values.project_id || null,
          organization_id: values.organization_id || null,
          role_prefix: rolePrefix || null,
          apply_default_role_mappings: true,
          create_project_roles: true,
          grant_existing_account_admins: true,
          resolve_user_ids_from_zitadel: values.resolve_user_ids_from_zitadel ?? true,
          default_role_keys: values.default_role_keys || [],
          user_id_by_email: userIdByEmail,
          dry_run: values.dry_run ?? true,
          skip_existing: true,
        }),
      });

      const payload = await bootstrapResponse.json();
      if (!bootstrapResponse.ok) {
        message.error(payload.detail || "Failed to run Zitadel onboarding");
        return;
      }

      const summary = payload.summary || {};
      const roleSummary = summary.role_sync_summary || {};
      const grantSummary = summary.admin_grant_summary || {};
      const unresolvedCount = Array.isArray(summary.unresolved_admins) ? summary.unresolved_admins.length : 0;
      const mode = summary.dry_run ? "Dry-run" : "Applied";

      Modal.success({
        title: `Zitadel Tenant Onboarding ${mode}`,
        width: 700,
        content: (
          <div>
            <p>Project: {summary.project_id || "-"}</p>
            <p>Organization: {summary.organization_id || "-"}</p>
            <p>
              Roles - created: {Number(roleSummary.created || 0)}, exists: {Number(roleSummary.exists || 0)}, failed:{" "}
              {Number(roleSummary.failed || 0)}
            </p>
            <p>
              Admin grants - created: {Number(grantSummary.created || 0)}, exists: {Number(grantSummary.exists || 0)}, failed:{" "}
              {Number(grantSummary.failed || 0)}
            </p>
            <p>Unresolved admins: {unresolvedCount}</p>
          </div>
        ),
      });

      if (!summary.dry_run) {
        await loadPolicyBundle(selectedAccount.account_id);
      }

      if (values.save_as_global_defaults) {
        await persistZitadelOnboardingDefaults({
          project_id: values.project_id || "",
          organization_id: values.organization_id || "",
          role_prefix: rolePrefix,
          resolve_user_ids_from_zitadel: values.resolve_user_ids_from_zitadel ?? true,
        });
      }
    } catch (error: any) {
      message.error(error?.message || "Error running Zitadel onboarding");
    } finally {
      setZitadelOnboardLoading(false);
    }
  };

  // Watch sso_provider to show/hide provider-specific fields
  const ssoProvider = Form.useWatch("sso_provider", ssoForm);
  const createAutoOnboard = Form.useWatch("auto_onboard_zitadel", createForm);

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
    ...(!isZitadelConfigured
      ? [
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
        ]
      : []),
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
          {!isZitadelConfigured && (
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
          )}
          <Tooltip title="Policies & Budget">
            <Button
              type="text"
              icon={<SettingOutlined />}
              onClick={() => {
                setSelectedAccount(record);
                setPolicyDrawerOpen(true);
                loadPolicyBundle(record.account_id);
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
  const modelPolicyOptions = modelCatalog
    .filter((model) => model.is_active !== false)
    .map((model) => ({
      value: model.model_name,
      label: `${model.display_name || model.model_name}${model.capability ? ` (${model.capability})` : ""}`,
    }));

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
          Manage tenant accounts, admins, auth configuration, and resource allocation
        </Text>
      </div>

      {isZitadelConfigured && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Zitadel-first mode enabled"
          description="Legacy per-account SSO configuration is hidden because centralized Zitadel authentication is configured."
        />
      )}

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
              onClick={openCreateAccountModal}
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

        <Divider />

        <div>
          <Title level={5}>Global Model Catalog (Super Admin)</Title>
          <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
            Add and manage globally available proxy models directly from tenant admin.
          </Text>

          <Form
            form={superModelForm}
            layout="vertical"
            onFinish={handleUpsertSuperModel}
            initialValues={{
              provider_id: "azure_openai",
              capability: "balanced",
              api_base_env_var: "AZURE_OPENAI_ENDPOINT",
              api_key_env_var: "AZURE_OPENAI_API_KEY",
              litellm_provider: "azure",
              sort_order: 100,
              is_active: true,
              content_capabilities_json: "{}",
              extra_body_json: "{}",
            }}
          >
            <Form.Item name="model_id" hidden>
              <Input />
            </Form.Item>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item
                  name="model_name"
                  label="Model Alias"
                  rules={[{ required: true, message: "Model alias is required" }]}
                >
                  <Input placeholder="gpt-5.2_smart" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name="display_name"
                  label="Display Name"
                  rules={[{ required: true, message: "Display name is required" }]}
                >
                  <Input placeholder="GPT-5.2 Smart" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name="deployment_name"
                  label="Deployment Name"
                  rules={[{ required: true, message: "Deployment name is required" }]}
                >
                  <Input placeholder="gpt-5.2" />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={12}>
              <Col span={6}>
                <Form.Item name="provider_id" label="Provider">
                  <Select
                    options={[
                      { value: "azure_openai", label: "Azure OpenAI" },
                      { value: "azure_anthropic", label: "Azure Anthropic" },
                      { value: "azure_xai", label: "Azure xAI" },
                      { value: "vertex_ai", label: "Vertex AI" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="capability" label="Capability">
                  <Select
                    options={[
                      { value: "fast", label: "fast" },
                      { value: "balanced", label: "balanced" },
                      { value: "smart", label: "smart" },
                      { value: "thinking", label: "thinking" },
                      { value: "expert", label: "expert" },
                      { value: "expert-thinking", label: "expert-thinking" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="input_cost_per_million" label="Input $ / 1M">
                  <InputNumber style={{ width: "100%" }} min={0} step={0.001} />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="output_cost_per_million" label="Output $ / 1M">
                  <InputNumber style={{ width: "100%" }} min={0} step={0.001} />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={12}>
              <Col span={6}>
                <Form.Item name="api_base_env_var" label="API Base Env">
                  <Input placeholder="AZURE_OPENAI_ENDPOINT" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="api_key_env_var" label="API Key Env">
                  <Input placeholder="AZURE_OPENAI_API_KEY" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item name="litellm_provider" label="LiteLLM Provider">
                  <Input placeholder="azure | anthropic | openai | gemini" />
                </Form.Item>
              </Col>
              <Col span={3}>
                <Form.Item name="sort_order" label="Sort Order">
                  <InputNumber style={{ width: "100%" }} min={0} step={1} />
                </Form.Item>
              </Col>
              <Col span={3}>
                <Form.Item name="is_active" label="Active" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="content_capabilities_json" label="Content Capabilities (JSON)">
                  <Input.TextArea rows={3} spellCheck={false} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="extra_body_json" label="Extra Body (JSON)">
                  <Input.TextArea rows={3} spellCheck={false} />
                </Form.Item>
              </Col>
            </Row>

            <Space style={{ marginBottom: 16 }}>
              <Button type="primary" htmlType="submit">
                Save Model
              </Button>
              <Button onClick={() => superModelForm.resetFields()}>Reset</Button>
              <Button onClick={fetchSuperModels} icon={<ReloadOutlined />} loading={modelCatalogLoading}>
                Refresh Catalog
              </Button>
            </Space>
          </Form>

          <Table
            size="small"
            rowKey="model_id"
            loading={modelCatalogLoading}
            pagination={{ pageSize: 8 }}
            dataSource={modelCatalog}
            columns={[
              { title: "Alias", dataIndex: "model_name", key: "model_name" },
              { title: "Display", dataIndex: "display_name", key: "display_name" },
              { title: "Provider", dataIndex: "provider_id", key: "provider_id" },
              { title: "Deployment", dataIndex: "deployment_name", key: "deployment_name" },
              { title: "Capability", dataIndex: "capability", key: "capability" },
              {
                title: "Status",
                key: "is_active",
                render: (_: any, record: SuperModelCatalogItem) => (
                  <Tag color={record.is_active === false ? "red" : "green"}>
                    {record.is_active === false ? "INACTIVE" : "ACTIVE"}
                  </Tag>
                ),
              },
              {
                title: "Actions",
                key: "actions",
                render: (_: any, record: SuperModelCatalogItem) => (
                  <Space>
                    <Button
                      size="small"
                      onClick={() => {
                        const asAny = record as any;
                        superModelForm.setFieldsValue({
                          model_id: record.model_id,
                          model_name: record.model_name,
                          display_name: record.display_name || "",
                          provider_id: record.provider_id || "",
                          deployment_name: record.deployment_name || "",
                          capability: record.capability || "",
                          input_cost_per_million: record.input_cost_per_million ?? undefined,
                          output_cost_per_million: record.output_cost_per_million ?? undefined,
                          api_base_env_var: record.api_base_env_var || "",
                          api_key_env_var: record.api_key_env_var || "",
                          sort_order: record.sort_order ?? 100,
                          is_active: record.is_active !== false,
                          content_capabilities_json: JSON.stringify(asAny.model_info?.content_capabilities || {}, null, 2),
                          extra_body_json: JSON.stringify(asAny.model_info?.extra_body || asAny.litellm_params?.extra_body || {}, null, 2),
                        });
                      }}
                    >
                      Edit
                    </Button>
                    <Popconfirm
                      title="Delete this model?"
                      onConfirm={() => handleDeleteSuperModel(record.model_id)}
                    >
                      <Button size="small" danger>
                        Delete
                      </Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </div>
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
        okText={createAutoOnboard ? "Create + Onboard" : "Create"}
        confirmLoading={createSubmitting}
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

          {isZitadelConfigured && (
            <>
              <Divider orientation="left" plain>
                Zitadel Auto-Onboarding (Recommended)
              </Divider>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                message="Fast path"
                description="Create account and run Zitadel role/grant bootstrap in one submit."
              />
              <Form.Item
                name="auto_onboard_zitadel"
                label="Enable auto-onboarding"
                valuePropName="checked"
                initialValue
              >
                <Switch checkedChildren="On" unCheckedChildren="Off" />
              </Form.Item>

              <Form.Item
                noStyle
                shouldUpdate={(prevValues, curValues) => prevValues.auto_onboard_zitadel !== curValues.auto_onboard_zitadel}
              >
                {({ getFieldValue }) =>
                  getFieldValue("auto_onboard_zitadel") ? (
                    <>
                      <Form.Item
                        name="zitadel_project_id"
                        label="Project ID"
                        rules={[{ required: true, message: "Project ID is required when auto-onboarding is enabled" }]}
                      >
                        <Input placeholder="zitadel project id" />
                      </Form.Item>
                      <Form.Item name="zitadel_organization_id" label="Organization ID (optional)">
                        <Input placeholder="zitadel org id (optional)" />
                      </Form.Item>
                      <Form.Item name="zitadel_role_prefix" label="Role Key Prefix (optional)">
                        <Input placeholder="e.g. zentience_" />
                      </Form.Item>
                      <Form.Item
                        name="zitadel_resolve_user_ids_from_zitadel"
                        label="Resolve user IDs from Zitadel email search"
                        valuePropName="checked"
                        initialValue
                      >
                        <Switch checkedChildren="Auto resolve" unCheckedChildren="Manual mapping" />
                      </Form.Item>
                      <Form.Item name="zitadel_save_defaults" label="Save as global defaults" valuePropName="checked" initialValue>
                        <Switch checkedChildren="Shared defaults" unCheckedChildren="Do not save" />
                      </Form.Item>
                      <Collapse
                        items={[
                          {
                            key: "create-zitadel-advanced",
                            label: "Advanced: User ID by Email JSON",
                            children: (
                              <Form.Item
                                name="zitadel_user_id_by_email_json"
                                initialValue="{}"
                                extra='Example: {"admin@acme.com":"123456789"}'
                              >
                                <Input.TextArea rows={4} spellCheck={false} />
                              </Form.Item>
                            ),
                          },
                        ]}
                      />
                    </>
                  ) : null
                }
              </Form.Item>
            </>
          )}
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
          description="Deleting this account will permanently remove it along with all its admins and auth configuration. This cannot be reversed."
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

      {!isZitadelConfigured && (
        <>
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
        </>
      )}

      {/* Policies and Budget Drawer */}
      <Drawer
        title={`Policies & Budget: ${selectedAccount?.account_name || ""}`}
        open={policyDrawerOpen}
        onClose={() => {
          setPolicyDrawerOpen(false);
          featurePackForm.resetFields();
          modelPolicyForm.resetFields();
          allocationForm.resetFields();
          zitadelConfigForm.resetFields();
          zitadelGrantForm.resetFields();
          zitadelRoleForm.resetFields();
          zitadelBootstrapForm.resetFields();
          zitadelQuickOnboardForm.resetFields();
        }}
        width={680}
      >
        <Tabs defaultActiveKey="feature-pack">
          <TabPane tab="Feature Pack" key="feature-pack">
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="Account-level feature entitlements"
              description="Enable or disable account capabilities and store optional config for downstream policy resolution."
            />
            <Form form={featurePackForm} layout="vertical" onFinish={handleSaveFeaturePack}>
              <Form.Item name="features" label="Enabled Features">
                <Select
                  mode="tags"
                  placeholder="Add feature flags"
                  options={[
                    { label: "create_agents", value: "create_agents" },
                    { label: "create_connections_openapi", value: "create_connections_openapi" },
                    { label: "create_connections_mcp", value: "create_connections_mcp" },
                    { label: "create_connections_composio", value: "create_connections_composio" },
                    { label: "image_generation", value: "image_generation" },
                    { label: "model_access_controls", value: "model_access_controls" },
                  ]}
                />
              </Form.Item>
              <Form.Item
                name="config_json"
                label="Feature Config (JSON)"
                initialValue="{}"
                extra="Optional structured configuration for feature flags."
              >
                <Input.TextArea rows={8} spellCheck={false} />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={policyLoading}>
                Save Feature Pack
              </Button>
            </Form>
          </TabPane>

          <TabPane tab="Console Model Policy" key="console-model-policy">
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="Global console model allow-list for this account"
              description="Allow-list is the authoritative super-admin control. Account admins can further refine grants at org/team/user scope."
            />
            <Form form={modelPolicyForm} layout="vertical" onFinish={handleSaveModelPolicy}>
              <Form.Item name="allow_models" label="Allow Models">
                <Select
                  mode="multiple"
                  showSearch
                  optionFilterProp="label"
                  options={modelPolicyOptions}
                  placeholder={modelPolicyOptions.length > 0 ? "Select from catalog" : "No catalog models loaded"}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={policyLoading}>
                Save Model Policy
              </Button>
            </Form>
          </TabPane>

          <TabPane tab="Account Allocation" key="account-allocation">
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="Super-admin credit allocation controls"
              description="Set monthly credits, overflow limit, and credit factor for this account."
            />
            <Form form={allocationForm} layout="vertical" onFinish={handleSaveAllocation}>
              <Form.Item
                name="monthly_credits"
                label="Monthly Credits"
                rules={[{ required: true, message: "Monthly credits are required" }]}
              >
                <InputNumber style={{ width: "100%" }} min={0} step={100} />
              </Form.Item>
              <Form.Item
                name="overflow_limit"
                label="Overflow Limit"
                rules={[{ required: true, message: "Overflow limit is required" }]}
              >
                <InputNumber style={{ width: "100%" }} min={0} step={100} />
              </Form.Item>
              <Form.Item
                name="credit_factor"
                label="Credit Factor"
                rules={[{ required: true, message: "Credit factor is required" }]}
              >
                <InputNumber style={{ width: "100%" }} min={0.0001} step={0.1} />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={policyLoading}>
                Save Allocation
              </Button>
            </Form>
          </TabPane>

          <TabPane tab="Zitadel" key="zitadel">
            {zitadelStatus && (
              <Alert
                type="success"
                showIcon
                style={{ marginBottom: 12 }}
                message={`Current Auth Provider: ${zitadelStatus.auth_provider || "unknown"}`}
                description={`Context account: ${zitadelStatus.account_id || "none"} | roles: ${(zitadelStatus.roles || []).join(", ") || "none"}`}
              />
            )}
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="Simplified tenant onboarding (recommended)"
              description="Use one workflow to set claim defaults, sync roles, and grant account-admin access. Keep advanced forms for manual overrides only."
            />
            <Card size="small" style={{ marginBottom: 12 }} title="One-Click Tenant Onboarding">
              <Alert
                type="success"
                showIcon
                style={{ marginBottom: 12 }}
                message="Recommended workflow"
                description="This applies canonical claim keys and role mappings, creates missing project roles, and syncs grants for existing account admins."
              />
              <Form
                form={zitadelQuickOnboardForm}
                layout="vertical"
                initialValues={{
                  resolve_user_ids_from_zitadel: true,
                  dry_run: true,
                  save_as_global_defaults: true,
                  user_id_by_email_json: "{}",
                }}
                onFinish={handleQuickOnboardZitadel}
              >
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item
                      name="project_id"
                      label="Project ID"
                      rules={[{ required: true, message: "Project ID is required" }]}
                    >
                      <Input placeholder="zitadel project id" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="organization_id" label="Organization ID (Optional)">
                      <Input placeholder="zitadel org id for org-scoped grants" />
                    </Form.Item>
                  </Col>
                </Row>
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item
                      name="role_prefix"
                      label="Role Key Prefix (Optional)"
                      extra="If set, generated roles become e.g. zentience_account_admin."
                    >
                      <Input placeholder="optional prefix, e.g. zentience_" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="default_role_keys" label="Additional Role Keys (Optional)">
                      <Select mode="tags" placeholder="added to each synced account-admin grant" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item
                  name="user_id_by_email_json"
                  label="User ID by Email JSON (Optional)"
                  extra='Example: {"admin@zentience.co":"123456789"}'
                >
                  <Input.TextArea rows={4} spellCheck={false} />
                </Form.Item>
                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item name="resolve_user_ids_from_zitadel" valuePropName="checked">
                      <Switch checkedChildren="Resolve users by email" unCheckedChildren="Manual user IDs only" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="dry_run" valuePropName="checked">
                      <Switch checkedChildren="Dry-run" unCheckedChildren="Apply changes" />
                    </Form.Item>
                  </Col>
                </Row>
                <Form.Item name="save_as_global_defaults" valuePropName="checked">
                  <Switch checkedChildren="Save as global defaults" unCheckedChildren="Do not save defaults" />
                </Form.Item>
                <Space>
                  <Button type="primary" htmlType="submit" loading={zitadelOnboardLoading}>
                    Run One-Click Onboarding
                  </Button>
                  <Button onClick={() => zitadelQuickOnboardForm.resetFields()}>
                    Reset
                  </Button>
                </Space>
              </Form>
            </Card>

            <Collapse
              items={[
                {
                  key: "zitadel-advanced",
                  label: "Advanced Zitadel Controls",
                  children: (
                    <>
                      <Card size="small" style={{ marginBottom: 12 }} title="Account Zitadel Config (Metadata + Provisioning Defaults)">
                        <Form form={zitadelConfigForm} layout="vertical" onFinish={handleSaveZitadelConfig}>
                          <Alert
                            type="warning"
                            showIcon
                            style={{ marginBottom: 12 }}
                            message="Metadata scope note"
                            description="Issuer URL, Account ID Claim, and Product Domains Claim here are account metadata/provisioning defaults. Runtime token verification currently uses global server env Zitadel settings."
                          />
                          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
                            <Switch />
                          </Form.Item>
                          <Form.Item
                            name="issuer"
                            label="Issuer URL (Metadata)"
                            extra="Account-level issuer metadata for provisioning/audit context. Runtime verifier currently uses global env issuer."
                          >
                            <Input placeholder="https://your-zitadel.example.com" />
                          </Form.Item>
                          <Form.Item name="audience" label="Audience">
                            <Input placeholder="optional audience claim value" />
                          </Form.Item>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="project_id" label="Project ID">
                                <Input placeholder="zitadel project id" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="organization_id" label="Organization ID">
                                <Input placeholder="zitadel org id (optional)" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item
                                name="account_id_claim"
                                label="Account ID Claim (Metadata)"
                                extra="Account-level claim key metadata. Runtime claim extraction currently uses global env claim configuration."
                              >
                                <Input placeholder="alchemi:account_id" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item
                                name="product_domains_claim"
                                label="Product Domains Claim (Metadata)"
                                extra="Account-level domain-claim metadata. Runtime domain extraction currently uses global claim keys."
                              >
                                <Input placeholder="product_domains_allowed" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item
                            name="role_mappings_json"
                            label="Role Mappings JSON"
                            initialValue="{}"
                            extra='Example: {"console_org_admin":"console_org_admin","copilot_org_admin":"copilot_org_admin"}'
                          >
                            <Input.TextArea rows={6} spellCheck={false} />
                          </Form.Item>
                          <Button type="primary" htmlType="submit" loading={policyLoading}>
                            Save Zitadel Config
                          </Button>
                        </Form>
                      </Card>

                      <Card size="small" style={{ marginBottom: 12 }} title="Provision User Grant">
                        <Form form={zitadelGrantForm} layout="vertical" onFinish={handleProvisionZitadelGrant}>
                          <Form.Item name="user_id" label="User ID" rules={[{ required: true, message: "User ID is required" }]}>
                            <Input placeholder="zitadel user id" />
                          </Form.Item>
                          <Form.Item
                            name="role_keys"
                            label="Role Keys"
                            rules={[{ required: true, message: "At least one role key is required" }]}
                          >
                            <Select
                              mode="tags"
                              placeholder="e.g. account_admin, copilot_org_admin"
                            />
                          </Form.Item>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="project_id" label="Project ID Override">
                                <Input placeholder="optional project id override" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="organization_id" label="Organization ID Override">
                                <Input placeholder="optional org id override" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Button htmlType="submit" loading={policyLoading}>
                            Provision User Grant
                          </Button>
                        </Form>
                      </Card>

                      <Card size="small" style={{ marginBottom: 12 }} title="Provision Project Role">
                        <Form form={zitadelRoleForm} layout="vertical" onFinish={handleProvisionZitadelRole}>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="key" label="Role Key" rules={[{ required: true, message: "Role key is required" }]}>
                                <Input placeholder="copilot_team_admin" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item
                                name="display_name"
                                label="Display Name"
                                rules={[{ required: true, message: "Display name is required" }]}
                              >
                                <Input placeholder="Copilot Team Admin" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="group" label="Role Group">
                                <Input placeholder="copilot (optional)" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="project_id" label="Project ID Override">
                                <Input placeholder="optional project id override" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Button htmlType="submit" loading={policyLoading}>
                            Provision Project Role
                          </Button>
                        </Form>
                      </Card>

                      <Card size="small" title="Bootstrap / Sync Workflow">
                        <Alert
                          type="info"
                          showIcon
                          style={{ marginBottom: 12 }}
                          message="One-shot Zitadel lifecycle automation"
                          description="Runs role sync + account-admin grant sync, and can apply default role mappings/claim defaults. Use dry-run first."
                        />
                        <Form
                          form={zitadelBootstrapForm}
                          layout="vertical"
                          initialValues={{
                            apply_default_role_mappings: true,
                            create_project_roles: true,
                            grant_existing_account_admins: true,
                            resolve_user_ids_from_zitadel: false,
                            dry_run: true,
                          }}
                          onFinish={handleBootstrapZitadel}
                        >
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="project_id" label="Project ID Override">
                                <Input placeholder="optional project id override" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="organization_id" label="Organization ID Override">
                                <Input placeholder="optional organization id override" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="role_prefix" label="Role Key Prefix">
                                <Input placeholder="optional prefix, e.g. acme_" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="default_role_keys" label="Additional Role Keys">
                                <Select mode="tags" placeholder="optional role keys added to every admin grant" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item
                            name="user_id_by_email_json"
                            label="User ID by Email JSON"
                            initialValue="{}"
                            extra='Example: {"admin@acme.com":"123456789"}'
                          >
                            <Input.TextArea rows={4} spellCheck={false} />
                          </Form.Item>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="apply_default_role_mappings" valuePropName="checked">
                                <Switch checkedChildren="Apply mappings" unCheckedChildren="No mappings" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="create_project_roles" valuePropName="checked">
                                <Switch checkedChildren="Sync roles" unCheckedChildren="Skip roles" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="grant_existing_account_admins" valuePropName="checked">
                                <Switch checkedChildren="Sync admin grants" unCheckedChildren="Skip admin grants" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="resolve_user_ids_from_zitadel" valuePropName="checked">
                                <Switch checkedChildren="Resolve users by email" unCheckedChildren="No user lookup" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="dry_run" valuePropName="checked">
                            <Switch checkedChildren="Dry-run" unCheckedChildren="Apply changes" />
                          </Form.Item>
                          <Space>
                            <Button type="primary" htmlType="submit" loading={policyLoading}>
                              Run Bootstrap Workflow
                            </Button>
                            <Button onClick={() => zitadelBootstrapForm.resetFields()}>
                              Reset
                            </Button>
                          </Space>
                        </Form>
                      </Card>
                    </>
                  ),
                },
              ]}
            />
          </TabPane>
        </Tabs>
      </Drawer>
    </div>
  );
}
