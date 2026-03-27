import { buildHeatmapModel } from '../components/GodEyeDashboard/viewModels';

describe('buildHeatmapModel', () => {
  it('projects backend category trends into heatmap cells and anomalies', () => {
    const model = buildHeatmapModel(
      {
        signals: {
          supply_chain: {
            dimensions: {
              investment_activity: { score: 0.42, count: 8 },
            },
          },
          macro_hf: {
            dimensions: {
              inventory: { score: -0.31, count: 5 },
            },
          },
        },
      },
      {
        records: [
          { category: 'bidding' },
          { category: 'hiring' },
          { category: 'commodity_inventory' },
        ],
        category_trends: {
          bidding: { delta_score: 0.18, momentum: 'strengthening', count: 6, high_confidence_count: 3 },
          env_assessment: { delta_score: 0.06, momentum: 'stable', count: 2, high_confidence_count: 1 },
          hiring: { delta_score: 0.12, momentum: 'strengthening', count: 4, high_confidence_count: 2 },
          commodity_inventory: { delta_score: -0.2, momentum: 'weakening', count: 5, high_confidence_count: 4 },
          customs: { delta_score: -0.04, momentum: 'stable', count: 2, high_confidence_count: 0 },
          port_congestion: { delta_score: 0.0, momentum: 'stable', count: 1, high_confidence_count: 0 },
        },
        category_series: {
          bidding: [{ date: '2026-03-10', avg_score: 0.2 }],
          commodity_inventory: [{ date: '2026-03-10', avg_score: -0.3 }],
        },
      }
    );

    const investmentCell = model.cells.find((cell) => cell.key === 'investment_activity');
    expect(investmentCell).toBeTruthy();
    expect(investmentCell.momentum).toBe('strengthening');
    expect(investmentCell.trendDelta).toBeGreaterThan(0);

    const inventoryCell = model.cells.find((cell) => cell.key === 'inventory');
    expect(inventoryCell).toBeTruthy();
    expect(inventoryCell.momentum).toBe('weakening');
    expect(inventoryCell.trendDelta).toBeLessThan(0);

    expect(model.anomalies.some((item) => item.title.includes('bidding'))).toBe(true);
    expect(model.anomalies.some((item) => item.title.includes('commodity_inventory'))).toBe(true);
  });
});
