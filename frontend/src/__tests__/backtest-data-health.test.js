import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import BacktestDataHealthPanel, {
  summarizeBacktestDataHealth,
  summarizeProviderRuntimeStatus,
} from '../components/BacktestDataHealthPanel';
import { checkIndustryHealth, getProviderRuntimeStatus } from '../services/api';

jest.mock('../services/api', () => ({
  checkIndustryHealth: jest.fn(),
  getProviderRuntimeStatus: jest.fn(),
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
  jest.clearAllMocks();
});

describe('BacktestDataHealthPanel', () => {
  test('summarizes connected and warning data sources', () => {
    const summary = summarizeBacktestDataHealth({
      status: 'healthy',
      active_provider: { name: 'Sina + THS' },
      data_source_mode: 'ths_primary',
      data_sources_contributing: ['ths', 'sina'],
      data_sources: {
        ths: { status: 'connected' },
        sina: { status: 'connected' },
        akshare: { status: 'blocked' },
      },
    });

    expect(summary.connectedCount).toBe(2);
    expect(summary.totalSources).toBe(3);
    expect(summary.warningCount).toBe(1);
    expect(summary.activeProvider).toBe('Sina + THS');
  });

  test('summarizes provider circuit breaker runtime status', () => {
    const summary = summarizeProviderRuntimeStatus({
      providers: {
        yahoo: {
          provider: { name: 'yahoo' },
          circuit_breakers: {},
        },
        sina_ths: {
          provider: { name: 'sina_ths' },
          circuit_breakers: {
            ths_hot_board: {
              name: 'sina_ths.ths_hot_board',
              state: 'open',
              failure_count: 5,
              failure_threshold: 5,
            },
            sina_fallback: {
              name: 'sina_ths.sina_fallback',
              state: 'half_open',
              failure_count: 1,
              failure_threshold: 5,
            },
          },
        },
      },
    });

    expect(summary.providerCount).toBe(2);
    expect(summary.breakerCount).toBe(2);
    expect(summary.openBreakerCount).toBe(1);
    expect(summary.halfOpenBreakerCount).toBe(1);
    expect(summary.failureCount).toBe(6);
    expect(summary.status).toBe('degraded');
  });

  test('renders source health status for the backtest workspace', async () => {
    checkIndustryHealth.mockResolvedValue({
      status: 'healthy',
      active_provider: { name: '新浪财经 (Sina Finance)', type: 'sina' },
      data_source_mode: 'ths_primary',
      data_sources_contributing: ['ths', 'sina'],
      data_sources: {
        ths: { name: '同花顺 (THS)', status: 'connected' },
        sina: { name: '新浪财经 (Sina Finance)', status: 'connected' },
        akshare: { name: 'AKShare', status: 'blocked' },
      },
    });
    getProviderRuntimeStatus.mockResolvedValue({
      success: true,
      timestamp: '2026-05-03T12:00:00',
      providers: {
        yahoo: {
          provider: { name: 'yahoo', description: 'US market fallback' },
          circuit_breakers: {},
        },
        sina_ths: {
          provider: { name: 'sina_ths' },
          circuit_breakers: {
            ths_hot_board: {
              name: 'sina_ths.ths_hot_board',
              state: 'open',
              failure_count: 5,
              failure_threshold: 5,
            },
          },
        },
      },
    });

    render(<BacktestDataHealthPanel />);

    await waitFor(() => {
      expect(screen.getByText('数据源健康')).toBeInTheDocument();
      expect(screen.getAllByText(/新浪财经 \(Sina Finance\)/).length).toBeGreaterThan(0);
      expect(screen.getByText('2/3')).toBeInTheDocument();
      expect(screen.getByText(/当前贡献来源：THS \+ SINA/)).toBeInTheDocument();
      expect(screen.getByText('Provider 熔断状态')).toBeInTheDocument();
      expect(screen.getByText('1 个熔断')).toBeInTheDocument();
      expect(screen.getByText(/sina_ths\.ths_hot_board: 熔断/)).toBeInTheDocument();
    });
  });

  test('keeps source health visible when provider runtime status fails', async () => {
    checkIndustryHealth.mockResolvedValue({
      status: 'healthy',
      active_provider: { name: '新浪财经 (Sina Finance)', type: 'sina' },
      data_source_mode: 'sina_primary',
      data_sources_contributing: ['sina'],
      data_sources: {
        sina: { name: '新浪财经 (Sina Finance)', status: 'connected' },
      },
    });
    getProviderRuntimeStatus.mockRejectedValue(new Error('runtime endpoint offline'));

    render(<BacktestDataHealthPanel />);

    await waitFor(() => {
      expect(screen.getByText('数据源健康')).toBeInTheDocument();
      expect(screen.getByText('1/1')).toBeInTheDocument();
      expect(screen.getByText('Provider 状态暂不可用')).toBeInTheDocument();
      expect(screen.getByText('runtime endpoint offline')).toBeInTheDocument();
      expect(screen.getByText('状态待确认')).toBeInTheDocument();
    });
  });
});
