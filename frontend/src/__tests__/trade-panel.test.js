import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import TradePanel from '../components/TradePanel';
import tradeWebSocketService from '../services/tradeWebsocket';
import {
  getPortfolio,
  getTradeHistory,
  getRealtimeQuote,
  executeTrade,
  resetAccount,
} from '../services/api';

const mockListeners = new Map();

jest.mock('../services/api', () => ({
  getPortfolio: jest.fn(),
  getTradeHistory: jest.fn(),
  getRealtimeQuote: jest.fn(),
  executeTrade: jest.fn(),
  resetAccount: jest.fn(),
}));

jest.mock('../services/tradeWebsocket', () => ({
  __esModule: true,
  default: {
    addListener: jest.fn(),
    connect: jest.fn(),
    disconnect: jest.fn(),
    getStatus: jest.fn(() => ({ isConnected: true })),
  },
}));

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;

  return {
    HistoryOutlined: MockIcon,
    ReloadOutlined: MockIcon,
    ArrowUpOutlined: MockIcon,
    ArrowDownOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  const Card = ({ title, children }) => (
    <section>
      {title ? <div>{title}</div> : null}
      {children}
    </section>
  );
  const Row = ({ children }) => <div>{children}</div>;
  const Col = ({ children }) => <div>{children}</div>;
  const InputNumber = ({ value, onChange, placeholder }) => (
    <input
      aria-label={placeholder || 'input-number'}
      value={value ?? ''}
      onChange={(event) => onChange?.(Number(event.target.value))}
    />
  );
  const Button = ({ children, onClick }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  );
  const Table = ({ dataSource = [] }) => (
    <div data-testid="table">{dataSource.map((item) => item.symbol || item.id).join(',')}</div>
  );
  const Tabs = ({ items = [], activeKey, defaultActiveKey, onChange }) => {
    const currentKey = activeKey || defaultActiveKey || items[0]?.key;
    return (
      <div>
        <button type="button" onClick={() => onChange?.(items[0]?.key)}>
          tabs
        </button>
        {items.find((item) => item.key === currentKey)?.children}
      </div>
    );
  };
  const Statistic = ({ title, value, suffix }) => (
    <div>
      <span>{title}</span>
      <span>{value}</span>
      {suffix ? <span>{suffix}</span> : null}
    </div>
  );
  const Tag = ({ children }) => <span>{children}</span>;
  const Space = ({ children }) => <div>{children}</div>;
  const Modal = ({ open, title, children }) => (
    open ? (
      <div>
        <div>{title}</div>
        <div>{children}</div>
      </div>
    ) : null
  );
  const Popconfirm = ({ children }) => <div>{children}</div>;

  return {
    Card,
    Row,
    Col,
    InputNumber,
    Button,
    Table,
    Tabs,
    Statistic,
    Tag,
    Space,
    Modal,
    Popconfirm,
    Typography: {
      Text: ({ children }) => <span>{children}</span>,
    },
    message: {
      success: jest.fn(),
      error: jest.fn(),
      warning: jest.fn(),
    },
  };
});

describe('TradePanel', () => {
  beforeEach(() => {
    mockListeners.clear();
    jest.clearAllMocks();
    tradeWebSocketService.addListener.mockImplementation((event, callback) => {
      mockListeners.set(event, callback);
      return () => mockListeners.delete(event);
    });
    tradeWebSocketService.connect.mockResolvedValue(undefined);
    getPortfolio.mockResolvedValue({ success: true, data: { positions: [], trade_count: 0 } });
    getTradeHistory.mockResolvedValue({ success: true, data: [] });
    getRealtimeQuote.mockResolvedValue({
      success: true,
      data: {
        symbol: '^GSPC',
        price: 5123.45,
        change_percent: 0.24,
        high: 5130,
        low: 5100,
        timestamp: '2026-03-18T09:30:00',
      },
    });
    executeTrade.mockResolvedValue({ success: true, data: {} });
    resetAccount.mockResolvedValue({ success: true });
  });

  test('loads single-symbol realtime quote for the active symbol', async () => {
    render(
      <TradePanel
        visible
        defaultSymbol="^GSPC"
        onClose={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(getRealtimeQuote).toHaveBeenCalledWith('^GSPC');
    });

    expect(await screen.findByText('参考市价 $5123.45')).toBeInTheDocument();
  });

  test('hydrates portfolio and history from the trade websocket snapshot', async () => {
    render(
      <TradePanel
        visible
        defaultSymbol="AAPL"
        onClose={jest.fn()}
      />
    );

    await act(async () => {
      mockListeners.get('trade_snapshot')?.({
        data: {
          portfolio: {
            balance: 98000,
            total_equity: 100500,
            total_pnl: 500,
            total_pnl_percent: 0.5,
            trade_count: 1,
            positions: [
              {
                symbol: 'AAPL',
                quantity: 10,
                avg_price: 180,
                current_price: 182,
                market_value: 1820,
                unrealized_pnl: 20,
                unrealized_pnl_percent: 1.11,
              },
            ],
          },
          history: [
            {
              id: 'trade-1',
              symbol: 'AAPL',
              action: 'BUY',
              quantity: 10,
              price: 180,
              total_amount: 1800,
              timestamp: '2026-03-18T09:30:00',
            },
          ],
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('交易次数')).toBeInTheDocument();
      expect(screen.getAllByTestId('table')[0]).toHaveTextContent('AAPL');
    });
  });
});
