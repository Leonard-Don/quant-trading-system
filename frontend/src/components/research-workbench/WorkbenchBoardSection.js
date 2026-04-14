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
import { buildActiveWorkbenchFilterMeta, extractLatestRefreshPriorityEvent } from './workbenchUtils';

const { Search } = Input;
const { Text } = Typography;

const QUICK_PRIORITY_FILTERS = [
  { reason: 'priority_new', label: '首次', fullLabel: '自动排序首次入列', color: 'blue' },
  { reason: 'priority_escalated', label: '升档', fullLabel: '自动排序升档', color: 'red' },
  { reason: 'priority_relaxed', label: '缓和', fullLabel: '自动排序缓和', color: 'green' },
  { reason: 'priority_updated', label: '更新', fullLabel: '自动排序同类更新', color: 'gold' },
];

const PRIORITY_CHANGE_TO_REASON = {
  new: 'priority_new',
  escalated: 'priority_escalated',
  relaxed: 'priority_relaxed',
  updated: 'priority_updated',
};

const WorkbenchBoardSection = ({
  archivedTasks,
  boardColumns,
  dragState,
  filters,
  handleDrop,
  onCopyViewLink,
  handleRestoreArchived,
  loading,
  renderBoardCard,
  refreshStats,
  saving,
  setDragState,
  setFilters,
  setSelectedTaskId,
  setShowArchived,
  showArchived,
  snapshotSummaryOptions,
  sourceOptions,
  TYPE_OPTIONS,
  REFRESH_OPTIONS,
  SNAPSHOT_VIEW_OPTIONS,
  REASON_OPTIONS,
}) => {
  const activeQuickFilter = QUICK_PRIORITY_FILTERS.find((item) => item.reason === filters.reason) || null;
  const activeFilterMeta = buildActiveWorkbenchFilterMeta(filters, {
    reasonOptions: REASON_OPTIONS,
    refreshOptions: REFRESH_OPTIONS,
    snapshotViewOptions: SNAPSHOT_VIEW_OPTIONS,
    sourceOptions,
    typeOptions: TYPE_OPTIONS,
  });
  const quickFilterCounts = {
    priority_new: refreshStats?.priorityNew || 0,
    priority_escalated: refreshStats?.priorityEscalated || 0,
    priority_relaxed: refreshStats?.priorityRelaxed || 0,
    priority_updated: refreshStats?.priorityUpdated || 0,
  };
  const snapshotSummarySelectOptions = [
    { label: '全部研究视角', value: '' },
    ...(filters.snapshotSummary && !(snapshotSummaryOptions || []).some((item) => item.value === filters.snapshotSummary)
      ? [{ label: filters.snapshotSummary, value: filters.snapshotSummary, fingerprint: filters.snapshotFingerprint || '' }]
      : []
    ),
    ...((snapshotSummaryOptions || []).map((item) => ({
      label: item.label,
      value: item.value,
    }))),
  ];

  const toggleReasonFilter = (reason) => {
    setFilters((prev) => ({
      ...prev,
      reason: prev.reason === reason ? '' : reason,
    }));
  };

  const clearAllFilters = () => {
    setFilters((prev) => ({
      ...prev,
      type: '',
      source: '',
      refresh: '',
      reason: '',
      snapshotView: '',
      snapshotFingerprint: '',
      snapshotSummary: '',
      keyword: '',
    }));
  };

  const clearFilterField = (field) => {
    if (!field) {
      return;
    }
    setFilters((prev) => ({
      ...prev,
      [field]: '',
    }));
  };

  const buildColumnPriorityCounts = (tasks = []) => tasks.reduce((accumulator, task) => {
    const changeType = extractLatestRefreshPriorityEvent(task)?.meta?.change_type;
    if (changeType && accumulator[changeType] !== undefined) {
      accumulator[changeType] += 1;
    }
    return accumulator;
  }, {
    new: 0,
    escalated: 0,
    relaxed: 0,
    updated: 0,
  });

  const renderColumnPriorityTag = (columnStatus, changeType, color, label, count) => {
    const reason = PRIORITY_CHANGE_TO_REASON[changeType];
    const isActive = filters.reason === reason;

    return (
      <Tag
        data-testid={`workbench-column-priority-${columnStatus}-${changeType}`}
        color={color}
        onClick={() => toggleReasonFilter(reason)}
        style={{
          cursor: 'pointer',
          borderStyle: isActive ? 'solid' : 'dashed',
          fontWeight: isActive ? 600 : 400,
        }}
      >
        {label} {count}
      </Tag>
    );
  };

  return (
  <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Card
      variant="borderless"
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
        <Select
          value={filters.snapshotView}
          options={SNAPSHOT_VIEW_OPTIONS}
          onChange={(value) => setFilters((prev) => ({ ...prev, snapshotView: value }))}
          style={{ width: 190 }}
        />
        <Select
          value={filters.snapshotSummary}
          options={snapshotSummarySelectOptions}
          onChange={(value) => {
            const matchedOption = snapshotSummarySelectOptions.find((item) => item.value === value);
            setFilters((prev) => ({
              ...prev,
              snapshotSummary: value,
              snapshotFingerprint: matchedOption?.fingerprint || '',
            }));
          }}
          style={{ width: 320 }}
        />
        <Search
          placeholder="搜索标题、symbol、template 或快照"
          allowClear
          value={filters.keyword}
          onChange={(event) => setFilters((prev) => ({ ...prev, keyword: event.target.value }))}
          style={{ width: 280 }}
        />
      </Space>
      <Space wrap style={{ width: '100%', marginTop: 12 }}>
        {QUICK_PRIORITY_FILTERS.map((item) => (
          <Button
            key={item.reason}
            size="small"
            type={filters.reason === item.reason ? 'primary' : 'default'}
            danger={item.reason === 'priority_escalated' && filters.reason === item.reason}
            onClick={() => toggleReasonFilter(item.reason)}
          >
            {item.label} {quickFilterCounts[item.reason]}
          </Button>
        ))}
        {activeFilterMeta.length ? (
          <>
            {activeFilterMeta.map((item) => (
              <Tag
                key={item.field}
                color={item.color}
                closable
                closeIcon={<span data-testid={`board-filter-close-${item.field}`}>×</span>}
                onClose={(event) => {
                  event.preventDefault();
                  clearFilterField(item.field);
                }}
              >
                {item.text}
              </Tag>
            ))}
          </>
        ) : (
          <Text type="secondary">快速切到首次入列、升档、缓和或同类更新任务。</Text>
        )}
        {filters.keyword?.trim() || filters.reason || filters.refresh || filters.snapshotView || filters.snapshotSummary || filters.type || filters.source ? (
          <Button size="small" type="link" onClick={clearAllFilters}>
            清空全部筛选
          </Button>
        ) : null}
        <Button size="small" type="link" onClick={onCopyViewLink}>
          复制当前视图链接
        </Button>
      </Space>
    </Card>

    {loading ? (
      <Card variant="borderless">
        <div style={{ minHeight: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Spin />
        </div>
      </Card>
    ) : (
      <Row gutter={[16, 16]}>
        {boardColumns.map((column) => {
          const columnPriorityCounts = buildColumnPriorityCounts(column.tasks);
          return (
          <Col xs={24} md={12} xl={6} key={column.status}>
            <Card
              variant="borderless"
              title={(
                <Space wrap>
                  <span>{column.title}</span>
                  <Tag>{column.tasks.length}</Tag>
                  {columnPriorityCounts.escalated
                    ? renderColumnPriorityTag(column.status, 'escalated', 'red', '升档', columnPriorityCounts.escalated)
                    : null}
                  {columnPriorityCounts.new
                    ? renderColumnPriorityTag(column.status, 'new', 'blue', '首次', columnPriorityCounts.new)
                    : null}
                  {columnPriorityCounts.relaxed
                    ? renderColumnPriorityTag(column.status, 'relaxed', 'green', '缓和', columnPriorityCounts.relaxed)
                    : null}
                  {columnPriorityCounts.updated
                    ? renderColumnPriorityTag(column.status, 'updated', 'gold', '更新', columnPriorityCounts.updated)
                    : null}
                </Space>
              )}
              styles={{ body: { minHeight: 340 } }}
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
                column.tasks.map((task) => (
                  <React.Fragment key={task.id}>
                    {renderBoardCard(task, column.status)}
                  </React.Fragment>
                ))
              ) : (
                <Empty
                  description={
                    activeQuickFilter
                      ? `${column.title}暂无${activeQuickFilter.fullLabel}任务`
                      : `${column.title}暂无任务`
                  }
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </Card>
          </Col>
          );
        })}
      </Row>
    )}

    <Card
      variant="borderless"
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
};

export default WorkbenchBoardSection;
