"""Tests for the core ETF rotation scoring strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategy.etf_rotation_strategy import (
    EtfAssetConfig,
    EtfOverlay,
    EtfRotationConfig,
    EtfRotationStrategy,
    EtfScoringConfig,
    EtfSignal,
)


def _make_price_matrix() -> pd.DataFrame:
    """Build a 120-day price matrix with one strong uptrend and one weak downtrend asset."""
    dates = pd.date_range("2025-01-01", periods=120, freq="B")
    rng = np.random.default_rng(seed=42)

    # Strong asset: steady uptrend with small noise
    strong_drift = np.linspace(0.0, 0.40, len(dates))
    strong_noise = rng.normal(0.0, 0.003, len(dates))
    strong = 100.0 * np.exp(strong_drift + np.cumsum(strong_noise))

    # Weak asset: steady downtrend with small noise
    weak_drift = np.linspace(0.0, -0.25, len(dates))
    weak_noise = rng.normal(0.0, 0.003, len(dates))
    weak = 100.0 * np.exp(weak_drift + np.cumsum(weak_noise))

    # Premium specialist asset: also uptrend but not as strong
    premium_drift = np.linspace(0.0, 0.15, len(dates))
    premium_noise = rng.normal(0.0, 0.003, len(dates))
    premium = 100.0 * np.exp(premium_drift + np.cumsum(premium_noise))

    return pd.DataFrame(
        {"STRONG": strong, "WEAK": weak, "512400": premium},
        index=dates,
    )


def _make_config(*, max_weight_512400: float = 0.4) -> EtfRotationConfig:
    return EtfRotationConfig(
        assets=[
            EtfAssetConfig(symbol="STRONG", min_weight=0.0, max_weight=0.5),
            EtfAssetConfig(symbol="WEAK", min_weight=0.0, max_weight=0.5),
            EtfAssetConfig(symbol="512400", min_weight=0.0, max_weight=max_weight_512400),
        ],
        gross_cap=0.9,
    )


def test_strong_asset_receives_higher_target_than_weak_asset():
    prices = _make_price_matrix()
    strategy = EtfRotationStrategy(_make_config())

    weights = strategy.generate_signals(prices)

    assert isinstance(weights, pd.DataFrame)
    assert list(weights.columns) == list(prices.columns)
    assert weights.index.equals(prices.index)

    last = weights.iloc[-1]
    assert last["STRONG"] > last["WEAK"]
    # Weak asset is below MA60: should be zeroed out
    assert last["WEAK"] == pytest.approx(0.0, abs=1e-9)


def test_overlay_max_weight_caps_512400_target():
    prices = _make_price_matrix()
    config = _make_config(max_weight_512400=0.5)
    strategy = EtfRotationStrategy(config)

    baseline = strategy.generate_signals(prices)
    baseline_premium = baseline.iloc[-1]["512400"]
    # Sanity: without overlay, premium asset should have some allocation.
    assert baseline_premium > 0.05

    capped = strategy.generate_signals(
        prices,
        overlays={"512400": EtfOverlay(max_weight=0.05, reason="premium too rich")},
    )
    final_premium = capped.iloc[-1]["512400"]
    assert final_premium <= 0.05 + 1e-9
    assert final_premium < baseline_premium


def test_block_new_buys_prevents_increase_above_current_weight():
    prices = _make_price_matrix()
    strategy = EtfRotationStrategy(_make_config())

    current_weights = {"512400": 0.02, "STRONG": 0.0, "WEAK": 0.0}
    blocked = strategy.generate_signals(
        prices,
        overlays={"512400": EtfOverlay(block_new_buys=True, reason="no new buys")},
        current_weights=current_weights,
    )
    last = blocked.iloc[-1]
    assert last["512400"] <= current_weights["512400"] + 1e-9


def test_gross_etf_weights_do_not_exceed_gross_cap():
    dates = pd.date_range("2025-01-01", periods=120, freq="B")
    rng = np.random.default_rng(seed=7)
    # Make every asset trend up so they all get max scores and push against the cap.
    prices = pd.DataFrame(
        {
            sym: 100.0
            * np.exp(np.linspace(0.0, 0.5, len(dates)) + np.cumsum(rng.normal(0.0, 0.002, len(dates))))
            for sym in ["A", "B", "C", "D"]
        },
        index=dates,
    )
    config = EtfRotationConfig(
        assets=[
            EtfAssetConfig(symbol="A", min_weight=0.0, max_weight=0.4),
            EtfAssetConfig(symbol="B", min_weight=0.0, max_weight=0.4),
            EtfAssetConfig(symbol="C", min_weight=0.0, max_weight=0.4),
            EtfAssetConfig(symbol="D", min_weight=0.0, max_weight=0.4),
        ],
        gross_cap=0.8,
    )
    strategy = EtfRotationStrategy(config)
    weights = strategy.generate_signals(prices)

    gross = weights.sum(axis=1)
    assert (gross <= 0.8 + 1e-9).all()
    # The cap should actually bind on at least the last day.
    assert gross.iloc[-1] == pytest.approx(0.8, abs=1e-6)


def test_signal_dataclass_records_score_breakdown():
    prices = _make_price_matrix()
    strategy = EtfRotationStrategy(_make_config())

    signals = strategy.evaluate(prices)
    assert {sig.symbol for sig in signals} == {"STRONG", "WEAK", "512400"}
    by_symbol = {sig.symbol: sig for sig in signals}

    strong_sig = by_symbol["STRONG"]
    weak_sig = by_symbol["WEAK"]
    assert isinstance(strong_sig, EtfSignal)
    assert strong_sig.score > weak_sig.score
    assert 0.0 <= strong_sig.target_weight <= 0.5
    assert weak_sig.target_weight == pytest.approx(0.0, abs=1e-9)
    # Trend component should be positive for strong, non-positive for weak.
    assert strong_sig.trend_score > 0.0
    assert weak_sig.trend_score <= 0.0


def test_generate_signals_matches_price_matrix_index_and_columns_for_backtester():
    prices = _make_price_matrix()
    strategy = EtfRotationStrategy(_make_config())
    weights = strategy.generate_signals(prices, lag_days=0)

    assert weights.index.equals(prices.index)
    assert list(weights.columns) == list(prices.columns)
    # Pre-warmup rows must be zero (no NaNs reaching the executor).
    early = weights.iloc[:60]
    assert (early.fillna(0.0).to_numpy() == 0.0).all()
    # Cash is implicit: weights can sum to less than 1.
    assert weights.sum(axis=1).max() <= 1.0 + 1e-9


def test_generate_signals_lag_days_one_shifts_weights_forward_to_avoid_lookahead():
    """Default ``lag_days=1`` must apply day-t signal at day-t+1."""

    prices = _make_price_matrix()
    strategy = EtfRotationStrategy(_make_config())

    same_day = strategy.generate_signals(prices, lag_days=0)
    lagged = strategy.generate_signals(prices)  # default lag_days=1

    # Day-1 lagged weights equal day-0 same-day weights.
    assert lagged.iloc[60].equals(same_day.iloc[59])
    # First row of the lagged frame is zero (no signal yet from prior day).
    assert (lagged.iloc[0].to_numpy() == 0.0).all()
    # Same gross-cap invariant still holds after the shift.
    assert lagged.sum(axis=1).max() <= 1.0 + 1e-9


def test_generate_signals_rejects_negative_lag():
    prices = _make_price_matrix()
    strategy = EtfRotationStrategy(_make_config())
    with pytest.raises(ValueError):
        strategy.generate_signals(prices, lag_days=-1)


def test_score_to_weight_ramps_smoothly_around_min_score_to_hold():
    """A score just above min_score_to_hold yields a small (not jump) weight."""

    config = EtfRotationConfig(
        assets=[EtfAssetConfig(symbol="X", min_weight=0.0, max_weight=0.30, base_weight=0.05)],
        gross_cap=0.9,
        min_score_to_hold=25.0,
        min_score_full_hold=35.0,
    )
    strategy = EtfRotationStrategy(config)
    asset = config.assets[0]

    below = strategy._score_to_weight(asset, score=24.0, latest=1.0, ma60=0.9, volatility60=0.15)
    just_above = strategy._score_to_weight(asset, score=26.0, latest=1.0, ma60=0.9, volatility60=0.15)
    midpoint = strategy._score_to_weight(asset, score=30.0, latest=1.0, ma60=0.9, volatility60=0.15)
    full = strategy._score_to_weight(asset, score=40.0, latest=1.0, ma60=0.9, volatility60=0.15)

    assert below == 0.0
    assert 0.0 < just_above < midpoint < full
    # The full-hold plateau should be at the score-scaled cap, not 0.
    assert full > 0.05


def test_vol_targeting_caps_weight_when_enabled_and_vol_high():
    config_off = EtfRotationConfig(
        assets=[EtfAssetConfig(symbol="X", min_weight=0.0, max_weight=0.30)],
        gross_cap=0.9,
        enable_vol_targeting=False,
    )
    config_on = EtfRotationConfig(
        assets=[EtfAssetConfig(symbol="X", min_weight=0.0, max_weight=0.30)],
        gross_cap=0.9,
        enable_vol_targeting=True,
        annualized_vol_target=0.20,
    )
    asset = config_off.assets[0]

    # High volatility → vol-targeting cap dominates.
    high_vol = 0.40
    off = EtfRotationStrategy(config_off)._score_to_weight(
        asset, score=80.0, latest=1.0, ma60=0.9, volatility60=high_vol
    )
    on = EtfRotationStrategy(config_on)._score_to_weight(
        asset, score=80.0, latest=1.0, ma60=0.9, volatility60=high_vol
    )
    # 0.20 / 0.40 = 0.5 → vol_cap = 0.15 (≤ 0.30) — must bind below the off case.
    assert on < off
    assert on <= 0.15 + 1e-9


def test_config_rejects_full_hold_below_min_score():
    with pytest.raises(ValueError):
        EtfRotationConfig(
            assets=[EtfAssetConfig(symbol="X", min_weight=0.0, max_weight=0.30)],
            min_score_to_hold=30.0,
            min_score_full_hold=20.0,
        )


def test_scoring_config_zero_trend_points_produces_lower_strong_score():
    """Disabling the trend ladder must noticeably reduce the strong asset's score."""

    prices = _make_price_matrix()
    base = _make_config()
    zero_trend = EtfRotationConfig(
        assets=base.assets,
        gross_cap=base.gross_cap,
        scoring=EtfScoringConfig(
            trend_above_ma20_points=0.0,
            trend_above_ma60_points=0.0,
            trend_ma20_above_ma60_points=0.0,
            trend_ma20_below_ma60_penalty=0.0,
        ),
    )

    base_signals = {s.symbol: s for s in EtfRotationStrategy(base).evaluate(prices)}
    flat_signals = {s.symbol: s for s in EtfRotationStrategy(zero_trend).evaluate(prices)}

    assert flat_signals["STRONG"].trend_score == 0.0
    assert flat_signals["STRONG"].score < base_signals["STRONG"].score


