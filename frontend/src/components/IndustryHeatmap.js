
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Card, Spin, Empty, Tooltip, Typography, Tag, Row, Col, Statistic, message, Button, Input, Radio, Select, Space, Progress, Slider, Grid } from 'antd';
import {
    RiseOutlined,
    FallOutlined,
    ReloadOutlined,
    FireOutlined,
    DashboardOutlined,
    BarChartOutlined,
    BgColorsOutlined,
    SearchOutlined,
    FullscreenOutlined,
    FullscreenExitOutlined
} from '@ant-design/icons';
import { getIndustryHeatmap, getIndustryHeatmapHistory } from '../services/api';
import { activateOnEnterOrSpace } from './industry/industryShared';

const { Text } = Typography;
const { useBreakpoint } = Grid;
const HEATMAP_SURFACE = 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 90%, var(--bg-primary) 10%) 0%, color-mix(in srgb, var(--bg-secondary) 82%, var(--bg-primary) 18%) 100%)';
const TOOLTIP_BG = 'color-mix(in srgb, var(--bg-primary) 88%, #0f172a 12%)';
const TOOLTIP_PANEL = 'color-mix(in srgb, var(--bg-secondary) 92%, var(--bg-primary) 8%)';
const TOOLTIP_PANEL_BORDER = 'color-mix(in srgb, var(--border-color) 82%, var(--text-primary) 18%)';
const TOOLTIP_TEXT = 'var(--text-primary)';
const TOOLTIP_MUTED = 'var(--text-secondary)';
const TOOLTIP_SUBTLE = 'var(--text-muted)';
const TOOLTIP_SHADOW = '0 10px 30px rgba(15, 23, 42, 0.18)';
const HEATMAP_POSITIVE = 'var(--accent-danger)';
const HEATMAP_NEGATIVE = 'var(--accent-success)';
const HEATMAP_WARNING = 'var(--accent-warning)';
const TILE_TEXT_SHADOW = '0 1px 3px rgba(15, 23, 42, 0.32)';
const HEATMAP_LIVE_REQUEST_TIMEOUT_MS = 12000;
const HEATMAP_HISTORY_FALLBACK_TIMEOUT_MS = 6000;

