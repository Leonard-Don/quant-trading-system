import React, { useState, useEffect, useCallback } from 'react';
import {
    Alert,
    Button,
    Input,
    InputNumber,
    Select,
    Space,
    Table,
    Tag,
    Modal,
    Form,
    message,
    Switch,
    Popconfirm,
    Badge,
    Tooltip,
    Typography
} from 'antd';
import {
    BellOutlined,
    PlusOutlined,
    DeleteOutlined,
    CheckCircleOutlined,
    AlertOutlined,
    SoundOutlined
} from '@ant-design/icons';
import { getMarketData } from '../services/api';
import {
    evaluateRealtimeAlert,
    getAlertConditionLabel,
    normalizePriceAlert,
} from '../utils/realtimeSignals';

const { Option } = Select;
const { Text, Title } = Typography;

const STORAGE_KEY = 'price_alerts';
const DEFAULT_CONDITION = 'price_above';
const CONDITION_OPTIONS = [
    { value: 'price_above', label: '价格 ≥ 目标值', needsThreshold: true, thresholdLabel: '目标价格', prefix: '$', step: 0.01 },
    { value: 'price_below', label: '价格 ≤ 目标值', needsThreshold: true, thresholdLabel: '目标价格', prefix: '$', step: 0.01 },
    { value: 'change_pct_above', label: '涨跌幅 ≥ 阈值', needsThreshold: true, thresholdLabel: '涨跌幅阈值', suffix: '%', step: 0.1 },
    { value: 'change_pct_below', label: '涨跌幅 ≤ 阈值', needsThreshold: true, thresholdLabel: '涨跌幅阈值', suffix: '%', step: 0.1 },
    { value: 'intraday_range_above', label: '日内振幅 ≥ 阈值', needsThreshold: true, thresholdLabel: '日内振幅阈值', suffix: '%', step: 0.1 },
    { value: 'relative_volume_above', label: '相对放量 ≥ 阈值', needsThreshold: true, thresholdLabel: '放量倍数阈值', suffix: 'x', step: 0.1 },
    { value: 'touch_high', label: '触及日内新高附近', needsThreshold: false },
    { value: 'touch_low', label: '触及日内新低附近', needsThreshold: false },
];

const normalizeStoredAlerts = (rawAlerts = []) => rawAlerts.map((item) => normalizePriceAlert(item));

const playAlertSound = () => {
    try {
        const audio = new Audio('data:audio/wav;base64,UklGRjIAAABXQVZFZm10IBIAAAABAAEAQB8AAEAfAAABAAgAAABmYWN0BAAAAAAAAABkYXRhAAAAAA==');
        audio.play().catch(() => { });
    } catch (error) {
        console.error('Failed to play alert sound:', error);
    }
};

/**
 * 实时提醒组件
 * 支持价格、涨跌幅、振幅与日内高低点规则，并优先使用实时 quote 触发
 */
