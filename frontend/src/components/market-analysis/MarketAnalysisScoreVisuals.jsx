/**
 * Score / recommendation / radar visuals for the MarketAnalysis overview
 * tab (layer 2 split). Three independently-usable subcomponents that
 * each take a small data payload, no React state, no closure
 * dependencies on the host component.
 */

import React from 'react';
import { Progress, Tag } from 'antd';
import {
    PolarAngleAxis,
    PolarGrid,
    PolarRadiusAxis,
    Radar,
    RadarChart,
    ResponsiveContainer,
    Tooltip as RechartsTooltip,
} from 'recharts';

const SCORE_BANDS = [
    { min: 75, color: '#00b578' },
    { min: 50, color: '#1890ff' },
    { min: 30, color: '#faad14' },
    { min: 0, color: '#ff3030' },
];

const colorForScore = (score) => {
    // Guard against null/undefined explicitly — Number(null) === 0, which
    // would otherwise classify "no score" as the lowest red band.
    if (score === null || score === undefined) return '#1890ff';
    const numeric = Number(score);
    if (!Number.isFinite(numeric)) return '#1890ff';
    const band = SCORE_BANDS.find((entry) => numeric >= entry.min);
    return band?.color || '#1890ff';
};

const RECOMMENDATION_COLORS = [
    { match: '买入', color: 'success' },
    { match: '卖出', color: 'error' },
    { match: '持有', color: 'warning' },
];

const colorForRecommendation = (rec) => {
    const text = String(rec || '');
    return RECOMMENDATION_COLORS.find((entry) => text.includes(entry.match))?.color || 'default';
};

export const ScoreGauge = ({ score }) => {
    const color = colorForScore(score);
    return (
        <div style={{ textAlign: 'center' }}>
            <Progress
                type="dashboard"
                percent={score}
                format={(percent) => (
                    <>
                        <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{percent}</div>
                        <div style={{ fontSize: '12px', color: '#888' }}>综合评分</div>
                    </>
                )}
                strokeColor={color}
                size={180}
            />
        </div>
    );
};

export const RecommendationTag = ({ recommendation }) => (
    <Tag color={colorForRecommendation(recommendation)} style={{ fontSize: '16px', padding: '5px 10px' }}>
        {recommendation}
    </Tag>
);

const RADAR_AXES = [
    { key: 'trend', subject: '趋势' },
    { key: 'volume', subject: '量价' },
    { key: 'sentiment', subject: '情绪' },
    { key: 'technical', subject: '技术' },
];

export const ScoreRadarChart = ({ scores }) => {
    const chartData = RADAR_AXES.map(({ key, subject }) => ({
        subject,
        A: scores?.[key] ?? 0,
        fullMark: 100,
    }));

    return (
        <div className="radar-chart-container">
            <ResponsiveContainer width="100%" height={240}>
                <RadarChart cx="50%" cy="50%" outerRadius="70%" data={chartData}>
                    <defs>
                        <linearGradient id="radarFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#2db7f5" stopOpacity={0.8} />
                            <stop offset="95%" stopColor="#00b578" stopOpacity={0.4} />
                        </linearGradient>
                    </defs>
                    <PolarGrid gridType="circle" stroke="rgba(148, 163, 184, 0.2)" />
                    <PolarAngleAxis
                        dataKey="subject"
                        tick={{ fill: 'var(--text-secondary)', fontSize: 13, fontWeight: 500 }}
                    />
                    <PolarRadiusAxis
                        angle={30}
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: '#94a3b8' }}
                        axisLine={false}
                        tickCount={6}
                    />
                    <Radar
                        name="综合评分"
                        dataKey="A"
                        stroke="#2db7f5"
                        strokeWidth={2.5}
                        fill="url(#radarFill)"
                        fillOpacity={0.8}
                        activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }}
                    />
                    <RechartsTooltip
                        contentStyle={{
                            backgroundColor: 'rgba(255, 255, 255, 0.9)',
                            borderRadius: '8px',
                            border: 'none',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                        }}
                        itemStyle={{ color: '#333', fontWeight: 500 }}
                        formatter={(value) => [`${value}分`, '得分']}
                    />
                </RadarChart>
            </ResponsiveContainer>
        </div>
    );
};

// Test surface: expose the resolvers so the band classification can be
// asserted without rendering the full Progress / Tag.
export const __TEST_ONLY__ = {
    colorForScore,
    colorForRecommendation,
};
