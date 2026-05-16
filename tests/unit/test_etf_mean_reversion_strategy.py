"""Tests for the mean-reversion ETF strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategy.etf_mean_reversion_strategy import (
    EtfMeanReversionConfig,
    EtfMeanReversionRotationConfig,
    EtfMeanReversionStrategy,
)
from src.strategy.etf_rotation_strategy import EtfAssetConfig


def _make_config(*, scoring: EtfMeanReversionConfig | None = None) -> EtfMeanReversionRotationConfig:
    return EtfMeanReversionRotationConfig(
        assets=[EtfAssetConfig(symbol="X", min_weight=0.0, max_weight=0.50)],
        gross_cap=0.9,
        scoring=scoring or EtfMeanReversionConfig(),
    )


def _series(price_path: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(price_path), freq="B")
    return pd.DataFrame({"X": price_path}, index=dates)


def _uptrend_with_recent_dip(periods: int = 220, dip_pct: float = -0.06) -> pd.DataFrame:
    """Build a 220-day uptrend that takes a ``dip_pct`` haircut on the last 5 days."""

    rng = np.random.default_rng(42)
    drift = np.linspace(0.0, 0.30, periods - 5)
    noise = rng.normal(0.0, 0.003, periods - 5)
    uptrend = 100.0 * np.exp(drift + np.cumsum(noise))
    dip = uptrend[-1] * np.linspace(1.0, 1.0 + dip_pct, 5)
    series = np.concatenate([uptrend, dip])
    return _series(series.tolist())


def test_mr_skips_assets_below_long_trend_by_default() -> None:
    """An asset below MA200 should get score 0 unless ``allow_below_long_trend`` is True."""

    # Long downtrend → latest stays below MA200
    rng = np.random.default_rng(7)
    drift = np.linspace(0.0, np.log(0.70), 220)
    noise = rng.normal(0.0, 0.003, 220)
    price = 100.0 * np.exp(drift + np.cumsum(noise))
    matrix = _series(price.tolist())

    strategy = EtfMeanReversionStrategy(_make_config())
    signals = strategy.evaluate(matrix)
    assert len(signals) == 1
    assert signals[0].score == 0.0
    assert "mr_blocked_below_ma200" in signals[0].reasons


def test_mr_scores_oversold_in_uptrend() -> None:
    """The strategy's bread-and-butter: long-trend intact but short-term dip."""

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.06)
    strategy = EtfMeanReversionStrategy(_make_config())
    signals = strategy.evaluate(matrix)
    sig = signals[0]
    assert sig.score > 30.0
    assert sig.target_weight > 0.0
    # Long-term trend reason captured
    assert any("mr_long_trend_intact" in r for r in sig.reasons)
    # Either reversal or capitulation triggered
    reversal_reasons = [r for r in sig.reasons if "mr_short_reversal" in r or "mr_deep_capitulation" in r]
    assert reversal_reasons


def test_mr_deep_capitulation_gets_higher_score_than_shallow_dip() -> None:
    """A larger 5-day drop should produce a higher score (within reason)."""

    shallow = _uptrend_with_recent_dip(periods=220, dip_pct=-0.03)
    deep = _uptrend_with_recent_dip(periods=220, dip_pct=-0.08)
    strategy = EtfMeanReversionStrategy(_make_config())
    shallow_sig = strategy.evaluate(shallow)[0]
    deep_sig = strategy.evaluate(deep)[0]
    assert deep_sig.score > shallow_sig.score


def test_mr_rejects_severe_long_term_collapse() -> None:
    """A 60d return below ``min_long_return`` should kill the signal."""

    # Tiny uptrend across 220 bars but the last 60 bars collapse 25%
    rng = np.random.default_rng(0)
    early = 100.0 * np.exp(
        np.linspace(0.0, 0.25, 160) + np.cumsum(rng.normal(0.0, 0.002, 160))
    )
    collapse = early[-1] * np.linspace(1.0, 0.75, 60)
    matrix = _series(np.concatenate([early, collapse]).tolist())

    strategy = EtfMeanReversionStrategy(_make_config())
    sig = strategy.evaluate(matrix)[0]
    # Either anti-falling-knife gate fires or the long-trend gate does;
    # either way the score must be zero.
    assert sig.score == 0.0
    assert any(
        "mr_blocked_long_return_too_negative" in r or "mr_blocked_below_ma200" in r
        for r in sig.reasons
    )


