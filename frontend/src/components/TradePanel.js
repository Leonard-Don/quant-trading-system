
import React, { useState, useEffect } from 'react';
import {
    Card,
    Row,
    Col,
    InputNumber,
    Button,
    Table,
    Tabs,
    Statistic,
    Tag,
    message,
    Space,
    Typography,
    Modal,
    Popconfirm
} from 'antd';
import {
    HistoryOutlined,
    ReloadOutlined,
    ArrowUpOutlined,
    ArrowDownOutlined
} from '@ant-design/icons';
import { getPortfolio, executeTrade, getTradeHistory, resetAccount } from '../services/api';

const { Text } = Typography;

const TradePanel = ({ defaultSymbol, visible, onClose, onSuccess }) => {
    const [portfolio, setPortfolio] = useState(null);
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(false);
    const [action, setAction] = useState('BUY');
    const [symbol, setSymbol] = useState(defaultSymbol || 'AAPL');
    const [quantity, setQuantity] = useState(100);
    const [price, setPrice] = useState(null); // Optional limit price

    useEffect(() => {
        if (visible) {
            fetchPortfolio();
            fetchHistory();
            if (defaultSymbol) {
                setSymbol(defaultSymbol);
                fetchCurrentPrice(defaultSymbol);
            }
        }
    }, [visible, defaultSymbol]);

    // Fetch data
    const fetchPortfolio = async () => {
        setLoading(true);
        try {
            const response = await getPortfolio();
            if (response.success) {
                setPortfolio(response.data);
            }
        } catch (error) {
            message.error('无法获取投资组合数据');
        } finally {
            setLoading(false);
        }
    };

    const fetchHistory = async () => {
        try {
            const response = await getTradeHistory();
            if (response.success) {
                setHistory(response.data);
            }
        } catch (error) {
            console.error(error);
        }
    };

    const fetchCurrentPrice = async (sym) => {
        // This assumes specific market data API or passed props. 
        // Simplified: uses the price from initial props or fetches
        // For now we just reset price to allow market order
        setPrice(null);
    };

    const handleTrade = async () => {
        if (!symbol || !quantity) {
            message.warning('请输入股票代码和数量');
            return;
        }

        setLoading(true);
        try {
            const response = await executeTrade(symbol, action, quantity, price);
            if (response.success) {
                message.success(`交易成功: ${action} ${quantity} ${symbol}`);
                fetchPortfolio();
                fetchHistory();
                if (onSuccess) onSuccess();
                // Optional: Close modal on success?
                // onClose();
            }
        } catch (error) {
            message.error(`交易失败: ${error.response?.data?.detail || error.message}`);
        } finally {
            setLoading(false);
        }
    };

    const handleReset = async () => {
        try {
            await resetAccount();
            message.success('账户已重置');
            fetchPortfolio();
            fetchHistory();
        } catch (error) {
            message.error('重置失败');
        }
    };

    // Columns for Positions Table
    const positionColumns = [
        { title: '代码', dataIndex: 'symbol', key: 'symbol' },
        { title: '持仓量', dataIndex: 'quantity', key: 'quantity' },
        {
            title: '成本均价',
            dataIndex: 'avg_price',
            key: 'avg_price',
            render: (val) => `$${val.toFixed(2)}`
        },
        {
            title: '现价',
            dataIndex: 'current_price',
            key: 'current_price',
            render: (val) => `$${val.toFixed(2)}`
        },
        {
            title: '市值',
            dataIndex: 'market_value',
            key: 'market_value',
            render: (val) => `$${val.toFixed(2)}`
        },
        {
            title: '浮动盈亏',
            dataIndex: 'unrealized_pnl',
            key: 'unrealized_pnl',
            render: (val, record) => (
                <span style={{ color: val >= 0 ? '#52c41a' : '#ff4d4f' }}>
                    ${val.toFixed(2)} ({record.unrealized_pnl_percent.toFixed(2)}%)
                </span>
            )
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Button
                    size="small"
                    danger
                    onClick={() => {
                        setSymbol(record.symbol);
                        setAction('SELL');
                        setQuantity(record.quantity);
                    }}
                >
                    卖出
                </Button>
            )
        }
    ];

    // Columns for History Table
    const historyColumns = [
        { title: '时间', dataIndex: 'timestamp', key: 'timestamp', render: (val) => new Date(val).toLocaleString() },
        {
            title: '方向',
            dataIndex: 'action',
            key: 'action',
            render: (val) => <Tag color={val === 'BUY' ? 'blue' : 'orange'}>{val}</Tag>
        },
        { title: '代码', dataIndex: 'symbol', key: 'symbol' },
        { title: '数量', dataIndex: 'quantity', key: 'quantity' },
        { title: '价格', dataIndex: 'price', key: 'price', render: (val) => `$${val.toFixed(2)}` },
        { title: '总额', dataIndex: 'total_amount', key: 'total_amount', render: (val) => `$${val.toFixed(2)}` },
        {
            title: '盈亏',
            dataIndex: 'pnl',
            key: 'pnl',
            render: (val) => val ? (
                <span style={{ color: val >= 0 ? '#52c41a' : '#ff4d4f' }}>
                    ${val.toFixed(2)}
                </span>
            ) : '-'
        }
    ];

    const actionTabItems = [
        { key: 'BUY', label: '买入' },
        { key: 'SELL', label: '卖出' }
    ];

    const portfolioTabItems = [
        {
            key: 'positions',
            label: `当前持仓 (${portfolio?.positions?.length || 0})`,
            children: (
                <Table
                    dataSource={portfolio?.positions || []}
                    columns={positionColumns}
                    rowKey="symbol"
                    pagination={false}
                    size="small"
                />
            )
        },
        {
            key: 'history',
            label: '交易历史',
            children: (
                <Table
                    dataSource={history}
                    columns={historyColumns}
                    rowKey="id"
                    pagination={{ pageSize: 5 }}
                    size="small"
                />
            )
        }
    ];

    return (
        <Modal
            title="模拟交易终端 (Paper Trading)"
            open={visible}
            onCancel={onClose}
            footer={null}
            width={1000}
            style={{ top: 20 }}
        >
            <Row gutter={[16, 16]}>
                {/* Left: Order Entry */}
                <Col span={8}>
                    <Card title="下单" bordered={false} style={{ background: 'var(--bg-tertiary)' }}>
                        <Space direction="vertical" style={{ width: '100%' }} size="middle">
                            <div>
                                <Text type="secondary">股票代码</Text>
                                <div style={{ fontWeight: 'bold', fontSize: 16 }}>{symbol}</div>
                            </div>

                            <Tabs activeKey={action} onChange={setAction} type="card" items={actionTabItems} />

                            <div>
                                <Text>数量</Text>
                                <InputNumber
                                    style={{ width: '100%' }}
                                    min={1}
                                    value={quantity}
                                    onChange={setQuantity}
                                />
                            </div>

                            <div>
                                <Text>价格 (留空为市价单)</Text>
                                <InputNumber
                                    style={{ width: '100%' }}
                                    min={0.01}
                                    step={0.01}
                                    value={price}
                                    onChange={setPrice}
                                    placeholder="市价 Market Price"
                                />
                            </div>

                            <Button
                                type="primary"
                                block
                                size="large"
                                loading={loading}
                                danger={action === 'SELL'}
                                onClick={handleTrade}
                                style={{ marginTop: 10 }}
                            >
                                {action === 'BUY' ? '买入 Buy' : '卖出 Sell'}
                            </Button>
                        </Space>
                    </Card>

                    {/* Account Summary Mini */}
                    {portfolio && (
                        <Card size="small" style={{ marginTop: 16 }}>
                            <Statistic
                                title="账户余额 (Cash)"
                                value={portfolio.balance}
                                precision={2}
                                prefix="$"
                            />
                            <Statistic
                                title="总资产 (Equity)"
                                value={portfolio.total_equity}
                                precision={2}
                                prefix="$"
                                style={{ marginTop: 10 }}
                            />
                        </Card>
                    )}
                </Col>

                {/* Right: Portfolio & History */}
                <Col span={16}>
                    {portfolio && (
                        <Row gutter={16} style={{ marginBottom: 16 }}>
                            <Col span={8}>
                                <Statistic
                                    title="总盈亏 (P&L)"
                                    value={portfolio.total_pnl}
                                    precision={2}
                                    valueStyle={{ color: portfolio.total_pnl >= 0 ? '#52c41a' : '#ff4d4f' }}
                                    prefix={portfolio.total_pnl >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                                    suffix={`(${portfolio.total_pnl_percent.toFixed(2)}%)`}
                                />
                            </Col>
                            <Col span={8}>
                                <Statistic title="交易次数" value={portfolio.trade_count} prefix={<HistoryOutlined />} />
                            </Col>
                            <Col span={8} style={{ textAlign: 'right' }}>
                                <Popconfirm title="确定重置账户吗?" onConfirm={handleReset}>
                                    <Button icon={<ReloadOutlined />}>重置账户</Button>
                                </Popconfirm>
                            </Col>
                        </Row>
                    )}

                    <Tabs defaultActiveKey="positions" items={portfolioTabItems} />
                </Col>
            </Row>
        </Modal>
    );
};

export default TradePanel;
