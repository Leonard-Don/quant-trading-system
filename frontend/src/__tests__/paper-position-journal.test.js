import { buildPaperPositionEntry } from '../utils/paperPositionJournal';

describe('buildPaperPositionEntry', () => {
    const FULL_POSITION = {
        symbol: 'aapl',
        quantity: 10,
        avg_cost: 150,
        last_price: 165,
        market_value: 1650,
        unrealized_pnl: 150,
        opened_at: '2026-05-01T08:00:00+00:00',
        updated_at: '2026-05-04T12:00:00+00:00',
    };

    it('renders a trade_plan entry with full mark-to-market detail', () => {
        const entry = buildPaperPositionEntry(FULL_POSITION);
        expect(entry).not.toBeNull();
        expect(entry.id).toBe('paper-position:AAPL');
        expect(entry.type).toBe('trade_plan');
        expect(entry.symbol).toBe('AAPL');
        expect(entry.title).toBe('AAPL 纸面持仓 10 股');
        expect(entry.summary).toContain('均价 $150.00');
        expect(entry.summary).toContain('现价 $165.00');
        expect(entry.summary).toContain('浮动 +150.00');
        // 10% PnL pct
        expect(entry.summary).toContain('10.00%');
        expect(entry.metrics).toMatchObject({
            quantity: 10,
            avg_cost: 150,
            last_price: 165,
            market_value: 1650,
            unrealized_pnl: 150,
        });
        expect(entry.tags).toEqual(['paper', 'AAPL']);
    });

    it('falls back to avg-cost-only summary when realtime quote is missing', () => {
        const entry = buildPaperPositionEntry({
            ...FULL_POSITION,
            last_price: null,
            market_value: null,
            unrealized_pnl: null,
        });
        expect(entry.summary).toContain('均价 $150.00');
        expect(entry.summary).not.toContain('现价');
        expect(entry.summary).not.toContain('浮动');
        expect(entry.metrics.last_price).toBeNull();
    });

    it('returns null on non-positive quantity', () => {
        expect(buildPaperPositionEntry({ ...FULL_POSITION, quantity: 0 })).toBeNull();
        expect(buildPaperPositionEntry({ ...FULL_POSITION, quantity: -3 })).toBeNull();
        expect(buildPaperPositionEntry({ ...FULL_POSITION, quantity: 'NaN' })).toBeNull();
    });

    it('returns null on missing symbol or null input', () => {
        expect(buildPaperPositionEntry({ ...FULL_POSITION, symbol: '' })).toBeNull();
        expect(buildPaperPositionEntry(null)).toBeNull();
        expect(buildPaperPositionEntry(undefined)).toBeNull();
    });

    it('preserves opened_at and updated_at under raw', () => {
        const entry = buildPaperPositionEntry(FULL_POSITION);
        expect(entry.raw).toEqual({
            opened_at: '2026-05-01T08:00:00+00:00',
            updated_at: '2026-05-04T12:00:00+00:00',
        });
    });
});
