import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatCard from '../design/components/StatCard';

describe('StatCard', () => {
  test('renders label and value with tabular numerals', () => {
    render(<StatCard label="待处理" value="10" />);
    expect(screen.getByText('待处理')).toBeTruthy();
    const value = screen.getByText('10');
    expect(value.className).toContain('tabular-nums');
  });

  test('applies accent class when accent is set', () => {
    render(<StatCard label="回测快照" value="24" accent />);
    expect(screen.getByText('24').className).toContain('text-accent');
  });
});
