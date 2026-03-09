"use client";

import { useUIConfig } from "@/app/(dashboard)/hooks/uiConfig/useUIConfig";
import LoadingScreen from "@/components/common_components/LoadingScreen";
import { getProxyBaseUrl, loginResolveCall } from "@/components/networking";
import { getCookie } from "@/utils/cookieUtils";
import { isJwtExpired } from "@/utils/jwtUtils";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

function TenantLoginPageContent() {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isResolving, setIsResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: uiConfig, isLoading: isConfigLoading } = useUIConfig();
  const router = useRouter();

  useEffect(() => {
    if (isConfigLoading) {
      return;
    }

    if (uiConfig && uiConfig.admin_ui_disabled) {
      setIsLoading(false);
      return;
    }

    const rawToken = getCookie("token");
    if (rawToken && !isJwtExpired(rawToken)) {
      router.replace(`${getProxyBaseUrl()}/ui`);
      return;
    }

    setIsLoading(false);
  }, [isConfigLoading, router, uiConfig]);

  const handleEmailSubmit = async () => {
    setError(null);
    setIsResolving(true);
    try {
      const result = await loginResolveCall(email.trim().toLowerCase());
      if (result.method === "password") {
        window.location.href = result.admin_login_url || `${getProxyBaseUrl()}/ui/admin/login`;
        return;
      }
      if (result.sso_url) {
        window.location.href = result.sso_url;
        return;
      }
      setError(result.error || "Unable to determine the tenant login route.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start login.");
    } finally {
      setIsResolving(false);
    }
  };

  const { Title, Text, Paragraph } = Typography;

  if (isConfigLoading || isLoading) {
    return <LoadingScreen />;
  }

  if (uiConfig && uiConfig.admin_ui_disabled) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Card className="w-full max-w-lg shadow-md">
          <Space direction="vertical" size="middle" className="w-full">
            <div className="text-center">
              <Title level={2}>Alchemi Studio Console</Title>
            </div>

            <Alert
              message="Admin UI Disabled"
              description={
                <Paragraph className="text-sm">
                  The Admin UI has been disabled by the administrator.
                </Paragraph>
              }
              type="warning"
              showIcon
            />
          </Space>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Card className="w-full max-w-lg shadow-md">
        <Space direction="vertical" size="middle" className="w-full">
          <div className="text-center">
            <Title level={2}>Alchemi Studio Console</Title>
          </div>

          <div className="text-center">
            <Title level={3}>Tenant Login</Title>
            <Text type="secondary">
              Enter your work email. Console will redirect you directly to your tenant login.
            </Text>
          </div>

          {error && <Alert message={error} type="error" showIcon />}

          <Form onFinish={handleEmailSubmit} layout="vertical" requiredMark={true}>
            <Form.Item
              label="Work Email"
              name="email"
              rules={[
                { required: true, message: "Please enter your work email" },
                { type: "email", message: "Please enter a valid email address" },
              ]}
            >
              <Input
                placeholder="you@company.com"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isResolving}
                size="large"
                className="rounded-md border-gray-300"
              />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                loading={isResolving}
                disabled={isResolving}
                block
                size="large"
              >
                {isResolving ? "Redirecting..." : "Continue with SSO"}
              </Button>
            </Form.Item>
          </Form>

          <div className="text-center">
            <Button type="link" href={`${getProxyBaseUrl()}/ui/admin/login`}>
              Platform admin login
            </Button>
          </div>
        </Space>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  const queryClient = new QueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <TenantLoginPageContent />
    </QueryClientProvider>
  );
}
