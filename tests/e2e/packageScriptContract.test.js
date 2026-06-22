// Fast package-script guard for the low-cost fixture-contract smoke lane.
//
// The E2E package.json is the discoverability surface for local and CI smoke
// checks. If verify:fixture-contract drifts out of verify:all, the standalone
// contract guard can silently stop running before the slower Playwright lanes.
// The same drift can hide on the CI side: if .github/workflows/ci.yml stops
// invoking `npm run verify:all`, the package script contract still passes
// locally while CI silently skips every fixture-contract smoke lane.
const { readFileSync } = require('fs');
const { join } = require('path');

const packageJson = JSON.parse(readFileSync(join(__dirname, 'package.json'), 'utf8'));
const ciWorkflow = readFileSync(join(__dirname, '..', '..', '.github', 'workflows', 'ci.yml'), 'utf8');
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
  for (const required of [
    'npm run verify:backtest',
    'npm run verify:industry',
    'npm run verify:realtime',
    'npm run verify:new',
  ]) {
    if (!steps.includes(required)) {
      failures.push(`verify:all must still include ${required}`);
    }
  }
  // Catch newly added verify:* lanes that forget to wire into verify:all.
  for (const lane of Object.keys(scripts)) {
    if (!lane.startsWith('verify:') || lane === 'verify:all') continue;
    const required = `npm run ${lane}`;
    if (!steps.includes(required)) {
      failures.push(`verify:all must include ${required} (every verify:* lane in package.json must run from verify:all)`);
    }
  }
}

const ciSteps = ciWorkflow.split(/\n\s{6}- name: /).slice(1).map((step) => `- name: ${step}`);
const runsResearchE2EFromPackage = ciSteps.some((step) => (
  /^- name:\s*Run research E2E suite/m.test(step)
  && /working-directory:\s*tests\/e2e/.test(step)
  && /run:\s*npm run verify:all/.test(step)
));
if (!runsResearchE2EFromPackage) {
  failures.push('CI workflow Run research E2E suite step must run npm run verify:all from tests/e2e');
}

if (failures.length > 0) {
  console.error(`package script contract: ${failures.length} failure(s)`);
  for (const failure of failures) {
    console.error(`  - ${failure}`);
  }
  process.exit(1);
}

console.log('package script contract: all checks passed');
