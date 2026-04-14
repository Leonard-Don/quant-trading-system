import { useState, useCallback, useEffect, useMemo, useRef, useDeferredValue } from 'react';

import { getGapAnalysis } from '../../services/api';
import { buildPricingPlaybook } from '../research-playbook/playbookViewModels';
import { buildMacroMispricingDraft, saveMacroMispricingDraft } from '../../utils/macroMispricingDraft';
import { buildAppUrl, readResearchContext } from '../../utils/researchContext';
import { ALIGNMENT_TAG_COLORS } from '../../utils/pricingSectionConstants';
import {
  HOT_PRICING_SYMBOLS,
  resolveAnalysisSymbol,
} from '../../utils/pricingResearch';
import usePricingScreening from './usePricingScreening';
import usePricingSearch from './usePricingSearch';
import usePricingWorkbenchActions from './usePricingWorkbenchActions';
import usePricingSensitivity from './usePricingSensitivity';
import usePricingAnalysisDetails from './usePricingAnalysisDetails';

export default function usePricingResearchData({ navigateByResearchAction }) {
  const initialResearchContext = readResearchContext() || {};
  const [symbol, setSymbol] = useState('');
  const [period, setPeriod] = useState(initialResearchContext.period || '1y');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [researchContext, setResearchContext] = useState(initialResearchContext);
  const [queueResumeHint, setQueueResumeHint] = useState('');
  const autoLoadedContextRef = useRef('');
  const handleAnalyzeRef = useRef(null);
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

  const {
    handleOpenRecentResearchTask,
    handleSuggestionSelect,
    recentResearchShortcutCards,
    recordSearchHistory,
    searchHistory,
    suggestions,
  } = usePricingSearch({
    deferredSymbolQuery,
    navigateByResearchAction,
    setPeriod,
    setSymbol,
  });

  const handleAnalyze = useCallback(async (overrideSymbol = null, overridePeriod = null) => {
    const targetSymbol = resolveAnalysisSymbol(overrideSymbol, symbol);
    const targetPeriod = typeof overridePeriod === 'string' && overridePeriod ? overridePeriod : period;
    if (!targetSymbol) return;
    setLoading(true);
    setError(null);
    setQueueResumeHint('');
    try {
      const result = await getGapAnalysis(targetSymbol, targetPeriod);
      setData(result);
      setResearchContext((prev) => ({
        ...prev,
        view: 'pricing',
        symbol: targetSymbol,
        period: targetPeriod,
      }));
      recordSearchHistory(targetSymbol);
    } catch (err) {
      setError(err.userMessage || err.message || '分析失败');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [period, recordSearchHistory, symbol]);

  const handleOpenMacroMispricingDraft = useCallback(() => {
    const thesis = data?.macro_mispricing_thesis || data?.implications?.macro_mispricing_thesis;
    if (!thesis || !Object.keys(thesis).length) return;

    const draft = buildMacroMispricingDraft({
      symbol: data?.symbol || symbol,
      thesis,
      structuralDecay: data?.structural_decay || data?.implications?.structural_decay || {},
      peopleLayer: data?.people_layer || {},
      source: 'pricing_thesis',
      note: thesis.summary || '来自定价研究的跨市场草案',
      sourceTaskType: 'pricing',
    });
    const draftId = saveMacroMispricingDraft(draft);
    if (!draftId) return;

    navigateByResearchAction({
      target: 'cross-market',
      template: draft.templateId,
      draft: draftId,
      source: 'pricing_thesis',
      note: thesis.summary || '来自定价研究的跨市场草案',
    });
  }, [data, navigateByResearchAction, symbol]);

  const canReturnToWorkbenchQueue = useMemo(
    () => (
      researchContext?.source === 'research_workbench'
      && Boolean(researchContext?.task)
      && researchContext?.workbenchQueueMode === 'pricing'
    ),
    [researchContext]
  );

  const handleReturnToWorkbenchNextTask = useCallback(() => {
    if (!canReturnToWorkbenchQueue) return;
    navigateByResearchAction({
      target: 'workbench',
      refresh: researchContext.workbenchRefresh || '',
      type: researchContext.workbenchType || '',
      sourceFilter: researchContext.workbenchSource || '',
      reason: researchContext.workbenchReason || '',
      snapshotView: researchContext.workbenchSnapshotView || '',
      snapshotFingerprint: researchContext.workbenchSnapshotFingerprint || '',
      snapshotSummary: researchContext.workbenchSnapshotSummary || '',
      keyword: researchContext.workbenchKeyword || '',
      queueMode: researchContext.workbenchQueueMode || 'pricing',
      queueAction: 'next_same_type',
      taskId: researchContext.task || '',
    }, window.location.search);
  }, [canReturnToWorkbenchQueue, navigateByResearchAction, researchContext]);

  const {
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
  } = usePricingScreening({
    handleAnalyze,
    period,
    setSymbol,
  });

  const {
    gapHistory,
    gapHistoryError,
    gapHistoryLoading,
    peerComparison,
    peerComparisonError,
    peerComparisonLoading,
  } = usePricingAnalysisDetails({
    data,
    period,
    symbol,
  });

  const {
    handleRunSensitivity,
    sensitivity: pricingSensitivity,
    sensitivityControls: pricingSensitivityControls,
    sensitivityError: pricingSensitivityError,
    sensitivityLoading: pricingSensitivityLoading,
    setSensitivityControls,
  } = usePricingSensitivity({
    data,
    researchContextSymbol: researchContext.symbol,
    symbol,
  });

  const {
    handleExportAudit,
    handleExportReport,
    handleSaveTask,
    handleUpdateSnapshot,
    savedTaskId,
    savingTask,
    setSavedTaskId,
    updatingSnapshot,
  } = usePricingWorkbenchActions({
    data,
    gapHistory,
    mergedContext,
    onSaveSuccess: () => {
      if (researchContext?.source === 'research_workbench' && researchContext?.workbenchQueueMode === 'pricing') {
        setQueueResumeHint('saved');
      }
    },
    onUpdateSnapshotSuccess: () => {
      if (researchContext?.source === 'research_workbench' && researchContext?.workbenchQueueMode === 'pricing') {
        setQueueResumeHint('snapshot');
      }
    },
    peerComparison,
    period,
    playbook,
    sensitivity: pricingSensitivity,
    symbol,
  });

  useEffect(() => {
    setQueueResumeHint('');
  }, [researchContext?.symbol, researchContext?.task]);

  useEffect(() => {
    if (
      researchContext?.source === 'research_workbench'
      && researchContext?.task
      && savedTaskId !== researchContext.task
    ) {
      setSavedTaskId(researchContext.task);
    }
  }, [researchContext?.source, researchContext?.task, savedTaskId, setSavedTaskId]);

  useEffect(() => {
    handleAnalyzeRef.current = handleAnalyze;
  }, [handleAnalyze]);

  useEffect(() => {
    const syncFromUrl = () => {
      const nextContext = readResearchContext() || {};
      setResearchContext(nextContext);
      if (nextContext.view === 'pricing' && nextContext.symbol) {
        setSymbol((prev) => (prev === nextContext.symbol ? prev : nextContext.symbol));
        setPeriod((prev) => (prev === (nextContext.period || '1y') ? prev : (nextContext.period || '1y')));
        const contextKey = `${nextContext.symbol}:${nextContext.period || '1y'}:${nextContext.source}:${nextContext.note}`;
        if (autoLoadedContextRef.current !== contextKey) {
          autoLoadedContextRef.current = contextKey;
          handleAnalyzeRef.current?.(nextContext.symbol, nextContext.period || '1y');
        }
      }
    };

    syncFromUrl();
    window.addEventListener('popstate', syncFromUrl);
    return () => window.removeEventListener('popstate', syncFromUrl);
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
      workbenchRefresh: researchContext.workbenchRefresh || undefined,
      workbenchType: researchContext.workbenchType || undefined,
      workbenchSource: researchContext.workbenchSource || undefined,
      workbenchReason: researchContext.workbenchReason || undefined,
      workbenchSnapshotView: researchContext.workbenchSnapshotView || undefined,
      workbenchSnapshotFingerprint: researchContext.workbenchSnapshotFingerprint || undefined,
      workbenchSnapshotSummary: researchContext.workbenchSnapshotSummary || undefined,
      workbenchKeyword: researchContext.workbenchKeyword || undefined,
      workbenchQueueMode: researchContext.workbenchQueueMode || undefined,
      workbenchQueueAction: researchContext.workbenchQueueAction || undefined,
      task: researchContext.task || undefined,
    });
    window.history.replaceState(null, '', nextUrl);
  }, [period, researchContext]);

  const handleKeyPress = useCallback((event) => {
    if (event.key === 'Enter') handleAnalyze();
  }, [handleAnalyze]);

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
    handleOpenMacroMispricingDraft,
    handleOpenRecentResearchTask,
    handleReturnToWorkbenchNextTask,
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
    canReturnToWorkbenchQueue,
    queueResumeHint,
    savedTaskId,
    savingTask,
    updatingSnapshot,
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
    sensitivity: pricingSensitivity,
    sensitivityControls: pricingSensitivityControls,
    sensitivityError: pricingSensitivityError,
    sensitivityLoading: pricingSensitivityLoading,
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
