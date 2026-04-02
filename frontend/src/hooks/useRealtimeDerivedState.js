import { useMemo } from 'react';

import {
  buildRealtimeActionPosture,
  summarizeAlertHitFollowThrough,
  summarizeAlertHitHistory,
} from '../utils/realtimeSignals';

export const useRealtimeDerivedState = ({
  alertHitHistory,
  anomalyFeed,
  currentTabSymbols,
  filteredReviewSnapshots,
  getQuoteFreshness,
  quotes,
  summarizeReviewAttribution,
}) => useMemo(() => {
  const currentTabQuotes = currentTabSymbols.map((symbol) => quotes[symbol]).filter(Boolean);
  const risingCount = currentTabQuotes.filter((quote) => quote?.change > 0).length;
  const fallingCount = currentTabQuotes.filter((quote) => quote?.change < 0).length;
  const flatCount = currentTabQuotes.filter((quote) => quote?.change === 0).length;
  const loadedQuotesCount = Object.values(quotes).filter(Boolean).length;
  const spotlightSymbol = currentTabSymbols
    .filter((symbol) => quotes[symbol])
    .sort((left, right) => Math.abs(Number(quotes[right]?.change_percent || 0)) - Math.abs(Number(quotes[left]?.change_percent || 0)))[0] || null;

  const marketSentiment = (() => {
    const activeCount = risingCount + fallingCount;
    if (!activeCount) {
      return {
        label: '待观察',
        detail: '当前分组还没有足够的涨跌样本',
      };
    }

    const breadth = risingCount / activeCount;
    if (breadth >= 0.66) {
      return {
        label: '偏强',
        detail: `上涨 ${risingCount} / 下跌 ${fallingCount}`,
      };
    }
    if (breadth <= 0.34) {
      return {
        label: '偏弱',
        detail: `上涨 ${risingCount} / 下跌 ${fallingCount}`,
      };
    }
    return {
      label: '中性',
      detail: `上涨 ${risingCount} / 下跌 ${fallingCount}${flatCount > 0 ? ` / 平 ${flatCount}` : ''}`,
    };
  })();

  const freshnessSummary = currentTabQuotes.reduce((summary, quote) => {
    const freshness = getQuoteFreshness(quote);
    if (freshness.state === 'fresh') summary.fresh += 1;
    else if (freshness.state === 'aging') summary.aging += 1;
    else if (freshness.state === 'delayed') summary.delayed += 1;
    else summary.pending += 1;
    return summary;
  }, { fresh: 0, aging: 0, delayed: 0, pending: 0 });

  const reviewOutcomeSummary = filteredReviewSnapshots.reduce((summary, snapshot) => {
    if (snapshot.outcome === 'validated') {
      summary.validated += 1;
    } else if (snapshot.outcome === 'invalidated') {
      summary.invalidated += 1;
    } else if (snapshot.outcome === 'watching') {
      summary.watching += 1;
    }
    return summary;
  }, { validated: 0, invalidated: 0, watching: 0 });
  const resolvedSnapshotCount = reviewOutcomeSummary.validated + reviewOutcomeSummary.invalidated;
  const validationRate = resolvedSnapshotCount > 0
    ? `${Math.round((reviewOutcomeSummary.validated / resolvedSnapshotCount) * 100)}%`
    : '--';
  const reviewAttribution = summarizeReviewAttribution(filteredReviewSnapshots);
  const currentTabAlertHitSummary = summarizeAlertHitHistory(alertHitHistory, currentTabSymbols);
  const currentTabAlertFollowThrough = summarizeAlertHitFollowThrough(alertHitHistory, quotes, currentTabSymbols);
  const realtimeActionPosture = buildRealtimeActionPosture({
    freshnessSummary,
    alertHitSummary: currentTabAlertHitSummary,
    alertFollowThrough: currentTabAlertFollowThrough,
    anomalyCount: anomalyFeed.length,
    symbolCount: currentTabSymbols.length,
    spotlightSymbol,
  });

  return {
    currentTabQuotes,
    flatCount,
    freshnessSummary,
    loadedQuotesCount,
    marketSentiment,
    currentTabAlertFollowThrough,
    currentTabAlertHitSummary,
    realtimeActionPosture,
    resolvedSnapshotCount,
    reviewAttribution,
    reviewOutcomeSummary,
    risingCount,
    spotlightSymbol,
    validationRate,
  };
}, [
  alertHitHistory,
  anomalyFeed,
  currentTabSymbols,
  filteredReviewSnapshots,
  getQuoteFreshness,
  quotes,
  summarizeReviewAttribution,
]);
