import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Card, Collapse, Empty, Radio, Space, Spin, Table, Tag, Tooltip, Typography,
} from 'antd';
import { ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
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

import { getEtfRotationPolicyFactorAttribution } from '../services/api';

const { Text } = Typography;

/**
 * Expandable "因子归因" section for the ETF rotation dashboard.
 *
 * Renders only when ``visible`` (i.e. ``policy_signal_factor_enabled``) is
 * true; otherwise the component returns ``null`` so the dashboard layout
 * doesn't even allocate space. Inside the section:
 *
 *  * a header tag shows the net contribution sign (``+X%`` / ``-X%``);
 *  * a Recharts BarChart renders per-rebalance contributions (green = positive,
 *    red = negative) inside an Antd Collapse so the default view stays compact;
 *  * a Radio period selector (7d / 30d / 60d / 90d) re-fetches on change;
 *  * a refresh button bypasses the backend's 5-minute cache.
 *
 * Data fetching is lazy: we only fire the API call once the section is
 * mounted (i.e. only when ``visible`` is true). Backend caches for 5min.
 */
const PERIOD_OPTIONS = [
  { label: '7天', value: 7 },
  { label: '30天', value: 30 },
  { label: '60天', value: 60 },
  { label: '90天', value: 90 },
];

const POSITIVE_COLOR = '#52c41a';
const NEGATIVE_COLOR = '#ff4d4f';

const formatPct = (value) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0.0000%';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(4)}%`;
};

const formatRunAt = (raw) => String(raw || '').slice(0, 16).replace('T', ' ');

const AttributionTooltip = ({ active, payload }) => {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload || {};
  const c = Number(row.contribution_pct) || 0;
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
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{row.label}</div>
      <div>ON: {formatPct(Number(row.on_pct) || 0)}</div>
      <div>OFF: {formatPct(Number(row.off_pct) || 0)}</div>
      <div style={{ color: c >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR, fontWeight: 600 }}>
        贡献: {formatPct(c)}
      </div>
    </div>
  );
};

