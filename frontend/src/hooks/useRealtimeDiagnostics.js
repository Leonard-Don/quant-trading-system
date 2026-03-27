import { useCallback, useEffect, useState } from 'react';

import api from '../services/api';

const DIAGNOSTICS_POLL_MS = 30000;

export const useRealtimeDiagnostics = ({
  enabled,
  isConnected,
  reconnectAttempts,
}) => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastLoadedAt, setLastLoadedAt] = useState(null);

  const fetchDiagnostics = useCallback(async () => {
    if (!enabled) {
      return null;
    }

    setLoading(true);
    try {
      const response = await api.get('/realtime/summary');
      const nextSummary = response?.data?.data || null;
      setSummary(nextSummary);
      setLastLoadedAt(Date.now());
      return nextSummary;
    } catch (error) {
      console.warn('Failed to load realtime diagnostics summary:', error);
      return null;
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const timer = setInterval(() => {
      fetchDiagnostics();
    }, DIAGNOSTICS_POLL_MS);

    return () => clearInterval(timer);
  }, [enabled, fetchDiagnostics]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const timer = setTimeout(() => {
      fetchDiagnostics();
    }, 120);

    return () => clearTimeout(timer);
  }, [enabled, fetchDiagnostics, isConnected, reconnectAttempts]);

  return {
    diagnosticsSummary: summary,
    diagnosticsLoading: loading,
    diagnosticsLastLoadedAt: lastLoadedAt,
    refreshDiagnostics: fetchDiagnostics,
  };
};
