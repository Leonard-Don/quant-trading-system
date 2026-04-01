import React, { useMemo } from 'react';
import { Tooltip } from 'antd';
import dayjs from '../utils/dayjs';

const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

const toNumber = (value) => {
    if (value === null || value === undefined || value === '') {
        return null;
    }

    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : null;
};

const parsePointDate = (item) => {
    const rawDate = item?.date || item?.Date || item?.index || item?.timestamp;
    if (!rawDate || (typeof rawDate === 'string' && rawDate.startsWith('point-'))) {
        return null;
    }

    const parsed = typeof rawDate === 'string' ? dayjs(rawDate) : dayjs(rawDate);
    return parsed.isValid() ? parsed : null;
};

const getMonthlyReturnFromTotals = (points, previousPoint) => {
    const validTotals = points
        .map((point) => toNumber(point.total ?? point.portfolio_value))
        .filter((value) => value !== null && value > 0);

    if (validTotals.length === 0) {
        return null;
    }

    const previousTotal = toNumber(previousPoint?.total ?? previousPoint?.portfolio_value);
    const startBase = previousTotal && previousTotal > 0 ? previousTotal : validTotals[0];
    const endTotal = validTotals[validTotals.length - 1];

    if (!startBase || startBase <= 0) {
        return null;
    }

    return (endTotal / startBase) - 1;
};

const getMonthlyReturnFromDailyReturns = (points) => {
    const dailyReturns = points
        .map((point) => toNumber(point.returns))
        .filter((value) => value !== null);

    if (dailyReturns.length === 0) {
        return null;
    }

    return dailyReturns.reduce((accumulator, value) => accumulator * (1 + value), 1) - 1;
};

export const buildMonthlyReturnTable = (data = []) => {
    if (!Array.isArray(data) || data.length === 0) {
        return {};
    }

    const points = data
        .map((item) => ({
            ...item,
            __parsedDate: parsePointDate(item),
        }))
        .filter((item) => item.__parsedDate)
        .sort((left, right) => left.__parsedDate.valueOf() - right.__parsedDate.valueOf());

    if (points.length === 0) {
        return {};
    }

    const monthlyTable = {};
    let cursor = 0;
    while (cursor < points.length) {
        const currentPoint = points[cursor];
        const year = currentPoint.__parsedDate.year();
        const month = currentPoint.__parsedDate.month();
        const previousPoint = cursor > 0 ? points[cursor - 1] : null;

        const monthPoints = [];
        while (
            cursor < points.length &&
            points[cursor].__parsedDate.year() === year &&
            points[cursor].__parsedDate.month() === month
        ) {
            monthPoints.push(points[cursor]);
            cursor += 1;
        }

        const monthlyReturn = getMonthlyReturnFromTotals(monthPoints, previousPoint);
        const fallbackReturn = monthlyReturn === null ? getMonthlyReturnFromDailyReturns(monthPoints) : monthlyReturn;

        if (!monthlyTable[year]) {
            monthlyTable[year] = Array(12).fill(null);
        }

        monthlyTable[year][month] = fallbackReturn;
    }

    return monthlyTable;
};

