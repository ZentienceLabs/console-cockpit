import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  copilotSupportTicketBulkUpdateCall,
  copilotSupportTicketCreateCall,
  copilotSupportTicketSummaryCall,
  copilotSupportTicketDeleteCall,
  copilotSupportTicketListCall,
  copilotSupportTicketUpdateCall,
} from "@/components/networking";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";

export const copilotSupportTicketKeys = createQueryKeys("copilotSupportTickets");

export const useCopilotSupportTickets = (params?: {
  account_id?: string;
  status?: string;
  priority?: string;
  search_text?: string;
  include_user_profile?: boolean;
  include_assigned_to?: boolean;
  limit?: number;
  offset?: number;
}) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotSupportTicketKeys.list({ filters: params }),
    queryFn: () => copilotSupportTicketListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotSupportTicket = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotSupportTicketCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotSupportTicketKeys.all });
    },
  });
};

export const useCopilotSupportTicketSummary = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotSupportTicketKeys.all, "summary", params] as const,
    queryFn: () => copilotSupportTicketSummaryCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useUpdateCopilotSupportTicket = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data, account_id }: { id: string; data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotSupportTicketUpdateCall(accessToken, id, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotSupportTicketKeys.all });
    },
  });
};

export const useDeleteCopilotSupportTicket = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, account_id }: { id: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotSupportTicketDeleteCall(accessToken, id, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotSupportTicketKeys.all });
    },
  });
};

export const useBulkUpdateCopilotSupportTickets = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      ticket_ids: string[];
      status?: string;
      priority?: string;
      assigned_to?: string | null;
      account_id?: string;
    }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotSupportTicketBulkUpdateCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotSupportTicketKeys.all });
    },
  });
};
