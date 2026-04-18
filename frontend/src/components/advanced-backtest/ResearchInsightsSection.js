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

import { formatPercentage } from '../../utils/formatting';

function ResearchInsightsSection({
  robustnessScore,
  overfittingWarnings,
  researchConclusion,
  marketRegimeResult,
  marketRegimeInsight,
  marketRegimeChartData,
  marketRegimeLoading,
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
                {marketRegimeLoading ? (
                  <Alert
                    type="info"
                    showIcon
                    message="正在刷新市场状态分层结果"
                    description="当前先保留上一版分层表现，新的市场状态分析完成后会自动替换。"
                  />
                ) : null}
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
    </>
  );
}

export default ResearchInsightsSection;
