import React from 'react';
import { Space, Tag, Typography } from 'antd';

import { formatResearchSource } from '../../utils/researchContext';
import { buildSnapshotComparison } from './snapshotCompare';
import { buildRefreshPriorityMeta } from './workbenchSelectors';
import {
  buildRefreshPriorityChangeSummary,
  extractSnapshotViewContext,
  extractLatestRefreshPriorityEvent,
  getRefreshPriorityChangeColor,
} from './workbenchUtils';

const { Text } = Typography;

function WorkbenchTaskCard({
  task,
  status,
  isSelected,
  isOverTarget,
  refreshSignal,
  onSelect,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
}) {
  const taskTypeColor = task.type === 'pricing'
    ? 'blue'
    : task.type === 'macro_mispricing'
      ? 'volcano'
      : task.type === 'trade_thesis'
        ? 'cyan'
      : 'purple';
  const templateMeta = task.snapshot?.payload?.template_meta || {};
  const executionPlan = task.snapshot?.payload?.execution_plan || {};
  const structuralDecay = task.snapshot?.payload?.structural_decay || {};
  const peopleLayer = task.snapshot?.payload?.people_layer || {};
  const tradeThesis = task.snapshot?.payload?.trade_thesis || {};
  const history = task?.snapshot_history || [];
  const latestComparison = history.length >= 2
    ? buildSnapshotComparison(task.type, history[1], history[0])
    : null;
  const refreshPriorityMeta = buildRefreshPriorityMeta(refreshSignal);
  const latestRefreshPriorityEvent = extractLatestRefreshPriorityEvent(task);
  const latestRefreshPriorityChangeLabel = latestRefreshPriorityEvent?.meta?.change_label || '';
  const latestRefreshPriorityChangeColor = getRefreshPriorityChangeColor(
    latestRefreshPriorityEvent?.meta?.change_type || 'updated'
  );
  const latestRefreshPriorityChangeSummary = buildRefreshPriorityChangeSummary(latestRefreshPriorityEvent);
  const snapshotViewContext = extractSnapshotViewContext(task.snapshot);

  return (
    <div
      key={task.id}
      data-testid={`workbench-task-card-${task.id}`}
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onClick={onSelect}
      style={{
        cursor: 'grab',
        borderRadius: 12,
        padding: 12,
        marginBottom: 10,
        background: isSelected ? 'rgba(24,144,255,0.12)' : 'rgba(255,255,255,0.03)',
        border: isOverTarget
          ? '1px dashed rgba(24,144,255,0.7)'
          : isSelected
            ? '1px solid rgba(24,144,255,0.45)'
            : '1px solid rgba(255,255,255,0.08)',
      }}
    >
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <Space wrap>
          <Text strong>{task.title}</Text>
          <Tag color={taskTypeColor}>{task.type}</Tag>
          {templateMeta.recommendation_tier ? <Tag color="gold">{templateMeta.recommendation_tier}</Tag> : null}
          {templateMeta.selection_quality?.label && templateMeta.selection_quality.label !== 'original' ? (
            <Tag color="orange">自动降级</Tag>
          ) : null}
          {templateMeta.resonance_label && templateMeta.resonance_label !== 'mixed' ? (
            <Tag color="magenta">{templateMeta.resonance_label}</Tag>
          ) : null}
          {refreshSignal ? <Tag color={refreshSignal.refreshTone || 'default'}>{refreshSignal.refreshLabel}</Tag> : null}
          {refreshSignal?.resonanceDriven ? <Tag color="magenta">共振驱动</Tag> : null}
          {refreshSignal?.biasCompressionShift?.coreLegAffected ? <Tag color="volcano">核心腿受压</Tag> : null}
          {refreshSignal?.selectionQualityRunState?.active ? <Tag color="gold">降级运行</Tag> : null}
          {refreshSignal?.reviewContextDriven ? <Tag color="geekblue">复核语境切换</Tag> : null}
          {refreshSignal?.structuralDecayRadarDriven ? <Tag color="volcano">系统衰败雷达</Tag> : null}
          {refreshSignal?.structuralDecayDriven ? <Tag color="volcano">结构性衰败</Tag> : null}
          {refreshSignal?.tradeThesisDriven ? <Tag color="cyan">交易 Thesis 漂移</Tag> : null}
          {refreshSignal?.peopleLayerDriven ? <Tag color="purple">人的维度</Tag> : null}
          {refreshSignal?.departmentChaosDriven ? <Tag color="volcano">部门混乱</Tag> : null}
          {refreshSignal?.inputReliabilityDriven ? <Tag color="blue">输入可靠度</Tag> : null}
          {refreshSignal?.selectionQualityDriven ? <Tag color="orange">自动降级</Tag> : null}
          {refreshSignal?.policySourceDriven ? <Tag color="red">政策源驱动</Tag> : null}
          {refreshSignal?.biasCompressionDriven ? <Tag color="orange">偏置收缩</Tag> : null}
          {latestRefreshPriorityChangeLabel ? (
            <Tag color={latestRefreshPriorityChangeColor}>{latestRefreshPriorityChangeLabel}</Tag>
          ) : null}
        </Space>
        <Text type="secondary">{task.snapshot?.headline || '暂无快照摘要'}</Text>
        {snapshotViewContext.summary ? (
          <Text type="secondary">最近快照视角 {snapshotViewContext.summary}</Text>
        ) : null}
        {snapshotViewContext.scopedTaskLabel ? (
          <Text type="secondary">{snapshotViewContext.scopedTaskLabel}</Text>
        ) : null}
        {latestComparison?.lead ? (
          <Text type="secondary">
            最近两版：{latestComparison.lead}
          </Text>
        ) : null}
        {refreshPriorityMeta ? (
          <>
            <Text strong style={{ color: refreshSignal?.severity === 'high' ? '#cf1322' : '#d48806' }}>
              自动排序：{refreshPriorityMeta.reasonLabel}
            </Text>
            {latestRefreshPriorityChangeSummary ? (
              <Text type="secondary">{latestRefreshPriorityChangeSummary}</Text>
            ) : null}
            <Text type="secondary">
              {refreshPriorityMeta.lead}
              {refreshPriorityMeta.detail ? ` · ${refreshPriorityMeta.detail}` : ''}
            </Text>
          </>
        ) : null}
        {refreshSignal?.selectionQualityRunState?.active ? (
          <Text style={{ color: '#ad6800' }}>
            优先重看：当前结果已按 {refreshSignal.selectionQualityRunState.label} 强度运行
            {refreshSignal.selectionQualityRunState.baseScore || refreshSignal.selectionQualityRunState.effectiveScore
              ? ` · ${Number(refreshSignal.selectionQualityRunState.baseScore || 0).toFixed(2)}→${Number(refreshSignal.selectionQualityRunState.effectiveScore || 0).toFixed(2)}`
              : ''}
          </Text>
        ) : refreshSignal?.inputReliabilityShift?.actionHint ? (
          <Text style={{ color: '#1677ff' }}>
            输入可靠度：{refreshSignal.inputReliabilityShift.actionHint}
          </Text>
        ) : refreshSignal?.structuralDecayRadarShift?.actionHint ? (
          <Text style={{ color: '#d4380d' }}>
            系统衰败雷达：{refreshSignal.structuralDecayRadarShift.actionHint}
          </Text>
        ) : refreshSignal?.peopleLayerShift?.actionHint ? (
          <Text style={{ color: '#722ed1' }}>
            人的维度：{refreshSignal.peopleLayerShift.actionHint}
          </Text>
        ) : null}
        {refreshSignal?.structuralDecayRadarShift?.topSignalSummary ? (
          <Text type="secondary">
            雷达焦点 {refreshSignal.structuralDecayRadarShift.topSignalSummary}
          </Text>
        ) : null}
        {refreshSignal?.peopleLayerShift?.evidenceSummary ? (
          <Text type="secondary">
            人事证据 {refreshSignal.peopleLayerShift.evidenceSummary}
          </Text>
        ) : null}
        {refreshSignal?.structuralDecayShift?.evidenceSummary ? (
          <Text type="secondary">
            衰败证据 {refreshSignal.structuralDecayShift.evidenceSummary}
          </Text>
        ) : null}
        {refreshSignal?.tradeThesisShift?.evidenceSummary ? (
          <Text type="secondary">
            Thesis 证据 {refreshSignal.tradeThesisShift.evidenceSummary}
          </Text>
        ) : null}
        {task.type === 'macro_mispricing' && structuralDecay?.score !== undefined && structuralDecay?.score !== null ? (
          <Text type="secondary">
            衰败评分 {Number(structuralDecay.score || 0).toFixed(2)}
            {structuralDecay?.dominant_failure_label ? ` · ${structuralDecay.dominant_failure_label}` : ''}
          </Text>
        ) : null}
        {task.type === 'macro_mispricing' && peopleLayer?.risk_level ? (
          <Text type="secondary">
            人的维度 {peopleLayer.risk_level}
            {peopleLayer?.summary ? ` · ${peopleLayer.summary}` : ''}
          </Text>
        ) : null}
        {task.type === 'trade_thesis' && tradeThesis?.thesis?.stance ? (
          <Text type="secondary">
            Thesis {tradeThesis.thesis.stance}
            {tradeThesis?.symbol ? ` · ${tradeThesis.symbol}` : ''}
            {tradeThesis?.thesis?.horizon ? ` · ${tradeThesis.thesis.horizon}` : ''}
          </Text>
        ) : null}
        {task.type === 'trade_thesis' && tradeThesis?.results_summary?.total_return !== undefined ? (
          <Text type="secondary">
            回测 {(Number(tradeThesis.results_summary.total_return || 0) * 100).toFixed(2)}%
            {tradeThesis?.results_summary?.sharpe_ratio !== undefined
              ? ` · Sharpe ${Number(tradeThesis.results_summary.sharpe_ratio || 0).toFixed(2)}`
              : ''}
          </Text>
        ) : null}
        {refreshSignal?.severity && refreshSignal.severity !== 'low' ? (
          <Text type="secondary">{refreshSignal.summary}</Text>
        ) : null}
        {templateMeta.theme ? <Text type="secondary">{templateMeta.theme}</Text> : null}
        {templateMeta.resonance_reason ? <Text type="secondary">{templateMeta.resonance_reason}</Text> : null}
        {templateMeta.bias_summary ? <Text type="secondary">{templateMeta.bias_summary}</Text> : null}
        {templateMeta.base_recommendation_score !== null
        && templateMeta.base_recommendation_score !== undefined ? (
          <Text type="secondary">
            推荐强度 {Number(templateMeta.base_recommendation_score || 0).toFixed(2)}
            {templateMeta.recommendation_score !== null && templateMeta.recommendation_score !== undefined
              ? ` -> ${Number(templateMeta.recommendation_score || 0).toFixed(2)}`
              : ''}
          </Text>
        ) : null}
        {templateMeta.selection_quality?.label && templateMeta.selection_quality.label !== 'original' ? (
          <Text type="secondary">
            自动降级 {templateMeta.selection_quality.label}
            {templateMeta.selection_quality?.reason ? ` · ${templateMeta.selection_quality.reason}` : ''}
          </Text>
        ) : null}
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
            {templateMeta.bias_quality_reason ? ` · ${templateMeta.bias_quality_reason}` : ''}
          </Text>
        ) : null}
        {templateMeta.core_leg_pressure?.affected ? (
          <Text type="secondary">
            核心腿受压 {templateMeta.core_leg_pressure.summary || templateMeta.core_leg_pressure.symbol}
          </Text>
        ) : null}
        {task.snapshot?.payload?.allocation_overlay?.compressed_assets?.length ? (
          <Text type="secondary">
            压缩焦点 {task.snapshot.payload.allocation_overlay.compressed_assets.join('，')}
            {task.snapshot.payload.allocation_overlay.compression_summary?.compression_effect !== undefined
              ? ` · 收缩 ${Number(task.snapshot.payload.allocation_overlay.compression_summary.compression_effect || 0).toFixed(1)}pp`
              : ''}
          </Text>
        ) : null}
        {templateMeta.bias_actions?.length ? (
          <Text type="secondary">
            {(templateMeta.bias_actions || []).slice(0, 2).map((item) => `${item.action === 'increase' ? '增配' : '减配'} ${item.symbol}`).join('，')}
          </Text>
        ) : null}
        {templateMeta.driver_summary?.length ? (
          <Text type="secondary">
            {(templateMeta.driver_summary || []).slice(0, 2).map((item) => `${item.label} ${Number(item.value || 0).toFixed(2)}`).join('，')}
          </Text>
        ) : null}
        {templateMeta.theme_core ? <Text type="secondary">{templateMeta.theme_core}</Text> : null}
        {task.snapshot?.payload?.allocation_overlay?.max_delta_weight ? (
          <Text type="secondary">
            最大偏移 {(Number(task.snapshot.payload.allocation_overlay.max_delta_weight || 0) * 100).toFixed(2)}pp
          </Text>
        ) : null}
        <Text type="secondary">
          {task.symbol || task.template || '-'} · {formatResearchSource(task.source || 'manual')}
        </Text>
        {executionPlan.route_count ? (
          <Text type="secondary">
            路由 {executionPlan.route_count} · 批次 {(executionPlan.batches || []).length}
          </Text>
        ) : null}
        {task.snapshot?.payload?.execution_diagnostics?.concentration_level ? (
          <Text type="secondary">
            集中度 {task.snapshot.payload.execution_diagnostics.concentration_level}
          </Text>
        ) : null}
        {task.snapshot?.payload?.execution_diagnostics?.liquidity_level ? (
          <Text type="secondary">
            流动性 {task.snapshot.payload.execution_diagnostics.liquidity_level}
            {task.snapshot.payload.execution_diagnostics.max_adv_usage !== undefined
              ? ` · Max ADV ${(Number(task.snapshot.payload.execution_diagnostics.max_adv_usage || 0) * 100).toFixed(2)}%`
              : ''}
          </Text>
        ) : null}
        {task.snapshot?.payload?.execution_diagnostics?.margin_level ? (
          <Text type="secondary">
            保证金 {task.snapshot.payload.execution_diagnostics.margin_level}
            {task.snapshot.payload.execution_diagnostics.margin_utilization !== undefined
              ? ` · ${(Number(task.snapshot.payload.execution_diagnostics.margin_utilization || 0) * 100).toFixed(2)}%`
              : ''}
            {task.snapshot.payload.execution_diagnostics.gross_leverage !== undefined
              ? ` · Gross ${Number(task.snapshot.payload.execution_diagnostics.gross_leverage || 0).toFixed(2)}x`
              : ''}
          </Text>
        ) : null}
        {task.snapshot?.payload?.execution_diagnostics?.beta_level ? (
          <Text type="secondary">
            Beta {task.snapshot.payload.execution_diagnostics.beta_level}
            {task.snapshot.payload.hedge_portfolio?.beta_neutrality?.beta !== undefined
              ? ` · ${Number(task.snapshot.payload.hedge_portfolio.beta_neutrality.beta || 0).toFixed(2)}`
              : ''}
          </Text>
        ) : null}
        {task.snapshot?.payload?.execution_diagnostics?.calendar_level ? (
          <Text type="secondary">
            日历 {task.snapshot.payload.execution_diagnostics.calendar_level}
            {task.snapshot.payload.data_alignment?.calendar_diagnostics?.max_mismatch_ratio !== undefined
              ? ` · mismatch ${(Number(task.snapshot.payload.data_alignment.calendar_diagnostics.max_mismatch_ratio || 0) * 100).toFixed(2)}%`
              : ''}
          </Text>
        ) : null}
        {task.snapshot?.payload?.execution_diagnostics?.suggested_rebalance ? (
          <Text type="secondary">
            调仓 {task.snapshot.payload.execution_diagnostics.suggested_rebalance}
          </Text>
        ) : null}
        {task.snapshot?.payload?.execution_plan?.execution_stress?.worst_case ? (
          <Text type="secondary">
            压测 {task.snapshot.payload.execution_plan.execution_stress.worst_case.label}
          </Text>
        ) : null}
        {task.snapshot?.payload?.research_input?.macro ? (
          <Text type="secondary">
            宏观 {Number(task.snapshot.payload.research_input.macro.macro_score || 0).toFixed(2)}
            {' · '}
            Δ{Number(task.snapshot.payload.research_input.macro.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(task.snapshot.payload.research_input.macro.macro_score_delta || 0).toFixed(2)}
            {task.snapshot.payload.research_input.macro.resonance?.label && task.snapshot.payload.research_input.macro.resonance.label !== 'mixed'
              ? ` · 共振 ${task.snapshot.payload.research_input.macro.resonance.label}`
              : ''}
            {task.snapshot.payload.research_input.macro.policy_source_health?.label
            && task.snapshot.payload.research_input.macro.policy_source_health.label !== 'unknown'
              ? ` · 政策源 ${task.snapshot.payload.research_input.macro.policy_source_health.label}`
              : ''}
            {task.snapshot.payload.research_input.macro.input_reliability?.label
            && task.snapshot.payload.research_input.macro.input_reliability.label !== 'unknown'
              ? ` · 输入 ${task.snapshot.payload.research_input.macro.input_reliability.label}`
              : ''}
          </Text>
        ) : null}
        {task.snapshot?.payload?.research_input?.macro?.policy_source_health?.reason ? (
          <Text type="secondary">
            政策源 {task.snapshot.payload.research_input.macro.policy_source_health.reason}
          </Text>
        ) : null}
        {task.snapshot?.payload?.research_input?.macro?.input_reliability?.lead ? (
          <Text type="secondary">
            输入可靠度 {task.snapshot.payload.research_input.macro.input_reliability.lead}
            {task.snapshot.payload.research_input.macro.input_reliability.score
              ? ` · score ${Number(task.snapshot.payload.research_input.macro.input_reliability.score || 0).toFixed(2)}`
              : ''}
            {task.snapshot.payload.research_input.macro.input_reliability.posture
              ? ` · ${task.snapshot.payload.research_input.macro.input_reliability.posture}`
              : ''}
          </Text>
        ) : null}
        {task.snapshot?.payload?.research_input?.alt_data?.top_categories?.length ? (
          <Text type="secondary">
            另类 {(task.snapshot.payload.research_input.alt_data.top_categories || [])
              .slice(0, 1)
              .map((item) => `${item.category} ${item.momentum === 'strengthening' ? '增强' : item.momentum === 'weakening' ? '走弱' : '稳定'}`)
              .join('，')}
          </Text>
        ) : null}
        <Text type="secondary">{new Date(task.updated_at).toLocaleString()}</Text>
      </Space>
    </div>
  );
}

export default WorkbenchTaskCard;
