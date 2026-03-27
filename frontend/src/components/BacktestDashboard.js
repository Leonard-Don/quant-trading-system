import React, { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Tabs, Spin, Space, Tag, Typography } from 'antd';
import { BarChartOutlined, HistoryOutlined, ExperimentOutlined, PieChartOutlined, GlobalOutlined, DeploymentUnitOutlined } from '@ant-design/icons';
import StrategyForm from './StrategyForm';
import ResultsDisplay from './ResultsDisplay';
import LoadingSpinner from './LoadingSpinner';
import CrossMarketBacktestPanel from './CrossMarketBacktestPanel';
import { buildAppUrl, navigateToAppUrl, sanitizeParamsForView } from '../utils/researchContext';
import { saveAdvancedExperimentIntent } from '../utils/backtestWorkspace';

// Lazy load history component to keep initial bundle size small
const BacktestHistory = lazy(() => import('./BacktestHistory'));
const StrategyComparison = lazy(() => import('./StrategyComparison'));
const PortfolioOptimizer = lazy(() => import('./PortfolioOptimizer'));
const AdvancedBacktestLab = lazy(() => import('./AdvancedBacktestLab'));

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
const RECORD_QUERY_KEY = 'record';
const VALID_TABS = new Set(['new', 'history', 'comparison', 'portfolio', 'cross-market', 'advanced']);
const TAB_META = {
    new: {
        title: '策略回测工作台',
        description: '从策略配置、执行到结果研判的一体化回测流，适合快速验证想法并沉淀可复用配置。',
        label: '主回测',
    },
    history: {
        title: '历史记录与复盘',
        description: '集中查看历史回测、下载报告并回看关键绩效指标，让每次试验都可追溯。',
        label: '历史',
    },
    comparison: {
        title: '多策略对比',
        description: '把同一标的下的多种策略放进统一评分和图表框架中，快速找出收益与风控的平衡点。',
        label: '对比',
    },
    portfolio: {
        title: '组合优化实验台',
        description: '围绕资产池、目标函数和有效前沿展开配置，查看建议仓位与风险收益分布。',
        label: '优化',
    },
    'cross-market': {
        title: '跨市场策略实验',
        description: '围绕模板、篮子构造、质量约束和联动研究任务，完成跨资产回测与诊断。',
        label: '跨市场',
    },
    advanced: {
        title: '高级实验台',
        description: '把批量回测和 Walk-Forward 接进统一工作流，方便在正式回测之外继续做系统性验证。',
        label: '高级实验',
    },
};

const readBacktestLocationState = (search = window.location.search) => {
    const params = new URLSearchParams(search);
    const tab = params.get(TAB_QUERY_KEY);
    return {
        activeTab: VALID_TABS.has(tab) ? tab : 'new',
        highlightRecordId: params.get(RECORD_QUERY_KEY) || '',
    };
};

