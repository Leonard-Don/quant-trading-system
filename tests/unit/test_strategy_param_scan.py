"""Unit tests for the strategy parameter sweep script.

``strategy_param_scan`` is a one-off tuning harness: it builds a grid of
``StrategyConfig`` overrides, runs each through ``FullPipelineStrategy``,
and prints a tidy comparison table. The script has a hardcoded
``PRICES`` constant pointing at the 4-year backtest CSV, so we monkeypatch
that to a synthetic fixture written into ``tmp_path``.

Coverage targets:
* ``_override_config``: dotted-key routing into strategy vs. ensemble dicts.
* ``_run``: single-config execution returning the result schema, plus
  partial-failure handling (one config crashes → run returns None and the
  surrounding loop continues).
* ``main``: the full sweep (12 runs) executes cleanly and returns 0.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scripts import strategy_param_scan
from src.strategy.etf_rotation_config_loader import load_strategy_config

DEFAULT_CODES = ["159985", "512400", "510300", "518680", "513130"]


# ---------------------------------------------------------------------------
# Synthetic price fixture + PRICES patcher
# ---------------------------------------------------------------------------


def _write_prices(tmp_path: Path, *, periods: int = 240) -> Path:
    """Write a deterministic synthetic 5-ETF price CSV.

    240 bars is just enough to clear the 200-day MA warmup that
    ``FullPipelineStrategy`` enforces internally. We keep the fixture
    minimal so the ~12-cell sweep stays well under 5 seconds.
    """
    dates = pd.bdate_range("2023-01-02", periods=periods)
    rng = np.random.default_rng(11)
    data = {}
    for offset, code in enumerate(DEFAULT_CODES):
        drift = np.linspace(0.0, 0.25 - 0.04 * offset, len(dates))
        noise = np.cumsum(rng.normal(0.0, 0.003, len(dates)))
        data[code] = 5.0 * np.exp(drift + noise)
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame(data, index=dates).to_csv(csv_path)
    return csv_path


@pytest.fixture
def patched_prices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Redirect the script's hardcoded PRICES constant at the fixture CSV."""
    csv_path = _write_prices(tmp_path)
    monkeypatch.setattr(strategy_param_scan, "PRICES", str(csv_path))
    return csv_path


# ---------------------------------------------------------------------------
# _override_config — dotted-key routing
# ---------------------------------------------------------------------------


def test_override_config_routes_strategy_keys_into_strategy_dict() -> None:
    """Plain keys must be merged into the ``strategy`` dict."""
    base = load_strategy_config()
    out = strategy_param_scan._override_config(
        base, min_score_to_hold=42.0, min_score_full_hold=55.0,
    )
    assert out.strategy["min_score_to_hold"] == 42.0
    assert out.strategy["min_score_full_hold"] == 55.0
    # Untouched keys survive intact (deep-merge, not replace).
    assert out.strategy["gross_cap"] == base.strategy["gross_cap"]


def test_override_config_routes_ensemble_keys_via_dotted_prefix() -> None:
    """Keys prefixed with ``ensemble.`` must route into the ensemble dict."""
    base = load_strategy_config()
    out = strategy_param_scan._override_config(
        base, **{"ensemble.enabled": True, "ensemble.alpha_floor": 0.40}
    )
    assert out.ensemble["enabled"] is True
    assert out.ensemble["alpha_floor"] == 0.40
    # Strategy dict untouched.
    assert out.strategy == base.strategy


def test_override_config_returns_new_config_without_mutating_base() -> None:
    """Override must be immutable on the original config object.

    Why: ``_run`` calls ``_override_config`` per grid cell; if the base
    config were mutated, subsequent runs would inherit prior overrides
    and the scan would lie about its results.
    """
    base = load_strategy_config()
    original_to_hold = base.strategy["min_score_to_hold"]
    _ = strategy_param_scan._override_config(base, min_score_to_hold=999.0)
    assert base.strategy["min_score_to_hold"] == original_to_hold


# ---------------------------------------------------------------------------
# _run — single grid cell
# ---------------------------------------------------------------------------


def test_run_returns_expected_schema(patched_prices: Path) -> None:
    """A successful ``_run`` call must return the documented result dict."""
    base = load_strategy_config()
    result = strategy_param_scan._run(
        "trend|baseline", base, mode="trend",
    )
    assert result is not None
    expected = {
        "label", "mode", "rebalance_delta", "overrides", "total_return",
        "annualized", "max_drawdown", "sharpe", "num_trades", "slippage",
    }
    assert expected <= result.keys()
    assert result["label"] == "trend|baseline"
    assert result["mode"] == "trend"
    assert isinstance(result["num_trades"], int)


