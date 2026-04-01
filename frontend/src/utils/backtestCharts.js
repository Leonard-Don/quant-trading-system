import dayjs from './dayjs';

import { calculateBollinger, calculateEMA, calculateSMA } from './indicators';

const TIME_RANGE_DAYS = {
  '5d': 5,
  '1mo': 30,
  '3mo': 90,
  '6mo': 180,
  '1y': 365,
  max: Infinity,
  '1W': 7,
  '1M': 30,
};

const toNumber = (value, fallback = null) => {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }

  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
};

const parsePointDate = (point, fallbackIndex = 0) => {
  const rawValue = point?.date ?? point?.Date ?? point?.index ?? point?.timestamp;
  if (!rawValue || (typeof rawValue === 'string' && rawValue.startsWith('point-'))) {
    return null;
  }

  const parsed = rawValue ? dayjs(rawValue) : dayjs('');

  if (parsed.isValid()) {
    return parsed;
  }

  return null;
};

export const getTimeRangeDays = (timeRange = 'max') => TIME_RANGE_DAYS[timeRange] ?? Infinity;

export const buildPerformanceChartData = (data = [], timeRange = 'max') => {
  if (!Array.isArray(data) || data.length === 0) {
    return [];
  }

  const normalized = data
    .map((item, index) => {
      const parsedDate = parsePointDate(item, index);
      const total = toNumber(item.total ?? item.portfolio_value, 0);
      const price = toNumber(item.price, null);
      const dateValue = parsedDate ? parsedDate.valueOf() : index;

      return {
        rawDate: item.date ?? item.Date ?? item.index ?? item.timestamp,
        dateValue,
        dateLabel: parsedDate ? parsedDate.format('MM/DD') : `#${index + 1}`,
        dateLongLabel: parsedDate ? parsedDate.format('YYYY-MM-DD') : `第 ${index + 1} 个交易点`,
        portfolio_value: total,
        total,
        price,
        signal: toNumber(item.signal, 0),
        returns: toNumber(item.returns, 0) * 100,
        cash: toNumber(item.cash, 0),
        holdings: toNumber(item.holdings, 0),
        position: toNumber(item.position, 0),
      };
    })
    .sort((left, right) => left.dateValue - right.dateValue);

  const rangeDays = getTimeRangeDays(timeRange);
  const latestDateValue = normalized[normalized.length - 1]?.dateValue ?? null;
  const filtered = latestDateValue && Number.isFinite(rangeDays) && rangeDays !== Infinity
    ? normalized.filter((item) => item.dateValue >= latestDateValue - rangeDays * 24 * 60 * 60 * 1000)
    : normalized;

  const prices = filtered.map((item) => item.price ?? item.portfolio_value);
  const sma20 = calculateSMA(prices, 20);
  const sma50 = calculateSMA(prices, 50);
  const ema12 = calculateEMA(prices, 12);
  const ema26 = calculateEMA(prices, 26);
  const bollinger = calculateBollinger(prices, 20);

  return filtered.map((item, index) => ({
    ...item,
    index,
    sma20: sma20[index],
    sma50: sma50[index],
    ema12: ema12[index],
    ema26: ema26[index],
    bbUpper: bollinger.upper[index],
    bbMiddle: bollinger.middle[index],
    bbLower: bollinger.lower[index],
    portfolioChange: filtered[0]?.portfolio_value
      ? ((item.portfolio_value / filtered[0].portfolio_value) - 1) * 100
      : 0,
  }));
};

export const buildDrawdownSeries = (data = []) => {
  if (!Array.isArray(data) || data.length === 0) {
    return { series: [], stats: null };
  }

  let runningMax = null;
  let underwaterDays = 0;
  let longestUnderwaterStreak = 0;
  let currentStreak = 0;

  const series = data
    .map((item, index) => {
      const parsedDate = parsePointDate(item, index);
      const total = toNumber(item.total ?? item.portfolio_value, null);
      if (total === null || total <= 0) {
        return null;
      }

      if (runningMax === null || total > runningMax) {
        runningMax = total;
      }

      const drawdown = runningMax > 0 ? ((total - runningMax) / runningMax) * 100 : 0;
      if (drawdown < 0) {
        underwaterDays += 1;
        currentStreak += 1;
        longestUnderwaterStreak = Math.max(longestUnderwaterStreak, currentStreak);
      } else {
        currentStreak = 0;
      }

      return {
        dateValue: parsedDate ? parsedDate.valueOf() : index,
        dateLabel: parsedDate ? parsedDate.format('MM/DD') : `#${index + 1}`,
        dateLongLabel: parsedDate ? parsedDate.format('YYYY-MM-DD') : `第 ${index + 1} 个交易点`,
        total,
        drawdown,
      };
    })
    .filter(Boolean);

  if (series.length === 0) {
    return { series: [], stats: null };
  }

  const drawdowns = series.map((item) => item.drawdown);
  const currentDrawdown = drawdowns[drawdowns.length - 1];

  return {
    series,
    stats: {
      maxDrawdown: Math.min(...drawdowns),
      currentDrawdown,
      underwaterDays,
      longestUnderwaterStreak,
    },
  };
};

