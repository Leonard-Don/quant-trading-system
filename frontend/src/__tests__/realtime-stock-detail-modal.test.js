import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

import RealtimeStockDetailModal from '../components/RealtimeStockDetailModal';

const mockMarketAnalysisMountSpy = jest.fn();
const mockMarketAnalysisUnmountSpy = jest.fn();

jest.mock('../components/MarketAnalysis', () => {
  const React = require('react');

  return function MockMarketAnalysis(props) {
    React.useEffect(() => {
      mockMarketAnalysisMountSpy(props.symbol);
      return () => {
        mockMarketAnalysisUnmountSpy(props.symbol);
      };
    }, [props.symbol]);

    return (
      <div data-testid="market-analysis">
        analysis:{props.symbol}:{props.embedMode ? 'embed' : 'full'}
      </div>
    );
  };
});

jest.mock('@ant-design/icons', () => {
  const React = require('react');
  const MockIcon = () => <span data-testid="icon" />;

  return {
    ClockCircleOutlined: MockIcon,
    DotChartOutlined: MockIcon,
    FundOutlined: MockIcon,
    RiseOutlined: MockIcon,
  };
});

jest.mock('antd', () => {
  const React = require('react');

  const Modal = ({ open, title, children }) => (
    open ? (
      <div>
        <div>{title}</div>
        <div>{children}</div>
      </div>
    ) : null
  );
  const Row = ({ children }) => <div>{children}</div>;
  const Col = ({ children }) => <div>{children}</div>;
  const Tag = ({ children }) => <span>{children}</span>;
  const Empty = ({ description }) => (
    <div>
      {description || 'empty'}
    </div>
  );
  Empty.PRESENTED_IMAGE_SIMPLE = 'simple';

  return {
    Modal,
    Row,
    Col,
    Tag,
    Empty,
    Typography: {
      Text: ({ children }) => <span>{children}</span>,
    },
  };
});

describe('RealtimeStockDetailModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('shows waiting state without quote and still loads embedded market analysis', () => {
    render(
      <RealtimeStockDetailModal
        open
        symbol="^GSPC"
        quote={null}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByTestId('realtime-quote-waiting')).toHaveTextContent('等待实时快照');
    expect(screen.getByTestId('market-analysis')).toHaveTextContent('analysis:^GSPC:embed');
    expect(mockMarketAnalysisMountSpy).toHaveBeenCalledWith('^GSPC');
  });

  test('remounts embedded market analysis when switching symbols', () => {
    const { rerender } = render(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{ symbol: 'AAPL', price: 180.55, change: 1.22, change_percent: 0.68 }}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByTestId('market-analysis')).toHaveTextContent('analysis:AAPL:embed');

    rerender(
      <RealtimeStockDetailModal
        open
        symbol="BTC-USD"
        quote={{ symbol: 'BTC-USD', price: 68000, change: -220, change_percent: -0.32 }}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByTestId('market-analysis')).toHaveTextContent('analysis:BTC-USD:embed');
    expect(mockMarketAnalysisMountSpy).toHaveBeenNthCalledWith(1, 'AAPL');
    expect(mockMarketAnalysisUnmountSpy).toHaveBeenCalledWith('AAPL');
    expect(mockMarketAnalysisMountSpy).toHaveBeenNthCalledWith(2, 'BTC-USD');
  });
});
