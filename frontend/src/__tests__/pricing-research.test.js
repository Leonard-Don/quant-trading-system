import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  buildPricingActionPosture,
  buildRecentPricingResearchEntries,
  mergePricingSuggestions,
  parsePricingUniverseInput,
  resolveAnalysisSymbol,
} from '../utils/pricingResearch';
import PricingResearch, { DriversCard, FactorModelCard, GapOverview, ImplicationsCard, PeopleLayerCard, StructuralDecayCard, ValuationCard } from '../components/PricingResearch';
import { MacroMispricingThesisCard } from '../components/pricing/PricingInsightCards';
import usePricingResearchData from '../components/pricing/usePricingResearchData';
import {
  getGapAnalysis,
  getPricingGapHistory,
  getPricingPeerComparison,
  getResearchTasks,
  getPricingSymbolSuggestions,
} from '../services/api';
import {
  buildAppUrl,
  readResearchContext,
} from '../utils/researchContext';

jest.mock('recharts', () => {
  const React = require('react');
  const passthrough = ({ children }) => <div>{children}</div>;
  return {
    ResponsiveContainer: passthrough,
    RadarChart: passthrough,
    PolarGrid: passthrough,
    PolarAngleAxis: passthrough,
    PolarRadiusAxis: passthrough,
    Radar: passthrough,
    BarChart: passthrough,
    Bar: passthrough,
    CartesianGrid: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
    Tooltip: passthrough,
    ReferenceLine: passthrough,
    Cell: passthrough,
    LineChart: passthrough,
    Line: passthrough,
    AreaChart: passthrough,
    Area: passthrough,
    Legend: passthrough,
    ComposedChart: passthrough,
  };
});

