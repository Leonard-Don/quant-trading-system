const DAY_MS = 24 * 60 * 60 * 1000;

export const parseSymbolsInput = (value = '') => Array.from(new Set(
  String(value)
    .split(',')
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
));

const clampNumber = (value, min, max) => {
  let next = Number(value);
  if (Number.isNaN(next)) {
    next = Number(min ?? max ?? 0);
  }
  if (min !== undefined) {
    next = Math.max(min, next);
  }
  if (max !== undefined) {
    next = Math.min(max, next);
  }
  return next;
};

const roundByStep = (value, step = 0.01) => {
  const precision = String(step).includes('.') ? String(step).split('.')[1].length : 0;
  return Number(value.toFixed(precision));
};

const shiftDateString = (value, days) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Date(date.getTime() + days * DAY_MS).toISOString().slice(0, 10);
};

export const buildParameterOptimizationTasks = ({
  symbol,
  strategy,
  dateRange,
  initialCapital,
  commission,
  slippage,
  baseParameters,
  strategyDefinition,
  density = 3,
}) => {
  const tunableEntries = Object.entries(strategyDefinition?.parameters || {}).slice(0, 2);
  if (!tunableEntries.length) {
    return [];
  }

  const valueSets = tunableEntries.map(([key, config]) => {
    const baseValue = Number(baseParameters?.[key] ?? config.default);
    const step = Number(config.step || 1);
    const values = density >= 5
      ? [baseValue - 2 * step, baseValue - step, baseValue, baseValue + step, baseValue + 2 * step]
      : [baseValue - step, baseValue, baseValue + step];
    return [
      key,
      Array.from(new Set(values.map((value) => roundByStep(clampNumber(value, config.min, config.max), step)))),
    ];
  });

  const recurse = (index, current, tasks) => {
    if (index >= valueSets.length) {
      const suffix = Object.entries(current).map(([key, value]) => `${key}:${value}`).join(' | ');
      tasks.push({
        task_id: `opt_${strategy}_${tasks.length + 1}`,
        symbol,
        strategy,
        parameters: { ...baseParameters, ...current },
        start_date: dateRange?.[0],
        end_date: dateRange?.[1],
        initial_capital: initialCapital,
        commission,
        slippage,
        research_label: suffix,
      });
      return;
    }

    const [key, values] = valueSets[index];
    values.forEach((value) => recurse(index + 1, { ...current, [key]: value }, tasks));
  };

  const tasks = [];
  recurse(0, {}, tasks);
  return tasks;
};

export const buildWalkForwardParameterCandidates = ({
  baseParameters,
  strategyDefinition,
  density = 3,
}) => {
  const tunableEntries = Object.entries(strategyDefinition?.parameters || {}).slice(0, 2);
  if (!tunableEntries.length) {
    return [baseParameters || {}];
  }

  const valueSets = tunableEntries.map(([key, config]) => {
    const baseValue = Number(baseParameters?.[key] ?? config.default);
    const step = Number(config.step || (config.type === 'float' ? 0.1 : 1));
    const values = density >= 5
      ? [baseValue - 2 * step, baseValue - step, baseValue, baseValue + step, baseValue + 2 * step]
      : [baseValue - step, baseValue, baseValue + step];
    return [
      key,
      Array.from(new Set(values.map((value) => roundByStep(clampNumber(value, config.min, config.max), step)))),
    ];
  });

  const candidates = [];
  const recurse = (index, current) => {
    if (index >= valueSets.length) {
      candidates.push({
        ...(baseParameters || {}),
        ...current,
      });
      return;
    }

    const [key, values] = valueSets[index];
    values.forEach((value) => recurse(index + 1, { ...current, [key]: value }));
  };

  recurse(0, {});
  return candidates;
};

export const buildMultiSymbolTasks = ({
  symbols,
  strategy,
  dateRange,
  initialCapital,
  commission,
  slippage,
  baseParameters,
}) => symbols.map((symbol, index) => ({
  task_id: `multi_${strategy}_${symbol}_${index + 1}`,
  symbol,
  strategy,
  parameters: baseParameters,
  start_date: dateRange?.[0],
  end_date: dateRange?.[1],
  initial_capital: initialCapital,
  commission,
  slippage,
  research_label: `${symbol} · 横向研究`,
}));