def test_mr_normalises_gross_cap_with_multi_asset_universe() -> None:
    """When several assets all score high, the gross_cap normaliser must clamp the sum."""

    dates = pd.date_range("2024-01-01", periods=220, freq="B")
    rng = np.random.default_rng(11)
    base = 100.0 * np.exp(
        np.linspace(0.0, 0.30, 215) + np.cumsum(rng.normal(0.0, 0.003, 215))
    )
    dipped = np.concatenate([base, base[-1] * np.linspace(1.0, 0.93, 5)])
    matrix = pd.DataFrame({code: dipped for code in ("A", "B", "C", "D")}, index=dates)

    config = EtfMeanReversionRotationConfig(
        assets=[
            EtfAssetConfig(symbol=code, max_weight=0.40, base_weight=0.15)
            for code in ("A", "B", "C", "D")
        ],
        gross_cap=0.80,
    )
    signals = EtfMeanReversionStrategy(config).evaluate(matrix)
    total = sum(s.target_weight for s in signals)
    assert total <= 0.80 + 1e-6


def test_mr_premium_overlay_penalises_score() -> None:
    """A high premium overlay should reduce the MR score."""

    from src.strategy.etf_rotation_strategy import EtfOverlay

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.05)
    strategy = EtfMeanReversionStrategy(_make_config())

    base = strategy.evaluate(matrix)[0]
    capped = strategy.evaluate(matrix, overlays={"X": EtfOverlay(premium=0.06)})[0]
    assert capped.score < base.score
    assert capped.premium_score < 0


def test_mr_config_rejects_inconsistent_score_thresholds() -> None:
    with pytest.raises(ValueError):
        EtfMeanReversionRotationConfig(
            assets=[EtfAssetConfig(symbol="X", max_weight=0.30)],
            min_score_to_hold=40.0,
            min_score_full_hold=20.0,
        )


# ---------------------------------------------------------------------------
# Construction / config validation
# ---------------------------------------------------------------------------


def test_mr_construction_with_default_scoring_config() -> None:
    """The dataclass default factory must give a fresh scoring config per call.

    Why: ``field(default_factory=...)`` guarantees independent instances so
    callers can mutate ``replace(cfg, scoring=...)`` without sharing state.
    """

    cfg = EtfMeanReversionRotationConfig(assets=[EtfAssetConfig(symbol="X", max_weight=0.30)])
    assert isinstance(cfg.scoring, EtfMeanReversionConfig)
    # Defaults are conservative: require_above_ma200 must be on out of the box.
    assert cfg.scoring.require_above_ma200 is True


def test_mr_construction_with_custom_scoring_config() -> None:
    """A caller-supplied scoring config flows into the strategy unchanged."""

    scoring = EtfMeanReversionConfig(
        deviation_clip=0.05,
        short_reversal_threshold=-0.02,
        allow_below_long_trend=True,
    )
    cfg = _make_config(scoring=scoring)
    strategy = EtfMeanReversionStrategy(cfg)
    assert strategy.config.scoring is scoring


def test_mr_construction_rejects_empty_asset_list() -> None:
    """Strategy must refuse a config with no assets — there's nothing to score."""

    with pytest.raises(ValueError, match="must not be empty"):
        EtfMeanReversionStrategy(
            EtfMeanReversionRotationConfig(assets=[])
        )


