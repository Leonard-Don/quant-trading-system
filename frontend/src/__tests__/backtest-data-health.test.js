import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import BacktestDataHealthPanel, { summarizeBacktestDataHealth } from '../components/BacktestDataHealthPanel';
import { checkIndustryHealth } from '../services/api';

jest.mock('../services/api', () => ({
  checkIndustryHealth: jest.fn(),
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

    render(<BacktestDataHealthPanel />);

    await waitFor(() => {
      expect(screen.getByText('数据源健康')).toBeInTheDocument();
      expect(screen.getByText('新浪财经 (Sina Finance)')).toBeInTheDocument();
      expect(screen.getByText('2/3')).toBeInTheDocument();
      expect(screen.getByText(/当前贡献来源：THS \+ SINA/)).toBeInTheDocument();
    });
  });
});
