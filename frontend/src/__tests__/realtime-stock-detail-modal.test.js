import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
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

jest.mock('../services/api', () => ({
  getKlines: jest.fn(() => Promise.resolve({
    klines: [
      { date: '2026-03-27T09:30:00.000Z', close: 181.4 },
      { date: '2026-03-27T10:30:00.000Z', close: 182.1 },
      { date: '2026-03-27T11:30:00.000Z', close: 184.2 },
    ],
  })),
}));

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
  const Button = ({ children, onClick, 'aria-pressed': ariaPressed, className }) => (
    <button type="button" onClick={onClick} aria-pressed={ariaPressed} className={className}>
      {children}
    </button>
  );
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
    Button,
    Empty,
    Typography: {
      Text: ({ children }) => <span>{children}</span>,
    },
  };
});

describe('RealtimeStockDetailModal', () => {
  const renderRealtimeDetailModal = async (ui) => {
    const view = render(ui);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    return view;
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('shows waiting state without quote and still loads embedded market analysis', async () => {
    await renderRealtimeDetailModal(
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

  test('remounts embedded market analysis when switching symbols', async () => {
    const { rerender } = await renderRealtimeDetailModal(
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
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId('market-analysis')).toHaveTextContent('analysis:BTC-USD:embed');
    expect(mockMarketAnalysisMountSpy).toHaveBeenNthCalledWith(1, 'AAPL');
    expect(mockMarketAnalysisUnmountSpy).toHaveBeenCalledWith('AAPL');
    expect(mockMarketAnalysisMountSpy).toHaveBeenNthCalledWith(2, 'BTC-USD');
  });

  test('infers category label for symbols outside stock database', async () => {
    await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="GC=F"
        quote={{ symbol: 'GC=F', price: 3012.4, change: 18.2, change_percent: 0.61 }}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByText('期货')).toBeInTheDocument();
    expect(screen.getByTestId('market-analysis')).toHaveTextContent('analysis:GC=F:embed');
  });

  test('renders missing order book fields as placeholders instead of zero values', async () => {
    await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="^IXIC"
        quote={{
          symbol: '^IXIC',
          price: 18200.12,
          change: 45.2,
          change_percent: 0.25,
          bid: 0,
          ask: 0,
        }}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getAllByText('-- / --').length).toBeGreaterThan(0);
    expect(screen.getByText('点差 --')).toBeInTheDocument();
  });

  test('renders an intraday klines trend in the quote header section', async () => {
    await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{
          symbol: 'AAPL',
          price: 184.2,
          change: 3.1,
          change_percent: 2.8,
          open: 180.5,
          low: 178,
          high: 185,
          previous_close: 179,
        }}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByText('盘中走势')).toBeInTheDocument();
    expect(screen.getByLabelText('AAPL 盘中走势线')).toBeInTheDocument();
  });

  test('renders an intraday timeline when detail events are provided', async () => {
    await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{ symbol: 'AAPL', price: 184.2, change: 1.22, change_percent: 0.68 }}
        eventTimeline={[
          {
            id: 'event-1',
            sourceLabel: '实时异动',
            title: '强势拉升',
            description: 'AAPL 当前涨幅 2.80%，放量同步抬升。',
            createdAt: '2026-03-27T10:10:00.000Z',
            tone: 'positive',
            kind: 'price_up',
            priceSnapshot: 180.55,
          },
          {
            id: 'event-2',
            sourceLabel: '复盘快照',
            title: '验证有效 · 美股',
            description: '盘后复核时确认趋势延续。',
            createdAt: '2026-03-27T11:30:00.000Z',
            tone: 'warning',
          },
        ]}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByTestId('detail-event-timeline')).toBeInTheDocument();
    expect(screen.getByText('盘中时间线')).toBeInTheDocument();
    expect(screen.getByText('强势拉升')).toBeInTheDocument();
    expect(screen.getByText('AAPL 当前涨幅 2.80%，放量同步抬升。')).toBeInTheDocument();
    expect(screen.getByText('验证有效 · 美股')).toBeInTheDocument();
    expect(screen.getAllByText('后效跟踪').length).toBeGreaterThan(0);
    expect(screen.getByText('后续仍在走强')).toBeInTheDocument();
  });

  test('renders signal summary and compare mode cards', async () => {
    await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{
          symbol: 'AAPL',
          price: 184.2,
          change: 3.1,
          change_percent: 2.8,
          low: 178,
          high: 185,
          previous_close: 179,
          bid: 184.1,
          ask: 184.2,
        }}
        compareCandidates={[
          {
            symbol: 'AAPL',
            name: '苹果',
            quote: {
              symbol: 'AAPL',
              price: 184.2,
              change_percent: 2.8,
              low: 178,
              high: 185,
              previous_close: 179,
            },
          },
          {
            symbol: 'NVDA',
            name: '英伟达',
            quote: {
              symbol: 'NVDA',
              price: 910.5,
              change_percent: 1.5,
              low: 896,
              high: 918,
              previous_close: 897,
            },
          },
          {
            symbol: 'MSFT',
            name: '微软',
            quote: {
              symbol: 'MSFT',
              price: 428.8,
              change_percent: -0.4,
              low: 425,
              high: 432,
              previous_close: 430,
            },
          },
        ]}
        compareTimelineMap={{
          AAPL: [{ id: 'aapl-event', tone: 'positive' }],
          NVDA: [{ id: 'nvda-event', tone: 'positive' }],
          MSFT: [{ id: 'msft-event', tone: 'negative' }],
        }}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByTestId('detail-signal-summary')).toBeInTheDocument();
    expect(screen.getByText('信号总表')).toBeInTheDocument();
    expect(screen.getAllByText('综合分').length).toBeGreaterThan(0);
    expect(screen.getByText('对比模式')).toBeInTheDocument();
    expect(screen.getByTestId('detail-compare-grid')).toHaveTextContent('AAPL');
    expect(screen.getByTestId('detail-compare-grid')).toHaveTextContent('NVDA');
    expect(screen.getByTestId('detail-compare-grid')).toHaveTextContent('MSFT');
    expect(screen.getByRole('button', { name: 'MSFT' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'MSFT' }));

    expect(screen.getByRole('button', { name: 'MSFT' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('detail-compare-grid')).not.toHaveTextContent('MSFT');
  });

  test('shows follow-through feedback for alert-triggered timeline events', async () => {
    await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{ symbol: 'AAPL', price: 198.4, change: 2.1, change_percent: 1.07 }}
        eventTimeline={[
          {
            id: 'alert-event-1',
            sourceLabel: '提醒命中',
            title: '提醒命中 · 价格 ≥ $195.20',
            description: 'AAPL 当前价格 $195.60 已突破 $195.20',
            createdAt: '2026-03-27T14:00:00.000Z',
            tone: 'warning',
            kind: 'alert_triggered',
            condition: 'price_above',
            threshold: 195.2,
            triggerPrice: 195.6,
          },
        ]}
        onCancel={jest.fn()}
      />
    );

    expect(screen.getByText('提醒命中 · 价格 ≥ $195.20')).toBeInTheDocument();
    expect(screen.getByText('命中后仍在阈值上方')).toBeInTheDocument();
  });

  test('keeps compare selection stable when switching away and back to the same symbol', async () => {
    const { rerender } = await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{ symbol: 'AAPL', price: 184.2, change: 3.1, change_percent: 2.8 }}
        compareCandidates={[
          { symbol: 'AAPL', quote: { symbol: 'AAPL', price: 184.2, change_percent: 2.8 } },
          { symbol: 'NVDA', quote: { symbol: 'NVDA', price: 910.5, change_percent: 1.5 } },
          { symbol: 'MSFT', quote: { symbol: 'MSFT', price: 428.8, change_percent: -0.4 } },
        ]}
        onCancel={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'MSFT' }));
    expect(screen.getByTestId('detail-compare-grid')).not.toHaveTextContent('MSFT');

    rerender(
      <RealtimeStockDetailModal
        open
        symbol="BTC-USD"
        quote={{ symbol: 'BTC-USD', price: 68000, change: -220, change_percent: -0.32 }}
        compareCandidates={[
          { symbol: 'BTC-USD', quote: { symbol: 'BTC-USD', price: 68000, change_percent: -0.32 } },
          { symbol: 'ETH-USD', quote: { symbol: 'ETH-USD', price: 3600, change_percent: 1.1 } },
          { symbol: 'SOL-USD', quote: { symbol: 'SOL-USD', price: 145, change_percent: 0.8 } },
        ]}
        onCancel={jest.fn()}
      />
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    rerender(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{ symbol: 'AAPL', price: 184.2, change: 3.1, change_percent: 2.8 }}
        compareCandidates={[
          { symbol: 'AAPL', quote: { symbol: 'AAPL', price: 184.2, change_percent: 2.8 } },
          { symbol: 'NVDA', quote: { symbol: 'NVDA', price: 910.5, change_percent: 1.5 } },
          { symbol: 'MSFT', quote: { symbol: 'MSFT', price: 428.8, change_percent: -0.4 } },
        ]}
        onCancel={jest.fn()}
      />
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId('detail-compare-grid')).toHaveTextContent('NVDA');
    expect(screen.getByTestId('detail-compare-grid')).not.toHaveTextContent('MSFT');
  });

  test('filters stale compare selections when switching detail symbols', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    try {
      const { rerender } = await renderRealtimeDetailModal(
        <RealtimeStockDetailModal
          open
          symbol="ETH-USD"
          quote={{ symbol: 'ETH-USD', price: 3600, change: 40, change_percent: 1.12 }}
          compareCandidates={[
            { symbol: 'ETH-USD', quote: { symbol: 'ETH-USD', price: 3600, change_percent: 1.12 } },
            { symbol: 'BTC-USD', quote: { symbol: 'BTC-USD', price: 68000, change_percent: -0.32 } },
            { symbol: 'SOL-USD', quote: { symbol: 'SOL-USD', price: 145, change_percent: 0.8 } },
          ]}
          onCancel={jest.fn()}
        />
      );

      rerender(
        <RealtimeStockDetailModal
          open
          symbol="BTC-USD"
          quote={{ symbol: 'BTC-USD', price: 68000, change: -220, change_percent: -0.32 }}
          compareCandidates={[
            { symbol: 'BTC-USD', quote: { symbol: 'BTC-USD', price: 68000, change_percent: -0.32 } },
            { symbol: 'ETH-USD', quote: { symbol: 'ETH-USD', price: 3600, change_percent: 1.12 } },
            { symbol: 'SOL-USD', quote: { symbol: 'SOL-USD', price: 145, change_percent: 0.8 } },
          ]}
          onCancel={jest.fn()}
        />
      );

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const compareGridText = screen.getByTestId('detail-compare-grid').textContent || '';
      expect(compareGridText.match(/BTC-USD/g)?.length ?? 0).toBe(1);
      expect(
        consoleErrorSpy.mock.calls.some((call) => call.join(' ').includes('Encountered two children with the same key'))
      ).toBe(false);
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  test('can hand off a quick trade draft from the detail signal summary', async () => {
    const onQuickTrade = jest.fn();

    await renderRealtimeDetailModal(
      <RealtimeStockDetailModal
        open
        symbol="AAPL"
        quote={{
          symbol: 'AAPL',
          price: 184.2,
          change: 3.1,
          change_percent: 2.8,
          open: 180.5,
          low: 178,
          high: 185,
          previous_close: 179,
        }}
        onQuickTrade={onQuickTrade}
        onCancel={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: '带入交易' }));

    expect(onQuickTrade).toHaveBeenCalledWith(
      'AAPL',
      expect.objectContaining({
        symbol: 'AAPL',
        action: 'BUY',
        limitPrice: 184.2,
        sourceTitle: '详情页快速交易',
      })
    );
  });
});
