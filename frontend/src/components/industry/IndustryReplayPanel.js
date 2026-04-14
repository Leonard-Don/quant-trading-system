import React, { useEffect, useState } from 'react';
import { Card, Button, Space, Radio, Select, Tag, Row, Col } from 'antd';
import { StarFilled } from '@ant-design/icons';

const IndustryReplayPanel = ({
    heatmapReplaySnapshots,
    activeReplaySnapshot,
    latestReplaySnapshot,
    replayWindow,
    setReplayWindow,
    heatmapReplayWindowOptions,
    comparisonBaseSnapshotId,
    setComparisonBaseSnapshotId,
    filteredReplaySnapshots,
    replayTargetSnapshot,
    formatReplaySnapshotTime,
    industryTimeframeLabels,
    setActiveTab,
    setSelectedReplaySnapshotId,
    setHeatmapViewState,
    setMarketCapFilter,
    panelSurface,
    panelBorder,
    panelShadow,
    panelMuted,
    textPrimary,
    textSecondary,
    replayComparison,
    activeReplayDiffIndustry,
    handleReplayDiffIndustrySelect,
    handleIndustryClick,
    getIndustryScoreTone,
    formatReplayDelta,
    replayIndustryDiffDetail,
    watchlistIndustries,
    toggleWatchlistIndustry,
    formatReplayMetricPercent,
    formatReplayMetricMoney,
}) => {
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        if (activeReplaySnapshot) {
            setExpanded(true);
        }
    }, [activeReplaySnapshot]);

    if (heatmapReplaySnapshots.length <= 0) {
        return null;
    }

    return (
        <Card
            size="small"
            data-testid="industry-replay-card"
            style={{
                marginBottom: 12,
                background: activeReplaySnapshot
                    ? 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 92%, var(--accent-primary) 8%) 0%, color-mix(in srgb, var(--bg-secondary) 96%, var(--accent-warning) 4%) 100%)'
                    : panelSurface,
                border: activeReplaySnapshot
                    ? '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)'
                    : panelBorder,
                boxShadow: panelShadow,
            }}
            styles={{ body: { padding: '12px 14px' } }}
        >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontSize: 11, color: panelMuted, fontWeight: 700, letterSpacing: '0.04em' }}>行业历史回放</span>
                    <span style={{ fontSize: 13, color: textPrimary }}>
                        {activeReplaySnapshot
                            ? `正在回看 ${formatReplaySnapshotTime(activeReplaySnapshot.updateTime)} 的行业截面，热力图已暂停实时刷新`
                            : `已记录 ${heatmapReplaySnapshots.length} 个历史快照，刷新页面后仍可快速回看刚才的行业截面`}
                    </span>
                </div>
                <Space size={8} wrap>
                    {latestReplaySnapshot && (
                        <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>
                            最新 {formatReplaySnapshotTime(latestReplaySnapshot.updateTime)}
                        </Tag>
                    )}
                    <Button size="small" type="text" onClick={() => setExpanded((current) => !current)}>
                        {expanded ? '收起深看' : '展开深看'}
                    </Button>
                    {activeReplaySnapshot && (
                        <Button
                            size="small"
                            type="primary"
                            onClick={() => setSelectedReplaySnapshotId(null)}
                        >
                            回到实时
                        </Button>
                    )}
                </Space>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: expanded ? 12 : 0 }}>
                <Radio.Group
                    value={replayWindow}
                    onChange={(event) => setReplayWindow(event.target.value)}
                    size="small"
                    buttonStyle="solid"
                >
                    {heatmapReplayWindowOptions.map((item) => (
                        <Radio.Button key={item.value} value={item.value}>
                            {item.label}
                        </Radio.Button>
                    ))}
                </Radio.Group>

                <Select
                    size="small"
                    value={comparisonBaseSnapshotId}
                    onChange={setComparisonBaseSnapshotId}
                    allowClear
                    placeholder="选择对比基线"
                    style={{ width: 180 }}
                    options={filteredReplaySnapshots
                        .filter((snapshot) => snapshot.id !== replayTargetSnapshot?.id)
                        .map((snapshot) => ({
                            value: snapshot.id,
                            label: `${formatReplaySnapshotTime(snapshot.updateTime)} · ${industryTimeframeLabels[snapshot.timeframe] || `${snapshot.timeframe}日`}`,
                        }))}
                />
            </div>

            <Space size={[8, 8]} wrap>
                {filteredReplaySnapshots.slice(0, expanded ? 6 : 3).map((snapshot, index) => (
                    <Button
                        key={snapshot.id}
                        size="small"
                        type={activeReplaySnapshot?.id === snapshot.id ? 'primary' : 'default'}
                        onClick={() => {
                            setActiveTab('heatmap');
                            setSelectedReplaySnapshotId(snapshot.id);
                            setHeatmapViewState((current) => ({
                                ...current,
                                timeframe: snapshot.timeframe,
                                sizeMetric: snapshot.sizeMetric,
                                colorMetric: snapshot.colorMetric,
                                displayCount: snapshot.displayCount,
                                searchTerm: snapshot.searchTerm || '',
                            }));
                            setMarketCapFilter(snapshot.marketCapFilter || 'all');
                        }}
                    >
                        {index === 0 ? '最新 ' : ''}{formatReplaySnapshotTime(snapshot.updateTime)} · {industryTimeframeLabels[snapshot.timeframe] || `${snapshot.timeframe}日`}
                    </Button>
                ))}
            </Space>

            {!expanded && (
                <div
                    style={{
                        marginTop: 12,
                        padding: '10px 12px',
                        borderRadius: 12,
                        background: 'color-mix(in srgb, var(--bg-primary) 20%, var(--bg-secondary) 80%)',
                        border: panelBorder,
                        fontSize: 12,
                        color: textSecondary,
                        lineHeight: 1.7,
                    }}
                >
                    {replayComparison
                        ? `已就绪 ${formatReplaySnapshotTime(replayComparison.base.updateTime)} 到 ${formatReplaySnapshotTime(replayComparison.target.updateTime)} 的快照对比。展开后可看升温/降温榜、评分抬升和行业级 diff。`
                        : '已经记录最近行业快照。展开后可切基线、查看快照变化榜和行业级 diff。'}
                </div>
            )}

            {expanded && (
                <>
                    <div
                        style={{
                            marginTop: 12,
                            padding: '12px 12px 10px',
                            borderRadius: 12,
                            background: 'color-mix(in srgb, var(--bg-primary) 20%, var(--bg-secondary) 80%)',
                            border: panelBorder,
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                <span style={{ fontSize: 11, color: panelMuted, fontWeight: 700, letterSpacing: '0.04em' }}>快照变化对比</span>
                                <span style={{ fontSize: 12, color: textSecondary }}>
                                    {replayComparison
                                        ? `${formatReplaySnapshotTime(replayComparison.base.updateTime)} 对比 ${formatReplaySnapshotTime(replayComparison.target.updateTime)}`
                                        : '至少需要两个快照，才能直接比较行业升温和降温变化'}
                                </span>
                            </div>
                            {replayComparison?.target && (
                                <Tag color="processing" style={{ margin: 0, borderRadius: 999 }}>
                                    {industryTimeframeLabels[replayComparison.target.timeframe] || `${replayComparison.target.timeframe}日`}
                                </Tag>
                            )}
                        </div>

                        {replayComparison ? (
                            <Row gutter={[10, 10]}>
                                <Col xs={24} md={8}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        <div style={{ fontSize: 11, color: textSecondary, fontWeight: 700 }}>升温最快</div>
                                        {replayComparison.strongestRise.map((item) => (
                                            <div key={`rise-${item.name}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                                                <Space size={6} wrap>
                                                    <Button
                                                        type={activeReplayDiffIndustry === item.name ? 'primary' : 'link'}
                                                        size="small"
                                                        style={{ padding: activeReplayDiffIndustry === item.name ? undefined : 0, height: 'auto' }}
                                                        onClick={() => handleReplayDiffIndustrySelect(item.name)}
                                                    >
                                                        {item.name}
                                                    </Button>
                                                    <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }} onClick={() => handleIndustryClick(item.name)}>
                                                        详情
                                                    </Button>
                                                </Space>
                                                <span style={{ fontSize: 12, color: '#cf1322', fontWeight: 700 }}>{formatReplayDelta(item.changeDelta, 2, '%')}</span>
                                            </div>
                                        ))}
                                    </div>
                                </Col>
                                <Col xs={24} md={8}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        <div style={{ fontSize: 11, color: textSecondary, fontWeight: 700 }}>降温最快</div>
                                        {replayComparison.strongestFall.map((item) => (
                                            <div key={`fall-${item.name}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                                                <Space size={6} wrap>
                                                    <Button
                                                        type={activeReplayDiffIndustry === item.name ? 'primary' : 'link'}
                                                        size="small"
                                                        style={{ padding: activeReplayDiffIndustry === item.name ? undefined : 0, height: 'auto' }}
                                                        onClick={() => handleReplayDiffIndustrySelect(item.name)}
                                                    >
                                                        {item.name}
                                                    </Button>
                                                    <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }} onClick={() => handleIndustryClick(item.name)}>
                                                        详情
                                                    </Button>
                                                </Space>
                                                <span style={{ fontSize: 12, color: '#3f8600', fontWeight: 700 }}>{formatReplayDelta(item.changeDelta, 2, '%')}</span>
                                            </div>
                                        ))}
                                    </div>
                                </Col>
                                <Col xs={24} md={8}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        <div style={{ fontSize: 11, color: textSecondary, fontWeight: 700 }}>评分抬升</div>
                                        {replayComparison.strongestScoreRise.map((item) => (
                                            <div key={`score-${item.name}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                                                <Space size={6} wrap>
                                                    <Button
                                                        type={activeReplayDiffIndustry === item.name ? 'primary' : 'link'}
                                                        size="small"
                                                        style={{ padding: activeReplayDiffIndustry === item.name ? undefined : 0, height: 'auto' }}
                                                        onClick={() => handleReplayDiffIndustrySelect(item.name)}
                                                    >
                                                        {item.name}
                                                    </Button>
                                                    <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }} onClick={() => handleIndustryClick(item.name)}>
                                                        详情
                                                    </Button>
                                                </Space>
                                                <span style={{ fontSize: 12, color: getIndustryScoreTone(item.scoreDelta + 50), fontWeight: 700 }}>
                                                    {formatReplayDelta(item.scoreDelta, 1)}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </Col>
                            </Row>
                        ) : (
                            <div style={{ fontSize: 12, color: textSecondary, lineHeight: 1.7 }}>
                                等再产生一个新快照后，这里会自动告诉你哪些行业升温最快、哪些行业开始降温，以及评分变化最大的板块。
                            </div>
                        )}
                    </div>

                    {replayIndustryDiffDetail && (
                        <div
                            data-testid="industry-replay-diff-detail"
                            style={{
                                marginTop: 12,
                                padding: '12px 12px 10px',
                                borderRadius: 12,
                                background: 'color-mix(in srgb, var(--bg-secondary) 86%, white 14%)',
                                border: panelBorder,
                            }}
                        >
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                            <span style={{ fontSize: 11, color: panelMuted, fontWeight: 700, letterSpacing: '0.04em' }}>行业级 Diff</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                <span style={{ fontSize: 16, fontWeight: 700, color: textPrimary }}>{replayIndustryDiffDetail.name}</span>
                                <Tag color={replayIndustryDiffDetail.leadingStockChanged ? 'gold' : 'default'} style={{ margin: 0, borderRadius: 999 }}>
                                    {replayIndustryDiffDetail.leadingStockChanged ? '龙头切换' : '龙头延续'}
                                </Tag>
                            </div>
                            <span style={{ fontSize: 12, color: textSecondary }}>
                                {formatReplaySnapshotTime(replayComparison.base.updateTime)} -> {formatReplaySnapshotTime(replayComparison.target.updateTime)}
                            </span>
                        </div>
                        <Space size={8} wrap>
                            <Button
                                size="small"
                                icon={<StarFilled style={{ color: watchlistIndustries.includes(replayIndustryDiffDetail.name) ? '#faad14' : 'rgba(0,0,0,0.25)' }} />}
                                onClick={() => toggleWatchlistIndustry(replayIndustryDiffDetail.name)}
                            >
                                {watchlistIndustries.includes(replayIndustryDiffDetail.name) ? '已在观察' : '加入观察'}
                            </Button>
                            <Button size="small" onClick={() => handleReplayDiffIndustrySelect(replayIndustryDiffDetail.name)}>
                                聚焦行业
                            </Button>
                            <Button size="small" type="primary" onClick={() => handleIndustryClick(replayIndustryDiffDetail.name)}>
                                查看行业详情
                            </Button>
                        </Space>
                    </div>

                    <Row gutter={[10, 10]}>
                        <Col xs={12} md={6}>
                            <div style={{ borderRadius: 10, padding: '10px 12px', background: 'rgba(245,34,45,0.05)', border: '1px solid rgba(245,34,45,0.12)' }}>
                                <div style={{ fontSize: 11, color: textSecondary, marginBottom: 4 }}>涨跌幅变化</div>
                                <div style={{ fontSize: 18, fontWeight: 700, color: replayIndustryDiffDetail.changeDelta >= 0 ? '#cf1322' : '#3f8600' }}>
                                    {formatReplayDelta(replayIndustryDiffDetail.changeDelta, 2, '%')}
                                </div>
                                <div style={{ fontSize: 11, color: panelMuted, marginTop: 4 }}>
                                    {formatReplayMetricPercent(replayIndustryDiffDetail.base?.value)} -> {formatReplayMetricPercent(replayIndustryDiffDetail.target?.value)}
                                </div>
                            </div>
                        </Col>
                        <Col xs={12} md={6}>
                            <div style={{ borderRadius: 10, padding: '10px 12px', background: 'rgba(250,173,20,0.06)', border: '1px solid rgba(250,173,20,0.14)' }}>
                                <div style={{ fontSize: 11, color: textSecondary, marginBottom: 4 }}>评分变化</div>
                                <div style={{ fontSize: 18, fontWeight: 700, color: getIndustryScoreTone(replayIndustryDiffDetail.target?.total_score) }}>
                                    {formatReplayDelta(replayIndustryDiffDetail.scoreDelta, 1)}
                                </div>
                                <div style={{ fontSize: 11, color: panelMuted, marginTop: 4 }}>
                                    {Number.isFinite(Number(replayIndustryDiffDetail.base?.total_score)) ? Number(replayIndustryDiffDetail.base.total_score).toFixed(1) : '-'}
                                    {' -> '}
                                    {Number.isFinite(Number(replayIndustryDiffDetail.target?.total_score)) ? Number(replayIndustryDiffDetail.target.total_score).toFixed(1) : '-'}
                                </div>
                            </div>
                        </Col>
                        <Col xs={12} md={6}>
                            <div style={{ borderRadius: 10, padding: '10px 12px', background: 'rgba(24,144,255,0.05)', border: '1px solid rgba(24,144,255,0.12)' }}>
                                <div style={{ fontSize: 11, color: textSecondary, marginBottom: 4 }}>主力资金变化</div>
                                <div style={{ fontSize: 18, fontWeight: 700, color: replayIndustryDiffDetail.flowDelta >= 0 ? '#cf1322' : '#3f8600' }}>
                                    {formatReplayMetricMoney(replayIndustryDiffDetail.flowDelta)}
                                </div>
                                <div style={{ fontSize: 11, color: panelMuted, marginTop: 4 }}>
                                    {formatReplayMetricMoney(replayIndustryDiffDetail.base?.moneyFlow)} -> {formatReplayMetricMoney(replayIndustryDiffDetail.target?.moneyFlow)}
                                </div>
                            </div>
                        </Col>
                        <Col xs={12} md={6}>
                            <div style={{ borderRadius: 10, padding: '10px 12px', background: 'rgba(82,196,26,0.05)', border: '1px solid rgba(82,196,26,0.12)' }}>
                                <div style={{ fontSize: 11, color: textSecondary, marginBottom: 4 }}>换手率变化</div>
                                <div style={{ fontSize: 18, fontWeight: 700, color: replayIndustryDiffDetail.turnoverDelta >= 0 ? '#cf1322' : '#3f8600' }}>
                                    {formatReplayDelta(replayIndustryDiffDetail.turnoverDelta, 2, '%')}
                                </div>
                                <div style={{ fontSize: 11, color: panelMuted, marginTop: 4 }}>
                                    {formatReplayMetricPercent(replayIndustryDiffDetail.base?.turnoverRate)} -> {formatReplayMetricPercent(replayIndustryDiffDetail.target?.turnoverRate)}
                                </div>
                            </div>
                        </Col>
                    </Row>

                    <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 10, background: 'rgba(255,255,255,0.45)' }}>
                        <div style={{ fontSize: 12, color: textPrimary, lineHeight: 1.75 }}>{replayIndustryDiffDetail.narrative}</div>
                        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 12 }}>
                            <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>
                                基线龙头: {replayIndustryDiffDetail.baseLeader || '暂无'}
                            </Tag>
                            <Tag color={replayIndustryDiffDetail.leadingStockChanged ? 'gold' : 'processing'} style={{ margin: 0, borderRadius: 999 }}>
                                当前龙头: {replayIndustryDiffDetail.targetLeader || '暂无'}
                            </Tag>
                        </div>
                    </div>
                        </div>
                    )}

                    <div style={{ marginTop: 10, fontSize: 10, color: panelMuted }}>
                        当前为本地持久化回放，不依赖后端历史库；适合盘中回看刚才看过的行业截面和研究焦点，刷新后也会保留最近快照。
                    </div>
                </>
            )}
        </Card>
    );
};

export default IndustryReplayPanel;