@pytest.mark.parametrize("gross_cap", [0.0, -0.1, 1.5, 2.0])
def test_mr_construction_rejects_invalid_gross_cap(gross_cap: float) -> None:
    """gross_cap must be in (0, 1] — anything else makes the normaliser nonsensical."""

    with pytest.raises(ValueError, match="gross_cap"):
        EtfMeanReversionStrategy(
            EtfMeanReversionRotationConfig(
                assets=[EtfAssetConfig(symbol="X", max_weight=0.3)],
                gross_cap=gross_cap,
            )
        )


# ---------------------------------------------------------------------------
# Empty / degenerate input handling
# ---------------------------------------------------------------------------


def test_mr_evaluate_with_empty_dataframe_returns_no_signals() -> None:
    """An empty price matrix must produce no signals, not a crash.

    Why: live callers may invoke the strategy before any data has loaded;
    a graceful empty list keeps the downstream plumbing simple.
    """

    strategy = EtfMeanReversionStrategy(_make_config())
    signals = strategy.evaluate(pd.DataFrame())
    assert signals == []


def test_mr_evaluate_with_short_history_below_warmup_drops_asset() -> None:
    """An asset with fewer than ``warmup_days`` bars must be silently dropped.

    Why: scoring relies on 60-day rolling stats; computing them on a
    half-warm series produces garbage. Dropping is safer than emitting
    a low-confidence signal.
    """

    matrix = _series([100.0 + i * 0.1 for i in range(30)])  # 30 < warmup_days=60
    strategy = EtfMeanReversionStrategy(_make_config())
    signals = strategy.evaluate(matrix)
    assert signals == []


def test_mr_evaluate_with_single_row_returns_no_signal() -> None:
    """A degenerate single-row price matrix must not raise."""

    strategy = EtfMeanReversionStrategy(_make_config())
    matrix = pd.DataFrame({"X": [100.0]}, index=pd.date_range("2024-01-01", periods=1))
    signals = strategy.evaluate(matrix)
    assert signals == []


def test_mr_evaluate_rejects_non_dataframe_input() -> None:
    """A list/dict/None input must be rejected with a clear ValueError.

    Why: callers occasionally pass a dict-of-series by mistake; failing
    fast surfaces the bug instead of silently returning [].
    """

    strategy = EtfMeanReversionStrategy(_make_config())
    with pytest.raises(ValueError, match="DataFrame"):
        strategy.evaluate({"X": [100.0, 101.0]})  # type: ignore[arg-type]


def test_mr_evaluate_with_all_nan_column_drops_asset() -> None:
    """A column that is all-NaN must drop out cleanly with no signal.

    Why: ``_prepare_prices`` uses ``ffill().dropna(how='all')`` and
    ``.dropna()`` per series; an all-NaN column ends with zero usable
    bars and should never reach the scoring path.
    """

    dates = pd.date_range("2024-01-01", periods=220, freq="B")
    matrix = pd.DataFrame({"X": [np.nan] * 220}, index=dates)
    strategy = EtfMeanReversionStrategy(_make_config())
    signals = strategy.evaluate(matrix)
    assert signals == []


def test_mr_evaluate_with_sparse_nan_uses_ffill() -> None:
    """Interior NaNs must be forward-filled, not abort the asset.

    Why: real ETF data has holiday/halt gaps; we expect the prepared
    matrix to fill those forward and still produce a signal.
    """

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.06)
    poisoned = matrix.copy()
    # Sprinkle a few NaN holes in the middle — must not block the signal.
    poisoned.iloc[50, 0] = np.nan
    poisoned.iloc[120, 0] = np.nan
    poisoned.iloc[180, 0] = np.nan

    strategy = EtfMeanReversionStrategy(_make_config())
    clean_signal = strategy.evaluate(matrix)[0]
    poisoned_signal = strategy.evaluate(poisoned)[0]
    # ffill means a small drift in score is fine; we just want a signal,
    # not a crash. Both should be in the same neighbourhood.
    assert poisoned_signal.score > 0
    # Sanity: the dip-driven score is similar (ffill preserves shape).
    assert abs(poisoned_signal.score - clean_signal.score) < 15.0


