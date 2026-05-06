/**
 * Presentational stats strip above the heatmap (layer 2 split).
 *
 * Reads `data.industries` to compute up/down/flat counts, market
 * breadth, market sentiment, and the top-3 net-inflow tags. Wrapped
 * with React.memo so the (relatively expensive) aggregation only re-runs
 * when the parent passes a new `data` reference — same caching the
 * inline `useMemo` provided.
 */

import React from 'react';
import { Col, Progress, Row, Statistic, Tag } from 'antd';
import { RiseOutlined, FallOutlined, DashboardOutlined } from '@ant-design/icons';

import {
    HEATMAP_POSITIVE,
    HEATMAP_NEGATIVE,
    HEATMAP_WARNING,
} from '../../utils/industryHeatmapTokens';
import { activateOnEnterOrSpace } from './industryShared';

const SENTIMENT_BULLISH = {
    label: '偏多',
    color: HEATMAP_POSITIVE,
    bg: 'color-mix(in srgb, var(--accent-danger) 12%, var(--bg-secondary) 88%)',
};
const SENTIMENT_BEARISH = {
    label: '偏空',
    color: HEATMAP_NEGATIVE,
    bg: 'color-mix(in srgb, var(--accent-success) 12%, var(--bg-secondary) 88%)',
};
const SENTIMENT_NEUTRAL = {
    label: '中性',
    color: HEATMAP_WARNING,
    bg: 'color-mix(in srgb, var(--accent-warning) 12%, var(--bg-secondary) 88%)',
};

const classifySentiment = (upRatio) => {
    if (upRatio > 0.6) return SENTIMENT_BULLISH;
    if (upRatio < 0.4) return SENTIMENT_BEARISH;
    return SENTIMENT_NEUTRAL;
};

const HeatmapStatsBar = ({ data, onIndustryClick }) => {
    const industries = Array.isArray(data?.industries) ? data.industries : null;
    if (!industries) return null;

    const total = industries.length;
    const upCount = industries.filter((row) => row.value > 0).length;
    const downCount = industries.filter((row) => row.value < 0).length;
    const flatCount = industries.filter((row) => row.value === 0).length;
    const upRatio = total > 0 ? upCount / total : 0;
    const upPercent = Math.round(upRatio * 100);
    const sentiment = classifySentiment(upRatio);

    const top3Inflow = [...industries]
        .filter((row) => (row.moneyFlow || 0) > 0)
        .sort((a, b) => (b.moneyFlow || 0) - (a.moneyFlow || 0))
        .slice(0, 3);

    const updateTimeLabel = data?.update_time
        ? new Date(data.update_time).toLocaleTimeString('zh-CN', { hour12: false })
        : '-';

    return (
        <div style={{ marginBottom: 16 }}>
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

                <Col flex="1" style={{ minWidth: 140 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                        市场广度 ({upPercent}%)
                    </div>
                    <Progress
                        percent={upPercent}
                        showInfo={false}
                        strokeColor={HEATMAP_POSITIVE}
                        trailColor={HEATMAP_NEGATIVE}
                        size="small"
                    />
                </Col>

                <Col flex="none">
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                        市场情绪
                    </div>
                    <Tag
                        style={{
                            color: sentiment.color,
                            background: sentiment.bg,
                            border: `1px solid ${sentiment.color}`,
                            fontWeight: 'bold',
                            fontSize: 13,
                            padding: '2px 10px',
                        }}
                    >
                        {sentiment.label}
                    </Tag>
                </Col>

                <Col flex="none">
                    <Statistic
                        title="更新时间"
                        value={updateTimeLabel}
                        valueStyle={{ fontSize: 13 }}
                    />
                </Col>
            </Row>

            {top3Inflow.length > 0 && (
                <div
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '6px 10px',
                        background: 'color-mix(in srgb, var(--accent-danger) 10%, var(--bg-secondary) 90%)',
                        borderRadius: 6,
                        border: '1px solid color-mix(in srgb, var(--accent-danger) 22%, var(--border-color) 78%)',
                        flexWrap: 'wrap',
                    }}
                >
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        💰 主力净流入
                    </span>
                    {top3Inflow.map((industry, index) => (
                        <Tag
                            key={industry.name}
                            color={index === 0 ? 'red' : index === 1 ? 'volcano' : 'orange'}
                            style={{ cursor: 'pointer', margin: 0 }}
                            onClick={() => onIndustryClick?.(industry.name)}
                            role="button"
                            tabIndex={0}
                            aria-label={`查看 ${industry.name} 行业详情，主力净流入 ${(industry.moneyFlow / 1e8).toFixed(1)} 亿`}
                            onKeyDown={(event) => activateOnEnterOrSpace(
                                event,
                                () => onIndustryClick?.(industry.name),
                            )}
                        >
                            {industry.name} +{(industry.moneyFlow / 1e8).toFixed(1)}亿
                        </Tag>
                    ))}
                </div>
            )}
        </div>
    );
};

// Memoize so the aggregation re-runs only when `data` changes —
// equivalent to the `useMemo([data, onIndustryClick])` the inline
// renderer used.
export default React.memo(HeatmapStatsBar);
