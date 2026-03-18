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
const PERIOD_LABELS = { 1: '1日', 3: '3日', 5: '5日', 10: '10日', 20: '20日' };

/**
 * 行业轮动对比图组件
 * 展示多个行业在不同时间周期的涨跌幅趋势对比
 */
const IndustryRotationChart = ({ initialIndustries = [] }) => {
    const [selectedIndustries, setSelectedIndustries] = useState(initialIndustries);
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
            const result = await getIndustryRotation(selectedIndustries, {
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
    }, [selectedIndustries]);

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

    // 图表数据
    const chartData = (rotationData?.data || []).map(item => ({
        ...item,
        periodLabel: PERIOD_LABELS[item.period] || `${item.period}日`
    }));

    return (
        <Card
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

            {/* 图表 */}
            {loading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                    <Spin />
                    <div style={{ marginTop: 12, color: '#999' }}>加载轮动数据...</div>
                </div>
            ) : selectedIndustries.length < 2 ? (
                <Empty
                    description="请选择至少 2 个行业进行对比"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
            ) : chartData.length === 0 ? (
                <Empty description="暂无轮动数据" />
            ) : (
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
