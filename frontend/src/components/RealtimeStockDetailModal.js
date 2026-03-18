import React from 'react';
import { Modal, Row, Col, Tag, Empty, Typography } from 'antd';
import {
    ClockCircleOutlined,
    DotChartOutlined,
    FundOutlined,
    RiseOutlined,
} from '@ant-design/icons';
import MarketAnalysis from './MarketAnalysis';
import { STOCK_DATABASE } from '../constants/stocks';

const { Text } = Typography;

const SNAPSHOT_PANEL_BG = 'linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 14%, var(--bg-secondary) 86%) 0%, color-mix(in srgb, var(--accent-secondary) 14%, var(--bg-secondary) 86%) 100%)';
const SNAPSHOT_CARD_BG = 'color-mix(in srgb, var(--bg-secondary) 92%, white 8%)';

const getDisplayName = (symbol) => {
    const info = STOCK_DATABASE[symbol];
    return info?.cn || info?.en || symbol || '未知标的';
};

const getCategoryLabel = (symbol) => {
    const type = STOCK_DATABASE[symbol]?.type;

    switch (type) {
        case 'index':
            return '指数';
        case 'us':
            return '美股';
        case 'cn':
            return 'A股';
        case 'crypto':
            return '加密货币';
        case 'bond':
            return '债券';
        case 'future':
            return '期货';
        case 'option':
            return '期权';
        default:
            return '实时行情';
    }
};

const formatNumber = (value, digits = 2, fallback = '--') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return fallback;
    }
    return Number(value).toFixed(digits);
};

const formatSignedNumber = (value, digits = 2, suffix = '', fallback = '--') => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return fallback;
    }

    const numericValue = Number(value);
    return `${numericValue >= 0 ? '+' : ''}${numericValue.toFixed(digits)}${suffix}`;
};

const formatVolume = (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '--';
    }

    const volume = Number(value);
    if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
    if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
    if (volume >= 1e3) return `${(volume / 1e3).toFixed(2)}K`;
    return `${volume}`;
};

const formatTimestamp = (value) => {
    if (!value) return '--';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleString();
};

const formatSpread = (bid, ask) => {
    if ([bid, ask].some(value => value === null || value === undefined || Number.isNaN(Number(value)))) {
        return '--';
    }

    return Number(ask - bid).toFixed(2);
};

const formatRangePercent = (low, high, previousClose) => {
    if ([low, high, previousClose].some(value => value === null || value === undefined || Number.isNaN(Number(value))) || Number(previousClose) === 0) {
        return '--';
    }

    return `${(((Number(high) - Number(low)) / Number(previousClose)) * 100).toFixed(2)}%`;
};

const renderMetricCard = (label, value, subtle, accentColor) => (
    <div
        style={{
            height: '100%',
            padding: '14px 16px',
            borderRadius: 14,
            background: SNAPSHOT_CARD_BG,
            border: `1px solid ${accentColor || 'var(--border-color)'}`,
            boxShadow: '0 10px 24px rgba(15, 23, 42, 0.05)',
        }}
    >
        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.04em', marginBottom: 8 }}>
            {label}
        </div>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.15 }}>
            {value}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8, minHeight: 18 }}>
            {subtle || '\u00A0'}
        </div>
    </div>
);