export const buildCostSensitivityTasks = ({
  symbol,
  strategy,
  dateRange,
  initialCapital,
  commission,
  slippage,
  baseParameters,
}) => {
  const scenarios = [
    { key: 'low', label: '低成本', commission: commission * 0.5, slippage: slippage * 0.5 },
    { key: 'base', label: '基准成本', commission, slippage },
    { key: 'high', label: '高成本', commission: commission * 2, slippage: slippage * 2 },
  ];
  return scenarios.map((scenario, index) => ({
    task_id: `cost_${strategy}_${scenario.key}_${index + 1}`,
    symbol,
    strategy,
    parameters: baseParameters,
    start_date: dateRange?.[0],
    end_date: dateRange?.[1],
    initial_capital: initialCapital,
    commission: scenario.commission,
    slippage: scenario.slippage,
    research_label: scenario.label,
  }));
};

export const buildRobustnessTasks = ({
  symbol,
  strategy,
  dateRange,
  initialCapital,
  commission,
  slippage,
  baseParameters,
  strategyDefinition,
}) => {
  const tasks = [
    {
      task_id: `robust_${strategy}_base`,
      symbol,
      strategy,
      parameters: baseParameters,
      start_date: dateRange?.[0],
      end_date: dateRange?.[1],
      initial_capital: initialCapital,
      commission,
      slippage,
      research_label: '基准窗口',
    },
  ];

  if (dateRange?.[0] && dateRange?.[1]) {
    tasks.push({
      ...tasks[0],
      task_id: `robust_${strategy}_earlier`,
      start_date: shiftDateString(dateRange[0], 30),
      end_date: shiftDateString(dateRange[1], -30),
      research_label: '收缩窗口',
    });
    tasks.push({
      ...tasks[0],
      task_id: `robust_${strategy}_later`,
      start_date: shiftDateString(dateRange[0], -30),
      end_date: shiftDateString(dateRange[1], 30),
      research_label: '扩展窗口',
    });
  }

  const firstParamEntry = Object.entries(strategyDefinition?.parameters || {})[0];
  if (firstParamEntry) {
    const [key, config] = firstParamEntry;
    const baseValue = Number(baseParameters?.[key] ?? config.default);
    const delta = Math.max(Number(config.step || 1), Math.abs(baseValue) * 0.1);
    tasks.push({
      ...tasks[0],
      task_id: `robust_${strategy}_param_low`,
      parameters: {
        ...baseParameters,
        [key]: roundByStep(clampNumber(baseValue - delta, config.min, config.max), config.step || 0.01),
      },
      research_label: `${key} 下探`,
    });
    tasks.push({
      ...tasks[0],
      task_id: `robust_${strategy}_param_high`,
      parameters: {
        ...baseParameters,
        [key]: roundByStep(clampNumber(baseValue + delta, config.min, config.max), config.step || 0.01),
      },
      research_label: `${key} 上调`,
    });
  }

  return tasks;
};

export const buildBenchmarkSummary = (compareData = {}, strategyName) => {
  const active = compareData?.[strategyName];
  const benchmark = compareData?.buy_and_hold;
  if (!active || !benchmark) {
    return null;
  }

  const excessReturn = Number(active.total_return || 0) - Number(benchmark.total_return || 0);
  const sharpeDelta = Number(active.sharpe_ratio || 0) - Number(benchmark.sharpe_ratio || 0);
  const drawdownDelta = Math.abs(Number(active.max_drawdown || 0)) - Math.abs(Number(benchmark.max_drawdown || 0));

  return {
    excessReturn,
    sharpeDelta,
    drawdownDelta,
    beatBenchmark: excessReturn > 0,
  };
};

