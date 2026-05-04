/**
 * Pure (or near-pure: localStorage / window for diagnostics) helpers
 * lifted out of RealTimePanel.js. Keeping these out of the host
 * component lets future sessions restructure the panel's hook tree
 * without dragging this logic along.
 */

import {
    REALTIME_DIAGNOSTICS_STORAGE_KEY,
    SNAPSHOT_OUTCOME_OPTIONS,
} from './realtimePanelConstants';

export const formatCompactCurrency = (value) => {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) {
        return '$0';
    }
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        notation: Math.abs(numeric) >= 10000 ? 'compact' : 'standard',
        maximumFractionDigits: Math.abs(numeric) >= 10000 ? 1 : 0,
    }).format(numeric);
};

/**
 * Resolve weights for a quote group. Honor explicit per-symbol weights
 * when they refer to symbols actually in the group; fall back to equal
 * weighting otherwise.
 */
export const normalizeGroupWeights = (group) => {
    const symbols = Array.isArray(group?.symbols) ? group.symbols.filter(Boolean) : [];
    if (!symbols.length) {
        return {};
    }

    const explicitWeights =
        group?.weights && typeof group.weights === 'object' && !Array.isArray(group.weights)
            ? Object.entries(group.weights).reduce((result, [symbol, rawWeight]) => {
                const numericWeight = Number(rawWeight);
                if (symbols.includes(symbol) && Number.isFinite(numericWeight)) {
                    result[symbol] = numericWeight;
                }
                return result;
            }, {})
            : {};

    if (Object.keys(explicitWeights).length) {
        return explicitWeights;
    }

    const equalWeight = 1 / symbols.length;
    return symbols.reduce((result, symbol) => {
        result[symbol] = equalWeight;
        return result;
    }, {});
};

/**
 * Diagnostics flag resolution: ?realtimeDiagnostics=1 (or =0) wins and
 * gets persisted to localStorage; absent that, falls back to the
 * persisted value; absent that, defaults to non-production.
 *
 * Touches window/localStorage — kept out of strict "pure helpers"
 * marketing but still safer in a util module than embedded in the
 * component.
 */
export const loadDiagnosticsEnabled = () => {
    if (typeof window === 'undefined') {
        return process.env.NODE_ENV !== 'production';
    }

    const query = new URLSearchParams(window.location.search);
    const queryValue = query.get('realtimeDiagnostics');
    if (queryValue === '1') {
        window.localStorage.setItem(REALTIME_DIAGNOSTICS_STORAGE_KEY, '1');
        return true;
    }
    if (queryValue === '0') {
        window.localStorage.setItem(REALTIME_DIAGNOSTICS_STORAGE_KEY, '0');
        return false;
    }

    const persisted = window.localStorage.getItem(REALTIME_DIAGNOSTICS_STORAGE_KEY);
    if (persisted === '1') return true;
    if (persisted === '0') return false;

    return process.env.NODE_ENV !== 'production';
};

const POSITIVE_TIMELINE_KINDS = new Set(['price_up', 'touch_high', 'trade_plan', 'review_validated']);
const NEGATIVE_TIMELINE_KINDS = new Set(['price_down', 'touch_low', 'review_invalidated']);
const WARNING_TIMELINE_KINDS = new Set(['volume_spike', 'range_expansion', 'alert_plan', 'review_snapshot']);

export const getTimelineTone = (kind = '') => {
    if (POSITIVE_TIMELINE_KINDS.has(kind)) return 'positive';
    if (NEGATIVE_TIMELINE_KINDS.has(kind)) return 'negative';
    if (WARNING_TIMELINE_KINDS.has(kind)) return 'warning';
    return 'neutral';
};

export const getSnapshotOutcomeMeta = (outcome) => SNAPSHOT_OUTCOME_OPTIONS[outcome] || null;

