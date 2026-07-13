import contextlib
import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = PROJECT_ROOT / "scripts" / "start_system.sh"
WORKER_SCRIPT = PROJECT_ROOT / "scripts" / "start_celery_worker.sh"


def _make_executable(path: Path) -> None:
    _write_executable(path, "#!/usr/bin/env bash\nexit 0\n")


def _write_executable(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _copy_start_script(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project with spaces"
    script = project / "scripts" / "start_system.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(START_SCRIPT, script)
    return project, script


def _copy_worker_script(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project with spaces"
    script = project / "scripts" / "start_celery_worker.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(WORKER_SCRIPT, script)
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


def _make_argv_recorder(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env bash
printf '%q ' "$@" >> "${PYTHON_CALLS:?}"
printf '\\n' >> "${PYTHON_CALLS:?}"
exit 0
""",
    )


def _make_worker_python(path: Path) -> None:
    _write_executable(
        path,
        """#!/usr/bin/env bash
printf '%q ' "$@" >> "${PYTHON_CALLS:?}"
printf '\\n' >> "${PYTHON_CALLS:?}"
if [[ "${1:-}" == "-" ]]; then
    cat >/dev/null
    exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "celery" ]]; then
    /bin/sleep 30
    exit 0
fi
exit 97
""",
    )


def _read_argv_calls(path: Path) -> list[list[str]]:
    return [shlex.split(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _worker_env(tmp_path: Path, calls: Path) -> dict[str, str]:
    fake_bin = tmp_path / "controlled path"
    _make_executable(fake_bin / "sleep")
    _write_executable(fake_bin / "python3", "#!/usr/bin/env bash\nexit 96\n")

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["PYTHON_CALLS"] = str(calls)
    env["CELERY_BROKER_URL"] = "redis://example.invalid:6379/0"
    return env


def _run_worker(
    project: Path,
    script: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "bash",
            str(script),
            "--loglevel",
            "debug",
            "--concurrency",
            "2",
            "--pool",
            "solo",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    pid_file = project / "logs" / "celery-worker.pid"
    if pid_file.exists():
        with contextlib.suppress(ProcessLookupError, ValueError):
            os.kill(int(pid_file.read_text(encoding="utf-8").strip()), 15)
    return result


def _expected_worker_calls() -> list[list[str]]:
    return [
        ["-"],
        [
            "-m",
            "celery",
            "-A",
            "backend.app.core.task_queue:celery_app",
            "worker",
            "--loglevel=debug",
            "--concurrency=2",
            "--pool=solo",
        ],
    ]


def _prepare_runnable_project(tmp_path: Path) -> tuple[Path, Path]:
    project, script = _copy_start_script(tmp_path)
    (project / "frontend" / "node_modules").mkdir(parents=True)
    (project / "requirements.txt").write_text("", encoding="utf-8")
    return project, script


def _foreground_env(tmp_path: Path, python_bin: Path, calls: Path) -> dict[str, str]:
    fake_bin = tmp_path / "controlled path"
    for command in ("node", "npm"):
        _make_executable(fake_bin / command)
    _write_executable(fake_bin / "sleep", "#!/usr/bin/env bash\n/bin/sleep 0.02\n")

    curl_count = tmp_path / "curl-count"
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
count=0
if [[ -f "${CURL_COUNT_FILE:?}" ]]; then
    count="$(<"$CURL_COUNT_FILE")"
fi
count=$((count + 1))
printf '%s\\n' "$count" > "$CURL_COUNT_FILE"
if [[ "$count" -le 2 ]]; then
    exit 0
fi
exit 1
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["PYTHON_BIN"] = str(python_bin)
    env["PYTHON_CALLS"] = str(calls)
    env["CURL_COUNT_FILE"] = str(curl_count)
    return env


def _run_controlled_foreground(
    tmp_path: Path, *args: str
) -> tuple[Path, list[list[str]], subprocess.CompletedProcess[str]]:
    project, script = _prepare_runnable_project(tmp_path)
    python_bin = tmp_path / "custom python" / "bin" / "python3"
    calls = tmp_path / "python-calls"
    _make_argv_recorder(python_bin)

    result = subprocess.run(
        ["bash", str(script), *args],
        check=False,
        capture_output=True,
        text=True,
        env=_foreground_env(tmp_path, python_bin, calls),
        timeout=10,
    )

    assert result.returncode == 1
    assert "前端服务意外停止" in result.stderr
    return project, _read_argv_calls(calls), result


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


def test_start_script_falls_back_to_python3_when_virtualenv_is_not_executable(
    tmp_path: Path,
) -> None:
    project, script = _copy_start_script(tmp_path)
    venv_python = project / ".venv" / "bin" / "python3"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("not executable\n", encoding="utf-8")
    fake_bin = tmp_path / "controlled path"
    _make_executable(fake_bin / "python3")
    env = os.environ.copy()
    env.pop("PYTHON_BIN", None)
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"

    result = _trace_help(script, env)

    assert result.returncode == 0
    assert _last_trace_assignment(result.stderr, "PYTHON_BIN") == "python3"


def test_start_script_rejects_invalid_explicit_python_override(tmp_path: Path) -> None:
    _, script = _copy_start_script(tmp_path)
    invalid_python = tmp_path / "missing python" / "bin" / "python3"
    env = os.environ.copy()
    env["PYTHON_BIN"] = str(invalid_python)

    result = subprocess.run(
        ["bash", str(script)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert (
        f"❌ 未找到命令: {invalid_python}。请先安装 Python3 或创建项目 .venv"
        in result.stderr
    )


def test_selected_python_checks_runtime_dependencies(tmp_path: Path) -> None:
    _, calls, _ = _run_controlled_foreground(tmp_path)

    assert ["-"] in calls


def test_selected_python_installs_dependencies(tmp_path: Path) -> None:
    project, calls, _ = _run_controlled_foreground(tmp_path, "--install")

    assert ["-m", "pip", "install", "-r", str(project / "requirements.txt")] in calls


def test_selected_python_launches_backend(tmp_path: Path) -> None:
    project, calls, _ = _run_controlled_foreground(tmp_path)

    assert [str(project / "scripts" / "start_backend.py")] in calls


def test_worker_prefers_explicit_python_with_spaces_and_preserves_argv(tmp_path: Path) -> None:
    project, script = _copy_worker_script(tmp_path)
    calls = tmp_path / "python-calls"
    explicit_python = tmp_path / "explicit python with spaces" / "bin" / "python3"
    _make_worker_python(explicit_python)
    _write_executable(project / ".venv" / "bin" / "python3", "#!/usr/bin/env bash\nexit 95\n")
    env = _worker_env(tmp_path, calls)
    env["PYTHON_BIN"] = str(explicit_python)

    result = _run_worker(project, script, env)

    assert result.returncode == 0, result.stderr
    assert _read_argv_calls(calls) == _expected_worker_calls()


def test_worker_prefers_project_virtualenv_when_system_python_is_unusable(
    tmp_path: Path,
) -> None:
    project, script = _copy_worker_script(tmp_path)
    calls = tmp_path / "python-calls"
    _make_worker_python(project / ".venv" / "bin" / "python3")
    env = _worker_env(tmp_path, calls)
    env.pop("PYTHON_BIN", None)

    result = _run_worker(project, script, env)

    assert result.returncode == 0, result.stderr
    assert _read_argv_calls(calls) == _expected_worker_calls()


def test_worker_falls_back_to_python3_when_project_virtualenv_is_not_executable(
    tmp_path: Path,
) -> None:
    project, script = _copy_worker_script(tmp_path)
    calls = tmp_path / "python-calls"
    venv_python = project / ".venv" / "bin" / "python3"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("not executable\n", encoding="utf-8")
    env = _worker_env(tmp_path, calls)
    _make_worker_python(tmp_path / "controlled path" / "python3")
    env.pop("PYTHON_BIN", None)

    result = _run_worker(project, script, env)

    assert result.returncode == 0, result.stderr
    assert _read_argv_calls(calls) == _expected_worker_calls()


def test_start_system_passes_selected_python_to_worker(tmp_path: Path) -> None:
    project, script = _prepare_runnable_project(tmp_path)
    selected_python = project / ".venv" / "bin" / "python3"
    calls = tmp_path / "python-calls"
    _make_argv_recorder(selected_python)
    worker_python = tmp_path / "worker-python-bin"
    _write_executable(
        project / "scripts" / "start_celery_worker.sh",
        """#!/usr/bin/env bash
printf '%s\\n' "${PYTHON_BIN-}" > "${WORKER_PYTHON_BIN:?}"
mkdir -p "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/logs"
printf '%s\\n' "$$" > "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/logs/celery-worker.pid"
""",
    )
    env = _foreground_env(tmp_path, selected_python, calls)
    env.pop("PYTHON_BIN", None)
    env["WORKER_PYTHON_BIN"] = str(worker_python)

    result = subprocess.run(
        ["bash", str(script), "--with-worker"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 1
    assert "前端服务意外停止" in result.stderr
    assert worker_python.read_text(encoding="utf-8").strip() == str(selected_python)


def test_daemon_with_worker_preserves_explicit_python_and_arguments(tmp_path: Path) -> None:
    _, script = _copy_start_script(tmp_path)
    explicit_python = tmp_path / "custom python" / "bin" / "python3"
    _make_executable(explicit_python)
    fake_bin = tmp_path / "controlled path"
    tmux_args = tmp_path / "tmux-new-session-args"
    _write_executable(
        fake_bin / "tmux",
        """#!/usr/bin/env bash
unset PYTHON_BIN
if [[ "${1:-}" == "has-session" ]]; then
    exit 1
fi
if [[ "${1:-}" == "new-session" ]]; then
    shift
    printf '%q ' "$@" > "${TMUX_NEW_SESSION_ARGS:?}"
    printf '\\n' >> "${TMUX_NEW_SESSION_ARGS:?}"
    exit 0
fi
exit 1
""",
    )
    _make_executable(fake_bin / "curl")
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["PYTHON_BIN"] = str(explicit_python)
    env["TMUX_NEW_SESSION_ARGS"] = str(tmux_args)

    result = subprocess.run(
        ["bash", str(script), "--daemon", "--with-worker"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    new_session_args = shlex.split(tmux_args.read_text(encoding="utf-8"))
    environment_index = new_session_args.index("-e")
    assert new_session_args[environment_index : environment_index + 2] == [
        "-e",
        f"PYTHON_BIN={explicit_python}",
    ]
    assert shlex.split(new_session_args[-1]) == [str(script), "--with-worker"]
