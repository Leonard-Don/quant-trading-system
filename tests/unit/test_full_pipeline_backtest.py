"""Unit tests for the full-pipeline ETF rotation backtest script.

These tests stay hermetic — no network, no live prices. Synthetic price
matrices written to ``tmp_path`` drive ``FullPipelineStrategy`` and
``run_backtest`` end-to-end so we cover construction, CLI exit codes,
output schema, and per-mode (trend / regime / ensemble) wiring.

Only external IO (``load_price_matrix`` reading the CSV) is mocked or
redirected via ``tmp_path``; the strategy classes themselves run for
real against synthetic uptrending price data — that's the only way to
catch regressions in the layer-stacking logic (regime + ensemble + risk
rules).
"""

from __future__ import annotations

import io
import json
import logging
import sys
from contextlib import redirect_stdout
from dataclasses import replace as dc_replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import full_pipeline_backtest
from src.strategy.etf_rotation_config_loader import load_strategy_config

DEFAULT_CODES = ["159985", "512400", "510300", "518680", "513130"]


# ---------------------------------------------------------------------------
# Synthetic price fixture
# ---------------------------------------------------------------------------


def _write_prices(
    tmp_path: Path,
    *,
    periods: int = 320,
    codes: list[str] | None = None,
    filename: str = "prices.csv",
) -> Path:
    """Build a deterministic price CSV with mild uptrends per asset.

    320 bars comfortably clears the 200-day warmup that
    ``FullPipelineStrategy`` enforces inside ``generate_signals``.
    """

    codes = codes or DEFAULT_CODES
    dates = pd.bdate_range("2023-01-02", periods=periods)
    rng = np.random.default_rng(11)
    data = {}
    for offset, code in enumerate(codes):
        drift = np.linspace(0.0, 0.25 - 0.04 * offset, len(dates))
        noise = np.cumsum(rng.normal(0.0, 0.003, len(dates)))
        data[code] = 5.0 * np.exp(drift + noise)
    csv_path = tmp_path / filename
    pd.DataFrame(data, index=dates).to_csv(csv_path)
    return csv_path


# ---------------------------------------------------------------------------
# Construction / argparse
# ---------------------------------------------------------------------------


def test_full_pipeline_strategy_rejects_unknown_mode() -> None:
    """``FullPipelineStrategy(mode=...)`` must reject anything but trend/regime/ensemble.

    Why: a silent fallthrough on a typo'd mode would mean the user's
    backtest doesn't reflect the layer they think they're exercising.
    """

    cfg = load_strategy_config()
    with pytest.raises(ValueError, match=r"mode must be trend\|regime\|ensemble"):
        full_pipeline_backtest.FullPipelineStrategy(
            strategy_config=cfg, mode="bogus"
        )


@pytest.mark.parametrize("mode", ["trend", "regime", "ensemble"])
def test_full_pipeline_strategy_accepts_each_mode(mode: str) -> None:
    """All three documented modes must construct cleanly."""

    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode=mode
    )
    assert strat._mode == mode
    # Default holdings are the 5-ETF seed.
    assert set(strat._asset_codes) == set(DEFAULT_CODES)
    assert strat.regime_counts == {}
    assert strat.regime_history == []


def test_argparse_rejects_unknown_mode_flag() -> None:
    """argparse must reject a ``--mode`` value outside the documented choices.

    Why: ``argparse`` exits the process with SystemExit(2) on a bad
    choice — we pin that contract so the CLI doesn't silently accept
    typos or new modes that haven't been wired through ``_compute_bar``.
    """

    parser = full_pipeline_backtest._build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--prices-csv", "x.csv", "--mode", "not-a-mode"])


def test_argparse_rejects_missing_required_prices_csv() -> None:
    """``--prices-csv`` is required; omitting it must abort with SystemExit."""

    parser = full_pipeline_backtest._build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_argparse_defaults_match_documented_values() -> None:
    """Argparse defaults must match the docstring / docs.

    Why: defaults are public API — changing them silently shifts every
    cron-driven run's behaviour. Pin them so a deliberate change shows
    up as a test diff.
    """

    parser = full_pipeline_backtest._build_arg_parser()
    args = parser.parse_args(["--prices-csv", "anything.csv"])
    assert args.mode == "ensemble"
    assert args.initial_capital == 100_000.0
    assert args.commission == 0.001
    assert args.slippage == 0.001


