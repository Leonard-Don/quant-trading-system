import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
    Card,
    Select,
    Button,
    Spin,
    Empty,
    Tag,
    Space,
    message,
    Typography
} from 'antd';
import {
    SwapOutlined,
    ReloadOutlined
} from '@ant-design/icons';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip as RechartsTooltip,
    ResponsiveContainer,
    Legend,
    ReferenceLine
} from 'recharts';
import { getIndustryRotation, getHotIndustries } from '../services/api';

const { Text } = Typography;

const COLORS = ['#ff4d4f', '#1890ff', '#52c41a', '#faad14', '#eb2f96'];
const PERIOD_LABELS = { 1: '1日', 3: '3日', 5: '5日', 10: '10日', 20: '20日', 60: '60日' };
const PERIOD_OPTIONS = [1, 3, 5, 10, 20, 60];
const PERIOD_PRESETS = [
    { key: 'short', label: '快节奏', periods: [1, 3, 5] },
    { key: 'standard', label: '标准', periods: [1, 5, 20] },
    { key: 'swing', label: '波段', periods: [5, 20, 60] },
];

/**
 * 行业轮动对比图组件
 * 展示多个行业在不同时间周期的涨跌幅趋势对比
 */
const IndustryRotationChart = ({ initialIndustries = [] }) => {
    const [selectedIndustries, setSelectedIndustries] = useState(initialIndustries);
    const [selectedPeriods, setSelectedPeriods] = useState([1, 5, 20]);
    const [rotationData, setRotationData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [industryOptions, setIndustryOptions] = useState([]);
    const [loadingOptions, setLoadingOptions] = useState(false);
    const rotationAbortRef = useRef(null);
    const rotationRequestIdRef = useRef(0);

    // 加载可选行业列表
    useEffect(() => {
        const loadOptions = async () => {
            try {
                setLoadingOptions(true);
                const result = await getHotIndustries(50, 5, 'change_pct', 'desc');
                const nextOptions = (result || []).map(i => i.industry_name).filter(Boolean);
                setIndustryOptions(nextOptions);
                if (nextOptions.length > 0) {
                    setSelectedIndustries(prev => {
                        if (prev.length >= 2) return prev;
                        const merged = [...new Set([...prev, ...nextOptions.slice(0, 3)])];
                        return merged.slice(0, 5);
                    });
                }
            } catch (err) {
                console.error('Failed to load industry options:', err);
            } finally {
                setLoadingOptions(false);
            }
        };
        loadOptions();
    }, []);

    // 同步 initialIndustries 变化
    useEffect(() => {
        if (initialIndustries.length > 0) {
            setSelectedIndustries(prev => {
                const incoming = initialIndustries.filter(name => !prev.includes(name));
                if (incoming.length === 0) {
                    return prev;
                }
                const preserved = prev.filter(name => !incoming.includes(name));
                return [...incoming, ...preserved].slice(0, 5);
            });
        }
    }, [initialIndustries]);

    // 加载轮动数据
    const loadRotation = useCallback(async () => {
        if (selectedIndustries.length < 2) {
            message.warning('请至少选择 2 个行业进行对比');
            return;
        }
        const requestId = ++rotationRequestIdRef.current;
        if (rotationAbortRef.current) {
            rotationAbortRef.current.abort();
        }
        const currentAbort = new AbortController();
        rotationAbortRef.current = currentAbort;
        let isCanceled = false;
        try {
            setLoading(true);
            const result = await getIndustryRotation(selectedIndustries, selectedPeriods, {
                signal: currentAbort.signal
            });
            if (rotationAbortRef.current !== currentAbort || requestId !== rotationRequestIdRef.current) {
                return;
            }
            setRotationData(result);
        } catch (err) {
            if (err.name === 'CanceledError') {
                isCanceled = true;
                return;
            }
            console.error('Failed to load rotation data:', err);
            message.error('加载轮动数据失败');
        } finally {
            if (!isCanceled && rotationAbortRef.current === currentAbort && requestId === rotationRequestIdRef.current) {
                setLoading(false);
            }
        }
    }, [selectedIndustries, selectedPeriods]);

    // 选中行业变化时自动加载
    useEffect(() => {
        if (selectedIndustries.length >= 2) {
            loadRotation();
        }
    }, [selectedIndustries, loadRotation]);

    useEffect(() => () => {
        if (rotationAbortRef.current) {
            rotationAbortRef.current.abort();
        }
    }, []);

    const handleAddIndustry = (value) => {
        if (selectedIndustries.length >= 5) {
            message.warning('最多选择 5 个行业进行对比');
            return;
        }
        if (!selectedIndustries.includes(value)) {
            setSelectedIndustries(prev => [...prev, value]);
        }
    };

    const handleRemoveIndustry = (name) => {
        setSelectedIndustries(prev => prev.filter(i => i !== name));
    };

    const handleApplyPreset = (periods) => {
        setSelectedPeriods(periods);
    };

    const handlePeriodsChange = (nextPeriods) => {
        const sanitized = [...new Set((nextPeriods || []).map((value) => Number(value)).filter((value) => PERIOD_OPTIONS.includes(value)))].sort((left, right) => left - right);
        if (sanitized.length === 0) {
            message.warning('至少保留一个统计周期');
            return;
        }
        setSelectedPeriods(sanitized.slice(0, 4));
    };

    // 图表数据
    const chartData = (rotationData?.data || []).map(item => ({
        ...item,
        periodLabel: PERIOD_LABELS[item.period] || `${item.period}日`
    }));
    const strongestIndustry = chartData.length > 0
        ? selectedIndustries.reduce((best, name) => {
            const values = chartData.map((item) => Number(item[name] || 0));
            const score = values.reduce((sum, value) => sum + value, 0);
            if (!best || score > best.score) {
                return { name, score, latest: values[values.length - 1] || 0 };
            }
            return best;
        }, null)
        : null;
    const weakestIndustry = chartData.length > 0
        ? selectedIndustries.reduce((worst, name) => {
            const values = chartData.map((item) => Number(item[name] || 0));
            const score = values.reduce((sum, value) => sum + value, 0);
            if (!worst || score < worst.score) {
                return { name, score, latest: values[values.length - 1] || 0 };
            }
            return worst;
        }, null)
        : null;

    return (
        <Card
            data-testid="industry-rotation-card"
            title={
                <span>
                    <SwapOutlined style={{ marginRight: 8, color: '#722ed1' }} />
                    行业轮动对比
                </span>
            }
            extra={
                <Button
                    onClick={loadRotation}
                    icon={<ReloadOutlined />}
                    size="small"
                    disabled={selectedIndustries.length < 2}
                >
                    刷新
                </Button>
            }
        >
            {/* 行业选择器 */}
            <div style={{ marginBottom: 16 }}>
                <Space wrap>
                    <Select
                        placeholder="添加行业对比"
                        style={{ width: 180 }}
                        onChange={handleAddIndustry}
                        value={undefined}
                        size="small"
                        showSearch
                        loading={loadingOptions}
                        filterOption={(input, option) =>
                            option?.children?.toLowerCase().includes(input.toLowerCase())
                        }
                    >
                        {industryOptions
                            .filter(name => !selectedIndustries.includes(name))
                            .map(name => (
                                <Select.Option key={name} value={name}>{name}</Select.Option>
                            ))
                        }
                    </Select>
                    {selectedIndustries.map((name, idx) => (
                        <Tag
                            key={name}
                            color={COLORS[idx]}
                            closable
                            onClose={() => handleRemoveIndustry(name)}
                            style={{ fontSize: 13 }}
                        >
                            {name}
                        </Tag>
                    ))}
                </Space>
            </div>

            <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <Space wrap>
                    <Text type="secondary" style={{ fontSize: 12 }}>周期模板</Text>
                    {PERIOD_PRESETS.map((preset) => {
                        const active = preset.periods.length === selectedPeriods.length
                            && preset.periods.every((period, index) => period === selectedPeriods[index]);
                        return (
                            <Button
                                key={preset.key}
                                size="small"
                                type={active ? 'primary' : 'default'}
                                ghost={!active}
                                onClick={() => handleApplyPreset(preset.periods)}
                            >
                                {preset.label}
                            </Button>
                        );
                    })}
                </Space>
                <Select
                    mode="multiple"
                    size="small"
                    style={{ minWidth: 220 }}
                    value={selectedPeriods}
                    onChange={handlePeriodsChange}
                    maxTagCount={4}
                    placeholder="选择统计周期"
                    options={PERIOD_OPTIONS.map((period) => ({ value: period, label: PERIOD_LABELS[period] || `${period}日` }))}
                />
            </div>

            {(strongestIndustry || weakestIndustry) && (
                <div style={{
                    marginBottom: 16,
                    display: 'flex',
                    gap: 10,
                    flexWrap: 'wrap',
                }}>
                    {strongestIndustry && (
                        <div style={{
                            padding: '10px 12px',
                            borderRadius: 12,
                            background: 'linear-gradient(180deg, rgba(207,19,34,0.08) 0%, rgba(207,19,34,0.02) 100%)',
                            border: '1px solid rgba(207,19,34,0.12)',
                            minWidth: 180,
                        }}>
                            <div style={{ fontSize: 11, color: '#cf1322', fontWeight: 700, marginBottom: 4 }}>阶段最强</div>
                            <div style={{ fontSize: 14, fontWeight: 700 }}>{strongestIndustry.name}</div>
                            <div style={{ fontSize: 12, color: '#595959' }}>
                                最近周期 {strongestIndustry.latest >= 0 ? '+' : ''}{strongestIndustry.latest.toFixed(2)}%
                            </div>
                        </div>
                    )}
                    {weakestIndustry && (
                        <div style={{
                            padding: '10px 12px',
                            borderRadius: 12,
                            background: 'linear-gradient(180deg, rgba(56,158,13,0.08) 0%, rgba(56,158,13,0.02) 100%)',
                            border: '1px solid rgba(56,158,13,0.12)',
                            minWidth: 180,
                        }}>
                            <div style={{ fontSize: 11, color: '#389e0d', fontWeight: 700, marginBottom: 4 }}>阶段偏弱</div>
                            <div style={{ fontSize: 14, fontWeight: 700 }}>{weakestIndustry.name}</div>
                            <div style={{ fontSize: 12, color: '#595959' }}>
                                最近周期 {weakestIndustry.latest >= 0 ? '+' : ''}{weakestIndustry.latest.toFixed(2)}%
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* 图表 */}
            {loading ? (
                <div style={{ textAlign: 'center', padding: 40 }} data-testid="industry-rotation-loading">
                    <Spin />
                    <div style={{ marginTop: 12, color: '#999' }}>加载轮动数据...</div>
                </div>
            ) : selectedIndustries.length < 2 ? (
                <Empty
                    data-testid="industry-rotation-empty"
                    description="请选择至少 2 个行业进行对比"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
            ) : chartData.length === 0 ? (
                <Empty description="暂无轮动数据" data-testid="industry-rotation-empty" />
            ) : (
                <div data-testid="industry-rotation-chart">
                    <ResponsiveContainer width="100%" height={320}>
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                            <XAxis
                                dataKey="periodLabel"
                                tick={{ fontSize: 12 }}
                            />
                            <YAxis
                                tick={{ fontSize: 12 }}
                                tickFormatter={(v) => `${v}%`}
                            />
                            <RechartsTooltip
                                formatter={(value, name) => [`${value.toFixed(2)}%`, name]}
                                labelFormatter={(label) => `周期: ${label}`}
                            />
                            <Legend />
                            <ReferenceLine y={0} stroke="#d9d9d9" strokeDasharray="3 3" />
                            {selectedIndustries.map((name, idx) => (
                                <Line
                                    key={name}
                                    type="monotone"
                                    dataKey={name}
                                    stroke={COLORS[idx]}
                                    strokeWidth={2}
                                    dot={{ r: 4 }}
                                    activeDot={{ r: 6 }}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            )}

            {rotationData?.update_time && (
                <div style={{ textAlign: 'right', marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                        更新时间: {new Date(rotationData.update_time).toLocaleString()}
                    </Text>
                </div>
            )}
        </Card>
    );
};

export default IndustryRotationChart;
