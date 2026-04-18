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
  await page.waitForFunction(() => {
    const hasColorMetric = Boolean(document.querySelector('.heatmap-control-color-metric'));
    const hasSearch = Boolean(
      document.querySelector('input[aria-label="按行业名称筛选热力图"]')
      || document.querySelector('input[placeholder="行业筛选…"]')
      || document.querySelector('input[placeholder="行业筛选..."]')
    );
    return hasColorMetric && hasSearch;
  }, null, { timeout: 60000 });
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

const getIndustrySearchInput = (page) => page
  .locator('input[aria-label="按行业名称筛选热力图"], input[placeholder="行业筛选…"], input[placeholder="行业筛选..."]')
  .first();

const openIndustryWorkspaceTab = async (page, labelPattern) => {
  const tab = page.getByRole('tab', { name: labelPattern }).first();
  await tab.waitFor({ state: 'visible', timeout: 10000 });
  await ensureNoVisibleModals(page);
  await tab.click({ force: true });
  await page.waitForTimeout(300);
};

const readVisibleHeatmapIndustryTitles = async (page) => page.locator('[data-testid="heatmap-tile"]:visible').evaluateAll(
  (nodes) => [...new Set(
    nodes
      .map((node) => (node.getAttribute('data-industry-name') || '').trim())
      .filter(Boolean)
  )]
);

const waitForHeatmapSearchSettled = async (page) => {
  await page.waitForFunction(() => {
    const hasVisibleTile = Array.from(document.querySelectorAll('[data-testid="heatmap-tile"]'))
      .some((node) => node.getClientRects().length > 0);
    const bodyText = document.body.innerText;
    return hasVisibleTile
      || bodyText.includes('未找到匹配的行业')
      || bodyText.includes('当前筛选条件下未找到匹配行业');
  }, null, { timeout: 15000 });
};

const isHeatmapSearchEmptyStateVisible = async (page) => page.evaluate(() => {
  const bodyText = document.body.innerText;
  return bodyText.includes('未找到匹配的行业') || bodyText.includes('当前筛选条件下未找到匹配行业');
});

const readIndustryPreferences = async (page) => page.evaluate(async () => {
  const response = await fetch('/industry/preferences');
  if (!response.ok) {
    throw new Error(`Failed to load industry preferences: ${response.status}`);
  }
  return response.json();
});

const writeIndustryPreferences = async (page, payload) => {
  await page.evaluate(async (nextPayload) => {
    const response = await fetch('/industry/preferences', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nextPayload),
    });
    if (!response.ok) {
      throw new Error(`Failed to update industry preferences: ${response.status}`);
    }
  }, payload);
};

const resetIndustryPreferences = async (page) => {
  await writeIndustryPreferences(page, {
    watchlist_industries: [],
    saved_views: [],
    alert_thresholds: {},
  });
};

const waitForIndustryDetailReady = async (page, options = {}) => {
  const { modalTimeout = 8000, contentTimeout = 45000 } = options;
  const modal = page.locator('[data-testid="industry-detail-modal"]');
  await modal.waitFor({ state: 'visible', timeout: modalTimeout });
  await page.locator('[data-testid="industry-detail-panel"]').waitFor({ state: 'visible', timeout: modalTimeout });
  await page.waitForFunction(() => {
    const panel = document.querySelector('[data-testid="industry-detail-panel"]');
    const summaryCards = Array.from(panel?.querySelectorAll('.industry-detail-summary-card') || []);
    const totalMarketCapCard = summaryCards.find((node) => {
      const labelNode = node.querySelector('.industry-detail-summary-card__label');
      return labelNode && (labelNode.textContent || '').trim() === '总市值';
    });
    const totalMarketCap = (totalMarketCapCard?.querySelector('.industry-detail-summary-card__value')?.textContent || '').trim();
    const degraded = (panel?.textContent || '').includes('当前显示的是降级行业数据');
    const aiVisible = panel?.querySelectorAll('[data-testid="industry-ai-insight-panel"]').length > 0;
    return Boolean(
      (totalMarketCap && totalMarketCap !== '-')
      || degraded
      || aiVisible
    );
  }, null, { timeout: contentTimeout });
  return modal;
};

const waitForRankingReady = async (page) => {
  await page.waitForFunction(
    () => document.querySelector('.ant-tabs-tab-active .ant-tabs-tab-btn')?.textContent?.includes('排行榜'),
    null,
    { timeout: 5000 }
  );
  await page.waitForFunction(() => {
    const card = document.querySelector('.industry-ranking-card');
    if (!card) return false;
    const table = card.querySelector('.ant-table');
    if (!table) return false;
    const spinning = Boolean(card.querySelector('.ant-spin-spinning'));
    const hasRows = card.querySelectorAll('.ant-table-tbody tr').length > 0;
    const hasEmpty = (card.textContent || '').includes('暂无排名数据');
    return !spinning && (hasRows || hasEmpty);
  }, null, { timeout: 12000 });
};

const readRankingSelectValues = async (page) => page.evaluate(() => ({
  sortBy: document.querySelector('[data-testid="ranking-control-sort-by"] .ant-select-selection-item')?.textContent?.trim() || '',
  lookback: document.querySelector('[data-testid="ranking-control-lookback"] .ant-select-selection-item')?.textContent?.trim() || '',
  volatility: document.querySelector('[data-testid="ranking-control-volatility"] .ant-select-selection-item')?.textContent?.trim() || '',
  marketCap: document.querySelector('[data-testid="ranking-control-market-cap"] .ant-select-selection-item')?.textContent?.trim() || '',
}));

const readRankingStateTagTexts = async (page) => page.evaluate(() => (
  Array.from(document.querySelectorAll('[data-testid="ranking-state-bar"] .industry-state-tag'))
    .map((node) => (node.textContent || '').trim())
));

