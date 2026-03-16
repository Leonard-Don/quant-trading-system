import React from 'react';
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine
} from 'recharts';
import moment from 'moment';

const DrawdownChart = ({ data }) => {
    if (!data || data.length === 0) return null;

    // Process data to calculate drawdown series if not readily available
    // Assuming 'data' contains { date, total } or { date, drawdown }
    // If only total value is provided, we calculate drawdown here

    const chartData = data.map(item => ({
        date: item.date,
        drawdown: item.drawdown !== undefined ? item.drawdown : 0, // Should be passed from backend or calculated
        value: item.total
    }));

    // If drawdown is not pre-calculated in the passed data, we can calculate it
    // But backend usually provides 'metrics', not timeseries of drawdown.
    // We can calculate it from the 'total' value series.
    let runningMax = -Infinity;
    const processedData = data.map(item => {
        const val = parseFloat(item.total);
        if (val > runningMax) runningMax = val;
        const dd = (val - runningMax) / runningMax;
        return {
            date: new Date(item.date).getTime(), // Timestamp for XAxis
            drawdown: dd * 100, // Convert to percentage
            value: val
        };
    });

    return (
        <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
                <AreaChart data={processedData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <defs>
                        <linearGradient id="colorDrawdown" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8} />
                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0.1} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                    <XAxis
                        dataKey="date"
                        tickFormatter={(tick) => moment(tick).format('MM-DD')}
                        type="number"
                        domain={['dataMin', 'dataMax']}
                        tick={{ fontSize: 11 }}
                    />
                    <YAxis
                        unit="%"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(val) => val.toFixed(1)}
                    />
                    <Tooltip
                        labelFormatter={(label) => moment(label).format('YYYY-MM-DD')}
                        formatter={(value) => [value.toFixed(2) + '%', '回撤']}
                        contentStyle={{ borderRadius: 8, border: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
                    />
                    <Area
                        type="monotone"
                        dataKey="drawdown"
                        stroke="#ef4444"
                        fillOpacity={1}
                        fill="url(#colorDrawdown)"
                    />
                    <ReferenceLine y={0} stroke="#666" strokeDasharray="3 3" />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
};

export default DrawdownChart;
