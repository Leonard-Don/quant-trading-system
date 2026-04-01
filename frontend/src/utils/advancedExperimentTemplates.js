const ADVANCED_EXPERIMENT_TEMPLATES_KEY = 'advanced_experiment_templates';
const ADVANCED_EXPERIMENT_SNAPSHOTS_KEY = 'advanced_experiment_snapshots';
const MAX_SNAPSHOTS = 12;

export const ADVANCED_TEMPLATE_CATEGORY_LABELS = {
  general: '通用实验',
  parameter_optimization: '参数寻优',
  benchmark: '基准对照',
  multi_symbol: '多标的研究',
  cost_sensitivity: '成本敏感性',
  robustness: '稳健性诊断',
  market_regime: '市场状态',
  portfolio: '组合策略',
};

const readStorage = (key, fallback = []) => {
  if (typeof window === 'undefined') {
    return fallback;
  }

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : fallback;
  } catch (error) {
    return fallback;
  }
};

const writeStorage = (key, value) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    // Ignore storage failures so experiments are never blocked.
  }
};

const sanitizeDateRange = (dateRange) => (
  Array.isArray(dateRange) && dateRange[0] && dateRange[1]
    ? [String(dateRange[0]), String(dateRange[1])]
    : null
);

export const inferAdvancedExperimentTemplateCategory = ({
  batchExperimentMeta,
  portfolioObjective,
  marketRegimeResult,
  benchmarkSummary,
}) => {
  const title = String(batchExperimentMeta?.title || '').trim();

  if (title.includes('参数寻优')) {
    return 'parameter_optimization';
  }
  if (title.includes('多标的')) {
    return 'multi_symbol';
  }
  if (title.includes('成本敏感')) {
    return 'cost_sensitivity';
  }
  if (title.includes('稳健性诊断')) {
    return 'robustness';
  }
  if (title.includes('组合')) {
    return 'portfolio';
  }
  if (marketRegimeResult?.summary) {
    return 'market_regime';
  }
  if (benchmarkSummary) {
    return 'benchmark';
  }
  if (portfolioObjective && portfolioObjective !== 'equal_weight') {
    return 'portfolio';
  }
  return 'general';
};

const buildBatchSummary = (batchResult, batchExperimentMeta) => {
  if (!batchResult?.summary) {
    return null;
  }

  return {
    title: batchExperimentMeta?.title || '批量回测结果',
    averageReturn: Number(batchResult.summary.average_return || 0),
    averageSharpe: Number(batchResult.summary.average_sharpe || 0),
    totalTasks: Number(batchResult.summary.total_tasks || 0),
    successfulTasks: Number(batchResult.summary.successful || 0),
    bestReturn: Number(batchResult.summary.best_result?.total_return || 0),
    bestDrawdown: Number(batchResult.summary.best_result?.max_drawdown || 0),
    rankingMetric: batchResult.summary.ranking_metric || 'sharpe_ratio',
  };
};

const buildWalkSummary = (walkResult) => {
  if (!walkResult?.aggregate_metrics) {
    return null;
  }

  return {
    averageReturn: Number(walkResult.aggregate_metrics.average_return || 0),
    averageSharpe: Number(walkResult.aggregate_metrics.average_sharpe || 0),
    returnStd: Number(walkResult.aggregate_metrics.return_std || 0),
    positiveWindows: Number(walkResult.aggregate_metrics.positive_windows || 0),
    negativeWindows: Number(walkResult.aggregate_metrics.negative_windows || 0),
    totalWindows: Number(walkResult.n_windows || 0),
  };
};

const buildBenchmarkSnapshot = (benchmarkSummary, benchmarkContext) => {
  if (!benchmarkSummary || !benchmarkContext?.strategy) {
    return null;
  }

  return {
    strategy: benchmarkContext.strategy,
    symbol: benchmarkContext.symbol,
    excessReturn: Number(benchmarkSummary.excessReturn || 0),
    sharpeDelta: Number(benchmarkSummary.sharpeDelta || 0),
    drawdownDelta: Number(benchmarkSummary.drawdownDelta || 0),
    beatBenchmark: Boolean(benchmarkSummary.beatBenchmark),
  };
};

const buildMarketRegimeSnapshot = (marketRegimeResult) => {
  if (!marketRegimeResult?.summary) {
    return null;
  }

  return {
    regimeCount: Number(marketRegimeResult.summary.regime_count || 0),
    positiveRegimes: Number(marketRegimeResult.summary.positive_regimes || 0),
    averageRegimeReturn: Number(marketRegimeResult.summary.average_regime_return || 0),
    strongestRegime: marketRegimeResult.summary.strongest_regime?.regime || '',
    weakestRegime: marketRegimeResult.summary.weakest_regime?.regime || '',
  };
};