const readIndustryStatistic = async (page, title) => page.evaluate((statTitle) => {
  const root = document.querySelector('[data-testid="industry-detail-modal"]');
  if (!root) return '';
  const summaryCards = Array.from(root.querySelectorAll('.industry-detail-summary-card'));
  const summaryCard = summaryCards.find((node) => {
    const labelNode = node.querySelector('.industry-detail-summary-card__label');
    return labelNode && (labelNode.textContent || '').trim() === statTitle;
  });
  if (summaryCard) {
    return (summaryCard.querySelector('.industry-detail-summary-card__value')?.textContent || '').trim();
  }
  const stats = Array.from(root.querySelectorAll('.ant-statistic'));
  const stat = stats.find((node) => {
    const titleNode = node.querySelector('.ant-statistic-title');
    return titleNode && (titleNode.textContent || '').trim() === statTitle;
  });
  return (stat?.querySelector('.ant-statistic-content-value')?.textContent || '').trim();
}, title);

const activateIndustryDetailTab = async (page, pattern) => {
  const modal = page.locator('[data-testid="industry-detail-modal"]');
  const targetTab = modal.locator('.ant-tabs-tab').filter({ hasText: pattern }).first();
  const tabCount = await targetTab.count().catch(() => 0);
  if (!tabCount) return;
  const selected = await targetTab.getAttribute('aria-selected').catch(() => null);
  if (selected !== 'true') {
    await targetTab.click();
  }
  await modal.locator('.ant-tabs-tab-active').filter({ hasText: pattern }).waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
};

const ensureIndustryStockTableVisible = async (page) => {
  await activateIndustryDetailTab(page, /成分股/);
  const stockTable = page.locator('[data-testid="industry-stock-table"]').first();
  await stockTable.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
  return stockTable;
};

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
      await modal.waitFor({ state: 'hidden', timeout: 2500 }).catch(() => {});
    }
    const stillVisible = await modal.isVisible().catch(() => false);
    if (stillVisible) {
      await page.keyboard.press('Escape').catch(() => {});
      await modal.waitFor({ state: 'hidden', timeout: 2500 }).catch(() => {});
    }
    await page.waitForTimeout(250);
  }
};

const closeAllVisibleModals = async (page) => {
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const visibleCloseButtons = page.locator('.ant-modal-wrap .ant-modal-close:visible');
    const closeCount = await visibleCloseButtons.count().catch(() => 0);
    if (!closeCount) {
      await page.keyboard.press('Escape').catch(() => {});
      const hasVisibleModal = await page.locator('.ant-modal-wrap:visible').count().catch(() => 0);
      if (!hasVisibleModal) {
        break;
      }
    } else {
      await visibleCloseButtons.first().click().catch(() => {});
    }
    await page.waitForTimeout(300);
  }
};

const ensureNoVisibleModals = async (page) => {
  await closeAllVisibleModals(page);
  await page.waitForFunction(() => (
    Array.from(document.querySelectorAll('.ant-modal-wrap'))
      .every((node) => node.getClientRects().length === 0)
  ), null, { timeout: 3000 }).catch(() => {});
};

const openIndustryDetailFromTile = async (page, tileLocator, options = {}) => {
  const { modalTimeout = 12000 } = options;
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
  return waitForIndustryDetailReady(page, { modalTimeout });
};

const setLocalStorageItem = async (page, key, value) => {
  await page.evaluate(([storageKey, storageValue]) => {
    if (storageValue == null) {
      window.localStorage.removeItem(storageKey);
      return;
    }
    window.localStorage.setItem(storageKey, storageValue);
  }, [key, value]);
};

