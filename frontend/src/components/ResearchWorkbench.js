import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Row,
  Space,
  Tag,
  Typography,
} from 'antd';

import {
  addResearchTaskComment,
  bulkUpdateResearchTasks,
  deleteResearchTask,
  deleteResearchTaskComment,
  reorderResearchBoard,
  updateResearchTask,
} from '../services/api';
import {
  buildCrossMarketLink,
  buildWorkbenchLink,
  navigateByResearchAction,
  navigateToAppUrl,
} from '../utils/researchContext';
import { useSafeMessageApi } from '../utils/messageApi';
import { buildMacroMispricingDraft, saveMacroMispricingDraft } from '../utils/macroMispricingDraft';
import WorkbenchBoardSection from './research-workbench/WorkbenchBoardSection';
import WorkbenchDetailPanel from './research-workbench/WorkbenchDetailPanel';
import WorkbenchOverviewPanels from './research-workbench/WorkbenchOverviewPanels';
import WorkbenchTaskCard from './research-workbench/WorkbenchTaskCard';
import useResearchWorkbenchData from './research-workbench/useResearchWorkbenchData';
import {
  buildBoardReorderItems,
  buildOpenTaskPriorityNote,
  buildRefreshPriorityEventPayload,
  buildRefreshPriorityMeta,
} from './research-workbench/workbenchSelectors';
import {
  buildWorkbenchViewSummary,
  moveBoardTask,
  normalizeBoardOrders,
  orderWorkbenchQueueTasks,
  REASON_OPTIONS,
  REFRESH_OPTIONS,
  SNAPSHOT_VIEW_OPTIONS,
  TYPE_OPTIONS,
} from './research-workbench/workbenchUtils';

const { Paragraph, Title } = Typography;

