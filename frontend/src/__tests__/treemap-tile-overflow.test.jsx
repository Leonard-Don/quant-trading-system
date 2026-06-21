import { describe, test, expect, beforeAll, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import IndustryHeatmap, { buildFallbackHeatmapPayload } from '../components/IndustryHeatmap';

// Mirror the exact shape used in industry-heatmap.test.js (camelCase fields).
// A single wide/tall industry forces the "large block" path (leader pill + market cap row).
const ONE_BIG_INDUSTRY = {
  industries: [
    {
      name: '半导体',
      value: 2.29,
      size: 1119070000000,
      stockCount: 179,
      leadingStock: '晶升股份这是一个很长的龙头股名称用于触发省略',
      leadingStockChange: 3.5,
      leadingStockPrice: 45.2,
      leadingStockSymbol: '688049',
      moneyFlow: 5_000_000_000,
      marketCapSource: 'live',
      turnoverRate: 2.4,
    },
  ],
  max_value: 2.29,
  min_value: 2.29,
  update_time: '2026-06-21T08:00:00Z',
};

describe('treemap tile text does not overflow', () => {
  beforeAll(() => {
    global.ResizeObserver = class ResizeObserver {
      observe() {}
      disconnect() {}
    };
  });

  beforeEach(() => {
    // Keep the auto-refresh poll inert (same pattern as industry-heatmap.test.js)
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  });

  test('leader-stock name uses shrink+ellipsis styles so it cannot overflow the pill', async () => {
    render(
      <IndustryHeatmap
        initialData={ONE_BIG_INDUSTRY}
        bootstrapLoading={false}
        showStats={false}
        onIndustryClick={() => {}}
        onTimeframeChange={() => {}}
      />,
    );
    const tile = await screen.findByTestId('heatmap-tile');
    const leader = tile.querySelector('[data-testid="heatmap-leader-name"]');
    expect(leader).toBeTruthy();
    expect(leader.style.textOverflow).toBe('ellipsis');
    expect(leader.style.overflow).toBe('hidden');
    expect(leader.style.minWidth).toBe('0px');
  });
});
