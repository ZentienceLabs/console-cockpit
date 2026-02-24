import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  copilotGlobalOpsBulkDeleteTemplatesCall,
  copilotGlobalOpsBulkUpdateTicketsCall,
  copilotGlobalOpsSummaryCall,
} from "@/components/networking";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";

export const copilotGlobalOpsKeys = createQueryKeys("copilotGlobalOps");

export const useCopilotGlobalOpsSummary = (params?: { account_ids?: string[] }) => {
  const { accessToken } = useAuthorized();
  const accountKey = params?.account_ids?.length
    ? [...params.account_ids].sort().join(",")
    : "all";
  return useQuery({
    queryKey: [...copilotGlobalOpsKeys.all, "summary", accountKey] as const,
    queryFn: () => copilotGlobalOpsSummaryCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotGlobalBulkUpdateTickets = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      account_ids?: string[];
      current_status?: string;
      search_text?: string;
      status?: string;
      priority?: string;
      assigned_to?: string | null;
      limit?: number;
    }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGlobalOpsBulkUpdateTicketsCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGlobalOpsKeys.all });
    },
  });
};

export const useCopilotGlobalBulkDeleteTemplates = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      account_ids?: string[];
      event_ids?: string[];
      types?: string[];
      template_ids?: string[];
      limit?: number;
      dry_run?: boolean;
    }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGlobalOpsBulkDeleteTemplatesCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGlobalOpsKeys.all });
    },
  });
};
