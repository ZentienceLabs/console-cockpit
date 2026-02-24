import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";
import {
  copilotModelCatalogCreateCall,
  copilotModelCatalogDeleteCall,
  copilotModelCatalogImportFromRouterCall,
  copilotModelCatalogListCall,
  copilotModelCatalogUpdateCall,
  copilotModelSelectionAccountsCall,
  copilotModelSelectionBulkUpdateCall,
  copilotModelSelectionGetCall,
  copilotModelSelectionUpdateCall,
} from "@/components/networking";

export const copilotModelSelectionKeys = createQueryKeys("copilotModelSelection");
export const copilotModelCatalogKeys = createQueryKeys("copilotModelCatalog");

export const useCopilotModelSelection = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotModelSelectionKeys.list({ filters: params }),
    queryFn: () => copilotModelSelectionGetCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useUpdateCopilotModelSelection = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { selected_models: string[]; account_id?: string; scope?: "super_admin" | "tenant_admin" }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotModelSelectionUpdateCall(accessToken, data);
    },
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: copilotModelSelectionKeys.all });
      if (vars?.account_id) {
        queryClient.invalidateQueries({ queryKey: copilotModelSelectionKeys.list({ filters: { account_id: vars.account_id } }) });
      }
    },
  });
};

export const useCopilotModelSelectionAccounts = (params?: { account_id?: string; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotModelSelectionKeys.all, "accounts", params] as const,
    queryFn: () => copilotModelSelectionAccountsCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useBulkUpdateCopilotModelSelection = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { account_ids: string[]; selected_models: string[]; scope?: "super_admin" | "tenant_admin" }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotModelSelectionBulkUpdateCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotModelSelectionKeys.all });
    },
  });
};

export const useCopilotModelCatalog = (params?: { include_inactive?: boolean }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotModelCatalogKeys.list({ filters: params }),
    queryFn: () => copilotModelCatalogListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotModelCatalogEntry = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Record<string, any>) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotModelCatalogCreateCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotModelCatalogKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotModelSelectionKeys.all });
    },
  });
};

export const useUpdateCopilotModelCatalogEntry = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotModelCatalogUpdateCall(accessToken, id, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotModelCatalogKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotModelSelectionKeys.all });
    },
  });
};

export const useDeleteCopilotModelCatalogEntry = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, hardDelete }: { id: string; hardDelete?: boolean }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotModelCatalogDeleteCall(accessToken, id, Boolean(hardDelete));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotModelCatalogKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotModelSelectionKeys.all });
    },
  });
};

export const useImportCopilotModelCatalogFromRouter = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data?: { model_names?: string[] }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotModelCatalogImportFromRouterCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotModelCatalogKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotModelSelectionKeys.all });
    },
  });
};
