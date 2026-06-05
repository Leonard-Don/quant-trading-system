/**
 * Overview tab content for MarketAnalysis (layer-3 split).
 *
 * Pure presentational component. Receives the overview / technical /
 * event slices plus the per-tab loading & error maps and renders the
 * exact markup previously inlined in MarketAnalysis. No data fetching,
 * no component-level state — behavior is byte-for-byte preserved.
 */
import { Suspense } from 'react';
import {
    Card,
    Row,
    Col,
    Tag,
    List,
    Typography,
    Alert,
    Space,
    Statistic,
    Empty,
    Spin,
    Popover,
    Tooltip,
} from 'antd';
import {
    RiseOutlined,
    FallOutlined,
    WarningOutlined,
    FundOutlined,
    LineChartOutlined,
    BankOutlined,
    CalendarOutlined,
    DollarCircleOutlined,
    NotificationOutlined,
    DashboardOutlined,
} from '@ant-design/icons';
import lazyWithRetry from '../../utils/lazyWithRetry';
import { MarketAnalysisSkeleton } from '../SkeletonLoaders';
import {
    RecommendationTag,
    ScoreGauge,
    ScoreRadarChart,
} from './MarketAnalysisScoreVisuals';
import { formatDisplayNumber } from '../../utils/marketAnalysisFormatters';

const CandlestickChart = lazyWithRetry(() => import('../CandlestickChart'));

const { Text } = Typography;

