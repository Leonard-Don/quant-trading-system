import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import LowVolPortfolioPanel from '../components/LowVolPortfolioPanel';
import { getLowVolatilityPortfolio } from '../services/api';

const mockMessageApi = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
};

vi.mock('../services/api', () => ({
  getLowVolatilityPortfolio: jest.fn(),
}));

vi.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
  getApiErrorMessage: (error, fallback) => (error && error.message) || fallback,
}));

vi.mock('@ant-design/icons', () => ({
  LineChartOutlined: () => <span data-testid="icon" />,
}));

// recharts doesn't render meaningfully in jsdom — stub to plain divs.
vi.mock('recharts', () => {
  const Pass = ({ children }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Pass,
    LineChart: Pass,
    Line: () => <div data-testid="line" />,
    XAxis: () => null,
    YAxis: () => null,
    Tooltip: () => null,
    Legend: () => null,
    CartesianGrid: () => null,
  };
});

vi.mock('antd', () => {
  const Card = ({ title, extra, children }) => (
    <section><div>{title}</div><div>{extra}</div><div>{children}</div></section>
  );
  const Alert = ({ message, description }) => (
    <div role="alert"><div>{message}</div><div>{description}</div></div>
  );
  const Button = ({ children, onClick }) => (
    <button type="button" onClick={onClick}>{children}</button>
  );
  const Select = ({ value, onChange, options = [] }) => (
    <select value={value} onChange={(e) => onChange?.(e.target.value)} aria-label="portfolio-universe-select">
      {options.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
    </select>
  );
  const InputNumber = ({ value, onChange }) => (
    <input type="number" aria-label="basket-n-input" value={value} onChange={(e) => onChange?.(Number(e.target.value))} />
  );
  const Table = ({ columns = [], dataSource = [] }) => (
    <table><tbody>
      {dataSource.map((row) => (
        <tr key={row.key} data-testid="metric-row">
          {columns.map((col) => (
            <td key={col.key}>{col.render ? col.render(row[col.dataIndex], row) : row[col.dataIndex]}</td>
          ))}
        </tr>
      ))}
    </tbody></table>
  );
  const Empty = ({ description }) => <div>{description}</div>;
  const Spin = () => <div>Loading</div>;
  const Space = ({ children }) => <div>{children}</div>;
  const Text = ({ children }) => <span>{children}</span>;
  const Paragraph = ({ children }) => <p>{children}</p>;
  const Statistic = ({ title, value, suffix }) => <div>{title}: {value}{suffix}</div>;
  const Row = ({ children }) => <div>{children}</div>;
  const Col = ({ children }) => <div>{children}</div>;
  const Typography = { Text, Paragraph };
  return { Card, Alert, Button, Select, InputNumber, Table, Empty, Spin, Space, Statistic, Row, Col, Typography };
});

const buildResponse = () => ({
  universe: 'csi300',
  index_code: '000300.SH',
  span: '20180101..20240101',
  window: 60,
  basket_n: 30,
  n_periods: 46,
  avg_annual_turnover: 2.7,
  cost_rates: { buy: 0.00076, sell: 0.00126 },
  equity_curve: [
    { date: '2019-01', basket_gross: 1.0, basket_net: 1.0, benchmark: 1.0 },
    { date: '2020-01', basket_gross: 1.1, basket_net: 1.08, benchmark: 1.02 },
  ],
  metrics: {
    net: { cagr: 0.0478, ann_vol: 0.123, sharpe: 0.44, max_drawdown: -0.13 },
    gross: { cagr: 0.0534, ann_vol: 0.123, sharpe: 0.48, max_drawdown: -0.12 },
    benchmark: { cagr: 0.025, ann_vol: 0.186, sharpe: 0.22, max_drawdown: -0.23 },
  },
  as_of: '2026-06-08T10:00:00',
  disclaimer: '低波动是本项目唯一通过样本外验证的信号（CSI500 OOS IC +0.11）。净 Sharpe≈0.44 vs 等权 0.22。仅供研究，非投资建议。',
});

describe('LowVolPortfolioPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getLowVolatilityPortfolio.mockResolvedValue(buildResponse());
  });

  test('does not auto-run; shows the disclaimer banner up front', () => {
    render(<LowVolPortfolioPanel />);
    // no auto-fetch on mount (backtest is heavy)
    expect(getLowVolatilityPortfolio).not.toHaveBeenCalled();
    // disclaimer banner is present even before running
    const alerts = screen.getAllByRole('alert');
    const text = alerts.map((a) => a.textContent).join(' ');
    expect(text).toContain('非投资建议');
  });

  test('runs the backtest and renders the metrics table (net / gross / benchmark)', async () => {
    render(<LowVolPortfolioPanel />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '运行回测' }));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(getLowVolatilityPortfolio).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getAllByTestId('metric-row')).toHaveLength(3);
    });

    const rows = screen.getAllByTestId('metric-row');
    expect(rows[0]).toHaveTextContent('低波动篮子(净)');
    expect(rows[2]).toHaveTextContent('等权基准');
    // net Sharpe and benchmark Sharpe rendered
    const tableText = rows.map((r) => r.textContent).join(' ');
    expect(tableText).toContain('0.44');
    expect(tableText).toContain('0.22');

    // data-driven disclaimer shows the OOS evidence
    const alerts = screen.getAllByRole('alert');
    expect(alerts.map((a) => a.textContent).join(' ')).toContain('样本外验证');
  });

  test('surfaces an error when the backtest request fails', async () => {
    getLowVolatilityPortfolio.mockRejectedValueOnce(new Error('boom'));

    render(<LowVolPortfolioPanel />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '运行回测' }));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockMessageApi.error).toHaveBeenCalledWith('boom');
    });
  });
});
