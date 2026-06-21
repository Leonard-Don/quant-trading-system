import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MetricGrid from '../design/components/MetricGrid';

describe('MetricGrid', () => {
  test('renders children inside a grid container', () => {
    render(<MetricGrid><div>a</div><div>b</div></MetricGrid>);
    const grid = screen.getByTestId('metric-grid');
    expect(grid.className).toContain('grid');
    expect(grid.childElementCount).toBe(2);
  });
});
