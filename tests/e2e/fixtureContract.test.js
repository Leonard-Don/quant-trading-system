// Standalone Node smoke for tests/e2e/fixtureContract.js.
//
// fixtureContract guards the deterministic payloads that verify_backtest_workflow
// and verify_industry_features hand to page.route(). If a future refactor weakens
// one of those guards, the Playwright runs only fail far downstream after a long
// awaitFor timeout. This script re-runs each helper with intentionally broken
// inputs so drift in the helpers themselves is caught in seconds, with no browser.
//
// Run via: node tests/e2e/fixtureContract.test.js
// (Also wired as `npm run verify:fixture-contract` from tests/e2e/package.json.)
const {
  assertBacktestHealthShape,
  assertProviderRuntimeShape,
  assertIndustryHeatmapShape,
  assertIndustryStocksShape,
  assertIndustryStocksStatusShape,
} = require('./fixtureContract');

const failures = [];

const expectThrows = (label, fn, expectedFragment) => {
  let actualMessage = null;
  let threw = false;
  try {
    fn();
  } catch (err) {
    threw = true;
    actualMessage = err && err.message;
  }
  if (!threw) {
    failures.push(`${label}: expected throw, but call returned normally`);
    return;
  }
  if (typeof actualMessage !== 'string' || !actualMessage.includes(expectedFragment)) {
    failures.push(
      `${label}: expected message to include ${JSON.stringify(expectedFragment)}, got ${JSON.stringify(actualMessage)}`,
    );
  }
};

const expectPasses = (label, fn) => {
  try {
    fn();
  } catch (err) {
    failures.push(`${label}: expected no throw, got ${JSON.stringify(err && err.message)}`);
  }
};

expectThrows(
  'assertBacktestHealthShape rejects null',
  () => assertBacktestHealthShape(null),
  'expected a plain object',
);
expectThrows(
  'assertBacktestHealthShape rejects empty data_sources map',
  () => assertBacktestHealthShape({ status: 'healthy', data_sources: {} }),
  'must declare at least one source',
);
expectThrows(
  'assertBacktestHealthShape rejects when no source is connected',
  () => assertBacktestHealthShape({
    status: 'healthy',
    data_sources: { fixture: { status: 'degraded' } },
  }),
  "status === 'connected'",
);

expectThrows(
  'assertProviderRuntimeShape rejects success === false',
  () => assertProviderRuntimeShape({
    success: false,
    providers: { fixture: { circuit_breakers: {} } },
  }),
  'success === false as a runtime failure',
);
expectThrows(
  'assertProviderRuntimeShape rejects empty providers map',
  () => assertProviderRuntimeShape({ success: true, providers: {} }),
  'must declare at least one provider',
);
expectThrows(
  'assertProviderRuntimeShape rejects provider missing circuit_breakers',
  () => assertProviderRuntimeShape({ success: true, providers: { fixture: {} } }),
  'circuit_breakers',
);

expectThrows(
  'assertIndustryHeatmapShape rejects empty industries array',
  () => assertIndustryHeatmapShape({ industries: [] }),
  'expected at least 1 entry',
);
expectThrows(
  'assertIndustryHeatmapShape rejects industry missing name',
  () => assertIndustryHeatmapShape({ industries: [{ name: '' }] }),
  'expected a non-empty string',
);

expectThrows(
  'assertIndustryStocksShape rejects empty array',
  () => assertIndustryStocksShape([]),
  'expected at least 1 entry',
);
expectThrows(
  'assertIndustryStocksShape rejects when no row reaches scoreStage full',
  () => assertIndustryStocksShape([{ symbol: '688981', scoreStage: 'partial' }]),
  "scoreStage === 'full'",
);

expectThrows(
  'assertIndustryStocksStatusShape rejects status !== ready',
  () => assertIndustryStocksStatusShape({ status: 'pending' }),
  "must be 'ready'",
);

expectPasses('valid fixtures pass every contract', () => {
  assertBacktestHealthShape({
    status: 'healthy',
    data_sources: {
      fixture: { status: 'connected', installed: true },
    },
  });
  assertProviderRuntimeShape({
    success: true,
    providers: {
      fixture: {
        circuit_breakers: {
          fixture_quotes: { state: 'closed' },
        },
      },
    },
  });
  assertIndustryHeatmapShape({
    industries: [{ name: '半导体', value: 2.4 }],
  });
  assertIndustryStocksShape([{ symbol: '688981', scoreStage: 'full' }]);
  assertIndustryStocksStatusShape({ status: 'ready' });
});

if (failures.length > 0) {
  console.error(`fixture contract smoke: ${failures.length} failure(s)`);
  for (const failure of failures) {
    console.error(`  - ${failure}`);
  }
  process.exit(1);
}

console.log('fixture contract smoke: all checks passed');
