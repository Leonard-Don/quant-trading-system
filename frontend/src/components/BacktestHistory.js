import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { AutoComplete, Card, Table, Button, Tag, Space, Popconfirm, Tooltip, Modal, Descriptions, Select } from 'antd';
import {
    HistoryOutlined,
    FilePdfOutlined,
    DeleteOutlined,
    ReloadOutlined,
    EyeOutlined,
    SearchOutlined,
    ClearOutlined,
} from '@ant-design/icons';
import {
    getBacktestHistory,
    getBacktestHistoryStats,
    getBacktestRecord,
    deleteBacktestRecord,
    downloadBacktestReport,
} from '../services/api';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';
import { normalizeBacktestResult } from '../utils/backtest';
import { useSafeMessageApi } from '../utils/messageApi';
import { getStrategyName, getStrategyParameterLabel, STRATEGY_NAMES } from '../constants/strategies';
import { navigateToAppUrl } from '../utils/researchContext';
import PerformanceChart from './PerformanceChart';
import {
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip as RechartsTooltip,
    XAxis,
    YAxis,
} from 'recharts';

const HISTORY_SYMBOL_QUERY_KEY = 'history_symbol';
const HISTORY_STRATEGY_QUERY_KEY = 'history_strategy';
const HISTORY_RECORD_TYPE_QUERY_KEY = 'history_record_type';
const RECORD_TYPE_META = {
    backtest: { label: '单次回测', color: 'blue' },
    batch_backtest: { label: '批量回测', color: 'purple' },
    walk_forward: { label: '滚动前瞻', color: 'gold' },
};
const DETAIL_METRIC_KEYS = [
    'avg_win',
    'avg_loss',
    'total_profit',
    'total_loss',
    'loss_rate',
    'avg_holding_days',
    'total_completed_trades',
    'has_open_position',
];
const CHART_POSITIVE = '#22c55e';
const CHART_NEGATIVE = '#ef4444';
const CHART_NEUTRAL = '#0ea5e9';

const getRecordTypeMeta = (recordType) => RECORD_TYPE_META[recordType] || { label: recordType || '实验记录', color: 'default' };

const getRecordStrategyLabel = (record) => {
    if (!record) {
        return '-';
    }
    if (record.record_type === 'batch_backtest') {
        return record.title || getStrategyName(record.strategy);
    }
    if (record.record_type === 'walk_forward') {
        return `${getStrategyName(record.strategy)} · 滚动前瞻`;
    }
    return getStrategyName(record.strategy);
};

const readHistoryFiltersFromSearch = (search = window.location.search) => {
    const params = new URLSearchParams(search);
    return {
        symbol: params.get(HISTORY_SYMBOL_QUERY_KEY) || '',
        strategy: params.get(HISTORY_STRATEGY_QUERY_KEY) || '',
        recordType: params.get(HISTORY_RECORD_TYPE_QUERY_KEY) || '',
    };
};

const hasDetailedMetrics = (record) => {
    if (!record) {
        return false;
    }

    const normalized = normalizeBacktestResult(
        record.result || { ...record.metrics, metrics: record.metrics }
    );

    return DETAIL_METRIC_KEYS.every((key) => normalized.metrics?.[key] !== undefined);
};

const needsRecordDetails = (record) => {
    if (!record) {
        return true;
    }
    if (record.summary_only) {
        return true;
    }

    const recordType = record.record_type || 'backtest';
    if (recordType === 'batch_backtest') {
        return !((record.result?.ranked_results?.length || 0) + (record.result?.results?.length || 0));
    }
    if (recordType === 'walk_forward') {
        return !(record.result?.window_results?.length);
    }

    const result = record.result || {};
    const hasBacktestArtifacts = (
        Object.prototype.hasOwnProperty.call(result, 'portfolio_history')
        || Object.prototype.hasOwnProperty.call(result, 'portfolio')
        || Object.prototype.hasOwnProperty.call(result, 'trades')
    );
    return !hasDetailedMetrics(record) || !hasBacktestArtifacts;
};

