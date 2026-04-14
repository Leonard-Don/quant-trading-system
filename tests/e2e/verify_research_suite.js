const { spawn } = require('child_process');
const path = require('path');

const E2E_DIR = __dirname;
const PROJECT_ROOT = path.resolve(E2E_DIR, '..', '..');
const FRONTEND_DIR = path.join(PROJECT_ROOT, 'frontend');
const FRONTEND_BASE_URL = process.env.E2E_FRONTEND_URL || 'http://127.0.0.1:3000';
const API_BASE_URL = process.env.E2E_API_URL || 'http://127.0.0.1:8000';
const STEPS = [
  { label: 'pricing-research', script: 'verify_pricing_research.js' },
  { label: 'continuous-review', script: 'verify_continuous_review_flow.js' },
];
const startedProcesses = [];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const canReach = async (url) => {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    const response = await fetch(url, {
      method: 'GET',
      signal: controller.signal,
    });
    clearTimeout(timer);
    return response.ok;
  } catch (error) {
    return false;
  }
};

const waitForService = async (url, name, timeout = 180000) => {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeout) {
    if (await canReach(url)) {
      return;
    }
    await sleep(1000);
  }
  throw new Error(`${name} 在 ${timeout}ms 内未就绪: ${url}`);
};

const startManagedProcess = (label, command, args, options = {}) => {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: {
      ...process.env,
      ...(options.env || {}),
    },
    stdio: 'ignore',
  });
  startedProcesses.push({ label, child });
  return child;
};

const ensureResearchServices = async () => {
  const frontendReady = await canReach(`${FRONTEND_BASE_URL}/?view=pricing`);
  const backendReady = await canReach(`${API_BASE_URL}/health`);

  if (!backendReady) {
    console.log('后端未运行，正在自动启动...');
    startManagedProcess(
      'backend',
      'python3',
      [path.join(PROJECT_ROOT, 'scripts/start_backend.py')],
      { cwd: PROJECT_ROOT, env: { API_RELOAD: 'false' } },
    );
  }

  if (!frontendReady) {
    console.log('前端未运行，正在自动启动...');
    startManagedProcess(
      'frontend',
      'npm',
      ['start'],
      { cwd: FRONTEND_DIR, env: { BROWSER: 'none' } },
    );
  }

  if (!backendReady) {
    await waitForService(`${API_BASE_URL}/health`, '后端');
  }
  if (!frontendReady) {
    await waitForService(`${FRONTEND_BASE_URL}/?view=pricing`, '前端');
  }
};

const stopManagedProcesses = () => {
  for (const { child } of startedProcesses.reverse()) {
    if (!child.killed) {
      child.kill('SIGTERM');
    }
  }
};

const runStep = (step) => new Promise((resolve, reject) => {
  const child = spawn(process.execPath, [path.join(E2E_DIR, step.script)], {
    cwd: E2E_DIR,
    env: process.env,
    stdio: 'inherit',
  });

  child.on('exit', (code) => {
    if (code === 0) {
      resolve();
      return;
    }
    reject(new Error(`${step.label} 回归失败，退出码 ${code}`));
  });
  child.on('error', reject);
});

(async () => {
  try {
    await ensureResearchServices();
    for (const step of STEPS) {
      console.log(`\n=== 开始执行 ${step.label} ===`);
      await runStep(step);
      console.log(`=== ${step.label} 已通过 ===`);
    }
    console.log('\n研究工作流 E2E 回归全部通过。');
  } catch (error) {
    console.error(`\n研究工作流 E2E 回归失败: ${error.message}`);
    process.exitCode = 1;
  } finally {
    stopManagedProcesses();
  }
})();
