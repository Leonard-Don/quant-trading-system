/**
 * Column descriptor factory for the hot-industry ranking table (split out of
 * IndustryDashboard, mirroring `buildIndustryPolicySignalColumn`).
 *
 * Returns the antd `columns` array verbatim from the former inline definition,
 * receiving the handful of handlers + helpers it closes over as a deps object so
 * the render/sorter logic stays testable and the parent stays the orchestrator.
 */

import { Tag, Button, Space, Tooltip } from 'antd';
import MiniSparkline from '../common/MiniSparkline';
import buildIndustryPolicySignalColumn from './buildIndustryPolicySignalColumn';
import {
    activateOnEnterOrSpace,
    getIndustryScoreTone,
    getMarketCapBadgeMeta,
} from './industryShared';

const PANEL_MUTED = 'var(--text-muted)';
const TEXT_SECONDARY = 'var(--text-secondary)';

const buildHotIndustryColumns = ({
    getIndustryVolatilityMeta,
    onIndustryClick,
    onJumpToMarketCapFilter,
    onScoreRadarRecord,
    onAddToComparison,
}) => [
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
            const volatilityMeta = getIndustryVolatilityMeta(record.industryVolatility, record.industryVolatilitySource);
            return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <Button
                        type="link"
                        size="small"
                        onClick={() => onIndustryClick(name)}
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
                            onClick={(event) => {
                                event.stopPropagation();
                                onJumpToMarketCapFilter(sourceMeta.filter);
                            }}
                            role="button"
                            tabIndex={0}
                            aria-label={`按 ${sourceMeta.label} 市值来源筛选 ${name}`}
                            onKeyDown={(event) => activateOnEnterOrSpace(event, () => {
                                event.stopPropagation();
                                onJumpToMarketCapFilter(sourceMeta.filter);
                            })}
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
                onClick={() => onScoreRadarRecord(record)}
                aria-label={`查看 ${record.industry_name} 综合评分雷达`}
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
            const meta = getIndustryVolatilityMeta(value, record.industryVolatilitySource);
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
    buildIndustryPolicySignalColumn({ mutedColor: PANEL_MUTED }),
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
                <Button className="industry-inline-link" type="link" size="small" onClick={() => onIndustryClick(record.industry_name)} style={{ padding: 0, height: 'auto', fontSize: 12 }}>详情</Button>
                <Button className="industry-inline-link" type="link" size="small" onClick={() => onAddToComparison(record.industry_name)} style={{ padding: 0, height: 'auto', color: 'var(--accent-secondary)', fontSize: 12 }}>对比</Button>
            </Space>
        )
    }
];

export default buildHotIndustryColumns;
