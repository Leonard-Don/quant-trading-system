import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';

jest.mock('antd', () => {
  const React = require('react');
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
  };
});

import {
  buildPricingPlaybook,
  buildPricingWorkbenchPayload,
} from '../components/research-playbook/playbookViewModels';
import { buildSnapshotComparison } from '../components/research-workbench/snapshotCompare';
import ResearchPlaybook from '../components/research-playbook/ResearchPlaybook';
import { getDriverImpactMeta, getPriceSourceLabel, getSignalStrengthMeta } from '../utils/pricingResearch';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
});

describe('pricing playbook percent formatting', () => {
  const pricingResult = {
    symbol: 'AAPL',
    gap_analysis: {
      current_price: 252.89,
      fair_value_mid: 155.49,
      gap_pct: 62.6,
      severity: 'extreme',
      severity_label: '极端偏离',
      direction: '溢价(高估)',
    },
    valuation: {
      current_price_source: 'historical_close',
      fair_value: {
        mid: 155.49,
        low: 132.17,
        high: 178.81,
        method: 'DCF + 可比估值加权',
        range_basis: 'dcf_scenarios_and_multiples',
      },
      dcf: {
        scenarios: [
          { name: 'bear', label: '悲观', intrinsic_value: 132.17, premium_discount: 20.4, assumptions: { wacc: 0.097, initial_growth: 0.08 } },
          { name: 'base', label: '基准', intrinsic_value: 155.49, premium_discount: 9.7, assumptions: { wacc: 0.082, initial_growth: 0.12 } },
          { name: 'bull', label: '乐观', intrinsic_value: 178.81, premium_discount: -1.5, assumptions: { wacc: 0.072, initial_growth: 0.16 } },
        ],
      },
    },
    factor_model: {
      period: '2y',
      data_points: 132,
      capm: { alpha_pct: 4.8, beta: 1.12, r_squared: 0.41 },
      fama_french: { alpha_pct: 3.7, r_squared: 0.46 },
    },
    deviation_drivers: {
      primary_driver: {
        factor: 'P/B 倍数法溢价',
        description: '当前 P/B 偏高',
        signal_strength: 3.33,
        ranking_reason: '相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源',
      },
      drivers: [{
        factor: 'P/B 倍数法溢价',
        description: '当前 P/B 偏高',
        signal_strength: 3.33,
        ranking_reason: '相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源',
      }],
    },
    implications: {
      primary_view: '高估',
      confidence: 'high',
      risk_level: 'high',
      factor_alignment: {
        label: '同向',
        status: 'aligned',
        summary: '因子信号与高估判断同向，证据互相印证',
      },
      insights: ['存在显著高估'],
    },
  };

  it('uses percent points in pricing playbook copy', () => {
    const playbook = buildPricingPlaybook({ symbol: 'AAPL', source: 'manual' }, pricingResult);

    expect(playbook.thesis).toContain('+62.6%');
    expect(playbook.thesis).not.toContain('6260.0%');
    expect(playbook.tasks[0].description).toContain('+62.6%');
  });

  it('persists corrected percent copy into the pricing workbench snapshot', () => {
    const playbook = buildPricingPlaybook({ symbol: 'AAPL', source: 'manual' }, pricingResult);
    const payload = buildPricingWorkbenchPayload({ symbol: 'AAPL', source: 'manual', period: '2y' }, pricingResult, playbook);

    expect(payload.snapshot.summary).toContain('+62.6%');
    expect(payload.snapshot.summary).not.toContain('6260.0%');
    expect(payload.context.period).toBe('2y');
    expect(payload.snapshot.payload.period).toBe('2y');
    expect(payload.snapshot.payload.current_price_source).toBe('historical_close');
    expect(payload.snapshot.payload.dcf_scenarios).toEqual([
      {
        name: 'bear',
        label: '悲观',
        intrinsic_value: 132.17,
        premium_discount: 20.4,
        assumptions: {
          wacc: 0.097,
          initial_growth: 0.08,
          terminal_growth: null,
          fcf_margin: null,
        },
      },
      {
        name: 'base',
        label: '基准',
        intrinsic_value: 155.49,
        premium_discount: 9.7,
        assumptions: {
          wacc: 0.082,
          initial_growth: 0.12,
          terminal_growth: null,
          fcf_margin: null,
        },
      },
      {
        name: 'bull',
        label: '乐观',
        intrinsic_value: 178.81,
        premium_discount: -1.5,
        assumptions: {
          wacc: 0.072,
          initial_growth: 0.16,
          terminal_growth: null,
          fcf_margin: null,
        },
      },
    ]);
    expect(payload.snapshot.payload.factor_model).toEqual({
      period: '2y',
      data_points: 132,
      capm_alpha_pct: 4.8,
      capm_beta: 1.12,
      capm_r_squared: 0.41,
      ff3_alpha_pct: 3.7,
      ff3_r_squared: 0.46,
      ff5_alpha_pct: null,
      ff5_profitability: null,
      ff5_investment: null,
    });
    expect(payload.snapshot.payload.primary_driver.factor).toBe('P/B 倍数法溢价');
    expect(payload.snapshot.payload.primary_driver.signal_strength).toBe(3.33);
    expect(payload.snapshot.payload.primary_driver.ranking_reason).toBe('相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源');
  });

  it('formats pricing snapshot comparison gap as percent points', () => {
    const comparison = buildSnapshotComparison(
      'pricing',
      {
        payload: {
          fair_value: { mid: 155.49, low: 132.17, high: 178.81 },
          dcf_scenarios: [
            { name: 'bear', intrinsic_value: 132.17 },
            { name: 'base', intrinsic_value: 155.49 },
            { name: 'bull', intrinsic_value: 178.81 },
          ],
          gap_analysis: { gap_pct: 62.6 },
          implications: {
            primary_view: '高估',
            confidence: 'high',
            confidence_score: 0.85,
            factor_alignment: { label: '同向', status: 'aligned' },
          },
          period: '2y',
          current_price_source: 'historical_close',
          factor_model: { period: '2y', data_points: 132 },
          monte_carlo: { p50: 156.4, p90: 181.2 },
          audit_trail: { comparable_benchmark_source: 'dynamic_peer_median' },
          primary_driver: { factor: 'P/B 倍数法溢价' },
          drivers: [{ factor: 'Alpha 超额收益' }],
        },
      },
      {
        payload: {
          fair_value: { mid: 148.21, low: 121.5, high: 166.8 },
          dcf_scenarios: [
            { name: 'bear', intrinsic_value: 121.5 },
            { name: 'base', intrinsic_value: 148.21 },
            { name: 'bull', intrinsic_value: 166.8 },
          ],
          gap_analysis: { gap_pct: 48.2 },
          implications: {
            primary_view: '高估',
            confidence: 'medium',
            confidence_score: 0.58,
            factor_alignment: { label: '冲突', status: 'conflict' },
          },
          period: '1y',
          current_price_source: 'live',
          factor_model: { period: '1y', data_points: 214 },
          monte_carlo: { p50: 149.1, p90: 170.3 },
          audit_trail: { comparable_benchmark_source: 'static_sector_template' },
          primary_driver: { factor: '估值回归驱动' },
          drivers: [{ factor: 'Alpha 超额收益' }],
        },
      }
    );

    const gapRow = comparison.rows.find((row) => row.key === 'gap-pct');
    const confidenceScoreRow = comparison.rows.find((row) => row.key === 'confidence-score');
    const driverRow = comparison.rows.find((row) => row.key === 'driver');
    const alignmentRow = comparison.rows.find((row) => row.key === 'alignment');
    const periodRow = comparison.rows.find((row) => row.key === 'analysis-period');
    const priceSourceRow = comparison.rows.find((row) => row.key === 'price-source');
    const factorSamplesRow = comparison.rows.find((row) => row.key === 'factor-samples');
    const bearRow = comparison.rows.find((row) => row.key === 'fair-value-bear');
    const bullRow = comparison.rows.find((row) => row.key === 'fair-value-bull');
    const spreadRow = comparison.rows.find((row) => row.key === 'scenario-spread');
    const monteP50Row = comparison.rows.find((row) => row.key === 'monte-carlo-median');
    const benchmarkSourceRow = comparison.rows.find((row) => row.key === 'benchmark-source');
    expect(gapRow.left).toBe('62.60%');
    expect(gapRow.right).toBe('48.20%');
    expect(gapRow.delta).toBe('-14.40%');
    expect(confidenceScoreRow.left).toBe('0.85');
    expect(confidenceScoreRow.right).toBe('0.58');
    expect(confidenceScoreRow.delta).toBe('-0.27');
    expect(driverRow.left).toBe('P/B 倍数法溢价');
    expect(driverRow.right).toBe('估值回归驱动');
    expect(alignmentRow.left).toBe('同向');
    expect(alignmentRow.right).toBe('冲突');
    expect(alignmentRow.delta).toBe('同向 -> 冲突');
    expect(periodRow.delta).toBe('2y -> 1y');
    expect(priceSourceRow.left).toBe('最近收盘价');
    expect(priceSourceRow.right).toBe('实时价格');
    expect(factorSamplesRow.left).toBe('132');
    expect(factorSamplesRow.right).toBe('214');
    expect(factorSamplesRow.delta).toBe('+82');
    expect(bearRow.left).toBe('132.17');
    expect(bearRow.right).toBe('121.50');
    expect(bearRow.delta).toBe('-10.67');
    expect(bullRow.left).toBe('178.81');
    expect(bullRow.right).toBe('166.80');
    expect(bullRow.delta).toBe('-12.01');
    expect(spreadRow.left).toBe('46.64');
    expect(spreadRow.right).toBe('45.30');
    expect(spreadRow.delta).toBe('-1.34');
    expect(monteP50Row.left).toBe('156.40');
    expect(monteP50Row.right).toBe('149.10');
    expect(benchmarkSourceRow.left).toBe('dynamic_peer_median');
    expect(benchmarkSourceRow.right).toBe('static_sector_template');
  });

  it('maps driver impact and strength to user-friendly labels', () => {
    expect(getDriverImpactMeta('overvalued')).toEqual({ color: 'red', label: '估值溢价' });
    expect(getPriceSourceLabel('historical_close')).toBe('最近收盘价');
    expect(getPriceSourceLabel('live')).toBe('实时价格');
    expect(getSignalStrengthMeta(3.33)).toEqual({ score: 3.33, label: '强', color: 'red' });
    expect(getSignalStrengthMeta(1.8)).toEqual({ score: 1.8, label: '中', color: 'gold' });
    expect(getSignalStrengthMeta(0.9)).toEqual({ score: 0.9, label: '弱', color: 'blue' });
  });

  it('does not render missing pricing gaps as zero percent', () => {
    const playbook = buildPricingPlaybook(
      { symbol: 'AAPL', source: 'manual' },
      {
        ...pricingResult,
        gap_analysis: {
          current_price: null,
          fair_value_mid: null,
          gap_pct: null,
          severity: 'unknown',
        },
      }
    );

    expect(playbook.thesis).toContain('价格偏差 —');
    expect(playbook.thesis).not.toContain('0.0%');
  });

  it('supports interactive checklist toggles in the research playbook', () => {
    const playbook = buildPricingPlaybook({ symbol: 'AAPL', source: 'manual' }, pricingResult);

    render(<ResearchPlaybook playbook={playbook} />);

    expect(screen.getByText('已勾选 0/4')).toBeTruthy();
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);

    expect(screen.getByText('已勾选 2/4')).toBeTruthy();
  });
});
