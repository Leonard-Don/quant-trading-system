/**
 * Module-level LRU-with-TTL cache for the multi-tab MarketAnalysis API
 * responses, lifted out of MarketAnalysis.js so the host component
 * shrinks and the cache logic can be unit-tested independently.
 *
 * Design notes:
 * - 2-minute TTL — matches the original behavior; long enough to skip
 *   re-fetching when a user toggles among the analysis tabs in quick
 *   succession, short enough that a stale tab catches up on refresh.
 * - 96-entry cap — original constant; protects against pathological
 *   accumulation when the user navigates many symbols.
 * - LRU policy implemented via Map insertion order: deleting + setting
 *   on access bumps an entry to "most recent". Eviction drops the
 *   first-inserted ("oldest") key.
 */

export const ANALYSIS_CACHE_TTL_MS = 2 * 60 * 1000;
export const ANALYSIS_CACHE_MAX_ENTRIES = 96;

const analysisResponseCache = new Map();

export const buildAnalysisCacheKey = (tab, symbol, interval = '') =>
    `${tab}|${symbol || ''}|${interval || ''}`;

const ANALYSIS_TABS_FOR_SYMBOL_PURGE = [
    ['overview', true],
    ['trend', true],
    ['volume', true],
    ['sentiment', true],
    ['pattern', true],
    ['fundamental', false],
    ['technical', true],
    ['events', false],
    ['sentimentHistory', false],
    ['industry', false],
    ['risk', true],
    ['correlation', false],
];

export const clearAnalysisCache = (symbol, interval) => {
    ANALYSIS_TABS_FOR_SYMBOL_PURGE.forEach(([tab, includeInterval]) => {
        const key = buildAnalysisCacheKey(tab, symbol, includeInterval ? interval : '');
        analysisResponseCache.delete(key);
    });
};

export const trimAnalysisCacheToLimit = () => {
    while (analysisResponseCache.size > ANALYSIS_CACHE_MAX_ENTRIES) {
        const oldestCacheKey = analysisResponseCache.keys().next().value;
        if (oldestCacheKey === undefined) return;
        analysisResponseCache.delete(oldestCacheKey);
    }
};

export const sweepExpiredAnalysisCacheEntries = (now = Date.now()) => {
    analysisResponseCache.forEach((entry, cacheKey) => {
        if (now - entry.cachedAt > ANALYSIS_CACHE_TTL_MS) {
            analysisResponseCache.delete(cacheKey);
        }
    });
};

const touchAnalysisCacheEntry = (cacheKey, cachedEntry) => {
    analysisResponseCache.delete(cacheKey);
    analysisResponseCache.set(cacheKey, cachedEntry);
};

export const readAnalysisCacheEntry = (cacheKey, now = Date.now()) => {
    const cached = analysisResponseCache.get(cacheKey);
    if (!cached) return null;

    if (now - cached.cachedAt > ANALYSIS_CACHE_TTL_MS) {
        analysisResponseCache.delete(cacheKey);
        return null;
    }

    touchAnalysisCacheEntry(cacheKey, cached);
    return cached;
};

export const writeAnalysisCache = (cacheKey, data, cachedAt = Date.now()) => {
    sweepExpiredAnalysisCacheEntries(cachedAt);
    analysisResponseCache.delete(cacheKey);
    analysisResponseCache.set(cacheKey, { data, cachedAt });
    trimAnalysisCacheToLimit();
    return cachedAt;
};

export const __TEST_ONLY__ = {
    clearAnalysisResponseCache: () => analysisResponseCache.clear(),
    getAnalysisCacheSize: () => analysisResponseCache.size,
    readAnalysisCacheEntry,
    writeAnalysisCache,
};
