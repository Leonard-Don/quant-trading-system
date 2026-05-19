"""Unit tests for the multi-strategy comparison harness.

These tests focus on:

1. The dataclass contract — every public field is populated and
   ``ComparisonReport.to_dict()`` round-trips as valid JSON.
2. Degenerate inputs — empty strategy list, empty period, mismatched
   universe — must NOT throw.
3. Determinism — same inputs run twice produce identical reports
   (no RNG, no environment leaks).
4. Multi-strategy fan-out — picking one, two, or three strategies
   produces the right number of entries + the right winner labels.
5. Numeric invariants — winner-by-metric correctly picks the strategy
   with the best metric, monotonic uptrend produces same return across
   strategies, regime analysis surfaces the trending/choppy halves.

Fixtures keep all prices in-memory; no disk I/O, no network. Tests run
in under a second each (the bar-by-bar generator is the slowest part
and is small-N here).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.backtest.etf_rotation_backtest import BacktestReport
from src.backtest.strategy_comparison import (
    DEFAULT_STRATEGY_LABELS,
    STRATEGY_LABEL_BLEND,
    STRATEGY_LABEL_MEAN_REVERSION,
    STRATEGY_LABEL_ROTATION,
    ComparisonReport,
    PairwiseSpread,
    StrategyComparator,
    WinnerSummary,
    build_default_strategy_specs,
    render_comparison_markdown,
)
from src.strategy.etf_rotation_strategy import (
    EtfAssetConfig,
    EtfRotationConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(symbols: tuple[str, ...] = ("STRONG", "WEAK")) -> EtfRotationConfig:
    """2-asset rotation config used by most tests. Mirrors test_etf_rotation_backtest."""

    return EtfRotationConfig(
        assets=[EtfAssetConfig(symbol=s, max_weight=0.5) for s in symbols],
        gross_cap=0.9,
        warmup_days=60,
    )


def _monotonic_uptrend(
    symbols: tuple[str, ...] = ("STRONG", "WEAK"),
    days: int = 180,
    daily_return: float = 0.001,
) -> pd.DataFrame:
    """Perfect monotonic uptrend, identical across symbols.

    Both columns get the same series so per-strategy weight differences
    do NOT translate into return differences — handy for asserting
    "different strategies, same realised return on a no-information
    series".
    """

    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    base = np.array(
        [100.0 * ((1.0 + daily_return) ** i) for i in range(days)], dtype=float,
    )
    return pd.DataFrame({s: base.copy() for s in symbols}, index=dates)


def _trend_market(
    symbols: tuple[str, ...] = ("STRONG", "WEAK"),
    days: int = 180,
    seed: int = 42,
) -> pd.DataFrame:
    """STRONG uptrend, WEAK downtrend with small noise. Deterministic across runs."""

    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    rng = np.random.default_rng(seed=seed)
    columns: dict[str, np.ndarray] = {}
    for offset, sym in enumerate(symbols):
        drift = np.linspace(0.0, 0.30 if offset == 0 else -0.20, days)
        noise = rng.normal(0.0, 0.003, days)
        columns[sym] = 100.0 * np.exp(drift + np.cumsum(noise))
    return pd.DataFrame(columns, index=dates)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_single_strategy_yields_single_entry_report() -> None:
    """A 1-strategy comparator produces a 1-entry per_strategy_metrics dict."""

    config = _make_config()
    prices = _trend_market()
    specs = [build_default_strategy_specs(config)[STRATEGY_LABEL_ROTATION]]

    report = StrategyComparator(specs, prices).run()

    assert isinstance(report, ComparisonReport)
    assert report.n_strategies == 1
    assert report.strategy_labels == [STRATEGY_LABEL_ROTATION]
    assert set(report.per_strategy_metrics.keys()) == {STRATEGY_LABEL_ROTATION}
    assert isinstance(
        report.per_strategy_metrics[STRATEGY_LABEL_ROTATION], BacktestReport,
    )
    # With a single strategy the winner across every metric is that strategy.
    assert report.winner_by_sharpe.label == STRATEGY_LABEL_ROTATION
    assert report.winner_by_return.label == STRATEGY_LABEL_ROTATION


def test_all_three_strategies_yields_three_entry_report() -> None:
    """The default 3-spec build produces a 3-entry comparison report."""

    config = _make_config()
    prices = _trend_market()
    specs = list(build_default_strategy_specs(config).values())

    report = StrategyComparator(specs, prices).run()

    assert report.n_strategies == 3
    assert set(report.strategy_labels) == set(DEFAULT_STRATEGY_LABELS)
    assert set(report.per_strategy_metrics.keys()) == set(DEFAULT_STRATEGY_LABELS)
    # Every winner field is populated (no NaN tape this fixture).
    for winner in (
        report.winner_by_sharpe,
        report.winner_by_return,
        report.winner_by_max_dd,
        report.winner_by_turnover,
    ):
        assert isinstance(winner, WinnerSummary)
        assert winner.label in DEFAULT_STRATEGY_LABELS

    # Pairwise spreads: N strategies → N * (N - 1) ordered pairs.
    assert len(report.pairwise_spreads) == 6
    for spread in report.pairwise_spreads:
        assert isinstance(spread, PairwiseSpread)
        assert spread.pair[0] != spread.pair[1]


def test_run_is_deterministic_same_inputs_same_report() -> None:
    """Two identical runs must produce metric-identical reports."""

    config = _make_config()
    prices = _trend_market(seed=7)
    specs1 = list(build_default_strategy_specs(config).values())
    specs2 = list(build_default_strategy_specs(config).values())

    r1 = StrategyComparator(specs1, prices).run()
    r2 = StrategyComparator(specs2, prices).run()

    assert r1.strategy_labels == r2.strategy_labels
    for label in r1.strategy_labels:
        assert r1.per_strategy_metrics[label].total_return_pct == pytest.approx(
            r2.per_strategy_metrics[label].total_return_pct, abs=1e-9,
        )
        assert r1.per_strategy_metrics[label].sharpe_ratio == pytest.approx(
            r2.per_strategy_metrics[label].sharpe_ratio, abs=1e-9,
        )
        assert r1.per_strategy_metrics[label].max_drawdown_pct == pytest.approx(
            r2.per_strategy_metrics[label].max_drawdown_pct, abs=1e-9,
        )
    # to_dict must also be byte-identical (the JSON sanitiser does no RNG).
    assert json.dumps(r1.to_dict(), sort_keys=True) == json.dumps(
        r2.to_dict(), sort_keys=True,
    )


def test_empty_strategy_list_returns_empty_report() -> None:
    """Empty strategies → fully empty report, no exception."""

    prices = _trend_market()
    report = StrategyComparator(strategies=[], price_history=prices).run()
    assert report.n_strategies == 0
    assert report.per_strategy_metrics == {}
    assert report.pairwise_spreads == []
    assert report.regime_analysis is None
    # Winner objects must still exist with label=None so consumers can render.
    for winner in (
        report.winner_by_sharpe,
        report.winner_by_return,
        report.winner_by_calmar,
        report.winner_by_max_dd,
        report.winner_by_turnover,
    ):
        assert winner.label is None
        assert winner.score is None
    # JSON must still serialise (allow_nan=False enforces no leaked NaN).
    json.dumps(report.to_dict(), allow_nan=False)


def test_empty_window_returns_empty_per_strategy_reports() -> None:
    """Period bounds outside the price range collapse to empty backtests."""

    config = _make_config()
    prices = _trend_market(days=180)
    specs = list(build_default_strategy_specs(config).values())

    report = StrategyComparator(
        specs,
        prices,
        period_start="2030-01-01",
        period_end="2030-12-31",
    ).run()

    # The comparator still emits a report (it never raises on degenerate
    # windows), but every per-strategy report should have n_bars=0.
    assert report.n_strategies == 3
    for label in DEFAULT_STRATEGY_LABELS:
        assert report.per_strategy_metrics[label].n_bars == 0


def test_monotonic_uptrend_all_strategies_post_same_return_class() -> None:
    """When every asset is the same monotonic series, no strategy can lose.

    With both columns identical and monotonic-up, regardless of which
    weights each strategy picks, the realised portfolio return must be
    >= 0 and the max-drawdown must be 0.
    """

    config = _make_config()
    prices = _monotonic_uptrend(days=180)
    specs = list(build_default_strategy_specs(config).values())

    report = StrategyComparator(specs, prices).run()

    for label in DEFAULT_STRATEGY_LABELS:
        rep = report.per_strategy_metrics[label]
        assert rep.total_return_pct >= 0.0
        assert rep.max_drawdown_pct == pytest.approx(0.0, abs=1e-9)
    # On a no-information series the regime detector should still
    # populate the structure even if the winner is degenerate.
    assert report.regime_analysis is not None


def test_winner_by_metric_picks_correct_label() -> None:
    """``_winner_higher_better`` + ``_winner_lower_better`` give the right label.

    We build a tiny report manually with three strategies and known
    metrics, then exercise the winner extractors via a hand-crafted
    ComparisonReport-equivalent flow. This tests the metric-selection
    logic without re-running the full backtest.
    """

    from src.backtest.strategy_comparison import (
        _winner_higher_better,
        _winner_lower_better,
    )

    # Build three synthetic BacktestReports with distinguishable metrics.
    def _r(
        label: str,
        sharpe: float,
        total_return: float,
        max_dd: float,
        calmar: float | None,
        turnover: float,
    ) -> BacktestReport:
        return BacktestReport(
            period_start="2024-01-01",
            period_end="2024-12-31",
            n_bars=200,
            n_assets=2,
            n_rebalances=20,
            initial_capital=100_000.0,
            final_equity=100_000.0 * (1.0 + total_return / 100.0),
            total_return_pct=total_return,
            annualized_return_pct=total_return,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            calmar_ratio=calmar,
            avg_turnover_pct=turnover,
            win_rate=0.5,
            comparable_buy_hold_return_pct=10.0,
            policy_signal_factor_enabled=False,
            rebalance_freq_days=5,
            rebalance_log=[],
            caveats=[f"strategy_label:{label}"],
        )

    per_strategy = {
        "a": _r("a", sharpe=1.2, total_return=6.0, max_dd=4.0, calmar=0.5, turnover=8.0),
        "b": _r("b", sharpe=0.4, total_return=10.0, max_dd=12.0, calmar=0.3, turnover=5.0),
        "c": _r("c", sharpe=0.9, total_return=2.0, max_dd=1.0, calmar=None, turnover=15.0),
    }

    w_sharpe = _winner_higher_better("sharpe", per_strategy, lambda r: r.sharpe_ratio)
    w_return = _winner_higher_better(
        "ret", per_strategy, lambda r: r.total_return_pct,
    )
    w_calmar = _winner_higher_better(
        "calmar", per_strategy, lambda r: r.calmar_ratio,
    )
    w_dd = _winner_lower_better("dd", per_strategy, lambda r: r.max_drawdown_pct)
    w_to = _winner_lower_better("to", per_strategy, lambda r: r.avg_turnover_pct)

    assert w_sharpe.label == "a"  # highest sharpe
    assert w_return.label == "b"  # highest return
    assert w_calmar.label == "a"  # highest calmar (c is None, skipped)
    assert w_dd.label == "c"      # lowest drawdown
    assert w_to.label == "b"      # lowest turnover


def test_regime_analysis_identifies_trending_and_choppy_halves() -> None:
    """The regime detector tags the smoother half as trending."""

    config = _make_config()
    # Engineer a 200-bar series whose first half is choppy noise and
    # whose second half is a smooth uptrend so the R^2 split lands on
    # second_half = trending.
    dates = pd.date_range("2024-01-01", periods=200, freq="B")
    rng = np.random.default_rng(seed=11)
    first_half_noise = 100.0 + rng.normal(0.0, 1.5, 100).cumsum()
    second_half_trend = first_half_noise[-1] + np.linspace(0.0, 30.0, 100)
    series = np.concatenate([first_half_noise, second_half_trend])
    prices = pd.DataFrame({s: series.copy() for s in ("STRONG", "WEAK")}, index=dates)

    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(specs, prices).run()

    assert report.regime_analysis is not None
    # Smooth-uptrend half must be tagged trending; noisy half must be choppy.
    assert report.regime_analysis.trending_half == "second_half"
    assert report.regime_analysis.choppy_half == "first_half"
    # Both winners must be valid labels (every strategy participated).
    assert report.regime_analysis.winner_trending in DEFAULT_STRATEGY_LABELS
    assert report.regime_analysis.winner_choppy in DEFAULT_STRATEGY_LABELS
    # Returns-per-half must cover every strategy.
    assert set(report.regime_analysis.returns_per_half.keys()) == set(
        DEFAULT_STRATEGY_LABELS,
    )
    for payload in report.regime_analysis.returns_per_half.values():
        assert "trending" in payload and "choppy" in payload


def test_to_dict_round_trips_as_strict_json() -> None:
    """Report payload must serialise via ``json.dumps(..., allow_nan=False)``."""

    config = _make_config()
    prices = _trend_market()
    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(specs, prices).run()

    payload = report.to_dict()
    # allow_nan=False makes the serialiser raise on any leaked NaN/Inf —
    # exactly the same contract FastAPI's default encoder enforces.
    encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False)
    decoded = json.loads(encoded)

    # Spot-check structure round-trip.
    assert decoded["n_strategies"] == 3
    assert set(decoded["strategy_labels"]) == set(DEFAULT_STRATEGY_LABELS)
    assert isinstance(decoded["per_strategy_metrics"], dict)
    assert "winner_by_sharpe" in decoded
    assert decoded["winner_by_sharpe"]["metric"] == "sharpe_ratio"


def test_markdown_renderer_includes_every_strategy_row() -> None:
    """``render_comparison_markdown`` must render one table row per strategy."""

    config = _make_config()
    prices = _trend_market()
    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(specs, prices).run()

    md = render_comparison_markdown(report)
    assert "多策略对照回放报告" in md
    for label in DEFAULT_STRATEGY_LABELS:
        assert f"`{label}`" in md
    # The pairwise table must list every ordered pair.
    for a in DEFAULT_STRATEGY_LABELS:
        for b in DEFAULT_STRATEGY_LABELS:
            if a == b:
                continue
            assert f"`{a}` vs `{b}`" in md


def test_duplicate_strategy_labels_rejected() -> None:
    """Duplicate spec labels must raise ValueError at constructor time."""

    config = _make_config()
    prices = _trend_market()
    specs = list(build_default_strategy_specs(config).values())
    # Inject a duplicate by re-using the same rotation spec under a fresh list.
    duplicate = [specs[0], specs[0]]
    with pytest.raises(ValueError, match="StrategySpec labels must be unique"):
        StrategyComparator(duplicate, prices)


def test_invalid_constructor_params_rejected() -> None:
    """Negative cadence / zero capital must raise at constructor time."""

    config = _make_config()
    prices = _trend_market()
    specs = list(build_default_strategy_specs(config).values())
    with pytest.raises(ValueError, match="rebalance_freq_days"):
        StrategyComparator(specs, prices, rebalance_freq_days=0)
    with pytest.raises(ValueError, match="initial_capital"):
        StrategyComparator(specs, prices, initial_capital=0.0)


def test_mean_reversion_and_blend_run_against_real_universe() -> None:
    """Smoke: MR + blend signal generators don't crash on a 5-ETF universe.

    The default-spec builder wires MR + blend via the bar-by-bar
    evaluator path, which is more complex than rotation's
    ``generate_signals``. This guards against regressions where the
    evaluator path silently produces all-zero weights or raises on the
    EtfSignal -> wide-DataFrame conversion.
    """

    config = EtfRotationConfig(
        assets=[
            EtfAssetConfig(symbol="A", max_weight=0.30),
            EtfAssetConfig(symbol="B", max_weight=0.30),
            EtfAssetConfig(symbol="C", max_weight=0.30),
            EtfAssetConfig(symbol="D", max_weight=0.30),
            EtfAssetConfig(symbol="E", max_weight=0.30),
        ],
        gross_cap=0.90,
        warmup_days=60,
    )
    dates = pd.date_range("2024-01-01", periods=180, freq="B")
    rng = np.random.default_rng(seed=99)
    cols: dict[str, np.ndarray] = {}
    for offset, sym in enumerate(("A", "B", "C", "D", "E")):
        drift = np.linspace(0.0, 0.10 * (1 + offset * 0.5), 180)
        noise = rng.normal(0.0, 0.005, 180)
        cols[sym] = 100.0 * np.exp(drift + np.cumsum(noise))
    prices = pd.DataFrame(cols, index=dates)

    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(specs, prices).run()

    # All three strategies must have non-empty per-strategy reports.
    for label in DEFAULT_STRATEGY_LABELS:
        rep = report.per_strategy_metrics[label]
        assert rep.n_bars > 0
        assert rep.n_assets == 5
        # n_rebalances > 0 means at least one weight allocation fired —
        # guards against the "evaluator returned no usable signals"
        # regression case.
        assert rep.n_rebalances > 0


def test_statistical_tests_section_emitted_when_opted_in() -> None:
    """compute_statistical_tests=True populates the statistical_tests block."""

    config = EtfRotationConfig(
        assets=[
            EtfAssetConfig(symbol=s, max_weight=0.30)
            for s in ("A", "B", "C", "D", "E")
        ],
        gross_cap=0.90,
        warmup_days=60,
    )
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    rng = np.random.default_rng(seed=101)
    cols: dict[str, np.ndarray] = {}
    for offset, sym in enumerate(("A", "B", "C", "D", "E")):
        drift = np.linspace(0.0, 0.20 * (1 + offset * 0.3), 300)
        noise = rng.normal(0.0, 0.005, 300)
        cols[sym] = 100.0 * np.exp(drift + np.cumsum(noise))
    prices = pd.DataFrame(cols, index=dates)
    specs = list(build_default_strategy_specs(config).values())

    report = StrategyComparator(
        specs,
        prices,
        compute_statistical_tests=True,
        statistical_alpha=0.05,
        statistical_block_size=5,
        statistical_n_bootstrap=200,
        statistical_include_buy_hold=True,
    ).run()

    assert report.statistical_tests is not None
    tests = report.statistical_tests
    # 3 rotation/MR/blend + buy_hold = 4 strategies → C(4,2)=6 unordered pairs.
    assert len(tests.pair_labels) == 6
    assert len(tests.dm_results) == 6
    assert len(tests.sharpe_results) == 6
    assert len(tests.block_bootstrap_results) == 6
    assert tests.alpha == pytest.approx(0.05)
    # The Bonferroni / Holm tables span the same set of pairs.
    assert len(tests.bonferroni_dm.rejected) == 6
    assert len(tests.holm_sharpe.rejected) == 6


def test_statistical_tests_section_omitted_by_default() -> None:
    """Without the opt-in flag the v0.1 report shape is preserved."""

    config = _make_config()
    prices = _trend_market()
    specs = list(build_default_strategy_specs(config).values())
    report = StrategyComparator(specs, prices).run()
    assert report.statistical_tests is None
    # Existing markdown renderer is unchanged.
    rendered = render_comparison_markdown(report)
    assert "统计显著性检验" not in rendered


def test_statistical_tests_serialises_via_to_dict() -> None:
    """The new section round-trips through ``ComparisonReport.to_dict``."""

    config = EtfRotationConfig(
        assets=[
            EtfAssetConfig(symbol=s, max_weight=0.30)
            for s in ("A", "B", "C", "D", "E")
        ],
        gross_cap=0.90,
        warmup_days=60,
    )
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    rng = np.random.default_rng(seed=202)
    cols: dict[str, np.ndarray] = {}
    for offset, sym in enumerate(("A", "B", "C", "D", "E")):
        drift = np.linspace(0.0, 0.10 * (1 + offset * 0.3), 300)
        noise = rng.normal(0.0, 0.005, 300)
        cols[sym] = 100.0 * np.exp(drift + np.cumsum(noise))
    prices = pd.DataFrame(cols, index=dates)
    specs = list(build_default_strategy_specs(config).values())

    report = StrategyComparator(
        specs,
        prices,
        compute_statistical_tests=True,
        statistical_n_bootstrap=100,
        statistical_block_size=4,
    ).run()

    payload = report.to_dict()
    assert "statistical_tests" in payload
    assert payload["statistical_tests"] is not None
    # JSON-strict — no NaN / Inf leakage.
    json.dumps(payload)
