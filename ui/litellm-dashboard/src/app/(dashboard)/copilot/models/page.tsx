"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Tabs, Modal, Form, Input, InputNumber, Select, Tag, Card, Checkbox, Button, Row, Col, Table, message } from "antd";
import { BlockOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import { modelApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

export default function CopilotModelsPage() {
  const { accessToken } = useAuthorized();

  // Model Catalog
  const [catalog, setCatalog] = useState<any[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogModal, setCatalogModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [catalogForm] = Form.useForm();

  // Eligibility
  const [eligibility, setEligibility] = useState<any>(null);
  const [eligibilityLoading, setEligibilityLoading] = useState(false);
  const [eligibleModels, setEligibleModels] = useState<string[]>([]);

  // Selection
  const [selection, setSelection] = useState<any>(null);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);

  // Effective
  const [effective, setEffective] = useState<any>(null);
  const [effectiveLoading, setEffectiveLoading] = useState(false);
  const [effectiveForm] = Form.useForm();

  const loadCatalog = useCallback(async () => {
    if (!accessToken) return;
    setCatalogLoading(true);
    try { const d = await modelApi.listCatalog(accessToken); setCatalog(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load catalog"); }
    finally { setCatalogLoading(false); }
  }, [accessToken]);

  const loadEligibility = useCallback(async () => {
    if (!accessToken) return;
    setEligibilityLoading(true);
    try {
      const d = await modelApi.getEligibility(accessToken);
      setEligibility(d);
      setEligibleModels((d as any)?.model_codes ?? []);
    } catch { setEligibility(null); }
    finally { setEligibilityLoading(false); }
  }, [accessToken]);

  const loadSelection = useCallback(async () => {
    if (!accessToken) return;
    setSelectionLoading(true);
    try {
      const d = await modelApi.getSelection(accessToken);
      setSelection(d);
      setSelectedModels((d as any)?.model_codes ?? []);
    } catch { setSelection(null); }
    finally { setSelectionLoading(false); }
  }, [accessToken]);

  useEffect(() => { loadCatalog(); loadEligibility(); loadSelection(); }, [loadCatalog, loadEligibility, loadSelection]);

  const handleRefresh = () => { loadCatalog(); loadEligibility(); loadSelection(); };

  const handleCatalogSave = async () => {
    if (!accessToken) return;
    try {
      const values = await catalogForm.validateFields();
      await modelApi.upsertCatalog(accessToken, values);
      message.success("Model saved");
      setCatalogModal({ open: false, editing: null }); catalogForm.resetFields(); loadCatalog();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  const handleEligibilitySave = async () => {
    if (!accessToken) return;
    try {
      await modelApi.setEligibility(accessToken, { model_codes: eligibleModels });
      message.success("Eligibility updated");
      loadEligibility();
    } catch (e: any) { message.error(e?.message ?? "Save failed"); }
  };

  const handleSelectionSave = async () => {
    if (!accessToken) return;
    try {
      await modelApi.setSelection(accessToken, { model_codes: selectedModels });
      message.success("Selection updated");
      loadSelection();
    } catch (e: any) { message.error(e?.message ?? "Save failed"); }
  };

  const handleEffectiveLoad = async () => {
    if (!accessToken) return;
    setEffectiveLoading(true);
    try {
      const params = effectiveForm.getFieldsValue();
      const filtered = Object.fromEntries(Object.entries(params).filter(([, v]) => v));
      const d = await modelApi.getEffective(accessToken, filtered as Record<string, string>);
      setEffective(d);
    } catch (e: any) { message.error(e?.message ?? "Failed to load effective models"); }
    finally { setEffectiveLoading(false); }
  };

  const enabledCatalog = catalog.filter(m => m.enabled !== false);

  return (
    <CopilotPageShell title="Model Governance" subtitle="Manage model catalog, eligibility, and selection policies." icon={<BlockOutlined />} onRefresh={handleRefresh}>
      <CopilotStatsRow stats={[
        { title: "Catalog Models", value: catalog.length, loading: catalogLoading },
        { title: "Eligible Models", value: eligibleModels.length, loading: eligibilityLoading },
        { title: "Selected (Default)", value: selectedModels.length, loading: selectionLoading },
      ]} />
      <Tabs defaultActiveKey="catalog" items={[
        { key: "catalog", label: `Model Catalog (${catalog.length})`, children: (
          <>
            <CopilotCrudTable dataSource={catalog} rowKey="code" loading={catalogLoading}
              searchFields={["code", "display_name", "provider", "capability"]}
              addLabel="Add Model"
              onAdd={() => { catalogForm.resetFields(); setCatalogModal({ open: true, editing: null }); }}
              onEdit={(r) => { catalogForm.setFieldsValue(r); setCatalogModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await modelApi.deleteCatalog(accessToken, r.code); loadCatalog(); } }}
              columns={[
                { title: "Code", dataIndex: "code", key: "code" },
                { title: "Display Name", dataIndex: "display_name", key: "display_name" },
                { title: "Provider", dataIndex: "provider", key: "provider", render: (v: string) => <Tag color="blue">{v ?? "—"}</Tag> },
                { title: "Capability", dataIndex: "capability", key: "capability", render: (v: string) => <Tag color="purple">{v ?? "chat"}</Tag> },
                { title: "Input $/1M", dataIndex: "cost_per_1m_input", key: "cost_in", render: (v: number) => v != null ? `$${v}` : "—" },
                { title: "Output $/1M", dataIndex: "cost_per_1m_output", key: "cost_out", render: (v: number) => v != null ? `$${v}` : "—" },
                { title: "Enabled", dataIndex: "enabled", key: "enabled", render: (v: boolean) => <Tag color={v !== false ? "green" : "default"}>{v !== false ? "Yes" : "No"}</Tag> },
              ]}
            />
            <Modal title={catalogModal.editing ? "Edit Model" : "Add Model"} open={catalogModal.open} onOk={handleCatalogSave} onCancel={() => setCatalogModal({ open: false, editing: null })} width={600}>
              <Form form={catalogForm} layout="vertical">
                <Form.Item name="code" label="Model Code" rules={[{ required: true }]}><Input disabled={!!catalogModal.editing} placeholder="e.g. gpt-4o, claude-sonnet" /></Form.Item>
                <Form.Item name="display_name" label="Display Name" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="provider" label="Provider"><Input placeholder="e.g. openai, anthropic" /></Form.Item>
                <Form.Item name="capability" label="Capability" initialValue="chat">
                  <Select options={[{ value: "chat", label: "Chat" }, { value: "completion", label: "Completion" }, { value: "embedding", label: "Embedding" }, { value: "image", label: "Image" }]} />
                </Form.Item>
                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="cost_per_1m_input" label="Input Cost per 1M tokens"><InputNumber min={0} step={0.01} style={{ width: "100%" }} /></Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="cost_per_1m_output" label="Output Cost per 1M tokens"><InputNumber min={0} step={0.01} style={{ width: "100%" }} /></Form.Item>
                  </Col>
                </Row>
                <Form.Item name="enabled" label="Enabled" valuePropName="checked" initialValue={true}><Checkbox>Enabled</Checkbox></Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "eligibility", label: "Eligibility", children: (
          <Card size="small">
            <p style={{ marginBottom: 16 }}>Select which models users in this account are eligible to use.</p>
            <Checkbox.Group value={eligibleModels} onChange={(v) => setEligibleModels(v as string[])} style={{ width: "100%" }}>
              <Row gutter={[8, 8]}>
                {enabledCatalog.map(m => (
                  <Col span={8} key={m.code}>
                    <Checkbox value={m.code}>{m.display_name || m.code}</Checkbox>
                  </Col>
                ))}
              </Row>
            </Checkbox.Group>
            {enabledCatalog.length === 0 && <p style={{ color: "#999" }}>No enabled models in catalog.</p>}
            <Button type="primary" style={{ marginTop: 16 }} onClick={handleEligibilitySave} loading={eligibilityLoading}>Save Eligibility</Button>
          </Card>
        )},
        { key: "selection", label: "Selection", children: (
          <Card size="small">
            <p style={{ marginBottom: 16 }}>Select the default models for this account. These are pre-selected for users.</p>
            <Checkbox.Group value={selectedModels} onChange={(v) => setSelectedModels(v as string[])} style={{ width: "100%" }}>
              <Row gutter={[8, 8]}>
                {eligibleModels.length > 0 ? eligibleModels.map(code => {
                  const m = catalog.find(c => c.code === code);
                  return (
                    <Col span={8} key={code}>
                      <Checkbox value={code}>{m?.display_name || code}</Checkbox>
                    </Col>
                  );
                }) : enabledCatalog.map(m => (
                  <Col span={8} key={m.code}>
                    <Checkbox value={m.code}>{m.display_name || m.code}</Checkbox>
                  </Col>
                ))}
              </Row>
            </Checkbox.Group>
            <Button type="primary" style={{ marginTop: 16 }} onClick={handleSelectionSave} loading={selectionLoading}>Save Selection</Button>
          </Card>
        )},
        { key: "effective", label: "Effective View", children: (
          <Card size="small">
            <Form form={effectiveForm} layout="inline" style={{ marginBottom: 16 }}>
              <Form.Item name="scope_type" label="Scope Type">
                <Select allowClear placeholder="Account" style={{ width: 160 }} options={[{ value: "ORG" }, { value: "TEAM" }, { value: "USER" }]} />
              </Form.Item>
              <Form.Item name="scope_id" label="Scope ID">
                <Input placeholder="Optional" style={{ width: 200 }} />
              </Form.Item>
              <Button type="primary" onClick={handleEffectiveLoad} loading={effectiveLoading}>Load</Button>
            </Form>
            {effective && (
              <Table
                dataSource={((effective as any)?.models ?? []).map((m: any, i: number) => ({ ...m, _key: m.code ?? i }))}
                rowKey="_key"
                size="small"
                pagination={false}
                columns={[
                  { title: "Code", dataIndex: "code", key: "code" },
                  { title: "Display Name", dataIndex: "display_name", key: "display_name" },
                  { title: "Source", dataIndex: "source", key: "source", render: (v: string) => v ? <Tag>{v}</Tag> : "—" },
                ]}
              />
            )}
            {!effective && <p style={{ color: "#999" }}>Click Load to view effective models for a scope.</p>}
          </Card>
        )},
      ]} />
    </CopilotPageShell>
  );
}
