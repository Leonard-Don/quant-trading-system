import {
  buildDrawdownSeries,
  buildPerformanceChartData,
  buildReturnDistribution,
  buildRiskRadarData,
} from '../utils/backtestCharts';

describe('backtest chart helpers', () => {
  test('filters performance data relative to the latest backtest point', () => {
    const result = buildPerformanceChartData([
      { date: '2023-01-01', total: 10000, price: 100 },
      { date: '2023-08-01', total: 10500, price: 105 },
      { date: '2024-01-01', total: 11200, price: 112 },
    ], '6mo');

    expect(result).toHaveLength(2);
    expect(result[0].dateLongLabel).toBe('2023-08-01');
    expect(result[1].dateLongLabel).toBe('2024-01-01');
  });

  test('derives return distribution from totals when explicit returns are missing', () => {
    const { bins, stats } = buildReturnDistribution([
      { date: '2024-01-01', total: 10000 },
      { date: '2024-01-02', total: 10100 },
      { date: '2024-01-03', total: 9999 },
      { date: '2024-01-04', total: 10049 },
    ]);

    expect(bins.length).toBeGreaterThan(0);
    expect(stats.positiveDays).toBe(2);
    expect(stats.negativeDays).toBe(1);
  });

  test('builds drawdown stats from portfolio totals', () => {
    const { series, stats } = buildDrawdownSeries([
      { date: '2024-01-01', total: 10000 },
      { date: '2024-01-02', total: 12000 },
      { date: '2024-01-03', total: 9000 },
      { date: '2024-01-04', total: 9500 },
    ]);

    expect(series).toHaveLength(4);
    expect(stats.maxDrawdown).toBeCloseTo(-25, 5);
    expect(stats.underwaterDays).toBe(2);
  });

  test('builds drawdown stats even when legacy points do not include parsable dates', () => {
    const { series, stats } = buildDrawdownSeries([
      { total: 10000 },
      { total: 12000 },
      { total: 9000 },
    ]);

    expect(series).toHaveLength(3);
    expect(series[0].dateLongLabel).toContain('第 1 个交易点');
    expect(stats.maxDrawdown).toBeCloseTo(-25, 5);
  });

  test('normalizes radar scores into a stable 0-100 range', () => {
    const radarData = buildRiskRadarData({
      total_return: 0.2,
      sharpe_ratio: 1.4,
      win_rate: 0.58,
      max_drawdown: 0.12,
      volatility: 0.18,
      profit_factor: 1.8,
    });

    expect(radarData).toHaveLength(6);
    radarData.forEach((item) => {
      expect(item.score).toBeGreaterThanOrEqual(0);
      expect(item.score).toBeLessThanOrEqual(100);
    });
  });

  test('preserves original series order when dates are missing', () => {
    const result = buildPerformanceChartData([
      { total: 10000, signal: 0 },
      { total: 12000, signal: 1 },
      { total: 11405, signal: 0 },
    ], 'max');

    expect(result[0].portfolio_value).toBe(10000);
    expect(result[result.length - 1].portfolio_value).toBe(11405);
    expect(result[0].dateLongLabel).toContain('第 1 个交易点');
  });
});
