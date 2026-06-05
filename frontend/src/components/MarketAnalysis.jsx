import { useState, useEffect, useRef, useMemo, Suspense } from 'react';
import {
    Input,
    Tabs,
    Tag,
    Typography,
    Radio,
    Spin
} from 'antd';
import {
    RadarChartOutlined,
    BarChartOutlined,
    RobotOutlined,
    SolutionOutlined,
    ExperimentOutlined,
    LineChartOutlined,
    BankOutlined,
    DashboardOutlined,
    ReloadOutlined,
} from '@ant-design/icons';


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
import lazyWithRetry from '../utils/lazyWithRetry';
import { DEFAULT_SYMBOL, SYMBOL_PLACEHOLDER_BILINGUAL } from '../utils/strategyDefaults';
import OverviewTab from './market-analysis/OverviewTab';
import TrendTab from './market-analysis/TrendTab';
import VolumeTab from './market-analysis/VolumeTab';
import SentimentTab from './market-analysis/SentimentTab';
import PatternTab from './market-analysis/PatternTab';
import FundamentalTab from './market-analysis/FundamentalTab';
import IndustryTab from './market-analysis/IndustryTab';
import RiskTab from './market-analysis/RiskTab';
import CorrelationTab from './market-analysis/CorrelationTab';
import {
    buildAnalysisCacheKey,
    clearAnalysisCache,
    readAnalysisCacheEntry,
    writeAnalysisCache,
} from '../utils/marketAnalysisCache';
import {
    DISPLAY_EMPTY,
    formatMetaTime,
} from '../utils/marketAnalysisFormatters';

import { Tooltip } from 'antd'; // Careful, we have RechartsTooltip imported as well.

const { Title } = Typography;
const { Search } = Input;

const AIPredictionPanel = lazyWithRetry(() => import('./AIPredictionPanel'));
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

// Re-exported for backward compatibility with existing tests; new
// callers should import from utils directly.
export {
    ANALYSIS_CACHE_TTL_MS,
    ANALYSIS_CACHE_MAX_ENTRIES,
    __TEST_ONLY__,
} from '../utils/marketAnalysisCache';

const MarketAnalysis = ({ symbol: propSymbol, embedMode = false }) => {
    const [symbol, setSymbol] = useState(propSymbol || DEFAULT_SYMBOL);
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
            const defaultSymbols = [DEFAULT_SYMBOL, '000858.SZ', '300750.SZ', 'SPY', 'AAPL'];
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

    // renderScoreGauge / renderRecommendation / renderRadarChart 拆到
    // ./market-analysis/MarketAnalysisScoreVisuals.js（layer 2 子组件）

    // --- Tab Contents (Memoized) ---

    // 1. Overview Content
    const overviewContent = useMemo(() => (
        <OverviewTab
            symbol={symbol}
            loadingTab={loadingTab}
            errorTab={errorTab}
            overviewData={overviewData}
            technicalData={technicalData}
            eventData={eventData}
        />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.overview, loadingTab.technical, loadingTab.events, errorTab.overview, overviewData, technicalData, eventData, symbol]);

    // 2. Trend Content
    const trendContent = useMemo(() => (
        <TrendTab loadingTab={loadingTab} errorTab={errorTab} trendData={trendData} />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.trend, errorTab.trend, trendData]);

    // 3. Volume Content
    const volumeContent = useMemo(() => (
        <VolumeTab loadingTab={loadingTab} errorTab={errorTab} volumeData={volumeData} symbol={symbol} />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.volume, errorTab.volume, volumeData, symbol]);

    // 4. Sentiment Content
    const sentimentContent = useMemo(() => (
        <SentimentTab
            loadingTab={loadingTab}
            errorTab={errorTab}
            sentimentData={sentimentData}
            sentimentHistoryData={sentimentHistoryData}
        />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.sentiment, loadingTab.sentimentHistory, errorTab.sentiment, sentimentData, sentimentHistoryData]);

    // 5. Pattern Content
    const patternContent = useMemo(() => (
        <PatternTab loadingTab={loadingTab} errorTab={errorTab} patternData={patternData} klinesData={klinesData} />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.pattern, errorTab.pattern, patternData, klinesData]);

    // 6. Fundamental Content
    const fundamentalContent = useMemo(() => (
        <FundamentalTab loadingTab={loadingTab} errorTab={errorTab} fundamentalData={fundamentalData} symbol={symbol} />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.fundamental, errorTab.fundamental, fundamentalData, symbol]);

    // 7. Industry Comparison Content
    const industryContent = useMemo(() => (
        <IndustryTab loadingTab={loadingTab} errorTab={errorTab} industryData={industryData} />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.industry, errorTab.industry, industryData]);

    // 8. Risk Metrics Content
    const riskContent = useMemo(() => (
        <RiskTab loadingTab={loadingTab} errorTab={errorTab} riskData={riskData} />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.risk, errorTab.risk, riskData]);

    // 9. Correlation Content
    const correlationContent = useMemo(() => (
        <CorrelationTab loadingTab={loadingTab} errorTab={errorTab} correlationData={correlationData} />
        // eslint-disable-next-line react-hooks/exhaustive-deps
    ), [loadingTab.correlation, errorTab.correlation, correlationData]);

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
                        <div className="market-analysis__embed-eyebrow">分析工作台</div>
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
                            placeholder={`输入股票代码 (如: ${SYMBOL_PLACEHOLDER_BILINGUAL})`}
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
