import React, { useState, useEffect, useCallback } from 'react';
import {
    Card,
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
    Tooltip
} from 'antd';
import {
    BellOutlined,
    PlusOutlined,
    DeleteOutlined,
    CheckCircleOutlined,
    AlertOutlined,
    SoundOutlined
} from '@ant-design/icons';

const { Option } = Select;

/**
 * 价格提醒组件
 * 支持设置价格上限/下限提醒，并通过浏览器通知提醒用户
 */
const PriceAlerts = () => {
    const [alerts, setAlerts] = useState([]);
    const [modalVisible, setModalVisible] = useState(false);
    const [form] = Form.useForm();
    const [notificationsEnabled, setNotificationsEnabled] = useState(false);
    // eslint-disable-next-line no-unused-vars
    const [triggeredAlerts, setTriggeredAlerts] = useState([]);

    // 从 localStorage 加载提醒
    useEffect(() => {
        const saved = localStorage.getItem('price_alerts');
        if (saved) {
            try {
                setAlerts(JSON.parse(saved));
            } catch (e) {
                console.error('Failed to load alerts:', e);
            }
        }

        // 检查通知权限
        if ('Notification' in window) {
            setNotificationsEnabled(Notification.permission === 'granted');
        }
    }, []);

    // 保存到 localStorage
    useEffect(() => {
        localStorage.setItem('price_alerts', JSON.stringify(alerts));
    }, [alerts]);

    // 请求通知权限
    const requestNotificationPermission = async () => {
        if (!('Notification' in window)) {
            message.warning('您的浏览器不支持通知功能');
            return;
        }

        const permission = await Notification.requestPermission();
        setNotificationsEnabled(permission === 'granted');

        if (permission === 'granted') {
            message.success('通知权限已开启');
            // 发送测试通知
            new Notification('价格提醒已启用', {
                body: '当股票价格触发您设定的条件时，您将收到通知',
                icon: '/favicon.ico'
            });
        } else {
            message.warning('通知权限被拒绝');
        }
    };

    // 检查价格并触发提醒
    const checkPrices = useCallback(async () => {
        const activeAlerts = alerts.filter(a => a.active && !a.triggered);
        if (activeAlerts.length === 0) return;

        for (const alert of activeAlerts) {
            try {
                const response = await fetch('http://localhost:8000/market-data', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbol: alert.symbol, period: '1d' })
                });

                if (!response.ok) continue;

                const result = await response.json();
                const prices = result.data?.data || result.data || [];
                if (prices.length === 0) continue;

                const currentPrice = prices[prices.length - 1].close;
                let shouldTrigger = false;

                if (alert.condition === 'above' && currentPrice >= alert.price) {
                    shouldTrigger = true;
                } else if (alert.condition === 'below' && currentPrice <= alert.price) {
                    shouldTrigger = true;
                }

                if (shouldTrigger) {
                    // 标记为已触发
                    setAlerts(prev => prev.map(a =>
                        a.id === alert.id ? { ...a, triggered: true, triggerPrice: currentPrice, triggerTime: new Date().toISOString() } : a
                    ));

                    setTriggeredAlerts(prev => [...prev, { ...alert, triggerPrice: currentPrice }]);

                    // 发送通知
                    if (notificationsEnabled) {
                        new Notification(`🔔 价格提醒: ${alert.symbol}`, {
                            body: `${alert.symbol} 当前价格 $${currentPrice.toFixed(2)} 已${alert.condition === 'above' ? '突破' : '跌破'} $${alert.price}`,
                            icon: '/favicon.ico',
                            tag: alert.id
                        });
                    }

                    // 播放提示音
                    try {
                        const audio = new Audio('data:audio/wav;base64,UklGRjIAAABXQVZFZm10IBIAAAABAAEAQB8AAEAfAAABAAgAAABmYWN0BAAAAAAAAABkYXRhAAAAAA==');
                        audio.play().catch(() => { });
                    } catch (e) { }

                    message.warning({
                        content: `${alert.symbol} 价格提醒已触发！当前: $${currentPrice.toFixed(2)}`,
                        duration: 5
                    });
                }
            } catch (err) {
                console.error('检查价格失败:', err);
            }
        }
    }, [alerts, notificationsEnabled]);

    // 定期检查价格 (每30秒)
    useEffect(() => {
        const interval = setInterval(checkPrices, 30000);
        return () => clearInterval(interval);
    }, [checkPrices]);

    // 添加新提醒
    const addAlert = (values) => {
        const newAlert = {
            id: `alert_${Date.now()}`,
            symbol: values.symbol.toUpperCase(),
            condition: values.condition,
            price: values.price,
            active: true,
            triggered: false,
            createdAt: new Date().toISOString()
        };

        setAlerts(prev => [...prev, newAlert]);
        setModalVisible(false);
        form.resetFields();
        message.success('价格提醒已添加');
    };

    // 删除提醒
    const deleteAlert = (id) => {
        setAlerts(prev => prev.filter(a => a.id !== id));
        message.success('提醒已删除');
    };

    // 切换提醒状态
    const toggleAlert = (id) => {
        setAlerts(prev => prev.map(a =>
            a.id === id ? { ...a, active: !a.active } : a
        ));
    };

    // 重置已触发的提醒
    const resetAlert = (id) => {
        setAlerts(prev => prev.map(a =>
            a.id === id ? { ...a, triggered: false, triggerPrice: null, triggerTime: null } : a
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
            dataIndex: 'condition',
            key: 'condition',
            render: (cond, record) => (
                <span>
                    {cond === 'above' ? '≥' : '≤'} <strong>${record.price}</strong>
                </span>
            )
        },
        {
            title: '状态',
            key: 'status',
            render: (_, record) => {
                if (record.triggered) {
                    return (
                        <Tooltip title={`触发于 ${new Date(record.triggerTime).toLocaleString()}, 价格: $${record.triggerPrice?.toFixed(2)}`}>
                            <Tag color="error" icon={<AlertOutlined />}>已触发</Tag>
                        </Tooltip>
                    );
                }
                return record.active ?
                    <Tag color="success" icon={<CheckCircleOutlined />}>监控中</Tag> :
                    <Tag color="default">已暂停</Tag>;
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

    return (
        <Card
            title={
                <Space>
                    <BellOutlined />
                    <span>价格提醒</span>
                    <Badge count={alerts.filter(a => a.active && !a.triggered).length} />
                </Space>
            }
            extra={
                <Space>
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
            }
        >
            <Table
                dataSource={alerts}
                columns={columns}
                rowKey="id"
                pagination={{ pageSize: 5 }}
                locale={{ emptyText: '暂无价格提醒' }}
            />

            <Modal
                title="添加价格提醒"
                open={modalVisible}
                onCancel={() => setModalVisible(false)}
                footer={null}
            >
                <Form form={form} onFinish={addAlert} layout="vertical">
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
                            <Option value="above">价格 ≥ (突破提醒)</Option>
                            <Option value="below">价格 ≤ (跌破提醒)</Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="price"
                        label="目标价格"
                        rules={[{ required: true, message: '请输入价格' }]}
                    >
                        <InputNumber
                            prefix="$"
                            min={0}
                            step={0.01}
                            style={{ width: '100%' }}
                            placeholder="例如: 150.00"
                        />
                    </Form.Item>

                    <Form.Item>
                        <Button type="primary" htmlType="submit" block>
                            添加提醒
                        </Button>
                    </Form.Item>
                </Form>
            </Modal>
        </Card>
    );
};

export default PriceAlerts;
