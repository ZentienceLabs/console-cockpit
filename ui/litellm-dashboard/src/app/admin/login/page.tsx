"use client";

import { useLogin } from "@/app/(dashboard)/hooks/login/useLogin";
import { getProxyBaseUrl } from "@/components/networking";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";

function AdminLoginPageContent() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const loginMutation = useLogin();
  const router = useRouter();

  const handleSubmit = () => {
    loginMutation.mutate(
      { username, password },
      {
        onSuccess: (data) => {
          router.push(data.redirect_url);
        },
      },
    );
  };

  const error =
    loginMutation.error instanceof Error ? loginMutation.error.message : null;
  const { Title, Text } = Typography;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <Card className="w-full max-w-lg shadow-md">
        <Space direction="vertical" size="middle" className="w-full">
          <div className="text-center">
            <Title level={2}>Platform Admin Login</Title>
            <Text type="secondary">
              Break-glass access for Console super admins.
            </Text>
          </div>

          {error && <Alert message={error} type="error" showIcon />}

          <Form onFinish={handleSubmit} layout="vertical" requiredMark={true}>
            <Form.Item
              label="Username"
              name="username"
              rules={[{ required: true, message: "Please enter your username" }]}
            >
              <Input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={loginMutation.isPending}
                size="large"
              />
            </Form.Item>

            <Form.Item
              label="Password"
              name="password"
              rules={[{ required: true, message: "Please enter your password" }]}
            >
              <Input.Password
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loginMutation.isPending}
                size="large"
              />
            </Form.Item>

            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                loading={loginMutation.isPending}
                disabled={loginMutation.isPending}
                block
                size="large"
              >
                {loginMutation.isPending ? "Logging in..." : "Login"}
              </Button>
            </Form.Item>
          </Form>

          <div className="text-center">
            <Button type="link" href={`${getProxyBaseUrl()}/ui/login`}>
              Back to tenant login
            </Button>
          </div>
        </Space>
      </Card>
    </div>
  );
}

export default function AdminLoginPage() {
  const queryClient = new QueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <AdminLoginPageContent />
    </QueryClientProvider>
  );
}
