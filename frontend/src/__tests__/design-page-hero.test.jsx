import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PageHero from '../design/components/PageHero';

describe('PageHero', () => {
  test('renders eyebrow, title, subtitle and the metrics slot', () => {
    render(
      <PageHero
        eyebrow="RESEARCH · 研究工作台"
        title="策略回测工作台"
        subtitle="一体化回测流"
        metrics={<div data-testid="kpis">kpis</div>}
      />,
    );
    expect(screen.getByText('RESEARCH · 研究工作台')).toBeTruthy();
    expect(screen.getByRole('heading', { name: '策略回测工作台' })).toBeTruthy();
    expect(screen.getByText('一体化回测流')).toBeTruthy();
    expect(screen.getByTestId('kpis')).toBeTruthy();
  });
});
