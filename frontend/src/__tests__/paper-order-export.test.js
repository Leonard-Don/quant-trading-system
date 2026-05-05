import {
    buildPaperOrderRows,
    buildPaperOrderCsvFilename,
    PAPER_ORDER_CSV_COLUMNS,
    buildPaperPositionRows,
    buildPaperPositionCsvFilename,
    PAPER_POSITION_CSV_COLUMNS,
} from '../utils/paperOrderExport';

describe('PAPER_ORDER_CSV_COLUMNS', () => {
    it('lists the expected columns in display order', () => {
        const keys = PAPER_ORDER_CSV_COLUMNS.map((c) => c.key);
        expect(keys).toEqual([
            'submitted_at',
            'order_type',
            'symbol',
            'side',
            'quantity',
            'fill_price',
            'effective_fill_price',
            'slippage_bps',
            'commission',
            'note',
        ]);
        // every column has a Chinese title
        PAPER_ORDER_CSV_COLUMNS.forEach((col) => {
            expect(col.title).toBeTruthy();
        });
    });
});

describe('buildPaperOrderRows', () => {
    it('flattens a complete order into the column shape', () => {
        const order = {
            id: 'ord-x',
            submitted_at: '2026-05-05T10:00:00+00:00',
            order_type: 'LIMIT',
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 5,
            fill_price: 100,
            effective_fill_price: 100.05,
            slippage_bps: 5,
            commission: 0.5,
            note: 'limit_triggered',
        };
        expect(buildPaperOrderRows([order])).toEqual([{
            submitted_at: '2026-05-05T10:00:00+00:00',
            order_type: 'LIMIT',
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 5,
            fill_price: 100,
            effective_fill_price: 100.05,
            slippage_bps: 5,
            commission: 0.5,
            note: 'limit_triggered',
        }]);
    });

    it('falls back to fill_price when effective_fill_price is missing (pre-C2 orders)', () => {
        const legacy = {
            submitted_at: '2026-05-01T10:00:00+00:00',
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 5,
            fill_price: 100,
            // no order_type, effective_fill_price, slippage_bps, commission, note
        };
        const rows = buildPaperOrderRows([legacy]);
        expect(rows[0].order_type).toBe('MARKET');
        expect(rows[0].effective_fill_price).toBe(100);
        expect(rows[0].slippage_bps).toBe(0);
        expect(rows[0].commission).toBe(0);
        expect(rows[0].note).toBe('');
    });

    it('returns empty for null / non-array input', () => {
        expect(buildPaperOrderRows(null)).toEqual([]);
        expect(buildPaperOrderRows(undefined)).toEqual([]);
        expect(buildPaperOrderRows('not an array')).toEqual([]);
    });

    it('coerces non-finite numeric fields to safe values without throwing', () => {
        const broken = {
            submitted_at: '2026-05-05T10:00:00+00:00',
            symbol: 'AAPL',
            side: 'BUY',
            quantity: 'oops',
            fill_price: 'NaN',
            slippage_bps: undefined,
        };
        const rows = buildPaperOrderRows([broken]);
        expect(rows[0].quantity).toBe('');
        expect(rows[0].fill_price).toBe('');
        expect(rows[0].slippage_bps).toBe(0);
    });
});

describe('buildPaperOrderCsvFilename', () => {
    it('formats as paper_orders_YYYYMMDD_HHmm', () => {
        // Force a deterministic date
        const fixed = new Date('2026-05-05T10:30:00');
        expect(buildPaperOrderCsvFilename(fixed)).toBe('paper_orders_20260505_1030');
    });

    it('zero-pads single-digit months / days / hours / minutes', () => {
        const fixed = new Date('2026-01-02T03:04:00');
        expect(buildPaperOrderCsvFilename(fixed)).toBe('paper_orders_20260102_0304');
    });

    it('defaults to current time when no Date is passed', () => {
        const result = buildPaperOrderCsvFilename();
        expect(result).toMatch(/^paper_orders_\d{8}_\d{4}$/);
    });
});

describe('PAPER_POSITION_CSV_COLUMNS', () => {
    it('lists position columns in display order', () => {
        const keys = PAPER_POSITION_CSV_COLUMNS.map((c) => c.key);
        expect(keys).toEqual([
            'symbol',
            'quantity',
            'avg_cost',
            'last_price',
            'market_value',
            'unrealized_pnl',
            'stop_loss_price',
            'take_profit_price',
            'opened_at',
            'updated_at',
        ]);
    });
});

describe('buildPaperPositionRows', () => {
    it('flattens an enriched position into the column shape', () => {
        const position = {
            symbol: 'AAPL',
            quantity: 10,
            avg_cost: 150,
            last_price: 165,
            market_value: 1650,
            unrealized_pnl: 150,
            stop_loss_price: 142.5,
            take_profit_price: 180,
            opened_at: '2026-05-01T08:00:00+00:00',
            updated_at: '2026-05-05T12:00:00+00:00',
        };
        expect(buildPaperPositionRows([position])).toEqual([{
            symbol: 'AAPL',
            quantity: 10,
            avg_cost: 150,
            last_price: 165,
            market_value: 1650,
            unrealized_pnl: 150,
            stop_loss_price: 142.5,
            take_profit_price: 180,
            opened_at: '2026-05-01T08:00:00+00:00',
            updated_at: '2026-05-05T12:00:00+00:00',
        }]);
    });

    it('blanks out missing mark-to-market fields (no quote yet)', () => {
        const position = {
            symbol: 'AAPL',
            quantity: 10,
            avg_cost: 150,
            // no last_price / market_value / unrealized_pnl
        };
        const row = buildPaperPositionRows([position])[0];
        expect(row.last_price).toBe('');
        expect(row.market_value).toBe('');
        expect(row.unrealized_pnl).toBe('');
        expect(row.stop_loss_price).toBe('');
        expect(row.take_profit_price).toBe('');
    });

    it('returns empty for null / non-array input', () => {
        expect(buildPaperPositionRows(null)).toEqual([]);
        expect(buildPaperPositionRows(undefined)).toEqual([]);
        expect(buildPaperPositionRows('nope')).toEqual([]);
    });
});

describe('buildPaperPositionCsvFilename', () => {
    it('formats as paper_positions_YYYYMMDD_HHmm', () => {
        const fixed = new Date('2026-05-05T10:30:00');
        expect(buildPaperPositionCsvFilename(fixed)).toBe('paper_positions_20260505_1030');
    });
});
