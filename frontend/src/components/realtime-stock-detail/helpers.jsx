/**
 * Shared pure helpers for RealtimeStockDetailModal (layer 1 split).
 *
 * Verbatim extraction of the module-level constants and pure functions that
 * previously lived at the top of RealtimeStockDetailModal.jsx. No hooks, no
 * component state — just formatters, chart-model builders, signal/compare/
 * follow-through logic, and the shared metric-card renderer. Both the parent
 * orchestrator and the extracted section children import from here so the math
 * and formatting stay identical across the split.
 */

import { STOCK_DATABASE } from '../../constants/stocks';
import { evaluateAlertHitFollowThrough } from '../../utils/realtimeSignals';
import { getCategoryLabel as getCategoryLabelForType, inferSymbolCategory } from '../../utils/realtimeFormatters';

export const SNAPSHOT_PANEL_BG = 'linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 14%, var(--bg-secondary) 86%) 0%, color-mix(in srgb, var(--accent-secondary) 14%, var(--bg-secondary) 86%) 100%)';
export const SNAPSHOT_CARD_BG = 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)';
export const EMPTY_LIST = [];
export const TREND_CHART_WIDTH = 960;
export const TREND_CHART_HEIGHT = 132;
export const TREND_CHART_PADDING = {
    top: 18,
    right: 92,
    bottom: 28,
    left: 36,
};

export const getDisplayName = (symbol) => {
    const info = STOCK_DATABASE[symbol];
    return info?.cn || info?.en || symbol || '未知标的';
};

export const getCategoryLabel = (symbol) => getCategoryLabelForType(inferSymbolCategory(symbol));

export const formatNumber = (value, digits = 2, fallback = '--') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return fallback;
    }
    return Number(value).toFixed(digits);
};

export const formatSignedNumber = (value, digits = 2, suffix = '', fallback = '--') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return fallback;
    }

    const numericValue = Number(value);
    return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(digits)}${suffix}`;
};

export const formatVolume = (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '--';
    }

    const volume = Number(value);
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(2)}K`;
    return `${volume}`;
};

export const formatTimestamp = (value) => {
    if (!value) return '--';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString();
};

export const formatCompactTimestamp = (value) => {
    if (!value) return '--';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
};

export const hasTradableOrderBookValue = (value) => (
    value !== null
    && value !== undefined
    && !Number.isNaN(Number(value))
    && Number(value) > 0
);

export const formatOrderBookValue = (value) => {
    if (!hasTradableOrderBookValue(value)) {
        return '--';
    }
    return Number(value).toFixed(2);
};

export const formatSpread = (bid, ask) => {
    if (!hasTradableOrderBookValue(bid) || !hasTradableOrderBookValue(ask)) {
        return '--';
    }

    return Number(Number(ask) - Number(bid)).toFixed(2);
};

export const normalizeOrderBookNumber = (value) => (
    hasTradableOrderBookValue(value) ? Number(value) : null
);

export const extractOrderBookProbe = (payload = null) => {
    const data = payload?.data || payload || {};
    const metrics = data.metrics || {};
    const bestBid = normalizeOrderBookNumber(metrics.best_bid ?? data.bids?.[0]?.price);
    const bestAsk = normalizeOrderBookNumber(metrics.best_ask ?? data.asks?.[0]?.price);

    if (bestBid === null && bestAsk === null) {
        return null;
    }

    return {
        bid: bestBid,
        ask: bestAsk,
        source: data.source || metrics.source || 'orderbook_probe',
        mode: data.mode || null,
        isSynthetic: Boolean(data.is_synthetic ?? data.diagnostics?.is_synthetic),
    };
};

export const buildEffectiveOrderBook = (quote = null, probe = null, status = 'idle') => {
    const quoteBid = normalizeOrderBookNumber(quote?.bid);
    const quoteAsk = normalizeOrderBookNumber(quote?.ask);
    const probeBid = normalizeOrderBookNumber(probe?.bid);
    const probeAsk = normalizeOrderBookNumber(probe?.ask);
    const bid = quoteBid ?? probeBid;
    const ask = quoteAsk ?? probeAsk;
    const hasQuoteSide = quoteBid !== null || quoteAsk !== null;
    const hasProbeSide = !hasQuoteSide && (probeBid !== null || probeAsk !== null);

    let subtle = '盘口最优报价';
    if (hasProbeSide) {
        const sourceLabel = probe?.source ? ` · ${probe.source}` : '';
        subtle = probe?.isSynthetic
            ? `盘口代理估算${sourceLabel}`
            : `盘口探测补全${sourceLabel}`;
    } else if (status === 'loading') {
        subtle = '盘口探测中';
    } else if (!hasQuoteSide) {
        subtle = '当前数据源未返回 bid/ask';
    }

    return {
        bid,
        ask,
        subtle,
        source: hasProbeSide ? probe?.source : quote?.source,
        isProbe: hasProbeSide,
    };
};

