import React from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Progress,
  Row,
  Select,
  Skeleton,
  Slider,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  MinusOutlined,
  SwapOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ReferenceLine,
  Cell,
} from 'recharts';
import {
  ALIGNMENT_TAG_COLORS,
  DISPLAY_EMPTY,
} from '../../utils/pricingSectionConstants';
import {
  getPriceSourceLabel,
  parsePricingUniverseInput,
  resolveAnalysisSymbol,
  SCREENING_PRESETS,
} from '../../utils/pricingResearch';

const { Option } = Select;
const { Text: AntText, Paragraph: AntParagraph } = Typography;

export function SensitivityAnalysisCard({
  symbol,
  loading,
  error,
  sensitivity,
  controls,
  onControlChange,
  onRun,
}) {
  const matrix = sensitivity?.sensitivity_matrix || [];
  const heatmapRows = matrix.flatMap((row) => (row.cases || []).map((item) => ({
    key: `${row.growth}-${item.wacc}`,
    growth: row.growth,
    wacc: item.wacc,
    fair_value: item.fair_value,
  })));

  return (
    <Card title="敏感性分析 / What-If">
      <AntParagraph type="secondary">
        调整折现率、增长率和现金流转化率，观察公允价值如何变化。当前标的：{resolveAnalysisSymbol(symbol) || '未选择'}。
      </AntParagraph>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <AntText>WACC</AntText>
          <Slider min={5} max={15} step={0.1} value={controls.wacc} onChange={(value) => onControlChange((prev) => ({ ...prev, wacc: value }))} />
        </Col>
        <Col xs={24} md={12}>
          <AntText>初始增长率</AntText>
          <Slider min={2} max={25} step={0.5} value={controls.initialGrowth} onChange={(value) => onControlChange((prev) => ({ ...prev, initialGrowth: value }))} />
        </Col>
        <Col xs={24} md={12}>
          <AntText>终值增长率</AntText>
          <Slider min={1} max={5} step={0.1} value={controls.terminalGrowth} onChange={(value) => onControlChange((prev) => ({ ...prev, terminalGrowth: value }))} />
        </Col>
        <Col xs={24} md={12}>
          <AntText>FCF 转化率</AntText>
          <Slider min={50} max={95} step={1} value={controls.fcfMargin} onChange={(value) => onControlChange((prev) => ({ ...prev, fcfMargin: value }))} />
        </Col>
      </Row>
      <Space style={{ marginTop: 12, marginBottom: 12 }}>
        <Button type="primary" onClick={onRun} loading={loading}>刷新敏感性分析</Button>
        <Tag>{`WACC ${controls.wacc}%`}</Tag>
        <Tag>{`增长 ${controls.initialGrowth}%`}</Tag>
      </Space>
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!loading && !heatmapRows.length ? <Empty description="运行敏感性分析后查看不同假设下的公允价值变化" /> : null}
      {heatmapRows.length ? (
        <Table
          size="small"
          pagination={false}
          dataSource={heatmapRows}
          columns={[
            { title: '增长率', dataIndex: 'growth', render: (value) => `${Number(value).toFixed(1)}%` },
            { title: 'WACC', dataIndex: 'wacc', render: (value) => `${Number(value).toFixed(1)}%` },
            { title: '公允价值', dataIndex: 'fair_value', render: (value) => `$${Number(value || 0).toFixed(2)}` },
          ]}
        />
      ) : null}
    </Card>
  );
}

