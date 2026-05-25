"""Tests for the walk-forward ETF rotation parameter scan."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import walkforward_etf_rotation
from src.strategy.etf_rotation_strategy import EtfRotationStrategy, EtfScoringConfig


def _write_prices(tmp_path: Path, periods: int = 600) -> Path:
    dates = pd.bdate_range("2022-01-03", periods=periods)
    rng = np.random.default_rng(11)
    codes = ["510300", "159985", "512400", "518680", "513130"]
    data = {}
    for offset, code in enumerate(codes):
        drift = np.linspace(0.0, 0.25 - 0.05 * offset, len(dates))
        noise = np.cumsum(rng.normal(0.0, 0.004, len(dates)))
        data[code] = 5.0 * np.exp(drift + noise)
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame(data, index=dates).to_csv(csv_path)
    return csv_path


# ---------------------------------------------------------------------------
# Grid loading
# ---------------------------------------------------------------------------


def test_load_grid_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"not_a_field": [1, 2]}))
    with pytest.raises(ValueError):
        walkforward_etf_rotation.load_grid(path)


def test_load_grid_strips_underscore_comments(tmp_path: Path) -> None:
    path = tmp_path / "grid.json"
    path.write_text(json.dumps({
        "_note": "ignored",
        "momentum_return20_multiplier": [200.0, 250.0],
    }))
    grid = walkforward_etf_rotation.load_grid(path)
    assert "momentum_return20_multiplier" in grid
    assert "_note" not in grid


def test_expand_grid_cartesian_product() -> None:
    grid = {
        "momentum_return20_multiplier": [200.0, 250.0],
        "premium_hard_threshold": [0.04, 0.05],
    }
    configs = walkforward_etf_rotation.expand_grid(grid)
    assert len(configs) == 4
    multipliers = {c.momentum_return20_multiplier for c in configs}
    thresholds = {c.premium_hard_threshold for c in configs}
    assert multipliers == {200.0, 250.0}
    assert thresholds == {0.04, 0.05}


def test_expand_grid_empty_returns_default_config() -> None:
    configs = walkforward_etf_rotation.expand_grid({})
    assert len(configs) == 1
    assert configs[0] == EtfScoringConfig()


# ---------------------------------------------------------------------------
# Window iteration
# ---------------------------------------------------------------------------


def test_iter_windows_yields_non_overlapping_test_slices() -> None:
    index = pd.bdate_range("2024-01-01", periods=200)
    windows = list(walkforward_etf_rotation.iter_windows(index, train_days=120, test_days=20))

    assert len(windows) > 0
    # Test slices must be contiguous and non-overlapping by default
    for prev, curr in zip(windows, windows[1:]):
        assert prev[1].max() < curr[1].min()


def test_iter_windows_rejects_zero_sizes() -> None:
    index = pd.bdate_range("2024-01-01", periods=50)
    with pytest.raises(ValueError):
        list(walkforward_etf_rotation.iter_windows(index, train_days=0, test_days=10))


# ---------------------------------------------------------------------------
# End-to-end run
# ---------------------------------------------------------------------------


def test_run_walkforward_returns_per_window_oos_metrics(tmp_path: Path) -> None:
    csv_path = _write_prices(tmp_path, periods=600)
    grid_path = tmp_path / "grid.json"
    grid_path.write_text(json.dumps({"momentum_return20_multiplier": [200.0, 300.0]}))

    result = walkforward_etf_rotation.run_walkforward(
        csv_path,
        grid_path,
        train_days=250,
        test_days=60,
    )
    assert result["summary"]["num_windows"] >= 1
    assert len(result["configs"]) == 2
    first = result["windows"][0]
    assert first["best_config_index"] in {0, 1}
    assert first["out_of_sample"] is not None
    assert "sharpe_ratio" in first["out_of_sample"]


def test_run_walkforward_without_grid_uses_default_config(tmp_path: Path) -> None:
    csv_path = _write_prices(tmp_path, periods=500)
    result = walkforward_etf_rotation.run_walkforward(
        csv_path,
        grid_path=None,
        train_days=250,
        test_days=60,
    )
    assert len(result["configs"]) == 1
    assert (
        result["configs"][0]["momentum_return20_multiplier"]
        == EtfScoringConfig().momentum_return20_multiplier
    )


def test_run_walkforward_payload_declares_manual_only_execution_contract(
    tmp_path: Path,
) -> None:
    """Machine-readable output must preserve the no-auto-ordering contract."""
    csv_path = _write_prices(tmp_path, periods=500)

    result = walkforward_etf_rotation.run_walkforward(
        csv_path,
        grid_path=None,
        train_days=250,
        test_days=60,
    )

    assert result["execution_contract"] == {
        "mode": "manual_only",
        "not_auto_ordering": True,
        "broker_api_calls": False,
        "review_required": True,
    }


def test_credibility_summary_compares_oos_to_equal_weight_benchmark(tmp_path: Path) -> None:
    """The report layer must say whether OOS windows beat a naive benchmark."""
    csv_path = _write_prices(tmp_path, periods=600)
    result = walkforward_etf_rotation.run_walkforward(
        csv_path,
        grid_path=None,
        train_days=250,
        test_days=60,
    )
    prices = pd.read_csv(csv_path, index_col=0)
    prices.index = pd.to_datetime(prices.index)

    summary = walkforward_etf_rotation.build_credibility_summary(result, prices)

    assert summary["num_windows"] == result["summary"]["num_windows"]
    assert summary["benchmark_name"] == "equal_weight_buy_hold"
    assert 0 <= summary["oos_win_rate_vs_benchmark"] <= 1
    assert "mean_oos_excess_return" in summary
    assert summary["verdict"] in {
        "credible_watchlist",
        "mixed_watchlist",
        "not_credible",
    }


def test_render_walkforward_report_surfaces_caveats_and_windows(tmp_path: Path) -> None:
    """Markdown report should be self-contained enough for manual review."""
    csv_path = _write_prices(tmp_path, periods=600)
    result = walkforward_etf_rotation.run_walkforward(
        csv_path,
        grid_path=None,
        train_days=250,
        test_days=60,
    )
    prices = pd.read_csv(csv_path, index_col=0)
    prices.index = pd.to_datetime(prices.index)

    report = walkforward_etf_rotation.render_walkforward_report(
        result,
        prices,
        source_label="synthetic fixture",
        generated_at="2026-05-25",
    )

    assert "# ETF Rotation Walk-Forward Credibility Report" in report
    assert "equal_weight_buy_hold" in report
    assert "manual-only" in report
    assert "not auto-ordering" in report
    assert "## Window Detail" in report


# ---------------------------------------------------------------------------
# Faithful out-of-sample evaluation
#
# The bug: the OOS test was previously run on ONLY the test slice. With
# warmup_days=60 and test_days=63, the strategy can only emit signals for
# ~3 bars of a 63-bar window — the rest are warmup zeros — so the reported
# OOS metrics were not a faithful read of the test window. The strategy
# must receive the FULL history (so warmup is satisfied) and the test
# window must be sliced AFTER signal generation, matching
# ``src/backtest/etf_rotation_walkforward.py``.
# ---------------------------------------------------------------------------


def test_evaluate_window_strategy_sees_warmup_before_test_slice(tmp_path: Path) -> None:
    """The OOS evaluation must give the strategy full history so the test
    window is fully covered by live (non-warmup) signals.

    We probe by capturing the price frame the strategy is asked to score:
    it must extend well before the test window's first bar — by at least
    the warmup length — rather than starting at the test window itself.
    """

    csv_path = _write_prices(tmp_path, periods=600)
    prices = pd.read_csv(csv_path, index_col=0)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")

    windows = list(
        walkforward_etf_rotation.iter_windows(
            prices.index, train_days=250, test_days=63,
        )
    )
    assert windows, "fixture should yield at least one window"
    train_index, test_index = windows[0]

    seen_lengths: list[int] = []
    real_generate = EtfRotationStrategy.generate_signals

    def _spy(self, price_matrix, *args, **kwargs):  # type: ignore[no-untyped-def]
        seen_lengths.append(len(price_matrix))
        return real_generate(self, price_matrix, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(EtfRotationStrategy, "generate_signals", _spy)
        walkforward_etf_rotation.evaluate_window(
            prices,
            train_index,
            test_index,
            [EtfScoringConfig()],
            initial_capital=100_000.0,
            commission=0.001,
            slippage=0.001,
            min_rebalance_weight_delta=0.03,
        )

    # evaluate_window evaluates every config in-sample first, then the
    # winning config once out-of-sample. With a single-config grid the
    # LAST generate_signals call is the OOS leg. It must NOT be starved:
    # the strategy has to be handed a frame longer than the 63-bar test
    # slice — it needs the 60-bar warmup on top. A frame of length ~63
    # means the OOS leg saw only the bare test slice.
    assert seen_lengths, "evaluate_window should invoke generate_signals"
    oos_input_len = seen_lengths[-1]
    assert oos_input_len >= len(test_index) + 60, (
        f"OOS strategy input was only {oos_input_len} bars; with a "
        f"{len(test_index)}-bar test window and 60-bar warmup it must be "
        f">= {len(test_index) + 60}. The strategy is being starved of warmup."
    )


def test_evaluate_window_oos_signals_cover_whole_test_window(tmp_path: Path) -> None:
    """Every bar of the OOS test window must carry a live signal.

    The starved bug only delivered a non-zero weight for ~2-3 of 63 test
    bars (the rest were warmup zeros). A correctly-warmed run delivers a
    signal on every test bar. We capture the weight frame the backtester
    actually executes on the OOS leg and assert near-full coverage.
    """

    csv_path = _write_prices(tmp_path, periods=600)
    prices = pd.read_csv(csv_path, index_col=0)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")

    windows = list(
        walkforward_etf_rotation.iter_windows(
            prices.index, train_days=250, test_days=63,
        )
    )
    train_index, test_index = windows[0]

    # Spy on the weight frame the OOS run feeds the execution engine. The
    # backtester slices weights to the price-matrix index it executes on,
    # so the frame restricted to the test window tells us coverage.
    captured: list[pd.DataFrame] = []
    real_generate = EtfRotationStrategy.generate_signals

    def _spy(self, price_matrix, *args, **kwargs):  # type: ignore[no-untyped-def]
        weights = real_generate(self, price_matrix, *args, **kwargs)
        captured.append(weights)
        return weights

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(EtfRotationStrategy, "generate_signals", _spy)
        walkforward_etf_rotation.evaluate_window(
            prices,
            train_index,
            test_index,
            [EtfScoringConfig()],
            initial_capital=100_000.0,
            commission=0.001,
            slippage=0.001,
            min_rebalance_weight_delta=0.03,
        )

    oos_weights = captured[-1]
    in_window = oos_weights.reindex(test_index)
    covered = int((in_window.abs().sum(axis=1) > 0).sum())
    # Allow a tiny shortfall for the 1-bar signal lag; the point is that
    # the OOS window is fully warmed, not starved to a handful of bars.
    assert covered >= len(test_index) - 2, (
        f"only {covered} of {len(test_index)} OOS test bars carry a live "
        f"signal — the strategy was starved of its 60-bar warmup."
    )
