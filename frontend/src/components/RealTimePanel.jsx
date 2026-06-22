import { useState, useEffect, useCallback, useMemo, useRef, Suspense } from 'react';
import {
  Card,
  Tag,
  Button,
  Space,
  Typography,
  Badge,
  Switch,
  Drawer,
} from 'antd';
import {
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
} from '@ant-design/icons';
import RealtimeQuoteBoard from './realtime/RealtimeQuoteBoard';
import RealtimeAnomalyRadar from './realtime/RealtimeAnomalyRadar';
import RealtimeAlertHistoryCard from './realtime/RealtimeAlertHistoryCard';
import RealtimeReviewSummaryCard from './realtime/RealtimeReviewSummaryCard';
import RealtimeDiagnosticsCard from './realtime/RealtimeDiagnosticsCard';
import RealtimeSnapshotDrawer from './realtime/RealtimeSnapshotDrawer';
import RealtimeWatchGroupMonitor from './realtime/RealtimeWatchGroupMonitor';
import RealtimeWorkbenchTools from './realtime/RealtimeWorkbenchTools';
import REALTIME_PANEL_STYLES from './realtime/realtimePanelStyles';
import { STOCK_DATABASE } from '../constants/stocks';
import { useRealtimeDiagnostics } from '../hooks/useRealtimeDiagnostics';
import { useRealtimeDerivedState, formatQuoteTime } from '../hooks/useRealtimeDerivedState';
import { useRealtimeFeed } from '../hooks/useRealtimeFeed';
import { useRealtimeMetadata } from '../hooks/useRealtimeMetadata';
import { useRealtimePreferences } from '../hooks/useRealtimePreferences';
import { useRealtimeReviewActions } from '../hooks/useRealtimeReviewActions';
import {
  buildAlertDraftFromAnomaly,
  buildRealtimeAnomalyFeed,
} from '../utils/realtimeSignals';
import {
  useRealtimeJournal,
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
  formatReviewSnapshotMarkdown,
  formatReviewSummaryMarkdown,
} from '../utils/realtimeShareTemplates';
import lazyWithRetry from '../utils/lazyWithRetry';
import { useSafeMessageApi } from '../utils/messageApi';
import {
    CATEGORY_OPTIONS,
    CATEGORY_THEMES,
    DEFAULT_SUBSCRIBED_SYMBOLS,
    DETAIL_COMPARE_CANDIDATE_LIMIT,
    DETAIL_PREFETCH_SYMBOL_LIMIT,
    EMPTY_NUMERIC_TEXT,
    QUOTE_SORT_OPTIONS,
    REALTIME_DIAGNOSTICS_STORAGE_KEY,
    REVIEW_SCOPE_OPTIONS,
} from '../utils/realtimePanelConstants';
import {
    buildRealtimeDetailTimeline,
    filterReviewSnapshots,
    formatCompactCurrency,
    getSnapshotOutcomeMeta,
    loadDiagnosticsEnabled,
    normalizeGroupWeights,
} from '../utils/realtimePanelHelpers';

const { Text } = Typography;

// Constants / pure helpers / loadDiagnosticsEnabled / timeline builders
// extracted so the host component focuses on hook orchestration. See:
//   - utils/realtimePanelConstants.js
//   - utils/realtimePanelHelpers.js

const RealtimeStockDetailModal = lazyWithRetry(() => import('./RealtimeStockDetailModal'));
const PriceAlerts = lazyWithRetry(() => import('./PriceAlerts'));

