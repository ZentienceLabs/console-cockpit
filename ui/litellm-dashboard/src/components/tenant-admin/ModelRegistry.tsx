"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Alert,
  Table,
  Card,
  Input,
  Tag,
  Typography,
  Button,
  message,
  Select,
  Row,
  Col,
  Statistic,
} from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";

const { Text } = Typography;

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

interface ModelInfo {
  model_name: string;
  litellm_params?: {
    model?: string;
    custom_llm_provider?: string;
  };
  model_info?: {
    id?: string;
    mode?: string;
    max_tokens?: number;
    max_input_tokens?: number;
    max_output_tokens?: number;
    input_cost_per_token?: number;
    output_cost_per_token?: number;
    supported_openai_params?: string[];
  };
}

export default function ModelRegistry() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchText, setSearchText] = useState("");
  const [providerFilter, setProviderFilter] = useState<string | undefined>();
  const accessToken = getCookie("token") || "";

  const fetchModels = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/model/info", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const result = await response.json();
        setModels(result.data || []);
      } else {
        message.error("Failed to load model info");
      }
    } catch {
      message.error("Error loading model info");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const getProvider = (model: ModelInfo): string => {
    if (model.litellm_params?.custom_llm_provider) {
      return model.litellm_params.custom_llm_provider;
    }
    const litellmModel = model.litellm_params?.model || "";
    const slash = litellmModel.indexOf("/");
    if (slash > 0) {
      return litellmModel.substring(0, slash);
    }
    return "unknown";
  };

  const providers = Array.from(new Set(models.map(getProvider))).sort();

  const filteredModels = models.filter((m) => {
    const matchesSearch =
      !searchText ||
      m.model_name.toLowerCase().includes(searchText.toLowerCase()) ||
      (m.litellm_params?.model || "").toLowerCase().includes(searchText.toLowerCase());
    const matchesProvider = !providerFilter || getProvider(m) === providerFilter;
    return matchesSearch && matchesProvider;
  });

  const formatCost = (costPerToken: number | undefined): string => {
    if (costPerToken === undefined || costPerToken === null) return "-";
    const costPerMillion = costPerToken * 1_000_000;
    if (costPerMillion < 0.01) return `$${costPerMillion.toFixed(4)}/M`;
    return `$${costPerMillion.toFixed(2)}/M`;
  };

  const columns = [
    {
      title: "Model Name",
      dataIndex: "model_name",
      key: "model_name",
      sorter: (a: ModelInfo, b: ModelInfo) =>
        a.model_name.localeCompare(b.model_name),
    },
    {
      title: "Provider",
      key: "provider",
      render: (_: any, record: ModelInfo) => {
        const provider = getProvider(record);
        const colors: Record<string, string> = {
          openai: "green",
          anthropic: "purple",
          azure: "blue",
          google: "red",
          aws: "orange",
          bedrock: "orange",
          vertex_ai: "red",
          cohere: "cyan",
          mistral: "geekblue",
        };
        return <Tag color={colors[provider] || "default"}>{provider}</Tag>;
      },
      filters: providers.map((p) => ({ text: p, value: p })),
      onFilter: (value: any, record: ModelInfo) => getProvider(record) === value,
    },
    {
      title: "LiteLLM Model",
      key: "litellm_model",
      ellipsis: true,
      render: (_: any, record: ModelInfo) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {record.litellm_params?.model || "-"}
        </Text>
      ),
    },
    {
      title: "Mode",
      key: "mode",
      render: (_: any, record: ModelInfo) => {
        const mode = record.model_info?.mode;
        if (!mode) return "-";
        const colors: Record<string, string> = {
          chat: "blue",
          completion: "green",
          embedding: "purple",
          image_generation: "magenta",
          audio_transcription: "orange",
        };
        return <Tag color={colors[mode] || "default"}>{mode}</Tag>;
      },
    },
    {
      title: "Max Tokens",
      key: "max_tokens",
      render: (_: any, record: ModelInfo) => {
        const max = record.model_info?.max_tokens;
        return max ? max.toLocaleString() : "-";
      },
      sorter: (a: ModelInfo, b: ModelInfo) =>
        (a.model_info?.max_tokens || 0) - (b.model_info?.max_tokens || 0),
    },
    {
      title: "Input Cost",
      key: "input_cost",
      render: (_: any, record: ModelInfo) =>
        formatCost(record.model_info?.input_cost_per_token),
      sorter: (a: ModelInfo, b: ModelInfo) =>
        (a.model_info?.input_cost_per_token || 0) -
        (b.model_info?.input_cost_per_token || 0),
    },
    {
      title: "Output Cost",
      key: "output_cost",
      render: (_: any, record: ModelInfo) =>
        formatCost(record.model_info?.output_cost_per_token),
      sorter: (a: ModelInfo, b: ModelInfo) =>
        (a.model_info?.output_cost_per_token || 0) -
        (b.model_info?.output_cost_per_token || 0),
    },
  ];

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message="Gateway BYOK Model Registry"
        description="This tab shows gateway models/deployments for the core console product. Copilot model governance is managed separately in the 'Copilot Model Governance' tab."
        style={{ marginBottom: 16 }}
      />
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic title="Total Models" value={models.length} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="Providers" value={providers.length} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="Shown"
              value={filteredModels.length}
              suffix={`/ ${models.length}`}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 16,
            gap: 12,
          }}
        >
          <div style={{ display: "flex", gap: 12 }}>
            <Input
              placeholder="Search models..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ width: 300 }}
              allowClear
            />
            <Select
              placeholder="Filter by provider"
              allowClear
              style={{ width: 200 }}
              options={providers.map((p) => ({ label: p, value: p }))}
              onChange={(v) => setProviderFilter(v)}
              value={providerFilter}
            />
          </div>
          <Button icon={<ReloadOutlined />} onClick={fetchModels}>
            Refresh
          </Button>
        </div>
        <Table
          dataSource={filteredModels}
          columns={columns}
          rowKey={(record) => record.model_name}
          loading={loading}
          pagination={{ pageSize: 20 }}
          size="small"
        />
      </Card>
    </div>
  );
}
