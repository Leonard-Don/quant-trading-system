const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { partitionConsoleMessages } = require('./consoleNoise');
const {
  assertBacktestHealthShape,
  assertProviderRuntimeShape,
  assertIndustryHeatmapShape,
  assertIndustryStocksShape,
  assertIndustryStocksStatusShape,
} = require('./fixtureContract');
const {
  assertMainLayoutClearOfSidebar,
  assertOverlayLayoutUsesFullViewport,
} = require('./layoutAssertions');

const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const ARTIFACT_DIR = path.join(PROJECT_ROOT, 'output', 'playwright');
const SCREENSHOT_PATH = path.join(ARTIFACT_DIR, 'backtest-workflow.png');
const APP_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const INDUSTRY_FIXTURE_NOW = '2026-05-07T00:00:00.000Z';
const INDUSTRY_FIXTURE_NAME = '半导体';
const INDUSTRY_FIXTURE_STOCKS = [
  {
    symbol: '688981',
    name: '中芯国际',
    rank: 1,
    total_score: 91.2,
    scoreStage: 'full',
    market_cap: 120000000000,
    pe_ratio: 8.5,
    change_pct: 1.8,
    money_flow: 240000000,
    turnover_rate: 1.2,
    industry: INDUSTRY_FIXTURE_NAME,
  },
  {
    symbol: '002371',
    name: '北方华创',
    rank: 2,
    total_score: 88.6,
    scoreStage: 'full',
    market_cap: 2100000000000,
    pe_ratio: 24.3,
    change_pct: 0.9,
    money_flow: 180000000,
    turnover_rate: 0.7,
    industry: INDUSTRY_FIXTURE_NAME,
  },
];
const INDUSTRY_FIXTURE_HEATMAP = {
  industries: [
    {
      name: INDUSTRY_FIXTURE_NAME,
      value: 2.4,
      total_score: 92.5,
      size: 1800000000000,
      stockCount: INDUSTRY_FIXTURE_STOCKS.length,
      moneyFlow: 360000000,
      turnoverRate: 1.8,
      industryVolatility: 2.1,
      industryVolatilitySource: 'stock_dispersion',
      netInflowRatio: 1.6,
      leadingStock: '中芯国际',
      leadingStockSymbol: '688981',
      sizeSource: 'estimated',
      marketCapSource: 'estimated_e2e_fixture',
      marketCapSnapshotAgeHours: null,
      marketCapSnapshotIsStale: false,
      valuationSource: 'unavailable',
      valuationQuality: 'unavailable',
      dataSources: ['e2e_fixture'],
      industryIndex: 1000,
      totalInflow: 8.2,
      totalOutflow: 4.6,
      leadingStockChange: 1.8,
      leadingStockPrice: 12.34,
      pe_ttm: 18.5,
      pb: 2.1,
      dividend_yield: 1.2,
    },
    {
      name: '消费电子',
      value: 1.1,
      total_score: 80.3,
      size: 900000000000,
      stockCount: 1,
      moneyFlow: 90000000,
      turnoverRate: 1.1,
      industryVolatility: 1.5,
      industryVolatilitySource: 'stock_dispersion',
      netInflowRatio: 0.9,
      leadingStock: '测试电子',
      sizeSource: 'estimated',
      marketCapSource: 'estimated_e2e_fixture',
      marketCapSnapshotAgeHours: null,
      marketCapSnapshotIsStale: false,
      valuationSource: 'unavailable',
      valuationQuality: 'unavailable',
      dataSources: ['e2e_fixture'],
      industryIndex: 980,
      totalInflow: 3.2,
      totalOutflow: 2.1,
      leadingStockChange: 1.1,
      leadingStockPrice: 9.87,
      pe_ttm: 22.4,
      pb: 2.8,
      dividend_yield: 0.8,
    },
  ],
  max_value: 2.4,
  min_value: 1.1,
  update_time: INDUSTRY_FIXTURE_NOW,
};

const ensureArtifactDir = () => {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
};

const assert = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

