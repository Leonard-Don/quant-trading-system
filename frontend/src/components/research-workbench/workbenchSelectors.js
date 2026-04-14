import { buildSnapshotComparison } from './snapshotCompare';
import {
  MAIN_STATUSES,
  extractSnapshotViewContext,
  extractLatestRefreshPriorityEvent,
  sortTasksByRefreshPriority,
  sortByBoardOrder,
  TIMELINE_COLOR,
  formatRefreshPriorityChangeLabel,
  formatTimelineType,
  formatRefreshReasonLabel,
  getRefreshPriorityChangeColor,
} from './workbenchUtils';

export function buildRefreshStats(refreshSignals, tasks = []) {
  const prioritized = refreshSignals.prioritized || [];
  const latestPriorityEvents = (tasks || [])
    .map((task) => extractLatestRefreshPriorityEvent(task))
    .filter(Boolean);
  const snapshotViewContexts = (tasks || []).map((task) => extractSnapshotViewContext(task.snapshot));
  return {
    high: prioritized.filter((item) => item.severity === 'high').length,
    medium: prioritized.filter((item) => item.severity === 'medium').length,
    low: prioritized.filter((item) => item.severity === 'low').length,
    resonance: prioritized.filter((item) => item.resonanceDriven).length,
    biasQualityCore: prioritized.filter((item) => item.biasCompressionShift?.coreLegAffected).length,
    selectionQualityActive: prioritized.filter((item) => item.selectionQualityRunState?.active).length,
    reviewContext: prioritized.filter((item) => item.reviewContextDriven).length,
    structuralDecay: prioritized.filter((item) => item.structuralDecayDriven || item.structuralDecayRadarDriven).length,
    structuralDecayRadar: prioritized.filter((item) => item.structuralDecayRadarDriven).length,
    tradeThesis: prioritized.filter((item) => item.tradeThesisDriven).length,
    peopleLayer: prioritized.filter((item) => item.peopleLayerDriven).length,
    peopleFragility: prioritized.filter((item) => item.peopleLayerDriven).length,
    departmentChaos: prioritized.filter((item) => item.departmentChaosDriven).length,
    policyExecution: prioritized.filter((item) => item.departmentChaosDriven).length,
    selectionQuality: prioritized.filter((item) => item.selectionQualityDriven || item.selectionQualityRunState?.active).length,
    inputReliability: prioritized.filter((item) => item.inputReliabilityDriven).length,
    sourceHealthDegradation: prioritized.filter((item) => item.inputReliabilityDriven || item.policySourceDriven).length,
    policySource: prioritized.filter((item) => item.policySourceDriven).length,
    biasQuality: prioritized.filter((item) => item.biasCompressionDriven).length,
    priorityEscalated: latestPriorityEvents.filter((event) => event?.meta?.change_type === 'escalated').length,
    priorityRelaxed: latestPriorityEvents.filter((event) => event?.meta?.change_type === 'relaxed').length,
    priorityNew: latestPriorityEvents.filter((event) => event?.meta?.change_type === 'new').length,
    priorityUpdated: latestPriorityEvents.filter((event) => event?.meta?.change_type === 'updated').length,
    snapshotViewFiltered: snapshotViewContexts.filter((item) => item.hasFilters || item.summary).length,
    snapshotViewScoped: snapshotViewContexts.filter((item) => item.scopedTaskLabel).length,
  };
}

