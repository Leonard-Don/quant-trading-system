import React from 'react';
import { Empty, List, Space, Tag, Typography } from 'antd';

import { getDriverImpactMeta, getPriceSourceLabel, getSignalStrengthMeta } from '../../utils/pricingResearch';
import { formatPricingScenarioSummary } from './workbenchUtils';

const { Paragraph, Text } = Typography;

const getSnapshotViewContext = (payload = {}) => payload.view_context || payload.workbench_view_context || {};
const formatSourceModeSummaryLabel = (summary = {}) => {
  const label = String(summary?.label || '').toLowerCase();
  if (label === 'official-led') return '官方/披露主导';
  if (label === 'fallback-heavy') return '回退源偏多';
  if (label === 'mixed') return '混合来源';
  return summary?.dominant || '-';
};

const SnapshotViewContextBlock = ({ payload = {} }) => {
  const viewContext = getSnapshotViewContext(payload);
  if (!viewContext?.summary && !viewContext?.scoped_task_label && !viewContext?.note) {
    return null;
  }

  return (
    <Space direction="vertical" size={2} style={{ width: '100%' }}>
      {viewContext.summary ? <Text type="secondary">工作台视图 {viewContext.summary}</Text> : null}
      {viewContext.scoped_task_label ? <Text type="secondary">{viewContext.scoped_task_label}</Text> : null}
      {viewContext.note ? <Text type="secondary">{viewContext.note}</Text> : null}
    </Space>
  );
};

function PricingSnapshotSummary({ task, payload }) {
  const fairValue = payload.fair_value || payload.valuation?.fair_value || {};
  const primaryDriver = payload.primary_driver || payload.drivers?.[0] || null;
  const primaryDriverStrength = getSignalStrengthMeta(primaryDriver?.signal_strength);
  const primaryDriverImpact = getDriverImpactMeta(primaryDriver?.impact);
  const factorSummary = payload.factor_model || {};
  const thesis = payload.macro_mispricing_thesis || {};
  const dcfScenarioSummary = formatPricingScenarioSummary(payload.dcf_scenarios || []);
  const monteCarlo = payload.monte_carlo || {};
  const auditTrail = payload.audit_trail || {};
  const governanceOverlay = payload.people_governance_overlay || {};
  const researchInputMacro = payload.research_input?.macro || {};

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Text strong>{task.snapshot.headline || 'Pricing Snapshot'}</Text>
      <Paragraph style={{ marginBottom: 0 }}>{task.snapshot.summary}</Paragraph>
      {payload.gap_analysis?.fair_value_mid ? (
        <Text type="secondary">
          当前价 {payload.gap_analysis.current_price || '-'} / 公允价值 {payload.gap_analysis.fair_value_mid}
        </Text>
      ) : null}
      {fairValue.mid ? (
        <Text type="secondary">
          综合公允价值区间 {fairValue.low || '-'} ~ {fairValue.high || '-'}
        </Text>
      ) : null}
      {dcfScenarioSummary ? <Text type="secondary">{dcfScenarioSummary}</Text> : null}
      {payload.implications?.primary_view ? (
        <Space wrap size={6}>
          <Tag color="blue">{payload.implications.primary_view}</Tag>
          {payload.implications?.confidence ? <Tag>{`置信度 ${payload.implications.confidence}`}</Tag> : null}
          {payload.implications?.confidence_score !== undefined && payload.implications?.confidence_score !== null ? (
            <Tag>{`评分 ${Number(payload.implications.confidence_score || 0).toFixed(2)}`}</Tag>
          ) : null}
          {payload.implications?.factor_alignment?.label ? (
            <Tag>{`证据 ${payload.implications?.factor_alignment?.label}`}</Tag>
          ) : null}
        </Space>
      ) : null}
      {payload.implications?.confidence_reasons?.length ? (
        <Text type="secondary">
          置信度说明 {(payload.implications.confidence_reasons || []).slice(0, 2).join('；')}
        </Text>
      ) : null}
      {payload.implications?.factor_alignment?.summary ? (
        <Text type="secondary">证据共振 {payload.implications?.factor_alignment?.summary}</Text>
      ) : null}
      {governanceOverlay?.label ? (
        <Text type="secondary">
          治理折价 {governanceOverlay.label}
          {governanceOverlay?.governance_discount_pct !== undefined && governanceOverlay?.governance_discount_pct !== null
            ? ` · ${Number(governanceOverlay.governance_discount_pct) >= 0 ? '-' : '+'}${Math.abs(Number(governanceOverlay.governance_discount_pct || 0)).toFixed(1)}%`
            : ''}
          {governanceOverlay?.confidence !== undefined && governanceOverlay?.confidence !== null
            ? ` · 置信度 ${Number(governanceOverlay.confidence).toFixed(2)}`
            : ''}
        </Text>
      ) : null}
      {governanceOverlay?.summary ? <Text type="secondary">{governanceOverlay.summary}</Text> : null}
      {researchInputMacro?.policy_execution?.summary ? (
        <Text type="secondary">
          政策执行 {researchInputMacro.policy_execution.summary}
          {researchInputMacro.policy_execution.top_department ? ` · ${researchInputMacro.policy_execution.top_department}` : ''}
        </Text>
      ) : null}
      {researchInputMacro?.source_mode_summary?.label ? (
        <Text type="secondary">
          来源治理 {formatSourceModeSummaryLabel(researchInputMacro.source_mode_summary)}
          {researchInputMacro.source_mode_summary.coverage ? ` · 覆盖 ${Number(researchInputMacro.source_mode_summary.coverage)}` : ''}
        </Text>
      ) : null}
      <SnapshotViewContextBlock payload={payload} />
      {(payload.period || factorSummary.data_points || payload.current_price_source) ? (
        <Text type="secondary">
          分析窗口 {payload.period || factorSummary.period || '—'}
          {factorSummary.data_points !== null && factorSummary.data_points !== undefined
            ? ` · 因子样本 ${factorSummary.data_points}`
            : ''}
          {payload.current_price_source ? ` · 现价来源 ${getPriceSourceLabel(payload.current_price_source)}` : ''}
        </Text>
      ) : null}
      {(factorSummary.capm_alpha_pct !== null && factorSummary.capm_alpha_pct !== undefined)
      || (factorSummary.ff3_alpha_pct !== null && factorSummary.ff3_alpha_pct !== undefined) ? (
        <Text type="secondary">
          CAPM α {factorSummary.capm_alpha_pct !== null && factorSummary.capm_alpha_pct !== undefined
            ? `${Number(factorSummary.capm_alpha_pct).toFixed(2)}%`
            : '—'}
          {factorSummary.capm_beta !== null && factorSummary.capm_beta !== undefined
            ? ` / β ${Number(factorSummary.capm_beta).toFixed(2)}`
            : ''}
          {' · '}
          FF3 α {factorSummary.ff3_alpha_pct !== null && factorSummary.ff3_alpha_pct !== undefined
            ? `${Number(factorSummary.ff3_alpha_pct).toFixed(2)}%`
            : '—'}
        </Text>
      ) : null}
      {(factorSummary.ff5_alpha_pct !== null && factorSummary.ff5_alpha_pct !== undefined)
      || (factorSummary.ff5_profitability !== null && factorSummary.ff5_profitability !== undefined)
      || (factorSummary.ff5_investment !== null && factorSummary.ff5_investment !== undefined) ? (
        <Text type="secondary">
          FF5 α {factorSummary.ff5_alpha_pct !== null && factorSummary.ff5_alpha_pct !== undefined
            ? `${Number(factorSummary.ff5_alpha_pct).toFixed(2)}%`
            : '—'}
          {factorSummary.ff5_profitability !== null && factorSummary.ff5_profitability !== undefined
            ? ` · 盈利 ${Number(factorSummary.ff5_profitability).toFixed(2)}`
            : ''}
          {factorSummary.ff5_investment !== null && factorSummary.ff5_investment !== undefined
            ? ` · 投资 ${Number(factorSummary.ff5_investment).toFixed(2)}`
            : ''}
        </Text>
      ) : null}
      {monteCarlo?.p50 !== undefined && monteCarlo?.p50 !== null ? (
        <Text type="secondary">
          Monte Carlo P50 {Number(monteCarlo.p50).toFixed(2)}
          {monteCarlo?.p90 !== undefined && monteCarlo?.p90 !== null ? ` · P90 ${Number(monteCarlo.p90).toFixed(2)}` : ''}
          {monteCarlo?.sample_count ? ` · 样本 ${monteCarlo.sample_count}` : ''}
        </Text>
      ) : null}
      {(auditTrail?.price_source || auditTrail?.comparable_benchmark_source) ? (
        <Text type="secondary">
          审计信息
          {auditTrail?.price_source ? ` · 价格源 ${getPriceSourceLabel(auditTrail.price_source)}` : ''}
          {auditTrail?.comparable_benchmark_source ? ` · 基准 ${auditTrail.comparable_benchmark_source}` : ''}
        </Text>
      ) : null}
      {primaryDriver?.factor ? (
        <Text type="secondary">
          主驱动 {primaryDriver.factor}
          {primaryDriverStrength ? ` · 强度 ${primaryDriverStrength.label}(${primaryDriverStrength.score.toFixed(2)})` : ''}
          {primaryDriver?.impact ? ` · ${primaryDriverImpact.label}` : ''}
          {primaryDriver.ranking_reason ? ` · ${primaryDriver.ranking_reason}` : ''}
        </Text>
      ) : null}
      {thesis?.primary_leg?.symbol ? (
        <Text type="secondary">
          Thesis {thesis.primary_leg.symbol} {thesis.primary_leg.side}
          {thesis.hedge_leg?.symbol ? ` / ${thesis.hedge_leg.symbol} ${thesis.hedge_leg.side}` : ''}
          {thesis.stance ? ` · ${thesis.stance}` : ''}
        </Text>
      ) : null}
      {thesis?.trade_legs?.length ? (
        <Text type="secondary">
          组合腿 {thesis.trade_legs.slice(0, 3).map((leg) => `${leg.symbol} ${leg.side}`).join(' / ')}
        </Text>
      ) : null}
      {(task.snapshot.highlights || []).map((item) => (
        <Text key={item} type="secondary">
          {item}
        </Text>
      ))}
    </Space>
  );
}

