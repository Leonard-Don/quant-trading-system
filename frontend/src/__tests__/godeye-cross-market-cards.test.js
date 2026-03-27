import { buildCrossMarketCards } from '../components/GodEyeDashboard/viewModels';

describe('GodEye cross-market cards narrative trends', () => {
  it('enriches template cards with narrative trend data from research workbench tasks', () => {
    const cards = buildCrossMarketCards(
      {
        templates: [
          {
            id: 'energy_vs_ai_apps',
            name: 'Energy vs AI',
            description: 'Physical energy against AI apps',
            narrative: 'Baseload scarcity theme',
            linked_factors: ['baseload_mismatch'],
            linked_dimensions: ['inventory'],
            assets: [
              { symbol: 'XLE', side: 'long', weight: 0.5, asset_class: 'ETF' },
              { symbol: 'HG=F', side: 'long', weight: 0.5, asset_class: 'COMMODITY_FUTURES' },
              { symbol: 'IGV', side: 'short', weight: 0.6, asset_class: 'ETF' },
              { symbol: 'SOXX', side: 'short', weight: 0.4, asset_class: 'ETF' },
            ],
            preferred_signal: 'positive',
            construction_mode: 'equal_weight',
          },
        ],
      },
      {
        macro_signal: 1,
        macro_score: 0.74,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'fragile',
            reason: '正文抓取脆弱源 ndrc',
            fragile_sources: ['ndrc'],
            watch_sources: [],
            healthy_sources: ['fed'],
            avg_full_text_ratio: 0.44,
          },
        },
        factors: [{ name: 'baseload_mismatch', z_score: 1.2, value: 0.7, signal: 1 }],
        trend: {
          factor_deltas: {
            growth_pressure: { z_score_delta: 0.38, signal_changed: true },
          },
        },
      },
      {
        category_summary: {
          inventory: { delta_score: 0.28, momentum: 'strengthening' },
        },
        signals: {
          macro_hf: {
            dimensions: {
              inventory: { score: 0.42 },
            },
          },
        },
      },
      [
        {
          id: 'rw_1',
          type: 'cross_market',
          status: 'in_progress',
          template: 'energy_vs_ai_apps',
          updated_at: '2026-03-20T12:00:00',
          snapshot: {
            payload: {
              template_meta: {
                template_id: 'energy_vs_ai_apps',
                bias_scale: 1,
                bias_quality_label: 'full',
                bias_quality_reason: '主要政策源正文覆盖稳定',
                dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.34 }],
                theme_core: 'XLE+8.5pp',
                theme_support: 'SOXX',
              },
              research_input: {
                macro: {
                  macro_score: 0.42,
                  macro_signal: 0,
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    avg_full_text_ratio: 0.86,
                  },
                },
                alt_data: {
                  top_categories: [
                    { category: 'inventory', delta_score: 0.03, momentum: 'stable' },
                  ],
                },
              },
              allocation_overlay: {
                compression_summary: { compression_effect: 3.1 },
                compressed_assets: ['XLE', 'IGV'],
                rows: [
                  { symbol: 'XLE', compression_delta: 0.031 },
                  { symbol: 'IGV', compression_delta: 0.018 },
                ],
              },
            },
          },
          snapshot_history: [
            {
              payload: {
                template_meta: {
                  template_id: 'energy_vs_ai_apps',
                  dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.34 }],
                  theme_core: 'XLE+8.5pp',
                  theme_support: 'SOXX',
                },
              },
            },
            {
              payload: {
                template_meta: {
                  template_id: 'energy_vs_ai_apps',
                  dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.21 }],
                  theme_core: 'XLE+4.0pp',
                  theme_support: 'IGV',
                },
              },
            },
          ],
        },
      ]
    );

    expect(cards).toHaveLength(1);
    expect(cards[0].trendLabel).toBe('驱动增强');
    expect(cards[0].trendSummary).toContain('成长端估值压力');
    expect(cards[0].latestThemeCore).toBe('XLE+8.5pp');
    expect(cards[0].latestThemeSupport).toBe('SOXX');
    expect(cards[0].taskRefreshLabel).toBe('建议更新');
    expect(cards[0].taskRefreshSeverity).toBe('high');
    expect(cards[0].taskRefreshTaskId).toBe('rw_1');
    expect(cards[0].taskRefreshPolicySourceDriven).toBe(true);
    expect(cards[0].taskRefreshBiasCompressionDriven).toBe(true);
    expect(cards[0].taskRefreshBiasCompressionCore).toBe(true);
    expect(cards[0].taskRefreshSelectionQualityDriven).toBe(true);
    expect(cards[0].rankingPenalty).toBeGreaterThan(0);
    expect(cards[0].rankingPenaltyReason).toContain('核心腿');
    expect(cards[0].baseRecommendationScore).toBeGreaterThan(cards[0].recommendationScore);
    expect(cards[0].taskAction.target).toBe('workbench');
    expect(cards[0].taskAction.taskId).toBe('rw_1');
    expect(cards[0].taskAction.reason).toBe('bias_quality_core');
    expect(cards[0].taskRefreshSummary).toContain('宏观信号从 0 切到 1');
    expect(cards[0].taskRefreshSummary).toContain('政策源从 healthy 切到 fragile');
    expect(cards[0].taskRefreshSummary).toContain('偏置收缩从 full 切到 compressed');
    expect(cards[0].taskRefreshSummary).toContain('核心腿受压 XLE');
    expect(cards[0].latestTopCompressedAsset).toContain('XLE');
    expect(cards[0].taskRefreshTopCompressedAsset).toContain('XLE');
  });
});
