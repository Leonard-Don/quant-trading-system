import React, { lazy, Suspense } from 'react';
import { Tabs, Spin } from 'antd';
import { BarChartOutlined, HistoryOutlined, ExperimentOutlined, PieChartOutlined, GlobalOutlined } from '@ant-design/icons';
import StrategyForm from './StrategyForm';
import ResultsDisplay from './ResultsDisplay';
import LoadingSpinner from './LoadingSpinner';
import CrossMarketBacktestPanel from './CrossMarketBacktestPanel';

// Lazy load history component to keep initial bundle size small
const BacktestHistory = lazy(() => import('./BacktestHistory'));
const StrategyComparison = lazy(() => import('./StrategyComparison'));
const PortfolioOptimizer = lazy(() => import('./PortfolioOptimizer'));

const LazyLoadFallback = () => (
    <div style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        height: '300px'
    }}>
        <Spin size="large" />
        <div style={{ marginTop: 12, color: '#8c8c8c' }}>加载历史记录...</div>
    </div>
);

const TAB_QUERY_KEY = 'tab';
const VALID_TABS = new Set(['new', 'history', 'comparison', 'portfolio', 'cross-market']);

const BacktestDashboard = ({ strategies, height, onSubmit, loading, results }) => {
    const initialTab = (() => {
        const params = new URLSearchParams(window.location.search);
        const tab = params.get(TAB_QUERY_KEY);
        return VALID_TABS.has(tab) ? tab : 'new';
    })();

    const tabItems = [
        {
            key: 'new',
            label: (
                <span>
                    <BarChartOutlined />
                    策略回测
                </span>
            ),
            children: (
                <>
                    <StrategyForm
                        strategies={strategies}
                        onSubmit={onSubmit}
                        loading={loading}
                    />

                    {loading && (
                        <LoadingSpinner
                            message="正在运行回测，请稍候..."
                            size="large"
                        />
                    )}

                    {results && <ResultsDisplay results={results} />}
                </>
            )
        },
        {
            key: 'history',
            label: (
                <span>
                    <HistoryOutlined />
                    回测历史
                </span>
            ),
            children: (
                <Suspense fallback={<LazyLoadFallback />}>
                    <BacktestHistory />
                </Suspense>
            )
        },
        {
            key: 'comparison',
            label: (
                <span>
                    <ExperimentOutlined />
                    策略对比
                </span>
            ),
            children: (
                <Suspense fallback={<LazyLoadFallback />}>
                    <StrategyComparison strategies={strategies} />
                </Suspense>
            )
        },
        {
            key: 'portfolio',
            label: (
                <span>
                    <PieChartOutlined />
                    组合优化
                </span>
            ),
            children: (
                <Suspense fallback={<LazyLoadFallback />}>
                    <PortfolioOptimizer />
                </Suspense>
            )
        },
        {
            key: 'cross-market',
            label: (
                <span>
                    <GlobalOutlined />
                    跨市场回测
                </span>
            ),
            children: <CrossMarketBacktestPanel />
        }
    ];

    return (
        <Tabs
            defaultActiveKey={initialTab}
            items={tabItems}
            onChange={(key) => {
                const params = new URLSearchParams(window.location.search);
                if (key === 'new') {
                    params.delete(TAB_QUERY_KEY);
                } else {
                    params.set(TAB_QUERY_KEY, key);
                }
                const nextQuery = params.toString();
                const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
                window.history.replaceState(null, '', nextUrl);
            }}
        />
    );
};

export default BacktestDashboard;
