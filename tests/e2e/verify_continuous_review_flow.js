const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { partitionConsoleMessages } = require('./consoleNoise');

const FRONTEND_BASE_URL = process.env.E2E_FRONTEND_URL || 'http://127.0.0.1:3000';
const API_BASE_URL = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const HEADLESS = process.env.PLAYWRIGHT_HEADLESS !== 'false';
const OUTPUT_DIR = path.resolve(__dirname, '../../output/playwright');
const E2E_SOURCE = `e2e_continuous_review_${Date.now()}`;

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

const getTaskTitleFromPayload = (payload) =>
  payload?.data?.title
  || payload?.title
  || '';

const waitForJsonResponse = async (page, predicate, timeout = 180000) => {
  const response = await page.waitForResponse(predicate, { timeout });
  return response.json();
};

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
    await new Promise((resolve) => setTimeout(resolve, 1000));
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

const buildResearchUrlFromWorkbench = (page, overrides = {}) => {
  const currentUrl = new URL(page.url());
  const params = new URLSearchParams(currentUrl.searchParams);
  Object.entries(overrides).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      params.delete(key);
      return;
    }
    params.set(key, value);
  });
  return `${FRONTEND_BASE_URL}/?${params.toString()}`;
};

const openWorkbenchTask = async (page, taskId, waitForNavigation, fallbackUrlBuilder = null) => {
  const openButton = page.locator(`[data-testid="workbench-open-task"][data-task-id="${taskId}"]`);
  await openButton.waitFor({ state: 'visible', timeout: 30000 });
  try {
    await clickWithRetry(openButton);
    await waitForNavigation();
  } catch (error) {
    try {
      const pendingNavigation = waitForNavigation();
      await openButton.evaluate((node) => node.click());
      await pendingNavigation;
    } catch (fallbackError) {
      if (!fallbackUrlBuilder) {
        throw fallbackError;
      }
      await page.goto(fallbackUrlBuilder(), {
        waitUntil: 'domcontentloaded',
        timeout: 60000,
      });
      await waitForNavigation();
    }
  }
};

const waitForLocationMatch = async (page, matcher, timeout = 60000) => {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeout) {
    const currentUrl = new URL(page.url());
    if (matcher(currentUrl)) {
      return currentUrl;
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`等待 URL 匹配超时，最后停留在: ${page.url()}`);
};

const ensureServiceAvailable = async (request, url, name) => {
  const response = await request.get(url, { timeout: 30000 });
  assertOk(response.ok(), `${name} 不可用: ${url} (${response.status()})`);
};

const createTask = async (request, payload) => {
  const response = await request.post(`${API_BASE_URL}/research-workbench/tasks`, {
    data: payload,
    timeout: 30000,
  });
  assertOk(response.ok(), `创建任务失败: ${payload.title} (${response.status()})`);
  const body = await response.json();
  const taskId = body?.data?.id || '';
  assertOk(taskId, `创建任务后未返回 task id: ${payload.title}`);
  return { id: taskId, body };
};

const updateTask = async (request, taskId, payload) => {
  const response = await request.put(`${API_BASE_URL}/research-workbench/tasks/${encodeURIComponent(taskId)}`, {
    data: payload,
    timeout: 30000,
  });
  assertOk(response.ok(), `更新任务失败: ${taskId} (${response.status()})`);
  return response.json();
};

const buildPricingTaskPayload = (title, symbol, boardOrder) => ({
  type: 'pricing',
  title,
  status: 'new',
  source: E2E_SOURCE,
  symbol,
  board_order: boardOrder,
  context: {
    period: '1y',
    seeded_by: 'playwright_continuous_review',
  },
  snapshot: {
    headline: title,
    summary: `${symbol} 连续复盘测试任务`,
    highlights: [`symbol:${symbol}`, 'continuous-review'],
    payload: {
      period: '1y',
      implications: {
        primary_view: '观察',
      },
    },
    saved_at: new Date().toISOString(),
  },
});

