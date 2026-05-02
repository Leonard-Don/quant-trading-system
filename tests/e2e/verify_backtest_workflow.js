const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { partitionConsoleMessages } = require('./consoleNoise');

const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const ARTIFACT_DIR = path.join(PROJECT_ROOT, 'output', 'playwright');
const SCREENSHOT_PATH = path.join(ARTIFACT_DIR, 'backtest-workflow.png');
const APP_URL = process.env.FRONTEND_URL || 'http://localhost:3000';

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
  await page.getByText('策略回测配置', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
};

const waitForIndustryHeatmapReady = async (page) => {
  await page.getByText('行业热力图', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('[data-testid="heatmap-tile"]').first().waitFor({ state: 'visible', timeout: 60000 });
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
  await page.goto(`${APP_URL}/?view=backtest`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForBacktestWorkspace(page);
  await page.getByText('信号执行延迟 (K线)', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('市场冲击 (bp)', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('市场冲击模型', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });

  const symbolInput = page.getByPlaceholder('输入股票代码 (如: AAPL)');
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
  const handoffSymbolValue = await page.getByPlaceholder('输入股票代码 (如: AAPL)').inputValue();
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
