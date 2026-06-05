import { useCallback, useRef } from 'react';

import { hasNumericValue, inferSymbolCategory } from '../utils/realtimeFormatters';
import {
  buildRealtimeShareDocument,
  formatReviewSnapshotShareHtml,
  formatReviewSummaryShareHtml,
} from '../utils/realtimeShareTemplates';
import {
  getSnapshotOutcomeMeta,
} from '../utils/realtimePanelHelpers';
import {
  REALTIME_EXPORT_VERSION,
  REVIEW_SNAPSHOT_VERSION,
} from '../utils/realtimePanelConstants';
import {
  MAX_REVIEW_SNAPSHOTS,
  MAX_TIMELINE_EVENTS,
  normalizeReviewSnapshot,
  normalizeTimelineEvent,
} from './useRealtimeJournal';

/**
 * Review-snapshot orchestration extracted from RealTimePanel.
 *
 * Owns the cohesive cluster of save / restore / focus / share / export / import
 * callbacks (plus the hidden file-input ref the import flow drives). The
 * behavior is identical to the inlined version — dependency arrays are
 * preserved verbatim — so memoization / callback identity is unchanged.
 */
export function useRealtimeReviewActions({
  activeTab,
  anomalyFeed,
  appendTimelineEvent,
  currentTabQuotes,
  currentTabSymbols,
  filteredReviewSnapshots,
  freshnessSummary,
  getCategoryLabel,
  getDisplayName,
  messageApi,
  openDetailForSymbol,
  quotes,
  reviewAttribution,
  reviewOutcomeSummary,
  reviewScopeLabel,
  reviewSnapshots,
  setActiveTab,
  setIsSnapshotDrawerVisible,
  setReviewSnapshots,
  setTimelineEvents,
  spotlightSymbol,
  timelineEvents,
  transportModeLabel,
  validationRate,
}) {
  const snapshotImportInputRef = useRef(null);

  const saveReviewSnapshot = useCallback(() => {
    const snapshot = {
      id: `snapshot_${Date.now()}`,
      createdAt: new Date().toISOString(),
      version: REVIEW_SNAPSHOT_VERSION,
      activeTab,
      activeTabLabel: getCategoryLabel(activeTab),
      transportModeLabel,
      spotlightSymbol,
      spotlightName: spotlightSymbol ? getDisplayName(spotlightSymbol) : null,
      watchedSymbols: currentTabSymbols.slice(0, 8),
      quoteSnapshots: currentTabSymbols.slice(0, 8).map((symbol) => {
        const quote = quotes[symbol];
        return {
          symbol,
          price: hasNumericValue(quote?.price) ? Number(quote.price).toFixed(2) : '--',
          changePercent: hasNumericValue(quote?.change_percent) ? `${Number(quote.change_percent).toFixed(2)}%` : '--',
          volume: hasNumericValue(quote?.volume) ? Number(quote.volume).toLocaleString() : '--',
        };
      }),
      loadedCount: currentTabQuotes.length,
      totalCount: currentTabSymbols.length,
      anomalyCount: anomalyFeed.length,
      anomalies: anomalyFeed.slice(0, 3).map((item) => ({
        symbol: item.symbol,
        title: item.title,
        description: item.description,
      })),
      freshnessSummary,
      note: '',
      outcome: null,
    };

    setReviewSnapshots((prev) => [snapshot, ...prev].slice(0, MAX_REVIEW_SNAPSHOTS));
    if (spotlightSymbol) {
      appendTimelineEvent({
        symbol: spotlightSymbol,
        kind: 'review_snapshot',
        source: 'review',
        sourceLabel: '复盘快照',
        title: `保存复盘快照 · ${getCategoryLabel(activeTab)}`,
        description: `记录了 ${anomalyFeed.length} 条异动与 ${currentTabQuotes.length}/${currentTabSymbols.length} 条已加载行情。`,
        createdAt: snapshot.createdAt,
        priceSnapshot: quotes[spotlightSymbol]?.price ?? null,
      });
    }
    messageApi.success('已保存当前复盘快照');
  // quotes is intentionally omitted here to keep the snapshot callback stable for UI interactions.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    activeTab,
    anomalyFeed,
    appendTimelineEvent,
    currentTabQuotes.length,
    currentTabSymbols,
    freshnessSummary,
    getDisplayName,
    messageApi,
    quotes,
    spotlightSymbol,
    transportModeLabel,
  ]);

  const restoreSnapshot = useCallback((snapshot) => {
    if (!snapshot?.activeTab) {
      return;
    }

    setActiveTab(snapshot.activeTab);
    setIsSnapshotDrawerVisible(false);
    messageApi.success(`已切换到 ${snapshot.activeTabLabel || getCategoryLabel(snapshot.activeTab)} 复盘视角`);
  }, [getCategoryLabel, messageApi, setActiveTab, setIsSnapshotDrawerVisible]);

  const openSnapshotFocus = useCallback((snapshot) => {
    if (!snapshot?.spotlightSymbol) {
      return;
    }

    setActiveTab(snapshot.activeTab || inferSymbolCategory(snapshot.spotlightSymbol));
    openDetailForSymbol(snapshot.spotlightSymbol, {
      note: 'snapshot focus',
      snapshotReason: 'detail_snapshot',
      fallbackReason: 'detail_rest',
      fallbackNote: 'snapshot focus fallback',
      closeSnapshotDrawer: true,
    });
  }, [openDetailForSymbol, setActiveTab]);

  const copyTextToClipboard = useCallback(async (content, successText) => {
    if (!navigator?.clipboard?.writeText) {
      messageApi.warning('当前环境不支持剪贴板复制');
      return;
    }

    try {
      await navigator.clipboard.writeText(content);
      messageApi.success(successText);
    } catch (error) {
      messageApi.error('复制失败，请稍后重试');
    }
  }, [messageApi]);

  const openShareWindow = useCallback((title, bodyHtml) => {
    if (typeof window === 'undefined' || typeof window.open !== 'function') {
      messageApi.warning('当前环境不支持分享卡片预览');
      return;
    }

    const shareWindow = window.open('', '_blank', 'noopener,noreferrer,width=960,height=760');

    if (!shareWindow?.document) {
      messageApi.warning('分享窗口被浏览器拦截了，请允许弹窗后重试');
      return;
    }

    shareWindow.document.write(buildRealtimeShareDocument(title, bodyHtml));
    shareWindow.document.close();
  }, [messageApi]);

  const openSnapshotShareCard = useCallback((snapshot) => {
    openShareWindow(
      `Realtime Review Snapshot - ${snapshot?.spotlightName || snapshot?.spotlightSymbol || '未记录焦点标的'}`,
      formatReviewSnapshotShareHtml(snapshot, getSnapshotOutcomeMeta)
    );
  }, [openShareWindow]);

  const openReviewSummaryShareCard = useCallback(() => {
    openShareWindow(
      `Realtime Review Summary - ${reviewScopeLabel}`,
      formatReviewSummaryShareHtml({
        scopeLabel: reviewScopeLabel,
        filteredReviewSnapshots,
        reviewOutcomeSummary,
        validationRate,
        reviewAttribution,
      })
    );
  }, [
    filteredReviewSnapshots,
    openShareWindow,
    reviewAttribution,
    reviewOutcomeSummary,
    reviewScopeLabel,
    validationRate,
  ]);

  const exportReviewSnapshots = useCallback(() => {
    const payload = JSON.stringify({
      version: REALTIME_EXPORT_VERSION,
      exported_at: new Date().toISOString(),
      review_snapshots: reviewSnapshots,
      timeline_events: timelineEvents,
    }, null, 2);
    copyTextToClipboard(payload, '复盘快照 JSON 已复制');
  }, [copyTextToClipboard, reviewSnapshots, timelineEvents]);

  const triggerSnapshotImport = useCallback(() => {
    snapshotImportInputRef.current?.click();
  }, []);

  const handleImportReviewSnapshots = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result || '[]'));
        const snapshotPayload = Array.isArray(parsed)
          ? parsed
          : parsed?.review_snapshots;
        const timelinePayload = Array.isArray(parsed)
          ? []
          : parsed?.timeline_events;

        if (!Array.isArray(snapshotPayload)) {
          throw new Error('invalid payload');
        }

        const normalized = snapshotPayload
          .map(normalizeReviewSnapshot)
          .filter(Boolean)
          .sort((left, right) => new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime())
          .slice(0, MAX_REVIEW_SNAPSHOTS);
        const normalizedTimeline = Array.isArray(timelinePayload)
          ? timelinePayload
              .map(normalizeTimelineEvent)
              .filter(Boolean)
              .slice(0, MAX_TIMELINE_EVENTS)
          : [];

        setReviewSnapshots(normalized);
        setTimelineEvents(normalizedTimeline);
        messageApi.success(`已导入 ${normalized.length} 条复盘快照`);
      } catch (error) {
        messageApi.error('复盘快照导入失败，请检查 JSON 格式');
      } finally {
        event.target.value = '';
      }
    };
    reader.readAsText(file);
  }, [messageApi, setReviewSnapshots, setTimelineEvents]);

  return {
    snapshotImportInputRef,
    saveReviewSnapshot,
    restoreSnapshot,
    openSnapshotFocus,
    copyTextToClipboard,
    openShareWindow,
    openSnapshotShareCard,
    openReviewSummaryShareCard,
    exportReviewSnapshots,
    triggerSnapshotImport,
    handleImportReviewSnapshots,
  };
}

export default useRealtimeReviewActions;
