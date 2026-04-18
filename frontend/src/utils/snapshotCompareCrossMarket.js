import {
  formatNumber,
  formatPercent,
  formatSignedDelta,
  extractViewContextMetrics,
  buildDriverTrendRows,
} from './snapshotCompareFormatters';

const getSelectionQualitySummaryLabel = (label) => {
  if (!label || label === '-') return '未知结果';
  if (label === 'original') return '普通结果';
  return '复核型结果';
};

const buildSelectionQualitySummary = (base, target) => {
  const baseLabel = getSelectionQualitySummaryLabel(base.selectionQualityLabel);
  const targetLabel = getSelectionQualitySummaryLabel(target.selectionQualityLabel);
  if (base.selectionQualityLabel === target.selectionQualityLabel) return `结果语境 ${baseLabel}`;
  return `结果语境 ${baseLabel} -> ${targetLabel}`;
};

const buildSelectionQualityStateSummary = (base, target) => {
  const baseLabel = base.selectionQualityLabel || '-';
  const targetLabel = target.selectionQualityLabel || '-';
  if (baseLabel === targetLabel) return `运行强度 ${baseLabel}`;
  return `运行强度 ${baseLabel} -> ${targetLabel}`;
};

export const buildSelectionQualityLead = (base, target) => {
  const baseState = base.selectionQualityLabel || '-';
  const targetState = target.selectionQualityLabel || '-';
  const baseSummary = getSelectionQualitySummaryLabel(base.selectionQualityLabel);
  const targetSummary = getSelectionQualitySummaryLabel(target.selectionQualityLabel);

  if (baseState === 'original' && targetState !== 'original') {
    return `目标版本已从${baseSummary}进入${targetSummary}，当前更适合按复核型结果理解。`;
  }
  if (baseState !== 'original' && targetState === 'original') {
    return `目标版本已从${baseSummary}回到${targetSummary}，可以重新按普通结果理解主题强度。`;
  }
  if (baseState !== targetState) {
    return `两版结果语境发生切换，运行强度由 ${baseState} 变为 ${targetState}。`;
  }
  if (targetState !== 'original') {
    return `两版都属于${targetSummary}，重点关注降级强度、偏置收缩和执行约束变化。`;
  }
  return '两版都属于普通结果，重点关注模板构造、输入条件和执行质量变化。';
};

