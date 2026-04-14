import { extractWorkbenchViewFingerprint } from '../../utils/workbenchViewFingerprint';

export const MAIN_STATUSES = ['new', 'in_progress', 'blocked', 'complete'];

export const STATUS_LABEL = {
  new: '新建',
  in_progress: '进行中',
  blocked: '阻塞',
  complete: '已完成',
  archived: '已归档',
};

export const TYPE_OPTIONS = [
  { label: '全部类型', value: '' },
  { label: 'Pricing', value: 'pricing' },
  { label: 'Cross-Market', value: 'cross_market' },
  { label: 'Macro Mispricing', value: 'macro_mispricing' },
  { label: 'Trade Thesis', value: 'trade_thesis' },
];

export const REFRESH_OPTIONS = [
  { label: '全部更新状态', value: '' },
  { label: '建议更新', value: 'high' },
  { label: '建议复核', value: 'medium' },
  { label: '继续观察', value: 'low' },
];

export const SNAPSHOT_VIEW_OPTIONS = [
  { label: '全部快照视角', value: '' },
  { label: '带筛选视角快照', value: 'filtered' },
  { label: '带任务焦点快照', value: 'scoped' },
];

export const REASON_OPTIONS = [
  { label: '全部更新原因', value: '' },
  { label: '自动排序首次入列', value: 'priority_new' },
  { label: '自动排序升档', value: 'priority_escalated' },
  { label: '自动排序缓和', value: 'priority_relaxed' },
  { label: '自动排序同类更新', value: 'priority_updated' },
  { label: '共振驱动', value: 'resonance' },
  { label: '核心腿受压', value: 'bias_quality_core' },
  { label: '降级运行', value: 'selection_quality_active' },
  { label: '复核语境切换', value: 'review_context' },
  { label: '结构衰败/系统雷达', value: 'structural_decay' },
  { label: '交易 Thesis 漂移', value: 'trade_thesis' },
  { label: '人的维度', value: 'people_layer' },
  { label: '人的维度', value: 'people_fragility' },
  { label: '部门混乱', value: 'department_chaos' },
  { label: '政策执行混乱', value: 'policy_execution' },
  { label: '自动降级', value: 'selection_quality' },
  { label: '输入可靠度', value: 'input_reliability' },
  { label: '来源健康退化', value: 'source_health_degradation' },
  { label: '政策源驱动', value: 'policy_source' },
  { label: '偏置收缩', value: 'bias_quality' },
];

export const REFRESH_REASON_LABELS = {
  resonance: '共振驱动',
  bias_quality_core: '核心腿受压',
  selection_quality_active: '降级运行',
  review_context: '复核语境切换',
  structural_decay: '结构衰败/系统雷达',
  trade_thesis: '交易 Thesis 漂移',
  people_layer: '人的维度',
  people_fragility: '人的维度',
  department_chaos: '部门混乱',
  policy_execution: '政策执行混乱',
  selection_quality: '自动降级',
  input_reliability: '输入可靠度',
  source_health_degradation: '来源健康退化',
  policy_source: '政策源驱动',
  bias_quality: '偏置收缩',
  macro: '宏观信号漂移',
  alt_data: '另类数据变化',
  factor_shift: '因子信号变化',
  observe: '继续观察',
};

export const formatRefreshReasonLabel = (reason = 'observe') => REFRESH_REASON_LABELS[reason] || REFRESH_REASON_LABELS.observe;

export const REFRESH_PRIORITY_CHANGE_LABELS = {
  new: '首次记录',
  escalated: '升级',
  relaxed: '缓和',
  updated: '更新',
};

export const REFRESH_PRIORITY_CHANGE_COLORS = {
  new: 'blue',
  escalated: 'red',
  relaxed: 'green',
  updated: 'gold',
};

export const formatRefreshPriorityChangeLabel = (changeType = 'updated') =>
  REFRESH_PRIORITY_CHANGE_LABELS[changeType] || REFRESH_PRIORITY_CHANGE_LABELS.updated;

export const getRefreshPriorityChangeColor = (changeType = 'updated') =>
  REFRESH_PRIORITY_CHANGE_COLORS[changeType] || REFRESH_PRIORITY_CHANGE_COLORS.updated;

export const findWorkbenchOptionLabel = (options = [], value = '', fallback = '') => {
  if (!value) {
    return '';
  }

  const matchedOption = (options || []).find((option) => option?.value === value);
  return matchedOption?.label || fallback || value;
};

