const DIMENSION_META = {
  investment_activity: { label: '投资活跃度', group: 'Supply Chain' },
  project_pipeline: { label: '项目管线', group: 'Supply Chain' },
  talent_structure: { label: '人才结构', group: 'Supply Chain' },
  inventory: { label: '库存压力', group: 'Macro HF' },
  trade: { label: '贸易脉冲', group: 'Macro HF' },
  logistics: { label: '物流摩擦', group: 'Macro HF' },
  people_layer: { label: '人的维度', group: 'People Layer' },
  policy_execution: { label: '政策执行', group: 'Policy Execution' },
  source_mode_summary: { label: '来源治理', group: 'Input Quality' },
};

const FACTOR_LABELS = {
  bureaucratic_friction: '官僚摩擦',
  tech_dilution: '技术稀释',
  baseload_mismatch: '基荷错配',
  rate_curve_pressure: '利率曲线压力',
  credit_spread_stress: '信用利差压力',
  fx_mismatch: '汇率错配',
  people_fragility: '人的维度脆弱',
  policy_execution_disorder: '政策执行混乱',
};

const DEFENSIVE_LONG_SYMBOLS = new Set(['XLU', 'DUK', 'CEG', 'NEE', 'XLE', 'VDE']);
const PHYSICAL_LONG_SYMBOLS = new Set(['HG=F', 'XLE', 'VDE', 'XLU', 'DUK', 'CEG', 'NEE']);
const GROWTH_SHORT_SYMBOLS = new Set(['QQQ', 'ARKK', 'IGV', 'CLOU', 'SOXX', 'SMH']);
const SEMI_SHORT_SYMBOLS = new Set(['SOXX', 'SMH']);
const RISK_ON_LONG_SYMBOLS = new Set(['QQQ', 'ARKK', 'IGV', 'CLOU', 'SOXX', 'SMH']);

const formatFactorName = (name = '') => FACTOR_LABELS[name] || name.replace(/_/g, ' ');

const clampMin = (value, minimum = 0.05) => Math.max(minimum, Number(value || 0));
const pushContribution = (list, key, label, value) => {
  const numeric = Number(value || 0);
  if (numeric <= 0.005) {
    return;
  }
  list.push({
    key,
    label,
    value: Number(numeric.toFixed(4)),
  });
};

const buildFactorLookup = (overview = {}) =>
  Object.fromEntries((overview?.factors || []).map((factor) => [factor.name, factor]));

const buildDimensionLookup = (snapshot = {}) => ({
  ...(snapshot?.signals?.supply_chain?.dimensions || {}),
  ...(snapshot?.signals?.macro_hf?.dimensions || {}),
});

const buildRecommendationTier = (score) => {
  if (score >= 2.6) return '优先部署';
  if (score >= 1.4) return '重点跟踪';
  return '候选模板';
};

const buildRecommendationTone = (score) => {
  if (score >= 2.6) return 'volcano';
  if (score >= 1.4) return 'gold';
  return 'blue';
};

const buildResonanceMeta = (overview = {}) => {
  const resonance = overview?.resonance_summary || {};
  return {
    label: resonance.label || 'mixed',
    reason: resonance.reason || '',
    positive: new Set(resonance.positive_cluster || []),
    negative: new Set(resonance.negative_cluster || []),
    weakening: new Set(resonance.weakening || []),
    precursor: new Set(resonance.precursor || []),
    reversed: new Set(resonance.reversed_factors || []),
  };
};

const buildPolicySourceHealthMeta = (overview = {}) => {
  const summary = overview?.evidence_summary?.policy_source_health_summary || {};
  return {
    label: summary.label || 'unknown',
    reason: summary.reason || '',
    fragileSources: summary.fragile_sources || [],
    watchSources: summary.watch_sources || [],
    avgFullTextRatio: Number(summary.avg_full_text_ratio || 0),
  };
};

const buildInputReliabilityMeta = (overview = {}) => {
  const summary = overview?.input_reliability_summary || {};
  return {
    label: summary.label || 'unknown',
    score: Number(summary.score || 0),
    lead: summary.lead || '',
    posture: summary.posture || '',
    reason: summary.reason || '',
    dominantIssueLabels: summary.dominant_issue_labels || [],
    dominantSupportLabels: summary.dominant_support_labels || [],
  };
};

const buildDepartmentChaosMeta = (overview = {}) => {
  const summary = overview?.department_chaos_summary || {};
  const topDepartment = (summary.top_departments || [])[0] || {};
  const avgScore = Number(summary.avg_chaos_score || 0);
  const topScore = Number(topDepartment.chaos_score || 0);
  const intensity = Math.max(avgScore, topScore);
  const label = summary.label || 'unknown';
  const active = label === 'chaotic' || intensity >= 0.58;
  const watch = label === 'watch' || intensity >= 0.38;
  const riskBudgetScale = active ? 0.82 : watch ? 0.92 : 1;

  return {
    label,
    summary: summary.summary || '',
    score: Number(avgScore.toFixed(4)),
    intensity: Number(Math.min(1, intensity).toFixed(4)),
    active,
    watch,
    riskBudgetScale,
    topDepartment: topDepartment.department || '',
    topDepartmentLabel: topDepartment.department_label || topDepartment.department || '',
    topDepartmentReason: topDepartment.reason || '',
    defensiveTilt: active ? Math.min(0.16, intensity * 0.16) : watch ? Math.min(0.07, intensity * 0.09) : 0,
    hedgeBoost: active ? Math.min(0.14, intensity * 0.14) : watch ? Math.min(0.06, intensity * 0.08) : 0,
    offensiveHaircut: active ? Math.min(0.12, intensity * 0.12) : watch ? Math.min(0.05, intensity * 0.06) : 0,
  };
};

