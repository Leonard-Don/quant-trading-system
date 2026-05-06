// Quick layout snapshot script — captures the four main workspaces
// at desktop breakpoint and dumps PNGs into tmp/snapshots/.
//
// Run from tests/e2e/:
//   node snapshot_layouts.js
//
// Output: <repo>/tmp/snapshots/0[1-4]-*.png

const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const OUT_DIR = path.join(REPO_ROOT, 'tmp', 'snapshots');

const VIEWS = [
  { name: '01-today',     url: 'http://localhost:3000?view=today' },
  { name: '02-backtest',  url: 'http://localhost:3000' },
  { name: '03-realtime',  url: 'http://localhost:3000?view=realtime' },
  { name: '04-industry',  url: 'http://localhost:3000?view=industry' },
];

(async () => {
  await fs.mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: 'zh-CN',
    ignoreHTTPSErrors: true,
  });

  const errors = {};
  for (const v of VIEWS) {
    errors[v.name] = [];
    const page = await context.newPage();
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors[v.name].push(msg.text());
    });
    page.on('pageerror', (err) => errors[v.name].push(`pageerror: ${err.message}`));

    try {
      await page.goto(v.url, { waitUntil: 'networkidle', timeout: 25_000 });
    } catch (err) {
      console.log(`[${v.name}] goto warn: ${err.message}`);
    }
    await page.waitForTimeout(2500);
    const out = path.join(OUT_DIR, `${v.name}.png`);
    await page.screenshot({ path: out, fullPage: true });
    console.log(`[${v.name}] saved → ${path.relative(REPO_ROOT, out)}`);
    await page.close();
  }

  console.log('---');
  for (const [name, list] of Object.entries(errors)) {
    if (list.length) {
      console.log(`[${name}] ${list.length} console error(s):`);
      list.slice(0, 3).forEach((e) => console.log(`  - ${e.slice(0, 200)}`));
    } else {
      console.log(`[${name}] clean console`);
    }
  }

  await browser.close();
})();
