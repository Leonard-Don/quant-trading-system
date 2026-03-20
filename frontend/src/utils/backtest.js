const BACKTEST_METRIC_FIELDS = [
  'initial_capital',
  'final_value',
  'total_return',
  'annualized_return',
  'volatility',
  'sharpe_ratio',
  'sortino_ratio',
  'calmar_ratio',
  'max_drawdown',
  'var_95',
  'num_trades',
  'total_trades',
  'num_buy_trades',
  'num_sell_trades',
  'win_rate',
  'profit_factor',
  'best_trade',
  'worst_trade',
  'net_profit',
  'gross_profit',
  'gross_loss',
  'avg_win',
  'avg_loss',
  'total_profit',
  'total_loss',
  'loss_rate',
  'avg_holding_days',
  'avg_trade',
  'max_consecutive_wins',
  'max_consecutive_losses',
  'total_completed_trades',
  'has_open_position',
];

const toNumber = (value, fallback = 0) => {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const normalizeDate = (value, fallback) => {
  if (!value) {
    return fallback;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toISOString();
  }

  return String(value);
};

export const normalizeBacktestTrade = (trade = {}) => {
  const rawType = trade.type || trade.action;
  const normalizedType = String(rawType || '')
    .trim()
    .toUpperCase();
  const type = normalizedType === 'BUY' || normalizedType === 'SELL'
    ? normalizedType
    : (String(trade.action || '').toLowerCase() === 'buy' ? 'BUY' : 'SELL');
  const action = type === 'BUY' ? 'buy' : 'sell';
  const quantity = toNumber(trade.quantity ?? trade.shares, 0);
  const price = toNumber(trade.price, 0);

  let value = trade.value;
  if (value === null || value === undefined) {
    value = type === 'BUY' ? trade.cost : trade.revenue;
  }
  if (value === null || value === undefined) {
    value = price * quantity;
  }

  return {
    ...trade,
    type,
    action,
    shares: quantity,
    quantity,
    price,
    value: toNumber(value, 0),
    cost: trade.cost ?? (type === 'BUY' ? toNumber(value, 0) : undefined),
    revenue: trade.revenue ?? (type === 'SELL' ? toNumber(value, 0) : undefined),
  };
};

export const normalizePortfolioHistory = (portfolio = []) => {
  if (!Array.isArray(portfolio)) {
    return [];
  }

  return portfolio.map((item, index) => {
    const total = toNumber(item.total ?? item.portfolio_value, 0);
    const price = item.price === null || item.price === undefined || item.price === ''
      ? null
      : toNumber(item.price, 0);

    return {
      ...item,
      date: normalizeDate(item.date ?? item.Date ?? item.index ?? item.timestamp, null),
      total,
      portfolio_value: total,
      price,
      signal: toNumber(item.signal, 0),
      returns: toNumber(item.returns, 0),
      cash: toNumber(item.cash, 0),
      holdings: toNumber(item.holdings, 0),
      position: toNumber(item.position, 0),
    };
  });
};

export const normalizeBacktestResult = (backtestResult = {}) => {
  if (!backtestResult || typeof backtestResult !== 'object') {
    return {
      metrics: {},
      performance_metrics: {},
      trades: [],
      portfolio_history: [],
      portfolio: [],
    };
  }

  const nestedMetrics =
    backtestResult.metrics && typeof backtestResult.metrics === 'object'
      ? backtestResult.metrics
      : {};
  const performanceMetrics =
    backtestResult.performance_metrics && typeof backtestResult.performance_metrics === 'object'
      ? backtestResult.performance_metrics
      : {};

  const mergedMetrics = {};
  BACKTEST_METRIC_FIELDS.forEach((field) => {
    if (backtestResult[field] !== undefined) {
      mergedMetrics[field] = backtestResult[field];
    } else if (nestedMetrics[field] !== undefined) {
      mergedMetrics[field] = nestedMetrics[field];
    } else if (performanceMetrics[field] !== undefined) {
      mergedMetrics[field] = performanceMetrics[field];
    }
  });

  const numTrades = toNumber(
    mergedMetrics.num_trades ?? mergedMetrics.total_trades,
    Array.isArray(backtestResult.trades) ? backtestResult.trades.length : 0
  );
  mergedMetrics.num_trades = numTrades;
  mergedMetrics.total_trades = numTrades;

  const trades = Array.isArray(backtestResult.trades)
    ? backtestResult.trades.map((trade) => normalizeBacktestTrade(trade))
    : [];
  const portfolioHistory = normalizePortfolioHistory(
    backtestResult.portfolio_history || backtestResult.portfolio || []
  );

  const normalized = {
    ...backtestResult,
    ...mergedMetrics,
    trades,
    portfolio_history: portfolioHistory,
    portfolio: portfolioHistory,
  };

  normalized.metrics = {
    ...nestedMetrics,
    ...mergedMetrics,
    num_trades: numTrades,
    total_trades: numTrades,
  };
  normalized.performance_metrics = {
    ...performanceMetrics,
    ...mergedMetrics,
    num_trades: numTrades,
    total_trades: numTrades,
  };

  return normalized;
};
