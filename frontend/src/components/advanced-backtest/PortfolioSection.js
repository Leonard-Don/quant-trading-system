import React from 'react';
import { Alert, Card, Col, Empty, Row, Space, Table, Tag } from 'antd';
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

import { getStrategyName } from '../../constants/strategies';
import { formatPercentage, formatCurrency } from '../../utils/formatting';
import { formatCompactNumber } from '../../hooks/useAdvancedBacktestLab';

const CHART_POSITIVE = '#22c55e';
const CHART_NEGATIVE = '#ef4444';
const CHART_NEUTRAL = '#0ea5e9';

function PortfolioSection({
  portfolioStrategyResult,
  portfolioChartData,
  portfolioPositionSnapshot,
  portfolioExposureSummary,
  portfolioLoading,
}) {
  return (
    <Card className="workspace-panel workspace-chart-card" title="组合级策略回测">
      {portfolioStrategyResult ? (
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          {portfolioLoading ? (
            <Alert
              type="info"
              showIcon
              message="正在刷新组合级结果"
              description="当前先保留上一版组合净值和暴露分析，新的回测完成后会自动替换。"
            />
          ) : null}
          <div className="summary-strip">
            <div className="summary-strip__item">
              <span className="summary-strip__label">组合收益</span>
              <span className="summary-strip__value">{formatPercentage(portfolioStrategyResult.total_return || 0)}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">年化收益</span>
              <span className="summary-strip__value">{formatPercentage(portfolioStrategyResult.annualized_return || 0)}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">最大回撤</span>
              <span className="summary-strip__value">{formatPercentage(portfolioStrategyResult.max_drawdown || 0)}</span>
            </div>
            <div className="summary-strip__item">
              <span className="summary-strip__label">夏普比率</span>
              <span className="summary-strip__value">{Number(portfolioStrategyResult.sharpe_ratio || 0).toFixed(2)}</span>
            </div>
          </div>
          <Alert
            type="info"
            showIcon
            message={`${getStrategyName(portfolioStrategyResult.strategy)} · 多资产组合`}
            description={`当前版本使用同一策略同时作用于多个标的，并按权重合成为组合净值。当前权重模式：${
              portfolioStrategyResult.portfolio_objective === 'max_sharpe'
                ? '最大夏普'
                : portfolioStrategyResult.portfolio_objective === 'min_volatility'
                  ? '最小波动'
                  : '等权组合'
            }。`}
          />
          {portfolioExposureSummary ? (
            <div className="summary-strip">
              <div className="summary-strip__item">
                <span className="summary-strip__label">总暴露</span>
                <span className="summary-strip__value">{formatPercentage(portfolioExposureSummary.grossExposure || 0)}</span>
              </div>
              <div className="summary-strip__item">
                <span className="summary-strip__label">净暴露</span>
                <span className="summary-strip__value">{formatPercentage(portfolioExposureSummary.netExposure || 0)}</span>
              </div>
              <div className="summary-strip__item">
                <span className="summary-strip__label">现金余额</span>
                <span className="summary-strip__value">{formatCurrency(portfolioExposureSummary.cash || 0)}</span>
              </div>
              <div className="summary-strip__item">
                <span className="summary-strip__label">活跃头寸</span>
                <span className="summary-strip__value">{portfolioExposureSummary.activePositions}</span>
              </div>
            </div>
          ) : null}
          {portfolioChartData.length ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={12}>
                <div style={{ height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={portfolioChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                      <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                      <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                      <RechartsTooltip />
                      <Line type="monotone" dataKey="total" name="组合净值" stroke={CHART_NEUTRAL} strokeWidth={2.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Col>
              <Col xs={24} xl={12}>
                <div style={{ height: 260 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={portfolioChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                      <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                      <YAxis
                        tickFormatter={(value) => formatPercentage(Number(value || 0))}
                        tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                      />
                      <RechartsTooltip formatter={(value) => formatPercentage(Number(value || 0))} />
                      <Legend />
                      <Line type="monotone" dataKey="grossExposure" name="总暴露" stroke={CHART_POSITIVE} strokeWidth={2.2} dot={false} />
                      <Line type="monotone" dataKey="netExposure" name="净暴露" stroke={CHART_NEGATIVE} strokeWidth={2.2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Col>
            </Row>
          ) : null}
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Table
                size="small"
                pagination={false}
                rowKey={(record) => record.symbol}
                dataSource={portfolioStrategyResult.portfolio_components || []}
                columns={[
                  { title: '标的', dataIndex: 'symbol', key: 'symbol' },
                  { title: '权重', dataIndex: 'weight', key: 'weight', render: (value) => formatPercentage(value || 0) },
                  { title: '总收益率', dataIndex: 'total_return', key: 'total_return', render: (value) => formatPercentage(value || 0) },
                  { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (value) => formatPercentage(value || 0) },
                  { title: '最终价值', dataIndex: 'final_value', key: 'final_value', render: (value) => formatCurrency(value || 0) },
                ]}
              />
            </Col>
            <Col xs={24} xl={12}>
              <Table
                size="small"
                pagination={false}
                rowKey={(record) => record.symbol}
                locale={{ emptyText: '当前没有活跃头寸' }}
                dataSource={portfolioPositionSnapshot}
                columns={[
                  { title: '标的', dataIndex: 'symbol', key: 'symbol' },
                  {
                    title: '方向',
                    dataIndex: 'direction',
                    key: 'direction',
                    render: (value) => <Tag color={value === '多头' ? 'green' : 'red'}>{value}</Tag>,
                  },
                  {
                    title: '持仓份额',
                    dataIndex: 'shares',
                    key: 'shares',
                    render: (value) => formatCompactNumber(value),
                  },
                  {
                    title: '目标权重',
                    dataIndex: 'targetWeight',
                    key: 'targetWeight',
                    render: (value) => formatPercentage(value || 0),
                  },
                ]}
              />
            </Col>
          </Row>
        </Space>
      ) : (
        <Empty description="运行组合级策略回测后，这里会展示组合表现和各资产贡献。" />
      )}
    </Card>
  );
}

export default PortfolioSection;
