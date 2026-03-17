import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const API_TIMEOUT = parseInt(process.env.REACT_APP_API_TIMEOUT) || 300000;
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

// 请求拦截器
api.interceptors.request.use(
  (config) => {
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
      console.error('API Network Error:', error.message);
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
  const response = await api.get('/strategies');
  return response.data;
};

export const getMarketData = async (params) => {
  const response = await api.post('/market-data', params);
  return response.data;
};

export const runBacktest = async (params) => {
  const response = await api.post('/backtest', params);
  return response.data;
};

export const getBacktestHistory = async (limit = 20) => {
  const response = await api.get(`/backtest/history?limit=${limit}`);
  return response.data;
};

export const deleteBacktestRecord = async (recordId) => {
  const response = await api.delete(`/backtest/history/${recordId}`);
  return response.data;
};

// 获取回测报告（Base64格式）
export const getBacktestReport = async (data) => {
  const response = await api.post('/backtest/report/base64', data);
  return response.data;
};



export const searchSymbols = async (query) => {
  const response = await api.get(`/symbols/search?query=${encodeURIComponent(query)}`);
  return response.data;
};

export const compareStrategies = async (symbol, strategies, startDate, endDate, initialCapital = 100000) => {
  const params = new URLSearchParams({
    symbol,
    strategies: strategies.join(','),
    ...(startDate && { start_date: startDate }),
    ...(endDate && { end_date: endDate }),
    initial_capital: initialCapital
  });

  const response = await api.get(`/backtest/compare?${params}`);
  return response.data;
};

export const getSystemStatus = async () => {
  const response = await api.get('/system/status?detailed=true');
  return response.data;
};

export const getPerformanceMetrics = async () => {
  const response = await api.get('/system/performance');
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

export const getComprehensiveAnalysis = async (symbol, interval = '1d') => {
  const response = await api.post('/analysis/comprehensive', { symbol, interval });
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


export const getPortfolio = async () => {
  const response = await api.get('/trade/portfolio');
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

// 告警相关 API
export const getAlertSummary = async () => {
  const response = await api.get('/system/alerts/summary');
  return response.data;
};

export const resolveAlert = async (alertIndex) => {
  const response = await api.post(`/system/alerts/${alertIndex}/resolve`);
  return response.data;
};

export const checkDependencies = async () => {
  const response = await api.get('/system/dependencies');
  return response.data;
};

// AI 模型相关 API
export const getAvailableModels = async () => {
  const response = await api.get('/analysis/models');
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

// 获取行业热力图数据
export const getIndustryHeatmap = async (days = 5, options = {}) => {
  const response = await api.get(`/industry/industries/heatmap?days=${days}`, options);
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
export const getIndustryRotation = async (industries, options = {}) => {
  const response = await api.get(
    `/industry/industries/rotation?industries=${encodeURIComponent(industries.join(','))}`,
    options
  );
  return response.data;
};

// 行业分析模块健康检查
export const checkIndustryHealth = async () => {
  const response = await api.get('/industry/health');
  return response.data;
};

// ============ 资产定价研究 API ============

// 因子模型分析（CAPM + Fama-French）
export const getFactorModelAnalysis = async (symbol, period = '1y') => {
  const response = await api.post('/pricing/factor-model', { symbol, period });
  return response.data;
};

// 内在价值估值（DCF + 可比估值）
export const getValuationAnalysis = async (symbol) => {
  const response = await api.post('/pricing/valuation', { symbol });
  return response.data;
};

// 定价差异分析（综合分析）
export const getGapAnalysis = async (symbol, period = '1y') => {
  const response = await api.post('/pricing/gap-analysis', { symbol, period });
  return response.data;
};

// 获取市场因子数据快照
export const getBenchmarkFactors = async () => {
  const response = await api.get('/pricing/benchmark-factors');
  return response.data;
};

export const getAltDataSnapshot = async (refresh = false) => {
  const response = await api.get(`/alt-data/snapshot?refresh=${refresh}`);
  return response.data;
};

export const getAltDataStatus = async () => {
  const response = await api.get('/alt-data/status');
  return response.data;
};

export const getAltSignals = async (params = {}) => {
  const search = new URLSearchParams();
  if (params.category) search.set('category', params.category);
  if (params.timeframe) search.set('timeframe', params.timeframe);
  if (params.refresh) search.set('refresh', 'true');
  const query = search.toString();
  const response = await api.get(`/alt-data/signals${query ? `?${query}` : ''}`);
  return response.data;
};

export const refreshAltData = async (provider = 'all') => {
  const response = await api.post(`/alt-data/refresh?provider=${encodeURIComponent(provider)}`);
  return response.data;
};

export const getAltDataHistory = async (params = {}) => {
  const search = new URLSearchParams();
  if (params.category) search.set('category', params.category);
  if (params.timeframe) search.set('timeframe', params.timeframe);
  if (params.limit) search.set('limit', String(params.limit));
  const query = search.toString();
  const response = await api.get(`/alt-data/history${query ? `?${query}` : ''}`);
  return response.data;
};

export const getMacroOverview = async (refresh = false) => {
  const response = await api.get(`/macro/overview?refresh=${refresh}`);
  return response.data;
};

export const getCrossMarketTemplates = async () => {
  const response = await api.get('/cross-market/templates');
  return response.data;
};

export const runCrossMarketBacktest = async (payload) => {
  const response = await api.post('/cross-market/backtest', payload);
  return response.data;
};

export default api;
