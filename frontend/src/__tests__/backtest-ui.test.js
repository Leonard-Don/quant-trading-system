import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import ResultsDisplay from '../components/ResultsDisplay';
import BacktestHistory from '../components/BacktestHistory';
import {
  getBacktestHistory,
  getBacktestHistoryStats,
  getBacktestRecord,
  downloadBacktestReport,
  runMarketRegimeBacktest,
} from '../services/api';

jest.mock('../services/api', () => ({
  getBacktestHistory: jest.fn(),
  getBacktestHistoryStats: jest.fn(),
  getBacktestRecord: jest.fn(),
  deleteBacktestRecord: jest.fn(),
  downloadBacktestReport: jest.fn(),
  runMarketRegimeBacktest: jest.fn(),
}));

jest.mock('../components/PerformanceChart', () => () => <div>PerformanceChart</div>);
jest.mock('../components/DrawdownChart', () => () => <div>DrawdownChart</div>);
jest.mock('../components/MonthlyHeatmap', () => () => <div>MonthlyHeatmap</div>);
jest.mock('../components/RiskRadar', () => () => <div>RiskRadar</div>);
jest.mock('../components/ReturnHistogram', () => () => <div>ReturnHistogram</div>);

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = () => ({
      matches: false,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    });
  }

  if (!window.ResizeObserver) {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }

  if (!window.URL.createObjectURL) {
    window.URL.createObjectURL = jest.fn(() => 'blob:test');
  }
  if (!window.URL.revokeObjectURL) {
    window.URL.revokeObjectURL = jest.fn();
  }
});

afterEach(() => {
  jest.clearAllMocks();
  window.history.replaceState(null, '', '/');
});

describe('ResultsDisplay', () => {
  test('renders top-level metrics and normalizes compatibility trade fields', async () => {
    const onOpenHistoryRecord = jest.fn();
    const onContinueAdvancedExperiment = jest.fn();
    runMarketRegimeBacktest.mockResolvedValue({
      success: true,
      data: {
        summary: {
          regime_count: 4,
          positive_regimes: 3,
          strongest_regime: {
            regime: '上涨趋势',
            strategy_total_return: 0.14,
          },
          weakest_regime: {
            regime: '下跌趋势',
            strategy_total_return: -0.03,
          },
        },
        regimes: [
          {
            regime: '上涨趋势',
            days: 24,
            strategy_total_return: 0.14,
            market_total_return: 0.12,
            win_rate: 0.67,
            max_drawdown: -0.05,
          },
        ],
      },
    });
    render(
      <ResultsDisplay
        onOpenHistoryRecord={onOpenHistoryRecord}
        onContinueAdvancedExperiment={onContinueAdvancedExperiment}
        results={{
          symbol: 'AAPL',
          strategy: 'buy_and_hold',
          total_return: 0.1,
          annualized_return: 0.2,
          max_drawdown: -0.05,
          sharpe_ratio: 1.5,
          final_value: 11000,
          num_trades: 1,
          win_rate: 1,
          profit_factor: 2.5,
          net_profit: 1000,
          history_record_id: 'bt_123',
          start_date: '2024-01-01',
          end_date: '2024-03-31',
          initial_capital: 10000,
          commission: 0.001,
          slippage: 0.001,
          execution_diagnostics: {
            configured_signal_mode: 'auto',
            resolved_signal_mode: 'target',
            allow_fractional_shares: true,
            position_sizer: 'FixedFractionSizer',
            risk_manager: null,
            stop_loss_pct: null,
            take_profit_pct: null,
          },
          trades: [
            {
              date: '2024-01-01',
              action: 'buy',
              quantity: 5,
              price: 100,
              value: 500,
            },
          ],
          portfolio_history: [
            {
              date: '2024-01-01',
              total: 10000,
              returns: 0,
              signal: 1,
            },
          ],
        }}
      />
    );

    expect(screen.getByText('最终价值')).toBeInTheDocument();
    expect(screen.getByText('$11,000.00')).toBeInTheDocument();
    expect(screen.getByText(/首日建仓后持续持有到回测结束/)).toBeInTheDocument();
    expect(screen.getByText(/执行诊断/)).toBeInTheDocument();
    expect(screen.getByText('目标仓位')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /查看历史记录/ }));
    expect(onOpenHistoryRecord).toHaveBeenCalledWith('bt_123');
    fireEvent.click(screen.getByRole('button', { name: /继续做高级实验/ }));
    expect(onContinueAdvancedExperiment).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /分析市场状态/ }));

    await waitFor(() => {
      expect(runMarketRegimeBacktest).toHaveBeenCalledWith(expect.objectContaining({
        symbol: 'AAPL',
        strategy: 'buy_and_hold',
        start_date: '2024-01-01',
        end_date: '2024-03-31',
      }));
      expect(screen.getByText(/最适合的市场状态/)).toBeInTheDocument();
      expect(screen.getAllByText(/上涨趋势/).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole('tab', { name: '交易记录' }));

    await waitFor(() => {
      expect(screen.getByText('买入')).toBeInTheDocument();
      expect(screen.getByText('$500.00')).toBeInTheDocument();
    });
  }, 10000);
});

