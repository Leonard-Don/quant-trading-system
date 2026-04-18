import React from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
} from 'antd';
import { DownloadOutlined, RiseOutlined } from '@ant-design/icons';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { getStrategyName, getStrategyParameterLabel, getStrategyDetails } from '../../constants/strategies';
import { formatPercentage } from '../../utils/formatting';
import { DEFAULT_CAPITAL, DEFAULT_COMMISSION, DEFAULT_SLIPPAGE, getMetricValue } from '../../hooks/useAdvancedBacktestLab';
import dayjs from '../../utils/dayjs';

const { RangePicker } = DatePicker;

const CHART_POSITIVE = '#22c55e';
const CHART_NEGATIVE = '#ef4444';
const CHART_NEUTRAL = '#0ea5e9';

const renderWalkTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="chart-tooltip">
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{point.label}</div>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{point.testRange}</div>
      <div>窗口收益 {formatPercentage(point.totalReturn)}</div>
      <div>夏普比率 {Number(point.sharpe || 0).toFixed(2)}</div>
      <div>最大回撤 {formatPercentage(-Math.abs(point.drawdown || 0))}</div>
    </div>
  );
};

const walkColumns = [
  {
    title: '窗口',
    dataIndex: 'window_id',
    key: 'window_id',
    render: (value) => `窗口 ${value + 1}`,
  },
  {
    title: '测试区间',
    key: 'test_range',
    render: (_, record) => `${record.test_start} ~ ${record.test_end}`,
  },
  {
    title: '总收益率',
    dataIndex: ['metrics', 'total_return'],
    key: 'total_return',
    render: (value) => formatPercentage(value || 0),
  },
  {
    title: '夏普比率',
    dataIndex: ['metrics', 'sharpe_ratio'],
    key: 'sharpe_ratio',
    render: (value) => Number(value || 0).toFixed(2),
  },
  {
    title: '最大回撤',
    dataIndex: ['metrics', 'max_drawdown'],
    key: 'max_drawdown',
    render: (value) => formatPercentage(value || 0),
  },
  {
    title: '训练窗优选参数',
    dataIndex: 'selected_parameters',
    key: 'selected_parameters',
    render: (value) => {
      const entries = Object.entries(value || {});
      if (!entries.length) return '-';
      return entries.map(([key, item]) => `${getStrategyParameterLabel(key, key)}:${item}`).join(' / ');
    },
  },
];

