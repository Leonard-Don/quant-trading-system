# Quant Trading Local Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve and test the useful project-virtualenv startup behavior, discard obsolete local WIP, publish the resulting clean `main` to GitHub, and then remove the local checkout and its data.

**Architecture:** Rebase the already-approved documentation commits onto current `origin/main`, align the Python 3.11 contract, and implement system/worker interpreter behavior test-first as focused startup-script changes. Treat all older stash, branch, and conflicting-tag history as disposable only after a verified Git bundle exists; delete the checkout only after `origin/main` contains every retained commit and all prescribed tests pass.

**Tech Stack:** Bash 3.2-compatible shell, Python 3.11+, pytest, Ruff baseline tooling, Vitest/Vite, Git/GitHub.

## Global Constraints

- Keep only code that is still valuable on current `origin/main` and passes its relevant tests.
- Do not upload or retain `.env`, `data/`, caches, models, logs, build products, or run history.
- Use Chinese commit messages for retained changes.
- Align the declared, documented, lint, type-check, and pinned-development-dependency Python floor at 3.11; the locked SciPy 1.16.0 already requires 3.11, and Sphinx must remain installable on 3.11.
- The two old stashes are discarded: the import-sort stash is broken and 610 commits behind; the Policy Radar key fix is already superseded by `buildRecordKey()` on `origin/main`.
- The local `fix/audit-docs-quick-wins` branch is discarded because `git cherry origin/main fix/audit-docs-quick-wins` marks its only commit patch-equivalent with `-`.
- The ten conflicting local release tags are discarded and replaced locally by the GitHub versions before final verification.
- Do not delete the checkout until all retained commits are present on `origin/main` and the safety bundle has been verified.
- The Task 1 safety bundle is intentionally a pre-integration snapshot; it is not evidence of the later current `HEAD`. Resolve `HEAD` live during final verification and carry its expected SHA across deletion in a repository-external marker.

## File Map

- Modify: `scripts/start_system.sh` — select the project virtualenv interpreter and use that same interpreter for dependency checks, installation, backend launch, and explicit worker handoff.
- Modify: `scripts/start_celery_worker.sh` — apply the same explicit override, executable project virtualenv, and `python3` fallback precedence to the worker probe and launch.
- Create: `tests/unit/test_start_system_script.py` — behavior tests for virtualenv selection, explicit override, interpreter-consistent pip/backend/worker invocation, argv boundaries, and daemon worker handoff.
- Modify: `pyproject.toml` — state the real Python 3.11 floor consistently for packaging, Ruff, and mypy.
- Modify: `requirements-dev.txt` — pin the newest Sphinx 9.0 release compatible with Python 3.11.
- Modify: `README.md` — publish the truthful Python 3.11+ requirement.
- Preserve: `docs/superpowers/specs/2026-07-13-local-retirement-design.md` — approved retirement design.
- Preserve: `docs/superpowers/plans/2026-07-13-local-retirement.md` — this execution plan.

---

### Task 1: Create a recoverable snapshot and rebase retained documentation

**Files:**
- Create temporarily: `/Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-before-cleanup.bundle`
- Preserve: `docs/superpowers/specs/2026-07-13-local-retirement-design.md`
- Preserve: `docs/superpowers/plans/2026-07-13-local-retirement.md`

**Interfaces:**
- Consumes: current `main`, `origin/main`, the dirty `scripts/start_system.sh`, all stash refs, local branches, and local tags.
- Produces: a verified Git bundle containing every Git ref and a clean `main` rebased onto current `origin/main`; the dirty startup patch remains reachable only in stash/bundle for reference.

- [ ] **Step 1: Store the dirty startup script in a named safety stash**

```bash
git stash push -m retirement-start-system -- scripts/start_system.sh
git status --short --branch
```

Expected: the script disappears from the status output; `main` remains ahead by the documentation commits and behind only if `origin/main` advanced.

