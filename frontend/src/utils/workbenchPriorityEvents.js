const REASON_LABELS = {
  structural_decay: '结构衰败/系统雷达',
  selection_quality_active: '降级运行',
  people_layer: '人的维度',
  department_chaos: '部门混乱',
  input_reliability: '输入可靠度',
};

const normalizeScore = (value) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
};

const buildEvent = ({
  reasonKey,
  severity,
  lead,
  detail,
  recommendation = '',
  summary = '',
}) => {
  if (!reasonKey || !lead) {
    return null;
  }

  return {
    reason_key: reasonKey,
    reason_label: REASON_LABELS[reasonKey] || REASON_LABELS.structural_decay,
    severity: severity || 'medium',
    lead,
    detail: detail || '',
    recommendation,
    summary: summary || lead,
  };
};

const isNonStableLabel = (label = '', unstableLabels = []) =>
  unstableLabels.includes(String(label || '').trim().toLowerCase());

export const buildPricingRefreshPriorityEvent = (pricingResult = {}, context = {}) => {
  const symbol = String(context?.symbol || pricingResult?.symbol || '').trim().toUpperCase() || '该标的';
  const structuralDecay = pricingResult?.structural_decay
    || pricingResult?.implications?.structural_decay
    || {};
  const peopleLayer = pricingResult?.people_layer || {};
  const macroMispricing = pricingResult?.macro_mispricing_thesis
    || pricingResult?.implications?.macro_mispricing_thesis
    || {};
  const structuralScore = normalizeScore(structuralDecay?.score);

  if (structuralScore >= 0.6 || String(structuralDecay?.label || '').includes('衰败')) {
    return buildEvent({
      reasonKey: 'structural_decay',
      severity: structuralScore >= 0.75 ? 'high' : 'medium',
      lead: structuralDecay?.summary || `${symbol} 的结构性衰败证据正在主导当前研究优先级`,
      detail: [
        structuralScore ? `衰败分 ${structuralScore.toFixed(2)}` : '',
        structuralDecay?.dominant_failure_label ? `主导失效 ${structuralDecay.dominant_failure_label}` : '',
        peopleLayer?.summary || '',
      ].filter(Boolean).join('；'),
      recommendation: macroMispricing?.stance
        ? `建议按${macroMispricing.stance}视角继续跟踪该任务。`
        : '',
      summary: structuralDecay?.summary || '',
    });
  }

  if (
    String(peopleLayer?.risk_level || '').toLowerCase() === 'high'
    || String(peopleLayer?.stance || '').toLowerCase() === 'fragile'
  ) {
    return buildEvent({
      reasonKey: 'people_layer',
      severity: 'medium',
      lead: peopleLayer?.summary || `${symbol} 的人的维度信号偏脆弱，值得优先跟踪`,
      detail: [
        peopleLayer?.risk_level ? `风险等级 ${peopleLayer.risk_level}` : '',
        peopleLayer?.stance ? `组织姿态 ${peopleLayer.stance}` : '',
      ].filter(Boolean).join('；'),
      summary: peopleLayer?.summary || '',
    });
  }

  return null;
};