const normalizeIndustrySearchText = (value) => String(value || '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[()（）]/g, '')
    .replace(/[-_/]/g, '')
    .replace(/及元件/g, '')
    .replace(/板块/g, '')
    .trim();

const buildIndustrySearchCandidates = (name) => {
    const raw = String(name || '').trim();
    if (!raw) return [];

    const canonical = raw.replace(/及元件/g, '').replace(/板块/g, '').trim();
    const variants = new Set([
        raw,
        normalizeIndustrySearchText(raw),
        canonical,
        normalizeIndustrySearchText(canonical),
    ]);

    return Array.from(variants).filter(Boolean);
};

const matchesIndustrySearch = (name, searchTerm) => {
    const normalizedQuery = normalizeIndustrySearchText(searchTerm);
    if (!normalizedQuery) return true;
    return buildIndustrySearchCandidates(name).some(
        (candidate) => normalizeIndustrySearchText(candidate).includes(normalizedQuery)
    );
};

const syncHeatmapTileFocusState = (node, active) => {
    if (!node) return;
    node.style.filter = active ? 'brightness(1.25)' : 'brightness(1)';
    node.style.zIndex = active ? '10' : '1';
    node.style.transform = active ? 'scale(1.02)' : 'scale(1)';
};

export const buildFallbackHeatmapPayload = (historyResponse, timeframe) => {
    const historyItems = Array.isArray(historyResponse?.items) ? historyResponse.items : [];
    const matchingItem = historyItems.find(
        (item) => Number(item?.days || 0) === Number(timeframe || 0) && Array.isArray(item?.industries) && item.industries.length > 0
    );
    const fallbackItem = matchingItem || historyItems.find((item) => Array.isArray(item?.industries) && item.industries.length > 0);

    if (!fallbackItem) {
        return null;
    }

    return {
        industries: fallbackItem.industries || [],
        max_value: fallbackItem.max_value ?? 0,
        min_value: fallbackItem.min_value ?? 0,
        update_time: fallbackItem.update_time || fallbackItem.captured_at || '',
    };
};

// ... (retain squarified treemap algorithms: worstAspectRatio, squarify, layoutRow) ...

/**
 * 计算一组行在当前 rect 中的布局
 * @param {Array} row - 当前行的数据项 (已含 normalizedSize)
 * @param {number} w - 当前短边长度
 * @returns {number} 最差纵横比
 */
function worstAspectRatio(row, w) {
    if (row.length === 0 || w <= 0) return Infinity;
    const s = row.reduce((acc, r) => acc + r.normalizedSize, 0);
    const maxArea = Math.max(...row.map(r => r.normalizedSize));
    const minArea = Math.min(...row.map(r => r.normalizedSize));
    return Math.max(
        (w * w * maxArea) / (s * s),
        (s * s) / (w * w * minArea)
    );
}

/**
 * Squarified Treemap 核心递归算法
 * 将 items 递归地排列到 rect 中
 */
function squarify(items, rect) {
    if (items.length === 0) return [];
    if (items.length === 1) {
        return [{ ...items[0], layout: { ...rect } }];
    }

    const { x, y, width, height } = rect;
    const totalArea = width * height;
    const totalSize = items.reduce((acc, item) => acc + item.normalizedSize, 0);

    if (totalSize <= 0 || totalArea <= 0) {
        return items.map(item => ({ ...item, layout: { x, y, width: 0, height: 0 } }));
    }

    // 归一化面积到像素面积
    const scale = totalArea / totalSize;
    const scaledItems = items.map(item => ({
        ...item,
        normalizedSize: item.normalizedSize * scale
    }));

    let currentRow = [];
    let remaining = [...scaledItems];
    let results = [];
    let currentRect = { ...rect };

    while (remaining.length > 0) {
        const isWide = currentRect.width >= currentRect.height;
        const shortSide = isWide ? currentRect.height : currentRect.width;
        const item = remaining[0];
        const testRow = [...currentRow, item];
        const currentWorst = worstAspectRatio(currentRow, shortSide);
        const testWorst = worstAspectRatio(testRow, shortSide);

        if (currentRow.length === 0 || testWorst <= currentWorst) {
            currentRow.push(item);
            remaining.shift();
        } else {
            // 固定当前行，递归处理剩余
            const rowResults = layoutRow(currentRow, currentRect, isWide);
            results.push(...rowResults.items);
            currentRect = rowResults.remainingRect;
            currentRow = [];
        }
    }

    // 最后一行
    if (currentRow.length > 0) {
        const isWide = currentRect.width >= currentRect.height;
        const rowResults = layoutRow(currentRow, currentRect, isWide);
        results.push(...rowResults.items);
    }

    return results;
}

/**
 * 在 rect 中排列一行
 */
function layoutRow(row, rect, isWide) {
    const { x, y, width, height } = rect;
    const rowArea = row.reduce((acc, r) => acc + r.normalizedSize, 0);
    const items = [];

    if (isWide) {
        const rowWidth = rowArea / height;
        let offsetY = y;
        for (const item of row) {
            const itemHeight = item.normalizedSize / rowWidth;
            items.push({
                ...item,
                layout: {
                    x: x,
                    y: offsetY,
                    width: Math.max(rowWidth, 0),
                    height: Math.max(itemHeight, 0)
                }
            });
            offsetY += itemHeight;
        }
        return {
            items,
            remainingRect: {
                x: x + rowWidth,
                y,
                width: Math.max(width - rowWidth, 0),
                height
            }
        };
    } else {
        const rowHeight = rowArea / width;
        let offsetX = x;
        for (const item of row) {
            const itemWidth = item.normalizedSize / rowHeight;
            items.push({
                ...item,
                layout: {
                    x: offsetX,
                    y: y,
                    width: Math.max(itemWidth, 0),
                    height: Math.max(rowHeight, 0)
                }
            });
            offsetX += itemWidth;
        }
        return {
            items,
            remainingRect: {
                x,
                y: y + rowHeight,
                width,
                height: Math.max(height - rowHeight, 0)
            }
        };
    }
}

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
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [loadSource, setLoadSource] = useState('');
    const [containerNode, setContainerNode] = useState(null);
    const [containerSize, setContainerSize] = useState({ width: 800, height: 450 });
    const [searchTerm, setSearchTerm] = useState('');
    const [displayCount, setDisplayCount] = useState(30);
    const [timeframe, setTimeframe] = useState(1); // 新增时间维度

    // 视图状态
    const [sizeMetric, setSizeMetric] = useState('market_cap'); // 方块大小: market_cap, turnover, net_inflow
    const [colorMetric, setColorMetric] = useState('change_pct'); // 颜色含义: change_pct, net_inflow_ratio, turnover_rate

    // AbortController refs
    const loadDataAbortRef = useRef(null);

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
            console.error('Failed to load industry heatmap:', err);
            const usedFallback = await loadHistoryFallback(currentAbort, 'error');
            if (usedFallback) {
                return;
            }
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
        loadData();
        
        return () => {
            if (loadDataAbortRef.current) {
                loadDataAbortRef.current.abort();
            }
        };
    }, [loadData, replaySnapshot]);

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
        if (value === 0) return '#555555';
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
    const formatBillion = (value) => {
        if (!value || value === 0) return '-';
        const billion = value / 100000000;
        if (Math.abs(billion) >= 1) return `${billion >= 0 ? '+' : ''}${billion.toFixed(2)} 亿`;
        const wan = value / 10000;
        return `${wan >= 0 ? '+' : ''}${wan.toFixed(0)} 万`;
    };

    // 渲染统计信息
    const renderStats = useMemo(() => {
        if (!data?.industries) return null;

        const industries = data.industries;
        const total = industries.length;
        const upCount = industries.filter(i => i.value > 0).length;
        const downCount = industries.filter(i => i.value < 0).length;
        const flatCount = industries.filter(i => i.value === 0).length;
        const upRatio = total > 0 ? Math.round((upCount / total) * 100) : 0;

        // 市场情绪
        const sentimentRatio = upCount / (total || 1);
        const sentiment = sentimentRatio > 0.6
            ? { label: '偏多', color: HEATMAP_POSITIVE, bg: 'color-mix(in srgb, var(--accent-danger) 12%, var(--bg-secondary) 88%)' }
            : sentimentRatio < 0.4
                ? { label: '偏空', color: HEATMAP_NEGATIVE, bg: 'color-mix(in srgb, var(--accent-success) 12%, var(--bg-secondary) 88%)' }
                : { label: '中性', color: HEATMAP_WARNING, bg: 'color-mix(in srgb, var(--accent-warning) 12%, var(--bg-secondary) 88%)' };

        // 资金 TOP3 流入行业
        const top3Inflow = [...industries]
            .filter(i => (i.moneyFlow || 0) > 0)
            .sort((a, b) => (b.moneyFlow || 0) - (a.moneyFlow || 0))
            .slice(0, 3);

        return (
            <div style={{ marginBottom: 16 }}>
                {/* 第一行：数字统计 */}
                <Row gutter={12} align="middle" style={{ marginBottom: 10 }}>
                    <Col flex="none">
                        <Statistic
                            title="上涨"
                            value={upCount}
                            valueStyle={{ color: HEATMAP_POSITIVE, fontSize: 22 }}
                            prefix={<RiseOutlined style={{ fontSize: 14 }} />}
                        />
                    </Col>
                    <Col flex="none">
                        <Statistic
                            title="下跌"
                            value={downCount}
                            valueStyle={{ color: HEATMAP_NEGATIVE, fontSize: 22 }}
                            prefix={<FallOutlined style={{ fontSize: 14 }} />}
                        />
                    </Col>
                    <Col flex="none">
                        <Statistic
                            title="平盘"
                            value={flatCount}
                            valueStyle={{ color: 'var(--text-muted)', fontSize: 22 }}
                            prefix={<DashboardOutlined style={{ fontSize: 14 }} />}
                        />
                    </Col>

                    {/* 市场广度进度条 */}
                    <Col flex="1" style={{ minWidth: 140 }}>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>市场广度 ({upRatio}%)</div>
                        <Progress
                            percent={upRatio}
                            showInfo={false}
                            strokeColor={HEATMAP_POSITIVE}
                            trailColor={HEATMAP_NEGATIVE}
                            size="small"
                        />
                    </Col>

                    {/* 市场情绪标签 */}
                    <Col flex="none">
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>市场情绪</div>
                        <Tag
                            style={{
                                color: sentiment.color,
                                background: sentiment.bg,
                                border: `1px solid ${sentiment.color}`,
                                fontWeight: 'bold',
                                fontSize: 13,
                                padding: '2px 10px'
                            }}
                        >
                            {sentiment.label}
                        </Tag>
                    </Col>

                    <Col flex="none">
                        <Statistic
                            title="更新时间"
                            value={data.update_time ? new Date(data.update_time).toLocaleTimeString('zh-CN', { hour12: false }) : '-'}
                            valueStyle={{ fontSize: 13 }}
                        />
                    </Col>
                </Row>

                {/* 第二行：资金净流入 TOP3 */}
                {top3Inflow.length > 0 && (
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '6px 10px',
                        background: 'color-mix(in srgb, var(--accent-danger) 10%, var(--bg-secondary) 90%)',
                        borderRadius: 6,
                        border: '1px solid color-mix(in srgb, var(--accent-danger) 22%, var(--border-color) 78%)',
                        flexWrap: 'wrap'
                    }}>
                        <span style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>💰 主力净流入</span>
                        {top3Inflow.map((ind, idx) => (
                            <Tag
                                key={ind.name}
                                color={idx === 0 ? 'red' : idx === 1 ? 'volcano' : 'orange'}
                                style={{ cursor: 'pointer', margin: 0 }}
                                onClick={() => onIndustryClick?.(ind.name)}
                                role="button"
                                tabIndex={0}
                                aria-label={`查看 ${ind.name} 行业详情，主力净流入 ${(ind.moneyFlow / 1e8).toFixed(1)} 亿`}
                                onKeyDown={(event) => activateOnEnterOrSpace(event, () => onIndustryClick?.(ind.name))}
                            >
                                {ind.name} +{(ind.moneyFlow / 1e8).toFixed(1)}亿
                            </Tag>
                        ))}
                    </div>
                )}
            </div>
        );
    }, [data, onIndustryClick]);

    // 使用 Treemap 计算布局和渲染
    const renderTreemap = useMemo(() => {
        if (!data?.industries || data.industries.length === 0) {
            return (
                <Empty description="暂无行业数据">
                    <Button type="primary" onClick={loadData} icon={<ReloadOutlined />}>
                        刷新数据
                    </Button>
                </Empty>
            );
        }

        const industries = data.industries;
        const { width: W, height: H } = containerSize;
        const gap = 2;

        // 准备 Treemap 数据
        // [Fallback] 检测市值数据是否全为 0，自动回退到 moneyFlow 作为大小代理
        const allSizeZero = sizeMetric === 'market_cap' && industries.every(ind => !ind.size || ind.size === 0);

        const sorted = [...industries]
            .map(ind => {
                // 根据 sizeMetric 决定方块大小
                let sizeValue = 1;
                if (sizeMetric === 'market_cap') {
                    if (allSizeZero) {
                        // 市值全为 0 时，使用 |moneyFlow| 或 stockCount 作为代理
                        sizeValue = Math.abs(ind.moneyFlow || 0) || (ind.stockCount || 1);
                    } else {
                        sizeValue = ind.size || 0;
                    }
                }
                else if (sizeMetric === 'turnover') {
                    // 真实成交额优先 (亿元 -> 元)
                    const realVolume = (ind.totalInflow || 0) + (ind.totalOutflow || 0);
                    if (realVolume > 0) {
                        sizeValue = realVolume * 1e8;
                    } else {
                        // 兜底：估算
                        sizeValue = Math.abs(ind.moneyFlow || 0) + (ind.size * (ind.turnoverRate || 0) / 100) || 0;
                    }
                }
                else if (sizeMetric === 'net_inflow') sizeValue = Math.abs(ind.moneyFlow || 0); // 绝对值做大小
                else sizeValue = 1;

                return {
                    ...ind,
                    normalizedSize: Math.max(sizeValue, 1) // 保持最小可见性
                };
            })
            .sort((a, b) => b.normalizedSize - a.normalizedSize);

        // 限制展示数量，让方块足够大以显示文字
        const sourceScoped = marketCapFilter === 'all'
            ? sorted
            : sorted.filter(matchesMarketCapFilter);
        const searchScoped = searchTerm
            ? sourceScoped.filter((item) => matchesIndustrySearch(item.name, searchTerm))
            : sourceScoped;
        const legendScoped = searchTerm
            ? searchScoped
            : searchScoped.filter((item) => {
                let metricValue = 0;
                if (colorMetric === 'change_pct') metricValue = Number(item.value || 0);
                else if (colorMetric === 'net_inflow_ratio') metricValue = Number(item.netInflowRatio || 0);
                else if (colorMetric === 'turnover_rate') metricValue = Number(item.turnoverRate || 0);
                else if (colorMetric === 'pe_ttm') metricValue = Number(item.pe_ttm || 0);
                else if (colorMetric === 'pb') metricValue = Number(item.pb || 0);
                return metricValue >= effectiveLegendRange[0] && metricValue <= effectiveLegendRange[1];
            });
        const displayedBase = legendScoped;
        const displayed = displayCount > 0 ? displayedBase.slice(0, displayCount) : displayedBase;

        if (displayed.length === 0) {
            const emptyDescription = searchTerm
                ? (marketCapFilter !== 'all' ? '当前筛选条件下未找到匹配行业' : '未找到匹配的行业')
                : legendRangeValue
                    ? '当前色阶区间下暂无匹配行业'
                    : '当前市值来源筛选下暂无行业';
            return (
                <div
                    ref={setContainerNode}
                    style={{
                        position: 'relative',
                        width: '100%',
                        height: H,
                        background: HEATMAP_SURFACE,
                        borderRadius: 8,
                        overflow: 'hidden',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                    }}
                >
                    <Empty
                        description={emptyDescription}
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                    >
                        {searchTerm && (
                            <Button
                                size="small"
                                style={{ marginRight: 8 }}
                                onClick={() => {
                                    setSearchTerm('');
                                    onSearchTermChange?.('');
                                }}
                            >
                                清除搜索
                            </Button>
                        )}
                        {legendRangeValue && (
                            <Button
                                size="small"
                                style={{ marginRight: 8 }}
                                onClick={() => onLegendRangeChange?.(null)}
                            >
                                清除色阶筛选
                            </Button>
                        )}
                        {onClearMarketCapFilter && (
                            <Button type="primary" size="small" onClick={onClearMarketCapFilter}>
                                {marketCapFilter !== 'all' ? '查看全部行业' : '刷新视图'}
                            </Button>
                        )}
                    </Empty>
                </div>
            );
        }

        // 执行 Treemap 布局
        const layoutItems = squarify(displayed, { x: 0, y: 0, width: W, height: H });

        // 计算当前数据集中涨跌幅的绝对值最大值，用于动态颜色映射
        const maxAbsChange = data.max_value !== undefined
            ? Math.max(Math.abs(data.max_value), Math.abs(data.min_value))
            : 5;

        return (
            <div
                ref={setContainerNode}
                style={{
                    position: 'relative',
                    width: '100%',
                    height: H,
                    background: HEATMAP_SURFACE,
                    borderRadius: 8,
                    overflow: 'hidden',
                }}
            >
                {layoutItems.map((item) => {
                    const { layout } = item;
                    if (!layout || layout.width < 1 || layout.height < 1) return null;

                    // 决定显示的数值和箭头逻辑
                    let displayValue = 0;
                    if (colorMetric === 'change_pct') displayValue = item.value;
                    else if (colorMetric === 'net_inflow_ratio') displayValue = item.netInflowRatio || 0;
                    else if (colorMetric === 'turnover_rate') displayValue = item.turnoverRate || 0;

                    const bgColor = getColor(displayValue, colorMetric, maxAbsChange);

                    const isLargeBlock = layout.width > 90 && layout.height > 70;
                    const isMediumBlock = layout.width > 55 && layout.height > 40;
                    const isSmallBlock = layout.width > 35 && layout.height > 22;
                    const canShowValue = layout.width > 68 && layout.height > 48;
                    const showMediumMeta = isMediumBlock && !isLargeBlock && layout.width > 82 && layout.height > 60;
                    
                    // 箭头方向逻辑：应与当前显示的数值 displayValue 保持一致
                    // 换手率 (turnover_rate) 始终为正，不显示箭头或显示火号
                    const showArrow = colorMetric !== 'turnover_rate';
                    const arrowIcon = displayValue >= 0 ? '↑' : '↓';
                    const arrowColor = displayValue >= 0 ? '#ff9c9c' : '#b7eb8f';
                    // 超大行业标记
                    const marketCapDisplayKind = getMarketCapDisplayKind(item);
                    const sourceCornerLabel = marketCapDisplayKind === 'snapshot'
                        ? '快照'
                        : marketCapDisplayKind === 'proxy'
                            ? '代理'
                            : marketCapDisplayKind === 'estimated'
                                ? '估'
                                : '实';
                    const sourceCornerStyle = marketCapDisplayKind === 'snapshot'
                        ? { background: 'color-mix(in srgb, var(--bg-primary) 72%, var(--text-primary) 28%)', color: 'var(--text-primary)' }
                        : marketCapDisplayKind === 'proxy'
                            ? { background: 'color-mix(in srgb, var(--accent-primary) 18%, var(--bg-primary) 82%)', color: 'color-mix(in srgb, var(--accent-primary) 78%, #ffffff 22%)' }
                            : marketCapDisplayKind === 'estimated'
                                ? { background: 'color-mix(in srgb, var(--accent-warning) 18%, var(--bg-primary) 82%)', color: 'color-mix(in srgb, var(--accent-warning) 78%, #ffffff 22%)' }
                                : { background: 'color-mix(in srgb, var(--accent-success) 18%, var(--bg-primary) 82%)', color: 'color-mix(in srgb, var(--accent-success) 76%, #ffffff 24%)' };
                    const textColor = TOOLTIP_TEXT;

                    // 市值格式化
                    const marketCapStr = item.size > 0
                        ? `${(item.size / 100000000).toFixed(0)} 亿`
                        : '-';

                    return (
                        <Tooltip
                            key={item.name}
                            autoAdjustOverflow={true}
                            color={TOOLTIP_BG}
                            styles={{
                                body: {
                                    padding: '14px 16px',
                                    borderRadius: '12px',
                                    border: `1px solid ${TOOLTIP_PANEL_BORDER}`,
                                    backdropFilter: 'blur(12px)',
                                    boxShadow: TOOLTIP_SHADOW,
                                    minWidth: 240
                                }
                            }}
                            title={(() => {
                                const hasFlow = (item.moneyFlow != null);
                                const hasLeader = !!item.leadingStock;
                                const hasVolatility = item.industryVolatility != null && item.industryVolatility > 0;
                                const volatilityMeta = getVolatilitySourceMeta(item.industryVolatilitySource);

                                const row = (label, value, color) => (
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                        <span style={{ color: TOOLTIP_MUTED, fontSize: 12 }}>{label}</span>
                                        <span style={{ color: color || TOOLTIP_TEXT, fontWeight: 500, fontSize: 12 }}>{value}</span>
                                    </div>
                                );

                                const metaPill = (label, options = {}) => (
                                    <span style={{
                                        fontSize: 10,
                                        padding: '2px 7px',
                                        borderRadius: 999,
                                        background: options.background || TOOLTIP_PANEL,
                                        color: options.color || TOOLTIP_TEXT,
                                        border: options.border || '1px solid transparent',
                                        whiteSpace: 'nowrap',
                                    }}>
                                        {label}
                                    </span>
                                );

                                return (
                                    <div>
                                        <div style={{
                                            fontWeight: 700,
                                            fontSize: 15,
                                            marginBottom: 8,
                                            paddingBottom: 8,
                                            borderBottom: `1px solid ${TOOLTIP_PANEL_BORDER}`,
                                            color: TOOLTIP_TEXT,
                                            display: 'flex',
                                            justifyContent: 'space-between',
                                            alignItems: 'center'
                                        }}>
                                            <span>{item.name}</span>
                                            <Tag color={item.value >= 0 ? 'error' : 'success'} style={{ margin: 0, border: 'none', fontWeight: 700 }}>
                                                {item.value >= 0 ? '+' : ''}{item.value.toFixed(2)}%
                                            </Tag>
                                        </div>

                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                                            {metaPill(
                                                marketCapDisplayKind === 'snapshot'
                                                    ? '↺ 快照市值'
                                                    : marketCapDisplayKind === 'proxy'
                                                        ? '≈ 行业组代理'
                                                        : marketCapDisplayKind === 'live'
                                                            ? '✓ 实时市值'
                                                            : '≈ 估算市值',
                                                {
                                                    background: marketCapDisplayKind === 'snapshot'
                                                        ? 'color-mix(in srgb, var(--bg-primary) 72%, var(--text-primary) 28%)'
                                                        : marketCapDisplayKind === 'proxy'
                                                            ? 'color-mix(in srgb, var(--accent-primary) 18%, var(--bg-primary) 82%)'
                                                            : marketCapDisplayKind === 'live'
                                                                ? 'color-mix(in srgb, #52c41a 18%, var(--bg-primary) 82%)'
                                                                : 'color-mix(in srgb, #faad14 18%, var(--bg-primary) 82%)',
                                                    color: marketCapDisplayKind === 'snapshot'
                                                        ? 'var(--text-primary)'
                                                        : marketCapDisplayKind === 'proxy'
                                                                ? 'color-mix(in srgb, var(--accent-primary) 78%, #ffffff 22%)'
                                                            : marketCapDisplayKind === 'live'
                                                                ? 'color-mix(in srgb, var(--accent-success) 76%, #ffffff 24%)'
                                                                : 'color-mix(in srgb, var(--accent-warning) 78%, #ffffff 22%)',
                                                }
                                            )}
                                            {marketCapDisplayKind === 'snapshot' && item.marketCapSnapshotAgeHours != null && metaPill(
                                                item.marketCapSnapshotIsStale
                                                    ? `旧快照 ${Math.round(item.marketCapSnapshotAgeHours)}h`
                                                    : `快照 ${Math.round(item.marketCapSnapshotAgeHours)}h`,
                                                {
                                                background: item.marketCapSnapshotIsStale ? 'color-mix(in srgb, var(--accent-warning) 18%, var(--bg-primary) 82%)' : 'color-mix(in srgb, var(--bg-primary) 72%, var(--text-primary) 28%)',
                                                    color: item.marketCapSnapshotIsStale ? 'color-mix(in srgb, var(--accent-warning) 78%, #ffffff 22%)' : 'var(--text-primary)',
                                                }
                                            )}
                                            {(item.valuationSource && item.valuationSource !== 'unavailable') && metaPill(
                                                item.valuationQuality === 'industry_level' ? '行业估值' : '龙头代理估值',
                                                {
                                                    background: item.valuationQuality === 'industry_level' ? 'color-mix(in srgb, var(--accent-primary) 18%, var(--bg-primary) 82%)' : 'color-mix(in srgb, var(--accent-warning) 18%, var(--bg-primary) 82%)',
                                                    color: item.valuationQuality === 'industry_level' ? 'color-mix(in srgb, var(--accent-primary) 78%, #ffffff 22%)' : 'color-mix(in srgb, var(--accent-warning) 78%, #ffffff 22%)',
                                                }
                                            )}
                                            {hasVolatility && metaPill(
                                                `波动率 ${volatilityMeta.label}`,
                                                {
                                                    background: TOOLTIP_PANEL,
                                                    color: volatilityMeta.color || TOOLTIP_TEXT,
                                                }
                                            )}
                                        </div>

                                        <div style={{
                                            display: 'grid',
                                            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                                            gap: 10,
                                            marginBottom: hasLeader ? 10 : 0,
                                        }}>
                                            <div style={{
                                                background: TOOLTIP_PANEL,
                                                border: `1px solid ${TOOLTIP_PANEL_BORDER}`,
                                                borderRadius: 8,
                                                padding: '8px 10px'
                                            }}>
                                                <div style={{ color: TOOLTIP_SUBTLE, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 6 }}>价格与广度</div>
                                                {item.stockCount > 0 && row('成分股', `${item.stockCount} 只`)}
                                                {item.industryIndex > 0 && row('行业指数', `${item.industryIndex.toFixed(2)} 点`)}
                                                {row('换手率', item.turnoverRate ? `${item.turnoverRate.toFixed(2)}%` : '-', item.turnoverRate > 3 ? HEATMAP_WARNING : undefined)}
                                                {hasVolatility && row(
                                                    '区间波动率',
                                                    `${item.industryVolatility.toFixed(2)}%`,
                                                    item.industryVolatility >= 4 ? HEATMAP_POSITIVE : item.industryVolatility >= 2 ? HEATMAP_WARNING : HEATMAP_NEGATIVE
                                                )}
                                            </div>

                                            <div style={{
                                                background: TOOLTIP_PANEL,
                                                border: `1px solid ${TOOLTIP_PANEL_BORDER}`,
                                                borderRadius: 8,
                                                padding: '8px 10px'
                                            }}>
                                                <div style={{ color: TOOLTIP_SUBTLE, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 6 }}>资金与估值</div>
                                                {hasFlow && row('主力净流入', formatBillion(item.moneyFlow), (item.moneyFlow || 0) >= 0 ? HEATMAP_POSITIVE : HEATMAP_NEGATIVE)}
                                                {item.netInflowRatio != null && row('净占比',
                                                    item.netInflowRatio ? `${item.netInflowRatio >= 0 ? '+' : ''}${item.netInflowRatio.toFixed(2)}%` : '-',
                                                    (item.netInflowRatio || 0) >= 0 ? HEATMAP_POSITIVE : HEATMAP_NEGATIVE
                                                )}
                                                {item.size > 0 && row('总市值', marketCapStr)}
                                                {item.pe_ttm != null && row('PE / PB', `${item.pe_ttm.toFixed(1)} / ${item.pb != null ? item.pb.toFixed(2) : '-'}`)}
                                                {item.dividend_yield != null && row('股息率', `${item.dividend_yield.toFixed(2)}%`)}
                                            </div>
                                        </div>

                                        {hasLeader && (
                                            <div style={{
                                                padding: '8px 10px',
                                                background: 'color-mix(in srgb, var(--accent-primary) 14%, var(--bg-primary) 86%)',
                                                border: '1px solid color-mix(in srgb, var(--accent-primary) 26%, var(--border-color) 74%)',
                                                borderRadius: 8,
                                                marginTop: 2
                                            }}>
                                                <div style={{ color: TOOLTIP_SUBTLE, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 6 }}>板块龙头</div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <span
                                                            className="industry-tooltip-link"
                                                            style={{
                                                                color: 'var(--accent-primary)',
                                                            fontWeight: 700,
                                                            fontSize: 13,
                                                            cursor: onLeadingStockClick ? 'pointer' : 'default',
                                                                textDecoration: onLeadingStockClick ? 'underline' : 'none',
                                                                textDecorationStyle: 'dotted',
                                                                textUnderlineOffset: 2,
                                                            }}
                                                            role={onLeadingStockClick ? 'button' : undefined}
                                                            tabIndex={onLeadingStockClick ? 0 : undefined}
                                                            aria-label={onLeadingStockClick ? `查看龙头股 ${item.leadingStock} 详情` : undefined}
                                                            onClick={(e) => {
                                                                if (onLeadingStockClick) {
                                                                    e.stopPropagation();
                                                                    onLeadingStockClick(item.leadingStock);
                                                                }
                                                            }}
                                                            onKeyDown={(event) => {
                                                                if (!onLeadingStockClick) return;
                                                                activateOnEnterOrSpace(event, () => onLeadingStockClick(item.leadingStock));
                                                            }}
                                                        >
                                                            {item.leadingStock}
                                                        </span>
                                                    {item.leadingStockChange !== 0 && (
                                                        <span style={{ color: item.leadingStockChange >= 0 ? HEATMAP_POSITIVE : HEATMAP_NEGATIVE, fontWeight: 700, fontSize: 13 }}>
                                                            {item.leadingStockChange >= 0 ? '+' : ''}{item.leadingStockChange.toFixed(2)}%
                                                        </span>
                                                    )}
                                                </div>
                                                {item.leadingStockPrice > 0 && (
                                                    <div style={{ color: TOOLTIP_SUBTLE, fontSize: 11, marginTop: 2 }}>¥{item.leadingStockPrice.toFixed(2)}</div>
                                                )}
                                            </div>
                                        )}

                                        <div style={{
                                            marginTop: 10,
                                            paddingTop: 6,
                                            borderTop: `1px solid ${TOOLTIP_PANEL_BORDER}`,
                                            display: 'flex',
                                            justifyContent: 'space-between',
                                            alignItems: 'center',
                                            gap: 8,
                                        }}>
                                            <span style={{ fontSize: 10, color: TOOLTIP_SUBTLE }}>
                                                来源: {Array.isArray(item.dataSources) && item.dataSources.length > 0
                                                    ? item.dataSources.join(' + ').toUpperCase()
                                                    : 'UNKNOWN'}
                                            </span>
                                            {(item.totalInflow > 0 || item.totalOutflow > 0) && (
                                                <span style={{ fontSize: 10, color: TOOLTIP_MUTED }}>
                                                    ↑{item.totalInflow.toFixed(1)} / ↓{item.totalOutflow.toFixed(1)} 亿
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                );
                            })()}
                            placement="top"
                            mouseEnterDelay={0.15}
                        >
                            <div
                                className="heatmap-tile"
                                data-testid="heatmap-tile"
                                data-industry-name={item.name}
                                onClick={() => onIndustryClick?.(item.name)}
                                role="button"
                                tabIndex={0}
                                aria-label={`查看 ${item.name} 行业详情`}
                                style={{
                                    position: 'absolute',
                                    left: layout.x + gap / 2,
                                    top: layout.y + gap / 2,
                                    width: layout.width - gap,
                                    height: layout.height - gap,
                                    backgroundColor: bgColor,
                                    borderRadius: 3,
                                    display: 'flex',
                                    flexDirection: 'column',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    cursor: 'pointer',
                                    transition: 'filter 0.15s, transform 0.15s, opacity 0.2s',
                                    overflow: 'hidden',
                                    boxSizing: 'border-box',
                                    padding: '2px 4px',
                                    opacity: 1,
                                    border: 'none',
                                    zIndex: 1,
                                }}
                                onKeyDown={(event) => activateOnEnterOrSpace(event, () => onIndustryClick?.(item.name))}
                                onMouseEnter={(e) => {
                                    syncHeatmapTileFocusState(e.currentTarget, true);
                                }}
                                onMouseLeave={(e) => {
                                    syncHeatmapTileFocusState(e.currentTarget, false);
                                }}
                                onFocus={(e) => syncHeatmapTileFocusState(e.currentTarget, true)}
                                onBlur={(e) => syncHeatmapTileFocusState(e.currentTarget, false)}
                            >
                                {(layout.width > 70 && layout.height > 40) && (
                                    <div
                                        className="heatmap-source-corner"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            onSelectMarketCapFilter?.(
                                                marketCapDisplayKind === 'live'
                                                    ? 'live'
                                                    : marketCapDisplayKind === 'snapshot'
                                                        ? 'snapshot'
                                                        : marketCapDisplayKind === 'proxy'
                                                            ? 'proxy'
                                                            : 'estimated'
                                                    );
                                        }}
                                        role="button"
                                        tabIndex={0}
                                        aria-label={`按 ${sourceCornerLabel} 来源筛选 ${item.name}`}
                                        onKeyDown={(event) => activateOnEnterOrSpace(event, () => (
                                            onSelectMarketCapFilter?.(
                                                marketCapDisplayKind === 'live'
                                                    ? 'live'
                                                    : marketCapDisplayKind === 'snapshot'
                                                        ? 'snapshot'
                                                        : marketCapDisplayKind === 'proxy'
                                                            ? 'proxy'
                                                            : 'estimated'
                                            )
                                        ))}
                                        style={{
                                            position: 'absolute',
                                            top: 4,
                                            right: 4,
                                            fontSize: layout.width > 110 ? 10 : 9,
                                            lineHeight: 1,
                                            padding: '3px 5px',
                                            borderRadius: 999,
                                            backdropFilter: 'blur(8px)',
                                            letterSpacing: '0.02em',
                                            fontWeight: 700,
                                            textShadow: 'none',
                                                cursor: 'pointer',
                                            border: marketCapFilter !== 'all'
                                                && ((marketCapDisplayKind === 'live' && marketCapFilter === 'live')
                                                    || (marketCapDisplayKind === 'snapshot' && marketCapFilter === 'snapshot')
                                                    || (marketCapDisplayKind === 'proxy' && marketCapFilter === 'proxy')
                                                    || (marketCapDisplayKind === 'estimated' && marketCapFilter === 'estimated'))
                                                ? `1px solid ${TOOLTIP_TEXT}`
                                                : '1px solid transparent',
                                            ...sourceCornerStyle,
                                        }}
                                    >
                                        {sourceCornerLabel}
                                    </div>
                                )}
                                {/* Hide text if block is too narrow or too short */}
                                {(layout.width > 24 && layout.height > 20) && (
                                    <>
                                        <Text
                                            strong
                                            style={{
                                                color: textColor,
                                                fontSize: isLargeBlock ? 14 : isMediumBlock ? 11 : isSmallBlock ? 10 : 9,
                                                textAlign: 'center',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'nowrap',
                                                maxWidth: '98%',
                                                lineHeight: isMediumBlock && !isLargeBlock ? 1.12 : 1.2,
                                                textShadow: TILE_TEXT_SHADOW,
                                                opacity: layout.width < 40 ? 0.8 : 1
                                            }}
                                        >
                                            {item.name}
                                        </Text>

                                        {canShowValue && (
                                            <Text
                                                style={{
                                                    color: textColor,
                                                    fontSize: isLargeBlock ? 15 : isMediumBlock ? 11 : 9,
                                                    fontWeight: 'bold',
                                                    lineHeight: isMediumBlock && !isLargeBlock ? 1.16 : 1.3,
                                                    textShadow: TILE_TEXT_SHADOW,
                                                    marginTop: isMediumBlock && !isLargeBlock ? 0 : 1,
                                                    maxWidth: '98%',
                                                    whiteSpace: 'nowrap',
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis'
                                                }}
                                            >
                                                {/* 显示当前指标对应的方向箭头 */}
                                                {showArrow && (
                                                    <span style={{ color: arrowColor, fontSize: isLargeBlock ? 13 : 10, marginRight: 2 }}>{arrowIcon}</span>
                                                )}
                                                {colorMetric === 'turnover_rate' || colorMetric === 'net_inflow_ratio'
                                                    ? `${displayValue.toFixed(1)}%`
                                                    : colorMetric === 'pe_ttm' || colorMetric === 'pb'
                                                        ? `${displayValue.toFixed(1)}${colorMetric === 'pe_ttm' ? 'x' : ''}`
                                                        : `${displayValue >= 0 ? '+' : ''}${displayValue.toFixed(2)}%`}
                                            </Text>
                                        )}

                                        {showMediumMeta && item.stockCount > 0 && (
                                            <Text
                                                style={{
                                                    color: 'color-mix(in srgb, var(--text-primary) 76%, transparent)',
                                                    fontSize: 9,
                                                    lineHeight: 1.2,
                                                    marginTop: 1,
                                                    maxWidth: '95%',
                                                    whiteSpace: 'nowrap',
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis',
                                                    textShadow: TILE_TEXT_SHADOW,
                                                }}
                                            >
                                                {item.stockCount}只
                                            </Text>
                                        )}

                                        {isLargeBlock && item.leadingStock && (
                                            <div
                                                onClick={(event) => {
                                                    if (onLeadingStockClick) {
                                                        event.stopPropagation();
                                                        onLeadingStockClick(item.leadingStock);
                                                    }
                                                }}
                                                role={onLeadingStockClick ? 'button' : undefined}
                                                tabIndex={onLeadingStockClick ? 0 : undefined}
                                                aria-label={onLeadingStockClick ? `查看 ${item.name} 龙头股 ${item.leadingStock}` : undefined}
                                                onKeyDown={(event) => {
                                                    if (!onLeadingStockClick) return;
                                                    activateOnEnterOrSpace(event, () => onLeadingStockClick(item.leadingStock));
                                                }}
                                                style={{
                                                    marginTop: 4,
                                                    padding: '2px 6px',
                                                    borderRadius: 999,
                                                    background: 'rgba(255,255,255,0.18)',
                                                    maxWidth: '95%',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: 4,
                                                    cursor: onLeadingStockClick ? 'pointer' : 'default',
                                                }}
                                            >
                                                <span style={{
                                                    color: textColor,
                                                    fontSize: 10,
                                                    opacity: 0.86,
                                                    whiteSpace: 'nowrap',
                                                }}>
                                                    龙头
                                                </span>
                                                <span style={{
                                                    color: textColor,
                                                    fontSize: 11,
                                                    fontWeight: 700,
                                                    whiteSpace: 'nowrap',
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis',
                                                    textShadow: TILE_TEXT_SHADOW,
                                                }}>
                                                    {item.leadingStock}
                                                </span>
                                                {Number.isFinite(Number(item.leadingStockChange)) && item.leadingStockChange !== 0 && (
                                                    <span style={{
                                                        color: item.leadingStockChange >= 0 ? HEATMAP_POSITIVE : HEATMAP_NEGATIVE,
                                                        fontSize: 10,
                                                        fontWeight: 700,
                                                        whiteSpace: 'nowrap',
                                                    }}>
                                                        {item.leadingStockChange >= 0 ? '+' : ''}{Number(item.leadingStockChange).toFixed(1)}%
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                    </>
                                )}

                                {/* 大块：市值 */}
                                {isLargeBlock && (
                                    <div style={{
                                        marginTop: 4,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        gap: 8,
                                        flexWrap: 'wrap',
                                        maxWidth: '96%',
                                    }}>
                                        <Text
                                            style={{
                                                color: 'color-mix(in srgb, var(--text-primary) 68%, transparent)',
                                                fontSize: 11,
                                                lineHeight: 1.2,
                                                textShadow: '0 1px 2px rgba(15, 23, 42, 0.24)',
                                            }}
                                        >
                                            {sizeMetric === 'market_cap' && (item.size > 0 ? `${(item.size / 100000000).toFixed(0)} 亿` : '')}
                                            {sizeMetric === 'net_inflow' && formatBillion(Math.abs(item.moneyFlow))}
                                        </Text>
                                        {item.stockCount > 0 && (
                                            <Text
                                                style={{
                                                    color: 'color-mix(in srgb, var(--text-primary) 62%, transparent)',
                                                    fontSize: 10,
                                                    lineHeight: 1.2,
                                                    textShadow: '0 1px 2px rgba(15, 23, 42, 0.24)',
                                                }}
                                            >
                                                {item.stockCount} 只
                                            </Text>
                                        )}
                                    </div>
                                )}
                            </div>
                        </Tooltip >
                    );
                })
                }
            </div >
        );
    }, [
        data,
        containerSize,
        getColor,
        getMarketCapDisplayKind,
        getVolatilitySourceMeta,
        onIndustryClick,
        onLeadingStockClick,
        onClearMarketCapFilter,
        onSelectMarketCapFilter,
        onSearchTermChange,
        searchTerm,
        displayCount,
        sizeMetric,
        colorMetric,
        marketCapFilter,
        matchesMarketCapFilter,
        effectiveLegendRange,
        legendRangeValue,
        loadData,
        onLegendRangeChange,
    ]);

    // 计算资金流入 TOP3（用于图例横幅，来自内存数据无需新 API）
    const top3InflowBanner = useMemo(() => {
        if (!data?.industries) return [];
        return [...data.industries]
            .filter(i => (i.moneyFlow || 0) > 0)
            .sort((a, b) => (b.moneyFlow || 0) - (a.moneyFlow || 0))
            .slice(0, 3);
    }, [data]);

    // 渲染图例
    const renderLegend = (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: 12,
            gap: 12,
            flexWrap: 'wrap'
        }}>
            {/* 颜色图例 + 大小图例 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <BgColorsOutlined />
                    <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {legendMeta.leftLabel}
                    </Text>
                    <div style={{
                        width: 120,
                        height: 8,
                        background: colorMetric === 'turnover_rate'
                            ? 'linear-gradient(to right, blue, yellow, red)'
                            : 'linear-gradient(to right, rgb(20, 180, 40), #6B6B6B, rgb(235, 20, 20))',
                        borderRadius: 4
                    }} />
                    <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {legendMeta.rightLabel}
                    </Text>
                </div>
                <div style={{ minWidth: 280, maxWidth: 380, flex: '1 1 280px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
                        <Text style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                            色阶区间刷选
                        </Text>
                        <Text style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                            {effectiveLegendRange[0].toFixed(colorMetric === 'pe_ttm' ? 0 : 1)}
                            {legendMeta.suffix}
                            {' '}~{' '}
                            {effectiveLegendRange[1].toFixed(colorMetric === 'pe_ttm' ? 0 : 1)}
                            {legendMeta.suffix}
                        </Text>
                    </div>
                    <div data-testid="heatmap-legend-slider">
                        <Slider
                            range
                            min={legendMeta.min}
                            max={legendMeta.max}
                            step={legendMeta.step}
                            value={effectiveLegendRange}
                            onChange={(value) => onLegendRangeChange?.(value)}
                            onChangeComplete={(value) => onLegendRangeChange?.(value)}
                            tooltip={{ open: false }}
                        />
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <BarChartOutlined />
                    <Text style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        方块大小 = {
                            sizeMetric === 'market_cap' ? '总市值' :
                                sizeMetric === 'turnover' ? '当日总成交额' :
                                    sizeMetric === 'net_inflow' ? '净流入绝对值' : '未知'
                        }
                    </Text>
                </div>
            </div>

            {/* 资金流入 TOP3 横幅 */}
            {top3InflowBanner.length > 0 && (
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '4px 10px',
                    background: 'color-mix(in srgb, var(--accent-danger) 10%, var(--bg-secondary) 90%)',
                    borderRadius: 6,
                    border: '1px solid color-mix(in srgb, var(--accent-danger) 24%, var(--border-color) 76%)',
                    flexWrap: 'wrap'
                }}>
                    <span style={{ fontSize: 11, color: 'var(--accent-danger)', whiteSpace: 'nowrap' }}>💰 净流入 TOP</span>
                    {top3InflowBanner.map((ind, idx) => (
                        <Tag
                            key={ind.name}
                            color={idx === 0 ? 'red' : idx === 1 ? 'volcano' : 'orange'}
                            style={{ margin: 0, cursor: 'pointer', fontSize: 11 }}
                            onClick={() => onIndustryClick?.(ind.name)}
                            role="button"
                            tabIndex={0}
                            aria-label={`查看 ${ind.name} 行业详情`}
                            onKeyDown={(event) => activateOnEnterOrSpace(event, () => onIndustryClick?.(ind.name))}
                        >
                            {ind.name}
                        </Tag>
                    ))}
                </div>
            )}
        </div>
    );

    const timeframeOptions = [
        { value: 1, label: '1日' },
        { value: 5, label: '5日' },
        { value: 10, label: '10日' },
        { value: 20, label: '20日' },
        { value: 60, label: '60日' },
    ];
    const sizeMetricOptions = [
        { value: 'market_cap', label: '按市值' },
        { value: 'net_inflow', label: '按净流入' },
        { value: 'turnover', label: '按成交额(估)' },
    ];
    const colorMetricOptions = [
        { value: 'change_pct', label: '看涨跌' },
        { value: 'net_inflow_ratio', label: '看净流入%' },
        { value: 'turnover_rate', label: '看换手率' },
        { value: 'pe_ttm', label: '看市盈率' },
        { value: 'pb', label: '看市净率' },
    ];
    const displayCountOptions = [
        { value: 30, label: 'Top 30' },
        { value: 50, label: 'Top 50' },
        { value: 0, label: '全部' },
    ];
    const refreshOptions = [
        { value: 0, label: isCompactMobile ? '关闭' : '不自动刷新' },
        { value: 60, label: isCompactMobile ? '60秒' : '⏱ 60秒' },
        { value: 120, label: isCompactMobile ? '2分钟' : '⏱ 2分钟' },
        { value: 300, label: isCompactMobile ? '5分钟' : '⏱ 5分钟' },
    ];

    const renderDesktopControls = (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            alignItems: 'flex-end'
        }}>
            <Space size={8} wrap>
                <Radio.Group
                    className="heatmap-control-timeframe"
                    value={timeframe}
                    onChange={e => {
                        setTimeframe(e.target.value);
                        onTimeframeChange?.(e.target.value);
                    }}
                    size="small"
                    optionType="button"
                    buttonStyle="solid"
                    style={{
                        boxShadow: focusControlKey === 'timeframe' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    aria-label="选择行业热力图统计时间范围"
                >
                    <Radio value={1}>1日</Radio>
                    <Radio value={5}>5日</Radio>
                    <Radio value={10}>10日</Radio>
                    <Radio value={20}>20日</Radio>
                    <Radio value={60}>60日</Radio>
                </Radio.Group>
                <Select
                    className="heatmap-control-size-metric"
                    value={sizeMetric}
                    onChange={(value) => {
                        setSizeMetric(value);
                        onSizeMetricChange?.(value);
                    }}
                    size="small"
                    style={{
                        width: 100,
                        boxShadow: focusControlKey === 'size_metric' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    options={sizeMetricOptions}
                    aria-label="选择行业热力图方块大小指标"
                />
                <Select
                    className="heatmap-control-color-metric"
                    value={colorMetric}
                    onChange={(value) => {
                        setColorMetric(value);
                        onColorMetricChange?.(value);
                    }}
                    size="small"
                    style={{
                        width: 110,
                        boxShadow: focusControlKey === 'color_metric' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    options={colorMetricOptions}
                    aria-label="选择行业热力图颜色指标"
                />
            </Space>
            <Space size={8} wrap>
                {replaySnapshot?.data && (
                    <Tag color="processing" style={{ margin: 0, borderRadius: 999 }}>
                        回放中 {replaySnapshot?.timeframe ? `${replaySnapshot.timeframe}日` : ''}
                    </Tag>
                )}
                {loadSource === 'history' && !replaySnapshot?.data && (
                    <Tag color="gold" style={{ margin: 0, borderRadius: 999 }}>
                        已切换到最近快照
                    </Tag>
                )}
                <Radio.Group
                    className="heatmap-control-display-count"
                    value={displayCount}
                    onChange={e => {
                        setDisplayCount(e.target.value);
                        onDisplayCountChange?.(e.target.value);
                    }}
                    size="small"
                    buttonStyle="solid"
                    style={{
                        boxShadow: focusControlKey === 'display_count' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    aria-label="选择行业热力图显示范围"
                >
                    <Radio.Button value={30}>Top 30</Radio.Button>
                    <Radio.Button value={50}>Top 50</Radio.Button>
                    <Radio.Button value={0}>全部</Radio.Button>
                </Radio.Group>
                <Input
                    className="heatmap-control-search"
                    placeholder="行业筛选…"
                    value={searchTerm}
                    prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
                    onChange={e => {
                        setSearchTerm(e.target.value);
                        onSearchTermChange?.(e.target.value);
                    }}
                    style={{
                        width: 150,
                        borderRadius: 4,
                        backgroundColor: 'var(--bg-secondary)',
                        border: '1px solid var(--border-color)',
                        color: 'var(--text-primary)',
                        boxShadow: focusControlKey === 'search' ? 'var(--industry-focus-ring)' : 'none',
                    }}
                    allowClear
                    size="small"
                    aria-label="按行业名称筛选热力图"
                    name="industry-heatmap-search"
                />
                <Select
                    value={refreshSec}
                    onChange={setRefreshSec}
                    size="small"
                    style={{ width: 100 }}
                    options={refreshOptions}
                    aria-label="选择行业热力图自动刷新频率"
                />
                <Button
                    type="text"
                    data-testid="heatmap-fullscreen-toggle"
                    icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                    onClick={onToggleFullscreen}
                    style={{ color: 'var(--text-secondary)' }}
                    aria-label={isFullscreen ? '退出行业热力图全屏' : '进入行业热力图全屏'}
                />
                <Button
                    type="text"
                    icon={<ReloadOutlined />}
                    onClick={loadData}
                    loading={loading}
                    disabled={Boolean(replaySnapshot?.data)}
                    style={{ color: 'var(--text-secondary)' }}
                    aria-label="刷新行业热力图数据"
                />
            </Space>
        </div>
    );

    const renderMobileControls = (
        <div className="industry-heatmap-controls industry-heatmap-controls--compact">
            {(replaySnapshot?.data || (loadSource === 'history' && !replaySnapshot?.data)) && (
                <div className="industry-heatmap-controls__badges">
                    {replaySnapshot?.data && (
                        <Tag color="processing" style={{ margin: 0, borderRadius: 999 }}>
                            回放中 {replaySnapshot?.timeframe ? `${replaySnapshot.timeframe}日` : ''}
                        </Tag>
                    )}
                    {loadSource === 'history' && !replaySnapshot?.data && (
                        <Tag color="gold" style={{ margin: 0, borderRadius: 999 }}>
                            最近快照
                        </Tag>
                    )}
                </div>
            )}
            <div className="industry-heatmap-controls__row">
                <Select
                    className="heatmap-control-timeframe"
                    value={timeframe}
                    onChange={(value) => {
                        setTimeframe(value);
                        onTimeframeChange?.(value);
                    }}
                    size="small"
                    style={{
                        width: 88,
                        boxShadow: focusControlKey === 'timeframe' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    options={timeframeOptions}
                    aria-label="选择行业热力图统计时间范围"
                />
                <Select
                    className="heatmap-control-display-count"
                    value={displayCount}
                    onChange={(value) => {
                        setDisplayCount(value);
                        onDisplayCountChange?.(value);
                    }}
                    size="small"
                    style={{
                        width: 92,
                        boxShadow: focusControlKey === 'display_count' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    options={displayCountOptions}
                    aria-label="选择行业热力图显示范围"
                />
                <Input
                    className="heatmap-control-search"
                    placeholder="行业筛选…"
                    value={searchTerm}
                    prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
                    onChange={e => {
                        setSearchTerm(e.target.value);
                        onSearchTermChange?.(e.target.value);
                    }}
                    style={{
                        flex: '1 1 0',
                        minWidth: 0,
                        borderRadius: 4,
                        backgroundColor: 'var(--bg-secondary)',
                        border: '1px solid var(--border-color)',
                        color: 'var(--text-primary)',
                        boxShadow: focusControlKey === 'search' ? 'var(--industry-focus-ring)' : 'none',
                    }}
                    allowClear
                    size="small"
                    aria-label="按行业名称筛选热力图"
                    name="industry-heatmap-search"
                />
            </div>
            <div className="industry-heatmap-controls__row">
                <Select
                    className="heatmap-control-size-metric"
                    value={sizeMetric}
                    onChange={(value) => {
                        setSizeMetric(value);
                        onSizeMetricChange?.(value);
                    }}
                    size="small"
                    style={{
                        width: 96,
                        boxShadow: focusControlKey === 'size_metric' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    options={sizeMetricOptions}
                    aria-label="选择行业热力图方块大小指标"
                />
                <Select
                    className="heatmap-control-color-metric"
                    value={colorMetric}
                    onChange={(value) => {
                        setColorMetric(value);
                        onColorMetricChange?.(value);
                    }}
                    size="small"
                    style={{
                        width: 108,
                        boxShadow: focusControlKey === 'color_metric' ? 'var(--industry-focus-ring)' : 'none',
                        borderRadius: 8,
                    }}
                    options={colorMetricOptions}
                    aria-label="选择行业热力图颜色指标"
                />
                <Select
                    value={refreshSec}
                    onChange={setRefreshSec}
                    size="small"
                    style={{ width: 82 }}
                    options={refreshOptions}
                    aria-label="选择行业热力图自动刷新频率"
                />
                <div className="industry-heatmap-controls__actions">
                    <Button
                        type="text"
                        data-testid="heatmap-fullscreen-toggle"
                        icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                        onClick={onToggleFullscreen}
                        style={{ color: 'var(--text-secondary)' }}
                        aria-label={isFullscreen ? '退出行业热力图全屏' : '进入行业热力图全屏'}
                    />
                    <Button
                        type="text"
                        icon={<ReloadOutlined />}
                        onClick={loadData}
                        loading={loading}
                        disabled={Boolean(replaySnapshot?.data)}
                        style={{ color: 'var(--text-secondary)' }}
                        aria-label="刷新行业热力图数据"
                    />
                </div>
            </div>
        </div>
    );

    const renderControls = isCompactMobile ? renderMobileControls : renderDesktopControls;

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
