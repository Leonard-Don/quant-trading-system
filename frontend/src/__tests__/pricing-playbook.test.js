import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  buildPricingPlaybook,
  buildPricingWorkbenchPayload,
} from '../components/research-playbook/playbookViewModels';
import { buildSnapshotComparison } from '../components/research-workbench/snapshotCompare';
import ResearchPlaybook from '../components/research-playbook/ResearchPlaybook';
import { getDriverImpactMeta, getPriceSourceLabel, getSignalStrengthMeta } from '../utils/pricingResearch';

jest.mock('antd', () => {
  const React = require('react');
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
  };
});

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
    people_layer: {
      stance: 'fragile',
      risk_level: 'high',
      summary: 'AAPL 的人事层结论偏脆弱，组织质量 0.42 / 脆弱度 0.64。',
    },
    structural_decay: {
      score: 0.74,
      label: '结构性衰败警报',
      action: 'structural_short',
      dominant_failure_label: '组织与治理稀释',
      summary: '结构性衰败警报，主导失效模式偏向 组织与治理稀释。',
    },
    macro_mispricing_thesis: {
      thesis_type: 'relative_short',
      stance: '结构性做空',
      score: 0.74,
      horizon: '中长期',
      primary_leg: {
        symbol: 'AAPL',
        side: 'short',
        role: 'primary',
      },
      hedge_leg: {
        symbol: 'XLK',
        side: 'long',
        role: 'hedge',
      },
      trade_legs: [
        { symbol: 'AAPL', side: 'short', role: 'core_expression', weight: 0.5 },
        { symbol: 'XLK', side: 'long', role: 'beta_hedge', weight: 0.3 },
        { symbol: 'GLD', side: 'long', role: 'stress_hedge', weight: 0.2 },
      ],
      kill_conditions: ['结构性衰败评分回落到 0.50 以下'],
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
    const payload = buildPricingWorkbenchPayload({
      symbol: 'AAPL',
      source: 'manual',
      period: '2y',
      workbenchRefresh: 'high',
      workbenchType: 'pricing',
      workbenchSource: 'godeye',
      workbenchReason: 'priority_escalated',
      workbenchKeyword: 'defense',
      task: 'rw_focus_1',
    }, pricingResult, playbook);

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
    expect(payload.snapshot.payload.people_layer).toEqual({
      stance: 'fragile',
      risk_level: 'high',
      summary: 'AAPL 的人事层结论偏脆弱，组织质量 0.42 / 脆弱度 0.64。',
    });
    expect(payload.snapshot.payload.structural_decay).toEqual({
      score: 0.74,
      label: '结构性衰败警报',
      action: 'structural_short',
      dominant_failure_label: '组织与治理稀释',
      summary: '结构性衰败警报，主导失效模式偏向 组织与治理稀释。',
    });
    expect(payload.context.workbench_view_context.summary).toBe('快速视图：自动排序升档 · 关键词：defense · 更新级别：建议更新 · 类型：Pricing · 来源：GodEye');
    expect(payload.snapshot.payload.view_context.summary).toBe(payload.context.workbench_view_context.summary);
    expect(payload.snapshot.payload.view_context.scoped_task_label).toBe('当前定位：rw_focus_1');
    expect(payload.snapshot.payload.macro_mispricing_thesis).toEqual({
      thesis_type: 'relative_short',
      stance: '结构性做空',
      score: 0.74,
      horizon: '中长期',
      primary_leg: {
        symbol: 'AAPL',
        side: 'short',
        role: 'primary',
      },
      hedge_leg: {
        symbol: 'XLK',
        side: 'long',
        role: 'hedge',
      },
      trade_legs: [
        { symbol: 'AAPL', side: 'short', role: 'core_expression', weight: 0.5 },
        { symbol: 'XLK', side: 'long', role: 'beta_hedge', weight: 0.3 },
        { symbol: 'GLD', side: 'long', role: 'stress_hedge', weight: 0.2 },
      ],
      kill_conditions: ['结构性衰败评分回落到 0.50 以下'],
    });
    expect(payload.refresh_priority_event).toMatchObject({
      reason_key: 'structural_decay',
      reason_label: '结构衰败/系统雷达',
      severity: 'medium',
    });
    expect(payload.refresh_priority_event.lead).toContain('结构性衰败警报');
  });

  it('formats pricing snapshot comparison gap as percent points', () => {
    const comparison = buildSnapshotComparison(
      'pricing',
      {
        payload: {
          view_context: {
            summary: '快速视图：自动排序首次入列 · 类型：Pricing',
            scoped_task_label: '当前定位：rw_base',
          },
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
          view_context: {
            summary: '快速视图：自动排序升档 · 关键词：defense',
            scoped_task_label: '当前定位：rw_target',
          },
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
    const workbenchViewRow = comparison.rows.find((row) => row.key === 'workbench-view');
    const workbenchTaskRow = comparison.rows.find((row) => row.key === 'workbench-task');
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
    expect(workbenchViewRow.delta).toBe('工作台筛选视角已变化');
    expect(workbenchTaskRow.delta).toBe('任务焦点已变化');
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

  it('escalates to cross-market when structured signals conflict even without macro keywords', () => {
    const playbook = buildPricingPlaybook(
      { symbol: 'XOM', source: 'manual' },
      {
        ...pricingResult,
        symbol: 'XOM',
        gap_analysis: {
          ...pricingResult.gap_analysis,
          severity: 'moderate',
          severity_label: '中度偏离',
          direction: '折价(低估)',
        },
        valuation: {
          ...pricingResult.valuation,
          comparables: {
            sector: 'Energy',
          },
        },
        factor_model: {
          ...pricingResult.factor_model,
          factor_source: { is_proxy: true },
          five_factor_source: { is_proxy: false },
        },
        deviation_drivers: {
          primary_driver: {
            factor: 'Beta 暴露',
            description: '系统性风险溢价抬升',
          },
          drivers: [
            {
              factor: 'Beta 暴露',
              description: '系统性风险溢价抬升',
            },
          ],
        },
        implications: {
          ...pricingResult.implications,
          confidence: 'low',
          risk_level: 'high',
          factor_alignment: {
            label: '冲突',
            status: 'conflict',
            summary: '二级因子表现与低估判断方向不一致',
          },
          insights: ['单标的结论需要更多验证'],
        },
      }
    );

    expect(playbook.thesis).toContain('跨市场模板');
    expect(playbook.tasks[3].status).toBe('warning');
    expect(playbook.tasks[3].description).toContain('因子信号与估值结论存在冲突');
    expect(playbook.next_actions[0].target).toBe('cross-market');
  });

  it('does not switch to cross-market from keywords alone when signals are otherwise healthy', () => {
    const playbook = buildPricingPlaybook(
      { symbol: 'NVDA', source: 'manual' },
      {
        ...pricingResult,
        symbol: 'NVDA',
        gap_analysis: {
          ...pricingResult.gap_analysis,
          severity: 'mild',
          severity_label: '轻度偏离',
        },
        valuation: {
          ...pricingResult.valuation,
          comparables: {
            sector: 'Technology',
          },
        },
        factor_model: {
          ...pricingResult.factor_model,
          factor_source: { is_proxy: false },
          five_factor_source: { is_proxy: false },
        },
        deviation_drivers: {
          ...pricingResult.deviation_drivers,
          drivers: [
            {
              factor: '需求预期',
              description: '算力需求提升带来估值扩张',
            },
          ],
        },
        implications: {
          ...pricingResult.implications,
          confidence: 'high',
          risk_level: 'low',
          factor_alignment: {
            label: '同向',
            status: 'aligned',
            summary: '因子信号与高估判断同向',
          },
          insights: ['算力周期仍在扩张'],
        },
      }
    );

    expect(playbook.thesis).toContain('继续留在单标的定价研究框架内');
    expect(playbook.tasks[3].status).toBe('complete');
    expect(playbook.next_actions.some((item) => item?.target === 'cross-market')).toBe(false);
  });
});
