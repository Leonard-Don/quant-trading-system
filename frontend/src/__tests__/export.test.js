import {
  formatBacktestForExport,
  formatBatchExperimentForExport,
  formatWalkForwardForExport,
} from '../utils/export';

describe('formatBacktestForExport', () => {
  test('uses top-level metrics when nested metrics are absent', () => {
    const formatted = formatBacktestForExport({
      total_return: 0.12,
      annualized_return: 0.18,
      sharpe_ratio: 1.5,
      max_drawdown: 0.06,
      win_rate: 0.55,
      num_trades: 3,
      initial_capital: 10000,
      final_value: 11200,
    });

    expect(formatted.metrics.find((item) => item.metric === '总收益率').value).toBe(
      '12.00%'
    );
    expect(formatted.metrics.find((item) => item.metric === '交易次数').value).toBe(3);
  });

  test('normalizes raw trade fields for export', () => {
    const formatted = formatBacktestForExport({
      trades: [
        {
          date: '2024-01-01',
          type: 'BUY',
          price: 100,
          shares: 10,
          cost: 1000,
        },
        {
          date: '2024-01-02',
          type: 'SELL',
          price: 110,
          shares: 10,
          revenue: 1100,
        },
      ],
    });

    expect(formatted.trades[0]).toMatchObject({
      action: '买入',
      quantity: 10,
      value: '1000.00',
    });
    expect(formatted.trades[1]).toMatchObject({
      action: '卖出',
      quantity: 10,
      value: '1100.00',
    });
  });

  test('formats batch experiment summary and ranked rows for export', () => {
    const formatted = formatBatchExperimentForExport({
      summary: {
        total_tasks: 2,
        successful: 2,
        average_return: 0.11,
        average_sharpe: 1.25,
        ranking_metric: 'sharpe_ratio',
      },
      ranked_results: [
        {
          task_id: 'task_1',
          strategy: 'moving_average',
          symbol: 'AAPL',
          success: true,
          metrics: {
            total_return: 0.15,
            sharpe_ratio: 1.8,
            max_drawdown: -0.06,
            final_value: 11500,
          },
        },
      ],
    });

    expect(formatted.summary.find((item) => item.metric === '总任务数').value).toBe(2);
    expect(formatted.rankedResults[0]).toMatchObject({
      task_id: 'task_1',
      strategy: 'moving_average',
      total_return: '15.00%',
      sharpe_ratio: '1.80',
    });
  });

  test('formats walk-forward windows for export', () => {
    const formatted = formatWalkForwardForExport({
      n_windows: 2,
      aggregate_metrics: {
        average_return: 0.08,
        return_std: 0.03,
        average_sharpe: 1.1,
        positive_windows: 1,
        negative_windows: 1,
      },
      window_results: [
        {
          window_id: 0,
          test_start: '2025-01-01',
          test_end: '2025-03-31',
          metrics: {
            total_return: 0.05,
            sharpe_ratio: 0.9,
            max_drawdown: -0.04,
          },
        },
      ],
    });

    expect(formatted.summary.find((item) => item.metric === '滚动窗口数').value).toBe(2);
    expect(formatted.windows[0]).toMatchObject({
      window: '窗口 1',
      total_return: '5.00%',
      sharpe_ratio: '0.90',
    });
  });
});
