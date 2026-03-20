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
                </Space>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>{card.name}</div>
                <Text style={{ color: 'rgba(125, 213, 255, 0.92)', display: 'block', marginBottom: 8 }}>
                  {card.theme || 'Macro theme'}
                </Text>
                <Paragraph style={{ color: 'rgba(245,248,252,0.82)', minHeight: 48 }}>{card.description}</Paragraph>
                <Paragraph style={{ color: 'rgba(245,248,252,0.72)', minHeight: 52, marginBottom: 10 }}>
                  {card.driverHeadline}
                </Paragraph>
                <Space wrap size={[6, 6]} style={{ display: 'flex', marginBottom: 12 }}>
                  {(card.matchedDrivers || []).map((driver) => (
                    <Tag key={driver.key} color={driver.type === 'factor' ? 'purple' : driver.type === 'alert' ? 'red' : 'blue'}>
                      {driver.label}
                    </Tag>
                  ))}
                </Space>
                <Text style={{ color: 'rgba(245,248,252,0.78)', display: 'block', marginBottom: 14 }}>
                  {card.stance}
                </Text>
                <Button size="small" type="primary" onClick={() => onNavigate?.(card.action)}>
                  {card.action.label}
                </Button>
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
