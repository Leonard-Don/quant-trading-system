/**
 * E2E probe for the surviving "new" workspaces / interactions added in the
 * 2026-05-03 → 2026-05-05 sessions:
 *   - D : industry → "政策雷达" tab
 *   - D2: industry heatmap "政策" toggle
 *
 * (The paper-trading probes — C/C2/F/G/H — were removed when the 纸面账户
 * module was retired on 2026-06-22.)
 *
 * Light-touch: load page, assert key DOM, no console errors. Not trying
 * to recreate the whole flow; the goal is "does this UI mount cleanly in a
 * browser?"
 */

const { chromium } = require('playwright');

const FRONTEND = process.env.FRONTEND_URL || 'http://localhost:3000';

const failures = [];
const log = (...args) => console.log(...args);
const fail = (label, detail) => {
    failures.push({ label, detail });
    console.error(`✗ ${label}: ${detail}`);
};
const ok = (label) => console.log(`✓ ${label}`);

const collectConsoleErrors = (page, label) => {
    const errors = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error') {
            const text = msg.text();
            // CRA dev hot-reload + common antd noise are not actionable
            if (/sockjs-node|Warning: ReactDOM\.render is no longer supported|defaultProps/.test(text)) return;
            errors.push(text);
        }
    });
    page.on('pageerror', (err) => {
        errors.push(`pageerror: ${err.message}`);
    });
    return () => {
        if (errors.length > 0) {
            fail(`${label} 控制台/页面错误`, errors.slice(0, 3).join(' | '));
        }
    };
};

(async () => {
    const browser = await chromium.launch();
    const context = await browser.newContext();

    // ---------- D: industry → 政策雷达 tab ----------
    {
        const page = await context.newPage();
        const drainConsole = collectConsoleErrors(page, '政策雷达 tab');
        await page.goto(`${FRONTEND}/?view=industry`);
        await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => null);

        // Try to click on the "政策雷达" tab
        let tabEntered = false;
        try {
            await page.getByRole('tab', { name: '政策雷达' }).click({ timeout: 10000 });
            tabEntered = true;
        } catch (_err) {
            // Fallback: try by inner text
            const tab = await page.$('text=政策雷达');
            if (tab) {
                await tab.click();
                tabEntered = true;
            }
        }
        if (tabEntered) ok('D 行业工作区"政策雷达" tab 可点击');
        else fail('D 政策雷达 tab', '在行业工作区找不到该 tab');

        // After clicking, the panel test-id should appear
        await page.waitForSelector('[data-testid="policy-radar-panel"]', { timeout: 15000 }).catch(() => null);
        const panel = await page.$('[data-testid="policy-radar-panel"]');
        if (panel) ok('D PolicyRadarPanel 已渲染');
        else fail('D PolicyRadarPanel', 'data-testid="policy-radar-panel" 未渲染');

        drainConsole();
        await page.close();
    }

    // ---------- D2: heatmap policy overlay toggle ----------
    {
        const page = await context.newPage();
        const drainConsole = collectConsoleErrors(page, '热力图政策叠加');
        await page.goto(`${FRONTEND}/?view=industry`);
        // Heatmap is the default tab; wait for some heatmap surface
        await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => null);

        const toggle = await page.$('[data-testid="heatmap-policy-overlay-toggle"]');
        if (!toggle) {
            fail('D2 热力图政策开关', 'data-testid="heatmap-policy-overlay-toggle" 未找到');
        } else {
            ok('D2 热力图政策开关元素存在');
            const beforeState = await toggle.getAttribute('aria-checked');
            await toggle.click();
            // antd Switch flips aria-checked synchronously
            const afterState = await page.$eval(
                '[data-testid="heatmap-policy-overlay-toggle"]',
                (el) => el.getAttribute('aria-checked'),
            ).catch(() => null);
            if (beforeState !== afterState) ok(`D2 切换有效（${beforeState} → ${afterState}）`);
            else fail('D2 切换状态', `aria-checked 未变化（${beforeState}）`);

            // Wait briefly for fetch + render; badges may or may not appear
            // depending on whether real policy data covers any displayed industry.
            // We treat "no console error after toggle" as the success bar here.
            await page.waitForTimeout(1500);
        }

        drainConsole();
        await page.close();
    }

    await browser.close();

    if (failures.length === 0) {
        log('\n所有新功能浏览器探针通过 ✅');
        process.exit(0);
    } else {
        log(`\n探针失败 ${failures.length} 项：`);
        failures.forEach((f) => log(` - ${f.label}: ${f.detail}`));
        process.exit(1);
    }
})().catch((err) => {
    console.error('探针运行异常:', err);
    process.exit(2);
});
