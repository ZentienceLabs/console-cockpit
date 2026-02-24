"use client";

import { useLogin } from "@/app/(dashboard)/hooks/login/useLogin";
import { useUIConfig } from "@/app/(dashboard)/hooks/uiConfig/useUIConfig";
import LoadingScreen from "@/components/common_components/LoadingScreen";
import { getProxyBaseUrl, loginResolveCall } from "@/components/networking";
import { getCookie } from "@/utils/cookieUtils";
import { isJwtExpired } from "@/utils/jwtUtils";
import { InfoCircleOutlined } from "@ant-design/icons";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type LoginStep = "email" | "password";

function LoginPageContent() {
  const [loginStep, setLoginStep] = useState<LoginStep>("email");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [isResolving, setIsResolving] = useState(false);
  const { data: uiConfig, isLoading: isConfigLoading } = useUIConfig();
  const loginMutation = useLogin();
  const router = useRouter();

  useEffect(() => {
    if (isConfigLoading) {
      return;
    }

    // Check if admin UI is disabled
    if (uiConfig && uiConfig.admin_ui_disabled) {
      setIsLoading(false);
      return;
    }

    const rawToken = getCookie("token");
    if (rawToken && !isJwtExpired(rawToken)) {
      router.replace(`${getProxyBaseUrl()}/ui`);
      return;
    }

    if (uiConfig && uiConfig.auto_redirect_to_sso) {
      router.push(`${getProxyBaseUrl()}/sso/key/generate`);
      return;
    }

    setIsLoading(false);
  }, [isConfigLoading, router, uiConfig]);

  const handleEmailSubmit = async () => {
    setResolveError(null);
    setIsResolving(true);
    try {
      const result = await loginResolveCall(email);
      if (result.method === "sso" && result.sso_url) {
        // Redirect to SSO provider
        window.location.href = result.sso_url;
      } else {
        // Password login - show password form
        setUsername(email);
        setLoginStep("password");
      }
    } catch (err) {
      // If resolve endpoint fails (e.g., not configured), fall back to password login
      setUsername(email);
      setLoginStep("password");
    } finally {
      setIsResolving(false);
    }
  };

  const handlePasswordSubmit = () => {
    loginMutation.mutate(
      { username, password },
      {
        onSuccess: (data) => {
          router.push(data.redirect_url);
        },
      },
    );
  };

  const handleBack = () => {
    setLoginStep("email");
    setPassword("");
    setResolveError(null);
    loginMutation.reset();
  };

  const error = loginMutation.error instanceof Error ? loginMutation.error.message : resolveError;
  const isLoginLoading = loginMutation.isPending;

  const { Title, Text, Paragraph } = Typography;

  if (isConfigLoading || isLoading) {
    return <LoadingScreen />;
  }

  // Show disabled message if admin UI is disabled
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
                <>
                  <Paragraph className="text-sm">
                    The Admin UI has been disabled by the administrator. To re-enable it, please update the following
                    environment variable:
                  </Paragraph>
                  <Paragraph className="text-sm">
                    <code className="bg-gray-100 px-1 py-0.5 rounded text-xs">DISABLE_ADMIN_UI=False</code>
                  </Paragraph>
                </>
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
            <Title level={3}>Login</Title>
            <Text type="secondary">Access your Alchemi Studio Console.</Text>
          </div>

          {error && <Alert message={error} type="error" showIcon />}

          {/* Zitadel SSO Login */}
          <Button
            type="default"
            size="large"
            block
            onClick={() => {
              window.location.href = `${getProxyBaseUrl()}/zitadel/authorize`;
            }}
            className="mb-2"
          >
            Sign in with Alchemi SSO
          </Button>

          <div className="text-center my-2">
            <Text type="secondary">or sign in with email</Text>
          </div>

          {loginStep === "email" ? (
            <Form onFinish={handleEmailSubmit} layout="vertical" requiredMark={true}>
              <Form.Item
                label="Email or Username"
                name="email"
                rules={[{ required: true, message: "Please enter your email or username" }]}
              >
                <Input
                  placeholder="Enter your email or username"
                  autoComplete="username"
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
                  {isResolving ? "Checking..." : "Continue"}
                </Button>
              </Form.Item>
            </Form>
          ) : (
            <Form onFinish={handlePasswordSubmit} layout="vertical" requiredMark={true}>
              <div className="mb-4">
                <Text type="secondary">
                  Signing in as <Text strong>{username}</Text>
                </Text>
                <Button type="link" size="small" onClick={handleBack} className="ml-2">
                  Change
                </Button>
              </div>

              <Form.Item
                label="Password"
                name="password"
                rules={[{ required: true, message: "Please enter your password" }]}
              >
                <Input.Password
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoginLoading}
                  size="large"
                  autoFocus
                />
              </Form.Item>

              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={isLoginLoading}
                  disabled={isLoginLoading}
                  block
                  size="large"
                >
                  {isLoginLoading ? "Logging in..." : "Login"}
                </Button>
              </Form.Item>
            </Form>
          )}
        </Space>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  const queryClient = new QueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <LoginPageContent />
    </QueryClientProvider>
  );
}
