import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag, Typography, Tabs, Statistic, Card, Row, Col } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  copilotBudgetPlanList,
  copilotBudgetPlanCreate,
  copilotBudgetPlanUpdate,
  copilotBudgetPlanDelete,
  copilotCreditBudgetList,
  copilotCreditBudgetCreate,
  copilotCreditBudgetUpdate,
  copilotCreditBudgetDelete,
} from "../networking";
import NotificationsManager from "../molecules/notifications_manager";

const { Title } = Typography;

interface BudgetPlan {
  id: string;
  name: string;
  is_active?: boolean;
  distribution?: any;
  account_id?: string;
  created_at?: string;
}

interface CreditBudget {
  id: string;
  scope_type?: string;
  scope_id?: string;
  allocated?: number;
  limit_amount?: number;
  overflow_cap?: number;
  used?: number;
  overflow_used?: number;
  cycle_start?: string;
  cycle_end?: string;
  budget_plan_id?: string;
  account_id?: string;
  created_at?: string;
}

interface CopilotBudgetsProps {
  accessToken: string | null;
  userRole?: string;
  userID?: string | null;
}

const CopilotBudgets: React.FC<CopilotBudgetsProps> = ({ accessToken }) => {
  const [plans, setPlans] = useState<BudgetPlan[]>([]);
  const [budgets, setBudgets] = useState<CreditBudget[]>([]);
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [loadingBudgets, setLoadingBudgets] = useState(false);
  const [planModalVisible, setPlanModalVisible] = useState(false);
  const [budgetModalVisible, setBudgetModalVisible] = useState(false);
  const [editingPlan, setEditingPlan] = useState<BudgetPlan | null>(null);
  const [editingBudget, setEditingBudget] = useState<CreditBudget | null>(null);
  const [planForm] = Form.useForm();
  const [budgetForm] = Form.useForm();

  const fetchPlans = async () => {
    if (!accessToken) return;
    setLoadingPlans(true);
    try {
      const data = await copilotBudgetPlanList(accessToken);
      setPlans(data.plans || data || []);
    } catch (error) {
      console.error("Error fetching budget plans:", error);
    } finally {
      setLoadingPlans(false);
    }
  };

  const fetchBudgets = async () => {
    if (!accessToken) return;
    setLoadingBudgets(true);
    try {
      const data = await copilotCreditBudgetList(accessToken);
      setBudgets(data.budgets || data || []);
    } catch (error) {
      console.error("Error fetching credit budgets:", error);
    } finally {
      setLoadingBudgets(false);
    }
  };

  useEffect(() => {
    fetchPlans();
    fetchBudgets();
  }, [accessToken]);

  // Summary stats
  const totalAllocated = budgets.reduce((sum, b) => sum + (b.allocated || 0), 0);
  const totalUsed = budgets.reduce((sum, b) => sum + (b.used || 0), 0);
  const totalRemaining = totalAllocated - totalUsed;

  // Budget Plans CRUD
  const handleCreatePlan = () => { setEditingPlan(null); planForm.resetFields(); setPlanModalVisible(true); };
  const handleEditPlan = (plan: BudgetPlan) => {
    setEditingPlan(plan);
    planForm.setFieldsValue({ name: plan.name, is_active: plan.is_active !== false, distribution: plan.distribution ? JSON.stringify(plan.distribution, null, 2) : "" });
    setPlanModalVisible(true);
  };
  const handleDeletePlan = (planId: string, name: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: `Delete plan "${name}"?`, okType: "danger", okText: "Delete",
      onOk: async () => { await copilotBudgetPlanDelete(accessToken, planId); NotificationsManager.success(`Plan "${name}" deleted`); fetchPlans(); },
    });
  };
  const handleSubmitPlan = async () => {
    if (!accessToken) return;
    const values = await planForm.validateFields();
    const payload: any = { name: values.name, is_active: values.is_active };
    if (values.distribution) { try { payload.distribution = JSON.parse(values.distribution); } catch { NotificationsManager.error("Distribution must be valid JSON"); return; } }
    if (editingPlan) {
      await copilotBudgetPlanUpdate(accessToken, editingPlan.id, payload);
      NotificationsManager.success(`Plan "${values.name}" updated`);
    } else {
      await copilotBudgetPlanCreate(accessToken, payload);
      NotificationsManager.success(`Plan "${values.name}" created`);
    }
    setPlanModalVisible(false);
    fetchPlans();
  };

  // Credit Budgets CRUD
  const handleCreateBudget = () => { setEditingBudget(null); budgetForm.resetFields(); setBudgetModalVisible(true); };
  const handleEditBudget = (budget: CreditBudget) => {
    setEditingBudget(budget);
    budgetForm.setFieldsValue({
      scope_type: budget.scope_type, scope_id: budget.scope_id,
      allocated: budget.allocated, limit_amount: budget.limit_amount,
      overflow_cap: budget.overflow_cap, budget_plan_id: budget.budget_plan_id,
    });
    setBudgetModalVisible(true);
  };
  const handleDeleteBudget = (budgetId: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: "Delete this budget?", okType: "danger", okText: "Delete",
      onOk: async () => { await copilotCreditBudgetDelete(accessToken, budgetId); NotificationsManager.success("Budget deleted"); fetchBudgets(); },
    });
  };
  const handleSubmitBudget = async () => {
    if (!accessToken) return;
    const values = await budgetForm.validateFields();
    if (editingBudget) {
      await copilotCreditBudgetUpdate(accessToken, editingBudget.id, values);
      NotificationsManager.success("Budget updated");
    } else {
      await copilotCreditBudgetCreate(accessToken, values);
      NotificationsManager.success("Budget created");
    }
    setBudgetModalVisible(false);
    fetchBudgets();
  };

  const planColumns = [
    { title: "Name", dataIndex: "name", key: "name", render: (t: string) => <span className="font-medium">{t}</span> },
    { title: "Active", dataIndex: "is_active", key: "is_active", render: (v: boolean) => <Tag color={v !== false ? "green" : "red"}>{v !== false ? "Yes" : "No"}</Tag> },
    { title: "Created", dataIndex: "created_at", key: "created_at", render: (t: string) => t ? new Date(t).toLocaleDateString() : "-" },
    {
      title: "Actions", key: "actions",
      render: (_: any, r: BudgetPlan) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEditPlan(r)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeletePlan(r.id, r.name)} />
        </Space>
      ),
    },
  ];

  const budgetColumns = [
    { title: "Scope Type", dataIndex: "scope_type", key: "scope_type", render: (t: string) => <Tag>{t || "-"}</Tag> },
    { title: "Scope ID", dataIndex: "scope_id", key: "scope_id", render: (t: string) => <span className="text-xs font-mono">{t?.slice(0, 12) || "-"}</span> },
    { title: "Allocated", dataIndex: "allocated", key: "allocated", render: (v: number) => v?.toFixed(2) || "0.00" },
    { title: "Used", dataIndex: "used", key: "used", render: (v: number) => v?.toFixed(2) || "0.00" },
    {
      title: "Remaining", key: "remaining",
      render: (_: any, r: CreditBudget) => {
        const rem = (r.allocated || 0) - (r.used || 0);
        return <span className={rem < 0 ? "text-red-500" : "text-green-600"}>{rem.toFixed(2)}</span>;
      },
    },
    { title: "Cycle Start", dataIndex: "cycle_start", key: "cycle_start", render: (t: string) => t ? new Date(t).toLocaleDateString() : "-" },
    { title: "Cycle End", dataIndex: "cycle_end", key: "cycle_end", render: (t: string) => t ? new Date(t).toLocaleDateString() : "-" },
    {
      title: "Actions", key: "actions",
      render: (_: any, r: CreditBudget) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEditBudget(r)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDeleteBudget(r.id)} />
        </Space>
      ),
    },
  ];

  const tabItems = [
    {
      key: "budgets",
      label: "Credit Budgets",
      children: (
        <>
          <Row gutter={16} className="mb-4">
            <Col span={8}><Card size="small"><Statistic title="Total Allocated" value={totalAllocated.toFixed(2)} prefix="$" /></Card></Col>
            <Col span={8}><Card size="small"><Statistic title="Total Used" value={totalUsed.toFixed(2)} prefix="$" /></Card></Col>
            <Col span={8}><Card size="small"><Statistic title="Remaining" value={totalRemaining.toFixed(2)} prefix="$" valueStyle={{ color: totalRemaining >= 0 ? "#3f8600" : "#cf1322" }} /></Card></Col>
          </Row>
          <div className="flex justify-end mb-3">
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchBudgets} loading={loadingBudgets}>Refresh</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateBudget}>Add Budget</Button>
            </Space>
          </div>
          <Table dataSource={budgets} columns={budgetColumns} rowKey="id" loading={loadingBudgets} pagination={{ pageSize: 20 }} size="small" />
        </>
      ),
    },
    {
      key: "plans",
      label: "Budget Plans",
      children: (
        <>
          <div className="flex justify-end mb-3">
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchPlans} loading={loadingPlans}>Refresh</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreatePlan}>Add Plan</Button>
            </Space>
          </div>
          <Table dataSource={plans} columns={planColumns} rowKey="id" loading={loadingPlans} pagination={{ pageSize: 20 }} size="small" />
        </>
      ),
    },
  ];

  return (
    <div className="w-full mx-auto max-w-[1200px] p-6">
      <Title level={4}>Credit Budgets</Title>
      <Tabs items={tabItems} />

      {/* Plan Modal */}
      <Modal title={editingPlan ? "Edit Budget Plan" : "Create Budget Plan"} open={planModalVisible} onOk={handleSubmitPlan} onCancel={() => setPlanModalVisible(false)} okText={editingPlan ? "Update" : "Create"}>
        <Form form={planForm} layout="vertical" className="mt-4">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input placeholder="Plan name" /></Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked" initialValue={true}>
            <Select options={[{ value: true, label: "Active" }, { value: false, label: "Inactive" }]} />
          </Form.Item>
          <Form.Item name="distribution" label="Distribution (JSON)">
            <Input.TextArea rows={3} placeholder='{"monthly": 1000}' />
          </Form.Item>
        </Form>
      </Modal>

      {/* Budget Modal */}
      <Modal title={editingBudget ? "Edit Credit Budget" : "Create Credit Budget"} open={budgetModalVisible} onOk={handleSubmitBudget} onCancel={() => setBudgetModalVisible(false)} okText={editingBudget ? "Update" : "Create"}>
        <Form form={budgetForm} layout="vertical" className="mt-4">
          <Form.Item name="scope_type" label="Scope Type" rules={[{ required: true }]}>
            <Select options={[{ value: "USER", label: "User" }, { value: "TEAM", label: "Team" }, { value: "WORKSPACE", label: "Workspace" }, { value: "ACCOUNT", label: "Account" }]} />
          </Form.Item>
          <Form.Item name="scope_id" label="Scope ID" rules={[{ required: true }]}><Input placeholder="ID of the user/team/workspace" /></Form.Item>
          <Form.Item name="allocated" label="Allocated Credits" rules={[{ required: true }]}><InputNumber min={0} step={0.01} className="w-full" /></Form.Item>
          <Form.Item name="limit_amount" label="Limit Amount"><InputNumber min={0} step={0.01} className="w-full" /></Form.Item>
          <Form.Item name="overflow_cap" label="Overflow Cap"><InputNumber min={0} step={0.01} className="w-full" /></Form.Item>
          <Form.Item name="budget_plan_id" label="Budget Plan ID"><Input placeholder="Associated budget plan (optional)" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotBudgets;