export const buildCrossMarketRefreshPriorityEvent = (template = {}, backtestResult = null, researchInputs = {}) => {
  const macroOverview = researchInputs?.macroOverview || {};
  const taskLabel = template?.name || template?.template_name || template?.id || '当前跨市场模板';
  const selectionQuality = backtestResult?.allocation_overlay?.selection_quality || {};
  const rankingPenalty = normalizeScore(
    selectionQuality?.ranking_penalty ?? template?.rankingPenalty
  );
  const templateSelectionLabel = rankingPenalty > 0
    ? (template?.biasQualityLabel || template?.selectionQualityLabel || 'softened')
    : '';
  const selectionLabel = String(selectionQuality?.label || templateSelectionLabel || '').trim().toLowerCase();

  if (selectionLabel && !['original', 'full', 'stable'].includes(selectionLabel)) {
    const baseScore = selectionQuality?.base_recommendation_score ?? template?.baseRecommendationScore ?? null;
    const effectiveScore = selectionQuality?.effective_recommendation_score ?? template?.recommendationScore ?? null;
    const displaySelectionLabel = selectionQuality?.label || templateSelectionLabel || selectionLabel;
    return buildEvent({
      reasonKey: 'selection_quality_active',
      severity: rankingPenalty >= 0.3 ? 'high' : 'medium',
      lead: `${taskLabel} 当前按 ${displaySelectionLabel} 强度运行，已进入优先复核区`,
      detail: [
        baseScore != null && effectiveScore != null
          ? `推荐分 ${Number(baseScore).toFixed(2)}→${Number(effectiveScore).toFixed(2)}`
          : '',
        selectionQuality?.reason || template?.rankingPenaltyReason || '',
      ].filter(Boolean).join('；'),
      recommendation: selectionQuality?.reason || template?.rankingPenaltyReason || '',
      summary: selectionQuality?.reason || '',
    });
  }

  const radar = macroOverview?.structural_decay_radar || {};
  const radarLabel = String(radar?.label || template?.structuralDecayRadarLabel || '').trim().toLowerCase();
  const radarScore = normalizeScore(radar?.score ?? template?.structuralDecayRadarScore);
  if (isNonStableLabel(radarLabel, ['decay_alert', 'decay_watch']) || radarScore >= 0.6) {
    const topSignals = (radar?.top_signals || template?.structuralDecayRadarTopSignals || [])
      .slice(0, 3)
      .map((item) => item?.label || item?.axis || item?.name || '')
      .filter(Boolean)
      .join(' / ');
    return buildEvent({
      reasonKey: 'structural_decay',
      severity: radarLabel === 'decay_alert' || radarScore >= 0.75 ? 'high' : 'medium',
      lead: radar?.action_hint || template?.structuralDecayRadarActionHint || `${taskLabel} 对应的系统衰败雷达正在升温`,
      detail: [
        radarScore ? `雷达分 ${radarScore.toFixed(2)}` : '',
        topSignals ? `雷达焦点 ${topSignals}` : '',
      ].filter(Boolean).join('；'),
      summary: radar?.display_label || radar?.label || '',
    });
  }

  const peopleLabel = String(template?.peopleFragilityLabel || '').trim().toLowerCase();
  const peopleScore = normalizeScore(template?.peopleFragilityScore);
  if (isNonStableLabel(peopleLabel, ['fragile', 'watch']) || peopleScore >= 0.6) {
    return buildEvent({
      reasonKey: 'people_layer',
      severity: peopleScore >= 0.75 ? 'high' : 'medium',
      lead: template?.peopleFragilityReason || `${taskLabel} 的人的维度出现脆弱迹象`,
      detail: [
        peopleScore ? `组织脆弱度 ${peopleScore.toFixed(2)}` : '',
        template?.peopleFragilityFocus ? `关注公司 ${template.peopleFragilityFocus}` : '',
      ].filter(Boolean).join('；'),
      summary: template?.peopleFragilityReason || '',
    });
  }

  const departmentLabel = String(
    macroOverview?.department_chaos_summary?.label || template?.departmentChaosLabel || ''
  ).trim().toLowerCase();
  const departmentScore = normalizeScore(
    macroOverview?.department_chaos_summary?.avg_chaos_score ?? template?.departmentChaosScore
  );
  if (isNonStableLabel(departmentLabel, ['chaotic', 'watch']) || departmentScore >= 0.45) {
    return buildEvent({
      reasonKey: 'department_chaos',
      severity: departmentLabel === 'chaotic' || departmentScore >= 0.65 ? 'high' : 'medium',
      lead: template?.departmentChaosReason
        || macroOverview?.department_chaos_summary?.summary
        || `${taskLabel} 关联的部门政策出现明显混乱`,
      detail: [
        departmentScore ? `混乱度 ${departmentScore.toFixed(2)}` : '',
        template?.departmentChaosTopDepartment ? `部门焦点 ${template.departmentChaosTopDepartment}` : '',
      ].filter(Boolean).join('；'),
      summary: template?.departmentChaosReason || macroOverview?.department_chaos_summary?.summary || '',
    });
  }

  const inputReliability = macroOverview?.input_reliability_summary || {};
  const reliabilityLabel = String(inputReliability?.label || '').trim().toLowerCase();
  if (isNonStableLabel(reliabilityLabel, ['watch', 'fragile'])) {
    return buildEvent({
      reasonKey: 'input_reliability',
      severity: reliabilityLabel === 'fragile' ? 'high' : 'medium',
      lead: inputReliability?.lead || `${taskLabel} 的输入可靠度需要持续观察`,
      detail: [
        inputReliability?.score != null ? `可靠度 ${normalizeScore(inputReliability.score).toFixed(2)}` : '',
        inputReliability?.reason || '',
      ].filter(Boolean).join('；'),
      summary: inputReliability?.reason || inputReliability?.lead || '',
    });
  }

  return null;
};

