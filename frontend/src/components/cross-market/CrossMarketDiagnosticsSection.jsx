import React from 'react';
import { Alert, Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd';

const { Text } = Typography;

function CrossMarketDiagnosticsSection({
  results,
  meta,
  quality,
  ASSET_CLASS_LABELS,
  concentrationMeta,
  liquidityMeta,
  marginMeta,
  betaMeta,
  cointegrationMeta,
  calendarMeta,
  stressMeta,
  formatCurrency,
  formatPercentage,
  formatVenue,
  formatConstructionMode,
}) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={12}>
        <Card title="数据对齐诊断" variant="borderless" className="workspace-panel">
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Statistic title="可交易日占比" value={(results.data_alignment?.tradable_day_ratio || 0) * 100} precision={2} suffix="%" />
            </Col>
            <Col span={8}>
              <Statistic title="丢弃日期数" value={results.data_alignment?.dropped_dates_count || 0} />
            </Col>
            <Col span={8}>
              <Statistic title="对齐后行数" value={results.data_alignment?.aligned_row_count || 0} />
            </Col>
          </Row>
          <Table
            style={{ marginTop: 16 }}
            size="small"
            rowKey="symbol"
            pagination={false}
            dataSource={results.data_alignment?.per_symbol || []}
            columns={[
              { title: '资产代码', dataIndex: 'symbol', key: 'symbol' },
              {
                title: '类别',
                dataIndex: 'asset_class',
                key: 'asset_class',
                render: (value) => ASSET_CLASS_LABELS[value] || value,
              },
              {
                title: 'Provider',
                dataIndex: 'provider',
                key: 'provider',
                render: (value) => <Tag color="blue">{value || '-'}</Tag>,
              },
              { title: '原始行数', dataIndex: 'raw_rows', key: 'raw_rows' },
              { title: '有效行数', dataIndex: 'valid_rows', key: 'valid_rows' },
              {
                title: '覆盖率',
                dataIndex: 'coverage_ratio',
                key: 'coverage_ratio',
                render: (value) => formatPercentage(Number(value || 0)),
              },
              {
                title: '日均成交额',
                dataIndex: 'avg_daily_notional',
                key: 'avg_daily_notional',
                render: (value) => formatCurrency(Number(value || 0)),
              },
              {
                title: 'Venue',
                dataIndex: 'venue',
                key: 'venue',
                render: (value) => formatVenue(value),
              },
            ]}
          />
        </Card>
      </Col>
      <Col xs={24} xl={12}>
        <Card title="执行诊断" variant="borderless" className="workspace-panel">
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Statistic title="换手率" value={results.execution_diagnostics?.turnover || 0} precision={2} />
            </Col>
            <Col span={8}>
              <Statistic title="成本拖累" value={(results.execution_diagnostics?.cost_drag || 0) * 100} precision={2} suffix="%" />
            </Col>
            <Col span={8}>
              <Statistic title="平均持有期" value={results.execution_diagnostics?.avg_holding_period || 0} precision={1} suffix=" 天" />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
            <Col span={8}>
              <Statistic title="执行路由数" value={results.execution_diagnostics?.route_count || results.execution_plan?.route_count || 0} />
            </Col>
            <Col span={8}>
              <Statistic title="批次数" value={(results.execution_plan?.batches || []).length} />
            </Col>
            <Col span={8}>
              <Statistic title="Provider 数" value={Object.keys(results.execution_plan?.by_provider || {}).length} />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
            <Col span={12}>
              <Statistic title="计划资金" value={results.execution_plan?.initial_capital || meta.initial_capital} formatter={(value) => formatCurrency(Number(value || 0))} />
            </Col>
            <Col span={12}>
              <Statistic title="平均对冲比" value={results.execution_plan?.avg_hedge_ratio || results.hedge_portfolio?.hedge_ratio?.average || 0} precision={2} />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
            <Col span={12}>
              <Statistic title="Lot 效率" value={(results.execution_diagnostics?.lot_efficiency || results.execution_plan?.sizing_summary?.lot_efficiency || 0) * 100} precision={2} suffix="%" />
            </Col>
            <Col span={12}>
              <Statistic title="残余资金" value={results.execution_diagnostics?.residual_notional || results.execution_plan?.sizing_summary?.total_residual_notional || 0} formatter={(value) => formatCurrency(Number(value || 0))} />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
            <Col span={12}>
              <Statistic title="最大 ADV 使用率" value={(results.execution_diagnostics?.max_adv_usage || results.execution_plan?.liquidity_summary?.max_adv_usage || 0) * 100} precision={2} suffix="%" />
            </Col>
            <Col span={12}>
              <Statistic title="流动性紧张路由" value={results.execution_diagnostics?.stretched_route_count || results.execution_plan?.liquidity_summary?.stretched_route_count || 0} />
            </Col>
          </Row>
          <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
            <Col span={12}>
              <Statistic title="保证金占用" value={(results.execution_diagnostics?.margin_utilization || results.execution_plan?.margin_summary?.utilization || 0) * 100} precision={2} suffix="%" />
            </Col>
            <Col span={12}>
              <Statistic title="Gross Leverage" value={results.execution_diagnostics?.gross_leverage || results.execution_plan?.margin_summary?.gross_leverage || 0} precision={2} suffix="x" />
            </Col>
          </Row>
          <div style={{ marginTop: 16 }}>
            <Tag color="purple">{formatConstructionMode(results.execution_diagnostics?.construction_mode || quality.construction_mode)}</Tag>
            <Tag color={concentrationMeta.color}>{concentrationMeta.label}</Tag>
            <Tag color={liquidityMeta.color}>{liquidityMeta.label}</Tag>
            <Tag color={marginMeta.color}>{marginMeta.label}</Tag>
            <Tag color={betaMeta.color}>{betaMeta.label}</Tag>
            <Tag color={cointegrationMeta.color}>{cointegrationMeta.label}</Tag>
            <Tag color={calendarMeta.color}>{calendarMeta.label}</Tag>
            {results.execution_diagnostics?.suggested_rebalance ? (
              <Tag color="geekblue">建议调仓 {results.execution_diagnostics.suggested_rebalance}</Tag>
            ) : null}
            <Text type="secondary"> 当前对冲构造模式</Text>
          </div>
          {results.execution_diagnostics?.concentration_reason ? (
            <Alert style={{ marginTop: 16 }} type={results.execution_diagnostics?.concentration_level === 'high' ? 'warning' : 'info'} showIcon message="执行集中度提示" description={results.execution_diagnostics.concentration_reason} />
          ) : null}
          {results.execution_diagnostics?.liquidity_reason ? (
            <Alert style={{ marginTop: 16 }} type={results.execution_diagnostics?.liquidity_level === 'stretched' ? 'warning' : 'info'} showIcon message="流动性容量提示" description={results.execution_diagnostics.liquidity_reason} />
          ) : null}
          {results.execution_diagnostics?.margin_reason ? (
            <Alert style={{ marginTop: 16 }} type={results.execution_diagnostics?.margin_level === 'aggressive' ? 'warning' : 'info'} showIcon message="保证金占用提示" description={results.execution_diagnostics.margin_reason} />
          ) : null}
          {results.execution_diagnostics?.beta_reason ? (
            <Alert style={{ marginTop: 16 }} type={results.execution_diagnostics?.beta_level === 'stretched' ? 'warning' : 'info'} showIcon message="Beta 中性提示" description={results.execution_diagnostics.beta_reason} />
          ) : null}
          {results.execution_diagnostics?.calendar_reason ? (
            <Alert style={{ marginTop: 16 }} type={results.execution_diagnostics?.calendar_level === 'stretched' ? 'warning' : 'info'} showIcon message="多市场日历提示" description={results.execution_diagnostics.calendar_reason} />
          ) : null}
          {results.execution_diagnostics?.cointegration_reason ? (
            <Alert style={{ marginTop: 16 }} type={results.execution_diagnostics?.cointegration_level === 'weak' ? 'warning' : 'info'} showIcon message="协整关系提示" description={results.execution_diagnostics.cointegration_reason} />
          ) : null}
          {Number(results.execution_diagnostics?.residual_notional || 0) > 0 ? (
            <Alert style={{ marginTop: 16 }} type="info" showIcon message="最小交易单位提示" description={`按最新价格和 lot size 换算后，预计有 ${formatCurrency(Number(results.execution_diagnostics?.residual_notional || 0))} 的名义金额无法精确贴合目标权重。`} />
          ) : null}
          {results.execution_diagnostics?.stress_test_flag ? (
            <Alert style={{ marginTop: 16 }} type={results.execution_diagnostics.stress_test_flag === 'high' ? 'warning' : 'info'} showIcon message={`压力测试最坏情景：${stressMeta.label}`} description={results.execution_diagnostics.stress_test_reason || '已根据资金放大情景评估路由拥挤度。'} />
          ) : null}
        </Card>
      </Col>
    </Row>
  );
}

export default CrossMarketDiagnosticsSection;
