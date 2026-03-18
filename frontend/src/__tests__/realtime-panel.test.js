import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  const Tabs = ({ items = [], activeKey }) => (
    <div>{items.find((item) => item.key === activeKey)?.children}</div>
  );

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
    webSocketService.addListener.mockImplementation(() => jest.fn());
    webSocketService.connect.mockResolvedValue(undefined);
    api.get.mockResolvedValue({
      data: {
        success: true,
        data: {
          '^GSPC': quote,
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
    expect(lastCall.quote).toEqual(quote);
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
});
