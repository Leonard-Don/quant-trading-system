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
    weights = strategy.generate_signals(prices)

    assert weights.index.equals(prices.index)
    assert list(weights.columns) == list(prices.columns)
    # Pre-warmup rows must be zero (no NaNs reaching the executor).
    early = weights.iloc[:60]
    assert (early.fillna(0.0).to_numpy() == 0.0).all()
    # Cash is implicit: weights can sum to less than 1.
    assert weights.sum(axis=1).max() <= 1.0 + 1e-9