- [ ] **Step 2: Create and verify a bundle containing all refs and stashes**

```bash
mkdir -p /Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety
git bundle create /Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-before-cleanup.bundle --all
git bundle verify /Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-before-cleanup.bundle
```

Expected: `git bundle verify` reports that the bundle is okay and lists `refs/stash`, `refs/heads/main`, and the local audit branch.

- [ ] **Step 3: Fetch branches without forcing the conflicting tags**

```bash
git fetch --prune origin
git rev-list --left-right --count HEAD...origin/main
```

Expected: the command succeeds; the left count reflects only retained local documentation commits.

- [ ] **Step 4: Rebase the retained documentation onto current GitHub main**

```bash
git rebase origin/main
git status --short --branch
```

Expected: rebase succeeds and the worktree is clean; `main` is ahead only by the design and plan commits.

### Task 2: Repair the Python development-environment contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements-dev.txt`
- Modify: `README.md`

**Interfaces:**
- Consumes: the public Python-version claim, packaging metadata, Ruff/mypy targets, and locked development requirements.
- Produces: one consistent Python 3.11+ contract and a development dependency set resolvable on Python 3.11.

- [ ] **Step 1: Reproduce the incompatible Sphinx pin on Python 3.11**

```bash
.venv/bin/python3 -m pip install --dry-run --ignore-installed \
  --python-version 3.11 --only-binary=:all: --no-deps 'sphinx==9.1.0'
```

Expected: FAIL with `9.1.0 Requires-Python >=3.12`.

- [ ] **Step 2: Record the currently contradictory Python floors**

```bash
.venv/bin/python3 - <<'PY'
import tomllib
from pathlib import Path

config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(config["project"]["requires-python"])
print(config["tool"]["ruff"]["target-version"])
print(config["tool"]["mypy"]["python_version"])
PY
rg -n 'Python-3\.9|`3\.9\+`' README.md
```

Expected: output shows `>=3.9`, `py39`, `3.10`, and two README Python 3.9+ claims even though locked SciPy requires Python 3.11.

- [ ] **Step 3: Apply the minimal consistent contract**

In `pyproject.toml`, use these exact values:

```toml
requires-python = ">=3.11"
```

```toml
[tool.ruff]
target-version = "py311"
```

```toml
[tool.mypy]
python_version = "3.11"
```

Update the adjacent mypy comment to describe the Python 3.11 project floor without claiming a 3.9 target. In `requirements-dev.txt`, replace:

```text
sphinx==9.1.0
```

with:

```text
sphinx==9.0.4
```

In `README.md`, change the Python badge and environment table requirement from `3.9+` to `3.11+`; retain the recommended version `3.13`.

- [ ] **Step 4: Verify the full direct requirement set resolves for Python 3.11**

```bash
.venv/bin/python3 -m pip install --dry-run --ignore-installed \
  --python-version 3.11 --only-binary=:all: --no-deps -r requirements-dev.txt
```

Expected: exit 0 and `Would install` includes `Sphinx-9.0.4`.

- [ ] **Step 5: Install the corrected development requirements in the project virtualenv**

```bash
.venv/bin/python3 -m pip install -r requirements-dev.txt
```

Expected: exit 0; `pytest-socket==0.8.0`, `ruff==0.15.10`, and `Sphinx==9.0.4` are installed.

- [ ] **Step 6: Verify metadata, tool targets, and documentation agree**

```bash
.venv/bin/python3 - <<'PY'
import tomllib
from pathlib import Path

config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
assert config["project"]["requires-python"] == ">=3.11"
assert config["tool"]["ruff"]["target-version"] == "py311"
assert config["tool"]["mypy"]["python_version"] == "3.11"
readme = Path("README.md").read_text(encoding="utf-8")
assert "Python-3.11+-blue" in readme
assert "`3.11+`" in readme
assert "3.9+" not in readme
PY
```

Expected: exit 0 with no assertion failures.

