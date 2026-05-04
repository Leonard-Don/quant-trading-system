/**
 * Constants and option lists used by the realtime panel. Pure module —
 * no React, no DOM, no side effects. Imported separately so test code
 * can assert on default lists / themes without dragging the host
 * component (and its 79 hooks) into the module graph.
 */

export const EMPTY_NUMERIC_TEXT = '--';
export const REALTIME_DIAGNOSTICS_STORAGE_KEY = 'realtime-panel:diagnostics-enabled';
export const REVIEW_SNAPSHOT_VERSION = 2;
export const REALTIME_EXPORT_VERSION = 1;

export const QUOTE_SORT_OPTIONS = [
    { key: 'change_desc', label: '涨跌幅' },
    { key: 'range_desc', label: '振幅' },
    { key: 'volume_desc', label: '成交量' },
    { key: 'symbol_asc', label: '代码' },
];

export const REVIEW_SCOPE_OPTIONS = [
    { key: 'all', label: '全部' },
    { key: 'recent7d', label: '最近7天' },
    { key: 'recent20', label: '最近20条' },
    { key: 'activeTab', label: '当前分组' },
];

export const DETAIL_COMPARE_CANDIDATE_LIMIT = 6;
export const DETAIL_PREFETCH_SYMBOL_LIMIT = 3;

export const SNAPSHOT_OUTCOME_OPTIONS = {
    watching: { label: '继续观察', color: 'default' },
    validated: { label: '验证有效', color: 'success' },
    invalidated: { label: '观察失效', color: 'error' },
};

export const DEFAULT_SUBSCRIBED_SYMBOLS = [
    '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
    'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'BABA',
    '600519.SS', '601398.SS', '300750.SZ', '000858.SZ',
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'DOGE-USD',
    '^TNX', '^TYX', 'TLT',
    'GC=F', 'CL=F', 'SI=F',
    'SPY', 'QQQ', 'UVXY',
];

export const CATEGORY_THEMES = {
    index: { label: '指数', accent: '#0ea5e9', soft: 'rgba(14, 165, 233, 0.12)' },
    us: { label: '美股', accent: '#22c55e', soft: 'rgba(34, 197, 94, 0.12)' },
    cn: { label: 'A股', accent: '#f97316', soft: 'rgba(249, 115, 22, 0.12)' },
    crypto: { label: '加密', accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' },
    bond: { label: '债券', accent: '#6366f1', soft: 'rgba(99, 102, 241, 0.12)' },
    future: { label: '期货', accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)' },
    option: { label: '期权', accent: '#a855f7', soft: 'rgba(168, 85, 247, 0.12)' },
    other: { label: '其他', accent: '#64748b', soft: 'rgba(100, 116, 139, 0.12)' },
};

export const CATEGORY_OPTIONS = [
    { key: 'index', label: '指数' },
    { key: 'us', label: '美股' },
    { key: 'cn', label: 'A股' },
    { key: 'crypto', label: '加密' },
    { key: 'bond', label: '债券' },
    { key: 'future', label: '期货' },
    { key: 'option', label: '期权' },
    { key: 'other', label: '其他' },
];
