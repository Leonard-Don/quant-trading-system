import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { getCrossMarketTemplates, runCrossMarketBacktest } from '../services/api';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';

const { Paragraph, Text, Title } = Typography;

const ASSET_CLASS_OPTIONS = [
  { value: 'US_STOCK', label: 'US Stock' },
  { value: 'ETF', label: 'ETF' },
  { value: 'COMMODITY_FUTURES', label: 'Commodity Futures' },
];

const DEFAULT_PARAMETERS = {
  lookback: 20,
  entry_threshold: 1.5,
  exit_threshold: 0.5,
};

const DEFAULT_QUALITY = {
  construction_mode: 'equal_weight',
  min_history_days: 60,
  min_overlap_ratio: 0.7,
};

const createAsset = (side, index) => ({
  key: `${side}-${index}-${Date.now()}`,
  side,
  symbol: '',
  asset_class: 'ETF',
  weight: null,
});

const normalizeAssets = (assets, side) =>
  assets
    .filter((asset) => asset.side === side)
    .map((asset) => ({
      ...asset,
      symbol: (asset.symbol || '').trim().toUpperCase(),
    }));

function CrossMarketBacktestPanel() {
  const [templates, setTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [running, setRunning] = useState(false);
  const [assets, setAssets] = useState([
    createAsset('long', 0),
    createAsset('short', 0),
  ]);
  const [parameters, setParameters] = useState(DEFAULT_PARAMETERS);
  const [quality, setQuality] = useState(DEFAULT_QUALITY);
  const [meta, setMeta] = useState({
    initial_capital: 100000,
    commission: 0.1,
    slippage: 0.1,
    start_date: '',
    end_date: '',
  });
  const [results, setResults] = useState(null);

  useEffect(() => {
    const loadTemplates = async () => {
      setLoadingTemplates(true);
      try {
        const response = await getCrossMarketTemplates();
        setTemplates(response.templates || []);
      } catch (error) {
        message.error(error.userMessage || error.message || '加载模板失败');
      } finally {
        setLoadingTemplates(false);
      }
    };

    loadTemplates();
  }, []);

  const longAssets = useMemo(() => normalizeAssets(assets, 'long'), [assets]);
  const shortAssets = useMemo(() => normalizeAssets(assets, 'short'), [assets]);

  const updateAsset = (key, field, value) => {
    setAssets((prev) =>
      prev.map((asset) => (asset.key === key ? { ...asset, [field]: value } : asset))
    );
  };

  const removeAsset = (key) => {
    setAssets((prev) => prev.filter((asset) => asset.key !== key));
  };

  const addAsset = (side) => {
    setAssets((prev) => [...prev, createAsset(side, prev.length)]);
  };

  const applyTemplate = (templateId) => {
    const template = templates.find((item) => item.id === templateId);
    if (!template) {
      return;
    }
    setAssets(
      template.assets.map((asset, index) => ({
        key: `${asset.side}-${index}-${template.id}`,
        ...asset,
      }))
    );
    setParameters({
      lookback: template.parameters?.lookback ?? DEFAULT_PARAMETERS.lookback,
      entry_threshold: template.parameters?.entry_threshold ?? DEFAULT_PARAMETERS.entry_threshold,
      exit_threshold: template.parameters?.exit_threshold ?? DEFAULT_PARAMETERS.exit_threshold,
    });
    setQuality((prev) => ({
      ...prev,
      construction_mode: template.construction_mode || DEFAULT_QUALITY.construction_mode,
    }));
    message.success(`已载入模板: ${template.name}`);
  };

  const handleRun = async () => {
    const payloadAssets = assets
      .map((asset) => ({
        symbol: (asset.symbol || '').trim().toUpperCase(),
        asset_class: asset.asset_class,
        side: asset.side,
        weight: asset.weight || undefined,
      }))
      .filter((asset) => asset.symbol);

    if (payloadAssets.length < 2) {
      message.error('请至少填写两个资产');
      return;
    }

    setRunning(true);
    setResults(null);
    try {
      const response = await runCrossMarketBacktest({
        assets: payloadAssets,
        strategy: 'spread_zscore',
        construction_mode: quality.construction_mode,
        parameters,
        min_history_days: quality.min_history_days,
        min_overlap_ratio: quality.min_overlap_ratio,
        initial_capital: meta.initial_capital,
        commission: meta.commission / 100,
        slippage: meta.slippage / 100,
        start_date: meta.start_date || undefined,
        end_date: meta.end_date || undefined,
      });
      if (response.success) {
        setResults(response.data);
        message.success('跨市场回测完成');
      } else {
        message.error(response.error || '跨市场回测失败');
      }
    } catch (error) {
      message.error(error.userMessage || error.message || '跨市场回测失败');
    } finally {
      setRunning(false);
    }
  };

  const renderAssetSection = (title, sideAssets, side) => (
    <Card
      title={title}
      extra={
        <Button size="small" icon={<PlusOutlined />} onClick={() => addAsset(side)}>
          新增
        </Button>
      }
      bordered={false}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        {sideAssets.map((asset) => (
          <Row gutter={12} key={asset.key}>
            <Col xs={24} md={8}>
              <Input
                value={asset.symbol}
                placeholder="Symbol"
                onChange={(event) => updateAsset(asset.key, 'symbol', event.target.value)}
              />
            </Col>
            <Col xs={24} md={8}>
              <Select
                value={asset.asset_class}
                options={ASSET_CLASS_OPTIONS}
                style={{ width: '100%' }}
                onChange={(value) => updateAsset(asset.key, 'asset_class', value)}
              />
            </Col>
            <Col xs={18} md={6}>
              <InputNumber
                value={asset.weight}
                min={0.01}
                step={0.05}
                placeholder="Weight"
                style={{ width: '100%' }}
                onChange={(value) => updateAsset(asset.key, 'weight', value)}
              />
            </Col>
            <Col xs={6} md={2}>
              <Button
                icon={<DeleteOutlined />}
                danger
                onClick={() => removeAsset(asset.key)}
              />
            </Col>
          </Row>
        ))}
      </Space>
    </Card>
  );

  const correlationColumns = useMemo(() => {
    if (!results?.correlation_matrix?.columns) {
      return [];
    }
    return [
      {
        title: 'Symbol',
        dataIndex: 'symbol',
        key: 'symbol',
        fixed: 'left',
      },
      ...results.correlation_matrix.columns.map((column) => ({
        title: column,
        dataIndex: column,
        key: column,
        render: (value) => Number(value).toFixed(3),
      })),
    ];
  }, [results]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Card bordered={false}>
        <Space direction="vertical" size={6}>
          <Tag color="geekblue" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
            Cross-Market MVP
          </Tag>
          <Title level={4} style={{ margin: 0 }}>
            跨市场回测
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            这一页专门用来演示跨资产长短腿组合。当前版本只支持 `USD` 计价、`1d`
            频率和 `spread_zscore` 策略。
          </Paragraph>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            {renderAssetSection('多头篮子', longAssets, 'long')}
            {renderAssetSection('空头篮子', shortAssets, 'short')}
          </Space>
        </Col>

        <Col xs={24} xl={8}>
          <Card title="参数与模板" bordered={false}>
            <Space direction="vertical" style={{ width: '100%' }} size={14}>
              <Select
                placeholder="载入演示模板"
                loading={loadingTemplates}
                options={templates.map((template) => ({
                  label: template.name,
                  value: template.id,
                }))}
                onChange={applyTemplate}
              />

              <Form layout="vertical">
                <Form.Item label="Construction Mode">
                  <Select
                    value={quality.construction_mode}
                    options={[
                      { value: 'equal_weight', label: 'Equal Weight' },
                      { value: 'ols_hedge', label: 'Rolling OLS Hedge' },
                    ]}
                    onChange={(value) => setQuality((prev) => ({ ...prev, construction_mode: value }))}
                  />
                </Form.Item>
                <Form.Item label="Lookback">
                  <InputNumber
                    min={5}
                    value={parameters.lookback}
                    style={{ width: '100%' }}
                    onChange={(value) =>
                      setParameters((prev) => ({ ...prev, lookback: value || DEFAULT_PARAMETERS.lookback }))
                    }
                  />
                </Form.Item>
                <Form.Item label="Entry Threshold">
                  <InputNumber
                    min={0.5}
                    step={0.1}
                    value={parameters.entry_threshold}
                    style={{ width: '100%' }}
                    onChange={(value) =>
                      setParameters((prev) => ({ ...prev, entry_threshold: value || DEFAULT_PARAMETERS.entry_threshold }))
                    }
                  />
                </Form.Item>
                <Form.Item label="Exit Threshold">
                  <InputNumber
                    min={0.1}
                    step={0.1}
                    value={parameters.exit_threshold}
                    style={{ width: '100%' }}
                    onChange={(value) =>
                      setParameters((prev) => ({ ...prev, exit_threshold: value || DEFAULT_PARAMETERS.exit_threshold }))
                    }
                  />
                </Form.Item>
                <Form.Item label="Initial Capital">
                  <InputNumber
                    min={1000}
                    step={1000}
                    value={meta.initial_capital}
                    style={{ width: '100%' }}
                    onChange={(value) => setMeta((prev) => ({ ...prev, initial_capital: value || 100000 }))}
                  />
                </Form.Item>
                <Form.Item label="Min History Days">
                  <InputNumber
                    min={10}
                    step={5}
                    value={quality.min_history_days}
                    style={{ width: '100%' }}
                    onChange={(value) => setQuality((prev) => ({ ...prev, min_history_days: value || 60 }))}
                  />
                </Form.Item>
                <Form.Item label="Min Overlap Ratio">
                  <InputNumber
                    min={0.1}
                    max={1}
                    step={0.05}
                    value={quality.min_overlap_ratio}
                    style={{ width: '100%' }}
                    onChange={(value) => setQuality((prev) => ({ ...prev, min_overlap_ratio: value || 0.7 }))}
                  />
                </Form.Item>
                <Form.Item label="Commission (%)">
                  <InputNumber
                    min={0}
                    step={0.01}
                    value={meta.commission}
                    style={{ width: '100%' }}
                    onChange={(value) => setMeta((prev) => ({ ...prev, commission: value ?? 0.1 }))}
                  />
                </Form.Item>
                <Form.Item label="Slippage (%)">
                  <InputNumber
                    min={0}
                    step={0.01}
                    value={meta.slippage}
                    style={{ width: '100%' }}
                    onChange={(value) => setMeta((prev) => ({ ...prev, slippage: value ?? 0.1 }))}
                  />
                </Form.Item>
                <Form.Item label="Start Date">
                  <Input
                    value={meta.start_date}
                    placeholder="YYYY-MM-DD"
                    onChange={(event) => setMeta((prev) => ({ ...prev, start_date: event.target.value }))}
                  />
                </Form.Item>
                <Form.Item label="End Date">
                  <Input
                    value={meta.end_date}
                    placeholder="YYYY-MM-DD"
                    onChange={(event) => setMeta((prev) => ({ ...prev, end_date: event.target.value }))}
                  />
                </Form.Item>
              </Form>

              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Button icon={<ReloadOutlined />} onClick={() => setResults(null)}>
                  清空结果
                </Button>
                <Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={handleRun}>
                  运行回测
                </Button>
              </Space>
            </Space>
          </Card>
        </Col>
      </Row>

      {running && !results ? (
        <Card bordered={false}>
          <div style={{ minHeight: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin size="large" />
          </div>
        </Card>
      ) : null}

      {results ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Alert
            type={results.total_return >= 0 ? 'success' : 'warning'}
            showIcon
            message="跨市场结果已生成"
            description={`样本区间 ${results.price_matrix_summary.start_date} 至 ${results.price_matrix_summary.end_date}，共 ${results.price_matrix_summary.row_count} 个对齐交易日。`}
          />

          {(results.data_alignment?.tradable_day_ratio || 0) < 0.8 ? (
            <Alert
              type="warning"
              showIcon
              message="数据对齐覆盖率偏低"
              description={`当前可交易日覆盖率为 ${(results.data_alignment?.tradable_day_ratio || 0) * 100}% ，建议检查资产组合或放宽时间窗口。`}
            />
          ) : null}

          <Row gutter={[16, 16]}>
            <Col xs={24} md={8}>
              <Card bordered={false}>
                <Statistic
                  title="总收益率"
                  value={results.total_return * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: getValueColor(results.total_return) }}
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card bordered={false}>
                <Statistic
                  title="最终净值"
                  value={results.final_value}
                  precision={2}
                  formatter={(value) => formatCurrency(Number(value || 0))}
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card bordered={false}>
                <Statistic
                  title="Sharpe"
                  value={results.sharpe_ratio}
                  precision={2}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="数据对齐诊断" bordered={false}>
                <Row gutter={[16, 16]}>
                  <Col span={8}>
                    <Statistic
                      title="可交易日占比"
                      value={(results.data_alignment?.tradable_day_ratio || 0) * 100}
                      precision={2}
                      suffix="%"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="丢弃日期数"
                      value={results.data_alignment?.dropped_dates_count || 0}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="对齐后行数"
                      value={results.data_alignment?.aligned_row_count || 0}
                    />
                  </Col>
                </Row>
                <Table
                  style={{ marginTop: 16 }}
                  size="small"
                  rowKey="symbol"
                  pagination={false}
                  dataSource={results.data_alignment?.per_symbol || []}
                  columns={[
                    { title: 'Symbol', dataIndex: 'symbol', key: 'symbol' },
                    { title: '原始行数', dataIndex: 'raw_rows', key: 'raw_rows' },
                    { title: '有效行数', dataIndex: 'valid_rows', key: 'valid_rows' },
                    {
                      title: '覆盖率',
                      dataIndex: 'coverage_ratio',
                      key: 'coverage_ratio',
                      render: (value) => formatPercentage(Number(value || 0)),
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="执行诊断" bordered={false}>
                <Row gutter={[16, 16]}>
                  <Col span={8}>
                    <Statistic
                      title="Turnover"
                      value={results.execution_diagnostics?.turnover || 0}
                      precision={2}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Cost Drag"
                      value={(results.execution_diagnostics?.cost_drag || 0) * 100}
                      precision={2}
                      suffix="%"
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Avg Holding"
                      value={results.execution_diagnostics?.avg_holding_period || 0}
                      precision={1}
                      suffix="d"
                    />
                  </Col>
                </Row>
                <div style={{ marginTop: 16 }}>
                  <Tag color="purple">
                    {results.execution_diagnostics?.construction_mode || quality.construction_mode}
                  </Tag>
                  <Text type="secondary"> 当前对冲构造模式</Text>
                </div>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={14}>
              <Card title="组合净值曲线" bordered={false}>
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer>
                    <LineChart data={results.portfolio_curve}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" minTickGap={32} />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="total" name="Portfolio" stroke="#1677ff" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </Col>
            <Col xs={24} xl={10}>
              <Card title="长短腿累计收益" bordered={false}>
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer>
                    <BarChart
                      data={[
                        {
                          leg: 'Long',
                          value: (results.leg_performance.long.cumulative_return || 0) * 100,
                        },
                        {
                          leg: 'Short',
                          value: (results.leg_performance.short.cumulative_return || 0) * 100,
                        },
                        {
                          leg: 'Spread',
                          value: (results.leg_performance.spread.cumulative_return || 0) * 100,
                        },
                      ]}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="leg" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="value" fill="#52c41a" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={results.hedge_ratio_series ? 14 : 24}>
              <Card title="Spread / Z-Score" bordered={false}>
                <div style={{ width: '100%', height: 320 }}>
                  <ResponsiveContainer>
                    <LineChart data={results.spread_series}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" minTickGap={32} />
                      <YAxis yAxisId="left" />
                      <YAxis yAxisId="right" orientation="right" />
                      <Tooltip />
                      <Legend />
                      <Line yAxisId="left" type="monotone" dataKey="spread" stroke="#13c2c2" dot={false} />
                      <Line yAxisId="right" type="monotone" dataKey="z_score" stroke="#cf1322" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </Col>
            {results.hedge_ratio_series ? (
              <Col xs={24} xl={10}>
                <Card title="Hedge Ratio" bordered={false}>
                  <div style={{ width: '100%', height: 320 }}>
                    <ResponsiveContainer>
                      <LineChart data={results.hedge_ratio_series}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" minTickGap={32} />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="hedge_ratio" stroke="#722ed1" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              </Col>
            ) : null}
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card title="交易记录" bordered={false}>
                <Table
                  size="small"
                  rowKey={(record, index) => `${record.date}-${index}`}
                  dataSource={results.trades || []}
                  pagination={{ pageSize: 6 }}
                  columns={[
                    { title: '日期', dataIndex: 'date', key: 'date' },
                    {
                      title: '动作',
                      dataIndex: 'type',
                      key: 'type',
                      render: (value) => <Tag color={String(value).includes('OPEN') ? 'blue' : 'orange'}>{value}</Tag>,
                    },
                    {
                      title: 'Spread',
                      dataIndex: 'spread',
                      key: 'spread',
                      render: (value) => Number(value).toFixed(4),
                    },
                    {
                      title: 'Z',
                      dataIndex: 'z_score',
                      key: 'z_score',
                      render: (value) => Number(value).toFixed(3),
                    },
                    {
                      title: 'PnL',
                      dataIndex: 'pnl',
                      key: 'pnl',
                      render: (value) => <span style={{ color: getValueColor(value) }}>{formatCurrency(Number(value || 0))}</span>,
                    },
                    {
                      title: '持有天数',
                      dataIndex: 'holding_period_days',
                      key: 'holding_period_days',
                      render: (value) => (value === null || value === undefined ? '-' : value),
                    },
                  ]}
                />
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card title="资产相关性矩阵" bordered={false}>
                <Table
                  size="small"
                  scroll={{ x: true }}
                  pagination={false}
                  rowKey="symbol"
                  dataSource={results.correlation_matrix.rows || []}
                  columns={correlationColumns}
                />
              </Card>
            </Col>
          </Row>

          <Card title="资产篮子摘要" bordered={false}>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Text strong>多头篮子</Text>
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {results.leg_performance.long.assets.map((asset) => (
                    <Tag key={`long-${asset.symbol}`}>{asset.symbol} · {asset.asset_class} · {formatPercentage(asset.weight)}</Tag>
                  ))}
                </div>
              </Col>
              <Col xs={24} md={12}>
                <Text strong>空头篮子</Text>
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {results.leg_performance.short.assets.map((asset) => (
                    <Tag key={`short-${asset.symbol}`}>{asset.symbol} · {asset.asset_class} · {formatPercentage(asset.weight)}</Tag>
                  ))}
                </div>
              </Col>
            </Row>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

export default CrossMarketBacktestPanel;
