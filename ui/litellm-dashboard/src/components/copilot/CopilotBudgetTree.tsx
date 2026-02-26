"use client";

import React, { useMemo } from "react";
import { Tree, Progress, Tag, Space, Typography } from "antd";
import type { DataNode } from "antd/es/tree";

const { Text } = Typography;

interface Allocation {
  scope_type: string;
  scope_id: string;
  scope_name?: string;
  allocated_credits: number;
  used_credits: number;
  overflow_cap?: number | null;
}

interface CopilotBudgetTreeProps {
  accountCredits: number;
  allocations: Allocation[];
  orgs?: Array<{ organization_id: string; name?: string }>;
  teams?: Array<{ team_id: string; name?: string; organization_id?: string }>;
}

function pct(used: number, allocated: number): number {
  if (allocated <= 0) return 0;
  return Math.min(Math.round((used / allocated) * 100), 100);
}

function progressStatus(p: number): "normal" | "active" | "exception" {
  if (p > 90) return "exception";
  if (p > 70) return "active";
  return "normal";
}

function renderNodeTitle(label: string, alloc: Allocation | null, type: string): React.ReactNode {
  if (!alloc) {
    return (
      <Space>
        <Tag>{type}</Tag>
        <Text>{label}</Text>
        <Text type="secondary">No allocation</Text>
      </Space>
    );
  }
  const p = pct(alloc.used_credits, alloc.allocated_credits);
  return (
    <Space style={{ width: "100%" }}>
      <Tag color="blue">{type}</Tag>
      <Text strong>{label}</Text>
      <Text>
        ${alloc.used_credits.toFixed(2)} / ${alloc.allocated_credits.toFixed(2)}
      </Text>
      {alloc.overflow_cap != null && alloc.overflow_cap > 0 && (
        <Text type="secondary">(overflow: ${alloc.overflow_cap.toFixed(2)})</Text>
      )}
      <Progress percent={p} size="small" status={progressStatus(p)} style={{ width: 120 }} />
    </Space>
  );
}

const CopilotBudgetTree: React.FC<CopilotBudgetTreeProps> = ({
  accountCredits,
  allocations,
  orgs = [],
  teams = [],
}) => {
  const allocMap = useMemo(() => {
    const m = new Map<string, Allocation>();
    allocations.forEach((a) => m.set(`${a.scope_type}:${a.scope_id}`, a));
    return m;
  }, [allocations]);

  const orgAllocations = allocations.filter((a) => a.scope_type === "ORG");
  const teamAllocations = allocations.filter((a) => a.scope_type === "TEAM");
  const userAllocations = allocations.filter((a) => a.scope_type === "USER");
  const totalAllocated = allocations.reduce((s, a) => s + a.allocated_credits, 0);

  const treeData: DataNode[] = [
    {
      key: "account",
      title: renderNodeTitle(
        "Account",
        { scope_type: "ACCOUNT", scope_id: "account", allocated_credits: accountCredits, used_credits: totalAllocated },
        "ACCOUNT",
      ),
      children: orgAllocations.map((oa) => {
        const orgName = oa.scope_name || orgs.find((o) => o.organization_id === oa.scope_id)?.name || oa.scope_id;
        const orgTeams = teamAllocations.filter((ta) => {
          const team = teams.find((t) => t.team_id === ta.scope_id);
          return team?.organization_id === oa.scope_id;
        });
        return {
          key: `org-${oa.scope_id}`,
          title: renderNodeTitle(orgName, oa, "ORG"),
          children: orgTeams.map((ta) => {
            const teamName = ta.scope_name || teams.find((t) => t.team_id === ta.scope_id)?.name || ta.scope_id;
            return {
              key: `team-${ta.scope_id}`,
              title: renderNodeTitle(teamName, ta, "TEAM"),
              children: userAllocations
                .filter(() => false) // Users don't have org/team linkage in allocations table; shown flat
                .map((ua) => ({
                  key: `user-${ua.scope_id}`,
                  title: renderNodeTitle(ua.scope_name || ua.scope_id, ua, "USER"),
                })),
            };
          }),
        };
      }),
    },
  ];

  // Add unattached teams and users at top level
  const attachedTeamIds = new Set(
    orgAllocations.flatMap((oa) =>
      teamAllocations
        .filter((ta) => {
          const team = teams.find((t) => t.team_id === ta.scope_id);
          return team?.organization_id === oa.scope_id;
        })
        .map((ta) => ta.scope_id),
    ),
  );

  const unattachedTeams = teamAllocations.filter((ta) => !attachedTeamIds.has(ta.scope_id));
  if (unattachedTeams.length > 0) {
    treeData[0].children = [
      ...(treeData[0].children || []),
      ...unattachedTeams.map((ta) => ({
        key: `team-${ta.scope_id}`,
        title: renderNodeTitle(ta.scope_name || ta.scope_id, ta, "TEAM"),
      })),
    ];
  }

  if (userAllocations.length > 0) {
    treeData[0].children = [
      ...(treeData[0].children || []),
      ...userAllocations.map((ua) => ({
        key: `user-${ua.scope_id}`,
        title: renderNodeTitle(ua.scope_name || ua.scope_id, ua, "USER"),
      })),
    ];
  }

  return (
    <Tree
      treeData={treeData}
      defaultExpandAll
      selectable={false}
      style={{ background: "transparent" }}
    />
  );
};

export default CopilotBudgetTree;
