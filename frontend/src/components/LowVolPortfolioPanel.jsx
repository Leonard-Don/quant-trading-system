import { useState, useCallback } from 'react';
import {
  Select,
  InputNumber,
  Button,
  Table,
  Alert,
  Space,
  Typography,
  Empty,
  Spin,
} from 'antd';
import { LineChartOutlined } from '@ant-design/icons';

import { Panel, MetricGrid, StatCard } from '../design/components';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';

import { getLowVolatilityPortfolio } from '../services/api';
import { useSafeMessageApi, getApiErrorMessage } from '../utils/messageApi';

const { Text, Paragraph } = Typography;

const UNIVERSE_OPTIONS = [
  { value: 'csi300', label: '沪深300 (CSI300)' },
  { value: 'csi500', label: '中证500 (CSI500)' },
];

const BASKET_MIN = 10;
const BASKET_MAX = 100;

const pct = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return `${(Number(value) * 100).toFixed(digits)}%`;
};

const ratio = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(digits);
};

// Metrics table: one row per leg, columns = the risk/return fields.
const LEG_LABELS = [
  { key: 'net', label: '低波动篮子(净)', highlight: true },
  { key: 'gross', label: '低波动篮子(毛)', highlight: false },
  { key: 'benchmark', label: '等权基准', highlight: false },
];

const buildMetricRows = (metrics) => {
  if (!metrics) return [];
  return LEG_LABELS.map(({ key, label, highlight }) => {
    const m = metrics[key] || {};
    return {
      key,
      leg: label,
      highlight,
      cagr: m.cagr,
      ann_vol: m.ann_vol,
      sharpe: m.sharpe,
      max_drawdown: m.max_drawdown,
    };
  });
};

const METRIC_COLUMNS = [
  {
    title: '组合',
    dataIndex: 'leg',
    key: 'leg',
    render: (leg, row) => (row.highlight ? <Text strong>{leg}</Text> : leg),
  },
  { title: '年化收益', dataIndex: 'cagr', key: 'cagr', render: (v) => pct(v) },
  { title: '年化波动', dataIndex: 'ann_vol', key: 'ann_vol', render: (v) => pct(v) },
  {
    title: 'Sharpe',
    dataIndex: 'sharpe',
    key: 'sharpe',
    render: (v, row) => (row.highlight ? <Text strong>{ratio(v)}</Text> : ratio(v)),
  },
  { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (v) => pct(v) },
];

const LowVolPortfolioPanel = () => {
  const message = useSafeMessageApi();
  const [universe, setUniverse] = useState('csi300');
  const [basketN, setBasketN] = useState(30);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // No auto-run on mount — the backtest is heavy. User triggers it explicitly.
  const runBacktest = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const safeN = Math.min(Math.max(Number(basketN) || 30, BASKET_MIN), BASKET_MAX);
      const result = await getLowVolatilityPortfolio({ universe, basketN: safeN });
      setData(result);
    } catch (err) {
      const detail = getApiErrorMessage(err, '低波动组合回测失败，请稍后重试');
      setError(detail);
      message.error(detail);
    } finally {
      setLoading(false);
    }
  }, [universe, basketN, message]);

  const disclaimer = data?.disclaimer;
  const curve = data?.equity_curve || [];
  const metricRows = buildMetricRows(data?.metrics);

  return (
    <Panel
      title="低波动组合回测（净额，含 A 股摩擦）"
      icon={<LineChartOutlined />}
      actions={(
        <Button type="primary" icon={<LineChartOutlined />} onClick={runBacktest} loading={loading}>
          运行回测
        </Button>
      )}
    >
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="净额回测 — 历史与信号，非保证收益"
        description={(
          <Paragraph style={{ marginBottom: 0 }}>
            {disclaimer || (
              '低波动是本项目唯一通过样本外验证的信号（CSI500 OOS IC +0.11）。此为净额回测'
              + '（已计入 A 股交易摩擦，总收益复权价）。CSI300 大盘：净 Sharpe≈0.44 vs 等权 0.22；'
              + 'CSI500 中小盘：换手更高，净额仅与等权持平甚至略逊。OOD 检验显示 2024–25 未见期'
              + '持续性偏弱，需实时监控。仅供研究，非投资建议。'
            )}
          </Paragraph>
        )}
      />

      <Space wrap style={{ marginBottom: 16 }}>
        <Space>
          <Text>指数池</Text>
          <Select
            value={universe}
            onChange={setUniverse}
            options={UNIVERSE_OPTIONS}
            style={{ width: 200 }}
            aria-label="portfolio-universe-select"
          />
        </Space>
        <Space>
          <Text>篮子只数</Text>
          <InputNumber
            min={BASKET_MIN}
            max={BASKET_MAX}
            value={basketN}
            onChange={(value) => setBasketN(value ?? 30)}
            aria-label="basket-n-input"
          />
        </Space>
      </Space>

      {error && !loading && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="回测失败"
          description={error}
        />
      )}

      {loading && !data ? (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin />
          <div style={{ marginTop: 12 }} className="text-muted">正在构建组合并计算净值（冷启动较慢）…</div>
        </div>
      ) : !data ? (
        <Empty description={'点击“运行回测”查看低波动组合净值曲线与指标'} />
      ) : (
        <>
          <MetricGrid className="mb-4">
            <StatCard label="调仓期数" value={data.n_periods ?? '—'} />
            <StatCard label="年换手(单边)" value={`${ratio(data.avg_annual_turnover, 2)}×`} />
            <StatCard label="净超额年化 vs 等权" value={pct((data.metrics?.net?.cagr ?? 0) - (data.metrics?.benchmark?.cagr ?? 0))} accent />
          </MetricGrid>

          <div style={{ width: '100%', height: 320, marginBottom: 16 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curve} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={32} />
                <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
                <Tooltip formatter={(v) => Number(v).toFixed(3)} />
                <Legend />
                <Line type="monotone" dataKey="basket_net" name="低波动篮子(净)" stroke="var(--color-accent)" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="basket_gross" name="低波动篮子(毛)" stroke="var(--color-warn)" dot={false} strokeDasharray="4 2" />
                <Line type="monotone" dataKey="benchmark" name="等权基准" stroke="var(--color-muted)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <Table
            rowKey="key"
            columns={METRIC_COLUMNS}
            dataSource={metricRows}
            pagination={false}
            size="small"
          />
        </>
      )}
    </Panel>
  );
};

export default LowVolPortfolioPanel;
