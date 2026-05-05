/**
 * Integration test for App.handleAutoExecuteBacktestToPaper (Feature I).
 *
 * Verifies the fast-path flow: fetch realtime quote → submit paper order →
 * navigate to ?view=paper. Each failure mode (quote unavailable, order
 * rejected) must fall back to F's prefill+navigate behavior so the user
 * still ends up in the paper workspace ready to retry manually.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import App from '../App';

let onSubmitFromBacktestDashboard = null;
let onAutoExecuteFromBacktestDashboard = null;

jest.mock('../components/ErrorBoundary', () => ({
  __esModule: true,
  default: ({ children }) => <>{children}</>,
}));

jest.mock('../components/RealTimePanel', () => ({ __esModule: true, default: () => <div>RealTimePanel</div> }));
jest.mock('../components/IndustryDashboard', () => ({ __esModule: true, default: () => <div>IndustryDashboard</div> }));
jest.mock('../components/TodayResearchDashboard', () => ({ __esModule: true, default: () => <div>TodayResearchDashboard</div> }));
jest.mock('../components/PaperTradingPanel', () => ({ __esModule: true, default: () => <div>PaperTradingPanel</div> }));

jest.mock('../components/BacktestDashboard', () => ({
  __esModule: true,
  default: ({ onSubmit, onAutoExecuteToPaperTrading }) => {
    onSubmitFromBacktestDashboard = onSubmit;
    onAutoExecuteFromBacktestDashboard = onAutoExecuteToPaperTrading;
    return <div>BacktestDashboard</div>;
  },
}));

const mockRunBacktest = jest.fn();
const mockGetRealtimeQuote = jest.fn();
const mockSubmitPaperOrder = jest.fn();
const mockCreateResearchJournalEntry = jest.fn();

jest.mock('../services/api', () => ({
  getStrategies: jest.fn(() => Promise.resolve([])),
  runBacktest: (...args) => mockRunBacktest(...args),
  createResearchJournalEntry: (...args) => mockCreateResearchJournalEntry(...args),
  getRealtimeQuote: (...args) => mockGetRealtimeQuote(...args),
  submitPaperOrder: (...args) => mockSubmitPaperOrder(...args),
}));

jest.mock('../contexts/ThemeContext', () => ({
  useTheme: () => ({ isDarkMode: false, toggleTheme: jest.fn() }),
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
      warning: jest.fn(),
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
          <button key={item.key} type="button">{item.label}</button>
        ))}
      </nav>
    ),
    Space: ({ children }) => <div>{children}</div>,
    Button: ({ children, onClick }) => <button type="button" onClick={onClick}>{children}</button>,
    Tooltip: ({ children }) => <>{children}</>,
    Spin: () => <div>Loading</div>,
    Grid: { useBreakpoint: () => ({ lg: true }) },
  };
});

const RESULT_WITH_TRADES = {
  symbol: 'AAPL',
  strategy: 'MovingAverageCrossover',
  total_return: 0.12,
  trades: [
    { type: 'BUY', quantity: 10, price: 100, date: '2024-01-01' },
    { type: 'SELL', quantity: 10, price: 110, date: '2024-06-01' },
  ],
};

describe('App auto-execute backtest to paper', () => {
  beforeEach(() => {
    onSubmitFromBacktestDashboard = null;
    onAutoExecuteFromBacktestDashboard = null;
    mockRunBacktest.mockReset();
    mockGetRealtimeQuote.mockReset();
    mockSubmitPaperOrder.mockReset();
    mockCreateResearchJournalEntry.mockReset();
    window.history.replaceState(null, '', '/?view=backtest');
    window.sessionStorage.clear();
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('happy path: fetches quote, submits order, navigates to paper', async () => {
    mockGetRealtimeQuote.mockResolvedValueOnce({ data: { price: 152.5 } });
    mockSubmitPaperOrder.mockResolvedValueOnce({ success: true });

    render(<App />);
    await waitFor(() => expect(onAutoExecuteFromBacktestDashboard).toBeInstanceOf(Function));

    await onAutoExecuteFromBacktestDashboard(RESULT_WITH_TRADES);

    expect(mockGetRealtimeQuote).toHaveBeenCalledWith('AAPL');
    expect(mockSubmitPaperOrder).toHaveBeenCalledTimes(1);
    const submitted = mockSubmitPaperOrder.mock.calls[0][0];
    expect(submitted).toMatchObject({
      symbol: 'AAPL',
      side: 'SELL',
      quantity: 10,
      fill_price: 152.5,
      commission: 0,
      slippage_bps: 0,
    });

    // Navigation to ?view=paper
    expect(window.location.search).toContain('view=paper');
    // No prefill needed since the order succeeded
    expect(window.sessionStorage.getItem('paper-trading-prefill')).toBeNull();
  });

  test('quote unavailable falls back to prefill path', async () => {
    mockGetRealtimeQuote.mockResolvedValueOnce({ data: { price: null } });

    render(<App />);
    await waitFor(() => expect(onAutoExecuteFromBacktestDashboard).toBeInstanceOf(Function));

    await onAutoExecuteFromBacktestDashboard(RESULT_WITH_TRADES);

    expect(mockSubmitPaperOrder).not.toHaveBeenCalled();
    // Prefill staged for the manual flow, navigation still happens
    const stored = JSON.parse(window.sessionStorage.getItem('paper-trading-prefill'));
    expect(stored).toMatchObject({ symbol: 'AAPL', side: 'SELL', quantity: 10 });
    expect(window.location.search).toContain('view=paper');
  });

  test('order rejection (e.g. insufficient cash) falls back to prefill path', async () => {
    mockGetRealtimeQuote.mockResolvedValueOnce({ data: { price: 100 } });
    mockSubmitPaperOrder.mockRejectedValueOnce({
      response: { data: { error: { message: 'insufficient cash' } } },
    });

    render(<App />);
    await waitFor(() => expect(onAutoExecuteFromBacktestDashboard).toBeInstanceOf(Function));

    await onAutoExecuteFromBacktestDashboard(RESULT_WITH_TRADES);

    expect(mockSubmitPaperOrder).toHaveBeenCalledTimes(1);
    const stored = JSON.parse(window.sessionStorage.getItem('paper-trading-prefill'));
    expect(stored).toMatchObject({ symbol: 'AAPL', side: 'SELL', quantity: 10 });
    expect(window.location.search).toContain('view=paper');
  });

  test('symbol-only result (no trades) bails out without quote / order calls', async () => {
    render(<App />);
    await waitFor(() => expect(onAutoExecuteFromBacktestDashboard).toBeInstanceOf(Function));

    await onAutoExecuteFromBacktestDashboard({ symbol: 'MSFT', strategy: 'BuyAndHold', trades: [] });

    expect(mockGetRealtimeQuote).not.toHaveBeenCalled();
    expect(mockSubmitPaperOrder).not.toHaveBeenCalled();
    // Bail-out doesn't navigate to ?view=paper
    expect(window.location.search).not.toContain('view=paper');
  });
});
