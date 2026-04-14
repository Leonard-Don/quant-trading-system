import { useCallback, useEffect, useState } from 'react';

export const INDUSTRY_URL_DEFAULTS = {
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

const readIndustryUrlState = () => {
    if (typeof window === 'undefined') {
        return { ...INDUSTRY_URL_DEFAULTS };
    }

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
    if (typeof window === 'undefined') return;

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

export default function useIndustryUrlState() {
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
    const [heatmapLegendRange, setHeatmapLegendRange] = useState(null);
    const [rankType, setRankType] = useState(initialUrlState.rankType);
    const [sortBy, setSortBy] = useState(initialUrlState.sortBy);
    const [lookbackDays, setLookbackDays] = useState(initialUrlState.lookbackDays);
    const [volatilityFilter, setVolatilityFilter] = useState(initialUrlState.volatilityFilter);
    const [rankingMarketCapFilter, setRankingMarketCapFilter] = useState(initialUrlState.rankingMarketCapFilter);
    const [focusedHeatmapControlKey, setFocusedHeatmapControlKey] = useState(null);
    const [focusedRankingControlKey, setFocusedRankingControlKey] = useState(null);

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
            setHeatmapViewState((prev) => ({ ...prev, timeframe: INDUSTRY_URL_DEFAULTS.timeframe }));
        } else if (key === 'size_metric') {
            setHeatmapViewState((prev) => ({ ...prev, sizeMetric: INDUSTRY_URL_DEFAULTS.sizeMetric }));
        } else if (key === 'color_metric') {
            setHeatmapViewState((prev) => ({ ...prev, colorMetric: INDUSTRY_URL_DEFAULTS.colorMetric }));
        } else if (key === 'display_count') {
            setHeatmapViewState((prev) => ({ ...prev, displayCount: INDUSTRY_URL_DEFAULTS.displayCount }));
        } else if (key === 'search') {
            setHeatmapViewState((prev) => ({ ...prev, searchTerm: INDUSTRY_URL_DEFAULTS.searchTerm }));
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

    const applyIndustryViewState = useCallback((state) => {
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
        const applyFromUrl = () => {
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

        window.addEventListener('popstate', applyFromUrl);
        return () => window.removeEventListener('popstate', applyFromUrl);
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

    return {
        activeTab,
        setActiveTab,
        marketCapFilter,
        setMarketCapFilter,
        heatmapViewState,
        setHeatmapViewState,
        heatmapLegendRange,
        setHeatmapLegendRange,
        rankType,
        setRankType,
        sortBy,
        setSortBy,
        lookbackDays,
        setLookbackDays,
        volatilityFilter,
        setVolatilityFilter,
        rankingMarketCapFilter,
        setRankingMarketCapFilter,
        focusedHeatmapControlKey,
        focusedRankingControlKey,
        toggleMarketCapFilter,
        jumpToMarketCapFilter,
        resetHeatmapViewState,
        clearHeatmapStateTag,
        focusHeatmapControl,
        resetRankingViewState,
        clearRankingStateTag,
        focusRankingControl,
        applyIndustryViewState,
    };
}
