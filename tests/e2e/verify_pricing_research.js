const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FRONTEND_BASE_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:3000';
const API_BASE_URL = process.env.E2E_API_URL || 'http://localhost:8000';
const SYMBOL = String(process.env.E2E_PRICING_SYMBOL || 'AAPL').trim().toUpperCase();
const SCREENING_UNIVERSE = process.env.E2E_PRICING_UNIVERSE || `${SYMBOL}\nMSFT\nNVDA`;
const INITIAL_PERIOD = process.env.E2E_PRICING_INITIAL_PERIOD || '1y';
const UPDATED_PERIOD = process.env.E2E_PRICING_UPDATED_PERIOD || '6mo';
const HEADLESS = process.env.PLAYWRIGHT_HEADLESS !== 'false';
const OUTPUT_DIR = path.resolve(__dirname, '../../output/playwright');
const FRONTEND_HEALTH_URL = `${FRONTEND_BASE_URL}/?view=pricing`;
const API_HEALTH_URL = `${API_BASE_URL}/health`;
const PERIOD_LABELS = {
  '6mo': '近6个月',
  '1y': '近1年',
  '2y': '近2年',
  '3y': '近3年',
};

const ensureDir = (dirPath) => {
  fs.mkdirSync(dirPath, { recursive: true });
};

const writeArtifact = async (page, filenamePrefix) => {
  ensureDir(OUTPUT_DIR);
  const screenshotPath = path.join(OUTPUT_DIR, `${filenamePrefix}.png`);
  const htmlPath = path.join(OUTPUT_DIR, `${filenamePrefix}.html`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  fs.writeFileSync(htmlPath, await page.content(), 'utf8');
  return { screenshotPath, htmlPath };
};

const assertOk = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

const getTaskIdFromPayload = (payload) =>
  payload?.data?.id
  || payload?.id
  || payload?.task_id
  || '';

const waitForJsonResponse = async (page, predicate, timeout = 180000) => {
  const response = await page.waitForResponse(predicate, { timeout });
  return response.json();
};

const clickWithRetry = async (locator, attempts = 3) => {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      await locator.waitFor({ state: 'visible', timeout: 30000 });
      await locator.click({ timeout: 30000 });
      return;
    } catch (error) {
      lastError = error;
      if (!String(error.message || error).includes('detached from the DOM') || attempt === attempts - 1) {
        throw error;
      }
    }
  }
  throw lastError;
};

const selectAntdOption = async (page, triggerSelector, optionText) => {
  const trigger = page.locator(triggerSelector);
  await trigger.waitFor({ state: 'visible', timeout: 30000 });
  await trigger.click();
  const option = page.locator('.ant-select-dropdown .ant-select-item-option-content').filter({ hasText: optionText }).last();
  await option.waitFor({ state: 'visible', timeout: 30000 });
  await option.click();
};

const waitForPricingReady = async (page, symbol) => {
  await page.locator('[data-testid="pricing-gap-overview"]').waitFor({ state: 'visible', timeout: 180000 });
  await page.locator('[data-testid="pricing-factor-card"]').waitFor({ state: 'visible', timeout: 180000 });
  await page.locator('[data-testid="pricing-implications-card"]').waitFor({ state: 'visible', timeout: 180000 });
  await page.waitForFunction(
    (expectedSymbol) => {
      const root = document.querySelector('[data-testid="pricing-gap-overview"]');
      return Boolean(root && root.textContent && root.textContent.includes(expectedSymbol));
    },
    symbol,
    { timeout: 180000 }
  );
};

const ensureServiceAvailable = async (request, url, name) => {
  const response = await request.get(url, { timeout: 30000 });
  assertOk(response.ok(), `${name} 不可用: ${url} (${response.status()})`);
};