export const buildSignalExplanation = (result = {}) => {
  const trades = Array.isArray(result.trades) ? result.trades : [];
  const completedTrades = trades.filter((trade) => String(trade.type || '').toUpperCase() === 'SELL');
  const bestTrade = completedTrades.reduce((best, trade) => (
    Number(trade.pnl || 0) > Number(best?.pnl || -Infinity) ? trade : best
  ), null);
  const worstTrade = completedTrades.reduce((worst, trade) => (
    Number(trade.pnl || 0) < Number(worst?.pnl || Infinity) ? trade : worst
  ), null);

  const summary = [];
  if (Number(result.total_return || 0) > 0) {
    summary.push(`这次回测整体取得 ${((Number(result.total_return || 0)) * 100).toFixed(2)}% 收益，策略方向判断是有效的。`);
  } else {
    summary.push(`这次回测整体收益为 ${((Number(result.total_return || 0)) * 100).toFixed(2)}%，当前信号在这段区间内没有形成稳定优势。`);
  }

  if (bestTrade) {
    summary.push(`最有贡献的一笔交易盈亏约 ${Number(bestTrade.pnl || 0).toFixed(2)}，说明策略在顺风段仍能抓到主要利润。`);
  }

  if (worstTrade) {
    summary.push(`拖累最大的交易约 ${Number(worstTrade.pnl || 0).toFixed(2)}，可以重点回看当时的进出场条件是否过慢。`);
  }

  if (result.has_open_position) {
    summary.push('回测结束时仍有未平仓头寸，说明最后一段趋势还没完全走完。');
  }

  if (!completedTrades.length && String(result.strategy || '') === 'buy_and_hold') {
    summary.push('买入持有策略本身用于基准对照，所以不会产生频繁交易信号。');
  }

  return summary;
};

export const buildBacktestActionPosture = ({
  result = {},
  benchmarkSummary = null,
} = {}) => {
  const totalReturn = Number(result.total_return || 0);
  const sharpeRatio = Number(result.sharpe_ratio || 0);
  const maxDrawdown = Math.abs(Number(result.max_drawdown || 0));
  const profitFactor = Number(result.profit_factor || 0);
  const winRate = Number(result.win_rate || 0);
  const tradeCount = Number(result.num_trades || 0);
  const beatBenchmark = benchmarkSummary ? Boolean(benchmarkSummary.beatBenchmark) : null;

  if (
    totalReturn <= 0
    || sharpeRatio < 0.6
    || maxDrawdown >= 0.2
    || (beatBenchmark === false && Number(benchmarkSummary?.excessReturn || 0) <= -0.03)
  ) {
    return {
      type: 'warning',
      label: 'review',
      posture: '先回测复核',
      title: '当前结果更适合先回到参数与风险假设复核',
      actionHint: '先回看参数、成本和风控假设，再决定是否继续把这套策略推进到后续实验。',
      reason: beatBenchmark === false && Number(benchmarkSummary?.excessReturn || 0) <= -0.03
        ? `当前相对基准落后 ${((Number(benchmarkSummary?.excessReturn || 0)) * 100).toFixed(2)}%，结果还不能直接推进。`
        : maxDrawdown >= 0.2
          ? `最大回撤已到 ${(maxDrawdown * 100).toFixed(2)}%，当前更适合先压缩风险再继续。`
          : `当前收益 ${((totalReturn) * 100).toFixed(2)}%，夏普 ${sharpeRatio.toFixed(2)}，结果还不够稳。`,
    };
  }

  if (
    totalReturn > 0
    && sharpeRatio >= 1
    && maxDrawdown <= 0.15
    && profitFactor >= 1.2
    && winRate >= 0.45
    && (beatBenchmark !== false)
  ) {
    return {
      type: 'success',
      label: 'advance',
      posture: '继续稳健性验证',
      title: '当前结果可以推进到稳健性与扩展验证',
      actionHint: '可以继续做滚动窗口、成本敏感性和市场状态验证，而不是只停留在单次回测结果。',
      reason: `当前收益 ${((totalReturn) * 100).toFixed(2)}%，夏普 ${sharpeRatio.toFixed(2)}，回撤 ${(maxDrawdown * 100).toFixed(2)}%，基础画像相对健康。`,
    };
  }

  return {
    type: 'info',
    label: 'observe',
    posture: '继续观察与补证',
    title: '当前结果适合继续观察并补充验证',
    actionHint: '可以继续补做基准对照、训练窗口切换和交易成本测试，再决定是否升级结论。',
    reason: tradeCount <= 1
      ? '当前交易样本还比较少，先把结果当作方向信号而不是定论。'
      : `当前收益 ${(totalReturn * 100).toFixed(2)}%，夏普 ${sharpeRatio.toFixed(2)}，还需要更多稳健性证据。`,
  };
};