const EtfPolicyFactorAttributionPanel = ({
  visible = false,
  periodDays: initialPeriodDays = 30,
  // Allow tests to inject a fake fetcher without going through axios.
  fetchAttribution = getEtfRotationPolicyFactorAttribution,
}) => {
  const [periodDays, setPeriodDays] = useState(initialPeriodDays);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (effectivePeriod, refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchAttribution({ periodDays: effectivePeriod, refresh });
      if (response?.success) {
        setReport(response.data);
      } else {
        setReport(null);
        setError(response?.error || '加载失败');
      }
    } catch (exc) {
      setReport(null);
      setError(exc?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, [fetchAttribution]);

  // Lazy fetch: only when the panel is visible AND when periodDays changes.
  useEffect(() => {
    if (visible) {
      load(periodDays, false);
    }
  }, [visible, periodDays, load]);

  // Chart rows: convert the API's per_rebalance_attribution into the shape
  // Recharts wants. Memoised so each Tooltip render doesn't re-derive.
  const chartData = useMemo(() => {
    const perRebal = Array.isArray(report?.per_rebalance_attribution)
      ? report.per_rebalance_attribution : [];
    return perRebal.map((row) => ({
      runAt: row.run_at,
      label: formatRunAt(row.run_at),
      contribution_pct: Number(row.factor_contribution_pct) || 0,
      on_pct: Number(row.factor_on_return_pct) || 0,
      off_pct: Number(row.factor_off_return_pct) || 0,
    }));
  }, [report]);

  if (!visible) {
    return null;
  }

  const contribution = report?.factor_contribution_pct ?? 0;
  const onReturn = report?.factor_on_return_pct ?? 0;
  const offReturn = report?.factor_off_return_pct ?? 0;
  const hitRate = report?.hit_rate_pct ?? 0;
  const nRebalances = report?.n_factor_on_rebalances ?? 0;
  const sign = contribution >= 0 ? '+' : '';
  const contributionLabel = `${sign}${contribution.toFixed(4)}%`;
  const tagColor = contribution > 0 ? 'green' : contribution < 0 ? 'red' : 'default';

  const winners = Array.isArray(report?.top_winner_etfs) ? report.top_winner_etfs : [];
  const losers = Array.isArray(report?.top_loser_etfs) ? report.top_loser_etfs : [];

  const headerTitle = (
    <Space size={8} wrap data-testid="etf-policy-factor-attribution-header">
      <ExperimentOutlined />
      <Text strong>{periodDays}日因子归因</Text>
      <Tooltip
        title={(
          <Space direction="vertical" size={2}>
            <div>对启用因子的历史调仓做归因回放，对比 factor-on 与比例 factor-off proxy。</div>
            <div>不计交易成本与调仓滞后；off leg 不是完整二次跑策略。</div>
          </Space>
        )}
      >
        <Tag color={tagColor} data-testid="etf-policy-factor-attribution-tag">
          {contributionLabel}
        </Tag>
      </Tooltip>
      <Text type="secondary">
        ON {formatPct(onReturn)} · OFF {formatPct(offReturn)} · 命中率 {hitRate.toFixed(1)}%
      </Text>
      <Text type="secondary">· {nRebalances} 次调仓</Text>
    </Space>
  );

  const periodSelector = (
    <Radio.Group
      size="small"
      value={periodDays}
      data-testid="etf-policy-factor-attribution-period"
      onClick={(event) => event.stopPropagation()}
      onChange={(event) => {
        const next = Number(event.target.value);
        if (Number.isFinite(next) && next !== periodDays) {
          setPeriodDays(next);
        }
      }}
    >
      {PERIOD_OPTIONS.map((opt) => (
        <Radio.Button
          key={opt.value}
          value={opt.value}
          data-testid={`etf-policy-factor-attribution-period-${opt.value}`}
        >
          {opt.label}
        </Radio.Button>
      ))}
    </Radio.Group>
  );

  const chartHeight = Math.max(160, Math.min(360, chartData.length * 28 + 80));

  return (
    <Card
      size="small"
      data-testid="etf-policy-factor-attribution-panel"
      style={{ marginTop: 8, background: 'var(--color-fill-quaternary, rgba(0,0,0,0.02))' }}
    >
      <Collapse
        ghost
        items={[{
          key: 'attribution',
          label: headerTitle,
          extra: (
            <Space size={6} onClick={(event) => event.stopPropagation()}>
              {periodSelector}
              <Tooltip title="重新计算（跳过缓存）">
                <ReloadOutlined
                  data-testid="etf-policy-factor-attribution-refresh"
                  onClick={(event) => {
                    event.stopPropagation();
                    load(periodDays, true);
                  }}
                  style={{ cursor: 'pointer' }}
                />
              </Tooltip>
            </Space>
          ),
          children: (
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              {loading && <Spin data-testid="etf-policy-factor-attribution-loading" />}
              {error && (
                <Alert
                  type="error"
                  showIcon
                  message="加载失败"
                  description={error}
                  data-testid="etf-policy-factor-attribution-error"
                />
              )}
              {!loading && !error && nRebalances === 0 && (
                <Empty
                  description={(
                    <Space direction="vertical" size={2}>
                      <Text type="secondary">
                        最近 {periodDays} 天没有启用因子的调仓记录，无法进行归因。
                      </Text>
                      <Text type="secondary">
                        启用开关后跑几次调仓再回来查看。
                      </Text>
                    </Space>
                  )}
                  data-testid="etf-policy-factor-attribution-empty"
                />
              )}
              {!loading && !error && nRebalances > 0 && (
                <>
                  <div data-testid="etf-policy-factor-attribution-chart">
                    <Space size={4} align="baseline">
                      <Text strong>逐次调仓贡献（%）</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        正向（绿）/ 负向（红）— hover 看 ON / OFF / 净贡献明细。
                      </Text>
                    </Space>
                    <div style={{ width: '100%', height: chartHeight, marginTop: 8 }}>
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
                            dataKey="label"
                            tick={{ fill: 'rgba(120, 130, 145, 0.85)', fontSize: 10 }}
                            tickLine={false}
                            axisLine={false}
                            angle={-25}
                            textAnchor="end"
                            height={48}
                            interval={0}
                          />
                          <YAxis
                            tick={{ fill: 'rgba(120, 130, 145, 0.85)', fontSize: 11 }}
                            tickLine={false}
                            axisLine={false}
                            tickFormatter={(value) => `${Number(value).toFixed(2)}%`}
                          />
                          <RechartsTooltip content={<AttributionTooltip />} />
                          <ReferenceLine y={0} stroke="rgba(148, 163, 184, 0.45)" />
                          <Bar
                            dataKey="contribution_pct"
                            radius={[4, 4, 0, 0]}
                            data-testid="etf-policy-factor-attribution-bar-series"
                          >
                            {chartData.map((row) => (
                              <Cell
                                key={row.runAt}
                                fill={row.contribution_pct >= 0 ? POSITIVE_COLOR : NEGATIVE_COLOR}
                                data-testid={`etf-policy-factor-attribution-bar-${row.runAt}`}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <Space
                    direction="horizontal"
                    size={16}
                    align="start"
                    wrap
                    style={{ width: '100%' }}
                  >
                    {winners.length > 0 && (
                      <div
                        data-testid="etf-policy-factor-attribution-winners"
                        style={{ flex: '1 1 280px', minWidth: 220 }}
                      >
                        <Text strong>Top winners</Text>
                        <Table
                          size="small"
                          pagination={false}
                          rowKey="code"
                          dataSource={winners}
                          columns={[
                            { title: 'ETF', dataIndex: 'code' },
                            {
                              title: '贡献',
                              dataIndex: 'contribution_pct',
                              render: (v) => (
                                <Text type="success">{formatPct(Number(v) || 0)}</Text>
                              ),
                            },
                            {
                              title: '次数',
                              dataIndex: 'n_rebalances',
                            },
                          ]}
                          style={{ marginTop: 8 }}
                        />
                      </div>
                    )}

                    {losers.length > 0 && (
                      <div
                        data-testid="etf-policy-factor-attribution-losers"
                        style={{ flex: '1 1 280px', minWidth: 220 }}
                      >
                        <Text strong>Top losers</Text>
                        <Table
                          size="small"
                          pagination={false}
                          rowKey="code"
                          dataSource={losers}
                          columns={[
                            { title: 'ETF', dataIndex: 'code' },
                            {
                              title: '贡献',
                              dataIndex: 'contribution_pct',
                              render: (v) => (
                                <Text type="danger">{formatPct(Number(v) || 0)}</Text>
                              ),
                            },
                            {
                              title: '次数',
                              dataIndex: 'n_rebalances',
                            },
                          ]}
                          style={{ marginTop: 8 }}
                        />
                      </div>
                    )}
                  </Space>
                </>
              )}
            </Space>
          ),
        }]}
      />
    </Card>
  );
};

export default EtfPolicyFactorAttributionPanel;
