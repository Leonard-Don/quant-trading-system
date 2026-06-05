
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Card, Spin, Empty, message, Button, Grid } from 'antd';
import {
    ReloadOutlined,
    FireOutlined,
} from '@ant-design/icons';
import { getIndustryHeatmap, getIndustryHeatmapHistory, getPolicyRadarSignal } from '../services/api';
import {
    buildPolicyOverlay,
} from '../utils/industryPolicyOverlay';
import HeatmapLegend from './industry/HeatmapLegend';
import HeatmapStatsBar from './industry/HeatmapStatsBar';
import HeatmapControls from './industry/HeatmapControls';
import HeatmapTreemap from './industry/HeatmapTreemap';
import {
    HEATMAP_LIVE_REQUEST_TIMEOUT_MS,
    HEATMAP_HISTORY_FALLBACK_TIMEOUT_MS,
} from '../utils/industryHeatmapTokens';
import {
    buildFallbackHeatmapPayload,
} from '../utils/industrySearch';

const { useBreakpoint } = Grid;

// Re-exported for backward compatibility with existing tests that import
// `buildFallbackHeatmapPayload` from this module.
export { buildFallbackHeatmapPayload };

// ========================================
// IndustryHeatmap 组件
// ========================================

/**
 * 行业热力图组件
 * 使用 Squarified Treemap 展示各行业涨跌幅，方块大小反映市值
 */
