/**
 * Industry dashboard hero header (layer-2 split of IndustryDashboard).
 *
 * Pure presentational — renders the eyebrow / heading / sentiment chips and the
 * action-posture + metric strip at the top of the page. The parent
 * (`IndustryDashboard`) computes all derived values from
 * `useIndustryDashboardData` and passes them in; this child only lays them out.
 *
 * The JSX, class names, inline styles and Chinese copy are a verbatim move of
 * the former hero <Card> block, so behavior is unchanged.
 */

import { Card, Tag, Space, Typography } from 'antd';
import { FireOutlined, BranchesOutlined } from '@ant-design/icons';

const { Title, Paragraph } = Typography;

const IndustryDashboardHero = ({
    sentimentTone,
    heatmapCoveragePct,
    actionLevelColor,
    industryActionPosture,
    selectedIndustry,
    heatmapIndustries,
    heatmapSummary,
    watchlistEntries,
    subscribedAlertNewCount,
}) => (
    <Card className="app-page-hero app-page-hero--industry" variant="borderless">
        <div className="app-page-hero__header industry-hero-header">
            <div className="app-page-hero__content industry-hero-header__content">
                <div className="app-page-eyebrow">
                    <FireOutlined />
                    行业指挥席
                </div>
                <div className="app-page-heading">
                    <span className="app-page-heading__icon">
                        <BranchesOutlined />
                    </span>
                    <div>
                        <Title level={3} style={{ margin: 0, color: 'var(--text-primary)' }}>
                            行业轮动大屏
                        </Title>
                        <Paragraph className="industry-hero-description" style={{ margin: '2px 0 0', color: 'var(--text-secondary)', maxWidth: 720, fontSize: 12.5 }}>
                            左侧先完成行业扫描与切换，右侧只保留当前焦点、龙头线索和下一步动作。
                        </Paragraph>
                    </div>
                </div>
                <Space wrap size={[8, 8]} className="industry-hero-chip-row" style={{ marginTop: 6 }}>
                    <Tag color={sentimentTone?.color === '#ff4d4f' ? 'error' : sentimentTone?.color === '#52c41a' ? 'success' : 'processing'} style={{ marginInlineEnd: 0 }}>
                        市场情绪：{sentimentTone?.label || '待刷新'}
                    </Tag>
                    {heatmapCoveragePct != null ? (
                        <Tag color="default" style={{ marginInlineEnd: 0 }}>
                            市值覆盖：{heatmapCoveragePct}%
                        </Tag>
                    ) : null}
                </Space>
                <div className="industry-hero-summary-grid">
                    <div className="industry-hero-brief">
                        <div>
                            <div className="industry-hero-brief__eyebrow">当前动作</div>
                            <div className="industry-hero-brief__title" style={{ color: actionLevelColor === 'gold' ? '#fde68a' : actionLevelColor === 'processing' ? '#bfdbfe' : '#bbf7d0' }}>
                                {industryActionPosture.title}
                            </div>
                            {selectedIndustry ? (
                                <Space wrap size={[6, 6]} className="industry-hero-brief__meta">
                                    <Tag color="cyan" style={{ marginInlineEnd: 0, borderRadius: 999 }}>
                                        焦点：{selectedIndustry}
                                    </Tag>
                                    <Tag color="default" style={{ marginInlineEnd: 0, borderRadius: 999 }}>
                                        详情 / 龙头 / 对比
                                    </Tag>
                                </Space>
                            ) : null}
                        </div>
                        <div className="industry-hero-brief__text">
                            {selectedIndustry
                                ? `${selectedIndustry} 已进入研究焦点，建议先确认行业详情、龙头承接和轮动位置，再决定是否加入观察或进入对比。`
                                : industryActionPosture.actionHint}
                        </div>
                    </div>
                    <div className="app-page-metric-strip industry-hero-metrics">
                        <div className="app-page-metric-card">
                            <span className="app-page-metric-card__label">热力覆盖</span>
                            <span className="app-page-metric-card__value">{heatmapIndustries.length} 个行业</span>
                        </div>
                        <div className="app-page-metric-card">
                            <span className="app-page-metric-card__label">上涨占比</span>
                            <span className="app-page-metric-card__value">
                                {heatmapSummary?.upRatio != null ? `${heatmapSummary.upRatio}%` : '--'}
                            </span>
                        </div>
                        <div className="app-page-metric-card">
                            <span className="app-page-metric-card__label">市值覆盖</span>
                            <span className="app-page-metric-card__value">
                                {heatmapCoveragePct != null ? `${heatmapCoveragePct}%` : '--'}
                            </span>
                        </div>
                        <div className="app-page-metric-card">
                            <span className="app-page-metric-card__label">观察 / 新提醒</span>
                            <span className="app-page-metric-card__value">
                                {watchlistEntries.length} / {subscribedAlertNewCount || 0}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </Card>
);

export default IndustryDashboardHero;