function ResearchWorkbench() {
  const message = useSafeMessageApi();
  const {
    archivedTasks,
    boardColumns,
    detailLoading,
    dragState,
    filteredTasks,
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
    snapshotSummaryOptions,
    selectedTask,
    selectedTaskId,
    selectedTaskRefreshSignal,
    selectedTaskPriorityEventPayload,
    selectedTaskPriorityMeta,
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
  const selectedTaskTitle = selectedTask?.title || tasks.find((task) => task.id === selectedTaskId)?.title || '';
  const workbenchViewSummary = buildWorkbenchViewSummary(filters, {
    reasonOptions: REASON_OPTIONS,
    refreshOptions: REFRESH_OPTIONS,
    snapshotViewOptions: SNAPSHOT_VIEW_OPTIONS,
    typeOptions: TYPE_OPTIONS,
    sourceOptions,
    selectedTaskId,
    selectedTaskTitle,
  });
  const bulkStatusTaskIds = filteredTasks
    .filter((task) => !['complete', 'archived', 'in_progress'].includes(task.status))
    .map((task) => task.id);
  const bulkCommentTaskIds = filteredTasks
    .filter((task) => task.status !== 'archived')
    .map((task) => task.id);
  const orderedQueueTasks = useMemo(
    () => orderWorkbenchQueueTasks(filteredTasks, Boolean(filters.refresh || filters.reason)),
    [filteredTasks, filters.reason, filters.refresh]
  );
  const bulkReviewComment = [
    `批量复盘：${workbenchViewSummary.headline}`,
    workbenchViewSummary.scopedTaskLabel || '',
  ].filter(Boolean).join(' · ');
  const getTaskLaunchMode = (task) => {
    if (!task) {
      return '';
    }
    if (task.type === 'pricing' && task.symbol) {
      return 'pricing';
    }
    if (task.type === 'cross_market' && task.template) {
      return 'cross_market';
    }
    if (task.type === 'macro_mispricing' && task.symbol) {
      return 'cross_market';
    }
    if (task.type === 'trade_thesis') {
      return 'cross_market';
    }
    return '';
  };
  const selectedTaskQueueMeta = useMemo(() => {
    const total = orderedQueueTasks.length;
    if (!total) {
      return {
        total: 0,
        index: -1,
        position: 0,
        label: '',
        currentTask: null,
        previousTask: null,
        nextTask: null,
        hasPrevious: false,
        hasNext: false,
      };
    }

    const currentIndex = orderedQueueTasks.findIndex((task) => task.id === selectedTaskId);
    const index = currentIndex >= 0 ? currentIndex : 0;
    const currentTask = orderedQueueTasks[index] || null;
    const previousTask = index > 0 ? orderedQueueTasks[index - 1] : null;
    const nextTask = index < total - 1 ? orderedQueueTasks[index + 1] : null;

    return {
      total,
      index,
      position: index + 1,
      label: `第 ${index + 1} / ${total} 条`,
      currentTask,
      previousTask,
      nextTask,
      hasPrevious: Boolean(previousTask),
      hasNext: Boolean(nextTask),
    };
  }, [orderedQueueTasks, selectedTaskId]);
  const queueLaunchSummary = useMemo(() => {
    const launchableTasks = orderedQueueTasks.filter((task) => Boolean(getTaskLaunchMode(task)));
    const pricingTasks = launchableTasks.filter((task) => getTaskLaunchMode(task) === 'pricing');
    const crossMarketTasks = launchableTasks.filter((task) => getTaskLaunchMode(task) === 'cross_market');

    return {
      total: orderedQueueTasks.length,
      launchableCount: launchableTasks.length,
      leadTask: launchableTasks[0] || null,
      pricingTask: pricingTasks[0] || null,
      crossMarketTask: crossMarketTasks[0] || null,
      pricingCount: pricingTasks.length,
      crossMarketCount: crossMarketTasks.length,
    };
  }, [orderedQueueTasks]);
  const selectedMatchingQueueMeta = useMemo(() => {
    const currentTask = selectedTaskQueueMeta.currentTask || selectedTask;
    const mode = getTaskLaunchMode(currentTask);

    if (!mode) {
      return {
        mode: '',
        title: '',
        total: 0,
        index: -1,
        label: '',
        currentTask: null,
        previousTask: null,
        nextTask: null,
        hasPrevious: false,
        hasNext: false,
      };
    }

    const matchingTasks = orderedQueueTasks.filter((task) => getTaskLaunchMode(task) === mode);
    const currentIndex = matchingTasks.findIndex((task) => task.id === currentTask?.id);
    const index = currentIndex >= 0 ? currentIndex : 0;
    const queueCurrentTask = matchingTasks[index] || null;
    const previousTask = index > 0 ? matchingTasks[index - 1] : null;
    const nextTask = index < matchingTasks.length - 1 ? matchingTasks[index + 1] : null;

    return {
      mode,
      title: mode === 'pricing' ? 'Pricing 执行队列' : '跨市场执行队列',
      total: matchingTasks.length,
      index,
      label: `第 ${index + 1} / ${matchingTasks.length} 条`,
      currentTask: queueCurrentTask,
      previousTask,
      nextTask,
      hasPrevious: Boolean(previousTask),
      hasNext: Boolean(nextTask),
    };
  }, [orderedQueueTasks, selectedTask, selectedTaskQueueMeta]);

  const withPriorityEvent = (payload = {}, taskId = selectedTask?.id || '') => {
    const taskRefreshSignal = taskId ? refreshSignals.byTaskId[taskId] : null;
    const taskPriorityMeta = taskId === selectedTask?.id
      ? selectedTaskPriorityMeta
      : buildRefreshPriorityMeta(taskRefreshSignal);
    const refreshPriorityEvent = taskId === selectedTask?.id
      ? selectedTaskPriorityEventPayload
      : buildRefreshPriorityEventPayload(taskRefreshSignal, taskPriorityMeta);

    return refreshPriorityEvent
      ? { ...payload, refresh_priority_event: refreshPriorityEvent }
      : payload;
  };

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

  const buildWorkbenchSearchForTask = (taskId = selectedTaskId) => {
    const targetTask = tasks.find((task) => task.id === taskId);
    const nextUrl = buildWorkbenchLink(
      {
        refresh: filters.refresh,
        type: filters.type,
        sourceFilter: filters.source,
        reason: filters.reason,
        snapshotView: filters.snapshotView,
        snapshotFingerprint: filters.snapshotFingerprint,
        snapshotSummary: filters.snapshotSummary,
        keyword: filters.keyword,
        queueMode: getTaskLaunchMode(targetTask),
        taskId,
      },
      window.location.search
    );
    return new URL(nextUrl, window.location.origin).search;
  };

  const openWorkbenchTask = (task, currentSearchOverride = window.location.search) => {
    if (!task) return;

    const taskRefreshSignal = task.id ? refreshSignals.byTaskId[task.id] : null;
    const taskOpenNote = task.id === selectedTask?.id
      ? openTaskPriorityNote
      : buildOpenTaskPriorityNote(task, taskRefreshSignal);

    if (task.type === 'trade_thesis') {
      const payload = task.snapshot?.payload || task.snapshot_history?.[0]?.payload || {};
      const draft = payload.draft || null;
      if (draft?.id && draft?.assets?.length) {
        const draftId = saveMacroMispricingDraft(draft);
        if (draftId) {
          navigateToAppUrl(
            buildCrossMarketLink(
              draft.templateId || task.template || '',
              'research_workbench',
              taskOpenNote,
              currentSearchOverride,
              draftId,
            )
          );
          return;
        }
      }
    }

    if (task.type === 'macro_mispricing' && task.symbol) {
      const payload = task.snapshot?.payload || task.snapshot_history?.[0]?.payload || {};
      const draft = buildMacroMispricingDraft({
        symbol: task.symbol,
        thesis: payload.macro_mispricing_thesis || {},
        structuralDecay: payload.structural_decay || {},
        peopleLayer: payload.people_layer || {},
        source: 'research_workbench',
        note: taskOpenNote,
        sourceTaskId: task.id,
        sourceTaskType: 'macro_mispricing',
      });
      const draftId = saveMacroMispricingDraft(draft);
      if (draftId) {
        navigateToAppUrl(
          buildCrossMarketLink(
            draft.templateId,
            'research_workbench',
            taskOpenNote,
            currentSearchOverride,
            draftId,
          )
        );
        return;
      }
    }

    if (task.type === 'pricing' && task.symbol) {
      navigateByResearchAction({
        target: 'pricing',
        symbol: task.symbol,
        period: task.snapshot?.payload?.period || task.context?.period || '',
        source: 'research_workbench',
        note: taskOpenNote,
      }, currentSearchOverride);
      return;
    }

    if (task.type === 'cross_market' && task.template) {
      navigateByResearchAction({
        target: 'cross-market',
        template: task.template,
        source: 'research_workbench',
        note: taskOpenNote,
      }, currentSearchOverride);
      return;
    }

    navigateByResearchAction({
      target: 'godsEye',
      source: 'research_workbench',
      note: '返回 GodEye 继续筛选研究线索',
    }, currentSearchOverride);
  };

  const handleStatusUpdate = async (status) => {
    if (!selectedTask) return;
    setSaving(true);
    try {
      await updateResearchTask(selectedTask.id, withPriorityEvent({ status }));
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
      await updateResearchTask(selectedTask.id, withPriorityEvent({
        title: titleDraft,
        note: noteDraft,
      }));
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
      await updateResearchTask(taskId, withPriorityEvent({ status: 'new' }, taskId));
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
    openWorkbenchTask(selectedTask, buildWorkbenchSearchForTask(selectedTask.id));
  };

  const handleSelectQueueTask = (direction) => {
    const nextTask = direction < 0 ? selectedTaskQueueMeta.previousTask : selectedTaskQueueMeta.nextTask;
    if (!nextTask?.id) {
      message.info(direction < 0 ? '当前已经是复盘队列第一条' : '当前已经是复盘队列最后一条');
      return;
    }
    setSelectedTaskId(nextTask.id);
  };

  const handleOpenNextTask = () => {
    const nextTask = selectedTaskQueueMeta.nextTask;
    if (!nextTask?.id) {
      message.info('当前已经是复盘队列最后一条');
      return;
    }
    setSelectedTaskId(nextTask.id);
    openWorkbenchTask(nextTask, buildWorkbenchSearchForTask(nextTask.id));
  };

  const handleSelectMatchingQueueTask = (direction) => {
    const nextTask = direction < 0 ? selectedMatchingQueueMeta.previousTask : selectedMatchingQueueMeta.nextTask;
    if (!nextTask?.id) {
      const queueLabel = selectedMatchingQueueMeta.mode === 'pricing' ? 'Pricing 执行队列' : '跨市场执行队列';
      message.info(direction < 0 ? `${queueLabel}已经到第一条` : `${queueLabel}已经到最后一条`);
      return;
    }
    setSelectedTaskId(nextTask.id);
  };

  const handleOpenMatchingQueueNext = () => {
    const nextTask = selectedMatchingQueueMeta.nextTask;
    if (!nextTask?.id) {
      const queueLabel = selectedMatchingQueueMeta.mode === 'pricing' ? 'Pricing 执行队列' : '跨市场执行队列';
      message.info(`${queueLabel}已经到最后一条`);
      return;
    }
    setSelectedTaskId(nextTask.id);
    openWorkbenchTask(nextTask, buildWorkbenchSearchForTask(nextTask.id));
  };

  const handleOpenQueueLead = () => {
    const leadTask = queueLaunchSummary.leadTask;
    if (!leadTask?.id) {
      message.info('当前队列里没有可直接打开的研究任务');
      return;
    }
    setSelectedTaskId(leadTask.id);
    openWorkbenchTask(leadTask, buildWorkbenchSearchForTask(leadTask.id));
  };

  const handleOpenQueueByMode = (mode) => {
    const targetTask = mode === 'pricing'
      ? queueLaunchSummary.pricingTask
      : queueLaunchSummary.crossMarketTask;
    if (!targetTask?.id) {
      message.info(mode === 'pricing' ? '当前队列里没有可打开的 Pricing 任务' : '当前队列里没有可打开的跨市场任务');
      return;
    }
    setSelectedTaskId(targetTask.id);
    openWorkbenchTask(targetTask, buildWorkbenchSearchForTask(targetTask.id));
  };

  const commitBoardReorder = async (nextTasks, successMessage = '看板顺序已更新') => {
    const previousTasks = tasks;
    const normalizedTasks = normalizeBoardOrders(nextTasks);
    setTasks(normalizedTasks);
    try {
      await reorderResearchBoard({
        items: buildBoardReorderItems(normalizedTasks, previousTasks, refreshSignals.byTaskId),
      });
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

  const handleCopyWorkbenchViewLink = async () => {
    if (!navigator?.clipboard?.writeText) {
      message.warning('当前环境不支持复制工作台链接');
      return;
    }

    const relativeUrl = buildWorkbenchLink(
      {
        refresh: filters.refresh,
        type: filters.type,
        sourceFilter: filters.source,
        reason: filters.reason,
        snapshotView: filters.snapshotView,
        snapshotFingerprint: filters.snapshotFingerprint,
        snapshotSummary: filters.snapshotSummary,
        keyword: filters.keyword,
        taskId: selectedTaskId,
      },
      window.location.search
    );
    const absoluteUrl = new URL(relativeUrl, window.location.origin).toString();

    try {
      await navigator.clipboard.writeText(absoluteUrl);
      message.success('当前工作台视图链接已复制');
    } catch (error) {
      message.error('复制工作台链接失败，请稍后重试');
    }
  };

  const handleBulkQueueCurrentView = async () => {
    if (!workbenchViewSummary.hasActiveFilters) {
      message.warning('请先在筛选视图下操作，避免误改全量任务');
      return;
    }
    if (!bulkStatusTaskIds.length) {
      message.info('当前视图里没有可推进到进行中的任务');
      return;
    }

    setSaving(true);
    try {
      const response = await bulkUpdateResearchTasks({
        task_ids: bulkStatusTaskIds,
        status: 'in_progress',
      });
      message.success(`已将 ${response?.total || bulkStatusTaskIds.length} 个任务推进到进行中`);
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '批量推进任务失败');
    } finally {
      setSaving(false);
    }
  };

  const handleBulkCommentCurrentView = async () => {
    if (!workbenchViewSummary.hasActiveFilters) {
      message.warning('请先在筛选视图下操作，避免误改全量任务');
      return;
    }
    if (!bulkCommentTaskIds.length) {
      message.info('当前视图里没有可写入复盘评论的任务');
      return;
    }

    setSaving(true);
    try {
      const response = await bulkUpdateResearchTasks({
        task_ids: bulkCommentTaskIds,
        comment: bulkReviewComment,
        author: 'local',
      });
      message.success(`已为 ${response?.total || bulkCommentTaskIds.length} 个任务写入复盘评论`);
      await refreshCurrentTask();
    } catch (error) {
      message.error(error.userMessage || error.message || '批量写入复盘评论失败');
    } finally {
      setSaving(false);
    }
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
      <Card variant="borderless">
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
          <Space wrap>
            <Tag color={workbenchViewSummary.hasActiveFilters ? 'blue' : 'default'}>
              当前共享视图
            </Tag>
            <Typography.Text strong>{workbenchViewSummary.headline}</Typography.Text>
            {workbenchViewSummary.scopedTaskLabel ? (
              <Tag color="processing">{workbenchViewSummary.scopedTaskLabel}</Tag>
            ) : null}
            <Button size="small" type="link" onClick={handleCopyWorkbenchViewLink}>
              复制当前视图链接
            </Button>
            <Button
              size="small"
              onClick={handleBulkQueueCurrentView}
              disabled={!workbenchViewSummary.hasActiveFilters || !bulkStatusTaskIds.length || saving}
            >
              批量推进到进行中 {bulkStatusTaskIds.length ? `(${bulkStatusTaskIds.length})` : ''}
            </Button>
            <Button
              size="small"
              onClick={handleBulkCommentCurrentView}
              disabled={!workbenchViewSummary.hasActiveFilters || !bulkCommentTaskIds.length || saving}
            >
              批量写入复盘评论 {bulkCommentTaskIds.length ? `(${bulkCommentTaskIds.length})` : ''}
            </Button>
          </Space>
          <Typography.Text type="secondary">{workbenchViewSummary.note}</Typography.Text>
        </Space>
      </Card>

      <WorkbenchOverviewPanels
        filters={filters}
        onOpenQueueCrossMarket={() => handleOpenQueueByMode('cross_market')}
        onOpenQueueLead={handleOpenQueueLead}
        onOpenQueuePricing={() => handleOpenQueueByMode('pricing')}
        onCopyViewLink={handleCopyWorkbenchViewLink}
        queueLaunchSummary={queueLaunchSummary}
        refreshStats={refreshStats}
        setFilters={setFilters}
        sourceOptions={sourceOptions}
        stats={stats}
        snapshotSummaryOptions={snapshotSummaryOptions}
        TYPE_OPTIONS={TYPE_OPTIONS}
        REFRESH_OPTIONS={REFRESH_OPTIONS}
        SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
        REASON_OPTIONS={REASON_OPTIONS}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
        <WorkbenchBoardSection
          archivedTasks={archivedTasks}
          boardColumns={boardColumns}
          dragState={dragState}
          filters={filters}
            onCopyViewLink={handleCopyWorkbenchViewLink}
            handleDrop={handleDrop}
          handleRestoreArchived={handleRestoreArchived}
          loading={loading}
          renderBoardCard={renderBoardCard}
          refreshStats={refreshStats}
          saving={saving}
          setDragState={setDragState}
          setFilters={setFilters}
            setSelectedTaskId={setSelectedTaskId}
          setShowArchived={setShowArchived}
          showArchived={showArchived}
          snapshotSummaryOptions={snapshotSummaryOptions}
          sourceOptions={sourceOptions}
          TYPE_OPTIONS={TYPE_OPTIONS}
            REFRESH_OPTIONS={REFRESH_OPTIONS}
            SNAPSHOT_VIEW_OPTIONS={SNAPSHOT_VIEW_OPTIONS}
            REASON_OPTIONS={REASON_OPTIONS}
          />
        </Col>

        <Col xs={24} xl={8}>
          <WorkbenchDetailPanel
            commentDraft={commentDraft}
            detailLoading={detailLoading}
            handleAddComment={handleAddComment}
            handleCopyViewLink={handleCopyWorkbenchViewLink}
            handleDelete={handleDelete}
            handleDeleteComment={handleDeleteComment}
            handleMetaSave={handleMetaSave}
            handleOpenMatchingQueueNext={handleOpenMatchingQueueNext}
            handleOpenNextTask={handleOpenNextTask}
            handleOpenTask={handleOpenTask}
            handleRestoreArchived={handleRestoreArchived}
            handleSelectMatchingQueueNext={() => handleSelectMatchingQueueTask(1)}
            handleSelectMatchingQueuePrevious={() => handleSelectMatchingQueueTask(-1)}
            handleSelectQueueNext={() => handleSelectQueueTask(1)}
            handleSelectQueuePrevious={() => handleSelectQueueTask(-1)}
            handleStatusUpdate={handleStatusUpdate}
            latestSnapshotComparison={latestSnapshotComparison}
            noteDraft={noteDraft}
            openTaskPriorityLabel={openTaskPriorityLabel}
            selectedMatchingQueueMeta={selectedMatchingQueueMeta}
            selectedTaskPriorityMeta={selectedTaskPriorityMeta}
            selectedTaskQueueMeta={selectedTaskQueueMeta}
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
            workbenchViewSummary={workbenchViewSummary}
          />
        </Col>
      </Row>
    </div>
  );
}

export default ResearchWorkbench;