export const extractCrossMarketMetrics = (snapshot) => {
  const payload = snapshot?.payload || {};
  const execution = payload.execution_diagnostics || {};
  const executionPlan = payload.execution_plan || {};
  const templateMeta = payload.template_meta || {};
  const alignment = payload.data_alignment || {};
  const overlay = payload.allocation_overlay || {};
  const selectionQuality = overlay.selection_quality || templateMeta.selection_quality || {};
  const inputReliabilityOverlay = overlay.input_reliability || templateMeta.input_reliability || {};
  const constraintOverlay = payload.constraint_overlay || {};
  const hedgePortfolio = payload.hedge_portfolio || {};
  const researchInput = payload.research_input || {};
  return {
    totalReturn: payload.total_return ?? null,
    sharpeRatio: payload.sharpe_ratio ?? null,
    coverage: alignment.tradable_day_ratio ?? null,
    costDrag: execution.cost_drag ?? null,
    turnover: execution.turnover ?? null,
    concentrationLevel: execution.concentration_level || '-',
    concentrationReason: execution.concentration_reason || '-',
    liquidityLevel: execution.liquidity_level || '-',
    maxAdvUsage: execution.max_adv_usage ?? null,
    marginLevel: execution.margin_level || '-',
    marginUtilization: execution.margin_utilization ?? null,
    grossLeverage: execution.gross_leverage ?? null,
    betaLevel: execution.beta_level || '-',
    betaValue: hedgePortfolio.beta_neutrality?.beta ?? null,
    betaGap: hedgePortfolio.beta_neutrality?.beta_gap ?? null,
    calendarLevel: execution.calendar_level || '-',
    calendarMismatch: alignment.calendar_diagnostics?.max_mismatch_ratio ?? null,
    macroScore: researchInput.macro?.macro_score ?? null,
    macroScoreDelta: researchInput.macro?.macro_score_delta ?? null,
    macroSignalChanged: Boolean(researchInput.macro?.macro_signal_changed),
    macroResonance: researchInput.macro?.resonance?.label || templateMeta.resonance_label || '-',
    policySourceHealth: researchInput.macro?.policy_source_health?.label || '-',
    policySourceReason: researchInput.macro?.policy_source_health?.reason || '-',
    policySourceFullTextRatio: researchInput.macro?.policy_source_health?.avg_full_text_ratio ?? null,
    departmentChaosLabel: researchInput.macro?.department_chaos?.label || '-',
    departmentChaosScore: researchInput.macro?.department_chaos?.avg_chaos_score ?? null,
    departmentChaosSummary: researchInput.macro?.department_chaos?.summary || '-',
    departmentChaosTopDepartment: researchInput.macro?.department_chaos?.top_departments?.[0]?.department
      || researchInput.macro?.department_chaos?.top_departments?.[0]?.department_label || '-',
    inputReliability: researchInput.macro?.input_reliability?.label || '-',
    inputReliabilityScore: researchInput.macro?.input_reliability?.score ?? null,
    inputReliabilityLead: researchInput.macro?.input_reliability?.lead || '-',
    inputReliabilityPosture: inputReliabilityOverlay.posture || researchInput.macro?.input_reliability?.posture || '-',
    inputReliabilityActionHint: inputReliabilityOverlay.action_hint || templateMeta.input_reliability?.action_hint || '-',
    altTrendHeadline: (researchInput.alt_data?.top_categories || [])
      .slice(0, 2).map((item) => `${item.category}:${item.momentum}`).join(', ') || '-',
    lotEfficiency: execution.lot_efficiency ?? null,
    rebalanceCadence: execution.suggested_rebalance || '-',
    stressFlag: execution.stress_test_flag || '-',
    routeCount: executionPlan.route_count ?? null,
    batchCount: Array.isArray(executionPlan.batches) ? executionPlan.batches.length : null,
    providerHeadline: Object.keys(executionPlan.by_provider || {}).join(', ') || '-',
    venueHeadline: (executionPlan.venue_allocation || []).map((item) => item.key).join(', ') || '-',
    maxBatchFraction: execution.max_batch_fraction ?? executionPlan.max_batch_fraction ?? null,
    baseRecommendationScore: selectionQuality.base_recommendation_score ?? templateMeta.base_recommendation_score ?? null,
    recommendationScore: selectionQuality.effective_recommendation_score ?? templateMeta.recommendation_score ?? null,
    baseRecommendationTier: selectionQuality.base_recommendation_tier || templateMeta.base_recommendation_tier || '-',
    recommendationTier: selectionQuality.effective_recommendation_tier || templateMeta.recommendation_tier || '-',
    rankingPenalty: selectionQuality.ranking_penalty ?? templateMeta.ranking_penalty ?? null,
    rankingPenaltyReason: selectionQuality.reason || templateMeta.ranking_penalty_reason || '-',
    selectionQualityLabel: selectionQuality.label || templateMeta.selection_quality?.label || '-',
    selectionQualityReason: selectionQuality.reason || templateMeta.selection_quality?.reason || '-',
    theme: templateMeta.theme || '-',
    resonanceReason: templateMeta.resonance_reason || researchInput.macro?.resonance?.reason || '-',
    allocationMode: templateMeta.allocation_mode || '-',
    biasStrengthRaw: templateMeta.bias_strength_raw ?? null,
    biasSummary: templateMeta.bias_summary || '-',
    biasScale: templateMeta.bias_scale ?? null,
    biasQualityLabel: templateMeta.bias_quality_label || '-',
    biasQualityReason: templateMeta.bias_quality_reason || '-',
    departmentChaosConstructionLabel: templateMeta.department_chaos_label || '-',
    departmentChaosRiskBudgetScale: templateMeta.department_chaos_risk_budget_scale ?? null,
    departmentChaosConstructionReason: templateMeta.department_chaos_reason || '-',
    peopleFragilityConstructionLabel: templateMeta.people_fragility_label || '-',
    peopleFragilityRiskBudgetScale: templateMeta.people_fragility_risk_budget_scale ?? null,
    peopleFragilityConstructionReason: templateMeta.people_fragility_reason || '-',
    structuralDecayRadarConstructionLabel: templateMeta.structural_decay_radar_label || '-',
    structuralDecayRadarRiskBudgetScale: templateMeta.structural_decay_radar_risk_budget_scale ?? null,
    structuralDecayRadarConstructionReason: templateMeta.structural_decay_radar_action_hint || '-',
    biasStrengthEffective: templateMeta.bias_strength ?? null,
    biasCompressionEffect: overlay.bias_compression_effect ?? null,
    biasCompressionRatio: overlay.compression_summary?.compression_ratio ?? null,
    compressedAssets: (overlay.compressed_assets || []).join(', ') || '-',
    topCompressedAsset: (overlay.rows || [])
      .slice().sort((l, r) => Math.abs(Number(r.compression_delta || 0)) - Math.abs(Number(l.compression_delta || 0)))
      .map((item) => Math.abs(Number(item.compression_delta || 0)) >= 0.005 ? `${item.symbol} ${(Math.abs(Number(item.compression_delta || 0)) * 100).toFixed(2)}pp` : null)
      .find(Boolean) || '-',
    coreLegPressure: templateMeta.core_leg_pressure?.affected ? 'yes' : 'no',
    coreLegPressureSummary: templateMeta.core_leg_pressure?.summary || '-',
    maxDeltaWeight: overlay.max_delta_weight ?? null,
    constraintBindingCount: constraintOverlay.binding_count ?? null,
    constraintMaxDeltaWeight: constraintOverlay.max_delta_weight ?? null,
    dominantDriverHeadline: (templateMeta.dominant_drivers || []).map((item) => item.label).join(', ') || '-',
    dominantDrivers: templateMeta.dominant_drivers || [],
    driverSummary: templateMeta.driver_summary || [],
    themeCore: templateMeta.theme_core || '-',
    themeSupport: templateMeta.theme_support || '-',
    policyExecutionLabel: templateMeta.policy_execution_label || '-',
    policyExecutionRiskBudgetScale: templateMeta.policy_execution_risk_budget_scale ?? null,
    policyExecutionReason: templateMeta.policy_execution_reason || '-',
    sourceModeLabel: templateMeta.source_mode_label || '-',
    sourceModeReason: templateMeta.source_mode_reason || '-',
    constructionMode: execution.construction_mode || payload.template?.construction_mode || '-',
    ...extractViewContextMetrics(payload),
  };
};

