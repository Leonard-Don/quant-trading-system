// Shape guards for the deterministic fixture payloads handed to page.route()
// in tests/e2e/verify_backtest_workflow.js and verify_industry_features.js.
//
// The frontend code does not consume entire payloads — it waits on a small
// number of fields:
//   - BacktestDataHealthPanel.jsx requires data_sources to include at least one
//     entry with status === 'connected' before it stops the loading state.
//   - The same panel and summarizeProviderRuntimeStatus() treat
//     providerRuntime.success === false as a runtime failure, and read each
//     provider's circuit_breakers map.
//   - IndustryHeatmap.jsx renders only when initialData.industries.length > 0.
//   - useIndustryStocks.js only marks the industry stock table 'full' when
//     some row has scoreStage === 'full', and waits on stocks/status === 'ready'.
//
// If a future change drops one of those fields, the Playwright run fails far
// downstream inside an awaitFor with no hint that the fixture itself drifted
// out of contract. These helpers turn that into an early, named error.

const formatLabel = (label) => (label ? `${label}: ` : '');

const ensureObject = (value, label) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${formatLabel(label)}expected a plain object, received ${value === null ? 'null' : typeof value}`);
  }
};

const ensureNonEmptyString = (value, label) => {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${formatLabel(label)}expected a non-empty string, received ${JSON.stringify(value)}`);
  }
};

const ensureArray = (value, label, { minLength = 0 } = {}) => {
  if (!Array.isArray(value)) {
    throw new Error(`${formatLabel(label)}expected an array, received ${value === null ? 'null' : typeof value}`);
  }
  if (value.length < minLength) {
    throw new Error(`${formatLabel(label)}expected at least ${minLength} entr${minLength === 1 ? 'y' : 'ies'}, received ${value.length}`);
  }
};

const assertBacktestHealthShape = (fixture, label = 'backtest health fixture') => {
  ensureObject(fixture, label);
  ensureNonEmptyString(fixture.status, `${label}.status`);
  ensureObject(fixture.data_sources, `${label}.data_sources`);
  const entries = Object.entries(fixture.data_sources);
  if (entries.length === 0) {
    throw new Error(`${label}.data_sources must declare at least one source`);
  }
  const connected = entries.some(([, source]) => source && source.status === 'connected');
  if (!connected) {
    throw new Error(`${label}.data_sources must include at least one entry with status === 'connected' (BacktestDataHealthPanel.jsx waits on this)`);
  }
};

const assertProviderRuntimeShape = (fixture, label = 'provider runtime fixture') => {
  ensureObject(fixture, label);
  if (fixture.success === false) {
    throw new Error(`${label}.success must not be false (BacktestDataHealthPanel treats success === false as a runtime failure)`);
  }
  ensureObject(fixture.providers, `${label}.providers`);
  const providerEntries = Object.entries(fixture.providers);
  if (providerEntries.length === 0) {
    throw new Error(`${label}.providers must declare at least one provider`);
  }
  providerEntries.forEach(([providerKey, providerValue]) => {
    ensureObject(providerValue, `${label}.providers.${providerKey}`);
    ensureObject(providerValue.circuit_breakers, `${label}.providers.${providerKey}.circuit_breakers`);
  });
};

const assertIndustryHeatmapShape = (fixture, label = 'industry heatmap fixture') => {
  ensureObject(fixture, label);
  ensureArray(fixture.industries, `${label}.industries`, { minLength: 1 });
  fixture.industries.forEach((industry, index) => {
    ensureObject(industry, `${label}.industries[${index}]`);
    ensureNonEmptyString(industry.name, `${label}.industries[${index}].name`);
  });
};

const assertIndustryStocksShape = (fixture, label = 'industry stocks fixture') => {
  ensureArray(fixture, label, { minLength: 1 });
  const fullStage = fixture.some((stock) => stock && stock.scoreStage === 'full');
  if (!fullStage) {
    throw new Error(`${label} must include at least one stock with scoreStage === 'full' (useIndustryStocks.js promotes the table once any row reaches 'full')`);
  }
};

const assertIndustryStocksStatusShape = (fixture, label = 'industry stocks status fixture') => {
  ensureObject(fixture, label);
  if (fixture.status !== 'ready') {
    throw new Error(`${label}.status must be 'ready' (industry detail panel keeps spinning otherwise), received ${JSON.stringify(fixture.status)}`);
  }
};

module.exports = {
  assertBacktestHealthShape,
  assertProviderRuntimeShape,
  assertIndustryHeatmapShape,
  assertIndustryStocksShape,
  assertIndustryStocksStatusShape,
};