- [ ] **Step 7: Commit the compatibility fix**

```bash
git add pyproject.toml requirements-dev.txt README.md
git commit -m "fix: 对齐 Python 3.11 开发环境契约"
```

Expected: one focused commit containing only the three compatibility files.

### Task 3: Add virtualenv-aware startup behavior test-first

**Files:**
- Create: `tests/unit/test_start_system_script.py`
- Modify: `scripts/start_system.sh`

**Interfaces:**
- Consumes: optional `PYTHON_BIN` environment variable and `${PROJECT_ROOT}/.venv/bin/python3`.
- Produces: one `PYTHON_BIN` value with precedence `explicit environment override > executable project .venv python3 > python3`; dependency installation uses `PYTHON_BIN -m pip`.
- Final-review extension: the direct worker uses the same precedence for its Celery probe and launch, while `start_system.sh --with-worker` passes the selected value explicitly through foreground and daemon paths.

- [ ] **Step 1: Write failing tests for interpreter selection and consistent invocation**

Create `tests/unit/test_start_system_script.py` with:

```python
import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = PROJECT_ROOT / "scripts" / "start_system.sh"


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _copy_start_script(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project with spaces"
    script = project / "scripts" / "start_system.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(START_SCRIPT, script)
    return project, script


def _last_trace_assignment(stderr: str, name: str) -> str:
    prefix = f"+ {name}="
    assignments = [line[len(prefix):] for line in stderr.splitlines() if line.startswith(prefix)]
    assert assignments, f"missing {name} assignment in shell trace"
    return shlex.split(assignments[-1])[0]


def _trace_help(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-x", str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_start_script_prefers_project_virtualenv(tmp_path: Path) -> None:
    project, script = _copy_start_script(tmp_path)
    venv_python = project / ".venv" / "bin" / "python3"
    _make_executable(venv_python)
    env = os.environ.copy()
    env.pop("PYTHON_BIN", None)

    result = _trace_help(script, env)

    assert result.returncode == 0
    assert _last_trace_assignment(result.stderr, "PYTHON_BIN") == str(venv_python)


def test_start_script_honors_explicit_python_override(tmp_path: Path) -> None:
    project, script = _copy_start_script(tmp_path)
    _make_executable(project / ".venv" / "bin" / "python3")
    explicit_python = tmp_path / "custom python" / "bin" / "python3"
    _make_executable(explicit_python)
    env = os.environ.copy()
    env["PYTHON_BIN"] = str(explicit_python)

    result = _trace_help(script, env)

    assert result.returncode == 0
    assert _last_trace_assignment(result.stderr, "PYTHON_BIN") == str(explicit_python)


def test_selected_python_installs_dependencies_and_launches_backend() -> None:
    source = START_SCRIPT.read_text(encoding="utf-8")

    assert '"$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt"' in source
    assert 'API_RELOAD=false "$PYTHON_BIN" "$PROJECT_ROOT/scripts/start_backend.py"' in source
    assert "pip3 install -r" not in source
```

- [ ] **Step 2: Run the tests and verify the red state**

```bash
.venv/bin/python3 -m pytest tests/unit/test_start_system_script.py -q
```

Expected: FAIL because current `origin/main` does not assign `PYTHON_BIN` or use it for pip/backend launch.

- [ ] **Step 3: Implement the minimal interpreter selection**

In `scripts/start_system.sh`, add `VENV_DIR` beside the existing directory constants:

```bash
VENV_DIR="$PROJECT_ROOT/.venv"
```

After the port and worker constants, add:

```bash
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$VENV_DIR/bin/python3" ]]; then
        PYTHON_BIN="$VENV_DIR/bin/python3"
    else
        PYTHON_BIN="python3"
    fi
fi
```

Replace `check_python_runtime_deps()` with:

```bash
check_python_runtime_deps() {
    "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import fastapi  # noqa: F401
import uvicorn  # noqa: F401
import pydantic  # noqa: F401
PY
}
```

