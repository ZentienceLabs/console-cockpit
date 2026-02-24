import { useQuery } from "@tanstack/react-query";
import { accountListCall } from "@/components/networking";
import { createQueryKeys } from "../common/queryKeysFactory";
import useAuthorized from "../useAuthorized";

export const copilotAccountKeys = createQueryKeys("copilotAccounts");

export const useCopilotAccounts = () => {
  const { accessToken, isSuperAdmin } = useAuthorized();
  return useQuery({
    queryKey: copilotAccountKeys.lists(),
    queryFn: () => accountListCall(accessToken!),
    enabled: Boolean(accessToken) && Boolean(isSuperAdmin),
  });
};
