import React from 'react';
import { Card, Col, Empty, Row, Tag, Typography } from 'antd';
import { resonanceColor } from './macroFactorColors';
import { PeopleLayerPanel, DepartmentChaosPanel, InputReliabilityPanel } from './MacroSummaryPanels';
import FactorCard from './FactorCard';
import FactorTable from './FactorTable';

const { Text } = Typography;

const CLUSTER_LABELS = {
  positive_cluster: '正向共振',
  negative_cluster: '负向共振',
  weakening: '同步衰减',
  precursor: '反转前兆',
  reversed_factors: '已反转',
};

const CONFIDENCE_METRICS = [
  { key: 'penalized_factor_count', label: 'confidence penalty' },
  { key: 'boosted_factor_count', label: 'confidence bonus' },
  { key: 'blind_spot_factor_count', label: 'blind spot' },
  { key: 'unstable_factor_count', label: 'unstable' },
  { key: 'lagging_factor_count', label: 'lagging' },
  { key: 'concentrated_factor_count', label: 'concentrated' },
  { key: 'drifting_factor_count', label: 'drifting' },
  { key: 'broken_flow_factor_count', label: 'broken flow' },
  { key: 'confirmed_factor_count', label: 'confirmed' },
  { key: 'dominance_shift_factor_count', label: 'dominance shift' },
  { key: 'inconsistent_factor_count', label: 'inconsistent' },
  { key: 'reversing_factor_count', label: 'reversing' },
  { key: 'precursor_factor_count', label: 'precursor' },
];

function MacroFactorPanel({ model = {}, onNavigate }) {
  const topFactors = model.topFactors || [];
  const factors = model.factors || [];
  const providerHealth = model.providerHealth || {};
  const staleness = model.staleness || {};
  const macroTrend = model.macroTrend || {};
  const resonanceSummary = model.resonanceSummary || {};
  const overallEvidence = model.evidenceSummary || {};
  const confidenceAdj = model.confidenceAdjustment || {};

  return (
    <Card
      title="Macro Factor Panel"
      variant="borderless"
      extra={<Tag color={staleness.is_stale ? 'orange' : 'green'}>{staleness.label || 'fresh'}</Tag>}
      styles={{ body: { display: 'flex', flexDirection: 'column', gap: 16 } }}
    >
      {factors.length ? (
        <>
          <PeopleLayerPanel peopleLayerSummary={model.peopleLayerSummary} />
          <DepartmentChaosPanel departmentChaosSummary={model.departmentChaosSummary} />
          <InputReliabilityPanel inputReliabilitySummary={model.inputReliabilitySummary} />

          <Row gutter={[12, 12]}>
            {topFactors.map((factor) => (
              <Col xs={24} md={8} key={factor.name}>
                <FactorCard factor={factor} onNavigate={onNavigate} />
              </Col>
            ))}
          </Row>

          <FactorTable factors={factors} />

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            {resonanceSummary?.label ? (
              <Text type="secondary">
                <Tag color={resonanceColor[resonanceSummary.label] || 'blue'}>resonance {resonanceSummary.label}</Tag>
                {resonanceSummary.reason}
              </Text>
            ) : null}
            {Object.keys(CLUSTER_LABELS).map((key) =>
              resonanceSummary?.[key]?.length ? (
                <Text key={key} type="secondary">{CLUSTER_LABELS[key]} {resonanceSummary[key].join('，')}</Text>
              ) : null
            )}
            <Text type="secondary">healthy {providerHealth.healthy_providers || 0}</Text>
            <Text type="secondary">degraded {providerHealth.degraded_providers || 0}</Text>
            <Text type="secondary">error {providerHealth.error_providers || 0}</Text>
            <Text type="secondary">
              macro Δ {Number(macroTrend.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(macroTrend.macro_score_delta || 0).toFixed(3)}
            </Text>
            {CONFIDENCE_METRICS.map(({ key, label }) =>
              Number(confidenceAdj[key] || 0) > 0 ? (
                <Text key={key} type="secondary">{label} {Number(confidenceAdj[key] || 0)} 因子</Text>
              ) : null
            )}
            <Text type="secondary">
              evidence {overallEvidence.source_count || 0} 源 / {overallEvidence.record_count || 0} 条
              {overallEvidence.official_source_count ? ` · 官方源 ${overallEvidence.official_source_count}` : ''}
              {overallEvidence.freshness_label ? ` · ${overallEvidence.freshness_label}` : ''}
              {overallEvidence.conflict_level && overallEvidence.conflict_level !== 'none' ? ` · conflict ${overallEvidence.conflict_level}` : ''}
              {overallEvidence.conflict_trend && overallEvidence.conflict_level !== 'none' ? ` · ${overallEvidence.conflict_trend}` : ''}
            </Text>
          </div>
        </>
      ) : (
        <Empty description="暂无宏观因子" />
      )}
    </Card>
  );
}

export default MacroFactorPanel;
