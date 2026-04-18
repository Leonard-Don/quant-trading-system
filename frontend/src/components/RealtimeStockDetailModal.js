import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Row, Col, Tag, Empty, Typography, Button } from 'antd';
import {
    ClockCircleOutlined,
    DotChartOutlined,
    FundOutlined,
    RiseOutlined,
} from '@ant-design/icons';
import MarketAnalysis from './MarketAnalysis';
import { STOCK_DATABASE } from '../constants/stocks';
import { getKlines } from '../services/api';
import { evaluateAlertHitFollowThrough } from '../utils/realtimeSignals';
import { getCategoryLabel as getCategoryLabelForType, inferSymbolCategory } from '../utils/realtimeFormatters';

const { Text } = Typography;

const SNAPSHOT_PANEL_BG = 'linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 14%, var(--bg-secondary) 86%) 0%, color-mix(in srgb, var(--accent-secondary) 14%, var(--bg-secondary) 86%) 100%)';
const SNAPSHOT_CARD_BG = 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)';
const EMPTY_LIST = [];

const getDisplayName = (symbol) => {
    const info = STOCK_DATABASE[symbol];
    return info?.cn || info?.en || symbol || '未知标的';
};

const getCategoryLabel = (symbol) => getCategoryLabelForType(inferSymbolCategory(symbol));

const formatNumber = (value, digits = 2, fallback = '--') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return fallback;
    }
    return Number(value).toFixed(digits);
};

const formatSignedNumber = (value, digits = 2, suffix = '', fallback = '--') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return fallback;
    }

    const numericValue = Number(value);
    return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(digits)}${suffix}`;
};

const formatVolume = (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '--';
    }

    const volume = Number(value);
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(2)}K`;
    return `${volume}`;
};

const formatTimestamp = (value) => {
    if (!value) return '--';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString();
};

const hasTradableOrderBookValue = (value) => (
    value !== null
    && value !== undefined
    && !Number.isNaN(Number(value))
    && Number(value) > 0
);

const formatOrderBookValue = (value) => {
    if (!hasTradableOrderBookValue(value)) {
        return '--';
    }
    return Number(value).toFixed(2);
};

const formatSpread = (bid, ask) => {
    if (!hasTradableOrderBookValue(bid) || !hasTradableOrderBookValue(ask)) {
        return '--';
    }

    return Number(Number(ask) - Number(bid)).toFixed(2);
};

