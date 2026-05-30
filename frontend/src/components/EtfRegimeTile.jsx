import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ExperimentOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';

import { getEtfRotationRegimeRecommendation } from '../services/api';

const { Text, Title } = Typography;

// Six regime labels mapped to AntD Tag colours + a one-line explanation. The
// risk gradient is: green (calm trending) → blue (calm choppy) → gold/orange
// (volatile or correction-prone) → red/volcano (bear). Defaults to "data
// insufficient" for the `unknown` label so the empty state is recognisable.
const REGIME_META = {
  trending_low_vol: {
    color: 'success',
    label: '上行低波动',
    detail: '价格趋势清晰且波动率正常。历史分段对照中，均值回归策略在趋势段表现更好。',
    risk: 'low',
  },
  trending_high_vol: {
    color: 'processing',
    label: '上行高波动',
    detail: '趋势存在但波动率抬升。轮动策略对市场状态切换更稳，建议适度降低总仓位上限。',
    risk: 'medium',
  },
  choppy_low_vol: {
    color: 'blue',
    label: '盘整低波动',
    detail: '趋势拟合度较低、波动率正常。历史分段对照中，轮动策略在盘整段表现更好。',
    risk: 'low',
  },
  choppy_high_vol: {
    color: 'gold',
    label: '盘整高波动',
    detail: '同时盘整和高波动。单一策略优势较弱，建议使用混合策略分散市场状态风险。',
    risk: 'medium',
  },
  bear_high_vol: {
    color: 'volcano',
    label: '熊市高波动',
    detail: '下行 + 高波动 — 历史上 long-only 系统化策略在该 regime 通常失血，建议现金为主。',
    risk: 'high',
  },
  bear_low_vol: {
    color: 'error',
    label: '熊市低波动',
    detail: '有序下行。均值回归策略在中性或弱跌环境中仍可能有小幅优势，但需要降仓位运行。',
    risk: 'high',
  },
  unknown: {
    color: 'default',
    label: '数据不足',
    detail: '历史数据不足以分类（需要 ≥ ~60 个交易日）。保持当前策略不变。',
    risk: 'unknown',
  },
};

const STRATEGY_LABELS = {
  rotation: '轮动策略',
  mean_reversion: '均值回归策略',
  blend: '混合策略',
  cash: '现金/等待',
  unchanged: '保持当前策略',
};

