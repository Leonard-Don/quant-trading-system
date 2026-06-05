/**
 * Pattern-recognition tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `patternContent` memo block.
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
    Empty,
    Spin,
} from 'antd';
import {
    RiseOutlined,
    FallOutlined,
} from '@ant-design/icons';
import {
    ComposedChart, ReferenceArea, Scatter,
    ResponsiveContainer,
    Tooltip as RechartsTooltip,
    XAxis,
    YAxis,
    CartesianGrid,
    Line,
} from 'recharts';

const { Text } = Typography;

const PatternTab = ({ loadingTab, errorTab, patternData, klinesData }) => {
    if (loadingTab.pattern && !patternData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.pattern) {
        return <Alert message="错误" description={errorTab.pattern} type="error" showIcon />;
    }
    if (!patternData) return <Empty description="暂无形态数据" />;

    const pattern_analysis = patternData.pattern_analysis || patternData;
    if (!pattern_analysis) return <Empty description="暂无形态数据" />;

    const klines = klinesData || [];
    const { candlestick_patterns, chart_patterns } = pattern_analysis;
    const patterns = chart_patterns || [];
    const candlestickPatterns = candlestick_patterns || [];

    // 辅助翻译映射
    const RELIABILITY_MAP = {
        'high': '高',
        'medium': '中',
        'low': '低',
        'very_high': '极高',
        'High': '高',
        'Medium': '中',
        'Low': '低',
        'Very High': '极高'
    };

    // 过滤掉不在当前K线范围内的形态
    const startDate = klines && klines.length > 0 ? new Date(klines[0].date) : new Date(0);

    const validPatterns = patterns.filter(p => {
        if (!p.points) return false;
        // 只要有一个点在范围内就显示
        return p.points.some(pt => new Date(pt.date) >= startDate);
    });

    const SIGNAL_MAP = {
        'bullish': '看涨',
        'bearish': '看跌',
        'bullish_reversal': '看涨反转',
        'bearish_reversal': '看跌反转',
        'bullish_continuation': '看涨持续',
        'bearish_continuation': '看跌持续',
        'consolidation': '整理',
        'reversal': '反转',
        'neutral': '中性',
    };

    const POINT_TYPE_MAP = {
        'peak1': '顶1', 'peak2': '顶2', 'peak': '顶部',
        'trough': '谷底', 'trough1': '谷1', 'trough2': '谷2',
        'neckline': '颈线', 'head': '头部',
        'left_shoulder': '左肩', 'right_shoulder': '右肩',
        'support': '支撑', 'resistance': '阻力',
        'breakout': '突破', 'bottom': '底部',
        'bottom1': '底1', 'bottom2': '底2',
        'top': '顶', 'start': '起点', 'end': '终点',
    };

    const translateSignal = (sig) => SIGNAL_MAP[sig?.toLowerCase?.()] || SIGNAL_MAP[sig] || sig;
    const translateReliability = (rel) => RELIABILITY_MAP[rel] || rel;
    const translatePointType = (type) => POINT_TYPE_MAP[type?.toLowerCase?.()] || POINT_TYPE_MAP[type] || type;

    // 将所有形态的点合并用于 Scatter 显示
    const patternMap = new Map();
    validPatterns.forEach(p => {
        (p.points || []).forEach(pt => {
            patternMap.set(pt.date, {
                ...pt,
                patternName: p.name,
                color: p.signal.includes('bullish') ? '#52c41a' : '#f5222d'
            });
        });
    });

    // 合并 pattern 数据到 klines 主数据
    const combinedData = (klines || []).map(k => ({
        ...k,
        patternPoint: patternMap.has(k.date) ? patternMap.get(k.date).price : null,
        patternMeta: patternMap.get(k.date)
    }));

    return (
        <Row gutter={[16, 16]}>
            <Col span={24}>
                <Card title="形态可视化" variant="borderless">
                    {klines && klines.length > 0 ? (
                        <div style={{ width: '100%', height: 400 }}>
                            <ResponsiveContainer>
                                <ComposedChart data={combinedData}>
                                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                                    <XAxis
                                        dataKey="date"
                                        minTickGap={30}
                                        tickFormatter={tick => tick.slice(5)}
                                    />
                                    <YAxis domain={['auto', 'auto']} />
                                    <RechartsTooltip
                                        labelFormatter={label => `日期: ${label}`}
                                        formatter={(value, name) => [value, name === 'close' ? '收盘价' : name]}
                                    />
                                    <Line
                                        data={combinedData}
                                        type="monotone"
                                        dataKey="close"
                                        stroke="#1890ff"
                                        dot={false}
                                        strokeWidth={2}
                                        name="close"
                                        isAnimationActive={false}
                                        connectNulls
                                    />

                                    {/* 绘制形态的关键点 */}
                                    <Scatter
                                        dataKey="patternPoint"
                                        fill="#8884d8"
                                        name="形态关键点"
                                        shape={(props) => {
                                            const { cx, cy, payload } = props;
                                            // payload is the data item (kline + patternMeta)
                                            if (!payload.patternMeta) return null;

                                            return (
                                                <g>
                                                    <circle cx={cx} cy={cy} r={6} fill={payload.patternMeta.color} stroke="#fff" strokeWidth={2} />
                                                    <text x={cx} y={cy - 10} textAnchor="middle" fill={payload.patternMeta.color} fontSize={10}>
                                                        {translatePointType(payload.patternMeta.type)}
                                                    </text>
                                                </g>
                                            );
                                        }}
                                    />

                                    {/* 可选：用参考区域高亮形态出现的区间 */}
                                    {validPatterns.map((p, idx) => {
                                        if (!p.points || p.points.length < 2) return null;
                                        const start = p.points[0].date;
                                        const end = p.points[p.points.length - 1].date;
                                        return (
                                            <ReferenceArea
                                                key={idx}
                                                x1={start}
                                                x2={end}
                                                strokeOpacity={0.3}
                                                fill={p.signal.includes('bullish') ? '#52c41a' : '#f5222d'}
                                                fillOpacity={0.1}
                                            />
                                        );
                                    })}
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <Empty description="暂无K线数据用于绘图" />
                    )}
                </Card>
            </Col>

            <Col span={24}>
                <Card title="识别到的图表形态" className="glass-card">
                    <List
                        itemLayout="horizontal"
                        dataSource={validPatterns}
                        renderItem={item => (
                            <List.Item>
                                <List.Item.Meta
                                    avatar={
                                        item.signal.includes('bullish') ?
                                            <RiseOutlined style={{ color: '#52c41a', fontSize: 24 }} /> :
                                            <FallOutlined style={{ color: '#f5222d', fontSize: 24 }} />
                                    }
                                    title={<Text strong>{item.name}</Text>}
                                    description={
                                        <Space direction="vertical" size={0}>
                                            <Text type="secondary">{item.description}</Text>
                                            <Space>
                                                <Tag color={item.signal.includes('bullish') ? 'success' : 'error'}>
                                                    {translateSignal(item.signal)}
                                                </Tag>
                                                <Tag>{translateReliability(item.reliability)} 可靠性</Tag>
                                            </Space>
                                        </Space>
                                    }
                                />
                            </List.Item>
                        )}
                        locale={{ emptyText: '近期未识别到明显图表形态' }}
                    />
                </Card>
            </Col>
            <Col span={24}>
                <Card title="识别到的K线形态">
                    <List
                        grid={{ gutter: 16, column: 3 }}
                        dataSource={candlestickPatterns.length > 0 ? candlestickPatterns : []}
                        renderItem={item => (
                            <List.Item>
                                <Card
                                    size="small"
                                    title={item.name}
                                    extra={<Tag color={item.signal.includes('bullish') ? 'red' : 'green'}>{translateSignal(item.signal)}</Tag>}
                                >
                                    <p>{item.description}</p>
                                    <Text type="secondary" style={{ fontSize: '12px' }}>可靠性: {translateReliability(item.reliability)}</Text>
                                    <br />
                                    <Text type="secondary" style={{ fontSize: '12px' }}>日期: {new Date(item.date).toLocaleDateString()}</Text>
                                </Card>
                            </List.Item>
                        )}
                        locale={{ emptyText: '近期未识别到K线形态' }}
                    />
                </Card>
            </Col>
        </Row>
    );
};

export default PatternTab;
