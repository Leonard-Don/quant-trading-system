import { getPriceSourceLabel } from '../../utils/pricingResearch';

const formatNumber = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return numeric.toFixed(digits);
};

const formatPercent = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return `${(numeric * 100).toFixed(digits)}%`;
};

const formatPercentPoints = (value, digits = 2) => {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return `${numeric.toFixed(digits)}%`;
};

const formatSignedDelta = (left, right, formatter = formatNumber) => {
  if (left === null || left === undefined || right === null || right === undefined) {
    return null;
  }
  const leftNumeric = Number(left);
  const rightNumeric = Number(right);
  if (Number.isNaN(leftNumeric) || Number.isNaN(rightNumeric)) {
    return null;
  }
  const delta = rightNumeric - leftNumeric;
  const prefix = delta > 0 ? '+' : '';
  return `${prefix}${formatter(delta)}`;
};

const buildDriverLookup = (items = []) =>
  Object.fromEntries((items || []).map((item) => [item.key, item]));

const buildDriverTrendRows = (baseDrivers = [], targetDrivers = []) => {
  const baseLookup = buildDriverLookup(baseDrivers);
  const targetLookup = buildDriverLookup(targetDrivers);
  const keys = Array.from(new Set([...Object.keys(baseLookup), ...Object.keys(targetLookup)]));

  return keys
    .map((key) => {
      const left = Number(baseLookup[key]?.value || 0);
      const right = Number(targetLookup[key]?.value || 0);
      return {
        key: `driver-${key}`,
        label: `Driver: ${targetLookup[key]?.label || baseLookup[key]?.label || key}`,
        left: formatNumber(left),
        right: formatNumber(right),
        delta: formatSignedDelta(left, right, (value) => formatNumber(value)),
        magnitude: Math.abs(right - left),
      };
    })
    .sort((a, b) => b.magnitude - a.magnitude)
    .slice(0, 3)
    .map(({ magnitude, ...row }) => row);
};

const getSelectionQualitySummaryLabel = (label) => {
  if (!label || label === '-') {
    return '未知结果';
  }
  if (label === 'original') {
    return '普通结果';
  }
  return '复核型结果';
};

const buildSelectionQualitySummary = (base, target) => {
  const baseLabel = getSelectionQualitySummaryLabel(base.selectionQualityLabel);
  const targetLabel = getSelectionQualitySummaryLabel(target.selectionQualityLabel);

  if (base.selectionQualityLabel === target.selectionQualityLabel) {
    return `结果语境 ${baseLabel}`;
  }

  return `结果语境 ${baseLabel} -> ${targetLabel}`;
};

const buildSelectionQualityStateSummary = (base, target) => {
  const baseLabel = base.selectionQualityLabel || '-';
  const targetLabel = target.selectionQualityLabel || '-';

  if (baseLabel === targetLabel) {
    return `运行强度 ${baseLabel}`;
  }

  return `运行强度 ${baseLabel} -> ${targetLabel}`;
};

