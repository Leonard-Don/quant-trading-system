import React, { useState, useEffect, useRef, useMemo, useCallback, lazy, Suspense } from 'react';
import {
    Card,
    Input,
    Tabs,
    Row,
    Col,
    Tag,
    List,
    Typography,
    Progress,
    Alert,
    Space,
    Table,
    Statistic,
    Empty,
    Divider,
    Radio,
    Spin,
    Popover
} from 'antd';
import {
    RiseOutlined,
    FallOutlined,
    WarningOutlined,
    RadarChartOutlined,
    BarChartOutlined,
    ThunderboltOutlined,
    RobotOutlined,
    SolutionOutlined,
    InfoCircleOutlined,
    ExperimentOutlined,
    FundOutlined,
    LineChartOutlined,
    BankOutlined,
    CalendarOutlined,
    DollarCircleOutlined,
    NotificationOutlined,
    DashboardOutlined,
    ReloadOutlined,
} from '@ant-design/icons';
import {
    Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
    ComposedChart, ReferenceArea, ReferenceLine, Scatter,
    ResponsiveContainer,
    Tooltip as RechartsTooltip,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Cell,
    CartesianGrid,
    Line,
    LineChart,
} from 'recharts';
import {
    getAnalysisOverview,
    analyzeTrend,
    analyzeVolumePrice,
    analyzeSentiment,
    recognizePatterns,
    getFundamentalAnalysis,
    getKlines,
    getTechnicalIndicators,
    getSentimentHistory,
    getIndustryComparison,
    getRiskMetrics,
    getCorrelationAnalysis,
    getEventSummary
} from '../services/api';
import { MarketAnalysisSkeleton } from './SkeletonLoaders';

import { Tooltip } from 'antd'; // Careful, we have RechartsTooltip imported as well. 

const { Title, Text } = Typography;
const { Search } = Input;
const DEFAULT_VOLUME_TREND = {
    trend: 'unknown',
    direction: 'neutral',
    volume_ratio: 0,
    avg_volume_5d: 0,
    avg_volume_20d: 0,
    current_volume: 0
};

const normalizeVolumeTrend = (value) => {
    if (!value) return { ...DEFAULT_VOLUME_TREND };
    if (typeof value === 'string') {
        return { ...DEFAULT_VOLUME_TREND, trend: value };
    }
    return { ...DEFAULT_VOLUME_TREND, ...value };
};

const DISPLAY_EMPTY = '--';
const ANALYSIS_CACHE_TTL_MS = 2 * 60 * 1000;
const analysisResponseCache = new Map();
const AIPredictionPanel = lazy(() => import('./AIPredictionPanel'));
const CandlestickChart = lazy(() => import('./CandlestickChart'));
const TAB_LABELS = {
    overview: '总览',
    trend: '趋势分析',
    volume: '量价分析',
    sentiment: '情绪分析',
    pattern: '形态识别',
    fundamental: '基本面分析',
    industry: '行业对比',
    risk: '风险评估',
    correlation: '相关性',
    prediction: 'AI 预测',
};

const buildAnalysisCacheKey = (tab, symbol, interval = '') => `${tab}|${symbol || ''}|${interval || ''}`;
const clearAnalysisCache = (symbol, interval) => {
    const keyFragments = [
        buildAnalysisCacheKey('overview', symbol, interval),
        buildAnalysisCacheKey('trend', symbol, interval),
        buildAnalysisCacheKey('volume', symbol, interval),
        buildAnalysisCacheKey('sentiment', symbol, interval),
        buildAnalysisCacheKey('pattern', symbol, interval),
        buildAnalysisCacheKey('fundamental', symbol),
        buildAnalysisCacheKey('technical', symbol, interval),
        buildAnalysisCacheKey('events', symbol),
        buildAnalysisCacheKey('sentimentHistory', symbol),
        buildAnalysisCacheKey('industry', symbol),
        buildAnalysisCacheKey('risk', symbol, interval),
        buildAnalysisCacheKey('correlation', symbol),
    ];
    keyFragments.forEach((cacheKey) => analysisResponseCache.delete(cacheKey));
};
const readAnalysisCacheEntry = (cacheKey) => {
    const cached = analysisResponseCache.get(cacheKey);
    if (!cached) {
        return null;
    }

    if (Date.now() - cached.cachedAt > ANALYSIS_CACHE_TTL_MS) {
        analysisResponseCache.delete(cacheKey);
        return null;
    }

    return cached;
};
const writeAnalysisCache = (cacheKey, data) => {
    const cachedAt = Date.now();
    analysisResponseCache.set(cacheKey, {
        data,
        cachedAt,
    });
    return cachedAt;
};

const formatDisplayNumber = (value, digits = 2, suffix = '') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return DISPLAY_EMPTY;
    }
    return `${Number(value).toFixed(digits)}${suffix}`;
};

