import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  DatePicker,
  Empty,
  InputNumber,
  Row,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ExperimentOutlined,
  LineChartOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { postEtfRotationWalkforward } from '../services/api';
import dayjs from '../utils/dayjs';

const { RangePicker } = DatePicker;
const { Text } = Typography;

/**
 * Walkforward backtest panel for the ETF rotation dashboard.
 *
 * Scope: this is the *historical strategy stability* tile — it rolls the
 * committed price matrix through N overlapping windows and aggregates
 * per-window metrics into a 0-1 ``consistency_score``. It is distinct
 * from the attribution tile (which scores the recent factor contribution
 * over the last X days): walkforward answers "does the strategy survive
 * across regimes?", attribution answers "what's the factor adding right
 * now?".
 *
 * UX choices:
 *   * Button-driven (not auto-run) because the backend takes ~30s and we
 *     don't want to burn a window every time the dashboard mounts.
 *   * Collapsed by default (the dashboard wraps this in a Collapse).
 *   * Results persist after a run; the Run button shows "重新回测" so
 *     users can tweak controls and re-run without losing context.
 *   * Negative-return windows render red, positive green — the same
 *     convention as the attribution tile.
 */

const POSITIVE_COLOR = '#52c41a';
const NEGATIVE_COLOR = '#ff4d4f';
const BUY_HOLD_COLOR = '#1677ff';

const DEFAULT_PERIOD_START = '2024-01-01';
const DEFAULT_PERIOD_END = '2025-04-30';

