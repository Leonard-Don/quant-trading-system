import { useMemo } from 'react';

import {
  buildRealtimeActionPosture,
  summarizeAlertHitFollowThrough,
  summarizeAlertHitHistory,
} from '../utils/realtimeSignals';

const formatQuoteTime = (value) => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const summarizeReviewAttribution = (snapshots = []) => {
  const validatedMarkets = new Map();
  const invalidatedSignals = new Map();
  const spotlightSymbols = new Map();

  snapshots.forEach((snapshot) => {
    if (snapshot.spotlightSymbol) {
      const current = spotlightSymbols.get(snapshot.spotlightSymbol) || {
        label: snapshot.spotlightName || snapshot.spotlightSymbol,
        count: 0,
      };
      current.count += 1;
      spotlightSymbols.set(snapshot.spotlightSymbol, current);
    }
    if (snapshot.outcome === 'validated' && snapshot.activeTabLabel) {
      validatedMarkets.set(snapshot.activeTabLabel, (validatedMarkets.get(snapshot.activeTabLabel) || 0) + 1);
    }
    if (snapshot.outcome === 'invalidated') {
      (snapshot.anomalies || []).forEach((anomaly) => {
        if (!anomaly?.title) return;
        invalidatedSignals.set(anomaly.title, (invalidatedSignals.get(anomaly.title) || 0) + 1);
      });
    }
  });

  const pickTop = (entries, formatter) => {
    const sorted = [...entries.entries()].sort((left, right) => right[1] - left[1]);
    return sorted.length ? formatter(sorted[0][0], sorted[0][1]) : '--';
  };

  return {
    topValidatedMarket: pickTop(validatedMarkets, (label, count) => `${label} · ${count} 次有效`),
    topInvalidatedSignal: pickTop(invalidatedSignals, (label, count) => `${label} · ${count} 次失效`),
    topSpotlightSymbol: pickTop(spotlightSymbols, (symbol, meta) => `${meta.label} · ${meta.count} 次聚焦`),
  };
};

export { formatQuoteTime, summarizeReviewAttribution };

export const useRealtimeDerivedState = ({
  alertHitHistory,
  anomalyFeed,
  currentTabSymbols,
  filteredReviewSnapshots,
  hasEverConnected,
  hasExperiencedFallback,
  isAutoUpdate,
  isConnected,
  lastClientRefreshAt,
  lastConnectionIssue,
  lastMarketUpdateAt,
  freshnessNow,
  getQuoteFreshness,
  quotes,
  reconnectAttempts,
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
  const transportModeLabel = !isAutoUpdate
    ? '手动刷新'
    : isConnected
      ? 'WebSocket 实时'
      : reconnectAttempts > 0
        ? '重连中 / REST 补数'
        : '连接中 / REST 补数';
  const lastClientRefreshLabel = lastClientRefreshAt ? formatQuoteTime(lastClientRefreshAt) : '--';
  const lastMarketUpdateLabel = lastMarketUpdateAt ? formatQuoteTime(lastMarketUpdateAt) : '--';
  const transportBanner = !isAutoUpdate
    ? {
        tone: 'manual',
        title: '自动更新已关闭',
        description: '当前只会在你手动点击刷新时拉取最新行情，适合临时暂停实时更新。',
      }
    : isConnected
      ? {
          tone: 'healthy',
          title: hasExperiencedFallback ? '实时推送已恢复' : '实时推送正常',
          description: hasExperiencedFallback
            ? 'WebSocket 已重新接管实时更新，列表会继续自动推进。'
            : '当前由 WebSocket 持续推送最新行情，REST 只在首屏和补数时兜底。',
        }
      : reconnectAttempts > 0
        ? {
            tone: 'fallback',
            title: '正在重连实时推送',
            description: `当前已切到 REST 补数，第 ${reconnectAttempts} 次重连进行中。${lastConnectionIssue ? ` 最近异常：${lastConnectionIssue}` : ''}`,
          }
        : {
            tone: 'fallback',
            title: hasEverConnected ? '已降级到 REST 补数' : '正在建立实时连接',
            description: hasEverConnected
              ? `实时推送暂时不可用，页面会先用 REST 补数维持更新，连接恢复后会自动切回实时模式。${lastConnectionIssue ? ` 最近异常：${lastConnectionIssue}` : ''}`
              : '在 WebSocket 建立前，页面会先通过 REST 拉取当前分组行情，避免首屏空白。',
          };
  const transportBannerStyle = transportBanner.tone === 'healthy'
    ? {
        color: '#166534',
        background: 'rgba(34, 197, 94, 0.14)',
        borderColor: 'rgba(34, 197, 94, 0.24)',
      }
    : transportBanner.tone === 'manual'
      ? {
          color: '#1d4ed8',
          background: 'rgba(59, 130, 246, 0.12)',
          borderColor: 'rgba(59, 130, 246, 0.2)',
        }
      : {
          color: '#b45309',
          background: 'rgba(245, 158, 11, 0.14)',
          borderColor: 'rgba(245, 158, 11, 0.26)',
        };

  return {
    currentTabQuotes,
    flatCount,
    freshnessSummary,
    loadedQuotesCount,
    marketSentiment,
    currentTabAlertFollowThrough,
    currentTabAlertHitSummary,
    lastClientRefreshLabel,
    lastMarketUpdateLabel,
    realtimeActionPosture,
    resolvedSnapshotCount,
    reviewAttribution,
    reviewOutcomeSummary,
    risingCount,
    spotlightSymbol,
    transportBanner,
    transportBannerStyle,
    transportModeLabel,
    validationRate,
  };
}, [
  alertHitHistory,
  anomalyFeed,
  currentTabSymbols,
  filteredReviewSnapshots,
  hasEverConnected,
  hasExperiencedFallback,
  isAutoUpdate,
  isConnected,
  lastClientRefreshAt,
  lastConnectionIssue,
  lastMarketUpdateAt,
  getQuoteFreshness,
  quotes,
  reconnectAttempts,
]);
