/**
 * Trend-analysis tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `trendContent` memo block.
 */
import {
    Card,
    Row,
    Col,
    Tag,
    List,
    Typography,
    Alert,
    Space,
    Table,
    Empty,
    Spin,
    Tooltip,
} from 'antd';
import {
    RiseOutlined,
    FallOutlined,
    InfoCircleOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

const TrendTab = ({ loadingTab, errorTab, trendData }) => {
    if (loadingTab.trend && !trendData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.trend) {
        return <Alert message="错误" description={errorTab.trend} type="error" showIcon />;
    }
    if (!trendData) return <Empty description="暂无趋势数据" />;

    const trend_analysis = trendData.trend_analysis || trendData;
    const { multi_timeframe = {}, support_levels = [], resistance_levels = [] } = trend_analysis || {};

    const columns = [
        { title: '周期', dataIndex: 'period', key: 'period' },
        {
            title: '趋势',
            dataIndex: 'trend',
            key: 'trend',
            render: (text) => (
                <Tag color={text === '上涨' ? 'red' : 'green'}>
                    {text === '上涨' ? <RiseOutlined /> : <FallOutlined />} {text}
                </Tag>
            )
        },
        {
            title: '涨跌幅',
            dataIndex: 'change_percent',
            key: 'change_percent',
            render: (val) => (
                <Text type={val > 0 ? 'danger' : 'success'}>
                    {val > 0 ? '+' : ''}{val}%
                </Text>
            )
        }
    ];

    const timeFrameData = Object.values(multi_timeframe || {});

    return (
        <Row gutter={[16, 16]}>
            <Col span={24}>
                <Card title="多周期趋势">
                    <Table
                        dataSource={timeFrameData}
                        columns={columns}
                        pagination={false}
                        rowKey="period"
                        size="small"
                    />
                </Card>
            </Col>

            {/* 斐波那契回撤 */}
            {trend_analysis.fibonacci_levels && (
                <Col xs={24} md={24}>
                    <Card
                        title={
                            <Space>
                                斐波那契回撤
                                <Tooltip title={
                                    <div>
                                        <p>斐波那契回撤用于识别潜在的支撑位和阻力位。</p>
                                        <p>• <b>0.236/0.382</b>: 强势回调，趋势可能延续。</p>
                                        <p>• <b>0.5/0.618</b>: 常见回调位，是关键的支撑/阻力区域。</p>
                                        <p>• <b>0.786</b>: 深度回调，趋势可能反转。</p>
                                    </div>
                                }>
                                    <InfoCircleOutlined style={{ color: '#1890ff', cursor: 'pointer' }} />
                                </Tooltip>
                            </Space>
                        }
                        variant="borderless"
                        className="analysis-card"
                    >
                        <Row gutter={24}>
                            <Col span={8}>
                                <div style={{ marginBottom: 16 }}>
                                    <Tag color="blue" style={{ fontSize: '14px', padding: '5px' }}>
                                        当前: {trend_analysis.fibonacci_levels.current_position}
                                    </Tag>
                                    <div style={{ fontSize: '12px', color: '#666', marginTop: 12, lineHeight: '1.5' }}>
                                        基于近期高点 {trend_analysis.fibonacci_levels.high_price?.toFixed(2)} 和
                                        低点 {trend_analysis.fibonacci_levels.low_price?.toFixed(2)} 计算。
                                        <br />
                                        价格通常会在这些比率位置遇到支撑或阻力。
                                    </div>
                                </div>
                            </Col>
                            <Col span={16}>
                                <List
                                    grid={{ gutter: 16, column: 3 }}
                                    dataSource={Object.entries(trend_analysis.fibonacci_levels.levels).sort((a, b) => parseFloat(b[1]) - parseFloat(a[1]))}
                                    renderItem={([level, price]) => (
                                        <List.Item>
                                            <Card size="small" styles={{ body: { padding: '8px', background: trend_analysis.fibonacci_levels.nearest_level === level ? '#e6f7ff' : 'transparent' } }}>
                                                <div style={{ fontSize: '12px', color: '#888' }}>
                                                    Fib {level}
                                                    {level === '0.618' && <span style={{ color: '#faad14', marginLeft: 4 }}>(黄金分割)</span>}
                                                    {level === '0.5' && <span style={{ color: '#52c41a', marginLeft: 4 }}>(中轴)</span>}
                                                </div>
                                                <div style={{
                                                    fontWeight: trend_analysis.fibonacci_levels.nearest_level === level ? 'bold' : 'normal',
                                                    color: trend_analysis.fibonacci_levels.nearest_level === level ? '#1890ff' : 'inherit',
                                                    fontSize: '16px'
                                                }}>
                                                    {price.toFixed(2)}
                                                </div>
                                            </Card>
                                        </List.Item>
                                    )}
                                />
                            </Col>
                        </Row>
                    </Card>
                </Col>
            )}

            <Col span={12}>
                <Card title="支撑位">
                    <List
                        dataSource={support_levels}
                        renderItem={level => (
                            <List.Item>
                                <Text type="success" strong>{level}</Text>
                            </List.Item>
                        )}
                    />
                </Card>
            </Col>
            <Col span={12}>
                <Card title="阻力位">
                    <List
                        dataSource={resistance_levels}
                        renderItem={level => (
                            <List.Item>
                                <Text type="danger" strong>{level}</Text>
                            </List.Item>
                        )}
                    />
                </Card>
            </Col>
        </Row>
    );
};

export default TrendTab;
