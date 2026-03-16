import React, { useState, useEffect, useMemo } from 'react';
import {
    Card,
    Row,
    Col,
    Statistic,
    Tag,
    List,
    Typography,
    Spin,
    Empty,
    Progress,
    Space,
    Tooltip,
    Badge
} from 'antd';
import {
    SmileOutlined,
    FrownOutlined,
    MehOutlined,
    RiseOutlined,
    FallOutlined,
    ThunderboltOutlined,
    ClockCircleOutlined,
    LinkOutlined
} from '@ant-design/icons';
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip as RechartsTooltip,
    ResponsiveContainer,
    ReferenceLine
} from 'recharts';

const { Text, Title, Paragraph } = Typography;

/**
 * 情绪仪表盘组件
 * 
 * 显示新闻情绪分析结果和趋势
 */
const SentimentDashboard = ({
    symbol = 'AAPL',
    newsData = [],
    sentimentHistory = [],
    loading = false,
    onRefresh
}) => {
    // 计算综合情绪指标
    const sentimentMetrics = useMemo(() => {
        if (!newsData || newsData.length === 0) {
            return {
                averageScore: 0,
                label: 'Neutral',
                positiveCount: 0,
                negativeCount: 0,
                neutralCount: 0
            };
        }

        const scores = newsData.map(n => n.overall_sentiment_score || 0);
        const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length;

        return {
            averageScore: avgScore,
            label: getSentimentLabel(avgScore),
            positiveCount: newsData.filter(n => (n.overall_sentiment_score || 0) > 0.1).length,
            negativeCount: newsData.filter(n => (n.overall_sentiment_score || 0) < -0.1).length,
            neutralCount: newsData.filter(n => Math.abs(n.overall_sentiment_score || 0) <= 0.1).length
        };
    }, [newsData]);

    // 获取情绪标签
    function getSentimentLabel(score) {
        if (score > 0.25) return 'Bullish';
        if (score > 0.1) return 'Somewhat-Bullish';
        if (score < -0.25) return 'Bearish';
        if (score < -0.1) return 'Somewhat-Bearish';
        return 'Neutral';
    }

    // 获取情绪颜色
    function getSentimentColor(label) {
        switch (label) {
            case 'Bullish': return '#52c41a';
            case 'Somewhat-Bullish': return '#73d13d';
            case 'Bearish': return '#ff4d4f';
            case 'Somewhat-Bearish': return '#ff7875';
            default: return '#faad14';
        }
    }

    // 获取情绪图标
    function getSentimentIcon(label) {
        switch (label) {
            case 'Bullish':
            case 'Somewhat-Bullish':
                return <SmileOutlined style={{ color: getSentimentColor(label) }} />;
            case 'Bearish':
            case 'Somewhat-Bearish':
                return <FrownOutlined style={{ color: getSentimentColor(label) }} />;
            default:
                return <MehOutlined style={{ color: getSentimentColor(label) }} />;
        }
    }

    // 格式化日期
    function formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const now = new Date();
        const diffHours = Math.floor((now - date) / (1000 * 60 * 60));

        if (diffHours < 1) return '刚刚';
        if (diffHours < 24) return `${diffHours}小时前`;
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays < 7) return `${diffDays}天前`;
        return date.toLocaleDateString();
    }

    // 情绪趋势图数据
    const trendData = useMemo(() => {
        if (!sentimentHistory || sentimentHistory.length === 0) {
            // 使用模拟数据
            return Array.from({ length: 14 }, (_, i) => ({
                date: new Date(Date.now() - (13 - i) * 24 * 60 * 60 * 1000).toLocaleDateString(),
                sentiment: Math.random() * 0.6 - 0.3
            }));
        }
        return sentimentHistory;
    }, [sentimentHistory]);

    if (loading) {
        return (
            <Card>
                <div style={{ textAlign: 'center', padding: 40 }}>
                    <Spin size="large" />
                    <Text style={{ display: 'block', marginTop: 16 }}>加载情绪数据中...</Text>
                </div>
            </Card>
        );
    }

    return (
        <div>
            {/* 情绪概览 */}
            <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={6}>
                    <Card size="small" style={{
                        background: `linear-gradient(135deg, ${getSentimentColor(sentimentMetrics.label)}20, ${getSentimentColor(sentimentMetrics.label)}05)`
                    }}>
                        <Statistic
                            title={<span>{getSentimentIcon(sentimentMetrics.label)} 综合情绪</span>}
                            value={sentimentMetrics.label}
                            valueStyle={{
                                color: getSentimentColor(sentimentMetrics.label),
                                fontSize: '20px'
                            }}
                        />
                        <Progress
                            percent={Math.round((sentimentMetrics.averageScore + 1) * 50)}
                            showInfo={false}
                            strokeColor={getSentimentColor(sentimentMetrics.label)}
                            trailColor="#f0f0f0"
                            size="small"
                        />
                    </Card>
                </Col>

                <Col span={6}>
                    <Card size="small" style={{ background: 'linear-gradient(135deg, #52c41a20, #52c41a05)' }}>
                        <Statistic
                            title={<span><RiseOutlined style={{ color: '#52c41a' }} /> 积极新闻</span>}
                            value={sentimentMetrics.positiveCount}
                            suffix={`/ ${newsData.length}`}
                            valueStyle={{ color: '#52c41a' }}
                        />
                    </Card>
                </Col>

                <Col span={6}>
                    <Card size="small" style={{ background: 'linear-gradient(135deg, #ff4d4f20, #ff4d4f05)' }}>
                        <Statistic
                            title={<span><FallOutlined style={{ color: '#ff4d4f' }} /> 消极新闻</span>}
                            value={sentimentMetrics.negativeCount}
                            suffix={`/ ${newsData.length}`}
                            valueStyle={{ color: '#ff4d4f' }}
                        />
                    </Card>
                </Col>

                <Col span={6}>
                    <Card size="small" style={{ background: 'linear-gradient(135deg, #faad1420, #faad1405)' }}>
                        <Statistic
                            title={<span><ThunderboltOutlined style={{ color: '#faad14' }} /> 情绪强度</span>}
                            value={Math.abs(sentimentMetrics.averageScore * 100).toFixed(1)}
                            suffix="%"
                            valueStyle={{ color: '#faad14' }}
                        />
                    </Card>
                </Col>
            </Row>

            <Row gutter={16}>
                {/* 情绪趋势图 */}
                <Col span={14}>
                    <Card title={`📈 ${symbol} 情绪趋势`} size="small">
                        <ResponsiveContainer width="100%" height={250}>
                            <AreaChart data={trendData}>
                                <defs>
                                    <linearGradient id="sentimentGradient" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#1890ff" stopOpacity={0.4} />
                                        <stop offset="95%" stopColor="#1890ff" stopOpacity={0.05} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                                <XAxis
                                    dataKey="date"
                                    tick={{ fontSize: 10 }}
                                    interval="preserveStartEnd"
                                />
                                <YAxis
                                    domain={[-1, 1]}
                                    tick={{ fontSize: 10 }}
                                    tickFormatter={(v) => v.toFixed(1)}
                                />
                                <RechartsTooltip
                                    formatter={(value) => [value?.toFixed(3), '情绪分数']}
                                />
                                <ReferenceLine y={0} stroke="#999" strokeDasharray="3 3" />
                                <ReferenceLine y={0.2} stroke="#52c41a" strokeDasharray="2 2" strokeOpacity={0.5} />
                                <ReferenceLine y={-0.2} stroke="#ff4d4f" strokeDasharray="2 2" strokeOpacity={0.5} />
                                <Area
                                    type="monotone"
                                    dataKey="sentiment"
                                    stroke="#1890ff"
                                    strokeWidth={2}
                                    fill="url(#sentimentGradient)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </Card>
                </Col>

                {/* 新闻列表 */}
                <Col span={10}>
                    <Card
                        title="📰 最新新闻"
                        size="small"
                        style={{ height: 310 }}
                        styles={{ body: { padding: '12px', maxHeight: 260, overflow: 'auto' } }}
                    >
                        {newsData.length === 0 ? (
                            <Empty description="暂无新闻数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        ) : (
                            <List
                                size="small"
                                dataSource={newsData.slice(0, 8)}
                                renderItem={(item) => (
                                    <List.Item style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                                        <div style={{ width: '100%' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                                <Text
                                                    strong
                                                    style={{
                                                        fontSize: 12,
                                                        flex: 1,
                                                        lineHeight: 1.4
                                                    }}
                                                    ellipsis={{ rows: 2 }}
                                                >
                                                    {item.title}
                                                </Text>
                                                <Tag
                                                    color={getSentimentColor(item.overall_sentiment_label || 'Neutral')}
                                                    style={{ marginLeft: 8, fontSize: 10 }}
                                                >
                                                    {item.overall_sentiment_label || 'Neutral'}
                                                </Tag>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                                                <Text type="secondary" style={{ fontSize: 10 }}>
                                                    {item.source} · <ClockCircleOutlined /> {formatDate(item.published_at)}
                                                </Text>
                                                {item.url && item.url !== '#' && (
                                                    <a href={item.url} target="_blank" rel="noopener noreferrer">
                                                        <LinkOutlined style={{ fontSize: 10 }} />
                                                    </a>
                                                )}
                                            </div>
                                        </div>
                                    </List.Item>
                                )}
                            />
                        )}
                    </Card>
                </Col>
            </Row>

            {/* 情绪信号提示 */}
            <Card size="small" style={{ marginTop: 16 }}>
                <Row gutter={16} align="middle">
                    <Col span={6}>
                        <Text strong>交易信号建议:</Text>
                    </Col>
                    <Col span={18}>
                        <Space>
                            {sentimentMetrics.averageScore > 0.2 && (
                                <Tag color="success" icon={<RiseOutlined />}>
                                    积极情绪 - 考虑做多
                                </Tag>
                            )}
                            {sentimentMetrics.averageScore < -0.2 && (
                                <Tag color="error" icon={<FallOutlined />}>
                                    消极情绪 - 考虑做空或观望
                                </Tag>
                            )}
                            {Math.abs(sentimentMetrics.averageScore) <= 0.2 && (
                                <Tag color="warning" icon={<MehOutlined />}>
                                    中性情绪 - 等待明确信号
                                </Tag>
                            )}
                            {Math.abs(sentimentMetrics.averageScore) > 0.5 && (
                                <Tooltip title="极端情绪可能预示反转">
                                    <Tag color="purple">
                                        ⚠️ 极端情绪警告
                                    </Tag>
                                </Tooltip>
                            )}
                        </Space>
                    </Col>
                </Row>
            </Card>
        </div>
    );
};

export default SentimentDashboard;
