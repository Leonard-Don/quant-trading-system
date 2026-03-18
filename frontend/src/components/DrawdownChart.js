import React, { useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { buildDrawdownSeries, formatChartCurrency, formatChartPercent } from '../utils/backtestCharts';

const DrawdownTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;

  return (
    <div className="backtest-chart-tooltip">
      <div className="backtest-chart-tooltip__title">{point?.dateLongLabel}</div>
      <div className="backtest-chart-tooltip__list">
        <div className="backtest-chart-tooltip__row">
          <span className="backtest-chart-tooltip__label">
            <span className="backtest-chart-tooltip__dot" style={{ background: '#ef4444' }} />
            回撤深度
          </span>
          <span className="backtest-chart-tooltip__value">{formatChartPercent(point?.drawdown || 0, 2)}</span>
        </div>
        <div className="backtest-chart-tooltip__row">
          <span className="backtest-chart-tooltip__label">
            <span className="backtest-chart-tooltip__dot" style={{ background: '#38bdf8' }} />
            当日净值
          </span>
          <span className="backtest-chart-tooltip__value">{formatChartCurrency(point?.total || 0)}</span>
        </div>
      </div>
    </div>
  );
};

const DrawdownChart = ({ data }) => {
  const { series, stats } = useMemo(() => buildDrawdownSeries(data), [data]);

  if (series.length === 0 || !stats) {
    return <div className="backtest-chart-empty">暂无足够数据生成回撤曲线。</div>;
  }

  const summary = [
    { label: '最大回撤', value: formatChartPercent(stats.maxDrawdown, 2) },
    { label: '当前回撤', value: formatChartPercent(stats.currentDrawdown, 2) },
    { label: '水下天数', value: `${stats.underwaterDays} 天` },
    { label: '最长恢复期', value: `${stats.longestUnderwaterStreak} 天` },
  ];

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
            <div className="backtest-chart-shell__title">回撤深度曲线</div>
            <div className="backtest-chart-shell__subtitle">
              追踪组合从历史峰值回落的幅度，快速识别最痛苦的回撤区间。
            </div>
          </div>
        </div>
        <div className="backtest-chart-canvas">
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity={0.65} />
                  <stop offset="100%" stopColor="#ef4444" stopOpacity={0.04} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(148, 163, 184, 0.12)" strokeDasharray="4 4" vertical={false} />
              <XAxis
                dataKey="dateLabel"
                tick={{ fill: 'rgba(148, 163, 184, 0.85)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <YAxis
                tick={{ fill: 'rgba(148, 163, 184, 0.85)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => `${value.toFixed(0)}%`}
              />
              <Tooltip content={<DrawdownTooltip />} />
              <Area
                type="monotone"
                dataKey="drawdown"
                stroke="#ef4444"
                strokeWidth={2.2}
                fill="url(#drawdownGradient)"
                fillOpacity={1}
                dot={false}
                activeDot={{ r: 4, stroke: '#fff', strokeWidth: 1.2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default DrawdownChart;
