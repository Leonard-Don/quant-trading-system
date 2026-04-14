const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { partitionConsoleMessages } = require('./consoleNoise');

const FRONTEND_BASE_URL = process.env.E2E_FRONTEND_URL || 'http://127.0.0.1:3000';
const API_BASE_URL = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const SYMBOL = String(process.env.E2E_PRICING_SYMBOL || 'AAPL').trim().toUpperCase();
const SCREENING_UNIVERSE = process.env.E2E_PRICING_UNIVERSE || `${SYMBOL}\nMSFT\nNVDA`;
const INITIAL_PERIOD = process.env.E2E_PRICING_INITIAL_PERIOD || '1y';
const UPDATED_PERIOD = process.env.E2E_PRICING_UPDATED_PERIOD || '6mo';
const WORKBENCH_REFRESH = process.env.E2E_WORKBENCH_REFRESH || 'high';
const WORKBENCH_TYPE = process.env.E2E_WORKBENCH_TYPE || 'pricing';
const WORKBENCH_SOURCE = process.env.E2E_WORKBENCH_SOURCE || 'pricing_playbook';
const WORKBENCH_REASON = process.env.E2E_WORKBENCH_REASON || 'priority_escalated';
const WORKBENCH_SNAPSHOT_VIEW = process.env.E2E_WORKBENCH_SNAPSHOT_VIEW || 'filtered';
const WORKBENCH_SNAPSHOT_FINGERPRINT = process.env.E2E_WORKBENCH_SNAPSHOT_FINGERPRINT || 'wv_pricing_e2e_focus';
const WORKBENCH_SNAPSHOT_SUMMARY = process.env.E2E_WORKBENCH_SNAPSHOT_SUMMARY || '快速视图：自动排序升档 · 类型：Pricing';
const WORKBENCH_KEYWORD = process.env.E2E_WORKBENCH_KEYWORD || 'hedge';
const PRICING_SOURCE = process.env.E2E_PRICING_SOURCE || WORKBENCH_SOURCE;
const PRICING_NOTE = process.env.E2E_PRICING_NOTE || 'playwright_e2e_workbench_context';
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

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const getTaskIdFromPayload = (payload) =>
  payload?.data?.id
  || payload?.id
  || payload?.task_id
  || '';

const getTaskSnapshotViewContext = (payload) =>
  payload?.data?.snapshot?.payload?.view_context
  || payload?.snapshot?.payload?.view_context
  || {};

const buildPricingUrl = () => {
  const params = new URLSearchParams({
    view: 'pricing',
    source: PRICING_SOURCE,
    note: PRICING_NOTE,
    workbench_refresh: WORKBENCH_REFRESH,
    workbench_type: WORKBENCH_TYPE,
    workbench_source: WORKBENCH_SOURCE,
    workbench_reason: WORKBENCH_REASON,
    workbench_snapshot_view: WORKBENCH_SNAPSHOT_VIEW,
    workbench_snapshot_fingerprint: WORKBENCH_SNAPSHOT_FINGERPRINT,
    workbench_snapshot_summary: WORKBENCH_SNAPSHOT_SUMMARY,
    workbench_keyword: WORKBENCH_KEYWORD,
  });
  return `${FRONTEND_BASE_URL}/?${params.toString()}`;
};

const buildWorkbenchUrl = (taskId) => {
  const params = new URLSearchParams({
    view: 'workbench',
    task: taskId,
    workbench_type: WORKBENCH_TYPE,
    workbench_source: WORKBENCH_SOURCE,
    workbench_snapshot_view: WORKBENCH_SNAPSHOT_VIEW,
    workbench_snapshot_fingerprint: WORKBENCH_SNAPSHOT_FINGERPRINT,
    workbench_snapshot_summary: WORKBENCH_SNAPSHOT_SUMMARY,
  });
  return `${FRONTEND_BASE_URL}/?${params.toString()}`;
};

const assertSnapshotViewContext = (taskPayload, stageLabel) => {
  const viewContext = getTaskSnapshotViewContext(taskPayload);
  assertOk(
    viewContext.view_fingerprint === WORKBENCH_SNAPSHOT_FINGERPRINT,
    `${stageLabel} 未写入稳定视图指纹`
  );
  assertOk(
    viewContext.snapshot_summary === WORKBENCH_SNAPSHOT_SUMMARY,
    `${stageLabel} 未写入研究视角摘要`
  );
  assertOk(
    String(viewContext.summary || '').includes(WORKBENCH_KEYWORD),
    `${stageLabel} 未保留工作台关键词上下文`
  );
};

const waitForJsonResponse = async (page, predicate, timeout = 180000) => {
  const response = await page.waitForResponse(predicate, { timeout });
  return response.json();
};

