import React from 'react';
import { Button, Card, Col, Empty, Row, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

function CrossMarketOverview({ cards = [], onNavigate }) {
  return (
    <Card
      title="Cross-Market Overview"
      variant="borderless"
      extra={<Tag color="cyan">{cards.length} templates</Tag>}
      styles={{ body: { minHeight: 320 } }}
    >
      {cards.length ? (
        <Row gutter={[12, 12]}>
          {cards.map((card) => (
            <Col xs={24} md={12} key={card.id}>
              <div
                style={{
                  height: '100%',
                  borderRadius: 14,
                  padding: 16,
                  background: 'linear-gradient(135deg, rgba(14, 28, 41, 0.92), rgba(24, 60, 90, 0.88))',
                  color: '#f5f8fc',
                }}
              >
                <Space wrap style={{ marginBottom: 10 }}>
                  <Tag color={card.recommendationTone || 'blue'}>{card.recommendationTier || '候选模板'}</Tag>
                  <Tag color="geekblue">{card.construction_mode}</Tag>
                  {card.executionPosture ? <Tag color="lime">{card.executionPosture}</Tag> : null}
                  <Tag color="gold">{card.longCount}L / {card.shortCount}S</Tag>
                  <Tag color="cyan">score {Number(card.recommendationScore || 0).toFixed(2)}</Tag>
                  {card.resonanceLabel && card.resonanceLabel !== 'mixed' ? (
                    <Tag color="magenta">resonance {card.resonanceLabel}</Tag>
                  ) : null}
                  {card.policySourceHealthLabel && card.policySourceHealthLabel !== 'unknown' ? (
                    <Tag color={card.policySourceHealthLabel === 'fragile' ? 'red' : card.policySourceHealthLabel === 'watch' ? 'gold' : 'green'}>
                      policy source {card.policySourceHealthLabel}
                    </Tag>
                  ) : null}
                  {card.inputReliabilityLabel && card.inputReliabilityLabel !== 'unknown' ? (
                    <Tag color={card.inputReliabilityLabel === 'fragile' ? 'red' : card.inputReliabilityLabel === 'watch' ? 'gold' : 'green'}>
                      input {card.inputReliabilityLabel}
                    </Tag>
                  ) : null}
                  {card.sourceModeLabel && card.sourceModeLabel !== 'mixed' ? (
                    <Tag color={card.sourceModeLabel === 'official-led' ? 'green' : card.sourceModeLabel === 'fallback-heavy' ? 'orange' : 'blue'}>
                      来源 {card.sourceModeLabel}
                    </Tag>
                  ) : null}
                  {card.policyExecutionLabel && card.policyExecutionLabel !== 'unknown' ? (
                    <Tag color={card.policyExecutionLabel === 'chaotic' ? 'red' : card.policyExecutionLabel === 'watch' ? 'gold' : 'green'}>
                      政策执行 {card.policyExecutionLabel}
                    </Tag>
                  ) : null}
                  {card.trendLabel ? (
                    <Tag color={card.trendTone || 'default'}>{card.trendLabel}</Tag>
                  ) : null}
                  {card.taskRefreshLabel ? (
                    <Tag color={card.taskRefreshTone || 'default'}>{card.taskRefreshLabel}</Tag>
                  ) : null}
                  {card.taskRefreshResonanceDriven ? (
                    <Tag color="magenta">共振驱动</Tag>
                  ) : null}
                  {card.taskRefreshBiasCompressionCore ? (
                    <Tag color="volcano">核心腿受压</Tag>
                  ) : null}
                  {card.taskRefreshSelectionQualityDriven ? (
                    <Tag color="orange">自动降级驱动</Tag>
                  ) : null}
                  {card.taskRefreshSelectionQualityActive ? (
                    <Tag color="gold">降级运行</Tag>
                  ) : null}
                  {card.taskRefreshReviewContextDriven ? (
                    <Tag color="geekblue">复核语境切换</Tag>
                  ) : null}
                  {card.taskRefreshInputReliabilityDriven ? (
                    <Tag color="blue">输入可靠度变化</Tag>
                  ) : null}
                  {card.rankingPenalty ? (
                    <Tag color="orange">排序降级</Tag>
                  ) : null}
                  {card.taskRefreshPolicySourceDriven ? (
                    <Tag color="red">政策源驱动</Tag>
                  ) : null}
                  {card.taskRefreshBiasCompressionDriven ? (
                    <Tag color="orange">偏置收缩</Tag>
                  ) : null}
                </Space>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>{card.name}</div>
                <Text style={{ color: 'rgba(125, 213, 255, 0.92)', display: 'block', marginBottom: 8 }}>
                  {card.theme || 'Macro theme'}
                </Text>
                {(card.themeCore || card.themeSupport) ? (
                  <Text style={{ color: 'rgba(245,248,252,0.76)', display: 'block', marginBottom: 8 }}>
                    核心腿：{card.themeCore || '暂无'} ｜ 辅助腿：{card.themeSupport || '暂无'}
                  </Text>
                ) : null}
                <Paragraph style={{ color: 'rgba(245,248,252,0.82)', minHeight: 48 }}>{card.description}</Paragraph>
                <Paragraph style={{ color: 'rgba(245,248,252,0.72)', minHeight: 52, marginBottom: 10 }}>
                  {card.driverHeadline}
                </Paragraph>
                {card.policyExecutionReason ? (
                  <Paragraph style={{ color: 'rgba(255, 205, 132, 0.92)', minHeight: 30, marginBottom: 10 }}>
                    政策执行：{card.policyExecutionReason}
                    {card.policyExecutionTopDepartment ? ` · ${card.policyExecutionTopDepartment}` : ''}
                    {card.policyExecutionRiskBudgetScale !== undefined
                      ? ` · 风险预算 ${Number(card.policyExecutionRiskBudgetScale || 1).toFixed(2)}x`
                      : ''}
                  </Paragraph>
                ) : null}
                {card.sourceModeReason ? (
                  <Paragraph style={{ color: 'rgba(173, 216, 255, 0.92)', minHeight: 30, marginBottom: 10 }}>
                    来源治理：{card.sourceModeReason}
                    {card.sourceModeRiskBudgetScale !== undefined
                      ? ` · 风险预算 ${Number(card.sourceModeRiskBudgetScale || 1).toFixed(2)}x`
                      : ''}
                  </Paragraph>
                ) : null}
                {card.resonanceReason && card.resonanceLabel !== 'mixed' ? (
                  <Paragraph style={{ color: 'rgba(255, 171, 245, 0.9)', minHeight: 32, marginBottom: 10 }}>
                    {card.resonanceReason}
                  </Paragraph>
                ) : null}
                {card.trendSummary ? (
                  <Paragraph style={{ color: 'rgba(255, 215, 128, 0.9)', minHeight: 36, marginBottom: 10 }}>
                    {card.trendSummary}
                  </Paragraph>
                ) : null}
                {card.taskRefreshSummary ? (
                  <Paragraph style={{ color: 'rgba(255, 177, 112, 0.92)', minHeight: 36, marginBottom: 10 }}>
                    {card.taskRefreshSummary}
                  </Paragraph>
                ) : null}
                {card.taskRefreshReviewContextShift?.lead ? (
                  <Paragraph style={{ color: 'rgba(168, 198, 255, 0.9)', minHeight: 28, marginBottom: 10 }}>
                    {card.taskRefreshReviewContextShift.lead}
                  </Paragraph>
                ) : null}
                {card.taskRecentComparisonLead ? (
                  <Paragraph style={{ color: 'rgba(196, 230, 255, 0.86)', minHeight: 30, marginBottom: 10 }}>
                    最近两版：{card.taskRecentComparisonLead}
                  </Paragraph>
                ) : null}
                {card.taskRefreshPolicySourceShift?.currentReason ? (
                  <Paragraph style={{ color: 'rgba(255, 120, 120, 0.92)', minHeight: 30, marginBottom: 10 }}>
                    政策源状态：{card.taskRefreshPolicySourceShift.currentReason}
                  </Paragraph>
                ) : null}
                {card.taskRefreshInputReliabilityShift?.currentLead ? (
                  <Paragraph style={{ color: 'rgba(173, 216, 255, 0.92)', minHeight: 30, marginBottom: 10 }}>
                    输入可靠度：{card.taskRefreshInputReliabilityShift.currentLead}
                  </Paragraph>
                ) : null}
                {card.taskRefreshBiasCompressionShift?.currentReason ? (
                  <Paragraph style={{ color: 'rgba(255, 190, 120, 0.9)', minHeight: 30, marginBottom: 10 }}>
                    偏置收缩：{card.taskRefreshBiasCompressionShift.currentReason}
                    {' · '}
                    scale {Number(card.taskRefreshBiasCompressionShift.savedScale || 1).toFixed(2)}x→{Number(card.taskRefreshBiasCompressionShift.currentScale || 1).toFixed(2)}x
                  </Paragraph>
                ) : null}
                {card.taskRefreshSelectionQualityShift?.currentReason && !card.taskRefreshBiasCompressionShift?.currentReason ? (
                  <Paragraph style={{ color: 'rgba(255, 182, 114, 0.9)', minHeight: 26, marginBottom: 10 }}>
                    自动降级：{card.taskRefreshSelectionQualityShift.currentReason}
                  </Paragraph>
                ) : null}
                {card.taskRefreshSelectionQualityRunState?.active ? (
                  <Paragraph style={{ color: 'rgba(255, 212, 120, 0.92)', minHeight: 28, marginBottom: 10 }}>
                    降级运行：当前结果已按 {card.taskRefreshSelectionQualityRunState.label} 强度运行
                    {card.taskRefreshSelectionQualityRunState.baseScore || card.taskRefreshSelectionQualityRunState.effectiveScore
                      ? ` · ${Number(card.taskRefreshSelectionQualityRunState.baseScore || 0).toFixed(2)}→${Number(card.taskRefreshSelectionQualityRunState.effectiveScore || 0).toFixed(2)}`
                      : ''}
                    {card.taskRefreshSelectionQualityRunState.reason
                      ? ` · ${card.taskRefreshSelectionQualityRunState.reason}`
                      : ''}
                  </Paragraph>
                ) : null}
                {card.taskRefreshTopCompressedAsset ? (
                  <Paragraph style={{ color: 'rgba(255, 204, 128, 0.9)', minHeight: 24, marginBottom: 10 }}>
                    压缩焦点：{card.taskRefreshTopCompressedAsset}
                    {card.taskRefreshBiasCompressionCore ? ' · 主题核心腿已进入压缩焦点' : ''}
                  </Paragraph>
                ) : null}
                {card.rankingPenaltyReason ? (
                  <Paragraph style={{ color: 'rgba(255, 170, 120, 0.88)', minHeight: 26, marginBottom: 10 }}>
                    排序调整：{card.rankingPenaltyReason}
                    {card.baseRecommendationScore !== undefined ? ` · ${Number(card.baseRecommendationScore || 0).toFixed(2)}→${Number(card.recommendationScore || 0).toFixed(2)}` : ''}
                  </Paragraph>
                ) : null}
                {card.policySourceHealthReason && !card.taskRefreshPolicySourceShift?.currentReason ? (
                  <Paragraph style={{ color: 'rgba(255, 160, 120, 0.88)', minHeight: 30, marginBottom: 10 }}>
                    政策源质量：{card.policySourceHealthReason}
                  </Paragraph>
                ) : null}
                {card.inputReliabilityLead ? (
                  <Paragraph style={{ color: 'rgba(210, 229, 255, 0.88)', minHeight: 30, marginBottom: 10 }}>
                    输入可靠度：{card.inputReliabilityLead}
                    {card.inputReliabilityScore ? ` · score ${Number(card.inputReliabilityScore || 0).toFixed(2)}` : ''}
                  </Paragraph>
                ) : null}
                {card.inputReliabilityPosture ? (
                  <Paragraph style={{ color: 'rgba(210, 229, 255, 0.72)', minHeight: 24, marginBottom: 10 }}>
                    使用姿势：{card.inputReliabilityPosture}
                  </Paragraph>
                ) : null}
                <Space wrap size={[6, 6]} style={{ display: 'flex', marginBottom: 12 }}>
                  {(card.matchedDrivers || []).map((driver) => (
                    <Tag
                      key={driver.key}
                      color={
                        driver.type === 'factor'
                          ? 'purple'
                          : driver.type === 'alert'
                            ? 'red'
                            : driver.type === 'resonance'
                              ? 'magenta'
                              : 'blue'
                      }
                    >
                      {driver.label}
                    </Tag>
                  ))}
                </Space>
                {(card.latestThemeCore || card.latestThemeSupport) ? (
                  <Text style={{ color: 'rgba(245,248,252,0.76)', display: 'block', marginBottom: 10 }}>
                    核心腿：{card.latestThemeCore || '暂无'} ｜ 辅助腿：{card.latestThemeSupport || '暂无'}
                  </Text>
                ) : null}
                {card.latestTopCompressedAsset ? (
                  <Text style={{ color: 'rgba(255, 210, 138, 0.82)', display: 'block', marginBottom: 10 }}>
                    当前压缩焦点：{card.latestTopCompressedAsset}
                    {card.latestCompressionEffect ? ` ｜ 收缩 ${Number(card.latestCompressionEffect || 0).toFixed(1)}pp` : ''}
                  </Text>
                ) : null}
                <Text style={{ color: 'rgba(245,248,252,0.78)', display: 'block', marginBottom: 14 }}>
                  {card.stance}
                </Text>
                <Space wrap>
                  <Button size="small" type="primary" onClick={() => onNavigate?.(card.action)}>
                    {card.action.label}
                  </Button>
                  {card.taskAction ? (
                    <Button size="small" onClick={() => onNavigate?.(card.taskAction)}>
                      {card.taskAction.label}
                    </Button>
                  ) : null}
                </Space>
              </div>
            </Col>
          ))}
        </Row>
      ) : (
        <Empty description="暂无跨市场模板" />
      )}
    </Card>
  );
}

export default CrossMarketOverview;