# ---------------------------------------------------------------------------
# generate_signals — per-mode wiring
# ---------------------------------------------------------------------------


def test_generate_signals_returns_full_weight_matrix_in_trend_mode(
    tmp_path: Path,
) -> None:
    """Trend mode must emit a (T, N) weight DataFrame aligned to the price
    matrix index/columns. Weights pre-warmup should be 0; post-warmup
    should be in [0, 1] and respect the asset config caps.

    Why: this is the surface the ``PortfolioBacktester`` consumes; any
    shape regression here breaks every downstream consumer.
    """

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="trend", lag_days=1
    )
    weights = strat.generate_signals(matrix)
    assert weights.shape == matrix.shape
    assert list(weights.columns) == list(matrix.columns)
    # First 200 rows are zero — generate_signals enforces a warmup_days
    # floor of 200 plus a 1-day lag.
    assert (weights.iloc[:200].to_numpy() == 0.0).all()
    # All weights live in [0, 1] (target-weight semantics).
    assert weights.to_numpy().min() >= -1e-12
    assert weights.to_numpy().max() <= 1.0 + 1e-9


def test_generate_signals_records_regime_history_in_regime_mode(
    tmp_path: Path,
) -> None:
    """Regime mode must populate ``regime_counts`` and ``regime_history``
    once the price matrix has at least one valid bar past warmup."""

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="regime", lag_days=1
    )
    strat.generate_signals(matrix)
    # At least one bar must have been classified into some regime label.
    assert sum(strat.regime_counts.values()) > 0
    # The history entries carry the timestamp + regime + multiplier triple.
    assert strat.regime_history
    first = strat.regime_history[0]
    assert {"timestamp", "regime", "gross_cap_multiplier"} <= first.keys()


def test_generate_signals_ensemble_mode_runs_when_ensemble_enabled(
    tmp_path: Path,
) -> None:
    """Ensemble mode with ``ensemble.enabled=True`` must still emit a
    valid weight matrix (the blender is exercised, not bypassed).

    The user's strategy.json defaults to ensemble disabled — flip it on
    inline so this test exercises the blend branch.
    """

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    base = load_strategy_config()
    cfg = dc_replace(base, ensemble={**dict(base.ensemble), "enabled": True})
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="ensemble", lag_days=1
    )
    weights = strat.generate_signals(matrix)
    assert weights.shape == matrix.shape
    # Sanity: there should still be at least some non-zero rows past warmup.
    assert (weights.iloc[200:].to_numpy() > 0).any()


# ---------------------------------------------------------------------------
# run_backtest — top-level entry
# ---------------------------------------------------------------------------


def test_run_backtest_returns_summary_dict_with_expected_keys(tmp_path: Path) -> None:
    """``run_backtest`` must return the documented summary schema."""

    csv_path = _write_prices(tmp_path)
    summary = full_pipeline_backtest.run_backtest(csv_path, mode="trend")
    required = {
        "mode", "initial_capital", "final_value", "total_return",
        "annualized_return", "max_drawdown", "sharpe_ratio",
        "num_trades", "execution_costs", "regime_breakdown",
    }
    assert required <= summary.keys()
    assert summary["mode"] == "trend"
    assert summary["initial_capital"] == 100_000.0
    assert isinstance(summary["num_trades"], int)


def test_run_backtest_returns_empty_dict_on_empty_price_matrix(
    tmp_path: Path,
) -> None:
    """An empty price CSV must produce an empty summary, not a crash.

    Why: cron-driven backtests can fail upstream (data feeds down,
    cache miss). The script must degrade to {} so the wrapper can
    treat it as "no data" rather than report fake numbers.
    """

    csv_path = tmp_path / "empty.csv"
    pd.DataFrame({code: [] for code in DEFAULT_CODES}).to_csv(csv_path)
    summary = full_pipeline_backtest.run_backtest(csv_path, mode="trend")
    assert summary == {}


