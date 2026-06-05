/**
 * Industry-comparison tab content for MarketAnalysis (layer-3 split).
 * Pure presentational; markup preserved verbatim from the original
 * inline `industryContent` memo block.
 */
import {
    Card,
    Row,
    Col,
    Typography,
    Alert,
    Table,
    Statistic,
    Empty,
    Spin,
} from 'antd';
import { BankOutlined } from '@ant-design/icons';
import {
    DISPLAY_EMPTY,
    formatDisplayNumber,
    formatDisplayPercent,
} from '../../utils/marketAnalysisFormatters';

const { Text } = Typography;

const IndustryTab = ({ loadingTab, errorTab, industryData }) => {
    if (loadingTab.industry && !industryData) {
        return <div style={{ padding: 24, textAlign: 'center' }}><Spin /></div>;
    }
    if (errorTab.industry) {
        return <Alert message="错误" description={errorTab.industry} type="error" showIcon />;
    }
    if (!industryData) return <Empty description="暂无行业对比数据" />;

    const { target, peers, industry_avg, industry, sector } = industryData;

    const columns = [
        { title: '股票', dataIndex: 'symbol', key: 'symbol', render: (t, r) => <Text strong={r.symbol === target?.symbol}>{t}</Text> },
        { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
        { title: 'PE', dataIndex: 'pe_ratio', key: 'pe_ratio', render: v => formatDisplayNumber(v) },
        { title: '营收增长', dataIndex: 'revenue_growth', key: 'revenue_growth', render: v => formatDisplayPercent(v) },
        { title: '利润率', dataIndex: 'profit_margin', key: 'profit_margin', render: v => formatDisplayPercent(v) },
    ];

    const tableData = target ? [target, ...(peers || [])] : (peers || []);

    return (
        <Row gutter={[16, 16]}>
            <Col span={24}>
                <Alert
                    message={`行业: ${industry || DISPLAY_EMPTY} | 板块: ${sector || DISPLAY_EMPTY}`}
                    description={`${target?.symbol || DISPLAY_EMPTY} 在同行业中 PE 排名第 ${target?.pe_rank || DISPLAY_EMPTY} 位，增长排名第 ${target?.growth_rank || DISPLAY_EMPTY} 位`}
                    type="info"
                    showIcon
                    icon={<BankOutlined />}
                />
            </Col>
            <Col xs={24} md={8}>
                <Card title="行业均值">
                    <Statistic title="平均 PE" value={formatDisplayNumber(industry_avg?.pe_ratio)} />
                    <Statistic title="平均增长率" value={formatDisplayPercent(industry_avg?.revenue_growth)} style={{ marginTop: 16 }} />
                    <Statistic title="平均利润率" value={formatDisplayPercent(industry_avg?.profit_margin)} style={{ marginTop: 16 }} />
                </Card>
            </Col>
            <Col xs={24} md={16}>
                <Card title="同行业公司对比">
                    <Table
                        dataSource={tableData}
                        columns={columns}
                        rowKey="symbol"
                        pagination={false}
                        size="small"
                    />
                </Card>
            </Col>
        </Row>
    );
};

export default IndustryTab;
