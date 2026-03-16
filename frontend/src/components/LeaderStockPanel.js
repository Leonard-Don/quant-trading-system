import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    Card,
    Table,
    Spin,
    Empty,
    Tag,
    Button,
    message,
    Tooltip
} from 'antd';
import {
    CrownOutlined,
    ReloadOutlined
} from '@ant-design/icons';
import { getLeaderStocks, getLeaderDetail } from '../services/api';
import StockDetailModal from './StockDetailModal';

/**
 * 龙头股面板组件
 * 展示龙头股推荐列表和详细分析
 */
const LeaderStockPanel = ({
    topN = 20,
    topIndustries = 5,
    perIndustry = 5,
    onStockClick
}) => {
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
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailData, setDetailData] = useState(null);
    const [detailError, setDetailError] = useState(null);
    const [modalVisible, setModalVisible] = useState(false);

    // AbortController refs
    const hotLeadersAbortRef = useRef(null);
    const coreLeadersAbortRef = useRef(null);
    const detailAbortRef = useRef(null);
    const loadRequestIdRef = useRef(0);
    const detailRequestIdRef = useRef(0);

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
        };
    }, [loadData]);

    // 合并 loading 状态：全部加载完后如果都为空，显示错误
    const loading = hotLoading && coreLoading;

    // 加载股票详情
    const loadDetail = useCallback(async (symbol, scoreType = 'core') => {
        if (detailAbortRef.current) detailAbortRef.current.abort();
        detailAbortRef.current = new AbortController();
        const requestId = detailRequestIdRef.current + 1;
        detailRequestIdRef.current = requestId;

        try {
            setDetailLoading(true);
            setSelectedStock(symbol);
            setModalVisible(true);
            setDetailError(null);
            setDetailData(null);
            const result = await getLeaderDetail(symbol, scoreType, {
                signal: detailAbortRef.current.signal
            });
            if (
                detailAbortRef.current?.signal.aborted ||
                detailRequestIdRef.current !== requestId
            ) {
                return;
            }
            setDetailData(result);
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
    }, []);

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
                        onClick={(e) => { e.stopPropagation(); loadDetail(record.symbol, scoreType); }}
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
            title: '得分',
            dataIndex: 'total_score',
            key: 'total_score',
            width: 60,
            sorter: (a, b) => (a.total_score || 0) - (b.total_score || 0),
            render: (score, record) => {
                const isSurge = resolveScoreType(record) === 'hot';
                const label = isSurge ? '动量得分' : '综合评分';
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
            onRetry={selectedStock ? () => loadDetail(selectedStock, detailData?.score_type || 'core') : undefined}
        />
    );

    if (loading) {
        return (
            <Card title="龙头股推荐">
                <div style={{ textAlign: 'center', padding: 50 }}>
                    <Spin size="large" />
                    <div style={{ marginTop: 16 }}>加载龙头股数据...</div>
                </div>
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

                <div style={{
                    marginBottom: 18,
                    padding: '12px 12px 6px',
                    borderRadius: 12,
                    background: 'linear-gradient(180deg, rgba(24,144,255,0.05) 0%, rgba(24,144,255,0.015) 100%)',
                    border: '1px solid rgba(24,144,255,0.10)'
                }} data-testid="leader-stock-table-core">
                    {renderSectionHeader('核心资产', '偏长期基本面与流动性中军', '#1890ff', coreLeaders.length, '综合评分')}
                    <Table
                        className="leader-stock-table leader-stock-table-core"
                        dataSource={coreLeaders}
                        columns={columns}
                        rowKey={getLeaderRowKey}
                        size="small"
                        loading={coreLoading}
                        pagination={false}
                        onRow={(record) => ({
                            onClick: () => {
                                if (onStockClick) {
                                    onStockClick(record.symbol);
                                    return;
                                }
                                loadDetail(record.symbol, resolveScoreType(record));
                            },
                            style: { cursor: 'pointer' },
                            'data-testid': 'leader-stock-row',
                            'data-symbol': record.symbol || '',
                            'data-score-type': resolveScoreType(record),
                        })}
                        style={{ background: 'transparent' }}
                        locale={{ emptyText: coreLoading ? '正在加载核心资产...' : '当前暂无可用核心资产标的' }}
                    />
                </div>
                
                <div style={{
                    padding: '12px 12px 6px',
                    borderRadius: 12,
                    background: 'linear-gradient(180deg, rgba(235,47,150,0.05) 0%, rgba(235,47,150,0.015) 100%)',
                    border: '1px solid rgba(235,47,150,0.10)'
                }} data-testid="leader-stock-table-hot">
                    {renderSectionHeader('热点先锋', '偏短线涨势与资金关注度', '#eb2f96', hotLeaders.length, '动量评分')}
                    <Table
                        className="leader-stock-table leader-stock-table-hot"
                        dataSource={hotLeaders}
                        columns={columns}
                        rowKey={getLeaderRowKey}
                        size="small"
                        loading={hotLoading}
                        pagination={false}
                        onRow={(record) => ({
                            onClick: () => {
                                if (onStockClick) {
                                    onStockClick(record.symbol);
                                    return;
                                }
                                loadDetail(record.symbol, resolveScoreType(record));
                            },
                            style: { cursor: 'pointer' },
                            'data-testid': 'leader-stock-row',
                            'data-symbol': record.symbol || '',
                            'data-score-type': resolveScoreType(record),
                        })}
                        style={{ background: 'transparent' }}
                        locale={{ emptyText: hotLoading ? '正在加载热点先锋...' : '当前暂无可用热点先锋标的' }}
                    />
                </div>
            </Card>
            {renderDetailModal()}
        </>
    );
};

export default LeaderStockPanel;
