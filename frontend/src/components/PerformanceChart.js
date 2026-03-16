import React, { useState, useMemo } from 'react';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  ReferenceLine,
  Brush,
  Area
} from 'recharts';
import {
  LineChartOutlined,
  BarChartOutlined,
  PieChartOutlined,
  DotChartOutlined,
  RiseOutlined,
  FallOutlined,
  ThunderboltOutlined,
  SettingOutlined,
  CheckOutlined
} from '@ant-design/icons';
import { Card, Row, Col, Space, Typography, Statistic, Dropdown, Button, Segmented } from 'antd';
import TimeRangeSelector from './common/TimeRangeSelector';
import { calculateSMA, calculateEMA, calculateBollinger } from '../utils/indicators';

const { Text } = Typography;

const PerformanceChart = ({ data }) => {
  const [showSignals, setShowSignals] = useState(true);
  const [showPrice, setShowPrice] = useState(true);
  const [showSMA, setShowSMA] = useState(false);
  const [showEMA, setShowEMA] = useState(false);
  const [showBollinger, setShowBollinger] = useState(false);
  const [chartType, setChartType] = useState('area');
  const [timeRange, setTimeRange] = useState('max');

  // 处理数据格式并计算技术指标
  const chartData = useMemo(() => {
    const safeData = data || [];
    if (safeData.length === 0) return [];

    // 时间范围过滤 - 适配 TimeRangeSelector 的值
    let days = Infinity;
    switch (timeRange) {
      case '5d': days = 5; break;
      case '1mo': days = 30; break;
      case '3mo': days = 90; break;
      case '6mo': days = 180; break;
      case '1y': days = 365; break;
      case 'max': days = Infinity; break;
      default: days = Infinity;
    }

    // 兼容旧值（如果有）
    if (timeRange === '1W') days = 7;
    if (timeRange === '1M') days = 30;

    const cutoffDate = days !== Infinity
      ? new Date(Date.now() - days * 24 * 60 * 60 * 1000)
      : null;

    const filteredData = cutoffDate
      ? safeData.filter(item => new Date(item.date) >= cutoffDate)
      : safeData;

    const processed = filteredData.map((item, index) => ({
      date: item.date ? new Date(item.date).toLocaleDateString() : 'Unknown',
      fullDate: item.date,
      portfolio_value: item.total != null ? item.total : 0,
      price: item.price != null ? item.price : 0,
      signal: item.signal || 0,
      returns: (item.returns || 0) * 100,
      volume: item.volume || Math.random() * 1000000,
      index: index
    }));

    // 提取价格序列
    const prices = processed.map(item => item.price);

    // 计算指标
    const sma20 = calculateSMA(prices, 20);
    const sma50 = calculateSMA(prices, 50);
    const ema12 = calculateEMA(prices, 12);
    const ema26 = calculateEMA(prices, 26);
    const bb = calculateBollinger(prices, 20);

    // 将指标合并回数据对象
    processed.forEach((item, index) => {
      item.sma20 = sma20[index];
      item.sma50 = sma50[index];
      item.ema12 = ema12[index];
      item.ema26 = ema26[index];
      item.bbUpper = bb.upper[index];
      item.bbMiddle = bb.middle[index];
      item.bbLower = bb.lower[index];
    });

    return processed;
  }, [data, timeRange]);

  // 交易信号统计
  const signalStats = useMemo(() => {
    const buySignals = chartData.filter(item => item.signal === 1).length;
    const sellSignals = chartData.filter(item => item.signal === -1).length;
    return { buy: buySignals, sell: sellSignals, total: buySignals + sellSignals };
  }, [chartData]);

  // 早期返回检查（在所有hooks之后）
  if (chartData.length === 0) {
    return <div style={{ padding: 20, textAlign: 'center', color: '#999' }}>暂无图表数据</div>;
  }

  // 增强版自定义Tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          backgroundColor: 'rgba(255, 255, 255, 0.98)',
          padding: '14px 18px',
          border: '1px solid #e8e8e8',
          borderRadius: '10px',
          boxShadow: '0 6px 16px rgba(0,0,0,0.12)',
          backdropFilter: 'blur(8px)',
          minWidth: '180px'
        }}>
          <Text strong style={{ fontSize: '13px', display: 'block', marginBottom: '10px', color: '#1890ff' }}>
            📅 {label}
          </Text>
          {payload.map((entry, index) => (
            <div key={index} style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              margin: '6px 0',
              padding: '4px 0',
              borderBottom: index < payload.length - 1 ? '1px solid #f0f0f0' : 'none'
            }}>
              <span style={{
                display: 'flex',
                alignItems: 'center',
                color: '#666',
                fontSize: '12px'
              }}>
                <span style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '3px',
                  backgroundColor: entry.color,
                  marginRight: '10px',
                  display: 'inline-block',
                  boxShadow: `0 0 4px ${entry.color}40`
                }} />
                {entry.name}
              </span>
              <Text strong style={{
                color: entry.value >= 0 ? '#52c41a' : '#ff4d4f',
                marginLeft: '16px',
                fontSize: '13px'
              }}>
                {(entry.value != null ? entry.value : 0).toFixed(2)}
                {entry.name.includes('回撤') || entry.name.includes('收益') || entry.name.includes('%') ? '%' : ''}
              </Text>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  // 信号点数据
  const signalData = chartData.filter(item => item.signal !== 0);

  const commonProps = {
    data: chartData,
    margin: { top: 10, right: 30, left: 0, bottom: 0 }
  };

  return (
    <div>
      {/* 信号统计 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" style={{ background: 'linear-gradient(135deg, #52c41a20, #52c41a05)' }}>
            <Statistic
              title={<span style={{ color: '#52c41a' }}><RiseOutlined /> 买入信号</span>}
              value={signalStats.buy}
              valueStyle={{ color: '#52c41a', fontSize: '24px' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: 'linear-gradient(135deg, #ff4d4f20, #ff4d4f05)' }}>
            <Statistic
              title={<span style={{ color: '#ff4d4f' }}><FallOutlined /> 卖出信号</span>}
              value={signalStats.sell}
              valueStyle={{ color: '#ff4d4f', fontSize: '24px' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: 'linear-gradient(135deg, #1890ff20, #1890ff05)' }}>
            <Statistic
              title={<span style={{ color: '#1890ff' }}><ThunderboltOutlined /> 总交易次数</span>}
              value={signalStats.total}
              valueStyle={{ color: '#1890ff', fontSize: '24px' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: 'linear-gradient(135deg, #722ed120, #722ed105)' }}>
            <Statistic
              title="数据天数"
              value={chartData.length}
              suffix="天"
              valueStyle={{ fontSize: '24px' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 主图表 */}
      <Card
        title={
          <Space>
            <span>📈 组合价值走势</span>
            <Segmented
              size="small"
              options={[
                { label: '区域图', value: 'area' },
                { label: '折线图', value: 'line' }
              ]}
              value={chartType}
              onChange={setChartType}
            />
          </Space>
        }
        extra={
          <Space size="small">
            {/* 统一的时间范围选择器 */}
            <TimeRangeSelector
              value={timeRange}
              onChange={setTimeRange}
              size="small"
            />
            <span style={{ color: '#d9d9d9' }}>|</span>

            {/* 合并后的图表设置菜单 */}
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  {
                    key: 'price',
                    label: '显示价格',
                    icon: showPrice ? <CheckOutlined /> : null,
                    onClick: () => setShowPrice(!showPrice)
                  },
                  {
                    key: 'sma',
                    label: '显示 SMA',
                    icon: showSMA ? <CheckOutlined /> : null,
                    onClick: () => setShowSMA(!showSMA)
                  },
                  {
                    key: 'ema',
                    label: '显示 EMA',
                    icon: showEMA ? <CheckOutlined /> : null,
                    onClick: () => setShowEMA(!showEMA)
                  },
                  {
                    key: 'bollinger',
                    label: '显示布林带',
                    icon: showBollinger ? <CheckOutlined /> : null,
                    onClick: () => setShowBollinger(!showBollinger)
                  },
                  { type: 'divider' },
                  {
                    key: 'signals',
                    label: '显示交易信号',
                    icon: showSignals ? <CheckOutlined /> : null,
                    onClick: () => setShowSignals(!showSignals)
                  }
                ]
              }}
            >
              <Button icon={<SettingOutlined />} size="small">
                图表设置
              </Button>
            </Dropdown>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <ResponsiveContainer width="100%" height={450}>
          <ComposedChart {...commonProps}>
            <defs>
              <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#1890ff" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#1890ff" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#666' }}
              tickLine={{ stroke: '#e8e8e8' }}
              axisLine={{ stroke: '#e8e8e8' }}
              interval="preserveStartEnd"
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 11, fill: '#666' }}
              tickLine={{ stroke: '#e8e8e8' }}
              axisLine={{ stroke: '#e8e8e8' }}
              tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 11, fill: '#666' }}
              tickLine={{ stroke: '#e8e8e8' }}
              axisLine={{ stroke: '#e8e8e8' }}
              tickFormatter={(value) => `$${value.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ paddingTop: '15px' }}
              formatter={(value) => <Text style={{ fontSize: '12px' }}>{value}</Text>}
            />

            {/* 组合价值 */}
            {chartType === 'area' ? (
              <Area
                yAxisId="left"
                type="monotone"
                dataKey="portfolio_value"
                stroke="#1890ff"
                strokeWidth={2}
                fill="url(#portfolioGradient)"
                name="组合价值"
              />
            ) : (
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="portfolio_value"
                stroke="#1890ff"
                strokeWidth={2}
                dot={false}
                name="组合价值"
              />
            )}

            {/* 股票价格 */}
            {showPrice && (
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="price"
                stroke="#722ed1"
                strokeWidth={1.5}
                dot={false}
                name="股票价格"
              />
            )}

            {/* SMA指标 */}
            {showSMA && (
              <>
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="sma20"
                  stroke="#faad14"
                  strokeWidth={1}
                  dot={false}
                  name="SMA20"
                  strokeDasharray="3 3"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="sma50"
                  stroke="#13c2c2"
                  strokeWidth={1}
                  dot={false}
                  name="SMA50"
                  strokeDasharray="5 5"
                />
              </>
            )}

            {/* EMA指标 */}
            {showEMA && (
              <>
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="ema12"
                  stroke="#eb2f96"
                  strokeWidth={1}
                  dot={false}
                  name="EMA12"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="ema26"
                  stroke="#52c41a"
                  strokeWidth={1}
                  dot={false}
                  name="EMA26"
                />
              </>
            )}

            {/* 布林带 */}
            {showBollinger && (
              <>
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="bbUpper"
                  stroke="#ff7875"
                  strokeWidth={1}
                  dot={false}
                  name="布林上轨"
                  strokeDasharray="2 2"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="bbMiddle"
                  stroke="#69c0ff"
                  strokeWidth={1}
                  dot={false}
                  name="布林中轨"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="bbLower"
                  stroke="#ff7875"
                  strokeWidth={1}
                  dot={false}
                  name="布林下轨"
                  strokeDasharray="2 2"
                />
              </>
            )}

            {/* 买入信号 */}
            {showSignals && signalData.filter(item => item.signal === 1).map((item, index) => (
              <ReferenceLine
                key={`buy-${index}`}
                yAxisId="left"
                x={item.date}
                stroke="#52c41a"
                strokeWidth={2}
                strokeDasharray="3 3"
                label={{ value: '▲', position: 'top', fill: '#52c41a', fontSize: 12 }}
              />
            ))}

            {/* 卖出信号 */}
            {showSignals && signalData.filter(item => item.signal === -1).map((item, index) => (
              <ReferenceLine
                key={`sell-${index}`}
                yAxisId="left"
                x={item.date}
                stroke="#ff4d4f"
                strokeWidth={2}
                strokeDasharray="3 3"
                label={{ value: '▼', position: 'bottom', fill: '#ff4d4f', fontSize: 12 }}
              />
            ))}

            {/* 缩放滑块 */}
            <Brush
              dataKey="date"
              height={35}
              stroke="#1890ff"
              fill="#fafafa"
              tickFormatter={() => ''}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
};

export default PerformanceChart;
