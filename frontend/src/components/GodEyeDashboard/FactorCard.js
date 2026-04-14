import React from 'react';
import { Button, Space, Statistic, Tag, Typography } from 'antd';
import {
  signalColor, conflictColor, conflictTrendColor, coverageColor,
  blindSpotColor, stabilityColor, lagColor, concentrationColor,
  driftColor, flowColor, confirmationColor, dominanceColor,
  consistencyColor, reversalColor, precursorColor, policySourceColor,
} from './macroFactorColors';

const { Text } = Typography;

const EVIDENCE_TAG_SPECS = [
  { path: 'coverage_summary.coverage_label', colorMap: coverageColor, prefix: 'coverage' },
  { path: 'stability_summary.label', colorMap: stabilityColor },
  { path: 'source_drift_summary.label', colorMap: driftColor, prefix: 'drift', hide: 'stable' },
  { path: 'source_gap_summary.label', colorMap: flowColor, prefix: 'flow', hide: 'stable' },
  { path: 'cross_confirmation_summary.label', colorMap: confirmationColor, prefix: 'confirm', hide: 'none' },
  { path: 'source_dominance_summary.label', colorMap: dominanceColor, prefix: 'dominance', hide: 'stable' },
  { path: 'consistency_summary.label', colorMap: consistencyColor, prefix: 'consistency', hide: 'unknown' },
  { path: 'reversal_summary.label', colorMap: reversalColor, prefix: 'reversal', hide: 'stable' },
  { path: 'reversal_precursor_summary.label', colorMap: precursorColor, prefix: 'precursor', hide: 'none' },
  { path: 'policy_source_health_summary.label', colorMap: policySourceColor, prefix: 'policy source', hide: 'unknown' },
];

const EVIDENCE_DETAIL_SPECS = [
  { path: 'stability_summary.reason', label: '稳定性' },
  { path: 'lag_summary.reason', label: '时效性' },
  { path: 'concentration_summary.reason', label: '集中度' },
  { path: 'source_drift_summary.reason', label: '来源漂移' },
  { path: 'source_gap_summary.reason', label: '更新节奏' },
  { path: 'cross_confirmation_summary.reason', label: '跨源确认' },
  { path: 'source_dominance_summary.reason', label: '主导权' },
  { path: 'consistency_summary.reason', label: '一致度' },
  { path: 'reversal_summary.reason', label: '反转' },
  { path: 'reversal_precursor_summary.reason', label: '前兆' },
  { path: 'policy_source_health_summary.reason', label: '政策源' },
];

const WARNING_SPECS = [
  { flag: 'blind_spot_warning', reason: 'blind_spot_reason', label: '输入盲区' },
  { flag: 'lag_warning', reason: 'lag_reason', label: '证据滞后' },
  { flag: 'concentration_warning', reason: 'concentration_reason', label: '证据集中' },
  { flag: 'source_drift_warning', reason: 'source_drift_reason', label: '来源退化' },
  { flag: 'source_gap_warning', reason: 'source_gap_reason', label: '证据断流' },
  { flag: 'policy_source_warning', reason: 'policy_source_reason', label: '政策源退化' },
  { flag: 'source_dominance_warning', reason: 'source_dominance_reason', label: '主导权切换' },
  { flag: 'consistency_warning', reason: 'consistency_reason', label: '强弱分歧' },
  { flag: 'reversal_warning', reason: 'reversal_reason', label: '方向反转' },
  { flag: 'reversal_precursor_warning', reason: 'reversal_precursor_reason', label: '反转前兆' },
  { flag: 'stability_warning', reason: 'stability_reason', label: '锚点不稳' },
];

const getNestedValue = (obj, path) => {
  const keys = path.split('.');
  let current = obj;
  for (const key of keys) {
    if (current == null) return undefined;
    current = current[key];
  }
  return current;
};

