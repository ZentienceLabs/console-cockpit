"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Table, Button, Modal, Form, Input, InputNumber, Select, Card, Statistic, Row, Col, Tabs, message, Space, Drawer, DatePicker, Tag, Progress } from "antd";
import { PlusOutlined, DeleteOutlined, EditOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  useCopilotBudgets,
  useCopilotBudgetSummary,
  useCopilotBudgetAllocationOverview,
  useCreateCopilotBudget,
  useUpdateCopilotBudget,
  useDeleteCopilotBudget,
  useAllocateCopilotBudget,
  useDistributeEqualCopilotBudget,
  useCopilotBudgetPlans,
  useCreateCopilotBudgetPlan,
  useUpdateCopilotBudgetPlan,
  useDeleteCopilotBudgetPlan,
} from "@/app/(dashboard)/hooks/copilot/useCopilotBudgets";
import {
  useCopilotGroups,
  useCopilotMemberships,
  useCopilotTeams,
} from "@/app/(dashboard)/hooks/copilot/useCopilotOverview";
import { useCopilotUsers } from "@/app/(dashboard)/hooks/copilot/useCopilotDirectory";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";
import { useCopilotAccounts } from "@/app/(dashboard)/hooks/copilot/useCopilotAccounts";

const { TabPane } = Tabs;

