import React from 'react';
import { Card, Row, Col, Skeleton } from 'antd';

/**
 * 骨架屏加载组件集合
 * 提供各种页面的加载占位效果
 */

// 统计卡片骨架屏
export const StatisticSkeleton = () => (
    <Card size="small" style={{ marginBottom: 16 }}>
        <Skeleton active paragraph={false} title={{ width: '60%' }} />
        <Skeleton.Input active size="large" style={{ marginTop: 8 }} />
    </Card>
);

// 图表区域骨架屏
export const ChartSkeleton = ({ height = 300 }) => (
    <Card size="small" style={{ marginBottom: 16 }}>
        <Skeleton.Input active block style={{ height, width: '100%' }} />
    </Card>
);

// 表格骨架屏
export const TableSkeleton = ({ rows = 5 }) => (
    <Card size="small">
        <Skeleton active paragraph={{ rows }} />
    </Card>
);

// 回测结果页面骨架屏
export const BacktestResultSkeleton = () => (
    <div style={{ padding: '16px 0' }}>
        {/* 指标卡片 */}
        <Row gutter={[16, 16]}>
            {[1, 2, 3, 4].map(i => (
                <Col span={6} key={i}>
                    <StatisticSkeleton />
                </Col>
            ))}
        </Row>
        <Row gutter={[16, 16]} style={{ marginTop: 8 }}>
            {[5, 6, 7, 8].map(i => (
                <Col span={6} key={i}>
                    <StatisticSkeleton />
                </Col>
            ))}
        </Row>
        {/* 图表区域 */}
        <ChartSkeleton height={250} />
    </div>
);

// 市场分析页面骨架屏
export const MarketAnalysisSkeleton = () => (
    <div>
        {/* 搜索区域 */}
        <Card size="small" style={{ marginBottom: 16 }}>
            <Skeleton.Input active style={{ width: 300 }} />
        </Card>
        {/* 分析结果 */}
        <Row gutter={16}>
            <Col span={8}>
                <StatisticSkeleton />
            </Col>
            <Col span={8}>
                <StatisticSkeleton />
            </Col>
            <Col span={8}>
                <StatisticSkeleton />
            </Col>
        </Row>
        <ChartSkeleton height={200} />
    </div>
);

// 实时行情页面骨架屏
export const RealTimeSkeleton = () => (
    <div>
        {/* 股票列表 */}
        <Card size="small" style={{ marginBottom: 16 }}>
            <Skeleton avatar active paragraph={{ rows: 2 }} />
            <Skeleton avatar active paragraph={{ rows: 2 }} />
            <Skeleton avatar active paragraph={{ rows: 2 }} />
        </Card>
        {/* 图表 */}
        <ChartSkeleton height={300} />
    </div>
);



// 通用页面加载骨架屏
export const PageSkeleton = () => (
    <div style={{ padding: 24 }}>
        <Skeleton active title={{ width: '30%' }} paragraph={false} />
        <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
            {[1, 2, 3].map(i => (
                <Col span={8} key={i}>
                    <StatisticSkeleton />
                </Col>
            ))}
        </Row>
        <ChartSkeleton height={300} />
        <TableSkeleton rows={5} />
    </div>
);

// AI 预测骨架屏
export const AIPredictionSkeleton = () => (
    <Card size="small">
        <Row gutter={16}>
            <Col span={8}>
                <Skeleton active paragraph={{ rows: 2 }} />
            </Col>
            <Col span={16}>
                <Skeleton.Input active block style={{ height: 150 }} />
            </Col>
        </Row>
    </Card>
);

const SkeletonLoaders = {
    StatisticSkeleton,
    ChartSkeleton,
    TableSkeleton,
    BacktestResultSkeleton,
    MarketAnalysisSkeleton,
    RealTimeSkeleton,

    PageSkeleton,
    AIPredictionSkeleton
};

export default SkeletonLoaders;
