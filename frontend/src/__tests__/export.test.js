import { formatBacktestForExport } from '../utils/export';

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
});
