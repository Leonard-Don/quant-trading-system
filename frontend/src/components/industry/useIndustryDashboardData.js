import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import useIndustryUrlState from './useIndustryUrlState';
import useIndustryHeatmapReplay from './useIndustryHeatmapReplay';
import useIndustryPreferences from './useIndustryPreferences';
import useIndustryRanking from './useIndustryRanking';
import useIndustryStocks from './useIndustryStocks';
import useIndustryAlerts from './useIndustryAlerts';
import useIndustrySelection from './useIndustrySelection';
import useIndustryWatchlist from './useIndustryWatchlist';
import { INDUSTRY_ALERT_KIND_OPTIONS } from './industryShared';
import { getIndustryBootstrap } from '../../services/api';

const MAX_WATCHLIST_INDUSTRIES = 12;
const INDUSTRY_BOOTSTRAP_RANKING_TOP_N = 50;
const INDUSTRY_BOOTSTRAP_LEADER_TOP_N = 5;
const INDUSTRY_BOOTSTRAP_TOP_INDUSTRIES = 5;
const INDUSTRY_BOOTSTRAP_PER_INDUSTRY = 3;

const useIndustryDashboardData = ({ message }) => {
    const [selectedIndustry, setSelectedIndustry] = useState(null);
    const [comparisonIndustries, setComparisonIndustries] = useState([]);
    const [industryBootstrap, setIndustryBootstrap] = useState(null);
    const [industryBootstrapLoading, setIndustryBootstrapLoading] = useState(true);
    const bootstrapAbortRef = useRef(null);

    const urlState = useIndustryUrlState();
    const bootstrapQuery = useMemo(() => ({
        days: urlState.heatmapViewState.timeframe,
        ranking_top_n: INDUSTRY_BOOTSTRAP_RANKING_TOP_N,
        leader_top_n: INDUSTRY_BOOTSTRAP_LEADER_TOP_N,
        top_industries: INDUSTRY_BOOTSTRAP_TOP_INDUSTRIES,
        per_industry: INDUSTRY_BOOTSTRAP_PER_INDUSTRY,
    }), [urlState.heatmapViewState.timeframe]);

    const replay = useIndustryHeatmapReplay({
        heatmapViewState: urlState.heatmapViewState,
        marketCapFilter: urlState.marketCapFilter,
        selectedIndustry,
        setSelectedIndustry,
    });

    useEffect(() => {
        if (replay.activeReplaySnapshot?.data) {
            setIndustryBootstrapLoading(false);
            return undefined;
        }

        if (bootstrapAbortRef.current) {
            bootstrapAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        bootstrapAbortRef.current = currentAbort;
        setIndustryBootstrap(null);
        setIndustryBootstrapLoading(true);

        getIndustryBootstrap(bootstrapQuery.days, {
            ranking_top_n: bootstrapQuery.ranking_top_n,
            leader_top_n: bootstrapQuery.leader_top_n,
            top_industries: bootstrapQuery.top_industries,
            per_industry: bootstrapQuery.per_industry,
        }, {
            signal: currentAbort.signal,
            timeout: 25000,
            suppressNetworkErrorLog: true,
        })
            .then((payload) => {
                if (bootstrapAbortRef.current !== currentAbort) return;
                setIndustryBootstrap(payload || null);
            })
            .catch((error) => {
                if (error?.name === 'CanceledError' || bootstrapAbortRef.current !== currentAbort) {
                    return;
                }
                console.warn('Industry bootstrap warmup failed, falling back to per-panel loading:', error);
                setIndustryBootstrap(null);
            })
            .finally(() => {
                if (bootstrapAbortRef.current === currentAbort) {
                    setIndustryBootstrapLoading(false);
                }
            });

        return () => {
            currentAbort.abort();
            if (bootstrapAbortRef.current === currentAbort) {
                bootstrapAbortRef.current = null;
            }
        };
    }, [bootstrapQuery, replay.activeReplaySnapshot]);

    const preferences = useIndustryPreferences({
        heatmapIndustriesLength: replay.heatmapIndustries.length,
        maxWatchlistIndustries: MAX_WATCHLIST_INDUSTRIES,
        message,
    });

    const ranking = useIndustryRanking({
        activeTab: urlState.activeTab,
        rankType: urlState.rankType,
        sortBy: urlState.sortBy,
        lookbackDays: urlState.lookbackDays,
        volatilityFilter: urlState.volatilityFilter,
        rankingMarketCapFilter: urlState.rankingMarketCapFilter,
        heatmapIndustriesLength: replay.heatmapIndustries.length,
        bootstrapHotIndustries: industryBootstrap?.hot_industries || [],
        bootstrapHotMeta: industryBootstrap ? {
            topN: industryBootstrap.ranking_top_n,
            type: industryBootstrap.ranking_type,
            sortBy: industryBootstrap.ranking_sort_by,
            lookbackDays: industryBootstrap.days,
        } : null,
        message,
    });

    const stocks = useIndustryStocks({
        message,
        setSelectedIndustry,
    });

    const alerts = useIndustryAlerts({
        heatmapIndustries: replay.heatmapIndustries,
        hotIndustries: ranking.hotIndustries,
        heatmapSummary: replay.heatmapSummary,
        industryAlertThresholds: preferences.industryAlertThresholds,
        industryAlertHistory: preferences.industryAlertHistory,
        setIndustryAlertHistory: preferences.setIndustryAlertHistory,
        industryAlertSubscription: preferences.industryAlertSubscription,
        desktopAlertNotifications: preferences.desktopAlertNotifications,
        watchlistIndustries: preferences.watchlistIndustries,
        selectedIndustry,
    });

    const selection = useIndustrySelection({
        filteredHotIndustries: ranking.filteredHotIndustries,
        heatmapIndustries: replay.heatmapIndustries,
        hotIndustries: ranking.hotIndustries,
        industryStocks: stocks.industryStocks,
        selectedIndustry,
        watchlistIndustries: preferences.watchlistIndustries,
    });

    const watchlist = useIndustryWatchlist({
        filteredHotIndustries: ranking.filteredHotIndustries,
        focusIndustrySuggestions: alerts.focusIndustrySuggestions,
        heatmapIndustries: replay.heatmapIndustries,
        hotIndustries: ranking.hotIndustries,
        rawIndustryAlerts: alerts.rawIndustryAlerts,
        replayComparison: replay.replayComparison,
        selectedIndustry,
        watchlistIndustries: preferences.watchlistIndustries,
    });

    const {
        activeTab,
        marketCapFilter,
        heatmapViewState,
        heatmapLegendRange,
        rankType,
        sortBy,
        lookbackDays,
        volatilityFilter,
        rankingMarketCapFilter,
        applyIndustryViewState,
        setActiveTab,
    } = urlState;
    const { clusterCount, setClusterCount } = ranking;
    const { replayWindow, setReplayWindow } = replay;
    const {
        industryAlertRule,
        industryAlertRecency,
        setIndustryAlertRule,
        setIndustryAlertRecency,
    } = alerts;
    const {
        industryAlertSubscription,
        setIndustryAlertSubscription,
        savedViewDraftName,
        savedIndustryViews,
        setSavedIndustryViews,
        setSavedViewDraftName,
    } = preferences;
    const { loadIndustryStocks } = stocks;

    // --- Cross-cutting saved-view callbacks ---

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
        applyIndustryViewState(state);
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
    }, [
        applyIndustryViewState,
        setClusterCount,
        setReplayWindow,
        setIndustryAlertRule,
        setIndustryAlertRecency,
        setIndustryAlertSubscription,
    ]);

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
    }, [captureCurrentViewState, message, savedIndustryViews, savedViewDraftName, setSavedIndustryViews, setSavedViewDraftName]);

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
    }, [captureCurrentViewState, message, setSavedIndustryViews]);

    const removeSavedIndustryView = useCallback((viewId) => {
        setSavedIndustryViews((current) => current.filter((item) => item.id !== viewId));
        message.success('已删除保存视图');
    }, [message, setSavedIndustryViews]);

    // --- Interaction handlers ---

    const handleIndustryClick = useCallback((industryName) => {
        setSelectedIndustry(industryName);
        loadIndustryStocks(industryName);
    }, [loadIndustryStocks]);

    const handleAddToComparison = useCallback((industryName) => {
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
    }, [comparisonIndustries, message, setActiveTab]);

    const openSelectedIndustryDetail = useCallback(() => {
        if (!selectedIndustry) return;
        loadIndustryStocks(selectedIndustry);
    }, [loadIndustryStocks, selectedIndustry]);

    useEffect(() => () => {
        if (bootstrapAbortRef.current) {
            bootstrapAbortRef.current.abort();
        }
    }, []);

    return {
        // URL state
        ...urlState,
        // Replay
        ...replay,
        // Preferences
        ...preferences,
        // Ranking
        ...ranking,
        // Stocks
        ...stocks,
        // Alerts
        ...alerts,
        // Selection
        ...selection,
        // Watchlist
        ...watchlist,
        industryBootstrap,
        industryBootstrapLoading,
        // Cross-cutting state
        selectedIndustry,
        setSelectedIndustry,
        comparisonIndustries,
        setComparisonIndustries,
        maxWatchlistIndustries: MAX_WATCHLIST_INDUSTRIES,
        // Saved view callbacks
        saveCurrentIndustryView,
        applySavedIndustryView,
        overwriteSavedIndustryView,
        removeSavedIndustryView,
        // Interaction handlers
        handleIndustryClick,
        handleAddToComparison,
        openSelectedIndustryDetail,
    };
};

export default useIndustryDashboardData;