const RealTimePanel = ({ openAlertsSignal = null }) => {
  const messageApi = useSafeMessageApi();
  const [searchSymbol, setSearchSymbol] = useState('');
  const [globalJumpQuery, setGlobalJumpQuery] = useState('');
  const [isAlertsDrawerVisible, setIsAlertsDrawerVisible] = useState(false);
  const [alertPrefillSymbol, setAlertPrefillSymbol] = useState('');
  const [alertPrefillDraft, setAlertPrefillDraft] = useState(null);
  const [alertComposerSignal, setAlertComposerSignal] = useState(0);

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
    ensureQuotesForSymbols,
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
    marketMood,
    marketMoodError,
    marketMoodLoading,
    quotes,
    reconnectAttempts,
    refreshMarketMood,
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

  const getDetailCompareSymbols = useCallback((focusSymbol, category = '', maxItems = DETAIL_COMPARE_CANDIDATE_LIMIT) => {
    const targetCategory = category || resolveSymbolCategory(focusSymbol);
    const normalizedFocusSymbol = String(focusSymbol || '').trim().toUpperCase();
    const orderedSymbols = getSymbolsByCategory(targetCategory)
      .filter(Boolean)
      .map((symbol) => String(symbol).trim().toUpperCase())
      .filter((symbol, index, list) => list.indexOf(symbol) === index)
      .sort((left, right) => {
        if (left === normalizedFocusSymbol) {
          return -1;
        }
        if (right === normalizedFocusSymbol) {
          return 1;
        }

        const leftHasQuote = Boolean(quotes[left]);
        const rightHasQuote = Boolean(quotes[right]);
        if (leftHasQuote !== rightHasQuote) {
          return leftHasQuote ? -1 : 1;
        }

        return Math.abs(Number(quotes[right]?.change_percent || 0)) - Math.abs(Number(quotes[left]?.change_percent || 0));
      });

    if (normalizedFocusSymbol && !orderedSymbols.includes(normalizedFocusSymbol)) {
      orderedSymbols.unshift(normalizedFocusSymbol);
    }

    return orderedSymbols.slice(0, maxItems);
  }, [getSymbolsByCategory, quotes, resolveSymbolCategory]);

  const openDetailForSymbol = useCallback((symbol, options = {}) => {
    if (!symbol) {
      return;
    }

    const detailPrefetchSymbols = getDetailCompareSymbols(
      symbol,
      options.category || resolveSymbolCategory(symbol),
      options.prefetchLimit || DETAIL_PREFETCH_SYMBOL_LIMIT,
    );
    ensureQuotesForSymbols(detailPrefetchSymbols, {
      note: options.note || 'detail open',
      snapshotReason: options.snapshotReason || 'detail_snapshot',
      fallbackReason: options.fallbackReason || 'detail_rest',
      fallbackNote: options.fallbackNote || 'detail open fallback',
    });
    setDetailSymbol(symbol);
    setIsDetailModalVisible(true);
    if (options.closeSnapshotDrawer) {
      setIsSnapshotDrawerVisible(false);
    }
  }, [ensureQuotesForSymbols, getDetailCompareSymbols, resolveSymbolCategory]);

  const handleShowDetail = useCallback((symbol) => {
    openDetailForSymbol(symbol, {
      note: 'detail open',
      snapshotReason: 'detail_snapshot',
      fallbackReason: 'detail_rest',
      fallbackNote: 'detail open fallback',
    });
  }, [openDetailForSymbol]);

  const handleNavigateDetailSymbol = useCallback((symbol) => {
    openDetailForSymbol(symbol, {
      note: 'detail compare switch',
      snapshotReason: 'detail_snapshot',
      fallbackReason: 'detail_rest',
      fallbackNote: 'detail compare switch fallback',
    });
  }, [openDetailForSymbol]);

  const handleCloseDetail = useCallback(() => {
    setIsDetailModalVisible(false);
    setDetailSymbol(null);
  }, []);

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
      rest_fallback: '备用刷新补齐',
      warmup_snapshot: '首屏快照',
      manual_snapshot: '手动快照',
      manual_rest: '手动备用刷新',
      detail_snapshot: '详情快照',
      detail_rest: '详情备用刷新',
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
        detail: marketAgeMs !== null ? `页面接收${receivedLabel}` : null,
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
        detail: marketAgeMs !== null ? `页面接收${receivedLabel}` : null,
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
      detail: marketAgeMs !== null ? `页面接收${receivedLabel}` : null,
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
    marketMood,
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
  const detailCompareCandidates = getDetailCompareSymbols(
    detailSymbol,
    detailSymbol ? resolveSymbolCategory(detailSymbol) : activeTab,
    DETAIL_COMPARE_CANDIDATE_LIMIT,
  )
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

  const {
    snapshotImportInputRef,
    saveReviewSnapshot,
    restoreSnapshot,
    openSnapshotFocus,
    copyTextToClipboard,
    openSnapshotShareCard,
    openReviewSummaryShareCard,
    exportReviewSnapshots,
    triggerSnapshotImport,
    handleImportReviewSnapshots,
  } = useRealtimeReviewActions({
    activeTab,
    anomalyFeed,
    appendTimelineEvent,
    currentTabQuotes,
    currentTabSymbols,
    filteredReviewSnapshots,
    freshnessSummary,
    getCategoryLabel,
    getDisplayName,
    messageApi,
    openDetailForSymbol,
    quotes,
    reviewAttribution,
    reviewOutcomeSummary,
    reviewScopeLabel,
    reviewSnapshots,
    setActiveTab,
    setIsSnapshotDrawerVisible,
    setReviewSnapshots,
    setTimelineEvents,
    spotlightSymbol,
    timelineEvents,
    transportModeLabel,
    validationRate,
  });

  const tabs = [
    { key: 'index', label: '指数', icon: <BarChartOutlined /> },
    { key: 'us', label: '美股', icon: <StockOutlined /> },
    { key: 'cn', label: 'A股', icon: <StockOutlined /> },
    { key: 'etf', label: 'ETF', icon: <FundOutlined /> },
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
  const overviewSummary = marketSentiment.source === 'tushare'
    ? `Tushare 盘后${marketSentiment.asOf ? ` ${marketSentiment.asOf}` : ''}：${marketSentiment.detail}`
    : `当前分组 ${getCategoryLabel(activeTab)} 已加载 ${currentTabSymbols.length} 个标的；全局盘面 ${marketSentiment.label}，${marketSentiment.detail}`;

  return (
    <div className="realtime-panel-shell app-page-shell app-page-shell--wide realtime-page-shell">
      <div className="app-page-section-block">
        <div className="app-page-section-kicker">实时指挥席</div>
        <Card
          className="realtime-hero-card realtime-hero-card--compact"
          style={{
            borderRadius: 8,
            overflow: 'hidden',
            border: '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)',
            boxShadow: '0 24px 60px rgba(15, 23, 42, 0.10)',
          }}
          styles={{ body: { padding: 0 } }}
        >
          <div className="realtime-hero">
            <div className="realtime-hero__main">
              <div className="realtime-hero__statusbar">
                <div className="realtime-hero__eyebrow">实时雷达</div>
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
                <div className="realtime-hero__chip realtime-hero__chip--category">当前分组：{getCategoryLabel(activeTab)}</div>
                <div className="realtime-hero__chip realtime-hero__chip--transport">行情更新：{transportModeLabel}</div>
                <div className="realtime-hero__chip realtime-hero__chip--auto">自动更新：{isAutoUpdate ? '开启' : '暂停'}</div>
                <div className="realtime-hero__chip realtime-hero__chip--time">行情时间：{lastMarketUpdateLabel}</div>
                {reconnectAttempts > 0 && <div className="realtime-hero__chip realtime-hero__chip--reconnect">重连 {reconnectAttempts}</div>}
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

            <div className="realtime-hero__sidecar realtime-hero__sidecar--desktop-toolbar">
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
          formatQuoteTime={formatQuoteTime}
          getDisplayName={getDisplayName}
          handleOpenAlerts={handleOpenAlerts}
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

      <RealtimeWorkbenchTools
        autoCompleteOptions={autoCompleteOptions}
        searchSymbol={searchSymbol}
        onSearch={handleSearch}
        onSelectSearch={handleSelect}
        onAddSymbol={addSymbol}
        globalJumpOptions={globalJumpOptions}
        globalJumpQuery={globalJumpQuery}
        onGlobalJumpSearch={handleGlobalJumpSearch}
        onGlobalJumpSelect={handleGlobalJumpSelect}
        marketSentiment={marketSentiment}
        marketMoodLoading={marketMoodLoading}
        marketMoodError={marketMoodError}
        onRefreshMarketMood={refreshMarketMood}
        overviewSummary={overviewSummary}
        overviewPrimaryStats={overviewPrimaryStats}
      />

      <RealtimeWatchGroupMonitor
        watchGroupName={watchGroupName}
        onWatchGroupNameChange={setWatchGroupName}
        watchGroupSymbols={watchGroupSymbols}
        onWatchGroupSymbolsChange={setWatchGroupSymbols}
        watchGroupCapital={watchGroupCapital}
        onWatchGroupCapitalChange={setWatchGroupCapital}
        watchGroupWeights={watchGroupWeights}
        onWatchGroupWeightsChange={setWatchGroupWeights}
        watchGroupSummaries={watchGroupSummaries}
        onAddWatchGroup={addWatchGroup}
        onRemoveWatchGroup={removeWatchGroup}
        formatPercent={formatPercent}
        formatCompactCurrency={formatCompactCurrency}
        getDisplayName={getDisplayName}
      />

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

      {/* 详情模态框 */}
      <Suspense fallback={null}>
        <RealtimeStockDetailModal
          open={isDetailModalVisible}
          onCancel={handleCloseDetail}
          onNavigateSymbol={handleNavigateDetailSymbol}
          symbol={detailSymbol}
          quote={detailSymbol ? quotes[detailSymbol] || null : null}
          quoteMap={quotes}
          eventTimeline={detailEventTimeline}
          compareCandidates={detailCompareCandidates}
          compareTimelineMap={detailCompareTimelineMap}
        />
      </Suspense>

      <style>{REALTIME_PANEL_STYLES}</style>
    </div>
  );
};

export default RealTimePanel;