def test_run_returns_none_on_empty_backtester_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``PortfolioBacktester.run`` returns an empty dict, ``_run`` must
    surface that as None so callers can skip the row.

    Why: an empty backtest output (e.g. empty price matrix) is not an
    error — the param-scan loop should keep marching and let other
    grid cells succeed. We pin the partial-failure contract here.
    """
    csv_path = _write_prices(tmp_path)
    monkeypatch.setattr(strategy_param_scan, "PRICES", str(csv_path))

    class _EmptyBacktester:
        def __init__(self, *a, **kw):
            pass
        def run(self, *a, **kw):
            return {}

    monkeypatch.setattr(strategy_param_scan, "PortfolioBacktester", _EmptyBacktester)
    base = load_strategy_config()
    result = strategy_param_scan._run("trend|empty", base, mode="trend")
    assert result is None


def test_run_propagates_rebalance_delta_into_backtester(
    patched_prices: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``rebalance_delta`` kwarg must flow into ``PortfolioBacktester``.

    Why: this is the friction-story knob the scan is designed to test;
    if it doesn't propagate, the whole ``trend|rebalance_delta=*`` sweep
    is comparing identical configurations.
    """
    captured: dict[str, Any] = {}

    real_cls = strategy_param_scan.PortfolioBacktester

    class _SpyBacktester(real_cls):  # type: ignore[misc]
        def __init__(self, *args, **kwargs):
            captured["min_rebalance_weight_delta"] = kwargs.get(
                "min_rebalance_weight_delta"
            )
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(strategy_param_scan, "PortfolioBacktester", _SpyBacktester)
    base = load_strategy_config()
    result = strategy_param_scan._run(
        "trend|rd=0.07", base, mode="trend", rebalance_delta=0.07,
    )
    assert result is not None
    assert captured["min_rebalance_weight_delta"] == 0.07
    assert result["rebalance_delta"] == 0.07


# ---------------------------------------------------------------------------
# main() — full sweep
# ---------------------------------------------------------------------------


def test_main_completes_full_sweep_and_returns_zero(patched_prices: Path) -> None:
    """``main()`` runs the documented 12-cell sweep and exits 0.

    The sweep covers (5 score levels + 5 rebalance deltas + 1 regime
    + 1 ensemble) = 12 rows. We capture stdout and assert the table
    header is present so a future refactor doesn't silently drop a row.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = strategy_param_scan.main([])
    assert rc == 0
    output = buf.getvalue()
    # Header is present.
    assert "label" in output
    assert "return" in output
    # Each named cell should produce one line.
    expected_labels = [
        "trend|min_score=15",
        "trend|min_score=20",
        "trend|min_score=25",
        "trend|min_score=30",
        "trend|min_score=35",
        "trend|rebalance_delta=0.03",
        "trend|rebalance_delta=0.05",
        "trend|rebalance_delta=0.07",
        "trend|rebalance_delta=0.1",
        "trend|rebalance_delta=0.15",
        "regime_only",
        "ensemble_on",
    ]
    for label in expected_labels:
        assert label in output, f"missing sweep row: {label!r}"


def test_main_partial_failure_continues_remaining_rows(
    patched_prices: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``_run`` returns None for one cell, ``main`` must keep printing
    the rest of the sweep — partial failure must not abort the whole table.

    Why: a long parameter scan that aborts on the first bad cell wastes
    everything the user computed before it. The pretty-print loop already
    guards with ``if r is None: continue``; we lock that contract.
    """
    real_run = strategy_param_scan._run
    call_state = {"n": 0}

    def _faulty_run(label, *args, **kwargs):
        call_state["n"] += 1
        # Force the 3rd cell to fail (None), the rest to succeed.
        if call_state["n"] == 3:
            return None
        return real_run(label, *args, **kwargs)

    monkeypatch.setattr(strategy_param_scan, "_run", _faulty_run)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = strategy_param_scan.main([])
    assert rc == 0
    output = buf.getvalue()
    # First two cells must be present.
    assert "trend|min_score=15" in output
    assert "trend|min_score=20" in output
    # Third cell (None) is omitted from the printed table.
    assert "trend|min_score=25" not in output
    # And the loop continued — later cells still appear.
    assert "trend|min_score=35" in output
    assert "regime_only" in output
    assert "ensemble_on" in output


