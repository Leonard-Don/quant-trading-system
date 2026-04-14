import { useEffect } from 'react';

import { readResearchContext } from '../../utils/researchContext';
import { filterWorkbenchTasks } from './workbenchSelectors';
import { orderWorkbenchQueueTasks } from './workbenchUtils';

const getTaskLaunchMode = (task) => {
  if (!task) return '';
  if (task.type === 'pricing' && task.symbol) return 'pricing';
  if (task.type === 'cross_market' && task.template) return 'cross_market';
  if (task.type === 'macro_mispricing' && task.symbol) return 'cross_market';
  if (task.type === 'trade_thesis') return 'cross_market';
  return '';
};

export default function useWorkbenchQueueNavigation({
  tasks,
  filters,
  filteredTasks,
  refreshSignals,
  selectedTaskId,
  setSelectedTaskId,
  workbenchQueueMode,
  workbenchQueueAction,
  setWorkbenchQueueAction,
  message,
}) {
  useEffect(() => {
    if (workbenchQueueAction !== 'next_same_type' || !workbenchQueueMode || !selectedTaskId || !filteredTasks.length) {
      return;
    }

    const queueContext = readResearchContext();
    const effectiveQueueFilters = {
      type: queueContext.workbenchType || filters.type,
      source: queueContext.workbenchSource || filters.source,
      refresh: queueContext.workbenchRefresh || filters.refresh,
      reason: queueContext.workbenchReason || filters.reason,
      snapshotView: queueContext.workbenchSnapshotView || filters.snapshotView,
      snapshotFingerprint: queueContext.workbenchSnapshotFingerprint || filters.snapshotFingerprint,
      snapshotSummary: queueContext.workbenchSnapshotSummary || filters.snapshotSummary,
      keyword: queueContext.workbenchKeyword || filters.keyword,
    };
    const queueTasks = orderWorkbenchQueueTasks(
      filterWorkbenchTasks(tasks, effectiveQueueFilters, refreshSignals.byTaskId),
      Boolean(effectiveQueueFilters.refresh || effectiveQueueFilters.reason)
    );
    const currentTaskId = queueContext.task || selectedTaskId;

    if (!queueTasks.length || !currentTaskId) {
      setWorkbenchQueueAction('');
      return;
    }

    const currentIndex = queueTasks.findIndex((task) => task.id === currentTaskId);
    if (currentIndex < 0) {
      const fallbackTaskId = queueTasks[0]?.id || '';
      if (fallbackTaskId && selectedTaskId !== fallbackTaskId) {
        setSelectedTaskId(fallbackTaskId);
        return;
      }
      setWorkbenchQueueAction('');
      return;
    }

    const nextTask = queueTasks
      .slice(currentIndex + 1)
      .find((task) => getTaskLaunchMode(task) === workbenchQueueMode);

    if (nextTask?.id) {
      setSelectedTaskId(nextTask.id);
    } else {
      message.info(
        workbenchQueueMode === 'pricing'
          ? '当前已经是 Pricing 执行队列最后一条'
          : '当前已经是跨市场执行队列最后一条'
      );
    }
    setWorkbenchQueueAction('');
  }, [
    filteredTasks.length,
    filters.keyword,
    filters.reason,
    filters.refresh,
    filters.snapshotFingerprint,
    filters.snapshotSummary,
    filters.snapshotView,
    filters.source,
    filters.type,
    refreshSignals.byTaskId,
    selectedTaskId,
    tasks,
    message,
    workbenchQueueAction,
    workbenchQueueMode,
    setSelectedTaskId,
    setWorkbenchQueueAction,
  ]);
}
