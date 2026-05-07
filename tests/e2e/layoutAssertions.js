const assert = (condition, message) => {
  if (!condition) {
    throw new Error(message);
  }
};

const readLayoutMetrics = async (page) => page.evaluate(() => {
  const sider = document.querySelector('.app-main-sider');
  const body = document.querySelector('.app-main-body');
  const main = document.querySelector('main');
  const siderRect = sider?.getBoundingClientRect();
  const bodyRect = body?.getBoundingClientRect();
  const mainRect = main?.getBoundingClientRect();
  return {
    viewportWidth: window.innerWidth,
    sider: siderRect ? {
      left: siderRect.left,
      right: siderRect.right,
      width: siderRect.width,
    } : null,
    body: bodyRect ? {
      left: bodyRect.left,
      right: bodyRect.right,
      width: bodyRect.width,
    } : null,
    main: mainRect ? {
      left: mainRect.left,
      right: mainRect.right,
      width: mainRect.width,
      paddingLeft: Number.parseFloat(getComputedStyle(main).paddingLeft || '0'),
    } : null,
  };
});

const assertMainLayoutClearOfSidebar = async (page, label = 'layout') => {
  const metrics = await readLayoutMetrics(page);

  assert(metrics.sider, `${label}: missing fixed sider`);
  assert(metrics.body, `${label}: missing app main body`);
  assert(metrics.main, `${label}: missing main content`);
  const overlapTolerancePx = 4;
  const mainContentLeft = metrics.main.left + (metrics.main.paddingLeft || 0);
  assert(
    mainContentLeft >= metrics.sider.right - overlapTolerancePx,
    `${label}: main content overlaps sidebar ${JSON.stringify({ ...metrics, mainContentLeft })}`,
  );
  assert(
    metrics.body.right <= metrics.viewportWidth + 1,
    `${label}: main body overflows viewport ${JSON.stringify(metrics)}`,
  );
  assert(
    metrics.body.width > 640,
    `${label}: main body unexpectedly narrow ${JSON.stringify(metrics)}`,
  );
};

const assertNoHorizontalOverflow = async (page, selector, label = selector) => {
  const offenders = await page.evaluate((targetSelector) => {
    const nodes = Array.from(document.querySelectorAll(targetSelector));
    return nodes
      .map((node, index) => {
        const rect = node.getBoundingClientRect();
        return {
          index,
          className: node.className,
          clientWidth: node.clientWidth,
          scrollWidth: node.scrollWidth,
          rectWidth: rect.width,
          text: (node.textContent || '').trim().slice(0, 80),
        };
      })
      .filter((item) => item.scrollWidth > Math.ceil(item.clientWidth) + 2)
      .slice(0, 5);
  }, selector);

  assert(
    offenders.length === 0,
    `${label}: detected horizontal overflow ${JSON.stringify(offenders)}`,
  );
};

const assertOverlayLayoutUsesFullViewport = async (page, label = 'overlay layout') => {
  const previousViewport = page.viewportSize();
  await page.setViewportSize({ width: 900, height: 1000 });
  await page.waitForTimeout(300);
  const metrics = await readLayoutMetrics(page);
  assert(metrics.body, `${label}: missing app main body`);
  const maxAllowedOverlayOffset = Math.max(metrics.sider?.width || 0, 72) + 8;
  assert(
    metrics.body.right >= metrics.viewportWidth - 4,
    `${label}: body should reach the viewport right edge in overlay mode ${JSON.stringify(metrics)}`,
  );
  assert(
    metrics.body.width >= metrics.viewportWidth - maxAllowedOverlayOffset,
    `${label}: body should not keep a desktop sidebar gutter in overlay mode ${JSON.stringify({ ...metrics, maxAllowedOverlayOffset })}`,
  );
  if (previousViewport) {
    await page.setViewportSize(previousViewport);
    await page.waitForTimeout(300);
  }
};

module.exports = {
  assertMainLayoutClearOfSidebar,
  assertNoHorizontalOverflow,
  assertOverlayLayoutUsesFullViewport,
};