const MonthlyHeatmap = ({ data }) => {
    const monthlyReturns = useMemo(() => {
        return buildMonthlyReturnTable(data);
    }, [data]);

    const years = Object.keys(monthlyReturns).sort((a, b) => b - a);

    const summary = useMemo(() => {
        const allValues = years.flatMap((year) => monthlyReturns[year].filter((value) => value !== null));
        if (allValues.length === 0) {
            return [];
        }

        return [
            {
                label: '覆盖月份',
                value: `${allValues.length} 个月`,
            },
            {
                label: '最佳单月',
                value: `${(Math.max(...allValues) * 100).toFixed(2)}%`,
            },
            {
                label: '最差单月',
                value: `${(Math.min(...allValues) * 100).toFixed(2)}%`,
            },
            {
                label: '月均收益',
                value: `${((allValues.reduce((sum, value) => sum + value, 0) / allValues.length) * 100).toFixed(2)}%`,
            },
        ];
    }, [monthlyReturns, years]);

    const getColor = (value) => {
        if (value === null) return 'rgba(148, 163, 184, 0.14)';
        if (value === 0) return '#ffffff';

        const intensity = Math.min(Math.abs(value) * 4, 1);
        if (value > 0) {
            return `rgba(34, 197, 94, ${0.16 + intensity * 0.84})`;
        } else {
            return `rgba(239, 68, 68, ${0.16 + intensity * 0.84})`;
        }
    };

    if (years.length === 0) {
        return (
            <div className="workspace-empty-state" style={{ minHeight: 180 }}>
                暂无足够的组合净值数据，无法生成月度热力图
            </div>
        );
    }

    return (
        <div className="backtest-chart-stack">
            <div className="summary-strip summary-strip--compact">
                {summary.map((item) => (
                    <div key={item.label} className="summary-strip__item">
                        <span className="summary-strip__label">{item.label}</span>
                        <span className="summary-strip__value">{item.value}</span>
                    </div>
                ))}
            </div>

            <div className="backtest-chart-shell">
                <div className="backtest-chart-shell__header">
                    <div>
                        <div className="backtest-chart-shell__title">月度收益热力图</div>
                        <div className="backtest-chart-shell__subtitle">
                            以组合净值为主、日收益为辅来聚合月度表现，避免旧快照把整月误算成 0。
                        </div>
                    </div>
                </div>

                <div className="backtest-chart-table">
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                        <thead>
                            <tr>
                                <th style={{ padding: 8, textAlign: 'left', color: 'rgba(255,255,255,0.65)' }}>年份</th>
                                {MONTH_LABELS.map((monthLabel) => (
                                    <th key={monthLabel} style={{ padding: 8, textAlign: 'center', color: 'rgba(255,255,255,0.65)' }}>{monthLabel}</th>
                                ))}
                                <th style={{ padding: 8, textAlign: 'center', fontWeight: 'bold', color: 'rgba(255,255,255,0.85)' }}>全年</th>
                            </tr>
                        </thead>
                        <tbody>
                            {years.map(year => {
                                const yearData = monthlyReturns[year];
                                const yearTotal = yearData.reduce((acc, val) => {
                                    if (val === null) return acc;
                                    return acc * (1 + val);
                                }, 1.0) - 1;

                                return (
                                    <tr key={year} style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                                        <td style={{ padding: 8, fontWeight: 'bold', color: 'rgba(255,255,255,0.92)' }}>{year}</td>
                                        {yearData.map((val, idx) => (
                                            <td key={idx} style={{ padding: 2 }}>
                                                <Tooltip title={val !== null ? `${year}年${MONTH_LABELS[idx]}: ${(val * 100).toFixed(2)}%` : `${year}年${MONTH_LABELS[idx]}: 无数据`}>
                                                    <div style={{
                                                        height: 32,
                                                        backgroundColor: getColor(val),
                                                        borderRadius: 10,
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        justifyContent: 'center',
                                                        color: val !== null && Math.abs(val) > 0.08 ? '#fff' : 'rgba(255,255,255,0.88)',
                                                        border: val === null ? '1px dashed rgba(255,255,255,0.08)' : '1px solid rgba(255,255,255,0.06)',
                                                        fontVariantNumeric: 'tabular-nums',
                                                    }}>
                                                        {val !== null ? `${(val * 100).toFixed(1)}%` : '-'}
                                                    </div>
                                                </Tooltip>
                                            </td>
                                        ))}
                                        <td style={{ padding: 8, textAlign: 'center', fontWeight: 'bold', color: yearTotal >= 0 ? 'var(--accent-success)' : 'var(--accent-danger)' }}>
                                            {(yearTotal * 100).toFixed(2)}%
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default MonthlyHeatmap;