Replace `install_python_deps()` with:

```bash
install_python_deps() {
    local install_log="$LOG_DIR/install-python.log"
    log_info "📦 安装 Python 依赖..."
    if "$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt" >"$install_log" 2>&1; then
        log_info "✅ Python 依赖安装完成"
    else
        log_error "❌ Python 依赖安装失败，请检查日志: $install_log"
        exit 1
    fi
}
```

Replace the Python command checks with:

```bash
require_command "$PYTHON_BIN" "请先安装 Python3 或创建项目 .venv"
```

Delete the separate `require_command pip3` line, and launch the backend with:

```bash
API_RELOAD=false "$PYTHON_BIN" "$PROJECT_ROOT/scripts/start_backend.py" >"$LOG_DIR/backend.log" 2>&1 &
```

- [ ] **Step 4: Run the targeted tests and shell parser**

```bash
bash -n scripts/start_system.sh
.venv/bin/python3 -m pytest tests/unit/test_start_system_script.py -q
./scripts/start_system.sh --help >/dev/null
```

Expected: Bash parsing succeeds, all targeted startup tests pass, and the help command exits 0 without starting services.

- [ ] **Step 5: Confirm the retained diff excludes the old tmux and pip fallback WIP**

```bash
git diff --check
git diff -- scripts/start_system.sh tests/unit/test_start_system_script.py
```

Expected: the diff contains only reviewed startup behavior: virtualenv selection, interpreter-consistent pip/backend/worker use, Bash 3.2-safe tmux command construction and environment handoff, plus their behavior tests; it does not restore the discarded `PIP_BIN` fallback branches.

- [ ] **Step 6: Commit the tested startup change**

```bash
git add scripts/start_system.sh tests/unit/test_start_system_script.py
git commit -m "fix: 启动脚本优先使用项目虚拟环境"
```

Expected: one focused commit containing exactly the script and its tests.

### Task 4: Remove obsolete local Git state

**Files:**
- Delete from Git refs: all stashes, `fix/audit-docs-quick-wins`, and the ten conflicting local tags.
- Preserve temporarily: verified Git bundle from Task 1.

**Interfaces:**
- Consumes: completed retained commits and the verified safety bundle.
- Produces: no stashes, no local-only branches, GitHub versions of all tags, and no commits reachable only from local branches.

- [ ] **Step 1: Reconfirm the two old stashes are superseded or broken**

```bash
git stash list --format='%gd %ci %gs'
git log --oneline -- frontend/src/components/industry/PolicyRadarPanel.jsx | head
git show origin/main:frontend/src/components/industry/PolicyRadarPanel.jsx | rg 'buildRecordKey|tagIndex'
```

Expected: stash messages include `wip-import-sort-refactor-broken` and the old Policy Radar WIP; current main contains the later `buildRecordKey` implementation.

- [ ] **Step 2: Remove every stash now that the retained code is committed**

```bash
git stash clear
test -z "$(git stash list)"
```

Expected: no stash entries remain.

- [ ] **Step 3: Delete the patch-equivalent local audit branch**

```bash
git cherry origin/main fix/audit-docs-quick-wins
git branch -D fix/audit-docs-quick-wins
```

Expected: `git cherry` prints `- 8774dc2...`; branch deletion succeeds.

- [ ] **Step 4: Replace conflicting local tags with GitHub tags**

```bash
git tag -d v3.3.0 v3.4.0 v3.4.1 v3.5.0 v3.6.0 v3.7.0 v3.8.0 v3.9.0 v4.0.0 v5.0.0
git fetch --prune --tags origin
```

Expected: fetch succeeds without `would clobber existing tag` errors.

- [ ] **Step 5: Verify no branch-only commits remain**

```bash
git log --oneline --branches --not --remotes
git branch -vv
```

Expected: the only local-only commits are the retained commits on `main`; there are no other local branches.

