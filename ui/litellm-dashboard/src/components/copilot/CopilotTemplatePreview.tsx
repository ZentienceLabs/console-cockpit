"use client";

import React, { useMemo } from "react";
import { Modal, Card, Typography } from "antd";

const { Text } = Typography;

interface CopilotTemplatePreviewProps {
  open: boolean;
  title?: string;
  subjectTemplate?: string;
  bodyTemplate?: string;
  variables?: Record<string, string>;
  onClose: () => void;
}

function interpolate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => vars[key] ?? `{{${key}}}`);
}

const CopilotTemplatePreview: React.FC<CopilotTemplatePreviewProps> = ({
  open,
  title = "Template Preview",
  subjectTemplate = "",
  bodyTemplate = "",
  variables = {},
  onClose,
}) => {
  const defaultVars: Record<string, string> = {
    user_name: "John Doe",
    user_email: "john@example.com",
    account_name: "Acme Corp",
    amount: "$500.00",
    threshold: "80%",
    ...variables,
  };

  const renderedSubject = useMemo(() => interpolate(subjectTemplate, defaultVars), [subjectTemplate, defaultVars]);
  const renderedBody = useMemo(() => interpolate(bodyTemplate, defaultVars), [bodyTemplate, defaultVars]);

  return (
    <Modal title={title} open={open} onCancel={onClose} footer={null} width={650}>
      {subjectTemplate && (
        <div style={{ marginBottom: 16 }}>
          <Text strong>Subject: </Text>
          <Text>{renderedSubject}</Text>
        </div>
      )}
      <Card size="small" style={{ background: "#fafafa" }}>
        <div
          style={{ minHeight: 100, fontFamily: "inherit", fontSize: 14, lineHeight: 1.6 }}
          dangerouslySetInnerHTML={{ __html: renderedBody }}
        />
      </Card>
      <div style={{ marginTop: 12 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          Variables used: {Object.keys(defaultVars).map((k) => `{{${k}}}`).join(", ")}
        </Text>
      </div>
    </Modal>
  );
};

export default CopilotTemplatePreview;
