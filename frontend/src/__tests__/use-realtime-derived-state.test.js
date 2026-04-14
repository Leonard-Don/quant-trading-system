import { renderHook } from '@testing-library/react';

import { useRealtimeDerivedState } from '../hooks/useRealtimeDerivedState';

describe('useRealtimeDerivedState', () => {
  test('derives transport summary and market sentiment for realtime hero', () => {
    const { result } = renderHook(() => useRealtimeDerivedState({
      alertHitHistory: [
        { symbol: '^GSPC', triggerTime: '2026-04-09T08:00:00.000Z', followThroughState: 'continued' },
      ],
      anomalyFeed: [{ id: 'anomaly-1' }, { id: 'anomaly-2' }],
      currentTabSymbols: ['^GSPC', '^IXIC'],
      filteredReviewSnapshots: [
        { outcome: 'validated', activeTab: 'index', spotlightSymbol: '^GSPC' },
      ],
      getQuoteFreshness: (quote) => ({
        state: quote.symbol === '^GSPC' ? 'fresh' : 'aging',
      }),
      hasEverConnected: true,
      hasExperiencedFallback: true,
      isAutoUpdate: true,
      isConnected: true,
      lastClientRefreshAt: '2026-04-09T08:01:00.000Z',
      lastConnectionIssue: '',
      lastMarketUpdateAt: '2026-04-09T08:00:30.000Z',
      freshnessNow: Date.now(),
      quotes: {
        '^GSPC': { symbol: '^GSPC', change: 10, change_percent: 1.2 },
        '^IXIC': { symbol: '^IXIC', change: -5, change_percent: -0.6 },
      },
      reconnectAttempts: 0,
    }));

    expect(result.current.marketSentiment).toEqual({
      label: '中性',
      detail: '上涨 1 / 下跌 1',
    });
    expect(result.current.freshnessSummary).toEqual({
      fresh: 1,
      aging: 1,
      delayed: 0,
      pending: 0,
    });
    expect(result.current.transportModeLabel).toBe('WebSocket 实时');
    expect(result.current.transportBanner.title).toBe('实时推送已恢复');
    expect(result.current.transportBannerStyle.color).toBe('#166534');
    // formatQuoteTime is now a module-scope function, producing locale time strings
    expect(result.current.lastClientRefreshLabel).not.toBe('--');
    expect(result.current.lastMarketUpdateLabel).not.toBe('--');
    expect(result.current.realtimeActionPosture.title).toBeDefined();
  });
});
