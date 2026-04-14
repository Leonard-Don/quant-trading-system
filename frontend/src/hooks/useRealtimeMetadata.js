import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import api from '../services/api';

const normalizeMetadataEntry = (symbol, entry) => {
  if (typeof symbol !== 'string' || !symbol.trim()) {
    return null;
  }

  const normalizedSymbol = symbol.trim().toUpperCase();
  const metadata = entry && typeof entry === 'object' ? entry : {};
  return {
    symbol: normalizedSymbol,
    en: typeof metadata.en === 'string' && metadata.en.trim() ? metadata.en.trim() : normalizedSymbol,
    cn: typeof metadata.cn === 'string' && metadata.cn.trim() ? metadata.cn.trim() : (metadata.en || normalizedSymbol),
    type: typeof metadata.type === 'string' && metadata.type.trim() ? metadata.type.trim() : null,
    source: typeof metadata.source === 'string' ? metadata.source : 'dynamic',
  };
};

export const useRealtimeMetadata = ({
  subscribedSymbols,
  knownMetadataMap = {},
}) => {
  const [metadataMap, setMetadataMap] = useState({});
  const requestedSymbolsRef = useRef(new Set());

  const mergeMetadata = useCallback((payload) => {
    if (!payload || typeof payload !== 'object') {
      return;
    }

    setMetadataMap((prev) => {
      const next = { ...prev };
      Object.entries(payload).forEach(([symbol, entry]) => {
        const normalized = normalizeMetadataEntry(symbol, entry);
        if (normalized) {
          next[normalized.symbol] = normalized;
          requestedSymbolsRef.current.add(normalized.symbol);
        }
      });
      return next;
    });
  }, []);

  const fetchMetadata = useCallback(async (symbols) => {
    const normalizedSymbols = Array.from(new Set(
      (Array.isArray(symbols) ? symbols : [symbols])
        .filter((symbol) => typeof symbol === 'string')
        .map((symbol) => symbol.trim().toUpperCase())
        .filter(Boolean)
    ));

    const pendingSymbols = normalizedSymbols.filter((symbol) => !requestedSymbolsRef.current.has(symbol));
    if (pendingSymbols.length === 0) {
      return {};
    }

    pendingSymbols.forEach((symbol) => requestedSymbolsRef.current.add(symbol));

    try {
      const response = await api.get('/realtime/metadata', {
        params: {
          symbols: pendingSymbols.join(','),
        },
      });
      const nextData = response?.data?.data || {};
      mergeMetadata(nextData);
      return nextData;
    } catch (error) {
      pendingSymbols.forEach((symbol) => requestedSymbolsRef.current.delete(symbol));
      console.warn('Failed to load realtime metadata:', error);
      return {};
    }
  }, [mergeMetadata]);

  const metadataSymbols = useMemo(() => (
    subscribedSymbols.filter((symbol) => !metadataMap[symbol] && !knownMetadataMap[symbol])
  ), [knownMetadataMap, metadataMap, subscribedSymbols]);

  useEffect(() => {
    if (metadataSymbols.length === 0) {
      return;
    }

    fetchMetadata(metadataSymbols);
  }, [fetchMetadata, metadataSymbols]);

  return {
    metadataMap,
    fetchMetadata,
    mergeMetadata,
  };
};