const buildPeopleFragilityMeta = (overview = {}) => {
  const summary = overview?.people_layer_summary || {};
  const watchlist = summary.watchlist || [];
  const fragileCompanies = summary.fragile_companies || [];
  const topCompany = [...fragileCompanies, ...watchlist]
    .sort((left, right) => Number(right?.people_fragility_score || 0) - Number(left?.people_fragility_score || 0))[0] || {};
  const avgScore = Number(summary.avg_fragility_score || 0);
  const topScore = Number(topCompany.people_fragility_score || 0);
  const dilutionRatio = Number(topCompany?.hiring_signal?.dilution_ratio || 0);
  const dilutionPressure = dilutionRatio > 1 ? Math.min(1, (dilutionRatio - 1) / 1.5) : 0;
  const intensity = Math.max(avgScore, topScore, dilutionPressure);
  const label = summary.label || (fragileCompanies.length ? 'fragile' : watchlist.length ? 'watch' : 'stable');
  const active = label === 'fragile' || topScore >= 0.68 || dilutionRatio >= 1.6;
  const watch = active || label === 'watch' || topScore >= 0.48 || dilutionRatio >= 1.35;
  const riskBudgetScale = active ? 0.88 : watch ? 0.96 : 1;

  return {
    label,
    summary: summary.summary || '',
    score: Number(Math.max(avgScore, topScore).toFixed(4)),
    intensity: Number(Math.min(1, intensity).toFixed(4)),
    active,
    watch,
    riskBudgetScale,
    companySymbol: topCompany.symbol || '',
    companyName: topCompany.company_name || topCompany.symbol || '',
    reason: topCompany.summary || summary.summary || '',
    shortBoost: active ? Math.min(0.18, intensity * 0.18) : watch ? Math.min(0.08, intensity * 0.1) : 0,
    defensiveTilt: active ? Math.min(0.08, intensity * 0.08) : watch ? Math.min(0.04, intensity * 0.05) : 0,
    riskOnHaircut: active ? Math.min(0.14, intensity * 0.14) : watch ? Math.min(0.06, intensity * 0.08) : 0,
  };
};

const buildPolicyExecutionMeta = (overview = {}) => {
  const summary = overview?.department_chaos_summary || {};
  const factorLookup = buildFactorLookup(overview);
  const factor = factorLookup.policy_execution_disorder || {};
  const topDepartment = (summary.top_departments || [])[0] || {};
  const avgScore = Number(summary.avg_chaos_score || 0);
  const factorStrength = Math.abs(Number(factor.z_score || factor.value || 0));
  const intensity = Math.max(avgScore, factorStrength * 0.28);
  const label = summary.label || (intensity >= 0.6 ? 'chaotic' : intensity >= 0.36 ? 'watch' : 'stable');
  const active = label === 'chaotic' || intensity >= 0.58;
  const watch = active || label === 'watch' || intensity >= 0.38;
  const riskBudgetScale = active ? 0.84 : watch ? 0.94 : 1;

  return {
    label,
    summary: summary.summary || '',
    score: Number(avgScore.toFixed(4)),
    intensity: Number(Math.min(1, intensity).toFixed(4)),
    active,
    watch,
    riskBudgetScale,
    topDepartment: topDepartment.department || '',
    topDepartmentLabel: topDepartment.department_label || topDepartment.department || '',
    reason: topDepartment.reason || summary.summary || '',
    hedgeBoost: active ? Math.min(0.16, intensity * 0.16) : watch ? Math.min(0.07, intensity * 0.09) : 0,
    offensiveHaircut: active ? Math.min(0.14, intensity * 0.14) : watch ? Math.min(0.06, intensity * 0.08) : 0,
  };
};

const buildSourceModeMeta = (overview = {}, snapshot = {}) => {
  const summary = overview?.source_mode_summary || snapshot?.source_mode_summary || {};
  const counts = summary?.counts || {};
  const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
  const officialLike = ['official', 'corporate_governance', 'market_disclosure', 'market', 'public_procurement', 'regulatory_filing']
    .reduce((sum, key) => sum + Number(counts?.[key] || 0), 0);
  const fallbackLike = ['proxy', 'curated', 'derived']
    .reduce((sum, key) => sum + Number(counts?.[key] || 0), 0);
  const officialShare = total ? officialLike / total : 0;
  const fallbackShare = total ? fallbackLike / total : 0;
  const providerHealth = snapshot?.provider_health || {};
  const degradedProviders = Number(providerHealth?.degraded_providers || 0) + Number(providerHealth?.error_providers || 0);
  const label = summary?.label
    || (fallbackShare >= 0.45 ? 'fallback-heavy' : officialShare >= 0.5 ? 'official-led' : 'mixed');
  const riskBudgetScale = label === 'fallback-heavy' ? (degradedProviders ? 0.72 : 0.8) : 1;

  return {
    label,
    dominant: summary?.dominant || '',
    counts,
    coverage: total,
    officialShare: Number(officialShare.toFixed(4)),
    fallbackShare: Number(fallbackShare.toFixed(4)),
    degradedProviders,
    riskBudgetScale,
    active: label === 'fallback-heavy',
    watch: label === 'mixed',
    reason:
      label === 'fallback-heavy'
        ? `当前来源治理偏回退，degraded provider ${degradedProviders} 个，建议压缩偏置强度。`
        : label === 'official-led'
          ? '当前研究输入以官方/披露源为主，来源治理对结论形成小幅正向支撑。'
          : '当前研究输入由多类来源混合组成，方向保持不变，但需要继续观察来源治理质量。',
  };
};

const buildStructuralDecayRadarMeta = (overview = {}) => {
  const radar = overview?.structural_decay_radar || {};
  const axes = radar.axes || [];
  const score = Number(radar.score || 0);
  const criticalAxisCount = Number(radar.critical_axis_count || 0);
  const topSignals = radar.top_signals || [];
  const active = radar.label === 'decay_alert' || score >= 0.68 || criticalAxisCount >= 3;
  const watch = active || radar.label === 'decay_watch' || score >= 0.44 || criticalAxisCount >= 1;
  const riskBudgetScale = active ? 0.78 : watch ? 0.9 : 1;
  const intensity = Math.min(1, Math.max(score, criticalAxisCount / 5));

  return {
    label: radar.label || 'stable',
    displayLabel: radar.display_label || '',
    score: Number(score.toFixed(4)),
    criticalAxisCount,
    axes,
    topSignals,
    actionHint: radar.action_hint || '',
    active,
    watch,
    riskBudgetScale,
    defensiveTilt: active ? Math.min(0.14, intensity * 0.14) : watch ? Math.min(0.06, intensity * 0.08) : 0,
    hedgeBoost: active ? Math.min(0.16, intensity * 0.16) : watch ? Math.min(0.07, intensity * 0.09) : 0,
    riskOnHaircut: active ? Math.min(0.13, intensity * 0.13) : watch ? Math.min(0.06, intensity * 0.08) : 0,
  };
};

export const CROSS_MARKET_FACTOR_LABELS = FACTOR_LABELS;
export const CROSS_MARKET_DIMENSION_LABELS = Object.fromEntries(
  Object.entries(DIMENSION_META).map(([key, meta]) => [key, meta.label])
);

