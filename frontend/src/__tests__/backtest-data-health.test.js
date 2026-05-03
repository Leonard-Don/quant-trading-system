import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

import BacktestDataHealthPanel, {
  buildBacktestDataHealthSnapshot,
  summarizeBacktestDataHealth,
  summarizeBacktestDataReadiness,
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
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: {
      writeText: jest.fn(),
    },
  });
});

afterEach(() => {
  jest.clearAllMocks();
  navigator.clipboard.writeText.mockReset();
  navigator.clipboard.writeText.mockResolvedValue(undefined);
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

  test('summarizes backtest data readiness from health and provider signals', () => {
    const degraded = summarizeBacktestDataReadiness(
      { connectedCount: 2, totalSources: 3, warningCount: 0 },
      { openBreakerCount: 1, halfOpenBreakerCount: 0 }
    );
    expect(degraded.status).toBe('degraded');
    expect(degraded.label).toBe('降级可跑');

    const ready = summarizeBacktestDataReadiness(
      { connectedCount: 2, totalSources: 2, warningCount: 0 },
      { openBreakerCount: 0, halfOpenBreakerCount: 0 }
    );
    expect(ready.status).toBe('ready');
    expect(ready.label).toBe('可以回测');
  });

  test('builds a copyable diagnostic snapshot', () => {
    const snapshot = buildBacktestDataHealthSnapshot({
      generatedAt: '2026-05-03T12:00:00.000Z',
      readiness: { status: 'ready', label: '可以回测', detail: '主要数据源可用' },
      healthData: { status: 'healthy' },
      providerRuntimeData: { success: true },
    });

    expect(snapshot).toContain('"generated_at": "2026-05-03T12:00:00.000Z"');
    expect(snapshot).toContain('"label": "可以回测"');
    expect(snapshot).toContain('"data_source_health"');
    expect(snapshot).toContain('"provider_runtime"');
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
      expect(screen.getByText('回测前判断')).toBeInTheDocument();
      expect(screen.getByText('降级可跑')).toBeInTheDocument();
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
      expect(screen.getAllByText('状态待确认').length).toBeGreaterThan(0);
    });
  });

  test('copies the current diagnostic snapshot to clipboard', async () => {
    checkIndustryHealth.mockResolvedValue({
      status: 'healthy',
      active_provider: { name: '新浪财经 (Sina Finance)', type: 'sina' },
      data_source_mode: 'sina_primary',
      data_sources_contributing: ['sina'],
      data_sources: {
        sina: { name: '新浪财经 (Sina Finance)', status: 'connected' },
      },
    });
    getProviderRuntimeStatus.mockResolvedValue({
      success: true,
      timestamp: '2026-05-03T12:00:00',
      providers: {
        yahoo: {
          provider: { name: 'yahoo' },
          circuit_breakers: {},
        },
      },
    });

    render(<BacktestDataHealthPanel />);

    await waitFor(() => {
      expect(screen.getByText('可以回测')).toBeInTheDocument();
    });

    await act(async () => {
      userEvent.click(screen.getByRole('button', { name: /复制诊断/ }));
    });

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('"readiness"')
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('"provider_runtime"')
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /已复制/ })).toBeInTheDocument();
    });
  });
});
