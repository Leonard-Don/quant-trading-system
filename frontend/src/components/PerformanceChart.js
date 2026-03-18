import React, { useMemo, useState } from 'react';
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Button, Dropdown, Segmented, Space, Tag } from 'antd';
import {
  CheckOutlined,
  FallOutlined,
  RiseOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

import TimeRangeSelector from './common/TimeRangeSelector';
import {
  buildPerformanceChartData,
  formatChartCurrency,
  formatChartPercent,
} from '../utils/backtestCharts';

const palette = {
  portfolio: '#38bdf8',
  price: '#a78bfa',
  sma20: '#f59e0b',
  sma50: '#14b8a6',
  ema12: '#f97316',
  ema26: '#22c55e',
  bollinger: '#fb7185',
  buy: '#10b981',
  sell: '#ef4444',
  axis: 'rgba(148, 163, 184, 0.85)',
  grid: 'rgba(148, 163, 184, 0.12)',
};

const buildAxisDomain = (values = []) => {
  const finiteValues = values.filter((value) => Number.isFinite(value));
  if (finiteValues.length === 0) {
    return [0, 1];
  }

  const min = Math.min(...finiteValues);
  const max = Math.max(...finiteValues);
  const spread = max - min;
  const padding = spread === 0
    ? Math.max(Math.abs(max) * 0.04, 1)
    : Math.max(spread * 0.14, Math.abs(max) * 0.01, 1);

  return [min - padding, max + padding];
};

const SignalMarker = ({ cx, cy, payload }) => {
  if (!Number.isFinite(cx) || !Number.isFinite(cy) || !payload) {
    return null;
  }

  const isBuy = payload.signal === 1;
  const size = 7;
  const path = isBuy
    ? `M ${cx} ${cy - size} L ${cx + size} ${cy + size} L ${cx - size} ${cy + size} Z`
    : `M ${cx} ${cy + size} L ${cx + size} ${cy - size} L ${cx - size} ${cy - size} Z`;

  return (
    <g>
      <path d={path} fill={isBuy ? palette.buy : palette.sell} stroke="rgba(15,23,42,0.9)" strokeWidth={1.2} />
      <circle cx={cx} cy={cy} r={2.5} fill="#fff" opacity={0.9} />
    </g>
  );
};

const PerformanceTooltip = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  const point = payload[0]?.payload;
  const signalLabel = point?.signal === 1 ? '买入信号' : point?.signal === -1 ? '卖出信号' : null;

  return (
    <div className="backtest-chart-tooltip">
      <div className="backtest-chart-tooltip__title">{point?.dateLongLabel || label}</div>
      <div className="backtest-chart-tooltip__list">
        {payload
          .filter((entry) => entry.value !== null && entry.value !== undefined)
          .map((entry) => (
            <div key={entry.dataKey} className="backtest-chart-tooltip__row">
              <span className="backtest-chart-tooltip__label">
                <span className="backtest-chart-tooltip__dot" style={{ background: entry.color }} />
                {entry.name}
              </span>
              <span className="backtest-chart-tooltip__value">
                {entry.dataKey === 'portfolio_value' ? formatChartCurrency(entry.value) : Number(entry.value).toFixed(2)}
              </span>
            </div>
          ))}
      </div>
      {signalLabel ? <Tag color={point.signal === 1 ? 'success' : 'error'}>{signalLabel}</Tag> : null}
    </div>
  );
};

