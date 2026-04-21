import { STOCK_DATABASE } from '../constants/stocks';

export const QUOTE_FRESH_MS = 45 * 1000;
export const QUOTE_DELAYED_MS = 3 * 60 * 1000;
export const HOUR_MS = 60 * 60 * 1000;
export const CATEGORY_LABELS = {
  index: '指数',
  us: '美股',
  cn: 'A股',
  crypto: '加密货币',
  bond: '债券',
  future: '期货',
  option: '期权',
  other: '其他',
};
const SOURCE_KIND_LABELS = Object.freeze({
  alert: '提醒',
  dynamic: '动态',
  fallback: '降级补数',
  history: '历史',
  history_fallback: '历史补数',
  live: '实时',
  manual: '手动',
  plan: '计划',
  realtime: '实时',
  rest: 'REST',
  review: '复盘',
  snapshot: '快照',
  websocket: 'WebSocket',
  ws: 'WebSocket',
});
const SOURCE_PROVIDER_LABELS = Object.freeze({
  akshare: 'AkShare',
  eastmoney: '东方财富',
  fmp: 'FMP',
  polygon: 'Polygon',
  sina: '新浪',
  test_history: 'Test History',
  yahoo: 'Yahoo',
});

const formatSourceWord = (word) => {
  const trimmedWord = String(word || '').trim();

  if (!trimmedWord) {
    return '';
  }

  if (/^[A-Z0-9]+$/.test(trimmedWord)) {
    return trimmedWord;
  }

  if (trimmedWord.length <= 3) {
    return trimmedWord.toUpperCase();
  }

  return `${trimmedWord.charAt(0).toUpperCase()}${trimmedWord.slice(1)}`;
};

const formatSourceToken = (token, labels = SOURCE_PROVIDER_LABELS) => {
  const trimmedToken = String(token || '').trim();

  if (!trimmedToken) {
    return '';
  }

  const normalizedToken = trimmedToken.toLowerCase();
  if (labels[normalizedToken]) {
    return labels[normalizedToken];
  }

  return trimmedToken
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map(formatSourceWord)
    .join(' ');
};

export const hasNumericValue = (value) => value !== undefined && value !== null && !Number.isNaN(Number(value));

export const formatRelativeAge = (ageMs, options = {}) => {
  const { prefix = '', suffix = '' } = options;
  const safeAge = Math.max(0, ageMs);

  if (safeAge <= QUOTE_FRESH_MS) {
    return `${prefix}刚刚更新${suffix}`;
  }

  if (safeAge < HOUR_MS) {
    const seconds = Math.max(1, Math.floor(safeAge / 1000));
    if (seconds < 60) {
      return `${prefix}${seconds} 秒前${suffix}`;
    }

    return `${prefix}${Math.max(1, Math.floor(seconds / 60))} 分钟前${suffix}`;
  }

  return `${prefix}${Math.max(1, Math.floor(safeAge / HOUR_MS))} 小时前${suffix}`;
};

export const inferSymbolCategory = (symbol) => {
  const type = STOCK_DATABASE[symbol]?.type;
  if (type) {
    return type;
  }

  if (/^\d{6}\.(SS|SZ|BJ)$/i.test(symbol)) {
    return 'cn';
  }

  if (/^-?[A-Z0-9]+-USD$/i.test(symbol)) {
    return 'crypto';
  }

  if (/=F$/i.test(symbol)) {
    return 'future';
  }

  if (symbol.startsWith('^')) {
    return /^(?:\^TNX|\^TYX|\^FVX|\^IRX)$/i.test(symbol) ? 'bond' : 'index';
  }

  return 'us';
};

export const getCategoryLabel = (category) => CATEGORY_LABELS[category] || CATEGORY_LABELS.other;

export const getRealtimeQuoteSourceMeta = (source) => {
  const rawSource = typeof source === 'string' ? source.trim() : '';

  if (!rawSource) {
    return {
      label: '--',
      detail: '',
      title: '--',
    };
  }

  const separatorIndex = rawSource.indexOf(':');
  const kindToken = separatorIndex >= 0 ? rawSource.slice(0, separatorIndex) : rawSource;
  const providerToken = separatorIndex >= 0 ? rawSource.slice(separatorIndex + 1) : '';
  const label = formatSourceToken(kindToken, SOURCE_KIND_LABELS);
  const detail = providerToken ? formatSourceToken(providerToken, SOURCE_PROVIDER_LABELS) : '';

  return {
    label: label || rawSource,
    detail: detail && detail !== label ? detail : '',
    title: rawSource,
  };
};

export const formatPrice = (price, fallback = '--') => {
  if (!hasNumericValue(price)) return fallback;
  return typeof price === 'number' ? price.toFixed(2) : parseFloat(price).toFixed(2);
};

export const formatPercent = (percent, fallback = '--') => {
  if (!hasNumericValue(percent)) return fallback;
  return typeof percent === 'number' ? `${percent.toFixed(2)}%` : `${parseFloat(percent).toFixed(2)}%`;
};

export const formatVolume = (volume, fallback = '--') => {
  if (volume === undefined || volume === null || Number.isNaN(Number(volume))) {
    return fallback;
  }

  if (volume >= 1000000) {
    return `${(volume / 1000000).toFixed(1)}M`;
  }
  if (volume >= 1000) {
    return `${(volume / 1000).toFixed(1)}K`;
  }
  return volume.toString();
};

export const buildMiniTrendSeries = (quote) => {
  const series = [
    Number(quote?.previous_close),
    Number(quote?.open),
    Number(quote?.low),
    Number(quote?.price),
    Number(quote?.high),
  ].filter((value) => Number.isFinite(value) && value > 0);

  if (series.length >= 3) {
    return series;
  }

  if (Number.isFinite(Number(quote?.price)) && Number.isFinite(Number(quote?.change))) {
    const currentPrice = Number(quote.price);
    const change = Number(quote.change);
    const previousPrice = currentPrice - change;
    return [
      previousPrice,
      previousPrice + change * 0.25,
      previousPrice + change * 0.6,
      currentPrice,
    ];
  }

  return [];
};

export const buildSparklinePoints = (series, width = 144, height = 44, padding = 4) => {
  if (!Array.isArray(series) || series.length < 2) {
    return null;
  }

  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;

  return series.map((value, index) => {
    const x = padding + (index * (width - padding * 2)) / (series.length - 1);
    const y = height - padding - (((value - min) / span) * (height - padding * 2));
    return `${x},${y}`;
  }).join(' ');
};
