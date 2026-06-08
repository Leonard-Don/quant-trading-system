import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import LowVolatilityScreen from '../components/LowVolatilityScreen';
import { getLowVolatilityScreen } from '../services/api';

const mockMessageApi = {
  success: jest.fn(),
  error: jest.fn(),
  warning: jest.fn(),
};

vi.mock('../services/api', () => ({
  getLowVolatilityScreen: jest.fn(),
}));

vi.mock('../utils/messageApi', () => ({
  useSafeMessageApi: () => mockMessageApi,
  getApiErrorMessage: (error, fallback) => (error && error.message) || fallback,
}));

vi.mock('@ant-design/icons', () => {
  const MockIcon = () => <span data-testid="icon" />;
  return {
    ReloadOutlined: MockIcon,
    SafetyCertificateOutlined: MockIcon,
  };
});

// Minimal antd surface: render labels/descriptions/rows as plain text so the
// test can assert on visible content without antd's full styling machinery.
vi.mock('antd', () => {
  const Card = ({ title, extra, children }) => (
    <section>
      <div>{title}</div>
      <div>{extra}</div>
      <div>{children}</div>
    </section>
  );
  const Alert = ({ message, description }) => (
    <div role="alert">
      <div>{message}</div>
      <div>{description}</div>
    </div>
  );
  const Button = ({ children, onClick }) => (
    <button type="button" onClick={onClick}>{children}</button>
  );
  const Select = ({ value, onChange, options = [] }) => (
    <select value={value} onChange={(e) => onChange?.(e.target.value)} aria-label="universe-select">
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
  const InputNumber = ({ value, onChange }) => (
    <input
      type="number"
      aria-label="top-input"
      value={value}
      onChange={(e) => onChange?.(Number(e.target.value))}
    />
  );
  const Table = ({ columns = [], dataSource = [] }) => (
    <table>
      <tbody>
        {dataSource.map((row) => (
          <tr key={row.symbol} data-testid="lowvol-row">
            {columns.map((col) => (
              <td key={col.key}>
                {col.render ? col.render(row[col.dataIndex], row) : row[col.dataIndex]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
  const Tag = ({ children }) => <span>{children}</span>;
  const Empty = ({ description }) => <div>{description}</div>;
  const Spin = () => <div>Loading</div>;
  const Space = ({ children }) => <div>{children}</div>;
  const Text = ({ children }) => <span>{children}</span>;
  const Paragraph = ({ children }) => <p>{children}</p>;
  const Typography = { Text, Paragraph };

  return { Card, Alert, Button, Select, InputNumber, Table, Tag, Empty, Spin, Space, Typography };
});

const buildResponse = () => ({
  as_of: '2026-06-08T10:00:00',
  universe: 'csi300',
  window: 60,
  count: 3,
  items: [
    { rank: 1, symbol: '111111.SH', name: '平静股', realized_vol: 0.01, annualized_vol: 0.16, recent_return: 1.2, n_bars: 80 },
    { rank: 2, symbol: '222222.SH', name: '中波股', realized_vol: 0.02, annualized_vol: 0.32, recent_return: -0.5, n_bars: 80 },
    { rank: 3, symbol: '333333.SZ', name: '狂野股', realized_vol: 0.05, annualized_vol: 0.79, recent_return: 3.4, n_bars: 80 },
  ],
  disclaimer: '低波动是本项目唯一通过样本外验证的信号（预注册确认：CSI500 OOS IC +0.11，详见 docs/research/lowvol-confirmation.md）。仅供研究，非投资建议。',
});

describe('LowVolatilityScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getLowVolatilityScreen.mockResolvedValue(buildResponse());
  });

  test('renders ranked rows in order and shows the disclaimer banner', async () => {
    render(<LowVolatilityScreen />);

    await waitFor(() => {
      expect(screen.getAllByTestId('lowvol-row')).toHaveLength(3);
    });

    const rows = screen.getAllByTestId('lowvol-row');
    // ascending vol order: 平静股 -> 中波股 -> 狂野股
    expect(rows[0]).toHaveTextContent('111111.SH');
    expect(rows[0]).toHaveTextContent('平静股');
    expect(rows[1]).toHaveTextContent('222222.SH');
    expect(rows[2]).toHaveTextContent('333333.SZ');

    // disclaimer banner prominently shows the OOS evidence
    const alerts = screen.getAllByRole('alert');
    const disclaimerText = alerts.map((a) => a.textContent).join(' ');
    expect(disclaimerText).toContain('样本外验证');
    expect(disclaimerText).toContain('lowvol-confirmation.md');
    expect(disclaimerText).toContain('非投资建议');
  });

  test('re-queries when the 查询 button is clicked', async () => {
    render(<LowVolatilityScreen />);

    await waitFor(() => {
      expect(getLowVolatilityScreen).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '查询' }));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(getLowVolatilityScreen).toHaveBeenCalledTimes(2);
    });
  });

  test('surfaces an error when the request fails', async () => {
    getLowVolatilityScreen.mockRejectedValueOnce(new Error('boom'));

    render(<LowVolatilityScreen />);

    await waitFor(() => {
      expect(mockMessageApi.error).toHaveBeenCalledWith('boom');
    });
  });
});
