import axios from 'axios';

const DEFAULT_LOCAL_API_BASE_URL = 'http://127.0.0.1:8000';
const API_BASE_URL = process.env.REACT_APP_API_URL || DEFAULT_LOCAL_API_BASE_URL;
const API_TIMEOUT = parseInt(process.env.REACT_APP_API_TIMEOUT) || 300000;
const API_AUTH_TOKEN_KEY = 'quant_research_auth_token';
const API_REFRESH_TOKEN_KEY = 'quant_research_refresh_token';
const LEGACY_API_AUTH_TOKEN_KEY = 'quant_lab_auth_token';
const LEGACY_API_REFRESH_TOKEN_KEY = 'quant_lab_refresh_token';

let authTokenCache = '';
let refreshTokenCache = '';
let refreshInFlight = null;

const readStoredToken = (storageKey, legacyStorageKey) => {
  if (typeof window === 'undefined') {
    return '';
  }
  const currentToken = window.localStorage.getItem(storageKey) || '';
  if (currentToken) {
    return currentToken;
  }
  const legacyToken = window.localStorage.getItem(legacyStorageKey) || '';
  if (legacyToken) {
    window.localStorage.setItem(storageKey, legacyToken);
    window.localStorage.removeItem(legacyStorageKey);
  }
  return legacyToken;
};

const removeStoredToken = (...storageKeys) => {
  if (typeof window !== 'undefined') {
    storageKeys.forEach((storageKey) => window.localStorage.removeItem(storageKey));
  }
};

if (typeof window !== 'undefined') {
  authTokenCache = readStoredToken(API_AUTH_TOKEN_KEY, LEGACY_API_AUTH_TOKEN_KEY);
  refreshTokenCache = readStoredToken(API_REFRESH_TOKEN_KEY, LEGACY_API_REFRESH_TOKEN_KEY);
}

export const getApiAuthToken = () => authTokenCache;
export const getApiRefreshToken = () => refreshTokenCache;

export const setApiAuthToken = (token) => {
  authTokenCache = token || '';
  if (typeof window !== 'undefined') {
    if (authTokenCache) {
      window.localStorage.setItem(API_AUTH_TOKEN_KEY, authTokenCache);
      window.localStorage.removeItem(LEGACY_API_AUTH_TOKEN_KEY);
    } else {
      removeStoredToken(API_AUTH_TOKEN_KEY, LEGACY_API_AUTH_TOKEN_KEY);
    }
  }
};

export const setApiRefreshToken = (token) => {
  refreshTokenCache = token || '';
  if (typeof window !== 'undefined') {
    if (refreshTokenCache) {
      window.localStorage.setItem(API_REFRESH_TOKEN_KEY, refreshTokenCache);
      window.localStorage.removeItem(LEGACY_API_REFRESH_TOKEN_KEY);
    } else {
      removeStoredToken(API_REFRESH_TOKEN_KEY, LEGACY_API_REFRESH_TOKEN_KEY);
    }
  }
};

const parseTimeout = (value, fallback) => {
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};
export const API_TIMEOUT_PROFILES = {
  default: API_TIMEOUT,
  analysis: parseTimeout(process.env.REACT_APP_API_TIMEOUT_ANALYSIS, 120000),
  standard: parseTimeout(process.env.REACT_APP_API_TIMEOUT_STANDARD, 30000),
  dashboard: parseTimeout(process.env.REACT_APP_API_TIMEOUT_DASHBOARD, 45000),
};
export const withTimeoutProfile = (profile = 'default', config = {}) => ({
  ...config,
  timeout: config.timeout ?? API_TIMEOUT_PROFILES[profile] ?? API_TIMEOUT_PROFILES.default,
});
const isCanceledRequest = (error) => (
  axios.isCancel(error)
  || error?.code === 'ERR_CANCELED'
  || error?.name === 'CanceledError'
  || error?.message === 'canceled'
);

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
});

