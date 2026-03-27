const hasNumericValue = (value) => value !== null && value !== undefined && !Number.isNaN(Number(value));

const toNumber = (value) => (hasNumericValue(value) ? Number(value) : null);

export const getIntradayRangePercent = (quote) => {
  const low = toNumber(quote?.low);
  const high = toNumber(quote?.high);
  const previousClose = toNumber(quote?.previous_close);

  if (low === null || high === null || previousClose === null || previousClose === 0) {
    return null;
  }

  return ((high - low) / previousClose) * 100;
};

export const getRelativeVolumeRatio = (symbol, allQuotes = {}) => {
  const volumes = Object.values(allQuotes)
    .map((quote) => toNumber(quote?.volume))
    .filter((value) => value !== null && value > 0);
  const targetVolume = toNumber(allQuotes[symbol]?.volume);
  const baseline = getMedian(volumes);

  if (targetVolume === null || baseline === null || baseline === 0) {
    return null;
  }

  return targetVolume / baseline;
};

export const isNearDayExtreme = (quote, type = 'high', tolerancePercent = 0.1) => {
  const price = toNumber(quote?.price);
  const extreme = toNumber(type === 'low' ? quote?.low : quote?.high);

  if (price === null || extreme === null || extreme === 0) {
    return false;
  }

  const distancePercent = Math.abs((price - extreme) / extreme) * 100;
  return distancePercent <= tolerancePercent;
};

export const normalizePriceAlert = (alert = {}) => {
  const conditionMap = {
    above: 'price_above',
    below: 'price_below',
  };

  const condition = conditionMap[alert.condition] || alert.condition || 'price_above';
  const normalizedThreshold = hasNumericValue(alert.threshold)
    ? Number(alert.threshold)
    : hasNumericValue(alert.price)
      ? Number(alert.price)
      : null;

  return {
    ...alert,
    condition,
    threshold: normalizedThreshold,
    tolerancePercent: hasNumericValue(alert.tolerancePercent) ? Number(alert.tolerancePercent) : 0.1,
  };
};

export const getAlertConditionLabel = (alert = {}) => {
  const normalized = normalizePriceAlert(alert);
  const thresholdText = hasNumericValue(normalized.threshold) ? Number(normalized.threshold).toFixed(2) : '--';

  switch (normalized.condition) {
    case 'price_above':
      return `价格 ≥ $${thresholdText}`;
    case 'price_below':
      return `价格 ≤ $${thresholdText}`;
    case 'change_pct_above':
      return `涨跌幅 ≥ ${thresholdText}%`;
    case 'change_pct_below':
      return `涨跌幅 ≤ ${thresholdText}%`;
    case 'intraday_range_above':
      return `日内振幅 ≥ ${thresholdText}%`;
    case 'relative_volume_above':
      return `相对放量 ≥ ${thresholdText}x`;
    case 'touch_high':
      return '触及日内新高';
    case 'touch_low':
      return '触及日内新低';
    default:
      return normalized.condition || '未知条件';
  }
};

