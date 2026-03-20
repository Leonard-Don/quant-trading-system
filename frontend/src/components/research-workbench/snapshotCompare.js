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
  const alignment = payload.data_alignment || {};
  return {
    totalReturn: payload.total_return ?? null,
    sharpeRatio: payload.sharpe_ratio ?? null,
    coverage: alignment.tradable_day_ratio ?? null,
    costDrag: execution.cost_drag ?? null,
    turnover: execution.turnover ?? null,
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
  return {
    summary: [
      `构造 ${base.constructionMode} -> ${target.constructionMode}`,
      `覆盖率 ${formatPercent(base.coverage)} -> ${formatPercent(target.coverage)}`,
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
    ],
  };
};