const buildSelectionQualityLead = (base, target) => {
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

const extractPricingMetrics = (snapshot) => {
  const payload = snapshot?.payload || {};
  const fairValue = payload.fair_value || {};
  const implications = payload.implications || {};
  const drivers = payload.drivers || [];
  const primaryDriver = payload.primary_driver || drivers[0] || {};
  const factorModel = payload.factor_model || {};
  const dcfScenarios = payload.dcf_scenarios || [];
  const bearCase = dcfScenarios.find((item) => item?.name === 'bear') || dcfScenarios[0] || null;
  const bullCase = dcfScenarios.find((item) => item?.name === 'bull') || dcfScenarios[dcfScenarios.length - 1] || null;
  const scenarioSpread = bearCase?.intrinsic_value != null && bullCase?.intrinsic_value != null
    ? Number(bullCase.intrinsic_value) - Number(bearCase.intrinsic_value)
    : null;
  return {
    fairValueMid: fairValue.mid ?? payload.gap_analysis?.fair_value_mid ?? null,
    fairValueLow: fairValue.low ?? bearCase?.intrinsic_value ?? null,
    fairValueHigh: fairValue.high ?? bullCase?.intrinsic_value ?? null,
    gapPct: payload.gap_analysis?.gap_pct ?? null,
    analysisPeriod: payload.period || factorModel.period || '-',
    currentPriceSource: getPriceSourceLabel(payload.current_price_source || ''),
    factorDataPoints: factorModel.data_points ?? null,
    primaryView: implications.primary_view || '-',
    alignmentLabel: implications.factor_alignment?.label || '-',
    driverHeadline: primaryDriver.factor || primaryDriver.name || '-',
    confidence: implications.confidence || '-',
    confidenceScore: implications.confidence_score ?? null,
    scenarioSpread,
    ff5Alpha: factorModel.ff5_alpha_pct ?? null,
    profitability: factorModel.ff5_profitability ?? null,
    investment: factorModel.ff5_investment ?? null,
    monteCarloMedian: payload.monte_carlo?.p50 ?? payload.monte_carlo?.median ?? null,
    monteCarloP90: payload.monte_carlo?.p90 ?? null,
    auditPriceSource: payload.audit_trail?.price_source || payload.current_price_source || '',
    auditBenchmarkSource: payload.audit_trail?.comparable_benchmark_source || payload.comparable?.benchmark_source || '-',
  };
};

const extractCrossMarketMetrics = (snapshot) => {
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
    inputReliability: researchInput.macro?.input_reliability?.label || '-',
    inputReliabilityScore: researchInput.macro?.input_reliability?.score ?? null,
    inputReliabilityLead: researchInput.macro?.input_reliability?.lead || '-',
    inputReliabilityPosture: inputReliabilityOverlay.posture || researchInput.macro?.input_reliability?.posture || '-',
    inputReliabilityActionHint: inputReliabilityOverlay.action_hint || templateMeta.input_reliability?.action_hint || '-',
    altTrendHeadline: (researchInput.alt_data?.top_categories || [])
      .slice(0, 2)
      .map((item) => `${item.category}:${item.momentum}`)
      .join(', ') || '-',
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
    biasStrengthEffective: templateMeta.bias_strength ?? null,
    biasCompressionEffect: overlay.bias_compression_effect ?? null,
    biasCompressionRatio: overlay.compression_summary?.compression_ratio ?? null,
    compressedAssets: (overlay.compressed_assets || []).join(', ') || '-',
    topCompressedAsset: (overlay.rows || [])
      .slice()
      .sort((left, right) => Math.abs(Number(right.compression_delta || 0)) - Math.abs(Number(left.compression_delta || 0)))
      .map((item) =>
        Math.abs(Number(item.compression_delta || 0)) >= 0.005
          ? `${item.symbol} ${(Math.abs(Number(item.compression_delta || 0)) * 100).toFixed(2)}pp`
          : null
      )
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
    constructionMode: execution.construction_mode || payload.template?.construction_mode || '-',
  };
};

