import { useState, useCallback, useEffect, useMemo, useRef, startTransition, useDeferredValue } from 'react';
import { message } from 'antd';

import {
  addResearchTaskSnapshot,
  createResearchTask,
  getGapAnalysis,
  getPricingGapHistory,
  getPricingPeerComparison,
  getPricingSymbolSuggestions,
  getResearchTasks,
  getValuationSensitivityAnalysis,
} from '../../services/api';
import { buildPricingPlaybook, buildPricingWorkbenchPayload } from '../research-playbook/playbookViewModels';
import { buildAppUrl, readResearchContext } from '../../utils/researchContext';
import { ALIGNMENT_TAG_COLORS, DEFAULT_SCREENING_UNIVERSE } from '../../utils/pricingSectionConstants';
import {
  buildRecentPricingResearchEntries,
  buildScreeningRowFromAnalysis,
  HOT_PRICING_SYMBOLS,
  mergePricingSuggestions,
  parsePricingUniverseInput,
  resolveAnalysisSymbol,
  sortScreeningRows,
} from '../../utils/pricingResearch';
import { exportToJSON } from '../../utils/export';
import {
  buildPricingResearchAuditPayload,
  buildPricingResearchReportHtml,
  openPricingResearchPrintWindow,
} from '../../utils/pricingResearchReport';

const SEARCH_HISTORY_KEY = 'pricing-research-history';