const buildPortfolioSnapshot = (portfolioStrategyResult) => {
  if (!portfolioStrategyResult) {
    return null;
  }

  return {
    objective: portfolioStrategyResult.portfolio_objective || 'equal_weight',
    totalReturn: Number(portfolioStrategyResult.total_return || 0),
    annualizedReturn: Number(portfolioStrategyResult.annualized_return || 0),
    maxDrawdown: Number(portfolioStrategyResult.max_drawdown || 0),
    sharpeRatio: Number(portfolioStrategyResult.sharpe_ratio || 0),
  };
};

export const loadAdvancedExperimentTemplates = () => (
  readStorage(ADVANCED_EXPERIMENT_TEMPLATES_KEY, []).sort((left, right) => (
    Number(Boolean(right.pinned)) - Number(Boolean(left.pinned))
    || new Date(right.updated_at || right.created_at || 0).getTime()
      - new Date(left.updated_at || left.created_at || 0).getTime()
  ))
);

export const saveAdvancedExperimentTemplate = (template) => {
  const existing = loadAdvancedExperimentTemplates();
  const now = new Date().toISOString();
  const nextTemplate = {
    ...template,
    id: template.id || `template_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    updated_at: now,
    created_at: template.created_at || now,
  };
  const filtered = existing.filter((item) => item.id !== nextTemplate.id);
  writeStorage(ADVANCED_EXPERIMENT_TEMPLATES_KEY, [nextTemplate, ...filtered]);
  return nextTemplate;
};

export const suggestAdvancedExperimentTemplateName = ({
  batchValues,
  walkValues,
  batchExperimentMeta,
  optimizationDensity,
  portfolioObjective,
}) => {
  const symbol = String(walkValues?.symbol || batchValues?.symbol || '').trim().toUpperCase() || 'MARKET';
  const strategy = String(walkValues?.strategy || batchValues?.strategies?.[0] || '').trim();

  if (batchExperimentMeta?.title && batchExperimentMeta.title !== '批量回测结果') {
    return `${symbol} · ${batchExperimentMeta.title}`;
  }

  if (portfolioObjective && portfolioObjective !== 'equal_weight') {
    const objectiveLabel = portfolioObjective === 'max_sharpe'
      ? '最大夏普组合'
      : portfolioObjective === 'min_volatility'
        ? '最小波动组合'
        : '等权组合';
    return `${symbol} · ${strategy || '策略'} · ${objectiveLabel}`;
  }

  if (strategy) {
    return `${symbol} · ${strategy} · 寻优密度 ${Number(optimizationDensity || 3)}`;
  }

  return `${symbol} · 高级实验模板`;
};

export const deleteAdvancedExperimentTemplate = (templateId) => {
  const existing = loadAdvancedExperimentTemplates();
  writeStorage(
    ADVANCED_EXPERIMENT_TEMPLATES_KEY,
    existing.filter((item) => item.id !== templateId)
  );
};

export const toggleAdvancedExperimentTemplatePinned = (templateId) => {
  const existing = loadAdvancedExperimentTemplates();
  let updatedTemplate = null;
  const nextTemplates = existing.map((item) => {
    if (item.id !== templateId) {
      return item;
    }

    updatedTemplate = {
      ...item,
      pinned: !item.pinned,
      updated_at: new Date().toISOString(),
    };
    return updatedTemplate;
  });

  writeStorage(ADVANCED_EXPERIMENT_TEMPLATES_KEY, nextTemplates);
  return updatedTemplate;
};

export const buildAdvancedExperimentTemplatePayload = ({
  name,
  category,
  note,
  batchValues,
  walkValues,
  batchConfigs,
  walkParams,
  researchSymbolsInput,
  optimizationDensity,
  portfolioObjective,
}) => ({
  name,
  category: category || 'general',
  note: String(note || '').trim(),
  batch: {
    ...batchValues,
    symbol: String(batchValues?.symbol || '').trim().toUpperCase(),
    dateRange: sanitizeDateRange(batchValues?.dateRange),
    strategies: batchValues?.strategies || [],
    strategy_parameters: batchConfigs || {},
  },
  walk: {
    ...walkValues,
    symbol: String(walkValues?.symbol || '').trim().toUpperCase(),
    dateRange: sanitizeDateRange(walkValues?.dateRange),
    strategy_parameters: walkParams || {},
  },
  researchSymbolsInput: String(researchSymbolsInput || '').trim(),
  optimizationDensity: Number(optimizationDensity || 3),
  portfolioObjective: portfolioObjective || 'equal_weight',
});

export const buildAdvancedExperimentTemplatePreview = (template) => {
  if (!template) {
    return null;
  }

  const batchStrategies = template.batch?.strategies || [];
  const walkParams = template.walk?.strategy_parameters || {};
  const batchParams = template.batch?.strategy_parameters || {};
  const primaryParamEntries = Object.entries(
    template.walk?.strategy
      ? walkParams
      : batchStrategies[0]
        ? (batchParams[batchStrategies[0]] || {})
        : {}
  ).slice(0, 4);

  return {
    name: template.name,
    category: template.category || 'general',
    note: String(template.note || '').trim(),
    symbol: template.walk?.symbol || template.batch?.symbol || '',
    strategy: template.walk?.strategy || batchStrategies[0] || '',
    strategyCount: batchStrategies.length,
    dateRange: template.walk?.dateRange || template.batch?.dateRange || null,
    researchSymbolsInput: template.researchSymbolsInput || '',
    optimizationDensity: Number(template.optimizationDensity || 3),
    portfolioObjective: template.portfolioObjective || 'equal_weight',
    keyParameters: primaryParamEntries.map(([key, value]) => ({
      key,
      value,
    })),
  };
};

export const buildMainBacktestDraftFromTemplate = (template) => {
  if (!template) {
    return null;
  }

  const symbol = String(template.walk?.symbol || template.batch?.symbol || '').trim().toUpperCase();
  const strategy = template.walk?.strategy || template.batch?.strategies?.[0] || '';
  const dateRange = template.walk?.dateRange || template.batch?.dateRange || null;
  const initialCapital = Number(template.walk?.initial_capital ?? template.batch?.initial_capital ?? 10000);
  const commission = Number(template.walk?.commission ?? template.batch?.commission ?? 0.1);
  const slippage = Number(template.walk?.slippage ?? template.batch?.slippage ?? 0.1);
  const parameters = template.walk?.strategy
    ? (template.walk?.strategy_parameters || {})
    : (template.batch?.strategy_parameters?.[strategy] || {});

  if (!symbol || !strategy || !dateRange?.[0] || !dateRange?.[1]) {
    return null;
  }

  return {
    symbol,
    strategy,
    dateRange,
    initial_capital: initialCapital,
    commission,
    slippage,
    parameters,
    source: 'advanced_template',
    template_name: template.name,
    updated_at: new Date().toISOString(),
  };
};

export const loadAdvancedExperimentSnapshots = () => (
  readStorage(ADVANCED_EXPERIMENT_SNAPSHOTS_KEY, []).sort((left, right) => (
    new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime()
  ))
);

export const saveAdvancedExperimentSnapshot = (snapshot) => {
  const existing = loadAdvancedExperimentSnapshots();
  const nextSnapshot = {
    ...snapshot,
    id: snapshot.id || `snapshot_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    created_at: snapshot.created_at || new Date().toISOString(),
  };
  const filtered = existing.filter((item) => item.id !== nextSnapshot.id);
  writeStorage(
    ADVANCED_EXPERIMENT_SNAPSHOTS_KEY,
    [nextSnapshot, ...filtered].slice(0, MAX_SNAPSHOTS)
  );
  return nextSnapshot;
};

