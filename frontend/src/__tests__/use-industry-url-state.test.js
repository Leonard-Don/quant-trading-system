import { act, renderHook, waitFor } from '@testing-library/react';

import useIndustryUrlState from '../components/industry/useIndustryUrlState';

describe('useIndustryUrlState', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/?view=industry');
  });

  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  test('preserves a local heatmap search term while syncing it into the URL', async () => {
    const { result } = renderHook(() => useIndustryUrlState());

    act(() => {
      result.current.setHeatmapViewState((previous) => ({
        ...previous,
        searchTerm: '房地',
      }));
    });

    await waitFor(() => {
      expect(result.current.heatmapViewState.searchTerm).toBe('房地');
    });

    await waitFor(() => {
      expect(new URLSearchParams(window.location.search).get('industry_search')).toBe('房地');
    });
  });

  test('hydrates heatmap search state from external browser navigation', async () => {
    const { result } = renderHook(() => useIndustryUrlState());

    act(() => {
      window.history.pushState(
        null,
        '',
        `/?view=industry&industry_search=${encodeURIComponent('新能源')}`,
      );
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    await waitFor(() => {
      expect(result.current.heatmapViewState.searchTerm).toBe('新能源');
    });
  });
});
