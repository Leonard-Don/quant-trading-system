import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import LeaderStockPanel, { __resetLeaderBoardClientCacheForTests } from '../components/LeaderStockPanel';
import {
  getLeaderBoards,
  getLeaderStocks,
  getLeaderDetail,
  getIndustryTrend,
} from '../services/api';

const mockMessageApi = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
};

const buildLeaderBoardCacheKey = (topN, topIndustries, perIndustry) => (
  `industry:leader-boards:v1:${topN}:${topIndustries}:${perIndustry}`
);

const buildLeaderRecord = (overrides = {}) => ({
  symbol: '600000',
  name: '缓存龙头',
  industry: '银行',
  score_type: 'core',
  global_rank: 1,
  industry_rank: 1,
  total_score: 86.3,
  market_cap: 187900000000,
  pe_ratio: 49.1,
  change_pct: 3.45,
  mini_trend: [98, 99, 100, 101, 102],
  dimension_scores: {},
  ...overrides,
});

jest.mock('../services/api', () => ({
  getLeaderBoards: jest.fn(),
  getLeaderStocks: jest.fn(),
  getLeaderDetail: jest.fn(),
  getIndustryTrend: jest.fn(),
}));

jest.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
}));

jest.mock('../components/StockDetailModal', () => () => null);
jest.mock('../components/common/MiniSparkline', () => () => <div data-testid="mini-sparkline" />);

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;
  return {
    CrownOutlined: MockIcon,
    ReloadOutlined: MockIcon,
    BarChartOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  const Card = ({ title, extra, children }) => (
    <section>
      <div>{title}</div>
      <div>{extra}</div>
      <div>{children}</div>
    </section>
  );
  const Empty = ({ description }) => <div>{description}</div>;
  Empty.PRESENTED_IMAGE_SIMPLE = null;
  const Tag = ({ children }) => <span>{children}</span>;
  const Button = ({ children, onClick }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  );
  const Tooltip = ({ children }) => <>{children}</>;

  return {
    Card,
    Empty,
    Tag,
    Button,
    Tooltip,
  };
});