# ---------------------------------------------------------------------------
# argparse — CLI surface
# ---------------------------------------------------------------------------


def test_argparse_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """``--help`` must exit 0 with the new flags documented.

    Why: the script is now scriptable; ``--help`` is the public contract
    for what flags exist. We pin it so a rename can't silently drop a
    sweep dimension.
    """
    with pytest.raises(SystemExit) as excinfo:
        strategy_param_scan.main(["--help"])
    # argparse uses code 0 for --help.
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    # The four new flags must all appear in the help text.
    assert "--prices-csv" in out
    assert "--min-scores" in out
    assert "--rebalance-deltas" in out
    assert "--output-csv" in out


def test_argparse_rejects_unknown_flag() -> None:
    """An unrecognised flag must abort with SystemExit (argparse's default).

    Why: silently accepting typo'd flags would let users think they ran
    a custom sweep when they actually ran the defaults.
    """
    parser = strategy_param_scan._build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--bogus-flag", "x"])


def test_argparse_defaults_match_legacy_hardcoded_sweep() -> None:
    """Defaults must match the legacy hardcoded grid bit-for-bit.

    Why: defaults are public API — any change shifts every cron-driven
    run silently. We pin them so a deliberate change shows up as a diff.
    """
    parser = strategy_param_scan._build_arg_parser()
    args = parser.parse_args([])
    assert args.prices_csv == strategy_param_scan.PRICES
    assert tuple(args.min_scores) == (15.0, 20.0, 25.0, 30.0, 35.0)
    assert tuple(args.rebalance_deltas) == (0.03, 0.05, 0.07, 0.10, 0.15)
    assert args.output_csv is None


def test_argparse_custom_prices_csv_overrides_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--prices-csv`` must override the module-level PRICES default.

    Why: this is the primary new flag — without it, the script is
    still effectively hardcoded.
    """
    csv_path = _write_prices(tmp_path)
    # Move PRICES to a non-existent path so we'd notice if the default
    # leaks through.
    monkeypatch.setattr(strategy_param_scan, "PRICES", "/does/not/exist.csv")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = strategy_param_scan.main(["--prices-csv", str(csv_path)])
    assert rc == 0
    # The sweep ran end-to-end against the custom CSV.
    assert "trend|min_score=15" in buf.getvalue()


def test_argparse_custom_min_scores_shrinks_sweep(
    patched_prices: Path,
) -> None:
    """``--min-scores`` must control which min_score rows appear.

    Why: this is the friction-knob of the harness — shrinking the grid
    is the main reason to use flags rather than the defaults.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = strategy_param_scan.main([
            "--min-scores", "20,30",
            # Keep rebalance grid tiny so the test stays fast.
            "--rebalance-deltas", "0.05",
        ])
    assert rc == 0
    output = buf.getvalue()
    # Only the two requested score cells appear.
    assert "trend|min_score=20" in output
    assert "trend|min_score=30" in output
    assert "trend|min_score=15" not in output
    assert "trend|min_score=35" not in output
    # Only the one rebalance cell appears.
    assert "trend|rebalance_delta=0.05" in output
    assert "trend|rebalance_delta=0.03" not in output


def test_argparse_invalid_float_list_rejected() -> None:
    """A non-numeric entry in ``--min-scores`` must abort with SystemExit.

    Why: this is the only custom type-converter in the parser; we pin
    the error path so a refactor can't silently coerce garbage to NaN.
    """
    parser = strategy_param_scan._build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--min-scores", "abc,30"])


def test_output_csv_writes_results(
    patched_prices: Path, tmp_path: Path,
) -> None:
    """``--output-csv`` must emit a machine-readable summary of the sweep.

    Why: the pretty-printed table is unparseable; downstream tooling
    (notebooks, dashboards) needs structured output. The CSV is the
    only structured surface this script now offers.
    """
    out_csv = tmp_path / "sweep.csv"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = strategy_param_scan.main([
            "--min-scores", "20",
            "--rebalance-deltas", "0.05",
            "--output-csv", str(out_csv),
        ])
    assert rc == 0
    assert out_csv.exists()
    text = out_csv.read_text(encoding="utf-8")
    # Header + at least one row.
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= 2
    assert "label" in lines[0]
    assert "total_return" in lines[0]
    assert "trend|min_score=20" in text
