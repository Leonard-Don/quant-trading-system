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
const REVIEW_SNAPSHOT_STORAGE_KEY = 'realtime-review-snapshots';

const mockRealtimeStockDetailModalSpy = jest.fn();
const mockTradePanelSpy = jest.fn();

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
    requestSnapshot: jest.fn(),
    unsubscribe: jest.fn(),
    disconnect: jest.fn(),
  },
}));

jest.mock('../components/TradePanel', () => (props) => {
  mockTradePanelSpy(props);
  return props.visible ? <div data-testid="trade-panel">{props.defaultSymbol}</div> : null;
});

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
    BellOutlined: MockIcon,
    DownOutlined: MockIcon,
    RightOutlined: MockIcon,
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
  const Drawer = ({ children, open }) => (open ? <div>{children}</div> : null);
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
    Drawer,
    Tabs,
  };
});

describe('RealTimePanel', () => {
  const listeners = {};
  let quote;
  let consoleWarnSpy;

  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    Object.keys(listeners).forEach((key) => delete listeners[key]);
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    quote = {
      symbol: '^GSPC',
      price: 5123.45,
      change: 12.34,
      change_percent: 0.24,
      volume: 123456,
      high: 5130.0,
      low: 5100.0,
      timestamp: new Date(Date.now() - 20 * 1000).toISOString(),
    };
    webSocketService.addListener.mockImplementation((event, callback) => {
      listeners[event] = callback;
      return jest.fn();
    });
    webSocketService.connect.mockResolvedValue(undefined);
    webSocketService.requestSnapshot.mockReturnValue(false);
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

      if (url === '/realtime/summary') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              websocket: {
                connections: 1,
                active_symbols: 6,
              },
              cache: {
                bundle_cache_hits: 5,
                bundle_cache_misses: 1,
                bundle_cache_writes: 2,
                bundle_prewarm_calls: 3,
                last_bundle_cache_key: ['^GSPC', '^DJI'],
                last_fetch_stats: {
                  requested: 6,
                  cache_hits: 4,
                  fetched: 2,
                  misses: 0,
                  duration_ms: 12.5,
                },
              },
              quality: {
                active_quote_count: 6,
                field_coverage: [
                  { field: 'price', coverage_ratio: 1 },
                  { field: 'bid', coverage_ratio: 0.5 },
                  { field: 'ask', coverage_ratio: 0.4 },
                ],
                most_incomplete_symbols: [
                  { symbol: 'GC=F', missing_count: 4 },
                  { symbol: '^HSI', missing_count: 3 },
                ],
              },
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

  afterEach(() => {
    consoleWarnSpy.mockRestore();
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

    const symbolCard = await screen.findByText((content, element) => {
      return element?.tagName === 'SPAN' && content.includes('^GSPC · 行情');
    });
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
      expect(screen.getAllByText('行情刚刚更新').length).toBeGreaterThan(0);
    });

    expect(screen.getByText('新鲜 1/6')).toBeInTheDocument();
    expect(screen.getByText('链路模式：连接中 / REST 补数')).toBeInTheDocument();
    expect(screen.getByText('正在建立实时连接')).toBeInTheDocument();
    expect(screen.queryByText('最近接收：--')).not.toBeInTheDocument();
    expect(screen.queryByText('最新行情时间：--')).not.toBeInTheDocument();
    expect(screen.getByText('接收链路刚刚更新')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/realtime/preferences', expect.objectContaining({
      headers: expect.objectContaining({
        'X-Realtime-Profile': expect.any(String),
      }),
    }));
  });

  test('renders development diagnostics from the realtime summary endpoint', async () => {
    render(<RealTimePanel />);

    await waitFor(() => {
      expect(screen.getByText('开发诊断')).toBeInTheDocument();
    });

    // Diagnostics panel is collapsed by default; click to expand
    fireEvent.click(screen.getByText('开发诊断'));

    await waitFor(() => {
      expect(screen.getByText('WS 连接 1')).toBeInTheDocument();
    });
    expect(screen.getByText('bundle 命中 5')).toBeInTheDocument();
    expect(screen.getByText('req 6 / hit 4 / fetch 2')).toBeInTheDocument();
    expect(screen.getByText('^GSPC, ^DJI')).toBeInTheDocument();
    expect(screen.getByText('活跃质量样本')).toBeInTheDocument();
    expect(screen.getByText('ask 40% / bid 50% / price 100%')).toBeInTheDocument();
    expect(screen.getByText('GC=F(4) / ^HSI(3)')).toBeInTheDocument();
    expect(screen.getByText('最近决策轨迹')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText((content) => content.includes('REST 补数 -> ^GSPC'))).toBeInTheDocument();
    });
    expect(api.get).toHaveBeenCalledWith('/realtime/summary');
  });

  test('renders anomaly radar entries for strong movers in the current tab', async () => {
    quote = {
      ...quote,
      change: 155.12,
      change_percent: 3.15,
      high: 5280,
      low: 5100,
      previous_close: 5000,
      price: 5279.9,
      volume: 999999999,
    };

    render(<RealTimePanel />);

    expect(await screen.findByText('异动雷达')).toBeInTheDocument();
    expect(await screen.findByText('强势拉升')).toBeInTheDocument();
    expect(await screen.findByText(/\^GSPC 当前涨幅 3.15%/)).toBeInTheDocument();
  });

  test('opens trade panel with a generated plan draft from anomaly radar', async () => {
    quote = {
      ...quote,
      symbol: '^GSPC',
      price: 5279.9,
      change: 155.12,
      change_percent: 3.15,
      high: 5280,
      low: 5100,
      previous_close: 5000,
      volume: 999999999,
    };

    render(<RealTimePanel />);

    fireEvent.click((await screen.findAllByRole('button', { name: '计划' }))[0]);

    await waitFor(() => {
      expect(screen.getByTestId('trade-panel')).toHaveTextContent('^GSPC');
    });

    const lastCall = mockTradePanelSpy.mock.calls.at(-1)?.[0];
    expect(lastCall.visible).toBe(true);
    expect(lastCall.defaultSymbol).toBe('^GSPC');
    expect(lastCall.planDraft).toEqual(expect.objectContaining({
      symbol: '^GSPC',
      action: 'BUY',
      suggestedEntry: 5279.9,
    }));
  });

  test('saves a local review snapshot for the current realtime workspace state', async () => {
    quote = {
      ...quote,
      symbol: '^GSPC',
      price: 5279.9,
      change: 155.12,
      change_percent: 3.15,
      high: 5280,
      low: 5100,
      previous_close: 5000,
      volume: 999999999,
    };

    render(<RealTimePanel />);

    await screen.findByText((content, element) => {
      return element?.tagName === 'SPAN' && content.includes('^GSPC · 行情');
    });

    fireEvent.click(screen.getByRole('button', { name: '保存快照' }));

    const snapshots = JSON.parse(window.localStorage.getItem(REVIEW_SNAPSHOT_STORAGE_KEY) || '[]');
    expect(snapshots).toHaveLength(1);
    expect(snapshots[0]).toEqual(expect.objectContaining({
      activeTab: 'index',
      activeTabLabel: '指数',
      spotlightSymbol: '^GSPC',
      anomalyCount: expect.any(Number),
    }));
  });

  test('restores the saved review snapshot tab', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-1',
        createdAt: '2026-03-27T09:30:00.000Z',
        activeTab: 'crypto',
        activeTabLabel: '加密',
        spotlightSymbol: 'BTC-USD',
        spotlightName: 'BTC-USD',
        transportModeLabel: 'WebSocket 实时',
        watchedSymbols: ['BTC-USD', 'ETH-USD'],
        loadedCount: 2,
        totalCount: 5,
        anomalyCount: 1,
        anomalies: [
          {
            symbol: 'BTC-USD',
            title: '放量异动',
            description: 'BTC-USD 当前成交量显著放大。',
          },
        ],
        freshnessSummary: { fresh: 2, aging: 0, delayed: 0, pending: 0 },
      },
    ]));

    render(<RealTimePanel />);

    fireEvent.click(screen.getAllByRole('button', { name: '恢复分组' })[0]);

    await waitFor(() => {
      expect(screen.getByText('当前分组：加密货币')).toBeInTheDocument();
    });
  });

  test('persists review notes and outcomes for saved snapshots', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-2',
        createdAt: '2026-03-27T10:00:00.000Z',
        activeTab: 'us',
        activeTabLabel: '美股',
        spotlightSymbol: 'AAPL',
        spotlightName: '苹果',
        transportModeLabel: 'WebSocket 实时',
        watchedSymbols: ['AAPL', 'MSFT'],
        loadedCount: 2,
        totalCount: 8,
        anomalyCount: 1,
        anomalies: [
          {
            symbol: 'AAPL',
            title: '强势拉升',
            description: 'AAPL 当前涨幅 2.80%，处于盘中强势区间。',
          },
        ],
        freshnessSummary: { fresh: 2, aging: 0, delayed: 0, pending: 0 },
        note: '',
        outcome: null,
      },
    ]));

    render(<RealTimePanel />);

    fireEvent.click(screen.getByRole('button', { name: '复盘快照' }));
    fireEvent.click(screen.getByRole('button', { name: '标记有效' }));
    fireEvent.change(
      screen.getByPlaceholderText('写下这笔快照后来的判断、复盘结论或后续动作'),
      { target: { value: '盘后确认突破有效，次日继续观察量能。' } }
    );

    const snapshots = JSON.parse(window.localStorage.getItem(REVIEW_SNAPSHOT_STORAGE_KEY) || '[]');
    expect(snapshots[0]).toEqual(expect.objectContaining({
      id: 'snapshot-2',
      outcome: 'validated',
      note: '盘后确认突破有效，次日继续观察量能。',
    }));
  });

  test('waits briefly for websocket snapshot before falling back to REST for the current tab', async () => {
    jest.useFakeTimers();

    render(<RealTimePanel />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/realtime/preferences', expect.any(Object));
    });

    api.get.mockClear();

    act(() => {
      ['^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI'].forEach((symbol) => {
        listeners.quote?.({
          symbol,
          data: {
            ...quote,
            symbol,
          },
        });
      });
    });

    await act(async () => {
      jest.advanceTimersByTime(220);
      await Promise.resolve();
    });

    expect(api.get).not.toHaveBeenCalledWith('/realtime/quotes', expect.anything());

    jest.useRealTimers();
  });

  test('prefers market timestamp over client receive time when judging quote freshness', async () => {
    quote = {
      ...quote,
      timestamp: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    };

    render(<RealTimePanel />);

    await waitFor(() => {
      expect(screen.getByText('行情延迟 10 分钟')).toBeInTheDocument();
    });

    expect(screen.getByText('接收链路刚刚更新')).toBeInTheDocument();
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

  test('warms the current tab with a websocket snapshot after the realtime connection comes up', async () => {
    jest.useFakeTimers();
    webSocketService.requestSnapshot.mockReturnValue(true);

    render(<RealTimePanel />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/realtime/preferences', expect.any(Object));
    });

    api.get.mockClear();

    await act(async () => {
      listeners.connection?.({ status: 'connected', reconnectAttempts: 0, recovered: false, lastError: null });
      jest.advanceTimersByTime(50);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(webSocketService.requestSnapshot).toHaveBeenCalledWith([
        '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
      ]);
    });
    expect(api.get).not.toHaveBeenCalledWith('/realtime/quotes', expect.anything());

    jest.useRealTimers();
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

  test('refresh button prefers websocket snapshot when realtime connection is healthy', async () => {
    webSocketService.requestSnapshot.mockReturnValue(true);

    render(<RealTimePanel />);

    await waitFor(() => {
      expect(api.get).toHaveBeenCalled();
    });

    api.get.mockClear();

    act(() => {
      listeners.connection?.({ status: 'connected', reconnectAttempts: 0, recovered: false, lastError: null });
    });

    fireEvent.click(screen.getByRole('button', { name: '刷新' }));

    expect(webSocketService.requestSnapshot).toHaveBeenCalledWith([
      '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
    ]);
    expect(api.get).not.toHaveBeenCalledWith('/realtime/quotes', expect.anything());
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
    api.get.mockImplementation((url) => {
      if (url === '/realtime/preferences') {
        return Promise.reject(new Error('preferences unavailable'));
      }

      return Promise.resolve({
        data: {
          success: true,
          data: {
            NFLX: {
              ...quote,
              symbol: 'NFLX',
            },
          },
        },
      });
    });

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
