import React, { useMemo, useState } from 'react';
import { Button, Card, Empty, Space, Tag, Timeline, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const directionColor = {
  stimulus: 'green',
  tightening: 'red',
  neutral: 'default',
};

function PolicyTimelineBar({ items = [], onNavigate }) {
  const [activeKey, setActiveKey] = useState(null);

  const activeItem = useMemo(
    () => items.find((item) => item.key === activeKey) || items[0],
    [items, activeKey]
  );

  return (
    <Card title="Policy Timeline" variant="borderless" styles={{ body: { minHeight: 360 } }}>
      {items.length ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ maxHeight: 240, overflowY: 'auto', paddingRight: 8 }}>
            <Timeline
              items={items.slice(0, 8).map((item) => ({
                color: directionColor[item.direction] || 'blue',
                children: (
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => setActiveKey(item.key)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') setActiveKey(item.key);
                    }}
                    style={{
                      cursor: 'pointer',
                      padding: '6px 8px',
                      borderRadius: 10,
                      background: activeItem?.key === item.key ? 'rgba(24, 144, 255, 0.12)' : 'transparent',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <Tag color={directionColor[item.direction]}>{item.directionLabel}</Tag>
                      <Text type="secondary">{new Date(item.timestamp).toLocaleString()}</Text>
                    </div>
                    <Text strong>{item.title}</Text>
                  </div>
                ),
              }))}
            />
          </div>

          {activeItem ? (
            <div
              style={{
                padding: 14,
                borderRadius: 14,
                background: 'rgba(10, 25, 38, 0.75)',
                border: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                <Tag color={directionColor[activeItem.direction]}>{activeItem.directionLabel}</Tag>
                <Tag>{activeItem.source}</Tag>
                <Tag color="blue">score {activeItem.score.toFixed(2)}</Tag>
              </div>
              <Paragraph style={{ color: '#f5f8fc', marginBottom: 8 }}>{activeItem.title}</Paragraph>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {activeItem.tags.length ? activeItem.tags.map((tag) => <Tag key={tag}>{tag}</Tag>) : <Text type="secondary">暂无产业标签</Text>}
              </div>
              <Space wrap style={{ marginTop: 12 }}>
                {activeItem.primaryAction ? (
                  <Button size="small" type="primary" onClick={() => onNavigate?.(activeItem.primaryAction)}>
                    {activeItem.primaryAction.label}
                  </Button>
                ) : null}
                {activeItem.secondaryAction ? (
                  <Button size="small" onClick={() => onNavigate?.(activeItem.secondaryAction)}>
                    {activeItem.secondaryAction.label}
                  </Button>
                ) : null}
              </Space>
            </div>
          ) : null}
        </div>
      ) : (
        <Empty description="暂无政策时间轴" />
      )}
    </Card>
  );
}

export default PolicyTimelineBar;
