/**
 * Snapshot panel for RealtimeStockDetailModal (layer 2 split).
 *
 * Pure render — no hooks, no data fetching. Owns the verbatim header / intraday
 * trend SVG / metric-card grid that previously lived inline at the top of the
 * parent modal body. Receives the parent's already-computed quote, trend-chart
 * model, order-book and range values, and emits nothing back. The parent stays
 * the orchestrator that owns the state, effects and memos; this child only
 * renders them.
 *
 * Lives in components/realtime-stock-detail/ alongside the sibling sections.
 */

import { Row, Col, Tag, Empty } from 'antd';
import {
    SNAPSHOT_PANEL_BG,
    TREND_CHART_WIDTH,
    TREND_CHART_HEIGHT,
    TREND_CHART_PADDING,
    formatNumber,
    formatVolume,
    formatSignedNumber,
    formatTimestamp,
    formatCompactTimestamp,
    renderMetricCard,
} from './helpers.jsx';

const SnapshotPanel = ({
    quote,
    displaySymbol,
    displayName,
    changeColor,
    activeTrendChart,
    trendUsesIntraday,
    activeTrendSeries,
    activeTrendRangeText,
    activeTrendChangeText,
    activeTrendDirectionLabel,
    trendAreaGradientId,
    trendLineGradientId,
    orderBookPairValue,
    effectiveOrderBook,
    spreadValue,
    rangePercent,
}) => (
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

        {quote && activeTrendChart ? (
            <div
                data-testid="detail-snapshot-trend"
                style={{
                    marginBottom: 14,
                    padding: '14px 14px 12px',
                    borderRadius: 16,
                    background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 84%, var(--accent-primary) 16%) 0%, color-mix(in srgb, var(--bg-secondary) 94%, var(--bg-primary) 6%) 100%)',
                    border: '1px solid color-mix(in srgb, var(--accent-primary) 22%, var(--border-color) 78%)',
                    boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.10), 0 14px 34px rgba(15, 23, 42, 0.10)',
                }}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 8 }}>
                    <div style={{ display: 'grid', gap: 3 }}>
                        <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--text-primary)' }}>
                            盘中走势
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                            {trendUsesIntraday ? `最近 ${activeTrendSeries.length} 根 1H K 线 · 收盘价` : '昨收 / 开盘 / 高低点 / 现价'}
                        </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 8, borderColor: 'rgba(148, 163, 184, 0.22)' }}>
                            区间 {activeTrendRangeText}
                        </Tag>
                        <Tag
                            color={Number(activeTrendChart.changePercent || 0) >= 0 ? 'success' : 'error'}
                            style={{ margin: 0, borderRadius: 999, paddingInline: 8, fontWeight: 700 }}
                        >
                            较起点 {activeTrendChangeText}
                        </Tag>
                    </div>
                </div>
                <svg
                    width="100%"
                    height="132"
                    viewBox={`0 0 ${TREND_CHART_WIDTH} ${TREND_CHART_HEIGHT}`}
                    preserveAspectRatio="none"
                    role="img"
                    aria-label={`${displaySymbol} 盘中走势线，${activeTrendDirectionLabel} ${activeTrendChangeText}，区间 ${activeTrendRangeText}`}
                >
                    <defs>
                        <linearGradient id={trendAreaGradientId} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={changeColor} stopOpacity="0.22" />
                            <stop offset="100%" stopColor={changeColor} stopOpacity="0.02" />
                        </linearGradient>
                        <linearGradient id={trendLineGradientId} x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor={changeColor} stopOpacity="0.58" />
                            <stop offset="100%" stopColor={changeColor} stopOpacity="1" />
                        </linearGradient>
                    </defs>
                    <rect
                        x="0.5"
                        y="0.5"
                        width={TREND_CHART_WIDTH - 1}
                        height={TREND_CHART_HEIGHT - 1}
                        rx="14"
                        fill="rgba(15, 23, 42, 0.10)"
                        stroke="rgba(148, 163, 184, 0.18)"
                    />
                    {activeTrendChart.gridY.map((y) => (
                        <line
                            key={`grid-${y}`}
                            x1={TREND_CHART_PADDING.left}
                            x2={TREND_CHART_WIDTH - TREND_CHART_PADDING.right}
                            y1={y}
                            y2={y}
                            stroke="rgba(148, 163, 184, 0.24)"
                            strokeWidth="1"
                            strokeDasharray="4 5"
                        />
                    ))}
                    <line
                        x1={TREND_CHART_PADDING.left}
                        x2={TREND_CHART_WIDTH - TREND_CHART_PADDING.right}
                        y1={activeTrendChart.baselineY}
                        y2={activeTrendChart.baselineY}
                        stroke={changeColor}
                        strokeWidth="1.2"
                        strokeOpacity="0.38"
                        strokeDasharray="7 6"
                    />
                    {activeTrendChart.yAxisLabels.map((item) => (
                        <text
                            key={`${item.label}-${item.value}`}
                            x={TREND_CHART_WIDTH - TREND_CHART_PADDING.right + 6}
                            y={item.y + 4}
                            fill="var(--text-secondary)"
                            fontSize="11"
                            fontWeight="700"
                        >
                            {formatNumber(item.value)}
                        </text>
                    ))}
                    <text
                        x={TREND_CHART_PADDING.left + 2}
                        y={Math.max(TREND_CHART_PADDING.top + 10, activeTrendChart.baselineY - 6)}
                        fill={changeColor}
                        fontSize="11"
                        fontWeight="800"
                    >
                        起点
                    </text>
                    <polygon
                        fill={`url(#${trendAreaGradientId})`}
                        points={activeTrendChart.areaPoints}
                    />
                    <line
                        x1={activeTrendChart.lastPoint.x}
                        x2={activeTrendChart.lastPoint.x}
                        y1={TREND_CHART_PADDING.top}
                        y2={TREND_CHART_HEIGHT - TREND_CHART_PADDING.bottom}
                        stroke={changeColor}
                        strokeWidth="1"
                        strokeOpacity="0.24"
                    />
                    <polyline
                        fill="none"
                        stroke={`url(#${trendLineGradientId})`}
                        strokeWidth="3.2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        points={activeTrendChart.linePoints}
                    />
                    {[activeTrendChart.firstPoint, activeTrendChart.lastPoint].map((point) => (
                        <circle
                            key={`${point.label}-${point.value}`}
                            cx={point.x}
                            cy={point.y}
                            r="4"
                            fill="white"
                            stroke={changeColor}
                            strokeWidth="2.2"
                        />
                    ))}
                    <g transform={`translate(${activeTrendChart.latestBadge.x} ${activeTrendChart.latestBadge.y})`}>
                        <rect
                            width={activeTrendChart.latestBadge.width}
                            height={activeTrendChart.latestBadge.height}
                            rx="10"
                            fill="rgba(15, 23, 42, 0.72)"
                            stroke="rgba(255, 255, 255, 0.22)"
                        />
                        <text
                            x={activeTrendChart.latestBadge.width / 2}
                            y="16"
                            textAnchor="middle"
                            fill="#ffffff"
                            fontSize="11"
                            fontWeight="800"
                        >
                            最新 {formatNumber(activeTrendChart.lastPoint.value)}
                        </text>
                    </g>
                </svg>
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: `repeat(${activeTrendChart.labels.length}, minmax(0, 1fr))`,
                        gap: 8,
                        marginTop: 6,
                    }}
                >
                    {activeTrendChart.labels.map((item, index) => (
                        <span
                            key={`${displaySymbol}-${item.label}-${item.value}`}
                            style={{
                                minWidth: 0,
                                textAlign: index === 0 ? 'left' : index === activeTrendChart.labels.length - 1 ? 'right' : 'center',
                                display: 'grid',
                                gap: 2,
                            }}
                        >
                            <span style={{ fontSize: 10, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {trendUsesIntraday ? formatCompactTimestamp(item.label) : item.label}
                            </span>
                            <strong style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.2 }}>
                                {formatNumber(item.value)}
                            </strong>
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
                    {renderMetricCard('买一 / 卖一', orderBookPairValue, effectiveOrderBook.subtle, '#ffe58f')}
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
);

export default SnapshotPanel;
