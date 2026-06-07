/**
 * Industry cluster analysis panel (layer-2 split of IndustryDashboard).
 *
 * Pure presentational — owns no state and does no data fetching. The parent
 * (`IndustryDashboard`) stays the orchestrator that holds the cluster slice of
 * `useIndustryDashboardData`; this child renders the cluster summary cards and
 * the momentum/flow scatter chart, forwarding interactions back through the
 * callbacks it receives.
 *
 * The JSX, styles, data-testids, recharts config and number formatting are a
 * verbatim move of the former `renderClusters` / `renderClusterScatterChart`
 * helpers, so behavior is unchanged.
 */

import {
    Row,
    Col,
    Card,
    Spin,
    Empty,
    Tag,
    Button,
    Space,
    Statistic,
} from 'antd';
import {
    FireOutlined,
    BranchesOutlined,
    ReloadOutlined,
} from '@ant-design/icons';
import {
    ScatterChart,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    ReferenceLine,
    Tooltip as RechartsTooltip,
    ResponsiveContainer,
} from 'recharts';

const PANEL_SURFACE = 'var(--bg-secondary)';
const PANEL_BORDER = '1px solid var(--border-color)';
const PANEL_MUTED = 'var(--text-muted)';
const TEXT_PRIMARY = 'var(--text-primary)';
const CLUSTER_COLORS = ['#ff4d4f', '#1890ff', '#52c41a', '#faad14', '#eb2f96'];