export const evaluateRealtimeAlert = (rawAlert, quote, allQuotes = {}) => {
  const alert = normalizePriceAlert(rawAlert);
  if (!quote) {
    return { triggered: false };
  }

  const price = toNumber(quote.price);
  const changePercent = toNumber(quote.change_percent);
  const intradayRangePercent = getIntradayRangePercent(quote);
  const relativeVolumeRatio = getRelativeVolumeRatio(alert.symbol, allQuotes);

  switch (alert.condition) {
    case 'price_above':
      if (price !== null && alert.threshold !== null && price >= alert.threshold) {
        return {
          triggered: true,
          triggerValue: price,
          message: `${alert.symbol} 当前价格 $${price.toFixed(2)} 已突破 $${alert.threshold.toFixed(2)}`,
        };
      }
      break;
    case 'price_below':
      if (price !== null && alert.threshold !== null && price <= alert.threshold) {
        return {
          triggered: true,
          triggerValue: price,
          message: `${alert.symbol} 当前价格 $${price.toFixed(2)} 已跌破 $${alert.threshold.toFixed(2)}`,
        };
      }
      break;
    case 'change_pct_above':
      if (changePercent !== null && alert.threshold !== null && changePercent >= alert.threshold) {
        return {
          triggered: true,
          triggerValue: changePercent,
          message: `${alert.symbol} 当前涨跌幅 ${changePercent.toFixed(2)}% 已超过 ${alert.threshold.toFixed(2)}%`,
        };
      }
      break;
    case 'change_pct_below':
      if (changePercent !== null && alert.threshold !== null && changePercent <= alert.threshold) {
        return {
          triggered: true,
          triggerValue: changePercent,
          message: `${alert.symbol} 当前涨跌幅 ${changePercent.toFixed(2)}% 已低于 ${alert.threshold.toFixed(2)}%`,
        };
      }
      break;
    case 'intraday_range_above':
      if (intradayRangePercent !== null && alert.threshold !== null && intradayRangePercent >= alert.threshold) {
        return {
          triggered: true,
          triggerValue: intradayRangePercent,
          message: `${alert.symbol} 日内振幅 ${intradayRangePercent.toFixed(2)}% 已超过 ${alert.threshold.toFixed(2)}%`,
        };
      }
      break;
    case 'relative_volume_above':
      if (relativeVolumeRatio !== null && alert.threshold !== null && relativeVolumeRatio >= alert.threshold) {
        return {
          triggered: true,
          triggerValue: relativeVolumeRatio,
          message: `${alert.symbol} 当前成交量已达到分组中位数的 ${relativeVolumeRatio.toFixed(2)} 倍`,
        };
      }
      break;
    case 'touch_high':
      if (isNearDayExtreme(quote, 'high', alert.tolerancePercent)) {
        return {
          triggered: true,
          triggerValue: price,
          message: `${alert.symbol} 当前价格已触及日内高点附近`,
        };
      }
      break;
    case 'touch_low':
      if (isNearDayExtreme(quote, 'low', alert.tolerancePercent)) {
        return {
          triggered: true,
          triggerValue: price,
          message: `${alert.symbol} 当前价格已触及日内低点附近`,
        };
      }
      break;
    default:
      break;
  }

  return { triggered: false };
};

const getMedian = (values) => {
  if (!values.length) {
    return null;
  }

  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }
  return sorted[middle];
};