def test_run_backtest_accepts_caller_supplied_strategy_config(
    tmp_path: Path,
) -> None:
    """Callers must be able to inject a pre-built StrategyConfig (tests).

    Why: ``run_backtest`` is reused by ``strategy_param_scan`` via
    ``FullPipelineStrategy`` directly, but the docstring promises a
    one-call backtest entry. Override config must flow through. We pin
    that by changing ``initial_capital`` (a flow-only knob with no
    interaction with scoring) and asserting it surfaces in the summary.
    """

    csv_path = _write_prices(tmp_path)
    base = load_strategy_config()
    custom = dc_replace(base)  # same config, but proves injection works
    summary = full_pipeline_backtest.run_backtest(
        csv_path, mode="trend", strategy_config=custom,
        initial_capital=250_000.0,
    )
    assert summary["initial_capital"] == 250_000.0
    # And ``run_backtest`` does not call ``load_strategy_config`` again
    # when one is supplied; if it did, the source_path would always be
    # populated. We can't easily assert "not called", but we can verify
    # the summary completes without exception even when we pass a custom
    # config object with a None source_path.
    no_path = dc_replace(custom, source_path=None)
    summary2 = full_pipeline_backtest.run_backtest(
        csv_path, mode="trend", strategy_config=no_path,
    )
    assert summary2["mode"] == "trend"


# ---------------------------------------------------------------------------
# main() — CLI exit codes and JSON output
# ---------------------------------------------------------------------------


