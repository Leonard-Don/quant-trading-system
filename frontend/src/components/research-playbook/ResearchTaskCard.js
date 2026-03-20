import React from 'react';
import { Button, Card, Tag, Typography } from 'antd';

import { STATUS_LABELS } from './playbookViewModels';

const { Paragraph, Text } = Typography;

const STATUS_COLORS = {
  ready: 'processing',
  blocked: 'default',
  warning: 'warning',
  complete: 'success',
};

function ResearchTaskCard({ task, onAction }) {
  return (
    <Card
      size="small"
      variant="borderless"
      style={{ height: '100%' }}
      extra={<Tag color={STATUS_COLORS[task.status] || 'default'}>{STATUS_LABELS[task.status] || task.status}</Tag>}
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 10, minHeight: 180 } }}
    >
      <Text strong>{task.title}</Text>
      <Paragraph style={{ marginBottom: 0, flex: 1 }}>
        {task.description}
      </Paragraph>
      {task.cta ? (
        <Button size="small" type="primary" onClick={() => onAction?.(task.cta)}>
          {task.cta.label}
        </Button>
      ) : null}
    </Card>
  );
}

export default ResearchTaskCard;
