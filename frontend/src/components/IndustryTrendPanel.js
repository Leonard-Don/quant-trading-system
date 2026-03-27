import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    Card,
    Row,
    Col,
    Statistic,
    Table,
    Tag,
    Spin,
    Empty,
    Button,
    Typography,
    Divider,
    message,
    Alert
} from 'antd';
import {
    RiseOutlined,
    FallOutlined,
    ReloadOutlined,
    BankOutlined,
    TeamOutlined,
    DollarOutlined
} from '@ant-design/icons';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip as RechartsTooltip,
    ResponsiveContainer,
    ReferenceLine,
    Cell
} from 'recharts';
import { getIndustryTrend } from '../services/api';

const { Text } = Typography;
const TEXT_SECONDARY = 'var(--text-secondary)';
const TEXT_MUTED = 'var(--text-muted)';
const SURFACE_BG = 'var(--bg-secondary)';
const POSITIVE = 'var(--accent-danger)';
const NEGATIVE = 'var(--accent-success)';
const WARNING = 'var(--accent-warning)';
const NEUTRAL_LINE = 'color-mix(in srgb, var(--border-color) 78%, var(--text-muted) 22%)';
const POSITIVE_SOFT = 'color-mix(in srgb, var(--accent-danger) 24%, #ffffff 76%)';
const NEGATIVE_SOFT = 'color-mix(in srgb, var(--accent-success) 24%, #ffffff 76%)';
const COMPACT_STAT_VALUE_STYLE = {
    fontSize: 20,
    lineHeight: 1.2,
    whiteSpace: 'nowrap',
};
const COMPACT_STAT_TITLE_STYLE = {
    fontSize: 12,
};

const calculateWeightedIndustryPe = (stocks = []) => {
    const validPairs = (stocks || [])
        .map((stock) => ({
            marketCap: Number(stock?.market_cap || 0),
            peRatio: Number(stock?.pe_ratio || 0),
        }))
        .filter(({ marketCap, peRatio }) => Number.isFinite(marketCap) && marketCap > 0 && Number.isFinite(peRatio) && peRatio > 0 && peRatio < 500);

    if (validPairs.length === 0) {
        return null;
    }

    const totalMarketCap = validPairs.reduce((sum, item) => sum + item.marketCap, 0);
    const totalEarnings = validPairs.reduce((sum, item) => sum + (item.marketCap / item.peRatio), 0);
    if (!Number.isFinite(totalMarketCap) || !Number.isFinite(totalEarnings) || totalMarketCap <= 0 || totalEarnings <= 0) {
        return null;
    }

    return totalMarketCap / totalEarnings;
};

/**
 * 行业趋势详情面板
 * 展示选中行业的趋势分析：统计信息 + 涨跌分布图 + 涨幅/跌幅前5
 */
