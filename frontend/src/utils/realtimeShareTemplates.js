export const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

export const formatReviewSnapshotMarkdown = (snapshot, getSnapshotOutcomeMeta) => {
  const outcomeMeta = getSnapshotOutcomeMeta(snapshot?.outcome);
  const anomalies = Array.isArray(snapshot?.anomalies) ? snapshot.anomalies : [];
  const watchedSymbols = Array.isArray(snapshot?.watchedSymbols) ? snapshot.watchedSymbols : [];
  const quoteSnapshots = Array.isArray(snapshot?.quoteSnapshots) ? snapshot.quoteSnapshots : [];

  return [
    `## 复盘快照 - ${snapshot?.spotlightName || snapshot?.spotlightSymbol || '未记录焦点标的'}`,
    '',
    `- 时间: ${snapshot?.createdAt || '--'}`,
    `- 分组: ${snapshot?.activeTabLabel || snapshot?.activeTab || '--'}`,
    `- 焦点标的: ${snapshot?.spotlightSymbol || '--'}`,
    `- 链路模式: ${snapshot?.transportModeLabel || '--'}`,
    `- 结果: ${outcomeMeta?.label || '未标记'}`,
    `- 异动数量: ${snapshot?.anomalyCount ?? 0}`,
    `- 覆盖情况: ${snapshot?.loadedCount ?? 0}/${snapshot?.totalCount ?? 0}`,
    snapshot?.note ? `- 备注: ${snapshot.note}` : null,
    '',
    '### 跟踪标的',
    watchedSymbols.length ? watchedSymbols.map((item) => `- ${item}`).join('\n') : '- --',
    '',
    '### 当时价格快照',
    quoteSnapshots.length
      ? quoteSnapshots.map((item) => `- ${item.symbol}: 价格 ${item.price ?? '--'} | 涨跌幅 ${item.changePercent ?? '--'} | 成交量 ${item.volume ?? '--'}`).join('\n')
      : '- --',
    '',
    '### 当时异动',
    anomalies.length
      ? anomalies.map((item) => `- ${item.title} | ${item.symbol}: ${item.description}`).join('\n')
      : '- 无显著异动',
  ].filter(Boolean).join('\n');
};

export const formatReviewSummaryMarkdown = ({
  scopeLabel,
  filteredReviewSnapshots,
  reviewOutcomeSummary,
  validationRate,
  reviewAttribution,
}) => [
  `## 实时行情复盘摘要 - ${scopeLabel}`,
  '',
  `- 样本数: ${filteredReviewSnapshots.length}`,
  `- 已复盘: ${reviewOutcomeSummary.validated + reviewOutcomeSummary.invalidated}/${filteredReviewSnapshots.length}`,
  `- 验证有效: ${reviewOutcomeSummary.validated}`,
  `- 观察失效: ${reviewOutcomeSummary.invalidated}`,
  `- 持续观察: ${reviewOutcomeSummary.watching}`,
  `- 有效率: ${validationRate}`,
  `- 最强分组: ${reviewAttribution.topValidatedMarket}`,
  `- 常失效异动: ${reviewAttribution.topInvalidatedSignal}`,
  `- 高频焦点: ${reviewAttribution.topSpotlightSymbol}`,
].join('\n');

export const formatReviewSnapshotShareHtml = (snapshot, getSnapshotOutcomeMeta) => {
  const outcomeMeta = getSnapshotOutcomeMeta(snapshot?.outcome);
  const anomalies = Array.isArray(snapshot?.anomalies) ? snapshot.anomalies : [];
  const watchedSymbols = Array.isArray(snapshot?.watchedSymbols) ? snapshot.watchedSymbols : [];
  const quoteSnapshots = Array.isArray(snapshot?.quoteSnapshots) ? snapshot.quoteSnapshots : [];

  return `
    <section class="share-card">
      <div class="eyebrow">Realtime Review Snapshot</div>
      <h1>${escapeHtml(snapshot?.spotlightName || snapshot?.spotlightSymbol || '未记录焦点标的')}</h1>
      <p class="subtitle">${escapeHtml(snapshot?.transportModeLabel || '--')}</p>
      <div class="chips">
        <span class="chip">${escapeHtml(snapshot?.activeTabLabel || snapshot?.activeTab || '--')}</span>
        <span class="chip">${escapeHtml(outcomeMeta?.label || '未标记')}</span>
        <span class="chip">${escapeHtml(snapshot?.createdAt || '--')}</span>
      </div>
      <div class="metrics">
        <div class="metric"><span>焦点标的</span><strong>${escapeHtml(snapshot?.spotlightSymbol || '--')}</strong></div>
        <div class="metric"><span>异动数量</span><strong>${escapeHtml(snapshot?.anomalyCount ?? 0)}</strong></div>
        <div class="metric"><span>覆盖情况</span><strong>${escapeHtml(`${snapshot?.loadedCount ?? 0}/${snapshot?.totalCount ?? 0}`)}</strong></div>
      </div>
      ${snapshot?.note ? `<div class="note"><strong>备注</strong><p>${escapeHtml(snapshot.note)}</p></div>` : ''}
      <div class="section">
        <h2>跟踪标的</h2>
        <div class="list">${watchedSymbols.length ? watchedSymbols.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join('') : '<span class="muted">--</span>'}</div>
      </div>
      <div class="section">
        <h2>当时价格快照</h2>
        ${quoteSnapshots.length ? quoteSnapshots.map((item) => `
          <div class="anomaly">
            <strong>${escapeHtml(item.symbol)}</strong>
            <p>价格 ${escapeHtml(item.price ?? '--')} · 涨跌幅 ${escapeHtml(item.changePercent ?? '--')} · 成交量 ${escapeHtml(item.volume ?? '--')}</p>
          </div>
        `).join('') : '<p class="muted">--</p>'}
      </div>
      <div class="section">
        <h2>当时异动</h2>
        ${anomalies.length ? anomalies.map((item) => `
          <div class="anomaly">
            <strong>${escapeHtml(item.title)} · ${escapeHtml(item.symbol)}</strong>
            <p>${escapeHtml(item.description)}</p>
          </div>
        `).join('') : '<p class="muted">无显著异动</p>'}
      </div>
    </section>
  `;
};

