import { inferSymbolCategory } from './realtimeFormatters';

const hasNumericValue = (value) => value !== null && value !== undefined && !Number.isNaN(Number(value));

const toNumber = (value) => (hasNumericValue(value) ? Number(value) : null);

export const ALERT_HIT_HISTORY_STORAGE_KEY = 'realtime-alert-hit-history';
export const MAX_ALERT_HIT_HISTORY = 80;
const ANOMALY_THRESHOLDS_BY_CATEGORY = {
  index: {
    priceMoveThreshold: 1.2,
    rangeThreshold: 2.2,
    volumeSpikeRatio: 1.8,
  },
  us: {
    priceMoveThreshold: 2,
    rangeThreshold: 3,
    volumeSpikeRatio: 2,
  },
  cn: {
    priceMoveThreshold: 2,
    rangeThreshold: 3,
    volumeSpikeRatio: 1.8,
  },
  crypto: {
    priceMoveThreshold: 5,
    rangeThreshold: 6.5,
    volumeSpikeRatio: 2.4,
  },
  bond: {
    priceMoveThreshold: 0.35,
    rangeThreshold: 0.8,
    volumeSpikeRatio: 1.6,
  },
  future: {
    priceMoveThreshold: 2.6,
    rangeThreshold: 4,
    volumeSpikeRatio: 2.1,
  },
  option: {
    priceMoveThreshold: 3.2,
    rangeThreshold: 4.5,
    volumeSpikeRatio: 2.2,
  },
  other: {
    priceMoveThreshold: 2,
    rangeThreshold: 3,
    volumeSpikeRatio: 2,
  },
};

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
    cooldownMinutes: hasNumericValue(alert.cooldownMinutes) ? Math.max(0, Number(alert.cooldownMinutes)) : 15,
  };
};

export const loadAlertHitHistory = () => {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const rawValue = window.localStorage.getItem(ALERT_HIT_HISTORY_STORAGE_KEY);
    if (!rawValue) {
      return [];
    }

    const parsedValue = JSON.parse(rawValue);
    return Array.isArray(parsedValue) ? parsedValue : [];
  } catch (error) {
    console.warn('Failed to load realtime alert hit history:', error);
    return [];
  }
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