const formatTimelineTime = (value) => {
    if (!value) return '--';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString([], {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
};

const getTimelineToneStyle = (tone = 'neutral') => {
    if (tone === 'positive') {
        return {
            borderColor: 'rgba(34, 197, 94, 0.24)',
            background: 'rgba(34, 197, 94, 0.08)',
            color: '#15803d',
        };
    }

    if (tone === 'negative') {
        return {
            borderColor: 'rgba(239, 68, 68, 0.24)',
            background: 'rgba(239, 68, 68, 0.08)',
            color: '#b91c1c',
        };
    }

    if (tone === 'warning') {
        return {
            borderColor: 'rgba(245, 158, 11, 0.24)',
            background: 'rgba(245, 158, 11, 0.08)',
            color: '#b45309',
        };
    }

    return {
        borderColor: 'rgba(148, 163, 184, 0.24)',
        background: 'rgba(148, 163, 184, 0.08)',
        color: 'var(--text-secondary)',
    };
};

const formatRangePercent = (low, high, previousClose) => {
    if ([low, high, previousClose].some(value => value === null || value === undefined || Number.isNaN(Number(value))) || Number(previousClose) === 0) {
        return '--';
    }

    return `${(((Number(high) - Number(low)) / Number(previousClose)) * 100).toFixed(2)}%`;
};

const getNumericRangePercent = (quote) => {
    const low = Number(quote?.low);
    const high = Number(quote?.high);
    const previousClose = Number(quote?.previous_close);

    if ([low, high, previousClose].some((value) => Number.isNaN(value)) || previousClose === 0) {
        return null;
    }

    return ((high - low) / previousClose) * 100;
};

const buildSnapshotTrendSeries = (quote = null) => {
    const points = [
        { label: '昨收', value: Number(quote?.previous_close) },
        { label: '开盘', value: Number(quote?.open) },
        { label: '低点', value: Number(quote?.low) },
        { label: '现价', value: Number(quote?.price) },
        { label: '高点', value: Number(quote?.high) },
    ].filter((item) => Number.isFinite(item.value) && item.value > 0);

    return points.length >= 2 ? points : EMPTY_LIST;
};

const buildTrendPolyline = (series = [], width = 320, height = 92, padding = 8) => {
    if (!Array.isArray(series) || series.length < 2) {
        return null;
    }

    const values = series.map((item) => item.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;

    return series.map((item, index) => {
        const x = padding + (index * (width - padding * 2)) / (series.length - 1);
        const y = height - padding - (((item.value - min) / span) * (height - padding * 2));
        return `${x},${y}`;
    }).join(' ');
};

const buildIntradayTrendSeries = (klines = []) => (
    Array.isArray(klines)
        ? klines
            .map((item) => {
                const value = Number(item?.close);
                const label = item?.date || item?.datetime || '';
                return Number.isFinite(value) && value > 0 ? { label, value } : null;
            })
            .filter(Boolean)
            .slice(-32)
        : EMPTY_LIST
);

const buildSignalSummary = (quote = null, eventTimeline = []) => {
    const changePercent = Number(quote?.change_percent);
    const rangePercent = getNumericRangePercent(quote);
    const spread = Number(formatSpread(quote?.bid, quote?.ask));
    const hasSpread = !Number.isNaN(spread);
    const positiveEvents = eventTimeline.filter((item) => item?.tone === 'positive').length;
    const negativeEvents = eventTimeline.filter((item) => item?.tone === 'negative').length;
    const warningEvents = eventTimeline.filter((item) => item?.tone === 'warning').length;

    const momentumScore = Number.isNaN(changePercent)
        ? 50
        : Math.max(0, Math.min(100, 50 + changePercent * 10));
    const volatilityScore = rangePercent === null
        ? 45
        : Math.max(0, Math.min(100, 35 + rangePercent * 12));
    const liquidityScore = hasSpread
        ? Math.max(0, Math.min(100, 85 - spread * 20))
        : 52;
    const eventScore = Math.max(0, Math.min(100, 50 + positiveEvents * 12 - negativeEvents * 12 + warningEvents * 4));
    const totalScore = Math.round((momentumScore + volatilityScore + liquidityScore + eventScore) / 4);

    const conviction = totalScore >= 70
        ? '偏强跟踪'
        : totalScore <= 40
            ? '谨慎观察'
            : '中性观察';

    return {
        totalScore,
        conviction,
        momentumLabel: Number.isNaN(changePercent)
            ? '动能待确认'
            : changePercent >= 2
                ? '动能强'
                : changePercent <= -2
                    ? '动能弱'
                    : '动能中性',
        volatilityLabel: rangePercent === null
            ? '波动待确认'
            : rangePercent >= 3
                ? '波动放大'
                : '波动可控',
        liquidityLabel: hasSpread
            ? spread <= 0.2
                ? '流动性顺滑'
                : '点差偏宽'
            : '流动性待确认',
        eventLabel: positiveEvents === negativeEvents
            ? '事件分歧'
            : positiveEvents > negativeEvents
                ? '事件偏多'
                : '事件偏空',
        eventBreakdown: `${positiveEvents} 多 / ${negativeEvents} 空 / ${warningEvents} 提醒`,
    };
};

const getSuggestedTradeQuantity = (symbol, price) => {
    if (!symbol) {
        return 100;
    }

    if (/-USD$/i.test(symbol)) {
        return 1;
    }

    if (price !== null && price >= 1000) {
        return 10;
    }

    if (price !== null && price >= 200) {
        return 25;
    }

    if (price !== null && price >= 50) {
        return 50;
    }

    return 100;
};

const buildQuickTradeDraft = (symbol, quote, signalSummary) => {
    const price = Number(quote?.price);
    if (!symbol || Number.isNaN(price) || price <= 0) {
        return null;
    }

    const low = Number(quote?.low);
    const high = Number(quote?.high);
    const changePercent = Number(quote?.change_percent);
    const isWeakSignal = (!Number.isNaN(changePercent) && changePercent < 0) || (signalSummary?.totalScore ?? 50) < 50;
    const action = isWeakSignal ? 'SELL' : 'BUY';
    const fallbackRisk = price * 0.018;
    const fallbackReward = price * 0.028;

    const stopLoss = action === 'BUY'
        ? (Number.isFinite(low) && low > 0 ? Math.min(price - 0.01, low) : Math.max(0.01, price - fallbackRisk))
        : (Number.isFinite(high) && high > 0 ? Math.max(price + 0.01, high) : price + fallbackRisk);
    const takeProfit = action === 'BUY'
        ? (Number.isFinite(high) && high > 0 ? Math.max(price + 0.01, high) : price + fallbackReward)
        : (Number.isFinite(low) && low > 0 ? Math.max(0.01, Math.min(price - 0.01, low)) : Math.max(0.01, price - fallbackReward));

    return {
        symbol,
        action,
        quantity: getSuggestedTradeQuantity(symbol, price),
        limitPrice: price,
        suggestedEntry: price,
        stopLoss: Number(stopLoss.toFixed(2)),
        takeProfit: Number(takeProfit.toFixed(2)),
        sourceTitle: '详情页快速交易',
        sourceDescription: `${signalSummary?.conviction || '盘中判断'} · 综合分 ${signalSummary?.totalScore ?? '--'} · 已按当前快照生成可编辑交易草稿。`,
        note: `${getDisplayName(symbol)} 当前参考价 ${formatNumber(price)}，可直接带入纸面交易终端继续调整。`,
    };
};

const buildCompareCards = (displaySymbol, quote, compareCandidates = [], selectedCompareSymbols = [], timelineBySymbol = {}) => {
    const compareCandidateMap = new Map(
        compareCandidates
            .filter((item) => item?.symbol)
            .map((item) => [item.symbol, item])
    );
    const currentCard = {
        symbol: displaySymbol,
        name: getDisplayName(displaySymbol),
        quote,
        signalSummary: buildSignalSummary(quote, timelineBySymbol[displaySymbol] || []),
    };

    const selectedCards = selectedCompareSymbols
        .map((targetSymbol) => compareCandidateMap.get(targetSymbol))
        .filter(Boolean)
        .map((item) => ({
            symbol: item.symbol,
            name: item.name || getDisplayName(item.symbol),
            quote: item.quote || null,
            signalSummary: buildSignalSummary(item.quote || null, timelineBySymbol[item.symbol] || []),
        }));

    return [currentCard, ...selectedCards];
};

const isSameSymbolList = (left = [], right = []) => (
    left.length === right.length && left.every((item, index) => item === right[index])
);

const dedupeCompareCandidates = (items = []) => {
    const seenSymbols = new Set();
    return items.filter((item) => {
        const symbol = item?.symbol;
        if (!symbol || seenSymbols.has(symbol)) {
            return false;
        }
        seenSymbols.add(symbol);
        return true;
    });
};

const sanitizeCompareSymbols = (symbols = [], availableTargets = [], displaySymbol) => {
    const availableSet = new Set(availableTargets);
    const seenSymbols = new Set();

    return symbols.filter((symbol) => {
        if (!symbol || symbol === displaySymbol || !availableSet.has(symbol) || seenSymbols.has(symbol)) {
            return false;
        }
        seenSymbols.add(symbol);
        return true;
    }).slice(0, 3);
};

// eslint-disable-next-line no-unused-vars
const getFollowThroughSummary = (event = {}, quote = null) => {
    const currentPrice = quote?.price === null || quote?.price === undefined || Number.isNaN(Number(quote?.price))
        ? null
        : Number(quote.price);

    if (currentPrice === null) {
        return {
            label: '等待最新行情',
            description: '当前还没有可用于评估后效的最新价格。',
            tone: 'neutral',
        };
    }

    const entryPrice = event?.entryPrice === null || event?.entryPrice === undefined || Number.isNaN(Number(event?.entryPrice))
        ? null
        : Number(event.entryPrice);
    const stopLoss = event?.stopLoss === null || event?.stopLoss === undefined || Number.isNaN(Number(event?.stopLoss))
        ? null
        : Number(event.stopLoss);
    const takeProfit = event?.takeProfit === null || event?.takeProfit === undefined || Number.isNaN(Number(event?.takeProfit))
        ? null
        : Number(event.takeProfit);
    const threshold = event?.threshold === null || event?.threshold === undefined || Number.isNaN(Number(event?.threshold))
        ? null
        : Number(event.threshold);
    const referencePrice = event?.priceSnapshot === null || event?.priceSnapshot === undefined || Number.isNaN(Number(event?.priceSnapshot))
        ? null
        : Number(event.priceSnapshot);

    if (event.kind === 'trade_plan') {
        const isBuy = (event.action || 'BUY') === 'BUY';
        if (takeProfit !== null && ((isBuy && currentPrice >= takeProfit) || (!isBuy && currentPrice <= takeProfit))) {
            return {
                label: '已触及止盈区',
                description: `当前价格 ${formatNumber(currentPrice)} 已到达计划止盈位 ${formatNumber(takeProfit)}。`,
                tone: 'positive',
            };
        }

        if (stopLoss !== null && ((isBuy && currentPrice <= stopLoss) || (!isBuy && currentPrice >= stopLoss))) {
            return {
                label: '已触及止损区',
                description: `当前价格 ${formatNumber(currentPrice)} 已触达计划止损位 ${formatNumber(stopLoss)}。`,
                tone: 'negative',
            };
        }

        if (entryPrice !== null) {
            const distance = Math.abs(((currentPrice - entryPrice) / entryPrice) * 100);
            const reachedEntry = isBuy ? currentPrice >= entryPrice : currentPrice <= entryPrice;
            return {
                label: reachedEntry ? '已进入计划区间' : '仍在等待入场',
                description: reachedEntry
                    ? `当前价格 ${formatNumber(currentPrice)} 已越过计划入场位 ${formatNumber(entryPrice)}。`
                    : `当前价格距离计划入场位 ${formatNumber(entryPrice)} 仍有 ${formatNumber(distance, 2)}% 空间。`,
                tone: reachedEntry ? 'warning' : 'neutral',
            };
        }
    }

    if (event.kind === 'alert_plan' && threshold !== null) {
        const condition = event.condition || '';
        const triggered = (
            (condition === 'price_above' && currentPrice >= threshold)
            || (condition === 'price_below' && currentPrice <= threshold)
        );
        return {
            label: triggered ? '提醒条件已满足' : '提醒条件未触发',
            description: triggered
                ? `当前价格 ${formatNumber(currentPrice)} 已满足提醒阈值 ${formatNumber(threshold)}。`
                : `当前价格 ${formatNumber(currentPrice)} 尚未到达提醒阈值 ${formatNumber(threshold)}。`,
            tone: triggered ? 'positive' : 'neutral',
        };
    }

    if (event.kind === 'alert_triggered') {
        const result = evaluateAlertHitFollowThrough(event, quote);
        return {
            label: result.label,
            description: result.description,
            tone: result.state === 'continued'
                ? 'positive'
                : result.state === 'reversed'
                    ? 'negative'
                    : 'neutral',
        };
    }

    if (referencePrice !== null && referencePrice !== 0) {
        const movePercent = ((currentPrice - referencePrice) / referencePrice) * 100;
        const absoluteMove = Math.abs(movePercent);
        const isBullishSignal = ['price_up', 'touch_high', 'trade_plan'].includes(event.kind) || event.tone === 'positive';
        const isBearishSignal = ['price_down', 'touch_low'].includes(event.kind) || event.tone === 'negative';

        if (isBullishSignal) {
            const continued = movePercent >= 0;
            return {
                label: continued ? '后续仍在走强' : '后续出现回吐',
                description: `相对事件发生时已${continued ? '继续抬升' : '回落'} ${formatNumber(absoluteMove, 2)}%。`,
                tone: continued ? 'positive' : 'negative',
            };
        }

        if (isBearishSignal) {
            const stillWeak = movePercent <= 0;
            return {
                label: stillWeak ? '后续继续走弱' : '后续出现反弹',
                description: `相对事件发生时已${stillWeak ? '继续回落' : '反弹修复'} ${formatNumber(absoluteMove, 2)}%。`,
                tone: stillWeak ? 'negative' : 'positive',
            };
        }

        return {
            label: movePercent >= 0 ? '后续偏强' : '后续偏弱',
            description: `相对事件发生时价格变化 ${movePercent >= 0 ? '+' : ''}${formatNumber(movePercent, 2)}%。`,
            tone: movePercent >= 0 ? 'positive' : 'negative',
        };
    }

    return {
        label: '等待后效判断',
        description: '当前事件还缺少足够的参考价位，先继续观察。',
        tone: 'neutral',
    };
};

const renderMetricCard = (label, value, subtle, accentColor) => (
    <div
        style={{
            height: '100%',
            padding: '12px 14px',
            borderRadius: 13,
            background: SNAPSHOT_CARD_BG,
            border: `1px solid ${accentColor || 'var(--border-color)'}`,
            boxShadow: '0 8px 20px rgba(15, 23, 42, 0.045)',
        }}
    >
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.06em', marginBottom: 6 }}>
            {label}
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.12 }}>
            {value}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6, minHeight: 16, lineHeight: 1.5 }}>
            {subtle || '\u00A0'}
        </div>
    </div>
);

