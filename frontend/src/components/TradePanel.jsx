
import { useState, useEffect, useRef } from 'react';
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
    ArrowDownOutlined,
    BellOutlined
} from '@ant-design/icons';
import {
    getPaperAccount,
    submitPaperOrder,
    listPaperOrders,
    resetPaperAccount,
    getRealtimeQuote,
} from '../services/api';
import { loadRealtimeProfileId } from '../hooks/useRealtimePreferences';
import { buildAlertDraftFromTradePlan } from '../utils/realtimeSignals';

const { Text } = Typography;

// The /trade account historically opened at $100k. The paper realtime profile
// defaults to $10k, so on first use (an empty, never-funded account) we seed it
// to $100k to preserve the prior starting balance. We only do this when the
// account is genuinely uninitialized — see maybeSeedStartingCapital — so we
// never wipe a live account on remount.
const STARTING_CAPITAL = 100000;
const REFRESH_INTERVAL_MS = 8000;

// Adapt the paper account ({ cash, initial_capital, positions:[{symbol,
// quantity, avg_cost}], orders_count }) into the portfolio shape the panel's
// render code expects. Positions are marked to market with whatever live quote
// we have (currently the active symbol's), falling back to avg_cost — a missing
// quote must not masquerade as a total loss.
const adaptPaperAccount = (account, quoteBySymbol = {}) => {
    if (!account) {
        return null;
    }
    const initialCapital = Number(account.initial_capital || 0);
    const cash = Number(account.cash || 0);
    const positions = (account.positions || []).map((position) => {
        const avgPrice = Number(position.avg_cost || 0);
        const quantity = Number(position.quantity || 0);
        const liveQuote = quoteBySymbol[position.symbol];
        const livePrice = liveQuote && Number.isFinite(Number(liveQuote.price))
            ? Number(liveQuote.price)
            : null;
        const currentPrice = livePrice != null ? livePrice : avgPrice;
        const marketValue = currentPrice * quantity;
        const costBasis = avgPrice * quantity;
        const unrealizedPnl = marketValue - costBasis;
        const unrealizedPnlPercent = costBasis > 0 ? (unrealizedPnl / costBasis) * 100 : 0;
        return {
            symbol: position.symbol,
            quantity,
            avg_price: avgPrice,
            current_price: currentPrice,
            market_value: marketValue,
            unrealized_pnl: unrealizedPnl,
            unrealized_pnl_percent: unrealizedPnlPercent,
        };
    });
    const positionsValue = positions.reduce((sum, item) => sum + Number(item.market_value || 0), 0);
    const totalEquity = cash + positionsValue;
    const totalPnl = totalEquity - initialCapital;
    const totalPnlPercent = initialCapital > 0 ? (totalPnl / initialCapital) * 100 : 0;
    return {
        balance: cash,
        initial_capital: initialCapital,
        total_equity: totalEquity,
        total_pnl: totalPnl,
        total_pnl_percent: totalPnlPercent,
        trade_count: Number(account.orders_count || 0),
        positions,
        pending_orders: account.pending_orders || [],
    };
};

// Map paper order records ({ side, submitted_at, fill_price,
// effective_fill_price }) into the history rows the table renders
// ({ action, timestamp, price, total_amount }).
const adaptPaperOrders = (orders = []) => orders.map((order) => {
    const fillPrice = Number(order.effective_fill_price ?? order.fill_price ?? 0);
    const quantity = Number(order.quantity || 0);
    return {
        id: order.id,
        symbol: order.symbol,
        action: order.side,
        quantity,
        price: fillPrice,
        total_amount: fillPrice * quantity,
        timestamp: order.submitted_at,
        pnl: null,
    };
});
const formatCurrency = (value) => `$${Number(value || 0).toFixed(2)}`;
const formatOptionalCurrency = (value) => (
    value === null || value === undefined || Number.isNaN(Number(value))
        ? '--'
        : formatCurrency(value)
);
const formatPercent = (value) => (
    value === null || value === undefined || Number.isNaN(Number(value))
        ? '--'
        : `${Number(value).toFixed(2)}%`
);
const formatTimestamp = (value) => {
    if (!value) {
        return '--';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return '--';
    }

    return date.toLocaleTimeString();
};
const hasFinitePositiveNumber = (value) => value !== null && value !== undefined && !Number.isNaN(Number(value)) && Number(value) > 0;
const DEFAULT_RISK_PERCENT = 2;

