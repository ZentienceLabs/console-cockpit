"use client";

import React from "react";
import { Typography, Space, Button } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

const { Title, Text } = Typography;

interface CopilotPageShellProps {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  onRefresh?: () => void;
  children: React.ReactNode;
}

const CopilotPageShell: React.FC<CopilotPageShellProps> = ({
  title,
  subtitle,
  icon,
  actions,
  onRefresh,
  children,
}) => {
  return (
    <div style={{ padding: 24, flex: 1, minWidth: 0, overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            {icon && <span style={{ marginRight: 8 }}>{icon}</span>}
            {title}
          </Title>
          {subtitle && (
            <Text type="secondary" style={{ marginTop: 4, display: "block" }}>
              {subtitle}
            </Text>
          )}
        </div>
        <Space>
          {onRefresh && (
            <Button icon={<ReloadOutlined />} onClick={onRefresh}>
              Refresh
            </Button>
          )}
          {actions}
        </Space>
      </div>
      {children}
    </div>
  );
};

export default CopilotPageShell;
