import React from 'react';
import { Button, Card, Col, Empty, Row, Space, Typography } from 'antd';

import ResearchSummaryBanner from './ResearchSummaryBanner';
import ResearchTaskCard from './ResearchTaskCard';

const { Text } = Typography;

function ResearchPlaybook({ playbook, onAction, onSave, saveLabel = '保存到研究工作台', saving = false }) {
  if (!playbook) {
    return null;
  }

  return (
    <Card
      bordered={false}
      title={playbook.playbook_type === 'pricing' ? '定价研究剧本' : '跨市场研究剧本'}
      extra={(
        <Space>
          {onSave ? (
            <Button size="small" onClick={onSave} loading={saving}>
              {saveLabel}
            </Button>
          ) : null}
          {playbook.stageLabel ? <Text type="secondary">{playbook.stageLabel}</Text> : null}
        </Space>
      )}
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