const formatPct = (value, fractionDigits = 2) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(fractionDigits)}%`;
};

const formatNumber = (value, fractionDigits = 2) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return value.toFixed(fractionDigits);
};

const formatDateLabel = (value) => {
  if (!value) return '';
  return String(value).slice(0, 10);
};

const WalkTooltip = ({ active, payload, meanBuyHoldPct }) => {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload || {};
  const ret = Number(row.return_pct) || 0;
  return (
    <div
      style={{
        background: 'var(--color-bg-elevated, #fff)',
        border: '1px solid var(--color-border, rgba(0,0,0,0.15))',
        borderRadius: 6,
        padding: '8px 10px',
        fontSize: 12,
        boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>窗口 #{row.window_idx}</div>
      <div style={{ color: 'var(--text-muted, #888)', marginBottom: 4 }}>
        {row.period}
      </div>
      <div style={{ color: ret >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR, fontWeight: 600 }}>
        策略收益: {formatPct(ret)}
      </div>
      <div>买入持有: {formatPct(Number(row.buy_hold_pct) || 0)}</div>
      <div>Sharpe: {formatNumber(Number(row.sharpe_ratio) || 0)}</div>
      <div>MaxDD: {formatPct(-Math.abs(Number(row.max_dd_pct) || 0))}</div>
      {Number.isFinite(meanBuyHoldPct) ? (
        <div style={{ marginTop: 4, color: BUY_HOLD_COLOR }}>
          平均买入持有线: {formatPct(meanBuyHoldPct)}
        </div>
      ) : null}
    </div>
  );
};

const buildSummaryTagLabel = (report) => {
  if (!report) return null;
  const pctPos = Number(report.pct_positive_windows) || 0;
  const median = Number(report.median_window_return_pct) || 0;
  return `${(pctPos * 100).toFixed(0)}% 窗口正收益 · median ${formatPct(median)}`;
};

const EtfWalkforwardPanel = ({
  // Allow tests to inject a fake fetcher without going through axios.
  postWalkforward = postEtfRotationWalkforward,
}) => {
  const [periodRange, setPeriodRange] = useState([
    dayjs(DEFAULT_PERIOD_START),
    dayjs(DEFAULT_PERIOD_END),
  ]);
  const [windowMonths, setWindowMonths] = useState(3);
  const [stepMonths, setStepMonths] = useState(1);
  const [enablePolicy, setEnablePolicy] = useState(false);
  const [useCachedResult, setUseCachedResult] = useState(true);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [cacheMeta, setCacheMeta] = useState(null);

  const handleRun = useCallback(async () => {
    if (!periodRange || !periodRange[0] || !periodRange[1]) {
      setError('请先选择回测日期区间。');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await postWalkforward({
        periodStart: periodRange[0].format('YYYY-MM-DD'),
        periodEnd: periodRange[1].format('YYYY-MM-DD'),
        windowMonths: Number(windowMonths) || 3,
        stepMonths: Number(stepMonths) || 1,
        enablePolicySignalFactor: Boolean(enablePolicy),
        refresh: !useCachedResult,
      });
      if (response?.success) {
        setReport(response.data || null);
        setCacheMeta({
          cached: Boolean(response.cached),
          age: response.cache_age_seconds ?? null,
        });
      } else {
        setReport(null);
        setError(response?.error || response?.detail || '回测失败');
      }
    } catch (exc) {
      setReport(null);
      setError(exc?.userMessage || exc?.message || '回测失败');
    } finally {
      setLoading(false);
    }
  }, [
    periodRange,
    windowMonths,
    stepMonths,
    enablePolicy,
    useCachedResult,
    postWalkforward,
  ]);

  const chartData = useMemo(() => {
    const windows = Array.isArray(report?.windows) ? report.windows : [];
    return windows.map((w, idx) => ({
      window_idx: idx + 1,
      period: `${formatDateLabel(w.period_start)} → ${formatDateLabel(w.period_end)}`,
      return_pct: Number(w.total_return_pct) || 0,
      sharpe_ratio: Number(w.sharpe_ratio) || 0,
      max_dd_pct: Number(w.max_drawdown_pct) || 0,
      buy_hold_pct: Number(w.comparable_buy_hold_return_pct) || 0,
      win_rate: Number(w.win_rate) || 0,
    }));
  }, [report]);

  const meanBuyHoldPct = useMemo(() => {
    if (typeof report?.mean_buy_hold_return_pct === 'number') {
      return report.mean_buy_hold_return_pct;
    }
    if (chartData.length === 0) return null;
    const sum = chartData.reduce((acc, r) => acc + (r.buy_hold_pct || 0), 0);
    return sum / chartData.length;
  }, [report, chartData]);

  const summaryTagLabel = buildSummaryTagLabel(report);
  const summaryTagColor = (() => {
    if (!report) return 'default';
    const pctPos = Number(report.pct_positive_windows) || 0;
    return pctPos >= 0.6 ? 'green' : pctPos >= 0.4 ? 'orange' : 'red';
  })();

  const tableColumns = [
    {
      title: '窗口',
      dataIndex: 'window_idx',
      key: 'window_idx',
      width: 70,
      render: (idx) => `#${idx}`,
    },
    {
      title: '区间',
      dataIndex: 'period',
      key: 'period',
    },
    {
      title: '策略收益',
      dataIndex: 'return_pct',
      key: 'return_pct',
      render: (value) => (
        <Text type={value >= 0 ? 'success' : 'danger'}>{formatPct(Number(value) || 0)}</Text>
      ),
    },
    {
      title: '买入持有',
      dataIndex: 'buy_hold_pct',
      key: 'buy_hold_pct',
      render: (value) => formatPct(Number(value) || 0),
    },
    {
      title: 'Sharpe',
      dataIndex: 'sharpe_ratio',
      key: 'sharpe_ratio',
      render: (value) => formatNumber(Number(value) || 0),
    },
    {
      title: 'MaxDD',
      dataIndex: 'max_dd_pct',
      key: 'max_dd_pct',
      render: (value) => (
        <Text type="warning">{formatPct(-Math.abs(Number(value) || 0))}</Text>
      ),
    },
    {
      title: '命中率',
      dataIndex: 'win_rate',
      key: 'win_rate',
      render: (value) => `${(Number(value) * 100 || 0).toFixed(1)}%`,
    },
  ];

  const chartHeight = Math.max(220, Math.min(420, chartData.length * 28 + 80));
  const runLabel = report ? '重新回测' : '运行回测';

  return (
    <Card
      size="small"
      data-testid="etf-walkforward-panel"
      style={{ background: 'var(--color-fill-quaternary, rgba(0,0,0,0.02))' }}
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space size={8} wrap align="center">
          <ExperimentOutlined />
          <Text strong>历史回测 (Walkforward)</Text>
          {summaryTagLabel ? (
            <Tag color={summaryTagColor} data-testid="etf-walkforward-summary-tag">
              {summaryTagLabel}
            </Tag>
          ) : null}
          <Tooltip
            title={(
              <Space direction="vertical" size={2}>
                <div>把 ETF 轮动策略在已提交的历史价格矩阵上滚动 N 个 ``window_months`` 的窗口。</div>
                <div>每次切窗运行一次完整 backtest，再把窗口收益 / Sharpe / 回撤聚合为稳定性报告。</div>
                <div>区别于上方 "因子归因" 面板（最近 X 天因子贡献）：walkforward 评估的是策略本身的多窗口稳健性。</div>
                <div>v0.1 caveats 继承：无交易成本 / 无买卖价差 / 无市场冲击 / next-bar close 全额成交。</div>
              </Space>
            )}
          >
            <Tag>什么是 walkforward？</Tag>
          </Tooltip>
        </Space>

        <Card size="small" data-testid="etf-walkforward-controls">
          <Row gutter={[12, 12]} align="middle">
            <Col xs={24} md={8}>
              <Text type="secondary">回测区间</Text>
              <div
                data-testid="etf-walkforward-range-picker"
                style={{ marginTop: 4 }}
              >
                <RangePicker
                  style={{ width: '100%' }}
                  value={periodRange}
                  onChange={(val) => setPeriodRange(val)}
                  separator="至"
                  placeholder={['开始日期', '结束日期']}
                />
              </div>
            </Col>
            <Col xs={12} md={3}>
              <Text type="secondary">窗口(月)</Text>
              <div
                data-testid="etf-walkforward-window-months"
                style={{ marginTop: 4 }}
              >
                <InputNumber
                  min={1}
                  max={24}
                  value={windowMonths}
                  onChange={(val) => setWindowMonths(val)}
                  style={{ width: '100%' }}
                />
              </div>
            </Col>
            <Col xs={12} md={3}>
              <Text type="secondary">步长(月)</Text>
              <div
                data-testid="etf-walkforward-step-months"
                style={{ marginTop: 4 }}
              >
                <InputNumber
                  min={1}
                  max={12}
                  value={stepMonths}
                  onChange={(val) => setStepMonths(val)}
                  style={{ width: '100%' }}
                />
              </div>
            </Col>
            <Col xs={12} md={3}>
              <Space direction="vertical" size={0}>
                <Text type="secondary">政策因子</Text>
                <Switch
                  checked={enablePolicy}
                  onChange={(val) => setEnablePolicy(val)}
                  checkedChildren="ON"
                  unCheckedChildren="OFF"
                  data-testid="etf-walkforward-policy-switch"
                />
              </Space>
            </Col>
            <Col xs={12} md={3}>
              <Space direction="vertical" size={0}>
                <Text type="secondary">缓存</Text>
                <Tooltip title="关闭后本次请求会带 refresh=true，绕过后端 1 小时缓存。">
                  <Checkbox
                    checked={useCachedResult}
                    onChange={(event) => setUseCachedResult(event.target.checked)}
                    data-testid="etf-walkforward-cache-checkbox"
                  >
                    使用
                  </Checkbox>
                </Tooltip>
              </Space>
            </Col>
            <Col xs={12} md={4}>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleRun}
                loading={loading}
                block
                data-testid="etf-walkforward-run-button"
              >
                {runLabel}
              </Button>
            </Col>
          </Row>
        </Card>

        {loading ? (
          <Card size="small" data-testid="etf-walkforward-loading">
            <Space>
              <Spin />
              <Text type="secondary">回测中… 约 30 秒 / 14 个窗口</Text>
            </Space>
          </Card>
        ) : null}

        {error ? (
          <Alert
            type="error"
            showIcon
            message="回测失败"
            description={error}
            data-testid="etf-walkforward-error"
          />
        ) : null}

        {!loading && !error && !report ? (
          <Empty
            description="选好参数后点击 “运行回测” 启动 walkforward 分析（默认 14 个窗口，~30s）。"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            data-testid="etf-walkforward-empty"
          />
        ) : null}

        {!loading && report && chartData.length > 0 ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Card size="small" data-testid="etf-walkforward-summary-tile">
              <Row gutter={[16, 12]}>
                <Col xs={12} md={4}>
                  <Statistic
                    title="median 窗口收益"
                    value={formatPct(report.median_window_return_pct)}
                    valueStyle={{
                      color: (Number(report.median_window_return_pct) || 0) >= 0
                        ? POSITIVE_COLOR : NEGATIVE_COLOR,
                    }}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="mean 窗口收益"
                    value={formatPct(report.mean_window_return_pct)}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="std (pp)"
                    value={formatNumber(report.return_std_pct)}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="% 正收益窗口"
                    value={`${((Number(report.pct_positive_windows) || 0) * 100).toFixed(1)}%`}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="consistency"
                    value={formatNumber(report.consistency_score, 3)}
                    suffix=" / 1.0"
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="mean buy-hold/窗口"
                    value={formatPct(report.mean_buy_hold_return_pct)}
                    valueStyle={{ color: BUY_HOLD_COLOR }}
                  />
                </Col>
              </Row>
              {cacheMeta?.cached ? (
                <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
                  缓存命中（{Math.round(cacheMeta.age || 0)}s ago）·
                  {' '}共 {report.n_windows} 个窗口 · 窗口 {report.window_months} 月 / 步长 {report.step_months} 月
                </Text>
              ) : (
                <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
                  共 {report.n_windows} 个窗口 · 窗口 {report.window_months} 月 / 步长 {report.step_months} 月
                </Text>
              )}
            </Card>

            <Card
              size="small"
              data-testid="etf-walkforward-chart-card"
              title={(
                <Space size={4}>
                  <LineChartOutlined />
                  <Text strong>逐窗收益（正绿 / 负红，蓝虚线 = 平均 buy-hold/窗口）</Text>
                </Space>
              )}
            >
              <div
                style={{ width: '100%', height: chartHeight }}
                data-testid="etf-walkforward-chart"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData}
                    margin={{ top: 8, right: 16, left: 4, bottom: 16 }}
                  >
                    <CartesianGrid
                      stroke="rgba(148, 163, 184, 0.12)"
                      strokeDasharray="4 4"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="window_idx"
                      tick={{ fill: 'rgba(120, 130, 145, 0.85)', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value) => `#${value}`}
                    />
                    <YAxis
                      tick={{ fill: 'rgba(120, 130, 145, 0.85)', fontSize: 11 }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value) => `${Number(value).toFixed(1)}%`}
                    />
                    <RechartsTooltip
                      content={<WalkTooltip meanBuyHoldPct={meanBuyHoldPct} />}
                    />
                    <ReferenceLine y={0} stroke="rgba(148, 163, 184, 0.45)" />
                    {Number.isFinite(meanBuyHoldPct) ? (
                      <ReferenceLine
                        y={meanBuyHoldPct}
                        stroke={BUY_HOLD_COLOR}
                        strokeDasharray="4 4"
                        label={{
                          value: `平均 buy-hold ${formatPct(meanBuyHoldPct)}`,
                          fill: BUY_HOLD_COLOR,
                          fontSize: 11,
                          position: 'insideTopRight',
                        }}
                        data-testid="etf-walkforward-buy-hold-overlay"
                      />
                    ) : null}
                    <Bar
                      dataKey="return_pct"
                      radius={[4, 4, 0, 0]}
                    >
                      {chartData.map((row) => (
                        <Cell
                          key={`bar-${row.window_idx}`}
                          fill={row.return_pct >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR}
                          data-testid={`etf-walkforward-bar-${row.window_idx}`}
                          data-sign={row.return_pct >= 0 ? 'positive' : 'negative'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card
              size="small"
              title="逐窗明细"
              data-testid="etf-walkforward-table-card"
            >
              <Table
                size="small"
                pagination={false}
                rowKey="window_idx"
                dataSource={chartData}
                columns={tableColumns}
                data-testid="etf-walkforward-table"
              />
            </Card>
          </Space>
        ) : null}

        {!loading && report && chartData.length === 0 ? (
          <Empty
            description="该参数组合下没有可用窗口（period 短于 window_months 或无价格数据）。"
            data-testid="etf-walkforward-no-windows"
          />
        ) : null}
      </Space>
    </Card>
  );
};

export default EtfWalkforwardPanel;
