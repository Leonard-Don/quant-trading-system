import { render, waitFor, cleanup, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

import MarketAnalysis, {
  ANALYSIS_CACHE_MAX_ENTRIES,
  ANALYSIS_CACHE_TTL_MS,
  __TEST_ONLY__,
} from '../components/MarketAnalysis';
import { getAnalysisOverview } from '../services/api';

vi.mock('../services/api', () => ({
  getAnalysisOverview: vi.fn(),
  analyzeTrend: vi.fn(),
  analyzeVolumePrice: vi.fn(),
  analyzeSentiment: vi.fn(),
  recognizePatterns: vi.fn(),
  getFundamentalAnalysis: vi.fn(),
  getKlines: vi.fn(),
  getTechnicalIndicators: vi.fn(),
  getSentimentHistory: vi.fn(),
  getIndustryComparison: vi.fn(),
  getRiskMetrics: vi.fn(),
  getCorrelationAnalysis: vi.fn(),
  getEventSummary: vi.fn(),
}));

vi.mock('../components/SkeletonLoaders', () => ({
  MarketAnalysisSkeleton: () => <div>loading</div>,
}));

vi.mock('../components/AIPredictionPanel', () => ({ default: () => <div>AI</div> }));
vi.mock('../components/CandlestickChart', () => ({ default: () => <div>Chart</div> }));

vi.mock('recharts', () => {
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


vi.mock('antd', () => {
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
    vi.clearAllMocks();
    __TEST_ONLY__.clearAnalysisResponseCache();
    getAnalysisOverview.mockResolvedValue(overviewPayload);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
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

  test('expires cached entries once ttl has elapsed', async () => {
    const nowSpy = vi.spyOn(Date, 'now');
    nowSpy.mockReturnValue(1_000);

    const view = render(<MarketAnalysis symbol="NVDA" embedMode />);

    await waitFor(() => {
      expect(getAnalysisOverview).toHaveBeenCalledTimes(1);
    });

    view.unmount();

    nowSpy.mockReturnValue(1_000 + ANALYSIS_CACHE_TTL_MS + 1);
    render(<MarketAnalysis symbol="NVDA" embedMode />);

    await waitFor(() => {
      expect(getAnalysisOverview).toHaveBeenCalledTimes(2);
    });

    nowSpy.mockRestore();
  });
});

describe('MarketAnalysis internal cache limits', () => {
  beforeEach(() => {
    __TEST_ONLY__.clearAnalysisResponseCache();
  });

  test('evicts the oldest cache entry when size exceeds the max limit', () => {
    for (let index = 0; index < ANALYSIS_CACHE_MAX_ENTRIES; index += 1) {
      __TEST_ONLY__.writeAnalysisCache(`overview|SYM${index}|1d`, { score: index }, index + 1);
    }

    __TEST_ONLY__.writeAnalysisCache('overview|OVERFLOW|1d', { score: 999 }, ANALYSIS_CACHE_MAX_ENTRIES + 1);

    expect(__TEST_ONLY__.getAnalysisCacheSize()).toBe(ANALYSIS_CACHE_MAX_ENTRIES);
    expect(__TEST_ONLY__.readAnalysisCacheEntry('overview|SYM0|1d', ANALYSIS_CACHE_MAX_ENTRIES + 2)).toBeNull();
    expect(__TEST_ONLY__.readAnalysisCacheEntry('overview|OVERFLOW|1d', ANALYSIS_CACHE_MAX_ENTRIES + 2)).toEqual({
      data: { score: 999 },
      cachedAt: ANALYSIS_CACHE_MAX_ENTRIES + 1,
    });
  });

  test('keeps recently read cache entries hot under lru eviction', () => {
    for (let index = 0; index < ANALYSIS_CACHE_MAX_ENTRIES; index += 1) {
      __TEST_ONLY__.writeAnalysisCache(`overview|SYM${index}|1d`, { score: index }, index + 1);
    }

    expect(__TEST_ONLY__.readAnalysisCacheEntry('overview|SYM0|1d', ANALYSIS_CACHE_MAX_ENTRIES + 1)).toEqual({
      data: { score: 0 },
      cachedAt: 1,
    });

    __TEST_ONLY__.writeAnalysisCache('overview|OVERFLOW|1d', { score: 999 }, ANALYSIS_CACHE_MAX_ENTRIES + 2);

    expect(__TEST_ONLY__.readAnalysisCacheEntry('overview|SYM0|1d', ANALYSIS_CACHE_MAX_ENTRIES + 3)).toEqual({
      data: { score: 0 },
      cachedAt: 1,
    });
    expect(__TEST_ONLY__.readAnalysisCacheEntry('overview|SYM1|1d', ANALYSIS_CACHE_MAX_ENTRIES + 3)).toBeNull();
  });
});
