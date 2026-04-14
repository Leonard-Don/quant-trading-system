import React, { useState } from 'react';
import {
    Layout,
    Row,
    Col,
    Card,
    Tabs,
    Spin,
    Empty,
    Tag,
    Button,
    Select,
    Space,
    Statistic,
    Modal,
    Tooltip
} from 'antd';
import {
    FireOutlined,
    BranchesOutlined,
    ReloadOutlined,
    CrownOutlined
} from '@ant-design/icons';
import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    ReferenceLine,
    Tooltip as RechartsTooltip,
    ResponsiveContainer
} from 'recharts';
import IndustryHeatmap from './IndustryHeatmap';
import IndustryTrendPanel from './IndustryTrendPanel';
import LeaderStockPanel from './LeaderStockPanel';
import IndustryRotationChart from './IndustryRotationChart';
import ApiStatusIndicator from './ApiStatusIndicator';
import StockDetailModal from './StockDetailModal';
import MiniSparkline from './common/MiniSparkline';
import IndustryScoreRadarModal from './industry/IndustryScoreRadarModal';
import IndustrySavedViewsPanel from './industry/IndustrySavedViewsPanel';
import IndustryRankingPanel from './industry/IndustryRankingPanel';
import IndustryAlertsPanel from './industry/IndustryAlertsPanel';
import IndustryWatchlistPanel from './industry/IndustryWatchlistPanel';
import IndustryMarketSnapshotBar from './industry/IndustryMarketSnapshotBar';
import IndustryResearchFocusPanel from './industry/IndustryResearchFocusPanel';
import IndustryReplayPanel from './industry/IndustryReplayPanel';
import IndustryHeatmapStateBar from './industry/IndustryHeatmapStateBar';
import { INDUSTRY_URL_DEFAULTS } from './industry/useIndustryUrlState';
import useIndustryDashboardData from './industry/useIndustryDashboardData';
import { useSafeMessageApi } from '../utils/messageApi';
import {
    INDUSTRY_ALERT_RECENCY_OPTIONS,
    INDUSTRY_ALERT_KIND_OPTIONS,
    formatIndustryAlertMoneyFlow,
    getIndustryScoreTone,
    formatIndustryAlertSeenLabel,
    getMarketCapBadgeMeta,
} from './industry/industryShared';

const { Option } = Select;
const INDUSTRY_TIMEFRAME_LABELS = { 1: '1日', 5: '5日', 10: '10日', 20: '20日', 60: '60日' };
const INDUSTRY_SIZE_METRIC_LABELS = { market_cap: '按市值', net_inflow: '按净流入', turnover: '按成交额(估)' };
const INDUSTRY_COLOR_METRIC_LABELS = {
    change_pct: '看涨跌',
    net_inflow_ratio: '看净流入%',
    turnover_rate: '看换手率',
    pe_ttm: '看市盈率',
    pb: '看市净率',
};
const INDUSTRY_FILTER_LABELS = {
    live: '实时市值',
    snapshot: '快照市值',
    proxy: '代理市值',
    estimated: '估算市值',
};
const INDUSTRY_RANK_TYPE_LABELS = {
    gainers: '涨幅榜',
    losers: '跌幅榜',
};
const INDUSTRY_RANK_SORT_LABELS = {
    change_pct: '按涨跌幅',
    total_score: '按综合得分',
    money_flow: '按资金流向',
    industry_volatility: '按波动率',
};
const INDUSTRY_VOLATILITY_FILTER_LABELS = {
    all: '全部波动',
    low: '低波动',
    medium: '中波动',
    high: '高波动',
};
const INDUSTRY_RANKING_MARKET_CAP_FILTER_LABELS = {
    all: '全部市值来源',
    live: '实时市值',
    snapshot: '快照市值',
    proxy: '代理市值',
    estimated: '估算市值',
};
const PANEL_SURFACE = 'var(--bg-secondary)';
const PANEL_BORDER = '1px solid var(--border-color)';
const PANEL_SHADOW = '0 1px 2px rgba(0,0,0,0.03)';
const PANEL_MUTED = 'var(--text-muted)';
const TEXT_PRIMARY = 'var(--text-primary)';
const TEXT_SECONDARY = 'var(--text-secondary)';
const CLUSTER_COLORS = ['#ff4d4f', '#1890ff', '#52c41a', '#faad14', '#eb2f96'];

/**
 * 行业分析主 Dashboard
 * 整合热力图、行业趋势、龙头股面板、行业排名等功能
 */
