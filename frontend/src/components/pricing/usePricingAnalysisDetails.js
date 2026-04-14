import { useEffect, useState } from 'react';

import { getPricingGapHistory, getPricingPeerComparison } from '../../services/api';
import { resolveAnalysisSymbol } from '../../utils/pricingResearch';

export default function usePricingAnalysisDetails({ data, period, symbol }) {
  const [gapHistory, setGapHistory] = useState(null);
  const [gapHistoryLoading, setGapHistoryLoading] = useState(false);
  const [gapHistoryError, setGapHistoryError] = useState(null);
  const [peerComparison, setPeerComparison] = useState(null);
  const [peerComparisonLoading, setPeerComparisonLoading] = useState(false);
  const [peerComparisonError, setPeerComparisonError] = useState(null);

  useEffect(() => {
    const targetSymbol = resolveAnalysisSymbol(data?.symbol, symbol);
    if (!data || !targetSymbol) {
      setGapHistory(null);
      setGapHistoryError(null);
      setPeerComparison(null);
      setPeerComparisonError(null);
      return;
    }

    let active = true;
    setGapHistoryLoading(true);
    setGapHistoryError(null);
    setPeerComparisonLoading(true);
    setPeerComparisonError(null);

    getPricingGapHistory(targetSymbol, period, 72)
      .then((payload) => {
        if (!active) return;
        if (payload?.error) {
          setGapHistory(null);
          setGapHistoryError(payload.error);
          return;
        }
        setGapHistory(payload);
      })
      .catch((err) => {
        if (!active) return;
        setGapHistory(null);
        setGapHistoryError(err.userMessage || err.message || '历史偏差数据加载失败');
      })
      .finally(() => {
        if (active) setGapHistoryLoading(false);
      });

    getPricingPeerComparison(targetSymbol, 5)
      .then((payload) => {
        if (!active) return;
        if (payload?.error) {
          setPeerComparison(null);
          setPeerComparisonError(payload.error);
          return;
        }
        setPeerComparison(payload);
      })
      .catch((err) => {
        if (!active) return;
        setPeerComparison(null);
        setPeerComparisonError(err.userMessage || err.message || '同行估值对比加载失败');
      })
      .finally(() => {
        if (active) setPeerComparisonLoading(false);
      });

    return () => {
      active = false;
    };
  }, [data, period, symbol]);

  return {
    gapHistory,
    gapHistoryError,
    gapHistoryLoading,
    peerComparison,
    peerComparisonError,
    peerComparisonLoading,
  };
}
