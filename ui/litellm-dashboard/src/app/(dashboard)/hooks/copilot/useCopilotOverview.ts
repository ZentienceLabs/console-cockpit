import { useQuery } from "@tanstack/react-query";
import {
  copilotGroupListCall,
  copilotInviteListCall,
  copilotMembershipListCall,
  copilotTeamListCall,
} from "@/components/networking";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";

export const copilotMembershipKeys = createQueryKeys("copilotMemberships");
export const copilotGroupKeys = createQueryKeys("copilotGroups");
export const copilotTeamKeys = createQueryKeys("copilotTeams");
export const copilotInviteKeys = createQueryKeys("copilotInvites");

export const useCopilotMemberships = (params?: { account_id?: string; user_id?: string; source?: string; is_active?: boolean; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotMembershipKeys.list({ filters: params }),
    queryFn: () => copilotMembershipListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotGroups = (params?: { account_id?: string; source?: string; include_teams?: boolean; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotGroupKeys.list({ filters: params }),
    queryFn: () => copilotGroupListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotTeams = (params?: { account_id?: string; source?: string; group_id?: string; include_members?: boolean; include_group?: boolean; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotTeamKeys.list({ filters: params }),
    queryFn: () => copilotTeamListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotInvites = (params?: { account_id?: string; email?: string; status?: string; limit?: number; offset?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotInviteKeys.list({ filters: params }),
    queryFn: () => copilotInviteListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};
