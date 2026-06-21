import { describe, test, expect } from 'vitest';
import { getChartTheme } from '../design/chartTheme';

describe('getChartTheme', () => {
  test('dark theme exposes up/down/accent/grid/axis + a series array', () => {
    const t = getChartTheme(true);
    expect(t.up).toBe('#34d399');
    expect(t.down).toBe('#f87171');
    expect(t.accent).toBe('#38bdf8');
    expect(Array.isArray(t.series)).toBe(true);
    expect(t.series.length).toBeGreaterThanOrEqual(3);
  });

  test('light theme swaps to the light palette', () => {
    expect(getChartTheme(false).up).toBe('#059669');
  });
});
