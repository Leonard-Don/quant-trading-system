const formatFactorName = (name = '') => {
  const mapping = {
    bureaucratic_friction: '官僚摩擦',
    tech_dilution: '技术稀释',
    baseload_mismatch: '基荷错配',
  };
  return mapping[name] || name.replace(/_/g, ' ');
};

const extractTaskPayload = (task = {}) =>
  task?.snapshot?.payload
  || task?.snapshot_history?.[0]?.payload
  || {};

const extractTaskResearchInput = (task = {}) =>
  extractTaskPayload(task)?.research_input || {};

const extractTaskTemplateMeta = (task = {}) =>
  extractTaskPayload(task)?.template_meta || {};

const BIAS_QUALITY_MAP = {
  fragile: { label: 'compressed', scale: 0.55 },
  watch: { label: 'cautious', scale: 0.78 },
  healthy: { label: 'full', scale: 1 },
  unknown: { label: 'full', scale: 1 },
};

const extractCompressedLeader = (allocationOverlay = {}) =>
  (allocationOverlay.rows || [])
    .slice()
    .sort((left, right) => Math.abs(Number(right?.compression_delta || 0)) - Math.abs(Number(left?.compression_delta || 0)))
    .find((item) => Math.abs(Number(item?.compression_delta || 0)) >= 0.005) || null;

const summarizeMacroShift = (macroInput = {}, overview = {}) => {
  const currentScore = Number(overview?.macro_score || 0);
  const savedScore = Number(macroInput?.macro_score || 0);
  const scoreGap = Number((currentScore - savedScore).toFixed(3));
  const currentSignal = Number(overview?.macro_signal ?? 0);
  const savedSignal = Number(macroInput?.macro_signal ?? 0);
  const signalShift = currentSignal !== savedSignal;

  return {
    currentScore,
    savedScore,
    scoreGap,
    currentSignal,
    savedSignal,
    signalShift,
  };
};

const summarizeResonanceShift = (macroInput = {}, overview = {}) => {
  const savedResonance = macroInput?.resonance || {};
  const currentResonance = overview?.resonance_summary || {};
  const savedLabel = savedResonance.label || 'mixed';
  const currentLabel = currentResonance.label || 'mixed';
  const labelChanged = savedLabel !== currentLabel;
  const savedFactors = new Set([
    ...(savedResonance.positive_cluster || []),
    ...(savedResonance.negative_cluster || []),
    ...(savedResonance.weakening || []),
    ...(savedResonance.precursor || []),
    ...(savedResonance.reversed_factors || []),
  ]);
  const currentFactors = new Set([
    ...(currentResonance.positive_cluster || []),
    ...(currentResonance.negative_cluster || []),
    ...(currentResonance.weakening || []),
    ...(currentResonance.precursor || []),
    ...(currentResonance.reversed_factors || []),
  ]);
  const addedFactors = Array.from(currentFactors).filter((item) => !savedFactors.has(item));
  const removedFactors = Array.from(savedFactors).filter((item) => !currentFactors.has(item));

  return {
    savedLabel,
    currentLabel,
    labelChanged,
    addedFactors,
    removedFactors,
    currentReason: currentResonance.reason || '',
  };
};

const summarizePolicySourceShift = (macroInput = {}, overview = {}) => {
  const savedHealth = macroInput?.policy_source_health || {};
  const currentHealth = overview?.evidence_summary?.policy_source_health_summary || {};
  const severityRank = { unknown: 0, healthy: 1, watch: 2, fragile: 3 };
  const savedLabel = savedHealth.label || 'unknown';
  const currentLabel = currentHealth.label || 'unknown';
  const savedRank = severityRank[savedLabel] || 0;
  const currentRank = severityRank[currentLabel] || 0;
  const worsening = currentRank > savedRank;
  const improving = currentRank < savedRank;
  const labelChanged = currentLabel !== savedLabel;
  const savedFragile = new Set(savedHealth.fragile_sources || []);
  const currentFragile = new Set(currentHealth.fragile_sources || []);
  const addedFragileSources = Array.from(currentFragile).filter((item) => !savedFragile.has(item));
  const removedFragileSources = Array.from(savedFragile).filter((item) => !currentFragile.has(item));
  const fullTextRatioGap = Number(
    (
      Number(currentHealth.avg_full_text_ratio || 0)
      - Number(savedHealth.avg_full_text_ratio || 0)
    ).toFixed(3)
  );

  return {
    savedLabel,
    currentLabel,
    labelChanged,
    worsening,
    improving,
    addedFragileSources,
    removedFragileSources,
    fullTextRatioGap,
    currentReason: currentHealth.reason || '',
  };
};