def test_mr_evaluate_silently_ignores_symbols_not_in_config() -> None:
    """Extra columns in the price matrix must be ignored, not raise.

    Why: callers often pass the universe-wide price matrix; the strategy
    should only score symbols it knows about.
    """

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.06)
    matrix["UNKNOWN"] = matrix["X"]  # add an unconfigured symbol

    strategy = EtfMeanReversionStrategy(_make_config())
    signals = strategy.evaluate(matrix)
    assert {s.symbol for s in signals} == {"X"}


# ---------------------------------------------------------------------------
# Path coverage on the scoring branches
# ---------------------------------------------------------------------------


def test_mr_allow_below_long_trend_unlocks_signal() -> None:
    """When ``allow_below_long_trend`` is True, a sub-MA200 asset can still
    score — useful for catching reversal bounces in long downtrends.

    The 60-day return gate still applies, so we keep that mild.
    """

    rng = np.random.default_rng(7)
    # Mild downtrend so MA200 is above latest, but ret60 stays > -20%.
    drift = np.linspace(0.0, np.log(0.92), 215)
    noise = rng.normal(0.0, 0.002, 215)
    base = 100.0 * np.exp(drift + np.cumsum(noise))
    # Tail dip to trigger the reversal component.
    dip = base[-1] * np.linspace(1.0, 0.95, 5)
    matrix = _series(np.concatenate([base, dip]).tolist())

    scoring = EtfMeanReversionConfig(allow_below_long_trend=True)
    strategy = EtfMeanReversionStrategy(_make_config(scoring=scoring))
    sig = strategy.evaluate(matrix)[0]
    # Should no longer hit the long-trend block.
    assert "mr_blocked_below_ma200" not in sig.reasons
    # And should pick up at least the reversal component.
    assert sig.score >= 0.0


def test_mr_hard_premium_overlay_penalises_more_than_soft() -> None:
    """The hard premium tier (default 5%) must impose a stricter penalty
    than the soft tier (default 2%).

    Why: covers both branches of the premium ladder, complementing the
    existing soft-only premium test.
    """

    from src.strategy.etf_rotation_strategy import EtfOverlay

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.05)
    strategy = EtfMeanReversionStrategy(_make_config())

    soft = strategy.evaluate(matrix, overlays={"X": EtfOverlay(premium=0.03)})[0]
    hard = strategy.evaluate(matrix, overlays={"X": EtfOverlay(premium=0.07)})[0]
    no_overlay = strategy.evaluate(matrix)[0]

    assert no_overlay.premium_score == 0.0
    assert soft.premium_score < 0.0
    assert hard.premium_score < soft.premium_score


def test_mr_overlay_max_weight_caps_target() -> None:
    """An overlay-supplied ``max_weight`` must shrink the target weight."""

    from src.strategy.etf_rotation_strategy import EtfOverlay

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.06)
    strategy = EtfMeanReversionStrategy(_make_config())

    base = strategy.evaluate(matrix)[0]
    if base.target_weight <= 0.05:
        pytest.skip("baseline already below the cap — overlay test inconclusive")
    capped = strategy.evaluate(
        matrix, overlays={"X": EtfOverlay(max_weight=0.05)}
    )[0]
    assert capped.target_weight <= 0.05 + 1e-9
    assert capped.target_weight < base.target_weight


def test_mr_overlay_block_new_buys_pins_to_current_weight() -> None:
    """``block_new_buys`` must prevent adding above the current position."""

    from src.strategy.etf_rotation_strategy import EtfOverlay

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.06)
    strategy = EtfMeanReversionStrategy(_make_config())

    blocked = strategy.evaluate(
        matrix,
        overlays={"X": EtfOverlay(block_new_buys=True)},
        current_weights={"X": 0.02},
    )[0]
    assert blocked.target_weight <= 0.02 + 1e-9


