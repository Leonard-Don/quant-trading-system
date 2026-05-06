import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';

import IndustryHeatmap, { buildFallbackHeatmapPayload } from '../components/IndustryHeatmap';
import { getIndustryHeatmap, getIndustryHeatmapHistory } from '../services/api';

vi.mock('../services/api', () => ({
  getIndustryHeatmap: vi.fn(),
  getIndustryHeatmapHistory: vi.fn(),
}));

describe('IndustryHeatmap history fallback', () => {
  let consoleErrorSpy;

  beforeAll(() => {
    global.ResizeObserver = class ResizeObserver {
      observe() {}
      disconnect() {}
    };
    const createMediaQueryList = (query) => {
      const mediaQueryList = {
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn((listener) => listener(mediaQueryList)),
        removeListener: vi.fn(),
        addEventListener: vi.fn((_, listener) => listener(mediaQueryList)),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      };
      return mediaQueryList;
    };
    const matchMedia = (query) => createMediaQueryList(query);
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: matchMedia,
    });
    Object.defineProperty(global, 'matchMedia', {
      writable: true,
      value: matchMedia,
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('prefers the matching timeframe snapshot when building a fallback payload', () => {
    const payload = buildFallbackHeatmapPayload({
      items: [
        {
          days: 5,
          update_time: '2026-04-17T06:00:00Z',
          max_value: 3,
          min_value: -2,
          industries: [{ name: '军工', value: 1.2 }],
        },
        {
          days: 1,
          update_time: '2026-04-17T08:00:00Z',
          max_value: 2,
          min_value: -1,
          industries: [{ name: '半导体', value: 2.1 }],
        },
      ],
    }, 1);

    expect(payload).toEqual({
      industries: [{ name: '半导体', value: 2.1 }],
      max_value: 2,
      min_value: -1,
      update_time: '2026-04-17T08:00:00Z',
    });
  });

  it('falls back to the latest history snapshot when the live heatmap request fails', async () => {
    const onDataLoad = vi.fn();
    getIndustryHeatmap.mockRejectedValueOnce(new Error('live heatmap unavailable'));
    getIndustryHeatmapHistory.mockResolvedValueOnce({
      items: [
        {
          days: 1,
          update_time: '2026-04-17T08:00:00Z',
          max_value: 2,
          min_value: -1,
          industries: [
            {
              name: '半导体',
              value: 2.1,
              size: 100,
              stockCount: 10,
              moneyFlow: 120000000,
              turnoverRate: 3.2,
              marketCapSource: 'snapshot_manual',
            },
          ],
        },
      ],
    });

    render(
      <IndustryHeatmap
        onIndustryClick={vi.fn()}
        onDataLoad={onDataLoad}
        showStats={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('最近快照')).toBeTruthy();
    });
    expect(screen.getAllByText('半导体').length).toBeGreaterThan(0);
    expect(onDataLoad).toHaveBeenCalledWith(expect.objectContaining({
      industries: expect.arrayContaining([
        expect.objectContaining({ name: '半导体', value: 2.1 }),
      ]),
      update_time: '2026-04-17T08:00:00Z',
    }));
  });

  it('uses bootstrapped heatmap data without issuing an extra live request', async () => {
    const onDataLoad = vi.fn();
    const payload = {
      industries: [
        {
          name: '军工',
          value: 1.6,
          size: 200,
          stockCount: 8,
          moneyFlow: 98000000,
          turnoverRate: 2.4,
          marketCapSource: 'snapshot_manual',
        },
      ],
      max_value: 1.6,
      min_value: 1.6,
      update_time: '2026-04-20T08:00:00Z',
    };

    render(
      <IndustryHeatmap
        onIndustryClick={vi.fn()}
        onDataLoad={onDataLoad}
        initialData={payload}
        bootstrapLoading={false}
        showStats={false}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('军工').length).toBeGreaterThan(0);
    });

    expect(getIndustryHeatmap).not.toHaveBeenCalled();
    expect(onDataLoad).toHaveBeenCalledWith(expect.objectContaining({
      industries: expect.arrayContaining([
        expect.objectContaining({ name: '军工', value: 1.6 }),
      ]),
      update_time: '2026-04-20T08:00:00Z',
    }));
  });
});
