/**
 * 数据导出工具
 * 支持 CSV、Excel、JSON 格式导出
 */

import { normalizeBacktestResult } from './backtest';

/**
 * 将数据导出为 CSV 格式
 * @param {Array} data - 数据数组
 * @param {string} filename - 文件名
 * @param {Array} columns - 列配置 [{key, title}]
 */
export const exportToCSV = (data, filename, columns = null) => {
    if (!data || data.length === 0) {
        console.warn('No data to export');
        return;
    }

    // 如果没有指定列，使用数据的所有键
    const cols = columns || Object.keys(data[0]).map(key => ({ key, title: key }));

    // 构建 CSV 内容
    const headers = cols.map(col => `"${col.title}"`).join(',');
    const rows = data.map(item =>
        cols.map(col => {
            let value = item[col.key];
            // 处理特殊字符
            if (value === null || value === undefined) {
                value = '';
            } else if (typeof value === 'object') {
                value = JSON.stringify(value);
            }
            // 转义引号
            value = String(value).replace(/"/g, '""');
            return `"${value}"`;
        }).join(',')
    ).join('\n');

    const csvContent = '\uFEFF' + headers + '\n' + rows; // 添加 BOM 支持中文
    downloadFile(csvContent, `${filename}.csv`, 'text/csv;charset=utf-8');
};

/**
 * 将数据导出为 JSON 格式
 * @param {any} data - 数据
 * @param {string} filename - 文件名
 */
export const exportToJSON = (data, filename) => {
    const jsonContent = JSON.stringify(data, null, 2);
    downloadFile(jsonContent, `${filename}.json`, 'application/json');
};

/**
 * 将数据导出为 Excel 格式 (使用简单的 HTML 表格方式)
 * @param {Array} data - 数据数组
 * @param {string} filename - 文件名
 * @param {Array} columns - 列配置
 * @param {string} sheetName - 工作表名称
 */
export const exportToExcel = (data, filename, columns = null, sheetName = 'Sheet1') => {
    if (!data || data.length === 0) {
        console.warn('No data to export');
        return;
    }

    const cols = columns || Object.keys(data[0]).map(key => ({ key, title: key }));

    // 构建 HTML 表格
    let html = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel">
    <head>
      <meta charset="UTF-8">
      <!--[if gte mso 9]>
      <xml>
        <x:ExcelWorkbook>
          <x:ExcelWorksheets>
            <x:ExcelWorksheet>
              <x:Name>${sheetName}</x:Name>
              <x:WorksheetOptions><x:Panes></x:Panes></x:WorksheetOptions>
            </x:ExcelWorksheet>
          </x:ExcelWorksheets>
        </x:ExcelWorkbook>
      </xml>
      <![endif]-->
      <style>
        table { border-collapse: collapse; }
        th, td { border: 1px solid #000; padding: 8px; }
        th { background-color: #4472c4; color: white; font-weight: bold; }
        tr:nth-child(even) { background-color: #f2f2f2; }
      </style>
    </head>
    <body>
      <table>
        <thead>
          <tr>
            ${cols.map(col => `<th>${escapeHtml(col.title)}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${data.map(item => `
            <tr>
              ${cols.map(col => {
        let value = item[col.key];
        if (value === null || value === undefined) value = '';
        if (typeof value === 'object') value = JSON.stringify(value);
        return `<td>${escapeHtml(String(value))}</td>`;
    }).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </body>
    </html>
  `;

    downloadFile(html, `${filename}.xls`, 'application/vnd.ms-excel');
};

/**
 * 下载文件
 */
const downloadFile = (content, filename, mimeType) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
};

/**
 * 转义 HTML 特殊字符
 */
const escapeHtml = (text) => {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

/**
 * 格式化回测结果用于导出
 * @param {Object} backtestResult - 回测结果对象
 */
export const formatBacktestForExport = (backtestResult) => {
    if (!backtestResult) return { metrics: [], trades: [], dailyData: [] };

    const normalized = normalizeBacktestResult(backtestResult);
    const summary = normalized.metrics || normalized.performance_metrics || normalized;
    const tradeRecords = normalized.trades || [];
    const portfolioHistory = normalized.portfolio_history || normalized.portfolio || [];

    // 格式化指标
    const metrics = [
        { metric: '总收益率', value: `${((summary.total_return || 0) * 100).toFixed(2)}%` },
        { metric: '年化收益率', value: `${((summary.annualized_return || 0) * 100).toFixed(2)}%` },
        { metric: '夏普比率', value: summary.sharpe_ratio?.toFixed(3) || 'N/A' },
        { metric: '最大回撤', value: `${((summary.max_drawdown || 0) * 100).toFixed(2)}%` },
        { metric: '胜率', value: `${((summary.win_rate || 0) * 100).toFixed(2)}%` },
        { metric: '交易次数', value: summary.num_trades ?? summary.total_trades ?? 0 },
        { metric: '初始资金', value: `$${summary.initial_capital?.toLocaleString() || 'N/A'}` },
        { metric: '最终资金', value: `$${summary.final_value?.toLocaleString() || 'N/A'}` }
    ];

    // 格式化交易记录
    const trades = tradeRecords.map(trade => {
        return {
            date: trade.date,
            action: trade.type === 'BUY' ? '买入' : '卖出',
            price: trade.price?.toFixed?.(2) || trade.price,
            quantity: trade.quantity ?? trade.shares ?? 0,
            value: trade.value?.toFixed?.(2) || trade.value,
            commission: trade.commission?.toFixed?.(2) || trade.commission
        };
    });

    // 格式化每日数据
    const dailyData = portfolioHistory.map(item => ({
        date: item.date,
        portfolio_value: item.total?.toFixed?.(2) || item.total,
        price: item.price?.toFixed?.(2) || item.price,
        signal: item.signal
    }));

    return { metrics, trades, dailyData };
};

export const formatBatchExperimentForExport = (batchResult) => {
    if (!batchResult) return { summary: [], rankedResults: [], allResults: [] };

    const summary = [
        { metric: '总任务数', value: batchResult.summary?.total_tasks ?? 0 },
        { metric: '成功任务数', value: batchResult.summary?.successful ?? 0 },
        { metric: '平均收益率', value: `${((batchResult.summary?.average_return || 0) * 100).toFixed(2)}%` },
        { metric: '平均夏普比率', value: Number(batchResult.summary?.average_sharpe || 0).toFixed(2) },
        { metric: '排名指标', value: batchResult.summary?.ranking_metric || '-' },
    ];

    const mapResult = (item) => ({
        task_id: item.task_id,
        strategy: item.strategy,
        symbol: item.symbol,
        total_return: `${((item.metrics?.total_return || item.total_return || 0) * 100).toFixed(2)}%`,
        sharpe_ratio: Number(item.metrics?.sharpe_ratio || item.sharpe_ratio || 0).toFixed(2),
        max_drawdown: `${((item.metrics?.max_drawdown || item.max_drawdown || 0) * 100).toFixed(2)}%`,
        final_value: Number(item.metrics?.final_value || item.final_value || 0).toFixed(2),
        success: item.success === false ? '失败' : '成功',
        error: item.error || '',
    });

    return {
        summary,
        rankedResults: (batchResult.ranked_results || []).map(mapResult),
        allResults: (batchResult.results || []).map(mapResult),
    };
};

export const formatWalkForwardForExport = (walkResult) => {
    if (!walkResult) return { summary: [], windows: [] };

    const summary = [
        { metric: '滚动窗口数', value: walkResult.n_windows ?? 0 },
        { metric: '平均收益率', value: `${((walkResult.aggregate_metrics?.average_return || 0) * 100).toFixed(2)}%` },
        { metric: '收益波动', value: `${((walkResult.aggregate_metrics?.return_std || 0) * 100).toFixed(2)}%` },
        { metric: '平均夏普比率', value: Number(walkResult.aggregate_metrics?.average_sharpe || 0).toFixed(2) },
        { metric: '正收益窗口', value: walkResult.aggregate_metrics?.positive_windows ?? 0 },
        { metric: '负收益窗口', value: walkResult.aggregate_metrics?.negative_windows ?? 0 },
        { metric: '优化指标', value: walkResult.aggregate_metrics?.optimization_metric || walkResult.optimization_metric || 'sharpe_ratio' },
        { metric: 'Monte Carlo P50', value: `${((walkResult.monte_carlo?.mean_return_p50 || 0) * 100).toFixed(2)}%` },
        { metric: '过拟合风险', value: walkResult.overfitting_diagnostics?.level || 'unknown' },
    ];

    const windows = (walkResult.window_results || []).map((item) => ({
        window: `窗口 ${Number(item.window_id || 0) + 1}`,
        test_range: `${item.test_start} ~ ${item.test_end}`,
        total_return: `${(((item.metrics?.total_return ?? item.total_return) || 0) * 100).toFixed(2)}%`,
        sharpe_ratio: Number(item.metrics?.sharpe_ratio || item.sharpe_ratio || 0).toFixed(2),
        max_drawdown: `${(((item.metrics?.max_drawdown ?? item.max_drawdown) || 0) * 100).toFixed(2)}%`,
        selected_parameters: JSON.stringify(item.selected_parameters || {}),
    }));

    return { summary, windows };
};

/**
 * 导出回测报告
 * @param {Object} backtestResult - 回测结果
 * @param {string} symbol - 股票代码
 * @param {string} strategy - 策略名称
 * @param {string} format - 导出格式 ('csv' | 'excel' | 'json')
 */
export const exportBacktestReport = (backtestResult, symbol, strategy, format = 'csv') => {
    const { metrics, trades, dailyData } = formatBacktestForExport(backtestResult);
    const filename = `backtest_${symbol}_${strategy}_${new Date().toISOString().split('T')[0]}`;

    switch (format) {
        case 'json':
            exportToJSON({ symbol, strategy, metrics, trades, dailyData }, filename);
            break;
        case 'excel':
            // 导出指标
            exportToExcel(metrics, `${filename}_metrics`, [
                { key: 'metric', title: '指标' },
                { key: 'value', title: '值' }
            ], '回测指标');
            break;
        case 'csv':
        default:
            // 导出指标
            exportToCSV(metrics, `${filename}_metrics`, [
                { key: 'metric', title: '指标' },
                { key: 'value', title: '值' }
            ]);
            break;
    }
};

const exportUtils = {
    exportToCSV,
    exportToJSON,
    exportToExcel,
    exportBacktestReport,
    formatBacktestForExport,
    formatBatchExperimentForExport,
    formatWalkForwardForExport
};

export default exportUtils;
