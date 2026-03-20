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

const extractPricingMetrics = (snapshot) => {
  const payload = snapshot?.payload || {};
  const fairValue = payload.fair_value || {};
  const implications = payload.implications || {};
  const drivers = payload.drivers || [];
  return {
    fairValueMid: fairValue.mid ?? payload.gap_analysis?.fair_value_mid ?? null,
    gapPct: payload.gap_analysis?.gap_pct ?? null,
    primaryView: implications.primary_view || '-',
    driverHeadline: drivers[0]?.factor || drivers[0]?.name || '-',
    confidence: implications.confidence || '-',
  };
};

const extractCrossMarketMetrics = (snapshot) => {
  const payload = snapshot?.payload || {};
  const execution = payload.execution_diagnostics || {};
  const executionPlan = payload.execution_plan || {};
  const templateMeta = payload.template_meta || {};
  const alignment = payload.data_alignment || {};
  const overlay = payload.allocation_overlay || {};
  return {
    totalReturn: payload.total_return ?? null,
    sharpeRatio: payload.sharpe_ratio ?? null,
    coverage: alignment.tradable_day_ratio ?? null,
    costDrag: execution.cost_drag ?? null,
    turnover: execution.turnover ?? null,
    concentrationLevel: execution.concentration_level || '-',
    concentrationReason: execution.concentration_reason || '-',
    lotEfficiency: execution.lot_efficiency ?? null,
    rebalanceCadence: execution.suggested_rebalance || '-',
    stressFlag: execution.stress_test_flag || '-',
    routeCount: executionPlan.route_count ?? null,
    batchCount: Array.isArray(executionPlan.batches) ? executionPlan.batches.length : null,
    providerHeadline: Object.keys(executionPlan.by_provider || {}).join(', ') || '-',
    venueHeadline: (executionPlan.venue_allocation || []).map((item) => item.key).join(', ') || '-',
    maxBatchFraction: execution.max_batch_fraction ?? executionPlan.max_batch_fraction ?? null,
    recommendationTier: templateMeta.recommendation_tier || '-',
    theme: templateMeta.theme || '-',
    allocationMode: templateMeta.allocation_mode || '-',
    biasSummary: templateMeta.bias_summary || '-',
    maxDeltaWeight: overlay.max_delta_weight ?? null,
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
          key: 'gap-pct',
          label: 'Gap',
          left: formatPercent(base.gapPct),
          right: formatPercent(target.gapPct),
          delta: formatSignedDelta(base.gapPct, target.gapPct, (value) => formatPercent(value)),
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
          key: 'confidence',
          label: 'Confidence',
          left: base.confidence,
          right: target.confidence,
          delta: base.confidence === target.confidence ? '不变' : `${base.confidence} -> ${target.confidence}`,
        },
      ],
    };
  }

  const base = extractCrossMarketMetrics(baseSnapshot);
  const target = extractCrossMarketMetrics(targetSnapshot);
  const driverTrendRows = buildDriverTrendRows(base.driverSummary, target.driverSummary);
  return {
    summary: [
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
        key: 'theme',
        label: 'Theme',
        left: base.theme,
        right: target.theme,
        delta: base.theme === target.theme ? '不变' : '已切换',
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
        key: 'bias-summary',
        label: 'Bias Summary',
        left: base.biasSummary,
        right: target.biasSummary,
        delta: base.biasSummary === target.biasSummary ? '不变' : '已调整',
      },
      {
        key: 'max-delta-weight',
        label: 'Max Weight Shift',
        left: formatPercent(base.maxDeltaWeight),
        right: formatPercent(target.maxDeltaWeight),
        delta: formatSignedDelta(base.maxDeltaWeight, target.maxDeltaWeight, (value) => formatPercent(value)),
      },
      ...driverTrendRows,
    ],
  };
};
