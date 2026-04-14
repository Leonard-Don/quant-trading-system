import { render, screen } from '@testing-library/react';

import { PeopleLayerCard } from '../components/pricing/PricingInsightCards';

describe('Pricing governance overlay card', () => {
  it('renders governance discount evidence, policy execution context, and source governance', () => {
    render(
      <PeopleLayerCard
        data={{
          stance: 'fragile',
          risk_level: 'high',
          confidence: 0.76,
          executive_profile: {
            technical_authority_score: 0.32,
            capital_markets_pressure: 0.71,
            leadership_balance: '商业/财务主导',
            average_tenure_years: 4.6,
          },
          insider_flow: {
            label: '内部人减持偏谨慎',
            net_action: 'selling',
            transaction_count: 4,
            summary: '近端内部人交易继续偏减持。',
          },
          hiring_signal: {
            signal: 'bearish',
            dilution_ratio: 1.67,
            tech_ratio: 0.28,
            alert_message: '技术组织继续被商业 KPI 稀释。',
          },
        }}
        overlay={{
          label: '治理折价',
          governance_discount_pct: 8.6,
          confidence: 0.72,
          source_mode_summary: {
            label: 'fallback-heavy',
            coverage: 8,
            official_share: 0.25,
            fallback_share: 0.5,
          },
          executive_evidence: {
            leadership_balance: '商业/财务主导',
            technical_authority_score: 0.32,
            capital_markets_pressure: 0.71,
            average_tenure_years: 4.6,
          },
          insider_evidence: {
            label: '内部人减持偏谨慎',
            net_action: 'selling',
            transaction_count: 4,
            summary: '近端内部人交易继续偏减持。',
          },
          hiring_evidence: {
            signal: 'bearish',
            dilution_ratio: 1.67,
            tech_ratio: 0.28,
            alert_message: '技术组织继续被商业 KPI 稀释。',
          },
          policy_execution_context: {
            label: 'chaotic',
            summary: '部门执行混乱继续升温。',
            top_department: '发改委',
            reversal_count: 2,
            execution_status: 'lagging',
            lag_days: 14,
          },
          summary: '执行/治理折价主导当前定价，需要把组织质量与政策执行噪音一起纳入估值判断。',
        }}
      />,
    );

    expect(screen.getByText('人的维度 / 治理折扣')).toBeTruthy();
    expect(screen.getByText('治理折价 8.6%')).toBeTruthy();
    expect(screen.getByText('治理置信度 0.72')).toBeTruthy();
    expect(screen.getByText('来源 回退源偏多')).toBeTruthy();
    expect(screen.getByText('政策执行上下文')).toBeTruthy();
    expect(screen.getByText('发改委')).toBeTruthy();
    expect(screen.getAllByText('内部人减持偏谨慎').length).toBeGreaterThan(0);
    expect(screen.getByText('稀释度 1.67')).toBeTruthy();
  });
});