const summarizeBiasCompressionShift = (templateMeta = {}, overview = {}, allocationOverlay = {}) => {
  const currentHealth = overview?.evidence_summary?.policy_source_health_summary || {};
  const currentHealthLabel = currentHealth.label || 'unknown';
  const currentBiasMeta = BIAS_QUALITY_MAP[currentHealthLabel] || BIAS_QUALITY_MAP.unknown;
  const savedLabel = templateMeta?.bias_quality_label || 'full';
  const savedScale = Number(templateMeta?.bias_scale ?? 1);
  const currentLabel = currentBiasMeta.label || 'full';
  const currentScale = Number(currentBiasMeta.scale ?? 1);
  const scaleGap = Number((currentScale - savedScale).toFixed(3));
  const labelChanged = savedLabel !== currentLabel;
  const compressed = currentScale < savedScale - 0.05;
  const expanded = currentScale > savedScale + 0.05;
  const compressedLeader = extractCompressedLeader(allocationOverlay);
  const coreLegSymbols = new Set([
    ...(templateMeta?.core_legs || []).map((item) => String(item?.symbol || '').toUpperCase()).filter(Boolean),
  ]);
  const themeCoreText = String(templateMeta?.theme_core || '').toUpperCase();
  const topCompressedSymbol = String(compressedLeader?.symbol || '').toUpperCase();
  const coreLegAffected = Boolean(
    topCompressedSymbol
    && (coreLegSymbols.has(topCompressedSymbol) || themeCoreText.includes(topCompressedSymbol))
  );

  return {
    savedLabel,
    currentLabel,
    savedScale,
    currentScale,
    scaleGap,
    labelChanged,
    compressed,
    expanded,
    topCompressedAsset: compressedLeader
      ? `${compressedLeader.symbol} ${(Math.abs(Number(compressedLeader.compression_delta || 0)) * 100).toFixed(2)}pp`
      : '',
    topCompressedSymbol,
    coreLegAffected,
    currentReason: currentHealth.reason || templateMeta?.bias_quality_reason || '',
  };
};

const summarizeSelectionQualityShift = (templateMeta = {}, biasCompressionShift = {}) => {
  const severityRank = {
    original: 0,
    softened: 1,
    auto_downgraded: 2,
  };
  const savedSelectionQuality = templateMeta?.selection_quality || {};
  const savedLabel = savedSelectionQuality.label
    || (templateMeta?.ranking_penalty > 0 ? 'softened' : 'original');
  const currentLabel = biasCompressionShift?.coreLegAffected
    ? 'auto_downgraded'
    : (biasCompressionShift?.compressed || biasCompressionShift?.labelChanged)
      ? 'softened'
      : 'original';
  const savedPenalty = Number(templateMeta?.ranking_penalty || 0);
  const currentPenalty = currentLabel === 'auto_downgraded'
    ? 0.45
    : currentLabel === 'softened'
      ? 0.2
      : 0;
  const labelChanged = savedLabel !== currentLabel;
  const penaltyGap = Number((currentPenalty - savedPenalty).toFixed(3));
  const worsening = (severityRank[currentLabel] || 0) > (severityRank[savedLabel] || 0);
  const improving = (severityRank[currentLabel] || 0) < (severityRank[savedLabel] || 0);

  return {
    savedLabel,
    currentLabel,
    savedPenalty,
    currentPenalty,
    penaltyGap,
    labelChanged,
    worsening,
    improving,
    currentReason: biasCompressionShift?.currentReason || savedSelectionQuality.reason || '',
  };
};

const summarizeSelectionQualityRunState = (templateMeta = {}, allocationOverlay = {}) => {
  const selectionQuality = allocationOverlay?.selection_quality || templateMeta?.selection_quality || {};
  const label = selectionQuality.label || 'original';
  const baseScore = Number(
    selectionQuality.base_recommendation_score
    ?? templateMeta?.base_recommendation_score
    ?? 0
  );
  const effectiveScore = Number(
    selectionQuality.effective_recommendation_score
    ?? templateMeta?.recommendation_score
    ?? templateMeta?.base_recommendation_score
    ?? 0
  );
  const baseTier = selectionQuality.base_recommendation_tier
    || templateMeta?.base_recommendation_tier
    || '';
  const effectiveTier = selectionQuality.effective_recommendation_tier
    || templateMeta?.recommendation_tier
    || baseTier;
  const rankingPenalty = Number(
    selectionQuality.ranking_penalty
    ?? templateMeta?.ranking_penalty
    ?? 0
  );

  return {
    label,
    active: label !== 'original' || rankingPenalty > 0.01,
    baseScore,
    effectiveScore,
    baseTier,
    effectiveTier,
    rankingPenalty,
    reason: selectionQuality.reason
      || templateMeta?.selection_quality?.reason
      || templateMeta?.ranking_penalty_reason
      || '',
  };
};