export const formatReviewSummaryShareHtml = ({
  scopeLabel,
  filteredReviewSnapshots,
  reviewOutcomeSummary,
  validationRate,
  reviewAttribution,
}) => `
  <section class="share-card">
    <div class="eyebrow">Realtime Review Summary</div>
    <h1>实时行情复盘摘要</h1>
    <p class="subtitle">${escapeHtml(scopeLabel)}</p>
    <div class="metrics">
      <div class="metric"><span>样本数</span><strong>${escapeHtml(filteredReviewSnapshots.length)}</strong></div>
      <div class="metric"><span>已复盘</span><strong>${escapeHtml(`${reviewOutcomeSummary.validated + reviewOutcomeSummary.invalidated}/${filteredReviewSnapshots.length}`)}</strong></div>
      <div class="metric"><span>验证有效</span><strong>${escapeHtml(reviewOutcomeSummary.validated)}</strong></div>
      <div class="metric"><span>观察失效</span><strong>${escapeHtml(reviewOutcomeSummary.invalidated)}</strong></div>
      <div class="metric"><span>持续观察</span><strong>${escapeHtml(reviewOutcomeSummary.watching)}</strong></div>
      <div class="metric"><span>有效率</span><strong>${escapeHtml(validationRate)}</strong></div>
    </div>
    <div class="section">
      <h2>归因结果</h2>
      <div class="metrics">
        <div class="metric"><span>最强分组</span><strong>${escapeHtml(reviewAttribution.topValidatedMarket)}</strong></div>
        <div class="metric"><span>常失效异动</span><strong>${escapeHtml(reviewAttribution.topInvalidatedSignal)}</strong></div>
        <div class="metric"><span>高频焦点</span><strong>${escapeHtml(reviewAttribution.topSpotlightSymbol)}</strong></div>
      </div>
    </div>
  </section>
`;

export const buildRealtimeShareDocument = (title, bodyHtml) => `<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(title)}</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f8fafc;
        --panel: rgba(255, 255, 255, 0.92);
        --panel-border: rgba(148, 163, 184, 0.24);
        --text-primary: #0f172a;
        --text-secondary: #475569;
        --text-muted: #64748b;
        --accent: #2563eb;
        --accent-soft: rgba(37, 99, 235, 0.1);
        --chip-bg: rgba(15, 23, 42, 0.06);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        min-height: 100vh;
        font-family: "SF Pro Display", "PingFang SC", "Helvetica Neue", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(59, 130, 246, 0.16), transparent 32%),
          radial-gradient(circle at top right, rgba(16, 185, 129, 0.14), transparent 30%),
          linear-gradient(180deg, #f8fbff 0%, var(--bg) 100%);
        color: var(--text-primary);
        padding: 32px;
      }
      .share-shell { max-width: 920px; margin: 0 auto; }
      .share-card {
        background: var(--panel);
        border: 1px solid var(--panel-border);
        border-radius: 28px;
        box-shadow: 0 28px 60px rgba(15, 23, 42, 0.12);
        padding: 32px;
        backdrop-filter: blur(12px);
      }
      .eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--accent);
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      h1 { margin: 18px 0 8px; font-size: clamp(28px, 4vw, 40px); line-height: 1.08; }
      .subtitle { margin: 0; font-size: 15px; color: var(--text-secondary); }
      .chips, .list { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
      .chip, .pill {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 8px 12px;
        background: var(--chip-bg);
        color: var(--text-primary);
        font-size: 13px;
        font-weight: 600;
      }
      .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: 12px; margin-top: 22px; }
      .metric {
        border-radius: 20px;
        padding: 16px 18px;
        background: rgba(255, 255, 255, 0.74);
        border: 1px solid rgba(148, 163, 184, 0.18);
        min-height: 92px;
      }
      .metric span { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }
      .metric strong { font-size: 20px; line-height: 1.2; }
      .section, .note { margin-top: 24px; padding-top: 20px; border-top: 1px solid rgba(148, 163, 184, 0.18); }
      .section h2, .note strong { display: block; margin: 0 0 12px; font-size: 15px; }
      .note p, .anomaly p { margin: 8px 0 0; color: var(--text-secondary); line-height: 1.6; }
      .anomaly { padding: 14px 0; }
      .anomaly + .anomaly { border-top: 1px dashed rgba(148, 163, 184, 0.2); }
      .muted { color: var(--text-muted); }
      @media (max-width: 640px) {
        body { padding: 18px; }
        .share-card { padding: 22px; border-radius: 22px; }
      }
    </style>
  </head>
  <body>
    <main class="share-shell">
      ${bodyHtml}
    </main>
  </body>
</html>`;
