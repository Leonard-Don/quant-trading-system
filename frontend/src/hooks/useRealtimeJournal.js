import { useCallback, useEffect, useRef, useState } from 'react';

import api from '../services/api';
import {
  ALERT_HIT_HISTORY_STORAGE_KEY,
  loadAlertHitHistory,
  MAX_ALERT_HIT_HISTORY,
} from '../utils/realtimeSignals';

const REVIEW_SNAPSHOT_STORAGE_KEY = 'realtime-review-snapshots';
const REALTIME_TIMELINE_STORAGE_KEY = 'realtime-timeline-events';
const MAX_REVIEW_SNAPSHOTS = 48;
const MAX_TIMELINE_EVENTS = 120;
const REALTIME_JOURNAL_DEBOUNCE_MS = 500;

const normalizeReviewSnapshot = (snapshot) => {
  if (!snapshot || typeof snapshot !== 'object' || !snapshot.id) {
    return null;
  }
  return { version: snapshot.version || 1, ...snapshot };
};

const normalizeTimelineEvent = (event) => {
  if (!event || typeof event !== 'object' || !event.id || !event.symbol) {
    return null;
  }
  return { version: event.version || 1, ...event };
};

const loadReviewSnapshots = () => {
  if (typeof window === 'undefined') return [];
  try {
    const rawValue = window.localStorage.getItem(REVIEW_SNAPSHOT_STORAGE_KEY);
    if (!rawValue) return [];
    const parsed = JSON.parse(rawValue);
    return Array.isArray(parsed) ? parsed.map(normalizeReviewSnapshot).filter(Boolean) : [];
  } catch {
    return [];
  }
};

const loadRealtimeTimelineEvents = () => {
  if (typeof window === 'undefined') return [];
  try {
    const rawValue = window.localStorage.getItem(REALTIME_TIMELINE_STORAGE_KEY);
    if (!rawValue) return [];
    const parsedValue = JSON.parse(rawValue);
    return Array.isArray(parsedValue) ? parsedValue.map(normalizeTimelineEvent).filter(Boolean) : [];
  } catch {
    return [];
  }
};

export { normalizeReviewSnapshot, normalizeTimelineEvent, MAX_REVIEW_SNAPSHOTS, MAX_TIMELINE_EVENTS };

