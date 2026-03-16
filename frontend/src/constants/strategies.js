// 策略名称映射 (中英文对照)
export const STRATEGY_NAMES = {
    'moving_average': '移动平均策略',
    'rsi': 'RSI强弱指标',
    'macd': 'MACD趋势跟随',
    'bollinger_bands': '布林带突破',
    'mean_reversion': '均值回归',
    'momentum': '动量策略',
    'vwap': 'VWAP成交量加权',
    'stochastic': '随机指标策略',
    'atr_trailing_stop': 'ATR移动止损',
    'buy_and_hold': '买入持有',
    'combined': '组合策略',
    // Fallback
    'unknown': '未知策略'
};

export const getStrategyName = (key) => {
    if (!key) return STRATEGY_NAMES['unknown'];
    return STRATEGY_NAMES[key] || STRATEGY_NAMES[key.toLowerCase()] || key;
};
