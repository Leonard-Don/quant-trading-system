import React from 'react';
import { Alert, Card, Col, Empty, Row, Space, Table } from 'antd';
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

import { formatCurrency, formatPercentage } from '../../utils/formatting';
import { getStrategyName } from '../../constants/strategies';

function ResearchInsightsSection({
  robustnessScore,
  overfittingWarnings,
  researchConclusion,
  marketRegimeResult,
  marketRegimeInsight,
  marketRegimeChartData,
  benchmarkResult,
  benchmarkContext,
  benchmarkSummary,
  benchmarkChartData,
  CHART_NEGATIVE,
  CHART_NEUTRAL,
  CHART_POSITIVE,
}) {
  return (
    <>
      <Row gutter={[20, 20]}>
        <Col xs={24} xl={9}>
          <Card className="workspace-panel workspace-chart-card" title="稳健性评分">
            {robustnessScore || overfittingWarnings.length || researchConclusion ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                {robustnessScore ? (
                  <>
                    <Alert
                      type={robustnessScore.score >= 75 ? 'success' : robustnessScore.score >= 55 ? 'info' : 'warning'}
                      showIcon
                      message={`稳健性评分 ${robustnessScore.score} / 100`}
                      description={`当前结论：${robustnessScore.level}稳健性。${robustnessScore.summary}`}
                    />
                    <div className="summary-strip">
                      {robustnessScore.dimensions.map((dimension) => (
                        <div className="summary-strip__item" key={dimension.key}>
                          <span className="summary-strip__label">{dimension.label}</span>
                          <span className="summary-strip__value">{dimension.score}</span>
                        </div>
                      ))}
                    </div>
                    <Table
                      size="small"
                      pagination={false}
                      rowKey={(record) => record.key}
                      dataSource={robustnessScore.dimensions}
                      columns={[
                        { title: '维度', dataIndex: 'label', key: 'label' },
                        { title: '得分', dataIndex: 'score', key: 'score', render: (value) => `${value}` },
                        { title: '说明', dataIndex: 'detail', key: 'detail' },
                      ]}
                    />
                  </>
                ) : null}
                {overfittingWarnings.length ? (
                  <div className="workspace-section">
                    <div className="workspace-section__header">
                      <div>
                        <div className="workspace-section__title">过拟合预警</div>
                        <div className="workspace-section__description">这些信号说明当前优势可能依赖少数参数、少数窗口或少数市场状态。</div>
                      </div>
                    </div>
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      {overfittingWarnings.map((warning) => (
                        <Alert key={warning.key} type="warning" showIcon message={warning.title} description={warning.description} />
                      ))}
                    </Space>
                  </div>
                ) : null}
                {researchConclusion ? (
                  <div className="workspace-section">
                    <div className="workspace-section__header">
                      <div>
                        <div className="workspace-section__title">自动研究结论</div>
                        <div className="workspace-section__description">把当前结果压缩成结论和下一步动作，减少人工读图和读表的成本。</div>
                      </div>
                    </div>
                    <Alert
                      type={overfittingWarnings.length ? 'warning' : 'success'}
                      showIcon
                      message={researchConclusion.title}
                      description={researchConclusion.summary}
                    />
                    <div className="summary-strip summary-strip--stack">
                      {researchConclusion.nextActions.map((action, index) => (
                        <div key={`${index + 1}-${action.slice(0, 12)}`} className="summary-strip__item">
                          <span className="summary-strip__label">下一步 {index + 1}</span>
                          <span className="summary-strip__value" style={{ whiteSpace: 'normal' }}>{action}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </Space>
            ) : (
              <Empty description="运行批量实验、滚动前瞻、基准对照或市场状态分析后，这里会给出稳健性评分、过拟合预警和自动研究结论。" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card className="workspace-panel workspace-chart-card" title="市场状态分层回测">
            {marketRegimeResult ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <div className="summary-strip">
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">市场状态数</span>
                    <span className="summary-strip__value">{marketRegimeResult.summary?.regime_count ?? 0}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">正收益状态</span>
                    <span className="summary-strip__value">{marketRegimeResult.summary?.positive_regimes ?? 0}</span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">平均阶段收益</span>
                    <span className="summary-strip__value">{formatPercentage(marketRegimeResult.summary?.average_regime_return ?? 0)}</span>
                  </div>
                </div>
                {marketRegimeInsight ? <Alert type={marketRegimeInsight.type} showIcon message={marketRegimeInsight.title} description={marketRegimeInsight.description} /> : null}
                {marketRegimeChartData.length ? (
                  <div style={{ height: 280 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={marketRegimeChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                        <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                        <YAxis tickFormatter={(value) => `${(Number(value || 0) * 100).toFixed(0)}%`} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                        <RechartsTooltip />
                        <Legend />
                        <Bar dataKey="strategyTotalReturn" name="策略收益" fill={CHART_POSITIVE} />
                        <Bar dataKey="marketTotalReturn" name="市场收益" fill={CHART_NEUTRAL} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : null}
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(record) => record.regime}
                  dataSource={marketRegimeResult.regimes || []}
                  columns={[
                    { title: '市场状态', dataIndex: 'regime', key: 'regime' },
                    { title: '天数', dataIndex: 'days', key: 'days' },
                    { title: '策略收益', dataIndex: 'strategy_total_return', key: 'strategy_total_return', render: (value) => formatPercentage(value || 0) },
                    { title: '市场收益', dataIndex: 'market_total_return', key: 'market_total_return', render: (value) => formatPercentage(value || 0) },
                    { title: '胜率', dataIndex: 'win_rate', key: 'win_rate', render: (value) => formatPercentage(value || 0) },
                    { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (value) => formatPercentage(value || 0) },
                  ]}
                />
              </Space>
            ) : (
              <Empty description="运行市场状态分层回测后，这里会展示策略在不同市场状态下的表现差异。" />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={12}>
          <Card className="workspace-panel workspace-chart-card" title="基准对照">
            {benchmarkResult?.data && benchmarkContext?.strategy ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
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
        </Col>
      </Row>
    </>
  );
}

export default ResearchInsightsSection;
