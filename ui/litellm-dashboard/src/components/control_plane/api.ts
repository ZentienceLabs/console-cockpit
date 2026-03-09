"use client";

export type ControlPlaneMembership = {
  account_id: string;
  account_name: string;
  account_alias?: string | null;
  domain?: string | null;
  account_status: string;
  membership_id: string;
  membership_role: string;
  membership_status: string;
  is_default: boolean;
  metadata?: Record<string, any>;
};

export type ControlPlaneContext = {
  user: {
    user_id: string;
    user_email: string;
    display_name?: string | null;
  } | null;
  memberships: ControlPlaneMembership[];
  platform_roles: string[];
  product_grants: string[];
  active_account_id: string | null;
  is_break_glass?: boolean;
};

export type ControlPlaneMember = {
  user_id: string;
  user_email: string;
  display_name?: string | null;
  zitadel_sub?: string | null;
  user_status?: string;
  membership_id: string;
  membership_role: string;
  membership_status: string;
  is_default: boolean;
  membership_metadata?: Record<string, any>;
};

export type IdentityBinding = {
  identity_binding_id?: string;
  provider?: string | null;
  zitadel_org_id?: string | null;
  issuer_url?: string | null;
  client_id?: string | null;
  default_redirect_url?: string | null;
  sso_enabled?: boolean;
  config?: Record<string, any>;
  metadata?: Record<string, any>;
};

export type IdentitySummary = {
  account: {
    account_id: string;
    account_name: string;
    account_alias?: string | null;
    domain?: string | null;
    status: string;
  };
  identity_binding: IdentityBinding | null;
};

export type DirectoryProviderConfig = {
  type?: string;
  name?: string;
  issuer?: string;
  client_id?: string;
  scopes?: string[];
  group_claim?: string | null;
  default_role?: string;
  sync_mode?: string;
  auto_register?: boolean;
  idp_id?: string;
};

export type DirectoryDomain = {
  orgId?: string;
  domainName?: string;
  isVerified?: boolean;
  isPrimary?: boolean;
};

export type DirectoryLoginPolicy = {
  login_mode?: string;
  allow_register?: boolean;
  allow_domain_discovery?: boolean;
  allow_username_password?: boolean;
  allow_external_idp?: boolean;
};

export type DirectoryScimConfig = {
  enabled?: boolean;
  machine_user_id?: string;
  token_id?: string;
  endpoint?: string;
  last_issued_at?: string;
  last_issued_by?: string;
  token_expires_at?: string;
  supports_groups?: boolean;
  group_sync_mode?: string;
};

export type DirectorySummary = {
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
  };
  directory: {
    org_id?: string | null;
    bootstrap_status?: string | null;
    provider_status?: string | null;
    managed_via_console: boolean;
    bootstrap_login?: string | null;
    sso_enabled: boolean;
    provider?: DirectoryProviderConfig | null;
    providers?: DirectoryProviderConfig[];
    scim?: DirectoryScimConfig | null;
    supports_group_scim: boolean;
    group_sync_strategy: string;
    management_url?: string | null;
    primary_domain?: string | null;
    additional_domains?: string[];
    domains?: DirectoryDomain[];
    login_policy?: DirectoryLoginPolicy | null;
  };
  capabilities: {
    can_bootstrap: boolean;
    can_manage_users: boolean;
    scim_support: string;
  };
};

export type ZitadelOrganization = {
  organization_id: string;
  name?: string;
  primary_domain?: string | null;
  state?: string;
};

export async function requestControlPlane<T>(
  sessionToken: string,
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${sessionToken}`,
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
      // Keep the fallback message when the response is not JSON.
    }
    throw new Error(detail);
  }

  return response.json();
}

export function formatMembershipRole(value?: string | null): string {
  const role = String(value || "").toLowerCase();
  switch (role) {
    case "owner":
      return "Owner";
    case "admin":
      return "Admin";
    case "account_admin":
      return "Account Admin";
    case "viewer":
      return "Viewer";
    case "member":
      return "Member";
    case "user":
      return "User";
    default:
      return value || "Unknown";
  }
}

export function isAdminMembership(role?: string | null): boolean {
  const normalized = String(role || "").toLowerCase();
  return normalized === "owner" || normalized === "admin" || normalized === "account_admin";
}
