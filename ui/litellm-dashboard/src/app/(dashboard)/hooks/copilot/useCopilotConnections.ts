import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";
import {
  copilotConnectionListCall,
  copilotConnectionCreateCall,
  copilotConnectionGetCall,
  copilotConnectionUpdateCall,
  copilotConnectionDeleteCall,
  copilotConnectionTestCall,
  copilotEnabledIntegrationsGetCall,
  copilotEnabledIntegrationsUpdateCall,
  copilotFeaturePolicyDeleteCall,
  copilotFeaturePolicyListCall,
  copilotFeaturePolicyResolveCall,
  copilotFeaturePolicyUpsertCall,
  copilotIntegrationCatalogCreateCall,
  copilotIntegrationCatalogDeleteCall,
  copilotIntegrationCatalogListCall,
  copilotIntegrationCatalogUpdateCall,
  copilotConnectionPermissionModeDeleteCall,
  copilotConnectionPermissionModeListCall,
  copilotConnectionPermissionModeResolveCall,
  copilotConnectionPermissionModeUpsertCall,
} from "@/components/networking";

export const copilotConnectionKeys = createQueryKeys("copilotConnections");
export const copilotIntegrationCatalogKeys = createQueryKeys("copilotIntegrationCatalog");
export const copilotEnabledIntegrationsKeys = createQueryKeys("copilotEnabledIntegrations");
export const copilotConnectionPermissionModeKeys = createQueryKeys("copilotConnectionPermissionModes");
export const copilotFeaturePolicyKeys = createQueryKeys("copilotFeaturePolicies");

export const useCopilotConnections = (params?: { account_id?: string; connection_type?: string; is_active?: boolean; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotConnectionKeys.list({ filters: params }),
    queryFn: () => copilotConnectionListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotConnection = (id: string) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotConnectionKeys.detail(id),
    queryFn: () => copilotConnectionGetCall(accessToken!, id),
    enabled: Boolean(accessToken) && Boolean(id),
  });
};

export const useCreateCopilotConnection = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Record<string, any> | { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      const payload = "data" in input ? input.data : input;
      const accountId = "data" in input ? input.account_id : undefined;
      return copilotConnectionCreateCall(accessToken, payload, { account_id: accountId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.all });
    },
  });
};

export const useUpdateCopilotConnection = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotConnectionUpdateCall(accessToken, id, data);
    },
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.detail(id) });
    },
  });
};

export const useDeleteCopilotConnection = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotConnectionDeleteCall(accessToken, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.all });
    },
  });
};

export const useTestCopilotConnection = () => {
  const { accessToken } = useAuthorized();
  return useMutation({
    mutationFn: (id: string) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotConnectionTestCall(accessToken, id);
    },
  });
};

export const useCopilotIntegrationCatalog = (params?: { include_inactive?: boolean }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotIntegrationCatalogKeys.list({ filters: params }),
    queryFn: () => copilotIntegrationCatalogListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotIntegrationCatalogEntry = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, any>) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotIntegrationCatalogCreateCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotIntegrationCatalogKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotEnabledIntegrationsKeys.all });
    },
  });
};

export const useUpdateCopilotIntegrationCatalogEntry = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotIntegrationCatalogUpdateCall(accessToken, id, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotIntegrationCatalogKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotEnabledIntegrationsKeys.all });
    },
  });
};

export const useDeleteCopilotIntegrationCatalogEntry = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, hardDelete }: { id: string; hardDelete?: boolean }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotIntegrationCatalogDeleteCall(accessToken, id, Boolean(hardDelete));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotIntegrationCatalogKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotEnabledIntegrationsKeys.all });
    },
  });
};

export const useCopilotEnabledIntegrations = (params?: { account_id?: string }, enabled: boolean = true) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotEnabledIntegrationsKeys.list({ filters: params }),
    queryFn: () => copilotEnabledIntegrationsGetCall(accessToken!, params),
    enabled: Boolean(accessToken) && enabled,
  });
};

export const useUpdateCopilotEnabledIntegrations = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { integration_ids: string[]; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotEnabledIntegrationsUpdateCall(accessToken, data);
    },
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: copilotEnabledIntegrationsKeys.all });
      if (vars?.account_id) {
        queryClient.invalidateQueries({ queryKey: copilotEnabledIntegrationsKeys.list({ filters: { account_id: vars.account_id } }) });
      }
    },
  });
};

export const useCopilotConnectionPermissionModes = (
  params?: { account_id?: string; scope_type?: string; scope_id?: string; connection_type?: string },
) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotConnectionPermissionModeKeys.list({ filters: params }),
    queryFn: () => copilotConnectionPermissionModeListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useUpsertCopilotConnectionPermissionMode = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, any>) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotConnectionPermissionModeUpsertCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotConnectionPermissionModeKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.all });
    },
  });
};

export const useDeleteCopilotConnectionPermissionMode = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { scope_type: string; scope_id: string; connection_type?: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotConnectionPermissionModeDeleteCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotConnectionPermissionModeKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.all });
    },
  });
};

export const useResolveCopilotConnectionPermissionMode = (
  params?: { account_id?: string; connection_type?: string; scope_type?: string; scope_id?: string },
  enabled: boolean = true,
) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotConnectionPermissionModeKeys.all, "resolve", params] as const,
    queryFn: () => copilotConnectionPermissionModeResolveCall(accessToken!, params),
    enabled: Boolean(accessToken) && enabled,
  });
};

export const useCopilotFeaturePolicies = (params?: { account_id?: string; scope_type?: string; scope_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotFeaturePolicyKeys.list({ filters: params }),
    queryFn: () => copilotFeaturePolicyListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useUpsertCopilotFeaturePolicy = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, any>) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotFeaturePolicyUpsertCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotFeaturePolicyKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.all });
    },
  });
};

export const useDeleteCopilotFeaturePolicy = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { scope_type: string; scope_id: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotFeaturePolicyDeleteCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotFeaturePolicyKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotConnectionKeys.all });
    },
  });
};

export const useResolveCopilotFeaturePolicy = (
  params?: { account_id?: string; scope_type?: string; scope_id?: string },
  enabled: boolean = true,
) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotFeaturePolicyKeys.all, "resolve", params] as const,
    queryFn: () => copilotFeaturePolicyResolveCall(accessToken!, params),
    enabled: Boolean(accessToken) && enabled,
  });
};
