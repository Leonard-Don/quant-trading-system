import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, Badge, Button, Card, Col, Collapse, Empty, message, Row, Space, Spin, Statistic, Switch, Table, Tag, Timeline, Tooltip, Typography,
} from 'antd';
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  LineChartOutlined,
  PauseCircleOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  StopOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';

import {
  getEtfRotationAnalytics,
  getEtfRotationAuditLog,
  getEtfRotationDailySignal,
  getEtfRotationLiveTarget,
  getEtfRotationPreferences,
  getPolicyRadarSignal,
  postEtfRotationPreferences,
  postEtfRotationRefresh,
  postEtfRotationReloadConfig,
} from '../services/api';

import lazyWithRetry from '../utils/lazyWithRetry';

// The attribution panel pulls in a Recharts <BarChart> + a fairly large
// markup tree; keep it out of the initial dashboard chunk so the toggle's
// default-OFF state never pays for code it doesn't render.
const EtfPolicyFactorAttributionPanel = lazyWithRetry(
  () => import('./EtfPolicyFactorAttributionPanel'),
);

// Walkforward panel is button-driven and collapsed by default — lazy
// import so its Recharts/Antd table tree stays out of the initial chunk.
const EtfWalkforwardPanel = lazyWithRetry(
  () => import('./EtfWalkforwardPanel'),
);

// Regime classifier tile — small + always-on, fetched once on mount via a
// deterministic backend endpoint. Lazy-loaded so the AntD Progress + Card
// tree it pulls in stays out of the initial dashboard chunk; the wrapper
// keeps the test-id "etf-regime-tile" available even before the chunk
// resolves so the existing Cypress/playwright selectors work.
const EtfRegimeTile = lazyWithRetry(
  () => import('./EtfRegimeTile'),
);

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

const REGIME_META = {
  bull: { color: 'success', label: '牛市 / 顺势', detail: '广义市场处于 200 日均线之上、波动率正常区间。' },
  correction: { color: 'warning', label: '调整 / 高位回撤', detail: '价格仍在 200 日均线之上但 60 日回撤 ≥ 5%。' },
  sideways: { color: 'processing', label: '盘整 / 波动放大', detail: '在 200 日均线附近横盘但波动率高于历史中位 1.5×。' },
  bear: { color: 'error', label: '熊市 / 趋势走弱', detail: '价格跌破 200 日均线，已开始降仓。' },
  crisis: { color: 'volcano', label: '危机 / 高波动深回撤', detail: '波动率 ≥ 2× 历史中位 或 60 日回撤 ≥ 15%。' },
  unknown: { color: 'default', label: '数据不足', detail: '历史数据不够长，暂不调整 gross_cap。' },
};

const MANUAL_BANNER_ZH = '手动调仓计划：请人工复核后执行；不连接券商接口，也不会自动下单。';

const POLL_INTERVAL_MS = 30_000;

// Policy data older than this is flagged as stale in the UI.
const POLICY_STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;

const POLICY_SIGNAL_META = {
  bullish: { color: 'red', label: '偏多' },
  bearish: { color: 'green', label: '偏空' },
  neutral: { color: 'default', label: '中性' },
};

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
  const overlays = plan?.overlays || {};
  const stopLossTriggered = plan?.stop_loss_triggered || {};
  const scoreBreakdown = plan?.score_breakdown || {};
  const manualOverrideStatus = plan?.manual_override_status || {};
  const codes = Array.from(new Set([...Object.keys(current), ...Object.keys(target), ...Object.keys(adjusted), ...Object.keys(quotes)]));
  const orderedCodes = [...codes.filter((code) => code !== 'CASH').sort(), ...codes.filter((code) => code === 'CASH')];
  return orderedCodes.map((code) => {
    const quote = quotes[code] || {};
    const overlay = overlays[code] || null;
    const stop = stopLossTriggered[code] || null;
    const breakdown = scoreBreakdown[code] || null;
    const overrideStatus = manualOverrideStatus[code] || null;
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
      premium: typeof quote.premium === 'number' ? quote.premium : null,
      estimatedNav: typeof quote.estimated_nav === 'number' ? quote.estimated_nav : null,
      overlay,
      stopLoss: stop,
      breakdown,
      manualOverride: overrideStatus,
    };
  });
};

const renderPriceWithBreakdown = (value, row) => {
  if (!Number.isFinite(Number(value))) return <Text type="secondary">—</Text>;
  const bd = row?.breakdown;
  if (!bd) return formatPrice(value);
  return (
    <Tooltip
      title={
        <Space direction="vertical" size={2}>
          {bd.ma20 !== undefined ? <div>MA20: {Number(bd.ma20).toFixed(3)}</div> : null}
          {bd.ma60 !== undefined ? <div>MA60: {Number(bd.ma60).toFixed(3)}</div> : null}
          {bd.ma200 !== null && bd.ma200 !== undefined ? (
            <div>
              MA200: {Number(bd.ma200).toFixed(3)}
              {bd.trend_long_strength !== null && bd.trend_long_strength !== undefined ? (
                <Text type={bd.trend_long_strength >= 0 ? 'success' : 'danger'}>
                  {` (${bd.trend_long_strength >= 0 ? '+' : ''}${(bd.trend_long_strength * 100).toFixed(2)}%)`}
                </Text>
              ) : null}
            </div>
          ) : <div>MA200: 数据不足</div>}
          <div>composite score: {Number(bd.score).toFixed(1)}</div>
          <div>　趋势 {Number(bd.trend_score).toFixed(1)} · 动量 {Number(bd.momentum_score).toFixed(1)} · 风险 {Number(bd.risk_score).toFixed(1)}</div>
        </Space>
      }
    >
      <span style={{ borderBottom: '1px dotted var(--color-text-tertiary, #888)', cursor: 'help' }}>
        {formatPrice(value)}
      </span>
    </Tooltip>
  );
};

