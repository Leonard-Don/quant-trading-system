/**
 * Risk-metrics tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `riskContent` memo block.
 */
import {
    Card,
    Row,
    Col,
    Typography,
    Alert,
    Statistic,
    Empty,
    Spin,
} from 'antd';
import { DashboardOutlined } from '@ant-design/icons';
import { DISPLAY_EMPTY } from '../../utils/marketAnalysisFormatters';

const { Text } = Typography;

const RiskTab = ({ loadingTab, errorTab, riskData }) => {
    if (loadingTab.risk && !riskData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.risk) {
        return <Alert message="错误" description={errorTab.risk} type="error" showIcon />;
    }
    if (!riskData) return <Empty description="暂无风险评估数据" />;

    const riskLevelText = { very_high: '极高', high: '高', medium: '中等', low: '低', very_low: '极低' };

    return (
        <Row gutter={[16, 16]}>
            <Col span={24}>
                <Alert
                    message={`风险等级: ${riskLevelText[riskData.risk_level] || riskData.risk_level}`}
                    description={riskData.risk_description}
                    type={riskData.risk_level === 'low' || riskData.risk_level === 'very_low' ? 'success' :
                        riskData.risk_level === 'medium' ? 'warning' : 'error'}
                    showIcon
                    icon={<DashboardOutlined />}
                />
            </Col>
            <Col xs={24} md={8}>
                <Card title="风险价值 (VaR)">
                    <Statistic
                        title="95% VaR (日度)"
                        value={riskData.var_95}
                        suffix="%"
                        valueStyle={{ color: riskData.var_95 < -5 ? '#ff4d4f' : '#faad14' }}
                    />
                    <Statistic
                        title="99% VaR (日度)"
                        value={riskData.var_99}
                        suffix="%"
                        style={{ marginTop: 16 }}
                        valueStyle={{ color: riskData.var_99 < -8 ? '#ff4d4f' : '#faad14' }}
                    />
                </Card>
            </Col>
            <Col xs={24} md={8}>
                <Card title="回撤与波动">
                    <Statistic
                        title="最大回撤"
                        value={riskData.max_drawdown}
                        suffix="%"
                        valueStyle={{ color: riskData.max_drawdown < -30 ? '#ff4d4f' : '#faad14' }}
                    />
                    <Statistic
                        title="年化波动率"
                        value={riskData.annual_volatility}
                        suffix="%"
                        style={{ marginTop: 16 }}
                    />
                </Card>
            </Col>
            <Col xs={24} md={8}>
                <Card title="风险调整收益">
                    <Statistic
                        title="夏普比率"
                        value={riskData.sharpe_ratio}
                        valueStyle={{ color: riskData.sharpe_ratio > 1 ? '#52c41a' : riskData.sharpe_ratio < 0 ? '#ff4d4f' : '#faad14' }}
                    />
                    <Statistic
                        title="索提诺比率"
                        value={riskData.sortino_ratio}
                        style={{ marginTop: 16 }}
                        valueStyle={{ color: riskData.sortino_ratio > 1 ? '#52c41a' : '#faad14' }}
                    />
                </Card>
            </Col>
            <Col xs={24} md={12}>
                <Card title="收益与Beta">
                    <Row gutter={16}>
                        <Col span={12}>
                            <Statistic
                                title="年化收益率"
                                value={riskData.annual_return}
                                suffix="%"
                                valueStyle={{ color: riskData.annual_return > 0 ? '#52c41a' : '#ff4d4f' }}
                            />
                        </Col>
                        <Col span={12}>
                            <Statistic title="Beta" value={riskData.beta} />
                        </Col>
                    </Row>
                </Card>
            </Col>
            <Col xs={24} md={12}>
                <Card title="最大回撤区间">
                    <Text>
                        从 {riskData.max_drawdown_period?.start || DISPLAY_EMPTY} 到 {riskData.max_drawdown_period?.end || DISPLAY_EMPTY}
                    </Text>
                    <div style={{ marginTop: 8 }}>
                        <Text type="secondary">分析数据点: {riskData.data_points ?? DISPLAY_EMPTY} 个</Text>
                    </div>
                </Card>
            </Col>
        </Row>
    );
};

export default RiskTab;
