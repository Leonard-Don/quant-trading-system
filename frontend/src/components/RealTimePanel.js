import React, { useState, useEffect, useCallback, useMemo, useRef, lazy, Suspense } from 'react';
import {
  Card,
  Tag,
  Input,
  Button,
  Space,
  Typography,
  Badge,
  Switch,
  AutoComplete,
  Drawer,
  Empty,
} from 'antd';
import {
  SearchOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  SyncOutlined,
  StockOutlined,
  PropertySafetyOutlined,
  BankOutlined,
  ThunderboltOutlined,
  BarChartOutlined,
  FundOutlined,
  BellOutlined,
  DeleteOutlined,
  FolderOutlined,
} from '@ant-design/icons';
import RealtimeQuoteBoard from './realtime/RealtimeQuoteBoard';
import RealtimeAnomalyRadar from './realtime/RealtimeAnomalyRadar';
import RealtimeAlertHistoryCard from './realtime/RealtimeAlertHistoryCard';
import RealtimeReviewSummaryCard from './realtime/RealtimeReviewSummaryCard';
import RealtimeDiagnosticsCard from './realtime/RealtimeDiagnosticsCard';
import RealtimeSnapshotDrawer from './realtime/RealtimeSnapshotDrawer';
import { STOCK_DATABASE } from '../constants/stocks';
import { useRealtimeDiagnostics } from '../hooks/useRealtimeDiagnostics';
import { useRealtimeDerivedState, formatQuoteTime } from '../hooks/useRealtimeDerivedState';
import { useRealtimeFeed } from '../hooks/useRealtimeFeed';
import { useRealtimeMetadata } from '../hooks/useRealtimeMetadata';
import { useRealtimePreferences } from '../hooks/useRealtimePreferences';
import {
  buildAlertDraftFromAnomaly,
  buildRealtimeAnomalyFeed,
  buildTradePlanDraftFromAnomaly,
} from '../utils/realtimeSignals';
import {
  useRealtimeJournal,
  normalizeReviewSnapshot,
  normalizeTimelineEvent,
  MAX_REVIEW_SNAPSHOTS,
  MAX_TIMELINE_EVENTS,
} from '../hooks/useRealtimeJournal';
import {
  QUOTE_FRESH_MS,
  QUOTE_DELAYED_MS,
  buildMiniTrendSeries,
  buildSparklinePoints,
  formatPercent,
  formatPrice,
  formatRelativeAge,
  formatVolume,
  getCategoryLabel as getCategoryLabelForType,
  hasNumericValue,
  inferSymbolCategory,
} from '../utils/realtimeFormatters';
import {
  buildRealtimeShareDocument,
  formatReviewSnapshotMarkdown,
  formatReviewSnapshotShareHtml,
  formatReviewSummaryMarkdown,
  formatReviewSummaryShareHtml,
} from '../utils/realtimeShareTemplates';
import { useSafeMessageApi } from '../utils/messageApi';

const { Text } = Typography;
const EMPTY_NUMERIC_TEXT = '--';
const REALTIME_DIAGNOSTICS_STORAGE_KEY = 'realtime-panel:diagnostics-enabled';
const REVIEW_SNAPSHOT_VERSION = 2;
const REALTIME_EXPORT_VERSION = 1;
const QUOTE_SORT_OPTIONS = [
  { key: 'change_desc', label: '涨跌幅' },
  { key: 'range_desc', label: '振幅' },
  { key: 'volume_desc', label: '成交量' },
  { key: 'symbol_asc', label: '代码' },
];
const REVIEW_SCOPE_OPTIONS = [
  { key: 'all', label: '全部' },
  { key: 'recent7d', label: '最近7天' },
  { key: 'recent20', label: '最近20条' },
  { key: 'activeTab', label: '当前分组' },
];
const SNAPSHOT_OUTCOME_OPTIONS = {
  watching: { label: '继续观察', color: 'default' },
  validated: { label: '验证有效', color: 'success' },
  invalidated: { label: '观察失效', color: 'error' },
};
const DEFAULT_SUBSCRIBED_SYMBOLS = [
  '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
  'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'BABA',
  '600519.SS', '601398.SS', '300750.SZ', '000858.SZ',
  'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'DOGE-USD',
  '^TNX', '^TYX', 'TLT',
  'GC=F', 'CL=F', 'SI=F',
  'SPY', 'QQQ', 'UVXY'
];
const CATEGORY_THEMES = {
  index: { label: '指数', accent: '#0ea5e9', soft: 'rgba(14, 165, 233, 0.12)' },
  us: { label: '美股', accent: '#22c55e', soft: 'rgba(34, 197, 94, 0.12)' },
  cn: { label: 'A股', accent: '#f97316', soft: 'rgba(249, 115, 22, 0.12)' },
  crypto: { label: '加密', accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' },
  bond: { label: '债券', accent: '#6366f1', soft: 'rgba(99, 102, 241, 0.12)' },
  future: { label: '期货', accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)' },
  option: { label: '期权', accent: '#a855f7', soft: 'rgba(168, 85, 247, 0.12)' },
  other: { label: '其他', accent: '#64748b', soft: 'rgba(100, 116, 139, 0.12)' },
};

const formatCompactCurrency = (value) => {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return '$0';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: Math.abs(numeric) >= 10000 ? 'compact' : 'standard',
    maximumFractionDigits: Math.abs(numeric) >= 10000 ? 1 : 0,
  }).format(numeric);
};

const normalizeGroupWeights = (group) => {
  const symbols = Array.isArray(group?.symbols) ? group.symbols.filter(Boolean) : [];
  if (!symbols.length) {
    return {};
  }

  const explicitWeights = group?.weights && typeof group.weights === 'object' && !Array.isArray(group.weights)
    ? Object.entries(group.weights).reduce((result, [symbol, rawWeight]) => {
        const numericWeight = Number(rawWeight);
        if (symbols.includes(symbol) && Number.isFinite(numericWeight)) {
          result[symbol] = numericWeight;
        }
        return result;
      }, {})
    : {};

  if (Object.keys(explicitWeights).length) {
    return explicitWeights;
  }

  const equalWeight = 1 / symbols.length;
  return symbols.reduce((result, symbol) => {
    result[symbol] = equalWeight;
    return result;
  }, {});
};
const CATEGORY_OPTIONS = [
  { key: 'index', label: '指数' },
  { key: 'us', label: '美股' },
  { key: 'cn', label: 'A股' },
  { key: 'crypto', label: '加密' },
  { key: 'bond', label: '债券' },
  { key: 'future', label: '期货' },
  { key: 'option', label: '期权' },
  { key: 'other', label: '其他' },
];
const TradePanel = lazy(() => import('./TradePanel'));
const RealtimeStockDetailModal = lazy(() => import('./RealtimeStockDetailModal'));
const PriceAlerts = lazy(() => import('./PriceAlerts'));

const loadDiagnosticsEnabled = () => {
  if (typeof window === 'undefined') {
    return process.env.NODE_ENV !== 'production';
  }

  const query = new URLSearchParams(window.location.search);
  const queryValue = query.get('realtimeDiagnostics');
  if (queryValue === '1') {
    window.localStorage.setItem(REALTIME_DIAGNOSTICS_STORAGE_KEY, '1');
    return true;
  }
  if (queryValue === '0') {
    window.localStorage.setItem(REALTIME_DIAGNOSTICS_STORAGE_KEY, '0');
    return false;
  }

  const persisted = window.localStorage.getItem(REALTIME_DIAGNOSTICS_STORAGE_KEY);
  if (persisted === '1') {
    return true;
  }
  if (persisted === '0') {
    return false;
  }

  return process.env.NODE_ENV !== 'production';
};

const getTimelineTone = (kind = '') => {
  if (['price_up', 'touch_high', 'trade_plan', 'review_validated'].includes(kind)) {
    return 'positive';
  }

  if (['price_down', 'touch_low', 'review_invalidated'].includes(kind)) {
    return 'negative';
  }

  if (['volume_spike', 'range_expansion', 'alert_plan', 'review_snapshot'].includes(kind)) {
    return 'warning';
  }

  return 'neutral';
};

const buildRealtimeDetailTimeline = ({ symbol, anomalyFeed = [], reviewSnapshots = [], actionEvents = [], alertHistory = [] }) => {
  if (!symbol) {
    return [];
  }

  const liveSignalEvents = anomalyFeed
    .filter((item) => item?.symbol === symbol)
    .map((item) => ({
      id: `live_${symbol}_${item.kind}_${item.timestamp || item.title}`,
      symbol,
      kind: item.kind || 'live_signal',
      source: 'live',
      sourceLabel: '实时异动',
      title: item.title,
      description: item.description,
      createdAt: item.timestamp || new Date().toISOString(),
      tone: getTimelineTone(item.kind),
      priceSnapshot: item.priceSnapshot,
      changePercentSnapshot: item.changePercentSnapshot,
      rangePercentSnapshot: item.rangePercentSnapshot,
      volumeSnapshot: item.volumeSnapshot,
    }));

  const reviewEvents = reviewSnapshots
    .filter((snapshot) => snapshot?.spotlightSymbol === symbol || (snapshot?.anomalies || []).some((item) => item?.symbol === symbol))
    .map((snapshot) => {
      const outcomeMeta = getSnapshotOutcomeMeta(snapshot.outcome);
      const relatedAnomaly = (snapshot.anomalies || []).find((item) => item?.symbol === symbol);
      return {
        id: `review_${snapshot.id}_${symbol}`,
        symbol,
        kind: snapshot.outcome ? `review_${snapshot.outcome}` : 'review_snapshot',
        source: 'review',
        sourceLabel: '复盘快照',
        title: outcomeMeta?.label ? `${outcomeMeta.label} · ${snapshot.activeTabLabel || snapshot.activeTab || '复盘记录'}` : '保存复盘快照',
        description: snapshot.note
          || relatedAnomaly?.description
          || `记录了 ${snapshot.activeTabLabel || snapshot.activeTab || '--'} 视角下的 ${snapshot.anomalyCount ?? 0} 条异动。`,
        createdAt: snapshot.updatedAt || snapshot.createdAt,
        tone: getTimelineTone(snapshot.outcome ? `review_${snapshot.outcome}` : 'review_snapshot'),
      };
    });

  const manualEvents = actionEvents
    .filter((event) => event?.symbol === symbol)
    .map((event) => ({
      ...event,
      tone: event.tone || getTimelineTone(event.kind),
    }));

  const alertEvents = alertHistory
    .filter((entry) => entry?.symbol === symbol)
    .map((entry) => ({
      id: `alert_hit_${entry.id}`,
      symbol,
      kind: 'alert_triggered',
      source: 'alert',
      sourceLabel: '提醒命中',
      title: `提醒命中 · ${entry.conditionLabel || '提醒规则'}`,
      description: entry.message || `${symbol} 的提醒规则已触发。`,
      createdAt: entry.triggerTime,
      tone: ['price_above', 'change_pct_above', 'touch_high'].includes(entry.condition) ? 'positive' : 'warning',
      priceSnapshot: entry.priceSnapshot ?? entry.triggerPrice ?? null,
      threshold: entry.threshold,
      condition: entry.condition,
    }));

  const uniqueEvents = new Map();
  [...liveSignalEvents, ...manualEvents, ...reviewEvents, ...alertEvents].forEach((event) => {
    if (!event?.id) {
      return;
    }
    uniqueEvents.set(event.id, event);
  });

  return Array.from(uniqueEvents.values())
    .sort((left, right) => new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime())
    .slice(0, 10);
};

