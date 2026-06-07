/**
 * Column descriptor factory for the industry constituent-stock table (split out
 * of IndustryDashboard, mirroring `buildIndustryPolicySignalColumn`).
 *
 * Returns the antd `columns` array verbatim from the former inline definition,
 * receiving the backtest handler it closes over as a deps object so the
 * render logic stays testable and the parent stays the orchestrator.
 */

import { Tag, Button, Tooltip } from 'antd';
import { BarChartOutlined } from '@ant-design/icons';
import {
    formatIndustryAlertMoneyFlow,
    getIndustryScoreTone,
} from './industryShared';

const buildStockColumns = ({ onBacktestStock }) => [
    {
        title: '排名',
        dataIndex: 'rank',
        key: 'rank',
        width: 55
    },
    {
        title: '代码',
        dataIndex: 'symbol',
        key: 'symbol',
        width: 80,
        render: (symbol) => <Tag color="blue">{symbol}</Tag>
    },
    {
        title: '名称',
        dataIndex: 'name',
        key: 'name',
        width: 100
    },
    {
        title: '得分',
        dataIndex: 'total_score',
        key: 'total_score',
        width: 80,
        render: (score) => {
            if (score === null || score === undefined || Number(score) <= 0) {
                return '-';
            }
            return (
                <Tooltip title={`综合评分 ${Number(score).toFixed(1)}`}>
                    <span style={{ fontWeight: 700, color: getIndustryScoreTone(score) }}>
                        {Number(score).toFixed(1)}
                    </span>
                </Tooltip>
            );
        }
    },
    {
        title: '涨跌幅',
        dataIndex: 'change_pct',
        key: 'change_pct',
        width: 90,
        render: (value) => {
            if (value === null || value === undefined) {
                return '-';
            }
            return (
                <span style={{ color: value >= 0 ? '#cf1322' : '#3f8600' }}>
                    {value >= 0 ? '+' : ''}{value.toFixed(2)}%
                </span>
            );
        }
    },
    {
        title: '主力净流入',
        dataIndex: 'money_flow',
        key: 'money_flow',
        width: 110,
        render: (value) => (
            value === null || value === undefined
                ? '-'
                : (
                    <span style={{ color: Number(value) >= 0 ? '#cf1322' : '#3f8600' }}>
                        {formatIndustryAlertMoneyFlow(Number(value))}
                    </span>
                )
        )
    },
    {
        title: '换手率',
        dataIndex: 'turnover_rate',
        key: 'turnover_rate',
        width: 86,
        render: (_, record) => {
            const value = record.turnover_rate ?? record.turnover;
            return value === null || value === undefined || Number.isNaN(Number(value))
                ? '-'
                : `${Number(value).toFixed(2)}%`;
        }
    },
    {
        title: '市值(亿)',
        dataIndex: 'market_cap',
        key: 'market_cap',
        width: 90,
        render: (value) => (
            value === null || value === undefined ? '-' : (value / 100000000).toFixed(1)
        )
    },
    {
        title: 'PE',
        dataIndex: 'pe_ratio',
        key: 'pe_ratio',
        width: 70,
        render: (value) => (
            value === null || value === undefined || value <= 0 ? '-' : value.toFixed(1)
        )
    },
    {
        title: '操作',
        key: 'backtest',
        width: 82,
        render: (_, record) => (
            <Button
                className="industry-inline-link"
                type="link"
                size="small"
                icon={<BarChartOutlined />}
                onClick={(event) => {
                    event.stopPropagation();
                    onBacktestStock(record, 'industry_stock_table');
                }}
                style={{ padding: 0, height: 'auto', fontSize: 12 }}
            >
                回测
            </Button>
        )
    }
];

export default buildStockColumns;
