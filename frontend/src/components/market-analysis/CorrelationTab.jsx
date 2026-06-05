/**
 * Correlation tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `correlationContent` memo block.
 */
import {
    Card,
    Row,
    Col,
    Tag,
    Alert,
    Space,
    Table,
    Empty,
    Spin,
} from 'antd';
import { LineChartOutlined } from '@ant-design/icons';

const CorrelationTab = ({ loadingTab, errorTab, correlationData }) => {
    if (loadingTab.correlation && !correlationData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.correlation) {
        return <Alert message="错误" description={errorTab.correlation} type="error" showIcon />;
    }
    if (!correlationData) return <Empty description="暂无相关性分析数据" />;

    // API 返回格式: { correlation_matrix: [{symbol1, symbol2, correlation}, ...], symbols: [...] }
    const rawMatrix = correlationData.correlation_matrix || [];
    const symbols = correlationData.symbols || [];

    // 构建相关性查找表
    const correlationMap = {};
    rawMatrix.forEach(item => {
        if (!correlationMap[item.symbol1]) correlationMap[item.symbol1] = {};
        correlationMap[item.symbol1][item.symbol2] = item.correlation;
    });

    const getCorrelationColor = (value) => {
        if (value === undefined || value === null) return '#d9d9d9';
        if (value >= 0.7) return '#52c41a';
        if (value >= 0.4) return '#faad14';
        if (value >= 0) return '#d9d9d9';
        if (value >= -0.4) return '#ffa39e';
        return '#ff4d4f';
    };

    const columns = [
        { title: '', dataIndex: 'symbol', key: 'symbol', fixed: 'left', width: 80 },
        ...symbols.map(s => ({
            title: s,
            dataIndex: s,
            key: s,
            width: 80,
            render: (v) => (
                <div style={{
                    background: getCorrelationColor(v),
                    padding: '4px 8px',
                    borderRadius: 4,
                    textAlign: 'center',
                    color: Math.abs(v || 0) > 0.5 ? '#fff' : '#000'
                }}>
                    {v !== undefined ? v.toFixed(2) : '-'}
                </div>
            )
        }))
    ];

    const tableData = symbols.map(s1 => {
        const row = { symbol: s1 };
        symbols.forEach(s2 => {
            row[s2] = correlationMap[s1]?.[s2];
        });
        return row;
    });

    return (
        <Row gutter={[16, 16]}>
            <Col span={24}>
                <Alert
                    message="股票相关性分析"
                    description="显示选定股票之间的价格走势相关性。相关系数范围 -1 到 1，正值表示正相关，负值表示负相关。"
                    type="info"
                    showIcon
                    icon={<LineChartOutlined />}
                />
            </Col>
            <Col span={24}>
                <Card title="相关性矩阵">
                    <Table
                        dataSource={tableData}
                        columns={columns}
                        rowKey="symbol"
                        pagination={false}
                        scroll={{ x: 'max-content' }}
                        size="small"
                    />
                </Card>
            </Col>
            <Col span={24}>
                <Card title="相关性图例">
                    <Space>
                        <Tag color="#52c41a">强正相关 (≥0.7)</Tag>
                        <Tag color="#faad14">中等正相关 (0.4~0.7)</Tag>
                        <Tag color="#d9d9d9">弱相关 (0.0~0.4)</Tag>
                        <Tag color="#ffa39e">中等负相关 (-0.4~0)</Tag>
                        <Tag color="#ff4d4f">强负相关 (≤-0.4)</Tag>
                    </Space>
                </Card>
            </Col>
        </Row>
    );
};

export default CorrelationTab;
