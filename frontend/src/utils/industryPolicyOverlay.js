/**
 * Pure helpers that join heatmap industry items with the policy_radar
 * `industry_signals` payload, keyed by normalized industry names.
 *
 * Stays free of React / DOM so it can be unit-tested without rendering.
 */

import { normalizeIndustrySearchText } from './industrySearch';

export const POLICY_OVERLAY_THRESHOLD = 0.2;

const safeNumber = (value) => {
    if (value == null) return null;
    const num = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(num) ? num : null;
};

const classifySignal = (avgImpact, providedSignal) => {
    // Trust an explicit upstream signal label when one is provided
    // (the backend already classified using the same threshold), but
    // fall back to local classification for graceful degradation.
    if (providedSignal === 'bullish' || providedSignal === 'bearish' || providedSignal === 'neutral') {
        return providedSignal;
    }
    if (avgImpact == null) return 'neutral';
    if (avgImpact >= POLICY_OVERLAY_THRESHOLD) return 'bullish';
    if (avgImpact <= -POLICY_OVERLAY_THRESHOLD) return 'bearish';
    return 'neutral';
};

/**
 * Build a lookup keyed by normalized industry name. The map preserves
 * the original raw industry name so the consumer can still display it.
 *
 * @param {Array<{name?: string}>} industries
 * @param {Object} industrySignals  Policy provider's per-industry payload.
 *   Shape: { "新能源": { avg_impact: 0.34, mentions: 5, signal: "bullish" }, ... }
 * @returns {Object} Map of normalizedName → enrichment.
 */
export const buildPolicyOverlay = (industries, industrySignals) => {
    if (!industrySignals || typeof industrySignals !== 'object') return {};

    // Pre-index policy entries by normalized name so we can resolve heatmap
    // industries that use slightly different aliases ("新能源" vs "新能源板块").
    const indexed = {};
    Object.entries(industrySignals).forEach(([rawName, info]) => {
        if (!rawName || !info || typeof info !== 'object') return;
        const key = normalizeIndustrySearchText(rawName);
        if (!key) return;
        const avgImpact = safeNumber(info.avg_impact ?? info.avgImpact);
        const mentions = safeNumber(info.mentions);
        const signal = classifySignal(avgImpact, info.signal);
        indexed[key] = {
            policyName: rawName,
            avgImpact,
            mentions: mentions != null ? Math.round(mentions) : 0,
            signal,
        };
    });

    // Optionally project onto the provided heatmap industries — keys not
    // present in heatmap data still get returned, since other consumers
    // (e.g. tooltip lookup keyed off arbitrary industry name) may want them.
    const overlay = { ...indexed };
    if (Array.isArray(industries)) {
        industries.forEach((industry) => {
            const name = industry?.name;
            if (!name) return;
            const key = normalizeIndustrySearchText(name);
            if (!key || overlay[key]) return;
            // No policy data for this heatmap industry; record an explicit miss
            // so callers can distinguish "no overlay enabled" from "no data for
            // this row" if they choose to.
            overlay[key] = null;
        });
    }
    return overlay;
};

/**
 * Look up a single industry's overlay enrichment.
 *
 * @returns enrichment object, or null when no policy data covers the industry
 */
export const lookupPolicyOverlay = (industryName, overlay) => {
    if (!industryName || !overlay || typeof overlay !== 'object') return null;
    const key = normalizeIndustrySearchText(industryName);
    if (!key) return null;
    const entry = overlay[key];
    return entry || null;
};
