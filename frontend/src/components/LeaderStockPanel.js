import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
    Card,
    Table,
    Empty,
    Tag,
    Button,
    Tooltip,
    Tabs
} from 'antd';
import {
    CrownOutlined,
    ReloadOutlined
} from '@ant-design/icons';
import { getLeaderStocks, getLeaderDetail, getIndustryTrend } from '../services/api';
import StockDetailModal from './StockDetailModal';
import MiniSparkline from './common/MiniSparkline';
import { useSafeMessageApi } from '../utils/messageApi';

const averageOf = (items, selector) => {
    const values = items
        .map(selector)
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value));
    if (values.length === 0) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
};

const averageDimensionScores = (items, keys) => keys.reduce((result, key) => {
    const average = averageOf(items, (item) => item?.dimension_scores?.[key]);
    if (average != null) {
        result[key] = average;
    }
    return result;
}, {});

const buildLeaderFallbackTrend = (record) => {
    const change = Number(record?.change_pct || 0);
    const cappedChange = Math.max(-8, Math.min(8, change));
    const endPoint = 100 + cappedChange;
    return [
        100 - cappedChange * 0.45,
        100 - cappedChange * 0.2,
        100 + cappedChange * 0.08,
        100 + cappedChange * 0.38,
        100 + cappedChange * 0.72,
        endPoint,
    ];
};

const renderLeaderLoadingScaffold = (accentColor, title, subtitle) => (
    <div
        style={{
            borderRadius: 12,
            border: `1px solid color-mix(in srgb, ${accentColor} 16%, var(--border-color) 84%)`,
            background: `linear-gradient(180deg, color-mix(in srgb, ${accentColor} 7%, var(--bg-secondary) 93%) 0%, color-mix(in srgb, var(--bg-secondary) 98%, var(--bg-primary) 2%) 100%)`,
            padding: '12px 12px 8px',
        }}
    >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{subtitle}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[0, 1, 2, 3].map((item) => (
                <div
                    key={item}
                    style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 72px',
                        gap: 12,
                        alignItems: 'center',
                        padding: '10px 12px',
                        borderRadius: 10,
                        background: 'color-mix(in srgb, var(--bg-primary) 18%, transparent)',
                        border: '1px solid color-mix(in srgb, var(--border-color) 88%, transparent 12%)',
                    }}
                >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <div style={{ width: `${72 - item * 7}%`, height: 10, borderRadius: 999, background: 'rgba(255,255,255,0.12)' }} />
                        <div style={{ width: `${46 - item * 4}%`, height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.08)' }} />
                    </div>
                    <div style={{ width: '100%', height: 28, borderRadius: 999, background: `color-mix(in srgb, ${accentColor} 18%, transparent)` }} />
                </div>
            ))}
        </div>
    </div>
);

/**
 * 龙头股面板组件
 * 展示龙头股推荐列表和详细分析
 */
