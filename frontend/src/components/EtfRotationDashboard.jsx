import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, Button, Card, Col, Empty, Row, Space, Spin, Statistic, Table, Tag, Tooltip, Typography,
} from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExperimentOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SwapOutlined,
  WarningOutlined,
} from '@ant-design/icons';

import {
  getEtfRotationDailySignal,
  getEtfRotationLiveTarget,
  postEtfRotationRefresh,
} from '../services/api';

const { Text, Title } = Typography;

const ETF_NAMES = {
  '159985': '豆粕ETF华夏',
  '512400': '有色金属ETF南方',
  '510300': '沪深300ETF华泰柏瑞',
  '518680': '金ETF富国',
  '513130': '恒生科技ETF华泰柏瑞',
  CASH: '现金',
};

const ACTION_META = {
  buy: { color: 'red', label: '买入' },
  sell: { color: 'green', label: '卖出' },
  hold: { color: 'default', label: '持有' },
};

const SOURCE_STATUS_META = {
  ready: { color: 'success', label: '实盘', icon: <CheckCircleOutlined /> },
  synthetic: { color: 'warning', label: '示例/合成', icon: <ExperimentOutlined /> },
  stale: { color: 'warning', label: '过期', icon: <ClockCircleOutlined /> },
  missing: { color: 'error', label: '缺失', icon: <WarningOutlined /> },
  error: { color: 'error', label: '错误', icon: <WarningOutlined /> },
};

const QUOTE_SOURCE_LABELS = {
  live: '实时报价+实盘历史',
  live_quotes_synthetic_history: '实时报价 / 合成历史',
  live_history_synthetic_quotes: '实盘历史 / 合成报价',
  synthetic: '全合成',
  fallback_synthetic: '回退合成',
};

const MANUAL_BANNER_ZH = '手动调仓计划：请人工复核后执行；不连接券商接口，也不会自动下单。';

const POLL_INTERVAL_MS = 30_000;

const STATIC_REASON_LABELS = {
  within_threshold: '无需调仓（偏离低于阈值）',
  missing_quote: '缺少可用行情，暂不操作',
  below_lot_size: '调整量不足一手，暂不操作',
  'Cash floor target maintained': '现金底线已保留',
  'Manual-only ETF rotation signal': '手动 ETF 轮动信号',
  rebalance_debounce_active: '权重变化低于阈值，沿用上次建议',
};

const formatBackendBanner = (value) => {
  const text = String(value || '').trim();
  if (!text) return MANUAL_BANNER_ZH;
  if (/Manual trade plan|No broker API|auto-ordering/i.test(text)) return MANUAL_BANNER_ZH;
  return text;
};

const formatTradeReason = (value) => {
  const text = String(value || '').trim();
  if (!text) return '—';
  if (STATIC_REASON_LABELS[text]) return STATIC_REASON_LABELS[text];
  const deltaMatch = text.match(/^delta_([+-]?\d+(?:\.\d+)?)$/);
  if (deltaMatch) {
    const delta = Number(deltaMatch[1]);
    if (Number.isFinite(delta)) return `目标偏离 ${(delta * 100).toFixed(2)}%`;
  }
  return text;
};

const formatRiskReason = (value) => {
  const text = String(value || '').trim();
  if (!text) return '—';
  if (STATIC_REASON_LABELS[text]) return STATIC_REASON_LABELS[text];

  let match = text.match(/^Cash floor: raised cash from ([\d.]+%) to ([\d.]+%)\.$/);
  if (match) return `现金底线：现金仓位从 ${match[1]} 提高到 ${match[2]}。`;

  match = text.match(/^Commodity\/resource bucket cap: reduced combined bucket from ([\d.]+%) to ([\d.]+%)\.$/);
  if (match) return `商品/资源类仓位上限：合计仓位从 ${match[1]} 降至 ${match[2]}。`;

  match = text.match(/^Single ETF cap for ([^:]+): reduced from ([\d.]+%) to ([\d.]+%)\.$/);
  if (match) return `单只 ETF 上限：${match[1]} 从 ${match[2]} 降至 ${match[3]}。`;

  match = text.match(/^Premium veto for ([^:]+): premium ([\d.]+%) exceeds ([\d.]+%); target increase capped at current weight\.$/);
  if (match) return `溢价风控：${match[1]} 溢价 ${match[2]} 超过 ${match[3]}，目标增仓限制在当前权重。`;

  match = text.match(/^Drawdown cut: portfolio drawdown ([\d.]+%) exceeds ([\d.]+%); gross ETF exposure reduced from ([\d.]+%) to ([\d.]+%)\.$/);
  if (match) return `回撤风控：组合回撤 ${match[1]} 超过 ${match[2]}，ETF 总敞口从 ${match[3]} 降至 ${match[4]}。`;

  return text;
};

