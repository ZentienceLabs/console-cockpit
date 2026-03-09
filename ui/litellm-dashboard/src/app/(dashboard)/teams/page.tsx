"use client";

import TeamsView from "@/app/(dashboard)/teams/TeamsView";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import useTeams from "@/app/(dashboard)/hooks/useTeams";
import { useEffect, useState } from "react";
import { Organization } from "@/components/networking";
import { fetchOrganizations } from "@/components/organizations";

const TeamsPage = () => {
  const { accessToken, userId, userRole } = useAuthorized();
  const { teams, setTeams } = useTeams();
  const [organizations, setOrganizations] = useState<Organization[]>([]);

  useEffect(() => {
    if (!accessToken) {
      setOrganizations([]);
      return;
    }

    void fetchOrganizations(accessToken, setOrganizations);
  }, [accessToken]);

  return (
    <TeamsView
      teams={teams}
      accessToken={accessToken}
      setTeams={setTeams}
      userID={userId}
      userRole={userRole}
      organizations={organizations}
    />
  );
};

export default TeamsPage;
