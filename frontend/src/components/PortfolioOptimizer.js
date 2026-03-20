import React, { useState } from 'react';
import {
    Card,
    Select,
    Button,
    Row,
    Col,
    Typography,
    Table,
    Space,
    Alert,
    Statistic,
    InputNumber
} from 'antd';
import {
    PieChart,
    Pie,
    Cell,
    Tooltip as RechartsTooltip,
    Legend,
    ResponsiveContainer,
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    ReferenceDot
} from 'recharts';
import { ExperimentOutlined, PieChartOutlined, DotChartOutlined } from '@ant-design/icons';
import { optimizePortfolio } from '../services/api';

const { Text } = Typography;
const { Option } = Select;

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658'];
const PERIOD_LABELS = {
    '3m': '近 3 个月',
    '6m': '近 6 个月',
    '1y': '近 1 年',
};
const OBJECTIVE_LABELS = {
    max_sharpe: '最大夏普比率',
    min_volatility: '最小波动率',
};

const PortfolioOptimizer = () => {
    const [selectedSymbols, setSelectedSymbols] = useState(['AAPL', 'MSFT', 'GOOGL', 'AMZN']);
    const [period, setPeriod] = useState('1y');
    const [objective, setObjective] = useState('max_sharpe');
    const [allocationCapital, setAllocationCapital] = useState(10000);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const handleOptimize = async () => {
        if (selectedSymbols.length < 2) {
            setError("至少选择两个资产进行组合");
            return;
        }
        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const data = await optimizePortfolio(selectedSymbols, period, objective);
            setResult(data);
        } catch (err) {
            console.error(err);
            setError("优化计算失败: " + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    // Format data for charts
    const pieData = result ? Object.entries(result.optimal_portfolio.weights)
        .filter(([_, weight]) => weight > 0.001) // Filter out negligible weights
        .map(([symbol, weight]) => ({
            name: symbol,
            value: weight
        })) : [];

    const scatterData = result ? result.efficient_frontier : [];

    const columns = [
        {
            title: '资产',
            dataIndex: 'asset',
            key: 'asset',
            render: (text) => <Text strong>{text}</Text>
        },
        {
            title: '推荐权重',
            dataIndex: 'weight',
            key: 'weight',
            render: (value) => `${(value * 100).toFixed(2)}%`,
            sorter: (a, b) => a.weight - b.weight
        },
        {
            title: `金额分配 (按 $${allocationCapital.toLocaleString()})`,
            key: 'amount',
            render: (_, record) => `$${(record.weight * allocationCapital).toLocaleString()}`
        }
    ];

    const tableData = result ? Object.entries(result.optimal_portfolio.weights).map(([asset, weight]) => ({
        key: asset,
        asset,
        weight
    })) : [];

    return (
        <div className="workspace-tab-view">
            <div className="workspace-section workspace-section--accent">
                <div className="workspace-section__header">
                    <div>
                        <div className="workspace-section__title">组合优化实验台</div>
                        <div className="workspace-section__description">基于马科维茨均值方差框架，在统一工作台里查看输入、最优权重和有效前沿。</div>
                    </div>
                </div>
                <div className="summary-strip summary-strip--compact">
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">资产池</span>
                        <span className="summary-strip__value">{selectedSymbols.length} 个</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">周期</span>
                        <span className="summary-strip__value">{PERIOD_LABELS[period] || period}</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">目标</span>
                        <span className="summary-strip__value">{OBJECTIVE_LABELS[objective] || objective}</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">参考资金</span>
                        <span className="summary-strip__value">{`$${allocationCapital.toLocaleString()}`}</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">状态</span>
                        <span className="summary-strip__value">{loading ? '计算中' : (result ? '结果已生成' : '待运行')}</span>
                    </div>
                </div>
            </div>

            <Card className="workspace-panel" style={{ marginBottom: 24 }}>
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    <Row gutter={16}>
                        <Col span={12}>
                            <Text strong>选择资产池 (输入代码回车添加)</Text>
                            <Select
                                mode="tags"
                                style={{ width: '100%', marginTop: 8 }}
                                placeholder="输入股票代码 例如: AAPL, TSLA"
                                value={selectedSymbols}
                                onChange={setSelectedSymbols}
                                tokenSeparators={[',', ' ']}
                            >
                                {['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'AMD'].map(s => (
                                    <Option key={s} value={s}>{s}</Option>
                                ))}
                            </Select>
                        </Col>
                        <Col span={6}>
                            <Text strong>时间周期</Text>
                            <Select value={period} onChange={setPeriod} style={{ width: '100%', marginTop: 8 }}>
                                <Option value="3m">近3个月</Option>
                                <Option value="6m">近6个月</Option>
                                <Option value="1y">近1年</Option>
                            </Select>
                        </Col>
                        <Col span={6}>
                            <Text strong>优化目标</Text>
                            <Select value={objective} onChange={setObjective} style={{ width: '100%', marginTop: 8 }}>
                                <Option value="max_sharpe">最大夏普比率</Option>
                                <Option value="min_volatility">最小波动率</Option>
                            </Select>
                        </Col>
                        <Col span={6}>
                            <Text strong>参考资金</Text>
                            <InputNumber
                                value={allocationCapital}
                                min={1000}
                                step={1000}
                                precision={0}
                                style={{ width: '100%', marginTop: 8 }}
                                onChange={(value) => setAllocationCapital(value || 10000)}
                            />
                        </Col>
                    </Row>
                    <Button type="primary" size="large" onClick={handleOptimize} loading={loading} block>
                        开始计算最优配置
                    </Button>
                </Space>
            </Card>

            {error && <Alert message="错误" description={error} type="error" showIcon style={{ marginBottom: 24 }} />}

            {result && (
                <Row gutter={[24, 24]}>
                    <Col span={8}>
                        <Card title="最优组合指标" variant="borderless" className="workspace-panel">
                            <Row gutter={[16, 24]}>
                                <Col span={24}>
                                    <Statistic title="预期年化收益率" value={result.optimal_portfolio.return} suffix="%" valueStyle={{ color: '#3f8600' }} />
                                </Col>
                                <Col span={24}>
                                    <Statistic title="预期年化波动率" value={result.optimal_portfolio.volatility} suffix="%" />
                                </Col>
                                <Col span={24}>
                                    <Statistic title="夏普比率" value={result.optimal_portfolio.sharpe_ratio} prefix={<ExperimentOutlined />} />
                                </Col>
                            </Row>
                        </Card>
                    </Col>

                    <Col span={16}>
                        <Card title={<><PieChartOutlined /> 推荐仓位分配</>} variant="borderless" className="workspace-panel workspace-chart-card">
                            <Row>
                                <Col span={12}>
                                    <div className="pie-chart-container" style={{ width: '100%', height: 300 }}>
                                        <ResponsiveContainer width="100%" height={300} minWidth={320} minHeight={300}>
                                            <PieChart margin={{ top: 10, right: 10, left: 10, bottom: 30 }}>
                                                <Pie
                                                    data={pieData}
                                                    cx="50%"
                                                    cy="45%"
                                                    innerRadius={50}
                                                    outerRadius={80}
                                                    fill="#8884d8"
                                                    paddingAngle={5}
                                                    dataKey="value"
                                                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                                                    labelLine={{ stroke: 'var(--text-muted)', strokeWidth: 1 }}
                                                >
                                                    {pieData.map((entry, index) => (
                                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                                    ))}
                                                </Pie>
                                                <RechartsTooltip />
                                                <Legend verticalAlign="bottom" height={30} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    </div>
                                </Col>
                                <Col span={12}>
                                    <Table
                                        dataSource={tableData}
                                        columns={columns}
                                        pagination={false}
                                        size="small"
                                    />
                                </Col>
                            </Row>
                        </Card>
                    </Col>

                    <Col span={24}>
                        <Card title={<><DotChartOutlined /> 有效前沿</>} variant="borderless" className="workspace-panel workspace-chart-card">
                            <div style={{ height: 400 }}>
                                <ResponsiveContainer width="100%" height={400} minWidth={320} minHeight={400}>
                                    <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                                        <CartesianGrid />
                                        <XAxis type="number" dataKey="volatility" name="波动率" unit="%" label={{ value: '风险 (波动率 %)', position: 'insideBottom', offset: -10 }} />
                                        <YAxis type="number" dataKey="return" name="收益率" unit="%" label={{ value: '预期收益率 %', angle: -90, position: 'insideLeft' }} />
                                        <RechartsTooltip cursor={{ strokeDasharray: '3 3' }} />
                                        <Scatter name="随机组合" data={scatterData} fill="#8884d8" fillOpacity={0.6} />
                                        <ReferenceDot
                                            x={result.optimal_portfolio.volatility}
                                            y={result.optimal_portfolio.return}
                                            r={6}
                                            fill="red"
                                            stroke="none"
                                            ifOverflow="extendDomain"
                                        />
                                        <Legend />
                                    </ScatterChart>
                                </ResponsiveContainer>
                                <div style={{ textAlign: 'center', marginTop: 10 }}>
                                    <Text type="secondary">红点表示当前计算出的最优组合位置</Text>
                                </div>
                            </div>
                        </Card>
                    </Col>
                </Row>
            )}
        </div>
    );
};

export default PortfolioOptimizer;