export const buildAdvancedExperimentSnapshot = ({
  batchResult,
  walkResult,
  benchmarkSummary,
  benchmarkContext,
  marketRegimeResult,
  portfolioStrategyResult,
  batchExperimentMeta,
  batchValues,
  walkValues,
  batchConfigs,
  walkParams,
  researchSymbolsInput,
  optimizationDensity,
  portfolioObjective,
  robustnessScore,
}) => {
  const batchSummary = buildBatchSummary(batchResult, batchExperimentMeta);
  const walkSummary = buildWalkSummary(walkResult);
  const benchmark = buildBenchmarkSnapshot(benchmarkSummary, benchmarkContext);
  const marketRegime = buildMarketRegimeSnapshot(marketRegimeResult);
  const portfolio = buildPortfolioSnapshot(portfolioStrategyResult);

  if (!batchSummary && !walkSummary && !benchmark && !marketRegime && !portfolio) {
    return null;
  }

  const primarySymbol = String(
    batchValues?.symbol || walkValues?.symbol || benchmarkContext?.symbol || ''
  ).trim().toUpperCase();
  const primaryStrategy = walkValues?.strategy || benchmarkContext?.strategy || '';
  const labelPrefix = primaryStrategy ? `${primarySymbol || '实验'} · ${primaryStrategy}` : (primarySymbol || '高级实验');

  return {
    name: `${labelPrefix} · ${new Date().toLocaleString('zh-CN', { hour12: false })}`,
    symbol: primarySymbol,
    strategy: primaryStrategy,
    batch: batchSummary,
    walkForward: walkSummary,
    benchmark,
    marketRegime,
    portfolio,
    robustnessScore: robustnessScore?.score ?? null,
    context: {
      researchSymbolsInput: String(researchSymbolsInput || '').trim(),
      optimizationDensity: Number(optimizationDensity || 3),
      portfolioObjective: portfolioObjective || 'equal_weight',
      batch: buildAdvancedExperimentTemplatePayload({
        name: '',
        batchValues,
        walkValues,
        batchConfigs,
        walkParams,
        researchSymbolsInput,
        optimizationDensity,
        portfolioObjective,
      }).batch,
      walk: buildAdvancedExperimentTemplatePayload({
        name: '',
        batchValues,
        walkValues,
        batchConfigs,
        walkParams,
        researchSymbolsInput,
        optimizationDensity,
        portfolioObjective,
      }).walk,
    },
  };
};

