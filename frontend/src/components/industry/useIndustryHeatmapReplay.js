import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { getIndustryHeatmapHistory } from '../../services/api';
import { formatIndustryAlertMoneyFlow, scheduleDeferredTask } from './industryShared';

const MAX_HEATMAP_REPLAY_SNAPSHOTS = 10;
const INDUSTRY_REPLAY_STORAGE_KEY = 'industry_heatmap_replay_snapshots_v1';
const INDUSTRY_REPLAY_SELECTION_KEY = 'industry_heatmap_replay_selected_v1';
const HEATMAP_REPLAY_RETENTION_MS = 24 * 60 * 60 * 1000;

export const HEATMAP_REPLAY_WINDOW_OPTIONS = [
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

export default function useIndustryHeatmapReplay({
    heatmapViewState,
    marketCapFilter,
    selectedIndustry,
    setSelectedIndustry,
}) {
    const replayHistoryFetchStartedRef = useRef(false);
    const [heatmapSummary, setHeatmapSummary] = useState(null);
    const [heatmapIndustries, setHeatmapIndustries] = useState([]);
    const [heatmapReplaySnapshots, setHeatmapReplaySnapshots] = useState([]);
    const [selectedReplaySnapshotId, setSelectedReplaySnapshotId] = useState(null);
    const [latestLiveHeatmapData, setLatestLiveHeatmapData] = useState(null);
    const [replayWindow, setReplayWindow] = useState('24h');
    const [comparisonBaseSnapshotId, setComparisonBaseSnapshotId] = useState(null);
    const [replayDiffIndustry, setReplayDiffIndustry] = useState(null);

    useEffect(() => {
        try {
            const storedSnapshotsRaw = window.localStorage.getItem(INDUSTRY_REPLAY_STORAGE_KEY);
            let localSnapshots = [];
            if (storedSnapshotsRaw) {
                const parsedSnapshots = JSON.parse(storedSnapshotsRaw);
                localSnapshots = pruneReplaySnapshots(Array.isArray(parsedSnapshots) ? parsedSnapshots : []);
            }

            const storedSelectedSnapshotId = window.localStorage.getItem(INDUSTRY_REPLAY_SELECTION_KEY);
            if (storedSelectedSnapshotId) {
                setSelectedReplaySnapshotId(storedSelectedSnapshotId);
            }

            if (localSnapshots.length > 0) {
                setHeatmapReplaySnapshots(localSnapshots);
            }
        } catch (error) {
            console.warn('Failed to hydrate industry replay snapshots from local storage:', error);
        }
    }, []);

    useEffect(() => {
        if (replayHistoryFetchStartedRef.current) return undefined;
        if (!heatmapIndustries.length) return undefined;

        replayHistoryFetchStartedRef.current = true;
        let isActive = true;

        const cancelIdleTask = scheduleDeferredTask(async () => {
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

                if (!isActive || backendSnapshots.length <= 0) return;
                setHeatmapReplaySnapshots((current) => {
                    const byId = new Map();
                    [...backendSnapshots, ...current].forEach((snapshot) => {
                        if (!snapshot?.id || byId.has(snapshot.id)) return;
                        byId.set(snapshot.id, snapshot);
                    });
                    return pruneReplaySnapshots(Array.from(byId.values()));
                });
            } catch (error) {
                console.warn('Failed to hydrate industry replay snapshots from backend history:', error);
            }
        }, 1600);

        return () => {
            isActive = false;
            cancelIdleTask();
        };
    }, [heatmapIndustries.length]);

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

    const applyHeatmapSnapshot = useCallback((data) => {
        if (!data?.industries?.length) return;
        const industries = data.industries;
        setHeatmapIndustries(industries);
        const total = industries.length;
        const upCount = industries.filter((item) => item.value > 0).length;
        const downCount = industries.filter((item) => item.value < 0).length;
        const flatCount = industries.filter((item) => item.value === 0).length;
        const upRatio = total > 0 ? Math.round((upCount / total) * 100) : 0;

        const avgChange = industries.reduce((acc, item) => acc + item.value, 0) / (total || 1);
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
        const topInflow = sorted.filter((item) => (item.moneyFlow || 0) > 0).slice(0, 3);
        const topOutflow = [...industries]
            .sort((a, b) => (a.moneyFlow || 0) - (b.moneyFlow || 0))
            .filter((item) => (item.moneyFlow || 0) < 0)
            .slice(0, 2);
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
            },
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
    }, [setSelectedIndustry]);

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

            return existingIndex >= 0
                ? current.map((item, index) => (index === existingIndex ? { ...item, ...snapshot, id: item.id } : item))
                : [snapshot, ...current].slice(0, MAX_HEATMAP_REPLAY_SNAPSHOTS);
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

    return {
        activeReplayDiffIndustry,
        activeReplaySnapshot,
        comparisonBaseSnapshotId,
        filteredReplaySnapshots,
        formatReplayDelta,
        formatReplayMetricMoney,
        formatReplayMetricPercent,
        formatReplaySnapshotTime,
        handleHeatmapDataLoad,
        handleReplayDiffIndustrySelect,
        heatmapIndustries,
        heatmapReplaySnapshots,
        heatmapReplayWindowOptions: HEATMAP_REPLAY_WINDOW_OPTIONS,
        heatmapSummary,
        latestReplaySnapshot,
        replayComparison,
        replayIndustryDiffDetail,
        replayTargetSnapshot,
        replayWindow,
        selectedReplaySnapshotId,
        setComparisonBaseSnapshotId,
        setReplayWindow,
        setSelectedReplaySnapshotId,
    };
}