export default function usePricingResearchData({ navigateByResearchAction }) {
  const initialResearchContext = readResearchContext() || {};
  const [symbol, setSymbol] = useState('');
  const [period, setPeriod] = useState(initialResearchContext.period || '1y');
  const [loading, setLoading] = useState(false);
  const [savingTask, setSavingTask] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [researchContext, setResearchContext] = useState(initialResearchContext);
  const [savedTaskId, setSavedTaskId] = useState('');
  const [screeningUniverse, setScreeningUniverse] = useState(DEFAULT_SCREENING_UNIVERSE);
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [screeningError, setScreeningError] = useState(null);
  const [screeningResults, setScreeningResults] = useState([]);
  const [screeningMeta, setScreeningMeta] = useState(null);
  const [screeningProgress, setScreeningProgress] = useState({ completed: 0, total: 0, running: false });
  const [screeningFilter, setScreeningFilter] = useState('all');
  const [screeningSector, setScreeningSector] = useState('all');
  const [screeningMinScore, setScreeningMinScore] = useState(0);
  const [suggestions, setSuggestions] = useState([]);
  const [searchHistory, setSearchHistory] = useState([]);
  const [recentResearchEntries, setRecentResearchEntries] = useState([]);
  const [sensitivity, setSensitivity] = useState(null);
  const [sensitivityLoading, setSensitivityLoading] = useState(false);
  const [sensitivityError, setSensitivityError] = useState(null);
  const [gapHistory, setGapHistory] = useState(null);
  const [gapHistoryLoading, setGapHistoryLoading] = useState(false);
  const [gapHistoryError, setGapHistoryError] = useState(null);
  const [peerComparison, setPeerComparison] = useState(null);
  const [peerComparisonLoading, setPeerComparisonLoading] = useState(false);
  const [peerComparisonError, setPeerComparisonError] = useState(null);
  const [sensitivityControls, setSensitivityControls] = useState({
    wacc: 8.2,
    initialGrowth: 12,
    terminalGrowth: 2.5,
    fcfMargin: 80,
  });
  const autoLoadedContextRef = useRef('');
  const deferredSymbolQuery = useDeferredValue(symbol);

  const mergedContext = useMemo(
    () => ({
      ...researchContext,
      symbol: researchContext.symbol || symbol,
    }),
    [researchContext, symbol]
  );

  const playbook = useMemo(
    () => buildPricingPlaybook(mergedContext, data),
    [mergedContext, data]
  );

  const filteredScreeningResults = useMemo(() => {
    return screeningResults.filter((item) => {
      if (screeningFilter === 'undervalued' && item.primary_view !== '低估') return false;
      if (screeningFilter === 'high-confidence' && Number(item.confidence_score || 0) < 0.72) return false;
      if (screeningFilter === 'aligned' && item.factor_alignment_status !== 'aligned') return false;
      if (screeningSector !== 'all' && (item.sector || '未知板块') !== screeningSector) return false;
      if (Number(item.screening_score || 0) < Number(screeningMinScore || 0)) return false;
      return true;
    });
  }, [screeningFilter, screeningMinScore, screeningResults, screeningSector]);

  const screeningSectors = useMemo(() => {
    const sectors = Array.from(new Set(screeningResults.map((item) => item.sector || '未知板块').filter(Boolean)));
    return sectors.sort();
  }, [screeningResults]);

  const handleOpenRecentResearchTask = useCallback((entry = {}) => {
    const taskId = entry?.taskId || entry?.task_id || '';
    if (taskId) {
      navigateByResearchAction({
        target: 'workbench',
        type: 'pricing',
        sourceFilter: 'research_workbench',
        reason: 'recent_pricing_search',
        taskId,
      });
      return;
    }
    if (entry?.period) setPeriod(entry.period);
    if (entry?.symbol) setSymbol(entry.symbol);
  }, [navigateByResearchAction]);

  const handleSuggestionSelect = useCallback((value, option) => {
    const taskId = option?.taskId || option?.task_id || '';
    if (taskId) {
      handleOpenRecentResearchTask({
        taskId,
        symbol: value,
        period: option?.period || '',
      });
      return;
    }
    setSymbol(value);
  }, [handleOpenRecentResearchTask]);

  const recentResearchShortcuts = useMemo(
    () => recentResearchEntries.slice(0, 4),
    [recentResearchEntries]
  );

  const recentResearchShortcutCards = useMemo(
    () => recentResearchShortcuts.map((item) => ({
      ...item,
      title: item.headline || item.title || `${item.symbol} 定价研究`,
      subtitle: [
        item.primary_view || '',
        item.confidence_label ? `置信度 ${item.confidence_label}` : '',
        item.factor_alignment_label || '',
        item.period ? `窗口 ${item.period}` : '',
      ].filter(Boolean).join(' · '),
    })),
    [recentResearchShortcuts]
  );

  const handleAnalyze = useCallback(async (overrideSymbol = null, overridePeriod = null) => {
    const targetSymbol = resolveAnalysisSymbol(overrideSymbol, symbol);
    const targetPeriod = typeof overridePeriod === 'string' && overridePeriod ? overridePeriod : period;
    if (!targetSymbol) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getGapAnalysis(targetSymbol, targetPeriod);
      setData(result);
      setResearchContext((prev) => ({
        ...prev,
        view: 'pricing',
        symbol: targetSymbol,
        period: targetPeriod,
      }));
      setSearchHistory((prev) => {
        const next = [targetSymbol, ...prev.filter((item) => item !== targetSymbol)].slice(0, 8);
        try {
          window.localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next));
        } catch (storageError) {
          console.debug('unable to persist pricing history', storageError);
        }
        return next;
      });
    } catch (err) {
      setError(err.userMessage || err.message || '分析失败');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, period]);

  useEffect(() => {
    const syncFromUrl = () => {
      const nextContext = readResearchContext() || {};
      setResearchContext(nextContext);
      if (nextContext.view === 'pricing' && nextContext.symbol) {
        setSymbol(nextContext.symbol);
        setPeriod(nextContext.period || '1y');
        const contextKey = `${nextContext.symbol}:${nextContext.period || '1y'}:${nextContext.source}:${nextContext.note}`;
        if (autoLoadedContextRef.current !== contextKey) {
          autoLoadedContextRef.current = contextKey;
          handleAnalyze(nextContext.symbol, nextContext.period || '1y');
        }
      }
    };

    syncFromUrl();
    window.addEventListener('popstate', syncFromUrl);
    return () => window.removeEventListener('popstate', syncFromUrl);
  }, [handleAnalyze]);

  useEffect(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(SEARCH_HISTORY_KEY) || '[]');
      if (Array.isArray(stored)) setSearchHistory(stored.filter(Boolean));
    } catch (storageError) {
      console.debug('unable to read pricing history', storageError);
    }
  }, []);

  useEffect(() => {
    let active = true;
    getResearchTasks({ limit: 40, type: 'pricing' })
      .then((payload) => {
        if (!active) return;
        const rows = payload?.data || [];
        setRecentResearchEntries(buildRecentPricingResearchEntries(rows).slice(0, 12));
      })
      .catch(() => {
        if (active) setRecentResearchEntries([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (researchContext?.view !== 'pricing') return;
    const nextUrl = buildAppUrl({
      currentSearch: window.location.search,
      view: 'pricing',
      symbol: researchContext.symbol || undefined,
      source: researchContext.source || undefined,
      note: researchContext.note || undefined,
      action: researchContext.action || undefined,
      period,
    });
    window.history.replaceState(null, '', nextUrl);
  }, [period, researchContext]);

  useEffect(() => {
    let active = true;
    const query = String(deferredSymbolQuery || '').trim();
    const preferredEntries = [
      ...buildRecentPricingResearchEntries(searchHistory.map((item) => ({ symbol: item }))),
      ...recentResearchEntries,
    ];
    getPricingSymbolSuggestions(query, 8)
      .then((payload) => {
        if (!active) return;
        const mergedSuggestions = mergePricingSuggestions(payload.data || [], preferredEntries, query);
        const options = mergedSuggestions.map((item) => ({
          value: item.symbol,
          taskId: item.task_id || '',
          period: item.period || '',
          labelMeta: item,
          label: item.symbol,
          richLabel: {
            recent: item.recent,
            primaryView: item.primary_view,
            confidenceLabel: item.confidence_label,
            factorAlignmentLabel: item.factor_alignment_label,
            factorAlignmentStatus: item.factor_alignment_status,
            name: item.name,
            group: item.group,
            market: item.market,
            period: item.period,
            headline: item.headline,
            summary: item.summary,
            primaryDriver: item.primary_driver,
            taskId: item.task_id,
          },
        }));
        setSuggestions(options);
      })
      .catch(() => {
        if (active) setSuggestions([]);
      });
    return () => {
      active = false;
    };
  }, [deferredSymbolQuery, recentResearchEntries, searchHistory]);

  useEffect(() => {
    const anchor = data?.valuation?.dcf?.sensitivity_anchor;
    if (!anchor) return;
    setSensitivityControls({
      wacc: Number((anchor.wacc || 0) * 100).toFixed(1) * 1,
      initialGrowth: Number((anchor.initial_growth || 0) * 100).toFixed(1) * 1,
      terminalGrowth: Number((anchor.terminal_growth || 0) * 100).toFixed(1) * 1,
      fcfMargin: Number((anchor.fcf_margin || 0) * 100).toFixed(0) * 1,
    });
  }, [data]);

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

  const handleKeyPress = useCallback((event) => {
    if (event.key === 'Enter') handleAnalyze();
  }, [handleAnalyze]);

  const handleSaveTask = useCallback(async () => {
    const payload = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
    );
    if (!payload) {
      message.error('请先输入标的后再保存到研究工作台');
      return;
    }

    setSavingTask(true);
    try {
      const response = await createResearchTask(payload);
      setSavedTaskId(response.data?.id || '');
      message.success(`已保存到研究工作台: ${response.data?.title || payload.title}`);
    } catch (err) {
      message.error(err.userMessage || err.message || '保存研究任务失败');
    } finally {
      setSavingTask(false);
    }
  }, [data, mergedContext, period, playbook]);

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
      const concurrency = Math.min(4, symbols.length);
      const rows = [];
      const failures = [];
      let completed = 0;
      let pointer = 0;

      const worker = async () => {
        while (pointer < symbols.length) {
          const currentIndex = pointer;
          pointer += 1;
          const currentSymbol = symbols[currentIndex];
          try {
            const analysis = await getGapAnalysis(currentSymbol, period);
            rows.push(buildScreeningRowFromAnalysis(analysis, period));
            setScreeningResults(sortScreeningRows(rows));
          } catch (err) {
            failures.push({
              symbol: currentSymbol,
              error: err.userMessage || err.message || '分析失败',
            });
          } finally {
            completed += 1;
            setScreeningProgress({ completed, total: symbols.length, running: completed < symbols.length });
          }
        }
      };

      await Promise.all(Array.from({ length: concurrency }, () => worker()));
      const sorted = sortScreeningRows(rows);
      setScreeningResults(sorted);
      setScreeningMeta({
        analyzedCount: sorted.length,
        totalInput: symbols.length,
        failureCount: failures.length,
        failures,
      });
    } catch (err) {
      setScreeningError(err.userMessage || err.message || '候选池筛选失败');
      setScreeningResults([]);
      setScreeningMeta(null);
    } finally {
      setScreeningLoading(false);
      setScreeningProgress((prev) => ({ ...prev, running: false }));
    }
  }, [period, screeningUniverse]);

  const handleInspectScreeningResult = useCallback((record) => {
    if (!record?.symbol) return;
    startTransition(() => {
      setSymbol(record.symbol);
    });
    handleAnalyze(record.symbol, period);
  }, [handleAnalyze, period]);

  const handleRunSensitivity = useCallback(async () => {
    const targetSymbol = resolveAnalysisSymbol(symbol, researchContext.symbol || '');
    if (!targetSymbol) {
      message.warning('请先选择一个标的再做敏感性分析');
      return;
    }

    setSensitivityLoading(true);
    setSensitivityError(null);
    try {
      const payload = await getValuationSensitivityAnalysis({
        symbol: targetSymbol,
        wacc: Number(sensitivityControls.wacc) / 100,
        initial_growth: Number(sensitivityControls.initialGrowth) / 100,
        terminal_growth: Number(sensitivityControls.terminalGrowth) / 100,
        fcf_margin: Number(sensitivityControls.fcfMargin) / 100,
        dcf_weight: data?.valuation?.fair_value?.dcf_weight,
        comparable_weight: data?.valuation?.fair_value?.comparable_weight,
      });
      setSensitivity(payload);
    } catch (err) {
      setSensitivityError(err.userMessage || err.message || '敏感性分析失败');
      setSensitivity(null);
    } finally {
      setSensitivityLoading(false);
    }
  }, [data?.valuation?.fair_value?.comparable_weight, data?.valuation?.fair_value?.dcf_weight, researchContext.symbol, sensitivityControls, symbol]);

  const handleApplyPreset = useCallback((symbols) => {
    setScreeningUniverse(symbols.join('\n'));
  }, []);

  const handleExportScreening = useCallback(() => {
    if (!screeningResults.length) return;
    const header = ['Rank', 'Symbol', 'Company', 'Score', 'View', 'GapPct', 'Confidence', 'Alignment', 'Driver'];
    const rows = screeningResults.map((item) => [
      item.rank,
      item.symbol,
      item.company_name || '',
      item.screening_score,
      item.primary_view || '',
      item.gap_pct ?? '',
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

  const handleExportReport = useCallback(() => {
    if (!data) {
      message.warning('请先完成一次定价分析');
      return;
    }

    try {
      const snapshot = buildPricingWorkbenchPayload(
        { ...mergedContext, period },
        data,
        playbook
      )?.snapshot?.payload || null;
      const reportHtml = buildPricingResearchReportHtml({
        symbol: resolveAnalysisSymbol(data?.symbol, symbol),
        period,
        generatedAt: new Date().toLocaleString(),
        analysis: data,
        snapshot,
        context: mergedContext,
        sensitivity,
        history: gapHistory,
        peerComparison,
      });
      const opened = openPricingResearchPrintWindow(reportHtml);
      if (!opened) {
        message.error('无法打开打印窗口，请检查浏览器弹窗设置');
        return;
      }
      message.success('已打开打印窗口，可直接另存为 PDF');
    } catch (exportError) {
      message.error(exportError.message || '导出研究报告失败');
    }
  }, [data, gapHistory, mergedContext, peerComparison, period, playbook, sensitivity, symbol]);

  const handleExportAudit = useCallback(() => {
    if (!data) {
      message.warning('请先完成一次定价分析');
      return;
    }

    const snapshot = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
    )?.snapshot?.payload || null;
    const payload = buildPricingResearchAuditPayload({
      symbol: resolveAnalysisSymbol(data?.symbol, symbol),
      period,
      context: mergedContext,
      analysis: data,
      snapshot,
      playbook,
      sensitivity,
      history: gapHistory,
      peerComparison,
    });
    exportToJSON(payload, `pricing-research-audit-${payload.symbol || 'unknown'}-${period}`);
    message.success('已导出审计 JSON');
  }, [data, gapHistory, mergedContext, peerComparison, period, playbook, sensitivity, symbol]);

  const handleUpdateSnapshot = useCallback(async () => {
    if (!savedTaskId) {
      message.info('请先保存任务，再更新当前任务快照');
      return;
    }

    const payload = buildPricingWorkbenchPayload(
      { ...mergedContext, period },
      data,
      playbook
    );
    if (!payload?.snapshot) {
      message.error('当前还没有可更新的研究快照');
      return;
    }

    setSavingTask(true);
    try {
      await addResearchTaskSnapshot(savedTaskId, { snapshot: payload.snapshot });
      message.success('当前任务快照已更新');
    } catch (err) {
      message.error(err.userMessage || err.message || '更新任务快照失败');
    } finally {
      setSavingTask(false);
    }
  }, [data, mergedContext, period, playbook, savedTaskId]);

  return {
    data,
    error,
    filteredScreeningResults,
    gapHistory,
    gapHistoryError,
    gapHistoryLoading,
    handleAnalyze,
    handleApplyPreset,
    handleExportAudit,
    handleExportReport,
    handleExportScreening,
    handleInspectScreeningResult,
    handleKeyPress,
    handleOpenRecentResearchTask,
    handleRunScreener,
    handleRunSensitivity,
    handleSaveTask,
    handleSuggestionSelect,
    handleUpdateSnapshot,
    HOT_PRICING_SYMBOLS,
    loading,
    mergedContext,
    peerComparison,
    peerComparisonError,
    peerComparisonLoading,
    period,
    playbook,
    recentResearchShortcutCards,
    researchContext,
    savedTaskId,
    savingTask,
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
    searchHistory,
    sensitivity,
    sensitivityControls,
    sensitivityError,
    sensitivityLoading,
    setPeriod,
    setScreeningFilter,
    setScreeningMinScore,
    setScreeningSector,
    setScreeningUniverse,
    setSensitivityControls,
    setSymbol,
    suggestions,
    symbol,
    suggestionTagColors: ALIGNMENT_TAG_COLORS,
  };
}
