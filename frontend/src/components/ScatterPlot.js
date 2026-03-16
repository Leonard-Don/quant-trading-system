import React, { useMemo, useState } from 'react';
import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
    ZAxis,
    Cell
} from 'recharts';
import { Card, Typography, Select, Space, Empty, Tag } from 'antd';
import {
    RiseOutlined,
    FallOutlined,
    AimOutlined
} from '@ant-design/icons';

const { Text } = Typography;

/**
 * 风险收益散点图组件
 * 用于策略/资产的风险收益对比分析
 */
const ScatterPlot = ({
    data,
    title = "风险收益分析",
    xAxisLabel = "波动率 (%)",
    yAxisLabel = "收益率 (%)",
    showQuadrants = true,
    colorBy = 'sharpe' // 'sharpe' | 'category' | 'none'
}) => {
    const [selectedPoint, setSelectedPoint] = useState(null);

    // 预设颜色列表
    const categoryColors = [
        '#1890ff', '#52c41a', '#722ed1', '#fa8c16',
        '#eb2f96', '#13c2c2', '#2f54eb', '#faad14'
    ];

    // 处理数据并计算颜色
    const processedData = useMemo(() => {
        if (!data || data.length === 0) return [];

        return data.map((item, index) => {
            let color;
            if (colorBy === 'sharpe') {
                // 根据夏普比率着色
                const sharpe = item.sharpe || 0;
                if (sharpe > 1) color = '#52c41a';
                else if (sharpe > 0.5) color = '#73d13d';
                else if (sharpe > 0) color = '#faad14';
                else color = '#ff4d4f';
            } else if (colorBy === 'category') {
                color = categoryColors[index % categoryColors.length];
            } else {
                color = '#1890ff';
            }

            return {
                ...item,
                color,
                size: item.size || 100
            };
        });
    }, [data, colorBy]);

    // 计算坐标轴范围
    const { xDomain, yDomain } = useMemo(() => {
        if (processedData.length === 0) {
            return { xDomain: [0, 30], yDomain: [-20, 40] };
        }

        const xValues = processedData.map(d => d.x);
        const yValues = processedData.map(d => d.y);

        const xMin = Math.min(0, ...xValues) * 1.1;
        const xMax = Math.max(...xValues) * 1.2;
        const yMin = Math.min(...yValues, 0) * 1.1;
        const yMax = Math.max(...yValues) * 1.2;

        return {
            xDomain: [Math.floor(xMin), Math.ceil(xMax)],
            yDomain: [Math.floor(yMin), Math.ceil(yMax)]
        };
    }, [processedData]);

    // 没有数据时显示空状态
    if (!data || data.length === 0) {
        return (
            <Card title={title} size="small">
                <Empty description="暂无分析数据" />
            </Card>
        );
    }

    // 自定义Tooltip
    const CustomTooltip = ({ active, payload }) => {
        if (active && payload && payload.length) {
            const point = payload[0].payload;
            return (
                <div style={{
                    backgroundColor: 'rgba(255, 255, 255, 0.98)',
                    padding: '12px 16px',
                    border: '1px solid #e8e8e8',
                    borderRadius: 8,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                    minWidth: 180
                }}>
                    <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
                        {point.name}
                    </Text>
                    <div style={{ marginBottom: 4 }}>
                        <Text style={{ color: '#666' }}>{xAxisLabel}: </Text>
                        <Text strong>{point.x?.toFixed(2)}%</Text>
                    </div>
                    <div style={{ marginBottom: 4 }}>
                        <Text style={{ color: '#666' }}>{yAxisLabel}: </Text>
                        <Text strong style={{ color: point.y >= 0 ? '#52c41a' : '#ff4d4f' }}>
                            {point.y >= 0 ? '+' : ''}{point.y?.toFixed(2)}%
                        </Text>
                    </div>
                    {point.sharpe !== undefined && (
                        <div>
                            <Text style={{ color: '#666' }}>夏普比率: </Text>
                            <Text strong>{point.sharpe?.toFixed(2)}</Text>
                        </div>
                    )}
                    {point.category && (
                        <Tag color="blue" style={{ marginTop: 8 }}>{point.category}</Tag>
                    )}
                </div>
            );
        }
        return null;
    };

    return (
        <Card
            title={
                <Space>
                    <AimOutlined />
                    {title}
                </Space>
            }
            size="small"
            extra={
                <Select
                    size="small"
                    value={colorBy}
                    style={{ width: 100 }}
                    options={[
                        { label: '按夏普', value: 'sharpe' },
                        { label: '按类别', value: 'category' },
                        { label: '无', value: 'none' }
                    ]}
                    disabled
                />
            }
        >
            <ResponsiveContainer width="100%" height={350}>
                <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />

                    <XAxis
                        type="number"
                        dataKey="x"
                        name={xAxisLabel}
                        domain={xDomain}
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => `${v}%`}
                        label={{
                            value: xAxisLabel,
                            position: 'bottom',
                            offset: 0,
                            style: { fontSize: 12, fill: '#666' }
                        }}
                    />

                    <YAxis
                        type="number"
                        dataKey="y"
                        name={yAxisLabel}
                        domain={yDomain}
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => `${v}%`}
                        label={{
                            value: yAxisLabel,
                            angle: -90,
                            position: 'insideLeft',
                            style: { fontSize: 12, fill: '#666' }
                        }}
                    />

                    <ZAxis type="number" dataKey="size" range={[60, 200]} />

                    <Tooltip content={<CustomTooltip />} />

                    {/* 象限参考线 */}
                    {showQuadrants && (
                        <>
                            <ReferenceLine x={0} stroke="#999" strokeDasharray="3 3" />
                            <ReferenceLine y={0} stroke="#999" strokeDasharray="3 3" />
                        </>
                    )}

                    <Scatter
                        name="策略"
                        data={processedData}
                        onClick={(data) => setSelectedPoint(data)}
                    >
                        {processedData.map((entry, index) => (
                            <Cell
                                key={`cell-${index}`}
                                fill={entry.color}
                                stroke={selectedPoint?.name === entry.name ? '#000' : entry.color}
                                strokeWidth={selectedPoint?.name === entry.name ? 2 : 1}
                                style={{ cursor: 'pointer' }}
                            />
                        ))}
                    </Scatter>
                </ScatterChart>
            </ResponsiveContainer>

            {/* 图例和说明 */}
            {colorBy === 'sharpe' && (
                <div style={{
                    display: 'flex',
                    justifyContent: 'center',
                    gap: 16,
                    marginTop: 8,
                    flexWrap: 'wrap'
                }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#52c41a' }} />
                        <Text style={{ fontSize: 11 }}>夏普 &gt; 1</Text>
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#73d13d' }} />
                        <Text style={{ fontSize: 11 }}>0.5 - 1</Text>
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#faad14' }} />
                        <Text style={{ fontSize: 11 }}>0 - 0.5</Text>
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ff4d4f' }} />
                        <Text style={{ fontSize: 11 }}>&lt; 0</Text>
                    </span>
                </div>
            )}

            {/* 选中点详情 */}
            {selectedPoint && (
                <div style={{
                    marginTop: 12,
                    padding: '8px 12px',
                    background: '#fafafa',
                    borderRadius: 6,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                }}>
                    <Text strong>{selectedPoint.name}</Text>
                    <Space>
                        <span>
                            {selectedPoint.y >= 0 ? <RiseOutlined style={{ color: '#52c41a' }} /> : <FallOutlined style={{ color: '#ff4d4f' }} />}
                            <Text style={{ marginLeft: 4 }}>{selectedPoint.y?.toFixed(2)}%</Text>
                        </span>
                        <Text type="secondary">|</Text>
                        <Text>风险: {selectedPoint.x?.toFixed(2)}%</Text>
                    </Space>
                </div>
            )}
        </Card>
    );
};

export default ScatterPlot;
