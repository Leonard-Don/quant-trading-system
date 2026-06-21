import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Toolbar, Surface, Panel, PageHero, StatCard, MetricGrid, SectionHeader, StatusPill } from '../design/components';

describe('Toolbar + barrel', () => {
  test('Toolbar renders children in a flex row', () => {
    render(<Toolbar><button>前 30</button><button>全部</button></Toolbar>);
    const bar = screen.getByTestId('toolbar');
    expect(bar.className).toContain('flex');
    expect(bar.childElementCount).toBe(2);
  });

  test('barrel exports every primitive', () => {
    expect(Surface).toBeTruthy();
    expect(Panel).toBeTruthy();
    expect(PageHero).toBeTruthy();
    expect(StatCard).toBeTruthy();
    expect(MetricGrid).toBeTruthy();
    expect(SectionHeader).toBeTruthy();
    expect(StatusPill).toBeTruthy();
  });
});