(async () => {
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1200 },
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  let createdTaskId = '';

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.message || String(error));
  });

  try {
    console.log('检查前后端服务可用性...');
    await ensureServiceAvailable(context.request, FRONTEND_HEALTH_URL, '前端');
    await ensureServiceAvailable(context.request, API_HEALTH_URL, '后端');

    console.log(`打开定价研究页面并分析 ${SYMBOL}...`);
    await page.goto(`${FRONTEND_BASE_URL}/?view=pricing`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.locator('[data-testid="pricing-research-page"]').waitFor({ state: 'visible', timeout: 60000 });

    console.log('先运行候选池筛选并从结果进入深度分析...');
    await page.locator('[data-testid="pricing-screener-input"]').fill(SCREENING_UNIVERSE);
    const screenerResponse = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes('/pricing/screener')
        && response.request().method() === 'POST'
        && response.status() === 200
    );
    await page.locator('[data-testid="pricing-screener-run-button"]').click();
    const screenerPayload = await screenerResponse;
    assertOk((screenerPayload.results || []).length > 0, '候选池筛选未返回结果');
    await page.getByText('机会分', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    const screenerRow = page.locator('tr').filter({ hasText: SYMBOL }).first();
    await screenerRow.waitFor({ state: 'visible', timeout: 60000 });
    const screenerInspect = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes('/pricing/gap-analysis')
        && response.request().method() === 'POST'
        && response.status() === 200
    );
    await screenerRow.getByRole('button', { name: '深入分析' }).click();
    await screenerInspect;
    await waitForPricingReady(page, SYMBOL);

    await page.locator('[data-testid="pricing-symbol-input"]').fill(SYMBOL);
    await selectAntdOption(page, '[data-testid="pricing-period-select"]', PERIOD_LABELS[INITIAL_PERIOD] || '近1年');

    const firstAnalysis = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes('/pricing/gap-analysis')
        && response.request().method() === 'POST'
        && response.status() === 200
    );
    await page.locator('[data-testid="pricing-analyze-button"]').click();
    await firstAnalysis;
    await waitForPricingReady(page, SYMBOL);
    assertOk(
      await page.locator('[data-testid="pricing-implications-card"]').getByText('证据共振').isVisible(),
      '首次分析后未显示证据共振'
    );

    console.log('保存初始研究任务到工作台...');
    const createTaskPromise = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes('/research-workbench/tasks')
        && response.request().method() === 'POST'
        && !response.url().includes('/snapshot')
        && response.status() >= 200
        && response.status() < 300
    );
    await clickWithRetry(page.locator('[data-testid="research-playbook-save-task"]').last());
    const createTaskPayload = await createTaskPromise;
    createdTaskId = getTaskIdFromPayload(createTaskPayload);
    assertOk(createdTaskId, '未能从创建任务响应中读取 task id');
    await page.getByText('已保存到研究工作台', { exact: false }).waitFor({ state: 'visible', timeout: 30000 });

    console.log(`切换分析窗口到 ${UPDATED_PERIOD} 并更新快照...`);
    await selectAntdOption(page, '[data-testid="pricing-period-select"]', PERIOD_LABELS[UPDATED_PERIOD] || '近6个月');
    const secondAnalysis = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes('/pricing/gap-analysis')
        && response.request().method() === 'POST'
        && response.status() === 200
    );
    await page.locator('[data-testid="pricing-analyze-button"]').click();
    await secondAnalysis;
    await waitForPricingReady(page, SYMBOL);

    const snapshotPromise = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes(`/research-workbench/tasks/${encodeURIComponent(createdTaskId)}/snapshot`)
        && response.request().method() === 'POST'
        && response.status() >= 200
        && response.status() < 300
    );
    await clickWithRetry(page.locator('[data-testid="research-playbook-update-snapshot"]').last());
    const snapshotPayload = await snapshotPromise;
    assertOk(Boolean(snapshotPayload), '更新快照接口未返回响应体');
    await page.getByText('当前任务快照已更新', { exact: false }).waitFor({ state: 'visible', timeout: 30000 });

    console.log('进入研究工作台，检查快照历史与版本对比...');
    await page.goto(`${FRONTEND_BASE_URL}/?view=workbench&task=${encodeURIComponent(createdTaskId)}`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await page.getByRole('heading', { name: '研究工作台' }).waitFor({ state: 'visible', timeout: 60000 });
    await page.getByText('任务详情', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await page.locator(`[data-testid="workbench-task-card-${createdTaskId}"]`).waitFor({ state: 'visible', timeout: 60000 });
    const comparePanel = page.locator('[data-testid="workbench-snapshot-compare"]');
    await comparePanel.waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('Evidence Alignment', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('Analysis Window', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText(`基准 ${INITIAL_PERIOD}`, { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText(`目标 ${UPDATED_PERIOD}`, { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
    await page.getByText('证据共振', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });

    console.log('从工作台重新打开研究页，确认 symbol 和 period 恢复正确...');
    await page.locator('[data-testid="workbench-open-task"]').click();
    await page.waitForURL(
      (url) =>
        url.searchParams.get('view') === 'pricing'
        && url.searchParams.get('symbol') === SYMBOL
        && url.searchParams.get('period') === UPDATED_PERIOD
        && url.searchParams.get('source') === 'research_workbench',
      { timeout: 60000 }
    );
    await page.locator('[data-testid="pricing-research-page"]').waitFor({ state: 'visible', timeout: 60000 });
    await page.waitForFunction(
      (expectedSymbol) => {
        const input = document.querySelector('[data-testid="pricing-symbol-input"]');
        return (input?.value || '').trim().toUpperCase() === expectedSymbol;
      },
      SYMBOL,
      { timeout: 60000 }
    );
    await page.waitForFunction(
      (expectedLabel) => {
        const trigger = document.querySelector('[data-testid="pricing-period-select"]');
        return (trigger?.textContent || '').includes(expectedLabel);
      },
      PERIOD_LABELS[UPDATED_PERIOD] || '近6个月',
      { timeout: 60000 }
    );
    await waitForPricingReady(page, SYMBOL);

    assertOk(pageErrors.length === 0, `页面出现运行时异常: ${pageErrors.join(' | ')}`);

    const artifacts = await writeArtifact(page, 'pricing-research-e2e');
    console.log(`任务创建成功: ${createdTaskId}`);
    console.log(`控制台错误数: ${consoleErrors.length}`);
    console.log(`页面异常数: ${pageErrors.length}`);
    console.log(`截图: ${artifacts.screenshotPath}`);
    console.log(`HTML: ${artifacts.htmlPath}`);
    console.log('定价研究端到端回归通过。');
  } catch (error) {
    const artifacts = await writeArtifact(page, 'pricing-research-e2e-failure').catch(() => null);
    console.error('定价研究端到端回归失败:', error.message);
    if (artifacts) {
      console.error(`失败截图: ${artifacts.screenshotPath}`);
      console.error(`失败 HTML: ${artifacts.htmlPath}`);
    }
    if (consoleErrors.length) {
      console.error(`控制台错误(${consoleErrors.length}):`);
      console.error(consoleErrors.join('\n'));
    }
    if (pageErrors.length) {
      console.error(`页面异常(${pageErrors.length}):`);
      console.error(pageErrors.join('\n'));
    }
    process.exitCode = 1;
  } finally {
    if (createdTaskId) {
      await context.request.delete(`${API_BASE_URL}/research-workbench/tasks/${encodeURIComponent(createdTaskId)}`).catch(() => null);
    }
    await browser.close();
  }
})();
