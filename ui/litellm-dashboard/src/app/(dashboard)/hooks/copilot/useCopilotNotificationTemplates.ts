import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  copilotNotificationTemplateBulkDeleteCall,
  copilotNotificationTemplateCreateCall,
  copilotNotificationTemplateSummaryCall,
  copilotNotificationTemplateDeleteCall,
  copilotNotificationTemplateListCall,
  copilotNotificationTemplateUpdateCall,
} from "@/components/networking";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";

export const copilotNotificationTemplateKeys = createQueryKeys("copilotNotificationTemplates");

export const useCopilotNotificationTemplates = (params?: {
  account_id?: string;
  event_id?: string;
  type?: string;
  limit?: number;
  offset?: number;
}) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotNotificationTemplateKeys.list({ filters: params }),
    queryFn: () => copilotNotificationTemplateListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotNotificationTemplate = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotNotificationTemplateCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotNotificationTemplateKeys.all });
    },
  });
};

export const useCopilotNotificationTemplateSummary = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotNotificationTemplateKeys.all, "summary", params] as const,
    queryFn: () => copilotNotificationTemplateSummaryCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useUpdateCopilotNotificationTemplate = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data, account_id }: { id: string; data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotNotificationTemplateUpdateCall(accessToken, id, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotNotificationTemplateKeys.all });
    },
  });
};

export const useDeleteCopilotNotificationTemplate = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, account_id }: { id: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotNotificationTemplateDeleteCall(accessToken, id, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotNotificationTemplateKeys.all });
    },
  });
};

export const useBulkDeleteCopilotNotificationTemplates = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { template_ids: string[]; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotNotificationTemplateBulkDeleteCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotNotificationTemplateKeys.all });
    },
  });
};
