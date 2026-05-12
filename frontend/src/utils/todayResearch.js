import {
  BACKTEST_RESEARCH_SNAPSHOTS_KEY,
  loadBacktestResearchSnapshots,
} from './backtestWorkspace';
import {
  ALERT_HIT_HISTORY_STORAGE_KEY,
  loadAlertHitHistory,
} from './realtimeSignals';
import {
  INDUSTRY_ALERT_HISTORY_STORAGE_KEY,
  INDUSTRY_SAVED_VIEWS_STORAGE_KEY,
  INDUSTRY_WATCHLIST_STORAGE_KEY,
  pruneIndustryAlertHistory,
} from '../components/industry/industryShared';

export const REALTIME_REVIEW_SNAPSHOT_STORAGE_KEY = 'realtime-review-snapshots';
export const REALTIME_TIMELINE_STORAGE_KEY = 'realtime-timeline-events';
export const PRICE_ALERTS_STORAGE_KEY = 'price_alerts';

export const TODAY_RESEARCH_TYPE_LABELS = {
  backtest: '回测快照',
  realtime_review: '实时复盘',
  realtime_alert: '实时提醒',
  realtime_event: '实时事件',
  industry_watch: '行业观察',
  industry_alert: '行业提醒',
  manual: '手动记录',
  trade_plan: '交易计划',
};

export const TODAY_RESEARCH_STATUS_LABELS = {
  open: '待处理',
  watching: '跟踪中',
  snoozed: '已稍后',
  done: '已完成',
  dismissed: '已忽略',
  archived: '已归档',
};

export const TODAY_RESEARCH_PRIORITY_LABELS = {
  high: '高',
  medium: '中',
  low: '低',
};

export const RESEARCH_INBOX_BUCKET_LABELS = {
  actionable: '需处理',
  watch: '继续观察',
  snoozed: '稍后',
  read_later: '稍后阅读',
  archived: '已归档',
};

export const RESEARCH_INBOX_BUCKET_ORDER = ['actionable', 'watch', 'snoozed', 'read_later', 'archived'];

export const RESEARCH_ACTION_KIND_LABELS = {
  review_alert: '复核提醒',
  confirm_trade_plan: '确认交易计划',
  review_backtest: '复核回测',
  continue_realtime_review: '继续实时复盘',
  follow_watchlist: '跟进行业观察',
  open_context: '打开上下文',
};

const STATUS_RANK = {
  open: 0,
  watching: 1,
  snoozed: 2,
  done: 3,
  dismissed: 4,
  archived: 5,
};

const PRIORITY_RANK = {
  high: 0,
  medium: 1,
  low: 2,
};

const INBOX_BUCKET_RANK = RESEARCH_INBOX_BUCKET_ORDER.reduce((result, bucket, index) => ({
  ...result,
  [bucket]: index,
}), {});

const INBOX_ACTIVE_STATUSES = new Set(['open', 'watching']);
const INBOX_ACTION_TYPES = new Set(['realtime_alert', 'industry_alert', 'trade_plan']);
const INBOX_HIGH_SIGNAL_RE = /(alert|hit|trigger|breakout|signal|urgent|risk|anomaly|buy|sell|提醒|命中|触发|突破|信号|异动|异常|风险|买入|卖出|交易计划|计划)/i;
const INBOX_WATCH_SIGNAL_RE = /(watch|monitor|pending|review|observe|观察|跟踪|复盘|待确认|继续看|列表)/i;
const DEFAULT_INBOX_RECENT_WINDOW_HOURS = 72;
const DEFAULT_RESEARCH_ACTION_LIMIT = 12;
const RESEARCH_ACTION_BUCKET_RANK = {
  actionable: 0,
  watch: 1,
  snoozed: 2,
  read_later: 3,
};
const RESEARCH_ACTION_KIND_RANK = {
  review_alert: 0,
  confirm_trade_plan: 1,
  review_backtest: 2,
  continue_realtime_review: 3,
  follow_watchlist: 4,
  open_context: 5,
};
const EMPTY_RESEARCH_ACTION_COUNTS = {
  total: 0,
  actionable: 0,
  watch: 0,
  snoozed: 0,
  read_later: 0,
  high: 0,
};

const safeArray = (value) => (Array.isArray(value) ? value : []);
const ACTIVE_RESEARCH_STATUSES = new Set(['open', 'watching']);

