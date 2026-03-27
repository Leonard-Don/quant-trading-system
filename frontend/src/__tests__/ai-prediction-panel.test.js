import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

import AIPredictionPanel from '../components/AIPredictionPanel';
import { compareModelPredictions, trainAllModels } from '../services/api';

jest.mock('../services/api', () => ({
  compareModelPredictions: jest.fn(),
  predictPrice: jest.fn(),
  predictWithLSTM: jest.fn(),
  trainAllModels: jest.fn(),
}));

jest.mock('recharts', () => {
  const React = require('react');
  const Mock = ({ children }) => <div>{children}</div>;

  return {
    ResponsiveContainer: Mock,
    ComposedChart: Mock,
    Line: Mock,
    Area: Mock,
    XAxis: Mock,
    YAxis: Mock,
    CartesianGrid: Mock,
    Tooltip: Mock,
    Legend: Mock,
  };
});

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;

  return {
    RobotOutlined: MockIcon,
    ArrowUpOutlined: MockIcon,
    ArrowDownOutlined: MockIcon,
    ExperimentOutlined: MockIcon,
    ReloadOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  const Card = ({ title, extra, children }) => (
    <section>
      {title ? <div>{title}</div> : null}
      {extra ? <div>{extra}</div> : null}
      {children}
    </section>
  );
  const Spin = () => <div>loading</div>;
  const Alert = ({ message, description }) => (
    <div>
      <div>{message}</div>
      <div>{description}</div>
    </div>
  );
  const Statistic = ({ title, value, prefix, suffix, formatter }) => {
    const displayValue = formatter ? formatter(value) : value;
    return (
      <div>
        <span>{title}</span>
        <span>{prefix}{displayValue}{suffix}</span>
      </div>
    );
  };
  const Tag = ({ children }) => <span>{children}</span>;
  const Button = ({ children, onClick }) => <button type="button" onClick={onClick}>{children}</button>;
  const Row = ({ children }) => <div>{children}</div>;
  const Col = ({ children }) => <div>{children}</div>;
  const Space = ({ children }) => <span>{children}</span>;
  const Tooltip = ({ children }) => <div>{children}</div>;

  return {
    Card,
    Spin,
    Alert,
    Typography: {
      Text: ({ children }) => <span>{children}</span>,
      Paragraph: ({ children }) => <p>{children}</p>,
    },
    Row,
    Col,
    Statistic,
    Tag,
    Button,
    Tooltip,
    Space,
    message: {
      success: jest.fn(),
      error: jest.fn(),
    },
  };
});

const createDeferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('AIPredictionPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    trainAllModels.mockResolvedValue({});
    compareModelPredictions.mockResolvedValue({
      symbol: 'AAPL',
      dates: ['2026-03-20', '2026-03-21'],
      predictions: {
        random_forest: {
          status: 'success',
          predicted_prices: [100, 108],
          confidence_intervals: [
            { lower: 98, upper: 102 },
            { lower: 105, upper: 111 },
          ],
        },
        lstm: {
          status: 'error',
          error: 'model unavailable',
        },
      },
      comparison: {},
    });
  });

  test('falls back to a single available model instead of fabricating zero-value consensus prices', async () => {
    render(<AIPredictionPanel symbol="AAPL" />);

    await waitFor(() => {
      expect(compareModelPredictions).toHaveBeenCalledWith('AAPL');
    });

    expect(await screen.findByText('当前仅使用随机森林结果')).toBeInTheDocument();
    expect(screen.getByText('暂不可用 LSTM')).toBeInTheDocument();
    expect(screen.getByText('$100.00')).toBeInTheDocument();
    expect(screen.getByText('$108.00')).toBeInTheDocument();
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument();
  });

  test('ignores stale prediction responses when switching symbols quickly', async () => {
    const msftRequest = createDeferred();
    const nvdaRequest = createDeferred();

    compareModelPredictions.mockImplementation((symbol) => {
      if (symbol === 'MSFT') {
        return msftRequest.promise;
      }
      if (symbol === 'NVDA') {
        return nvdaRequest.promise;
      }
      return Promise.reject(new Error(`Unexpected symbol ${symbol}`));
    });

    const { rerender } = render(<AIPredictionPanel symbol="MSFT" />);

    rerender(<AIPredictionPanel symbol="NVDA" />);

    nvdaRequest.resolve({
      symbol: 'NVDA',
      dates: ['2026-03-20', '2026-03-21'],
      predictions: {
        random_forest: {
          status: 'success',
          predicted_prices: [200, 210],
          confidence_intervals: [
            { lower: 198, upper: 202 },
            { lower: 207, upper: 213 },
          ],
        },
      },
      comparison: {},
    });

    msftRequest.resolve({
      symbol: 'MSFT',
      dates: ['2026-03-20', '2026-03-21'],
      predictions: {
        random_forest: {
          status: 'success',
          predicted_prices: [50, 55],
          confidence_intervals: [
            { lower: 49, upper: 51 },
            { lower: 54, upper: 56 },
          ],
        },
      },
      comparison: {},
    });

    expect(await screen.findByText('NVDA')).toBeInTheDocument();
    expect(screen.getByText('$200.00')).toBeInTheDocument();
    expect(screen.queryByText('$50.00')).not.toBeInTheDocument();
  });

  test('renders prediction results under React StrictMode instead of staying stuck in loading state', async () => {
    render(
      <React.StrictMode>
        <AIPredictionPanel symbol="AAPL" />
      </React.StrictMode>
    );

    expect(await screen.findByText('当前仅使用随机森林结果')).toBeInTheDocument();
    expect(screen.getByText('$100.00')).toBeInTheDocument();
    expect(screen.queryByText(/正在分析并预测未来趋势/)).not.toBeInTheDocument();
  });
});
