import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
const createDeferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

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
        {items.map((item) => (
          <button key={item.key} type="button" onClick={() => onChange?.(item.key)}>
            {item.label}
          </button>
        ))}
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
    await act(async () => {
      render(
        <TradePanel
          visible
          defaultSymbol="^GSPC"
          onClose={jest.fn()}
        />
      );
    });

    await waitFor(() => {
      expect(getRealtimeQuote).toHaveBeenCalledWith('^GSPC');
    });

    expect(await screen.findByText('参考市价 $5123.45')).toBeInTheDocument();
  });

  test('hydrates portfolio and history from the trade websocket snapshot', async () => {
    await act(async () => {
      render(
        <TradePanel
          visible
          defaultSymbol="AAPL"
          onClose={jest.fn()}
        />
      );
    });

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

  test('resets order state when reopening for another symbol', async () => {
    let rerender;
    await act(async () => {
      ({ rerender } = render(
        <TradePanel
          visible
          defaultSymbol="AAPL"
          onClose={jest.fn()}
        />
      ));
    });

    await waitFor(() => {
      expect(getRealtimeQuote).toHaveBeenCalledWith('AAPL');
    });

    const quantityInput = screen.getByLabelText('input-number');
    const priceInput = screen.getByLabelText('市价 Market Price');
    fireEvent.change(quantityInput, { target: { value: '25' } });
    fireEvent.change(priceInput, { target: { value: '101.5' } });
    await act(async () => {
      screen.getByRole('button', { name: '卖出' }).click();
    });

    await act(async () => {
      rerender(
        <TradePanel
          visible={false}
          defaultSymbol="AAPL"
          onClose={jest.fn()}
        />
      );
    });

    await act(async () => {
      rerender(
        <TradePanel
          visible
          defaultSymbol="MSFT"
          onClose={jest.fn()}
        />
      );
    });

    expect(screen.getByText('MSFT 买入计划')).toBeInTheDocument();
    expect(screen.getByText('准备买入')).toBeInTheDocument();
    expect(screen.queryByText('准备卖出')).not.toBeInTheDocument();

    const resetQuantityInput = screen.getByLabelText('input-number');
    const resetPriceInput = screen.getByLabelText('市价 Market Price');
    expect(resetQuantityInput).toHaveValue('100');
    expect(resetPriceInput).toHaveValue('');
  });

  test('ignores stale realtime quote responses when switching symbols quickly', async () => {
    const aaplRequest = createDeferred();
    const msftRequest = createDeferred();

    getRealtimeQuote
      .mockReset()
      .mockImplementation((symbol) => {
        if (symbol === 'AAPL') {
          return aaplRequest.promise;
        }
        if (symbol === 'MSFT') {
          return msftRequest.promise;
        }
        return Promise.resolve({ success: true, data: null });
      });

    let rerender;
    await act(async () => {
      ({ rerender } = render(
        <TradePanel
          visible
          defaultSymbol="AAPL"
          onClose={jest.fn()}
        />
      ));
    });

    await act(async () => {
      rerender(
        <TradePanel
          visible
          defaultSymbol="MSFT"
          onClose={jest.fn()}
        />
      );
    });

    await act(async () => {
      msftRequest.resolve({
        success: true,
        data: {
          symbol: 'MSFT',
          price: 412.34,
          change_percent: 1.23,
          high: 415,
          low: 408,
          timestamp: '2026-03-18T10:00:00',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('参考市价 $412.34')).toBeInTheDocument();
    });

    await act(async () => {
      aaplRequest.resolve({
        success: true,
        data: {
          symbol: 'AAPL',
          price: 999.99,
          change_percent: 9.99,
          high: 1005,
          low: 995,
          timestamp: '2026-03-18T09:30:00',
        },
      });
    });

    expect(screen.queryByText('参考市价 $999.99')).not.toBeInTheDocument();
    expect(screen.getByText('参考市价 $412.34')).toBeInTheDocument();
  });
});
