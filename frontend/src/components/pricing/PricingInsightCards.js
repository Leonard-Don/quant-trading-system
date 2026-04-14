import React from 'react';
import {
  Alert,
  Button,
  Card,
  Divider,
  Empty,
  Progress,
  Space,
  Tag,
  Typography,
} from 'antd';
import { InfoCircleOutlined, SwapOutlined } from '@ant-design/icons';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { ALIGNMENT_TAG_COLORS } from '../../utils/pricingSectionConstants';
import {
  buildPricingActionPosture,
  getDriverImpactMeta,
  getPriceSourceLabel,
  getSourceModeLabel,
  getSignalStrengthMeta,
} from '../../utils/pricingResearch';

const { Paragraph, Text } = Typography;

const PEOPLE_RISK_COLORS = {
  low: 'green',
  medium: 'orange',
  high: 'red',
};

const PEOPLE_STANCE_LABELS = {
  supportive: '支撑',
  balanced: '均衡',
  fragile: '脆弱',
};

export const DriversCard = ({ data }) => {
  if (!data) return null;
  const drivers = data.drivers || [];
  const primaryDriver = data.primary_driver || drivers[0] || null;
  const driverChartData = drivers.map((driver) => ({
    name: driver.factor,
    contribution: Number(driver.signal_strength || 0)
      * (['negative', 'undervalued', 'defensive'].includes(driver.impact) ? -1 : 1),
  }));
  const waterfallChartData = drivers.reduce((rows, driver) => {
    const contribution = Number(driver.signal_strength || 0)
      * (['negative', 'undervalued', 'defensive'].includes(driver.impact) ? -1 : 1);
    const previousEnd = rows.length ? rows[rows.length - 1].end : 0;
    const nextEnd = previousEnd + contribution;
    rows.push({
      name: driver.factor,
      base: previousEnd,
      contribution,
      end: nextEnd,
    });
    return rows;
  }, []);

  return (
    <Card data-testid="pricing-drivers-card" title={<><SwapOutlined style={{ marginRight: 8 }} />偏差驱动因素</>}>
      {drivers.length > 0 ? (
        <div>
          {primaryDriver ? (
            <div style={{
              padding: '10px 12px',
              marginBottom: 12,
              background: 'var(--bg-secondary, #fafafa)',
              borderRadius: 8,
              border: '1px solid var(--border-color, #f0f0f0)',
            }}>
              {(() => {
                const primaryStrength = getSignalStrengthMeta(primaryDriver.signal_strength);
                const primaryImpact = getDriverImpactMeta(primaryDriver.impact);
                return (
                  <>
                    <Space wrap size={6}>
                      <Tag color="gold">主驱动</Tag>
                      <Text strong>{primaryDriver.factor}</Text>
                      <Tag color={primaryImpact.color}>{primaryImpact.label}</Tag>
                      {primaryStrength ? (
                        <Tag color={primaryStrength.color}>{`强度 ${primaryStrength.label} (${primaryStrength.score.toFixed(2)})`}</Tag>
                      ) : null}
                    </Space>
                    {primaryDriver.ranking_reason ? (
                      <Paragraph style={{ marginBottom: 0, marginTop: 6, fontSize: 12, color: '#8c8c8c' }}>
                        判断依据：{primaryDriver.ranking_reason}
                      </Paragraph>
                    ) : null}
                  </>
                );
              })()}
            </div>
          ) : null}
          {driverChartData.length ? (
            <div style={{ width: '100%', height: 220, marginBottom: 12 }}>
              <ResponsiveContainer>
                <BarChart data={driverChartData} layout="vertical" margin={{ top: 12, right: 12, left: 24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" width={110} />
                  <ReferenceLine x={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                  <RechartsTooltip formatter={(value) => [Number(value).toFixed(2), '驱动贡献']} />
                  <Bar dataKey="contribution" radius={[0, 6, 6, 0]}>
                    {driverChartData.map((item) => (
                      <Cell key={item.name} fill={item.contribution >= 0 ? '#ff7875' : '#73d13d'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
          {waterfallChartData.length ? (
            <>
              <Text type="secondary" style={{ fontSize: 12 }}>驱动瀑布视图</Text>
              <div style={{ width: '100%', height: 240, marginTop: 8, marginBottom: 12 }}>
                <ResponsiveContainer>
                  <ComposedChart data={waterfallChartData} margin={{ top: 12, right: 12, left: 0, bottom: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" angle={-12} textAnchor="end" height={56} interval={0} />
                    <YAxis />
                    <ReferenceLine y={0} stroke="#8c8c8c" strokeDasharray="4 4" />
                    <RechartsTooltip formatter={(value, name) => [Number(value).toFixed(2), name === 'contribution' ? '边际贡献' : '累计偏差']} />
                    <Bar dataKey="base" stackId="waterfall" fill="transparent" />
                    <Bar dataKey="contribution" stackId="waterfall">
                      {waterfallChartData.map((item) => (
                        <Cell key={item.name} fill={item.contribution >= 0 ? '#ff7875' : '#73d13d'} />
                      ))}
                    </Bar>
                    <Line type="monotone" dataKey="end" stroke="#1677ff" strokeWidth={2} dot={{ r: 4 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : null}
          {drivers.map((driver, index) => {
            const impactMeta = getDriverImpactMeta(driver.impact);
            const strengthMeta = getSignalStrengthMeta(driver.signal_strength);
            return (
              <div key={index} style={{
                padding: '10px 12px', marginBottom: 8,
                border: '1px solid var(--border-color, #f0f0f0)',
                borderRadius: 6, borderLeft: `3px solid ${impactMeta.color}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space wrap size={6}>
                    <Text strong style={{ fontSize: 13 }}>{driver.factor}</Text>
                    {driver.rank === 1 ? <Tag color="gold">#1</Tag> : null}
                    {strengthMeta ? (
                      <Tag color={strengthMeta.color}>{`强度 ${strengthMeta.label} (${strengthMeta.score.toFixed(2)})`}</Tag>
                    ) : null}
                  </Space>
                  <Tag color={impactMeta.color}>{impactMeta.label}</Tag>
                </div>
                <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  {driver.description}
                </Paragraph>
                {driver.ranking_reason ? (
                  <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 11, color: '#bfbfbf' }}>
                    判断依据：{driver.ranking_reason}
                  </Paragraph>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <Empty description="未检测到显著偏差因素" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
    </Card>
  );
};

export const ImplicationsCard = ({ data, valuation = {}, factorModel = {}, gapAnalysis = {}, onRetry }) => {
  if (!data) return null;

  const riskColors = { low: '#52c41a', medium: '#faad14', high: '#ff4d4f' };
  const riskLabels = { low: '低', medium: '中', high: '高' };
  const confLabels = { low: '低', medium: '中', high: '高' };
  const confidenceReasons = data.confidence_reasons || [];
  const confidenceBreakdown = data.confidence_breakdown || [];
  const confidenceScore = data.confidence_score;
  const alignmentMeta = data.factor_alignment || null;
  const tradeSetup = data.trade_setup || null;
  const evidenceItems = [
    valuation.current_price_source ? `现价来源 ${getPriceSourceLabel(valuation.current_price_source)}` : null,
    factorModel.data_points ? `因子样本 ${factorModel.data_points}` : null,
    factorModel.period ? `分析窗口 ${factorModel.period}` : null,
  ].filter(Boolean);
  const actionPosture = buildPricingActionPosture({
    gapPct: gapAnalysis?.gap_pct,
    confidenceScore,
    alignmentStatus: alignmentMeta?.status,
    primaryView: data.primary_view,
    riskLevel: data.risk_level,
  });

  return (
    <Card data-testid="pricing-implications-card" title={<><InfoCircleOutlined style={{ marginRight: 8 }} />投资含义</>}>
      <div style={{ marginBottom: 12 }}>
        <Space size="large">
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>综合判断</Text>
            <div>
              <Tag
                color={data.primary_view === '低估' ? 'green' : data.primary_view === '高估' ? 'red' : 'blue'}
                style={{ fontSize: 16, padding: '4px 16px', marginTop: 4 }}
              >
                {data.primary_view || '合理'}
              </Tag>
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>风险等级</Text>
            <div>
              <Tag color={riskColors[data.risk_level]} style={{ marginTop: 4 }}>
                {riskLabels[data.risk_level] || '中'}
              </Tag>
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>分析置信度</Text>
            <div>
              <Tag style={{ marginTop: 4 }}>{confLabels[data.confidence] || '中'}</Tag>
            </div>
            {confidenceScore !== undefined && confidenceScore !== null ? (
              <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
                评分 {Number(confidenceScore).toFixed(2)}
              </Text>
            ) : null}
          </div>
          {alignmentMeta ? (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>证据共振</Text>
              <div>
                <Tag color={ALIGNMENT_TAG_COLORS[alignmentMeta.status] || 'default'} style={{ marginTop: 4 }}>
                  {alignmentMeta.label || '待确认'}
                </Tag>
              </div>
            </div>
          ) : null}
        </Space>
      </div>

      <Divider style={{ margin: '12px 0' }} />

      {evidenceItems.length ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>证据质量</Text>
          <div style={{ marginTop: 6 }}>
            <Space wrap size={6}>
              {evidenceItems.map((item) => (
                <Tag key={item}>{item}</Tag>
              ))}
            </Space>
          </div>
        </div>
      ) : null}

      {alignmentMeta?.summary ? (
        <Paragraph style={{ marginBottom: 12, fontSize: 12, color: '#8c8c8c' }}>
          <InfoCircleOutlined style={{ marginRight: 6, color: '#52c41a' }} />
          {alignmentMeta.summary}
        </Paragraph>
      ) : null}

      {actionPosture ? (
        <Alert
          type={actionPosture.type}
          showIcon
          style={{ marginBottom: 12 }}
          message={actionPosture.title}
          description={`${actionPosture.actionHint} ${actionPosture.reason}`.trim()}
        />
      ) : null}

      {confidenceReasons.length ? (
        <div style={{ marginBottom: 12 }}>
          {confidenceReasons.map((reason, index) => (
            <Paragraph key={`${reason}-${index}`} style={{ marginBottom: 6, fontSize: 12, color: '#8c8c8c' }}>
              <InfoCircleOutlined style={{ marginRight: 6, color: '#faad14' }} />
              {reason}
            </Paragraph>
          ))}
        </div>
      ) : null}

      {confidenceScore !== undefined && confidenceScore !== null ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>置信度透明度</Text>
          <Progress percent={Math.round(Number(confidenceScore) * 100)} strokeColor="#1677ff" />
        </div>
      ) : null}

      {confidenceBreakdown.length ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>置信度拆解</Text>
          <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
            {confidenceBreakdown.map((item) => (
              <div
                key={item.key}
                style={{
                  padding: '8px 10px',
                  border: '1px solid var(--border-color, #f0f0f0)',
                  borderRadius: 8,
                  background: 'var(--bg-secondary, #fafafa)',
                }}
              >
                <Space wrap size={6}>
                  <Text strong style={{ fontSize: 12 }}>{item.label}</Text>
                  <Tag color={item.status === 'positive' ? 'green' : item.status === 'negative' ? 'red' : 'gold'}>
                    {item.delta > 0 ? `+${item.delta.toFixed(2)}` : item.delta.toFixed(2)}
                  </Tag>
                </Space>
                <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  {item.detail}
                </Paragraph>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {tradeSetup ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>交易情景</Text>
          <div
            style={{
              marginTop: 8,
              padding: '12px',
              borderRadius: 10,
              background: 'var(--bg-secondary, #fafafa)',
              border: '1px solid var(--border-color, #f0f0f0)',
            }}
          >
            <Space wrap size={6} style={{ marginBottom: 8 }}>
              <Tag color="blue">{tradeSetup.stance || '观察'}</Tag>
              {tradeSetup.target_price ? <Tag>{`目标价 $${Number(tradeSetup.target_price).toFixed(2)}`}</Tag> : null}
              {tradeSetup.stop_loss ? <Tag color="volcano">{`风险边界 $${Number(tradeSetup.stop_loss).toFixed(2)}`}</Tag> : null}
              {tradeSetup.risk_reward ? <Tag color="purple">{`盈亏比 ${Number(tradeSetup.risk_reward).toFixed(2)}`}</Tag> : null}
            </Space>
            {tradeSetup.summary ? (
              <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#595959' }}>
                {tradeSetup.summary}
              </Paragraph>
            ) : null}
            <Space wrap size={8}>
              {tradeSetup.upside_pct !== undefined ? <Tag color="green">{`基准空间 ${tradeSetup.upside_pct > 0 ? '+' : ''}${tradeSetup.upside_pct}%`}</Tag> : null}
              {tradeSetup.stretch_upside_pct !== undefined ? <Tag>{`扩展空间 ${tradeSetup.stretch_upside_pct > 0 ? '+' : ''}${tradeSetup.stretch_upside_pct}%`}</Tag> : null}
              {tradeSetup.risk_pct !== undefined ? <Tag color="red">{`风险预算 ${tradeSetup.risk_pct}%`}</Tag> : null}
            </Space>
            {tradeSetup.quality_note ? (
              <Paragraph style={{ marginBottom: 0, marginTop: 8, fontSize: 12, color: '#8c8c8c' }}>
                {tradeSetup.quality_note}
              </Paragraph>
            ) : null}
          </div>
        </div>
      ) : null}

      {(data.insights || []).map((insight, index) => (
        <Paragraph key={index} style={{ marginBottom: 6, fontSize: 13 }}>
          <InfoCircleOutlined style={{ marginRight: 6, color: '#1890ff' }} />
          {insight}
        </Paragraph>
      ))}

      {onRetry ? (
        <Button type="link" onClick={() => onRetry()} style={{ paddingLeft: 0 }}>
          重新分析
        </Button>
      ) : null}
    </Card>
  );
};

export const PeopleLayerCard = ({ data, overlay = null }) => {
  if ((!data || !Object.keys(data).length) && (!overlay || !Object.keys(overlay).length)) return null;

  const executive = data?.executive_profile || overlay?.executive_evidence || {};
  const insider = data?.insider_flow || overlay?.insider_evidence || {};
  const hiring = data?.hiring_signal || overlay?.hiring_evidence || {};
  const stanceLabel = PEOPLE_STANCE_LABELS[data?.stance] || '均衡';
  const riskColor = PEOPLE_RISK_COLORS[data?.risk_level] || 'default';
  const governanceDiscountPct = Number(overlay?.governance_discount_pct || 0);
  const governanceTone = governanceDiscountPct >= 0
    ? governanceDiscountPct >= 10
      ? 'volcano'
      : governanceDiscountPct >= 4
        ? 'orange'
        : 'gold'
    : 'green';
  const policyExecutionContext = overlay?.policy_execution_context || {};
  const sourceModeSummary = overlay?.source_mode_summary || {};

  return (
    <Card data-testid="pricing-people-layer-card" title="人的维度 / 治理折扣">
      <Space wrap size={8} style={{ marginBottom: 10 }}>
        <Tag color="blue">{`组织姿态 ${stanceLabel}`}</Tag>
        <Tag color={riskColor}>{`组织风险 ${data?.risk_level || 'medium'}`}</Tag>
        {data?.confidence !== undefined && data?.confidence !== null ? (
          <Tag>{`置信度 ${Number(data.confidence).toFixed(2)}`}</Tag>
        ) : null}
        {overlay?.label ? <Tag color={governanceTone}>{overlay.label}</Tag> : null}
        {overlay?.governance_discount_pct !== undefined && overlay?.governance_discount_pct !== null ? (
          <Tag color={governanceTone}>
            {governanceDiscountPct >= 0
              ? `治理折价 ${governanceDiscountPct.toFixed(1)}%`
              : `执行支撑 ${Math.abs(governanceDiscountPct).toFixed(1)}%`}
          </Tag>
        ) : null}
        {overlay?.confidence !== undefined && overlay?.confidence !== null ? (
          <Tag>{`治理置信度 ${Number(overlay.confidence).toFixed(2)}`}</Tag>
        ) : null}
        {overlay?.source_mode_summary ? (
          <Tag color={sourceModeSummary.label === 'fallback-heavy' ? 'red' : sourceModeSummary.label === 'official-led' ? 'green' : 'blue'}>
            {`来源 ${getSourceModeLabel(sourceModeSummary)}`}
          </Tag>
        ) : null}
      </Space>

      {overlay?.summary ? (
        <Alert
          style={{ marginBottom: 12 }}
          type={governanceDiscountPct >= 4 ? 'warning' : governanceDiscountPct <= -3 ? 'success' : 'info'}
          showIcon
          message={overlay.label || '治理折扣'}
          description={overlay.summary}
        />
      ) : data?.summary ? (
        <Paragraph style={{ marginBottom: 12, color: '#595959' }}>{data.summary}</Paragraph>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <div style={{ padding: 12, border: '1px solid var(--border-color, #f0f0f0)', borderRadius: 8 }}>
          <Text strong>管理层画像</Text>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">技术决策权</Text>
            <Progress percent={Math.round(Number(executive.technical_authority_score || 0) * 100)} size="small" />
          </div>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">资本市场压力</Text>
            <Progress
              percent={Math.round(Number(executive.capital_markets_pressure || 0) * 100)}
              size="small"
              status={Number(executive.capital_markets_pressure || 0) > 0.55 ? 'exception' : 'normal'}
            />
          </div>
          <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#8c8c8c' }}>
            {executive.leadership_balance || '管理层结构待确认'}
            {executive.average_tenure_years ? ` · 平均 tenure ${executive.average_tenure_years} 年` : ''}
            {executive.summary ? ` · ${executive.summary}` : ''}
          </Paragraph>
        </div>

        <div style={{ padding: 12, border: '1px solid var(--border-color, #f0f0f0)', borderRadius: 8 }}>
          <Text strong>内部人交易</Text>
          <Space wrap size={6} style={{ marginTop: 8 }}>
            <Tag>{insider.label || '信号中性'}</Tag>
            {insider.net_action ? <Tag>{`动作 ${insider.net_action}`}</Tag> : null}
            {insider.transaction_count ? <Tag>{`笔数 ${insider.transaction_count}`}</Tag> : null}
          </Space>
          <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#8c8c8c' }}>
            {insider.summary || '暂无可用内部人交易数据'}
          </Paragraph>
        </div>

        <div style={{ padding: 12, border: '1px solid var(--border-color, #f0f0f0)', borderRadius: 8 }}>
          <Text strong>招聘稀释度</Text>
          <Space wrap size={6} style={{ marginTop: 8 }}>
            <Tag>{`信号 ${hiring.signal || 'neutral'}`}</Tag>
            {hiring.dilution_ratio !== undefined && hiring.dilution_ratio !== null ? (
              <Tag color={Number(hiring.dilution_ratio) > 1.5 ? 'red' : 'default'}>
                {`稀释度 ${Number(hiring.dilution_ratio).toFixed(2)}`}
              </Tag>
            ) : null}
            {hiring.tech_ratio !== undefined && hiring.tech_ratio !== null ? (
              <Tag>{`技术占比 ${(Number(hiring.tech_ratio) * 100).toFixed(0)}%`}</Tag>
            ) : null}
          </Space>
          <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#8c8c8c' }}>
            {hiring.alert_message || '当前招聘结构未触发强烈组织风险预警'}
          </Paragraph>
        </div>
      </div>

      {overlay?.source_mode_summary || policyExecutionContext?.label ? (
        <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
          {overlay?.source_mode_summary ? (
            <div
              style={{
                padding: '10px 12px',
                border: '1px solid var(--border-color, #f0f0f0)',
                borderRadius: 8,
                background: 'var(--bg-secondary, #fafafa)',
              }}
            >
              <Space wrap size={6}>
                <Text strong>证据来源治理</Text>
                <Tag color={sourceModeSummary.label === 'fallback-heavy' ? 'red' : sourceModeSummary.label === 'official-led' ? 'green' : 'blue'}>
                  {getSourceModeLabel(sourceModeSummary)}
                </Tag>
                {sourceModeSummary.coverage ? <Tag>{`覆盖 ${Number(sourceModeSummary.coverage)}`}</Tag> : null}
              </Space>
              <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#8c8c8c' }}>
                官方/披露占比 {`${Math.round(Number(sourceModeSummary.official_share || 0) * 100)}%`}
                {' · '}
                回退占比 {`${Math.round(Number(sourceModeSummary.fallback_share || 0) * 100)}%`}
              </Paragraph>
            </div>
          ) : null}
          {policyExecutionContext?.label ? (
            <div
              style={{
                padding: '10px 12px',
                border: '1px solid var(--border-color, #f0f0f0)',
                borderRadius: 8,
                background: 'var(--bg-secondary, #fafafa)',
              }}
            >
              <Space wrap size={6}>
                <Text strong>政策执行上下文</Text>
                <Tag color={policyExecutionContext.label === 'chaotic' ? 'red' : policyExecutionContext.label === 'watch' ? 'gold' : 'green'}>
                  {policyExecutionContext.label}
                </Tag>
                {policyExecutionContext.top_department ? <Tag>{policyExecutionContext.top_department}</Tag> : null}
                {policyExecutionContext.reversal_count !== undefined && policyExecutionContext.reversal_count !== null ? (
                  <Tag>{`反转 ${policyExecutionContext.reversal_count}`}</Tag>
                ) : null}
              </Space>
              <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#8c8c8c' }}>
                {policyExecutionContext.summary || policyExecutionContext.reason || '当前暂无显著政策执行噪音。'}
                {policyExecutionContext.execution_status ? ` · 执行状态 ${policyExecutionContext.execution_status}` : ''}
                {policyExecutionContext.lag_days !== undefined && policyExecutionContext.lag_days !== null ? ` · 滞后 ${policyExecutionContext.lag_days} 天` : ''}
              </Paragraph>
            </div>
          ) : null}
        </div>
      ) : null}

      {data?.flags?.length ? (
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>治理提示</Text>
          <div style={{ marginTop: 6 }}>
            <Space wrap size={6}>
              {data.flags.map((flag) => (
                <Tag key={flag}>{flag}</Tag>
              ))}
            </Space>
          </div>
        </div>
      ) : null}

      {data?.notes?.length ? (
        <Alert
          style={{ marginTop: 12 }}
          type={data.risk_level === 'high' ? 'warning' : 'info'}
          showIcon
          message="人的维度补充判断"
          description={(data.notes || []).slice(0, 2).join(' ')}
        />
      ) : null}
    </Card>
  );
};

export const StructuralDecayCard = ({ data }) => {
  if (!data || !Object.keys(data).length) return null;

  const actionColor = {
    structural_short: 'red',
    structural_avoid: 'volcano',
    watch: 'gold',
    stable: 'green',
  }[data.action] || 'default';

  return (
    <Card data-testid="pricing-structural-decay-card" title="Structural Decay">
      <Space wrap size={8} style={{ marginBottom: 10 }}>
        <Tag color={actionColor}>{data.label || '待确认'}</Tag>
        {data.action ? <Tag>{`行动 ${data.action}`}</Tag> : null}
        {data.reversibility ? <Tag>{`可逆性 ${data.reversibility}`}</Tag> : null}
        {data.horizon ? <Tag>{`时间维度 ${data.horizon}`}</Tag> : null}
      </Space>

      {data.summary ? (
        <Paragraph style={{ marginBottom: 12, color: '#595959' }}>{data.summary}</Paragraph>
      ) : null}

      {data.score !== undefined && data.score !== null ? (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>衰败确定性</Text>
          <Progress
            percent={Math.round(Number(data.score) * 100)}
            strokeColor={actionColor === 'green' ? '#52c41a' : actionColor === 'gold' ? '#faad14' : '#ff4d4f'}
          />
        </div>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <div style={{ padding: 12, border: '1px solid var(--border-color, #f0f0f0)', borderRadius: 8 }}>
          <Text strong>主导失效模式</Text>
          <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#595959' }}>
            {data.dominant_failure_label || '待确认'}
          </Paragraph>
        </div>
        <div style={{ padding: 12, border: '1px solid var(--border-color, #f0f0f0)', borderRadius: 8 }}>
          <Text strong>关键证据</Text>
          {(data.evidence || []).length ? (
            <div style={{ marginTop: 8 }}>
              <Space wrap size={6}>
                {(data.evidence || []).map((item) => (
                  <Tag key={item}>{item}</Tag>
                ))}
              </Space>
            </div>
          ) : (
            <Paragraph style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: '#8c8c8c' }}>
              当前暂无足够证据支撑结构性衰败判断
            </Paragraph>
          )}
        </div>
      </div>

      {(data.components || []).length ? (
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>衰败拆解</Text>
          <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
            {(data.components || []).map((item) => (
              <div
                key={item.key}
                style={{
                  padding: '8px 10px',
                  border: '1px solid var(--border-color, #f0f0f0)',
                  borderRadius: 8,
                  background: 'var(--bg-secondary, #fafafa)',
                }}
              >
                <Space wrap size={6}>
                  <Text strong style={{ fontSize: 12 }}>{item.label}</Text>
                  <Tag color={item.status === 'negative' ? 'green' : 'red'}>
                    {item.delta > 0 ? `+${Number(item.delta).toFixed(2)}` : Number(item.delta).toFixed(2)}
                  </Tag>
                </Space>
                <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 12, color: '#8c8c8c' }}>
                  {item.detail}
                </Paragraph>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
};

export const MacroMispricingThesisCard = ({ data, onOpenDraft }) => {
  if (!data || !Object.keys(data).length) return null;
  const tradeLegs = data.trade_legs || [];

  return (
    <Card data-testid="pricing-macro-mispricing-thesis-card" title="Macro Mispricing Thesis">
      <Space wrap size={8} style={{ marginBottom: 10 }}>
        {data.stance ? <Tag color="volcano">{data.stance}</Tag> : null}
        {data.thesis_type ? <Tag>{data.thesis_type}</Tag> : null}
        {data.horizon ? <Tag>{`观察期 ${data.horizon}`}</Tag> : null}
        {data.people_risk ? <Tag>{`人的维度 ${data.people_risk}`}</Tag> : null}
      </Space>

      {data.summary ? (
        <Paragraph style={{ marginBottom: 12, color: '#595959' }}>{data.summary}</Paragraph>
      ) : null}

      {onOpenDraft ? (
        <Button size="small" type="primary" style={{ marginBottom: 12 }} onClick={onOpenDraft}>
          打开跨市场草案
        </Button>
      ) : null}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <div style={{ padding: 12, border: '1px solid var(--border-color, #f0f0f0)', borderRadius: 8 }}>
          <Text strong>主腿</Text>
          <Paragraph style={{ marginTop: 8, marginBottom: 4, fontSize: 12 }}>
            {data.primary_leg?.symbol || '—'} · {data.primary_leg?.side || 'watch'}
          </Paragraph>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {data.primary_leg?.rationale || '暂无主腿说明'}
          </Text>
        </div>
        <div style={{ padding: 12, border: '1px solid var(--border-color, #f0f0f0)', borderRadius: 8 }}>
          <Text strong>对冲腿</Text>
          <Paragraph style={{ marginTop: 8, marginBottom: 4, fontSize: 12 }}>
            {data.hedge_leg?.symbol || '—'} {data.hedge_leg?.side ? `· ${data.hedge_leg.side}` : ''}
          </Paragraph>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {data.hedge_leg?.rationale || '当前更适合作为观察或单腿表达'}
          </Text>
        </div>
      </div>

      {tradeLegs.length ? (
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>组合腿</Text>
          <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
            {tradeLegs.map((leg, index) => (
              <div
                key={`${leg.symbol}-${leg.side}-${index}`}
                style={{
                  padding: 10,
                  borderRadius: 8,
                  border: '1px solid var(--border-color, #f0f0f0)',
                  background: 'var(--bg-secondary, #fafafa)',
                }}
              >
                <Space wrap size={6}>
                  <Text strong>{leg.symbol || '—'}</Text>
                  <Tag color={leg.side === 'short' ? 'red' : leg.side === 'long' ? 'green' : 'default'}>
                    {leg.side || 'watch'}
                  </Tag>
                  {leg.role ? <Tag>{leg.role}</Tag> : null}
                  {leg.weight !== undefined && leg.weight !== null ? (
                    <Tag>{`权重 ${(Number(leg.weight) * 100).toFixed(0)}%`}</Tag>
                  ) : null}
                </Space>
                {leg.thesis ? (
                  <Paragraph style={{ marginBottom: 0, marginTop: 6, fontSize: 12, color: '#8c8c8c' }}>
                    {leg.thesis}
                  </Paragraph>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {(data.target_price || data.risk_boundary || data.risk_reward) ? (
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>交易边界</Text>
          <div style={{ marginTop: 8 }}>
            <Space wrap size={6}>
              {data.target_price ? <Tag>{`目标价 $${Number(data.target_price).toFixed(2)}`}</Tag> : null}
              {data.risk_boundary ? <Tag>{`风险边界 $${Number(data.risk_boundary).toFixed(2)}`}</Tag> : null}
              {data.risk_reward ? <Tag>{`盈亏比 ${Number(data.risk_reward).toFixed(2)}`}</Tag> : null}
            </Space>
          </div>
        </div>
      ) : null}

      {(data.kill_conditions || []).length ? (
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>Kill Conditions</Text>
          <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
            {(data.kill_conditions || []).slice(0, 3).map((item) => (
              <Text key={item} type="secondary">{item}</Text>
            ))}
          </div>
        </div>
      ) : null}

      {(data.execution_notes || []).length ? (
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>执行备注</Text>
          <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
            {(data.execution_notes || []).slice(0, 3).map((item) => (
              <Text key={item} type="secondary">{item}</Text>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
};