const IndustryClusterPanel = ({
    loadingClusters,
    clusterError,
    clusters,
    selectedClusterPoint,
    onLoadClusters,
    onSetSelectedClusterPoint,
    onIndustryClick,
    onSetSelectedIndustry,
    onAddToComparison,
}) => {
    // 渲染聚类分析
    const renderClusters = () => {
        if (loadingClusters) {
            return <Spin />;
        }

        if (clusterError && !clusters) {
            return (
                <Empty description={clusterError}>
                    <Button
                        className="industry-empty-action"
                        type="primary"
                        onClick={() => onLoadClusters(false)}
                        icon={<ReloadOutlined />}
                    >
                        重试
                    </Button>
                </Empty>
            );
        }

        if (!clusters) {
            return (
                <Button className="industry-empty-action" onClick={() => onLoadClusters(false)} icon={<BranchesOutlined />}>
                    开始聚类分析
                </Button>
            );
        }

        return (
            <div>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                    {Object.entries(clusters.cluster_stats || {}).map(([idx, stats]) => {
                        const isHot = parseInt(idx) === clusters.hot_cluster;
                        return (
                            <Col span={12} key={idx}>
                                <Card
                                    size="small"
                                    title={
                                        <span>
                                            {isHot && (
                                                <FireOutlined style={{ color: '#ff4d4f', marginRight: 4 }} />
                                            )}
                                            {isHot ? '🔥 热门簇' : `簇 ${parseInt(idx) + 1}`}
                                        </span>
                                    }
                                    style={{
                                        borderColor: isHot ? '#ff4d4f' : undefined,
                                        boxShadow: isHot ? '0 0 8px rgba(255,77,79,0.3)' : undefined
                                    }}
                                >
                                    <Row gutter={8}>
                                        <Col span={12}>
                                            <Statistic
                                                title="平均动量"
                                                value={Math.abs(stats.avg_momentum) < 0.005 ? '0.00' : stats.avg_momentum?.toFixed(2)}
                                                suffix="%"
                                                valueStyle={{
                                                    color: stats.avg_momentum >= 0 ? '#cf1322' : '#3f8600',
                                                    fontSize: 14
                                                }}
                                            />
                                        </Col>
                                        <Col span={12}>
                                            <Statistic
                                                title="平均资金强度"
                                                value={Math.abs(stats.avg_flow) < 0.005 ? '0.00' : stats.avg_flow?.toFixed(2)}
                                                valueStyle={{
                                                    color: (stats.avg_flow || 0) >= 0 ? '#cf1322' : '#3f8600',
                                                    fontSize: 14
                                                }}
                                            />
                                        </Col>
                                    </Row>
                                    <div style={{ marginTop: 8 }}>
                                        <div style={{ color: PANEL_MUTED, fontSize: 12, marginBottom: 4 }}>
                                            行业数: {stats.count}
                                        </div>
                                        <div>
                                            {(stats.industries || []).slice(0, 4).map(ind => (
                                                <Tag
                                                    key={ind}
                                                    size="small"
                                                    style={{ cursor: 'pointer', marginBottom: 4 }}
                                                    onClick={() => onIndustryClick(ind)}
                                                >
                                                    {ind}
                                                </Tag>
                                            ))}
                                            {(stats.industries?.length || 0) > 4 && (
                                                <Tag size="small" style={{ color: PANEL_MUTED }}>
                                                    +{stats.industries.length - 4}
                                                </Tag>
                                            )}
                                        </div>
                                    </div>
                                </Card>
                            </Col>
                        );
                    })}
                </Row>
            </div>
        );
    };

    // 聚类散点图
    const renderClusterScatterChart = () => {
        if (loadingClusters && !clusters) {
            return (
                <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>
                        聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span>
                    </div>
                    <div
                        style={{
                            minHeight: 280,
                            borderRadius: 12,
                            border: PANEL_BORDER,
                            background: PANEL_SURFACE,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            gap: 10,
                        }}
                    >
                        <Spin />
                        <div style={{ fontSize: 12, color: PANEL_MUTED }}>聚类分析计算中，首次加载可能需要几秒</div>
                    </div>
                </div>
            );
        }

        if (!clusters) return null;

        const scatterData = (clusters.points || []).map(point => ({
            name: point.industry_name,
            cluster: point.cluster,
            x: point.weighted_change || 0,
            y: point.flow_strength || 0,
        }));
        const clusterKeys = Object.keys(clusters.cluster_stats || {}).length > 0
            ? Object.keys(clusters.cluster_stats || {}).map(k => parseInt(k))
            : [...new Set(scatterData.map(d => d.cluster))];

        if (scatterData.length === 0) {
            return (
                <div style={{ marginTop: 16 }}>
                    <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>
                        聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span>
                    </div>
                    <Empty description="当前暂无可展示的聚类点位" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                </div>
            );
        }

        return (
            <div style={{ marginTop: 16 }}>
                <div style={{ marginBottom: 8, fontWeight: 'bold', color: TEXT_PRIMARY }}>聚类分布图 <span style={{ fontWeight: 'normal', color: PANEL_MUTED, fontSize: 12 }}>（X=动量, Y=资金强度）</span></div>
                <div style={{ position: 'relative', borderRadius: 12, overflow: 'hidden' }}>
                    <div style={{ position: 'absolute', top: 8, left: 12, zIndex: 1 }}>
                        <Tag color="red" style={{ margin: 0, borderRadius: 999 }}>强势流入</Tag>
                    </div>
                    <div style={{ position: 'absolute', top: 8, right: 12, zIndex: 1 }}>
                        <Tag color="orange" style={{ margin: 0, borderRadius: 999 }}>弱势流入</Tag>
                    </div>
                    <div style={{ position: 'absolute', bottom: 8, left: 12, zIndex: 1 }}>
                        <Tag color="green" style={{ margin: 0, borderRadius: 999 }}>强势撤退</Tag>
                    </div>
                    <div style={{ position: 'absolute', bottom: 8, right: 12, zIndex: 1 }}>
                        <Tag color="blue" style={{ margin: 0, borderRadius: 999 }}>弱势修复</Tag>
                    </div>
                    <ResponsiveContainer width="100%" height={280}>
                        <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis
                                type="number"
                                dataKey="x"
                                name="动量"
                                tick={{ fontSize: 11 }}
                                tickFormatter={v => `${v.toFixed(1)}%`}
                            />
                            <YAxis
                                type="number"
                                dataKey="y"
                                name="资金强度"
                                tick={{ fontSize: 11 }}
                                domain={[-1.05, 1.05]}
                                tickFormatter={v => `${v.toFixed(1)}`}
                            />
                            <ReferenceLine x={0} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />
                            <ReferenceLine y={0} stroke="rgba(0,0,0,0.18)" strokeDasharray="4 4" />
                            <RechartsTooltip
                                formatter={(value, name) => [
                                    typeof value === 'number' ? value.toFixed(2) : value,
                                    name === 'x' ? '动量' : name === 'y' ? '资金强度' : name
                                ]}
                                labelFormatter={() => ''}
                                content={({ active, payload }) => {
                                    if (active && payload && payload.length) {
                                        const d = payload[0]?.payload;
                                        return (
                                            <div style={{
                                                background: 'var(--bg-secondary)',
                                                color: 'var(--text-primary)',
                                                border: '1px solid var(--border-color)',
                                                padding: '6px 10px',
                                                borderRadius: 4,
                                                fontSize: 12
                                            }}>
                                                <div style={{ fontWeight: 'bold' }}>{d?.name}</div>
                                                <div>动量: {d?.x?.toFixed(2)}%</div>
                                                <div>资金强度: {d?.y?.toFixed(2)}</div>
                                            </div>
                                        );
                                    }
                                    return null;
                                }}
                            />
                            {clusterKeys.map(clusterIdx => {
                                const isHot = clusterIdx === clusters.hot_cluster;
                                const clusterData = scatterData.filter(d => d.cluster === clusterIdx);
                                return (
                                    <Scatter
                                        key={clusterIdx}
                                        name={isHot ? '🔥 热门簇' : `簇 ${clusterIdx + 1}`}
                                        data={clusterData}
                                        fill={CLUSTER_COLORS[clusterIdx % CLUSTER_COLORS.length]}
                                        shape={(props) => {
                                            const selected = selectedClusterPoint?.name === props?.payload?.name;
                                            return (
                                                <circle
                                                    cx={props.cx}
                                                    cy={props.cy}
                                                    r={selected ? 7 : 5}
                                                    fill={props.fill}
                                                    stroke={selected ? '#111827' : '#ffffff'}
                                                    strokeWidth={selected ? 2.5 : 1.5}
                                                    style={{ cursor: 'pointer' }}
                                                />
                                            );
                                        }}
                                        onClick={(payload) => {
                                            const nextPoint = payload?.payload || payload;
                                            if (nextPoint?.name) {
                                                onSetSelectedClusterPoint(nextPoint);
                                            }
                                        }}
                                    />
                                );
                            })}
                        </ScatterChart>
                    </ResponsiveContainer>
                </div>
                {selectedClusterPoint && (
                    <Card
                        size="small"
                        style={{ marginTop: 12, borderRadius: 12, border: '1px solid rgba(24,144,255,0.18)' }}
                        styles={{ body: { padding: '12px 14px' } }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                    <span style={{ fontSize: 15, fontWeight: 700, color: TEXT_PRIMARY }}>{selectedClusterPoint.name}</span>
                                    <Tag color={selectedClusterPoint.cluster === clusters.hot_cluster ? 'red' : 'blue'} style={{ margin: 0, borderRadius: 999 }}>
                                        {selectedClusterPoint.cluster === clusters.hot_cluster ? '热门簇' : `簇 ${selectedClusterPoint.cluster + 1}`}
                                    </Tag>
                                </div>
                                <div style={{ fontSize: 12, color: PANEL_MUTED }}>
                                    动量 {selectedClusterPoint.x?.toFixed(2)}% · 资金强度 {selectedClusterPoint.y?.toFixed(2)}
                                </div>
                            </div>
                            <Space size={8} wrap>
                                <Button size="small" type="primary" onClick={() => onSetSelectedIndustry(selectedClusterPoint.name)}>
                                    聚焦
                                </Button>
                                <Button size="small" onClick={() => onIndustryClick(selectedClusterPoint.name)}>
                                    查看详情
                                </Button>
                                <Button size="small" onClick={() => onAddToComparison(selectedClusterPoint.name)}>
                                    加入对比
                                </Button>
                            </Space>
                        </div>
                    </Card>
                )}
            </div>
        );
    };

    return (
        <>
            {renderClusters()}
            {renderClusterScatterChart()}
        </>
    );
};

export default IndustryClusterPanel;
