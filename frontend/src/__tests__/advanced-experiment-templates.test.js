import {
  ADVANCED_TEMPLATE_CATEGORY_LABELS,
  buildMainBacktestDraftFromTemplate,
  buildAdvancedExperimentTemplatePreview,
  buildAdvancedExperimentSnapshot,
  buildAdvancedExperimentTemplatePayload,
  buildExperimentComparison,
  deleteAdvancedExperimentTemplate,
  inferAdvancedExperimentTemplateCategory,
  loadAdvancedExperimentSnapshots,
  loadAdvancedExperimentTemplates,
  saveAdvancedExperimentSnapshot,
  saveAdvancedExperimentTemplate,
  suggestAdvancedExperimentTemplateName,
  toggleAdvancedExperimentTemplatePinned,
} from '../utils/advancedExperimentTemplates';

describe('advanced experiment templates', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  test('saves, loads and deletes experiment templates', () => {
    const saved = saveAdvancedExperimentTemplate(buildAdvancedExperimentTemplatePayload({
      name: '趋势模板',
      note: '用于趋势策略的大盘股实验',
      batchValues: {
        symbol: 'aapl',
        dateRange: ['2025-01-01', '2025-12-31'],
        strategies: ['moving_average'],
      },
      walkValues: {
        symbol: 'aapl',
        strategy: 'moving_average',
        dateRange: ['2025-01-01', '2025-12-31'],
      },
      batchConfigs: {
        moving_average: { fast_period: 10, slow_period: 30 },
      },
      walkParams: { fast_period: 10, slow_period: 30 },
      researchSymbolsInput: 'AAPL,MSFT',
      optimizationDensity: 4,
      portfolioObjective: 'max_sharpe',
    }));

    const templates = loadAdvancedExperimentTemplates();
    expect(templates).toHaveLength(1);
    expect(templates[0].name).toBe('趋势模板');
    expect(templates[0].note).toBe('用于趋势策略的大盘股实验');
    expect(templates[0].batch.symbol).toBe('AAPL');
    expect(templates[0].walk.strategy_parameters.fast_period).toBe(10);

    deleteAdvancedExperimentTemplate(saved.id);
    expect(loadAdvancedExperimentTemplates()).toHaveLength(0);
  });

  test('overwrites existing templates by id and suggests readable names', () => {
    const initial = saveAdvancedExperimentTemplate(buildAdvancedExperimentTemplatePayload({
      name: '旧模板',
      batchValues: { symbol: 'aapl', dateRange: ['2025-01-01', '2025-12-31'], strategies: ['moving_average'] },
      walkValues: { symbol: 'aapl', strategy: 'moving_average', dateRange: ['2025-01-01', '2025-12-31'] },
      batchConfigs: {},
      walkParams: {},
      researchSymbolsInput: 'AAPL,MSFT',
      optimizationDensity: 3,
      portfolioObjective: 'equal_weight',
    }));

    saveAdvancedExperimentTemplate({
      ...buildAdvancedExperimentTemplatePayload({
        name: '新模板',
        batchValues: { symbol: 'msft', dateRange: ['2025-01-01', '2025-12-31'], strategies: ['rsi'] },
        walkValues: { symbol: 'msft', strategy: 'rsi', dateRange: ['2025-01-01', '2025-12-31'] },
        batchConfigs: {},
        walkParams: {},
        researchSymbolsInput: 'MSFT,NVDA',
        optimizationDensity: 4,
        portfolioObjective: 'max_sharpe',
      }),
      id: initial.id,
      created_at: initial.created_at,
    });

    const templates = loadAdvancedExperimentTemplates();
    expect(templates).toHaveLength(1);
    expect(templates[0].name).toBe('新模板');
    expect(templates[0].batch.symbol).toBe('MSFT');

    expect(suggestAdvancedExperimentTemplateName({
      batchValues: { symbol: 'aapl', strategies: ['moving_average'] },
      walkValues: { symbol: 'aapl', strategy: 'moving_average' },
      batchExperimentMeta: { title: '参数寻优结果' },
      optimizationDensity: 4,
      portfolioObjective: 'equal_weight',
    })).toContain('参数寻优结果');
  });

  test('infers template categories for grouping', () => {
    expect(inferAdvancedExperimentTemplateCategory({
      batchExperimentMeta: { title: '参数寻优结果' },
    })).toBe('parameter_optimization');

    expect(inferAdvancedExperimentTemplateCategory({
      batchExperimentMeta: { title: '多标的横向研究' },
    })).toBe('multi_symbol');

    expect(inferAdvancedExperimentTemplateCategory({
      benchmarkSummary: { excessReturn: 0.02 },
    })).toBe('benchmark');

    expect(ADVANCED_TEMPLATE_CATEGORY_LABELS.market_regime).toBe('市场状态');
  });

  test('pins templates and sorts pinned items first', () => {
    const first = saveAdvancedExperimentTemplate(buildAdvancedExperimentTemplatePayload({
      name: '模板A',
      batchValues: { symbol: 'aapl', dateRange: ['2025-01-01', '2025-12-31'], strategies: ['moving_average'] },
      walkValues: { symbol: 'aapl', strategy: 'moving_average', dateRange: ['2025-01-01', '2025-12-31'] },
      batchConfigs: {},
      walkParams: {},
      researchSymbolsInput: 'AAPL,MSFT',
      optimizationDensity: 3,
      portfolioObjective: 'equal_weight',
    }));
    const second = saveAdvancedExperimentTemplate(buildAdvancedExperimentTemplatePayload({
      name: '模板B',
      batchValues: { symbol: 'msft', dateRange: ['2025-01-01', '2025-12-31'], strategies: ['rsi'] },
      walkValues: { symbol: 'msft', strategy: 'rsi', dateRange: ['2025-01-01', '2025-12-31'] },
      batchConfigs: {},
      walkParams: {},
      researchSymbolsInput: 'MSFT,NVDA',
      optimizationDensity: 4,
      portfolioObjective: 'equal_weight',
    }));

    const pinned = toggleAdvancedExperimentTemplatePinned(first.id);
    expect(pinned.pinned).toBe(true);

    const templates = loadAdvancedExperimentTemplates();
    expect(templates[0].id).toBe(first.id);
    expect(templates[1].id).toBe(second.id);
  });

  test('builds and persists snapshots for experiment comparison', () => {
    const snapshot = buildAdvancedExperimentSnapshot({
      batchResult: {
        summary: {
          average_return: 0.08,
          average_sharpe: 1.24,
          total_tasks: 4,
          successful: 4,
          best_result: { total_return: 0.16, max_drawdown: -0.09 },
        },
      },
      walkResult: {
        n_windows: 5,
        aggregate_metrics: {
          average_return: 0.04,
          average_sharpe: 0.92,
          return_std: 0.03,
          positive_windows: 4,
          negative_windows: 1,
        },
      },
      benchmarkSummary: {
        excessReturn: 0.03,
        sharpeDelta: 0.2,
        drawdownDelta: -0.01,
        beatBenchmark: true,
      },
      benchmarkContext: {
        symbol: 'AAPL',
        strategy: 'moving_average',
      },
      marketRegimeResult: {
        summary: {
          regime_count: 4,
          positive_regimes: 3,
          average_regime_return: 0.02,
          strongest_regime: { regime: '上涨趋势' },
          weakest_regime: { regime: '下跌趋势' },
        },
      },
      portfolioStrategyResult: {
        portfolio_objective: 'equal_weight',
        total_return: 0.11,
        annualized_return: 0.09,
        max_drawdown: -0.07,
        sharpe_ratio: 1.02,
      },
      batchExperimentMeta: { title: '参数寻优结果' },
      batchValues: { symbol: 'AAPL', strategies: ['moving_average'] },
      walkValues: { symbol: 'AAPL', strategy: 'moving_average' },
      batchConfigs: {},
      walkParams: {},
      researchSymbolsInput: 'AAPL,MSFT',
      optimizationDensity: 3,
      portfolioObjective: 'equal_weight',
      robustnessScore: { score: 72 },
    });

    expect(snapshot.name).toContain('AAPL');
    expect(snapshot.batch.averageReturn).toBeCloseTo(0.08);

    saveAdvancedExperimentSnapshot(snapshot);
    expect(loadAdvancedExperimentSnapshots()).toHaveLength(1);
  });

  test('builds a compact template preview', () => {
    const preview = buildAdvancedExperimentTemplatePreview(buildAdvancedExperimentTemplatePayload({
      name: '预览模板',
      category: 'parameter_optimization',
      note: '适合观察均线参数扰动后的表现变化',
      batchValues: {
        symbol: 'aapl',
        dateRange: ['2025-01-01', '2025-12-31'],
        strategies: ['moving_average'],
      },
      walkValues: {
        symbol: 'aapl',
        strategy: 'moving_average',
        dateRange: ['2025-01-01', '2025-12-31'],
      },
      batchConfigs: {
        moving_average: { fast_period: 10, slow_period: 30 },
      },
      walkParams: { fast_period: 10, slow_period: 30 },
      researchSymbolsInput: 'AAPL,MSFT,NVDA',
      optimizationDensity: 4,
      portfolioObjective: 'max_sharpe',
    }));

    expect(preview.category).toBe('parameter_optimization');
    expect(preview.note).toContain('均线参数');
    expect(preview.symbol).toBe('AAPL');
    expect(preview.strategy).toBe('moving_average');
    expect(preview.keyParameters).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'fast_period', value: 10 }),
      ])
    );
  });

  test('builds main backtest drafts from advanced templates', () => {
    const draft = buildMainBacktestDraftFromTemplate(buildAdvancedExperimentTemplatePayload({
      name: '主回测模板',
      category: 'parameter_optimization',
      note: '回填主回测用',
      batchValues: {
        symbol: 'aapl',
        dateRange: ['2025-01-01', '2025-12-31'],
        strategies: ['moving_average'],
        initial_capital: 15000,
        commission: 0.15,
        slippage: 0.2,
      },
      walkValues: {
        symbol: 'aapl',
        strategy: 'moving_average',
        dateRange: ['2025-01-01', '2025-12-31'],
        initial_capital: 15000,
        commission: 0.15,
        slippage: 0.2,
      },
      batchConfigs: {
        moving_average: { fast_period: 10, slow_period: 30 },
      },
      walkParams: { fast_period: 10, slow_period: 30 },
      researchSymbolsInput: 'AAPL,MSFT',
      optimizationDensity: 3,
      portfolioObjective: 'equal_weight',
    }));

    expect(draft).toMatchObject({
      symbol: 'AAPL',
      strategy: 'moving_average',
      initial_capital: 15000,
      commission: 0.15,
      slippage: 0.2,
      source: 'advanced_template',
    });
    expect(draft.parameters.fast_period).toBe(10);
  });

  test('builds readable experiment comparisons', () => {
    const comparison = buildExperimentComparison({
      currentSnapshot: {
        name: '当前版本',
        batch: { averageReturn: 0.08, averageSharpe: 1.3 },
        walkForward: { averageReturn: 0.04, positiveWindows: 4, totalWindows: 5 },
        benchmark: { excessReturn: 0.03 },
        marketRegime: { positiveRegimes: 3, regimeCount: 4 },
        robustnessScore: 76,
      },
      previousSnapshot: {
        name: '上一个版本',
        batch: { averageReturn: 0.05, averageSharpe: 0.9 },
        walkForward: { averageReturn: 0.01, positiveWindows: 3, totalWindows: 5 },
        benchmark: { excessReturn: -0.01 },
        marketRegime: { positiveRegimes: 2, regimeCount: 4 },
        robustnessScore: 61,
      },
      formatPercentage: (value) => `${(Number(value || 0) * 100).toFixed(2)}%`,
      formatNumber: (value) => Number(value || 0).toFixed(2),
    });

    expect(comparison.rows).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: '批量平均收益', delta: '+3.00%' }),
        expect.objectContaining({ label: '稳健性评分', delta: '+15.00' }),
      ])
    );
  });
});
