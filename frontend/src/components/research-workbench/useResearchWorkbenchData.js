import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
import { getApiErrorMessage, useSafeMessageApi } from '../../utils/messageApi';
import {
  buildRefreshStats,
  filterWorkbenchTasks,
} from './workbenchSelectors';
import {
  MAIN_STATUSES,
  buildSnapshotViewSummaryOptions,
  sortByBoardOrder,
  STATUS_LABEL,
} from './workbenchUtils';
import useWorkbenchQueueNavigation from './useWorkbenchQueueNavigation';
import useSelectedTaskIntelligence from './useSelectedTaskIntelligence';

export default function useResearchWorkbenchData() {
  const message = useSafeMessageApi();
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
    snapshotView: initialContext.workbenchSnapshotView || '',
    snapshotFingerprint: initialContext.workbenchSnapshotFingerprint || '',
    snapshotSummary: initialContext.workbenchSnapshotSummary || '',
    keyword: initialContext.workbenchKeyword || '',
  });
  const [workbenchQueueMode, setWorkbenchQueueMode] = useState(initialContext.workbenchQueueMode || '');
  const [workbenchQueueAction, setWorkbenchQueueAction] = useState(initialContext.workbenchQueueAction || '');
  const [selectedTaskId, setSelectedTaskId] = useState(initialContext.task || '');
  const [selectedTask, setSelectedTask] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [showAllTimeline, setShowAllTimeline] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [dragState, setDragState] = useState(null);
  const taskDetailRequestRef = useRef(0);
  const pendingContextTaskIdRef = useRef(initialContext.task || '');

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

    const requestId = taskDetailRequestRef.current + 1;
    taskDetailRequestRef.current = requestId;
    setDetailLoading(true);
    try {
      const [taskResponse, timelineResponse] = await Promise.all([
        getResearchTask(taskId),
        getResearchTaskTimeline(taskId),
      ]);
      if (taskDetailRequestRef.current !== requestId) {
        return;
      }
      setSelectedTask(taskResponse.data || null);
      setTimeline(timelineResponse.data || []);
    } catch (error) {
      if (taskDetailRequestRef.current !== requestId) {
        return;
      }
      message.error(getApiErrorMessage(error, '加载任务详情失败'));
      setSelectedTask(null);
      setTimeline([]);
    } finally {
      if (taskDetailRequestRef.current === requestId) {
        setDetailLoading(false);
      }
    }
  }, [message]);

  const loadWorkbench = useCallback(async () => {
    setLoading(true);
    try {
      const [taskResponse, statsResponse, macroResponse, altSnapshotResponse] = await Promise.all([
        getResearchTasks({ limit: 200, view: 'board' }),
        getResearchTaskStats(),
        getMacroOverview(false),
        getAltDataSnapshot(false),
      ]);
      let nextTasks = taskResponse.data || [];
      const contextTaskId = readResearchContext().task || pendingContextTaskIdRef.current || '';
      if (contextTaskId && !nextTasks.some((task) => task.id === contextTaskId)) {
        try {
          const contextTaskResponse = await getResearchTask(contextTaskId);
          const contextTask = contextTaskResponse?.data || null;
          if (contextTask?.id) {
            nextTasks = [contextTask, ...nextTasks.filter((task) => task.id !== contextTask.id)];
          }
        } catch (detailError) {
          // Ignore direct-link enrichment failures here and let the regular detail loader surface errors.
        }
      }
      const hasContextTask = Boolean(contextTaskId) && nextTasks.some((task) => task.id === contextTaskId);
      if (hasContextTask) {
        pendingContextTaskIdRef.current = '';
      }
      setTasks(nextTasks);
      setStats(statsResponse.data || null);
      setLiveOverview(macroResponse || null);
      setLiveSnapshot(altSnapshotResponse || null);
      setSelectedTaskId((current) => {
        if (hasContextTask) {
          return contextTaskId;
        }
        if (current && nextTasks.some((task) => task.id === current)) {
          return current;
        }
        return nextTasks[0]?.id || '';
      });
    } catch (error) {
      message.error(getApiErrorMessage(error, '加载研究工作台失败'));
    } finally {
      setLoading(false);
    }
  }, [message]);

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
        snapshotView: filters.snapshotView,
        snapshotFingerprint: filters.snapshotFingerprint,
        snapshotSummary: filters.snapshotSummary,
        keyword: filters.keyword,
        queueMode: workbenchQueueMode,
        queueAction: workbenchQueueAction,
        taskId: selectedTaskId,
      },
      window.location.search
    );
    window.history.replaceState(null, '', nextUrl);
  }, [
    filters.keyword,
    filters.reason,
    filters.refresh,
    filters.snapshotFingerprint,
    filters.snapshotSummary,
    filters.snapshotView,
    filters.source,
    filters.type,
    selectedTaskId,
    workbenchQueueAction,
    workbenchQueueMode,
  ]);

  useEffect(() => {
    const handlePopState = () => {
      const nextContext = readResearchContext();
      pendingContextTaskIdRef.current = nextContext.task || '';
      setFilters((current) => ({
        ...current,
        type: nextContext.workbenchType || '',
        source: nextContext.workbenchSource || '',
        refresh: nextContext.workbenchRefresh || '',
        reason: nextContext.workbenchReason || '',
        snapshotView: nextContext.workbenchSnapshotView || '',
        snapshotFingerprint: nextContext.workbenchSnapshotFingerprint || '',
        snapshotSummary: nextContext.workbenchSnapshotSummary || '',
        keyword: nextContext.workbenchKeyword || '',
      }));
      setWorkbenchQueueMode(nextContext.workbenchQueueMode || '');
      setWorkbenchQueueAction(nextContext.workbenchQueueAction || '');
      setSelectedTaskId(nextContext.task || '');
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const refreshCurrentTask = useCallback(async () => {
    await loadWorkbench();
    await loadTaskDetail(selectedTaskId);
  }, [loadTaskDetail, loadWorkbench, selectedTaskId]);

  const refreshSignals = useMemo(
    () => buildResearchTaskRefreshSignals({ researchTasks: tasks, overview: liveOverview, snapshot: liveSnapshot }) || {
      prioritized: [],
      byTaskId: {},
    },
    [liveOverview, liveSnapshot, tasks]
  );

  const refreshStats = useMemo(() => buildRefreshStats(refreshSignals, tasks), [refreshSignals, tasks]);
  const snapshotSummaryOptions = useMemo(() => {
    const queuedViews = stats?.snapshot_view_queues;
    return Array.isArray(queuedViews) && queuedViews.length
      ? queuedViews.map((item) => ({
        label: item?.label || item?.value || '',
        value: item?.value || item?.label || '',
        fingerprint: item?.fingerprint || '',
        count: Number(item?.count || 0),
        scopedCount: Number(item?.scopedCount ?? item?.scoped_count ?? 0),
        latestAt: item?.latestAt || item?.latest_at || '',
        typeCounts: item?.typeCounts || item?.type_counts || {},
      }))
      : buildSnapshotViewSummaryOptions(tasks);
  }, [stats, tasks]);

  const filteredTasks = useMemo(
    () => filterWorkbenchTasks(tasks, filters, refreshSignals.byTaskId),
    [filters, refreshSignals.byTaskId, tasks]
  );

  useWorkbenchQueueNavigation({
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
  });

  useEffect(() => {
    if (!filteredTasks.length) {
      if (selectedTaskId && !loading && !pendingContextTaskIdRef.current) {
        setSelectedTaskId('');
      }
      return;
    }
    const queueContext = readResearchContext();
    const queuedTaskId = queueContext.task || '';
    if (workbenchQueueAction === 'next_same_type' && queuedTaskId) {
      const hasQueuedTask = filteredTasks.some((task) => task.id === queuedTaskId);
      const hasSelectedTask = filteredTasks.some((task) => task.id === selectedTaskId);
      if (!hasSelectedTask && hasQueuedTask) {
        setSelectedTaskId(queuedTaskId);
      }
      return;
    }
    const hasSelectedTask = filteredTasks.some((task) => task.id === selectedTaskId);
    if (pendingContextTaskIdRef.current && selectedTaskId === pendingContextTaskIdRef.current && !hasSelectedTask) {
      return;
    }
    if (!selectedTaskId || !hasSelectedTask) {
      setSelectedTaskId(filteredTasks[0].id);
    }
  }, [filteredTasks, loading, selectedTaskId, workbenchQueueAction]);

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

  const taskIntelligence = useSelectedTaskIntelligence({
    selectedTaskId,
    selectedTask,
    refreshSignals,
    timeline,
    showAllTimeline,
  });

  return {
    archivedTasks,
    boardColumns,
    detailLoading,
    dragState,
    filteredTasks,
    filters,
    loadTaskDetail,
    loadWorkbench,
    loading,
    refreshCurrentTask,
    refreshSignals,
    refreshStats,
    snapshotSummaryOptions,
    selectedTask,
    selectedTaskId,
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
    workbenchQueueAction,
    workbenchQueueMode,
    setWorkbenchQueueAction,
    setWorkbenchQueueMode,
    ...taskIntelligence,
  };
}
