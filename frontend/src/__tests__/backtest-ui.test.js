import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import ResultsDisplay from '../components/ResultsDisplay';
import BacktestHistory from '../components/BacktestHistory';
import { getBacktestHistory, getBacktestReport } from '../services/api';

jest.mock('../services/api', () => ({
  getBacktestHistory: jest.fn(),
  deleteBacktestRecord: jest.fn(),
  getBacktestReport: jest.fn(),
}));

jest.mock('../components/PerformanceChart', () => () => <div>PerformanceChart</div>);
jest.mock('../components/DrawdownChart', () => () => <div>DrawdownChart</div>);
jest.mock('../components/MonthlyHeatmap', () => () => <div>MonthlyHeatmap</div>);
jest.mock('../components/RiskRadar', () => () => <div>RiskRadar</div>);
jest.mock('../components/ReturnHistogram', () => () => <div>ReturnHistogram</div>);

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

  if (!window.URL.createObjectURL) {
    window.URL.createObjectURL = jest.fn(() => 'blob:test');
  }
});

afterEach(() => {
  jest.clearAllMocks();
});

describe('ResultsDisplay', () => {
  test('renders top-level metrics and normalizes compatibility trade fields', async () => {
    render(
      <ResultsDisplay
        results={{
          symbol: 'AAPL',
          strategy: 'buy_and_hold',
          total_return: 0.1,
          annualized_return: 0.2,
          max_drawdown: -0.05,
          sharpe_ratio: 1.5,
          final_value: 11000,
          num_trades: 1,
          win_rate: 1,
          profit_factor: 2.5,
          net_profit: 1000,
          trades: [
            {
              date: '2024-01-01',
              action: 'buy',
              quantity: 5,
              price: 100,
              value: 500,
            },
          ],
          portfolio_history: [
            {
              date: '2024-01-01',
              total: 10000,
              returns: 0,
              signal: 1,
            },
          ],
        }}
      />
    );

    expect(screen.getByText('最终价值')).toBeInTheDocument();
    expect(screen.getByText('$11,000.00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: '交易记录' }));

    await waitFor(() => {
      expect(screen.getByText('买入')).toBeInTheDocument();
      expect(screen.getByText('$500.00')).toBeInTheDocument();
    });
  });
});

describe('BacktestHistory', () => {
  test('builds a clean base64 pdf download link', async () => {
    getBacktestHistory.mockResolvedValue({
      success: true,
      data: [
        {
          id: 'rec-1',
          symbol: 'AAPL',
          strategy: 'buy_and_hold',
          timestamp: '2024-01-02T00:00:00Z',
          start_date: '2024-01-01',
          end_date: '2024-01-06',
          parameters: {},
          metrics: {
            total_return: 0.1,
            annualized_return: 0.2,
            sharpe_ratio: 1.5,
            max_drawdown: -0.05,
            num_trades: 1,
          },
          result: {
            total_return: 0.1,
            annualized_return: 0.2,
            sharpe_ratio: 1.5,
            max_drawdown: -0.05,
            num_trades: 1,
          },
        },
      ],
    });
    getBacktestReport.mockResolvedValue({
      success: true,
      data: {
        pdf_base64: 'ZmFrZQ==',
        filename: 'report.pdf',
      },
    });

    const { container } = render(<BacktestHistory />);

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    const anchor = { click: jest.fn(), href: '', download: '' };
    const createElementSpy = jest
      .spyOn(document, 'createElement')
      .mockImplementation((tagName) => {
        if (tagName === 'a') {
          return anchor;
        }
        return document.createElementNS('http://www.w3.org/1999/xhtml', tagName);
      });
    const appendChildSpy = jest.spyOn(document.body, 'appendChild').mockImplementation(() => anchor);
    const removeChildSpy = jest.spyOn(document.body, 'removeChild').mockImplementation(() => anchor);

    const buttons = container.querySelectorAll('button');
    fireEvent.click(buttons[2]);

    await waitFor(() => {
      expect(getBacktestReport).toHaveBeenCalled();
      expect(anchor.href).toBe('data:application/pdf;base64,ZmFrZQ==');
      expect(anchor.download).toBe('report.pdf');
      expect(anchor.click).toHaveBeenCalled();
    });

    createElementSpy.mockRestore();
    appendChildSpy.mockRestore();
    removeChildSpy.mockRestore();
  });
});