const getSnapshotSelectionQualityLabel = (snapshot = {}) => {
  const payload = snapshot?.payload || {};
  const label =
    payload?.allocation_overlay?.selection_quality?.label
    || payload?.template_meta?.selection_quality?.label
    || '';
  if (label) {
    return label;
  }
  return String(snapshot?.headline || '').includes('复核型结果') ? 'review_result' : 'original';
};

const summarizeReviewContextShift = (task = {}) => {
  const history = task?.snapshot_history || [];
  if (history.length < 2) {
    return {
      changed: false,
      enteredReview: false,
      exitedReview: false,
      savedLabel: '',
      currentLabel: '',
      lead: '',
    };
  }

  const currentLabel = getSnapshotSelectionQualityLabel(history[0]);
  const savedLabel = getSnapshotSelectionQualityLabel(history[1]);
  const currentIsReview = currentLabel !== 'original';
  const savedIsReview = savedLabel !== 'original';
  const changed = currentIsReview !== savedIsReview || currentLabel !== savedLabel;
  const enteredReview = !savedIsReview && currentIsReview;
  const exitedReview = savedIsReview && !currentIsReview;

  let lead = '';
  if (enteredReview) {
    lead = '最近两版已从普通结果切到复核型结果';
  } else if (exitedReview) {
    lead = '最近两版已从复核型结果回到普通结果';
  } else if (changed && currentIsReview) {
    lead = `最近两版复核强度已从 ${savedLabel} 切到 ${currentLabel}`;
  } else if (changed) {
    lead = `最近两版结果语境已从 ${savedLabel} 切到 ${currentLabel}`;
  }

  return {
    changed,
    enteredReview,
    exitedReview,
    savedLabel,
    currentLabel,
    lead,
  };
};

const summarizeAltShifts = (altInput = {}, snapshot = {}) => {
  const currentSummary = snapshot?.category_summary || {};
  const savedCategories = altInput?.top_categories || [];
  const changedCategories = savedCategories
    .map((item) => {
      const current = currentSummary[item.category];
      if (!current) {
        return null;
      }

      const previousDelta = Number(item.delta_score || 0);
      const currentDelta = Number(current.delta_score || 0);
      const deltaGap = Number((currentDelta - previousDelta).toFixed(3));
      const previousMomentum = item.momentum || 'stable';
      const currentMomentum = current.momentum || 'stable';
      const momentumShift = previousMomentum !== currentMomentum;

      if (!momentumShift && Math.abs(deltaGap) < 0.12) {
        return null;
      }

      return {
        category: item.category,
        previousMomentum,
        currentMomentum,
        previousDelta,
        currentDelta,
        deltaGap,
      };
    })
    .filter(Boolean)
    .sort((left, right) => Math.abs(right.deltaGap) - Math.abs(left.deltaGap));

  const savedNames = new Set(savedCategories.map((item) => item.category));
  const emergentCategories = Object.entries(currentSummary)
    .filter(([category, current]) => !savedNames.has(category) && Math.abs(Number(current?.delta_score || 0)) >= 0.18)
    .sort((left, right) => Math.abs(Number(right[1]?.delta_score || 0)) - Math.abs(Number(left[1]?.delta_score || 0)))
    .slice(0, 2)
    .map(([category, current]) => ({
      category,
      momentum: current?.momentum || 'stable',
      delta: Number(current?.delta_score || 0),
    }));

  return {
    changedCategories,
    emergentCategories,
  };
};

const summarizeFactorShifts = (overview = {}, templateMeta = {}) => {
  const factorDeltas = overview?.trend?.factor_deltas || {};
  const linked = new Set([
    ...(templateMeta?.dominant_drivers || []).map((item) => item?.key).filter(Boolean),
    ...(templateMeta?.driver_summary || []).map((item) => item?.key).filter(Boolean),
  ]);

  return Object.entries(factorDeltas)
    .filter(([key, item]) =>
      linked.has(key) || Boolean(item?.signal_changed) || Math.abs(Number(item?.z_score_delta || 0)) >= 0.35
    )
    .sort((left, right) => Math.abs(Number(right[1]?.z_score_delta || 0)) - Math.abs(Number(left[1]?.z_score_delta || 0)))
    .slice(0, 3)
    .map(([key, item]) => ({
      key,
      label: formatFactorName(key),
      zScoreDelta: Number(item?.z_score_delta || 0),
      signalChanged: Boolean(item?.signal_changed),
    }));
};

