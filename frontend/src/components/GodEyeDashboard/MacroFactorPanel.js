import React from 'react';
import { Button, Card, Col, Empty, Row, Space, Statistic, Table, Tag, Typography } from 'antd';

const { Text } = Typography;

const signalColor = {
  1: 'red',
  0: 'gold',
  '-1': 'green',
};

const conflictColor = {
  high: 'red',
  medium: 'orange',
  low: 'gold',
  none: 'default',
};

const conflictTrendColor = {
  rising: 'volcano',
  easing: 'green',
  stable: 'blue',
};

const coverageColor = {
  strong: 'green',
  partial: 'blue',
  thin: 'gold',
  sparse: 'red',
};

const blindSpotColor = {
  high: 'red',
  medium: 'orange',
  none: 'default',
};

const stabilityColor = {
  unstable: 'red',
  choppy: 'orange',
  stable: 'green',
};

const lagColor = {
  high: 'red',
  medium: 'orange',
  low: 'gold',
  none: 'green',
};

const concentrationColor = {
  high: 'red',
  medium: 'orange',
  low: 'green',
  none: 'default',
};

const driftColor = {
  degrading: 'red',
  improving: 'green',
  stable: 'blue',
  none: 'default',
  positive: 'green',
};

const flowColor = {
  broken: 'red',
  stretching: 'orange',
  stable: 'green',
  none: 'default',
};

const confirmationColor = {
  strong: 'green',
  moderate: 'blue',
  weak: 'gold',
  none: 'default',
};

const dominanceColor = {
  rotating: 'orange',
  derived_dominant: 'red',
  official_dominant: 'green',
  stable: 'blue',
  none: 'default',
};

const consistencyColor = {
  strong: 'green',
  moderate: 'blue',
  divergent: 'red',
  weak: 'gold',
  unknown: 'default',
};

const reversalColor = {
  reversed: 'red',
  fading: 'orange',
  emerging: 'blue',
  stable: 'green',
  none: 'default',
};

const precursorColor = {
  high: 'volcano',
  medium: 'gold',
  none: 'default',
};

const resonanceColor = {
  bullish_cluster: 'green',
  bearish_cluster: 'red',
  precursor_cluster: 'orange',
  fading_cluster: 'gold',
  reversal_cluster: 'volcano',
  mixed: 'blue',
};

const policySourceColor = {
  healthy: 'green',
  watch: 'gold',
  fragile: 'red',
  unknown: 'default',
};