export const buildSnapshotComparison = (taskType, baseSnapshot, targetSnapshot) => {
  if (!baseSnapshot || !targetSnapshot) {
    return null;
  }

  if (taskType === 'pricing') {
    const base = extractPricingMetrics(baseSnapshot);
    const target = extractPricingMetrics(targetSnapshot);
    return {
      summary: [
        `视角 ${base.primaryView} -> ${target.primaryView}`,
        `主驱动 ${base.driverHeadline} -> ${target.driverHeadline}`,
        `情景区间 ${formatNumber(base.fairValueLow)}-${formatNumber(base.fairValueHigh)} -> ${formatNumber(target.fairValueLow)}-${formatNumber(target.fairValueHigh)}`,
      ],
      rows: [
        {
          key: 'fair-value',
          label: 'Fair Value',
          left: formatNumber(base.fairValueMid),
          right: formatNumber(target.fairValueMid),
          delta: formatSignedDelta(base.fairValueMid, target.fairValueMid, (value) => formatNumber(value)),
        },
        {
          key: 'fair-value-bear',
          label: 'Bear Case',
          left: formatNumber(base.fairValueLow),
          right: formatNumber(target.fairValueLow),
          delta: formatSignedDelta(base.fairValueLow, target.fairValueLow, (value) => formatNumber(value)),
        },
        {
          key: 'fair-value-bull',
          label: 'Bull Case',
          left: formatNumber(base.fairValueHigh),
          right: formatNumber(target.fairValueHigh),
          delta: formatSignedDelta(base.fairValueHigh, target.fairValueHigh, (value) => formatNumber(value)),
        },
        {
          key: 'scenario-spread',
          label: 'Scenario Spread',
          left: formatNumber(base.scenarioSpread),
          right: formatNumber(target.scenarioSpread),
          delta: formatSignedDelta(base.scenarioSpread, target.scenarioSpread, (value) => formatNumber(value)),
        },
        {
          key: 'gap-pct',
          label: 'Gap',
          left: formatPercentPoints(base.gapPct),
          right: formatPercentPoints(target.gapPct),
          delta: formatSignedDelta(base.gapPct, target.gapPct, (value) => formatPercentPoints(value)),
        },
        {
          key: 'primary-view',
          label: 'Primary View',
          left: base.primaryView,
          right: target.primaryView,
          delta: base.primaryView === target.primaryView ? '不变' : `${base.primaryView} -> ${target.primaryView}`,
        },
        {
          key: 'driver',
          label: 'Top Driver',
          left: base.driverHeadline,
          right: target.driverHeadline,
          delta: base.driverHeadline === target.driverHeadline ? '不变' : '已切换',
        },
        {
          key: 'alignment',
          label: 'Evidence Alignment',
          left: base.alignmentLabel,
          right: target.alignmentLabel,
          delta: base.alignmentLabel === target.alignmentLabel ? '不变' : `${base.alignmentLabel} -> ${target.alignmentLabel}`,
        },
        {
          key: 'analysis-period',
          label: 'Analysis Window',
          left: base.analysisPeriod,
          right: target.analysisPeriod,
          delta: base.analysisPeriod === target.analysisPeriod ? '不变' : `${base.analysisPeriod} -> ${target.analysisPeriod}`,
        },
        {
          key: 'price-source',
          label: 'Price Source',
          left: base.currentPriceSource,
          right: target.currentPriceSource,
          delta: base.currentPriceSource === target.currentPriceSource ? '不变' : `${base.currentPriceSource} -> ${target.currentPriceSource}`,
        },
        {
          key: 'factor-samples',
          label: 'Factor Samples',
          left: formatNumber(base.factorDataPoints, 0),
          right: formatNumber(target.factorDataPoints, 0),
          delta: formatSignedDelta(base.factorDataPoints, target.factorDataPoints, (value) => formatNumber(value, 0)),
        },
        {
          key: 'confidence',
          label: 'Confidence',
          left: base.confidence,
          right: target.confidence,
          delta: base.confidence === target.confidence ? '不变' : `${base.confidence} -> ${target.confidence}`,
        },
        {
          key: 'confidence-score',
          label: 'Confidence Score',
          left: formatNumber(base.confidenceScore),
          right: formatNumber(target.confidenceScore),
          delta: formatSignedDelta(base.confidenceScore, target.confidenceScore, (value) => formatNumber(value)),
        },
        {
          key: 'ff5-alpha',
          label: 'FF5 Alpha',
          left: formatNumber(base.ff5Alpha),
          right: formatNumber(target.ff5Alpha),
          delta: formatSignedDelta(base.ff5Alpha, target.ff5Alpha, (value) => formatNumber(value)),
        },
        {
          key: 'profitability',
          label: 'Profitability',
          left: formatNumber(base.profitability),
          right: formatNumber(target.profitability),
          delta: formatSignedDelta(base.profitability, target.profitability, (value) => formatNumber(value)),
        },
        {
          key: 'investment',
          label: 'Investment',
          left: formatNumber(base.investment),
          right: formatNumber(target.investment),
          delta: formatSignedDelta(base.investment, target.investment, (value) => formatNumber(value)),
        },
        {
          key: 'monte-carlo-median',
          label: 'Monte Carlo P50',
          left: formatNumber(base.monteCarloMedian),
          right: formatNumber(target.monteCarloMedian),
          delta: formatSignedDelta(base.monteCarloMedian, target.monteCarloMedian, (value) => formatNumber(value)),
        },
        {
          key: 'monte-carlo-p90',
          label: 'Monte Carlo P90',
          left: formatNumber(base.monteCarloP90),
          right: formatNumber(target.monteCarloP90),
          delta: formatSignedDelta(base.monteCarloP90, target.monteCarloP90, (value) => formatNumber(value)),
        },
        {
          key: 'benchmark-source',
          label: 'Benchmark Source',
          left: base.auditBenchmarkSource,
          right: target.auditBenchmarkSource,
          delta: base.auditBenchmarkSource === target.auditBenchmarkSource ? '不变' : `${base.auditBenchmarkSource} -> ${target.auditBenchmarkSource}`,
        },
      ],
    };
  }

  const base = extractCrossMarketMetrics(baseSnapshot);
  const target = extractCrossMarketMetrics(targetSnapshot);
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
      {
        key: 'return',
        label: 'Total Return',
        left: formatPercent(base.totalReturn),
        right: formatPercent(target.totalReturn),
        delta: formatSignedDelta(base.totalReturn, target.totalReturn, (value) => formatPercent(value)),
      },
      {
        key: 'sharpe',
        label: 'Sharpe',
        left: formatNumber(base.sharpeRatio),
        right: formatNumber(target.sharpeRatio),
        delta: formatSignedDelta(base.sharpeRatio, target.sharpeRatio, (value) => formatNumber(value)),
      },
      {
        key: 'coverage',
        label: 'Coverage',
        left: formatPercent(base.coverage),
        right: formatPercent(target.coverage),
        delta: formatSignedDelta(base.coverage, target.coverage, (value) => formatPercent(value)),
      },
      {
        key: 'cost-drag',
        label: 'Cost Drag',
        left: formatPercent(base.costDrag),
        right: formatPercent(target.costDrag),
        delta: formatSignedDelta(base.costDrag, target.costDrag, (value) => formatPercent(value)),
      },
      {
        key: 'turnover',
        label: 'Turnover',
        left: formatNumber(base.turnover),
        right: formatNumber(target.turnover),
        delta: formatSignedDelta(base.turnover, target.turnover, (value) => formatNumber(value)),
      },
      {
        key: 'construction',
        label: 'Construction',
        left: base.constructionMode,
        right: target.constructionMode,
        delta: base.constructionMode === target.constructionMode ? '不变' : `${base.constructionMode} -> ${target.constructionMode}`,
      },
      {
        key: 'route-count',
        label: 'Route Count',
        left: formatNumber(base.routeCount, 0),
        right: formatNumber(target.routeCount, 0),
        delta: formatSignedDelta(base.routeCount, target.routeCount, (value) => formatNumber(value, 0)),
      },
      {
        key: 'batch-count',
        label: 'Batch Count',
        left: formatNumber(base.batchCount, 0),
        right: formatNumber(target.batchCount, 0),
        delta: formatSignedDelta(base.batchCount, target.batchCount, (value) => formatNumber(value, 0)),
      },
      {
        key: 'providers',
        label: 'Providers',
        left: base.providerHeadline,
        right: target.providerHeadline,
        delta: base.providerHeadline === target.providerHeadline ? '不变' : '已调整',
      },
      {
        key: 'venues',
        label: 'Venues',
        left: base.venueHeadline,
        right: target.venueHeadline,
        delta: base.venueHeadline === target.venueHeadline ? '不变' : '已调整',
      },
      {
        key: 'max-batch-fraction',
        label: 'Max Batch',
        left: formatPercent(base.maxBatchFraction),
        right: formatPercent(target.maxBatchFraction),
        delta: formatSignedDelta(base.maxBatchFraction, target.maxBatchFraction, (value) => formatPercent(value)),
      },
      {
        key: 'concentration',
        label: 'Concentration',
        left: base.concentrationLevel,
        right: target.concentrationLevel,
        delta: base.concentrationLevel === target.concentrationLevel ? '不变' : `${base.concentrationLevel} -> ${target.concentrationLevel}`,
      },
      {
        key: 'lot-efficiency',
        label: 'Lot Efficiency',
        left: formatPercent(base.lotEfficiency),
        right: formatPercent(target.lotEfficiency),
        delta: formatSignedDelta(base.lotEfficiency, target.lotEfficiency, (value) => formatPercent(value)),
      },
      {
        key: 'liquidity',
        label: 'Liquidity',
        left: base.liquidityLevel,
        right: target.liquidityLevel,
        delta: base.liquidityLevel === target.liquidityLevel ? '不变' : `${base.liquidityLevel} -> ${target.liquidityLevel}`,
      },
      {
        key: 'max-adv-usage',
        label: 'Max ADV Usage',
        left: formatPercent(base.maxAdvUsage),
        right: formatPercent(target.maxAdvUsage),
        delta: formatSignedDelta(base.maxAdvUsage, target.maxAdvUsage, (value) => formatPercent(value)),
      },
      {
        key: 'margin-level',
        label: 'Margin',
        left: base.marginLevel,
        right: target.marginLevel,
        delta: base.marginLevel === target.marginLevel ? '不变' : `${base.marginLevel} -> ${target.marginLevel}`,
      },
      {
        key: 'margin-utilization',
        label: 'Margin Utilization',
        left: formatPercent(base.marginUtilization),
        right: formatPercent(target.marginUtilization),
        delta: formatSignedDelta(base.marginUtilization, target.marginUtilization, (value) => formatPercent(value)),
      },
      {
        key: 'gross-leverage',
        label: 'Gross Leverage',
        left: formatNumber(base.grossLeverage),
        right: formatNumber(target.grossLeverage),
        delta: formatSignedDelta(base.grossLeverage, target.grossLeverage, (value) => formatNumber(value)),
      },
      {
        key: 'beta-level',
        label: 'Beta',
        left: base.betaLevel,
        right: target.betaLevel,
        delta: base.betaLevel === target.betaLevel ? '不变' : `${base.betaLevel} -> ${target.betaLevel}`,
      },
      {
        key: 'beta-value',
        label: 'Beta Value',
        left: formatNumber(base.betaValue),
        right: formatNumber(target.betaValue),
        delta: formatSignedDelta(base.betaValue, target.betaValue, (value) => formatNumber(value)),
      },
      {
        key: 'beta-gap',
        label: 'Beta Gap',
        left: formatNumber(base.betaGap),
        right: formatNumber(target.betaGap),
        delta: formatSignedDelta(base.betaGap, target.betaGap, (value) => formatNumber(value)),
      },
      {
        key: 'calendar-level',
        label: 'Calendar',
        left: base.calendarLevel,
        right: target.calendarLevel,
        delta: base.calendarLevel === target.calendarLevel ? '不变' : `${base.calendarLevel} -> ${target.calendarLevel}`,
      },
      {
        key: 'calendar-mismatch',
        label: 'Calendar Mismatch',
        left: formatPercent(base.calendarMismatch),
        right: formatPercent(target.calendarMismatch),
        delta: formatSignedDelta(base.calendarMismatch, target.calendarMismatch, (value) => formatPercent(value)),
      },
      {
        key: 'macro-score',
        label: 'Macro Score',
        left: formatNumber(base.macroScore),
        right: formatNumber(target.macroScore),
        delta: formatSignedDelta(base.macroScore, target.macroScore, (value) => formatNumber(value)),
      },
      {
        key: 'macro-score-delta',
        label: 'Macro Δ',
        left: formatNumber(base.macroScoreDelta),
        right: formatNumber(target.macroScoreDelta),
        delta: formatSignedDelta(base.macroScoreDelta, target.macroScoreDelta, (value) => formatNumber(value)),
      },
      {
        key: 'macro-signal-changed',
        label: 'Macro Signal Change',
        left: base.macroSignalChanged ? 'yes' : 'no',
        right: target.macroSignalChanged ? 'yes' : 'no',
        delta: base.macroSignalChanged === target.macroSignalChanged ? '不变' : '已切换',
      },
      {
        key: 'macro-resonance',
        label: 'Macro Resonance',
        left: base.macroResonance,
        right: target.macroResonance,
        delta: base.macroResonance === target.macroResonance ? '不变' : `${base.macroResonance} -> ${target.macroResonance}`,
      },
      {
        key: 'policy-source-health',
        label: 'Policy Source',
        left: base.policySourceHealth,
        right: target.policySourceHealth,
        delta: base.policySourceHealth === target.policySourceHealth ? '不变' : `${base.policySourceHealth} -> ${target.policySourceHealth}`,
      },
      {
        key: 'policy-source-ratio',
        label: 'Policy Full Text',
        left: formatPercent(base.policySourceFullTextRatio),
        right: formatPercent(target.policySourceFullTextRatio),
        delta: formatSignedDelta(base.policySourceFullTextRatio, target.policySourceFullTextRatio, (value) => formatPercent(value)),
      },
      {
        key: 'policy-source-reason',
        label: 'Policy Source Reason',
        left: base.policySourceReason,
        right: target.policySourceReason,
        delta: base.policySourceReason === target.policySourceReason ? '不变' : '政策源状态已变化',
      },
      {
        key: 'input-reliability',
        label: 'Input Reliability',
        left: base.inputReliability,
        right: target.inputReliability,
        delta: base.inputReliability === target.inputReliability ? '不变' : `${base.inputReliability} -> ${target.inputReliability}`,
      },
      {
        key: 'input-reliability-score',
        label: 'Input Reliability Score',
        left: formatNumber(base.inputReliabilityScore),
        right: formatNumber(target.inputReliabilityScore),
        delta: formatSignedDelta(base.inputReliabilityScore, target.inputReliabilityScore, (value) => formatNumber(value)),
      },
      {
        key: 'input-reliability-lead',
        label: 'Input Reliability Lead',
        left: base.inputReliabilityLead,
        right: target.inputReliabilityLead,
        delta: base.inputReliabilityLead === target.inputReliabilityLead ? '不变' : '输入可靠度判断已变化',
      },
      {
        key: 'input-reliability-posture',
        label: 'Input Reliability Posture',
        left: base.inputReliabilityPosture,
        right: target.inputReliabilityPosture,
        delta: base.inputReliabilityPosture === target.inputReliabilityPosture ? '不变' : '输入处理姿势已变化',
      },
      {
        key: 'input-reliability-action',
        label: 'Input Reliability Action',
        left: base.inputReliabilityActionHint,
        right: target.inputReliabilityActionHint,
        delta: base.inputReliabilityActionHint === target.inputReliabilityActionHint ? '不变' : '输入复核动作已变化',
      },
      {
        key: 'alt-trend-headline',
        label: 'Alt Trend',
        left: base.altTrendHeadline,
        right: target.altTrendHeadline,
        delta: base.altTrendHeadline === target.altTrendHeadline ? '不变' : '趋势结构已变',
      },
      {
        key: 'rebalance',
        label: 'Rebalance',
        left: base.rebalanceCadence,
        right: target.rebalanceCadence,
        delta: base.rebalanceCadence === target.rebalanceCadence ? '不变' : `${base.rebalanceCadence} -> ${target.rebalanceCadence}`,
      },
      {
        key: 'stress',
        label: 'Stress Flag',
        left: base.stressFlag,
        right: target.stressFlag,
        delta: base.stressFlag === target.stressFlag ? '不变' : `${base.stressFlag} -> ${target.stressFlag}`,
      },
      {
        key: 'recommendation-tier',
        label: 'Recommendation',
        left: base.recommendationTier,
        right: target.recommendationTier,
        delta: base.recommendationTier === target.recommendationTier ? '不变' : `${base.recommendationTier} -> ${target.recommendationTier}`,
      },
      {
        key: 'base-recommendation-score',
        label: 'Base Recommendation',
        left: formatNumber(base.baseRecommendationScore),
        right: formatNumber(target.baseRecommendationScore),
        delta: formatSignedDelta(base.baseRecommendationScore, target.baseRecommendationScore, (value) => formatNumber(value)),
      },
      {
        key: 'effective-recommendation-score',
        label: 'Effective Recommendation',
        left: formatNumber(base.recommendationScore),
        right: formatNumber(target.recommendationScore),
        delta: formatSignedDelta(base.recommendationScore, target.recommendationScore, (value) => formatNumber(value)),
      },
      {
        key: 'base-recommendation-tier',
        label: 'Base Tier',
        left: base.baseRecommendationTier,
        right: target.baseRecommendationTier,
        delta: base.baseRecommendationTier === target.baseRecommendationTier ? '不变' : `${base.baseRecommendationTier} -> ${target.baseRecommendationTier}`,
      },
      {
        key: 'ranking-penalty',
        label: 'Ranking Penalty',
        left: formatNumber(base.rankingPenalty),
        right: formatNumber(target.rankingPenalty),
        delta: formatSignedDelta(base.rankingPenalty, target.rankingPenalty, (value) => formatNumber(value)),
      },
      {
        key: 'selection-quality',
        label: 'Selection Quality',
        left: base.selectionQualityLabel,
        right: target.selectionQualityLabel,
        delta: base.selectionQualityLabel === target.selectionQualityLabel ? '不变' : `${base.selectionQualityLabel} -> ${target.selectionQualityLabel}`,
      },
      {
        key: 'selection-quality-reason',
        label: 'Selection Quality Reason',
        left: base.selectionQualityReason,
        right: target.selectionQualityReason,
        delta: base.selectionQualityReason === target.selectionQualityReason ? '不变' : '自动降级原因已变化',
      },
      {
        key: 'ranking-penalty-reason',
        label: 'Ranking Penalty Reason',
        left: base.rankingPenaltyReason,
        right: target.rankingPenaltyReason,
        delta: base.rankingPenaltyReason === target.rankingPenaltyReason ? '不变' : '排序惩罚原因已变化',
      },
      {
        key: 'theme',
        label: 'Theme',
        left: base.theme,
        right: target.theme,
        delta: base.theme === target.theme ? '不变' : '已切换',
      },
      {
        key: 'resonance-reason',
        label: 'Resonance Reason',
        left: base.resonanceReason,
        right: target.resonanceReason,
        delta: base.resonanceReason === target.resonanceReason ? '不变' : '共振背景已变化',
      },
      {
        key: 'dominant-driver',
        label: 'Dominant Driver',
        left: base.dominantDriverHeadline,
        right: target.dominantDriverHeadline,
        delta: base.dominantDriverHeadline === target.dominantDriverHeadline ? '不变' : '主导叙事已切换',
      },
      {
        key: 'theme-core',
        label: 'Theme Core',
        left: base.themeCore,
        right: target.themeCore,
        delta: base.themeCore === target.themeCore ? '不变' : '核心腿已切换',
      },
      {
        key: 'theme-support',
        label: 'Theme Support',
        left: base.themeSupport,
        right: target.themeSupport,
        delta: base.themeSupport === target.themeSupport ? '不变' : '辅助腿已调整',
      },
      {
        key: 'allocation-mode',
        label: 'Allocation Mode',
        left: base.allocationMode,
        right: target.allocationMode,
        delta: base.allocationMode === target.allocationMode ? '不变' : `${base.allocationMode} -> ${target.allocationMode}`,
      },
      {
        key: 'bias-strength-raw',
        label: 'Bias Raw',
        left: formatNumber(base.biasStrengthRaw),
        right: formatNumber(target.biasStrengthRaw),
        delta: formatSignedDelta(base.biasStrengthRaw, target.biasStrengthRaw, (value) => formatNumber(value)),
      },
      {
        key: 'bias-strength-effective',
        label: 'Bias Effective',
        left: formatNumber(base.biasStrengthEffective),
        right: formatNumber(target.biasStrengthEffective),
        delta: formatSignedDelta(base.biasStrengthEffective, target.biasStrengthEffective, (value) => formatNumber(value)),
      },
      {
        key: 'bias-summary',
        label: 'Bias Summary',
        left: base.biasSummary,
        right: target.biasSummary,
        delta: base.biasSummary === target.biasSummary ? '不变' : '已调整',
      },
      {
        key: 'bias-scale',
        label: 'Bias Scale',
        left: formatNumber(base.biasScale),
        right: formatNumber(target.biasScale),
        delta: formatSignedDelta(base.biasScale, target.biasScale, (value) => formatNumber(value)),
      },
      {
        key: 'bias-quality-label',
        label: 'Bias Quality',
        left: base.biasQualityLabel,
        right: target.biasQualityLabel,
        delta: base.biasQualityLabel === target.biasQualityLabel ? '不变' : `${base.biasQualityLabel} -> ${target.biasQualityLabel}`,
      },
      {
        key: 'bias-quality-reason',
        label: 'Bias Quality Reason',
        left: base.biasQualityReason,
        right: target.biasQualityReason,
        delta: base.biasQualityReason === target.biasQualityReason ? '不变' : '偏置质量已变化',
      },
      {
        key: 'bias-compression-effect',
        label: 'Bias Compression',
        left: formatNumber(base.biasCompressionEffect),
        right: formatNumber(target.biasCompressionEffect),
        delta: formatSignedDelta(base.biasCompressionEffect, target.biasCompressionEffect, (value) => formatNumber(value)),
      },
      {
        key: 'bias-compression-ratio',
        label: 'Bias Compression Ratio',
        left: formatPercent(base.biasCompressionRatio),
        right: formatPercent(target.biasCompressionRatio),
        delta: formatSignedDelta(base.biasCompressionRatio, target.biasCompressionRatio, (value) => formatPercent(value)),
      },
      {
        key: 'compressed-assets',
        label: 'Compressed Assets',
        left: base.compressedAssets,
        right: target.compressedAssets,
        delta: base.compressedAssets === target.compressedAssets ? '不变' : '受影响资产已变化',
      },
      {
        key: 'top-compressed-asset',
        label: 'Top Compressed',
        left: base.topCompressedAsset,
        right: target.topCompressedAsset,
        delta: base.topCompressedAsset === target.topCompressedAsset ? '不变' : '压缩焦点已切换',
      },
      {
        key: 'core-leg-pressure',
        label: 'Core Leg Pressure',
        left: base.coreLegPressure,
        right: target.coreLegPressure,
        delta: base.coreLegPressure === target.coreLegPressure ? '不变' : '核心腿状态已切换',
      },
      {
        key: 'core-leg-pressure-summary',
        label: 'Core Leg Focus',
        left: base.coreLegPressureSummary,
        right: target.coreLegPressureSummary,
        delta: base.coreLegPressureSummary === target.coreLegPressureSummary ? '不变' : '核心腿压缩焦点已变化',
      },
      {
        key: 'max-delta-weight',
        label: 'Max Weight Shift',
        left: formatPercent(base.maxDeltaWeight),
        right: formatPercent(target.maxDeltaWeight),
        delta: formatSignedDelta(base.maxDeltaWeight, target.maxDeltaWeight, (value) => formatPercent(value)),
      },
      {
        key: 'constraint-binding-count',
        label: 'Constraint Bindings',
        left: formatNumber(base.constraintBindingCount, 0),
        right: formatNumber(target.constraintBindingCount, 0),
        delta: formatSignedDelta(base.constraintBindingCount, target.constraintBindingCount, (value) => formatNumber(value, 0)),
      },
      {
        key: 'constraint-max-shift',
        label: 'Constraint Shift',
        left: formatPercent(base.constraintMaxDeltaWeight),
        right: formatPercent(target.constraintMaxDeltaWeight),
        delta: formatSignedDelta(base.constraintMaxDeltaWeight, target.constraintMaxDeltaWeight, (value) => formatPercent(value)),
      },
      ...driverTrendRows,
    ],
  };
};