const waitForBacktestWorkspace = async (page) => {
  await page.getByText('策略回测工作台', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('数据源健康', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('回测前判断', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('Provider 熔断状态', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('策略回测配置', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
};

const waitForIndustryHeatmapReady = async (page) => {
  await page.getByText('行业热力图', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('[data-testid="heatmap-tile"]').first().waitFor({ state: 'visible', timeout: 120000 });
};

const fulfillJson = async (route, payload) => route.fulfill({
  status: 200,
  contentType: 'application/json; charset=utf-8',
  body: JSON.stringify(payload),
});

const BACKTEST_HEALTH_FIXTURE = {
  status: 'healthy',
  active_provider: { name: 'E2E fixture provider', type: 'fixture' },
  data_sources: {
    fixture: {
      name: 'E2E deterministic data source',
      installed: true,
      has_market_cap: true,
      has_multi_day: true,
      has_real_money_flow: true,
      day_options: ['1日', '5日', '10日'],
      status: 'connected',
      status_detail: 'E2E fixture ready',
    },
  },
  data_sources_contributing: ['fixture'],
  data_source_mode: 'e2e_fixture',
  message: 'E2E fixture data source ready',
};

const PROVIDER_RUNTIME_FIXTURE = {
  success: true,
  timestamp: INDUSTRY_FIXTURE_NOW,
  providers: {
    fixture: {
      provider: { name: 'fixture', description: 'Deterministic E2E provider' },
      circuit_breakers: {
        fixture_quotes: {
          name: 'fixture.quotes',
          state: 'closed',
          failure_count: 0,
          failure_threshold: 5,
          next_attempt_at: null,
        },
      },
    },
  },
};

assertBacktestHealthShape(BACKTEST_HEALTH_FIXTURE);
assertProviderRuntimeShape(PROVIDER_RUNTIME_FIXTURE);
assertIndustryHeatmapShape(INDUSTRY_FIXTURE_HEATMAP);
assertIndustryStocksShape(INDUSTRY_FIXTURE_STOCKS);

const installBacktestHealthFixtureRoutes = async (page) => {
  await page.route('**/industry/health**', (route) => fulfillJson(route, BACKTEST_HEALTH_FIXTURE));
  await page.route('**/system/providers/status**', (route) => fulfillJson(route, PROVIDER_RUNTIME_FIXTURE));
};

const buildIndustryTrendFixture = (industryName) => ({
  industry_name: industryName,
  stock_count: INDUSTRY_FIXTURE_STOCKS.length,
  expected_stock_count: INDUSTRY_FIXTURE_STOCKS.length,
  total_market_cap: 2200000000000,
  avg_pe: 16.4,
  industry_volatility: 2.1,
  industry_volatility_source: 'stock_dispersion',
  period_days: 30,
  period_change_pct: 2.4,
  period_money_flow: 360000000,
  top_gainers: INDUSTRY_FIXTURE_STOCKS.slice(0, 1),
  top_losers: INDUSTRY_FIXTURE_STOCKS.slice(1, 2),
  rise_count: 2,
  fall_count: 0,
  flat_count: 0,
  stock_coverage_ratio: 1,
  change_coverage_ratio: 1,
  market_cap_coverage_ratio: 1,
  pe_coverage_ratio: 1,
  total_market_cap_fallback: false,
  avg_pe_fallback: false,
  market_cap_source: 'estimated_e2e_fixture',
  valuation_source: 'unavailable',
  valuation_quality: 'unavailable',
  trend_series: [
    { date: '2026-05-05', close: 998, change_pct: 0.4 },
    { date: '2026-05-06', close: 1005, change_pct: 0.7 },
    { date: '2026-05-07', close: 1024, change_pct: 1.9 },
  ],
  degraded: false,
  note: 'E2E fixture for deterministic industry-to-backtest handoff.',
  update_time: INDUSTRY_FIXTURE_NOW,
});

const installIndustryBacktestFixtureRoutes = async (page) => {
  const bootstrapPayload = {
    days: 5,
    ranking_top_n: 50,
    ranking_type: 'gainers',
    ranking_sort_by: 'total_score',
    ranking_order: 'desc',
    heatmap: INDUSTRY_FIXTURE_HEATMAP,
    hot_industries: INDUSTRY_FIXTURE_HEATMAP.industries.map((industry, index) => ({
      rank: index + 1,
      industry_name: industry.name,
      score: industry.total_score,
      momentum: industry.value,
      change_pct: industry.value,
      money_flow: industry.moneyFlow,
      flow_strength: industry.netInflowRatio,
      industryVolatility: industry.industryVolatility,
      industryVolatilitySource: industry.industryVolatilitySource,
      stock_count: industry.stockCount,
      total_market_cap: industry.size,
      marketCapSource: industry.marketCapSource,
      mini_trend: [0.3, 0.7, industry.value],
      score_breakdown: [],
    })),
    leaders: { core: [], hot: [], errors: {} },
    errors: {},
  };

  await page.route('**/industry/bootstrap**', (route) => fulfillJson(route, bootstrapPayload));
  await page.route('**/industry/industries/heatmap**', (route) => fulfillJson(route, INDUSTRY_FIXTURE_HEATMAP));
  await page.route(/.*\/industry\/industries\/[^/]+\/stocks\/status.*/, (route) => {
    const stocksStatusFixture = {
      industry_name: INDUSTRY_FIXTURE_NAME,
      top_n: 20,
      status: 'ready',
      rows: INDUSTRY_FIXTURE_STOCKS.length,
      message: 'E2E fixture ready',
      updated_at: INDUSTRY_FIXTURE_NOW,
    };
    assertIndustryStocksStatusShape(stocksStatusFixture);
    return fulfillJson(route, stocksStatusFixture);
  });
  await page.route(/.*\/industry\/industries\/[^/]+\/stocks\/stream.*/, (route) => route.fulfill({
    status: 200,
    contentType: 'text/event-stream; charset=utf-8',
    body: 'data: {"status":"ready"}\n\n',
  }));
  await page.route(/.*\/industry\/industries\/[^/]+\/stocks(?:\?.*)?$/, (route) => fulfillJson(route, INDUSTRY_FIXTURE_STOCKS));
  await page.route(/.*\/industry\/industries\/[^/]+\/trend.*/, (route) => {
    const match = route.request().url().match(/\/industry\/industries\/([^/]+)\/trend/);
    const industryName = match ? decodeURIComponent(match[1]) : INDUSTRY_FIXTURE_NAME;
    return fulfillJson(route, buildIndustryTrendFixture(industryName));
  });
};

const closeIndustryDetailModal = async (page) => {
  const modal = page.locator('[data-testid="industry-detail-modal"]');
  if (!(await modal.count().catch(() => 0)) || !(await modal.isVisible().catch(() => false))) {
    return;
  }

  const closeButton = modal.locator('.ant-modal-close').first();
  if (await closeButton.count().catch(() => 0)) {
    await closeButton.click({ force: true }).catch(() => {});
  } else {
    await page.keyboard.press('Escape').catch(() => {});
  }
  await modal.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
};

const waitForIndustryDetailReady = async (page) => {
  const modal = page.locator('[data-testid="industry-detail-modal"]');
  await modal.waitFor({ state: 'visible', timeout: 12000 });
  await page.locator('[data-testid="industry-detail-panel"]').waitFor({ state: 'visible', timeout: 12000 });
  await page.waitForFunction(() => {
    const panel = document.querySelector('[data-testid="industry-detail-panel"]');
    if (!panel) return false;
    const text = panel.textContent || '';
    return Boolean(
      panel.querySelector('[data-testid="industry-stock-table"]')
      || panel.querySelector('[data-testid="industry-ai-insight-panel"]')
      || text.includes('当前显示的是降级行业数据')
      || text.includes('成分股明细暂不可用')
      || text.includes('当前数据源未返回成分股明细')
      || text.includes('暂无成分股数据')
    );
  }, null, { timeout: 45000 });
  return modal;
};

const activateIndustryDetailTab = async (page, labelPattern) => {
  const modal = page.locator('[data-testid="industry-detail-modal"]');
  const targetTab = modal.locator('.ant-tabs-tab').filter({ hasText: labelPattern }).first();
  if (!(await targetTab.count().catch(() => 0))) {
    return;
  }
  const selected = await targetTab.getAttribute('aria-selected').catch(() => null);
  if (selected !== 'true') {
    await targetTab.click({ force: true });
  }
};

const ensureIndustryStockTableVisible = async (page) => {
  await activateIndustryDetailTab(page, /成分股/);
  await page.waitForFunction(() => {
    const panel = document.querySelector('[data-testid="industry-detail-panel"]');
    if (!panel) return false;
    const table = panel.querySelector('[data-testid="industry-stock-table"]');
    if (table && Array.from(table.querySelectorAll('button')).some((button) => (button.textContent || '').includes('回测'))) {
      return true;
    }
    const activePane = panel.querySelector('.ant-tabs-tabpane-active') || panel;
    if (activePane.querySelector('.ant-spin-spinning')) return false;
    const text = activePane.textContent || '';
    return text.includes('成分股明细暂不可用')
      || text.includes('当前数据源未返回成分股明细')
      || text.includes('暂无成分股数据');
  }, null, { timeout: 45000 }).catch(() => {});
  const stockTable = page.locator('[data-testid="industry-stock-table"]').first();
  if (await stockTable.count().catch(() => 0)) {
    await stockTable.waitFor({ state: 'visible', timeout: 12000 }).catch(() => {});
    return stockTable;
  }
  return null;
};

const openIndustryDetailFromTile = async (page, tileLocator) => {
  const industryName = await tileLocator.getAttribute('data-industry-name').catch(() => '');
  await tileLocator.click({ force: true });
  const modal = page.locator('[data-testid="industry-detail-modal"]');
  const openedByPointer = await modal.waitFor({ state: 'visible', timeout: 2500 }).then(() => true).catch(() => false);
  if (!openedByPointer && industryName) {
    await page.evaluate((targetIndustry) => {
      const node = Array.from(document.querySelectorAll('[data-testid="heatmap-tile"]'))
        .find((candidate) => (candidate.getAttribute('data-industry-name') || '') === targetIndustry);
      node?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }, industryName);
  }
  return waitForIndustryDetailReady(page);
};

const openIndustryWithBacktestButton = async (page) => {
  const preferredIndustries = ['半导体', '消费电子', '通信设备', '电池', '银行'];
  const candidates = [];
  for (const industryName of preferredIndustries) {
    const candidate = page.locator(`[data-testid="heatmap-tile"][data-industry-name="${industryName}"]`).first();
    if (await candidate.count().catch(() => 0)) {
      candidates.push(candidate);
    }
  }
  candidates.push(page.locator('[data-testid="heatmap-tile"]').first());

  for (const candidate of candidates) {
    await closeIndustryDetailModal(page);
    const industryName = await candidate.getAttribute('data-industry-name').catch(() => '');
    await openIndustryDetailFromTile(page, candidate);
    const stockTable = await ensureIndustryStockTableVisible(page);
    if (!stockTable) {
      continue;
    }
    const backtestButton = stockTable.locator('button').filter({ hasText: '回测' }).first();
    if (await backtestButton.count().catch(() => 0)) {
      console.log(`选择行业详情: ${industryName || '首个行业'}`);
      return backtestButton;
    }
  }

  throw new Error('未找到可用于回测接力的行业成分股按钮');
};

const readLocalStorageJson = async (page, key, fallback = null) => page.evaluate(
  ({ storageKey, fallbackValue }) => {
    try {
      return JSON.parse(window.localStorage.getItem(storageKey) || JSON.stringify(fallbackValue));
    } catch (error) {
      return fallbackValue;
    }
  },
  { storageKey: key, fallbackValue: fallback }
);

(async () => {
  ensureArtifactDir();

  const browser = await chromium.launch();
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    consoleErrors.push(error.message);
  });

  await page.setViewportSize({ width: 1440, height: 1040 });
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.localStorage.setItem('backtest_workspace_draft', JSON.stringify({
      symbol: 'AAPL',
      strategy: 'buy_and_hold',
      dateRange: ['2025-05-02', '2026-05-02'],
      dateRangeMode: 'fixed',
      initial_capital: 10000,
      commission: 0.1,
      slippage: 0.1,
      fixed_commission: 1,
      min_commission: 2,
      market_impact_bps: 3,
      market_impact_model: 'linear',
      execution_lag: 2,
      parameters: {},
      updated_at: new Date().toISOString(),
    }));
  });

  console.log('正在访问主回测工作台...');
  await installBacktestHealthFixtureRoutes(page);
  await page.goto(`${APP_URL}/?view=backtest`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForBacktestWorkspace(page);
  await assertMainLayoutClearOfSidebar(page, 'backtest workspace');
  await assertOverlayLayoutUsesFullViewport(page, 'backtest workspace');
  await page.getByText('信号执行延迟 (K线)', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('市场冲击 (bp)', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('市场冲击模型', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });

  const symbolInput = page.getByPlaceholder(/输入股票代码/);
  await symbolInput.waitFor({ state: 'visible', timeout: 60000 });
  const symbolValue = await symbolInput.inputValue();
  assert(symbolValue === 'AAPL', `回测草稿未正确预填标的，当前为 ${symbolValue}`);
  console.log('回测可信度输入项与草稿预填已显示: 是');

  await page.getByRole('button', { name: /开始回测/ }).click();
  await page.getByText('执行诊断', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('研究快照', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('信号延迟', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('T+2 K线', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('冲击模型', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('linear · 3.0bp', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('冲击成本估算', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('回测结果执行诊断与成本口径已显示: 是');

  const snapshotNote = 'E2E 回测研究快照';
  await page.getByPlaceholder('写下这次结果的判断、下一步验证或需要复核的数据源').fill(snapshotNote);
  await page.getByRole('button', { name: /保存快照/ }).click();
  await page.waitForFunction((expectedNote) => {
    const snapshots = JSON.parse(window.localStorage.getItem('backtest_research_snapshots') || '[]');
    return snapshots.some((item) => item.symbol === 'AAPL' && item.note === expectedNote);
  }, snapshotNote, { timeout: 10000 });
  const snapshots = await readLocalStorageJson(page, 'backtest_research_snapshots', []);
  assert(Array.isArray(snapshots) && snapshots.length > 0, '研究快照未写入 localStorage');
  console.log('研究快照保存已生效: 是');

  await page.getByRole('button', { name: /继续做高级实验/ }).click();
  await page.waitForFunction(() => new URLSearchParams(window.location.search).get('tab') === 'advanced', null, { timeout: 15000 });
  await page.getByText('高级实验台', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('主回测结果到高级实验台接力已生效: 是');

  console.log('验证行业成分股带入主回测...');
  await installIndustryBacktestFixtureRoutes(page);
  await page.goto(`${APP_URL}/?view=industry`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryHeatmapReady(page);
  const backtestButton = await openIndustryWithBacktestButton(page);
  await backtestButton.scrollIntoViewIfNeeded();
  await backtestButton.click();
  await page.waitForFunction(() => {
    const params = new URLSearchParams(window.location.search);
    const view = params.get('view') || 'backtest';
    return view === 'backtest'
      && params.get('action') === 'prefill_backtest'
      && params.get('source') === 'industry_stock_table';
  }, null, { timeout: 15000 });
  await waitForBacktestWorkspace(page);
  const handoffDraft = await readLocalStorageJson(page, 'backtest_workspace_draft', {});
  const handoffSymbolValue = await page.getByPlaceholder(/输入股票代码/).inputValue();
  assert(handoffDraft.source === 'industry_stock_table', '行业带入回测的来源未写入草稿');
  assert(handoffDraft.symbol && handoffDraft.symbol === handoffSymbolValue, '行业带入回测的标的未正确预填到表单');
  assert(handoffDraft.execution_lag === 1 && handoffDraft.market_impact_model === 'constant', '行业带入回测未使用默认执行假设');
  console.log('行业成分股带入主回测已生效: 是');

  await page.screenshot({ path: SCREENSHOT_PATH, fullPage: true });
  const { unknown: unexpectedConsoleErrors, ignoredSummary } = partitionConsoleMessages(consoleErrors);
  ignoredSummary.forEach((entry) => {
    console.log(`已忽略已知控制台噪声: ${entry.label} x${entry.count}`);
  });
  assert(
    unexpectedConsoleErrors.length === 0,
    `浏览器控制台存在未知错误:\n${unexpectedConsoleErrors.join('\n')}`
  );

  await browser.close();
  console.log('主回测工作流 E2E 回归通过');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