const refreshAccessTokenIfNeeded = async () => {
  if (!refreshTokenCache) {
    throw new Error('No refresh token available');
  }
  if (!refreshInFlight) {
    refreshInFlight = api.post(
      '/infrastructure/auth/refresh',
      {
        refresh_token: refreshTokenCache,
      },
      withTimeoutProfile('standard', { headers: { 'X-Skip-Auth-Refresh': '1' } }),
    )
      .then((response) => {
        const payload = response.data || {};
        if (payload.access_token) {
          setApiAuthToken(payload.access_token);
        }
        if (payload.refresh_token) {
          setApiRefreshToken(payload.refresh_token);
        }
        return payload;
      })
      .catch((error) => {
        setApiAuthToken('');
        setApiRefreshToken('');
        throw error;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
};

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    if (authTokenCache && !config.headers?.Authorization) {
      config.headers = {
        ...config.headers,
        Authorization: `Bearer ${authTokenCache}`,
      };
    }
    if (process.env.NODE_ENV === 'development') {
      console.log('API Request:', config.method?.toUpperCase(), config.url);
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器 - 增强错误处理
api.interceptors.response.use(
  (response) => {
    if (process.env.NODE_ENV === 'development') {
      console.log('API Response:', response.status, response.config.url);
    }
    return response;
  },
  (error) => {
    if (isCanceledRequest(error)) {
      error.userMessage = '请求已取消';
      error.errorCode = 'REQUEST_CANCELED';
      return Promise.reject(error);
    }

    const originalRequest = error.config || {};
    const canRefresh = (
      error.response?.status === 401
      && refreshTokenCache
      && !originalRequest._retry
      && originalRequest.headers?.['X-Skip-Auth-Refresh'] !== '1'
      && !String(originalRequest.url || '').includes('/infrastructure/auth/login')
      && !String(originalRequest.url || '').includes('/infrastructure/auth/refresh')
      && !String(originalRequest.url || '').includes('/infrastructure/oauth/token')
    );

    if (canRefresh) {
      originalRequest._retry = true;
      return refreshAccessTokenIfNeeded()
        .then(() => {
          originalRequest.headers = {
            ...(originalRequest.headers || {}),
            Authorization: `Bearer ${authTokenCache}`,
          };
          return api(originalRequest);
        });
    }

    // 统一错误处理
    let errorMessage = '请求失败，请稍后重试';
    let errorCode = 'UNKNOWN_ERROR';

    if (error.response) {
      // 服务器返回了错误响应
      const { status, data } = error.response;

      // 尝试从标准错误格式提取信息
      if (data?.error) {
        errorMessage = data.error.message || errorMessage;
        errorCode = data.error.code || errorCode;
      } else if (data?.detail) {
        errorMessage = data.detail;
      } else if (typeof data === 'string') {
        errorMessage = data;
      }

      // 根据状态码设置通用错误消息
      switch (status) {
        case 400:
          errorMessage = errorMessage || '请求参数错误';
          break;
        case 401:
          errorMessage = '请先登录';
          break;
        case 403:
          errorMessage = '没有权限访问';
          break;
        case 404:
          errorMessage = errorMessage || '请求的资源不存在';
          break;
        case 429:
          errorMessage = '请求过于频繁，请稍后再试';
          break;
        case 500:
          errorMessage = '服务器内部错误，请稍后重试';
          break;
        case 502:
        case 503:
          errorMessage = '服务暂时不可用，请稍后重试';
          break;
        default:
          break;
      }

      console.error(`API Error [${status}] ${errorCode}:`, errorMessage);
    } else if (error.request) {
      // 请求已发出但没有收到响应
      if (error.code === 'ECONNABORTED') {
        errorMessage = '请求超时，请检查网络连接';
      } else {
        errorMessage = '无法连接到服务器，请检查网络';
      }
      if (!error.config?.suppressNetworkErrorLog) {
        console.error('API Network Error:', error.config?.url || 'unknown', error.message);
      }
    } else {
      // 请求配置出错
      console.error('API Config Error:', error.message);
    }

    // 附加错误信息到 error 对象
    error.userMessage = errorMessage;
    error.errorCode = errorCode;

    return Promise.reject(error);
  }
);

// API方法
export const getStrategies = async () => {
  const response = await api.get('/strategies/');
  return response.data;
};

export const getMarketData = async (params) => {
  const response = await api.post('/market-data/', params);
  return response.data;
};

export const runBacktest = async (params) => {
  const response = await api.post('/backtest/', params);
  return response.data;
};

export const getBacktestHistory = async (limit = 20, filters = {}, offset = 0, options = {}) => {
  const params = new URLSearchParams({ limit: String(limit) });
  params.set('offset', String(offset));
  if (options.summaryOnly !== false) {
    params.set('summary_only', 'true');
  }
  if (filters.symbol) {
    params.set('symbol', filters.symbol);
  }
  if (filters.strategy) {
    params.set('strategy', filters.strategy);
  }
  if (filters.recordType) {
    params.set('record_type', filters.recordType);
  }
  const response = await api.get(`/backtest/history?${params.toString()}`);
  return response.data;
};

export const getBacktestHistoryStats = async (filters = {}) => {
  const params = new URLSearchParams();
  if (filters.symbol) {
    params.set('symbol', filters.symbol);
  }
  if (filters.strategy) {
    params.set('strategy', filters.strategy);
  }
  if (filters.recordType) {
    params.set('record_type', filters.recordType);
  }
  const query = params.toString();
  const response = await api.get(`/backtest/history/stats${query ? `?${query}` : ''}`);
  return response.data;
};

export const getBacktestRecord = async (recordId) => {
  const response = await api.get(`/backtest/history/${recordId}`);
  return response.data;
};

export const deleteBacktestRecord = async (recordId) => {
  const response = await api.delete(`/backtest/history/${recordId}`);
  return response.data;
};

export const saveAdvancedHistoryRecord = async (payload) => {
  const response = await api.post('/backtest/history/advanced', payload);
  return response.data;
};

const parseFilenameFromDisposition = (contentDisposition) => {
  if (!contentDisposition) {
    return '';
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }

  const asciiMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
  return asciiMatch?.[1] || '';
};

export const downloadBacktestReport = async (data) => {
  const response = await api.post('/backtest/report', data, {
    responseType: 'blob',
  });

  return {
    blob: response.data,
    filename: parseFilenameFromDisposition(response.headers['content-disposition']),
    contentType: response.headers['content-type'] || 'application/pdf',
  };
};

export const compareStrategies = async (
  symbolOrPayload,
  strategies,
  startDate,
  endDate,
  initialCapital = 10000,
  commission = 0.001,
  slippage = 0.001,
) => {
  const payload = typeof symbolOrPayload === 'object' && symbolOrPayload !== null
    ? symbolOrPayload
    : {
        symbol: symbolOrPayload,
        strategies,
        ...(startDate && { start_date: startDate }),
        ...(endDate && { end_date: endDate }),
        initial_capital: initialCapital,
        commission,
        slippage,
      };

  const response = await api.post('/backtest/compare', payload);
  return response.data;
};

export const runBatchBacktest = async (payload) => {
  const response = await api.post('/backtest/batch', payload);
  return response.data;
};

export const runWalkForwardBacktest = async (payload) => {
  const response = await api.post('/backtest/walk-forward', payload);
  return response.data;
};

export const runMarketRegimeBacktest = async (payload) => {
  const response = await api.post('/backtest/market-regimes', payload);
  return response.data;
};

export const runBacktestMonteCarlo = async (payload) => {
  const response = await api.post('/backtest/monte-carlo', payload, withTimeoutProfile('analysis'));
  return response.data;
};

export const queueBacktestMonteCarlo = async (payload) => {
  const response = await api.post('/backtest/monte-carlo/async', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const runMarketImpactAnalysis = async (payload) => {
  const response = await api.post('/backtest/impact-analysis', payload, withTimeoutProfile('analysis'));
  return response.data;
};

export const queueMarketImpactAnalysis = async (payload) => {
  const response = await api.post('/backtest/impact-analysis/async', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const compareStrategySignificance = async (payload) => {
  const response = await api.post('/backtest/compare/significance', payload, withTimeoutProfile('analysis'));
  return response.data;
};

export const queueStrategySignificance = async (payload) => {
  const response = await api.post('/backtest/compare/significance/async', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const runMultiPeriodBacktest = async (payload) => {
  const response = await api.post('/backtest/multi-period', payload, withTimeoutProfile('analysis'));
  return response.data;
};

export const queueMultiPeriodBacktest = async (payload) => {
  const response = await api.post('/backtest/multi-period/async', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const runPortfolioStrategyBacktest = async (payload) => {
  const response = await api.post('/backtest/portfolio-strategy', payload);
  return response.data;
};

// Analysis APIs
export const analyzeTrend = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/analyze', { symbol, interval });
  return response.data;
};

export const analyzeVolumePrice = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/volume-price', { symbol, interval });
  return response.data;
};

export const analyzeSentiment = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/sentiment', { symbol, interval });
  return response.data;
};

export const recognizePatterns = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/patterns', { symbol, interval });
  return response.data;
};

export const getAnalysisOverview = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/overview', { symbol, interval });
  return response.data;
};

export const getFundamentalAnalysis = async (symbol) => {
  const response = await api.post('/analysis/fundamental', { symbol });
  return response.data;
};

export const getKlines = async (symbol, interval = '1d', limit = 150) => {
  const response = await api.post(`/analysis/klines?limit=${limit}`, { symbol, interval });
  return response.data;
};

export const predictPrice = async (symbol) => {
  const response = await api.post('/analysis/prediction', { symbol });
  return response.data;
};

// 多股票相关性分析
export const getCorrelationAnalysis = async (symbols, periodDays = 90) => {
  const response = await api.post('/analysis/correlation', {
    symbols,
    period_days: periodDays
  });
  return response.data;
};

export const optimizePortfolio = async (symbols, period = '1y', objective = 'max_sharpe') => {
  // Wrap symbols in correct JSON structure: { symbols: ["A", "B"] }
  const response = await api.post('/optimization/optimize', { symbols, period, objective });
  return response.data;
};

export const getInfrastructureStatus = async () => {
  const response = await api.get('/infrastructure/status', withTimeoutProfile('standard'));
  return response.data;
};

export const createInfrastructureTask = async (payload) => {
  const response = await api.post('/infrastructure/tasks', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const saveInfrastructureRecord = async (payload) => {
  const response = await api.post('/infrastructure/persistence/records', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructurePersistenceDiagnostics = async () => {
  const response = await api.get('/infrastructure/persistence/diagnostics', withTimeoutProfile('standard'));
  return response.data;
};

export const bootstrapInfrastructurePersistence = async (payload) => {
  const response = await api.post('/infrastructure/persistence/bootstrap', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructurePersistenceMigrationPreview = async ({ sqlitePath } = {}) => {
  const params = new URLSearchParams();
  if (sqlitePath) params.set('sqlite_path', sqlitePath);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const response = await api.get(`/infrastructure/persistence/migration/preview${suffix}`, withTimeoutProfile('standard'));
  return response.data;
};

export const runInfrastructurePersistenceMigration = async (payload) => {
  const response = await api.post('/infrastructure/persistence/migration/run', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructureRecords = async ({ recordType, limit = 20 } = {}) => {
  const params = new URLSearchParams();
  if (recordType) params.set('record_type', recordType);
  params.set('limit', String(limit));
  const response = await api.get(`/infrastructure/persistence/records?${params.toString()}`, withTimeoutProfile('standard'));
  return response.data;
};

export const saveInfrastructureTimeseries = async (payload) => {
  const response = await api.post('/infrastructure/persistence/timeseries', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructureTimeseries = async ({ seriesName, symbol, limit = 20 } = {}) => {
  const params = new URLSearchParams();
  if (seriesName) params.set('series_name', seriesName);
  if (symbol) params.set('symbol', symbol);
  params.set('limit', String(limit));
  const response = await api.get(`/infrastructure/persistence/timeseries?${params.toString()}`, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructureTasks = async (limit = 20) => {
  const response = await api.get(`/infrastructure/tasks?limit=${limit}`, withTimeoutProfile('standard'));
  return response.data;
};

export const cancelInfrastructureTask = async (taskId) => {
  const response = await api.post(`/infrastructure/tasks/${encodeURIComponent(taskId)}/cancel`, undefined, withTimeoutProfile('standard'));
  return response.data;
};

export const updateInfrastructureRateLimits = async (payload) => {
  const response = await api.post('/infrastructure/rate-limits', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const createInfrastructureToken = async (payload) => {
  const response = await api.post('/infrastructure/auth/token', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const loginInfrastructureUser = async (payload) => {
  const response = await api.post('/infrastructure/auth/login', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const refreshInfrastructureToken = async (payload) => {
  const response = await api.post('/infrastructure/auth/refresh', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructureAuthUsers = async () => {
  const response = await api.get('/infrastructure/auth/users', withTimeoutProfile('standard'));
  return response.data;
};

export const saveInfrastructureAuthUser = async (payload) => {
  const response = await api.post('/infrastructure/auth/users', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const updateInfrastructureAuthPolicy = async (payload) => {
  const response = await api.post('/infrastructure/auth/policy', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const revokeInfrastructureAuthSession = async (sessionId) => {
  const response = await api.post(`/infrastructure/auth/sessions/${encodeURIComponent(sessionId)}/revoke`, undefined, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructureAuthProviders = async () => {
  const response = await api.get('/infrastructure/auth/oauth/providers', withTimeoutProfile('standard'));
  return response.data;
};

export const saveInfrastructureAuthProvider = async (payload) => {
  const response = await api.post('/infrastructure/auth/oauth/providers', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const syncInfrastructureAuthProvidersFromEnv = async () => {
  const response = await api.post('/infrastructure/auth/oauth/providers/sync-env', undefined, withTimeoutProfile('standard'));
  return response.data;
};

export const getInfrastructureAuthProviderDiagnostics = async (providerId) => {
  const response = await api.get(`/infrastructure/auth/oauth/providers/${encodeURIComponent(providerId)}/diagnostics`, withTimeoutProfile('standard'));
  return response.data;
};

export const startInfrastructureOAuthProvider = async (providerId, payload = {}) => {
  const response = await api.post(`/infrastructure/auth/oauth/providers/${encodeURIComponent(providerId)}/authorize`, payload, withTimeoutProfile('standard'));
  return response.data;
};

export const exchangeInfrastructureOAuthProvider = async (providerId, payload) => {
  const response = await api.post(`/infrastructure/auth/oauth/providers/${encodeURIComponent(providerId)}/exchange`, payload, withTimeoutProfile('standard'));
  return response.data;
};

export const testNotificationChannel = async (payload) => {
  const response = await api.post('/infrastructure/notifications/test', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const saveNotificationChannel = async (payload) => {
  const response = await api.post('/infrastructure/notifications/channels', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const deleteNotificationChannel = async (channelId) => {
  const response = await api.delete(`/infrastructure/notifications/channels/${encodeURIComponent(channelId)}`, withTimeoutProfile('standard'));
  return response.data;
};

export const saveConfigVersion = async (payload) => {
  const response = await api.post('/infrastructure/config-versions', payload, withTimeoutProfile('standard'));
  return response.data;
};

export const getConfigVersions = async ({ configType, configKey, ownerId = 'default', limit = 20 }) => {
  const params = new URLSearchParams({
    config_type: configType,
    config_key: configKey,
    owner_id: ownerId,
    limit: String(limit),
  });
  const response = await api.get(`/infrastructure/config-versions?${params.toString()}`, withTimeoutProfile('standard'));
  return response.data;
};

export const diffConfigVersions = async ({ configType, configKey, fromVersion, toVersion, ownerId = 'default' }) => {
  const params = new URLSearchParams({
    config_type: configType,
    config_key: configKey,
    owner_id: ownerId,
    from_version: String(fromVersion),
    to_version: String(toVersion),
  });
  const response = await api.get(`/infrastructure/config-versions/diff?${params.toString()}`, withTimeoutProfile('standard'));
  return response.data;
};

export const restoreConfigVersion = async (payload) => {
  const response = await api.post('/infrastructure/config-versions/restore', payload, withTimeoutProfile('standard'));
  return response.data;
};


export const getPortfolio = async () => {
  const response = await api.get('/trade/portfolio');
  return response.data;
};

export const getRealtimeQuote = async (symbol) => {
  const response = await api.get(`/realtime/quote/${encodeURIComponent(symbol)}`);
  return response.data;
};

export const getRealtimeReplay = async (symbol, params = {}) => {
  const search = new URLSearchParams();
  if (params.period) search.set('period', params.period);
  if (params.interval) search.set('interval', params.interval);
  if (params.limit) search.set('limit', String(params.limit));
  const query = search.toString();
  const response = await api.get(`/realtime/replay/${encodeURIComponent(symbol)}${query ? `?${query}` : ''}`, withTimeoutProfile('standard'));
  return response.data;
};

export const getRealtimeOrderbook = async (symbol, levels = 10) => {
  const response = await api.get(`/realtime/orderbook/${encodeURIComponent(symbol)}?levels=${levels}`, withTimeoutProfile('standard'));
  return response.data;
};

export const getRealtimeAnomalyDiagnostics = async (symbol, params = {}) => {
  const search = new URLSearchParams();
  if (params.period) search.set('period', params.period);
  if (params.interval) search.set('interval', params.interval);
  if (params.limit) search.set('limit', String(params.limit));
  if (params.z_window) search.set('z_window', String(params.z_window));
  if (params.return_z_threshold) search.set('return_z_threshold', String(params.return_z_threshold));
  if (params.volume_z_threshold) search.set('volume_z_threshold', String(params.volume_z_threshold));
  if (params.cusum_threshold_sigma) search.set('cusum_threshold_sigma', String(params.cusum_threshold_sigma));
  if (params.pattern_lookback) search.set('pattern_lookback', String(params.pattern_lookback));
  if (params.pattern_matches) search.set('pattern_matches', String(params.pattern_matches));
  const query = search.toString();
  const response = await api.get(`/realtime/anomaly-diagnostics/${encodeURIComponent(symbol)}${query ? `?${query}` : ''}`, withTimeoutProfile('standard'));
  return response.data;
};

export const getRealtimeAlerts = async (profileId) => {
  const response = await api.get('/realtime/alerts', {
    headers: profileId
      ? {
          'X-Realtime-Profile': profileId,
        }
      : undefined,
  });
  return response.data;
};

export const updateRealtimeAlerts = async (alerts, profileId, alertHitHistory = []) => {
  const response = await api.put(
    '/realtime/alerts',
    { alerts, alert_hit_history: alertHitHistory },
    {
      headers: profileId
        ? {
            'X-Realtime-Profile': profileId,
          }
        : undefined,
    }
  );
  return response.data;
};

export const recordRealtimeAlertHit = async (entry, profileId, options = {}) => {
  const response = await api.post(
    '/realtime/alerts/hits',
    {
      entry,
      notify_channels: options.notify_channels || [],
      create_workbench_task: options.create_workbench_task === true,
      persist_event_record: options.persist_event_record !== false,
      severity: options.severity || 'warning',
    },
    {
      headers: profileId
        ? {
            'X-Realtime-Profile': profileId,
          }
        : undefined,
    }
  );
  return response.data;
};

export const getRealtimeJournal = async (profileId) => {
  const response = await api.get('/realtime/journal', {
    headers: profileId
      ? {
          'X-Realtime-Profile': profileId,
        }
      : undefined,
  });
  return response.data;
};

export const updateRealtimeJournal = async (payload, profileId) => {
  const response = await api.put(
    '/realtime/journal',
    payload,
    {
      headers: profileId
        ? {
            'X-Realtime-Profile': profileId,
          }
        : undefined,
    }
  );
  return response.data;
};

export const executeTrade = async (symbol, action, quantity, price = null) => {
  const response = await api.post('/trade/execute', {
    symbol,
    action,
    quantity,
    price
  });
  return response.data;
};

export const getTradeHistory = async (limit = 50) => {
  const response = await api.get(`/trade/history?limit=${limit}`);
  return response.data;
};

// 事件 API
export const getEventSummary = async (symbol) => {
  const response = await api.post('/events/summary', { symbol });
  return response.data;
};

export const resetAccount = async () => {
  const response = await api.post('/trade/reset');
  return response.data;
};

export const compareModelPredictions = async (symbol) => {
  const response = await api.post('/analysis/prediction/compare', { symbol });
  return response.data;
};

export const predictWithLSTM = async (symbol) => {
  const response = await api.post('/analysis/prediction/lstm', { symbol });
  return response.data;
};

export const trainAllModels = async (symbol) => {
  const response = await api.post('/analysis/train/all', { symbol });
  return response.data;
};

// ============ 市场分析增强 API ============

// 获取技术指标快照（RSI、MACD、布林带）
export const getTechnicalIndicators = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/technical-indicators', { symbol, interval });
  return response.data;
};

// 获取历史情绪趋势（过去N天恐慌贪婪指数）
export const getSentimentHistory = async (symbol, days = 30) => {
  const response = await api.post(`/analysis/sentiment-history?days=${days}`, { symbol });
  return response.data;
};

// 获取行业对比分析
export const getIndustryComparison = async (symbol) => {
  const response = await api.post('/analysis/industry-comparison', { symbol });
  return response.data;
};

// 获取风险评估指标（VaR、最大回撤、夏普比率等）
export const getRiskMetrics = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/risk-metrics', { symbol, interval });
  return response.data;
};

// ============ 行业分析 API ============

// 获取热门行业排名
export const getHotIndustries = async (topN = 10, lookbackDays = 5, sortBy = 'total_score', order = 'desc', options = {}) => {
  const response = await api.get(`/industry/industries/hot?top_n=${topN}&lookback_days=${lookbackDays}&sort_by=${sortBy}&order=${order}`, options);
  return response.data;
};

// 获取行业成分股
export const getIndustryStocks = async (industryName, topN = 20, options = {}) => {
  const response = await api.get(`/industry/industries/${encodeURIComponent(industryName)}/stocks?top_n=${topN}`, options);
  return response.data;
};

export const getIndustryStockBuildStatus = async (industryName, topN = 20, options = {}) => {
  const response = await api.get(`/industry/industries/${encodeURIComponent(industryName)}/stocks/status?top_n=${topN}`, options);
  return response.data;
};

// 获取行业热力图数据
export const getIndustryHeatmap = async (days = 5, options = {}) => {
  const response = await api.get(`/industry/industries/heatmap?days=${days}`, options);
  return response.data;
};

export const getIndustryBootstrap = async (
  days = 5,
  params = {},
  options = {},
) => {
  const response = await api.get('/industry/bootstrap', {
    ...options,
    params: {
      ...options.params,
      days,
      ...params,
    },
  });
  return response.data;
};

export const getIndustryHeatmapHistory = async (params = {}, options = {}) => {
  const search = new URLSearchParams();
  if (params.limit) search.set('limit', String(params.limit));
  if (params.days) search.set('days', String(params.days));
  const query = search.toString();
  const response = await api.get(`/industry/industries/heatmap/history${query ? `?${query}` : ''}`, options);
  return response.data;
};

export const getIndustryPreferences = async (options = {}) => {
  const response = await api.get('/industry/preferences', options);
  return response.data;
};

export const updateIndustryPreferences = async (payload, options = {}) => {
  const response = await api.put('/industry/preferences', payload, options);
  return response.data;
};

export const exportIndustryPreferences = async (options = {}) => {
  const response = await api.get('/industry/preferences/export', options);
  return response.data;
};

export const importIndustryPreferences = async (payload, options = {}) => {
  const response = await api.post('/industry/preferences/import', payload, options);
  return response.data;
};

// 获取行业趋势分析
export const getIndustryTrend = async (industryName, days = 30, options = {}) => {
  const response = await api.get(`/industry/industries/${encodeURIComponent(industryName)}/trend?days=${days}`, options);
  return response.data;
};

// 获取行业聚类分析
export const getIndustryClusters = async (nClusters = 4, options = {}) => {
  const response = await api.get(`/industry/industries/clusters?n_clusters=${nClusters}`, options);
  return response.data;
};

// 获取龙头股推荐列表
export const getLeaderStocks = async (topN = 20, topIndustries = 5, perIndustry = 5, listType = 'hot', options = {}) => {
  const response = await api.get('/industry/leaders', {
    ...options,
    params: {
      ...options.params,
      top_n: topN,
      top_industries: topIndustries,
      per_industry: perIndustry,
      list_type: listType
    }
  });
  return response.data;
};

// 一次性获取核心资产与热点先锋榜单
export const getLeaderBoards = async (topN = 20, topIndustries = 5, perIndustry = 5, options = {}) => {
  const response = await api.get('/industry/leaders/overview', {
    ...options,
    params: {
      ...options.params,
      top_n: topN,
      top_industries: topIndustries,
      per_industry: perIndustry
    }
  });
  return response.data;
};

// 获取龙头股详细分析
export const getLeaderDetail = async (symbol, scoreType = 'core', options = {}) => {
  const response = await api.get(`/industry/leaders/${symbol}/detail`, {
    ...options,
    params: {
      ...options.params,
      score_type: scoreType
    }
  });
  return response.data;
};

// 获取行业轮动对比数据
export const getIndustryRotation = async (industries, periods = [], options = {}) => {
  const params = new URLSearchParams();
  params.set('industries', industries.join(','));
  if (Array.isArray(periods) && periods.length > 0) {
    params.set('periods', periods.join(','));
  }
  const response = await api.get(
    `/industry/industries/rotation?${params.toString()}`,
    options
  );
  return response.data;
};

export const getIndustryIntelligence = async (topN = 12, lookbackDays = 5, options = {}) => {
  const response = await api.get(
    `/industry/industries/intelligence?top_n=${topN}&lookback_days=${lookbackDays}`,
    options
  );
  return response.data;
};

export const getIndustryNetwork = async (topN = 18, lookbackDays = 5, minSimilarity = 0.92, options = {}) => {
  const response = await api.get(
    `/industry/industries/network?top_n=${topN}&lookback_days=${lookbackDays}&min_similarity=${minSimilarity}`,
    options
  );
  return response.data;
};

// 行业分析模块健康检查
export const checkIndustryHealth = async () => {
  const response = await api.get('/industry/health');
  return response.data;
};

export const getCrossMarketTemplates = async () => {
  const response = await api.get('/cross-market/templates', withTimeoutProfile('dashboard'));
  return response.data;
};

export const runCrossMarketBacktest = async (payload) => {
  const response = await api.post('/cross-market/backtest', payload, withTimeoutProfile('analysis'));
  return response.data;
};

export default api;
