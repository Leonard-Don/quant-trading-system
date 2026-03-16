/**
 * 数据导出工具
 * 支持 CSV、Excel、JSON 格式导出
 */

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

    // 格式化指标
    const metrics = [];
    if (backtestResult.metrics) {
        const m = backtestResult.metrics;
        metrics.push(
            { metric: '总收益率', value: `${(m.total_return * 100).toFixed(2)}%` },
            { metric: '年化收益率', value: `${(m.annualized_return * 100).toFixed(2)}%` },
            { metric: '夏普比率', value: m.sharpe_ratio?.toFixed(3) || 'N/A' },
            { metric: '最大回撤', value: `${(m.max_drawdown * 100).toFixed(2)}%` },
            { metric: '胜率', value: `${(m.win_rate * 100).toFixed(2)}%` },
            { metric: '交易次数', value: m.total_trades || 0 },
            { metric: '初始资金', value: `$${m.initial_capital?.toLocaleString() || 'N/A'}` },
            { metric: '最终资金', value: `$${m.final_value?.toLocaleString() || 'N/A'}` }
        );
    }

    // 格式化交易记录
    const trades = backtestResult.trades?.map(trade => ({
        date: trade.date,
        action: trade.action === 'buy' ? '买入' : '卖出',
        price: trade.price?.toFixed(2),
        quantity: trade.quantity,
        value: trade.value?.toFixed(2),
        commission: trade.commission?.toFixed(2)
    })) || [];

    // 格式化每日数据
    const dailyData = backtestResult.portfolio_history?.map(item => ({
        date: item.date,
        portfolio_value: item.total?.toFixed(2),
        price: item.price?.toFixed(2),
        signal: item.signal
    })) || [];

    return { metrics, trades, dailyData };
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

export default {
    exportToCSV,
    exportToJSON,
    exportToExcel,
    exportBacktestReport,
    formatBacktestForExport
};
