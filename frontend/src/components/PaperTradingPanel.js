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
    CloudUploadOutlined,
    DollarOutlined,
    LineChartOutlined,
    ReloadOutlined,
    ThunderboltOutlined,
} from '@ant-design/icons';

import {
    createResearchJournalEntry,
    getMultipleQuotes,
    getPaperAccount,
    listPaperOrders,
    resetPaperAccount,
    submitPaperOrder,
} from '../services/api';
import { consumePaperPrefill } from '../utils/paperTradingPrefill';
import { buildPaperPositionEntry } from '../utils/paperPositionJournal';

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
    const [snapshotting, setSnapshotting] = useState(false);
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

    // Stop-loss trigger guard: prevents the same position from being
    // auto-SELL'd twice while the first SELL request is in flight (the
    // position stays in `account.positions` until the refresh fires).
    const stopLossInFlightRef = useRef(new Set());

    // Quote polling for held positions + stop-loss trigger detection.
    useEffect(() => {
        const positionsForPoll = account?.positions || [];
        const symbols = positionsForPoll.map((position) => position.symbol);
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

                // Check each held position against its stop-loss price.
                positionsForPoll.forEach((position) => {
                    const stopLossPrice = Number(position?.stop_loss_price);
                    const lastPrice = Number(next[position.symbol]?.price);
                    if (
                        Number.isFinite(stopLossPrice)
                        && stopLossPrice > 0
                        && Number.isFinite(lastPrice)
                        && lastPrice > 0
                        && lastPrice <= stopLossPrice
                        && !stopLossInFlightRef.current.has(position.symbol)
                    ) {
                        stopLossInFlightRef.current.add(position.symbol);
                        submitPaperOrder({
                            symbol: position.symbol,
                            side: 'SELL',
                            quantity: position.quantity,
                            fill_price: lastPrice,
                            commission: 0,
                            slippage_bps: 10,
                            note: 'stop_loss_triggered',
                        }).then(() => {
                            message.warning(
                                `${position.symbol} 触发止损：自动按 ${formatMoney(lastPrice)} 卖出 ${position.quantity}`,
                            );
                            stopLossInFlightRef.current.delete(position.symbol);
                            refresh();
                        }).catch((error) => {
                            stopLossInFlightRef.current.delete(position.symbol);
                            const detail = error?.response?.data?.error?.message
                                || error?.message
                                || '止损单提交失败';
                            message.error(`${position.symbol} 止损失败：${detail}`);
                        });
                    }
                });
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
    }, [account?.positions, message, refresh]);

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
                slippage_bps: Number(values.slippage_bps || 0),
            };
            // Stop-loss is BUY-only and the form takes a percent; convert to
            // the [0, 0.5] ratio the backend expects.
            const stopLossPercent = Number(values.stop_loss_pct);
            if (payload.side === 'BUY' && Number.isFinite(stopLossPercent) && stopLossPercent > 0) {
                payload.stop_loss_pct = stopLossPercent / 100;
            }
            await submitPaperOrder(payload);
            message.success(`${payload.side} ${payload.quantity} ${payload.symbol} @ ${payload.fill_price} 已成交`);
            orderForm.resetFields(['quantity', 'fill_price', 'commission', 'slippage_bps', 'stop_loss_pct']);
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

    const handleSnapshotPositions = async () => {
        const enriched = summary.positions || [];
        const entries = enriched
            .map((position) => buildPaperPositionEntry(position))
            .filter(Boolean);
        if (entries.length === 0) return;

        setSnapshotting(true);
        try {
            const results = await Promise.allSettled(
                entries.map((entry) => createResearchJournalEntry(entry)),
            );
            const fulfilled = results.filter((r) => r.status === 'fulfilled').length;
            if (fulfilled === entries.length) {
                message.success(`已归档 ${fulfilled} 条持仓到今日研究档案`);
            } else if (fulfilled > 0) {
                message.warning(`归档完成 ${fulfilled}/${entries.length}（部分失败）`);
            } else {
                message.error('归档失败：研究档案不可用');
            }
        } catch (error) {
            message.error(error?.message || '归档失败');
        } finally {
            setSnapshotting(false);
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
        {
            title: '止损价',
            key: 'stop_loss',
            align: 'right',
            render: (_value, record) => {
                const stopLossPrice = Number(record?.stop_loss_price);
                if (!Number.isFinite(stopLossPrice) || stopLossPrice <= 0) {
                    return <Text type="secondary">—</Text>;
                }
                const lastPrice = Number(record?.last_price);
                let distanceLabel = null;
                if (Number.isFinite(lastPrice) && lastPrice > 0) {
                    const distancePct = ((lastPrice - stopLossPrice) / lastPrice) * 100;
                    const tone = distancePct < 1
                        ? 'var(--accent-danger)'
                        : 'var(--text-muted)';
                    distanceLabel = (
                        <div style={{ fontSize: 10, color: tone }}>
                            距触发 {distancePct.toFixed(2)}%
                        </div>
                    );
                }
                return (
                    <div data-testid={`paper-position-stop-loss-${record?.symbol}`}>
                        {formatMoney(stopLossPrice)}
                        {distanceLabel}
                    </div>
                );
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
            key: 'fill_price',
            align: 'right',
            width: 130,
            render: (_value, record) => {
                const requested = Number(record?.fill_price);
                // Older orders persisted before C2 don't carry effective_fill_price;
                // fall back to fill_price so historical rows still render normally.
                const rawEffective = record?.effective_fill_price ?? record?.fill_price;
                const effective = Number(rawEffective);
                const slippageBps = Number(record?.slippage_bps || 0);
                const hasSlippage = slippageBps > 0
                    && Number.isFinite(requested)
                    && Number.isFinite(effective)
                    && Math.abs(effective - requested) > 1e-9;

                if (!hasSlippage) {
                    return formatMoney(Number.isFinite(effective) ? effective : requested);
                }

                const slippageCost = (effective - requested) * Number(record.quantity || 0);
                return (
                    <Tooltip
                        title={(
                            <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                                <div>报价价：{formatMoney(requested)}</div>
                                <div>滑点：{slippageBps} bps</div>
                                <div>滑点成本：{formatMoney(Math.abs(slippageCost))}</div>
                            </div>
                        )}
                    >
                        <Text data-testid={`paper-order-effective-${record?.id}`}>
                            {formatMoney(effective)}{' '}
                            <Tag color="orange" style={{ marginLeft: 4, fontSize: 10 }}>
                                {slippageBps}bps
                            </Tag>
                        </Text>
                    </Tooltip>
                );
            },
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
                    <Tooltip title={summary.positions.length === 0 ? '暂无持仓可归档' : '把当前持仓写入今日研究档案，方便回到研究工作区时一眼看到'}>
                        <Button
                            size="small"
                            icon={<CloudUploadOutlined />}
                            onClick={handleSnapshotPositions}
                            loading={snapshotting}
                            disabled={summary.positions.length === 0}
                            data-testid="paper-snapshot-positions"
                        >
                            归档到档案
                        </Button>
                    </Tooltip>
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
                        <Form form={orderForm} layout="vertical" initialValues={{ side: 'BUY', commission: 0, slippage_bps: 0 }}>
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
                            <Form.Item
                                label={(
                                    <Tooltip title="执行滑点（基点 / bps），范围 0–100。BUY 时实际成交价 = 成交价 ×（1 + bps/10000），SELL 反之；模拟市场冲击。">
                                        <span>滑点（可选，bps）</span>
                                    </Tooltip>
                                )}
                                name="slippage_bps"
                            >
                                <InputNumber
                                    min={0}
                                    max={100}
                                    step={1}
                                    style={{ width: '100%' }}
                                    placeholder="如 5"
                                />
                            </Form.Item>
                            <Form.Item
                                label={(
                                    <Tooltip title="止损百分比，仅对 BUY 生效。设 5 表示当现价跌至 avg_cost × 0.95 以下时，前端 quote 轮询会自动按市价 SELL（带 10 bps 滑点）。范围 0–50%。">
                                        <span>止损（可选，%）</span>
                                    </Tooltip>
                                )}
                                name="stop_loss_pct"
                            >
                                <InputNumber
                                    min={0}
                                    max={50}
                                    step={1}
                                    style={{ width: '100%' }}
                                    placeholder="如 5（百分比）"
                                    data-testid="paper-stop-loss-input"
                                />
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
