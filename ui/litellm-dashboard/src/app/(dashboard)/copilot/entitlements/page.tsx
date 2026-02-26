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
  Card,
  Button,
  message,
} from "antd";
import { GoldOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import { entitlementApi, superAdminApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Safely parse a JSON string, returning undefined on failure. */
function tryParseJson(value: unknown): object | undefined {
  if (typeof value !== "string" || !value.trim()) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

/** Stringify a value for display in a TextArea. */
function jsonString(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function CopilotEntitlementsPage() {
  const { accessToken } = useAuthorized();

  // ---- Feature Catalog (super-admin) ----
  const [catalog, setCatalog] = useState<any[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogModal, setCatalogModal] = useState<{
    open: boolean;
    editing: any | null;
  }>({ open: false, editing: null });
  const [catalogForm] = Form.useForm();

  // ---- Subscription Plans (super-admin) ----
  const [plans, setPlans] = useState<any[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [planModal, setPlanModal] = useState<{
    open: boolean;
    editing: any | null;
  }>({ open: false, editing: null });
  const [planForm] = Form.useForm();

  // ---- Account Entitlements (read-only) ----
  const [entitlements, setEntitlements] = useState<any[]>([]);
  const [entitlementsLoading, setEntitlementsLoading] = useState(false);

  // ---- Account Setup (super-admin) ----
  const [setupAccountId, setSetupAccountId] = useState("");
  const [setupData, setSetupData] = useState<any>(null);
  const [setupLoading, setSetupLoading] = useState(false);
  const [setupSaving, setSetupSaving] = useState(false);
  const [setupForm] = Form.useForm();

  // -----------------------------------------------------------------------
  // Data loaders
  // -----------------------------------------------------------------------

  const loadCatalog = useCallback(async () => {
    if (!accessToken) return;
    setCatalogLoading(true);
    try {
      const d = await superAdminApi.listFeatureCatalog(accessToken);
      setCatalog(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load feature catalog");
    } finally {
      setCatalogLoading(false);
    }
  }, [accessToken]);

  const loadPlans = useCallback(async () => {
    if (!accessToken) return;
    setPlansLoading(true);
    try {
      const d = await superAdminApi.listSubscriptionPlans(accessToken);
      setPlans(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load subscription plans");
    } finally {
      setPlansLoading(false);
    }
  }, [accessToken]);

  const loadEntitlements = useCallback(async () => {
    if (!accessToken) return;
    setEntitlementsLoading(true);
    try {
      const d = await entitlementApi.getAccountEntitlements(accessToken);
      const arr = Array.isArray(d) ? d : (d as any)?.entitlements ?? [];
      setEntitlements(Array.isArray(arr) ? arr : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load entitlements");
    } finally {
      setEntitlementsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadCatalog();
    loadPlans();
    loadEntitlements();
  }, [loadCatalog, loadPlans, loadEntitlements]);

  const handleRefresh = () => {
    loadCatalog();
    loadPlans();
    loadEntitlements();
  };

  // -----------------------------------------------------------------------
  // Feature Catalog CRUD
  // -----------------------------------------------------------------------

  const openCatalogAdd = () => {
    catalogForm.resetFields();
    setCatalogModal({ open: true, editing: null });
  };

  const openCatalogEdit = (record: any) => {
    catalogForm.setFieldsValue({
      ...record,
      default_config: jsonString(record.default_config),
      plan_config: jsonString(record.plan_config),
    });
    setCatalogModal({ open: true, editing: record });
  };

  const handleCatalogSave = async () => {
    if (!accessToken) return;
    try {
      const values = await catalogForm.validateFields();
      const body = {
        ...values,
        default_config: tryParseJson(values.default_config) ?? values.default_config,
        plan_config: tryParseJson(values.plan_config) ?? values.plan_config,
      };

      if (catalogModal.editing) {
        const entryId =
          catalogModal.editing.id ?? catalogModal.editing.entry_id;
        await superAdminApi.updateFeatureCatalogItem(
          accessToken,
          entryId,
          body,
        );
      } else {
        await superAdminApi.createFeatureCatalogItem(accessToken, body);
      }
      message.success("Feature catalog item saved");
      setCatalogModal({ open: false, editing: null });
      catalogForm.resetFields();
      loadCatalog();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  const handleCatalogDelete = async (record: any) => {
    if (!accessToken) return;
    const entryId = record.id ?? record.entry_id;
    await superAdminApi.deleteFeatureCatalogItem(accessToken, entryId);
    loadCatalog();
  };

  // -----------------------------------------------------------------------
  // Subscription Plans CRUD
  // -----------------------------------------------------------------------

  const openPlanAdd = () => {
    planForm.resetFields();
    setPlanModal({ open: true, editing: null });
  };

  const openPlanEdit = (record: any) => {
    planForm.setFieldsValue({
      ...record,
      modules: jsonString(record.modules),
    });
    setPlanModal({ open: true, editing: record });
  };

  const handlePlanSave = async () => {
    if (!accessToken) return;
    try {
      const values = await planForm.validateFields();
      const body = {
        ...values,
        modules: tryParseJson(values.modules) ?? values.modules,
      };

      if (planModal.editing) {
        const planId =
          planModal.editing.plan_id ?? planModal.editing.id;
        await superAdminApi.updateSubscriptionPlan(accessToken, planId, body);
      } else {
        await superAdminApi.createSubscriptionPlan(accessToken, body);
      }
      message.success("Subscription plan saved");
      setPlanModal({ open: false, editing: null });
      planForm.resetFields();
      loadPlans();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    }
  };

  const handlePlanDelete = async (record: any) => {
    if (!accessToken) return;
    const planId = record.plan_id ?? record.id;
    await superAdminApi.deleteSubscriptionPlan(accessToken, planId);
    loadPlans();
  };

  // -----------------------------------------------------------------------
  // Account Setup
  // -----------------------------------------------------------------------

  const handleSetupLoad = async () => {
    if (!accessToken || !setupAccountId.trim()) {
      message.warning("Please enter an Account ID");
      return;
    }
    setSetupLoading(true);
    try {
      const d = await superAdminApi.getAccountSetup(
        accessToken,
        setupAccountId.trim(),
      );
      setSetupData(d);
      setupForm.setFieldsValue(d);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load account setup");
      setSetupData(null);
    } finally {
      setSetupLoading(false);
    }
  };

  const handleSetupSave = async () => {
    if (!accessToken || !setupAccountId.trim()) return;
    setSetupSaving(true);
    try {
      const values = await setupForm.validateFields();
      await superAdminApi.upsertAccountSetup(
        accessToken,
        setupAccountId.trim(),
        values,
      );
      message.success("Account setup saved");
      handleSetupLoad();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Save failed");
    } finally {
      setSetupSaving(false);
    }
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <CopilotPageShell
      title="Entitlements"
      subtitle="Manage feature catalog, subscription plans, account entitlements and setup. (Super Admin only)"
      icon={<GoldOutlined />}
      onRefresh={handleRefresh}
    >
      {/* Stats Row */}
      <CopilotStatsRow
        stats={[
          {
            title: "Catalog Features",
            value: catalog.length,
            loading: catalogLoading,
          },
          {
            title: "Subscription Plans",
            value: plans.length,
            loading: plansLoading,
          },
          {
            title: "Active Entitlements",
            value: entitlements.length,
            loading: entitlementsLoading,
          },
        ]}
      />

      {/* Tabs */}
      <Tabs
        defaultActiveKey="catalog"
        items={[
          // ------------------------------------------------------------------
          // TAB 1 — Feature Catalog
          // ------------------------------------------------------------------
          {
            key: "catalog",
            label: `Feature Catalog (${catalog.length})`,
            children: (
              <>
                <CopilotCrudTable
                  dataSource={catalog}
                  rowKey="id"
                  loading={catalogLoading}
                  searchFields={[
                    "product_code",
                    "feature_code",
                    "entity_code",
                    "name",
                    "category",
                  ]}
                  addLabel="Add Feature"
                  onAdd={openCatalogAdd}
                  onEdit={openCatalogEdit}
                  onDelete={handleCatalogDelete}
                  columns={[
                    {
                      title: "Product Code",
                      dataIndex: "product_code",
                      key: "product_code",
                    },
                    {
                      title: "Feature Code",
                      dataIndex: "feature_code",
                      key: "feature_code",
                    },
                    {
                      title: "Entity Code",
                      dataIndex: "entity_code",
                      key: "entity_code",
                    },
                    {
                      title: "Name",
                      dataIndex: "name",
                      key: "name",
                    },
                    {
                      title: "Category",
                      dataIndex: "category",
                      key: "category",
                      render: (v: string) =>
                        v ? <Tag color="blue">{v}</Tag> : "—",
                    },
                    {
                      title: "Active",
                      dataIndex: "is_active",
                      key: "is_active",
                      render: (v: boolean) => (
                        <Tag color={v !== false ? "green" : "default"}>
                          {v !== false ? "Yes" : "No"}
                        </Tag>
                      ),
                    },
                  ]}
                />

                {/* Feature Catalog Modal */}
                <Modal
                  title={
                    catalogModal.editing
                      ? "Edit Feature Catalog Item"
                      : "Add Feature Catalog Item"
                  }
                  open={catalogModal.open}
                  onOk={handleCatalogSave}
                  onCancel={() =>
                    setCatalogModal({ open: false, editing: null })
                  }
                  width={640}
                  destroyOnClose
                >
                  <Form form={catalogForm} layout="vertical">
                    <Form.Item
                      name="product_code"
                      label="Product Code"
                      rules={[{ required: true, message: "Product code is required" }]}
                    >
                      <Input placeholder="e.g. copilot" />
                    </Form.Item>
                    <Form.Item name="feature_code" label="Feature Code">
                      <Input placeholder="e.g. max_seats" />
                    </Form.Item>
                    <Form.Item name="entity_code" label="Entity Code">
                      <Input placeholder="e.g. account" />
                    </Form.Item>
                    <Form.Item
                      name="name"
                      label="Name"
                      rules={[{ required: true, message: "Name is required" }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                      <Input.TextArea rows={2} />
                    </Form.Item>
                    <Form.Item name="category" label="Category">
                      <Input placeholder="e.g. core, addon" />
                    </Form.Item>
                    <Form.Item name="default_config" label="Default Config (JSON)">
                      <Input.TextArea
                        rows={3}
                        placeholder='{"limit": 10}'
                      />
                    </Form.Item>
                    <Form.Item name="plan_config" label="Plan Config (JSON)">
                      <Input.TextArea
                        rows={3}
                        placeholder='{"basic": {"limit": 5}, "pro": {"limit": 50}}'
                      />
                    </Form.Item>
                    <Form.Item
                      name="is_active"
                      label="Active"
                      initialValue={true}
                    >
                      <Select
                        options={[
                          { value: true, label: "Yes" },
                          { value: false, label: "No" },
                        ]}
                      />
                    </Form.Item>
                  </Form>
                </Modal>
              </>
            ),
          },

          // ------------------------------------------------------------------
          // TAB 2 — Subscription Plans
          // ------------------------------------------------------------------
          {
            key: "plans",
            label: `Subscription Plans (${plans.length})`,
            children: (
              <>
                <CopilotCrudTable
                  dataSource={plans}
                  rowKey="plan_id"
                  loading={plansLoading}
                  searchFields={[
                    "plan_id",
                    "name",
                    "system_plan_id",
                    "plan_type",
                    "status",
                  ]}
                  addLabel="Add Plan"
                  onAdd={openPlanAdd}
                  onEdit={openPlanEdit}
                  onDelete={handlePlanDelete}
                  columns={[
                    {
                      title: "Plan ID",
                      dataIndex: "plan_id",
                      key: "plan_id",
                    },
                    {
                      title: "Name",
                      dataIndex: "name",
                      key: "name",
                    },
                    {
                      title: "System Plan ID",
                      dataIndex: "system_plan_id",
                      key: "system_plan_id",
                    },
                    {
                      title: "Base Price",
                      dataIndex: "base_price",
                      key: "base_price",
                      render: (v: number) =>
                        v != null ? `$${v}` : "—",
                    },
                    {
                      title: "Billing Period",
                      dataIndex: "billing_period",
                      key: "billing_period",
                      render: (v: string) =>
                        v ? <Tag color="blue">{v}</Tag> : "—",
                    },
                    {
                      title: "Plan Type",
                      dataIndex: "plan_type",
                      key: "plan_type",
                      render: (v: string) =>
                        v ? <Tag color="purple">{v}</Tag> : "—",
                    },
                    {
                      title: "Status",
                      dataIndex: "status",
                      key: "status",
                      render: (v: string) => {
                        const colorMap: Record<string, string> = {
                          active: "green",
                          inactive: "default",
                          draft: "orange",
                        };
                        return v ? (
                          <Tag color={colorMap[v] ?? "default"}>{v}</Tag>
                        ) : (
                          "—"
                        );
                      },
                    },
                    {
                      title: "Active",
                      dataIndex: "is_active",
                      key: "is_active",
                      render: (v: boolean) => (
                        <Tag color={v !== false ? "green" : "default"}>
                          {v !== false ? "Yes" : "No"}
                        </Tag>
                      ),
                    },
                  ]}
                />

                {/* Subscription Plans Modal */}
                <Modal
                  title={
                    planModal.editing
                      ? "Edit Subscription Plan"
                      : "Add Subscription Plan"
                  }
                  open={planModal.open}
                  onOk={handlePlanSave}
                  onCancel={() =>
                    setPlanModal({ open: false, editing: null })
                  }
                  width={640}
                  destroyOnClose
                >
                  <Form form={planForm} layout="vertical">
                    <Form.Item
                      name="name"
                      label="Name"
                      rules={[{ required: true, message: "Name is required" }]}
                    >
                      <Input placeholder="e.g. Professional Monthly" />
                    </Form.Item>
                    <Form.Item
                      name="system_plan_id"
                      label="System Plan ID"
                      rules={[{ required: true, message: "System Plan ID is required" }]}
                    >
                      <Input placeholder="e.g. plan_pro_monthly" />
                    </Form.Item>
                    <Form.Item name="base_price" label="Base Price">
                      <InputNumber
                        min={0}
                        step={0.01}
                        style={{ width: "100%" }}
                        placeholder="0.00"
                      />
                    </Form.Item>
                    <Form.Item name="description" label="Description">
                      <Input.TextArea rows={2} />
                    </Form.Item>
                    <Form.Item
                      name="billing_period"
                      label="Billing Period"
                      initialValue="monthly"
                    >
                      <Select
                        options={[
                          { value: "monthly", label: "Monthly" },
                          { value: "quarterly", label: "Quarterly" },
                          { value: "annual", label: "Annual" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="plan_type"
                      label="Plan Type"
                      initialValue="basic"
                    >
                      <Select
                        options={[
                          { value: "basic", label: "Basic" },
                          { value: "professional", label: "Professional" },
                          { value: "enterprise", label: "Enterprise" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item name="modules" label="Modules (JSON)">
                      <Input.TextArea
                        rows={3}
                        placeholder='["core", "analytics", "integrations"]'
                      />
                    </Form.Item>
                    <Form.Item name="trial_days" label="Trial Days">
                      <InputNumber
                        min={0}
                        step={1}
                        style={{ width: "100%" }}
                        placeholder="0"
                      />
                    </Form.Item>
                    <Form.Item
                      name="status"
                      label="Status"
                      initialValue="draft"
                    >
                      <Select
                        options={[
                          { value: "active", label: "Active" },
                          { value: "inactive", label: "Inactive" },
                          { value: "draft", label: "Draft" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="is_active"
                      label="Active"
                      initialValue={true}
                    >
                      <Select
                        options={[
                          { value: true, label: "Yes" },
                          { value: false, label: "No" },
                        ]}
                      />
                    </Form.Item>
                  </Form>
                </Modal>
              </>
            ),
          },

          // ------------------------------------------------------------------
          // TAB 3 — Account Entitlements (read-only)
          // ------------------------------------------------------------------
          {
            key: "entitlements",
            label: `Account Entitlements (${entitlements.length})`,
            children: (
              <CopilotCrudTable
                dataSource={entitlements}
                rowKey="feature_key"
                loading={entitlementsLoading}
                searchFields={["feature_key", "value", "source"]}
                showActions={false}
                columns={[
                  {
                    title: "Feature Key",
                    dataIndex: "feature_key",
                    key: "feature_key",
                  },
                  {
                    title: "Value",
                    dataIndex: "value",
                    key: "value",
                    render: (v: any) => {
                      if (typeof v === "boolean")
                        return (
                          <Tag color={v ? "green" : "default"}>
                            {String(v)}
                          </Tag>
                        );
                      return String(v ?? "—");
                    },
                  },
                  {
                    title: "Source",
                    dataIndex: "source",
                    key: "source",
                    render: (v: string) =>
                      v ? <Tag>{v}</Tag> : "—",
                  },
                  {
                    title: "Updated",
                    dataIndex: "updated_at",
                    key: "updated_at",
                  },
                ]}
              />
            ),
          },

          // ------------------------------------------------------------------
          // TAB 4 — Account Setup
          // ------------------------------------------------------------------
          {
            key: "setup",
            label: "Account Setup",
            children: (
              <Card size="small">
                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    marginBottom: 24,
                    alignItems: "center",
                  }}
                >
                  <Input
                    placeholder="Enter Account ID"
                    value={setupAccountId}
                    onChange={(e) => setSetupAccountId(e.target.value)}
                    style={{ maxWidth: 360 }}
                    onPressEnter={handleSetupLoad}
                  />
                  <Button
                    type="primary"
                    onClick={handleSetupLoad}
                    loading={setupLoading}
                  >
                    Load
                  </Button>
                </div>

                {setupData ? (
                  <Form form={setupForm} layout="vertical">
                    {Object.keys(setupData).map((key) => (
                      <Form.Item key={key} name={key} label={key}>
                        {typeof setupData[key] === "boolean" ? (
                          <Select
                            options={[
                              { value: true, label: "Yes" },
                              { value: false, label: "No" },
                            ]}
                          />
                        ) : typeof setupData[key] === "number" ? (
                          <InputNumber style={{ width: "100%" }} />
                        ) : typeof setupData[key] === "object" &&
                          setupData[key] !== null ? (
                          <Input.TextArea
                            rows={3}
                            defaultValue={JSON.stringify(
                              setupData[key],
                              null,
                              2,
                            )}
                          />
                        ) : (
                          <Input />
                        )}
                      </Form.Item>
                    ))}
                    <Button
                      type="primary"
                      onClick={handleSetupSave}
                      loading={setupSaving}
                    >
                      Save
                    </Button>
                  </Form>
                ) : (
                  <p style={{ color: "#999" }}>
                    Enter an Account ID and click Load to view and edit the
                    account setup configuration.
                  </p>
                )}
              </Card>
            ),
          },
        ]}
      />
    </CopilotPageShell>
  );
}
