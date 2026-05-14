import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import EtfRotationDashboard from '../components/EtfRotationDashboard';
import { getEtfRotationDailySignal } from '../services/api';

vi.mock('../services/api', () => ({
  getEtfRotationDailySignal: vi.fn(),
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
};

test('ETF轮动页面将接口里的英文提示和原因统一显示为中文', async () => {
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
