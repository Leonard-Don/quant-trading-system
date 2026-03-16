import React, { useMemo } from 'react';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell
} from 'recharts';

const ReturnHistogram = ({ data }) => {
    // 计算收益分布直方图数据
    const histogramData = useMemo(() => {
        if (!data || data.length === 0) return [];

        const returns = data.map(item => (item.returns || 0) * 100).filter(r => !isNaN(r) && r !== 0);
        if (returns.length === 0) return [];

        const min = Math.min(...returns);
        const max = Math.max(...returns);
        const binCount = 20;
        const binSize = (max - min) / binCount || 1;

        const bins = Array(binCount).fill(0).map((_, i) => ({
            range: `${(min + i * binSize).toFixed(1)}%`,
            rangeStart: min + i * binSize,
            rangeEnd: min + (i + 1) * binSize,
            count: 0,
            percentage: 0
        }));

        returns.forEach(r => {
            const binIndex = Math.min(Math.floor((r - min) / binSize), binCount - 1);
            if (binIndex >= 0 && binIndex < binCount) bins[binIndex].count++;
        });

        bins.forEach(bin => {
            bin.percentage = (bin.count / returns.length * 100);
        });

        return bins;
    }, [data]);

    if (!data || data.length === 0) return null;

    return (
        <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
                <BarChart data={histogramData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="range" tick={{ fontSize: 9 }} angle={-45} textAnchor="end" height={60} />
                    <YAxis tickFormatter={(v) => `${v.toFixed(0)}%`} tick={{ fontSize: 10 }} />
                    <Tooltip
                        formatter={(value, name) => [`${value.toFixed(1)}%`, '占比']}
                        labelFormatter={(label) => `收益区间: ${label}`}
                    />
                    <Bar dataKey="percentage" name="频率 (%)" radius={[4, 4, 0, 0]}>
                        {histogramData.map((entry, index) => (
                            <Cell
                                key={`cell-${index}`}
                                fill={entry.rangeStart >= 0 ? '#52c41a' : '#ff4d4f'}
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
};

export default ReturnHistogram;
