import React from 'react';
import { Button, Card, Col, Empty, Row, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

function CrossMarketOverview({ cards = [], onNavigate }) {
  return (
    <Card
      title="Cross-Market Overview"
      bordered={false}
      extra={<Tag color="cyan">{cards.length} templates</Tag>}
      bodyStyle={{ minHeight: 320 }}
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
                  {card.rankingPenalty ? (
                    <Tag color="orange">自动降级</Tag>
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
                <Paragraph style={{ color: 'rgba(245,248,252,0.82)', minHeight: 48 }}>{card.description}</Paragraph>
                <Paragraph style={{ color: 'rgba(245,248,252,0.72)', minHeight: 52, marginBottom: 10 }}>
                  {card.driverHeadline}
                </Paragraph>
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
                {card.taskRefreshPolicySourceShift?.currentReason ? (
                  <Paragraph style={{ color: 'rgba(255, 120, 120, 0.92)', minHeight: 30, marginBottom: 10 }}>
                    政策源状态：{card.taskRefreshPolicySourceShift.currentReason}
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
