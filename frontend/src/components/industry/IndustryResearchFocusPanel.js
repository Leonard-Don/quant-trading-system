import React from 'react';
import { Card, Tag, Button, Space, Row, Col, Progress } from 'antd';
import { BranchesOutlined, StarFilled } from '@ant-design/icons';

const TEXT_PRIMARY = 'var(--text-primary)';
const TEXT_SECONDARY = 'var(--text-secondary)';
const PANEL_SURFACE = 'var(--bg-secondary)';
const PANEL_BORDER = '1px solid var(--border-color)';
const PANEL_SHADOW = '0 1px 2px rgba(0,0,0,0.03)';

const IndustryResearchFocusPanel = ({
    selectedIndustry,
    selectedIndustrySnapshot,
    selectedIndustryMarketCapBadge,
    selectedIndustryVolatilityMeta,
    selectedIndustryFocusNarrative,
    selectedIndustryScoreBreakdown,
    selectedIndustryScoreSummary,
    selectedIndustryReasons,
    selectedIndustryWatched,
    focusIndustrySuggestions,
    onClearIndustry,
    onOpenIndustryDetail,
    onToggleWatchlist,
    onAddToComparison,
    onSelectIndustry,
}) => {
    const topBreakdown = (selectedIndustryScoreBreakdown || []).slice(0, 3);
    const topReasons = (selectedIndustryReasons || []).slice(0, 2);

    return (
        <Card
            size="small"
            style={{
                marginBottom: 12,
                borderRadius: 12,
                border: selectedIndustry
                    ? '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)'
                    : PANEL_BORDER,
                boxShadow: PANEL_SHADOW,
                background: selectedIndustry
                    ? 'linear-gradient(180deg, color-mix(in srgb, var(--accent-primary) 6%, var(--bg-secondary) 94%) 0%, color-mix(in srgb, var(--accent-warning) 4%, var(--bg-secondary) 96%) 100%)'
                    : PANEL_SURFACE,
            }}
            title={(
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontWeight: 700, color: TEXT_PRIMARY }}>研究焦点</span>
                    <span style={{ fontSize: 11, color: TEXT_SECONDARY }}>
                        {selectedIndustry ? '当前行业上下文与下一步动作' : '先选一个行业，再看龙头和详情'}
                    </span>
                </div>
            )}
        >
            {selectedIndustry ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            <span style={{ fontSize: 18, fontWeight: 700, color: TEXT_PRIMARY }}>{selectedIndustry}</span>
                            <Space size={[6, 6]} wrap>
                                {selectedIndustryMarketCapBadge && (
                                    <Tag color={selectedIndustryMarketCapBadge.color} style={{ margin: 0, borderRadius: 999 }}>
                                        {selectedIndustryMarketCapBadge.label}市值
                                    </Tag>
                                )}
                                {selectedIndustryVolatilityMeta?.value > 0 && (
                                    <Tag color={selectedIndustryVolatilityMeta.color} style={{ margin: 0, borderRadius: 999 }}>
                                        {selectedIndustryVolatilityMeta.label} {selectedIndustryVolatilityMeta.value.toFixed(1)}%
                                    </Tag>
                                )}
                            </Space>
                        </div>
                        <Button size="small" type="text" onClick={onClearIndustry}>清除</Button>
                    </div>

                    <div
                        style={{
                            padding: '10px 12px',
                            borderRadius: 10,
                            background: 'color-mix(in srgb, var(--accent-primary) 8%, var(--bg-secondary) 92%)',
                            border: '1px solid color-mix(in srgb, var(--accent-primary) 18%, var(--border-color) 82%)',
                        }}
                    >
                        <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 5, fontWeight: 700, letterSpacing: '0.04em' }}>
                            一句话判断
                        </div>
                        <div style={{ fontSize: 13, lineHeight: 1.65, color: TEXT_PRIMARY }}>{selectedIndustryFocusNarrative}</div>
                    </div>

                    <Row gutter={[8, 8]}>
                        <Col xs={8} sm={8}>
                            <div style={{ padding: '10px 12px', borderRadius: 10, background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)' }}>
                                <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 4 }}>综合得分</div>
                                <div style={{ fontSize: 18, fontWeight: 700, color: TEXT_PRIMARY }}>
                                    {selectedIndustrySnapshot?.score != null ? selectedIndustrySnapshot.score.toFixed(1) : '-'}
                                </div>
                            </div>
                        </Col>
                        <Col xs={8} sm={8}>
                            <div style={{ padding: '10px 12px', borderRadius: 10, background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)' }}>
                                <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 4 }}>涨跌幅</div>
                                <div style={{ fontSize: 18, fontWeight: 700, color: (selectedIndustrySnapshot?.change_pct || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                                    {selectedIndustrySnapshot?.change_pct != null
                                        ? `${selectedIndustrySnapshot.change_pct >= 0 ? '+' : ''}${selectedIndustrySnapshot.change_pct.toFixed(2)}%`
                                        : '-'}
                                </div>
                            </div>
                        </Col>
                        <Col xs={8} sm={8}>
                            <div style={{ padding: '10px 12px', borderRadius: 10, background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)' }}>
                                <div style={{ fontSize: 11, color: TEXT_SECONDARY, marginBottom: 4 }}>资金流向</div>
                                <div style={{ fontSize: 18, fontWeight: 700, color: (selectedIndustrySnapshot?.money_flow || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                                    {selectedIndustrySnapshot?.money_flow != null
                                        ? `${selectedIndustrySnapshot.money_flow >= 0 ? '+' : ''}${(selectedIndustrySnapshot.money_flow / 1e8).toFixed(1)}亿`
                                        : '-'}
                                </div>
                            </div>
                        </Col>
                    </Row>

                    {(topBreakdown.length > 0 || topReasons.length > 0) && (
                        <div
                            style={{
                                padding: '10px 12px',
                                borderRadius: 10,
                                background: 'color-mix(in srgb, var(--bg-secondary) 88%, var(--bg-primary) 12%)',
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                                    <div style={{ fontSize: 11, color: TEXT_SECONDARY, fontWeight: 700, letterSpacing: '0.04em' }}>
                                        当前驱动
                                    </div>
                                    <div style={{ fontSize: 12, color: TEXT_SECONDARY, lineHeight: 1.6 }}>
                                        {selectedIndustryScoreSummary || '帮助理解当前综合得分，不等同于后端原始权重。'}
                                    </div>
                                </div>
                                <Tag color="blue" style={{ margin: 0, borderRadius: 999 }}>研究视角</Tag>
                            </div>

                            {topBreakdown.length > 0 && (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: topReasons.length > 0 ? 10 : 0 }}>
                                    {topBreakdown.map((factor) => (
                                        <div key={factor.key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                                                <span style={{ fontSize: 12, fontWeight: 600, color: TEXT_PRIMARY }}>{factor.label}</span>
                                                <span style={{ fontSize: 12, fontWeight: 700, color: factor.color }}>{factor.score.toFixed(0)}</span>
                                            </div>
                                            <Progress
                                                percent={Math.round(factor.score)}
                                                showInfo={false}
                                                strokeColor={factor.color}
                                                trailColor="rgba(0,0,0,0.06)"
                                                size="small"
                                            />
                                        </div>
                                    ))}
                                </div>
                            )}

                            {topReasons.length > 0 && (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                    {topReasons.map((reason) => (
                                        <div key={reason} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                                            <span style={{ color: 'var(--accent-primary)', fontWeight: 700, lineHeight: 1.6 }}>•</span>
                                            <span style={{ fontSize: 12, lineHeight: 1.6, color: TEXT_PRIMARY }}>{reason}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    <Space size={8} wrap>
                        <Button type="primary" size="small" onClick={onOpenIndustryDetail}>
                            查看行业详情
                        </Button>
                        <Button
                            size="small"
                            data-testid="industry-focus-watchlist-button"
                            icon={<StarFilled style={{ color: selectedIndustryWatched ? '#faad14' : 'rgba(0,0,0,0.25)' }} />}
                            onClick={onToggleWatchlist}
                        >
                            {selectedIndustryWatched ? '已在观察列表' : '加入观察列表'}
                        </Button>
                        <Button size="small" icon={<BranchesOutlined />} onClick={onAddToComparison}>
                            加入轮动对比
                        </Button>
                    </Space>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ fontSize: 12, color: TEXT_SECONDARY, lineHeight: 1.7 }}>
                        从左侧热力图、排行榜或下面推荐标签中选一个行业，右侧会自动切到该行业的龙头股与研究动作。
                    </div>
                    {focusIndustrySuggestions.length > 0 && (
                        <Space size={[6, 6]} wrap>
                            {focusIndustrySuggestions.map((industry) => (
                                <Tag
                                    key={industry}
                                    color="processing"
                                    style={{ margin: 0, cursor: 'pointer', borderRadius: 999, paddingInline: 8 }}
                                    onClick={() => onSelectIndustry(industry)}
                                >
                                    {industry}
                                </Tag>
                            ))}
                        </Space>
                    )}
                </div>
            )}
        </Card>
    );
};

export default IndustryResearchFocusPanel;
