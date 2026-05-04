import {
    DEFAULT_VOLUME_TREND,
    DISPLAY_EMPTY,
    formatDisplayNumber,
    formatDisplayPercent,
    formatMetaTime,
    normalizeVolumeTrend,
} from '../utils/marketAnalysisFormatters';

describe('normalizeVolumeTrend', () => {
    it('returns the default shape for null/undefined input', () => {
        expect(normalizeVolumeTrend(null)).toEqual(DEFAULT_VOLUME_TREND);
        expect(normalizeVolumeTrend(undefined)).toEqual(DEFAULT_VOLUME_TREND);
        expect(normalizeVolumeTrend(0)).toEqual(DEFAULT_VOLUME_TREND);
    });

    it('promotes a bare string into the trend slot', () => {
        const result = normalizeVolumeTrend('rising');
        expect(result).toEqual({ ...DEFAULT_VOLUME_TREND, trend: 'rising' });
    });

    it('overlays a partial object on top of the defaults', () => {
        const result = normalizeVolumeTrend({ trend: 'rising', volume_ratio: 2.4 });
        expect(result).toEqual({
            ...DEFAULT_VOLUME_TREND,
            trend: 'rising',
            volume_ratio: 2.4,
        });
    });

    it('does not mutate the default object', () => {
        normalizeVolumeTrend({ trend: 'falling' });
        expect(DEFAULT_VOLUME_TREND.trend).toBe('unknown');
    });
});

describe('formatDisplayNumber', () => {
    it('formats a finite number to fixed digits', () => {
        expect(formatDisplayNumber(3.14159, 2)).toBe('3.14');
        expect(formatDisplayNumber('2.5', 1, '%')).toBe('2.5%');
    });

    it('returns the placeholder for null/undefined/NaN', () => {
        expect(formatDisplayNumber(null)).toBe(DISPLAY_EMPTY);
        expect(formatDisplayNumber(undefined)).toBe(DISPLAY_EMPTY);
        expect(formatDisplayNumber('not a number')).toBe(DISPLAY_EMPTY);
    });
});

describe('formatDisplayPercent', () => {
    it('treats raw values as already-percent by default', () => {
        expect(formatDisplayPercent(12.5)).toBe('12.50%');
    });

    it('multiplies by 100 when valueIsRatio=true', () => {
        expect(formatDisplayPercent(0.125, 2, true)).toBe('12.50%');
    });

    it('returns placeholder on invalid input', () => {
        expect(formatDisplayPercent(null)).toBe(DISPLAY_EMPTY);
        expect(formatDisplayPercent(NaN)).toBe(DISPLAY_EMPTY);
    });
});

describe('formatMetaTime', () => {
    it('returns placeholder on falsy input', () => {
        expect(formatMetaTime(null)).toBe(DISPLAY_EMPTY);
        expect(formatMetaTime(undefined)).toBe(DISPLAY_EMPTY);
        expect(formatMetaTime(0)).toBe(DISPLAY_EMPTY);
    });

    it('formats a timestamp into HH:MM:SS', () => {
        const ts = new Date('2026-05-04T08:15:30+00:00').getTime();
        const formatted = formatMetaTime(ts);
        // The exact rendering depends on the test env timezone, so we
        // assert structural shape rather than a specific value.
        expect(formatted).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    });
});
