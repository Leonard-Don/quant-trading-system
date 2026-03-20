import { buildSnapshotComparison } from '../components/research-workbench/snapshotCompare';

describe('buildSnapshotComparison for cross-market snapshots', () => {
  it('includes execution-plan and recommendation metadata deltas', () => {
    const comparison = buildSnapshotComparison(
      'cross_market',
      {
        payload: {
          total_return: 0.08,
          sharpe_ratio: 1.1,
          data_alignment: { tradable_day_ratio: 0.82 },
          execution_diagnostics: {
            cost_drag: 0.01,
            turnover: 4.2,
            construction_mode: 'equal_weight',
            concentration_level: 'moderate',
            max_batch_fraction: 0.45,
            lot_efficiency: 0.96,
            suggested_rebalance: 'weekly',
            stress_test_flag: 'high',
          },
          execution_plan: {
            route_count: 2,
            batches: [{}, {}],
            by_provider: { us_stock: 2 },
            venue_allocation: [{ key: 'US_ETF' }],
          },
          template_meta: {
            recommendation_tier: '重点跟踪',
            theme: 'Old theme',
            allocation_mode: 'template_base',
            bias_summary: '多头增配 XLE',
            dominant_drivers: [{ key: 'baseload_support', label: '基建/基荷支撑', value: 0.2 }],
            driver_summary: [
              { key: 'baseload_support', label: '基建/基荷支撑', value: 0.2 },
              { key: 'growth_pressure', label: '成长端估值压力', value: 0.1 },
            ],
            theme_core: 'XLE+4.0pp',
            theme_support: 'IGV',
          },
          allocation_overlay: {
            max_delta_weight: 0.04,
          },
        },
      },
      {
        payload: {
          total_return: 0.12,
          sharpe_ratio: 1.45,
          data_alignment: { tradable_day_ratio: 0.9 },
          execution_diagnostics: {
            cost_drag: 0.008,
            turnover: 3.8,
            construction_mode: 'ols_hedge',
            concentration_level: 'balanced',
            max_batch_fraction: 0.33,
            lot_efficiency: 0.992,
            suggested_rebalance: 'biweekly',
            stress_test_flag: 'moderate',
          },
          execution_plan: {
            route_count: 3,
            batches: [{}, {}, {}],
            by_provider: { commodity: 1, us_stock: 2 },
            venue_allocation: [{ key: 'COMEX_CME' }, { key: 'US_ETF' }],
          },
          template_meta: {
            recommendation_tier: '优先部署',
            theme: 'New theme',
            allocation_mode: 'macro_bias',
            bias_summary: '多头增配 XLE，空头增配 IGV',
            dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.32 }],
            driver_summary: [
              { key: 'baseload_support', label: '基建/基荷支撑', value: 0.18 },
              { key: 'growth_pressure', label: '成长端估值压力', value: 0.32 },
            ],
            theme_core: 'XLE+8.5pp',
            theme_support: 'SOXX',
          },
          allocation_overlay: {
            max_delta_weight: 0.085,
          },
        },
      }
    );

    expect(comparison.summary.some((item) => item.includes('执行批次'))).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Route Count')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Batch Count')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Max Batch')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Concentration')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Lot Efficiency')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Rebalance')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Stress Flag')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Recommendation')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Theme')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Allocation Mode')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Bias Summary')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Max Weight Shift')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Dominant Driver')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Theme Core')).toBe(true);
    expect(comparison.rows.some((row) => row.label.startsWith('Driver: '))).toBe(true);
  });
});
