import React, { useMemo } from 'react';
import {
    RadarChart,
    Radar,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
    ResponsiveContainer,
    Legend,
    Tooltip
} from 'recharts';

const RiskRadar = ({ metrics }) => {
    const riskRadarData = useMemo(() => {
        if (!metrics) return [];
        return [
            { metric: '夏普比率', value: Math.min(100, Math.max(0, ((metrics.sharpe_ratio || 0) + 1) * 33)), fullMark: 100 },
            { metric: '胜率', value: (metrics.win_rate || 0) * 100, fullMark: 100 },
            { metric: '收益率', value: Math.min(100, Math.max(0, (metrics.total_return || 0) + 50)), fullMark: 100 },
            { metric: '风险控制', value: Math.min(100, Math.max(0, 100 + (metrics.max_drawdown || 0))), fullMark: 100 },
            { metric: '稳定性', value: Math.min(100, Math.max(0, 100 - (metrics.volatility || 0) * 100)), fullMark: 100 },
            { metric: '盈亏比', value: Math.min(100, Math.max(0, (metrics.profit_factor || 1) * 33)), fullMark: 100 },
        ];
    }, [metrics]);

    if (!metrics) return null;

    return (
        <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
                <RadarChart data={riskRadarData}>
                    <PolarGrid stroke="#e8e8e8" />
                    <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
                    <Radar
                        name="风险指标"
                        dataKey="value"
                        stroke="#1890ff"
                        fill="#1890ff"
                        fillOpacity={0.4}
                    />
                    <Legend />
                    <Tooltip />
                </RadarChart>
            </ResponsiveContainer>
        </div>
    );
};

export default RiskRadar;
