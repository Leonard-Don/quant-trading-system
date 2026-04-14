import React from 'react';
import { Button, Card, Empty, Progress, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const ACTION_COLORS = {
  structural_short: 'red',
  structural_avoid: 'volcano',
  watch: 'gold',
  stable: 'green',
};

function DecayWatchPanel({ items = [], onNavigate, onOpenDraft, onSaveTask }) {
  return (
    <Card title="Decay Watch" variant="borderless">
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
                <Tag color={ACTION_COLORS[item.actionLabel] || 'default'}>{item.label}</Tag>
                {item.peopleRisk ? <Tag>{`人事风险 ${item.peopleRisk}`}</Tag> : null}
                {item.primaryView ? <Tag>{`定价结论 ${item.primaryView}`}</Tag> : null}
                {item.macroMispricingThesis?.stance ? <Tag>{item.macroMispricingThesis.stance}</Tag> : null}
                <Tag color={item.score >= 0.72 ? 'red' : item.score >= 0.5 ? 'orange' : 'blue'}>
                  {item.refreshLabel}
                </Tag>
              </Space>

              <Progress
                percent={Math.round(Number(item.score || 0) * 100)}
                strokeColor={item.score >= 0.72 ? '#ff4d4f' : item.score >= 0.5 ? '#fa8c16' : '#1677ff'}
                style={{ marginBottom: 8 }}
              />

              {item.summary ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#bfbfbf' }}>
                  {item.summary}
                </Paragraph>
              ) : null}

              {item.dominantFailureLabel ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#8c8c8c' }}>
                  主导失效模式：{item.dominantFailureLabel}
                </Paragraph>
              ) : null}

              {item.macroMispricingThesis?.primary_leg?.symbol ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#8c8c8c' }}>
                  Thesis：{item.macroMispricingThesis.primary_leg.symbol} {item.macroMispricingThesis.primary_leg.side}
                  {item.macroMispricingThesis.hedge_leg?.symbol
                    ? ` / ${item.macroMispricingThesis.hedge_leg.symbol} ${item.macroMispricingThesis.hedge_leg.side}`
                    : ''}
                </Paragraph>
              ) : null}

              {item.macroMispricingThesis?.trade_legs?.length ? (
                <Paragraph style={{ marginBottom: 8, fontSize: 12, color: '#8c8c8c' }}>
                  组合腿：
                  {item.macroMispricingThesis.trade_legs
                    .slice(0, 3)
                    .map((leg) => `${leg.symbol} ${leg.side}`)
                    .join(' / ')}
                </Paragraph>
              ) : null}

              {item.evidence?.length ? (
                <Space wrap size={6} style={{ marginBottom: 8 }}>
                  {item.evidence.slice(0, 3).map((evidence) => (
                    <Tag key={evidence}>{evidence}</Tag>
                  ))}
                </Space>
              ) : null}

              <Space size={8}>
                {item.action ? (
                  <Button size="small" type="link" style={{ paddingLeft: 0 }} onClick={() => onNavigate?.(item.action)}>
                    {item.action.label || '打开任务'}
                  </Button>
                ) : null}
                <Button size="small" onClick={() => onOpenDraft?.(item)}>
                  打开跨市场草案
                </Button>
                {!item.macroTaskId ? (
                  <Button size="small" onClick={() => onSaveTask?.(item)}>
                    保存到工作台
                  </Button>
                ) : null}
              </Space>
            </div>
          ))}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前还没有进入结构性衰败观察名单的标的" />
      )}
    </Card>
  );
}

export default DecayWatchPanel;
