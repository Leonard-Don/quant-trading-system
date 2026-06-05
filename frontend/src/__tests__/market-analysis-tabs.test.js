/**
 * Characterization tests for MarketAnalysis tab wiring.
 *
 * These lock down the externally-observable contract before the
 * god-component is decomposed into per-tab child components:
 *   - the component renders without crashing
 *   - switching to a tab triggers exactly its expected lazy API call
 *   - a key field from each tab's payload renders
 *
 * They intentionally drive the public surface only (props + tab clicks +
 * the mocked api module), so they survive any internal restructuring as
 * long as behavior is preserved.
 */
import { render, waitFor, cleanup, fireEvent, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

import MarketAnalysis, { __TEST_ONLY__ } from '../components/MarketAnalysis';
import {
  getAnalysisOverview,
  analyzeTrend,
  analyzeVolumePrice,
  analyzeSentiment,
  recognizePatterns,
  getFundamentalAnalysis,
  getKlines,
  getTechnicalIndicators,
  getSentimentHistory,
  getIndustryComparison,
  getRiskMetrics,
  getCorrelationAnalysis,
  getEventSummary,
} from '../services/api';

vi.mock('../services/api', () => ({
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

vi.mock('@ant-design/icons', () => {
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

vi.mock('antd', () => {
  const passthrough = ({ children }) => <div>{children}</div>;
  const Card = ({ title, children, extra }) => (
    <section>
      {title ? <div>{title}</div> : null}
      {extra ? <div>{extra}</div> : null}
      {children}
    </section>
  );
  // A minimal Tabs that renders the active tab's children AND exposes
  // every tab label as a clickable button so the test can switch tabs.
  const Tabs = ({ items = [], activeKey, onChange }) => {
    let activeItem = null;
    for (const item of items) {
      if (item.key === activeKey) {
        activeItem = item;
        break;
      }
    }
    return (
      <div>
        <div>
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              disabled={item.disabled}
              onClick={() => onChange && onChange(item.key)}
            >
              {`tab:${item.key}`}
            </button>
          ))}
        </div>
        <div>{Reflect.get(activeItem || {}, 'children')}</div>
      </div>
    );
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
  const Table = ({ dataSource = [], columns = [] }) => (
    <table>
      <tbody>
        {dataSource.map((row, ri) => (
          <tr key={ri}>
            {columns.map((col, ci) => (
              <td key={ci}>{col.render ? col.render(row[col.dataIndex], row) : row[col.dataIndex]}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
  const List = ({ dataSource = [], renderItem }) => (
    <div>{dataSource.map((item, index) => <div key={index}>{renderItem ? renderItem(item, index) : null}</div>)}</div>
  );
  List.Item = ({ children }) => <div>{children}</div>;
  List.Item.Meta = ({ avatar, title, description }) => (
    <div>{avatar}{title}{description}</div>
  );

  return {
    Card,
    Input: { Search },
    Tabs,
    Row: passthrough,
    Col: passthrough,
    Tag: ({ children }) => <span>{children}</span>,
    List,
    Typography: {
      Title: ({ children }) => <div>{children}</div>,
      Text: ({ children }) => <span>{children}</span>,
    },
    Progress: () => <div>progress</div>,
    Alert: ({ message, description }) => <div>{message}{description}</div>,
    Space: passthrough,
    Table,
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
  scores: { trend: 75, volume: 70, sentiment: 65, technical: 68 },
  key_signals: [{ type: '趋势', importance: 'high', signal: '均线多头排列' }],
  summary: { score: 82 },
  // No `indicators` field -> forces a lazy getTechnicalIndicators call.
};

const clickTab = (key) => fireEvent.click(screen.getByRole('button', { name: `tab:${key}` }));

describe('MarketAnalysis tab wiring (characterization)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __TEST_ONLY__.clearAnalysisResponseCache();
    getAnalysisOverview.mockResolvedValue(overviewPayload);
    getTechnicalIndicators.mockResolvedValue({
      rsi: { value: 55, status: 'neutral', signal: '中性' },
      macd: { value: 1.23, status: 'bullish', trend: '向上' },
      bollinger: { bandwidth: 12.5, position: 'neutral', signal: '平稳' },
    });
    getEventSummary.mockResolvedValue({ earnings: null, dividends: null, news: [] });
    analyzeTrend.mockResolvedValue({
      trend_analysis: { multi_timeframe: {}, support_levels: [11.1], resistance_levels: [22.2] },
    });
    analyzeVolumePrice.mockResolvedValue({
      volume_analysis: {
        volume_trend: { trend: 'expanding', direction: 'expanding', volume_ratio: 1.5 },
        money_flow: { mfi: 60, status: 'inflow' },
        volume_patterns: { patterns: [] },
        obv_analysis: { obv_trend: 'bullish', obv_change_20d: 0.1 },
      },
    });
    analyzeSentiment.mockResolvedValue({
      sentiment_analysis: {
        fear_greed_index: 42,
        overall_sentiment: 'neutral',
        volatility_sentiment: {},
        risk_level: 'medium',
      },
    });
    getSentimentHistory.mockResolvedValue({ history: [] });
    recognizePatterns.mockResolvedValue({ pattern_analysis: { candlestick_patterns: [], chart_patterns: [] } });
    getKlines.mockResolvedValue({ klines: [] });
    getFundamentalAnalysis.mockResolvedValue({
      fundamental_analysis: {
        metrics: { pe_ratio: 18.5, market_cap: 1e9 },
        valuation: { status: 'fair_value', score: 50 },
        financial_health: { status: 'healthy', score: 70 },
        growth: { status: 'moderate', score: 50 },
        summary: '基本面稳健',
      },
    });
    getIndustryComparison.mockResolvedValue({
      target: { symbol: 'AAPL', pe_rank: 1, growth_rank: 2 },
      peers: [],
      industry_avg: { pe_ratio: 20 },
      industry: '半导体',
      sector: '科技',
    });
    getRiskMetrics.mockResolvedValue({
      risk_level: 'medium',
      risk_description: '中等风险',
      var_95: -3.2,
      var_99: -5.1,
      max_drawdown: -12,
      annual_volatility: 25,
      sharpe_ratio: 1.2,
      sortino_ratio: 1.5,
      annual_return: 8,
      beta: 1.1,
    });
    getCorrelationAnalysis.mockResolvedValue({
      symbols: ['AAPL'],
      correlation_matrix: [{ symbol1: 'AAPL', symbol2: 'AAPL', correlation: 1 }],
    });
  });

  afterEach(() => {
    cleanup();
    jest.restoreAllMocks();
  });

  const renderAndSettle = async () => {
    render(<MarketAnalysis symbol="AAPL" embedMode />);
    await waitFor(() => expect(getAnalysisOverview).toHaveBeenCalledTimes(1));
  };

  test('renders without crashing and fetches the overview on mount', async () => {
    await renderAndSettle();
    expect(getAnalysisOverview).toHaveBeenCalledWith('AAPL', '1d');
    // The overview payload omits embedded `indicators`, so the technical
    // snapshot is back-filled by a lazy getTechnicalIndicators call.
    await waitFor(() => expect(getTechnicalIndicators).toHaveBeenCalledWith('AAPL', '1d'));
    // A key overview field renders.
    expect(screen.getByText('均线多头排列')).toBeInTheDocument();
  });

  test('trend tab triggers analyzeTrend and renders support/resistance', async () => {
    await renderAndSettle();
    clickTab('trend');
    await waitFor(() => expect(analyzeTrend).toHaveBeenCalledWith('AAPL', '1d'));
    expect(analyzeVolumePrice).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText('11.1')).toBeInTheDocument());
  });

  test('volume tab triggers analyzeVolumePrice', async () => {
    await renderAndSettle();
    clickTab('volume');
    await waitFor(() => expect(analyzeVolumePrice).toHaveBeenCalledWith('AAPL', '1d'));
    expect(analyzeTrend).not.toHaveBeenCalled();
  });

  test('sentiment tab triggers analyzeSentiment and sentiment history', async () => {
    await renderAndSettle();
    clickTab('sentiment');
    await waitFor(() => expect(analyzeSentiment).toHaveBeenCalledWith('AAPL', '1d'));
    await waitFor(() => expect(getSentimentHistory).toHaveBeenCalledWith('AAPL', 30));
  });

  test('pattern tab triggers recognizePatterns + getKlines together', async () => {
    await renderAndSettle();
    clickTab('pattern');
    await waitFor(() => expect(recognizePatterns).toHaveBeenCalledWith('AAPL', '1d'));
    await waitFor(() => expect(getKlines).toHaveBeenCalledWith('AAPL', '1d'));
  });

  test('fundamental tab triggers getFundamentalAnalysis and renders summary', async () => {
    await renderAndSettle();
    clickTab('fundamental');
    await waitFor(() => expect(getFundamentalAnalysis).toHaveBeenCalledWith('AAPL'));
    await waitFor(() => expect(screen.getByText((t) => t.includes('基本面稳健'))).toBeInTheDocument());
  });

  test('industry tab triggers getIndustryComparison', async () => {
    await renderAndSettle();
    clickTab('industry');
    await waitFor(() => expect(getIndustryComparison).toHaveBeenCalledWith('AAPL'));
  });

  test('risk tab triggers getRiskMetrics and renders risk description', async () => {
    await renderAndSettle();
    clickTab('risk');
    await waitFor(() => expect(getRiskMetrics).toHaveBeenCalledWith('AAPL', '1d'));
    await waitFor(() => expect(screen.getByText((t) => t.includes('中等风险'))).toBeInTheDocument());
  });

  test('correlation tab triggers getCorrelationAnalysis', async () => {
    await renderAndSettle();
    clickTab('correlation');
    await waitFor(() => expect(getCorrelationAnalysis).toHaveBeenCalled());
  });

  test('prediction tab renders the lazy AI panel without a data fetch', async () => {
    await renderAndSettle();
    clickTab('prediction');
    await waitFor(() => expect(screen.getByText('AI')).toBeInTheDocument());
  });
});
