import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import RealTimePanel from '../components/RealTimePanel';
import api from '../services/api';
import webSocketService from '../services/websocket';
import { buildRealtimeActionPosture } from '../utils/realtimeSignals';

const mockMessageApi = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
};
const REVIEW_SNAPSHOT_STORAGE_KEY = 'realtime-review-snapshots';
const ALERT_HIT_HISTORY_STORAGE_KEY = 'realtime-alert-hit-history';

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

jest.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
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
    DeleteOutlined: MockIcon,
    FolderOutlined: MockIcon,
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
  const Input = ({ value, onChange, placeholder, onPressEnter, 'aria-label': ariaLabel, name, autoComplete, inputMode }) => (
    <input
      aria-label={ariaLabel || placeholder}
      name={name}
      autoComplete={autoComplete}
      inputMode={inputMode}
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
  const Button = ({ children, icon, onClick, disabled, 'aria-label': ariaLabel, 'aria-pressed': ariaPressed }) => (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={ariaLabel} aria-pressed={ariaPressed}>
      {icon}
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
    Empty: ({ description }) => <div data-testid="empty">{description}</div>,
  };
});

describe('RealTimePanel', () => {
  const listeners = {};
  let quote;
  let consoleWarnSpy;
  let clipboardWriteText;
  let mockShareWindow;
  let originalWindowOpen;
  let originalNotification;
  let mockNotification;

  const renderRealtimePanel = async () => {
    const view = render(<RealTimePanel />);
    await act(async () => {
      await Promise.resolve();
    });
    return view;
  };

  test('builds a realtime action posture from freshness and follow-through', () => {
    expect(buildRealtimeActionPosture({
      freshnessSummary: { delayed: 5, aging: 2 },
      alertHitSummary: { totalHits: 2 },
      alertFollowThrough: { continued: 1, reversed: 0, pending: 1 },
      anomalyCount: 3,
      symbolCount: 10,
    })).toMatchObject({
      label: 'stale_feed',
      posture: '先确认链路质量',
    });

    expect(buildRealtimeActionPosture({
      freshnessSummary: { delayed: 0, aging: 0 },
      alertHitSummary: { totalHits: 4 },
      alertFollowThrough: { continued: 3, reversed: 1, pending: 0 },
      anomalyCount: 1,
      symbolCount: 10,
      spotlightSymbol: 'NVDA',
    })).toMatchObject({
      label: 'follow_through',
      posture: '先跟进持续性提醒',
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    window.localStorage.clear();
    Object.keys(listeners).forEach((key) => delete listeners[key]);
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    clipboardWriteText = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {
      value: { writeText: clipboardWriteText },
      configurable: true,
    });
    mockShareWindow = {
      document: {
        write: jest.fn(),
        close: jest.fn(),
      },
    };
    originalWindowOpen = window.open;
    window.open = jest.fn(() => mockShareWindow);
    originalNotification = global.Notification;
    mockNotification = jest.fn();
    global.Notification = Object.assign(mockNotification, {
      permission: 'granted',
      requestPermission: jest.fn().mockResolvedValue('granted'),
    });
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
              symbol_categories: {},
            },
          },
        });
      }

      if (url === '/realtime/journal') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              review_snapshots: [],
              timeline_events: [],
            },
          },
        });
      }

      if (url === '/realtime/alerts') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              alerts: [],
              alert_hit_history: [],
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
              symbol_categories: {},
            },
          },
        });
  });

  afterEach(() => {
    consoleWarnSpy.mockRestore();
    window.open = originalWindowOpen;
    global.Notification = originalNotification;
  });

  test('opens realtime detail modal with the current symbol and quote', async () => {
    await renderRealtimePanel();

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
    expect(Array.isArray(lastCall.eventTimeline)).toBe(true);
    expect(Array.isArray(lastCall.compareCandidates)).toBe(true);
    expect(lastCall.compareCandidates).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          symbol: '^GSPC',
          quote: expect.objectContaining(quote),
        }),
      ])
    );
  });

  test('supports global jump search for tracked symbols across groups', async () => {
    await renderRealtimePanel();

    const jumpInput = screen.getByRole('textbox', { name: '全局跳转搜索' });
    fireEvent.change(jumpInput, { target: { value: 'BTC-USD' } });
    fireEvent.keyDown(jumpInput, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('当前分组：加密货币')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId('realtime-stock-detail-modal')).toHaveTextContent('BTC-USD');
    });
  });

  test('exposes accessible names for realtime search inputs', async () => {
    await renderRealtimePanel();

    expect(screen.getByRole('textbox', { name: '添加跟踪标的搜索' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '全局跳转搜索' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '自选组合名称' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '自选组合标的列表' })).toBeInTheDocument();
  });

  test('opens realtime detail modal from the keyboard-accessible quote card trigger', async () => {
    await renderRealtimePanel();

    const detailTrigger = await screen.findByRole('button', { name: '打开 标普500 ^GSPC 深度详情' });
    fireEvent.keyDown(detailTrigger, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByTestId('realtime-stock-detail-modal')).toHaveTextContent('^GSPC');
    });
  });

  test('supports selecting and batch-removing quotes from the current group', async () => {
    await renderRealtimePanel();

    await screen.findByText((content, element) => element?.tagName === 'SPAN' && content.includes('^GSPC · 行情'));

    fireEvent.click(screen.getAllByRole('button', { name: '选择' })[0]);
    expect(screen.getByRole('button', { name: '已选中' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '批量删除' }));

    await waitFor(() => {
      expect(screen.queryByText((content, element) => element?.tagName === 'SPAN' && content.includes('^GSPC · 行情'))).not.toBeInTheDocument();
    });
  });

  test('supports moving selected quotes into another market group and syncing overrides', async () => {
    jest.useFakeTimers();

    await renderRealtimePanel();

    await screen.findByText((content, element) => element?.tagName === 'SPAN' && content.includes('^GSPC · 行情'));
    fireEvent.click(screen.getAllByRole('button', { name: '选择' })[0]);
    fireEvent.click(screen.getByRole('button', { name: '移到加密' }));

    await waitFor(() => {
      expect(screen.getByText('当前分组：加密货币')).toBeInTheDocument();
    });

    act(() => {
      jest.advanceTimersByTime(600);
    });

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        '/realtime/preferences',
        expect.objectContaining({
          symbol_categories: expect.objectContaining({
            '^GSPC': 'crypto',
          }),
        }),
        expect.any(Object)
      );
    });

    jest.useRealTimers();
  });

  test('passes related review events into the realtime detail timeline', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-detail-timeline',
        createdAt: '2026-03-27T12:00:00.000Z',
        activeTab: 'index',
        activeTabLabel: '指数',
        spotlightSymbol: '^GSPC',
        spotlightName: '标普500',
        transportModeLabel: 'WebSocket 实时',
        watchedSymbols: ['^GSPC', '^DJI'],
        loadedCount: 2,
        totalCount: 6,
        anomalyCount: 1,
        anomalies: [
          { symbol: '^GSPC', title: '强势拉升', description: '标普500 当前涨幅 2.10%。' },
        ],
        freshnessSummary: { fresh: 2, aging: 0, delayed: 0, pending: 0 },
        note: '盘后确认突破延续。',
        outcome: 'validated',
      },
    ]));

    await renderRealtimePanel();

    const symbolCard = await screen.findByText((content, element) => {
      return element?.tagName === 'SPAN' && content.includes('^GSPC · 行情');
    });
    fireEvent.click(symbolCard);

    await waitFor(() => {
      expect(screen.getByTestId('realtime-stock-detail-modal')).toHaveTextContent('^GSPC');
    });

    const lastCall = mockRealtimeStockDetailModalSpy.mock.calls.at(-1)?.[0];
    expect(lastCall.eventTimeline).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          symbol: '^GSPC',
          sourceLabel: '复盘快照',
          title: expect.stringContaining('验证有效'),
          description: '盘后确认突破延续。',
        }),
      ])
    );
  });

  test('renders alert hit history and passes alert-hit events into the detail timeline', async () => {
    window.localStorage.setItem(ALERT_HIT_HISTORY_STORAGE_KEY, JSON.stringify([
      {
        id: 'alert-hit-1',
        symbol: '^GSPC',
        condition: 'price_above',
        conditionLabel: '价格 ≥ $5100.00',
        threshold: 5100,
        triggerPrice: 5123.45,
        triggerTime: '2026-03-27T12:15:00.000Z',
        message: '^GSPC 当前价格 $5123.45 已突破 $5100.00',
        priceSnapshot: 5123.45,
      },
    ]));

    await renderRealtimePanel();

    expect(await screen.findByText('提醒命中历史')).toBeInTheDocument();
    expect(screen.getByText('默认收起提醒命中历史，避免主看盘面板被挤到页面下方。')).toBeInTheDocument();
    expect(screen.queryByText('命中次数')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展开提醒命中历史' }));

    expect(screen.getByText('命中次数')).toBeInTheDocument();
    expect(screen.getByText('命中后延续')).toBeInTheDocument();
    expect(screen.getByText('命中后反转')).toBeInTheDocument();
    expect(screen.getByText('待继续观察')).toBeInTheDocument();
    expect(screen.getByText('价格 ≥ $5100.00')).toBeInTheDocument();
    expect(screen.getByText('^GSPC 当前价格 $5123.45 已突破 $5100.00')).toBeInTheDocument();
    const alertMetric = screen.getByText('提醒命中').closest('.realtime-hero__metric');
    expect(alertMetric).toHaveTextContent('1');

    const symbolCard = await screen.findByText((content, element) => {
      return element?.tagName === 'SPAN' && content.includes('^GSPC · 行情');
    });
    fireEvent.click(symbolCard);

    await waitFor(() => {
      expect(screen.getByTestId('realtime-stock-detail-modal')).toHaveTextContent('^GSPC');
    });

    const lastCall = mockRealtimeStockDetailModalSpy.mock.calls.at(-1)?.[0];
    expect(lastCall.eventTimeline).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          symbol: '^GSPC',
          sourceLabel: '提醒命中',
          title: '提醒命中 · 价格 ≥ $5100.00',
          description: '^GSPC 当前价格 $5123.45 已突破 $5100.00',
        }),
      ])
    );
  });

  test('hydrates alert hit history from backend alerts payload', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/realtime/preferences') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              symbols: ['^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI'],
              active_tab: 'index',
              symbol_categories: {},
            },
          },
        });
      }

      if (url === '/realtime/journal') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              review_snapshots: [],
              timeline_events: [],
            },
          },
        });
      }

      if (url === '/realtime/alerts') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              alerts: [],
              alert_hit_history: [
                {
                  id: 'alert-hit-backend-1',
                  symbol: '^GSPC',
                  condition: 'price_above',
                  conditionLabel: '价格 ≥ $5100.00',
                  threshold: 5100,
                  triggerPrice: 5123.45,
                  triggerTime: '2026-03-27T12:15:00.000Z',
                  message: '^GSPC 当前价格 $5123.45 已突破 $5100.00',
                  priceSnapshot: 5123.45,
                },
              ],
            },
          },
        });
      }

      if (url === '/realtime/summary') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              websocket: { connections: 1, active_symbols: 6 },
              cache: {},
              quality: {},
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

    await renderRealtimePanel();

    const alertMetric = await screen.findByText('提醒命中');
    expect(alertMetric.closest('.realtime-hero__metric')).toHaveTextContent('1');
    fireEvent.click(screen.getByRole('button', { name: '展开提醒命中历史' }));
    expect(await screen.findByText('价格 ≥ $5100.00')).toBeInTheDocument();
    expect(screen.getByText('^GSPC 当前价格 $5123.45 已突破 $5100.00')).toBeInTheDocument();
  });

  test('shows quote freshness on the hero summary and the quote card', async () => {
    await renderRealtimePanel();

    await waitFor(() => {
      expect(screen.getAllByText('行情刚刚更新').length).toBeGreaterThan(0);
    });

    const freshnessMetric = screen.getByText('新鲜行情').closest('.realtime-hero__metric');
    expect(freshnessMetric).toHaveTextContent('1/6');
    expect(screen.getByText('链路模式：连接中 / REST 补数')).toBeInTheDocument();
    expect(screen.getByText('市场情绪')).toBeInTheDocument();
    expect(screen.getByText('偏强')).toBeInTheDocument();
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

  test('passes detail quick-trade callback into the realtime detail modal', async () => {
    await renderRealtimePanel();

    const symbolCard = await screen.findByText((content, element) => {
      return element?.tagName === 'SPAN' && content.includes('^GSPC · 行情');
    });
    fireEvent.click(symbolCard);

    await waitFor(() => {
      expect(screen.getByTestId('realtime-stock-detail-modal')).toHaveTextContent('^GSPC');
    });

    const lastCall = mockRealtimeStockDetailModalSpy.mock.calls.at(-1)?.[0];
    expect(lastCall.onQuickTrade).toEqual(expect.any(Function));

    act(() => {
      lastCall.onQuickTrade('^GSPC', {
        symbol: '^GSPC',
        action: 'BUY',
        quantity: 10,
        limitPrice: 5123.45,
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('trade-panel')).toHaveTextContent('^GSPC');
    });

    const tradeCall = mockTradePanelSpy.mock.calls.at(-1)?.[0];
    expect(tradeCall.planDraft).toEqual(expect.objectContaining({
      symbol: '^GSPC',
      action: 'BUY',
      quantity: 10,
      limitPrice: 5123.45,
    }));
  });

  test('renders development diagnostics from the realtime summary endpoint', async () => {
    await renderRealtimePanel();

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

    await renderRealtimePanel();

    expect(await screen.findByText('异动雷达')).toBeInTheDocument();
    expect(await screen.findByText('查看全部异动')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '展开异动' }));
    expect(await screen.findByText('强势拉升')).toBeInTheDocument();
    expect((await screen.findAllByText('高优先级')).length).toBeGreaterThan(0);
    expect(await screen.findByText(/\^GSPC 当前涨幅 3.15%/)).toBeInTheDocument();
  });

  test('sends a browser notification once for high-severity anomalies', async () => {
    quote = {
      ...quote,
      symbol: '^GSPC',
      price: 5300,
      change: 260,
      change_percent: 5.2,
      high: 5310,
      low: 5090,
      previous_close: 5040,
      volume: 999999999,
    };

    await renderRealtimePanel();

    await waitFor(() => {
      expect(mockNotification).toHaveBeenCalledWith(
        '异动雷达: ^GSPC',
        expect.objectContaining({
          body: expect.stringContaining('强势拉升'),
        })
      );
    });

    const notifyCallCount = mockNotification.mock.calls.length;

    act(() => {
      listeners.quote?.({
        symbol: '^GSPC',
        data: {
          ...quote,
          _clientReceivedAt: Date.now(),
        },
      });
    });

    await waitFor(() => {
      expect(mockNotification).toHaveBeenCalledTimes(notifyCallCount);
    });
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

    await renderRealtimePanel();
    fireEvent.click(screen.getByRole('button', { name: '展开异动' }));

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

    await renderRealtimePanel();

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

  test('syncs review snapshots and timeline events back to the realtime journal backend', async () => {
    jest.useFakeTimers();

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

    await renderRealtimePanel();

    await screen.findByText((content, element) => {
      return element?.tagName === 'SPAN' && content.includes('^GSPC · 行情');
    });

    fireEvent.click(screen.getByRole('button', { name: '保存快照' }));

    act(() => {
      jest.advanceTimersByTime(700);
    });

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith(
        '/realtime/journal',
        expect.objectContaining({
          review_snapshots: expect.arrayContaining([
            expect.objectContaining({
              activeTab: 'index',
              spotlightSymbol: '^GSPC',
            }),
          ]),
          timeline_events: expect.any(Array),
        }),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Realtime-Profile': expect.any(String),
          }),
        })
      );
    });

    jest.useRealTimers();
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

    await renderRealtimePanel();

    fireEvent.click(screen.getByRole('button', { name: '展开复盘快照' }));
    fireEvent.click(screen.getAllByRole('button', { name: '恢复分组' })[0]);

    await waitFor(() => {
      expect(screen.getByText('当前分组：加密货币')).toBeInTheDocument();
    });
  });

  test('switches to the snapshot market context before opening snapshot focus detail', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-focus',
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

    await renderRealtimePanel();

    fireEvent.click(screen.getByRole('button', { name: '展开复盘快照' }));
    fireEvent.click(screen.getByRole('button', { name: '焦点详情' }));

    await waitFor(() => {
      expect(screen.getByText('当前分组：加密货币')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId('realtime-stock-detail-modal')).toHaveTextContent('BTC-USD');
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

    await renderRealtimePanel();

    fireEvent.click(screen.getByRole('button', { name: '查看复盘快照' }));
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

  test('shows review outcome statistics for saved snapshots', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-a',
        createdAt: '2026-03-27T10:00:00.000Z',
        activeTab: 'us',
        activeTabLabel: '美股',
        spotlightSymbol: 'AAPL',
        spotlightName: '苹果',
        watchedSymbols: ['AAPL'],
        loadedCount: 1,
        totalCount: 4,
        anomalyCount: 1,
        anomalies: [{ symbol: 'AAPL', title: '强势拉升', description: 'AAPL 当前涨幅 2.80%。' }],
        freshnessSummary: { fresh: 1, aging: 0, delayed: 0, pending: 0 },
        outcome: 'validated',
        note: '',
      },
      {
        id: 'snapshot-b',
        createdAt: '2026-03-27T11:00:00.000Z',
        activeTab: 'crypto',
        activeTabLabel: '加密',
        spotlightSymbol: 'BTC-USD',
        spotlightName: 'BTC-USD',
        watchedSymbols: ['BTC-USD'],
        loadedCount: 1,
        totalCount: 5,
        anomalyCount: 1,
        anomalies: [{ symbol: 'BTC-USD', title: '放量异动', description: 'BTC-USD 当前成交量显著放大。' }],
        freshnessSummary: { fresh: 1, aging: 0, delayed: 0, pending: 0 },
        outcome: 'invalidated',
        note: '',
      },
      {
        id: 'snapshot-c',
        createdAt: '2026-03-27T12:00:00.000Z',
        activeTab: 'index',
        activeTabLabel: '指数',
        spotlightSymbol: 'AAPL',
        spotlightName: '苹果',
        watchedSymbols: ['^GSPC'],
        loadedCount: 1,
        totalCount: 6,
        anomalyCount: 0,
        anomalies: [],
        freshnessSummary: { fresh: 1, aging: 0, delayed: 0, pending: 0 },
        outcome: 'watching',
        note: '',
      },
    ]));

    await renderRealtimePanel();

    expect(screen.getByText('默认收起复盘快照，把主看盘区域留在更靠前的位置，需要回看时再展开。')).toBeInTheDocument();
    expect(screen.queryByText('已复盘')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展开复盘快照' }));

    expect(screen.getByText('已复盘')).toBeInTheDocument();
    expect(screen.getByText('2/3')).toBeInTheDocument();
    expect(screen.getAllByText('验证有效').length).toBeGreaterThan(0);
    expect(screen.getAllByText('观察失效').length).toBeGreaterThan(0);
    expect(screen.getByText('有效率')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('最强分组')).toBeInTheDocument();
    expect(screen.getByText('美股 · 1 次有效')).toBeInTheDocument();
    expect(screen.getByText('常失效异动')).toBeInTheDocument();
    expect(screen.getByText('放量异动 · 1 次失效')).toBeInTheDocument();
    expect(screen.getByText('高频焦点')).toBeInTheDocument();
    expect(screen.getByText('苹果 · 2 次聚焦')).toBeInTheDocument();
  });

  test('filters review statistics by the current active market group', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-us',
        createdAt: '2026-03-27T10:00:00.000Z',
        activeTab: 'us',
        activeTabLabel: '美股',
        spotlightSymbol: 'AAPL',
        spotlightName: '苹果',
        watchedSymbols: ['AAPL'],
        loadedCount: 1,
        totalCount: 4,
        anomalyCount: 1,
        anomalies: [{ symbol: 'AAPL', title: '强势拉升', description: 'AAPL 当前涨幅 2.80%。' }],
        freshnessSummary: { fresh: 1, aging: 0, delayed: 0, pending: 0 },
        outcome: 'validated',
        note: '',
      },
      {
        id: 'snapshot-index',
        createdAt: '2026-03-27T11:00:00.000Z',
        activeTab: 'index',
        activeTabLabel: '指数',
        spotlightSymbol: '^GSPC',
        spotlightName: '标普500',
        watchedSymbols: ['^GSPC'],
        loadedCount: 1,
        totalCount: 6,
        anomalyCount: 1,
        anomalies: [{ symbol: '^GSPC', title: '放量异动', description: '标普500 当前放量。' }],
        freshnessSummary: { fresh: 1, aging: 0, delayed: 0, pending: 0 },
        outcome: 'invalidated',
        note: '',
      },
    ]));

    await renderRealtimePanel();

    fireEvent.click(screen.getByRole('button', { name: '展开复盘快照' }));
    fireEvent.click(screen.getByRole('button', { name: '当前分组' }));

    await waitFor(() => {
      expect(screen.getByText('放量异动 · 1 次失效')).toBeInTheDocument();
    });
    expect(screen.getByText('标普500 · 1 次聚焦')).toBeInTheDocument();
    expect(screen.queryByText('美股 · 1 次有效')).not.toBeInTheDocument();
  });

  test('copies a saved review snapshot as markdown', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-copy',
        createdAt: '2026-03-27T12:00:00.000Z',
        activeTab: 'index',
        activeTabLabel: '指数',
        spotlightSymbol: '^GSPC',
        spotlightName: '标普500',
        transportModeLabel: 'WebSocket 实时',
        watchedSymbols: ['^GSPC', '^DJI'],
        quoteSnapshots: [
          { symbol: '^GSPC', price: '5123.45', changePercent: '0.24%', volume: '123,456' },
          { symbol: '^DJI', price: '38950.22', changePercent: '0.18%', volume: '--' },
        ],
        loadedCount: 2,
        totalCount: 6,
        anomalyCount: 1,
        anomalies: [
          { symbol: '^GSPC', title: '强势拉升', description: '标普500 当前涨幅 2.10%。' },
        ],
        freshnessSummary: { fresh: 2, aging: 0, delayed: 0, pending: 0 },
        note: '盘后继续观察突破延续性。',
        outcome: 'validated',
      },
    ]));

    await renderRealtimePanel();

    fireEvent.click(screen.getByRole('button', { name: '展开复盘快照' }));
    fireEvent.click(screen.getAllByRole('button', { name: '复制摘要' })[0]);

    await waitFor(() => {
      expect(clipboardWriteText).toHaveBeenCalled();
    });
    expect(clipboardWriteText.mock.calls[0][0]).toContain('## 复盘快照 - 标普500');
    expect(clipboardWriteText.mock.calls[0][0]).toContain('- 结果: 验证有效');
    expect(clipboardWriteText.mock.calls[0][0]).toContain('- 备注: 盘后继续观察突破延续性。');
    expect(clipboardWriteText.mock.calls[0][0]).toContain('### 当时价格快照');
    expect(clipboardWriteText.mock.calls[0][0]).toContain('^GSPC: 价格 5123.45');
  });

  test('exports versioned review snapshot JSON payloads', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-export',
        version: 2,
        createdAt: '2026-03-27T12:00:00.000Z',
        activeTab: 'index',
        activeTabLabel: '指数',
        spotlightSymbol: '^GSPC',
        spotlightName: '标普500',
        transportModeLabel: 'WebSocket 实时',
        watchedSymbols: ['^GSPC'],
        loadedCount: 1,
        totalCount: 6,
        anomalyCount: 0,
        anomalies: [],
        freshnessSummary: { fresh: 1, aging: 0, delayed: 0, pending: 0 },
      },
    ]));

    await renderRealtimePanel();

    fireEvent.click(screen.getByRole('button', { name: '展开复盘快照' }));
    fireEvent.click(screen.getByRole('button', { name: '导出 JSON' }));

    await waitFor(() => {
      expect(clipboardWriteText).toHaveBeenCalled();
    });
    expect(clipboardWriteText.mock.calls[0][0]).toContain('"version": 1');
    expect(clipboardWriteText.mock.calls[0][0]).toContain('"review_snapshots"');
    expect(clipboardWriteText.mock.calls[0][0]).toContain('"timeline_events"');
  });

  test('toggles the diagnostics panel visibility', async () => {
    await renderRealtimePanel();

    expect(screen.getByText('开发诊断')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '隐藏诊断' }));
    expect(screen.queryByRole('button', { name: '隐藏诊断' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '显示诊断' }));
    expect(screen.getByText('开发诊断')).toBeInTheDocument();
  });

  test('opens a visual share card for a saved review snapshot', async () => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify([
      {
        id: 'snapshot-share',
        createdAt: '2026-03-27T12:00:00.000Z',
        activeTab: 'index',
        activeTabLabel: '指数',
        spotlightSymbol: '^GSPC',
        spotlightName: '标普500',
        transportModeLabel: 'WebSocket 实时',
        watchedSymbols: ['^GSPC', '^DJI'],
        loadedCount: 2,
        totalCount: 6,
        anomalyCount: 1,
        anomalies: [
          { symbol: '^GSPC', title: '强势拉升', description: '标普500 当前涨幅 2.10%。' },
        ],
        freshnessSummary: { fresh: 2, aging: 0, delayed: 0, pending: 0 },
        note: '盘后继续观察突破延续性。',
        outcome: 'validated',
      },
    ]));

    await renderRealtimePanel();

    fireEvent.click(screen.getByRole('button', { name: '展开复盘快照' }));
    fireEvent.click(screen.getAllByRole('button', { name: '分享卡片' })[0]);

    await waitFor(() => {
      expect(window.open).toHaveBeenCalled();
    });
    expect(mockShareWindow.document.write).toHaveBeenCalled();
    const html = mockShareWindow.document.write.mock.calls[0][0];
    expect(html).toContain('Realtime Review Snapshot');
    expect(html).toContain('标普500');
    expect(html).toContain('盘后继续观察突破延续性。');
    expect(html).toContain('验证有效');
  });

  test('waits briefly for websocket snapshot before falling back to REST for the current tab', async () => {
    jest.useFakeTimers();

    await renderRealtimePanel();

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

    await renderRealtimePanel();

    await waitFor(() => {
      expect(screen.getByText('行情延迟 10 分钟')).toBeInTheDocument();
    });

    expect(screen.getByText('接收链路刚刚更新')).toBeInTheDocument();
  });

  test('shows recovery status after websocket reconnects', async () => {
    await renderRealtimePanel();

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
    expect(screen.getByText('重连 2')).toBeInTheDocument();
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

    await renderRealtimePanel();

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

  test('resets websocket subscriptions on unmount', async () => {
    const { unmount } = await renderRealtimePanel();

    unmount();

    expect(webSocketService.disconnect).toHaveBeenCalledWith({ resetSubscriptions: true });
  });

  test('adds a typed symbol when clicking the add button', async () => {
    await renderRealtimePanel();

    await waitFor(() => {
      expect(webSocketService.subscribe).toHaveBeenCalled();
    });

    webSocketService.subscribe.mockClear();

    fireEvent.change(
      screen.getByRole('textbox', { name: '添加跟踪标的搜索' }),
      { target: { value: 'NFLX' } }
    );
    fireEvent.click(screen.getByRole('button', { name: '添加' }));

    await waitFor(() => {
      const subscribeCalls = webSocketService.subscribe.mock.calls;
      const nflxCall = subscribeCalls.find(
        (call) => Array.isArray(call[0]) && call[0].includes('NFLX')
      );
      expect(nflxCall).toBeTruthy();
    });
  });

  test('supports switching quote view mode and sorting the current market board', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/realtime/preferences') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              symbols: ['^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI'],
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
              websocket: { connections: 1, active_symbols: 6 },
              cache: {},
              quality: {},
            },
          },
        });
      }

      return Promise.resolve({
        data: {
          success: true,
          data: {
            '^GSPC': {
              ...quote,
              symbol: '^GSPC',
              change_percent: 0.24,
            },
            '^DJI': {
              ...quote,
              symbol: '^DJI',
              price: 39000.12,
              change_percent: 1.24,
            },
          },
        },
      });
    });

    await renderRealtimePanel();

    expect(await screen.findByRole('button', { name: '列表模式' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '涨跌幅' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '列表模式' }));
    fireEvent.click(screen.getByRole('button', { name: '代码' }));

    const dowCard = await screen.findByText((content, element) => (
      element?.tagName === 'SPAN' && content.includes('^DJI · 行情')
    ));
    const spxCard = await screen.findByText((content, element) => (
      element?.tagName === 'SPAN' && content.includes('^GSPC · 行情')
    ));

    expect(dowCard.compareDocumentPosition(spxCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test('renders a mini sparkline for quote cards in both grid and list view', async () => {
    await renderRealtimePanel();

    expect(await screen.findByLabelText('^GSPC 价格轨迹')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '列表模式' }));

    expect(await screen.findByLabelText('^GSPC 价格轨迹')).toBeInTheDocument();
    expect(screen.getByText('快照轨迹')).toBeInTheDocument();
  });

  test('refresh button refetches the current tab instead of sending the click event as symbols', async () => {
    await renderRealtimePanel();

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

    await renderRealtimePanel();

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
    await renderRealtimePanel();

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

      if (url === '/realtime/alerts') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              alerts: [],
              alert_hit_history: [],
            },
          },
        });
      }

      if (url === '/realtime/journal') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              review_snapshots: [],
              timeline_events: [],
            },
          },
        });
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

    await renderRealtimePanel();

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/realtime/quotes', {
        params: expect.objectContaining({
          symbols: 'NFLX',
        }),
      });
    });
  });

  test('persists watchlist updates to local storage after adding a symbol', async () => {
    await renderRealtimePanel();

    fireEvent.change(
      screen.getByRole('textbox', { name: '添加跟踪标的搜索' }),
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

    await renderRealtimePanel();

    fireEvent.change(
      screen.getByRole('textbox', { name: '添加跟踪标的搜索' }),
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
          symbol_categories: expect.any(Object),
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
