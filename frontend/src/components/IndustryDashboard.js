import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import {
    Layout,
    Row,
    Col,
    Card,
    Tabs,
    Spin,
    Empty,
    Tag,
    Button,
    Select,
    Space,
    Statistic,
    Modal,
    Tooltip
} from 'antd';
import {
    FireOutlined,
    BranchesOutlined,
    ReloadOutlined,
    CrownOutlined
} from '@ant-design/icons';
import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    ReferenceLine,
    Tooltip as RechartsTooltip,
    ResponsiveContainer
} from 'recharts';
import IndustryHeatmap from './IndustryHeatmap';
import IndustryTrendPanel from './IndustryTrendPanel';
import LeaderStockPanel from './LeaderStockPanel';
import IndustryRotationChart from './IndustryRotationChart';
import ApiStatusIndicator from './ApiStatusIndicator';
import StockDetailModal from './StockDetailModal';
import MiniSparkline from './common/MiniSparkline';
import IndustryScoreRadarModal from './industry/IndustryScoreRadarModal';
import IndustrySavedViewsPanel from './industry/IndustrySavedViewsPanel';
import IndustryRankingPanel from './industry/IndustryRankingPanel';
import IndustryAlertsPanel from './industry/IndustryAlertsPanel';
import IndustryWatchlistPanel from './industry/IndustryWatchlistPanel';
import IndustryMarketSnapshotBar from './industry/IndustryMarketSnapshotBar';
import IndustryResearchFocusPanel from './industry/IndustryResearchFocusPanel';
import IndustryReplayPanel from './industry/IndustryReplayPanel';
import IndustryHeatmapStateBar from './industry/IndustryHeatmapStateBar';
import {
    getHotIndustries,
    getIndustryHeatmapHistory,
    getIndustryStocks,
    getIndustryClusters,
    getLeaderDetail
} from '../services/api';
import { useSafeMessageApi } from '../utils/messageApi';
import {
    INDUSTRY_ALERT_RECENCY_OPTIONS,
    INDUSTRY_ALERT_SUBSCRIPTION_STORAGE_KEY,
    INDUSTRY_ALERT_HISTORY_STORAGE_KEY,
    INDUSTRY_ALERT_BADGE_STORAGE_KEY,
    INDUSTRY_ALERT_BADGE_EVENT,
    INDUSTRY_ALERT_KIND_OPTIONS,
    INDUSTRY_ALERT_DESKTOP_STORAGE_KEY,
    INDUSTRY_WATCHLIST_STORAGE_KEY,
    INDUSTRY_SAVED_VIEWS_STORAGE_KEY,
    formatIndustryAlertMoneyFlow,
    getIndustryScoreTone,
    formatIndustryAlertSeenLabel,
    clampNumeric,
    getAlertSubscriptionBucket,
    pruneIndustryAlertHistory,
    getIndustryAlertSeverity,
    buildIndustryActionPosture,
} from './industry/industryShared';

const { Option } = Select;
const INDUSTRY_URL_DEFAULTS = {
    tab: 'heatmap',
    marketCapFilter: 'all',
    timeframe: 1,
    sizeMetric: 'market_cap',
    colorMetric: 'change_pct',
    displayCount: 30,
    searchTerm: '',
    rankType: 'gainers',
    sortBy: 'total_score',
    lookbackDays: 5,
    volatilityFilter: 'all',
    rankingMarketCapFilter: 'all',
};
const INDUSTRY_VALID_TABS = new Set(['heatmap', 'ranking', 'clusters', 'rotation']);
const INDUSTRY_VALID_FILTERS = new Set(['all', 'live', 'snapshot', 'proxy', 'estimated']);
const INDUSTRY_VALID_SIZE_METRICS = new Set(['market_cap', 'net_inflow', 'turnover']);
const INDUSTRY_VALID_COLOR_METRICS = new Set(['change_pct', 'net_inflow_ratio', 'turnover_rate', 'pe_ttm', 'pb']);
const INDUSTRY_VALID_RANK_TYPES = new Set(['gainers', 'losers']);
const INDUSTRY_VALID_SORTS = new Set(['change_pct', 'total_score', 'money_flow', 'industry_volatility']);
const INDUSTRY_VALID_VOLATILITY_FILTERS = new Set(['all', 'low', 'medium', 'high']);
const INDUSTRY_TIMEFRAME_LABELS = { 1: '1日', 5: '5日', 10: '10日', 20: '20日', 60: '60日' };
const INDUSTRY_SIZE_METRIC_LABELS = { market_cap: '按市值', net_inflow: '按净流入', turnover: '按成交额(估)' };
const INDUSTRY_COLOR_METRIC_LABELS = {
    change_pct: '看涨跌',
    net_inflow_ratio: '看净流入%',
    turnover_rate: '看换手率',
    pe_ttm: '看市盈率',
    pb: '看市净率',
};
const INDUSTRY_FILTER_LABELS = {
    live: '实时市值',
    snapshot: '快照市值',
    proxy: '代理市值',
    estimated: '估算市值',
};
const INDUSTRY_RANK_TYPE_LABELS = {
    gainers: '涨幅榜',
    losers: '跌幅榜',
};
const INDUSTRY_RANK_SORT_LABELS = {
    change_pct: '按涨跌幅',
    total_score: '按综合得分',
    money_flow: '按资金流向',
    industry_volatility: '按波动率',
};
const INDUSTRY_VOLATILITY_FILTER_LABELS = {
    all: '全部波动',
    low: '低波动',
    medium: '中波动',
    high: '高波动',
};
const INDUSTRY_RANKING_MARKET_CAP_FILTER_LABELS = {
    all: '全部市值来源',
    live: '实时市值',
    snapshot: '快照市值',
    proxy: '代理市值',
    estimated: '估算市值',
};
const PANEL_SURFACE = 'var(--bg-secondary)';
const PANEL_BORDER = '1px solid var(--border-color)';
const PANEL_SHADOW = '0 1px 2px rgba(0,0,0,0.03)';
const PANEL_MUTED = 'var(--text-muted)';
const TEXT_PRIMARY = 'var(--text-primary)';
const TEXT_SECONDARY = 'var(--text-secondary)';
const INDUSTRY_STOCK_FULL_POLL_ATTEMPTS = 30;
const INDUSTRY_STOCK_FULL_POLL_INTERVAL_MS = 900;
const MAX_WATCHLIST_INDUSTRIES = 12;
const MAX_HEATMAP_REPLAY_SNAPSHOTS = 10;
const INDUSTRY_REPLAY_STORAGE_KEY = 'industry_heatmap_replay_snapshots_v1';
const INDUSTRY_REPLAY_SELECTION_KEY = 'industry_heatmap_replay_selected_v1';
const HEATMAP_REPLAY_RETENTION_MS = 24 * 60 * 60 * 1000;
const HEATMAP_REPLAY_WINDOW_OPTIONS = [
    { value: '1h', label: '近1小时' },
    { value: '6h', label: '近6小时' },
    { value: '24h', label: '近24小时' },
    { value: 'all', label: '全部' },
];

const buildHeatmapReplaySnapshotId = (updateTime, timeframe) => (
    `heatmap:${timeframe || 'na'}:${updateTime || Date.now()}`
);

const formatReplaySnapshotTime = (value) => {
    if (!value) return '未知时间';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '未知时间';
    return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    });
};

const getReplayWindowMs = (windowKey) => {
    if (windowKey === '1h') return 60 * 60 * 1000;
    if (windowKey === '6h') return 6 * 60 * 60 * 1000;
    if (windowKey === '24h') return 24 * 60 * 60 * 1000;
    return Number.POSITIVE_INFINITY;
};