export function GapHistoryCard({ loading, error, historyData }) {
  const history = historyData?.history || [];
  const summary = historyData?.summary || {};

  return (
    <Card data-testid="pricing-gap-history-card" title="偏差历史时间序列">
      <AntParagraph type="secondary">
        用当前公允价值锚点回看过去一段时间的价格偏离轨迹，辅助判断均值回归和情绪扩张是否已经发生。
      </AntParagraph>
      {loading ? <Skeleton active paragraph={{ rows: 4 }} /> : null}
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!loading && !error && !history.length ? <Empty description="暂无历史偏差数据" /> : null}
      {history.length ? (
        <>
          <Space wrap size={8} style={{ marginBottom: 12 }}>
            <Tag>{`最新偏差 ${summary.latest_gap_pct > 0 ? '+' : ''}${Number(summary.latest_gap_pct || 0).toFixed(1)}%`}</Tag>
            <Tag color="red">{`最高溢价 ${Number(summary.max_gap_pct || 0).toFixed(1)}%`}</Tag>
            <Tag color="green">{`最低折价 ${Number(summary.min_gap_pct || 0).toFixed(1)}%`}</Tag>
          </Space>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={history} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" minTickGap={28} />
                <YAxis tickFormatter={(value) => `${value}%`} />
                <RechartsTooltip formatter={(value, name) => [name === 'gap_pct' ? `${Number(value).toFixed(2)}%` : `$${Number(value).toFixed(2)}`, name === 'gap_pct' ? '偏差' : '价格']} />
                <ReferenceLine y={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="gap_pct" stroke="#1677ff" strokeWidth={2} dot={false} name="gap_pct" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : null}
    </Card>
  );
}

export function PeerComparisonCard({ loading, error, peerComparison, onInspect }) {
  const target = peerComparison?.target || null;
  const peers = peerComparison?.peers || [];
  const rows = [target, ...peers].filter(Boolean).map((item) => ({ ...item, key: item.symbol }));
  const premiumChartData = rows.map((item) => ({
    symbol: item.symbol,
    premium_discount: Number(item.premium_discount || 0),
    is_target: item.is_target,
  }));
  const formatCurrency = (value) => (value === null || value === undefined || value === '' ? DISPLAY_EMPTY : `$${Number(value).toFixed(2)}`);

  return (
    <Card data-testid="pricing-peer-comparison-card" title="同行估值对比">
      <AntParagraph type="secondary">
        结合同行市值和核心倍数，快速判断当前标的是“自己贵”还是“整个板块一起贵”。
      </AntParagraph>
      {loading ? <Skeleton active paragraph={{ rows: 4 }} /> : null}
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!loading && !error && !rows.length ? <Empty description="暂无同行对比数据" /> : null}
      {rows.length ? (
        <>
          <Space wrap size={8} style={{ marginBottom: 12 }}>
            <Tag color="blue">{peerComparison?.sector || '未知板块'}</Tag>
            {peerComparison?.industry ? <Tag>{peerComparison.industry}</Tag> : null}
            <Tag>{`同行 ${peerComparison?.summary?.peer_count || 0} 家`}</Tag>
            {peerComparison?.summary?.same_industry_count ? <Tag>{`同细分行业 ${peerComparison.summary.same_industry_count} 家`}</Tag> : null}
            {peerComparison?.candidate_count ? <Tag>{`候选池 ${peerComparison.candidate_count} 家`}</Tag> : null}
            {peerComparison?.summary?.median_peer_pe ? <Tag>{`Peer P/E 中位数 ${peerComparison.summary.median_peer_pe}`}</Tag> : null}
            {peerComparison?.summary?.median_peer_ps ? <Tag>{`Peer P/S 中位数 ${peerComparison.summary.median_peer_ps}`}</Tag> : null}
          </Space>
          <div style={{ width: '100%', height: 220, marginBottom: 12 }}>
            <ResponsiveContainer>
              <BarChart data={premiumChartData} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="symbol" />
                <YAxis tickFormatter={(value) => `${value}%`} />
                <RechartsTooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, '相对公允价值溢折价']} />
                <ReferenceLine y={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                <Bar dataKey="premium_discount" radius={[6, 6, 0, 0]}>
                  {premiumChartData.map((entry) => (
                    <Cell key={entry.symbol} fill={entry.is_target ? '#1677ff' : entry.premium_discount > 0 ? '#ff7875' : '#73d13d'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <Table
            size="small"
            pagination={false}
            dataSource={rows}
            columns={[
              {
                title: '标的',
                dataIndex: 'symbol',
                key: 'symbol',
                render: (value, record) => (
                  <Space direction="vertical" size={0}>
                    <Space size={6}>
                      <AntText strong>{value}</AntText>
                      {record.is_target ? <Tag color="blue">当前标的</Tag> : null}
                    </Space>
                    {record.company_name ? <AntText type="secondary" style={{ fontSize: 12 }}>{record.company_name}</AntText> : null}
                  </Space>
                ),
              },
              { title: '现价 / 公允', key: 'valuation', render: (_, record) => `${formatCurrency(record.current_price)} / ${formatCurrency(record.fair_value)}` },
              {
                title: '溢折价',
                dataIndex: 'premium_discount',
                key: 'premium_discount',
                render: (value) => (value === null || value === undefined ? DISPLAY_EMPTY : <Tag color={value > 0 ? 'red' : 'green'}>{`${value > 0 ? '+' : ''}${Number(value).toFixed(1)}%`}</Tag>),
              },
              { title: 'P/E', dataIndex: 'pe_ratio', key: 'pe_ratio', render: (value) => (value ? Number(value).toFixed(1) : DISPLAY_EMPTY) },
              { title: 'P/S', dataIndex: 'price_to_sales', key: 'price_to_sales', render: (value) => (value ? Number(value).toFixed(1) : DISPLAY_EMPTY) },
              { title: 'EV/EBITDA', dataIndex: 'enterprise_to_ebitda', key: 'enterprise_to_ebitda', render: (value) => (value ? Number(value).toFixed(1) : DISPLAY_EMPTY) },
              {
                title: '操作',
                key: 'action',
                render: (_, record) => (
                  record.is_target ? (
                    <AntText type="secondary">当前</AntText>
                  ) : (
                    <Button
                      data-testid={`pricing-peer-inspect-${record.symbol}`}
                      type="link"
                      onClick={() => onInspect(record)}
                    >
                      深入分析
                    </Button>
                  )
                ),
              },
            ]}
          />
        </>
      ) : null}
    </Card>
  );
}

export const PricingScreenerCard = ({
  value,
  onChange,
  onRun,
  onInspect,
  loading,
  error,
  period,
  results,
  meta,
  progress,
  filter,
  onFilterChange,
  sectorFilter,
  onSectorFilterChange,
  minScore,
  onMinScoreChange,
  sectorOptions,
  onApplyPreset,
  onExport,
}) => {
  const candidateCount = parsePricingUniverseInput(value).length;

  return (
    <Card data-testid="pricing-screener-card" size="small" style={{ marginBottom: 16 }} title={<><ThunderboltOutlined style={{ marginRight: 8 }} />Mispricing 候选池筛选</>} extra={<Tag>{`窗口 ${period}`}</Tag>}>
      <AntParagraph type="secondary" style={{ marginBottom: 12 }}>
        一次跑一组候选标的，按偏差幅度、置信度和证据共振综合排序；点“深入分析”会回到单标的研究视图。
      </AntParagraph>
      <Input.TextArea data-testid="pricing-screener-input" rows={4} value={value} onChange={(event) => onChange(event.target.value)} placeholder="输入多个股票代码，支持换行、逗号或空格分隔" style={{ marginBottom: 12 }} />
      <Space wrap size={8} style={{ marginBottom: 12 }}>
        <AntText type="secondary">预设候选池:</AntText>
        {SCREENING_PRESETS.map((preset) => (
          <Tag key={preset.key} color="blue" style={{ cursor: 'pointer' }} onClick={() => onApplyPreset(preset.symbols)}>
            {preset.label}
          </Tag>
        ))}
      </Space>
      <Space wrap size="middle" style={{ marginBottom: 12 }}>
        <Button data-testid="pricing-screener-run-button" type="default" icon={<ThunderboltOutlined />} loading={loading} onClick={onRun}>批量筛选</Button>
        <Button onClick={onExport} disabled={!results?.length}>导出 CSV</Button>
        <AntText type="secondary">{`候选 ${candidateCount} 个`}</AntText>
        {meta ? <AntText type="secondary">{`已分析 ${meta.analyzedCount}/${meta.totalInput} · 失败 ${meta.failureCount}`}</AntText> : null}
      </Space>
      {progress?.total ? (
        <div style={{ marginBottom: 12 }}>
          <Progress percent={Math.round((Number(progress.completed || 0) / Number(progress.total || 1)) * 100)} status={progress.running ? 'active' : 'normal'} format={() => `${progress.completed}/${progress.total}`} />
        </div>
      ) : null}
      <Space wrap size={8} style={{ marginBottom: 12 }}>
        <AntText type="secondary">筛选视图:</AntText>
        <Select value={filter} onChange={onFilterChange} style={{ width: 180 }}>
          <Option value="all">全部结果</Option>
          <Option value="undervalued">只看低估</Option>
          <Option value="high-confidence">只看高置信度</Option>
          <Option value="aligned">只看证据同向</Option>
          <Option value="governance-risk">只看治理风险高</Option>
          <Option value="governance-support">只看执行支撑强</Option>
        </Select>
        <Select value={sectorFilter} onChange={onSectorFilterChange} style={{ width: 180 }}>
          <Option value="all">全部板块</Option>
          {(sectorOptions || []).map((sector) => <Option key={sector} value={sector}>{sector}</Option>)}
        </Select>
        <div style={{ minWidth: 220 }}>
          <AntText type="secondary" style={{ fontSize: 12 }}>{`机会分阈值 >= ${Number(minScore || 0).toFixed(0)}`}</AntText>
          <Slider min={0} max={40} step={1} value={minScore} onChange={onMinScoreChange} />
        </div>
      </Space>
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {results?.length ? (
        <Table
          data-testid="pricing-screener-results"
          size="small"
          rowKey="symbol"
          pagination={false}
          dataSource={results}
          columns={[
            { title: '#', dataIndex: 'rank', key: 'rank', width: 56 },
            {
              title: '标的',
              dataIndex: 'symbol',
              key: 'symbol',
              render: (value, record) => (
                <div>
                  <AntText strong>{value}</AntText>
                  {record.company_name ? <div style={{ fontSize: 12, color: '#8c8c8c' }}>{record.company_name}</div> : null}
                  {record.sector ? <div style={{ fontSize: 12, color: '#bfbfbf' }}>{record.sector}</div> : null}
                </div>
              ),
            },
            { title: '机会分', dataIndex: 'screening_score', key: 'screening_score', width: 100, render: (value) => <AntText strong>{Number(value || 0).toFixed(1)}</AntText> },
            { title: '偏差', dataIndex: 'gap_pct', key: 'gap_pct', width: 96, render: (value) => (value === null || value === undefined ? DISPLAY_EMPTY : `${value > 0 ? '+' : ''}${Number(value).toFixed(1)}%`) },
            {
              title: '治理折扣',
              dataIndex: 'people_governance_discount_pct',
              key: 'people_governance_discount_pct',
              width: 128,
              render: (value, record) => {
                if (value === null || value === undefined) return DISPLAY_EMPTY;
                const numeric = Number(value || 0);
                const color = numeric >= 6 ? 'red' : numeric > 0 ? 'gold' : numeric <= -3 ? 'green' : 'blue';
                return (
                  <Tooltip title={record.people_governance_summary || record.people_governance_label || ''}>
                    <Tag color={color}>
                      {numeric >= 0 ? `-${numeric.toFixed(1)}%` : `+${Math.abs(numeric).toFixed(1)}%`}
                    </Tag>
                  </Tooltip>
                );
              },
            },
            { title: '观点', dataIndex: 'primary_view', key: 'primary_view', width: 88, render: (value) => <Tag color={value === '低估' ? 'green' : value === '高估' ? 'red' : 'default'}>{value || '合理'}</Tag> },
            { title: '置信度', dataIndex: 'confidence_score', key: 'confidence_score', width: 110, render: (value, record) => <div><Tag>{record.confidence || 'medium'}</Tag><div style={{ fontSize: 12, color: '#8c8c8c' }}>{Number(value || 0).toFixed(2)}</div></div> },
            { title: '证据共振', dataIndex: 'factor_alignment_label', key: 'factor_alignment_label', width: 110, render: (value, record) => <Tag color={ALIGNMENT_TAG_COLORS[record.factor_alignment_status] || 'default'}>{value || '待确认'}</Tag> },
            { title: '主驱动', dataIndex: 'primary_driver', key: 'primary_driver', render: (value) => value || DISPLAY_EMPTY },
            {
              title: '操作',
              key: 'action',
              width: 100,
              render: (_, record) => (
                <Button
                  data-testid={`pricing-screener-inspect-${record.symbol}`}
                  type="link"
                  onClick={() => onInspect(record)}
                >
                  深入分析
                </Button>
              ),
            },
          ]}
        />
      ) : null}
    </Card>
  );
};

export const GapOverview = ({ data }) => {
  const gap = data?.gap_analysis || {};
  const valuation = data?.valuation || {};
  const gapPct = gap.gap_pct;
  const severity = gap.severity || 'unknown';
  const priceSourceLabel = getPriceSourceLabel(valuation.current_price_source || '');
  const formatCurrencyStat = (value) => (value === null || value === undefined || value === '' ? DISPLAY_EMPTY : `$${Number(value).toFixed(2)}`);
  const formatPercentPointStat = (value) => (value === null || value === undefined || value === '' ? DISPLAY_EMPTY : `${Math.abs(Number(value)).toFixed(1)}%`);
  const severityColor = { extreme: '#ff4d4f', high: '#fa8c16', moderate: '#faad14', mild: '#52c41a', negligible: '#1890ff', unknown: '#d9d9d9' };
  const directionIcon = gapPct > 0 ? <ArrowUpOutlined style={{ color: '#ff4d4f' }} /> : gapPct < 0 ? <ArrowDownOutlined style={{ color: '#52c41a' }} /> : gapPct === null || gapPct === undefined ? null : <MinusOutlined />;
  const rangeChartData = gap.fair_value_low && gap.fair_value_high ? [{ label: '下沿', value: Number(gap.fair_value_low) }, { label: '公允', value: Number(gap.fair_value_mid || 0) }, { label: '上沿', value: Number(gap.fair_value_high) }] : [];
  const thermometerPercent = gapPct === null || gapPct === undefined ? 0 : Math.min(100, Math.round((Math.abs(Number(gapPct)) / 30) * 100));
  const thermometerStatus = gapPct > 0 ? 'exception' : gapPct < 0 ? 'success' : 'normal';
  const thermometerLabel = gapPct > 0 ? '偏热' : gapPct < 0 ? '偏冷' : '中性';

  return (
    <Card data-testid="pricing-gap-overview" title={<Space><SwapOutlined /><span>定价差异概览</span><Tag color="blue">{data.symbol}</Tag>{valuation.company_name && <AntText type="secondary">{valuation.company_name}</AntText>}</Space>}>
      <Row gutter={[24, 16]}>
        <Col xs={12} sm={6}>
          <Statistic title="当前市价" value={gap.current_price} formatter={formatCurrencyStat} />
          {gap.current_price !== null && gap.current_price !== undefined ? <AntText type="secondary" style={{ fontSize: 12 }}>现价来源：{priceSourceLabel}</AntText> : null}
        </Col>
        <Col xs={12} sm={6}><Statistic title="公允价值" value={gap.fair_value_mid} formatter={formatCurrencyStat} valueStyle={{ color: '#1890ff' }} /></Col>
        <Col xs={12} sm={6}><Statistic title="偏差幅度" value={gapPct} formatter={formatPercentPointStat} prefix={directionIcon} valueStyle={gapPct === null || gapPct === undefined ? undefined : { color: gapPct > 0 ? '#ff4d4f' : '#52c41a' }} /></Col>
        <Col xs={12} sm={6}>
          <div>
            <div style={{ color: '#8c8c8c', fontSize: 12, marginBottom: 4 }}>估值状态</div>
            <Tag color={severityColor[severity]} style={{ fontSize: 14, padding: '4px 12px' }}>{gap.severity_label || '未知'}</Tag>
            <div style={{ marginTop: 4 }}><Tag>{gap.direction || ''}</Tag></div>
          </div>
        </Col>
      </Row>
      {gap.fair_value_low && gap.fair_value_high ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ marginBottom: 8 }}>
            <AntText type="secondary">定价温度计</AntText>
            <div style={{ marginTop: 6 }}>
              <Space size={8} align="center">
                <Progress percent={thermometerPercent} status={thermometerStatus} size={[220, 10]} showInfo={false} strokeColor={gapPct > 0 ? '#ff4d4f' : gapPct < 0 ? '#52c41a' : '#1677ff'} />
                <Tag color={gapPct > 0 ? 'red' : gapPct < 0 ? 'green' : 'blue'}>{thermometerLabel}</Tag>
              </Space>
            </div>
          </div>
          <AntText type="secondary">
            公允价值区间: ${gap.fair_value_low} ~ ${gap.fair_value_high}
            {gap.in_fair_range ? <Tag color="green" style={{ marginLeft: 8 }}>在合理区间内</Tag> : <Tag color="orange" style={{ marginLeft: 8 }}>偏离合理区间</Tag>}
          </AntText>
          <div style={{ width: '100%', height: 120, marginTop: 8 }}>
            <ResponsiveContainer>
              <BarChart data={rangeChartData} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" />
                <YAxis hide domain={['dataMin - 5', 'dataMax + 5']} />
                <RechartsTooltip formatter={(value) => [`$${Number(value).toFixed(2)}`, '估值']} />
                <ReferenceLine y={Number(gap.current_price || 0)} stroke="#ff4d4f" strokeDasharray="4 4" label="当前价" />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {rangeChartData.map((entry) => <Cell key={entry.label} fill={entry.label === '公允' ? '#1677ff' : '#91caff'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}
    </Card>
  );
};
