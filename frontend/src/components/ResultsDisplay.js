import React, { useState } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tabs,
  Button,
  message,
  Space,
  Tag,
  Dropdown
} from 'antd';
import {
  CopyOutlined,
  TrophyOutlined,
  DollarOutlined,
  LineChartOutlined,
  BarChartOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  FallOutlined,
  NumberOutlined,
  TransactionOutlined
} from '@ant-design/icons';
import { getBacktestReport } from '../services/api';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';
import PerformanceChart from './PerformanceChart';
import DrawdownChart from './DrawdownChart';
import MonthlyHeatmap from './MonthlyHeatmap';
import RiskRadar from './RiskRadar';
import ReturnHistogram from './ReturnHistogram';

const ResultsDisplay = ({ results }) => {
  const [activeTab, setActiveTab] = useState('overview');

  const copyResults = () => {
    const text = `
回测结果摘要
====================
总收益率: ${formatPercentage(results.total_return)}
年化收益率: ${formatPercentage(results.annualized_return)}
夏普比率: ${results.sharpe_ratio?.toFixed(2) || 'N/A'}
最大回撤: ${formatPercentage(Math.abs(results.max_drawdown))}
交易次数: ${results.num_trades || 0}
胜率: ${formatPercentage(results.win_rate)}
盈亏比: ${results.profit_factor?.toFixed(2) || 'N/A'}
最佳交易: ${results.best_trade?.toFixed(2) || 'N/A'}
最差交易: ${results.worst_trade?.toFixed(2) || 'N/A'}
净利润: ${results.net_profit?.toFixed(2) || 'N/A'}
最大连续盈利: ${results.max_consecutive_wins || 0}
最大连续亏损: ${results.max_consecutive_losses || 0}
====================
生成时间: ${new Date().toLocaleString()}
    `;

    navigator.clipboard.writeText(text).then(() => {
      message.success('结果已复制到剪贴板');
    }).catch(() => {
      message.error('复制失败');
    });
  };

  // 导出为CSV
  const exportToCSV = () => {
    try {
      // 构建汇总数据
      let csvContent = '回测结果汇总\n';
      csvContent += '指标,数值\n';
      csvContent += `总收益率,${(results.total_return * 100).toFixed(2)}%\n`;
      csvContent += `年化收益率,${(results.annualized_return * 100).toFixed(2)}%\n`;
      csvContent += `夏普比率,${results.sharpe_ratio?.toFixed(2) || 'N/A'}\n`;
      csvContent += `最大回撤,${(Math.abs(results.max_drawdown) * 100).toFixed(2)}%\n`;
      csvContent += `交易次数,${results.num_trades || 0}\n`;
      csvContent += `胜率,${(results.win_rate * 100).toFixed(2)}%\n`;
      csvContent += `盈亏比,${results.profit_factor?.toFixed(2) || 'N/A'}\n`;
      csvContent += `最终价值,$${results.final_value?.toFixed(2) || 'N/A'}\n`;
      csvContent += '\n';

      // 构建交易记录
      if (results.trades && results.trades.length > 0) {
        csvContent += '交易记录\n';
        csvContent += '日期,类型,价格,数量,金额,盈亏\n';
        results.trades.forEach(trade => {
          const amount = trade.type === 'BUY' ? trade.cost : trade.revenue;
          csvContent += `${new Date(trade.date).toLocaleDateString()},${trade.type === 'BUY' ? '买入' : '卖出'},${trade.price?.toFixed(2)},${trade.shares},${amount?.toFixed(2)},${trade.pnl?.toFixed(2) || '-'}\n`;
        });
      }

      // 下载文件
      const blob = new Blob(["\uFEFF" + csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `backtest_report_${new Date().toISOString().split('T')[0]}.csv`;
      link.click();
      message.success('CSV报告已导出');
    } catch (error) {
      message.error('导出失败: ' + error.message);
    }
  };

  // 导出为Excel (使用CSV格式，Excel可直接打开)
  const exportToExcel = () => {
    try {
      // 构建HTML表格格式，Excel可以直接打开
      let htmlContent = `
        <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">
        <head><meta charset="UTF-8"></head>
        <body>
        <table border="1">
          <tr><th colspan="2" style="background:#1890ff;color:white;font-size:16px;">回测结果报告</th></tr>
          <tr><th colspan="2" style="background:#f0f0f0;">生成时间: ${new Date().toLocaleString()}</th></tr>
          <tr><td colspan="2"></td></tr>
          <tr style="background:#e6f7ff;"><th>指标</th><th>数值</th></tr>
          <tr><td>总收益率</td><td style="color:${results.total_return >= 0 ? 'green' : 'red'};">${(results.total_return * 100).toFixed(2)}%</td></tr>
          <tr><td>年化收益率</td><td style="color:${results.annualized_return >= 0 ? 'green' : 'red'};">${(results.annualized_return * 100).toFixed(2)}%</td></tr>
          <tr><td>夏普比率</td><td>${results.sharpe_ratio?.toFixed(2) || 'N/A'}</td></tr>
          <tr><td>最大回撤</td><td style="color:red;">${(Math.abs(results.max_drawdown) * 100).toFixed(2)}%</td></tr>
          <tr><td>交易次数</td><td>${results.num_trades || 0}</td></tr>
          <tr><td>胜率</td><td>${(results.win_rate * 100).toFixed(2)}%</td></tr>
          <tr><td>盈亏比</td><td>${results.profit_factor?.toFixed(2) || 'N/A'}</td></tr>
          <tr><td>最终价值</td><td>$${results.final_value?.toFixed(2) || 'N/A'}</td></tr>
        </table>
      `;

      // 添加交易记录表
      if (results.trades && results.trades.length > 0) {
        htmlContent += `
          <br/>
          <table border="1">
            <tr><th colspan="6" style="background:#1890ff;color:white;">交易记录</th></tr>
            <tr style="background:#e6f7ff;"><th>日期</th><th>类型</th><th>价格</th><th>数量</th><th>金额</th><th>盈亏</th></tr>
        `;
        results.trades.forEach(trade => {
          const amount = trade.type === 'BUY' ? trade.cost : trade.revenue;
          const pnlColor = trade.pnl > 0 ? 'green' : (trade.pnl < 0 ? 'red' : 'black');
          htmlContent += `
            <tr>
              <td>${new Date(trade.date).toLocaleDateString()}</td>
              <td style="color:${trade.type === 'BUY' ? 'green' : 'red'};">${trade.type === 'BUY' ? '买入' : '卖出'}</td>
              <td>$${trade.price?.toFixed(2)}</td>
              <td>${trade.shares}</td>
              <td>$${amount?.toFixed(2)}</td>
              <td style="color:${pnlColor};">${trade.pnl ? '$' + trade.pnl.toFixed(2) : '-'}</td>
            </tr>
          `;
        });
        htmlContent += '</table>';
      }

      htmlContent += '</body></html>';

      // 下载文件
      const blob = new Blob([htmlContent], { type: 'application/vnd.ms-excel;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `backtest_report_${new Date().toISOString().split('T')[0]}.xls`;
      link.click();
      message.success('Excel报告已导出');
    } catch (error) {
      message.error('导出失败: ' + error.message);
    }
  };

  // 导出为PDF
  const exportToPDF = async () => {
    try {
      message.loading({ content: '正在生成PDF报告...', key: 'pdf_export' });

      const response = await getBacktestReport({
        symbol: results.symbol || 'UNKNOWN',
        strategy: results.strategy || 'unknown',
        backtest_result: results,
        parameters: results.parameters
      });

      if (response.success && response.data?.pdf_base64) {
        // Convert Base64 directly to download
        const byteCharacters = atob(response.data.pdf_base64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        const blob = new Blob([byteArray], { type: 'application/pdf' });

        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = response.data.filename || `backtest_report_${new Date().toISOString().split('T')[0]}.pdf`;
        link.click();

        message.success({ content: 'PDF报告已下载', key: 'pdf_export' });
      } else {
        throw new Error(response.error || '生成报告失败');
      }

    } catch (error) {
      console.error('PDF Export Error:', error);
      message.error({ content: '导出PDF失败: ' + (error.userMessage || error.message), key: 'pdf_export' });
    }
  };

  // 导出菜单项
  const exportMenuItems = [
    {
      key: 'pdf',
      label: 'PDF格式 (.pdf)',
      icon: <FilePdfOutlined style={{ color: '#ff4d4f' }} />,
      onClick: exportToPDF,
    },
    {
      key: 'excel',
      label: 'Excel格式 (.xls)',
      icon: <FileExcelOutlined style={{ color: 'var(--accent-success)' }} />,
      onClick: exportToExcel,
    },
    {
      key: 'csv',
      label: 'CSV格式 (.csv)',
      icon: <FileTextOutlined style={{ color: 'var(--accent-primary)' }} />,
      onClick: exportToCSV,
    },
  ];



  const tradesColumns = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      render: (date) => new Date(date).toLocaleDateString()
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      render: (type) => (
        <Tag color={type === 'BUY' ? 'success' : 'error'}>
          {type === 'BUY' ? '买入' : '卖出'}
        </Tag>
      )
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (price) => formatCurrency(price)
    },
    {
      title: '数量',
      dataIndex: 'shares',
      key: 'shares'
    },
    {
      title: '金额',
      dataIndex: 'cost',
      key: 'cost',
      render: (cost, record) => {
        const amount = record.type === 'BUY' ? cost : record.revenue;
        return formatCurrency(amount);
      }
    },
    {
      title: '盈亏',
      dataIndex: 'pnl',
      key: 'pnl',
      render: (pnl) => (
        <span style={{ color: getValueColor(pnl) }}>
          {pnl ? formatCurrency(pnl) : '-'}
        </span>
      )
    }
  ];

  const tabItems = [
    {
      key: 'overview',
      label: '概览',
      children: (
        <>
          {/* 第一行：财务核心指标 */}
          <Row gutter={[16, 16]}>
            <Col span={8}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="总收益率"
                  value={results.total_return * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{
                    color: getValueColor(results.total_return),
                    fontSize: '20px'
                  }}
                  prefix={<DollarOutlined style={{ fontSize: '16px' }} />}
                />
              </Card>
            </Col>

            <Col span={8}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="年化收益率"
                  value={results.annualized_return * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{
                    color: getValueColor(results.annualized_return),
                    fontSize: '20px'
                  }}
                  prefix={<LineChartOutlined style={{ fontSize: '16px' }} />}
                />
              </Card>
            </Col>

            <Col span={8}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="最终价值"
                  value={results.final_value}
                  precision={2}
                  valueStyle={{ color: getValueColor(results.total_return), fontSize: '20px' }}
                  prefix={<DollarOutlined style={{ fontSize: '16px' }} />}
                />
              </Card>
            </Col>
          </Row>

          {/* 第二行：风险控制指标 */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="夏普比率"
                  value={results.sharpe_ratio}
                  precision={2}
                  valueStyle={{ color: getValueColor(results.sharpe_ratio), fontSize: '18px' }}
                  prefix={<BarChartOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>

            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="Sortino比率"
                  value={results.sortino_ratio}
                  precision={2}
                  valueStyle={{ color: getValueColor(results.sortino_ratio), fontSize: '18px' }}
                  prefix={<RiseOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>

            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="最大回撤"
                  value={Math.abs(results.max_drawdown) * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: 'var(--accent-danger)', fontSize: '18px' }}
                  prefix={<FallOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>

            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="VaR (95%)"
                  value={Math.abs(results.var_95 || 0) * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: 'var(--accent-warning)', fontSize: '18px' }}
                  prefix={<ThunderboltOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>
          </Row>

          {/* 第三行：交易统计指标 */}
          <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="交易次数"
                  value={results.num_trades || 0}
                  valueStyle={{ color: 'var(--accent-primary)', fontSize: '18px' }}
                  prefix={<NumberOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>

            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="胜率"
                  value={results.win_rate * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: getValueColor(results.win_rate - 0.5), fontSize: '18px' }}
                />
              </Card>
            </Col>

            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="盈亏比"
                  value={results.profit_factor}
                  precision={2}
                  valueStyle={{ color: getValueColor(results.profit_factor - 1), fontSize: '18px' }}
                />
              </Card>
            </Col>

            <Col span={6}>
              <Card className="metric-card" size="small">
                <Statistic
                  title="平均交易"
                  value={results.avg_trade}
                  precision={2}
                  valueStyle={{ color: getValueColor(results.avg_trade), fontSize: '18px' }}
                  prefix={<TransactionOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>
          </Row>
        </>
      )
    },
    {
      key: 'charts',
      label: '图表分析',
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <PerformanceChart data={results.portfolio} />

          <Row gutter={16}>
            <Col span={12}>
              <Card type="inner" title="回撤分析" size="small">
                <DrawdownChart data={results.portfolio} />
              </Card>
            </Col>
            <Col span={12}>
              <Card type="inner" title="风险雷达" size="small">
                <RiskRadar metrics={results} />
              </Card>
            </Col>
          </Row>
        </div>
      )
    },
    {
      key: 'analysis',
      label: '收益分析',
      children: (
        <Row gutter={16}>
          <Col span={12}>
            <Card type="inner" title="收益分布" size="small">
              <ReturnHistogram data={results.portfolio} />
            </Card>
          </Col>
          <Col span={12}>
            <Card type="inner" title="月度热力图" size="small">
              <MonthlyHeatmap data={results.portfolio} />
            </Card>
          </Col>
        </Row>
      )
    },
    {
      key: 'trades',
      label: '交易记录',
      children: (
        <Table
          columns={tradesColumns}
          dataSource={results.trades || []}
          rowKey={(record, index) => index}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条记录`
          }}
        />
      )
    }
  ];

  return (
    <div className="results-container" style={{ marginTop: '16px' }}>
      <Card
        title={
          <Space>
            <TrophyOutlined />
            <span style={{ fontSize: '16px' }}>回测结果</span>
          </Space>
        }
        extra={
          <Space>
            <Dropdown menu={{ items: exportMenuItems }} placement="bottomRight">
              <Button icon={<DownloadOutlined />} size="small">
                导出报告
              </Button>
            </Dropdown>
            <Button
              icon={<CopyOutlined />}
              onClick={copyResults}
              size="small"
            >
              复制结果
            </Button>
          </Space>
        }
        size="small"
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>
    </div>
  );
};

export default ResultsDisplay;
