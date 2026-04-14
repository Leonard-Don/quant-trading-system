import { act, cleanup, renderHook, waitFor } from '@testing-library/react';

import api from '../services/api';
import webSocketService from '../services/websocket';
import { normalizeQuotePayload, useRealtimeFeed } from '../hooks/useRealtimeFeed';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
  },
}));

jest.mock('../services/websocket', () => ({
  __esModule: true,
  default: {
    addListener: jest.fn(),
    connect: jest.fn(),
    subscribe: jest.fn(),
    unsubscribe: jest.fn(),
    requestSnapshot: jest.fn(),
    disconnect: jest.fn(),
  },
}));

describe('useRealtimeFeed', () => {
  const listeners = {};
  const messageApi = {
    success: jest.fn(),
    error: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    Object.keys(listeners).forEach((key) => delete listeners[key]);
    webSocketService.addListener.mockImplementation((event, callback) => {
      listeners[event] = callback;
      return jest.fn();
    });
    webSocketService.connect.mockResolvedValue(undefined);
    webSocketService.requestSnapshot.mockReturnValue(true);
    api.get.mockResolvedValue({
      data: {
        success: true,
        data: {
          '^GSPC': {
            symbol: '^GSPC',
            price: 5100,
            change_percent: 1.2,
            timestamp: '2026-04-02T10:00:00.000Z',
          },
        },
      },
    });
  });

  afterEach(async () => {
    await act(async () => {
      jest.runOnlyPendingTimers();
      await Promise.resolve();
    });
    cleanup();
    jest.useRealTimers();
  });

  test('normalizes quote payload with client and market timestamps', () => {
    const normalized = normalizeQuotePayload(
      { symbol: 'AAPL', price: 180.5, timestamp: '2026-04-02T10:00:00.000Z' },
      12345
    );

    expect(normalized._clientReceivedAt).toBe(12345);
    expect(normalized._marketTimestampMs).toBe(new Date('2026-04-02T10:00:00.000Z').getTime());
  });

  test('updates connection state and quotes from websocket listeners', async () => {
    const { result } = renderHook(() => useRealtimeFeed({
      activeTab: 'index',
      messageApi,
      resolveSymbolsByCategory: () => ['^GSPC'],
      subscribedSymbols: ['^GSPC'],
    }));

    await act(async () => {
      jest.advanceTimersByTime(100);
      await Promise.resolve();
    });

    await act(async () => {
      listeners.connection?.({ status: 'connected' });
      listeners.quote?.({
        symbol: '^GSPC',
        data: {
          symbol: '^GSPC',
          price: 5123.45,
          change_percent: 0.24,
          timestamp: '2026-04-02T10:00:00.000Z',
        },
      });
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.isConnected).toBe(true));
    expect(webSocketService.subscribe).toHaveBeenCalledWith(['^GSPC'], { forceResend: true });
    expect(result.current.quotes['^GSPC']).toEqual(expect.objectContaining({
      price: 5123.45,
      _clientReceivedAt: expect.any(Number),
      _marketTimestampMs: new Date('2026-04-02T10:00:00.000Z').getTime(),
    }));
  });

  test('prefers websocket snapshot on manual refresh when connected', async () => {
    const { result } = renderHook(() => useRealtimeFeed({
      activeTab: 'index',
      messageApi,
      resolveSymbolsByCategory: () => ['^GSPC', '^IXIC'],
      subscribedSymbols: ['^GSPC', '^IXIC'],
    }));

    await act(async () => {
      jest.advanceTimersByTime(100);
      await Promise.resolve();
    });

    await act(async () => {
      listeners.connection?.({ status: 'connected' });
      await Promise.resolve();
    });

    await act(async () => {
      result.current.refreshCurrentTab();
      await Promise.resolve();
    });

    expect(webSocketService.requestSnapshot).toHaveBeenCalledWith(['^GSPC', '^IXIC']);
    expect(result.current.transportDecisions[0]).toEqual(expect.objectContaining({
      mode: 'manual_snapshot',
    }));
  });

  test('falls back to REST refresh when websocket snapshot is unavailable', async () => {
    webSocketService.requestSnapshot.mockReturnValue(false);

    const { result } = renderHook(() => useRealtimeFeed({
      activeTab: 'index',
      messageApi,
      resolveSymbolsByCategory: () => ['^GSPC'],
      subscribedSymbols: ['^GSPC'],
    }));

    await act(async () => {
      jest.advanceTimersByTime(100);
      await Promise.resolve();
    });

    await act(async () => {
      listeners.connection?.({ status: 'connected' });
      result.current.refreshCurrentTab();
      await Promise.resolve();
    });

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/realtime/quotes', {
      params: { symbols: '^GSPC' },
    }));
    expect(result.current.transportDecisions[0]).toEqual(expect.objectContaining({
      mode: 'manual_rest',
    }));
  });
});