export const buildTradeThesisRefreshPriorityEvent = (
  draft = {},
  template = {},
  backtestResult = null,
  researchInputs = {}
) => {
  const structuralDecay = draft?.structuralDecay || {};
  const peopleLayer = draft?.peopleLayer || {};
  const symbol = String(draft?.symbol || '').trim().toUpperCase() || '该组合';
  const structuralScore = normalizeScore(structuralDecay?.score);

  if (structuralScore >= 0.6 || String(structuralDecay?.label || '').includes('衰败')) {
    return buildEvent({
      reasonKey: 'structural_decay',
      severity: structuralScore >= 0.75 ? 'high' : 'medium',
      lead: structuralDecay?.summary || `${symbol} 的结构性衰败逻辑正在驱动该交易 Thesis`,
      detail: [
        structuralScore ? `衰败分 ${structuralScore.toFixed(2)}` : '',
        structuralDecay?.label || '',
      ].filter(Boolean).join('；'),
      recommendation: draft?.thesis?.summary || draft?.note || '',
      summary: structuralDecay?.summary || draft?.thesis?.summary || '',
    });
  }

  if (String(peopleLayer?.risk_level || '').toLowerCase() === 'high') {
    return buildEvent({
      reasonKey: 'people_layer',
      severity: 'medium',
      lead: draft?.thesis?.summary || `${symbol} 的人的维度风险正在支撑当前 Thesis`,
      detail: [
        peopleLayer?.risk_level ? `风险等级 ${peopleLayer.risk_level}` : '',
        draft?.note || '',
      ].filter(Boolean).join('；'),
      summary: draft?.thesis?.summary || '',
    });
  }

  return buildCrossMarketRefreshPriorityEvent(template, backtestResult, researchInputs);
};

export const buildMacroMispricingRefreshPriorityEvent = (item = {}) => {
  const symbol = String(item?.symbol || '').trim().toUpperCase() || '该标的';
  const structuralDecay = item?.structuralDecay || {};
  const peopleLayer = item?.peopleLayer || {};
  const score = normalizeScore(structuralDecay?.score || peopleLayer?.people_fragility_score);

  if (score >= 0.6 || String(structuralDecay?.label || '').includes('衰败')) {
    return buildEvent({
      reasonKey: 'structural_decay',
      severity: score >= 0.75 ? 'high' : 'medium',
      lead: structuralDecay?.summary || `${symbol} 已进入结构性衰败观察名单`,
      detail: [
        score ? `衰败分 ${score.toFixed(2)}` : '',
        structuralDecay?.dominant_failure_label ? `主导失效 ${structuralDecay.dominant_failure_label}` : '',
        peopleLayer?.summary || '',
      ].filter(Boolean).join('；'),
      recommendation: item?.macroMispricingThesis?.summary || '',
      summary: structuralDecay?.summary || '',
    });
  }

  if (
    String(peopleLayer?.risk_level || '').toLowerCase() === 'high'
    || normalizeScore(peopleLayer?.people_fragility_score) >= 0.6
  ) {
    return buildEvent({
      reasonKey: 'people_layer',
      severity: 'medium',
      lead: peopleLayer?.summary || `${symbol} 的人的维度风险值得持续跟踪`,
      detail: [
        peopleLayer?.people_fragility_score != null
          ? `组织脆弱度 ${normalizeScore(peopleLayer.people_fragility_score).toFixed(2)}`
          : '',
        peopleLayer?.risk_level ? `风险等级 ${peopleLayer.risk_level}` : '',
      ].filter(Boolean).join('；'),
      summary: peopleLayer?.summary || '',
    });
  }

  return null;
};
