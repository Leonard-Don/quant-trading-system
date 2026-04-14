import { useMemo } from 'react';

import {
  buildLatestSnapshotComparison,
  buildOpenTaskPriorityLabel,
  buildOpenTaskPriorityNote,
  buildRefreshPriorityEventPayload,
  buildRefreshPriorityMeta,
  buildTimelineItems,
} from './workbenchSelectors';

export default function useSelectedTaskIntelligence({
  selectedTaskId,
  selectedTask,
  refreshSignals,
  timeline,
  showAllTimeline,
}) {
  const selectedTaskRefreshSignal = selectedTaskId ? refreshSignals.byTaskId[selectedTaskId] : null;

  const openTaskPriorityLabel = useMemo(
    () => buildOpenTaskPriorityLabel(selectedTaskRefreshSignal),
    [selectedTaskRefreshSignal]
  );

  const openTaskPriorityNote = useMemo(
    () => buildOpenTaskPriorityNote(selectedTask, selectedTaskRefreshSignal),
    [selectedTask, selectedTaskRefreshSignal]
  );

  const selectedTaskPriorityMeta = useMemo(
    () => buildRefreshPriorityMeta(selectedTaskRefreshSignal),
    [selectedTaskRefreshSignal]
  );

  const selectedTaskPriorityEventPayload = useMemo(
    () => buildRefreshPriorityEventPayload(selectedTaskRefreshSignal, selectedTaskPriorityMeta),
    [selectedTaskPriorityMeta, selectedTaskRefreshSignal]
  );

  const latestSnapshotComparison = useMemo(
    () => buildLatestSnapshotComparison(selectedTask),
    [selectedTask]
  );

  const timelineItems = useMemo(
    () => buildTimelineItems(
      timeline,
      showAllTimeline,
      selectedTask,
      selectedTaskRefreshSignal,
      selectedTaskPriorityMeta
    ),
    [selectedTask, selectedTaskPriorityMeta, selectedTaskRefreshSignal, showAllTimeline, timeline]
  );

  return {
    selectedTaskRefreshSignal,
    openTaskPriorityLabel,
    openTaskPriorityNote,
    selectedTaskPriorityMeta,
    selectedTaskPriorityEventPayload,
    latestSnapshotComparison,
    timelineItems,
  };
}
