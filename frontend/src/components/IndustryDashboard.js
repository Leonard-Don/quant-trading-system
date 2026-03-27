import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import {
    Layout,
    Row,
    Col,
    Card,
    Tabs,
    Table,
    Spin,
    Empty,
    Tag,
    Button,
    Select,
    Space,
    Statistic,
    Progress,
    message,
    Radio,
    Modal,
    Tooltip
} from 'antd';
import {
    FireOutlined,
    BranchesOutlined,
    ReloadOutlined,
    RiseOutlined,
    FundOutlined,
    StarFilled,
    CrownOutlined
} from '@ant-design/icons';
import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip as RechartsTooltip,
    ResponsiveContainer
} from 'recharts';
import IndustryHeatmap from './IndustryHeatmap';
import IndustryTrendPanel from './IndustryTrendPanel';
import LeaderStockPanel from './LeaderStockPanel';
import IndustryRotationChart from './IndustryRotationChart';
import ApiStatusIndicator from './ApiStatusIndicator';
import StockDetailModal from './StockDetailModal';
import {
    getHotIndustries,
    getIndustryStocks,
    getIndustryClusters,
    getLeaderDetail
} from '../services/api';

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
const INDUSTRY_ALERT_RECENCY_OPTIONS = [
    { value: '15', label: '近15分钟新增' },
    { value: '30', label: '近30分钟新增' },
    { value: 'session', label: '本次会话' },
];
const MAX_HEATMAP_REPLAY_SNAPSHOTS = 10;

const formatIndustryAlertMoneyFlow = (value) => {
    const numericValue = Number(value || 0);
    if (!numericValue) return '0';
    const yi = numericValue / 1e8;
    if (Math.abs(yi) >= 1) return `${yi >= 0 ? '+' : ''}${yi.toFixed(1)}亿`;
    const wan = numericValue / 1e4;
    return `${wan >= 0 ? '+' : ''}${wan.toFixed(0)}万`;
};

const getIndustryScoreTone = (score) => {
    const numericScore = Number(score || 0);
    if (numericScore >= 70) return '#52c41a';
    if (numericScore >= 50) return '#faad14';
    return '#ff4d4f';
};

const formatIndustryAlertSeenLabel = (timestamp) => {
    if (!timestamp) return '刚刚出现';
    const diffMs = Math.max(0, Date.now() - timestamp);
    const diffMinutes = Math.floor(diffMs / 60000);
    if (diffMinutes < 1) return '刚刚出现';
    if (diffMinutes < 60) return `${diffMinutes} 分钟前出现`;
    const diffHours = Math.floor(diffMinutes / 60);
    return `${diffHours} 小时前出现`;
};

