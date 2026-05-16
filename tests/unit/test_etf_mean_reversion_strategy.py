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