const formatDisplayPercent = (value, digits = 2, valueIsRatio = false) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return DISPLAY_EMPTY;
    }
    const numericValue = valueIsRatio ? Number(value) * 100 : Number(value);
    return `${numericValue.toFixed(digits)}%`;
};
const formatMetaTime = (timestamp) => {
    if (!timestamp) {
        return DISPLAY_EMPTY;
    }

    return new Intl.DateTimeFormat('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    }).format(timestamp);
};

const MarketAnalysis = ({ symbol: propSymbol, embedMode = false }) => {
    const [symbol, setSymbol] = useState(propSymbol || 'AAPL');
    const [interval, setInterval] = useState('1d');
    const [activeTab, setActiveTab] = useState('overview');

    const [overviewData, setOverviewData] = useState(null);
    const [trendData, setTrendData] = useState(null);
    const [volumeData, setVolumeData] = useState(null);
    const [sentimentData, setSentimentData] = useState(null);
    const [patternData, setPatternData] = useState(null);
    const [fundamentalData, setFundamentalData] = useState(null);
    const [klinesData, setKlinesData] = useState(null);
    // 新增状态
    const [technicalData, setTechnicalData] = useState(null);
    const [sentimentHistoryData, setSentimentHistoryData] = useState(null);
    const [industryData, setIndustryData] = useState(null);
    const [riskData, setRiskData] = useState(null);
    const [correlationData, setCorrelationData] = useState(null);
    const [eventData, setEventData] = useState(null);

    const [loadingTab, setLoadingTab] = useState({});
    const [errorTab, setErrorTab] = useState({});
    const [tabMeta, setTabMeta] = useState({});

    const setTabLoading = (key, value) => {
        setLoadingTab(prev => ({ ...prev, [key]: value }));
    };

    const setTabError = (key, value) => {
        setErrorTab(prev => ({ ...prev, [key]: value }));
    };
    const setTabMetaEntry = (key, source, updatedAt) => {
        setTabMeta(prev => ({
            ...prev,
            [key]: {
                source,
                updatedAt,
            },
        }));
    };

    const resetAll = () => {
        setOverviewData(null);
        setTrendData(null);
        setVolumeData(null);
        setSentimentData(null);
        setPatternData(null);
        setFundamentalData(null);
        setKlinesData(null);
        setTechnicalData(null);
        setSentimentHistoryData(null);
        setIndustryData(null);
        setRiskData(null);
        setCorrelationData(null);
        setEventData(null);
        setLoadingTab({});
        setErrorTab({});
        setTabMeta({});
    };


    const buildAnalysisKey = (sym, intv) => `${sym || ''}|${intv || ''}`;
    const analysisKeyRef = useRef(buildAnalysisKey(symbol, interval));
    const prefetchHandleRef = useRef(null);
    const isInitializedRef = useRef(false); // 防止 StrictMode 双重执行
    const previousPropSymbolRef = useRef(propSymbol || null);

    const cancelPrefetch = () => {
        if (!prefetchHandleRef.current) return;
        if (prefetchHandleRef.current.type === 'idle' && typeof window !== 'undefined' && window.cancelIdleCallback) {
            window.cancelIdleCallback(prefetchHandleRef.current.id);
        } else {
            clearTimeout(prefetchHandleRef.current.id);
        }
        prefetchHandleRef.current = null;
    };

    const fetchTabIfNeeded = (tabKey, currentSymbol, currentInterval) => {
        const targetSymbol = currentSymbol || symbol;
        const targetInterval = currentInterval || interval;

        if (tabKey === 'overview' && !overviewData && !loadingTab.overview) {
            fetchOverview(targetSymbol, targetInterval);
            // 同时获取事件数据
            if (!eventData && !loadingTab.events) {
                fetchEvents(targetSymbol);
            }
        }
        if (tabKey === 'trend' && !trendData && !loadingTab.trend) {
            fetchTrend(targetSymbol, targetInterval);
        }
        if (tabKey === 'volume' && !volumeData && !loadingTab.volume) {
            fetchVolume(targetSymbol, targetInterval);
        }
        if (tabKey === 'sentiment' && !sentimentData && !loadingTab.sentiment) {
            fetchSentiment(targetSymbol, targetInterval);
            // 同时获取历史情绪数据
            if (!sentimentHistoryData && !loadingTab.sentimentHistory) {
                fetchSentimentHistory(targetSymbol);
            }
        }
        if (tabKey === 'pattern' && !patternData && !loadingTab.pattern) {
            fetchPattern(targetSymbol, targetInterval);
        }
        if (tabKey === 'fundamental' && !fundamentalData && !loadingTab.fundamental) {
            fetchFundamental(targetSymbol);
        }
        // 新增 Tab
        if (tabKey === 'industry' && !industryData && !loadingTab.industry) {
            fetchIndustryComparison(targetSymbol);
        }
        if (tabKey === 'risk' && !riskData && !loadingTab.risk) {
            fetchRiskMetrics(targetSymbol, targetInterval);
        }
        if (tabKey === 'correlation' && !correlationData && !loadingTab.correlation) {
            fetchCorrelation(targetSymbol);
        }
    };

    const schedulePrefetch = (localKey) => {
        if (localKey !== analysisKeyRef.current) return;
        cancelPrefetch();
        const queue = embedMode ? [] : ['trend', 'volume', 'sentiment', 'fundamental'];
        if (!queue.length) return;

        const runStep = (index) => {
            if (localKey !== analysisKeyRef.current) return;
            if (index >= queue.length) return;
            // Always use current refs for fetch
            fetchTabIfNeeded(queue[index], symbol, interval);

            const scheduleNext = () => runStep(index + 1);
            if (typeof window !== 'undefined' && window.requestIdleCallback) {
                const id = window.requestIdleCallback(scheduleNext, { timeout: 1000 });
                prefetchHandleRef.current = { type: 'idle', id };
            } else {
                const id = setTimeout(scheduleNext, 300);
                prefetchHandleRef.current = { type: 'timeout', id };
            }
        };

        const scheduleStart = () => runStep(0);
        if (typeof window !== 'undefined' && window.requestIdleCallback) {
            const id = window.requestIdleCallback(scheduleStart, { timeout: 1000 });
            prefetchHandleRef.current = { type: 'idle', id };
        } else {
            const id = setTimeout(scheduleStart, 300);
            prefetchHandleRef.current = { type: 'timeout', id };
        }
    };

    const fetchOverview = async (searchSymbol, selectedInterval = '1d') => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('overview', searchSymbol, selectedInterval);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('overview', null);
            setOverviewData(cachedResult);
            setTabMetaEntry('overview', 'cache', cachedEntry.cachedAt);
            if (cachedResult.indicators) {
                setTechnicalData(cachedResult.indicators);
            } else if (!technicalData && !loadingTab.technical) {
                fetchTechnicalIndicators(searchSymbol, selectedInterval);
            }
            schedulePrefetch(localKey);
            return;
        }
        setTabLoading('overview', true);
        setTabError('overview', null);
        try {
            const result = await getAnalysisOverview(searchSymbol, selectedInterval);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setOverviewData(result);
            setTabMetaEntry('overview', 'live', cachedAt);
            if (result.indicators) {
                setTechnicalData(result.indicators);
            } else if (!technicalData && !loadingTab.technical) {
                fetchTechnicalIndicators(searchSymbol, selectedInterval);
            }
            schedulePrefetch(localKey);
        } catch (err) {
            console.error('Failed to fetch overview:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('overview', '获取总览数据失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('overview', false);
            }
        }
    };

    const fetchTrend = async (searchSymbol, selectedInterval = '1d') => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('trend', searchSymbol, selectedInterval);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('trend', null);
            setTrendData(cachedResult);
            setTabMetaEntry('trend', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('trend', true);
        setTabError('trend', null);
        try {
            const result = await analyzeTrend(searchSymbol, selectedInterval);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setTrendData(result);
            setTabMetaEntry('trend', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch trend:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('trend', '获取趋势数据失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('trend', false);
            }
        }
    };

    const fetchVolume = async (searchSymbol, selectedInterval = '1d') => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('volume', searchSymbol, selectedInterval);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('volume', null);
            setVolumeData(cachedResult);
            setTabMetaEntry('volume', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('volume', true);
        setTabError('volume', null);
        try {
            const result = await analyzeVolumePrice(searchSymbol, selectedInterval);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setVolumeData(result);
            setTabMetaEntry('volume', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch volume:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('volume', '获取量价数据失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('volume', false);
            }
        }
    };

    const fetchSentiment = async (searchSymbol, selectedInterval = '1d') => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('sentiment', searchSymbol, selectedInterval);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('sentiment', null);
            setSentimentData(cachedResult);
            setTabMetaEntry('sentiment', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('sentiment', true);
        setTabError('sentiment', null);
        try {
            const result = await analyzeSentiment(searchSymbol, selectedInterval);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setSentimentData(result);
            setTabMetaEntry('sentiment', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch sentiment:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('sentiment', '获取情绪数据失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('sentiment', false);
            }
        }
    };

    const fetchPattern = async (searchSymbol, selectedInterval = '1d') => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('pattern', searchSymbol, selectedInterval);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('pattern', null);
            setPatternData(cachedResult.patternResult);
            setKlinesData(cachedResult.klinesData || []);
            setTabMetaEntry('pattern', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('pattern', true);
        setTabError('pattern', null);
        try {
            const [patternResult, klinesResult] = await Promise.all([
                recognizePatterns(searchSymbol, selectedInterval),
                getKlines(searchSymbol, selectedInterval)
            ]);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, {
                patternResult,
                klinesData: klinesResult.klines || [],
            });
            setPatternData(patternResult);
            setKlinesData(klinesResult.klines || []);
            setTabMetaEntry('pattern', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch pattern:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('pattern', '获取形态数据失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('pattern', false);
            }
        }
    };

    const fetchFundamental = async (searchSymbol) => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('fundamental', searchSymbol);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('fundamental', null);
            setFundamentalData(cachedResult);
            setTabMetaEntry('fundamental', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('fundamental', true);
        setTabError('fundamental', null);
        try {
            const result = await getFundamentalAnalysis(searchSymbol);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setFundamentalData(result);
            setTabMetaEntry('fundamental', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch fundamental:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('fundamental', '获取基本面数据失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('fundamental', false);
            }
        }
    };

    // 新增 fetch 函数
    const fetchTechnicalIndicators = async (searchSymbol, selectedInterval = '1d') => {
        if (!searchSymbol) return;
        const cacheKey = buildAnalysisCacheKey('technical', searchSymbol, selectedInterval);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('technical', null);
            setTechnicalData(cachedResult);
            return;
        }
        setTabLoading('technical', true);
        setTabError('technical', null);
        const localKey = analysisKeyRef.current;
        try {
            const data = await getTechnicalIndicators(searchSymbol, selectedInterval);
            if (localKey !== analysisKeyRef.current) return;
            // 后端直接返回 { rsi, macd, bollinger, overall }，无需额外转换
            writeAnalysisCache(cacheKey, data);
            setTechnicalData(data);
        } catch (err) {
            console.error('Failed to fetch technical indicators:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('technical', '获取技术指标失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('technical', false);
            }
        }
    };

    const fetchEvents = async (searchSymbol) => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('events', searchSymbol);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('events', null);
            setEventData(cachedResult);
            return;
        }
        setTabLoading('events', true);
        setTabError('events', null);
        try {
            const data = await getEventSummary(searchSymbol);
            if (localKey !== analysisKeyRef.current) return;
            writeAnalysisCache(cacheKey, data);
            setEventData(data);
        } catch (error) {
            console.error('Error fetching events:', error);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('events', '获取事件数据失败: ' + (error.response?.data?.detail || error.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('events', false);
            }
        }
    };

    const fetchSentimentHistory = async (searchSymbol) => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('sentimentHistory', searchSymbol);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('sentimentHistory', null);
            setSentimentHistoryData(cachedResult);
            return;
        }
        setTabLoading('sentimentHistory', true);
        setTabError('sentimentHistory', null);
        try {
            const result = await getSentimentHistory(searchSymbol, 30);
            if (localKey !== analysisKeyRef.current) return;
            writeAnalysisCache(cacheKey, result);
            setSentimentHistoryData(result);
        } catch (err) {
            console.error('Failed to fetch sentiment history:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('sentimentHistory', '获取历史情绪失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('sentimentHistory', false);
            }
        }
    };

    const fetchIndustryComparison = async (searchSymbol) => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('industry', searchSymbol);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('industry', null);
            setIndustryData(cachedResult);
            setTabMetaEntry('industry', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('industry', true);
        setTabError('industry', null);
        try {
            const result = await getIndustryComparison(searchSymbol);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setIndustryData(result);
            setTabMetaEntry('industry', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch industry comparison:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('industry', '获取行业对比失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('industry', false);
            }
        }
    };

    const fetchRiskMetrics = async (searchSymbol, selectedInterval = '1d') => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('risk', searchSymbol, selectedInterval);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('risk', null);
            setRiskData(cachedResult);
            setTabMetaEntry('risk', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('risk', true);
        setTabError('risk', null);
        try {
            const result = await getRiskMetrics(searchSymbol, selectedInterval);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setRiskData(result);
            setTabMetaEntry('risk', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch risk metrics:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('risk', '获取风险指标失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('risk', false);
            }
        }
    };

    const fetchCorrelation = async (searchSymbol) => {
        if (!searchSymbol) return;
        const localKey = analysisKeyRef.current;
        const cacheKey = buildAnalysisCacheKey('correlation', searchSymbol);
        const cachedEntry = readAnalysisCacheEntry(cacheKey);
        const cachedResult = cachedEntry?.data;
        if (cachedResult) {
            setTabError('correlation', null);
            setCorrelationData(cachedResult);
            setTabMetaEntry('correlation', 'cache', cachedEntry.cachedAt);
            return;
        }
        setTabLoading('correlation', true);
        setTabError('correlation', null);
        try {
            // 默认添加几个常见股票进行对比
            const defaultSymbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL'];
            const symbolsToUse = [searchSymbol, ...defaultSymbols.filter(s => s !== searchSymbol)].slice(0, 5);
            const result = await getCorrelationAnalysis(symbolsToUse, 90);
            if (localKey !== analysisKeyRef.current) return;
            const cachedAt = writeAnalysisCache(cacheKey, result);
            setCorrelationData(result);
            setTabMetaEntry('correlation', 'live', cachedAt);
        } catch (err) {
            console.error('Failed to fetch correlation:', err);
            if (localKey !== analysisKeyRef.current) return;
            setTabError('correlation', '获取相关性分析失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            if (localKey === analysisKeyRef.current) {
                setTabLoading('correlation', false);
            }
        }
    };

    const beginAnalysis = (nextSymbol, nextInterval) => {
        const localKey = buildAnalysisKey(nextSymbol, nextInterval);
        analysisKeyRef.current = localKey;
        cancelPrefetch();
        resetAll();
        setActiveTab('overview');
        fetchOverview(nextSymbol, nextInterval);
    };

    useEffect(() => {
        const targetSymbol = propSymbol || symbol;
        const incomingPropSymbol = propSymbol || null;
        const shouldReinitialize = !isInitializedRef.current || incomingPropSymbol !== previousPropSymbolRef.current;

        if (!targetSymbol || !shouldReinitialize) {
            return;
        }

        isInitializedRef.current = true;
        previousPropSymbolRef.current = incomingPropSymbol;

        if (propSymbol && propSymbol !== symbol) {
            setSymbol(propSymbol);
        }

        beginAnalysis(targetSymbol, interval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [propSymbol]);

    const handleSearch = (value) => {
        if (value) {
            setSymbol(value.toUpperCase());
            beginAnalysis(value.toUpperCase(), interval);
        }
    };

    const handleIntervalChange = (e) => {
        const newInterval = e.target.value;
        setInterval(newInterval);
        beginAnalysis(symbol, newInterval);
    };

    const handleTabChange = (key) => {
        setActiveTab(key);
        fetchTabIfNeeded(key, symbol, interval);
    };

    const handleRefreshAnalysis = () => {
        const currentTab = activeTab;
        clearAnalysisCache(symbol, interval);
        cancelPrefetch();
        resetAll();
        analysisKeyRef.current = buildAnalysisKey(symbol, interval);
        setActiveTab(currentTab);
        fetchOverview(symbol, interval);
        if (currentTab !== 'overview' && currentTab !== 'prediction') {
            fetchTabIfNeeded(currentTab, symbol, interval);
        }
    };
    const activeMetaKey = activeTab === 'prediction' ? 'overview' : activeTab;
    const activeTabMeta = tabMeta[activeMetaKey];
    const activeTabLabel = TAB_LABELS[activeTab] || activeTab;
    const activeMetaSourceLabel = activeTabMeta?.source === 'cache' ? '缓存命中' : activeTabMeta?.source === 'live' ? '实时拉取' : '等待加载';
    const activeMetaTone = activeTabMeta?.source === 'cache' ? { color: '#d97706', background: 'rgba(217, 119, 6, 0.12)' } : { color: '#2563eb', background: 'rgba(37, 99, 235, 0.12)' };
    const activeMetaTimeLabel = activeTabMeta?.updatedAt ? formatMetaTime(activeTabMeta.updatedAt) : DISPLAY_EMPTY;

    // --- Render Helpers ---

    const renderScoreGauge = useCallback((score) => {
        let color = '#1890ff';
        if (score >= 75) color = '#00b578';
        else if (score >= 50) color = '#1890ff';
        else if (score >= 30) color = '#faad14';
        else color = '#ff3030';

        return (
            <div style={{ textAlign: 'center' }}>
                <Progress
                    type="dashboard"
                    percent={score}
                    format={(percent) => (
                        <>
                            <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{percent}</div>
                            <div style={{ fontSize: '12px', color: '#888' }}>综合评分</div>
                        </>
                    )}
                    strokeColor={color}
                    size={180}
                />
            </div>
        );
    }, []);

    const renderRecommendation = useCallback((rec) => {
        let color = 'default';
        if (rec.includes('买入')) color = 'success';
        else if (rec.includes('卖出')) color = 'error';
        else if (rec.includes('持有')) color = 'warning';

        return (
            <Tag color={color} style={{ fontSize: '16px', padding: '5px 10px' }}>
                {rec}
            </Tag>
        );
    }, []);

    const renderRadarChart = useCallback((scores) => {
        const chartData = [
            { subject: '趋势', A: scores.trend, fullMark: 100 },
            { subject: '量价', A: scores.volume, fullMark: 100 },
            { subject: '情绪', A: scores.sentiment, fullMark: 100 },
            { subject: '技术', A: scores.technical, fullMark: 100 },
        ];

        return (
            <div className="radar-chart-container">
                <ResponsiveContainer width="100%" height={240}>
                    <RadarChart cx="50%" cy="50%" outerRadius="70%" data={chartData}>
                        <defs>
                            <linearGradient id="radarFill" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#2db7f5" stopOpacity={0.8} />
                                <stop offset="95%" stopColor="#00b578" stopOpacity={0.4} />
                            </linearGradient>
                        </defs>
                        <PolarGrid gridType="circle" stroke="rgba(148, 163, 184, 0.2)" />
                        <PolarAngleAxis
                            dataKey="subject"
                            tick={{ fill: 'var(--text-secondary)', fontSize: 13, fontWeight: 500 }}
                        />
                        <PolarRadiusAxis
                            angle={30}
                            domain={[0, 100]}
                            tick={{ fontSize: 10, fill: '#94a3b8' }}
                            axisLine={false}
                            tickCount={6}
                        />
                        <Radar
                            name="综合评分"
                            dataKey="A"
                            stroke="#2db7f5"
                            strokeWidth={2.5}
                            fill="url(#radarFill)"
                            fillOpacity={0.8}
                            activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }}
                        />
                        <RechartsTooltip
                            contentStyle={{
                                backgroundColor: 'rgba(255, 255, 255, 0.9)',
                                borderRadius: '8px',
                                border: 'none',
                                boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
                            }}
                            itemStyle={{ color: '#333', fontWeight: 500 }}
                            formatter={(value) => [`${value}分`, '得分']}
                        />
                    </RadarChart>
                </ResponsiveContainer>
            </div>
        );
    }, []);

    // --- Tab Contents (Memoized) ---

    // 1. Overview Content
    const overviewContent = useMemo(() => {
        if (loadingTab.overview && !overviewData) {
            return <MarketAnalysisSkeleton />;
        }
        if (errorTab.overview) {
            return <Alert message="错误" description={errorTab.overview} type="error" showIcon />;
        }
        if (!overviewData) return <Empty description="请输入股票代码开始分析" />;

        const CONFIDENCE_MAP = {
            'VERY_HIGH': '极高',
            'HIGH': '高',
            'MEDIUM': '中',
            'LOW': '低',
            'VERY_LOW': '极低',
            'low': '低',
            'medium': '中',
            'high': '高'
        };

        const translateConfidence = (conf) => CONFIDENCE_MAP[conf?.toUpperCase()] || conf;

        const getIndicatorColor = (status) => {
            if (status === 'bullish' || status === 'oversold') return '#52c41a';
            if (status === 'bearish' || status === 'overbought') return '#ff4d4f';
            return '#faad14';
        };

        const getIndicatorIcon = (status) => {
            if (status === 'bullish' || status === 'oversold') return <RiseOutlined />;
            if (status === 'bearish' || status === 'overbought') return <FallOutlined />;
            return <DashboardOutlined />;
        };

        const scoreExplanationContent = (
            <List
                size="small"
                dataSource={overviewData.score_explanation || []}
                renderItem={item => (
                    <List.Item style={{ padding: '8px 0' }}>
                        <div style={{ width: '100%' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <Text strong>{item.dimension}</Text>
                                <Tag color={item.score >= 60 ? 'success' : item.score < 40 ? 'error' : 'warning'}>
                                    {item.score}分
                                </Tag>
                            </div>
                            <Text type="secondary" style={{ fontSize: '12px' }}>{item.reason}</Text>
                        </div>
                    </List.Item>
                )}
                style={{ width: 320 }}
            />
        );

        const recommendationReasonContent = (
            <div style={{ maxWidth: 300 }}>
                <Text strong>推荐理由:</Text>
                <ul style={{ paddingLeft: 20, margin: '8px 0 0 0', fontSize: '12px' }}>
                    {(overviewData.recommendation_reasons || []).map((r, i) => (
                        <li key={i}>{r}</li>
                    ))}
                </ul>
            </div>
        );

        return (
            <Row gutter={[16, 16]}>
                <Col xs={24} md={8}>
                    <Card variant="borderless">
                        <Popover
                            content={scoreExplanationContent}
                            title="评分详情 (点击查看)"
                            trigger="click"
                            placement="right"
                        >
                            <div style={{ cursor: 'pointer' }}>
                                {renderScoreGauge(overviewData.overall_score)}
                            </div>
                        </Popover>
                        <div style={{ textAlign: 'center', marginTop: 16 }}>
                            <Space direction="vertical">
                                <Text type="secondary">投资建议</Text>
                                <Tooltip title={overviewData.recommendation_reasons?.length ? recommendationReasonContent : ''}>
                                    {renderRecommendation(overviewData.recommendation)}
                                </Tooltip>
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                    置信度: {translateConfidence(overviewData.confidence)}
                                </Text>
                            </Space>
                        </div>
                    </Card>
                </Col>

                <Col xs={24} md={8}>
                    <Card title="维度评分" variant="borderless">
                        {renderRadarChart(overviewData.scores)}
                    </Card>
                </Col>

                <Col xs={24} md={8}>
                    <Card title="关键信号" variant="borderless">
                        <List
                            dataSource={overviewData.key_signals}
                            renderItem={item => (
                                <List.Item>
                                    <Space>
                                        <Tag color={item.importance === 'high' ? 'red' : 'blue'}>
                                            {item.type}
                                        </Tag>
                                        <Text>{item.signal}</Text>
                                    </Space>
                                </List.Item>
                            )}
                        />
                    </Card>
                </Col>

                {/* K线图 */}
                <Col span={24}>
                    <Card
                        title={<><LineChartOutlined /> K线图表</>}
                        variant="borderless"
                    >
                        <Suspense fallback={<div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>}>
                            <CandlestickChart symbol={symbol} embedMode />
                        </Suspense>
                    </Card>
                </Col>

                {/* 技术指标快照 */}
                <Col span={24}>
                    <Card
                        title={<><FundOutlined /> 技术指标快照</>}
                        variant="borderless"
                        extra={loadingTab.technical ? <Spin size="small" /> : null}
                    >
                        {loadingTab.technical && !technicalData ? (
                            <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
                        ) : technicalData ? (
                            <Row gutter={16}>
                                <Col xs={24} md={8}>
                                    <Card size="small" variant="outlined">
                                        <Statistic
                                            title="RSI (14)"
                                            value={technicalData.rsi?.value}
                                            precision={2}
                                            valueStyle={{ color: getIndicatorColor(technicalData.rsi?.status) }}
                                            prefix={getIndicatorIcon(technicalData.rsi?.status)}
                                        />
                                        <Text type="secondary" style={{ fontSize: 12 }}>{technicalData.rsi?.signal}</Text>
                                    </Card>
                                </Col>
                                <Col xs={24} md={8}>
                                    <Card size="small" variant="outlined">
                                        <Statistic
                                            title="MACD"
                                            value={technicalData.macd?.value ?? technicalData.macd?.histogram}
                                            formatter={() => formatDisplayNumber(technicalData.macd?.value ?? technicalData.macd?.histogram, 4)}
                                            valueStyle={{ color: getIndicatorColor(technicalData.macd?.status) }}
                                            prefix={getIndicatorIcon(technicalData.macd?.status)}
                                        />
                                        <Text type="secondary" style={{ fontSize: 12 }}>{technicalData.macd?.trend || ''}</Text>
                                    </Card>
                                </Col>
                                <Col xs={24} md={8}>
                                    <Card size="small" variant="outlined">
                                        <Statistic
                                            title="布林带位置"
                                            value={technicalData.bollinger?.bandwidth}
                                            precision={2}
                                            suffix="%"
                                            valueStyle={{ color: getIndicatorColor(technicalData.bollinger?.position === 'above_upper' ? 'overbought' : technicalData.bollinger?.position === 'below_lower' ? 'oversold' : 'neutral') }}
                                        />
                                        <Text type="secondary" style={{ fontSize: 12 }}>{technicalData.bollinger?.signal}</Text>
                                    </Card>
                                </Col>
                                {technicalData.overall && (
                                    <Col span={24} style={{ marginTop: 12 }}>
                                        <Alert
                                            message={`综合信号: ${technicalData.overall.signal === 'strong_buy' ? '强力买入' :
                                                technicalData.overall.signal === 'buy' || technicalData.overall.signal === 'bullish' ? '看涨' :
                                                    technicalData.overall.signal === 'strong_sell' ? '强力卖出' :
                                                        technicalData.overall.signal === 'sell' || technicalData.overall.signal === 'bearish' ? '看跌' :
                                                            technicalData.overall.signal === 'neutral' ? '中性' : '未知'
                                                }${technicalData.overall.description ? ' — ' + technicalData.overall.description : ''}`}
                                            type={
                                                (technicalData.overall.signal === 'bullish' || technicalData.overall.signal === 'buy' || technicalData.overall.signal === 'strong_buy') ? 'success' :
                                                    (technicalData.overall.signal === 'bearish' || technicalData.overall.signal === 'sell' || technicalData.overall.signal === 'strong_sell') ? 'error' : 'info'
                                            }
                                            showIcon
                                        />
                                    </Col>
                                )}
                            </Row>
                        ) : (
                            <Empty description="点击此处加载技术指标" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        )}
                    </Card>
                </Col>

                <Col span={24}>
                    <Card
                        title={<span><CalendarOutlined /> 重要事件</span>}
                        loading={!eventData && !!loadingTab.events}
                        style={{ marginTop: 0 }}
                    >
                        {(!eventData || (!eventData.earnings && !eventData.dividends && !eventData.news?.length)) ? (
                            <Empty description="暂无近期重要事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        ) : (
                            <List
                                grid={{ gutter: 16, xs: 1, sm: 2, md: 3 }}
                                dataSource={[
                                    {
                                        type: 'earnings',
                                        title: '下一财报日',
                                        icon: <DollarCircleOutlined style={{ color: '#1890ff', fontSize: 24 }} />,
                                        content: (
                                            <div>
                                                <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                                                    {eventData.earnings?.next_earnings || '未定'}
                                                </div>
                                                {eventData.earnings?.estimate_avg && (
                                                    <div style={{ fontSize: 12, color: '#666' }}>
                                                        预估EPS: ${eventData.earnings.estimate_avg}
                                                    </div>
                                                )}
                                            </div>
                                        )
                                    },
                                    eventData.dividends?.last_amount > 0 ? {
                                        type: 'dividend',
                                        title: '分红派息',
                                        icon: <BankOutlined style={{ color: '#52c41a', fontSize: 24 }} />,
                                        content: (
                                            <div>
                                                <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                                                    ${eventData.dividends.last_amount} (最近)
                                                </div>
                                                <div style={{ fontSize: 12, color: '#666' }}>
                                                    预计: {eventData.dividends.next_date_estimated || '未知'}
                                                </div>
                                            </div>
                                        )
                                    } : null,
                                    eventData.news && eventData.news.length > 0 ? {
                                        type: 'news',
                                        title: '最新动态',
                                        icon: <NotificationOutlined style={{ color: '#faad14', fontSize: 24 }} />,
                                        content: (
                                            <a
                                                href={eventData.news[0].link}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#1890ff' }}
                                                title={eventData.news[0].title}
                                            >
                                                {eventData.news[0].title}
                                            </a>
                                        )
                                    } : null
                                ].filter(Boolean)}
                                renderItem={item => (
                                    <List.Item>
                                        <Card size="small" variant="borderless">
                                            <List.Item.Meta
                                                avatar={item.icon}
                                                title={item.title}
                                                description={item.content}
                                            />
                                        </Card>
                                    </List.Item>
                                )}
                            />
                        )}
                    </Card>
                </Col>

                <Col span={24}>
                    {overviewData.risk_warnings && overviewData.risk_warnings.length > 0 && (
                        <Alert
                            message="风险提示"
                            description={
                                <ul style={{ paddingLeft: 20, margin: 0 }}>
                                    {overviewData.risk_warnings.map((w, i) => <li key={i}>{w}</li>)}
                                </ul>
                            }
                            type="warning"
                            showIcon
                            icon={<WarningOutlined />}
                        />
                    )}
                </Col>
            </Row>
        );
    }, [loadingTab.overview, loadingTab.technical, loadingTab.events, errorTab.overview, overviewData, technicalData, eventData, renderScoreGauge, renderRadarChart, renderRecommendation, symbol]);

    // 2. Trend Content
    const trendContent = useMemo(() => {
        if (loadingTab.trend && !trendData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.trend) {
            return <Alert message="错误" description={errorTab.trend} type="error" showIcon />;
        }
        if (!trendData) return <Empty description="暂无趋势数据" />;

        const trend_analysis = trendData.trend_analysis || trendData;
        const { multi_timeframe = {}, support_levels = [], resistance_levels = [] } = trend_analysis || {};

        const columns = [
            { title: '周期', dataIndex: 'period', key: 'period' },
            {
                title: '趋势',
                dataIndex: 'trend',
                key: 'trend',
                render: (text) => (
                    <Tag color={text === '上涨' ? 'red' : 'green'}>
                        {text === '上涨' ? <RiseOutlined /> : <FallOutlined />} {text}
                    </Tag>
                )
            },
            {
                title: '涨跌幅',
                dataIndex: 'change_percent',
                key: 'change_percent',
                render: (val) => (
                    <Text type={val > 0 ? 'danger' : 'success'}>
                        {val > 0 ? '+' : ''}{val}%
                    </Text>
                )
            }
        ];

        const timeFrameData = Object.values(multi_timeframe || {});

        return (
            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Card title="多周期趋势">
                        <Table
                            dataSource={timeFrameData}
                            columns={columns}
                            pagination={false}
                            rowKey="period"
                            size="small"
                        />
                    </Card>
                </Col>

                {/* 斐波那契回撤 */}
                {trend_analysis.fibonacci_levels && (
                    <Col xs={24} md={24}>
                        <Card
                            title={
                                <Space>
                                    斐波那契回撤
                                    <Tooltip title={
                                        <div>
                                            <p>斐波那契回撤用于识别潜在的支撑位和阻力位。</p>
                                            <p>• <b>0.236/0.382</b>: 强势回调，趋势可能延续。</p>
                                            <p>• <b>0.5/0.618</b>: 常见回调位，是关键的支撑/阻力区域。</p>
                                            <p>• <b>0.786</b>: 深度回调，趋势可能反转。</p>
                                        </div>
                                    }>
                                        <InfoCircleOutlined style={{ color: '#1890ff', cursor: 'pointer' }} />
                                    </Tooltip>
                                </Space>
                            }
                            variant="borderless"
                            className="analysis-card"
                        >
                            <Row gutter={24}>
                                <Col span={8}>
                                    <div style={{ marginBottom: 16 }}>
                                        <Tag color="blue" style={{ fontSize: '14px', padding: '5px' }}>
                                            当前: {trend_analysis.fibonacci_levels.current_position}
                                        </Tag>
                                        <div style={{ fontSize: '12px', color: '#666', marginTop: 12, lineHeight: '1.5' }}>
                                            基于近期高点 {trend_analysis.fibonacci_levels.high_price?.toFixed(2)} 和
                                            低点 {trend_analysis.fibonacci_levels.low_price?.toFixed(2)} 计算。
                                            <br />
                                            价格通常会在这些比率位置遇到支撑或阻力。
                                        </div>
                                    </div>
                                </Col>
                                <Col span={16}>
                                    <List
                                        grid={{ gutter: 16, column: 3 }}
                                        dataSource={Object.entries(trend_analysis.fibonacci_levels.levels).sort((a, b) => parseFloat(b[1]) - parseFloat(a[1]))}
                                        renderItem={([level, price]) => (
                                            <List.Item>
                                                <Card size="small" styles={{ body: { padding: '8px', background: trend_analysis.fibonacci_levels.nearest_level === level ? '#e6f7ff' : 'transparent' } }}>
                                                    <div style={{ fontSize: '12px', color: '#888' }}>
                                                        Fib {level}
                                                        {level === '0.618' && <span style={{ color: '#faad14', marginLeft: 4 }}>(黄金分割)</span>}
                                                        {level === '0.5' && <span style={{ color: '#52c41a', marginLeft: 4 }}>(中轴)</span>}
                                                    </div>
                                                    <div style={{
                                                        fontWeight: trend_analysis.fibonacci_levels.nearest_level === level ? 'bold' : 'normal',
                                                        color: trend_analysis.fibonacci_levels.nearest_level === level ? '#1890ff' : 'inherit',
                                                        fontSize: '16px'
                                                    }}>
                                                        {price.toFixed(2)}
                                                    </div>
                                                </Card>
                                            </List.Item>
                                        )}
                                    />
                                </Col>
                            </Row>
                        </Card>
                    </Col>
                )}

                <Col span={12}>
                    <Card title="支撑位">
                        <List
                            dataSource={support_levels}
                            renderItem={level => (
                                <List.Item>
                                    <Text type="success" strong>{level}</Text>
                                </List.Item>
                            )}
                        />
                    </Card>
                </Col>
                <Col span={12}>
                    <Card title="阻力位">
                        <List
                            dataSource={resistance_levels}
                            renderItem={level => (
                                <List.Item>
                                    <Text type="danger" strong>{level}</Text>
                                </List.Item>
                            )}
                        />
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.trend, errorTab.trend, trendData]);

    // 3. Volume Content
    const volumeContent = useMemo(() => {
        if (loadingTab.volume && !volumeData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.volume) {
            return <Alert message="错误" description={errorTab.volume} type="error" showIcon />;
        }
        if (!volumeData) return <Empty description="暂无量价数据" />;

        const volume_analysis = volumeData.volume_analysis || volumeData;
        if (!volume_analysis) return <Empty description="暂无量价数据" />;

        const {
            volume_trend: rawVolumeTrend = {},
            money_flow = { mfi: null, status: 'neutral' },
            volume_patterns = { patterns: [] },
            obv_analysis = {}
        } = volume_analysis || {};

        const volumeTrend = normalizeVolumeTrend(rawVolumeTrend);
        const mfiValue = money_flow.mfi === null || money_flow.mfi === undefined || Number.isNaN(Number(money_flow.mfi))
            ? null
            : Number(money_flow.mfi);
        const flowStatus = money_flow.status || 'neutral';
        const mfiColor = mfiValue === null ? '#94a3b8' : (mfiValue > 80 ? '#ff3030' : mfiValue < 20 ? '#00b578' : '#1890ff');

        const VOLUME_TREND_MAP = {
            'shrinking': '缩量',
            'expanding': '放量',
            'stable': '平稳',
            'explosive': '爆量',
            'increasing': '放量',
            'normal': '正常',
            'extremely_low': '地量',
            'extremely_high': '天量'
        };

        return (
            <Row gutter={[16, 16]}>
                <Col xs={24} md={8}>
                    <Card title="量能趋势">
                        <Statistic
                            title="当前成交量趋势"
                            value={VOLUME_TREND_MAP[volumeTrend.trend] || volumeTrend.trend || '数据不足'}
                            valueStyle={{ color: volumeTrend.direction === 'expanding' ? '#ff3030' : '#00b578' }}
                            prefix={volumeTrend.direction === 'expanding' ? <RiseOutlined /> : <FallOutlined />}
                        />
                        <div style={{ marginTop: 10 }}>
                            <Text type="secondary">相对20日均量: </Text>
                            <Text strong>{formatDisplayNumber(volumeTrend.volume_ratio, 2, 'x')}</Text>
                        </div>
                    </Card>
                </Col>

                {/* 筹码分布 */}
                {volume_analysis.vpvr_analysis && (
                    <Col xs={24} md={24}>
                        <Card title="筹码分布 (VPVR)" variant="borderless" className="analysis-card">
                            <Row gutter={24}>
                                <Col span={6}>
                                    <Statistic title="控制点 (POC)" value={volume_analysis.vpvr_analysis.poc} prefix="$" />
                                    <div style={{ marginTop: 8 }}>
                                        <Tag color="gold">成交密集区</Tag>
                                    </div>
                                </Col>
                                <Col span={6}>
                                    <Statistic title="价值区域上沿 (VAH)" value={volume_analysis.vpvr_analysis.vah} prefix="$" />
                                </Col>
                                <Col span={6}>
                                    <Statistic title="价值区域下沿 (VAL)" value={volume_analysis.vpvr_analysis.val} prefix="$" />
                                </Col>
                                <Col span={6}>
                                    <Statistic title="总成交量" value={volume_analysis.vpvr_analysis.total_volume} formatter={(v) => new Intl.NumberFormat('en-US', { notation: "compact" }).format(v)} />
                                </Col>
                            </Row>
                            <div style={{ height: 250, marginTop: 24 }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={volume_analysis.vpvr_analysis.profile} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                        <XAxis dataKey="price_start" tickFormatter={(val) => val.toFixed(0)} />
                                        <YAxis hide />
                                        <RechartsTooltip
                                            formatter={(value) => new Intl.NumberFormat('en-US', { notation: "compact" }).format(value)}
                                            labelFormatter={(label) => `价格: ${label}`}
                                        />
                                        <Bar dataKey="volume" fill="#8884d8" barSize={20}>
                                            {
                                                volume_analysis.vpvr_analysis.profile.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.is_poc ? '#faad14' : (entry.in_value_area ? '#1890ff' : '#e6f7ff')} />
                                                ))
                                            }
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </Card>
                    </Col>
                )}
                <Col xs={24} md={8}>
                    <Card title="资金流向 (MFI)">
                        <div style={{ textAlign: 'center' }}>
                            <Progress
                                type="circle"
                                percent={mfiValue ?? 0}
                                format={() => (mfiValue === null ? DISPLAY_EMPTY : `${mfiValue}`)}
                                strokeColor={mfiColor}
                                size={120}
                            />
                            <div style={{ marginTop: 10 }}>
                                <Tag color={flowStatus === 'strong_inflow' ? 'red' : flowStatus.includes('outflow') ? 'green' : 'default'}>
                                    {flowStatus === 'strong_inflow' ? '强力流入' :
                                        flowStatus === 'inflow' ? '资金流入' :
                                            flowStatus === 'strong_outflow' ? '强力流出' :
                                                flowStatus === 'outflow' ? '资金流出' : '平衡'}
                                </Tag>
                            </div>
                        </div>
                    </Card>
                </Col>
                <Col xs={24} md={8}>
                    <Card title="能量潮 (OBV)">
                        <Statistic
                            title="OBV 趋势"
                            value={obv_analysis.obv_trend === 'bullish' ? '看涨' : obv_analysis.obv_trend === 'bearish' ? '看跌' : '中性'}
                            valueStyle={{ color: obv_analysis.obv_trend === 'bullish' ? '#ff3030' : '#00b578' }}
                        />
                        <div style={{ marginTop: 10 }}>
                            <Text>20日变化率: </Text>
                            <Text type={obv_analysis.obv_change_20d > 0 ? 'danger' : 'success'}>
                                {formatDisplayPercent(obv_analysis.obv_change_20d)}
                            </Text>
                        </div>
                    </Card>
                </Col>
                <Col span={24}>
                    <Card title="量价形态">
                        <List
                            grid={{ gutter: 16, column: 2 }}
                            dataSource={volume_patterns.patterns}
                            renderItem={item => (
                                <List.Item>
                                    <Alert
                                        message={item.description}
                                        type={item.signal === 'bullish' || item.signal === 'potential_bottom' ? 'success' : 'warning'}
                                        showIcon
                                    />
                                </List.Item>
                            )}
                            locale={{ emptyText: '未识别到明显量价形态' }}
                        />
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.volume, errorTab.volume, volumeData]);

    // 4. Sentiment Content
    const sentimentContent = useMemo(() => {
        if (loadingTab.sentiment && !sentimentData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.sentiment) {
            return <Alert message="错误" description={errorTab.sentiment} type="error" showIcon />;
        }
        if (!sentimentData) return <Empty description="暂无情绪数据" />;

        const sentiment_analysis = sentimentData.sentiment_analysis || sentimentData;
        if (!sentiment_analysis) return <Empty description="暂无情绪数据" />;

        const {
            fear_greed_index = 50,
            overall_sentiment = 'neutral',
            volatility_sentiment = {},
            risk_level = 'medium'
        } = sentiment_analysis || {};

        // Fear & Greed color
        const fgColor = fear_greed_index > 75 ? '#ff3030' : fear_greed_index < 25 ? '#00b578' : '#faad14';

        const VOLATILITY_MAP = {
            'stable': '稳定',
            'volatile': '波动',
            'very_volatile': '剧烈波动',
            'complacent': '低波动',
            'panic': '恐慌',
            'fear': '恐惧',
            'calm': '平静',
            'neutral': '中性'
        };

        const VOLATILITY_TREND_MAP = {
            'stable': '稳定',
            'increasing': '上升',
            'decreasing': '下降'
        };

        return (
            <Row gutter={[16, 16]}>
                <Col xs={24} md={12}>
                    <Card title="恐慌与贪婪指数">
                        <div style={{ textAlign: 'center', marginBottom: 20 }}>
                            <Progress
                                percent={fear_greed_index}
                                showInfo={false}
                                strokeColor={{
                                    '0%': '#00b578',
                                    '50%': '#faad14',
                                    '100%': '#ff3030',
                                }}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
                                <Text type="success">极度恐慌 (0)</Text>
                                <Text type="danger">极度贪婪 (100)</Text>
                            </div>
                            <Title level={2} style={{ margin: '10px 0', color: fgColor }}>
                                {fear_greed_index}
                            </Title>
                            <Tag color={fgColor} style={{ fontSize: '14px' }}>
                                {overall_sentiment === 'fear' ? '恐慌' :
                                    overall_sentiment === 'extreme_fear' ? '极度恐慌' :
                                        overall_sentiment === 'greed' ? '贪婪' :
                                            overall_sentiment === 'extreme_greed' ? '极度贪婪' : '中性'}
                            </Tag>
                        </div>
                    </Card>
                </Col>
                <Col xs={24} md={12}>
                    <Card title="风险概览">
                        <Row gutter={[16, 16]}>
                            <Col span={12}>
                                <Statistic
                                    title="风险等级"
                                    value={risk_level === 'low' ? '低' : risk_level === 'medium' ? '中' : risk_level === 'high' ? '高' : risk_level === 'very_high' ? '极高' : risk_level}
                                    prefix={<WarningOutlined />}
                                    valueStyle={{ color: risk_level === 'high' || risk_level === 'very_high' ? '#ff3030' : '#faad14' }}
                                />
                            </Col>
                            <Col span={12}>
                                <Statistic
                                    title="波动率状态"
                                    value={VOLATILITY_MAP[volatility_sentiment.sentiment] || volatility_sentiment.sentiment}
                                    prefix={<ThunderboltOutlined />}
                                />
                            </Col>
                        </Row>
                        <Divider />
                        <div style={{ marginTop: 10 }}>
                            <Text>当前波动率: {volatility_sentiment.historical_volatility}%</Text>
                            <br />
                            <Text type="secondary">波动率趋势: {VOLATILITY_TREND_MAP[volatility_sentiment.volatility_trend] || volatility_sentiment.volatility_trend}</Text>
                        </div>
                    </Card>
                </Col>

                {/* 历史情绪趋势 */}
                <Col span={24}>
                    <Card
                        title={<><LineChartOutlined /> 历史情绪趋势 (30天)</>}
                        extra={loadingTab.sentimentHistory ? <Spin size="small" /> : null}
                    >
                        {loadingTab.sentimentHistory && !sentimentHistoryData ? (
                            <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                        ) : sentimentHistoryData && sentimentHistoryData.history ? (
                            <ResponsiveContainer width="100%" height={300}>
                                <LineChart data={sentimentHistoryData.history}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                    <YAxis domain={[0, 100]} />
                                    <RechartsTooltip
                                        formatter={(value) => [`${value}`, '恐慌贪婪指数']}
                                        labelFormatter={(label) => `日期: ${label}`}
                                    />
                                    <Line
                                        type="monotone"
                                        dataKey="fear_greed_index"
                                        stroke="#1890ff"
                                        strokeWidth={2}
                                        dot={{ r: 3 }}
                                        activeDot={{ r: 6 }}
                                    />
                                    {/* 参考线 */}
                                    <ReferenceLine y={75} stroke="#ff3030" strokeDasharray="5 5" label={{ value: '贪婪', fill: '#ff3030', fontSize: 11 }} />
                                    <ReferenceLine y={25} stroke="#00b578" strokeDasharray="5 5" label={{ value: '恐惧', fill: '#00b578', fontSize: 11 }} />
                                </LineChart>
                            </ResponsiveContainer>
                        ) : (
                            <Empty description="暂无历史情绪数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        )}
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.sentiment, loadingTab.sentimentHistory, errorTab.sentiment, sentimentData, sentimentHistoryData]);

    // 5. Pattern Content
    const patternContent = useMemo(() => {
        if (loadingTab.pattern && !patternData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.pattern) {
            return <Alert message="错误" description={errorTab.pattern} type="error" showIcon />;
        }
        if (!patternData) return <Empty description="暂无形态数据" />;

        const pattern_analysis = patternData.pattern_analysis || patternData;
        if (!pattern_analysis) return <Empty description="暂无形态数据" />;

        const klines = klinesData || [];
        const { candlestick_patterns, chart_patterns } = pattern_analysis;
        const patterns = chart_patterns || [];
        const candlestickPatterns = candlestick_patterns || [];

        // 辅助翻译映射
        const RELIABILITY_MAP = {
            'high': '高',
            'medium': '中',
            'low': '低',
            'very_high': '极高',
            'High': '高',
            'Medium': '中',
            'Low': '低',
            'Very High': '极高'
        };

        // 过滤掉不在当前K线范围内的形态
        const startDate = klines && klines.length > 0 ? new Date(klines[0].date) : new Date(0);

        const validPatterns = patterns.filter(p => {
            if (!p.points) return false;
            // 只要有一个点在范围内就显示
            return p.points.some(pt => new Date(pt.date) >= startDate);
        });

        const SIGNAL_MAP = {
            'bullish': '看涨',
            'bearish': '看跌',
            'bullish_reversal': '看涨反转',
            'bearish_reversal': '看跌反转',
            'bullish_continuation': '看涨持续',
            'bearish_continuation': '看跌持续',
            'consolidation': '整理',
            'reversal': '反转',
            'neutral': '中性',
        };

        const POINT_TYPE_MAP = {
            'peak1': '顶1', 'peak2': '顶2', 'peak': '顶部',
            'trough': '谷底', 'trough1': '谷1', 'trough2': '谷2',
            'neckline': '颈线', 'head': '头部',
            'left_shoulder': '左肩', 'right_shoulder': '右肩',
            'support': '支撑', 'resistance': '阻力',
            'breakout': '突破', 'bottom': '底部',
            'bottom1': '底1', 'bottom2': '底2',
            'top': '顶', 'start': '起点', 'end': '终点',
        };

        const translateSignal = (sig) => SIGNAL_MAP[sig?.toLowerCase?.()] || SIGNAL_MAP[sig] || sig;
        const translateReliability = (rel) => RELIABILITY_MAP[rel] || rel;
        const translatePointType = (type) => POINT_TYPE_MAP[type?.toLowerCase?.()] || POINT_TYPE_MAP[type] || type;

        // 将所有形态的点合并用于 Scatter 显示
        const patternMap = new Map();
        validPatterns.forEach(p => {
            (p.points || []).forEach(pt => {
                patternMap.set(pt.date, {
                    ...pt,
                    patternName: p.name,
                    color: p.signal.includes('bullish') ? '#52c41a' : '#f5222d'
                });
            });
        });

        // 合并 pattern 数据到 klines 主数据
        const combinedData = (klines || []).map(k => ({
            ...k,
            patternPoint: patternMap.has(k.date) ? patternMap.get(k.date).price : null,
            patternMeta: patternMap.get(k.date)
        }));

        return (
            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Card title="形态可视化" variant="borderless">
                        {klines && klines.length > 0 ? (
                            <div style={{ width: '100%', height: 400 }}>
                                <ResponsiveContainer>
                                    <ComposedChart data={combinedData}>
                                        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                                        <XAxis
                                            dataKey="date"
                                            minTickGap={30}
                                            tickFormatter={tick => tick.slice(5)}
                                        />
                                        <YAxis domain={['auto', 'auto']} />
                                        <RechartsTooltip
                                            labelFormatter={label => `日期: ${label}`}
                                            formatter={(value, name) => [value, name === 'close' ? '收盘价' : name]}
                                        />
                                        <Line
                                            data={combinedData}
                                            type="monotone"
                                            dataKey="close"
                                            stroke="#1890ff"
                                            dot={false}
                                            strokeWidth={2}
                                            name="close"
                                            isAnimationActive={false}
                                            connectNulls
                                        />

                                        {/* 绘制形态的关键点 */}
                                        <Scatter
                                            dataKey="patternPoint"
                                            fill="#8884d8"
                                            name="形态关键点"
                                            shape={(props) => {
                                                const { cx, cy, payload } = props;
                                                // payload is the data item (kline + patternMeta)
                                                if (!payload.patternMeta) return null;

                                                return (
                                                    <g>
                                                        <circle cx={cx} cy={cy} r={6} fill={payload.patternMeta.color} stroke="#fff" strokeWidth={2} />
                                                        <text x={cx} y={cy - 10} textAnchor="middle" fill={payload.patternMeta.color} fontSize={10}>
                                                            {translatePointType(payload.patternMeta.type)}
                                                        </text>
                                                    </g>
                                                );
                                            }}
                                        />

                                        {/* 可选：用参考区域高亮形态出现的区间 */}
                                        {validPatterns.map((p, idx) => {
                                            if (!p.points || p.points.length < 2) return null;
                                            const start = p.points[0].date;
                                            const end = p.points[p.points.length - 1].date;
                                            return (
                                                <ReferenceArea
                                                    key={idx}
                                                    x1={start}
                                                    x2={end}
                                                    strokeOpacity={0.3}
                                                    fill={p.signal.includes('bullish') ? '#52c41a' : '#f5222d'}
                                                    fillOpacity={0.1}
                                                />
                                            );
                                        })}
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        ) : (
                            <Empty description="暂无K线数据用于绘图" />
                        )}
                    </Card>
                </Col>

                <Col span={24}>
                    <Card title="识别到的图表形态" className="glass-card">
                        <List
                            itemLayout="horizontal"
                            dataSource={validPatterns}
                            renderItem={item => (
                                <List.Item>
                                    <List.Item.Meta
                                        avatar={
                                            item.signal.includes('bullish') ?
                                                <RiseOutlined style={{ color: '#52c41a', fontSize: 24 }} /> :
                                                <FallOutlined style={{ color: '#f5222d', fontSize: 24 }} />
                                        }
                                        title={<Text strong>{item.name}</Text>}
                                        description={
                                            <Space direction="vertical" size={0}>
                                                <Text type="secondary">{item.description}</Text>
                                                <Space>
                                                    <Tag color={item.signal.includes('bullish') ? 'success' : 'error'}>
                                                        {translateSignal(item.signal)}
                                                    </Tag>
                                                    <Tag>{translateReliability(item.reliability)} 可靠性</Tag>
                                                </Space>
                                            </Space>
                                        }
                                    />
                                </List.Item>
                            )}
                            locale={{ emptyText: '近期未识别到明显图表形态' }}
                        />
                    </Card>
                </Col>
                <Col span={24}>
                    <Card title="识别到的K线形态">
                        <List
                            grid={{ gutter: 16, column: 3 }}
                            dataSource={candlestickPatterns.length > 0 ? candlestickPatterns : []}
                            renderItem={item => (
                                <List.Item>
                                    <Card
                                        size="small"
                                        title={item.name}
                                        extra={<Tag color={item.signal.includes('bullish') ? 'red' : 'green'}>{translateSignal(item.signal)}</Tag>}
                                    >
                                        <p>{item.description}</p>
                                        <Text type="secondary" style={{ fontSize: '12px' }}>可靠性: {translateReliability(item.reliability)}</Text>
                                        <br />
                                        <Text type="secondary" style={{ fontSize: '12px' }}>日期: {new Date(item.date).toLocaleDateString()}</Text>
                                    </Card>
                                </List.Item>
                            )}
                            locale={{ emptyText: '近期未识别到K线形态' }}
                        />
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.pattern, errorTab.pattern, patternData, klinesData]);

    // 6. Fundamental Content
    const fundamentalContent = useMemo(() => {
        if (loadingTab.fundamental && !fundamentalData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.fundamental) {
            return <Alert message="错误" description={errorTab.fundamental} type="error" showIcon />;
        }
        if (!fundamentalData) return <Empty description="暂无基本面数据" />;

        const fundamental_analysis = fundamentalData.fundamental_analysis || fundamentalData;
        if (!fundamental_analysis) return <Empty description="暂无基本面数据" />;

        const { metrics, valuation, financial_health, growth, summary } = fundamental_analysis;

        const formatLargeNumber = (num) => {
            if (!num) return DISPLAY_EMPTY;
            if (num > 1e12) return (num / 1e12).toFixed(2) + '万亿';
            if (num > 1e8) return (num / 1e8).toFixed(2) + '亿';
            return num.toLocaleString();
        };

        const FUNDAMENTAL_STATUS_MAP = {
            'fair_value': '合理估值', 'undervalued': '低估', 'overvalued': '高估',
            'stable': '稳定', 'moderate': '适中', 'strong': '强劲', 'weak': '弱',
            'healthy': '健康', 'unhealthy': '不健康',
            'high_growth': '高增长', 'low_growth': '低增长', 'negative_growth': '负增长',
            'good': '良好', 'poor': '较差', 'excellent': '优秀',
        };

        const ANALYST_RATING_MAP = {
            'strong_buy': '强力买入', 'buy': '买入', 'hold': '持有',
            'sell': '卖出', 'strong_sell': '强力卖出',
            'outperform': '跑赢大盘', 'underperform': '跑输大盘',
        };

        const translateStatus = (s) => FUNDAMENTAL_STATUS_MAP[s?.toLowerCase?.()] || s;
        const translateRating = (r) => ANALYST_RATING_MAP[r?.toLowerCase?.()?.replace(/\s+/g, '_')] || r;

        const renderScore = (item) => {
            if (!item) return null;
            let color = '#faad14';
            if (item.score >= 70) color = '#52c41a';
            if (item.score <= 30) color = '#ff4d4f';
            return <Tag color={color} style={{ marginLeft: 8 }}>{translateStatus(item.status)}</Tag>;
        };

        return (
            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Alert
                        message="基本面概览"
                        description={summary}
                        type="info"
                        showIcon
                        icon={<SolutionOutlined />}
                        style={{ marginBottom: 16 }}
                    />
                </Col>

                <Col xs={24} md={8}>
                    <Card title="估值指标" extra={renderScore(valuation)}>
                        <Statistic title="市盈率 (PE)" value={formatDisplayNumber(metrics.pe_ratio)} suffix={metrics.pe_ratio !== null && metrics.pe_ratio !== undefined ? 'x' : ''} />
                        <div style={{ marginTop: 16 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <Text type="secondary">PEG:</Text>
                                <Text>{formatDisplayNumber(metrics.peg_ratio)}</Text>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                                <Text type="secondary">市净率 (PB):</Text>
                                <Text>{formatDisplayNumber(metrics.price_to_book)}</Text>
                            </div>
                        </div>
                    </Card>
                </Col>

                <Col xs={24} md={8}>
                    <Card title="财务健康" extra={renderScore(financial_health)}>
                        <Statistic title="流动比率" value={formatDisplayNumber(metrics.current_ratio)} />
                        <div style={{ marginTop: 16 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <Text type="secondary">负债权益比:</Text>
                                <Text>{formatDisplayPercent(metrics.debt_to_equity)}</Text>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                                <Text type="secondary">利润率:</Text>
                                <Text>{formatDisplayPercent(metrics.profit_margin, 2, true)}</Text>
                            </div>
                        </div>
                    </Card>
                </Col>

                <Col xs={24} md={8}>
                    <Card title="增长能力" extra={renderScore(growth)}>
                        <Statistic
                            title="营收增长"
                            value={metrics.revenue_growth !== null && metrics.revenue_growth !== undefined ? Number((metrics.revenue_growth * 100).toFixed(2)) : undefined}
                            precision={2}
                            valueStyle={{ color: metrics.revenue_growth > 0 ? '#3f8600' : '#cf1322' }}
                            prefix={metrics.revenue_growth > 0 ? <RiseOutlined /> : <FallOutlined />}
                            suffix="%"
                        />
                        <div style={{ marginTop: 16 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <Text type="secondary">盈利增长:</Text>
                                <Text type={metrics.earnings_growth > 0 ? 'success' : 'danger'}>
                                    {formatDisplayPercent(metrics.earnings_growth, 2, true)}
                                </Text>
                            </div>
                        </div>
                    </Card>
                </Col>

                <Col span={24}>
                    <Card title="公司信息">
                        <Row gutter={[24, 24]}>
                            <Col span={8}>
                                <Statistic title="总市值" value={formatLargeNumber(metrics.market_cap)} />
                            </Col>
                            <Col span={8}>
                                <div className="ant-statistic-title">所属板块</div>
                                <div className="ant-statistic-content" style={{ fontSize: 20 }}>{metrics.sector || DISPLAY_EMPTY}</div>
                            </Col>
                            <Col span={8}>
                                <div className="ant-statistic-title">行业</div>
                                <div className="ant-statistic-content" style={{ fontSize: 20 }}>{metrics.industry || DISPLAY_EMPTY}</div>
                            </Col>
                            <Col span={8}>
                                <div className="ant-statistic-title">分析师评级</div>
                                <div className="ant-statistic-content" style={{ fontSize: 20 }}>
                                    {metrics.analyst_rating ? translateRating(metrics.analyst_rating) : DISPLAY_EMPTY}
                                </div>
                            </Col>
                            <Col span={8}>
                                <Statistic title="目标价" value={metrics.target_price} prefix="$" precision={2} />
                            </Col>
                            <Col span={8}>
                                <Statistic title="52周最高" value={metrics['52w_high']} prefix="$" precision={2} />
                            </Col>
                        </Row>
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.fundamental, errorTab.fundamental, fundamentalData]);

    // 7. Industry Comparison Content
    const industryContent = useMemo(() => {
        if (loadingTab.industry && !industryData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.industry) {
            return <Alert message="错误" description={errorTab.industry} type="error" showIcon />;
        }
        if (!industryData) return <Empty description="暂无行业对比数据" />;

        const { target, peers, industry_avg, industry, sector } = industryData;

        const columns = [
            { title: '股票', dataIndex: 'symbol', key: 'symbol', render: (t, r) => <Text strong={r.symbol === target?.symbol}>{t}</Text> },
            { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
            { title: 'PE', dataIndex: 'pe_ratio', key: 'pe_ratio', render: v => formatDisplayNumber(v) },
            { title: '营收增长', dataIndex: 'revenue_growth', key: 'revenue_growth', render: v => formatDisplayPercent(v) },
            { title: '利润率', dataIndex: 'profit_margin', key: 'profit_margin', render: v => formatDisplayPercent(v) },
        ];

        const tableData = target ? [target, ...(peers || [])] : (peers || []);

        return (
            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Alert
                        message={`行业: ${industry || DISPLAY_EMPTY} | 板块: ${sector || DISPLAY_EMPTY}`}
                        description={`${target?.symbol || DISPLAY_EMPTY} 在同行业中 PE 排名第 ${target?.pe_rank || DISPLAY_EMPTY} 位，增长排名第 ${target?.growth_rank || DISPLAY_EMPTY} 位`}
                        type="info"
                        showIcon
                        icon={<BankOutlined />}
                    />
                </Col>
                <Col xs={24} md={8}>
                    <Card title="行业均值">
                        <Statistic title="平均 PE" value={formatDisplayNumber(industry_avg?.pe_ratio)} />
                        <Statistic title="平均增长率" value={formatDisplayPercent(industry_avg?.revenue_growth)} style={{ marginTop: 16 }} />
                        <Statistic title="平均利润率" value={formatDisplayPercent(industry_avg?.profit_margin)} style={{ marginTop: 16 }} />
                    </Card>
                </Col>
                <Col xs={24} md={16}>
                    <Card title="同行业公司对比">
                        <Table
                            dataSource={tableData}
                            columns={columns}
                            rowKey="symbol"
                            pagination={false}
                            size="small"
                        />
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.industry, errorTab.industry, industryData]);

    // 8. Risk Metrics Content
    const riskContent = useMemo(() => {
        if (loadingTab.risk && !riskData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.risk) {
            return <Alert message="错误" description={errorTab.risk} type="error" showIcon />;
        }
        if (!riskData) return <Empty description="暂无风险评估数据" />;

        const riskLevelText = { very_high: '极高', high: '高', medium: '中等', low: '低', very_low: '极低' };

        return (
            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Alert
                        message={`风险等级: ${riskLevelText[riskData.risk_level] || riskData.risk_level}`}
                        description={riskData.risk_description}
                        type={riskData.risk_level === 'low' || riskData.risk_level === 'very_low' ? 'success' :
                            riskData.risk_level === 'medium' ? 'warning' : 'error'}
                        showIcon
                        icon={<DashboardOutlined />}
                    />
                </Col>
                <Col xs={24} md={8}>
                    <Card title="风险价值 (VaR)">
                        <Statistic
                            title="95% VaR (日度)"
                            value={riskData.var_95}
                            suffix="%"
                            valueStyle={{ color: riskData.var_95 < -5 ? '#ff4d4f' : '#faad14' }}
                        />
                        <Statistic
                            title="99% VaR (日度)"
                            value={riskData.var_99}
                            suffix="%"
                            style={{ marginTop: 16 }}
                            valueStyle={{ color: riskData.var_99 < -8 ? '#ff4d4f' : '#faad14' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} md={8}>
                    <Card title="回撤与波动">
                        <Statistic
                            title="最大回撤"
                            value={riskData.max_drawdown}
                            suffix="%"
                            valueStyle={{ color: riskData.max_drawdown < -30 ? '#ff4d4f' : '#faad14' }}
                        />
                        <Statistic
                            title="年化波动率"
                            value={riskData.annual_volatility}
                            suffix="%"
                            style={{ marginTop: 16 }}
                        />
                    </Card>
                </Col>
                <Col xs={24} md={8}>
                    <Card title="风险调整收益">
                        <Statistic
                            title="夏普比率"
                            value={riskData.sharpe_ratio}
                            valueStyle={{ color: riskData.sharpe_ratio > 1 ? '#52c41a' : riskData.sharpe_ratio < 0 ? '#ff4d4f' : '#faad14' }}
                        />
                        <Statistic
                            title="索提诺比率"
                            value={riskData.sortino_ratio}
                            style={{ marginTop: 16 }}
                            valueStyle={{ color: riskData.sortino_ratio > 1 ? '#52c41a' : '#faad14' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} md={12}>
                    <Card title="收益与Beta">
                        <Row gutter={16}>
                            <Col span={12}>
                                <Statistic
                                    title="年化收益率"
                                    value={riskData.annual_return}
                                    suffix="%"
                                    valueStyle={{ color: riskData.annual_return > 0 ? '#52c41a' : '#ff4d4f' }}
                                />
                            </Col>
                            <Col span={12}>
                                <Statistic title="Beta" value={riskData.beta} />
                            </Col>
                        </Row>
                    </Card>
                </Col>
                <Col xs={24} md={12}>
                    <Card title="最大回撤区间">
                        <Text>
                            从 {riskData.max_drawdown_period?.start || DISPLAY_EMPTY} 到 {riskData.max_drawdown_period?.end || DISPLAY_EMPTY}
                        </Text>
                        <div style={{ marginTop: 8 }}>
                            <Text type="secondary">分析数据点: {riskData.data_points ?? DISPLAY_EMPTY} 个</Text>
                        </div>
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.risk, errorTab.risk, riskData]);

    // 9. Correlation Content
    const correlationContent = useMemo(() => {
        if (loadingTab.correlation && !correlationData) {
            return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
        }
        if (errorTab.correlation) {
            return <Alert message="错误" description={errorTab.correlation} type="error" showIcon />;
        }
        if (!correlationData) return <Empty description="暂无相关性分析数据" />;

        // API 返回格式: { correlation_matrix: [{symbol1, symbol2, correlation}, ...], symbols: [...] }
        const rawMatrix = correlationData.correlation_matrix || [];
        const symbols = correlationData.symbols || [];

        // 构建相关性查找表
        const correlationMap = {};
        rawMatrix.forEach(item => {
            if (!correlationMap[item.symbol1]) correlationMap[item.symbol1] = {};
            correlationMap[item.symbol1][item.symbol2] = item.correlation;
        });

        const getCorrelationColor = (value) => {
            if (value === undefined || value === null) return '#d9d9d9';
            if (value >= 0.7) return '#52c41a';
            if (value >= 0.4) return '#faad14';
            if (value >= 0) return '#d9d9d9';
            if (value >= -0.4) return '#ffa39e';
            return '#ff4d4f';
        };

        const columns = [
            { title: '', dataIndex: 'symbol', key: 'symbol', fixed: 'left', width: 80 },
            ...symbols.map(s => ({
                title: s,
                dataIndex: s,
                key: s,
                width: 80,
                render: (v) => (
                    <div style={{
                        background: getCorrelationColor(v),
                        padding: '4px 8px',
                        borderRadius: 4,
                        textAlign: 'center',
                        color: Math.abs(v || 0) > 0.5 ? '#fff' : '#000'
                    }}>
                        {v !== undefined ? v.toFixed(2) : '-'}
                    </div>
                )
            }))
        ];

        const tableData = symbols.map(s1 => {
            const row = { symbol: s1 };
            symbols.forEach(s2 => {
                row[s2] = correlationMap[s1]?.[s2];
            });
            return row;
        });

        return (
            <Row gutter={[16, 16]}>
                <Col span={24}>
                    <Alert
                        message="股票相关性分析"
                        description="显示选定股票之间的价格走势相关性。相关系数范围 -1 到 1，正值表示正相关，负值表示负相关。"
                        type="info"
                        showIcon
                        icon={<LineChartOutlined />}
                    />
                </Col>
                <Col span={24}>
                    <Card title="相关性矩阵">
                        <Table
                            dataSource={tableData}
                            columns={columns}
                            rowKey="symbol"
                            pagination={false}
                            scroll={{ x: 'max-content' }}
                            size="small"
                        />
                    </Card>
                </Col>
                <Col span={24}>
                    <Card title="相关性图例">
                        <Space>
                            <Tag color="#52c41a">强正相关 (≥0.7)</Tag>
                            <Tag color="#faad14">中等正相关 (0.4~0.7)</Tag>
                            <Tag color="#d9d9d9">弱相关 (0.0~0.4)</Tag>
                            <Tag color="#ffa39e">中等负相关 (-0.4~0)</Tag>
                            <Tag color="#ff4d4f">强负相关 (≤-0.4)</Tag>
                        </Space>
                    </Card>
                </Col>
            </Row>
        );
    }, [loadingTab.correlation, errorTab.correlation, correlationData]);

    // 资产类型识别与 Tab 可用性控制
    const getAssetType = (sym) => {
        if (!sym) return 'STOCK';
        if (sym.includes('-USD') || sym.includes('-USDT')) return 'CRYPTO';
        if (sym.includes('=F')) return 'FUTURE';
        if (sym.startsWith('^')) return 'INDEX';
        return 'STOCK';
    };

    const assetType = getAssetType(symbol);

    const isTabAvailable = (key) => {
        if (assetType === 'STOCK') return true;
        // 指数、加密货币和期货没有基本面和行业数据
        if (['fundamental', 'industry'].includes(key)) return false;
        return true;
    };

    const getTabTooltip = (key) => {
        if (isTabAvailable(key)) return '';
        if (assetType === 'CRYPTO') return '加密货币暂无此数据';
        if (assetType === 'FUTURE') return '期货暂无此数据';
        if (assetType === 'INDEX') return '指数类资产暂无此数据';
        return '暂无数据';
    };

    const tabItems = [
        {
            key: 'overview',
            label: <span><DashboardOutlined />总览</span>,
            children: overviewContent
        },
        {
            key: 'trend',
            label: <span><LineChartOutlined />趋势分析</span>,
            children: trendContent
        },
        {
            key: 'volume',
            label: <span><BarChartOutlined />量价分析</span>,
            children: volumeContent
        },
        {
            key: 'sentiment',
            label: <span><ExperimentOutlined />情绪分析</span>,
            children: sentimentContent
        },
        {
            key: 'pattern',
            label: <span><RadarChartOutlined />形态识别</span>,
            children: patternContent
        },
        {
            key: 'fundamental',
            label: (
                <Tooltip title={getTabTooltip('fundamental')}>
                    <span style={{ color: !isTabAvailable('fundamental') ? '#999' : undefined }}>
                        <SolutionOutlined />基本面分析
                    </span>
                </Tooltip>
            ),
            disabled: !isTabAvailable('fundamental'),
            children: fundamentalContent
        },
        {
            key: 'industry',
            label: (
                <Tooltip title={getTabTooltip('industry')}>
                    <span style={{ color: !isTabAvailable('industry') ? '#999' : undefined }}>
                        <BankOutlined />行业对比
                    </span>
                </Tooltip>
            ),
            disabled: !isTabAvailable('industry'),
            children: industryContent
        },
        {
            key: 'risk',
            label: <span><DashboardOutlined />风险评估</span>,
            children: riskContent
        },
        {
            key: 'correlation',
            label: <span><LineChartOutlined />相关性</span>,
            children: correlationContent
        },
        {
            key: 'prediction',
            label: <span><RobotOutlined />AI 预测</span>,
            children: (
                <Suspense fallback={<div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>}>
                    <AIPredictionPanel symbol={symbol} />
                </Suspense>
            )
        }
    ];

    return (
        <div className={embedMode ? 'market-analysis market-analysis--embed' : 'market-analysis'} style={{ maxWidth: '100%', overflow: 'hidden' }}>
            <div
                style={{
                    marginBottom: embedMode ? 16 : 20,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: embedMode ? 'flex-start' : 'center',
                    flexWrap: 'wrap',
                    gap: 12,
                }}
            >
                {embedMode ? (
                    <div className="market-analysis__embed-hero">
                        <div className="market-analysis__embed-eyebrow">Analysis Workspace</div>
                        <div className="market-analysis__embed-title-row">
                            <div className="market-analysis__embed-title">{symbol} 全维分析</div>
                            <Tag color="blue" style={{ borderRadius: 999, margin: 0, paddingInline: 10 }}>
                                {interval === '1d' ? '日线' : interval === '1wk' ? '周线' : interval === '1mo' ? '月线' : '4小时'}
                            </Tag>
                        </div>
                        <div className="market-analysis__embed-subtitle">
                            保留趋势、量价、情绪、形态、风险、相关性和 AI 预测分析，适合在实时详情弹窗内快速切换。
                        </div>
                        <div className="market-analysis__embed-meta">
                            <div className="market-analysis__embed-chip">当前标签 {activeTabLabel}</div>
                            {overviewData?.summary?.score !== undefined && (
                                <div className="market-analysis__embed-chip">综合评分 {overviewData.summary.score}</div>
                            )}
                            <div
                                className="market-analysis__embed-chip"
                                style={{
                                    color: activeMetaTone.color,
                                    background: activeMetaTone.background,
                                }}
                            >
                                数据来源 {activeMetaSourceLabel}
                            </div>
                            <div className="market-analysis__embed-chip">最近刷新 {activeMetaTimeLabel}</div>
                        </div>
                    </div>
                ) : (
                    <Title level={3}>全维市场分析</Title>
                )}

                <div className={embedMode ? 'market-analysis__controls market-analysis__controls--embed' : 'market-analysis__controls'}>
                    {!embedMode && (
                        <Search
                            placeholder="输入股票代码 (如: AAPL)"
                            allowClear
                            enterButton="分析"
                            size="large"
                            onSearch={handleSearch}
                            style={{ width: 300 }}
                            loading={!!loadingTab.overview}
                            defaultValue={symbol}
                        />
                    )}
                    <Radio.Group value={interval} onChange={handleIntervalChange} buttonStyle="solid" size={embedMode ? 'small' : 'middle'}>
                        <Radio.Button value="1d">日线</Radio.Button>
                        <Radio.Button value="1wk">周线</Radio.Button>
                        <Radio.Button value="1mo">月线</Radio.Button>
                        <Radio.Button value="4h">4小时</Radio.Button>
                    </Radio.Group>
                    <button
                        type="button"
                        onClick={handleRefreshAnalysis}
                        style={{
                            border: '1px solid var(--border-color)',
                            background: 'var(--bg-secondary)',
                            color: 'var(--text-primary)',
                            borderRadius: 999,
                            padding: embedMode ? '6px 12px' : '8px 14px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 8,
                            cursor: 'pointer',
                            fontWeight: 600,
                        }}
                    >
                        <ReloadOutlined />
                        刷新分析
                    </button>
                </div>
            </div>
            <div
                style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 10,
                    marginBottom: 14,
                    color: 'var(--text-secondary)',
                    fontSize: 13,
                }}
            >
                <span>当前分析：{activeTabLabel}</span>
                <span>数据来源：{activeMetaSourceLabel}</span>
                <span>最近刷新：{activeMetaTimeLabel}</span>
            </div>

            <div className={embedMode ? 'market-analysis__tabs-shell market-analysis__tabs-shell--embed' : 'market-analysis__tabs-shell'}>
                <Tabs
                    activeKey={activeTab}
                    onChange={handleTabChange}
                    type="card"
                    size={embedMode ? 'small' : 'middle'}
                    destroyOnHidden
                    items={tabItems}
                />
            </div>

            <style>{`
                .market-analysis__controls {
                    display: flex;
                    align-items: center;
                    margin-left: auto;
                    gap: 12px;
                    flex-wrap: wrap;
                }

                .market-analysis__embed-hero {
                    display: grid;
                    gap: 8px;
                    padding: 16px 18px;
                    border-radius: 20px;
                    background: linear-gradient(135deg, rgba(14, 165, 233, 0.10), rgba(59, 130, 246, 0.05));
                    border: 1px solid color-mix(in srgb, var(--accent-primary) 16%, var(--border-color) 84%);
                    max-width: min(100%, 720px);
                }

                .market-analysis__embed-eyebrow {
                    font-size: 11px;
                    letter-spacing: 0.16em;
                    text-transform: uppercase;
                    font-weight: 700;
                    color: var(--text-secondary);
                }

                .market-analysis__embed-title-row {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    flex-wrap: wrap;
                }

                .market-analysis__embed-title {
                    font-size: 20px;
                    font-weight: 800;
                    color: var(--text-primary);
                }

                .market-analysis__embed-subtitle {
                    font-size: 13px;
                    line-height: 1.7;
                    color: var(--text-secondary);
                }

                .market-analysis__embed-meta {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                }

                .market-analysis__embed-chip {
                    padding: 7px 12px;
                    border-radius: 999px;
                    font-size: 12px;
                    color: var(--text-secondary);
                    background: color-mix(in srgb, var(--bg-secondary) 86%, white 14%);
                    border: 1px solid var(--border-color);
                }

                .market-analysis__tabs-shell--embed .ant-tabs-nav {
                    margin-bottom: 18px;
                }

                .market-analysis__tabs-shell--embed .ant-tabs-tab {
                    border-radius: 999px !important;
                    padding-inline: 14px !important;
                }

                .market-analysis__tabs-shell--embed .ant-tabs-content-holder {
                    padding-top: 2px;
                }

                .market-analysis--embed .ant-card,
                .market-analysis--embed .analysis-card,
                .market-analysis--embed .glass-card {
                    border-radius: 22px;
                    border: 1px solid color-mix(in srgb, var(--border-color) 82%, white 18%);
                    box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
                    background: linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 92%, white 8%) 0%, var(--bg-secondary) 100%);
                }

                .market-analysis--embed .ant-card-head {
                    border-bottom: 1px solid color-mix(in srgb, var(--border-color) 84%, white 16%);
                    min-height: 54px;
                }

                .market-analysis--embed .ant-card-head-title {
                    font-weight: 700;
                    color: var(--text-primary);
                }

                .market-analysis--embed .ant-card-body {
                    padding: 18px;
                }

                .market-analysis--embed .ant-alert {
                    border-radius: 18px;
                    border: 1px solid color-mix(in srgb, var(--border-color) 82%, white 18%);
                    box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
                }

                .market-analysis--embed .ant-statistic {
                    padding: 14px 16px;
                    border-radius: 18px;
                    background: color-mix(in srgb, var(--bg-primary) 88%, white 12%);
                    border: 1px solid color-mix(in srgb, var(--border-color) 84%, white 16%);
                }

                .market-analysis--embed .ant-statistic-title {
                    color: var(--text-secondary);
                    font-size: 12px;
                }

                .market-analysis--embed .ant-statistic-content {
                    color: var(--text-primary);
                }

                .market-analysis--embed .ant-list-item {
                    border-color: color-mix(in srgb, var(--border-color) 84%, white 16%) !important;
                }

                .market-analysis--embed .ant-tag {
                    border-radius: 999px;
                }

                .market-analysis--embed .ant-table-wrapper {
                    border-radius: 18px;
                    overflow: hidden;
                    border: 1px solid color-mix(in srgb, var(--border-color) 84%, white 16%);
                    background: color-mix(in srgb, var(--bg-primary) 90%, white 10%);
                }

                .market-analysis--embed .ant-table-thead > tr > th {
                    background: color-mix(in srgb, var(--bg-secondary) 84%, white 16%);
                    color: var(--text-secondary);
                    font-size: 12px;
                    font-weight: 700;
                }

                .market-analysis--embed .ant-table-tbody > tr > td {
                    background: transparent;
                }

                .market-analysis--embed .ant-empty {
                    padding: 20px 0;
                }

                .market-analysis--embed .radar-chart-container {
                    border-radius: 18px;
                    background: color-mix(in srgb, var(--bg-primary) 88%, white 12%);
                    border: 1px solid color-mix(in srgb, var(--border-color) 84%, white 16%);
                    padding: 12px;
                }

                @media (max-width: 640px) {
                    .market-analysis__controls--embed {
                        width: 100%;
                        margin-left: 0;
                    }

                    .market-analysis__controls--embed .ant-radio-group {
                        width: 100%;
                        display: grid;
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }

                    .market-analysis__controls--embed .ant-radio-button-wrapper {
                        text-align: center;
                    }
                }
            `}</style>
        </div>
    );
};

export default MarketAnalysis;
