import React from 'react';
import { Card, Table, Empty, Button, Radio, Select, Tooltip, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

const { Option } = Select;

const IndustryRankingPanel = ({
    rankType,
    onRankTypeChange,
    sortBy,
    onSortByChange,
    lookbackDays,
    onLookbackDaysChange,
    volatilityFilter,
    onVolatilityFilterChange,
    rankingMarketCapFilter,
    onRankingMarketCapFilterChange,
    loadingHot,
    focusedRankingControlKey,
    filteredHotIndustries,
    hotIndustryColumns,
    onReload,
    onIndustryClick,
    activeRankingStateTags,
    onFocusRankingControl,
    onClearRankingStateTag,
    onResetRankingViewState,
    panelSurface,
    panelBorder,
    panelShadow,
    panelMuted,
}) => {
    const hasActiveRankingState = activeRankingStateTags.length > 0;

    return (
        <Card
            className="industry-ranking-card"
            title="行业排名"
            extra={(
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '6px 8px',
                        borderRadius: 10,
                        background: 'color-mix(in srgb, var(--bg-secondary) 84%, var(--accent-secondary) 16%)',
                        border: '1px solid color-mix(in srgb, var(--border-color) 72%, var(--accent-secondary) 28%)'
                    }} className="ranking-toolbar-group ranking-toolbar-group-primary">
                        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>榜单</span>
                        <Radio.Group
                            className="ranking-control-rank-type"
                            value={rankType}
                            onChange={(event) => onRankTypeChange(event.target.value)}
                            size="small"
                            buttonStyle="solid"
                            disabled={loadingHot}
                            style={{
                                boxShadow: focusedRankingControlKey === 'rank_type' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                borderRadius: 8,
                            }}
                        >
                            <Radio.Button value="gainers">涨幅榜</Radio.Button>
                            <Radio.Button value="losers">跌幅榜</Radio.Button>
                        </Radio.Group>
                    </div>

                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '6px 8px',
                        borderRadius: 10,
                        background: 'color-mix(in srgb, var(--bg-secondary) 92%, var(--bg-primary) 8%)',
                        border: panelBorder
                    }} className="ranking-toolbar-group ranking-toolbar-group-secondary">
                        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>排序视图</span>
                        <Select
                            className="ranking-control-sort-by"
                            value={sortBy}
                            onChange={onSortByChange}
                            size="small"
                            style={{
                                width: 120,
                                boxShadow: focusedRankingControlKey === 'sort_by' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                borderRadius: 8,
                            }}
                            disabled={loadingHot}
                        >
                            <Option value="change_pct">按涨跌幅</Option>
                            <Option value="total_score">按综合得分</Option>
                            <Option value="money_flow">按资金流向</Option>
                            <Option value="industry_volatility">按波动率</Option>
                        </Select>
                        <Select
                            className="ranking-control-lookback"
                            value={lookbackDays}
                            onChange={onLookbackDaysChange}
                            size="small"
                            style={{
                                width: 96,
                                boxShadow: focusedRankingControlKey === 'lookback' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                borderRadius: 8,
                            }}
                            disabled={loadingHot}
                        >
                            <Option value={1}>近1日</Option>
                            <Option value={5}>近5日</Option>
                            <Option value={10}>近10日</Option>
                        </Select>
                        <Select
                            className="ranking-control-volatility"
                            value={volatilityFilter}
                            onChange={onVolatilityFilterChange}
                            size="small"
                            style={{
                                width: 112,
                                boxShadow: focusedRankingControlKey === 'volatility_filter' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                borderRadius: 8,
                            }}
                            disabled={loadingHot}
                        >
                            <Option value="all">全部波动</Option>
                            <Option value="low">低波动</Option>
                            <Option value="medium">中波动</Option>
                            <Option value="high">高波动</Option>
                        </Select>
                        <Select
                            className="ranking-control-market-cap"
                            value={rankingMarketCapFilter}
                            onChange={onRankingMarketCapFilterChange}
                            size="small"
                            style={{
                                width: 124,
                                boxShadow: focusedRankingControlKey === 'market_cap_filter' ? 'var(--industry-focus-ring-secondary)' : 'none',
                                borderRadius: 8,
                            }}
                            disabled={loadingHot}
                        >
                            <Option value="all">全部市值来源</Option>
                            <Option value="live">实时市值</Option>
                            <Option value="snapshot">快照市值</Option>
                            <Option value="proxy">代理市值</Option>
                            <Option value="estimated">估算市值</Option>
                        </Select>
                    </div>

                    <Tooltip title="刷新排行榜数据">
                        <Button
                            icon={<ReloadOutlined />}
                            onClick={onReload}
                            size="small"
                            type="text"
                            loading={loadingHot}
                        />
                    </Tooltip>
                </div>
            )}
        >
            {hasActiveRankingState && (
                <div
                    style={{
                        marginBottom: 12,
                        padding: '10px 14px',
                        borderRadius: 10,
                        background: panelSurface,
                        border: panelBorder,
                        boxShadow: panelShadow
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 11, color: panelMuted, fontWeight: 700, letterSpacing: '0.04em' }}>当前排行榜</span>
                            {activeRankingStateTags.map((item) => (
                                <Tag
                                    key={item.key}
                                    color="purple"
                                    closable
                                    className={`ranking-state-tag-${item.key} industry-state-tag`}
                                    onClick={() => onFocusRankingControl(item.key)}
                                    onClose={(event) => {
                                        event.preventDefault();
                                        onClearRankingStateTag(item.key);
                                    }}
                                    style={{ margin: 0, fontSize: 12, cursor: 'pointer', borderRadius: 999, paddingInline: 8 }}
                                >
                                    {item.label}: {item.value}
                                </Tag>
                            ))}
                        </div>
                        <Button className="industry-reset-button" size="small" type="text" onClick={onResetRankingViewState}>
                            恢复默认榜单
                        </Button>
                    </div>
                </div>
            )}

            <Table
                className="industry-ranking-table"
                dataSource={filteredHotIndustries}
                columns={hotIndustryColumns}
                rowKey="industry_name"
                size="small"
                loading={loadingHot}
                scroll={{ x: 980 }}
                pagination={{
                    pageSize: 15,
                    showSizeChanger: true,
                    pageSizeOptions: ['10', '15', '30', '50'],
                    showTotal: (total) => `共 ${total} 个行业`
                }}
                onRow={(record) => ({
                    onClick: () => onIndustryClick(record.industry_name),
                    style: { cursor: 'pointer' }
                })}
                locale={{
                    emptyText: (
                        <Empty description={loadingHot ? '正在加载行业排名...' : '暂无排名数据'}>
                            <Button
                                className="industry-empty-action"
                                type="dashed"
                                loading={loadingHot}
                                onClick={onReload}
                            >
                                刷新
                            </Button>
                        </Empty>
                    )
                }}
            />
        </Card>
    );
};

export default IndustryRankingPanel;
