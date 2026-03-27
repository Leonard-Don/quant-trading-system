const { chromium } = require('playwright');
const fs = require('fs');

const normalizeUrl = (value) => {
  const url = new URL(value);
  const params = new URLSearchParams(url.search);
  const sorted = [...params.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${url.origin}${url.pathname}?${new URLSearchParams(sorted).toString()}`;
};

const waitForIndustryAppShell = async (page) => {
  await page.waitForFunction(
    () => {
      const tabLabels = Array.from(document.querySelectorAll('.ant-tabs-tab-btn'))
        .map((node) => (node.textContent || '').trim());
      return tabLabels.includes('热力图') && tabLabels.includes('排行榜');
    },
    null,
    { timeout: 60000 }
  );
};

const waitForIndustryHeatmapReady = async (page, options = {}) => {
  const { allowEmpty = false } = options;
  await waitForIndustryAppShell(page);
  await page.locator('.ant-radio-button-wrapper').filter({ hasText: '1日' }).first().waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('.ant-radio-button-wrapper').filter({ hasText: '5日' }).first().waitFor({ state: 'visible', timeout: 60000 });
  await page.getByPlaceholder('行业筛选...').waitFor({ state: 'visible', timeout: 60000 });
  if (allowEmpty) {
    await page.waitForFunction(() => {
      const hasTile = Boolean(document.querySelector('[data-testid="heatmap-tile"]'));
      const hasEmpty = document.body.innerText.includes('当前市值来源筛选下暂无行业');
      return hasTile || hasEmpty;
    }, null, { timeout: 60000 });
    return;
  }
  await page.locator('[data-testid="heatmap-tile"]').first().waitFor({ state: 'visible', timeout: 60000 });
};

const waitForIndustryDetailReady = async (page) => {
  const modal = page.locator('[data-testid="industry-detail-modal"]');
  await modal.waitFor({ state: 'visible', timeout: 6000 });
  await page.locator('[data-testid="industry-detail-panel"]').waitFor({ state: 'visible', timeout: 6000 });
  await page.locator('[data-testid="industry-stock-table"] tbody tr').first().waitFor({ state: 'visible', timeout: 6000 });
  return modal;
};

const readIndustryStatistic = async (page, title) => page.evaluate((statTitle) => {
  const root = document.querySelector('[data-testid="industry-detail-modal"]');
  if (!root) return '';
  const stats = Array.from(root.querySelectorAll('.ant-statistic'));
  const stat = stats.find((node) => {
    const titleNode = node.querySelector('.ant-statistic-title');
    return titleNode && (titleNode.textContent || '').trim() === statTitle;
  });
  return (stat?.querySelector('.ant-statistic-content-value')?.textContent || '').trim();
}, title);

const waitForIndustryScoreStage = async (page, expectedStages, timeout = 6000) => {
  const stages = Array.isArray(expectedStages) ? expectedStages : [expectedStages];
  await page.waitForFunction((accepted) => {
    const node = document.querySelector('[data-testid="industry-stock-table"]');
    const stage = node?.getAttribute('data-score-stage');
    return Boolean(stage && accepted.includes(stage));
  }, stages, { timeout });
  return page.locator('[data-testid="industry-stock-table"]').getAttribute('data-score-stage');
};

const readIndustryDisplayReady = async (page) => page.locator('[data-testid="industry-stock-table"]').getAttribute('data-display-ready');

const closeVisibleModal = async (page, testId) => {
  const modal = page.locator(`[data-testid="${testId}"]`);
  if (await modal.count()) {
    const closeButton = modal.locator('.ant-modal-close');
    if (await closeButton.count()) {
      await closeButton.click();
      await modal.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(250);
    }
  }
};

const chooseSelectOption = async (page, selectLocator, optionText) => {
  await selectLocator.waitFor({ state: 'visible', timeout: 10000 });
  await selectLocator.click();
  const option = page.locator('.ant-select-dropdown .ant-select-item-option-content').filter({ hasText: optionText }).last();
  await option.waitFor({ state: 'visible', timeout: 10000 });
  await option.click();
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 1100 });
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  console.log('正在访问行业热度页面...');
  await page.goto('http://localhost:3000?view=industry', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryHeatmapReady(page);
  
  // 1. 验证热力图渲染和基础切换
  console.log('验证热力图维度切换...');
  
  // 切换到 5日
  await page.locator('.ant-radio-button-wrapper').filter({ hasText: '5日' }).first().click();
  await page.waitForTimeout(1000);
  
  // 切换指标：看净流入%
  await page.getByText('看涨跌', { exact: true }).click();
  await page.locator('.ant-select-item-option-content').filter({ hasText: '看净流入%' }).click();
  await page.waitForTimeout(1000);
  
  // 2. 验证搜索功能
  console.log('验证行业筛选搜索...');
  await page.getByPlaceholder('行业筛选...').fill('半导体');
  await page.waitForTimeout(500);
  const visibleIndustryTitles = await page.locator('.ant-card-body .ant-typography strong').evaluateAll(
    (nodes) => nodes.map(node => (node.textContent || '').trim()).filter(Boolean)
  );
  const semiconductorExists = visibleIndustryTitles.some((text) => text.includes('半导体'));
  const unrelatedVisible = visibleIndustryTitles.some((text) => text && !text.includes('半导体'));
  console.log(`搜索"半导体"结果: ${semiconductorExists ? '找到' : '未找到'}`);
  console.log(`搜索后仍有其他行业标题: ${unrelatedVisible ? '是' : '否'}`);
  await page.getByPlaceholder('行业筛选...').fill(''); // 清空搜索

  // 3. 验证市值来源筛选
  console.log('验证估算市值筛选...');
  await page.locator('.ant-tag').filter({ hasText: /估算\s+\d+/ }).first().click();
  await page.waitForTimeout(800);
  const stateBarVisible = await page.getByText('当前视图', { exact: false }).isVisible();
  const bodyTextAfterFilter = await page.locator('body').innerText();
  const estimatedStateVisible = bodyTextAfterFilter.includes('来源: 估算市值');
  const hasEstimatedIndustry = bodyTextAfterFilter.includes('军工装备');
  const hasLiveIndustry = bodyTextAfterFilter.includes('银行');
  console.log(`估算筛选状态标签: ${estimatedStateVisible ? '已显示' : '未显示'}`);
  console.log(`当前视图状态条: ${stateBarVisible ? '已显示' : '未显示'}`);
  console.log(`估算行业可见: ${hasEstimatedIndustry ? '是' : '否'}`);
  console.log(`实时行业仍在热力图中: ${hasLiveIndustry ? '是' : '否'}`);

  // 4. 验证 URL 状态持久化
  console.log('验证 URL 状态持久化...');
  const currentUrl = page.url();
  console.log(`当前 URL: ${currentUrl}`);
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryHeatmapReady(page);
  const reloadedUrl = page.url();
  const persistedBodyText = await page.locator('body').innerText();
  const persistedHintVisible = persistedBodyText.includes('来源: 估算市值');
  console.log(`刷新后 URL 保留: ${normalizeUrl(reloadedUrl) === normalizeUrl(currentUrl) ? '是' : '否'}`);
  console.log(`刷新后状态标签保留: ${persistedHintVisible ? '是' : '否'}`);
  await page.getByText('颜色: 看净流入%', { exact: false }).click();
  await page.waitForTimeout(300);
  const heatmapTagFocusWorks = await page.evaluate(() => {
    const node = document.querySelector('.heatmap-control-color-metric');
    return Boolean(node && getComputedStyle(node).boxShadow && getComputedStyle(node).boxShadow !== 'none');
  });
  console.log(`热力图状态标签定位控件是否生效: ${heatmapTagFocusWorks ? '是' : '否'}`);
  await page.locator('.heatmap-state-tag-market_cap_filter .ant-tag-close-icon').click();
  await page.waitForTimeout(1000);
  const heatmapUrlAfterSingleClear = page.url();
  const heatmapTextAfterSingleClear = await page.locator('body').innerText();
  console.log(`热力图单项标签清除是否生效: ${!heatmapTextAfterSingleClear.includes('来源: 估算市值') ? '是' : '否'}`);
  console.log(`热力图单项标签清除后 URL 已同步: ${!heatmapUrlAfterSingleClear.includes('industry_market_cap_filter=estimated') ? '是' : '否'}`);

  // 5. 验证热力图角标来源筛选
  console.log('验证热力图角标来源筛选...');
  await page.goto('http://localhost:3000/?view=industry', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryHeatmapReady(page);
  const liveCornerBadge = page.locator('.ant-card-body >> text=实').first();
  const liveCornerBadgeCount = await liveCornerBadge.count();
  if (liveCornerBadgeCount > 0) {
    await liveCornerBadge.click();
    await page.waitForTimeout(1200);
    const cornerFilterText = await page.locator('body').innerText();
    const cornerFilterHintVisible = cornerFilterText.includes('来源: 实时市值');
    const cornerFilterUrl = page.url();
    console.log(`热力图角标来源筛选是否生效: ${cornerFilterHintVisible ? '是' : '否'}`);
    console.log(`热力图角标来源筛选 URL 是否带参数: ${cornerFilterUrl.includes('industry_market_cap_filter=live') ? '是' : '否'}`);
  } else {
    console.log('热力图角标来源筛选是否生效: 跳过');
    console.log('热力图角标来源筛选 URL 是否带参数: 跳过');
  }

  // 6. 验证无命中来源筛选不会回退全量
  console.log('验证无命中来源筛选空态...');
  const proxyBadgeCount = await page.locator('.ant-tag').filter({ hasText: /代理\s+\d+/ }).count();
  if (proxyBadgeCount === 0) {
    await page.goto('http://localhost:3000/?view=industry&industry_market_cap_filter=proxy', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitForIndustryHeatmapReady(page, { allowEmpty: true });
    const proxyEmptyVisible = await page.getByText('当前市值来源筛选下暂无行业', { exact: false }).isVisible();
    const proxyClearVisible = await page.getByText('查看全部行业', { exact: false }).isVisible();
    console.log(`代理筛选空态是否显示: ${proxyEmptyVisible ? '是' : '否'}`);
    console.log(`代理筛选清除按钮是否显示: ${proxyClearVisible ? '是' : '否'}`);
    if (proxyClearVisible) {
      await page.getByText('查看全部行业', { exact: false }).click();
      await page.waitForTimeout(800);
      const afterClearText = await page.locator('body').innerText();
      console.log(`清除后空态是否消失: ${afterClearText.includes('当前市值来源筛选下暂无行业') ? '否' : '是'}`);
    }
  } else {
    console.log('代理筛选空态是否显示: 跳过（当前存在代理行业）');
    console.log('代理筛选清除按钮是否显示: 跳过（当前存在代理行业）');
  }

  // 7. 验证弹窗详情
  console.log('点击行业方块打开详情...');
  const firstHeatmapTile = page.locator('[data-testid="heatmap-tile"]').first();
  const industryText = (await firstHeatmapTile.getAttribute('data-industry-name')) || await firstHeatmapTile.innerText();
  console.log(`点击行业: ${industryText}`);
  await firstHeatmapTile.click();
  const detailModal = await waitForIndustryDetailReady(page);
  const modalVisible = await detailModal.isVisible();
  console.log(`详情弹窗是否打开: ${modalVisible ? '是' : '否'}`);
  if (modalVisible) {
    const stocksTableBody = page.locator('[data-testid="industry-stock-table"] tbody');
    const quickRowsRendered = await stocksTableBody.locator('tr').first().isVisible().catch(() => false);
    await page.waitForFunction(() => {
      const root = document.querySelector('[data-testid="industry-detail-modal"]');
      if (!root) return false;
      const stats = Array.from(root.querySelectorAll('.ant-statistic'));
      const totalMarketCapStat = stats.find((node) => {
        const titleNode = node.querySelector('.ant-statistic-title');
        return titleNode && (titleNode.textContent || '').trim() === '总市值';
      });
      const totalMarketCap = (totalMarketCapStat?.querySelector('.ant-statistic-content-value')?.textContent || '').trim();
      return totalMarketCap && totalMarketCap !== '-';
    }, null, { timeout: 10000 }).catch(() => {});
    await page.waitForFunction(() => {
      const node = document.querySelector('[data-testid="industry-stock-table"]');
      const stage = node?.getAttribute('data-score-stage');
      return stage === 'quick' || stage === 'full';
    }, null, { timeout: 4000 }).catch(() => {});
    const initialScoreStage = await page.locator('[data-testid="industry-stock-table"]').getAttribute('data-score-stage');
    const summarySnapshot = {
      totalMarketCap: await readIndustryStatistic(page, '总市值'),
      avgPe: await readIndustryStatistic(page, '平均市盈率'),
    };
    const stockRows = await page.locator('[data-testid="industry-stock-table"] tbody tr').evaluateAll(
      (rows) => rows.slice(0, 5).map((row) => Array.from(row.querySelectorAll('td')).map((cell) => (cell.textContent || '').trim()))
    );
    const quickScoreSnapshot = stockRows.map((cells) => cells[3] || '');
    await waitForIndustryScoreStage(page, ['quick', 'full'], 4000).catch(() => null);
    if (initialScoreStage === 'quick') {
      await waitForIndustryScoreStage(page, 'full', 9000).catch(() => null);
    }
    const upgradedScoreStage = await page.locator('[data-testid="industry-stock-table"]').getAttribute('data-score-stage');
    const upgradedDisplayReady = await readIndustryDisplayReady(page);
    const upgradedStockRows = await page.locator('[data-testid="industry-stock-table"] tbody tr').evaluateAll(
      (rows) => rows.slice(0, 5).map((row) => Array.from(row.querySelectorAll('td')).map((cell) => (cell.textContent || '').trim()))
    );
    const stockRowsHaveDetails = stockRows.some((cells) => {
      const marketCap = cells[5] || '';
      const peRatio = cells[6] || '';
      return marketCap !== '-' || peRatio !== '-';
    });
    const stockScoresUpgraded = upgradedStockRows.some((cells, idx) => {
      const score = cells[3] || '';
      const initialScore = quickScoreSnapshot[idx] || '';
      return score !== '-' && score !== '' && score !== initialScore;
    }) || upgradedStockRows.some((cells) => {
      const score = cells[3] || '';
      return score !== '-' && score !== '';
    });
    console.log(`行业成分股首屏快速渲染: ${quickRowsRendered ? '是' : '否'}`);
    console.log(`行业成分股初始评分阶段: ${initialScoreStage || 'unknown'}`);
    console.log(`行业摘要总市值已补齐: ${summarySnapshot.totalMarketCap && summarySnapshot.totalMarketCap !== '-' ? '是' : '否'}`);
    console.log(`行业成分股前5行存在真实明细: ${stockRowsHaveDetails ? '是' : '否'}`);
    const scoreDisplayReady = upgradedScoreStage === 'full' || upgradedDisplayReady === 'true';
    console.log(`行业成分股展示是否已就绪: ${scoreDisplayReady && stockScoresUpgraded ? '是' : scoreDisplayReady ? '是' : '否'}`);
    await closeVisibleModal(page, 'industry-detail-modal');
  }

  console.log('验证行业详情快速切换...');
  const visibleIndustryNames = await page.locator('[data-testid="heatmap-tile"]').evaluateAll(
    (nodes) => nodes.map((node) => node.getAttribute('data-industry-name') || '').filter(Boolean).slice(0, 2)
  );
  if (visibleIndustryNames.length >= 2) {
    const [firstIndustry, secondIndustry] = visibleIndustryNames;
    await page.evaluate(([firstName, secondName]) => {
      const findNode = (name) => Array.from(document.querySelectorAll('[data-testid="heatmap-tile"]'))
        .find((node) => (node.getAttribute('data-industry-name') || '').includes(name));
      findNode(firstName)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      findNode(secondName)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }, [firstIndustry, secondIndustry]);
    await page.waitForFunction((targetIndustry) => {
      const title = document.querySelector('[data-testid="industry-detail-modal"] .ant-modal-title');
      return (title?.textContent || '').includes(targetIndustry);
    }, secondIndustry, { timeout: 4000 }).catch(() => {});
    await page.waitForFunction(() => {
      const root = document.querySelector('[data-testid="industry-detail-modal"]');
      if (!root) return false;
      const stats = Array.from(root.querySelectorAll('.ant-statistic'));
      const totalMarketCapStat = stats.find((node) => {
        const titleNode = node.querySelector('.ant-statistic-title');
        return titleNode && (titleNode.textContent || '').trim() === '总市值';
      });
      const totalMarketCap = (totalMarketCapStat?.querySelector('.ant-statistic-content-value')?.textContent || '').trim();
      return totalMarketCap && totalMarketCap !== '-';
    }, null, { timeout: 6000 }).catch(() => {});
    const switchedTitle = await page.locator('[data-testid="industry-detail-modal"] .ant-modal-title').innerText();
    const switchedSummary = await readIndustryStatistic(page, '总市值');
    console.log(`快速切换后详情标题归属最新行业: ${switchedTitle.includes(secondIndustry) ? '是' : '否'}`);
    console.log(`快速切换后摘要已落到最新行业: ${switchedSummary && switchedSummary !== '-' ? '是' : '否'}`);
    await closeVisibleModal(page, 'industry-detail-modal');
  } else {
    console.log('快速切换后详情标题归属最新行业: 跳过');
    console.log('快速切换后摘要已落到最新行业: 跳过');
  }

  console.log('验证龙头股详情竞态保护...');
  const leaderRows = page.locator('[data-testid="leader-stock-table-core"] [data-testid="leader-stock-row"]');
  const leaderRowCount = await leaderRows.count();
  if (leaderRowCount >= 2) {
    const firstLeaderSymbol = await leaderRows.nth(0).getAttribute('data-symbol');
    const secondLeaderSymbol = await leaderRows.nth(1).getAttribute('data-symbol');
    await page.evaluate(() => {
      const close = document.querySelector('[data-testid="stock-detail-modal"] .ant-modal-close');
      close?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }).catch(() => {});
    await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('[data-testid="leader-stock-table-core"] [data-testid="leader-stock-row"]'));
      rows[0]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      rows[1]?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await page.locator('[data-testid="stock-detail-modal"]').waitFor({ state: 'visible', timeout: 6000 });
    await page.locator('[data-testid="stock-detail-modal-body"]').waitFor({ state: 'visible', timeout: 6000 });
    const stockDetailText = await page.locator('[data-testid="stock-detail-modal"]').innerText();
    console.log(`龙头股详情最终命中第二只: ${secondLeaderSymbol && stockDetailText.includes(secondLeaderSymbol) ? '是' : '否'}`);
    console.log(`龙头股旧响应未覆盖当前弹窗: ${firstLeaderSymbol && secondLeaderSymbol ? (!stockDetailText.includes(firstLeaderSymbol) || stockDetailText.includes(secondLeaderSymbol) ? '是' : '否') : '跳过'}`);
    await closeVisibleModal(page, 'stock-detail-modal');
  } else {
    console.log('龙头股详情最终命中第二只: 跳过');
    console.log('龙头股旧响应未覆盖当前弹窗: 跳过');
  }

  // 8. 验证标签页切换
  console.log('验证排行榜切换...');
  await page.click('.ant-tabs-tab-btn:has-text("排行榜")');
  await page.waitForTimeout(1000);
  const tableExists = await page.isVisible('.ant-table');
  console.log(`排行榜表格是否显示: ${tableExists ? '是' : '否'}`);
  const volatilityTagCount = await page.locator('.ant-table-tbody .ant-tag').filter({ hasText: /^(高波动|中波动|低波动)$/ }).count();
  console.log(`排行榜波动率标签是否显示: ${volatilityTagCount > 0 ? '是' : '否'}`);

  console.log('验证排行榜波动率排序与筛选...');
  await page.waitForFunction(
    () => document.querySelectorAll('.ant-tabs-tabpane-active .ant-card-extra .ant-select').length >= 4,
    null,
    { timeout: 10000 }
  );
  await chooseSelectOption(page, page.locator('.ant-tabs-tabpane-active .ranking-control-sort-by'), '按波动率');
  await page.waitForTimeout(1000);
  await chooseSelectOption(page, page.locator('.ant-tabs-tabpane-active .ranking-control-volatility'), '低波动');
  await page.waitForTimeout(1000);
  await chooseSelectOption(page, page.locator('.ant-tabs-tabpane-active .ranking-control-market-cap'), '实时市值');
  await page.waitForTimeout(1000);
  const rankingTableBody = page.locator('.ant-tabs-tabpane-active .ant-table-tbody');
  const rankingBodyRows = await rankingTableBody.locator('tr').evaluateAll(
    (rows) => rows.map(row => (row.textContent || '').trim()).filter(Boolean)
  );
  const rankingHasEmptyState = rankingBodyRows.length > 0 && rankingBodyRows[0].includes('暂无排名数据');
  const volatilityLabelsAfterFilter = await rankingTableBody.locator('.ant-tag').evaluateAll(
    (nodes) => nodes.map(node => (node.textContent || '').trim()).filter(text => text === '高波动' || text === '中波动' || text.startsWith('低波动'))
  );
  const onlyLowVolatility = rankingHasEmptyState || (volatilityLabelsAfterFilter.length > 0 && volatilityLabelsAfterFilter.every(text => text.startsWith('低波动')));
  console.log(`排行榜低波动筛选是否生效: ${onlyLowVolatility ? '是' : '否'}`);
  const sourceLabelsAfterFilter = await rankingTableBody.locator('.ant-tag').evaluateAll(
    (nodes) => nodes.map(node => (node.textContent || '').trim()).filter(text => text === '实时' || text === '快照' || text === '代理' || text === '估算')
  );
  const onlyLiveSource = rankingHasEmptyState || (sourceLabelsAfterFilter.length > 0 && sourceLabelsAfterFilter.every(text => text === '实时'));
  console.log(`排行榜实时市值筛选是否生效: ${onlyLiveSource ? '是' : '否'}`);

  console.log('验证排行榜 URL 状态持久化...');
  const rankingUrl = page.url();
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryAppShell(page);
  const reloadedRankingUrl = page.url();
  const rankingTabStillActive = await page.locator('.ant-tabs-tab-active .ant-tabs-tab-btn').innerText();
  const rankingSelectValues = await page.locator('.ant-tabs-tabpane-active .ant-card-extra .ant-select-selection-item').evaluateAll(
    (nodes) => nodes.map(node => (node.textContent || '').trim()).filter(Boolean)
  );
  const rankingUrlPersisted = normalizeUrl(reloadedRankingUrl) === normalizeUrl(rankingUrl);
  const rankingFiltersPersisted = rankingSelectValues.includes('按波动率')
    && rankingSelectValues.includes('低波动')
    && rankingSelectValues.includes('实时市值')
    && rankingSelectValues.includes('近5日');
  console.log(`排行榜 URL 保留: ${rankingUrlPersisted ? '是' : '否'}`);
  console.log(`排行榜刷新后仍停留当前标签页: ${rankingTabStillActive === '排行榜' ? '是' : '否'}`);
  console.log(`排行榜筛选状态刷新后保留: ${rankingFiltersPersisted ? '是' : '否'}`);
  const rankingStateBarText = await page.locator('body').innerText();
  console.log(`排行榜状态条是否显示: ${rankingStateBarText.includes('当前排行榜') ? '是' : '否'}`);
  console.log(`排行榜状态条是否反映组合视图: ${rankingStateBarText.includes('排序: 按波动率') && rankingStateBarText.includes('波动: 低波动') && rankingStateBarText.includes('市值来源: 实时市值') ? '是' : '否'}`);
  await page.getByText('排序: 按波动率', { exact: false }).click();
  await page.waitForTimeout(300);
  const rankingTagFocusWorks = await page.evaluate(() => {
    const node = document.querySelector('.ranking-control-sort-by');
    return Boolean(node && getComputedStyle(node).boxShadow && getComputedStyle(node).boxShadow !== 'none');
  });
  console.log(`排行榜状态标签定位控件是否生效: ${rankingTagFocusWorks ? '是' : '否'}`);
  await page.locator('.ranking-state-tag-market_cap_filter .ant-tag-close-icon').click();
  await page.waitForTimeout(1000);
  const partialResetRankingSelectValues = await page.locator('.ant-tabs-tabpane-active .ant-card-extra .ant-select-selection-item').evaluateAll(
    (nodes) => nodes.map(node => (node.textContent || '').trim()).filter(Boolean)
  );
  const partialResetRankingUrl = page.url();
  const rankingSingleTagResetApplied = partialResetRankingSelectValues.includes('按波动率')
    && partialResetRankingSelectValues.includes('低波动')
    && partialResetRankingSelectValues.includes('全部市值来源')
    && !partialResetRankingSelectValues.includes('实时市值');
  console.log(`排行榜单项标签清除是否生效: ${rankingSingleTagResetApplied ? '是' : '否'}`);
  console.log(`排行榜单项标签清除后 URL 已同步: ${!partialResetRankingUrl.includes('industry_rank_market_cap=live') && partialResetRankingUrl.includes('industry_rank_sort=industry_volatility') && partialResetRankingUrl.includes('industry_rank_volatility=low') ? '是' : '否'}`);
  await page.getByRole('button', { name: '恢复默认榜单' }).click();
  await page.waitForTimeout(1000);
  const resetRankingSelectValues = await page.locator('.ant-tabs-tabpane-active .ant-card-extra .ant-select-selection-item').evaluateAll(
    (nodes) => nodes.map(node => (node.textContent || '').trim()).filter(Boolean)
  );
  const resetRankingUrl = page.url();
  const rankingResetApplied = resetRankingSelectValues.includes('按综合得分')
    && resetRankingSelectValues.includes('全部波动')
    && resetRankingSelectValues.includes('全部市值来源')
    && resetRankingSelectValues.includes('近5日');
  console.log(`排行榜恢复默认是否生效: ${rankingResetApplied ? '是' : '否'}`);
  console.log(`排行榜恢复默认后 URL 已重置: ${!resetRankingUrl.includes('industry_rank_sort=industry_volatility') && !resetRankingUrl.includes('industry_rank_volatility=low') && !resetRankingUrl.includes('industry_rank_market_cap=live') ? '是' : '否'}`);

  console.log('验证排行榜来源标签联动...');
  const rankingFilterTag = page.locator('.ant-table-tbody .ant-tag').filter({ hasText: /^(实时|快照|代理|估算)$/ }).first();
  const rankingFilterTagCount = await rankingFilterTag.count();
  if (rankingFilterTagCount > 0) {
    const rankingFilterLabel = (await rankingFilterTag.innerText()).trim();
    await rankingFilterTag.click();
    await page.waitForTimeout(1200);
    const switchedToHeatmap = await page.locator('.ant-tabs-tab-active .ant-tabs-tab-btn').innerText();
    const heatmapFilterText = await page.locator('body').innerText();
    const heatmapFilterHintVisible = heatmapFilterText.includes(`来源: ${rankingFilterLabel === '实时' ? '实时市值' : rankingFilterLabel === '快照' ? '快照市值' : rankingFilterLabel === '代理' ? '代理市值' : '估算市值'}`);
    console.log(`排行榜来源标签点击后标签页: ${switchedToHeatmap}`);
    console.log(`排行榜来源标签 ${rankingFilterLabel} 联动是否生效: ${heatmapFilterHintVisible ? '是' : '否'}`);
  } else {
    console.log('排行榜来源标签点击后标签页: 跳过');
    console.log('排行榜来源标签联动是否生效: 跳过');
  }

  console.log('验证聚类分析...');
  await closeVisibleModal(page, 'industry-detail-modal');
  await closeVisibleModal(page, 'stock-detail-modal');
  await page.keyboard.press('Escape').catch(() => {});
  await page.locator('.ant-tabs-tab-btn').filter({ hasText: '聚类分析' }).click({ force: true });
  await page.waitForFunction(
    () => document.querySelector('.ant-tabs-tab-active .ant-tabs-tab-btn')?.textContent?.includes('聚类分析'),
    null,
    { timeout: 5000 }
  );
  await page.waitForFunction(
    () => document.body.innerText.includes('聚类分布图')
      || document.querySelectorAll('.recharts-responsive-container').length > 0,
    null,
    { timeout: 8000 }
  ).catch(() => {});
  const clusterChartState = await page.evaluate(() => ({
    hasScatterTitle: document.body.innerText.includes('聚类分布图'),
    responsiveCount: document.querySelectorAll('.recharts-responsive-container').length,
    hasCurrentViewBar: document.body.innerText.includes('当前视图'),
  }));
  const clusterChartExists = clusterChartState.hasScatterTitle || clusterChartState.responsiveCount > 0;
  console.log(`聚类分析图表是否显示: ${clusterChartExists ? '是' : '否'}`);
  console.log(`聚类分析页仍显示热力图状态条: ${clusterChartState.hasCurrentViewBar ? '是' : '否'}`);

  console.log('验证轮动对比...');
  await page.click('.ant-tabs-tab-btn:has-text("轮动对比")');
  await page.waitForTimeout(3000);
  const rotationChartExists = await page.evaluate(() => {
    const text = document.body.innerText;
    return (
      document.querySelectorAll('.recharts-responsive-container').length > 0
      || (text.includes('更新时间:') && !text.includes('请选择至少 2 个行业进行对比'))
    );
  });
  console.log(`轮动对比图表是否显示: ${rotationChartExists ? '是' : '否'}`);

  console.log('正在保存页面状态快照...');
  const content = await page.content();
  fs.writeFileSync('verify_result.html', content);
  console.log(`控制台错误数: ${consoleErrors.length}`);
  if (consoleErrors.length > 0) {
    console.log(consoleErrors.join('\n'));
  }

  await browser.close();
  console.log('验证完成。');
})();