const formatReplayDelta = (value, digits = 2, suffix = '') => {
    if (!Number.isFinite(Number(value))) return '-';
    const numericValue = Number(value);
    return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(digits)}${suffix}`;
};

const formatReplayMetricPercent = (value, digits = 2) => {
    if (!Number.isFinite(Number(value))) return '-';
    return `${Number(value).toFixed(digits)}%`;
};

const formatReplayMetricMoney = (value) => {
    if (!Number.isFinite(Number(value))) return '-';
    return formatIndustryAlertMoneyFlow(Number(value));
};

const pruneReplaySnapshots = (snapshots = []) => {
    const now = Date.now();
    return (snapshots || [])
        .map((snapshot) => normalizeReplaySnapshot(snapshot))
        .filter((snapshot) => {
            if (!snapshot?.id || !snapshot?.data?.industries?.length) return false;
            const updateTimestamp = new Date(snapshot.updateTime || snapshot.capturedAt || now).getTime();
            if (Number.isNaN(updateTimestamp)) return false;
            return (now - updateTimestamp) <= HEATMAP_REPLAY_RETENTION_MS;
        })
        .slice(0, MAX_HEATMAP_REPLAY_SNAPSHOTS);
};

const normalizeReplaySnapshot = (snapshot) => {
    if (!snapshot) return null;
    if (snapshot.data?.industries?.length) {
        return snapshot;
    }
    if (!Array.isArray(snapshot.industries) || snapshot.industries.length === 0) {
        return null;
    }
    return {
        id: snapshot.id || buildHeatmapReplaySnapshotId(snapshot.updateTime || snapshot.update_time, snapshot.timeframe || snapshot.days),
        updateTime: snapshot.updateTime || snapshot.update_time,
        capturedAt: snapshot.capturedAt || snapshot.captured_at || snapshot.updateTime || snapshot.update_time,
        timeframe: snapshot.timeframe || snapshot.days || 5,
        sizeMetric: snapshot.sizeMetric || 'market_cap',
        colorMetric: snapshot.colorMetric || 'change_pct',
        displayCount: snapshot.displayCount ?? 30,
        searchTerm: snapshot.searchTerm || '',
        marketCapFilter: snapshot.marketCapFilter || 'all',
        data: {
            industries: snapshot.industries,
            max_value: snapshot.max_value ?? snapshot.maxValue ?? 0,
            min_value: snapshot.min_value ?? snapshot.minValue ?? 0,
            update_time: snapshot.updateTime || snapshot.update_time || snapshot.capturedAt || snapshot.captured_at,
        },
    };
};

const getIndustryStockScoreStage = (stocks = []) => {
    if (!Array.isArray(stocks) || stocks.length === 0) return null;
    if (stocks.some((stock) => stock?.scoreStage === 'full')) return 'full';
    if (stocks.some((stock) => stock?.scoreStage === 'quick')) return 'quick';
    return stocks.some((stock) => Number(stock?.total_score || 0) > 0) ? 'full' : 'quick';
};

const hasDisplayReadyIndustryStockDetails = (stocks = []) => {
    if (!Array.isArray(stocks) || stocks.length === 0) return false;

    const hasDetailValue = (value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
    const detailThreshold = Math.max(3, Math.ceil(stocks.length * 0.5));
    const detailedRows = stocks.filter((stock) => [stock?.market_cap, stock?.pe_ratio, stock?.change_pct]
        .some((value) => hasDetailValue(value)));
    if (detailedRows.length >= detailThreshold) {
        return true;
    }

    const scoredDetailRows = stocks.filter((stock) => Number(stock?.total_score || 0) > 0
        && [stock?.market_cap, stock?.pe_ratio, stock?.change_pct].some((value) => hasDetailValue(value)));

    return scoredDetailRows.length >= detailThreshold;
};

const waitForAbortableDelay = (signal, timeoutMs) => (
    new Promise((resolve, reject) => {
        if (signal?.aborted) {
            reject(new DOMException('Aborted', 'AbortError'));
            return;
        }
        const timer = window.setTimeout(() => {
            if (signal) {
                signal.removeEventListener('abort', onAbort);
            }
            resolve();
        }, timeoutMs);
        const onAbort = () => {
            window.clearTimeout(timer);
            if (signal) {
                signal.removeEventListener('abort', onAbort);
            }
            reject(new DOMException('Aborted', 'AbortError'));
        };
        if (signal) {
            signal.addEventListener('abort', onAbort, { once: true });
        }
    })
);

const getMarketCapBadgeMeta = (source) => {
    const normalized = String(source || 'unknown');
    if (normalized.startsWith('snapshot_')) {
        return { label: '快照', color: 'blue', filter: 'snapshot' };
    }
    if (normalized === 'sina_proxy_stock_sum') {
        return { label: '代理', color: 'cyan', filter: 'proxy' };
    }
    if (normalized === 'unknown' || normalized.startsWith('estimated') || normalized === 'constant_fallback') {
        return { label: '估算', color: 'gold', filter: 'estimated' };
    }
    return { label: '实时', color: 'green', filter: 'live' };
};

const readIndustryUrlState = () => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('industry_tab');
    const marketCapFilter = params.get('industry_market_cap_filter');
    const timeframeParam = params.get('industry_timeframe');
    const timeframe = timeframeParam == null ? NaN : Number(timeframeParam);
    const sizeMetric = params.get('industry_size_metric');
    const colorMetric = params.get('industry_color_metric');
    const displayCountParam = params.get('industry_display_count');
    const displayCount = displayCountParam == null ? NaN : Number(displayCountParam);
    const searchTerm = params.get('industry_search');
    const rankType = params.get('industry_rank_type');
    const sortBy = params.get('industry_rank_sort');
    const lookbackDaysParam = params.get('industry_rank_lookback');
    const lookbackDays = lookbackDaysParam == null ? NaN : Number(lookbackDaysParam);
    const volatilityFilter = params.get('industry_rank_volatility');
    const rankingMarketCapFilter = params.get('industry_rank_market_cap');

    return {
        tab: INDUSTRY_VALID_TABS.has(tab) ? tab : INDUSTRY_URL_DEFAULTS.tab,
        marketCapFilter: INDUSTRY_VALID_FILTERS.has(marketCapFilter) ? marketCapFilter : INDUSTRY_URL_DEFAULTS.marketCapFilter,
        timeframe: [1, 5, 10, 20, 60].includes(timeframe) ? timeframe : INDUSTRY_URL_DEFAULTS.timeframe,
        sizeMetric: INDUSTRY_VALID_SIZE_METRICS.has(sizeMetric) ? sizeMetric : INDUSTRY_URL_DEFAULTS.sizeMetric,
        colorMetric: INDUSTRY_VALID_COLOR_METRICS.has(colorMetric) ? colorMetric : INDUSTRY_URL_DEFAULTS.colorMetric,
        displayCount: [0, 30, 50].includes(displayCount) ? displayCount : INDUSTRY_URL_DEFAULTS.displayCount,
        searchTerm: typeof searchTerm === 'string' ? searchTerm : INDUSTRY_URL_DEFAULTS.searchTerm,
        rankType: INDUSTRY_VALID_RANK_TYPES.has(rankType) ? rankType : INDUSTRY_URL_DEFAULTS.rankType,
        sortBy: INDUSTRY_VALID_SORTS.has(sortBy) ? sortBy : INDUSTRY_URL_DEFAULTS.sortBy,
        lookbackDays: [1, 5, 10].includes(lookbackDays) ? lookbackDays : INDUSTRY_URL_DEFAULTS.lookbackDays,
        volatilityFilter: INDUSTRY_VALID_VOLATILITY_FILTERS.has(volatilityFilter) ? volatilityFilter : INDUSTRY_URL_DEFAULTS.volatilityFilter,
        rankingMarketCapFilter: INDUSTRY_VALID_FILTERS.has(rankingMarketCapFilter) ? rankingMarketCapFilter : INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter,
    };
};

const writeIndustryUrlState = (state) => {
    const params = new URLSearchParams(window.location.search);
    const nextState = { ...INDUSTRY_URL_DEFAULTS, ...state };

    const syncParam = (key, value, defaultValue) => {
        if (value === defaultValue || value === '' || value == null) {
            params.delete(key);
        } else {
            params.set(key, String(value));
        }
    };

    syncParam('industry_tab', nextState.tab, INDUSTRY_URL_DEFAULTS.tab);
    syncParam('industry_market_cap_filter', nextState.marketCapFilter, INDUSTRY_URL_DEFAULTS.marketCapFilter);
    syncParam('industry_timeframe', nextState.timeframe, INDUSTRY_URL_DEFAULTS.timeframe);
    syncParam('industry_size_metric', nextState.sizeMetric, INDUSTRY_URL_DEFAULTS.sizeMetric);
    syncParam('industry_color_metric', nextState.colorMetric, INDUSTRY_URL_DEFAULTS.colorMetric);
    syncParam('industry_display_count', nextState.displayCount, INDUSTRY_URL_DEFAULTS.displayCount);
    syncParam('industry_search', nextState.searchTerm, INDUSTRY_URL_DEFAULTS.searchTerm);
    syncParam('industry_rank_type', nextState.rankType, INDUSTRY_URL_DEFAULTS.rankType);
    syncParam('industry_rank_sort', nextState.sortBy, INDUSTRY_URL_DEFAULTS.sortBy);
    syncParam('industry_rank_lookback', nextState.lookbackDays, INDUSTRY_URL_DEFAULTS.lookbackDays);
    syncParam('industry_rank_volatility', nextState.volatilityFilter, INDUSTRY_URL_DEFAULTS.volatilityFilter);
    syncParam('industry_rank_market_cap', nextState.rankingMarketCapFilter, INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter);

    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
    window.history.replaceState(null, '', nextUrl);
};

/**
 * 行业分析主 Dashboard
 * 整合热力图、行业趋势、龙头股面板、行业排名等功能
 */
const IndustryDashboard = () => {
    const message = useSafeMessageApi();
    const initialUrlState = readIndustryUrlState();
    const [activeTab, setActiveTab] = useState(initialUrlState.tab);
    const [marketCapFilter, setMarketCapFilter] = useState(initialUrlState.marketCapFilter);
    const [heatmapViewState, setHeatmapViewState] = useState({
        timeframe: initialUrlState.timeframe,
        sizeMetric: initialUrlState.sizeMetric,
        colorMetric: initialUrlState.colorMetric,
        displayCount: initialUrlState.displayCount,
        searchTerm: initialUrlState.searchTerm,
    });
    const [hotIndustries, setHotIndustries] = useState([]);
    const [loadingHot, setLoadingHot] = useState(false);
    const [hotRetryTick, setHotRetryTick] = useState(0);
    const [selectedIndustry, setSelectedIndustry] = useState(null);
    const [industryStocks, setIndustryStocks] = useState([]);
    const [loadingStocks, setLoadingStocks] = useState(false);
    const [stocksRefining, setStocksRefining] = useState(false);
    const [stocksScoreStage, setStocksScoreStage] = useState(null);
    const [stocksDisplayReady, setStocksDisplayReady] = useState(false);
    const [clusters, setClusters] = useState(null);
    const [loadingClusters, setLoadingClusters] = useState(false);
    const [clusterError, setClusterError] = useState(null);
    const [clusterCount, setClusterCount] = useState(4);
    const [selectedClusterPoint, setSelectedClusterPoint] = useState(null);
    const [rankType, setRankType] = useState(initialUrlState.rankType); // gainers | losers
    const [sortBy, setSortBy] = useState(initialUrlState.sortBy); // 排序维度 — 默认综合得分
    const [lookbackDays, setLookbackDays] = useState(initialUrlState.lookbackDays); // 排行回看周期
    const [volatilityFilter, setVolatilityFilter] = useState(initialUrlState.volatilityFilter); // all | low | medium | high
    const [rankingMarketCapFilter, setRankingMarketCapFilter] = useState(initialUrlState.rankingMarketCapFilter);
    const [focusedHeatmapControlKey, setFocusedHeatmapControlKey] = useState(null);
    const [focusedRankingControlKey, setFocusedRankingControlKey] = useState(null);
    const [comparisonIndustries, setComparisonIndustries] = useState([]); // 对比行业
    const [detailVisible, setDetailVisible] = useState(false); // 详情弹窗状态
    const [heatmapSummary, setHeatmapSummary] = useState(null); // 热力图摘要数据
    const [heatmapIndustries, setHeatmapIndustries] = useState([]); // 热力图原始行业快照
    const [heatmapLegendRange, setHeatmapLegendRange] = useState(null);
    const [heatmapFullscreen, setHeatmapFullscreen] = useState(false);
    const [stockDetailVisible, setStockDetailVisible] = useState(false); // 龙头股详情弹窗
    const [stockDetailSymbol, setStockDetailSymbol] = useState(null);
    const [stockDetailData, setStockDetailData] = useState(null);
    const [stockDetailLoading, setStockDetailLoading] = useState(false);
    const [stockDetailError, setStockDetailError] = useState(null);
    const [shouldRenderLeaderPanel, setShouldRenderLeaderPanel] = useState(false);
    const [industryAlertRule, setIndustryAlertRule] = useState('all');
    const [industryAlertRecency, setIndustryAlertRecency] = useState('15');
    const [industryAlertHistory, setIndustryAlertHistory] = useState({});
    const [industryAlertSubscription, setIndustryAlertSubscription] = useState({
        scope: 'all',
        kinds: INDUSTRY_ALERT_KIND_OPTIONS.map((item) => item.value),
    });
    const [industryAlertSubscriptionHydrated, setIndustryAlertSubscriptionHydrated] = useState(false);
    const [desktopAlertNotifications, setDesktopAlertNotifications] = useState(false);
    const [watchlistIndustries, setWatchlistIndustries] = useState([]);
    const [watchlistHydrated, setWatchlistHydrated] = useState(false);
    const [savedViewDraftName, setSavedViewDraftName] = useState('');
    const [savedIndustryViews, setSavedIndustryViews] = useState([]);
    const [heatmapReplaySnapshots, setHeatmapReplaySnapshots] = useState([]);
    const [selectedReplaySnapshotId, setSelectedReplaySnapshotId] = useState(null);
    const [latestLiveHeatmapData, setLatestLiveHeatmapData] = useState(null);
    const [replayWindow, setReplayWindow] = useState('24h');
    const [comparisonBaseSnapshotId, setComparisonBaseSnapshotId] = useState(null);
    const [replayDiffIndustry, setReplayDiffIndustry] = useState(null);
    const [scoreRadarRecord, setScoreRadarRecord] = useState(null);
    const hotRequestIdRef = useRef(0);
    const rankingPrefetchedRef = useRef(false);
    const clusterPrefetchedRef = useRef(false);
    const hotInFlightQueryKeyRef = useRef(null);
    const hotLoadedQueryKeyRef = useRef(null);
    const clusterAutoAttemptedRef = useRef(false);
    
    // AbortControllers refs
    const hotIndustriesAbortRef = useRef(null);
    const clustersAbortRef = useRef(null);
    const industryStocksAbortRef = useRef(null);
    const stockDetailAbortRef = useRef(null);
    const industryStocksRequestIdRef = useRef(0);
    const stockDetailRequestIdRef = useRef(0);

    const buildHotQueryKey = useCallback((topN, type, sort, lookback) =>
        `top_n:${topN}|type:${type}|sort:${sort}|lookback:${lookback}`, []);

    const toggleMarketCapFilter = useCallback((nextFilter) => {
        setMarketCapFilter((current) => (current === nextFilter ? 'all' : nextFilter));
        setActiveTab('heatmap');
    }, []);

    const jumpToMarketCapFilter = useCallback((nextFilter) => {
        setMarketCapFilter(nextFilter || 'all');
        setActiveTab('heatmap');
    }, []);

    const resetHeatmapViewState = useCallback(() => {
        setMarketCapFilter(INDUSTRY_URL_DEFAULTS.marketCapFilter);
        setHeatmapLegendRange(null);
        setHeatmapViewState({
            timeframe: INDUSTRY_URL_DEFAULTS.timeframe,
            sizeMetric: INDUSTRY_URL_DEFAULTS.sizeMetric,
            colorMetric: INDUSTRY_URL_DEFAULTS.colorMetric,
            displayCount: INDUSTRY_URL_DEFAULTS.displayCount,
            searchTerm: INDUSTRY_URL_DEFAULTS.searchTerm,
        });
        setActiveTab('heatmap');
    }, []);

    const clearHeatmapStateTag = useCallback((key) => {
        if (key === 'market_cap_filter') {
            setMarketCapFilter(INDUSTRY_URL_DEFAULTS.marketCapFilter);
        } else if (key === 'timeframe') {
            setHeatmapViewState(prev => ({ ...prev, timeframe: INDUSTRY_URL_DEFAULTS.timeframe }));
        } else if (key === 'size_metric') {
            setHeatmapViewState(prev => ({ ...prev, sizeMetric: INDUSTRY_URL_DEFAULTS.sizeMetric }));
        } else if (key === 'color_metric') {
            setHeatmapViewState(prev => ({ ...prev, colorMetric: INDUSTRY_URL_DEFAULTS.colorMetric }));
        } else if (key === 'display_count') {
            setHeatmapViewState(prev => ({ ...prev, displayCount: INDUSTRY_URL_DEFAULTS.displayCount }));
        } else if (key === 'search') {
            setHeatmapViewState(prev => ({ ...prev, searchTerm: INDUSTRY_URL_DEFAULTS.searchTerm }));
        } else if (key === 'legend_range') {
            setHeatmapLegendRange(null);
        }
        setActiveTab('heatmap');
    }, []);

    const focusHeatmapControl = useCallback((key) => {
        setActiveTab('heatmap');
        setFocusedHeatmapControlKey(key);
    }, []);

    const resetRankingViewState = useCallback(() => {
        setRankType(INDUSTRY_URL_DEFAULTS.rankType);
        setSortBy(INDUSTRY_URL_DEFAULTS.sortBy);
        setLookbackDays(INDUSTRY_URL_DEFAULTS.lookbackDays);
        setVolatilityFilter(INDUSTRY_URL_DEFAULTS.volatilityFilter);
        setRankingMarketCapFilter(INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter);
        setActiveTab('ranking');
    }, []);

    const clearRankingStateTag = useCallback((key) => {
        if (key === 'rank_type') {
            setRankType(INDUSTRY_URL_DEFAULTS.rankType);
        } else if (key === 'sort_by') {
            setSortBy(INDUSTRY_URL_DEFAULTS.sortBy);
        } else if (key === 'lookback') {
            setLookbackDays(INDUSTRY_URL_DEFAULTS.lookbackDays);
        } else if (key === 'volatility_filter') {
            setVolatilityFilter(INDUSTRY_URL_DEFAULTS.volatilityFilter);
        } else if (key === 'market_cap_filter') {
            setRankingMarketCapFilter(INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter);
        }
        setActiveTab('ranking');
    }, []);

    const focusRankingControl = useCallback((key) => {
        setActiveTab('ranking');
        setFocusedRankingControlKey(key);
    }, []);

    useEffect(() => {
        if (!focusedRankingControlKey) return undefined;
        const selectorMap = {
            rank_type: '.ranking-control-rank-type',
            sort_by: '.ranking-control-sort-by',
            lookback: '.ranking-control-lookback',
            volatility_filter: '.ranking-control-volatility',
            market_cap_filter: '.ranking-control-market-cap',
        };
        const timeoutId = window.setTimeout(() => {
            const node = document.querySelector(selectorMap[focusedRankingControlKey]);
            if (node) {
                node.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
                const focusTarget = node.querySelector('input, button, .ant-select-selector');
                if (focusTarget?.focus) {
                    focusTarget.focus();
                }
            }
        }, 120);
        const clearId = window.setTimeout(() => setFocusedRankingControlKey(null), 1800);
        return () => {
            window.clearTimeout(timeoutId);
            window.clearTimeout(clearId);
        };
    }, [focusedRankingControlKey]);

    useEffect(() => {
        if (!focusedHeatmapControlKey) return undefined;
        const selectorMap = {
            market_cap_filter: '.heatmap-control-market-cap-filter',
        };
        const timeoutId = window.setTimeout(() => {
            const selector = selectorMap[focusedHeatmapControlKey];
            if (!selector) return;
            const node = document.querySelector(selector);
            if (node) {
                node.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
            }
        }, 120);
        const clearId = window.setTimeout(() => setFocusedHeatmapControlKey(null), 1800);
        return () => {
            window.clearTimeout(timeoutId);
            window.clearTimeout(clearId);
        };
    }, [focusedHeatmapControlKey]);

    useEffect(() => {
        const applyIndustryUrlState = () => {
            const nextState = readIndustryUrlState();
            setActiveTab(nextState.tab);
            setMarketCapFilter(nextState.marketCapFilter);
            setHeatmapViewState({
                timeframe: nextState.timeframe,
                sizeMetric: nextState.sizeMetric,
                colorMetric: nextState.colorMetric,
                displayCount: nextState.displayCount,
                searchTerm: nextState.searchTerm,
            });
            setRankType(nextState.rankType);
            setSortBy(nextState.sortBy);
            setLookbackDays(nextState.lookbackDays);
            setVolatilityFilter(nextState.volatilityFilter);
            setRankingMarketCapFilter(nextState.rankingMarketCapFilter);
        };

        window.addEventListener('popstate', applyIndustryUrlState);
        return () => window.removeEventListener('popstate', applyIndustryUrlState);
    }, []);

    const captureCurrentViewState = useCallback(() => ({
        activeTab,
        marketCapFilter,
        heatmapViewState,
        heatmapLegendRange,
        rankType,
        sortBy,
        lookbackDays,
        volatilityFilter,
        rankingMarketCapFilter,
        clusterCount,
        replayWindow,
        industryAlertRule,
        industryAlertRecency,
        industryAlertSubscription,
    }), [
        activeTab,
        marketCapFilter,
        heatmapViewState,
        heatmapLegendRange,
        rankType,
        sortBy,
        lookbackDays,
        volatilityFilter,
        rankingMarketCapFilter,
        clusterCount,
        replayWindow,
        industryAlertRule,
        industryAlertRecency,
        industryAlertSubscription,
    ]);

    const applySavedViewState = useCallback((state) => {
        if (!state) return;
        setActiveTab(state.activeTab || INDUSTRY_URL_DEFAULTS.tab);
        setMarketCapFilter(state.marketCapFilter || INDUSTRY_URL_DEFAULTS.marketCapFilter);
        setHeatmapViewState({
            timeframe: state.heatmapViewState?.timeframe ?? INDUSTRY_URL_DEFAULTS.timeframe,
            sizeMetric: state.heatmapViewState?.sizeMetric ?? INDUSTRY_URL_DEFAULTS.sizeMetric,
            colorMetric: state.heatmapViewState?.colorMetric ?? INDUSTRY_URL_DEFAULTS.colorMetric,
            displayCount: state.heatmapViewState?.displayCount ?? INDUSTRY_URL_DEFAULTS.displayCount,
            searchTerm: state.heatmapViewState?.searchTerm ?? INDUSTRY_URL_DEFAULTS.searchTerm,
        });
        setHeatmapLegendRange(state.heatmapLegendRange ?? null);
        setRankType(state.rankType || INDUSTRY_URL_DEFAULTS.rankType);
        setSortBy(state.sortBy || INDUSTRY_URL_DEFAULTS.sortBy);
        setLookbackDays(state.lookbackDays || INDUSTRY_URL_DEFAULTS.lookbackDays);
        setVolatilityFilter(state.volatilityFilter || INDUSTRY_URL_DEFAULTS.volatilityFilter);
        setRankingMarketCapFilter(state.rankingMarketCapFilter || INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter);
        setClusterCount(state.clusterCount || 4);
        setReplayWindow(state.replayWindow || '24h');
        setIndustryAlertRule(state.industryAlertRule || 'all');
        setIndustryAlertRecency(state.industryAlertRecency || '15');
        setIndustryAlertSubscription({
            scope: state.industryAlertSubscription?.scope === 'watchlist' ? 'watchlist' : 'all',
            kinds: Array.isArray(state.industryAlertSubscription?.kinds) && state.industryAlertSubscription.kinds.length > 0
                ? state.industryAlertSubscription.kinds
                : INDUSTRY_ALERT_KIND_OPTIONS.map((item) => item.value),
        });
    }, []);

    const saveCurrentIndustryView = useCallback(() => {
        const trimmedName = savedViewDraftName.trim();
        const existingNames = new Set(savedIndustryViews.map((item) => item.name));
        let nextName = trimmedName || `行业视图 ${savedIndustryViews.length + 1}`;
        if (existingNames.has(nextName)) {
            nextName = `${nextName} ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`;
        }
        const nextView = {
            id: `industry-view-${Date.now()}`,
            name: nextName,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            state: captureCurrentViewState(),
        };
        setSavedIndustryViews((current) => [nextView, ...current].slice(0, 12));
        setSavedViewDraftName('');
        message.success(`已保存视图：${nextName}`);
    }, [captureCurrentViewState, message, savedIndustryViews, savedViewDraftName]);

    const applySavedIndustryView = useCallback((viewId) => {
        const target = savedIndustryViews.find((item) => item.id === viewId);
        if (!target) return;
        applySavedViewState(target.state);
        message.success(`已切换到视图：${target.name}`);
    }, [applySavedViewState, message, savedIndustryViews]);

    const overwriteSavedIndustryView = useCallback((viewId) => {
        setSavedIndustryViews((current) => current.map((item) => (
            item.id === viewId
                ? {
                    ...item,
                    updatedAt: new Date().toISOString(),
                    state: captureCurrentViewState(),
                }
                : item
        )));
        message.success('已用当前配置覆盖保存视图');
    }, [captureCurrentViewState, message]);

    const removeSavedIndustryView = useCallback((viewId) => {
        setSavedIndustryViews((current) => current.filter((item) => item.id !== viewId));
        message.success('已删除保存视图');
    }, [message]);

    useEffect(() => {
        let isActive = true;

        const hydrateReplaySnapshots = async () => {
        try {
            const storedSnapshotsRaw = window.localStorage.getItem(INDUSTRY_REPLAY_STORAGE_KEY);
            let localSnapshots = [];
            if (storedSnapshotsRaw) {
                const parsedSnapshots = JSON.parse(storedSnapshotsRaw);
                localSnapshots = pruneReplaySnapshots(Array.isArray(parsedSnapshots) ? parsedSnapshots : []);
            }

            const storedSelectedSnapshotId = window.localStorage.getItem(INDUSTRY_REPLAY_SELECTION_KEY);
            if (storedSelectedSnapshotId && isActive) {
                setSelectedReplaySnapshotId(storedSelectedSnapshotId);
            }

            let mergedSnapshots = localSnapshots;
            try {
                const historyResponse = await getIndustryHeatmapHistory({ limit: MAX_HEATMAP_REPLAY_SNAPSHOTS });
                const backendSnapshots = pruneReplaySnapshots((historyResponse?.items || []).map((item) => ({
                    snapshot_id: item.snapshot_id,
                    days: item.days,
                    captured_at: item.captured_at,
                    update_time: item.update_time,
                    max_value: item.max_value,
                    min_value: item.min_value,
                    industries: item.industries || [],
                })));
                const byId = new Map();
                [...backendSnapshots, ...localSnapshots].forEach((snapshot) => {
                    if (!snapshot?.id) return;
                    if (!byId.has(snapshot.id)) {
                        byId.set(snapshot.id, snapshot);
                    }
                });
                mergedSnapshots = pruneReplaySnapshots(Array.from(byId.values()));
            } catch (historyError) {
                console.warn('Failed to hydrate industry replay snapshots from backend history:', historyError);
            }

            if (isActive && mergedSnapshots.length > 0) {
                setHeatmapReplaySnapshots(mergedSnapshots);
            }
        } catch (error) {
            console.warn('Failed to hydrate industry replay snapshots:', error);
        }
        };

        hydrateReplaySnapshots();

        return () => {
            isActive = false;
        };
    }, []);

    useEffect(() => {
        try {
            const storedWatchlist = window.localStorage.getItem(INDUSTRY_WATCHLIST_STORAGE_KEY);
            if (!storedWatchlist) return;
            const parsedWatchlist = JSON.parse(storedWatchlist);
            if (Array.isArray(parsedWatchlist)) {
                setWatchlistIndustries(
                    Array.from(new Set(parsedWatchlist.filter((item) => typeof item === 'string' && item.trim()))).slice(0, MAX_WATCHLIST_INDUSTRIES)
                );
            }
        } catch (error) {
            console.warn('Failed to hydrate industry watchlist:', error);
        } finally {
            setWatchlistHydrated(true);
        }
    }, []);

    useEffect(() => {
        try {
            const storedSubscription = window.localStorage.getItem(INDUSTRY_ALERT_SUBSCRIPTION_STORAGE_KEY);
            if (!storedSubscription) return;
            const parsedSubscription = JSON.parse(storedSubscription);
            const nextKinds = Array.isArray(parsedSubscription?.kinds)
                ? parsedSubscription.kinds.filter((item) => INDUSTRY_ALERT_KIND_OPTIONS.some((option) => option.value === item))
                : INDUSTRY_ALERT_KIND_OPTIONS.map((item) => item.value);
            setIndustryAlertSubscription({
                scope: parsedSubscription?.scope === 'watchlist' ? 'watchlist' : 'all',
                kinds: nextKinds.length > 0 ? nextKinds : INDUSTRY_ALERT_KIND_OPTIONS.map((item) => item.value),
            });
        } catch (error) {
            console.warn('Failed to hydrate industry alert subscription:', error);
        } finally {
            setIndustryAlertSubscriptionHydrated(true);
        }
    }, []);

    useEffect(() => {
        try {
            const storedDesktopNotifications = window.localStorage.getItem(INDUSTRY_ALERT_DESKTOP_STORAGE_KEY);
            if (storedDesktopNotifications == null) {
                setDesktopAlertNotifications(typeof Notification !== 'undefined' && Notification.permission === 'granted');
                return;
            }
            setDesktopAlertNotifications(storedDesktopNotifications === 'true');
        } catch (error) {
            console.warn('Failed to hydrate industry desktop notifications:', error);
        }
    }, []);

    useEffect(() => {
        try {
            const storedSavedViews = window.localStorage.getItem(INDUSTRY_SAVED_VIEWS_STORAGE_KEY);
            if (!storedSavedViews) return;
            const parsedViews = JSON.parse(storedSavedViews);
            if (Array.isArray(parsedViews)) {
                setSavedIndustryViews(parsedViews.filter((item) => item?.id && item?.state));
            }
        } catch (error) {
            console.warn('Failed to hydrate industry saved views:', error);
        }
    }, []);

    useEffect(() => {
        try {
            const storedHistory = window.localStorage.getItem(INDUSTRY_ALERT_HISTORY_STORAGE_KEY);
            if (!storedHistory) return;
            const parsedHistory = JSON.parse(storedHistory);
            if (parsedHistory && typeof parsedHistory === 'object') {
                setIndustryAlertHistory(pruneIndustryAlertHistory(parsedHistory));
            }
        } catch (error) {
            console.warn('Failed to hydrate industry alert history:', error);
        }
    }, []);

    useEffect(() => {
        writeIndustryUrlState({
            tab: activeTab,
            marketCapFilter,
            timeframe: heatmapViewState.timeframe,
            sizeMetric: heatmapViewState.sizeMetric,
            colorMetric: heatmapViewState.colorMetric,
            displayCount: heatmapViewState.displayCount,
            searchTerm: heatmapViewState.searchTerm,
            rankType,
            sortBy,
            lookbackDays,
            volatilityFilter,
            rankingMarketCapFilter,
        });
    }, [activeTab, marketCapFilter, heatmapViewState, rankType, sortBy, lookbackDays, volatilityFilter, rankingMarketCapFilter]);

    useEffect(() => {
        try {
            const nextSnapshots = pruneReplaySnapshots(heatmapReplaySnapshots);
            window.localStorage.setItem(INDUSTRY_REPLAY_STORAGE_KEY, JSON.stringify(nextSnapshots));
            if (nextSnapshots.length !== heatmapReplaySnapshots.length) {
                setHeatmapReplaySnapshots(nextSnapshots);
            }
        } catch (error) {
            console.warn('Failed to persist industry replay snapshots:', error);
        }
    }, [heatmapReplaySnapshots]);

    useEffect(() => {
        try {
            if (selectedReplaySnapshotId) {
                window.localStorage.setItem(INDUSTRY_REPLAY_SELECTION_KEY, selectedReplaySnapshotId);
            } else {
                window.localStorage.removeItem(INDUSTRY_REPLAY_SELECTION_KEY);
            }
        } catch (error) {
            console.warn('Failed to persist selected replay snapshot:', error);
        }
    }, [selectedReplaySnapshotId]);

    useEffect(() => {
        if (!watchlistHydrated) return;
        try {
            window.localStorage.setItem(INDUSTRY_WATCHLIST_STORAGE_KEY, JSON.stringify(watchlistIndustries));
        } catch (error) {
            console.warn('Failed to persist industry watchlist:', error);
        }
    }, [watchlistHydrated, watchlistIndustries]);

    useEffect(() => {
        if (!industryAlertSubscriptionHydrated) return;
        try {
            window.localStorage.setItem(INDUSTRY_ALERT_SUBSCRIPTION_STORAGE_KEY, JSON.stringify(industryAlertSubscription));
        } catch (error) {
            console.warn('Failed to persist industry alert subscription:', error);
        }
    }, [industryAlertSubscription, industryAlertSubscriptionHydrated]);

    useEffect(() => {
        try {
            window.localStorage.setItem(
                INDUSTRY_ALERT_HISTORY_STORAGE_KEY,
                JSON.stringify(pruneIndustryAlertHistory(industryAlertHistory))
            );
        } catch (error) {
            console.warn('Failed to persist industry alert history:', error);
        }
    }, [industryAlertHistory]);

    useEffect(() => {
        try {
            window.localStorage.setItem(INDUSTRY_ALERT_DESKTOP_STORAGE_KEY, desktopAlertNotifications ? 'true' : 'false');
        } catch (error) {
            console.warn('Failed to persist industry desktop notifications:', error);
        }
    }, [desktopAlertNotifications]);

    useEffect(() => {
        try {
            window.localStorage.setItem(INDUSTRY_SAVED_VIEWS_STORAGE_KEY, JSON.stringify(savedIndustryViews));
        } catch (error) {
            console.warn('Failed to persist industry saved views:', error);
        }
    }, [savedIndustryViews]);

    const applyHeatmapSnapshot = useCallback((data) => {
        if (!data?.industries?.length) return;
        const industries = data.industries;
        setHeatmapIndustries(industries);
        const total = industries.length;
        const upCount = industries.filter(i => i.value > 0).length;
        const downCount = industries.filter(i => i.value < 0).length;
        const flatCount = industries.filter(i => i.value === 0).length;
        const upRatio = total > 0 ? Math.round((upCount / total) * 100) : 0;
        
        // 市场情绪算法优化：结合上涨家数占比和平均涨跌幅
        const avgChange = industries.reduce((acc, i) => acc + i.value, 0) / (total || 1);
        const sentimentRatio = upCount / (total || 1);
        
        let sentiment;
        if (sentimentRatio > 0.7 || (sentimentRatio > 0.55 && avgChange > 1.0)) {
            sentiment = { label: '极度乐观', color: '#f5222d', bg: 'rgba(245,34,45,0.15)' };
        } else if (sentimentRatio > 0.55 || avgChange > 0.3) {
            sentiment = { label: '偏多', color: '#cf1322', bg: 'rgba(207,19,34,0.1)' };
        } else if (sentimentRatio < 0.3 || (sentimentRatio < 0.45 && avgChange < -1.0)) {
            sentiment = { label: '极度恐慌', color: '#389e0d', bg: 'rgba(56,158,13,0.15)' };
        } else if (sentimentRatio < 0.45 || avgChange < -0.3) {
            sentiment = { label: '偏空', color: '#3f8600', bg: 'rgba(63,134,0,0.1)' };
        } else {
            sentiment = { label: '震荡中性', color: '#d48806', bg: 'rgba(212,136,6,0.1)' };
        }
        
        const sorted = [...industries].sort((a, b) => (b.moneyFlow || 0) - (a.moneyFlow || 0));
        const topInflow = sorted.filter(i => (i.moneyFlow || 0) > 0).slice(0, 3);
        const topOutflow = [...industries].sort((a, b) => (a.moneyFlow || 0) - (b.moneyFlow || 0)).filter(i => (i.moneyFlow || 0) < 0).slice(0, 2);
        const topTurnover = [...industries].sort((a, b) => (b.turnoverRate || 0) - (a.turnoverRate || 0)).slice(0, 2);
        const marketCapHealth = industries.reduce((acc, item) => {
            const source = String(item.marketCapSource || 'unknown');
            if (source.startsWith('snapshot_')) {
                acc.snapshotCount += 1;
                if (item.marketCapSnapshotIsStale) {
                    acc.staleSnapshotCount += 1;
                }
                if (typeof item.marketCapSnapshotAgeHours === 'number') {
                    acc.oldestSnapshotHours = Math.max(acc.oldestSnapshotHours, item.marketCapSnapshotAgeHours);
                }
            } else if (source === 'sina_proxy_stock_sum') {
                acc.proxyCount += 1;
            } else if (source === 'unknown' || source.startsWith('estimated')) {
                acc.estimatedCount += 1;
            } else {
                acc.liveCount += 1;
            }
            return acc;
        }, {
            liveCount: 0,
            snapshotCount: 0,
            staleSnapshotCount: 0,
            proxyCount: 0,
            estimatedCount: 0,
            oldestSnapshotHours: 0,
        });
        const coveragePct = total > 0
            ? Math.round(((marketCapHealth.liveCount + marketCapHealth.snapshotCount) / total) * 100)
            : 0;
        const coverageTone = coveragePct >= 85
            ? { color: '#52c41a', bg: 'rgba(82,196,26,0.12)' }
            : coveragePct >= 60
                ? { color: '#faad14', bg: 'rgba(250,173,20,0.12)' }
                : { color: '#ff7875', bg: 'rgba(255,120,117,0.12)' };
        setHeatmapSummary({ 
            upRatio, 
            sentiment, 
            topInflow, 
            topOutflow, 
            topTurnover, 
            total, 
            upCount, 
            downCount, 
            flatCount,
            updateTime: data.update_time,
            marketCapHealth: {
                ...marketCapHealth,
                coveragePct,
                coverageTone,
            }
        });
    }, []);

    const activeReplaySnapshot = useMemo(
        () => heatmapReplaySnapshots.find((item) => item.id === selectedReplaySnapshotId) || null,
        [heatmapReplaySnapshots, selectedReplaySnapshotId]
    );
    const latestReplaySnapshot = heatmapReplaySnapshots[0] || null;
    const filteredReplaySnapshots = useMemo(() => {
        const windowMs = getReplayWindowMs(replayWindow);
        if (!Number.isFinite(windowMs)) {
            return heatmapReplaySnapshots;
        }
        const now = Date.now();
        return heatmapReplaySnapshots.filter((snapshot) => {
            const timestamp = new Date(snapshot.updateTime || snapshot.capturedAt || now).getTime();
            return Number.isFinite(timestamp) && (now - timestamp) <= windowMs;
        });
    }, [heatmapReplaySnapshots, replayWindow]);
    const replayTargetSnapshot = activeReplaySnapshot || filteredReplaySnapshots[0] || latestReplaySnapshot || null;
    const replayComparisonBaseSnapshot = useMemo(() => {
        if (!filteredReplaySnapshots.length) return null;
        if (comparisonBaseSnapshotId) {
            return filteredReplaySnapshots.find((item) => item.id === comparisonBaseSnapshotId) || null;
        }
        if (replayTargetSnapshot?.id) {
            return filteredReplaySnapshots.find((item) => item.id !== replayTargetSnapshot.id) || null;
        }
        return filteredReplaySnapshots[1] || null;
    }, [comparisonBaseSnapshotId, filteredReplaySnapshots, replayTargetSnapshot]);
    const replayComparison = useMemo(() => {
        if (!replayTargetSnapshot?.data?.industries?.length || !replayComparisonBaseSnapshot?.data?.industries?.length) {
            return null;
        }

        const baseByIndustry = new Map(
            replayComparisonBaseSnapshot.data.industries.map((item) => [item.name, item])
        );
        const deltas = replayTargetSnapshot.data.industries
            .map((targetItem) => {
                const baseItem = baseByIndustry.get(targetItem.name);
                if (!baseItem) return null;
                const changeDelta = Number(targetItem.value || 0) - Number(baseItem.value || 0);
                const scoreDelta = Number(targetItem.total_score || 0) - Number(baseItem.total_score || 0);
                const flowDelta = Number(targetItem.moneyFlow || 0) - Number(baseItem.moneyFlow || 0);
                const turnoverDelta = Number(targetItem.turnoverRate || 0) - Number(baseItem.turnoverRate || 0);
                return {
                    name: targetItem.name,
                    changeDelta,
                    scoreDelta,
                    flowDelta,
                    turnoverDelta,
                    base: baseItem,
                    target: targetItem,
                    leadingStockChanged: (targetItem.leadingStock || '') !== (baseItem.leadingStock || ''),
                };
            })
            .filter(Boolean);

        if (!deltas.length) return null;

        const strongestRise = [...deltas].sort((a, b) => b.changeDelta - a.changeDelta).slice(0, 3);
        const strongestFall = [...deltas].sort((a, b) => a.changeDelta - b.changeDelta).slice(0, 3);
        const strongestScoreRise = [...deltas].sort((a, b) => b.scoreDelta - a.scoreDelta).slice(0, 3);
        const detailsByIndustry = new Map(deltas.map((item) => [item.name, item]));

        return {
            target: replayTargetSnapshot,
            base: replayComparisonBaseSnapshot,
            strongestRise,
            strongestFall,
            strongestScoreRise,
            detailsByIndustry,
        };
    }, [replayComparisonBaseSnapshot, replayTargetSnapshot]);

    const activeReplayDiffIndustry = useMemo(() => {
        if (!replayComparison?.detailsByIndustry?.size) {
            return null;
        }
        if (replayDiffIndustry && replayComparison.detailsByIndustry.has(replayDiffIndustry)) {
            return replayDiffIndustry;
        }
        if (selectedIndustry && replayComparison.detailsByIndustry.has(selectedIndustry)) {
            return selectedIndustry;
        }
        return replayComparison.strongestRise[0]?.name
            || replayComparison.strongestScoreRise[0]?.name
            || replayComparison.strongestFall[0]?.name
            || null;
    }, [replayComparison, replayDiffIndustry, selectedIndustry]);

    useEffect(() => {
        if (!activeReplayDiffIndustry) {
            if (replayDiffIndustry !== null) {
                setReplayDiffIndustry(null);
            }
            return;
        }
        if (replayDiffIndustry !== activeReplayDiffIndustry) {
            setReplayDiffIndustry(activeReplayDiffIndustry);
        }
    }, [activeReplayDiffIndustry, replayDiffIndustry]);

    const replayIndustryDiffDetail = useMemo(() => {
        if (!replayComparison?.detailsByIndustry?.size || !activeReplayDiffIndustry) {
            return null;
        }
        const detail = replayComparison.detailsByIndustry.get(activeReplayDiffIndustry);
        if (!detail) {
            return null;
        }

        const baseLeader = detail.base?.leadingStock || null;
        const targetLeader = detail.target?.leadingStock || null;
        const narrativeParts = [];

        if (detail.changeDelta >= 2) {
            narrativeParts.push('短线热度明显升温');
        } else if (detail.changeDelta <= -2) {
            narrativeParts.push('短线热度明显降温');
        } else {
            narrativeParts.push('价格表现整体平稳');
        }

        if (detail.flowDelta >= 1e8) {
            narrativeParts.push('主力资金继续净流入');
        } else if (detail.flowDelta <= -1e8) {
            narrativeParts.push('资金承接出现回落');
        }

        if (detail.leadingStockChanged && baseLeader && targetLeader) {
            narrativeParts.push(`龙头已从 ${baseLeader} 切换到 ${targetLeader}`);
        } else if (targetLeader) {
            narrativeParts.push(`龙头仍由 ${targetLeader} 领涨`);
        }

        return {
            ...detail,
            baseLeader,
            targetLeader,
            narrative: narrativeParts.join('，') || '当前快照差异较小，适合继续结合行业详情观察。',
        };
    }, [activeReplayDiffIndustry, replayComparison]);

    const handleReplayDiffIndustrySelect = useCallback((industryName) => {
        setReplayDiffIndustry(industryName);
        setSelectedIndustry(industryName);
    }, []);

    // 接收热力图数据摘要（供市场摘要横幅 + 会话内历史回放）
    const handleHeatmapDataLoad = useCallback((data) => {
        if (!data?.industries?.length) return;
        setLatestLiveHeatmapData(data);
        setHeatmapReplaySnapshots((current) => {
            const existingIndex = current.findIndex(
                (item) => item.updateTime === data.update_time && item.timeframe === heatmapViewState.timeframe
            );
            const snapshot = {
                id: buildHeatmapReplaySnapshotId(data.update_time, heatmapViewState.timeframe),
                updateTime: data.update_time || new Date().toISOString(),
                capturedAt: new Date().toISOString(),
                timeframe: heatmapViewState.timeframe,
                sizeMetric: heatmapViewState.sizeMetric,
                colorMetric: heatmapViewState.colorMetric,
                displayCount: heatmapViewState.displayCount,
                searchTerm: heatmapViewState.searchTerm,
                marketCapFilter,
                data,
            };

            const next = existingIndex >= 0
                ? current.map((item, index) => (index === existingIndex ? { ...item, ...snapshot, id: item.id } : item))
                : [snapshot, ...current].slice(0, MAX_HEATMAP_REPLAY_SNAPSHOTS);
            return next;
        });

        if (!selectedReplaySnapshotId) {
            applyHeatmapSnapshot(data);
        }
    }, [applyHeatmapSnapshot, heatmapViewState, marketCapFilter, selectedReplaySnapshotId]);

    useEffect(() => {
        if (activeReplaySnapshot?.data) {
            applyHeatmapSnapshot(activeReplaySnapshot.data);
            return;
        }
        if (latestLiveHeatmapData?.industries?.length) {
            applyHeatmapSnapshot(latestLiveHeatmapData);
        }
    }, [activeReplaySnapshot, applyHeatmapSnapshot, latestLiveHeatmapData]);

    useEffect(() => {
        if (!activeReplaySnapshot) return;
        if (heatmapViewState.timeframe !== activeReplaySnapshot.timeframe) {
            setSelectedReplaySnapshotId(null);
        }
    }, [activeReplaySnapshot, heatmapViewState.timeframe]);

    useEffect(() => {
        if (!selectedReplaySnapshotId) return;
        const exists = heatmapReplaySnapshots.some((snapshot) => snapshot.id === selectedReplaySnapshotId);
        if (!exists) {
            setSelectedReplaySnapshotId(null);
        }
    }, [heatmapReplaySnapshots, selectedReplaySnapshotId]);

    useEffect(() => {
        if (!comparisonBaseSnapshotId) return;
        const exists = filteredReplaySnapshots.some((snapshot) => snapshot.id === comparisonBaseSnapshotId);
        if (!exists) {
            setComparisonBaseSnapshotId(null);
        }
    }, [comparisonBaseSnapshotId, filteredReplaySnapshots]);

    // 加载热门行业
    const loadHotIndustries = useCallback(async (
        topN = 15,
        type = rankType,
        sort = sortBy,
        lookback = lookbackDays,
        silent = false
    ) => {
        const requestId = ++hotRequestIdRef.current;
        const queryKey = buildHotQueryKey(topN, type, sort, lookback);
        
        // 取消前一个进行中的请求
        if (hotIndustriesAbortRef.current) {
            hotIndustriesAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        hotIndustriesAbortRef.current = currentAbort;

        let isCanceled = false;
        try {
            setLoadingHot(true);
            hotInFlightQueryKeyRef.current = queryKey;
            const order = type === 'gainers' ? 'desc' : 'asc';
            const result = await getHotIndustries(topN, lookback, sort, order, {
                signal: currentAbort.signal
            });
            // 忽略过期请求结果，避免筛选快速切换导致表格闪烁
            if (requestId === hotRequestIdRef.current && currentAbort === hotIndustriesAbortRef.current) {
                setHotIndustries(result || []);
                hotLoadedQueryKeyRef.current = queryKey;
            }
        } catch (err) {
            if (err.name === 'CanceledError') {
                console.log('hot industries request canceled');
                isCanceled = true;
                return;
            }
            if (requestId === hotRequestIdRef.current) {
                console.error('Failed to load hot industries:', err);
            }
            if (requestId === hotRequestIdRef.current && !silent) {
                message.error('加载行业排名失败');
            }
        } finally {
            if (requestId === hotRequestIdRef.current && hotIndustriesAbortRef.current === currentAbort) {
                setLoadingHot(false);
                hotInFlightQueryKeyRef.current = null;
                if (isCanceled && activeTab === 'ranking' && hotLoadedQueryKeyRef.current !== queryKey) {
                    setHotRetryTick((tick) => tick + 1);
                }
            }
        }
    }, [activeTab, rankType, sortBy, lookbackDays, buildHotQueryKey, message]);

    // 首次进入行业页时，等热力图首屏稳定后再空闲预取排行榜，避免冷启动阶段抢占带宽
    useEffect(() => {
        if (activeTab === 'ranking') return;
        if (rankingPrefetchedRef.current) return;
        if (!heatmapIndustries.length) return undefined;

        let timeoutId = null;
        let idleId = null;
        const schedulePrefetch = () => {
            if (rankingPrefetchedRef.current) return;
            rankingPrefetchedRef.current = true;
            loadHotIndustries(50, 'gainers', 'total_score', lookbackDays, true);
        };

        if (typeof window.requestIdleCallback === 'function') {
            idleId = window.requestIdleCallback(schedulePrefetch, { timeout: 2500 });
        } else {
            timeoutId = window.setTimeout(schedulePrefetch, 1400);
        }

        return () => {
            if (idleId != null && typeof window.cancelIdleCallback === 'function') {
                window.cancelIdleCallback(idleId);
            }
            if (timeoutId != null) {
                window.clearTimeout(timeoutId);
            }
        };
    }, [activeTab, lookbackDays, loadHotIndustries, heatmapIndustries.length]);

    // 右侧龙头股面板延后挂载，让热力图优先完成冷启动渲染
    useEffect(() => {
        if (shouldRenderLeaderPanel) return undefined;
        if (activeTab === 'ranking' || heatmapIndustries.length > 0) {
            const timeoutId = window.setTimeout(() => {
                setShouldRenderLeaderPanel(true);
            }, 180);
            return () => window.clearTimeout(timeoutId);
        }

        const fallbackId = window.setTimeout(() => {
            setShouldRenderLeaderPanel(true);
        }, 1600);
        return () => window.clearTimeout(fallbackId);
    }, [activeTab, heatmapIndustries.length, shouldRenderLeaderPanel]);

    // 加载行业成分股
    const loadIndustryStocks = useCallback(async (industryName) => {
        // 取消前一个请求
        if (industryStocksAbortRef.current) {
            industryStocksAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        industryStocksAbortRef.current = currentAbort;
        const requestId = industryStocksRequestIdRef.current + 1;
        industryStocksRequestIdRef.current = requestId;

        let isCanceled = false;
        try {
            setLoadingStocks(true);
            setStocksRefining(false);
            setStocksScoreStage(null);
            setStocksDisplayReady(false);
            setIndustryStocks([]);
            setSelectedIndustry(industryName);
            const quickResult = await getIndustryStocks(industryName, 20, {
                signal: currentAbort.signal
            });
            if (
                industryStocksAbortRef.current !== currentAbort ||
                industryStocksRequestIdRef.current !== requestId
            ) {
                return;
            }

            const quickRows = quickResult || [];
            setIndustryStocks(quickRows);
            setLoadingStocks(false);
            const quickStage = getIndustryStockScoreStage(quickRows);
            setStocksScoreStage(quickStage);
            setStocksDisplayReady(quickStage === 'full' || hasDisplayReadyIndustryStockDetails(quickRows));

            if (quickRows.length === 0 || quickStage !== 'quick') {
                setStocksRefining(false);
                return;
            }

            setStocksRefining(true);
            for (let attempt = 0; attempt < INDUSTRY_STOCK_FULL_POLL_ATTEMPTS; attempt += 1) {
                await waitForAbortableDelay(currentAbort.signal, INDUSTRY_STOCK_FULL_POLL_INTERVAL_MS);
                const refinedResult = await getIndustryStocks(industryName, 20, {
                    signal: currentAbort.signal
                });
                if (
                    industryStocksAbortRef.current !== currentAbort ||
                    industryStocksRequestIdRef.current !== requestId
                ) {
                    return;
                }

                const refinedRows = refinedResult || [];
                if (refinedRows.length > 0) {
                    setIndustryStocks(refinedRows);
                }
                const refinedStage = getIndustryStockScoreStage(refinedRows);
                setStocksScoreStage(refinedStage);
                setStocksDisplayReady(refinedStage === 'full' || (attempt >= 1 && hasDisplayReadyIndustryStockDetails(refinedRows)));
                if (refinedStage === 'full') {
                    setStocksRefining(false);
                    return;
                }
            }
            setStocksRefining(false);
        } catch (err) {
            if (err.name === 'CanceledError' || err.name === 'AbortError') {
                isCanceled = true;
                return;
            }
            if (
                industryStocksAbortRef.current !== currentAbort ||
                industryStocksRequestIdRef.current !== requestId
            ) {
                return;
            }
            console.error('Failed to load industry stocks:', err);
            message.error('加载行业成分股失败');
        } finally {
            if (
                !isCanceled &&
                industryStocksAbortRef.current === currentAbort &&
                industryStocksRequestIdRef.current === requestId
            ) {
                setLoadingStocks(false);
                setStocksRefining(false);
            }
        }
    }, [message]);

    // 加载聚类分析
    const loadClusters = useCallback(async (silent = false) => {
        if (clustersAbortRef.current) {
            clustersAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        clustersAbortRef.current = currentAbort;

        let isCanceled = false;
        try {
            setLoadingClusters(true);
            setClusterError(null);
            const result = await getIndustryClusters(clusterCount, {
                signal: currentAbort.signal
            });
            if (clustersAbortRef.current !== currentAbort) return;
            setClusters(result);
        } catch (err) {
            if (err.name === 'CanceledError') {
                isCanceled = true;
                return;
            }
            if (clustersAbortRef.current !== currentAbort) return;
            console.error('Failed to load clusters:', err);
            setClusterError(err.userMessage || '加载聚类分析失败');
            if (!silent) {
                message.error('加载聚类分析失败');
            }
        } finally {
            if (!isCanceled && clustersAbortRef.current === currentAbort) {
                setLoadingClusters(false);
            }
        }
    }, [clusterCount, message]);

    // 聚类分析耗时更久，首屏稳定后空闲预取一次，避免首次切页等待过长
    useEffect(() => {
        if (activeTab === 'clusters') return;
        if (clusterPrefetchedRef.current) return;
        if (!heatmapIndustries.length) return undefined;

        let timeoutId = null;
        let idleId = null;
        const schedulePrefetch = () => {
            if (clusterPrefetchedRef.current) return;
            clusterPrefetchedRef.current = true;
            loadClusters(true);
        };

        if (typeof window.requestIdleCallback === 'function') {
            idleId = window.requestIdleCallback(schedulePrefetch, { timeout: 4200 });
        } else {
            timeoutId = window.setTimeout(schedulePrefetch, 2200);
        }

        return () => {
            if (idleId != null && typeof window.cancelIdleCallback === 'function') {
                window.cancelIdleCallback(idleId);
            }
            if (timeoutId != null) {
                window.clearTimeout(timeoutId);
            }
        };
    }, [activeTab, loadClusters, heatmapIndustries.length]);

    // 当切换到排名或聚类标签时自动加载数据
    useEffect(() => {
        if (activeTab === 'ranking') {
            const targetQueryKey = buildHotQueryKey(50, rankType, sortBy, lookbackDays);
            const hasMatchingLoaded = hotLoadedQueryKeyRef.current === targetQueryKey;
            const hasMatchingInFlight = hotInFlightQueryKeyRef.current === targetQueryKey;
            if (!hasMatchingLoaded && !hasMatchingInFlight) {
                loadHotIndustries(50, rankType, sortBy, lookbackDays);
            }
        }
        if (activeTab === 'clusters' && !clusters && !loadingClusters && !clusterAutoAttemptedRef.current) {
            clusterAutoAttemptedRef.current = true;
            loadClusters(true);
        }
    }, [activeTab, rankType, sortBy, lookbackDays, clusters, loadingClusters, loadHotIndustries, loadClusters, buildHotQueryKey, hotRetryTick]);

    useEffect(() => () => {
        if (hotIndustriesAbortRef.current) hotIndustriesAbortRef.current.abort();
        if (clustersAbortRef.current) clustersAbortRef.current.abort();
        if (industryStocksAbortRef.current) industryStocksAbortRef.current.abort();
        if (stockDetailAbortRef.current) stockDetailAbortRef.current.abort();
    }, []);

    // 处理行业点击 → 打开行业详情弹窗
    const handleIndustryClick = (industryName) => {
        setSelectedIndustry(industryName);
        loadIndustryStocks(industryName); // 自动加载成分股
        setDetailVisible(true);
    };

    // 添加行业到对比列表
    const handleAddToComparison = (industryName) => {
        if (!industryName) return;
        if (comparisonIndustries.includes(industryName)) {
            setActiveTab('rotation');
            return;
        }
        if (comparisonIndustries.length >= 5) {
            message.warning('最多对比 5 个行业');
            return;
        }
        setComparisonIndustries((prev) => [...prev, industryName]);
        setActiveTab('rotation');
    };

    const openSelectedIndustryDetail = useCallback(() => {
        if (!selectedIndustry) return;
        loadIndustryStocks(selectedIndustry);
        setDetailVisible(true);
    }, [loadIndustryStocks, selectedIndustry]);

    const toggleWatchlistIndustry = useCallback((industryName) => {
        if (!industryName) return;
        const alreadyWatched = watchlistIndustries.includes(industryName);
        if (alreadyWatched) {
            setWatchlistIndustries((current) => current.filter((item) => item !== industryName));
            message.success(`${industryName} 已移出观察列表`);
            return;
        }
        if (watchlistIndustries.length >= MAX_WATCHLIST_INDUSTRIES) {
            message.warning(`观察列表最多保留 ${MAX_WATCHLIST_INDUSTRIES} 个行业`);
            return;
        }
        setWatchlistIndustries((current) => [industryName, ...current]);
        message.success(`${industryName} 已加入观察列表`);
    }, [message, watchlistIndustries]);

    // 热力图领涨股点击 → 加载股票详情
    const handleLeadingStockClick = useCallback(async (stockName) => {
        if (stockDetailAbortRef.current) {
            stockDetailAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        stockDetailAbortRef.current = currentAbort;
        const requestId = stockDetailRequestIdRef.current + 1;
        stockDetailRequestIdRef.current = requestId;

        let isCanceled = false;
        try {
            setStockDetailLoading(true);
            setStockDetailVisible(true);
            setStockDetailSymbol(stockName);
            setStockDetailError(null);
            setStockDetailData(null);
            const result = await getLeaderDetail(stockName, 'hot', {
                signal: currentAbort.signal
            });
            if (
                stockDetailAbortRef.current !== currentAbort ||
                stockDetailRequestIdRef.current !== requestId
            ) {
                return;
            }
            setStockDetailData(result);
        } catch (err) {
            if (err.name === 'CanceledError' || err.name === 'AbortError') {
                isCanceled = true;
                return;
            }
            if (
                stockDetailAbortRef.current !== currentAbort ||
                stockDetailRequestIdRef.current !== requestId
            ) {
                return;
            }
            console.error('Failed to load stock detail:', err);
            setStockDetailError(err.userMessage || '加载股票详情失败');
        } finally {
            if (
                !isCanceled &&
                stockDetailAbortRef.current === currentAbort &&
                stockDetailRequestIdRef.current === requestId
            ) {
                setStockDetailLoading(false);
            }
        }
    }, []);

    const getIndustryVolatilityMeta = useCallback((value, source) => {
        const numericValue = Number(value || 0);
        const tone = numericValue >= 4
            ? { label: '高波动', color: 'error' }
            : numericValue >= 2
                ? { label: '中波动', color: 'warning' }
                : { label: '低波动', color: 'success' };
        const sourceLabelMap = {
            historical_index: '历史指数',
            stock_dispersion: '成分股离散度',
            amplitude_proxy: '振幅代理',
            turnover_rate_proxy: '换手率代理',
            change_proxy: '涨跌幅代理',
            unavailable: '暂无',
        };
        return {
            ...tone,
            value: numericValue,
            sourceLabel: sourceLabelMap[source] || '暂无',
        };
    }, []);

    const filteredHotIndustries = useMemo(() => {
        return (hotIndustries || []).filter((item) => {
            const value = Number(item?.industryVolatility || 0);
            const sourceMeta = getMarketCapBadgeMeta(item?.marketCapSource);
            const matchesVolatility = (
                volatilityFilter === 'all'
                || (volatilityFilter === 'high' && value >= 4)
                || (volatilityFilter === 'medium' && value >= 2 && value < 4)
                || (volatilityFilter === 'low' && value > 0 && value < 2)
            );
            const matchesSource = rankingMarketCapFilter === 'all' || sourceMeta.filter === rankingMarketCapFilter;
            return matchesVolatility && matchesSource;
        });
    }, [hotIndustries, volatilityFilter, rankingMarketCapFilter]);

    const selectedIndustrySnapshot = useMemo(() => {
        if (!selectedIndustry) return null;

        const rankingCandidates = [...(hotIndustries || []), ...(filteredHotIndustries || [])];
        const rankingSnapshot = rankingCandidates.find((item) => item?.industry_name === selectedIndustry) || null;
        const heatmapSnapshot = (heatmapIndustries || []).find((item) => item?.name === selectedIndustry) || null;

        if (!rankingSnapshot && !heatmapSnapshot) {
            return null;
        }

        return {
            industry_name: selectedIndustry,
            score: rankingSnapshot?.score
                ?? rankingSnapshot?.total_score
                ?? heatmapSnapshot?.total_score
                ?? null,
            change_pct: rankingSnapshot?.change_pct
                ?? heatmapSnapshot?.value
                ?? null,
            money_flow: rankingSnapshot?.money_flow
                ?? heatmapSnapshot?.moneyFlow
                ?? null,
            industryVolatility: rankingSnapshot?.industryVolatility
                ?? heatmapSnapshot?.industryVolatility
                ?? null,
            industryVolatilitySource: rankingSnapshot?.industryVolatilitySource
                ?? heatmapSnapshot?.industryVolatilitySource
                ?? 'unavailable',
            total_market_cap: rankingSnapshot?.total_market_cap
                ?? heatmapSnapshot?.size
                ?? null,
            stock_count: rankingSnapshot?.stock_count
                ?? heatmapSnapshot?.stockCount
                ?? null,
            marketCapSource: rankingSnapshot?.marketCapSource
                ?? heatmapSnapshot?.marketCapSource
                ?? 'unknown',
            leadingStock: heatmapSnapshot?.leadingStock || null,
            leadingStockChange: heatmapSnapshot?.leadingStockChange ?? null,
            turnoverRate: heatmapSnapshot?.turnoverRate ?? null,
            netInflowRatio: heatmapSnapshot?.netInflowRatio ?? null,
            pe_ttm: heatmapSnapshot?.pe_ttm ?? null,
            pb: heatmapSnapshot?.pb ?? null,
            valuationSource: heatmapSnapshot?.valuationSource ?? 'unavailable',
            valuationQuality: heatmapSnapshot?.valuationQuality ?? 'unavailable',
            dataSources: heatmapSnapshot?.dataSources ?? [],
        };
    }, [selectedIndustry, hotIndustries, filteredHotIndustries, heatmapIndustries]);

    const selectedIndustryWatched = useMemo(
        () => Boolean(selectedIndustry && watchlistIndustries.includes(selectedIndustry)),
        [selectedIndustry, watchlistIndustries]
    );

    const selectedIndustryMarketCapBadge = useMemo(
        () => (selectedIndustrySnapshot ? getMarketCapBadgeMeta(selectedIndustrySnapshot.marketCapSource) : null),
        [selectedIndustrySnapshot]
    );

    const selectedIndustryVolatilityMeta = useMemo(
        () => getIndustryVolatilityMeta(
            selectedIndustrySnapshot?.industryVolatility,
            selectedIndustrySnapshot?.industryVolatilitySource
        ),
        [selectedIndustrySnapshot, getIndustryVolatilityMeta]
    );

    const selectedIndustryLeadStock = useMemo(
        () => (industryStocks || []).find((item) => item?.name || item?.symbol) || (
            selectedIndustrySnapshot?.leadingStock
                ? {
                    name: selectedIndustrySnapshot.leadingStock,
                    total_score: 0,
                    change_pct: selectedIndustrySnapshot.leadingStockChange,
                }
                : null
        ),
        [industryStocks, selectedIndustrySnapshot]
    );

    const selectedIndustryFocusNarrative = useMemo(() => {
        if (!selectedIndustry) {
            return '';
        }
        if (!selectedIndustrySnapshot) {
            return `${selectedIndustry} 已进入研究焦点，可以继续查看行业详情和龙头股联动。`;
        }

        const score = Number(selectedIndustrySnapshot.score || 0);
        const change = Number(selectedIndustrySnapshot.change_pct || 0);
        const moneyFlow = Number(selectedIndustrySnapshot.money_flow || 0);
        const volatility = Number(selectedIndustrySnapshot.industryVolatility || 0);

        if (score >= 80 && change > 0 && moneyFlow > 0) {
            return `${selectedIndustry} 当前处于强势共振区间，热度、涨幅和资金方向比较一致。`;
        }
        if (score >= 70 && moneyFlow > 0) {
            return `${selectedIndustry} 目前偏强，资金仍在净流入，适合继续顺着龙头和轮动看。`;
        }
        if (change < 0 && moneyFlow < 0) {
            return `${selectedIndustry} 当前偏弱，价格和资金都在承压，更适合先看风险释放是否结束。`;
        }
        if (volatility >= 4) {
            return `${selectedIndustry} 现在波动偏高，适合重点盯节奏和龙头分化，而不是只看静态排名。`;
        }
        return `${selectedIndustry} 目前处于观察区，适合结合行业详情、龙头表现和轮动位置一起判断。`;
    }, [selectedIndustry, selectedIndustrySnapshot]);

    const selectedIndustryReasons = useMemo(() => {
        if (!selectedIndustrySnapshot) return [];

        const reasons = [];
        const score = Number(selectedIndustrySnapshot.score || 0);
        const change = Number(selectedIndustrySnapshot.change_pct || 0);
        const moneyFlow = Number(selectedIndustrySnapshot.money_flow || 0);
        const stockCount = Number(selectedIndustrySnapshot.stock_count || 0);
        const marketCap = Number(selectedIndustrySnapshot.total_market_cap || 0);
        const volatility = Number(selectedIndustrySnapshot.industryVolatility || 0);

        if (score >= 80) {
            reasons.push(`综合得分 ${score.toFixed(1)}，已经属于当前榜单里的高热度行业。`);
        } else if (score >= 65) {
            reasons.push(`综合得分 ${score.toFixed(1)}，仍处在值得持续跟踪的活跃区间。`);
        }

        if (moneyFlow > 0) {
            reasons.push(`主力资金净流入 ${(moneyFlow / 1e8).toFixed(1)} 亿，短线关注度还在。`);
        } else if (moneyFlow < 0) {
            reasons.push(`主力资金净流出 ${Math.abs(moneyFlow / 1e8).toFixed(1)} 亿，需要留意承接是否变弱。`);
        }

        if (change >= 3) {
            reasons.push(`近阶段涨幅 ${change.toFixed(2)}%，价格表现已经明显跑出来了。`);
        } else if (change <= -3) {
            reasons.push(`近阶段回撤 ${Math.abs(change).toFixed(2)}%，更适合结合风险释放视角去看。`);
        }

        if (volatility >= 4) {
            reasons.push(`区间波动率 ${volatility.toFixed(1)}%，行业内部可能已经开始分化。`);
        }

        if (marketCap > 0 && stockCount > 0) {
            reasons.push(`板块总市值约 ${(marketCap / 1e8).toFixed(0)} 亿，覆盖 ${stockCount} 只成分股，具备板块代表性。`);
        }

        if (selectedIndustryLeadStock?.name || selectedIndustryLeadStock?.symbol) {
            const leadName = selectedIndustryLeadStock.name || selectedIndustryLeadStock.symbol;
            const leadScore = Number(selectedIndustryLeadStock.total_score || 0);
            reasons.push(
                leadScore > 0
                    ? `龙头候选 ${leadName} 当前得分 ${leadScore.toFixed(1)}，可以直接往个股层继续下钻。`
                    : `龙头候选 ${leadName} 已经可见，适合继续看个股承接和扩散。`
            );
        }

        return reasons.slice(0, 3);
    }, [selectedIndustrySnapshot, selectedIndustryLeadStock]);

    const selectedIndustryScoreBreakdown = useMemo(() => {
        if (!selectedIndustrySnapshot) return [];

        const change = Number(selectedIndustrySnapshot.change_pct || 0);
        const moneyFlow = Number(selectedIndustrySnapshot.money_flow || 0);
        const netInflowRatio = Number(selectedIndustrySnapshot.netInflowRatio || 0);
        const turnoverRate = Number(selectedIndustrySnapshot.turnoverRate || 0);
        const volatility = Number(selectedIndustrySnapshot.industryVolatility || 0);
        const leadScore = Number(selectedIndustryLeadStock?.total_score || 0);
        const leadChange = Number(selectedIndustryLeadStock?.change_pct || selectedIndustrySnapshot.leadingStockChange || 0);
        const hasLeader = Boolean(selectedIndustryLeadStock?.name || selectedIndustryLeadStock?.symbol || selectedIndustrySnapshot.leadingStock);
        const valuationQuality = selectedIndustrySnapshot.valuationQuality || 'unavailable';
        const pe = Number(selectedIndustrySnapshot.pe_ttm || 0);
        const pb = Number(selectedIndustrySnapshot.pb || 0);

        const priceScore = clampNumeric(((change + 4) / 8) * 100);
        const capitalBase = moneyFlow > 0 ? 58 : moneyFlow < 0 ? 24 : 40;
        const capitalImpulse = clampNumeric(Math.abs(moneyFlow) / 1e9 * 18, 0, 28);
        const capitalRatioAdjustment = clampNumeric(netInflowRatio * 6, -18, 18);
        const capitalScore = clampNumeric(capitalBase + capitalImpulse + capitalRatioAdjustment);
        const turnoverScore = clampNumeric((turnoverRate / 5) * 100);
        const volatilityBalance = volatility > 0 ? clampNumeric(92 - Math.abs(volatility - 3) * 14, 24, 92) : 48;
        const activityScore = clampNumeric(turnoverScore * 0.65 + volatilityBalance * 0.35);
        const leaderBase = leadScore > 0 ? leadScore : (hasLeader ? 64 : 34);
        const leaderScore = clampNumeric(leaderBase + clampNumeric(leadChange * 4, -12, 12));
        const valuationBaseMap = {
            industry_level: 78,
            leader_proxy: 56,
            unavailable: 32,
        };
        let valuationScore = valuationBaseMap[valuationQuality] ?? 40;
        if (pe > 0) {
            if (pe >= 8 && pe <= 35) valuationScore += 12;
            else if (pe > 80) valuationScore -= 10;
        }
        if (pb > 0) {
            if (pb >= 1 && pb <= 4) valuationScore += 8;
            else if (pb > 10) valuationScore -= 6;
        }
        valuationScore = clampNumeric(valuationScore);

        const breakdown = [
            {
                key: 'price',
                label: '价格强度',
                score: priceScore,
                color: change >= 0 ? '#cf1322' : '#3f8600',
                summary: change >= 0
                    ? `行业涨跌幅 ${change.toFixed(2)}%，价格表现仍在正向贡献。`
                    : `行业涨跌幅 ${change.toFixed(2)}%，价格端正在拖累当前综合分。`,
            },
            {
                key: 'capital',
                label: '资金热度',
                score: capitalScore,
                color: moneyFlow >= 0 ? '#cf1322' : '#3f8600',
                summary: moneyFlow >= 0
                    ? `主力净流入 ${formatIndustryAlertMoneyFlow(moneyFlow)}，净流入占比 ${netInflowRatio.toFixed(2)}%。`
                    : `主力净流出 ${formatIndustryAlertMoneyFlow(moneyFlow)}，短线承接仍需继续确认。`,
            },
            {
                key: 'activity',
                label: '活跃度',
                score: activityScore,
                color: '#1677ff',
                summary: `换手率 ${turnoverRate ? turnoverRate.toFixed(2) : '-'}%，波动率 ${volatility ? volatility.toFixed(2) : '-'}%，体现板块活跃和分化程度。`,
            },
            {
                key: 'leader',
                label: '龙头牵引',
                score: leaderScore,
                color: '#722ed1',
                summary: hasLeader
                    ? `龙头候选 ${selectedIndustryLeadStock?.name || selectedIndustryLeadStock?.symbol || selectedIndustrySnapshot.leadingStock} ${leadScore > 0 ? `当前得分 ${leadScore.toFixed(1)}` : '已进入联动视图'}。`
                    : '当前还没有稳定龙头候选，板块扩散更值得继续观察。',
            },
            {
                key: 'valuation',
                label: '估值支撑',
                score: valuationScore,
                color: '#fa8c16',
                summary: valuationQuality === 'industry_level'
                    ? `估值来自行业级口径，PE ${pe > 0 ? pe.toFixed(2) : '-'}，PB ${pb > 0 ? pb.toFixed(2) : '-'}。`
                    : valuationQuality === 'leader_proxy'
                        ? '估值暂以龙头代理口径为主，更适合辅助判断，不宜单独下结论。'
                        : '当前估值口径较弱，更多适合和价格、资金、龙头一起看。',
            },
        ];

        return breakdown;
    }, [selectedIndustryLeadStock, selectedIndustrySnapshot]);

    const selectedIndustryScoreSummary = useMemo(() => {
        if (!selectedIndustryScoreBreakdown.length) return '';
        const dominant = [...selectedIndustryScoreBreakdown]
            .sort((left, right) => right.score - left.score)
            .slice(0, 2)
            .map((item) => item.label);
        return dominant.length > 0
            ? `当前综合分主要由${dominant.join('、')}在支撑。`
            : '';
    }, [selectedIndustryScoreBreakdown]);

    const focusIndustrySuggestions = useMemo(() => {
        const merged = [
            ...(heatmapSummary?.topInflow || []),
            ...(heatmapSummary?.topTurnover || []),
            ...(heatmapSummary?.topOutflow || []),
        ];
        const seen = new Set();
        return merged
            .map((item) => item?.name)
            .filter((name) => {
                if (!name || seen.has(name)) return false;
                seen.add(name);
                return true;
            })
            .slice(0, 5);
    }, [heatmapSummary]);

    const industryAlertSnapshots = useMemo(() => {
        const snapshots = new Map();

        (heatmapIndustries || []).forEach((item) => {
            if (!item?.name) return;
            snapshots.set(item.name, {
                industry_name: item.name,
                score: item.total_score ?? null,
                change_pct: item.value ?? null,
                money_flow: item.moneyFlow ?? null,
                industryVolatility: item.industryVolatility ?? null,
                turnoverRate: item.turnoverRate ?? null,
                stock_count: item.stockCount ?? null,
                marketCapSource: item.marketCapSource ?? 'unknown',
            });
        });

        (hotIndustries || []).forEach((item) => {
            if (!item?.industry_name) return;
            const current = snapshots.get(item.industry_name) || { industry_name: item.industry_name };
            snapshots.set(item.industry_name, {
                ...current,
                score: item.score ?? current.score ?? null,
                change_pct: item.change_pct ?? current.change_pct ?? null,
                money_flow: item.money_flow ?? current.money_flow ?? null,
                industryVolatility: item.industryVolatility ?? current.industryVolatility ?? null,
                stock_count: item.stock_count ?? current.stock_count ?? null,
                marketCapSource: item.marketCapSource ?? current.marketCapSource ?? 'unknown',
            });
        });

        return Array.from(snapshots.values());
    }, [heatmapIndustries, hotIndustries]);

    const rawIndustryAlerts = useMemo(() => {
        const bestByIndustry = new Map();
        const upsertAlert = (alert) => {
            if (!alert?.industry_name) return;
            const existing = bestByIndustry.get(alert.industry_name);
            if (!existing || alert.priority > existing.priority) {
                bestByIndustry.set(alert.industry_name, alert);
            }
        };

        industryAlertSnapshots.forEach((item) => {
            const name = item.industry_name;
            const score = Number(item.score || 0);
            const change = Number(item.change_pct || 0);
            const moneyFlow = Number(item.money_flow || 0);
            const volatility = Number(item.industryVolatility || 0);
            const turnoverRate = Number(item.turnoverRate || 0);

            if (score >= 80 && change >= 2 && moneyFlow > 0) {
                upsertAlert({
                    industry_name: name,
                    kind: 'resonance',
                    title: '强势共振',
                    color: 'red',
                    accent: '#ff7875',
                    summary: `综合得分 ${score.toFixed(1)}，涨幅 ${change.toFixed(2)}%，资金 ${formatIndustryAlertMoneyFlow(moneyFlow)}。`,
                    reason: '热度、价格和资金都在同向增强，适合先看龙头承接。',
                    priority: 120 + score + change + Math.min(moneyFlow / 1e8, 20),
                });
                return;
            }

            if (moneyFlow >= 8e8 && change >= 0.5) {
                upsertAlert({
                    industry_name: name,
                    kind: 'capital_inflow',
                    title: '资金突入',
                    color: 'volcano',
                    accent: '#ff9c6e',
                    summary: `主力净流入 ${formatIndustryAlertMoneyFlow(moneyFlow)}，价格同步转强。`,
                    reason: '短线关注度在升温，适合顺着热点扩散继续看。',
                    priority: 100 + Math.min(moneyFlow / 1e8, 24) + change,
                });
            }

            if (moneyFlow <= -8e8 && change <= -1) {
                upsertAlert({
                    industry_name: name,
                    kind: 'risk_release',
                    title: '风险释放',
                    color: 'green',
                    accent: '#95de64',
                    summary: `主力净流出 ${formatIndustryAlertMoneyFlow(moneyFlow)}，价格承压 ${Math.abs(change).toFixed(2)}%。`,
                    reason: '更适合先看承接与止跌信号，而不是直接追击。',
                    priority: 98 + Math.min(Math.abs(moneyFlow) / 1e8, 24) + Math.abs(change),
                });
            }

            if (volatility >= 4.5 && Math.abs(change) >= 2) {
                upsertAlert({
                    industry_name: name,
                    kind: 'high_volatility',
                    title: '高波动博弈',
                    color: 'gold',
                    accent: '#ffd666',
                    summary: `波动率 ${volatility.toFixed(1)}%，价格振幅已经明显放大。`,
                    reason: '更适合盯节奏和分化，不适合只看静态排行。',
                    priority: 92 + volatility + Math.abs(change),
                });
            }

            if (turnoverRate >= 3.5 && Math.abs(change) >= 1) {
                upsertAlert({
                    industry_name: name,
                    kind: 'rotation_heatup',
                    title: '轮动升温',
                    color: 'blue',
                    accent: '#69c0ff',
                    summary: `换手率 ${turnoverRate.toFixed(1)}%，板块活跃度在抬升。`,
                    reason: '适合直接加入轮动对比，看是不是新一轮资金切换。',
                    priority: 88 + turnoverRate + Math.abs(change),
                });
            }
        });

        return Array.from(bestByIndustry.values())
            .sort((a, b) => b.priority - a.priority)
            .slice(0, 6);
    }, [industryAlertSnapshots]);

    const watchlistAlertByIndustry = useMemo(
        () => new Map(rawIndustryAlerts.map((item) => [item.industry_name, item])),
        [rawIndustryAlerts]
    );

    // eslint-disable-next-line no-unused-vars
    const watchlistEntries = useMemo(() => {
        const rankingCandidates = [...(hotIndustries || []), ...(filteredHotIndustries || [])];
        return watchlistIndustries.map((industryName) => {
            const rankingSnapshot = rankingCandidates.find((item) => item?.industry_name === industryName) || null;
            const heatmapSnapshot = (heatmapIndustries || []).find((item) => item?.name === industryName) || null;
            const replayDiff = replayComparison?.detailsByIndustry?.get(industryName) || null;
            const alert = watchlistAlertByIndustry.get(industryName) || null;

            return {
                industryName,
                score: rankingSnapshot?.score
                    ?? rankingSnapshot?.total_score
                    ?? heatmapSnapshot?.total_score
                    ?? null,
                change_pct: rankingSnapshot?.change_pct
                    ?? heatmapSnapshot?.value
                    ?? null,
                money_flow: rankingSnapshot?.money_flow
                    ?? heatmapSnapshot?.moneyFlow
                    ?? null,
                turnoverRate: heatmapSnapshot?.turnoverRate ?? null,
                volatility: rankingSnapshot?.industryVolatility
                    ?? heatmapSnapshot?.industryVolatility
                    ?? null,
                leadingStock: heatmapSnapshot?.leadingStock || null,
                alert,
                replayDiff,
            };
        });
    }, [filteredHotIndustries, heatmapIndustries, hotIndustries, replayComparison, watchlistAlertByIndustry, watchlistIndustries]);

    // eslint-disable-next-line no-unused-vars
    const watchlistSuggestions = useMemo(() => {
        const seen = new Set(watchlistIndustries);
        const suggestions = [];
        const maybePush = (name) => {
            if (!name || seen.has(name)) return;
            seen.add(name);
            suggestions.push(name);
        };

        if (selectedIndustry) maybePush(selectedIndustry);
        rawIndustryAlerts.slice(0, 4).forEach((item) => maybePush(item.industry_name));
        focusIndustrySuggestions.forEach((name) => maybePush(name));
        return suggestions.slice(0, 5);
    }, [focusIndustrySuggestions, rawIndustryAlerts, selectedIndustry, watchlistIndustries]);

    useEffect(() => {
        if (rawIndustryAlerts.length === 0) return;

        const seenAt = Date.now();
        setIndustryAlertHistory((current) => {
            const next = { ...current };
            let changed = false;

            rawIndustryAlerts.forEach((alert) => {
                const key = `${alert.industry_name}:${alert.kind}`;
                const existing = current[key];
                const subscriptionBucket = getAlertSubscriptionBucket(alert.kind);
                if (!existing) {
                    next[key] = {
                        industry_name: alert.industry_name,
                        kind: alert.kind,
                        title: alert.title,
                        color: alert.color,
                        accent: alert.accent,
                        summary: alert.summary,
                        reason: alert.reason,
                        priority: alert.priority,
                        subscriptionBucket,
                        firstSeenAt: seenAt,
                        lastSeenAt: seenAt,
                        hitCount: 1,
                    };
                    changed = true;
                    return;
                }

                if (existing.lastSeenAt !== seenAt) {
                    next[key] = {
                        ...existing,
                        industry_name: alert.industry_name,
                        kind: alert.kind,
                        title: alert.title,
                        color: alert.color,
                        accent: alert.accent,
                        summary: alert.summary,
                        reason: alert.reason,
                        priority: alert.priority,
                        subscriptionBucket,
                        lastSeenAt: seenAt,
                        hitCount: (existing.hitCount || 1) + 1,
                    };
                    changed = true;
                }
            });

            return changed ? next : current;
        });
    }, [rawIndustryAlerts]);

    const subscribedIndustryAlerts = useMemo(() => {
        const recencyMs = industryAlertRecency === 'session' ? Number.POSITIVE_INFINITY : Number(industryAlertRecency || 15) * 60 * 1000;
        return rawIndustryAlerts
            .map((alert) => {
                const historyKey = `${alert.industry_name}:${alert.kind}`;
                const history = industryAlertHistory[historyKey];
                const firstSeenAt = history?.firstSeenAt || null;
                const isNew = firstSeenAt ? (Date.now() - firstSeenAt) <= recencyMs : false;
                return {
                    ...alert,
                    firstSeenAt,
                    isNew,
                    seenLabel: formatIndustryAlertSeenLabel(firstSeenAt),
                    subscriptionBucket: getAlertSubscriptionBucket(alert.kind),
                };
            })
            .filter((alert) => {
                const scopePass = industryAlertSubscription.scope !== 'watchlist'
                    || watchlistIndustries.includes(alert.industry_name);
                const kindPass = industryAlertSubscription.kinds.includes(alert.subscriptionBucket);
                return scopePass && kindPass;
            });
    }, [industryAlertHistory, industryAlertRecency, industryAlertSubscription, rawIndustryAlerts, watchlistIndustries]);

    const subscribedAlertNewCount = useMemo(
        () => subscribedIndustryAlerts.filter((alert) => alert.isNew).length,
        [subscribedIndustryAlerts]
    );

    const alertTimelineEntries = useMemo(() => {
        const recencyMs = industryAlertRecency === 'session'
            ? Number.POSITIVE_INFINITY
            : Number(industryAlertRecency || 15) * 60 * 1000;

        return Object.values(pruneIndustryAlertHistory(industryAlertHistory))
            .map((entry) => {
                const firstSeenAt = Number(entry?.firstSeenAt || 0) || null;
                const lastSeenAt = Number(entry?.lastSeenAt || firstSeenAt || 0) || null;
                const isNew = firstSeenAt ? (Date.now() - firstSeenAt) <= recencyMs : false;
                const severity = getIndustryAlertSeverity(entry);
                return {
                    ...entry,
                    firstSeenAt,
                    lastSeenAt,
                    isNew,
                    seenLabel: formatIndustryAlertSeenLabel(lastSeenAt),
                    subscriptionBucket: entry?.subscriptionBucket || getAlertSubscriptionBucket(entry?.kind),
                    severity,
                };
            })
            .filter((entry) => {
                const scopePass = industryAlertSubscription.scope !== 'watchlist'
                    || watchlistIndustries.includes(entry.industry_name);
                const kindPass = industryAlertSubscription.kinds.includes(entry.subscriptionBucket);
                if (!scopePass || !kindPass) return false;
                if (industryAlertRule === 'new') return entry.isNew;
                if (industryAlertRule === 'capital') return entry.subscriptionBucket === 'capital';
                if (industryAlertRule === 'risk') return entry.subscriptionBucket === 'risk';
                if (industryAlertRule === 'rotation') return entry.subscriptionBucket === 'rotation';
                return true;
            })
            .sort((a, b) => (b.lastSeenAt || 0) - (a.lastSeenAt || 0))
            .slice(0, 6);
    }, [
        industryAlertHistory,
        industryAlertRecency,
        industryAlertRule,
        industryAlertSubscription,
        watchlistIndustries,
    ]);

    useEffect(() => {
        window.localStorage.setItem(INDUSTRY_ALERT_BADGE_STORAGE_KEY, String(subscribedAlertNewCount || 0));
        window.dispatchEvent(new CustomEvent(INDUSTRY_ALERT_BADGE_EVENT, {
            detail: { count: subscribedAlertNewCount || 0 },
        }));
    }, [subscribedAlertNewCount]);

    const industryAlerts = useMemo(() => {
        const filteredAlerts = subscribedIndustryAlerts.filter((alert) => {
            if (industryAlertRule === 'new') return alert.isNew;
            if (industryAlertRule === 'capital') return ['capital_inflow', 'resonance'].includes(alert.kind);
            if (industryAlertRule === 'risk') return alert.kind === 'risk_release';
            if (industryAlertRule === 'rotation') return ['rotation_heatup', 'high_volatility'].includes(alert.kind);
            return true;
        });

        if (filteredAlerts.length > 0) {
            return filteredAlerts
                .sort((a, b) => Number(b.isNew) - Number(a.isNew) || b.priority - a.priority)
                .slice(0, 4);
        }

        if (rawIndustryAlerts.length > 0) {
            return [];
        }

        return focusIndustrySuggestions.slice(0, 3).map((industry, index) => ({
            industry_name: industry,
            kind: 'watchlist_seed',
            title: index === 0 ? '优先观察' : '关注备选',
            color: 'processing',
            accent: '#69c0ff',
            summary: `${industry} 当前处在热度聚合视野里，适合先加入观察列表。`,
            reason: '可以先看研究焦点、龙头股和行业详情三条链路。',
            priority: 60 - index,
            firstSeenAt: null,
            isNew: false,
            seenLabel: '等待下一次异动',
        }));
    }, [focusIndustrySuggestions, industryAlertRule, rawIndustryAlerts, subscribedIndustryAlerts]);

    const industryAlertsWithSeverity = useMemo(
        () => industryAlerts.map((alert) => ({ ...alert, severity: getIndustryAlertSeverity(alert) })),
        [industryAlerts]
    );
    const industryActionPosture = useMemo(
        () => buildIndustryActionPosture({
            alerts: industryAlertsWithSeverity,
            newCount: subscribedAlertNewCount,
            focusIndustrySuggestions,
            watchlistIndustries,
            selectedIndustry,
        }),
        [focusIndustrySuggestions, industryAlertsWithSeverity, selectedIndustry, subscribedAlertNewCount, watchlistIndustries]
    );

    const requestDesktopAlertPermission = useCallback(async () => {
        if (typeof window === 'undefined' || typeof Notification === 'undefined') {
            message.warning('当前浏览器不支持桌面通知');
            return;
        }
        try {
            const permission = await Notification.requestPermission();
            const granted = permission === 'granted';
            setDesktopAlertNotifications(granted);
            if (granted) {
                new Notification('行业异动提醒已启用', {
                    body: '后续会优先推送高严重等级的新增行业提醒。',
                });
                message.success('桌面通知已开启');
            } else {
                message.warning('桌面通知未开启');
            }
        } catch (error) {
            console.warn('Failed to request industry alert notification permission:', error);
            message.warning('无法开启桌面通知');
        }
    }, [message]);

    useEffect(() => {
        if (!desktopAlertNotifications || typeof window === 'undefined' || typeof Notification === 'undefined') {
            return;
        }
        if (Notification.permission !== 'granted') {
            return;
        }
        industryAlertsWithSeverity
            .filter((alert) => alert.isNew && alert.severity?.level !== 'low')
            .slice(0, 2)
            .forEach((alert) => {
                const notifyKey = `industry-alert-notified:${alert.industry_name}:${alert.kind}:${alert.firstSeenAt || 'na'}`;
                if (window.sessionStorage.getItem(notifyKey)) {
                    return;
                }
                window.sessionStorage.setItem(notifyKey, 'true');
                new Notification(`行业异动: ${alert.industry_name}`, {
                    body: `${alert.title} · ${alert.summary}`,
                });
            });
    }, [desktopAlertNotifications, industryAlertsWithSeverity]);

    // 热门行业表格列
    const hotIndustryColumns = [
        {
            title: '排名',
            dataIndex: 'rank',
            key: 'rank',
            width: 48,
            render: (rank) => {
                const medals = ['🥇', '🥈', '🥉'];
                if (rank <= 3) return <span style={{ fontSize: 16 }}>{medals[rank - 1]}</span>;
                return <span style={{ color: PANEL_MUTED, fontSize: 12, fontWeight: 600 }}>{rank}</span>;
            }
        },
        {
            title: '行业',
            dataIndex: 'industry_name',
            key: 'industry_name',
            render: (name, record) => {
                const sourceMeta = getMarketCapBadgeMeta(record.marketCapSource);
                const volatilityMeta = getIndustryVolatilityMeta(record.industryVolatility, record.industryVolatilitySource);
                return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <Button
                            type="link"
                            size="small"
                            onClick={() => handleIndustryClick(name)}
                            style={{ padding: 0, height: 'auto', width: 'fit-content', fontWeight: 600, fontSize: 13 }}
                        >
                            {name}
                        </Button>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            <Tag
                                color={sourceMeta.color}
                                style={{ margin: 0, width: 'fit-content', fontSize: 10, lineHeight: '15px', paddingInline: 6, cursor: 'pointer', borderRadius: 999 }}
                                onClick={() => jumpToMarketCapFilter(sourceMeta.filter)}
                            >
                                {sourceMeta.label}
                            </Tag>
                            {volatilityMeta.value > 0 && (
                                <Tooltip title={`区间波动率 ${volatilityMeta.value.toFixed(2)}% · ${volatilityMeta.sourceLabel}`}>
                                    <Tag color={volatilityMeta.color} style={{ margin: 0, width: 'fit-content', fontSize: 10, lineHeight: '15px', paddingInline: 6, borderRadius: 999 }}>
                                        {volatilityMeta.label}
                                    </Tag>
                                </Tooltip>
                            )}
                        </div>
                    </div>
                );
            }
        },
        {
            title: '综合得分',
            dataIndex: 'score',
            key: 'score',
            width: 82,
            render: (score, record) => (
                <Button
                    type="link"
                    size="small"
                    data-testid="industry-score-radar-trigger"
                    onClick={() => setScoreRadarRecord(record)}
                    style={{
                        padding: 0,
                        height: 'auto',
                        minWidth: 0,
                        fontWeight: 700,
                        fontSize: 13,
                        color: getIndustryScoreTone(score),
                    }}
                >
                    {Number(score || 0).toFixed(2)}
                </Button>
            )
        },
        {
            title: '涨跌幅',
            dataIndex: 'change_pct',
            key: 'change_pct',
            width: 84,
            sorter: (a, b) => a.change_pct - b.change_pct,
            render: (value) => (
                <span style={{ color: value >= 0 ? '#cf1322' : '#3f8600', fontWeight: 700, fontSize: 13 }}>
                    {value >= 0 ? '+' : ''}{(value || 0).toFixed(2)}%
                </span>
            )
        },
        {
            title: '走势',
            dataIndex: 'mini_trend',
            key: 'mini_trend',
            width: 98,
            render: (points, record) => (
                <Tooltip title={`${record.industry_name} 近5日相对走势`}>
                    <div style={{ width: 88 }}>
                        <MiniSparkline points={points} ariaLabel={`${record.industry_name} 近5日走势`} />
                    </div>
                </Tooltip>
            )
        },
        {
            title: '资金流向',
            dataIndex: 'money_flow',
            key: 'money_flow',
            width: 92,
            sorter: (a, b) => (a.money_flow || 0) - (b.money_flow || 0),
            render: (value) => {
                const displayValue = (value || 0) / 100000000;
                return (
                    <span style={{ color: displayValue >= 0 ? '#cf1322' : '#3f8600', fontSize: 12 }}>
                        {displayValue >= 0 ? '+' : ''}{displayValue.toFixed(2)}亿
                    </span>
                );
            }
        },
        {
            title: '动量',
            dataIndex: 'momentum',
            key: 'momentum',
            width: 80,
            sorter: (a, b) => (a.momentum || 0) - (b.momentum || 0),
            render: (value) => {
                const v = value || 0;
                return (
                    <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600', fontSize: 11, fontWeight: 600 }}>
                        {v >= 0 ? '↑' : '↓'}{Math.abs(v).toFixed(2)}
                    </span>
                );
            }
        },
        {
            title: '波动率',
            dataIndex: 'industryVolatility',
            key: 'industryVolatility',
            width: 110,
            sorter: (a, b) => (a.industryVolatility || 0) - (b.industryVolatility || 0),
            render: (value, record) => {
                const meta = getIndustryVolatilityMeta(value, record.industryVolatilitySource);
                if (!meta.value) return <span style={{ color: PANEL_MUTED }}>-</span>;
                return (
                    <Tooltip title={`区间波动率 ${meta.value.toFixed(2)}% · ${meta.sourceLabel}`}>
                        <Tag color={meta.color} style={{ margin: 0, borderRadius: 999, fontSize: 10, paddingInline: 6 }}>
                            {meta.label} {meta.value.toFixed(1)}%
                        </Tag>
                    </Tooltip>
                );
            }
        },
        {
            title: '市值(亿)',
            dataIndex: 'total_market_cap',
            key: 'total_market_cap',
            width: 82,
            sorter: (a, b) => (a.total_market_cap || 0) - (b.total_market_cap || 0),
            render: (value) => (
                <span style={{ color: TEXT_SECONDARY, fontSize: 12 }}>
                    {value ? ((value || 0) / 100000000).toFixed(0) : '-'}
                </span>
            )
        },
        {
            title: '成分股',
            dataIndex: 'stock_count',
            key: 'stock_count',
            width: 64,
            sorter: (a, b) => (a.stock_count || 0) - (b.stock_count || 0),
            render: (value) => <span style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{value || 0}</span>,
        },

        {
            title: '操作',
            key: 'action',
            width: 86,
            render: (_, record) => (
                <Space size={8}>
                    <Button className="industry-inline-link" type="link" size="small" onClick={() => handleIndustryClick(record.industry_name)} style={{ padding: 0, height: 'auto', fontSize: 12 }}>详情</Button>
                    <Button className="industry-inline-link" type="link" size="small" onClick={() => handleAddToComparison(record.industry_name)} style={{ padding: 0, height: 'auto', color: 'var(--accent-secondary)', fontSize: 12 }}>对比</Button>
                </Space>
            )
        }
    ];

    // 行业成分股表格列
    const stockColumns = [
        {
            title: '排名',
            dataIndex: 'rank',
            key: 'rank',
            width: 55
        },
        {
            title: '代码',
            dataIndex: 'symbol',
            key: 'symbol',
            width: 80,
            render: (symbol) => <Tag color="blue">{symbol}</Tag>
        },
        {
            title: '名称',
            dataIndex: 'name',
            key: 'name',
            width: 100
        },
        {
            title: '得分',
            dataIndex: 'total_score',
            key: 'total_score',
            width: 80,
            render: (score) => {
                if (score === null || score === undefined || Number(score) <= 0) {
                    return '-';
                }
                return (
                    <Tooltip title={`综合评分 ${Number(score).toFixed(1)}`}>
                        <span style={{ fontWeight: 700, color: getIndustryScoreTone(score) }}>
                            {Number(score).toFixed(1)}
                        </span>
                    </Tooltip>
                );
            }
        },
        {
            title: '涨跌幅',
            dataIndex: 'change_pct',
            key: 'change_pct',
            width: 90,
            render: (value) => {
                if (value === null || value === undefined) {
                    return '-';
                }
                return (
                    <span style={{ color: value >= 0 ? '#cf1322' : '#3f8600' }}>
                        {value >= 0 ? '+' : ''}{value.toFixed(2)}%
                    </span>
                );
            }
        },
        {
            title: '主力净流入',
            dataIndex: 'money_flow',
            key: 'money_flow',
            width: 110,
            render: (value) => (
                value === null || value === undefined
                    ? '-'
                    : (
                        <span style={{ color: Number(value) >= 0 ? '#cf1322' : '#3f8600' }}>
                            {formatIndustryAlertMoneyFlow(Number(value))}
                        </span>
                    )
            )
        },
        {
            title: '换手率',
            dataIndex: 'turnover_rate',
            key: 'turnover_rate',
            width: 86,
            render: (_, record) => {
                const value = record.turnover_rate ?? record.turnover;
                return value === null || value === undefined || Number.isNaN(Number(value))
                    ? '-'
                    : `${Number(value).toFixed(2)}%`;
            }
        },
        {
            title: '市值(亿)',
            dataIndex: 'market_cap',
            key: 'market_cap',
            width: 90,
            render: (value) => (
                value === null || value === undefined ? '-' : (value / 100000000).toFixed(1)
            )
        },
        {
            title: 'PE',
            dataIndex: 'pe_ratio',
            key: 'pe_ratio',
            width: 70,
            render: (value) => (
                value === null || value === undefined || value <= 0 ? '-' : value.toFixed(1)
            )
        }
    ];

    // 渲染聚类分析
    const renderClusters = () => {
        if (loadingClusters) {
            return <Spin />;
        }

        if (clusterError && !clusters) {
            return (
                <Empty description={clusterError}>
                    <Button
                        className="industry-empty-action"
                        type="primary"
                        onClick={() => loadClusters(false)}
                        icon={<ReloadOutlined />}
                    >
                        重试
                    </Button>
                </Empty>
            );
        }

        if (!clusters) {
            return (
                <Button className="industry-empty-action" onClick={() => loadClusters(false)} icon={<BranchesOutlined />}>
                    开始聚类分析
                </Button>
            );
        }

        return (
            <div>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                    {Object.entries(clusters.cluster_stats || {}).map(([idx, stats]) => {
                        const isHot = parseInt(idx) === clusters.hot_cluster;
                        return (
                            <Col span={12} key={idx}>
                                <Card
                                    size="small"
                                    title={
                                        <span>
                                            {isHot && (
                                                <FireOutlined style={{ color: '#ff4d4f', marginRight: 4 }} />
                                            )}
                                            {isHot ? '🔥 热门簇' : `簇 ${parseInt(idx) + 1}`}
                                        </span>
                                    }
                                    style={{
                                        borderColor: isHot ? '#ff4d4f' : undefined,
                                        boxShadow: isHot ? '0 0 8px rgba(255,77,79,0.3)' : undefined
                                    }}
                                >
                                    <Row gutter={8}>
                                        <Col span={12}>
                                            <Statistic
                                                title="平均动量"
                                                value={Math.abs(stats.avg_momentum) < 0.005 ? '0.00' : stats.avg_momentum?.toFixed(2)}
                                                suffix="%"
                                                valueStyle={{
                                                    color: stats.avg_momentum >= 0 ? '#cf1322' : '#3f8600',
                                                    fontSize: 14
                                                }}
                                            />
                                        </Col>
                                        <Col span={12}>
                                            <Statistic
                                                title="平均资金强度"
                                                value={Math.abs(stats.avg_flow) < 0.005 ? '0.00' : stats.avg_flow?.toFixed(2)}
                                                valueStyle={{
                                                    color: (stats.avg_flow || 0) >= 0 ? '#cf1322' : '#3f8600',
                                                    fontSize: 14
                                                }}
                                            />
                                        </Col>
                                    </Row>
                                    <div style={{ marginTop: 8 }}>
                                        <div style={{ color: PANEL_MUTED, fontSize: 12, marginBottom: 4 }}>
                                            行业数: {stats.count}
                                        </div>
                                        <div>
                                            {(stats.industries || []).slice(0, 4).map(ind => (
                                                <Tag
                                                    key={ind}
                                                    size="small"
                                                    style={{ cursor: 'pointer', marginBottom: 4 }}
                                                    onClick={() => handleIndustryClick(ind)}
                                                >
                                                    {ind}
                                                </Tag>
                                            ))}
                                            {(stats.industries?.length || 0) > 4 && (
                                                <Tag size="small" style={{ color: PANEL_MUTED }}>
                                                    +{stats.industries.length - 4}
                                                </Tag>
                                            )}
                                        </div>
                                    </div>
                                </Card>
                            </Col>
                        );
                    })}
                </Row>
            </div>
        );
    };

    // 聚类散点图
    const CLUSTER_COLORS = ['#ff4d4f', '#1890ff', '#52c41a', '#faad14', '#eb2f96'];

    const renderClusterScatterChart = () => {
        if (loadingClusters && !clusters) {
            return (
                <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>
                        聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span>
                    </div>
                    <div
                        style={{
                            minHeight: 280,
                            borderRadius: 12,
                            border: PANEL_BORDER,
                            background: PANEL_SURFACE,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            gap: 10,
                        }}
                    >
                        <Spin />
                        <div style={{ fontSize: 12, color: PANEL_MUTED }}>聚类分析计算中，首次加载可能需要几秒</div>
                    </div>
                </div>
            );
        }

        if (!clusters) return null;

        const scatterData = (clusters.points || []).map(point => ({
            name: point.industry_name,
            cluster: point.cluster,
            x: point.weighted_change || 0,
            y: point.flow_strength || 0,
        }));
        const clusterKeys = Object.keys(clusters.cluster_stats || {}).length > 0
            ? Object.keys(clusters.cluster_stats || {}).map(k => parseInt(k))
            : [...new Set(scatterData.map(d => d.cluster))];

        if (scatterData.length === 0) {
            return (
                <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>
                        聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span>
                    </div>
                    <Empty description="当前暂无可展示的聚类点位" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
            );
        }

        return (
            <div style={{ marginTop: 16 }}>
                <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span></div>
                <div style={{ position: 'relative', borderRadius: 12, overflow: 'hidden' }}>
                    <div style={{ position: 'absolute', top: 8, left: 12, zIndex: 1 }}>
                        <Tag color="red" style={{ margin: 0, borderRadius: 999 }}>强势流入</Tag>
                    </div>
                    <div style={{ position: 'absolute', top: 8, right: 12, zIndex: 1 }}>
                        <Tag color="orange" style={{ margin: 0, borderRadius: 999 }}>弱势流入</Tag>
                    </div>
                    <div style={{ position: 'absolute', bottom: 8, left: 12, zIndex: 1 }}>
                        <Tag color="green" style={{ margin: 0, borderRadius: 999 }}>强势撤退</Tag>
                    </div>
                    <div style={{ position: 'absolute', bottom: 8, right: 12, zIndex: 1 }}>
                        <Tag color="blue" style={{ margin: 0, borderRadius: 999 }}>弱势修复</Tag>
                    </div>
                    <ResponsiveContainer width="100%" height={280}>
                        <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis
                                type="number"
                                dataKey="x"
                                name="动量"
                                tick={{ fontSize: 11 }}
                                tickFormatter={v => `${v.toFixed(1)}%`}
                            />
                            <YAxis
                                type="number"
                                dataKey="y"
                                name="资金强度"
                                tick={{ fontSize: 11 }}
                                domain={[-1.05, 1.05]}
                                tickFormatter={v => `${v.toFixed(1)}`}
                            />
                            <ReferenceLine x={0} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />
                            <ReferenceLine y={0} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />
                            <RechartsTooltip
                                formatter={(value, name) => [
                                    typeof value === 'number' ? value.toFixed(2) : value,
                                    name === 'x' ? '动量' : name === 'y' ? '资金强度' : name
                                ]}
                                labelFormatter={() => ''}
                                content={({ active, payload }) => {
                                    if (active && payload && payload.length) {
                                        const d = payload[0]?.payload;
                                        return (
                                            <div style={{
                                                background: 'rgba(0,0,0,0.75)',
                                                color: '#fff',
                                                padding: '6px 10px',
                                                borderRadius: 4,
                                                fontSize: 12
                                            }}>
                                                <div style={{ fontWeight: 'bold' }}>{d?.name}</div>
                                                <div>动量: {d?.x?.toFixed(2)}%</div>
                                                <div>资金强度: {d?.y?.toFixed(2)}</div>
                                            </div>
                                        );
                                    }
                                    return null;
                                }}
                            />
                            {clusterKeys.map(clusterIdx => {
                                const isHot = clusterIdx === clusters.hot_cluster;
                                const clusterData = scatterData.filter(d => d.cluster === clusterIdx);
                                return (
                                    <Scatter
                                        key={clusterIdx}
                                        name={isHot ? '🔥 热门簇' : `簇 ${clusterIdx + 1}`}
                                        data={clusterData}
                                        fill={CLUSTER_COLORS[clusterIdx % CLUSTER_COLORS.length]}
                                        shape={(props) => {
                                            const selected = selectedClusterPoint?.name === props?.payload?.name;
                                            return (
                                                <circle
                                                    cx={props.cx}
                                                    cy={props.cy}
                                                    r={selected ? 7 : 5}
                                                    fill={props.fill}
                                                    stroke={selected ? '#111827' : '#ffffff'}
                                                    strokeWidth={selected ? 2.5 : 1.5}
                                                    style={{ cursor: 'pointer' }}
                                                />
                                            );
                                        }}
                                        onClick={(payload) => {
                                            const nextPoint = payload?.payload || payload;
                                            if (nextPoint?.name) {
                                                setSelectedClusterPoint(nextPoint);
                                            }
                                        }}
                                    />
                                );
                            })}
                        </ScatterChart>
                    </ResponsiveContainer>
                </div>
                {selectedClusterPoint && (
                    <Card
                        size="small"
                        style={{ marginTop: 12, borderRadius: 12, border: '1px solid rgba(24,144,255,0.18)' }}
                        styles={{ body: { padding: '12px 14px' } }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <span style={{ fontSize: 15, fontWeight: 700, color: TEXT_PRIMARY }}>{selectedClusterPoint.name}</span>
                                    <Tag color={selectedClusterPoint.cluster === clusters.hot_cluster ? 'red' : 'blue'} style={{ margin: 0, borderRadius: 999 }}>
                                        {selectedClusterPoint.cluster === clusters.hot_cluster ? '热门簇' : `簇 ${selectedClusterPoint.cluster + 1}`}
                                    </Tag>
                                </div>
                                <div style={{ fontSize: 12, color: PANEL_MUTED }}>
                                    动量 {selectedClusterPoint.x?.toFixed(2)}% · 资金强度 {selectedClusterPoint.y?.toFixed(2)}
                                </div>
                            </div>
                            <Space size={8} wrap>
                                <Button size="small" type="primary" onClick={() => setSelectedIndustry(selectedClusterPoint.name)}>
                                    聚焦
                                </Button>
                                <Button size="small" onClick={() => handleIndustryClick(selectedClusterPoint.name)}>
                                    查看详情
                                </Button>
                                <Button size="small" onClick={() => handleAddToComparison(selectedClusterPoint.name)}>
                                    加入对比
                                </Button>
                            </Space>
                        </div>
                    </Card>
                )}
            </div>
        );
    };

    const activeHeatmapStateTags = [];
    if (marketCapFilter !== INDUSTRY_URL_DEFAULTS.marketCapFilter) {
        activeHeatmapStateTags.push({ key: 'market_cap_filter', label: '来源', value: INDUSTRY_FILTER_LABELS[marketCapFilter] || marketCapFilter });
    }
    if (heatmapViewState.timeframe !== INDUSTRY_URL_DEFAULTS.timeframe) {
        activeHeatmapStateTags.push({ key: 'timeframe', label: '周期', value: INDUSTRY_TIMEFRAME_LABELS[heatmapViewState.timeframe] || `${heatmapViewState.timeframe}日` });
    }
    if (heatmapViewState.sizeMetric !== INDUSTRY_URL_DEFAULTS.sizeMetric) {
        activeHeatmapStateTags.push({ key: 'size_metric', label: '大小', value: INDUSTRY_SIZE_METRIC_LABELS[heatmapViewState.sizeMetric] || heatmapViewState.sizeMetric });
    }
    if (heatmapViewState.colorMetric !== INDUSTRY_URL_DEFAULTS.colorMetric) {
        activeHeatmapStateTags.push({ key: 'color_metric', label: '颜色', value: INDUSTRY_COLOR_METRIC_LABELS[heatmapViewState.colorMetric] || heatmapViewState.colorMetric });
    }
    if (heatmapViewState.displayCount !== INDUSTRY_URL_DEFAULTS.displayCount) {
        activeHeatmapStateTags.push({ key: 'display_count', label: '范围', value: heatmapViewState.displayCount === 0 ? '全部' : `Top ${heatmapViewState.displayCount}` });
    }
    if (heatmapViewState.searchTerm !== INDUSTRY_URL_DEFAULTS.searchTerm) {
        activeHeatmapStateTags.push({ key: 'search', label: '搜索', value: heatmapViewState.searchTerm });
    }
    if (Array.isArray(heatmapLegendRange) && heatmapLegendRange.length === 2) {
        activeHeatmapStateTags.push({
            key: 'legend_range',
            label: '色阶',
            value: `${Number(heatmapLegendRange[0]).toFixed(1)} ~ ${Number(heatmapLegendRange[1]).toFixed(1)}`,
        });
    }
    const hasActiveHeatmapState = activeHeatmapStateTags.length > 0;

    const activeRankingStateTags = [];
    if (rankType !== INDUSTRY_URL_DEFAULTS.rankType) {
        activeRankingStateTags.push({ key: 'rank_type', label: '榜单', value: INDUSTRY_RANK_TYPE_LABELS[rankType] || rankType });
    }
    if (sortBy !== INDUSTRY_URL_DEFAULTS.sortBy) {
        activeRankingStateTags.push({ key: 'sort_by', label: '排序', value: INDUSTRY_RANK_SORT_LABELS[sortBy] || sortBy });
    }
    if (lookbackDays !== INDUSTRY_URL_DEFAULTS.lookbackDays) {
        activeRankingStateTags.push({ key: 'lookback', label: '周期', value: `近${lookbackDays}日` });
    }
    if (volatilityFilter !== INDUSTRY_URL_DEFAULTS.volatilityFilter) {
        activeRankingStateTags.push({ key: 'volatility_filter', label: '波动', value: INDUSTRY_VOLATILITY_FILTER_LABELS[volatilityFilter] || volatilityFilter });
    }
    if (rankingMarketCapFilter !== INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter) {
        activeRankingStateTags.push({ key: 'market_cap_filter', label: '市值来源', value: INDUSTRY_RANKING_MARKET_CAP_FILTER_LABELS[rankingMarketCapFilter] || rankingMarketCapFilter });
    }

    const tabItems = [
        {
            label: '热力图',
            key: 'heatmap',
            children: (
                <IndustryHeatmap
                    onIndustryClick={handleIndustryClick}
                    onDataLoad={handleHeatmapDataLoad}
                    onLeadingStockClick={handleLeadingStockClick}
                    replaySnapshot={activeReplaySnapshot}
                    marketCapFilter={marketCapFilter}
                    onClearMarketCapFilter={() => setMarketCapFilter('all')}
                    onSelectMarketCapFilter={jumpToMarketCapFilter}
                    timeframeValue={heatmapViewState.timeframe}
                    sizeMetricValue={heatmapViewState.sizeMetric}
                    colorMetricValue={heatmapViewState.colorMetric}
                    displayCountValue={heatmapViewState.displayCount}
                    searchTermValue={heatmapViewState.searchTerm}
                    legendRangeValue={heatmapLegendRange}
                    onTimeframeChange={(value) => setHeatmapViewState(prev => ({ ...prev, timeframe: value }))}
                    onSizeMetricChange={(value) => setHeatmapViewState(prev => ({ ...prev, sizeMetric: value }))}
                    onColorMetricChange={(value) => setHeatmapViewState(prev => ({ ...prev, colorMetric: value }))}
                    onDisplayCountChange={(value) => setHeatmapViewState(prev => ({ ...prev, displayCount: value }))}
                    onSearchTermChange={(value) => setHeatmapViewState(prev => ({ ...prev, searchTerm: value }))}
                    onLegendRangeChange={setHeatmapLegendRange}
                    focusControlKey={focusedHeatmapControlKey}
                    showStats={false}
                    onToggleFullscreen={() => setHeatmapFullscreen((current) => !current)}
                    isFullscreen={false}
                />
            )
        },
        {
            label: '排行榜',
            key: 'ranking',
            children: (
                <IndustryRankingPanel
                    rankType={rankType}
                    onRankTypeChange={setRankType}
                    sortBy={sortBy}
                    onSortByChange={setSortBy}
                    lookbackDays={lookbackDays}
                    onLookbackDaysChange={setLookbackDays}
                    volatilityFilter={volatilityFilter}
                    onVolatilityFilterChange={setVolatilityFilter}
                    rankingMarketCapFilter={rankingMarketCapFilter}
                    onRankingMarketCapFilterChange={setRankingMarketCapFilter}
                    loadingHot={loadingHot}
                    focusedRankingControlKey={focusedRankingControlKey}
                    filteredHotIndustries={filteredHotIndustries}
                    hotIndustryColumns={hotIndustryColumns}
                    onReload={() => loadHotIndustries(50, rankType, sortBy, lookbackDays)}
                    onIndustryClick={handleIndustryClick}
                    activeRankingStateTags={activeRankingStateTags}
                    onFocusRankingControl={focusRankingControl}
                    onClearRankingStateTag={clearRankingStateTag}
                    onResetRankingViewState={resetRankingViewState}
                    panelSurface={PANEL_SURFACE}
                    panelBorder={PANEL_BORDER}
                    panelShadow={PANEL_SHADOW}
                    panelMuted={PANEL_MUTED}
                />
            )
        },
        {
            label: '聚类分析',
            key: 'clusters',
            children: (
                <Card
                    title="行业聚类分析"
                    extra={
                        <Space size={8} wrap>
                            <Select
                                value={clusterCount}
                                onChange={setClusterCount}
                                size="small"
                                style={{ width: 108 }}
                                disabled={loadingClusters}
                            >
                                <Option value={3}>3 个聚类</Option>
                                <Option value={4}>4 个聚类</Option>
                                <Option value={5}>5 个聚类</Option>
                                <Option value={6}>6 个聚类</Option>
                            </Select>
                            {clusters && (
                                <Button
                                    className="industry-inline-link"
                                    icon={<ReloadOutlined />}
                                    onClick={() => loadClusters(false)}
                                    size="small"
                                >
                                    重新分析
                                </Button>
                            )}
                        </Space>
                    }
                >
                    {renderClusters()}
                    {renderClusterScatterChart()}
                </Card>
            )
        },
        {
            label: '轮动对比',
            key: 'rotation',
            children: (
                <IndustryRotationChart
                    initialIndustries={comparisonIndustries.length > 0
                        ? comparisonIndustries
                        : (hotIndustries || []).slice(0, 3).map(i => i.industry_name)
                    }
                />
            )
        }
    ];

    return (
        <Layout style={{ padding: 24, background: 'var(--bg-primary)', minHeight: '100vh' }}>
            <Row gutter={[24, 24]}>
                {/* 左侧：热力图和热门行业 */}
                <Col xs={24} lg={16}>
                    <IndustryMarketSnapshotBar
                        heatmapSummary={heatmapSummary}
                        focusedHeatmapControlKey={focusedHeatmapControlKey}
                        marketCapFilter={marketCapFilter}
                        onIndustryClick={handleIndustryClick}
                        onToggleMarketCapFilter={toggleMarketCapFilter}
                        onResetMarketCapFilter={() => setMarketCapFilter('all')}
                        statusIndicator={<ApiStatusIndicator />}
                    />

                    <IndustryReplayPanel
                        heatmapReplaySnapshots={heatmapReplaySnapshots}
                        activeReplaySnapshot={activeReplaySnapshot}
                        latestReplaySnapshot={latestReplaySnapshot}
                        replayWindow={replayWindow}
                        setReplayWindow={setReplayWindow}
                        heatmapReplayWindowOptions={HEATMAP_REPLAY_WINDOW_OPTIONS}
                        comparisonBaseSnapshotId={comparisonBaseSnapshotId}
                        setComparisonBaseSnapshotId={setComparisonBaseSnapshotId}
                        filteredReplaySnapshots={filteredReplaySnapshots}
                        replayTargetSnapshot={replayTargetSnapshot}
                        formatReplaySnapshotTime={formatReplaySnapshotTime}
                        industryTimeframeLabels={INDUSTRY_TIMEFRAME_LABELS}
                        setActiveTab={setActiveTab}
                        setSelectedReplaySnapshotId={setSelectedReplaySnapshotId}
                        setHeatmapViewState={setHeatmapViewState}
                        setMarketCapFilter={setMarketCapFilter}
                        panelSurface={PANEL_SURFACE}
                        panelBorder={PANEL_BORDER}
                        panelShadow={PANEL_SHADOW}
                        panelMuted={PANEL_MUTED}
                        textPrimary={TEXT_PRIMARY}
                        textSecondary={TEXT_SECONDARY}
                        replayComparison={replayComparison}
                        activeReplayDiffIndustry={activeReplayDiffIndustry}
                        handleReplayDiffIndustrySelect={handleReplayDiffIndustrySelect}
                        handleIndustryClick={handleIndustryClick}
                        getIndustryScoreTone={getIndustryScoreTone}
                        formatReplayDelta={formatReplayDelta}
                        replayIndustryDiffDetail={replayIndustryDiffDetail}
                        watchlistIndustries={watchlistIndustries}
                        toggleWatchlistIndustry={toggleWatchlistIndustry}
                        formatReplayMetricPercent={formatReplayMetricPercent}
                        formatReplayMetricMoney={formatReplayMetricMoney}
                    />

                    <Card
                        size="small"
                        style={{
                            marginBottom: 12,
                            background: industryActionPosture.level === 'warning'
                                ? 'linear-gradient(180deg, rgba(250, 173, 20, 0.10) 0%, rgba(255,255,255,0.72) 100%)'
                                : industryActionPosture.level === 'info'
                                    ? 'linear-gradient(180deg, rgba(22, 119, 255, 0.08) 0%, rgba(255,255,255,0.72) 100%)'
                                    : 'linear-gradient(180deg, rgba(82, 196, 26, 0.08) 0%, rgba(255,255,255,0.72) 100%)',
                            border: industryActionPosture.level === 'warning'
                                ? '1px solid rgba(250, 173, 20, 0.35)'
                                : industryActionPosture.level === 'info'
                                    ? '1px solid rgba(22, 119, 255, 0.24)'
                                    : '1px solid rgba(82, 196, 26, 0.22)',
                        }}
                    >
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            <div style={{ fontSize: 11, color: PANEL_MUTED, fontWeight: 700, letterSpacing: '0.04em' }}>行业动作姿势</div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: TEXT_PRIMARY }}>{industryActionPosture.title}</div>
                            <div style={{ fontSize: 12, lineHeight: 1.7, color: TEXT_PRIMARY }}>{industryActionPosture.actionHint}</div>
                            <div style={{ fontSize: 11, lineHeight: 1.7, color: TEXT_SECONDARY }}>{industryActionPosture.reason}</div>
                        </div>
                    </Card>

                    <IndustryAlertsPanel
                        industryAlertsWithSeverity={industryAlertsWithSeverity}
                        rawIndustryAlerts={rawIndustryAlerts}
                        focusIndustrySuggestions={focusIndustrySuggestions}
                        subscribedAlertNewCount={subscribedAlertNewCount}
                        industryAlertSubscription={industryAlertSubscription}
                        desktopAlertNotifications={desktopAlertNotifications}
                        industryAlertRule={industryAlertRule}
                        setIndustryAlertRule={setIndustryAlertRule}
                        industryAlertRecency={industryAlertRecency}
                        setIndustryAlertRecency={setIndustryAlertRecency}
                        industryAlertKindOptions={INDUSTRY_ALERT_KIND_OPTIONS}
                        industryAlertRecencyOptions={INDUSTRY_ALERT_RECENCY_OPTIONS}
                        setIndustryAlertSubscription={setIndustryAlertSubscription}
                        requestDesktopAlertPermission={requestDesktopAlertPermission}
                        toggleWatchlistIndustry={toggleWatchlistIndustry}
                        watchlistIndustries={watchlistIndustries}
                        selectedIndustry={selectedIndustry}
                        setSelectedIndustry={setSelectedIndustry}
                        handleIndustryClick={handleIndustryClick}
                        handleAddToComparison={handleAddToComparison}
                        alertTimelineEntries={alertTimelineEntries}
                        formatIndustryAlertSeenLabel={formatIndustryAlertSeenLabel}
                        message={message}
                    />

                    <IndustryHeatmapStateBar
                        visible={activeTab === 'heatmap' && hasActiveHeatmapState}
                        activeHeatmapStateTags={activeHeatmapStateTags}
                        onFocusHeatmapControl={focusHeatmapControl}
                        onClearHeatmapStateTag={clearHeatmapStateTag}
                        onResetHeatmapViewState={resetHeatmapViewState}
                        panelSurface={PANEL_SURFACE}
                        panelBorder={PANEL_BORDER}
                        panelShadow={PANEL_SHADOW}
                        panelMuted={PANEL_MUTED}
                    />

                    <IndustrySavedViewsPanel
                        draftName={savedViewDraftName}
                        onDraftNameChange={setSavedViewDraftName}
                        onSave={saveCurrentIndustryView}
                        savedViews={savedIndustryViews}
                        onApply={applySavedIndustryView}
                        onOverwrite={overwriteSavedIndustryView}
                        onRemove={removeSavedIndustryView}
                    />

                    <Tabs
                        activeKey={activeTab}
                        onChange={setActiveTab}
                        items={tabItems}
                    />
                </Col>

                {/* 右侧：龙头股推荐 */}
                <Col xs={24} lg={8}>
                    {(watchlistEntries.length > 0 || watchlistSuggestions.length > 0) && (
                        <IndustryWatchlistPanel
                            watchlistEntries={watchlistEntries}
                            watchlistSuggestions={watchlistSuggestions}
                            selectedIndustry={selectedIndustry}
                            maxWatchlistIndustries={MAX_WATCHLIST_INDUSTRIES}
                            toggleWatchlistIndustry={toggleWatchlistIndustry}
                            setSelectedIndustry={setSelectedIndustry}
                            handleIndustryClick={handleIndustryClick}
                            handleAddToComparison={handleAddToComparison}
                            formatIndustryAlertMoneyFlow={formatIndustryAlertMoneyFlow}
                        />
                    )}

                    <IndustryResearchFocusPanel
                        selectedIndustry={selectedIndustry}
                        selectedIndustrySnapshot={selectedIndustrySnapshot}
                        selectedIndustryMarketCapBadge={selectedIndustryMarketCapBadge}
                        selectedIndustryVolatilityMeta={selectedIndustryVolatilityMeta}
                        selectedIndustryFocusNarrative={selectedIndustryFocusNarrative}
                        selectedIndustryScoreBreakdown={selectedIndustryScoreBreakdown}
                        selectedIndustryScoreSummary={selectedIndustryScoreSummary}
                        selectedIndustryReasons={selectedIndustryReasons}
                        selectedIndustryWatched={selectedIndustryWatched}
                        focusIndustrySuggestions={focusIndustrySuggestions}
                        onClearIndustry={() => setSelectedIndustry(null)}
                        onOpenIndustryDetail={openSelectedIndustryDetail}
                        onToggleWatchlist={() => toggleWatchlistIndustry(selectedIndustry)}
                        onAddToComparison={() => handleAddToComparison(selectedIndustry)}
                        onSelectIndustry={handleIndustryClick}
                    />

                    {shouldRenderLeaderPanel ? (
                        <LeaderStockPanel
                            topN={5}
                            topIndustries={5}
                            perIndustry={3}
                            focusIndustry={selectedIndustry}
                            onClearFocusIndustry={() => setSelectedIndustry(null)}
                        />
                    ) : (
                        <Card
                            title={
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                    <span>
                                        <CrownOutlined style={{ marginRight: 8, color: '#faad14' }} />
                                        龙头股推荐
                                    </span>
                                    <span style={{ fontSize: 11, color: TEXT_SECONDARY, fontWeight: 400 }}>首屏优先渲染行业热力图，龙头股榜单稍后加载</span>
                                </div>
                            }
                            styles={{ body: { paddingTop: 20, paddingBottom: 20 } }}
                        >
                            <div style={{ textAlign: 'center', padding: '18px 0 10px' }}>
                                <Spin size="small" />
                                <div style={{ marginTop: 12, fontSize: 12, color: TEXT_SECONDARY }}>
                                    正在后台准备龙头股榜单...
                                </div>
                            </div>
                        </Card>
                    )}
                </Col>
            </Row>

            <Modal
                title="行业热力图全屏"
                open={heatmapFullscreen}
                onCancel={() => setHeatmapFullscreen(false)}
                footer={null}
                width="92vw"
                style={{ top: 20 }}
                destroyOnHidden
                modalRender={(node) => <div data-testid="industry-heatmap-fullscreen-modal">{node}</div>}
                styles={{ body: { paddingTop: 8 } }}
            >
                <IndustryHeatmap
                    onIndustryClick={handleIndustryClick}
                    onDataLoad={handleHeatmapDataLoad}
                    onLeadingStockClick={handleLeadingStockClick}
                    replaySnapshot={activeReplaySnapshot}
                    marketCapFilter={marketCapFilter}
                    onClearMarketCapFilter={() => setMarketCapFilter('all')}
                    onSelectMarketCapFilter={jumpToMarketCapFilter}
                    timeframeValue={heatmapViewState.timeframe}
                    sizeMetricValue={heatmapViewState.sizeMetric}
                    colorMetricValue={heatmapViewState.colorMetric}
                    displayCountValue={heatmapViewState.displayCount}
                    searchTermValue={heatmapViewState.searchTerm}
                    legendRangeValue={heatmapLegendRange}
                    onTimeframeChange={(value) => setHeatmapViewState((prev) => ({ ...prev, timeframe: value }))}
                    onSizeMetricChange={(value) => setHeatmapViewState((prev) => ({ ...prev, sizeMetric: value }))}
                    onColorMetricChange={(value) => setHeatmapViewState((prev) => ({ ...prev, colorMetric: value }))}
                    onDisplayCountChange={(value) => setHeatmapViewState((prev) => ({ ...prev, displayCount: value }))}
                    onSearchTermChange={(value) => setHeatmapViewState((prev) => ({ ...prev, searchTerm: value }))}
                    onLegendRangeChange={setHeatmapLegendRange}
                    focusControlKey={focusedHeatmapControlKey}
                    showStats
                    onToggleFullscreen={() => setHeatmapFullscreen(false)}
                    isFullscreen
                />
            </Modal>

            {/* 行业详情弹窗 */}
            <Modal
                title={`${selectedIndustry} 行业详情`}
                open={detailVisible}
                onCancel={() => setDetailVisible(false)}
                footer={null}
                width={1000}
                destroyOnHidden
                modalRender={(node) => <div data-testid="industry-detail-modal">{node}</div>}
                styles={{ body: { padding: '0 24px 24px' } }}
            >
                <IndustryTrendPanel
                    industryName={selectedIndustry}
                    days={30}
                    industrySnapshot={selectedIndustrySnapshot}
                    stocks={industryStocks}
                    loadingStocks={loadingStocks}
                    stocksRefining={stocksRefining}
                    stocksScoreStage={stocksScoreStage}
                    stocksDisplayReady={stocksDisplayReady}
                    stockColumns={stockColumns}
                />
            </Modal>

            <StockDetailModal
                open={stockDetailVisible}
                onCancel={() => {
                    if (stockDetailAbortRef.current) {
                        stockDetailAbortRef.current.abort();
                    }
                    setStockDetailVisible(false);
                    setStockDetailSymbol(null);
                    setStockDetailError(null);
                    setStockDetailData(null);
                }}
                loading={stockDetailLoading}
                error={stockDetailError}
                detailData={stockDetailData}
                selectedStock={stockDetailData?.symbol || stockDetailSymbol}
                onRetry={stockDetailSymbol ? () => handleLeadingStockClick(stockDetailSymbol) : undefined}
            />

            <IndustryScoreRadarModal
                visible={Boolean(scoreRadarRecord)}
                onClose={() => setScoreRadarRecord(null)}
                record={scoreRadarRecord}
                snapshot={scoreRadarRecord ? selectedIndustrySnapshot?.industry_name === scoreRadarRecord.industry_name
                    ? selectedIndustrySnapshot
                    : (heatmapIndustries || []).find((item) => item?.name === scoreRadarRecord.industry_name) : null}
            />
        </Layout>
    );
};

export default IndustryDashboard;