const buildSummaryLines = ({
  macroShift,
  resonanceShift,
  policySourceShift,
  biasCompressionShift,
  selectionQualityShift,
  selectionQualityRunState,
  reviewContextShift,
  altShift,
  factorShift,
}) => {
  const lines = [];

  if (macroShift.signalShift) {
    lines.push(`宏观信号从 ${macroShift.savedSignal} 切到 ${macroShift.currentSignal}`);
  } else if (Math.abs(macroShift.scoreGap) >= 0.1) {
    lines.push(`宏观分数相对保存时 ${macroShift.scoreGap >= 0 ? '上行' : '下行'} ${Math.abs(macroShift.scoreGap).toFixed(2)}`);
  }

  if (resonanceShift?.labelChanged) {
    lines.push(`共振从 ${resonanceShift.savedLabel} 切到 ${resonanceShift.currentLabel}`);
  } else if (resonanceShift?.addedFactors?.[0]) {
    lines.push(`${formatFactorName(resonanceShift.addedFactors[0])} 新进入共振簇`);
  }

  if (policySourceShift?.labelChanged) {
    lines.push(`政策源从 ${policySourceShift.savedLabel} 切到 ${policySourceShift.currentLabel}`);
  } else if (policySourceShift?.addedFragileSources?.[0]) {
    lines.push(`${policySourceShift.addedFragileSources[0]} 进入政策脆弱源`);
  }

  if (biasCompressionShift?.labelChanged) {
    lines.push(`偏置收缩从 ${biasCompressionShift.savedLabel} 切到 ${biasCompressionShift.currentLabel}`);
  } else if (biasCompressionShift?.compressed) {
    lines.push(`偏置 scale ${biasCompressionShift.savedScale.toFixed(2)}x 下调到 ${biasCompressionShift.currentScale.toFixed(2)}x`);
  }
  if (biasCompressionShift?.coreLegAffected && biasCompressionShift?.topCompressedAsset) {
    lines.push(`核心腿受压 ${biasCompressionShift.topCompressedAsset}`);
  }
  if (selectionQualityShift?.labelChanged) {
    lines.push(`自动降级从 ${selectionQualityShift.savedLabel} 切到 ${selectionQualityShift.currentLabel}`);
  } else if (selectionQualityShift?.penaltyGap >= 0.1) {
    lines.push(`排序惩罚 ${selectionQualityShift.savedPenalty.toFixed(2)} 提升到 ${selectionQualityShift.currentPenalty.toFixed(2)}`);
  }
  if (selectionQualityRunState?.active) {
    lines.push(
      `当前结果已按 ${selectionQualityRunState.label} 强度运行`
      + (
        selectionQualityRunState.baseScore || selectionQualityRunState.effectiveScore
          ? ` (${selectionQualityRunState.baseScore.toFixed(2)}→${selectionQualityRunState.effectiveScore.toFixed(2)})`
          : ''
      )
    );
  }
  if (reviewContextShift?.lead) {
    lines.push(reviewContextShift.lead);
  }

  if (altShift.changedCategories[0]) {
    const item = altShift.changedCategories[0];
    lines.push(
      `${item.category} 从 ${item.previousMomentum === 'strengthening' ? '增强' : item.previousMomentum === 'weakening' ? '走弱' : '稳定'} 变为 ${item.currentMomentum === 'strengthening' ? '增强' : item.currentMomentum === 'weakening' ? '走弱' : '稳定'}`
    );
  } else if (altShift.emergentCategories[0]) {
    const item = altShift.emergentCategories[0];
    lines.push(`${item.category} 新进入高变化区`);
  }

  if (factorShift[0]) {
    const item = factorShift[0];
    lines.push(`${item.label} ΔZ ${item.zScoreDelta >= 0 ? '+' : ''}${item.zScoreDelta.toFixed(2)}`);
  }

  return lines;
};

