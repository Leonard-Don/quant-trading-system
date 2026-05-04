import {
    PAPER_TRADING_PREFILL_KEY,
    PAPER_TRADING_PREFILL_TTL_MS,
    setPaperPrefill,
    consumePaperPrefill,
    peekPaperPrefill,
    buildPrefillFromBacktest,
} from '../utils/paperTradingPrefill';

describe('paperTradingPrefill', () => {
    beforeEach(() => {
        try {
            window.sessionStorage.clear();
        } catch (_err) { /* ignore */ }
    });

    it('round-trips a payload', () => {
        const payload = { symbol: 'AAPL', side: 'BUY', quantity: 5, sourceLabel: 'src' };
        expect(setPaperPrefill(payload)).toBe(true);
        const consumed = consumePaperPrefill();
        expect(consumed).toMatchObject(payload);
        expect(consumed.writtenAt).toEqual(expect.any(Number));
    });

    it('consume clears the entry so a second read returns null', () => {
        setPaperPrefill({ symbol: 'AAPL' });
        consumePaperPrefill();
        expect(consumePaperPrefill()).toBeNull();
    });

    it('returns null when the prefill is older than the TTL', () => {
        const stale = { symbol: 'AAPL', writtenAt: Date.now() - PAPER_TRADING_PREFILL_TTL_MS - 1000 };
        window.sessionStorage.setItem(PAPER_TRADING_PREFILL_KEY, JSON.stringify(stale));
        expect(consumePaperPrefill()).toBeNull();
        // Even an expired entry is removed so we don't leave dust around
        expect(window.sessionStorage.getItem(PAPER_TRADING_PREFILL_KEY)).toBeNull();
    });

    it('returns null and clears the slot when sessionStorage holds malformed JSON', () => {
        window.sessionStorage.setItem(PAPER_TRADING_PREFILL_KEY, '{not-json');
        expect(consumePaperPrefill()).toBeNull();
        expect(window.sessionStorage.getItem(PAPER_TRADING_PREFILL_KEY)).toBeNull();
    });

    it('peek does not clear the slot', () => {
        setPaperPrefill({ symbol: 'AAPL' });
        expect(peekPaperPrefill()).toMatchObject({ symbol: 'AAPL' });
        // Still consumable
        expect(consumePaperPrefill()).toMatchObject({ symbol: 'AAPL' });
    });
});

describe('buildPrefillFromBacktest', () => {
    it('extracts symbol + last trade direction + quantity', () => {
        const results = {
            symbol: 'aapl',
            strategy: 'MovingAverageCrossover',
            trades: [
                { type: 'BUY', quantity: 10, price: 100, date: '2024-01-01' },
                { type: 'SELL', quantity: 5, price: 110, date: '2024-02-01' },
            ],
        };
        expect(buildPrefillFromBacktest(results)).toEqual({
            symbol: 'AAPL',
            side: 'SELL',
            quantity: 5,
            sourceLabel: '由 MovingAverageCrossover · 回测带入',
        });
    });

    it('falls back to symbol-only when there are no trades', () => {
        expect(
            buildPrefillFromBacktest({ symbol: 'msft', strategy: 'BuyAndHold', trades: [] }),
        ).toEqual({
            symbol: 'MSFT',
            side: null,
            quantity: null,
            sourceLabel: '由 BuyAndHold · 回测带入',
        });
    });

    it('returns null when the backtest result has no symbol', () => {
        expect(buildPrefillFromBacktest({ trades: [{ type: 'BUY', quantity: 1 }] })).toBeNull();
        expect(buildPrefillFromBacktest({})).toBeNull();
        expect(buildPrefillFromBacktest(null)).toBeNull();
    });

    it('skips a non-finite or non-positive quantity', () => {
        const result = buildPrefillFromBacktest({
            symbol: 'AAPL',
            strategy: 'BB',
            trades: [{ type: 'BUY', quantity: 0 }],
        });
        expect(result.quantity).toBeNull();
        expect(result.side).toBe('BUY');
    });

    it('uses generic source label when strategy name is missing', () => {
        const result = buildPrefillFromBacktest({
            symbol: 'AAPL',
            trades: [{ type: 'BUY', quantity: 1 }],
        });
        expect(result.sourceLabel).toBe('由回测带入');
    });
});
