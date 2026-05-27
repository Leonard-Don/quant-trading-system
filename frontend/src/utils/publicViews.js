const DEFAULT_PUBLIC_VIEW = 'backtest';

export const VIEW_QUERY_KEY = 'view';
export const PUBLIC_VIEW_IDS = ['today', 'backtest', 'realtime', 'industry', 'paper', 'etf'];
export const PUBLIC_VIEWS = new Set(PUBLIC_VIEW_IDS);
const PUBLIC_VIEW_ALIASES = {
  alerts: 'realtime',
};

export const normalizePublicView = (view = DEFAULT_PUBLIC_VIEW) => {
  const normalized = String(view || DEFAULT_PUBLIC_VIEW).trim().toLowerCase();
  const aliased = PUBLIC_VIEW_ALIASES[normalized] || normalized;
  return PUBLIC_VIEWS.has(aliased) ? aliased : DEFAULT_PUBLIC_VIEW;
};
