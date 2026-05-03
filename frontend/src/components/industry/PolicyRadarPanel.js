import React, { useEffect, useState, useCallback } from 'react';
import { Card, Empty, Spin, Tag, Tooltip, Typography, Space, Button } from 'antd';
import { ReloadOutlined, LinkOutlined, RadarChartOutlined } from '@ant-design/icons';

import { getPolicyRadarSignal, getPolicyRadarRecords } from '../../services/api';

const { Text, Link } = Typography;

const SIGNAL_PALETTE = {
    bullish: { color: 'var(--accent-danger)', label: '偏多' },
    bearish: { color: 'var(--accent-success)', label: '偏空' },
    neutral: { color: 'var(--text-muted)', label: '中性' },
};

const SOURCE_LEVEL_PALETTE = {
    healthy: { color: 'var(--accent-success)', label: '健康' },
    watch: { color: 'var(--accent-warning)', label: '观察' },
    fragile: { color: 'var(--accent-danger)', label: '脆弱' },
};

const formatTimestamp = (value) => {
    if (!value) return '—';
    try {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
    } catch (_err) {
        return value;
    }
};

const formatScore = (value) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return value.toFixed(2);
};

const renderIndustrySignals = (industrySignals = {}) => {
    const entries = Object.entries(industrySignals)
        .filter(([, info]) => info && typeof info === 'object')
        .sort((a, b) => Math.abs((b[1].avg_impact ?? 0)) - Math.abs((a[1].avg_impact ?? 0)))
        .slice(0, 8);

    if (entries.length === 0) {
        return <Text type="secondary">暂无行业级别政策信号。</Text>;
    }

    return (
        <Space size={[8, 8]} wrap>
            {entries.map(([industry, info]) => {
                const signalKey = info.signal || 'neutral';
                const palette = SIGNAL_PALETTE[signalKey] || SIGNAL_PALETTE.neutral;
                return (
                    <Tooltip
                        key={industry}
                        title={`${industry} · 平均影响 ${formatScore(info.avg_impact)} · 提及 ${info.mentions ?? 0}`}
                    >
                        <Tag color={palette.color}>
                            {industry} · {palette.label}
                        </Tag>
                    </Tooltip>
                );
            })}
        </Space>
    );
};

const renderSourceHealth = (sourceHealth = {}) => {
    const entries = Object.entries(sourceHealth);
    if (entries.length === 0) return null;
    return (
        <Space size={[6, 6]} wrap>
            {entries.map(([sourceId, health]) => {
                const palette = SOURCE_LEVEL_PALETTE[health?.level] || SOURCE_LEVEL_PALETTE.fragile;
                return (
                    <Tooltip
                        key={sourceId}
                        title={`记录数 ${health?.record_count ?? 0} · 全文比例 ${formatScore(health?.full_text_ratio)}`}
                    >
                        <Tag color={palette.color} style={{ fontSize: 12 }}>
                            {sourceId} · {palette.label}
                        </Tag>
                    </Tooltip>
                );
            })}
        </Space>
    );
};

const renderRecord = (record) => {
    const raw = record?.raw_value || {};
    const meta = record?.metadata || {};
    const link = meta.detail_url || meta.link || null;
    const tags = Array.isArray(record?.tags) ? record.tags : [];
    const score = record?.normalized_score;
    return (
        <li
            key={record?.record_id || `${record?.source}-${record?.timestamp}`}
            className="policy-radar-record"
            style={{ paddingBottom: 8, borderBottom: '1px solid var(--border-color)' }}
        >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <Text strong>{raw.title || '（无标题）'}</Text>
                <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                    {formatTimestamp(record?.timestamp)}
                </Text>
            </div>
            {raw.summary || raw.excerpt ? (
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                    {raw.summary || raw.excerpt}
                </Text>
            ) : null}
            <Space size={[4, 4]} wrap style={{ marginTop: 6 }}>
                <Tag>{record?.source || 'policy_radar'}</Tag>
                <Tag>得分 {formatScore(score)}</Tag>
                {tags.slice(0, 4).map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                ))}
                {link ? (
                    <Link href={link} target="_blank" rel="noreferrer noopener">
                        <LinkOutlined /> 原文
                    </Link>
                ) : null}
            </Space>
        </li>
    );
};

const PolicyRadarPanel = ({ industry = null, timeframe = '7d', limit = 10 }) => {
    const [loading, setLoading] = useState(true);
    const [signal, setSignal] = useState(null);
    const [records, setRecords] = useState([]);
    const [available, setAvailable] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        Promise.all([
            getPolicyRadarSignal().catch(() => null),
            getPolicyRadarRecords({ industry, timeframe, limit }).catch(() => null),
        ]).then(([signalResp, recordsResp]) => {
            if (cancelled) return;
            const signalData = signalResp?.data || null;
            const recordsData = recordsResp?.data || null;
            setSignal(signalData);
            setRecords(recordsData?.records || []);
            setAvailable(Boolean(signalData?.available || recordsData?.available));
            setLoading(false);
        });
        return () => { cancelled = true; };
    }, [industry, timeframe, limit, refreshKey]);

    return (
        <Card
            title={(
                <Space>
                    <RadarChartOutlined />
                    <span>政策雷达</span>
                    {signal?.last_refresh ? (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                            更新于 {formatTimestamp(signal.last_refresh)}
                        </Text>
                    ) : null}
                </Space>
            )}
            extra={(
                <Button
                    type="text"
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={refresh}
                    loading={loading}
                    aria-label="刷新政策雷达"
                />
            )}
            size="small"
            data-testid="policy-radar-panel"
        >
            {loading && !signal ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '24px 0' }}>
                    <Spin />
                </div>
            ) : !available ? (
                <Empty
                    description="政策数据未就绪。请确认 alt-data 调度器已启动并完成首次抓取。"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
            ) : (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <div>
                        <Text type="secondary" style={{ fontSize: 12 }}>共 {signal?.policy_count ?? 0} 条政策记录</Text>
                        <div style={{ marginTop: 6 }}>
                            {renderSourceHealth(signal?.source_health)}
                        </div>
                    </div>
                    <div>
                        <Text strong style={{ fontSize: 12 }}>行业信号</Text>
                        <div style={{ marginTop: 6 }}>
                            {renderIndustrySignals(signal?.industry_signals)}
                        </div>
                    </div>
                    <div>
                        <Text strong style={{ fontSize: 12 }}>
                            最近政策{industry ? `（${industry}）` : ''}
                        </Text>
                        {records.length === 0 ? (
                            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
                                此时间窗内无政策记录。
                            </Text>
                        ) : (
                            <ul
                                style={{
                                    listStyle: 'none',
                                    padding: 0,
                                    margin: '6px 0 0',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: 8,
                                }}
                            >
                                {records.slice(0, limit).map(renderRecord)}
                            </ul>
                        )}
                    </div>
                </Space>
            )}
        </Card>
    );
};

export default PolicyRadarPanel;
