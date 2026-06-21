import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Select,
  InputNumber,
  Button,
  Table,
  Alert,
  Space,
  Typography,
  Tag,
  Empty,
  Spin,
} from 'antd';
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons';

import { Panel } from '../design/components';
import { getLowVolatilityScreen } from '../services/api';
import { useSafeMessageApi, getApiErrorMessage } from '../utils/messageApi';

const { Text, Paragraph } = Typography;

const UNIVERSE_OPTIONS = [
  { value: 'csi300', label: '沪深300 (CSI300)' },
  { value: 'csi500', label: '中证500 (CSI500)' },
];

const TOP_CAP = 100;

const formatPercent = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return `${Number(value).toFixed(digits)}%`;
};

const formatVol = (value, digits = 4) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(digits);
};

const buildColumns = () => [
  {
    title: '排名',
    dataIndex: 'rank',
    key: 'rank',
    width: 72,
    render: (rank) => <Tag color="blue">{rank}</Tag>,
  },
  {
    title: '代码',
    dataIndex: 'symbol',
    key: 'symbol',
    width: 130,
  },
  {
    title: '名称',
    dataIndex: 'name',
    key: 'name',
    render: (name) => name || '—',
  },
  {
    title: '年化波动率',
    dataIndex: 'annualized_vol',
    key: 'annualized_vol',
    width: 130,
    render: (value) => formatVol(value),
  },
  {
    title: '近20日收益',
    dataIndex: 'recent_return',
    key: 'recent_return',
    width: 130,
    render: (value) => {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '—';
      }
      const cls = Number(value) >= 0 ? 'text-up' : 'text-down';
      return <Text className={cls}>{formatPercent(value)}</Text>;
    },
  },
];

const LowVolatilityScreen = () => {
  const message = useSafeMessageApi();
  const [universe, setUniverse] = useState('csi300');
  const [top, setTop] = useState(30);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const requestSeqRef = useRef(0);
  const isMountedRef = useRef(true);

  const runScreen = useCallback(async () => {
    const requestId = requestSeqRef.current + 1;
    requestSeqRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const safeTop = Math.min(Math.max(Number(top) || 30, 1), TOP_CAP);
      const result = await getLowVolatilityScreen({ universe, top: safeTop });
      if (!isMountedRef.current || requestSeqRef.current !== requestId) {
        return;
      }
      setData(result);
    } catch (err) {
      if (!isMountedRef.current || requestSeqRef.current !== requestId) {
        return;
      }
      const detail = getApiErrorMessage(err, '低波动选股查询失败，请稍后重试');
      setError(detail);
      message.error(detail);
    } finally {
      if (isMountedRef.current && requestSeqRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [universe, top, message]);

  useEffect(() => {
    isMountedRef.current = true;
    runScreen();
    return () => {
      isMountedRef.current = false;
    };
    // Run once on mount; subsequent runs are user-triggered via the button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const disclaimer = data?.disclaimer;
  const items = data?.items || [];

  return (
    <Panel
      title="低波动选股"
      icon={<SafetyCertificateOutlined />}
      actions={(
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          onClick={runScreen}
          loading={loading}
        >
          查询
        </Button>
      )}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="低波动是本项目唯一通过样本外验证的信号"
        description={(
          <Paragraph style={{ marginBottom: 0 }}>
            {disclaimer || (
              '低波动是本项目唯一通过样本外验证的信号（预注册确认：CSI500 OOS IC +0.11，'
              + '详见 docs/research/lowvol-confirmation.md）。这是 20 日持有期的横截面信号'
              + '——统计上低波动股票倾向跑赢，但这是信号不是保证收益，且未计入交易摩擦与容量。'
              + '仅供研究，非投资建议。'
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
            aria-label="universe-select"
          />
        </Space>
        <Space>
          <Text>返回名次</Text>
          <InputNumber
            min={1}
            max={TOP_CAP}
            value={top}
            onChange={(value) => setTop(value ?? 30)}
            aria-label="top-input"
          />
        </Space>
      </Space>

      {error && !loading && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="查询失败"
          description={error}
        />
      )}

      {data && (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary">
            {`池: ${universe.toUpperCase()} · 窗口: ${data.window} 交易日 · 已排名 ${data.count} 只`}
            {data.as_of ? ` · 时间: ${String(data.as_of).slice(0, 19).replace('T', ' ')}` : ''}
          </Text>
        </div>
      )}

      {loading && items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin />
          <div style={{ marginTop: 12 }} className="text-muted">正在拉取成分股并计算波动率…</div>
        </div>
      ) : (
        <Table
          rowKey="symbol"
          columns={buildColumns()}
          dataSource={items}
          loading={loading}
          pagination={false}
          size="small"
          locale={{ emptyText: <Empty description="暂无数据" /> }}
        />
      )}
    </Panel>
  );
};

export default LowVolatilityScreen;
