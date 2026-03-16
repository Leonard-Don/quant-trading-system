import React, { useState } from 'react';
import {
    Card,
    Input,
    Button,
    Row,
    Col,
    Tag,
    Space,
    Statistic,
    Alert,
    List,
    Tooltip,
    Spin
} from 'antd';
import {
    StockOutlined,
    PlusOutlined,
    ThunderboltOutlined,
    InfoCircleOutlined
} from '@ant-design/icons';
import { getCorrelationAnalysis } from '../services/api';



const CorrelationAnalysis = () => {
    const [symbols, setSymbols] = useState(['AAPL', 'GOOGL', 'MSFT']);
    const [inputValue, setInputValue] = useState('');
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    const addSymbol = (symbol) => {
        const upper = symbol.toUpperCase().trim();
        if (upper && !symbols.includes(upper) && symbols.length < 10) {
            setSymbols([...symbols, upper]);
            setInputValue('');
        }
    };

    const removeSymbol = (symbol) => {
        setSymbols(symbols.filter(s => s !== symbol));
    };

    const analyzeCorrelation = async () => {
        if (symbols.length < 2) {
            setError('至少需要2只股票进行相关性分析');
            return;
        }

        setLoading(true);
        setError(null);
        try {
            const result = await getCorrelationAnalysis(symbols, 90);
            setData(result);
        } catch (err) {
            console.error('Correlation analysis failed:', err);
            setError('分析失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    // 获取相关性颜色
    const getCorrelationColor = (value) => {
        if (value >= 0.7) return '#ff4d4f';  // 高正相关 - 红色
        if (value >= 0.4) return '#ffa940';  // 中正相关 - 橙色
        if (value >= 0.1) return '#fadb14';  // 低正相关 - 黄色
        if (value >= -0.1) return '#d9d9d9'; // 无相关 - 灰色
        if (value >= -0.4) return '#73d13d'; // 低负相关 - 绿色
        if (value >= -0.7) return '#40a9ff'; // 中负相关 - 蓝色
        return '#722ed1';                    // 高负相关 - 紫色
    };

    // 获取相关性等级颜色
    const getLevelColor = (level) => {
        const colors = {
            'very_high': 'error',
            'high': 'warning',
            'moderate': 'processing',
            'low': 'success',
            'very_low': 'default'
        };
        return colors[level] || 'default';
    };

    // 渲染热力图
    const renderHeatmap = () => {
        if (!data || !data.symbols) return null;

        const { symbols: validSymbols, correlation_matrix } = data;
        const n = validSymbols.length;

        // 构建矩阵数据
        const matrix = {};
        correlation_matrix.forEach(item => {
            if (!matrix[item.symbol1]) matrix[item.symbol1] = {};
            matrix[item.symbol1][item.symbol2] = item.correlation;
        });

        return (
            <div style={{ overflowX: 'auto' }}>
                <table style={{
                    borderCollapse: 'collapse',
                    width: '100%',
                    minWidth: n * 80
                }}>
                    <thead>
                        <tr>
                            <th style={{
                                padding: '10px',
                                background: 'var(--bg-tertiary)',
                                borderRadius: '8px 0 0 0'
                            }}></th>
                            {validSymbols.map((sym, i) => (
                                <th key={sym} style={{
                                    padding: '10px',
                                    background: 'var(--bg-tertiary)',
                                    color: 'var(--text-primary)',
                                    fontWeight: 600,
                                    borderRadius: i === n - 1 ? '0 8px 0 0' : 0
                                }}>
                                    {sym}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {validSymbols.map((sym1, i) => (
                            <tr key={sym1}>
                                <td style={{
                                    padding: '10px',
                                    background: 'var(--bg-tertiary)',
                                    color: 'var(--text-primary)',
                                    fontWeight: 600,
                                    borderRadius: i === n - 1 ? '0 0 0 8px' : 0
                                }}>
                                    {sym1}
                                </td>
                                {validSymbols.map((sym2, j) => {
                                    const value = matrix[sym1]?.[sym2] || 0;
                                    const isself = sym1 === sym2;
                                    return (
                                        <td key={sym2} style={{
                                            padding: '8px',
                                            textAlign: 'center',
                                            background: isself ? 'var(--bg-secondary)' : getCorrelationColor(value),
                                            color: isself ? 'var(--text-muted)' : '#fff',
                                            fontWeight: 500,
                                            transition: 'all 0.3s',
                                            borderRadius: i === n - 1 && j === n - 1 ? '0 0 8px 0' : 0
                                        }}>
                                            <Tooltip title={`${sym1} vs ${sym2}: ${(value * 100).toFixed(1)}% 相关`}>
                                                {isself ? '-' : value.toFixed(2)}
                                            </Tooltip>
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    return (
        <div>
            <Card
                title={
                    <Space>
                        <StockOutlined />
                        <span>多股票相关性分析</span>
                    </Space>
                }
                extra={
                    <Tooltip title="分析股票价格走势的相关性，帮助构建分散化投资组合">
                        <InfoCircleOutlined style={{ color: 'var(--text-muted)' }} />
                    </Tooltip>
                }
            >
                {/* 股票选择区 */}
                <div style={{ marginBottom: 16 }}>
                    <div style={{ marginBottom: 8 }}>
                        <Space wrap>
                            {symbols.map(sym => (
                                <Tag
                                    key={sym}
                                    closable
                                    onClose={() => removeSymbol(sym)}
                                    style={{
                                        padding: '4px 8px',
                                        fontSize: '14px'
                                    }}
                                >
                                    {sym}
                                </Tag>
                            ))}
                            {symbols.length < 10 && (
                                <Input
                                    placeholder="添加股票..."
                                    value={inputValue}
                                    onChange={(e) => setInputValue(e.target.value)}
                                    onPressEnter={(e) => addSymbol(e.target.value)}
                                    style={{ width: 120 }}
                                    suffix={
                                        <PlusOutlined
                                            onClick={() => addSymbol(inputValue)}
                                            style={{ cursor: 'pointer' }}
                                        />
                                    }
                                />
                            )}
                        </Space>
                    </div>
                    <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        onClick={analyzeCorrelation}
                        loading={loading}
                        disabled={symbols.length < 2}
                    >
                        分析相关性
                    </Button>
                </div>

                {error && (
                    <Alert
                        message={error}
                        type="error"
                        showIcon
                        style={{ marginBottom: 16 }}
                        closable
                        onClose={() => setError(null)}
                    />
                )}

                {loading && (
                    <div style={{ textAlign: 'center', padding: '40px 0' }}>
                        <Spin size="large" />
                        <div style={{ marginTop: 12, color: '#8c8c8c' }}>正在分析相关性...</div>
                    </div>
                )}

                {data && !loading && (
                    <>
                        {/* 汇总统计 */}
                        <Row gutter={16} style={{ marginBottom: 16 }}>
                            <Col span={8}>
                                <Card size="small">
                                    <Statistic
                                        title="平均相关性"
                                        value={data.average_correlation}
                                        precision={2}
                                        valueStyle={{
                                            color: data.average_correlation > 0.5 ?
                                                'var(--accent-warning)' : 'var(--accent-success)'
                                        }}
                                    />
                                </Card>
                            </Col>
                            <Col span={8}>
                                <Card size="small">
                                    <Statistic
                                        title="分析数据点"
                                        value={data.data_points}
                                        suffix="天"
                                    />
                                </Card>
                            </Col>
                            <Col span={8}>
                                <Card size="small">
                                    <div style={{ marginBottom: 4 }}>
                                        <span style={{ color: 'var(--text-secondary)' }}>分散化评估</span>
                                    </div>
                                    <Tag color={getLevelColor(data.interpretation?.level)}>
                                        {data.interpretation?.level === 'very_low' ? '优秀' :
                                            data.interpretation?.level === 'low' ? '良好' :
                                                data.interpretation?.level === 'moderate' ? '一般' :
                                                    data.interpretation?.level === 'high' ? '较差' : '很差'}
                                    </Tag>
                                </Card>
                            </Col>
                        </Row>

                        {/* 解读 */}
                        <Alert
                            message="投资建议"
                            description={data.interpretation?.description}
                            type={data.interpretation?.level === 'low' ||
                                data.interpretation?.level === 'very_low' ? 'success' : 'warning'}
                            showIcon
                            style={{ marginBottom: 16 }}
                        />

                        {/* 热力图 */}
                        <Card title="相关性矩阵" size="small" style={{ marginBottom: 16 }}>
                            {renderHeatmap()}
                            <div style={{
                                marginTop: 12,
                                display: 'flex',
                                justifyContent: 'center',
                                gap: 8,
                                flexWrap: 'wrap'
                            }}>
                                <Tag color="#722ed1">-1.0 高负相关</Tag>
                                <Tag color="#40a9ff">中负相关</Tag>
                                <Tag color="#73d13d">低负相关</Tag>
                                <Tag color="#d9d9d9">无相关</Tag>
                                <Tag color="#fadb14">低正相关</Tag>
                                <Tag color="#ffa940">中正相关</Tag>
                                <Tag color="#ff4d4f">+1.0 高正相关</Tag>
                            </div>
                        </Card>

                        {/* Top相关性 */}
                        {data.top_correlations && data.top_correlations.length > 0 && (
                            <Card title="相关性排名" size="small">
                                <List
                                    size="small"
                                    dataSource={data.top_correlations}
                                    renderItem={(item, index) => (
                                        <List.Item>
                                            <Space>
                                                <Tag>{index + 1}</Tag>
                                                <span style={{ fontWeight: 500 }}>{item.pair}</span>
                                            </Space>
                                            <Tag
                                                color={getCorrelationColor(item.correlation)}
                                                style={{ marginLeft: 'auto' }}
                                            >
                                                {(item.correlation * 100).toFixed(1)}%
                                            </Tag>
                                        </List.Item>
                                    )}
                                />
                            </Card>
                        )}
                    </>
                )}
            </Card>
        </div>
    );
};

export default CorrelationAnalysis;