function WalkForwardForm({
  walkForm,
  strategies,
  selectedWalkStrategy,
  strategyDefinitions,
  walkParams,
  setWalkParams,
  walkLoading,
  handleRunWalkForward,
}) {
  return (
    <Card
      className="workspace-panel workspace-panel--emphasis"
      title={(
        <div className="workspace-title">
          <div className="workspace-title__icon workspace-title__icon--accent">
            <RiseOutlined style={{ color: '#fff' }} />
          </div>
          <div>
            <div className="workspace-title__text">滚动前瞻分析</div>
            <div className="workspace-title__hint">查看滚动窗口下的稳定性，而不只盯单次整段结果。</div>
          </div>
        </div>
      )}
    >
      <Form
        form={walkForm}
        layout="vertical"
        onFinish={handleRunWalkForward}
        initialValues={{
          symbol: 'AAPL',
          strategy: 'moving_average',
          dateRange: [dayjs().subtract(2, 'year'), dayjs()],
          initial_capital: DEFAULT_CAPITAL,
          commission: DEFAULT_COMMISSION,
          slippage: DEFAULT_SLIPPAGE,
          train_period: 252,
          test_period: 63,
          step_size: 21,
          optimization_metric: 'sharpe_ratio',
          optimization_method: 'grid',
          optimization_budget: 24,
          monte_carlo_simulations: 120,
        }}
      >
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item label="标的代码" name="symbol" rules={[{ required: true, message: '请输入标的代码' }]}>
              <Input placeholder="如 AAPL" />
            </Form.Item>
          </Col>
          <Col xs={24} md={16}>
            <Form.Item label="实验区间" name="dateRange" rules={[{ required: true, message: '请选择日期区间' }]}>
              <RangePicker style={{ width: '100%' }} placeholder={['开始日期', '结束日期']} separator="至" />
            </Form.Item>
          </Col>
          <Col xs={24}>
            <Form.Item label="策略" name="strategy" rules={[{ required: true, message: '请选择策略' }]}>
              <Select
                options={strategies.map((strategy) => ({
                  value: strategy.name,
                  label: getStrategyName(strategy.name),
                }))}
              />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="训练窗口" name="train_period">
              <InputNumber min={20} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="测试窗口" name="test_period">
              <InputNumber min={5} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="滚动步长" name="step_size">
              <InputNumber min={1} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="优化指标" name="optimization_metric">
              <Select
                options={[
                  { value: 'sharpe_ratio', label: '夏普比率' },
                  { value: 'total_return', label: '总收益率' },
                  { value: 'annualized_return', label: '年化收益率' },
                  { value: 'calmar_ratio', label: '卡玛比率' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="优化方式" name="optimization_method">
              <Select
                options={[
                  { value: 'grid', label: '网格穷举' },
                  { value: 'bayesian', label: '自适应贝叶斯搜索' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="Monte Carlo 次数" name="monte_carlo_simulations">
              <InputNumber min={20} max={1000} precision={0} step={20} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="优化预算" name="optimization_budget">
              <InputNumber min={1} max={500} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="初始资金" name="initial_capital">
              <InputNumber min={1000} step={1000} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="手续费 (%)" name="commission">
              <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={8}>
            <Form.Item label="滑点 (%)" name="slippage">
              <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        {selectedWalkStrategy ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`${getStrategyName(selectedWalkStrategy)} · ${getStrategyDetails(selectedWalkStrategy).style}`}
            description={`${getStrategyDetails(selectedWalkStrategy).summary} ${getStrategyDetails(selectedWalkStrategy).marketFit}`}
          />
        ) : null}

        {selectedWalkStrategy && Object.keys(strategyDefinitions[selectedWalkStrategy]?.parameters || {}).length ? (
          <div className="workspace-section" style={{ marginBottom: 16 }}>
            <div className="workspace-section__header">
              <div>
                <div className="workspace-section__title">策略参数</div>
                <div className="workspace-section__description">系统会先围绕当前参数生成候选组合，在训练窗口中挑选更优参数，再拿到测试窗口做样本外验证。</div>
              </div>
            </div>
            <Row gutter={[12, 12]}>
              {Object.entries(strategyDefinitions[selectedWalkStrategy]?.parameters || {}).map(([key, config]) => (
                <Col key={`walk-${key}`} xs={24} md={12}>
                  <div className="workspace-field-label">{getStrategyParameterLabel(key, config.description)}</div>
                  <InputNumber
                    value={walkParams[key] ?? config.default}
                    min={config.min}
                    max={config.max}
                    step={config.step || 0.01}
                    style={{ width: '100%' }}
                    onChange={(value) => setWalkParams((previous) => ({ ...previous, [key]: value }))}
                  />
                </Col>
              ))}
            </Row>
          </div>
        ) : null}

        <Button type="primary" htmlType="submit" icon={<RiseOutlined />} loading={walkLoading} block>
          运行滚动前瞻分析
        </Button>
      </Form>
    </Card>
  );
}

function WalkForwardResults({
  walkResult,
  walkForwardChartData,
  walkInsight,
  walkLoading,
  focusedWalkRecord,
  focusedWalkWindowKey,
  setFocusedWalkWindowKey,
  handleSaveWalkHistory,
  handleExportWalkForward,
}) {
  return (
    <Card
      className="workspace-panel workspace-chart-card"
      title="滚动前瞻分析结果"
      extra={walkResult ? (
        <Space size="small">
          <Button size="small" onClick={handleSaveWalkHistory}>保存到历史</Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => handleExportWalkForward('csv')}>导出CSV</Button>
          <Button size="small" onClick={() => handleExportWalkForward('json')}>导出JSON</Button>
        </Space>
      ) : null}
    >
      {walkResult ? (
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {walkLoading ? (
            <Alert
              type="info"
              showIcon
              message="正在刷新滚动前瞻结果"
              description="上一版窗口稳定性分析会先保留，新的样本外验证完成后会自动替换。"
            />
          ) : null}
          <div className="summary-strip">
            <div className="summary-strip__item">
              <span className="summary-strip__label">滚动窗口</span>
              <span className="summary-strip__value">{walkResult.n_windows}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">平均收益</span>
              <span className="summary-strip__value">{formatPercentage(walkResult.aggregate_metrics?.average_return ?? 0)}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">收益波动</span>
              <span className="summary-strip__value">{formatPercentage(walkResult.aggregate_metrics?.return_std ?? 0)}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">平均夏普</span>
              <span className="summary-strip__value">{Number(walkResult.aggregate_metrics?.average_sharpe ?? 0).toFixed(2)}</span>
            </div>
          </div>
          <Alert
            type="info"
            showIcon
            message={`正收益窗口 ${walkResult.aggregate_metrics?.positive_windows ?? 0} 个，负收益窗口 ${walkResult.aggregate_metrics?.negative_windows ?? 0} 个`}
            description="如果窗口之间表现差异很大，就说明策略更依赖某些特定市场阶段，稳定性需要继续验证。"
          />
          {walkInsight ? (
            <Alert type={walkInsight.type} showIcon message={walkInsight.title} description={walkInsight.description} />
          ) : null}
          {walkResult.monte_carlo?.available ? (
            <div className="summary-strip">
              <div className="summary-strip__item">
                <span className="summary-strip__label">模拟次数</span>
                <span className="summary-strip__value">{walkResult.monte_carlo.simulations}</span>
              </div>
              <div className="summary-strip__item">
                <span className="summary-strip__label">平均收益 P10</span>
                <span className="summary-strip__value">{formatPercentage(walkResult.monte_carlo.mean_return_p10 ?? 0)}</span>
              </div>
              <div className="summary-strip__item">
                <span className="summary-strip__label">平均收益 P50</span>
                <span className="summary-strip__value">{formatPercentage(walkResult.monte_carlo.mean_return_p50 ?? 0)}</span>
              </div>
              <div className="summary-strip__item">
                <span className="summary-strip__label">负均值概率</span>
                <span className="summary-strip__value">{formatPercentage(walkResult.monte_carlo.negative_mean_probability ?? 0)}</span>
              </div>
            </div>
          ) : null}
          {walkResult.overfitting_diagnostics ? (
            <Alert
              type={
                walkResult.overfitting_diagnostics.level === 'high'
                  ? 'warning'
                  : walkResult.overfitting_diagnostics.level === 'medium'
                    ? 'info'
                    : 'success'
              }
              showIcon
              message={`样本外过拟合诊断：${walkResult.overfitting_diagnostics.level === 'high' ? '高风险' : walkResult.overfitting_diagnostics.level === 'medium' ? '中等风险' : '低风险'}`}
              description={(walkResult.overfitting_diagnostics.warnings || []).join('；') || '训练窗与测试窗表现没有出现明显断裂。'}
            />
          ) : null}
          {focusedWalkRecord ? (
            <Alert
              type="info"
              showIcon
              message={`当前聚焦：窗口 ${Number(focusedWalkRecord.window_id || 0) + 1}`}
              description={`${focusedWalkRecord.test_start} ~ ${focusedWalkRecord.test_end}，窗口收益 ${formatPercentage(getMetricValue(focusedWalkRecord, 'total_return'))}，夏普 ${Number(getMetricValue(focusedWalkRecord, 'sharpe_ratio')).toFixed(2)}，最大回撤 ${formatPercentage(getMetricValue(focusedWalkRecord, 'max_drawdown'))}`}
            />
          ) : null}
          {walkForwardChartData.length ? (
            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">窗口稳定性曲线</div>
                  <div className="workspace-section__description">观察每个测试窗口的收益和回撤变化，判断策略是否只在少数阶段有效。</div>
                </div>
              </div>
              <div style={{ height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={walkForwardChartData}
                    margin={{ top: 8, right: 12, left: 8, bottom: 8 }}
                    onClick={(state) => {
                      const nextWindowKey = state?.activePayload?.[0]?.payload?.key;
                      if (nextWindowKey) setFocusedWalkWindowKey(nextWindowKey);
                    }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                    <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                    <YAxis yAxisId="left" tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                    <RechartsTooltip content={renderWalkTooltip} />
                    <Legend />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="totalReturn"
                      name="窗口收益"
                      stroke={CHART_POSITIVE}
                      strokeWidth={2.5}
                      dot={(props) => {
                        const isFocused = props?.payload?.key === focusedWalkWindowKey;
                        const pointKey = props?.payload?.key || `${props?.cx ?? 'x'}-${props?.cy ?? 'y'}`;
                        return (
                          <circle
                            key={pointKey}
                            cx={props.cx}
                            cy={props.cy}
                            r={isFocused ? 5 : 3}
                            fill={CHART_POSITIVE}
                            stroke={isFocused ? '#f8fafc' : CHART_POSITIVE}
                            strokeWidth={isFocused ? 2 : 1}
                          />
                        );
                      }}
                      activeDot={{ r: 5 }}
                    />
                    <Line yAxisId="left" type="monotone" dataKey="drawdown" name="最大回撤绝对值" stroke={CHART_NEGATIVE} strokeWidth={2} strokeDasharray="6 4" dot={{ r: 2 }} />
                    <Line yAxisId="right" type="monotone" dataKey="sharpe" name="夏普比率" stroke={CHART_NEUTRAL} strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : null}
          <Table
            size="small"
            rowKey={(record) => `${record.window_id}-${record.test_start}`}
            dataSource={walkResult.window_results || []}
            columns={walkColumns}
            pagination={{ pageSize: 5, showSizeChanger: false }}
            onRow={(record) => {
              const rowKey = `${record.window_id}-${record.test_start}`;
              return {
                onClick: () => setFocusedWalkWindowKey(rowKey),
                style: {
                  cursor: 'pointer',
                  background: focusedWalkWindowKey === rowKey ? 'rgba(14, 165, 233, 0.12)' : undefined,
                },
              };
            }}
          />
        </Space>
      ) : (
        <Empty description="运行滚动前瞻分析后，这里会显示各窗口表现和聚合结果。" />
      )}
    </Card>
  );
}

export { WalkForwardForm, WalkForwardResults };
