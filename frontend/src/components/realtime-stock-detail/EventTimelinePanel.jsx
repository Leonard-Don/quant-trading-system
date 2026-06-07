/**
 * Intraday event-timeline panel for RealtimeStockDetailModal (layer 2 split).
 *
 * Pure render — no hooks, no data fetching. Owns the verbatim "盘中时间线"
 * section (per-event cards with follow-through tracking, or an empty state)
 * that previously lived inline in the parent modal body. Receives the parent's
 * eventTimeline, the live quote, and the quoteMap used by alert-hit
 * follow-through evaluation. The parent stays the orchestrator; this child only
 * renders.
 */

import { Tag, Empty, Typography } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import { evaluateAlertHitFollowThrough } from '../../utils/realtimeSignals';
import {
    getTimelineToneStyle,
    formatTimelineTime,
    getFollowThroughSummary,
} from './helpers.jsx';

const { Text } = Typography;

const EventTimelinePanel = ({
    eventTimeline,
    quote,
    quoteMap,
}) => (
    <section
        style={{
            borderRadius: 18,
            border: '1px solid var(--border-color)',
            background: 'var(--bg-secondary)',
            padding: 18,
            boxShadow: '0 8px 26px rgba(15, 23, 42, 0.06)',
        }}
    >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
            <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 700 }}>
                    <ClockCircleOutlined />
                    盘中时间线
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                    把实时异动、提醒草稿、交易计划和复盘记录串起来，便于快速回看这只标的在盘中的决策过程。
                </Text>
            </div>
            <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10, fontWeight: 700 }}>
                最近事件 {eventTimeline.length}
            </Tag>
        </div>

        {eventTimeline.length ? (
            <div data-testid="detail-event-timeline" style={{ display: 'grid', gap: 12 }}>
                {eventTimeline.map((event) => {
                    const toneStyle = getTimelineToneStyle(event.tone);
                    const followThrough = event.kind === 'alert_triggered'
                        ? (() => {
                            const result = evaluateAlertHitFollowThrough(event, quote, quoteMap || {});
                            return {
                                label: result.label,
                                description: result.description,
                                tone: result.state === 'continued'
                                    ? 'positive'
                                    : result.state === 'reversed'
                                        ? 'negative'
                                        : 'neutral',
                            };
                        })()
                        : getFollowThroughSummary(event, quote);
                    const followToneStyle = getTimelineToneStyle(followThrough.tone);
                    return (
                        <div
                            key={event.id}
                            style={{
                                display: 'grid',
                                gap: 10,
                                padding: '14px 16px',
                                borderRadius: 16,
                                border: `1px solid ${toneStyle.borderColor}`,
                                background: toneStyle.background,
                            }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(255,255,255,0.72)', color: toneStyle.color, fontWeight: 700 }}>
                                        {event.sourceLabel || '事件'}
                                    </Tag>
                                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                                        {event.title || '未命名事件'}
                                    </span>
                                </div>
                                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                    {formatTimelineTime(event.createdAt)}
                                </span>
                            </div>
                            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                                {event.description || '暂无更多说明'}
                            </div>
                            <div
                                style={{
                                    display: 'grid',
                                    gap: 6,
                                    padding: '10px 12px',
                                    borderRadius: 14,
                                    border: `1px solid ${followToneStyle.borderColor}`,
                                    background: 'rgba(255,255,255,0.72)',
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: followToneStyle.background, color: followToneStyle.color, fontWeight: 700 }}>
                                        后效跟踪
                                    </Tag>
                                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                                        {followThrough.label}
                                    </span>
                                </div>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                    {followThrough.description}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        ) : (
            <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                    <div data-testid="detail-event-timeline-empty">
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>还没有积累到盘中事件</div>
                        <div style={{ marginTop: 6, color: 'var(--text-secondary)' }}>
                            当这只标的触发异动、生成提醒或保存复盘快照后，这里会自动出现一条时间线。
                        </div>
                    </div>
                }
            />
        )}
    </section>
);

export default EventTimelinePanel;
