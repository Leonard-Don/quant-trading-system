const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

const formatCurrency = (value, digits = 2) => (
  value === null || value === undefined || value === ''
    ? '—'
    : `$${Number(value).toFixed(digits)}`
);

const formatPercentPoints = (value, digits = 1) => (
  value === null || value === undefined || value === ''
    ? '—'
    : `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(digits)}%`
);

const formatRate = (value, digits = 1) => (
  value === null || value === undefined || value === ''
    ? '—'
    : `${Number(value).toFixed(digits)}%`
);

const formatRatio = (value, digits = 2) => (
  value === null || value === undefined || value === ''
    ? '—'
    : Number(value).toFixed(digits)
);

const renderMetricCard = (label, value, tone = 'neutral') => `
  <div class="metric-card metric-card--${tone}">
    <div class="metric-card__label">${escapeHtml(label)}</div>
    <div class="metric-card__value">${escapeHtml(value)}</div>
  </div>
`;

const renderTable = (headers = [], rows = []) => `
  <table>
    <thead>
      <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join('')}</tr>
    </thead>
    <tbody>
      ${rows.length ? rows.map((row) => `
        <tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>
      `).join('') : `<tr><td colspan="${headers.length}">暂无数据</td></tr>`}
    </tbody>
  </table>
`;

export const buildPricingResearchAuditPayload = ({
  symbol,
  period,
  context = {},
  analysis = null,
  snapshot = null,
  playbook = null,
  sensitivity = null,
  history = null,
  peerComparison = null,
}) => ({
  exported_at: new Date().toISOString(),
  symbol,
  period,
  context,
  playbook,
  snapshot,
  analysis,
  sensitivity,
  history,
  peer_comparison: peerComparison,
});

