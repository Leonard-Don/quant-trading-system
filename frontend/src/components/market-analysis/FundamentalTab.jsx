/**
 * Fundamental-analysis tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `fundamentalContent` memo block.
 */
import {
    Card,
    Row,
    Col,
    Tag,
    Typography,
    Alert,
    Statistic,
    Empty,
    Spin,
} from 'antd';
import {
    RiseOutlined,
    FallOutlined,
    SolutionOutlined,
} from '@ant-design/icons';
import { getCurrencySymbol } from '../../utils/strategyDefaults';
import {
    DISPLAY_EMPTY,
    formatDisplayNumber,
    formatDisplayPercent,
} from '../../utils/marketAnalysisFormatters';

const { Text } = Typography;

const FundamentalTab = ({ loadingTab, errorTab, fundamentalData, symbol }) => {
    if (loadingTab.fundamental && !fundamentalData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.fundamental) {
        return <Alert message="错误" description={errorTab.fundamental} type="error" showIcon />;
    }
    if (!fundamentalData) return <Empty description="暂无基本面数据" />;

    const fundamental_analysis = fundamentalData.fundamental_analysis || fundamentalData;
    if (!fundamental_analysis) return <Empty description="暂无基本面数据" />;

    const { metrics, valuation, financial_health, growth, summary } = fundamental_analysis;

    const formatLargeNumber = (num) => {
        if (!num) return DISPLAY_EMPTY;
        if (num > 1e12) return (num / 1e12).toFixed(2) + '万亿';
        if (num > 1e8) return (num / 1e8).toFixed(2) + '亿';
        return num.toLocaleString();
    };

    const FUNDAMENTAL_STATUS_MAP = {
        'fair_value': '合理估值', 'undervalued': '低估', 'overvalued': '高估',
        'stable': '稳定', 'moderate': '适中', 'strong': '强劲', 'weak': '弱',
        'healthy': '健康', 'unhealthy': '不健康',
        'high_growth': '高增长', 'low_growth': '低增长', 'negative_growth': '负增长',
        'good': '良好', 'poor': '较差', 'excellent': '优秀',
    };

    const ANALYST_RATING_MAP = {
        'strong_buy': '强力买入', 'buy': '买入', 'hold': '持有',
        'sell': '卖出', 'strong_sell': '强力卖出',
        'outperform': '跑赢大盘', 'underperform': '跑输大盘',
    };

    const translateStatus = (s) => FUNDAMENTAL_STATUS_MAP[s?.toLowerCase?.()] || s;
    const translateRating = (r) => ANALYST_RATING_MAP[r?.toLowerCase?.()?.replace(/\s+/g, '_')] || r;

    const renderScore = (item) => {
        if (!item) return null;
        let color = '#faad14';
        if (item.score >= 70) color = '#52c41a';
        if (item.score <= 30) color = '#ff4d4f';
        return <Tag color={color} style={{ marginLeft: 8 }}>{translateStatus(item.status)}</Tag>;
    };

    return (
        <Row gutter={[16, 16]}>
            <Col span={24}>
                <Alert
                    message="基本面概览"
                    description={summary}
                    type="info"
                    showIcon
                    icon={<SolutionOutlined />}
                    style={{ marginBottom: 16 }}
                />
            </Col>

            <Col xs={24} md={8}>
                <Card title="估值指标" extra={renderScore(valuation)}>
                    <Statistic title="市盈率 (PE)" value={formatDisplayNumber(metrics.pe_ratio)} suffix={metrics.pe_ratio !== null && metrics.pe_ratio !== undefined ? 'x' : ''} />
                    <div style={{ marginTop: 16 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">PEG:</Text>
                            <Text>{formatDisplayNumber(metrics.peg_ratio)}</Text>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                            <Text type="secondary">市净率 (PB):</Text>
                            <Text>{formatDisplayNumber(metrics.price_to_book)}</Text>
                        </div>
                    </div>
                </Card>
            </Col>

            <Col xs={24} md={8}>
                <Card title="财务健康" extra={renderScore(financial_health)}>
                    <Statistic title="流动比率" value={formatDisplayNumber(metrics.current_ratio)} />
                    <div style={{ marginTop: 16 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">负债权益比:</Text>
                            <Text>{formatDisplayPercent(metrics.debt_to_equity)}</Text>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                            <Text type="secondary">利润率:</Text>
                            <Text>{formatDisplayPercent(metrics.profit_margin, 2, true)}</Text>
                        </div>
                    </div>
                </Card>
            </Col>

            <Col xs={24} md={8}>
                <Card title="增长能力" extra={renderScore(growth)}>
                    <Statistic
                        title="营收增长"
                        value={metrics.revenue_growth !== null && metrics.revenue_growth !== undefined ? Number((metrics.revenue_growth * 100).toFixed(2)) : undefined}
                        precision={2}
                        valueStyle={{ color: metrics.revenue_growth > 0 ? '#3f8600' : '#cf1322' }}
                        prefix={metrics.revenue_growth > 0 ? <RiseOutlined /> : <FallOutlined />}
                        suffix="%"
                    />
                    <div style={{ marginTop: 16 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <Text type="secondary">盈利增长:</Text>
                            <Text type={metrics.earnings_growth > 0 ? 'success' : 'danger'}>
                                {formatDisplayPercent(metrics.earnings_growth, 2, true)}
                            </Text>
                        </div>
                    </div>
                </Card>
            </Col>

            <Col span={24}>
                <Card title="公司信息">
                    <Row gutter={[24, 24]}>
                        <Col span={8}>
                            <Statistic title="总市值" value={formatLargeNumber(metrics.market_cap)} />
                        </Col>
                        <Col span={8}>
                            <div className="ant-statistic-title">所属板块</div>
                            <div className="ant-statistic-content" style={{ fontSize: 20 }}>{metrics.sector || DISPLAY_EMPTY}</div>
                        </Col>
                        <Col span={8}>
                            <div className="ant-statistic-title">行业</div>
                            <div className="ant-statistic-content" style={{ fontSize: 20 }}>{metrics.industry || DISPLAY_EMPTY}</div>
                        </Col>
                        <Col span={8}>
                            <div className="ant-statistic-title">分析师评级</div>
                            <div className="ant-statistic-content" style={{ fontSize: 20 }}>
                                {metrics.analyst_rating ? translateRating(metrics.analyst_rating) : DISPLAY_EMPTY}
                            </div>
                        </Col>
                        <Col span={8}>
                            <Statistic title="目标价" value={metrics.target_price} prefix={getCurrencySymbol(symbol)} precision={2} />
                        </Col>
                        <Col span={8}>
                            <Statistic title="52周最高" value={metrics['52w_high']} prefix={getCurrencySymbol(symbol)} precision={2} />
                        </Col>
                    </Row>
                </Card>
            </Col>
        </Row>
    );
};

export default FundamentalTab;
