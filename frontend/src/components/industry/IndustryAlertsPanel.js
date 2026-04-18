import React, { useEffect, useMemo, useState } from 'react';
import { Card, Tag, Space, Radio, Select, Checkbox, Button, Row, Col, Empty, InputNumber } from 'antd';
import { NotificationOutlined, StarFilled, BranchesOutlined } from '@ant-design/icons';
import { normalizeIndustryAlertThresholds } from './industryShared';

const { Option } = Select;
const INDUSTRY_ALERT_THRESHOLD_DEBOUNCE_MS = 360;

const areIndustryAlertThresholdsEqual = (left, right) => {
    const normalizedLeft = normalizeIndustryAlertThresholds(left);
    const normalizedRight = normalizeIndustryAlertThresholds(right);
    return Object.keys(normalizedLeft).every((key) => Number(normalizedLeft[key] || 0) === Number(normalizedRight[key] || 0));
};

const IndustryAlertsPanel = ({
    industryAlertsWithSeverity,
    rawIndustryAlerts,
    focusIndustrySuggestions,
    subscribedAlertNewCount,
    industryAlertSubscription,
    desktopAlertNotifications,
    industryAlertRule,
    setIndustryAlertRule,
    industryAlertRecency,
    setIndustryAlertRecency,
    industryAlertKindOptions,
    industryAlertRecencyOptions,
    setIndustryAlertSubscription,
    industryAlertThresholds,
    setIndustryAlertThresholds,
    requestDesktopAlertPermission,
    toggleWatchlistIndustry,
    watchlistIndustries,
    selectedIndustry,
    setSelectedIndustry,
    handleIndustryClick,
    handleAddToComparison,
    alertTimelineEntries,
    formatIndustryAlertSeenLabel,
    message,
}) => {
    const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
    const [showTimeline, setShowTimeline] = useState(false);
    const [showAllAlerts, setShowAllAlerts] = useState(false);
    const [draftThresholds, setDraftThresholds] = useState(() => normalizeIndustryAlertThresholds(industryAlertThresholds));

    const visibleAlerts = useMemo(
        () => (showAllAlerts ? industryAlertsWithSeverity : industryAlertsWithSeverity.slice(0, 4)),
        [industryAlertsWithSeverity, showAllAlerts]
    );

    useEffect(() => {
        const normalizedThresholds = normalizeIndustryAlertThresholds(industryAlertThresholds);
        setDraftThresholds((current) => (
            areIndustryAlertThresholdsEqual(current, normalizedThresholds) ? current : normalizedThresholds
        ));
    }, [industryAlertThresholds]);

    useEffect(() => {
        if (areIndustryAlertThresholdsEqual(draftThresholds, industryAlertThresholds)) {
            return undefined;
        }
        const timeoutId = window.setTimeout(() => {
            setIndustryAlertThresholds((current) => (
                areIndustryAlertThresholdsEqual(current, draftThresholds) ? current : draftThresholds
            ));
        }, INDUSTRY_ALERT_THRESHOLD_DEBOUNCE_MS);
        return () => window.clearTimeout(timeoutId);
    }, [draftThresholds, industryAlertThresholds, setIndustryAlertThresholds]);

    const updateDraftThreshold = (key, value, extraPatch = {}) => {
        const nextValue = Number(value || 0);
        setDraftThresholds((current) => ({
            ...current,
            [key]: nextValue,
            ...extraPatch,
        }));
    };

    if (!(industryAlertsWithSeverity.length > 0 || rawIndustryAlerts.length > 0 || focusIndustrySuggestions.length > 0)) {
        return null;
    }

    return (
        <Card
            size="small"
            data-testid="industry-alerts-card"
            style={{
                marginBottom: 12,
                background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 94%, var(--accent-warning) 6%) 0%, color-mix(in srgb, var(--bg-secondary) 96%, var(--accent-primary) 4%) 100%)',
                border: '1px solid color-mix(in srgb, var(--border-color) 82%, transparent 18%)',
                boxShadow: '0 10px 30px rgba(15, 23, 42, 0.06)',
            }}
            styles={{ body: { padding: '12px 14px' } }}
        >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>行业异动提醒</span>
                    <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>支持按规则筛选，也可以只订阅观察列表里的行业提醒</span>
                </div>
                <Space size={8} wrap>
                    <Tag color="processing" style={{ margin: 0, borderRadius: 999 }}>{industryAlertsWithSeverity.length} 条提醒</Tag>
                    <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>{subscribedAlertNewCount} 条新增</Tag>
                    <Tag color={industryAlertSubscription.scope === 'watchlist' ? 'gold' : 'default'} style={{ margin: 0, borderRadius: 999 }}>
                        {industryAlertSubscription.scope === 'watchlist' ? '仅观察列表' : '全部行业'}
                    </Tag>
                    <Tag color={desktopAlertNotifications ? 'processing' : 'default'} style={{ margin: 0, borderRadius: 999 }}>
                        {desktopAlertNotifications ? '桌面通知已开' : '桌面通知未开'}
                    </Tag>
                    <Button size="small" type="text" onClick={() => setShowAdvancedSettings((current) => !current)}>
                        {showAdvancedSettings ? '收起高级设置' : '高级设置'}
                    </Button>
                </Space>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
                <Space size={[8, 8]} wrap>
                    <Radio.Group
                        value={industryAlertRule}
                        onChange={(event) => setIndustryAlertRule(event.target.value)}
                        size="small"
                        buttonStyle="solid"
                        aria-label="选择行业提醒规则"
                    >
                        <Radio.Button value="all">全部</Radio.Button>
                        <Radio.Button value="new">新增</Radio.Button>
                        <Radio.Button value="capital">资金</Radio.Button>
                        <Radio.Button value="risk">风险</Radio.Button>
                        <Radio.Button value="rotation">轮动</Radio.Button>
                    </Radio.Group>

                    <Select value={industryAlertRecency} onChange={setIndustryAlertRecency} size="small" style={{ width: 128 }} disabled={industryAlertRule !== 'new'} aria-label="选择新增提醒时间范围">
                        {industryAlertRecencyOptions.map((item) => (
                            <Option key={item.value} value={item.value}>{item.label}</Option>
                        ))}
                    </Select>
                </Space>

                <Space size={[8, 8]} wrap>
                    <Radio.Group
                        value={industryAlertSubscription.scope}
                        onChange={(event) => setIndustryAlertSubscription((current) => ({ ...current, scope: event.target.value }))}
                        size="small"
                        buttonStyle="solid"
                        aria-label="选择提醒订阅范围"
                    >
                        <Radio.Button value="all">全部行业</Radio.Button>
                        <Radio.Button value="watchlist">观察列表</Radio.Button>
                    </Radio.Group>
                </Space>
            </div>

            {showAdvancedSettings && (
                <div
                    style={{
                        marginBottom: 12,
                        padding: '10px 12px',
                        borderRadius: 12,
                        background: 'rgba(255,255,255,0.56)',
                        border: '1px dashed color-mix(in srgb, var(--border-color) 82%, transparent 18%)',
                    }}
                    data-testid="industry-alert-thresholds-panel"
                >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>提醒阈值</span>
                            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>按自己的研究节奏调节提醒门槛，停止输入后会自动保存。</span>
                        </div>
                        <Space size={[8, 8]} wrap>
                            <Checkbox.Group
                                value={industryAlertSubscription.kinds}
                                options={industryAlertKindOptions}
                                aria-label="选择提醒种类"
                                onChange={(values) => {
                                    const nextKinds = values.filter((item) => industryAlertKindOptions.some((option) => option.value === item));
                                    if (nextKinds.length === 0) {
                                        message.warning('至少保留一种提醒规则');
                                        return;
                                    }
                                    setIndustryAlertSubscription((current) => ({ ...current, kinds: nextKinds }));
                                }}
                            />
                            <Button size="small" icon={<NotificationOutlined />} onClick={requestDesktopAlertPermission}>
                                {desktopAlertNotifications ? '重检通知权限' : '开启桌面通知'}
                            </Button>
                        </Space>
                    </div>
                    <Row gutter={[10, 10]}>
                        <Col xs={12} md={8} lg={4}>
                            <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>强势共振分数</span>
                            <InputNumber
                                size="small"
                                min={50}
                                max={100}
                                value={draftThresholds.resonance_score}
                                style={{ width: '100%' }}
                                onChange={(value) => updateDraftThreshold('resonance_score', value)}
                                aria-label="设置强势共振分数阈值"
                            />
                        </Col>
                        <Col xs={12} md={8} lg={4}>
                            <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>资金突入阈值(亿)</span>
                            <InputNumber
                                size="small"
                                min={1}
                                max={50}
                                value={Number(draftThresholds.capital_inflow_yi || 0)}
                                style={{ width: '100%' }}
                                onChange={(value) => updateDraftThreshold('capital_inflow_yi', value)}
                                aria-label="设置资金突入阈值"
                            />
                        </Col>
                        <Col xs={12} md={8} lg={4}>
                            <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>风险释放阈值(亿)</span>
                            <InputNumber
                                size="small"
                                min={1}
                                max={50}
                                value={Number(draftThresholds.risk_release_outflow_yi || 0)}
                                style={{ width: '100%' }}
                                onChange={(value) => updateDraftThreshold('risk_release_outflow_yi', value)}
                                aria-label="设置风险释放阈值"
                            />
                        </Col>
                        <Col xs={12} md={8} lg={4}>
                            <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>高波动阈值(%)</span>
                            <InputNumber
                                size="small"
                                min={1}
                                max={10}
                                step={0.1}
                                value={Number(draftThresholds.high_volatility_threshold || 0)}
                                style={{ width: '100%' }}
                                onChange={(value) => updateDraftThreshold('high_volatility_threshold', value)}
                                aria-label="设置高波动阈值"
                            />
                        </Col>
                        <Col xs={12} md={8} lg={4}>
                            <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>轮动换手阈值(%)</span>
                            <InputNumber
                                size="small"
                                min={1}
                                max={10}
                                step={0.1}
                                value={Number(draftThresholds.rotation_turnover_threshold || 0)}
                                style={{ width: '100%' }}
                                onChange={(value) => updateDraftThreshold('rotation_turnover_threshold', value)}
                                aria-label="设置轮动换手阈值"
                            />
                        </Col>
                        <Col xs={12} md={8} lg={4}>
                            <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>价格确认阈值(%)</span>
                            <InputNumber
                                size="small"
                                min={0}
                                max={10}
                                step={0.1}
                                value={Number(draftThresholds.capital_inflow_change_pct || 0)}
                                style={{ width: '100%' }}
                                onChange={(value) => updateDraftThreshold('capital_inflow_change_pct', value, {
                                    risk_release_change_pct: Number(value || 0),
                                })}
                                aria-label="设置价格确认阈值"
                            />
                        </Col>
                    </Row>
                </div>
            )}

            {industryAlertsWithSeverity.length > 0 ? (
                <>
                    <Row gutter={[10, 10]}>
                        {visibleAlerts.map((alert) => (
                        <Col xs={24} md={12} key={`${alert.industry_name}-${alert.title}`}>
                            <div
                                data-testid="industry-alert-item"
                                style={{
                                    height: '100%',
                                    borderRadius: 12,
                                    padding: '12px 12px 10px',
                                    background: 'color-mix(in srgb, var(--bg-primary) 26%, var(--bg-secondary) 74%)',
                                    border: `1px solid ${alert.accent}33`,
                                    boxShadow: `inset 0 0 0 1px ${alert.accent}14`,
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                            <Tag color={alert.color} style={{ margin: 0, borderRadius: 999, fontSize: 11 }}>{alert.title}</Tag>
                                            <Tag color={alert.severity?.color || 'default'} style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                                严重度 {alert.severity?.label || '低'}
                                            </Tag>
                                            <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{alert.industry_name}</span>
                                            <Tag color={alert.isNew ? 'magenta' : 'default'} style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                                {alert.isNew ? '本次会话新增' : '持续关注'}
                                            </Tag>
                                        </div>
                                        <div style={{ fontSize: 12, lineHeight: 1.7, color: 'var(--text-primary)' }}>{alert.summary}</div>
                                    </div>
                                    <Space size={6} wrap>
                                        <Tag color="default" style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>{alert.seenLabel}</Tag>
                                        {selectedIndustry === alert.industry_name && (
                                            <Tag color="gold" style={{ margin: 0, borderRadius: 999 }}>已聚焦</Tag>
                                        )}
                                    </Space>
                                </div>
                                <div style={{ fontSize: 11, lineHeight: 1.7, color: 'var(--text-secondary)', marginBottom: 10 }}>
                                    {alert.reason}
                                </div>
                                <Space size={8} wrap>
                                    <Button
                                        size="small"
                                        type="text"
                                        icon={<StarFilled style={{ color: watchlistIndustries.includes(alert.industry_name) ? '#faad14' : 'rgba(0,0,0,0.25)' }} />}
                                        onClick={() => toggleWatchlistIndustry(alert.industry_name)}
                                    >
                                        {watchlistIndustries.includes(alert.industry_name) ? '已在观察' : '加入观察'}
                                    </Button>
                                    <Button size="small" type={selectedIndustry === alert.industry_name ? 'default' : 'primary'} onClick={() => setSelectedIndustry(alert.industry_name)}>
                                        聚焦
                                    </Button>
                                    <Button size="small" type="text" onClick={() => handleIndustryClick(alert.industry_name)}>
                                        查看详情
                                    </Button>
                                    <Button size="small" type="text" icon={<BranchesOutlined />} onClick={() => handleAddToComparison(alert.industry_name)}>
                                        加入对比
                                    </Button>
                                </Space>
                            </div>
                        </Col>
                        ))}
                    </Row>
                    {industryAlertsWithSeverity.length > visibleAlerts.length && (
                        <div style={{ marginTop: 10, display: 'flex', justifyContent: 'center' }}>
                            <Button size="small" type="text" onClick={() => setShowAllAlerts((current) => !current)}>
                                {showAllAlerts ? '收起更多提醒' : `展开其余 ${industryAlertsWithSeverity.length - visibleAlerts.length} 条提醒`}
                            </Button>
                        </div>
                    )}
                </>
            ) : (
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                        industryAlertRule === 'new'
                            ? `当前没有${industryAlertRecency === 'session' ? '本次会话内' : `最近 ${industryAlertRecency} 分钟内`}新增提醒`
                            : (industryAlertSubscription.scope === 'watchlist'
                                ? '当前观察列表中没有匹配订阅规则的提醒'
                                : '当前筛选下没有匹配提醒')
                    }
                >
                    <Space size={8} wrap>
                        <Button size="small" onClick={() => setIndustryAlertRule('all')}>查看全部提醒</Button>
                        {industryAlertSubscription.scope === 'watchlist' && (
                            <Button size="small" type="text" onClick={() => setIndustryAlertSubscription((current) => ({ ...current, scope: 'all' }))}>
                                切回全部行业
                            </Button>
                        )}
                    </Space>
                </Empty>
            )}

            {alertTimelineEntries.length > 0 && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px dashed color-mix(in srgb, var(--border-color) 82%, transparent 18%)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: showTimeline ? 10 : 0, flexWrap: 'wrap' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.04em' }}>提醒时间线</span>
                            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>按最近触发排序，保留会话内与本地持久化的提醒命中轨迹</span>
                        </div>
                        <Space size={8} wrap>
                            <Tag color="default" style={{ margin: 0, borderRadius: 999 }}>最近 {alertTimelineEntries.length} 条</Tag>
                            <Button size="small" type="text" onClick={() => setShowTimeline((current) => !current)}>
                                {showTimeline ? '收起时间线' : '展开时间线'}
                            </Button>
                        </Space>
                    </div>

                    {showTimeline && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {alertTimelineEntries.map((entry) => (
                                <div
                                    key={`${entry.industry_name}:${entry.kind}`}
                                    style={{
                                        position: 'relative',
                                        padding: '10px 12px 10px 18px',
                                        borderRadius: 10,
                                        background: 'rgba(255,255,255,0.48)',
                                        border: '1px solid color-mix(in srgb, var(--border-color) 85%, transparent 15%)',
                                    }}
                                >
                                <div
                                    style={{
                                        position: 'absolute',
                                        left: 8,
                                        top: 14,
                                        width: 6,
                                        height: 6,
                                        borderRadius: '50%',
                                        background: entry.accent || '#1677ff',
                                        boxShadow: `0 0 0 4px ${(entry.accent || '#1677ff')}18`,
                                    }}
                                />
                                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                            <Tag color={entry.color || 'processing'} style={{ margin: 0, borderRadius: 999, fontSize: 11 }}>{entry.title || '异动提醒'}</Tag>
                                            <Tag color={entry.severity?.color || 'default'} style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                                严重度 {entry.severity?.label || '低'}
                                            </Tag>
                                            <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{entry.industry_name}</span>
                                            <Tag color={entry.isNew ? 'magenta' : 'default'} style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                                {entry.isNew ? '近期新增' : '持续追踪'}
                                            </Tag>
                                            <Tag color="default" style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>命中 {entry.hitCount || 1} 次</Tag>
                                        </div>
                                        <div style={{ fontSize: 12, lineHeight: 1.7, color: 'var(--text-primary)' }}>
                                            {entry.summary || entry.reason || '暂无更多说明'}
                                        </div>
                                    </div>
                                    <Space size={6} wrap>
                                        <Tag color="default" style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                            首次 {formatIndustryAlertSeenLabel(entry.firstSeenAt)}
                                        </Tag>
                                        <Tag color="default" style={{ margin: 0, borderRadius: 999, fontSize: 10 }}>
                                            最近 {formatIndustryAlertSeenLabel(entry.lastSeenAt)}
                                        </Tag>
                                    </Space>
                                </div>

                                <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                                        {entry.reason || '当前时间线会结合命中次数和最近出现时间，帮助判断异动是偶发还是持续。'}
                                    </div>
                                    <Space size={8} wrap>
                                        <Button size="small" type={selectedIndustry === entry.industry_name ? 'default' : 'primary'} onClick={() => setSelectedIndustry(entry.industry_name)}>
                                            聚焦
                                        </Button>
                                        <Button size="small" type="text" onClick={() => handleIndustryClick(entry.industry_name)}>
                                            查看详情
                                        </Button>
                                    </Space>
                                </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            <div style={{ marginTop: 10, fontSize: 10, color: 'var(--text-muted)' }}>
                当前为截面异动提醒；订阅设置会保留，下次进入页面仍按你的观察范围和规则显示。“新增”仍基于本页会话内首次出现时间判断。
            </div>
        </Card>
    );
};

export default IndustryAlertsPanel;