const waitForRequest = async (page, predicate, timeout = 180000) => (
  page.waitForRequest(predicate, { timeout })
);

const waitForTaskSnapshotCount = async (request, taskId, expectedCount, timeout = 60000) => {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeout) {
    const response = await request.get(`${API_BASE_URL}/research-workbench/tasks/${encodeURIComponent(taskId)}`, {
      timeout: 30000,
    });
    if (response.ok()) {
      const payload = await response.json();
      const history = payload?.data?.snapshot_history || [];
      if (history.length >= expectedCount) {
        return payload;
      }
    }
    await sleep(1000);
  }
  throw new Error(`任务 ${taskId} 的快照数量在 ${timeout}ms 内未达到 ${expectedCount}`);
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

const clickUntilRequest = async (page, locator, predicate, timeout = 30000) => {
  try {
    await Promise.all([
      waitForRequest(page, predicate, timeout),
      clickWithRetry(locator),
    ]);
    return;
  } catch (error) {
    const requestAfterFallback = waitForRequest(page, predicate, timeout);
    await locator.evaluate((node) => node.click());
    await requestAfterFallback;
  }
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
  await page.locator('[data-testid="pricing-people-layer-card"]').waitFor({ state: 'visible', timeout: 180000 });
  await page.waitForFunction(
    (expectedSymbol) => {
      const root = document.querySelector('[data-testid="pricing-gap-overview"]');
      return Boolean(root && root.textContent && root.textContent.includes(expectedSymbol));
    },
    symbol,
    { timeout: 180000 }
  );
};

