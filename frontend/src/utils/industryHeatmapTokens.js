/**
 * Visual tokens (CSS-variable-based colors, gradients, shadows) and request
 * timeouts shared by the industry heatmap view. Extracted from
 * IndustryHeatmap.js so the same palette can be referenced by future
 * sub-components (tooltip / legend / overlay) without duplication.
 */

export const HEATMAP_SURFACE = 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 90%, var(--bg-primary) 10%) 0%, color-mix(in srgb, var(--bg-secondary) 82%, var(--bg-primary) 18%) 100%)';
export const TOOLTIP_BG = 'color-mix(in srgb, var(--bg-primary) 88%, #0f172a 12%)';
export const TOOLTIP_PANEL = 'color-mix(in srgb, var(--bg-secondary) 92%, var(--bg-primary) 8%)';
export const TOOLTIP_PANEL_BORDER = 'color-mix(in srgb, var(--border-color) 82%, var(--text-primary) 18%)';
export const TOOLTIP_TEXT = 'var(--text-primary)';
export const TOOLTIP_MUTED = 'var(--text-secondary)';
export const TOOLTIP_SUBTLE = 'var(--text-muted)';
export const TOOLTIP_SHADOW = '0 10px 30px rgba(15, 23, 42, 0.18)';
export const HEATMAP_POSITIVE = 'var(--accent-danger)';
export const HEATMAP_NEGATIVE = 'var(--accent-success)';
export const HEATMAP_WARNING = 'var(--accent-warning)';
// Stronger shadow keeps tile labels readable on muted (~0%) tiles where
// the background can dip toward neutral grey.
export const TILE_TEXT_SHADOW = '0 1px 2px rgba(15, 23, 42, 0.55), 0 1px 6px rgba(15, 23, 42, 0.32)';

export const HEATMAP_LIVE_REQUEST_TIMEOUT_MS = 12000;
export const HEATMAP_HISTORY_FALLBACK_TIMEOUT_MS = 6000;
