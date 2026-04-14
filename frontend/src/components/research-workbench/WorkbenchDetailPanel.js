import React from 'react';
import {
  Button,
  Card,
  Empty,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import {
  DeleteOutlined,
  FolderOpenOutlined,
  LeftOutlined,
  RadarChartOutlined,
  RightOutlined,
} from '@ant-design/icons';

import { formatResearchSource, navigateByResearchAction } from '../../utils/researchContext';
import SnapshotComparePanel from './SnapshotComparePanel';
import {
  WorkbenchTaskActivitySection,
  WorkbenchTaskEditorSection,
  WorkbenchTaskSummarySection,
} from './WorkbenchDetailSections';
import { STATUS_COLOR } from './workbenchUtils';

const { Text } = Typography;

const WorkbenchDetailPanel = ({
  commentDraft,
  detailLoading,
  handleAddComment,
  handleCopyViewLink,
  handleDelete,
  handleDeleteComment,
  handleMetaSave,
  handleOpenMatchingQueueNext,
  handleOpenNextTask,
  handleOpenTask,
  handleRestoreArchived,
  handleSelectMatchingQueueNext,
  handleSelectMatchingQueuePrevious,
  handleSelectQueueNext,
  handleSelectQueuePrevious,
  handleStatusUpdate,
  latestSnapshotComparison,
  noteDraft,
  openTaskPriorityLabel,
  saving,
  selectedMatchingQueueMeta,
  selectedTask,
  selectedTaskPriorityMeta,
  selectedTaskQueueMeta,
  selectedTaskRefreshSignal,
  setCommentDraft,
  setNoteDraft,
  setShowAllTimeline,
  setTitleDraft,
  showAllTimeline,
  timeline,
  timelineItems,
  titleDraft,
  workbenchViewSummary,
}) => (
  <Card
    data-testid="workbench-detail-panel"
    data-task-id={selectedTask?.id || ''}
    variant="borderless"
    title="任务详情"
    extra={selectedTask ? <Tag color={STATUS_COLOR[selectedTask.status] || 'default'}>{selectedTask.status}</Tag> : null}
    styles={{ body: { minHeight: 760 } }}
  >
    {detailLoading ? (
      <div style={{ minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin />
      </div>
    ) : selectedTask ? (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {selectedTaskQueueMeta?.total ? (
          <Card size="small" variant="borderless" title="当前复盘队列">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space wrap>
                <Tag color="blue">{selectedTaskQueueMeta.label}</Tag>
                {selectedTaskQueueMeta.currentTask?.title ? (
                  <Text strong>{selectedTaskQueueMeta.currentTask.title}</Text>
                ) : null}
              </Space>
              <Space wrap>
                <Button
                  size="small"
                  icon={<LeftOutlined />}
                  onClick={handleSelectQueuePrevious}
                  disabled={!selectedTaskQueueMeta.hasPrevious}
                >
                  上一条
                </Button>
                <Button
                  size="small"
                  icon={<RightOutlined />}
                  onClick={handleSelectQueueNext}
                  disabled={!selectedTaskQueueMeta.hasNext}
                >
                  下一条
                </Button>
                <Button
                  size="small"
                  type="link"
                  onClick={handleOpenNextTask}
                  disabled={!selectedTaskQueueMeta.hasNext}
                  style={{ paddingInline: 0 }}
                >
                  打开下一条研究页
                </Button>
              </Space>
              <Text type="secondary">
                {selectedTaskQueueMeta.hasNext
                  ? `下一条：${selectedTaskQueueMeta.nextTask?.title || selectedTaskQueueMeta.nextTask?.id || '-'}`
                  : '当前已经到复盘队列末尾，可以回到顶部切换其他研究视角。'}
              </Text>
            </Space>
          </Card>
        ) : null}

        {selectedMatchingQueueMeta?.total ? (
          <Card size="small" variant="borderless" title={selectedMatchingQueueMeta.title}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space wrap>
                <Tag color={selectedMatchingQueueMeta.mode === 'pricing' ? 'blue' : 'purple'}>
                  {selectedMatchingQueueMeta.label}
                </Tag>
                {selectedMatchingQueueMeta.currentTask?.title ? (
                  <Text strong>{selectedMatchingQueueMeta.currentTask.title}</Text>
                ) : null}
              </Space>
              <Space wrap>
                <Button
                  size="small"
                  icon={<LeftOutlined />}
                  onClick={handleSelectMatchingQueuePrevious}
                  disabled={!selectedMatchingQueueMeta.hasPrevious}
                >
                  上一条同类型
                </Button>
                <Button
                  size="small"
                  icon={<RightOutlined />}
                  onClick={handleSelectMatchingQueueNext}
                  disabled={!selectedMatchingQueueMeta.hasNext}
                >
                  下一条同类型
                </Button>
                <Button
                  size="small"
                  type="link"
                  onClick={handleOpenMatchingQueueNext}
                  disabled={!selectedMatchingQueueMeta.hasNext}
                  style={{ paddingInline: 0 }}
                >
                  打开下一条同类型研究页
                </Button>
              </Space>
              <Text type="secondary">
                {selectedMatchingQueueMeta.hasNext
                  ? `下一条同类型：${selectedMatchingQueueMeta.nextTask?.title || selectedMatchingQueueMeta.nextTask?.id || '-'}`
                  : '当前同类型执行队列已经到末尾，可以切到另一类执行入口继续复盘。'}
              </Text>
            </Space>
          </Card>
        ) : null}

        <Space wrap>
          <Button
            data-testid="workbench-open-task"
            data-task-id={selectedTask?.id || ''}
            type="primary"
            icon={<FolderOpenOutlined />}
            onClick={handleOpenTask}
          >
            {openTaskPriorityLabel}
          </Button>
          <Button icon={<RadarChartOutlined />} onClick={() => navigateByResearchAction({ target: 'godsEye' })}>
            回到 GodEye
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete} loading={saving}>
            删除任务
          </Button>
        </Space>

        <WorkbenchTaskSummarySection
          latestSnapshotComparison={latestSnapshotComparison}
          handleCopyViewLink={handleCopyViewLink}
          selectedTask={{
            ...selectedTask,
            sourceLabel: formatResearchSource(selectedTask.source || 'manual'),
          }}
          selectedTaskRefreshSignal={selectedTaskRefreshSignal}
          workbenchViewSummary={workbenchViewSummary}
        />

        <WorkbenchTaskEditorSection
          handleMetaSave={handleMetaSave}
          noteDraft={noteDraft}
          saving={saving}
          setNoteDraft={setNoteDraft}
          setTitleDraft={setTitleDraft}
          titleDraft={titleDraft}
        />

        <SnapshotComparePanel task={selectedTask} />

        <WorkbenchTaskActivitySection
          commentDraft={commentDraft}
          handleAddComment={handleAddComment}
          handleDeleteComment={handleDeleteComment}
          handleRestoreArchived={handleRestoreArchived}
          handleStatusUpdate={handleStatusUpdate}
          saving={saving}
          selectedTask={selectedTask}
          selectedTaskPriorityMeta={selectedTaskPriorityMeta}
          setCommentDraft={setCommentDraft}
          setShowAllTimeline={setShowAllTimeline}
          showAllTimeline={showAllTimeline}
          timeline={timeline}
          timelineItems={timelineItems}
        />
      </Space>
    ) : (
      <Empty description="请选择一个研究任务" />
    )}
  </Card>
);

export default WorkbenchDetailPanel;