export const buildActiveWorkbenchFilterMeta = (
  filters = {},
  {
    reasonOptions = [],
    refreshOptions = [],
    snapshotViewOptions = [],
    typeOptions = [],
    sourceOptions = [],
  } = {}
) => {
  const keyword = filters?.keyword?.trim?.() || '';
  const reason = filters?.reason || '';
  const refresh = filters?.refresh || '';
  const snapshotView = filters?.snapshotView || '';
  const snapshotFingerprint = filters?.snapshotFingerprint || '';
  const snapshotSummary = filters?.snapshotSummary?.trim?.() || '';
  const type = filters?.type || '';
  const source = filters?.source || '';

  const items = [];

  if (reason) {
    items.push({
      field: 'reason',
      color: reason.startsWith('priority_') ? 'magenta' : 'purple',
      text: `${reason.startsWith('priority_') ? '快速视图' : '更新原因'}：${findWorkbenchOptionLabel(reasonOptions, reason, formatRefreshReasonLabel(reason))}`,
    });
  }

  if (keyword) {
    items.push({
      field: 'keyword',
      color: 'processing',
      text: `关键词：${keyword}`,
    });
  }

  if (refresh) {
    items.push({
      field: 'refresh',
      color: 'gold',
      text: `更新级别：${findWorkbenchOptionLabel(refreshOptions, refresh, refresh)}`,
    });
  }

  if (snapshotView) {
    items.push({
      field: 'snapshotView',
      color: 'lime',
      text: `快照视角：${findWorkbenchOptionLabel(snapshotViewOptions, snapshotView, snapshotView)}`,
    });
  }

  if (snapshotSummary || snapshotFingerprint) {
    items.push({
      field: 'snapshotSummary',
      color: 'volcano',
      text: `研究视角：${snapshotSummary || snapshotFingerprint}`,
    });
  }

  if (type) {
    items.push({
      field: 'type',
      color: 'geekblue',
      text: `类型：${findWorkbenchOptionLabel(typeOptions, type, type)}`,
    });
  }

  if (source) {
    items.push({
      field: 'source',
      color: 'cyan',
      text: `来源：${findWorkbenchOptionLabel(sourceOptions, source, source)}`,
    });
  }

  return items;
};

export const buildWorkbenchViewSummary = (
  filters = {},
  {
    reasonOptions = [],
    refreshOptions = [],
    snapshotViewOptions = [],
    typeOptions = [],
    sourceOptions = [],
    selectedTaskId = '',
    selectedTaskTitle = '',
  } = {}
) => {
  const activeFilterMeta = buildActiveWorkbenchFilterMeta(filters, {
    reasonOptions,
    refreshOptions,
    snapshotViewOptions,
    typeOptions,
    sourceOptions,
  });
  const summaryText = activeFilterMeta.length
    ? activeFilterMeta.map((item) => item.text).join(' · ')
    : '全部任务视图';
  const scopedTaskLabel = selectedTaskTitle
    ? `当前定位：${selectedTaskTitle}`
    : selectedTaskId
      ? `当前定位：${selectedTaskId}`
      : '';

  return {
    hasActiveFilters: activeFilterMeta.length > 0,
    headline: summaryText,
    note: activeFilterMeta.length
      ? '打开这个链接后，工作台会恢复到同一组筛选条件和当前任务焦点。'
      : '当前没有额外筛选，分享后会打开完整工作台视图。',
    scopedTaskLabel,
  };
};

export const extractSnapshotViewContext = (snapshot = null) => {
  const payload = snapshot?.payload || {};
  const viewContext = payload.view_context || payload.workbench_view_context || {};
  return {
    hasFilters: Boolean(viewContext.has_filters),
    fingerprint: extractWorkbenchViewFingerprint(viewContext),
    summary: viewContext.summary || '',
    scopedTaskLabel: viewContext.scoped_task_label || '',
    note: viewContext.note || '',
  };
};

export const buildSnapshotViewSummaryOptions = (tasks = [], limit = 6) => {
  const buckets = new Map();

  (tasks || []).forEach((task) => {
    const snapshotViewContext = extractSnapshotViewContext(task?.snapshot);
    const summary = String(snapshotViewContext.summary || '').trim();
    const fingerprint = String(snapshotViewContext.fingerprint || '').trim();
    const bucketKey = fingerprint || summary;
    if (!bucketKey) {
      return;
    }

    const current = buckets.get(bucketKey) || {
      value: summary,
      fingerprint,
      label: summary,
      count: 0,
      scopedCount: 0,
      latestAt: '',
    };
    current.count += 1;
    if (snapshotViewContext.scopedTaskLabel) {
      current.scopedCount += 1;
    }

    const latestAt = String(task?.snapshot?.saved_at || task?.updated_at || task?.created_at || '');
    if (latestAt && (!current.latestAt || latestAt > current.latestAt)) {
      current.latestAt = latestAt;
    }

    buckets.set(bucketKey, current);
  });

  return Array.from(buckets.values())
    .sort((left, right) =>
      Number(right.count || 0) - Number(left.count || 0)
      || Number(right.scopedCount || 0) - Number(left.scopedCount || 0)
      || String(right.latestAt || '').localeCompare(String(left.latestAt || ''))
    )
    .slice(0, limit);
};

export const extractLatestRefreshPriorityEvent = (task = null) =>
  (task?.timeline || []).find((event) => event?.type === 'refresh_priority') || null;

