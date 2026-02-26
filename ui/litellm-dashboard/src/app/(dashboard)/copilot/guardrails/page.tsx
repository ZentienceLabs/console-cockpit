"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Tabs,
  Modal,
  Form,
  Input,
  InputNumber,
  Select,
  Tag,
  Switch,
  Card,
  Row,
  Col,
  Button,
  Table,
  Badge,
  Descriptions,
  message,
} from "antd";
import { SafetyOutlined, SaveOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import CopilotGuardrailPipeline from "@/components/copilot/CopilotGuardrailPipeline";
import { guardrailApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

// ---------------------------------------------------------------------------
// Guard type constants
// ---------------------------------------------------------------------------
const GUARD_TYPES = ["pii", "toxic", "jailbreak"] as const;
type GuardType = (typeof GUARD_TYPES)[number];

const GUARD_TYPE_LABELS: Record<GuardType, string> = {
  pii: "PII Detection",
  toxic: "Toxic Detection",
  jailbreak: "Jailbreak Detection",
};

const GUARD_TYPE_COLORS: Record<GuardType, string> = {
  pii: "blue",
  toxic: "volcano",
  jailbreak: "purple",
};

// ---------------------------------------------------------------------------
// Defaults for new configs
// ---------------------------------------------------------------------------
function defaultConfig(guardType: GuardType, order: number): any {
  return {
    guard_type: guardType,
    enabled: false,
    execution_order: order,
    action_on_fail: "block",
    sensitivity: "medium",
  };
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------
export default function CopilotGuardrailsPage() {
  const { accessToken } = useAuthorized();

  // --- Configs state ---
  const [configs, setConfigs] = useState<Record<GuardType, any>>({
    pii: defaultConfig("pii", 1),
    toxic: defaultConfig("toxic", 2),
    jailbreak: defaultConfig("jailbreak", 3),
  });
  const [configsLoading, setConfigsLoading] = useState(false);
  const [savingGuard, setSavingGuard] = useState<GuardType | null>(null);

  // --- Patterns state ---
  const [patterns, setPatterns] = useState<any[]>([]);
  const [patternsLoading, setPatternsLoading] = useState(false);
  const [patternModal, setPatternModal] = useState<{
    open: boolean;
    editing: any | null;
  }>({ open: false, editing: null });
  const [patternForm] = Form.useForm();

  // --- Events state ---
  const [events, setEvents] = useState<any[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);

  // -----------------------------------------------------------------------
  // Data loaders
  // -----------------------------------------------------------------------
  const loadConfigs = useCallback(async () => {
    if (!accessToken) return;
    setConfigsLoading(true);
    try {
      const data = await guardrailApi.listConfigs(accessToken);
      const list: any[] = Array.isArray(data) ? data : [];
      const merged: Record<string, any> = {
        pii: defaultConfig("pii", 1),
        toxic: defaultConfig("toxic", 2),
        jailbreak: defaultConfig("jailbreak", 3),
      };
      list.forEach((c) => {
        if (c.guard_type && merged[c.guard_type]) {
          merged[c.guard_type] = { ...merged[c.guard_type], ...c };
        }
      });
      setConfigs(merged as Record<GuardType, any>);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load configs");
    } finally {
      setConfigsLoading(false);
    }
  }, [accessToken]);

  const loadPatterns = useCallback(async () => {
    if (!accessToken) return;
    setPatternsLoading(true);
    try {
      const d = await guardrailApi.listPatterns(accessToken);
      setPatterns(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load patterns");
    } finally {
      setPatternsLoading(false);
    }
  }, [accessToken]);

  const loadEvents = useCallback(async () => {
    if (!accessToken) return;
    setEventsLoading(true);
    try {
      const d = await guardrailApi.listEvents(accessToken);
      setEvents(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load events");
    } finally {
      setEventsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadConfigs();
    loadPatterns();
    loadEvents();
  }, [loadConfigs, loadPatterns, loadEvents]);

  const handleRefresh = () => {
    loadConfigs();
    loadPatterns();
    loadEvents();
  };

  // -----------------------------------------------------------------------
  // Config card helpers
  // -----------------------------------------------------------------------
  const updateLocalConfig = (guardType: GuardType, patch: Record<string, any>) => {
    setConfigs((prev) => ({
      ...prev,
      [guardType]: { ...prev[guardType], ...patch },
    }));
  };

  const handleSaveConfig = async (guardType: GuardType) => {
    if (!accessToken) return;
    setSavingGuard(guardType);
    try {
      await guardrailApi.upsertConfig(accessToken, configs[guardType], guardType);
      message.success(`${GUARD_TYPE_LABELS[guardType]} config saved`);
      loadConfigs();
    } catch (e: any) {
      message.error(e?.message ?? "Failed to save config");
    } finally {
      setSavingGuard(null);
    }
  };

  // -----------------------------------------------------------------------
  // Pattern CRUD
  // -----------------------------------------------------------------------
  const handlePatternSave = async () => {
    if (!accessToken) return;
    try {
      const values = await patternForm.validateFields();
      if (patternModal.editing) {
        await guardrailApi.updatePattern(
          accessToken,
          patternModal.editing.pattern_id,
          values,
        );
        message.success("Pattern updated");
      } else {
        await guardrailApi.createPattern(accessToken, values);
        message.success("Pattern created");
      }
      setPatternModal({ open: false, editing: null });
      patternForm.resetFields();
      loadPatterns();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  // -----------------------------------------------------------------------
  // Stats row data
  // -----------------------------------------------------------------------
  const statsData = [
    ...GUARD_TYPES.map((gt) => ({
      title: GUARD_TYPE_LABELS[gt],
      value: configs[gt]?.enabled ? "Enabled" : "Disabled",
      prefix: (
        <Badge
          status={configs[gt]?.enabled ? "success" : "default"}
          style={{ marginRight: 4 }}
        />
      ),
    })),
    {
      title: "Events",
      value: events.length,
    },
  ];

  // -----------------------------------------------------------------------
  // Pipeline configs array (for CopilotGuardrailPipeline)
  // -----------------------------------------------------------------------
  const pipelineConfigs = GUARD_TYPES.map((gt) => ({
    guard_type: gt,
    enabled: !!configs[gt]?.enabled,
    execution_order: configs[gt]?.execution_order ?? 0,
    action_on_fail: configs[gt]?.action_on_fail ?? "block",
  }));

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <CopilotPageShell
      title="Guardrails"
      subtitle="Configure guardrail policies, content filtering patterns, and review audit events."
      icon={<SafetyOutlined />}
      onRefresh={handleRefresh}
    >
      {/* Stats */}
      <CopilotStatsRow stats={statsData} columns={4} />

      {/* Tabs */}
      <Tabs
        defaultActiveKey="configs"
        items={[
          // -----------------------------------------------------------------
          // Guard Configs tab
          // -----------------------------------------------------------------
          {
            key: "configs",
            label: "Guard Configs",
            children: (
              <>
                <Row gutter={[16, 16]}>
                  {GUARD_TYPES.map((gt) => {
                    const cfg = configs[gt];
                    return (
                      <Col xs={24} md={8} key={gt}>
                        <Card
                          title={
                            <span>
                              <Tag color={GUARD_TYPE_COLORS[gt]}>
                                {gt.toUpperCase()}
                              </Tag>{" "}
                              {GUARD_TYPE_LABELS[gt]}
                            </span>
                          }
                          loading={configsLoading}
                          extra={
                            <Switch
                              checked={!!cfg?.enabled}
                              checkedChildren="ON"
                              unCheckedChildren="OFF"
                              onChange={(checked) =>
                                updateLocalConfig(gt, { enabled: checked })
                              }
                            />
                          }
                        >
                          <Form layout="vertical" size="small">
                            <Form.Item label="Execution Order">
                              <InputNumber
                                min={1}
                                max={100}
                                value={cfg?.execution_order ?? 1}
                                onChange={(v) =>
                                  updateLocalConfig(gt, { execution_order: v })
                                }
                                style={{ width: "100%" }}
                              />
                            </Form.Item>
                            <Form.Item label="Action on Fail">
                              <Select
                                value={cfg?.action_on_fail ?? "block"}
                                onChange={(v) =>
                                  updateLocalConfig(gt, { action_on_fail: v })
                                }
                                options={[
                                  { value: "block", label: "Block" },
                                  { value: "flag", label: "Flag" },
                                  { value: "log", label: "Log" },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item label="Sensitivity">
                              <Select
                                value={cfg?.sensitivity ?? "medium"}
                                onChange={(v) =>
                                  updateLocalConfig(gt, { sensitivity: v })
                                }
                                options={[
                                  { value: "low", label: "Low" },
                                  { value: "medium", label: "Medium" },
                                  { value: "high", label: "High" },
                                ]}
                              />
                            </Form.Item>
                            <Button
                              type="primary"
                              icon={<SaveOutlined />}
                              loading={savingGuard === gt}
                              onClick={() => handleSaveConfig(gt)}
                              block
                            >
                              Save
                            </Button>
                          </Form>
                        </Card>
                      </Col>
                    );
                  })}
                </Row>

                {/* Pipeline visualisation */}
                <CopilotGuardrailPipeline configs={pipelineConfigs} />
              </>
            ),
          },

          // -----------------------------------------------------------------
          // Custom Patterns tab
          // -----------------------------------------------------------------
          {
            key: "patterns",
            label: `Custom Patterns (${patterns.length})`,
            children: (
              <>
                <CopilotCrudTable
                  dataSource={patterns}
                  rowKey="pattern_id"
                  loading={patternsLoading}
                  searchFields={["name", "guard_type", "pattern"]}
                  addLabel="Add Pattern"
                  onAdd={() => {
                    patternForm.resetFields();
                    setPatternModal({ open: true, editing: null });
                  }}
                  onEdit={(r) => {
                    patternForm.setFieldsValue(r);
                    setPatternModal({ open: true, editing: r });
                  }}
                  onDelete={async (r) => {
                    if (accessToken)
                      await guardrailApi.deletePattern(
                        accessToken,
                        r.pattern_id,
                      );
                    loadPatterns();
                  }}
                  columns={[
                    {
                      title: "Pattern ID",
                      dataIndex: "pattern_id",
                      key: "pattern_id",
                      ellipsis: true,
                      width: 140,
                    },
                    {
                      title: "Name",
                      dataIndex: "name",
                      key: "name",
                    },
                    {
                      title: "Guard Type",
                      dataIndex: "guard_type",
                      key: "guard_type",
                      render: (v: string) => {
                        const color =
                          GUARD_TYPE_COLORS[v as GuardType] ?? "default";
                        return <Tag color={color}>{v}</Tag>;
                      },
                    },
                    {
                      title: "Pattern",
                      dataIndex: "pattern",
                      key: "pattern",
                      ellipsis: true,
                      render: (v: string) => (
                        <code
                          style={{
                            fontFamily: "monospace",
                            fontSize: 12,
                            background: "#f5f5f5",
                            padding: "2px 6px",
                            borderRadius: 4,
                          }}
                        >
                          {v}
                        </code>
                      ),
                    },
                    {
                      title: "Action",
                      dataIndex: "action",
                      key: "action",
                      render: (v: string) => {
                        const color =
                          v === "block"
                            ? "red"
                            : v === "flag"
                              ? "orange"
                              : "default";
                        return <Tag color={color}>{v ?? "block"}</Tag>;
                      },
                    },
                    {
                      title: "Enabled",
                      dataIndex: "enabled",
                      key: "enabled",
                      width: 90,
                      render: (v: boolean) => (
                        <Tag color={v !== false ? "green" : "default"}>
                          {v !== false ? "Yes" : "No"}
                        </Tag>
                      ),
                    },
                    {
                      title: "Created",
                      dataIndex: "created_at",
                      key: "created_at",
                      width: 180,
                    },
                  ]}
                />

                {/* Pattern form modal */}
                <Modal
                  title={
                    patternModal.editing ? "Edit Pattern" : "Add Pattern"
                  }
                  open={patternModal.open}
                  onOk={handlePatternSave}
                  onCancel={() =>
                    setPatternModal({ open: false, editing: null })
                  }
                  width={640}
                  destroyOnClose
                >
                  <Form form={patternForm} layout="vertical">
                    <Form.Item
                      name="name"
                      label="Name"
                      rules={[{ required: true, message: "Name is required" }]}
                    >
                      <Input placeholder="e.g. SSN Pattern" />
                    </Form.Item>
                    <Form.Item
                      name="guard_type"
                      label="Guard Type"
                      rules={[
                        { required: true, message: "Guard type is required" },
                      ]}
                    >
                      <Select
                        options={[
                          { value: "pii", label: "PII" },
                          { value: "toxic", label: "Toxic" },
                          { value: "jailbreak", label: "Jailbreak" },
                          { value: "custom", label: "Custom" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="pattern"
                      label="Pattern (regex)"
                      rules={[
                        { required: true, message: "Pattern is required" },
                      ]}
                    >
                      <Input.TextArea
                        rows={3}
                        placeholder="e.g. \b\d{3}-\d{2}-\d{4}\b"
                        style={{ fontFamily: "monospace" }}
                      />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                      <Input.TextArea rows={2} />
                    </Form.Item>
                    <Form.Item
                      name="action"
                      label="Action"
                      initialValue="block"
                    >
                      <Select
                        options={[
                          { value: "block", label: "Block" },
                          { value: "flag", label: "Flag" },
                          { value: "log", label: "Log" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="enabled"
                      label="Enabled"
                      valuePropName="checked"
                      initialValue={true}
                    >
                      <Switch checkedChildren="ON" unCheckedChildren="OFF" />
                    </Form.Item>
                  </Form>
                </Modal>
              </>
            ),
          },

          // -----------------------------------------------------------------
          // Events / Audit tab
          // -----------------------------------------------------------------
          {
            key: "events",
            label: `Events / Audit (${events.length})`,
            children: (
              <Table
                dataSource={events}
                rowKey={(r) => r.event_id ?? r.timestamp ?? Math.random()}
                loading={eventsLoading}
                pagination={{
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (t) => `${t} total`,
                }}
                size="middle"
                scroll={{ x: "max-content" }}
                expandable={{
                  expandedRowRender: (record) => (
                    <Descriptions
                      column={2}
                      size="small"
                      bordered
                      style={{ background: "#fafafa" }}
                    >
                      {Object.entries(record).map(([key, value]) => (
                        <Descriptions.Item label={key} key={key}>
                          {typeof value === "object"
                            ? JSON.stringify(value, null, 2)
                            : String(value ?? "-")}
                        </Descriptions.Item>
                      ))}
                    </Descriptions>
                  ),
                }}
                columns={[
                  {
                    title: "Timestamp",
                    dataIndex: "timestamp",
                    key: "timestamp",
                    width: 200,
                    sorter: (a: any, b: any) =>
                      String(a.timestamp ?? "").localeCompare(
                        String(b.timestamp ?? ""),
                      ),
                    defaultSortOrder: "descend",
                  },
                  {
                    title: "Event Type",
                    dataIndex: "event_type",
                    key: "event_type",
                    render: (v: string) => (
                      <Tag color="geekblue">{v ?? "-"}</Tag>
                    ),
                  },
                  {
                    title: "Guard Type",
                    dataIndex: "guard_type",
                    key: "guard_type",
                    render: (v: string) => {
                      const color =
                        GUARD_TYPE_COLORS[v as GuardType] ?? "default";
                      return <Tag color={color}>{v ?? "-"}</Tag>;
                    },
                  },
                  {
                    title: "Validation",
                    dataIndex: "validation_passed",
                    key: "validation_passed",
                    width: 110,
                    render: (v: boolean | null | undefined) => {
                      if (v === true)
                        return (
                          <Badge status="success" text="Pass" />
                        );
                      if (v === false)
                        return (
                          <Badge status="error" text="Fail" />
                        );
                      return <Badge status="default" text="-" />;
                    },
                  },
                  {
                    title: "Action Taken",
                    dataIndex: "action_taken",
                    key: "action_taken",
                    render: (v: string) => {
                      const color =
                        v === "block"
                          ? "red"
                          : v === "flag"
                            ? "orange"
                            : "default";
                      return <Tag color={color}>{v ?? "-"}</Tag>;
                    },
                  },
                  {
                    title: "User ID",
                    dataIndex: "user_id",
                    key: "user_id",
                    ellipsis: true,
                  },
                ]}
              />
            ),
          },
        ]}
      />
    </CopilotPageShell>
  );
}