export const filterReviewSnapshots = (snapshots = [], scope = 'all', activeTab = '') => {
    if (scope === 'recent20') {
        return snapshots.slice(0, 20);
    }

    if (scope === 'recent7d') {
        const now = Date.now();
        return snapshots.filter((snapshot) => {
            const createdAt = new Date(snapshot.createdAt).getTime();
            return Number.isFinite(createdAt) && now - createdAt <= 7 * 24 * 60 * 60 * 1000;
        });
    }

    if (scope === 'activeTab') {
        return snapshots.filter((snapshot) => snapshot.activeTab === activeTab);
    }

    return snapshots;
};

const ALERT_POSITIVE_CONDITIONS = new Set(['price_above', 'change_pct_above', 'touch_high']);

export const buildRealtimeDetailTimeline = ({
    symbol,
    anomalyFeed = [],
    reviewSnapshots = [],
    actionEvents = [],
    alertHistory = [],
}) => {
    if (!symbol) {
        return [];
    }

    const liveSignalEvents = anomalyFeed
        .filter((item) => item?.symbol === symbol)
        .map((item) => ({
            id: `live_${symbol}_${item.kind}_${item.timestamp || item.title}`,
            symbol,
            kind: item.kind || 'live_signal',
            source: 'live',
            sourceLabel: '实时异动',
            title: item.title,
            description: item.description,
            createdAt: item.timestamp || new Date().toISOString(),
            tone: getTimelineTone(item.kind),
            priceSnapshot: item.priceSnapshot,
            changePercentSnapshot: item.changePercentSnapshot,
            rangePercentSnapshot: item.rangePercentSnapshot,
            volumeSnapshot: item.volumeSnapshot,
        }));

    const reviewEvents = reviewSnapshots
        .filter((snapshot) => snapshot?.spotlightSymbol === symbol
            || (snapshot?.anomalies || []).some((item) => item?.symbol === symbol))
        .map((snapshot) => {
            const outcomeMeta = getSnapshotOutcomeMeta(snapshot.outcome);
            const relatedAnomaly = (snapshot.anomalies || []).find((item) => item?.symbol === symbol);
            return {
                id: `review_${snapshot.id}_${symbol}`,
                symbol,
                kind: snapshot.outcome ? `review_${snapshot.outcome}` : 'review_snapshot',
                source: 'review',
                sourceLabel: '复盘快照',
                title: outcomeMeta?.label
                    ? `${outcomeMeta.label} · ${snapshot.activeTabLabel || snapshot.activeTab || '复盘记录'}`
                    : '保存复盘快照',
                description: snapshot.note
                    || relatedAnomaly?.description
                    || `记录了 ${snapshot.activeTabLabel || snapshot.activeTab || '--'} 视角下的 ${snapshot.anomalyCount ?? 0} 条异动。`,
                createdAt: snapshot.updatedAt || snapshot.createdAt,
                tone: getTimelineTone(snapshot.outcome ? `review_${snapshot.outcome}` : 'review_snapshot'),
            };
        });

    const manualEvents = actionEvents
        .filter((event) => event?.symbol === symbol)
        .map((event) => ({
            ...event,
            tone: event.tone || getTimelineTone(event.kind),
        }));

    const alertEvents = alertHistory
        .filter((entry) => entry?.symbol === symbol)
        .map((entry) => ({
            id: `alert_hit_${entry.id}`,
            symbol,
            kind: 'alert_triggered',
            source: 'alert',
            sourceLabel: '提醒命中',
            title: `提醒命中 · ${entry.conditionLabel || '提醒规则'}`,
            description: entry.message || `${symbol} 的提醒规则已触发。`,
            createdAt: entry.triggerTime,
            tone: ALERT_POSITIVE_CONDITIONS.has(entry.condition) ? 'positive' : 'warning',
            priceSnapshot: entry.priceSnapshot ?? entry.triggerPrice ?? null,
            threshold: entry.threshold,
            condition: entry.condition,
        }));

    const uniqueEvents = new Map();
    [...liveSignalEvents, ...manualEvents, ...reviewEvents, ...alertEvents].forEach((event) => {
        if (!event?.id) return;
        uniqueEvents.set(event.id, event);
    });

    return Array.from(uniqueEvents.values())
        .sort((left, right) =>
            new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime()
        )
        .slice(0, 10);
};