const buildComparisonRow = (
  label,
  current,
  previous,
  formatter = (value) => value,
  deltaFormatter = formatter
) => {
  if (current === null || current === undefined) {
    return null;
  }

  const normalizedCurrent = Number(current || 0);
  const normalizedPrevious = Number(previous || 0);

  return {
    key: label,
    label,
    current: formatter(normalizedCurrent),
    previous: formatter(normalizedPrevious),
    deltaRaw: normalizedCurrent - normalizedPrevious,
    deltaFormatter,
  };
};

export const buildExperimentComparison = ({
  currentSnapshot,
  previousSnapshot,
  formatPercentage,
  formatNumber,
}) => {
  if (!currentSnapshot || !previousSnapshot) {
    return null;
  }

  const rows = [
    buildComparisonRow(
      '批量平均收益',
      currentSnapshot.batch?.averageReturn,
      previousSnapshot.batch?.averageReturn,
      formatPercentage,
      formatPercentage
    ),
    buildComparisonRow(
      '批量平均夏普',
      currentSnapshot.batch?.averageSharpe,
      previousSnapshot.batch?.averageSharpe,
      formatNumber,
      formatNumber
    ),
    buildComparisonRow(
      '滚动平均收益',
      currentSnapshot.walkForward?.averageReturn,
      previousSnapshot.walkForward?.averageReturn,
      formatPercentage,
      formatPercentage
    ),
    buildComparisonRow(
      '正收益窗口占比',
      currentSnapshot.walkForward?.totalWindows
        ? currentSnapshot.walkForward.positiveWindows / currentSnapshot.walkForward.totalWindows
        : null,
      previousSnapshot.walkForward?.totalWindows
        ? previousSnapshot.walkForward.positiveWindows / previousSnapshot.walkForward.totalWindows
        : null,
      formatPercentage,
      formatPercentage
    ),
    buildComparisonRow(
      '基准超额收益',
      currentSnapshot.benchmark?.excessReturn,
      previousSnapshot.benchmark?.excessReturn,
      formatPercentage,
      formatPercentage
    ),
    buildComparisonRow(
      '市场状态正收益占比',
      currentSnapshot.marketRegime?.regimeCount
        ? currentSnapshot.marketRegime.positiveRegimes / currentSnapshot.marketRegime.regimeCount
        : null,
      previousSnapshot.marketRegime?.regimeCount
        ? previousSnapshot.marketRegime.positiveRegimes / previousSnapshot.marketRegime.regimeCount
        : null,
      formatPercentage,
      formatPercentage
    ),
    buildComparisonRow(
      '稳健性评分',
      currentSnapshot.robustnessScore,
      previousSnapshot.robustnessScore,
      formatNumber,
      formatNumber
    ),
  ].filter(Boolean);

  if (!rows.length) {
    return null;
  }

  return {
    title: `${currentSnapshot.name} 对比 ${previousSnapshot.name}`,
    rows: rows.map((row) => ({
      ...row,
      delta: Math.abs(row.deltaRaw) < 0.000001 ? '持平' : `${row.deltaRaw > 0 ? '+' : ''}${row.deltaFormatter(row.deltaRaw)}`,
      direction: row.deltaRaw > 0 ? 'up' : row.deltaRaw < 0 ? 'down' : 'flat',
    })),
  };
};
