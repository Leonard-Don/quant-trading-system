import { render, waitFor, cleanup, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

import MarketAnalysis from '../components/MarketAnalysis';
import { getAnalysisOverview } from '../services/api';

jest.mock('../services/api', () => ({
  getAnalysisOverview: jest.fn(),
  analyzeTrend: jest.fn(),
  analyzeVolumePrice: jest.fn(),
  analyzeSentiment: jest.fn(),
  recognizePatterns: jest.fn(),
  getFundamentalAnalysis: jest.fn(),
  getKlines: jest.fn(),
  getTechnicalIndicators: jest.fn(),
  getSentimentHistory: jest.fn(),
  getIndustryComparison: jest.fn(),
  getRiskMetrics: jest.fn(),
  getCorrelationAnalysis: jest.fn(),
  getEventSummary: jest.fn(),
}));

jest.mock('../components/SkeletonLoaders', () => ({
  MarketAnalysisSkeleton: () => <div>loading</div>,
}));

jest.mock('../components/AIPredictionPanel', () => () => <div>AI</div>);
jest.mock('../components/CandlestickChart', () => () => <div>Chart</div>);

jest.mock('recharts', () => {
  const Mock = () => null;

  return {
    Radar: Mock,
    RadarChart: Mock,
    PolarGrid: Mock,
    PolarAngleAxis: Mock,
    PolarRadiusAxis: Mock,
    ComposedChart: Mock,
    ReferenceArea: Mock,
    ReferenceLine: Mock,
    Scatter: Mock,
    ResponsiveContainer: Mock,
    Tooltip: Mock,
    BarChart: Mock,
    Bar: Mock,
    XAxis: Mock,
    YAxis: Mock,
    Cell: Mock,
    CartesianGrid: Mock,
    Line: Mock,
    LineChart: Mock,
  };
});

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;

  return {
    RiseOutlined: MockIcon,
    FallOutlined: MockIcon,
    WarningOutlined: MockIcon,
    RadarChartOutlined: MockIcon,
    BarChartOutlined: MockIcon,
    ThunderboltOutlined: MockIcon,
    RobotOutlined: MockIcon,
    SolutionOutlined: MockIcon,
    InfoCircleOutlined: MockIcon,
    ExperimentOutlined: MockIcon,
    FundOutlined: MockIcon,
    LineChartOutlined: MockIcon,
    BankOutlined: MockIcon,
    CalendarOutlined: MockIcon,
    DollarCircleOutlined: MockIcon,
    NotificationOutlined: MockIcon,
    DashboardOutlined: MockIcon,
    ReloadOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  const passthrough = ({ children }) => <div>{children}</div>;
  const Card = ({ title, children, extra }) => (
    <section>
      {title ? <div>{title}</div> : null}
      {extra ? <div>{extra}</div> : null}
      {children}
    </section>
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
  const Statistic = ({ title, value, formatter, prefix, suffix }) => (
    <div>
      <span>{title}</span>
      <span>{prefix}{formatter ? formatter(value) : value}{suffix}</span>
    </div>
  );
  const Search = () => null;
  const RadioGroup = ({ children }) => <div>{children}</div>;
  const RadioButton = ({ children }) => <button type="button">{children}</button>;
  const Empty = ({ description }) => <div>{description || 'empty'}</div>;
  Empty.PRESENTED_IMAGE_SIMPLE = 'simple';

  return {
    Card,
    Input: { Search },
    Tabs,
    Row: passthrough,
    Col: passthrough,
    Tag: ({ children }) => <span>{children}</span>,
    List: ({ dataSource = [], renderItem }) => <div>{dataSource.map((item, index) => <div key={index}>{renderItem(item)}</div>)}</div>,
    Typography: {
      Title: ({ children }) => <div>{children}</div>,
      Text: ({ children }) => <span>{children}</span>,
    },
    Progress: () => <div>progress</div>,
    Alert: ({ message, description }) => <div>{message}{description}</div>,
    Space: passthrough,
    Table: () => <div>table</div>,
    Statistic,
    Empty,
    Divider: () => <hr />,
    Radio: {
      Group: RadioGroup,
      Button: RadioButton,
    },
    Spin: () => <div>spin</div>,
    Popover: passthrough,
    Tooltip: passthrough,
  };
});

const overviewPayload = {
  overall_score: 82,
  recommendation: '持有',
  confidence: 'MEDIUM',
  scores: {
    trend: 75,
    volume: 70,
    sentiment: 65,
    technical: 68,
  },
  key_signals: [],
  indicators: {
    rsi: { value: 55, status: 'neutral', signal: '中性' },
    macd: { value: 1.23, status: 'bullish', trend: '向上' },
    bollinger: { bandwidth: 12.5, position: 'neutral', signal: '平稳' },
  },
  summary: {
    score: 82,
  },
};

describe('MarketAnalysis cache behavior', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getAnalysisOverview.mockResolvedValue(overviewPayload);
  });

  afterEach(() => {
    cleanup();
  });

  test('reuses cached overview data when reopening the same symbol and interval', async () => {
    const view = render(<MarketAnalysis symbol="AAPL" embedMode />);

    await waitFor(() => {
      expect(getAnalysisOverview).toHaveBeenCalledTimes(1);
    });
    expect(getAnalysisOverview).toHaveBeenCalledWith('AAPL', '1d');
    await waitFor(() => {
      expect(screen.getAllByText(/数据来源 实时拉取|数据来源：实时拉取/).length).toBeGreaterThan(0);
    });

    view.unmount();

    render(<MarketAnalysis symbol="AAPL" embedMode />);

    await waitFor(() => {
      expect(getAnalysisOverview).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/数据来源 缓存命中|数据来源：缓存命中/).length).toBeGreaterThan(0);
    });
  });

  test('refresh action bypasses cached overview data', async () => {
    render(<MarketAnalysis symbol="MSFT" embedMode />);

    await waitFor(() => {
      expect(getAnalysisOverview).toHaveBeenCalledTimes(1);
    });
    expect(getAnalysisOverview).toHaveBeenCalledWith('MSFT', '1d');

    getAnalysisOverview.mockResolvedValueOnce({
      ...overviewPayload,
      overall_score: 88,
      summary: { score: 88 },
    });

    fireEvent.click(screen.getByRole('button', { name: /刷新分析/ }));

    await waitFor(() => {
      expect(getAnalysisOverview).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/数据来源 实时拉取|数据来源：实时拉取/).length).toBeGreaterThan(0);
    });
  });
});
