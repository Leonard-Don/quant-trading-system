import React from 'react';
import { Button, Card, Empty, Progress, Space, Tag, Typography } from 'antd';

const { Paragraph, Text } = Typography;

const LABEL_COLOR = {
  decay_alert: 'red',
  decay_watch: 'orange',
  stable: 'green',
};

const AXIS_COLOR = {
  critical: '#ff4d4f',
  watch: '#faad14',
  stable: '#52c41a',
};

function StructuralDecayRadarPanel({ model = {}, onNavigate }) {
  const axes = model?.axes || [];
  if (!model || !axes.length) {
    return (
      <Card title="结构衰败雷达" variant="borderless">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂缺结构衰败雷达数据" />
      </Card>
    );
  }

  const score = Number(model.score || 0);
  const actionNote = model.action_hint || '来自结构衰败雷达的系统级观察。';

  return (
    <Card
      title="结构衰败雷达"
      variant="borderless"
      extra={<Tag color={LABEL_COLOR[model.label] || 'default'}>{model.display_label || model.label}</Tag>}
    >
      <Progress
        percent={Math.round(score * 100)}
        strokeColor={score >= 0.68 ? '#ff4d4f' : score >= 0.44 ? '#fa8c16' : '#52c41a'}
        style={{ marginBottom: 10 }}
      />

      <Paragraph style={{ marginBottom: 12, fontSize: 12, color: '#bfbfbf' }}>
        {model.action_hint}
      </Paragraph>

      <div style={{ display: 'grid', gap: 10 }}>
        {axes.map((axis) => (
          <div key={axis.key}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text>{axis.label}</Text>
              <Text type="secondary">{Math.round(Number(axis.score || 0) * 100)}%</Text>
            </Space>
            <Progress
              percent={Math.round(Number(axis.score || 0) * 100)}
              showInfo={false}
              strokeColor={AXIS_COLOR[axis.status] || '#1677ff'}
              size="small"
            />
            {axis.status !== 'stable' ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {axis.summary}
              </Text>
            ) : null}
          </div>
        ))}
      </div>

      {model.top_signals?.length ? (
        <Space wrap size={6} style={{ marginTop: 12 }}>
          {model.top_signals.slice(0, 3).map((signal) => (
            <Tag key={signal.key}>{signal.label} {Math.round(Number(signal.score || 0) * 100)}%</Tag>
          ))}
        </Space>
      ) : null}

      <Space wrap size={8} style={{ marginTop: 12 }}>
        <Button
          size="small"
          type={model.label === 'decay_alert' ? 'primary' : 'default'}
          onClick={() => onNavigate?.({
            target: 'cross-market',
            template: 'defensive_beta_hedge',
            source: 'decay_radar',
            note: actionNote,
          })}
        >
          打开防御模板
        </Button>
        <Button
          size="small"
          onClick={() => onNavigate?.({
            target: 'workbench',
            refresh: 'high',
            type: 'macro_mispricing',
            reason: 'structural_decay',
            source: 'decay_radar',
            note: actionNote,
          })}
        >
          查看衰败任务
        </Button>
      </Space>
    </Card>
  );
}

export default StructuralDecayRadarPanel;
