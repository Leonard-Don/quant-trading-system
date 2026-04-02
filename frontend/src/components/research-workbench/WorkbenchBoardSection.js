import React from 'react';
import {
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { InboxOutlined } from '@ant-design/icons';

const { Search } = Input;
const { Text } = Typography;

const WorkbenchBoardSection = ({
  archivedTasks,
  boardColumns,
  dragState,
  filters,
  handleDrop,
  handleRestoreArchived,
  loading,
  renderBoardCard,
  saving,
  setDragState,
  setFilters,
  setSelectedTaskId,
  setShowArchived,
  showArchived,
  sourceOptions,
  TYPE_OPTIONS,
  REFRESH_OPTIONS,
  REASON_OPTIONS,
}) => (
  <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Card
      bordered={false}
      title="看板工具条"
      extra={dragState?.taskId ? <Tag color="processing">拖拽中</Tag> : null}
    >
      <Space wrap style={{ width: '100%' }}>
        <Select
          value={filters.type}
          options={TYPE_OPTIONS}
          onChange={(value) => setFilters((prev) => ({ ...prev, type: value }))}
          style={{ width: 160 }}
        />
        <Select
          value={filters.source}
          options={sourceOptions}
          onChange={(value) => setFilters((prev) => ({ ...prev, source: value }))}
          style={{ width: 180 }}
        />
        <Select
          value={filters.refresh}
          options={REFRESH_OPTIONS}
          onChange={(value) => setFilters((prev) => ({ ...prev, refresh: value }))}
          style={{ width: 180 }}
        />
        <Select
          value={filters.reason}
          options={REASON_OPTIONS}
          onChange={(value) => setFilters((prev) => ({ ...prev, reason: value }))}
          style={{ width: 180 }}
        />
        <Search
          placeholder="搜索标题、symbol、template 或快照"
          allowClear
          value={filters.keyword}
          onChange={(event) => setFilters((prev) => ({ ...prev, keyword: event.target.value }))}
          style={{ width: 280 }}
        />
      </Space>
    </Card>

    {loading ? (
      <Card bordered={false}>
        <div style={{ minHeight: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Spin />
        </div>
      </Card>
    ) : (
      <Row gutter={[16, 16]}>
        {boardColumns.map((column) => (
          <Col xs={24} md={12} xl={6} key={column.status}>
            <Card
              bordered={false}
              title={(
                <Space wrap>
                  <span>{column.title}</span>
                  <Tag>{column.tasks.length}</Tag>
                </Space>
              )}
              bodyStyle={{ minHeight: 340 }}
              onDragOver={(event) => {
                event.preventDefault();
                setDragState((current) => (
                  current ? { ...current, overTaskId: null, overStatus: column.status } : current
                ));
              }}
              onDrop={(event) => {
                event.preventDefault();
                handleDrop(column.status);
              }}
              style={{
                border:
                  dragState?.overStatus === column.status && !dragState?.overTaskId
                    ? '1px dashed rgba(24,144,255,0.6)'
                    : undefined,
              }}
            >
              {column.tasks.length ? (
                column.tasks.map((task) => renderBoardCard(task, column.status))
              ) : (
                <Empty description={`${column.title}暂无任务`} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </Col>
        ))}
      </Row>
    )}

    <Card
      bordered={false}
      title={(
        <Space>
          <InboxOutlined />
          <span>Archived 收纳区</span>
          <Tag>{archivedTasks.length}</Tag>
        </Space>
      )}
      extra={(
        <Button type="link" onClick={() => setShowArchived((prev) => !prev)}>
          {showArchived ? '收起' : '展开'}
        </Button>
      )}
    >
      {showArchived ? (
        archivedTasks.length ? (
          <List
            dataSource={archivedTasks}
            renderItem={(task) => (
              <List.Item
                actions={[
                  <Button
                    key="restore"
                    size="small"
                    onClick={() => handleRestoreArchived(task.id)}
                    loading={saving}
                  >
                    恢复到新建
                  </Button>,
                ]}
                onClick={() => setSelectedTaskId(task.id)}
                style={{ cursor: 'pointer' }}
              >
                <List.Item.Meta
                  title={(
                    <Space wrap>
                      <Text strong>{task.title}</Text>
                      <Tag color="default">archived</Tag>
                    </Space>
                  )}
                  description={`${task.snapshot?.headline || '暂无摘要'} · ${new Date(task.updated_at).toLocaleString()}`}
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty description="当前没有归档任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )
      ) : (
        <Text type="secondary">归档任务默认收起，避免占用主看板空间。</Text>
      )}
    </Card>
  </Space>
);

export default WorkbenchBoardSection;