const IndustryDashboard = () => {
    const message = useSafeMessageApi();
    const [detailVisible, setDetailVisible] = useState(false);
    const [heatmapFullscreen, setHeatmapFullscreen] = useState(false);
    const [scoreRadarRecord, setScoreRadarRecord] = useState(null);

    const data = useIndustryDashboardData({ message });

    const handleIndustryClickWithDetail = (industryName) => {
        data.handleIndustryClick(industryName);
        setDetailVisible(true);
    };

    const openSelectedIndustryDetailWithModal = () => {
        data.openSelectedIndustryDetail();
        setDetailVisible(true);
    };

    // 热门行业表格列
    const hotIndustryColumns = [
        {
            title: '排名',
            dataIndex: 'rank',
            key: 'rank',
            width: 48,
            render: (rank) => {
                const medals = ['🥇', '🥈', '🥉'];
                if (rank <= 3) return <span style={{ fontSize: 16 }}>{medals[rank - 1]}</span>;
                return <span style={{ color: PANEL_MUTED, fontSize: 12, fontWeight: 600 }}>{rank}</span>;
            }
        },
        {
            title: '行业',
            dataIndex: 'industry_name',
            key: 'industry_name',
            render: (name, record) => {
                const sourceMeta = getMarketCapBadgeMeta(record.marketCapSource);
                const volatilityMeta = data.getIndustryVolatilityMeta(record.industryVolatility, record.industryVolatilitySource);
                return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <Button
                            type="link"
                            size="small"
                            onClick={() => handleIndustryClickWithDetail(name)}
                            style={{ padding: 0, height: 'auto', width: 'fit-content', fontWeight: 600, fontSize: 13 }}
                        >
                            {name}
                        </Button>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            <Tag
                                color={sourceMeta.color}
                                data-testid="industry-market-cap-source-tag"
                                data-market-cap-filter={sourceMeta.filter}
                                style={{ margin: 0, width: 'fit-content', fontSize: 10, lineHeight: '15px', paddingInline: 6, cursor: 'pointer', borderRadius: 999 }}
                                onClick={() => data.jumpToMarketCapFilter(sourceMeta.filter)}
                            >
                                {sourceMeta.label}
                            </Tag>
                            {volatilityMeta.value > 0 && (
                                <Tooltip title={`区间波动率 ${volatilityMeta.value.toFixed(2)}% · ${volatilityMeta.sourceLabel}`}>
                                    <Tag color={volatilityMeta.color} style={{ margin: 0, width: 'fit-content', fontSize: 10, lineHeight: '15px', paddingInline: 6, borderRadius: 999 }}>
                                        {volatilityMeta.label}
                                    </Tag>
                                </Tooltip>
                            )}
                        </div>
                    </div>
                );
            }
        },
        {
            title: '综合得分',
            dataIndex: 'score',
            key: 'score',
            width: 82,
            render: (score, record) => (
                <Button
                    type="link"
                    size="small"
                    data-testid="industry-score-radar-trigger"
                    onClick={() => setScoreRadarRecord(record)}
                    style={{
                        padding: 0,
                        height: 'auto',
                        minWidth: 0,
                        fontWeight: 700,
                        fontSize: 13,
                        color: getIndustryScoreTone(score),
                    }}
                >
                    {Number(score || 0).toFixed(2)}
                </Button>
            )
        },
        {
            title: '涨跌幅',
            dataIndex: 'change_pct',
            key: 'change_pct',
            width: 84,
            sorter: (a, b) => a.change_pct - b.change_pct,
            render: (value) => (
                <span style={{ color: value >= 0 ? '#cf1322' : '#3f8600', fontWeight: 700, fontSize: 13 }}>
                    {value >= 0 ? '+' : ''}{(value || 0).toFixed(2)}%
                </span>
            )
        },
        {
            title: '走势',
            dataIndex: 'mini_trend',
            key: 'mini_trend',
            width: 98,
            render: (points, record) => (
                <Tooltip title={`${record.industry_name} 近5日相对走势`}>
                    <div style={{ width: 88 }}>
                        <MiniSparkline points={points} ariaLabel={`${record.industry_name} 近5日走势`} />
                    </div>
                </Tooltip>
            )
        },
        {
            title: '资金流向',
            dataIndex: 'money_flow',
            key: 'money_flow',
            width: 92,
            sorter: (a, b) => (a.money_flow || 0) - (b.money_flow || 0),
            render: (value) => {
                const displayValue = (value || 0) / 100000000;
                return (
                    <span style={{ color: displayValue >= 0 ? '#cf1322' : '#3f8600', fontSize: 12 }}>
                        {displayValue >= 0 ? '+' : ''}{displayValue.toFixed(2)}亿
                    </span>
                );
            }
        },
        {
            title: '动量',
            dataIndex: 'momentum',
            key: 'momentum',
            width: 80,
            sorter: (a, b) => (a.momentum || 0) - (b.momentum || 0),
            render: (value) => {
                const v = value || 0;
                return (
                    <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600', fontSize: 11, fontWeight: 600 }}>
                        {v >= 0 ? '↑' : '↓'}{Math.abs(v).toFixed(2)}
                    </span>
                );
            }
        },
        {
            title: '波动率',
            dataIndex: 'industryVolatility',
            key: 'industryVolatility',
            width: 110,
            sorter: (a, b) => (a.industryVolatility || 0) - (b.industryVolatility || 0),
            render: (value, record) => {
                const meta = data.getIndustryVolatilityMeta(value, record.industryVolatilitySource);
                if (!meta.value) return <span style={{ color: PANEL_MUTED }}>-</span>;
                return (
                    <Tooltip title={`区间波动率 ${meta.value.toFixed(2)}% · ${meta.sourceLabel}`}>
                        <Tag color={meta.color} style={{ margin: 0, borderRadius: 999, fontSize: 10, paddingInline: 6 }}>
                            {meta.label} {meta.value.toFixed(1)}%
                        </Tag>
                    </Tooltip>
                );
            }
        },
        {
            title: '市值(亿)',
            dataIndex: 'total_market_cap',
            key: 'total_market_cap',
            width: 82,
            sorter: (a, b) => (a.total_market_cap || 0) - (b.total_market_cap || 0),
            render: (value) => (
                <span style={{ color: TEXT_SECONDARY, fontSize: 12 }}>
                    {value ? ((value || 0) / 100000000).toFixed(0) : '-'}
                </span>
            )
        },
        {
            title: '成分股',
            dataIndex: 'stock_count',
            key: 'stock_count',
            width: 64,
            sorter: (a, b) => (a.stock_count || 0) - (b.stock_count || 0),
            render: (value) => <span style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{value || 0}</span>,
        },
        {
            title: '操作',
            key: 'action',
            width: 86,
            render: (_, record) => (
                <Space size={8}>
                    <Button className="industry-inline-link" type="link" size="small" onClick={() => handleIndustryClickWithDetail(record.industry_name)} style={{ padding: 0, height: 'auto', fontSize: 12 }}>详情</Button>
                    <Button className="industry-inline-link" type="link" size="small" onClick={() => data.handleAddToComparison(record.industry_name)} style={{ padding: 0, height: 'auto', color: 'var(--accent-secondary)', fontSize: 12 }}>对比</Button>
                </Space>
            )
        }
    ];

    // 行业成分股表格列
    const stockColumns = [
        {
            title: '排名',
            dataIndex: 'rank',
            key: 'rank',
            width: 55
        },
        {
            title: '代码',
            dataIndex: 'symbol',
            key: 'symbol',
            width: 80,
            render: (symbol) => <Tag color="blue">{symbol}</Tag>
        },
        {
            title: '名称',
            dataIndex: 'name',
            key: 'name',
            width: 100
        },
        {
            title: '得分',
            dataIndex: 'total_score',
            key: 'total_score',
            width: 80,
            render: (score) => {
                if (score === null || score === undefined || Number(score) <= 0) {
                    return '-';
                }
                return (
                    <Tooltip title={`综合评分 ${Number(score).toFixed(1)}`}>
                        <span style={{ fontWeight: 700, color: getIndustryScoreTone(score) }}>
                            {Number(score).toFixed(1)}
                        </span>
                    </Tooltip>
                );
            }
        },
        {
            title: '涨跌幅',
            dataIndex: 'change_pct',
            key: 'change_pct',
            width: 90,
            render: (value) => {
                if (value === null || value === undefined) {
                    return '-';
                }
                return (
                    <span style={{ color: value >= 0 ? '#cf1322' : '#3f8600' }}>
                        {value >= 0 ? '+' : ''}{value.toFixed(2)}%
                    </span>
                );
            }
        },
        {
            title: '主力净流入',
            dataIndex: 'money_flow',
            key: 'money_flow',
            width: 110,
            render: (value) => (
                value === null || value === undefined
                    ? '-'
                    : (
                        <span style={{ color: Number(value) >= 0 ? '#cf1322' : '#3f8600' }}>
                            {formatIndustryAlertMoneyFlow(Number(value))}
                        </span>
                    )
            )
        },
        {
            title: '换手率',
            dataIndex: 'turnover_rate',
            key: 'turnover_rate',
            width: 86,
            render: (_, record) => {
                const value = record.turnover_rate ?? record.turnover;
                return value === null || value === undefined || Number.isNaN(Number(value))
                    ? '-'
                    : `${Number(value).toFixed(2)}%`;
            }
        },
        {
            title: '市值(亿)',
            dataIndex: 'market_cap',
            key: 'market_cap',
            width: 90,
            render: (value) => (
                value === null || value === undefined ? '-' : (value / 100000000).toFixed(1)
            )
        },
        {
            title: 'PE',
            dataIndex: 'pe_ratio',
            key: 'pe_ratio',
            width: 70,
            render: (value) => (
                value === null || value === undefined || value <= 0 ? '-' : value.toFixed(1)
            )
        }
    ];

    // 渲染聚类分析
    const renderClusters = () => {
        if (data.loadingClusters) {
            return <Spin />;
        }

        if (data.clusterError && !data.clusters) {
            return (
                <Empty description={data.clusterError}>
                    <Button
                        className="industry-empty-action"
                        type="primary"
                        onClick={() => data.loadClusters(false)}
                        icon={<ReloadOutlined />}
                    >
                        重试
                    </Button>
                </Empty>
            );
        }

        if (!data.clusters) {
            return (
                <Button className="industry-empty-action" onClick={() => data.loadClusters(false)} icon={<BranchesOutlined />}>
                    开始聚类分析
                </Button>
            );
        }

        return (
            <div>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                    {Object.entries(data.clusters.cluster_stats || {}).map(([idx, stats]) => {
                        const isHot = parseInt(idx) === data.clusters.hot_cluster;
                        return (
                            <Col span={12} key={idx}>
                                <Card
                                    size="small"
                                    title={
                                        <span>
                                            {isHot && (
                                                <FireOutlined style={{ color: '#ff4d4f', marginRight: 4 }} />
                                            )}
                                            {isHot ? '🔥 热门簇' : `簇 ${parseInt(idx) + 1}`}
                                        </span>
                                    }
                                    style={{
                                        borderColor: isHot ? '#ff4d4f' : undefined,
                                        boxShadow: isHot ? '0 0 8px rgba(255,77,79,0.3)' : undefined
                                    }}
                                >
                                    <Row gutter={8}>
                                        <Col span={12}>
                                            <Statistic
                                                title="平均动量"
                                                value={Math.abs(stats.avg_momentum) < 0.005 ? '0.00' : stats.avg_momentum?.toFixed(2)}
                                                suffix="%"
                                                valueStyle={{
                                                    color: stats.avg_momentum >= 0 ? '#cf1322' : '#3f8600',
                                                    fontSize: 14
                                                }}
                                            />
                                        </Col>
                                        <Col span={12}>
                                            <Statistic
                                                title="平均资金强度"
                                                value={Math.abs(stats.avg_flow) < 0.005 ? '0.00' : stats.avg_flow?.toFixed(2)}
                                                valueStyle={{
                                                    color: (stats.avg_flow || 0) >= 0 ? '#cf1322' : '#3f8600',
                                                    fontSize: 14
                                                }}
                                            />
                                        </Col>
                                    </Row>
                                    <div style={{ marginTop: 8 }}>
                                        <div style={{ color: PANEL_MUTED, fontSize: 12, marginBottom: 4 }}>
                                            行业数: {stats.count}
                                        </div>
                                        <div>
                                            {(stats.industries || []).slice(0, 4).map(ind => (
                                                <Tag
                                                    key={ind}
                                                    size="small"
                                                    style={{ cursor: 'pointer', marginBottom: 4 }}
                                                    onClick={() => handleIndustryClickWithDetail(ind)}
                                                >
                                                    {ind}
                                                </Tag>
                                            ))}
                                            {(stats.industries?.length || 0) > 4 && (
                                                <Tag size="small" style={{ color: PANEL_MUTED }}>
                                                    +{stats.industries.length - 4}
                                                </Tag>
                                            )}
                                        </div>
                                    </div>
                                </Card>
                            </Col>
                        );
                    })}
                </Row>
            </div>
        );
    };

    // 聚类散点图
    const renderClusterScatterChart = () => {
        if (data.loadingClusters && !data.clusters) {
            return (
                <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>
                        聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span>
                    </div>
                    <div
                        style={{
                            minHeight: 280,
                            borderRadius: 12,
                            border: PANEL_BORDER,
                            background: PANEL_SURFACE,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            gap: 10,
                        }}
                    >
                        <Spin />
                        <div style={{ fontSize: 12, color: PANEL_MUTED }}>聚类分析计算中，首次加载可能需要几秒</div>
                    </div>
                </div>
            );
        }

        if (!data.clusters) return null;

        const scatterData = (data.clusters.points || []).map(point => ({
            name: point.industry_name,
            cluster: point.cluster,
            x: point.weighted_change || 0,
            y: point.flow_strength || 0,
        }));
        const clusterKeys = Object.keys(data.clusters.cluster_stats || {}).length > 0
            ? Object.keys(data.clusters.cluster_stats || {}).map(k => parseInt(k))
            : [...new Set(scatterData.map(d => d.cluster))];

        if (scatterData.length === 0) {
            return (
                <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>
                        聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span>
                    </div>
                    <Empty description="当前暂无可展示的聚类点位" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
            );
        }

        return (
            <div style={{ marginTop: 16 }}>
                <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span></div>
                <div style={{ position: 'relative', borderRadius: 12, overflow: 'hidden' }}>
                    <div style={{ position: 'absolute', top: 8, left: 12, zIndex: 1 }}>
                        <Tag color="red" style={{ margin: 0, borderRadius: 999 }}>强势流入</Tag>
                    </div>
                    <div style={{ position: 'absolute', top: 8, right: 12, zIndex: 1 }}>
                        <Tag color="orange" style={{ margin: 0, borderRadius: 999 }}>弱势流入</Tag>
                    </div>
                    <div style={{ position: 'absolute', bottom: 8, left: 12, zIndex: 1 }}>
                        <Tag color="green" style={{ margin: 0, borderRadius: 999 }}>强势撤退</Tag>
                    </div>
                    <div style={{ position: 'absolute', bottom: 8, right: 12, zIndex: 1 }}>
                        <Tag color="blue" style={{ margin: 0, borderRadius: 999 }}>弱势修复</Tag>
                    </div>
                    <ResponsiveContainer width="100%" height={280}>
                        <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis
                                type="number"
                                dataKey="x"
                                name="动量"
                                tick={{ fontSize: 11 }}
                                tickFormatter={v => `${v.toFixed(1)}%`}
                            />
                            <YAxis
                                type="number"
                                dataKey="y"
                                name="资金强度"
                                tick={{ fontSize: 11 }}
                                domain={[-1.05, 1.05]}
                                tickFormatter={v => `${v.toFixed(1)}`}
                            />
                            <ReferenceLine x={0} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />
                            <ReferenceLine y={0} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />
                            <RechartsTooltip
                                formatter={(value, name) => [
                                    typeof value === 'number' ? value.toFixed(2) : value,
                                    name === 'x' ? '动量' : name === 'y' ? '资金强度' : name
                                ]}
                                labelFormatter={() => ''}
                                content={({ active, payload }) => {
                                    if (active && payload && payload.length) {
                                        const d = payload[0]?.payload;
                                        return (
                                            <div style={{
                                                background: 'rgba(0,0,0,0.75)',
                                                color: '#fff',
                                                padding: '6px 10px',
                                                borderRadius: 4,
                                                fontSize: 12
                                            }}>
                                                <div style={{ fontWeight: 'bold' }}>{d?.name}</div>
                                                <div>动量: {d?.x?.toFixed(2)}%</div>
                                                <div>资金强度: {d?.y?.toFixed(2)}</div>
                                            </div>
                                        );
                                    }
                                    return null;
                                }}
                            />
                            {clusterKeys.map(clusterIdx => {
                                const isHot = clusterIdx === data.clusters.hot_cluster;
                                const clusterData = scatterData.filter(d => d.cluster === clusterIdx);
                                return (
                                    <Scatter
                                        key={clusterIdx}
                                        name={isHot ? '🔥 热门簇' : `簇 ${clusterIdx + 1}`}
                                        data={clusterData}
                                        fill={CLUSTER_COLORS[clusterIdx % CLUSTER_COLORS.length]}
                                        shape={(props) => {
                                            const selected = data.selectedClusterPoint?.name === props?.payload?.name;
                                            return (
                                                <circle
                                                    cx={props.cx}
                                                    cy={props.cy}
                                                    r={selected ? 7 : 5}
                                                    fill={props.fill}
                                                    stroke={selected ? '#111827' : '#ffffff'}
                                                    strokeWidth={selected ? 2.5 : 1.5}
                                                    style={{ cursor: 'pointer' }}
                                                />
                                            );
                                        }}
                                        onClick={(payload) => {
                                            const nextPoint = payload?.payload || payload;
                                            if (nextPoint?.name) {
                                                data.setSelectedClusterPoint(nextPoint);
                                            }
                                        }}
                                    />
                                );
                            })}
                        </ScatterChart>
                    </ResponsiveContainer>
                </div>
                {data.selectedClusterPoint && (
                    <Card
                        size="small"
                        style={{ marginTop: 12, borderRadius: 12, border: '1px solid rgba(24,144,255,0.18)' }}
                        styles={{ body: { padding: '12px 14px' } }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <span style={{ fontSize: 15, fontWeight: 700, color: TEXT_PRIMARY }}>{data.selectedClusterPoint.name}</span>
                                    <Tag color={data.selectedClusterPoint.cluster === data.clusters.hot_cluster ? 'red' : 'blue'} style={{ margin: 0, borderRadius: 999 }}>
                                        {data.selectedClusterPoint.cluster === data.clusters.hot_cluster ? '热门簇' : `簇 ${data.selectedClusterPoint.cluster + 1}`}
                                    </Tag>
                                </div>
                                <div style={{ fontSize: 12, color: PANEL_MUTED }}>
                                    动量 {data.selectedClusterPoint.x?.toFixed(2)}% · 资金强度 {data.selectedClusterPoint.y?.toFixed(2)}
                                </div>
                            </div>
                            <Space size={8} wrap>
                                <Button size="small" type="primary" onClick={() => data.setSelectedIndustry(data.selectedClusterPoint.name)}>
                                    聚焦
                                </Button>
                                <Button size="small" onClick={() => handleIndustryClickWithDetail(data.selectedClusterPoint.name)}>
                                    查看详情
                                </Button>
                                <Button size="small" onClick={() => data.handleAddToComparison(data.selectedClusterPoint.name)}>
                                    加入对比
                                </Button>
                            </Space>
                        </div>
                    </Card>
                )}
            </div>
        );
    };

    const activeHeatmapStateTags = [];
    if (data.marketCapFilter !== INDUSTRY_URL_DEFAULTS.marketCapFilter) {
        activeHeatmapStateTags.push({ key: 'market_cap_filter', label: '来源', value: INDUSTRY_FILTER_LABELS[data.marketCapFilter] || data.marketCapFilter });
    }
    if (data.heatmapViewState.timeframe !== INDUSTRY_URL_DEFAULTS.timeframe) {
        activeHeatmapStateTags.push({ key: 'timeframe', label: '周期', value: INDUSTRY_TIMEFRAME_LABELS[data.heatmapViewState.timeframe] || `${data.heatmapViewState.timeframe}日` });
    }
    if (data.heatmapViewState.sizeMetric !== INDUSTRY_URL_DEFAULTS.sizeMetric) {
        activeHeatmapStateTags.push({ key: 'size_metric', label: '大小', value: INDUSTRY_SIZE_METRIC_LABELS[data.heatmapViewState.sizeMetric] || data.heatmapViewState.sizeMetric });
    }
    if (data.heatmapViewState.colorMetric !== INDUSTRY_URL_DEFAULTS.colorMetric) {
        activeHeatmapStateTags.push({ key: 'color_metric', label: '颜色', value: INDUSTRY_COLOR_METRIC_LABELS[data.heatmapViewState.colorMetric] || data.heatmapViewState.colorMetric });
    }
    if (data.heatmapViewState.displayCount !== INDUSTRY_URL_DEFAULTS.displayCount) {
        activeHeatmapStateTags.push({ key: 'display_count', label: '范围', value: data.heatmapViewState.displayCount === 0 ? '全部' : `Top ${data.heatmapViewState.displayCount}` });
    }
    if (data.heatmapViewState.searchTerm !== INDUSTRY_URL_DEFAULTS.searchTerm) {
        activeHeatmapStateTags.push({ key: 'search', label: '搜索', value: data.heatmapViewState.searchTerm });
    }
    if (Array.isArray(data.heatmapLegendRange) && data.heatmapLegendRange.length === 2) {
        activeHeatmapStateTags.push({
            key: 'legend_range',
            label: '色阶',
            value: `${Number(data.heatmapLegendRange[0]).toFixed(1)} ~ ${Number(data.heatmapLegendRange[1]).toFixed(1)}`,
        });
    }
    const hasActiveHeatmapState = activeHeatmapStateTags.length > 0;
    const shouldShowHeatmapStateBar = hasActiveHeatmapState && ['heatmap', 'clusters'].includes(data.activeTab);

    const activeRankingStateTags = [];
    if (data.rankType !== INDUSTRY_URL_DEFAULTS.rankType) {
        activeRankingStateTags.push({ key: 'rank_type', label: '榜单', value: INDUSTRY_RANK_TYPE_LABELS[data.rankType] || data.rankType });
    }
    if (data.sortBy !== INDUSTRY_URL_DEFAULTS.sortBy) {
        activeRankingStateTags.push({ key: 'sort_by', label: '排序', value: INDUSTRY_RANK_SORT_LABELS[data.sortBy] || data.sortBy });
    }
    if (data.lookbackDays !== INDUSTRY_URL_DEFAULTS.lookbackDays) {
        activeRankingStateTags.push({ key: 'lookback', label: '周期', value: `近${data.lookbackDays}日` });
    }
    if (data.volatilityFilter !== INDUSTRY_URL_DEFAULTS.volatilityFilter) {
        activeRankingStateTags.push({ key: 'volatility_filter', label: '波动', value: INDUSTRY_VOLATILITY_FILTER_LABELS[data.volatilityFilter] || data.volatilityFilter });
    }
    if (data.rankingMarketCapFilter !== INDUSTRY_URL_DEFAULTS.rankingMarketCapFilter) {
        activeRankingStateTags.push({ key: 'market_cap_filter', label: '市值来源', value: INDUSTRY_RANKING_MARKET_CAP_FILTER_LABELS[data.rankingMarketCapFilter] || data.rankingMarketCapFilter });
    }

    const tabItems = [
        {
            label: '热力图',
            key: 'heatmap',
            children: (
                <IndustryHeatmap
                    onIndustryClick={handleIndustryClickWithDetail}
                    onDataLoad={data.handleHeatmapDataLoad}
                    onLeadingStockClick={data.handleLeadingStockClick}
                    replaySnapshot={data.activeReplaySnapshot}
                    marketCapFilter={data.marketCapFilter}
                    onClearMarketCapFilter={() => data.setMarketCapFilter('all')}
                    onSelectMarketCapFilter={data.jumpToMarketCapFilter}
                    timeframeValue={data.heatmapViewState.timeframe}
                    sizeMetricValue={data.heatmapViewState.sizeMetric}
                    colorMetricValue={data.heatmapViewState.colorMetric}
                    displayCountValue={data.heatmapViewState.displayCount}
                    searchTermValue={data.heatmapViewState.searchTerm}
                    legendRangeValue={data.heatmapLegendRange}
                    onTimeframeChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, timeframe: value }))}
                    onSizeMetricChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, sizeMetric: value }))}
                    onColorMetricChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, colorMetric: value }))}
                    onDisplayCountChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, displayCount: value }))}
                    onSearchTermChange={(value) => data.setHeatmapViewState(prev => ({ ...prev, searchTerm: value }))}
                    onLegendRangeChange={data.setHeatmapLegendRange}
                    focusControlKey={data.focusedHeatmapControlKey}
                    showStats={false}
                    onToggleFullscreen={() => setHeatmapFullscreen((current) => !current)}
                    isFullscreen={false}
                />
            )
        },
        {
            label: '排行榜',
            key: 'ranking',
            children: (
                <IndustryRankingPanel
                    rankType={data.rankType}
                    onRankTypeChange={data.setRankType}
                    sortBy={data.sortBy}
                    onSortByChange={data.setSortBy}
                    lookbackDays={data.lookbackDays}
                    onLookbackDaysChange={data.setLookbackDays}
                    volatilityFilter={data.volatilityFilter}
                    onVolatilityFilterChange={data.setVolatilityFilter}
                    rankingMarketCapFilter={data.rankingMarketCapFilter}
                    onRankingMarketCapFilterChange={data.setRankingMarketCapFilter}
                    loadingHot={data.loadingHot}
                    focusedRankingControlKey={data.focusedRankingControlKey}
                    filteredHotIndustries={data.filteredHotIndustries}
                    hotIndustryColumns={hotIndustryColumns}
                    onReload={() => data.loadHotIndustries(50, data.rankType, data.sortBy, data.lookbackDays)}
                    onIndustryClick={handleIndustryClickWithDetail}
                    activeRankingStateTags={activeRankingStateTags}
                    onFocusRankingControl={data.focusRankingControl}
                    onClearRankingStateTag={data.clearRankingStateTag}
                    onResetRankingViewState={data.resetRankingViewState}
                    panelSurface={PANEL_SURFACE}
                    panelBorder={PANEL_BORDER}
                    panelShadow={PANEL_SHADOW}
                    panelMuted={PANEL_MUTED}
                />
            )
        },
        {
            label: '聚类分析',
            key: 'clusters',
            children: (
                <Card
                    title="行业聚类分析"
                    extra={
                        <Space size={8} wrap>
                            <Select
                                value={data.clusterCount}
                                onChange={data.setClusterCount}
                                size="small"
                                style={{ width: 108 }}
                                disabled={data.loadingClusters}
                            >
                                <Option value={3}>3 个聚类</Option>
                                <Option value={4}>4 个聚类</Option>
                                <Option value={5}>5 个聚类</Option>
                                <Option value={6}>6 个聚类</Option>
                            </Select>
                            {data.clusters && (
                                <Button
                                    className="industry-inline-link"
                                    icon={<ReloadOutlined />}
                                    onClick={() => data.loadClusters(false)}
                                    size="small"
                                >
                                    重新分析
                                </Button>
                            )}
                        </Space>
                    }
                >
                    {renderClusters()}
                    {renderClusterScatterChart()}
                </Card>
            )
        },
        {
            label: '轮动对比',
            key: 'rotation',
            children: (
                <IndustryRotationChart
                    initialIndustries={data.comparisonIndustries.length > 0
                        ? data.comparisonIndustries
                        : (data.hotIndustries || []).slice(0, 3).map(i => i.industry_name)
                    }
                />
            )
        }
    ];

    return (
        <Layout style={{ padding: 24, background: 'var(--bg-primary)', minHeight: '100vh' }}>
            <Row gutter={[24, 24]}>
                {/* 左侧：热力图和热门行业 */}
                <Col xs={24} lg={16}>
                    <IndustryMarketSnapshotBar
                        heatmapSummary={data.heatmapSummary}
                        focusedHeatmapControlKey={data.focusedHeatmapControlKey}
                        marketCapFilter={data.marketCapFilter}
                        onIndustryClick={handleIndustryClickWithDetail}
                        onToggleMarketCapFilter={data.toggleMarketCapFilter}
                        onResetMarketCapFilter={() => data.setMarketCapFilter('all')}
                        statusIndicator={<ApiStatusIndicator />}
                    />

                    <Card
                        size="small"
                        style={{
                            marginBottom: 12,
                            background: data.industryActionPosture.level === 'warning'
                                ? 'linear-gradient(180deg, rgba(250, 173, 20, 0.10) 0%, rgba(255,255,255,0.72) 100%)'
                                : data.industryActionPosture.level === 'info'
                                    ? 'linear-gradient(180deg, rgba(22, 119, 255, 0.08) 0%, rgba(255,255,255,0.72) 100%)'
                                    : 'linear-gradient(180deg, rgba(82, 196, 26, 0.08) 0%, rgba(255,255,255,0.72) 100%)',
                            border: data.industryActionPosture.level === 'warning'
                                ? '1px solid rgba(250, 173, 20, 0.35)'
                                : data.industryActionPosture.level === 'info'
                                    ? '1px solid rgba(22, 119, 255, 0.24)'
                                    : '1px solid rgba(82, 196, 26, 0.22)',
                        }}
                    >
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            <div style={{ fontSize: 11, color: PANEL_MUTED, fontWeight: 700, letterSpacing: '0.04em' }}>行业动作姿势</div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: TEXT_PRIMARY }}>{data.industryActionPosture.title}</div>
                            <div style={{ fontSize: 12, lineHeight: 1.7, color: TEXT_PRIMARY }}>{data.industryActionPosture.actionHint}</div>
                            <div style={{ fontSize: 11, lineHeight: 1.7, color: TEXT_SECONDARY }}>{data.industryActionPosture.reason}</div>
                        </div>
                    </Card>

                    <IndustryHeatmapStateBar
                        visible={shouldShowHeatmapStateBar}
                        activeHeatmapStateTags={activeHeatmapStateTags}
                        onFocusHeatmapControl={data.focusHeatmapControl}
                        onClearHeatmapStateTag={data.clearHeatmapStateTag}
                        onResetHeatmapViewState={data.resetHeatmapViewState}
                        panelSurface={PANEL_SURFACE}
                        panelBorder={PANEL_BORDER}
                        panelShadow={PANEL_SHADOW}
                        panelMuted={PANEL_MUTED}
                    />

                    <Tabs
                        activeKey={data.activeTab}
                        onChange={data.setActiveTab}
                        items={tabItems}
                    />

                    <IndustryReplayPanel
                        heatmapReplaySnapshots={data.heatmapReplaySnapshots}
                        activeReplaySnapshot={data.activeReplaySnapshot}
                        latestReplaySnapshot={data.latestReplaySnapshot}
                        replayWindow={data.replayWindow}
                        setReplayWindow={data.setReplayWindow}
                        heatmapReplayWindowOptions={data.heatmapReplayWindowOptions}
                        comparisonBaseSnapshotId={data.comparisonBaseSnapshotId}
                        setComparisonBaseSnapshotId={data.setComparisonBaseSnapshotId}
                        filteredReplaySnapshots={data.filteredReplaySnapshots}
                        replayTargetSnapshot={data.replayTargetSnapshot}
                        formatReplaySnapshotTime={data.formatReplaySnapshotTime}
                        industryTimeframeLabels={INDUSTRY_TIMEFRAME_LABELS}
                        setActiveTab={data.setActiveTab}
                        setSelectedReplaySnapshotId={data.setSelectedReplaySnapshotId}
                        setHeatmapViewState={data.setHeatmapViewState}
                        setMarketCapFilter={data.setMarketCapFilter}
                        panelSurface={PANEL_SURFACE}
                        panelBorder={PANEL_BORDER}
                        panelShadow={PANEL_SHADOW}
                        panelMuted={PANEL_MUTED}
                        textPrimary={TEXT_PRIMARY}
                        textSecondary={TEXT_SECONDARY}
                        replayComparison={data.replayComparison}
                        activeReplayDiffIndustry={data.activeReplayDiffIndustry}
                        handleReplayDiffIndustrySelect={data.handleReplayDiffIndustrySelect}
                        handleIndustryClick={handleIndustryClickWithDetail}
                        getIndustryScoreTone={getIndustryScoreTone}
                        formatReplayDelta={data.formatReplayDelta}
                        replayIndustryDiffDetail={data.replayIndustryDiffDetail}
                        watchlistIndustries={data.watchlistIndustries}
                        toggleWatchlistIndustry={data.toggleWatchlistIndustry}
                        formatReplayMetricPercent={data.formatReplayMetricPercent}
                        formatReplayMetricMoney={data.formatReplayMetricMoney}
                    />

                    <IndustryAlertsPanel
                        industryAlertsWithSeverity={data.industryAlertsWithSeverity}
                        rawIndustryAlerts={data.rawIndustryAlerts}
                        focusIndustrySuggestions={data.focusIndustrySuggestions}
                        subscribedAlertNewCount={data.subscribedAlertNewCount}
                        industryAlertSubscription={data.industryAlertSubscription}
                        desktopAlertNotifications={data.desktopAlertNotifications}
                        industryAlertRule={data.industryAlertRule}
                        setIndustryAlertRule={data.setIndustryAlertRule}
                        industryAlertRecency={data.industryAlertRecency}
                        setIndustryAlertRecency={data.setIndustryAlertRecency}
                        industryAlertKindOptions={INDUSTRY_ALERT_KIND_OPTIONS}
                        industryAlertRecencyOptions={INDUSTRY_ALERT_RECENCY_OPTIONS}
                        setIndustryAlertSubscription={data.setIndustryAlertSubscription}
                        industryAlertThresholds={data.industryAlertThresholds}
                        setIndustryAlertThresholds={data.setIndustryAlertThresholds}
                        requestDesktopAlertPermission={data.requestDesktopAlertPermission}
                        toggleWatchlistIndustry={data.toggleWatchlistIndustry}
                        watchlistIndustries={data.watchlistIndustries}
                        selectedIndustry={data.selectedIndustry}
                        setSelectedIndustry={data.setSelectedIndustry}
                        handleIndustryClick={handleIndustryClickWithDetail}
                        handleAddToComparison={data.handleAddToComparison}
                        alertTimelineEntries={data.alertTimelineEntries}
                        formatIndustryAlertSeenLabel={formatIndustryAlertSeenLabel}
                        message={message}
                    />

                    <IndustrySavedViewsPanel
                        draftName={data.savedViewDraftName}
                        onDraftNameChange={data.setSavedViewDraftName}
                        onSave={data.saveCurrentIndustryView}
                        savedViews={data.savedIndustryViews}
                        onApply={data.applySavedIndustryView}
                        onOverwrite={data.overwriteSavedIndustryView}
                        onRemove={data.removeSavedIndustryView}
                        onExport={data.handleExportSavedViews}
                        onImportClick={data.handleImportSavedViewsClick}
                    />
                    <input
                        ref={data.savedViewImportInputRef}
                        type="file"
                        accept="application/json,.json"
                        onChange={data.handleImportSavedViews}
                        style={{ display: 'none' }}
                    />
                </Col>

                {/* 右侧：龙头股推荐 */}
                <Col xs={24} lg={8}>
                    <IndustryResearchFocusPanel
                        selectedIndustry={data.selectedIndustry}
                        selectedIndustrySnapshot={data.selectedIndustrySnapshot}
                        selectedIndustryMarketCapBadge={data.selectedIndustryMarketCapBadge}
                        selectedIndustryVolatilityMeta={data.selectedIndustryVolatilityMeta}
                        selectedIndustryFocusNarrative={data.selectedIndustryFocusNarrative}
                        selectedIndustryScoreBreakdown={data.selectedIndustryScoreBreakdown}
                        selectedIndustryScoreSummary={data.selectedIndustryScoreSummary}
                        selectedIndustryReasons={data.selectedIndustryReasons}
                        selectedIndustryWatched={data.selectedIndustryWatched}
                        focusIndustrySuggestions={data.focusIndustrySuggestions}
                        onClearIndustry={() => data.setSelectedIndustry(null)}
                        onOpenIndustryDetail={openSelectedIndustryDetailWithModal}
                        onToggleWatchlist={() => data.toggleWatchlistIndustry(data.selectedIndustry)}
                        onAddToComparison={() => data.handleAddToComparison(data.selectedIndustry)}
                        onSelectIndustry={handleIndustryClickWithDetail}
                    />

                    <Card
                        size="small"
                        style={{ borderRadius: 12 }}
                        styles={{ body: { paddingTop: 10 } }}
                    >
                        <Tabs
                            defaultActiveKey="leaders"
                            items={[
                                {
                                    key: 'leaders',
                                    label: '龙头股',
                                    children: data.shouldRenderLeaderPanel ? (
                                        <LeaderStockPanel
                                            topN={5}
                                            topIndustries={5}
                                            perIndustry={3}
                                            focusIndustry={data.selectedIndustry}
                                            onClearFocusIndustry={() => data.setSelectedIndustry(null)}
                                        />
                                    ) : (
                                        <Card
                                            title={
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                                    <span>
                                                        <CrownOutlined style={{ marginRight: 8, color: '#faad14' }} />
                                                        龙头股推荐
                                                    </span>
                                                    <span style={{ fontSize: 11, color: TEXT_SECONDARY, fontWeight: 400 }}>首屏优先渲染行业热力图，龙头股榜单稍后加载</span>
                                                </div>
                                            }
                                            styles={{ body: { paddingTop: 20, paddingBottom: 20 } }}
                                        >
                                            <div style={{ textAlign: 'center', padding: '18px 0 10px' }}>
                                                <Spin size="small" />
                                                <div style={{ marginTop: 12, fontSize: 12, color: TEXT_SECONDARY }}>
                                                    正在后台准备龙头股榜单...
                                                </div>
                                            </div>
                                        </Card>
                                    ),
                                },
                                {
                                    key: 'watchlist',
                                    label: `观察列表${data.watchlistEntries.length > 0 ? ` (${data.watchlistEntries.length})` : ''}`,
                                    children: (
                                        <IndustryWatchlistPanel
                                            watchlistEntries={data.watchlistEntries}
                                            watchlistSuggestions={data.watchlistSuggestions}
                                            selectedIndustry={data.selectedIndustry}
                                            maxWatchlistIndustries={data.maxWatchlistIndustries}
                                            toggleWatchlistIndustry={data.toggleWatchlistIndustry}
                                            setSelectedIndustry={data.setSelectedIndustry}
                                            handleIndustryClick={handleIndustryClickWithDetail}
                                            handleAddToComparison={data.handleAddToComparison}
                                            formatIndustryAlertMoneyFlow={formatIndustryAlertMoneyFlow}
                                        />
                                    ),
                                },
                            ]}
                        />
                    </Card>
                </Col>
            </Row>

            <Modal
                title="行业热力图全屏"
                open={heatmapFullscreen}
                onCancel={() => setHeatmapFullscreen(false)}
                footer={null}
                width="92vw"
                style={{ top: 20 }}
                destroyOnHidden
                modalRender={(node) => <div data-testid="industry-heatmap-fullscreen-modal">{node}</div>}
                styles={{ body: { paddingTop: 8 } }}
            >
                <IndustryHeatmap
                    onIndustryClick={handleIndustryClickWithDetail}
                    onDataLoad={data.handleHeatmapDataLoad}
                    onLeadingStockClick={data.handleLeadingStockClick}
                    replaySnapshot={data.activeReplaySnapshot}
                    marketCapFilter={data.marketCapFilter}
                    onClearMarketCapFilter={() => data.setMarketCapFilter('all')}
                    onSelectMarketCapFilter={data.jumpToMarketCapFilter}
                    timeframeValue={data.heatmapViewState.timeframe}
                    sizeMetricValue={data.heatmapViewState.sizeMetric}
                    colorMetricValue={data.heatmapViewState.colorMetric}
                    displayCountValue={data.heatmapViewState.displayCount}
                    searchTermValue={data.heatmapViewState.searchTerm}
                    legendRangeValue={data.heatmapLegendRange}
                    onTimeframeChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, timeframe: value }))}
                    onSizeMetricChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, sizeMetric: value }))}
                    onColorMetricChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, colorMetric: value }))}
                    onDisplayCountChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, displayCount: value }))}
                    onSearchTermChange={(value) => data.setHeatmapViewState((prev) => ({ ...prev, searchTerm: value }))}
                    onLegendRangeChange={data.setHeatmapLegendRange}
                    focusControlKey={data.focusedHeatmapControlKey}
                    showStats
                    onToggleFullscreen={() => setHeatmapFullscreen(false)}
                    isFullscreen
                />
            </Modal>

            {/* 行业详情弹窗 */}
            <Modal
                title={`${data.selectedIndustry} 行业详情`}
                open={detailVisible}
                onCancel={() => setDetailVisible(false)}
                footer={null}
                width={1000}
                destroyOnHidden
                modalRender={(node) => <div data-testid="industry-detail-modal">{node}</div>}
                styles={{ body: { padding: '0 24px 24px' } }}
            >
                <IndustryTrendPanel
                    industryName={data.selectedIndustry}
                    days={30}
                    industrySnapshot={data.selectedIndustrySnapshot}
                    stocks={data.industryStocks}
                    loadingStocks={data.loadingStocks}
                    stocksRefining={data.stocksRefining}
                    stocksScoreStage={data.stocksScoreStage}
                    stocksDisplayReady={data.stocksDisplayReady}
                    stockColumns={stockColumns}
                />
            </Modal>

            <StockDetailModal
                open={data.stockDetailVisible}
                onCancel={data.closeStockDetail}
                loading={data.stockDetailLoading}
                error={data.stockDetailError}
                detailData={data.stockDetailData}
                selectedStock={data.stockDetailData?.symbol || data.stockDetailSymbol}
                onRetry={data.stockDetailSymbol ? () => data.handleLeadingStockClick(data.stockDetailSymbol) : undefined}
            />

            <IndustryScoreRadarModal
                visible={Boolean(scoreRadarRecord)}
                onClose={() => setScoreRadarRecord(null)}
                record={scoreRadarRecord}
                snapshot={scoreRadarRecord ? data.selectedIndustrySnapshot?.industry_name === scoreRadarRecord.industry_name
                    ? data.selectedIndustrySnapshot
                    : (data.heatmapIndustries || []).find((item) => item?.name === scoreRadarRecord.industry_name) : null}
            />
        </Layout>
    );
};

export default IndustryDashboard;
