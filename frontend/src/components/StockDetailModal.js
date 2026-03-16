import React from 'react';
import { Modal, Spin, Empty, Tag, Row, Col, Progress, Button, Tooltip } from 'antd';
import { ReloadOutlined, StarFilled } from '@ant-design/icons';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';

const DETAIL_MODAL_BODY_BG = 'linear-gradient(180deg, color-mix(in srgb, var(--bg-primary) 88%, #ffffff 12%) 0%, var(--bg-primary) 140px)';
const DETAIL_HERO_BG = 'linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 18%, var(--bg-secondary) 82%) 0%, color-mix(in srgb, var(--accent-secondary) 16%, var(--bg-secondary) 84%) 100%)';
const DETAIL_HERO_BORDER = '1px solid color-mix(in srgb, var(--border-color) 68%, var(--accent-primary) 32%)';
const DETAIL_HERO_SHADOW = '0 10px 30px rgba(15, 23, 42, 0.14)';
const DETAIL_HERO_TEXT = 'var(--text-primary)';
const DETAIL_HERO_MUTED = 'var(--text-secondary)';
const DETAIL_HERO_SUBTLE = 'var(--text-muted)';

const renderDimensionScores = (scores) => {
    if (!scores) return null;

    const isSurge = scores.score_type === 'hot' || scores.score_type === 'surge';
    const dimensions = [
        { key: 'market_cap', label: '规模优势', color: '#1890ff' },
        { key: 'valuation', label: '估值水平', color: '#722ed1' },
        { key: 'profitability', label: '盈利能力', color: '#52c41a' },
        { key: 'growth', label: '成长潜力', color: '#faad14' },
        { key: 'momentum', label: isSurge ? '涨幅动量' : '价格动量', color: '#f5222d' },
        ...(isSurge && scores.money_flow != null
            ? [{ key: 'money_flow', label: '资金流向', color: '#13c2c2' }]
            : []),
        { key: 'activity', label: '交易活跃度', color: '#eb2f96' },
    ];

    return (
        <Row gutter={[16, 16]}>
            {dimensions.map((dim) => {
                const rawScore = scores[dim.key] || 0;
                const percentScore = rawScore <= 1 ? Math.round(rawScore * 100) : Math.round(rawScore);

                return (
                    <Col span={8} key={dim.key}>
                        <Tooltip title={`${dim.label}得分: ${percentScore}分`}>
                            <div style={{ textAlign: 'center' }}>
                                <Progress
                                    type="circle"
                                    percent={percentScore}
                                    size={60}
                                    strokeColor={dim.color}
                                    format={(percent) => <span style={{ fontSize: 12 }}>{percent}</span>}
                                />
                                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>
                                    {dim.label}
                                </div>
                            </div>
                        </Tooltip>
                    </Col>
                );
            })}
        </Row>
    );
};

const renderPriceChart = (priceData) => {
    if (!priceData || priceData.length === 0) {
        return <Empty description="暂无价格数据" />;
    }

    const chartData = priceData.map((item) => ({
        date: item.date || item.index,
        close: item.close,
        volume: item.volume,
    }));

    return (
        <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
                    tickFormatter={(val) => (val ? val.substring(5, 10) : '')}
                />
                <YAxis
                    domain={['auto', 'auto']}
                    tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
                />
                <RechartsTooltip
                    formatter={(value) => [value.toFixed(2), '收盘价']}
                    labelFormatter={(label) => `日期: ${label}`}
                />
                <Line
                    type="monotone"
                    dataKey="close"
                    stroke="#1890ff"
                    dot={false}
                    strokeWidth={2}
                />
            </LineChart>
        </ResponsiveContainer>
    );
};

const renderDetailMetric = (label, value, options = {}) => (
    <div
        style={{
            background: options.background || 'var(--bg-secondary)',
            border: `1px solid ${options.borderColor || 'var(--border-color)'}`,
            borderRadius: 12,
            padding: '12px 14px',
            minHeight: 84,
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
        }}
    >
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700, letterSpacing: '0.03em', marginBottom: 8 }}>
            {label}
        </div>
        <div
            style={{
                fontSize: options.fontSize || 20,
                fontWeight: 700,
                color: options.color || 'var(--text-primary)',
                lineHeight: 1.2,
            }}
        >
            {value}
        </div>
        {options.subtle && (
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
                {options.subtle}
            </div>
        )}
    </div>
);

const renderDetailSection = (title, subtitle, accentColor, children) => (
    <div
        style={{
            marginTop: 16,
            padding: '14px 16px',
            borderRadius: 14,
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-color)',
            boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
        }}
    >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 12 }}>
            <span
                style={{
                    width: 6,
                    minWidth: 6,
                    height: 28,
                    borderRadius: 999,
                    background: accentColor,
                    marginTop: 2,
                    boxShadow: `0 0 0 4px ${accentColor}22`,
                }}
            />
            <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)', lineHeight: 1.2 }}>{title}</div>
                {subtitle && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{subtitle}</div>}
            </div>
        </div>
        {children}
    </div>
);

