import React, { useState, useEffect, useRef } from 'react';
import { Card, Spin, Alert, Typography, Row, Col, Statistic, Tag, Button, Tooltip as AntTooltip, message, Space } from 'antd';
import { RobotOutlined, ArrowUpOutlined, ArrowDownOutlined, ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import { ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { compareModelPredictions, trainAllModels } from '../services/api';

const { Text, Paragraph } = Typography;
const AI_COLORS = {
    primary: '#0f766e',
    primarySoft: 'rgba(15, 118, 110, 0.14)',
    secondary: '#2563eb',
    secondarySoft: 'rgba(37, 99, 235, 0.12)',
    positive: '#16a34a',
    positiveSoft: 'rgba(22, 163, 74, 0.12)',
    negative: '#dc2626',
    negativeSoft: 'rgba(220, 38, 38, 0.12)',
    neutral: '#ca8a04',
    neutralSoft: 'rgba(202, 138, 4, 0.12)',
    panel: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 94%, white 6%) 0%, color-mix(in srgb, var(--bg-primary) 96%, white 4%) 100%)',
};
const MODEL_LABELS = {
    random_forest: '随机森林',
    lstm: 'LSTM',
};
const predictionResultCache = new Map();
const predictionRequestCache = new Map();

const buildPredictionCacheKey = (symbol) => `${symbol || ''}:consensus`;
const hasNumericValue = (value) => value !== null && value !== undefined && !Number.isNaN(Number(value));
const getPricePoint = (prices = [], index) => hasNumericValue(prices?.[index]) ? Number(prices[index]) : null;

