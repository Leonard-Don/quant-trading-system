import React from 'react';
import { Card, Col, Row, Tag, Typography } from 'antd';

const { Text } = Typography;

function CrossMarketBasketSummaryCard({
  results,
  ASSET_CLASS_LABELS,
  formatPercentage,
}) {
  if (!results?.leg_performance?.long?.assets || !results?.leg_performance?.short?.assets) {
    return null;
  }

  return (
    <Card title="资产篮子摘要" variant="borderless">
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Text strong>多头篮子</Text>
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {results.leg_performance.long.assets.map((asset) => (
              <Tag key={`long-${asset.symbol}`}>{asset.symbol} · {ASSET_CLASS_LABELS[asset.asset_class] || asset.asset_class} · {formatPercentage(asset.weight)}</Tag>
            ))}
          </div>
        </Col>
        <Col xs={24} md={12}>
          <Text strong>空头篮子</Text>
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {results.leg_performance.short.assets.map((asset) => (
              <Tag key={`short-${asset.symbol}`}>{asset.symbol} · {ASSET_CLASS_LABELS[asset.asset_class] || asset.asset_class} · {formatPercentage(asset.weight)}</Tag>
            ))}
          </div>
        </Col>
      </Row>
    </Card>
  );
}

export default CrossMarketBasketSummaryCard;
