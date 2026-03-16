import React, { useMemo } from 'react';
import { Card, Tooltip } from 'antd';
import moment from 'moment';

const MonthlyHeatmap = ({ data }) => {
    // data: array of { date, returns } (daily returns)

    const monthlyReturns = useMemo(() => {
        if (!data || data.length === 0) return {};

        const returnsByYearMonth = {};

        data.forEach(item => {
            const date = moment(item.date);
            const year = date.year();
            const month = date.month(); // 0-11

            if (!returnsByYearMonth[year]) {
                returnsByYearMonth[year] = Array(12).fill(0);
            }

            // Aggregate returns: (1+r1)*(1+r2)... - 1
            // We need to parse 'returns' properly. Assuming item.returns is simple float.
            const dailyRet = parseFloat(item.returns) || 0;

            // Simple compounding 
            // Current val = Previous val * (1 + dailyRet)
            // We initialize with 1.0 (base)
            if (returnsByYearMonth[year][month] === 0) returnsByYearMonth[year][month] = 1.0;

            returnsByYearMonth[year][month] *= (1 + dailyRet);
        });

        // Convert accumulators back to percentage return
        Object.keys(returnsByYearMonth).forEach(year => {
            for (let m = 0; m < 12; m++) {
                if (returnsByYearMonth[year][m] !== 0) {
                    returnsByYearMonth[year][m] = (returnsByYearMonth[year][m] - 1);
                } else {
                    returnsByYearMonth[year][m] = null; // No data for this month
                }
            }
        });

        return returnsByYearMonth;
    }, [data]);

    const years = Object.keys(monthlyReturns).sort((a, b) => b - a);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    const getColor = (value) => {
        if (value === null) return '#f0f0f0'; // No data
        if (value === 0) return '#ffffff';

        // Green for positive, Red for negative
        const intensity = Math.min(Math.abs(value) * 5, 1); // Scale intensity
        if (value > 0) {
            return `rgba(34, 197, 94, ${0.1 + intensity * 0.9})`; // green-500 equivalent
        } else {
            return `rgba(239, 68, 68, ${0.1 + intensity * 0.9})`; // red-500 equivalent
        }
    };

    return (
        <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                    <tr>
                        <th style={{ padding: 8, textAlign: 'left', color: '#666' }}>Year</th>
                        {months.map(m => (
                            <th key={m} style={{ padding: 8, textAlign: 'center', color: '#666' }}>{m}</th>
                        ))}
                        <th style={{ padding: 8, textAlign: 'center', fontWeight: 'bold' }}>Total</th>
                    </tr>
                </thead>
                <tbody>
                    {years.map(year => {
                        const yearData = monthlyReturns[year];
                        // Calculate year total
                        const yearTotal = yearData.reduce((acc, val) => {
                            if (val === null) return acc;
                            return acc * (1 + val);
                        }, 1.0) - 1;

                        return (
                            <tr key={year} style={{ borderTop: '1px solid #f0f0f0' }}>
                                <td style={{ padding: 8, fontWeight: 'bold' }}>{year}</td>
                                {yearData.map((val, idx) => (
                                    <td key={idx} style={{ padding: 2 }}>
                                        <Tooltip title={val !== null ? `${(val * 100).toFixed(2)}%` : '无数据'}>
                                            <div style={{
                                                height: 30,
                                                backgroundColor: getColor(val),
                                                borderRadius: 4,
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                color: val && Math.abs(val) > 0.1 ? '#fff' : '#333'
                                            }}>
                                                {val !== null ? (val * 100).toFixed(1) : '-'}
                                            </div>
                                        </Tooltip>
                                    </td>
                                ))}
                                <td style={{ padding: 8, textAlign: 'center', fontWeight: 'bold', color: yearTotal >= 0 ? 'green' : 'red' }}>
                                    {(yearTotal * 100).toFixed(2)}%
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

export default MonthlyHeatmap;
