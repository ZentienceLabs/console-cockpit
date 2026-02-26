"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  Tabs,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Button,
  Space,
  Drawer,
  Typography,
  Divider,
  Timeline,
  message,
} from "antd";
import { CustomerServiceOutlined, SendOutlined } from "@ant-design/icons";
import CopilotPageShell from "@/components/copilot/CopilotPageShell";
import CopilotCrudTable from "@/components/copilot/CopilotCrudTable";
import CopilotStatsRow from "@/components/copilot/CopilotStatsRow";
import { supportApi } from "@/lib/copilotApi";
import useAuthorized from "@/app/(dashboard)/hooks/useAuthorized";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

// ---------------------------------------------------------------------------
// Color maps
// ---------------------------------------------------------------------------
const priorityColors: Record<string, string> = {
  low: "default",
  medium: "blue",
  high: "orange",
  critical: "red",
};

const statusColors: Record<string, string> = {
  open: "blue",
  in_progress: "orange",
  pending: "gold",
  resolved: "green",
  closed: "default",
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------
export default function CopilotSupportPage() {
  const { accessToken } = useAuthorized();

  // Tickets state
  const [tickets, setTickets] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Create modal state
  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm();

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [comments, setComments] = useState<any[]>([]);
  const [commentText, setCommentText] = useState("");
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);

  // -------------------------------------------------------------------------
  // Data loading
  // -------------------------------------------------------------------------
  const loadTickets = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const d = await supportApi.listTickets(accessToken);
      setTickets(Array.isArray(d) ? d : []);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to load tickets");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  const loadTicketDetail = useCallback(
    async (ticketId: string) => {
      if (!accessToken) return;
      setDetailLoading(true);
      try {
        const detail: any = await supportApi.getTicket(accessToken, ticketId);
        setSelectedTicket(detail);
        setComments(Array.isArray(detail?.comments) ? detail.comments : []);
      } catch (e: any) {
        message.error(e?.message ?? "Failed to load ticket details");
      } finally {
        setDetailLoading(false);
      }
    },
    [accessToken],
  );

  // -------------------------------------------------------------------------
  // Derived stats
  // -------------------------------------------------------------------------
  const stats = useMemo(() => {
    const total = tickets.length;
    const open = tickets.filter((t) => t.status === "open").length;
    const inProgress = tickets.filter((t) => t.status === "in_progress").length;
    const closed = tickets.filter((t) => t.status === "closed").length;
    return { total, open, inProgress, closed };
  }, [tickets]);

  const openTickets = useMemo(
    () => tickets.filter((t) => t.status !== "closed" && t.status !== "resolved"),
    [tickets],
  );

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------
  const handleCreate = async () => {
    if (!accessToken) return;
    try {
      const values = await createForm.validateFields();
      await supportApi.createTicket(accessToken, values);
      message.success("Ticket created");
      setCreateModal(false);
      createForm.resetFields();
      loadTickets();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e?.message ?? "Failed to create ticket");
    }
  };

  const handleRowClick = (record: any) => {
    setSelectedTicket(record);
    setComments(Array.isArray(record?.comments) ? record.comments : []);
    setCommentText("");
    setDrawerOpen(true);
    loadTicketDetail(record.ticket_id);
  };

  const handleAddComment = async () => {
    if (!accessToken || !selectedTicket || !commentText.trim()) return;
    setCommentSubmitting(true);
    try {
      await supportApi.addComment(accessToken, selectedTicket.ticket_id, {
        content: commentText.trim(),
      });
      message.success("Comment added");
      setCommentText("");
      await loadTicketDetail(selectedTicket.ticket_id);
    } catch (e: any) {
      message.error(e?.message ?? "Failed to add comment");
    } finally {
      setCommentSubmitting(false);
    }
  };

  const handleStatusChange = async (newStatus: string) => {
    if (!accessToken || !selectedTicket) return;
    setStatusUpdating(true);
    try {
      await supportApi.updateTicket(accessToken, selectedTicket.ticket_id, {
        status: newStatus,
      });
      message.success("Status updated");
      setSelectedTicket((prev: any) => (prev ? { ...prev, status: newStatus } : prev));
      loadTickets();
    } catch (e: any) {
      message.error(e?.message ?? "Failed to update status");
    } finally {
      setStatusUpdating(false);
    }
  };

  const handleCloseTicket = async () => {
    if (!accessToken || !selectedTicket) return;
    try {
      await supportApi.closeTicket(accessToken, selectedTicket.ticket_id);
      message.success("Ticket closed");
      setSelectedTicket((prev: any) => (prev ? { ...prev, status: "closed" } : prev));
      loadTickets();
    } catch (e: any) {
      message.error(e?.message ?? "Failed to close ticket");
    }
  };

  const handleDrawerClose = () => {
    setDrawerOpen(false);
    setSelectedTicket(null);
    setComments([]);
    setCommentText("");
  };

  // -------------------------------------------------------------------------
  // Table columns
  // -------------------------------------------------------------------------
  const columns = [
    {
      title: "Ticket ID",
      dataIndex: "ticket_id",
      key: "ticket_id",
      width: 120,
      ellipsis: true,
      render: (v: string, record: any) => (
        <Button type="link" size="small" onClick={() => handleRowClick(record)} style={{ padding: 0 }}>
          {v}
        </Button>
      ),
    },
    {
      title: "Subject",
      dataIndex: "subject",
      key: "subject",
      ellipsis: true,
      render: (v: string, record: any) => (
        <Button type="link" size="small" onClick={() => handleRowClick(record)} style={{ padding: 0 }}>
          {v}
        </Button>
      ),
    },
    {
      title: "Category",
      dataIndex: "category",
      key: "category",
      width: 130,
      render: (v: string) => (v ? <Tag>{v}</Tag> : "—"),
    },
    {
      title: "Priority",
      dataIndex: "priority",
      key: "priority",
      width: 100,
      render: (v: string) => (
        <Tag color={priorityColors[v] ?? "default"}>{v ?? "medium"}</Tag>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (v: string) => (
        <Tag color={statusColors[v] ?? "default"}>{v ?? "open"}</Tag>
      ),
    },
    {
      title: "Created By",
      dataIndex: "created_by",
      key: "created_by",
      ellipsis: true,
    },
    {
      title: "Assignee",
      dataIndex: "assignee",
      key: "assignee",
      ellipsis: true,
      render: (v: string) => v || "—",
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      width: 170,
      render: (v: string) => (v ? new Date(v).toLocaleString() : "—"),
    },
    {
      title: "Updated",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (v: string) => (v ? new Date(v).toLocaleString() : "—"),
    },
  ];

  // -------------------------------------------------------------------------
  // Table builder for both tabs
  // -------------------------------------------------------------------------
  const renderTable = (data: any[]) => (
    <CopilotCrudTable
      dataSource={data}
      rowKey="ticket_id"
      loading={loading}
      searchFields={["ticket_id", "subject", "category", "priority", "status", "created_by", "assignee"]}
      addLabel="Create Ticket"
      onAdd={() => {
        createForm.resetFields();
        setCreateModal(true);
      }}
      showActions={false}
      columns={columns}
    />
  );

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <CopilotPageShell
      title="Support"
      subtitle="Manage support tickets and response tracking."
      icon={<CustomerServiceOutlined />}
      onRefresh={loadTickets}
    >
      {/* Stats row */}
      <CopilotStatsRow
        stats={[
          { title: "Total Tickets", value: stats.total, loading },
          { title: "Open", value: stats.open, loading },
          { title: "In Progress", value: stats.inProgress, loading },
          { title: "Closed", value: stats.closed, loading },
        ]}
      />

      {/* Tabs: Open Tickets / All Tickets */}
      <Tabs
        defaultActiveKey="open"
        items={[
          {
            key: "open",
            label: `Open Tickets (${openTickets.length})`,
            children: renderTable(openTickets),
          },
          {
            key: "all",
            label: `All Tickets (${tickets.length})`,
            children: renderTable(tickets),
          },
        ]}
      />

      {/* Create Ticket Modal */}
      <Modal
        title="Create Ticket"
        open={createModal}
        onOk={handleCreate}
        onCancel={() => setCreateModal(false)}
        width={600}
        okText="Create"
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="subject"
            label="Subject"
            rules={[{ required: true, message: "Subject is required" }]}
          >
            <Input placeholder="Brief summary of the issue" />
          </Form.Item>
          <Form.Item
            name="description"
            label="Description"
            rules={[{ required: true, message: "Description is required" }]}
          >
            <TextArea rows={4} placeholder="Describe your issue in detail" />
          </Form.Item>
          <Form.Item name="category" label="Category" initialValue="question">
            <Select
              options={[
                { value: "bug", label: "Bug" },
                { value: "feature_request", label: "Feature Request" },
                { value: "question", label: "Question" },
                { value: "other", label: "Other" },
              ]}
            />
          </Form.Item>
          <Form.Item name="priority" label="Priority" initialValue="medium">
            <Select
              options={[
                { value: "low", label: "Low" },
                { value: "medium", label: "Medium" },
                { value: "high", label: "High" },
                { value: "critical", label: "Critical" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Ticket Detail Drawer */}
      <Drawer
        title={selectedTicket ? `Ticket: ${selectedTicket.subject}` : "Ticket Details"}
        placement="right"
        width={640}
        open={drawerOpen}
        onClose={handleDrawerClose}
        extra={
          selectedTicket && selectedTicket.status !== "closed" ? (
            <Button danger onClick={handleCloseTicket}>
              Close Ticket
            </Button>
          ) : null
        }
      >
        {selectedTicket && (
          <div>
            {/* Ticket metadata */}
            <Space direction="vertical" size="small" style={{ width: "100%", marginBottom: 16 }}>
              <div>
                <Text type="secondary">Ticket ID: </Text>
                <Text copyable>{selectedTicket.ticket_id}</Text>
              </div>
              <div>
                <Text type="secondary">Status: </Text>
                <Select
                  value={selectedTicket.status}
                  onChange={handleStatusChange}
                  loading={statusUpdating}
                  style={{ minWidth: 140 }}
                  options={[
                    { value: "open", label: "Open" },
                    { value: "in_progress", label: "In Progress" },
                    { value: "pending", label: "Pending" },
                    { value: "resolved", label: "Resolved" },
                    { value: "closed", label: "Closed" },
                  ]}
                />
              </div>
              <div>
                <Text type="secondary">Priority: </Text>
                <Tag color={priorityColors[selectedTicket.priority] ?? "default"}>
                  {selectedTicket.priority ?? "medium"}
                </Tag>
              </div>
              <div>
                <Text type="secondary">Category: </Text>
                <Tag>{selectedTicket.category ?? "—"}</Tag>
              </div>
              <div>
                <Text type="secondary">Created By: </Text>
                <Text>{selectedTicket.created_by ?? "—"}</Text>
              </div>
              <div>
                <Text type="secondary">Assignee: </Text>
                <Text>{selectedTicket.assignee ?? "Unassigned"}</Text>
              </div>
              <div>
                <Text type="secondary">Created: </Text>
                <Text>
                  {selectedTicket.created_at
                    ? new Date(selectedTicket.created_at).toLocaleString()
                    : "—"}
                </Text>
              </div>
              <div>
                <Text type="secondary">Updated: </Text>
                <Text>
                  {selectedTicket.updated_at
                    ? new Date(selectedTicket.updated_at).toLocaleString()
                    : "—"}
                </Text>
              </div>
            </Space>

            <Divider orientation="left">Description</Divider>
            <Paragraph style={{ whiteSpace: "pre-wrap" }}>
              {selectedTicket.description || "No description provided."}
            </Paragraph>

            <Divider orientation="left">Comments ({comments.length})</Divider>

            {comments.length > 0 ? (
              <Timeline
                items={comments.map((c: any, idx: number) => ({
                  key: c.comment_id ?? idx,
                  children: (
                    <div>
                      <div style={{ marginBottom: 4 }}>
                        <Text strong>{c.author ?? c.created_by ?? "Unknown"}</Text>
                        <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                          {c.created_at ? new Date(c.created_at).toLocaleString() : ""}
                        </Text>
                      </div>
                      <Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                        {c.content ?? c.body ?? c.text ?? ""}
                      </Paragraph>
                    </div>
                  ),
                }))}
              />
            ) : (
              <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
                No comments yet.
              </Text>
            )}

            {/* Add comment */}
            <div style={{ marginTop: 16 }}>
              <TextArea
                rows={3}
                placeholder="Add a comment..."
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                disabled={commentSubmitting}
              />
              <div style={{ marginTop: 8, textAlign: "right" }}>
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={handleAddComment}
                  loading={commentSubmitting}
                  disabled={!commentText.trim()}
                >
                  Submit Comment
                </Button>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </CopilotPageShell>
  );
}
