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
        baseRecommendationTier: '优先部署',
        recommendationScore: 3.2,
        baseRecommendationScore: 3.65,
        rankingPenalty: 0.45,
        rankingPenaltyReason: '核心腿 XLE 已进入压缩焦点，主题排序自动降级',
        resonanceLabel: 'bullish_cluster',
        resonanceReason: '多个宏观因子同时强化正向扭曲，形成上行共振',
        driverHeadline: '基荷错配(z=1.80) · 投资活跃度(score=0.40)',
        biasSummary: '多头增配 XLE，空头增配 IGV',
        rawBiasStrength: 11.8,
        biasStrength: 8.5,
        biasScale: 0.55,
        biasQualityLabel: 'compressed',
        biasQualityReason: '正文抓取脆弱源 ndrc，宏观偏置已收缩',
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
      ],
      {
        macroOverview: {
          macro_score: 0.73,
          macro_signal: 1,
          confidence: 0.82,
          snapshot_timestamp: '2026-03-20T10:00:00',
          input_reliability_summary: {
            label: 'watch',
            score: 0.63,
            lead: '当前输入可靠度需要持续观察，主要受政策源质量波动影响。',
            posture: '当前宏观输入更适合作为研究排序与提示信号。',
            reason: 'effective confidence 0.63 · freshness recent · policy source watch',
            dominant_issue_labels: ['政策源脆弱'],
            dominant_support_labels: ['跨源确认'],
          },
          evidence_summary: {
            policy_source_health_summary: {
              label: 'watch',
              reason: '正文抓取需关注 ndrc',
              fragile_sources: [],
              watch_sources: ['ndrc'],
              healthy_sources: ['fed'],
              avg_full_text_ratio: 0.68,
            },
          },
          trend: {
            macro_score_delta: 0.18,
            macro_signal_changed: true,
            factor_deltas: {
              baseload_mismatch: { z_score_delta: 0.42, signal_changed: true },
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
        },
        altSnapshot: {
          snapshot_timestamp: '2026-03-20T10:05:00',
          staleness: { label: 'fresh', max_snapshot_age_seconds: 320 },
          category_summary: {
            policy: { count: 5, avg_score: 0.31, delta_score: 0.15, momentum: 'strengthening' },
            customs: { count: 4, avg_score: -0.22, delta_score: -0.13, momentum: 'weakening' },
          },
        },
      }
    );

    expect(payload.context.theme).toBe('Baseload scarcity vs AI application enthusiasm');
    expect(payload.context.base_recommendation_tier).toBe('优先部署');
    expect(payload.context.recommendation_tier).toBe('优先部署');
    expect(payload.context.base_recommendation_score).toBe(3.65);
    expect(payload.context.recommendation_score).toBe(3.2);
    expect(payload.context.ranking_penalty).toBe(0.45);
    expect(payload.context.ranking_penalty_reason).toContain('核心腿 XLE');
    expect(payload.context.selection_quality.label).toBe('softened');
    expect(payload.context.recommendation_reason).toContain('基荷错配');
    expect(payload.context.resonance_label).toBe('bullish_cluster');
    expect(payload.context.resonance_reason).toContain('上行共振');
    expect(payload.context.allocation_mode).toBe('macro_bias');
    expect(payload.context.bias_summary).toContain('多头增配');
    expect(payload.context.bias_strength_raw).toBe(11.8);
    expect(payload.context.bias_scale).toBe(0.55);
    expect(payload.context.bias_quality_label).toBe('compressed');
    expect(payload.context.bias_actions).toHaveLength(2);
    expect(payload.context.driver_summary).toHaveLength(2);
    expect(payload.context.theme_core).toContain('XLE');
    expect(payload.context.core_leg_pressure.affected).toBe(false);
    expect(payload.context.research_input.macro.macro_score).toBe(0.73);
    expect(payload.context.research_input.macro.macro_signal_changed).toBe(true);
    expect(payload.context.research_input.macro.policy_source_health.label).toBe('watch');
    expect(payload.context.research_input.macro.policy_source_health.reason).toContain('ndrc');
    expect(payload.context.research_input.macro.input_reliability.label).toBe('watch');
    expect(payload.context.research_input.macro.input_reliability.lead).toContain('输入可靠度需要持续观察');
    expect(payload.context.research_input.macro.input_reliability.posture).toContain('研究排序与提示信号');
    expect(payload.context.research_input.alt_data.top_categories).toHaveLength(2);
    expect(payload.context.input_reliability.label).toBe('watch');
    expect(payload.context.input_reliability.posture).toContain('研究排序与提示信号');
    expect(payload.snapshot.payload.template_meta.theme).toBe(payload.context.theme);
    expect(payload.snapshot.payload.template_meta.base_recommendation_tier).toBe('优先部署');
    expect(payload.snapshot.payload.template_meta.recommendation_tier).toBe('优先部署');
    expect(payload.snapshot.payload.template_meta.base_recommendation_score).toBe(3.65);
    expect(payload.snapshot.payload.template_meta.recommendation_score).toBe(3.2);
    expect(payload.snapshot.payload.template_meta.ranking_penalty).toBe(0.45);
    expect(payload.snapshot.payload.template_meta.ranking_penalty_reason).toContain('核心腿 XLE');
    expect(payload.snapshot.payload.template_meta.selection_quality.label).toBe('softened');
    expect(payload.snapshot.payload.template_meta.resonance_label).toBe('bullish_cluster');
    expect(payload.snapshot.payload.template_meta.resonance_reason).toContain('上行共振');
    expect(payload.snapshot.payload.template_meta.recommendation_reason).toContain('投资活跃度');
    expect(payload.snapshot.payload.template_meta.bias_summary).toContain('IGV');
    expect(payload.snapshot.payload.template_meta.bias_strength_raw).toBe(11.8);
    expect(payload.snapshot.payload.template_meta.bias_scale).toBe(0.55);
    expect(payload.snapshot.payload.template_meta.bias_quality_label).toBe('compressed');
    expect(payload.snapshot.payload.template_meta.bias_actions[0].symbol).toBe('XLE');
    expect(payload.snapshot.payload.template_meta.driver_summary[0].label).toContain('基建');
    expect(payload.snapshot.payload.template_meta.theme_support).toBe('IGV');
    expect(payload.snapshot.payload.template_meta.core_leg_pressure.affected).toBe(false);
    expect(payload.snapshot.payload.research_input.macro.macro_score_delta).toBe(0.18);
    expect(payload.snapshot.payload.research_input.macro.resonance.label).toBe('bullish_cluster');
    expect(payload.snapshot.payload.research_input.macro.policy_source_health.avg_full_text_ratio).toBe(0.68);
    expect(payload.snapshot.payload.research_input.macro.input_reliability.score).toBe(0.63);
    expect(payload.snapshot.payload.template_meta.input_reliability.label).toBe('watch');
    expect(payload.snapshot.payload.template_meta.input_reliability.posture).toContain('研究排序与提示信号');
    expect(payload.snapshot.payload.research_input.alt_data.top_categories[0].category).toBe('policy');
  });

  it('persists core-leg pressure when the compression focus hits a core leg', () => {
    const payload = buildCrossMarketWorkbenchPayload(
      { source: 'cross_market_panel', template: 'utilities_vs_growth' },
      {
        id: 'utilities_vs_growth',
        name: 'Utilities vs Growth',
        themeCore: 'XLU+6.0pp',
        coreLegs: [{ symbol: 'XLU', side: 'long', role: 'core', delta: 6 }],
      },
      {
        allocation_overlay: {
          selection_quality: {
            label: 'auto_downgraded',
            base_recommendation_score: 3.4,
            effective_recommendation_score: 2.95,
            base_recommendation_tier: '重点跟踪',
            effective_recommendation_tier: '观察中',
            ranking_penalty: 0.45,
            reason: '核心腿 XLU 已进入压缩焦点，主题排序自动降级',
          },
          rows: [
            { symbol: 'XLU', compression_delta: 0.026 },
            { symbol: 'QQQ', compression_delta: 0.01 },
          ],
        },
      },
      [],
      {}
    );

    expect(payload.context.core_leg_pressure.affected).toBe(true);
    expect(payload.context.core_leg_pressure.symbol).toBe('XLU');
    expect(payload.context.core_leg_pressure.summary).toContain('XLU');
    expect(payload.context.selection_quality.label).toBe('auto_downgraded');
    expect(payload.context.base_recommendation_score).toBe(3.4);
    expect(payload.context.recommendation_score).toBe(2.95);
    expect(payload.context.ranking_penalty).toBe(0.45);
    expect(payload.snapshot.headline).toContain('复核型结果');
    expect(payload.snapshot.summary).toContain('复核型回测结果');
    expect(payload.snapshot.summary).toContain('auto_downgraded');
    expect(payload.snapshot.payload.template_meta.core_leg_pressure.affected).toBe(true);
    expect(payload.snapshot.payload.template_meta.selection_quality.label).toBe('auto_downgraded');
  });
});
