import React from 'react';
import { fireEvent, render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';

import BacktestDashboard from '../components/BacktestDashboard';

vi.mock('../components/StrategyForm', () => ({ default: () => <div>StrategyForm</div> }));
vi.mock('../components/ResultsDisplay', () => ({ default: () => <div>ResultsDisplay</div> }));
vi.mock('../components/LoadingSpinner', () => ({ default: () => <div>LoadingSpinner</div> }));
vi.mock('../components/CrossMarketBacktestPanel', () => ({ default: () => <div>CrossMarketBacktestPanel</div> }));
vi.mock('../components/BacktestHistory', () => ({ default: () => <div>BacktestHistory</div> }));
vi.mock('../components/StrategyComparison', () => ({ default: () => <div>StrategyComparison</div> }));
vi.mock('../components/PortfolioOptimizer', () => ({ default: () => <div>PortfolioOptimizer</div> }));
vi.mock('../components/BacktestDataHealthPanel', () => ({ default: () => <div>BacktestDataHealthPanel</div> }));
vi.mock('../components/AdvancedBacktestLab', () => ({ default: ({ onImportTemplateToMainBacktest }) => (
  <div>
    <div>AdvancedBacktestLab</div>
    <button type="button" onClick={() => onImportTemplateToMainBacktest?.({ symbol: 'AAPL' })}>
      import-template
    </button>
  </div>
) }));

vi.mock('antd', () => {
  const React = require('react');
  return {
    Card: ({ children, title, extra }) => (
      <div>
        <div>{title}</div>
        <div>{extra}</div>
        <div>{children}</div>
      </div>
    ),
    Tabs: ({ activeKey, items, onChange }) => {
      const activeItem = items.find((item) => item.key === activeKey) || items[0];
      return (
        <div>
          <div>
            {items.map((item) => (
              <button key={item.key} type="button" onClick={() => onChange(item.key)}>
                {typeof item.label === 'string' ? item.label : item.key}
              </button>
            ))}
          </div>
          <div>{activeItem?.children}</div>
        </div>
      );
    },
    Spin: () => <div>Spin</div>,
    Space: ({ children }) => <div>{children}</div>,
    Tag: ({ children }) => <span>{children}</span>,
    Typography: {
      Title: ({ children }) => <div>{children}</div>,
      Paragraph: ({ children }) => <div>{children}</div>,
    },
  };
});


describe('BacktestDashboard', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  test('syncs active tab with browser history changes', async () => {
    window.history.replaceState(null, '', '/?tab=history');

    render(
      <BacktestDashboard
        strategies={[{ name: 'buy_and_hold' }]}
        onSubmit={vi.fn()}
        loading={false}
        results={null}
      />
    );

    expect(await screen.findByText('BacktestHistory')).toBeInTheDocument();

    await act(async () => {
      window.history.pushState(null, '', '/?tab=comparison');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    await waitFor(() => {
      expect(screen.getByText('StrategyComparison')).toBeInTheDocument();
    });
  });

  test('pushes tab changes into the URL so they can be revisited', async () => {
    render(
      <BacktestDashboard
        strategies={[{ name: 'buy_and_hold' }]}
        onSubmit={vi.fn()}
        loading={false}
        results={null}
      />
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'comparison' }));
    });

    await waitFor(() => {
      expect(window.location.search).toContain('tab=comparison');
    });
    expect(await screen.findByText('StrategyComparison')).toBeInTheDocument();
  });

  test('supports the advanced experiments tab from URL state', async () => {
    window.history.replaceState(null, '', '/?tab=advanced');

    render(
      <BacktestDashboard
        strategies={[{ name: 'buy_and_hold' }]}
        onSubmit={vi.fn()}
        loading={false}
        results={null}
      />
    );

    expect(await screen.findByText('AdvancedBacktestLab')).toBeInTheDocument();
  });

  test('returns to the main backtest tab when importing a template from advanced experiments', async () => {
    window.history.replaceState(null, '', '/?tab=advanced');

    render(
      <BacktestDashboard
        strategies={[{ name: 'buy_and_hold' }]}
        onSubmit={vi.fn()}
        loading={false}
        results={null}
      />
    );

    fireEvent.click(await screen.findByRole('button', { name: 'import-template' }));

    await waitFor(() => {
      expect(window.location.search).not.toContain('tab=advanced');
      expect(screen.getByText('StrategyForm')).toBeInTheDocument();
    });
  });
});