export const deriveReturnSeries = (data = []) => {
  if (!Array.isArray(data) || data.length === 0) {
    return [];
  }

  const returns = [];
  let previousTotal = null;

  data.forEach((item) => {
    const explicitReturn = toNumber(item.returns, null);
    if (explicitReturn !== null && Number.isFinite(explicitReturn)) {
      returns.push(explicitReturn);
      previousTotal = toNumber(item.total ?? item.portfolio_value, previousTotal);
      return;
    }

    const total = toNumber(item.total ?? item.portfolio_value, null);
    if (previousTotal !== null && total !== null && previousTotal > 0) {
      returns.push((total - previousTotal) / previousTotal);
    }
    previousTotal = total ?? previousTotal;
  });

  return returns.filter((value) => Number.isFinite(value));
};

export const buildReturnDistribution = (data = []) => {
  const returns = deriveReturnSeries(data).map((value) => value * 100);
  if (returns.length === 0) {
    return { bins: [], stats: null };
  }

  const min = Math.min(...returns);
  const max = Math.max(...returns);
  const binCount = Math.max(8, Math.min(18, Math.round(Math.sqrt(returns.length))));
  const spread = max - min || 1;
  const binSize = spread / binCount;

  const bins = Array.from({ length: binCount }, (_, index) => {
    const rangeStart = min + index * binSize;
    const rangeEnd = index === binCount - 1 ? max : rangeStart + binSize;
    const center = rangeStart + (rangeEnd - rangeStart) / 2;

    return {
      key: `${rangeStart.toFixed(2)}-${rangeEnd.toFixed(2)}`,
      rangeStart,
      rangeEnd,
      center,
      count: 0,
      percentage: 0,
      label: `${rangeStart.toFixed(1)}%`,
    };
  });

  returns.forEach((value) => {
    const rawIndex = Math.floor((value - min) / (binSize || 1));
    const binIndex = Math.max(0, Math.min(binCount - 1, rawIndex));
    bins[binIndex].count += 1;
  });

  bins.forEach((bin) => {
    bin.percentage = (bin.count / returns.length) * 100;
  });

  const sorted = [...returns].sort((left, right) => left - right);
  const midpoint = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 0
    ? (sorted[midpoint - 1] + sorted[midpoint]) / 2
    : sorted[midpoint];

  return {
    bins,
    stats: {
      positiveDays: returns.filter((value) => value > 0).length,
      negativeDays: returns.filter((value) => value < 0).length,
      flatDays: returns.filter((value) => value === 0).length,
      avgReturn: returns.reduce((sum, value) => sum + value, 0) / returns.length,
      medianReturn: median,
    },
  };
};

const clampScore = (value) => Math.max(0, Math.min(100, value));

export const buildRiskRadarData = (metrics = {}) => {
  if (!metrics || typeof metrics !== 'object') {
    return [];
  }

  const totalReturn = toNumber(metrics.total_return, 0);
  const sharpeRatio = toNumber(metrics.sharpe_ratio, 0);
  const winRate = toNumber(metrics.win_rate, 0);
  const maxDrawdown = Math.abs(toNumber(metrics.max_drawdown, 0));
  const volatility = toNumber(metrics.volatility, 0);
  const profitFactor = toNumber(metrics.profit_factor, 0);

  return [
    {
      metric: '收益效率',
      score: clampScore(50 + totalReturn * 140),
      rawValue: totalReturn * 100,
      suffix: '%',
    },
    {
      metric: '风险调整',
      score: clampScore(50 + sharpeRatio * 18),
      rawValue: sharpeRatio,
      suffix: '',
    },
    {
      metric: '胜率',
      score: clampScore(winRate * 100),
      rawValue: winRate * 100,
      suffix: '%',
    },
    {
      metric: '回撤控制',
      score: clampScore(100 - maxDrawdown * 260),
      rawValue: maxDrawdown * 100,
      suffix: '%',
    },
    {
      metric: '波动稳定',
      score: clampScore(100 - volatility * 180),
      rawValue: volatility * 100,
      suffix: '%',
    },
    {
      metric: '盈亏结构',
      score: clampScore(profitFactor * 28),
      rawValue: profitFactor,
      suffix: '',
    },
  ];
};

export const formatChartCurrency = (value) => {
  const numericValue = toNumber(value, 0) ?? 0;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: numericValue >= 1000 ? 0 : 2,
  }).format(numericValue);
};

export const formatChartPercent = (value, digits = 1) => `${toNumber(value, 0).toFixed(digits)}%`;
