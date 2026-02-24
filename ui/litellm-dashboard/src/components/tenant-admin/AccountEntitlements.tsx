"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Card,
  Form,
  InputNumber,
  Switch,
  Button,
  Select,
  Typography,
  message,
  Divider,
  Row,
  Col,
  Spin,
  Empty,
} from "antd";
import { SaveOutlined } from "@ant-design/icons";

const { Text, Title } = Typography;

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

interface Account {
  account_id: string;
  account_name: string;
  status: string;
}

interface Entitlements {
  max_models?: number;
  max_keys?: number;
  max_teams?: number;
  max_budget?: number;
  features?: Record<string, boolean>;
}

const defaultFeatureFlags = [
  { key: "copilot_budgets", label: "Credit Budgets" },
  { key: "copilot_agents", label: "Agents & Marketplace" },
  { key: "copilot_connections", label: "Connections & Tools" },
  { key: "copilot_guardrails", label: "Enhanced Guardrails" },
  { key: "playground", label: "LLM Playground" },
  { key: "model_management", label: "Model Management" },
  { key: "sso_config", label: "SSO Configuration" },
];

export default function AccountEntitlements() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>();
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [form] = Form.useForm();
  const accessToken = getCookie("token") || "";

  const fetchAccounts = useCallback(async () => {
    setAccountsLoading(true);
    try {
      const response = await fetch("/account/list", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        setAccounts(data.accounts || []);
      }
    } catch {
      message.error("Error loading accounts");
    } finally {
      setAccountsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const fetchEntitlements = useCallback(
    async (accountId: string) => {
      setLoading(true);
      try {
        const response = await fetch(`/copilot/entitlements/${accountId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (response.ok) {
          const data = await response.json();
          const ent = data.entitlements || {};
          setEntitlements(ent);
          form.setFieldsValue({
            max_models: ent.max_models,
            max_keys: ent.max_keys,
            max_teams: ent.max_teams,
            max_budget: ent.max_budget,
            ...Object.fromEntries(
              defaultFeatureFlags.map((f) => [
                `feature_${f.key}`,
                ent.features?.[f.key] ?? true,
              ])
            ),
          });
        } else {
          message.error("Failed to load entitlements");
        }
      } catch {
        message.error("Error loading entitlements");
      } finally {
        setLoading(false);
      }
    },
    [accessToken, form]
  );

  const handleAccountSelect = (accountId: string) => {
    setSelectedAccountId(accountId);
    fetchEntitlements(accountId);
  };

  const handleSave = async (values: any) => {
    if (!selectedAccountId) return;
    setSaving(true);

    const features: Record<string, boolean> = {};
    for (const flag of defaultFeatureFlags) {
      features[flag.key] = values[`feature_${flag.key}`] ?? true;
    }

    const payload: any = { features };
    if (values.max_models !== undefined && values.max_models !== null) {
      payload.max_models = values.max_models;
    }
    if (values.max_keys !== undefined && values.max_keys !== null) {
      payload.max_keys = values.max_keys;
    }
    if (values.max_teams !== undefined && values.max_teams !== null) {
      payload.max_teams = values.max_teams;
    }
    if (values.max_budget !== undefined && values.max_budget !== null) {
      payload.max_budget = values.max_budget;
    }

    try {
      const response = await fetch(
        `/copilot/entitlements/${selectedAccountId}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify(payload),
        }
      );
      if (response.ok) {
        message.success("Entitlements saved successfully");
        fetchEntitlements(selectedAccountId);
      } else {
        const err = await response.json();
        message.error(err.detail || "Failed to save entitlements");
      }
    } catch {
      message.error("Error saving entitlements");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <Card style={{ marginBottom: 24 }}>
        <Text strong style={{ display: "block", marginBottom: 12 }}>
          Select Account
        </Text>
        <Select
          placeholder="Choose an account to manage entitlements"
          style={{ width: 400 }}
          loading={accountsLoading}
          showSearch
          optionFilterProp="label"
          onChange={handleAccountSelect}
          value={selectedAccountId}
          options={accounts.map((a) => ({
            label: `${a.account_name} (${a.status})`,
            value: a.account_id,
          }))}
        />
      </Card>

      {!selectedAccountId && (
        <Empty description="Select an account above to view and edit entitlements" />
      )}

      {selectedAccountId && loading && (
        <Card>
          <div style={{ textAlign: "center", padding: 48 }}>
            <Spin size="large" />
          </div>
        </Card>
      )}

      {selectedAccountId && !loading && entitlements !== null && (
        <Card>
          <Form form={form} layout="vertical" onFinish={handleSave}>
            <Title level={5}>Resource Limits</Title>
            <Row gutter={24}>
              <Col span={6}>
                <Form.Item
                  name="max_models"
                  label="Max Models"
                  extra="Leave empty for unlimited"
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={0}
                    placeholder="Unlimited"
                  />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item
                  name="max_keys"
                  label="Max API Keys"
                  extra="Leave empty for unlimited"
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={0}
                    placeholder="Unlimited"
                  />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item
                  name="max_teams"
                  label="Max Teams"
                  extra="Leave empty for unlimited"
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={0}
                    placeholder="Unlimited"
                  />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item
                  name="max_budget"
                  label="Max Budget (USD)"
                  extra="Leave empty for unlimited"
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    min={0}
                    step={100}
                    placeholder="Unlimited"
                  />
                </Form.Item>
              </Col>
            </Row>

            <Divider />

            <Title level={5}>Feature Access</Title>
            <Row gutter={[24, 16]}>
              {defaultFeatureFlags.map((flag) => (
                <Col span={8} key={flag.key}>
                  <Form.Item
                    name={`feature_${flag.key}`}
                    label={flag.label}
                    valuePropName="checked"
                  >
                    <Switch />
                  </Form.Item>
                </Col>
              ))}
            </Row>

            <Divider />

            <Button
              type="primary"
              htmlType="submit"
              icon={<SaveOutlined />}
              loading={saving}
            >
              Save Entitlements
            </Button>
          </Form>
        </Card>
      )}
    </div>
  );
}
