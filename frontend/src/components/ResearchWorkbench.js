import React, { useEffect, useState } from 'react';
import {
  Card,
  Col,
  Row,
  Space,
  Tag,
  Typography,
  message,
} from 'antd';

import {
  addResearchTaskComment,
  deleteResearchTask,
  deleteResearchTaskComment,
  reorderResearchBoard,
  updateResearchTask,
} from '../services/api';
import {
  navigateByResearchAction,
} from '../utils/researchContext';
import WorkbenchBoardSection from './research-workbench/WorkbenchBoardSection';
import WorkbenchDetailPanel from './research-workbench/WorkbenchDetailPanel';
import WorkbenchOverviewPanels from './research-workbench/WorkbenchOverviewPanels';
import WorkbenchTaskCard from './research-workbench/WorkbenchTaskCard';
import useResearchWorkbenchData from './research-workbench/useResearchWorkbenchData';
import {
  buildReorderPayload,
  moveBoardTask,
  normalizeBoardOrders,
  REASON_OPTIONS,
  REFRESH_OPTIONS,
  TYPE_OPTIONS,
} from './research-workbench/workbenchUtils';

const { Paragraph, Title } = Typography;

function ResearchWorkbench() {
  const {
    archivedTasks,
    boardColumns,
    detailLoading,
    dragState,
    filters,
    latestSnapshotComparison,
    loadTaskDetail,
    loadWorkbench,
    loading,
    openTaskPriorityLabel,
    openTaskPriorityNote,
    refreshCurrentTask,
    refreshSignals,
    refreshStats,
    selectedTask,
    selectedTaskId,
    selectedTaskRefreshSignal,
    setDragState,
    setFilters,
    setSelectedTaskId,
    setShowAllTimeline,
    setShowArchived,
    showAllTimeline,
    showArchived,
    sourceOptions,
    stats,
    tasks,
    setTasks,
    timeline,
    timelineItems,
  } = useResearchWorkbenchData();
  const [saving, setSaving] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [commentDraft, setCommentDraft] = useState('');

  useEffect(() => {
    if (!selectedTask) {
      setTitleDraft('');
      setNoteDraft('');
      setCommentDraft('');
      setShowAllTimeline(false);
      return;
    }
    setTitleDraft(selectedTask.title || '');
    setNoteDraft(selectedTask.note || '');
    setShowAllTimeline(false);
  }, [selectedTask, setShowAllTimeline]);

  const handleStatusUpdate = async (status) => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await updateResearchTask(selectedTask.id, { status });
      message.success(status === 'archived' ? '任务已归档' : '任务状态已更新');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '更新任务状态失败');
    } finally {
      setSaving(false);
    }
  };

  const handleMetaSave = async () => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await updateResearchTask(selectedTask.id, {
        title: titleDraft,
        note: noteDraft,
      });
      message.success('任务信息已保存');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '保存任务信息失败');
    } finally {
      setSaving(false);
    }
  };

  const handleAddComment = async () => {
    if (!selectedTask || !commentDraft.trim()) return;
    setSaving(true);
    try {
      await addResearchTaskComment(selectedTask.id, {
        body: commentDraft.trim(),
        author: 'local',
      });
      setCommentDraft('');
      message.success('评论已添加');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '添加评论失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteComment = async (commentId) => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await deleteResearchTaskComment(selectedTask.id, commentId);
      message.success('评论已删除');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '删除评论失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await deleteResearchTask(selectedTask.id);
      message.success('任务已删除');
      await loadWorkbench();
    } catch (error) {
      message.error(error.userMessage || error.message || '删除任务失败');
    } finally {
      setSaving(false);
    }
  };

  const handleRestoreArchived = async (taskId) => {
    setSaving(true);
    try {
      await updateResearchTask(taskId, { status: 'new' });
      message.success('任务已恢复到新建列');
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '恢复任务失败');
    } finally {
      setSaving(false);
    }
  };

  const handleOpenTask = () => {
    if (!selectedTask) return;

    if (selectedTask.type === 'pricing' && selectedTask.symbol) {
      navigateByResearchAction({
        target: 'pricing',
        symbol: selectedTask.symbol,
        period: selectedTask.snapshot?.payload?.period || selectedTask.context?.period || '',
        source: 'research_workbench',
        note: openTaskPriorityNote,
      });
      return;
    }

    if (selectedTask.type === 'cross_market' && selectedTask.template) {
      navigateByResearchAction({
        target: 'cross-market',
        template: selectedTask.template,
        source: 'research_workbench',
        note: openTaskPriorityNote,
      });
      return;
    }

    navigateByResearchAction({
      target: 'godsEye',
      source: 'research_workbench',
      note: '返回 GodEye 继续筛选研究线索',
    });
  };

  const commitBoardReorder = async (nextTasks, successMessage = '看板顺序已更新') => {
    const previousTasks = tasks;
    const normalizedTasks = normalizeBoardOrders(nextTasks);
    setTasks(normalizedTasks);
    try {
      await reorderResearchBoard({ items: buildReorderPayload(normalizedTasks) });
      await loadWorkbench();
      if (selectedTaskId) {
        await loadTaskDetail(selectedTaskId);
      }
      message.success(successMessage);
    } catch (error) {
      setTasks(previousTasks);
      message.error(error.userMessage || error.message || '更新看板顺序失败');
    } finally {
      setDragState(null);
    }
  };

  const handleDrop = async (targetStatus, targetTaskId = null) => {
    if (!dragState?.taskId) {
      return;
    }
    const nextTasks = moveBoardTask(tasks, dragState.taskId, targetStatus, targetTaskId);
    await commitBoardReorder(nextTasks);
  };

  const renderBoardCard = (task, status) => {
    const isOverTarget = dragState?.overTaskId === task.id && dragState?.overStatus === status;
    const refreshSignal = refreshSignals.byTaskId[task.id];
    return (
      <WorkbenchTaskCard
        task={task}
        status={status}
        isSelected={selectedTaskId === task.id}
        isOverTarget={isOverTarget}
        refreshSignal={refreshSignal}
        onSelect={() => setSelectedTaskId(task.id)}
        onDragStart={() => setDragState({ taskId: task.id, sourceStatus: status, overTaskId: null, overStatus: null })}
        onDragEnd={() => setDragState(null)}
        onDragOver={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setDragState((current) => (current ? { ...current, overTaskId: task.id, overStatus: status } : current));
        }}
        onDrop={(event) => {
          event.preventDefault();
          event.stopPropagation();
          handleDrop(status, task.id);
        }}
      />
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card bordered={false}>
        <Space direction="vertical" size={6}>
          <Tag color="geekblue" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
            Research Workbench V3
          </Tag>
          <Title level={4} style={{ margin: 0 }}>
            研究工作台
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            研究任务现在以多列看板形式推进。你可以直接拖拽任务跨列流转，同时继续保留评论、时间线和快照演进记录。
          </Paragraph>
        </Space>
      </Card>

      <WorkbenchOverviewPanels refreshStats={refreshStats} stats={stats} />

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <WorkbenchBoardSection
            archivedTasks={archivedTasks}
            boardColumns={boardColumns}
            dragState={dragState}
            filters={filters}
            handleDrop={handleDrop}
            handleRestoreArchived={handleRestoreArchived}
            loading={loading}
            renderBoardCard={renderBoardCard}
            saving={saving}
            setDragState={setDragState}
            setFilters={setFilters}
            setSelectedTaskId={setSelectedTaskId}
            setShowArchived={setShowArchived}
            showArchived={showArchived}
            sourceOptions={sourceOptions}
            TYPE_OPTIONS={TYPE_OPTIONS}
            REFRESH_OPTIONS={REFRESH_OPTIONS}
            REASON_OPTIONS={REASON_OPTIONS}
          />
        </Col>

        <Col xs={24} xl={8}>
          <WorkbenchDetailPanel
            commentDraft={commentDraft}
            detailLoading={detailLoading}
            handleAddComment={handleAddComment}
            handleDelete={handleDelete}
            handleDeleteComment={handleDeleteComment}
            handleMetaSave={handleMetaSave}
            handleOpenTask={handleOpenTask}
            handleRestoreArchived={handleRestoreArchived}
            handleStatusUpdate={handleStatusUpdate}
            latestSnapshotComparison={latestSnapshotComparison}
            noteDraft={noteDraft}
            openTaskPriorityLabel={openTaskPriorityLabel}
            saving={saving}
            selectedTask={selectedTask}
            selectedTaskRefreshSignal={selectedTaskRefreshSignal}
            setCommentDraft={setCommentDraft}
            setNoteDraft={setNoteDraft}
            setShowAllTimeline={setShowAllTimeline}
            setTitleDraft={setTitleDraft}
            showAllTimeline={showAllTimeline}
            timeline={timeline}
            timelineItems={timelineItems}
            titleDraft={titleDraft}
          />
        </Col>
      </Row>
    </div>
  );
}

export default ResearchWorkbench;
