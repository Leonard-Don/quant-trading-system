import { buildCrossMarketWorkbenchPayload } from '../components/research-playbook/playbookViewModels';

describe('buildCrossMarketWorkbenchPayload', () => {
  it('persists recommendation metadata in task context and snapshot payload', () => {
    const payload = buildCrossMarketWorkbenchPayload(
      { source: 'cross_market_panel', template: 'energy_vs_ai_apps', note: '推荐模板入口' },
      {
        id: 'energy_vs_ai_apps',
        name: 'Energy infrastructure vs AI application ETF',
        theme: 'Baseload scarcity vs AI application enthusiasm',
        recommendationTier: '优先部署',
        recommendationScore: 3.2,
        driverHeadline: '基荷错配(z=1.80) · 投资活跃度(score=0.40)',
        biasSummary: '多头增配 XLE，空头增配 IGV',
        biasStrength: 8.5,
        biasHighlights: ['XLE +8.5pp', 'IGV +6.0pp'],
        biasActions: [
          { symbol: 'XLE', side: 'long', action: 'increase', delta: 0.085 },
          { symbol: 'IGV', side: 'short', action: 'increase', delta: 0.06 },
        ],
        driverSummary: [
          { key: 'baseload_support', label: '基建/基荷支撑', value: 0.31 },
          { key: 'growth_pressure', label: '成长端估值压力', value: 0.24 },
        ],
        dominantDrivers: [
          { key: 'baseload_support', label: '基建/基荷支撑', value: 0.31 },
        ],
        coreLegs: [
          { symbol: 'XLE', side: 'long', role: 'core', delta: 8.5 },
        ],
        supportLegs: [
          { symbol: 'IGV', side: 'short', role: 'support', delta: 1.6 },
        ],
        themeCore: 'XLE+8.5pp',
        themeSupport: 'IGV',
        construction_mode: 'equal_weight',
        description: 'Physical energy backbone against AI enthusiasm.',
      },
      null,
      [
        { symbol: 'XLE', asset_class: 'ETF', side: 'long', weight: 0.5 },
        { symbol: 'IGV', asset_class: 'ETF', side: 'short', weight: 0.5 },
      ]
    );

    expect(payload.context.theme).toBe('Baseload scarcity vs AI application enthusiasm');
    expect(payload.context.recommendation_tier).toBe('优先部署');
    expect(payload.context.recommendation_score).toBe(3.2);
    expect(payload.context.recommendation_reason).toContain('基荷错配');
    expect(payload.context.allocation_mode).toBe('macro_bias');
    expect(payload.context.bias_summary).toContain('多头增配');
    expect(payload.context.bias_actions).toHaveLength(2);
    expect(payload.context.driver_summary).toHaveLength(2);
    expect(payload.context.theme_core).toContain('XLE');
    expect(payload.snapshot.payload.template_meta.theme).toBe(payload.context.theme);
    expect(payload.snapshot.payload.template_meta.recommendation_tier).toBe('优先部署');
    expect(payload.snapshot.payload.template_meta.recommendation_reason).toContain('投资活跃度');
    expect(payload.snapshot.payload.template_meta.bias_summary).toContain('IGV');
    expect(payload.snapshot.payload.template_meta.bias_actions[0].symbol).toBe('XLE');
    expect(payload.snapshot.payload.template_meta.driver_summary[0].label).toContain('基建');
    expect(payload.snapshot.payload.template_meta.theme_support).toBe('IGV');
  });
});
