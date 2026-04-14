import React from 'react';
import { Empty, Space, Table, Tag, Typography } from 'antd';
import {
  signalColor, conflictColor, conflictTrendColor, coverageColor,
  stabilityColor, lagColor, concentrationColor, driftColor, flowColor,
  confirmationColor, dominanceColor, consistencyColor, reversalColor,
  precursorColor,
} from './macroFactorColors';

const { Text } = Typography;

const EVIDENCE_TAG_SPECS = [
  { key: 'coverage_summary.coverage_label', colorMap: coverageColor },
  { key: 'stability_summary.label', colorMap: stabilityColor },
  { key: 'lag_summary.level', colorMap: lagColor, hide: 'none' },
  { key: 'concentration_summary.label', colorMap: concentrationColor, hide: 'low' },
  { key: 'source_drift_summary.label', colorMap: driftColor, hide: 'stable' },
  { key: 'source_gap_summary.label', colorMap: flowColor, hide: 'stable' },
  { key: 'cross_confirmation_summary.label', colorMap: confirmationColor, hide: 'none' },
  { key: 'source_dominance_summary.label', colorMap: dominanceColor, hide: 'stable' },
  { key: 'consistency_summary.label', colorMap: consistencyColor, hide: 'unknown' },
  { key: 'reversal_summary.label', colorMap: reversalColor, hide: 'stable' },
  { key: 'reversal_precursor_summary.label', colorMap: precursorColor, hide: 'none' },
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

const renderEvidenceTags = (value) => (
  <Space size={6}>
    <Text>{Number(value?.source_count || 0)} 源 / {Number(value?.record_count || 0)} 条</Text>
    {value?.conflict_level && value.conflict_level !== 'none' ? (
      <Tag color={conflictColor[value.conflict_level] || 'orange'}>{value.conflict_level}</Tag>
    ) : null}
    {value?.conflict_trend && value.conflict_level !== 'none' ? (
      <Tag color={conflictTrendColor[value.conflict_trend] || 'blue'}>{value.conflict_trend}</Tag>
    ) : null}
    {EVIDENCE_TAG_SPECS.map(({ key, colorMap, hide }) => {
      const tagValue = getNestedValue(value, key);
      if (!tagValue || tagValue === hide) return null;
      return <Tag key={key} color={colorMap[tagValue] || 'blue'}>{tagValue}</Tag>;
    })}
  </Space>
);

const columns = [
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
    render: renderEvidenceTags,
  },
];

function FactorTable({ factors }) {
  return (
    <Table
      size="small"
      pagination={false}
      dataSource={factors.map((factor) => ({ key: factor.name, ...factor }))}
      locale={{ emptyText: <Empty description="暂无因子" /> }}
      columns={columns}
    />
  );
}

export default FactorTable;
