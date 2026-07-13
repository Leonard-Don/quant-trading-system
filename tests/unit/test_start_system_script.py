import os
import shlex
import shutil
import stat
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = PROJECT_ROOT / "scripts" / "start_system.sh"


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


def _read_argv_calls(path: Path) -> list[list[str]]:
    return [shlex.split(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _prepare_runnable_project(tmp_path: Path) -> tuple[Path, Path]:
    project, script = _copy_start_script(tmp_path)
    (project / "frontend" / "node_modules").mkdir(parents=True)
    (project / "requirements.txt").write_text("", encoding="utf-8")
    return project, script


def _foreground_env(tmp_path: Path, python_bin: Path, calls: Path) -> dict[str, str]:
    fake_bin = tmp_path / "controlled path"
    for command in ("node", "npm", "sleep"):
        _make_executable(fake_bin / command)

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


def test_daemon_passes_explicit_python_to_existing_tmux_server(tmp_path: Path) -> None:
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
        ["bash", str(script), "--daemon"],
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
