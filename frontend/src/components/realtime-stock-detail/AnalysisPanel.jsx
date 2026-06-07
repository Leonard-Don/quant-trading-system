/**
 * Full-dimension analysis panel for RealtimeStockDetailModal (layer 2 split).
 *
 * Pure render — no hooks, no data fetching. Owns the verbatim "全维分析" section
 * that previously lived inline at the bottom of the parent modal body. Embeds
 * MarketAnalysis with the same `key={symbol}` so symbol switches keep
 * remounting the embedded analysis exactly as before. The parent stays the
 * orchestrator; this child only renders.
 */

import { Empty, Typography } from 'antd';
import { DotChartOutlined, RiseOutlined, ClockCircleOutlined } from '@ant-design/icons';
import MarketAnalysis from '../MarketAnalysis';

const { Text } = Typography;

const AnalysisPanel = ({ symbol }) => (
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
);

export default AnalysisPanel;