const PriceAlerts = ({
    embedded = false,
    prefillSymbol = '',
    prefillDraft = null,
    composerSignal = 0,
    liveQuotes = {},
}) => {
    const [alerts, setAlerts] = useState([]);
    const [modalVisible, setModalVisible] = useState(false);
    const [form] = Form.useForm();
    const [notificationsEnabled, setNotificationsEnabled] = useState(false);
    // eslint-disable-next-line no-unused-vars
    const [triggeredAlerts, setTriggeredAlerts] = useState([]);
    const watchedCondition = Form.useWatch('condition', form) || DEFAULT_CONDITION;
    const selectedCondition = CONDITION_OPTIONS.find((item) => item.value === watchedCondition) || CONDITION_OPTIONS[0];

    useEffect(() => {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            try {
                setAlerts(normalizeStoredAlerts(JSON.parse(saved)));
            } catch (e) {
                console.error('Failed to load alerts:', e);
            }
        }

        if ('Notification' in window) {
            setNotificationsEnabled(Notification.permission === 'granted');
        }
    }, []);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
    }, [alerts]);

    useEffect(() => {
        if (!prefillSymbol || !composerSignal) {
            return;
        }

        setModalVisible(true);
        const nextCondition = prefillDraft?.condition || form.getFieldValue('condition') || DEFAULT_CONDITION;
        const nextValues = {
            symbol: (prefillDraft?.symbol || prefillSymbol).toUpperCase(),
            condition: nextCondition,
            threshold: prefillDraft && Object.prototype.hasOwnProperty.call(prefillDraft, 'threshold')
                ? prefillDraft.threshold
                : undefined,
        };

        form.setFieldsValue(nextValues);
    }, [composerSignal, form, prefillDraft, prefillSymbol]);

    const requestNotificationPermission = async () => {
        if (!('Notification' in window)) {
            message.warning('您的浏览器不支持通知功能');
            return;
        }

        const permission = await Notification.requestPermission();
        setNotificationsEnabled(permission === 'granted');

        if (permission === 'granted') {
            message.success('通知权限已开启');
            new Notification('实时提醒已启用', {
                body: '当行情触发您设定的规则时，您将收到通知',
                icon: '/favicon.ico'
            });
        } else {
            message.warning('通知权限被拒绝');
        }
    };

    const markTriggered = useCallback((alert, triggerValue, content) => {
        setAlerts((prev) => prev.map((item) => (
            item.id === alert.id
                ? {
                    ...item,
                    triggered: true,
                    triggerValue,
                    triggerTime: new Date().toISOString(),
                }
                : item
        )));

        setTriggeredAlerts((prev) => [...prev, { ...alert, triggerValue }]);

        if (notificationsEnabled) {
            new Notification(`🔔 实时提醒: ${alert.symbol}`, {
                body: content,
                icon: '/favicon.ico',
                tag: alert.id
            });
        }

        playAlertSound();

        message.warning({
            content,
            duration: 5
        });
    }, [notificationsEnabled]);

    const evaluateLiveAlerts = useCallback(() => {
        const activeAlerts = alerts.filter((item) => item.active && !item.triggered);
        if (activeAlerts.length === 0) {
            return;
        }

        activeAlerts.forEach((alert) => {
            if (alert.armedAt && Date.now() < new Date(alert.armedAt).getTime()) {
                return;
            }

            const quote = liveQuotes[alert.symbol];
            if (!quote) {
                return;
            }

            const result = evaluateRealtimeAlert(alert, quote, liveQuotes);
            if (result.triggered) {
                markTriggered(alert, result.triggerValue, result.message || `${alert.symbol} 实时提醒已触发`);
            }
        });
    }, [alerts, liveQuotes, markTriggered]);

    const fallbackCheckPrices = useCallback(async () => {
        const activeAlerts = alerts.filter((item) => item.active && !item.triggered);
        if (activeAlerts.length === 0) {
            return;
        }

        for (const alert of activeAlerts) {
            const normalizedAlert = normalizePriceAlert(alert);
            if (normalizedAlert.armedAt && Date.now() < new Date(normalizedAlert.armedAt).getTime()) {
                continue;
            }

            if (!['price_above', 'price_below'].includes(normalizedAlert.condition)) {
                continue;
            }

            try {
                const result = await getMarketData({ symbol: normalizedAlert.symbol, period: '1d' });
                const prices = result.data?.data || result.data || [];
                if (prices.length === 0) continue;

                const currentPrice = prices[prices.length - 1].close;
                const evaluation = evaluateRealtimeAlert(normalizedAlert, { price: currentPrice });
                if (evaluation.triggered) {
                    markTriggered(
                        normalizedAlert,
                        evaluation.triggerValue,
                        evaluation.message || `${normalizedAlert.symbol} 价格提醒已触发`
                    );
                }
            } catch (err) {
                console.error('检查价格失败:', err);
            }
        }
    }, [alerts, markTriggered]);

    useEffect(() => {
        if (Object.keys(liveQuotes).length === 0) {
            return;
        }

        evaluateLiveAlerts();
    }, [evaluateLiveAlerts, liveQuotes]);

    useEffect(() => {
        if (Object.keys(liveQuotes).length > 0) {
            return undefined;
        }

        const interval = setInterval(fallbackCheckPrices, 30000);
        return () => clearInterval(interval);
    }, [fallbackCheckPrices, liveQuotes]);

    const addAlert = (values) => {
        const newAlert = normalizePriceAlert({
            id: `alert_${Date.now()}`,
            symbol: values.symbol.toUpperCase(),
            condition: values.condition,
            threshold: selectedCondition.needsThreshold ? Number(values.threshold) : null,
            active: true,
            triggered: false,
            createdAt: new Date().toISOString(),
            armedAt: new Date(Date.now() + 5000).toISOString(),
        });

        setAlerts((prev) => [...prev, newAlert]);
        setModalVisible(false);
        form.resetFields();
        message.success('实时提醒规则已添加');
    };

    const deleteAlert = (id) => {
        setAlerts((prev) => prev.filter((item) => item.id !== id));
        message.success('提醒已删除');
    };

    const toggleAlert = (id) => {
        setAlerts((prev) => prev.map((item) =>
            item.id === id ? { ...item, active: !item.active } : item
        ));
    };

    const resetAlert = (id) => {
        setAlerts((prev) => prev.map((item) =>
            item.id === id
                ? { ...item, triggered: false, triggerValue: null, triggerTime: null }
                : item
        ));
    };

    const columns = [
        {
            title: '股票',
            dataIndex: 'symbol',
            key: 'symbol',
            render: (text) => <Tag color="blue">{text}</Tag>
        },
        {
            title: '条件',
            key: 'condition',
            render: (_, record) => getAlertConditionLabel(record)
        },
        {
            title: '状态',
            key: 'status',
            render: (_, record) => {
                if (record.triggered) {
                    return (
                        <Tooltip title={`触发于 ${new Date(record.triggerTime).toLocaleString()}`}>
                            <Tag color="error" icon={<AlertOutlined />}>已触发</Tag>
                        </Tooltip>
                    );
                }
                return record.active
                    ? <Tag color="success" icon={<CheckCircleOutlined />}>监控中</Tag>
                    : <Tag color="default">已暂停</Tag>;
            }
        },
        {
            title: '操作',
            key: 'actions',
            render: (_, record) => (
                <Space>
                    <Switch
                        size="small"
                        checked={record.active}
                        onChange={() => toggleAlert(record.id)}
                        disabled={record.triggered}
                    />
                    {record.triggered && (
                        <Button size="small" onClick={() => resetAlert(record.id)}>重置</Button>
                    )}
                    <Popconfirm title="确定删除？" onConfirm={() => deleteAlert(record.id)}>
                        <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                </Space>
            )
        }
    ];

    const activeAlertCount = alerts.filter((item) => item.active && !item.triggered).length;
    const triggeredAlertCount = alerts.filter((item) => item.triggered).length;
    const pausedAlertCount = alerts.filter((item) => !item.active && !item.triggered).length;
    const controls = (
        <Space wrap>
            <Tooltip title={notificationsEnabled ? '通知已开启' : '点击开启浏览器通知'}>
                <Button
                    type={notificationsEnabled ? 'default' : 'primary'}
                    icon={<SoundOutlined />}
                    onClick={requestNotificationPermission}
                    disabled={notificationsEnabled}
                >
                    {notificationsEnabled ? '通知已开启' : '开启通知'}
                </Button>
            </Tooltip>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
                添加提醒
            </Button>
        </Space>
    );

    const content = (
        <>
            {embedded ? (
                <div style={{ marginBottom: 16 }}>
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: 16,
                        flexWrap: 'wrap',
                        marginBottom: 16
                    }}>
                        <div>
                            <Space size={10}>
                                <BellOutlined />
                                <Title level={5} style={{ margin: 0 }}>实时提醒</Title>
                                <Badge count={activeAlertCount} />
                            </Space>
                            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                                支持价格、涨跌幅、日内振幅、相对放量和高低点规则；嵌入实时页时会优先使用实时 quote 触发。
                            </Text>
                        </div>
                        {controls}
                    </div>
                    <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                        message="提醒规则保存在当前浏览器"
                        description="适合个人工作台使用。切换浏览器、设备或清理本地数据后，需要重新配置提醒。"
                    />
                </div>
            ) : null}

            <Space wrap size={[8, 8]} style={{ marginBottom: 16 }}>
                <Tag color="success">监控中 {activeAlertCount}</Tag>
                <Tag color="error">已触发 {triggeredAlertCount}</Tag>
                <Tag>已暂停 {pausedAlertCount}</Tag>
            </Space>

            <Table
                dataSource={alerts}
                columns={columns}
                rowKey="id"
                pagination={{ pageSize: 6 }}
                locale={{ emptyText: '暂无实时提醒' }}
            />

            <Modal
                title="添加实时提醒"
                open={modalVisible}
                onCancel={() => setModalVisible(false)}
                footer={null}
            >
                {prefillDraft?.sourceTitle ? (
                    <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 16 }}
                        message={`从「${prefillDraft.sourceTitle}」快速创建`}
                        description={prefillDraft.sourceDescription || '已为你带入该异动对应的默认规则，你可以继续微调阈值后保存。'}
                    />
                ) : null}
                <Form
                    form={form}
                    onFinish={addAlert}
                    layout="vertical"
                    initialValues={{ condition: DEFAULT_CONDITION }}
                >
                    <Form.Item
                        name="symbol"
                        label="股票代码"
                        rules={[{ required: true, message: '请输入股票代码' }]}
                    >
                        <Input placeholder="例如: AAPL" />
                    </Form.Item>

                    <Form.Item
                        name="condition"
                        label="触发条件"
                        rules={[{ required: true, message: '请选择条件' }]}
                    >
                        <Select placeholder="选择条件">
                            {CONDITION_OPTIONS.map((option) => (
                                <Option key={option.value} value={option.value}>
                                    {option.label}
                                </Option>
                            ))}
                        </Select>
                    </Form.Item>

                    {selectedCondition.needsThreshold && (
                        <Form.Item
                            name="threshold"
                            label={selectedCondition.thresholdLabel}
                            rules={[{ required: true, message: '请输入阈值' }]}
                        >
                            <InputNumber
                                min={selectedCondition.value === 'price_above'
                                    || selectedCondition.value === 'price_below'
                                    || selectedCondition.value === 'relative_volume_above'
                                    ? 0
                                    : undefined}
                                step={selectedCondition.step || 0.01}
                                style={{ width: '100%' }}
                                addonBefore={selectedCondition.prefix}
                                addonAfter={selectedCondition.suffix}
                                placeholder="请输入阈值"
                            />
                        </Form.Item>
                    )}

                    <Form.Item>
                        <Button type="primary" htmlType="submit" block>
                            添加提醒规则
                        </Button>
                    </Form.Item>
                </Form>
            </Modal>
        </>
    );

    if (embedded) {
        return content;
    }

    return (
        <div>
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: 16,
                flexWrap: 'wrap',
                marginBottom: 16
            }}>
                <Space>
                    <BellOutlined />
                    <span>实时提醒</span>
                    <Badge count={activeAlertCount} />
                </Space>
                {controls}
            </div>
            {content}
        </div>
    );
};

export default PriceAlerts;
