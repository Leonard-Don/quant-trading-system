"""Unit tests for :mod:`src.backtest.parameter_optimizer`.

Coverage targets:

1. Construction validation — unknown grid keys, empty values, oversize
   cartesian product, bad metric all raise at construction.
2. Empty grid → returns an empty report with a clear caveat (no crash).
3. Single-config grid → metrics match a direct
   :class:`EtfRotationBacktester` run with the same overrides.
4. Multi-config grid → produces N results, top-N selection respects the
   chosen metric direction.
5. Parameter sensitivity computation works on a hand-built dataset and
   ranks the larger-swing parameter first.
6. Top-N selection honours metric-direction (higher-better for Sharpe,
   lower-better for MaxDD).
7. Transaction cost model threads through every config (caveats reflect
   it; default-off caveat absent when TC enabled).
8. Walkforward integration smoke — when ``with_walkforward=True``, the
   report carries per-top-config :class:`WalkforwardReport`s.

Synthetic-only; no disk I/O, no network. Suite completes in < 5s.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.backtest.etf_rotation_backtest import (
    BacktestReport,
    EtfRotationBacktester,
)
from src.backtest.etf_rotation_walkforward import WalkforwardReport
from src.backtest.parameter_optimizer import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    MAX_GRID_SIZE,
    SUPPORTED_METRICS,
    ConfigResult,
    OptimizationReport,
    ParameterOptimizer,
    ParameterSensitivity,
    WinnerByMetric,
    _apply_overrides,
    _compute_sensitivity,
    _top_n_by_metric,
)
from src.backtest.transaction_costs import TransactionCostModel
from src.strategy.etf_rotation_strategy import (
    EtfAssetConfig,
    EtfRotationConfig,
    EtfScoringConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(symbols: tuple[str, ...] = ("STRONG", "WEAK")) -> EtfRotationConfig:
    return EtfRotationConfig(
        assets=[EtfAssetConfig(symbol=s, max_weight=0.5) for s in symbols],
        gross_cap=0.9,
        warmup_days=60,
    )


def _trend_market(
    symbols: tuple[str, ...] = ("STRONG", "WEAK"),
    days: int = 360,
    seed: int = 42,
) -> pd.DataFrame:
    """STRONG uptrend, WEAK downtrend. Deterministic across runs."""

    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    rng = np.random.default_rng(seed=seed)
    columns: dict[str, np.ndarray] = {}
    for offset, sym in enumerate(symbols):
        drift = np.linspace(0.0, 0.30 if offset == 0 else -0.20, days)
        noise = rng.normal(0.0, 0.003, days)
        columns[sym] = 100.0 * np.exp(drift + np.cumsum(noise))
    return pd.DataFrame(columns, index=dates)


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


def test_construction_rejects_unknown_grid_key() -> None:
    config = _make_config()
    prices = _trend_market()
    with pytest.raises(ValueError, match="not a dataclass field"):
        ParameterOptimizer(
            base_config=config,
            price_history=prices,
            parameter_grid={"not_a_field": [0.5]},
        )


def test_construction_rejects_empty_value_list() -> None:
    config = _make_config()
    prices = _trend_market()
    with pytest.raises(ValueError, match="at least one candidate value"):
        ParameterOptimizer(
            base_config=config,
            price_history=prices,
            parameter_grid={"gross_cap": []},
        )


def test_construction_rejects_oversize_grid() -> None:
    config = _make_config()
    prices = _trend_market()
    grid = {
        "gross_cap": list(range(MAX_GRID_SIZE + 1)),
    }
    with pytest.raises(ValueError, match="exceeds max_grid_size"):
        ParameterOptimizer(
            base_config=config,
            price_history=prices,
            parameter_grid=grid,
        )


def test_construction_rejects_unsupported_metric() -> None:
    config = _make_config()
    prices = _trend_market()
    with pytest.raises(ValueError, match="optimize_for"):
        ParameterOptimizer(
            base_config=config,
            price_history=prices,
            parameter_grid={"gross_cap": [0.8]},
            optimize_for="not_a_metric",
        )


def test_construction_accepts_dotted_nested_key() -> None:
    """``scoring.trend_above_ma20_points`` is a valid dotted field path."""

    config = _make_config()
    prices = _trend_market()
    opt = ParameterOptimizer(
        base_config=config,
        price_history=prices,
        parameter_grid={"scoring.trend_above_ma20_points": [15.0, 25.0]},
    )
    # Should NOT raise.
    assert opt is not None


# ---------------------------------------------------------------------------
# Empty / single / multi
# ---------------------------------------------------------------------------


def test_empty_grid_returns_empty_report() -> None:
    """Zero-key grid → empty report with caveat, no exception."""

    config = _make_config()
    prices = _trend_market()
    opt = ParameterOptimizer(
        base_config=config,
        price_history=prices,
        parameter_grid={},
    )
    report = opt.run()
    assert isinstance(report, OptimizationReport)
    assert report.n_configs_evaluated == 0
    assert report.configurations == []
    assert any("empty_parameter_grid" in c for c in report.caveats)


def test_single_config_matches_direct_backtest() -> None:
    """One-cell grid → metrics match a direct backtester run."""

    config = _make_config()
    prices = _trend_market(days=240)
    opt = ParameterOptimizer(
        base_config=config,
        price_history=prices,
        parameter_grid={"gross_cap": [0.85]},
        period_start="2024-04-01",
    )
    report = opt.run()

    assert report.n_configs_evaluated == 1
    [only] = report.configurations

    # Re-run directly with the same override.
    direct_cfg = _apply_overrides(config, {"gross_cap": 0.85})
    direct = EtfRotationBacktester(
        config=direct_cfg,
        price_history=prices,
        period_start="2024-04-01",
    ).run()

    assert only.sharpe_ratio == pytest.approx(direct.sharpe_ratio, abs=1e-9)
    assert only.total_return_pct == pytest.approx(direct.total_return_pct, abs=1e-9)
    assert only.max_drawdown_pct == pytest.approx(direct.max_drawdown_pct, abs=1e-9)
    assert only.n_bars == direct.n_bars


def test_multi_config_grid_produces_multiple_results() -> None:
    """3×2=6 grid → 6 configs evaluated, optima populated, JSON serialisable."""

    config = _make_config()
    prices = _trend_market(days=300)
    opt = ParameterOptimizer(
        base_config=config,
        price_history=prices,
        parameter_grid={
            "gross_cap": [0.6, 0.8, 1.0],
            "min_score_to_hold": [15.0, 25.0],
        },
        period_start="2024-04-01",
        top_n=4,
    )
    report = opt.run()

    assert report.n_configs_requested == 6
    assert report.n_configs_evaluated == 6
    assert len(report.configurations) == 6
    # Every config carries its parameter dict and a non-None BacktestReport.
    for cr in report.configurations:
        assert set(cr.parameters.keys()) == {"gross_cap", "min_score_to_hold"}
        assert isinstance(cr.report, BacktestReport)

    # Optima populated for every supported metric.
    for metric in SUPPORTED_METRICS:
        winner = report.optimal_by_metric[metric]
        assert isinstance(winner, WinnerByMetric)
        assert winner.metric == metric

    # JSON round-trip survives.
    payload = report.to_dict()
    encoded = json.dumps(payload, allow_nan=False)
    assert "configurations" in encoded


# ---------------------------------------------------------------------------
# Sensitivity / top-N
# ---------------------------------------------------------------------------


def _stub_config_result(
    cid: int,
    params: dict[str, float],
    sharpe: float,
    max_dd: float = 5.0,
) -> ConfigResult:
    """Build a minimal :class:`ConfigResult` for unit-tests of helpers.

    The :class:`BacktestReport` stub is intentionally minimal — most
    helpers only touch the numeric fields on the ``ConfigResult`` row.
    """

    stub = BacktestReport(
        period_start="2024-01-01",
        period_end="2024-03-31",
        n_bars=60,
        n_assets=2,
        n_rebalances=12,
        initial_capital=100_000.0,
        final_equity=105_000.0,
        total_return_pct=5.0,
        annualized_return_pct=20.0,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd,
        calmar_ratio=20.0 / max_dd if max_dd > 0 else None,
        avg_turnover_pct=10.0,
        win_rate=0.55,
        comparable_buy_hold_return_pct=4.0,
        policy_signal_factor_enabled=False,
        rebalance_freq_days=5,
    )
    return ConfigResult(
        config_id=cid,
        parameters=params,
        sharpe_ratio=sharpe,
        total_return_pct=5.0,
        annualized_return_pct=20.0,
        max_drawdown_pct=max_dd,
        calmar_ratio=20.0 / max_dd if max_dd > 0 else None,
        avg_turnover_pct=10.0,
        win_rate=0.55,
        n_bars=60,
        n_rebalances=12,
        report=stub,
    )


def test_parameter_sensitivity_ranks_higher_spread_first() -> None:
    """A parameter with bigger Sharpe swing must rank above a flat one."""

    # ``alpha`` swings Sharpe by 1.0; ``beta`` is a no-op.
    configs = [
        _stub_config_result(0, {"alpha": 0.1, "beta": 1}, sharpe=0.5),
        _stub_config_result(1, {"alpha": 0.5, "beta": 1}, sharpe=1.5),
        _stub_config_result(2, {"alpha": 0.1, "beta": 2}, sharpe=0.5),
        _stub_config_result(3, {"alpha": 0.5, "beta": 2}, sharpe=1.5),
    ]
    sensitivity = _compute_sensitivity(configs, ["alpha", "beta"])
    # alpha first because its mean-Sharpe std is larger.
    assert sensitivity[0].parameter == "alpha"
    assert sensitivity[1].parameter == "beta"
    assert sensitivity[0].sharpe_std > sensitivity[1].sharpe_std
    # beta has zero spread — both values produce the same mean Sharpe.
    assert sensitivity[1].sharpe_range == pytest.approx(0.0)


def test_top_n_by_metric_respects_direction() -> None:
    """Higher-is-better for Sharpe, lower-is-better for max_drawdown_pct."""

    configs = [
        _stub_config_result(0, {"g": 0.6}, sharpe=0.2, max_dd=10.0),
        _stub_config_result(1, {"g": 0.7}, sharpe=0.8, max_dd=5.0),
        _stub_config_result(2, {"g": 0.8}, sharpe=1.5, max_dd=2.0),
        _stub_config_result(3, {"g": 0.9}, sharpe=1.0, max_dd=8.0),
    ]
    top_sharpe = _top_n_by_metric(configs, metric="sharpe_ratio", n=3)
    assert [c.config_id for c in top_sharpe] == [2, 3, 1]

    top_dd = _top_n_by_metric(configs, metric="max_drawdown_pct", n=2)
    # Lower MaxDD first.
    assert [c.config_id for c in top_dd] == [2, 1]


# ---------------------------------------------------------------------------
# Transaction-cost threading
# ---------------------------------------------------------------------------


def test_tc_model_threads_through_every_config() -> None:
    """Passing a TC model results in every config's report being TC-enabled.

    The default caveat about "no transaction costs modeled" must drop
    out of the optimization-level caveats when TC is supplied.
    """

    config = _make_config()
    prices = _trend_market(days=200)
    tc_model = TransactionCostModel()
    opt = ParameterOptimizer(
        base_config=config,
        price_history=prices,
        parameter_grid={"gross_cap": [0.8, 0.9]},
        period_start="2024-04-01",
        tc_model=tc_model,
    )
    report = opt.run()
    assert report.n_configs_evaluated == 2
    for cr in report.configurations:
        assert cr.report.tc_enabled is True
    assert not any(
        c.startswith("no_transaction_costs_modeled") for c in report.caveats
    )


# ---------------------------------------------------------------------------
# Walkforward integration
# ---------------------------------------------------------------------------


def test_walkforward_integration_smoke() -> None:
    """``with_walkforward=True`` populates per-top-config walkforward reports."""

    config = _make_config()
    # Need enough history for at least one walkforward window (3 months).
    prices = _trend_market(days=360)
    opt = ParameterOptimizer(
        base_config=config,
        price_history=prices,
        parameter_grid={"gross_cap": [0.8, 0.9]},
        period_start="2024-04-01",
        period_end="2025-04-30",
        top_n=2,
    )
    report = opt.run(
        with_walkforward=True,
        walkforward_window_months=3,
        walkforward_step_months=2,
    )
    assert report.walkforward_results
    assert len(report.walkforward_results) == 2
    for _cid, wf in report.walkforward_results.items():
        assert isinstance(wf, WalkforwardReport)
        # The window count is data-dependent but the walkforward report
        # must be well-formed regardless.
        assert wf.window_months == 3
        assert wf.step_months == 2
    assert any(
        c.startswith("walkforward_stability_check_applied_to_top")
        for c in report.caveats
    )