const IndustryTrendPanel = ({
    industryName,
    days = 30,
    stocks = [],
    loadingStocks = false,
    stocksRefining = false,
    stocksScoreStage = null,
    stocksDisplayReady = false,
    stockColumns = []
}) => {
    const getVolatilityMeta = (value, source) => {
        const tone = value >= 4 ? { color: POSITIVE, label: '高波动', tagColor: 'error' }
            : value >= 2 ? { color: WARNING, label: '中波动', tagColor: 'warning' }
                : { color: NEGATIVE, label: '低波动', tagColor: 'success' };
        const sourceLabelMap = {
            historical_index: '历史指数',
            stock_dispersion: '成分股离散度',
            amplitude_proxy: '振幅代理',
            turnover_rate_proxy: '换手率代理',
            change_proxy: '涨跌幅代理',
        };
        return {
            ...tone,
            sourceLabel: sourceLabelMap[source] || '暂无',
        };
    };
    const getTrendRowKey = (record) => [
        record.symbol || '',
        record.name || '',
        record.change_pct ?? '',
        record.total_score ?? '',
    ].join('-') || 'unknown';
    const [trendData, setTrendData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const trendAbortRef = useRef(null);

    const loadTrend = useCallback(async () => {
        if (!industryName) return;
        if (trendAbortRef.current) {
            trendAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        trendAbortRef.current = currentAbort;

        let isCanceled = false;
        try {
            setLoading(true);
            setError(null);
            const result = await getIndustryTrend(industryName, days, {
                signal: currentAbort.signal,
            });
            if (trendAbortRef.current !== currentAbort) return;
            setTrendData(result);
        } catch (err) {
            if (err.name === 'CanceledError' || err.name === 'AbortError') {
                isCanceled = true;
                return;
            }
            if (trendAbortRef.current !== currentAbort) return;
            console.error('Failed to load industry trend:', err);
            setError(err.userMessage || '加载行业趋势失败');
            message.error('加载行业趋势失败');
        } finally {
            if (!isCanceled && trendAbortRef.current === currentAbort) {
                setLoading(false);
            }
        }
    }, [industryName, days]);

    useEffect(() => {
        loadTrend();
        return () => {
            if (trendAbortRef.current) {
                trendAbortRef.current.abort();
            }
        };
    }, [loadTrend]);

    if (!industryName) {
        return (
            <Card>
                <Empty
                    description="请先从热力图或排行榜中选择一个行业"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
            </Card>
        );
    }

    const formatMarketCap = (value) => {
        if (!value) return '-';
        const yi = value / 100000000;
        if (yi >= 10000) return `${(yi / 10000).toFixed(2)}万亿`;
        return `${yi.toFixed(0)}亿`;
    };

    const formatMoneyFlow = (value) => {
        if (!value) return '-';
        const yi = value / 100000000;
        if (Math.abs(yi) >= 1) return `${yi >= 0 ? '+' : ''}${yi.toFixed(2)}亿`;
        const wan = value / 10000;
        return `${wan >= 0 ? '+' : ''}${wan.toFixed(0)}万`;
    };

    const stockDerivedTotalMarketCap = (stocks || []).reduce((sum, stock) => sum + Number(stock?.market_cap || 0), 0);
    const stockDerivedAvgPe = calculateWeightedIndustryPe(stocks);

    const renderStocksSection = () => (
        <div style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 8 }} data-testid="industry-stock-table-header">
                <Text strong><TeamOutlined /> 行业成分股 ({stocks?.length || 0})</Text>
            </div>
            {stocksScoreStage === 'quick' && (stocks?.length || 0) > 0 && (
                <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message={
                        stocksDisplayReady
                            ? '当前展示已具备主要明细，完整评分后台仍在构建'
                            : (stocksRefining ? '当前为快速评分，完整评分后台计算中（大行业可能稍慢）' : '当前为快速评分')
                    }
                />
            )}
            <div
                data-testid="industry-stock-table"
                data-score-stage={stocksScoreStage || 'unknown'}
                data-display-ready={stocksDisplayReady ? 'true' : 'false'}
            >
                <Table
                    dataSource={stocks}
                    columns={stockColumns}
                    rowKey={getTrendRowKey}
                    size="small"
                    loading={loadingStocks && (!stocks || stocks.length === 0)}
                    pagination={{ pageSize: 10 }}
                    locale={{ emptyText: trendData?.degraded ? '当前数据源未返回成分股明细' : '暂无成分股数据' }}
                />
            </div>
        </div>
    );

    if (loading && !trendData) {
        return (
            <Card
                data-testid="industry-detail-panel"
                title={
                    <span>
                        <BankOutlined style={{ marginRight: 8, color: 'var(--accent-primary)' }} />
                        {industryName} 行业概览
                    </span>
                }
                extra={
                    <Button className="industry-inline-link" onClick={loadTrend} icon={<ReloadOutlined />} size="small">
                        刷新
                    </Button>
                }
            >
                <div style={{ textAlign: 'center', padding: '12px 0 20px' }}>
                    <Spin />
                    <div style={{ marginTop: 12, color: TEXT_MUTED }}>行业摘要加载中，成分股可先行展示</div>
                </div>
                <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                    <Col xs={12} sm={12} md={8} lg={6}>
                        <Statistic
                            title="成分股数量"
                            value={stocks?.length || 0}
                            suffix="只"
                            prefix={<TeamOutlined />}
                            valueStyle={COMPACT_STAT_VALUE_STYLE}
                            titleStyle={COMPACT_STAT_TITLE_STYLE}
                        />
                    </Col>
                <Col xs={12} sm={12} md={8} lg={8}>
                        <Statistic
                            title="总市值"
                            value={stockDerivedTotalMarketCap}
                            formatter={() => formatMarketCap(stockDerivedTotalMarketCap)}
                            prefix={<DollarOutlined />}
                            valueStyle={COMPACT_STAT_VALUE_STYLE}
                            titleStyle={COMPACT_STAT_TITLE_STYLE}
                        />
                    </Col>
                    <Col xs={12} sm={12} md={8} lg={6}>
                        <Statistic
                            title="平均市盈率"
                            value={stockDerivedAvgPe || '-'}
                            precision={2}
                            valueStyle={COMPACT_STAT_VALUE_STYLE}
                            titleStyle={COMPACT_STAT_TITLE_STYLE}
                        />
                    </Col>
                </Row>
                <Divider style={{ margin: '12px 0' }} />
                {renderStocksSection()}
            </Card>
        );
    }

    if (error && !trendData) {
        return (
            <Card
                data-testid="industry-detail-panel"
                title={
                    <span>
                        <BankOutlined style={{ marginRight: 8, color: 'var(--accent-primary)' }} />
                        {industryName} 行业概览
                    </span>
                }
                extra={<Button className="industry-empty-action" onClick={loadTrend} icon={<ReloadOutlined />} size="small">重试</Button>}
            >
                <Empty description={error} />
                <Divider style={{ margin: '12px 0' }} />
                {renderStocksSection()}
            </Card>
        );
    }

    if (!trendData) return null;

    // 涨跌分布柱状图数据（去重：同一股票只保留一条）
    const barChartDataRaw = [
        ...(trendData.top_gainers || []).map(s => ({
            name: s.name || s.symbol,
            value: s.change_pct || 0,
        })),
        ...(trendData.top_losers || []).map(s => ({
            name: s.name || s.symbol,
            value: s.change_pct || 0,
        })),
    ];
    const seen = new Set();
    const barChartData = barChartDataRaw.filter(item => {
        if (seen.has(item.name)) return false;
        seen.add(item.name);
        return true;
    }).sort((a, b) => b.value - a.value);

    const riseCount = trendData.rise_count || 0;
    const fallCount = trendData.fall_count || 0;
    const flatCount = trendData.flat_count || 0;
    const volatilityValue = Number(trendData.industry_volatility || 0);
    const volatilityMeta = getVolatilityMeta(volatilityValue, trendData.industry_volatility_source);
    const derivedTotalMarketCap = (
        Number(trendData.total_market_cap || 0) > 0
            ? Number(trendData.total_market_cap || 0)
            : stockDerivedTotalMarketCap
    );
    const derivedAvgPe = (
        trendData.avg_pe != null && trendData.avg_pe > 0
            ? trendData.avg_pe
            : stockDerivedAvgPe
    );

    return (
        <Card
            data-testid="industry-detail-panel"
            title={
                <span>
                    <BankOutlined style={{ marginRight: 8, color: 'var(--accent-primary)' }} />
                    {industryName} 行业概览
                </span>
            }
            extra={
                <Button className="industry-inline-link" onClick={loadTrend} icon={<ReloadOutlined />} size="small">
                    刷新
                </Button>
            }
        >
            {trendData.degraded && (
                <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="当前显示的是降级行业数据"
                    description={trendData.note || '成分股明细暂不可用，页面仅展示行业聚合指标。'}
                />
            )}

            {/* 行业统计信息 */}
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                <Col xs={12} sm={12} md={8} lg={6}>
                    <Statistic
                        title="成分股数量"
                        value={trendData.stock_count || 0}
                        suffix="只"
                        prefix={<TeamOutlined />}
                        valueStyle={COMPACT_STAT_VALUE_STYLE}
                        titleStyle={COMPACT_STAT_TITLE_STYLE}
                    />
                </Col>
                <Col xs={12} sm={12} md={8} lg={8}>
                    <Statistic
                        title="总市值"
                        value={derivedTotalMarketCap}
                        formatter={() => formatMarketCap(derivedTotalMarketCap)}
                        prefix={<DollarOutlined />}
                        valueStyle={COMPACT_STAT_VALUE_STYLE}
                        titleStyle={COMPACT_STAT_TITLE_STYLE}
                    />
                </Col>
                <Col xs={12} sm={12} md={8} lg={6}>
                    <Statistic
                        title="平均市盈率"
                        value={derivedAvgPe || '-'}
                        precision={2}
                        valueStyle={COMPACT_STAT_VALUE_STYLE}
                        titleStyle={COMPACT_STAT_TITLE_STYLE}
                    />
                </Col>
                <Col xs={12} sm={12} md={12} lg={5}>
                    <Statistic
                        title="区间波动率"
                        value={volatilityValue || '-'}
                        precision={2}
                        suffix={volatilityValue ? '%' : ''}
                        valueStyle={{
                            ...COMPACT_STAT_VALUE_STYLE,
                            color: volatilityValue ? volatilityMeta.color : undefined,
                        }}
                        titleStyle={COMPACT_STAT_TITLE_STYLE}
                    />
                    {volatilityValue > 0 && (
                        <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                            <Tag color={volatilityMeta.tagColor} style={{ marginRight: 6 }}>
                                {volatilityMeta.label}
                            </Tag>
                            <Text type="secondary" style={{ fontSize: 12 }}>来源: {volatilityMeta.sourceLabel}</Text>
                        </div>
                    )}
                </Col>
                <Col xs={24} sm={24} md={12} lg={5}>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        <Statistic
                            title={<span style={{ fontSize: 12 }}>涨/跌/平</span>}
                            valueRender={() => (
                                <span style={{ fontSize: 16 }}>
                                    <span style={{ color: POSITIVE }}>{riseCount}</span>
                                    <span style={{ color: TEXT_MUTED, margin: '0 4px' }}>/</span>
                                    <span style={{ color: NEGATIVE }}>{fallCount}</span>
                                    <span style={{ color: TEXT_MUTED, margin: '0 4px' }}>/</span>
                                    <span style={{ color: TEXT_SECONDARY }}>{flatCount}</span>
                                </span>
                            )}
                            prefix={<RiseOutlined style={{ color: POSITIVE }} />}
                        />
                    </div>
                </Col>
            </Row>

            {/* 涨跌比例可视化 */}
            {(riseCount + fallCount + flatCount) > 0 && (
                <div style={{ marginBottom: 12, display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', background: `color-mix(in srgb, ${SURFACE_BG} 84%, var(--bg-primary) 16%)` }}>
                    {riseCount > 0 && <div style={{ width: `${riseCount / (riseCount + fallCount + flatCount) * 100}%`, background: `linear-gradient(90deg, ${POSITIVE_SOFT}, ${POSITIVE})`, transition: 'width 0.3s' }} />}
                    {flatCount > 0 && <div style={{ width: `${flatCount / (riseCount + fallCount + flatCount) * 100}%`, background: `color-mix(in srgb, ${TEXT_MUTED} 65%, #d9d9d9 35%)`, transition: 'width 0.3s' }} />}
                    {fallCount > 0 && <div style={{ width: `${fallCount / (riseCount + fallCount + flatCount) * 100}%`, background: `linear-gradient(90deg, ${NEGATIVE_SOFT}, ${NEGATIVE})`, transition: 'width 0.3s' }} />}
                </div>
            )}

            <div style={{ marginBottom: 12 }}>
                <Text type="secondary">
                    近 {trendData.period_days || days} 日行业涨跌幅：
                    <span style={{ color: (trendData.period_change_pct || 0) >= 0 ? POSITIVE : NEGATIVE, fontWeight: 'bold' }}>
                        {(trendData.period_change_pct || 0) >= 0 ? '+' : ''}{(trendData.period_change_pct || 0).toFixed(2)}%
                    </span>
                    {' '}| 主力净流入：{formatMoneyFlow(trendData.period_money_flow)}
                </Text>
            </div>

            {/* 涨跌分布柱状图 */}
            {barChartData.length > 0 && (
                <>
                    <Divider style={{ margin: '12px 0' }} />
                    <div style={{ marginBottom: 8 }}>
                        <Text strong>涨跌幅分布</Text>
                    </div>
                    <ResponsiveContainer width="100%" height={Math.max(120, barChartData.length * 30 + 40)}>
                        <BarChart data={barChartData} layout="vertical" margin={{ left: 60, right: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                            <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
                            <YAxis
                                type="category"
                                dataKey="name"
                                tick={{ fontSize: 11 }}
                                width={55}
                            />
                            <RechartsTooltip
                                formatter={(value) => [`${value.toFixed(2)}%`, '涨跌幅']}
                            />
                            <ReferenceLine x={0} stroke={NEUTRAL_LINE} />
                            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
                                {barChartData.map((entry, idx) => (
                                    <Cell
                                        key={idx}
                                        fill={entry.value >= 0 ? POSITIVE : NEGATIVE}
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </>
            )}

            <Divider style={{ margin: '12px 0' }} />

            {/* 涨跌幅排行 */}
            <Row gutter={16}>
                <Col span={12}>
                    <div style={{ marginBottom: 8 }}>
                        <Text strong style={{ color: POSITIVE }}>
                            <RiseOutlined /> 涨幅前5
                        </Text>
                    </div>
                    <Table
                        dataSource={(trendData.top_gainers || []).map((s, i) => ({ ...s, _rank: i + 1 }))}
                        columns={[
                            { title: '排名', dataIndex: '_rank', key: '_rank', width: 50 },
                            { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 80, render: (v) => <Tag color="blue">{v}</Tag> },
                            { title: '名称', dataIndex: 'name', key: 'name', width: 90 },
                            {
                                title: '涨跌幅', dataIndex: 'change_pct', key: 'change_pct', width: 80, render: (v) => (
                                    <span style={{ color: (v || 0) >= 0 ? POSITIVE : NEGATIVE, fontWeight: 'bold' }}>
                                        {(v || 0) >= 0 ? '+' : ''}{(v || 0).toFixed(2)}%
                                    </span>
                                )
                            },
                            {
                                title: '市值', dataIndex: 'market_cap', key: 'mc_g', width: 70, render: (v) => {
                                    if (!v) return '-';
                                    const yi = v / 100000000;
                                    return yi >= 10000 ? `${(yi / 10000).toFixed(1)}万亿` : `${yi.toFixed(0)}亿`;
                                }
                            },
                        ]}
                        rowKey={getTrendRowKey}
                        size="small"
                        pagination={false}
                        locale={{ emptyText: trendData.degraded ? '降级模式下无涨幅榜明细' : '暂无数据' }}
                    />
                </Col>
                <Col span={12}>
                    <div style={{ marginBottom: 8 }}>
                        <Text strong style={{ color: NEGATIVE }}>
                            <FallOutlined /> 跌幅前5
                        </Text>
                    </div>
                    <Table
                        dataSource={(trendData.top_losers || []).map((s, i) => ({ ...s, _rank: i + 1 }))}
                        columns={[
                            { title: '排名', dataIndex: '_rank', key: '_rank', width: 50 },
                            { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 80, render: (v) => <Tag color="blue">{v}</Tag> },
                            { title: '名称', dataIndex: 'name', key: 'name', width: 90 },
                            {
                                title: '涨跌幅', dataIndex: 'change_pct', key: 'change_pct', width: 80, render: (v) => (
                                    <span style={{ color: (v || 0) >= 0 ? POSITIVE : NEGATIVE, fontWeight: 'bold' }}>
                                        {(v || 0) >= 0 ? '+' : ''}{(v || 0).toFixed(2)}%
                                    </span>
                                )
                            },
                            {
                                title: '市值', dataIndex: 'market_cap', key: 'mc_l', width: 70, render: (v) => {
                                    if (!v) return '-';
                                    const yi = v / 100000000;
                                    return yi >= 10000 ? `${(yi / 10000).toFixed(1)}万亿` : `${yi.toFixed(0)}亿`;
                                }
                            },
                        ]}
                        rowKey={getTrendRowKey}
                        size="small"
                        pagination={false}
                        locale={{ emptyText: trendData.degraded ? '降级模式下无跌幅榜明细' : '暂无数据' }}
                    />
                </Col>
            </Row>

            <Divider style={{ margin: '12px 0' }} />

            {/* 行业成分股列表 */}
            {renderStocksSection()}

            {trendData.update_time && (
                <div style={{ textAlign: 'right', marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                        更新时间: {new Date(trendData.update_time).toLocaleString()}
                    </Text>
                </div>
            )}
        </Card>
    );
};

export default IndustryTrendPanel;
