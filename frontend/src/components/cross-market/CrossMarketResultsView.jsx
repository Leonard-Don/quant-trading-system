/**
 * Full results canvas for the cross-market backtest panel: the result banners,
 * the headline statistics, the diagnostics / universe / hedge cards, the
 * execution and liquidity tables, the recharts visualisations, the trade /
 * correlation / contribution tables and the allocation / constraint overlays.
 *
 * Pure presentational split (layer 2): `results` plus every derived column
 * definition and meta resolver are computed in the host panel and passed down.
 * Extracted verbatim from CrossMarketBacktestPanel.jsx so behaviour matches.
 */

import { Alert, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from 'antd';
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

import CrossMarketDiagnosticsSection from './CrossMarketDiagnosticsSection';
import CrossMarketBasketSummaryCard from './CrossMarketBasketSummaryCard';
import { ASSET_CLASS_LABELS } from '../../utils/crossMarketDefaults';
import {
  formatBiasQualityLabel,
  formatConstructionMode,
  formatExecutionChannel,
  formatSignalLabel,
  formatSignalList,
  formatStatusLabel,
  formatTemplateTheme,
  formatTradeAction,
  formatVenue,
} from '../../utils/crossMarketFormatters';
import { getSelectionQualityMeta } from '../../utils/crossMarketMeta';
import { extractCoreLegPressure } from '../../utils/crossMarketReviewHelpers';
import { formatCurrency, formatPercentage, getValueColor } from '../../utils/formatting';

const { Text } = Typography;

function CrossMarketResultsView({
  results,
  selectedTemplate,
  meta,
  quality,
  concentrationMeta,
  liquidityMeta,
  marginMeta,
  betaMeta,
  cointegrationMeta,
  calendarMeta,
  stressMeta,
  executionBatchColumns,
  executionRouteColumns,
  providerAllocationColumns,
  venueAllocationColumns,
  stressScenarioColumns,
  allocationOverlayColumns,
  correlationColumns,
  contributionColumns,
  assetContributionRows,
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Alert
        type={results.total_return >= 0 ? 'success' : 'warning'}
        showIcon
        message={`跨市场结果已生成${
          results.allocation_overlay?.selection_quality?.label && results.allocation_overlay.selection_quality.label !== 'original'
            ? ' · 复核型结果'
            : ''
        }`}
        description={`样本区间 ${results.price_matrix_summary.start_date} 至 ${results.price_matrix_summary.end_date}，共 ${results.price_matrix_summary.row_count} 个对齐交易日。${
          selectedTemplate?.recentComparisonLead
            ? ` 最近两版：${selectedTemplate.recentComparisonLead}`
            : ''
        }${
          results.allocation_overlay?.selection_quality?.label && results.allocation_overlay.selection_quality.label !== 'original'
            ? ` 当前结果按 ${formatStatusLabel(results.allocation_overlay.selection_quality.label)} 强度运行，应作为复核型结果理解。`
            : ''
        }${
          results.allocation_overlay?.input_reliability?.action_hint
            ? ` ${results.allocation_overlay.input_reliability.action_hint}`
            : ''
        }`}
      />

      {results.allocation_overlay?.selection_quality ? (
        <Alert
          type={getSelectionQualityMeta(results.allocation_overlay.selection_quality.label).type}
          showIcon
          message={getSelectionQualityMeta(results.allocation_overlay.selection_quality.label).title}
          description={`推荐强度 ${Number(results.allocation_overlay.selection_quality.base_recommendation_score || 0).toFixed(2)} → ${Number(results.allocation_overlay.selection_quality.effective_recommendation_score || 0).toFixed(2)}${
            results.allocation_overlay.selection_quality.base_recommendation_tier
              ? ` · ${results.allocation_overlay.selection_quality.base_recommendation_tier} → ${results.allocation_overlay.selection_quality.effective_recommendation_tier || '-'}`
              : ''
          }${
            results.allocation_overlay.selection_quality.ranking_penalty
              ? ` · 惩罚 ${Number(results.allocation_overlay.selection_quality.ranking_penalty || 0).toFixed(2)}`
              : ''
          }${
            results.allocation_overlay.selection_quality.reason
              ? ` · ${results.allocation_overlay.selection_quality.reason}`
              : ''
          }${
            results.allocation_overlay.input_reliability?.posture
              ? ` · ${formatStatusLabel(results.allocation_overlay.input_reliability.posture)}`
              : ''
          }${
            results.allocation_overlay.input_reliability?.action_hint
              ? ` · ${results.allocation_overlay.input_reliability.action_hint}`
              : ''
          }`}
        />
      ) : null}

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
          <Card variant="borderless" className="workspace-panel">
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
          <Card variant="borderless" className="workspace-panel">
            <Statistic
              title="最终净值"
              value={results.final_value}
              precision={2}
              formatter={(value) => formatCurrency(Number(value || 0))}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card variant="borderless" className="workspace-panel">
            <Statistic
              title="夏普比率"
              value={results.sharpe_ratio}
              precision={2}
            />
          </Card>
        </Col>
      </Row>

      <CrossMarketDiagnosticsSection
        results={results}
        meta={meta}
        quality={quality}
        ASSET_CLASS_LABELS={ASSET_CLASS_LABELS}
        concentrationMeta={concentrationMeta}
        liquidityMeta={liquidityMeta}
        marginMeta={marginMeta}
        betaMeta={betaMeta}
        cointegrationMeta={cointegrationMeta}
        calendarMeta={calendarMeta}
        stressMeta={stressMeta}
        formatCurrency={formatCurrency}
        formatPercentage={formatPercentage}
        formatVenue={formatVenue}
        formatConstructionMode={formatConstructionMode}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="资产宇宙摘要" variant="borderless" className="workspace-panel">
            <Row gutter={[16, 16]}>
              <Col span={8}>
                <Statistic
                  title="资产数量"
                  value={results.asset_universe?.asset_count || 0}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="多头数量"
                  value={results.asset_universe?.by_side?.long || 0}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="空头数量"
                  value={results.asset_universe?.by_side?.short || 0}
                />
              </Col>
            </Row>
            <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {Object.entries(results.asset_universe?.by_asset_class || {}).map(([key, value]) => (
                <Tag key={key}>{ASSET_CLASS_LABELS[key] || key} · {value}</Tag>
              ))}
              {Object.entries(results.asset_universe?.execution_channels || {}).map(([key, value]) => (
                <Tag color="cyan" key={key}>{formatExecutionChannel(key)} · {value}</Tag>
              ))}
              {Object.entries(results.asset_universe?.providers || {}).map(([key, value]) => (
                <Tag color="blue" key={key}>{key} · {value}</Tag>
              ))}
              {(results.asset_universe?.currencies || []).map((currency) => (
                <Tag color="blue" key={currency}>{currency}</Tag>
              ))}
            </div>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="对冲组合画像" variant="borderless" className="workspace-panel">
            <Row gutter={[16, 16]}>
              <Col span={8}>
                <Statistic
                  title="总暴露"
                  value={(results.hedge_portfolio?.gross_exposure || 0) * 100}
                  precision={2}
                  suffix="%"
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="净暴露"
                  value={(results.hedge_portfolio?.net_exposure || 0) * 100}
                  precision={2}
                  suffix="%"
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="平均对冲比"
                  value={results.hedge_portfolio?.hedge_ratio?.average || 0}
                  precision={2}
                />
              </Col>
            </Row>
            <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
              <Col span={8}>
                <Statistic
                  title="Beta"
                  value={results.hedge_portfolio?.beta_neutrality?.beta || 0}
                  precision={2}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="Beta 偏离"
                  value={(results.hedge_portfolio?.beta_neutrality?.beta_gap || 0) * 100}
                  precision={2}
                  suffix="pp"
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="滚动 Beta"
                  value={results.hedge_portfolio?.beta_neutrality?.rolling_beta_last || 0}
                  precision={2}
                />
              </Col>
            </Row>
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Text type="secondary">
                多头权重 {formatPercentage(results.hedge_portfolio?.long_weight || 0)} ·
                空头权重 {formatPercentage(results.hedge_portfolio?.short_weight || 0)} ·
                有效空头 {formatPercentage(results.hedge_portfolio?.effective_short_weight || 0)}
              </Text>
              <Text type="secondary">
                对冲比区间 {Number(results.hedge_portfolio?.hedge_ratio?.min || 0).toFixed(2)} ~ {Number(results.hedge_portfolio?.hedge_ratio?.max || 0).toFixed(2)}
              </Text>
              {results.hedge_portfolio?.beta_neutrality?.reason ? (
                <Text type="secondary">
                  {results.hedge_portfolio.beta_neutrality.reason}
                </Text>
              ) : null}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="执行批次计划" variant="borderless">
            <Table
              size="small"
              rowKey="route_key"
              pagination={false}
              dataSource={results.execution_plan?.batches || []}
              locale={{ emptyText: '暂无执行批次' }}
              columns={executionBatchColumns}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="逐资产执行路由" variant="borderless">
            <Table
              size="small"
              rowKey={(record) => `${record.symbol}-${record.side}`}
              pagination={{ pageSize: 6, showSizeChanger: false }}
              dataSource={results.execution_plan?.routes || []}
              locale={{ emptyText: '暂无执行路由' }}
              columns={executionRouteColumns}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="数据源资金分布" variant="borderless">
            <Table
              size="small"
              rowKey="key"
              pagination={false}
              dataSource={results.execution_plan?.provider_allocation || []}
              locale={{ emptyText: '暂无数据源分布' }}
              columns={providerAllocationColumns}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="交易场所资金分布" variant="borderless">
            <Table
              size="small"
              rowKey="key"
              pagination={false}
              dataSource={results.execution_plan?.venue_allocation || []}
              locale={{ emptyText: '暂无交易场所分布' }}
              columns={venueAllocationColumns}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="流动性概况" variant="borderless">
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Space wrap size={[8, 8]}>
                <Tag color={liquidityMeta.color}>{liquidityMeta.label}</Tag>
                <Tag color="cyan">
                  最大日成交额占用 {(Number(results.execution_plan?.liquidity_summary?.max_adv_usage || 0) * 100).toFixed(2)}%
                </Tag>
                <Tag color="orange">
                  关注路由 {results.execution_plan?.liquidity_summary?.watch_route_count || 0}
                </Tag>
                <Tag color="red">
                  紧张路由 {results.execution_plan?.liquidity_summary?.stretched_route_count || 0}
                </Tag>
              </Space>
              {results.execution_plan?.liquidity_summary?.reason ? (
                <Text type="secondary">{results.execution_plan.liquidity_summary.reason}</Text>
              ) : null}
              {results.execution_plan?.liquidity_summary?.largest_adv_route ? (
                <Text type="secondary">
                  最紧路由 {results.execution_plan.liquidity_summary.largest_adv_route.symbol}
                  {' · '}
                  日成交额占用 {(Number(results.execution_plan.liquidity_summary.largest_adv_route.adv_usage || 0) * 100).toFixed(2)}%
                  {' · '}
                  日均成交额 {formatCurrency(Number(results.execution_plan.liquidity_summary.largest_adv_route.avg_daily_notional || 0))}
                </Text>
              ) : null}
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="多市场日历概况" variant="borderless">
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Space wrap size={[8, 8]}>
                <Tag color={calendarMeta.color}>{calendarMeta.label}</Tag>
                <Tag color="cyan">
                  最大错位 {(Number(results.data_alignment?.calendar_diagnostics?.max_mismatch_ratio || 0) * 100).toFixed(2)}%
                </Tag>
              </Space>
              {results.data_alignment?.calendar_diagnostics?.reason ? (
                <Text type="secondary">{results.data_alignment.calendar_diagnostics.reason}</Text>
              ) : null}
              <Table
                size="small"
                rowKey="venue"
                pagination={false}
                dataSource={results.data_alignment?.calendar_diagnostics?.rows || []}
                locale={{ emptyText: '暂无日历错位信息' }}
                columns={[
                  {
                    title: '交易场所',
                    dataIndex: 'venue',
                    key: 'venue',
                    render: (value) => formatVenue(value),
                  },
                  { title: '活跃日', dataIndex: 'active_dates', key: 'active_dates' },
                  { title: '共享日', dataIndex: 'shared_dates', key: 'shared_dates' },
                  {
                    title: '错位率',
                    dataIndex: 'mismatch_ratio',
                    key: 'mismatch_ratio',
                    render: (value) => formatPercentage(Number(value || 0)),
                  },
                ]}
              />
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title="执行压力测试" variant="borderless">
            <Table
              size="small"
              rowKey="label"
              pagination={false}
              dataSource={results.execution_plan?.execution_stress?.scenarios || []}
              locale={{ emptyText: '暂无压力测试结果' }}
              columns={stressScenarioColumns}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="保证金与杠杆画像" variant="borderless">
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Space wrap size={[8, 8]}>
                <Tag color={marginMeta.color}>{marginMeta.label}</Tag>
                <Tag color="volcano">
                  保证金 {(Number(results.execution_plan?.margin_summary?.utilization || 0) * 100).toFixed(2)}%
                </Tag>
                <Tag color="purple">
                  总杠杆 {Number(results.execution_plan?.margin_summary?.gross_leverage || 0).toFixed(2)}x
                </Tag>
                <Tag color="blue">
                  空头 {formatCurrency(Number(results.execution_plan?.margin_summary?.short_notional || 0))}
                </Tag>
                <Tag color="cyan">
                  期货 {formatCurrency(Number(results.execution_plan?.margin_summary?.futures_notional || 0))}
                </Tag>
              </Space>
              {results.execution_plan?.margin_summary?.reason ? (
                <Text type="secondary">{results.execution_plan.margin_summary.reason}</Text>
              ) : null}
              {results.execution_plan?.margin_summary?.max_margin_route ? (
                <Text type="secondary">
                  最大保证金路由 {results.execution_plan.margin_summary.max_margin_route.symbol}
                  {' · '}
                  {formatCurrency(Number(results.execution_plan.margin_summary.max_margin_route.margin_requirement || 0))}
                  {' · '}
                  保证金率 {(Number(results.execution_plan.margin_summary.max_margin_route.margin_rate || 0) * 100).toFixed(2)}%
                </Text>
              ) : null}
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card title="组合净值曲线" variant="borderless" className="workspace-panel workspace-chart-card">
            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer width="100%" height={320} minWidth={320} minHeight={320}>
                <LineChart data={results.portfolio_curve}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" minTickGap={32} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="total" name="组合净值" stroke="#1677ff" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="长短腿累计收益" variant="borderless" className="workspace-panel workspace-chart-card">
            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer width="100%" height={320} minWidth={320} minHeight={320}>
                <BarChart
                  data={[
                    {
                      leg: '多头',
                      value: (results.leg_performance.long.cumulative_return || 0) * 100,
                    },
                    {
                      leg: '空头',
                      value: (results.leg_performance.short.cumulative_return || 0) * 100,
                    },
                    {
                      leg: '价差',
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
          <Card title="价差与 Z 分数" variant="borderless" className="workspace-panel workspace-chart-card">
            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer width="100%" height={320} minWidth={320} minHeight={320}>
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
            <Card title="对冲比率" variant="borderless">
              <div style={{ width: '100%', height: 320 }}>
                <ResponsiveContainer width="100%" height={280} minWidth={320} minHeight={280}>
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
          <Card title="交易记录" variant="borderless">
            <Table
              size="small"
              rowKey={(record) => [
                record.date,
                record.type || record.action,
                record.symbol,
                record.price,
                record.quantity ?? record.value,
              ].filter(Boolean).join('-')}
              dataSource={results.trades || []}
              locale={{ emptyText: '暂无交易记录' }}
              pagination={{ pageSize: 6, showSizeChanger: false }}
              columns={[
                { title: '日期', dataIndex: 'date', key: 'date' },
                {
                  title: '动作',
                  dataIndex: 'type',
                  key: 'type',
                  render: (value) => (
                    <Tag color={String(value).includes('OPEN') ? 'blue' : 'orange'}>
                      {formatTradeAction(value)}
                    </Tag>
                  ),
                },
                {
                  title: '价差',
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
                  title: '盈亏',
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
          <Card title="资产相关性矩阵" variant="borderless">
            <Table
              size="small"
              scroll={{ x: true }}
              locale={{ emptyText: '暂无相关性数据' }}
              pagination={false}
              rowKey="symbol"
              dataSource={results.correlation_matrix.rows || []}
              columns={correlationColumns}
            />
          </Card>
        </Col>
      </Row>

      <Card title="资产贡献度" variant="borderless">
        <Table
          size="small"
          rowKey="symbol"
          pagination={false}
          locale={{ emptyText: '暂无贡献度数据' }}
          dataSource={assetContributionRows}
          columns={contributionColumns}
        />
      </Card>

      <CrossMarketBasketSummaryCard
        results={results}
        ASSET_CLASS_LABELS={ASSET_CLASS_LABELS}
        formatPercentage={formatPercentage}
      />

      {results.allocation_overlay ? (
        <Card title="权重偏置对照" variant="borderless">
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space wrap size={[8, 8]}>
              <Tag color={results.allocation_overlay.allocation_mode === 'macro_bias' ? 'green' : 'default'}>
                {results.allocation_overlay.allocation_mode === 'macro_bias' ? '宏观偏置' : '模板原始权重'}
              </Tag>
              {results.allocation_overlay.theme ? <Tag color="blue">{formatTemplateTheme(results.allocation_overlay.theme)}</Tag> : null}
              {results.allocation_overlay.bias_strength ? <Tag color="green">偏置 {Number(results.allocation_overlay.bias_strength).toFixed(1)}pp</Tag> : null}
              {results.allocation_overlay.compression_summary?.label && results.allocation_overlay.compression_summary.label !== 'full' ? (
                <Tag color={results.allocation_overlay.compression_summary.label === 'compressed' ? 'orange' : 'gold'}>
                  压缩 {formatBiasQualityLabel(results.allocation_overlay.compression_summary.label)}
                </Tag>
              ) : null}
            </Space>
            {results.allocation_overlay.bias_summary ? (
              <Text>{results.allocation_overlay.bias_summary}</Text>
            ) : null}
            {results.allocation_overlay.compression_summary ? (
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <Text type="secondary">
                  原始偏置 {Number(results.allocation_overlay.compression_summary.raw_bias_strength || 0).toFixed(1)}pp
                  {' · '}
                  生效偏置 {Number(results.allocation_overlay.compression_summary.effective_bias_strength || 0).toFixed(1)}pp
                  {' · '}
                  收缩 {Number(results.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp
                  {' · '}
                  比例 {(Number(results.allocation_overlay.compression_summary.compression_ratio || 0) * 100).toFixed(1)}%
                </Text>
                {results.allocation_overlay.compression_summary.reason ? (
                  <Text type="secondary">
                    {results.allocation_overlay.compression_summary.reason}
                  </Text>
                ) : null}
                <Text type="secondary">
                  受影响资产 {results.allocation_overlay.compressed_asset_count || 0} 个
                  {results.allocation_overlay.compressed_assets?.length
                    ? ` · ${results.allocation_overlay.compressed_assets.join('、')}`
                    : ''}
                </Text>
                {results.allocation_overlay.selection_quality?.reason ? (
                  <Text type="secondary">
                    推荐降级 {Number(results.allocation_overlay.selection_quality.base_recommendation_score || 0).toFixed(2)}
                    →{Number(results.allocation_overlay.selection_quality.effective_recommendation_score || 0).toFixed(2)}
                    {results.allocation_overlay.selection_quality.effective_recommendation_tier
                      ? ` · ${formatStatusLabel(results.allocation_overlay.selection_quality.effective_recommendation_tier)}`
                      : ''}
                    {' · '}
                    {results.allocation_overlay.selection_quality.reason}
                  </Text>
                ) : null}
              </Space>
            ) : null}
            {results.allocation_overlay.bias_highlights?.length ? (
              <Space wrap size={[6, 6]}>
                {results.allocation_overlay.bias_highlights.map((item) => (
                  <Tag key={item} color="green">{formatSignalLabel(item)}</Tag>
                ))}
              </Space>
            ) : null}
            {results.allocation_overlay.bias_actions?.length ? (
              <Space wrap size={[6, 6]}>
                {results.allocation_overlay.bias_actions.map((item) => (
                  <Tag key={`${item.side}-${item.symbol}`} color={item.action === 'increase' ? 'green' : 'orange'}>
                    {item.action === 'increase' ? '增配' : '减配'} {item.symbol}
                  </Tag>
                ))}
              </Space>
            ) : null}
            {results.allocation_overlay.driver_summary?.length ? (
              <Space wrap size={[6, 6]}>
                {results.allocation_overlay.driver_summary.map((item) => (
                  <Tag key={item.key} color="purple">
                    {item.label} {Number(item.value || 0).toFixed(2)}
                  </Tag>
                ))}
              </Space>
            ) : null}
            {results.allocation_overlay.dominant_drivers?.length ? (
              <Space wrap size={[6, 6]}>
                {results.allocation_overlay.dominant_drivers.map((item) => (
                  <Tag key={`dominant-${item.key}`} color="magenta">
                    主导 {item.label}
                  </Tag>
                ))}
              </Space>
            ) : null}
            {results.allocation_overlay.execution_posture ? (
              <Text type="secondary">执行姿态：{formatSignalLabel(results.allocation_overlay.execution_posture)}</Text>
            ) : null}
            {results.allocation_overlay.theme_core ? (
              <Text type="secondary">核心腿：{formatSignalList(results.allocation_overlay.theme_core)}</Text>
            ) : null}
            {extractCoreLegPressure(results.allocation_overlay).affected ? (
              <Text type="secondary">核心腿受压：{extractCoreLegPressure(results.allocation_overlay).summary}</Text>
            ) : null}
            {results.allocation_overlay.theme_support ? (
              <Text type="secondary">辅助腿：{formatSignalList(results.allocation_overlay.theme_support)}</Text>
            ) : null}
            {results.allocation_overlay.policy_execution?.active ? (
              <Text type="secondary">
                政策执行：{formatStatusLabel(results.allocation_overlay.policy_execution.label)}
                {results.allocation_overlay.policy_execution.top_department
                  ? ` · ${results.allocation_overlay.policy_execution.top_department}`
                  : ''}
                {results.allocation_overlay.policy_execution.risk_budget_scale !== undefined
                  ? ` · 风险预算 ${Number(results.allocation_overlay.policy_execution.risk_budget_scale || 1).toFixed(2)}x`
                  : ''}
                {results.allocation_overlay.policy_execution.reason
                  ? ` · ${results.allocation_overlay.policy_execution.reason}`
                  : ''}
              </Text>
            ) : null}
            {results.allocation_overlay.source_mode_summary?.active ? (
              <Text type="secondary">
                来源治理：{formatStatusLabel(results.allocation_overlay.source_mode_summary.label)}
                {results.allocation_overlay.source_mode_summary.dominant
                  ? ` · ${results.allocation_overlay.source_mode_summary.dominant}`
                  : ''}
                {results.allocation_overlay.source_mode_summary.risk_budget_scale !== undefined
                  ? ` · 风险预算 ${Number(results.allocation_overlay.source_mode_summary.risk_budget_scale || 1).toFixed(2)}x`
                  : ''}
                {results.allocation_overlay.source_mode_summary.reason
                  ? ` · ${results.allocation_overlay.source_mode_summary.reason}`
                  : ''}
              </Text>
            ) : null}
            <Text type="secondary">
              偏移资产 {results.allocation_overlay.shifted_asset_count || 0} 个 · 最大偏移 {(Number(results.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
            </Text>
            {results.allocation_overlay.side_bias_summary ? (
              <Text type="secondary">
                多头 {formatPercentage(Number(results.allocation_overlay.side_bias_summary.long_raw_weight || 0))}→{formatPercentage(Number(results.allocation_overlay.side_bias_summary.long_effective_weight || 0))}
                {' · '}
                空头 {formatPercentage(Number(results.allocation_overlay.side_bias_summary.short_raw_weight || 0))}→{formatPercentage(Number(results.allocation_overlay.side_bias_summary.short_effective_weight || 0))}
              </Text>
            ) : null}
            <Table
              size="small"
              rowKey={(record) => `${record.symbol}-${record.side}`}
              pagination={false}
              locale={{ emptyText: '暂无权重偏置对照' }}
              dataSource={results.allocation_overlay.rows || []}
              columns={allocationOverlayColumns}
            />
            {results.allocation_overlay.signal_attribution?.length ? (
              <Table
                size="small"
                rowKey={(record) => `${record.side}-${record.symbol}`}
                pagination={false}
                locale={{ emptyText: '暂无归因说明' }}
                dataSource={results.allocation_overlay.signal_attribution}
                columns={[
                  { title: '资产', dataIndex: 'symbol', key: 'symbol' },
                  {
                    title: '方向',
                    dataIndex: 'side',
                    key: 'side',
                    render: (value) => <Tag color={value === 'long' ? 'green' : 'volcano'}>{value === 'long' ? '多头' : '空头'}</Tag>,
                  },
                  {
                    title: '权重乘数',
                    dataIndex: 'multiplier',
                    key: 'multiplier',
                    render: (value) => Number(value || 0).toFixed(2),
                  },
                  {
                    title: '归因',
                    dataIndex: 'reasons',
                    key: 'reasons',
                    render: (value) => (value || []).join('；') || '无显著偏置',
                  },
                  {
                    title: '分解',
                    dataIndex: 'breakdown',
                    key: 'breakdown',
                    render: (value) => (value || []).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('；') || '无',
                  },
                ]}
                style={{ marginTop: 12 }}
              />
            ) : null}
          </Space>
        </Card>
      ) : null}
      {results.constraint_overlay?.applied ? (
        <Card title="组合约束落地" variant="borderless">
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space wrap size={[8, 8]}>
              {results.constraint_overlay.constraints?.max_single_weight ? (
                <Tag color="blue">
                  单资产上限 {(Number(results.constraint_overlay.constraints.max_single_weight || 0) * 100).toFixed(1)}%
                </Tag>
              ) : null}
              {results.constraint_overlay.constraints?.min_single_weight ? (
                <Tag color="purple">
                  单资产下限 {(Number(results.constraint_overlay.constraints.min_single_weight || 0) * 100).toFixed(1)}%
                </Tag>
              ) : null}
              <Tag color={results.constraint_overlay.binding_count ? 'orange' : 'green'}>
                触发约束 {results.constraint_overlay.binding_count || 0} 个
              </Tag>
            </Space>
            <Text type="secondary">
              最大约束偏移 {(Number(results.constraint_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
            </Text>
            {results.constraint_overlay.binding_assets?.length ? (
              <Space wrap size={[6, 6]}>
                {results.constraint_overlay.binding_assets.map((symbol) => (
                  <Tag key={`binding-${symbol}`} color="orange">{symbol}</Tag>
                ))}
              </Space>
            ) : null}
            <Table
              size="small"
              rowKey={(record) => `${record.symbol}-${record.side}`}
              pagination={false}
              locale={{ emptyText: '暂无约束调整' }}
              dataSource={results.constraint_overlay.rows || []}
              columns={[
                { title: '资产', dataIndex: 'symbol', key: 'symbol' },
                {
                  title: '方向',
                  dataIndex: 'side',
                  key: 'side',
                  render: (value) => <Tag color={value === 'long' ? 'green' : 'volcano'}>{value === 'long' ? '多头' : '空头'}</Tag>,
                },
                {
                  title: '原始权重',
                  dataIndex: 'base_weight',
                  key: 'base_weight',
                  render: (value) => formatPercentage(Number(value || 0)),
                },
                {
                  title: '约束后',
                  dataIndex: 'constrained_weight',
                  key: 'constrained_weight',
                  render: (value) => formatPercentage(Number(value || 0)),
                },
                {
                  title: '变化',
                  dataIndex: 'delta_weight',
                  key: 'delta_weight',
                  render: (value) => (
                    <span style={{ color: getValueColor(Number(value || 0)) }}>
                      {Number(value || 0) >= 0 ? '+' : ''}{formatPercentage(Number(value || 0))}
                    </span>
                  ),
                },
                {
                  title: '触发',
                  dataIndex: 'binding',
                  key: 'binding',
                  render: (value) => (value ? <Tag color={value === 'max' ? 'red' : 'purple'}>{value === 'max' ? '上限' : value === 'min' ? '下限' : value}</Tag> : '-'),
                },
              ]}
            />
          </Space>
        </Card>
      ) : null}
    </div>
  );
}

export default CrossMarketResultsView;
