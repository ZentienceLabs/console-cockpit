import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Space, Tag, Typography } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  copilotMarketplaceList,
  copilotMarketplaceCreate,
  copilotMarketplaceUpdate,
  copilotMarketplaceDelete,
} from "../networking";
import NotificationsManager from "../molecules/notifications_manager";

const { TextArea } = Input;
const { Title } = Typography;

interface MarketplaceListing {
  id: string;
  agent_id?: string;
  listing_status?: string;
  listing_data?: any;
  account_id?: string;
  created_at?: string;
  updated_at?: string;
}

interface CopilotMarketplaceProps {
  accessToken: string | null;
  userRole?: string;
  userID?: string | null;
}

const CopilotMarketplace: React.FC<CopilotMarketplaceProps> = ({ accessToken }) => {
  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingListing, setEditingListing] = useState<MarketplaceListing | null>(null);
  const [form] = Form.useForm();

  const fetchListings = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const data = await copilotMarketplaceList(accessToken);
      setListings(data.listings || data || []);
    } catch (error) {
      console.error("Error fetching marketplace listings:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchListings();
  }, [accessToken]);

  const handleCreate = () => {
    setEditingListing(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (listing: MarketplaceListing) => {
    setEditingListing(listing);
    form.setFieldsValue({
      agent_id: listing.agent_id,
      listing_status: listing.listing_status || "DRAFT",
      listing_data: listing.listing_data ? JSON.stringify(listing.listing_data, null, 2) : "",
    });
    setModalVisible(true);
  };

  const handleDelete = async (listingId: string) => {
    if (!accessToken) return;
    Modal.confirm({
      title: "Delete this listing?",
      content: "This action cannot be undone.",
      okText: "Delete",
      okType: "danger",
      onOk: async () => {
        try {
          await copilotMarketplaceDelete(accessToken, listingId);
          NotificationsManager.success("Listing deleted");
          fetchListings();
        } catch (error) {
          console.error("Error deleting listing:", error);
        }
      },
    });
  };

  const handleSubmit = async () => {
    if (!accessToken) return;
    try {
      const values = await form.validateFields();
      const payload: any = {
        agent_id: values.agent_id,
        listing_status: values.listing_status,
      };
      if (values.listing_data) {
        try {
          payload.listing_data = JSON.parse(values.listing_data);
        } catch {
          NotificationsManager.error("Listing data must be valid JSON");
          return;
        }
      }

      if (editingListing) {
        await copilotMarketplaceUpdate(accessToken, editingListing.id, payload);
        NotificationsManager.success("Listing updated");
      } else {
        await copilotMarketplaceCreate(accessToken, payload);
        NotificationsManager.success("Listing created");
      }
      setModalVisible(false);
      fetchListings();
    } catch (error) {
      console.error("Error saving listing:", error);
    }
  };

  const columns = [
    {
      title: "Agent ID",
      dataIndex: "agent_id",
      key: "agent_id",
      render: (text: string) => <span className="font-mono text-xs">{text || "-"}</span>,
    },
    {
      title: "Status",
      dataIndex: "listing_status",
      key: "listing_status",
      render: (status: string) => (
        <Tag color={status === "PUBLISHED" ? "green" : status === "DRAFT" ? "orange" : "default"}>
          {status || "DRAFT"}
        </Tag>
      ),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (text: string) => text ? new Date(text).toLocaleDateString() : "-",
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, record: MarketplaceListing) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Button type="link" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)} />
        </Space>
      ),
    },
  ];

  return (
    <div className="w-full mx-auto max-w-[1200px] p-6">
      <div className="flex justify-between items-center mb-4">
        <Title level={4} className="mb-0">Marketplace Listings</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchListings} loading={loading}>Refresh</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>Add Listing</Button>
        </Space>
      </div>

      <Table
        dataSource={listings}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        size="small"
      />

      <Modal
        title={editingListing ? "Edit Listing" : "Create Listing"}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        okText={editingListing ? "Update" : "Create"}
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="agent_id" label="Agent ID" rules={[{ required: true }]}>
            <Input placeholder="Agent ID to list" />
          </Form.Item>
          <Form.Item name="listing_status" label="Status" initialValue="DRAFT">
            <Select options={[
              { value: "DRAFT", label: "Draft" },
              { value: "PUBLISHED", label: "Published" },
              { value: "UNLISTED", label: "Unlisted" },
            ]} />
          </Form.Item>
          <Form.Item name="listing_data" label="Listing Data (JSON)">
            <TextArea rows={4} placeholder='{"title": "My Agent", "description": "..."}' />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CopilotMarketplace;