const normalizeSideWeights = (assets = []) => {
  const total = assets.reduce((sum, asset) => sum + Number(asset.weight || 0), 0) || 1;
  return assets.map((asset) => ({
    ...asset,
    weight: Number((Number(asset.weight || 0) / total).toFixed(6)),
  }));
};

const buildSignalContext = (overview = {}, snapshot = {}) => {
  const factorLookup = buildFactorLookup(overview);
  const dimensionLookup = buildDimensionLookup(snapshot);
  return {
    baseload:
      Math.max(
        Math.abs(Number(factorLookup.baseload_mismatch?.z_score || factorLookup.baseload_mismatch?.value || 0)),
        Math.abs(Number(dimensionLookup.inventory?.score || 0)),
        Math.abs(Number(dimensionLookup.project_pipeline?.score || 0))
      ),
    techDilution:
      Math.max(
        Math.abs(Number(factorLookup.tech_dilution?.z_score || factorLookup.tech_dilution?.value || 0)),
        Math.abs(Number(dimensionLookup.talent_structure?.score || 0))
      ),
    bureaucratic:
      Math.max(
        Math.abs(Number(factorLookup.bureaucratic_friction?.z_score || factorLookup.bureaucratic_friction?.value || 0)),
        Math.abs(Number(dimensionLookup.logistics?.score || 0))
      ),
    trade:
      Math.max(
        Math.abs(Number(dimensionLookup.trade?.score || 0)),
        Math.abs(Number(dimensionLookup.logistics?.score || 0))
      ),
    investment: Math.abs(Number(dimensionLookup.investment_activity?.score || 0)),
  };
};

const buildBiasQualityMeta = (
  policySourceHealth = {},
  inputReliability = {},
  departmentChaos = {},
  peopleFragility = {},
  structuralDecayRadar = {},
  sourceModeMeta = {}
) => {
  const structuralScale = Math.min(
    Number(departmentChaos.riskBudgetScale || 1),
    Number(peopleFragility.riskBudgetScale || 1),
    Number(structuralDecayRadar.riskBudgetScale || 1),
    Number(sourceModeMeta.riskBudgetScale || 1)
  );
  if (sourceModeMeta.label === 'fallback-heavy') {
    return {
      scale: Math.min(sourceModeMeta.riskBudgetScale || 0.8, structuralScale),
      label: 'source_guarded',
      reason: sourceModeMeta.reason || '来源治理偏回退，组合偏置只做幅度压缩，不改方向。',
    };
  }
  if (policySourceHealth.label === 'fragile' || inputReliability.label === 'fragile') {
    const reasons = [policySourceHealth.reason, inputReliability.lead || inputReliability.reason].filter(Boolean);
    return {
      scale: Math.min(policySourceHealth.label === 'fragile' ? 0.55 : 0.72, structuralScale),
      label: 'compressed',
      reason: reasons.join(' · ') || '整体输入可靠度偏脆弱，宏观偏置已收缩到更保守的幅度',
    };
  }
  if (policySourceHealth.label === 'watch' || inputReliability.label === 'watch') {
    const reasons = [policySourceHealth.reason, inputReliability.lead || inputReliability.reason].filter(Boolean);
    return {
      scale: Math.min(policySourceHealth.label === 'watch' ? 0.78 : 0.88, structuralScale),
      label: 'cautious',
      reason: reasons.join(' · ') || '整体输入可靠度需要观察，宏观偏置已适度收缩',
    };
  }
  if (structuralDecayRadar.active) {
    return {
      scale: structuralDecayRadar.riskBudgetScale,
      label: 'decay_guarded',
      reason: `${structuralDecayRadar.displayLabel || '结构衰败雷达'} 进入警报区，组合偏置进入系统级防御风险预算`,
    };
  }
  if (structuralDecayRadar.watch) {
    return {
      scale: structuralDecayRadar.riskBudgetScale,
      label: 'decay_watch',
      reason: `${structuralDecayRadar.displayLabel || '结构衰败雷达'} 升温，组合偏置适度保守`,
    };
  }
  if (departmentChaos.active) {
    return {
      scale: departmentChaos.riskBudgetScale,
      label: 'chaos_guarded',
      reason: `${departmentChaos.topDepartmentLabel || '政策主体'} 政策混乱度偏高，组合偏置进入防御化风险预算`,
    };
  }
  if (departmentChaos.watch) {
    return {
      scale: departmentChaos.riskBudgetScale,
      label: 'chaos_watch',
      reason: `${departmentChaos.topDepartmentLabel || '政策主体'} 政策混乱度处于观察区，组合偏置适度保守`,
    };
  }
  if (peopleFragility.active) {
    return {
      scale: peopleFragility.riskBudgetScale,
      label: 'people_guarded',
      reason: `${peopleFragility.companyName || '重点公司'} 组织脆弱度偏高，组合偏置进入执行质量折扣`,
    };
  }
  if (peopleFragility.watch) {
    return {
      scale: peopleFragility.riskBudgetScale,
      label: 'people_watch',
      reason: `${peopleFragility.companyName || '重点公司'} 组织脆弱度处于观察区，组合偏置适度保守`,
    };
  }
  return {
    scale: 1,
    label: 'full',
    reason: sourceModeMeta.reason || policySourceHealth.reason || '',
  };
};

