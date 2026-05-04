/**
 * One-shot sessionStorage handoff for prefilling the paper trading order
 * form (e.g. from a backtest "send to paper" action).
 *
 * Why sessionStorage: same-tab transient transfer with automatic isolation
 * across tabs and no URL pollution. Consumer reads + clears, so the prefill
 * doesn't get re-applied on every paper-panel re-mount.
 */

export const PAPER_TRADING_PREFILL_KEY = 'paper-trading-prefill';
export const PAPER_TRADING_PREFILL_TTL_MS = 30_000;

const safeStorage = () => {
    try {
        if (typeof window === 'undefined') return null;
        return window.sessionStorage || null;
    } catch (_err) {
        return null;
    }
};

const now = () => Date.now();

/**
 * Persist a prefill payload. Caller is expected to navigate to the paper
 * workspace shortly after — payload expires after PAPER_TRADING_PREFILL_TTL_MS
 * to avoid a stale handoff sticking around if the user backs out.
 */
export const setPaperPrefill = (payload) => {
    const storage = safeStorage();
    if (!storage) return false;
    const safe = payload && typeof payload === 'object' ? payload : {};
    const stamped = { ...safe, writtenAt: now() };
    try {
        storage.setItem(PAPER_TRADING_PREFILL_KEY, JSON.stringify(stamped));
        return true;
    } catch (_err) {
        return false;
    }
};

/**
 * Pop the prefill payload (read + delete). Returns null if absent, expired,
 * or unparseable.
 */
export const consumePaperPrefill = () => {
    const storage = safeStorage();
    if (!storage) return null;
    let raw;
    try {
        raw = storage.getItem(PAPER_TRADING_PREFILL_KEY);
    } catch (_err) {
        return null;
    }
    // Always attempt removal so a corrupted entry doesn't poison the next read
    try { storage.removeItem(PAPER_TRADING_PREFILL_KEY); } catch (_err) { /* ignore */ }

    if (!raw) return null;
    let parsed;
    try {
        parsed = JSON.parse(raw);
    } catch (_err) {
        return null;
    }
    if (!parsed || typeof parsed !== 'object') return null;
    if (typeof parsed.writtenAt === 'number' && now() - parsed.writtenAt > PAPER_TRADING_PREFILL_TTL_MS) {
        return null;
    }
    return parsed;
};

/**
 * Inspect without consuming. Useful for tests; not part of the production
 * data flow.
 */
export const peekPaperPrefill = () => {
    const storage = safeStorage();
    if (!storage) return null;
    try {
        const raw = storage.getItem(PAPER_TRADING_PREFILL_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (_err) {
        return null;
    }
};

/**
 * Derive a paper-trading prefill payload from a finished backtest result.
 * Returns null if the result is too thin to act on (no symbol).
 */
export const buildPrefillFromBacktest = (results) => {
    if (!results || typeof results !== 'object') return null;
    const symbol = String(results.symbol || '').trim().toUpperCase();
    if (!symbol) return null;

    const trades = Array.isArray(results.trades) ? results.trades : [];
    const lastTrade = trades.length > 0 ? trades[trades.length - 1] : null;
    const side = lastTrade?.type === 'BUY' || lastTrade?.type === 'SELL' ? lastTrade.type : null;
    const rawQuantity = lastTrade?.quantity;
    const quantity = typeof rawQuantity === 'number' && Number.isFinite(rawQuantity) && rawQuantity > 0
        ? rawQuantity
        : null;

    const strategyName = String(results.strategy || '').trim();
    const sourceLabel = strategyName
        ? `由 ${strategyName} · 回测带入`
        : '由回测带入';

    return {
        symbol,
        side,
        quantity,
        sourceLabel,
    };
};
