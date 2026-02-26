import { Member, Team } from "@/components/networking";

// Define admin roles and permissions
export const old_admin_roles = ["Admin", "Admin Viewer"];
export const v2_admin_role_names = ["proxy_admin", "proxy_admin_viewer", "org_admin"];
export const all_admin_roles = [
  ...old_admin_roles,
  ...v2_admin_role_names,
  "App Owner",       // app_owner JWT role
  "Account Admin",   // account_admin JWT role
];

// Copilot management role groups
export const copilot_admin_roles = [
  "Admin",           // app_admin maps here
  "App Owner",       // app_owner maps here
  "Account Admin",   // account_admin / tenant_admin maps here
  "Org Admin",       // org_admin maps here
  "proxy_admin",
];
export const super_admin_only_roles = ["proxy_admin"];

export const internalUserRoles = ["Internal User", "Internal Viewer"];
export const rolesAllowedToSeeUsage = ["Admin", "Admin Viewer", "Internal User", "Internal Viewer", "App Owner", "Account Admin"];
export const rolesWithWriteAccess = ["Internal User", "Admin", "proxy_admin", "App Owner", "Account Admin"];

// Helper function to check if a role is in all_admin_roles
export const isAdminRole = (role: string): boolean => {
  return all_admin_roles.includes(role);
};

export const isProxyAdminRole = (role: string): boolean => {
  return role === "proxy_admin" || role === "Admin";
};

export const isUserTeamAdminForAnyTeam = (teams: Team[] | null, userID: string): boolean => {
  if (teams == null) {
    return false;
  }
  return teams.some((team) => isUserTeamAdminForSingleTeam(team.members_with_roles, userID));
};

export const isUserTeamAdminForSingleTeam = (teamMemberWithRoles: Member[] | null, userID: string): boolean => {
  if (teamMemberWithRoles == null) {
    return false;
  }
  return teamMemberWithRoles.some((member) => member.user_id === userID && member.role === "admin");
};
