import { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Tag } from 'antd';
import { FundOutlined } from '@ant-design/icons';
import { getKlines, getRealtimeOrderbook } from '../services/api';
import {
    EMPTY_LIST,
    getDisplayName,
    getCategoryLabel,
    formatSignedNumber,
    formatNumber,
    formatSpread,
    formatOrderBookValue,
    formatRangePercent,
    hasTradableOrderBookValue,
    extractOrderBookProbe,
    buildEffectiveOrderBook,
    buildSnapshotTrendSeries,
    buildTrendChartModel,
    buildIntradayTrendSeries,
    buildSignalSummary,
    buildCompareCards,
    isSameSymbolList,
    dedupeCompareCandidates,
    sanitizeCompareSymbols,
} from './realtime-stock-detail/helpers.jsx';
import SnapshotPanel from './realtime-stock-detail/SnapshotPanel.jsx';
import SignalSummaryPanel from './realtime-stock-detail/SignalSummaryPanel.jsx';
import ComparePanel from './realtime-stock-detail/ComparePanel.jsx';
import EventTimelinePanel from './realtime-stock-detail/EventTimelinePanel.jsx';
import AnalysisPanel from './realtime-stock-detail/AnalysisPanel.jsx';

const RealtimeStockDetailModal = ({
    open,
    symbol,
    quote,
    quoteMap = null,
    onCancel,
    onNavigateSymbol = null,
    eventTimeline = EMPTY_LIST,
    compareCandidates,
    compareTimelineMap,
}) => {
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
    const [selectedCompareSymbols, setSelectedCompareSymbols] = useState([]);
    const [intradayTrendSeries, setIntradayTrendSeries] = useState(EMPTY_LIST);
    const [orderBookProbe, setOrderBookProbe] = useState(null);
    const [orderBookProbeStatus, setOrderBookProbeStatus] = useState('idle');
    const hasQuoteForOrderBook = Boolean(quote);
    const effectiveOrderBook = useMemo(
        () => buildEffectiveOrderBook(quote, orderBookProbe, orderBookProbeStatus),
        [orderBookProbe, orderBookProbeStatus, quote]
    );
    const quoteWithOrderBook = useMemo(
        () => (quote ? {
            ...quote,
            bid: effectiveOrderBook.bid ?? quote.bid,
            ask: effectiveOrderBook.ask ?? quote.ask,
        } : quote),
        [effectiveOrderBook.ask, effectiveOrderBook.bid, quote]
    );
    const spreadValue = formatSpread(effectiveOrderBook.bid, effectiveOrderBook.ask);
    const orderBookPairValue = `${formatOrderBookValue(effectiveOrderBook.bid)} / ${formatOrderBookValue(effectiveOrderBook.ask)}`;
    const rangePercent = formatRangePercent(quote?.low, quote?.high, quote?.previous_close);
    const snapshotTrendSeries = useMemo(() => buildSnapshotTrendSeries(quote), [quote]);
    const trendUsesIntraday = intradayTrendSeries.length >= 2;
    const activeTrendSeries = trendUsesIntraday ? intradayTrendSeries : snapshotTrendSeries;
    const activeTrendChart = useMemo(() => buildTrendChartModel(activeTrendSeries), [activeTrendSeries]);
    const trendAreaGradientId = useMemo(
        () => `detail-trend-area-gradient-${String(displaySymbol || 'symbol').replace(/[^a-zA-Z0-9_-]/g, '-')}`,
        [displaySymbol]
    );
    const trendLineGradientId = useMemo(
        () => `detail-trend-line-gradient-${String(displaySymbol || 'symbol').replace(/[^a-zA-Z0-9_-]/g, '-')}`,
        [displaySymbol]
    );
    const activeTrendChangeText = activeTrendChart
        ? formatSignedNumber(activeTrendChart.changePercent, 2, '%')
        : '--';
    const activeTrendRangeText = activeTrendChart
        ? `${formatNumber(activeTrendChart.min)} - ${formatNumber(activeTrendChart.max)}`
        : '--';
    const activeTrendDirectionLabel = !activeTrendChart
        ? '走势待补'
        : Number(activeTrendChart.changePercent || 0) > 0
            ? '较起点上行'
            : Number(activeTrendChart.changePercent || 0) < 0
                ? '较起点回落'
                : '较起点持平';
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
        if (!open || !hasQuoteForOrderBook || !displaySymbol || displaySymbol === '--') {
            setOrderBookProbe(null);
            setOrderBookProbeStatus('idle');
            return undefined;
        }

        const quoteHasBothSides = hasTradableOrderBookValue(quote.bid) && hasTradableOrderBookValue(quote.ask);
        if (quoteHasBothSides) {
            setOrderBookProbe(null);
            setOrderBookProbeStatus('idle');
            return undefined;
        }

        let cancelled = false;
        setOrderBookProbeStatus('loading');
        setOrderBookProbe(null);

        const loadOrderBookProbe = async () => {
            try {
                const response = await getRealtimeOrderbook(displaySymbol, 1);
                if (cancelled) {
                    return;
                }
                setOrderBookProbe(extractOrderBookProbe(response));
                setOrderBookProbeStatus('ready');
            } catch (error) {
                if (!cancelled) {
                    setOrderBookProbe(null);
                    setOrderBookProbeStatus('error');
                }
            }
        };

        loadOrderBookProbe();

        return () => {
            cancelled = true;
        };
    }, [displaySymbol, hasQuoteForOrderBook, open, quote?.ask, quote?.bid, quote?.source]);

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

    const signalSummary = useMemo(() => buildSignalSummary(quoteWithOrderBook, eventTimeline), [eventTimeline, quoteWithOrderBook]);
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
                <SnapshotPanel
                    quote={quote}
                    displaySymbol={displaySymbol}
                    displayName={displayName}
                    changeColor={changeColor}
                    activeTrendChart={activeTrendChart}
                    trendUsesIntraday={trendUsesIntraday}
                    activeTrendSeries={activeTrendSeries}
                    activeTrendRangeText={activeTrendRangeText}
                    activeTrendChangeText={activeTrendChangeText}
                    activeTrendDirectionLabel={activeTrendDirectionLabel}
                    trendAreaGradientId={trendAreaGradientId}
                    trendLineGradientId={trendLineGradientId}
                    orderBookPairValue={orderBookPairValue}
                    effectiveOrderBook={effectiveOrderBook}
                    spreadValue={spreadValue}
                    rangePercent={rangePercent}
                />

                <SignalSummaryPanel
                    signalSummary={signalSummary}
                    quote={quote}
                    rangePercent={rangePercent}
                    displaySymbol={displaySymbol}
                />

                <ComparePanel
                    displaySymbol={displaySymbol}
                    safeCompareCandidates={safeCompareCandidates}
                    effectiveSelectedCompareSymbols={effectiveSelectedCompareSymbols}
                    compareCards={compareCards}
                    toggleCompareSymbol={toggleCompareSymbol}
                    onNavigateSymbol={onNavigateSymbol}
                />

                <EventTimelinePanel
                    eventTimeline={eventTimeline}
                    quote={quote}
                    quoteMap={quoteMap}
                />

                <AnalysisPanel symbol={symbol} />
            </div>
        </Modal>
    );
};

export default RealtimeStockDetailModal;