### Task 5: Run the complete verification gates

**Files:**
- Verify: all retained source, tests, and documentation.

**Interfaces:**
- Consumes: final local `main` before push.
- Produces: fresh evidence that shell, backend, lint baseline, frontend tests, and frontend production build pass.

- [ ] **Step 1: Run shell and targeted startup verification**

```bash
bash -n scripts/start_system.sh scripts/start_celery_worker.sh
.venv/bin/python3 -m pytest tests/unit/test_start_system_script.py -q
./scripts/start_system.sh --help >/dev/null
./scripts/start_celery_worker.sh --help >/dev/null
```

Expected: both shell scripts parse, both help paths exit 0 without starting services, and all targeted startup tests pass.

- [ ] **Step 2: Run the repository Ruff baseline gate**

```bash
.venv/bin/python3 scripts/check_ruff_baseline.py
```

Expected: exit 0 with no Ruff baseline increase.

- [ ] **Step 3: Run the prescribed backend suite and coverage gate**

```bash
.venv/bin/python3 -m pytest tests/unit tests/integration -m "not perf" --cov=src --cov=backend --cov-fail-under=60 -q
```

Expected: all selected tests pass and total coverage is at least 60%.

- [ ] **Step 4: Run frontend lint, tests, and production build**

```bash
cd frontend
npm run lint
npm test
npm run build
```

Expected: ESLint exits 0, Vitest reports no failures, and Vite completes a production build.

- [ ] **Step 5: Verify repository cleanliness before publication**

```bash
git diff --check
git status --short --branch
```

Expected: no worktree changes; `main` is ahead of `origin/main` only by reviewed retained commits for documentation, the Python 3.11 contract/lint compatibility, and tested startup behavior.

### Task 6: Publish, verify GitHub, and delete the local checkout

**Files:**
- Delete after remote verification: `/Users/leonardodon/quant-trading-system`
- Delete after remote verification: `/Users/leonardodon/.config/superpowers/worktrees/quant-trading-system`
- Delete after remote verification: `/Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-before-cleanup.bundle`
- Create temporarily outside the repository, then delete after post-removal verification: `/Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-origin-main.expected`

**Interfaces:**
- Consumes: clean tested `main` and verified safety bundle.
- Produces: GitHub `origin/main` containing every retained commit and no remaining local Quant Trading checkout, data, cache, or temporary bundle.

- [ ] **Step 1: Push retained commits directly to GitHub main**

```bash
git push origin main
```

Expected: push succeeds. If branch protection rejects the push, stop before deletion and use the repository's required PR path.

- [ ] **Step 2: Fetch and prove exact local/remote agreement**

```bash
git fetch --prune --tags origin
git rev-list --left-right --count main...origin/main
EXPECTED_ORIGIN_MAIN_MARKER=/Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-origin-main.expected
EXPECTED_ORIGIN_MAIN="$(git rev-parse main)"
printf '%s\n' "$EXPECTED_ORIGIN_MAIN" > "$EXPECTED_ORIGIN_MAIN_MARKER"
REMOTE_ORIGIN_MAIN="$(git ls-remote origin refs/heads/main | awk 'NR == 1 {print $1}')"
test -n "$REMOTE_ORIGIN_MAIN"
test "$EXPECTED_ORIGIN_MAIN" = "$REMOTE_ORIGIN_MAIN"
git status --porcelain=v1
test -z "$(git stash list)"
```

Expected: divergence is `0 0`, local and live remote commit hashes match, the expected SHA is saved outside the repository, status is empty, and there are no stashes.

- [ ] **Step 3: Confirm no process or launch item references the checkout**