const RealtimeStockDetailModal = ({ open, symbol, quote, onCancel }) => {
    const displaySymbol = symbol || quote?.symbol || '--';
    const displayName = getDisplayName(displaySymbol);
    const categoryLabel = getCategoryLabel(displaySymbol);
    const isPositive = Number(quote?.change ?? 0) >= 0;
    const changeColor = isPositive ? '#cf1322' : '#389e0d';
    const spreadValue = formatSpread(quote?.bid, quote?.ask);
    const rangePercent = formatRangePercent(quote?.low, quote?.high, quote?.previous_close);

    return (
        <Modal
            title={
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                            <span style={{ display: 'flex', alignItems: 'center', fontWeight: 800, fontSize: 18, color: 'var(--text-primary)' }}>
                                <FundOutlined style={{ marginRight: 8, color: '#1677ff' }} />
                                {displayName} 深度详情
                            </span>
                            <Tag color="blue" style={{ margin: 0, borderRadius: 999, paddingInline: 10, fontWeight: 700 }}>
                                {categoryLabel}
                            </Tag>
                            <Tag color={quote ? 'success' : 'default'} style={{ margin: 0, borderRadius: 999, paddingInline: 10, fontWeight: 700 }}>
                                {displaySymbol}
                            </Tag>
                        </div>
                        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                            实时快照与多维分析合并展示，适合直接在行情工作台里快速研判。
                        </div>
                    </div>

                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10, paddingBlock: 4, fontWeight: 700 }}>
                            日内振幅 {rangePercent}
                        </Tag>
                        <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 10, paddingBlock: 4, fontWeight: 700 }}>
                            点差 {spreadValue}
                        </Tag>
                    </div>
                </div>
            }
            open={open}
            onCancel={onCancel}
            footer={null}
            width={1280}
            destroyOnHidden
            modalRender={(node) => <div data-testid="realtime-stock-detail-modal">{node}</div>}
            styles={{
                body: {
                    padding: 20,
                    background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-primary) 92%, white 8%) 0%, var(--bg-primary) 220px)',
                },
            }}
        >
            <div style={{ display: 'grid', gap: 18 }}>
                <section
                    style={{
                        padding: 18,
                        borderRadius: 18,
                        background: SNAPSHOT_PANEL_BG,
                        border: '1px solid color-mix(in srgb, var(--accent-primary) 24%, var(--border-color) 76%)',
                        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.10)',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 14 }}>
                        <div style={{ display: 'grid', gap: 10 }}>
                            <div>
                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>标的代码</div>
                                <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.1 }}>
                                    {displaySymbol}
                                </div>
                                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 8 }}>
                                    {displayName}
                                </div>
                            </div>

                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(255,255,255,0.72)' }}>
                                    数据源 {quote?.source || '--'}
                                </Tag>
                                <Tag style={{ margin: 0, borderRadius: 999, borderColor: 'transparent', background: 'rgba(255,255,255,0.72)' }}>
                                    更新时间 {formatTimestamp(quote?.timestamp)}
                                </Tag>
                            </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                                实时变化
                            </div>
                            <div style={{ fontSize: 30, fontWeight: 800, color: changeColor, lineHeight: 1 }}>
                                {quote ? formatSignedNumber(quote.change_percent, 2, '%') : '--'}
                            </div>
                            <div style={{ fontSize: 13, color: changeColor, marginTop: 8 }}>
                                {quote ? formatSignedNumber(quote.change) : '等待实时数据'}
                            </div>
                        </div>
                    </div>

                    {quote ? (
                        <Row gutter={[14, 14]}>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('最新价', formatNumber(quote.price), '来自实时行情流', '#91caff')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('开盘 / 昨收', `${formatNumber(quote.open)} / ${formatNumber(quote.previous_close)}`, '开盘价与上一交易日收盘', '#b7eb8f')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('日内区间', `${formatNumber(quote.low)} - ${formatNumber(quote.high)}`, '最低价到最高价', '#ffd591')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('成交量', formatVolume(quote.volume), '实时累计成交量', '#d3adf7')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('买一 / 卖一', `${formatNumber(quote.bid)} / ${formatNumber(quote.ask)}`, '盘口最优报价', '#ffe58f')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('买卖点差', spreadValue, '买一和卖一的差值', '#87e8de')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('日内振幅', rangePercent, '基于昨收估算的区间波动', '#ffccc7')}
                            </Col>
                            <Col xs={24} sm={12} lg={6}>
                                {renderMetricCard('详情主体', '全维分析', '下方按 Tab 查看趋势、量价、情绪等', '#adc6ff')}
                            </Col>
                        </Row>
                    ) : (
                        <Empty
                            image={Empty.PRESENTED_IMAGE_SIMPLE}
                            description={
                                <div data-testid="realtime-quote-waiting">
                                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>等待实时快照</div>
                                    <div style={{ marginTop: 6, color: 'var(--text-secondary)' }}>
                                        当前还没收到 {displaySymbol} 的实时 quote，历史分析仍会继续加载。
                                    </div>
                                </div>
                            }
                        />
                    )}
                </section>

                <section
                    style={{
                        borderRadius: 18,
                        border: '1px solid var(--border-color)',
                        background: 'var(--bg-secondary)',
                        padding: 18,
                        boxShadow: '0 8px 26px rgba(15, 23, 42, 0.06)',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 700 }}>
                                <DotChartOutlined />
                                全维分析
                            </div>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                                总览、趋势、量价、情绪、形态、基本面、行业、风险、相关性与 AI 预测
                            </Text>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: 12 }}>
                            <RiseOutlined />
                            <span>分析数据来自历史行情与现有分析接口</span>
                            <ClockCircleOutlined />
                        </div>
                    </div>

                    {symbol ? (
                        <MarketAnalysis key={symbol} symbol={symbol} embedMode />
                    ) : (
                        <Empty description="暂无可分析的标的" />
                    )}
                </section>
            </div>
        </Modal>
    );
};

export default RealtimeStockDetailModal;