const RealtimeStockDetailModal = ({ open, symbol, quote, quoteMap = null, onCancel, onQuickTrade = null, eventTimeline = EMPTY_LIST, compareCandidates, compareTimelineMap }) => {
    const safeCompareCandidates = useMemo(
        () => dedupeCompareCandidates(Array.isArray(compareCandidates) ? compareCandidates : EMPTY_LIST),
        [compareCandidates]
    );
    const safeCompareTimelineMap = useMemo(
        () => (compareTimelineMap && typeof compareTimelineMap === 'object' ? compareTimelineMap : {}),
        [compareTimelineMap]
    );
    const compareSelectionMemoryRef = useRef({});
    const displaySymbol = symbol || quote?.symbol || '--';
    const displayName = getDisplayName(displaySymbol);
    const categoryLabel = getCategoryLabel(displaySymbol);
    const hasChange = quote?.change !== null && quote?.change !== undefined && !Number.isNaN(Number(quote.change));
    const isPositive = hasChange ? Number(quote.change) >= 0 : null;
    const changeColor = isPositive === null
        ? 'var(--text-secondary)'
        : isPositive
            ? 'var(--accent-success)'
            : 'var(--accent-danger)';
    const spreadValue = formatSpread(quote?.bid, quote?.ask);
    const rangePercent = formatRangePercent(quote?.low, quote?.high, quote?.previous_close);
    const [selectedCompareSymbols, setSelectedCompareSymbols] = useState([]);
    const [intradayTrendSeries, setIntradayTrendSeries] = useState(EMPTY_LIST);
    const snapshotTrendSeries = useMemo(() => buildSnapshotTrendSeries(quote), [quote]);
    const snapshotTrendPolyline = useMemo(() => buildTrendPolyline(snapshotTrendSeries), [snapshotTrendSeries]);
    const intradayTrendPolyline = useMemo(() => buildTrendPolyline(intradayTrendSeries), [intradayTrendSeries]);
    const compareTargetSymbols = useMemo(
        () => safeCompareCandidates
            .filter((item) => item?.symbol && item.symbol !== displaySymbol)
            .map((item) => item.symbol),
        [displaySymbol, safeCompareCandidates]
    );
    const effectiveSelectedCompareSymbols = useMemo(
        () => sanitizeCompareSymbols(selectedCompareSymbols, compareTargetSymbols, displaySymbol),
        [compareTargetSymbols, displaySymbol, selectedCompareSymbols]
    );

    useEffect(() => {
        if (!open || !displaySymbol || displaySymbol === '--') {
            setIntradayTrendSeries(EMPTY_LIST);
            return undefined;
        }

        let cancelled = false;
        const loadIntradayTrend = async () => {
            try {
                const response = await getKlines(displaySymbol, '1h', 32);
                if (cancelled) {
                    return;
                }
                setIntradayTrendSeries(buildIntradayTrendSeries(response?.klines || response?.data?.klines || []));
            } catch (error) {
                if (!cancelled) {
                    setIntradayTrendSeries(EMPTY_LIST);
                }
            }
        };

        loadIntradayTrend();

        return () => {
            cancelled = true;
        };
    }, [displaySymbol, open]);

    useEffect(() => {
        if (!open) {
            return;
        }

        const rememberedTargets = Array.isArray(compareSelectionMemoryRef.current[displaySymbol])
            ? sanitizeCompareSymbols(compareSelectionMemoryRef.current[displaySymbol], compareTargetSymbols, displaySymbol)
            : [];
        const nextTargets = rememberedTargets.length > 0
            ? rememberedTargets
            : compareTargetSymbols.slice(0, 2);
        compareSelectionMemoryRef.current[displaySymbol] = nextTargets;
        setSelectedCompareSymbols((prev) => (isSameSymbolList(prev, nextTargets) ? prev : nextTargets));
    }, [compareTargetSymbols, displaySymbol, open]);

    const signalSummary = useMemo(() => buildSignalSummary(quote, eventTimeline), [eventTimeline, quote]);
    const quickTradeDraft = useMemo(() => buildQuickTradeDraft(displaySymbol, quote, signalSummary), [displaySymbol, quote, signalSummary]);
    const compareCards = useMemo(
        () => buildCompareCards(displaySymbol, quote, safeCompareCandidates, effectiveSelectedCompareSymbols, safeCompareTimelineMap),
        [displaySymbol, effectiveSelectedCompareSymbols, quote, safeCompareCandidates, safeCompareTimelineMap]
    );

    const toggleCompareSymbol = (targetSymbol) => {
        if (!compareTargetSymbols.includes(targetSymbol)) {
            return;
        }

        setSelectedCompareSymbols((prev) => {
            const normalizedPrev = sanitizeCompareSymbols(prev, compareTargetSymbols, displaySymbol);
            let nextSelection;
            if (normalizedPrev.includes(targetSymbol)) {
                nextSelection = normalizedPrev.filter((item) => item !== targetSymbol);
            } else {
                nextSelection = [...normalizedPrev, targetSymbol].slice(0, 3);
            }
            compareSelectionMemoryRef.current[displaySymbol] = nextSelection;
            return nextSelection;
        });
    };

    return (
        <Modal
            title={
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                            <span style={{ display: 'flex', alignItems: 'center', fontWeight: 800, fontSize: 18, color: 'var(--text-primary)' }}>
                                <FundOutlined style={{ marginRight: 8, color: '#1677ff' }} />
                                {displayName} 深度详情
                            </span>
                            <Tag color="blue" style={{ margin: 0, borderRadius: 999, paddingInline: 9, fontWeight: 700 }}>
                                {categoryLabel}
                            </Tag>
                            <Tag color={quote ? 'success' : 'default'} style={{ margin: 0, borderRadius: 999, paddingInline: 9, fontWeight: 700 }}>
                                {displaySymbol}
                            </Tag>
                        </div>
                        <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.55 }}>
                            把实时快照、盘中信号和全维分析压缩到一个弹窗里，便于快速研判。
                        </div>
                    </div>

                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 9, paddingBlock: 3, fontWeight: 700 }}>
                            日内振幅 {rangePercent}
                        </Tag>
                        <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 9, paddingBlock: 3, fontWeight: 700 }}>
                            点差 {spreadValue}
                        </Tag>
                    </div>
                </div>
            }
            open={open}
            onCancel={onCancel}
            footer={null}
            width={1280}
            destroyOnHidden
            modalRender={(node) => <div data-testid="realtime-stock-detail-modal">{node}</div>}
            styles={{
                body: {
                    padding: 20,
                    background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-primary) 92%, white 8%) 0%, var(--bg-primary) 220px)',
                },
            }}
        >
            <div style={{ display: 'grid', gap: 18 }}>
                <section
                    style={{
                        padding: 16,
                        borderRadius: 18,
                        background: SNAPSHOT_PANEL_BG,
                        border: '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)',
                        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.10)',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 14 }}>
                        <div style={{ display: 'grid', gap: 10 }}>
                            <div>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>标的代码</div>
                                <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.1 }}>
                                    {displaySymbol}
                                </div>
                                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 8 }}>
                                    {displayName}
                                </div>
                            </div>

                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(255,255,255,0.72)', paddingInline: 8 }}>
                                    数据源 {quote?.source || '--'}
                                </Tag>
                                <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(255,255,255,0.72)', paddingInline: 8 }}>
                                    更新时间 {formatTimestamp(quote?.timestamp)}
                                </Tag>
                            </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                                实时变化
                            </div>
                            <div style={{ fontSize: 30, fontWeight: 800, color: changeColor, lineHeight: 1 }}>
                                {quote ? formatSignedNumber(quote.change_percent, 2, '%') : '--'}
                            </div>
                            <div style={{ fontSize: 13, color: changeColor, marginTop: 8 }}>
                                {quote ? formatSignedNumber(quote.change) : '等待实时数据'}
                            </div>
                        </div>
                    </div>

                    {quote && (intradayTrendPolyline || snapshotTrendPolyline) ? (
                        <div
                            data-testid="detail-snapshot-trend"
                            style={{
                                marginBottom: 14,
                                padding: '10px 12px',
                                borderRadius: 15,
                                background: 'rgba(255,255,255,0.72)',
                                border: '1px solid rgba(148, 163, 184, 0.18)',
                            }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
                                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.04em' }}>
                                    盘中走势
                                </div>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                    {intradayTrendPolyline ? '基于最近一段 K 线收盘价' : '昨收 / 开盘 / 低点 / 现价 / 高点'}
                                </div>
                            </div>
                            <svg
                                width="100%"
                                height="82"
                                viewBox="0 0 320 82"
                                preserveAspectRatio="none"
                                role="img"
                                aria-label={`${displaySymbol} 盘中走势线`}
                            >
                                <polyline
                                    fill="none"
                                    stroke={changeColor}
                                    strokeWidth="3"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    points={intradayTrendPolyline || snapshotTrendPolyline}
                                />
                            </svg>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
                                {(intradayTrendPolyline ? [
                                    intradayTrendSeries[0],
                                    intradayTrendSeries[Math.max(0, Math.floor(intradayTrendSeries.length / 2))],
                                    intradayTrendSeries[intradayTrendSeries.length - 1],
                                ] : snapshotTrendSeries).filter(Boolean).map((item) => (
                                    <span
                                        key={`${displaySymbol}-${item.label}-${item.value}`}
                                        style={{ fontSize: 10, color: 'var(--text-secondary)' }}
                                    >
                                        {intradayTrendPolyline ? `${formatTimestamp(item.label)} ${formatNumber(item.value)}` : `${item.label} ${formatNumber(item.value)}`}
                                    </span>
                                ))}
                            </div>
                        </div>
                    ) : null}

                    {quote ? (
                        <Row gutter={[14, 14]}>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('最新价', formatNumber(quote.price), '来自实时行情流', '#91caff')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('开盘 / 昨收', `${formatNumber(quote.open)} / ${formatNumber(quote.previous_close)}`, '开盘价与上一交易日收盘', '#b7eb8f')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('日内区间', `${formatNumber(quote.low)} - ${formatNumber(quote.high)}`, '最低价到最高价', '#ffd591')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('成交量', formatVolume(quote.volume), '实时累计成交量', '#d3adf7')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('买一 / 卖一', `${formatOrderBookValue(quote.bid)} / ${formatOrderBookValue(quote.ask)}`, '盘口最优报价', '#ffe58f')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('买卖点差', spreadValue, '买一和卖一的差值', '#87e8de')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('日内振幅', rangePercent, '基于昨收估算的区间波动', '#ffccc7')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('详情主体', '全维分析', '下方按 Tab 查看趋势、量价、情绪等', '#adc6ff')}
                            </Col>
                        </Row>
                    ) : (
                        <Empty
                            image={Empty.PRESENTED_IMAGE_SIMPLE}
                            description={
                                <div data-testid="realtime-quote-waiting">
                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>等待实时快照</div>
                                    <div style={{ marginTop: 6, color: 'var(--text-secondary)' }}>
                                        当前还没收到 {displaySymbol} 的实时 quote，历史分析仍会继续加载。
                                    </div>
                                </div>
                            }
                        />
                    )}
                </section>

                <section
                    style={{
                        borderRadius: 18,
                        border: '1px solid var(--border-color)',
                        background: 'var(--bg-secondary)',
                        padding: 16,
                        boxShadow: '0 8px 26px rgba(15, 23, 42, 0.06)',
                    }}
                    data-testid="detail-signal-summary"
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 700 }}>
                                <RiseOutlined />
                                信号总表
                            </div>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                                先用一屏判断强弱，再决定往下展开哪块分析。
                            </Text>
                        </div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                            <Tag color="blue" style={{ margin: 0, borderRadius: 999, paddingInline: 9, fontWeight: 700 }}>
                                综合分 {signalSummary.totalScore}
                            </Tag>
                            <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 9, fontWeight: 700 }}>
                                {signalSummary.conviction}
                            </Tag>
                            {onQuickTrade && quickTradeDraft ? (
                                <Button size="small" type="primary" onClick={() => onQuickTrade(displaySymbol, quickTradeDraft)}>
                                    带入交易
                                </Button>
                            ) : null}
                        </div>
                    </div>

                    <Row gutter={[14, 14]}>
                        <Col xs={24} sm={12} lg={6}>
                            {renderMetricCard('综合判断', `${signalSummary.totalScore}`, signalSummary.conviction, '#91caff')}
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                            {renderMetricCard('动能信号', signalSummary.momentumLabel, quote ? formatSignedNumber(quote.change_percent, 2, '%') : '等待实时数据', '#b7eb8f')}
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                            {renderMetricCard('波动信号', signalSummary.volatilityLabel, `日内振幅 ${rangePercent}`, '#ffd591')}
                        </Col>
                        <Col xs={24} sm={12} lg={6}>
                            {renderMetricCard('事件方向', signalSummary.eventLabel, signalSummary.eventBreakdown, '#d3adf7')}
                        </Col>
                    </Row>
                </section>

                <section
                    style={{
                        borderRadius: 18,
                        border: '1px solid var(--border-color)',
                        background: 'var(--bg-secondary)',
                        padding: 18,
                        boxShadow: '0 8px 26px rgba(15, 23, 42, 0.06)',
                    }}
                    data-testid="detail-compare-mode"
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 700 }}>
                                <DotChartOutlined />
                                对比模式
                            </div>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                选几个同组标的一起看快照和信号分，适合盘中比较谁更强、谁更稳、谁更值得往下深挖。
                            </Text>
                        </div>
                        <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10, fontWeight: 700 }}>
                            已选对比 {effectiveSelectedCompareSymbols.length}
                        </Tag>
                    </div>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
                        {safeCompareCandidates.filter((item) => item?.symbol !== displaySymbol).slice(0, 6).map((item) => {
                            const selected = effectiveSelectedCompareSymbols.includes(item.symbol);
                            return (
                                <Button
                                    key={item.symbol}
                                    type={selected ? 'primary' : 'default'}
                                    size="small"
                                    className="realtime-compare-toggle"
                                    aria-pressed={selected}
                                    onClick={() => toggleCompareSymbol(item.symbol)}
                                    style={{
                                        borderRadius: 999,
                                        border: `1px solid ${selected ? 'rgba(37, 99, 235, 0.32)' : 'var(--border-color)'}`,
                                        background: selected ? 'rgba(37, 99, 235, 0.08)' : 'rgba(15, 23, 42, 0.03)',
                                        color: selected ? '#1d4ed8' : 'var(--text-primary)',
                                        padding: '8px 12px',
                                        fontWeight: 700,
                                    }}
                                >
                                    {item.symbol}
                                </Button>
                            );
                        })}
                    </div>

                    <div data-testid="detail-compare-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                        {compareCards.map((item) => (
                            <div
                                key={item.symbol}
                                style={{
                                    padding: 16,
                                    borderRadius: 16,
                                    border: `1px solid ${item.symbol === displaySymbol ? 'rgba(37, 99, 235, 0.28)' : 'var(--border-color)'}`,
                                    background: item.symbol === displaySymbol ? 'rgba(37, 99, 235, 0.06)' : 'rgba(255,255,255,0.72)',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start', marginBottom: 10 }}>
                                    <div>
                                        <div style={{ fontWeight: 800, color: 'var(--text-primary)' }}>
                                            {item.symbol}
                                        </div>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                                            {item.name}
                                        </div>
                                    </div>
                                    {item.symbol === displaySymbol ? (
                                        <Tag color="blue" style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>当前标的</Tag>
                                    ) : null}
                                </div>

                                <div style={{ display: 'grid', gap: 8 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                                        <span style={{ color: 'var(--text-secondary)' }}>最新价</span>
                                        <strong>{formatNumber(item.quote?.price)}</strong>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                                        <span style={{ color: 'var(--text-secondary)' }}>涨跌幅</span>
                                        <strong>{formatSignedNumber(item.quote?.change_percent, 2, '%')}</strong>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                                        <span style={{ color: 'var(--text-secondary)' }}>日内振幅</span>
                                        <strong>{formatRangePercent(item.quote?.low, item.quote?.high, item.quote?.previous_close)}</strong>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                                        <span style={{ color: 'var(--text-secondary)' }}>综合分</span>
                                        <strong>{item.signalSummary.totalScore}</strong>
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                        {item.signalSummary.conviction} · {item.signalSummary.eventLabel}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>

                <section
                    style={{
                        borderRadius: 18,
                        border: '1px solid var(--border-color)',
                        background: 'var(--bg-secondary)',
                        padding: 18,
                        boxShadow: '0 8px 26px rgba(15, 23, 42, 0.06)',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 700 }}>
                                <ClockCircleOutlined />
                                盘中时间线
                            </div>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                把实时异动、提醒草稿、交易计划和复盘记录串起来，便于快速回看这只标的在盘中的决策过程。
                            </Text>
                        </div>
                        <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10, fontWeight: 700 }}>
                            最近事件 {eventTimeline.length}
                        </Tag>
                    </div>

                    {eventTimeline.length ? (
                        <div data-testid="detail-event-timeline" style={{ display: 'grid', gap: 12 }}>
                            {eventTimeline.map((event) => {
                                const toneStyle = getTimelineToneStyle(event.tone);
                                const followThrough = event.kind === 'alert_triggered'
                                    ? (() => {
                                        const result = evaluateAlertHitFollowThrough(event, quote, quoteMap || {});
                                        return {
                                            label: result.label,
                                            description: result.description,
                                            tone: result.state === 'continued'
                                                ? 'positive'
                                                : result.state === 'reversed'
                                                    ? 'negative'
                                                    : 'neutral',
                                        };
                                    })()
                                    : getFollowThroughSummary(event, quote);
                                const followToneStyle = getTimelineToneStyle(followThrough.tone);
                                return (
                                    <div
                                        key={event.id}
                                        style={{
                                            display: 'grid',
                                            gap: 10,
                                            padding: '14px 16px',
                                            borderRadius: 16,
                                            border: `1px solid ${toneStyle.borderColor}`,
                                            background: toneStyle.background,
                                        }}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                                <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(255,255,255,0.72)', color: toneStyle.color, fontWeight: 700 }}>
                                                    {event.sourceLabel || '事件'}
                                                </Tag>
                                                <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                                                    {event.title || '未命名事件'}
                                                </span>
                                            </div>
                                            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                                {formatTimelineTime(event.createdAt)}
                                            </span>
                                        </div>
                                        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                                            {event.description || '暂无更多说明'}
                                        </div>
                                        <div
                                            style={{
                                                display: 'grid',
                                                gap: 6,
                                                padding: '10px 12px',
                                                borderRadius: 14,
                                                border: `1px solid ${followToneStyle.borderColor}`,
                                                background: 'rgba(255,255,255,0.72)',
                                            }}
                                        >
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                                <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: followToneStyle.background, color: followToneStyle.color, fontWeight: 700 }}>
                                                    后效跟踪
                                                </Tag>
                                                <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                                                    {followThrough.label}
                                                </span>
                                            </div>
                                            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                                {followThrough.description}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <Empty
                            image={Empty.PRESENTED_IMAGE_SIMPLE}
                            description={
                                <div data-testid="detail-event-timeline-empty">
                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>还没有积累到盘中事件</div>
                                    <div style={{ marginTop: 6, color: 'var(--text-secondary)' }}>
                                        当这只标的触发异动、生成提醒或保存复盘快照后，这里会自动出现一条时间线。
                                    </div>
                                </div>
                            }
                        />
                    )}
                </section>

                <section
                    style={{
                        borderRadius: 18,
                        border: '1px solid var(--border-color)',
                        background: 'var(--bg-secondary)',
                        padding: 18,
                        boxShadow: '0 8px 26px rgba(15, 23, 42, 0.06)',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 700 }}>
                                <DotChartOutlined />
                                全维分析
                            </div>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                总览、趋势、量价、情绪、形态、基本面、行业、风险、相关性与 AI 预测
                            </Text>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: 12 }}>
                            <RiseOutlined />
                            <span>分析数据来自历史行情与现有分析接口</span>
                            <ClockCircleOutlined />
                        </div>
                    </div>

                    {symbol ? (
                        <MarketAnalysis key={symbol} symbol={symbol} embedMode />
                    ) : (
                        <Empty description="暂无可分析的标的" />
                    )}
                </section>
            </div>
        </Modal>
    );
};

export default RealtimeStockDetailModal;
