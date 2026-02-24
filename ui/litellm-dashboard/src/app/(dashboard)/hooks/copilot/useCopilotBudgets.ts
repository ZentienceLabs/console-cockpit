import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";
import {
  copilotBudgetListCall,
  copilotBudgetCreateCall,
  copilotBudgetGetCall,
  copilotBudgetUpdateCall,
  copilotBudgetDeleteCall,
  copilotBudgetSummaryCall,
  copilotBudgetAllocationOverviewCall,
  copilotBudgetAllocateCall,
  copilotBudgetDistributeEqualCall,
  copilotBudgetAlertsCall,
  copilotBudgetRecordUsageCall,
  copilotBudgetPlanListCall,
  copilotBudgetPlanCreateCall,
  copilotBudgetPlanUpdateCall,
  copilotBudgetPlanDeleteCall,
} from "@/components/networking";

export const copilotBudgetKeys = createQueryKeys("copilotBudgets");
export const copilotBudgetPlanKeys = createQueryKeys("copilotBudgetPlans");

export const useCopilotBudgets = (
  params?: {
    account_id?: string;
    scope_type?: string;
    scope_id?: string;
    active_only?: boolean;
    resolve_inherited?: boolean;
    limit?: number;
    offset?: number;
  },
) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotBudgetKeys.list({ filters: params }),
    queryFn: () => copilotBudgetListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotBudget = (id: string) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotBudgetKeys.detail(id),
    queryFn: () => copilotBudgetGetCall(accessToken!, id),
    enabled: Boolean(accessToken) && Boolean(id),
  });
};

export const useCopilotBudgetSummary = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotBudgetKeys.all, "summary", params] as const,
    queryFn: () => copilotBudgetSummaryCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotBudgetAllocationOverview = (params?: { account_id?: string; active_only?: boolean }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotBudgetKeys.all, "allocation-overview", params] as const,
    queryFn: () => copilotBudgetAllocationOverviewCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotBudgetAlerts = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotBudgetKeys.all, "alerts", params] as const,
    queryFn: () => copilotBudgetAlertsCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotBudget = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetKeys.all });
    },
  });
};

export const useUpdateCopilotBudget = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetUpdateCall(accessToken, id, data);
    },
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetKeys.all });
      queryClient.invalidateQueries({ queryKey: copilotBudgetKeys.detail(id) });
    },
  });
};

export const useDeleteCopilotBudget = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetDeleteCall(accessToken, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetKeys.all });
    },
  });
};

export const useRecordCopilotBudgetUsage = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { scope_type: string; scope_id: string; amount: number }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetRecordUsageCall(accessToken, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetKeys.all });
    },
  });
};

export const useAllocateCopilotBudget = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ parentBudgetId, data }: { parentBudgetId: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetAllocateCall(accessToken, parentBudgetId, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetKeys.all });
    },
  });
};

export const useDistributeEqualCopilotBudget = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ parentBudgetId, data }: { parentBudgetId: string; data?: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetDistributeEqualCall(accessToken, parentBudgetId, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetKeys.all });
    },
  });
};

// Budget Plans
export const useCopilotBudgetPlans = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: copilotBudgetPlanKeys.list({ filters: params }),
    queryFn: () => copilotBudgetPlanListCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCreateCopilotBudgetPlan = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ data, account_id }: { data: Record<string, any>; account_id?: string }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetPlanCreateCall(accessToken, data, { account_id });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetPlanKeys.all });
    },
  });
};

export const useUpdateCopilotBudgetPlan = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, any> }) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetPlanUpdateCall(accessToken, id, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetPlanKeys.all });
    },
  });
};

export const useDeleteCopilotBudgetPlan = () => {
  const { accessToken } = useAuthorized();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => {
      if (!accessToken) throw new Error("Access token is required");
      return copilotBudgetPlanDeleteCall(accessToken, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: copilotBudgetPlanKeys.all });
    },
  });
};
