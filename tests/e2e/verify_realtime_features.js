const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const ARTIFACT_DIR = path.join(PROJECT_ROOT, 'output', 'playwright');
const IMPORT_FIXTURE_PATH = path.join(ARTIFACT_DIR, 'realtime-import-snapshots.json');

const ensureArtifactDir = () => {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
};

const waitForRealtimeShell = async (page) => {
  await page.getByText('多市场看盘面板', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('.ant-tabs-tab-btn').filter({ hasText: '指数' }).first().waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('.realtime-quote-card').first().waitFor({ state: 'visible', timeout: 60000 });
};

const waitForQuoteCard = async (page, symbol) => {
  const card = page.locator('.realtime-quote-card').filter({ hasText: symbol }).first();
  await card.waitFor({ state: 'visible', timeout: 60000 });
  await card.scrollIntoViewIfNeeded();
  return card;
};

const closeVisibleModal = async (page) => {
  const closeButton = page.locator('.ant-modal-close').last();
  if (await closeButton.count()) {
    await closeButton.click();
    await page.waitForTimeout(300);
  }
};

const closeVisibleDrawer = async (page) => {
  const visibleDrawer = page.locator('.ant-drawer-content-wrapper:visible').last();
  if (await visibleDrawer.count()) {
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(300);
    if (await visibleDrawer.isVisible().catch(() => false)) {
      const mask = page.locator('.ant-drawer-mask:visible').last();
      if (await mask.count()) {
        await mask.click({ position: { x: 8, y: 8 }, force: true }).catch(() => {});
        await page.waitForTimeout(300);
      }
    }
    if (await visibleDrawer.isVisible().catch(() => false)) {
      const closeButton = page.locator('.ant-drawer-close:visible').last();
      if (await closeButton.count()) {
        await closeButton.scrollIntoViewIfNeeded().catch(() => {});
        await closeButton.click({ force: true }).catch(() => {});
        await page.waitForTimeout(300);
      }
    }
  }
};

(async () => {
  ensureArtifactDir();

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1480, height: 1100 });

  await page.addInitScript(() => {
    const seededProfileId = `rtp-e2e-${Date.now()}`;
    const defaultSymbols = [
      '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
      'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'BABA',
      '600519.SS', '601398.SS', '300750.SZ', '000858.SZ',
      'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'DOGE-USD',
      '^TNX', '^TYX', 'TLT',
      'GC=F', 'CL=F', 'SI=F',
      'SPY', 'QQQ', 'UVXY',
    ];

    window.__copiedTexts = [];
    const clipboard = {
      writeText: async (text) => {
        window.__copiedTexts.push(text);
      },
    };
    Object.defineProperty(navigator, 'clipboard', {
      value: clipboard,
      configurable: true,
    });
    window.localStorage.setItem('realtime-panel:profile-id', seededProfileId);
    window.localStorage.setItem('realtime-panel:symbols', JSON.stringify(defaultSymbols));
    window.localStorage.setItem('realtime-panel:active-tab', 'index');
    window.localStorage.setItem('realtime-panel:symbol-categories', JSON.stringify({}));
    window.localStorage.setItem('realtime-panel:diagnostics-enabled', '1');
    window.localStorage.setItem('realtime-review-snapshots', JSON.stringify([]));
    window.localStorage.setItem('realtime-timeline-events', JSON.stringify([]));
    window.localStorage.setItem('price_alerts', JSON.stringify([]));
    window.localStorage.setItem('realtime-alert-hit-history', JSON.stringify([
      {
        id: 'e2e-alert-hit-1',
        symbol: '^GSPC',
        condition: 'price_above',
        conditionLabel: '价格 ≥ $5100.00',
        threshold: 5100,
        triggerPrice: 5123.45,
        triggerTime: '2026-03-27T12:15:00.000Z',
        message: '^GSPC 当前价格 $5123.45 已突破 $5100.00',
        priceSnapshot: 5123.45,
      },
    ]));
  });

  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.message || String(error));
  });
  page.on('requestfailed', (request) => {
    failedRequests.push({
      url: request.url(),
      errorText: request.failure()?.errorText || '',
      method: request.method(),
    });
  });

  console.log('正在访问实时行情页面...');
  await page.goto('http://localhost:3000/?view=realtime', {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });
  await waitForRealtimeShell(page);
  await page.getByText('开发诊断', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  const showDiagnosticsButton = page.getByRole('button', { name: '显示诊断' });
  if (await showDiagnosticsButton.isVisible().catch(() => false)) {
    await showDiagnosticsButton.click();
  }
  const diagnosticsTrail = page.getByText('最近决策轨迹', { exact: true });
  if (!(await diagnosticsTrail.isVisible().catch(() => false))) {
    await page.getByText('开发诊断', { exact: true }).click();
  }
  await diagnosticsTrail.waitFor({ state: 'visible', timeout: 60000 });

  console.log('验证看盘面板列表模式与排序...');
  await page.getByRole('button', { name: '列表模式' }).click();
  await page.locator('.realtime-quote-card--list').first().waitFor({ state: 'visible', timeout: 60000 });
  await page.getByRole('button', { name: /代\s*码/ }).click();
  console.log('看盘面板列表模式与排序已生效: 是');

  console.log('验证默认指数视图...');
  const indexCard = await waitForQuoteCard(page, '^GSPC');
  const indexCardText = await indexCard.innerText();
  console.log(`指数卡片可见: ${indexCardText.includes('^GSPC') ? '是' : '否'}`);
  await page.getByText('提醒命中历史', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByRole('button', { name: '展开提醒命中历史' }).click();
  await page.getByText('价格 ≥ $5100.00', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('提醒命中历史已展示: 是');

  console.log('保存一条复盘快照...');
  await page.getByRole('button', { name: '保存快照' }).click();
  await page.getByRole('button', { name: '展开复盘快照' }).click();
  await page.getByRole('button', { name: '复制摘要' }).first().waitFor({ state: 'visible', timeout: 60000 });
  console.log('复盘快照已保存并展开: 是');

  console.log('验证复盘快照复制与 JSON 导出...');
  await page.getByRole('button', { name: '复制摘要' }).first().click();
  await page.getByRole('button', { name: '导出 JSON' }).click();
  const copiedTexts = await page.evaluate(() => window.__copiedTexts || []);
  const markdownCopy = copiedTexts.find((entry) => entry.includes('## 复盘快照 -'));
  const jsonCopy = copiedTexts.find((entry) => entry.includes('"spotlightSymbol"'));
  if (!markdownCopy || !jsonCopy) {
    throw new Error('复盘快照复制/导出未写入剪贴板');
  }
  console.log('复盘快照复制与 JSON 导出已生效: 是');

  console.log('验证复盘快照 JSON 导入...');
  fs.writeFileSync(
    IMPORT_FIXTURE_PATH,
    JSON.stringify([
      {
        id: 'e2e-imported-snapshot',
        createdAt: '2026-03-31T09:30:00.000Z',
        activeTab: 'crypto',
        activeTabLabel: '加密',
        spotlightSymbol: 'ETH-USD',
        spotlightName: 'ETH Imported',
        transportModeLabel: 'WebSocket 实时',
        watchedSymbols: ['ETH-USD', 'BTC-USD'],
        loadedCount: 2,
        totalCount: 5,
        anomalyCount: 1,
        anomalies: [
          {
            symbol: 'ETH-USD',
            title: '放量异动',
            description: 'ETH-USD 当前成交量显著放大。',
          },
        ],
        freshnessSummary: { fresh: 2, aging: 0, delayed: 0, pending: 0 },
        note: '导入的复盘快照',
        outcome: 'validated',
      },
    ], null, 2),
    'utf-8'
  );
  await page.locator('input[type="file"]').setInputFiles(IMPORT_FIXTURE_PATH);
  await page.getByText('ETH Imported · ETH-USD', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('复盘快照 JSON 导入已生效: 是');

  console.log('从导入快照打开焦点详情...');
  await page.getByRole('button', { name: '焦点详情' }).click();
  await page.getByText('当前分组：加密货币', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  const detailModal = page.locator('[data-testid="realtime-stock-detail-modal"]');
  await detailModal.waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('ETH-USD 全维分析', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('导入快照焦点详情已联动到正确分组: 是');
  await closeVisibleModal(page);

  console.log('验证全局跳转搜索...');
  const globalJumpInput = page.getByPlaceholder('全局搜索并跳转... (例如 AAPL / BTC-USD / 纳指)');
  await globalJumpInput.fill('BTC-USD');
  await globalJumpInput.press('Enter');
  await page.getByText('当前分组：加密货币', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('[data-testid="realtime-stock-detail-modal"]').waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('BTC-USD 全维分析', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('全局跳转已切组并打开详情: 是');
  await closeVisibleModal(page);

  console.log('打开指数详情，验证详情页新增模块...');
  await page.locator('.ant-tabs-tab-btn').filter({ hasText: '指数' }).first().click();
  await indexCard.click();
  await page.locator('[data-testid="realtime-stock-detail-modal"]').waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('信号总表', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('对比模式', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('盘中时间线', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('[data-testid="detail-compare-grid"]').waitFor({ state: 'visible', timeout: 60000 });
  const compareGridText = await page.locator('[data-testid="detail-compare-grid"]').innerText();
  console.log(`详情页对比模式已就绪: ${compareGridText.includes('^GSPC') ? '是' : '否'}`);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, 'realtime-detail.png'), fullPage: true });
  await closeVisibleModal(page);

  console.log('切换到美股分组，验证交易入口...');
  await globalJumpInput.fill('AAPL');
  await globalJumpInput.press('Enter');
  await page.getByText('当前分组：美股', { exact: false }).waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('[data-testid="realtime-stock-detail-modal"]').waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('AAPL 全维分析', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('验证详情页带入交易...');
  await page.getByRole('button', { name: '带入交易' }).click();
  await page.getByText('模拟交易终端', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('仓位建议', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('详情页一键带入交易已生效: 是');
  await closeVisibleModal(page);

  const usCard = page.locator('.realtime-quote-card:visible').first();
  await usCard.waitFor({ state: 'visible', timeout: 60000 });
  await usCard.getByRole('button', { name: '交易' }).click();
  await page.getByText('模拟交易终端', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('下单面板', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('交易弹窗已打开: 是');
  await page.screenshot({ path: path.join(ARTIFACT_DIR, 'realtime-trade-modal.png'), fullPage: true });
  await closeVisibleModal(page);

  console.log('验证提醒抽屉...');
  await usCard.getByRole('button', { name: '提醒' }).click();
  await page.locator('.ant-drawer-title').filter({ hasText: '价格提醒' }).first().waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('提醒规则管理', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  console.log('提醒抽屉已打开: 是');
  await closeVisibleDrawer(page);

  console.log('验证批量选择与删除...');
  await page.getByRole('button', { name: '全选当前分组' }).click();
  await page.getByRole('button', { name: '批量删除' }).click();
  await page.locator('.realtime-quote-card').filter({ hasText: 'AAPL' }).first().waitFor({ state: 'detached', timeout: 60000 });
  console.log('批量删除已生效: 是');

  const isRealtimeRelevantUrl = (url) => (
    url.includes('localhost:8000')
    && !url.includes('/industry/')
    && (
      url.includes('/realtime/')
      || url.includes('/analysis/')
      || url.includes('/trading/')
      || url.includes('/trade/')
      || url.includes('/ws/')
    )
  );
  const unexpectedConsoleErrors = consoleErrors.filter((entry) => (
    !entry.includes('API Network Error:')
    && !entry.includes('ERR_CONNECTION_RESET')
    && !entry.includes('ERR_CONNECTION_REFUSED')
  ));
  const relevantFailedRequests = failedRequests.filter((entry) => isRealtimeRelevantUrl(entry.url));

  if (unexpectedConsoleErrors.length > 0) {
    console.log(`浏览器 console error 数量: ${unexpectedConsoleErrors.length}`);
    unexpectedConsoleErrors.slice(0, 5).forEach((entry, index) => {
      console.log(`  [${index + 1}] ${entry}`);
    });
  }

  if (pageErrors.length > 0) {
    console.log(`浏览器 pageerror 数量: ${pageErrors.length}`);
    pageErrors.slice(0, 5).forEach((entry, index) => {
      console.log(`  [${index + 1}] ${entry}`);
    });
  }

  if (relevantFailedRequests.length > 0) {
    console.log(`实时相关 requestfailed 数量: ${relevantFailedRequests.length}`);
    relevantFailedRequests.slice(0, 10).forEach((entry, index) => {
      console.log(`  [${index + 1}] ${entry.method} ${entry.url} -> ${entry.errorText || 'unknown'}`);
    });
  }

  if (unexpectedConsoleErrors.length > 0 || pageErrors.length > 0 || relevantFailedRequests.length > 0) {
    throw new Error('检测到实时链路异常');
  }

  console.log('实时行情 E2E 回归通过');
  await browser.close();
})().catch(async (error) => {
  console.error('实时行情 E2E 回归失败:', error);
  process.exit(1);
});
