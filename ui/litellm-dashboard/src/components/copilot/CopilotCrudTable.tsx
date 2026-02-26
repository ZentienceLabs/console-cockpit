"use client";

import React, { useState, useMemo } from "react";
import { Table, Input, Button, Space, Popconfirm, message } from "antd";
import { PlusOutlined, SearchOutlined, DeleteOutlined, EditOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";

interface CopilotCrudTableProps<T extends Record<string, any>> {
  dataSource: T[];
  columns: ColumnsType<T>;
  rowKey: string;
  loading?: boolean;
  searchFields?: string[];
  onAdd?: () => void;
  onEdit?: (record: T) => void;
  onDelete?: (record: T) => Promise<void>;
  addLabel?: string;
  showActions?: boolean;
  extraActions?: React.ReactNode;
  expandable?: Record<string, any>;
}

function CopilotCrudTable<T extends Record<string, any>>({
  dataSource,
  columns,
  rowKey,
  loading = false,
  searchFields = [],
  onAdd,
  onEdit,
  onDelete,
  addLabel = "Add",
  showActions = true,
  extraActions,
  expandable,
}: CopilotCrudTableProps<T>) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search || searchFields.length === 0) return dataSource;
    const lower = search.toLowerCase();
    return dataSource.filter((row) =>
      searchFields.some((f) => String(row[f] ?? "").toLowerCase().includes(lower)),
    );
  }, [dataSource, search, searchFields]);

  const actionColumn: ColumnsType<T> = showActions && (onEdit || onDelete)
    ? [
        {
          title: "Actions",
          key: "_actions",
          width: 120,
          render: (_: unknown, record: T) => (
            <Space>
              {onEdit && (
                <Button type="link" size="small" icon={<EditOutlined />} onClick={() => onEdit(record)}>
                  Edit
                </Button>
              )}
              {onDelete && (
                <Popconfirm
                  title="Delete this item?"
                  onConfirm={async () => {
                    try {
                      await onDelete(record);
                      message.success("Deleted");
                    } catch (e: any) {
                      message.error(e?.message ?? "Delete failed");
                    }
                  }}
                >
                  <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                    Delete
                  </Button>
                </Popconfirm>
              )}
            </Space>
          ),
        },
      ]
    : [];

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          {searchFields.length > 0 && (
            <Input
              placeholder="Search..."
              prefix={<SearchOutlined />}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 260 }}
              allowClear
            />
          )}
          {extraActions}
        </Space>
        {onAdd && (
          <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>
            {addLabel}
          </Button>
        )}
      </div>
      <Table<T>
        dataSource={filtered}
        columns={[...columns, ...actionColumn]}
        rowKey={rowKey}
        loading={loading}
        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `${t} total` }}
        size="middle"
        scroll={{ x: "max-content" }}
        expandable={expandable}
      />
    </>
  );
}

export default CopilotCrudTable;
