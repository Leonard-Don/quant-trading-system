import {
    buildRealtimeDetailTimeline,
    filterReviewSnapshots,
    formatCompactCurrency,
    getSnapshotOutcomeMeta,
    getTimelineTone,
    normalizeGroupWeights,
} from '../utils/realtimePanelHelpers';
import {
    CATEGORY_OPTIONS,
    CATEGORY_THEMES,
    DEFAULT_SUBSCRIBED_SYMBOLS,
    SNAPSHOT_OUTCOME_OPTIONS,
} from '../utils/realtimePanelConstants';

describe('realtimePanelConstants', () => {
    it('default subscribed symbol list is non-empty and unique', () => {
        expect(DEFAULT_SUBSCRIBED_SYMBOLS.length).toBeGreaterThan(10);
        const unique = new Set(DEFAULT_SUBSCRIBED_SYMBOLS);
        expect(unique.size).toBe(DEFAULT_SUBSCRIBED_SYMBOLS.length);
    });

    it('every CATEGORY_OPTIONS entry has a CATEGORY_THEMES counterpart', () => {
        CATEGORY_OPTIONS.forEach((option) => {
            expect(CATEGORY_THEMES[option.key]).toBeDefined();
            expect(CATEGORY_THEMES[option.key].label).toBe(option.label);
        });
    });

    it('snapshot outcomes cover the documented states', () => {
        expect(Object.keys(SNAPSHOT_OUTCOME_OPTIONS)).toEqual(
            expect.arrayContaining(['watching', 'validated', 'invalidated']),
        );
    });
});

describe('formatCompactCurrency', () => {
    it('uses standard notation under 10k', () => {
        expect(formatCompactCurrency(1234)).toBe('$1,234');
    });

    it('switches to compact notation past 10k', () => {
        // En-US locale renders "12.3K"; we just assert the suffix shape.
        expect(formatCompactCurrency(12345)).toMatch(/^\$\d+(\.\d)?[KMB]/);
    });

    it('handles non-finite gracefully', () => {
        expect(formatCompactCurrency('not a number')).toBe('$0');
        expect(formatCompactCurrency(null)).toBe('$0');
    });
});

describe('normalizeGroupWeights', () => {
    it('returns explicit weights filtered to known symbols', () => {
        const result = normalizeGroupWeights({
            symbols: ['AAPL', 'MSFT'],
            weights: { AAPL: 0.6, MSFT: 0.4, GOOG: 0.5 },
        });
        expect(result).toEqual({ AAPL: 0.6, MSFT: 0.4 });
    });

    it('falls back to equal weighting when no usable explicit weights given', () => {
        const result = normalizeGroupWeights({ symbols: ['AAPL', 'MSFT', 'GOOG'] });
        expect(result.AAPL).toBeCloseTo(1 / 3);
        expect(result.MSFT).toBeCloseTo(1 / 3);
        expect(result.GOOG).toBeCloseTo(1 / 3);
    });

    it('returns empty when no symbols', () => {
        expect(normalizeGroupWeights({})).toEqual({});
        expect(normalizeGroupWeights({ symbols: [] })).toEqual({});
    });
});

describe('getTimelineTone', () => {
    it('classifies positive kinds', () => {
        expect(getTimelineTone('price_up')).toBe('positive');
        expect(getTimelineTone('review_validated')).toBe('positive');
    });

    it('classifies negative kinds', () => {
        expect(getTimelineTone('price_down')).toBe('negative');
        expect(getTimelineTone('review_invalidated')).toBe('negative');
    });

    it('classifies warning kinds', () => {
        expect(getTimelineTone('volume_spike')).toBe('warning');
        expect(getTimelineTone('alert_plan')).toBe('warning');
    });

    it('falls back to neutral on unknown kind', () => {
        expect(getTimelineTone('foo')).toBe('neutral');
        expect(getTimelineTone()).toBe('neutral');
    });
});

