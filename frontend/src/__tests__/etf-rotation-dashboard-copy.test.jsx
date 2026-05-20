import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

import EtfRotationDashboard from '../components/EtfRotationDashboard';
import {
  getEtfRotationDailySignal,
  getEtfRotationLiveTarget,
  getEtfRotationPreferences,
  postEtfRotationRefresh,
  postEtfRotationWalkforward,
} from '../services/api';

vi.mock('../services/api', () => ({
  getEtfRotationAnalytics: vi.fn(),
  getEtfRotationAuditLog: vi.fn(),
  getEtfRotationDailySignal: vi.fn(),
  getEtfRotationLiveTarget: vi.fn(),
  getEtfRotationRegimeRecommendation: vi.fn().mockResolvedValue({
    success: true,
    data: {
      regime: { regime_name: 'choppy_low_vol', confidence: 0.73, features: {} },
      recommendation: { recommended_strategy: 'rotation', config_overrides: {} },
    },
  }),
  getEtfRotationPolicyFactorAttribution: vi.fn().mockResolvedValue({
    success: true,
    data: { n_factor_on_rebalances: 0, per_rebalance_attribution: [] },
  }),
  getEtfRotationPreferences: vi.fn(),
  getPolicyRadarSignal: vi.fn(),
  postEtfRotationPreferences: vi.fn(),
  postEtfRotationRefresh: vi.fn(),
  postEtfRotationReloadConfig: vi.fn(),
  postEtfRotationWalkforward: vi.fn(),
}));