function MacroFactorPanel({ model = {}, onNavigate }) {
  const topFactors = model.topFactors || [];
  const factors = model.factors || [];
  const providerHealth = model.providerHealth || {};
  const staleness = model.staleness || {};
  const macroTrend = model.macroTrend || {};
  const resonanceSummary = model.resonanceSummary || {};
  const overallEvidence = model.evidenceSummary || {};
  const clusterLabels = {
    positive_cluster: '正向共振',
    negative_cluster: '负向共振',
    weakening: '同步衰减',
    precursor: '反转前兆',
    reversed_factors: '已反转',
  };

  return (
    <Card
      title="Macro Factor Panel"
      bordered={false}
      extra={
        <Tag color={staleness.is_stale ? 'orange' : 'green'}>
          {staleness.label || 'fresh'}
        </Tag>
      }
      bodyStyle={{ display: 'flex', flexDirection: 'column', gap: 16 }}
    >
      {factors.length ? (
        <>
          <Row gutter={[12, 12]}>
            {topFactors.map((factor) => (
              <Col xs={24} md={8} key={factor.name}>
                <div
                  style={{
                    borderRadius: 14,
                    padding: 14,
                    background: 'rgba(9, 25, 37, 0.78)',
                    border: '1px solid rgba(255,255,255,0.06)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
                    <Text strong style={{ color: '#f5f8fc' }}>{factor.displayName}</Text>
                    <Tag color={signalColor[factor.signal]}>{factor.signal}</Tag>
                  </div>
                  <Statistic
                    title="Z-Score"
                    value={Number(factor.z_score || 0)}
                    precision={3}
                    valueStyle={{ color: '#f5f8fc', fontSize: 24 }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary">confidence {Number(factor.confidence || 0).toFixed(2)}</Text>
                    {Number(factor?.metadata?.confidence_support_bonus || 0) > 0 ? (
                      <Text type="secondary">
                        {' · '}bonus +{Number(factor.metadata.confidence_support_bonus || 0).toFixed(2)}
                      </Text>
                    ) : null}
                    {Number(factor?.metadata?.confidence_penalty || 0) > 0 ? (
                      <Text type="secondary">
                        {' · '}penalty -{Number(factor.metadata.confidence_penalty || 0).toFixed(2)}
                      </Text>
                    ) : null}
                  </div>
                  {factor.evidenceSummary?.source_count ? (
                    <div style={{ marginTop: 6 }}>
                      <Text type="secondary">
                        证据 {factor.evidenceSummary.source_count} 源 / {factor.evidenceSummary.record_count || 0} 条
                        {factor.evidenceSummary.official_source_count
                          ? ` · 官方源 ${factor.evidenceSummary.official_source_count}`
                          : ''}
                        {factor.evidenceSummary.weighted_evidence_score !== undefined
                          ? ` · 证据分 ${Number(factor.evidenceSummary.weighted_evidence_score || 0).toFixed(2)}`
                          : ''}
                      </Text>
                      {factor.evidenceSummary?.coverage_summary?.coverage_label ? (
                        <Text type="secondary">
                          {' · '}coverage {factor.evidenceSummary.coverage_summary.coverage_label}
                        </Text>
                      ) : null}
                    </div>
                  ) : null}
                  <div style={{ marginTop: 6 }}>
                    <Tag color={factor.trendDelta >= 0 ? 'green' : 'orange'}>
                      ΔZ {factor.trendDelta >= 0 ? '+' : ''}{Number(factor.trendDelta || 0).toFixed(3)}
                    </Tag>
                    {factor.signalChanged ? (
                      <Tag color="magenta">signal shift {factor.previousSignal}→{factor.signal}</Tag>
                    ) : null}
                    {factor.evidenceSummary?.conflict_level && factor.evidenceSummary.conflict_level !== 'none' ? (
                      <Tag color={conflictColor[factor.evidenceSummary.conflict_level] || 'orange'}>
                        conflict {factor.evidenceSummary.conflict_level}
                      </Tag>
                    ) : null}
                    {factor.evidenceSummary?.conflict_trend && factor.evidenceSummary.conflict_level !== 'none' ? (
                      <Tag color={conflictTrendColor[factor.evidenceSummary.conflict_trend] || 'blue'}>
                        {factor.evidenceSummary.conflict_trend}
                      </Tag>
                    ) : null}
                    {factor.evidenceSummary?.coverage_summary?.coverage_label ? (
                      <Tag color={coverageColor[factor.evidenceSummary.coverage_summary.coverage_label] || 'blue'}>
                        coverage {factor.evidenceSummary.coverage_summary.coverage_label}
                      </Tag>
                    ) : null}
                    {factor?.metadata?.blind_spot_warning ? (
                      <Tag color={blindSpotColor[factor.metadata.blind_spot_level] || 'orange'}>
                        blind spot
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.stability_summary?.label ? (
                      <Tag color={stabilityColor[factor.evidenceSummary.stability_summary.label] || 'blue'}>
                        {factor.evidenceSummary.stability_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.metadata?.lag_warning ? (
                      <Tag color={lagColor[factor.metadata.lag_level] || 'orange'}>
                        lagging
                      </Tag>
                    ) : null}
                    {factor?.metadata?.concentration_warning ? (
                      <Tag color={concentrationColor[factor.metadata.concentration_level] || 'orange'}>
                        concentrated
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.source_drift_summary?.label && factor.evidenceSummary.source_drift_summary.label !== 'stable' ? (
                      <Tag color={driftColor[factor.evidenceSummary.source_drift_summary.label] || 'blue'}>
                        drift {factor.evidenceSummary.source_drift_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.source_gap_summary?.label && factor.evidenceSummary.source_gap_summary.label !== 'stable' ? (
                      <Tag color={flowColor[factor.evidenceSummary.source_gap_summary.label] || 'orange'}>
                        flow {factor.evidenceSummary.source_gap_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.cross_confirmation_summary?.label && factor.evidenceSummary.cross_confirmation_summary.label !== 'none' ? (
                      <Tag color={confirmationColor[factor.evidenceSummary.cross_confirmation_summary.label] || 'blue'}>
                        confirm {factor.evidenceSummary.cross_confirmation_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.source_dominance_summary?.label && factor.evidenceSummary.source_dominance_summary.label !== 'stable' ? (
                      <Tag color={dominanceColor[factor.evidenceSummary.source_dominance_summary.label] || 'orange'}>
                        dominance {factor.evidenceSummary.source_dominance_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.consistency_summary?.label && factor.evidenceSummary.consistency_summary.label !== 'unknown' ? (
                      <Tag color={consistencyColor[factor.evidenceSummary.consistency_summary.label] || 'blue'}>
                        consistency {factor.evidenceSummary.consistency_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.reversal_summary?.label && factor.evidenceSummary.reversal_summary.label !== 'stable' ? (
                      <Tag color={reversalColor[factor.evidenceSummary.reversal_summary.label] || 'orange'}>
                        reversal {factor.evidenceSummary.reversal_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.reversal_precursor_summary?.label && factor.evidenceSummary.reversal_precursor_summary.label !== 'none' ? (
                      <Tag color={precursorColor[factor.evidenceSummary.reversal_precursor_summary.label] || 'gold'}>
                        precursor {factor.evidenceSummary.reversal_precursor_summary.label}
                      </Tag>
                    ) : null}
                    {factor?.evidenceSummary?.policy_source_health_summary?.label
                    && factor.evidenceSummary.policy_source_health_summary.label !== 'unknown' ? (
                      <Tag color={policySourceColor[factor.evidenceSummary.policy_source_health_summary.label] || 'blue'}>
                        policy source {factor.evidenceSummary.policy_source_health_summary.label}
                      </Tag>
                    ) : null}
                  </div>
                  {factor.action ? (
                    <Button size="small" style={{ marginTop: 12 }} onClick={() => onNavigate?.(factor.action)}>
                      {factor.action.label}
                    </Button>
                  ) : null}
                  {factor.evidenceSummary?.recent_evidence?.[0] ? (
                    <div style={{ marginTop: 10 }}>
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        <Text type="secondary">
                          最近证据 {factor.evidenceSummary.recent_evidence[0].headline}
                        </Text>
                        {factor.evidenceSummary.recent_evidence[0].excerpt ? (
                          <Text type="secondary">
                            {factor.evidenceSummary.recent_evidence[0].excerpt}
                          </Text>
                        ) : null}
                        {factor.evidenceSummary.recent_evidence[0].canonical_entity ? (
                          <Text type="secondary">
                            实体 {factor.evidenceSummary.recent_evidence[0].canonical_entity}
                          </Text>
                        ) : null}
                        <Text type="secondary">
                          {factor.evidenceSummary.recent_evidence[0].source_tier || 'derived'}
                          {' · '}
                          {factor.evidenceSummary.recent_evidence[0].freshness_label || 'stale'}
                        </Text>
                      </Space>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.top_entities?.length ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        重点实体 {(factor.evidenceSummary.top_entities || []).map((item) => item.entity).join('，')}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.coverage_summary?.missing_categories?.length ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        缺失维度 {factor.evidenceSummary.coverage_summary.missing_categories.join('，')}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.stability_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        稳定性 {factor.evidenceSummary.stability_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.lag_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        时效性 {factor.evidenceSummary.lag_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.concentration_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        集中度 {factor.evidenceSummary.concentration_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.source_drift_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        来源漂移 {factor.evidenceSummary.source_drift_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.source_gap_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        更新节奏 {factor.evidenceSummary.source_gap_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.cross_confirmation_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        跨源确认 {factor.evidenceSummary.cross_confirmation_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.source_dominance_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        主导权 {factor.evidenceSummary.source_dominance_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.consistency_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        一致度 {factor.evidenceSummary.consistency_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.reversal_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        反转 {factor.evidenceSummary.reversal_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.reversal_precursor_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        前兆 {factor.evidenceSummary.reversal_precursor_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.policy_source_health_summary?.reason ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary">
                        政策源 {factor.evidenceSummary.policy_source_health_summary.reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.blind_spot_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        输入盲区 {factor.metadata.blind_spot_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.lag_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        证据滞后 {factor.metadata.lag_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.concentration_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        证据集中 {factor.metadata.concentration_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.source_drift_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        来源退化 {factor.metadata.source_drift_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.source_gap_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        证据断流 {factor.metadata.source_gap_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.policy_source_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        政策源退化 {factor.metadata.policy_source_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.source_dominance_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        主导权切换 {factor.metadata.source_dominance_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.consistency_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        强弱分歧 {factor.metadata.consistency_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.reversal_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        方向反转 {factor.metadata.reversal_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.reversal_precursor_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        反转前兆 {factor.metadata.reversal_precursor_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor?.metadata?.stability_warning ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        锚点不稳 {factor.metadata.stability_reason}
                      </Text>
                    </div>
                  ) : null}
                  {factor.evidenceSummary?.conflicts?.[0] ? (
                    <div style={{ marginTop: 8 }}>
                      <Text type="warning">
                        证据分裂 {factor.evidenceSummary.conflicts[0].summary}
                      </Text>
                      {factor.evidenceSummary.conflicts[0].source_pattern_label ? (
                        <div>
                          <Text type="secondary">
                            {factor.evidenceSummary.conflicts[0].source_pattern_label}
                          </Text>
                        </div>
                      ) : null}
                      {factor.evidenceSummary.conflict_trend_reason ? (
                        <div>
                          <Text type="secondary">
                            {factor.evidenceSummary.conflict_trend_reason}
                          </Text>
                        </div>
                      ) : null}
                      {factor?.metadata?.confidence_penalty_reason && Number(factor?.metadata?.confidence_penalty || 0) > 0 ? (
                        <div>
                          <Text type="secondary">
                            置信度折扣 {factor.metadata.confidence_penalty_reason}
                          </Text>
                        </div>
                      ) : null}
                      {factor?.metadata?.confidence_support_reason && Number(factor?.metadata?.confidence_support_bonus || 0) > 0 ? (
                        <div>
                          <Text type="secondary">
                            置信度加成 {factor.metadata.confidence_support_reason}
                          </Text>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </Col>
            ))}
          </Row>

          <Table
            size="small"
            pagination={false}
            dataSource={factors.map((factor) => ({ key: factor.name, ...factor }))}
            locale={{ emptyText: <Empty description="暂无因子" /> }}
            columns={[
              {
                title: '因子',
                dataIndex: 'displayName',
                key: 'displayName',
                render: (value) => <Text strong>{value}</Text>,
              },
              {
                title: '值',
                dataIndex: 'value',
                key: 'value',
                render: (value) => Number(value || 0).toFixed(4),
              },
              {
                title: 'Z',
                dataIndex: 'z_score',
                key: 'z_score',
                render: (value) => Number(value || 0).toFixed(3),
              },
              {
                title: 'ΔZ',
                dataIndex: 'trendDelta',
                key: 'trendDelta',
                render: (value, record) => (
                  <Space size={6}>
                    <Text>{Number(value || 0) >= 0 ? '+' : ''}{Number(value || 0).toFixed(3)}</Text>
                    {record.signalChanged ? <Tag color="magenta">shift</Tag> : null}
                  </Space>
                ),
              },
              {
                title: '置信度',
                dataIndex: 'confidence',
                key: 'confidence',
                render: (value) => Number(value || 0).toFixed(2),
              },
              {
                title: '信号',
                dataIndex: 'signal',
                key: 'signal',
                render: (value) => <Tag color={signalColor[value]}>{value}</Tag>,
              },
              {
                title: '证据',
                dataIndex: 'evidenceSummary',
                key: 'evidenceSummary',
                render: (value) => (
                  <Space size={6}>
                    <Text>
                      {Number(value?.source_count || 0)} 源 / {Number(value?.record_count || 0)} 条
                    </Text>
                    {value?.conflict_level && value.conflict_level !== 'none' ? (
                      <Tag color={conflictColor[value.conflict_level] || 'orange'}>
                        {value.conflict_level}
                      </Tag>
                    ) : null}
                    {value?.conflict_trend && value.conflict_level !== 'none' ? (
                      <Tag color={conflictTrendColor[value.conflict_trend] || 'blue'}>
                        {value.conflict_trend}
                      </Tag>
                    ) : null}
                    {value?.coverage_summary?.coverage_label ? (
                      <Tag color={coverageColor[value.coverage_summary.coverage_label] || 'blue'}>
                        {value.coverage_summary.coverage_label}
                      </Tag>
                    ) : null}
                    {value?.stability_summary?.label ? (
                      <Tag color={stabilityColor[value.stability_summary.label] || 'blue'}>
                        {value.stability_summary.label}
                      </Tag>
                    ) : null}
                    {value?.lag_summary?.level && value.lag_summary.level !== 'none' ? (
                      <Tag color={lagColor[value.lag_summary.level] || 'orange'}>
                        {value.lag_summary.level}
                      </Tag>
                    ) : null}
                    {value?.concentration_summary?.label && value.concentration_summary.label !== 'low' ? (
                      <Tag color={concentrationColor[value.concentration_summary.label] || 'orange'}>
                        {value.concentration_summary.label}
                      </Tag>
                    ) : null}
                    {value?.source_drift_summary?.label && value.source_drift_summary.label !== 'stable' ? (
                      <Tag color={driftColor[value.source_drift_summary.label] || 'blue'}>
                        {value.source_drift_summary.label}
                      </Tag>
                    ) : null}
                    {value?.source_gap_summary?.label && value.source_gap_summary.label !== 'stable' ? (
                      <Tag color={flowColor[value.source_gap_summary.label] || 'orange'}>
                        {value.source_gap_summary.label}
                      </Tag>
                    ) : null}
                    {value?.cross_confirmation_summary?.label && value.cross_confirmation_summary.label !== 'none' ? (
                      <Tag color={confirmationColor[value.cross_confirmation_summary.label] || 'blue'}>
                        {value.cross_confirmation_summary.label}
                      </Tag>
                    ) : null}
                    {value?.source_dominance_summary?.label && value.source_dominance_summary.label !== 'stable' ? (
                      <Tag color={dominanceColor[value.source_dominance_summary.label] || 'orange'}>
                        {value.source_dominance_summary.label}
                      </Tag>
                    ) : null}
                    {value?.consistency_summary?.label && value.consistency_summary.label !== 'unknown' ? (
                      <Tag color={consistencyColor[value.consistency_summary.label] || 'blue'}>
                        {value.consistency_summary.label}
                      </Tag>
                    ) : null}
                    {value?.reversal_summary?.label && value.reversal_summary.label !== 'stable' ? (
                      <Tag color={reversalColor[value.reversal_summary.label] || 'orange'}>
                        {value.reversal_summary.label}
                      </Tag>
                    ) : null}
                    {value?.reversal_precursor_summary?.label && value.reversal_precursor_summary.label !== 'none' ? (
                      <Tag color={precursorColor[value.reversal_precursor_summary.label] || 'gold'}>
                        {value.reversal_precursor_summary.label}
                      </Tag>
                    ) : null}
                  </Space>
                ),
              },
            ]}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            {resonanceSummary?.label ? (
              <Text type="secondary">
                <Tag color={resonanceColor[resonanceSummary.label] || 'blue'}>
                  resonance {resonanceSummary.label}
                </Tag>
                {resonanceSummary.reason}
              </Text>
            ) : null}
            {['positive_cluster', 'negative_cluster', 'weakening', 'precursor', 'reversed_factors'].map((key) =>
              resonanceSummary?.[key]?.length ? (
                <Text key={key} type="secondary">
                  {clusterLabels[key]} {resonanceSummary[key].join('，')}
                </Text>
              ) : null
            )}
            <Text type="secondary">healthy {providerHealth.healthy_providers || 0}</Text>
            <Text type="secondary">degraded {providerHealth.degraded_providers || 0}</Text>
            <Text type="secondary">error {providerHealth.error_providers || 0}</Text>
            <Text type="secondary">
              macro Δ {Number(macroTrend.macro_score_delta || 0) >= 0 ? '+' : ''}{Number(macroTrend.macro_score_delta || 0).toFixed(3)}
            </Text>
            {Number(model?.confidenceAdjustment?.penalized_factor_count || 0) > 0 ? (
              <Text type="secondary">
                confidence penalty {Number(model.confidenceAdjustment.penalized_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.boosted_factor_count || 0) > 0 ? (
              <Text type="secondary">
                confidence bonus {Number(model.confidenceAdjustment.boosted_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.blind_spot_factor_count || 0) > 0 ? (
              <Text type="secondary">
                blind spot {Number(model.confidenceAdjustment.blind_spot_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.unstable_factor_count || 0) > 0 ? (
              <Text type="secondary">
                unstable {Number(model.confidenceAdjustment.unstable_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.lagging_factor_count || 0) > 0 ? (
              <Text type="secondary">
                lagging {Number(model.confidenceAdjustment.lagging_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.concentrated_factor_count || 0) > 0 ? (
              <Text type="secondary">
                concentrated {Number(model.confidenceAdjustment.concentrated_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.drifting_factor_count || 0) > 0 ? (
              <Text type="secondary">
                drifting {Number(model.confidenceAdjustment.drifting_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.broken_flow_factor_count || 0) > 0 ? (
              <Text type="secondary">
                broken flow {Number(model.confidenceAdjustment.broken_flow_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.confirmed_factor_count || 0) > 0 ? (
              <Text type="secondary">
                confirmed {Number(model.confidenceAdjustment.confirmed_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.dominance_shift_factor_count || 0) > 0 ? (
              <Text type="secondary">
                dominance shift {Number(model.confidenceAdjustment.dominance_shift_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.inconsistent_factor_count || 0) > 0 ? (
              <Text type="secondary">
                inconsistent {Number(model.confidenceAdjustment.inconsistent_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.reversing_factor_count || 0) > 0 ? (
              <Text type="secondary">
                reversing {Number(model.confidenceAdjustment.reversing_factor_count || 0)} 因子
              </Text>
            ) : null}
            {Number(model?.confidenceAdjustment?.precursor_factor_count || 0) > 0 ? (
              <Text type="secondary">
                precursor {Number(model.confidenceAdjustment.precursor_factor_count || 0)} 因子
              </Text>
            ) : null}
            <Text type="secondary">
              evidence {overallEvidence.source_count || 0} 源 / {overallEvidence.record_count || 0} 条
              {overallEvidence.official_source_count ? ` · 官方源 ${overallEvidence.official_source_count}` : ''}
              {overallEvidence.freshness_label ? ` · ${overallEvidence.freshness_label}` : ''}
              {overallEvidence.conflict_level && overallEvidence.conflict_level !== 'none'
                ? ` · conflict ${overallEvidence.conflict_level}`
                : ''}
              {overallEvidence.conflict_trend && overallEvidence.conflict_level !== 'none'
                ? ` · ${overallEvidence.conflict_trend}`
                : ''}
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
