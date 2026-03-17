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
  Typography,
  message,
} from 'antd';
import {
  DeleteOutlined,
  FolderOpenOutlined,
  RadarChartOutlined,
  SaveOutlined,
} from '@ant-design/icons';

import {
  deleteResearchTask,
  getResearchTaskStats,
  getResearchTasks,
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

function ResearchWorkbench() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({ type: '', status: '', source: '' });
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [titleDraft, setTitleDraft] = useState('');
  const [noteDraft, setNoteDraft] = useState('');

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) || tasks[0] || null,
    [tasks, selectedTaskId]
  );

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
    if (!selectedTask) {
      setTitleDraft('');
      setNoteDraft('');
      return;
    }
    setTitleDraft(selectedTask.title || '');
    setNoteDraft(selectedTask.note || '');
  }, [selectedTask]);

  const handleFilterChange = async (field, value) => {
    const nextFilters = { ...filters, [field]: value };
    setFilters(nextFilters);
  };

  const handleStatusUpdate = async (status) => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await updateResearchTask(selectedTask.id, { status });
      message.success('任务状态已更新');
      await loadWorkbench(filters);
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
      await loadWorkbench(filters);
    } catch (error) {
      message.error(error.userMessage || error.message || '保存任务信息失败');
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
      return (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text strong>{task.snapshot.headline || 'Pricing Snapshot'}</Text>
          <Paragraph style={{ marginBottom: 0 }}>{task.snapshot.summary}</Paragraph>
          {payload.gap_analysis?.fair_value_mid ? (
            <Text type="secondary">
              当前价 {payload.gap_analysis.current_price || '-'} / 公允价值 {payload.gap_analysis.fair_value_mid}
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
            把 GodEye、定价研究和跨市场回测里的任务卡保存下来，在这里持续跟踪、更新状态并重新打开原始研究页。
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
                      border: task.id === selectedTask?.id ? '1px solid rgba(24,144,255,0.45)' : '1px solid transparent',
                      background: task.id === selectedTask?.id ? 'rgba(24,144,255,0.08)' : 'transparent',
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
            {selectedTask ? (
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

                <Card size="small" title="快照摘要" bordered={false}>
                  {renderSnapshot(selectedTask)}
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