const buildAdjustedAssets = (
  template = {},
  signalContext = {},
  qualityMeta = {},
  departmentChaos = {},
  peopleFragility = {},
  structuralDecayRadar = {},
  policyExecution = {},
  sourceModeMeta = {}
) => {
  const longAssets = [];
  const shortAssets = [];
  const rawLongAssets = [];
  const rawShortAssets = [];
  const signalAttribution = [];
  const driverSummary = {};
  const qualityScale = Number(qualityMeta.scale || 1);

  (template.assets || []).forEach((asset) => {
    const currentWeight = Number(asset.weight || 0) || 1;
    let multiplier = 1;
    const symbol = String(asset.symbol || '').toUpperCase();
    const isLong = asset.side === 'long';
    const biasReasons = [];
    const breakdown = [];

    if (isLong) {
      if (asset.asset_class === 'COMMODITY_FUTURES') {
        const uplift = signalContext.baseload * 0.16 + signalContext.trade * 0.12;
        multiplier += uplift;
        pushContribution(breakdown, 'physical_tightness', '上游实物紧张', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`上游实物紧张 ${uplift.toFixed(2)}`);
        }
      }
      if (DEFENSIVE_LONG_SYMBOLS.has(symbol)) {
        const uplift = signalContext.bureaucratic * 0.1 + signalContext.baseload * 0.08;
        multiplier += uplift;
        pushContribution(breakdown, 'defensive_premium', '防守资产溢价', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`防守资产溢价 ${uplift.toFixed(2)}`);
        }
      }
      if (PHYSICAL_LONG_SYMBOLS.has(symbol)) {
        const uplift = signalContext.investment * 0.12 + signalContext.baseload * 0.1;
        multiplier += uplift;
        pushContribution(breakdown, 'baseload_support', '基建/基荷支撑', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`基建/基荷支撑 ${uplift.toFixed(2)}`);
        }
      }
      if (departmentChaos.watch && (DEFENSIVE_LONG_SYMBOLS.has(symbol) || PHYSICAL_LONG_SYMBOLS.has(symbol))) {
        const uplift = departmentChaos.defensiveTilt;
        multiplier += uplift;
        pushContribution(breakdown, 'department_chaos_defensive', '部门混乱防御化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`部门混乱防御化 ${uplift.toFixed(2)}`);
        }
      } else if (departmentChaos.watch && RISK_ON_LONG_SYMBOLS.has(symbol)) {
        const haircut = departmentChaos.offensiveHaircut;
        multiplier -= haircut;
        pushContribution(breakdown, 'department_chaos_offensive_haircut', '进攻腿风险折扣', haircut);
        if (haircut > 0.02) {
          biasReasons.push(`进攻腿风险折扣 -${haircut.toFixed(2)}`);
        }
      }
      if (policyExecution.watch && (DEFENSIVE_LONG_SYMBOLS.has(symbol) || PHYSICAL_LONG_SYMBOLS.has(symbol))) {
        const uplift = policyExecution.hedgeBoost;
        multiplier += uplift;
        pushContribution(breakdown, 'policy_execution_defensive', '政策执行防御化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`政策执行防御化 ${uplift.toFixed(2)}`);
        }
      } else if (policyExecution.watch && RISK_ON_LONG_SYMBOLS.has(symbol)) {
        const haircut = policyExecution.offensiveHaircut;
        multiplier -= haircut;
        pushContribution(breakdown, 'policy_execution_offensive_haircut', '政策执行风险折扣', haircut);
        if (haircut > 0.02) {
          biasReasons.push(`政策执行风险折扣 -${haircut.toFixed(2)}`);
        }
      }
      if (peopleFragility.watch && DEFENSIVE_LONG_SYMBOLS.has(symbol)) {
        const uplift = peopleFragility.defensiveTilt;
        multiplier += uplift;
        pushContribution(breakdown, 'people_fragility_defensive', '组织脆弱防御化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`组织脆弱防御化 ${uplift.toFixed(2)}`);
        }
      } else if (peopleFragility.watch && RISK_ON_LONG_SYMBOLS.has(symbol)) {
        const haircut = peopleFragility.riskOnHaircut;
        multiplier -= haircut;
        pushContribution(breakdown, 'people_fragility_risk_on_haircut', '组织脆弱风险折扣', haircut);
        if (haircut > 0.02) {
          biasReasons.push(`组织脆弱风险折扣 -${haircut.toFixed(2)}`);
        }
      }
      if (structuralDecayRadar.watch && (DEFENSIVE_LONG_SYMBOLS.has(symbol) || PHYSICAL_LONG_SYMBOLS.has(symbol))) {
        const uplift = structuralDecayRadar.defensiveTilt;
        multiplier += uplift;
        pushContribution(breakdown, 'structural_decay_defensive', '结构衰败防御化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`结构衰败防御化 ${uplift.toFixed(2)}`);
        }
      } else if (structuralDecayRadar.watch && RISK_ON_LONG_SYMBOLS.has(symbol)) {
        const haircut = structuralDecayRadar.riskOnHaircut;
        multiplier -= haircut;
        pushContribution(breakdown, 'structural_decay_risk_on_haircut', '结构衰败风险折扣', haircut);
        if (haircut > 0.02) {
          biasReasons.push(`结构衰败风险折扣 -${haircut.toFixed(2)}`);
        }
      }
    } else {
      if (GROWTH_SHORT_SYMBOLS.has(symbol)) {
        const uplift = signalContext.techDilution * 0.14 + signalContext.baseload * 0.08;
        multiplier += uplift;
        pushContribution(breakdown, 'growth_pressure', '成长端估值压力', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`成长端估值压力 ${uplift.toFixed(2)}`);
        }
      }
      if (SEMI_SHORT_SYMBOLS.has(symbol)) {
        const uplift = signalContext.trade * 0.1;
        multiplier += uplift;
        pushContribution(breakdown, 'trade_friction', '贸易摩擦抬升', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`贸易摩擦抬升 ${uplift.toFixed(2)}`);
        }
      }
      if (symbol === 'QQQ') {
        const uplift = signalContext.bureaucratic * 0.06;
        multiplier += uplift;
        pushContribution(breakdown, 'bureaucratic_drag', '官僚摩擦压制估值', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`官僚摩擦压制估值 ${uplift.toFixed(2)}`);
        }
      }
      if (departmentChaos.watch && GROWTH_SHORT_SYMBOLS.has(symbol)) {
        const uplift = departmentChaos.hedgeBoost;
        multiplier += uplift;
        pushContribution(breakdown, 'department_chaos_hedge', '部门混乱对冲强化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`部门混乱对冲强化 ${uplift.toFixed(2)}`);
        }
      }
      if (policyExecution.watch && GROWTH_SHORT_SYMBOLS.has(symbol)) {
        const uplift = policyExecution.hedgeBoost;
        multiplier += uplift;
        pushContribution(breakdown, 'policy_execution_hedge', '政策执行对冲强化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`政策执行对冲强化 ${uplift.toFixed(2)}`);
        }
      }
      if (peopleFragility.watch && GROWTH_SHORT_SYMBOLS.has(symbol)) {
        const uplift = peopleFragility.shortBoost;
        multiplier += uplift;
        pushContribution(breakdown, 'people_fragility_short', '组织脆弱空头强化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`组织脆弱空头强化 ${uplift.toFixed(2)}`);
        }
      }
      if (structuralDecayRadar.watch && GROWTH_SHORT_SYMBOLS.has(symbol)) {
        const uplift = structuralDecayRadar.hedgeBoost;
        multiplier += uplift;
        pushContribution(breakdown, 'structural_decay_hedge', '结构衰败对冲强化', uplift);
        if (uplift > 0.02) {
          biasReasons.push(`结构衰败对冲强化 ${uplift.toFixed(2)}`);
        }
      }
    }

    breakdown.forEach((item) => {
      driverSummary[item.key] = {
        key: item.key,
        label: item.label,
        value: Number(((driverSummary[item.key]?.value || 0) + item.value).toFixed(4)),
      };
    });

    const adjustedMultiplier = 1 + (multiplier - 1) * qualityScale;
    const adjusted = {
      ...asset,
      weight: clampMin(currentWeight * adjustedMultiplier, 0.01),
      base_weight: Number(currentWeight.toFixed(6)),
      bias_reasons: biasReasons,
      bias_breakdown: breakdown,
    };
    const rawAdjusted = {
      ...asset,
      weight: clampMin(currentWeight * multiplier, 0.01),
      base_weight: Number(currentWeight.toFixed(6)),
    };
    signalAttribution.push({
      symbol,
      side: asset.side,
      asset_class: asset.asset_class,
      multiplier: Number(adjustedMultiplier.toFixed(4)),
      raw_multiplier: Number(multiplier.toFixed(4)),
      quality_scale: Number(qualityScale.toFixed(2)),
      reasons: biasReasons,
      breakdown,
    });
    if (isLong) {
      longAssets.push(adjusted);
      rawLongAssets.push(rawAdjusted);
    } else {
      shortAssets.push(adjusted);
      rawShortAssets.push(rawAdjusted);
    }
  });

  const normalizedLong = normalizeSideWeights(longAssets);
  const normalizedShort = normalizeSideWeights(shortAssets);
  const normalizedRawLong = normalizeSideWeights(rawLongAssets);
  const normalizedRawShort = normalizeSideWeights(rawShortAssets);
  const adjustedAssets = [...normalizedLong, ...normalizedShort];
  const rawAdjustedAssets = [...normalizedRawLong, ...normalizedRawShort];
  const deltas = adjustedAssets
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      delta: Number(((asset.weight || 0) - (asset.base_weight || 0)).toFixed(4)),
    }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const rawDeltas = rawAdjustedAssets
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      delta: Number(((asset.weight || 0) - (asset.base_weight || 0)).toFixed(4)),
    }))
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  const longLeader = deltas.find((item) => item.side === 'long' && item.delta > 0);
  const shortLeader = deltas.find((item) => item.side === 'short' && item.delta > 0);
  const strongestShift = deltas[0] ? Math.abs(deltas[0].delta) : 0;
  const rawStrongestShift = rawDeltas[0] ? Math.abs(rawDeltas[0].delta) : 0;

  const summaryParts = [];
  if (longLeader) {
    summaryParts.push(`多头增配 ${longLeader.symbol}`);
  }
  if (shortLeader) {
    summaryParts.push(`空头增配 ${shortLeader.symbol}`);
  }
  if (departmentChaos.watch) {
    summaryParts.push(`${departmentChaos.topDepartmentLabel || '政策主体'} 混乱触发防御化`);
  }
  if (policyExecution.watch) {
    summaryParts.push(`${policyExecution.topDepartmentLabel || '政策执行'} 触发政策敏感对冲`);
  }
  if (peopleFragility.watch) {
    summaryParts.push(`${peopleFragility.companyName || '组织脆弱'} 触发执行质量折扣`);
  }
  if (structuralDecayRadar.watch) {
    summaryParts.push(`${structuralDecayRadar.displayLabel || '结构衰败雷达'} 触发系统防御预算`);
  }

  const biasHighlights = deltas
    .filter((item) => Math.abs(item.delta) >= 0.02)
    .slice(0, 4)
    .map((item) => `${item.symbol} ${item.delta > 0 ? '+' : ''}${(item.delta * 100).toFixed(1)}pp`);
  const biasActions = deltas
    .filter((item) => Math.abs(item.delta) >= 0.02)
    .slice(0, 6)
    .map((item) => ({
      symbol: item.symbol,
      side: item.side,
      action: item.delta > 0 ? 'increase' : 'reduce',
      delta: Number(item.delta.toFixed(4)),
    }));
  const rawBiasHighlights = rawDeltas
    .filter((item) => Math.abs(item.delta) >= 0.02)
    .slice(0, 4)
    .map((item) => `${item.symbol} ${item.delta > 0 ? '+' : ''}${(item.delta * 100).toFixed(1)}pp`);
  const dominantDrivers = Object.values(driverSummary)
    .sort((a, b) => b.value - a.value)
    .slice(0, 3);
  const coreLegs = adjustedAssets
    .filter((asset) => Math.abs((asset.weight || 0) - (asset.base_weight || 0)) >= 0.025)
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      role: 'core',
      delta: Number((((asset.weight || 0) - (asset.base_weight || 0)) * 100).toFixed(2)),
    }));
  const supportLegs = adjustedAssets
    .filter((asset) => Math.abs((asset.weight || 0) - (asset.base_weight || 0)) < 0.025)
    .map((asset) => ({
      symbol: asset.symbol,
      side: asset.side,
      role: 'support',
      delta: Number((((asset.weight || 0) - (asset.base_weight || 0)) * 100).toFixed(2)),
    }));
  const themeCore = coreLegs.length
    ? coreLegs.map((item) => `${item.symbol}${item.delta > 0 ? '+' : ''}${item.delta.toFixed(1)}pp`).join('，')
    : '暂无明确主题核心腿';
  const themeSupport = supportLegs.length
    ? supportLegs.map((item) => item.symbol).join('，')
    : '无辅助腿';

  return {
    rawAdjustedAssets,
    adjustedAssets,
    biasSummary: summaryParts.join('，') || '当前信号更适合作为方向参考，权重保持接近模板原始配置',
    rawBiasStrength: Number((rawStrongestShift * 100).toFixed(2)),
    biasStrength: Number((strongestShift * 100).toFixed(2)),
    biasScale: Number(qualityScale.toFixed(2)),
    biasQualityLabel: qualityMeta.label || 'full',
    biasQualityReason: qualityMeta.reason || '',
    rawBiasHighlights,
    biasHighlights,
    biasActions,
    signalAttribution,
    driverSummary: Object.values(driverSummary).sort((a, b) => b.value - a.value),
    dominantDrivers,
    coreLegs,
    supportLegs,
    themeCore,
    themeSupport,
    departmentChaosLabel: departmentChaos.label || 'unknown',
    departmentChaosScore: departmentChaos.score || 0,
    departmentChaosTopDepartment: departmentChaos.topDepartmentLabel || '',
    departmentChaosReason: departmentChaos.topDepartmentReason || departmentChaos.summary || '',
    departmentChaosRiskBudgetScale: Number((departmentChaos.riskBudgetScale || 1).toFixed(2)),
    policyExecutionLabel: policyExecution.label || 'unknown',
    policyExecutionScore: policyExecution.score || 0,
    policyExecutionTopDepartment: policyExecution.topDepartmentLabel || '',
    policyExecutionReason: policyExecution.reason || '',
    policyExecutionRiskBudgetScale: Number((policyExecution.riskBudgetScale || 1).toFixed(2)),
    peopleFragilityLabel: peopleFragility.label || 'stable',
    peopleFragilityScore: peopleFragility.score || 0,
    peopleFragilityFocus: peopleFragility.companyName || '',
    peopleFragilityReason: peopleFragility.reason || '',
    peopleFragilityRiskBudgetScale: Number((peopleFragility.riskBudgetScale || 1).toFixed(2)),
    structuralDecayRadarLabel: structuralDecayRadar.label || 'stable',
    structuralDecayRadarDisplayLabel: structuralDecayRadar.displayLabel || '',
    structuralDecayRadarScore: structuralDecayRadar.score || 0,
    structuralDecayRadarActionHint: structuralDecayRadar.actionHint || '',
    structuralDecayRadarRiskBudgetScale: Number((structuralDecayRadar.riskBudgetScale || 1).toFixed(2)),
    structuralDecayRadarTopSignals: structuralDecayRadar.topSignals || [],
    sourceModeLabel: sourceModeMeta.label || 'mixed',
    sourceModeDominant: sourceModeMeta.dominant || '',
    sourceModeReason: sourceModeMeta.reason || '',
    sourceModeRiskBudgetScale: Number((sourceModeMeta.riskBudgetScale || 1).toFixed(2)),
  };
};

