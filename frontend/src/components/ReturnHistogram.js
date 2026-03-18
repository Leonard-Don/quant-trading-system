import React, { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { buildReturnDistribution, formatChartPercent } from '../utils/backtestCharts';

const getBarColor = (center) => {
  const intensity = Math.min(Math.abs(center) / 2.8, 1);
  if (center >= 0) {
    return `rgba(16, 185, 129, ${0.28 + intensity * 0.72})`;
  }
  return `rgba(239, 68, 68, ${0.28 + intensity * 0.72})`;
};

const HistogramTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;
  return (
    <div className="backtest-chart-tooltip">
      <div className="backtest-chart-tooltip__title">
        日收益区间 {point?.rangeStart?.toFixed(2)}% ~ {point?.rangeEnd?.toFixed(2)}%
      </div>
      <div className="backtest-chart-tooltip__list">
        <div className="backtest-chart-tooltip__row">
          <span className="backtest-chart-tooltip__label">
            <span className="backtest-chart-tooltip__dot" style={{ background: getBarColor(point?.center || 0) }} />
            样本占比
          </span>
          <span className="backtest-chart-tooltip__value">{formatChartPercent(point?.percentage || 0, 1)}</span>
        </div>
        <div className="backtest-chart-tooltip__row">
          <span className="backtest-chart-tooltip__label">交易日数量</span>
          <span className="backtest-chart-tooltip__value">{point?.count || 0}</span>
        </div>
      </div>
    </div>
  );
};

const ReturnHistogram = ({ data }) => {
  const { bins, stats } = useMemo(() => buildReturnDistribution(data), [data]);

  if (bins.length === 0 || !stats) {
    return <div className="backtest-chart-empty">暂无足够数据生成收益分布。</div>;
  }

  const summary = [
    { label: '上涨日', value: `${stats.positiveDays} 天` },
    { label: '下跌日', value: `${stats.negativeDays} 天` },
    { label: '平均日收益', value: formatChartPercent(stats.avgReturn, 2) },
    { label: '中位日收益', value: formatChartPercent(stats.medianReturn, 2) },
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
            <div className="backtest-chart-shell__title">收益分布直方图</div>
            <div className="backtest-chart-shell__subtitle">
              看日收益在不同区间的密度分布，快速判断尾部风险和收益的偏态。
            </div>
          </div>
        </div>

        <div className="backtest-chart-canvas">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={bins} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="rgba(148, 163, 184, 0.12)" strokeDasharray="4 4" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fill: 'rgba(148, 163, 184, 0.85)', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                angle={-30}
                textAnchor="end"
                height={54}
                interval={0}
              />
              <YAxis
                tick={{ fill: 'rgba(148, 163, 184, 0.85)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => `${value.toFixed(0)}%`}
              />
              <Tooltip content={<HistogramTooltip />} />
              <ReferenceLine
                y={0}
                stroke="rgba(148, 163, 184, 0.25)"
              />
              <ReferenceLine
                x={bins.reduce((closest, bin) => (
                  Math.abs(bin.center - stats.avgReturn) < Math.abs(closest.center - stats.avgReturn) ? bin : closest
                ), bins[0]).label}
                stroke="rgba(56, 189, 248, 0.7)"
                strokeDasharray="5 5"
                label={{ value: '均值', fill: '#7dd3fc', fontSize: 11, position: 'insideTopRight' }}
              />
              <Bar dataKey="percentage" radius={[8, 8, 0, 0]}>
                {bins.map((entry) => (
                  <Cell key={entry.key} fill={getBarColor(entry.center)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default ReturnHistogram;
