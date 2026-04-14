import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { getHotIndustries, getIndustryClusters } from '../../services/api';
import { getMarketCapBadgeMeta } from './industryShared';

const useIndustryRanking = ({
    activeTab,
    rankType,
    sortBy,
    lookbackDays,
    volatilityFilter,
    rankingMarketCapFilter,
    heatmapIndustriesLength,
    message,
}) => {
    const [hotIndustries, setHotIndustries] = useState([]);
    const [loadingHot, setLoadingHot] = useState(false);
    const [hotRetryTick, setHotRetryTick] = useState(0);
    const [clusters, setClusters] = useState(null);
    const [loadingClusters, setLoadingClusters] = useState(false);
    const [clusterError, setClusterError] = useState(null);
    const [clusterCount, setClusterCount] = useState(4);
    const [selectedClusterPoint, setSelectedClusterPoint] = useState(null);
    const [shouldRenderLeaderPanel, setShouldRenderLeaderPanel] = useState(false);

    const hotRequestIdRef = useRef(0);
    const rankingPrefetchedRef = useRef(false);
    const clusterPrefetchedRef = useRef(false);
    const hotInFlightQueryKeyRef = useRef(null);
    const hotLoadedQueryKeyRef = useRef(null);
    const clusterAutoAttemptedRef = useRef(false);
    const hotIndustriesAbortRef = useRef(null);
    const clustersAbortRef = useRef(null);

    const buildHotQueryKey = useCallback((topN, type, sort, lookback) =>
        `top_n:${topN}|type:${type}|sort:${sort}|lookback:${lookback}`, []);

    const loadHotIndustries = useCallback(async (
        topN = 15,
        type = rankType,
        sort = sortBy,
        lookback = lookbackDays,
        silent = false
    ) => {
        const requestId = ++hotRequestIdRef.current;
        const queryKey = buildHotQueryKey(topN, type, sort, lookback);

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

    // 首次进入行业页时，等热力图首屏稳定后再空闲预取排行榜
    useEffect(() => {
        if (activeTab === 'ranking') return;
        if (rankingPrefetchedRef.current) return;
        if (!heatmapIndustriesLength) return undefined;

        let timeoutId = null;
        const schedulePrefetch = () => {
            if (rankingPrefetchedRef.current) return;
            rankingPrefetchedRef.current = true;
            loadHotIndustries(50, 'gainers', 'total_score', lookbackDays, true);
        };

        timeoutId = window.setTimeout(schedulePrefetch, 2200);

        return () => {
            if (timeoutId != null) {
                window.clearTimeout(timeoutId);
            }
        };
    }, [activeTab, lookbackDays, loadHotIndustries, heatmapIndustriesLength]);

    // 右侧龙头股面板延后挂载，让热力图优先完成冷启动渲染
    useEffect(() => {
        if (shouldRenderLeaderPanel) return undefined;
        if (activeTab === 'ranking' || heatmapIndustriesLength > 0) {
            const timeoutId = window.setTimeout(() => {
                setShouldRenderLeaderPanel(true);
            }, 900);
            return () => window.clearTimeout(timeoutId);
        }

        const fallbackId = window.setTimeout(() => {
            setShouldRenderLeaderPanel(true);
        }, 2200);
        return () => window.clearTimeout(fallbackId);
    }, [activeTab, heatmapIndustriesLength, shouldRenderLeaderPanel]);

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

    // 聚类分析耗时更久，首屏稳定后空闲预取一次
    useEffect(() => {
        if (activeTab === 'clusters') return;
        if (clusterPrefetchedRef.current) return;
        if (!heatmapIndustriesLength) return undefined;

        let timeoutId = null;
        const schedulePrefetch = () => {
            if (clusterPrefetchedRef.current) return;
            clusterPrefetchedRef.current = true;
            loadClusters(true);
        };

        timeoutId = window.setTimeout(schedulePrefetch, 3200);

        return () => {
            if (timeoutId != null) {
                window.clearTimeout(timeoutId);
            }
        };
    }, [activeTab, loadClusters, heatmapIndustriesLength]);

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

    // Cleanup abort controllers on unmount
    useEffect(() => () => {
        if (hotIndustriesAbortRef.current) hotIndustriesAbortRef.current.abort();
        if (clustersAbortRef.current) clustersAbortRef.current.abort();
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

    return {
        hotIndustries,
        loadingHot,
        clusters,
        loadingClusters,
        clusterError,
        clusterCount,
        setClusterCount,
        selectedClusterPoint,
        setSelectedClusterPoint,
        shouldRenderLeaderPanel,
        loadHotIndustries,
        loadClusters,
        filteredHotIndustries,
    };
};

export default useIndustryRanking;
