import {
  buildBatchDraftState,
  buildBatchInsight,
  buildWalkForwardInsight,
} from '../utils/advancedBacktestLab';
import {
  buildBenchmarkSummary,
  buildCostSensitivityTasks,
  buildMultiSymbolTasks,
  buildParameterOptimizationTasks,
  buildRobustnessTasks,
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
});
