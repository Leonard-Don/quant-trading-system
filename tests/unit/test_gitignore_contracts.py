from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_outputs_directory_is_gitignored() -> None:
    """Runtime-generated outputs/ artifacts should not dirty local checkouts."""

    result = subprocess.run(
        ["git", "check-ignore", "outputs/smoke.json"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "outputs/smoke.json"
