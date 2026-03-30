import { buildResearchTaskRefreshSignals } from '../utils/researchTaskSignals';

describe('buildResearchTaskRefreshSignals', () => {
  it('marks cross-market task for refresh when current macro and alt inputs drift materially', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        macro_score: 0.81,
        macro_signal: 1,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'fragile',
            reason: '正文抓取脆弱源 ndrc',
            fragile_sources: ['ndrc'],
            watch_sources: [],
            healthy_sources: ['fed'],
            avg_full_text_ratio: 0.42,
          },
        },
        resonance_summary: {
          label: 'bullish_cluster',
          reason: '多个宏观因子同时强化正向扭曲，形成上行共振',
          positive_cluster: ['baseload_mismatch'],
          negative_cluster: [],
          weakening: [],
          precursor: [],
          reversed_factors: [],
        },
        trend: {
          factor_deltas: {
            baseload_mismatch: { z_score_delta: 0.42, signal_changed: true },
          },
        },
      },
      snapshot: {
        category_summary: {
          inventory: { delta_score: 0.34, momentum: 'strengthening' },
          trade: { delta_score: -0.21, momentum: 'weakening' },
        },
      },
      researchTasks: [
        {
          id: 'task_1',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Energy vs AI thesis',
          template: 'energy_vs_ai_apps',
          snapshot: {
            payload: {
              research_input: {
                macro: {
                  macro_score: 0.42,
                  macro_signal: 0,
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    fragile_sources: [],
                    watch_sources: [],
                    healthy_sources: ['ndrc', 'fed'],
                    avg_full_text_ratio: 0.86,
                  },
                  resonance: {
                    label: 'mixed',
                    reason: '当前因子变化尚未形成明确共振',
                    positive_cluster: [],
                    negative_cluster: [],
                    weakening: [],
                    precursor: [],
                    reversed_factors: [],
                  },
                },
                alt_data: {
                  top_categories: [
                    { category: 'inventory', delta_score: 0.08, momentum: 'stable' },
                  ],
                },
              },
              template_meta: {
                template_id: 'energy_vs_ai_apps',
                bias_scale: 1,
                bias_quality_label: 'full',
                bias_quality_reason: '主要政策源正文覆盖稳定',
                dominant_drivers: [{ key: 'baseload_mismatch', label: '基荷错配', value: 0.22 }],
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.task_1.refreshLabel).toBe('建议更新');
    expect(model.byTaskId.task_1.severity).toBe('high');
    expect(model.byTaskId.task_1.resonanceDriven).toBe(true);
    expect(model.byTaskId.task_1.policySourceDriven).toBe(true);
    expect(model.byTaskId.task_1.biasCompressionDriven).toBe(true);
    expect(model.byTaskId.task_1.priorityReason).toBe('resonance');
    expect(model.byTaskId.task_1.policySourceShift.currentLabel).toBe('fragile');
    expect(model.byTaskId.task_1.biasCompressionShift.currentLabel).toBe('compressed');
    expect(model.byTemplateId.energy_vs_ai_apps.summary).toContain('宏观信号从 0 切到 1');
    expect(model.byTemplateId.energy_vs_ai_apps.summary).toContain('共振从 mixed 切到 bullish_cluster');
    expect(model.byTemplateId.energy_vs_ai_apps.summary).toContain('政策源从 healthy 切到 fragile');
    expect(model.byTemplateId.energy_vs_ai_apps.summary).toContain('偏置收缩从 full 切到 compressed');
    expect(model.byTaskId.task_1.resonanceShift.currentLabel).toBe('bullish_cluster');
    expect(model.prioritized[0].factorShift[0].label).toBe('基荷错配');
  });

  it('prioritizes core-leg compression above ordinary bias compression when resonance is absent', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        macro_score: 0.46,
        macro_signal: 0,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'fragile',
            reason: '正文抓取脆弱源 ndrc',
            fragile_sources: ['ndrc'],
            watch_sources: [],
            healthy_sources: ['fed'],
            avg_full_text_ratio: 0.42,
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
        trend: {
          factor_deltas: {},
        },
      },
      snapshot: {
        category_summary: {},
      },
      researchTasks: [
        {
          id: 'task_core',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Utilities hedge thesis',
          template: 'utilities_vs_growth',
          snapshot: {
            payload: {
              research_input: {
                macro: {
                  macro_score: 0.44,
                  macro_signal: 0,
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    fragile_sources: [],
                    watch_sources: [],
                    healthy_sources: ['ndrc', 'fed'],
                    avg_full_text_ratio: 0.86,
                  },
                  resonance: {
                    label: 'mixed',
                    reason: '当前因子变化尚未形成明确共振',
                    positive_cluster: [],
                    negative_cluster: [],
                    weakening: [],
                    precursor: [],
                    reversed_factors: [],
                  },
                },
                alt_data: {
                  top_categories: [],
                },
              },
              template_meta: {
                template_id: 'utilities_vs_growth',
                bias_scale: 1,
                bias_quality_label: 'full',
                bias_quality_reason: '主要政策源正文覆盖稳定',
                theme_core: 'XLU+6.0pp',
                core_legs: [{ symbol: 'XLU' }],
              },
              allocation_overlay: {
                rows: [
                  { symbol: 'XLU', compression_delta: 0.027 },
                  { symbol: 'QQQ', compression_delta: 0.011 },
                ],
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.task_core.biasCompressionDriven).toBe(true);
    expect(model.byTaskId.task_core.selectionQualityDriven).toBe(true);
    expect(model.byTaskId.task_core.biasCompressionShift.coreLegAffected).toBe(true);
    expect(model.byTaskId.task_core.biasCompressionShift.topCompressedAsset).toContain('XLU');
    expect(model.byTaskId.task_core.priorityReason).toBe('bias_quality_core');
    expect(model.byTaskId.task_core.priorityWeight).toBe(4);
    expect(model.byTaskId.task_core.summary).toContain('核心腿受压 XLU');
    expect(model.byTaskId.task_core.summary).toContain('自动降级从 original 切到 auto_downgraded');
  });

  it('treats non-core auto-downgrade as a standalone refresh reason', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        macro_score: 0.41,
        macro_signal: 0,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'fragile',
            reason: '正文抓取脆弱源 ndrc',
            fragile_sources: ['ndrc'],
            watch_sources: [],
            healthy_sources: ['fed'],
            avg_full_text_ratio: 0.41,
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
        trend: {
          factor_deltas: {},
        },
      },
      snapshot: {
        category_summary: {},
      },
      researchTasks: [
        {
          id: 'task_softened',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Defensive beta hedge',
          template: 'defensive_beta_hedge',
          snapshot: {
            payload: {
              research_input: {
                macro: {
                  macro_score: 0.4,
                  macro_signal: 0,
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    fragile_sources: [],
                    watch_sources: [],
                    healthy_sources: ['fed', 'ndrc'],
                    avg_full_text_ratio: 0.86,
                  },
                  resonance: {
                    label: 'mixed',
                    reason: '当前因子变化尚未形成明确共振',
                    positive_cluster: [],
                    negative_cluster: [],
                    weakening: [],
                    precursor: [],
                    reversed_factors: [],
                  },
                },
                alt_data: {
                  top_categories: [],
                },
              },
              template_meta: {
                template_id: 'defensive_beta_hedge',
                selection_quality: {
                  label: 'original',
                  reason: '原始推荐强度保留',
                },
                ranking_penalty: 0,
                bias_scale: 1,
                bias_quality_label: 'full',
                bias_quality_reason: '主要政策源正文覆盖稳定',
                theme_core: 'XLV+3.0pp',
                core_legs: [{ symbol: 'XLV' }],
              },
              allocation_overlay: {
                selection_quality: {
                  label: 'softened',
                  base_recommendation_score: 2.8,
                  effective_recommendation_score: 2.32,
                  base_recommendation_tier: 'high conviction',
                  effective_recommendation_tier: 'watchlist',
                  ranking_penalty: 0.2,
                  reason: '当前主题已进入自动降级处理，默认模板选择谨慎下调',
                },
                rows: [
                  { symbol: 'SPY', compression_delta: 0.018 },
                ],
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.task_softened.selectionQualityDriven).toBe(true);
    expect(model.byTaskId.task_softened.selectionQualityRunState.active).toBe(true);
    expect(model.byTaskId.task_softened.biasCompressionShift.coreLegAffected).toBe(false);
    expect(model.byTaskId.task_softened.selectionQualityShift.currentLabel).toBe('softened');
    expect(model.byTaskId.task_softened.selectionQualityRunState.label).toBe('softened');
    expect(model.byTaskId.task_softened.priorityReason).toBe('selection_quality_active');
    expect(model.byTaskId.task_softened.priorityWeight).toBe(3.75);
    expect(model.byTaskId.task_softened.summary).toContain('自动降级从 original 切到 softened');
    expect(model.byTaskId.task_softened.summary).toContain('当前结果已按 softened 强度运行');
    expect(model.byTaskId.task_softened.recommendation).toContain('降级运行状态');
  });

  it('marks review-context shift when latest snapshots move from ordinary to review result', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        macro_score: 0.4,
        macro_signal: 0,
        evidence_summary: {
          policy_source_health_summary: {
            label: 'healthy',
            reason: '主要政策源正文覆盖稳定',
            fragile_sources: [],
            watch_sources: [],
            healthy_sources: ['fed'],
            avg_full_text_ratio: 0.86,
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
        trend: {
          factor_deltas: {},
        },
      },
      snapshot: {
        category_summary: {},
      },
      researchTasks: [
        {
          id: 'task_review_context',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Review context shift',
          template: 'energy_vs_ai_apps',
          snapshot: {
            payload: {
              research_input: {
                macro: {
                  macro_score: 0.4,
                  macro_signal: 0,
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    fragile_sources: [],
                    watch_sources: [],
                    healthy_sources: ['fed'],
                    avg_full_text_ratio: 0.86,
                  },
                  resonance: {
                    label: 'mixed',
                    reason: '当前因子变化尚未形成明确共振',
                    positive_cluster: [],
                    negative_cluster: [],
                    weakening: [],
                    precursor: [],
                    reversed_factors: [],
                  },
                },
                alt_data: {
                  top_categories: [],
                },
              },
              template_meta: {
                template_id: 'energy_vs_ai_apps',
                selection_quality: {
                  label: 'original',
                  reason: '原始推荐强度保留',
                },
                ranking_penalty: 0,
              },
              allocation_overlay: {
                selection_quality: {
                  label: 'original',
                  base_recommendation_score: 3.1,
                  effective_recommendation_score: 3.1,
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
              headline: 'Energy vs AI 跨市场复核型结果',
              payload: {
                template_meta: {
                  template_id: 'energy_vs_ai_apps',
                  selection_quality: {
                    label: 'softened',
                    reason: '当前主题已进入自动降级处理',
                  },
                },
                allocation_overlay: {
                  selection_quality: {
                    label: 'softened',
                  },
                },
              },
            },
            {
              headline: 'Energy vs AI 跨市场结果',
              payload: {
                template_meta: {
                  template_id: 'energy_vs_ai_apps',
                  selection_quality: {
                    label: 'original',
                    reason: '原始推荐强度保留',
                  },
                },
                allocation_overlay: {
                  selection_quality: {
                    label: 'original',
                  },
                },
              },
            },
          ],
        },
      ],
    });

    expect(model.byTaskId.task_review_context.reviewContextDriven).toBe(true);
    expect(model.byTaskId.task_review_context.reviewContextShift.enteredReview).toBe(true);
    expect(model.byTaskId.task_review_context.reviewContextShift.lead).toContain('最近两版已从普通结果切到复核型结果');
    expect(model.byTaskId.task_review_context.summary).toContain('最近两版已从普通结果切到复核型结果');
  });
});
