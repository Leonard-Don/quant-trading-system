import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

import MonthlyHeatmap, { buildMonthlyReturnTable } from '../components/MonthlyHeatmap';

describe('buildMonthlyReturnTable', () => {
  test('derives monthly returns from portfolio totals when returns are missing', () => {
    const table = buildMonthlyReturnTable([
      { date: '2024-01-02', total: 10000 },
      { date: '2024-01-31', total: 11000 },
      { date: '2024-02-01', total: 11220 },
      { date: '2024-02-29', total: 12100 },
    ]);

    expect(table['2024'][0]).toBeCloseTo(0.1, 6);
    expect(table['2024'][1]).toBeCloseTo(0.1, 6);
  });

  test('falls back to compounding daily returns when portfolio totals are unavailable', () => {
    const table = buildMonthlyReturnTable([
      { date: '2024-03-01', returns: 0.1 },
      { date: '2024-03-04', returns: -0.05 },
    ]);

    expect(table['2024'][2]).toBeCloseTo(0.045, 6);
  });
});

describe('MonthlyHeatmap', () => {
  test('renders computed monthly values from portfolio history totals', () => {
    render(
      <MonthlyHeatmap
        data={[
          { date: '2024-01-02', total: 10000 },
          { date: '2024-01-31', total: 11000 },
          { date: '2024-02-01', total: 11220 },
          { date: '2024-02-29', total: 12100 },
        ]}
      />
    );

    expect(screen.getByText('2024')).toBeInTheDocument();
    expect(screen.getAllByText('10.0%')).toHaveLength(2);
    expect(screen.getByText('21.00%')).toBeInTheDocument();
  });
});
