import React from 'react';
import { Card, Col, Row, Space, Tag, Typography } from 'antd';

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

      {results.allocation_overlay ? (
        <Card title="权重偏置对照" variant="borderless" style={{ marginTop: 16 }}>
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space wrap size={[8, 8]}>
              <Tag color={results.allocation_overlay.allocation_mode === 'macro_bias' ? 'green' : 'default'}>
                {results.allocation_overlay.allocation_mode === 'macro_bias' ? '宏观偏置' : '模板原始权重'}
              </Tag>
              {results.allocation_overlay.theme ? <Tag color="blue">{results.allocation_overlay.theme}</Tag> : null}
              {results.allocation_overlay.bias_strength ? <Tag color="green">bias {Number(results.allocation_overlay.bias_strength).toFixed(1)}pp</Tag> : null}
              {results.allocation_overlay.compression_summary?.label && results.allocation_overlay.compression_summary.label !== 'full' ? (
                <Tag color={results.allocation_overlay.compression_summary.label === 'compressed' ? 'orange' : 'gold'}>
                  压缩 {results.allocation_overlay.compression_summary.label}
                </Tag>
              ) : null}
            </Space>
            {results.allocation_overlay.bias_summary ? <Text>{results.allocation_overlay.bias_summary}</Text> : null}
            {results.allocation_overlay.compression_summary ? (
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <Text type="secondary">
                  原始偏置 {Number(results.allocation_overlay.compression_summary.raw_bias_strength || 0).toFixed(1)}pp
                  {' · '}
                  生效偏置 {Number(results.allocation_overlay.compression_summary.effective_bias_strength || 0).toFixed(1)}pp
                  {' · '}
                  收缩 {Number(results.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp
                </Text>
                {results.allocation_overlay.compression_summary.reason ? (
                  <Text type="secondary">{results.allocation_overlay.compression_summary.reason}</Text>
                ) : null}
              </Space>
            ) : null}
          </Space>
        </Card>
      ) : null}
    </Card>
  );
}

export default CrossMarketBasketSummaryCard;