export const buildAlertHitHistoryEntry = ({ alert, triggerValue, message, quote = null }) => {
  const normalizedAlert = normalizePriceAlert(alert);
  const triggerPrice = toNumber(quote?.price);

  return {
    id: `alert_hit_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    alertId: normalizedAlert.id || null,
    symbol: normalizedAlert.symbol || '--',
    condition: normalizedAlert.condition,
    conditionLabel: getAlertConditionLabel(normalizedAlert),
    threshold: normalizedAlert.threshold,
    triggerValue: toNumber(triggerValue),
    triggerPrice,
    triggerTime: new Date().toISOString(),
    message: message || `${normalizedAlert.symbol || '该标的'} 的提醒已触发`,
    sourceTitle: normalizedAlert.sourceTitle || null,
    priceSnapshot: triggerPrice,
    changePercentSnapshot: toNumber(quote?.change_percent),
    rangePercentSnapshot: getIntradayRangePercent(quote),
  };
};

export const summarizeAlertHitHistory = (history = [], symbols = null) => {
  const symbolSet = Array.isArray(symbols) && symbols.length > 0 ? new Set(symbols) : null;
  const filteredHistory = history.filter((entry) => (
    !symbolSet || symbolSet.has(entry?.symbol)
  ));
  const symbolCounts = new Map();
  const conditionCounts = new Map();

  filteredHistory.forEach((entry) => {
    if (entry?.symbol) {
      symbolCounts.set(entry.symbol, (symbolCounts.get(entry.symbol) || 0) + 1);
    }

    if (entry?.conditionLabel) {
      conditionCounts.set(entry.conditionLabel, (conditionCounts.get(entry.conditionLabel) || 0) + 1);
    }
  });

  const pickTop = (entries) => {
    const sorted = [...entries.entries()].sort((left, right) => right[1] - left[1]);
    if (!sorted.length) {
      return '--';
    }

    const [label, count] = sorted[0];
    return `${label} · ${count} 次`;
  };

  return {
    totalHits: filteredHistory.length,
    uniqueSymbols: new Set(filteredHistory.map((entry) => entry?.symbol).filter(Boolean)).size,
    topSymbol: pickTop(symbolCounts),
    topCondition: pickTop(conditionCounts),
    lastTriggeredAt: filteredHistory[0]?.triggerTime || null,
    recentHits: filteredHistory.slice(0, 5),
  };
};

export const evaluateAlertHitFollowThrough = (entry, quote = null, allQuotes = {}) => {
  const condition = entry?.condition || '';
  const currentPrice = toNumber(quote?.price);
  const currentChangePercent = toNumber(quote?.change_percent);
  const currentRangePercent = getIntradayRangePercent(quote);
  const currentRelativeVolume = entry?.symbol ? getRelativeVolumeRatio(entry.symbol, allQuotes) : null;
  const triggerPrice = toNumber(entry?.triggerPrice ?? entry?.priceSnapshot);
  const threshold = toNumber(entry?.threshold);

  const buildPending = (description = '当前提醒已经命中，但还缺少足够信号判断后效强弱。') => ({
    state: 'pending',
    label: '等待后效判断',
    description,
  });

  if (!quote) {
    return buildPending('当前还没有可用于判断提醒后效的最新行情。');
  }

  if (threshold !== null) {
    if (condition === 'price_above') {
      if (currentPrice === null) {
        return buildPending('当前还没有可用于判断价格提醒后效的最新价格。');
      }
      return currentPrice >= threshold
        ? {
            state: 'continued',
            label: '命中后仍在阈值上方',
            description: `当前价格仍高于提醒阈值 ${threshold.toFixed(2)}。`,
          }
        : {
            state: 'reversed',
            label: '命中后跌回阈值下方',
            description: `当前价格已经回到提醒阈值 ${threshold.toFixed(2)} 下方。`,
          };
    }

    if (condition === 'price_below') {
      if (currentPrice === null) {
        return buildPending('当前还没有可用于判断价格提醒后效的最新价格。');
      }
      return currentPrice <= threshold
        ? {
            state: 'continued',
            label: '命中后仍在阈值下方',
            description: `当前价格仍低于提醒阈值 ${threshold.toFixed(2)}。`,
          }
        : {
            state: 'reversed',
            label: '命中后回到阈值上方',
            description: `当前价格已经回到提醒阈值 ${threshold.toFixed(2)} 上方。`,
          };
    }

    if (condition === 'change_pct_above') {
      if (currentChangePercent === null) {
        return buildPending('当前还没有可用于判断涨跌幅提醒后效的最新涨跌幅。');
      }
      return currentChangePercent >= threshold
        ? {
            state: 'continued',
            label: '命中后涨幅仍然成立',
            description: `当前涨跌幅仍高于提醒阈值 ${threshold.toFixed(2)}%。`,
          }
        : {
            state: 'reversed',
            label: '命中后涨幅回落',
            description: `当前涨跌幅已回到提醒阈值 ${threshold.toFixed(2)}% 下方。`,
          };
    }

    if (condition === 'change_pct_below') {
      if (currentChangePercent === null) {
        return buildPending('当前还没有可用于判断跌幅提醒后效的最新涨跌幅。');
      }
      return currentChangePercent <= threshold
        ? {
            state: 'continued',
            label: '命中后跌幅仍然成立',
            description: `当前涨跌幅仍低于提醒阈值 ${threshold.toFixed(2)}%。`,
          }
        : {
            state: 'reversed',
            label: '命中后跌幅收窄',
            description: `当前涨跌幅已回到提醒阈值 ${threshold.toFixed(2)}% 上方。`,
          };
    }

    if (condition === 'intraday_range_above') {
      if (currentRangePercent === null) {
        return buildPending('当前还没有足够的高低点数据判断振幅提醒后效。');
      }
      return currentRangePercent >= threshold
        ? {
            state: 'continued',
            label: '命中后振幅仍在放大',
            description: `当前日内振幅仍高于提醒阈值 ${threshold.toFixed(2)}%。`,
          }
        : {
            state: 'reversed',
            label: '命中后振幅回落',
            description: `当前日内振幅已回到提醒阈值 ${threshold.toFixed(2)}% 下方。`,
          };
    }

    if (condition === 'relative_volume_above') {
      if (currentRelativeVolume === null) {
        return buildPending('当前还没有足够的分组成交量上下文判断放量提醒后效。');
      }
      return currentRelativeVolume >= threshold
        ? {
            state: 'continued',
            label: '命中后仍在相对放量',
            description: `当前相对成交量仍高于提醒阈值 ${threshold.toFixed(2)}x。`,
          }
        : {
            state: 'reversed',
            label: '命中后放量回落',
            description: `当前相对成交量已回到提醒阈值 ${threshold.toFixed(2)}x 下方。`,
          };
    }
  }

  if (condition === 'touch_high') {
    if (isNearDayExtreme(quote, 'high', entry?.tolerancePercent || 0.1)) {
      return {
        state: 'continued',
        label: '命中后仍贴近日高',
        description: '当前价格仍然停留在日内高点附近。',
      };
    }
    if (currentPrice === null) {
      return buildPending('当前还没有可用于判断日高提醒后效的最新价格。');
    }
    return {
      state: 'reversed',
      label: '命中后离开日高区域',
      description: '当前价格已经离开日内高点附近。',
    };
  }

  if (condition === 'touch_low') {
    if (isNearDayExtreme(quote, 'low', entry?.tolerancePercent || 0.1)) {
      return {
        state: 'continued',
        label: '命中后仍贴近日低',
        description: '当前价格仍然停留在日内低点附近。',
      };
    }
    if (currentPrice === null) {
      return buildPending('当前还没有可用于判断日低提醒后效的最新价格。');
    }
    return {
      state: 'reversed',
      label: '命中后离开日低区域',
      description: '当前价格已经离开日内低点附近。',
    };
  }

  if (triggerPrice !== null && triggerPrice !== 0 && currentPrice !== null) {
    const movePercent = ((currentPrice - triggerPrice) / triggerPrice) * 100;
    const absoluteMove = Math.abs(movePercent).toFixed(2);
    const isBullish = ['price_above', 'change_pct_above', 'touch_high', 'intraday_range_above', 'relative_volume_above'].includes(condition);
    const isBearish = ['price_below', 'change_pct_below', 'touch_low'].includes(condition);

    if (isBullish) {
      return movePercent >= 0
        ? {
            state: 'continued',
            label: '命中后继续走强',
            description: `相对命中时价格继续抬升 ${absoluteMove}%。`,
          }
        : {
            state: 'reversed',
            label: '命中后出现回吐',
            description: `相对命中时价格回落 ${absoluteMove}%。`,
          };
    }

    if (isBearish) {
      return movePercent <= 0
        ? {
            state: 'continued',
            label: '命中后继续走弱',
            description: `相对命中时价格继续回落 ${absoluteMove}%。`,
          }
        : {
            state: 'reversed',
            label: '命中后出现反弹',
            description: `相对命中时价格反弹 ${absoluteMove}%。`,
          };
    }
  }

  return buildPending();
};

export const summarizeAlertHitFollowThrough = (history = [], quotes = {}, symbols = null) => {
  const symbolSet = Array.isArray(symbols) && symbols.length > 0 ? new Set(symbols) : null;
  const summary = {
    continued: 0,
    reversed: 0,
    pending: 0,
  };

  history.forEach((entry) => {
    if (!entry?.symbol || (symbolSet && !symbolSet.has(entry.symbol))) {
      return;
    }

    const result = evaluateAlertHitFollowThrough(entry, quotes[entry.symbol], quotes);
    if (result.state === 'continued') {
      summary.continued += 1;
    } else if (result.state === 'reversed') {
      summary.reversed += 1;
    } else {
      summary.pending += 1;
    }
  });

  return summary;
};

export const buildRealtimeActionPosture = ({
  freshnessSummary = {},
  alertHitSummary = {},
  alertFollowThrough = {},
  anomalyCount = 0,
  symbolCount = 0,
  spotlightSymbol = '',
} = {}) => {
  const safeSymbolCount = Math.max(Number(symbolCount || 0), 1);
  const delayedCount = Number(freshnessSummary?.delayed || 0);
  const agingCount = Number(freshnessSummary?.aging || 0);
  const totalHits = Number(alertHitSummary?.totalHits || 0);
  const continuedCount = Number(alertFollowThrough?.continued || 0);
  const reversedCount = Number(alertFollowThrough?.reversed || 0);
  const pendingCount = Number(alertFollowThrough?.pending || 0);

  if (delayedCount / safeSymbolCount >= 0.35 || delayedCount >= 4) {
    return {
      level: 'warning',
      label: 'stale_feed',
      title: '先确认链路与行情时效',
      posture: '先确认链路质量',
      actionHint: '当前应先刷新或检查链路，再决定这些异动和提醒是否仍然有效。',
      reason: `当前分组有 ${delayedCount}/${safeSymbolCount} 个标的已进入延迟状态，继续放大解读之前更适合先确认数据时效。`,
    };
  }

  if (totalHits > 0 && continuedCount >= Math.max(1, reversedCount)) {
    return {
      level: 'success',
      label: 'follow_through',
      title: '优先跟进仍在延续的提醒',
      posture: '先跟进持续性提醒',
      actionHint: '当前更适合先看命中后仍在延续的提醒，再决定是否保存复盘快照或拆成交易计划。',
      reason: `当前分组提醒命中 ${totalHits} 次，其中 ${continuedCount} 次仍在延续，反转 ${reversedCount} 次，等待判断 ${pendingCount} 次。`,
    };
  }

  if (anomalyCount > 0) {
    return {
      level: 'info',
      label: 'anomaly_watch',
      title: spotlightSymbol ? `优先处理 ${spotlightSymbol} 及新增异动` : '优先处理新增异动',
      posture: '先看新增异动',
      actionHint: '当前可先围绕焦点标的和新增异动做观察，再决定是否创建提醒或交易计划。',
      reason: `当前分组还有 ${anomalyCount} 条异动待处理${agingCount > 0 ? `，另有 ${agingCount} 个标的开始变旧。` : '。'}`,
    };
  }

  return {
    level: 'default',
    label: 'observe',
    title: '当前更适合继续观察当前分组',
    posture: '继续观察',
    actionHint: '当前没有明显需要立刻升级处理的异动，更适合维持观察节奏并等待下一次信号刷新。',
    reason: `当前分组共 ${safeSymbolCount} 个标的，延迟 ${delayedCount} 个，提醒命中 ${totalHits} 次。`,
  };
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

const getMeanStd = (values = []) => {
  const clean = values.filter((value) => hasNumericValue(value)).map(Number);
  if (clean.length < 2) {
    return { mean: null, std: null };
  }
  const mean = clean.reduce((sum, value) => sum + value, 0) / clean.length;
  const variance = clean.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / clean.length;
  return { mean, std: Math.sqrt(variance) };
};

export const getAnomalySeverityMeta = (kind, severity) => {
  const numericSeverity = hasNumericValue(severity) ? Number(severity) : 0;

  if (kind === 'volume_spike') {
    if (numericSeverity >= 4) {
      return { level: 'critical', label: '极强', color: '#b91c1c', background: 'rgba(239, 68, 68, 0.16)' };
    }
    if (numericSeverity >= 2.5) {
      return { level: 'high', label: '高优先级', color: '#c2410c', background: 'rgba(249, 115, 22, 0.16)' };
    }
    return { level: 'medium', label: '关注', color: '#b45309', background: 'rgba(245, 158, 11, 0.16)' };
  }

  if (kind === 'range_expansion') {
    if (numericSeverity >= 6) {
      return { level: 'critical', label: '极强', color: '#b91c1c', background: 'rgba(239, 68, 68, 0.16)' };
    }
    if (numericSeverity >= 4) {
      return { level: 'high', label: '高优先级', color: '#c2410c', background: 'rgba(249, 115, 22, 0.16)' };
    }
    return { level: 'medium', label: '关注', color: '#b45309', background: 'rgba(245, 158, 11, 0.16)' };
  }

  if (kind === 'touch_high' || kind === 'touch_low') {
    if (numericSeverity >= 3) {
      return { level: 'high', label: '高优先级', color: '#c2410c', background: 'rgba(249, 115, 22, 0.16)' };
    }
    return { level: 'medium', label: '关注', color: '#b45309', background: 'rgba(245, 158, 11, 0.16)' };
  }

  if (numericSeverity >= 5) {
    return { level: 'critical', label: '极强', color: '#b91c1c', background: 'rgba(239, 68, 68, 0.16)' };
  }
  if (numericSeverity >= 3) {
    return { level: 'high', label: '高优先级', color: '#c2410c', background: 'rgba(249, 115, 22, 0.16)' };
  }
  return { level: 'medium', label: '关注', color: '#b45309', background: 'rgba(245, 158, 11, 0.16)' };
};

export const buildRealtimeAnomalyFeed = (symbols = [], quotes = {}, options = {}) => {
  const {
    limit = 6,
    priceMoveThreshold = 2,
    rangeThreshold = 3,
    volumeSpikeRatio = 2,
    zScoreThreshold = 2.2,
    thresholdsByCategory = ANOMALY_THRESHOLDS_BY_CATEGORY,
  } = options;

  const normalizedSymbols = symbols.filter(Boolean);
  const volumeBaseline = getMedian(
    normalizedSymbols
      .map((symbol) => toNumber(quotes[symbol]?.volume))
      .filter((value) => value !== null && value > 0)
  );
  const { mean: changeMean, std: changeStd } = getMeanStd(
    normalizedSymbols
      .map((symbol) => toNumber(quotes[symbol]?.change_percent))
      .filter((value) => value !== null)
  );

  const events = [];
  normalizedSymbols.forEach((symbol) => {
    const quote = quotes[symbol];
    if (!quote) {
      return;
    }

    const category = inferSymbolCategory(symbol);
    const categoryThresholds = thresholdsByCategory[category] || thresholdsByCategory.other || {};
    const effectivePriceMoveThreshold = categoryThresholds.priceMoveThreshold ?? priceMoveThreshold;
    const effectiveRangeThreshold = categoryThresholds.rangeThreshold ?? rangeThreshold;
    const effectiveVolumeSpikeRatio = categoryThresholds.volumeSpikeRatio ?? volumeSpikeRatio;

    const price = toNumber(quote.price);
    const changePercent = toNumber(quote.change_percent);
    const volume = toNumber(quote.volume);
    const rangePercent = getIntradayRangePercent(quote);
    const timestamp = quote._clientReceivedAt || quote.timestamp || Date.now();
    const changeZScore = changeStd && changePercent !== null
      ? (changePercent - changeMean) / changeStd
      : null;

    if (changePercent !== null && changePercent >= effectivePriceMoveThreshold) {
      events.push({
        id: `${symbol}-price-up`,
        symbol,
        kind: 'price_up',
        severity: Math.abs(changePercent),
        title: '强势拉升',
        description: `${symbol} 当前涨幅 ${changePercent.toFixed(2)}%，处于盘中强势区间。`,
        timestamp,
        priceSnapshot: price,
        changePercentSnapshot: changePercent,
      });
    }

    if (changePercent !== null && changePercent <= -effectivePriceMoveThreshold) {
      events.push({
        id: `${symbol}-price-down`,
        symbol,
        kind: 'price_down',
        severity: Math.abs(changePercent),
        title: '快速回落',
        description: `${symbol} 当前跌幅 ${Math.abs(changePercent).toFixed(2)}%，需留意盘中回撤。`,
        timestamp,
        priceSnapshot: price,
        changePercentSnapshot: changePercent,
      });
    }

    if (changeZScore !== null && Math.abs(changeZScore) >= zScoreThreshold) {
      events.push({
        id: `${symbol}-zscore`,
        symbol,
        kind: 'statistical_zscore',
        severity: Math.abs(changeZScore),
        title: '统计异动',
        description: `${symbol} 横截面涨跌 Z-Score ${changeZScore.toFixed(2)}，显著偏离当前分组均值。`,
        timestamp,
        priceSnapshot: price,
        changePercentSnapshot: changePercent,
        zScore: changeZScore,
      });
    }

    if (changePercent !== null && rangePercent !== null) {
      const cusumProxy = Math.abs(changePercent) + Math.max(0, rangePercent - effectiveRangeThreshold) * 0.5;
      if (cusumProxy >= effectivePriceMoveThreshold * 1.8) {
        events.push({
          id: `${symbol}-cusum`,
          symbol,
          kind: 'cusum_shift',
          severity: cusumProxy,
          title: 'CUSUM 趋势漂移',
          description: `${symbol} 涨跌幅与振幅组合信号显示盘中状态发生漂移，CUSUM proxy ${cusumProxy.toFixed(2)}。`,
          timestamp,
          priceSnapshot: price,
          changePercentSnapshot: changePercent,
          rangePercentSnapshot: rangePercent,
          cusumProxy,
        });
      }
    }

    if (rangePercent !== null && rangePercent >= effectiveRangeThreshold) {
      events.push({
        id: `${symbol}-range`,
        symbol,
        kind: 'range_expansion',
        severity: rangePercent,
        title: '振幅扩张',
        description: `${symbol} 日内振幅 ${rangePercent.toFixed(2)}%，波动显著放大。`,
        timestamp,
        priceSnapshot: price,
        rangePercentSnapshot: rangePercent,
      });
    }

    if (volumeBaseline && volume !== null && volume >= volumeBaseline * effectiveVolumeSpikeRatio) {
      events.push({
        id: `${symbol}-volume`,
        symbol,
        kind: 'volume_spike',
        severity: volume / volumeBaseline,
        title: '放量异动',
        description: `${symbol} 当前成交量约为分组中位数的 ${(volume / volumeBaseline).toFixed(1)} 倍。`,
        timestamp,
        priceSnapshot: price,
        volumeSnapshot: volume,
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
        priceSnapshot: price,
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
        priceSnapshot: price,
      });
    }
  });

  // Deduplicate by id — keep the highest-severity entry for each id
  const deduped = new Map();
  events.forEach((event) => {
    const existing = deduped.get(event.id);
    if (!existing || event.severity > existing.severity) {
      deduped.set(event.id, event);
    }
  });

  return Array.from(deduped.values())
    .sort((left, right) => {
      if (right.severity !== left.severity) {
        return right.severity - left.severity;
      }
      return new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime();
    })
    .map((event) => ({
      ...event,
      ...getAnomalySeverityMeta(event.kind, event.severity),
    }))
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
