import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import CrossMarketBacktestPanel from '../components/CrossMarketBacktestPanel';

jest.mock('antd/lib/grid/hooks/useBreakpoint', () => jest.fn(() => ({})));
jest.mock('antd/es/grid/hooks/useBreakpoint', () => jest.fn(() => ({})));
jest.mock('antd/lib/_util/responsiveObserver', () => () => ({
  matchHandlers: {},
  dispatch: jest.fn(),
  subscribe: jest.fn(() => Symbol('token')),
  unsubscribe: jest.fn(),
  register: jest.fn(),
  unregister: jest.fn(),
  responsiveMap: {},
}));
jest.mock('antd/es/_util/responsiveObserver', () => () => ({
  matchHandlers: {},
  dispatch: jest.fn(),
  subscribe: jest.fn(() => Symbol('token')),
  unsubscribe: jest.fn(),
  register: jest.fn(),
  unregister: jest.fn(),
  responsiveMap: {},
}));

jest.mock('recharts', () => {
  const React = require('react');
  const passthrough = ({ children }) => <div>{children}</div>;
  return {
    ResponsiveContainer: passthrough,
    BarChart: passthrough,
    Bar: passthrough,
    CartesianGrid: passthrough,
    Legend: passthrough,
    Line: passthrough,
    LineChart: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

jest.mock('antd', () => {
  const actual = jest.requireActual('antd');
  return {
    ...actual,
    Row: ({ children, ...props }) => <div {...props}>{children}</div>,
    Col: ({ children, ...props }) => <div {...props}>{children}</div>,
    Table: ({ dataSource }) => <div data-testid="mock-table">{Array.isArray(dataSource) ? dataSource.length : 0}</div>,
  };
});

jest.mock('../components/research-playbook/ResearchPlaybook', () => (props) => (
  <div>
    <div>{props.playbook?.stageLabel || ''}</div>
    {props.onSaveTask ? (
      <button type="button" onClick={props.onSaveTask}>
        保存到研究工作台
      </button>
    ) : null}
    {props.onUpdateSnapshot ? (
      <button type="button" onClick={props.onUpdateSnapshot}>
        更新当前任务快照
      </button>
    ) : null}
  </div>
));

jest.mock('../components/cross-market/CrossMarketDiagnosticsSection', () => () => <div>diagnostics</div>);
jest.mock('../components/cross-market/CrossMarketBasketSummaryCard', () => () => <div>basket-summary</div>);

jest.mock('../components/research-playbook/playbookViewModels', () => ({
  buildCrossMarketPlaybook: jest.fn(() => ({
    stageLabel: '待运行',
    steps: [],
  })),
}));

jest.mock('../utils/snapshotCompare', () => ({
  buildSnapshotComparison: jest.fn(() => null),
}));

jest.mock('../services/api', () => ({
  getCrossMarketTemplates: jest.fn(),
  runCrossMarketBacktest: jest.fn(),
}));

const mockMessageApi = {
  success: jest.fn(),
  info: jest.fn(),
  warning: jest.fn(),
  error: jest.fn(),
  loading: jest.fn(),
  open: jest.fn(),
  destroy: jest.fn(),
};

jest.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
}));

jest.mock('../utils/crossMarketRecommendations', () => ({
  buildCrossMarketCards: jest.fn(),
  CROSS_MARKET_DIMENSION_LABELS: {
    policy_execution: '政策执行',
    people_fragility: '人的脆弱度',
  },
  CROSS_MARKET_FACTOR_LABELS: {
    people_fragility: 'People Fragility',
    policy_execution_disorder: 'Policy Execution Disorder',
  },
}));

const mockNavigateByResearchAction = jest.fn();
const mockReadResearchContext = jest.fn();

jest.mock('../utils/researchContext', () => ({
  formatResearchSource: jest.fn(() => '研究工作台'),
  navigateByResearchAction: (...args) => mockNavigateByResearchAction(...args),
  readResearchContext: (...args) => mockReadResearchContext(...args),
}));

const {
  getCrossMarketTemplates,
  runCrossMarketBacktest,
} = require('../services/api');
const { buildCrossMarketCards } = require('../utils/crossMarketRecommendations');
const { buildCrossMarketPlaybook } = require('../components/research-playbook/playbookViewModels');
const { formatResearchSource } = require('../utils/researchContext');

