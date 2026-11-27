import React from 'react';
import { render, waitFor } from '@testing-library/react';
import PerformanceChart from '../components/PerformanceChart';

vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => React.cloneElement(children, { width: 800, height: 440 }),
  };
});

describe('PerformanceChart endpoint marker', () => {
  beforeAll(() => {
    global.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
    window.matchMedia = window.matchMedia || ((query) => ({
      matches: false,
      media: query,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    }));
  });

  test('places the latest net-value marker from the axis scales', async () => {
    const { container } = render(
      <PerformanceChart
        data={[
          { date: '2024-01-01', total: 10000, price: 100, signal: 0 },
          { date: '2024-01-02', total: 10200, price: 101, signal: 0 },
          { date: '2024-01-03', total: 10400, price: 102, signal: 0 },
        ]}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.backtest-chart-endpoint__ripple')).toBeTruthy();
    });
    const ripple = container.querySelector('.backtest-chart-endpoint__ripple');
    expect(Number(ripple.getAttribute('cx'))).toBeGreaterThan(0);
    expect(Number(ripple.getAttribute('cy'))).toBeGreaterThan(0);
    expect(container.querySelector('.backtest-chart-endpoint__label').textContent).toBe('$10,400');
  });
});