const CopilotBudgetsPage: React.FC = () => {
  const { accountId, isSuperAdmin } = useAuthorized();
  const [selectedAccountId, setSelectedAccountId] = useState<string | undefined>(accountId || undefined);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingBudget, setEditingBudget] = useState<any>(null);
  const [isOverrideFlow, setIsOverrideFlow] = useState(false);
  const [allocationModalOpen, setAllocationModalOpen] = useState(false);
  const [distributeModalOpen, setDistributeModalOpen] = useState(false);
  const [selectedParentBudget, setSelectedParentBudget] = useState<any>(null);
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<any>(null);
  const [form] = Form.useForm();
  const [allocationForm] = Form.useForm();
  const [distributeForm] = Form.useForm();
  const [planForm] = Form.useForm();

  const accountFilter = isSuperAdmin ? selectedAccountId : undefined;
  const { data: accountData, isLoading: accountLoading } = useCopilotAccounts();
  const { data: budgetsData, isLoading } = useCopilotBudgets({
    account_id: accountFilter,
    active_only: true,
    resolve_inherited: true,
  });
  const { data: summaryData } = useCopilotBudgetSummary({ account_id: accountFilter });
  const { data: allocationOverviewData, isLoading: allocationLoading } = useCopilotBudgetAllocationOverview({
    account_id: accountFilter,
    active_only: true,
  });
  const { data: plansData, isLoading: plansLoading } = useCopilotBudgetPlans({ account_id: accountFilter });
  const { data: usersData } = useCopilotUsers({
    account_id: accountFilter,
    source: "identity",
    include_memberships: true,
    limit: 500,
    offset: 0,
  });
  const { data: groupsData } = useCopilotGroups({ account_id: accountFilter, source: "identity", limit: 500 });
  const { data: teamsData } = useCopilotTeams({ account_id: accountFilter, source: "identity", include_group: true, limit: 500 });
  const { data: membershipsData } = useCopilotMemberships({ account_id: accountFilter, source: "identity", limit: 500 });

  const createBudget = useCreateCopilotBudget();
  const updateBudget = useUpdateCopilotBudget();
  const deleteBudget = useDeleteCopilotBudget();
  const allocateBudget = useAllocateCopilotBudget();
  const distributeEqual = useDistributeEqualCopilotBudget();
  const createPlan = useCreateCopilotBudgetPlan();
  const updatePlan = useUpdateCopilotBudgetPlan();
  const deletePlan = useDeleteCopilotBudgetPlan();

  const budgets = budgetsData?.data ?? [];
  const accountBudgetRows = useMemo(() => budgets.filter((b: any) => b.scope_type === "account"), [budgets]);
  const summary = summaryData?.data ?? [];
  const allocationOverview = allocationOverviewData?.data ?? {};
  const accountAllocationBudget = allocationOverview?.account_budget ?? null;
  const parentBudgets = allocationOverview?.parent_budgets ?? [];
  const plans = plansData?.data ?? [];
  const accounts = accountData?.accounts ?? [];
  const directoryUsers = usersData?.data?.users ?? [];
  const groups = groupsData?.data ?? [];
  const teams = teamsData?.data ?? [];
  const rawMemberships = membershipsData?.data ?? [];

  useEffect(() => {
    if (isSuperAdmin && !selectedAccountId && accounts.length > 0) {
      setSelectedAccountId(accounts[0].account_id);
    }
  }, [accounts, isSuperAdmin, selectedAccountId]);

  const totalAllocated = summary.reduce((sum: number, s: any) => sum + (s.total_allocated || 0), 0);
  const totalUsed = summary.reduce((sum: number, s: any) => sum + (s.total_used || 0), 0);
  const totalRemaining = totalAllocated - totalUsed;

  const users = useMemo(() => {
    const byId: Record<string, any> = {};
    for (const user of directoryUsers) {
      if (user?.id) {
        byId[user.id] = user;
      }
    }
    for (const membership of rawMemberships) {
      const user = membership?.user;
      if (user?.id && !byId[user.id]) {
        byId[user.id] = user;
      }
    }
    return Object.values(byId);
  }, [directoryUsers, rawMemberships]);

  const memberships = useMemo(() => {
    const rows: any[] = [];
    const seen = new Set<string>();

    const addMembership = (membership: any) => {
      if (!membership) return;
      const userId = membership.user_id || membership.user?.id;
      if (!userId) return;
      const teamId = membership.team_id || membership.team?.id || "";
      const dedupeKey = membership.id || `${userId}:${teamId}:${membership.app_role || ""}`;
      if (seen.has(dedupeKey)) return;
      seen.add(dedupeKey);
      rows.push({
        ...membership,
        user_id: userId,
        team_id: teamId || undefined,
      });
    };

    rawMemberships.forEach(addMembership);
    directoryUsers.forEach((user: any) => {
      (user?.memberships || []).forEach((membership: any) => {
        addMembership({
          ...membership,
          user_id: membership?.user_id || user.id,
          user: membership?.user || {
            id: user.id,
            name: user.name,
            email: user.email,
          },
        });
      });
    });
    return rows;
  }, [directoryUsers, rawMemberships]);

  const ensureAccountForSuperAdminWrite = () => {
    if (isSuperAdmin && !accountFilter) {
      message.warning("Select an account before creating Copilot budgets or plans.");
      return false;
    }
    return true;
  };

  const scopeLabelByType: Record<string, string> = {
    account: "Account",
    group: "Organization",
    team: "Team",
    user: "User",
  };

  const entityNameByScope = useMemo(() => {
    const lookup: Record<string, string> = {};
    groups.forEach((g: any) => {
      lookup[`group:${g.id}`] = g.name;
    });
    teams.forEach((t: any) => {
      lookup[`team:${t.id}`] = t.name;
    });
    users.forEach((u: any) => {
      lookup[`user:${u.id}`] = u.name || u.email || u.id;
    });
    const activeAccount = accountFilter || accountId;
    if (activeAccount) {
      lookup[`account:${activeAccount}`] = "Current Account";
    }
    return lookup;
  }, [accountFilter, accountId, groups, teams, users]);

  const parentBudgetOptions = useMemo(() => {
    return (parentBudgets || []).map((budget: any) => ({
      label: `${scopeLabelByType[budget.scope_type] || budget.scope_type}: ${
        entityNameByScope[`${budget.scope_type}:${budget.scope_id}`] || budget.scope_id
      } (Unallocated ${(Number(budget.unallocated || 0)).toLocaleString()})`,
      value: budget.id,
      scope_type: budget.scope_type,
    }));
  }, [entityNameByScope, parentBudgets]);

  const allocationTargetScopeOptions = useMemo(() => {
    if (!selectedParentBudget) return [];
    if (selectedParentBudget.scope_type === "account") {
      return [
        { label: "Organization", value: "group" },
        { label: "Team", value: "team" },
        { label: "User", value: "user" },
      ];
    }
    if (selectedParentBudget.scope_type === "group") {
      return [
        { label: "Team", value: "team" },
        { label: "User", value: "user" },
      ];
    }
    if (selectedParentBudget.scope_type === "team") {
      return [{ label: "User", value: "user" }];
    }
    return [];
  }, [selectedParentBudget]);

  const allocationTargetScopeType = Form.useWatch("target_scope_type", allocationForm);
  const allocationTargetEntityOptions = useMemo(() => {
    if (!selectedParentBudget || !allocationTargetScopeType) return [];
    if (allocationTargetScopeType === "group") {
      return groups.map((g: any) => ({ label: g.name, value: g.id }));
    }
    if (allocationTargetScopeType === "team") {
      const parentScope = selectedParentBudget.scope_type;
      if (parentScope === "group") {
        return teams
          .filter((t: any) => t.group_id === selectedParentBudget.scope_id || t.group?.id === selectedParentBudget.scope_id)
          .map((t: any) => ({ label: t.group?.name ? `${t.name} (${t.group.name})` : t.name, value: t.id }));
      }
      return teams.map((t: any) => ({ label: t.group?.name ? `${t.name} (${t.group.name})` : t.name, value: t.id }));
    }
    if (allocationTargetScopeType === "user") {
      if (selectedParentBudget.scope_type === "team") {
        return users
          .filter((u: any) => memberships.some((m: any) => m.user_id === u.id && m.team_id === selectedParentBudget.scope_id))
          .map((u: any) => ({ label: u.email ? `${u.name || "User"} (${u.email})` : (u.name || u.id), value: u.id }));
      }
      if (selectedParentBudget.scope_type === "group") {
        const groupTeamIds = new Set(
          teams
            .filter((t: any) => t.group_id === selectedParentBudget.scope_id || t.group?.id === selectedParentBudget.scope_id)
            .map((t: any) => t.id),
        );
        return users
          .filter((u: any) => memberships.some((m: any) => m.user_id === u.id && m.team_id && groupTeamIds.has(m.team_id)))
          .map((u: any) => ({ label: u.email ? `${u.name || "User"} (${u.email})` : (u.name || u.id), value: u.id }));
      }
      return users.map((u: any) => ({ label: u.email ? `${u.name || "User"} (${u.email})` : (u.name || u.id), value: u.id }));
    }
    return [];
  }, [allocationTargetScopeType, groups, memberships, selectedParentBudget, teams, users]);

  const activeBudgets = useMemo(() => {
    const now = Date.now();
    return budgets.filter((budget: any) => {
      const start = Date.parse(String(budget.cycle_start || ""));
      const end = Date.parse(String(budget.cycle_end || ""));
      if (!Number.isFinite(start) || !Number.isFinite(end)) return false;
      return start <= now && now <= end;
    });
  }, [budgets]);

  const latestBudgetByScope = useMemo(() => {
    const map: Record<string, any> = {};
    for (const budget of activeBudgets) {
      const key = `${budget.scope_type}:${budget.scope_id}`;
      const existing = map[key];
      if (!existing) {
        map[key] = budget;
        continue;
      }
      const existingTs = Date.parse(String(existing.created_at || existing.updated_at || ""));
      const nextTs = Date.parse(String(budget.created_at || budget.updated_at || ""));
      if (Number.isFinite(nextTs) && (!Number.isFinite(existingTs) || nextTs > existingTs)) {
        map[key] = budget;
      }
    }
    return map;
  }, [activeBudgets]);

  const effectiveUserRows = useMemo(() => {
    const activeAccount = accountFilter || accountId;
    if (!activeAccount) return [];
    const accountBudget = latestBudgetByScope[`account:${activeAccount}`];

    const firstMembershipByUser: Record<string, any> = {};
    memberships.forEach((membership: any) => {
      const userId = membership?.user_id;
      if (userId && !firstMembershipByUser[userId]) {
        firstMembershipByUser[userId] = membership;
      }
    });

    return users.map((user: any) => {
      const membership = firstMembershipByUser[user.id];
      const teamId = membership?.team_id || membership?.team?.id;
      const groupId = membership?.team?.group_id || membership?.team?.group?.id;

      const userBudget = latestBudgetByScope[`user:${user.id}`];
      const teamBudget = teamId ? latestBudgetByScope[`team:${teamId}`] : null;
      const groupBudget = groupId ? latestBudgetByScope[`group:${groupId}`] : null;
      const effectiveBudget = userBudget || teamBudget || groupBudget || accountBudget;

      const source = userBudget
        ? "User Override"
        : teamBudget
          ? `Team: ${membership?.team?.name || teamId}`
          : groupBudget
            ? `Organization: ${membership?.team?.group?.name || groupId}`
            : "Account Default";

      return {
        key: user.id,
        user_id: user.id,
        user_name: user.name || user.email || user.id,
        user_email: user.email,
        team_name: membership?.team?.name || "-",
        group_name: membership?.team?.group?.name || "-",
        effective_allocated: Number(effectiveBudget?.allocated || 0),
        effective_limit: Number(effectiveBudget?.limit_amount || 0),
        effective_used: Number(effectiveBudget?.used || 0),
        effective_overflow_cap: effectiveBudget?.overflow_cap,
        source,
        source_budget: effectiveBudget || null,
      };
    });
  }, [accountFilter, accountId, latestBudgetByScope, memberships, users]);

  const openUserOverride = (record: any) => {
    const sourceBudget = record.source_budget;
    if (!sourceBudget) {
      message.warning("No base budget found. Create an account budget first.");
      return;
    }
    setEditingBudget(null);
    setIsOverrideFlow(true);
    form.resetFields();
    form.setFieldsValue(toBudgetFormValues({
      scope_type: "user",
      scope_id: record.user_id,
      parent_budget_id: sourceBudget?.id,
      allocation_strategy: "override",
      allocated: Number(sourceBudget.allocated || 0),
      limit_amount: Number(sourceBudget.limit_amount || 0),
      overflow_cap: sourceBudget.overflow_cap != null ? Number(sourceBudget.overflow_cap) : undefined,
      cycle_start: sourceBudget.cycle_start,
      cycle_end: sourceBudget.cycle_end,
    }));
    setDrawerOpen(true);
  };

  const handleCreateOrUpdate = async () => {
    try {
      const values = await form.validateFields();
      const payload = { ...values };
      if (!editingBudget) {
        if (!ensureAccountForSuperAdminWrite()) return;
        if (!isOverrideFlow) {
          payload.scope_type = "account";
          payload.scope_id = accountFilter || accountId;
          payload.cycle_start = values.cycle_start?.toISOString?.() ?? values.cycle_start;
          payload.cycle_end = values.cycle_end?.toISOString?.() ?? values.cycle_end;
        }
      }
      if (editingBudget) {
        await updateBudget.mutateAsync({ id: editingBudget.id, data: payload });
        message.success("Budget updated");
      } else {
        if (isOverrideFlow && payload.parent_budget_id) {
          await allocateBudget.mutateAsync({
            parentBudgetId: payload.parent_budget_id,
            data: {
              target_scope_type: "user",
              target_scope_id: payload.scope_id,
              allocated: payload.allocated,
              limit_amount: payload.limit_amount,
              overflow_cap: payload.overflow_cap,
              allocation_strategy: payload.allocation_strategy || "manual",
            },
          });
          message.success("Budget allocation saved");
        } else {
          await createBudget.mutateAsync({ data: payload, account_id: accountFilter });
          message.success("Budget created");
        }
      }
      setDrawerOpen(false);
      setEditingBudget(null);
      setIsOverrideFlow(false);
      form.resetFields();
    } catch (err) {
      // validation or API error
    }
  };

  const handleDelete = (id: string) => {
    Modal.confirm({
      title: "Delete Budget",
      content: "Are you sure you want to delete this budget?",
      onOk: async () => {
        await deleteBudget.mutateAsync(id);
        message.success("Budget deleted");
      },
    });
  };

  const toBudgetFormValues = (record: any) => ({
    ...record,
    cycle_start: record?.cycle_start ? dayjs(record.cycle_start) : undefined,
    cycle_end: record?.cycle_end ? dayjs(record.cycle_end) : undefined,
  });

  const openAllocationModal = (parent: any) => {
    setSelectedParentBudget(parent);
    allocationForm.resetFields();
    const defaultScopeType = parent.scope_type === "team" ? "user" : parent.scope_type === "group" ? "team" : "group";
    allocationForm.setFieldsValue({
      target_scope_type: defaultScopeType,
      allocation_strategy: "manual",
    });
    setAllocationModalOpen(true);
  };

  const handleAllocationSave = async () => {
    if (!selectedParentBudget) return;
    try {
      const values = await allocationForm.validateFields();
      await allocateBudget.mutateAsync({
        parentBudgetId: selectedParentBudget.id,
        data: values,
      });
      message.success("Allocation saved");
      setAllocationModalOpen(false);
      setSelectedParentBudget(null);
      allocationForm.resetFields();
    } catch {
      // handled by query error toast
    }
  };

  const openDistributeModal = (parent: any) => {
    setSelectedParentBudget(parent);
    distributeForm.setFieldsValue({ include_override_users: false, target_scope_type: "user" });
    setDistributeModalOpen(true);
  };

  const handleDistributeEqual = async () => {
    if (!selectedParentBudget) return;
    try {
      const values = await distributeForm.validateFields();
      const res: any = await distributeEqual.mutateAsync({
        parentBudgetId: selectedParentBudget.id,
        data: values,
      });
      const stats = res?.data || {};
      message.success(
        `Distributed equally: created ${stats.created || 0}, updated ${stats.updated || 0}, locked overrides ${stats.locked_override_users || 0}`,
      );
      setDistributeModalOpen(false);
      setSelectedParentBudget(null);
    } catch {
      // handled by query error toast
    }
  };

  const handlePlanCreateOrUpdate = async () => {
    try {
      const values = await planForm.validateFields();
      if (values.distribution_mode === "weighted") {
        const totalWeight = Number(values.group_weight || 0) + Number(values.team_weight || 0) + Number(values.user_weight || 0);
        if (totalWeight <= 0) {
          message.error("Weighted distribution requires at least one non-zero weight.");
          return;
        }
      }

      const payload = {
        name: values.name,
        is_active: values.is_active,
        distribution: {
          distribution_mode: values.distribution_mode || "manual",
          default_target_scope: values.default_target_scope || "organization",
          auto_distribute_new_users: Boolean(values.auto_distribute_new_users),
          lock_user_overrides: Boolean(values.lock_user_overrides),
          weights: {
            group: Number(values.group_weight || 0),
            team: Number(values.team_weight || 0),
            user: Number(values.user_weight || 0),
          },
          notes: values.notes?.trim?.() || "",
        },
      };
      if (editingPlan) {
        await updatePlan.mutateAsync({ id: editingPlan.id, data: payload });
        message.success("Plan updated");
      } else {
        if (!ensureAccountForSuperAdminWrite()) return;
        await createPlan.mutateAsync({ data: payload, account_id: accountFilter });
        message.success("Plan created");
      }
      setPlanModalOpen(false);
      setEditingPlan(null);
      planForm.resetFields();
    } catch (err) {
      // validation or API error
    }
  };

  const selectedPlanMode = Form.useWatch("distribution_mode", planForm);

  const budgetColumns = [
    {
      title: "Account",
      key: "scope",
      render: (_: any, record: any) => (
        <Space>
          <Tag color="blue">{scopeLabelByType[record.scope_type] || record.scope_type}</Tag>
          <span>{entityNameByScope[`${record.scope_type}:${record.scope_id}`] || record.scope_id}</span>
        </Space>
      ),
    },
    {
      title: "Allocated",
      dataIndex: "allocated",
      key: "allocated",
      render: (v: number) => v?.toLocaleString() ?? 0,
    },
    {
      title: "Distributed",
      dataIndex: "distributed_allocated",
      key: "distributed_allocated",
      render: (v: number) => Number(v || 0).toLocaleString(),
    },
    {
      title: "Unallocated",
      dataIndex: "unallocated",
      key: "unallocated",
      render: (v: number) => (
        <Tag color={Number(v || 0) > 0 ? "green" : "default"}>
          {Number(v || 0).toLocaleString()}
        </Tag>
      ),
    },
    {
      title: "Limit",
      dataIndex: "limit_amount",
      key: "limit_amount",
      render: (v: number) => v?.toLocaleString() ?? 0,
    },
    {
      title: "Used",
      dataIndex: "used",
      key: "used",
      render: (v: number, record: any) => {
        const pct = record.limit_amount > 0 ? Math.round((v / record.limit_amount) * 100) : 0;
        return (
          <Space direction="vertical" size={0}>
            <span>{v?.toLocaleString() ?? 0}</span>
            <Progress percent={pct} size="small" status={pct >= 90 ? "exception" : "normal"} showInfo={false} />
          </Space>
        );
      },
    },
    {
      title: "Overflow",
      key: "overflow",
      render: (_: any, record: any) => (
        <span>{record.overflow_used ?? 0} / {record.overflow_cap ?? "N/A"}</span>
      ),
    },
    {
      title: "Cycle",
      key: "cycle",
      render: (_: any, record: any) => (
        <span>{record.cycle_start?.split("T")[0]} - {record.cycle_end?.split("T")[0]}</span>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingBudget(record);
              setIsOverrideFlow(false);
              form.setFieldsValue(toBudgetFormValues(record));
              setDrawerOpen(true);
            }}
          />
          <Button size="small" icon={<DeleteOutlined />} danger onClick={() => handleDelete(record.id)} />
        </Space>
      ),
    },
  ];

  const allocationColumns = [
    {
      title: "Parent Scope",
      key: "scope",
      render: (_: any, record: any) => (
        <Space>
          <Tag color="purple">{scopeLabelByType[record.scope_type] || record.scope_type}</Tag>
          <span>{entityNameByScope[`${record.scope_type}:${record.scope_id}`] || record.scope_id}</span>
        </Space>
      ),
    },
    {
      title: "Allocated",
      dataIndex: "allocated",
      key: "allocated",
      render: (v: number) => v?.toLocaleString() ?? 0,
    },
    {
      title: "Distributed",
      dataIndex: "distributed_allocated",
      key: "distributed_allocated",
      render: (v: number) => Number(v || 0).toLocaleString(),
    },
    {
      title: "Unallocated",
      dataIndex: "unallocated",
      key: "unallocated",
      render: (v: number) => <Tag color={Number(v || 0) > 0 ? "green" : "default"}>{Number(v || 0).toLocaleString()}</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" onClick={() => openAllocationModal(record)}>
            Allocate
          </Button>
          {(record.scope_type === "group" || record.scope_type === "team") && (
            <Button size="small" onClick={() => openDistributeModal(record)}>
              Distribute Equally
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const effectiveUserColumns = [
    { title: "User", dataIndex: "user_name", key: "user_name" },
    { title: "Email", dataIndex: "user_email", key: "user_email" },
    { title: "Team", dataIndex: "team_name", key: "team_name" },
    { title: "Organization", dataIndex: "group_name", key: "group_name" },
    {
      title: "Effective Allocated",
      dataIndex: "effective_allocated",
      key: "effective_allocated",
      render: (value: number) => value?.toLocaleString() ?? 0,
    },
    {
      title: "Effective Limit",
      dataIndex: "effective_limit",
      key: "effective_limit",
      render: (value: number) => value?.toLocaleString() ?? 0,
    },
    {
      title: "Effective Used",
      dataIndex: "effective_used",
      key: "effective_used",
      render: (value: number, record: any) => {
        const pct = record.effective_limit > 0 ? Math.round((value / record.effective_limit) * 100) : 0;
        return (
          <Space direction="vertical" size={0}>
            <span>{value?.toLocaleString() ?? 0}</span>
            <Progress percent={pct} size="small" status={pct >= 90 ? "exception" : "normal"} showInfo={false} />
          </Space>
        );
      },
    },
    {
      title: "Source",
      dataIndex: "source",
      key: "source",
      render: (value: string) => <Tag color={value === "User Override" ? "green" : "blue"}>{value}</Tag>,
    },
    {
      title: "Action",
      key: "action",
      render: (_: any, record: any) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openUserOverride(record)}>
          Override
        </Button>
      ),
    },
  ];

  const planColumns = [
    { title: "Name", dataIndex: "name", key: "name" },
    {
      title: "Distribution",
      key: "distribution",
      render: (_: any, record: any) => {
        const distribution = record?.distribution || {};
        const mode = distribution?.distribution_mode || "manual";
        const target = distribution?.default_target_scope || "organization";
        const weights = distribution?.weights || {};
        const weightSummary = [weights.group, weights.team, weights.user]
          .filter((v: any) => Number.isFinite(Number(v)))
          .map((v: any) => Number(v))
          .join(" / ");
        return (
          <Space direction="vertical" size={0}>
            <Tag color="blue">{mode}</Tag>
            <span>Default target: {target}</span>
            {mode === "weighted" && weightSummary ? <span>Weights (Org/Team/User): {weightSummary}</span> : null}
          </Space>
        );
      },
    },
    {
      title: "Active",
      dataIndex: "is_active",
      key: "is_active",
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "Active" : "Inactive"}</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: any) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingPlan(record);
              const distribution = record?.distribution || {};
              const weights = distribution?.weights || {};
              planForm.setFieldsValue({
                ...record,
                distribution_mode: distribution.distribution_mode || "manual",
                default_target_scope: distribution.default_target_scope || "organization",
                auto_distribute_new_users: distribution.auto_distribute_new_users ?? false,
                lock_user_overrides: distribution.lock_user_overrides ?? false,
                group_weight: Number(weights.group ?? 50),
                team_weight: Number(weights.team ?? 30),
                user_weight: Number(weights.user ?? 20),
                notes: distribution.notes || "",
              });
              setPlanModalOpen(true);
            }}
          />
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            onClick={() => {
              Modal.confirm({
                title: "Delete Plan",
                content: "Delete this budget plan?",
                onOk: async () => {
                  await deletePlan.mutateAsync(record.id);
                  message.success("Plan deleted");
                },
              });
            }}
          />
        </Space>
      ),
    },
  ];

  return (
    <div style={{ width: "100%" }}>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={8}>
          <Card>
            <Statistic title="Total Allocated" value={totalAllocated} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="Total Used" value={totalUsed} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="Total Remaining" value={totalRemaining} valueStyle={{ color: totalRemaining > 0 ? "#3f8600" : "#cf1322" }} />
          </Card>
        </Col>
      </Row>

      <Tabs defaultActiveKey="budgets">
        <TabPane tab="1. Account Budget" key="budgets">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between" }}>
            <Space>
              {isSuperAdmin && (
                <Select
                  placeholder="Filter by account"
                  allowClear
                  style={{ width: 280 }}
                  loading={accountLoading}
                  value={selectedAccountId}
                  onChange={(v) => setSelectedAccountId(v)}
                  options={accounts.map((a: any) => ({
                    label: `${a.account_name} (${a.status})`,
                    value: a.account_id,
                  }))}
                />
              )}
            </Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingBudget(null);
                setIsOverrideFlow(false);
                form.resetFields();
                form.setFieldsValue({
                  scope_type: "account",
                  scope_id: accountFilter || accountId,
                  allocation_strategy: "manual",
                  cycle_start: undefined,
                  cycle_end: undefined,
                });
                setDrawerOpen(true);
              }}
            >
              Create Account Budget
            </Button>
          </div>
          <div style={{ marginBottom: 12, color: "#666" }}>
            Step 1: Set the account-level credit pool and cycle. This creates the unallocated pool used in Distribution.
          </div>
          <Table
            dataSource={accountBudgetRows}
            columns={budgetColumns}
            rowKey="id"
            loading={isLoading}
            pagination={{ total: accountBudgetRows.length, pageSize: 20 }}
          />
        </TabPane>
        <TabPane tab="2. Distribution" key="allocation">
          <div style={{ marginBottom: 12, color: "#666" }}>
            Step 2: Allocate credits from account to organizations/teams/users, or distribute equally.
          </div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Card>
                <Statistic title="Account Allocated" value={Number(accountAllocationBudget?.allocated || 0)} />
              </Card>
            </Col>
            <Col span={12}>
              <Card>
                <Statistic
                  title="Account Unallocated"
                  value={Number(accountAllocationBudget?.unallocated || 0)}
                  valueStyle={{ color: Number(accountAllocationBudget?.unallocated || 0) > 0 ? "#3f8600" : undefined }}
                />
              </Card>
            </Col>
          </Row>
          <Table
            dataSource={parentBudgets}
            columns={allocationColumns}
            rowKey="id"
            loading={allocationLoading}
            pagination={{ pageSize: 50 }}
          />
        </TabPane>
        <TabPane tab="3. User Overrides" key="effective">
          <div style={{ marginBottom: 12, color: "#666" }}>
            Step 3: Review each user's effective credits and create user-level overrides where needed.
          </div>
          <Table
            dataSource={effectiveUserRows}
            columns={effectiveUserColumns}
            rowKey="user_id"
            pagination={{ pageSize: 50 }}
          />
        </TabPane>
        <TabPane tab="4. Budget Plans (Advanced)" key="plans">
          <div style={{ marginBottom: 16, display: "flex", justifyContent: "flex-end" }}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingPlan(null);
                planForm.resetFields();
                planForm.setFieldsValue({
                  name: "",
                  is_active: true,
                  distribution_mode: "manual",
                  default_target_scope: "organization",
                  auto_distribute_new_users: false,
                  lock_user_overrides: false,
                  group_weight: 50,
                  team_weight: 30,
                  user_weight: 20,
                  notes: "",
                });
                setPlanModalOpen(true);
              }}
            >
              Create Plan
            </Button>
          </div>
          <Table dataSource={plans} columns={planColumns} rowKey="id" loading={plansLoading} />
        </TabPane>
      </Tabs>

      <Drawer
        title={editingBudget ? "Edit Account Budget" : isOverrideFlow ? "Create User Override" : "Create Account Budget"}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setEditingBudget(null);
          setIsOverrideFlow(false);
          form.resetFields();
        }}
        width={480}
        extra={
          <Button
            type="primary"
            onClick={handleCreateOrUpdate}
            loading={createBudget.isPending || updateBudget.isPending || allocateBudget.isPending}
          >
            {editingBudget ? "Update" : isOverrideFlow ? "Save Override" : "Create"}
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="scope_type" hidden>
            <Input />
          </Form.Item>
          {(!isOverrideFlow || editingBudget) && (
            <Form.Item name="scope_id" hidden>
              <Input />
            </Form.Item>
          )}

          {isOverrideFlow && !editingBudget && (
            <>
              <Form.Item
                name="scope_id"
                label="User"
                rules={[{ required: true, message: "Select a user." }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={users.map((u: any) => ({
                    label: u.email ? `${u.name || "User"} (${u.email})` : (u.name || u.id),
                    value: u.id,
                  }))}
                />
              </Form.Item>
              <Form.Item
                name="parent_budget_id"
                label="Source Budget"
                rules={[{ required: true, message: "Select source budget." }]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={parentBudgetOptions.filter((o: any) => (
                    o.scope_type === "account" || o.scope_type === "group" || o.scope_type === "team"
                  ))}
                />
              </Form.Item>
              <Form.Item name="allocation_strategy" label="Override Mode" initialValue="override">
                <Select options={[{ label: "User Override", value: "override" }]} />
              </Form.Item>
            </>
          )}

          <Form.Item name="allocated" label="Allocated Credits">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="limit_amount" label="Limit Amount">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="overflow_cap" label="Overflow Cap">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          {!editingBudget && !isOverrideFlow && (
            <>
              <Form.Item name="cycle_start" label="Cycle Start" rules={[{ required: true }]}>
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="cycle_end" label="Cycle End" rules={[{ required: true }]}>
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </>
          )}
        </Form>
      </Drawer>

      <Modal
        title={`Allocate from ${selectedParentBudget ? `${scopeLabelByType[selectedParentBudget.scope_type] || selectedParentBudget.scope_type}` : "Parent"} Budget`}
        open={allocationModalOpen}
        onOk={handleAllocationSave}
        onCancel={() => {
          setAllocationModalOpen(false);
          setSelectedParentBudget(null);
        }}
        confirmLoading={allocateBudget.isPending}
      >
        <Form form={allocationForm} layout="vertical">
          <Form.Item name="target_scope_type" label="Target Scope" rules={[{ required: true }]}>
            <Select options={allocationTargetScopeOptions} />
          </Form.Item>
          <Form.Item name="target_scope_id" label="Target Entity" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={allocationTargetEntityOptions} />
          </Form.Item>
          <Form.Item name="allocated" label="Allocated Credits" rules={[{ required: true }]}>
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="limit_amount" label="Limit Amount">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="overflow_cap" label="Overflow Cap">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="allocation_strategy" label="Strategy" initialValue="manual">
            <Select
              options={[
                { label: "Manual", value: "manual" },
                { label: "Override", value: "override" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Distribute Equally to Users"
        open={distributeModalOpen}
        onOk={handleDistributeEqual}
        onCancel={() => {
          setDistributeModalOpen(false);
          setSelectedParentBudget(null);
        }}
        confirmLoading={distributeEqual.isPending}
      >
        <Form form={distributeForm} layout="vertical">
          <Form.Item name="target_scope_type" initialValue="user" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            name="include_override_users"
            label="Include existing override users in equal distribution"
            initialValue={false}
          >
            <Select options={[{ label: "No (keep overrides fixed)", value: false }, { label: "Yes", value: true }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingPlan ? "Edit Plan" : "Create Plan"}
        open={planModalOpen}
        onOk={handlePlanCreateOrUpdate}
        onCancel={() => { setPlanModalOpen(false); setEditingPlan(null); }}
        confirmLoading={createPlan.isPending || updatePlan.isPending}
      >
        <Form form={planForm} layout="vertical">
          <Form.Item name="name" label="Plan Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="is_active" label="Active" initialValue={true}>
            <Select options={[{ label: "Active", value: true }, { label: "Inactive", value: false }]} />
          </Form.Item>
          <Form.Item name="distribution_mode" label="Distribution Mode" initialValue="manual">
            <Select
              options={[
                { label: "Manual", value: "manual" },
                { label: "Equal Distribution", value: "equal_distribution" },
                { label: "Weighted", value: "weighted" },
              ]}
            />
          </Form.Item>
          <Form.Item name="default_target_scope" label="Default Allocation Target" initialValue="organization">
            <Select
              options={[
                { label: "Organization", value: "organization" },
                { label: "Team", value: "team" },
                { label: "User", value: "user" },
              ]}
            />
          </Form.Item>
          <Form.Item name="auto_distribute_new_users" label="Auto-distribute to new users" initialValue={false}>
            <Select options={[{ label: "No", value: false }, { label: "Yes", value: true }]} />
          </Form.Item>
          <Form.Item name="lock_user_overrides" label="Lock user overrides on distribute" initialValue={false}>
            <Select options={[{ label: "No", value: false }, { label: "Yes", value: true }]} />
          </Form.Item>
          {selectedPlanMode === "weighted" && (
            <Row gutter={8}>
              <Col span={8}>
                <Form.Item name="group_weight" label="Org Weight" initialValue={50}>
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="team_weight" label="Team Weight" initialValue={30}>
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="user_weight" label="User Weight" initialValue={20}>
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>
          )}
          <Form.Item name="notes" label="Plan Notes">
            <Input.TextArea rows={3} placeholder="Document plan intent and usage." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotBudgetsPage;