export const buildRefreshPriorityChangeSummary = (event = null) => {
  const meta = event?.meta || {};
  const changeType = meta.change_type || '';
  const reasonLabel = meta.reason_label || '';
  const previousReasonLabel = meta.previous_reason_label || '';
  const urgencyDelta = meta.urgency_delta;
  const priorityWeightDelta = meta.priority_weight_delta;

  const deltaSummary = [
    urgencyDelta !== undefined && urgencyDelta !== null
      ? `紧急度 ${Number(urgencyDelta) >= 0 ? '+' : ''}${Number(urgencyDelta).toFixed(1)}`
      : '',
    priorityWeightDelta !== undefined && priorityWeightDelta !== null
      ? `排序权重 ${Number(priorityWeightDelta) >= 0 ? '+' : ''}${Number(priorityWeightDelta).toFixed(1)}`
      : '',
  ].filter(Boolean).join(' · ');

  if (changeType === 'new') {
    return '首次进入自动排序队列';
  }

  if (changeType === 'escalated') {
    return [
      previousReasonLabel ? `较上次从${previousReasonLabel}升档` : `较上次${reasonLabel || '自动排序'}升档`,
      deltaSummary,
    ].filter(Boolean).join(' · ');
  }

  if (changeType === 'relaxed') {
    return [
      previousReasonLabel ? `较上次从${previousReasonLabel}缓和` : `较上次${reasonLabel || '自动排序'}缓和`,
      deltaSummary,
    ].filter(Boolean).join(' · ');
  }

  if (changeType === 'updated') {
    return meta.reason_changed && previousReasonLabel
      ? `自动排序原因由${previousReasonLabel}切换到${reasonLabel || '当前原因'}`
      : '同类风险仍在驱动自动排序';
  }

  return '';
};

export const STATUS_COLOR = {
  new: 'blue',
  in_progress: 'processing',
  blocked: 'orange',
  complete: 'green',
  archived: 'default',
};

export const TIMELINE_COLOR = {
  created: 'blue',
  status_changed: 'orange',
  snapshot_saved: 'green',
  metadata_updated: 'purple',
  comment_added: 'cyan',
  comment_deleted: 'red',
  board_reordered: 'gold',
  refresh_priority: 'red',
};

export const formatPricingScenarioSummary = (scenarios = []) => {
  const bearCase = (scenarios || []).find((item) => item?.name === 'bear') || null;
  const baseCase = (scenarios || []).find((item) => item?.name === 'base') || null;
  const bullCase = (scenarios || []).find((item) => item?.name === 'bull') || null;
  const summaryParts = [
    bearCase?.intrinsic_value != null ? `悲观 ${Number(bearCase.intrinsic_value).toFixed(2)}` : null,
    baseCase?.intrinsic_value != null ? `基准 ${Number(baseCase.intrinsic_value).toFixed(2)}` : null,
    bullCase?.intrinsic_value != null ? `乐观 ${Number(bullCase.intrinsic_value).toFixed(2)}` : null,
  ].filter(Boolean);

  return summaryParts.length ? `DCF 情景 ${summaryParts.join(' / ')}` : '';
};

export const sortTasksByRefreshPriority = (tasks = [], refreshLookup = {}, enablePriority = false) => {
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

export const formatContextValue = (value) => {
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

export const formatTimelineType = (value) => ({
  created: '创建',
  status_changed: '状态',
  snapshot_saved: '快照',
  metadata_updated: '元信息',
  comment_added: '评论',
  comment_deleted: '删除',
  board_reordered: '排序',
  refresh_priority: '自动排序',
}[value] || '事件');

export const sortByBoardOrder = (left, right) => {
  const orderGap = Number(left.board_order || 0) - Number(right.board_order || 0);
  if (orderGap !== 0) {
    return orderGap;
  }
  return String(left.updated_at || '').localeCompare(String(right.updated_at || ''));
};

export const orderWorkbenchQueueTasks = (tasks = [], enablePriority = false) => {
  const list = [...tasks];
  if (enablePriority) {
    return list;
  }

  const orderedMain = MAIN_STATUSES.flatMap((status) =>
    list
      .filter((task) => task.status === status)
      .sort(sortByBoardOrder)
  );
  const remainder = list
    .filter((task) => !MAIN_STATUSES.includes(task.status))
    .sort(sortByBoardOrder);

  return [...orderedMain, ...remainder];
};

export const normalizeBoardOrders = (tasks) => {
  const cloned = tasks.map((task) => ({ ...task }));
  MAIN_STATUSES.forEach((status) => {
    const lane = cloned.filter((task) => task.status === status).sort(sortByBoardOrder);
    lane.forEach((task, index) => {
      task.board_order = index;
    });
  });
  return cloned;
};

export const moveBoardTask = (tasks, draggedTaskId, targetStatus, targetTaskId = null) => {
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

export const buildReorderPayload = (tasks) =>
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
