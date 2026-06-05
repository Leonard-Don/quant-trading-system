/**
 * Sentiment tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `sentimentContent` memo block.
 */
import {
    Card,
    Row,
    Col,
    Tag,
    Typography,
    Progress,
    Alert,
    Statistic,
    Empty,
    Divider,
    Spin,
} from 'antd';
import {
    WarningOutlined,
    ThunderboltOutlined,
    LineChartOutlined,
} from '@ant-design/icons';
import {
    ReferenceLine,
    ResponsiveContainer,
    Tooltip as RechartsTooltip,
    XAxis,
    YAxis,
    CartesianGrid,
    Line,
    LineChart,
} from 'recharts';

const { Title, Text } = Typography;

const SentimentTab = ({ loadingTab, errorTab, sentimentData, sentimentHistoryData }) => {
    if (loadingTab.sentiment && !sentimentData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.sentiment) {
        return <Alert message="错误" description={errorTab.sentiment} type="error" showIcon />;
    }
    if (!sentimentData) return <Empty description="暂无情绪数据" />;

    const sentiment_analysis = sentimentData.sentiment_analysis || sentimentData;
    if (!sentiment_analysis) return <Empty description="暂无情绪数据" />;

    const {
        fear_greed_index = 50,
        overall_sentiment = 'neutral',
        volatility_sentiment = {},
        risk_level = 'medium'
    } = sentiment_analysis || {};

    // Fear & Greed color
    const fgColor = fear_greed_index > 75 ? '#ff3030' : fear_greed_index < 25 ? '#00b578' : '#faad14';

    const VOLATILITY_MAP = {
        'stable': '稳定',
        'volatile': '波动',
        'very_volatile': '剧烈波动',
        'complacent': '低波动',
        'panic': '恐慌',
        'fear': '恐惧',
        'calm': '平静',
        'neutral': '中性'
    };

    const VOLATILITY_TREND_MAP = {
        'stable': '稳定',
        'increasing': '上升',
        'decreasing': '下降'
    };

    return (
        <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
                <Card title="恐慌与贪婪指数">
                    <div style={{ textAlign: 'center', marginBottom: 20 }}>
                        <Progress
                            percent={fear_greed_index}
                            showInfo={false}
                            strokeColor={{
                                '0%': '#00b578',
                                '50%': '#faad14',
                                '100%': '#ff3030',
                            }}
                        />
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
                            <Text type="success">极度恐慌 (0)</Text>
                            <Text type="danger">极度贪婪 (100)</Text>
                        </div>
                        <Title level={2} style={{ margin: '10px 0', color: fgColor }}>
                            {fear_greed_index}
                        </Title>
                        <Tag color={fgColor} style={{ fontSize: '14px' }}>
                            {overall_sentiment === 'fear' ? '恐慌' :
                                overall_sentiment === 'extreme_fear' ? '极度恐慌' :
                                    overall_sentiment === 'greed' ? '贪婪' :
                                        overall_sentiment === 'extreme_greed' ? '极度贪婪' : '中性'}
                        </Tag>
                    </div>
                </Card>
            </Col>
            <Col xs={24} md={12}>
                <Card title="风险概览">
                    <Row gutter={[16, 16]}>
                        <Col span={12}>
                            <Statistic
                                title="风险等级"
                                value={risk_level === 'low' ? '低' : risk_level === 'medium' ? '中' : risk_level === 'high' ? '高' : risk_level === 'very_high' ? '极高' : risk_level}
                                prefix={<WarningOutlined />}
                                valueStyle={{ color: risk_level === 'high' || risk_level === 'very_high' ? '#ff3030' : '#faad14' }}
                            />
                        </Col>
                        <Col span={12}>
                            <Statistic
                                title="波动率状态"
                                value={VOLATILITY_MAP[volatility_sentiment.sentiment] || volatility_sentiment.sentiment}
                                prefix={<ThunderboltOutlined />}
                            />
                        </Col>
                    </Row>
                    <Divider />
                    <div style={{ marginTop: 10 }}>
                        <Text>当前波动率: {volatility_sentiment.historical_volatility}%</Text>
                        <br />
                        <Text type="secondary">波动率趋势: {VOLATILITY_TREND_MAP[volatility_sentiment.volatility_trend] || volatility_sentiment.volatility_trend}</Text>
                    </div>
                </Card>
            </Col>

            {/* 历史情绪趋势 */}
            <Col span={24}>
                <Card
                    title={<><LineChartOutlined /> 历史情绪趋势 (30天)</>}
                    extra={loadingTab.sentimentHistory ? <Spin size="small" /> : null}
                >
                    {loadingTab.sentimentHistory && !sentimentHistoryData ? (
                        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                    ) : sentimentHistoryData && sentimentHistoryData.history ? (
                        <ResponsiveContainer width="100%" height={300}>
                            <LineChart data={sentimentHistoryData.history}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                                <YAxis domain={[0, 100]} />
                                <RechartsTooltip
                                    formatter={(value) => [`${value}`, '恐慌贪婪指数']}
                                    labelFormatter={(label) => `日期: ${label}`}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="fear_greed_index"
                                    stroke="#1890ff"
                                    strokeWidth={2}
                                    dot={{ r: 3 }}
                                    activeDot={{ r: 6 }}
                                />
                                {/* 参考线 */}
                                <ReferenceLine y={75} stroke="#ff3030" strokeDasharray="5 5" label={{ value: '贪婪', fill: '#ff3030', fontSize: 11 }} />
                                <ReferenceLine y={25} stroke="#00b578" strokeDasharray="5 5" label={{ value: '恐惧', fill: '#00b578', fontSize: 11 }} />
                            </LineChart>
                        </ResponsiveContainer>
                    ) : (
                        <Empty description="暂无历史情绪数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                </Card>
            </Col>
        </Row>
    );
};

export default SentimentTab;
