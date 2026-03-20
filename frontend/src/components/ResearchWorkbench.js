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
  InboxOutlined,
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
  reorderResearchBoard,
  updateResearchTask,
} from '../services/api';
import { formatResearchSource, navigateByResearchAction } from '../utils/researchContext';
import SnapshotComparePanel from './research-workbench/SnapshotComparePanel';

const { Paragraph, Text, Title } = Typography;
const { TextArea, Search } = Input;

const MAIN_STATUSES = ['new', 'in_progress', 'blocked', 'complete'];

const STATUS_LABEL = {
  new: '新建',
  in_progress: '进行中',
  blocked: '阻塞',
  complete: '已完成',
  archived: '已归档',
};

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
  board_reordered: 'gold',
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
  board_reordered: '排序',
}[value] || '事件');

const sortByBoardOrder = (left, right) => {
  const orderGap = Number(left.board_order || 0) - Number(right.board_order || 0);
  if (orderGap !== 0) {
    return orderGap;
  }
  return String(left.updated_at || '').localeCompare(String(right.updated_at || ''));
};

const normalizeBoardOrders = (tasks) => {
  const cloned = tasks.map((task) => ({ ...task }));
  MAIN_STATUSES.forEach((status) => {
    const lane = cloned.filter((task) => task.status === status).sort(sortByBoardOrder);
    lane.forEach((task, index) => {
      task.board_order = index;
    });
  });
  return cloned;
};

const moveBoardTask = (tasks, draggedTaskId, targetStatus, targetTaskId = null) => {
  const normalized = normalizeBoardOrders(tasks);
  const draggedTask = normalized.find((task) => task.id === draggedTaskId);
  if (!draggedTask) {
    return normalized;
  }

  const boardMap = Object.fromEntries(
    MAIN_STATUSES.map((status) => [
      status,
      normalized.filter((task) => task.status === status).sort(sortByBoardOrder),
    ])
  );

  const sourceStatus = draggedTask.status;
  boardMap[sourceStatus] = boardMap[sourceStatus].filter((task) => task.id !== draggedTaskId);

  const nextTask = { ...draggedTask, status: targetStatus };
  const targetLane = [...boardMap[targetStatus]];
  const insertIndex = targetTaskId
    ? Math.max(targetLane.findIndex((task) => task.id === targetTaskId), 0)
    : targetLane.length;
  targetLane.splice(insertIndex, 0, nextTask);
  boardMap[targetStatus] = targetLane;

  MAIN_STATUSES.forEach((status) => {
    boardMap[status].forEach((task, index) => {
      task.board_order = index;
    });
  });

  const archived = normalized.filter((task) => task.status === 'archived');
  return [...MAIN_STATUSES.flatMap((status) => boardMap[status]), ...archived];
};

const buildReorderPayload = (tasks) =>
  MAIN_STATUSES.flatMap((status) =>
    tasks
      .filter((task) => task.status === status)
      .sort(sortByBoardOrder)
      .map((task, index) => ({
        task_id: task.id,
        status,
        board_order: index,
      }))
  );

