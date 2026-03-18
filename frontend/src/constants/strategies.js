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

export const STRATEGY_PARAMETER_LABELS = {
    fast_period: '快速周期',
    slow_period: '慢速周期',
    period: '指标周期',
    oversold: '超卖阈值',
    overbought: '超买阈值',
    num_std: '标准差倍数',
    signal_period: '信号线周期',
    lookback_period: '回看周期',
    entry_threshold: '入场阈值',
    exit_threshold: '离场阈值',
    fast_window: '快速窗口',
    slow_window: '慢速窗口',
    k_period: 'K 线周期',
    d_period: 'D 线周期',
    atr_period: 'ATR 周期',
    atr_multiplier: 'ATR 倍数',
};

export const getStrategyName = (key) => {
    if (!key) return STRATEGY_NAMES['unknown'];
    return STRATEGY_NAMES[key] || STRATEGY_NAMES[key.toLowerCase()] || key;
};

export const getStrategyParameterLabel = (key, fallback) => {
    if (!key) return fallback || '参数';
    return STRATEGY_PARAMETER_LABELS[key] || fallback || key;
};
