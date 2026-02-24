import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";
import {
  copilotGuardrailsConfigListCall,
  copilotGuardrailsConfigGetCall,
  copilotGuardrailsConfigUpsertCall,
  copilotGuardrailsConfigToggleCall,
  copilotGuardrailsPatternListCall,
  copilotGuardrailsPatternCreateCall,
  copilotGuardrailsPatternUpdateCall,
  copilotGuardrailsPatternDeleteCall,
  copilotGuardrailsAuditListCall,
} from "@/components/networking";

export const copilotGuardrailsConfigKeys = createQueryKeys("copilotGuardrailsConfig");
export const copilotGuardrailsPatternKeys = createQueryKeys("copilotGuardrailsPatterns");
export const copilotGuardrailsAuditKeys = createQueryKeys("copilotGuardrailsAudit");

// Guard Configs
export const useCopilotGuardrailsConfig = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotGuardrailsConfigKeys.list({ filters: params }),
    queryFn: () => copilotGuardrailsConfigListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotGuardrailsConfigByType = (guardType: string, params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotGuardrailsConfigKeys.detail(`${guardType}:${params?.account_id || "default"}`),
    queryFn: () => copilotGuardrailsConfigGetCall(accessToken!, guardType, params),
    enabled: Boolean(accessToken) && Boolean(guardType),
  });
};

export const useUpsertCopilotGuardrailsConfig = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ guardType, data, account_id }: { guardType: string; data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGuardrailsConfigUpsertCall(accessToken, guardType, data, { account_id });
    },
    onSuccess: (_data, { guardType }) => {
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsConfigKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsConfigKeys.detail(guardType) });
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsAuditKeys.all });
    },
  });
};

export const useToggleCopilotGuardrailsConfig = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ guardType, account_id }: { guardType: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGuardrailsConfigToggleCall(accessToken, guardType, { account_id });
    },
    onSuccess: (_data, { guardType }) => {
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsConfigKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsConfigKeys.detail(guardType) });
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsAuditKeys.all });
    },
  });
};

// Custom Patterns
export const useCopilotGuardrailsPatterns = (params?: { account_id?: string; guard_type?: string; enabled?: boolean; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotGuardrailsPatternKeys.list({ filters: params }),
    queryFn: () => copilotGuardrailsPatternListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotGuardrailsPattern = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Record<string, any> | { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      const payload = "data" in input ? input.data : input;
      const accountId = "data" in input ? input.account_id : undefined;
      return copilotGuardrailsPatternCreateCall(accessToken, payload, { account_id: accountId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsPatternKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsAuditKeys.all });
    },
  });
};

export const useUpdateCopilotGuardrailsPattern = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data, account_id }: { id: string; data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGuardrailsPatternUpdateCall(accessToken, id, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsPatternKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsAuditKeys.all });
    },
  });
};

export const useDeleteCopilotGuardrailsPattern = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, account_id }: { id: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGuardrailsPatternDeleteCall(accessToken, id, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsPatternKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotGuardrailsAuditKeys.all });
    },
  });
};

// Audit Log
export const useCopilotGuardrailsAudit = (params?: { account_id?: string; guard_type?: string; date_from?: string; date_to?: string; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotGuardrailsAuditKeys.list({ filters: params }),
    queryFn: () => copilotGuardrailsAuditListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};
