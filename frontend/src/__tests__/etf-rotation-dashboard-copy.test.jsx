import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

import EtfRotationDashboard from '../components/EtfRotationDashboard';
import {
  getEtfRotationDailySignal,
  getEtfRotationLiveTarget,
  postEtfRotationRefresh,
} from '../services/api';

vi.mock('../services/api', () => ({
  getEtfRotationDailySignal: vi.fn(),
  getEtfRotationLiveTarget: vi.fn(),
  postEtfRotationRefresh: vi.fn(),
}));

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
    { code: '512400', name: '有色金属ETF南方', action: 'sell', shares: 1500, estimated_amount: 3313.5, current_weight: 0.324, target_weight: 0.22, reason: 'delta_-0.1040' },
    { code: '510300', name: '沪深300ETF华泰柏瑞', action: 'hold', shares: 0, estimated_amount: 0, current_weight: 0.219, target_weight: 0.28, reason: 'within_threshold' },
  ],
  risk_reasons: ['Cash floor target maintained', 'Manual-only ETF rotation signal'],
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
  expect(pageText).toContain('现金底线已保留');
  expect(pageText).toContain('手动 ETF 轮动信号');
  expect(pageText).toContain('历史行情回退');
  expect(pageText).toContain('测试实时行情');

  expect(pageText).not.toContain('Manual trade plan');
  expect(pageText).not.toContain('No broker API');
  expect(pageText).not.toContain('delta_-0.1040');
  expect(pageText).not.toContain('within_threshold');
  expect(pageText).not.toContain('Cash floor target maintained');
  expect(pageText).not.toContain('Manual-only ETF rotation signal');
  expect(pageText).not.toContain('historical_fallback:yahoo');
  expect(pageText).not.toContain('fake-live');
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
