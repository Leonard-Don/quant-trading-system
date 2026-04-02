import React from 'react';
import {
  Button,
  Card,
  Empty,
  Space,
  Spin,
  Tag,
} from 'antd';
import {
  DeleteOutlined,
  FolderOpenOutlined,
  RadarChartOutlined,
} from '@ant-design/icons';

import { formatResearchSource, navigateByResearchAction } from '../../utils/researchContext';
import SnapshotComparePanel from './SnapshotComparePanel';
import {
  WorkbenchTaskActivitySection,
  WorkbenchTaskEditorSection,
  WorkbenchTaskSummarySection,
} from './WorkbenchDetailSections';
import { STATUS_COLOR } from './workbenchUtils';

const WorkbenchDetailPanel = ({
  commentDraft,
  detailLoading,
  handleAddComment,
  handleDelete,
  handleDeleteComment,
  handleMetaSave,
  handleOpenTask,
  handleRestoreArchived,
  handleStatusUpdate,
  latestSnapshotComparison,
  noteDraft,
  openTaskPriorityLabel,
  saving,
  selectedTask,
  selectedTaskRefreshSignal,
  setCommentDraft,
  setNoteDraft,
  setShowAllTimeline,
  setTitleDraft,
  showAllTimeline,
  timeline,
  timelineItems,
  titleDraft,
}) => (
  <Card
    bordered={false}
    title="任务详情"
    extra={selectedTask ? <Tag color={STATUS_COLOR[selectedTask.status] || 'default'}>{selectedTask.status}</Tag> : null}
    bodyStyle={{ minHeight: 760 }}
  >
    {detailLoading ? (
      <div style={{ minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin />
      </div>
    ) : selectedTask ? (
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space wrap>
          <Button data-testid="workbench-open-task" type="primary" icon={<FolderOpenOutlined />} onClick={handleOpenTask}>
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
          selectedTask={{
            ...selectedTask,
            sourceLabel: formatResearchSource(selectedTask.source || 'manual'),
          }}
          selectedTaskRefreshSignal={selectedTaskRefreshSignal}
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
