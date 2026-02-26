"use client";

import React from "react";
import { Card, Statistic, Col, Row } from "antd";

interface StatItem {
  title: string;
  value: string | number;
  prefix?: React.ReactNode;
  suffix?: string;
  precision?: number;
  loading?: boolean;
}

interface CopilotStatsRowProps {
  stats: StatItem[];
  columns?: number;
}

const CopilotStatsRow: React.FC<CopilotStatsRowProps> = ({ stats, columns }) => {
  const span = Math.floor(24 / (columns ?? stats.length));
  return (
    <Row gutter={16} style={{ marginBottom: 24 }}>
      {stats.map((s, i) => (
        <Col span={span} key={i}>
          <Card>
            <Statistic
              title={s.title}
              value={s.value}
              prefix={s.prefix}
              suffix={s.suffix}
              precision={s.precision}
              loading={s.loading}
            />
          </Card>
        </Col>
      ))}
    </Row>
  );
};

export default CopilotStatsRow;