export const buildRealtimeAnomalyFeed = (symbols = [], quotes = {}, options = {}) => {
  const {
    limit = 6,
    priceMoveThreshold = 2,
    rangeThreshold = 3,
    volumeSpikeRatio = 2,
  } = options;

  const normalizedSymbols = symbols.filter(Boolean);
  const volumeBaseline = getMedian(
    normalizedSymbols
      .map((symbol) => toNumber(quotes[symbol]?.volume))
      .filter((value) => value !== null && value > 0)
  );

  const events = [];
  normalizedSymbols.forEach((symbol) => {
    const quote = quotes[symbol];
    if (!quote) {
      return;
    }

    const changePercent = toNumber(quote.change_percent);
    const volume = toNumber(quote.volume);
    const rangePercent = getIntradayRangePercent(quote);
    const timestamp = quote._clientReceivedAt || quote.timestamp || Date.now();

    if (changePercent !== null && changePercent >= priceMoveThreshold) {
      events.push({
        id: `${symbol}-price-up`,
        symbol,
        kind: 'price_up',
        severity: Math.abs(changePercent),
        title: '强势拉升',
        description: `${symbol} 当前涨幅 ${changePercent.toFixed(2)}%，处于盘中强势区间。`,
        timestamp,
      });
    }

    if (changePercent !== null && changePercent <= -priceMoveThreshold) {
      events.push({
        id: `${symbol}-price-down`,
        symbol,
        kind: 'price_down',
        severity: Math.abs(changePercent),
        title: '快速回落',
        description: `${symbol} 当前跌幅 ${Math.abs(changePercent).toFixed(2)}%，需留意盘中回撤。`,
        timestamp,
      });
    }

    if (rangePercent !== null && rangePercent >= rangeThreshold) {
      events.push({
        id: `${symbol}-range`,
        symbol,
        kind: 'range_expansion',
        severity: rangePercent,
        title: '振幅扩张',
        description: `${symbol} 日内振幅 ${rangePercent.toFixed(2)}%，波动显著放大。`,
        timestamp,
      });
    }

    if (volumeBaseline && volume !== null && volume >= volumeBaseline * volumeSpikeRatio) {
      events.push({
        id: `${symbol}-volume`,
        symbol,
        kind: 'volume_spike',
        severity: volume / volumeBaseline,
        title: '放量异动',
        description: `${symbol} 当前成交量约为分组中位数的 ${(volume / volumeBaseline).toFixed(1)} 倍。`,
        timestamp,
      });
    }

    if (isNearDayExtreme(quote, 'high') && (changePercent ?? 0) >= 0) {
      events.push({
        id: `${symbol}-high`,
        symbol,
        kind: 'touch_high',
        severity: Math.abs(changePercent || 0) + 0.5,
        title: '逼近日高',
        description: `${symbol} 当前价格接近日内高点，短线突破关注度提升。`,
        timestamp,
      });
    }

    if (isNearDayExtreme(quote, 'low') && (changePercent ?? 0) <= 0) {
      events.push({
        id: `${symbol}-low`,
        symbol,
        kind: 'touch_low',
        severity: Math.abs(changePercent || 0) + 0.5,
        title: '逼近日低',
        description: `${symbol} 当前价格接近日内低点，需留意继续走弱。`,
        timestamp,
      });
    }
  });

  return events
    .sort((left, right) => {
      if (right.severity !== left.severity) {
        return right.severity - left.severity;
      }
      return new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime();
    })
    .slice(0, limit);
};

const roundThreshold = (value, step, direction = 'up') => {
  if (!hasNumericValue(value)) {
    return null;
  }

  const numericValue = Number(value);
  const scaled = numericValue / step;
  return direction === 'down'
    ? Math.floor(scaled) * step
    : Math.ceil(scaled) * step;
};

const roundPrice = (value) => {
  if (!hasNumericValue(value)) {
    return null;
  }

  return Math.round(Number(value) * 100) / 100;
};

const getSuggestedQuantity = (symbol, price) => {
  if (!symbol) {
    return 100;
  }

  if (/-USD$/i.test(symbol)) {
    return 1;
  }

  if (price !== null && price >= 1000) {
    return 10;
  }

  if (price !== null && price >= 200) {
    return 25;
  }

  if (price !== null && price >= 50) {
    return 50;
  }

  return 100;
};

export const buildAlertDraftFromAnomaly = (item, quote, allQuotes = {}) => {
  if (!item?.symbol) {
    return null;
  }

  const baseDraft = {
    symbol: item.symbol,
    sourceTitle: item.title,
    sourceDescription: item.description,
  };

  switch (item.kind) {
    case 'price_up': {
      const nextThreshold = roundThreshold((toNumber(quote?.change_percent) || 0) + 0.25, 0.5, 'up');
      return { ...baseDraft, condition: 'change_pct_above', threshold: Math.max(2, nextThreshold || 2) };
    }
    case 'price_down': {
      const nextThreshold = roundThreshold((toNumber(quote?.change_percent) || 0) - 0.25, 0.5, 'down');
      return { ...baseDraft, condition: 'change_pct_below', threshold: Math.min(-2, nextThreshold || -2) };
    }
    case 'range_expansion': {
      const nextThreshold = roundThreshold((getIntradayRangePercent(quote) || 0) + 0.25, 0.5, 'up');
      return { ...baseDraft, condition: 'intraday_range_above', threshold: Math.max(2, nextThreshold || 2) };
    }
    case 'volume_spike': {
      const ratio = getRelativeVolumeRatio(item.symbol, allQuotes);
      const nextThreshold = roundThreshold((ratio || 0) + 0.2, 0.5, 'up');
      return { ...baseDraft, condition: 'relative_volume_above', threshold: Math.max(2, nextThreshold || 2) };
    }
    case 'touch_high':
      return { ...baseDraft, condition: 'touch_high' };
    case 'touch_low':
      return { ...baseDraft, condition: 'touch_low' };
    default:
      return { ...baseDraft, condition: 'price_above', threshold: toNumber(quote?.price) };
  }
};

