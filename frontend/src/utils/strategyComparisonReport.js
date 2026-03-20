import { getStrategyParameterLabel } from '../constants/strategies';

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const formatPercent = (value) => `${(Number(value || 0) * 100).toFixed(2)}%`;

const formatParameterSummary = (parameters = {}) => {
  const entries = Object.entries(parameters || {});
  if (entries.length === 0) {
    return '默认参数';
  }

  return entries
    .map(([key, value]) => `${getStrategyParameterLabel(key, key)}：${value}`)
    .join('，');
};

export const buildStrategyComparisonReportHtml = ({
  symbol,
  startDate,
  endDate,
  generatedAt,
  initialCapital,
  commission,
  slippage,
  rankedData = [],
  dataSource = [],
}) => {
  const generatedTime = generatedAt || new Date().toLocaleString();
  const bestStrategy = rankedData[0];

  const rows = dataSource.map((item) => `
    <tr>
      <td>${escapeHtml(item.strategyName)}</td>
      <td>${formatPercent(item.total_return)}</td>
      <td>${formatPercent(item.annualized_return)}</td>
      <td>${formatPercent(item.max_drawdown)}</td>
      <td>${Number(item.sharpe_ratio || 0).toFixed(2)}</td>
      <td>${Number(item.num_trades || 0)}</td>
      <td>${escapeHtml(formatParameterSummary(item.parameters))}</td>
    </tr>
  `).join('');

  const rankCards = rankedData.slice(0, 3).map((item, index) => `
    <div class="rank-card">
      <div class="rank-card__badge">#${index + 1}</div>
      <div class="rank-card__name">${escapeHtml(item.strategyName)}</div>
      <div class="rank-card__score">综合评分 ${Number(item.scores?.overall_score || 0)}</div>
      <div class="rank-card__meta">
        收益 ${formatPercent(item.total_return)} / 夏普 ${Number(item.sharpe_ratio || 0).toFixed(2)}
      </div>
    </div>
  `).join('');

  return `<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>策略对比报告</title>
    <style>
      :root {
        color-scheme: light;
        --text-main: #0f172a;
        --text-muted: #475569;
        --line: #dbe4f0;
        --panel: #f8fafc;
        --accent: #1d4ed8;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 32px;
        font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        color: var(--text-main);
        background: white;
      }
      .report {
        max-width: 980px;
        margin: 0 auto;
      }
      h1 {
        margin: 0 0 12px;
        font-size: 30px;
      }
      .subtitle {
        margin-bottom: 24px;
        color: var(--text-muted);
        font-size: 14px;
      }
      .meta {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin-bottom: 24px;
      }
      .meta-item, .rank-card {
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 14px 16px;
        background: var(--panel);
      }
      .meta-item__label {
        color: var(--text-muted);
        font-size: 12px;
        margin-bottom: 6px;
      }
      .meta-item__value {
        font-size: 18px;
        font-weight: 700;
      }
      .section-title {
        margin: 28px 0 12px;
        font-size: 18px;
        font-weight: 700;
      }
      .rank-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
      }
      .rank-card__badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 40px;
        height: 28px;
        border-radius: 999px;
        background: #dbeafe;
        color: var(--accent);
        font-weight: 700;
        margin-bottom: 10px;
      }
      .rank-card__name {
        font-size: 16px;
        font-weight: 700;
        margin-bottom: 8px;
      }
      .rank-card__score, .rank-card__meta, .summary {
        color: var(--text-muted);
        font-size: 13px;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 12px;
      }
      th, td {
        border: 1px solid var(--line);
        padding: 10px 12px;
        text-align: left;
        font-size: 13px;
      }
      th {
        background: #eff6ff;
        color: var(--accent);
      }
      .summary {
        margin-top: 12px;
        line-height: 1.7;
      }
      @page {
        size: A4;
        margin: 16mm;
      }
      @media print {
        body {
          padding: 0;
        }
        .report {
          max-width: none;
        }
      }
    </style>
  </head>
  <body>
    <div class="report">
      <h1>策略对比报告</h1>
      <div class="subtitle">用于沉淀同一标的、同一时间区间内多策略的收益与风控差异。</div>

      <div class="meta">
        <div class="meta-item">
          <div class="meta-item__label">标的</div>
          <div class="meta-item__value">${escapeHtml(symbol)}</div>
        </div>
        <div class="meta-item">
          <div class="meta-item__label">开始日期</div>
          <div class="meta-item__value">${escapeHtml(startDate)}</div>
        </div>
        <div class="meta-item">
          <div class="meta-item__label">结束日期</div>
          <div class="meta-item__value">${escapeHtml(endDate)}</div>
        </div>
        <div class="meta-item">
          <div class="meta-item__label">生成时间</div>
          <div class="meta-item__value">${escapeHtml(generatedTime)}</div>
        </div>
      </div>

      <div class="summary">
        实验设置：初始资金 ${escapeHtml(initialCapital ?? '') || '-'}，手续费 ${escapeHtml(commission ?? '') || '-'}，滑点 ${escapeHtml(slippage ?? '') || '-'}。
      </div>

      <div class="section-title">综合排名</div>
      <div class="rank-grid">${rankCards || '<div class="rank-card">暂无排名数据</div>'}</div>

      <div class="section-title">对比明细</div>
      <table>
        <thead>
          <tr>
            <th>策略</th>
            <th>总收益率</th>
            <th>年化收益</th>
            <th>最大回撤</th>
            <th>夏普比率</th>
            <th>交易次数</th>
            <th>参数版本</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>

      <div class="summary">
        ${bestStrategy ? `当前综合排名第一的是 ${escapeHtml(bestStrategy.strategyName)}，总收益率 ${formatPercent(bestStrategy.total_return)}，夏普比率 ${Number(bestStrategy.sharpe_ratio || 0).toFixed(2)}。` : '当前没有可汇总的策略结果。'}
      </div>
    </div>
    <script>
      window.addEventListener('load', () => {
        window.print();
      });
    </script>
  </body>
</html>`;
};

export const openStrategyComparisonPrintWindow = (reportHtml) => {
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    return false;
  }

  printWindow.opener = null;
  printWindow.document.open();
  printWindow.document.write(reportHtml);
  printWindow.document.close();
  printWindow.focus();
  return true;
};