const queueContext = {
  source: 'research_workbench',
  task: 'rw_ctx_1',
  template: 'people_decay_short_vs_cashflow_defensive',
  workbenchQueueMode: 'cross_market',
  workbenchRefresh: 'high',
  workbenchType: 'cross_market',
  workbenchSource: 'godeye_people_watchlist',
  workbenchReason: 'people_fragility',
  workbenchSnapshotView: 'filtered',
  workbenchSnapshotFingerprint: 'wv_cross_queue',
  workbenchSnapshotSummary: '快速视图：人的脆弱度升温 · 类型：Cross-Market',
  workbenchKeyword: 'decay',
};

const template = {
  id: 'people_decay_short_vs_cashflow_defensive',
  name: 'People Decay / Cashflow Defensive',
  theme: 'People Decay',
  description: '组织衰败与现金流防御的对冲模板',
  narrative: '当人的维度和政策执行同时恶化时，组合应明显转向防御。',
  construction_mode: 'equal_weight',
  parameters: {
    lookback: 20,
    entry_threshold: 1.5,
    exit_threshold: 0.5,
  },
  assets: [
    { symbol: 'XLU', asset_class: 'ETF', side: 'long', weight: 0.5 },
    { symbol: 'QQQ', asset_class: 'ETF', side: 'short', weight: 0.5 },
  ],
  linked_factors: ['people_fragility', 'policy_execution_disorder'],
  linked_dimensions: ['policy_execution', 'people_fragility'],
  sourceModeLabel: 'fallback-heavy',
  sourceModeDominant: 'proxy',
  sourceModeReason: '来源治理偏脆弱，风险预算应先收缩。',
  sourceModeRiskBudgetScale: 0.72,
  policyExecutionLabel: 'chaotic',
  policyExecutionScore: 0.67,
  policyExecutionTopDepartment: '发改委',
  policyExecutionReason: '正文覆盖退化，执行滞后需要进一步收缩风险预算。',
  policyExecutionRiskBudgetScale: 0.84,
  peopleFragilityLabel: 'fragile',
  peopleFragilityScore: 0.78,
  peopleFragilityFocus: 'BABA / BIDU',
  peopleFragilityReason: '核心技术与治理结构正在失衡。',
  peopleFragilityRiskBudgetScale: 0.8,
  structuralDecayRadarLabel: 'decay_alert',
  structuralDecayRadarDisplayLabel: '结构衰败雷达告警',
  structuralDecayRadarScore: 0.81,
  structuralDecayRadarActionHint: '建议先走防御腿，再决定是否加空头。',
  structuralDecayRadarRiskBudgetScale: 0.76,
  executionPosture: '防御优先 / 对冲增强',
  themeCore: 'XLU',
  themeSupport: 'XLP',
  recommendationTier: '优先部署',
};

const backtestResponse = {
  success: true,
  data: {
    total_return: 0.12,
    performance_summary: {},
    price_matrix_summary: {
      start_date: '2025-01-02',
      end_date: '2025-03-31',
      row_count: 58,
      asset_count: 2,
    },
    data_alignment: {
      tradable_day_ratio: 0.94,
      calendar_diagnostics: {
        reason: '交易日历基本对齐',
      },
    },
    hedge_portfolio: {
      beta_neutrality: {
        reason: '净 beta 接近中性',
      },
    },
    execution_plan: {
      liquidity_summary: {
        reason: '流动性可接受',
      },
      margin_summary: {
        reason: '保证金压力可控',
      },
    },
    execution_diagnostics: {},
    leg_performance: {
      long: { cumulative_return: 0.08 },
      short: { cumulative_return: 0.03 },
      spread: { cumulative_return: 0.12 },
    },
    correlation_matrix: {
      columns: ['symbol', 'XLU', 'QQQ'],
      rows: [
        { symbol: 'XLU', XLU: 1, QQQ: -0.42 },
        { symbol: 'QQQ', XLU: -0.42, QQQ: 1 },
      ],
    },
    allocation_overlay: {
      allocation_mode: 'macro_bias',
      theme: 'People Decay',
      bias_strength: 6.5,
      bias_summary: '宏观权重偏向防御腿。',
      compression_summary: {
        label: 'compressed',
      },
      selection_quality: { label: 'original' },
      dominant_drivers: [],
      execution_posture: '防御优先 / 对冲增强',
      theme_core: 'XLU',
      theme_support: 'XLP',
      compressed_asset_count: 1,
      compressed_assets: ['QQQ'],
      bias_highlights: [],
      bias_actions: [],
      driver_summary: [],
      policy_execution: {
        active: true,
        label: 'chaotic',
        top_department: '发改委',
        risk_budget_scale: 0.84,
        reason: '正文覆盖退化',
      },
      source_mode_summary: {
        active: true,
        label: 'fallback-heavy',
        dominant: 'proxy',
        risk_budget_scale: 0.72,
        reason: '来源治理偏脆弱',
      },
      shifted_asset_count: 1,
      max_delta_weight: 0.05,
      rows: [],
      signal_attribution: [],
      side_bias_summary: {
        long_raw_weight: 0.5,
        long_effective_weight: 0.45,
        short_raw_weight: 0.5,
        short_effective_weight: 0.55,
      },
    },
    constraint_overlay: {
      constraints: {},
      binding_count: 0,
      max_delta_weight: 0,
      binding_assets: [],
      rows: [],
    },
    equity_curve: [],
    drawdown_curve: [],
    trades: [],
    monthly_returns: [],
  },
};