const LeaderStockPanel = ({
    topN = 20,
    topIndustries = 5,
    perIndustry = 5,
    onStockClick,
    focusIndustry = null,
    onClearFocusIndustry
}) => {
    const message = useSafeMessageApi();
    const normalizeIndustry = useCallback((value) => String(value || '').trim().toLowerCase(), []);
    const resolveScoreType = (record) => {
        if (record?.score_type) return record.score_type;
        return (record?.dimension_scores?.score_type === 'surge' || record?.dimension_scores?.score_type === 'hot')
            ? 'hot'
            : 'core';
    };
    const getLeaderRowKey = (record) => `${record.symbol || 'unknown'}-${record.industry || 'na'}`;
    const [hotLeaders, setHotLeaders] = useState([]);
    const [coreLeaders, setCoreLeaders] = useState([]);
    const [hotLoading, setHotLoading] = useState(true);
    const [coreLoading, setCoreLoading] = useState(true);
    const [error, setError] = useState(null);
    const [warning, setWarning] = useState(null);
    const [selectedStock, setSelectedStock] = useState(null);
    const [selectedScoreType, setSelectedScoreType] = useState('core');
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailData, setDetailData] = useState(null);
    const [detailError, setDetailError] = useState(null);
    const [modalVisible, setModalVisible] = useState(false);
    const [selectedStockRecord, setSelectedStockRecord] = useState(null);
    const [detailIndustryTrend, setDetailIndustryTrend] = useState(null);
    const [activeBoard, setActiveBoard] = useState('core');

    // AbortController refs
    const hotLeadersAbortRef = useRef(null);
    const coreLeadersAbortRef = useRef(null);
    const detailAbortRef = useRef(null);
    const detailTrendAbortRef = useRef(null);
    const loadRequestIdRef = useRef(0);
    const detailRequestIdRef = useRef(0);
    const hotAutoRetryRef = useRef(false);

    // 渐进加载：hot 和 core 独立请求，先到先渲染
    const loadData = useCallback(async () => {
        const requestId = ++loadRequestIdRef.current;
        setError(null);
        setWarning(null);
        setHotLoading(true);
        setCoreLoading(true);

        // 取消之前的请求
        if (hotLeadersAbortRef.current) hotLeadersAbortRef.current.abort();
        if (coreLeadersAbortRef.current) coreLeadersAbortRef.current.abort();
        
        hotLeadersAbortRef.current = new AbortController();
        coreLeadersAbortRef.current = new AbortController();

        // Hot 请求（通常更快）
        const hotPromise = getLeaderStocks(topN, topIndustries, perIndustry, 'hot', {
            signal: hotLeadersAbortRef.current.signal
        })
            .then(data => {
                if (requestId !== loadRequestIdRef.current) return { canceled: true };
                setHotLeaders(data || []);
                return { ok: true, empty: !data || data.length === 0 };
            })
            .catch(err => {
                if (err.name === 'CanceledError') return { canceled: true };
                console.error('Failed to load hot leaders:', err);
                if (requestId === loadRequestIdRef.current) {
                    setHotLeaders([]);
                }
                return { ok: false, message: '热点先锋榜单加载失败' };
            })
            .finally(() => {
                if (requestId === loadRequestIdRef.current) {
                    setHotLoading(false);
                }
            });

        // Core 请求（较慢）
        const corePromise = getLeaderStocks(topN, topIndustries, perIndustry, 'core', {
            signal: coreLeadersAbortRef.current.signal
        })
            .then(data => {
                if (requestId !== loadRequestIdRef.current) return { canceled: true };
                setCoreLeaders(data || []);
                return { ok: true, empty: !data || data.length === 0 };
            })
            .catch(err => {
                if (err.name === 'CanceledError') return { canceled: true };
                console.error('Failed to load core leaders:', err);
                if (requestId === loadRequestIdRef.current) {
                    setCoreLeaders([]);
                }
                return { ok: false, message: '核心资产榜单加载失败' };
            })
            .finally(() => {
                if (requestId === loadRequestIdRef.current) {
                    setCoreLoading(false);
                }
            });

        const [hotResult, coreResult] = await Promise.all([hotPromise, corePromise]);
        if (requestId !== loadRequestIdRef.current) return;

        const failures = [hotResult, coreResult].filter(result => result && result.ok === false);
        if (failures.length >= 2) {
            setError('龙头股榜单加载失败，请稍后重试');
            return;
        }
        if (failures.length === 1) {
            setWarning(failures[0].message);
        }
    }, [topN, topIndustries, perIndustry]);

    useEffect(() => {
        loadData();
        
        return () => {
            if (hotLeadersAbortRef.current) hotLeadersAbortRef.current.abort();
            if (coreLeadersAbortRef.current) coreLeadersAbortRef.current.abort();
            if (detailAbortRef.current) detailAbortRef.current.abort();
            if (detailTrendAbortRef.current) detailTrendAbortRef.current.abort();
        };
    }, [loadData]);

    useEffect(() => {
        if (hotLoading) return undefined;
        if (hotLeaders.length > 0) {
            hotAutoRetryRef.current = false;
            return undefined;
        }
        if (error || hotAutoRetryRef.current) return undefined;

        hotAutoRetryRef.current = true;
        const retryTimer = window.setTimeout(() => {
            loadData();
        }, 1200);

        return () => window.clearTimeout(retryTimer);
    }, [error, hotLeaders.length, hotLoading, loadData]);

    // 合并 loading 状态：全部加载完后如果都为空，显示错误
    const loading = hotLoading && coreLoading;

    const focusedIndustryKey = normalizeIndustry(focusIndustry);
    const focusedCoreLeaders = useMemo(
        () => (!focusedIndustryKey
            ? []
            : coreLeaders.filter((item) => normalizeIndustry(item?.industry) === focusedIndustryKey)),
        [coreLeaders, focusedIndustryKey, normalizeIndustry]
    );
    const focusedHotLeaders = useMemo(
        () => (!focusedIndustryKey
            ? []
            : hotLeaders.filter((item) => normalizeIndustry(item?.industry) === focusedIndustryKey)),
        [hotLeaders, focusedIndustryKey, normalizeIndustry]
    );
    const displayedCoreLeaders = focusedIndustryKey && focusedCoreLeaders.length > 0 ? focusedCoreLeaders : coreLeaders;
    const displayedHotLeaders = focusedIndustryKey && focusedHotLeaders.length > 0 ? focusedHotLeaders : hotLeaders;
    const focusHasMatches = focusedCoreLeaders.length > 0 || focusedHotLeaders.length > 0;
    const activeLeaderPool = useMemo(
        () => (selectedScoreType === 'hot' ? hotLeaders : coreLeaders),
        [coreLeaders, hotLeaders, selectedScoreType]
    );
    const detailRecommendationContext = useMemo(() => {
        if (!selectedStockRecord) return null;

        const normalizedIndustry = normalizeIndustry(selectedStockRecord.industry);
        const peerPool = activeLeaderPool.filter((item) => item?.symbol);
        const industryPeers = peerPool.filter((item) => normalizeIndustry(item?.industry) === normalizedIndustry);
        const industryPeersExSelf = industryPeers.filter((item) => item.symbol !== selectedStockRecord.symbol);
        const peerPoolExSelf = peerPool.filter((item) => item.symbol !== selectedStockRecord.symbol);
        const scoreValue = Number(selectedStockRecord.total_score || detailData?.total_score || 0);
        const scoreLabel = selectedScoreType === 'hot' ? '动量评分' : '综合评分';
        const stockPe = Number(detailData?.raw_data?.pe_ttm || selectedStockRecord.pe_ratio || 0);
        const stockChange = Number(detailData?.raw_data?.change_pct ?? selectedStockRecord.change_pct ?? 0);
        const stockCap = Number(detailData?.raw_data?.market_cap || selectedStockRecord.market_cap || 0);
        const industryAvgScore = averageOf(industryPeersExSelf, (item) => item?.total_score);
        const marketAvgScore = averageOf(peerPoolExSelf, (item) => item?.total_score);
        const industryAvgChange = averageOf(industryPeersExSelf, (item) => item?.change_pct);
        const marketAvgChange = averageOf(peerPoolExSelf, (item) => item?.change_pct);
        const industryAvgPe = Number(detailIndustryTrend?.avg_pe || 0) > 0 ? Number(detailIndustryTrend.avg_pe) : averageOf(industryPeersExSelf, (item) => item?.pe_ratio);
        const industryAvgCap = Number(detailIndustryTrend?.total_market_cap || 0) > 0 && Number(detailIndustryTrend?.stock_count || 0) > 0
            ? Number(detailIndustryTrend.total_market_cap) / Number(detailIndustryTrend.stock_count)
            : averageOf(industryPeersExSelf, (item) => item?.market_cap);
        const dimensionKeys = ['market_cap', 'valuation', 'profitability', 'growth', 'momentum', 'activity'];
        if (selectedScoreType === 'hot') {
            dimensionKeys.splice(5, 0, 'money_flow');
        }
        const industryDimensionAverages = averageDimensionScores(industryPeersExSelf, dimensionKeys);
        const marketDimensionAverages = averageDimensionScores(peerPoolExSelf, dimensionKeys);

        const reasons = [];
        if (selectedStockRecord.industry_rank === 1) {
            reasons.push(`当前在 ${selectedStockRecord.industry} 榜单里排第 1，属于这一轮最强龙头。`);
        } else if (selectedStockRecord.industry_rank > 1) {
            reasons.push(`当前在 ${selectedStockRecord.industry} 榜单里排第 ${selectedStockRecord.industry_rank}，已经进入行业主线关注区。`);
        }

        if (selectedStockRecord.global_rank > 0 && selectedStockRecord.global_rank <= 10) {
            reasons.push(`全市场同口径榜单排名第 ${selectedStockRecord.global_rank}，说明不仅行业内强，跨行业比较也靠前。`);
        }

        if (industryAvgScore != null && scoreValue > 0) {
            const delta = scoreValue - industryAvgScore;
            if (delta >= 4) {
                reasons.push(`${scoreLabel}比同业龙头均值高 ${delta.toFixed(1)} 分，强度已经明显拉开。`);
            } else if (delta <= -4) {
                reasons.push(`${scoreLabel}比同业龙头均值低 ${Math.abs(delta).toFixed(1)} 分，更适合当跟随标的看待。`);
            }
        } else if (marketAvgScore != null && scoreValue > 0) {
            const delta = scoreValue - marketAvgScore;
            if (delta >= 4) {
                reasons.push(`${scoreLabel}比全市场龙头均值高 ${delta.toFixed(1)} 分，具备跨行业比较优势。`);
            }
        }

        if (selectedScoreType === 'core') {
            if (industryAvgPe != null && industryAvgPe > 0 && stockPe > 0) {
                if (stockPe <= industryAvgPe * 0.85) {
                    reasons.push(`当前 PE ${stockPe.toFixed(1)}，低于行业均值 ${industryAvgPe.toFixed(1)}，估值相对更从容。`);
                } else if (stockPe >= industryAvgPe * 1.2) {
                    reasons.push(`当前 PE ${stockPe.toFixed(1)}，高于行业均值 ${industryAvgPe.toFixed(1)}，市场已经给了更高溢价。`);
                }
            }
            if (industryAvgCap != null && industryAvgCap > 0 && stockCap >= industryAvgCap * 2) {
                reasons.push(`总市值明显高于行业平均体量，更接近行业定价锚和机构中军。`);
            }
        } else {
            if (industryAvgChange != null && stockChange >= industryAvgChange + 1) {
                reasons.push(`当日涨幅比同业龙头均值高 ${(stockChange - industryAvgChange).toFixed(1)}%，短线承接更强。`);
            } else if (marketAvgChange != null && stockChange >= marketAvgChange + 1) {
                reasons.push(`当日涨幅比全市场同口径龙头均值高 ${(stockChange - marketAvgChange).toFixed(1)}%，属于更强的情绪承接。`);
            }
            const moneyFlowScore = Number(detailData?.dimension_scores?.money_flow || 0);
            if (moneyFlowScore >= 0.65) {
                reasons.push(`资金流向维度得分 ${(moneyFlowScore * 100).toFixed(0)}，说明短线资金关注度仍在维持。`);
            }
        }

        if (reasons.length === 0) {
            reasons.push(`当前被收录进${selectedScoreType === 'hot' ? '热点先锋' : '核心资产'}榜单，说明它在这一轮榜单筛选里已经通过了基础门槛。`);
        }

        return {
            scoreType: selectedScoreType,
            scoreLabel,
            scoreValue,
            industryName: selectedStockRecord.industry,
            industryRank: selectedStockRecord.industry_rank || null,
            globalRank: selectedStockRecord.global_rank || null,
            industryAvgScore,
            marketAvgScore,
            industryAvgPe,
            industryDimensionAverages,
            marketDimensionAverages,
            reasons: reasons.slice(0, 4),
        };
    }, [activeLeaderPool, detailData, detailIndustryTrend, normalizeIndustry, selectedScoreType, selectedStockRecord]);

    useEffect(() => {
        if (focusIndustry && focusedCoreLeaders.length === 0 && focusedHotLeaders.length > 0) {
            setActiveBoard('hot');
            return;
        }
        if (focusIndustry && focusedCoreLeaders.length > 0) {
            setActiveBoard('core');
        }
    }, [focusIndustry, focusedCoreLeaders.length, focusedHotLeaders.length]);

    useEffect(() => {
        if (focusIndustry) return;
        if (activeBoard === 'core' && displayedCoreLeaders.length === 0 && !hotLoading && displayedHotLeaders.length > 0) {
            setActiveBoard('hot');
            return;
        }
        if (activeBoard === 'hot' && displayedHotLeaders.length === 0 && !coreLoading && displayedCoreLeaders.length > 0) {
            setActiveBoard('core');
        }
    }, [
        activeBoard,
        coreLoading,
        displayedCoreLeaders.length,
        displayedHotLeaders.length,
        focusIndustry,
        hotLoading,
    ]);

    // 加载股票详情
    const loadDetail = useCallback(async (symbol, scoreType = 'core', record = null) => {
        if (detailAbortRef.current) detailAbortRef.current.abort();
        if (detailTrendAbortRef.current) detailTrendAbortRef.current.abort();
        detailAbortRef.current = new AbortController();
        detailTrendAbortRef.current = new AbortController();
        const requestId = detailRequestIdRef.current + 1;
        detailRequestIdRef.current = requestId;

        try {
            setDetailLoading(true);
            setSelectedStock(symbol);
            setSelectedScoreType(scoreType);
            setSelectedStockRecord(record);
            setModalVisible(true);
            setDetailError(null);
            setDetailData(null);
            setDetailIndustryTrend(null);
            const industryName = record?.industry || null;
            const [detailResult, industryTrendResult] = await Promise.allSettled([
                getLeaderDetail(symbol, scoreType, {
                    signal: detailAbortRef.current.signal
                }),
                industryName
                    ? getIndustryTrend(industryName, 30, {
                        signal: detailTrendAbortRef.current.signal
                    })
                    : Promise.resolve(null),
            ]);
            if (
                detailAbortRef.current?.signal.aborted ||
                detailRequestIdRef.current !== requestId
            ) {
                return;
            }
            if (detailResult.status !== 'fulfilled') {
                throw detailResult.reason;
            }
            setDetailData(detailResult.value);
            if (industryTrendResult.status === 'fulfilled') {
                setDetailIndustryTrend(industryTrendResult.value);
            }
        } catch (err) {
            if (err.name === 'CanceledError' || err.name === 'AbortError') return;
            if (detailRequestIdRef.current !== requestId) return;
            console.error('Failed to load stock detail:', err);
            message.error('加载股票详情失败');
            setDetailData(null);
            setDetailError(err.userMessage || '当前股票详情暂不可用');
        } finally {
            if (detailRequestIdRef.current !== requestId) return;
            setDetailLoading(false);
        }
    }, [message]);

    // 表格列定义 — 含核心指标
    const columns = [
        {
            title: '排名',
            dataIndex: 'global_rank',
            key: 'global_rank',
            width: 40,
            render: (rank) => {
                const medals = {
                    1: { icon: '🥇', color: '#d48806' },
                    2: { icon: '🥈', color: 'var(--text-secondary)' },
                    3: { icon: '🥉', color: '#b37feb' },
                };
                const medal = medals[rank];
                if (medal) {
                    return (
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: 700, fontSize: 12, color: medal.color }}>
                            <span style={{ fontSize: 14 }}>{medal.icon}</span>
                            {rank}
                        </span>
                    );
                }
                return (
                    <span style={{
                        fontWeight: 700,
                        fontSize: 12,
                        color: rank <= 10 ? 'var(--accent-warning)' : 'var(--text-muted)'
                    }}>
                        {rank}
                    </span>
                );
            }
        },
        {
            title: '代码',
            dataIndex: 'symbol',
            key: 'symbol',
            width: 62,
            render: (symbol) => (
                <Tag color="blue" style={{ margin: 0, fontSize: 10, lineHeight: '15px', paddingInline: 6, borderRadius: 999 }}>{symbol}</Tag>
            )
        },
        {
            title: '名称',
            dataIndex: 'name',
            key: 'name',
            width: 84,
            ellipsis: true,
            render: (name, record) => {
                const scoreType = resolveScoreType(record);
                return (
                    <Button
                        type="link"
                        size="small"
                        onClick={(e) => { e.stopPropagation(); loadDetail(record.symbol, scoreType, record); }}
                        style={{ padding: 0, height: 'auto', fontWeight: 600, fontSize: 13 }}
                    >
                        {name}
                    </Button>
                );
            }
        },
        {
            title: '涨跌幅',
            dataIndex: 'change_pct',
            key: 'change_pct',
            width: 68,
            sorter: (a, b) => (a.change_pct || 0) - (b.change_pct || 0),
            render: (value) => (
                <span style={{ color: (value || 0) >= 0 ? '#cf1322' : '#3f8600', fontWeight: 700, fontSize: 12 }}>
                    {(value || 0) >= 0 ? '+' : ''}{(value || 0).toFixed(2)}%
                </span>
            )
        },
        {
            title: '走势',
            dataIndex: 'mini_trend',
            key: 'mini_trend',
            width: 96,
            render: (points, record) => (
                <Tooltip title={`${record.name || record.symbol} 近期价格轨迹`}>
                    <div style={{ width: 88 }}>
                        <MiniSparkline points={(points && points.length >= 2) ? points : buildLeaderFallbackTrend(record)} ariaLabel={`${record.name || record.symbol} 近期走势`} />
                    </div>
                </Tooltip>
            )
        },
        {
            title: '得分',
            dataIndex: 'total_score',
            key: 'total_score',
            width: 60,
            sorter: (a, b) => (a.total_score || 0) - (b.total_score || 0),
            render: (score, record) => {
                const isSurge = resolveScoreType(record) === 'hot';
                const label = isSurge ? '动量评分' : '综合评分';
                return (
                    <Tooltip title={`${label} ${(score || 0).toFixed(1)}`}>
                        <span style={{
                            fontWeight: 700,
                            fontSize: 13,
                            color: (score || 0) >= 70 ? '#52c41a' : (score || 0) >= 50 ? '#faad14' : '#ff4d4f'
                        }}>
                            {(score || 0).toFixed(1)}
                        </span>
                    </Tooltip>
                );
            }
        },
        {
            title: '市值',
            dataIndex: 'market_cap',
            key: 'market_cap',
            width: 62,
            sorter: (a, b) => (a.market_cap || 0) - (b.market_cap || 0),
            render: (value) => {
                if (!value) return <span style={{ color: 'var(--text-muted)' }}>-</span>;
                const yi = value / 1e8;
                if (yi >= 10000) return <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{(yi / 10000).toFixed(1)}万亿</span>;
                return <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{yi.toFixed(0)}亿</span>;
            }
        },
        {
            title: 'PE',
            dataIndex: 'pe_ratio',
            key: 'pe_ratio',
            width: 48,
            sorter: (a, b) => (a.pe_ratio || 0) - (b.pe_ratio || 0),
            render: (value) => {
                if (!value) return <span style={{ color: 'var(--text-muted)' }}>-</span>;
                const color = value > 0 && value < 30 ? '#52c41a' : value > 80 ? '#ff4d4f' : 'var(--text-primary)';
                return <span style={{ fontSize: 11, color }}>{value.toFixed(1)}</span>;
            }
        },
        {
            title: '行业',
            dataIndex: 'industry',
            key: 'industry',
            width: 68,
            ellipsis: true,
            render: (industry, record) => {
                const tagColors = ['magenta', 'red', 'volcano', 'orange', 'gold', 'green', 'cyan', 'blue', 'geekblue', 'purple'];
                const hash = (industry || '').split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
                const color = tagColors[hash % tagColors.length];
                const rank = record.industry_rank;
                return (
                    <Tooltip title={rank > 0 ? `行业内排名 #${rank}` : undefined}>
                        <Tag color={color} style={{ fontSize: 10, lineHeight: '15px', paddingInline: 6, borderRadius: 999, maxWidth: 90, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {industry}{rank > 1 ? ` #${rank}` : ''}
                        </Tag>
                    </Tooltip>
                );
            }
        },
    ];

    const renderSectionHeader = (title, subtitle, accentColor, count, scoreHint) => (
        <div style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
            marginBottom: 10,
        }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <span style={{
                    width: 6,
                    minWidth: 6,
                    height: 28,
                    borderRadius: 999,
                    background: accentColor,
                    marginTop: 2,
                    boxShadow: `0 0 0 4px ${accentColor}22`,
                }} />
                <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.2 }}>{title}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{subtitle}</div>
                </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                <Tag color="default" style={{ margin: 0, borderRadius: 999, fontSize: 11 }}>{count} 只</Tag>
                <Tag color="default" style={{ margin: 0, borderRadius: 999, fontSize: 11 }}>{scoreHint}</Tag>
            </div>
        </div>
    );

    // 渲染详情弹窗
    const renderDetailModal = () => (
        <StockDetailModal
            open={modalVisible}
            onCancel={() => setModalVisible(false)}
            loading={detailLoading}
            error={detailError}
            detailData={detailData}
            selectedStock={selectedStock}
            selectedRecord={selectedStockRecord}
            recommendationContext={detailRecommendationContext}
            onRetry={selectedStock ? () => loadDetail(selectedStock, selectedScoreType || 'core', selectedStockRecord) : undefined}
        />
    );

    if (loading) {
        return (
            <Card title="龙头股推荐">
                {renderLeaderLoadingScaffold('#faad14', '正在准备龙头股榜单', '优先补核心资产与热点先锋的首批可读标的。')}
            </Card>
        );
    }

    if (error) {
        return (
            <Card
                title="龙头股推荐"
                extra={
                    <Button className="industry-empty-action" icon={<ReloadOutlined />} onClick={loadData}>
                        重试
                    </Button>
                }
            >
                <Empty description={error} />
            </Card>
        );
    }

    return (
        <>
            <Card
                data-testid="leader-stock-panel"
                title={
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <span>
                            <CrownOutlined style={{ marginRight: 8, color: '#faad14' }} />
                            龙头股推荐
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 400 }}>同看核心资产与热点先锋，点击整行可直接查看详情</span>
                    </div>
                }
                extra={
                    <Tooltip title="刷新龙头股榜单">
                        <Button icon={<ReloadOutlined />} onClick={loadData} size="small" type="text" />
                    </Tooltip>
                }
                styles={{ body: { paddingTop: 12, paddingBottom: 12 } }}
            >
                {warning && (
                    <div style={{
                        marginBottom: 12,
                        padding: '10px 12px',
                        borderRadius: 10,
                        background: '#fffbe6',
                        border: '1px solid #ffe58f',
                        color: '#ad6800',
                        fontSize: 12
                    }}>
                        {warning}
                    </div>
                )}

                {focusIndustry && (
                    <div style={{
                        marginBottom: 12,
                        padding: '10px 12px',
                        borderRadius: 12,
                        background: focusHasMatches
                            ? 'linear-gradient(180deg, rgba(250,173,20,0.09) 0%, rgba(250,173,20,0.02) 100%)'
                            : 'linear-gradient(180deg, rgba(140,140,140,0.08) 0%, rgba(140,140,140,0.02) 100%)',
                        border: focusHasMatches
                            ? '1px solid rgba(250,173,20,0.24)'
                            : '1px solid rgba(140,140,140,0.18)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 12,
                        flexWrap: 'wrap'
                    }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700 }}>当前行业聚焦</span>
                                <Tag color={focusHasMatches ? 'gold' : 'default'} style={{ margin: 0, borderRadius: 999 }}>{focusIndustry}</Tag>
                            </div>
                            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                {focusHasMatches
                                    ? `核心资产 ${focusedCoreLeaders.length} 只，热点先锋 ${focusedHotLeaders.length} 只`
                                    : '当前榜单里暂无该行业龙头，已回退展示全市场榜单'}
                            </div>
                        </div>
                        {onClearFocusIndustry && (
                            <Button size="small" type="text" onClick={onClearFocusIndustry}>
                                清除聚焦
                            </Button>
                        )}
                    </div>
                )}

                <Tabs
                    activeKey={activeBoard}
                    onChange={setActiveBoard}
                    items={[
                        {
                            key: 'core',
                            label: `核心资产 ${displayedCoreLeaders.length}`,
                            children: (
                                <div style={{
                                    padding: '12px 12px 6px',
                                    borderRadius: 12,
                                    background: 'linear-gradient(180deg, rgba(24,144,255,0.05) 0%, rgba(24,144,255,0.015) 100%)',
                                    border: '1px solid rgba(24,144,255,0.10)'
                                }} data-testid="leader-stock-table-core">
                                    {coreLoading && displayedCoreLeaders.length === 0
                                        ? renderLeaderLoadingScaffold('#1890ff', '核心资产', '正在按基本面与流动性整理行业中军。')
                                        : (
                                            <>
                                    {renderSectionHeader(
                                        '核心资产',
                                        focusIndustry && focusedCoreLeaders.length > 0 ? `${focusIndustry} 行业内偏长期基本面与流动性中军` : '偏长期基本面与流动性中军',
                                        '#1890ff',
                                        displayedCoreLeaders.length,
                                        focusIndustry && focusedCoreLeaders.length > 0 ? '行业内综合评分' : '综合评分'
                                    )}
                                    <Table
                                        className="leader-stock-table leader-stock-table-core"
                                        dataSource={displayedCoreLeaders}
                                        columns={columns}
                                        rowKey={getLeaderRowKey}
                                        size="small"
                                        loading={coreLoading}
                                        scroll={{ x: 760 }}
                                        pagination={false}
                                        onRow={(record) => ({
                                            onClick: () => {
                                                if (onStockClick) {
                                                    onStockClick(record.symbol);
                                                    return;
                                                }
                                                loadDetail(record.symbol, resolveScoreType(record), record);
                                            },
                                            style: { cursor: 'pointer' },
                                            'data-testid': 'leader-stock-row',
                                            'data-symbol': record.symbol || '',
                                            'data-score-type': resolveScoreType(record),
                                        })}
                                        style={{ background: 'transparent' }}
                                        locale={{ emptyText: coreLoading ? '正在加载核心资产...' : (focusIndustry ? '当前行业暂无可用核心资产标的' : '当前暂无可用核心资产标的') }}
                                    />
                                            </>
                                        )}
                                </div>
                            ),
                        },
                        {
                            key: 'hot',
                            label: `热点先锋 ${displayedHotLeaders.length}`,
                            children: (
                                <div style={{
                                    padding: '12px 12px 6px',
                                    borderRadius: 12,
                                    background: 'linear-gradient(180deg, rgba(235,47,150,0.05) 0%, rgba(235,47,150,0.015) 100%)',
                                    border: '1px solid rgba(235,47,150,0.10)'
                                }} data-testid="leader-stock-table-hot">
                                    {hotLoading && displayedHotLeaders.length === 0
                                        ? renderLeaderLoadingScaffold('#eb2f96', '热点先锋', '正在按短线动量与资金关注度筛选热点标的。')
                                        : (
                                            <>
                                    {renderSectionHeader(
                                        '热点先锋',
                                        focusIndustry && focusedHotLeaders.length > 0 ? `${focusIndustry} 行业内偏短线涨势与资金关注度` : '偏短线涨势与资金关注度',
                                        '#eb2f96',
                                        displayedHotLeaders.length,
                                        focusIndustry && focusedHotLeaders.length > 0 ? '行业内动量评分' : '动量评分'
                                    )}
                                    <Table
                                        className="leader-stock-table leader-stock-table-hot"
                                        dataSource={displayedHotLeaders}
                                        columns={columns}
                                        rowKey={getLeaderRowKey}
                                        size="small"
                                        loading={hotLoading}
                                        scroll={{ x: 760 }}
                                        pagination={false}
                                        onRow={(record) => ({
                                            onClick: () => {
                                                if (onStockClick) {
                                                    onStockClick(record.symbol);
                                                    return;
                                                }
                                                loadDetail(record.symbol, resolveScoreType(record), record);
                                            },
                                            style: { cursor: 'pointer' },
                                            'data-testid': 'leader-stock-row',
                                            'data-symbol': record.symbol || '',
                                            'data-score-type': resolveScoreType(record),
                                        })}
                                        style={{ background: 'transparent' }}
                                        locale={{ emptyText: hotLoading ? '正在加载热点先锋...' : (focusIndustry ? '当前行业暂无可用热点先锋标的' : '当前暂无可用热点先锋标的') }}
                                    />
                                            </>
                                        )}
                                </div>
                            ),
                        },
                    ]}
                />
            </Card>
            {renderDetailModal()}
        </>
    );
};

export default LeaderStockPanel;
