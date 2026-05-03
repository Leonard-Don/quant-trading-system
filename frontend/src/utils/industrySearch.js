/**
 * Industry name normalization, search, and small DOM-effect helpers
 * extracted from IndustryHeatmap.js so they can be reused by other
 * industry-themed views (ranking, leader, rotation) without duplication.
 */

export const normalizeIndustrySearchText = (value) => String(value || '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[()（）]/g, '')
    .replace(/[-_/]/g, '')
    .replace(/及元件/g, '')
    .replace(/板块/g, '')
    .trim();

export const buildIndustrySearchCandidates = (name) => {
    const raw = String(name || '').trim();
    if (!raw) return [];

    const canonical = raw.replace(/及元件/g, '').replace(/板块/g, '').trim();
    const variants = new Set([
        raw,
        normalizeIndustrySearchText(raw),
        canonical,
        normalizeIndustrySearchText(canonical),
    ]);

    return Array.from(variants).filter(Boolean);
};

export const matchesIndustrySearch = (name, searchTerm) => {
    const normalizedQuery = normalizeIndustrySearchText(searchTerm);
    if (!normalizedQuery) return true;
    return buildIndustrySearchCandidates(name).some(
        (candidate) => normalizeIndustrySearchText(candidate).includes(normalizedQuery)
    );
};

/**
 * Apply / clear the visual focus state on a heatmap tile DOM node.
 * Used by hover and keyboard focus handlers — kept here because it's
 * a tiny imperative DOM mutation that doesn't belong inside React JSX.
 */
export const syncHeatmapTileFocusState = (node, active) => {
    if (!node) return;
    node.style.filter = active ? 'brightness(1.25)' : 'brightness(1)';
    node.style.zIndex = active ? '10' : '1';
    node.style.transform = active ? 'scale(1.02)' : 'scale(1)';
};

/**
 * Pick the best matching snapshot from an industry heatmap *history*
 * response when the live request fails or returns nothing useful.
 * Prefers a snapshot whose `days` field matches the requested timeframe;
 * otherwise falls back to the most recent non-empty snapshot.
 */
export const buildFallbackHeatmapPayload = (historyResponse, timeframe) => {
    const historyItems = Array.isArray(historyResponse?.items) ? historyResponse.items : [];
    const matchingItem = historyItems.find(
        (item) => Number(item?.days || 0) === Number(timeframe || 0) && Array.isArray(item?.industries) && item.industries.length > 0
    );
    const fallbackItem = matchingItem || historyItems.find((item) => Array.isArray(item?.industries) && item.industries.length > 0);

    if (!fallbackItem) {
        return null;
    }

    return {
        industries: fallbackItem.industries || [],
        max_value: fallbackItem.max_value ?? 0,
        min_value: fallbackItem.min_value ?? 0,
        update_time: fallbackItem.update_time || fallbackItem.captured_at || '',
    };
};