export function filterWorkbenchTasks(tasks, filters, refreshSignalsByTaskId) {
  const keyword = filters.keyword.trim().toLowerCase();
  const matches = tasks.filter((task) => {
    const signal = refreshSignalsByTaskId[task.id];
    const latestPriorityEvent = extractLatestRefreshPriorityEvent(task);
    const snapshotViewContext = extractSnapshotViewContext(task.snapshot);
    if (filters.type && task.type !== filters.type) return false;
    if (filters.source && task.source !== filters.source) return false;
    if (filters.refresh) {
      const severity = signal?.severity || 'low';
      if (severity !== filters.refresh) return false;
    }
    if (filters.snapshotView === 'filtered' && !(snapshotViewContext.hasFilters || snapshotViewContext.summary)) return false;
    if (filters.snapshotView === 'scoped' && !snapshotViewContext.scopedTaskLabel) return false;
    if (filters.snapshotFingerprint) {
      const fingerprintMatches = snapshotViewContext.fingerprint === filters.snapshotFingerprint;
      const legacySummaryMatches = !snapshotViewContext.fingerprint
        && filters.snapshotSummary
        && snapshotViewContext.summary === filters.snapshotSummary;
      if (!fingerprintMatches && !legacySummaryMatches) return false;
    } else if (filters.snapshotSummary && snapshotViewContext.summary !== filters.snapshotSummary) {
      return false;
    }
    if (filters.reason === 'priority_new' && latestPriorityEvent?.meta?.change_type !== 'new') return false;
    if (filters.reason === 'priority_escalated' && latestPriorityEvent?.meta?.change_type !== 'escalated') return false;
    if (filters.reason === 'priority_relaxed' && latestPriorityEvent?.meta?.change_type !== 'relaxed') return false;
    if (filters.reason === 'priority_updated' && latestPriorityEvent?.meta?.change_type !== 'updated') return false;
    if (filters.reason === 'resonance' && !signal?.resonanceDriven) return false;
    if (filters.reason === 'policy_source' && !signal?.policySourceDriven) return false;
    if (filters.reason === 'input_reliability' && !signal?.inputReliabilityDriven) return false;
    if (filters.reason === 'source_health_degradation' && !(signal?.inputReliabilityDriven || signal?.policySourceDriven)) return false;
    if (filters.reason === 'bias_quality_core' && !signal?.biasCompressionShift?.coreLegAffected) return false;
    if (filters.reason === 'selection_quality_active' && !signal?.selectionQualityRunState?.active) return false;
    if (filters.reason === 'review_context' && !signal?.reviewContextDriven) return false;
    if (filters.reason === 'structural_decay' && !(signal?.structuralDecayDriven || signal?.structuralDecayRadarDriven)) return false;
    if (filters.reason === 'trade_thesis' && !signal?.tradeThesisDriven) return false;
    if ((filters.reason === 'people_layer' || filters.reason === 'people_fragility') && !signal?.peopleLayerDriven) return false;
    if ((filters.reason === 'department_chaos' || filters.reason === 'policy_execution') && !signal?.departmentChaosDriven) return false;
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
      snapshotViewContext.summary,
      snapshotViewContext.scopedTaskLabel,
      snapshotViewContext.note,
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
    : selectedTaskRefreshSignal?.structuralDecayRadarDriven
      ? '优先复核系统衰败雷达'
    : selectedTaskRefreshSignal?.structuralDecayDriven
      ? '优先复核衰败判断'
    : selectedTaskRefreshSignal?.tradeThesisDriven
      ? '优先复核交易 Thesis'
    : selectedTaskRefreshSignal?.peopleLayerDriven
      ? '优先复核人的维度'
    : selectedTaskRefreshSignal?.departmentChaosDriven
      ? '复核部门混乱'
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
        : selectedTaskRefreshSignal?.structuralDecayRadarShift?.actionHint
          ? `${
              selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
            } · ${selectedTaskRefreshSignal.structuralDecayRadarShift.actionHint}`
        : selectedTaskRefreshSignal?.peopleLayerShift?.actionHint
          ? `${
              selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
            } · ${selectedTaskRefreshSignal.peopleLayerShift.actionHint}`
        : selectedTaskRefreshSignal?.structuralDecayShift?.actionHint
          ? `${
              selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
            } · ${selectedTaskRefreshSignal.structuralDecayShift.actionHint}`
        : selectedTaskRefreshSignal?.tradeThesisShift?.actionHint
          ? `${
              selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
            } · ${selectedTaskRefreshSignal.tradeThesisShift.actionHint}`
        : selectedTaskRefreshSignal?.departmentChaosShift?.actionHint
          ? `${
              selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
            } · ${selectedTaskRefreshSignal.departmentChaosShift.actionHint}`
        : selectedTaskRefreshSignal?.inputReliabilityShift?.actionHint
          ? `${
              selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`
          } · ${selectedTaskRefreshSignal.inputReliabilityShift.actionHint}`
        : selectedTask.note || `从研究工作台重新打开 ${selectedTask.title}`;
}

export function buildRefreshPriorityMeta(selectedTaskRefreshSignal) {
  if (!selectedTaskRefreshSignal || selectedTaskRefreshSignal.severity === 'low') {
    return null;
  }

  const reasonKey = selectedTaskRefreshSignal.priorityReason || 'observe';
  const reasonLabel = formatRefreshReasonLabel(reasonKey);
  const urgencyScore = Number(selectedTaskRefreshSignal.urgencyScore || 0);
  const priorityWeight = Number(selectedTaskRefreshSignal.priorityWeight || 0);
  const metrics = [
    selectedTaskRefreshSignal.urgencyScore !== undefined
      ? `紧急度 ${urgencyScore.toFixed(1)}`
      : '',
    selectedTaskRefreshSignal.priorityWeight !== undefined
      ? `排序权重 ${priorityWeight.toFixed(1)}`
      : '',
  ].filter(Boolean).join(' · ');

  const buildMeta = (lead, detail) => ({
    reasonKey,
    reasonLabel,
    alertType: selectedTaskRefreshSignal.severity === 'high' ? 'error' : 'warning',
    severity: selectedTaskRefreshSignal.severity || 'medium',
    urgencyScore,
    priorityWeight,
    lead: lead || selectedTaskRefreshSignal.summary || '当前任务的输入结构已变化，建议优先复核。',
    detail: [metrics, detail].filter(Boolean).join('；'),
  });

  if (selectedTaskRefreshSignal.selectionQualityRunState?.active) {
    const runState = selectedTaskRefreshSignal.selectionQualityRunState;
    return buildMeta(
      '当前保存结果已经处于降级运行状态',
      [
        runState.label ? `当前按 ${runState.label} 强度运行` : '',
        runState.baseScore || runState.effectiveScore
          ? `推荐分 ${Number(runState.baseScore || 0).toFixed(2)}→${Number(runState.effectiveScore || 0).toFixed(2)}`
          : '',
        runState.reason || selectedTaskRefreshSignal.recommendation,
      ].filter(Boolean).join('；')
    );
  }

  if (selectedTaskRefreshSignal.structuralDecayRadarDriven) {
    const shift = selectedTaskRefreshSignal.structuralDecayRadarShift || {};
    return buildMeta(
      shift.lead || '系统级结构衰败雷达正在驱动当前任务的自动排序',
      [
        shift.topSignalSummary ? `雷达焦点 ${shift.topSignalSummary}` : '',
        shift.currentSummary || '',
        shift.actionHint || selectedTaskRefreshSignal.recommendation,
      ].filter(Boolean).join('；')
    );
  }

  if (selectedTaskRefreshSignal.structuralDecayDriven) {
    const shift = selectedTaskRefreshSignal.structuralDecayShift || {};
    return buildMeta(
      shift.lead || '结构性衰败判断较保存时进一步恶化',
      [
        shift.evidenceSummary ? `衰败证据 ${shift.evidenceSummary}` : '',
        shift.currentSummary || '',
        shift.actionHint || selectedTaskRefreshSignal.recommendation,
      ].filter(Boolean).join('；')
    );
  }

  if (selectedTaskRefreshSignal.tradeThesisDriven) {
    const shift = selectedTaskRefreshSignal.tradeThesisShift || {};
    return buildMeta(
      shift.lead || '交易 Thesis 与最新证据出现漂移',
      [
        shift.evidenceSummary ? `Thesis 证据 ${shift.evidenceSummary}` : '',
        shift.currentSummary || '',
        shift.actionHint || selectedTaskRefreshSignal.recommendation,
      ].filter(Boolean).join('；')
    );
  }

  if (selectedTaskRefreshSignal.peopleLayerDriven) {
    const shift = selectedTaskRefreshSignal.peopleLayerShift || {};
    return buildMeta(
      shift.lead || '人的维度较保存时明显走弱',
      [
        shift.evidenceSummary ? `人事证据 ${shift.evidenceSummary}` : '',
        shift.currentSummary || '',
        shift.actionHint || selectedTaskRefreshSignal.recommendation,
      ].filter(Boolean).join('；')
    );
  }

  if (selectedTaskRefreshSignal.departmentChaosDriven) {
    const shift = selectedTaskRefreshSignal.departmentChaosShift || {};
    return buildMeta(
      shift.lead || '部门级政策混乱较保存时明显恶化',
      [
        shift.topDepartmentLabel ? `部门焦点 ${shift.topDepartmentLabel}` : '',
        shift.currentSummary || '',
        shift.actionHint || selectedTaskRefreshSignal.recommendation,
      ].filter(Boolean).join('；')
    );
  }

  if (selectedTaskRefreshSignal.inputReliabilityDriven) {
    const shift = selectedTaskRefreshSignal.inputReliabilityShift || {};
    return buildMeta(
      shift.currentLead || '输入可靠度正在影响当前任务的优先级',
      [
        shift.currentSummary || '',
        shift.actionHint || selectedTaskRefreshSignal.recommendation,
      ].filter(Boolean).join('；')
    );
  }

  return buildMeta(
    `${reasonLabel} 正在驱动当前任务的自动排序`,
    selectedTaskRefreshSignal.recommendation || selectedTaskRefreshSignal.summary || ''
  );
}

export function buildRefreshPriorityEventPayload(selectedTaskRefreshSignal, selectedTaskPriorityMeta) {
  if (!selectedTaskRefreshSignal || !selectedTaskPriorityMeta) {
    return null;
  }

  return {
    reason_key: selectedTaskPriorityMeta.reasonKey,
    reason_label: selectedTaskPriorityMeta.reasonLabel,
    severity: selectedTaskPriorityMeta.severity,
    urgency_score: selectedTaskPriorityMeta.urgencyScore,
    priority_weight: selectedTaskPriorityMeta.priorityWeight,
    lead: selectedTaskPriorityMeta.lead,
    detail: selectedTaskPriorityMeta.detail,
    recommendation: selectedTaskRefreshSignal.recommendation || '',
    summary: selectedTaskRefreshSignal.summary || '',
  };
}

export function buildLatestSnapshotComparison(selectedTask) {
  const history = selectedTask?.snapshot_history || [];
  if (history.length < 2) return null;
  return buildSnapshotComparison(selectedTask?.type, history[1], history[0]);
}

const getSeverityRank = (value) => ({
  low: 1,
  medium: 2,
  high: 3,
}[String(value || '').trim()] || 0);

const buildRefreshPriorityChangeMeta = (eventPayload = null, timeline = []) => {
  if (!eventPayload) {
    return {
      changeType: 'new',
      changeLabel: formatRefreshPriorityChangeLabel('new'),
      changeColor: getRefreshPriorityChangeColor('new'),
    };
  }

  const latestRefreshPriorityEvent = (timeline || []).find((event) => event?.type === 'refresh_priority');
  const previousMeta = latestRefreshPriorityEvent?.meta || {};
  if (!latestRefreshPriorityEvent) {
    return {
      changeType: 'new',
      changeLabel: formatRefreshPriorityChangeLabel('new'),
      changeColor: getRefreshPriorityChangeColor('new'),
    };
  }

  const urgencyDelta = (
    eventPayload.urgency_score !== undefined
    && previousMeta.urgency_score !== undefined
    && previousMeta.urgency_score !== null
  )
    ? Number(eventPayload.urgency_score || 0) - Number(previousMeta.urgency_score || 0)
    : null;
  const priorityWeightDelta = (
    eventPayload.priority_weight !== undefined
    && previousMeta.priority_weight !== undefined
    && previousMeta.priority_weight !== null
  )
    ? Number(eventPayload.priority_weight || 0) - Number(previousMeta.priority_weight || 0)
    : null;
  const severityDelta = getSeverityRank(eventPayload.severity) - getSeverityRank(previousMeta.severity);
  const reasonChanged = (eventPayload.reason_key || '') !== (previousMeta.priority_reason || previousMeta.reason_key || '');

  let changeType = 'updated';
  if (severityDelta > 0 || (urgencyDelta !== null && urgencyDelta > 0.25) || (priorityWeightDelta !== null && priorityWeightDelta > 0.25)) {
    changeType = 'escalated';
  } else if (
    severityDelta < 0
    || (urgencyDelta !== null && urgencyDelta < -0.25)
    || (priorityWeightDelta !== null && priorityWeightDelta < -0.25)
  ) {
    changeType = 'relaxed';
  }

  return {
    changeType,
    changeLabel: formatRefreshPriorityChangeLabel(changeType),
    changeColor: getRefreshPriorityChangeColor(changeType),
    reasonChanged,
    previousReasonLabel: previousMeta.reason_label || '',
    previousSeverity: previousMeta.severity || '',
    urgencyDelta,
    priorityWeightDelta,
    severityDelta,
  };
};

const buildRefreshPriorityTimelineLabel = (reasonLabel, changeType = 'new') => {
  if (changeType === 'escalated') {
    return `系统自动重排升级：${reasonLabel}`;
  }
  if (changeType === 'relaxed') {
    return `系统自动重排缓和：${reasonLabel}`;
  }
  if (changeType === 'updated') {
    return `系统自动重排更新：${reasonLabel}`;
  }
  return `系统自动重排：${reasonLabel}`;
};

const matchesPriorityEvent = (event, eventPayload, detail, label, reasonLabel) => (
  event?.type === 'refresh_priority'
  && event?.detail === detail
  && (event?.meta?.priority_reason || event?.meta?.reason_key || '') === (eventPayload?.reason_key || '')
  && (
    event?.label === label
    || String(event?.label || '').endsWith(`：${reasonLabel}`)
  )
);

export function buildPriorityTimelineEvent(
  selectedTask,
  selectedTaskRefreshSignal,
  selectedTaskPriorityMeta,
  timeline = []
) {
  if (!selectedTask || !selectedTaskRefreshSignal || !selectedTaskPriorityMeta) {
    return null;
  }

  const eventPayload = buildRefreshPriorityEventPayload(selectedTaskRefreshSignal, selectedTaskPriorityMeta);
  if (!eventPayload) {
    return null;
  }

  const changeMeta = buildRefreshPriorityChangeMeta(eventPayload, timeline);
  const detail = [
    selectedTaskPriorityMeta.lead,
    selectedTaskPriorityMeta.detail,
  ].filter(Boolean).join('；');
  const label = buildRefreshPriorityTimelineLabel(selectedTaskPriorityMeta.reasonLabel, changeMeta.changeType);

  if ((timeline || []).some((event) => matchesPriorityEvent(
    event,
    eventPayload,
    detail,
    label,
    selectedTaskPriorityMeta.reasonLabel
  ))) {
    return null;
  }

  return {
    id: `synthetic_refresh_priority_${selectedTask.id}`,
    type: 'refresh_priority',
    label,
    detail,
    created_at: selectedTask.updated_at || selectedTask.snapshot?.saved_at || selectedTask.created_at || '',
    meta: {
      ...eventPayload,
      change_type: changeMeta.changeType,
      change_label: changeMeta.changeLabel,
      synthetic: true,
    },
  };
}

export function buildTimelineItems(
  timeline,
  showAllTimeline,
  selectedTask = null,
  selectedTaskRefreshSignal = null,
  selectedTaskPriorityMeta = null
) {
  const syntheticPriorityEvent = buildPriorityTimelineEvent(
    selectedTask,
    selectedTaskRefreshSignal,
    selectedTaskPriorityMeta,
    timeline
  );
  const sourceTimeline = syntheticPriorityEvent
    ? [syntheticPriorityEvent, ...(timeline || [])]
    : (timeline || []);
  const visible = showAllTimeline ? sourceTimeline : sourceTimeline.slice(0, 8);
  return visible.map((event) => ({
    color: TIMELINE_COLOR[event.type] || 'blue',
    dot: event.type === 'comment_added' ? 'comment' : 'clock',
    children: {
      changeLabel: event?.meta?.change_label || '',
      changeColor: getRefreshPriorityChangeColor(event?.meta?.change_type || 'updated'),
      detail: event.detail,
      label: event.label,
      type: formatTimelineType(event.type),
      createdAt: event.created_at,
      color: TIMELINE_COLOR[event.type] || 'default',
      snapshotViewSummary: event?.meta?.view_context_summary || '',
      snapshotViewFocus: event?.meta?.view_context_scoped_task_label || '',
      snapshotViewNote: event?.meta?.view_context_note || '',
    },
  }));
}

export function buildBoardReorderItems(tasks, previousTasks = [], refreshLookup = {}) {
  const previousById = Object.fromEntries((previousTasks || []).map((task) => [task.id, task]));

  return MAIN_STATUSES.flatMap((status) =>
    (tasks || [])
      .filter((task) => task.status === status)
      .sort(sortByBoardOrder)
      .map((task, index) => {
        const previousTask = previousById[task.id] || null;
        const changed = !previousTask
          || previousTask.status !== status
          || Number(previousTask.board_order || 0) !== index;
        const refreshSignal = refreshLookup[task.id] || null;
        const priorityMeta = changed ? buildRefreshPriorityMeta(refreshSignal) : null;
        const refreshPriorityEvent = changed
          ? buildRefreshPriorityEventPayload(refreshSignal, priorityMeta)
          : null;
        return {
          task_id: task.id,
          status,
          board_order: index,
          ...(refreshPriorityEvent ? { refresh_priority_event: refreshPriorityEvent } : {}),
        };
      })
  );
}
