/**
 * Compare-mode panel for RealtimeStockDetailModal (layer 2 split).
 *
 * Pure render — no hooks, no data fetching. Owns the verbatim "对比模式" section
 * (candidate toggle chips + compare-card grid) that previously lived inline in
 * the parent modal body. Receives the parent's already-deduped candidates,
 * sanitized selection, built compare cards, and the toggle / navigate
 * callbacks. The parent stays the orchestrator that owns the selection state;
 * this child only renders it.
 */

import { Tag, Typography, Button } from 'antd';
import { DotChartOutlined } from '@ant-design/icons';
import {
    formatNumber,
    formatSignedNumber,
    formatRangePercent,
    getCompareQuoteStatus,
} from './helpers.jsx';

const { Text } = Typography;

const ComparePanel = ({
    displaySymbol,
    safeCompareCandidates,
    effectiveSelectedCompareSymbols,
    compareCards,
    toggleCompareSymbol,
    onNavigateSymbol,
}) => (
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
            {compareCards.map((item) => {
                const isPrimaryCard = item.symbol === displaySymbol;
                const primaryTextColor = '#f8fafc';
                const secondaryTextColor = isPrimaryCard ? 'rgba(219, 234, 254, 0.88)' : 'rgba(226, 232, 240, 0.76)';
                const compareQuoteStatus = getCompareQuoteStatus(item.quote, isPrimaryCard);
                const statusColors = compareQuoteStatus.tone === 'ready'
                    ? {
                        borderColor: 'rgba(134, 239, 172, 0.24)',
                        background: 'rgba(22, 163, 74, 0.18)',
                        color: '#dcfce7',
                    }
                    : {
                        borderColor: 'rgba(253, 224, 71, 0.22)',
                        background: 'rgba(202, 138, 4, 0.18)',
                        color: '#fef3c7',
                    };

                return (
                <div
                    key={item.symbol}
                    data-testid={`detail-compare-card-${item.symbol}`}
                    style={{
                        padding: 16,
                        borderRadius: 16,
                        border: `1px solid ${isPrimaryCard ? 'rgba(96, 165, 250, 0.44)' : 'rgba(148, 163, 184, 0.18)'}`,
                        background: isPrimaryCard
                            ? 'linear-gradient(180deg, rgba(30, 64, 175, 0.40) 0%, rgba(15, 23, 42, 0.88) 100%)'
                            : 'linear-gradient(180deg, rgba(15, 23, 42, 0.78) 0%, rgba(2, 6, 23, 0.92) 100%)',
                        boxShadow: isPrimaryCard
                            ? '0 16px 30px rgba(37, 99, 235, 0.18)'
                            : '0 12px 24px rgba(2, 6, 23, 0.18)',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start', marginBottom: 10 }}>
                        <div>
                            <div style={{ fontWeight: 800, color: primaryTextColor }}>
                                {item.symbol}
                            </div>
                            <div style={{ fontSize: 12, color: secondaryTextColor, marginTop: 4 }}>
                                {item.name}
                            </div>
                        </div>
                        {isPrimaryCard ? (
                            <Tag color="blue" style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>当前标的</Tag>
                        ) : (
                            onNavigateSymbol ? (
                                <Button
                                    size="small"
                                    type="primary"
                                    onClick={() => onNavigateSymbol(item.symbol)}
                                    aria-label={`切换到 ${item.symbol}`}
                                    data-testid={`detail-compare-switch-${item.symbol}`}
                                    style={{
                                        borderRadius: 999,
                                        borderColor: 'rgba(191, 219, 254, 0.32)',
                                        background: 'rgba(59, 130, 246, 0.18)',
                                        color: '#eff6ff',
                                        fontWeight: 700,
                                    }}
                                >
                                    {`切换到 ${item.symbol}`}
                                </Button>
                            ) : null
                        )}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
                        <Tag
                            style={{
                                margin: 0,
                                borderRadius: 999,
                                paddingInline: 10,
                                border: `1px solid ${statusColors.borderColor}`,
                                background: statusColors.background,
                                color: statusColors.color,
                                fontWeight: 700,
                            }}
                        >
                            {compareQuoteStatus.label}
                        </Tag>
                        <span style={{ fontSize: 11, color: secondaryTextColor }}>
                            {compareQuoteStatus.description}
                        </span>
                    </div>

                    <div style={{ display: 'grid', gap: 8 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                            <span style={{ color: secondaryTextColor }}>最新价</span>
                            <strong style={{ color: primaryTextColor }}>{formatNumber(item.quote?.price)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                            <span style={{ color: secondaryTextColor }}>涨跌幅</span>
                            <strong style={{ color: primaryTextColor }}>{formatSignedNumber(item.quote?.change_percent, 2, '%')}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                            <span style={{ color: secondaryTextColor }}>日内振幅</span>
                            <strong style={{ color: primaryTextColor }}>{formatRangePercent(item.quote?.low, item.quote?.high, item.quote?.previous_close)}</strong>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                            <span style={{ color: secondaryTextColor }}>综合分</span>
                            <strong style={{ color: primaryTextColor }}>{item.signalSummary.totalScore}</strong>
                        </div>
                        <div style={{ fontSize: 12, color: secondaryTextColor }}>
                            {item.signalSummary.conviction} · {item.signalSummary.eventLabel}
                        </div>
                    </div>
                </div>
            )})}
        </div>
    </section>
);

export default ComparePanel;
