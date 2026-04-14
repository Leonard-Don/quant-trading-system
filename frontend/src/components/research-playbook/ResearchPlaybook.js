import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Empty, Row, Space, Typography } from 'antd';

import ResearchSummaryBanner from './ResearchSummaryBanner';
import ResearchTaskCard from './ResearchTaskCard';

const { Text } = Typography;

function ResearchPlaybook({
  playbook,
  onAction,
  onSave,
  onSaveTask,
  onSecondarySaveTask,
  onUpdateSnapshot,
  saveLabel = '保存到研究工作台',
  secondarySaveLabel = '保存为交易 Thesis',
  updateLabel = '更新当前任务快照',
  saving = false,
  saveLoading,
  secondarySaveLoading,
  updateLoading,
}) {
  const saveHandler = onSaveTask || onSave;
  const [checkedTaskIds, setCheckedTaskIds] = useState([]);
  const tasks = useMemo(() => playbook?.tasks || [], [playbook]);
  const taskIds = useMemo(() => tasks.map((task) => task.id), [tasks]);
  const taskSignature = useMemo(() => taskIds.join('|'), [taskIds]);

  useEffect(() => {
    setCheckedTaskIds([]);
  }, [playbook?.headline, taskSignature]);

  if (!playbook) {
    return null;
  }

  const completedCount = checkedTaskIds.length;
  const totalTasks = taskIds.length;

  return (
    <Card
      variant="borderless"
      title={playbook.playbook_type === 'pricing' ? '定价研究剧本' : '跨市场研究剧本'}
      extra={(
        <Space>
          {onSecondarySaveTask ? (
            <Button
              data-testid="research-playbook-save-secondary-task"
              size="small"
              onClick={onSecondarySaveTask}
              loading={secondarySaveLoading ?? saving}
            >
              {secondarySaveLabel}
            </Button>
          ) : null}
          {saveHandler ? (
            <Button
              data-testid="research-playbook-save-task"
              size="small"
              onClick={saveHandler}
              loading={saveLoading ?? saving}
            >
              {saveLabel}
            </Button>
          ) : null}
          {onUpdateSnapshot ? (
            <Button
              data-testid="research-playbook-update-snapshot"
              size="small"
              onClick={onUpdateSnapshot}
              disabled={Boolean(updateLoading ?? saving)}
            >
              {updateLabel}
            </Button>
          ) : null}
          {totalTasks ? <Text type="secondary">{`已勾选 ${completedCount}/${totalTasks}`}</Text> : null}
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

      {tasks.length ? (
        <Row gutter={[12, 12]}>
          {tasks.map((task) => (
            <Col xs={24} md={12} key={task.id}>
              <ResearchTaskCard
                task={task}
                onAction={onAction}
                checked={checkedTaskIds.includes(task.id)}
                onToggle={(taskId, checked) => {
                  setCheckedTaskIds((prev) => (
                    checked
                      ? [...prev, taskId].filter((value, index, array) => array.indexOf(value) === index)
                      : prev.filter((item) => item !== taskId)
                  ));
                }}
              />
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