const buildHeatmapReplaySnapshotId = (updateTime, timeframe, sequence = 0) => (
    `${updateTime || Date.now()}::${timeframe || 'na'}::${sequence}`
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

const getIndustryStockScoreStage = (stocks = []) => {
    if (!Array.isArray(stocks) || stocks.length === 0) return null;
    if (stocks.some((stock) => stock?.scoreStage === 'full')) return 'full';
    if (stocks.some((stock) => stock?.scoreStage === 'quick')) return 'quick';
    return stocks.some((stock) => Number(stock?.total_score || 0) > 0) ? 'full' : 'quick';
};

const hasDisplayReadyIndustryStockDetails = (stocks = []) => {
    if (!Array.isArray(stocks) || stocks.length === 0) return false;

    const meaningfulRows = stocks.filter((stock) => {
        const hasScore = Number(stock?.total_score || 0) > 0;
        const hasDetail = [stock?.market_cap, stock?.pe_ratio, stock?.change_pct]
            .some((value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)));
        return hasScore && hasDetail;
    });

    return meaningfulRows.length >= Math.max(3, Math.ceil(stocks.length * 0.5));
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
    const [stockDetailVisible, setStockDetailVisible] = useState(false); // 龙头股详情弹窗
    const [stockDetailSymbol, setStockDetailSymbol] = useState(null);
    const [stockDetailData, setStockDetailData] = useState(null);
    const [stockDetailLoading, setStockDetailLoading] = useState(false);
    const [stockDetailError, setStockDetailError] = useState(null);
    const [shouldRenderLeaderPanel, setShouldRenderLeaderPanel] = useState(false);
    const [industryAlertRule, setIndustryAlertRule] = useState('all');
    const [industryAlertRecency, setIndustryAlertRecency] = useState('15');
    const [industryAlertHistory, setIndustryAlertHistory] = useState({});
    const [heatmapReplaySnapshots, setHeatmapReplaySnapshots] = useState([]);
    const [selectedReplaySnapshotId, setSelectedReplaySnapshotId] = useState(null);
    const [latestLiveHeatmapData, setLatestLiveHeatmapData] = useState(null);
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

    // 接收热力图数据摘要（供市场摘要横幅 + 会话内历史回放）
    const handleHeatmapDataLoad = useCallback((data) => {
        if (!data?.industries?.length) return;
        setLatestLiveHeatmapData(data);
        setHeatmapReplaySnapshots((current) => {
            const existingIndex = current.findIndex(
                (item) => item.updateTime === data.update_time && item.timeframe === heatmapViewState.timeframe
            );
            const snapshot = {
                id: buildHeatmapReplaySnapshotId(data.update_time, heatmapViewState.timeframe, existingIndex >= 0 ? existingIndex : current.length),
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
    }, [activeTab, rankType, sortBy, lookbackDays, buildHotQueryKey]);

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
    }, []);

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
            const result = await getIndustryClusters(4, {
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
    }, []);

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
        setComparisonIndustries(prev => {
            if (prev.includes(industryName)) return prev;
            if (prev.length >= 5) {
                message.warning('最多对比 5 个行业');
                return prev;
            }
            return [...prev, industryName];
        });
        setActiveTab('rotation');
    };

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
            pe_ttm: heatmapSnapshot?.pe_ttm ?? null,
            pb: heatmapSnapshot?.pb ?? null,
        };
    }, [selectedIndustry, hotIndustries, filteredHotIndustries, heatmapIndustries]);

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

    useEffect(() => {
        if (rawIndustryAlerts.length === 0) return;

        const seenAt = Date.now();
        setIndustryAlertHistory((current) => {
            const next = { ...current };
            let changed = false;

            rawIndustryAlerts.forEach((alert) => {
                const key = `${alert.industry_name}:${alert.kind}`;
                const existing = current[key];
                if (!existing) {
                    next[key] = {
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
                        lastSeenAt: seenAt,
                        hitCount: (existing.hitCount || 1) + 1,
                    };
                    changed = true;
                }
            });

            return changed ? next : current;
        });
    }, [rawIndustryAlerts]);

    const industryAlerts = useMemo(() => {
        const recencyMs = industryAlertRecency === 'session' ? Number.POSITIVE_INFINITY : Number(industryAlertRecency || 15) * 60 * 1000;
        const alertsWithHistory = rawIndustryAlerts.map((alert) => {
            const historyKey = `${alert.industry_name}:${alert.kind}`;
            const history = industryAlertHistory[historyKey];
            const firstSeenAt = history?.firstSeenAt || null;
            const isNew = firstSeenAt ? (Date.now() - firstSeenAt) <= recencyMs : false;
            return {
                ...alert,
                firstSeenAt,
                isNew,
                seenLabel: formatIndustryAlertSeenLabel(firstSeenAt),
            };
        });

        const filteredAlerts = alertsWithHistory.filter((alert) => {
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
    }, [focusIndustrySuggestions, industryAlertHistory, industryAlertRecency, industryAlertRule, rawIndustryAlerts]);

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
            render: (score) => (
                <span style={{ fontWeight: 700, fontSize: 13, color: TEXT_PRIMARY }}>
                    {score?.toFixed(2)}
                </span>
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
                                    shape="circle"
                                />
                            );
                        })}
                    </ScatterChart>
                </ResponsiveContainer>
            </div>
        );
    };

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
                    onTimeframeChange={(value) => setHeatmapViewState(prev => ({ ...prev, timeframe: value }))}
                    onSizeMetricChange={(value) => setHeatmapViewState(prev => ({ ...prev, sizeMetric: value }))}
                    onColorMetricChange={(value) => setHeatmapViewState(prev => ({ ...prev, colorMetric: value }))}
                    onDisplayCountChange={(value) => setHeatmapViewState(prev => ({ ...prev, displayCount: value }))}
                    onSearchTermChange={(value) => setHeatmapViewState(prev => ({ ...prev, searchTerm: value }))}
                    focusControlKey={focusedHeatmapControlKey}
                    showStats={false}
                />
            )
        },
        {
            label: '排行榜',
            key: 'ranking',
            children: (
                <Card
                    className="industry-ranking-card"
                    title="行业排名"
                    extra={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '6px 8px',
                                borderRadius: 10,
                                background: 'color-mix(in srgb, var(--bg-secondary) 84%, var(--accent-secondary) 16%)',
                                border: '1px solid color-mix(in srgb, var(--border-color) 72%, var(--accent-secondary) 28%)'
                            }} className="ranking-toolbar-group ranking-toolbar-group-primary">
                                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>榜单</span>
                                <Radio.Group
                                    className="ranking-control-rank-type"
                                    value={rankType}
                                    onChange={e => setRankType(e.target.value)}
                                    size="small"
                                    buttonStyle="solid"
                                    disabled={loadingHot}
                                    style={{
                                        boxShadow: focusedRankingControlKey === 'rank_type' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                        borderRadius: 8,
                                    }}
                                >
                                    <Radio.Button value="gainers">涨幅榜</Radio.Button>
                                    <Radio.Button value="losers">跌幅榜</Radio.Button>
                                </Radio.Group>
                            </div>

                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '6px 8px',
                                borderRadius: 10,
                                background: 'color-mix(in srgb, var(--bg-secondary) 92%, var(--bg-primary) 8%)',
                                border: PANEL_BORDER
                            }} className="ranking-toolbar-group ranking-toolbar-group-secondary">
                                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>排序视图</span>
                                <Select
                                    className="ranking-control-sort-by"
                                    value={sortBy}
                                    onChange={setSortBy}
                                    size="small"
                                    style={{
                                        width: 120,
                                        boxShadow: focusedRankingControlKey === 'sort_by' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                        borderRadius: 8,
                                    }}
                                    disabled={loadingHot}
                                >
                                    <Option value="change_pct">按涨跌幅</Option>
                                    <Option value="total_score">按综合得分</Option>
                                    <Option value="money_flow">按资金流向</Option>
                                    <Option value="industry_volatility">按波动率</Option>
                                </Select>
                                <Select
                                    className="ranking-control-lookback"
                                    value={lookbackDays}
                                    onChange={setLookbackDays}
                                    size="small"
                                    style={{
                                        width: 96,
                                        boxShadow: focusedRankingControlKey === 'lookback' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                        borderRadius: 8,
                                    }}
                                    disabled={loadingHot}
                                >
                                    <Option value={1}>近1日</Option>
                                    <Option value={5}>近5日</Option>
                                    <Option value={10}>近10日</Option>
                                </Select>
                                <Select
                                    className="ranking-control-volatility"
                                    value={volatilityFilter}
                                    onChange={setVolatilityFilter}
                                    size="small"
                                    style={{
                                        width: 112,
                                        boxShadow: focusedRankingControlKey === 'volatility_filter' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                        borderRadius: 8,
                                    }}
                                    disabled={loadingHot}
                                >
                                    <Option value="all">全部波动</Option>
                                    <Option value="low">低波动</Option>
                                    <Option value="medium">中波动</Option>
                                    <Option value="high">高波动</Option>
                                </Select>
                                <Select
                                    className="ranking-control-market-cap"
                                    value={rankingMarketCapFilter}
                                    onChange={setRankingMarketCapFilter}
                                    size="small"
                                    style={{
                                        width: 124,
                                        boxShadow: focusedRankingControlKey === 'market_cap_filter' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                        borderRadius: 8,
                                    }}
                                    disabled={loadingHot}
                                >
                                    <Option value="all">全部市值来源</Option>
                                    <Option value="live">实时市值</Option>
                                    <Option value="snapshot">快照市值</Option>
                                    <Option value="proxy">代理市值</Option>
                                    <Option value="estimated">估算市值</Option>
                                </Select>
                            </div>

                            <Tooltip title="刷新排行榜数据">
                                <Button
                                    icon={<ReloadOutlined />}
                                    onClick={() => loadHotIndustries(50, rankType, sortBy, lookbackDays)}
                                    size="small"
                                    type="text"
                                    loading={loadingHot}
                                />
                            </Tooltip>
                        </div>
                    }
                >
                    <Table
                        className="industry-ranking-table"
                        dataSource={filteredHotIndustries}
                        columns={hotIndustryColumns}
                        rowKey="industry_name"
                        size="small"
                        loading={loadingHot}
                        pagination={{
                            pageSize: 15,
                            showSizeChanger: true,
                            pageSizeOptions: ['10', '15', '30', '50'],
                            showTotal: (total) => `共 ${total} 个行业`
                        }}
                        onRow={(record) => ({
                            onClick: () => handleIndustryClick(record.industry_name),
                            style: { cursor: 'pointer' }
                        })}
                        locale={{
                            emptyText: (
                                <Empty description={loadingHot ? '正在加载行业排名...' : '暂无排名数据'}>
                                    <Button
                                        className="industry-empty-action"
                                        type="dashed"
                                        loading={loadingHot}
                                        onClick={() => loadHotIndustries(50, rankType, sortBy, lookbackDays)}
                                    >
                                        刷新
                                    </Button>
                                </Empty>
                            )
                        }}
                    />
                </Card>
            )
        },
        {
            label: '聚类分析',
            key: 'clusters',
            children: (
                <Card
                    title="行业聚类分析"
                    extra={
                        clusters && (
                            <Button
                                className="industry-inline-link"
                                icon={<ReloadOutlined />}
                                onClick={() => loadClusters(false)}
                                size="small"
                            >
                                重新分析
                            </Button>
                        )
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
    const hasActiveRankingState = activeRankingStateTags.length > 0;

    return (
        <Layout style={{ padding: 24, background: 'var(--bg-primary)', minHeight: '100vh' }}>
            <Row gutter={[24, 24]}>
                {/* 左侧：热力图和热门行业 */}
                <Col xs={24} lg={16}>
                    {/* 市场摘要横幅 */}
                    {heatmapSummary && (
                        <Card
                            size="small"
                            style={{
                                marginBottom: 12,
                                background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                                border: '1px solid rgba(255,255,255,0.1)',
                                borderRadius: 8
                            }}
                            styles={{ body: { padding: '12px 14px' } }}
                        >
                            <div style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                gap: 12,
                                marginBottom: 10,
                                flexWrap: 'wrap'
                            }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                    <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.42)', fontWeight: 700, letterSpacing: '0.04em' }}>市场快照</span>
                                    <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.82)' }}>行业热度与市值质量概览</span>
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
                                    <div style={{ textAlign: 'right' }}>
                                        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 2 }}>数据更新</div>
                                        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', fontFamily: 'monospace' }}>
                                            {heatmapSummary.updateTime ? new Date(heatmapSummary.updateTime).toLocaleTimeString('zh-CN', { hour12: false }) : '-'}
                                        </div>
                                    </div>
                                    <ApiStatusIndicator />
                                </div>
                            </div>
                            <Row gutter={[10, 10]} align="stretch" wrap>
                                <Col xs={24} sm={12} xl={5}>
                                    <div style={{
                                        height: '100%',
                                        background: 'rgba(255,255,255,0.05)',
                                        border: '1px solid rgba(255,255,255,0.08)',
                                        borderRadius: 10,
                                        padding: '10px 12px'
                                    }}>
                                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 3 }}>市场情绪</div>
                                    <Tag
                                        style={{
                                            color: heatmapSummary.sentiment.color,
                                            background: heatmapSummary.sentiment.bg,
                                            border: `1px solid ${heatmapSummary.sentiment.color}`,
                                            fontWeight: 'bold',
                                            fontSize: 14,
                                            padding: '2px 12px',
                                            margin: 0
                                        }}
                                    >
                                        {heatmapSummary.sentiment.label}
                                    </Tag>
                                    </div>
                                </Col>

                                <Col xs={24} sm={12} xl={5}>
                                    <div style={{
                                        height: '100%',
                                        background: 'rgba(255,255,255,0.05)',
                                        border: '1px solid rgba(255,255,255,0.08)',
                                        borderRadius: 10,
                                        padding: '10px 12px'
                                    }}>
                                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 3 }}>
                                        市场广度 &nbsp;
                                        <span style={{ color: heatmapSummary.sentiment.color, fontWeight: 600 }}>{heatmapSummary.upRatio}%</span>
                                        <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>&nbsp;(↑{heatmapSummary.upCount} ━{heatmapSummary.flatCount} ↓{heatmapSummary.downCount})</span>
                                    </div>
                                    <Progress
                                        percent={heatmapSummary.upRatio}
                                        showInfo={false}
                                        strokeColor="#cf1322"
                                        trailColor="#3f8600"
                                        size="small"
                                        style={{ marginBottom: 0 }}
                                    />
                                    </div>
                                </Col>

                                {heatmapSummary.topInflow.length > 0 && (
                                    <Col xs={24} sm={12} xl={5}>
                                        <div style={{
                                            height: '100%',
                                            background: 'rgba(255,255,255,0.05)',
                                            border: '1px solid rgba(255,255,255,0.08)',
                                            borderRadius: 10,
                                            padding: '10px 12px'
                                        }}>
                                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>
                                            <RiseOutlined style={{ color: '#ff7875', marginRight: 3 }} />主力流入
                                        </div>
                                        <Space size={[4, 4]} wrap style={{ maxWidth: '100%' }}>
                                            {heatmapSummary.topInflow.map((ind, idx) => (
                                                <Tag
                                                    key={ind.name}
                                                    color={idx === 0 ? 'red' : 'volcano'}
                                                    style={{
                                                        margin: 0,
                                                        cursor: 'pointer',
                                                        fontSize: 10,
                                                        lineHeight: '15px',
                                                        paddingInline: 6,
                                                        borderRadius: 999,
                                                        maxWidth: '100%',
                                                        whiteSpace: 'normal',
                                                        wordBreak: 'break-word'
                                                    }}
                                                    onClick={() => handleIndustryClick(ind.name)}
                                                >
                                                    {ind.name}
                                                </Tag>
                                            ))}
                                        </Space>
                                        </div>
                                    </Col>
                                )}

                                {heatmapSummary.topOutflow.length > 0 && (
                                    <Col xs={24} sm={12} xl={5}>
                                        <div style={{
                                            height: '100%',
                                            background: 'rgba(255,255,255,0.05)',
                                            border: '1px solid rgba(255,255,255,0.08)',
                                            borderRadius: 10,
                                            padding: '10px 12px'
                                        }}>
                                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>
                                            <FundOutlined style={{ color: '#95de64', marginRight: 3 }} />流出压力
                                        </div>
                                        <Space size={[4, 4]} wrap style={{ maxWidth: '100%' }}>
                                            {heatmapSummary.topOutflow.map((ind, idx) => (
                                                <Tag
                                                    key={ind.name}
                                                    color={idx === 0 ? 'green' : 'lime'}
                                                    style={{
                                                        margin: 0,
                                                        cursor: 'pointer',
                                                        fontSize: 10,
                                                        lineHeight: '15px',
                                                        paddingInline: 6,
                                                        borderRadius: 999,
                                                        maxWidth: '100%',
                                                        whiteSpace: 'normal',
                                                        wordBreak: 'break-word'
                                                    }}
                                                    onClick={() => handleIndustryClick(ind.name)}
                                                >
                                                    {ind.name}
                                                </Tag>
                                            ))}
                                        </Space>
                                        </div>
                                    </Col>
                                )}

                                {heatmapSummary.topTurnover.length > 0 && (
                                    <Col xs={24} sm={12} xl={4}>
                                        <div style={{
                                            height: '100%',
                                            background: 'rgba(255,255,255,0.05)',
                                            border: '1px solid rgba(255,255,255,0.08)',
                                            borderRadius: 10,
                                            padding: '10px 12px'
                                        }}>
                                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>
                                            <FundOutlined style={{ color: '#faad14', marginRight: 3 }} />活跃行业
                                        </div>
                                        <Space size={[4, 4]} wrap style={{ maxWidth: '100%' }}>
                                            {heatmapSummary.topTurnover.map((ind) => (
                                                <Tag
                                                    key={ind.name}
                                                    color="gold"
                                                    style={{
                                                        margin: 0,
                                                        cursor: 'pointer',
                                                        fontSize: 10,
                                                        lineHeight: '15px',
                                                        paddingInline: 6,
                                                        borderRadius: 999,
                                                        maxWidth: '100%',
                                                        whiteSpace: 'normal',
                                                        wordBreak: 'break-word'
                                                    }}
                                                    onClick={() => handleIndustryClick(ind.name)}
                                                >
                                                    {ind.name}
                                                </Tag>
                                            ))}
                                        </Space>
                                        </div>
                                    </Col>
                                )}

                                {heatmapSummary.marketCapHealth && (
                                    <Col
                                        xs={24}
                                        xl={5}
                                        className="heatmap-control-market-cap-filter"
                                        style={{
                                            boxShadow: focusedHeatmapControlKey === 'market_cap_filter' ? '0 0 0 2px rgba(24,144,255,0.22)' : 'none',
                                            borderRadius: 8,
                                            transition: 'all 0.2s ease',
                                        }}
                                    >
                                        <div style={{
                                            height: '100%',
                                            background: 'rgba(255,255,255,0.05)',
                                            border: '1px solid rgba(255,255,255,0.08)',
                                            borderRadius: 10,
                                            padding: focusedHeatmapControlKey === 'market_cap_filter' ? '8px 10px' : '10px 12px'
                                        }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                                            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>
                                                <StarFilled style={{ color: heatmapSummary.marketCapHealth.coverageTone.color, marginRight: 4 }} />
                                                市值覆盖
                                            </div>
                                            <div style={{ color: heatmapSummary.marketCapHealth.coverageTone.color, fontWeight: 700, fontSize: 16 }}>
                                                {heatmapSummary.marketCapHealth.coveragePct}%
                                            </div>
                                        </div>
                                        <Space size={[4, 4]} wrap style={{ marginBottom: 2 }}>
                                            <Tooltip title="点击高亮实时市值行业">
                                                <Tag
                                                    color={marketCapFilter === 'live' ? 'green' : 'default'}
                                                    style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                                    onClick={() => toggleMarketCapFilter('live')}
                                                >
                                                    实时 {heatmapSummary.marketCapHealth.liveCount}
                                                </Tag>
                                            </Tooltip>
                                            <Tooltip title="点击高亮快照市值行业">
                                                <Tag
                                                    color={marketCapFilter === 'snapshot' ? (heatmapSummary.marketCapHealth.staleSnapshotCount > 0 ? 'orange' : 'blue') : 'default'}
                                                    style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                                    onClick={() => toggleMarketCapFilter('snapshot')}
                                                >
                                                    快照 {heatmapSummary.marketCapHealth.snapshotCount}
                                                    {heatmapSummary.marketCapHealth.staleSnapshotCount > 0
                                                        ? ` / 旧 ${heatmapSummary.marketCapHealth.staleSnapshotCount}`
                                                        : ''}
                                                </Tag>
                                            </Tooltip>
                                            {heatmapSummary.marketCapHealth.proxyCount > 0 && (
                                                <Tooltip title="点击高亮行业组代理市值">
                                                    <Tag
                                                        color={marketCapFilter === 'proxy' ? 'cyan' : 'default'}
                                                        style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                                        onClick={() => toggleMarketCapFilter('proxy')}
                                                    >
                                                        代理 {heatmapSummary.marketCapHealth.proxyCount}
                                                    </Tag>
                                                </Tooltip>
                                            )}
                                            <Tooltip title="点击高亮估算市值行业">
                                                <Tag
                                                    color={marketCapFilter === 'estimated' ? 'gold' : 'default'}
                                                    style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                                    onClick={() => toggleMarketCapFilter('estimated')}
                                                >
                                                    估算 {heatmapSummary.marketCapHealth.estimatedCount}
                                                </Tag>
                                            </Tooltip>
                                            {marketCapFilter !== 'all' && (
                                                <Tooltip title="清除市值来源筛选">
                                                    <Tag
                                                        color="processing"
                                                        style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                                        onClick={() => setMarketCapFilter('all')}
                                                    >
                                                        查看全部
                                                    </Tag>
                                                </Tooltip>
                                            )}
                                        </Space>
                                        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.38)', marginTop: 4 }}>
                                            {heatmapSummary.marketCapHealth.snapshotCount > 0
                                                ? `最老快照 ${Math.round(heatmapSummary.marketCapHealth.oldestSnapshotHours || 0)}h`
                                                : '当前无快照市值'}
                                        </div>
                                        </div>
                                    </Col>
                                )}
                            </Row>
                        </Card>
                    )}

                    {heatmapReplaySnapshots.length > 0 && (
                        <Card
                            size="small"
                            data-testid="industry-replay-card"
                            style={{
                                marginBottom: 12,
                                background: activeReplaySnapshot
                                    ? 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 92%, var(--accent-primary) 8%) 0%, color-mix(in srgb, var(--bg-secondary) 96%, var(--accent-warning) 4%) 100%)'
                                    : PANEL_SURFACE,
                                border: activeReplaySnapshot
                                    ? '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)'
                                    : PANEL_BORDER,
                                boxShadow: PANEL_SHADOW,
                            }}
                            styles={{ body: { padding: '12px 14px' } }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                    <span style={{ fontSize: 11, color: PANEL_MUTED, fontWeight: 700, letterSpacing: '0.04em' }}>行业历史回放</span>
                                    <span style={{ fontSize: 13, color: TEXT_PRIMARY }}>
                                        {activeReplaySnapshot
                                            ? `正在回看 ${formatReplaySnapshotTime(activeReplaySnapshot.updateTime)} 的行业截面，热力图已暂停实时刷新`
                                            : `已记录 ${heatmapReplaySnapshots.length} 个会话快照，可快速回看刚才的行业截面`}
                                    </span>
                                </div>
                                <Space size={8} wrap>
                                    {latestReplaySnapshot && (
                                        <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>
                                            最新 {formatReplaySnapshotTime(latestReplaySnapshot.updateTime)}
                                        </Tag>
                                    )}
                                    {activeReplaySnapshot && (
                                        <Button
                                            size="small"
                                            type="primary"
                                            onClick={() => setSelectedReplaySnapshotId(null)}
                                        >
                                            回到实时
                                        </Button>
                                    )}
                                </Space>
                            </div>

                            <Space size={[8, 8]} wrap>
                                {heatmapReplaySnapshots.slice(0, 6).map((snapshot, index) => (
                                    <Button
                                        key={snapshot.id}
                                        size="small"
                                        type={activeReplaySnapshot?.id === snapshot.id ? 'primary' : 'default'}
                                        onClick={() => {
                                            setActiveTab('heatmap');
                                            setSelectedReplaySnapshotId(snapshot.id);
                                            setHeatmapViewState((current) => ({
                                                ...current,
                                                timeframe: snapshot.timeframe,
                                                sizeMetric: snapshot.sizeMetric,
                                                colorMetric: snapshot.colorMetric,
                                                displayCount: snapshot.displayCount,
                                                searchTerm: snapshot.searchTerm || '',
                                            }));
                                            setMarketCapFilter(snapshot.marketCapFilter || 'all');
                                        }}
                                    >
                                        {index === 0 ? '最新 ' : ''}{formatReplaySnapshotTime(snapshot.updateTime)} · {INDUSTRY_TIMEFRAME_LABELS[snapshot.timeframe] || `${snapshot.timeframe}日`}
                                    </Button>
                                ))}
                            </Space>

                            <div style={{ marginTop: 10, fontSize: 10, color: PANEL_MUTED }}>
                                当前是会话内回放，不依赖后端历史库；适合盘中回看刚才看过的行业截面和研究焦点。
                            </div>
                        </Card>
                    )}

                    {(industryAlerts.length > 0 || rawIndustryAlerts.length > 0 || focusIndustrySuggestions.length > 0) && (
                        <Card
                            size="small"
                            data-testid="industry-alerts-card"
                            style={{
                                marginBottom: 12,
                                background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 94%, var(--accent-warning) 6%) 0%, color-mix(in srgb, var(--bg-secondary) 96%, var(--accent-primary) 4%) 100%)',
                                border: PANEL_BORDER,
                                boxShadow: PANEL_SHADOW,
                            }}
                            styles={{ body: { padding: '12px 14px' } }}
                        >
                            <div style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                gap: 12,
                                marginBottom: 12,
                                flexWrap: 'wrap'
                            }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                    <span style={{ fontSize: 11, color: PANEL_MUTED, fontWeight: 700, letterSpacing: '0.04em' }}>行业异动提醒</span>
                                    <span style={{ fontSize: 13, color: TEXT_PRIMARY }}>支持按规则筛选，并标出本次会话内新出现的提醒</span>
                                </div>
                                <Space size={8} wrap>
                                    <Tag color="processing" style={{ margin: 0, borderRadius: 999 }}>
                                        {industryAlerts.length} 条提醒
                                    </Tag>
                                    <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>
                                        {industryAlerts.filter((alert) => alert.isNew).length} 条新增
                                    </Tag>
                                </Space>
                            </div>

                            <div
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    gap: 10,
                                    flexWrap: 'wrap',
                                    marginBottom: 12,
                                }}
                            >
                                <Radio.Group
                                    value={industryAlertRule}
                                    onChange={(event) => setIndustryAlertRule(event.target.value)}
                                    size="small"
                                    buttonStyle="solid"
                                >
                                    <Radio.Button value="all">全部</Radio.Button>
                                    <Radio.Button value="new">新增</Radio.Button>
                                    <Radio.Button value="capital">资金</Radio.Button>
                                    <Radio.Button value="risk">风险</Radio.Button>
                                    <Radio.Button value="rotation">轮动</Radio.Button>
                                </Radio.Group>

                                <Select
                                    value={industryAlertRecency}
                                    onChange={setIndustryAlertRecency}
                                    size="small"
                                    style={{ width: 128 }}
                                    disabled={industryAlertRule !== 'new'}
                                >
                                    {INDUSTRY_ALERT_RECENCY_OPTIONS.map((item) => (
                                        <Option key={item.value} value={item.value}>{item.label}</Option>
                                    ))}
                                </Select>
                            </div>

                            {industryAlerts.length > 0 ? (
                                <Row gutter={[10, 10]}>
                                    {industryAlerts.map((alert) => (
                                        <Col xs={24} md={12} key={`${alert.industry_name}-${alert.title}`}>
                                            <div
                                                data-testid="industry-alert-item"
                                                style={{
                                                    height: '100%',
                                                    borderRadius: 12,
                                                    padding: '12px 12px 10px',
                                                    background: 'color-mix(in srgb, var(--bg-primary) 26%, var(--bg-secondary) 74%)',
                                                    border: `1px solid ${alert.accent}33`,
                                                    boxShadow: `inset 0 0 0 1px ${alert.accent}14`,
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                                            <Tag color={alert.color} style={{ margin: 0, borderRadius: 999, fontSize: 11 }}>
                                                                {alert.title}
                                                            </Tag>
                                                            <span style={{ fontSize: 15, fontWeight: 700, color: TEXT_PRIMARY }}>{alert.industry_name}</span>
                                                            <Tag color={alert.isNew ? 'magenta' : 'default'} style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                                                {alert.isNew ? '本次会话新增' : '持续关注'}
                                                            </Tag>
                                                        </div>
                                                        <div style={{ fontSize: 12, lineHeight: 1.7, color: TEXT_PRIMARY }}>
                                                            {alert.summary}
                                                        </div>
                                                    </div>
                                                    <Space size={6} wrap>
                                                        <Tag color="default" style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                                            {alert.seenLabel}
                                                        </Tag>
                                                        {selectedIndustry === alert.industry_name && (
                                                            <Tag color="gold" style={{ margin: 0, borderRadius: 999 }}>已聚焦</Tag>
                                                        )}
                                                    </Space>
                                                </div>
                                                <div style={{ fontSize: 11, lineHeight: 1.7, color: TEXT_SECONDARY, marginBottom: 10 }}>
                                                    {alert.reason}
                                                </div>
                                                <Space size={8} wrap>
                                                    <Button
                                                        size="small"
                                                        type={selectedIndustry === alert.industry_name ? 'default' : 'primary'}
                                                        onClick={() => setSelectedIndustry(alert.industry_name)}
                                                    >
                                                        聚焦
                                                    </Button>
                                                    <Button
                                                        size="small"
                                                        type="text"
                                                        onClick={() => handleIndustryClick(alert.industry_name)}
                                                    >
                                                        查看详情
                                                    </Button>
                                                    <Button
                                                        size="small"
                                                        type="text"
                                                        icon={<BranchesOutlined />}
                                                        onClick={() => handleAddToComparison(alert.industry_name)}
                                                    >
                                                        加入对比
                                                    </Button>
                                                </Space>
                                            </div>
                                        </Col>
                                    ))}
                                </Row>
                            ) : (
                                <Empty
                                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                                    description={
                                        industryAlertRule === 'new'
                                            ? `当前没有${industryAlertRecency === 'session' ? '本次会话内' : `最近 ${industryAlertRecency} 分钟内`}新增提醒`
                                            : '当前筛选下没有匹配提醒'
                                    }
                                >
                                    <Button size="small" onClick={() => setIndustryAlertRule('all')}>
                                        查看全部提醒
                                    </Button>
                                </Empty>
                            )}

                            <div style={{ marginTop: 10, fontSize: 10, color: PANEL_MUTED }}>
                                当前为截面异动提醒；“新增”基于本页会话内首次出现时间判断，后续接入历史回放后可以升级成真正的突变告警。
                            </div>
                        </Card>
                    )}

                    {activeTab === 'heatmap' && hasActiveHeatmapState && (
                        <div
                            style={{
                                marginBottom: 12,
                                padding: '10px 14px',
                                borderRadius: 10,
                                background: PANEL_SURFACE,
                                border: PANEL_BORDER,
                                boxShadow: PANEL_SHADOW
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <span style={{ fontSize: 11, color: PANEL_MUTED, fontWeight: 700, letterSpacing: '0.04em' }}>当前视图</span>
                                    {activeHeatmapStateTags.map((item) => (
                                        <Tag
                                            key={item.key}
                                            color="processing"
                                            closable
                                            className={`heatmap-state-tag-${item.key} industry-state-tag`}
                                            onClick={() => focusHeatmapControl(item.key)}
                                            onClose={(event) => {
                                                event.preventDefault();
                                                clearHeatmapStateTag(item.key);
                                            }}
                                            style={{ margin: 0, fontSize: 12, cursor: 'pointer', borderRadius: 999, paddingInline: 8 }}
                                        >
                                            {item.label}: {item.value}
                                        </Tag>
                                    ))}
                                </div>
                                <Button className="industry-reset-button" size="small" type="text" onClick={resetHeatmapViewState}>
                                    清除全部
                                </Button>
                            </div>
                        </div>
                    )}

                    {activeTab === 'ranking' && hasActiveRankingState && (
                        <div
                            style={{
                                marginBottom: 12,
                                padding: '10px 14px',
                                borderRadius: 10,
                                background: PANEL_SURFACE,
                                border: PANEL_BORDER,
                                boxShadow: PANEL_SHADOW
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <span style={{ fontSize: 11, color: PANEL_MUTED, fontWeight: 700, letterSpacing: '0.04em' }}>当前筛选</span>
                                    {activeRankingStateTags.map((item) => (
                                        <Tag
                                            key={item.key}
                                            color="purple"
                                            closable
                                            className={`ranking-state-tag-${item.key} industry-state-tag`}
                                            onClick={() => focusRankingControl(item.key)}
                                            onClose={(event) => {
                                                event.preventDefault();
                                                clearRankingStateTag(item.key);
                                            }}
                                            style={{ margin: 0, fontSize: 12, cursor: 'pointer', borderRadius: 999, paddingInline: 8 }}
                                        >
                                            {item.label}: {item.value}
                                        </Tag>
                                    ))}
                                </div>
                                <Button className="industry-reset-button" size="small" type="text" onClick={resetRankingViewState}>
                                    恢复默认榜单
                                </Button>
                            </div>
                        </div>
                    )}

                    <Tabs
                        activeKey={activeTab}
                        onChange={setActiveTab}
                        items={tabItems}
                    />
                </Col>

                {/* 右侧：龙头股推荐 */}
                <Col xs={24} lg={8}>
                    <Card
                        size="small"
                        style={{
                            marginBottom: 12,
                            borderRadius: 12,
                            border: selectedIndustry
                                ? '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)'
                                : PANEL_BORDER,
                            boxShadow: PANEL_SHADOW,
                            background: selectedIndustry
                                ? 'linear-gradient(180deg, color-mix(in srgb, var(--accent-primary) 6%, var(--bg-secondary) 94%) 0%, color-mix(in srgb, var(--accent-warning) 4%, var(--bg-secondary) 96%) 100%)'
                                : PANEL_SURFACE
                        }}
                        title={
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                <span style={{ fontWeight: 700, color: TEXT_PRIMARY }}>研究焦点</span>
                                <span style={{ fontSize: 11, color: TEXT_SECONDARY }}>
                                    {selectedIndustry ? '当前行业上下文与下一步动作' : '先选一个行业，再看龙头和详情'}
                                </span>
                            </div>
                        }
                    >
                        {selectedIndustry ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        <span style={{ fontSize: 18, fontWeight: 700, color: TEXT_PRIMARY }}>{selectedIndustry}</span>
                                        <Space size={[6, 6]} wrap>
                                            {selectedIndustrySnapshot && (
                                                <Tag
                                                    color={getMarketCapBadgeMeta(selectedIndustrySnapshot.marketCapSource).color}
                                                    style={{ margin: 0, borderRadius: 999 }}
                                                >
                                                    {getMarketCapBadgeMeta(selectedIndustrySnapshot.marketCapSource).label}市值
                                                </Tag>
                                            )}
                                            {selectedIndustryVolatilityMeta?.value > 0 && (
                                                <Tag color={selectedIndustryVolatilityMeta.color} style={{ margin: 0, borderRadius: 999 }}>
                                                    {selectedIndustryVolatilityMeta.label} {selectedIndustryVolatilityMeta.value.toFixed(1)}%
                                                </Tag>
                                            )}
                                        </Space>
                                    </div>
                                    <Button size="small" type="text" onClick={() => setSelectedIndustry(null)}>
                                        清除
                                    </Button>
                                </div>

                                <div style={{
                                    padding: '10px 12px',
                                    borderRadius: 10,
                                    background: 'color-mix(in srgb, var(--accent-primary) 8%, var(--bg-secondary) 92%)',
                                    border: '1px solid color-mix(in srgb, var(--accent-primary) 18%, var(--border-color) 82%)'
                                }}>
                                    <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 5, fontWeight: 700, letterSpacing: '0.04em' }}>
                                        一句话判断
                                    </div>
                                    <div style={{ fontSize: 13, lineHeight: 1.7, color: TEXT_PRIMARY }}>
                                        {selectedIndustryFocusNarrative}
                                    </div>
                                </div>

                                <Row gutter={[8, 8]}>
                                    <Col span={8}>
                                        <div style={{ padding: '10px 12px', borderRadius: 10, background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)' }}>
                                            <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 4 }}>综合得分</div>
                                            <div style={{ fontSize: 18, fontWeight: 700, color: TEXT_PRIMARY }}>
                                                {selectedIndustrySnapshot?.score != null ? selectedIndustrySnapshot.score.toFixed(1) : '-'}
                                            </div>
                                        </div>
                                    </Col>
                                    <Col span={8}>
                                        <div style={{ padding: '10px 12px', borderRadius: 10, background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)' }}>
                                            <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 4 }}>涨跌幅</div>
                                            <div style={{ fontSize: 18, fontWeight: 700, color: (selectedIndustrySnapshot?.change_pct || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                                                {selectedIndustrySnapshot?.change_pct != null ? `${selectedIndustrySnapshot.change_pct >= 0 ? '+' : ''}${selectedIndustrySnapshot.change_pct.toFixed(2)}%` : '-'}
                                            </div>
                                        </div>
                                    </Col>
                                    <Col span={8}>
                                        <div style={{ padding: '10px 12px', borderRadius: 10, background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)' }}>
                                            <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 4 }}>资金流向</div>
                                            <div style={{ fontSize: 18, fontWeight: 700, color: (selectedIndustrySnapshot?.money_flow || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                                                {selectedIndustrySnapshot?.money_flow != null ? `${selectedIndustrySnapshot.money_flow >= 0 ? '+' : ''}${(selectedIndustrySnapshot.money_flow / 1e8).toFixed(1)}亿` : '-'}
                                            </div>
                                        </div>
                                    </Col>
                                </Row>

                                {selectedIndustryReasons.length > 0 && (
                                    <div style={{
                                        padding: '10px 12px',
                                        borderRadius: 10,
                                        background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)'
                                    }}>
                                        <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 8, fontWeight: 700, letterSpacing: '0.04em' }}>
                                            为什么值得看
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                            {selectedIndustryReasons.map((reason) => (
                                                <div key={reason} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                                                    <span style={{ color: 'var(--accent-primary)', fontWeight: 700, lineHeight: 1.6 }}>•</span>
                                                    <span style={{ fontSize: 12, lineHeight: 1.7, color: TEXT_PRIMARY }}>{reason}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                <Space size={8} wrap>
                                    <Button type="primary" size="small" onClick={() => {
                                        if (selectedIndustry) {
                                            loadIndustryStocks(selectedIndustry);
                                            setDetailVisible(true);
                                        }
                                    }}>
                                        查看行业详情
                                    </Button>
                                    <Button size="small" icon={<BranchesOutlined />} onClick={() => handleAddToComparison(selectedIndustry)}>
                                        加入轮动对比
                                    </Button>
                                </Space>
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                <div style={{ fontSize: 12, color: TEXT_SECONDARY, lineHeight: 1.7 }}>
                                    从左侧热力图、排行榜或下面推荐标签中选一个行业，右侧会自动切到该行业的龙头股与研究动作。
                                </div>
                                {focusIndustrySuggestions.length > 0 && (
                                    <Space size={[6, 6]} wrap>
                                        {focusIndustrySuggestions.map((industry) => (
                                            <Tag
                                                key={industry}
                                                color="processing"
                                                style={{ margin: 0, cursor: 'pointer', borderRadius: 999, paddingInline: 8 }}
                                                onClick={() => handleIndustryClick(industry)}
                                            >
                                                {industry}
                                            </Tag>
                                        ))}
                                    </Space>
                                )}
                            </div>
                        )}
                    </Card>

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
        </Layout>
    );
};

export default IndustryDashboard;