describe('BacktestHistory', () => {
  beforeEach(() => {
    getBacktestHistoryStats.mockResolvedValue({
      success: true,
      data: {
        total_records: 12,
        avg_return: 0.08,
        strategy_count: 3,
        latest_record_at: '2024-01-02T00:00:00Z',
      },
    });
  });

  test('downloads report through blob response', async () => {
    getBacktestHistory.mockResolvedValue({
      success: true,
      total: 1,
      data: [
        {
          id: 'rec-1',
          symbol: 'AAPL',
          strategy: 'buy_and_hold',
          timestamp: '2024-01-02T00:00:00Z',
          start_date: '2024-01-01',
          end_date: '2024-01-06',
          parameters: {},
          metrics: {
            total_return: 0.1,
            annualized_return: 0.2,
            sharpe_ratio: 1.5,
            max_drawdown: -0.05,
            num_trades: 1,
          },
          result: {
            total_return: 0.1,
            annualized_return: 0.2,
            sharpe_ratio: 1.5,
            max_drawdown: -0.05,
            num_trades: 1,
          },
        },
      ],
    });
    downloadBacktestReport.mockResolvedValue({
      blob: new Blob(['fake-pdf'], { type: 'application/pdf' }),
      filename: 'report.pdf',
      contentType: 'application/pdf',
    });
    getBacktestRecord.mockResolvedValue({
      success: true,
      data: {
        id: 'rec-1',
        symbol: 'AAPL',
        strategy: 'buy_and_hold',
        timestamp: '2024-01-02T00:00:00Z',
        start_date: '2024-01-01',
        end_date: '2024-01-06',
        parameters: {},
        metrics: {
          total_return: 0.1,
          annualized_return: 0.2,
          sharpe_ratio: 1.5,
          max_drawdown: -0.05,
          num_trades: 1,
        },
        result: {
          total_return: 0.1,
          annualized_return: 0.2,
          sharpe_ratio: 1.5,
          max_drawdown: -0.05,
          num_trades: 1,
          trades: [
            {
              date: '2024-01-02',
              action: 'buy',
              quantity: 5,
              price: 100,
              value: 500,
            },
          ],
        },
      },
    });

    const { container } = render(<BacktestHistory />);

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    const anchor = { click: jest.fn(), href: '', download: '' };
    const createElementSpy = jest
      .spyOn(document, 'createElement')
      .mockImplementation((tagName) => {
        if (tagName === 'a') {
          return anchor;
        }
        return document.createElementNS('http://www.w3.org/1999/xhtml', tagName);
      });
    const appendChildSpy = jest.spyOn(document.body, 'appendChild').mockImplementation(() => anchor);
    const removeChildSpy = jest.spyOn(document.body, 'removeChild').mockImplementation(() => anchor);

    try {
      const downloadButton = container.querySelector('tbody button.ant-btn-primary');
      fireEvent.click(downloadButton);

      await waitFor(() => {
        expect(getBacktestRecord).toHaveBeenCalledWith('rec-1');
        expect(downloadBacktestReport).toHaveBeenCalled();
        expect(window.URL.createObjectURL).toHaveBeenCalled();
        expect(anchor.download).toBe('report.pdf');
        expect(anchor.click).toHaveBeenCalled();
      });
    } finally {
      createElementSpy.mockRestore();
      appendChildSpy.mockRestore();
      removeChildSpy.mockRestore();
    }
  });

  test('loads backend stats and opens highlighted history record from detail endpoint', async () => {
    getBacktestHistory.mockResolvedValue({
      success: true,
      data: [],
    });
    getBacktestRecord.mockResolvedValue({
      success: true,
      data: {
        id: 'rec-42',
        symbol: 'TSLA',
        strategy: 'macd',
        timestamp: '2024-02-01T00:00:00Z',
        start_date: '2024-01-01',
        end_date: '2024-02-01',
        parameters: { fast_period: 12 },
        metrics: {
          total_return: 0.12,
          annualized_return: 0.2,
          sharpe_ratio: 1.4,
          max_drawdown: -0.06,
          num_trades: 4,
          final_value: 11200,
          net_profit: 1200,
          avg_win: 300,
          avg_loss: -120,
          total_profit: 900,
          total_loss: -240,
          loss_rate: 0.25,
          avg_holding_days: 6.5,
          total_completed_trades: 2,
          has_open_position: false,
        },
        result: {
          total_return: 0.12,
          annualized_return: 0.2,
          sharpe_ratio: 1.4,
          max_drawdown: -0.06,
          num_trades: 4,
          portfolio_history: [
            {
              date: '2024-01-08',
              total: 10000,
              returns: 0,
              signal: 1,
            },
            {
              date: '2024-01-18',
              total: 11200,
              returns: 0.12,
              signal: -1,
            },
          ],
          trades: [
            {
              date: '2024-01-08',
              type: 'BUY',
              quantity: 5,
              price: 200,
              value: 1000,
              pnl: 0,
            },
            {
              date: '2024-01-18',
              type: 'SELL',
              quantity: 5,
              price: 240,
              value: 1200,
              pnl: 200,
            },
          ],
        },
      },
    });

    render(<BacktestHistory highlightRecordId="rec-42" />);

    await waitFor(() => {
      expect(getBacktestHistoryStats).toHaveBeenCalled();
      expect(getBacktestRecord).toHaveBeenCalledWith('rec-42');
      expect(screen.getAllByText('12 条').length).toBeGreaterThan(0);
      expect(screen.getByText('TSLA')).toBeInTheDocument();
      expect(screen.getByText('扩展诊断')).toBeInTheDocument();
      expect(screen.getByText('交易明细')).toBeInTheDocument();
      expect(screen.getByText('组合净值回放')).toBeInTheDocument();
      expect(screen.getByText('PerformanceChart')).toBeInTheDocument();
      expect(screen.getByText('$1,200.00')).toBeInTheDocument();
      expect(screen.getByText('平均盈利')).toBeInTheDocument();
      expect(screen.getByText('卖出')).toBeInTheDocument();
    });
  });

  test('restores and submits history filters through backend queries', async () => {
    window.history.replaceState(null, '', '/?tab=history&history_symbol=MSFT&history_strategy=macd&history_record_type=walk_forward');

    getBacktestHistory.mockResolvedValue({
      success: true,
      data: [],
    });

    render(<BacktestHistory />);

    await waitFor(() => {
      expect(getBacktestHistory).toHaveBeenCalledWith(10, {
        symbol: 'MSFT',
        strategy: 'macd',
        recordType: 'walk_forward',
      }, 0);
      expect(getBacktestHistoryStats).toHaveBeenCalledWith({
        symbol: 'MSFT',
        strategy: 'macd',
        recordType: 'walk_forward',
      });
    });

    const resetButton = screen.getByLabelText('clear').closest('button');
    fireEvent.click(resetButton);

    await waitFor(() => {
      expect(getBacktestHistory).toHaveBeenLastCalledWith(10, {
        symbol: undefined,
        strategy: undefined,
        recordType: undefined,
      }, 0);
    });
  });

  test('opens list record details with extended metrics from normalized result payload', async () => {
    getBacktestHistory.mockResolvedValue({
      success: true,
      total: 1,
      data: [
        {
          id: 'rec-99',
          symbol: 'AAPL',
          strategy: 'moving_average',
          timestamp: '2024-03-01T00:00:00Z',
          start_date: '2024-01-01',
          end_date: '2024-03-01',
          parameters: {},
          metrics: {
            total_return: 0.1,
            annualized_return: 0.12,
            sharpe_ratio: 1.3,
            max_drawdown: -0.05,
            num_trades: 4,
          },
          result: {
            total_return: 0.1,
            annualized_return: 0.12,
            sharpe_ratio: 1.3,
            max_drawdown: -0.05,
            num_trades: 4,
            avg_win: 300,
            avg_loss: -120,
            total_profit: 900,
            total_loss: -240,
            loss_rate: 0.25,
            avg_holding_days: 6.5,
            total_completed_trades: 2,
            has_open_position: false,
            trades: [
              {
                date: '2024-02-01',
                type: 'SELL',
                quantity: 5,
                price: 240,
                value: 1200,
                pnl: 200,
              },
            ],
            portfolio_history: [
              {
                date: '2024-02-01',
                total: 11200,
                returns: 0.12,
                signal: -1,
              },
            ],
          },
        },
      ],
    });

    render(<BacktestHistory />);

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('eye'));

    await waitFor(() => {
      expect(screen.getByText('平均盈利')).toBeInTheDocument();
      expect(screen.getByText('$300.00')).toBeInTheDocument();
      expect(screen.getByText('$900.00')).toBeInTheDocument();
      expect(screen.getByText('6.5 天')).toBeInTheDocument();
      expect(screen.getByText('已全部平仓')).toBeInTheDocument();
    });
  });

  test('renders advanced batch experiment details without backtest-only sections', async () => {
    getBacktestHistory.mockResolvedValue({
      success: true,
      total: 1,
      data: [
        {
          id: 'advanced-1',
          record_type: 'batch_backtest',
          title: '批量回测 · AAPL',
          symbol: 'AAPL',
          strategy: 'batch_backtest',
          timestamp: '2024-03-01T00:00:00Z',
          start_date: '2024-01-01',
          end_date: '2024-03-01',
          parameters: {
            ranking_metric: 'sharpe_ratio',
          },
          metrics: {
            total_return: 0.08,
            sharpe_ratio: 1.1,
            total_tasks: 2,
            successful: 2,
          },
          result: {
            summary: {
              total_tasks: 2,
              successful: 2,
            },
            results: [
              {
                task_id: 'task_1',
                strategy: 'moving_average',
                success: true,
                metrics: {
                  total_return: 0.1,
                  sharpe_ratio: 1.2,
                },
              },
            ],
          },
        },
      ],
    });
    getBacktestRecord.mockResolvedValue({
      success: true,
      data: {
        id: 'advanced-1',
        record_type: 'batch_backtest',
        title: '批量回测 · AAPL',
        symbol: 'AAPL',
        strategy: 'batch_backtest',
        timestamp: '2024-03-01T00:00:00Z',
        start_date: '2024-01-01',
        end_date: '2024-03-01',
        parameters: {
          ranking_metric: 'sharpe_ratio',
        },
        metrics: {
          total_return: 0.08,
          sharpe_ratio: 1.1,
          total_tasks: 2,
          successful: 2,
        },
        result: {
          summary: {
            total_tasks: 2,
            successful: 2,
          },
          results: [
            {
              task_id: 'task_1',
              strategy: 'moving_average',
              success: true,
              metrics: {
                total_return: 0.1,
                sharpe_ratio: 1.2,
              },
            },
          ],
        },
      },
    });

    render(<BacktestHistory />);

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('eye'));

    await waitFor(() => {
      expect(screen.getByText('实验摘要')).toBeInTheDocument();
      expect(screen.getByText('总任务数')).toBeInTheDocument();
      expect(screen.getByText('成功率')).toBeInTheDocument();
      expect(screen.getByText('批量结果明细')).toBeInTheDocument();
      expect(screen.getAllByText('批量回测').length).toBeGreaterThan(0);
      expect(screen.queryByText('组合净值回放')).not.toBeInTheDocument();
      expect(screen.queryByText('交易明细')).not.toBeInTheDocument();
    });
  });
});