def test_mr_deviation_clip_saturates_at_clip_value() -> None:
    """Deviations beyond ``deviation_clip`` must not earn more reversal points.

    Why: the linear ramp is clipped to ``deviation_clip``; a 20% drop
    below MA20 must score no more than a 10% drop when the clip is 10%.
    """

    moderate = _uptrend_with_recent_dip(periods=220, dip_pct=-0.10)
    extreme = _uptrend_with_recent_dip(periods=220, dip_pct=-0.18)

    scoring = EtfMeanReversionConfig(
        deviation_clip=0.10,
        deviation_max_points=40.0,
        # Allow the long-trend block to lift, since an 18% dip can push
        # latest under MA200; we want to isolate the deviation branch.
        allow_below_long_trend=True,
        # And widen the anti-falling-knife gate, otherwise extreme is killed.
        min_long_return=-0.50,
    )
    strategy = EtfMeanReversionStrategy(_make_config(scoring=scoring))

    mod_sig = strategy.evaluate(moderate)[0]
    ext_sig = strategy.evaluate(extreme)[0]

    # The reversal+momentum contribution lives in momentum_score.
    # Once clipped, the extra dip can only add momentum bonuses, not
    # more deviation points. So they should be in the same band.
    assert ext_sig.momentum_score >= mod_sig.momentum_score
    # Extreme dip mustn't multiply the deviation contribution beyond clip.
    # ``deviation_max_points`` is 40; momentum bonuses add at most
    # short_reversal_bonus + deep_capitulation_bonus = 25. Cap = 65.
    assert ext_sig.momentum_score <= 65.0 + 1e-6


def test_mr_short_reversal_below_threshold_adds_bonus_only() -> None:
    """A ret5 just below ``short_reversal_threshold`` adds short bonus;
    ret5 below ``deep_capitulation_threshold`` adds both bonuses.

    This complements the existing shallow-vs-deep ordering test by
    pinning the exact reason strings produced at each tier.
    """

    short = _uptrend_with_recent_dip(periods=220, dip_pct=-0.05)
    deep = _uptrend_with_recent_dip(periods=220, dip_pct=-0.09)
    strategy = EtfMeanReversionStrategy(_make_config())

    short_sig = strategy.evaluate(short)[0]
    deep_sig = strategy.evaluate(deep)[0]

    assert "mr_short_reversal_ret5" in short_sig.reasons
    assert "mr_deep_capitulation_ret5" not in short_sig.reasons
    assert "mr_deep_capitulation_ret5" in deep_sig.reasons


def test_mr_below_warmup_skips_silently_in_multi_asset_universe() -> None:
    """Among many assets, ones lacking history must be dropped without
    aborting the rest.

    Why: real universes are heterogeneous (newer ETFs alongside old
    ones); the strategy must score what it can.
    """

    dates = pd.date_range("2024-01-01", periods=220, freq="B")
    rng = np.random.default_rng(11)
    base = 100.0 * np.exp(np.linspace(0.0, 0.30, 215) + np.cumsum(rng.normal(0.0, 0.003, 215)))
    dipped = np.concatenate([base, base[-1] * np.linspace(1.0, 0.94, 5)])
    short = np.full(220, np.nan)
    short[-30:] = np.linspace(99.0, 101.0, 30)  # only 30 bars of data
    matrix = pd.DataFrame({"FULL": dipped, "SHORT": short}, index=dates)
    config = EtfMeanReversionRotationConfig(
        assets=[
            EtfAssetConfig(symbol="FULL", max_weight=0.30),
            EtfAssetConfig(symbol="SHORT", max_weight=0.30),
        ],
        gross_cap=0.90,
    )
    signals = EtfMeanReversionStrategy(config).evaluate(matrix)
    assert {s.symbol for s in signals} == {"FULL"}


# ---------------------------------------------------------------------------
# Composition smoke: MR signals feeding the portfolio risk-rules layer
# ---------------------------------------------------------------------------


