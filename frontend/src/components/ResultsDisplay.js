import React, { useEffect, useMemo, useState } from 'react';
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
  Dropdown,
  Alert,
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
  TransactionOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined
} from '@ant-design/icons';
import { downloadBacktestReport, runMarketRegimeBacktest } from '../services/api';
import { getStrategyDetails, getStrategyName } from '../constants/strategies';
import { formatCurrency, formatPercentage, getValueColor } from '../utils/formatting';
import { normalizeBacktestResult } from '../utils/backtest';
import { buildBacktestActionPosture, buildSignalExplanation } from '../utils/backtestResearch';
import { buildMarketRegimeInsight } from '../utils/advancedBacktestLab';
import { useSafeMessageApi } from '../utils/messageApi';
import PerformanceChart from './PerformanceChart';
import DrawdownChart from './DrawdownChart';
import MonthlyHeatmap from './MonthlyHeatmap';
import RiskRadar from './RiskRadar';
import ReturnHistogram from './ReturnHistogram';

const ResultsDisplay = ({ results, isRefreshing = false, onOpenHistoryRecord, onContinueAdvancedExperiment }) => {
  const message = useSafeMessageApi();
  const [activeTab, setActiveTab] = useState('overview');
  const [marketRegimeLoading, setMarketRegimeLoading] = useState(false);
  const [marketRegimeResult, setMarketRegimeResult] = useState(null);
  const normalizedResults = useMemo(() => normalizeBacktestResult(results), [results]);
  const strategyDetails = useMemo(
    () => getStrategyDetails(normalizedResults.strategy),
    [normalizedResults.strategy]
  );
  const signalExplanation = useMemo(
    () => buildSignalExplanation(normalizedResults),
    [normalizedResults]
  );
  const actionPosture = useMemo(
    () => buildBacktestActionPosture({ result: normalizedResults }),
    [normalizedResults]
  );
  const executionDiagnostics = useMemo(
    () => normalizedResults.execution_diagnostics || {},
    [normalizedResults.execution_diagnostics]
  );
  const executionDiagnosticItems = useMemo(() => {
    if (!executionDiagnostics || !Object.keys(executionDiagnostics).length) {
      return [];
    }

    const signalModeLabel = executionDiagnostics.resolved_signal_mode === 'target'
      ? '目标仓位'
      : executionDiagnostics.resolved_signal_mode === 'event'
        ? '事件信号'
        : '自动识别';

    return [
      { label: '执行语义', value: signalModeLabel },
      { label: '小数份额', value: executionDiagnostics.allow_fractional_shares ? '已开启' : '关闭' },
      { label: '仓位管理', value: executionDiagnostics.position_sizer || '默认仓位器' },
      { label: '风控组件', value: executionDiagnostics.risk_manager || '未启用' },
      {
        label: '止损 / 止盈',
        value: executionDiagnostics.stop_loss_pct || executionDiagnostics.take_profit_pct
          ? `${executionDiagnostics.stop_loss_pct ? formatPercentage(executionDiagnostics.stop_loss_pct) : '未设'} / ${executionDiagnostics.take_profit_pct ? formatPercentage(executionDiagnostics.take_profit_pct) : '未设'}`
          : '未设',
      },
    ];
  }, [executionDiagnostics]);
  const marketRegimeInsight = useMemo(
    () => buildMarketRegimeInsight(marketRegimeResult),
    [marketRegimeResult]
  );
  const trades = normalizedResults.trades || [];
  const portfolioHistory = normalizedResults.portfolio_history || normalizedResults.portfolio || [];

  useEffect(() => {
    setMarketRegimeResult(null);
    setMarketRegimeLoading(false);
  }, [
    normalizedResults.symbol,
    normalizedResults.strategy,
    normalizedResults.start_date,
    normalizedResults.end_date,
  ]);
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
    { label: '亏损率', value: formatPercentage(normalizedResults.loss_rate || 0) },
    { label: '盈亏比', value: normalizedResults.profit_factor?.toFixed(2) || '不适用' },
    { label: '完成交易', value: `${normalizedResults.total_completed_trades || 0} 组` },
    { label: '持仓状态', value: normalizedResults.has_open_position ? '仍有未平仓' : '已全部平仓' },
    { label: '净利润', value: formatCurrency(normalizedResults.net_profit || 0) },
  ];
  const extendedMetrics = [
    {
      key: 'avg_win',
      title: '平均盈利',
      value: normalizedResults.avg_win || 0,
      formatter: (value) => formatCurrency(Number(value || 0)),
      color: 'var(--accent-success)',
      icon: <RiseOutlined style={{ fontSize: '14px' }} />,
    },
    {
      key: 'avg_loss',
      title: '平均亏损',
      value: normalizedResults.avg_loss || 0,
      formatter: (value) => formatCurrency(Number(value || 0)),
      color: 'var(--accent-danger)',
      icon: <FallOutlined style={{ fontSize: '14px' }} />,
    },
    {
      key: 'avg_holding_days',
      title: '平均持仓天数',
      value: normalizedResults.avg_holding_days || 0,
      precision: 1,
      suffix: '天',
      color: 'var(--accent-primary)',
      icon: <ClockCircleOutlined style={{ fontSize: '14px' }} />,
    },
    {
      key: 'total_profit',
      title: '累计盈利',
      value: normalizedResults.total_profit || 0,
      formatter: (value) => formatCurrency(Number(value || 0)),
      color: 'var(--accent-success)',
      icon: <ThunderboltOutlined style={{ fontSize: '14px' }} />,
    },
  ];
  const resultSummaryItems = [
    { label: '策略', value: getStrategyName(normalizedResults.strategy) },
    { label: '标的', value: normalizedResults.symbol || '未提供' },
    { label: '总收益', value: formatPercentage(normalizedResults.total_return || 0) },
    { label: '夏普', value: normalizedResults.sharpe_ratio?.toFixed(2) || '不适用' },
    { label: '最大回撤', value: formatPercentage(Math.abs(normalizedResults.max_drawdown || 0)) },
  ];
  const secondaryMetrics = [
    {
      key: 'sortino_ratio',
      title: '索提诺比率',
      value: normalizedResults.sortino_ratio,
      precision: 2,
      color: getValueColor(normalizedResults.sortino_ratio),
      icon: <RiseOutlined style={{ fontSize: '14px' }} />,
    },
    {
      key: 'var_95',
      title: '在险价值 (95%)',
      value: Math.abs(normalizedResults.var_95 || 0) * 100,
      precision: 2,
      suffix: '%',
      color: 'var(--accent-warning)',
      icon: <ThunderboltOutlined style={{ fontSize: '14px' }} />,
    },
    {
      key: 'avg_trade',
      title: '平均单笔收益',
      value: normalizedResults.avg_trade,
      precision: 2,
      color: getValueColor(normalizedResults.avg_trade),
      icon: <TransactionOutlined style={{ fontSize: '14px' }} />,
    },
    ...extendedMetrics,
  ];
  const signalLeadItems = signalExplanation.slice(0, 2);

  const runMarketRegimeAnalysis = async () => {
    if (!normalizedResults.symbol || !normalizedResults.strategy) {
      message.warning('当前结果缺少标的或策略信息，暂时无法分析市场状态。');
      return;
    }

    setMarketRegimeLoading(true);
    try {
      const response = await runMarketRegimeBacktest({
        symbol: normalizedResults.symbol,
        strategy: normalizedResults.strategy,
        parameters: normalizedResults.parameters || {},
        start_date: normalizedResults.start_date,
        end_date: normalizedResults.end_date,
        initial_capital: normalizedResults.initial_capital,
        commission: normalizedResults.commission,
        slippage: normalizedResults.slippage,
      });

      if (!response?.success) {
        throw new Error(response?.error || '市场状态分析失败');
      }

      setMarketRegimeResult(response.data);
      message.success('市场状态分析已完成');
    } catch (error) {
      message.error(error.userMessage || error.message || '市场状态分析失败');
    } finally {
      setMarketRegimeLoading(false);
    }
  };

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

      const response = await downloadBacktestReport({
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

      if (response?.blob) {
        const link = document.createElement('a');
        const objectUrl = URL.createObjectURL(response.blob);
        link.href = objectUrl;
        link.download = response.filename || `backtest_report_${new Date().toISOString().split('T')[0]}.pdf`;
        link.click();
        URL.revokeObjectURL(objectUrl);

        message.success({ content: 'PDF报告已下载', key: 'pdf_export' });
      } else {
        throw new Error('生成报告失败');
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
              <div className="workspace-section workspace-section--accent results-overview-hero">
                <div className="workspace-section__header">
                  <div>
                    <div className="workspace-section__title">结果总览</div>
                    <div className="workspace-section__description">先抓住收益、风险和最终价值，再决定要不要继续钻图表、执行细节和市场状态。</div>
                  </div>
                </div>
                <div className="results-primary-kpi-grid">
                  {primaryMetrics.map((metric) => (
                    <div key={metric.key}>
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
                    </div>
                  ))}
                </div>
              </div>
            </Col>
            <Col xs={24} xl={8}>
              <div className="workspace-section results-diagnostic-panel">
                <div className="workspace-section__header">
                  <div>
                    <div className="workspace-section__title">运行诊断</div>
                    <div className="workspace-section__description">用更短的检查项确认这次结果是否值得继续投入时间。</div>
                  </div>
                </div>
                <div className="results-diagnostic-grid">
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

          <div className="workspace-section">
            <div className="workspace-section__header">
              <div>
                <div className="workspace-section__title">补充指标</div>
                <div className="workspace-section__description">把风险、持仓效率和盈亏结构压成一组紧凑卡片，不再拆成多段往下堆。</div>
              </div>
            </div>
            <div className="results-secondary-kpi-grid">
              {secondaryMetrics.map((metric) => (
                <Card key={metric.key} className="metric-card workspace-kpi-card" size="small">
                  <Statistic
                    title={metric.title}
                    value={metric.value}
                    precision={metric.precision}
                    suffix={metric.suffix}
                    formatter={metric.formatter}
                    valueStyle={{ color: metric.color, fontSize: '18px' }}
                    prefix={metric.icon}
                  />
                </Card>
              ))}
            </div>
          </div>

          {signalExplanation.length ? (
            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">信号解释</div>
                  <div className="workspace-section__description">把结果翻译成短句结论，帮助快速理解策略为什么有效、哪里还不稳。</div>
                </div>
              </div>
              <div className="results-note-grid">
                {signalExplanation.map((item, index) => (
                  <div key={`${index + 1}-${item.slice(0, 12)}`} className="summary-strip__item">
                    <span className="summary-strip__label">结论 {index + 1}</span>
                    <span className="summary-strip__value" style={{ whiteSpace: 'normal' }}>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {executionDiagnosticItems.length ? (
            <div className="workspace-section">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">执行诊断</div>
                  <div className="workspace-section__description">把这次回测采用的执行语义、仓位器和风控方式显式写出来，避免只看结果却不清楚执行口径。</div>
                </div>
              </div>
              <Alert
                type="info"
                showIcon
                message={`本次回测按 ${executionDiagnosticItems[0]?.value || '默认执行'} 运行`}
                description={
                  executionDiagnostics.configured_signal_mode && executionDiagnostics.configured_signal_mode !== executionDiagnostics.resolved_signal_mode
                    ? `原始配置为 ${executionDiagnostics.configured_signal_mode}，引擎最终按 ${executionDiagnostics.resolved_signal_mode} 解释信号。`
                    : '当前结果已经附带执行层诊断信息，便于区分事件信号回测和目标仓位回测。'
                }
              />
              <div className="results-note-grid" style={{ marginTop: 12 }}>
                {executionDiagnosticItems.map((item) => (
                  <div key={item.label} className="summary-strip__item">
                    <span className="summary-strip__label">{item.label}</span>
                    <span className="summary-strip__value">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="workspace-section">
            <div className="workspace-section__header">
              <div>
                <div className="workspace-section__title">市场状态结论</div>
                <div className="workspace-section__description">把这次回测放进上涨、下跌和震荡环境里看，判断策略更适合什么行情。</div>
              </div>
              <Button
                size="small"
                icon={<BarChartOutlined />}
                loading={marketRegimeLoading}
                onClick={runMarketRegimeAnalysis}
              >
                分析市场状态
              </Button>
            </div>
            {marketRegimeResult ? (
              <div className="workspace-analysis-stack">
                {marketRegimeInsight ? (
                  <Alert
                    type={marketRegimeInsight.type}
                    showIcon
                    message={marketRegimeInsight.title}
                    description={marketRegimeInsight.description}
                  />
                ) : null}
                <div className="summary-strip summary-strip--stack">
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">最适合的市场状态</span>
                    <span className="summary-strip__value">
                      {marketRegimeResult.summary?.strongest_regime?.regime || '未识别'}
                      {' · '}
                      {formatPercentage(marketRegimeResult.summary?.strongest_regime?.strategy_total_return || 0)}
                    </span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">最承压的市场状态</span>
                    <span className="summary-strip__value">
                      {marketRegimeResult.summary?.weakest_regime?.regime || '未识别'}
                      {' · '}
                      {formatPercentage(marketRegimeResult.summary?.weakest_regime?.strategy_total_return || 0)}
                    </span>
                  </div>
                  <div className="summary-strip__item">
                    <span className="summary-strip__label">正收益状态占比</span>
                    <span className="summary-strip__value">
                      {formatPercentage(
                        Number(marketRegimeResult.summary?.positive_regimes || 0)
                        / Math.max(Number(marketRegimeResult.summary?.regime_count || 0), 1)
                      )}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <Alert
                type="info"
                showIcon
                message="还没有市场状态结论"
                description="点击“分析市场状态”后，结果页会直接告诉你这个策略更适合上涨、下跌还是震荡行情。"
              />
            )}
          </div>
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
          <Col xs={24}>
            <div className="workspace-section workspace-chart-card">
              <div className="workspace-section__header">
                <div>
                  <div className="workspace-section__title">市场状态分层结果</div>
                  <div className="workspace-section__description">把策略收益和市场收益放在同一张表里，快速确认它到底擅长什么环境。</div>
                </div>
              </div>
              {marketRegimeResult ? (
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(record) => record.regime}
                  dataSource={marketRegimeResult.regimes || []}
                  columns={[
                    { title: '市场状态', dataIndex: 'regime', key: 'regime' },
                    { title: '区间天数', dataIndex: 'days', key: 'days' },
                    { title: '策略收益', dataIndex: 'strategy_total_return', key: 'strategy_total_return', render: (value) => formatPercentage(value || 0) },
                    { title: '市场收益', dataIndex: 'market_total_return', key: 'market_total_return', render: (value) => formatPercentage(value || 0) },
                    { title: '胜率', dataIndex: 'win_rate', key: 'win_rate', render: (value) => formatPercentage(value || 0) },
                    { title: '最大回撤', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (value) => formatPercentage(value || 0) },
                  ]}
                />
              ) : (
                <Alert
                  type="info"
                  showIcon
                  message="尚未生成市场状态分层结果"
                  description="先在概览页点击“分析市场状态”，这里就会补出完整分层明细。"
                />
              )}
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
    <div className="results-container backtest-results">
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
            {normalizedResults.history_record_id ? (
              <Button
                icon={<FileTextOutlined />}
                onClick={() => onOpenHistoryRecord?.(normalizedResults.history_record_id)}
                size="small"
              >
                查看历史记录
              </Button>
            ) : null}
            <Button
              icon={<DeploymentUnitOutlined />}
              onClick={() => onContinueAdvancedExperiment?.()}
              size="small"
            >
              继续做高级实验
            </Button>
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
        <div className="summary-strip summary-strip--compact results-summary-strip">
          {resultSummaryItems.map((item) => (
            <div key={item.label} className="summary-strip__item">
              <span className="summary-strip__label">{item.label}</span>
              <span className="summary-strip__value">{item.value}</span>
            </div>
          ))}
        </div>
        {isRefreshing ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message="正在基于新配置刷新回测结果"
            description="当前先保留上一版分析面板，等新结果返回后会自动替换。"
          />
        ) : null}
        <div className="results-lead-grid">
          <div className="workspace-section results-lead-card results-lead-card--profile">
            <div className="results-lead-card__eyebrow">策略画像</div>
            <div className="results-lead-card__title">{`${getStrategyName(normalizedResults.strategy)} · ${strategyDetails.style}`}</div>
            <div className="results-lead-card__copy">{strategyDetails.summary}</div>
            <div className="results-lead-card__meta">{strategyDetails.marketFit}</div>
          </div>
          <div className={`workspace-section results-lead-card results-lead-card--${actionPosture?.type || 'info'}`}>
            <div className="results-lead-card__eyebrow">当前建议</div>
            <div className="results-lead-card__title">{actionPosture?.title || '继续观察结果'}</div>
            <div className="results-lead-card__copy">{actionPosture?.actionHint || '先看概览指标，再决定是否继续分析图表和交易记录。'}</div>
            <div className="results-lead-card__meta">{actionPosture?.reason || signalLeadItems[0] || '当前结果已经进入结果工作区，可以继续做对照和稳健性验证。'}</div>
          </div>
        </div>
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>
    </div>
  );
};

export default ResultsDisplay;
