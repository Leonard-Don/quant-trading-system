/**
 * Build a research-journal entry from a finished backtest run.
 *
 * Shape aligns with `backend/app/services/research_journal.py::_normalize_entry`:
 * fields beyond the recognized set are preserved under `raw`.
 *
 * Returns `null` when there's nothing to archive (defensive — caller can
 * skip the network round-trip in that case).
 */

const truncate = (value, maxChars) => {
    if (value == null) return '';
    const text = String(value);
    if (text.length <= maxChars) return text;
    return `${text.slice(0, Math.max(maxChars - 1, 0))}…`;
};

const safeNumber = (value) => {
    if (value == null) return null;
    const num = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(num) ? num : null;
};

const formatPercent = (value, digits = 2) => {
    const num = safeNumber(value);
    if (num === null) return '—';
    return `${(num * 100).toFixed(digits)}%`;
};

export const buildBacktestJournalEntry = (formData, result) => {
    if (!formData || !result) return null;

    const symbol = String(formData.symbol || '').trim().toUpperCase();
    const strategyName = String(formData.strategy_name || formData.strategy || '').trim();

    const titleParts = [strategyName, symbol].filter(Boolean);
    const title = titleParts.length > 0 ? titleParts.join(' · ') : '回测记录';

    const periodParts = [];
    if (formData.start_date) periodParts.push(`起 ${formData.start_date}`);
    if (formData.end_date) periodParts.push(`止 ${formData.end_date}`);
    if (formData.initial_capital != null) {
        periodParts.push(`初始资金 ${formData.initial_capital}`);
    }
    const summaryParts = [];
    if (periodParts.length > 0) summaryParts.push(periodParts.join('，'));

    const totalReturn = safeNumber(result.total_return);
    const sharpe = safeNumber(result.sharpe_ratio);
    const drawdown = safeNumber(result.max_drawdown);
    const numTrades = safeNumber(result.num_trades);
    summaryParts.push(
        `收益 ${formatPercent(totalReturn)}，Sharpe ${sharpe !== null ? sharpe.toFixed(2) : '—'}`
    );

    const entry = {
        type: 'backtest',
        status: 'open',
        priority: 'medium',
        title: truncate(title, 180),
        summary: truncate(summaryParts.join('；'), 360),
        symbol,
        source: 'backtest_auto',
        source_label: '自动归档',
        metrics: {
            total_return: totalReturn,
            sharpe_ratio: sharpe,
            max_drawdown: drawdown,
            num_trades: numTrades,
        },
        raw: {
            strategy: strategyName,
            parameters: formData.strategy_params || formData.parameters || {},
            period: {
                start: formData.start_date || null,
                end: formData.end_date || null,
            },
            initial_capital: formData.initial_capital ?? null,
            commission: formData.commission ?? null,
            slippage: formData.slippage ?? null,
        },
        tags: ['auto', strategyName].filter(Boolean),
    };

    return entry;
};
