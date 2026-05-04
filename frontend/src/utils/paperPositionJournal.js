/**
 * Build a research-journal entry from a paper-trading position.
 *
 * Stable id keyed on `paper-position:<SYMBOL>`: re-archiving the same
 * symbol just updates the existing entry (research_journal_store
 * deduplicates by id and prefers the newer updated_at), so the journal
 * never accumulates a stack of historical paper-position rows for the
 * same ticker.
 */

const safeNumber = (value) => {
    if (value == null) return null;
    const num = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(num) ? num : null;
};

const formatMoney = (value) => {
    const num = safeNumber(value);
    if (num === null) return '—';
    return `$${num.toFixed(2)}`;
};

const formatSignedMoney = (value) => {
    const num = safeNumber(value);
    if (num === null) return '—';
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}`;
};

const formatPercentMaybe = (value) => {
    const num = safeNumber(value);
    if (num === null) return null;
    return `${(num * 100).toFixed(2)}%`;
};

export const buildPaperPositionEntry = (position) => {
    if (!position || typeof position !== 'object') return null;
    const symbol = String(position.symbol || '').trim().toUpperCase();
    if (!symbol) return null;

    const quantity = safeNumber(position.quantity);
    if (quantity === null || quantity <= 0) return null;

    const avgCost = safeNumber(position.avg_cost);
    const lastPrice = safeNumber(position.last_price);
    const marketValue = safeNumber(position.market_value);
    const unrealizedPnl = safeNumber(position.unrealized_pnl);
    const pnlPctValue = lastPrice !== null && avgCost !== null && avgCost > 0
        ? (lastPrice - avgCost) / avgCost
        : null;
    const pnlPct = formatPercentMaybe(pnlPctValue);

    const summaryParts = [];
    if (avgCost !== null) summaryParts.push(`均价 ${formatMoney(avgCost)}`);
    if (lastPrice !== null) summaryParts.push(`现价 ${formatMoney(lastPrice)}`);
    if (unrealizedPnl !== null) {
        const pnlBlock = pnlPct ? `浮动 ${formatSignedMoney(unrealizedPnl)} (${pnlPct})` : `浮动 ${formatSignedMoney(unrealizedPnl)}`;
        summaryParts.push(pnlBlock);
    }

    return {
        id: `paper-position:${symbol}`,
        type: 'trade_plan',
        status: 'open',
        priority: 'medium',
        title: `${symbol} 纸面持仓 ${quantity} 股`,
        summary: summaryParts.join('，'),
        symbol,
        source: 'paper_trading',
        source_label: '纸面账户',
        metrics: {
            quantity,
            avg_cost: avgCost,
            last_price: lastPrice,
            market_value: marketValue,
            unrealized_pnl: unrealizedPnl,
        },
        raw: {
            opened_at: position.opened_at || null,
            updated_at: position.updated_at || null,
        },
        tags: ['paper', symbol],
    };
};
