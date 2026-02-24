import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";
import {
  copilotAgentListCall,
  copilotAgentCreateCall,
  copilotAgentGetCall,
  copilotAgentUpdateCall,
  copilotAgentDeleteCall,
  copilotAgentGroupListCall,
  copilotAgentGroupCreateCall,
  copilotAgentGroupUpdateCall,
  copilotAgentGroupDeleteCall,
  copilotAgentGroupMemberAddCall,
  copilotAgentGroupMemberRemoveCall,
  copilotMarketplaceListCall,
  copilotMarketplaceCreateCall,
  copilotMarketplaceGetCall,
  copilotMarketplaceUpdateCall,
  copilotMarketplaceDeleteCall,
  copilotMarketplaceFeaturedCall,
  copilotMarketplaceInstallCall,
} from "@/components/networking";

export const copilotAgentKeys = createQueryKeys("copilotAgents");
export const copilotAgentGroupKeys = createQueryKeys("copilotAgentGroups");
export const copilotMarketplaceKeys = createQueryKeys("copilotMarketplace");

// Agents
export const useCopilotAgents = (params?: { account_id?: string; status?: string; provider?: string; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotAgentKeys.list({ filters: params }),
    queryFn: () => copilotAgentListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotAgent = (agentId: string) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotAgentKeys.detail(agentId),
    queryFn: () => copilotAgentGetCall(accessToken!, agentId),
    enabled: Boolean(accessToken) && Boolean(agentId),
  });
};

export const useCreateCopilotAgent = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Record<string, any> | { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      const payload = "data" in input ? input.data : input;
      const accountId = "data" in input ? input.account_id : undefined;
      return copilotAgentCreateCall(accessToken, payload, { account_id: accountId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotAgentKeys.all });
    },
  });
};

export const useUpdateCopilotAgent = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotAgentUpdateCall(accessToken, agentId, data);
    },
    onSuccess: (_data, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: copilotAgentKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotAgentKeys.detail(agentId) });
    },
  });
};

export const useDeleteCopilotAgent = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotAgentDeleteCall(accessToken, agentId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotAgentKeys.all });
    },
  });
};

// Agent Groups
export const useCopilotAgentGroups = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotAgentGroupKeys.list({ filters: params }),
    queryFn: () => copilotAgentGroupListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotAgentGroup = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Record<string, any> | { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      const payload = "data" in input ? input.data : input;
      const accountId = "data" in input ? input.account_id : undefined;
      return copilotAgentGroupCreateCall(accessToken, payload, { account_id: accountId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotAgentGroupKeys.all });
    },
  });
};

export const useUpdateCopilotAgentGroup = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotAgentGroupUpdateCall(accessToken, id, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotAgentGroupKeys.all });
    },
  });
};

export const useDeleteCopilotAgentGroup = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotAgentGroupDeleteCall(accessToken, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotAgentGroupKeys.all });
    },
  });
};

export const useAddCopilotAgentGroupMember = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, data }: { groupId: string; data: { agent_id: string; display_order?: number } }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotAgentGroupMemberAddCall(accessToken, groupId, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotAgentGroupKeys.all });
    },
  });
};

export const useRemoveCopilotAgentGroupMember = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, agentId }: { groupId: string; agentId: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotAgentGroupMemberRemoveCall(accessToken, groupId, agentId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotAgentGroupKeys.all });
    },
  });
};

// Marketplace
export const useCopilotMarketplace = (params?: { account_id?: string; entity_type?: string; status?: string; is_featured?: boolean; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotMarketplaceKeys.list({ filters: params }),
    queryFn: () => copilotMarketplaceListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotMarketplaceItem = (id: string) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotMarketplaceKeys.detail(id),
    queryFn: () => copilotMarketplaceGetCall(accessToken!, id),
    enabled: Boolean(accessToken) && Boolean(id),
  });
};

export const useCopilotMarketplaceFeatured = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotMarketplaceKeys.all, "featured", params] as const,
    queryFn: () => copilotMarketplaceFeaturedCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotMarketplaceItem = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Record<string, any> | { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      const payload = "data" in input ? input.data : input;
      const accountId = "data" in input ? input.account_id : undefined;
      return copilotMarketplaceCreateCall(accessToken, payload, { account_id: accountId });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotMarketplaceKeys.all });
    },
  });
};

export const useUpdateCopilotMarketplaceItem = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotMarketplaceUpdateCall(accessToken, id, data);
    },
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: copilotMarketplaceKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotMarketplaceKeys.detail(id) });
    },
  });
};

export const useDeleteCopilotMarketplaceItem = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotMarketplaceDeleteCall(accessToken, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotMarketplaceKeys.all });
    },
  });
};

export const useInstallCopilotMarketplaceItem = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: string | { id: string; data?: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      if (typeof input === "string") {
        return copilotMarketplaceInstallCall(accessToken, input);
      }
      return copilotMarketplaceInstallCall(accessToken, input.id, input.data, { account_id: input.account_id });
    },
    onSuccess: (_data, input) => {
      const id = typeof input === "string" ? input : input.id;
      queryClient.invalidateQueries({ queryKey: copilotMarketplaceKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: copilotMarketplaceKeys.all });
    },
  });
};
