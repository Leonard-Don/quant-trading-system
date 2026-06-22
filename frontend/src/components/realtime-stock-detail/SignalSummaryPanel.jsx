/**
 * Signal-summary panel for RealtimeStockDetailModal (layer 2 split).
 *
 * Pure render — no hooks, no data fetching. Owns the verbatim "信号总表" section
 * (score tags, four-up metric grid) that previously lived inline in the parent
 * modal body. Receives the parent's already-computed signal summary, quote, and
 * range value. The parent stays the orchestrator; this child only renders.
 */

import { Row, Col, Tag, Typography } from 'antd';
import { RiseOutlined } from '@ant-design/icons';
import {
    formatSignedNumber,
    renderMetricCard,
} from './helpers.jsx';

const { Text } = Typography;

const SignalSummaryPanel = ({
    signalSummary,
    quote,
    rangePercent,
}) => (
    <section
        style={{
            borderRadius: 18,
            border: '1px solid var(--border-color)',
            background: 'var(--bg-secondary)',
            padding: 16,
            boxShadow: '0 8px 26px rgba(15, 23, 42, 0.06)',
        }}
        data-testid="detail-signal-summary"
    >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
            <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-primary)', fontWeight: 700 }}>
                    <RiseOutlined />
                    信号总表
                </div>
                <Text type="secondary" style={{ fontSize: 11 }}>
                    先用一屏判断强弱，再决定往下展开哪块分析。
                </Text>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <Tag color="blue" style={{ margin: 0, borderRadius: 999, paddingInline: 9, fontWeight: 700 }}>
                    综合分 {signalSummary.totalScore}
                </Tag>
                <Tag style={{ margin: 0, borderRadius: 999, paddingInline: 9, fontWeight: 700 }}>
                    {signalSummary.conviction}
                </Tag>
            </div>
        </div>

        <Row gutter={[14, 14]}>
            <Col xs={24} sm={12} lg={6}>
                {renderMetricCard('综合判断', `${signalSummary.totalScore}`, signalSummary.conviction, '#91caff')}
            </Col>
            <Col xs={24} sm={12} lg={6}>
                {renderMetricCard('动能信号', signalSummary.momentumLabel, quote ? formatSignedNumber(quote.change_percent, 2, '%') : '等待实时数据', '#b7eb8f')}
            </Col>
            <Col xs={24} sm={12} lg={6}>
                {renderMetricCard('波动信号', signalSummary.volatilityLabel, `日内振幅 ${rangePercent}`, '#ffd591')}
            </Col>
            <Col xs={24} sm={12} lg={6}>
                {renderMetricCard('事件方向', signalSummary.eventLabel, signalSummary.eventBreakdown, '#d3adf7')}
            </Col>
        </Row>
    </section>
);

export default SignalSummaryPanel;
