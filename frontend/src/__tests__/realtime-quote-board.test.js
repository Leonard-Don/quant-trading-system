import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

import RealtimeQuoteBoard from '../components/realtime/RealtimeQuoteBoard';

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;

  return {
    ArrowUpOutlined: MockIcon,
    ArrowDownOutlined: MockIcon,
    BellOutlined: MockIcon,
    DollarOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  return {
    Card: ({ children, className, style, loading, styles, ...rest }) => (
      <div className={className} style={style} {...rest}>
        {children}
      </div>
    ),
    Button: ({ children, danger, icon, loading, onClick, size, type, ...rest }) => (
      <button type="button" onClick={onClick} {...rest}>
        {icon}
        {children}
      </button>
    ),
    Space: ({ children }) => <div>{children}</div>,
    Tabs: ({ items = [], activeKey, onChange, className }) => (
      <div className={className}>
        <div>
          {items.map((item) => (
            <button key={item.key} type="button" onClick={() => onChange?.(item.key)}>
              {item.label}
            </button>
          ))}
        </div>
        <div>{items.find((item) => item.key === activeKey)?.children}</div>
      </div>
    ),
    Typography: {
      Text: ({ children, type, strong, className, ...rest }) => (
        <span
          className={className}
          data-type={type}
          data-strong={strong ? 'true' : 'false'}
          {...rest}
        >
          {children}
        </span>
      ),
    },
    Tag: ({ children, color, style, ...rest }) => (
      <span data-color={color} style={style} {...rest}>
        {children}
      </span>
    ),
  };
});

const createSymbols = (count) => Array.from({ length: count }, (_, index) => `SYM${index + 1}`);

const createQuote = (index) => ({
  price: 100 + index,
  change: index % 2 === 0 ? 1.2 : -0.8,
  change_percent: index % 2 === 0 ? 0.012 : -0.008,
  low: 95 + index,
  high: 105 + index,
  open: 98 + index,
  previous_close: 99 + index,
  volume: 100000 + index,
  timestamp: '2026-04-16T10:00:00Z',
  _clientReceivedAt: '2026-04-16T10:00:01Z',
  source: 'test-feed',
});

const createProps = (symbolCount = 60) => {
  const symbols = createSymbols(symbolCount);
  const quotes = Object.fromEntries(symbols.map((symbol, index) => [symbol, createQuote(index)]));

  return {
    EMPTY_NUMERIC_TEXT: '--',
    activeTab: 'us',
    categoryOptions: [{ key: 'us', label: '美股' }],
    onActiveTabChange: jest.fn(),
    buildMiniTrendSeries: () => [1, 2, 3, 4],
    buildSparklinePoints: () => '0,32 48,28 96,18 144,10',
    currentTabSymbols: symbols,
    draggingSymbol: null,
    getCategoryLabel: () => '美股',
    getCategoryTheme: () => ({
      accent: '#2563eb',
      soft: 'rgba(37, 99, 235, 0.12)',
      label: '美股',
    }),
    getDisplayName: (symbol) => `名称 ${symbol}`,
    getQuoteFreshness: () => ({
      label: '实时',
      detail: '刚刚更新',
      tone: {
        color: '#16a34a',
        background: 'rgba(34, 197, 94, 0.14)',
      },
    }),
    handleOpenAlerts: jest.fn(),
    handleOpenTrade: jest.fn(),
    handleShowDetail: jest.fn(),
    hasNumericValue: (value) => value !== null && value !== undefined && !Number.isNaN(Number(value)),
    inferSymbolCategory: () => 'us',
    onClearSelectedQuotes: jest.fn(),
    onMoveSelectedQuotesToCategory: jest.fn(),
    onRemoveSelectedQuotes: jest.fn(),
    onSelectAllCurrentTab: jest.fn(),
    onSetDraggingSymbol: jest.fn(),
    onToggleQuoteSelection: jest.fn(),
    quoteSortMode: 'default',
    onQuoteSortModeChange: jest.fn(),
    quoteViewMode: 'grid',
    onQuoteViewModeChange: jest.fn(),
    quotes,
    removeSymbol: jest.fn(),
    resolveSymbolCategory: () => 'us',
    reorderWithinCategory: jest.fn(),
    selectedCurrentTabSymbols: [],
    selectedQuoteSymbols: [],
    sortSymbolsForDisplay: (items) => [...items],
    tabs: [{ key: 'us', label: '美股', icon: 'U' }],
    formatPrice: (value) => String(value ?? '--'),
    formatPercent: (value) => `${(Number(value) * 100).toFixed(2)}%`,
    formatQuoteTime: () => '10:00:00',
    formatVolume: (value) => String(value ?? '--'),
    getSymbolsByCategory: () => symbols,
    quoteSortOptions: [{ key: 'default', label: '默认' }],
  };
};

describe('RealtimeQuoteBoard', () => {
  test('progressively renders large grid tabs instead of mounting the whole watchlist at once', () => {
    render(<RealtimeQuoteBoard {...createProps(60)} />);

    expect(screen.getByText('名称 SYM24')).toBeInTheDocument();
    expect(screen.queryByText('名称 SYM25')).not.toBeInTheDocument();
    expect(screen.getByText('已渲染 24 / 60 个卡片，继续加载以展开完整分组。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '再加载 24 个' }));

    expect(screen.getByText('名称 SYM48')).toBeInTheDocument();
    expect(screen.queryByText('名称 SYM49')).not.toBeInTheDocument();
    expect(screen.getByText('已渲染 48 / 60 个卡片，继续加载以展开完整分组。')).toBeInTheDocument();
  });

  test('keeps smaller grid tabs fully rendered without progressive loading controls', () => {
    render(<RealtimeQuoteBoard {...createProps(6)} />);

    expect(screen.getByText('名称 SYM6')).toBeInTheDocument();
    expect(screen.queryByText(/已渲染/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /再加载/ })).not.toBeInTheDocument();
  });
});
