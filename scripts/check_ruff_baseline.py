#!/usr/bin/env python3
"""Fail the build when new Ruff findings appear beyond the committed baseline.

This is the baseline-locked lint gate (mirrors the super-pricing-system pattern).
It does NOT require zero findings — it only fails when the count grows. Pair
with intentional clean-up commits that lower ``scripts/ruff_baseline_count.txt``.

Re-baseline workflow (when you intentionally fix findings):

    python scripts/check_ruff_baseline.py --write-baseline
    git add scripts/ruff_baseline_count.txt
    git commit -m "chore(lint): tighten ruff baseline to <N>"

Local pre-commit usage (same checks CI runs):

    python scripts/check_ruff_baseline.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "scripts" / "ruff_baseline_count.txt"
DEFAULT_TARGETS: tuple[str, ...] = ("src", "backend", "scripts", "tests")


def _run_ruff_json(targets: tuple[str, ...]) -> list[dict[str, Any]]:
    """Run ruff in JSON mode and return the findings list."""
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--output-format",
        "json",
        *targets,
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    # ruff exits 0 when clean, 1 when findings exist. Anything else is real failure.
    if result.returncode not in {0, 1}:
        sys.stderr.write(result.stderr or result.stdout)
        raise SystemExit(
            f"ruff exited with unexpected status {result.returncode}. "
            "Make sure ruff is installed (pip install -r requirements-dev.txt)."
        )
    if not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        sys.stderr.write(result.stdout)
        raise SystemExit(f"Unable to parse ruff JSON output: {exc}") from exc
    if not isinstance(payload, list):  # pragma: no cover - defensive
        raise SystemExit("Unexpected ruff JSON output shape (expected list)")
    return payload


def _read_baseline() -> int:
    if not BASELINE_PATH.exists():
        raise SystemExit(
            f"Missing {BASELINE_PATH.relative_to(PROJECT_ROOT)}. "
            "Run `python scripts/check_ruff_baseline.py --write-baseline` first."
        )
    text = BASELINE_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(
            f"{BASELINE_PATH.relative_to(PROJECT_ROOT)} is empty. Expected a single integer."
        )
    try:
        return int(text)
    except ValueError as exc:
        raise SystemExit(
            f"{BASELINE_PATH.relative_to(PROJECT_ROOT)} must contain a single integer; "
            f"got {text!r}"
        ) from exc


def _write_baseline(count: int) -> None:
    BASELINE_PATH.write_text(f"{count}\n", encoding="utf-8")


def _summarise_by_rule(findings: list[dict[str, Any]], limit: int = 10) -> str:
    counter: Counter[str] = Counter(str(f.get("code", "?")) for f in findings)
    lines = []
    for rule, count in counter.most_common(limit):
        lines.append(f"    {count:>5}  {rule}")
    omitted_rules = len(counter) - min(len(counter), limit)
    if omitted_rules:
        omitted_count = sum(counter.values()) - sum(
            count for _, count in counter.most_common(limit)
        )
        lines.append(f"    ... {omitted_count} more across {omitted_rules} other rules")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=(
            "Overwrite scripts/ruff_baseline_count.txt with the current finding count. "
            "Use after you intentionally fix findings to lock in the new floor."
        ),
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=list(DEFAULT_TARGETS),
        help="Paths passed to ruff. Defaults to: src backend scripts tests",
    )
    args = parser.parse_args()

    targets = tuple(args.targets)
    findings = _run_ruff_json(targets)
    current = len(findings)

    if args.write_baseline:
        _write_baseline(current)
        print(
            f"Wrote {BASELINE_PATH.relative_to(PROJECT_ROOT)} with {current} findings."
        )
        return 0

    baseline = _read_baseline()
    new_count = max(current - baseline, 0)
    resolved_count = max(baseline - current, 0)

    if current > baseline:
        print("Ruff baseline gate FAILED: new findings detected.")
        print(
            f"  current={current} baseline={baseline} "
            f"resolved={resolved_count} new={new_count}"
        )
        print("Top rule codes in current run:")
        print(_summarise_by_rule(findings))
        print(
            "\nFix the new findings, or — if intentional — run "
            "`python scripts/check_ruff_baseline.py --write-baseline` to tighten the floor."
        )
        return 1

    print(
        "Ruff baseline gate passed: "
        f"current={current} baseline={baseline} "
        f"resolved={resolved_count} new={new_count}"
    )
    if current < baseline:
        print(
            "Heads up: current count is below baseline. Consider re-baselining via "
            "`python scripts/check_ruff_baseline.py --write-baseline` to lock the win in."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