function MacroMispricingSnapshotSummary({ task, payload }) {
  const structuralDecay = payload.structural_decay || {};
  const thesis = payload.macro_mispricing_thesis || {};
  const peopleLayer = payload.people_layer || {};
  const implications = payload.implications || {};
  const gapAnalysis = payload.gap_analysis || {};
  const evidence = structuralDecay.evidence || [];

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Text strong>{task.snapshot.headline || 'Macro Mispricing Snapshot'}</Text>
      <Paragraph style={{ marginBottom: 0 }}>{task.snapshot.summary}</Paragraph>
      <Space wrap size={6}>
        {structuralDecay.label ? <Tag color="volcano">{structuralDecay.label}</Tag> : null}
        {structuralDecay.action ? <Tag color="red">{structuralDecay.action}</Tag> : null}
        {peopleLayer.risk_level ? <Tag>{`人的维度 ${peopleLayer.risk_level}`}</Tag> : null}
        {implications.primary_view ? <Tag>{`定价结论 ${implications.primary_view}`}</Tag> : null}
      </Space>
      {structuralDecay.score !== undefined && structuralDecay.score !== null ? (
        <Text type="secondary">
          衰败评分 {Number(structuralDecay.score || 0).toFixed(2)}
          {structuralDecay.reversibility ? ` · 可逆性 ${structuralDecay.reversibility}` : ''}
          {structuralDecay.horizon ? ` · 观察期 ${structuralDecay.horizon}` : ''}
        </Text>
      ) : null}
      {structuralDecay.dominant_failure_label ? (
        <Text type="secondary">主导失效模式 {structuralDecay.dominant_failure_label}</Text>
      ) : null}
      {peopleLayer.summary ? <Text type="secondary">人的维度 {peopleLayer.summary}</Text> : null}
      {gapAnalysis.gap_pct !== undefined && gapAnalysis.gap_pct !== null ? (
        <Text type="secondary">
          当前错价 {Number(gapAnalysis.gap_pct || 0).toFixed(2)}%
          {gapAnalysis.direction ? ` · ${gapAnalysis.direction}` : ''}
        </Text>
      ) : null}
      <SnapshotViewContextBlock payload={payload} />
      {thesis?.primary_leg?.symbol ? (
        <Text type="secondary">
          Thesis {thesis.primary_leg.symbol} {thesis.primary_leg.side}
          {thesis.hedge_leg?.symbol ? ` / ${thesis.hedge_leg.symbol} ${thesis.hedge_leg.side}` : ''}
          {thesis.stance ? ` · ${thesis.stance}` : ''}
        </Text>
      ) : null}
      {thesis?.trade_legs?.length ? (
        <Text type="secondary">
          组合腿 {thesis.trade_legs.slice(0, 3).map((leg) => `${leg.symbol} ${leg.side}`).join(' / ')}
        </Text>
      ) : null}
      {evidence.length ? (
        <Text type="secondary">关键证据 {evidence.slice(0, 3).join('；')}</Text>
      ) : null}
      {(task.snapshot.highlights || []).map((item) => (
        <Text key={item} type="secondary">
          {item}
        </Text>
      ))}
    </Space>
  );
}

