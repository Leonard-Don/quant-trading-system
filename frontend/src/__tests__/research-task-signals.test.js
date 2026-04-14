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

  it('elevates tasks when overall input reliability degrades even if policy-source health is unchanged', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        macro_score: 0.46,
        macro_signal: 0,
        input_reliability_summary: {
          label: 'fragile',
          score: 0.41,
          lead: '当前输入可靠度偏脆弱，主要风险来自时效偏旧与来源退化。',
          reason: 'effective confidence 0.41 · freshness aging · 风险 时效偏旧、来源退化',
        },
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
          id: 'task_input_reliability',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Input reliability thesis',
          template: 'energy_vs_ai_apps',
          snapshot: {
            payload: {
              research_input: {
                macro: {
                  macro_score: 0.45,
                  macro_signal: 0,
                  input_reliability: {
                    label: 'robust',
                    score: 0.84,
                    lead: '当前输入可靠度整体稳健。',
                  },
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    fragile_sources: [],
                    watch_sources: [],
                    healthy_sources: ['fed'],
                    avg_full_text_ratio: 0.88,
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
                bias_scale: 1,
                bias_quality_label: 'full',
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.task_input_reliability.inputReliabilityDriven).toBe(true);
    expect(model.byTaskId.task_input_reliability.inputReliabilityShift.savedLabel).toBe('robust');
    expect(model.byTaskId.task_input_reliability.inputReliabilityShift.currentLabel).toBe('fragile');
    expect(model.byTaskId.task_input_reliability.inputReliabilityShift.transition).toBe('enter_fragile');
    expect(model.byTaskId.task_input_reliability.inputReliabilityShift.actionHint).toContain('先复核当前宏观输入可靠度');
    expect(model.byTaskId.task_input_reliability.priorityReason).toBe('source_health_degradation');
    expect(model.byTaskId.task_input_reliability.summary).toContain('输入可靠度从 robust 切到 fragile');
    expect(model.byTaskId.task_input_reliability.recommendation).toContain('先复核当前宏观输入可靠度');
  });

  it('marks cross-market task for refresh when department-level policy chaos worsens', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        macro_score: 0.45,
        macro_signal: 0,
        department_chaos_summary: {
          label: 'chaotic',
          summary: '发改委政策方向反复切换，长官意志强度快速抬升。',
          avg_chaos_score: 0.68,
          top_departments: [
            {
              department: 'ndrc',
              department_label: '发改委',
              label: 'chaotic',
              chaos_score: 0.72,
              policy_reversal_count: 3,
              avg_will_intensity: 0.84,
              reason: '政策转向频繁且意志强度升高',
            },
          ],
        },
        evidence_summary: {
          policy_source_health_summary: {
            label: 'healthy',
            reason: '主要政策源正文覆盖稳定',
            fragile_sources: [],
            watch_sources: [],
            healthy_sources: ['ndrc', 'fed'],
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
        trend: {
          factor_deltas: {},
        },
      },
      snapshot: {
        category_summary: {},
      },
      researchTasks: [
        {
          id: 'task_department_chaos',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Utilities policy hedge',
          template: 'utilities_vs_growth',
          snapshot: {
            payload: {
              research_input: {
                macro: {
                  macro_score: 0.44,
                  macro_signal: 0,
                  department_chaos: {
                    label: 'watch',
                    summary: '政策主体仍在观察区。',
                    avg_chaos_score: 0.36,
                    top_departments: [
                      {
                        department: 'ndrc',
                        department_label: '发改委',
                        label: 'watch',
                        chaos_score: 0.42,
                      },
                    ],
                  },
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    fragile_sources: [],
                    watch_sources: [],
                    healthy_sources: ['ndrc', 'fed'],
                    avg_full_text_ratio: 0.88,
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
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.task_department_chaos.departmentChaosDriven).toBe(true);
    expect(model.byTaskId.task_department_chaos.departmentChaosShift.savedLabel).toBe('watch');
    expect(model.byTaskId.task_department_chaos.departmentChaosShift.currentLabel).toBe('chaotic');
    expect(model.byTaskId.task_department_chaos.departmentChaosShift.topDepartmentLabel).toBe('发改委');
    expect(model.byTaskId.task_department_chaos.priorityReason).toBe('policy_execution');
    expect(model.byTaskId.task_department_chaos.summary).toContain('部门混乱从 watch 切到 chaotic');
    expect(model.byTaskId.task_department_chaos.recommendation).toContain('部门级政策混乱');
  });

  it('marks cross-market task for refresh when structural decay radar escalates into alert', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        structural_decay_radar: {
          label: 'decay_alert',
          score: 0.74,
          critical_axis_count: 3,
          action_hint: '系统级脆弱性已经进入警报区，应收缩风险预算并强化防御/对冲腿。',
          top_signals: [
            { label: '组织脆弱', value: 0.82 },
            { label: '部门混乱', value: 0.78 },
          ],
        },
      },
      researchTasks: [
        {
          id: 'task_decay_radar',
          type: 'cross_market',
          status: 'in_progress',
          title: '[CrossMarket] Utilities vs Growth',
          template: 'utilities_vs_growth',
          snapshot: {
            payload: {
              research_input: {
                macro: {
                  macro_score: 0.44,
                  macro_signal: 0,
                  structural_decay_radar: {
                    label: 'stable',
                    score: 0.28,
                    critical_axis_count: 0,
                    action_hint: '系统级脆弱性仍在稳定区。',
                    top_signals: [],
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
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.task_decay_radar.structuralDecayRadarDriven).toBe(true);
    expect(model.byTaskId.task_decay_radar.priorityReason).toBe('structural_decay');
    expect(model.byTaskId.task_decay_radar.structuralDecayRadarShift.savedLabel).toBe('stable');
    expect(model.byTaskId.task_decay_radar.structuralDecayRadarShift.currentLabel).toBe('decay_alert');
    expect(model.byTaskId.task_decay_radar.structuralDecayRadarShift.topSignalSummary).toContain('组织脆弱');
    expect(model.byTaskId.task_decay_radar.summary).toContain('系统级衰败雷达从 stable 升级到 decay_alert');
    expect(model.byTaskId.task_decay_radar.recommendation).toContain('风险预算');
  });

  it('marks pricing task for refresh when people layer risk worsens materially', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        people_layer_summary: {
          label: 'fragile',
          summary: '当前跟踪样本的人事脆弱度均值抬升，高风险公司增加。',
          watchlist: [
            {
              symbol: 'BABA',
              company_name: '阿里巴巴',
              risk_level: 'high',
              stance: 'fragile',
              people_fragility_score: 0.78,
              people_quality_score: 0.34,
              summary: '资本市场和合规压力继续抬升，人的维度偏脆弱。',
            },
          ],
        },
      },
      researchTasks: [
        {
          id: 'pricing_people_shift',
          type: 'pricing',
          status: 'in_progress',
          title: '[Pricing] BABA mispricing review',
          symbol: 'BABA',
          snapshot: {
            payload: {
              people_layer: {
                symbol: 'BABA',
                risk_level: 'medium',
                stance: 'neutral',
                people_fragility_score: 0.46,
                people_quality_score: 0.5,
                summary: '当前组织结构压力可控。',
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.pricing_people_shift.peopleLayerDriven).toBe(true);
    expect(model.byTaskId.pricing_people_shift.priorityReason).toBe('people_fragility');
    expect(model.byTaskId.pricing_people_shift.peopleLayerShift.savedRiskLevel).toBe('medium');
    expect(model.byTaskId.pricing_people_shift.peopleLayerShift.currentRiskLevel).toBe('high');
    expect(model.byTaskId.pricing_people_shift.peopleLayerShift.enteredFragile).toBe(true);
    expect(model.byTaskId.pricing_people_shift.summary).toContain('人的维度从 medium 切到 high');
    expect(model.byTaskId.pricing_people_shift.recommendation).toContain('组织结构恶化');
  });

  it('marks macro mispricing task for refresh when linked pricing decay worsens further', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        people_layer_summary: {
          summary: '多家公司组织脆弱度抬升',
          watchlist: [
            {
              symbol: 'BABA',
              risk_level: 'high',
              stance: 'fragile',
              people_fragility_score: 0.84,
              people_quality_score: 0.32,
              summary: '技术权威继续被稀释，组织治理恶化。',
              hiring_signal: { dilution_ratio: 1.78 },
              insider_flow: { conviction_score: -0.26 },
            },
          ],
        },
      },
      snapshot: {},
      researchTasks: [
        {
          id: 'macro_decay_1',
          type: 'macro_mispricing',
          status: 'in_progress',
          title: '[MacroMispricing] BABA 结构性衰败观察',
          symbol: 'BABA',
          snapshot: {
            payload: {
              source_task_id: 'pricing_baba_1',
              people_layer: {
                risk_level: 'medium',
                stance: 'neutral',
                people_fragility_score: 0.58,
                people_quality_score: 0.46,
                hiring_signal: { dilution_ratio: 1.31 },
                insider_flow: { conviction_score: -0.08 },
              },
              structural_decay: {
                score: 0.61,
                label: '结构性衰败观察',
                action: 'watch',
                dominant_failure_label: '组织与治理稀释',
                evidence: ['人的维度开始转弱'],
              },
            },
          },
        },
        {
          id: 'pricing_baba_1',
          type: 'pricing',
          status: 'in_progress',
          title: '[Pricing] BABA mispricing review',
          symbol: 'BABA',
          snapshot: {
            payload: {
              structural_decay: {
                score: 0.83,
                label: '结构性衰败警报',
                action: 'structural_short',
                dominant_failure_label: '组织与治理稀释',
                summary: '结构性衰败判断进一步升级。',
                evidence: ['人的维度已进入高脆弱区间', '招聘稀释度 1.78', '内部人信号 -0.26'],
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.macro_decay_1.refreshLabel).toBe('建议更新');
    expect(model.byTaskId.macro_decay_1.severity).toBe('high');
    expect(model.byTaskId.macro_decay_1.structuralDecayDriven).toBe(true);
    expect(model.byTaskId.macro_decay_1.peopleLayerDriven).toBe(true);
    expect(model.byTaskId.macro_decay_1.priorityReason).toBe('structural_decay');
    expect(model.byTaskId.macro_decay_1.structuralDecayShift.currentAction).toBe('structural_short');
    expect(model.byTaskId.macro_decay_1.structuralDecayShift.evidenceSummary).toContain('招聘稀释度 1.78');
    expect(model.byTaskId.macro_decay_1.summary).toContain('衰败判断从 watch 升级到 structural_short');
  });

  it('marks trade thesis for refresh when linked pricing thesis changes its stance and lead leg', () => {
    const model = buildResearchTaskRefreshSignals({
      overview: {
        people_layer_summary: {
          summary: 'BABA 的组织脆弱度进一步抬升',
          watchlist: [
            {
              symbol: 'BABA',
              risk_level: 'high',
              stance: 'fragile',
              people_fragility_score: 0.79,
              people_quality_score: 0.33,
              summary: '管理与技术权威继续分化。',
            },
          ],
        },
      },
      researchTasks: [
        {
          id: 'trade_thesis_baba',
          type: 'trade_thesis',
          status: 'in_progress',
          title: '[TradeThesis] BABA macro mispricing basket',
          symbol: 'BABA',
          snapshot: {
            payload: {
              trade_thesis: {
                symbol: 'BABA',
                source_task_id: 'pricing_baba_trade',
                thesis: {
                  stance: '结构性做空',
                  horizon: '6-12m',
                  summary: '以 BABA 为主表达腿做长期对冲。',
                  trade_legs: [
                    { symbol: 'BABA', side: 'short', role: 'core_expression' },
                    { symbol: 'KWEB', side: 'long', role: 'beta_hedge' },
                  ],
                },
              },
              structural_decay: {
                score: 0.62,
                label: '结构性衰败观察',
                action: 'watch',
                dominant_failure_label: '组织与治理稀释',
              },
              people_layer: {
                risk_level: 'medium',
                stance: 'neutral',
                people_fragility_score: 0.52,
              },
            },
          },
        },
        {
          id: 'pricing_baba_trade',
          type: 'pricing',
          status: 'in_progress',
          title: '[Pricing] BABA mispricing review',
          symbol: 'BABA',
          snapshot: {
            payload: {
              macro_mispricing_thesis: {
                stance: '结构性回避',
                horizon: '3-6m',
                summary: '主表达腿应从单名义空头切到板块对冲。',
                trade_legs: [
                  { symbol: 'KWEB', side: 'short', role: 'core_expression' },
                  { symbol: 'BABA', side: 'short', role: 'support_expression' },
                  { symbol: 'FXI', side: 'long', role: 'beta_hedge' },
                ],
              },
              structural_decay: {
                score: 0.79,
                label: '结构性衰败警报',
                action: 'structural_avoid',
                dominant_failure_label: '组织与治理稀释',
                summary: '结构性衰败继续走坏。',
              },
            },
          },
        },
      ],
    });

    expect(model.byTaskId.trade_thesis_baba.tradeThesisDriven).toBe(true);
    expect(model.byTaskId.trade_thesis_baba.priorityReason).toBe('structural_decay');
    expect(model.byTaskId.trade_thesis_baba.tradeThesisShift.stanceChanged).toBe(true);
    expect(model.byTaskId.trade_thesis_baba.tradeThesisShift.leadLegChanged).toBe(true);
    expect(model.byTaskId.trade_thesis_baba.tradeThesisShift.currentLeadLeg).toBe('KWEB');
    expect(model.byTaskId.trade_thesis_baba.summary).toContain('交易 Thesis 从 结构性做空 切到 结构性回避');
    expect(model.byTaskId.trade_thesis_baba.recommendation).toContain('交易 Thesis');
  });
});
