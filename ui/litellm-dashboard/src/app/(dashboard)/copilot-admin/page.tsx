"use client";

import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { isAdminRole } from "@/utils/roles";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

const centralizedSections = [
  {
    title: "Members",
    description: "Grant tenant access, assign product grants, and manage account membership.",
    href: "/users",
  },
  {
    title: "Directory & SSO",
    description: "Review the linked tenant directory and open Zitadel-managed identity settings.",
    href: "/settings/admin-settings",
  },
  {
    title: "Organizations",
    description: "Manage tenant organizations and their member structures.",
    href: "/organizations",
  },
  {
    title: "Teams",
    description: "Manage Copilot workspace and team access for the tenant.",
    href: "/teams",
  },
  {
    title: "Policies",
    description: "Manage Copilot access policy and enforcement settings.",
    href: "/policies",
  },
  {
    title: "Guardrails",
    description: "Configure the unified guardrails surface used across Console and Copilot.",
    href: "/guardrails",
  },
  {
    title: "MCP Servers",
    description: "Manage Copilot connections and MCP-backed tool integrations.",
    href: "/tools/mcp-servers",
  },
  {
    title: "Logs",
    description: "Review Copilot-related audit trails and operational logs in the unified cockpit.",
    href: "/logs",
  },
  {
    title: "Budgets",
    description: "Manage budget controls supporting the centralized Copilot administration model.",
    href: "/experimental/budgets",
  },
];

const pendingSections = [
  "Agent Definitions",
  "Marketplace",
  "Account Catalog",
  "Workflow",
  "Wallet",
  "Cost Tracking",
  "Requests",
];

export default function CopilotAdminPage() {
  const searchParams = useSearchParams();
  const { isLoading, isSuperAdmin, userRole, activeAccountId, userEmail } = useAuthorized();
  const legacyPath = searchParams.get("legacy_path");
  const canAccess = isSuperAdmin || isAdminRole(userRole);

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-8 text-sm text-slate-600">
        Loading Copilot admin...
      </div>
    );
  }

  if (!canAccess) {
    return (
      <div className="w-full p-8">
        <div className="mx-auto max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 p-6">
          <h1 className="text-2xl font-semibold text-slate-900">Copilot Admin</h1>
          <p className="mt-3 text-sm text-slate-700">
            This centralized Copilot administration surface is available to tenant account admins
            and super admins. Your current session does not have tenant admin privileges.
          </p>
          <div className="mt-4">
            <Link href="/virtual-keys" className="text-sm font-medium text-sky-700 hover:text-sky-900">
              Return to Virtual Keys
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div>
          <h1 className="text-3xl font-semibold text-slate-900">Copilot Admin</h1>
          <p className="mt-2 text-sm text-slate-600">
            Copilot administration has moved out of <code>alchemi-web /cockpit</code> and into the
            unified Console cockpit, as defined in Phase 2 of the migration.
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-sm font-medium text-slate-900">
            {isSuperAdmin ? "Super Admin Session" : "Tenant Admin Session"}
          </div>
          <div className="mt-2 text-sm text-slate-600">
            {isSuperAdmin
              ? "Use this page to verify the migrated Copilot admin surfaces and support tenant onboarding."
              : `Signed in as ${userEmail || "tenant admin"}${activeAccountId ? ` with active account ${activeAccountId}` : ""}. Use the sections below to administer the tenant.`}
          </div>
        </div>

        {legacyPath ? (
          <div className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
            <div className="font-medium">Legacy cockpit route redirected</div>
            <div className="mt-1">
              The old route <code>{legacyPath}</code> from <code>alchemi-web</code> has been
              sunset. Use one of the centralized Console sections below instead.
            </div>
          </div>
        ) : null}

        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          Phase 2 status: tenant-facing Copilot management is now centralized in Console. The
          sections below are the current migrated admin surfaces available for account admins.
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {centralizedSections.map((section) => (
            <div
              key={section.href}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="text-lg font-medium text-slate-900">{section.title}</div>
              <p className="mt-2 text-sm text-slate-600">{section.description}</p>
              <div className="mt-4">
                <Link
                  href={section.href}
                  className="text-sm font-medium text-sky-700 hover:text-sky-900"
                >
                  Open {section.title}
                </Link>
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-lg font-medium text-slate-900">Remaining Phase 2 Areas</div>
          <p className="mt-2 text-sm text-slate-600">
            These legacy Copilot cockpit areas are still being folded into the unified Console
            experience and should not send users back to <code>alchemi-web</code>.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            {pendingSections.map((section) => (
              <span
                key={section}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700"
              >
                {section}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
