"use client";

import React from "react";
import { Steps, Tag } from "antd";
import { CheckCircleOutlined, CloseCircleOutlined, MinusCircleOutlined } from "@ant-design/icons";

interface GuardConfig {
  guard_type: string;
  enabled: boolean;
  execution_order: number;
  action_on_fail?: string;
}

interface CopilotGuardrailPipelineProps {
  configs: GuardConfig[];
}

const CopilotGuardrailPipeline: React.FC<CopilotGuardrailPipelineProps> = ({ configs }) => {
  const sorted = [...configs].sort((a, b) => (a.execution_order ?? 0) - (b.execution_order ?? 0));

  const items = sorted.map((c) => ({
    title: (
      <span>
        {c.guard_type.toUpperCase()}{" "}
        {c.enabled ? (
          <Tag color="green" icon={<CheckCircleOutlined />}>Enabled</Tag>
        ) : (
          <Tag icon={<MinusCircleOutlined />}>Disabled</Tag>
        )}
      </span>
    ),
    description: c.enabled ? `Action: ${c.action_on_fail ?? "block"}` : "Skipped",
    status: c.enabled ? ("process" as const) : ("wait" as const),
    icon: c.enabled ? <CheckCircleOutlined /> : <CloseCircleOutlined />,
  }));

  if (items.length === 0) {
    return <div style={{ color: "#999", padding: 16 }}>No guardrails configured.</div>;
  }

  return (
    <div style={{ padding: "16px 0" }}>
      <Steps items={items} size="small" />
    </div>
  );
};

export default CopilotGuardrailPipeline;
