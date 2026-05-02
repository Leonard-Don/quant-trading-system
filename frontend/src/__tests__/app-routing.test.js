import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import App from '../App';

let mockBreakpoints = { lg: true };
let mockIsDarkMode = false;
const mockToggleTheme = jest.fn();

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

jest.mock('../components/BacktestDashboard', () => ({
  __esModule: true,
  default: () => <div>BacktestDashboard</div>,
}));

jest.mock('../components/TodayResearchDashboard', () => ({
  __esModule: true,
  default: () => <div>TodayResearchDashboard</div>,
}));

jest.mock('../services/api', () => ({
  getStrategies: jest.fn(() => Promise.resolve([])),
  runBacktest: jest.fn(),
}));

jest.mock('../contexts/ThemeContext', () => ({
  useTheme: () => ({
    isDarkMode: mockIsDarkMode,
    toggleTheme: mockToggleTheme,
  }),
}));

jest.mock('../generated/version', () => ({
  APP_VERSION: 'test-version',
}));

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;

  return {
    DashboardOutlined: MockIcon,
    BarChartOutlined: MockIcon,
    LineChartOutlined: MockIcon,
    MenuOutlined: MockIcon,
    SunOutlined: MockIcon,
    MoonOutlined: MockIcon,
    FireOutlined: MockIcon,
    FundOutlined: MockIcon,
    RadarChartOutlined: MockIcon,
    FolderOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  const AntdApp = ({ children, ...rest }) => <div {...rest}>{children}</div>;
  AntdApp.useApp = () => ({
    message: {
      error: jest.fn(),
      loading: jest.fn(),
      destroy: jest.fn(),
      success: jest.fn(),
    },
  });

  const LayoutBase = ({ children, ...rest }) => <div {...rest}>{children}</div>;
  const Layout = Object.assign(LayoutBase, {
    Header: ({ children, ...rest }) => <header {...rest}>{children}</header>,
    Content: ({ children, ...rest }) => <main {...rest}>{children}</main>,
    Sider: ({ children, collapsible, collapsed, collapsedWidth, trigger, width, ...rest }) => (
      <aside {...rest} data-collapsed={collapsed ? 'true' : 'false'} data-width={width}>
        {children}
      </aside>
    ),
  });

  return {
    App: AntdApp,
    Layout,
    Typography: {
      Title: ({ children, ...rest }) => <h1 {...rest}>{children}</h1>,
    },
    Menu: ({ items = [], onClick }) => (
      <nav>
        {items.map((item) => (
          <button key={item.key} type="button" onClick={() => onClick?.({ key: item.key })}>
            {item.label}
          </button>
        ))}
      </nav>
    ),
    Space: ({ children, ...rest }) => <div {...rest}>{children}</div>,
    Button: ({ children, onClick, icon, ...rest }) => (
      <button type="button" onClick={onClick} {...rest}>
        {icon}
        {children}
      </button>
    ),
    Tooltip: ({ children }) => <>{children}</>,
    Spin: () => <div>Loading</div>,
    Grid: {
      useBreakpoint: () => mockBreakpoints,
    },
  };
});

describe('App realtime view routing', () => {
  beforeEach(() => {
    mockBreakpoints = { lg: true };
    mockIsDarkMode = false;
    mockToggleTheme.mockReset();
    window.history.replaceState(null, '', '/?view=realtime&tab=crypto');
  });

  test('preserves realtime tab params while syncing the current view url', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('RealTimePanel')).toBeInTheDocument();
    });

    expect(window.location.search).toContain('view=realtime');
    expect(window.location.search).toContain('tab=crypto');
  });

  test('opens the daily research dashboard from the public navigation', async () => {
    window.history.replaceState(null, '', '/?view=today&symbol=AAPL&source=legacy');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('TodayResearchDashboard')).toBeInTheDocument();
    });

    expect(window.location.search).toContain('view=today');
    expect(window.location.search).not.toContain('symbol=AAPL');

    fireEvent.click(screen.getByRole('button', { name: '策略回测' }));

    await waitFor(() => {
      expect(screen.getByText('BacktestDashboard')).toBeInTheDocument();
    });
  });

  test('renders the app shell without a fixed-height inner scroll container', async () => {
    const { container } = render(<App />);

    await waitFor(() => {
      expect(screen.getByText('RealTimePanel')).toBeInTheDocument();
    });

    expect(container.querySelector('.app-root-layout')).not.toHaveStyle({ height: '100vh' });
    expect(container.querySelector('.app-main-content')).not.toHaveStyle({ overflow: 'auto' });
  });

  test('exposes accessible mobile navigation and theme controls', async () => {
    mockBreakpoints = { lg: false };

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('RealTimePanel')).toBeInTheDocument();
    });

    const menuButton = screen.getByRole('button', { name: '展开导航菜单' });
    expect(menuButton).toHaveAttribute('aria-controls', 'app-primary-navigation');
    expect(menuButton).toHaveAttribute('aria-expanded', 'false');

    const themeButton = screen.getByRole('button', { name: '切换到深色主题' });
    expect(themeButton).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(menuButton);

    expect(screen.getByRole('button', { name: '收起导航菜单' })).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById('app-primary-navigation')).toHaveAttribute('data-collapsed', 'false');
  });

  test('falls back removed system views to the backtest workspace and cleans stale params', async () => {
    window.history.replaceState(null, '', '/?view=pricing&symbol=AAPL&period=2y&source=research_workbench');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('BacktestDashboard')).toBeInTheDocument();
    });

    expect(window.location.search).not.toContain('view=pricing');
    expect(window.location.search).not.toContain('symbol=AAPL');
    expect(window.location.search).not.toContain('period=2y');
  });

  test('keeps an industry-to-backtest handoff symbol while normalizing the URL', async () => {
    window.history.replaceState(null, '', '/?symbol=600519&source=industry_leader&action=prefill_backtest&note=leader');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('BacktestDashboard')).toBeInTheDocument();
    });

    expect(window.location.search).toContain('symbol=600519');
    expect(window.location.search).toContain('source=industry_leader');
    expect(window.location.search).toContain('action=prefill_backtest');
  });
});