const OverviewTab = ({
    symbol,
    loadingTab,
    errorTab,
    overviewData,
    technicalData,
    eventData,
}) => {
    if (loadingTab.overview && !overviewData) {
        return <MarketAnalysisSkeleton />;
    }
    if (errorTab.overview) {
        return <Alert message="错误" description={errorTab.overview} type="error" showIcon />;
    }
    if (!overviewData) return <Empty description="请输入股票代码开始分析" />;

    const CONFIDENCE_MAP = {
        'VERY_HIGH': '极高',
        'HIGH': '高',
        'MEDIUM': '中',
        'LOW': '低',
        'VERY_LOW': '极低',
        'low': '低',
        'medium': '中',
        'high': '高'
    };

    const translateConfidence = (conf) => CONFIDENCE_MAP[conf?.toUpperCase()] || conf;

    const getIndicatorColor = (status) => {
        if (status === 'bullish' || status === 'oversold') return '#52c41a';
        if (status === 'bearish' || status === 'overbought') return '#ff4d4f';
        return '#faad14';
    };

    const getIndicatorIcon = (status) => {
        if (status === 'bullish' || status === 'oversold') return <RiseOutlined />;
        if (status === 'bearish' || status === 'overbought') return <FallOutlined />;
        return <DashboardOutlined />;
    };

    const scoreExplanationContent = (
        <List
            size="small"
            dataSource={overviewData.score_explanation || []}
            renderItem={item => (
                <List.Item style={{ padding: '8px 0' }}>
                    <div style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <Text strong>{item.dimension}</Text>
                            <Tag color={item.score >= 60 ? 'success' : item.score < 40 ? 'error' : 'warning'}>
                                {item.score}分
                            </Tag>
                        </div>
                        <Text type="secondary" style={{ fontSize: '12px' }}>{item.reason}</Text>
                    </div>
                </List.Item>
            )}
            style={{ width: 320 }}
        />
    );

    const recommendationReasonContent = (
        <div style={{ maxWidth: 300 }}>
            <Text strong>推荐理由:</Text>
            <ul style={{ paddingLeft: 20, margin: '8px 0 0 0', fontSize: '12px' }}>
                {(overviewData.recommendation_reasons || []).map((r, i) => (
                    <li key={i}>{r}</li>
                ))}
            </ul>
        </div>
    );

    return (
        <Row gutter={[16, 16]}>
            <Col xs={24} md={8}>
                <Card variant="borderless">
                    <Popover
                        content={scoreExplanationContent}
                        title="评分详情 (点击查看)"
                        trigger="click"
                        placement="right"
                    >
                        <div style={{ cursor: 'pointer' }}>
                            <ScoreGauge score={overviewData.overall_score} />
                        </div>
                    </Popover>
                    <div style={{ textAlign: 'center', marginTop: 16 }}>
                        <Space direction="vertical">
                            <Text type="secondary">投资建议</Text>
                            <Tooltip title={overviewData.recommendation_reasons?.length ? recommendationReasonContent : ''}>
                                <RecommendationTag recommendation={overviewData.recommendation} />
                            </Tooltip>
                            <Text type="secondary" style={{ fontSize: '12px' }}>
                                置信度: {translateConfidence(overviewData.confidence)}
                            </Text>
                        </Space>
                    </div>
                </Card>
            </Col>

            <Col xs={24} md={8}>
                <Card title="维度评分" variant="borderless">
                    <ScoreRadarChart scores={overviewData.scores} />
                </Card>
            </Col>

            <Col xs={24} md={8}>
                <Card title="关键信号" variant="borderless">
                    <List
                        dataSource={overviewData.key_signals}
                        renderItem={item => (
                            <List.Item>
                                <Space>
                                    <Tag color={item.importance === 'high' ? 'red' : 'blue'}>
                                        {item.type}
                                    </Tag>
                                    <Text>{item.signal}</Text>
                                </Space>
                            </List.Item>
                        )}
                    />
                </Card>
            </Col>

            {/* K线图 */}
            <Col span={24}>
                <Card
                    title={<><LineChartOutlined /> K线图表</>}
                    variant="borderless"
                >
                    <Suspense fallback={<div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>}>
                        <CandlestickChart symbol={symbol} embedMode />
                    </Suspense>
                </Card>
            </Col>

            {/* 技术指标快照 */}
            <Col span={24}>
                <Card
                    title={<><FundOutlined /> 技术指标快照</>}
                    variant="borderless"
                    extra={loadingTab.technical ? <Spin size="small" /> : null}
                >
                    {loadingTab.technical && !technicalData ? (
                        <div style={{ textAlign: 'center', padding: 20 }}><Spin /></div>
                    ) : technicalData ? (
                        <Row gutter={16}>
                            <Col xs={24} md={8}>
                                <Card size="small" variant="outlined">
                                    <Statistic
                                        title="RSI (14)"
                                        value={technicalData.rsi?.value}
                                        precision={2}
                                        valueStyle={{ color: getIndicatorColor(technicalData.rsi?.status) }}
                                        prefix={getIndicatorIcon(technicalData.rsi?.status)}
                                    />
                                    <Text type="secondary" style={{ fontSize: 12 }}>{technicalData.rsi?.signal}</Text>
                                </Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small" variant="outlined">
                                    <Statistic
                                        title="MACD"
                                        value={technicalData.macd?.value ?? technicalData.macd?.histogram}
                                        formatter={() => formatDisplayNumber(technicalData.macd?.value ?? technicalData.macd?.histogram, 4)}
                                        valueStyle={{ color: getIndicatorColor(technicalData.macd?.status) }}
                                        prefix={getIndicatorIcon(technicalData.macd?.status)}
                                    />
                                    <Text type="secondary" style={{ fontSize: 12 }}>{technicalData.macd?.trend || ''}</Text>
                                </Card>
                            </Col>
                            <Col xs={24} md={8}>
                                <Card size="small" variant="outlined">
                                    <Statistic
                                        title="布林带位置"
                                        value={technicalData.bollinger?.bandwidth}
                                        precision={2}
                                        suffix="%"
                                        valueStyle={{ color: getIndicatorColor(technicalData.bollinger?.position === 'above_upper' ? 'overbought' : technicalData.bollinger?.position === 'below_lower' ? 'oversold' : 'neutral') }}
                                    />
                                    <Text type="secondary" style={{ fontSize: 12 }}>{technicalData.bollinger?.signal}</Text>
                                </Card>
                            </Col>
                            {technicalData.overall && (
                                <Col span={24} style={{ marginTop: 12 }}>
                                    <Alert
                                        message={`综合信号: ${technicalData.overall.signal === 'strong_buy' ? '强力买入' :
                                            technicalData.overall.signal === 'buy' || technicalData.overall.signal === 'bullish' ? '看涨' :
                                                technicalData.overall.signal === 'strong_sell' ? '强力卖出' :
                                                    technicalData.overall.signal === 'sell' || technicalData.overall.signal === 'bearish' ? '看跌' :
                                                        technicalData.overall.signal === 'neutral' ? '中性' : '未知'
                                            }${technicalData.overall.description ? ' — ' + technicalData.overall.description : ''}`}
                                        type={
                                            (technicalData.overall.signal === 'bullish' || technicalData.overall.signal === 'buy' || technicalData.overall.signal === 'strong_buy') ? 'success' :
                                                (technicalData.overall.signal === 'bearish' || technicalData.overall.signal === 'sell' || technicalData.overall.signal === 'strong_sell') ? 'error' : 'info'
                                        }
                                        showIcon
                                    />
                                </Col>
                            )}
                        </Row>
                    ) : (
                        <Empty description="点击此处加载技术指标" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                </Card>
            </Col>

            <Col span={24}>
                <Card
                    title={<span><CalendarOutlined /> 重要事件</span>}
                    loading={!eventData && !!loadingTab.events}
                    style={{ marginTop: 0 }}
                >
                    {(!eventData || (!eventData.earnings && !eventData.dividends && !eventData.news?.length)) ? (
                        <Empty description="暂无近期重要事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    ) : (
                        <List
                            grid={{ gutter: 16, xs: 1, sm: 2, md: 3 }}
                            dataSource={[
                                {
                                    type: 'earnings',
                                    title: '下一财报日',
                                    icon: <DollarCircleOutlined style={{ color: '#1890ff', fontSize: 24 }} />,
                                    content: (
                                        <div>
                                            <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                                                {eventData.earnings?.next_earnings || '未定'}
                                            </div>
                                            {eventData.earnings?.estimate_avg && (
                                                <div style={{ fontSize: 12, color: '#666' }}>
                                                    预估EPS: ${eventData.earnings.estimate_avg}
                                                </div>
                                            )}
                                        </div>
                                    )
                                },
                                eventData.dividends?.last_amount > 0 ? {
                                    type: 'dividend',
                                    title: '分红派息',
                                    icon: <BankOutlined style={{ color: '#52c41a', fontSize: 24 }} />,
                                    content: (
                                        <div>
                                            <div style={{ fontSize: 16, fontWeight: 'bold' }}>
                                                ${eventData.dividends.last_amount} (最近)
                                            </div>
                                            <div style={{ fontSize: 12, color: '#666' }}>
                                                预计: {eventData.dividends.next_date_estimated || '未知'}
                                            </div>
                                        </div>
                                    )
                                } : null,
                                eventData.news && eventData.news.length > 0 ? {
                                    type: 'news',
                                    title: '最新动态',
                                    icon: <NotificationOutlined style={{ color: '#faad14', fontSize: 24 }} />,
                                    content: (
                                        <a
                                            href={eventData.news[0].link}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#1890ff' }}
                                            title={eventData.news[0].title}
                                        >
                                            {eventData.news[0].title}
                                        </a>
                                    )
                                } : null
                            ].filter(Boolean)}
                            renderItem={item => (
                                <List.Item>
                                    <Card size="small" variant="borderless">
                                        <List.Item.Meta
                                            avatar={item.icon}
                                            title={item.title}
                                            description={item.content}
                                        />
                                    </Card>
                                </List.Item>
                            )}
                        />
                    )}
                </Card>
            </Col>

            <Col span={24}>
                {overviewData.risk_warnings && overviewData.risk_warnings.length > 0 && (
                    <Alert
                        message="风险提示"
                        description={
                            <ul style={{ paddingLeft: 20, margin: 0 }}>
                                {overviewData.risk_warnings.map((w, i) => <li key={i}>{w}</li>)}
                            </ul>
                        }
                        type="warning"
                        showIcon
                        icon={<WarningOutlined />}
                    />
                )}
            </Col>
        </Row>
    );
};

export default OverviewTab;
