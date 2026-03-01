import Link from "next/link";

const sections = [
  { title: "Global Ops", href: "/copilot/global-ops", description: "Cross-scope Copilot operations and triage summary." },
  { title: "Directory", href: "/copilot/directory", description: "Manage Copilot orgs, teams, and users." },
  { title: "Credits", href: "/copilot/credits", description: "Allocation plans, equal distribution, and overrides." },
  { title: "Agents", href: "/copilot/agents", description: "Create agents and manage usage scope." },
  { title: "Connections", href: "/copilot/connections", description: "OpenAPI, MCP, and Composio connections and grants." },
  { title: "Guardrails", href: "/copilot/guardrails", description: "Presets, assignments, and custom patterns." },
  { title: "Models", href: "/copilot/models", description: "Copilot model grants and effective access." },
  { title: "Feature Access", href: "/copilot/entitlements", description: "Enable/disable scoped product capabilities." },
  { title: "Marketplace", href: "/copilot/marketplace", description: "Publish and manage curated resources." },
  { title: "Observability", href: "/copilot/observability", description: "Audit, cost, and usage-oriented visibility." },
  { title: "Audit Logs", href: "/copilot/audit", description: "Domain-scoped immutable management event stream." },
];

export default function CopilotRootPage() {
  return (
    <div style={{ padding: 20 }}>
      <h1 style={{ marginTop: 0, marginBottom: 6 }}>Copilot Control</h1>
      <p style={{ marginTop: 0, marginBottom: 20, color: "#666" }}>
        Centralized management for Copilot directory, budgets, agents, tools, guardrails, access, and marketplace.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: 12,
        }}
      >
        {sections.map((section) => (
          <Link
            key={section.href}
            href={section.href}
            style={{
              display: "block",
              border: "1px solid #e5e7eb",
              borderRadius: 8,
              padding: 14,
              textDecoration: "none",
              color: "inherit",
              background: "#fff",
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 6 }}>{section.title}</div>
            <div style={{ color: "#666", fontSize: 13 }}>{section.description}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
