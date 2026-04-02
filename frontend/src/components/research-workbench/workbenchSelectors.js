import { buildSnapshotComparison } from './snapshotCompare';
import {
  sortTasksByRefreshPriority,
  TIMELINE_COLOR,
  formatTimelineType,
} from './workbenchUtils';

export function buildRefreshStats(refreshSignals) {
  const prioritized = refreshSignals.prioritized || [];
  return {
    high: prioritized.filter((item) => item.severity === 'high').length,
    medium: prioritized.filter((item) => item.severity === 'medium').length,
    low: prioritized.filter((item) => item.severity === 'low').length,
    resonance: prioritized.filter((item) => item.resonanceDriven).length,
    biasQualityCore: prioritized.filter((item) => item.biasCompressionShift?.coreLegAffected).length,
    selectionQualityActive: prioritized.filter((item) => item.selectionQualityRunState?.active).length,
    reviewContext: prioritized.filter((item) => item.reviewContextDriven).length,
    selectionQuality: prioritized.filter((item) => item.selectionQualityDriven || item.selectionQualityRunState?.active).length,
    inputReliability: prioritized.filter((item) => item.inputReliabilityDriven).length,
    policySource: prioritized.filter((item) => item.policySourceDriven).length,
    biasQuality: prioritized.filter((item) => item.biasCompressionDriven).length,
  };
}

export function filterWorkbenchTasks(tasks, filters, refreshSignalsByTaskId) {
  const keyword = filters.keyword.trim().toLowerCase();
  const matches = tasks.filter((task) => {
    const signal = refreshSignalsByTaskId[task.id];
    if (filters.type && task.type !== filters.type) return false;
    if (filters.source && task.source !== filters.source) return false;
    if (filters.refresh) {
      const severity = signal?.severity || 'low';
      if (severity !== filters.refresh) return false;
    }
    if (filters.reason === 'resonance' && !signal?.resonanceDriven) return false;
    if (filters.reason === 'policy_source' && !signal?.policySourceDriven) return false;
    if (filters.reason === 'input_reliability' && !signal?.inputReliabilityDriven) return false;
    if (filters.reason === 'bias_quality_core' && !signal?.biasCompressionShift?.coreLegAffected) return false;
    if (filters.reason === 'selection_quality_active' && !signal?.selectionQualityRunState?.active) return false;
    if (filters.reason === 'review_context' && !signal?.reviewContextDriven) return false;
    if (filters.reason === 'selection_quality' && !(signal?.selectionQualityDriven || signal?.selectionQualityRunState?.active)) {
      return false;
    }
    if (filters.reason === 'bias_quality' && !signal?.biasCompressionDriven) return false;
    if (!keyword) return true;
    const haystack = [
      task.title,
      task.symbol,
      task.template,
      task.note,
      task.snapshot?.headline,
      task.snapshot?.summary,
    ].join(' ').toLowerCase();
    return haystack.includes(keyword);
  });

  return sortTasksByRefreshPriority(
    matches,
    refreshSignalsByTaskId,
    Boolean(filters.refresh || filters.reason)
  );
}

export function buildOpenTaskPriorityLabel(selectedTaskRefreshSignal) {
  return selectedTaskRefreshSignal?.selectionQualityRunState?.active
    ? '优先重看研究页'
    : selectedTaskRefreshSignal?.reviewContextShift?.enteredReview
      ? '按复核结果重看'
    : selectedTaskRefreshSignal?.reviewContextShift?.exitedReview
      ? '确认恢复普通结果'
    : selectedTaskRefreshSignal?.reviewContextDriven
      ? '重新确认结果语境'
    : selectedTaskRefreshSignal?.inputReliabilityShift?.enteredFragile
      ? '先复核输入可靠度'
    : selectedTaskRefreshSignal?.inputReliabilityShift?.recoveredRobust
      ? '确认恢复正常强度'
    : selectedTaskRefreshSignal?.inputReliabilityDriven
      ? '重新确认输入质量'
    : '重新打开研究页';
}

export function buildOpenTaskPriorityNote(selectedTask, selectedTaskRefreshSignal) {
  if (!selectedTask) return '';
  return selectedTaskRefreshSignal?.selectionQualityRunState?.active
    ? `${
        selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
      } · 当前结果已按 ${selectedTaskRefreshSignal.selectionQualityRunState.label} 强度运行，建议优先重看`
    : selectedTaskRefreshSignal?.reviewContextShift?.actionHint
      ? `${
          selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
        } · ${selectedTaskRefreshSignal.reviewContextShift.actionHint}`
      : selectedTaskRefreshSignal?.inputReliabilityShift?.actionHint
        ? `${
            selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
          } · ${selectedTaskRefreshSignal.inputReliabilityShift.actionHint}`
        : selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`;
}

export function buildLatestSnapshotComparison(selectedTask) {
  const history = selectedTask?.snapshot_history || [];
  if (history.length < 2) return null;
  return buildSnapshotComparison(selectedTask?.type, history[1], history[0]);
}

export function buildTimelineItems(timeline, showAllTimeline) {
  const visible = showAllTimeline ? timeline : timeline.slice(0, 8);
  return visible.map((event) => ({
    color: TIMELINE_COLOR[event.type] || 'blue',
    dot: event.type === 'comment_added' ? 'comment' : 'clock',
    children: {
      detail: event.detail,
      label: event.label,
      type: formatTimelineType(event.type),
      createdAt: event.created_at,
      color: TIMELINE_COLOR[event.type] || 'default',
    },
  }));
}