const FEATURE_META = {
  trend_r2: {
    label: '趋势拟合度 R²',
    tooltip: '对数价格线性拟合的 R²；越大越接近直线趋势。',
    format: (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(3)),
  },
  trend_slope: {
    label: '趋势斜率',
    tooltip: '对数价格的每日变化率；负值表示下行。',
    format: (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(5)),
  },
  realized_vol: {
    label: '实现波动率',
    tooltip: '过去窗口的年化波动率；> 25% 通常视为高波动。',
    format: (v) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(1)}%`),
  },
  return_skew: {
    label: '收益偏度',
    tooltip: '日收益分布偏度；负值越大左尾越厚（容易发生急跌）。',
    format: (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2)),
  },
  drawdown_ratio: {
    label: '回撤/波动比',
    tooltip: '窗口内最大回撤除以年化波动率；高值表示低波动下的不寻常压力。',
    format: (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2)),
  },
  avg_pairwise_correlation: {
    label: '跨资产相关性',
    tooltip: '宇宙内 ETF 两两相关性的平均值；> 0.7 通常视为风险厌恶 / 同向化。',
    format: (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2)),
  },
};

const FEATURE_ORDER = [
  'trend_r2',
  'trend_slope',
  'realized_vol',
  'return_skew',
  'drawdown_ratio',
  'avg_pairwise_correlation',
];

const CONFIG_OVERRIDE_LABELS = {
  gross_cap: '总仓位上限',
  min_score_to_hold: '持有最低分',
  max_single_etf_weight: '单只 ETF 上限',
  cash_floor: '现金底线',
};

const RATIONALE_LABELS = {
  'Trending market with calm vol — empirical (commit a54b986) shows mean_reversion captured the trending half (+6.17% vs rotation +3.85%). Run mean_reversion at full gross_cap.':
    '趋势清晰且波动温和：历史分段对照显示，均值回归策略在趋势段表现更好。建议按完整总仓位上限运行均值回归策略。',
  "Trend exists but volatility is elevated — rotation handles regime shifts better than MR's grid orders. Trim gross_cap to 0.85 to soak up the extra noise.":
    '趋势仍在但波动率抬升：轮动策略对市场状态切换更稳。建议把总仓位上限降到 0.85，给噪声留出缓冲。',
  'Choppy market with calm vol — empirical (commit a54b986) shows rotation captured the choppy half (+5.48% vs MR +2.10%). Run rotation at full gross_cap.':
    '盘整且波动温和：历史分段对照显示，轮动策略在盘整段表现更好。建议按完整总仓位上限运行轮动策略。',
  'Choppy AND volatile — single-strategy edge is small; blend rotation and MR to diversify regime risk, and shave 15% off gross_cap to respect the elevated vol.':
    '盘整且高波动：单一策略优势较弱。建议混合轮动和均值回归，并把总仓位上限下调 15%，控制高波动风险。',
  'Falling market with high vol — historical evidence shows long-only systematic strategies bleed in this regime. Drop gross_cap to 0.20 (80% cash) and wait for vol to normalise.':
    '下跌且高波动：历史证据显示只做多系统策略在这种环境容易失血。建议把总仓位上限降到 0.20，保留约 80% 现金，等待波动回落。',
  'Orderly downtrend — MR still has a small positive edge in neutral/weakly negative regimes. Run mean_reversion at gross_cap 0.60 (40% cash buffer).':
    '有序下行：均值回归策略在中性或弱跌环境中仍可能有小幅优势。建议以 0.60 的总仓位上限运行，保留约 40% 现金缓冲。',
};

const formatStrategy = (name) => {
  if (!name) return '—';
  return STRATEGY_LABELS[name] || name;
};

const formatOverrides = (overrides) => {
  if (!overrides || Object.keys(overrides).length === 0) return null;
  return Object.entries(overrides)
    .map(([k, v]) => `${CONFIG_OVERRIDE_LABELS[k] || k}=${typeof v === 'number' ? v.toFixed(2) : String(v)}`)
    .join(', ');
};

const formatRegimeReason = (value) => {
  const text = String(value || '').trim();
  if (!text) return '—';

  let match = text.match(/^trend_slope ([^/]+)\/day <= ([^ ]+) \(bearish\)$/);
  if (match) return `趋势斜率 ${match[1]}/日 ≤ ${match[2]}，偏空`;

  match = text.match(/^trend_r2 ([^ ]+) >= ([^ ]+) \(trending\)$/);
  if (match) return `趋势拟合度 ${match[1]} ≥ ${match[2]}，趋势清晰`;

  match = text.match(/^trend_r2 ([^ ]+) >= 0\.80 \(very clean\)$/);
  if (match) return `趋势拟合度 ${match[1]} ≥ 0.80，趋势非常干净`;

  match = text.match(/^trend_r2 ([^ ]+) < ([^ ]+) \(choppy\)$/);
  if (match) return `趋势拟合度 ${match[1]} < ${match[2]}，偏盘整`;

  match = text.match(/^realised_vol ([^ ]+) >= ([^ ]+) \(high\)$/);
  if (match) return `实现波动率 ${match[1]} ≥ ${match[2]}，高波动`;

  match = text.match(/^realised_vol ([^ ]+) < ([^ ]+) \((calm|orderly)\)$/);
  if (match) return `实现波动率 ${match[1]} < ${match[2]}，${match[3] === 'orderly' ? '有序下行' : '波动温和'}`;

  match = text.match(/^return_skew ([^ ]+) <= ([^ ]+) \(crash-prone\)$/);
  if (match) return `收益偏度 ${match[1]} ≤ ${match[2]}，左尾风险较高`;

  match = text.match(/^avg pairwise corr ([^ ]+) >= ([^ ]+) \(risk-off\)$/);
  if (match) return `平均跨资产相关性 ${match[1]} ≥ ${match[2]}，风险偏好下降`;

  match = text.match(/^avg pairwise corr ([^ ]+) \(risk-on but herded\)$/);
  if (match) return `平均跨资产相关性 ${match[1]}，风险偏好仍在但同向化较强`;

  match = text.match(/^drawdown\/vol ([^ ]+) >= ([^ ]+)$/);
  if (match) return `回撤/波动比 ${match[1]} ≥ ${match[2]}`;

  return text;
};

const formatRecommendationRationale = (value) => {
  const text = String(value || '').trim();
  if (!text) return null;
  return RATIONALE_LABELS[text] || text;
};

const EtfRegimeTile = ({ lookbackDays = 90 }) => {
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await getEtfRotationRegimeRecommendation({ lookbackDays });
        if (cancelled) return;
        if (response && response.success) {
          setPayload(response.data);
        } else {
          setError('无法计算市场状态推荐。');
        }
      } catch (err) {
        if (!cancelled) {
          const detail = err?.response?.data?.detail || err?.message || '未知错误';
          setError(String(detail));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [lookbackDays, reloadKey]);

  const regime = payload?.regime;
  const recommendation = payload?.recommendation;
  const meta = useMemo(
    () => REGIME_META[regime?.regime_name] || REGIME_META.unknown,
    [regime?.regime_name],
  );

  const overrideText = formatOverrides(recommendation?.config_overrides);
  const strategyName = recommendation?.strategy_name || recommendation?.recommended_strategy;
  const recommendationRationale = formatRecommendationRationale(recommendation?.rationale);

  return (
    <Card
      data-testid="etf-regime-tile"
      title={(
        <Space>
          <ExperimentOutlined style={{ color: 'var(--accent-primary)' }} />
          <Title level={4} style={{ margin: 0 }}>市场状态 + 策略推荐</Title>
          <Tooltip title="基于过去 90 个交易日的 5 个特征（趋势拟合度、实现波动率、收益偏度、回撤/波动比、跨资产相关性）分类到 6 类市场状态之一，并映射到推荐策略。沿用多策略比较里的分段结论。">
            <InfoCircleOutlined style={{ color: 'var(--text-secondary)' }} />
          </Tooltip>
        </Space>
      )}
      extra={(
        <Tooltip title="重新拉取 regime 分类">
          <a
            onClick={() => setReloadKey((k) => k + 1)}
            data-testid="etf-regime-tile-refresh"
            style={{ cursor: 'pointer' }}
          >
            <ReloadOutlined /> 刷新
          </a>
        </Tooltip>
      )}
    >
      {loading && !payload ? (
        <Spin tip="正在分类市场状态..." />
      ) : error ? (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={error}
          data-testid="etf-regime-tile-error"
        />
      ) : !regime ? (
        <Empty description="无可用 regime 数据" />
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Row gutter={[16, 8]} align="middle">
            <Col xs={24} md={10}>
              <Space direction="vertical" size={4}>
                <Text type="secondary">当前市场状态</Text>
                <Space>
                  <Tooltip title={meta.detail}>
                    <Tag
                      color={meta.color}
                      data-testid="etf-regime-tile-tag"
                      style={{ fontSize: 14, padding: '4px 12px' }}
                    >
                      {meta.label}
                    </Tag>
                  </Tooltip>
                  <Tooltip title={regime.regime_name ? `原始状态代码：${regime.regime_name}` : '暂无原始状态代码'}>
                    <Tag data-testid="etf-regime-tile-raw-name">模型已分类</Tag>
                  </Tooltip>
                </Space>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  截止 {regime.as_of || '—'} · 用到 {regime.n_bars_used} 天 / {regime.n_assets_used} 个标的
                </Text>
              </Space>
            </Col>
            <Col xs={24} md={8}>
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <Text type="secondary">置信度</Text>
                <Progress
                  percent={Math.round((regime.confidence || 0) * 100)}
                  status={regime.confidence >= 0.7 ? 'success' : 'normal'}
                  data-testid="etf-regime-tile-confidence"
                />
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Statistic
                title="回看窗口（交易日）"
                value={regime.lookback_days}
                prefix={<ThunderboltOutlined />}
              />
            </Col>
          </Row>

          <Card
            size="small"
            type="inner"
            title="特征值"
            data-testid="etf-regime-tile-features"
          >
            <Row gutter={[16, 8]}>
              {FEATURE_ORDER.map((key) => {
                const featureMeta = FEATURE_META[key];
                const value = regime.features?.[key];
                return (
                  <Col xs={12} md={8} key={key}>
                    <Tooltip title={featureMeta.tooltip}>
                      <Space direction="vertical" size={0}>
                        <Text type="secondary" style={{ fontSize: 12 }}>{featureMeta.label}</Text>
                        <Text
                          strong
                          data-testid={`etf-regime-tile-feature-${key}`}
                        >
                          {featureMeta.format(value)}
                        </Text>
                      </Space>
                    </Tooltip>
                  </Col>
                );
              })}
            </Row>
            {regime.reasons && regime.reasons.length > 0 ? (
              <div style={{ marginTop: 12 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>分类依据：</Text>
                <ul style={{ marginTop: 4, marginBottom: 0, paddingLeft: 20 }}>
                  {regime.reasons.map((r, i) => (
                    <li key={i}>
                      <Text type="secondary" style={{ fontSize: 12 }}>{formatRegimeReason(r)}</Text>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>

          <Card
            size="small"
            type="inner"
            title="推荐"
            data-testid="etf-regime-tile-recommendation"
          >
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space wrap>
                <Text type="secondary">运行策略：</Text>
                <Tag color="geekblue" style={{ fontSize: 14, padding: '4px 12px' }} data-testid="etf-regime-tile-strategy">
                  {formatStrategy(strategyName)}
                </Tag>
                {overrideText ? (
                  <Tag color="purple" data-testid="etf-regime-tile-overrides">{overrideText}</Tag>
                ) : (
                  <Tag data-testid="etf-regime-tile-overrides-empty">无 config 覆盖</Tag>
                )}
              </Space>
              {recommendation?.alternatives?.length ? (
                <Space wrap>
                  <Text type="secondary" style={{ fontSize: 12 }}>备选：</Text>
                  {recommendation.alternatives.map((alt) => (
                    <Tag key={alt} data-testid={`etf-regime-tile-alt-${alt}`}>
                      {formatStrategy(alt)}
                    </Tag>
                  ))}
                </Space>
              ) : null}
              {recommendation?.rationale ? (
                <Alert
                  type="info"
                  showIcon
                  message="原因"
                  description={recommendationRationale}
                  data-testid="etf-regime-tile-rationale"
                />
              ) : null}
            </Space>
          </Card>
        </Space>
      )}
    </Card>
  );
};

export default EtfRegimeTile;