function FactorCard({ factor, onNavigate }) {
  const ev = factor.evidenceSummary || {};
  const meta = factor?.metadata || {};

  return (
    <div style={{ borderRadius: 14, padding: 14, background: 'rgba(9, 25, 37, 0.78)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
        <Text strong style={{ color: '#f5f8fc' }}>{factor.displayName}</Text>
        <Tag color={signalColor[factor.signal]}>{factor.signal}</Tag>
      </div>

      <Statistic title="Z-Score" value={Number(factor.z_score || 0)} precision={3} valueStyle={{ color: '#f5f8fc', fontSize: 24 }} />

      <div style={{ marginTop: 8 }}>
        <Text type="secondary">confidence {Number(factor.confidence || 0).toFixed(2)}</Text>
        {Number(meta.confidence_support_bonus || 0) > 0 ? (
          <Text type="secondary"> · bonus +{Number(meta.confidence_support_bonus || 0).toFixed(2)}</Text>
        ) : null}
        {Number(meta.confidence_penalty || 0) > 0 ? (
          <Text type="secondary"> · penalty -{Number(meta.confidence_penalty || 0).toFixed(2)}</Text>
        ) : null}
      </div>

      {ev.source_count ? (
        <div style={{ marginTop: 6 }}>
          <Text type="secondary">
            证据 {ev.source_count} 源 / {ev.record_count || 0} 条
            {ev.official_source_count ? ` · 官方源 ${ev.official_source_count}` : ''}
            {ev.weighted_evidence_score !== undefined ? ` · 证据分 ${Number(ev.weighted_evidence_score || 0).toFixed(2)}` : ''}
          </Text>
          {ev.coverage_summary?.coverage_label ? (
            <Text type="secondary"> · coverage {ev.coverage_summary.coverage_label}</Text>
          ) : null}
        </div>
      ) : null}

      {/* Signal tags */}
      <div style={{ marginTop: 6 }}>
        <Tag color={factor.trendDelta >= 0 ? 'green' : 'orange'}>
          ΔZ {factor.trendDelta >= 0 ? '+' : ''}{Number(factor.trendDelta || 0).toFixed(3)}
        </Tag>
        {factor.signalChanged ? <Tag color="magenta">signal shift {factor.previousSignal}→{factor.signal}</Tag> : null}
        {ev.conflict_level && ev.conflict_level !== 'none' ? (
          <Tag color={conflictColor[ev.conflict_level] || 'orange'}>conflict {ev.conflict_level}</Tag>
        ) : null}
        {ev.conflict_trend && ev.conflict_level !== 'none' ? (
          <Tag color={conflictTrendColor[ev.conflict_trend] || 'blue'}>{ev.conflict_trend}</Tag>
        ) : null}
        {meta.blind_spot_warning ? (
          <Tag color={blindSpotColor[meta.blind_spot_level] || 'orange'}>blind spot</Tag>
        ) : null}
        {meta.lag_warning ? <Tag color={lagColor[meta.lag_level] || 'orange'}>lagging</Tag> : null}
        {meta.concentration_warning ? (
          <Tag color={concentrationColor[meta.concentration_level] || 'orange'}>concentrated</Tag>
        ) : null}
        {EVIDENCE_TAG_SPECS.map(({ path, colorMap, prefix, hide }) => {
          const value = getNestedValue(ev, path);
          if (!value || value === hide) return null;
          return <Tag key={path} color={colorMap[value] || 'blue'}>{prefix ? `${prefix} ` : ''}{value}</Tag>;
        })}
      </div>

      {factor.action ? (
        <Button size="small" style={{ marginTop: 12 }} onClick={() => onNavigate?.(factor.action)}>
          {factor.action.label}
        </Button>
      ) : null}

      {/* Recent evidence */}
      {ev.recent_evidence?.[0] ? (
        <div style={{ marginTop: 10 }}>
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            <Text type="secondary">最近证据 {ev.recent_evidence[0].headline}</Text>
            {ev.recent_evidence[0].excerpt ? <Text type="secondary">{ev.recent_evidence[0].excerpt}</Text> : null}
            {ev.recent_evidence[0].canonical_entity ? <Text type="secondary">实体 {ev.recent_evidence[0].canonical_entity}</Text> : null}
            <Text type="secondary">{ev.recent_evidence[0].source_tier || 'derived'} · {ev.recent_evidence[0].freshness_label || 'stale'}</Text>
          </Space>
        </div>
      ) : null}

      {ev.top_entities?.length ? (
        <div style={{ marginTop: 8 }}>
          <Text type="secondary">重点实体 {(ev.top_entities || []).map((item) => item.entity).join('，')}</Text>
        </div>
      ) : null}

      {ev.coverage_summary?.missing_categories?.length ? (
        <div style={{ marginTop: 8 }}>
          <Text type="secondary">缺失维度 {ev.coverage_summary.missing_categories.join('，')}</Text>
        </div>
      ) : null}

      {/* Evidence detail lines */}
      {EVIDENCE_DETAIL_SPECS.map(({ path, label }) => {
        const value = getNestedValue(ev, path);
        if (!value) return null;
        return (
          <div key={path} style={{ marginTop: 8 }}>
            <Text type="secondary">{label} {value}</Text>
          </div>
        );
      })}

      {/* Warning lines */}
      {WARNING_SPECS.map(({ flag, reason, label }) => {
        if (!meta[flag]) return null;
        return (
          <div key={flag} style={{ marginTop: 8 }}>
            <Text type="warning">{label} {meta[reason]}</Text>
          </div>
        );
      })}

      {/* Conflict details */}
      {ev.conflicts?.[0] ? (
        <div style={{ marginTop: 8 }}>
          <Text type="warning">证据分裂 {ev.conflicts[0].summary}</Text>
          {ev.conflicts[0].source_pattern_label ? (
            <div><Text type="secondary">{ev.conflicts[0].source_pattern_label}</Text></div>
          ) : null}
          {ev.conflict_trend_reason ? (
            <div><Text type="secondary">{ev.conflict_trend_reason}</Text></div>
          ) : null}
          {meta.confidence_penalty_reason && Number(meta.confidence_penalty || 0) > 0 ? (
            <div><Text type="secondary">置信度折扣 {meta.confidence_penalty_reason}</Text></div>
          ) : null}
          {meta.confidence_support_reason && Number(meta.confidence_support_bonus || 0) > 0 ? (
            <div><Text type="secondary">置信度加成 {meta.confidence_support_reason}</Text></div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default FactorCard;
