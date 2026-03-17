import React from 'react';
import { Card, Col, Empty, Row, Space, Typography } from 'antd';

import ResearchSummaryBanner from './ResearchSummaryBanner';
import ResearchTaskCard from './ResearchTaskCard';

const { Text } = Typography;

function ResearchPlaybook({ playbook, onAction }) {
  if (!playbook) {
    return null;
  }

  return (
    <Card
      bordered={false}
      title={playbook.playbook_type === 'pricing' ? '定价研究剧本' : '跨市场研究剧本'}
      extra={playbook.stageLabel ? <Text type="secondary">{playbook.stageLabel}</Text> : null}
      bodyStyle={{ display: 'flex', flexDirection: 'column', gap: 16 }}
    >
      <ResearchSummaryBanner
        title={playbook.playbook_type}
        headline={playbook.headline}
        thesis={playbook.thesis}
        context={playbook.context}
        warnings={playbook.warnings}
        nextActions={playbook.next_actions}
        onAction={onAction}
      />

      {playbook.tasks?.length ? (
        <Row gutter={[12, 12]}>
          {playbook.tasks.map((task) => (
            <Col xs={24} md={12} key={task.id}>
              <ResearchTaskCard task={task} onAction={onAction} />
            </Col>
          ))}
        </Row>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Empty description="暂无研究任务卡" />
        </Space>
      )}
    </Card>
  );
}

export default ResearchPlaybook;
