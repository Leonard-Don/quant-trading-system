import {
  buildPricingPlaybook,
  buildPricingWorkbenchPayload,
} from '../components/research-playbook/playbookViewModels';
import { buildSnapshotComparison } from '../components/research-workbench/snapshotCompare';

describe('pricing playbook percent formatting', () => {
  const pricingResult = {
    symbol: 'AAPL',
    gap_analysis: {
      current_price: 252.89,
      fair_value_mid: 155.49,
      gap_pct: 62.6,
      severity: 'extreme',
      severity_label: '极端偏离',
      direction: '溢价(高估)',
    },
    valuation: {
      fair_value: {
        mid: 155.49,
        low: 132.17,
        high: 178.81,
        method: 'DCF + 可比估值加权',
      },
    },
    deviation_drivers: {
      primary_driver: {
        factor: 'P/B 倍数法溢价',
        description: '当前 P/B 偏高',
        signal_strength: 3.33,
        ranking_reason: '按估值倍数偏离行业基准幅度排序',
      },
      drivers: [{
        factor: 'P/B 倍数法溢价',
        description: '当前 P/B 偏高',
        signal_strength: 3.33,
        ranking_reason: '按估值倍数偏离行业基准幅度排序',
      }],
    },
    implications: {
      primary_view: '高估',
      confidence: 'high',
      risk_level: 'high',
      insights: ['存在显著高估'],
    },
  };

  it('uses percent points in pricing playbook copy', () => {
    const playbook = buildPricingPlaybook({ symbol: 'AAPL', source: 'manual' }, pricingResult);

    expect(playbook.thesis).toContain('+62.6%');
    expect(playbook.thesis).not.toContain('6260.0%');
    expect(playbook.tasks[0].description).toContain('+62.6%');
  });

  it('persists corrected percent copy into the pricing workbench snapshot', () => {
    const playbook = buildPricingPlaybook({ symbol: 'AAPL', source: 'manual' }, pricingResult);
    const payload = buildPricingWorkbenchPayload({ symbol: 'AAPL', source: 'manual' }, pricingResult, playbook);

    expect(payload.snapshot.summary).toContain('+62.6%');
    expect(payload.snapshot.summary).not.toContain('6260.0%');
    expect(payload.snapshot.payload.primary_driver.factor).toBe('P/B 倍数法溢价');
    expect(payload.snapshot.payload.primary_driver.signal_strength).toBe(3.33);
    expect(payload.snapshot.payload.primary_driver.ranking_reason).toBe('按估值倍数偏离行业基准幅度排序');
  });

  it('formats pricing snapshot comparison gap as percent points', () => {
    const comparison = buildSnapshotComparison(
      'pricing',
      {
        payload: {
          fair_value: { mid: 155.49 },
          gap_analysis: { gap_pct: 62.6 },
          implications: { primary_view: '高估', confidence: 'high', confidence_score: 0.85 },
          primary_driver: { factor: 'P/B 倍数法溢价' },
          drivers: [{ factor: 'Alpha 超额收益' }],
        },
      },
      {
        payload: {
          fair_value: { mid: 148.21 },
          gap_analysis: { gap_pct: 48.2 },
          implications: { primary_view: '高估', confidence: 'medium', confidence_score: 0.58 },
          primary_driver: { factor: '估值回归驱动' },
          drivers: [{ factor: 'Alpha 超额收益' }],
        },
      }
    );

    const gapRow = comparison.rows.find((row) => row.key === 'gap-pct');
    const confidenceScoreRow = comparison.rows.find((row) => row.key === 'confidence-score');
    const driverRow = comparison.rows.find((row) => row.key === 'driver');
    expect(gapRow.left).toBe('62.60%');
    expect(gapRow.right).toBe('48.20%');
    expect(gapRow.delta).toBe('-14.40%');
    expect(confidenceScoreRow.left).toBe('0.85');
    expect(confidenceScoreRow.right).toBe('0.58');
    expect(confidenceScoreRow.delta).toBe('-0.27');
    expect(driverRow.left).toBe('P/B 倍数法溢价');
    expect(driverRow.right).toBe('估值回归驱动');
  });
});