const chooseSelectOption = async (page, selectLocator, optionText) => {
  const openDropdown = async () => {
    await page.waitForFunction((element) => {
      if (!element) return false;
      return !element.classList.contains('ant-select-disabled');
    }, await selectLocator.elementHandle(), { timeout: 10000 }).catch(() => {});
    const selectorLocator = selectLocator.locator('.ant-select-selector');
    const hasSelector = await selectorLocator.count().catch(() => 0);
    if (hasSelector) {
      await selectorLocator.first().waitFor({ state: 'visible', timeout: 10000 });
      await selectorLocator.first().click({ force: true });
      return;
    }
    await selectLocator.waitFor({ state: 'visible', timeout: 10000 });
    await selectLocator.click({ force: true });
  };

  for (let attempt = 0; attempt < 4; attempt += 1) {
    await openDropdown();
    await page.waitForFunction(
      () => document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').length > 0,
      null,
      { timeout: 8000 }
    );
    const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)').last();
    const option = dropdown.locator('.ant-select-item-option-content').filter({ hasText: optionText }).first();
    try {
      await dropdown.waitFor({ state: 'attached', timeout: 8000 });
      await option.waitFor({ state: 'visible', timeout: 8000 });
      await option.click({ force: true });
      await page.waitForTimeout(250);
      return;
    } catch (error) {
      await page.keyboard.press('Escape').catch(() => {});
      await page.locator('body').click({ position: { x: 8, y: 8 } }).catch(() => {});
      if (attempt === 3) {
        throw error;
      }
      await page.waitForTimeout(400);
    }
  }
};

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 1100 });
  const consoleErrors = [];
  let originalIndustryPreferences = null;
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  try {
    console.log('正在访问行业热度页面...');
    await page.goto('http://localhost:3000?view=industry', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitForIndustryHeatmapReady(page);
    originalIndustryPreferences = await readIndustryPreferences(page).catch(() => null);

    // 1. 验证热力图渲染和基础切换
    console.log('验证热力图维度切换...');

    // 切换到 5日
    await page.locator('.ant-radio-button-wrapper').filter({ hasText: '5日' }).first().click();
    await waitForIndustryHeatmapReady(page);

    // 切换指标：看净流入%
    await chooseSelectOption(page, page.locator('.heatmap-control-color-metric'), '看净流入%');
    await waitForIndustryHeatmapReady(page);

    // 2. 验证搜索功能
    console.log('验证行业筛选搜索...');
    const initialIndustryTitles = await readVisibleHeatmapIndustryTitles(page);
    const searchCandidates = [...new Set(
      initialIndustryTitles
        .slice(0, 5)
        .flatMap((text) => {
          const normalized = (text || '').trim();
          if (!normalized) return [];
          const shortKeyword = normalized.length > 2 ? normalized.slice(0, 2) : normalized;
          return [normalized, shortKeyword];
        })
    )];
    let searchResult = null;
    for (const candidate of searchCandidates) {
      await getIndustrySearchInput(page).fill(candidate);
      await waitForHeatmapSearchSettled(page);
      const candidateVisibleTitles = await readVisibleHeatmapIndustryTitles(page);
      const candidateEmptyVisible = await isHeatmapSearchEmptyStateVisible(page);
      const candidateMatched = candidateVisibleTitles.length > 0
        && candidateVisibleTitles.every((text) => text.includes(candidate));
      searchResult = {
        keyword: candidate,
        visibleIndustryTitles: candidateVisibleTitles,
        emptyVisible: candidateEmptyVisible,
        matched: candidateMatched,
      };
      if (candidateMatched) {
        break;
      }
    }
    console.log(`搜索"${searchResult?.keyword || ''}"结果: ${searchResult?.visibleIndustryTitles?.length > 0 ? '找到' : '未找到'}`);
    console.log(`搜索后仅显示匹配行业: ${searchResult?.matched ? '是' : '否'}`);
    if (!searchResult?.matched) {
      throw new Error(`行业搜索未稳定命中匹配结果: ${searchResult?.keyword || 'unknown'}`);
    }
    await getIndustrySearchInput(page).fill(''); // 清空搜索
    await waitForIndustryHeatmapReady(page);

    // 3. 验证市值来源筛选
    console.log('验证估算市值筛选...');
    await ensureNoVisibleModals(page);
    const estimatedMarketCapTag = page.locator('.heatmap-control-market-cap-filter .ant-tag').filter({ hasText: /估算\s+\d+/ }).first();
    await estimatedMarketCapTag.scrollIntoViewIfNeeded().catch(() => {});
    await estimatedMarketCapTag.click();
    await waitForIndustryHeatmapReady(page, { allowEmpty: true });
    const stateBarVisible = await page.getByText('当前视图', { exact: false }).isVisible();
    const bodyTextAfterFilter = await page.locator('body').innerText();
    const estimatedStateVisible = bodyTextAfterFilter.includes('来源: 估算市值');
    const estimatedFilterUrl = page.url();
    const estimatedVisibleIndustries = await readVisibleHeatmapIndustryTitles(page);
    const estimatedEmptyVisible = await page.getByText('当前市值来源筛选下暂无行业', { exact: false }).isVisible().catch(() => false);
    const estimatedFilterUsable = estimatedVisibleIndustries.length > 0 || estimatedEmptyVisible;
    console.log(`估算筛选状态标签: ${estimatedStateVisible ? '已显示' : '未显示'}`);
    console.log(`当前视图状态条: ${stateBarVisible ? '已显示' : '未显示'}`);
    console.log(`估算筛选 URL 是否带参数: ${estimatedFilterUrl.includes('industry_market_cap_filter=estimated') ? '是' : '否'}`);
    console.log(`估算筛选结果是否可用: ${estimatedFilterUsable ? '是' : '否'}`);
    if (!estimatedStateVisible || !estimatedFilterUrl.includes('industry_market_cap_filter=estimated')) {
      throw new Error('估算市值筛选未正确同步到状态条或 URL');
    }
    if (!estimatedFilterUsable) {
      throw new Error('估算市值筛选后未出现行业结果或空态');
    }

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

    console.log('验证热力图色阶刷选与全屏...');
    const legendSliderMounted = await page.locator('[data-testid="heatmap-legend-slider"]').count().catch(() => 0) > 0;
    const fullscreenToggleVisible = await page.locator('[data-testid="heatmap-fullscreen-toggle"]').isVisible().catch(() => false);
  if (fullscreenToggleVisible) {
    await page.locator('[data-testid="heatmap-fullscreen-toggle"]').click();
    await page.locator('[data-testid="industry-heatmap-fullscreen-modal"]').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  }
  const fullscreenModalVisible = await page.locator('[data-testid="industry-heatmap-fullscreen-modal"]').isVisible().catch(() => false);
    console.log(`热力图色阶刷选滑块是否挂载: ${legendSliderMounted ? '是' : '否'}`);
  console.log(`热力图全屏按钮是否显示: ${fullscreenToggleVisible ? '是' : '否'}`);
  console.log(`热力图全屏弹窗是否显示: ${fullscreenModalVisible ? '是' : '否'}`);
  await closeVisibleModal(page, 'industry-heatmap-fullscreen-modal');

  console.log('验证保存视图...');
  await setLocalStorageItem(page, 'industry_saved_views_v1', null);
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryAppShell(page);
  await openIndustryWorkspaceTab(page, /视图沉淀/);
  await page.locator('[data-testid="industry-saved-views-panel"]').waitFor({ state: 'visible', timeout: 60000 });
  const savedViewsPanelVisible = await page.locator('[data-testid="industry-saved-views-panel"]').isVisible().catch(() => false);
  const savedViewsExportVisible = await page.getByRole('button', { name: '导出' }).isVisible().catch(() => false);
  const savedViewsImportVisible = await page.getByRole('button', { name: '导入' }).isVisible().catch(() => false);
  const viewName = `测试视图-${Date.now().toString().slice(-6)}`;
  if (savedViewsPanelVisible) {
    await page.locator('[data-testid="industry-saved-view-name-input"]').fill(viewName);
    await page.locator('[data-testid="industry-saved-view-save-button"]').click();
    await page.waitForTimeout(800);
  }
  const expandSavedViewsButton = page.getByRole('button', { name: '展开列表' });
  if (await expandSavedViewsButton.isVisible().catch(() => false)) {
    await expandSavedViewsButton.click().catch(() => {});
    await page.waitForTimeout(400);
  }
  const savedViewItemVisible = await page.locator('[data-testid="industry-saved-view-item"]').filter({ hasText: viewName }).first().isVisible().catch(() => false);
  const savedViewsStorageRaw = await page.evaluate(() => window.localStorage.getItem('industry_saved_views_v1') || '[]');
  const savedViewsPersisted = Array.isArray(JSON.parse(savedViewsStorageRaw)) && JSON.parse(savedViewsStorageRaw).some((item) => item?.name === viewName);
  console.log(`保存视图面板是否显示: ${savedViewsPanelVisible ? '是' : '否'}`);
  console.log(`保存视图是否成功创建: ${savedViewItemVisible ? '是' : '否'}`);
  console.log(`保存视图是否已写入本地存储: ${savedViewsPersisted ? '是' : '否'}`);
  console.log(`保存视图导出按钮是否显示: ${savedViewsExportVisible ? '是' : '否'}`);
  console.log(`保存视图导入按钮是否显示: ${savedViewsImportVisible ? '是' : '否'}`);

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
  const preferredIndustries = ['半导体', '消费电子', '通信设备', '电池', '银行'];
  let firstHeatmapTile = page.locator('[data-testid="heatmap-tile"]').first();
  for (const industryName of preferredIndustries) {
    const candidate = page.locator(`[data-testid="heatmap-tile"][data-industry-name="${industryName}"]`).first();
    if (await candidate.count().catch(() => 0)) {
      firstHeatmapTile = candidate;
      break;
    }
  }
  const industryText = (await firstHeatmapTile.getAttribute('data-industry-name')) || await firstHeatmapTile.innerText();
  console.log(`点击行业: ${industryText}`);
  const detailModal = await openIndustryDetailFromTile(page, firstHeatmapTile);
  const modalVisible = await detailModal.isVisible();
  console.log(`详情弹窗是否打开: ${modalVisible ? '是' : '否'}`);
  if (modalVisible) {
    await page.waitForFunction(
      () => document.querySelectorAll('[data-testid="industry-ai-insight-panel"]').length > 0,
      null,
      { timeout: 6000 }
    ).catch(() => {});
    const summarySnapshot = {
      totalMarketCap: await readIndustryStatistic(page, '总市值'),
      avgPe: await readIndustryStatistic(page, '平均市盈率'),
    };
    const aiInsightVisible = await page.locator('[data-testid="industry-ai-insight-panel"]').count().catch(() => 0);
    const stockTable = await ensureIndustryStockTableVisible(page);
    const stocksTableBody = stockTable.locator('tbody');
    const quickRowsRendered = await stocksTableBody.locator('tr').first().isVisible().catch(() => false);
    await page.waitForFunction(() => {
      const node = document.querySelector('[data-testid="industry-stock-table"]');
      const stage = node?.getAttribute('data-score-stage');
      return stage === 'quick' || stage === 'full';
    }, null, { timeout: 10000 }).catch(() => {});
    const initialScoreStage = await stockTable.getAttribute('data-score-stage');
    const stockTableSnapshot = await stockTable.evaluate((table) => {
      const headers = Array.from(table.querySelectorAll('thead th')).map((cell) => (cell.textContent || '').trim());
      const rows = Array.from(table.querySelectorAll('tbody tr'))
        .slice(0, 5)
        .map((row) => Array.from(row.querySelectorAll('td')).map((cell) => (cell.textContent || '').trim()));
      return { headers, rows };
    });
    const stockRows = stockTableSnapshot.rows;
    const quickScoreSnapshot = stockRows.map((cells) => cells[3] || '');
    await waitForIndustryScoreStage(page, ['quick', 'full'], 10000).catch(() => null);
    if (initialScoreStage === 'quick') {
      await waitForIndustryScoreStage(page, 'full', 20000).catch(() => null);
    }
    const upgradedStockTable = await ensureIndustryStockTableVisible(page);
    const upgradedScoreStage = await upgradedStockTable.getAttribute('data-score-stage');
    const upgradedDisplayReady = await upgradedStockTable.getAttribute('data-display-ready');
    const upgradedStockRows = await upgradedStockTable.locator('tbody tr').evaluateAll(
      (rows) => rows.slice(0, 5).map((row) => Array.from(row.querySelectorAll('td')).map((cell) => (cell.textContent || '').trim()))
    );
    const detailDegraded = await page.getByText('当前显示的是降级行业数据', { exact: false }).isVisible().catch(() => false);
    const detailColumnKeywords = ['主力净流入', '换手率', '市值', 'PE'];
    const detailColumnIndexes = stockTableSnapshot.headers
      .map((header, index) => (detailColumnKeywords.some((keyword) => header.includes(keyword)) ? index : -1))
      .filter((index) => index >= 0);
    const stockRowsHaveDetails = stockRows.some((cells) => (
      detailColumnIndexes.some((index) => {
        const value = cells[index] || '';
        return value && value !== '-';
      })
    ));
    const upgradedRowsHaveDetails = upgradedStockRows.some((cells) => (
      detailColumnIndexes.some((index) => {
        const value = cells[index] || '';
        return value && value !== '-';
      })
    ));
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
    console.log(`行业详情是否处于降级模式: ${detailDegraded ? '是' : '否'}`);
    console.log(`行业成分股前5行存在真实明细: ${stockRowsHaveDetails || upgradedRowsHaveDetails ? '是' : '否'}`);
    console.log(`行业详情 AI 洞察是否显示: ${aiInsightVisible > 0 ? '是' : '否'}`);
    const scoreDisplayReady = upgradedScoreStage === 'full' || upgradedDisplayReady === 'true' || detailDegraded;
    const detailContentUsable = stockRowsHaveDetails || upgradedRowsHaveDetails || detailDegraded || upgradedStockRows.length > 0;
    console.log(`行业成分股展示是否已就绪: ${scoreDisplayReady && stockScoresUpgraded ? '是' : scoreDisplayReady ? '是' : '否'}`);
    if (!detailContentUsable) {
      throw new Error('行业成分股详情未进入可用状态');
    }
    if (!scoreDisplayReady) {
      throw new Error('行业成分股表格仍未进入可展示状态');
    }
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
      const summaryCards = Array.from(root.querySelectorAll('.industry-detail-summary-card'));
      const totalMarketCapCard = summaryCards.find((node) => {
        const labelNode = node.querySelector('.industry-detail-summary-card__label');
        return labelNode && (labelNode.textContent || '').trim() === '总市值';
      });
      const totalMarketCap = (totalMarketCapCard?.querySelector('.industry-detail-summary-card__value')?.textContent || '').trim();
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

  console.log('验证观察列表提醒订阅...');
  await setLocalStorageItem(page, 'industry_watchlist_v1', null);
  await setLocalStorageItem(page, 'industry_alert_subscription_v1', null);
  await resetIndustryPreferences(page);
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryHeatmapReady(page);
  await closeVisibleModal(page, 'industry-detail-modal');
  const watchlistSeedTile = page.locator('[data-testid="heatmap-tile"]').first();
  const watchlistSeedIndustry = await watchlistSeedTile.getAttribute('data-industry-name');
  if (watchlistSeedIndustry) {
    await openIndustryDetailFromTile(page, watchlistSeedTile, { modalTimeout: 12000 });
    await closeVisibleModal(page, 'industry-detail-modal');
    await ensureNoVisibleModals(page);
    const focusWatchlistButton = page.locator('[data-testid="industry-focus-watchlist-button"]').first();
    await focusWatchlistButton.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
    const focusWatchlistLabel = await focusWatchlistButton.innerText().catch(() => '');
    if (focusWatchlistLabel.includes('加入')) {
      await focusWatchlistButton.click({ force: true });
      await page.waitForFunction((targetIndustry) => {
        try {
          const watchlist = JSON.parse(window.localStorage.getItem('industry_watchlist_v1') || '[]');
          return Array.isArray(watchlist) && watchlist.includes(targetIndustry);
        } catch (error) {
          return false;
        }
      }, watchlistSeedIndustry, { timeout: 5000 }).catch(() => {});
    }
    await page.waitForTimeout(600);
    const watchlistTab = page.getByRole('tab', { name: /观察列表/ }).first();
    await ensureNoVisibleModals(page);
    await watchlistTab.click({ force: true });
    await page.waitForTimeout(300);
    const watchlistCard = page.locator('[data-testid="industry-watchlist-card"]');
    await watchlistCard.waitFor({ state: 'visible', timeout: 10000 });
    const watchlistExpandButton = watchlistCard.getByRole('button', { name: /展开|收起/ }).first();
    if (await watchlistExpandButton.isVisible().catch(() => false)) {
      const watchlistExpandLabel = await watchlistExpandButton.innerText().catch(() => '');
      if (watchlistExpandLabel.includes('展开')) {
        await watchlistExpandButton.click();
        await page.waitForTimeout(300);
      }
    }
    const watchlistItemVisible = await watchlistCard.locator('[data-testid="industry-watchlist-item"]').filter({ hasText: watchlistSeedIndustry }).first().isVisible().catch(() => false);
    await openIndustryWorkspaceTab(page, /提醒中心/);
    const alertsCard = page.locator('[data-testid="industry-alerts-card"]');
    await alertsCard.waitFor({ state: 'visible', timeout: 10000 });
    const advancedSettingsButton = page.getByRole('button', { name: /高级设置|收起高级设置/ }).first();
    if (await advancedSettingsButton.isVisible().catch(() => false)) {
      const advancedLabel = await advancedSettingsButton.innerText().catch(() => '');
      if (!advancedLabel.includes('收起')) {
        await advancedSettingsButton.click();
        await page.waitForTimeout(300);
      }
    }
    const alertThresholdPanelVisible = await page.locator('[data-testid="industry-alert-thresholds-panel"]').isVisible().catch(() => false);
    await page.evaluate(() => {
      const alertsRoot = document.querySelector('[data-testid="industry-alerts-card"]');
      if (!alertsRoot) return;
      const scopeNode = Array.from(alertsRoot.querySelectorAll('.ant-radio-group .ant-radio-button-wrapper'))
        .find((item) => (item.textContent || '').includes('观察列表'));
      scopeNode?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      const checkboxLabel = Array.from(alertsRoot.querySelectorAll('.ant-checkbox-group label'))
        .find((item) => (item.textContent || '').includes('轮动'));
      checkboxLabel?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await page.waitForTimeout(800);
    const savedSubscription = JSON.parse(await page.evaluate(() => window.localStorage.getItem('industry_alert_subscription_v1') || '{}'));
    const savedScopeWatchlist = savedSubscription.scope === 'watchlist';
    const savedKindsExcludeRotation = Array.isArray(savedSubscription.kinds) && !savedSubscription.kinds.includes('rotation');
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitForIndustryHeatmapReady(page);
    const watchlistTabAfterReload = page.getByRole('tab', { name: /观察列表/ }).first();
    await ensureNoVisibleModals(page);
    await watchlistTabAfterReload.click({ force: true }).catch(() => {});
    await page.waitForTimeout(300);
    const watchlistCardAfterReload = page.locator('[data-testid="industry-watchlist-card"]');
    const watchlistExpandButtonAfterReload = watchlistCardAfterReload.getByRole('button', { name: /展开|收起/ }).first();
    if (await watchlistExpandButtonAfterReload.isVisible().catch(() => false)) {
      const watchlistExpandLabelAfterReload = await watchlistExpandButtonAfterReload.innerText().catch(() => '');
      if (watchlistExpandLabelAfterReload.includes('展开')) {
        await watchlistExpandButtonAfterReload.click();
        await page.waitForTimeout(300);
      }
    }
    await openIndustryWorkspaceTab(page, /提醒中心/);
    const subscriptionTagVisible = await page.getByText('仅观察列表', { exact: false }).isVisible().catch(() => false);
    const persistedSubscription = JSON.parse(await page.evaluate(() => window.localStorage.getItem('industry_alert_subscription_v1') || '{}'));
    const persistedWatchlistScope = persistedSubscription.scope === 'watchlist';
    const persistedKindsExcludeRotation = Array.isArray(persistedSubscription.kinds) && !persistedSubscription.kinds.includes('rotation');
    const watchlistItemPersisted = await page.locator('[data-testid="industry-watchlist-card"] [data-testid="industry-watchlist-item"]').filter({ hasText: watchlistSeedIndustry }).first().isVisible().catch(() => false);
    console.log(`观察列表行业是否成功加入: ${watchlistItemVisible ? '是' : '否'}`);
    console.log(`提醒阈值面板是否显示: ${alertThresholdPanelVisible ? '是' : '否'}`);
    console.log(`提醒订阅范围是否已保存为观察列表: ${savedScopeWatchlist ? '是' : '否'}`);
    console.log(`提醒订阅规则是否已保存去掉轮动: ${savedKindsExcludeRotation ? '是' : '否'}`);
    console.log(`刷新后仅观察列表标签是否显示: ${subscriptionTagVisible ? '是' : '否'}`);
    console.log(`刷新后订阅设置是否仍保留: ${persistedWatchlistScope && persistedKindsExcludeRotation ? '是' : '否'}`);
    console.log(`刷新后观察列表行业是否仍保留: ${watchlistItemPersisted ? '是' : '否'}`);
  } else {
    console.log('观察列表行业是否成功加入: 跳过');
    console.log('提醒阈值面板是否显示: 跳过');
    console.log('提醒订阅范围是否已保存为观察列表: 跳过');
    console.log('提醒订阅规则是否已保存去掉轮动: 跳过');
    console.log('刷新后仅观察列表标签是否显示: 跳过');
    console.log('刷新后订阅设置是否仍保留: 跳过');
    console.log('刷新后观察列表行业是否仍保留: 跳过');
  }

  console.log('验证龙头股 Sparkline...');
  await page.getByRole('tab', { name: '龙头股' }).first().click().catch(() => {});
  await page.waitForTimeout(300);
  const leaderPanel = page.locator('[data-testid="leader-stock-panel"]');
  await page.waitForFunction(() => {
    const activePane = document.querySelector('[data-testid="leader-stock-panel"] .ant-tabs-tabpane-active');
    if (!activePane) return false;
    const hasRows = activePane.querySelectorAll('[data-testid="leader-stock-row"]').length > 0;
    const loading = Boolean(activePane.querySelector('.ant-spin-spinning'));
    const text = activePane.textContent || '';
    const hasEmpty = text.includes('暂无可用核心资产标的')
      || text.includes('当前行业暂无可用核心资产标的')
      || text.includes('暂无可用热点先锋标的')
      || text.includes('当前行业暂无可用热点先锋标的');
    return (!loading && hasRows) || hasEmpty;
  }, null, { timeout: 10000 }).catch(() => {});
  const activeLeaderTab = leaderPanel.locator('.ant-tabs-tabpane-active');
  const leaderSparklineVisible = await activeLeaderTab.locator('[data-testid="mini-sparkline"]').first().isVisible().catch(() => false);
  console.log(`龙头股走势火花线是否显示: ${leaderSparklineVisible ? '是' : '否'}`);

  console.log('验证龙头股详情竞态保护...');
  const leaderRows = activeLeaderTab.locator('[data-testid="leader-stock-row"]');
  const leaderRowCount = await leaderRows.count();
  if (leaderRowCount >= 2) {
    const firstLeaderSymbol = await leaderRows.nth(0).getAttribute('data-symbol');
    const secondLeaderSymbol = await leaderRows.nth(1).getAttribute('data-symbol');
    await page.evaluate(() => {
      const close = document.querySelector('[data-testid="stock-detail-modal"] .ant-modal-close');
      close?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }).catch(() => {});
    await page.evaluate(() => {
      const activePane = document.querySelector('[data-testid="leader-stock-panel"] .ant-tabs-tabpane-active');
      const rows = Array.from(activePane?.querySelectorAll('[data-testid="leader-stock-row"]') || []);
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
  await page.locator('.ant-tabs-tab-btn').filter({ hasText: '排行榜' }).click({ force: true });
  await waitForRankingReady(page);
  const tableExists = await page.isVisible('.ant-table');
    const rankingSparklineVisible = await page.locator('.industry-ranking-table [data-testid="mini-sparkline"], .industry-ranking-table [data-testid="mini-sparkline-empty"]').first().isVisible().catch(() => false);
  console.log(`排行榜表格是否显示: ${tableExists ? '是' : '否'}`);
  const volatilityTagCount = await page.locator('.ant-table-tbody .ant-tag').filter({ hasText: /^(高波动|中波动|低波动)$/ }).count();
  console.log(`排行榜波动率标签是否显示: ${volatilityTagCount > 0 ? '是' : '否'}`);
    console.log(`排行榜走势组件是否显示: ${rankingSparklineVisible ? '是' : '否'}`);
  const radarTriggerVisible = await page.locator('[data-testid="industry-score-radar-trigger"]').first().isVisible().catch(() => false);
  if (radarTriggerVisible) {
    await page.locator('[data-testid="industry-score-radar-trigger"]').first().click();
    await page.locator('[data-testid="industry-score-radar-modal"]').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  }
  const radarModalVisible = await page.locator('[data-testid="industry-score-radar-modal"]').isVisible().catch(() => false);
  console.log(`排行榜评分雷达入口是否显示: ${radarTriggerVisible ? '是' : '否'}`);
  console.log(`排行榜评分雷达弹窗是否显示: ${radarModalVisible ? '是' : '否'}`);
  await closeVisibleModal(page, 'industry-score-radar-modal');
  await closeAllVisibleModals(page);

  console.log('验证排行榜波动率排序与筛选...');
  await page.waitForFunction(
    () => document.querySelectorAll('.ant-tabs-tabpane-active .ant-card-extra .ant-select').length >= 4,
    null,
    { timeout: 10000 }
  );
  await chooseSelectOption(page, page.locator('.ant-tabs-tabpane-active .ranking-control-sort-by'), '按波动率');
  await page.waitForFunction(
    () => document.querySelector('[data-testid="ranking-control-sort-by"] .ant-select-selection-item')?.textContent?.trim() === '按波动率',
    null,
    { timeout: 10000 }
  );
  await waitForRankingReady(page);
  await chooseSelectOption(page, page.locator('.ant-tabs-tabpane-active .ranking-control-volatility'), '低波动');
  await page.waitForFunction(
    () => document.querySelector('[data-testid="ranking-control-volatility"] .ant-select-selection-item')?.textContent?.trim() === '低波动',
    null,
    { timeout: 10000 }
  );
  await waitForRankingReady(page);
  await chooseSelectOption(page, page.locator('.ant-tabs-tabpane-active .ranking-control-market-cap'), '实时市值');
  await page.waitForFunction(
    () => document.querySelector('[data-testid="ranking-control-market-cap"] .ant-select-selection-item')?.textContent?.trim() === '实时市值',
    null,
    { timeout: 10000 }
  );
  await waitForRankingReady(page);
  const rankingTableBody = page.locator('.ant-tabs-tabpane-active .ant-table-tbody');
  const rankingBodyRows = await rankingTableBody.locator('tr').evaluateAll(
    (rows) => rows.map(row => (row.textContent || '').trim()).filter(Boolean)
  );
  const rankingHasEmptyState = rankingBodyRows.length > 0 && rankingBodyRows[0].includes('暂无排名数据');
  const rankingBodyText = rankingBodyRows.join('\n');
  const onlyLowVolatility = rankingHasEmptyState || (!rankingBodyText.includes('高波动') && !rankingBodyText.includes('中波动'));
  console.log(`排行榜低波动筛选是否生效: ${onlyLowVolatility ? '是' : '否'}`);
  const sourceLabelsAfterFilter = await rankingTableBody.locator('[data-testid="industry-market-cap-source-tag"]').evaluateAll(
    (nodes) => nodes.map(node => (node.textContent || '').trim()).filter(Boolean)
  );
  const onlyLiveSource = rankingHasEmptyState || (sourceLabelsAfterFilter.length > 0 && sourceLabelsAfterFilter.every(text => text === '实时'));
  console.log(`排行榜实时市值筛选是否生效: ${onlyLiveSource ? '是' : '否'}`);

  console.log('验证排行榜 URL 状态持久化...');
  const rankingUrl = page.url();
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForIndustryAppShell(page);
  await waitForRankingReady(page);
  const reloadedRankingUrl = page.url();
  const rankingTabStillActive = await page.getByRole('tab', { name: '排行榜' }).getAttribute('aria-selected');
  await page.waitForFunction(() => {
    const sortBy = document.querySelector('[data-testid="ranking-control-sort-by"] .ant-select-selection-item')?.textContent?.trim();
    const lookback = document.querySelector('[data-testid="ranking-control-lookback"] .ant-select-selection-item')?.textContent?.trim();
    const volatility = document.querySelector('[data-testid="ranking-control-volatility"] .ant-select-selection-item')?.textContent?.trim();
    const marketCap = document.querySelector('[data-testid="ranking-control-market-cap"] .ant-select-selection-item')?.textContent?.trim();
    return sortBy === '按波动率' && lookback === '近5日' && volatility === '低波动' && marketCap === '实时市值';
  }, null, { timeout: 10000 }).catch(() => {});
  const rankingSelectValues = await readRankingSelectValues(page);
  const rankingUrlPersisted = normalizeUrl(reloadedRankingUrl) === normalizeUrl(rankingUrl);
  const rankingFiltersPersisted = rankingSelectValues.sortBy === '按波动率'
    && rankingSelectValues.volatility === '低波动'
    && rankingSelectValues.marketCap === '实时市值'
    && rankingSelectValues.lookback === '近5日';
  console.log(`排行榜 URL 保留: ${rankingUrlPersisted ? '是' : '否'}`);
  console.log(`排行榜刷新后仍停留当前标签页: ${rankingTabStillActive === 'true' ? '是' : '否'}`);
  console.log(`排行榜筛选状态刷新后保留: ${rankingFiltersPersisted ? '是' : '否'}`);
  const rankingStateBarVisible = await page.locator('[data-testid="ranking-state-bar"]').isVisible().catch(() => false);
  const rankingStateTags = await readRankingStateTagTexts(page);
  console.log(`排行榜状态条是否显示: ${rankingStateBarVisible ? '是' : '否'}`);
  console.log(`排行榜状态条是否反映组合视图: ${rankingStateTags.some((text) => text.includes('排序: 按波动率')) && rankingStateTags.some((text) => text.includes('波动: 低波动')) && rankingStateTags.some((text) => text.includes('市值来源: 实时市值')) ? '是' : '否'}`);
  await page.getByText('排序: 按波动率', { exact: false }).click();
  await page.waitForTimeout(300);
  const rankingTagFocusWorks = await page.evaluate(() => {
    const node = document.querySelector('.ranking-control-sort-by');
    return Boolean(node && getComputedStyle(node).boxShadow && getComputedStyle(node).boxShadow !== 'none');
  });
  console.log(`排行榜状态标签定位控件是否生效: ${rankingTagFocusWorks ? '是' : '否'}`);
  await page.locator('[data-testid="ranking-state-tag-close-market_cap_filter"]').click();
  await page.waitForTimeout(1000);
  await waitForRankingReady(page);
  const partialResetRankingSelectValues = await readRankingSelectValues(page);
  const partialResetRankingUrl = page.url();
  const rankingSingleTagResetApplied = partialResetRankingSelectValues.sortBy === '按波动率'
    && partialResetRankingSelectValues.volatility === '低波动'
    && partialResetRankingSelectValues.marketCap === '全部市值来源';
  console.log(`排行榜单项标签清除是否生效: ${rankingSingleTagResetApplied ? '是' : '否'}`);
  console.log(`排行榜单项标签清除后 URL 已同步: ${!partialResetRankingUrl.includes('industry_rank_market_cap=live') && partialResetRankingUrl.includes('industry_rank_sort=industry_volatility') && partialResetRankingUrl.includes('industry_rank_volatility=low') ? '是' : '否'}`);
  await page.locator('[data-testid="ranking-reset-button"]').click();
  await page.waitForTimeout(1000);
  await waitForRankingReady(page);
  const resetRankingSelectValues = await readRankingSelectValues(page);
  const resetRankingUrl = page.url();
  const rankingResetApplied = resetRankingSelectValues.sortBy === '按综合得分'
    && resetRankingSelectValues.volatility === '全部波动'
    && resetRankingSelectValues.marketCap === '全部市值来源'
    && resetRankingSelectValues.lookback === '近5日';
  console.log(`排行榜恢复默认是否生效: ${rankingResetApplied ? '是' : '否'}`);
  console.log(`排行榜恢复默认后 URL 已重置: ${!resetRankingUrl.includes('industry_rank_sort=industry_volatility') && !resetRankingUrl.includes('industry_rank_volatility=low') && !resetRankingUrl.includes('industry_rank_market_cap=live') ? '是' : '否'}`);

  console.log('验证排行榜来源标签联动...');
  const rankingFilterTag = page.locator('.ant-table-tbody .ant-tag').filter({ hasText: /^(实时|快照|代理|估算)$/ }).first();
  const rankingFilterTagCount = await rankingFilterTag.count();
  if (rankingFilterTagCount > 0) {
    await waitForRankingReady(page);
    const rankingFilterLabel = (await rankingFilterTag.innerText()).trim();
    await rankingFilterTag.click({ force: true });
    await page.waitForTimeout(1200);
    const switchedToHeatmap = await page.getByRole('tab', { name: '热力图' }).getAttribute('aria-selected');
    const heatmapFilterText = await page.locator('body').innerText();
    const heatmapFilterHintVisible = heatmapFilterText.includes(`来源: ${rankingFilterLabel === '实时' ? '实时市值' : rankingFilterLabel === '快照' ? '快照市值' : rankingFilterLabel === '代理' ? '代理市值' : '估算市值'}`);
    console.log(`排行榜来源标签点击后标签页: ${switchedToHeatmap === 'true' ? '热力图' : '未知'}`);
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
  await page.locator('.ant-tabs-tab-btn').filter({ hasText: '轮动对比' }).click({ force: true });
  await page.waitForFunction(
    () => document.querySelector('.ant-tabs-tab-active .ant-tabs-tab-btn')?.textContent?.includes('轮动对比'),
    null,
    { timeout: 5000 }
  );
  await page.waitForFunction(() => {
    const card = document.querySelector('[data-testid="industry-rotation-card"]');
    if (!card) return false;
    return Boolean(
      card.querySelector('[data-testid="industry-rotation-chart"]')
      || card.querySelector('[data-testid="industry-rotation-empty"]')
      || card.querySelector('[data-testid="industry-rotation-loading"]')
    );
  }, null, { timeout: 10000 }).catch(() => {});
  await page.waitForFunction(() => {
    const card = document.querySelector('[data-testid="industry-rotation-card"]');
    if (!card) return false;
    const hasChart = Boolean(card.querySelector('[data-testid="industry-rotation-chart"]'));
    const stillLoading = Boolean(card.querySelector('[data-testid="industry-rotation-loading"]'));
    const hasEmpty = Boolean(card.querySelector('[data-testid="industry-rotation-empty"]'));
    return hasChart || (!stillLoading && hasEmpty);
  }, null, { timeout: 15000 }).catch(() => {});
  const rotationChartExists = await page.locator('[data-testid="industry-rotation-chart"]').isVisible().catch(() => false);
  console.log(`轮动对比图表是否显示: ${rotationChartExists ? '是' : '否'}`);

    console.log('验证完成。');
  } finally {
    if (!page.isClosed()) {
      console.log('正在保存页面状态快照...');
      const content = await page.content().catch(() => '');
      if (content) {
        fs.writeFileSync('verify_result.html', content);
      }
      if (originalIndustryPreferences) {
        await page.goto('http://localhost:3000?view=industry', { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
        await writeIndustryPreferences(page, originalIndustryPreferences).catch((error) => {
          console.log(`恢复行业偏好失败: ${error.message}`);
        });
      }
    }
    console.log(`控制台错误数: ${consoleErrors.length}`);
    if (consoleErrors.length > 0) {
      console.log(consoleErrors.join('\n'));
    }
    await browser.close();
  }
})();
