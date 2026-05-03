/**
 * Integration test for the auto-archive hook in App.js#handleBacktest.
 *
 * Verifies:
 * 1. A successful backtest run produces a research-journal entry POST
 * 2. The entry payload reflects the form + result data
 * 3. A failure on the journal write does NOT propagate (best-effort)
 */

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import App from '../App';

let onSubmitFromBacktestDashboard = null;

jest.mock('../components/ErrorBoundary', () => ({
  __esModule: true,
  default: ({ children }) => <>{children}</>,
}));

jest.mock('../components/RealTimePanel', () => ({
  __esModule: true,
  default: () => <div>RealTimePanel</div>,
}));

jest.mock('../components/IndustryDashboard', () => ({
  __esModule: true,
  default: () => <div>IndustryDashboard</div>,
}));

jest.mock('../components/TodayResearchDashboard', () => ({
  __esModule: true,
  default: () => <div>TodayResearchDashboard</div>,
}));

// Capture the onSubmit callback so the test can fire a synthetic backtest run.
jest.mock('../components/BacktestDashboard', () => ({
  __esModule: true,
  default: ({ onSubmit }) => {
    onSubmitFromBacktestDashboard = onSubmit;
    return <div>BacktestDashboard</div>;
  },
}));

const mockRunBacktest = jest.fn();
const mockCreateResearchJournalEntry = jest.fn();

jest.mock('../services/api', () => ({
  getStrategies: jest.fn(() => Promise.resolve([])),
  runBacktest: (...args) => mockRunBacktest(...args),
  createResearchJournalEntry: (...args) => mockCreateResearchJournalEntry(...args),
}));

jest.mock('../contexts/ThemeContext', () => ({
  useTheme: () => ({
    isDarkMode: false,
    toggleTheme: jest.fn(),
  }),
}));

jest.mock('../generated/version', () => ({ APP_VERSION: 'test' }));

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;
  return new Proxy({}, { get: () => MockIcon });
});

jest.mock('antd', () => {
  const React = require('react');
  const AntdApp = ({ children }) => <div>{children}</div>;
  AntdApp.useApp = () => ({
    message: {
      error: jest.fn(),
      loading: jest.fn(),
      destroy: jest.fn(),
      success: jest.fn(),
    },
  });

  const LayoutBase = ({ children }) => <div>{children}</div>;
  const Layout = Object.assign(LayoutBase, {
    Header: ({ children }) => <header>{children}</header>,
    Content: ({ children }) => <main>{children}</main>,
    Sider: ({ children }) => <aside>{children}</aside>,
  });

  return {
    App: AntdApp,
    Layout,
    Typography: { Title: ({ children }) => <h1>{children}</h1> },
    Menu: ({ items = [] }) => (
      <nav>
        {items.map((item) => (
          <button key={item.key} type="button">
            {item.label}
          </button>
        ))}
      </nav>
    ),
    Space: ({ children }) => <div>{children}</div>,
    Button: ({ children, onClick }) => (
      <button type="button" onClick={onClick}>
        {children}
      </button>
    ),
    Tooltip: ({ children }) => <>{children}</>,
    Spin: () => <div>Loading</div>,
    Grid: { useBreakpoint: () => ({ lg: true }) },
  };
});

const FORM = {
  symbol: 'AAPL',
  strategy_name: 'MovingAverageCrossover',
  start_date: '2024-01-01',
  end_date: '2024-12-31',
  initial_capital: 10000,
};
const RESULT = {
  total_return: 0.12,
  sharpe_ratio: 1.05,
  max_drawdown: 0.08,
  num_trades: 5,
};

describe('App backtest auto-archive', () => {
  beforeEach(() => {
    onSubmitFromBacktestDashboard = null;
    mockRunBacktest.mockReset();
    mockCreateResearchJournalEntry.mockReset();
    window.history.replaceState(null, '', '/?view=backtest');
    // Suppress the warn we deliberately log in the failure-path test
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('archives a successful backtest run as a journal entry', async () => {
    mockRunBacktest.mockResolvedValueOnce({ success: true, data: RESULT });
    mockCreateResearchJournalEntry.mockResolvedValueOnce({ success: true });

    render(<App />);

    await waitFor(() => {
      expect(onSubmitFromBacktestDashboard).toBeInstanceOf(Function);
    });

    await onSubmitFromBacktestDashboard(FORM);

    await waitFor(() => {
      expect(mockCreateResearchJournalEntry).toHaveBeenCalledTimes(1);
    });

    const archived = mockCreateResearchJournalEntry.mock.calls[0][0];
    expect(archived.type).toBe('backtest');
    expect(archived.symbol).toBe('AAPL');
    expect(archived.metrics).toMatchObject({
      total_return: 0.12,
      sharpe_ratio: 1.05,
    });
    expect(archived.title).toContain('MovingAverageCrossover');
  });

  test('journal failure does not raise to the user-facing flow', async () => {
    mockRunBacktest.mockResolvedValueOnce({ success: true, data: RESULT });
    mockCreateResearchJournalEntry.mockRejectedValueOnce(new Error('journal down'));

    render(<App />);

    await waitFor(() => {
      expect(onSubmitFromBacktestDashboard).toBeInstanceOf(Function);
    });

    // If the rejection were unhandled, this would throw or trigger an unhandled
    // rejection. We resolve cleanly because handleBacktest awaits the success
    // branch and only fires the journal write as a detached promise.
    await expect(onSubmitFromBacktestDashboard(FORM)).resolves.toBeUndefined();

    await waitFor(() => {
      expect(mockCreateResearchJournalEntry).toHaveBeenCalledTimes(1);
    });
  });

  test('failed backtest does not write to the journal', async () => {
    mockRunBacktest.mockResolvedValueOnce({ success: false, error: 'bad data' });

    render(<App />);

    await waitFor(() => {
      expect(onSubmitFromBacktestDashboard).toBeInstanceOf(Function);
    });

    await onSubmitFromBacktestDashboard(FORM);

    expect(mockCreateResearchJournalEntry).not.toHaveBeenCalled();
  });
});