const renderPremium = (value) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return <Text type="secondary">—</Text>;
  const pct = (value * 100).toFixed(2);
  let color = 'default';
  if (value >= 0.05) color = 'error';        // hard veto threshold
  else if (value >= 0.02) color = 'warning'; // qdii/commodity veto threshold
  else if (value <= -0.01) color = 'success';
  return <Tag color={color}>{value >= 0 ? '+' : ''}{pct}%</Tag>;
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
  const [reloadLoading, setReloadLoading] = useState(false);
  const [plan, setPlan] = useState(null);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [endpoint, setEndpoint] = useState('live-target'); // 'live-target' | 'daily-signal'
  const [lastFetchedAt, setLastFetchedAt] = useState(null);
  const [auditEntries, setAuditEntries] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [analytics, setAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [policySignal, setPolicySignal] = useState(null);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [policyLoaded, setPolicyLoaded] = useState(false);
  // Policy-factor toggle state. Optimistic flip on click; reconciled from
  // the daily-signal response (which always carries the effective
  // ``policy_signal_factor_enabled`` boolean) once the round-trip lands.
  const [policyToggleLoading, setPolicyToggleLoading] = useState(false);
  // Walkforward panel: lazy-loaded chunk + collapsed-by-default UX so the
  // dashboard's initial render doesn't pay for it. We track whether the
  // user has ever expanded it so the lazy import only fires on demand.
  const [walkforwardOpen, setWalkforwardOpen] = useState(false);
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

  const reloadConfig = useCallback(async () => {
    setReloadLoading(true);
    try {
      const response = await postEtfRotationReloadConfig({ refreshAfter: true });
      message.success('配置已重载，下次刷新生效');
      // Pick up the freshly-built plan that reload-config triggered.
      try {
        const latest = await getEtfRotationLiveTarget({ triggerRefresh: false });
        applyResponse(latest, 'live-target');
      } catch (innerErr) {
        // eslint-disable-next-line no-console
        console.warn('reload-config post-fetch failed', innerErr);
      }
      return response;
    } catch (err) {
      message.error(err?.userMessage || err?.message || '重载配置失败');
      throw err;
    } finally {
      setReloadLoading(false);
    }
  }, [applyResponse]);

  const fetchAuditLog = useCallback(async () => {
    setAuditLoading(true);
    try {
      const response = await getEtfRotationAuditLog({ limit: 40 });
      const entries = response?.data?.entries || [];
      setAuditEntries(entries.slice().reverse()); // newest first
    } catch (err) {
      message.error(err?.userMessage || err?.message || '审计日志加载失败');
    } finally {
      setAuditLoading(false);
    }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    setAnalyticsLoading(true);
    try {
      const response = await getEtfRotationAnalytics();
      setAnalytics(response?.data || null);
    } catch (err) {
      message.error(err?.userMessage || err?.message || 'Edge 度量加载失败');
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  const fetchPolicySignal = useCallback(async () => {
    setPolicyLoading(true);
    try {
      const response = await getPolicyRadarSignal();
      setPolicySignal(response?.data || null);
    } catch (err) {
      // Degrade silently: policy radar is informational only, never fail loud.
      // eslint-disable-next-line no-console
      console.warn('policy-radar signal fetch failed', err);
      setPolicySignal(null);
    } finally {
      setPolicyLoaded(true);
      setPolicyLoading(false);
    }
  }, []);

  // Persist the policy-factor preference and re-pull the daily signal so
  // the response (and the page) reflects the new effective state. The
  // server stamps ``policy_signal_factor_enabled`` on the plan, which
  // ``unwrapPlanEnvelope`` -> ``setPlan`` propagates to the toggle below.
  const togglePolicyFactor = useCallback(async (nextEnabled) => {
    setPolicyToggleLoading(true);
    try {
      await postEtfRotationPreferences({ policySignalFactorEnabled: nextEnabled });
      // Pull a fresh plan so the page sees the new effective bool + the
      // recomputed weights. Prefer live-target (the canonical endpoint
      // when the service is healthy); fall back to daily-signal when the
      // service hasn't bootstrapped yet.
      try {
        const refreshed = await getEtfRotationLiveTarget({ triggerRefresh: true });
        applyResponse(refreshed, 'live-target');
        setEndpoint('live-target');
      } catch (innerErr) {
        // eslint-disable-next-line no-console
        console.warn('live-target re-fetch after toggle failed; falling back', innerErr);
        const fallback = await getEtfRotationDailySignal({ quote_source: 'live', use_cache: false });
        applyResponse(fallback, 'daily-signal');
        setEndpoint('daily-signal');
      }
      message.success(
        nextEnabled ? '已启用政策信号因子（生效到下次刷新）' : '已关闭政策信号因子',
      );
    } catch (err) {
      message.error(err?.userMessage || err?.message || '政策因子开关保存失败');
    } finally {
      setPolicyToggleLoading(false);
    }
  }, [applyResponse]);

  // Bootstrap the toggle state on first render: pull the preference store
  // so we render the same "off vs on" the next daily-signal call will
  // resolve to. Failures degrade silently to "off, source=config".
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await getEtfRotationPreferences();
        if (cancelled) return;
        // No setState needed yet — the daily-signal response is what
        // drives the rendered toggle (single source of truth). We just
        // surface a console message when the preference disagrees with
        // the current rendered state, to flag mid-air collisions during
        // dev. In production this whole block is a no-op pre-warmer that
        // confirms the endpoint is reachable.
        const effective = response?.data?.effective?.policy_signal_factor_enabled;
        if (typeof effective !== 'boolean') {
          // eslint-disable-next-line no-console
          console.warn('preferences endpoint returned unexpected shape', response);
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('preferences pre-warm failed', err);
      }
    })();
    return () => { cancelled = true; };
  }, []);

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
  const premiumStatus = plan?.premium_monitor_status || null;
  const activeOverlays = plan?.overlays || {};
  const regime = plan?.regime || null;
  const ensemble = plan?.ensemble || null;
  const policyFactorSummary = plan?.policy_signal_factor || {};
  // Top-level shortcut is what the API stamps after the precedence
  // resolution (query > preference > config). When it's missing we fall
  // back to the summary block — which is what older API responses had.
  const policyFactorEnabled = typeof plan?.policy_signal_factor_enabled === 'boolean'
    ? plan.policy_signal_factor_enabled
    : Boolean(policyFactorSummary.enabled);
  const policyFactorSource = typeof policyFactorSummary.source === 'string'
    ? policyFactorSummary.source
    : null;
  // Aggregate per-ETF policy_adjustment entries so the Δ panel renders
  // exactly what the strategy is doing right now (instead of pulling
  // potentially-stale data from the audit log).
  const policyAdjustmentRows = useMemo(() => {
    const bd = plan?.score_breakdown || {};
    return Object.entries(bd)
      .map(([code, payload]) => {
        const meta = payload?.policy_adjustment;
        if (!meta || !meta.applied) return null;
        return { code, ...meta };
      })
      .filter(Boolean);
  }, [plan]);
  const quoteSourceCode = meta?.quoteSource || plan?.quote_source;
  const quoteModeLabel = QUOTE_SOURCE_LABELS[quoteSourceCode] || (
    plan?.quote_source === 'live'
      ? `实时行情 ${liveStatus.resolved ?? 0}/${liveStatus.requested ?? 0}`
      : plan?.quote_source === 'fallback_synthetic'
        ? '实时行情不可用 / 已回退截图种子'
        : '截图种子行情'
  );
  const refreshedAt = formatIsoToLocal(meta?.refreshedAt) || formatIsoToLocal(lastFetchedAt);

  const topPolicySignals = useMemo(() => {
    const industrySignals = policySignal?.industry_signals;
    if (!industrySignals || typeof industrySignals !== 'object') return [];
    return Object.entries(industrySignals)
      .filter(([, info]) => info && typeof info === 'object')
      .sort((a, b) => Math.abs(Number(b[1]?.avg_impact) || 0) - Math.abs(Number(a[1]?.avg_impact) || 0))
      .slice(0, 3);
  }, [policySignal]);

  const policyLastRefresh = policySignal?.last_refresh || null;
  const policyLastRefreshLocal = formatIsoToLocal(policyLastRefresh);
  const policyIsStale = useMemo(() => {
    if (!policyLastRefresh) return false;
    const date = new Date(policyLastRefresh);
    if (Number.isNaN(date.getTime())) return false;
    return Date.now() - date.getTime() > POLICY_STALE_THRESHOLD_MS;
  }, [policyLastRefresh]);
  const policyAvailable = Boolean(policySignal?.available) && topPolicySignals.length > 0;

  const weightColumns = [
    {
      title: '代码',
      dataIndex: 'code',
      key: 'code',
      width: 130,
      render: (code, row) => {
        const tags = [];
        if (row?.stopLoss) {
          tags.push(
            <Tooltip
              key="stop-loss"
              title={
                <>
                  <div>触发 per-position 止损</div>
                  <div>成本 ¥{row.stopLoss.cost_price?.toFixed(3)} / 当前 ¥{row.stopLoss.current_price?.toFixed(3)}</div>
                  <div>浮亏 {(row.stopLoss.loss_pct * 100).toFixed(2)}%</div>
                  <div>阈值 {(row.stopLoss.threshold * 100).toFixed(0)}%</div>
                </>
              }
            >
              <Tag icon={<StopOutlined />} color="error" data-testid={`etf-stop-loss-${code}`}>
                止损
              </Tag>
            </Tooltip>
          );
        }
        if (row?.manualOverride?.invalidated) {
          const o = row.manualOverride;
          tags.push(
            <Tooltip
              key="override-invalidated"
              title={
                <>
                  <div>你的 override 已破</div>
                  {o.thesis ? <div>当时判断: {o.thesis}</div> : null}
                  <div>失效线 ¥{Number(o.invalidation_price).toFixed(3)}</div>
                  {Number.isFinite(o.current_price) ? (
                    <div>当前 ¥{Number(o.current_price).toFixed(3)}</div>
                  ) : null}
                  {o.set_at ? <div>设置于 {o.set_at}</div> : null}
                  {o.note ? <div>备注: {o.note}</div> : null}
                </>
              }
            >
              <Tag color="volcano" data-testid={`etf-override-invalidated-${code}`}>
                override已破
              </Tag>
            </Tooltip>
          );
        } else if (row?.manualOverride?.invalidation_price) {
          const o = row.manualOverride;
          tags.push(
            <Tooltip
              key="override-active"
              title={
                <>
                  <div>你的 override 仍然有效</div>
                  {o.thesis ? <div>判断: {o.thesis}</div> : null}
                  <div>失效线 ¥{Number(o.invalidation_price).toFixed(3)}</div>
                  {Number.isFinite(o.current_price) ? (
                    <div>当前 ¥{Number(o.current_price).toFixed(3)}</div>
                  ) : null}
                  {o.set_at ? <div>设置于 {o.set_at}</div> : null}
                </>
              }
            >
              <Tag color="gold" data-testid={`etf-override-active-${code}`}>
                override
              </Tag>
            </Tooltip>
          );
        }
        if (tags.length === 0) return code;
        return (
          <Space size={4} wrap>
            <span>{code}</span>
            {tags}
          </Space>
        );
      },
    },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '实时价', dataIndex: 'currentPrice', key: 'currentPrice', render: renderPriceWithBreakdown },
    {
      title: '估算净值',
      dataIndex: 'estimatedNav',
      key: 'estimatedNav',
      render: (value) => Number.isFinite(value) ? formatPrice(value) : <Text type="secondary">—</Text>,
    },
    {
      title: '溢价',
      dataIndex: 'premium',
      key: 'premium',
      render: renderPremium,
    },
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
    {
      title: '挂单价（推荐 / 三档）',
      dataIndex: 'pricing',
      key: 'pricing',
      render: (pricing, row) => {
        if (!pricing || row?.action === 'hold') {
          return <Text type="secondary">—</Text>;
        }
        const fmt = (v) => Number.isFinite(Number(v)) ? `¥${Number(v).toFixed(3)}` : '—';
        const recColor = row.action === 'sell' ? 'green' : 'red';
        const levels = pricing.limit_prices || {};
        return (
          <Tooltip
            title={
              <Space direction="vertical" size={2}>
                <div><strong>三档限价</strong>（最小单位 {fmt(pricing.tick_size)}）</div>
                <div>积极：{fmt(levels.aggressive)} {row.action === 'sell' ? '（成交快，价低）' : '（成交快，价高）'}</div>
                <div>中性：{fmt(levels.neutral)}（约市价）</div>
                <div>保守：{fmt(levels.passive)} {row.action === 'sell' ? '（挂卖一上方等更好价格）' : '（挂买一下方等更好价格）'}</div>
                <div style={{ marginTop: 4 }}><strong>分批：</strong>{pricing.batches} 笔 × {(pricing.shares_per_batch || []).map(n => Number(n).toLocaleString('zh-CN')).join(' / ')} 股</div>
                <div><strong>建议时段：</strong></div>
                {(pricing.preferred_windows || []).map((w, i) => <div key={i}>· {w}</div>)}
              </Space>
            }
          >
            <Space direction="vertical" size={1}>
              <Tag color={recColor} data-testid={`etf-pricing-rec-${row.code}`}>
                {pricing.recommended_level === 'aggressive' ? '积极' : pricing.recommended_level === 'passive' ? '保守' : '中性'} {fmt(pricing.recommended_price)}
              </Tag>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {fmt(levels.aggressive)} / {fmt(levels.neutral)} / {fmt(levels.passive)}
              </Text>
              {pricing.batches > 1 ? (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  分 {pricing.batches} 笔
                </Text>
              ) : null}
            </Space>
          </Tooltip>
        );
      },
    },
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
                <Tooltip title="重新读取 ~/.config/etf-rotation/strategy.json，无需重启后端">
                  <Button
                    icon={<SettingOutlined />}
                    onClick={reloadConfig}
                    loading={reloadLoading}
                    data-testid="etf-reload-config-button"
                  >
                    重载配置
                  </Button>
                </Tooltip>
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
            {regime ? (
              <Space direction="vertical" size={4} style={{ width: '100%' }} data-testid="etf-regime-row">
                <Text type="secondary">市场状态（regime 探测，影响总仓位上限 + 评分权重）</Text>
                <Space size={[8, 4]} wrap>
                  <Tooltip
                    title={
                      <>
                        <div>{REGIME_META[regime.regime]?.detail || regime.regime}</div>
                        {regime.proxy_code ? <div>代理：{regime.proxy_code}</div> : null}
                        {regime.proxy_price !== null && regime.ma_long !== null ? (
                          <div>价格 {regime.proxy_price?.toFixed(3)} vs 200日均线 {regime.ma_long?.toFixed(3)}</div>
                        ) : null}
                        {regime.realized_vol !== null ? (
                          <div>60日年化波动 {(regime.realized_vol * 100).toFixed(1)}%
                            {regime.vol_median !== null
                              ? `（历史中位 ${(regime.vol_median * 100).toFixed(1)}%）`
                              : ''}
                          </div>
                        ) : null}
                        {regime.drawdown !== null ? (
                          <div>60日回撤 {(regime.drawdown * 100).toFixed(1)}%</div>
                        ) : null}
                        {(regime.reasons || []).map((reason, i) => (
                          <div key={i}>• {reason}</div>
                        ))}
                      </>
                    }
                  >
                    <Tag color={(REGIME_META[regime.regime] || REGIME_META.unknown).color} data-testid="etf-regime-tag">
                      {(REGIME_META[regime.regime] || REGIME_META.unknown).label}
                    </Tag>
                  </Tooltip>
                  <Tag>gross_cap × {regime.gross_cap_multiplier?.toFixed(2)}</Tag>
                  {regime.min_score_to_hold_offset > 0 ? (
                    <Tag color="orange">min_score +{regime.min_score_to_hold_offset.toFixed(0)}</Tag>
                  ) : null}
                  {regime.scoring_overrides_applied
                    && Object.keys(regime.scoring_overrides_applied).length > 0 ? (
                    <Tooltip
                      title={
                        <>
                          <div>该 regime 下激活的 scoring 覆盖：</div>
                          {Object.entries(regime.scoring_overrides_applied).map(([k, v]) => (
                            <div key={k}>• {k} = {typeof v === 'number' ? v.toFixed(2) : String(v)}</div>
                          ))}
                        </>
                      }
                    >
                      <Tag color="purple" data-testid="etf-regime-scoring-override">
                        scoring 覆盖 ×{Object.keys(regime.scoring_overrides_applied).length}
                      </Tag>
                    </Tooltip>
                  ) : null}
                  {ensemble?.enabled ? (
                    <Tooltip
                      title={
                        <>
                          <div>多策略融合：trend + mean-reversion</div>
                          <div>当前 regime: {ensemble.regime}</div>
                          <div>α_trend = {(ensemble.alpha_trend * 100).toFixed(0)}%</div>
                          <div>α_mr = {(ensemble.alpha_mean_reversion * 100).toFixed(0)}%</div>
                          {ensemble.regime_blend_weights ? (
                            <div style={{ marginTop: 4, fontSize: 11 }}>
                              全 regime 权重表：
                              {Object.entries(ensemble.regime_blend_weights).map(([k, v]) => (
                                <div key={k}>· {k}: trend {(v * 100).toFixed(0)}% / mr {((1 - v) * 100).toFixed(0)}%</div>
                              ))}
                            </div>
                          ) : null}
                        </>
                      }
                    >
                      <Tag color="geekblue" data-testid="etf-ensemble-tag">
                        融合 α={ensemble.alpha_trend?.toFixed(2)}
                      </Tag>
                    </Tooltip>
                  ) : null}
                </Space>
              </Space>
            ) : null}

            <Space
              direction="vertical"
              size={6}
              style={{ width: '100%' }}
              data-testid="etf-policy-factor-toggle-row"
            >
              <Space size={[8, 4]} wrap align="center">
                <Tooltip
                  title={(
                    <Space direction="vertical" size={2}>
                      <div>启用后：政策雷达对每个 ETF 行业的多空判断会以一个温和的权重因子参与目标权重计算。</div>
                      <div>默认调整幅度小（±10%），并且会被 ETF 单只仓位上限 / 现金底线等风控规则二次约束。</div>
                      <div>关闭后：纯趋势/动量/风险/溢价四因子，policy_radar 数据仅作为参考展示。</div>
                      <div>偏好持久化在 ~/.config/etf-rotation/ui_preferences.json，不影响 strategy.json。</div>
                    </Space>
                  )}
                >
                  <Space size={6} align="center">
                    <ThunderboltOutlined style={{ color: policyFactorEnabled ? 'var(--accent-success, #52c41a)' : 'var(--color-text-tertiary, #888)' }} />
                    <Text strong>政策信号因子</Text>
                  </Space>
                </Tooltip>
                <Switch
                  checked={policyFactorEnabled}
                  loading={policyToggleLoading}
                  onChange={togglePolicyFactor}
                  data-testid="etf-policy-factor-toggle"
                  checkedChildren="ON"
                  unCheckedChildren="OFF"
                />
                <Badge
                  status={policyFactorEnabled ? 'success' : 'default'}
                  text={(
                    <Text type={policyFactorEnabled ? 'success' : 'secondary'} data-testid="etf-policy-factor-state-tag">
                      {policyFactorEnabled ? '已启用' : '已关闭'}
                    </Text>
                  )}
                />
                {policyFactorSource ? (
                  <Tooltip
                    title={(
                      <>
                        <div>当前生效来源：</div>
                        <div>· query = 本次 URL 参数覆盖</div>
                        <div>· preference = 仪表盘开关（持久化）</div>
                        <div>· config = strategy.json 默认值</div>
                      </>
                    )}
                  >
                    <Tag color="blue">来源：{policyFactorSource}</Tag>
                  </Tooltip>
                ) : null}
                {policyFactorEnabled && policyFactorSummary.applied_count ? (
                  <Tag color="purple">当前应用 {policyFactorSummary.applied_count} 只</Tag>
                ) : null}
              </Space>
              {policyFactorEnabled ? (
                <Card
                  size="small"
                  data-testid="etf-policy-factor-delta-panel"
                  style={{ background: 'var(--color-fill-quaternary, rgba(0,0,0,0.02))' }}
                  title={(
                    <Space size={6}>
                      <Text strong>Δ vs factor-off</Text>
                      <Text type="secondary">（开启后相对关闭状态的权重调整）</Text>
                    </Space>
                  )}
                >
                  {policyAdjustmentRows.length === 0 ? (
                    <Text type="secondary">
                      暂无生效调整：policy_radar 信号要么是中性，要么没有 ETF 命中。
                    </Text>
                  ) : (
                    <ul
                      style={{ margin: 0, paddingLeft: 18 }}
                      data-testid="etf-policy-factor-delta-list"
                    >
                      {policyAdjustmentRows.map((row) => {
                        const deltaPct = Number(row.delta_weight ?? 0) * 100;
                        const sign = deltaPct >= 0 ? '+' : '';
                        const label = row.signal === 'bullish'
                          ? 'policy boost'
                          : row.signal === 'bearish'
                            ? 'policy penalty'
                            : 'policy adjustment';
                        return (
                          <li
                            key={`${row.code}-policy-delta`}
                            data-testid={`etf-policy-factor-delta-${row.code}`}
                          >
                            <Space size={6} wrap>
                              <Text strong>{ETF_NAMES[row.code] || row.code}</Text>
                              <Text type="secondary">（{row.code}）</Text>
                              <Tag color={row.signal === 'bullish' ? 'green' : row.signal === 'bearish' ? 'red' : 'default'}>
                                {sign}{deltaPct.toFixed(1)}% {label}
                              </Tag>
                              {row.industry ? (
                                <Text type="secondary">行业：{row.industry}</Text>
                              ) : null}
                            </Space>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </Card>
              ) : null}
              {policyFactorEnabled ? (
                <Suspense fallback={null}>
                  <EtfPolicyFactorAttributionPanel
                    visible={policyFactorEnabled}
                    periodDays={30}
                  />
                </Suspense>
              ) : null}
            </Space>

            {sourceHealth.length > 0 ? (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Text type="secondary">数据源健康度（鼠标悬停看采样时间）</Text>
                <SourceHealthBadges entries={sourceHealth} />
              </Space>
            ) : null}
            {premiumStatus ? (
              <Space direction="vertical" size={4} style={{ width: '100%' }} data-testid="etf-premium-monitor-status">
                <Text type="secondary">
                  溢价监控（每 60s 拉取东财估值，最近运行：
                  {formatIsoToLocal(premiumStatus.last_run_at) || '—'}）
                </Text>
                <Space size={[8, 4]} wrap>
                  {(premiumStatus.watched_codes || []).map((code) => {
                    const outcome = (premiumStatus.last_outcome || {})[code] || 'pending';
                    const overlay = activeOverlays[code];
                    const color = outcome === 'ok' ? 'success' : 'default';
                    const label =
                      outcome === 'ok' ? '已更新'
                      : outcome === 'fetch_error' ? '网络错误'
                      : outcome === 'parse_failed' ? '解析失败'
                      : outcome === 'pending' ? '等待中'
                      : outcome;
                    const premiumStr =
                      overlay && typeof overlay.premium === 'number'
                        ? ` ${overlay.premium >= 0 ? '+' : ''}${(overlay.premium * 100).toFixed(2)}%`
                        : '';
                    return (
                      <Tag key={code} color={color}>
                        {code}: {label}{premiumStr}
                      </Tag>
                    );
                  })}
                </Space>
              </Space>
            ) : null}
          </Space>
        </Card>

        {error ? <Alert type="error" showIcon message="ETF轮动信号加载失败" description={error} /> : null}

        {plan?.stop_loss_triggered && Object.keys(plan.stop_loss_triggered).length > 0 ? (
          <Alert
            type="error"
            showIcon
            icon={<AlertOutlined />}
            data-testid="etf-stop-loss-alert"
            message="触发 per-position 止损"
            description={
              <Space direction="vertical" size={4}>
                {Object.entries(plan.stop_loss_triggered).map(([code, info]) => (
                  <Text key={code}>
                    {ETF_NAMES[code] || code}（{code}）浮亏
                    <Text strong type="danger">{` ${(info.loss_pct * 100).toFixed(2)}% `}</Text>
                    达到阈值 {(info.threshold * 100).toFixed(0)}%，
                    策略已将目标权重强制设为 0；建议人工复核后清仓。
                  </Text>
                ))}
              </Space>
            }
          />
        ) : null}

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

            <Suspense fallback={<Card data-testid="etf-regime-tile"><Spin /></Card>}>
              <EtfRegimeTile lookbackDays={90} />
            </Suspense>

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

            <Collapse
              data-testid="etf-edge-analytics-collapse"
              onChange={(keys) => {
                const arr = Array.isArray(keys) ? keys : [keys];
                if (arr.includes('edge') && !analytics && !analyticsLoading) fetchAnalytics();
              }}
              items={[{
                key: 'edge',
                label: (
                  <Space>
                    <LineChartOutlined />
                    <Text strong>策略 Edge 度量（IC + 命中率）</Text>
                    {analytics ? (
                      <Tag color="default">{analytics.n_audit_entries} 条历史</Tag>
                    ) : null}
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Space size={[8, 4]} wrap>
                      <Button size="small" onClick={fetchAnalytics} loading={analyticsLoading}>重新计算</Button>
                      <Text type="secondary">
                        IC ≥ 0.05 = 有可测量 alpha；命中率 ≥ 55% = 信号方向准确度高。
                        审计样本不足时显示为 —。
                      </Text>
                    </Space>
                    {!analytics ? (
                      <Empty description={analyticsLoading ? '计算中...' : '点击重新计算载入'} />
                    ) : (
                      <Row gutter={[16, 16]}>
                        {Object.entries(analytics.horizons || {}).map(([key, h]) => {
                          const ic = h?.information_coefficient;
                          const hr = h?.hit_rate;
                          const hmin = h?.horizon_minutes;
                          const horizonLabel =
                            hmin >= 1440 ? `${(hmin / 1440).toFixed(0)} 日`
                            : hmin >= 60 ? `${(hmin / 60).toFixed(0)} 小时`
                            : `${hmin} 分钟`;
                          const formatPct = (v) =>
                            typeof v === 'number' && Number.isFinite(v)
                              ? `${(v * 100).toFixed(1)}%`
                              : '—';
                          const formatIC = (v) =>
                            typeof v === 'number' && Number.isFinite(v) ? v.toFixed(3) : '—';
                          const icColor =
                            typeof ic === 'number' && Number.isFinite(ic)
                              ? ic > 0.05 ? '#52c41a' : ic > 0 ? '#faad14' : '#ff4d4f'
                              : undefined;
                          return (
                            <Col xs={24} md={8} key={key}>
                              <Card size="small" title={`前瞻 ${horizonLabel}`}>
                                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                  <Space size={[8, 4]} wrap>
                                    <Statistic
                                      title="IC"
                                      value={formatIC(ic)}
                                      valueStyle={icColor ? { color: icColor } : undefined}
                                    />
                                    <Statistic title="命中率" value={formatPct(hr)} />
                                    <Statistic title="样本" value={h?.n_pairs ?? 0} />
                                  </Space>
                                  {h?.per_code && Object.keys(h.per_code).length > 0 ? (
                                    <Space size={[6, 4]} wrap>
                                      {Object.entries(h.per_code).map(([code, m]) => {
                                        const codeIC = m?.ic;
                                        const codeIcColor =
                                          typeof codeIC === 'number' && Number.isFinite(codeIC)
                                            ? codeIC > 0.05 ? 'success' : codeIC > 0 ? 'warning' : 'error'
                                            : 'default';
                                        return (
                                          <Tooltip
                                            key={code}
                                            title={
                                              <>
                                                <div>样本 {m.n_pairs}</div>
                                                <div>IC {formatIC(codeIC)}</div>
                                                <div>命中率 {formatPct(m.hit_rate)}</div>
                                              </>
                                            }
                                          >
                                            <Tag color={codeIcColor}>
                                              {code} IC={formatIC(codeIC)}
                                            </Tag>
                                          </Tooltip>
                                        );
                                      })}
                                    </Space>
                                  ) : null}
                                </Space>
                              </Card>
                            </Col>
                          );
                        })}
                      </Row>
                    )}
                  </Space>
                ),
              }]}
            />

            <Collapse
              data-testid="etf-policy-signals-panel"
              onChange={(keys) => {
                const arr = Array.isArray(keys) ? keys : [keys];
                if (arr.includes('policy') && !policyLoaded && !policyLoading) fetchPolicySignal();
              }}
              items={[{
                key: 'policy',
                label: (
                  <Space>
                    <RadarChartOutlined />
                    <Text strong>政策信号（policy_radar 最新行业影响）</Text>
                    {policyLoaded && policyAvailable ? (
                      <Tag color="default">Top {topPolicySignals.length}</Tag>
                    ) : null}
                    {policyLoaded && policyIsStale ? (
                      <Tooltip title={`政策数据最近一次刷新已超过 24 小时（${policyLastRefreshLocal || '时间未知'}）`}>
                        <Tag
                          color="warning"
                          icon={<WarningOutlined />}
                          data-testid="etf-policy-signals-stale-warning"
                        >
                          已过期
                        </Tag>
                      </Tooltip>
                    ) : null}
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Space size={[8, 4]} wrap>
                      <Button size="small" onClick={fetchPolicySignal} loading={policyLoading}>重新加载</Button>
                      <Text type="secondary">
                        {policyLastRefreshLocal
                          ? `政策数据更新时间：${policyLastRefreshLocal}`
                          : '政策数据更新时间：—'}
                      </Text>
                      <Text type="secondary">
                        {policyFactorEnabled
                          ? `政策因子已启用：映射到 ETF 的行业信号会以温和权重因子参与目标权重计算；当前应用 ${policyFactorSummary.applied_count || 0} 只。`
                          : '当前策略未启用政策因子；这里仅供参考，不参与 ETF 轮动目标权重计算。'}
                      </Text>
                    </Space>
                    {policyLoading && !policyLoaded ? (
                      <Spin />
                    ) : !policyAvailable ? (
                      <Empty
                        description="政策数据未就绪。请确认 alt-data 调度器已启动并完成首次抓取。"
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                      />
                    ) : (
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        {topPolicySignals.map(([industry, info]) => {
                          const signalKey = info?.signal || 'neutral';
                          const palette = POLICY_SIGNAL_META[signalKey] || POLICY_SIGNAL_META.neutral;
                          const avgImpact = Number(info?.avg_impact);
                          const impactText = Number.isFinite(avgImpact) ? avgImpact.toFixed(2) : '—';
                          const mentions = info?.mentions ?? 0;
                          return (
                            <Space
                              key={industry}
                              size={[8, 4]}
                              wrap
                              data-testid={`etf-policy-signal-row-${industry}`}
                            >
                              <Text strong>{industry}</Text>
                              <Tag color={palette.color}>{palette.label}</Tag>
                              <Text type="secondary">
                                平均影响 {avgImpact >= 0 && Number.isFinite(avgImpact) ? '+' : ''}{impactText}
                              </Text>
                              <Text type="secondary">· 提及 {mentions}</Text>
                            </Space>
                          );
                        })}
                      </Space>
                    )}
                  </Space>
                ),
              }]}
            />

            <Collapse
              data-testid="etf-audit-log-collapse"
              onChange={(keys) => {
                if (Array.isArray(keys) ? keys.includes('audit') : keys === 'audit') {
                  if (auditEntries.length === 0 && !auditLoading) fetchAuditLog();
                }
              }}
              items={[{
                key: 'audit',
                label: (
                  <Space>
                    <HistoryOutlined />
                    <Text strong>信号历史（最近 40 次刷新）</Text>
                  </Space>
                ),
                children: (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Space>
                      <Button size="small" onClick={fetchAuditLog} loading={auditLoading}>重新加载</Button>
                      <Text type="secondary">读自 ~/.config/etf-rotation/audit.jsonl</Text>
                    </Space>
                    {auditEntries.length === 0 && !auditLoading ? (
                      <Empty description="暂无审计记录" />
                    ) : (
                      <Timeline
                        items={auditEntries.slice(0, 40).map((entry) => {
                          const ts = formatIsoToLocal(entry.run_at) || entry.run_at;
                          const adj = entry.adjusted_weights || {};
                          const cash = adj.CASH;
                          const non_zero = Object.entries(adj).filter(([k, v]) => k !== 'CASH' && Number(v) > 0.005);
                          const policyFactor = entry.policy_signal_factor || null;
                          const scoreBreakdown = entry.score_breakdown || {};
                          // Collect per-ETF policy adjustments where applied=true.
                          // Each row reads: "新能源汽车 ETF: -8% policy bearish".
                          const policyAdjustments = Object.entries(scoreBreakdown)
                            .map(([code, payload]) => {
                              const meta = payload?.policy_adjustment;
                              if (!meta || !meta.applied) return null;
                              return { code, ...meta };
                            })
                            .filter(Boolean);
                          return {
                            key: entry.run_at,
                            color: String(entry.quote_source || '').includes('debounced') ? 'gray' : 'blue',
                            children: (
                              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                <Space>
                                  <Text strong>{ts}</Text>
                                  <Tag>{entry.quote_source || '-'}</Tag>
                                  {typeof entry.total_asset === 'number'
                                    ? <Text type="secondary">¥{Number(entry.total_asset).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}</Text>
                                    : null}
                                  {policyFactor && policyFactor.enabled
                                    ? (
                                      <Tag color="purple" data-testid="etf-audit-policy-factor-tag">
                                        政策因子 ON
                                        {policyFactor.applied_count
                                          ? ` · ${policyFactor.applied_count} 只`
                                          : ''}
                                      </Tag>
                                    )
                                    : null}
                                </Space>
                                <Space size={[6, 4]} wrap>
                                  {non_zero.map(([code, w]) => (
                                    <Tag key={code} color="blue">{code} {(Number(w) * 100).toFixed(1)}%</Tag>
                                  ))}
                                  {typeof cash === 'number'
                                    ? <Tag color="default">CASH {(cash * 100).toFixed(1)}%</Tag>
                                    : null}
                                </Space>
                                {policyAdjustments.length > 0 ? (
                                  <Space
                                    size={[6, 4]}
                                    wrap
                                    data-testid="etf-audit-policy-adjustments"
                                  >
                                    {policyAdjustments.map((row) => {
                                      const deltaPct = Number(row.delta_weight ?? 0) * 100;
                                      const sign = deltaPct >= 0 ? '+' : '';
                                      const color = row.signal === 'bullish'
                                        ? 'green'
                                        : (row.signal === 'bearish' ? 'red' : 'default');
                                      return (
                                        <Tag
                                          key={`${row.code}-policy`}
                                          color={color}
                                          title={`industry=${row.industry}, avg_impact=${Number(row.avg_impact || 0).toFixed(3)}`}
                                        >
                                          {row.code} {sign}{deltaPct.toFixed(1)}% policy {row.signal}
                                        </Tag>
                                      );
                                    })}
                                  </Space>
                                ) : null}
                              </Space>
                            ),
                          };
                        })}
                      />
                    )}
                  </Space>
                ),
              }]}
            />

            <Collapse
              data-testid="etf-walkforward-collapse"
              onChange={(keys) => {
                const arr = Array.isArray(keys) ? keys : [keys];
                setWalkforwardOpen(arr.includes('walkforward'));
              }}
              items={[{
                key: 'walkforward',
                label: (
                  <Space>
                    <ExperimentOutlined />
                    <Text strong>历史回测 (Walkforward) · 多窗口稳定性</Text>
                    <Tag color="default" data-testid="etf-walkforward-scope-tag">
                      回放历史价格 · 不同于上方因子归因
                    </Tag>
                  </Space>
                ),
                children: walkforwardOpen ? (
                  <Suspense fallback={<Spin data-testid="etf-walkforward-lazy-fallback" />}>
                    <EtfWalkforwardPanel />
                  </Suspense>
                ) : null,
              }]}
            />
          </>
        )}
      </Space>
    </div>
  );
};

export default EtfRotationDashboard;
