import { useCallback, useEffect, useRef, useState } from 'react';

import api from '../services/api';
import webSocketService from '../services/websocket';

const QUOTE_FRESHNESS_TICK_MS = 15000;
const WS_CONNECT_WARMUP_MS = 40;
const WS_SNAPSHOT_GRACE_MS = 180;

const toTimestampMs = (value) => {
  if (!value) {
    return null;
  }

  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? null : parsed;
};

export const normalizeQuotePayload = (quote, receivedAt = Date.now()) => ({
  ...quote,
  _clientReceivedAt: receivedAt,
  _marketTimestampMs: toTimestampMs(quote?.timestamp),
});

export const useRealtimeFeed = ({
  activeTab,
  messageApi,
  resolveSymbolsByCategory,
  subscribedSymbols,
}) => {
  const [quotes, setQuotes] = useState({});
  const [isConnected, setIsConnected] = useState(false);
  const [isAutoUpdate, setIsAutoUpdate] = useState(true);
  const [loading, setLoading] = useState(false);
  const [transportDecisions, setTransportDecisions] = useState([]);
  const [freshnessNow, setFreshnessNow] = useState(Date.now());
  const [lastMarketUpdateAt, setLastMarketUpdateAt] = useState(null);
  const [lastClientRefreshAt, setLastClientRefreshAt] = useState(null);
  const [hasEverConnected, setHasEverConnected] = useState(false);
  const [hasExperiencedFallback, setHasExperiencedFallback] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastConnectionIssue, setLastConnectionIssue] = useState('');
  const [isBrowserOnline, setIsBrowserOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );

  const isInitializedRef = useRef(false);
  const shownMessagesRef = useRef(new Set());
  const previousSubscribedSymbolsRef = useRef(new Set());
  const currentTabSymbolsRef = useRef(resolveSymbolsByCategory(activeTab));
  const connectTimerRef = useRef(null);
  const missingQuoteRequestsRef = useRef(new Set());
  const currentTabFallbackTimerRef = useRef(null);
  const currentTabWarmupTimerRef = useRef(null);
  const quotesRef = useRef({});

  useEffect(() => {
    quotesRef.current = quotes;
  }, [quotes]);

  useEffect(() => {
    currentTabSymbolsRef.current = resolveSymbolsByCategory(activeTab);
  }, [activeTab, resolveSymbolsByCategory]);

  const pushTransportDecision = useCallback((mode, symbols = [], note = '') => {
    const normalizedSymbols = (Array.isArray(symbols) ? symbols : [symbols])
      .filter(Boolean)
      .map(symbol => String(symbol).trim().toUpperCase());

    setTransportDecisions((prev) => {
      const next = [
        {
          id: `${Date.now()}-${mode}-${normalizedSymbols.join('-')}`,
          mode,
          symbols: normalizedSymbols,
          note,
          timestamp: Date.now(),
        },
        ...prev,
      ];
      return next.slice(0, 6);
    });
  }, []);

  useEffect(() => {
    const removeConnectionListener = webSocketService.addListener('connection', (data) => {
      setIsConnected(data.status === 'connected');
      if (data.status === 'connected') {
        setHasEverConnected(true);
        setReconnectAttempts(0);
        setLastConnectionIssue('');
        setLoading(false);
        if (currentTabSymbolsRef.current.length > 0) {
          webSocketService.subscribe(currentTabSymbolsRef.current, { forceResend: true });
        }
        if (!shownMessagesRef.current.has('connected')) {
          shownMessagesRef.current.add('connected');
          messageApi.success('实时数据连接已建立');
        }
      } else if (data.status === 'reconnecting' || data.status === 'disconnected') {
        setHasExperiencedFallback(true);
        setReconnectAttempts(data.reconnectAttempts || 0);
        setLastConnectionIssue(data.lastError || '');
      }
    });

    const removeQuoteListener = webSocketService.addListener('quote', (data) => {
      const { symbol, data: quoteData } = data;
      const receivedAt = Date.now();
      const normalizedQuote = normalizeQuotePayload(quoteData, receivedAt);
      setLoading(false);
      setLastClientRefreshAt(receivedAt);
      setLastMarketUpdateAt(normalizedQuote._marketTimestampMs || receivedAt);
      setQuotes(prev => ({
        ...prev,
        [symbol]: normalizedQuote,
      }));
    });

    const removeErrorListener = webSocketService.addListener('error', (data) => {
      console.error('WebSocket Error:', data.error);
      setIsConnected(false);
      setLastConnectionIssue(data.reason || data.error?.message || 'WebSocket error');
    });

    return () => {
      removeConnectionListener();
      removeQuoteListener();
      removeErrorListener();
      if (currentTabFallbackTimerRef.current) {
        clearTimeout(currentTabFallbackTimerRef.current);
        currentTabFallbackTimerRef.current = null;
      }
      if (currentTabWarmupTimerRef.current) {
        clearTimeout(currentTabWarmupTimerRef.current);
        currentTabWarmupTimerRef.current = null;
      }
      webSocketService.disconnect({ resetSubscriptions: true });
    };
  }, [messageApi]);

  useEffect(() => {
    if (isAutoUpdate) {
      if (connectTimerRef.current) {
        clearTimeout(connectTimerRef.current);
      }

      connectTimerRef.current = setTimeout(() => {
        webSocketService.connect().catch((error) => {
          console.error('Failed to connect WS:', error);
          messageApi.error('无法建立实时数据连接');
        });
      }, 80);
    } else {
      if (connectTimerRef.current) {
        clearTimeout(connectTimerRef.current);
        connectTimerRef.current = null;
      }
      webSocketService.disconnect();
      setIsConnected(false);
    }

    return () => {
      if (connectTimerRef.current) {
        clearTimeout(connectTimerRef.current);
        connectTimerRef.current = null;
      }
    };
  }, [isAutoUpdate, messageApi]);

  useEffect(() => {
    const handleOnline = () => {
      setIsBrowserOnline(true);
      if (isAutoUpdate && !webSocketService.isConnected) {
        webSocketService.manualReconnect().catch(() => {});
      }
    };
    const handleOffline = () => {
      setIsBrowserOnline(false);
      setLastConnectionIssue('浏览器离线');
    };
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [isAutoUpdate]);

  useEffect(() => {
    const currentTabSymbols = resolveSymbolsByCategory(activeTab);
    const previousSymbols = previousSubscribedSymbolsRef.current;
    const nextSymbols = new Set(currentTabSymbols);

    const addedSymbols = currentTabSymbols.filter(symbol => !previousSymbols.has(symbol));
    const removedSymbols = Array.from(previousSymbols).filter(symbol => !nextSymbols.has(symbol));

    if (addedSymbols.length > 0) {
      webSocketService.subscribe(addedSymbols);
    }

    if (removedSymbols.length > 0) {
      webSocketService.unsubscribe(removedSymbols);
    }

    previousSubscribedSymbolsRef.current = nextSymbols;
  }, [activeTab, resolveSymbolsByCategory]);

  useEffect(() => {
    if (!isAutoUpdate) return;
    const timer = setInterval(() => {
      setFreshnessNow(Date.now());
    }, QUOTE_FRESHNESS_TICK_MS);

    return () => clearInterval(timer);
  }, [isAutoUpdate]);

  const clearMissingQuoteRequests = useCallback((symbols = []) => {
    const targetSymbols = Array.isArray(symbols) ? symbols : [symbols];
    targetSymbols
      .filter(Boolean)
      .forEach(symbol => missingQuoteRequestsRef.current.delete(String(symbol).trim().toUpperCase()));
  }, []);

  const fetchQuotes = useCallback(async (symbols = subscribedSymbols, options = {}) => {
    const isEventLike = symbols && typeof symbols === 'object' && (
      typeof symbols.preventDefault === 'function'
      || typeof symbols.stopPropagation === 'function'
      || symbols.nativeEvent
    );
    const normalizedSymbols = isEventLike ? subscribedSymbols : symbols;
    const targetSymbols = (Array.isArray(normalizedSymbols) ? normalizedSymbols : [normalizedSymbols])
      .filter(Boolean)
      .map(symbol => String(symbol).trim().toUpperCase());
    if (!targetSymbols.length) return;
    if (options.reason) {
      pushTransportDecision(options.reason, targetSymbols, options.note || '');
    }

    setLoading(true);
    try {
      const response = await api.get('/realtime/quotes', {
        params: { symbols: targetSymbols.join(',') },
      });

      if (response.data.success) {
        clearMissingQuoteRequests(Object.keys(response.data.data || {}));
        const receivedAt = Date.now();
        const normalizedQuotes = Object.fromEntries(
          Object.entries(response.data.data || {}).map(([symbol, quote]) => [
            symbol,
            normalizeQuotePayload(quote, receivedAt),
          ])
        );
        if (Object.keys(normalizedQuotes).length > 0) {
          setLastClientRefreshAt(receivedAt);
          const latestMarketTimestamp = Object.values(normalizedQuotes).reduce((latest, quote) => {
            return Math.max(latest, quote._marketTimestampMs || 0);
          }, 0);
          setLastMarketUpdateAt(latestMarketTimestamp || receivedAt);
        }
        setQuotes(prev => ({ ...prev, ...normalizedQuotes }));
      }
    } catch (error) {
      console.error('获取初始数据失败:', error);
    } finally {
      clearMissingQuoteRequests(targetSymbols);
      setLoading(false);
    }
  }, [clearMissingQuoteRequests, pushTransportDecision, subscribedSymbols]);

  const scheduleCurrentTabFallbackFetch = useCallback((delayMs = WS_SNAPSHOT_GRACE_MS) => {
    if (currentTabFallbackTimerRef.current) {
      clearTimeout(currentTabFallbackTimerRef.current);
    }

    const symbolsInCurrentTab = resolveSymbolsByCategory(activeTab);
    if (!symbolsInCurrentTab.length) {
      return;
    }

    currentTabFallbackTimerRef.current = setTimeout(() => {
      const missingSymbols = symbolsInCurrentTab.filter(
        symbol => !quotesRef.current[symbol] && !missingQuoteRequestsRef.current.has(symbol)
      );
      if (missingSymbols.length > 0) {
        missingSymbols.forEach(symbol => missingQuoteRequestsRef.current.add(symbol));
        fetchQuotes(missingSymbols, { reason: 'rest_fallback', note: 'snapshot grace miss' });
      }
    }, delayMs);
  }, [activeTab, fetchQuotes, resolveSymbolsByCategory]);

  const scheduleCurrentTabWarmupSnapshot = useCallback((delayMs = WS_CONNECT_WARMUP_MS) => {
    if (currentTabWarmupTimerRef.current) {
      clearTimeout(currentTabWarmupTimerRef.current);
    }

    const symbolsInCurrentTab = resolveSymbolsByCategory(activeTab);
    if (!symbolsInCurrentTab.length || !isConnected) {
      return;
    }

    currentTabWarmupTimerRef.current = setTimeout(() => {
      const missingSymbols = symbolsInCurrentTab.filter(symbol => !quotesRef.current[symbol]);
      if (missingSymbols.length > 0 && webSocketService.requestSnapshot(missingSymbols)) {
        pushTransportDecision('warmup_snapshot', missingSymbols, 'post-connect warmup');
        setLoading(true);
      }
    }, delayMs);
  }, [activeTab, isConnected, pushTransportDecision, resolveSymbolsByCategory]);

  useEffect(() => {
    if (!isInitializedRef.current) {
      isInitializedRef.current = true;
    }

    if (isAutoUpdate && isConnected) {
      scheduleCurrentTabWarmupSnapshot();
    }
    scheduleCurrentTabFallbackFetch(isAutoUpdate ? WS_SNAPSHOT_GRACE_MS : 0);

    return () => {
      if (currentTabFallbackTimerRef.current) {
        clearTimeout(currentTabFallbackTimerRef.current);
        currentTabFallbackTimerRef.current = null;
      }
      if (currentTabWarmupTimerRef.current) {
        clearTimeout(currentTabWarmupTimerRef.current);
        currentTabWarmupTimerRef.current = null;
      }
    };
  }, [
    activeTab,
    isAutoUpdate,
    isConnected,
    scheduleCurrentTabFallbackFetch,
    scheduleCurrentTabWarmupSnapshot,
    subscribedSymbols,
  ]);

  const refreshCurrentTab = useCallback(() => {
    const symbolsInCurrentTab = resolveSymbolsByCategory(activeTab);
    clearMissingQuoteRequests(symbolsInCurrentTab);
    if (isConnected && webSocketService.requestSnapshot(symbolsInCurrentTab)) {
      pushTransportDecision('manual_snapshot', symbolsInCurrentTab, 'manual refresh');
      setLoading(true);
      scheduleCurrentTabFallbackFetch(WS_SNAPSHOT_GRACE_MS);
      return;
    }

    fetchQuotes(symbolsInCurrentTab, { reason: 'manual_rest', note: 'manual refresh fallback' });
  }, [
    activeTab,
    clearMissingQuoteRequests,
    fetchQuotes,
    isConnected,
    pushTransportDecision,
    resolveSymbolsByCategory,
    scheduleCurrentTabFallbackFetch,
  ]);

  const removeQuote = useCallback((symbol) => {
    clearMissingQuoteRequests([symbol]);
    setQuotes(prev => {
      const next = { ...prev };
      delete next[symbol];
      return next;
    });
  }, [clearMissingQuoteRequests]);

  const manualReconnect = useCallback(() => {
    setReconnectAttempts(0);
    setLastConnectionIssue('');
    webSocketService.manualReconnect().then(() => {
      messageApi.success('手动重连成功');
    }).catch(() => {
      messageApi.error('手动重连失败，将继续自动重试');
    });
  }, [messageApi]);

  return {
    clearMissingQuoteRequests,
    fetchQuotes,
    freshnessNow,
    hasEverConnected,
    hasExperiencedFallback,
    isAutoUpdate,
    isBrowserOnline,
    isConnected,
    lastConnectionIssue,
    lastClientRefreshAt,
    lastMarketUpdateAt,
    loading,
    manualReconnect,
    quotes,
    reconnectAttempts,
    refreshCurrentTab,
    removeQuote,
    setIsAutoUpdate,
    transportDecisions,
  };
};
