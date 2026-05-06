/**
 * Presentational legend for IndustryHeatmap (layer 2 split).
 *
 * Pure render — no hooks, no data fetching. Receives the parent's
 * already-computed metric meta + range + top3 banner; emits range
 * changes and tag clicks back through callbacks. Lives in
 * components/industry/ alongside the other heatmap-adjacent
 * subpanels.
 */

import React from 'react';
import { Slider, Tag, Typography } from 'antd';
import { BgColorsOutlined, BarChartOutlined } from '@ant-design/icons';

import { activateOnEnterOrSpace } from './industryShared';

const { Text } = Typography;

const SIZE_METRIC_LABELS = {
    market_cap: '总市值',
    turnover: '当日总成交额',
    net_inflow: '净流入绝对值',
};

const sizeLabel = (sizeMetric) => SIZE_METRIC_LABELS[sizeMetric] || '未知';

const HeatmapLegend = ({
    legendMeta,
    effectiveLegendRange,
    colorMetric,
    sizeMetric,
    onLegendRangeChange,
    top3InflowBanner = [],
    onIndustryClick,
}) => {
    const gradient = colorMetric === 'turnover_rate'
        ? 'linear-gradient(to right, blue, yellow, red)'
        : 'linear-gradient(to right, rgb(20, 180, 40), #6B6B6B, rgb(235, 20, 20))';

    const rangeDigits = colorMetric === 'pe_ttm' ? 0 : 1;

    return (
        <div
            style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginTop: 12,
                gap: 12,
                flexWrap: 'wrap',
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <BgColorsOutlined />
                    <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {legendMeta.leftLabel}
                    </Text>
                    <div
                        style={{
                            width: 120,
                            height: 8,
                            background: gradient,
                            borderRadius: 4,
                        }}
                    />
                    <Text style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {legendMeta.rightLabel}
                    </Text>
                </div>

                <div style={{ minWidth: 280, maxWidth: 380, flex: '1 1 280px' }}>
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 8,
                            marginBottom: 4,
                        }}
                    >
                        <Text style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                            色阶区间刷选
                        </Text>
                        <Text style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                            {effectiveLegendRange[0].toFixed(rangeDigits)}
                            {legendMeta.suffix}
                            {' '}~{' '}
                            {effectiveLegendRange[1].toFixed(rangeDigits)}
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
                        方块大小 = {sizeLabel(sizeMetric)}
                    </Text>
                </div>
            </div>

            {top3InflowBanner.length > 0 && (
                <div
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '4px 10px',
                        background: 'color-mix(in srgb, var(--accent-danger) 10%, var(--bg-secondary) 90%)',
                        borderRadius: 6,
                        border: '1px solid color-mix(in srgb, var(--accent-danger) 24%, var(--border-color) 76%)',
                        flexWrap: 'wrap',
                    }}
                >
                    <span style={{ fontSize: 11, color: 'var(--accent-danger)', whiteSpace: 'nowrap' }}>
                        💰 净流入 TOP
                    </span>
                    {top3InflowBanner.map((industry, index) => (
                        <Tag
                            key={industry.name}
                            color={index === 0 ? 'red' : index === 1 ? 'volcano' : 'orange'}
                            style={{ margin: 0, cursor: 'pointer', fontSize: 11 }}
                            onClick={() => onIndustryClick?.(industry.name)}
                            role="button"
                            tabIndex={0}
                            aria-label={`查看 ${industry.name} 行业详情`}
                            onKeyDown={(event) => activateOnEnterOrSpace(
                                event,
                                () => onIndustryClick?.(industry.name),
                            )}
                        >
                            {industry.name}
                        </Tag>
                    ))}
                </div>
            )}
        </div>
    );
};

export default HeatmapLegend;