export const buildPricingResearchReportHtml = ({
  symbol,
  period,
  generatedAt,
  analysis = {},
  snapshot = {},
  context = {},
  sensitivity = {},
  history = {},
  peerComparison = {},
}) => {
  const gap = analysis?.gap_analysis || {};
  const valuation = analysis?.valuation || {};
  const factorModel = analysis?.factor_model || {};
  const implications = analysis?.implications || {};
  const drivers = analysis?.deviation_drivers?.drivers || [];
  const primaryDriver = analysis?.deviation_drivers?.primary_driver || drivers[0] || null;
  const dcfScenarios = valuation?.dcf?.scenarios || [];
  const comparableMethods = valuation?.comparable?.methods || [];
  const confidenceBreakdown = implications?.confidence_breakdown || [];
  const thesis = analysis?.macro_mispricing_thesis || implications?.macro_mispricing_thesis || snapshot?.macro_mispricing_thesis || {};
  const historyRows = (history?.history || []).slice(-8).reverse();
  const peerRows = [peerComparison?.target, ...(peerComparison?.peers || [])].filter(Boolean);
  const generatedTime = generatedAt || new Date().toLocaleString();
  const evidenceItems = [
    valuation.current_price_source ? `现价来源：${valuation.current_price_source}` : null,
    factorModel.period ? `分析窗口：${factorModel.period}` : null,
    factorModel.data_points ? `因子样本：${factorModel.data_points}` : null,
    valuation?.comparable?.benchmark_source ? `可比基准：${valuation.comparable.benchmark_source}` : null,
  ].filter(Boolean);

  return `<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>定价研究报告</title>
    <style>
      :root {
        color-scheme: light;
        --text-main: #0f172a;
        --text-muted: #475569;
        --line: #dbe4f0;
        --panel: #f8fafc;
        --panel-strong: #eff6ff;
        --accent: #1d4ed8;
        --good: #15803d;
        --warn: #b45309;
        --bad: #b91c1c;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 28px;
        font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        color: var(--text-main);
        background: white;
      }
      .report {
        max-width: 1040px;
        margin: 0 auto;
      }
      h1 {
        margin: 0 0 12px;
        font-size: 30px;
      }
      .subtitle, .summary, .muted {
        color: var(--text-muted);
        line-height: 1.7;
      }
      .header-grid, .metric-grid, .evidence-grid, .driver-grid {
        display: grid;
        gap: 12px;
      }
      .header-grid {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        margin: 20px 0 12px;
      }
      .metric-grid {
        grid-template-columns: repeat(5, minmax(0, 1fr));
        margin: 20px 0;
      }
      .evidence-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .driver-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .panel, .metric-card {
        border: 1px solid var(--line);
        border-radius: 16px;
        background: var(--panel);
        padding: 14px 16px;
      }
      .panel--strong {
        background: var(--panel-strong);
      }
      .metric-card__label, .meta-label, .section-kicker {
        color: var(--text-muted);
        font-size: 12px;
        margin-bottom: 6px;
      }
      .metric-card__value, .meta-value {
        font-size: 18px;
        font-weight: 700;
      }
      .metric-card--good .metric-card__value { color: var(--good); }
      .metric-card--bad .metric-card__value { color: var(--bad); }
      .metric-card--warn .metric-card__value { color: var(--warn); }
      .section-title {
        margin: 30px 0 12px;
        font-size: 18px;
        font-weight: 700;
      }
      .pill-list {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 10px;
      }
      .pill {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        border: 1px solid var(--line);
        background: white;
        padding: 6px 10px;
        font-size: 12px;
        color: var(--text-muted);
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
      .kv {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px 14px;
      }
      .kv-item {
        border-bottom: 1px dashed var(--line);
        padding-bottom: 8px;
      }
      .kv-item strong {
        display: block;
        margin-bottom: 4px;
        font-size: 12px;
        color: var(--text-muted);
      }
      .two-col {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }
      @page {
        size: A4;
        margin: 16mm;
      }
      @media print {
        body { padding: 0; }
        .report { max-width: none; }
      }
    </style>
  </head>
  <body>
    <div class="report">
      <h1>定价研究报告</h1>
      <div class="subtitle">把一级估值、因子定价、驱动归因和交易情景放进同一份可打印研究摘要。</div>

      <div class="header-grid">
        <div class="panel">
          <div class="meta-label">标的</div>
          <div class="meta-value">${escapeHtml(symbol || analysis?.symbol || '—')}</div>
        </div>
        <div class="panel">
          <div class="meta-label">分析窗口</div>
          <div class="meta-value">${escapeHtml(period || factorModel?.period || '1y')}</div>
        </div>
        <div class="panel">
          <div class="meta-label">生成时间</div>
          <div class="meta-value">${escapeHtml(generatedTime)}</div>
        </div>
        <div class="panel">
          <div class="meta-label">研究来源</div>
          <div class="meta-value">${escapeHtml(context?.source || '直接分析')}</div>
        </div>
      </div>

      <div class="metric-grid">
        ${renderMetricCard('当前市价', formatCurrency(gap.current_price))}
        ${renderMetricCard('公允价值', formatCurrency(gap.fair_value_mid), 'good')}
        ${renderMetricCard('偏差幅度', formatPercentPoints(gap.gap_pct), Number(gap.gap_pct || 0) > 0 ? 'bad' : 'good')}
        ${renderMetricCard('研究观点', implications.primary_view || gap.direction || '合理')}
        ${renderMetricCard('置信度', `${implications.confidence || 'medium'} / ${formatRatio(implications.confidence_score)}`, 'warn')}
      </div>

      <div class="panel panel--strong">
        <div class="section-kicker">执行摘要</div>
        <div class="summary">
          ${escapeHtml(analysis?.summary || implications?.trade_setup?.summary || '当前研究已完成定价偏差、估值锚点和因子证据的联动分析。')}
        </div>
        <div class="pill-list">
          ${(evidenceItems.length ? evidenceItems : ['暂无额外证据标签']).map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join('')}
          ${implications?.factor_alignment?.label ? `<span class="pill">证据共振：${escapeHtml(implications.factor_alignment.label)}</span>` : ''}
          ${primaryDriver?.factor ? `<span class="pill">主驱动：${escapeHtml(primaryDriver.factor)}</span>` : ''}
        </div>
      </div>

      <div class="section-title">估值与因子概览</div>
      <div class="two-col">
        <div class="panel">
          <div class="section-kicker">估值锚点</div>
          <div class="kv">
            <div class="kv-item"><strong>公允价值区间</strong>${escapeHtml(`${formatCurrency(gap.fair_value_low)} ~ ${formatCurrency(gap.fair_value_high)}`)}</div>
            <div class="kv-item"><strong>DCF 中枢</strong>${escapeHtml(formatCurrency(valuation?.dcf?.intrinsic_value))}</div>
            <div class="kv-item"><strong>Comparable 中枢</strong>${escapeHtml(formatCurrency(valuation?.comparable?.fair_value))}</div>
            <div class="kv-item"><strong>综合方法</strong>${escapeHtml(valuation?.fair_value?.method || '—')}</div>
          </div>
        </div>
        <div class="panel">
          <div class="section-kicker">因子摘要</div>
          <div class="kv">
            <div class="kv-item"><strong>CAPM Alpha</strong>${escapeHtml(formatPercentPoints(factorModel?.capm?.alpha_pct, 2))}</div>
            <div class="kv-item"><strong>CAPM Beta</strong>${escapeHtml(formatRatio(factorModel?.capm?.beta, 3))}</div>
            <div class="kv-item"><strong>FF3 Alpha</strong>${escapeHtml(formatPercentPoints(factorModel?.fama_french?.alpha_pct, 2))}</div>
            <div class="kv-item"><strong>FF5 Alpha</strong>${escapeHtml(formatPercentPoints(factorModel?.fama_french_five_factor?.alpha_pct, 2))}</div>
          </div>
        </div>
      </div>

      <div class="section-title">估值细节</div>
      ${renderTable(
        ['情景', '公允价值', 'WACC', '初始增长', '溢价/折价'],
        dcfScenarios.map((item) => [
          item.label || item.name || '—',
          formatCurrency(item.intrinsic_value),
          formatRate(Number(item.assumptions?.wacc || 0) * 100),
          formatRate(Number(item.assumptions?.initial_growth || 0) * 100),
          formatPercentPoints(item.premium_discount),
        ]),
      )}

      ${renderTable(
        ['方法', '当前倍数', '行业/同行基准', '公允价值'],
        comparableMethods.map((item) => [
          item.method || '—',
          formatRatio(item.current_multiple, 1),
          formatRatio(item.benchmark_multiple, 1),
          formatCurrency(item.fair_value),
        ]),
      )}

      <div class="section-title">驱动与交易情景</div>
      <div class="driver-grid">
        <div class="panel">
          <div class="section-kicker">主驱动</div>
          <div style="font-size: 18px; font-weight: 700; margin-bottom: 6px;">${escapeHtml(primaryDriver?.factor || '暂无')}</div>
          <div class="muted">${escapeHtml(primaryDriver?.ranking_reason || primaryDriver?.description || '暂无主驱动解释')}</div>
        </div>
        <div class="panel">
          <div class="section-kicker">交易情景</div>
          <div class="kv">
            <div class="kv-item"><strong>立场</strong>${escapeHtml(implications?.trade_setup?.stance || '观察')}</div>
            <div class="kv-item"><strong>目标价</strong>${escapeHtml(formatCurrency(implications?.trade_setup?.target_price))}</div>
            <div class="kv-item"><strong>风险边界</strong>${escapeHtml(formatCurrency(implications?.trade_setup?.stop_loss))}</div>
            <div class="kv-item"><strong>盈亏比</strong>${escapeHtml(formatRatio(implications?.trade_setup?.risk_reward))}</div>
          </div>
        </div>
      </div>

      ${(thesis?.primary_leg?.symbol || thesis?.hedge_leg?.symbol) ? `
        <div class="section-title">Macro Mispricing Thesis</div>
        <div class="driver-grid">
          <div class="panel">
            <div class="section-kicker">主腿 / 对冲腿</div>
            <div class="kv">
              <div class="kv-item"><strong>主腿</strong>${escapeHtml(`${thesis?.primary_leg?.symbol || '—'} ${thesis?.primary_leg?.side || ''}`)}</div>
              <div class="kv-item"><strong>对冲腿</strong>${escapeHtml(`${thesis?.hedge_leg?.symbol || '—'} ${thesis?.hedge_leg?.side || ''}`)}</div>
              <div class="kv-item"><strong>姿态</strong>${escapeHtml(thesis?.stance || '观察')}</div>
              <div class="kv-item"><strong>观察期</strong>${escapeHtml(thesis?.horizon || '—')}</div>
            </div>
          </div>
          <div class="panel">
            <div class="section-kicker">Kill Conditions</div>
            <div class="summary">${escapeHtml((thesis?.kill_conditions || []).slice(0, 3).join('；') || '暂无')}</div>
          </div>
        </div>
      ` : ''}

      <div class="section-title">置信度拆解</div>
      ${renderTable(
        ['维度', '变化', '状态', '说明'],
        confidenceBreakdown.map((item) => [
          item.label || item.key || '—',
          item.delta > 0 ? `+${Number(item.delta).toFixed(2)}` : Number(item.delta || 0).toFixed(2),
          item.status || 'neutral',
          item.detail || '—',
        ]),
      )}

      <div class="section-title">历史与同行</div>
      <div class="two-col">
        <div class="panel">
          <div class="section-kicker">最近偏差轨迹</div>
          ${renderTable(
            ['日期', '价格', '偏差'],
            historyRows.map((item) => [
              item.date || '—',
              formatCurrency(item.price),
              formatPercentPoints(item.gap_pct),
            ]),
          )}
        </div>
        <div class="panel">
          <div class="section-kicker">同行估值快照</div>
          ${renderTable(
            ['标的', '现价', '公允价值', '溢折价'],
            peerRows.slice(0, 6).map((item) => [
              item.symbol || '—',
              formatCurrency(item.current_price),
              formatCurrency(item.fair_value),
              formatPercentPoints(item.premium_discount),
            ]),
          )}
        </div>
      </div>

      <div class="section-title">审计附注</div>
      <div class="panel">
        <div class="summary">该导出用于研究沉淀与复盘。结构化审计快照已单独保存在导出 JSON 中，可对接工作台或外部归档流程。</div>
        ${(snapshot?.audit_trail || sensitivity?.selected_case) ? `
          <div class="pill-list">
            ${snapshot?.audit_trail?.price_source ? `<span class="pill">现价来源：${escapeHtml(snapshot.audit_trail.price_source)}</span>` : ''}
            ${snapshot?.audit_trail?.factor_source ? `<span class="pill">FF3 来源：${escapeHtml(snapshot.audit_trail.factor_source)}</span>` : ''}
            ${snapshot?.audit_trail?.five_factor_source ? `<span class="pill">FF5 来源：${escapeHtml(snapshot.audit_trail.five_factor_source)}</span>` : ''}
            ${snapshot?.audit_trail?.comparable_benchmark_source ? `<span class="pill">可比基准：${escapeHtml(snapshot.audit_trail.comparable_benchmark_source)}</span>` : ''}
            ${sensitivity?.selected_case ? `<span class="pill">What-If 当前情景：${escapeHtml(sensitivity.selected_case.label || '自定义')}</span>` : ''}
          </div>
        ` : ''}
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

export const openPricingResearchPrintWindow = (reportHtml) => {
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