const BacktestDashboard = ({ strategies, height, onSubmit, loading, results }) => {
    const [locationState, setLocationState] = useState(() => readBacktestLocationState());
    const { activeTab, highlightRecordId } = locationState;

    useEffect(() => {
        const syncLocationState = () => {
            setLocationState(readBacktestLocationState());
        };

        window.addEventListener('popstate', syncLocationState);
        return () => window.removeEventListener('popstate', syncLocationState);
    }, []);

    const activeMeta = TAB_META[activeTab] || TAB_META.new;
    const heroStats = useMemo(() => {
        const items = [
            { label: '当前工作区', value: activeMeta.label },
            { label: '可用策略', value: `${strategies.length} 个` },
        ];
        if (activeTab === 'new' && loading) {
            items.push({ label: '状态', value: '回测执行中' });
        } else if (activeTab === 'new' && results) {
            items.push({
                label: '最新结果',
                value: `${(Number(results.total_return || 0) * 100).toFixed(2)}%`,
            });
            items.push({
                label: '成交事件',
                value: `${results.num_trades || 0} 笔`,
            });
        } else {
            items.push({ label: '体验风格', value: '量化工作台' });
        }
        return items;
    }, [activeMeta.label, activeTab, loading, results, strategies.length]);

    const setBacktestTab = (key, extraParams = {}) => {
        const params = new URLSearchParams(window.location.search);
        if (key === 'new') {
            params.delete(TAB_QUERY_KEY);
        } else {
            params.set(TAB_QUERY_KEY, key);
        }
        Object.entries(extraParams).forEach(([paramKey, value]) => {
            if (value === undefined || value === null || value === '') {
                params.delete(paramKey);
            } else {
                params.set(paramKey, value);
            }
        });
        sanitizeParamsForView(params, 'backtest');
        const nextUrl = buildAppUrl({
            currentSearch: `?${params.toString()}`,
            view: 'backtest',
            tab: params.get(TAB_QUERY_KEY),
            record: params.get(RECORD_QUERY_KEY),
            historySymbol: params.get('history_symbol'),
            historyStrategy: params.get('history_strategy'),
            template: params.get('template'),
            action: params.get('action'),
            source: params.get('source'),
            note: params.get('note'),
        });
        navigateToAppUrl(nextUrl);
    };

    const handleOpenHistoryRecord = (recordId) => {
        setBacktestTab('history', { [RECORD_QUERY_KEY]: recordId });
    };

    const handleContinueToAdvancedExperiment = () => {
        saveAdvancedExperimentIntent({
            type: 'import_main_backtest',
            created_at: new Date().toISOString(),
        });
        setBacktestTab('advanced');
    };

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
                <div className="workspace-tab-view">
                    <StrategyForm
                        strategies={strategies}
                        onSubmit={onSubmit}
                        loading={loading}
                    />

                    {loading && (
                        <div className="workspace-section">
                            <LoadingSpinner
                                message="正在运行回测，请稍候..."
                                size="large"
                            />
                        </div>
                    )}

                    {results && (
                        <ResultsDisplay
                            results={results}
                            onOpenHistoryRecord={handleOpenHistoryRecord}
                            onContinueAdvancedExperiment={handleContinueToAdvancedExperiment}
                        />
                    )}
                </div>
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
                    <BacktestHistory highlightRecordId={highlightRecordId} />
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
        },
        {
            key: 'advanced',
            label: (
                <span>
                    <DeploymentUnitOutlined />
                    高级实验
                </span>
            ),
            children: (
                <Suspense fallback={<LazyLoadFallback />}>
                    <AdvancedBacktestLab strategies={strategies} />
                </Suspense>
            )
        }
    ];

    return (
        <div className="backtest-workspace">
            <div className="backtest-hero">
                <div className="backtest-hero__content">
                    <div className="workspace-tagline">量化研究工作台</div>
                    <Typography.Title level={2} style={{ margin: 0 }}>
                        {activeMeta.title}
                    </Typography.Title>
                    <Typography.Paragraph className="workspace-subtext">
                        {activeMeta.description}
                    </Typography.Paragraph>
                </div>
                <div className="summary-strip">
                    {heroStats.map((item) => (
                        <div key={item.label} className="summary-strip__item">
                            <span className="summary-strip__label">{item.label}</span>
                            <span className="summary-strip__value">{item.value}</span>
                        </div>
                    ))}
                </div>
                <Space wrap>
                    <Tag color="geekblue">模块统一体验升级</Tag>
                    <Tag color={loading ? 'processing' : 'default'}>
                        {loading ? '回测运行中' : '状态稳定'}
                    </Tag>
                    {results ? (
                        <Tag color={Number(results.total_return || 0) >= 0 ? 'success' : 'error'}>
                            最新收益 {(Number(results.total_return || 0) * 100).toFixed(2)}%
                        </Tag>
                    ) : null}
                </Space>
            </div>

            <div className="backtest-workspace__content">
                <Tabs
                    className="backtest-workspace-tabs"
                    activeKey={activeTab}
                    items={tabItems}
                    onChange={(key) => setBacktestTab(key, { [RECORD_QUERY_KEY]: '' })}
                />
            </div>
        </div>
    );
};

export default BacktestDashboard;
