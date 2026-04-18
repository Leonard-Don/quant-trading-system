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
  Tag,
} from 'antd';
import { DownloadOutlined, ExperimentOutlined, PartitionOutlined } from '@ant-design/icons';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { getStrategyName, getStrategyParameterLabel, getStrategyDetails } from '../../constants/strategies';
import { formatPercentage, formatCurrency, getValueColor } from '../../utils/formatting';
import { DEFAULT_CAPITAL, DEFAULT_COMMISSION, DEFAULT_SLIPPAGE, getMetricValue } from '../../hooks/useAdvancedBacktestLab';
import dayjs from '../../utils/dayjs';

const { RangePicker } = DatePicker;

const CHART_POSITIVE = '#22c55e';
const CHART_NEGATIVE = '#ef4444';
const CHART_NEUTRAL = '#0ea5e9';

const renderBatchTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="chart-tooltip">
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{point.label}</div>
      <div>总收益率 {formatPercentage(point.totalReturn)}</div>
      <div>夏普比率 {Number(point.sharpe || 0).toFixed(2)}</div>
      <div>最大回撤 {formatPercentage(-Math.abs(point.drawdown || 0))}</div>
    </div>
  );
};

const batchRankingColumns = [
  {
    title: '任务',
    dataIndex: 'task_id',
    key: 'task_id',
    render: (_, record) => (
      <div>
        <div style={{ fontWeight: 700 }}>{record.research_label || getStrategyName(record.strategy)}</div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{record.symbol} · {getStrategyName(record.strategy)}</div>
      </div>
    ),
  },
  {
    title: '总收益率',
    dataIndex: ['metrics', 'total_return'],
    key: 'total_return',
    render: (value) => <span style={{ color: getValueColor(value || 0) }}>{formatPercentage(value || 0)}</span>,
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
    title: '最终价值',
    dataIndex: ['metrics', 'final_value'],
    key: 'final_value',
    render: (value) => formatCurrency(value || 0),
  },
  {
    title: '状态',
    dataIndex: 'success',
    key: 'success',
    render: (value, record) => value ? <Tag color="success">成功</Tag> : <Tag color="error">{record.error || '失败'}</Tag>,
  },
];

