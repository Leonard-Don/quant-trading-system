const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { partitionConsoleMessages } = require('./consoleNoise');

const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const ARTIFACT_DIR = path.join(PROJECT_ROOT, 'output', 'playwright');
const SCREENSHOT_PATH = path.join(ARTIFACT_DIR, 'today-research.png');
const APP_URL = process.env.FRONTEND_URL || 'http://localhost:3000';

const ensureArtifactDir = () => {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
};

const assert = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

(async () => {
  ensureArtifactDir();

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1040 } });
  const consoleErrors = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    consoleErrors.push(error.message);
  });

  await page.addInitScript(() => {
    window.localStorage.clear();
    window.localStorage.setItem('realtime-panel:profile-id', 'e2e-today-research');
    window.localStorage.setItem('backtest_research_snapshots', JSON.stringify([
      {
        id: 'bt-e2e',
        created_at: '2026-05-02T09:00:00.000Z',
        symbol: 'AAPL',
        strategy: 'buy_and_hold',
        note: 'E2E 回测快照',
        metrics: {
          total_return: 0.12,
          max_drawdown: -0.05,
          sharpe_ratio: 1.1,
          num_trades: 1,
        },
      },
    ]));
    window.localStorage.setItem('realtime-review-snapshots', JSON.stringify([
      {
        id: 'review-e2e',
        createdAt: '2026-05-02T10:00:00.000Z',
        spotlightSymbol: 'MSFT',
        spotlightName: 'Microsoft',
        activeTabLabel: '美股',
        outcome: 'pending',
        note: 'E2E 复盘快照',
      },
    ]));
    window.localStorage.setItem('realtime-timeline-events', JSON.stringify([
      {
        id: 'plan-e2e',
        kind: 'trade_plan',
        symbol: 'NVDA',
        title: 'NVDA 买入计划',
        description: '等待入场提醒',
        createdAt: '2026-05-02T11:00:00.000Z',
      },
    ]));
    window.localStorage.setItem('realtime-alert-hit-history', JSON.stringify([
      {
        id: 'hit-e2e',
        symbol: 'BTC-USD',
        message: 'BTC 提醒命中',
        triggerTime: '2026-05-02T12:00:00.000Z',
      },
    ]));
    window.localStorage.setItem('industry_watchlist_v1', JSON.stringify(['半导体']));
    window.localStorage.setItem('industry_alert_history_v1', JSON.stringify({
      semiconductor: {
        industry_name: '半导体',
        message: '半导体资金共振',
        hitCount: 2,
        priority: 120,
        firstSeenAt: Date.parse('2026-05-02T13:00:00.000Z'),
        lastSeenAt: Date.parse('2026-05-02T13:10:00.000Z'),
      },
    }));
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (text) => {
          window.__todayResearchCopiedText = text;
        },
      },
    });
  });

  console.log('正在访问今日研究页面...');
  await page.goto(`${APP_URL}/?view=today`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.getByRole('heading', { name: '今日研究' }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('处理队列', { exact: true }).waitFor({ state: 'visible', timeout: 60000 });
  await page.getByTestId('today-research-entry').first().waitFor({ state: 'visible', timeout: 60000 });

  const entries = await page.getByTestId('today-research-entry').count();
  assert(entries >= 6, `今日研究档案条目过少: ${entries}`);
  await page.getByText('AAPL · buy_and_hold 回测', { exact: false }).first().waitFor({ state: 'visible', timeout: 60000 });
  await page.getByText('半导体 · 行业观察', { exact: true }).first().waitFor({ state: 'visible', timeout: 60000 });
  console.log('本地研究状态已汇总到今日研究: 是');

  console.log('验证手动研究记录...');
  await page.getByLabel('标题').fill('E2E 手动研究记录');
  await page.getByLabel('标的').fill('TSLA');
  await page.getByLabel('摘要').fill('继续观察开盘强度');
  await page.getByLabel('记录').fill('盘前先看提醒，再决定是否带入回测。');
  await page.getByRole('button', { name: '加入研究档案' }).click();
  await page.getByText('E2E 手动研究记录', { exact: true }).first().waitFor({ state: 'visible', timeout: 60000 });
  console.log('手动研究记录已写入档案: 是');

  console.log('验证备份导出...');
  await page.getByRole('button', { name: '导出备份' }).click();
  await page.waitForFunction(() => {
    const copied = window.__todayResearchCopiedText || '';
    return copied.includes('"journal"') && copied.includes('E2E 手动研究记录');
  }, null, { timeout: 10000 });
  console.log('研究档案备份导出已生效: 是');

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
  console.log('今日研究 E2E 回归通过');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
