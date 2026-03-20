import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import RealTimePanel from '../components/RealTimePanel';
import api from '../services/api';
import webSocketService from '../services/websocket';

const mockMessageApi = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
};

const mockRealtimeStockDetailModalSpy = jest.fn();

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    put: jest.fn(),
  },
}));

jest.mock('../services/websocket', () => ({
  __esModule: true,
  default: {
    addListener: jest.fn(),
    connect: jest.fn(),
    subscribe: jest.fn(),
    unsubscribe: jest.fn(),
    disconnect: jest.fn(),
  },
}));

jest.mock('../components/TradePanel', () => () => null);

jest.mock('../components/RealtimeStockDetailModal', () => (props) => {
  mockRealtimeStockDetailModalSpy(props);
  if (!props.open) {
    return null;
  }

  return (
    <div data-testid="realtime-stock-detail-modal">
      {props.symbol}
    </div>
  );
});

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = ({ children }) => <span>{children}</span>;

  return {
    ArrowUpOutlined: MockIcon,
    ArrowDownOutlined: MockIcon,
    SearchOutlined: MockIcon,
    PlayCircleOutlined: MockIcon,
    PauseCircleOutlined: MockIcon,
    SyncOutlined: MockIcon,
    RiseOutlined: MockIcon,
    DollarOutlined: MockIcon,
    StockOutlined: MockIcon,
    PropertySafetyOutlined: MockIcon,
    BankOutlined: MockIcon,
    ThunderboltOutlined: MockIcon,
    BarChartOutlined: MockIcon,
    FundOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  const Card = ({ children }) => <section>{children}</section>;
  const Row = ({ children }) => <div>{children}</div>;
  const Col = ({ children }) => <div>{children}</div>;
  const Tag = ({ children }) => <span>{children}</span>;
  const Badge = () => <span data-testid="badge" />;
  const Statistic = ({ title, value }) => (
    <div>
      <span>{title}</span>
      <span>{value}</span>
    </div>
  );
  const Switch = ({ checked, onChange }) => (
    <input
      aria-label="auto-update"
      type="checkbox"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
    />
  );
  const Input = ({ value, onChange, placeholder, onPressEnter }) => (
    <input
      aria-label={placeholder}
      value={value}
      onChange={(event) => onChange?.(event)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          onPressEnter?.(event);
        }
      }}
      placeholder={placeholder}
    />
  );
  const Button = ({ children, onClick }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  );
  const Space = ({ children }) => <div>{children}</div>;
  Space.Compact = ({ children }) => <div>{children}</div>;
  const AutoComplete = ({ children, onChange }) => (
    <div>
      {React.cloneElement(children, {
        onChange: (event) => onChange?.(event.target.value),
      })}
    </div>
  );
  const Tabs = ({ items = [], activeKey }) => {
    let activeItem = null;
    for (const item of items) {
      if (item.key === activeKey) {
        activeItem = item;
        break;
      }
    }
    return <div>{Reflect.get(activeItem || {}, 'children')}</div>;
  };

  return {
    Card,
    Row,
    Col,
    Statistic,
    Tag,
    Input,
    Button,
    Space,
    Typography: {
      Text: ({ children }) => <span>{children}</span>,
    },
    Badge,
    Switch,
    message: {
      useMessage: () => [mockMessageApi, null],
    },
    AutoComplete,
    Tabs,
  };
});

