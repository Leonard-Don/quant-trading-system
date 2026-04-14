import { buildSnapshotComparison } from '../components/research-workbench/snapshotCompare';

describe('buildSnapshotComparison for cross-market snapshots', () => {
  it('includes execution-plan and recommendation metadata deltas', () => {
    const comparison = buildSnapshotComparison(
      'cross_market',
      {
        payload: {
          total_return: 0.08,
          sharpe_ratio: 1.1,
          data_alignment: { tradable_day_ratio: 0.82 },
          execution_diagnostics: {
            cost_drag: 0.01,
            turnover: 4.2,
            construction_mode: 'equal_weight',
            concentration_level: 'moderate',
            liquidity_level: 'watch',
            max_adv_usage: 0.031,
            margin_level: 'elevated',
            margin_utilization: 1.12,
            gross_leverage: 1.85,
            beta_level: 'watch',
            calendar_level: 'watch',
            max_batch_fraction: 0.45,
            lot_efficiency: 0.96,
            suggested_rebalance: 'weekly',
            stress_test_flag: 'high',
          },
          data_alignment: {
            tradable_day_ratio: 0.82,
            calendar_diagnostics: { max_mismatch_ratio: 0.14 },
          },
          hedge_portfolio: {
            beta_neutrality: {
              beta: 1.22,
              beta_gap: 0.22,
            },
          },
          research_input: {
            macro: {
              macro_score: 0.72,
              macro_score_delta: 0.16,
              macro_signal_changed: true,
              policy_source_health: {
                label: 'healthy',
                reason: '主要政策源正文覆盖稳定',
                avg_full_text_ratio: 0.88,
              },
              policy_execution: {
                label: 'watch',
                score: 0.38,
                summary: '部门执行仍处观察区。',
                top_departments: [{ department_label: '发改委' }],
              },
              source_mode_summary: {
                label: 'official-led',
                coverage: 6,
              },
              input_reliability: {
                label: 'robust',
                score: 0.84,
                lead: '当前输入可靠度整体稳健。',
              },
              resonance: {
                label: 'fading_cluster',
                reason: '多个因子同步衰减，共振正在减弱',
              },
            },
            alt_data: {
              top_categories: [
                { category: 'policy', momentum: 'strengthening' },
                { category: 'customs', momentum: 'weakening' },
              ],
            },
          },
          execution_plan: {
            route_count: 2,
            batches: [{}, {}],
            by_provider: { us_stock: 2 },
            venue_allocation: [{ key: 'US_ETF' }],
          },
          template_meta: {
            base_recommendation_tier: '重点跟踪',
            recommendation_tier: '重点跟踪',
            base_recommendation_score: 3.1,
            recommendation_score: 3.1,
            ranking_penalty: 0,
            ranking_penalty_reason: '',
            selection_quality: {
              label: 'original',
              reason: '原始推荐强度保留',
            },
            theme: 'Old theme',
            resonance_label: 'fading_cluster',
            resonance_reason: '多个因子同步衰减，共振正在减弱',
            allocation_mode: 'template_base',
            bias_summary: '多头增配 XLE',
            bias_scale: 1,
            bias_quality_label: 'full',
            bias_quality_reason: '主要政策源正文覆盖稳定',
            policy_execution_label: 'watch',
            policy_execution_risk_budget_scale: 0.94,
            policy_execution_reason: '执行仍处观察区',
            source_mode_label: 'official-led',
            source_mode_risk_budget_scale: 1,
            source_mode_reason: '当前研究输入以官方/披露源为主。',
            dominant_drivers: [{ key: 'baseload_support', label: '基建/基荷支撑', value: 0.2 }],
            driver_summary: [
              { key: 'baseload_support', label: '基建/基荷支撑', value: 0.2 },
              { key: 'growth_pressure', label: '成长端估值压力', value: 0.1 },
            ],
            theme_core: 'XLE+4.0pp',
            theme_support: 'IGV',
            core_leg_pressure: {
              affected: false,
              symbol: '',
              compression_delta: 0,
              summary: '',
            },
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
            max_delta_weight: 0.04,
            bias_compression_effect: 0,
            compression_summary: { compression_ratio: 0 },
            compressed_assets: [],
            rows: [],
          },
          constraint_overlay: {
            binding_count: 1,
            max_delta_weight: 0.03,
          },
        },
      },
      {
        payload: {
          total_return: 0.12,
          sharpe_ratio: 1.45,
          data_alignment: { tradable_day_ratio: 0.9 },
          execution_diagnostics: {
            cost_drag: 0.008,
            turnover: 3.8,
            construction_mode: 'ols_hedge',
            concentration_level: 'balanced',
            liquidity_level: 'comfortable',
            max_adv_usage: 0.014,
            margin_level: 'manageable',
            margin_utilization: 0.86,
            gross_leverage: 1.42,
            beta_level: 'balanced',
            calendar_level: 'aligned',
            max_batch_fraction: 0.33,
            lot_efficiency: 0.992,
            suggested_rebalance: 'biweekly',
            stress_test_flag: 'moderate',
          },
          data_alignment: {
            tradable_day_ratio: 0.9,
            calendar_diagnostics: { max_mismatch_ratio: 0.03 },
          },
          hedge_portfolio: {
            beta_neutrality: {
              beta: 1.04,
              beta_gap: 0.04,
            },
          },
          research_input: {
            macro: {
              macro_score: 0.49,
              macro_score_delta: 0.04,
              macro_signal_changed: false,
              policy_source_health: {
                label: 'fragile',
                reason: '正文抓取脆弱源 ndrc',
                avg_full_text_ratio: 0.43,
              },
              policy_execution: {
                label: 'chaotic',
                score: 0.66,
                summary: '政策执行混乱继续升温。',
                top_departments: [{ department_label: '发改委' }],
              },
              source_mode_summary: {
                label: 'fallback-heavy',
                coverage: 8,
              },
              input_reliability: {
                label: 'fragile',
                score: 0.41,
                lead: '当前输入可靠度偏脆弱，主要风险来自时效偏旧与来源退化。',
              },
              resonance: {
                label: 'bullish_cluster',
                reason: '多个宏观因子同时强化正向扭曲，形成上行共振',
              },
            },
            alt_data: {
              top_categories: [
                { category: 'policy', momentum: 'stable' },
                { category: 'inventory', momentum: 'strengthening' },
              ],
            },
          },
          execution_plan: {
            route_count: 3,
            batches: [{}, {}, {}],
            by_provider: { commodity: 1, us_stock: 2 },
            venue_allocation: [{ key: 'COMEX_CME' }, { key: 'US_ETF' }],
          },
          template_meta: {
            base_recommendation_tier: '优先部署',
            recommendation_tier: '优先部署',
            base_recommendation_score: 3.45,
            recommendation_score: 2.88,
            ranking_penalty: 0.57,
            ranking_penalty_reason: '核心腿 XLE 已进入压缩焦点，主题排序自动降级',
            selection_quality: {
              label: 'auto_downgraded',
              reason: '核心腿 XLE 已进入压缩焦点，主题排序自动降级',
            },
            theme: 'New theme',
            resonance_label: 'bullish_cluster',
            resonance_reason: '多个宏观因子同时强化正向扭曲，形成上行共振',
            allocation_mode: 'macro_bias',
            bias_summary: '多头增配 XLE，空头增配 IGV',
            bias_scale: 0.55,
            bias_quality_label: 'compressed',
            bias_quality_reason: '正文抓取脆弱源 ndrc，宏观偏置已收缩',
            policy_execution_label: 'chaotic',
            policy_execution_risk_budget_scale: 0.84,
            policy_execution_reason: '正文覆盖退化，执行滞后正在抬升组合防御需求',
            source_mode_label: 'fallback-heavy',
            source_mode_risk_budget_scale: 0.72,
            source_mode_reason: '当前来源治理偏回退，建议压缩偏置强度。',
            dominant_drivers: [{ key: 'growth_pressure', label: '成长端估值压力', value: 0.32 }],
            driver_summary: [
              { key: 'baseload_support', label: '基建/基荷支撑', value: 0.18 },
              { key: 'growth_pressure', label: '成长端估值压力', value: 0.32 },
            ],
            theme_core: 'XLE+8.5pp',
            theme_support: 'SOXX',
            core_leg_pressure: {
              affected: true,
              symbol: 'XLE',
              compression_delta: 0.031,
              summary: 'XLE 3.10pp',
            },
          },
          allocation_overlay: {
            selection_quality: {
              label: 'auto_downgraded',
              base_recommendation_score: 3.45,
              effective_recommendation_score: 2.88,
              base_recommendation_tier: '优先部署',
              effective_recommendation_tier: '优先部署',
              ranking_penalty: 0.57,
              reason: '核心腿 XLE 已进入压缩焦点，主题排序自动降级',
            },
            max_delta_weight: 0.085,
            bias_compression_effect: 3.1,
            compression_summary: { compression_ratio: 0.2627 },
            compressed_assets: ['XLE', 'IGV'],
            rows: [
              { symbol: 'XLE', compression_delta: 0.031 },
              { symbol: 'IGV', compression_delta: 0.018 },
            ],
          },
          constraint_overlay: {
            binding_count: 3,
            max_delta_weight: 0.07,
          },
        },
      }
    );

    expect(comparison.lead).toContain('目标版本已从普通结果进入复核型结果');
    expect(comparison.summary[0]).toContain('结果语境 普通结果 -> 复核型结果');
    expect(comparison.summary[1]).toContain('运行强度 original -> auto_downgraded');
    expect(comparison.summary.some((item) => item.includes('执行批次'))).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Route Count')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Batch Count')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Max Batch')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Concentration')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Lot Efficiency')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Liquidity')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Max ADV Usage')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Margin')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Margin Utilization')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Gross Leverage')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Beta')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Beta Value')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Calendar')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Calendar Mismatch')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Macro Score')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Macro Δ')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Macro Resonance')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Policy Source')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Policy Execution')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Policy Execution Score')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Policy Execution Focus')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Input Reliability')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Input Reliability Score')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Input Reliability Lead')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Policy Full Text')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Policy Source Reason')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Source Mode')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Source Mode Construction')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Macro Signal Change')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Alt Trend')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Rebalance')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Stress Flag')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Recommendation')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Base Recommendation')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Effective Recommendation')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Base Tier')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Ranking Penalty')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Selection Quality')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Selection Quality Reason')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Ranking Penalty Reason')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Theme')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Resonance Reason')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Allocation Mode')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Bias Summary')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Bias Scale')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Bias Quality')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Bias Quality Reason')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Bias Compression')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Bias Compression Ratio')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Compressed Assets')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Top Compressed')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Core Leg Pressure')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Core Leg Focus')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Max Weight Shift')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Constraint Bindings')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Constraint Shift')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Dominant Driver')).toBe(true);
    expect(comparison.rows.some((row) => row.label === 'Theme Core')).toBe(true);
    expect(comparison.rows.some((row) => row.label.startsWith('Driver: '))).toBe(true);
  });
});
