import { buildHunterModel } from '../components/GodEyeDashboard/viewModels';

describe('buildHunterModel narrative shifts', () => {
  it('adds a cross-market alert when dominant driver and theme core change across research snapshots', () => {
    const alerts = buildHunterModel({
      snapshot: {
        category_summary: {
          inventory: { delta_score: 0.29, momentum: 'strengthening' },
        },
      },
      overview: {
        macro_score: 0.77,
        macro_signal: 1,
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
        trend: {
          factor_deltas: {
            growth_pressure: { z_score_delta: 0.41, signal_changed: true },
          },
        },
      },
      status: {},
      researchTasks: [
        {
          id: 'task_1',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Energy vs AI thesis',
          template: 'energy_vs_ai_apps',
          updated_at: '2026-03-20T10:00:00',
          snapshot: {
            payload: {
              template_meta: {
                template_id: 'energy_vs_ai_apps',
                bias_scale: 1,
                bias_quality_label: 'full',
                bias_quality_reason: '主要政策源正文覆盖稳定',
                dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.31 }],
                theme_core: 'XLE+8.5pp',
                theme_support: 'SOXX',
              },
              research_input: {
                macro: {
                  macro_score: 0.35,
                  macro_signal: 0,
                  policy_source_health: {
                    label: 'healthy',
                    reason: '主要政策源正文覆盖稳定',
                    avg_full_text_ratio: 0.88,
                  },
                },
                alt_data: {
                  top_categories: [
                    { category: 'inventory', delta_score: 0.04, momentum: 'stable' },
                  ],
                },
              },
              allocation_overlay: {
                selection_quality: {
                  label: 'auto_downgraded',
                  base_recommendation_score: 3.05,
                  effective_recommendation_score: 2.6,
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
                    reason: '当前主题已进入自动降级处理，默认模板选择谨慎下调',
                  },
                  dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.31 }],
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
                  dominant_drivers: [{ key: 'baseload_support', label: '基建/基荷支撑', value: 0.19 }],
                  theme_core: 'HG=F+4.0pp',
                  theme_support: 'IGV',
                },
              },
            },
          ],
        },
      ],
    });

    expect(alerts.some((item) => item.title.includes('主导叙事切换'))).toBe(true);
    const shiftAlert = alerts.find((item) => item.key === 'narrative-shift-energy_vs_ai_apps');
    expect(shiftAlert.severity).toBe('high');
    expect(shiftAlert.description).toContain('主导驱动从 基建/基荷支撑 切换到 成长端估值压力');
    expect(shiftAlert.action.target).toBe('cross-market');
    expect(shiftAlert.action.template).toBe('energy_vs_ai_apps');
    const refreshAlert = alerts.find((item) => item.key === 'refresh-task_1');
    expect(refreshAlert).toBeTruthy();
    expect(refreshAlert.title).toContain('建议更新');
    expect(refreshAlert.action.target).toBe('workbench');
    expect(refreshAlert.action.label).toBe('优先重看任务');
    expect(refreshAlert.action.taskId).toBe('task_1');
    expect(refreshAlert.action.reason).toBe('bias_quality_core');
    expect(refreshAlert.description).toContain('政策源从 healthy 切到 fragile');
    expect(refreshAlert.description).toContain('偏置收缩从 full 切到 compressed');
    expect(refreshAlert.description).toContain('核心腿受压 XLE');
    expect(refreshAlert.description).toContain('最近两版：目标版本已从普通结果进入复核型结果');
    expect(refreshAlert.description).toContain('降级运行 auto_downgraded');
    expect(refreshAlert.description).toContain('当前结果已在降级强度下运行，应优先重看');
    expect(refreshAlert.description).toContain('压缩焦点 XLE');
  });

  it('adds a resonance alert when multiple macro factors strengthen together', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        resonance_summary: {
          label: 'bullish_cluster',
          reason: '多个宏观因子同时强化正向扭曲，形成上行共振',
          positive_cluster: ['bureaucratic_friction', 'baseload_mismatch'],
          negative_cluster: [],
          weakening: [],
          precursor: [],
          reversed_factors: [],
        },
      },
      status: {},
      researchTasks: [],
    });

    const resonanceAlert = alerts.find((item) => item.key === 'resonance-bullish_cluster');
    expect(resonanceAlert).toBeTruthy();
    expect(resonanceAlert.severity).toBe('high');
    expect(resonanceAlert.description).toContain('官僚摩擦');
    expect(resonanceAlert.action.target).toBe('cross-market');
  });

  it('adds a pricing alert when people-layer flags fragile companies', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        people_layer_summary: {
          fragile_companies: [
            {
              symbol: 'BABA',
              company_name: '阿里巴巴',
              people_fragility_score: 0.72,
              summary: '阿里巴巴 的人事层结论偏脆弱，组织质量 0.38 / 脆弱度 0.67。',
            },
          ],
        },
      },
      status: {},
      researchTasks: [],
    });

    const peopleAlert = alerts.find((item) => item.key === 'people-BABA');
    expect(peopleAlert).toBeTruthy();
    expect(peopleAlert.severity).toBe('high');
    expect(peopleAlert.title).toContain('组织脆弱度偏高');
    expect(peopleAlert.action.target).toBe('pricing');
    expect(peopleAlert.action.symbol).toBe('BABA');
  });

  it('adds a cross-market alert when department chaos becomes elevated', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        department_chaos_summary: {
          label: 'chaotic',
          top_departments: [
            {
              department: 'ndrc',
              department_label: '发改委',
              label: 'chaotic',
              chaos_score: 0.74,
              reason: '方向反复 2 次，长官意志 0.72',
            },
          ],
        },
      },
      status: {},
      researchTasks: [],
    });

    const departmentAlert = alerts.find((item) => item.key === 'department-chaos-ndrc');
    expect(departmentAlert).toBeTruthy();
    expect(departmentAlert.severity).toBe('high');
    expect(departmentAlert.title).toContain('发改委 政策混乱度偏高');
    expect(departmentAlert.description).toContain('方向反复');
    expect(departmentAlert.action.target).toBe('cross-market');
  });

  it('explains people-layer evidence in pricing refresh alerts and routes pricing tasks correctly', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        people_layer_summary: {
          watchlist: [
            {
              symbol: 'BABA',
              company_name: '阿里巴巴',
              risk_level: 'high',
              stance: 'fragile',
              people_fragility_score: 0.78,
              people_quality_score: 0.34,
              summary: '资本市场和合规压力继续抬升，人的维度偏脆弱。',
              hiring_signal: {
                dilution_ratio: 1.72,
              },
              insider_flow: {
                conviction_score: -0.24,
              },
            },
          ],
        },
      },
      status: {},
      researchTasks: [
        {
          id: 'pricing_people_refresh',
          type: 'pricing',
          status: 'in_progress',
          title: '[Pricing] BABA mispricing review',
          symbol: 'BABA',
          updated_at: '2026-03-22T10:00:00',
          snapshot: {
            payload: {
              people_layer: {
                symbol: 'BABA',
                risk_level: 'medium',
                stance: 'neutral',
                people_fragility_score: 0.46,
                people_quality_score: 0.5,
                summary: '当前组织结构压力可控。',
                hiring_signal: {
                  dilution_ratio: 1.32,
                },
                insider_flow: {
                  conviction_score: -0.08,
                },
              },
            },
          },
        },
      ],
    });

    const refreshAlert = alerts.find((item) => item.key === 'refresh-pricing_people_refresh');
    expect(refreshAlert).toBeTruthy();
    expect(refreshAlert.description).toContain('人的维度已进入高风险区');
    expect(refreshAlert.description).toContain('人事证据 招聘稀释度 1.32→1.72');
    expect(refreshAlert.description).toContain('内部人信号 -0.08→-0.24');
    expect(refreshAlert.action.target).toBe('workbench');
    expect(refreshAlert.action.taskId).toBe('pricing_people_refresh');
    expect(refreshAlert.action.type).toBe('pricing');
    expect(refreshAlert.action.reason).toBe('people_fragility');
    expect(refreshAlert.action.label).toBe('优先复核人的维度');
  });

  it('surfaces input-reliability deterioration in refresh alerts', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        macro_score: 0.46,
        macro_signal: 1,
        input_reliability_summary: {
          label: 'fragile',
          score: 0.41,
          lead: '当前输入可靠度偏脆弱，主要风险来自时效偏旧与来源退化。',
          reason: 'effective confidence 0.41 · freshness aging',
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
        trend: { factor_deltas: {} },
      },
      status: {},
      researchTasks: [
        {
          id: 'task_input_reliability',
          type: 'cross_market',
          status: 'in_progress',
          title: 'Input reliability thesis',
          template: 'energy_vs_ai_apps',
          updated_at: '2026-03-22T10:00:00',
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
                    avg_full_text_ratio: 0.88,
                  },
                },
                alt_data: {
                  top_categories: [],
                },
              },
              template_meta: {
                template_id: 'energy_vs_ai_apps',
              },
            },
          },
        },
      ],
    });

    const refreshAlert = alerts.find((item) => item.key === 'refresh-task_input_reliability');
    expect(refreshAlert).toBeTruthy();
    expect(refreshAlert.description).toContain('输入可靠度 robust→fragile');
    expect(refreshAlert.action.reason).toBe('source_health_degradation');
    expect(refreshAlert.action.label).toBe('先复核输入可靠度');
    expect(refreshAlert.action.note).toContain('先复核当前宏观输入可靠度');
  });

  it('promotes worsening macro mispricing tasks into GodEye hunter alerts', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        people_layer_summary: {
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
      status: {},
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

    const refreshAlert = alerts.find((item) => item.key === 'refresh-macro_decay_1');
    expect(refreshAlert).toBeTruthy();
    expect(refreshAlert.title).toContain('建议更新');
    expect(refreshAlert.description).toContain('衰败判断从 watch 升级到 structural_short');
    expect(refreshAlert.description).toContain('衰败证据');
    expect(refreshAlert.description).toContain('招聘稀释度 1.78');
    expect(refreshAlert.action.target).toBe('workbench');
    expect(refreshAlert.action.type).toBe('macro_mispricing');
    expect(refreshAlert.action.reason).toBe('structural_decay');
    expect(refreshAlert.action.label).toBe('优先复核衰败判断');
  });

  it('promotes drifting trade thesis tasks into GodEye hunter alerts', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        people_layer_summary: {
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
      status: {},
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
            },
          },
        },
      ],
    });

    const refreshAlert = alerts.find((item) => item.key === 'refresh-trade_thesis_baba');
    expect(refreshAlert).toBeTruthy();
    expect(refreshAlert.description).toContain('交易 Thesis 从 结构性做空 切到 结构性回避');
    expect(refreshAlert.description).toContain('Thesis 证据');
    expect(refreshAlert.action.target).toBe('workbench');
    expect(refreshAlert.action.type).toBe('trade_thesis');
    expect(refreshAlert.action.reason).toBe('trade_thesis');
    expect(refreshAlert.action.label).toBe('优先复核交易 Thesis');
  });

  it('surfaces structural decay radar escalation as a cross-market hunter alert', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        structural_decay_radar: {
          label: 'decay_alert',
          display_label: '结构衰败警报',
          score: 0.74,
          action_hint: '人的维度、治理与执行证据已经共振。',
        },
      },
      status: {},
      researchTasks: [],
    });

    const radarAlert = alerts.find((item) => item.key === 'structural-decay-radar');
    expect(radarAlert).toBeTruthy();
    expect(radarAlert.severity).toBe('high');
    expect(radarAlert.description).toContain('结构衰败警报');
    expect(radarAlert.action.target).toBe('cross-market');
    expect(radarAlert.action.template).toBe('defensive_beta_hedge');
    expect(radarAlert.action.source).toBe('decay_radar');
  });

  it('surfaces a source-governance alert when research inputs become fallback-heavy', () => {
    const alerts = buildHunterModel({
      snapshot: {},
      overview: {
        source_mode_summary: {
          label: 'fallback-heavy',
          reason: '当前研究输入由 proxy/curated 回退源主导，建议压缩偏置强度。',
        },
      },
      status: {},
      researchTasks: [],
    });

    const sourceAlert = alerts.find((item) => item.key === 'source-mode-fallback-heavy');
    expect(sourceAlert).toBeTruthy();
    expect(sourceAlert.severity).toBe('medium');
    expect(sourceAlert.description).toContain('proxy/curated');
  });
});