const stringifyText = (value) => (value === null || value === undefined ? '' : String(value));
const hasLegacyFallbackValue = (value) => value !== null && value !== undefined && value !== '';
const pickLegacyValue = (value, fallback) => (hasLegacyFallbackValue(value) ? value : fallback);

const normalizeSearchText = (value) => stringifyText(value).trim().toLowerCase();

const buildEntrySearchText = (entry) => [
  entry.title,
  entry.summary,
  entry.note,
  entry.symbol,
  entry.industry,
  entry.source,
  entry.source_label,
  TODAY_RESEARCH_TYPE_LABELS[entry.type],
  TODAY_RESEARCH_STATUS_LABELS[entry.status],
  TODAY_RESEARCH_PRIORITY_LABELS[entry.priority],
  entry.action?.label,
  ...safeArray(entry.tags),
].filter(Boolean).join(' ').toLowerCase();

export const safeReadJsonStorage = (key, fallback) => {
  if (typeof window === 'undefined') {
    return fallback;
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
};

const normalizeIso = (value, fallback = new Date().toISOString()) => {
  const text = String(value || '').trim();
  if (!text) return fallback;
  const timestamp = Date.parse(text);
  return Number.isNaN(timestamp) ? fallback : new Date(timestamp).toISOString();
};

const normalizeSymbol = (value) => stringifyText(value).trim().toUpperCase();

const compactText = (value, max = 240) => stringifyText(value).trim().slice(0, max);

const compactLabelText = (value, max = 120) => {
  if (value === null || value === undefined || typeof value === 'boolean') {
    return '';
  }
  return compactText(value, max);
};

const normalizeTags = (value) => {
  const tags = [];
  const seen = new Set();
  for (const item of safeArray(value)) {
    if (item === null || item === undefined || typeof item === 'boolean') {
      continue;
    }
    const tag = compactText(item, 40);
    if (!tag || seen.has(tag)) {
      continue;
    }
    tags.push(tag);
    seen.add(tag);
    if (tags.length >= 8) {
      break;
    }
  }
  return tags;
};

const normalizeLifecycle = (value = {}, fallbackStatus = 'open') => {
  if (!value || typeof value !== 'object') {
    return {};
  }
  const status = TODAY_RESEARCH_STATUS_LABELS[value.status] ? value.status : fallbackStatus;
  return {
    ...value,
    status,
    note: compactText(value.note, 1200),
    updated_at: value.updated_at ? normalizeIso(value.updated_at) : undefined,
  };
};

const compactNumber = (value, fallback = null) => {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
};

const toPercentText = (value) => {
  const numericValue = compactNumber(value);
  if (numericValue === null) return '--';
  return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(2)}%`;
};

export const normalizeResearchEntry = (entry = {}, fallbackIndex = 0) => {
  const type = TODAY_RESEARCH_TYPE_LABELS[entry.type] ? entry.type : 'manual';
  const status = TODAY_RESEARCH_STATUS_LABELS[entry.status] ? entry.status : 'open';
  const priority = TODAY_RESEARCH_PRIORITY_LABELS[entry.priority] ? entry.priority : 'medium';
  const createdAt = normalizeIso(entry.created_at || entry.createdAt);
  const updatedAt = normalizeIso(entry.updated_at || entry.updatedAt || createdAt, createdAt);
  const symbol = normalizeSymbol(entry.symbol);
  const industry = compactText(pickLegacyValue(entry.industry, entry.industry_name), 120);
  const title = compactText(entry.title, 180) || symbol || industry || '研究记录';

  return {
    id: compactText(entry.id, 180) || `research_${type}_${fallbackIndex}`,
    type,
    status,
    priority,
    title,
    summary: compactText(entry.summary, 360),
    note: compactText(entry.note, 1200),
    symbol,
    industry,
    source: compactText(entry.source, 80) || type,
    source_label: (
      compactText(pickLegacyValue(entry.source_label, entry.sourceLabel), 80)
      || TODAY_RESEARCH_TYPE_LABELS[type]
    ),
    created_at: createdAt,
    updated_at: updatedAt,
    tags: normalizeTags(entry.tags),
    metrics: entry.metrics && typeof entry.metrics === 'object' ? entry.metrics : {},
    action: entry.action && typeof entry.action === 'object' ? entry.action : {},
    lifecycle: normalizeLifecycle(entry.lifecycle, status),
    status_updated_at: entry.status_updated_at ? normalizeIso(entry.status_updated_at, updatedAt) : undefined,
    raw: entry.raw && typeof entry.raw === 'object' ? entry.raw : {},
  };
};

export const mergeResearchEntries = (entries = []) => {
  const entryMap = new Map();
  entries.forEach((entry, index) => {
    const normalized = normalizeResearchEntry(entry, index);
    const existing = entryMap.get(normalized.id);
    if (!existing || Date.parse(normalized.updated_at) >= Date.parse(existing.updated_at)) {
      entryMap.set(normalized.id, normalized);
    }
  });

  return Array.from(entryMap.values()).sort((left, right) => {
    const statusDiff = (STATUS_RANK[left.status] ?? 9) - (STATUS_RANK[right.status] ?? 9);
    if (statusDiff) return statusDiff;
    const priorityDiff = (PRIORITY_RANK[left.priority] ?? 9) - (PRIORITY_RANK[right.priority] ?? 9);
    if (priorityDiff) return priorityDiff;
    return Date.parse(right.updated_at || 0) - Date.parse(left.updated_at || 0);
  });
};

export const filterResearchEntries = (entries = [], filters = {}) => {
  const status = filters.status || 'all';
  const priority = filters.priority || 'all';
  const type = filters.type || 'all';
  const keyword = normalizeSearchText(filters.keyword);

  return mergeResearchEntries(entries).filter((entry) => {
    if (status === 'active' && !ACTIVE_RESEARCH_STATUSES.has(entry.status)) {
      return false;
    }
    if (status !== 'all' && status !== 'active' && entry.status !== status) {
      return false;
    }
    if (priority !== 'all' && entry.priority !== priority) {
      return false;
    }
    if (type !== 'all' && entry.type !== type) {
      return false;
    }
    if (keyword && !buildEntrySearchText(entry).includes(keyword)) {
      return false;
    }
    return true;
  });
};

const flattenInboxText = (value) => {
  if (value === null || value === undefined) {
    return '';
  }
  if (Array.isArray(value)) {
    return value.map(flattenInboxText).filter(Boolean).join(' ');
  }
  if (typeof value === 'object') {
    return Object.values(value).map(flattenInboxText).filter(Boolean).join(' ');
  }
  return stringifyText(value);
};

const buildInboxSignalText = (entry) => [
  entry.type,
  entry.title,
  entry.summary,
  entry.source,
  entry.source_label,
  entry.action?.label,
  entry.action?.view,
  entry.action?.kind,
  entry.tone,
  entry.signal,
  entry.raw?.tone,
  entry.raw?.signal,
  entry.raw?.sentiment,
  ...safeArray(entry.tags),
].map(flattenInboxText).filter(Boolean).join(' ');

const resolveInboxReferenceTime = (options = {}) => {
  const timestamp = Date.parse(options.now || options.generated_at || options.referenceTime || '');
  if (!Number.isNaN(timestamp)) {
    return timestamp;
  }
  return Date.now();
};

const isInboxEntryRecent = (entry, options = {}) => {
  const timestamp = Date.parse(entry.updated_at || entry.created_at || '');
  if (Number.isNaN(timestamp)) {
    return true;
  }
  const referenceTime = resolveInboxReferenceTime(options);
  const recentWindowMs = Number(options.recentWindowHours || DEFAULT_INBOX_RECENT_WINDOW_HOURS) * 60 * 60 * 1000;
  return timestamp >= referenceTime - recentWindowMs;
};

const deriveInboxBucket = (entry, options = {}) => {
  if (entry.status === 'archived' || entry.status === 'dismissed') {
    return 'archived';
  }
  if (entry.status === 'snoozed') {
    return 'snoozed';
  }
  if (entry.status === 'done') {
    return 'read_later';
  }

  const signalText = buildInboxSignalText(entry);
  const hasActionSignal = INBOX_ACTION_TYPES.has(entry.type) || INBOX_HIGH_SIGNAL_RE.test(signalText);
  const hasWatchSignal = entry.status === 'watching' || INBOX_WATCH_SIGNAL_RE.test(signalText);
  const isRecent = isInboxEntryRecent(entry, options);

  if (!isRecent && !hasActionSignal && entry.priority !== 'high') {
    return 'read_later';
  }
  if (INBOX_ACTIVE_STATUSES.has(entry.status) && (entry.status === 'open' || hasActionSignal || entry.priority === 'high')) {
    return 'actionable';
  }
  if (hasWatchSignal) {
    return 'watch';
  }
  return isRecent ? 'watch' : 'read_later';
};

const deriveInboxPriority = (entry, bucket, options = {}) => {
  if (bucket === 'archived' || bucket === 'read_later') {
    return 'low';
  }
  if (bucket === 'snoozed') {
    return TODAY_RESEARCH_PRIORITY_LABELS[entry.priority] ? entry.priority : 'medium';
  }
  const signalText = buildInboxSignalText(entry);
  if (bucket === 'actionable' && (
    entry.priority === 'high'
    || INBOX_ACTION_TYPES.has(entry.type)
    || INBOX_HIGH_SIGNAL_RE.test(signalText)
  )) {
    return 'high';
  }
  if (!isInboxEntryRecent(entry, options)) {
    return entry.priority === 'high' ? 'medium' : 'low';
  }
  return TODAY_RESEARCH_PRIORITY_LABELS[entry.priority] ? entry.priority : 'medium';
};

const buildInboxReason = (entry, bucket, options = {}) => {
  if (bucket === 'archived') {
    return '已从今日处理流移出';
  }
  if (bucket === 'snoozed') {
    return '已稍后，暂不作为当前处理项';
  }
  if (entry.status === 'done') {
    return '已完成，适合稍后回看';
  }
  if (!isInboxEntryRecent(entry, options) && bucket === 'read_later') {
    return '更新较久，先放入稍后阅读';
  }
  if (bucket === 'actionable') {
    return entry.action?.label || '需要打开上下文处理';
  }
  return '继续观察后续变化';
};

export const deriveResearchInboxEntries = (entries = [], options = {}) => mergeResearchEntries(entries).map((entry) => {
  const inboxBucket = deriveInboxBucket(entry, options);
  const inboxPriority = deriveInboxPriority(entry, inboxBucket, options);
  return {
    ...entry,
    inbox_bucket: inboxBucket,
    inbox_status: inboxBucket,
    inbox_priority: inboxPriority,
    inbox_reason: buildInboxReason(entry, inboxBucket, options),
    inbox_tags: safeArray(entry.tags).slice(0, 4),
  };
}).sort((left, right) => {
  const bucketDiff = (INBOX_BUCKET_RANK[left.inbox_bucket] ?? 9) - (INBOX_BUCKET_RANK[right.inbox_bucket] ?? 9);
  if (bucketDiff) return bucketDiff;
  const statusDiff = (STATUS_RANK[left.status] ?? 9) - (STATUS_RANK[right.status] ?? 9);
  if (statusDiff) return statusDiff;
  const priorityDiff = (PRIORITY_RANK[left.inbox_priority] ?? 9) - (PRIORITY_RANK[right.inbox_priority] ?? 9);
  if (priorityDiff) return priorityDiff;
  return Date.parse(right.updated_at || 0) - Date.parse(left.updated_at || 0);
});

export const groupResearchInboxEntries = (entries = [], options = {}) => {
  const groups = RESEARCH_INBOX_BUCKET_ORDER.reduce((result, bucket) => ({
    ...result,
    [bucket]: [],
  }), {});
  deriveResearchInboxEntries(entries, options).forEach((entry) => {
    const bucket = RESEARCH_INBOX_BUCKET_LABELS[entry.inbox_bucket] ? entry.inbox_bucket : 'read_later';
    groups[bucket].push(entry);
  });
  return groups;
};

export const filterResearchInboxEntries = (entries = [], filters = {}, options = {}) => {
  const bucket = filters.bucket || 'all';
  const priority = filters.priority || 'all';
  return deriveResearchInboxEntries(entries, options).filter((entry) => {
    if (bucket !== 'all' && entry.inbox_bucket !== bucket) {
      return false;
    }
    if (priority !== 'all' && entry.inbox_priority !== priority) {
      return false;
    }
    return true;
  });
};

const deriveResearchActionKind = (entry) => {
  if (entry.type === 'realtime_alert' || entry.type === 'industry_alert') {
    return 'review_alert';
  }
  if (entry.type === 'trade_plan') {
    return 'confirm_trade_plan';
  }
  if (entry.type === 'backtest') {
    return 'review_backtest';
  }
  if (entry.type === 'realtime_review') {
    return 'continue_realtime_review';
  }
  if (entry.type === 'industry_watch') {
    return 'follow_watchlist';
  }
  return 'open_context';
};

const deriveResearchActionPriority = (entry, kind) => {
  if (
    entry.inbox_priority === 'high'
    || entry.priority === 'high'
    || kind === 'review_alert'
    || kind === 'confirm_trade_plan'
  ) {
    return 'high';
  }
  return TODAY_RESEARCH_PRIORITY_LABELS[entry.inbox_priority]
    ? entry.inbox_priority
    : (TODAY_RESEARCH_PRIORITY_LABELS[entry.priority] ? entry.priority : 'medium');
};

const buildResearchActionDescription = (entry, kind) => {
  const target = compactLabelText(entry.symbol || entry.industry || entry.title, 120) || '当前线索';
  if (kind === 'review_alert') {
    return `确认 ${target} 的提醒是否需要升级为回测、复盘或交易计划。`;
  }
  if (kind === 'confirm_trade_plan') {
    return `复核 ${target} 的入场条件、风险边界和后续执行状态。`;
  }
  if (kind === 'review_backtest') {
    return `检查 ${target} 的收益、回撤和样本条件是否支持继续跟踪。`;
  }
  if (kind === 'continue_realtime_review') {
    return `回到 ${target} 的实时复盘，确认最新行情是否改变判断。`;
  }
  if (kind === 'follow_watchlist') {
    return `跟进 ${target} 的热度、排行榜和龙头股变化。`;
  }
  return `打开 ${target} 的研究上下文，决定下一步处理方式。`;
};

const sanitizeResearchActionPayload = (action) => {
  if (!action || typeof action !== 'object') {
    return {};
  }
  return Object.entries(action).reduce((result, [key, value]) => {
    if (value === null || value === undefined || typeof value === 'boolean') {
      return result;
    }
    result[key] = value;
    return result;
  }, {});
};

export const summarizeResearchActionQueue = (actions = []) => safeArray(actions).reduce((result, action) => {
  const bucket = RESEARCH_ACTION_BUCKET_RANK[action.inbox_bucket] !== undefined
    ? action.inbox_bucket
    : 'read_later';
  result.total += 1;
  result[bucket] += 1;
  if (action.priority === 'high') {
    result.high += 1;
  }
  return result;
}, { ...EMPTY_RESEARCH_ACTION_COUNTS });

export const deriveResearchActionQueue = (entries = [], options = {}) => {
  const limit = Number.isFinite(Number(options.limit))
    ? Math.max(0, Number(options.limit))
    : DEFAULT_RESEARCH_ACTION_LIMIT;

  return deriveResearchInboxEntries(entries, options)
    .filter((entry) => (
      entry.inbox_bucket === 'actionable'
        || entry.inbox_bucket === 'watch'
        || entry.inbox_bucket === 'snoozed'
    ))
    .map((entry) => {
      const kind = deriveResearchActionKind(entry);
      const priority = deriveResearchActionPriority(entry, kind);
      const label = RESEARCH_ACTION_KIND_LABELS[kind] || RESEARCH_ACTION_KIND_LABELS.open_context;
      const sourceLabel = compactLabelText(entry.source_label || entry.source, 80);
      return {
        key: `research_action:${entry.id}`,
        kind,
        label,
        description: buildResearchActionDescription(entry, kind),
        entry_id: entry.id,
        entry_title: entry.title,
        entry_type: entry.type,
        inbox_bucket: entry.inbox_bucket,
        priority,
        symbol: entry.symbol,
        industry: entry.industry,
        source: entry.source,
        source_label: sourceLabel || entry.source,
        updated_at: entry.updated_at,
        tags: safeArray(entry.inbox_tags || entry.tags).slice(0, 4),
        action: sanitizeResearchActionPayload(entry.action),
      };
    })
    .sort((left, right) => {
      const bucketDiff = (RESEARCH_ACTION_BUCKET_RANK[left.inbox_bucket] ?? 9) - (RESEARCH_ACTION_BUCKET_RANK[right.inbox_bucket] ?? 9);
      if (bucketDiff) return bucketDiff;
      const priorityDiff = (PRIORITY_RANK[left.priority] ?? 9) - (PRIORITY_RANK[right.priority] ?? 9);
      if (priorityDiff) return priorityDiff;
      const kindDiff = (RESEARCH_ACTION_KIND_RANK[left.kind] ?? 9) - (RESEARCH_ACTION_KIND_RANK[right.kind] ?? 9);
      if (kindDiff) return kindDiff;
      const updatedDiff = Date.parse(right.updated_at || 0) - Date.parse(left.updated_at || 0);
      if (updatedDiff) return updatedDiff;
      return String(left.entry_id).localeCompare(String(right.entry_id));
    })
    .slice(0, limit);
};

const buildBacktestEntries = (snapshots = []) => safeArray(snapshots).map((snapshot, index) => {
  const symbol = normalizeSymbol(snapshot.symbol);
  const totalReturn = snapshot.metrics?.total_return;
  const maxDrawdown = snapshot.metrics?.max_drawdown;
  return normalizeResearchEntry({
    id: `backtest:${snapshot.id || index}`,
    type: 'backtest',
    status: 'open',
    priority: compactNumber(snapshot.metrics?.sharpe_ratio, 0) >= 1 ? 'high' : 'medium',
    title: `${symbol || '未命名标的'} · ${snapshot.strategy || '策略'} 回测`,
    summary: `收益 ${toPercentText(totalReturn)}，最大回撤 ${toPercentText(maxDrawdown)}，交易 ${snapshot.metrics?.num_trades ?? '--'} 次。`,
    note: snapshot.note,
    symbol,
    source: 'backtest_research_snapshots',
    source_label: '回测研究快照',
    created_at: snapshot.created_at,
    updated_at: snapshot.created_at,
    tags: ['回测', snapshot.strategy].filter(Boolean),
    metrics: snapshot.metrics || {},
    action: { view: 'backtest', tab: 'history', label: '打开回测历史' },
    raw: snapshot,
  }, index);
});

const buildRealtimeReviewEntries = (snapshots = []) => safeArray(snapshots).map((snapshot, index) => {
  const symbol = normalizeSymbol(snapshot.spotlightSymbol || snapshot.symbol);
  const outcome = compactText(snapshot.outcome, 40);
  const status = outcome === 'validated' || outcome === 'invalidated' ? 'done' : 'watching';
  return normalizeResearchEntry({
    id: `realtime_review:${snapshot.id || index}`,
    type: 'realtime_review',
    status,
    priority: outcome === 'pending' || !outcome ? 'medium' : 'low',
    title: `${symbol || snapshot.spotlightName || '实时焦点'} · 复盘快照`,
    summary: snapshot.activeTabLabel
      ? `${snapshot.activeTabLabel} 分组快照，焦点 ${snapshot.spotlightName || symbol || '未记录'}。`
      : `焦点 ${snapshot.spotlightName || symbol || '未记录'} 的实时复盘记录。`,
    note: snapshot.note,
    symbol,
    source: 'realtime_review_snapshots',
    source_label: '实时复盘',
    created_at: snapshot.createdAt || snapshot.created_at,
    updated_at: snapshot.updatedAt || snapshot.createdAt || snapshot.created_at,
    tags: ['复盘', snapshot.activeTabLabel, outcome].filter(Boolean),
    metrics: {
      anomaly_count: safeArray(snapshot.anomalyFeed).length,
      quote_count: safeArray(snapshot.quotes).length,
    },
    action: { view: 'realtime', symbol, label: '打开实时详情' },
    raw: snapshot,
  }, index);
});

const buildRealtimeAlertEntries = (history = []) => safeArray(history).map((entry, index) => {
  const symbol = normalizeSymbol(entry.symbol);
  return normalizeResearchEntry({
    id: `realtime_alert:${entry.id || index}`,
    type: 'realtime_alert',
    status: 'open',
    priority: Math.abs(Number(entry.changePercentSnapshot || 0)) >= 3 ? 'high' : 'medium',
    title: `${symbol || '实时标的'} · 提醒命中`,
    summary: entry.message || entry.conditionLabel || '实时提醒已触发。',
    note: entry.sourceTitle || '',
    symbol,
    source: 'realtime_alert_hit_history',
    source_label: '实时提醒',
    created_at: entry.triggerTime || entry.created_at,
    updated_at: entry.triggerTime || entry.created_at,
    tags: ['提醒', entry.conditionLabel].filter(Boolean),
    metrics: {
      trigger_price: compactNumber(entry.triggerPrice ?? entry.priceSnapshot),
      change_percent: compactNumber(entry.changePercentSnapshot),
    },
    action: { view: 'realtime', symbol, label: '打开实时看盘' },
    raw: entry,
  }, index);
});

const buildRealtimeEventEntries = (events = []) => safeArray(events).map((event, index) => {
  const symbol = normalizeSymbol(event.symbol);
  const isTradePlan = event.kind === 'trade_plan';
  return normalizeResearchEntry({
    id: `${isTradePlan ? 'trade_plan' : 'realtime_event'}:${event.id || index}`,
    type: isTradePlan ? 'trade_plan' : 'realtime_event',
    status: isTradePlan ? 'open' : 'watching',
    priority: isTradePlan ? 'high' : 'medium',
    title: event.title || `${symbol || '实时标的'} · ${isTradePlan ? '交易计划' : '实时事件'}`,
    summary: event.description || event.summary || '',
    note: event.note || '',
    symbol,
    source: 'realtime_timeline_events',
    source_label: isTradePlan ? '交易计划' : '实时事件',
    created_at: event.createdAt || event.created_at,
    updated_at: event.updatedAt || event.createdAt || event.created_at,
    tags: [isTradePlan ? '交易计划' : '实时事件', event.kind].filter(Boolean),
    metrics: event.metrics || {},
    action: { view: 'realtime', symbol, label: '打开实时详情' },
    raw: event,
  }, index);
});

const buildIndustryWatchEntries = (watchlist = [], generatedAt) => safeArray(watchlist).map((industry, index) => {
  const industryName = compactText(industry, 120);
  return normalizeResearchEntry({
    id: `industry_watch:${industryName}`,
    type: 'industry_watch',
    status: 'watching',
    priority: index < 3 ? 'medium' : 'low',
    title: `${industryName} · 行业观察`,
    summary: '已加入行业观察列表，适合继续看热力图、排行榜和龙头股。',
    industry: industryName,
    source: 'industry_watchlist',
    source_label: '行业观察',
    created_at: generatedAt,
    updated_at: generatedAt,
    tags: ['行业', '观察列表'],
    action: { view: 'industry', label: '打开行业热度' },
    raw: { industry: industryName },
  }, index);
});

const buildIndustryAlertEntries = (history = {}, generatedAt) => Object.entries(history || {}).map(([key, item], index) => {
  const industry = compactText(item?.industry_name || item?.industryName || item?.industry || key, 120);
  const priority = Number(item?.priority || 0) >= 110 || Number(item?.hitCount || 0) >= 2 ? 'high' : 'medium';
  return normalizeResearchEntry({
    id: `industry_alert:${key}`,
    type: 'industry_alert',
    status: 'open',
    priority,
    title: `${industry} · 行业提醒`,
    summary: item?.message || item?.title || `行业提醒出现 ${item?.hitCount || 1} 次。`,
    industry,
    source: 'industry_alert_history',
    source_label: '行业提醒',
    created_at: new Date(Number(item?.firstSeenAt || item?.lastSeenAt || Date.parse(generatedAt))).toISOString(),
    updated_at: new Date(Number(item?.lastSeenAt || item?.firstSeenAt || Date.parse(generatedAt))).toISOString(),
    tags: ['行业提醒', item?.kind].filter(Boolean),
    metrics: {
      hit_count: compactNumber(item?.hitCount, 1),
      priority: compactNumber(item?.priority),
    },
    action: { view: 'industry', label: '打开行业提醒' },
    raw: item,
  }, index);
});

const buildPriceAlertRuleEntries = (alerts = [], generatedAt) => safeArray(alerts).filter((alert) => alert?.active !== false).map((alert, index) => {
  const symbol = normalizeSymbol(alert.symbol);
  return normalizeResearchEntry({
    id: `price_alert_rule:${alert.id || symbol || index}`,
    type: 'realtime_alert',
    status: alert.triggered ? 'done' : 'watching',
    priority: alert.triggered ? 'high' : 'medium',
    title: `${symbol || '实时标的'} · 提醒规则`,
    summary: alert.conditionLabel || alert.condition || '已设置实时提醒规则。',
    symbol,
    source: 'price_alert_rules',
    source_label: '提醒规则',
    created_at: alert.createdAt || generatedAt,
    updated_at: alert.updatedAt || generatedAt,
    tags: ['提醒规则', alert.condition].filter(Boolean),
    metrics: { threshold: compactNumber(alert.threshold) },
    action: { view: 'realtime', symbol, label: '打开提醒抽屉' },
    raw: alert,
  }, index);
});

export const collectLocalResearchState = () => {
  const generatedAt = new Date().toISOString();
  const backtestSnapshots = loadBacktestResearchSnapshots();
  const realtimeReviewSnapshots = safeReadJsonStorage(REALTIME_REVIEW_SNAPSHOT_STORAGE_KEY, []);
  const realtimeTimelineEvents = safeReadJsonStorage(REALTIME_TIMELINE_STORAGE_KEY, []);
  const realtimeAlertHitHistory = loadAlertHitHistory();
  const industryWatchlist = safeReadJsonStorage(INDUSTRY_WATCHLIST_STORAGE_KEY, []);
  const industryAlertHistory = pruneIndustryAlertHistory(safeReadJsonStorage(INDUSTRY_ALERT_HISTORY_STORAGE_KEY, {}));
  const industrySavedViews = safeReadJsonStorage(INDUSTRY_SAVED_VIEWS_STORAGE_KEY, []);
  const priceAlerts = safeReadJsonStorage(PRICE_ALERTS_STORAGE_KEY, []);

  return {
    generated_at: generatedAt,
    backtest_snapshots: backtestSnapshots,
    realtime_review_snapshots: safeArray(realtimeReviewSnapshots),
    realtime_timeline_events: safeArray(realtimeTimelineEvents),
    realtime_alert_hit_history: safeArray(realtimeAlertHitHistory),
    industry_watchlist: safeArray(industryWatchlist),
    industry_alert_history: industryAlertHistory,
    industry_saved_views: safeArray(industrySavedViews),
    price_alert_rules: safeArray(priceAlerts),
  };
};

export const buildTodayResearchSnapshot = (localState = collectLocalResearchState(), extraEntries = []) => {
  const generatedAt = localState.generated_at || new Date().toISOString();
  const entries = mergeResearchEntries([
    ...buildBacktestEntries(localState.backtest_snapshots),
    ...buildRealtimeReviewEntries(localState.realtime_review_snapshots),
    ...buildRealtimeAlertEntries(localState.realtime_alert_hit_history),
    ...buildRealtimeEventEntries(localState.realtime_timeline_events),
    ...buildIndustryWatchEntries(localState.industry_watchlist, generatedAt),
    ...buildIndustryAlertEntries(localState.industry_alert_history, generatedAt),
    ...buildPriceAlertRuleEntries(localState.price_alert_rules, generatedAt),
    ...safeArray(extraEntries),
  ]);

  return {
    entries,
    source_state: {
      keys: {
        backtest: BACKTEST_RESEARCH_SNAPSHOTS_KEY,
        realtime_review: REALTIME_REVIEW_SNAPSHOT_STORAGE_KEY,
        realtime_timeline: REALTIME_TIMELINE_STORAGE_KEY,
        realtime_alerts: ALERT_HIT_HISTORY_STORAGE_KEY,
        industry_watchlist: INDUSTRY_WATCHLIST_STORAGE_KEY,
        industry_alerts: INDUSTRY_ALERT_HISTORY_STORAGE_KEY,
      },
      counts: {
        backtest_snapshots: safeArray(localState.backtest_snapshots).length,
        realtime_review_snapshots: safeArray(localState.realtime_review_snapshots).length,
        realtime_timeline_events: safeArray(localState.realtime_timeline_events).length,
        realtime_alert_hit_history: safeArray(localState.realtime_alert_hit_history).length,
        industry_watchlist: safeArray(localState.industry_watchlist).length,
        industry_alert_history: Object.keys(localState.industry_alert_history || {}).length,
        industry_saved_views: safeArray(localState.industry_saved_views).length,
        price_alert_rules: safeArray(localState.price_alert_rules).length,
      },
    },
    generated_at: generatedAt,
  };
};

export const summarizeResearchEntries = (entries = [], options = {}) => {
  const normalizedEntries = mergeResearchEntries(entries);
  const counts = normalizedEntries.reduce((result, entry) => {
    result.byType[entry.type] = (result.byType[entry.type] || 0) + 1;
    result.byStatus[entry.status] = (result.byStatus[entry.status] || 0) + 1;
    if (entry.symbol) result.symbols.add(entry.symbol);
    if (entry.industry) result.industries.add(entry.industry);
    return result;
  }, {
    byType: {},
    byStatus: {},
    symbols: new Set(),
    industries: new Set(),
  });

  const actionQueue = normalizedEntries
    .filter((entry) => ['open', 'watching'].includes(entry.status))
    .slice(0, 12);
  const researchActions = deriveResearchActionQueue(normalizedEntries, options);

  return {
    total_entries: normalizedEntries.length,
    open_entries: (counts.byStatus.open || 0) + (counts.byStatus.watching || 0),
    type_counts: counts.byType,
    status_counts: counts.byStatus,
    symbol_count: counts.symbols.size,
    industry_count: counts.industries.size,
    action_queue: actionQueue,
    research_actions: researchActions,
    research_action_counts: summarizeResearchActionQueue(researchActions),
  };
};
