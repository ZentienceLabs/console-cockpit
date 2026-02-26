"use client";

import React from "react";
import { Modal, Input } from "antd";

interface CopilotJsonModalProps {
  open: boolean;
  title?: string;
  data: unknown;
  onClose: () => void;
}

const CopilotJsonModal: React.FC<CopilotJsonModalProps> = ({ open, title = "Details", data, onClose }) => {
  const formatted = React.useMemo(() => {
    try {
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  }, [data]);

  return (
    <Modal title={title} open={open} onCancel={onClose} footer={null} width={700}>
      <Input.TextArea
        value={formatted}
        readOnly
        autoSize={{ minRows: 6, maxRows: 30 }}
        style={{ fontFamily: "monospace", fontSize: 12 }}
      />
    </Modal>
  );
};

export default CopilotJsonModal;