def test_main_returns_zero_and_prints_json_summary(tmp_path: Path) -> None:
    """main() with valid args must exit 0 and emit a JSON document."""

    csv_path = _write_prices(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = full_pipeline_backtest.main([
            "--prices-csv", str(csv_path),
            "--mode", "trend",
        ])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["mode"] == "trend"
    assert payload["initial_capital"] == 100_000.0


def test_main_raises_on_missing_prices_csv() -> None:
    """A non-existent ``--prices-csv`` should bubble up the file IO error.

    Why: failing loudly is correct for a backtest CLI — silently
    writing a degenerate result would let cron jobs claim success.
    """

    with pytest.raises(FileNotFoundError):
        full_pipeline_backtest.main([
            "--prices-csv", "/nonexistent/path/prices.csv",
            "--mode", "trend",
        ])


# ---------------------------------------------------------------------------
# Per-bar fault tolerance + regime / risk-rule edge cases
# ---------------------------------------------------------------------------


def test_generate_signals_below_error_threshold_continues_and_logs_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Per-bar failures below the threshold are swallowed; success summary is logged.

    Why: a transient bug in scoring shouldn't abort an entire historical
    backtest. Bars that fail land as zeros, but as long as the rate stays
    under ``max_error_rate`` we proceed and emit a final summary line so
    operators can see how clean the run was.
    """

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="trend", lag_days=1,
        # Allow up to 100% failure rate so we can pin the "swallows" branch
        # without the threshold raising.
        max_error_rate=1.0,
    )

    # Fail roughly the first 10% of post-warmup bars only.
    call_state = {"n": 0}
    real = strat._compute_bar

    def _flaky(window, timestamp):
        call_state["n"] += 1
        if call_state["n"] <= 10:
            raise RuntimeError("simulated transient scoring failure")
        return real(window, timestamp)

    monkeypatch.setattr(strat, "_compute_bar", _flaky)
    caplog.set_level(logging.INFO, logger=full_pipeline_backtest.logger.name)
    weights = strat.generate_signals(matrix)
    # No raise; weights matrix has the expected shape.
    assert weights.shape == matrix.shape
    # Some bars succeeded → at least one non-zero post-warmup row.
    assert (weights.iloc[200:].to_numpy() > 0).any()
    # The success summary log line is emitted.
    assert any(
        "Backtest completed" in rec.getMessage() and "bars succeeded" in rec.getMessage()
        for rec in caplog.records
    ), f"missing summary log; got: {[r.getMessage() for r in caplog.records[-5:]]}"


def test_generate_signals_above_error_threshold_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If every bar fails, the threshold guard must raise with a clear message.

    Why: a multi-year backtest where 100% of bars fail is not a transient
    issue — it's a data integrity problem (wrong schema, NaN columns,
    etc.). Cron jobs must halt loudly rather than write a degenerate
    summary that looks like success.
    """

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="trend", lag_days=1,
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated scoring failure")

    monkeypatch.setattr(strat, "_compute_bar", _boom)
    with pytest.raises(RuntimeError, match=r"Per-bar failure rate .* exceeds threshold"):
        strat.generate_signals(matrix)


def test_generate_signals_custom_max_error_rate_allows_higher_tolerance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``max_error_rate=0.5`` must allow up to 50% per-bar failure without raising.

    Why: noisy alt-data corpuses (e.g. early-2020 COVID gap) legitimately
    produce more failures than the 25% default. Users need a knob to
    tune tolerance without monkey-patching internals.
    """

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="trend", lag_days=1,
        max_error_rate=0.5,
    )

    # Fail every other call → roughly 50% failure rate.
    call_state = {"n": 0}
    real = strat._compute_bar

    def _alternating(window, timestamp):
        call_state["n"] += 1
        if call_state["n"] % 2 == 0:
            raise RuntimeError("simulated alternating failure")
        return real(window, timestamp)

    monkeypatch.setattr(strat, "_compute_bar", _alternating)
    # Should not raise — 50% is at-or-below the 50% threshold (strict >).
    weights = strat.generate_signals(matrix)
    assert weights.shape == matrix.shape


def test_full_pipeline_strategy_rejects_invalid_max_error_rate() -> None:
    """``max_error_rate`` outside [0.0, 1.0] must raise at construction time.

    Why: the threshold is a fraction; values outside that range indicate
    a unit confusion (percent vs. fraction). We pin a fail-fast contract
    so the script can't run with a meaningless tolerance.
    """

    cfg = load_strategy_config()
    with pytest.raises(ValueError, match=r"max_error_rate must be in"):
        full_pipeline_backtest.FullPipelineStrategy(
            strategy_config=cfg, mode="trend", max_error_rate=1.5,
        )
    with pytest.raises(ValueError, match=r"max_error_rate must be in"):
        full_pipeline_backtest.FullPipelineStrategy(
            strategy_config=cfg, mode="trend", max_error_rate=-0.1,
        )


def test_argparse_max_error_rate_flag_default_and_override() -> None:
    """``--max-error-rate`` must default to 0.25 and accept a custom value.

    Why: this is the new public knob from the threshold refactor. Pin
    both default and override paths so the CLI surface is locked.
    """

    parser = full_pipeline_backtest._build_arg_parser()
    args = parser.parse_args(["--prices-csv", "x.csv"])
    assert args.max_error_rate == 0.25
    args = parser.parse_args(["--prices-csv", "x.csv", "--max-error-rate", "0.5"])
    assert args.max_error_rate == 0.5


def test_compute_bar_skips_risk_rules_when_apply_risk_rules_false(
    tmp_path: Path,
) -> None:
    """``apply_risk_rules=False`` must return the raw strategy weights.

    Why: this branch (``return target_weights, regime_label`` at line ~221)
    is a public knob for testing the strategy in isolation from the
    risk-rules layer. Cover it explicitly.
    """

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="trend", lag_days=1, apply_risk_rules=False,
    )
    # Pull one specific post-warmup window
    window = matrix.iloc[: 250]
    weights, _regime = strat._compute_bar(window, window.index[-1])
    assert isinstance(weights, dict)
    # Without risk rules, no CASH key should appear (the strategy itself
    # doesn't emit one — only ``apply_etf_portfolio_risk_rules`` does).
    assert "CASH" not in weights


def test_classify_returns_none_when_regime_disabled(tmp_path: Path) -> None:
    """``_classify`` must return None when ``regime.enabled`` is False.

    Why: regime classification is opt-in (the user can disable it
    via strategy.json); the per-bar code path must respect that flag
    without falling back to a default regime label.
    """

    csv_path = _write_prices(tmp_path)
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    base = load_strategy_config()
    cfg = dc_replace(base, regime={**dict(base.regime), "enabled": False})
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="regime", lag_days=1,
    )
    decision = strat._classify(matrix.iloc[: 250])
    assert decision is None


def test_classify_returns_none_when_proxy_code_absent(tmp_path: Path) -> None:
    """If the regime proxy code isn't in the price matrix, classification
    must short-circuit to None rather than raising KeyError.

    Why: callers might pass a price matrix that doesn't include the
    default proxy (510300 / SH000300); failing fast with KeyError
    would mask a config mismatch as a crash.
    """

    csv_path = _write_prices(tmp_path, codes=["159985", "512400", "518680", "513130"])
    matrix = full_pipeline_backtest.load_price_matrix(csv_path)
    cfg = load_strategy_config()
    strat = full_pipeline_backtest.FullPipelineStrategy(
        strategy_config=cfg, mode="regime", lag_days=1,
    )
    decision = strat._classify(matrix.iloc[: 250])
    assert decision is None