describe('LeaderStockPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __resetLeaderBoardClientCacheForTests();
    window.sessionStorage.clear();
    getLeaderBoards.mockResolvedValue({ core: [], hot: [], errors: {} });
    getLeaderStocks.mockResolvedValue([]);
    getLeaderDetail.mockResolvedValue({});
    getIndustryTrend.mockResolvedValue(null);
  });

  test('renders cached leader overview immediately and refreshes it in background', async () => {
    const cacheKey = buildLeaderBoardCacheKey(5, 5, 3);
    window.sessionStorage.setItem(cacheKey, JSON.stringify({
      version: 1,
      timestamp: Date.now(),
      core: [buildLeaderRecord({ name: '缓存核心', symbol: '600001' })],
      hot: [buildLeaderRecord({ name: '缓存热点', symbol: '300001', score_type: 'hot' })],
      errors: {},
    }));

    let resolveOverview;
    getLeaderBoards.mockReturnValue(new Promise((resolve) => {
      resolveOverview = resolve;
    }));

    render(<LeaderStockPanel topN={5} topIndustries={5} perIndustry={3} />);

    expect(screen.getByText('缓存核心')).toBeInTheDocument();
    expect(screen.getByText('缓存热点')).toBeInTheDocument();

    await act(async () => {
      resolveOverview({
        core: [buildLeaderRecord({ name: '实时核心', symbol: '600002' })],
        hot: [buildLeaderRecord({ name: '实时热点', symbol: '300002', score_type: 'hot' })],
        errors: {},
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('实时核心')).toBeInTheDocument();
      expect(screen.getByText('实时热点')).toBeInTheDocument();
    });

    const cachedSnapshot = JSON.parse(window.sessionStorage.getItem(cacheKey) || '{}');
    expect(cachedSnapshot.core?.[0]?.name).toBe('实时核心');
    expect(cachedSnapshot.hot?.[0]?.name).toBe('实时热点');
  });

  test('keeps cached overview visible when refresh fails', async () => {
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const cacheKey = buildLeaderBoardCacheKey(5, 5, 3);
    try {
      window.sessionStorage.setItem(cacheKey, JSON.stringify({
        version: 1,
        timestamp: Date.now(),
        core: [buildLeaderRecord({ name: '缓存核心', symbol: '600001' })],
        hot: [buildLeaderRecord({ name: '缓存热点', symbol: '300001', score_type: 'hot' })],
        errors: {},
      }));

      getLeaderBoards.mockRejectedValue(new Error('overview failed'));
      getLeaderStocks.mockRejectedValue(new Error('legacy failed'));

      render(<LeaderStockPanel topN={5} topIndustries={5} perIndustry={3} />);

      expect(screen.getByText('缓存核心')).toBeInTheDocument();
      expect(screen.getByText('缓存热点')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText('龙头股榜单刷新失败，当前展示的是稍早快照')).toBeInTheDocument();
      });

      expect(screen.queryByText('龙头股榜单加载失败，请稍后重试')).not.toBeInTheDocument();
    } finally {
      warnSpy.mockRestore();
      errorSpy.mockRestore();
    }
  });

  test('reuses in-flight overview request across remounts', async () => {
    let resolveOverview;
    getLeaderBoards.mockReturnValue(new Promise((resolve) => {
      resolveOverview = resolve;
    }));

    const firstRender = render(<LeaderStockPanel topN={5} topIndustries={5} perIndustry={3} />);
    firstRender.unmount();

    render(<LeaderStockPanel topN={5} topIndustries={5} perIndustry={3} />);

    expect(getLeaderBoards).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveOverview({
        core: [buildLeaderRecord({ name: '共享核心', symbol: '600003' })],
        hot: [buildLeaderRecord({ name: '共享热点', symbol: '300003', score_type: 'hot' })],
        errors: {},
      });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText('共享核心')).toBeInTheDocument();
      expect(screen.getByText('共享热点')).toBeInTheDocument();
    });
  });

  test('renders bootstrapped overview without issuing another overview request', async () => {
    render(
      <LeaderStockPanel
        topN={5}
        topIndustries={5}
        perIndustry={3}
        bootstrapLoading={false}
        bootstrappedOverview={{
          core: [buildLeaderRecord({ name: '预热核心', symbol: '600010' })],
          hot: [buildLeaderRecord({ name: '预热热点', symbol: '300010', score_type: 'hot' })],
          errors: {},
        }}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('预热核心')).toBeInTheDocument();
      expect(screen.getByText('预热热点')).toBeInTheDocument();
    });

    expect(getLeaderBoards).not.toHaveBeenCalled();
  });

  test('tops up sparse focused leader lists with supplemental reference rows', async () => {
    render(
      <LeaderStockPanel
        topN={5}
        topIndustries={5}
        perIndustry={3}
        focusIndustry="银行"
        bootstrappedOverview={{
          core: [
            buildLeaderRecord({ name: '农业银行', symbol: '601288', industry: '银行', global_rank: 2 }),
            buildLeaderRecord({ name: '建设银行', symbol: '601939', industry: '银行', global_rank: 3 }),
            buildLeaderRecord({ name: '中国银行', symbol: '601988', industry: '银行', global_rank: 4 }),
            buildLeaderRecord({ name: '宁德时代', symbol: '300750', industry: '电池', global_rank: 5 }),
          ],
          hot: [
            buildLeaderRecord({ name: '中信银行', symbol: '601998', industry: '银行', score_type: 'hot', global_rank: 4 }),
            buildLeaderRecord({ name: '工业富联', symbol: '601138', industry: '通信设备', score_type: 'hot', global_rank: 5 }),
          ],
          errors: {},
        }}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/已补入参考标的/)).toBeInTheDocument();
      expect(screen.getAllByText('补位参考').length).toBeGreaterThan(0);
      expect(screen.getByText('宁德时代')).toBeInTheDocument();
      expect(screen.getByText('工业富联')).toBeInTheDocument();
    });
  });

  test('exposes a backtest handoff action for leader rows', async () => {
    const handleBacktestStock = jest.fn();

    render(
      <LeaderStockPanel
        topN={5}
        topIndustries={5}
        perIndustry={3}
        onBacktestStock={handleBacktestStock}
        bootstrappedOverview={{
          core: [buildLeaderRecord({ name: '回测核心', symbol: '600111' })],
          hot: [],
          errors: {},
        }}
      />
    );

    fireEvent.click(await screen.findByRole('button', { name: '回测' }));

    expect(handleBacktestStock).toHaveBeenCalledWith(expect.objectContaining({
      symbol: '600111',
      name: '回测核心',
    }));
  });
});
