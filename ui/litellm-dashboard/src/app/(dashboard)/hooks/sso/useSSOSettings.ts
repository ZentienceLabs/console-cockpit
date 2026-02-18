import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { getAccountSSOConfig, getSSOSettings } from "@/components/networking";
import { useQuery, UseQueryResult } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";

export interface SSOFieldSchema {
  description: string;
  properties: {
    [key: string]: {
      description: string;
      type: string;
    };
  };
}

export interface SSOSettingsValues {
  google_client_id: string | null;
  google_client_secret: string | null;
  microsoft_client_id: string | null;
  microsoft_client_secret: string | null;
  microsoft_tenant: string | null;
  generic_client_id: string | null;
  generic_client_secret: string | null;
  generic_authorization_endpoint: string | null;
  generic_token_endpoint: string | null;
  generic_userinfo_endpoint: string | null;
  proxy_base_url: string | null;
  user_email: string | null;
  ui_access_mode: string | null;
  role_mappings: RoleMappings | null;
  team_mappings: TeamMappings | null;
}

export interface RoleMappings {
  provider: string;
  group_claim: string;
  default_role: "internal_user" | "internal_user_viewer" | "proxy_admin" | "proxy_admin_viewer";
  roles: {
    [key: string]: string[];
  };
}

export interface TeamMappings {
  team_ids_jwt_field: string;
}

export interface SSOSettingsResponse {
  values: SSOSettingsValues;
  field_schema: SSOFieldSchema;
}

const ssoKeys = createQueryKeys("sso");

// Default field schema (used when per-account endpoint doesn't return one)
const defaultFieldSchema: SSOFieldSchema = {
  description: "Configuration for SSO authentication settings",
  properties: {
    google_client_id: { description: "Google OAuth Client ID", type: "string" },
    google_client_secret: { description: "Google OAuth Client Secret", type: "string" },
    microsoft_client_id: { description: "Microsoft OAuth Client ID", type: "string" },
    microsoft_client_secret: { description: "Microsoft OAuth Client Secret", type: "string" },
    microsoft_tenant: { description: "Microsoft Azure Tenant ID", type: "string" },
    generic_client_id: { description: "Generic OAuth Client ID", type: "string" },
    generic_client_secret: { description: "Generic OAuth Client Secret", type: "string" },
    generic_authorization_endpoint: { description: "Authorization endpoint URL", type: "string" },
    generic_token_endpoint: { description: "Token endpoint URL", type: "string" },
    generic_userinfo_endpoint: { description: "User info endpoint URL", type: "string" },
    proxy_base_url: { description: "Base URL of the proxy server", type: "string" },
    user_email: { description: "Email of the admin user", type: "string" },
    ui_access_mode: { description: "Access mode for the UI", type: "string" },
  },
};

export const useSSOSettings = (): UseQueryResult<SSOSettingsResponse> => {
  const { accessToken, userId, userRole, accountId, isSuperAdmin } = useAuthorized();
  const isAccountAdmin = Boolean(accountId) && !isSuperAdmin;

  return useQuery<SSOSettingsResponse>({
    queryKey: isAccountAdmin
      ? ssoKeys.detail(`account-${accountId}`)
      : ssoKeys.detail("settings"),
    queryFn: async () => {
      if (isAccountAdmin && accountId) {
        // Account admin: use per-account SSO endpoint
        const data = await getAccountSSOConfig(accessToken!, accountId);
        if (!data) {
          // No SSO config exists yet - return empty values
          return {
            values: {
              google_client_id: null,
              google_client_secret: null,
              microsoft_client_id: null,
              microsoft_client_secret: null,
              microsoft_tenant: null,
              generic_client_id: null,
              generic_client_secret: null,
              generic_authorization_endpoint: null,
              generic_token_endpoint: null,
              generic_userinfo_endpoint: null,
              proxy_base_url: null,
              user_email: null,
              ui_access_mode: null,
              role_mappings: null,
              team_mappings: null,
            } as SSOSettingsValues,
            field_schema: defaultFieldSchema,
          };
        }
        // Transform per-account response to SSOSettingsResponse format
        const ssoSettings = data.sso_settings || {};
        return {
          values: {
            google_client_id: ssoSettings.google_client_id ?? null,
            google_client_secret: ssoSettings.google_client_secret ?? null,
            microsoft_client_id: ssoSettings.microsoft_client_id ?? null,
            microsoft_client_secret: ssoSettings.microsoft_client_secret ?? null,
            microsoft_tenant: ssoSettings.microsoft_tenant ?? null,
            generic_client_id: ssoSettings.generic_client_id ?? null,
            generic_client_secret: ssoSettings.generic_client_secret ?? null,
            generic_authorization_endpoint: ssoSettings.generic_authorization_endpoint ?? null,
            generic_token_endpoint: ssoSettings.generic_token_endpoint ?? null,
            generic_userinfo_endpoint: ssoSettings.generic_userinfo_endpoint ?? null,
            proxy_base_url: ssoSettings.proxy_base_url ?? null,
            user_email: ssoSettings.user_email ?? null,
            ui_access_mode: ssoSettings.ui_access_mode ?? null,
            role_mappings: ssoSettings.role_mappings ?? null,
            team_mappings: ssoSettings.team_mappings ?? null,
          } as SSOSettingsValues,
          field_schema: defaultFieldSchema,
        };
      }
      // Super admin: use global SSO endpoint
      return await getSSOSettings(accessToken!);
    },
    enabled: Boolean(accessToken && userId && userRole),
  });
};