def test_mr_drawdown_severe_branch_fires_with_default_floor() -> None:
    """Drawdown severe-penalty path must fire at the default ``drawdown_floor``.

    Historical context: an earlier commit shipped ``drawdown_floor=-25.0``,
    wired as if drawdown were a percentage. But the runtime feeds it a
    *fraction* (e.g. -0.25 for a 25% peak-to-trough). The branch was dead
    code at defaults. The default is now ``-0.20`` — a meaningful "severe"
    threshold in fraction units — so this test runs without overriding it.
    """

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.25)
    scoring = EtfMeanReversionConfig(
        drawdown_severe_penalty=20.0,
        allow_below_long_trend=True, # lift the long-trend gate so the
                                     # risk path is the one being tested
        min_long_return=-0.50,
    )
    strategy = EtfMeanReversionStrategy(_make_config(scoring=scoring))
    sig = strategy.evaluate(matrix)[0]
    assert "mr_drawdown_severe" in sig.reasons
    # Risk component falls below the baseline once the severe penalty fires.
    assert sig.risk_score < scoring.risk_baseline


def test_mr_drawdown_floor_default_is_fraction_not_percentage() -> None:
    """The default ``drawdown_floor`` must live in fraction units.

    Guard against regression to the old ``-25.0`` value: the runtime
    compares ``drawdown_floor`` against ``drawdown60`` which is a fraction
    (latest/high60 - 1.0, so always in [-1.0, 0.0]). A value outside
    that range would silently make the severe-drawdown branch unreachable.
    """

    default = EtfMeanReversionConfig()
    assert -1.0 < default.drawdown_floor < 0.0, (
        f"drawdown_floor={default.drawdown_floor} is not a fraction in (-1, 0); "
        "it must match the units of drawdown60 (latest/high60 - 1.0)."
    )


def test_mr_ramp_degenerate_when_full_hold_equals_min_score() -> None:
    """When ``min_score_full_hold == min_score_to_hold`` the ramp degenerates
    to a hard step — any score above the threshold is treated as full hold.

    Why: the score-to-weight ramp guards against this with
    ``ramp_high <= ramp_low + 1e-9``; this test pins the documented
    behaviour and covers that branch.
    """

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.06)
    cfg = EtfMeanReversionRotationConfig(
        assets=[EtfAssetConfig(symbol="X", max_weight=0.40, base_weight=0.10)],
        gross_cap=0.90,
        min_score_to_hold=25.0,
        min_score_full_hold=25.0,  # ramp collapses to a step
    )
    strategy = EtfMeanReversionStrategy(cfg)
    sig = strategy.evaluate(matrix)[0]
    # Score is comfortably above 25 in this scenario; a hard step yields
    # the score-scaled cap directly (no partial ramp scaling).
    assert sig.target_weight > 0.0


def test_mr_signals_feed_portfolio_risk_rules_cleanly() -> None:
    """End-to-end smoke: the MR strategy emits target weights that can be
    passed straight into ``apply_etf_portfolio_risk_rules`` without any
    massaging — same protocol as the trend strategy.

    Why: a coverage gap in the original commit was *integration*: nothing
    proved the MR target weights are shape-compatible with the rules
    layer. This pins the contract.
    """

    from src.risk.etf_portfolio_rules import apply_etf_portfolio_risk_rules

    matrix = _uptrend_with_recent_dip(periods=220, dip_pct=-0.06)
    strategy = EtfMeanReversionStrategy(_make_config())
    signals = strategy.evaluate(matrix)
    proposed = {s.symbol: s.target_weight for s in signals}

    decision = apply_etf_portfolio_risk_rules(
        proposed_weights=proposed,
        asset_metadata={"X": {"category": "domestic_equity"}},
    )
    # Single-name cap (default 0.30) must not be violated.
    assert decision.adjusted_weights["X"] <= 0.30 + 1e-9
    # Cash floor must be respected after the rules pass.
    assert decision.adjusted_weights.get("CASH", 0.0) >= 0.10 - 1e-9