const buildCrossTaskPayload = (title, template, boardOrder, options = {}) => ({
  type: 'cross_market',
  title,
  status: 'new',
  source: options.source || E2E_SOURCE,
  template,
  board_order: boardOrder,
  context: {
    seeded_by: 'playwright_continuous_review',
    ...(options.context || {}),
  },
  snapshot: {
    headline: title,
    summary: `${template} 连续复盘测试任务`,
    highlights: [`template:${template}`, 'continuous-review'],
    payload: {
      template_meta: {
        template_id: template,
      },
    },
    saved_at: new Date().toISOString(),
  },
});

const buildWorkbenchUrl = (type, taskId, options = {}) => {
  const sourceFilter = options.sourceFilter === undefined ? E2E_SOURCE : options.sourceFilter;
  const params = new URLSearchParams({
    view: 'workbench',
    task: taskId,
  });
  if (type) params.set('workbench_type', type);
  if (sourceFilter) params.set('workbench_source', sourceFilter);
  if (options.keyword) params.set('workbench_keyword', options.keyword);
  return `${FRONTEND_BASE_URL}/?${params.toString()}`;
};

const waitForWorkbenchTask = async (page, taskId, title) => {
  const taskCard = page.locator(`[data-testid="workbench-task-card-${taskId}"]`);
  await taskCard.waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText(title, { exact: false }).first().waitFor({ state: 'visible', timeout: 60000 });
  const detailPanel = page.locator(`[data-testid="workbench-detail-panel"][data-task-id="${taskId}"]`);
  const isSelected = await detailPanel.isVisible({ timeout: 3000 }).catch(() => false);
  if (!isSelected) {
    await taskCard.click();
  }
  await detailPanel.waitFor({ state: 'visible', timeout: 60000 });
  await page.locator(`[data-testid="workbench-open-task"][data-task-id="${taskId}"]`).waitFor({ state: 'visible', timeout: 60000 });
};

const waitForPricingOpen = async (page, taskId, symbol) => {
  await waitForLocationMatch(
    page,
    (url) =>
      url.searchParams.get('view') === 'pricing'
      && url.searchParams.get('symbol') === symbol
      && url.searchParams.get('source') === 'research_workbench'
      && url.searchParams.get('task') === taskId
      && url.searchParams.get('workbench_queue_mode') === 'pricing'
  );
  await page.locator('[data-testid="pricing-research-page"]').waitFor({ state: 'visible', timeout: 60000 });
  await page.getByRole('button', { name: '回到工作台下一条 Pricing 任务' }).waitFor({ state: 'visible', timeout: 60000 });
};

const waitForCrossMarketOpen = async (page, taskId, template) => {
  await waitForLocationMatch(
    page,
    (url) => {
      const resolvedView = url.searchParams.get('view') || 'backtest';
      return resolvedView === 'backtest'
      && url.searchParams.get('tab') === 'cross-market'
      && url.searchParams.get('template') === template
      && url.searchParams.get('source') === 'research_workbench'
      && url.searchParams.get('task') === taskId
      && url.searchParams.get('workbench_queue_mode') === 'cross_market';
    }
  );
  await page.getByRole('button', { name: '回到工作台下一条跨市场任务' }).waitFor({ state: 'visible', timeout: 60000 });
};

const waitForGodEyeCrossMarketOpen = async (page) => {
  const url = await waitForLocationMatch(
    page,
    (currentUrl) => {
      const resolvedView = currentUrl.searchParams.get('view') || 'backtest';
      return resolvedView === 'backtest'
        && currentUrl.searchParams.get('tab') === 'cross-market'
        && String(currentUrl.searchParams.get('source') || '').startsWith('godeye_');
    },
  );
  await page.locator('[data-testid="research-playbook-save-task"]').waitFor({ state: 'visible', timeout: 60000 });
  return {
    template: url.searchParams.get('template') || '',
    source: url.searchParams.get('source') || '',
  };
};

