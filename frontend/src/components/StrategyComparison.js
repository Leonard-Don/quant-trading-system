import React, { useEffect, useMemo, useState } from 'react';
import {
    Card,
    Select,
    DatePicker,
    Button,
    Table,
    Row,
    Col,
    Space,
    Typography,
    Alert,
    Progress,
    Tag,
    Input,
    InputNumber,
} from 'antd';
import { BarChartOutlined, DownloadOutlined, TrophyOutlined } from '@ant-design/icons';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    RadarChart,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
    Radar,
    Cell
} from 'recharts';
import dayjs from '../utils/dayjs';
import { compareStrategies } from '../services/api';
import { getStrategyName, getStrategyParameterLabel, getStrategyDetails } from '../constants/strategies';
import { normalizeBacktestResult } from '../utils/backtest';
import { useSafeMessageApi } from '../utils/messageApi';
import {
    buildStrategyComparisonReportHtml,
    openStrategyComparisonPrintWindow,
} from '../utils/strategyComparisonReport';

const { Text } = Typography;
const { RangePicker } = DatePicker;
const DATE_FORMAT = 'YYYY-MM-DD';

const StrategyComparison = ({ strategies }) => {
    const message = useSafeMessageApi();
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [strategyParameters, setStrategyParameters] = useState({});
    const [params, setParams] = useState({
        symbol: 'AAPL',
        selectedStrategies: [],
        dateRange: [dayjs().subtract(1, 'year'), dayjs()],
        initialCapital: 10000,
        commission: 0.1,
        slippage: 0.1,
    });

    const strategyDefinitions = useMemo(() => (
        Object.fromEntries(strategies.map((strategy) => [strategy.name, strategy]))
    ), [strategies]);
    const comparisonPresets = useMemo(() => {
        const availableStrategies = new Set(strategies.map((strategy) => strategy.name));
        return [
            {
                key: 'trend-vs-benchmark',
                label: '均线 vs 基准',
                description: '快速比较趋势策略和买入持有。',
                strategies: ['moving_average', 'buy_and_hold'],
            },
            {
                key: 'macd-vs-trend',
                label: 'MACD vs 均线',
                description: '对比两种常见趋势跟随思路。',
                strategies: ['macd', 'moving_average'],
            },
            {
                key: 'reversion-vs-momentum',
                label: '均值回归 vs 动量',
                description: '观察反转逻辑和动量逻辑在同一标的下的差异。',
                strategies: ['mean_reversion', 'momentum'],
            },
        ].filter((preset) => preset.strategies.every((strategyName) => availableStrategies.has(strategyName)));
    }, [strategies]);

    useEffect(() => {
        setStrategyParameters((previous) => {
            const next = {};
            params.selectedStrategies.forEach((strategyName) => {
                const strategy = strategyDefinitions[strategyName];
                const defaults = Object.fromEntries(
                    Object.entries(strategy?.parameters || {}).map(([key, config]) => [key, config.default])
                );
                next[strategyName] = {
                    ...defaults,
                    ...(previous[strategyName] || {}),
                };
            });
            return next;
        });
    }, [params.selectedStrategies, strategyDefinitions]);

    const updateStrategyParameter = (strategyName, parameterKey, value) => {
        setStrategyParameters((previous) => ({
            ...previous,
            [strategyName]: {
                ...(previous[strategyName] || {}),
                [parameterKey]: value,
            },
        }));
    };

    const handleCompare = async () => {
        if (!params.symbol.trim()) {
            message.warning('请输入要比较的标的代码');
            return;
        }

        if (params.selectedStrategies.length < 2) {
            message.warning('请至少选择两个策略进行对比');
            return;
        }

        setLoading(true);

        try {
            const response = await compareStrategies({
                symbol: params.symbol,
                start_date: params.dateRange[0]?.format(DATE_FORMAT),
                end_date: params.dateRange[1]?.format(DATE_FORMAT),
                initial_capital: params.initialCapital,
                commission: (params.commission ?? 0) / 100,
                slippage: (params.slippage ?? 0) / 100,
                strategy_configs: params.selectedStrategies.map((strategyName) => ({
                    name: strategyName,
                    parameters: strategyParameters[strategyName] || {},
                })),
            });

            if (response.success) {
                setResults(response.data);
                message.success('对比分析完成');
            } else {
                message.error('分析失败: ' + response.error);
            }
        } catch (error) {
            console.error('Comparison error:', error);
            message.error('请求失败: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    const applyPreset = (presetStrategies) => {
        setParams((previous) => ({ ...previous, selectedStrategies: presetStrategies }));
    };

    const renderStrategyParameterPanels = () => {
        if (params.selectedStrategies.length === 0) {
            return null;
        }

        return (
            <Card className="workspace-panel" style={{ marginBottom: 20 }} title="策略参数版本">
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                    {params.selectedStrategies.map((strategyName) => {
                        const strategy = strategyDefinitions[strategyName];
                        const parameterEntries = Object.entries(strategy?.parameters || {});

                        return (
                            <Card
                                key={strategyName}
                                size="small"
                                title={getStrategyName(strategyName)}
                                className="workspace-panel workspace-panel--subtle"
                            >
                                <div className="workspace-section__description" style={{ marginBottom: 12 }}>
                                    {getStrategyDetails(strategyName).summary}
                                </div>
                                <div className="workspace-section__hint" style={{ marginBottom: 16 }}>
                                    {getStrategyDetails(strategyName).marketFit}
                                </div>
                                {parameterEntries.length === 0 ? (
                                    <Alert
                                        message="该策略当前没有可调参数，将按默认规则参与对比。"
                                        type="info"
                                        showIcon
                                    />
                                ) : (
                                    <Row gutter={[16, 16]}>
                                        {parameterEntries.map(([parameterKey, parameterConfig]) => (
                                            <Col key={`${strategyName}-${parameterKey}`} xs={24} md={12} lg={8}>
                                                <div className="workspace-field-label">
                                                    {getStrategyParameterLabel(parameterKey, parameterConfig.description)}
                                                </div>
                                                <InputNumber
                                                    aria-label={`${getStrategyName(strategyName)}-${parameterKey}`}
                                                    value={strategyParameters[strategyName]?.[parameterKey] ?? parameterConfig.default}
                                                    min={parameterConfig.min}
                                                    max={parameterConfig.max}
                                                    step={parameterConfig.step || 0.01}
                                                    style={{ width: '100%' }}
                                                    onChange={(value) => updateStrategyParameter(strategyName, parameterKey, value)}
                                                />
                                            </Col>
                                        ))}
                                    </Row>
                                )}
                            </Card>
                        );
                    })}
                </Space>
            </Card>
        );
    };

    // 导出对比报告为 PDF（通过浏览器打印，确保中文稳定渲染）
    const exportComparisonReport = () => {
        if (!results || dataSource.length === 0) {
            message.warning('请先进行策略对比');
            return;
        }

        try {
            const reportHtml = buildStrategyComparisonReportHtml({
                symbol: params.symbol,
                startDate: params.dateRange[0]?.format(DATE_FORMAT),
                endDate: params.dateRange[1]?.format(DATE_FORMAT),
                generatedAt: new Date().toLocaleString(),
                initialCapital: `$${Number(params.initialCapital || 0).toLocaleString()}`,
                commission: `${params.commission}%`,
                slippage: `${params.slippage}%`,
                rankedData,
                dataSource,
            });
            const opened = openStrategyComparisonPrintWindow(reportHtml);
            if (!opened) {
                message.error('无法打开打印窗口，请检查浏览器弹窗设置');
                return;
            }
            message.success('已打开打印窗口，可直接另存为 PDF');
        } catch (error) {
            message.error('导出失败: ' + error.message);
        }
    };

    const columns = [
        {
            title: '策略名称',
            dataIndex: 'strategyName', // Changed to localized name
            key: 'strategyName',
            render: (text) => <Text strong>{text}</Text>
        },
        {
            title: '总收益率',
            dataIndex: 'total_return',
            key: 'total_return',
            render: (value, record) => {
                if (record.num_trades === 0) {
                    return <Text type="secondary">无交易</Text>;
                }
                return (
                    <Text type={value >= 0 ? 'success' : 'danger'}>
                        {(value * 100).toFixed(2)}%
                    </Text>
                );
            },
            sorter: (a, b) => a.total_return - b.total_return
        },
        {
            title: '年化收益',
            dataIndex: 'annualized_return',
            key: 'annualized_return',
            render: (value) => `${(value * 100).toFixed(2)}%`
        },
        {
            title: '最大回撤',
            dataIndex: 'max_drawdown',
            key: 'max_drawdown',
            render: (value) => (
                <Text type="danger">
                    {(value * 100).toFixed(2)}%
                </Text>
            )
        },
        {
            title: '夏普比率',
            dataIndex: 'sharpe_ratio',
            key: 'sharpe_ratio',
            render: (value) => value.toFixed(2)
        },
        {
            title: '交易次数',
            dataIndex: 'num_trades',
            key: 'num_trades'
        }
    ];

    // 转换数据用于表格和图表
    const dataSource = useMemo(() => (
        results
            ? Object.entries(results).map(([name, metrics]) => {
            const normalized = normalizeBacktestResult(metrics);
            return {
                key: name,
                strategy: name,
                strategyName: getStrategyName(name),
                ...normalized,
                scores: normalized.scores || metrics.scores,
                rank: normalized.rank || metrics.rank,
            };
        })
            : []
    ), [results]);

    // 直接使用后端返回的排名数据
    const rankedData = useMemo(() => {
        if (dataSource.length === 0) return [];
        return [...dataSource].sort((a, b) => a.rank - b.rank);
    }, [dataSource]);

    // 获取排名奖牌颜色
    const getRankColor = (rank) => {
        switch (rank) {
            case 1: return { color: '#ffd700', bg: 'linear-gradient(135deg, #ffd700 0%, #ffed4a 100%)', label: '🥇' };
            case 2: return { color: '#c0c0c0', bg: 'linear-gradient(135deg, #c0c0c0 0%, #e8e8e8 100%)', label: '🥈' };
            case 3: return { color: '#cd7f32', bg: 'linear-gradient(135deg, #cd7f32 0%, #dda15e 100%)', label: '🥉' };
            default: return { color: '#8b5cf6', bg: '#8b5cf6', label: rank };
        }
    };

    const chartData = dataSource.map(item => ({
        name: item.strategyName,
        '总收益率': parseFloat((item.total_return * 100).toFixed(2)), // Parse float for chart scaling
        '最大回撤': parseFloat((item.max_drawdown * 100).toFixed(2))
    }));

    return (
        <div className="workspace-tab-view">
            <div className="workspace-section workspace-section--accent">
                <div className="workspace-section__header">
                    <div>
                        <div className="workspace-section__title">策略性能对比</div>
                        <div className="workspace-section__description">在同一标的与时间区间内横向比较多种策略，把收益、风控和综合评分放进统一视图。</div>
                    </div>
                </div>
                <div className="summary-strip summary-strip--compact">
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">标的</span>
                        <span className="summary-strip__value">{params.symbol}</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">已选策略</span>
                        <span className="summary-strip__value">{params.selectedStrategies.length} 个</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">区间</span>
                        <span className="summary-strip__value">{`${params.dateRange[0].format('YYYY-MM-DD')} ~ ${params.dateRange[1].format('YYYY-MM-DD')}`}</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">初始资金</span>
                        <span className="summary-strip__value">{`$${Number(params.initialCapital || 0).toLocaleString()}`}</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">成本设置</span>
                        <span className="summary-strip__value">{`${params.commission}% / ${params.slippage}%`}</span>
                    </div>
                    <div className="summary-strip__item">
                        <span className="summary-strip__label">状态</span>
                        <span className="summary-strip__value">{loading ? '分析中' : (results ? '结果已生成' : '待运行')}</span>
                    </div>
                </div>
            </div>

            <Card className="workspace-panel" style={{ marginBottom: 20 }}>
                <Space size="large" wrap style={{ marginBottom: comparisonPresets.length ? 12 : 0 }}>
                    <div style={{ width: 180 }}>
                        <Input
                            value={params.symbol}
                            placeholder="输入标的代码"
                            onChange={(event) => setParams((prev) => ({ ...prev, symbol: event.target.value.trim().toUpperCase() }))}
                        />
                    </div>
                    <div style={{ width: 300 }}>
                        <Select
                            mode="multiple"
                            value={params.selectedStrategies}
                            style={{ width: '100%' }}
                            placeholder="选择要对比的策略"
                            onChange={(values) => setParams(prev => ({ ...prev, selectedStrategies: values }))}
                            maxTagCount="responsive"
                        >
                            {strategies.map(s => (
                                <Select.Option key={s.name} value={s.name}>{getStrategyName(s.name)}</Select.Option>
                            ))}
                        </Select>
                    </div>
                    <RangePicker
                        value={params.dateRange}
                        placeholder={['开始日期', '结束日期']}
                        separator="至"
                        onChange={(dates) => setParams(prev => ({ ...prev, dateRange: dates }))}
                    />
                    <InputNumber
                        value={params.initialCapital}
                        min={1000}
                        step={1000}
                        precision={0}
                        placeholder="初始资金"
                        style={{ width: 160 }}
                        onChange={(value) => setParams((prev) => ({ ...prev, initialCapital: value ?? 10000 }))}
                    />
                    <InputNumber
                        value={params.commission}
                        min={0}
                        step={0.01}
                        precision={2}
                        placeholder="手续费"
                        style={{ width: 110 }}
                        onChange={(value) => setParams((prev) => ({ ...prev, commission: value ?? 0 }))}
                    />
                    <Text type="secondary">%</Text>
                    <InputNumber
                        value={params.slippage}
                        min={0}
                        step={0.01}
                        precision={2}
                        placeholder="滑点"
                        style={{ width: 110 }}
                        onChange={(value) => setParams((prev) => ({ ...prev, slippage: value ?? 0 }))}
                    />
                    <Text type="secondary">%</Text>
                    <Button
                        type="primary"
                        icon={<BarChartOutlined />}
                        onClick={handleCompare}
                        loading={loading}
                        disabled={params.selectedStrategies.length < 2}
                    >
                        开始对比
                    </Button>
                    {results && (
                        <Button
                            icon={<DownloadOutlined />}
                            onClick={exportComparisonReport}
                        >
                            导出PDF报告
                        </Button>
                    )}
                </Space>
                {comparisonPresets.length ? (
                    <Space wrap>
                        <Text type="secondary">快速开始</Text>
                        {comparisonPresets.map((preset) => (
                            <Button
                                key={preset.key}
                                size="small"
                                onClick={() => applyPreset(preset.strategies)}
                            >
                                {preset.label}
                            </Button>
                        ))}
                    </Space>
                ) : null}
            </Card>

            {renderStrategyParameterPanels()}

            {results && (
                <Row gutter={[16, 16]}>
                    {loading ? (
                        <Col span={24}>
                            <Alert
                                type="info"
                                showIcon
                                message="正在基于新配置刷新对比结果"
                                description="上一版对比结果会先保留，新的评分和图表返回后会自动覆盖。"
                            />
                        </Col>
                    ) : null}
                    {/* 综合评分排名卡片 */}
                    <Col span={24}>
                        <Card
                            className="workspace-panel workspace-panel--emphasis"
                            title={
                                <Space>
                                    <TrophyOutlined style={{ color: '#ffd700' }} />
                                    <span>策略综合评分排名</span>
                                </Space>
                            }
                        >
                            <Row gutter={16}>
                                {rankedData.slice(0, 4).map((item) => {
                                    const rankStyle = getRankColor(item.rank);
                                    return (
                                        <Col span={6} key={item.strategy}>
                                            <div style={{
                                                background: 'rgba(255,255,255,0.05)',
                                                borderRadius: 12,
                                                padding: 16,
                                                textAlign: 'center',
                                                border: item.rank === 1 ? '2px solid #ffd700' : '1px solid rgba(255,255,255,0.1)'
                                            }}>
                                                <div style={{
                                                    fontSize: 32,
                                                    marginBottom: 8,
                                                    textShadow: item.rank <= 3 ? '0 0 10px rgba(255,215,0,0.5)' : 'none'
                                                }}>
                                                    {rankStyle.label}
                                                </div>
                                                <div style={{ color: '#fff', fontWeight: 600, fontSize: 16, marginBottom: 8 }}>
                                                    {item.strategyName}
                                                </div>
                                                <Progress
                                                    percent={item.scores.overall_score}
                                                    strokeColor={rankStyle.bg}
                                                    trailColor="rgba(255,255,255,0.1)"
                                                    format={(pct) => <span style={{ color: '#fff', fontWeight: 600 }}>{pct}</span>}
                                                />
                                                <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-around' }}>
                                                    <Tag color="green">收益 {item.scores.return_score}</Tag>
                                                    <Tag color="blue">夏普 {item.scores.sharpe_score}</Tag>
                                                    <Tag color="orange">风控 {item.scores.risk_score}</Tag>
                                                </div>
                                            </div>
                                        </Col>
                                    );
                                })}
                            </Row>
                        </Card>
                    </Col>

                    <Col span={24}>
                        <Card title="对比结果概览" className="workspace-panel">
                            <Table
                                dataSource={dataSource}
                                columns={columns}
                                pagination={false}
                                size="middle"
                            />
                        </Card>
                    </Col>

                    {/* 雷达图 - 多维度对比 */}
                    <Col span={12}>
                        <Card title="多维度性能雷达图" className="workspace-chart-card workspace-panel">
                            <div className="radar-chart-container">
                                <ResponsiveContainer width="100%" height={380} minWidth={320} minHeight={380}>
                                    <RadarChart
                                        cx="50%"
                                        cy="50%"
                                        outerRadius="70%"
                                        data={[
                                            { metric: '收益率', ...Object.fromEntries(dataSource.map(d => [d.strategy, Math.min(100, Math.max(0, (d.total_return + 0.5) * 100))])) },
                                            { metric: '夏普比率', ...Object.fromEntries(dataSource.map(d => [d.strategy, Math.min(100, Math.max(0, (d.sharpe_ratio + 1) * 30))])) },
                                            { metric: '稳定性', ...Object.fromEntries(dataSource.map(d => [d.strategy, Math.min(100, Math.max(0, 100 - d.max_drawdown * 200))])) },
                                            { metric: '交易效率', ...Object.fromEntries(dataSource.map(d => [d.strategy, Math.min(100, Math.max(0, d.num_trades > 0 ? 50 + (d.total_return / d.num_trades) * 1000 : 50))])) },
                                            { metric: '年化', ...Object.fromEntries(dataSource.map(d => [d.strategy, Math.min(100, Math.max(0, (d.annualized_return + 0.3) * 150))])) }
                                        ]}
                                    >
                                        <PolarGrid stroke="rgba(255,255,255,0.3)" />
                                        <PolarAngleAxis
                                            dataKey="metric"
                                            tick={{ fill: '#fff', fontSize: 13, fontWeight: 'bold' }}
                                        />
                                        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
                                        {dataSource.map((entry, index) => (
                                            <Radar
                                                key={entry.strategy}
                                                name={entry.strategyName}
                                                dataKey={entry.strategy}
                                                stroke={['#00f5d4', '#fee440', '#f15bb5', '#9b5de5'][index % 4]}
                                                fill={['#00f5d4', '#fee440', '#f15bb5', '#9b5de5'][index % 4]}
                                                fillOpacity={0.4}
                                                strokeWidth={3}
                                            />
                                        ))}
                                        <Legend wrapperStyle={{ color: '#fff', paddingTop: 20 }} />
                                        <Tooltip contentStyle={{ background: 'rgba(0,0,0,0.8)', border: 'none', borderRadius: 8 }} />
                                    </RadarChart>
                                </ResponsiveContainer>
                            </div>
                        </Card>
                    </Col>

                    {/* 增强柱状图 */}
                    <Col span={12}>
                        <Card title="收益与风险对比" className="workspace-chart-card workspace-panel">
                            <ResponsiveContainer width="100%" height={380} minWidth={320} minHeight={380}>
                                <BarChart data={chartData} margin={{ top: 20, right: 30, left: 30, bottom: 20 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                    <XAxis dataKey="name" tick={{ fill: '#fff', fontSize: 11 }} />
                                    <YAxis
                                        unit="%"
                                        tick={{ fill: '#fff', fontSize: 11 }}
                                        domain={['auto', 'auto']}
                                    />
                                    <Tooltip
                                        contentStyle={{ background: 'rgba(0,0,0,0.9)', border: '1px solid #00f5d4', borderRadius: 8 }}
                                        labelStyle={{ color: '#00f5d4' }}
                                    />
                                    <Legend wrapperStyle={{ color: '#fff', paddingTop: 10 }} />
                                    <Bar dataKey="总收益率" name="总收益率 (%)" radius={[4, 4, 0, 0]}>
                                        {chartData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={parseFloat(entry['总收益率']) >= 0 ? '#00f5d4' : '#ff6b6b'} />
                                        ))}
                                    </Bar>
                                    <Bar dataKey="最大回撤" name="最大回撤 (%)" fill="#ff6b6b" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </Card>
                    </Col>

                    {/* 夏普比率对比 */}
                    <Col span={24}>
                        <Card title="风险调整收益对比 (夏普比率)" className="workspace-chart-card workspace-panel">
                            <ResponsiveContainer width="100%" height={250} minWidth={320} minHeight={250}>
                                <BarChart
                                    data={dataSource.map(d => ({ name: d.strategyName, '夏普比率': d.sharpe_ratio, '年化收益': (d.annualized_return * 100).toFixed(2) }))}
                                    layout="vertical"
                                    margin={{ top: 10, right: 50, left: 100, bottom: 10 }}
                                >
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                    <XAxis type="number" tick={{ fill: '#fff' }} />
                                    <YAxis type="category" dataKey="name" tick={{ fill: '#fff', fontSize: 12 }} width={120} />
                                    <Tooltip
                                        contentStyle={{ background: 'rgba(0,0,0,0.9)', border: '1px solid #fee440', borderRadius: 8 }}
                                    />
                                    <Legend wrapperStyle={{ color: '#fff' }} />
                                    <Bar dataKey="夏普比率" fill="#fee440" radius={[0, 4, 4, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </Card>
                    </Col>
                </Row>
            )}

            {!results && !loading && (
                <Alert
                    message="请选择至少两个策略并点击“开始对比”以查看性能差异"
                    type="info"
                    showIcon
                />
            )}
        </div>
    );
};

export default StrategyComparison;
