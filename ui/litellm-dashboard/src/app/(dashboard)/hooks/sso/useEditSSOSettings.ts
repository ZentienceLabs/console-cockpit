import { useMutation, useQueryClient, UseMutationResult } from "@tanstack/react-query";
import { updateSSOSettings, updateAccountSSOConfig, deleteAccountSSOConfig } from "@/components/networking";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { createQueryKeys } from "../common/queryKeysFactory";

export interface EditSSOSettingsParams {
  google_client_id?: string | null;
  google_client_secret?: string | null;
  microsoft_client_id?: string | null;
  microsoft_client_secret?: string | null;
  microsoft_tenant?: string | null;
  generic_client_id?: string | null;
  generic_client_secret?: string | null;
  generic_authorization_endpoint?: string | null;
  generic_token_endpoint?: string | null;
  generic_userinfo_endpoint?: string | null;
  proxy_base_url?: string | null;
  user_email?: string | null;
  sso_provider?: string | null;
  role_mappings?: any;
  [key: string]: any;
}

export interface EditSSOSettingsResponse {
  [key: string]: any;
}

const ssoKeys = createQueryKeys("sso");

export const useEditSSOSettings = (): UseMutationResult<EditSSOSettingsResponse, Error, EditSSOSettingsParams> => {
  const { accessToken, accountId, isSuperAdmin } = useAuthorized();
  const queryClient = useQueryClient();
  const isAccountAdmin = Boolean(accountId) && !isSuperAdmin;

  return useMutation<EditSSOSettingsResponse, Error, EditSSOSettingsParams>({
    mutationFn: async (params: EditSSOSettingsParams) => {
      if (!accessToken) {
        throw new Error("Access token is required");
      }
      if (isAccountAdmin && accountId) {
        // Check if this is a "delete" operation (all fields null)
        const allNull = [
          "google_client_id", "google_client_secret",
          "microsoft_client_id", "microsoft_client_secret", "microsoft_tenant",
          "generic_client_id", "generic_client_secret",
          "generic_authorization_endpoint", "generic_token_endpoint", "generic_userinfo_endpoint",
          "proxy_base_url", "user_email", "sso_provider",
        ].every((key) => params[key] === null || params[key] === undefined);

        if (allNull) {
          return await deleteAccountSSOConfig(accessToken, accountId);
        }

        // Extract sso_provider, wrap the rest as sso_settings
        const { sso_provider, role_mappings, team_mappings, ...ssoFields } = params;
        return await updateAccountSSOConfig(accessToken, accountId, {
          sso_provider: sso_provider || null,
          enabled: true,
          sso_settings: { ...ssoFields, role_mappings, team_mappings },
        });
      }
      // Super admin: use global SSO endpoint
      return await updateSSOSettings(accessToken, params);
    },
    onSuccess: () => {
      // Invalidate SSO settings query to refetch
      if (isAccountAdmin && accountId) {
        queryClient.invalidateQueries({ queryKey: ssoKeys.detail(`account-${accountId}`) });
      } else {
        queryClient.invalidateQueries({ queryKey: ssoKeys.detail("settings") });
      }
    },
  });
};
