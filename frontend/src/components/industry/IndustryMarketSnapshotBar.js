import React from 'react';
import { Card, Tag, Space, Tooltip } from 'antd';
import { RiseOutlined, FundOutlined, StarFilled, ClockCircleOutlined } from '@ant-design/icons';

const IndustryMarketSnapshotBar = ({
    heatmapSummary,
    focusedHeatmapControlKey,
    marketCapFilter,
    onIndustryClick,
    onToggleMarketCapFilter,
    onResetMarketCapFilter,
    statusIndicator,
}) => {
    if (!heatmapSummary) {
        return null;
    }

    const renderIndustryTags = (items, colorPicker) => (
        <Space size={[4, 4]} wrap className="industry-market-snapshot-pill__content">
            {items.map((industry, index) => (
                <Tag
                    key={industry.name}
                    color={colorPicker(index)}
                    style={{
                        margin: 0,
                        cursor: 'pointer',
                        fontSize: 10,
                        lineHeight: '15px',
                        paddingInline: 6,
                        borderRadius: 999,
                        maxWidth: '100%',
                        whiteSpace: 'normal',
                        wordBreak: 'break-word',
                    }}
                    onClick={() => onIndustryClick(industry.name)}
                >
                    {industry.name}
                </Tag>
            ))}
        </Space>
    );

    return (
        <Card
            className="industry-market-snapshot-bar"
            size="small"
            style={{
                background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 16,
            }}
            styles={{ body: { padding: '8px 10px' } }}
        >
            <div
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 10,
                    marginBottom: 6,
                    flexWrap: 'wrap',
                }}
            >
                <div className="industry-market-snapshot-bar__title-group">
                    <span className="industry-market-snapshot-bar__eyebrow">
                        市场快照
                    </span>
                    <span className="industry-market-snapshot-bar__summary">只保留当前会改变扫描优先级的状态，减少和首屏摘要重复。</span>
                </div>
                <div className="industry-market-snapshot-bar__meta">
                    <span className="industry-market-snapshot-bar__timestamp">
                        <ClockCircleOutlined style={{ marginRight: 6 }} />
                        数据更新
                        {' '}
                        {heatmapSummary.updateTime
                            ? new Date(heatmapSummary.updateTime).toLocaleTimeString('zh-CN', { hour12: false })
                            : '-'}
                    </span>
                    <div style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <Tag
                            style={{
                                color: heatmapSummary.sentiment.color,
                                background: heatmapSummary.sentiment.bg,
                                border: `1px solid ${heatmapSummary.sentiment.color}`,
                                fontWeight: 'bold',
                                margin: 0,
                                borderRadius: 999,
                            }}
                        >
                            {heatmapSummary.sentiment.label}
                        </Tag>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.58)', fontVariantNumeric: 'tabular-nums' }}>
                            上涨占比 {heatmapSummary.upRatio}% · ↑{heatmapSummary.upCount} ━{heatmapSummary.flatCount} ↓{heatmapSummary.downCount}
                        </div>
                        <div style={{ display: 'inline-flex', alignItems: 'center' }}>
                            {statusIndicator}
                        </div>
                    </div>
                </div>
            </div>

            <div className="industry-market-snapshot-strip">
                {heatmapSummary.topInflow.length > 0 && (
                    <div className="industry-market-snapshot-pill">
                        <div className="industry-market-snapshot-pill__label">
                            <RiseOutlined style={{ color: '#ff7875', marginRight: 4 }} />
                            主力流入
                        </div>
                        {renderIndustryTags(heatmapSummary.topInflow, (index) => (index === 0 ? 'red' : 'volcano'))}
                    </div>
                )}

                {heatmapSummary.topOutflow.length > 0 && (
                    <div className="industry-market-snapshot-pill">
                        <div className="industry-market-snapshot-pill__label">
                            <FundOutlined style={{ color: '#95de64', marginRight: 4 }} />
                            流出压力
                        </div>
                        {renderIndustryTags(heatmapSummary.topOutflow, (index) => (index === 0 ? 'green' : 'lime'))}
                    </div>
                )}

                {heatmapSummary.topTurnover.length > 0 && (
                    <div className="industry-market-snapshot-pill">
                        <div className="industry-market-snapshot-pill__label">
                            <FundOutlined style={{ color: '#faad14', marginRight: 4 }} />
                            活跃行业
                        </div>
                        {renderIndustryTags(heatmapSummary.topTurnover, () => 'gold')}
                    </div>
                )}

                {heatmapSummary.marketCapHealth && (
                    <div
                        className={`industry-market-snapshot-pill heatmap-control-market-cap-filter ${focusedHeatmapControlKey === 'market_cap_filter' ? 'industry-market-snapshot-pill--focus' : ''}`}
                    >
                        <div className="industry-market-snapshot-pill__label">
                            <StarFilled style={{ color: heatmapSummary.marketCapHealth.coverageTone.color, marginRight: 4 }} />
                            市值覆盖 {heatmapSummary.marketCapHealth.coveragePct}%
                        </div>
                        <Space size={[4, 4]} wrap className="industry-market-snapshot-pill__content">
                            <Tooltip title="点击高亮实时市值行业">
                                <Tag
                                    color={marketCapFilter === 'live' ? 'green' : 'default'}
                                    style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                    onClick={() => onToggleMarketCapFilter('live')}
                                >
                                    实时 {heatmapSummary.marketCapHealth.liveCount}
                                </Tag>
                            </Tooltip>
                            <Tooltip title="点击高亮快照市值行业">
                                <Tag
                                    color={marketCapFilter === 'snapshot'
                                        ? (heatmapSummary.marketCapHealth.staleSnapshotCount > 0 ? 'orange' : 'blue')
                                        : 'default'}
                                    style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                    onClick={() => onToggleMarketCapFilter('snapshot')}
                                >
                                    快照 {heatmapSummary.marketCapHealth.snapshotCount}
                                    {heatmapSummary.marketCapHealth.staleSnapshotCount > 0
                                        ? ` / 旧 ${heatmapSummary.marketCapHealth.staleSnapshotCount}`
                                        : ''}
                                </Tag>
                            </Tooltip>
                            {heatmapSummary.marketCapHealth.proxyCount > 0 && (
                                <Tooltip title="点击高亮行业组代理市值">
                                    <Tag
                                        color={marketCapFilter === 'proxy' ? 'cyan' : 'default'}
                                        style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                        onClick={() => onToggleMarketCapFilter('proxy')}
                                    >
                                        代理 {heatmapSummary.marketCapHealth.proxyCount}
                                    </Tag>
                                </Tooltip>
                            )}
                            <Tooltip title="点击高亮估算市值行业">
                                <Tag
                                    color={marketCapFilter === 'estimated' ? 'gold' : 'default'}
                                    style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                    onClick={() => onToggleMarketCapFilter('estimated')}
                                >
                                    估算 {heatmapSummary.marketCapHealth.estimatedCount}
                                </Tag>
                            </Tooltip>
                            {marketCapFilter !== 'all' && (
                                <Tooltip title="清除市值来源筛选">
                                    <Tag
                                        color="processing"
                                        style={{ margin: 0, fontSize: 11, cursor: 'pointer' }}
                                        onClick={onResetMarketCapFilter}
                                    >
                                        查看全部
                                    </Tag>
                                </Tooltip>
                            )}
                        </Space>
                        <div className="industry-market-snapshot-pill__text">
                            {heatmapSummary.marketCapHealth.snapshotCount > 0
                                ? `最老快照 ${Math.round(heatmapSummary.marketCapHealth.oldestSnapshotHours || 0)}h`
                                : '当前无快照市值'}
                        </div>
                    </div>
                )}
            </div>
        </Card>
    );
};

export default IndustryMarketSnapshotBar;
