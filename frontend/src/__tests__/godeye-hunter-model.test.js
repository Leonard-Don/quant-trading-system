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
    expect(refreshAlert.action.taskId).toBe('task_1');
    expect(refreshAlert.action.reason).toBe('bias_quality_core');
    expect(refreshAlert.description).toContain('政策源从 healthy 切到 fragile');
    expect(refreshAlert.description).toContain('偏置收缩从 full 切到 compressed');
    expect(refreshAlert.description).toContain('核心腿受压 XLE');
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
});