const determinePriorityReason = ({
  resonanceDriven,
  selectionQualityDriven,
  selectionQualityRunState,
  reviewContextDriven,
  biasCompressionDriven,
  biasCompressionShift,
  policySourceDriven,
  macroShift,
  altShift,
  factorShift,
}) => {
  if (resonanceDriven) {
    return 'resonance';
  }
  if (biasCompressionShift?.coreLegAffected) {
    return 'bias_quality_core';
  }
  if (selectionQualityRunState?.active) {
    return 'selection_quality_active';
  }
  if (reviewContextDriven) {
    return 'review_context';
  }
  if (selectionQualityDriven) {
    return 'selection_quality';
  }
  if (biasCompressionDriven) {
    return 'bias_quality';
  }
  if (policySourceDriven) {
    return 'policy_source';
  }
  if (macroShift?.signalShift || Math.abs(Number(macroShift?.scoreGap || 0)) >= 0.18) {
    return 'macro';
  }
  if ((altShift?.changedCategories || []).length || (altShift?.emergentCategories || []).length) {
    return 'alt_data';
  }
  if ((factorShift || []).length) {
    return 'factor_shift';
  }
  return 'observe';
};

const getPriorityWeight = (reason = '') => {
  switch (reason) {
    case 'resonance':
      return 5;
    case 'bias_quality_core':
      return 4;
    case 'selection_quality_active':
      return 3.75;
    case 'review_context':
      return 3.6;
    case 'selection_quality':
      return 3.5;
    case 'bias_quality':
      return 3;
    case 'policy_source':
      return 2;
    case 'macro':
      return 1;
    case 'alt_data':
      return 1;
    case 'factor_shift':
      return 1;
    default:
      return 0;
  }
};

