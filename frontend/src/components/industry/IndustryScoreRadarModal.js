import React, { useMemo } from 'react';
import { Modal, Row, Col, Statistic, Tag, Empty } from 'antd';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';
import { clampNumeric, formatIndustryAlertMoneyFlow, getIndustryScoreTone } from './industryShared';

const buildRadarData = (record, snapshot) => {
    if (Array.isArray(record?.score_breakdown) && record.score_breakdown.length > 0) {
        return record.score_breakdown.map((item) => ({
            dimension: item.dimension,
            value: Number(item.value || 0),
            fullMark: 100,
            weight: Number(item.weight || 0),
            metric: item.metric,
            metricLabel: item.metric_label,
            source: 'backend',
        }));
    }

    if (!record && !snapshot) {
        return [];
    }

    const score = Number(record?.score ?? record?.total_score ?? snapshot?.score ?? 0);
    const changePct = Number(record?.change_pct ?? snapshot?.change_pct ?? 0);
    const moneyFlow = Number(record?.money_flow ?? snapshot?.money_flow ?? 0);
    const volatility = Number(record?.industryVolatility ?? snapshot?.industryVolatility ?? 0);
    const turnoverRate = Number(snapshot?.turnoverRate ?? 0);
    const netInflowRatio = Number(snapshot?.netInflowRatio ?? 0);
    const pe = Number(snapshot?.pe_ttm ?? 0);
    const pb = Number(snapshot?.pb ?? 0);
    const stockCount = Number(record?.stock_count ?? snapshot?.stock_count ?? 0);
    const marketCap = Number(record?.total_market_cap ?? snapshot?.total_market_cap ?? 0);

    const priceScore = clampNumeric(((changePct + 5) / 10) * 100);
    const capitalScore = clampNumeric(50 + clampNumeric(netInflowRatio * 10, -24, 24) + clampNumeric(moneyFlow / 1e8, -25, 25));
    const activityScore = clampNumeric((turnoverRate > 0 ? (turnoverRate / 5) * 75 : 32) + clampNumeric(stockCount / 2, 0, 25));
    const valuationBase = pe > 0
        ? clampNumeric(85 - Math.max(pe - 18, 0) * 1.2, 18, 88)
        : 42;
    const valuationScore = pb > 0 ? clampNumeric((valuationBase * 0.75) + clampNumeric(88 - pb * 10, 18, 88) * 0.25) : valuationBase;
    const stabilityScore = volatility > 0 ? clampNumeric(92 - Math.abs(volatility - 2.4) * 14, 18, 92) : 46;
    const scaleScore = marketCap > 0 ? clampNumeric(30 + Math.log10(Math.max(marketCap / 1e8, 1)) * 16, 30, 92) : 38;

    return [
        { dimension: '价格动量', value: Math.round(priceScore), fullMark: 100 },
        { dimension: '资金承接', value: Math.round(capitalScore), fullMark: 100 },
        { dimension: '交易活跃', value: Math.round(activityScore), fullMark: 100 },
        { dimension: '估值支撑', value: Math.round(valuationScore), fullMark: 100 },
        { dimension: '波动稳定', value: Math.round(stabilityScore), fullMark: 100 },
        { dimension: '板块体量', value: Math.round(scaleScore), fullMark: 100 },
        { dimension: '综合得分', value: Math.round(clampNumeric(score, 0, 100)), fullMark: 100 },
    ];
};

const IndustryScoreRadarModal = ({
    visible,
    onClose,
    record,
    snapshot,
}) => {
    const radarData = useMemo(() => buildRadarData(record, snapshot), [record, snapshot]);
    const industryName = record?.industry_name || snapshot?.industry_name || '';
    const score = Number(record?.score ?? record?.total_score ?? snapshot?.score ?? 0);
    const changePct = Number(record?.change_pct ?? snapshot?.change_pct ?? 0);
    const moneyFlow = Number(record?.money_flow ?? snapshot?.money_flow ?? 0);

    return (
        <Modal
            open={visible}
            title={industryName ? `${industryName} 评分拆解` : '行业评分拆解'}
            onCancel={onClose}
            footer={null}
            width={760}
            destroyOnHidden
            modalRender={(node) => <div data-testid="industry-score-radar-modal">{node}</div>}
        >
            {!radarData.length ? (
                <Empty description="当前行业缺少足够的评分因子，暂时无法生成雷达图" />
            ) : (
                <>
                    <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
                        <Col xs={8}>
                            <Statistic
                                title="综合评分"
                                value={score || 0}
                                precision={1}
                                valueStyle={{ color: getIndustryScoreTone(score), fontSize: 24 }}
                            />
                        </Col>
                        <Col xs={8}>
                            <Statistic
                                title="涨跌幅"
                                value={changePct}
                                precision={2}
                                suffix="%"
                                valueStyle={{ color: changePct >= 0 ? '#cf1322' : '#3f8600', fontSize: 22 }}
                            />
                        </Col>
                        <Col xs={8}>
                            <Statistic
                                title="主力资金"
                                value={formatIndustryAlertMoneyFlow(moneyFlow)}
                                valueStyle={{ color: moneyFlow >= 0 ? '#cf1322' : '#3f8600', fontSize: 20 }}
                            />
                        </Col>
                    </Row>

                    <div style={{ height: 360 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <RadarChart data={radarData}>
                                <PolarGrid stroke="rgba(0,0,0,0.08)" />
                                <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12 }} />
                                <PolarRadiusAxis angle={90} domain={[0, 100]} tickCount={6} tick={{ fontSize: 11 }} />
                                <Radar
                                    name="行业评分"
                                    dataKey="value"
                                    stroke="#1677ff"
                                    fill="rgba(22, 119, 255, 0.22)"
                                    fillOpacity={1}
                                />
                            </RadarChart>
                        </ResponsiveContainer>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                        {radarData
                            .filter((item) => item.dimension !== '综合得分')
                            .sort((left, right) => right.value - left.value)
                            .slice(0, 3)
                            .map((item) => (
                                <Tag key={item.dimension} color="processing" style={{ margin: 0, borderRadius: 999 }}>
                                    {item.dimension} {item.value}
                                </Tag>
                            ))}
                        {radarData.some((item) => item.source === 'backend') && (
                            <Tag color="blue" style={{ margin: 0, borderRadius: 999 }}>
                                使用后端统一评分口径
                            </Tag>
                        )}
                    </div>
                </>
            )}
        </Modal>
    );
};

export default IndustryScoreRadarModal;