function BatchBacktestForm({
  batchForm,
  strategies,
  selectedBatchStrategies,
  strategyDefinitions,
  batchConfigs,
  updateBatchParam,
  batchLoading,
  handleRunBatch,
}) {
  return (
    <Card
      className="workspace-panel"
      title={(
        <div className="workspace-title">
          <div className="workspace-title__icon">
            <PartitionOutlined style={{ color: '#fff' }} />
          </div>
          <div>
            <div className="workspace-title__text">批量回测</div>
            <div className="workspace-title__hint">同一实验上下文下，一次性跑多策略并输出排名。</div>
          </div>
        </div>
      )}
    >
      <Form
        form={batchForm}
        layout="vertical"
        onFinish={handleRunBatch}
        initialValues={{
          symbol: 'AAPL',
          strategies: ['buy_and_hold', 'moving_average'],
          dateRange: [dayjs().subtract(1, 'year'), dayjs()],
          initial_capital: DEFAULT_CAPITAL,
          commission: DEFAULT_COMMISSION,
          slippage: DEFAULT_SLIPPAGE,
          ranking_metric: 'sharpe_ratio',
          top_n: 3,
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
            <Form.Item label="策略列表" name="strategies" rules={[{ required: true, message: '请选择至少一个策略' }]}>
              <Select
                mode="multiple"
                placeholder="选择要批量执行的策略"
                options={strategies.map((strategy) => ({
                  value: strategy.name,
                  label: getStrategyName(strategy.name),
                }))}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="初始资金" name="initial_capital">
              <InputNumber min={1000} step={1000} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={4}>
            <Form.Item label="手续费 (%)" name="commission">
              <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={4}>
            <Form.Item label="滑点 (%)" name="slippage">
              <InputNumber min={0} step={0.01} precision={2} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={12} md={4}>
            <Form.Item label="排名指标" name="ranking_metric">
              <Select
                options={[
                  { value: 'sharpe_ratio', label: '夏普比率' },
                  { value: 'total_return', label: '总收益率' },
                  { value: 'max_drawdown', label: '最大回撤' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={12} md={4}>
            <Form.Item label="保留前 N 名" name="top_n">
              <InputNumber min={1} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        {selectedBatchStrategies.length ? (
          <div className="workspace-analysis-stack" style={{ marginBottom: 16 }}>
            {selectedBatchStrategies.map((strategyName) => {
              const strategy = strategyDefinitions[strategyName];
              const entries = Object.entries(strategy?.parameters || {});
              return (
                <div key={strategyName} className="workspace-section">
                  <div className="workspace-section__header">
                    <div>
                      <div className="workspace-section__title">{getStrategyName(strategyName)}</div>
                      <div className="workspace-section__description">{getStrategyDetails(strategyName).summary}</div>
                    </div>
                  </div>
                  <div className="workspace-section__hint" style={{ marginBottom: 12 }}>
                    {getStrategyDetails(strategyName).marketFit}
                  </div>
                  {entries.length ? (
                    <Row gutter={[12, 12]}>
                      {entries.map(([key, config]) => (
                        <Col key={`${strategyName}-${key}`} xs={24} md={12}>
                          <div className="workspace-field-label">{getStrategyParameterLabel(key, config.description)}</div>
                          <InputNumber
                            value={batchConfigs[strategyName]?.[key] ?? config.default}
                            min={config.min}
                            max={config.max}
                            step={config.step || 0.01}
                            style={{ width: '100%' }}
                            onChange={(value) => updateBatchParam(strategyName, key, value)}
                          />
                        </Col>
                      ))}
                    </Row>
                  ) : (
                    <Alert message="该策略没有额外参数，将按默认规则执行。" type="info" showIcon />
                  )}
                </div>
              );
            })}
          </div>
        ) : null}

        <Button type="primary" htmlType="submit" icon={<ExperimentOutlined />} loading={batchLoading} block>
          运行批量回测
        </Button>
      </Form>
    </Card>
  );
}

function BatchBacktestResults({
  batchResult,
  batchRecords,
  batchRankingData,
  batchInsight,
  batchExperimentMeta,
  batchPendingMeta,
  batchLoading,
  focusedBatchRecord,
  focusedBatchTaskId,
  setFocusedBatchTaskId,
  handleSaveBatchHistory,
  handleExportBatch,
}) {
  return (
    <Card
      className="workspace-panel workspace-chart-card"
      title={batchExperimentMeta.title}
      extra={batchResult ? (
        <Space size="small">
          <Button size="small" onClick={handleSaveBatchHistory}>保存到历史</Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => handleExportBatch('csv')}>导出CSV</Button>
          <Button size="small" onClick={() => handleExportBatch('json')}>导出JSON</Button>
        </Space>
      ) : null}
    >
      {batchResult ? (
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {batchLoading ? (
            <Alert
              type="info"
              showIcon
              message={`正在刷新：${batchPendingMeta?.title || batchExperimentMeta.title}`}
              description="当前先保留上一版结果，新的批量实验完成后会自动替换。"
            />
          ) : null}
          <Alert type="info" showIcon message={batchExperimentMeta.title} description={batchExperimentMeta.description} />
          <div className="summary-strip">
            <div className="summary-strip__item">
              <span className="summary-strip__label">总任务数</span>
              <span className="summary-strip__value">{batchResult.summary?.total_tasks ?? 0}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">成功任务</span>
              <span className="summary-strip__value">{batchResult.summary?.successful ?? 0}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">平均收益</span>
              <span className="summary-strip__value">{formatPercentage(batchResult.summary?.average_return ?? 0)}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">平均夏普</span>
              <span className="summary-strip__value">{Number(batchResult.summary?.average_sharpe ?? 0).toFixed(2)}</span>
            </div>
          </div>
          {batchResult.summary?.best_result ? (
            <Alert
              type="success"
              showIcon
              message={`当前最佳策略：${getStrategyName(batchResult.summary.best_result.strategy)}`}
              description={`总收益 ${formatPercentage(batchResult.summary.best_result.total_return || 0)}，夏普 ${Number(batchResult.summary.best_result.sharpe_ratio || 0).toFixed(2)}`}
            />
          ) : null}
          {batchInsight ? (
            <Alert type={batchInsight.type} showIcon message={batchInsight.title} description={batchInsight.description} />
          ) : null}
          {focusedBatchRecord ? (
            <Alert
              type="info"
              showIcon
              message={`当前聚焦：${getStrategyName(focusedBatchRecord.strategy)} · ${focusedBatchRecord.symbol}`}
              description={`总收益 ${formatPercentage(getMetricValue(focusedBatchRecord, 'total_return'))}，夏普 ${Number(getMetricValue(focusedBatchRecord, 'sharpe_ratio')).toFixed(2)}，最终价值 ${formatCurrency(getMetricValue(focusedBatchRecord, 'final_value'))}`}
            />
          ) : null}
          {batchRankingData.length ? (
            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">策略排名图</div>
                  <div className="workspace-section__description">用收益率和夏普比率快速判断哪几个策略更值得继续深挖。</div>
                </div>
              </div>
              <div style={{ height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={batchRankingData}
                    margin={{ top: 8, right: 12, left: 8, bottom: 12 }}
                    onClick={(state) => {
                      const nextTaskId = state?.activePayload?.[0]?.payload?.taskId;
                      if (nextTaskId) setFocusedBatchTaskId(nextTaskId);
                    }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                    <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} interval={0} angle={-12} textAnchor="end" height={56} />
                    <YAxis yAxisId="left" tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                    <RechartsTooltip content={renderBatchTooltip} />
                    <Legend />
                    <Bar yAxisId="left" dataKey="totalReturn" name="总收益率">
                      {batchRankingData.map((entry) => (
                        <Cell
                          key={entry.key}
                          fill={entry.totalReturn >= 0 ? CHART_POSITIVE : CHART_NEGATIVE}
                          fillOpacity={!focusedBatchTaskId || focusedBatchTaskId === entry.taskId ? 1 : 0.35}
                          stroke={focusedBatchTaskId === entry.taskId ? '#f8fafc' : 'none'}
                          strokeWidth={focusedBatchTaskId === entry.taskId ? 2 : 0}
                        />
                      ))}
                    </Bar>
                    <Line yAxisId="right" type="monotone" dataKey="sharpe" name="夏普比率" stroke={CHART_NEUTRAL} strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : null}
          <Table
            size="small"
            rowKey={(record) => record.task_id}
            dataSource={batchRecords}
            columns={batchRankingColumns}
            pagination={false}
            onRow={(record) => ({
              onClick: () => setFocusedBatchTaskId(record.task_id),
              style: {
                cursor: 'pointer',
                background: focusedBatchTaskId === record.task_id ? 'rgba(14, 165, 233, 0.12)' : undefined,
              },
            })}
          />
        </Space>
      ) : (
        <Empty description="运行批量回测后，这里会显示汇总和排名。" />
      )}
    </Card>
  );
}

export { BatchBacktestForm, BatchBacktestResults };