function CrossMarketSnapshotSummary({ task, payload }) {
  const tradeThesis = payload.trade_thesis || {};
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Text strong>{task.snapshot.headline || 'Cross-Market Snapshot'}</Text>
      <Paragraph style={{ marginBottom: 0 }}>{task.snapshot.summary}</Paragraph>
      {tradeThesis?.thesis?.stance ? (
        <Text type="secondary">
          Thesis {tradeThesis.thesis.stance}
          {tradeThesis?.symbol ? ` · ${tradeThesis.symbol}` : ''}
          {tradeThesis?.thesis?.horizon ? ` · ${tradeThesis.thesis.horizon}` : ''}
        </Text>
      ) : null}
      {tradeThesis?.results_summary?.total_return !== undefined ? (
        <Text type="secondary">
          回测 {(Number(tradeThesis.results_summary.total_return || 0) * 100).toFixed(2)}%
          {tradeThesis?.results_summary?.sharpe_ratio !== undefined
            ? ` · Sharpe ${Number(tradeThesis.results_summary.sharpe_ratio || 0).toFixed(2)}`
            : ''}
          {tradeThesis?.results_summary?.coverage !== undefined
            ? ` · 覆盖率 ${(Number(tradeThesis.results_summary.coverage || 0) * 100).toFixed(2)}%`
            : ''}
        </Text>
      ) : null}
      {tradeThesis?.assets?.length ? (
        <Text type="secondary">
          组合腿 {tradeThesis.assets.slice(0, 3).map((asset) => `${asset.symbol} ${asset.side}`).join(' / ')}
        </Text>
      ) : null}
      <SnapshotViewContextBlock payload={payload} />
      {payload.template_meta?.theme ? <Text type="secondary">主题 {payload.template_meta.theme}</Text> : null}
      {payload.template_meta?.allocation_mode ? (
        <Text type="secondary">
          配置模式 {payload.template_meta.allocation_mode === 'macro_bias' ? '宏观偏置' : '模板原始权重'}
        </Text>
      ) : null}
      {payload.template_meta?.bias_summary ? <Text type="secondary">权重偏置 {payload.template_meta.bias_summary}</Text> : null}
      {payload.template_meta?.bias_strength_raw ? (
        <Text type="secondary">
          原始偏置 {Number(payload.template_meta.bias_strength_raw || 0).toFixed(1)}pp
          {payload.template_meta?.bias_strength ? ` · 生效偏置 ${Number(payload.template_meta.bias_strength || 0).toFixed(1)}pp` : ''}
        </Text>
      ) : null}
      {payload.template_meta?.bias_quality_label && payload.template_meta.bias_quality_label !== 'full' ? (
        <Text type="secondary">
          偏置收缩 {payload.template_meta.bias_quality_label}
          {payload.template_meta?.bias_scale ? ` · scale ${Number(payload.template_meta.bias_scale).toFixed(2)}x` : ''}
          {payload.template_meta?.bias_quality_reason ? ` · ${payload.template_meta.bias_quality_reason}` : ''}
        </Text>
      ) : null}
      {payload.template_meta?.department_chaos_label && payload.template_meta.department_chaos_label !== 'unknown' ? (
        <Text type="secondary">
          部门混乱构造 {payload.template_meta.department_chaos_label}
          {payload.template_meta?.department_chaos_top_department ? ` · ${payload.template_meta.department_chaos_top_department}` : ''}
          {payload.template_meta?.department_chaos_risk_budget_scale
            ? ` · 风险预算 ${Number(payload.template_meta.department_chaos_risk_budget_scale || 1).toFixed(2)}x`
            : ''}
        </Text>
      ) : null}
      {payload.template_meta?.policy_execution_label && payload.template_meta.policy_execution_label !== 'unknown' ? (
        <Text type="secondary">
          政策执行构造 {payload.template_meta.policy_execution_label}
          {payload.template_meta?.policy_execution_top_department ? ` · ${payload.template_meta.policy_execution_top_department}` : ''}
          {payload.template_meta?.policy_execution_risk_budget_scale
            ? ` · 风险预算 ${Number(payload.template_meta.policy_execution_risk_budget_scale || 1).toFixed(2)}x`
            : ''}
        </Text>
      ) : null}
      {payload.template_meta?.people_fragility_label && payload.template_meta.people_fragility_label !== 'stable' ? (
        <Text type="secondary">
          人的维度构造 {payload.template_meta.people_fragility_label}
          {payload.template_meta?.people_fragility_focus ? ` · ${payload.template_meta.people_fragility_focus}` : ''}
          {payload.template_meta?.people_fragility_risk_budget_scale
            ? ` · 风险预算 ${Number(payload.template_meta.people_fragility_risk_budget_scale || 1).toFixed(2)}x`
            : ''}
        </Text>
      ) : null}
      {payload.template_meta?.structural_decay_radar_label && payload.template_meta.structural_decay_radar_label !== 'stable' ? (
        <Text type="secondary">
          结构衰败雷达 {payload.template_meta.structural_decay_radar_display_label || payload.template_meta.structural_decay_radar_label}
          {payload.template_meta?.structural_decay_radar_score !== undefined && payload.template_meta?.structural_decay_radar_score !== null
            ? ` · ${Math.round(Number(payload.template_meta.structural_decay_radar_score || 0) * 100)}%`
            : ''}
          {payload.template_meta?.structural_decay_radar_risk_budget_scale
            ? ` · 风险预算 ${Number(payload.template_meta.structural_decay_radar_risk_budget_scale || 1).toFixed(2)}x`
            : ''}
        </Text>
      ) : null}
      {payload.template_meta?.core_leg_pressure?.affected ? (
        <Text type="secondary">
          核心腿受压 {payload.template_meta.core_leg_pressure.summary || payload.template_meta.core_leg_pressure.symbol}
        </Text>
      ) : null}
      {payload.allocation_overlay?.compressed_assets?.length ? (
        <Text type="secondary">
          压缩焦点 {payload.allocation_overlay.compressed_assets.join('，')}
          {payload.allocation_overlay.compression_summary?.compression_effect !== undefined
            ? ` · 收缩 ${Number(payload.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp`
            : ''}
        </Text>
      ) : null}
      {payload.template_meta?.bias_actions?.length ? (
        <Text type="secondary">
          建议动作 {(payload.template_meta.bias_actions || []).map((item) => `${item.action === 'increase' ? '增配' : '减配'} ${item.symbol}`).join('，')}
        </Text>
      ) : null}
      {payload.template_meta?.driver_summary?.length ? (
        <Text type="secondary">
          驱动分解 {(payload.template_meta.driver_summary || []).slice(0, 3).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('，')}
        </Text>
      ) : null}
      {payload.template_meta?.theme_core ? <Text type="secondary">核心腿 {payload.template_meta.theme_core}</Text> : null}
      {payload.template_meta?.theme_support ? <Text type="secondary">辅助腿 {payload.template_meta.theme_support}</Text> : null}
      {payload.allocation_overlay?.max_delta_weight ? (
        <Text type="secondary">最大权重偏移 {(Number(payload.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp</Text>
      ) : null}
      {payload.constraint_overlay?.binding_count ? (
        <Text type="secondary">
          组合约束触发 {payload.constraint_overlay.binding_count} 个 · 最大约束偏移 {(Number(payload.constraint_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
        </Text>
      ) : null}
      {payload.template_meta?.recommendation_tier ? <Tag color="gold">{payload.template_meta.recommendation_tier}</Tag> : null}
      {payload.template_meta?.selection_quality?.label && payload.template_meta.selection_quality.label !== 'original' ? (
        <Tag color="orange">自动降级 {payload.template_meta.selection_quality.label}</Tag>
      ) : null}
      {payload.template_meta?.resonance_label && payload.template_meta.resonance_label !== 'mixed' ? (
        <Tag color="magenta">共振 {payload.template_meta.resonance_label}</Tag>
      ) : null}
      {payload.template_meta?.base_recommendation_score !== null
      && payload.template_meta?.base_recommendation_score !== undefined ? (
        <Text type="secondary">
          推荐强度 {Number(payload.template_meta.base_recommendation_score || 0).toFixed(2)}
          {payload.template_meta?.recommendation_score !== null && payload.template_meta?.recommendation_score !== undefined
            ? ` -> ${Number(payload.template_meta.recommendation_score || 0).toFixed(2)}`
            : ''}
          {payload.template_meta?.base_recommendation_tier
            ? ` · ${payload.template_meta.base_recommendation_tier} -> ${payload.template_meta.recommendation_tier || '-'}`
            : ''}
        </Text>
      ) : null}
      {payload.template_meta?.ranking_penalty ? (
        <Text type="secondary">
          排序惩罚 {Number(payload.template_meta.ranking_penalty || 0).toFixed(2)}
          {payload.template_meta?.ranking_penalty_reason ? ` · ${payload.template_meta.ranking_penalty_reason}` : ''}
        </Text>
      ) : null}
      {payload.template_meta?.recommendation_reason ? <Text type="secondary">推荐依据 {payload.template_meta.recommendation_reason}</Text> : null}
      {payload.template_meta?.resonance_reason ? <Text type="secondary">共振背景 {payload.template_meta.resonance_reason}</Text> : null}
      {payload.research_input?.macro ? (
        <Text type="secondary">
          宏观输入 分数 {Number(payload.research_input.macro.macro_score || 0).toFixed(2)}
          {' · '}
          Δ{Number(payload.research_input.macro.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(payload.research_input.macro.macro_score_delta || 0).toFixed(2)}
          {payload.research_input.macro.macro_signal_changed ? ' · 信号切换' : ''}
          {payload.research_input.macro.resonance?.label && payload.research_input.macro.resonance.label !== 'mixed'
            ? ` · 共振 ${payload.research_input.macro.resonance.label}`
            : ''}
          {payload.research_input.macro.policy_source_health?.label
          && payload.research_input.macro.policy_source_health.label !== 'unknown'
            ? ` · 政策源 ${payload.research_input.macro.policy_source_health.label}`
            : ''}
          {payload.research_input.macro.department_chaos?.label
          && payload.research_input.macro.department_chaos.label !== 'unknown'
            ? ` · 部门 ${payload.research_input.macro.department_chaos.label}`
            : ''}
          {payload.research_input.macro.input_reliability?.label
          && payload.research_input.macro.input_reliability.label !== 'unknown'
            ? ` · 输入 ${payload.research_input.macro.input_reliability.label}`
            : ''}
        </Text>
      ) : null}
      {payload.research_input?.macro?.policy_source_health?.reason ? (
        <Text type="secondary">政策源 {payload.research_input.macro.policy_source_health.reason}</Text>
      ) : null}
      {payload.research_input?.macro?.department_chaos?.summary ? (
        <Text type="secondary">部门混乱 {payload.research_input.macro.department_chaos.summary}</Text>
      ) : null}
      {payload.research_input?.macro?.people_layer?.summary ? (
        <Text type="secondary">人的维度 {payload.research_input.macro.people_layer.summary}</Text>
      ) : null}
      {payload.research_input?.macro?.policy_execution?.summary ? (
        <Text type="secondary">
          政策执行 {payload.research_input.macro.policy_execution.summary}
          {payload.research_input.macro.policy_execution.top_departments?.[0]?.department_label
            ? ` · ${payload.research_input.macro.policy_execution.top_departments[0].department_label}`
            : ''}
        </Text>
      ) : null}
      {payload.research_input?.macro?.source_mode_summary?.label ? (
        <Text type="secondary">
          来源治理 {formatSourceModeSummaryLabel(payload.research_input.macro.source_mode_summary)}
          {payload.research_input.macro.source_mode_summary.coverage
            ? ` · 覆盖 ${Number(payload.research_input.macro.source_mode_summary.coverage)}`
            : ''}
        </Text>
      ) : null}
      {payload.research_input?.macro?.input_reliability?.lead ? (
        <Text type="secondary">
          输入可靠度 {payload.research_input.macro.input_reliability.lead}
          {payload.research_input.macro.input_reliability.score
            ? ` · score ${Number(payload.research_input.macro.input_reliability.score || 0).toFixed(2)}`
            : ''}
          {payload.research_input.macro.input_reliability.posture
            ? ` · ${payload.research_input.macro.input_reliability.posture}`
            : ''}
        </Text>
      ) : null}
      {payload.research_input?.alt_data?.top_categories?.length ? (
        <Text type="secondary">
          另类数据 {(payload.research_input.alt_data.top_categories || [])
            .slice(0, 2)
            .map((item) => `${item.category} ${item.momentum === 'strengthening' ? '增强' : item.momentum === 'weakening' ? '走弱' : '稳定'} ${Number(item.delta_score || 0) >= 0 ? '+' : ''}${Number(item.delta_score || 0).toFixed(2)}`)
            .join('，')}
        </Text>
      ) : null}
      {payload.total_return !== undefined ? (
        <Text type="secondary">
          总收益 {(Number(payload.total_return || 0) * 100).toFixed(2)}% / Sharpe {Number(payload.sharpe_ratio || 0).toFixed(2)}
        </Text>
      ) : null}
      {payload.execution_plan?.batches?.length ? (
        <Text type="secondary">
          执行批次 {payload.execution_plan.batches.length} / 路由 {payload.execution_plan.route_count || 0}
          {payload.execution_plan.initial_capital ? ` / 计划资金 ${Number(payload.execution_plan.initial_capital).toLocaleString()}` : ''}
        </Text>
      ) : null}
      {payload.execution_diagnostics?.concentration_level ? (
        <Text type="secondary">
          执行集中度 {payload.execution_diagnostics.concentration_level}
          {payload.execution_diagnostics.concentration_reason ? ` · ${payload.execution_diagnostics.concentration_reason}` : ''}
        </Text>
      ) : null}
      {payload.execution_diagnostics?.liquidity_level ? (
        <Text type="secondary">
          流动性 {payload.execution_diagnostics.liquidity_level}
          {payload.execution_diagnostics.max_adv_usage !== undefined
            ? ` · Max ADV ${(Number(payload.execution_diagnostics.max_adv_usage || 0) * 100).toFixed(2)}%`
            : ''}
        </Text>
      ) : null}
      {payload.execution_diagnostics?.margin_level ? (
        <Text type="secondary">
          保证金 {payload.execution_diagnostics.margin_level}
          {payload.execution_diagnostics.margin_utilization !== undefined
            ? ` · ${(Number(payload.execution_diagnostics.margin_utilization || 0) * 100).toFixed(2)}%`
            : ''}
          {payload.execution_diagnostics.gross_leverage !== undefined
            ? ` · Gross ${Number(payload.execution_diagnostics.gross_leverage || 0).toFixed(2)}x`
            : ''}
        </Text>
      ) : null}
      {payload.execution_diagnostics?.beta_level ? (
        <Text type="secondary">
          Beta {payload.execution_diagnostics.beta_level}
          {payload.hedge_portfolio?.beta_neutrality?.beta !== undefined
            ? ` · ${Number(payload.hedge_portfolio.beta_neutrality.beta || 0).toFixed(2)}`
            : ''}
        </Text>
      ) : null}
      {payload.execution_diagnostics?.calendar_level ? (
        <Text type="secondary">
          日历 {payload.execution_diagnostics.calendar_level}
          {payload.data_alignment?.calendar_diagnostics?.max_mismatch_ratio !== undefined
            ? ` · mismatch ${(Number(payload.data_alignment.calendar_diagnostics.max_mismatch_ratio || 0) * 100).toFixed(2)}%`
            : ''}
        </Text>
      ) : null}
      {payload.execution_diagnostics?.suggested_rebalance ? (
        <Text type="secondary">
          建议调仓 {payload.execution_diagnostics.suggested_rebalance}
          {payload.execution_diagnostics.lot_efficiency !== undefined
            ? ` · Lot 效率 ${(Number(payload.execution_diagnostics.lot_efficiency || 0) * 100).toFixed(2)}%`
            : ''}
        </Text>
      ) : null}
      {payload.execution_plan?.execution_stress?.worst_case ? (
        <Text type="secondary">
          压力测试 {payload.execution_plan.execution_stress.worst_case.label} · {payload.execution_plan.execution_stress.worst_case.concentration_level}
        </Text>
      ) : null}
      {payload.data_alignment?.tradable_day_ratio !== undefined ? (
        <Text type="secondary">覆盖率 {(Number(payload.data_alignment.tradable_day_ratio || 0) * 100).toFixed(2)}%</Text>
      ) : null}
      {(task.snapshot.highlights || []).map((item) => (
        <Text key={item} type="secondary">
          {item}
        </Text>
      ))}
    </Space>
  );
}

export function SnapshotSummary({ task }) {
  if (!task?.snapshot) {
    return <Empty description="暂无保存快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const payload = task.snapshot.payload || {};
  if (task.type === 'pricing') {
    return <PricingSnapshotSummary task={task} payload={payload} />;
  }
  if (task.type === 'macro_mispricing') {
    return <MacroMispricingSnapshotSummary task={task} payload={payload} />;
  }
  return <CrossMarketSnapshotSummary task={task} payload={payload} />;
}

export function SnapshotHistoryList({ task }) {
  const history = task?.snapshot_history || [];
  if (!history.length) {
    return <Empty description="暂无历史快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <List
      size="small"
      dataSource={history}
      renderItem={(item) => {
        const payload = item.payload || {};
        const savedAt = item.saved_at ? new Date(item.saved_at).toLocaleString() : '-';
        const pricingValue = payload.fair_value?.mid || payload.gap_analysis?.fair_value_mid;
        const dcfScenarioSummary = formatPricingScenarioSummary(payload.dcf_scenarios || []);
        const templateMeta = payload.template_meta || {};
        const primaryDriverStrength = getSignalStrengthMeta(payload.primary_driver?.signal_strength);
        const viewContext = getSnapshotViewContext(payload);
        const isReviewRunSnapshot = Boolean(
          String(item.headline || '').includes('复核型结果')
          || (templateMeta.selection_quality?.label && templateMeta.selection_quality.label !== 'original')
        );

        return (
          <List.Item>
            <List.Item.Meta
              title={(
                <Space wrap>
                  <Text strong>{item.headline || '研究快照'}</Text>
                  {isReviewRunSnapshot ? <Tag color="gold">复核型结果</Tag> : null}
                  <Tag>{savedAt}</Tag>
                </Space>
              )}
              description={(
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Text type="secondary">{item.summary || '暂无摘要'}</Text>
                  {task.type === 'pricing' || task.type === 'macro_mispricing' ? (
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Space wrap size={6}>
                        <Text type="secondary">
                          Fair value {pricingValue || '-'} · {(payload.implications?.primary_view || '待判断')}
                        </Text>
                        {payload.implications?.confidence ? <Tag>{`置信度 ${payload.implications.confidence}`}</Tag> : null}
                        {payload.implications?.confidence_score !== undefined && payload.implications?.confidence_score !== null ? (
                          <Tag>{`评分 ${Number(payload.implications.confidence_score || 0).toFixed(2)}`}</Tag>
                        ) : null}
                        {payload.implications?.factor_alignment?.label ? (
                          <Tag>{`证据 ${payload.implications.factor_alignment.label}`}</Tag>
                        ) : null}
                        {payload.primary_driver?.factor ? <Tag>{`主驱动 ${payload.primary_driver.factor}`}</Tag> : null}
                        {primaryDriverStrength ? <Tag>{`强度 ${primaryDriverStrength.label}`}</Tag> : null}
                      </Space>
                      {dcfScenarioSummary ? <Text type="secondary">{dcfScenarioSummary}</Text> : null}
                      {payload.factor_model?.ff5_alpha_pct !== null && payload.factor_model?.ff5_alpha_pct !== undefined ? (
                        <Text type="secondary">
                          FF5 α {Number(payload.factor_model.ff5_alpha_pct || 0).toFixed(2)}%
                          {payload.factor_model?.ff5_profitability !== null && payload.factor_model?.ff5_profitability !== undefined
                            ? ` · 盈利 ${Number(payload.factor_model.ff5_profitability || 0).toFixed(2)}`
                            : ''}
                          {payload.factor_model?.ff5_investment !== null && payload.factor_model?.ff5_investment !== undefined
                            ? ` · 投资 ${Number(payload.factor_model.ff5_investment || 0).toFixed(2)}`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.monte_carlo?.p50 !== undefined && payload.monte_carlo?.p50 !== null ? (
                        <Text type="secondary">
                          Monte Carlo P50 {Number(payload.monte_carlo.p50 || 0).toFixed(2)}
                          {payload.monte_carlo?.p90 !== undefined && payload.monte_carlo?.p90 !== null
                            ? ` · P90 ${Number(payload.monte_carlo.p90 || 0).toFixed(2)}`
                            : ''}
                        </Text>
                      ) : null}
                      {task.type === 'macro_mispricing' && payload.structural_decay?.score !== undefined && payload.structural_decay?.score !== null ? (
                        <Text type="secondary">
                          衰败评分 {Number(payload.structural_decay.score || 0).toFixed(2)}
                          {payload.structural_decay?.dominant_failure_label
                            ? ` · ${payload.structural_decay.dominant_failure_label}`
                            : ''}
                        </Text>
                      ) : null}
                      {task.type === 'macro_mispricing' && payload.people_layer?.risk_level ? (
                        <Text type="secondary">
                          人的维度 {payload.people_layer.risk_level}
                          {payload.people_layer?.summary ? ` · ${payload.people_layer.summary}` : ''}
                        </Text>
                      ) : null}
                      {viewContext.summary ? <Text type="secondary">工作台视图 {viewContext.summary}</Text> : null}
                      {viewContext.scoped_task_label ? <Text type="secondary">{viewContext.scoped_task_label}</Text> : null}
                      {payload.macro_mispricing_thesis?.primary_leg?.symbol ? (
                        <Text type="secondary">
                          Thesis {payload.macro_mispricing_thesis.primary_leg.symbol} {payload.macro_mispricing_thesis.primary_leg.side}
                          {payload.macro_mispricing_thesis.hedge_leg?.symbol
                            ? ` / ${payload.macro_mispricing_thesis.hedge_leg.symbol} ${payload.macro_mispricing_thesis.hedge_leg.side}`
                            : ''}
                        </Text>
                      ) : null}
                      {task.type === 'trade_thesis' && payload.trade_thesis?.thesis?.stance ? (
                        <Text type="secondary">
                          Thesis {payload.trade_thesis.thesis.stance}
                          {payload.trade_thesis?.symbol ? ` · ${payload.trade_thesis.symbol}` : ''}
                          {payload.trade_thesis?.thesis?.horizon ? ` · ${payload.trade_thesis.thesis.horizon}` : ''}
                        </Text>
                      ) : null}
                      {task.type === 'trade_thesis' && payload.trade_thesis?.assets?.length ? (
                        <Text type="secondary">
                          组合腿 {payload.trade_thesis.assets.slice(0, 3).map((asset) => `${asset.symbol} ${asset.side}`).join(' / ')}
                        </Text>
                      ) : null}
                    </Space>
                  ) : (
                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                      <Text type="secondary">
                        Return {(Number(payload.total_return || 0) * 100).toFixed(2)}% · Sharpe {Number(payload.sharpe_ratio || 0).toFixed(2)}
                      </Text>
                      {payload.execution_plan?.batches?.length ? (
                        <Text type="secondary">
                          执行批次 {payload.execution_plan.batches.length} · 路由 {payload.execution_plan.route_count || 0}
                          {payload.execution_plan.initial_capital ? ` · 资金 ${Number(payload.execution_plan.initial_capital).toLocaleString()}` : ''}
                        </Text>
                      ) : null}
                      {payload.execution_diagnostics?.concentration_level ? <Text type="secondary">集中度 {payload.execution_diagnostics.concentration_level}</Text> : null}
                      {payload.execution_diagnostics?.liquidity_level ? (
                        <Text type="secondary">
                          流动性 {payload.execution_diagnostics.liquidity_level}
                          {payload.execution_diagnostics.max_adv_usage !== undefined
                            ? ` · Max ADV ${(Number(payload.execution_diagnostics.max_adv_usage || 0) * 100).toFixed(2)}%`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.execution_diagnostics?.margin_level ? (
                        <Text type="secondary">
                          保证金 {payload.execution_diagnostics.margin_level}
                          {payload.execution_diagnostics.margin_utilization !== undefined
                            ? ` · ${(Number(payload.execution_diagnostics.margin_utilization || 0) * 100).toFixed(2)}%`
                            : ''}
                          {payload.execution_diagnostics.gross_leverage !== undefined
                            ? ` · Gross ${Number(payload.execution_diagnostics.gross_leverage || 0).toFixed(2)}x`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.execution_diagnostics?.beta_level ? (
                        <Text type="secondary">
                          Beta {payload.execution_diagnostics.beta_level}
                          {payload.hedge_portfolio?.beta_neutrality?.beta !== undefined
                            ? ` · ${Number(payload.hedge_portfolio.beta_neutrality.beta || 0).toFixed(2)}`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.execution_diagnostics?.calendar_level ? (
                        <Text type="secondary">
                          日历 {payload.execution_diagnostics.calendar_level}
                          {payload.data_alignment?.calendar_diagnostics?.max_mismatch_ratio !== undefined
                            ? ` · mismatch ${(Number(payload.data_alignment.calendar_diagnostics.max_mismatch_ratio || 0) * 100).toFixed(2)}%`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.execution_diagnostics?.suggested_rebalance ? (
                        <Text type="secondary">
                          调仓 {payload.execution_diagnostics.suggested_rebalance}
                          {payload.execution_diagnostics.lot_efficiency !== undefined
                            ? ` · Lot ${(Number(payload.execution_diagnostics.lot_efficiency || 0) * 100).toFixed(1)}%`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.execution_plan?.execution_stress?.worst_case ? (
                        <Text type="secondary">
                          压测 {payload.execution_plan.execution_stress.worst_case.label} · {payload.execution_plan.execution_stress.worst_case.concentration_level}
                        </Text>
                      ) : null}
                      {templateMeta.recommendation_tier ? (
                        <Text type="secondary">
                          推荐 {templateMeta.recommendation_tier}
                          {templateMeta.theme ? ` · ${templateMeta.theme}` : ''}
                        </Text>
                      ) : null}
                      {templateMeta.selection_quality?.label && templateMeta.selection_quality.label !== 'original' ? (
                        <Text type="secondary">
                          自动降级 {templateMeta.selection_quality.label}
                          {templateMeta.selection_quality?.reason ? ` · ${templateMeta.selection_quality.reason}` : ''}
                        </Text>
                      ) : null}
                      {isReviewRunSnapshot ? (
                        <Text style={{ color: '#ad6800' }}>
                          这是一版复核型结果，建议与普通默认模板结果分开理解。
                        </Text>
                      ) : null}
                      {templateMeta.base_recommendation_score !== null
                      && templateMeta.base_recommendation_score !== undefined ? (
                        <Text type="secondary">
                          推荐强度 {Number(templateMeta.base_recommendation_score || 0).toFixed(2)}
                          {templateMeta.recommendation_score !== null && templateMeta.recommendation_score !== undefined
                            ? ` -> ${Number(templateMeta.recommendation_score || 0).toFixed(2)}`
                            : ''}
                          {templateMeta.base_recommendation_tier
                            ? ` · ${templateMeta.base_recommendation_tier} -> ${templateMeta.recommendation_tier || '-'}`
                            : ''}
                        </Text>
                      ) : null}
                      {templateMeta.ranking_penalty ? (
                        <Text type="secondary">
                          排序惩罚 {Number(templateMeta.ranking_penalty || 0).toFixed(2)}
                          {templateMeta.ranking_penalty_reason ? ` · ${templateMeta.ranking_penalty_reason}` : ''}
                        </Text>
                      ) : null}
                      {templateMeta.resonance_label && templateMeta.resonance_label !== 'mixed' ? <Text type="secondary">共振 {templateMeta.resonance_label}</Text> : null}
                      {templateMeta.bias_summary ? <Text type="secondary">偏置 {templateMeta.bias_summary}</Text> : null}
                      {templateMeta.bias_strength_raw ? (
                        <Text type="secondary">
                          原始偏置 {Number(templateMeta.bias_strength_raw || 0).toFixed(1)}pp
                          {templateMeta.bias_strength ? ` · 生效偏置 ${Number(templateMeta.bias_strength || 0).toFixed(1)}pp` : ''}
                        </Text>
                      ) : null}
                      {templateMeta.bias_quality_label && templateMeta.bias_quality_label !== 'full' ? (
                        <Text type="secondary">
                          偏置收缩 {templateMeta.bias_quality_label}
                          {templateMeta.bias_scale ? ` · scale ${Number(templateMeta.bias_scale).toFixed(2)}x` : ''}
                        </Text>
                      ) : null}
                      {templateMeta.department_chaos_label && templateMeta.department_chaos_label !== 'unknown' ? (
                        <Text type="secondary">
                          部门混乱构造 {templateMeta.department_chaos_label}
                          {templateMeta.department_chaos_top_department ? ` · ${templateMeta.department_chaos_top_department}` : ''}
                          {templateMeta.department_chaos_risk_budget_scale
                            ? ` · 风险预算 ${Number(templateMeta.department_chaos_risk_budget_scale || 1).toFixed(2)}x`
                            : ''}
                        </Text>
                      ) : null}
                      {templateMeta.people_fragility_label && templateMeta.people_fragility_label !== 'stable' ? (
                        <Text type="secondary">
                          人的维度构造 {templateMeta.people_fragility_label}
                          {templateMeta.people_fragility_focus ? ` · ${templateMeta.people_fragility_focus}` : ''}
                          {templateMeta.people_fragility_risk_budget_scale
                            ? ` · 风险预算 ${Number(templateMeta.people_fragility_risk_budget_scale || 1).toFixed(2)}x`
                            : ''}
                        </Text>
                      ) : null}
                      {templateMeta.structural_decay_radar_label && templateMeta.structural_decay_radar_label !== 'stable' ? (
                        <Text type="secondary">
                          结构衰败雷达 {templateMeta.structural_decay_radar_display_label || templateMeta.structural_decay_radar_label}
                          {templateMeta.structural_decay_radar_score !== undefined && templateMeta.structural_decay_radar_score !== null
                            ? ` · ${Math.round(Number(templateMeta.structural_decay_radar_score || 0) * 100)}%`
                            : ''}
                          {templateMeta.structural_decay_radar_risk_budget_scale
                            ? ` · 风险预算 ${Number(templateMeta.structural_decay_radar_risk_budget_scale || 1).toFixed(2)}x`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.allocation_overlay?.compressed_assets?.length ? (
                        <Text type="secondary">
                          压缩焦点 {payload.allocation_overlay.compressed_assets.join('，')}
                          {payload.allocation_overlay.compression_summary?.compression_effect !== undefined
                            ? ` · 收缩 ${Number(payload.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp`
                            : ''}
                        </Text>
                      ) : null}
                      {templateMeta.bias_actions?.length ? (
                        <Text type="secondary">
                          动作 {(templateMeta.bias_actions || []).slice(0, 3).map((item) => `${item.action === 'increase' ? '增配' : '减配'} ${item.symbol}`).join('，')}
                        </Text>
                      ) : null}
                      {templateMeta.driver_summary?.length ? (
                        <Text type="secondary">
                          分解 {(templateMeta.driver_summary || []).slice(0, 2).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('，')}
                        </Text>
                      ) : null}
                      {templateMeta.theme_core ? <Text type="secondary">核心腿 {templateMeta.theme_core}</Text> : null}
                      {payload.allocation_overlay?.max_delta_weight ? (
                        <Text type="secondary">最大偏移 {(Number(payload.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp</Text>
                      ) : null}
                      {payload.constraint_overlay?.binding_count ? (
                        <Text type="secondary">
                          约束 {payload.constraint_overlay.binding_count} 个 · 最大约束偏移 {(Number(payload.constraint_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
                        </Text>
                      ) : null}
                      {templateMeta.recommendation_reason ? <Text type="secondary">{templateMeta.recommendation_reason}</Text> : null}
                      {templateMeta.resonance_reason ? <Text type="secondary">{templateMeta.resonance_reason}</Text> : null}
                      {viewContext.summary ? <Text type="secondary">工作台视图 {viewContext.summary}</Text> : null}
                      {viewContext.scoped_task_label ? <Text type="secondary">{viewContext.scoped_task_label}</Text> : null}
                      {payload.research_input?.macro ? (
                        <Text type="secondary">
                          宏观 {Number(payload.research_input.macro.macro_score || 0).toFixed(2)}
                          {' · '}
                          Δ{Number(payload.research_input.macro.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(payload.research_input.macro.macro_score_delta || 0).toFixed(2)}
                          {payload.research_input.macro.resonance?.label && payload.research_input.macro.resonance.label !== 'mixed'
                            ? ` · 共振 ${payload.research_input.macro.resonance.label}`
                            : ''}
                          {payload.research_input.macro.policy_source_health?.label
                          && payload.research_input.macro.policy_source_health.label !== 'unknown'
                            ? ` · 政策源 ${payload.research_input.macro.policy_source_health.label}`
                            : ''}
                          {payload.research_input.macro.department_chaos?.label
                          && payload.research_input.macro.department_chaos.label !== 'unknown'
                            ? ` · 部门 ${payload.research_input.macro.department_chaos.label}`
                            : ''}
                          {payload.research_input.macro.input_reliability?.label
                          && payload.research_input.macro.input_reliability.label !== 'unknown'
                            ? ` · 输入 ${payload.research_input.macro.input_reliability.label}`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.research_input?.macro?.policy_source_health?.reason ? (
                        <Text type="secondary">政策源 {payload.research_input.macro.policy_source_health.reason}</Text>
                      ) : null}
                      {payload.research_input?.macro?.department_chaos?.summary ? (
                        <Text type="secondary">部门混乱 {payload.research_input.macro.department_chaos.summary}</Text>
                      ) : null}
                      {payload.research_input?.macro?.input_reliability?.lead ? (
                        <Text type="secondary">
                          输入可靠度 {payload.research_input.macro.input_reliability.lead}
                          {payload.research_input.macro.input_reliability.score
                            ? ` · score ${Number(payload.research_input.macro.input_reliability.score || 0).toFixed(2)}`
                            : ''}
                          {payload.research_input.macro.input_reliability.posture
                            ? ` · ${payload.research_input.macro.input_reliability.posture}`
                            : ''}
                        </Text>
                      ) : null}
                      {payload.research_input?.alt_data?.top_categories?.length ? (
                        <Text type="secondary">
                          另类 {(payload.research_input.alt_data.top_categories || [])
                            .slice(0, 1)
                            .map((entry) => `${entry.category} ${entry.momentum === 'strengthening' ? '增强' : entry.momentum === 'weakening' ? '走弱' : '稳定'}`)
                            .join('，')}
                        </Text>
                      ) : null}
                    </Space>
                  )}
                </Space>
              )}
            />
          </List.Item>
        );
      }}
    />
  );
}