const IndustryHeatmap = ({
    onIndustryClick,
    onDataLoad,
    onLeadingStockClick,
    replaySnapshot = null,
    initialData = null,
    bootstrapLoading = false,
    marketCapFilter = 'all',
    onClearMarketCapFilter,
    onSelectMarketCapFilter,
    timeframeValue,
    sizeMetricValue,
    colorMetricValue,
    displayCountValue,
    searchTermValue,
    onTimeframeChange,
    onSizeMetricChange,
    onColorMetricChange,
    onDisplayCountChange,
    onSearchTermChange,
    legendRangeValue,
    onLegendRangeChange,
    focusControlKey,
    showStats = true,
    onToggleFullscreen,
    isFullscreen = false,
}) => {
    const screens = useBreakpoint();
    const isCompactMobile = !screens.md;
    const [refreshSec, setRefreshSec] = useState(60);
    const [data, setData] = useState(() => (initialData?.industries?.length ? initialData : null));
    const [loading, setLoading] = useState(() => !initialData?.industries?.length);
    const [error, setError] = useState(null);
    const [loadSource, setLoadSource] = useState(() => (initialData?.industries?.length ? 'bootstrap' : ''));
    const [containerNode, setContainerNode] = useState(null);
    const [containerSize, setContainerSize] = useState({ width: 800, height: 450 });
    const [searchTerm, setSearchTerm] = useState('');
    const [displayCount, setDisplayCount] = useState(30);
    const [timeframe, setTimeframe] = useState(1); // 新增时间维度

    // 视图状态
    const [sizeMetric, setSizeMetric] = useState('market_cap'); // 方块大小: market_cap, turnover, net_inflow
    const [colorMetric, setColorMetric] = useState('change_pct'); // 颜色含义: change_pct, net_inflow_ratio, turnover_rate

    // 政策叠加：把 policy_radar industry_signals 叠加到 tile 右上角徽标。
    // 默认 off 不破坏既有视觉；on 时才发起一次请求。
    const [policyOverlayOn, setPolicyOverlayOn] = useState(false);
    const [policyIndustrySignals, setPolicyIndustrySignals] = useState(null);
    const [policyOverlayLoading, setPolicyOverlayLoading] = useState(false);
    // 政策色彩覆盖模式：与默认温度着色并行的可选着色方案，
    // ON 时 tile 背景按 policy_signal 着色（红=偏多/绿=偏空/灰=中性），
    // OFF 时回归 colorMetric 决定的温度着色。两套着色互不替换。
    const [policyColorMode, setPolicyColorMode] = useState(false);

    // AbortController refs
    const loadDataAbortRef = useRef(null);

    // Lazy-fetch policy radar signal when either the badge overlay or the
    // policy color-mode is toggled on. Cache the result so toggling either
    // off then back on doesn't re-hit the network unnecessarily within the
    // same component lifecycle.
    useEffect(() => {
        if (!policyOverlayOn && !policyColorMode) return undefined;
        if (policyIndustrySignals !== null) return undefined;
        let cancelled = false;
        setPolicyOverlayLoading(true);
        getPolicyRadarSignal()
            .then((response) => {
                if (cancelled) return;
                const payload = response?.data || {};
                setPolicyIndustrySignals(payload.industry_signals || {});
            })
            .catch(() => {
                if (cancelled) return;
                // Don't toast — overlay is opt-in and best-effort.
                setPolicyIndustrySignals({});
            })
            .finally(() => {
                if (!cancelled) setPolicyOverlayLoading(false);
            });
        return () => { cancelled = true; };
    }, [policyOverlayOn, policyColorMode, policyIndustrySignals]);

    // Memoize the normalized overlay map. Recomputes when either the
    // policy payload or the rendered industry list changes.
    // 注意：badge 叠加和 color 模式都依赖同一张 lookup map，所以只要任一开关 on
    // 都要构建一次。否则 color 模式开启时 tile 拿不到 policy 数据。
    const policyOverlayMap = useMemo(() => {
        if ((!policyOverlayOn && !policyColorMode) || !policyIndustrySignals) return null;
        return buildPolicyOverlay(data?.industries || [], policyIndustrySignals);
    }, [policyOverlayOn, policyColorMode, policyIndustrySignals, data]);

    useEffect(() => {
        if (!focusControlKey) return undefined;
        const selectorMap = {
            market_cap_filter: '.heatmap-control-market-cap-filter',
            timeframe: '.heatmap-control-timeframe',
            size_metric: '.heatmap-control-size-metric',
            color_metric: '.heatmap-control-color-metric',
            display_count: '.heatmap-control-display-count',
            search: '.heatmap-control-search',
        };
        const timeoutId = window.setTimeout(() => {
            const node = document.querySelector(selectorMap[focusControlKey]);
            if (node) {
                node.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
                const focusTarget = node.querySelector('input, button, .ant-select-selector');
                if (focusTarget?.focus) {
                    focusTarget.focus();
                }
            }
        }, 120);
        return () => window.clearTimeout(timeoutId);
    }, [focusControlKey]);

    useEffect(() => {
        if (timeframeValue != null) {
            setTimeframe(timeframeValue);
        }
    }, [timeframeValue]);

    useEffect(() => {
        if (sizeMetricValue) {
            setSizeMetric(sizeMetricValue);
        }
    }, [sizeMetricValue]);

    useEffect(() => {
        if (colorMetricValue) {
            setColorMetric(colorMetricValue);
        }
    }, [colorMetricValue]);

    useEffect(() => {
        if (displayCountValue != null) {
            setDisplayCount(displayCountValue);
        }
    }, [displayCountValue]);

    useEffect(() => {
        if (typeof searchTermValue === 'string') {
            setSearchTerm(searchTermValue);
        }
    }, [searchTermValue]);

    useEffect(() => {
        if (!replaySnapshot?.data) return undefined;
        if (loadDataAbortRef.current) {
            loadDataAbortRef.current.abort();
        }
        setError(null);
        setLoading(false);
        setLoadSource('replay');
        setData(replaySnapshot.data);
        return undefined;
    }, [replaySnapshot]);

    useEffect(() => {
        if (!initialData?.industries?.length || replaySnapshot?.data) return;
        if (loadDataAbortRef.current) {
            loadDataAbortRef.current.abort();
        }
        setError(null);
        setLoading(false);
        setLoadSource('bootstrap');
        setData(initialData);
        onDataLoad?.(initialData);
    }, [initialData, onDataLoad, replaySnapshot]);

    // 响应式容器尺寸监听
    useEffect(() => {
        if (!containerNode) return;

        const updateSize = () => {
            const { width } = containerNode.getBoundingClientRect();
            if (width > 0) {
                // Finding the "Golden" Aspect Ratio for Squarified Treemap:
                // 1.0 causes a horizontal strip at the bottom for Top 30 due to data distribution.
                // 0.6 causes a vertical strip on the right.
                // 0.8 is the balanced sweet spot to keep blocks squarish for a 30-item set.
                // For 'All' (displayCount = 0) and 'Top 50', we use 1.0 for maximum vertical expansion.
                const count = displayCount > 0 ? displayCount : 100;
                const ratio = count > 35 ? 1.0 : 0.8;
                setContainerSize({
                    width: Math.max(width - 2, 300),
                    height: Math.max(Math.round(width * ratio), 320)
                });
            }
        };

        const observer = new ResizeObserver(updateSize);
        observer.observe(containerNode);

        // Initial update
        updateSize();

        return () => observer.disconnect();
    }, [containerNode, displayCount]);

    const loadHistoryFallback = useCallback(async (currentAbort, reason = 'error') => {
        try {
            const historyResponse = await getIndustryHeatmapHistory(
                { limit: 6, days: timeframe },
                {
                    signal: currentAbort.signal,
                    timeout: HEATMAP_HISTORY_FALLBACK_TIMEOUT_MS,
                }
            );
            if (loadDataAbortRef.current !== currentAbort) return false;

            const fallbackPayload = buildFallbackHeatmapPayload(historyResponse, timeframe);
            if (!fallbackPayload?.industries?.length) {
                return false;
            }

            setData(fallbackPayload);
            setError(null);
            setLoadSource('history');
            onDataLoad?.(fallbackPayload);
            message.warning(
                reason === 'empty'
                    ? '行业热力图暂时无实时结果，已切换到最近快照'
                    : '行业热力图实时链路异常，已切换到最近快照'
            );
            return true;
        } catch (fallbackError) {
            if (fallbackError?.name === 'CanceledError') {
                return false;
            }
            if (loadDataAbortRef.current !== currentAbort) {
                return false;
            }
            console.error('Failed to load industry heatmap history fallback:', fallbackError);
            return false;
        }
    }, [onDataLoad, timeframe]);

    // 加载热力图数据
    const loadData = useCallback(async () => {
        if (replaySnapshot?.data) {
            setData(replaySnapshot.data);
            setLoading(false);
            setError(null);
            setLoadSource('replay');
            return;
        }
        if (loadDataAbortRef.current) {
            loadDataAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        loadDataAbortRef.current = currentAbort;

        let isCanceled = false;
        try {
            setLoading(true);
            setError(null);
            setLoadSource('');
            const result = await getIndustryHeatmap(timeframe, {
                signal: currentAbort.signal,
                timeout: HEATMAP_LIVE_REQUEST_TIMEOUT_MS,
            });
            if (loadDataAbortRef.current !== currentAbort) return;
            if (!result?.industries?.length) {
                const usedFallback = await loadHistoryFallback(currentAbort, 'empty');
                if (usedFallback) {
                    return;
                }
            }
            setData(result);
            setLoadSource('live');
            onDataLoad?.(result);
        } catch (err) {
            if (err.name === 'CanceledError') {
                isCanceled = true;
                return;
            }
            if (loadDataAbortRef.current !== currentAbort) return;
            const usedFallback = await loadHistoryFallback(currentAbort, 'error');
            if (usedFallback) {
                return;
            }
            console.error('Failed to load industry heatmap:', err);
            setError(err.userMessage || '加载行业数据失败');
            setLoadSource('');
            message.error('加载行业数据失败');
        } finally {
            if (!isCanceled && loadDataAbortRef.current === currentAbort) {
                setLoading(false);
            }
        }
    }, [loadHistoryFallback, onDataLoad, replaySnapshot, timeframe]);

    useEffect(() => {
        if (replaySnapshot?.data) {
            return () => {
                if (loadDataAbortRef.current) {
                    loadDataAbortRef.current.abort();
                }
            };
        }
        if (bootstrapLoading) {
            setLoading(true);
            setError(null);
            setLoadSource('');
            return () => {
                if (loadDataAbortRef.current) {
                    loadDataAbortRef.current.abort();
                }
            };
        }
        if (initialData?.industries?.length) {
            return () => {
                if (loadDataAbortRef.current) {
                    loadDataAbortRef.current.abort();
                }
            };
        }
        loadData();
        
        return () => {
            if (loadDataAbortRef.current) {
                loadDataAbortRef.current.abort();
            }
        };
    }, [bootstrapLoading, initialData, loadData, replaySnapshot]);

    // 自动刷新
    useEffect(() => {
        if (replaySnapshot?.data) return undefined;
        if (refreshSec > 0) {
            const timer = setInterval(loadData, refreshSec * 1000);
            return () => clearInterval(timer);
        }
    }, [refreshSec, loadData, replaySnapshot]);

    // 红涨绿跌渐变色计算（共用逻辑）
    const redGreenGradient = useCallback((value, absMax) => {
        // Slate-grey for true zero: pairs better with the dark theme + white
        // text than the older neutral #555 (contrast ratio ~6.5:1 vs #f8fafc).
        if (value === 0) return '#475569';
        const clampedMax = Math.max(absMax, 2);
        const intensity = Math.min(Math.abs(value) / clampedMax, 1);
        const t = Math.pow(intensity, 0.7);
        if (value > 0) {
            return `rgb(${Math.round(160 + t * 75)}, ${Math.round(80 - t * 65)}, ${Math.round(70 - t * 55)})`;
        } else {
            return `rgb(${Math.round(60 - t * 45)}, ${Math.round(140 + t * 50)}, ${Math.round(80 - t * 50)})`;
        }
    }, []);

    const matchesMarketCapFilter = useCallback((item) => {
        const source = String(item?.marketCapSource || 'unknown');
        if (marketCapFilter === 'all') return true;
        if (marketCapFilter === 'snapshot') return source.startsWith('snapshot_');
        if (marketCapFilter === 'proxy') return source === 'sina_proxy_stock_sum';
        if (marketCapFilter === 'estimated') return source === 'unknown' || source.startsWith('estimated');
        if (marketCapFilter === 'live') {
            return !source.startsWith('snapshot_')
                && source !== 'sina_proxy_stock_sum'
                && source !== 'unknown'
                && !source.startsWith('estimated');
        }
        return true;
    }, [marketCapFilter]);

    const getMarketCapDisplayKind = useCallback((item) => {
        const source = String(item?.marketCapSource || 'unknown');
        if (source.startsWith('snapshot_')) return 'snapshot';
        if (source === 'sina_proxy_stock_sum') return 'proxy';
        if (source === 'unknown' || source.startsWith('estimated') || source === 'constant_fallback') return 'estimated';
        return 'live';
    }, []);

    const getVolatilitySourceMeta = useCallback((source) => {
        switch (source) {
            case 'historical_index':
                return { label: '历史指数', color: '#69c0ff' };
            case 'stock_dispersion':
                return { label: '成分股离散度', color: '#95de64' };
            case 'amplitude_proxy':
                return { label: '振幅代理', color: '#ffd666' };
            case 'turnover_rate_proxy':
                return { label: '换手率代理', color: '#ffbb96' };
            case 'change_proxy':
                return { label: '涨跌幅代理', color: '#d3adf7' };
            default:
                return { label: '暂无', color: '#8c8c8c' };
        }
    }, []);

    const legendMeta = useMemo(() => {
        if (colorMetric === 'net_inflow_ratio') {
            return { min: -3, max: 3, step: 0.1, leftLabel: '净流出', rightLabel: '净流入', suffix: '%' };
        }
        if (colorMetric === 'turnover_rate') {
            return { min: 0, max: 8, step: 0.1, leftLabel: '低换手', rightLabel: '高换手', suffix: '%' };
        }
        if (colorMetric === 'pe_ttm') {
            return { min: 0, max: 80, step: 1, leftLabel: '低估值', rightLabel: '高估值', suffix: 'x' };
        }
        if (colorMetric === 'pb') {
            return { min: 0, max: 10, step: 0.1, leftLabel: '低PB', rightLabel: '高PB', suffix: 'x' };
        }
        const maxAbs = data?.max_value !== undefined
            ? Math.max(Math.abs(data.max_value || 0), Math.abs(data.min_value || 0), 5)
            : 5;
        return { min: -maxAbs, max: maxAbs, step: 0.1, leftLabel: '跌/出', rightLabel: '涨/入', suffix: '%' };
    }, [colorMetric, data]);

    const effectiveLegendRange = useMemo(() => {
        if (
            Array.isArray(legendRangeValue)
            && legendRangeValue.length === 2
            && Number.isFinite(Number(legendRangeValue[0]))
            && Number.isFinite(Number(legendRangeValue[1]))
        ) {
            return [Number(legendRangeValue[0]), Number(legendRangeValue[1])];
        }
        return [legendMeta.min, legendMeta.max];
    }, [legendMeta.max, legendMeta.min, legendRangeValue]);

    // 计算颜色
    const getColor = useCallback((value, metric, dynamicMax = 5) => {
        if (metric === 'change_pct') {
            return redGreenGradient(value, dynamicMax);
        }
        else if (metric === 'net_inflow_ratio') {
            return redGreenGradient(value, 2); // +/- 2% 为饱和点
        }
        else if (metric === 'pe_ttm') {
            // PE: 低估值(绿/灰) -> 高估值(红)
            // 简单逻辑：20以下绿色，40以上红色
            if (value <= 0) return '#555555';
            if (value < 20) return `rgb(60, 140, 80)`; // 稳重绿
            if (value < 40) return `rgb(200, 180, 60)`; // 警示黄
            return `rgb(220, 60, 60)`; // 危险红
        }
        else if (metric === 'pb') {
             // PB: < 1 绿, > 5 红
             if (value <= 0) return '#555555';
             if (value < 1.5) return `rgb(60, 140, 80)`;
             if (value < 4) return `rgb(200, 180, 60)`;
             return `rgb(220, 60, 60)`;
        }
        else if (metric === 'turnover_rate') {
            // 换手率：热度图（蓝 -> 黄 -> 红）
            const max = 5; // 5% 以上为高换手
            const t = Math.min(Math.max(value, 0) / max, 1);
            if (t < 0.5) {
                const ratio = t * 2;
                return `rgb(${Math.round(ratio * 255)}, ${Math.round(ratio * 255)}, ${Math.round(255 - ratio * 155)})`;
            } else {
                const ratio = (t - 0.5) * 2;
                return `rgb(255, ${Math.round(255 - ratio * 200)}, ${Math.round(100 - ratio * 100)})`;
            }
        }
        return '#555555';
    }, [redGreenGradient]);

    // 格式化数字（亿元）
    const formatBillion = useCallback((value) => {
        if (!value || value === 0) return '-';
        const billion = value / 100000000;
        if (Math.abs(billion) >= 1) return `${billion >= 0 ? '+' : ''}${billion.toFixed(2)} 亿`;
        const wan = value / 10000;
        return `${wan >= 0 ? '+' : ''}${wan.toFixed(0)} 万`;
    }, []);

    // 渲染统计信息
    // renderStats 拆到 ./industry/HeatmapStatsBar.js（layer 2 第二个子组件）
    const renderStats = (
        <HeatmapStatsBar data={data} onIndustryClick={onIndustryClick} />
    );

    // 使用 Treemap 计算布局和渲染 — 拆到 ./industry/HeatmapTreemap.jsx（layer 2 子组件）
    const renderTreemap = (
        <HeatmapTreemap
            data={data}
            containerSize={containerSize}
            setContainerNode={setContainerNode}
            loadData={loadData}
            sizeMetric={sizeMetric}
            colorMetric={colorMetric}
            marketCapFilter={marketCapFilter}
            matchesMarketCapFilter={matchesMarketCapFilter}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            onSearchTermChange={onSearchTermChange}
            displayCount={displayCount}
            effectiveLegendRange={effectiveLegendRange}
            legendRangeValue={legendRangeValue}
            onLegendRangeChange={onLegendRangeChange}
            onClearMarketCapFilter={onClearMarketCapFilter}
            onSelectMarketCapFilter={onSelectMarketCapFilter}
            onIndustryClick={onIndustryClick}
            onLeadingStockClick={onLeadingStockClick}
            getColor={getColor}
            getMarketCapDisplayKind={getMarketCapDisplayKind}
            getVolatilitySourceMeta={getVolatilitySourceMeta}
            formatBillion={formatBillion}
            policyOverlayMap={policyOverlayMap}
            policyColorMode={policyColorMode}
        />
    );

    // 计算资金流入 TOP3（用于图例横幅，来自内存数据无需新 API）
    const top3InflowBanner = useMemo(() => {
        if (!data?.industries) return [];
        return [...data.industries]
            .filter(i => (i.moneyFlow || 0) > 0)
            .sort((a, b) => (b.moneyFlow || 0) - (a.moneyFlow || 0))
            .slice(0, 3);
    }, [data]);

    // 渲染图例 — 拆到 ./industry/HeatmapLegend.js（layer 2 子组件）
    const renderLegend = (
        <HeatmapLegend
            legendMeta={legendMeta}
            effectiveLegendRange={effectiveLegendRange}
            colorMetric={colorMetric}
            sizeMetric={sizeMetric}
            onLegendRangeChange={onLegendRangeChange}
            top3InflowBanner={top3InflowBanner}
            onIndustryClick={onIndustryClick}
        />
    );

    // 工具栏控件 — 拆到 ./industry/HeatmapControls.jsx（layer 2 子组件）
    const renderControls = (
        <HeatmapControls
            isCompactMobile={isCompactMobile}
            timeframe={timeframe}
            setTimeframe={setTimeframe}
            onTimeframeChange={onTimeframeChange}
            sizeMetric={sizeMetric}
            setSizeMetric={setSizeMetric}
            onSizeMetricChange={onSizeMetricChange}
            colorMetric={colorMetric}
            setColorMetric={setColorMetric}
            onColorMetricChange={onColorMetricChange}
            displayCount={displayCount}
            setDisplayCount={setDisplayCount}
            onDisplayCountChange={onDisplayCountChange}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            onSearchTermChange={onSearchTermChange}
            refreshSec={refreshSec}
            setRefreshSec={setRefreshSec}
            policyOverlayOn={policyOverlayOn}
            setPolicyOverlayOn={setPolicyOverlayOn}
            policyOverlayLoading={policyOverlayLoading}
            policyColorMode={policyColorMode}
            setPolicyColorMode={setPolicyColorMode}
            loadSource={loadSource}
            loading={loading}
            loadData={loadData}
            replaySnapshot={replaySnapshot}
            focusControlKey={focusControlKey}
            isFullscreen={isFullscreen}
            onToggleFullscreen={onToggleFullscreen}
        />
    );

    if (loading) {
        // 骨架屏：模拟热力图方块布局，减少等待焦虑
        const skeletonBlocks = [
            { w: '28%', h: 90 }, { w: '22%', h: 90 }, { w: '18%', h: 90 }, { w: '30%', h: 90 },
            { w: '35%', h: 70 }, { w: '25%', h: 70 }, { w: '40%', h: 70 },
            { w: '20%', h: 55 }, { w: '30%', h: 55 }, { w: '25%', h: 55 }, { w: '25%', h: 55 },
        ];
        return (
            <Card
                className="industry-heatmap-card"
                title={<span><FireOutlined style={{ marginRight: 8, color: 'var(--accent-danger)' }} />行业热力图</span>}
                extra={renderControls}
                styles={isCompactMobile ? { body: { padding: 12 } } : undefined}
            >
                <div style={{
                    display: 'flex', flexWrap: 'wrap', gap: 3,
                    background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 82%, var(--bg-primary) 18%) 0%, var(--bg-secondary) 100%)', borderRadius: 8, padding: 3,
                    minHeight: 300, position: 'relative', overflow: 'hidden'
                }}>
                    {skeletonBlocks.map((b, i) => (
                        <div key={i} style={{
                            width: b.w, height: b.h, borderRadius: 3,
                            background: `color-mix(in srgb, var(--bg-tertiary) ${18 + (i % 3) * 8}%, transparent)`,
                            animation: 'pulse 1.8s ease-in-out infinite',
                            animationDelay: `${i * 0.12}s`,
                        }} className="industry-heatmap-skeleton-block" />
                    ))}
                    <div style={{
                        position: 'absolute', top: '50%', left: '50%',
                        transform: 'translate(-50%, -50%)',
                        textAlign: 'center', zIndex: 2
                    }}>
                        <Spin size="large" />
                        <div style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
                            正在加载行业数据…
                        </div>
                    </div>
                </div>
                <style>{`@keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 0.8; } }`}</style>
            </Card>
        );
    }

    if (error) {
        return (
            <Card
                className="industry-heatmap-card"
                title="行业热力图"
                extra={
                    <Button className="industry-inline-link" type="link" size="small" onClick={loadData} style={{ padding: 0 }}>
                        <ReloadOutlined /> 重试
                    </Button>
                }
            >
                <Empty description={error} />
            </Card>
        );
    }

    return (
        <Card
            className="industry-heatmap-card"
            title={
                <span>
                    <FireOutlined style={{ marginRight: 8, color: 'var(--accent-danger)' }} />
                    行业热力图
                </span>
            }
            extra={renderControls}
            styles={isCompactMobile ? { body: { padding: 12 } } : undefined}
        >
            {showStats && !isCompactMobile && renderStats}
            {renderTreemap}
            {renderLegend}
        </Card>
    );
};

export default IndustryHeatmap;
