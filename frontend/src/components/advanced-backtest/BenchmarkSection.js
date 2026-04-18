import React from 'react';
import { Alert, Card, Empty, Space, Table } from 'antd';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { getStrategyName } from '../../constants/strategies';
import { formatPercentage, formatCurrency } from '../../utils/formatting';

const CHART_POSITIVE = '#22c55e';
const CHART_NEGATIVE = '#ef4444';

function BenchmarkSection({
  benchmarkResult,
  benchmarkContext,
  benchmarkSummary,
  benchmarkChartData,
  benchmarkLoading,
}) {
  return (
    <Card className="workspace-panel workspace-chart-card" title="基准对照">
      {benchmarkResult?.data && benchmarkContext?.strategy ? (
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {benchmarkLoading ? (
            <Alert
              type="info"
              showIcon
              message="正在刷新基准对照"
              description="当前先保留上一版和买入持有的对比，新的基准结果返回后会自动替换。"
            />
          ) : null}
          <Alert
            type={benchmarkSummary?.beatBenchmark ? 'success' : 'warning'}
            showIcon
            message={`${getStrategyName(benchmarkContext.strategy)} vs 买入持有`}
            description={
              benchmarkSummary
                ? `${benchmarkContext.symbol} · ${benchmarkContext.dateRange?.filter(Boolean).join(' 至 ')}，超额收益 ${formatPercentage(benchmarkSummary.excessReturn)}，夏普差值 ${benchmarkSummary.sharpeDelta.toFixed(2)}，回撤差值 ${formatPercentage(-benchmarkSummary.drawdownDelta)}`
                : '当前结果不足以生成基准对照摘要。'
            }
          />
          {benchmarkChartData.length ? (
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={benchmarkChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                  <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                  <YAxis tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                  <RechartsTooltip />
                  <Legend />
                  <Bar dataKey="totalReturn" name="总收益率" fill={CHART_POSITIVE} />
                  <Bar dataKey="drawdown" name="最大回撤绝对值" fill={CHART_NEGATIVE} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          <Table
            size="small"
            pagination={false}
            rowKey={(record) => record.key}
            dataSource={Object.entries(benchmarkResult.data).map(([key, value]) => ({
              key,
              strategy: getStrategyName(key),
              total_return: value.total_return,
              sharpe_ratio: value.sharpe_ratio,
              max_drawdown: value.max_drawdown,
              final_value: value.final_value,
            }))}
            columns={[
              { title: '策略', dataIndex: 'strategy', key: 'strategy' },
              { title: '总收益率', dataIndex: 'total_return', key: 'total_return', render: (value) => formatPercentage(value || 0) },
              { title: '夏普比率', dataIndex: 'sharpe_ratio', key: 'sharpe_ratio', render: (value) => Number(value || 0).toFixed(2) },
              { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (value) => formatPercentage(value || 0) },
              { title: '最终价值', dataIndex: 'final_value', key: 'final_value', render: (value) => formatCurrency(value || 0) },
            ]}
          />
        </Space>
      ) : (
        <Empty description="运行基准对照后，这里会展示策略与买入持有的差异。" />
      )}
    </Card>
  );
}

export default BenchmarkSection;