const AIPredictionPanel = ({ symbol }) => {
    const [loading, setLoading] = useState(false);
    const [training, setTraining] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const requestSequenceRef = useRef(0);
    const isMountedRef = useRef(true);

    useEffect(() => {
        isMountedRef.current = true;

        return () => {
            isMountedRef.current = false;
            requestSequenceRef.current += 1;
        };
    }, []);

    useEffect(() => {
        if (symbol) {
            requestSequenceRef.current += 1;
            setData(null);
            setError(null);
            fetchPrediction({ requestId: requestSequenceRef.current });
        } else {
            requestSequenceRef.current += 1;
            setData(null);
            setError(null);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [symbol]);

    const fetchPrediction = async (options = {}) => {
        const { forceRefresh = false, requestId = requestSequenceRef.current } = options;
        const cacheKey = buildPredictionCacheKey(symbol);
        setLoading(true);
        setError(null);
        try {
            if (!forceRefresh && predictionResultCache.has(cacheKey)) {
                if (isMountedRef.current && requestSequenceRef.current === requestId) {
                    setData(predictionResultCache.get(cacheKey));
                }
                return;
            }

            let requestPromise = predictionRequestCache.get(cacheKey);
            if (!requestPromise || forceRefresh) {
                requestPromise = compareModelPredictions(symbol);
                predictionRequestCache.set(cacheKey, requestPromise);
            }

            const result = await requestPromise;
            predictionResultCache.set(cacheKey, result);
            predictionRequestCache.delete(cacheKey);
            if (isMountedRef.current && requestSequenceRef.current === requestId) {
                setData(result);
            }
        } catch (err) {
            predictionRequestCache.delete(cacheKey);
            console.error("Prediction error:", err);
            if (isMountedRef.current && requestSequenceRef.current === requestId) {
                setError("无法获取AI预测数据，请稍后重试");
            }
        } finally {
            if (isMountedRef.current && requestSequenceRef.current === requestId) {
                setLoading(false);
            }
        }
    };

    const handleTrainModels = async () => {
        setTraining(true);
        try {
            await trainAllModels(symbol);
            predictionResultCache.delete(buildPredictionCacheKey(symbol));
            message.success('模型训练完成！正在刷新预测...');
            requestSequenceRef.current += 1;
            fetchPrediction({ forceRefresh: true, requestId: requestSequenceRef.current });
        } catch (err) {
            console.error("Training error:", err);
            message.error('模型训练失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            setTraining(false);
        }
    };

    if (loading && !data) {
        return (
            <Card style={{ minHeight: 400, display: 'flex', justifyContent: 'center', alignItems: 'center', borderRadius: 22 }}>
                <div style={{ textAlign: 'center' }}>
                    <Spin size="large" />
                    <div style={{ marginTop: 12, color: 'var(--text-secondary)' }}>
                        AI 综合共识正在分析并预测未来趋势...
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

    const randomForestPrediction = data.predictions?.random_forest || null;
    const lstmPrediction = data.predictions?.lstm || null;
    const randomForestAvailable = randomForestPrediction?.status === 'success'
        && Array.isArray(randomForestPrediction.predicted_prices)
        && randomForestPrediction.predicted_prices.length > 0;
    const lstmAvailable = lstmPrediction?.status === 'success'
        && Array.isArray(lstmPrediction.predicted_prices)
        && lstmPrediction.predicted_prices.length > 0;
    const availableModelNames = [
        randomForestAvailable ? MODEL_LABELS.random_forest : null,
        lstmAvailable ? MODEL_LABELS.lstm : null,
    ].filter(Boolean);
    const unavailableModelNames = [
        randomForestAvailable ? null : MODEL_LABELS.random_forest,
        lstmAvailable ? null : MODEL_LABELS.lstm,
    ].filter(Boolean);
    const hasAnyPrediction = randomForestAvailable || lstmAvailable || (
        Array.isArray(data.predicted_prices) && data.predicted_prices.some((value) => hasNumericValue(value))
    );

    // --- Data Formatting Helpers ---

    const formatChartData = () => {
        if (!data.dates) return [];

        return data.dates.map((date, index) => {
            const item = { date: new Date(date).toLocaleDateString() };
            const rfPrice = getPricePoint(randomForestPrediction?.predicted_prices, index);
            const lstmPrice = getPricePoint(lstmPrediction?.predicted_prices, index);

            if (rfPrice !== null && lstmPrice !== null) {
                item.price = (lstmPrice * 0.5) + (rfPrice * 0.5);

                const disagreement = Math.abs(rfPrice - lstmPrice);
                const lower = randomForestPrediction?.confidence_intervals?.[index]?.lower;
                const upper = randomForestPrediction?.confidence_intervals?.[index]?.upper;
                const baseInterval = hasNumericValue(lower) && hasNumericValue(upper)
                    ? Number(upper) - Number(lower)
                    : 0;
                const intervalHalf = (baseInterval / 2) + (disagreement * 0.5);

                item.range = [item.price - intervalHalf, item.price + intervalHalf];
            } else if (rfPrice !== null || lstmPrice !== null) {
                item.price = rfPrice ?? lstmPrice;
                const fallbackPrediction = rfPrice !== null ? randomForestPrediction : lstmPrediction;
                const fallbackInterval = fallbackPrediction?.confidence_intervals?.[index];
                if (hasNumericValue(fallbackInterval?.lower) && hasNumericValue(fallbackInterval?.upper)) {
                    item.range = [Number(fallbackInterval.lower), Number(fallbackInterval.upper)];
                }
            } else {
                item.price = null;
            }
            return item;
        }).filter((item) => item.price !== null);
    };

    const chartData = formatChartData();
    let startPrice = null, endPrice = null, priceChange = null, percentChange = null;

    const projectedPrices = chartData
        .map((item) => item.price)
        .filter((value) => value !== null);

    if (projectedPrices.length > 0) {
        startPrice = projectedPrices[0];
        endPrice = projectedPrices[projectedPrices.length - 1];
    }

    if (hasNumericValue(startPrice) && hasNumericValue(endPrice)) {
        priceChange = endPrice - startPrice;
        percentChange = startPrice > 0 ? (priceChange / startPrice) * 100 : 0;
    }
    const isPositive = hasNumericValue(priceChange) ? priceChange >= 0 : true;
    const agreementMetric = data.metrics?.accuracy;
    const agreementValue = hasNumericValue(agreementMetric)
        ? Number(agreementMetric) * 100
        : null;
    const hasPartialPrediction = availableModelNames.length === 1;

    // --- Render Content ---

    const renderControls = () => (
        <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10, borderColor: 'transparent', background: AI_COLORS.primarySoft, color: AI_COLORS.primary, fontWeight: 700 }}>
                        {symbol}
                    </Tag>
                    <Tag icon={<RobotOutlined />} style={{ margin: 0, borderRadius: 999, paddingInline: 10, borderColor: 'transparent', background: AI_COLORS.secondarySoft, color: AI_COLORS.secondary, fontWeight: 700 }}>
                        AI 综合预测
                    </Tag>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    等权融合 LSTM 与随机森林，输出未来 5 天的共识价格路径和区间判断。
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {availableModelNames.map((label) => (
                        <Tag key={label} style={{ margin: 0, borderRadius: 999, paddingInline: 10, borderColor: 'transparent', background: AI_COLORS.positiveSoft, color: AI_COLORS.positive, fontWeight: 700 }}>
                            已接入 {label}
                        </Tag>
                    ))}
                    {unavailableModelNames.map((label) => (
                        <Tag key={label} style={{ margin: 0, borderRadius: 999, paddingInline: 10, borderColor: 'transparent', background: AI_COLORS.neutralSoft, color: AI_COLORS.neutral, fontWeight: 700 }}>
                            暂不可用 {label}
                        </Tag>
                    ))}
                </div>
            </div>

            <AntTooltip title="使用最新数据重新训练所有模型 (耗时较长)">
                <Button
                    icon={training ? <Spin indicator={<ExperimentOutlined spin />} /> : <ExperimentOutlined />}
                    onClick={handleTrainModels}
                    loading={training}
                    size="middle"
                >
                    {training ? '训练中...' : '训练模型'}
                </Button>
            </AntTooltip>
        </div>
    );

    const renderSummary = () => (
        <Row gutter={24} style={{ marginBottom: 24 }}>
            <Col span={6}>
                <Card size="small" style={{ borderRadius: 18, background: AI_COLORS.primarySoft, borderColor: 'transparent' }}>
                    <Statistic
                        title={<span style={{ color: 'var(--text-secondary)' }}>起始预测均价</span>}
                        value={startPrice}
                        formatter={() => hasNumericValue(startPrice) ? Number(startPrice).toFixed(2) : '--'}
                        prefix={hasNumericValue(startPrice) ? '$' : ''}
                        valueStyle={{ color: AI_COLORS.primary, fontSize: 24 }}
                    />
                </Card>
            </Col>
            <Col span={6}>
                <Card size="small" style={{ borderRadius: 18, background: isPositive ? AI_COLORS.positiveSoft : AI_COLORS.negativeSoft, borderColor: 'transparent' }}>
                    <Statistic
                        title={<span style={{ color: 'var(--text-secondary)' }}>5日后预测均价</span>}
                        value={endPrice}
                        formatter={() => hasNumericValue(endPrice) ? Number(endPrice).toFixed(2) : '--'}
                        prefix={hasNumericValue(endPrice) ? '$' : ''}
                        valueStyle={{ color: isPositive ? AI_COLORS.positive : AI_COLORS.negative, fontSize: 24 }}
                    />
                </Card>
            </Col>
            <Col span={6}>
                <Card size="small" style={{ borderRadius: 18, background: isPositive ? AI_COLORS.positiveSoft : AI_COLORS.negativeSoft, borderColor: 'transparent' }}>
                    <Statistic
                        title={<span style={{ color: 'var(--text-secondary)' }}>预测涨跌幅</span>}
                        value={percentChange}
                        formatter={() => hasNumericValue(percentChange) ? Number(percentChange).toFixed(2) : '--'}
                        valueStyle={{ color: isPositive ? AI_COLORS.positive : AI_COLORS.negative, fontSize: 24 }}
                        prefix={hasNumericValue(percentChange) ? (isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />) : ''}
                        suffix={hasNumericValue(percentChange) ? '%' : ''}
                    />
                </Card>
            </Col>
            <Col span={6}>
                <Card size="small" style={{ borderRadius: 18, background: AI_COLORS.secondarySoft, borderColor: 'transparent' }}>
                    <Statistic
                        title={<span style={{ color: 'var(--text-secondary)' }}>置信度/误差</span>}
                        value={agreementValue}
                        formatter={() => hasNumericValue(agreementValue) ? Number(agreementValue).toFixed(2) : '--'}
                        suffix={hasNumericValue(agreementValue) ? '%' : ''}
                        valueStyle={{ color: AI_COLORS.secondary, fontSize: 24 }}
                    />
                </Card>
            </Col>
        </Row>
    );

    const renderChart = () => (
        <div style={{ height: 400 }}>
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.22)" />
                    <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={{ stroke: 'rgba(148, 163, 184, 0.24)' }} tickLine={false} />
                    <YAxis domain={['auto', 'auto']} tick={{ fill: '#64748b', fontSize: 12 }} axisLine={{ stroke: 'rgba(148, 163, 184, 0.24)' }} tickLine={false} />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: 'rgba(15, 23, 42, 0.92)',
                            border: '1px solid rgba(148, 163, 184, 0.2)',
                            borderRadius: 16,
                            boxShadow: '0 18px 34px rgba(15, 23, 42, 0.18)',
                        }}
                        itemStyle={{ color: '#f8fafc' }}
                        labelStyle={{ color: '#cbd5e1' }}
                    />
                    <Legend wrapperStyle={{ paddingTop: 8 }} />

                    <>
                        {chartData.some(d => d.range) && (
                            <Area
                                type="monotone"
                                dataKey="range"
                                stroke={AI_COLORS.secondary}
                                fill={AI_COLORS.secondary}
                                fillOpacity={0.16}
                                name="95% 置信区间"
                            />
                        )}
                        <Line
                            type="monotone"
                            dataKey="price"
                            stroke={isPositive ? AI_COLORS.positive : AI_COLORS.secondary}
                            strokeWidth={3}
                            dot={{ r: 4 }}
                            name="预测价格"
                        />
                    </>
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
                        variant="borderless"
                        style={{
                            boxShadow: '0 18px 42px rgba(15, 23, 42, 0.08)',
                            background: AI_COLORS.panel,
                            borderRadius: 22,
                            border: '1px solid color-mix(in srgb, var(--border-color) 84%, white 16%)'
                        }}
                        styles={{
                            header: {
                                color: 'var(--text-primary)',
                                borderBottom: '1px solid color-mix(in srgb, var(--border-color) 84%, white 16%)',
                                minHeight: 56,
                            }
                        }}
                        extra={<Button type="text" icon={<ReloadOutlined style={{ color: 'var(--text-secondary)' }} />} onClick={() => fetchPrediction({ forceRefresh: true })} />}
                    >
                        {renderControls()}

                        {!hasAnyPrediction && (
                            <Alert
                                message="暂无可用预测结果"
                                description="当前没有可展示的模型输出，请稍后重试或重新训练模型。"
                                type="warning"
                                showIcon
                                style={{ marginBottom: 16, borderRadius: 18 }}
                            />
                        )}

                        {hasPartialPrediction && (
                            <Alert
                                message={`当前仅使用${availableModelNames[0]}结果`}
                                description={`综合共识模式下，${unavailableModelNames.join('、')} 当前不可用，因此页面会回退为单模型结果，不再伪造 0 值预测。`}
                                type="info"
                                showIcon
                                style={{ marginBottom: 16, borderRadius: 18 }}
                            />
                        )}

                        {renderSummary()}

                        <Row gutter={16} style={{ marginBottom: 16 }}>
                            <Col span={24}>
                                <Paragraph style={{ color: 'var(--text-secondary)', marginBottom: 0 }}>
                                    <Text strong style={{ color: AI_COLORS.primary }}>模型说明：</Text>
                                    {'等权融合 LSTM (50%) 和随机森林 (50%) 的结果，提供更稳健的预测参考。'}
                                    <br />
                                    <Space style={{ marginTop: 8 }}>
                                        <Tag style={{ borderRadius: 999, background: AI_COLORS.secondarySoft, color: AI_COLORS.secondary, borderColor: 'transparent' }}>动态特征工程</Tag>
                                        <Tag style={{ borderRadius: 999, background: AI_COLORS.primarySoft, color: AI_COLORS.primary, borderColor: 'transparent' }}>5日共识路径</Tag>
                                        <Tag style={{ borderRadius: 999, background: AI_COLORS.neutralSoft, color: AI_COLORS.neutral, borderColor: 'transparent' }}>
                                            终点均价 {hasNumericValue(endPrice) ? `$${Number(endPrice).toFixed(2)}` : '--'}
                                        </Tag>
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
                            style={{ marginTop: 16, borderRadius: 18 }}
                        />
                    </Card>
                </Col>
            </Row>
        </div>
    );
};

export default AIPredictionPanel;
