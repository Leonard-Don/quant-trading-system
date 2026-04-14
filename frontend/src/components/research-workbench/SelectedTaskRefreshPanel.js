import React from 'react';
import { Card, Space, Tag, Typography } from 'antd';

const { Text } = Typography;

function SelectedTaskRefreshPanel({ selectedTaskRefreshSignal }) {
  return (
    <Card
      size="small"
      title="输入变化与更新建议"
      variant="borderless"
      extra={
        selectedTaskRefreshSignal ? (
          <Space wrap>
            <Tag color={selectedTaskRefreshSignal.refreshTone || 'default'}>
              {selectedTaskRefreshSignal.refreshLabel}
            </Tag>
            {selectedTaskRefreshSignal.resonanceDriven ? <Tag color="magenta">共振驱动</Tag> : null}
            {selectedTaskRefreshSignal.biasCompressionShift?.coreLegAffected ? <Tag color="volcano">核心腿受压</Tag> : null}
            {selectedTaskRefreshSignal.selectionQualityDriven ? <Tag color="orange">自动降级</Tag> : null}
            {selectedTaskRefreshSignal.selectionQualityRunState?.active ? <Tag color="gold">降级运行</Tag> : null}
            {selectedTaskRefreshSignal.reviewContextDriven ? <Tag color="geekblue">复核语境切换</Tag> : null}
            {selectedTaskRefreshSignal.structuralDecayRadarDriven ? <Tag color="volcano">系统衰败雷达</Tag> : null}
            {selectedTaskRefreshSignal.structuralDecayDriven ? <Tag color="volcano">结构性衰败</Tag> : null}
            {selectedTaskRefreshSignal.tradeThesisDriven ? <Tag color="cyan">交易 Thesis 漂移</Tag> : null}
            {selectedTaskRefreshSignal.peopleLayerDriven ? <Tag color="purple">人的维度</Tag> : null}
            {selectedTaskRefreshSignal.departmentChaosDriven ? <Tag color="volcano">部门混乱</Tag> : null}
            {selectedTaskRefreshSignal.inputReliabilityDriven ? <Tag color="blue">输入可靠度</Tag> : null}
            {selectedTaskRefreshSignal.policySourceDriven ? <Tag color="red">政策源驱动</Tag> : null}
            {selectedTaskRefreshSignal.biasCompressionDriven ? <Tag color="orange">偏置收缩</Tag> : null}
          </Space>
        ) : null
      }
    >
      {selectedTaskRefreshSignal ? (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Text strong>{selectedTaskRefreshSignal.recommendation}</Text>
          <Text type="secondary">{selectedTaskRefreshSignal.summary}</Text>
          {selectedTaskRefreshSignal.macroShift ? (
            <Text type="secondary">
              当前宏观分数 {Number(selectedTaskRefreshSignal.macroShift.currentScore || 0).toFixed(2)}
              {' · '}
              保存时 {Number(selectedTaskRefreshSignal.macroShift.savedScore || 0).toFixed(2)}
              {' · '}
              Δ{Number(selectedTaskRefreshSignal.macroShift.scoreGap || 0) >= 0 ? '+' : ''}{Number(selectedTaskRefreshSignal.macroShift.scoreGap || 0).toFixed(2)}
              {selectedTaskRefreshSignal.macroShift.signalShift
                ? ` · 信号 ${selectedTaskRefreshSignal.macroShift.savedSignal}→${selectedTaskRefreshSignal.macroShift.currentSignal}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.policySourceShift ? (
            <Text type="secondary">
              政策源 {selectedTaskRefreshSignal.policySourceShift.savedLabel}→{selectedTaskRefreshSignal.policySourceShift.currentLabel}
              {selectedTaskRefreshSignal.policySourceShift.fullTextRatioGap
                ? ` · 正文覆盖 ${selectedTaskRefreshSignal.policySourceShift.fullTextRatioGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.policySourceShift.fullTextRatioGap || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.policySourceShift.currentReason
                ? ` · ${selectedTaskRefreshSignal.policySourceShift.currentReason}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.inputReliabilityShift ? (
            <Text type="secondary">
              输入可靠度 {selectedTaskRefreshSignal.inputReliabilityShift.savedLabel}→{selectedTaskRefreshSignal.inputReliabilityShift.currentLabel}
              {selectedTaskRefreshSignal.inputReliabilityShift.scoreGap
                ? ` · score ${selectedTaskRefreshSignal.inputReliabilityShift.scoreGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.inputReliabilityShift.scoreGap || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.inputReliabilityShift.currentLead
                ? ` · ${selectedTaskRefreshSignal.inputReliabilityShift.currentLead}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.inputReliabilityShift?.actionHint ? (
            <Text strong style={{ color: '#1677ff' }}>
              {selectedTaskRefreshSignal.inputReliabilityShift.actionHint}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.departmentChaosShift ? (
            <Text type="secondary">
              部门混乱 {selectedTaskRefreshSignal.departmentChaosShift.savedLabel}→{selectedTaskRefreshSignal.departmentChaosShift.currentLabel}
              {selectedTaskRefreshSignal.departmentChaosShift.scoreGap
                ? ` · score ${selectedTaskRefreshSignal.departmentChaosShift.scoreGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.departmentChaosShift.scoreGap || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.departmentChaosShift.topDepartmentLabel
                ? ` · 焦点 ${selectedTaskRefreshSignal.departmentChaosShift.topDepartmentLabel}`
                : ''}
              {selectedTaskRefreshSignal.departmentChaosShift.topDepartmentReason
                ? ` · ${selectedTaskRefreshSignal.departmentChaosShift.topDepartmentReason}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.departmentChaosShift?.actionHint ? (
            <Text strong style={{ color: '#d4380d' }}>
              {selectedTaskRefreshSignal.departmentChaosShift.actionHint}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.selectionQualityShift ? (
            <Text type="secondary">
              自动降级 {selectedTaskRefreshSignal.selectionQualityShift.savedLabel}→{selectedTaskRefreshSignal.selectionQualityShift.currentLabel}
              {selectedTaskRefreshSignal.selectionQualityShift.penaltyGap
                ? ` · 惩罚 ${selectedTaskRefreshSignal.selectionQualityShift.penaltyGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.selectionQualityShift.penaltyGap || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.selectionQualityShift.currentReason
                ? ` · ${selectedTaskRefreshSignal.selectionQualityShift.currentReason}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.selectionQualityRunState?.active ? (
            <Text type="secondary">
              当前结果按 {selectedTaskRefreshSignal.selectionQualityRunState.label} 强度运行
              {selectedTaskRefreshSignal.selectionQualityRunState.baseScore || selectedTaskRefreshSignal.selectionQualityRunState.effectiveScore
                ? ` · 推荐分 ${Number(selectedTaskRefreshSignal.selectionQualityRunState.baseScore || 0).toFixed(2)}→${Number(selectedTaskRefreshSignal.selectionQualityRunState.effectiveScore || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.selectionQualityRunState.baseTier || selectedTaskRefreshSignal.selectionQualityRunState.effectiveTier
                ? ` · Tier ${selectedTaskRefreshSignal.selectionQualityRunState.baseTier || '-'}→${selectedTaskRefreshSignal.selectionQualityRunState.effectiveTier || '-'}`
                : ''}
              {selectedTaskRefreshSignal.selectionQualityRunState.rankingPenalty
                ? ` · 惩罚 ${Number(selectedTaskRefreshSignal.selectionQualityRunState.rankingPenalty || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.selectionQualityRunState.reason
                ? ` · ${selectedTaskRefreshSignal.selectionQualityRunState.reason}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.selectionQualityRunState?.active ? (
            <Text strong style={{ color: '#ad6800' }}>
              当前保存结果已经在降级强度下运行，建议优先重看研究页而不是只做被动观察。
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.reviewContextShift?.lead ? (
            <Text type="secondary">
              {selectedTaskRefreshSignal.reviewContextShift.lead}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.reviewContextShift?.actionHint ? (
            <Text strong style={{ color: '#1d39c4' }}>
              {selectedTaskRefreshSignal.reviewContextShift.actionHint}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.structuralDecayRadarShift ? (
            <Text type="secondary">
              系统衰败雷达 {selectedTaskRefreshSignal.structuralDecayRadarShift.savedLabel}→{selectedTaskRefreshSignal.structuralDecayRadarShift.currentLabel}
              {selectedTaskRefreshSignal.structuralDecayRadarShift.scoreGap
                ? ` · score ${selectedTaskRefreshSignal.structuralDecayRadarShift.scoreGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.structuralDecayRadarShift.scoreGap || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.structuralDecayRadarShift.criticalAxisGap
                ? ` · 关键轴 ${selectedTaskRefreshSignal.structuralDecayRadarShift.criticalAxisGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.structuralDecayRadarShift.criticalAxisGap || 0)}`
                : ''}
              {selectedTaskRefreshSignal.structuralDecayRadarShift.topSignalSummary
                ? ` · ${selectedTaskRefreshSignal.structuralDecayRadarShift.topSignalSummary}`
                : ''}
              {selectedTaskRefreshSignal.structuralDecayRadarShift.currentSummary
                ? ` · ${selectedTaskRefreshSignal.structuralDecayRadarShift.currentSummary}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.structuralDecayRadarShift?.actionHint ? (
            <Text strong style={{ color: '#d4380d' }}>
              {selectedTaskRefreshSignal.structuralDecayRadarShift.actionHint}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.structuralDecayShift ? (
            <Text type="secondary">
              衰败判断 {selectedTaskRefreshSignal.structuralDecayShift.savedAction}→{selectedTaskRefreshSignal.structuralDecayShift.currentAction}
              {selectedTaskRefreshSignal.structuralDecayShift.scoreGap
                ? ` · score ${selectedTaskRefreshSignal.structuralDecayShift.scoreGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.structuralDecayShift.scoreGap || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.structuralDecayShift.currentFailure
                ? ` · ${selectedTaskRefreshSignal.structuralDecayShift.currentFailure}`
                : ''}
              {selectedTaskRefreshSignal.structuralDecayShift.currentSummary
                ? ` · ${selectedTaskRefreshSignal.structuralDecayShift.currentSummary}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.structuralDecayShift?.evidenceSummary ? (
            <Text type="secondary">
              衰败证据 {selectedTaskRefreshSignal.structuralDecayShift.evidenceSummary}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.structuralDecayShift?.actionHint ? (
            <Text strong style={{ color: '#cf1322' }}>
              {selectedTaskRefreshSignal.structuralDecayShift.actionHint}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.tradeThesisShift ? (
            <Text type="secondary">
              交易 Thesis
              {selectedTaskRefreshSignal.tradeThesisShift.savedStance
                ? ` ${selectedTaskRefreshSignal.tradeThesisShift.savedStance}→${selectedTaskRefreshSignal.tradeThesisShift.currentStance}`
                : ''}
              {selectedTaskRefreshSignal.tradeThesisShift.savedLeadLeg && selectedTaskRefreshSignal.tradeThesisShift.currentLeadLeg
                ? ` · 主腿 ${selectedTaskRefreshSignal.tradeThesisShift.savedLeadLeg}→${selectedTaskRefreshSignal.tradeThesisShift.currentLeadLeg}`
                : ''}
              {selectedTaskRefreshSignal.tradeThesisShift.currentSummary
                ? ` · ${selectedTaskRefreshSignal.tradeThesisShift.currentSummary}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.tradeThesisShift?.evidenceSummary ? (
            <Text type="secondary">
              Thesis 证据 {selectedTaskRefreshSignal.tradeThesisShift.evidenceSummary}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.tradeThesisShift?.actionHint ? (
            <Text strong style={{ color: '#08979c' }}>
              {selectedTaskRefreshSignal.tradeThesisShift.actionHint}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.peopleLayerShift ? (
            <Text type="secondary">
              人的维度 {selectedTaskRefreshSignal.peopleLayerShift.savedRiskLevel}→{selectedTaskRefreshSignal.peopleLayerShift.currentRiskLevel}
              {' · '}
              stance {selectedTaskRefreshSignal.peopleLayerShift.savedStance}→{selectedTaskRefreshSignal.peopleLayerShift.currentStance}
              {selectedTaskRefreshSignal.peopleLayerShift.fragilityGap
                ? ` · fragility ${selectedTaskRefreshSignal.peopleLayerShift.fragilityGap >= 0 ? '+' : ''}${Number(selectedTaskRefreshSignal.peopleLayerShift.fragilityGap || 0).toFixed(2)}`
                : ''}
              {selectedTaskRefreshSignal.peopleLayerShift.currentSummary
                ? ` · ${selectedTaskRefreshSignal.peopleLayerShift.currentSummary}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.peopleLayerShift?.evidenceSummary ? (
            <Text type="secondary">
              人事证据 {selectedTaskRefreshSignal.peopleLayerShift.evidenceSummary}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.peopleLayerShift?.actionHint ? (
            <Text strong style={{ color: '#722ed1' }}>
              {selectedTaskRefreshSignal.peopleLayerShift.actionHint}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.biasCompressionShift ? (
            <Text type="secondary">
              偏置收缩 {selectedTaskRefreshSignal.biasCompressionShift.savedLabel}→{selectedTaskRefreshSignal.biasCompressionShift.currentLabel}
              {' · '}
              scale {Number(selectedTaskRefreshSignal.biasCompressionShift.savedScale || 1).toFixed(2)}x→{Number(selectedTaskRefreshSignal.biasCompressionShift.currentScale || 1).toFixed(2)}x
              {selectedTaskRefreshSignal.biasCompressionShift.topCompressedAsset
                ? ` · 压缩焦点 ${selectedTaskRefreshSignal.biasCompressionShift.topCompressedAsset}`
                : ''}
              {selectedTaskRefreshSignal.biasCompressionShift.coreLegAffected
                ? ' · 主题核心腿已进入压缩焦点'
                : ''}
              {selectedTaskRefreshSignal.biasCompressionShift.currentReason
                ? ` · ${selectedTaskRefreshSignal.biasCompressionShift.currentReason}`
                : ''}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.altShift?.changedCategories?.length ? (
            <Text type="secondary">
              另类变化 {selectedTaskRefreshSignal.altShift.changedCategories
                .slice(0, 2)
                .map((item) => `${item.category} ${item.previousMomentum === 'strengthening' ? '增强' : item.previousMomentum === 'weakening' ? '走弱' : '稳定'}→${item.currentMomentum === 'strengthening' ? '增强' : item.currentMomentum === 'weakening' ? '走弱' : '稳定'}`)
                .join('，')}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.altShift?.emergentCategories?.length ? (
            <Text type="secondary">
              新热点 {selectedTaskRefreshSignal.altShift.emergentCategories
                .map((item) => `${item.category} ${item.momentum === 'strengthening' ? '增强' : item.momentum === 'weakening' ? '走弱' : '稳定'} ${item.delta >= 0 ? '+' : ''}${Number(item.delta || 0).toFixed(2)}`)
                .join('，')}
            </Text>
          ) : null}
          {selectedTaskRefreshSignal.factorShift?.length ? (
            <Text type="secondary">
              因子变化 {selectedTaskRefreshSignal.factorShift
                .map((item) => `${item.label} ${item.zScoreDelta >= 0 ? '+' : ''}${Number(item.zScoreDelta || 0).toFixed(2)}${item.signalChanged ? ' shift' : ''}`)
                .join('，')}
            </Text>
          ) : null}
        </Space>
      ) : (
        <Text type="secondary">当前任务还没有足够的输入快照，先继续积累研究记录。</Text>
      )}
    </Card>
  );
}

export default SelectedTaskRefreshPanel;