```bash
PROCESS_LIST=""
if ! PROCESS_LIST="$(ps axww -o command=)"; then
    echo "process scan failed" >&2
    exit 1
fi

PROCESS_MATCHES=""
if PROCESS_MATCHES="$(printf '%s\n' "$PROCESS_LIST" | rg '/Users/leonardodon/quant-trading-syste[m]')"; then
    printf 'checkout-referencing processes found:\n%s\n' "$PROCESS_MATCHES" >&2
    exit 1
else
    PROCESS_SCAN_STATUS=$?
    if [[ "$PROCESS_SCAN_STATUS" -ne 1 ]]; then
        echo "process match scan failed with status $PROCESS_SCAN_STATUS" >&2
        exit 1
    fi
fi

LAUNCH_AGENT_DIRS=()
for launch_agent_dir in /Users/leonardodon/Library/LaunchAgents /Library/LaunchAgents; do
    if [[ ! -e "$launch_agent_dir" ]]; then
        continue
    fi
    if [[ ! -d "$launch_agent_dir" || ! -r "$launch_agent_dir" ]]; then
        echo "LaunchAgent path is not a readable directory: $launch_agent_dir" >&2
        exit 1
    fi
    LAUNCH_AGENT_DIRS+=("$launch_agent_dir")
done
if [[ "${#LAUNCH_AGENT_DIRS[@]}" -eq 0 ]]; then
    echo "no readable LaunchAgent directories available for scanning" >&2
    exit 1
fi

LAUNCH_AGENT_MATCHES=""
if LAUNCH_AGENT_MATCHES="$(rg -l '/Users/leonardodon/quant-trading-syste[m]' "${LAUNCH_AGENT_DIRS[@]}" 2>&1)"; then
    printf 'checkout-referencing LaunchAgents found:\n%s\n' "$LAUNCH_AGENT_MATCHES" >&2
    exit 1
else
    LAUNCH_AGENT_SCAN_STATUS=$?
    if [[ "$LAUNCH_AGENT_SCAN_STATUS" -ne 1 ]]; then
        printf 'LaunchAgent scan failed with status %s:\n%s\n' \
            "$LAUNCH_AGENT_SCAN_STATUS" "$LAUNCH_AGENT_MATCHES" >&2
        exit 1
    fi
fi
```

Expected: both scans complete successfully with `rg` status 1 (no matches). Any real process or LaunchAgent match, any unreadable scan root, or any scan status greater than 1 prints diagnostics and exits 1 before deletion.

- [ ] **Step 4: Remove the temporary bundle and local directories**

```bash
rm -f /Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-before-cleanup.bundle
rm -rf /Users/leonardodon/quant-trading-system
rmdir /Users/leonardodon/.config/superpowers/worktrees/quant-trading-system 2>/dev/null || true
```

Expected: deletion succeeds only after Steps 1-3 pass.

- [ ] **Step 5: Verify local deletion and remote persistence from outside the checkout**

```bash
test ! -e /Users/leonardodon/quant-trading-system
test ! -e /Users/leonardodon/.config/superpowers/worktrees/quant-trading-system
test ! -e /Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-before-cleanup.bundle
EXPECTED_ORIGIN_MAIN_MARKER=/Users/leonardodon/Documents/Codex/2026-07-13/qu-a/work/retirement-safety/quant-trading-origin-main.expected
test -f "$EXPECTED_ORIGIN_MAIN_MARKER"
EXPECTED_ORIGIN_MAIN="$(cat "$EXPECTED_ORIGIN_MAIN_MARKER")"
REMOTE_ORIGIN_MAIN="$(git ls-remote https://github.com/Leonard-Don/quant-trading-system.git refs/heads/main | awk 'NR == 1 {print $1}')"
test -n "$REMOTE_ORIGIN_MAIN"
test "$EXPECTED_ORIGIN_MAIN" = "$REMOTE_ORIGIN_MAIN"
rm -f "$EXPECTED_ORIGIN_MAIN_MARKER"
test ! -e "$EXPECTED_ORIGIN_MAIN_MARKER"
```

Expected: all three retired local paths are absent, GitHub returns exactly the SHA saved before deletion, and the repository-external marker is removed only after that comparison succeeds.
