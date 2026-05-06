/**
 * Constants and seed-state factories for the cross-market backtest panel.
 * Pure module — no React, no DOM, no side effects beyond Date.now() in
 * the asset key.
 */

import { getDefaultBacktestDateRangeStrings } from './backtestDefaults';

export const ASSET_CLASS_OPTIONS = [
    { value: 'US_STOCK', label: '美股' },
    { value: 'ETF', label: 'ETF 基金' },
    { value: 'COMMODITY_FUTURES', label: '商品期货' },
];

export const ASSET_CLASS_LABELS = Object.fromEntries(
    ASSET_CLASS_OPTIONS.map((option) => [option.value, option.label])
);

export const CONSTRUCTION_MODE_LABELS = {
    equal_weight: '等权配置',
    ols_hedge: '滚动 OLS 对冲',
};

const [DEFAULT_START, DEFAULT_END] = getDefaultBacktestDateRangeStrings();

export const DEFAULT_CROSS_MARKET_START_DATE = DEFAULT_START;
export const DEFAULT_CROSS_MARKET_END_DATE = DEFAULT_END;

export const DEFAULT_PARAMETERS = {
    lookback: 20,
    entry_threshold: 1.5,
    exit_threshold: 0.5,
};

export const DEFAULT_QUALITY = {
    construction_mode: 'equal_weight',
    min_history_days: 60,
    min_overlap_ratio: 0.7,
};

export const DEFAULT_CONSTRAINTS = {
    max_single_weight: null,
    min_single_weight: null,
};

export const createAsset = (side, index) => ({
    key: `${side}-${index}-${Date.now()}`,
    side,
    symbol: '',
    asset_class: 'ETF',
    weight: null,
});

export const normalizeAssets = (assets, side) =>
    assets
        .filter((asset) => asset.side === side)
        .map((asset) => ({
            ...asset,
            symbol: (asset.symbol || '').trim().toUpperCase(),
        }));
