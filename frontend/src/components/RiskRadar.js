import React, { useMemo } from 'react';
import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';

import { buildRiskRadarData, formatChartPercent } from '../utils/backtestCharts';

const RadarTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;
  const formattedRaw = point?.suffix === '%'
    ? formatChartPercent(point?.rawValue || 0, 2)
    : Number(point?.rawValue || 0).toFixed(2);

  return (
    <div className="backtest-chart-tooltip">
      <div className="backtest-chart-tooltip__title">{point?.metric}</div>
      <div className="backtest-chart-tooltip__list">
        <div className="backtest-chart-tooltip__row">
          <span className="backtest-chart-tooltip__label">
            <span className="backtest-chart-tooltip__dot" style={{ background: '#38bdf8' }} />
            归一化评分
          </span>
          <span className="backtest-chart-tooltip__value">{Number(point?.score || 0).toFixed(0)}</span>
        </div>
        <div className="backtest-chart-tooltip__row">
          <span className="backtest-chart-tooltip__label">原始指标</span>
          <span className="backtest-chart-tooltip__value">{formattedRaw}</span>
        </div>
      </div>
    </div>
  );
};

const RiskRadar = ({ metrics }) => {
  const radarData = useMemo(() => buildRiskRadarData(metrics), [metrics]);

  if (radarData.length === 0) {
    return <div className="backtest-chart-empty">暂无足够指标生成风险雷达。</div>;
  }

  return (
    <div className="backtest-chart-stack">
      <div className="backtest-chart-shell">
        <div className="backtest-chart-shell__header">
          <div>
            <div className="backtest-chart-shell__title">风险画像雷达</div>
            <div className="backtest-chart-shell__subtitle">
              把收益效率、风险调整、回撤控制和盈亏结构收拢到同一张画像里。
            </div>
          </div>
        </div>

        <div className="backtest-chart-grid">
          <div className="backtest-chart-canvas">
            <ResponsiveContainer width="100%" height={320}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="rgba(148, 163, 184, 0.18)" />
                <PolarAngleAxis dataKey="metric" tick={{ fill: 'rgba(241, 245, 249, 0.9)', fontSize: 11 }} />
                <PolarRadiusAxis
                  angle={24}
                  domain={[0, 100]}
                  tick={{ fill: 'rgba(148, 163, 184, 0.75)', fontSize: 10 }}
                  axisLine={false}
                />
                <Radar
                  name="策略画像"
                  dataKey="score"
                  stroke="#38bdf8"
                  fill="#38bdf8"
                  fillOpacity={0.32}
                  strokeWidth={2.4}
                />
                <Legend />
                <Tooltip content={<RadarTooltip />} />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          <div className="backtest-chart-sidepanel">
            {radarData.map((item) => {
              const rawValue = item.suffix === '%' ? formatChartPercent(item.rawValue, 2) : Number(item.rawValue || 0).toFixed(2);
              return (
                <div key={item.metric} className="backtest-chart-sidepanel__item">
                  <div className="backtest-chart-sidepanel__topline">
                    <span>{item.metric}</span>
                    <span>{Number(item.score).toFixed(0)}</span>
                  </div>
                  <div className="backtest-chart-sidepanel__bar">
                    <span style={{ width: `${item.score}%` }} />
                  </div>
                  <div className="backtest-chart-sidepanel__meta">原始值 {rawValue}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiskRadar;
