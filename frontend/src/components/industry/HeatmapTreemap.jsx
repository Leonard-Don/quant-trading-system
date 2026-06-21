/**
 * Squarified-treemap canvas for IndustryHeatmap (layer 2 split).
 *
 * Pure render — no data fetching, no view state of its own. The parent stays
 * the orchestrator that owns all state, AbortControllers and the network
 * lifecycle; this child only takes the already-computed data + view selectors +
 * color/format helpers and renders the tile grid (or the appropriate empty
 * state). The whole body is the verbatim move of the parent's `renderTreemap`
 * useMemo, so React still re-renders it only when these props change.
 *
 * Lives in components/industry/ alongside HeatmapLegend / HeatmapStatsBar /
 * HeatmapControls.
 */

import { useMemo } from 'react';
import { Empty, Tooltip, Typography, Tag, Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

import { lookupPolicyOverlay } from '../../utils/industryPolicyOverlay';
import { activateOnEnterOrSpace } from './industryShared';
import {
    HEATMAP_SURFACE,
    TOOLTIP_BG,
    TOOLTIP_PANEL,
    TOOLTIP_PANEL_BORDER,
    TOOLTIP_TEXT,
    TOOLTIP_MUTED,
    TOOLTIP_SUBTLE,
    TOOLTIP_SHADOW,
    HEATMAP_POSITIVE,
    HEATMAP_NEGATIVE,
    HEATMAP_WARNING,
    TILE_TEXT_SHADOW,
} from '../../utils/industryHeatmapTokens';
import { matchesIndustrySearch, syncHeatmapTileFocusState } from '../../utils/industrySearch';
import { squarify } from '../../utils/squarifiedTreemap';

const { Text } = Typography;

const HeatmapTreemap = ({
    data,
    containerSize,
    setContainerNode,
    loadData,
    sizeMetric,
    colorMetric,
    marketCapFilter,
    matchesMarketCapFilter,
    searchTerm,
    setSearchTerm,
    onSearchTermChange,
    displayCount,
    effectiveLegendRange,
    legendRangeValue,
    onLegendRangeChange,
    onClearMarketCapFilter,
    onSelectMarketCapFilter,
    onIndustryClick,
    onLeadingStockClick,
    getColor,
    getMarketCapDisplayKind,
    getVolatilitySourceMeta,
    formatBillion,
    policyOverlayMap,
    policyColorMode,
}) => {
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

                    const baseBgColor = getColor(displayValue, colorMetric, maxAbsChange);

                    const policyEntry = policyOverlayMap
                        ? lookupPolicyOverlay(item.name, policyOverlayMap)
                        : null;
                    const policyBadge = policyEntry && policyEntry.signal !== 'neutral'
                        ? policyEntry.signal === 'bullish'
                            ? { glyph: '▲', color: HEATMAP_POSITIVE, label: '政策利好' }
                            : { glyph: '▼', color: HEATMAP_NEGATIVE, label: '政策利空' }
                        : null;

                    // 政策色彩覆盖模式：用 policy_signal 接管 tile 背景色。
                    // 默认温度着色不变，只是 ON 时被 override。无数据的行业回退到中性灰，
                    // 保证视觉一致（不退化成默认温度色，避免用户误以为没切换成功）。
                    let bgColor = baseBgColor;
                    if (policyColorMode) {
                        if (!policyEntry || policyEntry.signal === 'neutral') {
                            bgColor = '#6b7280'; // neutral gray
                        } else if (policyEntry.signal === 'bullish') {
                            bgColor = 'rgb(60, 140, 80)';
                        } else if (policyEntry.signal === 'bearish') {
                            bgColor = 'rgb(200, 60, 60)';
                        }
                    }

                    const isLargeBlock = layout.width > 90 && layout.height > 70;
                    const isMediumBlock = layout.width > 55 && layout.height > 40;
                    const isSmallBlock = layout.width > 35 && layout.height > 22;
                    const canShowValue = layout.width > 68 && layout.height > 48;
                    const showMediumMeta = isMediumBlock && !isLargeBlock && layout.width > 82 && layout.height > 60;

                    // 箭头方向逻辑：应与当前显示的数值 displayValue 保持一致
                    // 换手率 (turnover_rate) 始终为正，不显示箭头或显示火号
                    const showArrow = colorMetric !== 'turnover_rate';
                    const arrowIcon = displayValue >= 0 ? '↑' : '↓';
                    const arrowColor = displayValue >= 0 ? '#b7eb8f' : '#ff9c9c';
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
                                            <Tag color={item.value >= 0 ? 'success' : 'error'} style={{ margin: 0, border: 'none', fontWeight: 700 }}>
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
                                                            cursor: onLeadingStockClick && item.leadingStockSymbol ? 'pointer' : 'default',
                                                                textDecoration: onLeadingStockClick && item.leadingStockSymbol ? 'underline' : 'none',
                                                                textDecorationStyle: 'dotted',
                                                                textUnderlineOffset: 2,
                                                            }}
                                                            role={onLeadingStockClick && item.leadingStockSymbol ? 'button' : undefined}
                                                            tabIndex={onLeadingStockClick && item.leadingStockSymbol ? 0 : undefined}
                                                            aria-label={onLeadingStockClick && item.leadingStockSymbol ? `查看龙头股 ${item.leadingStock} 详情` : undefined}
                                                            onClick={(e) => {
                                                                if (onLeadingStockClick && item.leadingStockSymbol) {
                                                                    e.stopPropagation();
                                                                    onLeadingStockClick({
                                                                        name: item.leadingStock,
                                                                        symbol: item.leadingStockSymbol,
                                                                    });
                                                                }
                                                            }}
                                                            onKeyDown={(event) => {
                                                                if (!onLeadingStockClick || !item.leadingStockSymbol) return;
                                                                activateOnEnterOrSpace(event, () => onLeadingStockClick({
                                                                    name: item.leadingStock,
                                                                    symbol: item.leadingStockSymbol,
                                                                }));
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
                                {policyBadge && (
                                    <Tooltip
                                        title={`${policyBadge.label}（${policyEntry.mentions || 0} 个事件，影响 ${(policyEntry.avgImpact ?? 0).toFixed(2)}）`}
                                    >
                                        <div
                                            className="heatmap-policy-badge"
                                            data-testid={`heatmap-policy-badge-${item.name}`}
                                            style={{
                                                position: 'absolute',
                                                top: 4,
                                                left: 4,
                                                zIndex: 6,
                                                color: policyBadge.color,
                                                fontSize: layout.width > 90 ? 12 : 10,
                                                lineHeight: 1,
                                                pointerEvents: 'auto',
                                                textShadow: '0 1px 2px rgba(15, 23, 42, 0.7)',
                                            }}
                                            aria-label={policyBadge.label}
                                        >
                                            {policyBadge.glyph}
                                        </div>
                                    </Tooltip>
                                )}
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
                                {(layout.width > 30 && layout.height > 26) && (
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
                                                    if (onLeadingStockClick && item.leadingStockSymbol) {
                                                        event.stopPropagation();
                                                        onLeadingStockClick({
                                                            name: item.leadingStock,
                                                            symbol: item.leadingStockSymbol,
                                                        });
                                                    }
                                                }}
                                                role={onLeadingStockClick && item.leadingStockSymbol ? 'button' : undefined}
                                                tabIndex={onLeadingStockClick && item.leadingStockSymbol ? 0 : undefined}
                                                aria-label={onLeadingStockClick && item.leadingStockSymbol ? `查看 ${item.name} 龙头股 ${item.leadingStock}` : undefined}
                                                onKeyDown={(event) => {
                                                    if (!onLeadingStockClick || !item.leadingStockSymbol) return;
                                                    activateOnEnterOrSpace(event, () => onLeadingStockClick({
                                                        name: item.leadingStock,
                                                        symbol: item.leadingStockSymbol,
                                                    }));
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
                                                    cursor: onLeadingStockClick && item.leadingStockSymbol ? 'pointer' : 'default',
                                                    overflow: 'hidden',
                                                    minWidth: 0,
                                                }}
                                            >
                                                <span style={{
                                                    color: textColor,
                                                    fontSize: 10,
                                                    opacity: 0.86,
                                                    whiteSpace: 'nowrap',
                                                    flexShrink: 0,
                                                }}>
                                                    龙头
                                                </span>
                                                <span
                                                    data-testid="heatmap-leader-name"
                                                    style={{
                                                    color: textColor,
                                                    fontSize: 11,
                                                    fontWeight: 700,
                                                    whiteSpace: 'nowrap',
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis',
                                                    textShadow: TILE_TEXT_SHADOW,
                                                    minWidth: '0px',
                                                    maxWidth: '100%',
                                                    flexShrink: 1,
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
                                                maxWidth: '100%',
                                                whiteSpace: 'nowrap',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
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
        policyOverlayMap,
        policyColorMode,
        formatBillion,
        setContainerNode,
        setSearchTerm,
    ]);

    return renderTreemap;
};

export default HeatmapTreemap;
