import React, { useEffect, useMemo, useState } from 'react';
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
    detail: '价格趋势清晰且波动率正常 — mean_reversion 在 R²=0.792 的 2024-2025 下半场领跑 (+6.17%)。',
    risk: 'low',
  },
  trending_high_vol: {
    color: 'processing',
    label: '上行高波动',
    detail: '趋势存在但波动率抬升 — rotation 应对 regime shift 更稳，下调 gross_cap 给噪声留余量。',
    risk: 'medium',
  },
  choppy_low_vol: {
    color: 'blue',
    label: '盘整低波动',
    detail: 'R² 较低、波动率正常 — rotation 在 R²=0.370 的 2024 上半场领跑 (+5.48%)。',
    risk: 'low',
  },
  choppy_high_vol: {
    color: 'gold',
    label: '盘整高波动',
    detail: '同时盘整 + 高波动 — 单策略 alpha 微薄，建议 blend 分散 regime 风险。',
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
    detail: '有序下行 — mean_reversion 在中性 / 弱跌中仍有小幅正 edge，降仓位运行。',
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
  rotation: 'rotation（轮动）',
  mean_reversion: 'mean_reversion（均值回归）',
  blend: 'blend（混合）',
  cash: 'cash（清仓 / 等待）',
  unchanged: '保持当前策略',
};

const FEATURE_META = {
  trend_r2: {
    label: 'trend R²',
    tooltip: 'log(price) 线性拟合的 R²；越大越接近直线趋势。',
    format: (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(3)),
  },
  trend_slope: {
    label: 'trend slope',
    tooltip: 'log-price 每日变化率；负值表示下行。',
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
    label: 'max_dd / vol',
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

const formatStrategy = (name) => {
  if (!name) return '—';
  return STRATEGY_LABELS[name] || name;
};

const formatOverrides = (overrides) => {
  if (!overrides || Object.keys(overrides).length === 0) return null;
  return Object.entries(overrides)
    .map(([k, v]) => `${k}=${typeof v === 'number' ? v.toFixed(2) : String(v)}`)
    .join(', ');
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
          setError('Unable to compute regime recommendation.');
        }
      } catch (err) {
        if (!cancelled) {
          const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
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

  return (
    <Card
      data-testid="etf-regime-tile"
      title={(
        <Space>
          <ExperimentOutlined style={{ color: 'var(--accent-primary)' }} />
          <Title level={4} style={{ margin: 0 }}>市场状态 + 策略推荐</Title>
          <Tooltip title="基于过去 90 个交易日的 5 个特征（trend R² / 实现波动率 / 偏度 / 回撤比 / 跨资产相关性）分类到 6 个 regime 之一，并映射到推荐策略。落地了 commit a54b986 多策略比较的 regime 分离结论。">
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
                <Text type="secondary">当前 regime</Text>
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
                  <Tag data-testid="etf-regime-tile-raw-name">{regime.regime_name}</Tag>
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
                title="lookback (交易日)"
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
                      <Text type="secondary" style={{ fontSize: 12 }}>{r}</Text>
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
                  {formatStrategy(recommendation?.strategy_name)}
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
                  description={recommendation.rationale}
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