const updateSnapshotAndContinue = async ({
  continueButtonLabel,
  page,
  request,
  taskId,
  taskLabel,
}) => {
  const updateSnapshotButton = page.locator('[data-testid="research-playbook-update-snapshot"]').last();
  await updateSnapshotButton.waitFor({ state: 'visible', timeout: 60000 });
  await page.waitForFunction(
    () => {
      const button = document.querySelector('[data-testid="research-playbook-update-snapshot"]');
      return Boolean(button) && !button.disabled;
    },
    { timeout: 60000 }
  );

  const snapshotPromise = waitForJsonResponse(
    page,
    (response) =>
      response.url().includes(`/research-workbench/tasks/${encodeURIComponent(taskId)}/snapshot`)
      && response.request().method() === 'POST'
      && response.status() >= 200
      && response.status() < 300
  );
  await clickWithRetry(updateSnapshotButton);
  const snapshotPayload = await snapshotPromise;
  assertOk(Boolean(snapshotPayload), `${taskLabel} 更新快照接口未返回响应体`);
  await page.getByText('当前任务快照已更新', { exact: false }).waitFor({ state: 'visible', timeout: 30000 });
  await waitForTaskSnapshotCount(request, taskId, 2, 60000);
  const continueButton = page.getByRole('button', { name: continueButtonLabel });
  await continueButton.waitFor({ state: 'visible', timeout: 30000 });
  await continueButton.click();
};

const waitForWorkbenchQueueAdvance = async (page, taskId, type, title, options = {}) => {
  const sourceFilter = options.sourceFilter === undefined ? E2E_SOURCE : options.sourceFilter;
  await waitForLocationMatch(
    page,
    (url) =>
      url.searchParams.get('view') === 'workbench'
      && (!type || url.searchParams.get('workbench_type') === type)
      && (!sourceFilter || url.searchParams.get('workbench_source') === sourceFilter)
      && (!options.keyword || url.searchParams.get('workbench_keyword') === options.keyword)
      && url.searchParams.get('task') === taskId
      && !url.searchParams.get('workbench_queue_action')
  );
  await waitForWorkbenchTask(page, taskId, title);
};

