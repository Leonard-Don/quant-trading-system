import { buildBacktestJournalEntry } from '../utils/backtestJournalEntry';

describe('buildBacktestJournalEntry', () => {
    const FORM = {
        symbol: 'aapl',
        strategy_name: 'MovingAverageCrossover',
        start_date: '2024-01-01',
        end_date: '2024-12-31',
        initial_capital: 100000,
        commission: 0.001,
        slippage: 0.001,
        strategy_params: { fast_period: 10, slow_period: 30 },
    };

    const RESULT = {
        total_return: 0.184,
        sharpe_ratio: 1.42,
        max_drawdown: 0.083,
        num_trades: 12,
    };

    it('produces a journal entry with the expected envelope', () => {
        const entry = buildBacktestJournalEntry(FORM, RESULT);
        expect(entry).toMatchObject({
            type: 'backtest',
            status: 'open',
            priority: 'medium',
            symbol: 'AAPL',
            source: 'backtest_auto',
            source_label: '自动归档',
        });
        expect(entry.title).toContain('MovingAverageCrossover');
        expect(entry.title).toContain('AAPL');
        expect(entry.tags).toContain('auto');
        expect(entry.tags).toContain('MovingAverageCrossover');
    });

    it('captures key performance metrics for downstream comparison', () => {
        const entry = buildBacktestJournalEntry(FORM, RESULT);
        expect(entry.metrics).toEqual({
            total_return: 0.184,
            sharpe_ratio: 1.42,
            max_drawdown: 0.083,
            num_trades: 12,
        });
    });

    it('preserves the strategy parameters and period under raw', () => {
        const entry = buildBacktestJournalEntry(FORM, RESULT);
        expect(entry.raw.strategy).toBe('MovingAverageCrossover');
        expect(entry.raw.parameters).toEqual({ fast_period: 10, slow_period: 30 });
        expect(entry.raw.period).toEqual({ start: '2024-01-01', end: '2024-12-31' });
        expect(entry.raw.initial_capital).toBe(100000);
    });

    it('summary embeds period and headline metrics in human form', () => {
        const entry = buildBacktestJournalEntry(FORM, RESULT);
        expect(entry.summary).toContain('2024-01-01');
        expect(entry.summary).toContain('2024-12-31');
        expect(entry.summary).toContain('18.40%');
        expect(entry.summary).toContain('1.42');
    });

    it('returns null when either side is missing', () => {
        expect(buildBacktestJournalEntry(null, RESULT)).toBeNull();
        expect(buildBacktestJournalEntry(FORM, null)).toBeNull();
    });

    it('handles non-finite metrics gracefully', () => {
        const entry = buildBacktestJournalEntry(FORM, {
            total_return: 'NaN',
            sharpe_ratio: undefined,
            max_drawdown: null,
            num_trades: 'oops',
        });
        expect(entry.metrics.total_return).toBeNull();
        expect(entry.metrics.sharpe_ratio).toBeNull();
        expect(entry.metrics.max_drawdown).toBeNull();
        expect(entry.metrics.num_trades).toBeNull();
        // Summary still renders with em-dash placeholders rather than throwing
        expect(entry.summary).toContain('—');
    });

    it('falls back gracefully when symbol or strategy name is missing', () => {
        const entry = buildBacktestJournalEntry({ ...FORM, symbol: '', strategy_name: '' }, RESULT);
        expect(entry.title).toBe('回测记录');
        expect(entry.symbol).toBe('');
        expect(entry.tags).toEqual(['auto']);
    });
});