export const buildResearchTaskRefreshSignals = ({
  researchTasks = [],
  overview = {},
  snapshot = {},
} = {}) => {
  const activeTasks = (researchTasks || []).filter(
    (task) => task?.type === 'cross_market' && task?.status !== 'archived'
  );

  const suggestions = activeTasks.map((task) => {
    const researchInput = extractTaskResearchInput(task);
    const templateMeta = extractTaskTemplateMeta(task);
    const hasSavedInput =
      Object.keys(researchInput?.macro || {}).length > 0
      || (researchInput?.alt_data?.top_categories || []).length > 0;

    if (!hasSavedInput) {
      return {
        taskId: task.id,
        templateId: task.template || templateMeta.template_id || '',
        title: task.title || templateMeta.template_name || '',
        refreshLabel: '继续观察',
        refreshTone: 'blue',
        severity: 'low',
        urgencyScore: 0,
        summary: '当前任务还没有保存足够的输入快照，建议先运行一次研究并记录结果。',
        macroShift: null,
        policySourceShift: null,
        altShift: { changedCategories: [], emergentCategories: [] },
        factorShift: [],
        policySourceDriven: false,
        resonanceDriven: false,
        recommendation: '先生成首个研究快照，再判断是否需要更新任务',
      };
    }

    const macroShift = summarizeMacroShift(researchInput?.macro || {}, overview);
    const resonanceShift = summarizeResonanceShift(researchInput?.macro || {}, overview);
    const policySourceShift = summarizePolicySourceShift(researchInput?.macro || {}, overview);
    const allocationOverlay = extractTaskPayload(task)?.allocation_overlay || {};
    const biasCompressionShift = summarizeBiasCompressionShift(templateMeta, overview, allocationOverlay);
    const selectionQualityShift = summarizeSelectionQualityShift(templateMeta, biasCompressionShift);
    const selectionQualityRunState = summarizeSelectionQualityRunState(templateMeta, allocationOverlay);
    const reviewContextShift = summarizeReviewContextShift(task);
    const altShift = summarizeAltShifts(researchInput?.alt_data || {}, snapshot);
    const factorShift = summarizeFactorShifts(overview, templateMeta);

    let urgencyScore = 0;
    if (macroShift.signalShift) urgencyScore += 2;
    if (Math.abs(macroShift.scoreGap) >= 0.18) urgencyScore += 2;
    else if (Math.abs(macroShift.scoreGap) >= 0.1) urgencyScore += 1;
    if (resonanceShift.labelChanged) urgencyScore += 2;
    else if (resonanceShift.addedFactors.length || resonanceShift.removedFactors.length) urgencyScore += 1;
    if (policySourceShift.worsening) urgencyScore += 2;
    else if (policySourceShift.labelChanged || policySourceShift.addedFragileSources.length) urgencyScore += 1;
    if (biasCompressionShift.compressed) urgencyScore += biasCompressionShift.scaleGap <= -0.2 ? 2 : 1;
    else if (biasCompressionShift.labelChanged) urgencyScore += 1;
    if (biasCompressionShift.coreLegAffected) urgencyScore += 1;
    if (selectionQualityShift.worsening) urgencyScore += 1;
    else if (selectionQualityShift.labelChanged || selectionQualityShift.penaltyGap >= 0.1) urgencyScore += 1;
    if (selectionQualityRunState.active) urgencyScore += selectionQualityRunState.label === 'auto_downgraded' ? 2 : 1;
    if (reviewContextShift.enteredReview) urgencyScore += 1;
    else if (reviewContextShift.exitedReview) urgencyScore += 0.5;
    urgencyScore += Math.min(2, altShift.changedCategories.length);
    if (altShift.emergentCategories.length) urgencyScore += 1;
    if (factorShift.some((item) => item.signalChanged)) urgencyScore += 1;

    let refreshLabel = '继续观察';
    let refreshTone = 'blue';
    let severity = 'low';
    if (urgencyScore >= 4) {
      refreshLabel = '建议更新';
      refreshTone = 'red';
      severity = 'high';
    } else if (urgencyScore >= 2) {
      refreshLabel = '建议复核';
      refreshTone = 'orange';
      severity = 'medium';
    }

    const summaryLines = buildSummaryLines({
      macroShift,
      resonanceShift,
      policySourceShift,
      biasCompressionShift,
      selectionQualityShift,
      selectionQualityRunState,
      reviewContextShift,
      altShift,
      factorShift,
    });
    const summary = summaryLines.length
      ? summaryLines.join('；')
      : '保存时的宏观与另类数据输入仍然基本稳定，可继续沿当前研究方向推进。';
    const resonanceDriven =
      resonanceShift.labelChanged
      || resonanceShift.addedFactors.length > 0
      || resonanceShift.removedFactors.length > 0;
    const policySourceDriven =
      policySourceShift.worsening
      || policySourceShift.labelChanged
      || policySourceShift.addedFragileSources.length > 0;
    const biasCompressionDriven =
      biasCompressionShift.compressed
      || biasCompressionShift.labelChanged;
    const selectionQualityDriven =
      selectionQualityShift.worsening
      || selectionQualityShift.labelChanged
      || selectionQualityShift.penaltyGap >= 0.1;
    const reviewContextDriven = reviewContextShift.changed;
    const priorityReason = determinePriorityReason({
      resonanceDriven,
      selectionQualityDriven,
      selectionQualityRunState,
      reviewContextDriven,
      biasCompressionDriven,
      biasCompressionShift,
      policySourceDriven,
      macroShift,
      altShift,
      factorShift,
    });
    const priorityWeight = getPriorityWeight(priorityReason);

    return {
      taskId: task.id,
      templateId: task.template || templateMeta.template_id || '',
      title: task.title || templateMeta.template_name || '',
      refreshLabel,
      refreshTone,
      severity,
      urgencyScore,
      summary,
      macroShift,
      resonanceShift,
      policySourceShift,
      biasCompressionShift,
      selectionQualityShift,
      selectionQualityRunState,
      reviewContextShift,
      resonanceDriven,
      policySourceDriven,
      biasCompressionDriven,
      selectionQualityDriven,
      reviewContextDriven,
      priorityReason,
      priorityWeight,
      altShift,
      factorShift,
      recommendation:
        severity === 'high'
          ? selectionQualityRunState.active
            ? '建议优先重开研究页并更新快照，当前结果已处于降级运行状态'
            : '建议重新打开研究页并更新快照'
          : severity === 'medium'
            ? selectionQualityRunState.active
              ? '建议优先复核当前结果，当前结果已处于降级运行状态'
              : '建议在当前工作台内复核关键输入后再推进'
            : selectionQualityRunState.active
              ? '当前结果已处于降级运行状态，建议继续观察并准备重开研究'
              : '当前可以继续执行现有研究路线',
    };
  });

  return {
    byTaskId: Object.fromEntries(suggestions.map((item) => [item.taskId, item])),
    byTemplateId: Object.fromEntries(
      suggestions
        .filter((item) => item.templateId)
        .map((item) => [item.templateId, item])
    ),
    prioritized: [...suggestions].sort((left, right) => {
      if (right.urgencyScore !== left.urgencyScore) {
        return right.urgencyScore - left.urgencyScore;
      }
      return (right.priorityWeight || 0) - (left.priorityWeight || 0);
    }),
  };
};
