import React from 'react';
import { Button, Card, Empty, Progress, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const SEVERITY_COLORS = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
};

function TradeThesisWatchPanel({ items = [], onNavigate }) {
  return (
    <Card title="Thesis Drift Watch" variant="borderless">
      {items.length ? (
        <div style={{ display: 'grid', gap: 12 }}>
          {items.map((item) => (
            <div
              key={item.key}
              style={{
                padding: 12,
                borderRadius: 10,
                border: '1px solid rgba(255,255,255,0.08)',
                background: 'rgba(255,255,255,0.03)',
              }}
            >
              <Space wrap size={6} style={{ marginBottom: 8 }}>
                <Text strong>{item.symbol || item.title}</Text>
                {item.stance ? <Tag color="cyan">{item.stance}</Tag> : null}
                {item.horizon ? <Tag>{item.horizon}</Tag> : null}
                <Tag color={SEVERITY_COLORS[item.refreshSeverity] || 'default'}>{item.refreshLabel}</Tag>
              </Space>

              <Progress
                percent={Math.round(Number(item.score || 0) * 100)}
                strokeColor={
                  item.refreshSeverity === 'high'
                    ? '#ff4d4f'
                    : item.refreshSeverity === 'medium'
                      ? '#fa8c16'
                      : '#1677ff'
                }
                style={{ marginBottom: 8 }}
              />

              {item.summary ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#bfbfbf' }}>
                  {item.summary}
                </Paragraph>
              ) : null}

              {item.leadLeg ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#8c8c8c' }}>
                  主表达腿：{item.leadLeg}
                </Paragraph>
              ) : null}

              {item.tradeLegs?.length ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#8c8c8c' }}>
                  组合腿：
                  {item.tradeLegs
                    .slice(0, 3)
                    .map((leg) => `${leg.symbol} ${leg.side}`)
                    .join(' / ')}
                </Paragraph>
              ) : null}

              {item.driftLead ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#d9d9d9' }}>
                  漂移提示：{item.driftLead}
                </Paragraph>
              ) : null}

              {item.driftEvidence ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#8c8c8c' }}>
                  变化证据：{item.driftEvidence}
                </Paragraph>
              ) : null}

              <Button
                size="small"
                type="link"
                style={{ paddingLeft: 0 }}
                onClick={() => onNavigate?.(item.action)}
              >
                {item.action?.label || '打开交易 Thesis'}
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有进入独立观察区的交易 Thesis" />
      )}
    </Card>
  );
}

export default TradeThesisWatchPanel;