export const formatTimelineTime = (value) => {
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

export const getTimelineToneStyle = (tone = 'neutral') => {
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

export const formatRangePercent = (low, high, previousClose) => {
    if ([low, high, previousClose].some(value => value === null || value === undefined || Number.isNaN(Number(value))) || Number(previousClose) === 0) {
        return '--';
    }

    return `${(((Number(high) - Number(low)) / Number(previousClose)) * 100).toFixed(2)}%`;
};

export const getNumericRangePercent = (quote) => {
    const low = Number(quote?.low);
    const high = Number(quote?.high);
    const previousClose = Number(quote?.previous_close);

    if ([low, high, previousClose].some((value) => Number.isNaN(value)) || previousClose === 0) {
        return null;
    }

    return ((high - low) / previousClose) * 100;
};

export const buildSnapshotTrendSeries = (quote = null) => {
    const open = Number(quote?.open);
    const low = Number(quote?.low);
    const high = Number(quote?.high);
    const price = Number(quote?.price);
    const hasOpen = Number.isFinite(open) && open > 0;
    const hasPrice = Number.isFinite(price) && price > 0;
    const rangePoints = hasOpen && hasPrice && price < open
        ? [
            { label: '高点', value: high },
            { label: '低点', value: low },
        ]
        : [
            { label: '低点', value: low },
            { label: '高点', value: high },
        ];
    const points = [
        { label: '昨收', value: Number(quote?.previous_close) },
        { label: '开盘', value: Number(quote?.open) },
        ...rangePoints,
        { label: '现价', value: price },
    ].filter((item) => Number.isFinite(item.value) && item.value > 0);

    return points.length >= 2 ? points : EMPTY_LIST;
};

export const buildTrendChartModel = (
    series = [],
    width = TREND_CHART_WIDTH,
    height = TREND_CHART_HEIGHT,
    padding = TREND_CHART_PADDING
) => {
    if (!Array.isArray(series) || series.length < 2) {
        return null;
    }

    const values = series.map((item) => item.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const points = series.map((item, index) => {
        const x = padding.left + (index * chartWidth) / (series.length - 1);
        const y = padding.top + ((max - item.value) / span) * chartHeight;
        return { ...item, x, y };
    });
    const firstPoint = points[0];
    const lastPoint = points[points.length - 1];
    const midPoint = points[Math.max(0, Math.floor(points.length / 2))];
    const linePoints = points.map((item) => `${item.x.toFixed(2)},${item.y.toFixed(2)}`).join(' ');
    const baseline = height - padding.bottom;
    const baselineY = firstPoint.y;
    const areaPoints = [
        `${firstPoint.x.toFixed(2)},${baseline}`,
        linePoints,
        `${lastPoint.x.toFixed(2)},${baseline}`,
    ].join(' ');
    const changePercent = Number(firstPoint.value)
        ? ((Number(lastPoint.value) - Number(firstPoint.value)) / Number(firstPoint.value)) * 100
        : null;
    const latestBadgeWidth = 116;
    const latestBadgeHeight = 24;
    const latestBadgeX = Math.min(
        Math.max(lastPoint.x - latestBadgeWidth + 10, padding.left),
        width - padding.right - latestBadgeWidth + 24
    );
    const latestBadgeY = Math.min(
        Math.max(lastPoint.y - latestBadgeHeight - 8, padding.top),
        height - padding.bottom - latestBadgeHeight
    );
    const yAxisLabels = [
        { label: '高', value: max, y: padding.top },
        { label: '中', value: (max + min) / 2, y: padding.top + chartHeight / 2 },
        { label: '低', value: min, y: baseline },
    ];

    return {
        points,
        firstPoint,
        midPoint,
        lastPoint,
        baselineY,
        linePoints,
        areaPoints,
        min,
        max,
        changePercent,
        latestBadge: {
            x: latestBadgeX,
            y: latestBadgeY,
            width: latestBadgeWidth,
            height: latestBadgeHeight,
        },
        yAxisLabels,
        gridY: [
            padding.top,
            padding.top + chartHeight / 2,
            baseline,
        ],
        labels: [firstPoint, midPoint, lastPoint].filter((item, index, list) => (
            item && list.findIndex((candidate) => candidate.label === item.label && candidate.value === item.value) === index
        )),
    };
};

export const buildIntradayTrendSeries = (klines = []) => (
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

export const buildSignalSummary = (quote = null, eventTimeline = []) => {
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

export const getSuggestedTradeQuantity = (symbol, price) => {
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

export const buildQuickTradeDraft = (symbol, quote, signalSummary) => {
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

export const buildCompareCards = (displaySymbol, quote, compareCandidates = [], selectedCompareSymbols = [], timelineBySymbol = {}) => {
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

export const getCompareQuoteStatus = (quote, isPrimaryCard = false) => {
    if (quote) {
        return {
            label: isPrimaryCard ? '当前快照已就绪' : '实时就绪',
            tone: 'ready',
            description: '行情字段已经到位，可直接横向比较强弱。',
        };
    }

    return {
        label: isPrimaryCard ? '等待当前快照' : '待补数',
        tone: 'pending',
        description: '正在补请求这张对比卡的实时 quote，回来后会自动刷新。',
    };
};

export const isSameSymbolList = (left = [], right = []) => (
    left.length === right.length && left.every((item, index) => item === right[index])
);

export const dedupeCompareCandidates = (items = []) => {
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

export const sanitizeCompareSymbols = (symbols = [], availableTargets = [], displaySymbol) => {
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


export const getFollowThroughSummary = (event = {}, quote = null) => {
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

export const renderMetricCard = (label, value, subtle, accentColor) => (
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
            {subtle || ' '}
        </div>
    </div>
);