const waitForSymbolInputValue = async (page, expectedSymbol, timeout = 60000) => {
  await page.waitForFunction(
    (symbol) => {
      const input = document.querySelector('[data-testid="pricing-symbol-input"]');
      return Boolean(input && String(input.value || '').trim().toUpperCase() === symbol);
    },
    expectedSymbol,
    { timeout }
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
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: FRONTEND_BASE_URL });
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
    await page.goto(buildPricingUrl(), { waitUntil: 'domcontentloaded', timeout: 60000 });
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
    const screenerRow = page.locator(`[data-testid="pricing-screener-results"] tr[data-row-key="${SYMBOL}"]`).first();
    await screenerRow.waitFor({ state: 'visible', timeout: 60000 });
    const gapAnalysisRequestMatcher = (request) =>
      request.url().includes('/pricing/gap-analysis')
      && request.method() === 'POST';
    const inspectButton = page.locator(`[data-testid="pricing-screener-inspect-${SYMBOL}"]`).first();
    await inspectButton.scrollIntoViewIfNeeded();
    await clickUntilRequest(page, inspectButton, gapAnalysisRequestMatcher, 30000);
    await waitForSymbolInputValue(page, SYMBOL);
    await waitForPricingReady(page, SYMBOL);

    console.log('确认深入分析结果页的治理折扣卡与主分析区都已就绪...');
    await page
      .locator('[data-testid="pricing-implications-card"]')
      .getByText('证据共振')
      .first()
      .waitFor({ state: 'visible', timeout: 60000 });
    await page.locator('[data-testid="pricing-people-layer-card"]').getByText('人的维度 / 治理折扣', { exact: true }).waitFor({
      state: 'visible',
      timeout: 60000,
    });
    await page.locator('[data-testid="pricing-people-layer-card"]').getByText('来源治理', { exact: false }).waitFor({
      state: 'visible',
      timeout: 60000,
    });
    await page.locator('[data-testid="pricing-people-layer-card"]').getByText('政策执行上下文', { exact: true }).waitFor({
      state: 'visible',
      timeout: 60000,
    });

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
    const createdTaskDetail = await waitForTaskSnapshotCount(context.request, createdTaskId, 1, 30000);
    assertSnapshotViewContext(createdTaskDetail, '初始保存');
    console.log(`初始任务已落库，当前快照数: ${(createdTaskDetail?.data?.snapshot_history || []).length}`);

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
    const updateSnapshotButton = page.locator('[data-testid="research-playbook-update-snapshot"]').last();
    await updateSnapshotButton.waitFor({ state: 'visible', timeout: 30000 });
    await page.waitForFunction(
      () => {
        const button = document.querySelector('[data-testid="research-playbook-update-snapshot"]');
        return Boolean(button) && !button.disabled;
      },
      { timeout: 30000 }
    );

    const snapshotPromise = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes(`/research-workbench/tasks/${encodeURIComponent(createdTaskId)}/snapshot`)
        && response.request().method() === 'POST'
        && response.status() >= 200
        && response.status() < 300
    );
    console.log('点击更新当前任务快照...');
    await clickWithRetry(updateSnapshotButton);
    const snapshotPayload = await snapshotPromise;
    assertOk(Boolean(snapshotPayload), '更新快照接口未返回响应体');
    await page.getByText('当前任务快照已更新', { exact: false }).waitFor({ state: 'visible', timeout: 30000 });
    const updatedTaskDetail = await waitForTaskSnapshotCount(context.request, createdTaskId, 2, 60000);
    assertSnapshotViewContext(updatedTaskDetail, '快照更新');
    console.log(`快照更新完成，当前快照数: ${(updatedTaskDetail?.data?.snapshot_history || []).length}`);

    console.log('进入研究工作台，检查按稳定视图指纹恢复的复盘队列...');
    await page.goto(buildWorkbenchUrl(createdTaskId), {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await page.getByRole('heading', { name: '研究工作台' }).waitFor({ state: 'visible', timeout: 60000 });
    await page.getByText('任务详情', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await page.locator(`[data-testid="workbench-task-card-${createdTaskId}"]`).waitFor({ state: 'visible', timeout: 60000 });
    await page.getByText('当前共享视图上下文', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await page.getByText(`研究视角：${WORKBENCH_SNAPSHOT_SUMMARY}`, { exact: false }).first().waitFor({
      state: 'visible',
      timeout: 60000,
    });
    await page.getByText(`最近快照视角 ${getTaskSnapshotViewContext(updatedTaskDetail).summary}`, { exact: false }).first().waitFor({
      state: 'visible',
      timeout: 60000,
    });
    const comparePanel = page.locator('[data-testid="workbench-snapshot-compare"]');
    await comparePanel.waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('版本对比', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('Evidence Alignment', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('Analysis Window', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('Governance Overlay', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('Policy Execution', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText('Source Mode', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText(`基准 ${INITIAL_PERIOD}`, { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
    await comparePanel.getByText(`目标 ${UPDATED_PERIOD}`, { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
    await page.getByText('证据共振', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
    console.log('验证复制当前视图链接会保留稳定视图指纹...');
    await page.getByRole('button', { name: '复制当前视图链接' }).first().click();
    await page.getByText('当前工作台视图链接已复制', { exact: false }).waitFor({ state: 'visible', timeout: 30000 });
    const copiedUrl = await page.evaluate(() => navigator.clipboard.readText());
    const copiedUrlParams = new URL(copiedUrl).searchParams;
    assertOk(copiedUrlParams.get('workbench_snapshot_fingerprint') === WORKBENCH_SNAPSHOT_FINGERPRINT, '复制链接未保留稳定视图指纹');
    assertOk(copiedUrlParams.get('workbench_snapshot_summary') === WORKBENCH_SNAPSHOT_SUMMARY, '复制链接未保留研究视角摘要');
    console.log('工作台版本对比已显示。');

    console.log('从工作台重新打开研究页，确认 symbol、period 和工作台视图上下文一并恢复...');
    await page.locator('[data-testid="workbench-open-task"]').click();
    await page.waitForURL(
      (url) =>
        url.searchParams.get('view') === 'pricing'
        && url.searchParams.get('symbol') === SYMBOL
        && url.searchParams.get('period') === UPDATED_PERIOD
        && url.searchParams.get('source') === 'research_workbench'
        && url.searchParams.get('workbench_snapshot_fingerprint') === WORKBENCH_SNAPSHOT_FINGERPRINT
        && url.searchParams.get('workbench_snapshot_summary') === WORKBENCH_SNAPSHOT_SUMMARY,
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

    const consoleSummary = partitionConsoleMessages(consoleErrors);
    assertOk(
      consoleSummary.unknown.length === 0,
      `页面出现未知控制台错误: ${consoleSummary.unknown.join(' | ')}`
    );
    assertOk(pageErrors.length === 0, `页面出现运行时异常: ${pageErrors.join(' | ')}`);

    const artifacts = await writeArtifact(page, 'pricing-research-e2e');
    console.log(`任务创建成功: ${createdTaskId}`);
    console.log(`控制台错误数: ${consoleErrors.length}（已知噪音 ${consoleSummary.ignored.length} / 未知 ${consoleSummary.unknown.length}）`);
    if (consoleSummary.ignoredSummary.length) {
      console.log(`已知控制台噪音: ${consoleSummary.ignoredSummary.map((item) => `${item.label} × ${item.count}`).join('；')}`);
    }
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
      const consoleSummary = partitionConsoleMessages(consoleErrors);
      if (consoleSummary.unknown.length) {
        console.error(consoleSummary.unknown.join('\n'));
      } else {
        console.error(consoleErrors.join('\n'));
      }
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
