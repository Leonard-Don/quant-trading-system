import React, { useState } from 'react';
import {
    Card,
    Switch,
    Slider,
    Space,
    Typography,
    Row,
    Col,
    Collapse,
    InputNumber,
    Divider,
    Tag
} from 'antd';
import {
    LineChartOutlined,
    SettingOutlined,
    ReloadOutlined
} from '@ant-design/icons';

const { Text } = Typography;
const { Panel } = Collapse;

/**
 * 技术指标叠加控制面板
 * 控制图表上显示的技术指标及其参数
 */
const IndicatorOverlay = ({
    indicators = {},
    onChange,
    compact = false
}) => {
    // 默认指标配置
    const defaultIndicators = {
        sma: { enabled: false, periods: [20, 50], color: ['#faad14', '#13c2c2'] },
        ema: { enabled: false, periods: [12, 26], color: ['#722ed1', '#eb2f96'] },
        bollinger: { enabled: false, period: 20, stdDev: 2, color: '#1890ff' },
        rsi: { enabled: false, period: 14, overbought: 70, oversold: 30 },
        macd: { enabled: false, fast: 12, slow: 26, signal: 9 },
        volume: { enabled: true }
    };

    const [config, setConfig] = useState({ ...defaultIndicators, ...indicators });

    // 更新配置
    const updateConfig = (key, value) => {
        const newConfig = { ...config, [key]: { ...config[key], ...value } };
        setConfig(newConfig);
        onChange?.(newConfig);
    };

    // 切换指标开关
    const toggleIndicator = (key, enabled) => {
        updateConfig(key, { enabled });
    };

    // 重置所有指标
    const resetAll = () => {
        setConfig(defaultIndicators);
        onChange?.(defaultIndicators);
    };

    // 紧凑模式 - 只显示开关
    if (compact) {
        return (
            <Space wrap size="small">
                {Object.entries(config).map(([key, value]) => (
                    <Tag
                        key={key}
                        color={value.enabled ? 'blue' : 'default'}
                        style={{ cursor: 'pointer' }}
                        onClick={() => toggleIndicator(key, !value.enabled)}
                    >
                        {key.toUpperCase()}
                    </Tag>
                ))}
            </Space>
        );
    }

    return (
        <Card
            title={
                <Space>
                    <SettingOutlined />
                    <span>技术指标设置</span>
                </Space>
            }
            size="small"
            extra={
                <a onClick={resetAll} style={{ fontSize: 12 }}>
                    <ReloadOutlined /> 重置
                </a>
            }
        >
            <Collapse ghost defaultActiveKey={['trend', 'momentum']}>
                {/* 趋势指标 */}
                <Panel header="趋势指标" key="trend">
                    {/* SMA */}
                    <Row align="middle" style={{ marginBottom: 12 }}>
                        <Col span={8}>
                            <Switch
                                size="small"
                                checked={config.sma.enabled}
                                onChange={(checked) => toggleIndicator('sma', checked)}
                            />
                            <Text style={{ marginLeft: 8 }}>SMA</Text>
                        </Col>
                        <Col span={16}>
                            {config.sma.enabled && (
                                <Space size="small">
                                    <InputNumber
                                        size="small"
                                        min={5}
                                        max={200}
                                        value={config.sma.periods[0]}
                                        onChange={(v) => updateConfig('sma', {
                                            periods: [v, config.sma.periods[1]]
                                        })}
                                        style={{ width: 60 }}
                                    />
                                    <InputNumber
                                        size="small"
                                        min={5}
                                        max={200}
                                        value={config.sma.periods[1]}
                                        onChange={(v) => updateConfig('sma', {
                                            periods: [config.sma.periods[0], v]
                                        })}
                                        style={{ width: 60 }}
                                    />
                                </Space>
                            )}
                        </Col>
                    </Row>

                    {/* EMA */}
                    <Row align="middle" style={{ marginBottom: 12 }}>
                        <Col span={8}>
                            <Switch
                                size="small"
                                checked={config.ema.enabled}
                                onChange={(checked) => toggleIndicator('ema', checked)}
                            />
                            <Text style={{ marginLeft: 8 }}>EMA</Text>
                        </Col>
                        <Col span={16}>
                            {config.ema.enabled && (
                                <Space size="small">
                                    <InputNumber
                                        size="small"
                                        min={5}
                                        max={200}
                                        value={config.ema.periods[0]}
                                        onChange={(v) => updateConfig('ema', {
                                            periods: [v, config.ema.periods[1]]
                                        })}
                                        style={{ width: 60 }}
                                    />
                                    <InputNumber
                                        size="small"
                                        min={5}
                                        max={200}
                                        value={config.ema.periods[1]}
                                        onChange={(v) => updateConfig('ema', {
                                            periods: [config.ema.periods[0], v]
                                        })}
                                        style={{ width: 60 }}
                                    />
                                </Space>
                            )}
                        </Col>
                    </Row>

                    {/* Bollinger Bands */}
                    <Row align="middle">
                        <Col span={8}>
                            <Switch
                                size="small"
                                checked={config.bollinger.enabled}
                                onChange={(checked) => toggleIndicator('bollinger', checked)}
                            />
                            <Text style={{ marginLeft: 8 }}>布林带</Text>
                        </Col>
                        <Col span={16}>
                            {config.bollinger.enabled && (
                                <Space size="small">
                                    <Text style={{ fontSize: 11 }}>周期:</Text>
                                    <InputNumber
                                        size="small"
                                        min={5}
                                        max={50}
                                        value={config.bollinger.period}
                                        onChange={(v) => updateConfig('bollinger', { period: v })}
                                        style={{ width: 55 }}
                                    />
                                    <Text style={{ fontSize: 11 }}>标准差:</Text>
                                    <InputNumber
                                        size="small"
                                        min={1}
                                        max={4}
                                        step={0.5}
                                        value={config.bollinger.stdDev}
                                        onChange={(v) => updateConfig('bollinger', { stdDev: v })}
                                        style={{ width: 55 }}
                                    />
                                </Space>
                            )}
                        </Col>
                    </Row>
                </Panel>

                {/* 动量指标 */}
                <Panel header="动量指标" key="momentum">
                    {/* RSI */}
                    <Row align="middle" style={{ marginBottom: 12 }}>
                        <Col span={8}>
                            <Switch
                                size="small"
                                checked={config.rsi.enabled}
                                onChange={(checked) => toggleIndicator('rsi', checked)}
                            />
                            <Text style={{ marginLeft: 8 }}>RSI</Text>
                        </Col>
                        <Col span={16}>
                            {config.rsi.enabled && (
                                <Space size="small">
                                    <Text style={{ fontSize: 11 }}>周期:</Text>
                                    <InputNumber
                                        size="small"
                                        min={5}
                                        max={30}
                                        value={config.rsi.period}
                                        onChange={(v) => updateConfig('rsi', { period: v })}
                                        style={{ width: 55 }}
                                    />
                                </Space>
                            )}
                        </Col>
                    </Row>

                    {/* MACD */}
                    <Row align="middle">
                        <Col span={8}>
                            <Switch
                                size="small"
                                checked={config.macd.enabled}
                                onChange={(checked) => toggleIndicator('macd', checked)}
                            />
                            <Text style={{ marginLeft: 8 }}>MACD</Text>
                        </Col>
                        <Col span={16}>
                            {config.macd.enabled && (
                                <Space size="small" wrap>
                                    <span>
                                        <Text style={{ fontSize: 10 }}>快:</Text>
                                        <InputNumber
                                            size="small"
                                            min={5}
                                            max={20}
                                            value={config.macd.fast}
                                            onChange={(v) => updateConfig('macd', { fast: v })}
                                            style={{ width: 45 }}
                                        />
                                    </span>
                                    <span>
                                        <Text style={{ fontSize: 10 }}>慢:</Text>
                                        <InputNumber
                                            size="small"
                                            min={15}
                                            max={50}
                                            value={config.macd.slow}
                                            onChange={(v) => updateConfig('macd', { slow: v })}
                                            style={{ width: 45 }}
                                        />
                                    </span>
                                    <span>
                                        <Text style={{ fontSize: 10 }}>信号:</Text>
                                        <InputNumber
                                            size="small"
                                            min={5}
                                            max={20}
                                            value={config.macd.signal}
                                            onChange={(v) => updateConfig('macd', { signal: v })}
                                            style={{ width: 45 }}
                                        />
                                    </span>
                                </Space>
                            )}
                        </Col>
                    </Row>
                </Panel>

                {/* 成交量 */}
                <Panel header="其他" key="other">
                    <Row align="middle">
                        <Col span={8}>
                            <Switch
                                size="small"
                                checked={config.volume.enabled}
                                onChange={(checked) => toggleIndicator('volume', checked)}
                            />
                            <Text style={{ marginLeft: 8 }}>成交量</Text>
                        </Col>
                    </Row>
                </Panel>
            </Collapse>

            {/* 当前启用的指标汇总 */}
            <Divider style={{ margin: '12px 0' }} />
            <div>
                <Text type="secondary" style={{ fontSize: 11 }}>当前启用: </Text>
                {Object.entries(config)
                    .filter(([_, v]) => v.enabled)
                    .map(([key]) => (
                        <Tag key={key} color="blue" style={{ fontSize: 10 }}>
                            {key.toUpperCase()}
                        </Tag>
                    ))}
                {Object.values(config).every(v => !v.enabled) && (
                    <Text type="secondary" style={{ fontSize: 11 }}>无</Text>
                )}
            </div>
        </Card>
    );
};

export default IndicatorOverlay;