beforeEach(() => {
  // The dashboard pre-warms the preference store on mount; let the
  // bootstrap resolve quietly so unrelated tests don't see console
  // warnings about an unhandled rejection.
  getEtfRotationPreferences.mockResolvedValue({
    success: true,
    data: {
      preference: { policy_signal_factor_enabled: null },
      effective: { policy_signal_factor_enabled: false, source: 'config' },
      config_default: { policy_signal_factor_enabled: false },
    },
  });
});

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = () => ({
      matches: false,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
  }

  if (!window.ResizeObserver) {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

afterEach(() => {
  vi.clearAllMocks();
});

const mixedLanguageFixture = {
  manual_only: true,
  auto_ordering: false,
  banner: 'Manual trade plan — review and execute manually. No broker API is called and no auto-ordering occurs.',
  total_asset: 32000,
  current_weights: { '512400': 0.324, '510300': 0.219, CASH: 0.18 },
  target_weights: { '512400': 0.22, '510300': 0.28, CASH: 0.18 },
  adjusted_weights: { '512400': 0.22, '510300': 0.28, CASH: 0.18 },
  quote_source: 'live',
  live_quote_status: { requested: 5, resolved: 4, missing: 1, use_cache: true },
  quote_snapshot: {
    '512400': { current_price: 2.209, source: 'historical_fallback:yahoo' },
    '510300': { current_price: 5.017, source: 'fake-live' },
  },
  suggestions: [
    {
      code: '512400',
      name: '有色金属ETF南方',
      action: 'sell',
      shares: 1500,
      estimated_amount: 3313.5,
      current_weight: 0.324,
      target_weight: 0.22,
      reason: 'delta_-0.1040',
      pricing: {
        action: 'sell',
        reference_price: 2.209,
        tick_size: 0.001,
        limit_prices: { aggressive: 2.207, neutral: 2.208, passive: 2.210 },
        recommended_level: 'neutral',
        recommended_price: 2.208,
        batches: 1,
        shares_per_batch: [1500],
        preferred_windows: ['10:00-11:00'],
        notes: [],
      },
    },
    { code: '510300', name: '沪深300ETF华泰柏瑞', action: 'hold', shares: 0, estimated_amount: 0, current_weight: 0.219, target_weight: 0.28, reason: 'within_threshold' },
  ],
  risk_reasons: ['Cash floor target maintained', 'Manual-only ETF rotation signal'],
  score_breakdown: {
    '512400': {
      latest_price: 2.209,
      return5: -0.02,
      return20: 0.03,
      return60: 0.08,
      ma20: 2.18,
      ma60: 2.11,
      rsi14: 32,
      bollinger_position: 0.1,
      drawdown60: -0.06,
      volatility60: 0.18,
    },
    '510300': {
      latest_price: 5.017,
      return5: 0.04,
      return20: 0.07,
      return60: 0.12,
      ma20: 4.91,
      ma60: 4.82,
      rsi14: 75,
      bollinger_position: 0.95,
      drawdown60: -0.02,
      volatility60: 0.14,
    },
  },
  source_health: [
    { source_id: 'etf_holdings', display_name: 'ETF 持仓快照', status: 'ready', as_of: '2026-05-15T01:00:00+00:00' },
    { source_id: 'etf_quotes', display_name: 'ETF 实时行情', status: 'ready', as_of: '2026-05-15T01:30:00+00:00' },
    { source_id: 'price_matrix', display_name: 'ETF 价格历史', status: 'synthetic', reason: 'deterministic_random_walk', as_of: null },
  ],
};

test('ETF轮动页面将接口里的英文提示和原因统一显示为中文', async () => {
  // Simulate the live-target endpoint being unavailable (503) so the
  // dashboard falls through to the legacy daily-signal endpoint.
  const liveTargetError = new Error('Service Unavailable');
  liveTargetError.response = { status: 503 };
  getEtfRotationLiveTarget.mockRejectedValue(liveTargetError);
  getEtfRotationDailySignal.mockResolvedValue({ data: mixedLanguageFixture });

  const { container } = render(<EtfRotationDashboard />);

  await waitFor(() => {
    expect(screen.getByText('目标偏离 -10.40%')).toBeInTheDocument();
  });

  const pageText = container.textContent;
  expect(pageText).toContain('手动调仓计划');
  expect(pageText).toContain('无需调仓');
  expect(pageText).toContain('目标偏离 -10.40%');
  expect(screen.getByTestId('etf-pricing-rec-512400')).toHaveTextContent('中性 ¥2.208');
  expect(pageText).toContain('现金底线已保留');
  expect(pageText).toContain('手动 ETF 轮动信号');
  expect(pageText).toContain('历史行情回退');
  expect(pageText).toContain('测试实时行情');
  expect(pageText).toContain('逐仓位短线择时');
  expect(pageText).toContain('距20日线');
  expect(pageText).toContain('相对强弱');
  expect(pageText).toContain('战术加仓候选');
  expect(pageText).toContain('短线过热');

  expect(pageText).not.toContain('Manual trade plan');
  expect(pageText).not.toContain('No broker API');
  expect(pageText).not.toContain('delta_-0.1040');
  expect(pageText).not.toContain('within_threshold');
  expect(pageText).not.toContain('Cash floor target maintained');
  expect(pageText).not.toContain('Manual-only ETF rotation signal');
  expect(pageText).not.toContain('historical_fallback:yahoo');
  expect(pageText).not.toContain('fake-live');
  expect(pageText).not.toContain('战术 ADD 候选');
  expect(pageText).not.toContain('OVERBOUGHT');
  expect(pageText).not.toContain('趋势弱·WAIT');
});

test('ETF轮动挂单提示使用接口返回的 tick_size', async () => {
  const fixture = {
    ...mixedLanguageFixture,
    suggestions: mixedLanguageFixture.suggestions.map((item) => (
      item.code === '512400'
        ? {
          ...item,
          pricing: {
            ...item.pricing,
            tick_size: 0.01,
            limit_prices: { aggressive: 2.19, neutral: 2.20, passive: 2.21 },
            recommended_price: 2.20,
          },
        }
        : item
    )),
  };
  getEtfRotationLiveTarget.mockRejectedValue(Object.assign(new Error('Service Unavailable'), { response: { status: 503 } }));
  getEtfRotationDailySignal.mockResolvedValue({ data: fixture });

  render(<EtfRotationDashboard />);

  const rec = await screen.findByTestId('etf-pricing-rec-512400');
  expect(rec).toHaveTextContent('中性 ¥2.200');
  await userEvent.hover(rec);
  expect(await screen.findByText(/最小单位 ¥0\.010/)).toBeInTheDocument();
});

test('ETF轮动页面在 live-target 可用时显示实时刷新模式并渲染数据源健康度', async () => {
  const liveTargetEnvelope = {
    data: {
      plan: mixedLanguageFixture,
      refreshed_at: '2026-05-15T02:00:00+00:00',
      quote_source: 'live',
      debounced: false,
      debounce_max_delta: null,
      reasons: [],
    },
    refresh: { is_trading_hours: false },
  };
  getEtfRotationLiveTarget.mockResolvedValue(liveTargetEnvelope);

  render(<EtfRotationDashboard />);

  await waitFor(() => {
    expect(screen.getByTestId('etf-endpoint-tag')).toHaveTextContent('实时刷新模式');
  });

  // Source health badges visible with Chinese display_name + status label.
  expect(screen.getByText(/ETF 持仓快照/)).toBeInTheDocument();
  expect(screen.getByText(/ETF 价格历史/)).toBeInTheDocument();
  // Quote-source mode label uses the cross-endpoint mapping.
  expect(screen.getByText('实时报价+实盘历史')).toBeInTheDocument();
  // The legacy daily-signal endpoint must not have been called when
  // live-target succeeded.
  expect(getEtfRotationDailySignal).not.toHaveBeenCalled();
});

test('ETF轮动页面默认折叠 walkforward，展开后才加载面板且不自动请求', async () => {
  const liveTargetEnvelope = {
    data: {
      plan: mixedLanguageFixture,
      refreshed_at: '2026-05-15T02:00:00+00:00',
      quote_source: 'live',
      debounced: false,
    },
    refresh: { is_trading_hours: false },
  };
  getEtfRotationLiveTarget.mockResolvedValue(liveTargetEnvelope);

  render(<EtfRotationDashboard />);

  const collapse = await screen.findByTestId('etf-walkforward-collapse');
  expect(collapse).toBeInTheDocument();
  expect(screen.queryByTestId('etf-walkforward-panel')).not.toBeInTheDocument();

  const user = userEvent.setup();
  await user.click(screen.getByText('历史回测 (Walkforward) · 多窗口稳定性'));

  expect(await screen.findByTestId('etf-walkforward-panel')).toBeInTheDocument();
  expect(screen.getByTestId('etf-walkforward-cache-checkbox')).toBeInTheDocument();
  expect(postEtfRotationWalkforward).not.toHaveBeenCalled();
});

test('点击 "强制刷新" 在 live-target 模式下调用 POST /etf-rotation/refresh', async () => {
  const liveTargetEnvelope = {
    data: {
      plan: mixedLanguageFixture,
      refreshed_at: '2026-05-15T02:00:00+00:00',
      quote_source: 'live',
      debounced: false,
    },
    refresh: { is_trading_hours: false },
  };
  getEtfRotationLiveTarget.mockResolvedValue(liveTargetEnvelope);

  const refreshedFixture = {
    ...mixedLanguageFixture,
    total_asset: 31500,
  };
  postEtfRotationRefresh.mockResolvedValue({
    data: {
      plan: refreshedFixture,
      refreshed_at: '2026-05-15T03:00:00+00:00',
      quote_source: 'live',
      debounced: false,
    },
    refresh: { refreshed: true },
  });

  render(<EtfRotationDashboard />);
  await waitFor(() => {
    expect(screen.getByTestId('etf-endpoint-tag')).toBeInTheDocument();
  });

  const user = userEvent.setup();
  await user.click(screen.getByTestId('etf-force-refresh-button'));

  await waitFor(() => {
    expect(postEtfRotationRefresh).toHaveBeenCalledWith({ useCache: false });
  });
});

test('政策因子开关默认显示为关闭，Δ 面板不渲染', async () => {
  getEtfRotationLiveTarget.mockResolvedValue({
    data: {
      plan: mixedLanguageFixture,
      refreshed_at: '2026-05-16T02:00:00+00:00',
      quote_source: 'live',
      debounced: false,
    },
  });

  render(<EtfRotationDashboard />);
  // Toggle row renders unconditionally inside the header card.
  const toggle = await screen.findByTestId('etf-policy-factor-toggle');
  expect(toggle).toBeInTheDocument();
  // ``aria-checked`` is how Antd Switch surfaces state to ARIA.
  expect(toggle.getAttribute('aria-checked')).toBe('false');
  // Δ panel hides while the factor is off.
  expect(screen.queryByTestId('etf-policy-factor-delta-panel')).not.toBeInTheDocument();
  // The state badge says "已关闭".
  expect(screen.getByTestId('etf-policy-factor-state-tag')).toHaveTextContent('已关闭');
});

test('manual_override 失效线被破时在价格表里显示 override已破 红色徽标', async () => {
  const planWithInvalidatedOverride = {
    ...mixedLanguageFixture,
    manual_override_status: {
      '512400': {
        invalidation_price: 1.975,
        thesis: '底部+石油抽走流动性',
        set_at: '2026-05-18',
        current_price: 1.96,
        invalidated: true,
        note: '2026-05-19 早盘 1.96 已破',
      },
      '510300': {
        // Override exists but holding the line — should show "override" (gold) not "override已破".
        invalidation_price: 4.50,
        thesis: '长期持有',
        current_price: 5.017,
        invalidated: false,
      },
    },
  };

  getEtfRotationLiveTarget.mockResolvedValue({
    data: {
      plan: planWithInvalidatedOverride,
      refreshed_at: '2026-05-19T02:00:00+00:00',
      quote_source: 'live',
      debounced: false,
    },
    refresh: { is_trading_hours: false },
  });

  render(<EtfRotationDashboard />);

  // The invalidated badge for 512400 must render.
  await waitFor(() => {
    expect(screen.getByTestId('etf-override-invalidated-512400')).toBeInTheDocument();
  });
  expect(screen.getByTestId('etf-override-invalidated-512400')).toHaveTextContent('override已破');

  // The still-valid override for 510300 renders the lighter "override" pill,
  // not the red "override已破" one.
  expect(screen.getByTestId('etf-override-active-510300')).toBeInTheDocument();
  expect(screen.getByTestId('etf-override-active-510300')).toHaveTextContent('override');
  expect(screen.queryByTestId('etf-override-invalidated-510300')).not.toBeInTheDocument();
});

test('ETF轮动页面在 live-target 503 后会自动 trigger_refresh 重新拉取', async () => {
  const error503 = new Error('Service Unavailable');
  error503.response = { status: 503 };

  // First call (no trigger) fails 503; second call (trigger_refresh=true) succeeds.
  getEtfRotationLiveTarget
    .mockRejectedValueOnce(error503)
    .mockResolvedValueOnce({
      data: {
        plan: mixedLanguageFixture,
        refreshed_at: '2026-05-15T02:00:00+00:00',
        quote_source: 'live',
        debounced: false,
      },
    });

  render(<EtfRotationDashboard />);

  await waitFor(() => {
    expect(screen.getByText(/总资产|组合资产/i)).toBeInTheDocument();
  });

  // The bootstrap path must have been called with trigger_refresh=true.
  const triggerCall = getEtfRotationLiveTarget.mock.calls.find(
    (args) => args[0]?.triggerRefresh === true,
  );
  expect(triggerCall).toBeDefined();
});