const PerformanceChart = ({ data }) => {
  const [showSignals, setShowSignals] = useState(true);
  const [showPrice, setShowPrice] = useState(true);
  const [showSMA, setShowSMA] = useState(false);
  const [showEMA, setShowEMA] = useState(false);
  const [showBollinger, setShowBollinger] = useState(false);
  const [chartType, setChartType] = useState('area');
  const [timeRange, setTimeRange] = useState('max');

  const chartData = useMemo(() => buildPerformanceChartData(data, timeRange), [data, timeRange]);
  const hasPriceSeries = useMemo(
    () => chartData.some((item) => item.price !== null && !Number.isNaN(item.price)),
    [chartData]
  );
  const buySignals = useMemo(() => chartData.filter((item) => item.signal === 1), [chartData]);
  const sellSignals = useMemo(() => chartData.filter((item) => item.signal === -1), [chartData]);
  const portfolioDomain = useMemo(
    () => buildAxisDomain(chartData.map((item) => item.portfolio_value)),
    [chartData]
  );
  const priceDomain = useMemo(
    () => buildAxisDomain(chartData.map((item) => item.price)),
    [chartData]
  );

  const chartSummary = useMemo(() => {
    if (chartData.length === 0) {
      return [];
    }

    const firstPoint = chartData[0];
    const lastPoint = chartData[chartData.length - 1];
    const delta = firstPoint.portfolio_value > 0
      ? ((lastPoint.portfolio_value / firstPoint.portfolio_value) - 1) * 100
      : 0;

    return [
      {
        label: '最新净值',
        value: formatChartCurrency(lastPoint.portfolio_value),
      },
      {
        label: '区间变化',
        value: formatChartPercent(delta, 2),
      },
      {
        label: '信号数',
        value: `${buySignals.length + sellSignals.length} 个`,
      },
      {
        label: '观察窗口',
        value: `${chartData.length} 个交易日`,
      },
    ];
  }, [buySignals.length, chartData, sellSignals.length]);

  const menuItems = [
    {
      key: 'price',
      label: '显示价格叠层',
      icon: showPrice && hasPriceSeries ? <CheckOutlined /> : null,
      disabled: !hasPriceSeries,
      onClick: () => setShowPrice((value) => !value),
    },
    {
      key: 'sma',
      label: '显示 SMA',
      icon: showSMA && hasPriceSeries ? <CheckOutlined /> : null,
      disabled: !hasPriceSeries,
      onClick: () => setShowSMA((value) => !value),
    },
    {
      key: 'ema',
      label: '显示 EMA',
      icon: showEMA && hasPriceSeries ? <CheckOutlined /> : null,
      disabled: !hasPriceSeries,
      onClick: () => setShowEMA((value) => !value),
    },
    {
      key: 'bollinger',
      label: '显示布林带',
      icon: showBollinger && hasPriceSeries ? <CheckOutlined /> : null,
      disabled: !hasPriceSeries,
      onClick: () => setShowBollinger((value) => !value),
    },
    {
      type: 'divider',
    },
    {
      key: 'signals',
      label: '显示交易信号',
      icon: showSignals ? <CheckOutlined /> : null,
      onClick: () => setShowSignals((value) => !value),
    },
  ];

  if (chartData.length === 0) {
    return <div className="backtest-chart-empty">暂无可用于绘制净值曲线的组合历史数据。</div>;
  }

  return (
    <div className="backtest-chart-stack">
      <div className="summary-strip summary-strip--compact">
        {chartSummary.map((item) => (
          <div key={item.label} className="summary-strip__item">
            <span className="summary-strip__label">{item.label}</span>
            <span className="summary-strip__value">{item.value}</span>
          </div>
        ))}
      </div>

      <div className="backtest-chart-shell">
        <div className="backtest-chart-shell__header">
          <div>
            <div className="backtest-chart-shell__title">组合净值主曲线</div>
            <div className="backtest-chart-shell__subtitle">
              用更清晰的双轴视图查看组合净值、标的价格以及交易信号落点。
            </div>
          </div>
          <Space wrap size="small">
            <TimeRangeSelector value={timeRange} onChange={setTimeRange} size="small" />
            <Segmented
              size="small"
              options={[
                { label: '面积', value: 'area' },
                { label: '折线', value: 'line' },
              ]}
              value={chartType}
              onChange={setChartType}
            />
            <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
              <Button size="small" icon={<SettingOutlined />}>叠层设置</Button>
            </Dropdown>
          </Space>
        </div>

        <div className="backtest-chart-shell__badges">
          <span className="backtest-chart-badge">
            <RiseOutlined /> 买入 {buySignals.length}
          </span>
          <span className="backtest-chart-badge backtest-chart-badge--danger">
            <FallOutlined /> 卖出 {sellSignals.length}
          </span>
          <span className="backtest-chart-badge backtest-chart-badge--accent">
            <ThunderboltOutlined /> {hasPriceSeries ? '含标的价格叠层' : '仅展示组合净值'}
          </span>
        </div>

        <div className="backtest-chart-canvas">
          <ResponsiveContainer width="100%" height={440}>
            <ComposedChart data={chartData} margin={{ top: 12, right: 24, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="portfolioAreaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={palette.portfolio} stopOpacity={0.4} />
                  <stop offset="70%" stopColor={palette.portfolio} stopOpacity={0.12} />
                  <stop offset="100%" stopColor={palette.portfolio} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={palette.grid} strokeDasharray="4 4" vertical={false} />
              <XAxis
                dataKey="dateLabel"
                minTickGap={24}
                tick={{ fill: palette.axis, fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: palette.grid }}
              />
              <YAxis
                yAxisId="left"
                width={78}
                domain={portfolioDomain}
                tick={{ fill: palette.axis, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => formatChartCurrency(value)}
              />
              {showPrice && hasPriceSeries ? (
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  width={68}
                  domain={priceDomain}
                  tick={{ fill: palette.axis, fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value) => `${Number(value).toFixed(0)}`}
                />
              ) : null}
              <Tooltip content={<PerformanceTooltip />} />
              <Legend wrapperStyle={{ paddingTop: 18 }} iconType="circle" />

              {chartType === 'area' ? (
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="portfolio_value"
                  name="组合净值"
                  stroke={palette.portfolio}
                  strokeWidth={2.6}
                  fill="url(#portfolioAreaGradient)"
                  fillOpacity={1}
                  dot={false}
                  activeDot={{ r: 4, stroke: '#fff', strokeWidth: 1.5 }}
                />
              ) : (
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="portfolio_value"
                  name="组合净值"
                  stroke={palette.portfolio}
                  strokeWidth={2.6}
                  dot={false}
                  activeDot={{ r: 4, stroke: '#fff', strokeWidth: 1.5 }}
                />
              )}

              {showPrice && hasPriceSeries ? (
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="price"
                  name="标的价格"
                  stroke={palette.price}
                  strokeWidth={1.7}
                  dot={false}
                />
              ) : null}

              {showSMA && hasPriceSeries ? (
                <>
                  <Line yAxisId="right" type="monotone" dataKey="sma20" name="SMA20" stroke={palette.sma20} strokeWidth={1.2} dot={false} strokeDasharray="4 4" />
                  <Line yAxisId="right" type="monotone" dataKey="sma50" name="SMA50" stroke={palette.sma50} strokeWidth={1.2} dot={false} strokeDasharray="6 6" />
                </>
              ) : null}

              {showEMA && hasPriceSeries ? (
                <>
                  <Line yAxisId="right" type="monotone" dataKey="ema12" name="EMA12" stroke={palette.ema12} strokeWidth={1.2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="ema26" name="EMA26" stroke={palette.ema26} strokeWidth={1.2} dot={false} />
                </>
              ) : null}

              {showBollinger && hasPriceSeries ? (
                <>
                  <Line yAxisId="right" type="monotone" dataKey="bbUpper" name="布林上轨" stroke={palette.bollinger} strokeWidth={1} dot={false} strokeDasharray="3 3" />
                  <Line yAxisId="right" type="monotone" dataKey="bbMiddle" name="布林中轨" stroke="#c084fc" strokeWidth={1} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="bbLower" name="布林下轨" stroke={palette.bollinger} strokeWidth={1} dot={false} strokeDasharray="3 3" />
                </>
              ) : null}

              {showSignals ? (
                <Scatter
                  yAxisId="left"
                  name="交易信号"
                  data={chartData.filter((item) => item.signal !== 0)}
                  dataKey="portfolio_value"
                  shape={(props) => <SignalMarker {...props} />}
                />
              ) : null}

              <Brush
                dataKey="dateLabel"
                height={28}
                stroke="rgba(56,189,248,0.45)"
                travellerWidth={10}
                fill="rgba(15,23,42,0.35)"
                tickFormatter={() => ''}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default PerformanceChart;
