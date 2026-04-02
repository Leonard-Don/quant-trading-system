import { useCallback, useEffect, useMemo, useState } from 'react';
import { message } from 'antd';

import {
  getAltDataSnapshot,
  getMacroOverview,
  getResearchTask,
  getResearchTaskStats,
  getResearchTasks,
  getResearchTaskTimeline,
} from '../../services/api';
import {
  buildWorkbenchLink,
  formatResearchSource,
  readResearchContext,
} from '../../utils/researchContext';
import { buildResearchTaskRefreshSignals } from '../../utils/researchTaskSignals';
import {
  buildLatestSnapshotComparison,
  buildOpenTaskPriorityLabel,
  buildOpenTaskPriorityNote,
  buildRefreshStats,
  buildTimelineItems,
  filterWorkbenchTasks,
} from './workbenchSelectors';
import {
  MAIN_STATUSES,
  sortByBoardOrder,
  STATUS_LABEL,
} from './workbenchUtils';

export default function useResearchWorkbenchData() {
  const initialContext = readResearchContext();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState(null);
  const [liveOverview, setLiveOverview] = useState(null);
  const [liveSnapshot, setLiveSnapshot] = useState(null);
  const [filters, setFilters] = useState({
    type: initialContext.workbenchType || '',
    source: initialContext.workbenchSource || '',
    refresh: initialContext.workbenchRefresh || '',
    reason: initialContext.workbenchReason || '',
    keyword: '',
  });
  const [selectedTaskId, setSelectedTaskId] = useState(initialContext.task || '');
  const [selectedTask, setSelectedTask] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [showAllTimeline, setShowAllTimeline] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [dragState, setDragState] = useState(null);

  const sourceOptions = useMemo(() => {
    const uniqueSources = Array.from(new Set(tasks.map((task) => task.source).filter(Boolean)));
    return [
      { label: '全部来源', value: '' },
      ...uniqueSources.map((source) => ({
        label: formatResearchSource(source),
        value: source,
      })),
    ];
  }, [tasks]);

  const loadTaskDetail = useCallback(async (taskId) => {
    if (!taskId) {
      setSelectedTask(null);
      setTimeline([]);
      return;
    }

    setDetailLoading(true);
    try {
      const [taskResponse, timelineResponse] = await Promise.all([
        getResearchTask(taskId),
        getResearchTaskTimeline(taskId),
      ]);
      setSelectedTask(taskResponse.data || null);
      setTimeline(timelineResponse.data || []);
    } catch (error) {
      message.error(error.userMessage || error.message || '加载任务详情失败');
      setSelectedTask(null);
      setTimeline([]);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    try {
      const [taskResponse, statsResponse, macroResponse, altSnapshotResponse] = await Promise.all([
        getResearchTasks({ limit: 200, view: 'board' }),
        getResearchTaskStats(),
        getMacroOverview(false),
        getAltDataSnapshot(false),
      ]);
      const nextTasks = taskResponse.data || [];
      setTasks(nextTasks);
      setStats(statsResponse.data || null);
      setLiveOverview(macroResponse || null);
      setLiveSnapshot(altSnapshotResponse || null);
      setSelectedTaskId((current) => {
        if (current && nextTasks.some((task) => task.id === current)) {
          return current;
        }
        return nextTasks[0]?.id || '';
      });
    } catch (error) {
      message.error(error.userMessage || error.message || '加载研究工作台失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkbench();
  }, [loadWorkbench]);

  useEffect(() => {
    loadTaskDetail(selectedTaskId);
  }, [loadTaskDetail, selectedTaskId]);

  useEffect(() => {
    const nextUrl = buildWorkbenchLink(
      {
        refresh: filters.refresh,
        type: filters.type,
        sourceFilter: filters.source,
        reason: filters.reason,
        taskId: selectedTaskId,
      },
      window.location.search
    );
    window.history.replaceState(null, '', nextUrl);
  }, [filters.reason, filters.refresh, filters.source, filters.type, selectedTaskId]);

  const refreshCurrentTask = useCallback(async () => {
    await loadWorkbench();
    await loadTaskDetail(selectedTaskId);
  }, [loadTaskDetail, loadWorkbench, selectedTaskId]);

  const refreshSignals = useMemo(
    () => buildResearchTaskRefreshSignals({ researchTasks: tasks, overview: liveOverview, snapshot: liveSnapshot }),
    [liveOverview, liveSnapshot, tasks]
  );

  const refreshStats = useMemo(() => buildRefreshStats(refreshSignals), [refreshSignals]);

  const filteredTasks = useMemo(
    () => filterWorkbenchTasks(tasks, filters, refreshSignals.byTaskId),
    [filters, refreshSignals.byTaskId, tasks]
  );

  useEffect(() => {
    if (!filteredTasks.length) {
      if (selectedTaskId) setSelectedTaskId('');
      return;
    }
    const hasSelectedTask = filteredTasks.some((task) => task.id === selectedTaskId);
    if (!selectedTaskId || !hasSelectedTask) {
      setSelectedTaskId(filteredTasks[0].id);
    }
  }, [filteredTasks, selectedTaskId]);

  const boardColumns = useMemo(
    () =>
      MAIN_STATUSES.map((status) => ({
        status,
        title: STATUS_LABEL[status],
        tasks: filteredTasks.filter((task) => task.status === status).sort(sortByBoardOrder),
      })),
    [filteredTasks]
  );

  const archivedTasks = useMemo(
    () =>
      filteredTasks
        .filter((task) => task.status === 'archived')
        .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || ''))),
    [filteredTasks]
  );

  const selectedTaskRefreshSignal = selectedTaskId ? refreshSignals.byTaskId[selectedTaskId] : null;
  const openTaskPriorityLabel = useMemo(
    () => buildOpenTaskPriorityLabel(selectedTaskRefreshSignal),
    [selectedTaskRefreshSignal]
  );
  const openTaskPriorityNote = useMemo(
    () => buildOpenTaskPriorityNote(selectedTask, selectedTaskRefreshSignal),
    [selectedTask, selectedTaskRefreshSignal]
  );
  const latestSnapshotComparison = useMemo(
    () => buildLatestSnapshotComparison(selectedTask),
    [selectedTask]
  );
  const timelineItems = useMemo(
    () => buildTimelineItems(timeline, showAllTimeline),
    [showAllTimeline, timeline]
  );

  return {
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
  };
}
