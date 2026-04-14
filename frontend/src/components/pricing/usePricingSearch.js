import { useCallback, useEffect, useMemo, useState } from 'react';

import { getPricingSymbolSuggestions, getResearchTasks } from '../../services/api';
import {
  buildRecentPricingResearchEntries,
  mergePricingSuggestions,
} from '../../utils/pricingResearch';

const SEARCH_HISTORY_KEY = 'pricing-research-history';

export default function usePricingSearch({
  deferredSymbolQuery,
  navigateByResearchAction,
  setPeriod,
  setSymbol,
}) {
  const [suggestions, setSuggestions] = useState([]);
  const [searchHistory, setSearchHistory] = useState([]);
  const [recentResearchEntries, setRecentResearchEntries] = useState([]);

  const recordSearchHistory = useCallback((targetSymbol) => {
    setSearchHistory((prev) => {
      const next = [targetSymbol, ...prev.filter((item) => item !== targetSymbol)].slice(0, 8);
      try {
        window.localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next));
      } catch (storageError) {
        console.debug('unable to persist pricing history', storageError);
      }
      return next;
    });
  }, []);

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
  }, [navigateByResearchAction, setPeriod, setSymbol]);

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
  }, [handleOpenRecentResearchTask, setSymbol]);

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

  return {
    handleOpenRecentResearchTask,
    handleSuggestionSelect,
    recentResearchShortcutCards,
    recordSearchHistory,
    searchHistory,
    suggestions,
  };
}
