import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert, Card, Collapse, Empty, Space, Spin, Table, Tag, Tooltip, Typography,
} from 'antd';
import { ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';

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
 *  * an Antd Collapse hides the per-rebalance bar chart + winner/loser
 *    tables behind a single click — keeps the default view compact.
 *
 * Data fetching is lazy: we only fire the API call once the section is
 * mounted (i.e. only when ``visible`` is true). Backend caches for 5min.
 */
const SimpleBar = ({ value, peak }) => {
  const denom = peak > 0 ? peak : 1;
  const widthPct = Math.min(100, Math.abs(value) / denom * 100);
  const color = value >= 0 ? '#52c41a' : '#ff4d4f';
  return (
    <div style={{
      position: 'relative', height: 14, width: '100%',
      background: 'var(--color-fill-tertiary, rgba(0,0,0,0.04))', borderRadius: 4,
    }}>
      <div style={{
        position: 'absolute', top: 0,
        left: value >= 0 ? '50%' : `${50 - widthPct / 2}%`,
        height: '100%', width: `${widthPct / 2}%`,
        background: color, borderRadius: 4,
      }} />
      <div style={{
        position: 'absolute', top: 0, left: '50%',
        height: '100%', width: 1,
        background: 'var(--color-border, rgba(0,0,0,0.15))',
      }} />
    </div>
  );
};

const formatPct = (value) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '0.0000%';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(4)}%`;
};

const EtfPolicyFactorAttributionPanel = ({
  visible = false,
  periodDays = 30,
  // Allow tests to inject a fake fetcher without going through axios.
  fetchAttribution = getEtfRotationPolicyFactorAttribution,
}) => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchAttribution({ periodDays, refresh });
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
  }, [fetchAttribution, periodDays]);

  useEffect(() => {
    if (visible) {
      load(false);
    }
  }, [visible, load]);

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

  const perRebal = Array.isArray(report?.per_rebalance_attribution)
    ? report.per_rebalance_attribution : [];
  const peakAbs = perRebal.reduce(
    (acc, row) => Math.max(acc, Math.abs(Number(row.factor_contribution_pct) || 0)),
    0,
  );

  const winners = Array.isArray(report?.top_winner_etfs) ? report.top_winner_etfs : [];
  const losers = Array.isArray(report?.top_loser_etfs) ? report.top_loser_etfs : [];

  const headerTitle = (
    <Space size={8} wrap data-testid="etf-policy-factor-attribution-header">
      <ExperimentOutlined />
      <Text strong>{periodDays}日因子贡献</Text>
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

  return (
    <Card
      size="small"
      data-testid="etf-policy-factor-attribution"
      style={{ marginTop: 8, background: 'var(--color-fill-quaternary, rgba(0,0,0,0.02))' }}
    >
      <Collapse
        ghost
        items={[{
          key: 'attribution',
          label: headerTitle,
          extra: (
            <Tooltip title="重新计算（跳过缓存）">
              <ReloadOutlined
                data-testid="etf-policy-factor-attribution-refresh"
                onClick={(event) => {
                  event.stopPropagation();
                  load(true);
                }}
                style={{ cursor: 'pointer' }}
              />
            </Tooltip>
          ),
          children: (
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              {loading && <Spin />}
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
                    <Text strong>逐次调仓贡献（%）</Text>
                    <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                      {perRebal.map((row) => {
                        const c = Number(row.factor_contribution_pct) || 0;
                        return (
                          <Space
                            key={row.run_at}
                            size={8}
                            style={{ width: '100%' }}
                            data-testid={`etf-policy-factor-attribution-bar-${row.run_at}`}
                          >
                            <Text style={{ width: 168, fontSize: 12 }} type="secondary">
                              {String(row.run_at).slice(0, 16).replace('T', ' ')}
                            </Text>
                            <div style={{ flex: 1 }}>
                              <SimpleBar value={c} peak={peakAbs} />
                            </div>
                            <Text
                              type={c >= 0 ? 'success' : 'danger'}
                              style={{ width: 80, textAlign: 'right', fontSize: 12 }}
                            >
                              {formatPct(c)}
                            </Text>
                          </Space>
                        );
                      })}
                    </Space>
                  </div>

                  {winners.length > 0 && (
                    <div data-testid="etf-policy-factor-attribution-winners">
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
                            title: '调仓次数',
                            dataIndex: 'n_rebalances',
                          },
                        ]}
                        style={{ marginTop: 8 }}
                      />
                    </div>
                  )}

                  {losers.length > 0 && (
                    <div data-testid="etf-policy-factor-attribution-losers">
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
                            title: '调仓次数',
                            dataIndex: 'n_rebalances',
                          },
                        ]}
                        style={{ marginTop: 8 }}
                      />
                    </div>
                  )}
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
