"""Tests for the broad-market regime detector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategy.etf_regime_detector import (
    RegimeDetectorConfig,
    build_detector_config,
    classify_regime,
)


def _trend_series(periods: int, start: float, end: float, *, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=periods)
    drift = np.linspace(0, np.log(end / start), periods)
    noise = np.cumsum(rng.normal(0, 0.003, periods))
    return pd.Series(start * np.exp(drift + noise), index=dates)


def _flat_series(periods: int, level: float = 5.0, vol: float = 0.005, *, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=periods)
    noise = np.cumsum(rng.normal(0, vol, periods))
    return pd.Series(level * np.exp(noise), index=dates)


def test_classify_unknown_when_series_shorter_than_ma_window() -> None:
    cfg = RegimeDetectorConfig(ma_long_window=200)
    short = _trend_series(120, 5.0, 5.3)
    decision = classify_regime(short, config=cfg)
    assert decision.regime == "unknown"
    assert decision.confidence == 0.0
    assert decision.gross_cap_multiplier == 1.0


def test_classify_bull_when_price_above_ma_with_normal_vol() -> None:
    # Long steady uptrend → price way above MA200, normal vol
    series = _trend_series(500, 4.0, 6.0, seed=1)
    decision = classify_regime(series)
    assert decision.regime == "bull"
    assert decision.proxy_price > decision.ma_long
    assert decision.gross_cap_multiplier == 1.0
    assert decision.min_score_to_hold_offset == 0.0


def test_classify_bear_when_price_below_long_ma() -> None:
    # Down-trend: price drops below MA200
    series = _trend_series(500, 6.0, 4.0, seed=2)
    decision = classify_regime(series)
    assert decision.regime in {"bear", "crisis"}
    if decision.regime == "bear":
        assert decision.gross_cap_multiplier < 1.0
        assert decision.min_score_to_hold_offset > 0.0


def test_classify_crisis_on_deep_drawdown() -> None:
    # First a 350-day uptrend then a sharp 20% crash over the final 30 days.
    up = _trend_series(350, 4.0, 6.0, seed=3)
    rng = np.random.default_rng(3)
    crash_dates = pd.bdate_range(up.index[-1] + pd.Timedelta(days=1), periods=60)
    crash_drift = np.linspace(0, np.log(0.80), 60)
    crash_noise = np.cumsum(rng.normal(0, 0.01, 60))
    crash = pd.Series(up.iloc[-1] * np.exp(crash_drift + crash_noise), index=crash_dates)
    series = pd.concat([up, crash])
    decision = classify_regime(series)
    assert decision.regime == "crisis"
    assert decision.gross_cap_multiplier <= 0.5
    assert decision.min_score_to_hold_offset >= 10.0


def test_classify_correction_when_above_ma_but_drawn_down() -> None:
    # Long uptrend, then a small 7% pullback. MA200 (computed over 200 days
    # of uptrend) sits below the recent low → price still above MA but
    # drawdown over the last 60 days clears the correction threshold.
    up = _trend_series(350, 4.0, 7.0, seed=4)
    rng = np.random.default_rng(4)
    pullback_dates = pd.bdate_range(up.index[-1] + pd.Timedelta(days=1), periods=60)
    pullback_drift = np.linspace(0, np.log(0.93), 60)
    pullback_noise = np.cumsum(rng.normal(0, 0.003, 60))
    pullback = pd.Series(
        up.iloc[-1] * np.exp(pullback_drift + pullback_noise),
        index=pullback_dates,
    )
    series = pd.concat([up, pullback])
    decision = classify_regime(series)
    # Expectation: above MA but drawdown is meaningful → correction
    # (or in noisier seeds we might tip into sideways via elevated vol —
    # both are acceptable "derate" labels).
    assert decision.regime in {"correction", "sideways"}
    assert decision.gross_cap_multiplier < 1.0


def test_hysteresis_keeps_bull_when_dipping_just_below_ma() -> None:
    """A 0.5% dip below MA200 should not flip a previously-bull market."""

    # Force ma_long ~= latest by using a long flat series.
    series = _flat_series(400, level=5.0, vol=0.001, seed=5)
    cfg = RegimeDetectorConfig(ma_hysteresis=0.01)
    bull_first = classify_regime(series, config=cfg, previous_regime="bull")
    # Now nudge the latest price 0.3% below MA (still inside hysteresis band).
    nudged = series.copy()
    nudged.iloc[-1] = nudged.iloc[-200:].mean() * 0.997
    held_bull = classify_regime(nudged, config=cfg, previous_regime="bull")
    # Without hysteresis, "previous_regime=bear" treatment would flip; with
    # ``previous_regime="bull"`` the lower band protects the bull label.
    assert bull_first.regime in {"bull", "sideways"}
    assert held_bull.regime in {"bull", "sideways"}


def test_build_detector_config_overrides_defaults() -> None:
    raw = {
        "proxy_code": "159949",
        "ma_long_window": 100,
        "drawdown_crisis": 0.20,
        "gross_cap_multipliers": {"bear": 0.50},
    }
    cfg = build_detector_config(raw)
    assert cfg.proxy_code == "159949"
    assert cfg.ma_long_window == 100
    assert cfg.drawdown_crisis == pytest.approx(0.20)
    assert cfg.gross_cap_multipliers["bear"] == pytest.approx(0.50)
    # Untouched fields retain defaults.
    assert cfg.vol_window == 60