const TradePanel = ({ defaultSymbol, visible, onClose, onSuccess, planDraft = null, onCreateAlertFromPlan = null }) => {
    const [rawAccount, setRawAccount] = useState(null);
    const [rawOrders, setRawOrders] = useState([]);
    const [loading, setLoading] = useState(false);
    const [action, setAction] = useState('BUY');
    const [symbol, setSymbol] = useState(defaultSymbol || 'AAPL');
    const [quantity, setQuantity] = useState(100);
    const [price, setPrice] = useState(null); // Optional limit price
    const [currentQuote, setCurrentQuote] = useState(null);
    const [quoteLoading, setQuoteLoading] = useState(false);
    const [riskPercent, setRiskPercent] = useState(DEFAULT_RISK_PERCENT);
    const currentQuoteRequestRef = useRef(0);
    // Resolve the realtime profile once per mount so the paper account scopes to
    // the same per-browser identity the rest of the realtime workbench uses.
    const profileIdRef = useRef(loadRealtimeProfileId());

    // Mark held positions to market with the active symbol's live quote when we
    // have it; everything else carries at avg_cost inside adaptPaperAccount.
    const quoteBySymbol = currentQuote?.symbol && Number.isFinite(Number(currentQuote.price))
        ? { [currentQuote.symbol]: currentQuote }
        : {};
    const portfolio = adaptPaperAccount(rawAccount, quoteBySymbol);
    const history = adaptPaperOrders(rawOrders);

    // Poll-after-action replaces the old trade WebSocket live-push: this is a
    // single-user local tool, so we just re-fetch account + orders. A light
    // interval keeps the view fresh while the modal is open (mirrors the quote
    // cadence RealTimePanel already polls at).
    useEffect(() => {
        if (!visible) {
            return undefined;
        }

        let cancelled = false;

        const load = async () => {
            await maybeSeedStartingCapital();
            if (cancelled) {
                return;
            }
            await refreshAccountAndOrders();
        };

        load();

        const intervalId = window.setInterval(() => {
            refreshAccountAndOrders();
        }, REFRESH_INTERVAL_MS);

        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
        };
        // refreshAccountAndOrders / maybeSeedStartingCapital are stable closures
        // over the per-mount profile ref; re-running only on visibility is intended.
    }, [visible]);

    useEffect(() => {
        if (visible) {
            setSymbol(planDraft?.symbol || defaultSymbol || 'AAPL');
            setAction(planDraft?.action || 'BUY');
            setQuantity(planDraft?.quantity || 100);
            setPrice(planDraft?.limitPrice ?? null);
            setRiskPercent(DEFAULT_RISK_PERCENT);
            setCurrentQuote(null);
        }
    }, [visible, defaultSymbol, planDraft]);

    useEffect(() => {
        if (!visible) {
            currentQuoteRequestRef.current += 1;
            setCurrentQuote(null);
            setQuoteLoading(false);
        }
    }, [visible]);

    useEffect(() => {
        if (visible && symbol) {
            fetchCurrentPrice(symbol);
        }
    }, [visible, symbol]);

    // Fetch data — paper account + order history, scoped to the realtime profile.
    const refreshAccountAndOrders = async () => {
        setLoading(true);
        try {
            const [accountResp, ordersResp] = await Promise.all([
                getPaperAccount(profileIdRef.current).catch(() => null),
                listPaperOrders({ limit: 50 }, profileIdRef.current).catch(() => null),
            ]);
            if (accountResp?.success) {
                setRawAccount(accountResp.data || null);
            }
            if (ordersResp?.success) {
                setRawOrders(ordersResp.data?.orders || []);
            }
        } catch (error) {
            message.error('无法获取纸面账户数据');
        } finally {
            setLoading(false);
        }
    };

    // Seed a ~$100k starting balance on first use only. The paper realtime
    // profile defaults to $10k; the legacy /trade account opened at $100k. We
    // reset to STARTING_CAPITAL exclusively when the account is genuinely
    // uninitialized (never funded + no positions + no orders) so an existing
    // account is never wiped on remount.
    const maybeSeedStartingCapital = async () => {
        try {
            const response = await getPaperAccount(profileIdRef.current);
            if (!response?.success) {
                return;
            }
            const account = response.data || {};
            const isUninitialized = !account.initial_capital
                && (account.positions || []).length === 0
                && Number(account.orders_count || 0) === 0;
            if (isUninitialized) {
                await resetPaperAccount({ initialCapital: STARTING_CAPITAL }, profileIdRef.current);
            }
        } catch (error) {
            // best-effort seed; the regular refresh still loads whatever exists
        }
    };

    const fetchCurrentPrice = async (sym) => {
        if (!sym) {
            currentQuoteRequestRef.current += 1;
            setCurrentQuote(null);
            return;
        }

        const requestId = currentQuoteRequestRef.current + 1;
        currentQuoteRequestRef.current = requestId;
        setCurrentQuote(null);
        setQuoteLoading(true);
        try {
            const response = await getRealtimeQuote(sym);
            if (currentQuoteRequestRef.current !== requestId) {
                return;
            }
            if (response.success) {
                setCurrentQuote(response.data || null);
            }
        } catch (error) {
            if (currentQuoteRequestRef.current === requestId) {
                setCurrentQuote(null);
            }
        } finally {
            if (currentQuoteRequestRef.current === requestId) {
                setQuoteLoading(false);
            }
        }
    };

    const handleTrade = async () => {
        if (!symbol || !quantity) {
            message.warning('请输入股票代码和数量');
            return;
        }

        // The paper engine fills at an explicit price. Use the typed limit price
        // when present, otherwise the live quote acts as the market fill price.
        const fillPrice = hasFinitePositiveNumber(price)
            ? Number(price)
            : (hasFinitePositiveNumber(currentQuote?.price) ? Number(currentQuote.price) : null);
        if (!hasFinitePositiveNumber(fillPrice)) {
            message.warning('暂无可用成交价，请填写价格或等待行情同步');
            return;
        }

        setLoading(true);
        try {
            const response = await submitPaperOrder(
                {
                    symbol,
                    side: action,
                    quantity,
                    fill_price: fillPrice,
                    order_type: 'MARKET',
                },
                profileIdRef.current,
            );
            if (response.success) {
                message.success(`交易成功: ${action} ${quantity} ${symbol}`);
                // Poll-after-action: re-fetch account + orders.
                await refreshAccountAndOrders();
                if (onSuccess) onSuccess();
            }
        } catch (error) {
            const detail = error.response?.data?.detail
                || error.userMessage
                || error.message;
            message.error(`交易失败: ${detail}`);
        } finally {
            setLoading(false);
        }
    };

    const handleReset = async () => {
        try {
            // Preserve the panel's ~$100k starting balance on reset.
            await resetPaperAccount({ initialCapital: STARTING_CAPITAL }, profileIdRef.current);
            message.success('账户已重置');
            await refreshAccountAndOrders();
        } catch (error) {
            message.error('重置失败');
        }
    };

    const handleCreateAlert = (target) => {
        if (!planDraft || !onCreateAlertFromPlan) {
            return;
        }

        const draft = buildAlertDraftFromTradePlan(planDraft, target);
        if (draft) {
            onCreateAlertFromPlan(draft);
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

    const activePosition = portfolio?.positions?.find((item) => item.symbol === symbol) || null;
    const referencePrice = price ?? planDraft?.suggestedEntry ?? currentQuote?.price ?? null;
    const stopReferencePrice = planDraft?.stopLoss ?? null;
    const riskCapital = portfolio?.total_equity && hasFinitePositiveNumber(riskPercent)
        ? Number(portfolio.total_equity) * (Number(riskPercent) / 100)
        : null;
    const riskPerShare = hasFinitePositiveNumber(referencePrice) && hasFinitePositiveNumber(stopReferencePrice)
        ? Math.abs(Number(referencePrice) - Number(stopReferencePrice))
        : null;
    const maxAffordableQuantity = hasFinitePositiveNumber(referencePrice) && hasFinitePositiveNumber(portfolio?.balance)
        ? Math.floor(Number(portfolio.balance) / Number(referencePrice))
        : null;
    const suggestedRiskQuantity = hasFinitePositiveNumber(riskCapital) && hasFinitePositiveNumber(riskPerShare) && riskPerShare > 0
        ? Math.floor(Number(riskCapital) / Number(riskPerShare))
        : null;
    const suggestedQuantity = suggestedRiskQuantity !== null && maxAffordableQuantity !== null
        ? Math.max(0, Math.min(suggestedRiskQuantity, maxAffordableQuantity))
        : suggestedRiskQuantity;
    const estimatedExposure = hasFinitePositiveNumber(referencePrice) && hasFinitePositiveNumber(suggestedQuantity)
        ? Number(referencePrice) * Number(suggestedQuantity)
        : null;

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
            title={
                <div style={{ display: 'grid', gap: 6 }}>
                    <div style={{ fontSize: 19, fontWeight: 800, color: 'var(--text-primary)' }}>
                        模拟交易终端
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        在实时行情工作台里直接完成纸面交易，快速验证买卖假设与仓位变化。
                    </div>
                </div>
            }
            open={visible}
            onCancel={onClose}
            footer={null}
            width={1000}
            style={{ top: 20 }}
            styles={{
                body: {
                    padding: 20,
                    background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-primary) 94%, white 6%) 0%, var(--bg-primary) 100%)',
                },
            }}
        >
            <div className="trade-panel-shell">
                <Card
                    className="trade-panel-hero"
                    styles={{ body: { padding: 20 } }}
                >
                    <div className="trade-panel-hero__copy">
                        <div className="trade-panel-hero__eyebrow">纸面交易</div>
                        <div className="trade-panel-hero__title">
                            {symbol || 'AAPL'} {action === 'BUY' ? '买入计划' : '卖出计划'}
                        </div>
                        <div className="trade-panel-hero__subtitle">
                            {action === 'BUY'
                                ? '在不影响真实账户的前提下，快速测试进场节奏、下单数量和仓位分配。'
                                : '从当前持仓直接切换为卖出流程，验证减仓与止盈思路。'}
                        </div>
                    </div>
                    <div className="trade-panel-hero__chips">
                        <div className="trade-panel-hero__chip">当前标的 {symbol || '--'}</div>
                        <div className="trade-panel-hero__chip">订单类型 {price ? '限价单' : '市价单'}</div>
                        <div className="trade-panel-hero__chip">默认数量 {quantity || 0}</div>
                        <div className="trade-panel-hero__chip">
                            参考市价 {quoteLoading ? '同步中' : formatOptionalCurrency(currentQuote?.price)}
                        </div>
                    </div>
                </Card>

                {planDraft ? (
                    <Card
                        className="trade-panel-card"
                        style={{ background: 'linear-gradient(180deg, color-mix(in srgb, var(--accent-primary) 10%, var(--bg-secondary) 90%) 0%, color-mix(in srgb, var(--bg-secondary) 94%, white 6%) 100%)' }}
                    >
                        <div style={{ display: 'grid', gap: 14 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                                <div>
                                    <div style={{ fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 700 }}>
                                        Trading Draft
                                    </div>
                                    <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>
                                        {planDraft.sourceTitle || '异动交易计划'}
                                    </div>
                                    <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
                                        {planDraft.sourceDescription || planDraft.note || '已根据当前异动自动带入交易草稿参数。'}
                                    </div>
                                </div>
                                <Space wrap>
                                    <Tag color={action === 'BUY' ? 'green' : 'volcano'} style={{ borderRadius: 999, paddingInline: 10 }}>
                                        {action === 'BUY' ? '顺势进场草稿' : '风险收缩草稿'}
                                    </Tag>
                                    <Tag color="blue" style={{ borderRadius: 999, paddingInline: 10 }}>
                                        建议数量 {quantity}
                                    </Tag>
                                </Space>
                            </div>

                            {onCreateAlertFromPlan ? (
                                <Space wrap size={8}>
                                    <Button className="trade-panel-secondary-button" size="small" icon={<BellOutlined />} onClick={() => handleCreateAlert('entry')}>
                                        转入场提醒
                                    </Button>
                                    <Button className="trade-panel-secondary-button" size="small" icon={<BellOutlined />} onClick={() => handleCreateAlert('stop')}>
                                        转止损提醒
                                    </Button>
                                    <Button className="trade-panel-secondary-button" size="small" icon={<BellOutlined />} onClick={() => handleCreateAlert('take')}>
                                        转止盈提醒
                                    </Button>
                                </Space>
                            ) : null}

                            <div className="trade-panel-quote-grid">
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">建议入场</div>
                                    <div className="trade-panel-quote-stat__value">{formatOptionalCurrency(planDraft.suggestedEntry)}</div>
                                </div>
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">止损参考</div>
                                    <div className="trade-panel-quote-stat__value">{formatOptionalCurrency(planDraft.stopLoss)}</div>
                                </div>
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">止盈参考</div>
                                    <div className="trade-panel-quote-stat__value">{formatOptionalCurrency(planDraft.takeProfit)}</div>
                                </div>
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">计划说明</div>
                                    <div className="trade-panel-quote-stat__value" style={{ fontSize: 13, lineHeight: 1.5 }}>
                                        {planDraft.note || '已自动生成一份可编辑的交易计划草稿。'}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </Card>
                ) : null}

                <Row gutter={[16, 16]}>
                {/* Left: Order Entry */}
                <Col xs={24} lg={8}>
                    <Card
                        title="下单面板"
                        variant="borderless"
                        className="trade-panel-card"
                        style={{ background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-secondary) 90%, white 10%) 0%, var(--bg-tertiary) 100%)' }}
                    >
                        <Space direction="vertical" style={{ width: '100%' }} size="middle">
                            <div>
                                <Text type="secondary">股票代码</Text>
                                <div style={{ fontWeight: 'bold', fontSize: 18, color: 'var(--text-primary)' }}>{symbol}</div>
                                <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                    <Tag color={action === 'BUY' ? 'green' : 'volcano'} style={{ borderRadius: 999, paddingInline: 10 }}>
                                        {action === 'BUY' ? '准备买入' : '准备卖出'}
                                    </Tag>
                                    {activePosition && (
                                        <Tag color="blue" style={{ borderRadius: 999, paddingInline: 10 }}>
                                            当前持仓 {activePosition.quantity}
                                        </Tag>
                                    )}
                                    {currentQuote?.price && (
                                        <Tag color={Number(currentQuote.change || 0) >= 0 ? 'green' : 'volcano'} style={{ borderRadius: 999, paddingInline: 10 }}>
                                            最新 {formatOptionalCurrency(currentQuote.price)} / {formatPercent(currentQuote.change_percent)}
                                        </Tag>
                                    )}
                                </div>
                            </div>

                            <div className="trade-panel-quote-grid">
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">最新价</div>
                                    <div className="trade-panel-quote-stat__value">{quoteLoading ? '同步中' : formatOptionalCurrency(currentQuote?.price)}</div>
                                </div>
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">涨跌幅</div>
                                    <div className="trade-panel-quote-stat__value">{formatPercent(currentQuote?.change_percent)}</div>
                                </div>
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">日内区间</div>
                                    <div className="trade-panel-quote-stat__value">
                                        {currentQuote
                                            ? `${formatOptionalCurrency(currentQuote.low)} - ${formatOptionalCurrency(currentQuote.high)}`
                                            : '--'}
                                    </div>
                                </div>
                                <div className="trade-panel-quote-stat">
                                    <div className="trade-panel-quote-stat__label">更新时间</div>
                                    <div className="trade-panel-quote-stat__value">{formatTimestamp(currentQuote?.timestamp)}</div>
                                </div>
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

                            <div className="trade-panel-risk-card">
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                                    <Text strong>仓位建议</Text>
                                    <Space wrap>
                                        <Text type="secondary">风险占比</Text>
                                        <InputNumber
                                            min={0.5}
                                            max={10}
                                            step={0.5}
                                            value={riskPercent}
                                            onChange={setRiskPercent}
                                            placeholder="2"
                                        />
                                        <Text type="secondary">%</Text>
                                    </Space>
                                </div>
                                <div className="trade-panel-quote-grid" style={{ marginTop: 12 }}>
                                    <div className="trade-panel-quote-stat">
                                        <div className="trade-panel-quote-stat__label">风险预算</div>
                                        <div className="trade-panel-quote-stat__value">{formatOptionalCurrency(riskCapital)}</div>
                                    </div>
                                    <div className="trade-panel-quote-stat">
                                        <div className="trade-panel-quote-stat__label">每股风险</div>
                                        <div className="trade-panel-quote-stat__value">{formatOptionalCurrency(riskPerShare)}</div>
                                    </div>
                                    <div className="trade-panel-quote-stat">
                                        <div className="trade-panel-quote-stat__label">建议仓位</div>
                                        <div className="trade-panel-quote-stat__value">{suggestedQuantity ?? '--'}</div>
                                    </div>
                                    <div className="trade-panel-quote-stat">
                                        <div className="trade-panel-quote-stat__label">预计敞口</div>
                                        <div className="trade-panel-quote-stat__value">{formatOptionalCurrency(estimatedExposure)}</div>
                                    </div>
                                </div>
                                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                                    {hasFinitePositiveNumber(stopReferencePrice) && hasFinitePositiveNumber(referencePrice)
                                        ? `按参考入场 ${formatOptionalCurrency(referencePrice)} 与止损 ${formatOptionalCurrency(stopReferencePrice)} 计算，并自动受账户余额约束。`
                                        : '填入交易计划或止损位后，这里会按账户总资产给出建议仓位。'}
                                </div>
                                {hasFinitePositiveNumber(suggestedQuantity) ? (
                                    <Button className="trade-panel-secondary-button" style={{ marginTop: 10 }} onClick={() => setQuantity(suggestedQuantity)}>
                                        使用建议仓位
                                    </Button>
                                ) : null}
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
                                <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                                    留空时以后端最新行情成交，当前参考价 {quoteLoading ? '同步中' : formatOptionalCurrency(currentQuote?.price)}
                                </div>
                            </div>

                            <Button
                                type="primary"
                                block
                                size="large"
                                loading={loading}
                                danger={action === 'SELL'}
                                onClick={handleTrade}
                                style={{ marginTop: 10, height: 46, fontWeight: 700, borderRadius: 14 }}
                            >
                                {action === 'BUY' ? '买入 Buy' : '卖出 Sell'}
                            </Button>
                        </Space>
                    </Card>

                    {/* Account Summary Mini */}
                    {portfolio && (
                        <Card size="small" className="trade-panel-card" style={{ marginTop: 16 }}>
                            <div className="trade-panel-mini-grid">
                                <div className="trade-panel-mini-stat">
                                    <div className="trade-panel-mini-stat__label">账户余额</div>
                                    <div className="trade-panel-mini-stat__value">{formatCurrency(portfolio.balance)}</div>
                                </div>
                                <div className="trade-panel-mini-stat">
                                    <div className="trade-panel-mini-stat__label">总资产</div>
                                    <div className="trade-panel-mini-stat__value">{formatCurrency(portfolio.total_equity)}</div>
                                </div>
                            </div>
                        </Card>
                    )}
                </Col>

                {/* Right: Portfolio & History */}
                <Col xs={24} lg={16}>
                    {portfolio && (
                        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                            <Col xs={24} sm={12} xl={8}>
                                <Card className="trade-panel-stat-card trade-panel-stat-card--pnl">
                                    <Statistic
                                        title="总盈亏 (P&L)"
                                        value={portfolio.total_pnl}
                                        precision={2}
                                        valueStyle={{ color: portfolio.total_pnl >= 0 ? '#52c41a' : '#ff4d4f' }}
                                        prefix={portfolio.total_pnl >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                                        suffix={`(${portfolio.total_pnl_percent.toFixed(2)}%)`}
                                    />
                                </Card>
                            </Col>
                            <Col xs={24} sm={12} xl={8}>
                                <Card className="trade-panel-stat-card">
                                    <Statistic title="交易次数" value={portfolio.trade_count} prefix={<HistoryOutlined />} />
                                </Card>
                            </Col>
                            <Col xs={24} sm={24} xl={8}>
                                <Card className="trade-panel-stat-card trade-panel-stat-card--reset">
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                                        <div>
                                            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>账户重置</div>
                                            <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                                                一键恢复到初始纸面账户状态
                                            </div>
                                        </div>
                                        <Popconfirm title="确定重置账户吗?" onConfirm={handleReset}>
                                            <Button danger icon={<ReloadOutlined />}>重置账户</Button>
                                        </Popconfirm>
                                    </div>
                                </Card>
                            </Col>
                        </Row>
                    )}

                    <Card className="trade-panel-card">
                        <Tabs defaultActiveKey="positions" items={portfolioTabItems} />
                    </Card>
                </Col>
                </Row>
            </div>

            <style>{`
                .trade-panel-shell {
                    display: grid;
                    gap: 16px;
                }

                .trade-panel-hero,
                .trade-panel-card,
                .trade-panel-stat-card {
                    border-radius: 24px;
                    border: 1px solid var(--border-color);
                    box-shadow: 0 14px 36px rgba(15, 23, 42, 0.07);
                }

                .trade-panel-hero {
                    background:
                        linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 14%, var(--bg-secondary) 86%) 0%, color-mix(in srgb, var(--accent-secondary) 12%, var(--bg-secondary) 88%) 100%);
                }

                .trade-panel-hero__eyebrow {
                    font-size: 11px;
                    letter-spacing: 0.16em;
                    text-transform: uppercase;
                    color: var(--text-secondary);
                    font-weight: 700;
                }

                .trade-panel-hero__title {
                    margin-top: 8px;
                    font-size: 24px;
                    font-weight: 800;
                    color: var(--text-primary);
                }

                .trade-panel-hero__subtitle {
                    margin-top: 10px;
                    font-size: 13px;
                    line-height: 1.7;
                    color: var(--text-secondary);
                }

                .trade-panel-hero__chips {
                    margin-top: 16px;
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                }

                .trade-panel-hero__chip {
                    padding: 8px 12px;
                    border-radius: 999px;
                    background: color-mix(in srgb, var(--bg-secondary) 84%, white 16%);
                    border: 1px solid color-mix(in srgb, var(--accent-primary) 14%, var(--border-color) 86%);
                    font-size: 12px;
                    color: var(--text-secondary);
                }

                .trade-panel-mini-grid {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 12px;
                }

                .trade-panel-mini-stat {
                    padding: 14px;
                    border-radius: 18px;
                    background: color-mix(in srgb, var(--bg-primary) 88%, white 12%);
                    border: 1px solid var(--border-color);
                }

                .trade-panel-mini-stat__label {
                    font-size: 12px;
                    color: var(--text-secondary);
                }

                .trade-panel-mini-stat__value {
                    margin-top: 6px;
                    font-size: 20px;
                    font-weight: 800;
                    color: var(--text-primary);
                }

                .trade-panel-stat-card--pnl {
                    background: linear-gradient(135deg, rgba(34, 197, 94, 0.12), rgba(34, 197, 94, 0.03));
                }

                .trade-panel-stat-card--reset {
                    background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(99, 102, 241, 0.03));
                }

                .trade-panel-quote-grid {
                    display: grid;
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                    gap: 10px;
                }

                .trade-panel-quote-stat {
                    padding: 12px 14px;
                    border-radius: 16px;
                    background: color-mix(in srgb, var(--bg-primary) 88%, white 12%);
                    border: 1px solid var(--border-color);
                }

                .trade-panel-quote-stat__label {
                    font-size: 12px;
                    color: var(--text-secondary);
                }

                .trade-panel-quote-stat__value {
                    margin-top: 6px;
                    font-size: 15px;
                    font-weight: 700;
                    color: var(--text-primary);
                }

                .trade-panel-risk-card {
                    padding: 14px;
                    border-radius: 18px;
                    border: 1px solid var(--border-color);
                    background: color-mix(in srgb, var(--bg-primary) 90%, white 10%);
                }

                .trade-panel-secondary-button {
                    border-radius: 12px;
                    background: color-mix(in srgb, var(--bg-primary) 92%, white 8%);
                    border-color: color-mix(in srgb, var(--accent-primary) 14%, var(--border-color) 86%);
                }

                @media (max-width: 640px) {
                    .trade-panel-quote-grid,
                    .trade-panel-mini-grid {
                        grid-template-columns: 1fr;
                    }
                }
            `}</style>
        </Modal>
    );
};

export default TradePanel;
