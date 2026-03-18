import React, { useMemo, useState } from 'react';
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tabs,
  Button,
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
  TransactionOutlined
} from '@ant-design/icons';
import { getBacktestReport } from '../services/api';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';
import { normalizeBacktestResult } from '../utils/backtest';
import { useSafeMessageApi } from '../utils/messageApi';
import PerformanceChart from './PerformanceChart';
import DrawdownChart from './DrawdownChart';
import MonthlyHeatmap from './MonthlyHeatmap';
import RiskRadar from './RiskRadar';
import ReturnHistogram from './ReturnHistogram';

const ResultsDisplay = ({ results }) => {
  const message = useSafeMessageApi();
  const [activeTab, setActiveTab] = useState('overview');
  const normalizedResults = useMemo(() => normalizeBacktestResult(results), [results]);
  const trades = normalizedResults.trades || [];
  const portfolioHistory = normalizedResults.portfolio_history || normalizedResults.portfolio || [];
  const primaryMetrics = [
    {
      key: 'total_return',
      title: '总收益率',
      value: normalizedResults.total_return * 100,
      suffix: '%',
      precision: 2,
      color: getValueColor(normalizedResults.total_return),
      icon: <DollarOutlined style={{ fontSize: '16px' }} />,
    },
    {
      key: 'annualized_return',
      title: '年化收益率',
      value: normalizedResults.annualized_return * 100,
      suffix: '%',
      precision: 2,
      color: getValueColor(normalizedResults.annualized_return),
      icon: <LineChartOutlined style={{ fontSize: '16px' }} />,
    },
    {
      key: 'max_drawdown',
      title: '最大回撤',
      value: Math.abs(normalizedResults.max_drawdown) * 100,
      suffix: '%',
      precision: 2,
      color: 'var(--accent-danger)',
      icon: <FallOutlined style={{ fontSize: '16px' }} />,
    },
    {
      key: 'sharpe_ratio',
      title: '夏普比率',
      value: normalizedResults.sharpe_ratio,
      precision: 2,
      color: getValueColor(normalizedResults.sharpe_ratio),
      icon: <BarChartOutlined style={{ fontSize: '16px' }} />,
    },
    {
      key: 'final_value',
      title: '最终价值',
      value: normalizedResults.final_value,
      precision: 2,
      color: getValueColor(normalizedResults.total_return),
      icon: <DollarOutlined style={{ fontSize: '16px' }} />,
      formatter: (value) => formatCurrency(Number(value || 0)),
    },
  ];
  const diagnosticMetrics = [
    { label: '交易次数', value: `${normalizedResults.num_trades || 0} 笔` },
    { label: '胜率', value: formatPercentage(normalizedResults.win_rate || 0) },
    { label: '盈亏比', value: normalizedResults.profit_factor?.toFixed(2) || '不适用' },
    { label: '完成交易', value: `${normalizedResults.total_completed_trades || 0} 组` },
    { label: '持仓状态', value: normalizedResults.has_open_position ? '仍有未平仓' : '已全部平仓' },
    { label: '净利润', value: formatCurrency(normalizedResults.net_profit || 0) },
  ];

  const copyResults = () => {
    const text = `
回测结果摘要
====================
总收益率: ${formatPercentage(normalizedResults.total_return)}
年化收益率: ${formatPercentage(normalizedResults.annualized_return)}
夏普比率: ${normalizedResults.sharpe_ratio?.toFixed(2) || '不适用'}
最大回撤: ${formatPercentage(Math.abs(normalizedResults.max_drawdown))}
交易次数: ${normalizedResults.num_trades || 0}
胜率: ${formatPercentage(normalizedResults.win_rate)}
盈亏比: ${normalizedResults.profit_factor?.toFixed(2) || '不适用'}
最佳交易: ${normalizedResults.best_trade?.toFixed(2) || '不适用'}
最差交易: ${normalizedResults.worst_trade?.toFixed(2) || '不适用'}
净利润: ${normalizedResults.net_profit?.toFixed(2) || '不适用'}
最大连续盈利: ${normalizedResults.max_consecutive_wins || 0}
最大连续亏损: ${normalizedResults.max_consecutive_losses || 0}
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
      csvContent += `总收益率,${(normalizedResults.total_return * 100).toFixed(2)}%\n`;
      csvContent += `年化收益率,${(normalizedResults.annualized_return * 100).toFixed(2)}%\n`;
      csvContent += `夏普比率,${normalizedResults.sharpe_ratio?.toFixed(2) || '不适用'}\n`;
      csvContent += `最大回撤,${(Math.abs(normalizedResults.max_drawdown) * 100).toFixed(2)}%\n`;
      csvContent += `交易次数,${normalizedResults.num_trades || 0}\n`;
      csvContent += `胜率,${(normalizedResults.win_rate * 100).toFixed(2)}%\n`;
      csvContent += `盈亏比,${normalizedResults.profit_factor?.toFixed(2) || '不适用'}\n`;
      csvContent += `最终价值,$${normalizedResults.final_value?.toFixed(2) || '不适用'}\n`;
      csvContent += '\n';

      // 构建交易记录
      if (trades.length > 0) {
        csvContent += '交易记录\n';
        csvContent += '日期,类型,价格,数量,金额,盈亏\n';
        trades.forEach((trade) => {
          csvContent += `${new Date(trade.date).toLocaleDateString()},${trade.type === 'BUY' ? '买入' : '卖出'},${trade.price?.toFixed(2)},${trade.quantity},${trade.value?.toFixed(2)},${trade.pnl?.toFixed(2) || '-'}\n`;
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
          <tr><td>总收益率</td><td style="color:${normalizedResults.total_return >= 0 ? 'green' : 'red'};">${(normalizedResults.total_return * 100).toFixed(2)}%</td></tr>
          <tr><td>年化收益率</td><td style="color:${normalizedResults.annualized_return >= 0 ? 'green' : 'red'};">${(normalizedResults.annualized_return * 100).toFixed(2)}%</td></tr>
          <tr><td>夏普比率</td><td>${normalizedResults.sharpe_ratio?.toFixed(2) || '不适用'}</td></tr>
          <tr><td>最大回撤</td><td style="color:red;">${(Math.abs(normalizedResults.max_drawdown) * 100).toFixed(2)}%</td></tr>
          <tr><td>交易次数</td><td>${normalizedResults.num_trades || 0}</td></tr>
          <tr><td>胜率</td><td>${(normalizedResults.win_rate * 100).toFixed(2)}%</td></tr>
          <tr><td>盈亏比</td><td>${normalizedResults.profit_factor?.toFixed(2) || '不适用'}</td></tr>
          <tr><td>最终价值</td><td>$${normalizedResults.final_value?.toFixed(2) || '不适用'}</td></tr>
        </table>
      `;

      // 添加交易记录表
      if (trades.length > 0) {
        htmlContent += `
          <br/>
          <table border="1">
            <tr><th colspan="6" style="background:#1890ff;color:white;">交易记录</th></tr>
            <tr style="background:#e6f7ff;"><th>日期</th><th>类型</th><th>价格</th><th>数量</th><th>金额</th><th>盈亏</th></tr>
        `;
        trades.forEach((trade) => {
          const pnlColor = trade.pnl > 0 ? 'green' : (trade.pnl < 0 ? 'red' : 'black');
          htmlContent += `
            <tr>
              <td>${new Date(trade.date).toLocaleDateString()}</td>
              <td style="color:${trade.type === 'BUY' ? 'green' : 'red'};">${trade.type === 'BUY' ? '买入' : '卖出'}</td>
              <td>$${trade.price?.toFixed(2)}</td>
              <td>${trade.quantity}</td>
              <td>$${trade.value?.toFixed(2)}</td>
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
        symbol: normalizedResults.symbol || 'UNKNOWN',
        strategy: normalizedResults.strategy || 'unknown',
        backtest_result: normalizedResults,
        parameters: normalizedResults.parameters,
        start_date: normalizedResults.start_date,
        end_date: normalizedResults.end_date,
        initial_capital: normalizedResults.initial_capital,
        commission: normalizedResults.commission,
        slippage: normalizedResults.slippage,
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
      dataIndex: 'quantity',
      key: 'quantity'
    },
    {
      title: '金额',
      dataIndex: 'value',
      key: 'value',
      render: (value) => formatCurrency(value)
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
        <div className="workspace-analysis-stack">
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={16}>
              <div className="workspace-section workspace-section--accent">
                <div className="workspace-section__header">
                  <div>
                    <div className="workspace-section__title">首屏结论</div>
                    <div className="workspace-section__description">先看收益、风险和最终价值，再决定是否继续深入图表与交易诊断。</div>
                  </div>
                </div>
                <Row gutter={[16, 16]}>
                  {primaryMetrics.map((metric) => (
                    <Col xs={24} sm={12} lg={8} key={metric.key}>
                      <Card className="metric-card workspace-kpi-card" size="small">
                        <Statistic
                          title={metric.title}
                          value={metric.value}
                          precision={metric.precision}
                          suffix={metric.suffix}
                          formatter={metric.formatter}
                          valueStyle={{ color: metric.color, fontSize: '20px' }}
                          prefix={metric.icon}
                        />
                      </Card>
                    </Col>
                  ))}
                </Row>
              </div>
            </Col>
            <Col xs={24} xl={8}>
              <div className="workspace-section">
                <div className="workspace-section__header">
                  <div>
                    <div className="workspace-section__title">次级诊断</div>
                    <div className="workspace-section__description">补充交易效率、持仓状态和完成交易数，帮助快速判断结果质量。</div>
                  </div>
                </div>
                <div className="summary-strip summary-strip--stack">
                  {diagnosticMetrics.map((item) => (
                    <div key={item.label} className="summary-strip__item">
                      <span className="summary-strip__label">{item.label}</span>
                      <span className="summary-strip__value">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} md={8}>
              <Card className="metric-card workspace-kpi-card" size="small">
                <Statistic
                  title="索提诺比率"
                  value={normalizedResults.sortino_ratio}
                  precision={2}
                  valueStyle={{ color: getValueColor(normalizedResults.sortino_ratio), fontSize: '18px' }}
                  prefix={<RiseOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card className="metric-card workspace-kpi-card" size="small">
                <Statistic
                  title="在险价值 (95%)"
                  value={Math.abs(normalizedResults.var_95 || 0) * 100}
                  precision={2}
                  suffix="%"
                  valueStyle={{ color: 'var(--accent-warning)', fontSize: '18px' }}
                  prefix={<ThunderboltOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card className="metric-card workspace-kpi-card" size="small">
                <Statistic
                  title="平均单笔收益"
                  value={normalizedResults.avg_trade}
                  precision={2}
                  valueStyle={{ color: getValueColor(normalizedResults.avg_trade), fontSize: '18px' }}
                  prefix={<TransactionOutlined style={{ fontSize: '14px' }} />}
                />
              </Card>
            </Col>
          </Row>
        </div>
      )
    },
    {
      key: 'charts',
      label: '图表分析',
      children: (
        <div className="workspace-analysis-stack">
          <div className="workspace-section">
            <div className="workspace-section__header">
              <div>
                <div className="workspace-section__title">组合净值与主曲线</div>
                <div className="workspace-section__description">把组合总资产变化放在最前面，先确认回测曲线是否符合预期。</div>
              </div>
            </div>
            <PerformanceChart data={portfolioHistory} />
          </div>

          <Row gutter={16}>
            <Col xs={24} xl={12}>
              <div className="workspace-section workspace-chart-card">
                <div className="workspace-section__header">
                  <div>
                    <div className="workspace-section__title">回撤分析</div>
                    <div className="workspace-section__description">把最大回撤、当前水位和恢复时间放进同一张回撤曲线里。</div>
                  </div>
                </div>
                <DrawdownChart data={portfolioHistory} />
              </div>
            </Col>
            <Col xs={24} xl={12}>
              <div className="workspace-section workspace-chart-card">
                <div className="workspace-section__header">
                  <div>
                    <div className="workspace-section__title">风险雷达</div>
                    <div className="workspace-section__description">把收益、胜率、回撤和稳定性压缩成一张更易扫读的画像。</div>
                  </div>
                </div>
                <RiskRadar metrics={results} />
              </div>
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
          <Col xs={24} xl={12}>
            <div className="workspace-section workspace-chart-card">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">收益分布</div>
                  <div className="workspace-section__description">观察收益分布的偏态、密度和尾部风险，不只盯着均值。</div>
                </div>
              </div>
              <ReturnHistogram data={portfolioHistory} />
            </div>
          </Col>
          <Col xs={24} xl={12}>
            <div className="workspace-section workspace-chart-card">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">月度热力图</div>
                  <div className="workspace-section__description">按月汇总组合表现，快速识别强势月份、承压月份和年度节奏。</div>
                </div>
              </div>
              <MonthlyHeatmap data={portfolioHistory} />
            </div>
          </Col>
        </Row>
      )
    },
    {
      key: 'trades',
      label: '交易记录',
      children: (
        <Card className="workspace-chart-card" size="small" title="成交明细">
          <Table
            columns={tradesColumns}
            dataSource={trades}
            rowKey={(record) => `${record.date}-${record.type}-${record.quantity}-${record.price}`}
            locale={{ emptyText: '暂无成交记录' }}
            pagination={{
              pageSize: 10,
              showSizeChanger: false,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条记录`
            }}
          />
        </Card>
      )
    }
  ];

  return (
    <div className="results-container backtest-results" style={{ marginTop: '16px' }}>
      <Card
        className="workspace-panel workspace-panel--result"
        title={
          <div className="workspace-title">
            <div className="workspace-title__icon workspace-title__icon--accent">
              <TrophyOutlined />
            </div>
            <div>
              <div className="workspace-title__text">回测结果</div>
              <div className="workspace-title__hint">结果已进入分析工作区，先看结论条，再深入图表、收益分析和成交明细。</div>
            </div>
          </div>
        }
        extra={
          <Space wrap className="workspace-toolbar">
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
        <div className="summary-strip summary-strip--compact">
          <div className="summary-strip__item">
            <span className="summary-strip__label">策略</span>
            <span className="summary-strip__value">{normalizedResults.strategy || '当前回测'}</span>
          </div>
          <div className="summary-strip__item">
            <span className="summary-strip__label">标的</span>
            <span className="summary-strip__value">{normalizedResults.symbol || '未提供'}</span>
          </div>
          <div className="summary-strip__item">
            <span className="summary-strip__label">状态</span>
            <span className="summary-strip__value">{Number(normalizedResults.total_return || 0) >= 0 ? '收益为正' : '收益承压'}</span>
          </div>
        </div>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>
    </div>
  );
};

export default ResultsDisplay;