jest.mock('antd', () => {
  const React = require('react');
  const actual = jest.requireActual('antd');

  const MockTable = ({ dataSource = [], columns = [] }) => (
    <table data-testid="mock-antd-table">
      <tbody>
        {dataSource.map((row, rowIndex) => (
          <tr key={row.name || row.key || rowIndex}>
            {columns.map((column, columnIndex) => {
              const dataIndex = Array.isArray(column.dataIndex)
                ? column.dataIndex
                : column.dataIndex
                  ? [column.dataIndex]
                  : [];
              const value = dataIndex.reduce((current, key) => current?.[key], row);
              const content = column.render ? column.render(value, row, rowIndex) : value;
              return <td key={`${column.key || column.dataIndex || columnIndex}`}>{content}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );

  const MockDescriptions = ({ children }) => <div data-testid="mock-antd-descriptions">{children}</div>;
  MockDescriptions.Item = ({ label, children }) => (
    <div data-testid="mock-antd-descriptions-item">
      <span>{label}</span>
      <span>{children}</span>
    </div>
  );

  const MockRow = ({ children, ...props }) => <div {...props}>{children}</div>;
  const MockCol = ({ children, ...props }) => <div {...props}>{children}</div>;

  return {
    ...actual,
    Descriptions: MockDescriptions,
    Row: MockRow,
    Col: MockCol,
    Table: MockTable,
  };
});

const mockNavigateByResearchAction = jest.fn();

jest.mock('../utils/researchContext', () => ({
  buildAppUrl: jest.fn(() => '/?view=pricing'),
  formatResearchSource: jest.fn((value) => value || ''),
  navigateByResearchAction: (...args) => mockNavigateByResearchAction(...args),
  readResearchContext: jest.fn(() => ({})),
}));

jest.mock('../services/api', () => ({
  addResearchTaskSnapshot: jest.fn(),
  createResearchTask: jest.fn(),
  getGapAnalysis: jest.fn(),
  getPricingGapHistory: jest.fn(() => Promise.resolve({ history: [] })),
  getPricingPeerComparison: jest.fn(() => Promise.resolve({ peers: [] })),
  getResearchTasks: jest.fn(() => Promise.resolve({ data: [] })),
  getPricingSymbolSuggestions: jest.fn(() => Promise.resolve({ data: [] })),
  getValuationSensitivityAnalysis: jest.fn(),
}));

const mockMessageApi = {
  success: jest.fn(),
  info: jest.fn(),
  warning: jest.fn(),
  error: jest.fn(),
  loading: jest.fn(),
  open: jest.fn(),
  destroy: jest.fn(),
};

jest.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
}));

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
});

beforeEach(() => {
  jest.clearAllMocks();
  readResearchContext.mockReturnValue({});
  getGapAnalysis.mockResolvedValue({});
  getPricingGapHistory.mockResolvedValue({ history: [] });
  getPricingPeerComparison.mockResolvedValue({ peers: [] });
  getResearchTasks.mockResolvedValue({ data: [] });
  getPricingSymbolSuggestions.mockResolvedValue({ data: [] });
});

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

function PricingResearchDataHarness() {
  usePricingResearchData({ navigateByResearchAction: mockNavigateByResearchAction });
  return <div data-testid="pricing-research-data-harness">harness</div>;
}

describe('pricingResearch symbol normalization', () => {
  it('uses the fallback symbol when button click passes an event object', () => {
    const syntheticEvent = { type: 'click', target: {} };

    expect(resolveAnalysisSymbol(syntheticEvent, ' aapl ')).toBe('AAPL');
  });

  it('prefers an explicit override symbol when provided', () => {
    expect(resolveAnalysisSymbol(' msft ', 'aapl')).toBe('MSFT');
  });

  it('parses a pricing universe with dedupe and mixed separators', () => {
    expect(parsePricingUniverseInput(' aapl, msft\nNVDA  aapl；tsla | meta ')).toEqual([
      'AAPL',
      'MSFT',
      'NVDA',
      'TSLA',
      'META',
    ]);
  });

  it('merges recent research symbols ahead of api suggestions', () => {
    expect(mergePricingSuggestions(
      [
        { symbol: 'AAPL', name: 'Apple', group: 'Mega Cap Tech', market: 'US' },
        { symbol: 'MSFT', name: 'Microsoft', group: 'Mega Cap Tech', market: 'US' },
      ],
      ['MSFT', 'NVDA', 'msft'],
      '',
    )).toEqual([
      {
        symbol: 'MSFT',
        name: 'Microsoft',
        group: 'Mega Cap Tech',
        market: 'US',
        recent: true,
        task_id: '',
        primary_view: '',
        confidence: '',
        confidence_label: '',
        factor_alignment_status: '',
        factor_alignment_label: '',
        primary_driver: '',
        primary_driver_reason: '',
        period: '',
        headline: '',
        summary: '',
      },
      {
        symbol: 'NVDA',
        name: '',
        group: '最近研究',
        market: '',
        recent: true,
        task_id: '',
        primary_view: '',
        confidence: '',
        confidence_label: '',
        factor_alignment_status: '',
        factor_alignment_label: '',
        primary_driver: '',
        primary_driver_reason: '',
        period: '',
        headline: '',
        summary: '',
      },
      { symbol: 'AAPL', name: 'Apple', group: 'Mega Cap Tech', market: 'US', recent: false },
    ]);
  });

  it('builds recent research entries from workbench pricing tasks', () => {
    expect(buildRecentPricingResearchEntries([
      {
        id: 'rw_123',
        symbol: 'aapl',
        updated_at: '2026-04-01T10:00:00',
        snapshot: {
          headline: 'AAPL 定价研究剧本',
          summary: 'Apple 当前偏向低估。',
          payload: {
            period: '2y',
            implications: {
              primary_view: '低估',
              confidence: 'high',
              factor_alignment: {
                status: 'aligned',
                label: '同向',
              },
            },
            deviation_drivers: {
              primary_driver: {
                factor: 'P/E 倍数法折价',
                ranking_reason: '相对行业估值折价最显著。',
              },
            },
          },
        },
      },
      {
        symbol: 'AAPL',
        snapshot: { payload: {} },
      },
    ])).toEqual([
      {
        symbol: 'AAPL',
        task_id: 'rw_123',
        title: '',
        headline: 'AAPL 定价研究剧本',
        summary: 'Apple 当前偏向低估。',
        period: '2y',
        primary_view: '低估',
        confidence: 'high',
        confidence_label: '高',
        factor_alignment_status: 'aligned',
        factor_alignment_label: '同向',
        primary_driver: 'P/E 倍数法折价',
        primary_driver_reason: '相对行业估值折价最显著。',
        recent: true,
        updated_at: '2026-04-01T10:00:00',
      },
    ]);
  });

  it('builds a deploy posture when pricing gap and evidence are both strong', () => {
    expect(buildPricingActionPosture({
      gapPct: -18.4,
      confidenceScore: 0.81,
      alignmentStatus: 'aligned',
      primaryView: '低估',
      riskLevel: 'medium',
    })).toMatchObject({
      label: 'deploy',
      posture: '可推进到执行清单',
    });
  });

  it('renders a pricing action posture inside implications card', () => {
    render(
      <ImplicationsCard
        data={{
          primary_view: '低估',
          risk_level: 'medium',
          confidence: 'high',
          confidence_score: 0.82,
          factor_alignment: {
            status: 'aligned',
            label: '证据一致',
            summary: '估值结论与因子方向一致。',
          },
          insights: [],
        }}
        valuation={{ current_price_source: 'live' }}
        factorModel={{ data_points: 252, period: '2y' }}
        gapAnalysis={{ gap_pct: -16.8 }}
      />,
    );

    expect(screen.getByText('当前可以推进到优先买入清单')).toBeTruthy();
    expect(screen.getAllByText(/推进到优先买入清单/i).length).toBeGreaterThan(0);
  });

  it('renders recent research shortcuts and opens the linked workbench task', async () => {
    getResearchTasks.mockResolvedValue({
      data: [
        {
          id: 'rw_123',
          symbol: 'AAPL',
          updated_at: '2026-04-01T10:00:00',
          snapshot: {
            headline: 'AAPL 定价研究剧本',
            summary: 'Apple 当前偏向低估。',
            payload: {
              period: '2y',
              implications: {
                primary_view: '低估',
                confidence: 'high',
                factor_alignment: {
                  status: 'aligned',
                  label: '同向',
                },
              },
              deviation_drivers: {
                primary_driver: {
                  factor: 'P/E 倍数法折价',
                },
              },
            },
          },
        },
      ],
    });

    render(<PricingResearch />);

    await screen.findByTestId('pricing-recent-research-shortcuts');
    expect(screen.getAllByText('同向').length).toBeGreaterThan(0);
    expect(screen.getByText('主驱动 P/E 倍数法折价')).toBeTruthy();
    fireEvent.click(screen.getByText('AAPL 定价研究剧本'));

    expect(mockNavigateByResearchAction).toHaveBeenCalledWith({
      target: 'workbench',
      type: 'pricing',
      sourceFilter: 'research_workbench',
      reason: 'recent_pricing_search',
      taskId: 'rw_123',
    });
  });

  it('preserves workbench view context when syncing pricing urls', async () => {
    readResearchContext.mockReturnValue({
      view: 'pricing',
      symbol: 'AAPL',
      period: '1y',
      source: 'pricing_playbook',
      workbenchRefresh: 'high',
      workbenchType: 'pricing',
      workbenchSource: 'pricing_playbook',
      workbenchReason: 'priority_escalated',
      workbenchSnapshotView: 'filtered',
      workbenchSnapshotFingerprint: 'wv_pricing_focus',
      workbenchSnapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
      workbenchKeyword: 'hedge',
      workbenchQueueMode: 'pricing',
      workbenchQueueAction: 'next_same_type',
      task: 'rw_123',
    });

    render(<PricingResearchDataHarness />);

    await waitFor(() => expect(buildAppUrl).toHaveBeenCalledWith(expect.objectContaining({
      view: 'pricing',
      symbol: 'AAPL',
      period: '1y',
      source: 'pricing_playbook',
      workbenchRefresh: 'high',
      workbenchType: 'pricing',
      workbenchSource: 'pricing_playbook',
      workbenchReason: 'priority_escalated',
      workbenchSnapshotView: 'filtered',
      workbenchSnapshotFingerprint: 'wv_pricing_focus',
      workbenchSnapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
      workbenchKeyword: 'hedge',
      workbenchQueueMode: 'pricing',
      workbenchQueueAction: 'next_same_type',
      task: 'rw_123',
    })));
  });

  it('returns to the next pricing workbench task from the research page', async () => {
    window.history.replaceState(
      null,
      '',
      '/?view=pricing&symbol=AAPL&period=1y&source=research_workbench&workbench_refresh=high&workbench_type=pricing&workbench_source=research_workbench&workbench_reason=priority_escalated&workbench_snapshot_view=filtered&workbench_snapshot_fingerprint=wv_pricing_focus&workbench_snapshot_summary=%E5%BF%AB%E9%80%9F%E8%A7%86%E5%9B%BE%EF%BC%9A%E8%87%AA%E5%8A%A8%E6%8E%92%E5%BA%8F%E5%8D%87%E6%A1%A3%20%C2%B7%20%E7%B1%BB%E5%9E%8B%EF%BC%9APricing&workbench_keyword=hedge&workbench_queue_mode=pricing&task=rw_123'
    );
    readResearchContext.mockReturnValue({
      view: 'pricing',
      symbol: 'AAPL',
      period: '1y',
      source: 'research_workbench',
      note: '从工作台继续复盘',
      workbenchRefresh: 'high',
      workbenchType: 'pricing',
      workbenchSource: 'research_workbench',
      workbenchReason: 'priority_escalated',
      workbenchSnapshotView: 'filtered',
      workbenchSnapshotFingerprint: 'wv_pricing_focus',
      workbenchSnapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
      workbenchKeyword: 'hedge',
      workbenchQueueMode: 'pricing',
      task: 'rw_123',
    });
    getGapAnalysis.mockResolvedValueOnce({
      symbol: 'AAPL',
      implications: {},
      deviation_drivers: {},
    });

    render(<PricingResearch />);

    const button = await screen.findByRole('button', { name: '回到工作台下一条 Pricing 任务' });
    fireEvent.click(button);

    expect(mockNavigateByResearchAction).toHaveBeenCalledWith(
      {
        target: 'workbench',
        refresh: 'high',
        type: 'pricing',
        sourceFilter: 'research_workbench',
        reason: 'priority_escalated',
        snapshotView: 'filtered',
        snapshotFingerprint: 'wv_pricing_focus',
        snapshotSummary: '快速视图：自动排序升档 · 类型：Pricing',
        keyword: 'hedge',
        queueMode: 'pricing',
        queueAction: 'next_same_type',
        taskId: 'rw_123',
      },
      expect.stringContaining('view=pricing')
    );
  });

  it('shows update snapshot when reopening an existing workbench pricing task', async () => {
    readResearchContext.mockReturnValue({
      view: 'pricing',
      symbol: 'AAPL',
      period: '1y',
      source: 'research_workbench',
      note: '从工作台继续复盘',
      workbenchQueueMode: 'pricing',
      task: 'rw_existing_pricing',
    });
    getGapAnalysis.mockResolvedValueOnce({
      symbol: 'AAPL',
      implications: {},
      deviation_drivers: {},
    });

    render(<PricingResearch />);

    await screen.findByRole('button', { name: '更新当前任务快照' });
  });

  it('renders DCF scenario analysis on the valuation card', () => {
    render(
      <ValuationCard
        data={{
          sector: 'Technology',
          fair_value: {
            mid: 104.0,
            low: 86.0,
            high: 121.0,
            method: 'DCF + 可比估值加权',
            range_basis: 'dcf_scenarios_and_multiples',
          },
          dcf: {
            intrinsic_value: 100,
            terminal_pct: 61.2,
            assumptions: { wacc: 0.082, initial_growth: 0.12 },
            premium_discount: 5.0,
            scenarios: [
              {
                name: 'bear',
                label: '悲观',
                intrinsic_value: 86,
                premium_discount: 16.3,
                assumptions: { wacc: 0.097, initial_growth: 0.08 },
              },
              {
                name: 'base',
                label: '基准',
                intrinsic_value: 100,
                premium_discount: 0,
                assumptions: { wacc: 0.082, initial_growth: 0.12 },
              },
              {
                name: 'bull',
                label: '乐观',
                intrinsic_value: 121,
                premium_discount: -9.1,
                assumptions: { wacc: 0.072, initial_growth: 0.16 },
              },
            ],
          },
          monte_carlo: {
            sample_count: 200,
            p10: 88,
            p50: 102,
            p90: 121,
            distribution: [
              { bucket: '(80,90]', count: 12 },
              { bucket: '(90,100]', count: 41 },
            ],
          },
          comparable: {
            fair_value: 108,
            methods: [
              { method: 'P/E 倍数法', fair_value: 108 },
              { method: 'EV/Revenue 倍数法', fair_value: 112 },
              { method: 'PEG 倍数法', fair_value: 106 },
            ],
          },
        }}
      />
    );

    expect(screen.getByText('DCF 情景分析')).toBeTruthy();
    expect(screen.getByText('Monte Carlo 估值分布')).toBeTruthy();
    expect(screen.getByText('悲观')).toBeTruthy();
    expect(screen.getByText('乐观')).toBeTruthy();
    expect(screen.getByText('区间依据: DCF 情景 + 可比倍数分布')).toBeTruthy();
    expect(screen.getByText('EV/Revenue 倍数法')).toBeTruthy();
    expect(screen.getByText('PEG 倍数法')).toBeTruthy();
  });

  it('renders a pricing thermometer inside gap overview', () => {
    render(
      <GapOverview
        data={{
          symbol: 'AAPL',
          valuation: { company_name: 'Apple', current_price_source: 'live' },
          gap_analysis: {
            current_price: 180,
            fair_value_mid: 150,
            fair_value_low: 130,
            fair_value_high: 170,
            gap_pct: 20,
            severity: 'high',
            severity_label: '显著偏离',
            direction: '溢价(高估)',
            in_fair_range: false,
          },
        }}
      />,
    );

    expect(screen.getByText('定价温度计')).toBeTruthy();
    expect(screen.getByText('偏热')).toBeTruthy();
  });

  it('renders factor residual diagnostics summary', () => {
    render(
      <FactorModelCard
        data={{
          period: '1y',
          data_points: 180,
          factor_source: {},
          five_factor_source: {},
          capm: {
            alpha_pct: 2.1,
            beta: 1.03,
            r_squared: 0.64,
            significance: { alpha_t_stat: 2.4, alpha_p_value: 0.018, beta_t_stat: 11.2 },
            residual_diagnostics: { durbin_watson: 1.88, autocorr_lag1: 0.12 },
            idiosyncratic_risk: 0.23,
            interpretation: { alpha: '存在正 alpha' },
          },
          fama_french: {
            alpha_pct: 1.8,
            factor_loadings: { market: 1.01, size: -0.12, value: 0.08 },
            r_squared: 0.7,
            significance: { alpha_p_value: 0.02, market_p_value: 0.0, size_p_value: 0.11, value_p_value: 0.22 },
            residual_diagnostics: { durbin_watson: 1.95, autocorr_lag1: 0.05 },
            interpretation: { size: '规模暴露有限' },
          },
          fama_french_five_factor: {
            alpha_pct: 1.2,
            factor_loadings: { profitability: 0.18, investment: -0.09 },
            r_squared: 0.72,
            significance: { profitability_p_value: 0.03, investment_p_value: 0.08 },
            residual_diagnostics: { durbin_watson: 2.01, autocorr_lag1: -0.02 },
            interpretation: { profitability: '盈利能力因子偏强' },
          },
          attribution: { components: { market: { label: '市场贡献', pct: 7.2 } } },
        }}
      />,
    );

    expect(screen.getByText('残差诊断')).toBeTruthy();
    expect(screen.getByText('CAPM 特质波动 23.0%')).toBeTruthy();
    expect(screen.getByText('FF3 DW=1.95')).toBeTruthy();
  });

  it('renders confidence breakdown and trade setup on the implications card', () => {
    render(
      <ImplicationsCard
        data={{
          primary_view: '低估',
          risk_level: 'medium',
          confidence: 'high',
          confidence_score: 0.82,
          confidence_reasons: ['样本窗口偏短'],
          confidence_breakdown: [
            { key: 'gap_anchor', label: '价格偏差锚点', delta: 0.15, status: 'positive', detail: '当前价格和公允价值中枢都可用' },
            { key: 'factor_alignment', label: '证据共振', delta: -0.12, status: 'negative', detail: '二级因子表现与估值结论方向不一致' },
          ],
          trade_setup: {
            stance: '关注做多修复',
            target_price: 118.5,
            stop_loss: 92.4,
            risk_reward: 1.8,
            upside_pct: 12.3,
            stretch_upside_pct: 18.6,
            risk_pct: 6.8,
            quality_note: '因子与估值同向，情景可信度更高。',
            summary: '若按低估回归处理，可观察价格向公允价值中枢修复的空间。',
          },
          factor_alignment: { status: 'aligned', label: '同向', summary: '因子信号与低估判断同向，证据互相印证' },
          insights: ['存在中度低估，可能存在交易机会'],
        }}
        valuation={{ current_price_source: 'live' }}
        factorModel={{ data_points: 180, period: '1y' }}
      />
    );

    expect(screen.getByText('置信度拆解')).toBeTruthy();
    expect(screen.getByText('交易情景')).toBeTruthy();
    expect(screen.getByText('目标价 $118.50')).toBeTruthy();
    expect(screen.getByText('盈亏比 1.80')).toBeTruthy();
  });

  it('renders driver contribution chart context and primary driver summary', () => {
    render(
      <DriversCard
        data={{
          primary_driver: {
            factor: 'P/B 倍数法溢价',
            impact: 'overvalued',
            signal_strength: 1.9,
            ranking_reason: '相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源',
          },
          drivers: [
            {
              factor: 'P/B 倍数法溢价',
              impact: 'overvalued',
              signal_strength: 1.9,
              rank: 1,
              description: '当前 P/B 为 4.8，行业基准为 2.4，溢价 100%',
              ranking_reason: '相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源',
            },
            {
              factor: '低系统性风险',
              impact: 'defensive',
              signal_strength: 1.2,
              rank: 2,
              description: 'Beta=0.65，防御性定价可能享受安全溢价',
              ranking_reason: 'Beta 明显低于市场中性水平，说明防御属性带来的安全溢价是当前定价偏差的核心来源',
            },
          ],
        }}
      />
    );

    expect(screen.getByText('主驱动')).toBeTruthy();
    expect(screen.getByText('驱动瀑布视图')).toBeTruthy();
    expect(screen.getAllByText('P/B 倍数法溢价').length).toBeGreaterThan(0);
    expect(screen.getAllByText('判断依据：相对行业基准的估值溢价最显著，说明倍数扩张是当前定价偏差的主要来源').length).toBeGreaterThan(0);
  });

  it('renders people layer risk and management context', () => {
    render(
      <PeopleLayerCard
        data={{
          stance: 'fragile',
          risk_level: 'high',
          confidence: 0.71,
          summary: '阿里巴巴的人事层结论偏脆弱，组织质量 0.38 / 脆弱度 0.67。',
          flags: ['财务与平台治理议题占比高', '技术组织被商业目标稀释的风险偏高'],
          notes: ['内部人交易偏减持，说明管理层对当前定价的安全边际未给出强背书。'],
          executive_profile: {
            technical_authority_score: 0.34,
            capital_markets_pressure: 0.62,
            leadership_balance: '商业/财务主导',
            average_tenure_years: 4.8,
          },
          insider_flow: {
            label: '内部人减持偏谨慎',
            net_action: 'selling',
            transaction_count: 3,
            summary: '阿里巴巴 近端内部人交易呈 selling，净额 -18.0M 美元。',
          },
          hiring_signal: {
            signal: 'bearish',
            dilution_ratio: 1.72,
            tech_ratio: 0.29,
            alert_message: '⚠️ 阿里巴巴 技术高管稀释度 1.72 超过警戒线 1.5',
          },
        }}
      />,
    );

    expect(screen.getByText('人的维度 / 治理折扣')).toBeTruthy();
    expect(screen.getByText('组织姿态 脆弱')).toBeTruthy();
    expect(screen.getByText('组织风险 high')).toBeTruthy();
    expect(screen.getByText('招聘稀释度')).toBeTruthy();
    expect(screen.getByText('内部人减持偏谨慎')).toBeTruthy();
  });

  it('renders structural decay score and evidence breakdown', () => {
    render(
      <StructuralDecayCard
        data={{
          score: 0.78,
          label: '结构性衰败警报',
          action: 'structural_short',
          reversibility: '低',
          horizon: '长期',
          dominant_failure_label: '组织与治理稀释',
          summary: '结构性衰败警报，主导失效模式偏向 组织与治理稀释。',
          evidence: ['人的维度已进入高脆弱区间', '招聘稀释度 1.72', '内部人交易偏减持'],
          components: [
            { key: 'people_fragility', label: '组织脆弱度', delta: 0.28, status: 'positive', detail: '人的维度已进入高脆弱区间' },
            { key: 'hiring_dilution', label: '技术稀释', delta: 0.14, status: 'positive', detail: '招聘稀释度 1.72，组织重心向非技术侧偏移' },
          ],
        }}
      />,
    );

    expect(screen.getByText('Structural Decay')).toBeTruthy();
    expect(screen.getByText('结构性衰败警报')).toBeTruthy();
    expect(screen.getByText('主导失效模式')).toBeTruthy();
    expect(screen.getByText('组织与治理稀释')).toBeTruthy();
    expect(screen.getByText('衰败拆解')).toBeTruthy();
  });

  it('renders macro mispricing thesis with legs and kill conditions', () => {
    render(
      <MacroMispricingThesisCard
        data={{
          thesis_type: 'relative_short',
          stance: '结构性做空',
          score: 0.81,
          horizon: '中长期',
          people_risk: 'high',
          summary: 'BABA 更像组织与叙事共同劣化导致的长期错误定价。',
          primary_leg: {
            symbol: 'BABA',
            side: 'short',
            role: 'primary',
            rationale: '组织与治理稀释',
          },
          hedge_leg: {
            symbol: 'KWEB',
            side: 'long',
            role: 'hedge',
            rationale: '对冲中国互联网 Beta',
          },
          target_price: 82.5,
          risk_boundary: 108.0,
          risk_reward: 2.3,
          kill_conditions: [
            '人的维度风险从 high/fragile 明显修复到 medium 或以下',
            '结构性衰败评分回落到 0.50 以下',
          ],
          trade_legs: [
            { symbol: 'BABA', side: 'short', role: 'core_expression', weight: 0.5, thesis: '组织与治理稀释' },
            { symbol: 'KWEB', side: 'long', role: 'beta_hedge', weight: 0.3, thesis: '对冲中国互联网 Beta' },
            { symbol: 'GLD', side: 'long', role: 'stress_hedge', weight: 0.2, thesis: '保留系统性冲击防御' },
          ],
          execution_notes: ['优先表达 idiosyncratic 错价，避免把系统性方向误当 thesis 收益来源'],
        }}
      />,
    );

    expect(screen.getByText('Macro Mispricing Thesis')).toBeTruthy();
    expect(screen.getByText('结构性做空')).toBeTruthy();
    expect(screen.getByText('主腿')).toBeTruthy();
    expect(screen.getByText('BABA · short')).toBeTruthy();
    expect(screen.getByText('KWEB · long')).toBeTruthy();
    expect(screen.getByText('组合腿')).toBeTruthy();
    expect(screen.getByText('GLD')).toBeTruthy();
    expect(screen.getByText('执行备注')).toBeTruthy();
    expect(screen.getByText('Kill Conditions')).toBeTruthy();
    expect(screen.getByText('结构性衰败评分回落到 0.50 以下')).toBeTruthy();
  });
});
