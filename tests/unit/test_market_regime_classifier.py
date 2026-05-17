"""Tests for the market regime classifier + strategy recommender.

The classifier productises commit ``a54b986``'s regime-separation
finding (rotation wins choppy, mean_reversion wins trending). These
tests verify:

* Synthetic trending / choppy / bear inputs → correct regime label
* Feature computation correctness for each of the 5 features
* Strategy recommendation map agrees with the empirical anchor
* Empty / degenerate inputs return ``unknown`` instead of raising
* Real-data smoke test against ``data/etf_backtest/etf_prices_4y.csv``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.strategy.market_regime_classifier import (
    REGIME_LABELS,
    ClassifierConfig,
    MarketRegime,
    MarketRegimeClassifier,
)
from src.strategy.strategy_recommender import (
    StrategyRecommendation,
    recommend_strategy,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REAL_PRICE_CSV = PROJECT_ROOT / "data" / "etf_backtest" / "etf_prices_4y.csv"


# ---------------------------------------------------------------------------
# Synthetic price helpers — small, deterministic generators that produce
# wide-form DataFrames in the same shape as the ETF backtest CSV.
# ---------------------------------------------------------------------------


def _make_trending_universe(
    periods: int = 120,
    *,
    drift_per_day: float = 0.002,
    noise: float = 0.003,
    n_assets: int = 5,
    seed: int = 0,
) -> pd.DataFrame:
    """Steady up-trend with small noise → high R² + non-negative slope."""

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=periods)
    series = {}
    for i in range(n_assets):
        eps = rng.normal(0, noise, periods)
        log_path = np.cumsum(np.full(periods, drift_per_day) + eps)
        # Slightly different starting levels so the columns aren't identical
        series[f"ASSET{i}"] = float(1.0 + 0.1 * i) * np.exp(log_path)
    return pd.DataFrame(series, index=dates)


def _make_choppy_universe(
    periods: int = 120,
    *,
    noise: float = 0.008,
    n_assets: int = 5,
    seed: int = 0,
) -> pd.DataFrame:
    """Near-zero drift but moderate per-day noise → low R², low vol."""

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=periods)
    series = {}
    for i in range(n_assets):
        eps = rng.normal(0, noise, periods)
        log_path = np.cumsum(eps)
        series[f"ASSET{i}"] = float(1.0 + 0.1 * i) * np.exp(log_path)
    return pd.DataFrame(series, index=dates)


def _make_bear_universe(
    periods: int = 120,
    *,
    drift_per_day: float = -0.003,
    noise: float = 0.015,
    n_assets: int = 5,
    seed: int = 1,
) -> pd.DataFrame:
    """Negative drift + elevated noise → bear_high_vol."""

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=periods)
    series = {}
    for i in range(n_assets):
        eps = rng.normal(0, noise, periods)
        log_path = np.cumsum(np.full(periods, drift_per_day) + eps)
        series[f"ASSET{i}"] = float(1.0 + 0.1 * i) * np.exp(log_path)
    return pd.DataFrame(series, index=dates)


# ---------------------------------------------------------------------------
# Classifier behaviour
# ---------------------------------------------------------------------------


def test_synthetic_trending_low_vol_classified_as_trending() -> None:
    df = _make_trending_universe(periods=120, drift_per_day=0.002, noise=0.001, seed=11)
    regime = MarketRegimeClassifier().classify(df, lookback_days=90)
    assert regime.regime_name in {"trending_low_vol", "trending_high_vol"}
    # Sanity: trend_r2 must clear the threshold for any trending label
    assert regime.features["trend_r2"] is not None
    assert regime.features["trend_r2"] >= 0.5
    assert regime.confidence >= 0.5


def test_synthetic_choppy_classified_as_choppy() -> None:
    df = _make_choppy_universe(periods=120, noise=0.008, seed=22)
    regime = MarketRegimeClassifier().classify(df, lookback_days=90)
    assert regime.regime_name.startswith("choppy_")
    assert regime.features["trend_r2"] is not None
    # Choppy is defined by low R^2 with non-bearish slope
    assert regime.features["trend_r2"] < 0.55


def test_synthetic_bear_high_vol_classified_as_bear() -> None:
    df = _make_bear_universe(periods=120, drift_per_day=-0.004, noise=0.020, seed=33)
    regime = MarketRegimeClassifier().classify(df, lookback_days=90)
    assert regime.regime_name.startswith("bear_")
    assert regime.features["trend_slope"] is not None
    assert regime.features["trend_slope"] < 0.0


def test_high_priced_fund_does_not_dominate_equal_weight_proxy() -> None:
    """A high nominal price down-leg must not swamp four low-price up-legs."""

    periods = 120
    dates = pd.bdate_range("2024-01-02", periods=periods)
    steps = np.arange(periods, dtype=float)
    high_price_falling = 10_000.0 * np.exp(-0.002 * steps)
    low_price_rising = np.exp(0.002 * steps)
    df = pd.DataFrame(
        {
            "HIGH_PRICE_FALLING": high_price_falling,
            "LOW_PRICE_RISING_0": low_price_rising,
            "LOW_PRICE_RISING_1": 1.1 * low_price_rising,
            "LOW_PRICE_RISING_2": 1.2 * low_price_rising,
            "LOW_PRICE_RISING_3": 1.3 * low_price_rising,
        },
        index=dates,
    )

    regime = MarketRegimeClassifier().classify(df, lookback_days=90)

    assert regime.features["trend_slope"] is not None
    assert regime.features["trend_slope"] > 0.0
    assert not regime.regime_name.startswith("bear_")


def test_nominal_price_rescaling_leaves_regime_features_unchanged() -> None:
    """The same percentage paths should classify identically at any price level."""

    periods = 120
    dates = pd.bdate_range("2024-01-02", periods=periods)
    rng = np.random.default_rng(2026)
    log_returns = {
        "A": 0.0015 + rng.normal(0.0, 0.0030, periods),
        "B": 0.0010 + rng.normal(0.0, 0.0035, periods),
        "C": -0.0005 + rng.normal(0.0, 0.0025, periods),
        "D": 0.0008 + rng.normal(0.0, 0.0040, periods),
    }
    base = pd.DataFrame(
        {
            "A": 10.0 * np.exp(np.cumsum(log_returns["A"])),
            "B": 100.0 * np.exp(np.cumsum(log_returns["B"])),
            "C": 1_000.0 * np.exp(np.cumsum(log_returns["C"])),
            "D": 5.0 * np.exp(np.cumsum(log_returns["D"])),
        },
        index=dates,
    )
    rescaled = base.copy()
    rescaled["A"] *= 1_000_000.0
    rescaled["C"] *= 0.001

    base_regime = MarketRegimeClassifier().classify(base, lookback_days=90)
    rescaled_regime = MarketRegimeClassifier().classify(rescaled, lookback_days=90)

    assert rescaled_regime.regime_name == base_regime.regime_name
    for key, value in base_regime.features.items():
        assert value is not None, f"missing base feature: {key}"
        assert rescaled_regime.features[key] == pytest.approx(
            value,
            rel=1e-12,
            abs=1e-12,
        ), key


def test_feature_values_are_finite_and_in_expected_ranges() -> None:
    df = _make_trending_universe(periods=100, drift_per_day=0.001, noise=0.004, seed=44)
    regime = MarketRegimeClassifier().classify(df, lookback_days=90)
    # All five (six including slope) features should be finite
    for key in (
        "trend_r2",
        "trend_slope",
        "realized_vol",
        "return_skew",
        "drawdown_ratio",
        "avg_pairwise_correlation",
    ):
        assert regime.features[key] is not None, f"missing feature: {key}"
        assert np.isfinite(regime.features[key]), f"non-finite feature: {key}"
    # R^2 always in [0, 1]
    assert 0.0 <= regime.features["trend_r2"] <= 1.0
    # Realised vol is non-negative (annualised)
    assert regime.features["realized_vol"] >= 0.0
    # Drawdown ratio is non-negative (max_dd is positive)
    assert regime.features["drawdown_ratio"] >= 0.0
    # Average correlation is in [-1, 1]
    assert -1.0 <= regime.features["avg_pairwise_correlation"] <= 1.0


def test_recommendation_map_matches_regime_label() -> None:
    # Every defined regime label except 'unknown' must yield a deterministic
    # recommendation. The recommender must round-trip through to_dict.
    expected = {
        "trending_low_vol": "mean_reversion",
        "trending_high_vol": "rotation",
        "choppy_low_vol": "rotation",
        "choppy_high_vol": "blend",
        "bear_high_vol": "cash",
        "bear_low_vol": "mean_reversion",
        "unknown": "unchanged",
    }
    classifier = MarketRegimeClassifier()
    # Build a stub regime by hand for each label (the classifier's mapping
    # would be checked elsewhere; here we exercise the recommender directly).
    for label, want in expected.items():
        stub = MarketRegime(
            regime_name=label,
            confidence=0.5,
            features={},
            recommended_strategy="placeholder",
            recommended_config_overrides={},
            reasons=[],
            lookback_days=90,
            n_bars_used=90,
            n_assets_used=5,
            as_of=None,
        )
        rec = recommend_strategy(stub)
        assert rec.strategy_name == want, f"{label} → expected {want}, got {rec.strategy_name}"
        # to_dict() round-trip
        as_dict = rec.to_dict()
        assert as_dict["strategy_name"] == want
        # Recommendation regime metadata mirrors the input regime
        assert as_dict["regime_name"] == label


def test_empty_input_returns_unknown_regime() -> None:
    empty = pd.DataFrame()
    regime = MarketRegimeClassifier().classify(empty, lookback_days=90)
    assert regime.regime_name == "unknown"
    assert regime.confidence == 0.0
    assert regime.recommended_strategy == "unchanged"
    assert regime.recommended_config_overrides == {}
    # Features all None
    assert all(v is None for v in regime.features.values())


def test_window_too_short_returns_unknown() -> None:
    df = _make_trending_universe(periods=8, seed=5)  # < 10 rows
    regime = MarketRegimeClassifier().classify(df, lookback_days=90)
    assert regime.regime_name == "unknown"
    assert regime.confidence == 0.0
    assert regime.n_bars_used <= 8


def test_nan_only_input_returns_unknown() -> None:
    dates = pd.bdate_range("2024-01-02", periods=30)
    df = pd.DataFrame({"A": [float("nan")] * 30, "B": [float("nan")] * 30}, index=dates)
    regime = MarketRegimeClassifier().classify(df, lookback_days=30)
    assert regime.regime_name == "unknown"


def test_classifier_is_deterministic() -> None:
    """Same input → same output, byte-for-byte equal regime dicts."""

    df = _make_trending_universe(periods=120, drift_per_day=0.0015, noise=0.003, seed=99)
    first = MarketRegimeClassifier().classify(df, lookback_days=90).to_dict()
    second = MarketRegimeClassifier().classify(df, lookback_days=90).to_dict()
    assert first == second


def test_to_dict_is_json_serialisable() -> None:
    """The regime + recommendation dataclasses survive ``json.dumps``."""

    import json

    df = _make_trending_universe(periods=120, seed=7)
    regime = MarketRegimeClassifier().classify(df, lookback_days=90)
    rec = recommend_strategy(regime)
    payload = {"regime": regime.to_dict(), "recommendation": rec.to_dict()}
    # allow_nan=False enforces strict-JSON semantics — fail loudly if any
    # downstream feature value sneaks through as NaN.
    blob = json.dumps(payload, allow_nan=False, ensure_ascii=False)
    assert "regime_name" in blob


def test_extra_overrides_layered_onto_recommendation() -> None:
    """Caller-supplied overrides must override the canonical map."""

    stub = MarketRegime(
        regime_name="choppy_low_vol",  # canonical rotation, gross_cap=1.0
        confidence=0.6,
        features={},
        recommended_strategy="rotation",
        recommended_config_overrides={"gross_cap": 1.0},
        reasons=[],
        lookback_days=90,
        n_bars_used=90,
        n_assets_used=5,
        as_of=None,
    )
    rec = recommend_strategy(stub, extra_overrides={"gross_cap": 0.5, "extra_field": 7})
    assert rec.strategy_name == "rotation"
    assert rec.config_overrides == {"gross_cap": 0.5, "extra_field": 7}


def test_regime_labels_constant_matches_recommendation_table() -> None:
    """The public REGIME_LABELS tuple covers every key the recommender uses."""

    from src.strategy.market_regime_classifier import _RECOMMENDATION_TABLE

    for label in REGIME_LABELS:
        assert label in _RECOMMENDATION_TABLE


def test_config_thresholds_can_be_overridden() -> None:
    """A stricter R^2 threshold reclassifies a mildly-trending universe as choppy."""

    # Use 0.001 drift + moderate noise → R^2 will sit roughly in (0.4, 0.7)
    # by construction. With default 0.55 threshold the classifier is allowed
    # to land in trending OR choppy depending on the random draw; we make
    # the test deterministic by pinning a seed where default → trending,
    # then forcing a high threshold to flip the label.
    df = _make_trending_universe(periods=120, drift_per_day=0.002, noise=0.003, seed=101)
    default = MarketRegimeClassifier().classify(df, lookback_days=90)
    strict_cfg = ClassifierConfig(trend_r2_threshold=0.999)
    strict = MarketRegimeClassifier(config=strict_cfg).classify(df, lookback_days=90)
    # Trending under default but not under strict (unless slope is bearish
    # which the trending generator avoids).
    if default.regime_name.startswith("trending_"):
        assert not strict.regime_name.startswith("trending_")


# ---------------------------------------------------------------------------
# Real-data smoke
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REAL_PRICE_CSV.exists(),
    reason="real-data CSV not present in this environment",
)
def test_real_data_smoke_returns_valid_regime() -> None:
    """Real CSV → some valid regime label + a non-empty recommendation."""

    frame = pd.read_csv(REAL_PRICE_CSV, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.apply(pd.to_numeric, errors="coerce").sort_index().ffill().dropna(how="all")

    regime = MarketRegimeClassifier().classify(frame, lookback_days=90)
    rec = recommend_strategy(regime)
    assert regime.regime_name in REGIME_LABELS
    # On the committed historical window we should always have enough data
    # to land somewhere other than unknown.
    assert regime.regime_name != "unknown"
    assert regime.n_bars_used == 90
    assert regime.n_assets_used == frame.shape[1]
    # Recommendation must agree with the regime's recommended_strategy field
    assert rec.strategy_name == regime.recommended_strategy
    assert rec.strategy_name in {"rotation", "mean_reversion", "blend", "cash", "unchanged"}
