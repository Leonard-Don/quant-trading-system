import React, { useState, useEffect } from 'react';
import { Row, Col, Card, Input, Alert, Typography } from 'antd';
import { getCorrelationAnalysis } from '../services/api';

const { Title, Text } = Typography;

const CorrelationPanel = ({ symbol }) => {
    const [targetSymbols, setTargetSymbols] = useState(symbol || 'AAPL');
    const [correlationData, setCorrelationData] = useState(null);
    const [cLoading, setCLoading] = useState(false);
    const [cError, setCError] = useState(null);

    // Pre-fill with some peers if available, or just the current symbol
    useEffect(() => {
        if (symbol && !targetSymbols.includes(symbol)) {
            setTargetSymbols(prev => prev ? `${prev}, ${symbol}` : symbol);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [symbol]);

    const fetchCorrelation = async () => {
        const symbols = targetSymbols.split(/[,，\s]+/).filter(s => s.trim());
        if (symbols.length < 2) {
            setCError('请至少输入2个股票代码进行比较');
            return;
        }

        setCLoading(true);
        setCError(null);
        try {
            const result = await getCorrelationAnalysis(symbols);
            setCorrelationData(result);
        } catch (err) {
            setCError('分析失败: ' + (err.response?.data?.detail || err.message));
        } finally {
            setCLoading(false);
        }
    };

    return (
        <Row gutter={[16, 16]}>
            <Col span={24}>
                <Card title="多股票相关性分析" bordered={false}>
                    <div style={{ marginBottom: 16 }}>
                        <Text type="secondary">输入股票代码（用逗号分隔，如: AAPL, MSFT, GOOGL, TSLA）</Text>
                        <Input.Search
                            placeholder="AAPL, MSFT, GOOGL"
                            value={targetSymbols}
                            onChange={e => setTargetSymbols(e.target.value)}
                            enterButton="开始分析"
                            size="large"
                            onSearch={fetchCorrelation}
                            loading={cLoading}
                            style={{ marginTop: 8 }}
                        />
                    </div>

                    {cError && <Alert message={cError} type="error" showIcon style={{ marginBottom: 16 }} />}

                    {correlationData && (
                        <>
                            <Alert
                                message={correlationData.interpretation.level === 'very_high' ? '高度相关' : correlationData.interpretation.level === 'high' ? '较高相关' : '相关性适中'}
                                description={correlationData.interpretation.description}
                                type={correlationData.interpretation.level.includes('high') ? 'warning' : 'info'}
                                showIcon
                                style={{ marginBottom: 24 }}
                            />

                            <Title level={5}>相关性矩阵热力图</Title>
                            <div style={{ overflowX: 'auto', paddingBottom: 10 }}>
                                <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 500 }}>
                                    <thead>
                                        <tr>
                                            <th style={{ padding: 8 }}></th>
                                            {correlationData.symbols.map(s => (
                                                <th key={s} style={{ padding: 8, textAlign: 'center' }}>{s}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {correlationData.symbols.map((rowSymbol, i) => (
                                            <tr key={rowSymbol}>
                                                <td style={{ padding: 8, fontWeight: 'bold' }}>{rowSymbol}</td>
                                                {correlationData.symbols.map((colSymbol, j) => {
                                                    const item = correlationData.correlation_matrix.find(
                                                        x => x.symbol1 === rowSymbol && x.symbol2 === colSymbol
                                                    );
                                                    const val = item ? item.correlation : (rowSymbol === colSymbol ? 1 : 0);
                                                    const opacity = Math.abs(val);
                                                    const color = val > 0
                                                        ? `rgba(245, 34, 45, ${opacity})` // Red for positive
                                                        : `rgba(82, 196, 26, ${opacity})`; // Green for negative (diversification)

                                                    return (
                                                        <td key={colSymbol} style={{
                                                            padding: 12,
                                                            textAlign: 'center',
                                                            backgroundColor: color,
                                                            color: opacity > 0.5 ? '#fff' : '#000',
                                                            border: '1px solid #f0f0f0'
                                                        }}>
                                                            {val.toFixed(2)}
                                                        </td>
                                                    );
                                                })}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </>
                    )}
                </Card>
            </Col>
        </Row>
    );
};

export default CorrelationPanel;
