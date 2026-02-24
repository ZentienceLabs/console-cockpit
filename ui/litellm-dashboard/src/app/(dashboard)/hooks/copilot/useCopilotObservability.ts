import { useQuery } from "@tanstack/react-query";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";
import {
  copilotObservabilityAlertsCall,
  copilotObservabilityAuditCall,
  copilotObservabilitySummaryCall,
} from "@/components/networking";

export const copilotObservabilityKeys = createQueryKeys("copilotObservability");

export const useCopilotObservabilityAlerts = (params?: { account_id?: string; limit?: number }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotObservabilityKeys.all, "alerts", params] as const,
    queryFn: () => copilotObservabilityAlertsCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotObservabilityAudit = (params?: {
  account_id?: string;
  event_type?: string;
  severity?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotObservabilityKeys.all, "audit", params] as const,
    queryFn: () => copilotObservabilityAuditCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};

export const useCopilotObservabilitySummary = (params?: { account_id?: string }) => {
  const { accessToken } = useAuthorized();
  return useQuery({
    queryKey: [...copilotObservabilityKeys.all, "summary", params] as const,
    queryFn: () => copilotObservabilitySummaryCall(accessToken!, params),
    enabled: Boolean(accessToken),
  });
};
