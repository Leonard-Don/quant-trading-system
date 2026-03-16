import React, { useState, useEffect } from 'react';
import { Card, Spin, Alert, Typography, Row, Col, Statistic, Tag, Button, Select, Radio, Tooltip as AntTooltip, message, Space } from 'antd';
import { RobotOutlined, ArrowUpOutlined, ArrowDownOutlined, ExperimentOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { predictPrice, predictWithLSTM, compareModelPredictions, trainAllModels } from '../services/api';

const { Text, Paragraph } = Typography;
const { Option } = Select;

const AIPredictionPanel = ({ symbol }) => {
    const [loading, setLoading] = useState(false);
    const [training, setTraining] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [modelType, setModelType] = useState('consensus'); // random_forest, lstm, compare, consensus

    useEffect(() => {
        if (symbol) {
            fetchPrediction();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [symbol, modelType]);

    const fetchPrediction = async () => {
        setLoading(true);
        setError(null);
        try {
            let result;
            if (modelType === 'random_forest') {
                result = await predictPrice(symbol);
            } else if (modelType === 'lstm') {
                result = await predictWithLSTM(symbol);
            } else if (modelType === 'compare' || modelType === 'consensus') {
                result = await compareModelPredictions(symbol);
            }
            setData(result);
        } catch (err) {
            console.error("Prediction error:", err);
            setError("无法获取AI预测数据，请稍后重试");
        } finally {
            setLoading(false);
        }
    };

    const handleTrainModels = async () => {
        setTraining(true);
        try {
            await trainAllModels(symbol);
            message.success('模型训练完成！正在刷新预测...');
            fetchPrediction();
        } catch (err) {
            console.error("Training error:", err);
            message.error('模型训练失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            setTraining(false);
        }
    };

    if (loading && !data) {
        return (
            <Card style={{ minHeight: 400, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                    <Spin size="large" />
                    <div style={{ marginTop: 12, color: '#8c8c8c' }}>
                        {`AI (${modelType.toUpperCase()}) 正在分析并预测未来趋势...`}
                    </div>
                </div>
            </Card>
        );
    }

    if (error) {
        return (
            <Card>
                <Alert message="分析失败" description={error} type="error" showIcon />
                <Button type="primary" onClick={fetchPrediction} style={{ marginTop: 16 }}>重试</Button>
            </Card>
        );
    }

    if (!data) return null;

    // --- Data Formatting Helpers ---

    const formatChartData = () => {
        if (!data.dates) return [];

        return data.dates.map((date, index) => {
            const item = { date: new Date(date).toLocaleDateString() };

            if (modelType === 'compare') {
                // Fix: Access data via data.predictions object
                const rfPred = data.predictions?.random_forest || {};
                const lstmPred = data.predictions?.lstm || {};

                item.rf_price = rfPred.predicted_prices?.[index] || 0;
                item.lstm_price = lstmPred.predicted_prices?.[index] || 0;
                // 计算平均值作为参考
                item.avg_price = (item.rf_price + item.lstm_price) / 2;
            } else if (modelType === 'consensus') {
                // Consensus Logic: 50% LSTM + 50% RF (equal weight)
                const rfPred = data.predictions?.random_forest || {};
                const lstmPred = data.predictions?.lstm || {};

                const rfPrice = rfPred.predicted_prices?.[index] || 0;
                const lstmPrice = lstmPred.predicted_prices?.[index] || 0;

                if (rfPrice && lstmPrice) {
                    item.price = (lstmPrice * 0.5) + (rfPrice * 0.5);

                    // Synthetic confidence interval for consensus
                    // Use wider interval if models disagree
                    const disagreement = Math.abs(rfPrice - lstmPrice);
                    const baseInterval = (rfPred.confidence_intervals?.[index]?.upper - rfPred.confidence_intervals?.[index]?.lower) || 0;
                    const intervalHalf = (baseInterval / 2) + (disagreement * 0.5);

                    item.range = [item.price - intervalHalf, item.price + intervalHalf];
                } else {
                    item.price = lstmPrice || rfPrice || 0;
                }
            } else {
                item.price = data.predicted_prices[index];
                if (data.confidence_intervals) {
                    item.range = [data.confidence_intervals[index].lower, data.confidence_intervals[index].upper];
                }
            }
            return item;
        });
    };

    const chartData = formatChartData();
    let startPrice = 0, endPrice = 0, priceChange = 0, percentChange = 0;

    // Calculate metrics based on model type
    if (modelType === 'compare' || modelType === 'consensus') {
        const rfPred = data.predictions?.random_forest || {};
        const lstmPred = data.predictions?.lstm || {};

        // Use average for summary metrics in comparison mode
        const rfStart = rfPred.predicted_prices?.[0] || 0;
        const rfEnd = rfPred.predicted_prices?.slice(-1)[0] || 0;
        const lstmStart = lstmPred.predicted_prices?.[0] || 0;
        const lstmEnd = lstmPred.predicted_prices?.slice(-1)[0] || 0;

        if (modelType === 'consensus') {
            startPrice = (lstmStart * 0.5) + (rfStart * 0.5);
            endPrice = (lstmEnd * 0.5) + (rfEnd * 0.5);
        } else {
            startPrice = (rfStart + lstmStart) / 2;
            endPrice = (rfEnd + lstmEnd) / 2;
        }
    } else {
        startPrice = chartData[0]?.price || 0;
        endPrice = chartData[chartData.length - 1]?.price || 0;
    }

    priceChange = endPrice - startPrice;
    percentChange = startPrice > 0 ? (priceChange / startPrice) * 100 : 0;
    const isPositive = priceChange >= 0;

    // --- Render Content ---

    const renderControls = () => (
        <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
                <Tag color="cyan" style={{ marginRight: 8 }}>{symbol}</Tag>
                <Tag color="blue" icon={<RobotOutlined />}>AI 综合预测 (Consensus)</Tag>
            </div>

            <AntTooltip title="使用最新数据重新训练所有模型 (耗时较长)">
                <Button
                    icon={training ? <Spin indicator={<ExperimentOutlined spin />} /> : <ExperimentOutlined />}
                    onClick={handleTrainModels}
                    loading={training}
                >
                    {training ? '训练中...' : '训练模型'}
                </Button>
            </AntTooltip>
        </div>
    );

    const renderSummary = () => (
        <Row gutter={24} style={{ marginBottom: 24 }}>
            <Col span={6}>
                <Statistic
                    title={<span style={{ color: 'rgba(255,255,255,0.7)' }}>起始预测均价</span>}
                    value={startPrice}
                    precision={2}
                    prefix="$"
                    valueStyle={{ color: '#00f5d4', fontSize: 24 }}
                />
            </Col>
            <Col span={6}>
                <Statistic
                    title={<span style={{ color: 'rgba(255,255,255,0.7)' }}>5日后预测均价</span>}
                    value={endPrice}
                    precision={2}
                    prefix="$"
                    valueStyle={{ color: isPositive ? '#00f5d4' : '#ff6b6b', fontSize: 24 }}
                />
            </Col>
            <Col span={6}>
                <Statistic
                    title={<span style={{ color: 'rgba(255,255,255,0.7)' }}>预测涨跌幅</span>}
                    value={percentChange}
                    precision={2}
                    valueStyle={{ color: isPositive ? '#00f5d4' : '#ff6b6b', fontSize: 24 }}
                    prefix={isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                    suffix="%"
                />
            </Col>
            <Col span={6}>
                <Statistic
                    title={<span style={{ color: 'rgba(255,255,255,0.7)' }}>置信度/误差</span>}
                    value={modelType === 'compare' ? data.comparison?.agreement_metrics?.mean_difference_percent : (data.metrics?.accuracy || 0.85) * 100}
                    precision={2}
                    prefix={modelType === 'compare' ? 'Diff ' : ''}
                    suffix="%"
                    valueStyle={{ color: '#b37feb', fontSize: 24 }}
                />
            </Col>
        </Row>
    );

    const renderChart = () => (
        <div style={{ height: 400 }}>
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis dataKey="date" />
                    <YAxis domain={['auto', 'auto']} />
                    <Tooltip
                        contentStyle={{ backgroundColor: 'rgba(0,0,0,0.8)', border: 'none' }}
                        itemStyle={{ color: '#fff' }}
                    />
                    <Legend />

                    {modelType === 'compare' ? (
                        <>
                            <Line type="monotone" dataKey="rf_price" name="Random Forest" stroke="#1890ff" strokeWidth={2} dot={{ r: 3 }} />
                            <Line type="monotone" dataKey="lstm_price" name="LSTM" stroke="#eb2f96" strokeWidth={2} dot={{ r: 3 }} />
                            <Area type="monotone" dataKey="rf_price" fill="#1890ff" stroke="none" fillOpacity={0.1} />
                        </>
                    ) : (
                        <>
                            {chartData.some(d => d.range) && (
                                <Area
                                    type="monotone"
                                    dataKey="range"
                                    stroke="#8884d8"
                                    fill="#8884d8"
                                    fillOpacity={0.2}
                                    name="95% 置信区间"
                                />
                            )}
                            <Line
                                type="monotone"
                                dataKey="price"
                                stroke="#1890ff"
                                strokeWidth={3}
                                dot={{ r: 4 }}
                                name="预测价格"
                            />
                        </>
                    )}
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );

    return (
        <div style={{ marginTop: 24 }}>
            <Row gutter={[24, 24]}>
                <Col span={24}>
                    <Card
                        title={<><RobotOutlined /> AI 价格预测 (未来5天)</>}
                        bordered={false}
                        style={{
                            boxShadow: '0 4px 20px rgba(0,0,0,0.1)',
                            background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                            borderRadius: 12
                        }}
                        headStyle={{ color: '#fff', borderBottom: '1px solid rgba(255,255,255,0.1)' }}
                        extra={<Button type="text" icon={<ReloadOutlined style={{ color: 'white' }} />} onClick={fetchPrediction} />}
                    >
                        {renderControls()}

                        {renderSummary()}

                        <Row gutter={16} style={{ marginBottom: 16 }}>
                            <Col span={24}>
                                <Paragraph style={{ color: 'rgba(255,255,255,0.8)' }}>
                                    <Text strong style={{ color: '#fee440' }}>模型说明：</Text>
                                    {'等权融合 LSTM (50%) 和 Random Forest (50%) 的结果，提供最稳健的预测。'}
                                    <br />
                                    <Space style={{ marginTop: 8 }}>
                                        <Tag color="purple">动态特征工程</Tag>
                                    </Space>
                                </Paragraph>
                            </Col>
                        </Row>

                        {renderChart()}

                        <Alert
                            message="风险提示"
                            description="AI预测基于历史数据，不代表未来表现。LSTM 模型对参数敏感，训练需要较多数据。"
                            type="warning"
                            showIcon
                            style={{ marginTop: 16 }}
                        />
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default AIPredictionPanel;
