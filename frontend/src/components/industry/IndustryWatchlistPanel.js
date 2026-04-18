import React, { useMemo, useState } from 'react';
import { Card, Tag, Button, Space } from 'antd';
import { StarFilled, BranchesOutlined } from '@ant-design/icons';
import { activateOnEnterOrSpace } from './industryShared';

const IndustryWatchlistPanel = ({
    watchlistEntries,
    watchlistSuggestions,
    selectedIndustry,
    maxWatchlistIndustries,
    toggleWatchlistIndustry,
    setSelectedIndustry,
    handleIndustryClick,
    handleAddToComparison,
    formatIndustryAlertMoneyFlow,
}) => {
    const [expanded, setExpanded] = useState(false);
    const visibleEntries = useMemo(
        () => (expanded ? watchlistEntries : watchlistEntries.slice(0, 3)),
        [expanded, watchlistEntries]
    );

    return (
    <Card
        size="small"
        data-testid="industry-watchlist-card"
        style={{
            marginBottom: 12,
            borderRadius: 12,
            border: '1px solid color-mix(in srgb, var(--border-color) 82%, transparent 18%)',
            boxShadow: '0 10px 30px rgba(15, 23, 42, 0.06)',
            background: 'color-mix(in srgb, var(--bg-secondary) 92%, var(--bg-primary) 8%)',
        }}
        title={(
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                    <StarFilled style={{ marginRight: 8, color: '#faad14' }} />
                    我的观察
                </span>
                <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                    收藏常看的行业，和异动提醒、回放对比一起看
                </span>
            </div>
        )}
        extra={watchlistEntries.length > 0 ? (
            <Space size={8} wrap>
                <Tag color="gold" style={{ margin: 0, borderRadius: 999 }}>
                    {watchlistEntries.length}/{maxWatchlistIndustries}
                </Tag>
                <Button size="small" type="text" onClick={() => setExpanded((current) => !current)}>
                    {expanded ? '收起' : '展开'}
                </Button>
            </Space>
        ) : null}
    >
        {watchlistEntries.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {!expanded && watchlistEntries.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-secondary)' }}>
                        <span>优先观察</span>
                        {watchlistEntries.slice(0, 3).map((item) => (
                            <Tag key={item.industryName} color={item.industryName === selectedIndustry ? 'processing' : 'default'} style={{ margin: 0, borderRadius: 999 }}>
                                {item.industryName}
                            </Tag>
                        ))}
                    </div>
                )}
                {visibleEntries.map((item) => (
                    <div
                        key={item.industryName}
                        data-testid="industry-watchlist-item"
                        style={{
                            borderRadius: 12,
                            padding: '12px 12px 10px',
                            background: item.industryName === selectedIndustry
                                ? 'color-mix(in srgb, var(--accent-primary) 8%, var(--bg-secondary) 92%)'
                                : 'color-mix(in srgb, var(--bg-primary) 18%, var(--bg-secondary) 82%)',
                            border: item.industryName === selectedIndustry
                                ? '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)'
                                : '1px solid color-mix(in srgb, var(--border-color) 82%, transparent 18%)',
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{item.industryName}</span>
                                    {item.alert && (
                                        <Tag color={item.alert.color} style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                            {item.alert.title}
                                        </Tag>
                                    )}
                                    {item.replayDiff && (
                                        <Tag color={item.replayDiff.changeDelta >= 0 ? 'red' : 'green'} style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                            回放 {item.replayDiff.changeDelta >= 0 ? '+' : ''}{Number(item.replayDiff.changeDelta || 0).toFixed(2)}%
                                        </Tag>
                                    )}
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-secondary)' }}>
                                    <span>评分 {item.score != null ? Number(item.score).toFixed(1) : '-'}</span>
                                    <span style={{ color: (item.change_pct || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                                        涨跌 {item.change_pct != null ? `${item.change_pct >= 0 ? '+' : ''}${Number(item.change_pct).toFixed(2)}%` : '-'}
                                    </span>
                                    <span style={{ color: (item.money_flow || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                                        资金 {item.money_flow != null ? formatIndustryAlertMoneyFlow(item.money_flow) : '-'}
                                    </span>
                                </div>
                            </div>
                            <Button size="small" type="text" onClick={() => toggleWatchlistIndustry(item.industryName)}>
                                移除
                            </Button>
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 8 }}>
                            {item.alert
                                ? item.alert.reason
                                : item.leadingStock
                                    ? `龙头候选 ${item.leadingStock} 已可见，适合继续顺着行业详情和龙头股联动下钻。`
                                    : '当前没有命中提醒，可以先保留观察，等下一次异动或回放对比时再看。'}
                        </div>
                        <Space size={8} wrap>
                            <Button
                                size="small"
                                type={selectedIndustry === item.industryName ? 'default' : 'primary'}
                                onClick={() => setSelectedIndustry(item.industryName)}
                            >
                                {selectedIndustry === item.industryName ? '已聚焦' : '聚焦'}
                            </Button>
                            <Button size="small" type="text" onClick={() => handleIndustryClick(item.industryName)}>
                                查看详情
                            </Button>
                            <Button size="small" type="text" icon={<BranchesOutlined />} onClick={() => handleAddToComparison(item.industryName)}>
                                加入对比
                            </Button>
                        </Space>
                    </div>
                ))}
                {watchlistEntries.length > visibleEntries.length && (
                    <div style={{ display: 'flex', justifyContent: 'center' }}>
                        <Button size="small" type="text" onClick={() => setExpanded(true)}>
                            展开其余 {watchlistEntries.length - visibleEntries.length} 个观察行业
                        </Button>
                    </div>
                )}
            </div>
        ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    还没有加入观察的行业。可以先从当前提醒、研究焦点或热力图里挑几个常看的板块放进来。
                </div>
                {watchlistSuggestions.length > 0 && (
                    <Space size={[6, 6]} wrap>
                        {watchlistSuggestions.map((industry) => (
                            <Tag
                                key={industry}
                                color="gold"
                                style={{ margin: 0, cursor: 'pointer', borderRadius: 999, paddingInline: 8 }}
                                onClick={() => toggleWatchlistIndustry(industry)}
                                role="button"
                                tabIndex={0}
                                aria-label={`把 ${industry} 加入观察列表`}
                                className="industry-watchlist-suggestion"
                                onKeyDown={(event) => activateOnEnterOrSpace(event, () => toggleWatchlistIndustry(industry))}
                            >
                                + {industry}
                            </Tag>
                        ))}
                    </Space>
                )}
            </div>
        )}
    </Card>
    );
};

export default IndustryWatchlistPanel;
