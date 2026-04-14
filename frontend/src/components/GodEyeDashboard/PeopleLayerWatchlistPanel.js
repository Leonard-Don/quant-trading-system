import React from 'react';
import { Button, Card, Empty, List, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

function buildPricingAction(item) {
  return {
    target: 'pricing',
    symbol: item?.symbol || '',
    source: 'godeye_people_watchlist',
    note: item?.summary || '来自 GodEye People Layer Watchlist',
  };
}

function buildCrossMarketAction(item) {
  return {
    target: 'cross-market',
    template: item?.risk_level === 'high'
      ? 'people_decay_short_vs_cashflow_defensive'
      : 'defensive_beta_hedge',
    source: 'godeye_people_watchlist',
    note: item?.summary || '来自 GodEye People Layer Watchlist',
  };
}

export default function PeopleLayerWatchlistPanel({ overview = {}, onNavigate }) {
  const summary = overview?.people_layer_summary || {};
  const watchlist = summary?.watchlist || [];

  return (
    <Card
      title="People Layer Watchlist"
      extra={summary?.label ? <Tag color={summary.label === 'fragile' ? 'red' : summary.label === 'watch' ? 'gold' : 'green'}>{summary.label}</Tag> : null}
      styles={{ body: { minHeight: 280 } }}
    >
      {summary?.summary ? (
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>
          {summary.summary}
        </Paragraph>
      ) : null}
      {!watchlist.length ? (
        <Empty description="暂无 people layer watchlist" />
      ) : (
        <List
          dataSource={watchlist.slice(0, 5)}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button key="pricing" size="small" type="link" onClick={() => onNavigate?.(buildPricingAction(item))}>定价</Button>,
                <Button key="cross-market" size="small" type="link" onClick={() => onNavigate?.(buildCrossMarketAction(item))}>跨市场</Button>,
              ]}
            >
              <List.Item.Meta
                title={(
                  <Space wrap size={6}>
                    <Text strong>{item?.symbol || '-'}</Text>
                    {item?.company_name ? <Text type="secondary">{item.company_name}</Text> : null}
                    <Tag color={item?.risk_level === 'high' ? 'red' : item?.risk_level === 'medium' ? 'gold' : 'green'}>
                      风险 {item?.risk_level || 'unknown'}
                    </Tag>
                    <Tag color={item?.stance === 'supportive' ? 'green' : item?.stance === 'fragile' ? 'red' : 'blue'}>
                      {item?.stance || 'balanced'}
                    </Tag>
                  </Space>
                )}
                description={(
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    <Text type="secondary">
                      脆弱度 {Number(item?.people_fragility_score || 0).toFixed(2)}
                      {' · '}
                      质量 {Number(item?.people_quality_score || 0).toFixed(2)}
                    </Text>
                    {(item?.source_modes || []).length ? (
                      <Text type="secondary">来源 {(item.source_modes || []).join(' / ')}</Text>
                    ) : null}
                    {item?.summary ? <Text>{item.summary}</Text> : null}
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      )}
    </Card>
  );
}
