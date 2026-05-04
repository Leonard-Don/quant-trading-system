/**
 * Paper Trading workspace (v0).
 *
 * Manual ledger: user submits BUY/SELL orders that fill at the
 * supplied price; backend persists positions & orders per profile.
 * Mark-to-market PnL is computed client-side using getMultipleQuotes
 * polling (backend doesn't push prices in v0).
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    App as AntdApp,
    Button,
    Card,
    Col,
    Empty,
    Form,
    Input,
    InputNumber,
    Modal,
    Popconfirm,
    Row,
    Segmented,
    Space,
    Statistic,
    Table,
    Tag,
    Tooltip,
    Typography,
} from 'antd';
import {
    DollarOutlined,
    LineChartOutlined,
    ReloadOutlined,
    ThunderboltOutlined,
} from '@ant-design/icons';

import {
    getMultipleQuotes,
    getPaperAccount,
    listPaperOrders,
    resetPaperAccount,
    submitPaperOrder,
} from '../services/api';
import { consumePaperPrefill } from '../utils/paperTradingPrefill';

const { Title, Text } = Typography;

const QUOTE_POLL_MS = 5000;

const formatMoney = (value) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return `$${value.toFixed(2)}`;
};

const formatPercent = (value) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return `${(value * 100).toFixed(2)}%`;
};

const computeMarkToMarket = (positions, quoteMap) => {
    let unrealized = 0;
    let marketValue = 0;
    const enriched = positions.map((position) => {
        const quote = quoteMap[position.symbol];
        const lastPrice = typeof quote?.price === 'number' && Number.isFinite(quote.price)
            ? quote.price
            : null;
        const value = lastPrice != null ? lastPrice * position.quantity : null;
        const pnl = lastPrice != null
            ? (lastPrice - position.avg_cost) * position.quantity
            : null;
        if (value != null) marketValue += value;
        if (pnl != null) unrealized += pnl;
        return {
            ...position,
            last_price: lastPrice,
            market_value: value,
            unrealized_pnl: pnl,
        };
    });
    return { positions: enriched, unrealized, marketValue };
};

const PaperTradingPanel = () => {
    const { message } = AntdApp.useApp();
    const [account, setAccount] = useState(null);
    const [orders, setOrders] = useState([]);
    const [quoteMap, setQuoteMap] = useState({});
    const [submitting, setSubmitting] = useState(false);
    const [resetting, setResetting] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);
    const [prefillSource, setPrefillSource] = useState(null);
    const [orderForm] = Form.useForm();

    const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

    // One-shot consume of the cross-workspace handoff (e.g. from a backtest
    // result panel). We hold off until the account has loaded so the Form
    // element is mounted (the panel renders an <Empty> placeholder before
    // that, and setFieldsValue on a disconnected form instance is a no-op
    // that emits a noisy console warning).
    const prefillConsumedRef = useRef(false);
    useEffect(() => {
        if (!account || prefillConsumedRef.current) return;
        const prefill = consumePaperPrefill();
        prefillConsumedRef.current = true;
        if (!prefill) return;
        const fields = {};
        if (prefill.symbol) fields.symbol = prefill.symbol;
        if (prefill.side === 'BUY' || prefill.side === 'SELL') fields.side = prefill.side;
        if (typeof prefill.quantity === 'number' && Number.isFinite(prefill.quantity) && prefill.quantity > 0) {
            fields.quantity = prefill.quantity;
        }
        if (Object.keys(fields).length > 0) {
            orderForm.setFieldsValue(fields);
            setPrefillSource(prefill.sourceLabel || '已预填');
        }
    }, [account, orderForm]);

    const dismissPrefill = useCallback(() => setPrefillSource(null), []);

    // Initial / on-action load
    useEffect(() => {
        let cancelled = false;
        Promise.all([
            getPaperAccount().catch(() => null),
            listPaperOrders({ limit: 50 }).catch(() => null),
        ]).then(([accountResp, ordersResp]) => {
            if (cancelled) return;
            setAccount(accountResp?.data || null);
            setOrders(ordersResp?.data?.orders || []);
        });
        return () => { cancelled = true; };
    }, [refreshKey]);

    // Quote polling for held positions
    useEffect(() => {
        const symbols = (account?.positions || []).map((position) => position.symbol);
        if (symbols.length === 0) return undefined;

        let cancelled = false;
        const fetchQuotes = async () => {
            try {
                const response = await getMultipleQuotes(symbols);
                if (cancelled) return;
                const next = {};
                const quotesData = response?.data?.quotes || response?.quotes || response;
                if (quotesData && typeof quotesData === 'object') {
                    Object.entries(quotesData).forEach(([symbol, payload]) => {
                        if (payload && typeof payload === 'object') {
                            next[symbol] = {
                                price: payload.price ?? payload.last_price ?? null,
                            };
                        }
                    });
                }
                setQuoteMap(next);
            } catch (_err) {
                // best-effort polling — silent on transient failure
            }
        };

        fetchQuotes();
        const handle = setInterval(fetchQuotes, QUOTE_POLL_MS);
        return () => {
            cancelled = true;
            clearInterval(handle);
        };
    }, [account?.positions]);

    const summary = useMemo(() => {
        const positions = account?.positions || [];
        const { positions: enriched, unrealized, marketValue } =
            computeMarkToMarket(positions, quoteMap);
        const cash = account?.cash || 0;
        const equity = cash + marketValue;
        const initialCapital = account?.initial_capital || 0;
        const totalReturn = initialCapital > 0 ? (equity - initialCapital) / initialCapital : null;
        return { positions: enriched, unrealized, marketValue, equity, totalReturn, cash, initialCapital };
    }, [account, quoteMap]);

    const handleSubmit = async () => {
        try {
            const values = await orderForm.validateFields();
            setSubmitting(true);
            const payload = {
                symbol: String(values.symbol || '').trim().toUpperCase(),
                side: values.side || 'BUY',
                quantity: Number(values.quantity),
                fill_price: Number(values.fill_price),
                commission: Number(values.commission || 0),
            };
            await submitPaperOrder(payload);
            message.success(`${payload.side} ${payload.quantity} ${payload.symbol} @ ${payload.fill_price} 已成交`);
            orderForm.resetFields(['quantity', 'fill_price', 'commission']);
            refresh();
        } catch (error) {
            const detail = error?.response?.data?.error?.message
                || error?.response?.data?.detail
                || error?.message
                || '订单提交失败';
            message.error(detail);
        } finally {
            setSubmitting(false);
        }
    };

    const handleReset = async (initialCapital) => {
        setResetting(true);
        try {
            await resetPaperAccount({ initialCapital });
            message.success('账户已重置');
            refresh();
        } catch (error) {
            message.error(error?.message || '重置失败');
        } finally {
            setResetting(false);
        }
    };

    const positionColumns = [
        { title: '标的', dataIndex: 'symbol', key: 'symbol' },
        {
            title: '数量',
            dataIndex: 'quantity',
            key: 'quantity',
            align: 'right',
            render: (value) => (typeof value === 'number' ? value.toString() : value),
        },
        {
            title: '均价',
            dataIndex: 'avg_cost',
            key: 'avg_cost',
            align: 'right',
            render: formatMoney,
        },
        {
            title: '现价',
            dataIndex: 'last_price',
            key: 'last_price',
            align: 'right',
            render: (value) => (value == null ? <Text type="secondary">—</Text> : formatMoney(value)),
        },
        {
            title: '浮动盈亏',
            dataIndex: 'unrealized_pnl',
            key: 'unrealized_pnl',
            align: 'right',
            render: (value) => {
                if (value == null) return <Text type="secondary">—</Text>;
                const tone = value >= 0 ? 'var(--accent-danger)' : 'var(--accent-success)';
                return <Text style={{ color: tone }}>{formatMoney(value)}</Text>;
            },
        },
    ];

    const orderColumns = [
        { title: '时间', dataIndex: 'submitted_at', key: 'submitted_at', width: 200 },
        {
            title: '方向',
            dataIndex: 'side',
            key: 'side',
            width: 80,
            render: (value) => (
                <Tag color={value === 'BUY' ? 'red' : 'green'}>{value}</Tag>
            ),
        },
        { title: '标的', dataIndex: 'symbol', key: 'symbol', width: 100 },
        {
            title: '数量',
            dataIndex: 'quantity',
            key: 'quantity',
            align: 'right',
            width: 100,
        },
        {
            title: '成交价',
            dataIndex: 'fill_price',
            key: 'fill_price',
            align: 'right',
            width: 120,
            render: formatMoney,
        },
    ];

    if (!account) {
        return <Empty description="纸面账户加载中..." />;
    }

    return (
        <div className="paper-trading-workspace" style={{ padding: 16 }}>
            <Card variant="borderless" style={{ marginBottom: 16 }}>
                <Title level={4} style={{ marginTop: 0 }}>
                    <ThunderboltOutlined /> 纸面账户
                </Title>
                <Row gutter={[16, 16]}>
                    <Col xs={12} md={6}>
                        <Statistic
                            title="现金"
                            value={summary.cash}
                            precision={2}
                            prefix="$"
                            valueStyle={{ fontSize: 22 }}
                        />
                    </Col>
                    <Col xs={12} md={6}>
                        <Statistic
                            title="持仓市值"
                            value={summary.marketValue}
                            precision={2}
                            prefix="$"
                            valueStyle={{ fontSize: 22 }}
                        />
                    </Col>
                    <Col xs={12} md={6}>
                        <Statistic
                            title="总权益"
                            value={summary.equity}
                            precision={2}
                            prefix="$"
                            valueStyle={{ fontSize: 22, color: 'var(--text-primary)' }}
                        />
                    </Col>
                    <Col xs={12} md={6}>
                        <Statistic
                            title="总收益率"
                            value={summary.totalReturn != null ? summary.totalReturn * 100 : 0}
                            precision={2}
                            suffix="%"
                            valueStyle={{
                                fontSize: 22,
                                color: (summary.totalReturn ?? 0) >= 0
                                    ? 'var(--accent-danger)'
                                    : 'var(--accent-success)',
                            }}
                        />
                    </Col>
                </Row>
                <Space style={{ marginTop: 12 }}>
                    <Tooltip title="账户首次开立时设置；可通过重置改变">
                        <Tag>初始资金 {formatMoney(summary.initialCapital)}</Tag>
                    </Tooltip>
                    <Tag>持仓 {summary.positions.length}</Tag>
                    <Tag>订单 {orders.length}</Tag>
                    <Button
                        size="small"
                        icon={<ReloadOutlined />}
                        onClick={refresh}
                        aria-label="刷新纸面账户"
                    >
                        刷新
                    </Button>
                    <Popconfirm
                        title="重置账户？"
                        description="将清空持仓、订单与盈亏，回到初始资金状态。"
                        onConfirm={() => handleReset(summary.initialCapital || 10000)}
                        okText="重置"
                        cancelText="取消"
                    >
                        <Button size="small" danger loading={resetting}>重置</Button>
                    </Popconfirm>
                </Space>
            </Card>

            <Row gutter={[16, 16]}>
                <Col xs={24} md={10}>
                    <Card title={<><DollarOutlined /> 下单</>} size="small">
                        {prefillSource ? (
                            <Tag
                                color="processing"
                                closable
                                onClose={dismissPrefill}
                                style={{ marginBottom: 12 }}
                                data-testid="paper-prefill-tag"
                            >
                                {prefillSource}
                            </Tag>
                        ) : null}
                        <Form form={orderForm} layout="vertical" initialValues={{ side: 'BUY', commission: 0 }}>
                            <Form.Item label="方向" name="side">
                                <Segmented options={[{ label: '买入', value: 'BUY' }, { label: '卖出', value: 'SELL' }]} />
                            </Form.Item>
                            <Form.Item
                                label="标的"
                                name="symbol"
                                rules={[{ required: true, message: '请输入标的代码' }]}
                            >
                                <Input placeholder="如 AAPL" />
                            </Form.Item>
                            <Form.Item
                                label="数量"
                                name="quantity"
                                rules={[{ required: true, message: '请输入数量' }]}
                            >
                                <InputNumber min={0.0001} style={{ width: '100%' }} placeholder="如 10" />
                            </Form.Item>
                            <Form.Item
                                label="成交价"
                                name="fill_price"
                                rules={[{ required: true, message: '请输入成交价' }]}
                            >
                                <InputNumber min={0.0001} style={{ width: '100%' }} placeholder="如 150.0" />
                            </Form.Item>
                            <Form.Item label="手续费（可选）" name="commission">
                                <InputNumber min={0} style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item style={{ marginBottom: 0 }}>
                                <Button type="primary" loading={submitting} onClick={handleSubmit} block>
                                    提交订单
                                </Button>
                            </Form.Item>
                        </Form>
                    </Card>
                </Col>
                <Col xs={24} md={14}>
                    <Card title={<><LineChartOutlined /> 当前持仓</>} size="small">
                        <Table
                            dataSource={summary.positions}
                            columns={positionColumns}
                            rowKey="symbol"
                            size="small"
                            pagination={false}
                            locale={{ emptyText: '暂无持仓' }}
                        />
                    </Card>
                </Col>
            </Row>

            <Card title="近期订单" size="small" style={{ marginTop: 16 }}>
                <Table
                    dataSource={orders}
                    columns={orderColumns}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 10 }}
                    locale={{ emptyText: '暂无订单' }}
                />
            </Card>
        </div>
    );
};

export default PaperTradingPanel;
