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
  getAltDataSnapshot,
  getMacroOverview,
  getResearchTask,
  getResearchTaskStats,
  getResearchTasks,
  getResearchTaskTimeline,
  reorderResearchBoard,
  updateResearchTask,
} from '../services/api';
import {
  buildWorkbenchLink,
  formatResearchSource,
  navigateByResearchAction,
  readResearchContext,
} from '../utils/researchContext';
import { buildResearchTaskRefreshSignals } from '../utils/researchTaskSignals';
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

const REFRESH_OPTIONS = [
  { label: '全部更新状态', value: '' },
  { label: '建议更新', value: 'high' },
  { label: '建议复核', value: 'medium' },
  { label: '继续观察', value: 'low' },
];

const REASON_OPTIONS = [
  { label: '全部更新原因', value: '' },
  { label: '共振驱动', value: 'resonance' },
  { label: '核心腿受压', value: 'bias_quality_core' },
  { label: '自动降级', value: 'selection_quality' },
  { label: '政策源驱动', value: 'policy_source' },
  { label: '偏置收缩', value: 'bias_quality' },
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

const sortTasksByRefreshPriority = (tasks = [], refreshLookup = {}, enablePriority = false) => {
  const list = [...tasks];
  if (!enablePriority) {
    return list;
  }

  return list.sort((left, right) => {
    const leftSignal = refreshLookup[left.id] || {};
    const rightSignal = refreshLookup[right.id] || {};
    if (Number(rightSignal.urgencyScore || 0) !== Number(leftSignal.urgencyScore || 0)) {
      return Number(rightSignal.urgencyScore || 0) - Number(leftSignal.urgencyScore || 0);
    }
    if (Number(rightSignal.priorityWeight || 0) !== Number(leftSignal.priorityWeight || 0)) {
      return Number(rightSignal.priorityWeight || 0) - Number(leftSignal.priorityWeight || 0);
    }
    return String(right.updated_at || '').localeCompare(String(left.updated_at || ''));
  });
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
  const initialContext = readResearchContext();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [liveOverview, setLiveOverview] = useState(null);
  const [liveSnapshot, setLiveSnapshot] = useState(null);
  const [filters, setFilters] = useState({
    type: initialContext.workbenchType || '',
    source: initialContext.workbenchSource || '',
    refresh: initialContext.workbenchRefresh || '',
    reason: initialContext.workbenchReason || '',
    keyword: '',
  });
  const [selectedTaskId, setSelectedTaskId] = useState(initialContext.task || '');
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
      const [taskResponse, statsResponse, macroResponse, altSnapshotResponse] = await Promise.all([
        getResearchTasks({ limit: 200, view: 'board' }),
        getResearchTaskStats(),
        getMacroOverview(false),
        getAltDataSnapshot(false),
      ]);
      const nextTasks = taskResponse.data || [];
      setTasks(nextTasks);
      setStats(statsResponse.data || null);
      setLiveOverview(macroResponse || null);
      setLiveSnapshot(altSnapshotResponse || null);
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
    const nextUrl = buildWorkbenchLink(
      {
        refresh: filters.refresh,
        type: filters.type,
        sourceFilter: filters.source,
        reason: filters.reason,
        taskId: selectedTaskId,
      },
      window.location.search
    );
    window.history.replaceState(null, '', nextUrl);
  }, [filters.reason, filters.refresh, filters.source, filters.type, selectedTaskId]);

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

  const refreshSignals = useMemo(
    () => buildResearchTaskRefreshSignals({ researchTasks: tasks, overview: liveOverview, snapshot: liveSnapshot }),
    [liveOverview, liveSnapshot, tasks]
  );

  const refreshStats = useMemo(() => {
    const prioritized = refreshSignals.prioritized || [];
    return {
      high: prioritized.filter((item) => item.severity === 'high').length,
      medium: prioritized.filter((item) => item.severity === 'medium').length,
      low: prioritized.filter((item) => item.severity === 'low').length,
      resonance: prioritized.filter((item) => item.resonanceDriven).length,
      biasQualityCore: prioritized.filter((item) => item.biasCompressionShift?.coreLegAffected).length,
      selectionQuality: prioritized.filter((item) => item.selectionQualityDriven || item.selectionQualityRunState?.active).length,
      policySource: prioritized.filter((item) => item.policySourceDriven).length,
      biasQuality: prioritized.filter((item) => item.biasCompressionDriven).length,
    };
  }, [refreshSignals]);

  const filteredTasks = useMemo(() => {
    const keyword = filters.keyword.trim().toLowerCase();
    const matches = tasks.filter((task) => {
      if (filters.type && task.type !== filters.type) {
        return false;
      }
      if (filters.source && task.source !== filters.source) {
        return false;
      }
      if (filters.refresh) {
        const severity = refreshSignals.byTaskId[task.id]?.severity || 'low';
        if (severity !== filters.refresh) {
          return false;
        }
      }
      if (filters.reason === 'resonance' && !refreshSignals.byTaskId[task.id]?.resonanceDriven) {
        return false;
      }
      if (filters.reason === 'policy_source' && !refreshSignals.byTaskId[task.id]?.policySourceDriven) {
        return false;
      }
      if (filters.reason === 'bias_quality_core' && !refreshSignals.byTaskId[task.id]?.biasCompressionShift?.coreLegAffected) {
        return false;
      }
      if (
        filters.reason === 'selection_quality'
        && !(
          refreshSignals.byTaskId[task.id]?.selectionQualityDriven
          || refreshSignals.byTaskId[task.id]?.selectionQualityRunState?.active
        )
      ) {
        return false;
      }
      if (filters.reason === 'bias_quality' && !refreshSignals.byTaskId[task.id]?.biasCompressionDriven) {
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
    return sortTasksByRefreshPriority(
      matches,
      refreshSignals.byTaskId,
      Boolean(filters.refresh || filters.reason)
    );
  }, [filters, refreshSignals.byTaskId, tasks]);

  useEffect(() => {
    if (!filteredTasks.length) {
      if (selectedTaskId) {
        setSelectedTaskId('');
      }
      return;
    }
    const hasSelectedTask = filteredTasks.some((task) => task.id === selectedTaskId);
    if (!selectedTaskId || !hasSelectedTask) {
      setSelectedTaskId(filteredTasks[0].id);
    }
  }, [filteredTasks, selectedTaskId]);

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

  const selectedTaskRefreshSignal = selectedTaskId ? refreshSignals.byTaskId[selectedTaskId] : null;

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
      const primaryDriver = payload.primary_driver || payload.drivers?.[0] || null;
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
            <Space wrap size={6}>
              <Tag color="blue">{payload.implications.primary_view}</Tag>
              {payload.implications?.confidence ? (
                <Tag>{`置信度 ${payload.implications.confidence}`}</Tag>
              ) : null}
              {payload.implications?.confidence_score !== undefined && payload.implications?.confidence_score !== null ? (
                <Tag>{`评分 ${Number(payload.implications.confidence_score || 0).toFixed(2)}`}</Tag>
              ) : null}
            </Space>
          ) : null}
          {payload.implications?.confidence_reasons?.length ? (
            <Text type="secondary">
              置信度说明 {(payload.implications.confidence_reasons || []).slice(0, 2).join('；')}
            </Text>
          ) : null}
          {primaryDriver?.factor ? (
            <Text type="secondary">
              主驱动 {primaryDriver.factor}
              {primaryDriver.signal_strength !== undefined && primaryDriver.signal_strength !== null
                ? ` · 强度 ${Number(primaryDriver.signal_strength).toFixed(2)}`
                : ''}
              {primaryDriver.ranking_reason ? ` · ${primaryDriver.ranking_reason}` : ''}
            </Text>
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
        {payload.template_meta?.bias_strength_raw ? (
          <Text type="secondary">
            原始偏置 {Number(payload.template_meta.bias_strength_raw || 0).toFixed(1)}pp
            {payload.template_meta?.bias_strength ? ` · 生效偏置 ${Number(payload.template_meta.bias_strength || 0).toFixed(1)}pp` : ''}
          </Text>
        ) : null}
        {payload.template_meta?.bias_quality_label && payload.template_meta.bias_quality_label !== 'full' ? (
          <Text type="secondary">
            偏置收缩 {payload.template_meta.bias_quality_label}
            {payload.template_meta?.bias_scale ? ` · scale ${Number(payload.template_meta.bias_scale).toFixed(2)}x` : ''}
            {payload.template_meta?.bias_quality_reason ? ` · ${payload.template_meta.bias_quality_reason}` : ''}
          </Text>
        ) : null}
        {payload.template_meta?.core_leg_pressure?.affected ? (
          <Text type="secondary">
            核心腿受压 {payload.template_meta.core_leg_pressure.summary || payload.template_meta.core_leg_pressure.symbol}
          </Text>
        ) : null}
        {payload.allocation_overlay?.compressed_assets?.length ? (
          <Text type="secondary">
            压缩焦点 {payload.allocation_overlay.compressed_assets.join('，')}
            {payload.allocation_overlay.compression_summary?.compression_effect !== undefined
              ? ` · 收缩 ${Number(payload.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp`
              : ''}
          </Text>
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
        {payload.constraint_overlay?.binding_count ? (
          <Text type="secondary">
            组合约束触发 {payload.constraint_overlay.binding_count} 个 · 最大约束偏移 {(Number(payload.constraint_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
          </Text>
        ) : null}
        {payload.template_meta?.recommendation_tier ? (
          <Tag color="gold">{payload.template_meta.recommendation_tier}</Tag>
        ) : null}
        {payload.template_meta?.selection_quality?.label && payload.template_meta.selection_quality.label !== 'original' ? (
          <Tag color="orange">自动降级 {payload.template_meta.selection_quality.label}</Tag>
        ) : null}
        {payload.template_meta?.resonance_label && payload.template_meta.resonance_label !== 'mixed' ? (
          <Tag color="magenta">共振 {payload.template_meta.resonance_label}</Tag>
        ) : null}
        {payload.template_meta?.base_recommendation_score !== null
        && payload.template_meta?.base_recommendation_score !== undefined ? (
          <Text type="secondary">
            推荐强度 {Number(payload.template_meta.base_recommendation_score || 0).toFixed(2)}
            {payload.template_meta?.recommendation_score !== null && payload.template_meta?.recommendation_score !== undefined
              ? ` -> ${Number(payload.template_meta.recommendation_score || 0).toFixed(2)}`
              : ''}
            {payload.template_meta?.base_recommendation_tier
              ? ` · ${payload.template_meta.base_recommendation_tier} -> ${payload.template_meta.recommendation_tier || '-'}`
              : ''}
          </Text>
        ) : null}
        {payload.template_meta?.ranking_penalty ? (
          <Text type="secondary">
            排序惩罚 {Number(payload.template_meta.ranking_penalty || 0).toFixed(2)}
            {payload.template_meta?.ranking_penalty_reason ? ` · ${payload.template_meta.ranking_penalty_reason}` : ''}
          </Text>
        ) : null}
        {payload.template_meta?.recommendation_reason ? (
          <Text type="secondary">推荐依据 {payload.template_meta.recommendation_reason}</Text>
        ) : null}
        {payload.template_meta?.resonance_reason ? (
          <Text type="secondary">共振背景 {payload.template_meta.resonance_reason}</Text>
        ) : null}
        {payload.research_input?.macro ? (
          <Text type="secondary">
            宏观输入 分数 {Number(payload.research_input.macro.macro_score || 0).toFixed(2)}
            {' · '}
            Δ{Number(payload.research_input.macro.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(payload.research_input.macro.macro_score_delta || 0).toFixed(2)}
            {payload.research_input.macro.macro_signal_changed ? ' · 信号切换' : ''}
            {payload.research_input.macro.resonance?.label && payload.research_input.macro.resonance.label !== 'mixed'
              ? ` · 共振 ${payload.research_input.macro.resonance.label}`
              : ''}
            {payload.research_input.macro.policy_source_health?.label
            && payload.research_input.macro.policy_source_health.label !== 'unknown'
              ? ` · 政策源 ${payload.research_input.macro.policy_source_health.label}`
              : ''}
          </Text>
        ) : null}
        {payload.research_input?.macro?.policy_source_health?.reason ? (
          <Text type="secondary">
            政策源 {payload.research_input.macro.policy_source_health.reason}
          </Text>
        ) : null}
        {payload.research_input?.alt_data?.top_categories?.length ? (
          <Text type="secondary">
            另类数据 {(payload.research_input.alt_data.top_categories || [])
              .slice(0, 2)
              .map((item) => `${item.category} ${item.momentum === 'strengthening' ? '增强' : item.momentum === 'weakening' ? '走弱' : '稳定'} ${Number(item.delta_score || 0) >= 0 ? '+' : ''}${Number(item.delta_score || 0).toFixed(2)}`)
              .join('，')}
          </Text>
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
        {payload.execution_diagnostics?.liquidity_level ? (
          <Text type="secondary">
            流动性 {payload.execution_diagnostics.liquidity_level}
            {payload.execution_diagnostics.max_adv_usage !== undefined
              ? ` · Max ADV ${(Number(payload.execution_diagnostics.max_adv_usage || 0) * 100).toFixed(2)}%`
              : ''}
          </Text>
        ) : null}
        {payload.execution_diagnostics?.margin_level ? (
          <Text type="secondary">
            保证金 {payload.execution_diagnostics.margin_level}
            {payload.execution_diagnostics.margin_utilization !== undefined
              ? ` · ${(Number(payload.execution_diagnostics.margin_utilization || 0) * 100).toFixed(2)}%`
              : ''}
            {payload.execution_diagnostics.gross_leverage !== undefined
              ? ` · Gross ${Number(payload.execution_diagnostics.gross_leverage || 0).toFixed(2)}x`
              : ''}
          </Text>
        ) : null}
        {payload.execution_diagnostics?.beta_level ? (
          <Text type="secondary">
            Beta {payload.execution_diagnostics.beta_level}
            {payload.hedge_portfolio?.beta_neutrality?.beta !== undefined
              ? ` · ${Number(payload.hedge_portfolio.beta_neutrality.beta || 0).toFixed(2)}`
              : ''}
          </Text>
        ) : null}
        {payload.execution_diagnostics?.calendar_level ? (
          <Text type="secondary">
            日历 {payload.execution_diagnostics.calendar_level}
            {payload.data_alignment?.calendar_diagnostics?.max_mismatch_ratio !== undefined
              ? ` · mismatch ${(Number(payload.data_alignment.calendar_diagnostics.max_mismatch_ratio || 0) * 100).toFixed(2)}%`
              : ''}
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
                      <Space wrap size={6}>
                        <Text type="secondary">
                          Fair value {pricingValue || '-'} · {(payload.implications?.primary_view || '待判断')}
                        </Text>
                        {payload.implications?.confidence ? (
                          <Tag>{`置信度 ${payload.implications.confidence}`}</Tag>
                        ) : null}
                        {payload.implications?.confidence_score !== undefined && payload.implications?.confidence_score !== null ? (
                          <Tag>{`评分 ${Number(payload.implications.confidence_score || 0).toFixed(2)}`}</Tag>
                        ) : null}
                        {payload.primary_driver?.factor ? (
                          <Tag>{`主驱动 ${payload.primary_driver.factor}`}</Tag>
                        ) : null}
                      </Space>
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
                        {payload.execution_diagnostics?.liquidity_level ? (
                          <Text type="secondary">
                            流动性 {payload.execution_diagnostics.liquidity_level}
                            {payload.execution_diagnostics.max_adv_usage !== undefined
                              ? ` · Max ADV ${(Number(payload.execution_diagnostics.max_adv_usage || 0) * 100).toFixed(2)}%`
                              : ''}
                          </Text>
                        ) : null}
                        {payload.execution_diagnostics?.margin_level ? (
                          <Text type="secondary">
                            保证金 {payload.execution_diagnostics.margin_level}
                            {payload.execution_diagnostics.margin_utilization !== undefined
                              ? ` · ${(Number(payload.execution_diagnostics.margin_utilization || 0) * 100).toFixed(2)}%`
                              : ''}
                            {payload.execution_diagnostics.gross_leverage !== undefined
                              ? ` · Gross ${Number(payload.execution_diagnostics.gross_leverage || 0).toFixed(2)}x`
                              : ''}
                          </Text>
                        ) : null}
                        {payload.execution_diagnostics?.beta_level ? (
                          <Text type="secondary">
                            Beta {payload.execution_diagnostics.beta_level}
                            {payload.hedge_portfolio?.beta_neutrality?.beta !== undefined
                              ? ` · ${Number(payload.hedge_portfolio.beta_neutrality.beta || 0).toFixed(2)}`
                              : ''}
                          </Text>
                        ) : null}
                        {payload.execution_diagnostics?.calendar_level ? (
                          <Text type="secondary">
                            日历 {payload.execution_diagnostics.calendar_level}
                            {payload.data_alignment?.calendar_diagnostics?.max_mismatch_ratio !== undefined
                              ? ` · mismatch ${(Number(payload.data_alignment.calendar_diagnostics.max_mismatch_ratio || 0) * 100).toFixed(2)}%`
                              : ''}
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
                        {templateMeta.selection_quality?.label && templateMeta.selection_quality.label !== 'original' ? (
                          <Text type="secondary">
                            自动降级 {templateMeta.selection_quality.label}
                            {templateMeta.selection_quality?.reason ? ` · ${templateMeta.selection_quality.reason}` : ''}
                          </Text>
                        ) : null}
                        {templateMeta.base_recommendation_score !== null
                        && templateMeta.base_recommendation_score !== undefined ? (
                          <Text type="secondary">
                            推荐强度 {Number(templateMeta.base_recommendation_score || 0).toFixed(2)}
                            {templateMeta.recommendation_score !== null && templateMeta.recommendation_score !== undefined
                              ? ` -> ${Number(templateMeta.recommendation_score || 0).toFixed(2)}`
                              : ''}
                            {templateMeta.base_recommendation_tier
                              ? ` · ${templateMeta.base_recommendation_tier} -> ${templateMeta.recommendation_tier || '-'}`
                              : ''}
                          </Text>
                        ) : null}
                        {templateMeta.ranking_penalty ? (
                          <Text type="secondary">
                            排序惩罚 {Number(templateMeta.ranking_penalty || 0).toFixed(2)}
                            {templateMeta.ranking_penalty_reason ? ` · ${templateMeta.ranking_penalty_reason}` : ''}
                          </Text>
                        ) : null}
                        {templateMeta.resonance_label && templateMeta.resonance_label !== 'mixed' ? (
                          <Text type="secondary">
                            共振 {templateMeta.resonance_label}
                          </Text>
                        ) : null}
                        {templateMeta.bias_summary ? (
                          <Text type="secondary">
                            偏置 {templateMeta.bias_summary}
                          </Text>
                        ) : null}
                        {templateMeta.bias_strength_raw ? (
                          <Text type="secondary">
                            原始偏置 {Number(templateMeta.bias_strength_raw || 0).toFixed(1)}pp
                            {templateMeta.bias_strength ? ` · 生效偏置 ${Number(templateMeta.bias_strength || 0).toFixed(1)}pp` : ''}
                          </Text>
                        ) : null}
                        {templateMeta.bias_quality_label && templateMeta.bias_quality_label !== 'full' ? (
                          <Text type="secondary">
                            偏置收缩 {templateMeta.bias_quality_label}
                            {templateMeta.bias_scale ? ` · scale ${Number(templateMeta.bias_scale).toFixed(2)}x` : ''}
                          </Text>
                        ) : null}
                        {payload.allocation_overlay?.compressed_assets?.length ? (
                          <Text type="secondary">
                            压缩焦点 {payload.allocation_overlay.compressed_assets.join('，')}
                            {payload.allocation_overlay.compression_summary?.compression_effect !== undefined
                              ? ` · 收缩 ${Number(payload.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp`
                              : ''}
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
                        {payload.constraint_overlay?.binding_count ? (
                          <Text type="secondary">
                            约束 {payload.constraint_overlay.binding_count} 个 · 最大约束偏移 {(Number(payload.constraint_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
                          </Text>
                        ) : null}
                        {templateMeta.recommendation_reason ? (
                          <Text type="secondary">{templateMeta.recommendation_reason}</Text>
                        ) : null}
                        {templateMeta.resonance_reason ? (
                          <Text type="secondary">{templateMeta.resonance_reason}</Text>
                        ) : null}
                        {payload.research_input?.macro ? (
                          <Text type="secondary">
                            宏观 {Number(payload.research_input.macro.macro_score || 0).toFixed(2)}
                            {' · '}
                            Δ{Number(payload.research_input.macro.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(payload.research_input.macro.macro_score_delta || 0).toFixed(2)}
                            {payload.research_input.macro.resonance?.label && payload.research_input.macro.resonance.label !== 'mixed'
                              ? ` · 共振 ${payload.research_input.macro.resonance.label}`
                              : ''}
                            {payload.research_input.macro.policy_source_health?.label
                            && payload.research_input.macro.policy_source_health.label !== 'unknown'
                              ? ` · 政策源 ${payload.research_input.macro.policy_source_health.label}`
                              : ''}
                          </Text>
                        ) : null}
                        {payload.research_input?.macro?.policy_source_health?.reason ? (
                          <Text type="secondary">
                            政策源 {payload.research_input.macro.policy_source_health.reason}
                          </Text>
                        ) : null}
                        {payload.research_input?.alt_data?.top_categories?.length ? (
                          <Text type="secondary">
                            另类 {(payload.research_input.alt_data.top_categories || [])
                              .slice(0, 1)
                              .map((item) => `${item.category} ${item.momentum === 'strengthening' ? '增强' : item.momentum === 'weakening' ? '走弱' : '稳定'}`)
                              .join('，')}
                          </Text>
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
    const refreshSignal = refreshSignals.byTaskId[task.id];
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
            {templateMeta.selection_quality?.label && templateMeta.selection_quality.label !== 'original' ? (
              <Tag color="orange">自动降级</Tag>
            ) : null}
            {templateMeta.resonance_label && templateMeta.resonance_label !== 'mixed' ? (
              <Tag color="magenta">{templateMeta.resonance_label}</Tag>
            ) : null}
            {refreshSignal ? <Tag color={refreshSignal.refreshTone || 'default'}>{refreshSignal.refreshLabel}</Tag> : null}
            {refreshSignal?.resonanceDriven ? <Tag color="magenta">共振驱动</Tag> : null}
            {refreshSignal?.biasCompressionShift?.coreLegAffected ? <Tag color="volcano">核心腿受压</Tag> : null}
            {refreshSignal?.selectionQualityDriven ? <Tag color="orange">自动降级</Tag> : null}
            {refreshSignal?.policySourceDriven ? <Tag color="red">政策源驱动</Tag> : null}
            {refreshSignal?.biasCompressionDriven ? <Tag color="orange">偏置收缩</Tag> : null}
          </Space>
          <Text type="secondary">{task.snapshot?.headline || '暂无快照摘要'}</Text>
          {refreshSignal?.severity !== 'low' ? <Text type="secondary">{refreshSignal.summary}</Text> : null}
          {templateMeta.theme ? <Text type="secondary">{templateMeta.theme}</Text> : null}
          {templateMeta.resonance_reason ? <Text type="secondary">{templateMeta.resonance_reason}</Text> : null}
          {templateMeta.bias_summary ? <Text type="secondary">{templateMeta.bias_summary}</Text> : null}
          {templateMeta.base_recommendation_score !== null
          && templateMeta.base_recommendation_score !== undefined ? (
            <Text type="secondary">
              推荐强度 {Number(templateMeta.base_recommendation_score || 0).toFixed(2)}
              {templateMeta.recommendation_score !== null && templateMeta.recommendation_score !== undefined
                ? ` -> ${Number(templateMeta.recommendation_score || 0).toFixed(2)}`
                : ''}
            </Text>
          ) : null}
          {templateMeta.selection_quality?.label && templateMeta.selection_quality.label !== 'original' ? (
            <Text type="secondary">
              自动降级 {templateMeta.selection_quality.label}
              {templateMeta.selection_quality?.reason ? ` · ${templateMeta.selection_quality.reason}` : ''}
            </Text>
          ) : null}
          {templateMeta.bias_strength_raw ? (
            <Text type="secondary">
              原始偏置 {Number(templateMeta.bias_strength_raw || 0).toFixed(1)}pp
              {templateMeta.bias_strength ? ` · 生效偏置 ${Number(templateMeta.bias_strength || 0).toFixed(1)}pp` : ''}
            </Text>
          ) : null}
          {templateMeta.bias_quality_label && templateMeta.bias_quality_label !== 'full' ? (
            <Text type="secondary">
              偏置收缩 {templateMeta.bias_quality_label}
              {templateMeta.bias_scale ? ` · scale ${Number(templateMeta.bias_scale).toFixed(2)}x` : ''}
              {templateMeta.bias_quality_reason ? ` · ${templateMeta.bias_quality_reason}` : ''}
            </Text>
          ) : null}
          {templateMeta.core_leg_pressure?.affected ? (
            <Text type="secondary">
              核心腿受压 {templateMeta.core_leg_pressure.summary || templateMeta.core_leg_pressure.symbol}
            </Text>
          ) : null}
          {task.snapshot?.payload?.allocation_overlay?.compressed_assets?.length ? (
            <Text type="secondary">
              压缩焦点 {task.snapshot.payload.allocation_overlay.compressed_assets.join('，')}
              {task.snapshot.payload.allocation_overlay.compression_summary?.compression_effect !== undefined
                ? ` · 收缩 ${Number(task.snapshot.payload.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp`
                : ''}
            </Text>
          ) : null}
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
          {task.snapshot?.payload?.execution_diagnostics?.liquidity_level ? (
            <Text type="secondary">
              流动性 {task.snapshot.payload.execution_diagnostics.liquidity_level}
              {task.snapshot.payload.execution_diagnostics.max_adv_usage !== undefined
                ? ` · Max ADV ${(Number(task.snapshot.payload.execution_diagnostics.max_adv_usage || 0) * 100).toFixed(2)}%`
                : ''}
            </Text>
          ) : null}
          {task.snapshot?.payload?.execution_diagnostics?.margin_level ? (
            <Text type="secondary">
              保证金 {task.snapshot.payload.execution_diagnostics.margin_level}
              {task.snapshot.payload.execution_diagnostics.margin_utilization !== undefined
                ? ` · ${(Number(task.snapshot.payload.execution_diagnostics.margin_utilization || 0) * 100).toFixed(2)}%`
                : ''}
              {task.snapshot.payload.execution_diagnostics.gross_leverage !== undefined
                ? ` · Gross ${Number(task.snapshot.payload.execution_diagnostics.gross_leverage || 0).toFixed(2)}x`
                : ''}
            </Text>
          ) : null}
          {task.snapshot?.payload?.execution_diagnostics?.beta_level ? (
            <Text type="secondary">
              Beta {task.snapshot.payload.execution_diagnostics.beta_level}
              {task.snapshot.payload.hedge_portfolio?.beta_neutrality?.beta !== undefined
                ? ` · ${Number(task.snapshot.payload.hedge_portfolio.beta_neutrality.beta || 0).toFixed(2)}`
                : ''}
            </Text>
          ) : null}
          {task.snapshot?.payload?.execution_diagnostics?.calendar_level ? (
            <Text type="secondary">
              日历 {task.snapshot.payload.execution_diagnostics.calendar_level}
              {task.snapshot.payload.data_alignment?.calendar_diagnostics?.max_mismatch_ratio !== undefined
                ? ` · mismatch ${(Number(task.snapshot.payload.data_alignment.calendar_diagnostics.max_mismatch_ratio || 0) * 100).toFixed(2)}%`
                : ''}
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
          {task.snapshot?.payload?.research_input?.macro ? (
            <Text type="secondary">
              宏观 {Number(task.snapshot.payload.research_input.macro.macro_score || 0).toFixed(2)}
              {' · '}
              Δ{Number(task.snapshot.payload.research_input.macro.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(task.snapshot.payload.research_input.macro.macro_score_delta || 0).toFixed(2)}
              {task.snapshot.payload.research_input.macro.resonance?.label && task.snapshot.payload.research_input.macro.resonance.label !== 'mixed'
                ? ` · 共振 ${task.snapshot.payload.research_input.macro.resonance.label}`
                : ''}
              {task.snapshot.payload.research_input.macro.policy_source_health?.label
              && task.snapshot.payload.research_input.macro.policy_source_health.label !== 'unknown'
                ? ` · 政策源 ${task.snapshot.payload.research_input.macro.policy_source_health.label}`
                : ''}
            </Text>
          ) : null}
          {task.snapshot?.payload?.research_input?.macro?.policy_source_health?.reason ? (
            <Text type="secondary">
              政策源 {task.snapshot.payload.research_input.macro.policy_source_health.reason}
            </Text>
          ) : null}
          {task.snapshot?.payload?.research_input?.alt_data?.top_categories?.length ? (
            <Text type="secondary">
              另类 {(task.snapshot.payload.research_input.alt_data.top_categories || [])
                .slice(0, 1)
                .map((item) => `${item.category} ${item.momentum === 'strengthening' ? '增强' : item.momentum === 'weakening' ? '走弱' : '稳定'}`)
                .join('，')}
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
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic title="建议更新" value={refreshStats.high} valueStyle={{ color: '#cf1322' }} />
            <Text type="secondary">宏观或另类数据与保存输入明显脱节，建议优先重开研究。</Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic title="建议复核" value={refreshStats.medium} valueStyle={{ color: '#d48806' }} />
            <Text type="secondary">核心驱动在变化，适合先做一次中间复核，再决定是否更新快照。</Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic title="共振驱动" value={refreshStats.resonance} valueStyle={{ color: '#c41d7f' }} />
            <Text type="secondary">这些任务的优先级变化来自宏观共振结构切换，更值得优先看。</Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic title="核心腿受压" value={refreshStats.biasQualityCore} valueStyle={{ color: '#fa541c' }} />
            <Text type="secondary">这些任务的主题核心腿已经成为偏置收缩焦点，通常比普通配置压缩更值得先处理。</Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic title="自动降级" value={refreshStats.selectionQuality} valueStyle={{ color: '#d48806' }} />
            <Text type="secondary">这些任务已经从原始推荐切到降级处理，说明主题排序本身正在被重新评估。</Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic title="政策源驱动" value={refreshStats.policySource} valueStyle={{ color: '#cf1322' }} />
            <Text type="secondary">这些任务的更新优先级来自政策正文抓取质量退化，应先确认研究输入是否仍然可靠。</Text>
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card bordered={false}>
            <Statistic title="偏置收缩" value={refreshStats.biasQuality} valueStyle={{ color: '#d46b08' }} />
            <Text type="secondary">这些任务的宏观偏置强度已经被证据质量压缩，建议先确认模板还适不适合维持原有配置力度。</Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={24}>
          <Card bordered={false}>
            <Statistic title="继续观察" value={refreshStats.low} valueStyle={{ color: '#1677ff' }} />
            <Text type="secondary">当前输入与保存快照仍然相近，可以继续沿现有研究路线推进。</Text>
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

                {selectedTask.type === 'cross_market' ? (
                  <Card
                    size="small"
                    title="输入变化与更新建议"
                    bordered={false}
                    extra={
                      selectedTaskRefreshSignal ? (
                        <Space wrap>
                          <Tag color={selectedTaskRefreshSignal.refreshTone || 'default'}>
                            {selectedTaskRefreshSignal.refreshLabel}
                          </Tag>
                          {selectedTaskRefreshSignal.resonanceDriven ? (
                            <Tag color="magenta">共振驱动</Tag>
                          ) : null}
                          {selectedTaskRefreshSignal.biasCompressionShift?.coreLegAffected ? (
                            <Tag color="volcano">核心腿受压</Tag>
                          ) : null}
                          {selectedTaskRefreshSignal.selectionQualityDriven ? (
                            <Tag color="orange">自动降级</Tag>
                          ) : null}
                          {selectedTaskRefreshSignal.selectionQualityRunState?.active ? (
                            <Tag color="gold">降级运行</Tag>
                          ) : null}
                          {selectedTaskRefreshSignal.policySourceDriven ? (
                            <Tag color="red">政策源驱动</Tag>
                          ) : null}
                          {selectedTaskRefreshSignal.biasCompressionDriven ? (
                            <Tag color="orange">偏置收缩</Tag>
                          ) : null}
                        </Space>
                      ) : null
                    }
                  >
                    {selectedTaskRefreshSignal ? (
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Text strong>{selectedTaskRefreshSignal.recommendation}</Text>
                        <Text type="secondary">{selectedTaskRefreshSignal.summary}</Text>
                        {selectedTaskRefreshSignal.macroShift ? (
                          <Text type="secondary">
                            当前宏观分数 {Number(selectedTaskRefreshSignal.macroShift.currentScore || 0).toFixed(2)}
                            {' · '}
                            保存时 {Number(selectedTaskRefreshSignal.macroShift.savedScore || 0).toFixed(2)}
                            {' · '}
                            Δ{Number(selectedTaskRefreshSignal.macroShift.scoreGap || 0) >= 0 ? '+' : ''}{Number(selectedTaskRefreshSignal.macroShift.scoreGap || 0).toFixed(2)}
                            {selectedTaskRefreshSignal.macroShift.signalShift
                              ? ` · 信号 ${selectedTaskRefreshSignal.macroShift.savedSignal}→${selectedTaskRefreshSignal.macroShift.currentSignal}`
                              : ''}
                          </Text>
                        ) : null}
                        {selectedTaskRefreshSignal.policySourceShift ? (
                          <Text type="secondary">
                            政策源 {selectedTaskRefreshSignal.policySourceShift.savedLabel}→{selectedTaskRefreshSignal.policySourceShift.currentLabel}
                            {selectedTaskRefreshSignal.policySourceShift.fullTextRatioGap
                              ? ` · 正文覆盖 ${selectedTaskRefreshSignal.policySourceShift.fullTextRatioGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.policySourceShift.fullTextRatioGap || 0).toFixed(2)}`
                              : ''}
                            {selectedTaskRefreshSignal.policySourceShift.currentReason
                              ? ` · ${selectedTaskRefreshSignal.policySourceShift.currentReason}`
                              : ''}
                          </Text>
                        ) : null}
                        {selectedTaskRefreshSignal.selectionQualityShift ? (
                          <Text type="secondary">
                            自动降级 {selectedTaskRefreshSignal.selectionQualityShift.savedLabel}→{selectedTaskRefreshSignal.selectionQualityShift.currentLabel}
                            {selectedTaskRefreshSignal.selectionQualityShift.penaltyGap
                              ? ` · 惩罚 ${selectedTaskRefreshSignal.selectionQualityShift.penaltyGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.selectionQualityShift.penaltyGap || 0).toFixed(2)}`
                              : ''}
                            {selectedTaskRefreshSignal.selectionQualityShift.currentReason
                              ? ` · ${selectedTaskRefreshSignal.selectionQualityShift.currentReason}`
                              : ''}
                          </Text>
                        ) : null}
                        {selectedTaskRefreshSignal.selectionQualityRunState?.active ? (
                          <Text type="secondary">
                            当前结果按 {selectedTaskRefreshSignal.selectionQualityRunState.label} 强度运行
                            {selectedTaskRefreshSignal.selectionQualityRunState.baseScore || selectedTaskRefreshSignal.selectionQualityRunState.effectiveScore
                              ? ` · 推荐分 ${Number(selectedTaskRefreshSignal.selectionQualityRunState.baseScore || 0).toFixed(2)}→${Number(selectedTaskRefreshSignal.selectionQualityRunState.effectiveScore || 0).toFixed(2)}`
                              : ''}
                            {selectedTaskRefreshSignal.selectionQualityRunState.baseTier || selectedTaskRefreshSignal.selectionQualityRunState.effectiveTier
                              ? ` · Tier ${selectedTaskRefreshSignal.selectionQualityRunState.baseTier || '-'}→${selectedTaskRefreshSignal.selectionQualityRunState.effectiveTier || '-'}`
                              : ''}
                            {selectedTaskRefreshSignal.selectionQualityRunState.rankingPenalty
                              ? ` · 惩罚 ${Number(selectedTaskRefreshSignal.selectionQualityRunState.rankingPenalty || 0).toFixed(2)}`
                              : ''}
                            {selectedTaskRefreshSignal.selectionQualityRunState.reason
                              ? ` · ${selectedTaskRefreshSignal.selectionQualityRunState.reason}`
                              : ''}
                          </Text>
                        ) : null}
                        {selectedTaskRefreshSignal.biasCompressionShift ? (
                          <Text type="secondary">
                            偏置收缩 {selectedTaskRefreshSignal.biasCompressionShift.savedLabel}→{selectedTaskRefreshSignal.biasCompressionShift.currentLabel}
                            {' · '}
                            scale {Number(selectedTaskRefreshSignal.biasCompressionShift.savedScale || 1).toFixed(2)}x→{Number(selectedTaskRefreshSignal.biasCompressionShift.currentScale || 1).toFixed(2)}x
                            {selectedTaskRefreshSignal.biasCompressionShift.topCompressedAsset
                              ? ` · 压缩焦点 ${selectedTaskRefreshSignal.biasCompressionShift.topCompressedAsset}`
                              : ''}
                            {selectedTaskRefreshSignal.biasCompressionShift.coreLegAffected
                              ? ' · 主题核心腿已进入压缩焦点'
                              : ''}
                            {selectedTaskRefreshSignal.biasCompressionShift.currentReason
                              ? ` · ${selectedTaskRefreshSignal.biasCompressionShift.currentReason}`
                              : ''}
                          </Text>
                        ) : null}
                        {selectedTaskRefreshSignal.altShift?.changedCategories?.length ? (
                          <Text type="secondary">
                            另类变化 {selectedTaskRefreshSignal.altShift.changedCategories
                              .slice(0, 2)
                              .map((item) => `${item.category} ${item.previousMomentum === 'strengthening' ? '增强' : item.previousMomentum === 'weakening' ? '走弱' : '稳定'}→${item.currentMomentum === 'strengthening' ? '增强' : item.currentMomentum === 'weakening' ? '走弱' : '稳定'}`)
                              .join('，')}
                          </Text>
                        ) : null}
                        {selectedTaskRefreshSignal.altShift?.emergentCategories?.length ? (
                          <Text type="secondary">
                            新热点 {selectedTaskRefreshSignal.altShift.emergentCategories
                              .map((item) => `${item.category} ${item.momentum === 'strengthening' ? '增强' : item.momentum === 'weakening' ? '走弱' : '稳定'} ${item.delta >= 0 ? '+' : ''}${Number(item.delta || 0).toFixed(2)}`)
                              .join('，')}
                          </Text>
                        ) : null}
                        {selectedTaskRefreshSignal.factorShift?.length ? (
                          <Text type="secondary">
                            因子变化 {selectedTaskRefreshSignal.factorShift
                              .map((item) => `${item.label} ${item.zScoreDelta >= 0 ? '+' : ''}${Number(item.zScoreDelta || 0).toFixed(2)}${item.signalChanged ? ' shift' : ''}`)
                              .join('，')}
                          </Text>
                        ) : null}
                      </Space>
                    ) : (
                      <Text type="secondary">当前任务还没有足够的输入快照，先继续积累研究记录。</Text>
                    )}
                  </Card>
                ) : null}

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