const t = (base, target, key, label, changeLabel) => ({
  key, label, left: base[key], right: target[key],
  delta: base[key] === target[key] ? '不变' : (changeLabel || `${base[key]} -> ${target[key]}`),
});

export const buildCrossMarketComparisonRows = (base, target) => {
  const driverTrendRows = buildDriverTrendRows(base.driverSummary, target.driverSummary);
  return {
    lead: buildSelectionQualityLead(base, target),
    summary: [
      buildSelectionQualitySummary(base, target),
      buildSelectionQualityStateSummary(base, target),
      `构造 ${base.constructionMode} -> ${target.constructionMode}`,
      `覆盖率 ${formatPercent(base.coverage)} -> ${formatPercent(target.coverage)}`,
      `执行批次 ${formatNumber(base.batchCount, 0)} -> ${formatNumber(target.batchCount, 0)}`,
      `主导驱动 ${base.dominantDriverHeadline} -> ${target.dominantDriverHeadline}`,
    ],
    rows: [
      { key: 'return', label: 'Total Return', left: formatPercent(base.totalReturn), right: formatPercent(target.totalReturn), delta: formatSignedDelta(base.totalReturn, target.totalReturn, (v) => formatPercent(v)) },
      { key: 'sharpe', label: 'Sharpe', left: formatNumber(base.sharpeRatio), right: formatNumber(target.sharpeRatio), delta: formatSignedDelta(base.sharpeRatio, target.sharpeRatio, (v) => formatNumber(v)) },
      { key: 'coverage', label: 'Coverage', left: formatPercent(base.coverage), right: formatPercent(target.coverage), delta: formatSignedDelta(base.coverage, target.coverage, (v) => formatPercent(v)) },
      { key: 'cost-drag', label: 'Cost Drag', left: formatPercent(base.costDrag), right: formatPercent(target.costDrag), delta: formatSignedDelta(base.costDrag, target.costDrag, (v) => formatPercent(v)) },
      { key: 'turnover', label: 'Turnover', left: formatNumber(base.turnover), right: formatNumber(target.turnover), delta: formatSignedDelta(base.turnover, target.turnover, (v) => formatNumber(v)) },
      t(base, target, 'constructionMode', 'Construction'),
      t(base, target, 'viewContextSummary', 'Workbench View', base.viewContextSummary === target.viewContextSummary ? undefined : '工作台筛选视角已变化'),
      t(base, target, 'viewContextTask', 'Workbench Focus', base.viewContextTask === target.viewContextTask ? undefined : '任务焦点已变化'),
      { key: 'route-count', label: 'Route Count', left: formatNumber(base.routeCount, 0), right: formatNumber(target.routeCount, 0), delta: formatSignedDelta(base.routeCount, target.routeCount, (v) => formatNumber(v, 0)) },
      { key: 'batch-count', label: 'Batch Count', left: formatNumber(base.batchCount, 0), right: formatNumber(target.batchCount, 0), delta: formatSignedDelta(base.batchCount, target.batchCount, (v) => formatNumber(v, 0)) },
      t(base, target, 'providerHeadline', 'Providers', base.providerHeadline === target.providerHeadline ? undefined : '已调整'),
      t(base, target, 'venueHeadline', 'Venues', base.venueHeadline === target.venueHeadline ? undefined : '已调整'),
      { key: 'max-batch-fraction', label: 'Max Batch', left: formatPercent(base.maxBatchFraction), right: formatPercent(target.maxBatchFraction), delta: formatSignedDelta(base.maxBatchFraction, target.maxBatchFraction, (v) => formatPercent(v)) },
      t(base, target, 'concentrationLevel', 'Concentration'),
      { key: 'lot-efficiency', label: 'Lot Efficiency', left: formatPercent(base.lotEfficiency), right: formatPercent(target.lotEfficiency), delta: formatSignedDelta(base.lotEfficiency, target.lotEfficiency, (v) => formatPercent(v)) },
      t(base, target, 'liquidityLevel', 'Liquidity'),
      { key: 'max-adv-usage', label: 'Max ADV Usage', left: formatPercent(base.maxAdvUsage), right: formatPercent(target.maxAdvUsage), delta: formatSignedDelta(base.maxAdvUsage, target.maxAdvUsage, (v) => formatPercent(v)) },
      t(base, target, 'marginLevel', 'Margin'),
      { key: 'margin-utilization', label: 'Margin Utilization', left: formatPercent(base.marginUtilization), right: formatPercent(target.marginUtilization), delta: formatSignedDelta(base.marginUtilization, target.marginUtilization, (v) => formatPercent(v)) },
      { key: 'gross-leverage', label: 'Gross Leverage', left: formatNumber(base.grossLeverage), right: formatNumber(target.grossLeverage), delta: formatSignedDelta(base.grossLeverage, target.grossLeverage, (v) => formatNumber(v)) },
      t(base, target, 'betaLevel', 'Beta'),
      { key: 'beta-value', label: 'Beta Value', left: formatNumber(base.betaValue), right: formatNumber(target.betaValue), delta: formatSignedDelta(base.betaValue, target.betaValue, (v) => formatNumber(v)) },
      { key: 'beta-gap', label: 'Beta Gap', left: formatNumber(base.betaGap), right: formatNumber(target.betaGap), delta: formatSignedDelta(base.betaGap, target.betaGap, (v) => formatNumber(v)) },
      t(base, target, 'calendarLevel', 'Calendar'),
      { key: 'calendar-mismatch', label: 'Calendar Mismatch', left: formatPercent(base.calendarMismatch), right: formatPercent(target.calendarMismatch), delta: formatSignedDelta(base.calendarMismatch, target.calendarMismatch, (v) => formatPercent(v)) },
      { key: 'macro-score', label: 'Macro Score', left: formatNumber(base.macroScore), right: formatNumber(target.macroScore), delta: formatSignedDelta(base.macroScore, target.macroScore, (v) => formatNumber(v)) },
      { key: 'macro-score-delta', label: 'Macro Δ', left: formatNumber(base.macroScoreDelta), right: formatNumber(target.macroScoreDelta), delta: formatSignedDelta(base.macroScoreDelta, target.macroScoreDelta, (v) => formatNumber(v)) },
      { key: 'macro-signal-changed', label: 'Macro Signal Change', left: base.macroSignalChanged ? 'yes' : 'no', right: target.macroSignalChanged ? 'yes' : 'no', delta: base.macroSignalChanged === target.macroSignalChanged ? '不变' : '已切换' },
      t(base, target, 'macroResonance', 'Macro Resonance'),
      t(base, target, 'policySourceHealth', 'Policy Source'),
      { key: 'policy-source-ratio', label: 'Policy Full Text', left: formatPercent(base.policySourceFullTextRatio), right: formatPercent(target.policySourceFullTextRatio), delta: formatSignedDelta(base.policySourceFullTextRatio, target.policySourceFullTextRatio, (v) => formatPercent(v)) },
      t(base, target, 'policySourceReason', 'Policy Source Reason', base.policySourceReason === target.policySourceReason ? undefined : '政策源状态已变化'),
      t(base, target, 'policyExecutionLabel', 'Policy Execution'),
      { key: 'policy-execution-score', label: 'Policy Execution Score', left: formatNumber(base.policyExecutionRiskBudgetScale), right: formatNumber(target.policyExecutionRiskBudgetScale), delta: formatSignedDelta(base.policyExecutionRiskBudgetScale, target.policyExecutionRiskBudgetScale, (v) => formatNumber(v)) },
      t(base, target, 'policyExecutionReason', 'Policy Execution Focus', base.policyExecutionReason === target.policyExecutionReason ? undefined : '政策执行判断已变化'),
      t(base, target, 'sourceModeLabel', 'Source Mode'),
      t(base, target, 'sourceModeReason', 'Source Mode Construction', base.sourceModeReason === target.sourceModeReason ? undefined : '来源模式已变化'),
      t(base, target, 'departmentChaosLabel', 'Department Chaos'),
      { key: 'department-chaos-score', label: 'Department Chaos Score', left: formatNumber(base.departmentChaosScore), right: formatNumber(target.departmentChaosScore), delta: formatSignedDelta(base.departmentChaosScore, target.departmentChaosScore, (v) => formatNumber(v)) },
      t(base, target, 'departmentChaosTopDepartment', 'Department Focus', base.departmentChaosTopDepartment === target.departmentChaosTopDepartment ? undefined : '部门焦点已变化'),
      t(base, target, 'departmentChaosSummary', 'Department Chaos Summary', base.departmentChaosSummary === target.departmentChaosSummary ? undefined : '部门混乱判断已变化'),
      t(base, target, 'inputReliability', 'Input Reliability'),
      { key: 'input-reliability-score', label: 'Input Reliability Score', left: formatNumber(base.inputReliabilityScore), right: formatNumber(target.inputReliabilityScore), delta: formatSignedDelta(base.inputReliabilityScore, target.inputReliabilityScore, (v) => formatNumber(v)) },
      t(base, target, 'inputReliabilityLead', 'Input Reliability Lead', base.inputReliabilityLead === target.inputReliabilityLead ? undefined : '输入可靠度判断已变化'),
      t(base, target, 'inputReliabilityPosture', 'Input Reliability Posture', base.inputReliabilityPosture === target.inputReliabilityPosture ? undefined : '输入处理姿势已变化'),
      t(base, target, 'inputReliabilityActionHint', 'Input Reliability Action', base.inputReliabilityActionHint === target.inputReliabilityActionHint ? undefined : '输入复核动作已变化'),
      t(base, target, 'altTrendHeadline', 'Alt Trend', base.altTrendHeadline === target.altTrendHeadline ? undefined : '趋势结构已变'),
      t(base, target, 'rebalanceCadence', 'Rebalance'),
      t(base, target, 'stressFlag', 'Stress Flag'),
      t(base, target, 'recommendationTier', 'Recommendation'),
      { key: 'base-recommendation-score', label: 'Base Recommendation', left: formatNumber(base.baseRecommendationScore), right: formatNumber(target.baseRecommendationScore), delta: formatSignedDelta(base.baseRecommendationScore, target.baseRecommendationScore, (v) => formatNumber(v)) },
      { key: 'effective-recommendation-score', label: 'Effective Recommendation', left: formatNumber(base.recommendationScore), right: formatNumber(target.recommendationScore), delta: formatSignedDelta(base.recommendationScore, target.recommendationScore, (v) => formatNumber(v)) },
      t(base, target, 'baseRecommendationTier', 'Base Tier'),
      { key: 'ranking-penalty', label: 'Ranking Penalty', left: formatNumber(base.rankingPenalty), right: formatNumber(target.rankingPenalty), delta: formatSignedDelta(base.rankingPenalty, target.rankingPenalty, (v) => formatNumber(v)) },
      t(base, target, 'selectionQualityLabel', 'Selection Quality'),
      t(base, target, 'selectionQualityReason', 'Selection Quality Reason', base.selectionQualityReason === target.selectionQualityReason ? undefined : '自动降级原因已变化'),
      t(base, target, 'rankingPenaltyReason', 'Ranking Penalty Reason', base.rankingPenaltyReason === target.rankingPenaltyReason ? undefined : '排序惩罚原因已变化'),
      t(base, target, 'theme', 'Theme', base.theme === target.theme ? undefined : '已切换'),
      t(base, target, 'resonanceReason', 'Resonance Reason', base.resonanceReason === target.resonanceReason ? undefined : '共振背景已变化'),
      t(base, target, 'dominantDriverHeadline', 'Dominant Driver', base.dominantDriverHeadline === target.dominantDriverHeadline ? undefined : '主导叙事已切换'),
      t(base, target, 'themeCore', 'Theme Core', base.themeCore === target.themeCore ? undefined : '核心腿已切换'),
      t(base, target, 'themeSupport', 'Theme Support', base.themeSupport === target.themeSupport ? undefined : '辅助腿已调整'),
      t(base, target, 'allocationMode', 'Allocation Mode'),
      { key: 'bias-strength-raw', label: 'Bias Raw', left: formatNumber(base.biasStrengthRaw), right: formatNumber(target.biasStrengthRaw), delta: formatSignedDelta(base.biasStrengthRaw, target.biasStrengthRaw, (v) => formatNumber(v)) },
      { key: 'bias-strength-effective', label: 'Bias Effective', left: formatNumber(base.biasStrengthEffective), right: formatNumber(target.biasStrengthEffective), delta: formatSignedDelta(base.biasStrengthEffective, target.biasStrengthEffective, (v) => formatNumber(v)) },
      t(base, target, 'biasSummary', 'Bias Summary', base.biasSummary === target.biasSummary ? undefined : '已调整'),
      { key: 'bias-scale', label: 'Bias Scale', left: formatNumber(base.biasScale), right: formatNumber(target.biasScale), delta: formatSignedDelta(base.biasScale, target.biasScale, (v) => formatNumber(v)) },
      t(base, target, 'biasQualityLabel', 'Bias Quality'),
      t(base, target, 'biasQualityReason', 'Bias Quality Reason', base.biasQualityReason === target.biasQualityReason ? undefined : '偏置质量已变化'),
      t(base, target, 'departmentChaosConstructionLabel', 'Department Chaos Construction'),
      { key: 'department-chaos-risk-budget', label: 'Department Risk Budget', left: formatNumber(base.departmentChaosRiskBudgetScale), right: formatNumber(target.departmentChaosRiskBudgetScale), delta: formatSignedDelta(base.departmentChaosRiskBudgetScale, target.departmentChaosRiskBudgetScale, (v) => formatNumber(v)) },
      t(base, target, 'departmentChaosConstructionReason', 'Department Construction Reason', base.departmentChaosConstructionReason === target.departmentChaosConstructionReason ? undefined : '部门构造约束已变化'),
      t(base, target, 'peopleFragilityConstructionLabel', 'People Layer Construction'),
      { key: 'people-fragility-risk-budget', label: 'People Risk Budget', left: formatNumber(base.peopleFragilityRiskBudgetScale), right: formatNumber(target.peopleFragilityRiskBudgetScale), delta: formatSignedDelta(base.peopleFragilityRiskBudgetScale, target.peopleFragilityRiskBudgetScale, (v) => formatNumber(v)) },
      t(base, target, 'peopleFragilityConstructionReason', 'People Construction Reason', base.peopleFragilityConstructionReason === target.peopleFragilityConstructionReason ? undefined : '人的维度构造约束已变化'),
      t(base, target, 'structuralDecayRadarConstructionLabel', 'Structural Decay Radar'),
      { key: 'structural-decay-radar-risk-budget', label: 'Structural Decay Risk Budget', left: formatNumber(base.structuralDecayRadarRiskBudgetScale), right: formatNumber(target.structuralDecayRadarRiskBudgetScale), delta: formatSignedDelta(base.structuralDecayRadarRiskBudgetScale, target.structuralDecayRadarRiskBudgetScale, (v) => formatNumber(v)) },
      t(base, target, 'structuralDecayRadarConstructionReason', 'Structural Decay Reason', base.structuralDecayRadarConstructionReason === target.structuralDecayRadarConstructionReason ? undefined : '结构衰败雷达约束已变化'),
      { key: 'bias-compression-effect', label: 'Bias Compression', left: formatNumber(base.biasCompressionEffect), right: formatNumber(target.biasCompressionEffect), delta: formatSignedDelta(base.biasCompressionEffect, target.biasCompressionEffect, (v) => formatNumber(v)) },
      { key: 'bias-compression-ratio', label: 'Bias Compression Ratio', left: formatPercent(base.biasCompressionRatio), right: formatPercent(target.biasCompressionRatio), delta: formatSignedDelta(base.biasCompressionRatio, target.biasCompressionRatio, (v) => formatPercent(v)) },
      t(base, target, 'compressedAssets', 'Compressed Assets', base.compressedAssets === target.compressedAssets ? undefined : '受影响资产已变化'),
      t(base, target, 'topCompressedAsset', 'Top Compressed', base.topCompressedAsset === target.topCompressedAsset ? undefined : '压缩焦点已切换'),
      t(base, target, 'coreLegPressure', 'Core Leg Pressure', base.coreLegPressure === target.coreLegPressure ? undefined : '核心腿状态已切换'),
      t(base, target, 'coreLegPressureSummary', 'Core Leg Focus', base.coreLegPressureSummary === target.coreLegPressureSummary ? undefined : '核心腿压缩焦点已变化'),
      { key: 'max-delta-weight', label: 'Max Weight Shift', left: formatPercent(base.maxDeltaWeight), right: formatPercent(target.maxDeltaWeight), delta: formatSignedDelta(base.maxDeltaWeight, target.maxDeltaWeight, (v) => formatPercent(v)) },
      { key: 'constraint-binding-count', label: 'Constraint Bindings', left: formatNumber(base.constraintBindingCount, 0), right: formatNumber(target.constraintBindingCount, 0), delta: formatSignedDelta(base.constraintBindingCount, target.constraintBindingCount, (v) => formatNumber(v, 0)) },
      { key: 'constraint-max-shift', label: 'Constraint Shift', left: formatPercent(base.constraintMaxDeltaWeight), right: formatPercent(target.constraintMaxDeltaWeight), delta: formatSignedDelta(base.constraintMaxDeltaWeight, target.constraintMaxDeltaWeight, (v) => formatPercent(v)) },
      ...driverTrendRows,
    ],
  };
};
