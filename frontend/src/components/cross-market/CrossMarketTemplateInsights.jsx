/**
 * Banner stack rendered above the cross-market layout: the selected-template
 * narrative alert, the applied macro-bias alert, the suggested increase/reduce
 * roster, the theme-conclusion card, and the top-recommendation alert.
 *
 * Pure presentational split (layer 2): every value is derived in the host panel
 * and passed down as props. No state, no data fetching. Extracted verbatim from
 * CrossMarketBacktestPanel.jsx to keep behaviour identical.
 */

import { Alert, Space, Tag, Typography } from 'antd';

import { Panel } from '../../design/components';

import {
  formatBiasQualityLabel,
  formatSignalLabel,
  formatSignalList,
  formatStatusLabel,
  formatTemplateName,
  formatTemplateNarrative,
  formatTemplateTheme,
} from '../../utils/crossMarketFormatters';
import {
  getReviewPriorityContextLine,
  getReviewPriorityTitleSuffix,
} from '../../utils/crossMarketReviewHelpers';
import {
  CROSS_MARKET_DIMENSION_LABELS,
  CROSS_MARKET_FACTOR_LABELS,
} from '../../utils/crossMarketRecommendations';

const { Text } = Typography;

function CrossMarketTemplateInsights({
  researchContext,
  selectedTemplate,
  selectedTemplateSelectionQualityLines,
  appliedBiasMeta,
  effectiveTemplate,
  topRecommendation,
  topRecommendationNeedsPriorityReview,
  topRecommendationSelectionQualityLines,
}) {
  return (
    <div className="app-page-banner-stack">
      {selectedTemplate ? (
        <Alert
          type="info"
          showIcon
          message={`当前模板主题：${formatTemplateTheme(selectedTemplate)}${selectedTemplate.recommendationTier ? ` · ${selectedTemplate.recommendationTier}` : ''}`}
          description={(
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Text>{formatTemplateNarrative(selectedTemplate.narrative || selectedTemplate.description)}</Text>
              {selectedTemplate.driverHeadline ? (
                <Text type="secondary">{selectedTemplate.driverHeadline}</Text>
              ) : null}
              {selectedTemplate.resonanceReason && selectedTemplate.resonanceLabel !== 'mixed' ? (
                <Text type="secondary">{selectedTemplate.resonanceReason}</Text>
              ) : null}
              <Space wrap size={[6, 6]}>
                {(selectedTemplate.linked_factors || []).map((factor) => (
                  <Tag key={`factor-${factor}`} color="purple">
                    因子: {CROSS_MARKET_FACTOR_LABELS[factor] || factor}
                  </Tag>
                ))}
                {(selectedTemplate.linked_dimensions || []).map((dimension) => (
                  <Tag key={`dimension-${dimension}`} color="blue">
                    维度: {CROSS_MARKET_DIMENSION_LABELS[dimension] || dimension}
                  </Tag>
                ))}
                {selectedTemplate.resonanceLabel && selectedTemplate.resonanceLabel !== 'mixed' ? (
                  <Tag color="magenta">共振 {formatStatusLabel(selectedTemplate.resonanceLabel)}</Tag>
                ) : null}
                {selectedTemplate.policySourceHealthLabel && selectedTemplate.policySourceHealthLabel !== 'unknown' ? (
                  <Tag color={selectedTemplate.policySourceHealthLabel === 'fragile' ? 'red' : selectedTemplate.policySourceHealthLabel === 'watch' ? 'gold' : 'green'}>
                    政策来源 {formatStatusLabel(selectedTemplate.policySourceHealthLabel)}
                  </Tag>
                ) : null}
                {selectedTemplate.inputReliabilityLabel && selectedTemplate.inputReliabilityLabel !== 'unknown' ? (
                  <Tag color={selectedTemplate.inputReliabilityLabel === 'fragile' ? 'red' : selectedTemplate.inputReliabilityLabel === 'watch' ? 'gold' : 'green'}>
                    输入可靠度 {formatStatusLabel(selectedTemplate.inputReliabilityLabel)}
                  </Tag>
                ) : null}
                {selectedTemplate.sourceModeLabel && selectedTemplate.sourceModeLabel !== 'mixed' ? (
                  <Tag color={selectedTemplate.sourceModeLabel === 'official-led' ? 'green' : selectedTemplate.sourceModeLabel === 'fallback-heavy' ? 'orange' : 'blue'}>
                    来源 {formatStatusLabel(selectedTemplate.sourceModeLabel)}
                  </Tag>
                ) : null}
                {selectedTemplate.policyExecutionLabel && selectedTemplate.policyExecutionLabel !== 'unknown' ? (
                  <Tag color={selectedTemplate.policyExecutionLabel === 'chaotic' ? 'red' : selectedTemplate.policyExecutionLabel === 'watch' ? 'gold' : 'green'}>
                    政策执行 {formatStatusLabel(selectedTemplate.policyExecutionLabel)}
                  </Tag>
                ) : null}
                {selectedTemplate.executionPosture ? (
                  <Tag color="lime">{formatSignalLabel(selectedTemplate.executionPosture)}</Tag>
                ) : null}
              </Space>
              {(selectedTemplate.themeCore || selectedTemplate.themeSupport) ? (
                <Text type="secondary">
                  核心腿：{formatSignalList(selectedTemplate.themeCore) || '暂无'} · 辅助腿：{formatSignalList(selectedTemplate.themeSupport) || '暂无'}
                </Text>
              ) : null}
              {selectedTemplate.policySourceHealthReason ? (
                <Text type="secondary">{selectedTemplate.policySourceHealthReason}</Text>
              ) : null}
              {selectedTemplate.policyExecutionReason ? (
                <Text type="secondary">
                  政策执行：{selectedTemplate.policyExecutionReason}
                  {selectedTemplate.policyExecutionTopDepartment
                    ? ` · ${selectedTemplate.policyExecutionTopDepartment}`
                    : ''}
                  {selectedTemplate.policyExecutionRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(selectedTemplate.policyExecutionRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {selectedTemplate.sourceModeReason ? (
                <Text type="secondary">
                  来源治理：{selectedTemplate.sourceModeReason}
                  {selectedTemplate.sourceModeRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(selectedTemplate.sourceModeRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {selectedTemplate.inputReliabilityLead ? (
                <Text type="secondary">
                  输入可靠度：{selectedTemplate.inputReliabilityLead}
                  {selectedTemplate.inputReliabilityScore
                    ? ` · 评分 ${Number(selectedTemplate.inputReliabilityScore || 0).toFixed(2)}`
                    : ''}
                </Text>
              ) : null}
              {selectedTemplate.inputReliabilityPosture ? (
                <Text type="secondary">使用姿势：{selectedTemplate.inputReliabilityPosture}</Text>
              ) : null}
              {selectedTemplate.refreshMeta?.inputReliabilityShift?.actionHint ? (
                <Text type="secondary">{selectedTemplate.refreshMeta.inputReliabilityShift.actionHint}</Text>
              ) : null}
              {selectedTemplateSelectionQualityLines.map((line) => (
                <Text key={line} type="secondary">
                  {line}
                </Text>
              ))}
              {selectedTemplate.biasQualityLabel && selectedTemplate.biasQualityLabel !== 'full' ? (
                <Text type="secondary">
                  偏置收缩 {formatBiasQualityLabel(selectedTemplate.biasQualityLabel)} · {selectedTemplate.biasQualityReason}
                </Text>
              ) : null}
            </Space>
          )}
        />
      ) : null}

      {appliedBiasMeta ? (
        <Alert
          type="success"
          showIcon
          message={`宏观权重偏置已启用 · 强度 ${Number(appliedBiasMeta.strength || 0).toFixed(1)}pp`}
          description={(
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
              <Text>{appliedBiasMeta.summary}</Text>
              {appliedBiasMeta.qualityLabel && appliedBiasMeta.qualityLabel !== 'full' ? (
                <Text type="secondary">偏置收缩 {formatBiasQualityLabel(appliedBiasMeta.qualityLabel)} · {appliedBiasMeta.qualityReason}</Text>
              ) : null}
              {appliedBiasMeta.departmentChaosLabel && appliedBiasMeta.departmentChaosLabel !== 'unknown' ? (
                <Text type="secondary">
                  部门混乱 {formatStatusLabel(appliedBiasMeta.departmentChaosLabel)}
                  {appliedBiasMeta.departmentChaosTopDepartment ? ` · ${appliedBiasMeta.departmentChaosTopDepartment}` : ''}
                  {appliedBiasMeta.departmentChaosRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.departmentChaosRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.peopleFragilityLabel && appliedBiasMeta.peopleFragilityLabel !== 'stable' ? (
                <Text type="secondary">
                  人的维度 {formatStatusLabel(appliedBiasMeta.peopleFragilityLabel)}
                  {appliedBiasMeta.peopleFragilityFocus ? ` · ${appliedBiasMeta.peopleFragilityFocus}` : ''}
                  {appliedBiasMeta.peopleFragilityRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.peopleFragilityRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.policyExecutionLabel && appliedBiasMeta.policyExecutionLabel !== 'unknown' ? (
                <Text type="secondary">
                  政策执行 {formatStatusLabel(appliedBiasMeta.policyExecutionLabel)}
                  {appliedBiasMeta.policyExecutionTopDepartment ? ` · ${appliedBiasMeta.policyExecutionTopDepartment}` : ''}
                  {appliedBiasMeta.policyExecutionRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.policyExecutionRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.sourceModeLabel && appliedBiasMeta.sourceModeLabel !== 'mixed' ? (
                <Text type="secondary">
                  来源治理 {formatStatusLabel(appliedBiasMeta.sourceModeLabel)}
                  {appliedBiasMeta.sourceModeReason ? ` · ${appliedBiasMeta.sourceModeReason}` : ''}
                  {appliedBiasMeta.sourceModeRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.sourceModeRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              {appliedBiasMeta.structuralDecayRadarLabel && appliedBiasMeta.structuralDecayRadarLabel !== 'stable' ? (
                <Text type="secondary">
                  结构衰败 {appliedBiasMeta.structuralDecayRadarDisplayLabel || formatStatusLabel(appliedBiasMeta.structuralDecayRadarLabel)}
                  {appliedBiasMeta.structuralDecayRadarScore !== undefined
                    ? ` · ${Math.round(Number(appliedBiasMeta.structuralDecayRadarScore || 0) * 100)}%`
                    : ''}
                  {appliedBiasMeta.structuralDecayRadarRiskBudgetScale !== undefined
                    ? ` · 风险预算 ${Number(appliedBiasMeta.structuralDecayRadarRiskBudgetScale || 1).toFixed(2)}x`
                    : ''}
                </Text>
              ) : null}
              <Space wrap size={[6, 6]}>
                {(appliedBiasMeta.highlights || []).map((item) => (
                  <Tag key={item} color="green">{formatSignalLabel(item)}</Tag>
                ))}
              </Space>
            </Space>
          )}
        />
      ) : null}

      {effectiveTemplate?.biasActions?.length ? (
        <Panel title="建议增减仓名单">
          <Space wrap size={[8, 8]}>
            {effectiveTemplate.biasActions.map((item) => (
              <Tag key={`${item.side}-${item.symbol}`} color={item.action === 'increase' ? 'green' : 'orange'}>
                {item.action === 'increase' ? '增配' : '减配'} {item.symbol} {item.delta > 0 ? '+' : ''}{(Number(item.delta || 0) * 100).toFixed(1)}pp
              </Tag>
            ))}
          </Space>
        </Panel>
      ) : null}

      {effectiveTemplate?.dominantDrivers?.length ? (
        <Panel title="主题结论">
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Text>{formatSignalList(effectiveTemplate.themeCore) || '暂无主题核心腿'}</Text>
            <Text type="secondary">辅助腿：{formatSignalList(effectiveTemplate.themeSupport) || '无'}</Text>
            <Space wrap size={[6, 6]}>
              {effectiveTemplate.dominantDrivers.map((item) => (
                <Tag key={item.key} color="purple">
                  主导驱动 {item.label} {Number(item.value || 0).toFixed(2)}
                </Tag>
              ))}
            </Space>
          </Space>
        </Panel>
      ) : null}

      {!researchContext?.template && topRecommendation ? (
        <Alert
          type={topRecommendationNeedsPriorityReview ? 'warning' : 'success'}
          showIcon
          message={`当前首选模板：${formatTemplateName(topRecommendation)}${topRecommendationNeedsPriorityReview ? ` · ${getReviewPriorityTitleSuffix(topRecommendation?.refreshMeta)}` : ''}`}
          description={`${topRecommendation.driverHeadline}。${
            topRecommendation.recentComparisonLead
              ? `最近两版：${topRecommendation.recentComparisonLead}。`
              : ''
          }${
            topRecommendationNeedsPriorityReview
              ? getReviewPriorityContextLine(topRecommendation?.refreshMeta)
              : ''
          }${
            topRecommendation.rankingPenaltyReason
            || topRecommendationSelectionQualityLines[0]
            || topRecommendation.biasSummary
            || '该模板会作为默认起点，你也可以在右侧改成其他模板。'
          }`}
        />
      ) : null}
    </div>
  );
}

export default CrossMarketTemplateInsights;
