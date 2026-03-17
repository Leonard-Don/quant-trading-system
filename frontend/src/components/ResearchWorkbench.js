import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
  Statistic,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import {
  ClockCircleOutlined,
  CommentOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  RadarChartOutlined,
  SaveOutlined,
} from '@ant-design/icons';

import {
  addResearchTaskComment,
  deleteResearchTask,
  deleteResearchTaskComment,
  getResearchTask,
  getResearchTaskStats,
  getResearchTasks,
  getResearchTaskTimeline,
  updateResearchTask,
} from '../services/api';
import { formatResearchSource, navigateByResearchAction } from '../utils/researchContext';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

const STATUS_OPTIONS = [
  { label: '全部状态', value: '' },
  { label: '新建', value: 'new' },
  { label: '进行中', value: 'in_progress' },
  { label: '阻塞', value: 'blocked' },
  { label: '已完成', value: 'complete' },
  { label: '已归档', value: 'archived' },
];

const TYPE_OPTIONS = [
  { label: '全部类型', value: '' },
  { label: 'Pricing', value: 'pricing' },
  { label: 'Cross-Market', value: 'cross_market' },
];

const STATUS_COLOR = {
  new: 'blue',
  in_progress: 'processing',
  blocked: 'orange',
  complete: 'green',
  archived: 'default',
};

const TIMELINE_COLOR = {
  created: 'blue',
  status_changed: 'orange',
  snapshot_saved: 'green',
  metadata_updated: 'purple',
  comment_added: 'cyan',
  comment_deleted: 'red',
};

const formatContextValue = (value) => {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === 'object') {
          return [item.symbol, item.side, item.asset_class].filter(Boolean).join('/');
        }
        return String(item);
      })
      .join(', ');
  }

  if (value && typeof value === 'object') {
    return Object.entries(value)
      .slice(0, 4)
      .map(([key, item]) => `${key}:${item}`)
      .join(', ');
  }

  return String(value);
};

const formatTimelineType = (value) => ({
  created: '创建',
  status_changed: '状态',
  snapshot_saved: '快照',
  metadata_updated: '元信息',
  comment_added: '评论',
  comment_deleted: '删除',
}[value] || '事件');

