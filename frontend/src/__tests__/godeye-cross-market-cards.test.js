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
                selection_quality: {
                  label: 'auto_downgraded',
                  base_recommendation_score: 3.12,
                  effective_recommendation_score: 2.67,
                  base_recommendation_tier: '优先部署',
                  effective_recommendation_tier: '重点跟踪',
                  ranking_penalty: 0.45,
                  reason: '当前主题已进入自动降级处理，默认模板选择谨慎下调',
                },
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
                  selection_quality: {
                    label: 'auto_downgraded',
                    reason: '核心腿 XLE 已进入压缩焦点，主题排序自动降级',
                  },
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
                  selection_quality: {
                    label: 'original',
                    reason: '原始推荐强度保留',
                  },
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
    expect(cards[0].taskRefreshSelectionQualityActive).toBe(true);
    expect(cards[0].taskRefreshReviewContextDriven).toBe(true);
    expect(cards[0].taskRefreshSelectionQualityRunState.label).toBe('auto_downgraded');
    expect(cards[0].rankingPenalty).toBeGreaterThan(0);
    expect(cards[0].rankingPenaltyReason).toContain('核心腿');
    expect(cards[0].baseRecommendationScore).toBeGreaterThan(cards[0].recommendationScore);
    expect(cards[0].taskAction.target).toBe('workbench');
    expect(cards[0].taskAction.label).toBe('优先重看任务');
    expect(cards[0].taskAction.taskId).toBe('rw_1');
    expect(cards[0].taskAction.reason).toBe('bias_quality_core');
    expect(cards[0].taskRefreshSummary).toContain('宏观信号从 0 切到 1');
    expect(cards[0].taskRefreshSummary).toContain('政策源从 healthy 切到 fragile');
    expect(cards[0].taskRefreshSummary).toContain('偏置收缩从 full 切到 compressed');
    expect(cards[0].taskRefreshSummary).toContain('核心腿受压 XLE');
    expect(cards[0].latestTopCompressedAsset).toContain('XLE');
    expect(cards[0].taskRefreshTopCompressedAsset).toContain('XLE');
    expect(cards[0].taskRecentComparisonLead).toContain('目标版本已从普通结果进入复核型结果');
  });

  it('softly downgrades a template when recent snapshots switch review context without active downgraded run-state', () => {
    const cards = buildCrossMarketCards(
      {
        templates: [
          {
            id: 'utilities_vs_growth',
            name: 'Utilities vs Growth',
            description: 'Defensive utilities against growth beta',
            narrative: 'Defensive hedge',
            linked_factors: ['bureaucratic_friction'],
            linked_dimensions: ['inventory'],
            assets: [
              { symbol: 'XLU', side: 'long', weight: 0.5, asset_class: 'ETF' },
              { symbol: 'ARKK', side: 'long', weight: 0.5, asset_class: 'ETF' },
              { symbol: 'QQQ', side: 'short', weight: 0.5, asset_class: 'ETF' },
            ],
            preferred_signal: 'positive',
            construction_mode: 'equal_weight',
          },
        ],
      },
      {
        macro_signal: 0,
        macro_score: 0.41,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'healthy',
            reason: '主要政策源正文覆盖稳定',
            fragile_sources: [],
            watch_sources: [],
            healthy_sources: ['fed'],
            avg_full_text_ratio: 0.88,
          },
        },
        factors: [{ name: 'bureaucratic_friction', z_score: 0.3, value: 0.18, signal: 0 }],
        trend: { factor_deltas: {} },
      },
      { category_summary: {}, signals: {} },
      [
        {
          id: 'rw_review',
          type: 'cross_market',
          status: 'in_progress',
          template: 'utilities_vs_growth',
          updated_at: '2026-03-21T10:00:00',
          snapshot: {
            payload: {
              template_meta: {
                template_id: 'utilities_vs_growth',
                selection_quality: { label: 'original', reason: '原始推荐强度保留' },
              },
              research_input: {
                macro: {
                  macro_score: 0.41,
                  macro_signal: 0,
                  policy_source_health: { label: 'healthy', reason: '主要政策源正文覆盖稳定', avg_full_text_ratio: 0.88 },
                },
                alt_data: { top_categories: [] },
              },
              allocation_overlay: {
                selection_quality: {
                  label: 'original',
                  base_recommendation_score: 1.8,
                  effective_recommendation_score: 1.8,
                  base_recommendation_tier: '重点跟踪',
                  effective_recommendation_tier: '重点跟踪',
                  ranking_penalty: 0,
                  reason: '原始推荐强度保留',
                },
              },
            },
          },
          snapshot_history: [
            {
              payload: {
                template_meta: {
                  template_id: 'utilities_vs_growth',
                  selection_quality: { label: 'original', reason: '原始推荐强度保留' },
                },
              },
            },
            {
              payload: {
                template_meta: {
                  template_id: 'utilities_vs_growth',
                  selection_quality: { label: 'auto_downgraded', reason: '上一版曾为自动降级结果' },
                },
              },
            },
          ],
        },
      ]
    );

    expect(cards[0].taskRefreshReviewContextDriven).toBe(true);
    expect(cards[0].taskRefreshSelectionQualityActive).toBe(false);
    expect(cards[0].rankingPenalty).toBeCloseTo(0.24, 5);
    expect(cards[0].rankingPenaltyReason).toContain('复核语境');
  });

  it('surfaces department-chaos refresh metadata on cross-market cards', () => {
    const cards = buildCrossMarketCards(
      {
        templates: [
          {
            id: 'utilities_vs_growth',
            name: 'Utilities vs Growth',
            description: 'Defensive utilities against growth beta',
            narrative: 'Department policy chaos hedge',
            linked_factors: ['bureaucratic_friction'],
            linked_dimensions: ['policy'],
            assets: [
              { symbol: 'XLU', side: 'long', weight: 0.5, asset_class: 'ETF' },
              { symbol: 'ARKK', side: 'long', weight: 0.5, asset_class: 'ETF' },
              { symbol: 'QQQ', side: 'short', weight: 0.5, asset_class: 'ETF' },
            ],
            preferred_signal: 'positive',
            construction_mode: 'equal_weight',
          },
        ],
      },
      {
        macro_signal: 0,
        macro_score: 0.42,
        department_chaos_summary: {
          label: 'chaotic',
          summary: '发改委政策方向反复切换，长官意志强度抬升。',
          avg_chaos_score: 0.69,
          top_departments: [
            {
              department: 'ndrc',
              department_label: '发改委',
              label: 'chaotic',
              chaos_score: 0.74,
              reason: '政策反复与意志强度同步升高',
            },
          ],
        },
        evidence_summary: {
          policy_source_health_summary: {
            label: 'healthy',
            reason: '主要政策源正文覆盖稳定',
            fragile_sources: [],
            watch_sources: [],
            healthy_sources: ['ndrc'],
            avg_full_text_ratio: 0.88,
          },
        },
        resonance_summary: {
          label: 'mixed',
          reason: '当前因子变化尚未形成明确共振',
          positive_cluster: [],
          negative_cluster: [],
          weakening: [],
          precursor: [],
          reversed_factors: [],
        },
        factors: [{ name: 'bureaucratic_friction', z_score: 0.4, value: 0.22, signal: 0 }],
        trend: { factor_deltas: {} },
      },
      { category_summary: {}, signals: {} },
      [
        {
          id: 'rw_department',
          type: 'cross_market',
          status: 'in_progress',
          template: 'utilities_vs_growth',
          updated_at: '2026-03-21T10:00:00',
          snapshot: {
            payload: {
              template_meta: {
                template_id: 'utilities_vs_growth',
                bias_scale: 1,
                bias_quality_label: 'full',
              },
              research_input: {
                macro: {
                  macro_score: 0.41,
                  macro_signal: 0,
                  department_chaos: {
                    label: 'watch',
                    summary: '政策主体仍处观察区。',
                    avg_chaos_score: 0.35,
                    top_departments: [
                      { department: 'ndrc', department_label: '发改委', label: 'watch', chaos_score: 0.38 },
                    ],
                  },
                  policy_source_health: { label: 'healthy', reason: '主要政策源正文覆盖稳定', avg_full_text_ratio: 0.88 },
                  resonance: { label: 'mixed', positive_cluster: [], negative_cluster: [] },
                },
                alt_data: { top_categories: [] },
              },
            },
          },
        },
      ]
    );

    expect(cards[0].taskRefreshDepartmentChaosDriven).toBe(true);
    expect(cards[0].taskRefreshDepartmentChaosShift.currentLabel).toBe('chaotic');
    expect(cards[0].taskRefreshSummary).toContain('部门混乱从 watch 切到 chaotic');
    expect(cards[0].rankingPenalty).toBeCloseTo(0.18, 5);
    expect(cards[0].rankingPenaltyReason).toContain('部门混乱');
    expect(cards[0].taskAction.reason).toBe('policy_execution');
    expect(cards[0].taskAction.label).toBe('优先复核部门混乱');
    expect(cards[0].biasQualityLabel).toBe('chaos_guarded');
    expect(cards[0].departmentChaosRiskBudgetScale).toBeLessThan(1);
    expect(cards[0].rawAdjustedAssets).toHaveLength(3);
    expect(cards[0].adjustedAssets.find((item) => item.symbol === 'XLU').weight).toBeGreaterThan(0.5);
    expect(cards[0].adjustedAssets.find((item) => item.symbol === 'ARKK').weight).toBeLessThan(0.5);
    expect(cards[0].biasSummary).toContain('混乱触发防御化');
    expect(cards[0].driverSummary.some((item) => item.key === 'department_chaos_defensive')).toBe(true);
  });
});
