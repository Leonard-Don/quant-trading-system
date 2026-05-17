"""Output-path safety tests for scripts/recommend_strategy.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import recommend_strategy as cli


def _assert_cli_rejects(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(argv)

    assert exc_info.value.code == 2
    return capsys.readouterr().err


def test_output_json_cannot_overwrite_input_price_csv(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    price_csv = tmp_path / "prices.csv"

    stderr = _assert_cli_rejects(
        [
            "--price-csv",
            str(price_csv),
            "--output-json",
            str(price_csv),
            "--quiet",
        ],
        capsys,
    )

    assert "must not overwrite --price-csv" in stderr


def test_output_json_cannot_target_project_data_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    price_csv = tmp_path / "prices.csv"
    output_json = cli.PROJECT_ROOT / "data" / "etf_backtest" / "blocked.json"

    stderr = _assert_cli_rejects(
        [
            "--price-csv",
            str(price_csv),
            "--output-json",
            str(output_json),
            "--quiet",
        ],
        capsys,
    )

    assert "must not write into a data directory" in stderr


def test_output_md_cannot_target_source_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    price_csv = tmp_path / "prices.csv"
    output_md = cli.PROJECT_ROOT / "src" / "strategy" / "blocked.md"

    stderr = _assert_cli_rejects(
        [
            "--price-csv",
            str(price_csv),
            "--output-md",
            str(output_md),
            "--quiet",
        ],
        capsys,
    )

    assert "must not target protected project path" in stderr


def test_output_md_cannot_overwrite_project_metadata_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    price_csv = tmp_path / "prices.csv"
    output_md = cli.PROJECT_ROOT / "README.md"

    stderr = _assert_cli_rejects(
        [
            "--price-csv",
            str(price_csv),
            "--output-md",
            str(output_md),
            "--quiet",
        ],
        capsys,
    )

    assert "must not overwrite protected project file" in stderr
