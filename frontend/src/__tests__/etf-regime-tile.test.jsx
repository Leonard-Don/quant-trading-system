import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import EtfRegimeTile from '../components/EtfRegimeTile';
import { getEtfRotationRegimeRecommendation } from '../services/api';

vi.mock('../services/api', () => ({
  getEtfRotationRegimeRecommendation: vi.fn(),
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
});

afterEach(() => {
  vi.clearAllMocks();
});

test('ETF市场状态卡片将特征、策略和原因统一显示为中文', async () => {
  getEtfRotationRegimeRecommendation.mockResolvedValue({
    success: true,
    data: {
      regime: {
        regime_name: 'bear_high_vol',
        confidence: 0.82,
        as_of: '2026-05-20',
        lookback_days: 90,
        n_bars_used: 90,
        n_assets_used: 5,
        features: {
          trend_r2: 0.084,
          trend_slope: -0.00035,
          realized_vol: 0.237,
          return_skew: -1.04,
          drawdown_ratio: 0.66,
          avg_pairwise_correlation: 0.72,
        },
        reasons: [
          'trend_slope -0.0004/day <= -0.0005 (bearish)',
          'realised_vol 23.7% >= 20% (high)',
          'return_skew -1.04 <= -0.50 (crash-prone)',
          'avg pairwise corr 0.72 >= 0.70 (risk-off)',
        ],
      },
      recommendation: {
        strategy_name: 'cash',
        config_overrides: { gross_cap: 0.2 },
        rationale: 'Falling market with high vol — historical evidence shows long-only systematic strategies bleed in this regime. Drop gross_cap to 0.20 (80% cash) and wait for vol to normalise.',
        alternatives: ['mean_reversion', 'blend'],
      },
    },
  });

  const { container } = render(<EtfRegimeTile />);

  await waitFor(() => {
    expect(screen.getByTestId('etf-regime-tile-features')).toBeInTheDocument();
  });

  const pageText = container.textContent;
  expect(pageText).toContain('趋势拟合度 R²');
  expect(pageText).toContain('趋势斜率');
  expect(pageText).toContain('实现波动率');
  expect(pageText).toContain('收益偏度');
  expect(pageText).toContain('回撤/波动比');
  expect(pageText).toContain('跨资产相关性');
  expect(pageText).toContain('现金/等待');
  expect(pageText).toContain('总仓位上限=0.20');
  expect(pageText).toContain('趋势斜率 -0.0004/日 ≤ -0.0005，偏空');
  expect(pageText).toContain('实现波动率 23.7% ≥ 20%，高波动');
  expect(pageText).toContain('左尾风险较高');
  expect(pageText).toContain('风险偏好下降');
  expect(pageText).toContain('下跌且高波动');

  expect(pageText).not.toContain('trend R²');
  expect(pageText).not.toContain('trend slope');
  expect(pageText).not.toContain('max_dd / vol');
  expect(pageText).not.toContain('Falling market with high vol');
  expect(pageText).not.toContain('mean_reversion');
  expect(pageText).not.toContain('gross_cap');
});