function ResearchWorkbench() {
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({ type: '', source: '', keyword: '' });
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [selectedTask, setSelectedTask] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [titleDraft, setTitleDraft] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [commentDraft, setCommentDraft] = useState('');
  const [showAllTimeline, setShowAllTimeline] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [dragState, setDragState] = useState(null);

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

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    try {
      const [taskResponse, statsResponse] = await Promise.all([
        getResearchTasks({ limit: 200, view: 'board' }),
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
  }, []);

  useEffect(() => {
    loadWorkbench();
  }, [loadWorkbench]);

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

  const refreshCurrentTask = useCallback(async () => {
    await loadWorkbench();
    await loadTaskDetail(selectedTaskId);
  }, [loadTaskDetail, loadWorkbench, selectedTaskId]);

  const filteredTasks = useMemo(() => {
    const keyword = filters.keyword.trim().toLowerCase();
    return tasks.filter((task) => {
      if (filters.type && task.type !== filters.type) {
        return false;
      }
      if (filters.source && task.source !== filters.source) {
        return false;
      }
      if (!keyword) {
        return true;
      }
      const haystack = [
        task.title,
        task.symbol,
        task.template,
        task.note,
        task.snapshot?.headline,
        task.snapshot?.summary,
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }, [filters, tasks]);

  const boardColumns = useMemo(
    () =>
      MAIN_STATUSES.map((status) => ({
        status,
        title: STATUS_LABEL[status],
        tasks: filteredTasks.filter((task) => task.status === status).sort(sortByBoardOrder),
      })),
    [filteredTasks]
  );

  const archivedTasks = useMemo(
    () =>
      filteredTasks
        .filter((task) => task.status === 'archived')
        .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || ''))),
    [filteredTasks]
  );

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

  const handleStatusUpdate = async (status) => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await updateResearchTask(selectedTask.id, { status });
      message.success(status === 'archived' ? '任务已归档' : '任务状态已更新');
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
      await loadWorkbench();
    } catch (error) {
      message.error(error.userMessage || error.message || '删除任务失败');
    } finally {
      setSaving(false);
    }
  };

  const handleRestoreArchived = async (taskId) => {
    setSaving(true);
    try {
      await updateResearchTask(taskId, { status: 'new' });
      message.success('任务已恢复到新建列');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '恢复任务失败');
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

  const commitBoardReorder = async (nextTasks, successMessage = '看板顺序已更新') => {
    const previousTasks = tasks;
    const normalizedTasks = normalizeBoardOrders(nextTasks);
    setTasks(normalizedTasks);
    try {
      await reorderResearchBoard({ items: buildReorderPayload(normalizedTasks) });
      await loadWorkbench();
      if (selectedTaskId) {
        await loadTaskDetail(selectedTaskId);
      }
      message.success(successMessage);
    } catch (error) {
      setTasks(previousTasks);
      message.error(error.userMessage || error.message || '更新看板顺序失败');
    } finally {
      setDragState(null);
    }
  };

  const handleDrop = async (targetStatus, targetTaskId = null) => {
    if (!dragState?.taskId) {
      return;
    }
    const nextTasks = moveBoardTask(tasks, dragState.taskId, targetStatus, targetTaskId);
    await commitBoardReorder(nextTasks);
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
        {payload.template_meta?.theme ? (
          <Text type="secondary">主题 {payload.template_meta.theme}</Text>
        ) : null}
        {payload.template_meta?.allocation_mode ? (
          <Text type="secondary">
            配置模式 {payload.template_meta.allocation_mode === 'macro_bias' ? '宏观偏置' : '模板原始权重'}
          </Text>
        ) : null}
        {payload.template_meta?.bias_summary ? (
          <Text type="secondary">权重偏置 {payload.template_meta.bias_summary}</Text>
        ) : null}
        {payload.template_meta?.bias_actions?.length ? (
          <Text type="secondary">
            建议动作 {(payload.template_meta.bias_actions || []).map((item) => `${item.action === 'increase' ? '增配' : '减配'} ${item.symbol}`).join('，')}
          </Text>
        ) : null}
        {payload.template_meta?.driver_summary?.length ? (
          <Text type="secondary">
            驱动分解 {(payload.template_meta.driver_summary || []).slice(0, 3).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('，')}
          </Text>
        ) : null}
        {payload.template_meta?.theme_core ? (
          <Text type="secondary">核心腿 {payload.template_meta.theme_core}</Text>
        ) : null}
        {payload.template_meta?.theme_support ? (
          <Text type="secondary">辅助腿 {payload.template_meta.theme_support}</Text>
        ) : null}
        {payload.allocation_overlay?.max_delta_weight ? (
          <Text type="secondary">
            最大权重偏移 {(Number(payload.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
          </Text>
        ) : null}
        {payload.template_meta?.recommendation_tier ? (
          <Tag color="gold">{payload.template_meta.recommendation_tier}</Tag>
        ) : null}
        {payload.template_meta?.recommendation_reason ? (
          <Text type="secondary">推荐依据 {payload.template_meta.recommendation_reason}</Text>
        ) : null}
        {payload.total_return !== undefined ? (
          <Text type="secondary">
            总收益 {(Number(payload.total_return || 0) * 100).toFixed(2)}% / Sharpe {Number(payload.sharpe_ratio || 0).toFixed(2)}
          </Text>
        ) : null}
        {payload.execution_plan?.batches?.length ? (
          <Text type="secondary">
            执行批次 {payload.execution_plan.batches.length} / 路由 {payload.execution_plan.route_count || 0}
            {payload.execution_plan.initial_capital ? ` / 计划资金 ${Number(payload.execution_plan.initial_capital).toLocaleString()}` : ''}
          </Text>
        ) : null}
        {payload.execution_diagnostics?.concentration_level ? (
          <Text type="secondary">
            执行集中度 {payload.execution_diagnostics.concentration_level}
            {payload.execution_diagnostics.concentration_reason ? ` · ${payload.execution_diagnostics.concentration_reason}` : ''}
          </Text>
        ) : null}
        {payload.execution_diagnostics?.suggested_rebalance ? (
          <Text type="secondary">
            建议调仓 {payload.execution_diagnostics.suggested_rebalance}
            {payload.execution_diagnostics.lot_efficiency !== undefined
              ? ` · Lot 效率 ${(Number(payload.execution_diagnostics.lot_efficiency || 0) * 100).toFixed(2)}%`
              : ''}
          </Text>
        ) : null}
        {payload.execution_plan?.execution_stress?.worst_case ? (
          <Text type="secondary">
            压力测试 {payload.execution_plan.execution_stress.worst_case.label} · {payload.execution_plan.execution_stress.worst_case.concentration_level}
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
          const templateMeta = payload.template_meta || {};
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
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        <Text type="secondary">
                          Return {(Number(payload.total_return || 0) * 100).toFixed(2)}% · Sharpe {Number(payload.sharpe_ratio || 0).toFixed(2)}
                        </Text>
                        {payload.execution_plan?.batches?.length ? (
                          <Text type="secondary">
                            执行批次 {payload.execution_plan.batches.length} · 路由 {payload.execution_plan.route_count || 0}
                            {payload.execution_plan.initial_capital ? ` · 资金 ${Number(payload.execution_plan.initial_capital).toLocaleString()}` : ''}
                          </Text>
                        ) : null}
                        {payload.execution_diagnostics?.concentration_level ? (
                          <Text type="secondary">
                            集中度 {payload.execution_diagnostics.concentration_level}
                          </Text>
                        ) : null}
                        {payload.execution_diagnostics?.suggested_rebalance ? (
                          <Text type="secondary">
                            调仓 {payload.execution_diagnostics.suggested_rebalance}
                            {payload.execution_diagnostics.lot_efficiency !== undefined
                              ? ` · Lot ${(Number(payload.execution_diagnostics.lot_efficiency || 0) * 100).toFixed(1)}%`
                              : ''}
                          </Text>
                        ) : null}
                        {payload.execution_plan?.execution_stress?.worst_case ? (
                          <Text type="secondary">
                            压测 {payload.execution_plan.execution_stress.worst_case.label} · {payload.execution_plan.execution_stress.worst_case.concentration_level}
                          </Text>
                        ) : null}
                        {templateMeta.recommendation_tier ? (
                          <Text type="secondary">
                            推荐 {templateMeta.recommendation_tier}
                            {templateMeta.theme ? ` · ${templateMeta.theme}` : ''}
                          </Text>
                        ) : null}
                        {templateMeta.bias_summary ? (
                          <Text type="secondary">
                            偏置 {templateMeta.bias_summary}
                          </Text>
                        ) : null}
                        {templateMeta.bias_actions?.length ? (
                          <Text type="secondary">
                            动作 {(templateMeta.bias_actions || []).slice(0, 3).map((item) => `${item.action === 'increase' ? '增配' : '减配'} ${item.symbol}`).join('，')}
                          </Text>
                        ) : null}
                        {templateMeta.driver_summary?.length ? (
                          <Text type="secondary">
                            分解 {(templateMeta.driver_summary || []).slice(0, 2).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('，')}
                          </Text>
                        ) : null}
                        {templateMeta.theme_core ? (
                          <Text type="secondary">
                            核心腿 {templateMeta.theme_core}
                          </Text>
                        ) : null}
                        {payload.allocation_overlay?.max_delta_weight ? (
                          <Text type="secondary">
                            最大偏移 {(Number(payload.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
                          </Text>
                        ) : null}
                        {templateMeta.recommendation_reason ? (
                          <Text type="secondary">{templateMeta.recommendation_reason}</Text>
                        ) : null}
                      </Space>
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

  const renderBoardCard = (task, status) => {
    const isOverTarget = dragState?.overTaskId === task.id && dragState?.overStatus === status;
    const templateMeta = task.snapshot?.payload?.template_meta || {};
    const executionPlan = task.snapshot?.payload?.execution_plan || {};
    return (
      <div
        key={task.id}
        draggable
        onDragStart={() => setDragState({ taskId: task.id, sourceStatus: status, overTaskId: null, overStatus: null })}
        onDragEnd={() => setDragState(null)}
        onDragOver={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setDragState((current) => (current ? { ...current, overTaskId: task.id, overStatus: status } : current));
        }}
        onDrop={(event) => {
          event.preventDefault();
          event.stopPropagation();
          handleDrop(status, task.id);
        }}
        onClick={() => setSelectedTaskId(task.id)}
        style={{
          cursor: 'grab',
          borderRadius: 12,
          padding: 12,
          marginBottom: 10,
          background: selectedTaskId === task.id ? 'rgba(24,144,255,0.12)' : 'rgba(255,255,255,0.03)',
          border: isOverTarget
            ? '1px dashed rgba(24,144,255,0.7)'
            : selectedTaskId === task.id
              ? '1px solid rgba(24,144,255,0.45)'
              : '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>{task.title}</Text>
            <Tag color={task.type === 'pricing' ? 'blue' : 'purple'}>{task.type}</Tag>
            {templateMeta.recommendation_tier ? <Tag color="gold">{templateMeta.recommendation_tier}</Tag> : null}
          </Space>
          <Text type="secondary">{task.snapshot?.headline || '暂无快照摘要'}</Text>
          {templateMeta.theme ? <Text type="secondary">{templateMeta.theme}</Text> : null}
          {templateMeta.bias_summary ? <Text type="secondary">{templateMeta.bias_summary}</Text> : null}
          {templateMeta.bias_actions?.length ? (
            <Text type="secondary">
              {(templateMeta.bias_actions || []).slice(0, 2).map((item) => `${item.action === 'increase' ? '增配' : '减配'} ${item.symbol}`).join('，')}
            </Text>
          ) : null}
          {templateMeta.driver_summary?.length ? (
            <Text type="secondary">
              {(templateMeta.driver_summary || []).slice(0, 2).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('，')}
            </Text>
          ) : null}
          {templateMeta.theme_core ? <Text type="secondary">{templateMeta.theme_core}</Text> : null}
          {task.snapshot?.payload?.allocation_overlay?.max_delta_weight ? (
            <Text type="secondary">
              最大偏移 {(Number(task.snapshot.payload.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
            </Text>
          ) : null}
          <Text type="secondary">
            {task.symbol || task.template || '-'} · {formatResearchSource(task.source || 'manual')}
          </Text>
          {executionPlan.route_count ? (
            <Text type="secondary">
              路由 {executionPlan.route_count} · 批次 {(executionPlan.batches || []).length}
            </Text>
          ) : null}
          {task.snapshot?.payload?.execution_diagnostics?.concentration_level ? (
            <Text type="secondary">
              集中度 {task.snapshot.payload.execution_diagnostics.concentration_level}
            </Text>
          ) : null}
          {task.snapshot?.payload?.execution_diagnostics?.suggested_rebalance ? (
            <Text type="secondary">
              调仓 {task.snapshot.payload.execution_diagnostics.suggested_rebalance}
            </Text>
          ) : null}
          {task.snapshot?.payload?.execution_plan?.execution_stress?.worst_case ? (
            <Text type="secondary">
              压测 {task.snapshot.payload.execution_plan.execution_stress.worst_case.label}
            </Text>
          ) : null}
          <Text type="secondary">{new Date(task.updated_at).toLocaleString()}</Text>
        </Space>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card bordered={false}>
        <Space direction="vertical" size={6}>
          <Tag color="geekblue" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
            Research Workbench V3
          </Tag>
          <Title level={4} style={{ margin: 0 }}>
            研究工作台
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            研究任务现在以多列看板形式推进。你可以直接拖拽任务跨列流转，同时继续保留评论、时间线和快照演进记录。
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
        <Col xs={24} xl={16}>
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
        </Col>

        <Col xs={24} xl={8}>
          <Card
            bordered={false}
            title="任务详情"
            extra={selectedTask ? <Tag color={STATUS_COLOR[selectedTask.status] || 'default'}>{selectedTask.status}</Tag> : null}
            bodyStyle={{ minHeight: 760 }}
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

                <SnapshotComparePanel task={selectedTask} />

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
                    {selectedTask.status === 'archived' ? (
                      <Button type="primary" onClick={() => handleRestoreArchived(selectedTask.id)} loading={saving}>
                        恢复到新建
                      </Button>
                    ) : (
                      <>
                        <Button onClick={() => handleStatusUpdate('new')} loading={saving}>
                          放回新建
                        </Button>
                        <Button onClick={() => handleStatusUpdate('in_progress')} loading={saving}>
                          进行中
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
                      </>
                    )}
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