beforeAll(() => {
  const createMediaQueryList = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  });
  const matchMedia = jest.fn().mockImplementation((query) => createMediaQueryList(query));
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: matchMedia,
  });
  Object.defineProperty(global, 'matchMedia', {
    writable: true,
    value: matchMedia,
  });
});

describe('CrossMarketBacktestPanel retained cross-market flow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.history.replaceState(null, '', '/?tab=cross-market');
    formatResearchSource.mockReturnValue('研究工作台');
    mockReadResearchContext.mockReturnValue(queueContext);
    buildCrossMarketPlaybook.mockReturnValue({
      stageLabel: '待运行',
      steps: [],
    });
    getCrossMarketTemplates.mockResolvedValue({ templates: [template] });
    runCrossMarketBacktest.mockResolvedValue(backtestResponse);
    buildCrossMarketCards.mockReturnValue([template]);
  });

  it('drops workbench save and queue controls while preserving template context', async () => {
    render(<CrossMarketBacktestPanel />);

    expect(await screen.findByText(/已载入来自 研究工作台 的跨市场模板/)).toBeTruthy();
    expect(screen.queryByText('当前任务来自工作台复盘队列')).toBeNull();
    expect(screen.queryByRole('button', { name: '保存到研究工作台' })).toBeNull();
    expect(screen.queryByRole('button', { name: '更新当前任务快照' })).toBeNull();
    expect(screen.queryByRole('button', { name: '回到工作台下一条跨市场任务' })).toBeNull();
    expect(mockNavigateByResearchAction).not.toHaveBeenCalled();
  });

  it('updates retained template context when browser history changes', async () => {
    mockReadResearchContext.mockImplementation((search = '') => {
      const params = new URLSearchParams(search);
      if (params.get('template') === queueContext.template) {
        return queueContext;
      }
      return {};
    });

    render(<CrossMarketBacktestPanel />);

    await waitFor(() => {
      expect(screen.queryByText(/已载入来自 研究工作台 的跨市场模板/)).toBeNull();
    });

    await act(async () => {
      window.history.pushState(
        null,
        '',
        `/?tab=cross-market&template=${queueContext.template}&source=${queueContext.source}&note=reload`
      );
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(await screen.findByText(/已载入来自 研究工作台 的跨市场模板/)).toBeTruthy();
  });

  it('shows governance overlays on the template panel and inside backtest results', async () => {
    render(<CrossMarketBacktestPanel />);

    expect((await screen.findAllByText('来源 fallback-heavy')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('政策执行 chaotic').length).toBeGreaterThan(0);
    expect(screen.getAllByText('核心腿：XLU · 辅助腿：XLP').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/来源治理偏脆弱，风险预算应先收缩/).length).toBeGreaterThan(0);
    expect(await screen.findByDisplayValue('XLU')).toBeTruthy();
    expect(await screen.findByDisplayValue('QQQ')).toBeTruthy();

    fireEvent.click(screen.getByText('运行回测'));

    await waitFor(() => {
      expect(runCrossMarketBacktest).toHaveBeenCalledTimes(1);
    });
    expect(mockMessageApi.success).toHaveBeenCalledWith('跨市场回测完成');

    expect(await screen.findByText(/执行姿态：防御优先 \/ 对冲增强/)).toBeTruthy();
    expect(screen.getByText(/政策执行：chaotic/)).toBeTruthy();
    expect(screen.getByText(/来源治理：fallback-heavy/)).toBeTruthy();
  });
});