const formatQuoteSource = (value) => {
  const text = String(value || '').trim();
  if (!text) return null;
  if (text === 'fake-live') return '测试实时行情';
  if (/^historical?_fallback/i.test(text)) return '历史行情回退';
  if (/^synthetic/i.test(text)) return '模拟行情';
  if (/^realtime_manager$/i.test(text)) return '实时行情服务';
  if (/^yahoo$/i.test(text)) return '雅虎行情';
  if (/^commodity$/i.test(text)) return '商品行情源';
  if (/^us_stock$/i.test(text)) return '美股行情源';
  return text;
};

const formatPercent = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `${(number * 100).toFixed(2)}%`;
};

const formatCurrency = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `¥${number.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
};

const formatPrice = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return number.toLocaleString('zh-CN', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
};

const formatIsoToLocal = (value) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('zh-CN', { hour12: false });
};

const buildWeightRows = (plan) => {
  const current = plan?.current_weights || {};
  const target = plan?.target_weights || {};
  const adjusted = plan?.adjusted_weights || {};
  const quotes = plan?.quote_snapshot || {};
  const codes = Array.from(new Set([...Object.keys(current), ...Object.keys(target), ...Object.keys(adjusted), ...Object.keys(quotes)]));
  const orderedCodes = [...codes.filter((code) => code !== 'CASH').sort(), ...codes.filter((code) => code === 'CASH')];
  return orderedCodes.map((code) => {
    const quote = quotes[code] || {};
    return {
      key: code,
      code,
      name: ETF_NAMES[code] || quote.name || code,
      current: current[code],
      target: target[code],
      adjusted: adjusted[code],
      currentPrice: quote.current_price,
      quoteSource: formatQuoteSource(quote.source),
      quoteTimestamp: quote.timestamp || quote.date,
    };
  });
};

/**
 * Resolves the rendering shape regardless of which endpoint produced the
 * response — /live-target wraps the plan inside `data.plan`, /daily-signal
 * returns the plan directly under `data`.
 */
const unwrapPlanEnvelope = (response, { endpoint }) => {
  const data = response?.data || response || null;
  if (!data) return { plan: null, meta: null };
  if (endpoint === 'live-target') {
    return {
      plan: data.plan || null,
      meta: {
        refreshedAt: data.refreshed_at || null,
        quoteSource: data.quote_source || data.plan?.quote_source || null,
        debounced: Boolean(data.debounced),
        debounceMaxDelta: data.debounce_max_delta ?? null,
        reasons: Array.isArray(data.reasons) ? data.reasons : [],
      },
    };
  }
  return {
    plan: data,
    meta: {
      refreshedAt: null,
      quoteSource: data.quote_source || null,
      debounced: false,
      debounceMaxDelta: null,
      reasons: [],
    },
  };
};

const SourceHealthBadges = ({ entries }) => {
  if (!Array.isArray(entries) || entries.length === 0) return null;
  return (
    <Space size={[8, 8]} wrap data-testid="etf-source-health-row">
      {entries.map((entry) => {
        const status = entry?.status || 'missing';
        const meta = SOURCE_STATUS_META[status] || SOURCE_STATUS_META.missing;
        const asOf = formatIsoToLocal(entry?.as_of);
        return (
          <Tooltip
            key={entry?.source_id || entry?.display_name}
            title={
              <>
                <div>状态：{meta.label}</div>
                {asOf ? <div>采样时间：{asOf}</div> : null}
                {entry?.reason ? <div>原因：{entry.reason}</div> : null}
              </>
            }
          >
            <Tag color={meta.color} icon={meta.icon}>
              {entry?.display_name || entry?.source_id || '数据源'}：{meta.label}
            </Tag>
          </Tooltip>
        );
      })}
    </Space>
  );
};

const EtfRotationDashboard = () => {
  const [loading, setLoading] = useState(true);
  const [forceLoading, setForceLoading] = useState(false);
  const [plan, setPlan] = useState(null);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [endpoint, setEndpoint] = useState('live-target'); // 'live-target' | 'daily-signal'
  const [lastFetchedAt, setLastFetchedAt] = useState(null);
  const pollTimerRef = useRef(null);

  const applyResponse = useCallback((response, endpointUsed) => {
    const { plan: nextPlan, meta: nextMeta } = unwrapPlanEnvelope(response, { endpoint: endpointUsed });
    if (nextPlan) {
      setPlan(nextPlan);
      setMeta(nextMeta);
      setError(null);
    }
    setLastFetchedAt(new Date().toISOString());
  }, []);

  const fetchLiveTarget = useCallback(async ({ trigger = false } = {}) => {
    try {
      const response = await getEtfRotationLiveTarget({ triggerRefresh: trigger });
      applyResponse(response, 'live-target');
      setEndpoint('live-target');
      return true;
    } catch (err) {
      // 503 is normal when the service hasn't built a plan yet — bootstrap one.
      const status = err?.response?.status || err?.status;
      if (status === 503) {
        try {
          const triggered = await getEtfRotationLiveTarget({ triggerRefresh: true });
          applyResponse(triggered, 'live-target');
          setEndpoint('live-target');
          return true;
        } catch (innerErr) {
          // fall through to legacy endpoint
          // eslint-disable-next-line no-console
          console.warn('live-target bootstrap failed, falling back to daily-signal', innerErr);
        }
      } else {
        // eslint-disable-next-line no-console
        console.warn('live-target unavailable, falling back to daily-signal', err);
      }
      return false;
    }
  }, [applyResponse]);

  const fetchDailySignalFallback = useCallback(async () => {
    const response = await getEtfRotationDailySignal({ quote_source: 'live', use_cache: true });
    applyResponse(response, 'daily-signal');
    setEndpoint('daily-signal');
  }, [applyResponse]);

  const refreshNow = useCallback(async () => {
    setForceLoading(true);
    setError(null);
    try {
      if (endpoint === 'live-target') {
        const response = await postEtfRotationRefresh({ useCache: false });
        applyResponse(response, 'live-target');
      } else {
        const response = await getEtfRotationDailySignal({ quote_source: 'live', use_cache: false });
        applyResponse(response, 'daily-signal');
      }
    } catch (err) {
      setError(err?.userMessage || err?.message || '刷新失败');
    } finally {
      setForceLoading(false);
    }
  }, [endpoint, applyResponse]);

  // Initial load + polling
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!cancelled) setLoading(true);
      try {
        const ok = await fetchLiveTarget({ trigger: false });
        if (!ok && !cancelled) await fetchDailySignalFallback();
      } catch (err) {
        if (!cancelled) setError(err?.userMessage || err?.message || 'ETF轮动信号加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [fetchLiveTarget, fetchDailySignalFallback]);

  useEffect(() => {
    if (endpoint !== 'live-target') return undefined;
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = setInterval(() => {
      fetchLiveTarget({ trigger: false }).catch((err) => {
        // eslint-disable-next-line no-console
        console.warn('live-target poll failed', err);
      });
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [endpoint, fetchLiveTarget]);

  const weightRows = useMemo(() => buildWeightRows(plan), [plan]);
  const suggestions = Array.isArray(plan?.suggestions) ? plan.suggestions : [];
  const riskReasons = Array.isArray(plan?.risk_reasons) ? plan.risk_reasons : [];
  const liveStatus = plan?.live_quote_status || {};
  const sourceHealth = Array.isArray(plan?.source_health) ? plan.source_health : [];
  const quoteSourceCode = meta?.quoteSource || plan?.quote_source;
  const quoteModeLabel = QUOTE_SOURCE_LABELS[quoteSourceCode] || (
    plan?.quote_source === 'live'
      ? `实时行情 ${liveStatus.resolved ?? 0}/${liveStatus.requested ?? 0}`
      : plan?.quote_source === 'fallback_synthetic'
        ? '实时行情不可用 / 已回退截图种子'
        : '截图种子行情'
  );
  const refreshedAt = formatIsoToLocal(meta?.refreshedAt) || formatIsoToLocal(lastFetchedAt);

  const weightColumns = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 110 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '实时价', dataIndex: 'currentPrice', key: 'currentPrice', render: formatPrice },
    { title: '行情源', dataIndex: 'quoteSource', key: 'quoteSource', render: (value) => value ? <Tag color="blue">{value}</Tag> : <Text type="secondary">—</Text> },
    { title: '当前权重', dataIndex: 'current', key: 'current', render: formatPercent },
    { title: '策略目标', dataIndex: 'target', key: 'target', render: formatPercent },
    { title: '风控后目标', dataIndex: 'adjusted', key: 'adjusted', render: formatPercent },
  ];

  const suggestionColumns = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 110 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '动作',
      dataIndex: 'action',
      key: 'action',
      render: (action) => {
        const metaAction = ACTION_META[action] || ACTION_META.hold;
        return <Tag color={metaAction.color}>{metaAction.label}</Tag>;
      },
    },
    { title: '股数', dataIndex: 'shares', key: 'shares', render: (value) => Number(value || 0).toLocaleString('zh-CN') },
    { title: '估算金额', dataIndex: 'estimated_amount', key: 'estimated_amount', render: formatCurrency },
    { title: '原因', dataIndex: 'reason', key: 'reason', render: formatTradeReason },
  ];

  return (
    <div className="etf-rotation-dashboard" data-testid="etf-rotation-dashboard">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }} wrap>
              <Space>
                <SwapOutlined style={{ color: 'var(--accent-primary)' }} />
                <Title level={3} style={{ margin: 0 }}>ETF轮动调仓</Title>
                <Tag color={endpoint === 'live-target' ? 'green' : 'orange'} data-testid="etf-endpoint-tag">
                  {endpoint === 'live-target' ? '实时刷新模式' : '兼容模式（旧端点）'}
                </Tag>
              </Space>
              <Space>
                {meta?.debounced ? (
                  <Tooltip title={`权重变化低于阈值，沿用上次建议。max_delta=${meta.debounceMaxDelta}`}>
                    <Tag icon={<PauseCircleOutlined />} color="default">已防抖</Tag>
                  </Tooltip>
                ) : null}
                <Button
                  icon={<ReloadOutlined />}
                  onClick={refreshNow}
                  loading={forceLoading || loading}
                  data-testid="etf-force-refresh-button"
                >
                  强制刷新
                </Button>
              </Space>
            </Space>
            <Alert
              type="info"
              showIcon
              message={formatBackendBanner(plan?.banner)}
              description={`本页使用实时行情刷新当前持仓市值和权重；只展示目标权重和手动买卖建议，不连接券商、不自动下单。${liveStatus.error ? ` 行情错误：${liveStatus.error}` : ''}`}
              data-testid="etf-manual-only-banner"
            />
            {sourceHealth.length > 0 ? (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">数据源健康度（鼠标悬停看采样时间）</Text>
                <SourceHealthBadges entries={sourceHealth} />
              </Space>
            ) : null}
          </Space>
        </Card>

        {error ? <Alert type="error" showIcon message="ETF轮动信号加载失败" description={error} /> : null}

        {loading && !plan ? (
          <Card><Spin /> <Text type="secondary">正在加载 ETF 轮动信号...</Text></Card>
        ) : !plan ? (
          <Card><Empty description="暂无 ETF 轮动信号" /></Card>
        ) : (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={6}>
                <Card>
                  <Statistic title="组合资产" value={plan.total_asset || 0} precision={2} prefix="¥" />
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card>
                  <Statistic title="行情模式" value={quoteModeLabel} />
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card>
                  <Space direction="vertical" size={0}>
                    <Text type="secondary">最近刷新</Text>
                    <Text strong data-testid="etf-refreshed-at">{refreshedAt || '—'}</Text>
                  </Space>
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card>
                  <Space>
                    <SafetyCertificateOutlined style={{ color: 'var(--accent-success)' }} />
                    <Text strong>{plan.manual_only && plan.auto_ordering === false ? '手动执行 / 无自动下单' : '请复核执行模式'}</Text>
                  </Space>
                </Card>
              </Col>
            </Row>

            <Card title="权重对比" data-testid="etf-weight-table">
              <Table columns={weightColumns} dataSource={weightRows} pagination={false} size="small" />
            </Card>

            <Card title="手动交易建议" data-testid="etf-suggestion-table">
              <Table
                columns={suggestionColumns}
                dataSource={suggestions.map((item) => ({ ...item, key: item.code }))}
                pagination={false}
                size="small"
              />
            </Card>

            <Card title="风控原因" data-testid="etf-risk-reasons">
              {riskReasons.length === 0 ? (
                <Text type="secondary">暂无风控调整。</Text>
              ) : (
                <Space size={[8, 8]} wrap>
                  {riskReasons.map((reason, index) => <Tag key={`${reason}-${index}`}>{formatRiskReason(reason)}</Tag>)}
                </Space>
              )}
            </Card>
          </>
        )}
      </Space>
    </div>
  );
};

export default EtfRotationDashboard;
