"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import { Tabs, Modal, Form, Input, InputNumber, Select, Tag, Button, Space, message } from "antd";
import { ShopOutlined, CheckCircleOutlined, EyeInvisibleOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import { marketplaceApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

const ENTITY_TYPE_COLORS: Record<string, string> = { AGENT: "blue", MCP: "green", OPENAPI: "orange" };
const STATUS_COLORS: Record<string, string> = { draft: "default", pending: "processing", published: "success", rejected: "error" };
const PRICING_COLORS: Record<string, string> = { free: "green", paid: "gold", freemium: "cyan" };

export default function CopilotMarketplacePage() {
  const { accessToken } = useAuthorized();

  // --- Listings ---
  const [listings, setListings] = useState<any[]>([]);
  const [listingsLoading, setListingsLoading] = useState(false);
  const [listingModal, setListingModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [listingForm] = Form.useForm();

  // --- Assignments ---
  const [assignments, setAssignments] = useState<any[]>([]);
  const [assignmentsLoading, setAssignmentsLoading] = useState(false);
  const [assignmentModal, setAssignmentModal] = useState<{ open: boolean; editing: any | null }>({ open: false, editing: null });
  const [assignmentForm] = Form.useForm();

  // --- Loaders ---
  const loadListings = useCallback(async () => {
    if (!accessToken) return;
    setListingsLoading(true);
    try { const d = await marketplaceApi.listListings(accessToken); setListings(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load listings"); }
    finally { setListingsLoading(false); }
  }, [accessToken]);

  const loadAssignments = useCallback(async () => {
    if (!accessToken) return;
    setAssignmentsLoading(true);
    try { const d = await marketplaceApi.listAssignments(accessToken); setAssignments(Array.isArray(d) ? d : []); }
    catch (e: any) { message.error(e?.message ?? "Failed to load assignments"); }
    finally { setAssignmentsLoading(false); }
  }, [accessToken]);

  useEffect(() => { loadListings(); loadAssignments(); }, [loadListings, loadAssignments]);

  const handleRefresh = () => { loadListings(); loadAssignments(); };

  // --- Derived stats ---
  const publishedCount = useMemo(() => listings.filter((l) => l.status === "published").length, [listings]);
  const draftCount = useMemo(() => listings.filter((l) => l.status === "draft").length, [listings]);

  // --- Listing title lookup for assignments ---
  const listingTitleMap = useMemo(() => {
    const map: Record<string, string> = {};
    listings.forEach((l) => { map[l.listing_id] = l.title ?? l.listing_id; });
    return map;
  }, [listings]);

  // Published listings for the assignment form select
  const publishedListings = useMemo(() => listings.filter((l) => l.status === "published"), [listings]);

  // --- Listing Save ---
  const handleListingSave = async () => {
    if (!accessToken) return;
    try {
      const values = await listingForm.validateFields();
      if (listingModal.editing) {
        await marketplaceApi.updateListing(accessToken, listingModal.editing.listing_id, values);
        message.success("Listing updated");
      } else {
        await marketplaceApi.createListing(accessToken, values);
        message.success("Listing created");
      }
      setListingModal({ open: false, editing: null });
      listingForm.resetFields();
      loadListings();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  // --- Publish / Hide ---
  const handlePublish = async (record: any) => {
    if (!accessToken) return;
    try {
      await marketplaceApi.publishListing(accessToken, record.listing_id);
      message.success("Listing published");
      loadListings();
    } catch (e: any) { message.error(e?.message ?? "Publish failed"); }
  };

  const handleHide = async (record: any) => {
    if (!accessToken) return;
    try {
      await marketplaceApi.hideListing(accessToken, record.listing_id);
      message.success("Listing hidden");
      loadListings();
    } catch (e: any) { message.error(e?.message ?? "Hide failed"); }
  };

  // --- Assignment Save ---
  const handleAssignmentSave = async () => {
    if (!accessToken) return;
    try {
      const values = await assignmentForm.validateFields();
      await marketplaceApi.createAssignment(accessToken, values);
      message.success("Assignment created");
      setAssignmentModal({ open: false, editing: null });
      assignmentForm.resetFields();
      loadAssignments();
    } catch (e: any) { if (e?.errorFields) return; message.error(e?.message ?? "Save failed"); }
  };

  // --- Form watchers ---
  const pricingModel = Form.useWatch("pricing_model", listingForm);

  return (
    <CopilotPageShell title="Marketplace" subtitle="Manage marketplace listings and assignments." icon={<ShopOutlined />} onRefresh={handleRefresh}>
      <CopilotStatsRow stats={[
        { title: "Total Listings", value: listings.length, loading: listingsLoading },
        { title: "Published", value: publishedCount, loading: listingsLoading },
        { title: "Draft", value: draftCount, loading: listingsLoading },
        { title: "Assignments", value: assignments.length, loading: assignmentsLoading },
      ]} />
      <Tabs defaultActiveKey="listings" items={[
        { key: "listings", label: `Listings (${listings.length})`, children: (
          <>
            <CopilotCrudTable dataSource={listings} rowKey="listing_id" loading={listingsLoading}
              searchFields={["listing_id", "title", "entity_type", "entity_id", "pricing_model", "status"]}
              addLabel="Add Listing"
              onAdd={() => { listingForm.resetFields(); setListingModal({ open: true, editing: null }); }}
              onEdit={(r) => { listingForm.setFieldsValue(r); setListingModal({ open: true, editing: r }); }}
              onDelete={async (r) => { if (accessToken) { await marketplaceApi.deleteListing(accessToken, r.listing_id); loadListings(); } }}
              columns={[
                { title: "Listing ID", dataIndex: "listing_id", key: "listing_id", ellipsis: true, width: 200 },
                { title: "Title", dataIndex: "title", key: "title" },
                { title: "Entity Type", dataIndex: "entity_type", key: "entity_type", render: (v: string) => <Tag color={ENTITY_TYPE_COLORS[v] ?? "default"}>{v}</Tag> },
                { title: "Entity ID", dataIndex: "entity_id", key: "entity_id", ellipsis: true },
                { title: "Pricing", dataIndex: "pricing_model", key: "pricing_model", render: (v: string) => <Tag color={PRICING_COLORS[v] ?? "default"}>{v}</Tag> },
                { title: "Status", dataIndex: "status", key: "status", render: (v: string) => <Tag color={STATUS_COLORS[v] ?? "default"}>{v}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "\u2014" },
                { title: "Publish / Hide", key: "_publish_hide", width: 180, render: (_: unknown, r: any) => (
                  <Space>
                    {r.status !== "published" && (
                      <Button type="link" size="small" icon={<CheckCircleOutlined />} onClick={() => handlePublish(r)}>Publish</Button>
                    )}
                    {r.status === "published" && (
                      <Button type="link" size="small" danger icon={<EyeInvisibleOutlined />} onClick={() => handleHide(r)}>Hide</Button>
                    )}
                  </Space>
                )},
              ]}
            />
            <Modal title={listingModal.editing ? "Edit Listing" : "Add Listing"} open={listingModal.open} onOk={handleListingSave} onCancel={() => setListingModal({ open: false, editing: null })} width={600}>
              <Form form={listingForm} layout="vertical">
                <Form.Item name="title" label="Title" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="description" label="Description"><Input.TextArea rows={3} /></Form.Item>
                <Form.Item name="entity_type" label="Entity Type" rules={[{ required: true }]}>
                  <Select options={[{ value: "AGENT", label: "Agent" }, { value: "MCP", label: "MCP" }, { value: "OPENAPI", label: "OpenAPI" }]} />
                </Form.Item>
                <Form.Item name="entity_id" label="Entity ID" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="pricing_model" label="Pricing Model" rules={[{ required: true }]}>
                  <Select options={[{ value: "free", label: "Free" }, { value: "paid", label: "Paid" }, { value: "freemium", label: "Freemium" }]} />
                </Form.Item>
                {pricingModel === "paid" && (
                  <Form.Item name="price" label="Price" rules={[{ required: true }]}><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
                )}
                <Form.Item name="tags" label="Tags"><Select mode="tags" placeholder="Add tags" /></Form.Item>
              </Form>
            </Modal>
          </>
        )},
        { key: "assignments", label: `Assignments (${assignments.length})`, children: (
          <>
            <CopilotCrudTable dataSource={assignments} rowKey="assignment_id" loading={assignmentsLoading}
              searchFields={["assignment_id", "listing_id", "scope_type", "scope_id", "status"]}
              addLabel="Add Assignment"
              onAdd={() => { assignmentForm.resetFields(); setAssignmentModal({ open: true, editing: null }); }}
              onDelete={async (r) => { if (accessToken) { await marketplaceApi.deleteAssignment(accessToken, r.assignment_id); loadAssignments(); } }}
              showActions={true}
              columns={[
                { title: "Assignment ID", dataIndex: "assignment_id", key: "assignment_id", ellipsis: true, width: 200 },
                { title: "Listing", dataIndex: "listing_id", key: "listing_id", render: (v: string) => listingTitleMap[v] ?? v },
                { title: "Scope Type", dataIndex: "scope_type", key: "scope_type", render: (v: string) => <Tag color="blue">{v}</Tag> },
                { title: "Scope ID", dataIndex: "scope_id", key: "scope_id", ellipsis: true },
                { title: "Status", dataIndex: "status", key: "status", render: (v: string) => <Tag color={STATUS_COLORS[v] ?? "default"}>{v}</Tag> },
                { title: "Created", dataIndex: "created_at", key: "created_at", render: (v: string) => v ? new Date(v).toLocaleDateString() : "\u2014" },
              ]}
            />
            <Modal title="Add Assignment" open={assignmentModal.open} onOk={handleAssignmentSave} onCancel={() => setAssignmentModal({ open: false, editing: null })} width={500}>
              <Form form={assignmentForm} layout="vertical">
                <Form.Item name="listing_id" label="Listing" rules={[{ required: true }]}>
                  <Select placeholder="Select a published listing" options={publishedListings.map((l) => ({ value: l.listing_id, label: l.title ?? l.listing_id }))} />
                </Form.Item>
                <Form.Item name="scope_type" label="Scope Type" rules={[{ required: true }]}>
                  <Select options={[{ value: "ORG", label: "Organization" }, { value: "TEAM", label: "Team" }, { value: "USER", label: "User" }]} />
                </Form.Item>
                <Form.Item name="scope_id" label="Scope ID" rules={[{ required: true }]}><Input /></Form.Item>
              </Form>
            </Modal>
          </>
        )},
      ]} />
    </CopilotPageShell>
  );
}
