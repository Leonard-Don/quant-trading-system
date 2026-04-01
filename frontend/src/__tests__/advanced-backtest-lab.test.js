import {
  buildBatchDraftState,
  buildBatchInsight,
  buildMarketRegimeInsight,
  buildOverfittingWarnings,
  buildPortfolioExposureChartData,
  buildPortfolioExposureSummary,
  buildPortfolioPositionSnapshot,
  buildResearchConclusion,
  buildRobustnessScore,
  buildWalkForwardInsight,
} from '../utils/advancedBacktestLab';
import {
  buildBacktestActionPosture,
  buildBenchmarkSummary,
  buildCostSensitivityTasks,
  buildMultiSymbolTasks,
  buildParameterOptimizationTasks,
  buildRobustnessTasks,
  buildWalkForwardParameterCandidates,
  buildSignalExplanation,
  parseSymbolsInput,
} from '../utils/backtestResearch';

describe('advancedBacktestLab utilities', () => {
  test('normalizes the main backtest draft before importing into advanced experiments', () => {
    expect(buildBatchDraftState(null)).toBeNull();

    expect(buildBatchDraftState({
      symbol: 'tsla',
      strategy: 'moving_average',
      dateRange: ['2025-01-01', '2025-12-31'],
      initial_capital: 25000,
      commission: 0.15,
      slippage: 0.2,
      parameters: { fast_period: 10, slow_period: 30 },
    })).toEqual({
      symbol: 'TSLA',
      strategy: 'moving_average',
      dateRange: ['2025-01-01', '2025-12-31'],
      initial_capital: 25000,
      commission: 0.15,
      slippage: 0.2,
      parameters: { fast_period: 10, slow_period: 30 },
    });
  });

  test('builds a readable batch experiment insight', () => {
    const insight = buildBatchInsight({
      summary: {
        best_result: {
          strategy: 'moving_average',
          total_return: 0.18,
          sharpe_ratio: 1.42,
          max_drawdown: -0.12,
        },
      },
      ranked_results: [
        {
          task_id: 'task_1',
          strategy: 'moving_average',
          success: true,
          metrics: {
            total_return: 0.18,
            sharpe_ratio: 1.42,
            max_drawdown: -0.12,
          },
        },
        {
          task_id: 'task_2',
          strategy: 'rsi',
          success: true,
          metrics: {
            total_return: 0.09,
            sharpe_ratio: 1.15,
            max_drawdown: -0.08,
          },
        },
      ],
    });

    expect(insight).toMatchObject({
      type: 'success',
      title: expect.stringContaining('领先策略'),
    });
    expect(insight.description).toContain('9.00%');
  });

  test('warns when the best batch result has a deep drawdown in summary metrics', () => {
    const insight = buildBatchInsight({
      summary: {
        best_result: {
          task_id: 'task_1',
          strategy: 'moving_average',
          total_return: 0.22,
          sharpe_ratio: 1.55,
          max_drawdown: -0.24,
        },
      },
      ranked_results: [
        {
          task_id: 'task_1',
          strategy: 'moving_average',
          success: true,
          metrics: {
            total_return: 0.22,
            sharpe_ratio: 1.55,
          },
        },
      ],
    });

    expect(insight).toMatchObject({
      type: 'warning',
      title: expect.stringContaining('回撤偏深'),
    });
    expect(insight.description).toContain('24.00%');
  });

  test('builds a readable walk-forward insight', () => {
    const insight = buildWalkForwardInsight({
      n_windows: 5,
      aggregate_metrics: {
        positive_windows: 4,
        negative_windows: 1,
        average_return: 0.06,
        average_sharpe: 1.1,
        return_std: 0.03,
      },
    });

    expect(insight).toMatchObject({
      type: 'success',
      title: expect.stringContaining('较稳定'),
    });
    expect(insight.description).toContain('4/5');
  });

  test('builds research helper tasks for optimization and multi-symbol experiments', () => {
    const strategyDefinition = {
      parameters: {
        fast_period: { default: 10, min: 5, max: 20, step: 5 },
        slow_period: { default: 30, min: 20, max: 60, step: 10 },
      },
    };

    const optimizationTasks = buildParameterOptimizationTasks({
      symbol: 'AAPL',
      strategy: 'moving_average',
      dateRange: ['2025-01-01', '2025-12-31'],
      initialCapital: 10000,
      commission: 0.001,
      slippage: 0.001,
      baseParameters: { fast_period: 10, slow_period: 30 },
      strategyDefinition,
      density: 3,
    });
    expect(optimizationTasks.length).toBeGreaterThan(1);
    expect(optimizationTasks[0].research_label).toContain('fast_period');

    expect(parseSymbolsInput('aapl, msft, aapl , nvda')).toEqual(['AAPL', 'MSFT', 'NVDA']);

    expect(buildMultiSymbolTasks({
      symbols: ['AAPL', 'MSFT'],
      strategy: 'buy_and_hold',
      dateRange: ['2025-01-01', '2025-06-30'],
      initialCapital: 10000,
      commission: 0.001,
      slippage: 0.001,
      baseParameters: {},
    })).toHaveLength(2);

    expect(buildCostSensitivityTasks({
      symbol: 'AAPL',
      strategy: 'macd',
      dateRange: ['2025-01-01', '2025-06-30'],
      initialCapital: 10000,
      commission: 0.001,
      slippage: 0.001,
      baseParameters: {},
    })).toHaveLength(3);

    expect(buildRobustnessTasks({
      symbol: 'AAPL',
      strategy: 'moving_average',
      dateRange: ['2025-01-01', '2025-06-30'],
      initialCapital: 10000,
      commission: 0.001,
      slippage: 0.001,
      baseParameters: { fast_period: 10 },
      strategyDefinition,
    }).length).toBeGreaterThan(2);

    const walkCandidates = buildWalkForwardParameterCandidates({
      baseParameters: { fast_period: 10, slow_period: 30 },
      strategyDefinition,
      density: 3,
    });
    expect(walkCandidates.length).toBeGreaterThan(1);
    expect(walkCandidates[0]).toHaveProperty('fast_period');
    expect(walkCandidates[0]).toHaveProperty('slow_period');
  });

  test('builds benchmark and signal explanations', () => {
    const benchmark = buildBenchmarkSummary({
      moving_average: { total_return: 0.16, sharpe_ratio: 1.3, max_drawdown: -0.08 },
      buy_and_hold: { total_return: 0.1, sharpe_ratio: 0.9, max_drawdown: -0.12 },
    }, 'moving_average');

    expect(benchmark).toMatchObject({
      beatBenchmark: true,
    });
    expect(benchmark.excessReturn).toBeCloseTo(0.06);

    const explanation = buildSignalExplanation({
      strategy: 'buy_and_hold',
      total_return: 0.12,
      has_open_position: true,
      trades: [],
    });
    expect(explanation.join(' ')).toContain('买入持有策略');
  });

  test('builds a backtest action posture from result quality', () => {
    expect(buildBacktestActionPosture({
      result: {
        total_return: 0.18,
        sharpe_ratio: 1.24,
        max_drawdown: -0.09,
        profit_factor: 1.6,
        win_rate: 0.53,
        num_trades: 12,
      },
    })).toMatchObject({
      label: 'advance',
      posture: '继续稳健性验证',
    });

    expect(buildBacktestActionPosture({
      result: {
        total_return: -0.04,
        sharpe_ratio: 0.2,
        max_drawdown: -0.23,
        profit_factor: 0.8,
        win_rate: 0.35,
        num_trades: 8,
      },
    })).toMatchObject({
      label: 'review',
      posture: '先回测复核',
    });
  });

  test('builds market regime insight and robustness score', () => {
    const marketRegimeResult = {
      summary: {
        regime_count: 4,
        positive_regimes: 3,
        strongest_regime: { regime: '上涨趋势', strategy_total_return: 0.14 },
        weakest_regime: { regime: '下跌趋势', strategy_total_return: -0.03 },
      },
      regimes: [
        { regime: '上涨趋势', strategy_total_return: 0.14 },
        { regime: '下跌趋势', strategy_total_return: -0.03 },
        { regime: '高波动震荡', strategy_total_return: 0.04 },
        { regime: '低波动整理', strategy_total_return: 0.02 },
      ],
    };

    const regimeInsight = buildMarketRegimeInsight(marketRegimeResult);
    expect(regimeInsight).toMatchObject({
      type: 'success',
      title: expect.stringContaining('多数市场状态'),
    });

    const robustness = buildRobustnessScore({
      batchResult: {
        summary: {
          total_tasks: 4,
          successful: 4,
          average_return: 0.09,
          best_result: { max_drawdown: -0.1 },
        },
      },
      walkResult: {
        n_windows: 5,
        aggregate_metrics: {
          positive_windows: 4,
          average_sharpe: 1.2,
          return_std: 0.04,
        },
      },
      benchmarkSummary: {
        excessReturn: 0.05,
        sharpeDelta: 0.3,
        drawdownDelta: -0.02,
      },
      marketRegimeResult,
    });

    expect(robustness.score).toBeGreaterThan(60);
    expect(robustness.dimensions).toHaveLength(4);
  });

  test('builds overfitting warnings and research conclusion', () => {
    const batchResult = {
      summary: {
        total_tasks: 4,
        successful: 4,
        average_return: 0.04,
        best_result: {
          max_drawdown: -0.11,
        },
      },
      ranked_results: [
        {
          task_id: 'best',
          success: true,
          metrics: {
            total_return: 0.22,
          },
        },
        {
          task_id: 'peer-1',
          success: true,
          metrics: {
            total_return: 0.03,
          },
        },
        {
          task_id: 'peer-2',
          success: true,
          metrics: {
            total_return: 0.01,
          },
        },
      ],
    };

    const walkResult = {
      n_windows: 5,
      aggregate_metrics: {
        positive_windows: 2,
        return_std: 0.09,
      },
    };

    const benchmarkSummary = {
      excessReturn: -0.01,
    };

    const marketRegimeResult = {
      summary: {
        regime_count: 4,
        positive_regimes: 2,
        strongest_regime: { strategy_total_return: 0.16 },
        weakest_regime: { strategy_total_return: -0.08, regime: '下跌趋势' },
      },
      regimes: [{}, {}, {}, {}],
    };

    const warnings = buildOverfittingWarnings({
      batchResult,
      walkResult,
      benchmarkSummary,
      marketRegimeResult,
    });

    expect(warnings.length).toBeGreaterThanOrEqual(3);
    expect(warnings.some((item) => item.title.includes('基准'))).toBe(true);

    const conclusion = buildResearchConclusion({
      robustnessScore: { score: 48, level: '低', summary: '当前稳健性偏低。' },
      overfittingWarnings: warnings,
      batchResult,
      walkResult,
      benchmarkSummary,
      marketRegimeResult,
    });

    expect(conclusion.title).toContain('阶段性有效');
    expect(conclusion.nextActions.length).toBeGreaterThan(0);
  });

  test('builds portfolio exposure chart data and current position snapshot', () => {
    const portfolioStrategyResult = {
      portfolio_history: [
        { date: '2025-01-02', total: 10000, gross_exposure: 0.5, net_exposure: 0.1, cash: 5000 },
        { date: '2025-01-03', total: 10120, gross_exposure: 0.9, net_exposure: 0.2, cash: 1200 },
      ],
      positions_history: [
        { date: '2025-01-02', AAPL: 10, MSFT: -4, NVDA: 0 },
        { date: '2025-01-03', AAPL: 12.5, MSFT: -3.25, NVDA: 0 },
      ],
      weights: {
        AAPL: 0.6,
        MSFT: -0.4,
      },
    };

    expect(buildPortfolioExposureChartData(portfolioStrategyResult)).toEqual([
      { date: '2025-01-02', total: 10000, grossExposure: 0.5, netExposure: 0.1, cash: 5000 },
      { date: '2025-01-03', total: 10120, grossExposure: 0.9, netExposure: 0.2, cash: 1200 },
    ]);

    expect(buildPortfolioPositionSnapshot(portfolioStrategyResult)).toEqual([
      { symbol: 'AAPL', shares: 12.5, targetWeight: 0.6, direction: '多头' },
      { symbol: 'MSFT', shares: -3.25, targetWeight: -0.4, direction: '空头' },
    ]);

    expect(buildPortfolioExposureSummary(portfolioStrategyResult)).toEqual({
      grossExposure: 0.9,
      netExposure: 0.2,
      cash: 1200,
      activePositions: 2,
    });
  });
});
