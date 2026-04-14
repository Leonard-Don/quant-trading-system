import React from 'react';
import { Space, Tag, Typography } from 'antd';
import { peopleLayerColor, departmentChaosColor, reliabilityColor } from './macroFactorColors';

const { Text } = Typography;

function PeopleLayerPanel({ peopleLayerSummary }) {
  if (!peopleLayerSummary?.label) return null;

  return (
    <div style={{ borderRadius: 14, padding: 14, background: 'rgba(32, 17, 21, 0.62)', border: '1px solid rgba(255,255,255,0.08)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <Space wrap>
          <Tag color={peopleLayerColor[peopleLayerSummary.label] || 'blue'}>people {peopleLayerSummary.label}</Tag>
          <Text type="secondary">fragility {Number(peopleLayerSummary.avg_fragility_score || 0).toFixed(2)}</Text>
          <Text type="secondary">quality {Number(peopleLayerSummary.avg_quality_score || 0).toFixed(2)}</Text>
          <Text type="secondary">高风险 {Number(peopleLayerSummary.fragile_company_count || 0)}</Text>
        </Space>
        {peopleLayerSummary?.watchlist?.length ? (
          <Text type="secondary">
            重点观察 {(peopleLayerSummary.watchlist || []).slice(0, 3).map((item) => item.symbol).join('、')}
          </Text>
        ) : null}
      </div>
      {peopleLayerSummary.summary ? (
        <div style={{ marginTop: 8 }}><Text style={{ color: '#f5f8fc' }}>{peopleLayerSummary.summary}</Text></div>
      ) : null}
      {peopleLayerSummary?.fragile_companies?.length ? (
        <div style={{ marginTop: 8 }}>
          <Space wrap size={6}>
            {(peopleLayerSummary.fragile_companies || []).map((item) => (
              <Tag key={item.symbol} color="red">{`${item.symbol} fragility ${Number(item.people_fragility_score || 0).toFixed(2)}`}</Tag>
            ))}
          </Space>
        </div>
      ) : null}
    </div>
  );
}

function DepartmentChaosPanel({ departmentChaosSummary }) {
  if (!departmentChaosSummary?.label) return null;

  return (
    <div style={{ borderRadius: 14, padding: 14, background: 'rgba(34, 20, 12, 0.68)', border: '1px solid rgba(255,255,255,0.08)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <Space wrap>
          <Tag color={departmentChaosColor[departmentChaosSummary.label] || 'blue'}>department {departmentChaosSummary.label}</Tag>
          <Text type="secondary">chaos {Number(departmentChaosSummary.avg_chaos_score || 0).toFixed(2)}</Text>
          <Text type="secondary">主体 {Number(departmentChaosSummary.department_count || 0)}</Text>
          <Text type="secondary">高混乱 {Number(departmentChaosSummary.chaotic_department_count || 0)}</Text>
        </Space>
        {departmentChaosSummary?.top_departments?.length ? (
          <Text type="secondary">
            重点部门 {(departmentChaosSummary.top_departments || []).slice(0, 3).map((item) => item.department_label || item.department).join('、')}
          </Text>
        ) : null}
      </div>
      {departmentChaosSummary.summary ? (
        <div style={{ marginTop: 8 }}><Text style={{ color: '#f5f8fc' }}>{departmentChaosSummary.summary}</Text></div>
      ) : null}
      {departmentChaosSummary?.top_departments?.length ? (
        <div style={{ marginTop: 8 }}>
          <Space wrap size={6}>
            {(departmentChaosSummary.top_departments || []).slice(0, 4).map((item) => (
              <Tag key={item.department} color={departmentChaosColor[item.label] || 'blue'}>
                {item.department_label || item.department} {Number(item.chaos_score || 0).toFixed(2)}
              </Tag>
            ))}
          </Space>
        </div>
      ) : null}
    </div>
  );
}

function InputReliabilityPanel({ inputReliabilitySummary }) {
  if (!inputReliabilitySummary?.label) return null;

  return (
    <div style={{ borderRadius: 14, padding: 14, background: 'rgba(11, 30, 44, 0.72)', border: '1px solid rgba(255,255,255,0.08)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <Space wrap>
          <Tag color={reliabilityColor[inputReliabilitySummary.label] || 'blue'}>input {inputReliabilitySummary.label}</Tag>
          <Text type="secondary">score {Number(inputReliabilitySummary.score || 0).toFixed(2)}</Text>
          <Text type="secondary">risk hits {Number(inputReliabilitySummary.issue_factor_hits || 0)}</Text>
          <Text type="secondary">support hits {Number(inputReliabilitySummary.support_factor_hits || 0)}</Text>
        </Space>
        {inputReliabilitySummary?.dominant_issue_labels?.length ? (
          <Text type="secondary">主要风险 {inputReliabilitySummary.dominant_issue_labels.join('，')}</Text>
        ) : null}
      </div>
      {inputReliabilitySummary.lead ? (
        <div style={{ marginTop: 8 }}><Text style={{ color: '#f5f8fc' }}>{inputReliabilitySummary.lead}</Text></div>
      ) : null}
      {inputReliabilitySummary.posture ? (
        <div style={{ marginTop: 6 }}><Text type="secondary">{inputReliabilitySummary.posture}</Text></div>
      ) : null}
      {inputReliabilitySummary.reason ? (
        <div style={{ marginTop: 6 }}><Text type="secondary">{inputReliabilitySummary.reason}</Text></div>
      ) : null}
    </div>
  );
}

export { PeopleLayerPanel, DepartmentChaosPanel, InputReliabilityPanel };
