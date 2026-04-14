import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
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
import * as api from '../services/api';
import * as realtimePreferences from '../hooks/useRealtimePreferences';
import {
    ALERT_HIT_HISTORY_STORAGE_KEY,
    buildAlertHitHistoryEntry,
    evaluateRealtimeAlert,
    getAlertConditionLabel,
    loadAlertHitHistory,
    MAX_ALERT_HIT_HISTORY,
    normalizePriceAlert,
    summarizeAlertHitHistory,
} from '../utils/realtimeSignals';

const { Option } = Select;
const { Text, Title } = Typography;

const STORAGE_KEY = 'price_alerts';
const DEFAULT_CONDITION = 'price_above';
const DEFAULT_ALERT_COOLDOWN_MINUTES = 15;
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
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            return;
        }

        const context = new AudioContextClass();
        const now = context.currentTime;
        const gains = [0, 0.16];

        gains.forEach((gainValue, index) => {
            const oscillator = context.createOscillator();
            const gainNode = context.createGain();
            const startAt = now + index * 0.14;
            const endAt = startAt + 0.08;

            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(index === 0 ? 880 : 1174, startAt);
            gainNode.gain.setValueAtTime(0.0001, startAt);
            gainNode.gain.linearRampToValueAtTime(gainValue, startAt + 0.01);
            gainNode.gain.exponentialRampToValueAtTime(0.0001, endAt);

            oscillator.connect(gainNode);
            gainNode.connect(context.destination);
            oscillator.start(startAt);
            oscillator.stop(endAt + 0.01);
        });

        setTimeout(() => {
            context.close().catch(() => {});
        }, 400);
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
    initialAlertHitHistory = null,
    onAlertHitHistoryChange,
    onAlertTriggered,
}) => {
    const [alerts, setAlerts] = useState([]);
    const [alertHitHistory, setAlertHitHistory] = useState(() => (
        Array.isArray(initialAlertHitHistory) ? initialAlertHitHistory : loadAlertHitHistory()
    ));
    const [modalVisible, setModalVisible] = useState(false);
    const [isAlertsHydrated, setIsAlertsHydrated] = useState(false);
    const [selectedAlertIds, setSelectedAlertIds] = useState([]);
    const [symbolFilter, setSymbolFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('all');
    const [conditionFilter, setConditionFilter] = useState('all');
    const [form] = Form.useForm();
    const [notificationsEnabled, setNotificationsEnabled] = useState(false);
    const triggeredAlertIdsRef = useRef(new Set());
    const lastSyncedAlertsRef = useRef('');
    const saveAlertsTimerRef = useRef(null);
    const latestAlertsRef = useRef('');
    const realtimeProfileIdRef = useRef(realtimePreferences.loadRealtimeProfileId());
    // eslint-disable-next-line no-unused-vars
    const [triggeredAlerts, setTriggeredAlerts] = useState([]);
    const watchedCondition = Form.useWatch('condition', form) || DEFAULT_CONDITION;
    const selectedCondition = CONDITION_OPTIONS.find((item) => item.value === watchedCondition) || CONDITION_OPTIONS[0];
    const conditionCounts = useMemo(() => alerts.reduce((result, item) => {
        const key = item?.condition || 'unknown';
        result[key] = (result[key] || 0) + 1;
        return result;
    }, {}), [alerts]);
    const filteredAlerts = useMemo(() => {
        const normalizedQuery = symbolFilter.trim().toUpperCase();

        return alerts.filter((item) => {
            if (normalizedQuery && !item.symbol?.toUpperCase().includes(normalizedQuery)) {
                return false;
            }

            if (statusFilter === 'armed' && (!item.active || item.triggered)) {
                return false;
            }

            if (statusFilter === 'paused' && (item.active || item.triggered)) {
                return false;
            }

            if (statusFilter === 'triggered' && !item.triggered) {
                return false;
            }

            if (conditionFilter !== 'all' && item.condition !== conditionFilter) {
                return false;
            }

            return true;
        });
    }, [alerts, conditionFilter, statusFilter, symbolFilter]);
    const selectedAlerts = useMemo(() => alerts.filter((item) => selectedAlertIds.includes(item.id)), [alerts, selectedAlertIds]);
    const selectedTriggeredCount = selectedAlerts.filter((item) => item.triggered).length;
    const selectedPausedCount = selectedAlerts.filter((item) => !item.active && !item.triggered).length;

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
        latestAlertsRef.current = JSON.stringify(alerts);
    }, [alerts]);

    useEffect(() => {
        if (!Array.isArray(initialAlertHitHistory)) {
            return;
        }

        setAlertHitHistory(initialAlertHitHistory);
    }, [initialAlertHitHistory]);

    useEffect(() => {
        let isCancelled = false;
        const initialSnapshot = latestAlertsRef.current || JSON.stringify([]);
        const initialAlertHistorySnapshot = JSON.stringify(
            Array.isArray(initialAlertHitHistory) ? initialAlertHitHistory : alertHitHistory
        );

        const hydrateAlerts = async () => {
            try {
                const response = await api.getRealtimeAlerts(realtimeProfileIdRef.current);
                if (!response.success || isCancelled) {
                    return;
                }

                const backendAlerts = Array.isArray(response.data?.alerts)
                    ? normalizeStoredAlerts(response.data.alerts)
                    : [];
                const backendAlertHitHistory = Array.isArray(response.data?.alert_hit_history)
                    ? response.data.alert_hit_history.slice(0, MAX_ALERT_HIT_HISTORY)
                    : [];
                const userChangedAlertsDuringHydration = (latestAlertsRef.current || initialSnapshot) !== initialSnapshot;
                const currentAlertHistorySnapshot = JSON.stringify(
                    Array.isArray(initialAlertHitHistory) ? initialAlertHitHistory : alertHitHistory
                );
                const userChangedAlertHistoryDuringHydration = currentAlertHistorySnapshot !== initialAlertHistorySnapshot;

                let localAlerts = [];
                let localAlertHitHistory = [];
                try {
                    localAlerts = JSON.parse(initialSnapshot);
                } catch (error) {
                    console.warn('Failed to parse initial realtime alerts snapshot, falling back to current state:', error);
                }
                try {
                    localAlertHitHistory = JSON.parse(initialAlertHistorySnapshot);
                } catch (error) {
                    console.warn('Failed to parse initial alert hit history snapshot, falling back to current state:', error);
                }

                if (!userChangedAlertsDuringHydration) {
                    if (backendAlerts.length === 0 && Array.isArray(localAlerts) && localAlerts.length > 0) {
                        lastSyncedAlertsRef.current = '';
                    } else {
                        setAlerts(backendAlerts);
                        lastSyncedAlertsRef.current = JSON.stringify({
                            alerts: backendAlerts,
                            alert_hit_history: backendAlertHitHistory,
                        });
                    }
                }

                if (!userChangedAlertHistoryDuringHydration) {
                    if (backendAlertHitHistory.length === 0 && Array.isArray(localAlertHitHistory) && localAlertHitHistory.length > 0) {
                        onAlertHitHistoryChange?.(localAlertHitHistory);
                    } else {
                        setAlertHitHistory(backendAlertHitHistory);
                        onAlertHitHistoryChange?.(backendAlertHitHistory);
                    }
                }
            } catch (error) {
                console.warn('Failed to load realtime alerts from backend, falling back to local cache:', error);
            } finally {
                if (!isCancelled) {
                    setIsAlertsHydrated(true);
                }
            }
        };

        hydrateAlerts();

        return () => {
            isCancelled = true;
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
    }, [alerts]);

    useEffect(() => {
        if (!isAlertsHydrated) {
            return undefined;
        }

        const serializedPayload = JSON.stringify({
            alerts,
            alert_hit_history: alertHitHistory,
        });
        if (serializedPayload === lastSyncedAlertsRef.current) {
            return undefined;
        }

        if (saveAlertsTimerRef.current) {
            clearTimeout(saveAlertsTimerRef.current);
        }

        saveAlertsTimerRef.current = setTimeout(async () => {
            try {
                await api.updateRealtimeAlerts(alerts, realtimeProfileIdRef.current, alertHitHistory);
                lastSyncedAlertsRef.current = serializedPayload;
            } catch (error) {
                console.warn('Failed to sync realtime alerts to backend, keeping local cache only:', error);
            }
        }, 500);

        return () => {
            if (saveAlertsTimerRef.current) {
                clearTimeout(saveAlertsTimerRef.current);
                saveAlertsTimerRef.current = null;
            }
        };
    }, [alertHitHistory, alerts, isAlertsHydrated]);

    useEffect(() => {
        localStorage.setItem(ALERT_HIT_HISTORY_STORAGE_KEY, JSON.stringify(alertHitHistory));
    }, [alertHitHistory]);

    useEffect(() => {
        onAlertHitHistoryChange?.(alertHitHistory);
    }, [alertHitHistory, onAlertHitHistoryChange]);

    useEffect(() => {
        triggeredAlertIdsRef.current = new Set(
            alerts.filter((item) => item?.triggered && item?.id).map((item) => item.id)
        );
    }, [alerts]);

    useEffect(() => {
        setSelectedAlertIds((prev) => prev.filter((id) => alerts.some((item) => item.id === id)));
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

    const markTriggered = useCallback((alert, triggerValue, content, quote = null) => {
        if (alert?.id && triggeredAlertIdsRef.current.has(alert.id)) {
            return;
        }
        if (alert?.id) {
            triggeredAlertIdsRef.current.add(alert.id);
        }

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
        const historyEntry = buildAlertHitHistoryEntry({
            alert,
            triggerValue,
            message: content,
            quote,
        });
        setAlertHitHistory((prev) => [historyEntry, ...prev].slice(0, MAX_ALERT_HIT_HISTORY));
        onAlertTriggered?.(historyEntry);
        void api.recordRealtimeAlertHit(
            historyEntry,
            realtimeProfileIdRef.current,
            {
                severity: ['price_below', 'change_pct_below', 'touch_low'].includes(alert?.condition) ? 'critical' : 'warning',
                persist_event_record: true,
            }
        ).catch((error) => {
            console.warn('Failed to publish realtime alert hit to unified bus:', error);
        });

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
    }, [notificationsEnabled, onAlertTriggered]);

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
                markTriggered(alert, result.triggerValue, result.message || `${alert.symbol} 实时提醒已触发`, quote);
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
                const result = await api.getMarketData({ symbol: normalizedAlert.symbol, period: '1d' });
                const prices = result.data?.data || result.data || [];
                if (prices.length === 0) continue;

                const currentPrice = prices[prices.length - 1].close;
                const fallbackQuote = { price: currentPrice };
                const evaluation = evaluateRealtimeAlert(normalizedAlert, fallbackQuote);
                if (evaluation.triggered) {
                    markTriggered(
                        normalizedAlert,
                        evaluation.triggerValue,
                        evaluation.message || `${normalizedAlert.symbol} 价格提醒已触发`,
                        fallbackQuote
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
            cooldownMinutes: Number(values.cooldownMinutes) || DEFAULT_ALERT_COOLDOWN_MINUTES,
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
        triggeredAlertIdsRef.current.delete(id);
        setAlerts((prev) => prev.filter((item) => item.id !== id));
        setSelectedAlertIds((prev) => prev.filter((item) => item !== id));
        message.success('提醒已删除');
    };

    const toggleAlert = (id) => {
        setAlerts((prev) => prev.map((item) =>
            item.id === id
                ? {
                    ...item,
                    active: !item.active,
                    armedAt: !item.active
                        ? new Date(Date.now() + Math.max(5000, (item.cooldownMinutes || DEFAULT_ALERT_COOLDOWN_MINUTES) * 60 * 1000)).toISOString()
                        : item.armedAt,
                }
                : item
        ));
    };

    const resetAlert = (id) => {
        triggeredAlertIdsRef.current.delete(id);
        setAlerts((prev) => prev.map((item) =>
            item.id === id
                ? {
                    ...item,
                    triggered: false,
                    triggerValue: null,
                    triggerTime: null,
                    armedAt: new Date(Date.now() + Math.max(5000, (item.cooldownMinutes || DEFAULT_ALERT_COOLDOWN_MINUTES) * 60 * 1000)).toISOString(),
                }
                : item
        ));
        message.success('提醒已重置，并进入冷却期');
    };

    const clearSelectedAlerts = () => {
        setSelectedAlertIds([]);
    };

    const pauseSelectedAlerts = () => {
        if (selectedAlertIds.length === 0) {
            return;
        }

        setAlerts((prev) => prev.map((item) => (
            selectedAlertIds.includes(item.id)
                ? { ...item, active: false }
                : item
        )));
        message.success(`已暂停 ${selectedAlertIds.length} 条提醒`);
    };

    const resumeSelectedAlerts = () => {
        if (selectedAlertIds.length === 0) {
            return;
        }

        setAlerts((prev) => prev.map((item) => (
            selectedAlertIds.includes(item.id)
                ? {
                    ...item,
                    active: true,
                    armedAt: new Date(Date.now() + Math.max(5000, (item.cooldownMinutes || DEFAULT_ALERT_COOLDOWN_MINUTES) * 60 * 1000)).toISOString(),
                  }
                : item
        )));
        message.success(`已恢复 ${selectedAlertIds.length} 条提醒`);
    };

    const resetSelectedAlerts = () => {
        if (selectedAlertIds.length === 0) {
            return;
        }

        selectedAlertIds.forEach((id) => triggeredAlertIdsRef.current.delete(id));
        setAlerts((prev) => prev.map((item) => (
            selectedAlertIds.includes(item.id)
                ? {
                    ...item,
                    triggered: false,
                    triggerValue: null,
                    triggerTime: null,
                    active: true,
                    armedAt: new Date(Date.now() + Math.max(5000, (item.cooldownMinutes || DEFAULT_ALERT_COOLDOWN_MINUTES) * 60 * 1000)).toISOString(),
                  }
                : item
        )));
        message.success(`已重置 ${selectedAlertIds.length} 条提醒，并重新进入冷却期`);
    };

    const deleteSelectedAlerts = () => {
        if (selectedAlertIds.length === 0) {
            return;
        }

        selectedAlertIds.forEach((id) => triggeredAlertIdsRef.current.delete(id));
        setAlerts((prev) => prev.filter((item) => !selectedAlertIds.includes(item.id)));
        setSelectedAlertIds([]);
        message.success(`已删除 ${selectedAlertIds.length} 条提醒`);
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
            title: '冷却',
            key: 'cooldown',
            render: (_, record) => (
                <Tag style={{ borderRadius: 999, paddingInline: 10 }}>
                    {record.cooldownMinutes || DEFAULT_ALERT_COOLDOWN_MINUTES} 分钟
                </Tag>
            )
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
    const alertHitSummary = summarizeAlertHitHistory(alertHitHistory);
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

    const managementToolbar = (
        <div
            style={{
                display: 'grid',
                gap: 12,
                marginBottom: 16,
                padding: 16,
                borderRadius: 18,
                border: '1px solid var(--border-color)',
                background: 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)',
            }}
        >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                <div>
                    <Title level={5} style={{ margin: 0 }}>提醒规则管理</Title>
                    <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                        通过条件分组、状态筛选和批量操作管理较多提醒，不用逐条翻找。
                    </Text>
                </div>
                <Space wrap>
                    <Tag color="blue">已选 {selectedAlertIds.length}</Tag>
                    <Tag>筛选结果 {filteredAlerts.length}</Tag>
                    <Tag color="error">已触发 {selectedTriggeredCount}</Tag>
                    <Tag>已暂停 {selectedPausedCount}</Tag>
                </Space>
            </div>

            <Space wrap>
                <Input
                    allowClear
                    placeholder="筛选提醒代码"
                    value={symbolFilter}
                    onChange={(event) => setSymbolFilter(event.target.value)}
                    style={{ width: 180 }}
                />
                <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 160 }}>
                    <Option value="all">全部状态</Option>
                    <Option value="armed">监控中</Option>
                    <Option value="triggered">已触发</Option>
                    <Option value="paused">已暂停</Option>
                </Select>
                <Select value={conditionFilter} onChange={setConditionFilter} style={{ width: 220 }}>
                    <Option value="all">全部条件</Option>
                    {CONDITION_OPTIONS.map((option) => (
                        <Option key={option.value} value={option.value}>
                            {option.label}
                        </Option>
                    ))}
                </Select>
                <Button onClick={clearSelectedAlerts}>清空选择</Button>
                <Button onClick={pauseSelectedAlerts} disabled={selectedAlertIds.length === 0}>批量暂停</Button>
                <Button onClick={resumeSelectedAlerts} disabled={selectedAlertIds.length === 0}>批量启用</Button>
                <Button onClick={resetSelectedAlerts} disabled={selectedAlertIds.length === 0}>批量重置</Button>
                <Button danger onClick={deleteSelectedAlerts} disabled={selectedAlertIds.length === 0}>批量删除</Button>
            </Space>

            <Space wrap>
                <Tag
                    color={conditionFilter === 'all' ? 'blue' : 'default'}
                    style={{ borderRadius: 999, cursor: 'pointer', paddingInline: 10 }}
                    onClick={() => setConditionFilter('all')}
                >
                    全部条件 {alerts.length}
                </Tag>
                {CONDITION_OPTIONS.map((option) => (
                    <Tag
                        key={option.value}
                        color={conditionFilter === option.value ? 'processing' : 'default'}
                        style={{ borderRadius: 999, cursor: 'pointer', paddingInline: 10 }}
                        onClick={() => setConditionFilter(option.value)}
                    >
                        {option.label} {conditionCounts[option.value] || 0}
                    </Tag>
                ))}
            </Space>
        </div>
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
                        message="提醒规则会同步到当前实时工作台 profile"
                        description="本地缓存仍会保留一份，同时会像自选偏好一样同步到后端，换浏览器前至少能保住这套提醒规则。"
                    />
                </div>
            ) : null}

            <Space wrap size={[8, 8]} style={{ marginBottom: 16 }}>
                <Tag color="success">监控中 {activeAlertCount}</Tag>
                <Tag color="error">已触发 {triggeredAlertCount}</Tag>
                <Tag>已暂停 {pausedAlertCount}</Tag>
                <Tag color="processing">命中历史 {alertHitSummary.totalHits}</Tag>
            </Space>

            <div
                style={{
                    display: 'grid',
                    gap: 12,
                    marginBottom: 16,
                    padding: 16,
                    borderRadius: 18,
                    border: '1px solid var(--border-color)',
                    background: 'color-mix(in srgb, var(--bg-secondary) 90%, white 10%)',
                }}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                    <div>
                        <Title level={5} style={{ margin: 0 }}>提醒命中历史</Title>
                        <Text type="secondary" style={{ display: 'block', marginTop: 6 }}>
                            回看最近触发过的提醒，判断哪类规则更常命中、哪些标的更值得继续跟踪。
                        </Text>
                    </div>
                    <Space wrap>
                        <Tag color="blue">涉及标的 {alertHitSummary.uniqueSymbols}</Tag>
                        <Tag>高频条件 {alertHitSummary.topCondition}</Tag>
                    </Space>
                </div>

                {alertHitSummary.recentHits.length === 0 ? (
                    <Text type="secondary">最近还没有提醒命中记录，等实时行情触发后这里会自动沉淀。</Text>
                ) : (
                    <div style={{ display: 'grid', gap: 10 }}>
                        {alertHitSummary.recentHits.map((entry) => (
                            <div
                                key={entry.id}
                                style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    gap: 12,
                                    alignItems: 'center',
                                    flexWrap: 'wrap',
                                    padding: '12px 14px',
                                    borderRadius: 14,
                                    background: 'rgba(15, 23, 42, 0.04)',
                                }}
                            >
                                <div style={{ display: 'grid', gap: 4 }}>
                                    <Space wrap>
                                        <Tag color="processing" style={{ margin: 0 }}>{entry.symbol}</Tag>
                                        <Tag style={{ margin: 0 }}>{entry.conditionLabel}</Tag>
                                        <Text type="secondary" style={{ fontSize: 12 }}>
                                            {new Date(entry.triggerTime).toLocaleString()}
                                        </Text>
                                    </Space>
                                    <Text style={{ color: 'var(--text-primary)' }}>
                                        {entry.message}
                                    </Text>
                                </div>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                    触发价 {entry.triggerPrice === null || entry.triggerPrice === undefined ? '--' : Number(entry.triggerPrice).toFixed(2)}
                                </Text>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {managementToolbar}

            <Table
                dataSource={filteredAlerts}
                columns={columns}
                rowKey="id"
                rowSelection={{
                    selectedRowKeys: selectedAlertIds,
                    onChange: (keys) => setSelectedAlertIds(keys),
                }}
                pagination={{ pageSize: 8 }}
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
                    initialValues={{ condition: DEFAULT_CONDITION, cooldownMinutes: DEFAULT_ALERT_COOLDOWN_MINUTES }}
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
                            <Space.Compact style={{ width: '100%' }}>
                                {selectedCondition.prefix ? (
                                    <span
                                        style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            padding: '0 12px',
                                            border: '1px solid var(--border-color)',
                                            borderRight: 'none',
                                            borderRadius: '8px 0 0 8px',
                                            background: 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)',
                                            color: 'var(--text-secondary)',
                                            fontWeight: 600,
                                        }}
                                    >
                                        {selectedCondition.prefix}
                                    </span>
                                ) : null}
                                <InputNumber
                                    min={selectedCondition.value === 'price_above'
                                        || selectedCondition.value === 'price_below'
                                        || selectedCondition.value === 'relative_volume_above'
                                        ? 0
                                        : undefined}
                                    step={selectedCondition.step || 0.01}
                                    style={{ width: '100%' }}
                                    placeholder="请输入阈值"
                                />
                                {selectedCondition.suffix ? (
                                    <span
                                        style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            padding: '0 12px',
                                            border: '1px solid var(--border-color)',
                                            borderLeft: 'none',
                                            borderRadius: '0 8px 8px 0',
                                            background: 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)',
                                            color: 'var(--text-secondary)',
                                            fontWeight: 600,
                                        }}
                                    >
                                        {selectedCondition.suffix}
                                    </span>
                                ) : null}
                            </Space.Compact>
                        </Form.Item>
                    )}

                    <Form.Item
                        name="cooldownMinutes"
                        label="触发后冷却期（分钟）"
                    >
                        <InputNumber
                            min={1}
                            max={240}
                            step={1}
                            style={{ width: '100%' }}
                            placeholder="默认 15 分钟"
                        />
                    </Form.Item>

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