export const buildCrossMarketCards = (payload = {}, overview = {}, snapshot = {}, buildAction = null) => {
  const templates = payload?.templates || [];
  const factorLookup = buildFactorLookup(overview);
  const dimensionLookup = buildDimensionLookup(snapshot);
  const supplyAlerts = snapshot?.signals?.supply_chain?.alerts || [];
  const signalContext = buildSignalContext(overview, snapshot);
  const resonanceMeta = buildResonanceMeta(overview);
  const policySourceHealth = buildPolicySourceHealthMeta(overview);
  const inputReliability = buildInputReliabilityMeta(overview);
  const departmentChaos = buildDepartmentChaosMeta(overview);
  const policyExecution = buildPolicyExecutionMeta(overview);
  const peopleFragility = buildPeopleFragilityMeta(overview);
  const structuralDecayRadar = buildStructuralDecayRadarMeta(overview);
  const sourceModeMeta = buildSourceModeMeta(overview, snapshot);

  return templates
    .map((template) => {
      const longCount = template.assets.filter((asset) => asset.side === 'long').length;
      const shortCount = template.assets.filter((asset) => asset.side === 'short').length;
      const matchedDrivers = [];
      let recommendationScore = 0;

      (template.linked_factors || []).forEach((factorName) => {
        const factor = factorLookup[factorName];
        if (!factor) {
          return;
        }
        const strength = Math.abs(Number(factor.z_score || factor.value || 0));
        if (strength < 0.2 && !factor.signal) {
          return;
        }
        recommendationScore += Math.max(0.4, strength);
        matchedDrivers.push({
          key: `factor-${factorName}`,
          label: formatFactorName(factorName),
          detail: `z=${Number(factor.z_score || 0).toFixed(2)}`,
          type: 'factor',
        });
      });

      (template.linked_dimensions || []).forEach((dimensionName) => {
        const dimension = dimensionLookup[dimensionName];
        if (!dimension) {
          return;
        }
        const strength = Math.abs(Number(dimension.score || 0));
        if (strength < 0.18) {
          return;
        }
        recommendationScore += Math.max(0.25, strength);
        matchedDrivers.push({
          key: `dimension-${dimensionName}`,
          label: DIMENSION_META[dimensionName]?.label || dimensionName,
          detail: `score=${Number(dimension.score || 0).toFixed(2)}`,
          type: 'dimension',
        });
      });

      if ((template.linked_dimensions || []).includes('policy_execution') && policyExecution.watch) {
        recommendationScore += policyExecution.active ? 0.32 : 0.14;
        matchedDrivers.push({
          key: `policy-execution-dimension-${template.id}`,
          label: `政策执行 ${policyExecution.topDepartmentLabel || policyExecution.label}`,
          detail: policyExecution.reason || `score=${policyExecution.score.toFixed(2)}`,
          type: 'quality',
        });
      }
      if ((template.linked_dimensions || []).includes('people_layer') && peopleFragility.watch) {
        recommendationScore += peopleFragility.active ? 0.28 : 0.12;
        matchedDrivers.push({
          key: `people-layer-dimension-${template.id}`,
          label: `人的维度 ${peopleFragility.companyName || peopleFragility.label}`,
          detail: peopleFragility.reason || `fragility=${peopleFragility.score.toFixed(2)}`,
          type: 'quality',
        });
      }
      if ((template.linked_dimensions || []).includes('source_mode_summary')) {
        if (sourceModeMeta.active) {
          recommendationScore = Math.max(0, recommendationScore - 0.18);
          matchedDrivers.push({
            key: `source-mode-dimension-${template.id}`,
            label: '来源治理回退',
            detail: sourceModeMeta.reason,
            type: 'quality',
          });
        } else if (sourceModeMeta.label === 'official-led') {
          recommendationScore += 0.06;
          matchedDrivers.push({
            key: `source-mode-dimension-${template.id}`,
            label: '来源治理稳健',
            detail: sourceModeMeta.reason,
            type: 'quality',
          });
        }
      }

      const linkedFactors = template.linked_factors || [];
      const resonanceMatches = {
        positive: linkedFactors.filter((factorName) => resonanceMeta.positive.has(factorName)),
        negative: linkedFactors.filter((factorName) => resonanceMeta.negative.has(factorName)),
        weakening: linkedFactors.filter((factorName) => resonanceMeta.weakening.has(factorName)),
        precursor: linkedFactors.filter((factorName) => resonanceMeta.precursor.has(factorName)),
        reversed: linkedFactors.filter((factorName) => resonanceMeta.reversed.has(factorName)),
      };

      if (resonanceMatches.positive.length) {
        recommendationScore += resonanceMatches.positive.length * 0.55;
        matchedDrivers.push({
          key: `resonance-positive-${template.id}`,
          label: `正向共振 ${resonanceMatches.positive.map((name) => formatFactorName(name)).join('、')}`,
          detail: resonanceMeta.reason || '多个因子同步强化',
          type: 'resonance',
        });
      }
      if (resonanceMatches.negative.length && template.preferred_signal !== 'positive') {
        recommendationScore += resonanceMatches.negative.length * 0.45;
        matchedDrivers.push({
          key: `resonance-negative-${template.id}`,
          label: `负向共振 ${resonanceMatches.negative.map((name) => formatFactorName(name)).join('、')}`,
          detail: resonanceMeta.reason || '多个因子同步走弱',
          type: 'resonance',
        });
      }
      if (resonanceMatches.precursor.length || resonanceMatches.reversed.length) {
        recommendationScore += 0.2;
        matchedDrivers.push({
          key: `resonance-turn-${template.id}`,
          label: `叙事临界 ${[
            ...resonanceMatches.precursor.map((name) => formatFactorName(name)),
            ...resonanceMatches.reversed.map((name) => formatFactorName(name)),
          ].join('、')}`,
          detail: resonanceMeta.reason || '相关因子进入反转临界区',
          type: 'resonance',
        });
      }
      if (resonanceMatches.weakening.length) {
        recommendationScore = Math.max(0, recommendationScore - Math.min(0.25, resonanceMatches.weakening.length * 0.1));
      }

      if ((template.linked_dimensions || []).includes('talent_structure') && supplyAlerts.length) {
        recommendationScore += Math.min(0.9, supplyAlerts.length * 0.25);
        matchedDrivers.push({
          key: 'supply-alerts',
          label: `供应链预警 ${supplyAlerts.length} 条`,
          detail: '人才结构与执行质量出现扰动',
          type: 'alert',
        });
      }

      if (template.preferred_signal === 'positive' && overview?.macro_signal === 1) {
        recommendationScore += 0.25;
      }

      if (policySourceHealth.label === 'fragile') {
        recommendationScore = Math.max(0, recommendationScore - 0.35);
        matchedDrivers.push({
          key: `policy-source-${template.id}`,
          label: `政策源退化 ${policySourceHealth.fragileSources.slice(0, 2).join('、') || 'fragile'}`,
          detail: policySourceHealth.reason || '政策正文抓取质量下降，推荐级别需打折',
          type: 'quality',
        });
      } else if (policySourceHealth.label === 'watch') {
        recommendationScore = Math.max(0, recommendationScore - 0.18);
        matchedDrivers.push({
          key: `policy-source-${template.id}`,
          label: '政策源需关注',
          detail: policySourceHealth.reason || '政策正文覆盖下降，推荐级别适度打折',
          type: 'quality',
        });
      } else if (policySourceHealth.label === 'healthy') {
        recommendationScore += 0.06;
      }

      if (inputReliability.label === 'fragile') {
        recommendationScore = Math.max(0, recommendationScore - 0.28);
        matchedDrivers.push({
          key: `input-reliability-${template.id}`,
          label: '输入可靠度偏脆弱',
          detail: inputReliability.lead || inputReliability.reason || '宏观输入质量整体偏脆弱，模板排序继续下调',
          type: 'quality',
        });
      } else if (inputReliability.label === 'watch') {
        recommendationScore = Math.max(0, recommendationScore - 0.14);
        matchedDrivers.push({
          key: `input-reliability-${template.id}`,
          label: '输入可靠度需观察',
          detail: inputReliability.lead || inputReliability.reason || '宏观输入质量存在波动，模板排序适度下调',
          type: 'quality',
        });
      } else if (inputReliability.label === 'robust') {
        recommendationScore += 0.05;
      }

      const linkedToBureaucratic = (template.linked_factors || []).includes('bureaucratic_friction');
      if (departmentChaos.active && linkedToBureaucratic) {
        recommendationScore += 0.34;
        matchedDrivers.push({
          key: `department-chaos-${template.id}`,
          label: `部门混乱 ${departmentChaos.topDepartmentLabel || departmentChaos.label}`,
          detail: departmentChaos.topDepartmentReason || departmentChaos.summary || `chaos=${departmentChaos.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (departmentChaos.watch && linkedToBureaucratic) {
        recommendationScore += 0.14;
        matchedDrivers.push({
          key: `department-chaos-${template.id}`,
          label: '部门混乱观察',
          detail: departmentChaos.topDepartmentReason || departmentChaos.summary || `chaos=${departmentChaos.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (departmentChaos.active) {
        recommendationScore = Math.max(0, recommendationScore - 0.08);
      }

      const linkedToPolicyExecution =
        (template.linked_factors || []).includes('policy_execution_disorder')
        || (template.linked_dimensions || []).includes('policy_execution');
      if (policyExecution.active && linkedToPolicyExecution) {
        recommendationScore += 0.34;
        matchedDrivers.push({
          key: `policy-execution-${template.id}`,
          label: `政策执行 ${policyExecution.topDepartmentLabel || policyExecution.label}`,
          detail: policyExecution.reason || `score=${policyExecution.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (policyExecution.watch && linkedToPolicyExecution) {
        recommendationScore += 0.14;
        matchedDrivers.push({
          key: `policy-execution-${template.id}`,
          label: '政策执行观察',
          detail: policyExecution.reason || `score=${policyExecution.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (policyExecution.active) {
        recommendationScore = Math.max(0, recommendationScore - 0.06);
      }

      const linkedToPeopleLayer =
        (template.linked_factors || []).includes('tech_dilution')
        || (template.linked_dimensions || []).includes('talent_structure');
      if (peopleFragility.active && linkedToPeopleLayer) {
        recommendationScore += 0.32;
        matchedDrivers.push({
          key: `people-fragility-${template.id}`,
          label: `组织脆弱 ${peopleFragility.companyName || peopleFragility.label}`,
          detail: peopleFragility.reason || peopleFragility.summary || `fragility=${peopleFragility.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (peopleFragility.watch && linkedToPeopleLayer) {
        recommendationScore += 0.13;
        matchedDrivers.push({
          key: `people-fragility-${template.id}`,
          label: '组织脆弱观察',
          detail: peopleFragility.reason || peopleFragility.summary || `fragility=${peopleFragility.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (peopleFragility.active) {
        recommendationScore = Math.max(0, recommendationScore - 0.06);
      }

      const linkedToStructuralDecay =
        template.id === 'defensive_beta_hedge'
        || template.id === 'utilities_vs_growth'
        || (template.linked_factors || []).some((factorName) =>
          ['tech_dilution', 'bureaucratic_friction', 'baseload_mismatch', 'credit_spread_stress'].includes(factorName)
        )
        || (template.assets || []).some((asset) => DEFENSIVE_LONG_SYMBOLS.has(String(asset.symbol || '').toUpperCase()))
        || (template.assets || []).some((asset) => GROWTH_SHORT_SYMBOLS.has(String(asset.symbol || '').toUpperCase()));
      if (structuralDecayRadar.active && linkedToStructuralDecay) {
        recommendationScore += 0.36;
        matchedDrivers.push({
          key: `structural-decay-radar-${template.id}`,
          label: structuralDecayRadar.displayLabel || '结构衰败雷达',
          detail: structuralDecayRadar.actionHint || `decay=${structuralDecayRadar.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (structuralDecayRadar.watch && linkedToStructuralDecay) {
        recommendationScore += 0.16;
        matchedDrivers.push({
          key: `structural-decay-radar-${template.id}`,
          label: '结构衰败观察',
          detail: structuralDecayRadar.actionHint || `decay=${structuralDecayRadar.score.toFixed(2)}`,
          type: 'quality',
        });
      } else if (structuralDecayRadar.active) {
        recommendationScore = Math.max(0, recommendationScore - 0.08);
      }

      const roundedScore = Number(recommendationScore.toFixed(2));
      const recommendationTier = buildRecommendationTier(roundedScore);
      const biasQuality = buildBiasQualityMeta(
        policySourceHealth,
        inputReliability,
        departmentChaos,
        peopleFragility,
        structuralDecayRadar,
        sourceModeMeta
      );
      const allocationBias = buildAdjustedAssets(
        template,
        signalContext,
        biasQuality,
        departmentChaos,
        peopleFragility,
        structuralDecayRadar,
        policyExecution,
        sourceModeMeta
      );
      const prioritizedDrivers = [...matchedDrivers].sort((a, b) => {
        const priority = { resonance: 0, quality: 1, factor: 2, alert: 3, dimension: 4 };
        return (priority[a.type] ?? 9) - (priority[b.type] ?? 9);
      });
      const driverHeadline = matchedDrivers.length
        ? prioritizedDrivers
            .slice(0, 3)
            .map((item) => `${item.label}(${item.detail})`)
            .join(' · ')
        : '当前模板更多作为备用情景模板，可结合手动研究继续验证';

      const actionNote = `${template.name} 的推荐依据：${driverHeadline}。${template.narrative || template.description}`;

      return {
        ...template,
        longCount,
        shortCount,
        stance: longCount >= shortCount ? '偏防守/资源端' : '偏对冲/做空端',
        recommendationScore: roundedScore,
        recommendationTier,
        recommendationTone: buildRecommendationTone(roundedScore),
        matchedDrivers: prioritizedDrivers.slice(0, 4),
        driverHeadline,
        resonanceLabel: resonanceMeta.label,
        resonanceReason: resonanceMeta.reason,
        resonanceFactors: resonanceMatches,
        policySourceHealthLabel: policySourceHealth.label,
        policySourceHealthReason: policySourceHealth.reason,
        inputReliabilityLabel: inputReliability.label,
        inputReliabilityScore: inputReliability.score,
        inputReliabilityLead: inputReliability.lead,
        inputReliabilityPosture: inputReliability.posture,
        inputReliabilityReason: inputReliability.reason,
        sourceModeLabel: allocationBias.sourceModeLabel,
        sourceModeDominant: allocationBias.sourceModeDominant,
        sourceModeReason: allocationBias.sourceModeReason,
        sourceModeRiskBudgetScale: allocationBias.sourceModeRiskBudgetScale,
        policyExecutionLabel: allocationBias.policyExecutionLabel,
        policyExecutionScore: allocationBias.policyExecutionScore,
        policyExecutionTopDepartment: allocationBias.policyExecutionTopDepartment,
        policyExecutionReason: allocationBias.policyExecutionReason,
        policyExecutionRiskBudgetScale: allocationBias.policyExecutionRiskBudgetScale,
        adjustedAssets: allocationBias.adjustedAssets,
        rawAdjustedAssets: allocationBias.rawAdjustedAssets,
        biasSummary: allocationBias.biasSummary,
        rawBiasStrength: allocationBias.rawBiasStrength,
        biasStrength: allocationBias.biasStrength,
        biasScale: allocationBias.biasScale,
        biasQualityLabel: allocationBias.biasQualityLabel,
        biasQualityReason: allocationBias.biasQualityReason,
        biasHighlights: allocationBias.biasHighlights,
        biasActions: allocationBias.biasActions,
        signalAttribution: allocationBias.signalAttribution,
        driverSummary: allocationBias.driverSummary,
        dominantDrivers: allocationBias.dominantDrivers,
        coreLegs: allocationBias.coreLegs,
        supportLegs: allocationBias.supportLegs,
        themeCore: template.theme_core || allocationBias.themeCore || '',
        themeSupport: (Array.isArray(template.theme_support) ? template.theme_support.join('、') : template.theme_support) || allocationBias.themeSupport || '',
        executionPosture: template.execution_posture || '',
        departmentChaosLabel: allocationBias.departmentChaosLabel,
        departmentChaosScore: allocationBias.departmentChaosScore,
        departmentChaosTopDepartment: allocationBias.departmentChaosTopDepartment,
        departmentChaosReason: allocationBias.departmentChaosReason,
        departmentChaosRiskBudgetScale: allocationBias.departmentChaosRiskBudgetScale,
        peopleFragilityLabel: allocationBias.peopleFragilityLabel,
        peopleFragilityScore: allocationBias.peopleFragilityScore,
        peopleFragilityFocus: allocationBias.peopleFragilityFocus,
        peopleFragilityReason: allocationBias.peopleFragilityReason,
        peopleFragilityRiskBudgetScale: allocationBias.peopleFragilityRiskBudgetScale,
        structuralDecayRadarLabel: allocationBias.structuralDecayRadarLabel,
        structuralDecayRadarDisplayLabel: allocationBias.structuralDecayRadarDisplayLabel,
        structuralDecayRadarScore: allocationBias.structuralDecayRadarScore,
        structuralDecayRadarActionHint: allocationBias.structuralDecayRadarActionHint,
        structuralDecayRadarRiskBudgetScale: allocationBias.structuralDecayRadarRiskBudgetScale,
        structuralDecayRadarTopSignals: allocationBias.structuralDecayRadarTopSignals,
        action: buildAction ? buildAction(template.id, actionNote) : null,
      };
    })
    .sort((a, b) => b.recommendationScore - a.recommendationScore);
};
