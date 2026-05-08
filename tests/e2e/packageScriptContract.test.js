// Fast package-script guard for the low-cost fixture-contract smoke lane.
//
// The E2E package.json is the discoverability surface for local and CI smoke
// checks. If verify:fixture-contract drifts out of verify:all, the standalone
// contract guard can silently stop running before the slower Playwright lanes.
const { readFileSync } = require('fs');
const { join } = require('path');

const packageJson = JSON.parse(readFileSync(join(__dirname, 'package.json'), 'utf8'));
const scripts = packageJson.scripts || {};
const failures = [];

const expectScript = (name, expected) => {
  if (scripts[name] !== expected) {
    failures.push(`${name}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(scripts[name])}`);
  }
};

expectScript('verify:fixture-contract', 'node fixtureContract.test.js');
expectScript('verify:package-contract', 'node packageScriptContract.test.js');

const verifyAll = scripts['verify:all'];
if (typeof verifyAll !== 'string') {
  failures.push('verify:all must be a string script');
} else {
  const steps = verifyAll.split('&&').map((step) => step.trim());
  const expectedPrefix = ['npm run verify:package-contract', 'npm run verify:fixture-contract'];
  expectedPrefix.forEach((expectedStep, index) => {
    if (steps[index] !== expectedStep) {
      failures.push(`verify:all step ${index + 1}: expected ${JSON.stringify(expectedStep)}, got ${JSON.stringify(steps[index])}`);
    }
  });
  for (const required of ['npm run verify:backtest', 'npm run verify:industry', 'npm run verify:new']) {
    if (!steps.includes(required)) {
      failures.push(`verify:all must still include ${required}`);
    }
  }
}

if (failures.length > 0) {
  console.error(`package script contract: ${failures.length} failure(s)`);
  for (const failure of failures) {
    console.error(`  - ${failure}`);
  }
  process.exit(1);
}

console.log('package script contract: all checks passed');