const getSnapshotOutcomeMeta = (outcome) => SNAPSHOT_OUTCOME_OPTIONS[outcome] || null;
const filterReviewSnapshots = (snapshots = [], scope = 'all', activeTab = '') => {
  if (scope === 'recent20') {
    return snapshots.slice(0, 20);
  }

  if (scope === 'recent7d') {
    const now = Date.now();
    return snapshots.filter((snapshot) => {
      const createdAt = new Date(snapshot.createdAt).getTime();
      return Number.isFinite(createdAt) && now - createdAt <= 7 * 24 * 60 * 60 * 1000;
    });
  }

  if (scope === 'activeTab') {
    return snapshots.filter((snapshot) => snapshot.activeTab === activeTab);
  }

  return snapshots;
};

const RealTimePanel = ({ openAlertsSignal = null }) => {
  const messageApi = useSafeMessageApi();
  const [searchSymbol, setSearchSymbol] = useState('');
  const [globalJumpQuery, setGlobalJumpQuery] = useState('');
  const [isAlertsDrawerVisible, setIsAlertsDrawerVisible] = useState(false);
  const [alertPrefillSymbol, setAlertPrefillSymbol] = useState('');
  const [alertPrefillDraft, setAlertPrefillDraft] = useState(null);
  const [alertComposerSignal, setAlertComposerSignal] = useState(0);

  // Trade Modal State
  const [isTradeModalVisible, setIsTradeModalVisible] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [tradePlanDraft, setTradePlanDraft] = useState(null);
  const [quoteSortMode, setQuoteSortMode] = useState('change_desc');
  const [quoteViewMode, setQuoteViewMode] = useState('grid');

  // Detail Modal State
  const [isDetailModalVisible, setIsDetailModalVisible] = useState(false);
  const [detailSymbol, setDetailSymbol] = useState(null);
  const [autoCompleteOptions, setAutoCompleteOptions] = useState([]);
  const [globalJumpOptions, setGlobalJumpOptions] = useState([]);
  const [isAnomalyExpanded, setIsAnomalyExpanded] = useState(false);
  const [isAlertHistoryExpanded, setIsAlertHistoryExpanded] = useState(false);
  const [isReviewExpanded, setIsReviewExpanded] = useState(false);
  const [isDiagnosticsExpanded, setIsDiagnosticsExpanded] = useState(false);
  const [isSnapshotDrawerVisible, setIsSnapshotDrawerVisible] = useState(false);
  const [diagnosticsEnabled, setDiagnosticsEnabled] = useState(loadDiagnosticsEnabled);
  const [reviewScope, setReviewScope] = useState('all');
  const [selectedQuoteSymbols, setSelectedQuoteSymbols] = useState([]);
  const [draggingSymbol, setDraggingSymbol] = useState(null);
  const [watchGroupName, setWatchGroupName] = useState('');
  const [watchGroupSymbols, setWatchGroupSymbols] = useState('');
  const [watchGroupCapital, setWatchGroupCapital] = useState('');
  const [watchGroupWeights, setWatchGroupWeights] = useState('');
  const notifiedAnomaliesRef = useRef(new Map());
  const snapshotImportInputRef = useRef(null);

  useEffect(() => {
    if (openAlertsSignal) {
      setIsAlertsDrawerVisible(true);
    }
  }, [openAlertsSignal]);

  useEffect(() => {
    window.localStorage.setItem(
      REALTIME_DIAGNOSTICS_STORAGE_KEY,
      diagnosticsEnabled ? '1' : '0'
    );
  }, [diagnosticsEnabled]);

  const {
    activeTab,
    realtimeProfileId,
    setActiveTab,
    setSymbolCategoryOverrides,
    setSubscribedSymbols,
    subscribedSymbols,
    symbolCategoryOverrides,
    watchGroups,
    setWatchGroups,
  } = useRealtimePreferences({
    defaultSymbols: DEFAULT_SUBSCRIBED_SYMBOLS,
    validActiveTabs: CATEGORY_OPTIONS.map((option) => option.key),
  });
  const {
    metadataMap,
    fetchMetadata,
  } = useRealtimeMetadata({
    knownMetadataMap: STOCK_DATABASE,
    subscribedSymbols,
  });

  const {
    alertHitHistory,
    setAlertHitHistory,
    appendTimelineEvent,
    handleAlertTriggered,
    reviewSnapshots,
    setReviewSnapshots,
    timelineEvents,
    setTimelineEvents,
    updateReviewSnapshot,
  } = useRealtimeJournal({ realtimeProfileId });

  const resolveSymbolCategory = useCallback((symbol) => {
    return symbolCategoryOverrides[symbol] || metadataMap[symbol]?.type || inferSymbolCategory(symbol);
  }, [metadataMap, symbolCategoryOverrides]);

  const getSymbolsByCategory = useCallback((category) => {
    return subscribedSymbols.filter(symbol => {
      return resolveSymbolCategory(symbol) === category;
    });
  }, [resolveSymbolCategory, subscribedSymbols]);

  const {
    clearMissingQuoteRequests,
    fetchQuotes,
    freshnessNow,
    hasEverConnected,
    hasExperiencedFallback,
    isAutoUpdate,
    isBrowserOnline,
    isConnected,
    lastConnectionIssue,
    lastClientRefreshAt,
    lastMarketUpdateAt,
    loading,
    manualReconnect,
    quotes,
    reconnectAttempts,
    refreshCurrentTab,
    removeQuote,
    setIsAutoUpdate,
    transportDecisions,
  } = useRealtimeFeed({
    activeTab,
    messageApi,
    resolveSymbolsByCategory: getSymbolsByCategory,
    subscribedSymbols,
  });
  const {
    diagnosticsSummary,
    diagnosticsLoading,
    diagnosticsLastLoadedAt,
    refreshDiagnostics,
  } = useRealtimeDiagnostics({
    enabled: diagnosticsEnabled,
    isConnected,
    reconnectAttempts,
  });

  const subscribeSymbol = useCallback((symbol) => {
    if (subscribedSymbols.includes(symbol)) {
      return false;
    }

    setSubscribedSymbols(prev => [...prev, symbol]);
    messageApi.success(`已订阅 ${symbol} 的实时数据`);
    return true;
  }, [messageApi, setSubscribedSymbols, subscribedSymbols]);

  const removeSymbol = useCallback((symbol) => {
    setSubscribedSymbols(prev => prev.filter(s => s !== symbol));
    setSelectedQuoteSymbols((prev) => prev.filter((item) => item !== symbol));
    removeQuote(symbol);
  }, [removeQuote, setSubscribedSymbols]);

  const reorderWithinCategory = useCallback((fromSymbol, toSymbol) => {
    if (!fromSymbol || !toSymbol || fromSymbol === toSymbol) {
      return;
    }

    if (resolveSymbolCategory(fromSymbol) !== activeTab || resolveSymbolCategory(toSymbol) !== activeTab) {
      return;
    }

    setSubscribedSymbols((prev) => {
      const next = [...prev];
      const fromIndex = next.indexOf(fromSymbol);
      const toIndex = next.indexOf(toSymbol);

      if (fromIndex === -1 || toIndex === -1 || fromIndex === toIndex) {
        return prev;
      }

      const [movedSymbol] = next.splice(fromIndex, 1);
      const adjustedTargetIndex = next.indexOf(toSymbol);
      next.splice(adjustedTargetIndex, 0, movedSymbol);
      return next;
    });
  }, [activeTab, resolveSymbolCategory, setSubscribedSymbols]);

  const toggleAutoUpdate = useCallback((checked) => {
    setIsAutoUpdate(checked);
  }, [setIsAutoUpdate]);

  // 添加新股票
  const addSymbol = useCallback((symbol) => {
    if (!symbol) return;
    const newSymbol = symbol.trim().toUpperCase();
    if (subscribedSymbols.includes(newSymbol)) return;

    const added = subscribeSymbol(newSymbol);
    if (!added) {
      return;
    }
    const nextCategory = resolveSymbolCategory(newSymbol);
    if (nextCategory) {
      setActiveTab(nextCategory);
    }
    clearMissingQuoteRequests([newSymbol]);
    fetchQuotes([newSymbol]);
    if (!STOCK_DATABASE[newSymbol]) {
      fetchMetadata([newSymbol]);
    }
    setSearchSymbol('');
    setAutoCompleteOptions([]);
  }, [
    clearMissingQuoteRequests,
    fetchMetadata,
    fetchQuotes,
    setActiveTab,
    subscribeSymbol,
    subscribedSymbols,
    resolveSymbolCategory,
  ]);

  const handleOpenTrade = useCallback((symbol, draft = null) => {
    setSelectedSymbol(symbol);
    setTradePlanDraft(draft);
    setIsTradeModalVisible(true);
    if (draft?.symbol) {
      appendTimelineEvent({
        symbol: draft.symbol,
        kind: 'trade_plan',
        source: 'plan',
        sourceLabel: '交易计划',
        title: draft.sourceTitle || '生成交易计划',
        description: draft.note || draft.sourceDescription || `已为 ${draft.symbol} 生成交易计划草稿。`,
        action: draft.action,
        entryPrice: draft.suggestedEntry ?? draft.limitPrice,
        stopLoss: draft.stopLoss,
        takeProfit: draft.takeProfit,
        priceSnapshot: quotes[draft.symbol]?.price ?? draft.suggestedEntry ?? draft.limitPrice ?? null,
      });
    }
  }, [appendTimelineEvent, quotes]);

  const handleCloseTrade = useCallback(() => {
    setIsTradeModalVisible(false);
    setSelectedSymbol(null);
    setTradePlanDraft(null);
  }, []);

  const getDisplayName = useCallback((symbol) => {
    const metadata = metadataMap[symbol];
    if (metadata) {
      return metadata.cn || metadata.en || symbol;
    }
    const info = STOCK_DATABASE[symbol];
    if (info) {
      return info.cn || info.en || symbol;
    }
    return symbol;
  }, [metadataMap]);

  const handleShowDetail = useCallback((symbol) => {
    setDetailSymbol(symbol);
    setIsDetailModalVisible(true);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setIsDetailModalVisible(false);
    setDetailSymbol(null);
  }, []);

  const handleOpenTradeFromDetail = useCallback((symbol, draft = null) => {
    setIsDetailModalVisible(false);
    handleOpenTrade(symbol, draft);
  }, [handleOpenTrade]);

  const handleOpenAlerts = useCallback((symbol = '', draft = null) => {
    if (symbol) {
      setAlertPrefillSymbol(symbol);
      setAlertPrefillDraft(draft);
    } else {
      setAlertPrefillSymbol('');
      setAlertPrefillDraft(null);
    }
    setAlertComposerSignal(Date.now());
    setIsAlertsDrawerVisible(true);
    if (draft?.symbol) {
      appendTimelineEvent({
        symbol: draft.symbol,
        kind: 'alert_plan',
        source: 'alert',
        sourceLabel: '提醒草稿',
        title: draft.sourceTitle || '生成提醒规则',
        description: draft.sourceDescription || `已为 ${draft.symbol} 准备提醒规则草稿。`,
        condition: draft.condition,
        threshold: draft.threshold,
        priceSnapshot: quotes[draft.symbol]?.price ?? null,
      });
    }
  }, [appendTimelineEvent, quotes]);

  const handleCloseAlerts = useCallback(() => {
    setIsAlertsDrawerVisible(false);
    setAlertPrefillDraft(null);
  }, []);

  const handleCreateAlertFromTradePlan = useCallback((draft) => {
    if (!draft?.symbol) {
      return;
    }

    handleCloseTrade();
    handleOpenAlerts(draft.symbol, draft);
  }, [handleCloseTrade, handleOpenAlerts]);

  const findMatchingSymbols = useCallback((input) => {
    if (!input || input.trim() === '') return [];

    const query = input.toLowerCase().trim();
    const results = [];

    Object.entries(STOCK_DATABASE).forEach(([code, info]) => {
      if (subscribedSymbols.includes(code)) return;

      if (code.toLowerCase().includes(query)) {
        results.push({ code, info, matchType: 'code', priority: code.toLowerCase() === query ? 0 : 1 });
        return;
      }
      if (info.en.toLowerCase().includes(query)) {
        results.push({ code, info, matchType: 'en', priority: 2 });
        return;
      }
      if (info.cn.includes(query)) {
        results.push({ code, info, matchType: 'cn', priority: 2 });
        return;
      }
    });

    return results.sort((a, b) => a.priority - b.priority).slice(0, 10);
  }, [subscribedSymbols]);

  const findJumpCandidates = useCallback((input) => {
    if (!input || input.trim() === '') {
      return [];
    }

    const query = input.toLowerCase().trim();
    const trackedResults = subscribedSymbols
      .filter((code) => {
        const info = metadataMap[code] || STOCK_DATABASE[code];
        return code.toLowerCase().includes(query)
          || info?.en?.toLowerCase?.().includes(query)
          || info?.cn?.includes(query);
      })
      .map((code) => ({
        code,
        tracked: true,
        info: metadataMap[code] || STOCK_DATABASE[code] || { en: code, cn: code, type: resolveSymbolCategory(code) },
        priority: code.toLowerCase() === query ? 0 : 1,
      }));

    const addableResults = findMatchingSymbols(input).map((item) => ({
      ...item,
      tracked: false,
      priority: item.priority + 2,
    }));

    return [...trackedResults, ...addableResults]
      .sort((left, right) => left.priority - right.priority)
      .slice(0, 12);
  }, [findMatchingSymbols, metadataMap, resolveSymbolCategory, subscribedSymbols]);

  const currentTabSymbols = getSymbolsByCategory(activeTab);
  const selectedCurrentTabSymbols = selectedQuoteSymbols.filter((symbol) => currentTabSymbols.includes(symbol));
  const watchGroupSummaries = useMemo(() => (
    (watchGroups || []).map((group) => {
      const groupSymbols = (group.symbols || []).filter(Boolean);
      const weightMap = normalizeGroupWeights(group);
      const capital = Number(group.capital || 0);
      const availableQuotes = groupSymbols
        .map((symbol) => ({ symbol, quote: quotes[symbol] }))
        .filter((item) => item.quote);
      const changes = availableQuotes
        .map((item) => Number(item.quote?.change_percent))
        .filter((value) => Number.isFinite(value));
      const avgChange = changes.length
        ? changes.reduce((sum, value) => sum + value, 0) / changes.length
        : null;
      const breadth = changes.length
        ? changes.filter((value) => value > 0).length / changes.length
        : null;
      const strongest = availableQuotes
        .slice()
        .sort((left, right) => Number(right.quote?.change_percent || 0) - Number(left.quote?.change_percent || 0))[0];
      const weakest = availableQuotes
        .slice()
        .sort((left, right) => Number(left.quote?.change_percent || 0) - Number(right.quote?.change_percent || 0))[0];
      const weightEntries = groupSymbols.map((symbol) => ({
        symbol,
        weight: Number(weightMap[symbol] || 0),
        category: resolveSymbolCategory(symbol),
        quote: quotes[symbol],
      }));
      const grossWeight = weightEntries.reduce((sum, item) => sum + Math.abs(item.weight), 0);
      const netWeight = weightEntries.reduce((sum, item) => sum + item.weight, 0);
      const weightedChange = availableQuotes.length
        ? weightEntries.reduce((sum, item) => {
            const change = Number(item.quote?.change_percent);
            if (!Number.isFinite(change)) {
              return sum;
            }
            return sum + (item.weight * change);
          }, 0)
        : null;
      const estimatedPnl = capital > 0 && weightedChange !== null
        ? capital * (weightedChange / 100)
        : null;
      const exposureByCategory = weightEntries.reduce((result, item) => {
        if (!item.category) {
          return result;
        }
        result[item.category] = (result[item.category] || 0) + Math.abs(item.weight);
        return result;
      }, {});
      const topExposures = Object.entries(exposureByCategory)
        .sort((left, right) => right[1] - left[1])
        .slice(0, 2)
        .map(([category, weight]) => ({
          category,
          label: getCategoryLabelForType(category),
          weight,
        }));
      const concentration = weightEntries.length
        ? Math.max(...weightEntries.map((item) => Math.abs(item.weight)))
        : 0;

      return {
        ...group,
        trackedCount: groupSymbols.length,
        liveCount: availableQuotes.length,
        avgChange,
        breadth,
        strongest,
        weakest,
        weightedChange,
        estimatedPnl,
        capital,
        grossWeight,
        netWeight,
        concentration,
        topExposures,
        weightMap,
      };
    })
  ), [quotes, resolveSymbolCategory, watchGroups]);
  const toggleQuoteSelection = useCallback((symbol) => {
    setSelectedQuoteSymbols((prev) => (
      prev.includes(symbol)
        ? prev.filter((item) => item !== symbol)
        : [...prev, symbol]
    ));
  }, []);

  const selectAllCurrentTab = useCallback(() => {
    setSelectedQuoteSymbols(currentTabSymbols);
  }, [currentTabSymbols]);

  const clearSelectedQuotes = useCallback(() => {
    setSelectedQuoteSymbols([]);
  }, []);

  const addWatchGroup = useCallback(() => {
    const name = watchGroupName.trim();
    const parsedSymbols = watchGroupSymbols
      .split(/[\s,，]+/)
      .map((symbol) => symbol.trim().toUpperCase())
      .filter(Boolean);
    const parsedWeights = watchGroupWeights
      .split(/[\s,，]+/)
      .map((entry) => entry.trim())
      .filter(Boolean)
      .reduce((result, entry) => {
        const [rawSymbol, rawWeight] = entry.split(':');
        const symbol = String(rawSymbol || '').trim().toUpperCase();
        const numericWeight = Number(rawWeight);
        if (symbol && Number.isFinite(numericWeight)) {
          result[symbol] = numericWeight;
        }
        return result;
      }, {});
    const capital = Number(watchGroupCapital);
    if (!name || parsedSymbols.length === 0) {
      messageApi.warning('请输入组合名称和至少一个标的');
      return;
    }

    setWatchGroups((prev) => [
      {
        id: `watch-${Date.now()}`,
        name,
        symbols: Array.from(new Set(parsedSymbols)),
        notes: '',
        capital: Number.isFinite(capital) ? Math.max(capital, 0) : 0,
        weights: parsedWeights,
      },
      ...prev.filter((group) => group.name !== name),
    ]);
    setWatchGroupName('');
    setWatchGroupSymbols('');
    setWatchGroupCapital('');
    setWatchGroupWeights('');
    messageApi.success(`已创建组合 ${name}`);
  }, [messageApi, setWatchGroups, watchGroupCapital, watchGroupName, watchGroupSymbols, watchGroupWeights]);

  const removeWatchGroup = useCallback((groupId) => {
    setWatchGroups((prev) => prev.filter((group) => group.id !== groupId));
  }, [setWatchGroups]);

  const moveSelectedQuotesToCategory = useCallback((targetCategory) => {
    if (!targetCategory || selectedCurrentTabSymbols.length === 0 || targetCategory === activeTab) {
      return;
    }

    setSymbolCategoryOverrides((prev) => {
      const next = { ...prev };
      selectedCurrentTabSymbols.forEach((symbol) => {
        if (inferSymbolCategory(symbol) === targetCategory) {
          delete next[symbol];
        } else {
          next[symbol] = targetCategory;
        }
      });
      return next;
    });
    setActiveTab(targetCategory);
    setSelectedQuoteSymbols([]);
    messageApi.success(`已将 ${selectedCurrentTabSymbols.length} 个标的移动到${getCategoryLabelForType(targetCategory)}`);
  }, [activeTab, messageApi, selectedCurrentTabSymbols, setActiveTab, setSymbolCategoryOverrides]);

  const removeSelectedQuotes = useCallback(() => {
    if (selectedCurrentTabSymbols.length === 0) {
      return;
    }

    const removedCount = selectedCurrentTabSymbols.length;
    setSubscribedSymbols((prev) => prev.filter((symbol) => !selectedCurrentTabSymbols.includes(symbol)));
    selectedCurrentTabSymbols.forEach((symbol) => removeQuote(symbol));
    setSelectedQuoteSymbols([]);
    messageApi.success(`已移除 ${removedCount} 个标的`);
  }, [messageApi, removeQuote, selectedCurrentTabSymbols, setSubscribedSymbols]);

  const handleSearch = (value) => {
    setSearchSymbol(value);
    if (!value || value.trim() === '') {
      setAutoCompleteOptions([]);
      return;
    }

    const results = findMatchingSymbols(value);
    const options = results.map(({ code, info }) => ({
      value: code,
      label: (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
          <span>
            <Text strong style={{ fontSize: '14px' }}>{code}</Text>
            <Text type="secondary" style={{ marginLeft: 10 }}>{info.cn}</Text>
            <Text type="secondary" style={{ marginLeft: 6, fontSize: '12px' }}>({info.en})</Text>
          </span>
          <Tag color="blue" style={{ margin: 0 }}>
            {getCategoryLabel(info.type)}
          </Tag>
        </div>
      )
    }));
    setAutoCompleteOptions(options);
  };

  const handleSelect = (value) => {
    addSymbol(value);
    setAutoCompleteOptions([]);
  };

  const handleGlobalJumpSearch = useCallback((value) => {
    setGlobalJumpQuery(value);
    if (!value || value.trim() === '') {
      setGlobalJumpOptions([]);
      return;
    }

    const options = findJumpCandidates(value).map(({ code, info, tracked }) => ({
      value: code,
      label: (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
          <span>
            <Text strong style={{ fontSize: '14px' }}>{code}</Text>
            <Text type="secondary" style={{ marginLeft: 10 }}>{info?.cn || code}</Text>
          </span>
          <Tag color={tracked ? 'geekblue' : 'blue'} style={{ margin: 0 }}>
            {tracked ? '已跟踪' : '可添加'}
          </Tag>
        </div>
      ),
    }));
    setGlobalJumpOptions(options);
  }, [findJumpCandidates]);

  const handleGlobalJumpSelect = useCallback((value) => {
    const normalized = String(value || '').trim().toUpperCase();
    if (!normalized) {
      return;
    }

    if (subscribedSymbols.includes(normalized)) {
      setActiveTab(resolveSymbolCategory(normalized));
      handleShowDetail(normalized);
      messageApi.success(`已跳转到 ${normalized} 的实时详情`);
    } else {
      addSymbol(normalized);
    }

    setGlobalJumpQuery('');
    setGlobalJumpOptions([]);
  }, [addSymbol, handleShowDetail, messageApi, resolveSymbolCategory, setActiveTab, subscribedSymbols]);

  const getCategoryLabel = getCategoryLabelForType;

  const getCategoryTheme = (type) => CATEGORY_THEMES[type] || CATEGORY_THEMES.other;
  const getQuoteRangePercent = useCallback((quote) => {
    const high = Number(quote?.high);
    const low = Number(quote?.low);
    const base = Number(quote?.previous_close ?? quote?.price);
    if (![high, low, base].every(Number.isFinite) || base <= 0) {
      return null;
    }
    return ((high - low) / base) * 100;
  }, []);
  const getQuoteSortValue = useCallback((symbol, quote, mode) => {
    switch (mode) {
      case 'range_desc':
        return getQuoteRangePercent(quote) ?? Number.NEGATIVE_INFINITY;
      case 'volume_desc':
        return hasNumericValue(quote?.volume) ? Number(quote.volume) : Number.NEGATIVE_INFINITY;
      case 'symbol_asc':
        return symbol;
      case 'change_desc':
      default:
        return hasNumericValue(quote?.change_percent) ? Number(quote.change_percent) : Number.NEGATIVE_INFINITY;
    }
  }, [getQuoteRangePercent]);
  const sortSymbolsForDisplay = useCallback((symbols) => {
    return [...symbols].sort((left, right) => {
      const leftQuote = quotes[left];
      const rightQuote = quotes[right];
      const leftValue = getQuoteSortValue(left, leftQuote, quoteSortMode);
      const rightValue = getQuoteSortValue(right, rightQuote, quoteSortMode);

      if (quoteSortMode === 'symbol_asc') {
        return String(leftValue).localeCompare(String(rightValue));
      }

      if (leftValue === rightValue) {
        return left.localeCompare(right);
      }

      return Number(rightValue) - Number(leftValue);
    });
  }, [getQuoteSortValue, quoteSortMode, quotes]);
  const diagnosticsCache = diagnosticsSummary?.cache || {};
  const diagnosticsFetch = diagnosticsCache.last_fetch_stats || {};
  const diagnosticsQuality = diagnosticsSummary?.quality || {};
  const weakestFields = Array.isArray(diagnosticsQuality.field_coverage)
    ? [...diagnosticsQuality.field_coverage]
      .sort((left, right) => left.coverage_ratio - right.coverage_ratio)
      .slice(0, 3)
    : [];
  const weakestSymbols = Array.isArray(diagnosticsQuality.most_incomplete_symbols)
    ? diagnosticsQuality.most_incomplete_symbols.slice(0, 3)
    : [];
  const formatTransportDecision = (decision) => {
    const modeLabelMap = {
      rest_fallback: 'REST 补数',
      warmup_snapshot: 'Warmup Snapshot',
      manual_snapshot: '手动 Snapshot',
      manual_rest: '手动 REST',
    };

    const modeLabel = modeLabelMap[decision.mode] || decision.mode;
    const symbolLabel = decision.symbols?.length ? decision.symbols.join(', ') : '--';
    return `${modeLabel} -> ${symbolLabel}`;
  };

  const getQuoteFreshness = useCallback((quote) => {
    if (!quote?._clientReceivedAt) {
      return {
        state: 'pending',
        label: '待补数',
        detail: null,
        tone: {
          color: '#64748b',
          background: 'rgba(100, 116, 139, 0.12)',
        },
      };
    }

    const marketTimestampMs = Number.isFinite(quote._marketTimestampMs) ? quote._marketTimestampMs : null;
    const marketAgeMs = marketTimestampMs ? Math.max(0, freshnessNow - marketTimestampMs) : null;
    const clientAgeMs = Math.max(0, freshnessNow - quote._clientReceivedAt);
    const effectiveAgeMs = marketAgeMs ?? clientAgeMs;
    const receivedLabel = formatRelativeAge(clientAgeMs);

    if (effectiveAgeMs <= QUOTE_FRESH_MS) {
      return {
        state: 'fresh',
        label: marketAgeMs !== null ? '行情刚刚更新' : '刚刚更新',
        detail: marketAgeMs !== null ? `接收链路${receivedLabel}` : null,
        tone: {
          color: '#15803d',
          background: 'rgba(34, 197, 94, 0.14)',
        },
      };
    }

    if (effectiveAgeMs <= QUOTE_DELAYED_MS) {
      return {
        state: 'aging',
        label: marketAgeMs !== null
          ? formatRelativeAge(effectiveAgeMs, { prefix: '行情 ' })
          : formatRelativeAge(effectiveAgeMs),
        detail: marketAgeMs !== null ? `接收链路${receivedLabel}` : null,
        tone: {
          color: '#b45309',
          background: 'rgba(245, 158, 11, 0.16)',
        },
      };
    }

    return {
      state: 'delayed',
      label: marketAgeMs !== null
        ? `行情延迟 ${Math.max(1, Math.floor(effectiveAgeMs / 60000))} 分钟`
        : `延迟 ${Math.max(1, Math.floor(effectiveAgeMs / 60000))} 分钟`,
      detail: marketAgeMs !== null ? `接收链路${receivedLabel}` : null,
      tone: {
        color: '#b91c1c',
        background: 'rgba(239, 68, 68, 0.14)',
      },
    };
  }, [freshnessNow]);

  const anomalyFeed = buildRealtimeAnomalyFeed(currentTabSymbols, quotes, { limit: 6 });
  useEffect(() => {
    if (typeof window === 'undefined' || typeof Notification === 'undefined') {
      return;
    }

    if (Notification.permission !== 'granted') {
      return;
    }

    const now = Date.now();
    const cooldownMs = 10 * 60 * 1000;
    const notifications = notifiedAnomaliesRef.current;

    anomalyFeed.forEach((item) => {
      if (!item?.id || !['high', 'critical'].includes(item.level)) {
        return;
      }

      const lastNotifiedAt = notifications.get(item.id) || 0;
      if (now - lastNotifiedAt < cooldownMs) {
        return;
      }

      notifications.set(item.id, now);
      new Notification(`异动雷达: ${item.symbol}`, {
        body: `${item.title} · ${item.description}`,
      });
    });

    if (notifications.size > 80) {
      const activeIds = new Set(anomalyFeed.map((item) => item.id));
      Array.from(notifications.keys()).forEach((key) => {
        if (!activeIds.has(key)) {
          notifications.delete(key);
        }
      });
    }
  }, [anomalyFeed]);
  const filteredReviewSnapshots = filterReviewSnapshots(reviewSnapshots, reviewScope, activeTab);
  const reviewScopeLabel = REVIEW_SCOPE_OPTIONS.find((option) => option.key === reviewScope)?.label || '全部';
  const latestSnapshots = filteredReviewSnapshots.slice(0, 3);
  const {
    currentTabAlertFollowThrough,
    currentTabAlertHitSummary,
    currentTabQuotes,
    fallingCount,
    freshnessSummary,
    lastClientRefreshLabel,
    lastMarketUpdateLabel,
    loadedQuotesCount,
    marketSentiment,
    realtimeActionPosture,
    resolvedSnapshotCount,
    reviewAttribution,
    reviewOutcomeSummary,
    risingCount,
    spotlightSymbol,
    transportBanner,
    transportBannerStyle,
    transportModeLabel,
    validationRate,
  } = useRealtimeDerivedState({
    alertHitHistory,
    anomalyFeed,
    currentTabSymbols,
    filteredReviewSnapshots,
    hasEverConnected,
    hasExperiencedFallback,
    isAutoUpdate,
    isConnected,
    lastClientRefreshAt,
    lastConnectionIssue,
    lastMarketUpdateAt,
    freshnessNow,
    getQuoteFreshness,
    quotes,
    reconnectAttempts,
  });
  const detailEventTimeline = buildRealtimeDetailTimeline({
    symbol: detailSymbol,
    anomalyFeed,
    reviewSnapshots,
    actionEvents: timelineEvents,
    alertHistory: alertHitHistory,
  });
  const detailCompareCandidates = currentTabSymbols
    .filter((symbol) => symbol && quotes[symbol])
    .filter((symbol, index, list) => list.indexOf(symbol) === index)
    .sort((left, right) => Math.abs(Number(quotes[right]?.change_percent || 0)) - Math.abs(Number(quotes[left]?.change_percent || 0)))
    .slice(0, 6)
    .map((candidateSymbol) => ({
      symbol: candidateSymbol,
      name: getDisplayName(candidateSymbol),
      quote: quotes[candidateSymbol] || null,
    }));
  const detailCompareTimelineMap = detailCompareCandidates.reduce((accumulator, item) => {
    accumulator[item.symbol] = buildRealtimeDetailTimeline({
      symbol: item.symbol,
      anomalyFeed,
      reviewSnapshots,
      actionEvents: timelineEvents,
      alertHistory: alertHitHistory,
    });
    return accumulator;
  }, {});

  const saveReviewSnapshot = useCallback(() => {
    const snapshot = {
      id: `snapshot_${Date.now()}`,
      createdAt: new Date().toISOString(),
      version: REVIEW_SNAPSHOT_VERSION,
      activeTab,
      activeTabLabel: getCategoryLabel(activeTab),
      transportModeLabel,
      spotlightSymbol,
      spotlightName: spotlightSymbol ? getDisplayName(spotlightSymbol) : null,
      watchedSymbols: currentTabSymbols.slice(0, 8),
      quoteSnapshots: currentTabSymbols.slice(0, 8).map((symbol) => {
        const quote = quotes[symbol];
        return {
          symbol,
          price: hasNumericValue(quote?.price) ? Number(quote.price).toFixed(2) : '--',
          changePercent: hasNumericValue(quote?.change_percent) ? `${Number(quote.change_percent).toFixed(2)}%` : '--',
          volume: hasNumericValue(quote?.volume) ? Number(quote.volume).toLocaleString() : '--',
        };
      }),
      loadedCount: currentTabQuotes.length,
      totalCount: currentTabSymbols.length,
      anomalyCount: anomalyFeed.length,
      anomalies: anomalyFeed.slice(0, 3).map((item) => ({
        symbol: item.symbol,
        title: item.title,
        description: item.description,
      })),
      freshnessSummary,
      note: '',
      outcome: null,
    };

    setReviewSnapshots((prev) => [snapshot, ...prev].slice(0, MAX_REVIEW_SNAPSHOTS));
    if (spotlightSymbol) {
      appendTimelineEvent({
        symbol: spotlightSymbol,
        kind: 'review_snapshot',
        source: 'review',
        sourceLabel: '复盘快照',
        title: `保存复盘快照 · ${getCategoryLabel(activeTab)}`,
        description: `记录了 ${anomalyFeed.length} 条异动与 ${currentTabQuotes.length}/${currentTabSymbols.length} 条已加载行情。`,
        createdAt: snapshot.createdAt,
        priceSnapshot: quotes[spotlightSymbol]?.price ?? null,
      });
    }
    messageApi.success('已保存当前复盘快照');
  // quotes is intentionally omitted here to keep the snapshot callback stable for UI interactions.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    activeTab,
    anomalyFeed,
    appendTimelineEvent,
    currentTabQuotes.length,
    currentTabSymbols,
    freshnessSummary,
    getDisplayName,
    messageApi,
    quotes,
    spotlightSymbol,
    transportModeLabel,
  ]);

  const restoreSnapshot = useCallback((snapshot) => {
    if (!snapshot?.activeTab) {
      return;
    }

    setActiveTab(snapshot.activeTab);
    setIsSnapshotDrawerVisible(false);
    messageApi.success(`已切换到 ${snapshot.activeTabLabel || getCategoryLabelForType(snapshot.activeTab)} 复盘视角`);
  }, [messageApi, setActiveTab]);

  const openSnapshotFocus = useCallback((snapshot) => {
    if (!snapshot?.spotlightSymbol) {
      return;
    }

    setActiveTab(snapshot.activeTab || inferSymbolCategory(snapshot.spotlightSymbol));
    setDetailSymbol(snapshot.spotlightSymbol);
    setIsDetailModalVisible(true);
  }, [setActiveTab]);

  const copyTextToClipboard = useCallback(async (content, successText) => {
    if (!navigator?.clipboard?.writeText) {
      messageApi.warning('当前环境不支持剪贴板复制');
      return;
    }

    try {
      await navigator.clipboard.writeText(content);
      messageApi.success(successText);
    } catch (error) {
      messageApi.error('复制失败，请稍后重试');
    }
  }, [messageApi]);

  const openShareWindow = useCallback((title, bodyHtml) => {
    if (typeof window === 'undefined' || typeof window.open !== 'function') {
      messageApi.warning('当前环境不支持分享卡片预览');
      return;
    }

    const shareWindow = window.open('', '_blank', 'noopener,noreferrer,width=960,height=760');

    if (!shareWindow?.document) {
      messageApi.warning('分享窗口被浏览器拦截了，请允许弹窗后重试');
      return;
    }

    shareWindow.document.write(buildRealtimeShareDocument(title, bodyHtml));
    shareWindow.document.close();
  }, [messageApi]);

  const openSnapshotShareCard = useCallback((snapshot) => {
    openShareWindow(
      `Realtime Review Snapshot - ${snapshot?.spotlightName || snapshot?.spotlightSymbol || '未记录焦点标的'}`,
      formatReviewSnapshotShareHtml(snapshot, getSnapshotOutcomeMeta)
    );
  }, [openShareWindow]);

  const openReviewSummaryShareCard = useCallback(() => {
    openShareWindow(
      `Realtime Review Summary - ${reviewScopeLabel}`,
      formatReviewSummaryShareHtml({
        scopeLabel: reviewScopeLabel,
        filteredReviewSnapshots,
        reviewOutcomeSummary,
        validationRate,
        reviewAttribution,
      })
    );
  }, [
    filteredReviewSnapshots,
    openShareWindow,
    reviewAttribution,
    reviewOutcomeSummary,
    reviewScopeLabel,
    validationRate,
  ]);

  const exportReviewSnapshots = useCallback(() => {
    const payload = JSON.stringify({
      version: REALTIME_EXPORT_VERSION,
      exported_at: new Date().toISOString(),
      review_snapshots: reviewSnapshots,
      timeline_events: timelineEvents,
    }, null, 2);
    copyTextToClipboard(payload, '复盘快照 JSON 已复制');
  }, [copyTextToClipboard, reviewSnapshots, timelineEvents]);

  const triggerSnapshotImport = useCallback(() => {
    snapshotImportInputRef.current?.click();
  }, []);

  const handleImportReviewSnapshots = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result || '[]'));
        const snapshotPayload = Array.isArray(parsed)
          ? parsed
          : parsed?.review_snapshots;
        const timelinePayload = Array.isArray(parsed)
          ? []
          : parsed?.timeline_events;

        if (!Array.isArray(snapshotPayload)) {
          throw new Error('invalid payload');
        }

        const normalized = snapshotPayload
          .map(normalizeReviewSnapshot)
          .filter(Boolean)
          .sort((left, right) => new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime())
          .slice(0, MAX_REVIEW_SNAPSHOTS);
        const normalizedTimeline = Array.isArray(timelinePayload)
          ? timelinePayload
              .map(normalizeTimelineEvent)
              .filter(Boolean)
              .slice(0, MAX_TIMELINE_EVENTS)
          : [];

        setReviewSnapshots(normalized);
        setTimelineEvents(normalizedTimeline);
        messageApi.success(`已导入 ${normalized.length} 条复盘快照`);
      } catch (error) {
        messageApi.error('复盘快照导入失败，请检查 JSON 格式');
      } finally {
        event.target.value = '';
      }
    };
    reader.readAsText(file);
  }, [messageApi, setReviewSnapshots, setTimelineEvents]);

  const tabs = [
    { key: 'index', label: '指数', icon: <BarChartOutlined /> },
    { key: 'us', label: '美股', icon: <StockOutlined /> },
    { key: 'cn', label: 'A股', icon: <StockOutlined /> },
    { key: 'crypto', label: '加密', icon: <ThunderboltOutlined /> },
    { key: 'bond', label: '债券', icon: <BankOutlined /> },
    { key: 'future', label: '期货', icon: <PropertySafetyOutlined /> },
    { key: 'option', label: '期权', icon: <FundOutlined /> },
  ];

  const freshnessDetailParts = [];
  if (freshnessSummary.aging > 0) freshnessDetailParts.push(`变旧 ${freshnessSummary.aging}`);
  if (freshnessSummary.delayed > 0) freshnessDetailParts.push(`延迟 ${freshnessSummary.delayed}`);
  if (freshnessSummary.pending > 0) freshnessDetailParts.push(`待补数 ${freshnessSummary.pending}`);

  const heroPrimaryStats = [
    {
      key: 'active-tab',
      label: '当前分组',
      value: getCategoryLabel(activeTab),
      detail: `${currentTabSymbols.length} 个标的位于当前视图`,
    },
    {
      key: 'coverage',
      label: '样本覆盖',
      value: `${loadedQuotesCount ?? 0}/${subscribedSymbols.length}`,
      detail: `接收时间 ${lastClientRefreshLabel}`,
    },
    {
      key: 'freshness',
      label: '新鲜行情',
      value: `${freshnessSummary.fresh ?? 0}/${currentTabSymbols.length}`,
      detail: freshnessDetailParts.length ? freshnessDetailParts.join(' · ') : '当前分组行情新鲜度正常',
    },
    {
      key: 'alerts',
      label: '提醒命中',
      value: `${currentTabAlertHitSummary.totalHits ?? 0}`,
      detail: spotlightSymbol
        ? `焦点 ${getDisplayName(spotlightSymbol)} ${formatPercent(quotes[spotlightSymbol]?.change_percent)}`
        : '当前未锁定焦点标的',
    },
  ];

  const spotlightChangeLabel = spotlightSymbol
    ? formatPercent(quotes[spotlightSymbol]?.change_percent)
    : null;

  const heroSignalToneStyles = realtimeActionPosture.level === 'warning'
    ? {
        borderColor: 'rgba(250, 173, 20, 0.55)',
        background: 'rgba(250, 173, 20, 0.10)',
        color: 'var(--text-primary)',
      }
    : realtimeActionPosture.level === 'success'
      ? {
          borderColor: 'rgba(82, 196, 26, 0.45)',
          background: 'rgba(82, 196, 26, 0.10)',
          color: 'var(--text-primary)',
        }
      : {
          borderColor: transportBannerStyle.borderColor,
          background: transportBannerStyle.background,
          color: transportBannerStyle.color,
        };

  const overviewPrimaryStats = [
    {
      key: 'total',
      label: '监控总数',
      value: `${subscribedSymbols.length}`,
      detail: '跨市场订阅中的标的',
      tone: 'primary',
    },
    {
      key: 'rising',
      label: '上涨',
      value: `${risingCount ?? 0}`,
      detail: '已覆盖标的中上涨数量',
      tone: 'positive',
    },
    {
      key: 'falling',
      label: '下跌',
      value: `${fallingCount ?? 0}`,
      detail: '已覆盖标的中下跌数量',
      tone: 'negative',
    },
  ];
  const overviewSummary = `当前分组 ${getCategoryLabel(activeTab)} 已加载 ${currentTabSymbols.length} 个标的；全局盘面 ${marketSentiment.label}，${marketSentiment.detail}`;

  return (
    <div className="realtime-panel-shell app-page-shell app-page-shell--wide realtime-page-shell">
      <div className="app-page-section-block">
        <div className="app-page-section-kicker">实时指挥席</div>
        <Card
          className="realtime-hero-card"
          style={{
            borderRadius: 28,
            overflow: 'hidden',
            border: '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)',
            boxShadow: '0 24px 60px rgba(15, 23, 42, 0.10)',
          }}
          styles={{ body: { padding: 0 } }}
        >
          <div className="realtime-hero">
            <div className="realtime-hero__main">
              <div className="realtime-hero__statusbar">
                <div className="realtime-hero__eyebrow">Realtime Radar</div>
                <div className="realtime-hero__status-meta">
                  {spotlightSymbol && (
                    <div className="realtime-hero__focus-pill">
                      <span className="realtime-hero__focus-label">当前焦点</span>
                      <span className="realtime-hero__focus-text">
                        {getDisplayName(spotlightSymbol)} · {spotlightSymbol} · {spotlightChangeLabel}
                      </span>
                    </div>
                  )}
                  <Tag
                    color={isConnected ? 'success' : 'error'}
                    style={{ margin: 0, borderRadius: 999, paddingInline: 12, fontWeight: 700 }}
                  >
                    {isConnected ? '已连接' : '未连接'}
                  </Tag>
                </div>
              </div>
              <div className="realtime-hero__title-row">
                <div className="realtime-hero__headline">
                  <Space>
                    <Badge status={isConnected ? 'processing' : 'error'} />
                    <Text strong style={{ fontSize: '24px', color: 'var(--text-primary)' }}>实时行情工作台</Text>
                  </Space>
                  <div className="realtime-hero__subtitle">
                    先确认链路和分组状态，再直接进入卡片盯盘、提醒和详情联动。
                  </div>
                </div>
              </div>
              <div className="realtime-hero__meta">
                <div className="realtime-hero__chip">当前分组：{getCategoryLabel(activeTab)}</div>
                <div className="realtime-hero__chip">链路模式：{transportModeLabel}</div>
                <div className="realtime-hero__chip">自动更新：{isAutoUpdate ? '开启' : '暂停'}</div>
                <div className="realtime-hero__chip">行情时间：{lastMarketUpdateLabel}</div>
                {reconnectAttempts > 0 && <div className="realtime-hero__chip">重连 {reconnectAttempts}</div>}
              </div>
              <div className="realtime-hero__metric-grid">
                {heroPrimaryStats.map((item) => (
                  <div key={item.key} className="realtime-hero__metric">
                    <div className="realtime-hero__metric-label">{item.label}</div>
                    <div className="realtime-hero__metric-value">{item.value}</div>
                    <div className="realtime-hero__metric-detail">{item.detail}</div>
                  </div>
                ))}
              </div>
              {!isConnected && (
                <div className="realtime-hero__telemetry">
                  <Button
                    type="link"
                    size="small"
                    icon={<SyncOutlined />}
                    onClick={manualReconnect}
                    style={{ padding: 0, height: 'auto', fontSize: 12 }}
                  >
                    手动重连
                  </Button>
                </div>
              )}
            </div>

            <div className="realtime-hero__sidecar">
              <div className="realtime-hero__action-row">
                <Button
                  className="realtime-hero__refresh"
                  type="primary"
                  icon={<SyncOutlined spin={loading} />}
                  onClick={refreshCurrentTab}
                  loading={loading}
                  size="large"
                >
                  刷新
                </Button>
                <Button
                  className="realtime-hero__secondary-button"
                  icon={<BellOutlined />}
                  onClick={() => handleOpenAlerts()}
                  size="large"
                >
                  价格提醒
                </Button>
              </div>
              <div className="realtime-hero__utility-row">
                <div className="realtime-hero__toggle-pill">
                  <Text style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>自动更新</Text>
                  <Switch
                    checked={isAutoUpdate}
                    onChange={toggleAutoUpdate}
                    checkedChildren={<PlayCircleOutlined />}
                    unCheckedChildren={<PauseCircleOutlined />}
                  />
                </div>
                <div className="realtime-hero__utility-actions">
                  <Button className="realtime-hero__secondary-button" onClick={saveReviewSnapshot}>
                    保存快照
                  </Button>
                  <Button type="text" onClick={() => setIsSnapshotDrawerVisible(true)}>
                    查看复盘快照
                  </Button>
                </div>
              </div>
              <div className="realtime-hero__signal-stack">
                {!isBrowserOnline && (
                  <div
                    className="realtime-hero__signal-card"
                    style={{
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                      background: 'rgba(239, 68, 68, 0.10)',
                      color: '#b91c1c',
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: 13 }}>浏览器已离线</div>
                    <div style={{ marginTop: 4, fontSize: 12, lineHeight: 1.6 }}>
                      网络连接已中断，实时数据暂停更新。恢复网络后将自动重连。
                    </div>
                  </div>
                )}
                <div
                  className="realtime-hero__signal-card"
                  style={{
                    border: `1px solid ${heroSignalToneStyles.borderColor}`,
                    background: heroSignalToneStyles.background,
                    color: heroSignalToneStyles.color,
                  }}
                >
                  <div className="realtime-hero__signal-pill-row">
                    <span className="realtime-hero__signal-pill">{transportBanner.title}</span>
                    <span className="realtime-hero__signal-pill realtime-hero__signal-pill--accent">{realtimeActionPosture.title}</span>
                  </div>
                  <div className="realtime-hero__signal-card-detail">{realtimeActionPosture.actionHint}</div>
                  <div className="realtime-hero__signal-card-detail realtime-hero__signal-card-detail--muted">
                    {transportBanner.description}
                  </div>
                  <div className="realtime-hero__signal-card-detail realtime-hero__signal-card-detail--muted">
                    {realtimeActionPosture.reason}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div className="app-page-section-block">
        <div className="app-page-section-kicker">盯盘与异动</div>
        <RealtimeQuoteBoard
          EMPTY_NUMERIC_TEXT={EMPTY_NUMERIC_TEXT}
          activeTab={activeTab}
          onActiveTabChange={setActiveTab}
          buildMiniTrendSeries={buildMiniTrendSeries}
          buildSparklinePoints={buildSparklinePoints}
          currentTabSymbols={currentTabSymbols}
          draggingSymbol={draggingSymbol}
          formatPrice={formatPrice}
          formatPercent={formatPercent}
          formatQuoteTime={formatQuoteTime}
          formatVolume={formatVolume}
          getCategoryLabel={getCategoryLabel}
          getCategoryTheme={getCategoryTheme}
          getDisplayName={getDisplayName}
          getQuoteFreshness={getQuoteFreshness}
          getSymbolsByCategory={getSymbolsByCategory}
          handleOpenAlerts={handleOpenAlerts}
          handleOpenTrade={handleOpenTrade}
          handleShowDetail={handleShowDetail}
          hasNumericValue={hasNumericValue}
          inferSymbolCategory={inferSymbolCategory}
          categoryOptions={CATEGORY_OPTIONS}
          onClearSelectedQuotes={clearSelectedQuotes}
          onMoveSelectedQuotesToCategory={moveSelectedQuotesToCategory}
          onRemoveSelectedQuotes={removeSelectedQuotes}
          onSelectAllCurrentTab={selectAllCurrentTab}
          onSetDraggingSymbol={setDraggingSymbol}
          onToggleQuoteSelection={toggleQuoteSelection}
          quoteSortMode={quoteSortMode}
          onQuoteSortModeChange={setQuoteSortMode}
          quoteSortOptions={QUOTE_SORT_OPTIONS}
          quoteViewMode={quoteViewMode}
          onQuoteViewModeChange={setQuoteViewMode}
          quotes={quotes}
          removeSymbol={removeSymbol}
          reorderWithinCategory={reorderWithinCategory}
          selectedCurrentTabSymbols={selectedCurrentTabSymbols}
          selectedQuoteSymbols={selectedQuoteSymbols}
          resolveSymbolCategory={resolveSymbolCategory}
          sortSymbolsForDisplay={sortSymbolsForDisplay}
          tabs={tabs}
        />

        <RealtimeAnomalyRadar
          anomalyFeed={anomalyFeed}
          buildAlertDraftFromAnomaly={buildAlertDraftFromAnomaly}
          buildTradePlanDraftFromAnomaly={buildTradePlanDraftFromAnomaly}
          formatQuoteTime={formatQuoteTime}
          getDisplayName={getDisplayName}
          handleOpenAlerts={handleOpenAlerts}
          handleOpenTrade={handleOpenTrade}
          handleShowDetail={handleShowDetail}
          isExpanded={isAnomalyExpanded}
          onToggleExpanded={() => setIsAnomalyExpanded(prev => !prev)}
          quotes={quotes}
        />

        <RealtimeAlertHistoryCard
          currentTabAlertFollowThrough={currentTabAlertFollowThrough}
          currentTabAlertHitSummary={currentTabAlertHitSummary}
          formatQuoteTime={formatQuoteTime}
          handleOpenAlerts={handleOpenAlerts}
          handleShowDetail={handleShowDetail}
          isExpanded={isAlertHistoryExpanded}
          onToggleExpanded={() => setIsAlertHistoryExpanded(prev => !prev)}
        />
      </div>

      <div className="app-page-section-block">
        <div className="app-page-section-kicker">工作台工具</div>
        <div className="realtime-overview-grid">
          <Card
            className="realtime-search-card"
            style={{
              borderRadius: 24,
              border: '1px solid var(--border-color)',
              boxShadow: '0 14px 34px rgba(15, 23, 42, 0.06)',
            }}
          >
            <div className="realtime-block-title">添加跟踪标的</div>
            <div className="realtime-block-subtitle">把新增标的与快速跳转合并在同一层，减少从搜索到看盘的路径长度。</div>
            <div className="realtime-search-grid">
              <div className="realtime-search-panel">
                <div className="realtime-search-panel__title">添加跟踪</div>
                <div className="realtime-search-panel__hint">支持代码、英文名和中文名，添加后会自动进入对应分组。</div>
                <Space.Compact style={{ width: '100%', marginTop: 14 }}>
                  <AutoComplete
                    style={{ flex: 1 }}
                    options={autoCompleteOptions}
                    value={searchSymbol}
                    onChange={handleSearch}
                    onSelect={handleSelect}
                  >
                    <Input
                      aria-label="添加跟踪标的搜索"
                      name="tracked_symbol_search"
                      autoComplete="off"
                      placeholder="搜索... (支持指数、美股、A股、加密货币、债券等)"
                      prefix={<SearchOutlined />}
                      allowClear
                      size="large"
                      onPressEnter={() => addSymbol(searchSymbol)}
                    />
                  </AutoComplete>
                  <Button type="primary" size="large" onClick={() => addSymbol(searchSymbol)}>
                    添加
                  </Button>
                </Space.Compact>
              </div>

              <div className="realtime-search-panel">
                <div className="realtime-search-panel__title">全局跳转</div>
                <div className="realtime-search-panel__hint">输入已跟踪标的可直接切组并打开详情，未跟踪标的则直接加入工作台。</div>
                <Space.Compact style={{ width: '100%', marginTop: 14 }}>
                  <AutoComplete
                    style={{ flex: 1 }}
                    options={globalJumpOptions}
                    value={globalJumpQuery}
                    onChange={handleGlobalJumpSearch}
                    onSelect={handleGlobalJumpSelect}
                  >
                    <Input
                      aria-label="全局跳转搜索"
                      name="global_jump_search"
                      autoComplete="off"
                      placeholder="全局搜索并跳转... (例如 AAPL / BTC-USD / 纳指)"
                      prefix={<SearchOutlined />}
                      allowClear
                      size="large"
                      onPressEnter={() => handleGlobalJumpSelect(globalJumpQuery)}
                    />
                  </AutoComplete>
                  <Button size="large" onClick={() => handleGlobalJumpSelect(globalJumpQuery)}>
                    跳转
                  </Button>
                </Space.Compact>
              </div>
            </div>
          </Card>

          <Card
            className="realtime-overview-card"
            style={{
              borderRadius: 24,
              border: '1px solid var(--border-color)',
              boxShadow: '0 14px 34px rgba(15, 23, 42, 0.06)',
            }}
          >
            <div className="realtime-block-title">市场概览</div>
            <div className="realtime-block-subtitle">先看覆盖面、涨跌分布与情绪状态，再进入主看盘区处理细节。</div>
            <div className="realtime-overview-brief">
              <div className="realtime-overview-brief__label">市场情绪</div>
              <div className="realtime-overview-brief__value">{marketSentiment.label}</div>
              <div className="realtime-overview-brief__detail">{overviewSummary}</div>
            </div>
            <div className="realtime-overview-stats realtime-overview-stats--compact">
              {overviewPrimaryStats.map((item) => (
                <div key={item.key} className={`realtime-overview-stat realtime-overview-stat--${item.tone}`}>
                  <div className="realtime-overview-stat__label">{item.label}</div>
                  <div className="realtime-overview-stat__value">{item.value}</div>
                  <div className="realtime-overview-stat__detail">{item.detail}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className="app-page-section-block">
        <div className="app-page-section-kicker">组合监控与敞口</div>
        <Card
          style={{
            borderRadius: 24,
            border: '1px solid var(--border-color)',
            boxShadow: '0 14px 34px rgba(15, 23, 42, 0.06)',
          }}
        >
          <div className="realtime-block-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FolderOutlined />
            自选组合监控
          </div>
          <div className="realtime-block-subtitle">
            把多个标的组织成“科技重仓”“对冲腿”等组合，实时观察组合级涨跌、宽度和最强驱动。
          </div>
          <Space.Compact style={{ width: '100%', marginTop: 16 }}>
            <Input
              style={{ maxWidth: 220 }}
              aria-label="自选组合名称"
              name="watch_group_name"
              autoComplete="off"
              value={watchGroupName}
              onChange={(event) => setWatchGroupName(event.target.value)}
              placeholder="组合名称"
            />
            <Input
              aria-label="自选组合标的列表"
              name="watch_group_symbols"
              autoComplete="off"
              value={watchGroupSymbols}
              onChange={(event) => setWatchGroupSymbols(event.target.value)}
              placeholder="标的列表，逗号分隔，如 AAPL, MSFT, NVDA"
              onPressEnter={addWatchGroup}
            />
            <Button type="primary" onClick={addWatchGroup}>添加组合</Button>
          </Space.Compact>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'minmax(180px, 220px) minmax(260px, 1fr)', marginTop: 12 }}>
            <Input
              aria-label="自选组合资金"
              name="watch_group_capital"
              autoComplete="off"
              inputMode="decimal"
              value={watchGroupCapital}
              onChange={(event) => setWatchGroupCapital(event.target.value)}
              placeholder="组合资金，可选，如 100000"
            />
            <Input
              aria-label="自选组合权重"
              name="watch_group_weights"
              autoComplete="off"
              value={watchGroupWeights}
              onChange={(event) => setWatchGroupWeights(event.target.value)}
              placeholder="权重/对冲腿，可选，如 AAPL:0.5 MSFT:0.3 NVDA:-0.2"
            />
          </div>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', marginTop: 18 }}>
            {watchGroupSummaries.length ? watchGroupSummaries.map((group) => (
              <div
                key={group.id}
                style={{
                  borderRadius: 16,
                  padding: 16,
                  border: '1px solid rgba(148, 163, 184, 0.18)',
                  background: 'rgba(15, 23, 42, 0.02)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15 }}>{group.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                      {group.trackedCount} 个标的 · 实时覆盖 {group.liveCount}/{group.trackedCount}
                    </div>
                  </div>
                  <Button
                    type="text"
                    icon={<DeleteOutlined />}
                    aria-label={`删除组合 ${group.name}`}
                    onClick={() => removeWatchGroup(group.id)}
                  />
                </div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
                  <Tag color={Number(group.avgChange || 0) >= 0 ? 'green' : 'red'}>
                    组合均值 {group.avgChange === null ? '--' : formatPercent(group.avgChange)}
                  </Tag>
                  <Tag color={Number(group.weightedChange || 0) >= 0 ? 'green' : 'red'}>
                    加权收益 {group.weightedChange === null ? '--' : formatPercent(group.weightedChange)}
                  </Tag>
                  <Tag color="blue">
                    上涨宽度 {group.breadth === null ? '--' : `${Math.round(group.breadth * 100)}%`}
                  </Tag>
                  <Tag color="purple">
                    估算 P&L {group.estimatedPnl === null ? '--' : formatCompactCurrency(group.estimatedPnl)}
                  </Tag>
                </div>
                <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {group.strongest
                    ? `最强驱动：${getDisplayName(group.strongest.symbol)} ${formatPercent(group.strongest.quote?.change_percent)}`
                    : '等待实时行情覆盖后显示组合驱动。'}
                </div>
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {`净暴露 ${group.netWeight.toFixed(2)}x · 总暴露 ${group.grossWeight.toFixed(2)}x · 最大单名权重 ${(group.concentration * 100).toFixed(0)}%`}
                </div>
                <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {group.topExposures.length
                    ? group.topExposures.map((item) => (
                      <Tag key={`${group.id}-${item.category}`} color="geekblue">
                        {`${item.label} 暴露 ${(item.weight * 100).toFixed(0)}%`}
                      </Tag>
                    ))
                    : <Tag>等待暴露计算</Tag>}
                </div>
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {group.weakest
                    ? `最弱标的：${getDisplayName(group.weakest.symbol)} ${formatPercent(group.weakest.quote?.change_percent)}`
                    : '暂无最弱标的。'}
                </div>
                <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {(group.symbols || []).slice(0, 6).map((symbol) => (
                    <Tag key={`${group.id}-${symbol}`}>{`${symbol} ${Number(group.weightMap?.[symbol] || 0).toFixed(2)}x`}</Tag>
                  ))}
                </div>
              </div>
            )) : (
              <Empty description="还没有组合。可以把当前关注的标的组织成研究篮子。" />
            )}
          </div>
        </Card>
      </div>

      <div className="app-page-section-block">
        <div className="app-page-section-kicker">复盘与诊断</div>
        <RealtimeReviewSummaryCard
          REVIEW_SCOPE_OPTIONS={REVIEW_SCOPE_OPTIONS}
          copyTextToClipboard={copyTextToClipboard}
          exportReviewSnapshots={exportReviewSnapshots}
          filteredReviewSnapshots={filteredReviewSnapshots}
          formatQuoteTime={formatQuoteTime}
          formatReviewSnapshotMarkdown={(snapshot) => formatReviewSnapshotMarkdown(snapshot, getSnapshotOutcomeMeta)}
          formatReviewSummaryMarkdown={formatReviewSummaryMarkdown}
          getCategoryLabel={getCategoryLabel}
          getSnapshotOutcomeMeta={getSnapshotOutcomeMeta}
          isExpanded={isReviewExpanded}
          latestSnapshots={latestSnapshots}
          onOpenReviewSummaryShareCard={openReviewSummaryShareCard}
          onOpenSnapshotFocus={openSnapshotFocus}
          onOpenSnapshotShareCard={openSnapshotShareCard}
          onRestoreSnapshot={restoreSnapshot}
          onSetReviewScope={setReviewScope}
          onToggleExpanded={() => setIsReviewExpanded(prev => !prev)}
          onTriggerSnapshotImport={triggerSnapshotImport}
          resolvedSnapshotCount={resolvedSnapshotCount}
          reviewAttribution={reviewAttribution}
          reviewOutcomeSummary={reviewOutcomeSummary}
          reviewScope={reviewScope}
          reviewScopeLabel={reviewScopeLabel}
          validationRate={validationRate}
        />

        <input
          ref={snapshotImportInputRef}
          type="file"
          accept="application/json"
          style={{ display: 'none' }}
          onChange={handleImportReviewSnapshots}
        />

        {diagnosticsEnabled && (
          <RealtimeDiagnosticsCard
            diagnosticsCache={diagnosticsCache}
            diagnosticsFetch={diagnosticsFetch}
            diagnosticsLastLoadedAt={diagnosticsLastLoadedAt}
            diagnosticsLoading={diagnosticsLoading}
            diagnosticsQuality={diagnosticsQuality}
            diagnosticsSummary={diagnosticsSummary}
            formatQuoteTime={formatQuoteTime}
            formatTransportDecision={formatTransportDecision}
            isExpanded={isDiagnosticsExpanded}
            onDisable={() => setDiagnosticsEnabled(false)}
            onRefresh={refreshDiagnostics}
            onToggleExpanded={() => setIsDiagnosticsExpanded(prev => !prev)}
            transportDecisions={transportDecisions}
            weakestFields={weakestFields}
            weakestSymbols={weakestSymbols}
          />
        )}

        {!diagnosticsEnabled && (
          <Card
            className="realtime-diagnostics-launcher"
            style={{
              borderRadius: 20,
              border: '1px dashed color-mix(in srgb, var(--accent-primary) 26%, var(--border-color) 74%)',
              background: 'color-mix(in srgb, var(--bg-secondary) 88%, white 12%)',
              boxShadow: '0 10px 24px rgba(15, 23, 42, 0.04)',
            }}
          >
            <div className="realtime-board-head" style={{ marginBottom: 0 }}>
              <div>
                <div className="realtime-block-title" style={{ fontSize: 16 }}>开发诊断</div>
                <div className="realtime-block-subtitle">
                  当前已隐藏调试信息，只有在需要排查链路、缓存或字段覆盖时再展开。
                </div>
              </div>
              <Button size="small" onClick={() => setDiagnosticsEnabled(true)}>
                显示诊断
              </Button>
            </div>
          </Card>
        )}
      </div>

      <Drawer
        title="价格提醒"
        placement="right"
        width={720}
        onClose={handleCloseAlerts}
        open={isAlertsDrawerVisible}
      >
        <Suspense fallback={null}>
          <PriceAlerts
            embedded
            prefillSymbol={alertPrefillSymbol}
            prefillDraft={alertPrefillDraft}
            composerSignal={alertComposerSignal}
            initialAlertHitHistory={alertHitHistory}
            liveQuotes={quotes}
            onAlertHitHistoryChange={setAlertHitHistory}
            onAlertTriggered={handleAlertTriggered}
          />
        </Suspense>
      </Drawer>

      <RealtimeSnapshotDrawer
        filteredReviewSnapshots={filteredReviewSnapshots}
        formatQuoteTime={formatQuoteTime}
        formatReviewSnapshotMarkdown={(snapshot) => formatReviewSnapshotMarkdown(snapshot, getSnapshotOutcomeMeta)}
        getCategoryLabel={getCategoryLabel}
        getSnapshotOutcomeMeta={getSnapshotOutcomeMeta}
        isOpen={isSnapshotDrawerVisible}
        onClose={() => setIsSnapshotDrawerVisible(false)}
        onCopyText={copyTextToClipboard}
        onOpenSnapshotFocus={openSnapshotFocus}
        onOpenSnapshotShareCard={openSnapshotShareCard}
        onRestoreSnapshot={restoreSnapshot}
        onUpdateReviewSnapshot={updateReviewSnapshot}
      />

      <Suspense fallback={null}>
        <TradePanel
          visible={isTradeModalVisible}
          defaultSymbol={selectedSymbol}
          planDraft={tradePlanDraft}
          onCreateAlertFromPlan={handleCreateAlertFromTradePlan}
          onClose={handleCloseTrade}
          onSuccess={() => {
            messageApi.success('交易已记录');
          }}
        />
      </Suspense>

      {/* 详情模态框 */}
      <Suspense fallback={null}>
        <RealtimeStockDetailModal
          open={isDetailModalVisible}
          onCancel={handleCloseDetail}
          onQuickTrade={handleOpenTradeFromDetail}
          symbol={detailSymbol}
          quote={detailSymbol ? quotes[detailSymbol] || null : null}
          quoteMap={quotes}
          eventTimeline={detailEventTimeline}
          compareCandidates={detailCompareCandidates}
          compareTimelineMap={detailCompareTimelineMap}
        />
      </Suspense>

      <style>{`
        .realtime-panel-shell {
          padding: 0;
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          align-content: start;
          gap: 18px;
          background:
            radial-gradient(circle at top left, color-mix(in srgb, var(--accent-primary) 10%, transparent 90%), transparent 34%),
            radial-gradient(circle at top right, color-mix(in srgb, var(--accent-secondary) 12%, transparent 88%), transparent 30%);
        }

        .realtime-panel-shell > * {
          min-width: 0;
        }

        .realtime-panel-shell .app-page-section-block {
          min-width: 0;
        }

        .realtime-hero {
          display: grid;
          grid-template-columns: minmax(0, 1.55fr) minmax(300px, 0.88fr);
          gap: 16px;
          padding: 18px 20px;
          background:
            linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 12%, var(--bg-secondary) 88%) 0%, color-mix(in srgb, var(--accent-secondary) 10%, var(--bg-secondary) 90%) 100%);
        }

        .realtime-hero__main,
        .realtime-hero__sidecar {
          min-width: 0;
        }

        .realtime-hero__main {
          display: grid;
          gap: 12px;
          align-content: start;
        }

        .realtime-hero__statusbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          flex-wrap: wrap;
        }

        .realtime-hero__eyebrow {
          font-size: 11px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--text-secondary);
          font-weight: 700;
        }

        .realtime-hero__status-meta {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 10px;
          flex-wrap: wrap;
        }

        .realtime-hero__title-row {
          display: flex;
          align-items: flex-start;
          justify-content: flex-start;
          gap: 12px;
        }

        .realtime-hero__headline {
          min-width: 0;
        }

        .realtime-hero__subtitle {
          margin-top: 8px;
          max-width: 560px;
          color: var(--text-secondary);
          line-height: 1.55;
          font-size: 12px;
        }

        .realtime-hero__meta {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .realtime-hero__chip {
          padding: 6px 10px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, var(--border-color) 84%);
          font-size: 11px;
          color: var(--text-secondary);
          white-space: nowrap;
        }

        .realtime-hero__focus-pill {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 8px 12px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-secondary) 84%, white 16%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 18%, var(--border-color) 82%);
          min-width: 0;
          max-width: min(100%, 420px);
        }

        .realtime-hero__focus-label {
          font-size: 10px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
          white-space: nowrap;
        }

        .realtime-hero__focus-text {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .realtime-hero__metric-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
        }

        .realtime-hero__metric {
          padding: 11px 12px;
          border-radius: 16px;
          background: color-mix(in srgb, var(--bg-secondary) 88%, white 12%);
          border: 1px solid color-mix(in srgb, var(--border-color) 78%, white 22%);
        }

        .realtime-hero__metric-label {
          font-size: 11px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-hero__metric-value {
          margin-top: 8px;
          font-size: 21px;
          line-height: 1.05;
          font-weight: 800;
          letter-spacing: -0.03em;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .realtime-hero__metric-detail {
          margin-top: 4px;
          font-size: 11px;
          line-height: 1.4;
          color: var(--text-secondary);
        }

        .realtime-hero__telemetry {
          display: flex;
          flex-wrap: wrap;
          gap: 6px 10px;
          color: var(--text-secondary);
          font-size: 11px;
          line-height: 1.5;
        }

        .realtime-hero__telemetry span {
          padding: 4px 0;
          white-space: nowrap;
        }

        .realtime-hero__sidecar {
          display: grid;
          gap: 8px;
          align-content: start;
          padding: 12px;
          border-radius: 18px;
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
          border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, var(--border-color) 84%);
        }

        .realtime-hero__action-row {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
        }

        .realtime-hero__refresh {
          min-height: 42px;
          font-weight: 700;
        }

        .realtime-hero__secondary-button {
          min-height: 38px;
        }

        .realtime-hero__utility-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
        }

        .realtime-hero__toggle-pill {
          display: inline-flex;
          align-items: center;
          gap: 12px;
          padding: 10px 12px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-primary) 92%, white 8%);
          border: 1px solid var(--border-color);
        }

        .realtime-hero__utility-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 8px;
          flex-wrap: wrap;
        }

        .realtime-hero__signal-stack {
          display: grid;
          gap: 8px;
        }

        .realtime-hero__signal-card {
          padding: 9px 11px;
          border-radius: 14px;
        }

        .realtime-hero__signal-card-title {
          font-weight: 700;
          font-size: 13px;
          line-height: 1.4;
        }

        .realtime-hero__signal-pill-row {
          display: flex;
          align-items: center;
          gap: 6px;
          flex-wrap: wrap;
        }

        .realtime-hero__signal-pill {
          display: inline-flex;
          align-items: center;
          padding: 4px 8px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-primary) 86%, white 14%);
          border: 1px solid color-mix(in srgb, var(--border-color) 76%, white 24%);
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }

        .realtime-hero__signal-pill--accent {
          background: color-mix(in srgb, var(--accent-primary) 16%, var(--bg-primary) 84%);
          border-color: color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%);
        }

        .realtime-hero__signal-card-detail {
          margin-top: 4px;
          font-size: 12px;
          line-height: 1.5;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .realtime-hero__signal-card-detail--muted {
          font-size: 11px;
          color: var(--text-secondary);
        }

        .realtime-overview-grid {
          display: grid;
          grid-template-columns: minmax(360px, 1.2fr) minmax(300px, 0.9fr);
          gap: 18px;
        }

        .realtime-search-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 14px;
          margin-top: 16px;
        }

        .realtime-search-panel {
          padding: 16px;
          border-radius: 18px;
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
          border: 1px solid color-mix(in srgb, var(--border-color) 74%, white 26%);
        }

        .realtime-search-panel__title {
          font-size: 14px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-search-panel__hint {
          margin-top: 6px;
          font-size: 12px;
          line-height: 1.6;
          color: var(--text-secondary);
        }

        .realtime-overview-stats {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
          margin-top: 16px;
        }

        .realtime-overview-stats--compact {
          grid-template-columns: repeat(3, minmax(0, 1fr));
          margin-top: 12px;
        }

        .realtime-overview-brief {
          margin-top: 14px;
          padding: 14px 16px;
          border-radius: 18px;
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
          border: 1px solid color-mix(in srgb, var(--border-color) 76%, white 24%);
        }

        .realtime-overview-brief__label {
          font-size: 11px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-overview-brief__value {
          margin-top: 8px;
          font-size: 24px;
          line-height: 1.1;
          font-weight: 800;
          color: var(--text-primary);
        }

        .realtime-overview-brief__detail {
          margin-top: 8px;
          font-size: 12px;
          line-height: 1.6;
          color: var(--text-secondary);
        }

        .realtime-overview-stat {
          padding: 14px 16px;
          border-radius: 18px;
          border: 1px solid color-mix(in srgb, var(--border-color) 76%, white 24%);
          background: color-mix(in srgb, var(--bg-secondary) 90%, white 10%);
        }

        .realtime-overview-stat--primary {
          background: linear-gradient(135deg, rgba(14, 165, 233, 0.14), rgba(56, 189, 248, 0.05));
        }

        .realtime-overview-stat--positive {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.14), rgba(34, 197, 94, 0.05));
        }

        .realtime-overview-stat--negative {
          background: linear-gradient(135deg, rgba(239, 68, 68, 0.14), rgba(239, 68, 68, 0.05));
        }

        .realtime-overview-stat--focus {
          background: linear-gradient(135deg, rgba(168, 85, 247, 0.14), rgba(168, 85, 247, 0.05));
        }

        .realtime-overview-stat--neutral {
          grid-column: 1 / -1;
        }

        .realtime-overview-stat__label {
          font-size: 11px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-overview-stat__value {
          margin-top: 10px;
          font-size: 26px;
          line-height: 1.05;
          font-weight: 800;
          letter-spacing: -0.03em;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .realtime-overview-stat__detail {
          margin-top: 8px;
          font-size: 12px;
          line-height: 1.55;
          color: var(--text-secondary);
        }

        .realtime-block-title {
          font-size: 18px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-block-subtitle {
          margin-top: 6px;
          color: var(--text-secondary);
          font-size: 13px;
          line-height: 1.65;
        }

        .realtime-board-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 18px;
          flex-wrap: wrap;
        }

        .realtime-board-headline {
          display: grid;
          gap: 10px;
          min-width: 0;
        }

        .realtime-board-badges {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }

        .realtime-board-controls {
          display: grid;
          gap: 12px;
          justify-items: end;
          min-width: min(100%, 520px);
        }

        .realtime-board-control-group {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 10px;
          flex-wrap: wrap;
        }

        .realtime-board-control-label {
          font-size: 12px;
          white-space: nowrap;
        }

        .realtime-board-control-group .ant-btn {
          border-radius: 999px;
        }

        .realtime-board-summary {
          display: inline-flex;
          align-items: baseline;
          gap: 10px;
          padding: 10px 14px;
          border-radius: 999px;
          background: color-mix(in srgb, var(--bg-primary) 88%, white 12%);
          border: 1px solid var(--border-color);
          color: var(--text-secondary);
        }

        .realtime-board-summary strong {
          font-size: 22px;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .market-tabs .ant-tabs-nav {
          margin-bottom: 20px;
        }

        .market-tabs .ant-tabs-tab {
          border-radius: 999px !important;
          padding-inline: 16px !important;
        }

        .realtime-quote-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 16px;
          align-items: stretch;
        }

        .realtime-quote-grid--list {
          grid-template-columns: 1fr;
        }

        .realtime-quote-card__surface {
          min-height: 100%;
          display: grid;
          gap: 16px;
        }

        .realtime-quote-card__header,
        .realtime-quote-card__price-row,
        .realtime-quote-card__footer {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }

        .realtime-quote-card__tags {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
          flex-wrap: wrap;
        }

        .realtime-quote-card__name {
          margin-bottom: 4px;
        }

        .realtime-quote-card__sparkline {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          margin-top: 10px;
          padding: 8px 10px;
          border-radius: 14px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--border-color) 78%, white 22%);
          color: var(--text-secondary);
          font-size: 11px;
          line-height: 1.4;
        }

        .realtime-quote-card__sparkline svg {
          display: block;
          flex: none;
        }

        .realtime-quote-card__source {
          text-align: right;
          min-width: 76px;
          padding: 10px 12px;
          border-radius: 16px;
          background: color-mix(in srgb, var(--bg-secondary) 82%, white 18%);
          border: 1px solid color-mix(in srgb, var(--border-color) 80%, white 20%);
          color: var(--text-secondary);
          white-space: nowrap;
        }

        .realtime-quote-card__price {
          font-size: 32px;
          line-height: 1;
          font-weight: 800;
          color: var(--text-primary);
          letter-spacing: -0.03em;
        }

        .realtime-quote-card__delta {
          margin-top: 8px;
          font-size: 14px;
          font-weight: 700;
        }

        .realtime-quote-card__focus {
          min-width: 120px;
          text-align: right;
          padding: 10px 12px;
          border-radius: 16px;
          background: rgba(15, 23, 42, 0.04);
        }

        .realtime-quote-card__focus-label {
          font-size: 11px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-quote-card__focus-value {
          margin-top: 6px;
          font-size: 13px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .realtime-quote-card__metrics {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
        }

        .realtime-quote-card__metric {
          padding: 12px;
          border-radius: 16px;
          background: color-mix(in srgb, var(--bg-secondary) 80%, white 20%);
          border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent 30%);
          display: grid;
          gap: 8px;
        }

        .realtime-quote-card__metric span {
          font-size: 11px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--text-secondary);
        }

        .realtime-quote-card__metric strong {
          font-size: 13px;
          line-height: 1.45;
          color: var(--text-primary);
          word-break: break-word;
        }

        .realtime-quote-card__footer {
          align-items: center;
          padding-top: 4px;
        }

        .realtime-quote-card--list .realtime-quote-card__surface--list {
          grid-template-columns: minmax(0, 1.45fr) minmax(180px, 0.7fr) minmax(280px, 0.95fr) auto;
          align-items: center;
        }

        .realtime-quote-card--list .realtime-quote-card__header,
        .realtime-quote-card--list .realtime-quote-card__price-row,
        .realtime-quote-card--list .realtime-quote-card__footer {
          align-items: center;
        }

        .realtime-quote-card--list .realtime-quote-card__price-row {
          justify-content: flex-start;
        }

        .realtime-quote-card--list .realtime-quote-card__price {
          font-size: 26px;
        }

        .realtime-quote-card--list .realtime-quote-card__focus {
          min-width: auto;
          text-align: left;
        }

        .realtime-quote-card--list .realtime-quote-card__footer {
          justify-content: flex-end;
        }

        @media (max-width: 1320px) {
          .realtime-hero__metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .realtime-overview-stats--compact {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 1180px) {
          .realtime-overview-grid,
          .realtime-hero {
            grid-template-columns: 1fr;
          }

          .realtime-search-grid,
          .realtime-hero__metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .realtime-board-controls {
            justify-items: start;
            min-width: 100%;
          }

          .realtime-board-control-group {
            justify-content: flex-start;
          }

          .realtime-quote-card--list .realtime-quote-card__surface--list {
            grid-template-columns: 1fr 1fr;
          }

          .realtime-hero__status-meta {
            justify-content: flex-start;
          }
        }

        @media (max-width: 900px) {
          .realtime-overview-stats,
          .realtime-quote-card__metrics {
            grid-template-columns: 1fr 1fr;
          }

          .realtime-overview-stat--neutral {
            grid-column: auto;
          }

          .realtime-quote-card--list .realtime-quote-card__surface--list {
            grid-template-columns: 1fr;
          }

          .realtime-overview-stats--compact {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 640px) {
          .realtime-panel-shell {
            padding: 12px;
          }

          .realtime-hero {
            gap: 12px;
            padding: 14px;
          }

          .realtime-hero__main {
            gap: 10px;
          }

          .realtime-hero__subtitle {
            display: none;
          }

          .realtime-hero__title-row,
          .realtime-hero__utility-row,
          .realtime-board-control-group {
            align-items: flex-start;
          }

          .realtime-hero__status-meta,
          .realtime-hero__utility-actions {
            width: 100%;
            justify-content: flex-start;
          }

          .realtime-hero__meta {
            display: grid;
            grid-auto-flow: column;
            grid-auto-columns: max-content;
            overflow-x: auto;
            overscroll-behavior-x: contain;
            padding-bottom: 2px;
            scrollbar-width: none;
          }

          .realtime-hero__meta::-webkit-scrollbar,
          .realtime-hero__metric-grid::-webkit-scrollbar {
            display: none;
          }

          .realtime-hero__focus-pill,
          .realtime-hero__utility-actions .ant-btn {
            width: 100%;
          }

          .realtime-hero__focus-pill {
            gap: 8px;
            padding: 6px 10px;
          }

          .realtime-hero__focus-label {
            font-size: 9px;
          }

          .realtime-hero__focus-text {
            font-size: 11px;
          }

          .realtime-hero__chip {
            padding: 5px 9px;
            font-size: 10px;
          }

          .realtime-hero__action-row,
          .realtime-hero__utility-actions {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            display: grid;
          }

          .realtime-hero__metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .realtime-hero__metric {
            padding: 10px 11px;
          }

          .realtime-hero__metric-value {
            margin-top: 6px;
            font-size: 19px;
          }

          .realtime-hero__metric-detail {
            display: none;
          }

          .realtime-hero__sidecar {
            gap: 6px;
            padding: 10px;
          }

          .realtime-hero__utility-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 8px;
            width: 100%;
          }

          .realtime-hero__toggle-pill {
            width: 100%;
            justify-content: space-between;
            padding: 8px 10px;
          }

          .realtime-hero__refresh {
            min-height: 38px;
          }

          .realtime-hero__secondary-button,
          .realtime-hero__utility-actions .ant-btn {
            min-height: 34px;
          }

          .realtime-hero__signal-card {
            padding: 8px 10px;
          }

          .realtime-hero__utility-actions .ant-btn {
            justify-content: center;
          }

          .realtime-quote-grid,
          .realtime-overview-stats,
          .realtime-quote-card__metrics {
            grid-template-columns: 1fr;
          }

          .realtime-quote-card__header,
          .realtime-quote-card__price-row,
          .realtime-quote-card__footer {
            flex-direction: column;
            align-items: stretch;
          }

          .realtime-quote-card__source,
          .realtime-quote-card__focus {
            text-align: left;
          }

          .realtime-hero__telemetry span {
            white-space: normal;
          }

          .realtime-hero__signal-card-detail {
            -webkit-line-clamp: 1;
          }

          .realtime-hero__signal-card-detail--muted {
            display: none;
          }
        }

        @media (max-width: 360px) {
          .realtime-hero__action-row,
          .realtime-hero__utility-actions {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
};

export default RealTimePanel;