const StockDetailModal = ({
    open,
    onCancel,
    loading = false,
    error = null,
    detailData = null,
    selectedStock = null,
    onRetry,
}) => (
    <Modal
        title={
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ display: 'flex', alignItems: 'center', fontWeight: 700 }}>
                    <StarFilled style={{ color: '#faad14', marginRight: 8 }} />
                    {detailData?.name || selectedStock || '股票'} 详细分析
                </span>
                {detailData?.score_type && (
                    <Tag
                        color={detailData.score_type === 'hot' ? 'volcano' : 'blue'}
                        style={{ margin: 0, fontSize: 11, borderRadius: 999, paddingInline: 8 }}
                    >
                        {detailData.score_type === 'hot' ? '动量评分' : '综合评分'}
                    </Tag>
                )}
            </div>
        }
        open={open}
        onCancel={onCancel}
        footer={null}
        width={800}
        destroyOnHidden
        modalRender={(node) => <div data-testid="stock-detail-modal">{node}</div>}
        styles={{
            body: {
                background: DETAIL_MODAL_BODY_BG,
                padding: 18,
            },
        }}
    >
        {loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin size="large" />
            </div>
        ) : error ? (
            <Empty
                description={error}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
            >
                {onRetry && (
                    <Button className="industry-empty-action" icon={<ReloadOutlined />} onClick={onRetry}>
                        重试
                    </Button>
                )}
            </Empty>
        ) : detailData ? (
            <div data-testid="stock-detail-modal-body">
                <div
                    style={{
                        padding: '16px 18px',
                        borderRadius: 16,
                        background: DETAIL_HERO_BG,
                        border: DETAIL_HERO_BORDER,
                        boxShadow: DETAIL_HERO_SHADOW,
                        marginBottom: 16,
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                        <div>
                            <div style={{ fontSize: 12, color: DETAIL_HERO_MUTED, marginBottom: 6 }}>股票代码</div>
                            <div style={{ fontSize: 24, fontWeight: 700, color: DETAIL_HERO_TEXT, lineHeight: 1.1 }}>{detailData.symbol}</div>
                            <div style={{ fontSize: 12, color: DETAIL_HERO_TEXT, marginTop: 8 }}>{detailData.name}</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 12, color: DETAIL_HERO_MUTED, marginBottom: 6 }}>
                                {detailData.score_type === 'hot' ? '动量得分' : '综合得分'}
                            </div>
                            <div
                                style={{
                                    fontSize: 30,
                                    fontWeight: 800,
                                    color: detailData.total_score >= 70 ? '#95de64' : detailData.total_score >= 50 ? '#ffd666' : '#ff9c9c',
                                    lineHeight: 1,
                                }}
                            >
                                {detailData.total_score?.toFixed(2)}
                            </div>
                            <div style={{ fontSize: 11, color: DETAIL_HERO_SUBTLE, marginTop: 6 }}>
                                {detailData.score_type === 'hot' ? '短线动量与资金关注度' : '基本面、估值与流动性'}
                            </div>
                        </div>
                    </div>
                </div>

                {detailData.raw_data && Object.keys(detailData.raw_data).length > 0 && (
                    renderDetailSection('财务基本面', '真实基础面数据，不随榜单类型漂移', '#1890ff', (
                        <>
                            <Row gutter={[12, 12]}>
                                <Col span={6}>
                                    {renderDetailMetric(
                                        '总市值',
                                        detailData.raw_data.market_cap
                                            ? detailData.raw_data.market_cap >= 1e12
                                                ? `${(detailData.raw_data.market_cap / 1e12).toFixed(2)}万亿`
                                                : `${(detailData.raw_data.market_cap / 1e8).toFixed(0)}亿`
                                            : '-'
                                    )}
                                </Col>
                                <Col span={6}>
                                    {renderDetailMetric(
                                        'PE (TTM)',
                                        detailData.raw_data.pe_ttm ? detailData.raw_data.pe_ttm.toFixed(2) : '-',
                                        {
                                            color: detailData.raw_data.pe_ttm > 0 && detailData.raw_data.pe_ttm < 30
                                                ? '#389e0d'
                                                : detailData.raw_data.pe_ttm > 80 ? '#cf1322' : 'var(--text-primary)',
                                        }
                                    )}
                                </Col>
                                <Col span={6}>
                                    {renderDetailMetric('PB (市净率)', detailData.raw_data.pb ? detailData.raw_data.pb.toFixed(2) : '-')}
                                </Col>
                                <Col span={6}>
                                    {renderDetailMetric(
                                        '涨跌幅',
                                        detailData.raw_data.change_pct != null ? `${detailData.raw_data.change_pct >= 0 ? '+' : ''}${detailData.raw_data.change_pct.toFixed(2)}%` : '-',
                                        {
                                            color: (detailData.raw_data.change_pct || 0) >= 0 ? '#cf1322' : '#3f8600',
                                        }
                                    )}
                                </Col>
                            </Row>
                            <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
                                {detailData.raw_data.roe != null && detailData.raw_data.roe !== 0 && (
                                    <Col span={6}>
                                        {renderDetailMetric(
                                            'ROE (净资产收益率)',
                                            `${detailData.raw_data.roe.toFixed(2)}%`,
                                            {
                                                fontSize: 18,
                                                color: detailData.raw_data.roe > 15 ? '#389e0d' : detailData.raw_data.roe < 0 ? '#cf1322' : 'var(--text-primary)',
                                            }
                                        )}
                                    </Col>
                                )}
                                {detailData.raw_data.revenue_yoy != null && detailData.raw_data.revenue_yoy !== 0 && (
                                    <Col span={6}>
                                        {renderDetailMetric(
                                            '营收同比增速',
                                            `${detailData.raw_data.revenue_yoy >= 0 ? '+' : ''}${detailData.raw_data.revenue_yoy.toFixed(2)}%`,
                                            {
                                                fontSize: 18,
                                                color: detailData.raw_data.revenue_yoy > 0 ? '#cf1322' : '#3f8600',
                                            }
                                        )}
                                    </Col>
                                )}
                                {detailData.raw_data.profit_yoy != null && detailData.raw_data.profit_yoy !== 0 && (
                                    <Col span={6}>
                                        {renderDetailMetric(
                                            '净利润同比增速',
                                            `${detailData.raw_data.profit_yoy >= 0 ? '+' : ''}${detailData.raw_data.profit_yoy.toFixed(2)}%`,
                                            {
                                                fontSize: 18,
                                                color: detailData.raw_data.profit_yoy > 0 ? '#cf1322' : '#3f8600',
                                            }
                                        )}
                                    </Col>
                                )}
                                {detailData.raw_data.turnover != null && detailData.raw_data.turnover !== 0 && (
                                    <Col span={6}>
                                        {renderDetailMetric(
                                            '换手率',
                                            `${detailData.raw_data.turnover.toFixed(2)}%`,
                                            {
                                                fontSize: 18,
                                                color: detailData.raw_data.turnover > 5 ? '#d48806' : 'var(--text-primary)',
                                            }
                                        )}
                                    </Col>
                                )}
                            </Row>
                        </>
                    ))
                )}

                {renderDetailSection(
                    '评分维度',
                    detailData.score_type === 'hot' ? '更强调涨势与资金响应' : '更强调估值、盈利与成长',
                    detailData.score_type === 'hot' ? '#eb2f96' : '#722ed1',
                    renderDimensionScores(detailData.dimension_scores)
                )}

                {detailData.technical_analysis && Object.keys(detailData.technical_analysis).length > 0 && (
                    renderDetailSection('技术指标', '近 60 日走势与波动特征', '#13c2c2', (
                        <Row gutter={[12, 12]}>
                            <Col span={6}>
                                {renderDetailMetric('最新价', detailData.technical_analysis.latest_close ? detailData.technical_analysis.latest_close.toFixed(2) : '-')}
                            </Col>
                            <Col span={6}>
                                {renderDetailMetric(
                                    'MA5 (短期趋势)',
                                    detailData.technical_analysis.ma5 ? detailData.technical_analysis.ma5.toFixed(2) : '-',
                                    {
                                        color: detailData.technical_analysis.latest_close >= detailData.technical_analysis.ma5 ? '#cf1322' : '#3f8600',
                                        subtle: detailData.technical_analysis.latest_close >= detailData.technical_analysis.ma5 ? '价格在 MA5 上方' : '价格在 MA5 下方',
                                    }
                                )}
                            </Col>
                            <Col span={6}>
                                {renderDetailMetric(
                                    'MA20 (中期趋势)',
                                    detailData.technical_analysis.ma20 ? detailData.technical_analysis.ma20.toFixed(2) : '-',
                                    {
                                        color: detailData.technical_analysis.latest_close >= detailData.technical_analysis.ma20 ? '#cf1322' : '#3f8600',
                                        subtle: detailData.technical_analysis.latest_close >= detailData.technical_analysis.ma20 ? '价格在 MA20 上方' : '价格在 MA20 下方',
                                    }
                                )}
                            </Col>
                            <Col span={6}>
                                {renderDetailMetric(
                                    '60日波动率',
                                    detailData.technical_analysis.volatility_60d ? `${detailData.technical_analysis.volatility_60d.toFixed(2)}%` : '-',
                                    { color: '#d48806' }
                                )}
                            </Col>
                        </Row>
                    ))
                )}

                {renderDetailSection('近期走势', '最近 30 个交易日收盘价', '#1890ff', renderPriceChart(detailData.price_data))}
            </div>
        ) : (
            <Empty description="无法加载详情" />
        )}
    </Modal>
);

export default StockDetailModal;
