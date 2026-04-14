import { startTransition, useCallback, useMemo, useState } from 'react';

import { runPricingScreener } from '../../services/api';
import { useSafeMessageApi } from '../../utils/messageApi';
import { DEFAULT_SCREENING_UNIVERSE } from '../../utils/pricingSectionConstants';
import { parsePricingUniverseInput, sortScreeningRows } from '../../utils/pricingResearch';

export default function usePricingScreening({ handleAnalyze, period, setSymbol }) {
  const message = useSafeMessageApi();
  const [screeningUniverse, setScreeningUniverse] = useState(DEFAULT_SCREENING_UNIVERSE);
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [screeningError, setScreeningError] = useState(null);
  const [screeningResults, setScreeningResults] = useState([]);
  const [screeningMeta, setScreeningMeta] = useState(null);
  const [screeningProgress, setScreeningProgress] = useState({ completed: 0, total: 0, running: false });
  const [screeningFilter, setScreeningFilter] = useState('all');
  const [screeningSector, setScreeningSector] = useState('all');
  const [screeningMinScore, setScreeningMinScore] = useState(0);

  const filteredScreeningResults = useMemo(() => (
    screeningResults.filter((item) => {
      if (screeningFilter === 'undervalued' && item.primary_view !== '低估') return false;
      if (screeningFilter === 'high-confidence' && Number(item.confidence_score || 0) < 0.72) return false;
      if (screeningFilter === 'aligned' && item.factor_alignment_status !== 'aligned') return false;
      if (screeningFilter === 'governance-risk' && Number(item.people_governance_discount_pct || 0) < 5) return false;
      if (screeningFilter === 'governance-support' && Number(item.people_governance_discount_pct || 0) > -3) return false;
      if (screeningSector !== 'all' && (item.sector || '未知板块') !== screeningSector) return false;
      if (Number(item.screening_score || 0) < Number(screeningMinScore || 0)) return false;
      return true;
    })
  ), [screeningFilter, screeningMinScore, screeningResults, screeningSector]);

  const screeningSectors = useMemo(() => {
    const sectors = Array.from(new Set(screeningResults.map((item) => item.sector || '未知板块').filter(Boolean)));
    return sectors.sort();
  }, [screeningResults]);

  const handleRunScreener = useCallback(async () => {
    const symbols = parsePricingUniverseInput(screeningUniverse);
    if (!symbols.length) {
      message.warning('请先输入至少一个股票代码');
      return;
    }

    setScreeningLoading(true);
    setScreeningError(null);
    setScreeningResults([]);
    setScreeningProgress({ completed: 0, total: symbols.length, running: true });
    try {
      const payload = await runPricingScreener(
        symbols,
        period,
        Math.min(10, symbols.length),
        Math.min(3, symbols.length)
      );
      const sorted = sortScreeningRows(
        (payload?.results || []).map((row) => ({
          ...row,
          sector: row?.sector || '',
        }))
      );
      setScreeningResults(sorted);
      setScreeningMeta({
        analyzedCount: Number(payload?.analyzed_count || sorted.length),
        totalInput: Number(payload?.total_input || symbols.length),
        failureCount: Number((payload?.failures || []).length),
        failures: payload?.failures || [],
      });
      setScreeningProgress({ completed: symbols.length, total: symbols.length, running: false });
    } catch (err) {
      setScreeningError(err.userMessage || err.message || '候选池筛选失败');
      setScreeningResults([]);
      setScreeningMeta(null);
    } finally {
      setScreeningLoading(false);
      setScreeningProgress((prev) => ({ ...prev, running: false }));
    }
  }, [message, period, screeningUniverse]);

  const handleInspectScreeningResult = useCallback((record) => {
    if (!record?.symbol) return;
    startTransition(() => {
      setSymbol(record.symbol);
    });
    handleAnalyze(record.symbol, period);
  }, [handleAnalyze, period, setSymbol]);

  const handleApplyPreset = useCallback((symbols) => {
    setScreeningUniverse(symbols.join('\n'));
  }, []);

  const handleExportScreening = useCallback(() => {
    if (!screeningResults.length) return;
    const header = ['Rank', 'Symbol', 'Company', 'Score', 'View', 'GapPct', 'GovernanceDiscountPct', 'GovernanceLabel', 'Confidence', 'Alignment', 'Driver'];
    const rows = screeningResults.map((item) => [
      item.rank,
      item.symbol,
      item.company_name || '',
      item.screening_score,
      item.primary_view || '',
      item.gap_pct ?? '',
      item.people_governance_discount_pct ?? '',
      item.people_governance_label || '',
      item.confidence_score ?? '',
      item.factor_alignment_label || '',
      item.primary_driver || '',
    ]);
    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `pricing-screener-${period}.csv`;
    link.click();
    window.URL.revokeObjectURL(url);
  }, [period, screeningResults]);

  return {
    filteredScreeningResults,
    handleApplyPreset,
    handleExportScreening,
    handleInspectScreeningResult,
    handleRunScreener,
    screeningError,
    screeningFilter,
    screeningLoading,
    screeningMeta,
    screeningMinScore,
    screeningProgress,
    screeningResults,
    screeningSector,
    screeningSectors,
    screeningUniverse,
    setScreeningFilter,
    setScreeningMinScore,
    setScreeningSector,
    setScreeningUniverse,
  };
}
