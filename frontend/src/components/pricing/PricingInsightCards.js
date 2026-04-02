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
  getSignalStrengthMeta,
} from '../../utils/pricingResearch';

const { Paragraph, Text } = Typography;

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