export const useRealtimeJournal = ({ realtimeProfileId }) => {
  const [reviewSnapshots, setReviewSnapshots] = useState(loadReviewSnapshots);
  const [timelineEvents, setTimelineEvents] = useState(loadRealtimeTimelineEvents);
  const [alertHitHistory, setAlertHitHistory] = useState(loadAlertHitHistory);
  const [isJournalHydrated, setIsJournalHydrated] = useState(false);

  const journalSaveTimerRef = useRef(null);
  const latestJournalRef = useRef('');
  const lastSyncedJournalRef = useRef('');

  // --- localStorage persistence ---
  useEffect(() => {
    window.localStorage.setItem(REVIEW_SNAPSHOT_STORAGE_KEY, JSON.stringify(reviewSnapshots));
  }, [reviewSnapshots]);

  useEffect(() => {
    window.localStorage.setItem(REALTIME_TIMELINE_STORAGE_KEY, JSON.stringify(timelineEvents));
  }, [timelineEvents]);

  useEffect(() => {
    window.localStorage.setItem(ALERT_HIT_HISTORY_STORAGE_KEY, JSON.stringify(alertHitHistory));
  }, [alertHitHistory]);

  useEffect(() => {
    latestJournalRef.current = JSON.stringify({
      review_snapshots: reviewSnapshots,
      timeline_events: timelineEvents,
    });
  }, [reviewSnapshots, timelineEvents]);

  // --- Backend hydration: journal ---
  useEffect(() => {
    let isCancelled = false;
    const initialJournalSnapshot = latestJournalRef.current || JSON.stringify({
      review_snapshots: reviewSnapshots,
      timeline_events: timelineEvents,
    });
    let initialLocalJournal = { review_snapshots: reviewSnapshots, timeline_events: timelineEvents };
    try {
      initialLocalJournal = JSON.parse(initialJournalSnapshot);
    } catch {}

    const hydrateJournal = async () => {
      try {
        const response = await api.get('/realtime/journal', {
          headers: { 'X-Realtime-Profile': realtimeProfileId },
        });
        if (!response.data?.success || isCancelled) return;

        const currentJournalSnapshot = latestJournalRef.current || initialJournalSnapshot;
        const userChangedDuringHydration = currentJournalSnapshot !== initialJournalSnapshot;
        const nextReviewSnapshots = Array.isArray(response.data.data?.review_snapshots)
          ? response.data.data.review_snapshots.map(normalizeReviewSnapshot).filter(Boolean).slice(0, MAX_REVIEW_SNAPSHOTS)
          : [];
        const nextTimelineEvents = Array.isArray(response.data.data?.timeline_events)
          ? response.data.data.timeline_events.map(normalizeTimelineEvent).filter(Boolean).slice(0, MAX_TIMELINE_EVENTS)
          : [];
        const backendEmpty = nextReviewSnapshots.length === 0 && nextTimelineEvents.length === 0;
        const localHasEntries =
          (Array.isArray(initialLocalJournal.review_snapshots) && initialLocalJournal.review_snapshots.length > 0) ||
          (Array.isArray(initialLocalJournal.timeline_events) && initialLocalJournal.timeline_events.length > 0);

        if (!userChangedDuringHydration) {
          if (backendEmpty && localHasEntries) {
            lastSyncedJournalRef.current = '';
          } else {
            setReviewSnapshots(nextReviewSnapshots);
            setTimelineEvents(nextTimelineEvents);
            lastSyncedJournalRef.current = JSON.stringify({
              review_snapshots: nextReviewSnapshots,
              timeline_events: nextTimelineEvents,
            });
          }
        }
      } catch {
        // fall back to local cache
      } finally {
        if (!isCancelled) setIsJournalHydrated(true);
      }
    };

    hydrateJournal();
    return () => { isCancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realtimeProfileId]);

  // --- Backend sync: journal (debounced) ---
  useEffect(() => {
    if (!isJournalHydrated) return undefined;

    const payload = { review_snapshots: reviewSnapshots, timeline_events: timelineEvents };
    const serializedPayload = JSON.stringify(payload);
    if (serializedPayload === lastSyncedJournalRef.current) return undefined;

    if (journalSaveTimerRef.current) clearTimeout(journalSaveTimerRef.current);

    journalSaveTimerRef.current = setTimeout(async () => {
      try {
        await api.put('/realtime/journal', payload, {
          headers: { 'X-Realtime-Profile': realtimeProfileId },
        });
        lastSyncedJournalRef.current = serializedPayload;
      } catch {}
    }, REALTIME_JOURNAL_DEBOUNCE_MS);

    return () => {
      if (journalSaveTimerRef.current) {
        clearTimeout(journalSaveTimerRef.current);
        journalSaveTimerRef.current = null;
      }
    };
  }, [isJournalHydrated, realtimeProfileId, reviewSnapshots, timelineEvents]);

  // --- Backend hydration: alert hit history ---
  useEffect(() => {
    let isCancelled = false;
    const initialSnapshot = JSON.stringify(alertHitHistory);

    const hydrateAlertHitHistory = async () => {
      try {
        const response = await api.get('/realtime/alerts', {
          headers: { 'X-Realtime-Profile': realtimeProfileId },
        });
        if (!response.data?.success || isCancelled) return;

        const nextHistory = Array.isArray(response.data.data?.alert_hit_history)
          ? response.data.data.alert_hit_history.slice(0, MAX_ALERT_HIT_HISTORY)
          : [];
        const userChanged = JSON.stringify(alertHitHistory) !== initialSnapshot;
        const backendEmpty = nextHistory.length === 0;
        const localExists = alertHitHistory.length > 0;

        if (!userChanged) {
          if (backendEmpty && localExists) return;
          setAlertHitHistory(nextHistory);
        }
      } catch {}
    };

    hydrateAlertHitHistory();
    return () => { isCancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realtimeProfileId]);

  // --- Callbacks ---
  const appendTimelineEvent = useCallback((event) => {
    if (!event?.symbol) return;
    const nextEvent = {
      id: `timeline_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      createdAt: new Date().toISOString(),
      version: 1,
      ...event,
    };
    setTimelineEvents((prev) => [nextEvent, ...prev].slice(0, MAX_TIMELINE_EVENTS));
  }, []);

  const handleAlertTriggered = useCallback((historyEntry) => {
    if (!historyEntry?.symbol) return;
    setAlertHitHistory((prev) => [historyEntry, ...prev].slice(0, MAX_ALERT_HIT_HISTORY));
  }, []);

  const updateReviewSnapshot = useCallback((snapshotId, updates) => {
    setReviewSnapshots((prev) => prev.map((snapshot) => (
      snapshot.id === snapshotId
        ? { ...snapshot, ...updates, updatedAt: new Date().toISOString() }
        : snapshot
    )));
  }, []);

  return {
    alertHitHistory,
    setAlertHitHistory,
    appendTimelineEvent,
    handleAlertTriggered,
    isJournalHydrated,
    reviewSnapshots,
    setReviewSnapshots,
    timelineEvents,
    setTimelineEvents,
    updateReviewSnapshot,
  };
};
