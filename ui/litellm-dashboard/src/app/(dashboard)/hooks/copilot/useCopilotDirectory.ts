import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  copilotGroupListCall,
  copilotGroupCreateCall,
  copilotGroupDeleteCall,
  copilotGroupUpdateCall,
  copilotInviteAcceptCall,
  copilotInviteCreateCall,
  copilotInviteListCall,
  copilotInviteRejectCall,
  copilotTeamCreateCall,
  copilotTeamDeleteCall,
  copilotTeamListCall,
  copilotTeamUpdateCall,
  copilotUserCreateCall,
  copilotUserListCall,
  copilotUserReconcileIdentityCall,
  copilotUserMembershipUpdateCall,
  copilotUserUpdateCall,
} from "@/components/networking";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";

export const copilotUserKeys = createQueryKeys("copilotUsers");
export const copilotGroupDirectoryKeys = createQueryKeys("copilotDirectoryGroups");
export const copilotTeamDirectoryKeys = createQueryKeys("copilotDirectoryTeams");
export const copilotInviteDirectoryKeys = createQueryKeys("copilotDirectoryInvites");

export const useCopilotUsers = (params?: {
  account_id?: string;
  source?: string;
  is_active?: boolean;
  include_memberships?: boolean;
  limit?: number;
  offset?: number;
}) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotUserKeys.list({ filters: params }),
    queryFn: () => copilotUserListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useReconcileCopilotIdentityUsers = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ account_id }: { account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotUserReconcileIdentityCall(accessToken, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotGroupDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
    },
  });
};

export const useCopilotDirectoryGroups = (params?: {
  account_id?: string;
  source?: string;
  include_teams?: boolean;
  limit?: number;
  offset?: number;
}) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotGroupDirectoryKeys.list({ filters: params }),
    queryFn: () => copilotGroupListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotDirectoryTeams = (params?: {
  account_id?: string;
  source?: string;
  group_id?: string;
  include_members?: boolean;
  include_group?: boolean;
  limit?: number;
  offset?: number;
}) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotTeamDirectoryKeys.list({ filters: params }),
    queryFn: () => copilotTeamListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotDirectoryInvites = (params?: {
  account_id?: string;
  email?: string;
  status?: string;
  limit?: number;
  offset?: number;
}) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotInviteDirectoryKeys.list({ filters: params }),
    queryFn: () => copilotInviteListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotUser = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotUserCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotGroupDirectoryKeys.all });
    },
  });
};

export const useUpdateCopilotUser = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      data,
      account_id,
    }: {
      userId: string;
      data: Record<string, any>;
      account_id?: string;
    }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotUserUpdateCall(accessToken, userId, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
    },
  });
};

export const useUpdateCopilotMembership = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      data,
      account_id,
    }: {
      userId: string;
      data: Record<string, any>;
      account_id?: string;
    }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotUserMembershipUpdateCall(accessToken, userId, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
    },
  });
};

export const useCreateCopilotDirectoryGroup = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGroupCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGroupDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
    },
  });
};

export const useUpdateCopilotDirectoryGroup = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      groupId,
      data,
      account_id,
    }: {
      groupId: string;
      data: Record<string, any>;
      account_id?: string;
    }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGroupUpdateCall(accessToken, groupId, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGroupDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
    },
  });
};

export const useDeleteCopilotDirectoryGroup = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, account_id }: { groupId: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotGroupDeleteCall(accessToken, groupId, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotGroupDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
    },
  });
};

export const useCreateCopilotDirectoryTeam = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotTeamCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
    },
  });
};

export const useUpdateCopilotDirectoryTeam = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      teamId,
      data,
      account_id,
    }: {
      teamId: string;
      data: Record<string, any>;
      account_id?: string;
    }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotTeamUpdateCall(accessToken, teamId, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
    },
  });
};

export const useDeleteCopilotDirectoryTeam = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ teamId, account_id }: { teamId: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotTeamDeleteCall(accessToken, teamId, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
    },
  });
};

export const useCreateCopilotInvite = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotInviteCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotInviteDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
    },
  });
};

export const useAcceptCopilotInvite = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ inviteId, account_id }: { inviteId: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotInviteAcceptCall(accessToken, inviteId, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotInviteDirectoryKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotUserKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotTeamDirectoryKeys.all });
    },
  });
};

export const useRejectCopilotInvite = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ inviteId, account_id }: { inviteId: string; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotInviteRejectCall(accessToken, inviteId, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotInviteDirectoryKeys.all });
    },
  });
};