export const buildTradePlanDraftFromAnomaly = (item, quote) => {
  if (!item?.symbol) {
    return null;
  }

  const price = toNumber(quote?.price);
  const low = toNumber(quote?.low);
  const high = toNumber(quote?.high);
  const action = item.kind === 'price_down' || item.kind === 'touch_low' ? 'SELL' : 'BUY';
  const quantity = getSuggestedQuantity(item.symbol, price);

  const bullishStop = roundPrice(price !== null ? price * 0.985 : low);
  const bullishTake = roundPrice(price !== null ? price * 1.03 : high);
  const bearishStop = roundPrice(price !== null ? price * 1.015 : high);
  const bearishTake = roundPrice(price !== null ? price * 0.97 : low);

  return {
    symbol: item.symbol,
    action,
    quantity,
    limitPrice: price,
    suggestedEntry: roundPrice(price),
    stopLoss: action === 'BUY' ? bullishStop : bearishStop,
    takeProfit: action === 'BUY' ? bullishTake : bearishTake,
    sourceTitle: item.title,
    sourceDescription: item.description,
    note: action === 'BUY'
      ? '由异动雷达自动生成，适合先做纸面进场推演，再决定是否保留为市价或改成限价。'
      : '由异动雷达自动生成，适合先评估减仓、止盈或风险收缩方案。',
  };
};

export const buildAlertDraftFromTradePlan = (planDraft, target = 'entry') => {
  if (!planDraft?.symbol) {
    return null;
  }

  const action = planDraft.action || 'BUY';
  const entryPrice = toNumber(planDraft.suggestedEntry ?? planDraft.limitPrice);
  const stopLoss = toNumber(planDraft.stopLoss);
  const takeProfit = toNumber(planDraft.takeProfit);
  const sourceTitle = planDraft.sourceTitle || '交易计划';

  if (target === 'stop' && stopLoss !== null) {
    return {
      symbol: planDraft.symbol,
      condition: action === 'BUY' ? 'price_below' : 'price_above',
      threshold: stopLoss,
      sourceTitle: `${sourceTitle} · 止损提醒`,
      sourceDescription: `当 ${planDraft.symbol} 触及 ${roundPrice(stopLoss)} 时提醒你复核风险控制。`,
    };
  }

  if (target === 'take' && takeProfit !== null) {
    return {
      symbol: planDraft.symbol,
      condition: action === 'BUY' ? 'price_above' : 'price_below',
      threshold: takeProfit,
      sourceTitle: `${sourceTitle} · 止盈提醒`,
      sourceDescription: `当 ${planDraft.symbol} 触及 ${roundPrice(takeProfit)} 时提醒你评估止盈或继续持有。`,
    };
  }

  return {
    symbol: planDraft.symbol,
    condition: action === 'BUY' ? 'price_above' : 'price_below',
    threshold: entryPrice,
    sourceTitle: `${sourceTitle} · 入场提醒`,
    sourceDescription: `当 ${planDraft.symbol} 到达计划入场位 ${roundPrice(entryPrice)} 时提醒你确认执行。`,
  };
};