def test_cross_sectional_scoring_picks_strongest_when_universe_is_mixed():
    """In cross_sectional mode, the strongest asset gets a higher weight
    than the weak one even if absolute thresholds wouldn't have separated them."""

    prices = _make_price_matrix()
    base_config = _make_config()
    cs_config = EtfRotationConfig(
        assets=base_config.assets,
        gross_cap=base_config.gross_cap,
        scoring_mode="cross_sectional",
    )

    abs_signals = {s.symbol: s for s in EtfRotationStrategy(base_config).evaluate(prices)}
    cs_signals = {s.symbol: s for s in EtfRotationStrategy(cs_config).evaluate(prices)}

    # Both modes must still rank STRONG above WEAK and 512400.
    assert cs_signals["STRONG"].score > cs_signals["WEAK"].score
    assert cs_signals["STRONG"].target_weight > cs_signals["WEAK"].target_weight
    # Cross-sectional rebuilds the score — must differ from absolute output.
    assert cs_signals["STRONG"].score != abs_signals["STRONG"].score


def test_cross_sectional_scoring_falls_back_when_only_one_asset():
    """A universe with a single eligible asset can't be standardised; the
    cross-sectional path must leave the single signal untouched."""

    dates = pd.date_range("2025-01-01", periods=120, freq="B")
    rng = np.random.default_rng(seed=99)
    prices = pd.DataFrame(
        {"ONLY": 100.0 * np.exp(np.linspace(0, 0.30, len(dates)) + np.cumsum(rng.normal(0, 0.003, len(dates))))},
        index=dates,
    )
    config = EtfRotationConfig(
        assets=[EtfAssetConfig(symbol="ONLY", min_weight=0.0, max_weight=0.50)],
        gross_cap=0.90,
        scoring_mode="cross_sectional",
    )
    signals = EtfRotationStrategy(config).evaluate(prices)
    assert len(signals) == 1
    # Should still produce a non-zero target (asset is trending up strongly).
    assert signals[0].target_weight > 0.0


def test_invalid_scoring_mode_raises():
    with pytest.raises(ValueError):
        EtfRotationConfig(
            assets=[EtfAssetConfig(symbol="X", min_weight=0.0, max_weight=0.30)],
            scoring_mode="not_a_mode",
        )


def test_scoring_config_premium_threshold_alters_penalty():
    """A lower hard-premium threshold must fire the penalty on milder overlays."""

    prices = _make_price_matrix()
    base_config = _make_config()
    aggressive = EtfRotationConfig(
        assets=base_config.assets,
        gross_cap=base_config.gross_cap,
        scoring=EtfScoringConfig(
            premium_hard_threshold=0.02,
            premium_hard_penalty=-40.0,
            premium_soft_threshold=0.01,
        ),
    )

    overlays = {"512400": EtfOverlay(premium=0.03)}
    default = {s.symbol: s for s in EtfRotationStrategy(base_config).evaluate(prices, overlays=overlays)}
    tight = {s.symbol: s for s in EtfRotationStrategy(aggressive).evaluate(prices, overlays=overlays)}

    assert tight["512400"].premium_score < default["512400"].premium_score
    assert tight["512400"].score < default["512400"].score