describe('RealTimePanel', () => {
  const listeners = {};
  const quote = {
    symbol: '^GSPC',
    price: 5123.45,
    change: 12.34,
    change_percent: 0.24,
    volume: 123456,
    high: 5130.0,
    low: 5100.0,
    timestamp: '2026-03-18T09:30:00',
  };

  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    Object.keys(listeners).forEach((key) => delete listeners[key]);
    webSocketService.addListener.mockImplementation((event, callback) => {
      listeners[event] = callback;
      return jest.fn();
    });
    webSocketService.connect.mockResolvedValue(undefined);
    api.get.mockImplementation((url) => {
      if (url === '/realtime/preferences') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              symbols: ['^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI', 'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'BABA', '600519.SS', '601398.SS', '300750.SZ', '000858.SZ', 'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'DOGE-USD', '^TNX', '^TYX', 'TLT', 'GC=F', 'CL=F', 'SI=F', 'SPY', 'QQQ', 'UVXY'],
              active_tab: 'index',
            },
          },
        });
      }

      return Promise.resolve({
        data: {
          success: true,
          data: {
            '^GSPC': quote,
          },
        },
      });
    });
    api.put.mockResolvedValue({
      data: {
        success: true,
        data: {
          symbols: [],
          active_tab: 'index',
        },
      },
    });
  });

  test('opens realtime detail modal with the current symbol and quote', async () => {
    render(<RealTimePanel />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/realtime/quotes', {
        params: expect.objectContaining({
          symbols: expect.stringContaining('^GSPC'),
        }),
      });
    });

    const symbolCard = await screen.findByText(/\^GSPC/, { selector: 'span' });
    fireEvent.click(symbolCard);

    await waitFor(() => {
      expect(screen.getByTestId('realtime-stock-detail-modal')).toHaveTextContent('^GSPC');
    });

    const lastCall = mockRealtimeStockDetailModalSpy.mock.calls.at(-1)?.[0];
    expect(lastCall.open).toBe(true);
    expect(lastCall.symbol).toBe('^GSPC');
    expect(lastCall.quote).toEqual(expect.objectContaining(quote));
    expect(lastCall.quote._clientReceivedAt).toEqual(expect.any(Number));
  });

  test('shows quote freshness on the hero summary and the quote card', async () => {
    render(<RealTimePanel />);

    await waitFor(() => {
      expect(screen.getAllByText('刚刚更新').length).toBeGreaterThan(0);
    });

    expect(screen.getByText('新鲜 1/6')).toBeInTheDocument();
    expect(screen.getByText('链路模式：连接中 / REST 补数')).toBeInTheDocument();
    expect(screen.getByText('正在建立实时连接')).toBeInTheDocument();
    expect(screen.queryByText('最近成功刷新：--')).not.toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/realtime/preferences', expect.objectContaining({
      headers: expect.objectContaining({
        'X-Realtime-Profile': expect.any(String),
      }),
    }));
  });

  test('shows recovery status after websocket reconnects', async () => {
    render(<RealTimePanel />);

    act(() => {
      listeners.connection?.({ status: 'connected', reconnectAttempts: 0, recovered: false, lastError: null });
    });

    await waitFor(() => {
      expect(screen.getByText('实时推送正常')).toBeInTheDocument();
    });

    act(() => {
      listeners.connection?.({ status: 'reconnecting', reconnectAttempts: 2, lastError: 'network lost', nextRetryInMs: 3000 });
    });

    await waitFor(() => {
      expect(screen.getByText('正在重连实时推送')).toBeInTheDocument();
    });
    expect(screen.getByText('链路模式：重连中 / REST 补数')).toBeInTheDocument();
    expect(screen.getByText('重连次数：2')).toBeInTheDocument();
    expect(screen.getByText(/最近异常：network lost/)).toBeInTheDocument();

    act(() => {
      listeners.connection?.({ status: 'connected', reconnectAttempts: 0, recovered: true, lastError: null });
    });

    await waitFor(() => {
      expect(screen.getByText('实时推送已恢复')).toBeInTheDocument();
    });

    expect(screen.getByText('链路模式：WebSocket 实时')).toBeInTheDocument();
  });

  test('resets websocket subscriptions on unmount', () => {
    const { unmount } = render(<RealTimePanel />);

    unmount();

    expect(webSocketService.disconnect).toHaveBeenCalledWith({ resetSubscriptions: true });
  });

  test('adds a typed symbol when clicking the add button', async () => {
    render(<RealTimePanel />);

    await waitFor(() => {
      expect(webSocketService.subscribe).toHaveBeenCalled();
    });

    webSocketService.subscribe.mockClear();

    fireEvent.change(
      screen.getByLabelText('搜索... (支持指数、美股、A股、加密货币、债券等)'),
      { target: { value: 'NFLX' } }
    );
    fireEvent.click(screen.getByRole('button', { name: '添加' }));

    await waitFor(() => {
      expect(webSocketService.subscribe).toHaveBeenCalledWith(['NFLX']);
    });
  });

  test('refresh button refetches the current tab instead of sending the click event as symbols', async () => {
    render(<RealTimePanel />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalled();
    });

    api.get.mockClear();

    fireEvent.click(screen.getByRole('button', { name: '刷新' }));

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/realtime/quotes', {
        params: expect.objectContaining({
          symbols: expect.stringContaining('^GSPC'),
        }),
      });
    });

    expect(api.get.mock.calls[0][1].params.symbols).not.toContain('[object Object]');
  });

  test('does not repeatedly refetch the same unresolved symbols on every quote update', async () => {
    render(<RealTimePanel />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalled();
    });

    api.get.mockClear();

    act(() => {
      listeners.quote?.({
        symbol: '^GSPC',
        data: {
          ...quote,
          price: 5126.12,
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('5126.12')).toBeInTheDocument();
    });

    expect(api.get).not.toHaveBeenCalled();
  });

  test('restores persisted watchlist and active tab from local storage', async () => {
    window.localStorage.setItem('realtime-panel:symbols', JSON.stringify(['NFLX']));
    window.localStorage.setItem('realtime-panel:active-tab', 'us');

    render(<RealTimePanel />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/realtime/quotes', {
        params: expect.objectContaining({
          symbols: 'NFLX',
        }),
      });
    });
  });

  test('persists watchlist updates to local storage after adding a symbol', async () => {
    render(<RealTimePanel />);

    fireEvent.change(
      screen.getByLabelText('搜索... (支持指数、美股、A股、加密货币、债券等)'),
      { target: { value: 'NFLX' } }
    );
    fireEvent.click(screen.getByRole('button', { name: '添加' }));

    await waitFor(() => {
      const storedSymbols = JSON.parse(window.localStorage.getItem('realtime-panel:symbols'));
      expect(storedSymbols).toContain('NFLX');
    });

    expect(window.localStorage.getItem('realtime-panel:active-tab')).toBe('us');
  });

  test('syncs updated watchlist preferences back to the backend', async () => {
    jest.useFakeTimers();

    render(<RealTimePanel />);

    fireEvent.change(
      screen.getByLabelText('搜索... (支持指数、美股、A股、加密货币、债券等)'),
      { target: { value: 'NFLX' } }
    );
    fireEvent.click(screen.getByRole('button', { name: '添加' }));

    act(() => {
      jest.advanceTimersByTime(600);
    });

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        '/realtime/preferences',
        expect.objectContaining({
          symbols: expect.arrayContaining(['NFLX']),
          active_tab: 'us',
        }),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Realtime-Profile': expect.any(String),
          }),
        })
      );
    });

    expect(window.localStorage.getItem('realtime-panel:profile-id')).toEqual(expect.any(String));

    jest.useRealTimers();
  });
});
