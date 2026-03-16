import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Tag, Space, message, Popconfirm, Tooltip, Modal, Descriptions } from 'antd';
import {
    HistoryOutlined,
    FilePdfOutlined,
    DeleteOutlined,
    ReloadOutlined,
    DownloadOutlined,
    EyeOutlined
} from '@ant-design/icons';
import { getBacktestHistory, deleteBacktestRecord, getBacktestReport } from '../services/api';
import { formatPercentage } from '../utils/formatting';
import { getStrategyName } from '../constants/strategies';

const BacktestHistory = () => {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(false);
    const [downloadingId, setDownloadingId] = useState(null);
    const [detailVisible, setDetailVisible] = useState(false);
    const [selectedRecord, setSelectedRecord] = useState(null);

    const fetchHistory = async () => {
        setLoading(true);
        try {
            const response = await getBacktestHistory(50);
            if (response && response.success) {
                setHistory(response.data);
            }
        } catch (error) {
            console.error('Failed to fetch history:', error);
            message.error('无法获取回测历史');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchHistory();
    }, []);

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
                backtest_result: record.result || {} // Ensure we have result data
            };

            const response = await getBacktestReport(reportData);

            if (response && response.success && response.data) {
                // Data is base64 encoded PDF
                const pdfData = response.data.pdf_base64 || response.data;
                const link = document.createElement('a');
                link.href = `data: application / pdf; base64, ${pdfData} `;
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
                <Descriptions.Item label="Sortino比率">{metrics.sortino_ratio?.toFixed(2) || '-'}</Descriptions.Item>
                <Descriptions.Item label="波动率">{formatPercentage(metrics.volatility)}</Descriptions.Item>
            </Descriptions>
        );
    };

    return (
        <>
            <Card
                title={
                    <Space>
                        <HistoryOutlined />
                        <span>回测历史</span>
                    </Space>
                }
                extra={
                    <Button
                        icon={<ReloadOutlined />}
                        onClick={fetchHistory}
                        loading={loading}
                        size="small"
                    >
                        刷新
                    </Button>
                }
                style={{ marginTop: 16 }}
                styles={{ body: { padding: 0 } }}
            >
                <Table
                    dataSource={history}
                    columns={columns}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10 }}
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
                        <Descriptions bordered size="small" column={2}>
                            <Descriptions.Item label="策略">{getStrategyName(selectedRecord.strategy)}</Descriptions.Item>
                            <Descriptions.Item label="股票">{selectedRecord.symbol}</Descriptions.Item>
                            <Descriptions.Item label="开始日期">{selectedRecord.start_date}</Descriptions.Item>
                            <Descriptions.Item label="结束日期">{selectedRecord.end_date}</Descriptions.Item>
                            <Descriptions.Item label="记录时间">{new Date(selectedRecord.timestamp).toLocaleString()}</Descriptions.Item>
                        </Descriptions>

                        <Card title="策略参数" size="small">
                            <Descriptions bordered size="small" column={2}>
                                {Object.entries(selectedRecord.parameters || {}).map(([key, value]) => (
                                    <Descriptions.Item key={key} label={key}>{String(value)}</Descriptions.Item>
                                ))}
                            </Descriptions>
                        </Card>

                        <Card title="性能指标" size="small">
                            {renderMetrics(selectedRecord.metrics)}
                        </Card>
                    </Space>
                )}
            </Modal>
        </>
    );
};

export default BacktestHistory;
