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
];

export const REFRESH_OPTIONS = [
  { label: '全部更新状态', value: '' },
  { label: '建议更新', value: 'high' },
  { label: '建议复核', value: 'medium' },
  { label: '继续观察', value: 'low' },
];

export const REASON_OPTIONS = [
  { label: '全部更新原因', value: '' },
  { label: '共振驱动', value: 'resonance' },
  { label: '核心腿受压', value: 'bias_quality_core' },
  { label: '降级运行', value: 'selection_quality_active' },
  { label: '复核语境切换', value: 'review_context' },
  { label: '自动降级', value: 'selection_quality' },
  { label: '输入可靠度', value: 'input_reliability' },
  { label: '政策源驱动', value: 'policy_source' },
  { label: '偏置收缩', value: 'bias_quality' },
];

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
}[value] || '事件');

export const sortByBoardOrder = (left, right) => {
  const orderGap = Number(left.board_order || 0) - Number(right.board_order || 0);
  if (orderGap !== 0) {
    return orderGap;
  }
  return String(left.updated_at || '').localeCompare(String(right.updated_at || ''));
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
