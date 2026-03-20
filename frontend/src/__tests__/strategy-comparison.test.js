import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import StrategyComparison from '../components/StrategyComparison';
import { compareStrategies } from '../services/api';

jest.mock('../services/api', () => ({
  compareStrategies: jest.fn(),
}));

const mockOpenStrategyComparisonPrintWindow = jest.fn(() => true);

jest.mock('../utils/strategyComparisonReport', () => ({
  buildStrategyComparisonReportHtml: jest.fn(() => '<html><body>report</body></html>'),
  openStrategyComparisonPrintWindow: (...args) => mockOpenStrategyComparisonPrintWindow(...args),
}));

jest.mock('recharts', () => {
  const React = require('react');
  const MockChart = ({ children }) => <div>{children}</div>;
  return {
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
    BarChart: MockChart,
    Bar: MockChart,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
    RadarChart: MockChart,
    PolarGrid: () => null,
    PolarAngleAxis: () => null,
    PolarRadiusAxis: () => null,
    Radar: () => null,
    Cell: () => null,
  };
});

jest.mock('antd', () => {
  const React = require('react');
  const mockMessage = {
    warning: jest.fn(),
    success: jest.fn(),
    error: jest.fn(),
  };

  const Select = ({ mode, value = [], onChange, children }) => (
    <input
      aria-label="strategy-select"
      value={Array.isArray(value) ? value.join(',') : value}
      onChange={(event) => {
        const nextValue = event.target.value
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean);
        onChange(mode === 'multiple' ? nextValue : nextValue[0]);
      }}
      list="strategy-options"
    />
  );
  Select.Option = ({ value, children }) => <option value={value}>{children}</option>;

  const RangePicker = ({ value, onChange }) => (
    <button type="button" onClick={() => onChange(value)}>
      range
    </button>
  );

  const Table = ({ dataSource = [], columns = [] }) => (
    <table>
      <tbody>
        {dataSource.map((row) => (
          <tr key={row.key}>
            {columns.map((column) => {
              const cellValue = row[column.dataIndex];
              return (
                <td key={column.key || column.dataIndex}>
                  {column.render ? column.render(cellValue, row) : cellValue}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );

  return {
    Card: ({ title, extra, children }) => (
      <section>
        <div>{title}</div>
        <div>{extra}</div>
        {children}
      </section>
    ),
    Select,
    DatePicker: { RangePicker },
    Button: ({ children, onClick, disabled }) => (
      <button type="button" onClick={onClick} disabled={disabled}>
        {children}
      </button>
    ),
    Input: ({ value, onChange, placeholder }) => (
      <input
        aria-label={placeholder}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
      />
    ),
    InputNumber: ({ value, onChange, placeholder, ...props }) => (
      <input
        aria-label={props['aria-label'] || placeholder}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        placeholder={placeholder}
      />
    ),
    Table,
    Row: ({ children }) => <div>{children}</div>,
    Col: ({ children }) => <div>{children}</div>,
    Space: ({ children }) => <div>{children}</div>,
    Typography: {
      Text: ({ children }) => <span>{children}</span>,
    },
    message: mockMessage,
    App: {
      useApp: () => ({
        message: mockMessage,
      }),
    },
    Alert: ({ message }) => <div>{message}</div>,
    Progress: ({ percent }) => <div>{percent}</div>,
    Tag: ({ children }) => <span>{children}</span>,
  };
});

describe('StrategyComparison', () => {
  afterEach(() => {
    mockOpenStrategyComparisonPrintWindow.mockClear();
  });

  test('renders compare results that include nested metrics mirrors', async () => {
    compareStrategies.mockResolvedValue({
      success: true,
      data: {
        buy_and_hold: {
          total_return: 0.12,
          annualized_return: 0.18,
          sharpe_ratio: 1.4,
          max_drawdown: -0.04,
          num_trades: 1,
          rank: 1,
          scores: {
            return_score: 80,
            sharpe_score: 75,
            risk_score: 90,
            overall_score: 82,
          },
          metrics: {
            total_return: 0.12,
            annualized_return: 0.18,
            sharpe_ratio: 1.4,
            max_drawdown: -0.04,
            num_trades: 1,
            total_trades: 1,
          },
        },
        moving_average: {
          total_return: 0.05,
          annualized_return: 0.08,
          sharpe_ratio: 0.9,
          max_drawdown: -0.08,
          num_trades: 4,
          rank: 2,
          scores: {
            return_score: 60,
            sharpe_score: 55,
            risk_score: 50,
            overall_score: 56,
          },
          metrics: {
            total_return: 0.05,
            annualized_return: 0.08,
            sharpe_ratio: 0.9,
            max_drawdown: -0.08,
            num_trades: 4,
            total_trades: 4,
          },
        },
      },
    });

    render(
      <StrategyComparison
        strategies={[
          { name: 'buy_and_hold' },
          {
            name: 'moving_average',
            parameters: {
              fast_period: { default: 5, min: 1, max: 50 },
              slow_period: { default: 20, min: 2, max: 200 },
            },
          },
        ]}
      />
    );

    fireEvent.change(screen.getByLabelText('strategy-select'), {
      target: { value: 'buy_and_hold,moving_average' },
    });
    await waitFor(() => {
      expect(screen.getByLabelText('移动平均策略-fast_period')).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText('初始资金'), {
      target: { value: '25000' },
    });
    fireEvent.change(screen.getByLabelText('手续费'), {
      target: { value: '0.2' },
    });
    fireEvent.change(screen.getByLabelText('滑点'), {
      target: { value: '0.15' },
    });
    fireEvent.change(screen.getByLabelText('移动平均策略-fast_period'), {
      target: { value: '8' },
    });
    fireEvent.change(screen.getByLabelText('移动平均策略-slow_period'), {
      target: { value: '21' },
    });
    fireEvent.click(screen.getByRole('button', { name: '开始对比' }));

    await waitFor(() => {
      expect(compareStrategies).toHaveBeenCalledWith({
        symbol: 'AAPL',
        start_date: expect.any(String),
        end_date: expect.any(String),
        initial_capital: 25000,
        commission: 0.002,
        slippage: 0.0015,
        strategy_configs: [
          { name: 'buy_and_hold', parameters: {} },
          { name: 'moving_average', parameters: { fast_period: 8, slow_period: 21 } },
        ],
      });
      expect(screen.getAllByText('买入持有').length).toBeGreaterThan(0);
      expect(screen.getAllByText('移动平均策略').length).toBeGreaterThan(0);
    });
  });

  test('opens printable comparison report instead of relying on jsPDF Chinese fonts', async () => {
    compareStrategies.mockResolvedValue({
      success: true,
      data: {
        macd: {
          total_return: 0.08,
          annualized_return: 0.12,
          sharpe_ratio: 1.1,
          max_drawdown: -0.06,
          num_trades: 5,
          rank: 1,
          scores: {
            return_score: 82,
            sharpe_score: 78,
            risk_score: 70,
            overall_score: 78,
          },
          metrics: {
            total_return: 0.08,
            annualized_return: 0.12,
            sharpe_ratio: 1.1,
            max_drawdown: -0.06,
            num_trades: 5,
          },
        },
        moving_average: {
          total_return: 0.04,
          annualized_return: 0.06,
          sharpe_ratio: 0.7,
          max_drawdown: -0.09,
          num_trades: 3,
          rank: 2,
          scores: {
            return_score: 60,
            sharpe_score: 55,
            risk_score: 48,
            overall_score: 55,
          },
          metrics: {
            total_return: 0.04,
            annualized_return: 0.06,
            sharpe_ratio: 0.7,
            max_drawdown: -0.09,
            num_trades: 3,
          },
        },
      },
    });

    render(
      <StrategyComparison
        strategies={[
          { name: 'macd' },
          { name: 'moving_average' },
        ]}
      />
    );

    fireEvent.change(screen.getByLabelText('strategy-select'), {
      target: { value: 'macd,moving_average' },
    });
    fireEvent.click(screen.getByRole('button', { name: '开始对比' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '导出PDF报告' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '导出PDF报告' }));

    expect(mockOpenStrategyComparisonPrintWindow).toHaveBeenCalled();
  });
});
