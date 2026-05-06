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
  done: '已完成',
  archived: '已归档',
};

export const TODAY_RESEARCH_PRIORITY_LABELS = {
  high: '高',
  medium: '中',
  low: '低',
};

const STATUS_RANK = {
  open: 0,
  watching: 1,
  done: 2,
  archived: 3,
};

const PRIORITY_RANK = {
  high: 0,
  medium: 1,
  low: 2,
};

const safeArray = (value) => (Array.isArray(value) ? value : []);
const ACTIVE_RESEARCH_STATUSES = new Set(['open', 'watching']);

const normalizeSearchText = (value) => String(value || '').trim().toLowerCase();

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

const normalizeSymbol = (value) => String(value || '').trim().toUpperCase();

const compactText = (value, max = 240) => String(value || '').trim().slice(0, max);

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
  const industry = compactText(entry.industry || entry.industry_name, 120);
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
    source_label: compactText(entry.source_label || entry.sourceLabel, 80) || TODAY_RESEARCH_TYPE_LABELS[type],
    created_at: createdAt,
    updated_at: updatedAt,
    tags: safeArray(entry.tags).filter((item) => typeof item === 'string' && item.trim()).slice(0, 8),
    metrics: entry.metrics && typeof entry.metrics === 'object' ? entry.metrics : {},
    action: entry.action && typeof entry.action === 'object' ? entry.action : {},
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

export const summarizeResearchEntries = (entries = []) => {
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

  return {
    total_entries: normalizedEntries.length,
    open_entries: (counts.byStatus.open || 0) + (counts.byStatus.watching || 0),
    type_counts: counts.byType,
    status_counts: counts.byStatus,
    symbol_count: counts.symbols.size,
    industry_count: counts.industries.size,
    action_queue: actionQueue,
  };
};
