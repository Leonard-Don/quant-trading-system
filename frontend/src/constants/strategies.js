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
    'turtle_trading': '海龟交易突破',
    'multi_factor': '多因子复合择时',
    'buy_and_hold': '买入持有',
    'batch_backtest': '批量回测实验',
    'combined': '组合策略',
    // Fallback
    'unknown': '未知策略'
};

export const STRATEGY_DETAILS = {
    moving_average: {
        summary: '通过快慢均线交叉识别趋势启动与反转，适合顺着中期趋势做波段跟随。',
        marketFit: '更适合趋势明确、噪音相对较小的行情。',
        style: '趋势跟随',
    },
    rsi: {
        summary: '根据 RSI 超买超卖区间寻找反转机会，适合捕捉短中期回落后的修复段。',
        marketFit: '更适合震荡市、情绪过热或超跌后的反向交易。',
        style: '摆动反转',
    },
    macd: {
        summary: '用 DIF、DEA 与柱状线判断趋势强化或减弱，兼顾启动确认与节奏切换。',
        marketFit: '适合趋势刚形成或正在延续的波段行情。',
        style: '趋势确认',
    },
    bollinger_bands: {
        summary: '围绕价格对均值的偏离程度做突破或回归判断，关注波动扩张后的方向选择。',
        marketFit: '适合波动率切换频繁、突破与回归都较明显的阶段。',
        style: '波动突破',
    },
    mean_reversion: {
        summary: '当价格偏离历史均值过大时逆向入场，假设价格最终会向均值回归。',
        marketFit: '适合横盘震荡、估值和价格容易回归中枢的市场。',
        style: '均值回归',
    },
    momentum: {
        summary: '根据一段时间内累计涨跌幅跟随强势方向，强调强者恒强的延续性。',
        marketFit: '适合持续性强、结构性明显的趋势市场。',
        style: '强势追踪',
    },
    vwap: {
        summary: '以成交量加权均价作为锚点判断价格偏离和回归，强调量价协同。',
        marketFit: '更适合量能变化明显、价格围绕成交重心摆动的场景。',
        style: '量价锚定',
    },
    stochastic: {
        summary: '通过 K/D 指标寻找短线超买超卖与转折点，适合节奏较快的信号交易。',
        marketFit: '适合高波动震荡区间和短线切换频繁的阶段。',
        style: '短线摆动',
    },
    atr_trailing_stop: {
        summary: '用 ATR 动态止损跟踪趋势，同时按波动变化自动调节退出阈值。',
        marketFit: '适合趋势延续但波动较大的行情，强调控制回撤。',
        style: '趋势止损',
    },
    turtle_trading: {
        summary: '以 Donchian 通道突破作为入场信号，用较短退出通道管理离场，适合捕捉中期趋势扩张段。',
        marketFit: '更适合趋势明确、突破后延续性较强的市场，不适合高噪音横盘震荡。',
        style: '突破跟随',
    },
    multi_factor: {
        summary: '把动量、短线回归、成交量脉冲和波动惩罚合成为一个因子分数，再用阈值决定进出场。',
        marketFit: '适合希望同时兼顾趋势延续与节奏过滤的中期择时研究。',
        style: '因子复合',
    },
    buy_and_hold: {
        summary: '首日建仓后持续持有到回测结束，常作为长期配置和策略基准对照。',
        marketFit: '适合长期投资视角，以及和主动交易策略做收益基线比较。',
        style: '基准持有',
    },
    batch_backtest: {
        summary: '把多个策略放在同一实验上下文中批量运行，快速筛选更有潜力的方案。',
        marketFit: '适合研究初筛和多策略横向比较。',
        style: '实验筛选',
    },
    combined: {
        summary: '把多种信号组合到同一套规则中执行，强调策略之间的互补性。',
        marketFit: '适合需要多维信号确认、避免单一指标失真的场景。',
        style: '组合决策',
    },
    unknown: {
        summary: '当前策略暂无详细说明。',
        marketFit: '可先查看参数和结果表现，再决定是否继续研究。',
        style: '待补充',
    },
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
    entry_period: '突破入场周期',
    exit_period: '退出通道周期',
    momentum_window: '动量窗口',
    mean_reversion_window: '回归窗口',
    volume_window: '成交量窗口',
    volatility_window: '波动率窗口',
    ranking_metric: '排名指标',
    top_n: '保留前 N 名',
    initial_capital: '初始资金',
    commission: '手续费 (%)',
    slippage: '滑点 (%)',
    train_period: '训练窗口',
    test_period: '测试窗口',
    step_size: '滚动步长',
    strategies: '策略列表',
    strategy_parameters: '策略参数版本',
};

export const getStrategyName = (key) => {
    if (!key) return STRATEGY_NAMES['unknown'];
    return STRATEGY_NAMES[key] || STRATEGY_NAMES[key.toLowerCase()] || key;
};

export const getStrategyDetails = (key) => {
    if (!key) return STRATEGY_DETAILS.unknown;
    return STRATEGY_DETAILS[key] || STRATEGY_DETAILS[key.toLowerCase()] || STRATEGY_DETAILS.unknown;
};

export const getStrategyDescription = (key) => getStrategyDetails(key).summary;

export const getStrategyParameterLabel = (key, fallback) => {
    if (!key) return fallback || '参数';
    return STRATEGY_PARAMETER_LABELS[key] || fallback || key;
};
