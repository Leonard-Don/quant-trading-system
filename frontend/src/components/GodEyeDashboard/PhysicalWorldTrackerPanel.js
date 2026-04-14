import React from 'react';
import { Card, Empty, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const MODE_LABELS = {
  official: '官方',
  market: '市场',
  proxy: '代理',
  curated: '人工回退',
  derived: '派生',
};

function buildPhysicalCards(snapshot = {}) {
  const macro = snapshot?.signals?.macro_hf || {};
  const dimensions = macro?.dimensions || {};
  const latest = macro?.latest_readings || {};

  return [
    {
      key: 'trade',
      title: '海关 / 贸易脉冲',
      score: Number(dimensions?.trade?.score || 0),
      freshness: latest?.customs_data?.freshness || latest?.trade?.freshness || '',
      sourceMode: latest?.customs_data?.source_mode || latest?.trade?.source_mode || '',
      fallbackReason: latest?.customs_data?.fallback_reason || latest?.trade?.fallback_reason || '',
      summary: dimensions?.trade?.summary || macro?.summary || '',
    },
    {
      key: 'inventory',
      title: 'LME / 库存压力',
      score: Number(dimensions?.inventory?.score || 0),
      freshness: latest?.lme_inventory?.freshness || latest?.inventory?.freshness || '',
      sourceMode: latest?.lme_inventory?.source_mode || latest?.inventory?.source_mode || '',
      fallbackReason: latest?.lme_inventory?.fallback_reason || latest?.inventory?.fallback_reason || '',
      summary: dimensions?.inventory?.summary || macro?.summary || '',
    },
    {
      key: 'logistics',
      title: '港口 / 物流摩擦',
      score: Number(dimensions?.logistics?.score || 0),
      freshness: latest?.port_congestion?.freshness || latest?.logistics?.freshness || '',
      sourceMode: latest?.port_congestion?.source_mode || latest?.logistics?.source_mode || '',
      fallbackReason: latest?.port_congestion?.fallback_reason || latest?.logistics?.fallback_reason || '',
      summary: dimensions?.logistics?.summary || macro?.summary || '',
    },
  ];
}

export default function PhysicalWorldTrackerPanel({ snapshot = {} }) {
  const cards = buildPhysicalCards(snapshot);
  const hasSignal = cards.some((item) => item.score || item.summary || item.sourceMode);

  return (
    <Card title="Physical World Tracker" styles={{ body: { minHeight: 280 } }}>
      {!hasSignal ? (
        <Empty description="暂无物理世界高频数据" />
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {cards.map((item) => (
            <div
              key={item.key}
              style={{
                padding: 12,
                borderRadius: 12,
                border: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(12, 24, 34, 0.72)',
              }}
            >
              <Space wrap size={6} style={{ marginBottom: 8 }}>
                <Text strong style={{ color: '#f5f8fc' }}>{item.title}</Text>
                <Tag color={item.score >= 0.55 ? 'red' : item.score >= 0.25 ? 'gold' : 'green'}>
                  score {item.score.toFixed(2)}
                </Tag>
                {item.sourceMode ? <Tag>{MODE_LABELS[item.sourceMode] || item.sourceMode}</Tag> : null}
                {item.freshness ? <Tag>{item.freshness}</Tag> : null}
              </Space>
              {item.summary ? (
                <Paragraph style={{ marginBottom: 6, color: 'rgba(245,248,252,0.85)' }}>
                  {item.summary}
                </Paragraph>
              ) : null}
              {item.fallbackReason ? (
                <Text type="secondary">fallback: {item.fallbackReason}</Text>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
