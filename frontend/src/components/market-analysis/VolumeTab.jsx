/**
 * Volume / price tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `volumeContent` memo block.
 */
import {
    Card,
    Row,
    Col,
    Tag,
    List,
    Typography,
    Progress,
    Alert,
    Statistic,
    Empty,
    Spin,
} from 'antd';
import {
    RiseOutlined,
    FallOutlined,
} from '@ant-design/icons';
import {
    ResponsiveContainer,
    Tooltip as RechartsTooltip,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    Cell,
} from 'recharts';
import { getCurrencySymbol } from '../../utils/strategyDefaults';
import {
    DISPLAY_EMPTY,
    formatDisplayNumber,
    formatDisplayPercent,
    normalizeVolumeTrend,
} from '../../utils/marketAnalysisFormatters';

const { Text } = Typography;

const VolumeTab = ({ loadingTab, errorTab, volumeData, symbol }) => {
    if (loadingTab.volume && !volumeData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.volume) {
        return <Alert message="错误" description={errorTab.volume} type="error" showIcon />;
    }
    if (!volumeData) return <Empty description="暂无量价数据" />;

    const volume_analysis = volumeData.volume_analysis || volumeData;
    if (!volume_analysis) return <Empty description="暂无量价数据" />;

    const {
        volume_trend: rawVolumeTrend = {},
        money_flow = { mfi: null, status: 'neutral' },
        volume_patterns = { patterns: [] },
        obv_analysis = {}
    } = volume_analysis || {};

    const volumeTrend = normalizeVolumeTrend(rawVolumeTrend);
    const mfiValue = money_flow.mfi === null || money_flow.mfi === undefined || Number.isNaN(Number(money_flow.mfi))
        ? null
        : Number(money_flow.mfi);
    const flowStatus = money_flow.status || 'neutral';
    const mfiColor = mfiValue === null ? '#94a3b8' : (mfiValue > 80 ? '#ff3030' : mfiValue < 20 ? '#00b578' : '#1890ff');

    const VOLUME_TREND_MAP = {
        'shrinking': '缩量',
        'expanding': '放量',
        'stable': '平稳',
        'explosive': '爆量',
        'increasing': '放量',
        'normal': '正常',
        'extremely_low': '地量',
        'extremely_high': '天量'
    };

    return (
        <Row gutter={[16, 16]}>
            <Col xs={24} md={8}>
                <Card title="量能趋势">
                    <Statistic
                        title="当前成交量趋势"
                        value={VOLUME_TREND_MAP[volumeTrend.trend] || volumeTrend.trend || '数据不足'}
                        valueStyle={{ color: volumeTrend.direction === 'expanding' ? '#ff3030' : '#00b578' }}
                        prefix={volumeTrend.direction === 'expanding' ? <RiseOutlined /> : <FallOutlined />}
                    />
                    <div style={{ marginTop: 10 }}>
                        <Text type="secondary">相对20日均量: </Text>
                        <Text strong>{formatDisplayNumber(volumeTrend.volume_ratio, 2, 'x')}</Text>
                    </div>
                </Card>
            </Col>

            {/* 筹码分布 */}
            {volume_analysis.vpvr_analysis && (
                <Col xs={24} md={24}>
                    <Card title="筹码分布 (VPVR)" variant="borderless" className="analysis-card">
                        <Row gutter={24}>
                            <Col span={6}>
                                <Statistic title="控制点 (POC)" value={volume_analysis.vpvr_analysis.poc} prefix={getCurrencySymbol(symbol)} />
                                <div style={{ marginTop: 8 }}>
                                    <Tag color="gold">成交密集区</Tag>
                                </div>
                            </Col>
                            <Col span={6}>
                                <Statistic title="价值区域上沿 (VAH)" value={volume_analysis.vpvr_analysis.vah} prefix={getCurrencySymbol(symbol)} />
                            </Col>
                            <Col span={6}>
                                <Statistic title="价值区域下沿 (VAL)" value={volume_analysis.vpvr_analysis.val} prefix={getCurrencySymbol(symbol)} />
                            </Col>
                            <Col span={6}>
                                <Statistic title="总成交量" value={volume_analysis.vpvr_analysis.total_volume} formatter={(v) => new Intl.NumberFormat('en-US', { notation: "compact" }).format(v)} />
                            </Col>
                        </Row>
                        <div style={{ height: 250, marginTop: 24 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={volume_analysis.vpvr_analysis.profile} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                    <XAxis dataKey="price_start" tickFormatter={(val) => val.toFixed(0)} />
                                    <YAxis hide />
                                    <RechartsTooltip
                                        formatter={(value) => new Intl.NumberFormat('en-US', { notation: "compact" }).format(value)}
                                        labelFormatter={(label) => `价格: ${label}`}
                                    />
                                    <Bar dataKey="volume" fill="#8884d8" barSize={20}>
                                        {
                                            volume_analysis.vpvr_analysis.profile.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={entry.is_poc ? '#faad14' : (entry.in_value_area ? '#1890ff' : '#e6f7ff')} />
                                            ))
                                        }
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </Card>
                </Col>
            )}
            <Col xs={24} md={8}>
                <Card title="资金流向 (MFI)">
                    <div style={{ textAlign: 'center' }}>
                        <Progress
                            type="circle"
                            percent={mfiValue ?? 0}
                            format={() => (mfiValue === null ? DISPLAY_EMPTY : `${mfiValue}`)}
                            strokeColor={mfiColor}
                            size={120}
                        />
                        <div style={{ marginTop: 10 }}>
                            <Tag color={flowStatus === 'strong_inflow' ? 'red' : flowStatus.includes('outflow') ? 'green' : 'default'}>
                                {flowStatus === 'strong_inflow' ? '强力流入' :
                                    flowStatus === 'inflow' ? '资金流入' :
                                        flowStatus === 'strong_outflow' ? '强力流出' :
                                            flowStatus === 'outflow' ? '资金流出' : '平衡'}
                            </Tag>
                        </div>
                    </div>
                </Card>
            </Col>
            <Col xs={24} md={8}>
                <Card title="能量潮 (OBV)">
                    <Statistic
                        title="OBV 趋势"
                        value={obv_analysis.obv_trend === 'bullish' ? '看涨' : obv_analysis.obv_trend === 'bearish' ? '看跌' : '中性'}
                        valueStyle={{ color: obv_analysis.obv_trend === 'bullish' ? '#ff3030' : '#00b578' }}
                    />
                    <div style={{ marginTop: 10 }}>
                        <Text>20日变化率: </Text>
                        <Text type={obv_analysis.obv_change_20d > 0 ? 'danger' : 'success'}>
                            {formatDisplayPercent(obv_analysis.obv_change_20d)}
                        </Text>
                    </div>
                </Card>
            </Col>
            <Col span={24}>
                <Card title="量价形态">
                    <List
                        grid={{ gutter: 16, column: 2 }}
                        dataSource={volume_patterns.patterns}
                        renderItem={item => (
                            <List.Item>
                                <Alert
                                    message={item.description}
                                    type={item.signal === 'bullish' || item.signal === 'potential_bottom' ? 'success' : 'warning'}
                                    showIcon
                                />
                            </List.Item>
                        )}
                        locale={{ emptyText: '未识别到明显量价形态' }}
                    />
                </Card>
            </Col>
        </Row>
    );
};

export default VolumeTab;
