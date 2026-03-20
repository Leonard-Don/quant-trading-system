import React from 'react';
import { Button, Card, Col, Empty, Row, Space, Typography } from 'antd';

import ResearchSummaryBanner from './ResearchSummaryBanner';
import ResearchTaskCard from './ResearchTaskCard';

const { Text } = Typography;

function ResearchPlaybook({
  playbook,
  onAction,
  onSave,
  onSaveTask,
  onUpdateSnapshot,
  saveLabel = '保存到研究工作台',
  updateLabel = '更新当前任务快照',
  saving = false,
}) {
  if (!playbook) {
    return null;
  }

  const saveHandler = onSaveTask || onSave;

  return (
    <Card
      variant="borderless"
      title={playbook.playbook_type === 'pricing' ? '定价研究剧本' : '跨市场研究剧本'}
      extra={(
        <Space>
          {saveHandler ? (
            <Button size="small" onClick={saveHandler} loading={saving}>
              {saveLabel}
            </Button>
          ) : null}
          {onUpdateSnapshot ? (
            <Button size="small" onClick={onUpdateSnapshot} loading={saving}>
              {updateLabel}
            </Button>
          ) : null}
          {playbook.stageLabel ? <Text type="secondary">{playbook.stageLabel}</Text> : null}
        </Space>
      )}
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 16 } }}
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
