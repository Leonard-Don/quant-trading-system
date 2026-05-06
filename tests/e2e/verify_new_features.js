/**
 * E2E probe for the new workspaces / interactions added in the
 * 2026-05-03 → 2026-05-05 sessions:
 *   - C : ?view=paper  (paper trading panel)
 *   - C2: paper trading slippage form field
 *   - D : industry → "政策雷达" tab
 *   - D2: industry heatmap "政策" toggle
 *   - F : backtest → paper handoff (sessionStorage prefill)
 *   - G : journal entry → paper handoff (today-research button)
 *   - H : paper positions → research journal (snapshot button)
 *
 * Light-touch: load page, assert key DOM, no console errors. Not trying
 * to recreate the whole flow (e.g. running a real backtest); the goal is
 * "does this newly-shipped UI mount cleanly in a browser?"
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

    // ---------------------- C: paper trading mount ----------------------
    {
        const page = await context.newPage();
        const drainConsole = collectConsoleErrors(page, '纸面账户');
        await page.goto(`${FRONTEND}/?view=paper`);
        // Wait for the paper workspace heading (Statistic / chips)
        await page.waitForSelector('.paper-trading-workspace', { timeout: 30000 }).catch(() => null);
        const hasWorkspace = await page.$('.paper-trading-workspace');
        if (!hasWorkspace) fail('C 纸面账户工作区未渲染', '.paper-trading-workspace 不存在');
        else ok('C 纸面账户工作区已渲染 (?view=paper)');

        // Order form fields visible
        const orderInput = await page.$('input[placeholder="如 AAPL"]');
        const qtyInput = await page.$('input[placeholder="如 10"]');
        const fillInput = await page.$('input[placeholder="如 150.0"]');
        if (orderInput && qtyInput && fillInput) ok('C 下单表单 symbol/quantity/fill_price 输入框俱全');
        else fail('C 下单表单缺字段', `symbol=${!!orderInput} qty=${!!qtyInput} fill=${!!fillInput}`);

        // Account chips render — at least one of these labels must appear
        const text = await page.content();
        if (/初始资金/.test(text)) ok('C 账户卡片渲染（初始资金 chip 可见）');
        else fail('C 账户卡片', '"初始资金" 字样未找到');

        drainConsole();
        await page.close();
    }

    // ---------- F: paper trading consumes sessionStorage prefill ----------
    {
        const page = await context.newPage();
        const drainConsole = collectConsoleErrors(page, '回测→纸面 prefill');
        // Plant a prefill BEFORE the panel mounts. We need to land on the
        // origin first so sessionStorage is keyed correctly, then navigate.
        await page.goto(`${FRONTEND}/`);
        await page.evaluate(() => {
            sessionStorage.setItem('paper-trading-prefill', JSON.stringify({
                symbol: 'GOOG',
                side: 'BUY',
                quantity: 3,
                sourceLabel: '由 E2E 探针 · 回测带入',
                writtenAt: Date.now(),
            }));
        });
        await page.goto(`${FRONTEND}/?view=paper`);
        await page.waitForSelector('[data-testid="paper-prefill-tag"]', { timeout: 15000 }).catch(() => null);

        const tag = await page.$('[data-testid="paper-prefill-tag"]');
        if (tag) ok('F prefill tag 在工作区出现');
        else fail('F prefill', 'paper-prefill-tag 未渲染');

        const symbolValue = await page.evaluate(() => {
            const el = document.querySelector('input[placeholder="如 AAPL"]');
            return el ? el.value : null;
        });
        if (symbolValue === 'GOOG') ok('F 表单 symbol 字段已被预填为 GOOG');
        else fail('F 表单 symbol 预填', `期望 GOOG，实际 ${symbolValue}`);

        // sessionStorage entry should be drained after consumption
        const remaining = await page.evaluate(() => sessionStorage.getItem('paper-trading-prefill'));
        if (remaining === null) ok('F prefill 消费后 sessionStorage 已清空');
        else fail('F prefill 消费', `sessionStorage 仍有: ${remaining}`);

        drainConsole();
        await page.close();
    }

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

    // ---------- C2: slippage form field on the paper trading panel ----------
    {
        const page = await context.newPage();
        const drainConsole = collectConsoleErrors(page, 'C2 滑点表单');
        await page.goto(`${FRONTEND}/?view=paper`);
        await page.waitForSelector('.paper-trading-workspace', { timeout: 30000 }).catch(() => null);

        const slippageInput = await page.$('input[placeholder="如 5"]');
        if (!slippageInput) {
            fail('C2 滑点字段', 'placeholder="如 5" 的 InputNumber 未渲染');
        } else {
            ok('C2 滑点字段已渲染');
            // Field starts at the form's initial 0; typing "8" appends → "08".
            // Just confirm it's writable and parses as a positive number, not
            // the exact rendered string.
            await slippageInput.click();
            await slippageInput.type('8');
            const numericValue = await slippageInput.evaluate((el) => Number(el.value));
            if (Number.isFinite(numericValue) && numericValue > 0) {
                ok(`C2 滑点字段接受数字输入（解析为 ${numericValue}）`);
            } else {
                fail('C2 滑点输入', `期望可解析为正数，实际 "${numericValue}"`);
            }
        }

        drainConsole();
        await page.close();
    }

    // ---------- H: paper trading "归档到档案" button ----------
    {
        const page = await context.newPage();
        const drainConsole = collectConsoleErrors(page, 'H 持仓归档');
        await page.goto(`${FRONTEND}/?view=paper`);
        await page.waitForSelector('.paper-trading-workspace', { timeout: 30000 }).catch(() => null);

        const archiveBtn = await page.$('[data-testid="paper-snapshot-positions"]');
        if (!archiveBtn) {
            fail('H 归档按钮', '[data-testid="paper-snapshot-positions"] 未渲染');
        } else {
            ok('H 归档按钮已渲染');
            // With no positions, the button should be disabled — that's the
            // graceful empty-state path. We just assert the disabled-attribute
            // resolution doesn't error.
            const isDisabled = await archiveBtn.evaluate((el) => el.disabled);
            ok(`H 归档按钮 disabled=${isDisabled}（与持仓状态对应即可）`);
        }

        drainConsole();
        await page.close();
    }

    // ---------- G: today research "送到纸面账户" button rendering ----------
    // Plant a fake type=backtest entry into the local research-journal cache
    // before the dashboard mounts so it merges into the rendered list. The
    // dashboard reads localStorage as its merge source for offline state.
    {
        const page = await context.newPage();
        const drainConsole = collectConsoleErrors(page, 'G 档案送纸面按钮');
        await page.goto(`${FRONTEND}/`);
        await page.evaluate(() => {
            const fakeBacktest = {
                id: 'bt-probe-1',
                created_at: new Date().toISOString(),
                symbol: 'AAPL',
                strategy: 'MovingAverageCrossover',
                note: '探针测试',
                metrics: { total_return: 0.1, max_drawdown: -0.03, sharpe_ratio: 1.0, num_trades: 1 },
            };
            localStorage.setItem('backtest_research_snapshots', JSON.stringify([fakeBacktest]));
        });

        await page.goto(`${FRONTEND}/?view=today`);
        await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => null);

        // The dashboard renders all backtest-typed entries with this testid.
        const button = await page.waitForSelector(
            '[data-testid="today-entry-send-to-paper"]',
            { timeout: 15000 },
        ).catch(() => null);
        if (button) ok('G "送到纸面账户" 按钮在 backtest 档案条目上可见');
        else fail('G send-to-paper 按钮', '在 backtest 档案条目上未渲染');

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
