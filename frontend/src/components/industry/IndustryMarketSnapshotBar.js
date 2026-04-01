import React from 'react';
import { Card, Row, Col, Tag, Progress, Space, Tooltip } from 'antd';
import { RiseOutlined, FundOutlined, StarFilled } from '@ant-design/icons';

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

    return (
        <Card
            size="small"
            style={{
                marginBottom: 12,
                background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8,
            }}
            styles={{ body: { padding: '12px 14px' } }}
        >
            <div
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                    marginBottom: 10,
                    flexWrap: 'wrap',
                }}
            >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.42)', fontWeight: 700, letterSpacing: '0.04em' }}>
                        市场快照
                    </span>
                    <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.82)' }}>行业热度与市值质量概览</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 'auto' }}>
                    <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 2 }}>数据更新</div>
                        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)', fontFamily: 'monospace' }}>
                            {heatmapSummary.updateTime
                                ? new Date(heatmapSummary.updateTime).toLocaleTimeString('zh-CN', { hour12: false })
                                : '-'}
                        </div>
                    </div>
                    {statusIndicator}
                </div>
            </div>

            <Row gutter={[10, 10]} align="stretch" wrap>
                <Col xs={24} sm={12} xl={5}>
                    <div
                        style={{
                            height: '100%',
                            background: 'rgba(255,255,255,0.05)',
                            border: '1px solid rgba(255,255,255,0.08)',
                            borderRadius: 10,
                            padding: '10px 12px',
                        }}
                    >
                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 3 }}>市场情绪</div>
                        <Tag
                            style={{
                                color: heatmapSummary.sentiment.color,
                                background: heatmapSummary.sentiment.bg,
                                border: `1px solid ${heatmapSummary.sentiment.color}`,
                                fontWeight: 'bold',
                                fontSize: 14,
                                padding: '2px 12px',
                                margin: 0,
                            }}
                        >
                            {heatmapSummary.sentiment.label}
                        </Tag>
                    </div>
                </Col>

                <Col xs={24} sm={12} xl={5}>
                    <div
                        style={{
                            height: '100%',
                            background: 'rgba(255,255,255,0.05)',
                            border: '1px solid rgba(255,255,255,0.08)',
                            borderRadius: 10,
                            padding: '10px 12px',
                        }}
                    >
                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 3 }}>
                            市场广度 &nbsp;
                            <span style={{ color: heatmapSummary.sentiment.color, fontWeight: 600 }}>{heatmapSummary.upRatio}%</span>
                            <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: 10 }}>
                                &nbsp;(↑{heatmapSummary.upCount} ━{heatmapSummary.flatCount} ↓{heatmapSummary.downCount})
                            </span>
                        </div>
                        <Progress
                            percent={heatmapSummary.upRatio}
                            showInfo={false}
                            strokeColor="#cf1322"
                            trailColor="#3f8600"
                            size="small"
                            style={{ marginBottom: 0 }}
                        />
                    </div>
                </Col>

                {heatmapSummary.topInflow.length > 0 && (
                    <Col xs={24} sm={12} xl={5}>
                        <div
                            style={{
                                height: '100%',
                                background: 'rgba(255,255,255,0.05)',
                                border: '1px solid rgba(255,255,255,0.08)',
                                borderRadius: 10,
                                padding: '10px 12px',
                            }}
                        >
                            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>
                                <RiseOutlined style={{ color: '#ff7875', marginRight: 3 }} />
                                主力流入
                            </div>
                            <Space size={[4, 4]} wrap style={{ maxWidth: '100%' }}>
                                {heatmapSummary.topInflow.map((industry, index) => (
                                    <Tag
                                        key={industry.name}
                                        color={index === 0 ? 'red' : 'volcano'}
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
                        </div>
                    </Col>
                )}

                {heatmapSummary.topOutflow.length > 0 && (
                    <Col xs={24} sm={12} xl={5}>
                        <div
                            style={{
                                height: '100%',
                                background: 'rgba(255,255,255,0.05)',
                                border: '1px solid rgba(255,255,255,0.08)',
                                borderRadius: 10,
                                padding: '10px 12px',
                            }}
                        >
                            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>
                                <FundOutlined style={{ color: '#95de64', marginRight: 3 }} />
                                流出压力
                            </div>
                            <Space size={[4, 4]} wrap style={{ maxWidth: '100%' }}>
                                {heatmapSummary.topOutflow.map((industry, index) => (
                                    <Tag
                                        key={industry.name}
                                        color={index === 0 ? 'green' : 'lime'}
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
                        </div>
                    </Col>
                )}

                {heatmapSummary.topTurnover.length > 0 && (
                    <Col xs={24} sm={12} xl={4}>
                        <div
                            style={{
                                height: '100%',
                                background: 'rgba(255,255,255,0.05)',
                                border: '1px solid rgba(255,255,255,0.08)',
                                borderRadius: 10,
                                padding: '10px 12px',
                            }}
                        >
                            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginBottom: 4 }}>
                                <FundOutlined style={{ color: '#faad14', marginRight: 3 }} />
                                活跃行业
                            </div>
                            <Space size={[4, 4]} wrap style={{ maxWidth: '100%' }}>
                                {heatmapSummary.topTurnover.map((industry) => (
                                    <Tag
                                        key={industry.name}
                                        color="gold"
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
                        </div>
                    </Col>
                )}

                {heatmapSummary.marketCapHealth && (
                    <Col
                        xs={24}
                        xl={5}
                        className="heatmap-control-market-cap-filter"
                        style={{
                            boxShadow: focusedHeatmapControlKey === 'market_cap_filter'
                                ? '0 0 0 2px rgba(24,144,255,0.22)'
                                : 'none',
                            borderRadius: 8,
                            transition: 'all 0.2s ease',
                        }}
                    >
                        <div
                            style={{
                                height: '100%',
                                background: 'rgba(255,255,255,0.05)',
                                border: '1px solid rgba(255,255,255,0.08)',
                                borderRadius: 10,
                                padding: focusedHeatmapControlKey === 'market_cap_filter' ? '8px 10px' : '10px 12px',
                            }}
                        >
                            <div
                                style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'baseline',
                                    gap: 8,
                                    marginBottom: 4,
                                }}
                            >
                                <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>
                                    <StarFilled style={{ color: heatmapSummary.marketCapHealth.coverageTone.color, marginRight: 4 }} />
                                    市值覆盖
                                </div>
                                <div style={{ color: heatmapSummary.marketCapHealth.coverageTone.color, fontWeight: 700, fontSize: 16 }}>
                                    {heatmapSummary.marketCapHealth.coveragePct}%
                                </div>
                            </div>
                            <Space size={[4, 4]} wrap style={{ marginBottom: 2 }}>
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
                            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.38)', marginTop: 4 }}>
                                {heatmapSummary.marketCapHealth.snapshotCount > 0
                                    ? `最老快照 ${Math.round(heatmapSummary.marketCapHealth.oldestSnapshotHours || 0)}h`
                                    : '当前无快照市值'}
                            </div>
                        </div>
                    </Col>
                )}
            </Row>
        </Card>
    );
};

export default IndustryMarketSnapshotBar;