function ResearchWorkbench() {
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({ type: '', status: '', source: '' });
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [selectedTask, setSelectedTask] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [titleDraft, setTitleDraft] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [commentDraft, setCommentDraft] = useState('');
  const [showAllTimeline, setShowAllTimeline] = useState(false);

  const sourceOptions = useMemo(() => {
    const uniqueSources = Array.from(new Set(tasks.map((task) => task.source).filter(Boolean)));
    return [
      { label: '全部来源', value: '' },
      ...uniqueSources.map((source) => ({
        label: formatResearchSource(source),
        value: source,
      })),
    ];
  }, [tasks]);

  const loadTaskDetail = useCallback(async (taskId) => {
    if (!taskId) {
      setSelectedTask(null);
      setTimeline([]);
      return;
    }

    setDetailLoading(true);
    try {
      const [taskResponse, timelineResponse] = await Promise.all([
        getResearchTask(taskId),
        getResearchTaskTimeline(taskId),
      ]);
      setSelectedTask(taskResponse.data || null);
      setTimeline(timelineResponse.data || []);
    } catch (error) {
      message.error(error.userMessage || error.message || '加载任务详情失败');
      setSelectedTask(null);
      setTimeline([]);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadWorkbench = useCallback(async (nextFilters = filters) => {
    setLoading(true);
    try {
      const [taskResponse, statsResponse] = await Promise.all([
        getResearchTasks({ limit: 100, ...nextFilters }),
        getResearchTaskStats(),
      ]);
      const nextTasks = taskResponse.data || [];
      setTasks(nextTasks);
      setStats(statsResponse.data || null);
      setSelectedTaskId((current) => {
        if (current && nextTasks.some((task) => task.id === current)) {
          return current;
        }
        return nextTasks[0]?.id || '';
      });
    } catch (error) {
      message.error(error.userMessage || error.message || '加载研究工作台失败');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadWorkbench(filters);
  }, [filters, loadWorkbench]);

  useEffect(() => {
    loadTaskDetail(selectedTaskId);
  }, [loadTaskDetail, selectedTaskId]);

  useEffect(() => {
    if (!selectedTask) {
      setTitleDraft('');
      setNoteDraft('');
      setCommentDraft('');
      setShowAllTimeline(false);
      return;
    }
    setTitleDraft(selectedTask.title || '');
    setNoteDraft(selectedTask.note || '');
    setShowAllTimeline(false);
  }, [selectedTask]);

  const handleFilterChange = (field, value) => {
    const nextFilters = { ...filters, [field]: value };
    setFilters(nextFilters);
  };

  const refreshCurrentTask = useCallback(async () => {
    await loadWorkbench(filters);
    await loadTaskDetail(selectedTaskId);
  }, [filters, loadTaskDetail, loadWorkbench, selectedTaskId]);

  const handleStatusUpdate = async (status) => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await updateResearchTask(selectedTask.id, { status });
      message.success('任务状态已更新');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '更新任务状态失败');
    } finally {
      setSaving(false);
    }
  };

  const handleMetaSave = async () => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await updateResearchTask(selectedTask.id, {
        title: titleDraft,
        note: noteDraft,
      });
      message.success('任务信息已保存');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '保存任务信息失败');
    } finally {
      setSaving(false);
    }
  };

  const handleAddComment = async () => {
    if (!selectedTask || !commentDraft.trim()) return;
    setSaving(true);
    try {
      await addResearchTaskComment(selectedTask.id, {
        body: commentDraft.trim(),
        author: 'local',
      });
      setCommentDraft('');
      message.success('评论已添加');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '添加评论失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteComment = async (commentId) => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await deleteResearchTaskComment(selectedTask.id, commentId);
      message.success('评论已删除');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '删除评论失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await deleteResearchTask(selectedTask.id);
      message.success('任务已删除');
      await loadWorkbench(filters);
    } catch (error) {
      message.error(error.userMessage || error.message || '删除任务失败');
    } finally {
      setSaving(false);
    }
  };

  const handleOpenTask = () => {
    if (!selectedTask) return;

    if (selectedTask.type === 'pricing' && selectedTask.symbol) {
      navigateByResearchAction({
        target: 'pricing',
        symbol: selectedTask.symbol,
        source: 'research_workbench',
        note: selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`,
      });
      return;
    }

    if (selectedTask.type === 'cross_market' && selectedTask.template) {
      navigateByResearchAction({
        target: 'cross-market',
        template: selectedTask.template,
        source: 'research_workbench',
        note: selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`,
      });
      return;
    }

    navigateByResearchAction({
      target: 'godsEye',
      source: 'research_workbench',
      note: '返回 GodEye 继续筛选研究线索',
    });
  };

  const renderSnapshot = (task) => {
    if (!task?.snapshot) {
      return <Empty description="暂无保存快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }

    const payload = task.snapshot.payload || {};
    if (task.type === 'pricing') {
      const fairValue = payload.fair_value || payload.valuation?.fair_value || {};
      return (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text strong>{task.snapshot.headline || 'Pricing Snapshot'}</Text>
          <Paragraph style={{ marginBottom: 0 }}>{task.snapshot.summary}</Paragraph>
          {payload.gap_analysis?.fair_value_mid ? (
            <Text type="secondary">
              当前价 {payload.gap_analysis.current_price || '-'} / 公允价值 {payload.gap_analysis.fair_value_mid}
            </Text>
          ) : null}
          {fairValue.mid ? (
            <Text type="secondary">
              综合公允价值区间 {fairValue.low || '-'} ~ {fairValue.high || '-'}
            </Text>
          ) : null}
          {payload.implications?.primary_view ? (
            <Tag color="blue">{payload.implications.primary_view}</Tag>
          ) : null}
          {(task.snapshot.highlights || []).map((item) => (
            <Text key={item} type="secondary">
              {item}
            </Text>
          ))}
        </Space>
      );
    }

    return (
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong>{task.snapshot.headline || 'Cross-Market Snapshot'}</Text>
        <Paragraph style={{ marginBottom: 0 }}>{task.snapshot.summary}</Paragraph>
        {payload.total_return !== undefined ? (
          <Text type="secondary">
            总收益 {(Number(payload.total_return || 0) * 100).toFixed(2)}% / Sharpe {Number(payload.sharpe_ratio || 0).toFixed(2)}
          </Text>
        ) : null}
        {payload.data_alignment?.tradable_day_ratio !== undefined ? (
          <Text type="secondary">
            覆盖率 {(Number(payload.data_alignment.tradable_day_ratio || 0) * 100).toFixed(2)}%
          </Text>
        ) : null}
        {(task.snapshot.highlights || []).map((item) => (
          <Text key={item} type="secondary">
            {item}
          </Text>
        ))}
      </Space>
    );
  };

  const renderSnapshotHistory = (task) => {
    const history = task?.snapshot_history || [];
    if (!history.length) {
      return <Empty description="暂无历史快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }

    return (
      <List
        size="small"
        dataSource={history}
        renderItem={(item) => {
          const payload = item.payload || {};
          const savedAt = item.saved_at ? new Date(item.saved_at).toLocaleString() : '-';
          const pricingValue = payload.fair_value?.mid || payload.gap_analysis?.fair_value_mid;
          return (
            <List.Item>
              <List.Item.Meta
                title={(
                  <Space wrap>
                    <Text strong>{item.headline || '研究快照'}</Text>
                    <Tag>{savedAt}</Tag>
                  </Space>
                )}
                description={(
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Text type="secondary">{item.summary || '暂无摘要'}</Text>
                    {task.type === 'pricing' ? (
                      <Text type="secondary">
                        Fair value {pricingValue || '-'} · {(payload.implications?.primary_view || '待判断')}
                      </Text>
                    ) : (
                      <Text type="secondary">
                        Return {(Number(payload.total_return || 0) * 100).toFixed(2)}% · Sharpe {Number(payload.sharpe_ratio || 0).toFixed(2)}
                      </Text>
                    )}
                  </Space>
                )}
              />
            </List.Item>
          );
        }}
      />
    );
  };

  const timelineItems = useMemo(() => {
    const visible = showAllTimeline ? timeline : timeline.slice(0, 8);
    return visible.map((event) => ({
      color: TIMELINE_COLOR[event.type] || 'blue',
      dot: event.type === 'comment_added' ? <CommentOutlined /> : <ClockCircleOutlined />,
      children: (
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>{event.label}</Text>
            <Tag color={TIMELINE_COLOR[event.type] || 'default'}>{formatTimelineType(event.type)}</Tag>
            <Text type="secondary">{new Date(event.created_at).toLocaleString()}</Text>
          </Space>
          {event.detail ? <Text type="secondary">{event.detail}</Text> : null}
        </Space>
      ),
    }));
  }, [showAllTimeline, timeline]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card bordered={false}>
        <Space direction="vertical" size={6}>
          <Tag color="geekblue" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
            Research Workbench
          </Tag>
          <Title level={4} style={{ margin: 0 }}>
            研究工作台
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            把 GodEye、定价研究和跨市场回测里的任务卡保存下来，在这里持续跟踪、更新状态，并查看研究如何一步步演进。
          </Paragraph>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card bordered={false}>
            <Statistic title="总任务" value={stats?.total || 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card bordered={false}>
            <Statistic title="进行中" value={stats?.status_counts?.in_progress || 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card bordered={false}>
            <Statistic title="阻塞" value={stats?.status_counts?.blocked || 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card bordered={false}>
            <Statistic title="已完成" value={stats?.status_counts?.complete || 0} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <Card
            bordered={false}
            title="任务列表"
            extra={(
              <Space wrap>
                <Select
                  size="small"
                  value={filters.type}
                  options={TYPE_OPTIONS}
                  onChange={(value) => handleFilterChange('type', value)}
                  style={{ width: 140 }}
                />
                <Select
                  size="small"
                  value={filters.status}
                  options={STATUS_OPTIONS}
                  onChange={(value) => handleFilterChange('status', value)}
                  style={{ width: 140 }}
                />
                <Select
                  size="small"
                  value={filters.source}
                  options={sourceOptions}
                  onChange={(value) => handleFilterChange('source', value)}
                  style={{ width: 160 }}
                />
              </Space>
            )}
            bodyStyle={{ minHeight: 560 }}
          >
            {loading ? (
              <div style={{ minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
              </div>
            ) : (
              <List
                dataSource={tasks}
                locale={{ emptyText: '暂无研究任务' }}
                renderItem={(task) => (
                  <List.Item
                    onClick={() => setSelectedTaskId(task.id)}
                    style={{
                      cursor: 'pointer',
                      padding: '12px 10px',
                      borderRadius: 12,
                      marginBottom: 8,
                      border: task.id === selectedTaskId ? '1px solid rgba(24,144,255,0.45)' : '1px solid transparent',
                      background: task.id === selectedTaskId ? 'rgba(24,144,255,0.08)' : 'transparent',
                    }}
                  >
                    <List.Item.Meta
                      title={(
                        <Space wrap>
                          <Text strong>{task.title}</Text>
                          <Tag color={task.type === 'pricing' ? 'blue' : 'purple'}>{task.type}</Tag>
                          <Tag color={STATUS_COLOR[task.status] || 'default'}>{task.status}</Tag>
                        </Space>
                      )}
                      description={(
                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                          <Text type="secondary">{task.snapshot?.headline || '暂无摘要'}</Text>
                          <Text type="secondary">
                            {formatResearchSource(task.source || 'manual')} · {new Date(task.updated_at).toLocaleString()}
                          </Text>
                        </Space>
                      )}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card
            bordered={false}
            title="任务详情"
            extra={selectedTask ? <Tag color={STATUS_COLOR[selectedTask.status] || 'default'}>{selectedTask.status}</Tag> : null}
            bodyStyle={{ minHeight: 560 }}
          >
            {detailLoading ? (
              <div style={{ minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
              </div>
            ) : selectedTask ? (
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Space wrap>
                  <Button type="primary" icon={<FolderOpenOutlined />} onClick={handleOpenTask}>
                    重新打开研究页
                  </Button>
                  <Button icon={<RadarChartOutlined />} onClick={() => navigateByResearchAction({ target: 'godsEye' })}>
                    回到 GodEye
                  </Button>
                  <Button danger icon={<DeleteOutlined />} onClick={handleDelete} loading={saving}>
                    删除任务
                  </Button>
                </Space>

                <Row gutter={[12, 12]}>
                  <Col xs={24} md={12}>
                    <Card size="small" bordered={false}>
                      <Text type="secondary">类型</Text>
                      <div><Text strong>{selectedTask.type}</Text></div>
                    </Card>
                  </Col>
                  <Col xs={24} md={12}>
                    <Card size="small" bordered={false}>
                      <Text type="secondary">来源</Text>
                      <div><Text strong>{formatResearchSource(selectedTask.source || 'manual')}</Text></div>
                    </Card>
                  </Col>
                  <Col xs={24} md={12}>
                    <Card size="small" bordered={false}>
                      <Text type="secondary">Symbol</Text>
                      <div><Text strong>{selectedTask.symbol || '-'}</Text></div>
                    </Card>
                  </Col>
                  <Col xs={24} md={12}>
                    <Card size="small" bordered={false}>
                      <Text type="secondary">Template</Text>
                      <div><Text strong>{selectedTask.template || '-'}</Text></div>
                    </Card>
                  </Col>
                </Row>

                <Card size="small" title="任务信息" bordered={false}>
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Input value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} placeholder="任务标题" />
                    <TextArea
                      rows={3}
                      value={noteDraft}
                      onChange={(event) => setNoteDraft(event.target.value)}
                      placeholder="补充备注或下一步计划"
                    />
                    <Button icon={<SaveOutlined />} onClick={handleMetaSave} loading={saving} style={{ alignSelf: 'flex-start' }}>
                      保存备注
                    </Button>
                  </Space>
                </Card>

                <Card size="small" title="任务上下文" bordered={false}>
                  <Space wrap>
                    {Object.entries(selectedTask.context || {}).map(([key, value]) => (
                      <Tag key={key}>
                        {key}: {formatContextValue(value)}
                      </Tag>
                    ))}
                  </Space>
                </Card>

                <Card size="small" title="当前快照" bordered={false}>
                  {renderSnapshot(selectedTask)}
                </Card>

                <Card size="small" title="历史快照" bordered={false}>
                  {renderSnapshotHistory(selectedTask)}
                </Card>

                <Card
                  size="small"
                  title={(
                    <Space>
                      <HistoryOutlined />
                      <span>研究时间线</span>
                    </Space>
                  )}
                  extra={
                    timeline.length > 8 ? (
                      <Button type="link" size="small" onClick={() => setShowAllTimeline((prev) => !prev)}>
                        {showAllTimeline ? '收起' : '展开更多'}
                      </Button>
                    ) : null
                  }
                  bordered={false}
                >
                  {timeline.length ? (
                    <Timeline items={timelineItems} />
                  ) : (
                    <Empty description="暂无时间线事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </Card>

                <Card
                  size="small"
                  title={(
                    <Space>
                      <CommentOutlined />
                      <span>评论</span>
                    </Space>
                  )}
                  bordered={false}
                >
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <TextArea
                      rows={3}
                      value={commentDraft}
                      onChange={(event) => setCommentDraft(event.target.value)}
                      placeholder="记录这一步的判断、风险或下一步动作"
                    />
                    <Button
                      type="primary"
                      icon={<CommentOutlined />}
                      onClick={handleAddComment}
                      loading={saving}
                      disabled={!commentDraft.trim()}
                      style={{ alignSelf: 'flex-start' }}
                    >
                      添加评论
                    </Button>

                    {(selectedTask.comments || []).length ? (
                      <List
                        size="small"
                        dataSource={selectedTask.comments}
                        renderItem={(comment) => (
                          <List.Item
                            actions={[
                              <Button
                                key="delete"
                                type="link"
                                danger
                                size="small"
                                onClick={() => handleDeleteComment(comment.id)}
                              >
                                删除
                              </Button>,
                            ]}
                          >
                            <List.Item.Meta
                              title={(
                                <Space wrap>
                                  <Text strong>{comment.author || 'local'}</Text>
                                  <Text type="secondary">{new Date(comment.created_at).toLocaleString()}</Text>
                                </Space>
                              )}
                              description={comment.body}
                            />
                          </List.Item>
                        )}
                      />
                    ) : (
                      <Empty description="暂无评论" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                  </Space>
                </Card>

                <Card size="small" title="状态流转" bordered={false}>
                  <Space wrap>
                    <Button onClick={() => handleStatusUpdate('in_progress')} loading={saving}>
                      开始
                    </Button>
                    <Button onClick={() => handleStatusUpdate('blocked')} loading={saving}>
                      阻塞
                    </Button>
                    <Button type="primary" onClick={() => handleStatusUpdate('complete')} loading={saving}>
                      完成
                    </Button>
                    <Button onClick={() => handleStatusUpdate('archived')} loading={saving}>
                      归档
                    </Button>
                  </Space>
                </Card>
              </Space>
            ) : (
              <Empty description="请选择一个研究任务" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

export default ResearchWorkbench;