const navigateToGodEyeCrossMarket = async (page) => {
  await page.goto(`${FRONTEND_BASE_URL}/?view=godsEye`, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await page.getByText('GodEye V2 作战大屏', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  const peoplePanel = page.locator('.ant-card').filter({
    has: page.getByText('People Layer Watchlist', { exact: true }),
  }).first();
  const peopleCrossButton = peoplePanel.getByRole('button', { name: '跨市场' }).first();
  if (await peopleCrossButton.isVisible({ timeout: 5000 }).catch(() => false)) {
    await peopleCrossButton.click();
    return waitForGodEyeCrossMarketOpen(page);
  }

  const chaosPanel = page.locator('.ant-card').filter({
    has: page.getByText('Department Chaos Board', { exact: true }),
  }).first();
  const policyTemplateButton = chaosPanel.getByRole('button', { name: '政策模板' }).first();
  await policyTemplateButton.waitFor({ state: 'visible', timeout: 30000 });
  await policyTemplateButton.click();
  return waitForGodEyeCrossMarketOpen(page);
};

const logWorkbenchSelection = async (page, label) => {
  const detailTaskId = await page.locator('[data-testid="workbench-detail-panel"]').getAttribute('data-task-id').catch(() => '');
  const openTaskId = await page.locator('[data-testid="workbench-open-task"]').getAttribute('data-task-id').catch(() => '');
  console.log(`${label}: currentUrl=${page.url()} detailTaskId=${detailTaskId || '-'} openTaskId=${openTaskId || '-'}`);
};

(async () => {
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1200 },
  });
  const page = await context.newPage();
  const createdTaskIds = [];
  const consoleErrors = [];
  const pageErrors = [];

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
    await ensureServiceAvailable(context.request, `${FRONTEND_BASE_URL}/?view=workbench`, '前端');
    await ensureServiceAvailable(context.request, `${API_BASE_URL}/health`, '后端');

    console.log('预置连续复盘队列任务...');
    const pricingTaskOne = await createTask(
      context.request,
      buildPricingTaskPayload('E2E Pricing Queue 1', 'AAPL', 0),
    );
    const pricingTaskTwo = await createTask(
      context.request,
      buildPricingTaskPayload('E2E Pricing Queue 2', 'NVDA', 1),
    );
    createdTaskIds.push(pricingTaskOne.id, pricingTaskTwo.id);
    console.log(`任务队列: pricing#1=${pricingTaskOne.id}, pricing#2=${pricingTaskTwo.id}`);

    console.log('验证 Pricing 连续复盘链路...');
    await page.goto(buildWorkbenchUrl('pricing', pricingTaskOne.id), {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await page.getByRole('heading', { name: '研究工作台' }).waitFor({ state: 'visible', timeout: 60000 });
    await waitForWorkbenchTask(page, pricingTaskOne.id, 'E2E Pricing Queue 1');
    await openWorkbenchTask(
      page,
      pricingTaskOne.id,
      () => waitForPricingOpen(page, pricingTaskOne.id, 'AAPL'),
      () => buildResearchUrlFromWorkbench(page, {
        view: 'pricing',
        symbol: 'AAPL',
        source: 'research_workbench',
        task: pricingTaskOne.id,
      }),
    );
    await updateSnapshotAndContinue({
      continueButtonLabel: '完成当前复盘并继续下一条',
      page,
      request: context.request,
      taskId: pricingTaskOne.id,
      taskLabel: 'Pricing 队列首条任务',
    });
    await logWorkbenchSelection(page, 'Pricing 返回工作台后');
    await waitForWorkbenchQueueAdvance(page, pricingTaskTwo.id, 'pricing', 'E2E Pricing Queue 2');
    await openWorkbenchTask(
      page,
      pricingTaskTwo.id,
      () => waitForPricingOpen(page, pricingTaskTwo.id, 'NVDA'),
      () => buildResearchUrlFromWorkbench(page, {
        view: 'pricing',
        symbol: 'NVDA',
        source: 'research_workbench',
        task: pricingTaskTwo.id,
      }),
    );

    console.log('验证 GodEye -> Cross-Market -> Workbench 连续复盘链路...');
    const godEyeNavigation = await navigateToGodEyeCrossMarket(page);
    console.log(`GodEye 已导航到跨市场模板: template=${godEyeNavigation.template || '-'} source=${godEyeNavigation.source || '-'}`);
    const saveTaskPromise = waitForJsonResponse(
      page,
      (response) =>
        response.url().includes('/research-workbench/tasks')
        && response.request().method() === 'POST'
        && !response.url().includes('/snapshot')
        && response.status() >= 200
        && response.status() < 300,
    );
    await clickWithRetry(page.locator('[data-testid="research-playbook-save-task"]').last());
    const godEyeSavedTaskPayload = await saveTaskPromise;
    const godEyeCrossTaskId = getTaskIdFromPayload(godEyeSavedTaskPayload);
    const godEyeCrossTaskTitle = getTaskTitleFromPayload(godEyeSavedTaskPayload) || 'GodEye Cross Queue 1';
    assertOk(godEyeCrossTaskId, 'GodEye 导航后的跨市场任务未成功保存到工作台');
    createdTaskIds.push(godEyeCrossTaskId);
    console.log(`GodEye 首条跨市场任务已保存: ${godEyeCrossTaskId}`);
    await page.getByText('已保存到研究工作台', { exact: false }).waitFor({ state: 'visible', timeout: 30000 });
    await updateTask(context.request, godEyeCrossTaskId, {
      title: `${godEyeCrossTaskTitle} ${E2E_SOURCE}`,
      note: `playwright-godeye-queue ${E2E_SOURCE}`,
      board_order: 0,
    });

    const crossTaskTwo = await createTask(
      context.request,
      buildCrossTaskPayload(`E2E Cross Queue 2 ${E2E_SOURCE}`, godEyeNavigation.template || 'defensive_beta_hedge', 1, {
        source: godEyeNavigation.source || E2E_SOURCE,
        context: {
          seeded_from: 'godeye_follow_up',
        },
      }),
    );
    createdTaskIds.push(crossTaskTwo.id);
    console.log(`GodEye 连续复盘第二条任务已预置: ${crossTaskTwo.id}`);

    await page.goto(buildWorkbenchUrl('cross_market', godEyeCrossTaskId, { sourceFilter: '', keyword: E2E_SOURCE }), {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await page.getByRole('heading', { name: '研究工作台' }).waitFor({ state: 'visible', timeout: 60000 });
    await waitForWorkbenchTask(page, godEyeCrossTaskId, E2E_SOURCE);
    console.log(`工作台已定位到 GodEye 首条任务: ${godEyeCrossTaskId}`);
    await openWorkbenchTask(
      page,
      godEyeCrossTaskId,
      () => waitForCrossMarketOpen(page, godEyeCrossTaskId, godEyeNavigation.template || 'defensive_beta_hedge'),
      () => buildResearchUrlFromWorkbench(page, {
        view: 'backtest',
        tab: 'cross-market',
        template: godEyeNavigation.template || 'defensive_beta_hedge',
        source: 'research_workbench',
        task: godEyeCrossTaskId,
      }),
    );
    console.log(`GodEye 首条任务已重新打开到跨市场研究页: ${godEyeCrossTaskId}`);
    await updateSnapshotAndContinue({
      continueButtonLabel: '完成当前复盘并继续下一条',
      page,
      request: context.request,
      taskId: godEyeCrossTaskId,
      taskLabel: 'GodEye Cross-Market 队列首条任务',
    });
    console.log(`GodEye 首条任务完成后已返回工作台，验证同一连续复盘视图仍然保留并切入下一条: ${crossTaskTwo.id}`);
    await waitForLocationMatch(
      page,
      (url) =>
        url.searchParams.get('view') === 'workbench'
        && url.searchParams.get('workbench_type') === 'cross_market'
        && url.searchParams.get('workbench_keyword') === E2E_SOURCE
        && url.searchParams.get('workbench_queue_mode') === 'cross_market',
    );
    await waitForWorkbenchTask(page, crossTaskTwo.id, `E2E Cross Queue 2 ${E2E_SOURCE}`);
    console.log(`GodEye 队列第二条任务已经出现在当前连续复盘视图中: ${crossTaskTwo.id}`);
    await openWorkbenchTask(
      page,
      crossTaskTwo.id,
      () => waitForCrossMarketOpen(page, crossTaskTwo.id, godEyeNavigation.template || 'defensive_beta_hedge'),
      () => buildResearchUrlFromWorkbench(page, {
        view: 'backtest',
        tab: 'cross-market',
        template: godEyeNavigation.template || 'defensive_beta_hedge',
        source: 'research_workbench',
        task: crossTaskTwo.id,
      }),
    );
    console.log(`GodEye 队列第二条任务已重新打开到跨市场研究页: ${crossTaskTwo.id}`);

    const consoleSummary = partitionConsoleMessages(consoleErrors);
    assertOk(
      consoleSummary.unknown.length === 0,
      `页面出现未知控制台错误: ${consoleSummary.unknown.join(' | ')}`
    );
    assertOk(pageErrors.length === 0, `页面出现运行时异常: ${pageErrors.join(' | ')}`);

    const artifacts = await writeArtifact(page, 'continuous-review-e2e');
    console.log(`连续复盘 E2E 通过，已创建并验证任务 ${createdTaskIds.join(', ')}`);
    console.log(`控制台错误数: ${consoleErrors.length}（已知噪音 ${consoleSummary.ignored.length} / 未知 ${consoleSummary.unknown.length}）`);
    if (consoleSummary.ignoredSummary.length) {
      console.log(`已知控制台噪音: ${consoleSummary.ignoredSummary.map((item) => `${item.label} × ${item.count}`).join('；')}`);
    }
    console.log(`页面异常数: ${pageErrors.length}`);
    console.log(`截图: ${artifacts.screenshotPath}`);
    console.log(`HTML: ${artifacts.htmlPath}`);
  } catch (error) {
    const artifacts = await writeArtifact(page, 'continuous-review-e2e-failure').catch(() => null);
    console.error('连续复盘 E2E 失败:', error.message);
    await logWorkbenchSelection(page, '失败现场').catch(() => null);
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
    for (const taskId of createdTaskIds) {
      await context.request.delete(`${API_BASE_URL}/research-workbench/tasks/${encodeURIComponent(taskId)}`).catch(() => null);
    }
    await browser.close();
  }
})();
