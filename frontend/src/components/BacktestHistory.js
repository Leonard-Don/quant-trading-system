import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Card, Table, Button, Tag, Space, Popconfirm, Tooltip, Modal, Descriptions } from 'antd';
import {
    HistoryOutlined,
    FilePdfOutlined,
    DeleteOutlined,
    ReloadOutlined,
    EyeOutlined
} from '@ant-design/icons';
import { getBacktestHistory, deleteBacktestRecord, getBacktestReport } from '../services/api';
import { formatPercentage } from '../utils/formatting';
import { normalizeBacktestResult } from '../utils/backtest';
import { useSafeMessageApi } from '../utils/messageApi';
import { getStrategyName } from '../constants/strategies';

const BacktestHistory = () => {
    const message = useSafeMessageApi();
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(false);
    const [downloadingId, setDownloadingId] = useState(null);
    const [detailVisible, setDetailVisible] = useState(false);
    const [selectedRecord, setSelectedRecord] = useState(null);
    const [lastUpdatedAt, setLastUpdatedAt] = useState(null);

    const fetchHistory = useCallback(async () => {
        setLoading(true);
        try {
            const response = await getBacktestHistory(50);
            if (response && response.success) {
                setHistory(response.data);
                setLastUpdatedAt(new Date());
            }
        } catch (error) {
            console.error('Failed to fetch history:', error);
            message.error('无法获取回测历史');
        } finally {
            setLoading(false);
        }
    }, [message]);

    useEffect(() => {
        fetchHistory();
    }, [fetchHistory]);

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

    const summaryItems = useMemo(() => {
        const totalRecords = normalizedHistory.length;
        const averageReturn = totalRecords
            ? normalizedHistory.reduce((sum, record) => sum + Number(record.metrics?.total_return || 0), 0) / totalRecords
            : 0;
        const uniqueStrategies = new Set(normalizedHistory.map((record) => record.strategy)).size;
        const mostRecent = normalizedHistory[0]?.timestamp;

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
    }, [lastUpdatedAt, normalizedHistory]);

    const handleDelete = async (id) => {
        try {
            const response = await deleteBacktestRecord(id);
            if (response && response.success) {
                message.success('记录已删除');
                fetchHistory(); // Refresh list
            }
        } catch (error) {
            console.error('Delete failed:', error);
            message.error('删除失败');
        }
    };

    const handleViewDetails = (record) => {
        setSelectedRecord(record);
        setDetailVisible(true);
    };

    const handleDownloadReport = async (record) => {
        setDownloadingId(record.id);
        try {
            // Prepare data for report generation
            // The backend expects the full result object to generate the report
            // If the history record doesn't contain full details, we might need to fetch it first
            // Assuming history record contains 'result' or we pass what we have

            const reportData = {
                symbol: record.symbol,
                strategy: record.strategy,
                parameters: record.parameters,
                backtest_result: normalizeBacktestResult(
                    record.result || { ...record.metrics, metrics: record.metrics }
                ),
                start_date: record.start_date,
                end_date: record.end_date,
            };

            const response = await getBacktestReport(reportData);

            if (response && response.success && response.data) {
                // Data is base64 encoded PDF
                const pdfData = response.data.pdf_base64 || response.data;
                const link = document.createElement('a');
                link.href = `data:application/pdf;base64,${pdfData}`;
                link.download = response.data.filename || `report_${record.symbol}_${record.strategy}_${new Date(record.timestamp).toISOString().split('T')[0]}.pdf`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
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
            width: 150,
            render: (text) => getStrategyName(text)
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
                            disabled={!record.result} // Disable if no detailed result data
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
                        loading={loading}
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
                        <Tag color="blue">{normalizedHistory.length} 条记录</Tag>
                        <Tag color="geekblue">可复盘</Tag>
                    </Space>
                }
                style={{ marginTop: 16 }}
                styles={{ body: { padding: 0 } }}
            >
                <Table
                    dataSource={normalizedHistory}
                    columns={columns}
                    rowKey="id"
                    loading={loading}
                    locale={{ emptyText: '暂无历史记录' }}
                    pagination={{
                        pageSize: 10,
                        showSizeChanger: false,
                        showTotal: (total) => `共 ${total} 条记录`,
                    }}
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
                {selectedRecord && (
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                        <div className="workspace-section">
                            <div className="workspace-section__header">
                                <div>
                                    <div className="workspace-section__title">基本信息</div>
                                    <div className="workspace-section__description">快速确认标的、策略、时间区间和记录生成时间。</div>
                                </div>
                            </div>
                            <Descriptions bordered size="small" column={2}>
                                <Descriptions.Item label="策略">{getStrategyName(selectedRecord.strategy)}</Descriptions.Item>
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
                                {Object.entries(selectedRecord.parameters || {}).map(([key, value]) => (
                                    <Descriptions.Item key={key} label={key}>{String(value)}</Descriptions.Item>
                                ))}
                            </Descriptions>
                        </div>

                        <div className="workspace-section">
                            <div className="workspace-section__header">
                                <div>
                                    <div className="workspace-section__title">性能指标</div>
                                    <div className="workspace-section__description">回放收益、风险和交易统计的核心结论。</div>
                                </div>
                            </div>
                            {renderMetrics(selectedRecord.metrics)}
                        </div>
                    </Space>
                )}
            </Modal>
        </div>
    );
};

export default BacktestHistory;
