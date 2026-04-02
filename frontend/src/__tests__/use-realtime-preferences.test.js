import { act, renderHook, waitFor } from '@testing-library/react';

import api from '../services/api';
import { useRealtimePreferences } from '../hooks/useRealtimePreferences';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    put: jest.fn(),
  },
}));

describe('useRealtimePreferences', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    window.localStorage.clear();
    api.get.mockResolvedValue({
      data: {
        success: true,
        data: {
          symbols: ['AAPL', 'MSFT'],
          active_tab: 'us',
          symbol_categories: {},
        },
      },
    });
    api.put.mockResolvedValue({ data: { success: true } });
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  test('hydrates preferences from backend when local state is unchanged', async () => {
    const { result } = renderHook(() => useRealtimePreferences({
      defaultSymbols: ['^GSPC'],
      defaultActiveTab: 'index',
    }));

    await waitFor(() => expect(result.current.activeTab).toBe('us'));
    expect(result.current.subscribedSymbols).toEqual(['AAPL', 'MSFT']);
  });

  test('persists updated preferences to backend after debounce', async () => {
    const { result } = renderHook(() => useRealtimePreferences({
      defaultSymbols: ['^GSPC'],
      defaultActiveTab: 'index',
    }));

    await waitFor(() => expect(result.current.activeTab).toBe('us'));

    act(() => {
      result.current.setActiveTab('crypto');
      result.current.setSubscribedSymbols(['BTC-USD', 'ETH-USD']);
    });

    await act(async () => {
      jest.advanceTimersByTime(600);
      await Promise.resolve();
    });

    expect(api.put).toHaveBeenCalledWith(
      '/realtime/preferences',
      expect.objectContaining({
        active_tab: 'crypto',
        symbols: ['BTC-USD', 'ETH-USD'],
      }),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Realtime-Profile': expect.any(String),
        }),
      })
    );
  });
});
