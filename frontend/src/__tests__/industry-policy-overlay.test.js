import {
    buildPolicyOverlay,
    lookupPolicyOverlay,
    POLICY_OVERLAY_THRESHOLD,
} from '../utils/industryPolicyOverlay';

describe('buildPolicyOverlay / lookupPolicyOverlay', () => {
    const HEATMAP = [
        { name: '新能源' },
        { name: '半导体' },
        { name: '医药生物' },
    ];

    it('exact-match join surfaces the signal payload', () => {
        const overlay = buildPolicyOverlay(HEATMAP, {
            新能源: { avg_impact: 0.34, mentions: 5, signal: 'bullish' },
        });
        const result = lookupPolicyOverlay('新能源', overlay);
        expect(result).toMatchObject({ signal: 'bullish', avgImpact: 0.34, mentions: 5 });
    });

    it('matches across alias variants via normalization', () => {
        const overlay = buildPolicyOverlay(HEATMAP, {
            '新能源板块': { avg_impact: 0.4, mentions: 2, signal: 'bullish' },
        });
        // Heatmap uses canonical "新能源"; policy uses "新能源板块" — normalize bridges them
        const result = lookupPolicyOverlay('新能源', overlay);
        expect(result).not.toBeNull();
        expect(result.signal).toBe('bullish');
    });

    it('avg_impact within ±threshold reclassifies to neutral when signal field is missing', () => {
        const overlay = buildPolicyOverlay(HEATMAP, {
            半导体: { avg_impact: POLICY_OVERLAY_THRESHOLD - 0.05, mentions: 1 }, // no signal field
        });
        expect(lookupPolicyOverlay('半导体', overlay).signal).toBe('neutral');
    });

    it('avg_impact above +threshold is classified as bullish', () => {
        const overlay = buildPolicyOverlay(HEATMAP, {
            半导体: { avg_impact: POLICY_OVERLAY_THRESHOLD + 0.1, mentions: 3 },
        });
        expect(lookupPolicyOverlay('半导体', overlay).signal).toBe('bullish');
    });

    it('avg_impact below -threshold is classified as bearish', () => {
        const overlay = buildPolicyOverlay(HEATMAP, {
            医药生物: { avg_impact: -(POLICY_OVERLAY_THRESHOLD + 0.05), mentions: 2 },
        });
        expect(lookupPolicyOverlay('医药生物', overlay).signal).toBe('bearish');
    });

    it('explicit upstream signal trumps the local threshold check', () => {
        // Backend says "neutral" even though avg_impact crossed our threshold
        // → trust the backend so cross-source classifications stay aligned.
        const overlay = buildPolicyOverlay(HEATMAP, {
            新能源: { avg_impact: 0.5, mentions: 4, signal: 'neutral' },
        });
        expect(lookupPolicyOverlay('新能源', overlay).signal).toBe('neutral');
    });

    it('industry without policy data returns null on lookup', () => {
        const overlay = buildPolicyOverlay(HEATMAP, {
            新能源: { avg_impact: 0.4, mentions: 1, signal: 'bullish' },
        });
        expect(lookupPolicyOverlay('医药生物', overlay)).toBeNull();
    });

    it('handles empty / non-object inputs gracefully', () => {
        expect(buildPolicyOverlay(HEATMAP, null)).toEqual({});
        expect(buildPolicyOverlay(HEATMAP, undefined)).toEqual({});
        // Normalization preserves Chinese characters, only stripping noise
        expect(buildPolicyOverlay(null, { 新能源: { signal: 'bullish' } })).toEqual({
            '新能源': expect.objectContaining({ signal: 'bullish' }),
        });
        expect(lookupPolicyOverlay('新能源', null)).toBeNull();
        expect(lookupPolicyOverlay('', { foo: { signal: 'bullish' } })).toBeNull();
    });

    it('non-finite avg_impact resolves to neutral (no crash)', () => {
        const overlay = buildPolicyOverlay(HEATMAP, {
            新能源: { avg_impact: 'oops', mentions: 'NaN' },
        });
        const result = lookupPolicyOverlay('新能源', overlay);
        expect(result).not.toBeNull();
        expect(result.signal).toBe('neutral');
        expect(result.mentions).toBe(0);
    });
});