const BacktestHistory = ({ highlightRecordId = '' }) => {
    const message = useSafeMessageApi();
    const initialFilters = readHistoryFiltersFromSearch();
    const [history, setHistory] = useState([]);
    const [historyStats, setHistoryStats] = useState(null);
    const [loading, setLoading] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [downloadingId, setDownloadingId] = useState(null);
    const [detailVisible, setDetailVisible] = useState(false);
    const [selectedRecord, setSelectedRecord] = useState(null);
    const [lastUpdatedAt, setLastUpdatedAt] = useState(null);
    const [pagination, setPagination] = useState({
        current: 1,
        pageSize: 10,
        total: 0,
    });
    const currentPage = pagination.current;
    const pageSize = pagination.pageSize;
    const [filters, setFilters] = useState({
        symbol: initialFilters.symbol,
        strategy: initialFilters.strategy,
        recordType: initialFilters.recordType,
    });
    const [filterInputs, setFilterInputs] = useState({
        symbol: initialFilters.symbol,
        strategy: initialFilters.strategy,
        recordType: initialFilters.recordType,
    });

    const updateHistoryFilterQuery = useCallback((nextFilters, { replace = false } = {}) => {
        const params = new URLSearchParams(window.location.search);
        if (nextFilters.symbol) {
            params.set(HISTORY_SYMBOL_QUERY_KEY, nextFilters.symbol);
        } else {
            params.delete(HISTORY_SYMBOL_QUERY_KEY);
        }
        if (nextFilters.strategy) {
            params.set(HISTORY_STRATEGY_QUERY_KEY, nextFilters.strategy);
        } else {
            params.delete(HISTORY_STRATEGY_QUERY_KEY);
        }
        if (nextFilters.recordType) {
            params.set(HISTORY_RECORD_TYPE_QUERY_KEY, nextFilters.recordType);
        } else {
            params.delete(HISTORY_RECORD_TYPE_QUERY_KEY);
        }
        const query = params.toString();
        const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`;
        if (replace) {
            window.history.replaceState(null, '', nextUrl);
            return;
        }
        navigateToAppUrl(nextUrl);
    }, []);

    const fetchHistory = useCallback(async () => {
        setLoading(true);
        try {
            const queryFilters = {
                symbol: filters.symbol || undefined,
                strategy: filters.strategy || undefined,
                recordType: filters.recordType || undefined,
            };
            const offset = (currentPage - 1) * pageSize;
            const [historyResponse, statsResponse] = await Promise.all([
                getBacktestHistory(pageSize, queryFilters, offset, { summaryOnly: true }),
                getBacktestHistoryStats(queryFilters).catch(() => null),
            ]);

            if (historyResponse && historyResponse.success) {
                setHistory(historyResponse.data);
                setLastUpdatedAt(new Date());
                setPagination((current) => ({
                    ...current,
                    total: historyResponse.total ?? current.total,
                }));
            }
            if (statsResponse && statsResponse.success) {
                setHistoryStats(statsResponse.data);
                setPagination((current) => ({
                    ...current,
                    total: statsResponse.data?.total_records ?? current.total,
                }));
            }
        } catch (error) {
            console.error('Failed to fetch history:', error);
            message.error('无法获取回测历史');
        } finally {
            setLoading(false);
        }
    }, [currentPage, filters.recordType, filters.strategy, filters.symbol, message, pageSize]);

    const clearHighlightQuery = useCallback(() => {
        const params = new URLSearchParams(window.location.search);
        if (!params.get('record')) {
            return;
        }
        params.delete('record');
        const query = params.toString();
        window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`);
    }, []);

    const fetchRecordDetails = useCallback(async (recordId) => {
        if (!recordId) {
            return null;
        }

        setDetailLoading(true);
        try {
            const response = await getBacktestRecord(recordId);
            if (response?.success && response.data) {
                const record = response.data;
                const normalizedResult = normalizeBacktestResult(
                    record.result || { ...record.metrics, metrics: record.metrics }
                );
                return {
                    ...record,
                    result: normalizedResult,
                    metrics: normalizedResult.metrics,
                };
            }
            throw new Error(response?.error || '获取详情失败');
        } catch (error) {
            console.error('Failed to fetch backtest record:', error);
            message.error(error.userMessage || error.message || '无法获取回测详情');
            return null;
        } finally {
            setDetailLoading(false);
        }
    }, [message]);

    useEffect(() => {
        fetchHistory();
    }, [fetchHistory]);

    useEffect(() => {
        const syncFiltersFromLocation = () => {
            const nextFilters = readHistoryFiltersFromSearch();
            setFilters(nextFilters);
            setFilterInputs(nextFilters);
            setPagination((current) => ({ ...current, current: 1 }));
        };

        window.addEventListener('popstate', syncFiltersFromLocation);
        return () => window.removeEventListener('popstate', syncFiltersFromLocation);
    }, []);

    const normalizedHistory = useMemo(() => (
        history.map((record) => {
            const normalizedResult = normalizeBacktestResult(
                record.result || { ...record.metrics, metrics: record.metrics }
            );
            return {
                ...record,
                result: normalizedResult,
                metrics: normalizedResult.metrics,
            };
        })
    ), [history]);

    useEffect(() => {
        const openHighlightedRecord = async () => {
            if (!highlightRecordId) {
                return;
            }
            const existing = normalizedHistory.find((record) => record.id === highlightRecordId);
            const record = existing && !needsRecordDetails(existing)
                ? existing
                : (await fetchRecordDetails(highlightRecordId)) || existing;
            if (record) {
                setSelectedRecord(record);
                setDetailVisible(true);
                clearHighlightQuery();
            }
        };

        openHighlightedRecord();
    }, [clearHighlightQuery, fetchRecordDetails, highlightRecordId, normalizedHistory]);

    const summaryItems = useMemo(() => {
        const totalRecords = historyStats?.total_records ?? normalizedHistory.length;
        const averageReturn = historyStats?.avg_return ?? (
            normalizedHistory.length
                ? normalizedHistory.reduce((sum, record) => sum + Number(record.metrics?.total_return || 0), 0) / normalizedHistory.length
                : 0
        );
        const uniqueStrategies = historyStats?.strategy_count ?? (
            historyStats?.strategies
                ? Object.keys(historyStats.strategies).length
                : new Set(normalizedHistory.map((record) => record.strategy)).size
        );
        const mostRecent = historyStats?.latest_record_at || normalizedHistory[0]?.timestamp;

        return [
            { label: '历史记录', value: `${totalRecords} 条` },
            { label: '平均收益', value: formatPercentage(averageReturn) },
            { label: '策略覆盖', value: `${uniqueStrategies} 种` },
            {
                label: '最近更新',
                value: mostRecent
                    ? new Date(mostRecent).toLocaleString()
                    : (lastUpdatedAt ? lastUpdatedAt.toLocaleString() : '尚未加载'),
            },
        ];
    }, [historyStats, lastUpdatedAt, normalizedHistory]);

    const handleDelete = async (id) => {
        try {
            const response = await deleteBacktestRecord(id);
            if (response && response.success) {
                message.success('记录已删除');
                if (normalizedHistory.length === 1 && currentPage > 1) {
                    setPagination((current) => ({
                        ...current,
                        current: current.current - 1,
                        total: Math.max(current.total - 1, 0),
                    }));
                } else {
                    setPagination((current) => ({
                        ...current,
                        total: Math.max(current.total - 1, 0),
                    }));
                    fetchHistory();
                }
            }
        } catch (error) {
            console.error('Delete failed:', error);
            message.error('删除失败');
        }
    };

    const handleSearch = () => {
        const nextFilters = {
            symbol: filterInputs.symbol.trim().toUpperCase(),
            strategy: filterInputs.strategy,
            recordType: filterInputs.recordType,
        };
        setFilters(nextFilters);
        setPagination((current) => ({ ...current, current: 1 }));
        updateHistoryFilterQuery(nextFilters);
    };

    const handleResetFilters = () => {
        const nextFilters = { symbol: '', strategy: '', recordType: '' };
        setFilterInputs(nextFilters);
        setFilters(nextFilters);
        setPagination((current) => ({ ...current, current: 1 }));
        updateHistoryFilterQuery(nextFilters);
    };

    const handleTableChange = (nextPagination) => {
        setPagination((current) => ({
            ...current,
            current: nextPagination.current || current.current,
            pageSize: nextPagination.pageSize || current.pageSize,
        }));
    };

    const handleViewDetails = async (record) => {
        const detailedRecord = !needsRecordDetails(record)
            ? record
            : (await fetchRecordDetails(record.id)) || record;
        if (!detailedRecord) {
            return;
        }
        setSelectedRecord(detailedRecord);
        setDetailVisible(true);
    };

    const handleDownloadReport = async (record) => {
        setDownloadingId(record.id);
        try {
            const detailedRecord = !needsRecordDetails(record)
                ? record
                : (await fetchRecordDetails(record.id)) || record;
            if (!detailedRecord) {
                return;
            }

            const reportData = {
                symbol: detailedRecord.symbol,
                strategy: detailedRecord.strategy,
                parameters: detailedRecord.parameters,
                backtest_result: normalizeBacktestResult(
                    detailedRecord.result || { ...detailedRecord.metrics, metrics: detailedRecord.metrics }
                ),
                start_date: detailedRecord.start_date,
                end_date: detailedRecord.end_date,
            };

            const response = await downloadBacktestReport(reportData);

            if (response?.blob) {
                const link = document.createElement('a');
                const objectUrl = URL.createObjectURL(response.blob);
                link.href = objectUrl;
                link.download = response.filename || `report_${detailedRecord.symbol}_${detailedRecord.strategy}_${new Date(detailedRecord.timestamp).toISOString().split('T')[0]}.pdf`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(objectUrl);
                message.success('报告已下载');
            } else {
                message.error('生成报告失败');
            }
        } catch (error) {
            console.error('Download report failed:', error);
            message.error('下载报告失败');
        } finally {
            setDownloadingId(null);
        }
    };

    const columns = [
        {
            title: '时间',
            dataIndex: 'timestamp',
            key: 'timestamp',
            width: 180,
            render: (text) => {
                if (!text) return '-';
                const date = new Date(text);
                return isNaN(date.getTime()) ? '-' : date.toLocaleString();
            }
        },
        {
            title: '类型',
            dataIndex: 'record_type',
            key: 'record_type',
            width: 110,
            render: (value) => {
                const meta = getRecordTypeMeta(value || 'backtest');
                return <Tag color={meta.color}>{meta.label}</Tag>;
            }
        },
        {
            title: '股票',
            dataIndex: 'symbol',
            key: 'symbol',
            width: 100,
            render: (text) => <Tag color="blue">{text}</Tag>
        },
        {
            title: '策略',
            dataIndex: 'strategy',
            key: 'strategy',
            width: 180,
            render: (_, record) => getRecordStrategyLabel(record)
        },
        {
            title: '收益率',
            dataIndex: ['metrics', 'total_return'],
            key: 'return',
            width: 120,
            render: (val) => {
                // val is decimal, formatPercentage expects decimal
                const formatted = formatPercentage(val);
                const color = val >= 0 ? 'green' : 'red';
                return <span style={{ color }}>{formatted}</span>;
            }
        },
        {
            title: '夏普比率',
            dataIndex: ['metrics', 'sharpe_ratio'],
            key: 'sharpe',
            width: 100,
            render: (val) => val?.toFixed(2) || '-'
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Space size="small">
                    <Tooltip title="查看详情">
                        <Button
                            type="default"
                            shape="circle"
                            icon={<EyeOutlined />}
                            size="small"
                            onClick={() => handleViewDetails(record)}
                        />
                    </Tooltip>
                    <Tooltip title="下载PDF报告">
                        <Button
                            type="primary"
                            shape="circle"
                            icon={<FilePdfOutlined />}
                            size="small"
                            onClick={() => handleDownloadReport(record)}
                            loading={downloadingId === record.id}
                            disabled={(record.record_type || 'backtest') !== 'backtest'}
                        />
                    </Tooltip>
                    <Popconfirm
                        title="确定删除这条记录吗?"
                        onConfirm={() => handleDelete(record.id)}
                        okText="删除"
                        cancelText="取消"
                    >
                        <Button
                            type="text"
                            danger
                            shape="circle"
                            icon={<DeleteOutlined />}
                            size="small"
                        />
                    </Popconfirm>
                </Space>
            )
        }
    ];

    const strategyOptions = useMemo(() => {
        const preferredStrategies = Object.keys(historyStats?.strategies || {});
        const fallbackStrategies = Object.keys(STRATEGY_NAMES).filter((key) => !['unknown', 'combined'].includes(key));
        const merged = [...new Set([...preferredStrategies, ...fallbackStrategies])];
        return merged.map((value) => ({
            value,
            label: getStrategyName(value),
        }));
    }, [historyStats]);

    const symbolOptions = useMemo(() => {
        const historicalSymbols = Object.keys(historyStats?.symbols || {});
        const currentPageSymbols = normalizedHistory.map((record) => record.symbol).filter(Boolean);
        const currentInput = filterInputs.symbol ? [filterInputs.symbol.toUpperCase()] : [];
        return [...new Set([...historicalSymbols, ...currentPageSymbols, ...currentInput])]
            .filter(Boolean)
            .sort()
            .map((symbol) => ({ value: symbol }));
    }, [filterInputs.symbol, historyStats, normalizedHistory]);

    // Helper to render metrics content
    const renderMetrics = (metrics) => {
        if (!metrics) return null;
        return (
            <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="总收益率">{formatPercentage(metrics.total_return)}</Descriptions.Item>
                <Descriptions.Item label="年化收益率">{formatPercentage(metrics.annualized_return)}</Descriptions.Item>
                <Descriptions.Item label="夏普比率">{metrics.sharpe_ratio?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="最大回撤">{formatPercentage(metrics.max_drawdown)}</Descriptions.Item>
                <Descriptions.Item label="交易次数">{metrics.total_trades || metrics.num_trades}</Descriptions.Item>
                <Descriptions.Item label="胜率">{formatPercentage(metrics.win_rate)}</Descriptions.Item>
                <Descriptions.Item label="索提诺比率">{metrics.sortino_ratio?.toFixed(2) || '-'}</Descriptions.Item>
                <Descriptions.Item label="波动率">{formatPercentage(metrics.volatility)}</Descriptions.Item>
            </Descriptions>
        );
    };

    const renderDiagnosticMetrics = (metrics) => {
        if (!metrics) return null;
        return (
            <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="最终价值">{formatCurrency(metrics.final_value || 0)}</Descriptions.Item>
                <Descriptions.Item label="净利润">{formatCurrency(metrics.net_profit || 0)}</Descriptions.Item>
                <Descriptions.Item label="平均盈利">{formatCurrency(metrics.avg_win || 0)}</Descriptions.Item>
                <Descriptions.Item label="平均亏损">{formatCurrency(metrics.avg_loss || 0)}</Descriptions.Item>
                <Descriptions.Item label="累计盈利">{formatCurrency(metrics.total_profit || 0)}</Descriptions.Item>
                <Descriptions.Item label="累计亏损">{formatCurrency(metrics.total_loss || 0)}</Descriptions.Item>
                <Descriptions.Item label="亏损率">{formatPercentage(metrics.loss_rate || 0)}</Descriptions.Item>
                <Descriptions.Item label="平均持仓天数">
                    {metrics.avg_holding_days ? `${Number(metrics.avg_holding_days).toFixed(1)} 天` : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="完成交易">{metrics.total_completed_trades || 0}</Descriptions.Item>
                <Descriptions.Item label="持仓状态">{metrics.has_open_position ? '仍有未平仓' : '已全部平仓'}</Descriptions.Item>
            </Descriptions>
        );
    };

    const renderExperimentSummaryMetrics = (recordType, metrics, parameters = {}) => {
        if (!metrics) return null;

        if (recordType === 'batch_backtest') {
            const totalTasks = Number(metrics.total_tasks || 0);
            const successful = Number(metrics.successful || 0);
            const successRate = totalTasks > 0 ? successful / totalTasks : 0;
            const selectedStrategies = Array.isArray(parameters.strategies) ? parameters.strategies : [];
            return (
                <Descriptions bordered size="small" column={2}>
                    <Descriptions.Item label="平均收益率">{formatPercentage(metrics.average_return ?? metrics.total_return ?? 0)}</Descriptions.Item>
                    <Descriptions.Item label="平均夏普比率">{Number(metrics.average_sharpe ?? metrics.sharpe_ratio ?? 0).toFixed(2)}</Descriptions.Item>
                    <Descriptions.Item label="总任务数">{totalTasks}</Descriptions.Item>
                    <Descriptions.Item label="成功任务">{successful}</Descriptions.Item>
                    <Descriptions.Item label="成功率">{formatPercentage(successRate)}</Descriptions.Item>
                    <Descriptions.Item label="排名指标">{parameters.ranking_metric || metrics.ranking_metric || '-'}</Descriptions.Item>
                    <Descriptions.Item label="保留前 N 名">{parameters.top_n || '-'}</Descriptions.Item>
                    <Descriptions.Item label="参与策略数">{selectedStrategies.length || '-'}</Descriptions.Item>
                </Descriptions>
            );
        }

        if (recordType === 'walk_forward') {
            const totalWindows = Number(metrics.n_windows || 0);
            const positiveWindows = Number(metrics.positive_windows || 0);
            const negativeWindows = Number(metrics.negative_windows || 0);
            const positiveRate = totalWindows > 0 ? positiveWindows / totalWindows : 0;
            return (
                <Descriptions bordered size="small" column={2}>
                    <Descriptions.Item label="滚动窗口数">{totalWindows}</Descriptions.Item>
                    <Descriptions.Item label="正收益窗口">{positiveWindows}</Descriptions.Item>
                    <Descriptions.Item label="负收益窗口">{negativeWindows}</Descriptions.Item>
                    <Descriptions.Item label="正收益占比">{formatPercentage(positiveRate)}</Descriptions.Item>
                    <Descriptions.Item label="平均收益率">{formatPercentage(metrics.total_return || 0)}</Descriptions.Item>
                    <Descriptions.Item label="平均夏普比率">{Number(metrics.sharpe_ratio || 0).toFixed(2)}</Descriptions.Item>
                    <Descriptions.Item label="收益波动">{formatPercentage(metrics.return_std || 0)}</Descriptions.Item>
                    <Descriptions.Item label="训练 / 测试 / 步长">{`${metrics.train_period || parameters.train_period || '-'} / ${metrics.test_period || parameters.test_period || '-'} / ${metrics.step_size || parameters.step_size || '-'}`}</Descriptions.Item>
                </Descriptions>
            );
        }

        return null;
    };

    const detailTrades = selectedRecord?.result?.trades || [];
    const detailPortfolioHistory = selectedRecord?.result?.portfolio_history
        || selectedRecord?.result?.portfolio
        || [];
    const detailBatchResults = selectedRecord?.result?.ranked_results?.length
        ? selectedRecord?.result?.ranked_results
        : selectedRecord?.result?.results || [];
    const detailWalkWindows = selectedRecord?.result?.window_results || [];
    const selectedRecordType = selectedRecord?.record_type || 'backtest';
    const batchChartData = detailBatchResults.map((record) => ({
        key: record.task_id,
        label: getStrategyName(record.strategy),
        totalReturn: Number(record.metrics?.total_return || 0),
        sharpe: Number(record.metrics?.sharpe_ratio || 0),
    }));
    const walkChartData = detailWalkWindows.map((record) => ({
        key: `${record.window_id}-${record.test_start}`,
        label: `窗口 ${Number(record.window_id || 0) + 1}`,
        totalReturn: Number(record.metrics?.total_return || 0),
        drawdown: Math.abs(Number(record.metrics?.max_drawdown || 0)),
        range: `${record.test_start} ~ ${record.test_end}`,
    }));
    const tradeColumns = [
        {
            title: '日期',
            dataIndex: 'date',
            key: 'date',
            render: (value) => {
                if (!value) return '-';
                const date = new Date(value);
                return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString();
            },
        },
        {
            title: '类型',
            dataIndex: 'type',
            key: 'type',
            render: (value) => (
                <Tag color={String(value).toUpperCase() === 'BUY' ? 'green' : 'red'}>
                    {String(value).toUpperCase() === 'BUY' ? '买入' : '卖出'}
                </Tag>
            ),
        },
        {
            title: '价格',
            dataIndex: 'price',
            key: 'price',
            render: (value) => formatCurrency(value || 0),
        },
        {
            title: '数量',
            dataIndex: 'quantity',
            key: 'quantity',
        },
        {
            title: '金额',
            dataIndex: 'value',
            key: 'value',
            render: (value) => formatCurrency(value || 0),
        },
        {
            title: '盈亏',
            dataIndex: 'pnl',
            key: 'pnl',
            render: (value) => (
                <span style={{ color: getValueColor(value || 0) }}>
                    {value === undefined || value === null ? '-' : formatCurrency(value)}
                </span>
            ),
        },
    ];

    const batchResultColumns = [
        {
            title: '任务',
            dataIndex: 'task_id',
            key: 'task_id',
        },
        {
            title: '策略',
            dataIndex: 'strategy',
            key: 'strategy',
            render: (value) => getStrategyName(value),
        },
        {
            title: '总收益率',
            key: 'total_return',
            render: (_, record) => formatPercentage(record.metrics?.total_return || 0),
        },
        {
            title: '夏普比率',
            key: 'sharpe_ratio',
            render: (_, record) => Number(record.metrics?.sharpe_ratio || 0).toFixed(2),
        },
        {
            title: '状态',
            key: 'success',
            render: (_, record) => record.success === false ? <Tag color="error">失败</Tag> : <Tag color="success">成功</Tag>,
        },
    ];

    const walkWindowColumns = [
        {
            title: '窗口',
            dataIndex: 'window_id',
            key: 'window_id',
            render: (value) => `窗口 ${Number(value || 0) + 1}`,
        },
        {
            title: '测试区间',
            key: 'range',
            render: (_, record) => `${record.test_start} ~ ${record.test_end}`,
        },
        {
            title: '总收益率',
            key: 'total_return',
            render: (_, record) => formatPercentage(record.metrics?.total_return || 0),
        },
        {
            title: '夏普比率',
            key: 'sharpe_ratio',
            render: (_, record) => Number(record.metrics?.sharpe_ratio || 0).toFixed(2),
        },
        {
            title: '最大回撤',
            key: 'max_drawdown',
            render: (_, record) => formatPercentage(record.metrics?.max_drawdown || 0),
        },
    ];

    const renderBatchHistoryTooltip = ({ active, payload }) => {
        if (!active || !payload?.length) {
            return null;
        }
        const point = payload[0]?.payload;
        if (!point) {
            return null;
        }

        return (
            <div className="chart-tooltip">
                <div style={{ fontWeight: 700, marginBottom: 6 }}>{point.label}</div>
                <div>总收益率 {formatPercentage(point.totalReturn)}</div>
                <div>夏普比率 {Number(point.sharpe || 0).toFixed(2)}</div>
            </div>
        );
    };

    const renderWalkHistoryTooltip = ({ active, payload }) => {
        if (!active || !payload?.length) {
            return null;
        }
        const point = payload[0]?.payload;
        if (!point) {
            return null;
        }

        return (
            <div className="chart-tooltip">
                <div style={{ fontWeight: 700, marginBottom: 6 }}>{point.label}</div>
                <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{point.range}</div>
                <div>窗口收益 {formatPercentage(point.totalReturn)}</div>
                <div>最大回撤绝对值 {formatPercentage(point.drawdown)}</div>
            </div>
        );
    };

    return (
        <div className="workspace-tab-view">
            <div className="workspace-section workspace-section--accent">
                <div className="workspace-section__header">
                    <div>
                        <div className="workspace-section__title">历史记录与复盘</div>
                        <div className="workspace-section__description">把历史回测、报告下载和详情查看收敛到同一条工作流里，方便回顾实验结果。</div>
                    </div>
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={fetchHistory}
                        loading={loading || detailLoading}
                        size="small"
                    >
                        刷新记录
                    </Button>
                </div>
                <div className="summary-strip summary-strip--compact">
                    {summaryItems.map((item) => (
                        <div key={item.label} className="summary-strip__item">
                            <span className="summary-strip__label">{item.label}</span>
                            <span className="summary-strip__value">{item.value}</span>
                        </div>
                    ))}
                </div>
            </div>

            <Card
                className="workspace-panel"
                title={
                    <div className="workspace-title">
                        <div className="workspace-title__icon">
                            <HistoryOutlined />
                        </div>
                        <div>
                            <div className="workspace-title__text">回测历史</div>
                            <div className="workspace-title__hint">查看列表、打开详情、删除记录或生成报告。</div>
                        </div>
                    </div>
                }
                extra={
                    <Space wrap className="workspace-toolbar">
                        <Tag color="blue">{summaryItems[0]?.value || `${normalizedHistory.length} 条记录`}</Tag>
                        {filters.symbol ? <Tag color="cyan">标的 {filters.symbol}</Tag> : null}
                        {filters.strategy ? <Tag color="purple">{getStrategyName(filters.strategy)}</Tag> : null}
                        {filters.recordType ? <Tag color={getRecordTypeMeta(filters.recordType).color}>{getRecordTypeMeta(filters.recordType).label}</Tag> : null}
                        <Tag color="geekblue">可复盘</Tag>
                    </Space>
                }
                style={{ marginTop: 16 }}
                styles={{ body: { padding: 0 } }}
            >
                <div className="workspace-toolbar" style={{ padding: '16px 16px 0', display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                    <AutoComplete
                        allowClear
                        placeholder="按股票代码筛选，如 AAPL"
                        value={filterInputs.symbol}
                        options={symbolOptions}
                        onChange={(value) => setFilterInputs((current) => ({ ...current, symbol: String(value || '').toUpperCase() }))}
                        onSelect={(value) => setFilterInputs((current) => ({ ...current, symbol: String(value).toUpperCase() }))}
                        onKeyDown={(event) => {
                            if (event.key === 'Enter') {
                                handleSearch();
                            }
                        }}
                        style={{ width: 220 }}
                    />
                    <Select
                        allowClear
                        placeholder="按策略筛选"
                        value={filterInputs.strategy || undefined}
                        onChange={(value) => setFilterInputs((current) => ({ ...current, strategy: value || '' }))}
                        options={strategyOptions}
                        style={{ width: 220 }}
                    />
                    <Select
                        allowClear
                        placeholder="按类型筛选"
                        value={filterInputs.recordType || undefined}
                        onChange={(value) => setFilterInputs((current) => ({ ...current, recordType: value || '' }))}
                        options={Object.entries(RECORD_TYPE_META).map(([value, meta]) => ({
                            value,
                            label: meta.label,
                        }))}
                        style={{ width: 180 }}
                    />
                    <Space wrap>
                        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
                            应用筛选
                        </Button>
                        <Button icon={<ClearOutlined />} onClick={handleResetFilters}>
                            清空筛选
                        </Button>
                    </Space>
                </div>
                <Table
                    dataSource={normalizedHistory}
                    columns={columns}
                    rowKey="id"
                    loading={loading || detailLoading}
                    locale={{ emptyText: '暂无历史记录' }}
                    pagination={{
                        current: pagination.current,
                        pageSize: pagination.pageSize,
                        total: pagination.total,
                        showSizeChanger: true,
                        pageSizeOptions: ['10', '20', '50'],
                        showTotal: (total) => `共 ${total} 条记录`,
                    }}
                    onChange={handleTableChange}
                    size="small"
                />
            </Card>

            <Modal
                title="回测详情"
                open={detailVisible}
                onCancel={() => setDetailVisible(false)}
                footer={[
                    <Button key="close" onClick={() => setDetailVisible(false)}>
                        关闭
                    </Button>,
                    selectedRecord && (
                        <Button
                            key="download"
                            type="primary"
                            icon={<FilePdfOutlined />}
                            onClick={() => handleDownloadReport(selectedRecord)}
                            loading={downloadingId === selectedRecord.id}
                        >
                            下载报告
                        </Button>
                    )
                ]}
                width={800}
            >
                {detailLoading && !selectedRecord ? (
                    <div style={{ padding: '24px 0', textAlign: 'center' }}>正在加载详情...</div>
                ) : selectedRecord && (
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                        <div className="workspace-section">
                            <div className="workspace-section__header">
                                <div>
                                    <div className="workspace-section__title">基本信息</div>
                                    <div className="workspace-section__description">快速确认标的、策略、时间区间和记录生成时间。</div>
                                </div>
                            </div>
                            <Descriptions bordered size="small" column={2}>
                                <Descriptions.Item label="记录类型">
                                    <Tag color={getRecordTypeMeta(selectedRecordType).color}>
                                        {getRecordTypeMeta(selectedRecordType).label}
                                    </Tag>
                                </Descriptions.Item>
                                <Descriptions.Item label="标题">{selectedRecord.title || getRecordStrategyLabel(selectedRecord)}</Descriptions.Item>
                                <Descriptions.Item label="策略">{getRecordStrategyLabel(selectedRecord)}</Descriptions.Item>
                                <Descriptions.Item label="股票">{selectedRecord.symbol}</Descriptions.Item>
                                <Descriptions.Item label="开始日期">{selectedRecord.start_date}</Descriptions.Item>
                                <Descriptions.Item label="结束日期">{selectedRecord.end_date}</Descriptions.Item>
                                <Descriptions.Item label="记录时间">{new Date(selectedRecord.timestamp).toLocaleString()}</Descriptions.Item>
                            </Descriptions>
                        </div>

                        <div className="workspace-section">
                            <div className="workspace-section__header">
                                <div>
                                    <div className="workspace-section__title">策略参数</div>
                                    <div className="workspace-section__description">记录当时的参数快照，方便后续复现实验配置。</div>
                                </div>
                            </div>
                            <Descriptions bordered size="small" column={2}>
                                {Object.entries(selectedRecord.parameters || {}).length > 0 ? (
                                    Object.entries(selectedRecord.parameters || {}).map(([key, value]) => (
                                        <Descriptions.Item key={key} label={getStrategyParameterLabel(key, key)}>
                                            {String(value)}
                                        </Descriptions.Item>
                                    ))
                                ) : (
                                    <Descriptions.Item label="参数快照" span={2}>
                                        当前记录未保存额外参数
                                    </Descriptions.Item>
                                )}
                            </Descriptions>
                        </div>

                        {selectedRecordType === 'backtest' ? (
                            <>
                                <div className="workspace-section">
                                    <div className="workspace-section__header">
                                        <div>
                                            <div className="workspace-section__title">性能指标</div>
                                            <div className="workspace-section__description">回放收益、风险和交易统计的核心结论。</div>
                                        </div>
                                    </div>
                                    {renderMetrics(selectedRecord.metrics)}
                                </div>

                                <div className="workspace-section">
                                    <div className="workspace-section__header">
                                        <div>
                                            <div className="workspace-section__title">扩展诊断</div>
                                            <div className="workspace-section__description">补充最终价值、盈亏拆解、持仓状态和平均持仓时长，帮助快速复盘结果质量。</div>
                                        </div>
                                    </div>
                                    {renderDiagnosticMetrics(selectedRecord.metrics)}
                                </div>
                            </>
                        ) : (
                            <div className="workspace-section">
                                <div className="workspace-section__header">
                                    <div>
                                        <div className="workspace-section__title">实验摘要</div>
                                        <div className="workspace-section__description">根据实验类型显示最关键的任务规模、成功率或窗口分布，方便快速判断结果质量。</div>
                                    </div>
                                </div>
                                {renderExperimentSummaryMetrics(selectedRecordType, selectedRecord.metrics, selectedRecord.parameters)}
                            </div>
                        )}

                        {selectedRecordType === 'backtest' ? (
                            <>
                                <div className="workspace-section">
                                    <div className="workspace-section__header">
                                        <div>
                                            <div className="workspace-section__title">交易明细</div>
                                            <div className="workspace-section__description">直接查看历史记录里的买卖轨迹与单笔盈亏，不必再额外打开导出报告。</div>
                                        </div>
                                    </div>
                                    <Table
                                        columns={tradeColumns}
                                        dataSource={detailTrades}
                                        rowKey={(record) => `${record.date}-${record.type}-${record.quantity}-${record.price}`}
                                        locale={{ emptyText: '暂无交易明细' }}
                                        pagination={false}
                                        size="small"
                                    />
                                </div>

                                <div className="workspace-section workspace-chart-card">
                                    <div className="workspace-section__header">
                                        <div>
                                            <div className="workspace-section__title">组合净值回放</div>
                                            <div className="workspace-section__description">直接在历史详情里查看当次回测的净值曲线与交易信号落点。</div>
                                        </div>
                                    </div>
                                    <PerformanceChart data={detailPortfolioHistory} />
                                </div>
                            </>
                        ) : null}

                        {selectedRecordType === 'batch_backtest' ? (
                            <>
                                {batchChartData.length ? (
                                    <div className="workspace-section workspace-chart-card">
                                        <div className="workspace-section__header">
                                            <div>
                                                <div className="workspace-section__title">策略表现概览</div>
                                                <div className="workspace-section__description">快速比较这次批量实验里各策略的收益和夏普表现。</div>
                                            </div>
                                        </div>
                                        <div style={{ height: 280 }}>
                                            <ResponsiveContainer width="100%" height="100%">
                                                <BarChart data={batchChartData} margin={{ top: 8, right: 12, left: 8, bottom: 16 }}>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                                                    <XAxis
                                                        dataKey="label"
                                                        tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                                                        interval={0}
                                                        angle={-10}
                                                        textAnchor="end"
                                                        height={56}
                                                    />
                                                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                                                    <RechartsTooltip content={renderBatchHistoryTooltip} />
                                                    <Bar dataKey="totalReturn" name="总收益率">
                                                        {batchChartData.map((entry) => (
                                                            <Cell key={entry.key} fill={entry.totalReturn >= 0 ? CHART_POSITIVE : CHART_NEGATIVE} />
                                                        ))}
                                                    </Bar>
                                                    <Bar dataKey="sharpe" name="夏普比率" fill={CHART_NEUTRAL} />
                                                </BarChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </div>
                                ) : null}
                                <div className="workspace-section">
                                    <div className="workspace-section__header">
                                        <div>
                                            <div className="workspace-section__title">批量结果明细</div>
                                            <div className="workspace-section__description">查看本次批量实验下每个策略任务的收益、夏普和执行状态。</div>
                                        </div>
                                    </div>
                                    <Table
                                        columns={batchResultColumns}
                                        dataSource={detailBatchResults}
                                        rowKey={(record) => record.task_id}
                                        locale={{ emptyText: '暂无批量结果' }}
                                        pagination={false}
                                        size="small"
                                    />
                                </div>
                            </>
                        ) : null}

                        {selectedRecordType === 'walk_forward' ? (
                            <>
                                {walkChartData.length ? (
                                    <div className="workspace-section workspace-chart-card">
                                        <div className="workspace-section__header">
                                            <div>
                                                <div className="workspace-section__title">窗口收益曲线</div>
                                                <div className="workspace-section__description">观察不同测试窗口的收益和回撤变化，判断策略在不同阶段的稳定性。</div>
                                            </div>
                                        </div>
                                        <div style={{ height: 280 }}>
                                            <ResponsiveContainer width="100%" height="100%">
                                                <LineChart data={walkChartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.18)" />
                                                    <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                                                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                                                    <RechartsTooltip content={renderWalkHistoryTooltip} />
                                                    <Line
                                                        type="monotone"
                                                        dataKey="totalReturn"
                                                        name="窗口收益"
                                                        stroke={CHART_POSITIVE}
                                                        strokeWidth={2.5}
                                                        dot={{ r: 3 }}
                                                        activeDot={{ r: 5 }}
                                                    />
                                                    <Line
                                                        type="monotone"
                                                        dataKey="drawdown"
                                                        name="最大回撤绝对值"
                                                        stroke={CHART_NEGATIVE}
                                                        strokeWidth={2}
                                                        strokeDasharray="6 4"
                                                        dot={{ r: 2 }}
                                                    />
                                                </LineChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </div>
                                ) : null}
                                <div className="workspace-section">
                                    <div className="workspace-section__header">
                                        <div>
                                            <div className="workspace-section__title">滚动窗口明细</div>
                                            <div className="workspace-section__description">回看每个测试窗口的收益、夏普和回撤，判断策略在不同阶段的稳定性。</div>
                                        </div>
                                    </div>
                                    <Table
                                        columns={walkWindowColumns}
                                        dataSource={detailWalkWindows}
                                        rowKey={(record) => `${record.window_id}-${record.test_start}`}
                                        locale={{ emptyText: '暂无窗口结果' }}
                                        pagination={false}
                                        size="small"
                                    />
                                </div>
                            </>
                        ) : null}
                    </Space>
                )}
            </Modal>
        </div>
    );
};

export default BacktestHistory;