describe('getSnapshotOutcomeMeta', () => {
    it('resolves known outcome labels', () => {
        expect(getSnapshotOutcomeMeta('watching')).toEqual({ label: '继续观察', color: 'default' });
        expect(getSnapshotOutcomeMeta('validated').label).toBe('验证有效');
    });

    it('returns null for unknown outcomes', () => {
        expect(getSnapshotOutcomeMeta('unknown')).toBeNull();
        expect(getSnapshotOutcomeMeta(undefined)).toBeNull();
    });
});

describe('filterReviewSnapshots', () => {
    const snapshots = [
        { id: 's1', createdAt: '2026-05-04T08:00:00Z', activeTab: 'us' },
        { id: 's2', createdAt: '2026-04-20T08:00:00Z', activeTab: 'cn' },
        { id: 's3', createdAt: '2026-05-03T08:00:00Z', activeTab: 'us' },
    ];

    it('"all" returns the full list', () => {
        expect(filterReviewSnapshots(snapshots, 'all')).toBe(snapshots);
    });

    it('"recent20" caps to first 20', () => {
        const long = Array.from({ length: 30 }, (_, i) => ({ id: `s${i}` }));
        expect(filterReviewSnapshots(long, 'recent20')).toHaveLength(20);
    });

    it('"recent7d" filters by createdAt against now', () => {
        const realDateNow = Date.now;
        Date.now = () => new Date('2026-05-05T00:00:00Z').getTime();
        try {
            const result = filterReviewSnapshots(snapshots, 'recent7d');
            // s2 is 15 days old, dropped
            expect(result.map((s) => s.id)).toEqual(['s1', 's3']);
        } finally {
            Date.now = realDateNow;
        }
    });

    it('"activeTab" filters to matching tab', () => {
        const result = filterReviewSnapshots(snapshots, 'activeTab', 'us');
        expect(result.map((s) => s.id)).toEqual(['s1', 's3']);
    });
});

describe('buildRealtimeDetailTimeline', () => {
    it('returns empty when symbol is missing', () => {
        expect(buildRealtimeDetailTimeline({})).toEqual([]);
    });

    it('aggregates events from all four sources, dedupes, and sorts desc', () => {
        const events = buildRealtimeDetailTimeline({
            symbol: 'AAPL',
            anomalyFeed: [
                {
                    symbol: 'AAPL',
                    kind: 'price_up',
                    title: '突破阻力位',
                    description: '价格上突',
                    timestamp: '2026-05-04T10:00:00Z',
                },
            ],
            reviewSnapshots: [
                {
                    id: 'r1',
                    spotlightSymbol: 'AAPL',
                    outcome: 'validated',
                    createdAt: '2026-05-03T08:00:00Z',
                    updatedAt: '2026-05-03T09:00:00Z',
                    anomalyCount: 2,
                    activeTabLabel: '美股',
                },
            ],
            actionEvents: [
                {
                    id: 'manual_AAPL_plan',
                    symbol: 'AAPL',
                    kind: 'trade_plan',
                    createdAt: '2026-05-04T08:00:00Z',
                    title: '加仓计划',
                },
            ],
            alertHistory: [
                {
                    id: 42,
                    symbol: 'AAPL',
                    condition: 'price_above',
                    conditionLabel: '价格上穿',
                    threshold: 200,
                    triggerTime: '2026-05-04T09:00:00Z',
                    triggerPrice: 201,
                },
            ],
        });

        // 4 distinct events expected
        expect(events).toHaveLength(4);
        // Sorted desc by createdAt
        const times = events.map((event) => new Date(event.createdAt).getTime());
        expect([...times].sort((a, b) => b - a)).toEqual(times);
    });

    it('non-matching symbol items are excluded', () => {
        const events = buildRealtimeDetailTimeline({
            symbol: 'AAPL',
            anomalyFeed: [{ symbol: 'MSFT', kind: 'price_up', timestamp: '2026-05-04' }],
        });
        expect(events).toEqual([]);
    });
});
