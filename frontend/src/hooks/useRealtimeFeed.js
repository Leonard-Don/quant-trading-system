import { useCallback, useEffect, useRef, useState } from 'react';

import api from '../services/api';
import webSocketService from '../services/websocket';

const QUOTE_FRESHNESS_TICK_MS = 15000;

export const normalizeQuotePayload = (quote, receivedAt = Date.now()) => ({
  ...quote,
  _clientReceivedAt: receivedAt,
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
  const [freshnessNow, setFreshnessNow] = useState(Date.now());
  const [lastMarketUpdateAt, setLastMarketUpdateAt] = useState(null);
  const [hasEverConnected, setHasEverConnected] = useState(false);
  const [hasExperiencedFallback, setHasExperiencedFallback] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastConnectionIssue, setLastConnectionIssue] = useState('');

  const isInitializedRef = useRef(false);
  const shownMessagesRef = useRef(new Set());
  const previousSubscribedSymbolsRef = useRef(new Set());
  const connectTimerRef = useRef(null);
  const missingQuoteRequestsRef = useRef(new Set());

  useEffect(() => {
    const removeConnectionListener = webSocketService.addListener('connection', (data) => {
      setIsConnected(data.status === 'connected');
      if (data.status === 'connected') {
        setHasEverConnected(true);
        setReconnectAttempts(0);
        setLastConnectionIssue('');
        setLoading(false);
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
      setLastMarketUpdateAt(receivedAt);
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
    const previousSymbols = previousSubscribedSymbolsRef.current;
    const nextSymbols = new Set(subscribedSymbols);

    const addedSymbols = subscribedSymbols.filter(symbol => !previousSymbols.has(symbol));
    const removedSymbols = Array.from(previousSymbols).filter(symbol => !nextSymbols.has(symbol));

    if (addedSymbols.length > 0) {
      webSocketService.subscribe(addedSymbols);
    }

    if (removedSymbols.length > 0) {
      webSocketService.unsubscribe(removedSymbols);
    }

    previousSubscribedSymbolsRef.current = nextSymbols;
  }, [subscribedSymbols]);

  useEffect(() => {
    const timer = setInterval(() => {
      setFreshnessNow(Date.now());
    }, QUOTE_FRESHNESS_TICK_MS);

    return () => clearInterval(timer);
  }, []);

  const clearMissingQuoteRequests = useCallback((symbols = []) => {
    const targetSymbols = Array.isArray(symbols) ? symbols : [symbols];
    targetSymbols
      .filter(Boolean)
      .forEach(symbol => missingQuoteRequestsRef.current.delete(String(symbol).trim().toUpperCase()));
  }, []);

  const fetchQuotes = useCallback(async (symbols = subscribedSymbols) => {
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
          setLastMarketUpdateAt(receivedAt);
        }
        setQuotes(prev => ({ ...prev, ...normalizedQuotes }));
      }
    } catch (error) {
      console.error('获取初始数据失败:', error);
    } finally {
      setLoading(false);
    }
  }, [clearMissingQuoteRequests, subscribedSymbols]);

  useEffect(() => {
    if (isInitializedRef.current) return;
    isInitializedRef.current = true;
    fetchQuotes(resolveSymbolsByCategory(activeTab));

    return () => {};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const missingSymbols = resolveSymbolsByCategory(activeTab).filter(
      symbol => !quotes[symbol] && !missingQuoteRequestsRef.current.has(symbol)
    );
    if (missingSymbols.length > 0) {
      missingSymbols.forEach(symbol => missingQuoteRequestsRef.current.add(symbol));
      fetchQuotes(missingSymbols);
    }
  }, [activeTab, fetchQuotes, quotes, resolveSymbolsByCategory]);

  const refreshCurrentTab = useCallback(() => {
    const symbolsInCurrentTab = resolveSymbolsByCategory(activeTab);
    clearMissingQuoteRequests(symbolsInCurrentTab);
    fetchQuotes(symbolsInCurrentTab);
  }, [activeTab, clearMissingQuoteRequests, fetchQuotes, resolveSymbolsByCategory]);

  const removeQuote = useCallback((symbol) => {
    clearMissingQuoteRequests([symbol]);
    setQuotes(prev => {
      const next = { ...prev };
      delete next[symbol];
      return next;
    });
  }, [clearMissingQuoteRequests]);

  return {
    clearMissingQuoteRequests,
    fetchQuotes,
    freshnessNow,
    hasEverConnected,
    hasExperiencedFallback,
    isAutoUpdate,
    isConnected,
    lastConnectionIssue,
    lastMarketUpdateAt,
    loading,
    quotes,
    reconnectAttempts,
    refreshCurrentTab,
    removeQuote,
    setIsAutoUpdate,
  };
};
