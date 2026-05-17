"""Market regime classifier + strategy recommender.

Productises the empirical finding from the multi-strategy comparison
(commit ``a54b986``): on the same window, **rotation** dominated the
choppy first half while **mean_reversion** dominated the trending
second half — exactly the kind of regime-separation result that begs
for a runtime classifier so the operator can pick *which* strategy to
run without re-reading the comparison report every week.

This module is **complementary** to :mod:`src.strategy.etf_regime_detector`:

* ``etf_regime_detector`` classifies the *broad market* against an MA200
  / vol-regime / drawdown ladder and feeds a multiplier into the
  rotation strategy's ``gross_cap`` (1 of 6 sticky labels with
  hysteresis around the MA boundary). It is wired *inside* the
  rotation pipeline.
* This module classifies the *cross-asset universe* on a different
  6-label taxonomy (``trending_low_vol`` / ``trending_high_vol`` /
  ``choppy_low_vol`` / ``choppy_high_vol`` / ``bear_high_vol`` /
  ``bear_low_vol``) and recommends *which strategy entirely* to RUN.
  It is wired into the dashboard tile and consumed by the operator,
  not by any in-process pipeline.

Design choices
--------------
* Deterministic — no ML model, just feature engineering + threshold
  mapping. Same input → same output, easy to unit-test, easy to
  explain on a slide.
* Five features (R^2 of log-price linear fit, realised vol, return
  skew, drawdown ratio, cross-asset correlation) on a lookback-start
  normalised, equal-weight market proxy — chosen so a
  single feature failing the data check still leaves the other four
  to produce a confident label.
* Graceful fallback — empty / too-short input returns the ``unknown``
  regime with confidence 0 and a no-op recommendation (stay on
  current strategy), never raises.

The empirical anchor (kept here so future readers don't lose it):
commit ``a54b986`` shipped the multi-strategy comparison report. On
the ``2024-01-01 → 2025-04-30`` window the trending-vs-choppy half
split landed at:

* first half  R^2=0.370 (choppy)   → winner = rotation (+5.48%)
* second half R^2=0.792 (trending) → winner = mean_reversion (+6.17%)

The recommender below encodes that table — choppy regimes recommend
rotation; trending regimes recommend mean_reversion. Bear regimes
recommend mean_reversion *with a reduced gross_cap* (defensive long
bias) or full cash, depending on volatility.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252

# ---------------------------------------------------------------------------
# Public regime taxonomy
# ---------------------------------------------------------------------------

REGIME_LABELS: tuple[str, ...] = (
    "trending_low_vol",
    "trending_high_vol",
    "choppy_low_vol",
    "choppy_high_vol",
    "bear_high_vol",
    "bear_low_vol",
    "unknown",
)

# ---------------------------------------------------------------------------
# Threshold config + feature / regime dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassifierConfig:
    """Thresholds for :meth:`MarketRegimeClassifier.classify`.

    Defaults are tuned for a daily 4-5 ETF universe with a 90-day
    lookback. ``trend_r2_threshold`` of 0.55 corresponds roughly to the
    midpoint between the ``a54b986`` first-half R^2 (0.370, choppy)
    and second-half R^2 (0.792, trending), so the classifier reproduces
    the same split on the same window.
    """

    trend_r2_threshold: float = 0.55
    bear_slope_threshold: float = -0.0005  # log-price slope per day (~-12% annualised)
    vol_high_threshold: float = 0.25  # annualised vol; >25% = "high vol"
    skew_negative_threshold: float = -0.5  # large negative = crash-prone
    drawdown_ratio_high: float = 0.6  # max_dd / vol → high stress
    correlation_high_threshold: float = 0.7  # avg pairwise corr → risk-off

    # When any one of the five features cannot be computed we still
    # want a regime, just with lower confidence. ``min_features_required``
    # is the smallest count below which we bail to ``unknown``.
    min_features_required: int = 3

    # Multiplier confidence floor + ceiling
    min_confidence: float = 0.30
    max_confidence: float = 0.95


@dataclass(frozen=True)
class MarketRegime:
    """The classification outcome with the full feature snapshot.

    Carrying every feature value alongside the label lets the dashboard
    tile render the *why* without a second round-trip.
    """

    regime_name: str
    confidence: float
    features: dict[str, Optional[float]]
    recommended_strategy: str
    recommended_config_overrides: dict[str, Any]
    reasons: list[str]
    lookback_days: int
    n_bars_used: int
    n_assets_used: int
    as_of: Optional[str]  # ISO date of the last bar in the input

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_name": self.regime_name,
            "confidence": float(self.confidence),
            "features": {
                k: (float(v) if v is not None else None)
                for k, v in self.features.items()
            },
            "recommended_strategy": self.recommended_strategy,
            "recommended_config_overrides": dict(self.recommended_config_overrides),
            "reasons": list(self.reasons),
            "lookback_days": int(self.lookback_days),
            "n_bars_used": int(self.n_bars_used),
            "n_assets_used": int(self.n_assets_used),
            "as_of": self.as_of,
        }


# ---------------------------------------------------------------------------
# Feature engineering helpers
# ---------------------------------------------------------------------------


def _log_price_r2_and_slope(series: pd.Series) -> tuple[Optional[float], Optional[float]]:
    """Compute R^2 + slope of a linear fit on ``log(price)``.

    Returns ``(R^2, slope_per_day)``; ``(None, None)`` when the series is
    too short or has zero variance. R^2 is bounded to ``[0, 1]``.
    Slope is the log-price linear regression coefficient — negative
    means down-trend.
    """

    values = series.dropna().to_numpy(dtype=float)
    if values.size < 3 or (values <= 0).any():
        return (None, None)
    y = np.log(values)
    if float(y.var()) < 1e-15:
        return (0.0, 0.0)
    x = np.arange(y.size, dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()
    denom = float(((x - x_mean) ** 2).sum())
    if denom < 1e-15:
        return (0.0, 0.0)
    slope = float(((x - x_mean) * (y - y_mean)).sum()) / denom
    intercept = y_mean - slope * x_mean
    y_pred = slope * x + intercept
    ss_res = float(((y - y_pred) ** 2).sum())
    ss_tot = float(((y - y_mean) ** 2).sum())
    if ss_tot < 1e-15:
        return (0.0, slope)
    r2 = float(max(0.0, min(1.0, 1.0 - ss_res / ss_tot)))
    return (r2, slope)


def _realized_vol(series: pd.Series) -> Optional[float]:
    """Annualised realised vol from daily log-returns. ``None`` if too short."""

    returns = np.log(series.dropna().astype(float)).diff().dropna()
    if returns.size < 2:
        return None
    std = float(returns.std(ddof=0))
    if not np.isfinite(std):
        return None
    return float(std * np.sqrt(TRADING_DAYS_PER_YEAR))


def _return_skew(series: pd.Series) -> Optional[float]:
    """Skewness of daily simple returns. Negative = crash-prone left tail."""

    returns = series.dropna().astype(float).pct_change().dropna()
    if returns.size < 3:
        return None
    std = float(returns.std(ddof=0))
    if std < 1e-12:
        return 0.0
    mean = float(returns.mean())
    centered = (returns - mean) / std
    skew_val = float((centered ** 3).mean())
    if not np.isfinite(skew_val):
        return None
    return skew_val


def _drawdown_ratio(series: pd.Series, realized_vol: Optional[float]) -> Optional[float]:
    """``max_drawdown_abs / annualised_vol`` — stress index.

    Both quantities are positive; the ratio rises when realised vol is
    low but the drawdown is large (e.g. orderly grind-downs), which
    flags an unusual stress regime that pure vol misses.
    """

    values = series.dropna().to_numpy(dtype=float)
    if values.size < 2 or realized_vol is None or realized_vol < 1e-9:
        return None
    cum = pd.Series(values)
    running_max = cum.cummax()
    drawdown = (cum / running_max) - 1.0
    max_dd = float(-drawdown.min())  # positive number
    if not np.isfinite(max_dd):
        return None
    return float(max_dd / realized_vol)


def _normalize_price_window(price_frame: pd.DataFrame) -> pd.DataFrame:
    """Scale each usable asset to 1.0 at the first lookback bar.

    The classifier describes an equal-weighted market proxy. Averaging
    raw ETF price levels would overweight high-priced funds, so every
    asset must enter the proxy as a percentage path from the same
    lookback start.
    """

    if price_frame is None or price_frame.empty:
        return pd.DataFrame(index=getattr(price_frame, "index", None))

    numeric = price_frame.apply(pd.to_numeric, errors="coerce")
    start_prices = numeric.iloc[0].astype(float)
    valid_start_mask = (start_prices > 0) & np.isfinite(start_prices)
    valid_columns = start_prices.index[valid_start_mask]
    if len(valid_columns) == 0:
        return pd.DataFrame(index=numeric.index)

    usable = numeric.loc[:, valid_columns].where(numeric.loc[:, valid_columns] > 0)
    return usable.divide(start_prices.loc[valid_columns], axis=1)


def _avg_pairwise_correlation(price_frame: pd.DataFrame) -> Optional[float]:
    """Average pairwise correlation of log-returns across the universe.

    Returns ``None`` when there are fewer than two usable columns or
    too few overlapping rows. High average correlation → cross-asset
    risk-off (everything moves together)."""

    if price_frame is None or price_frame.shape[1] < 2:
        return None
    log_prices = np.log(price_frame.where(price_frame > 0))
    returns = log_prices.diff().dropna(how="all")
    if returns.shape[0] < 3:
        return None
    corr = returns.corr(min_periods=3)
    if corr is None or corr.empty:
        return None
    n = corr.shape[0]
    if n < 2:
        return None
    # Sum of off-diagonal, skipping NaN.
    arr = corr.to_numpy(dtype=float)
    mask = ~np.eye(n, dtype=bool)
    values = arr[mask]
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(finite.mean())


# ---------------------------------------------------------------------------
# Regime mapping
# ---------------------------------------------------------------------------


def _map_features_to_regime(
    features: Mapping[str, Optional[float]],
    config: ClassifierConfig,
) -> tuple[str, float, list[str]]:
    """Deterministic feature → regime label mapping.

    The branches are ordered:

    1. Bear (negative trend slope) — split by vol into bear_high_vol /
       bear_low_vol.
    2. Trending (R^2 >= threshold, non-negative slope) — split by vol.
    3. Choppy (everything else) — split by vol.

    Confidence starts from a base per branch and is bumped/penalised
    by the strength of the supporting signals (e.g. very negative
    skew + high correlation in a bear_high_vol case → confidence ↑;
    a trending classification with mediocre R^2 → confidence ↓).
    """

    r2 = features.get("trend_r2")
    slope = features.get("trend_slope")
    vol = features.get("realized_vol")
    skew = features.get("return_skew")
    dd_ratio = features.get("drawdown_ratio")
    corr = features.get("avg_pairwise_correlation")

    reasons: list[str] = []
    is_high_vol = vol is not None and vol >= config.vol_high_threshold
    is_bear = slope is not None and slope <= config.bear_slope_threshold
    is_trending = (
        r2 is not None
        and slope is not None
        and r2 >= config.trend_r2_threshold
        and slope > config.bear_slope_threshold
    )

    if is_bear:
        if is_high_vol:
            regime = "bear_high_vol"
            confidence = 0.7
            reasons.append(
                f"trend_slope {slope:.4f}/day <= {config.bear_slope_threshold:.4f} (bearish)"
            )
            reasons.append(f"realised_vol {vol:.1%} >= {config.vol_high_threshold:.0%} (high)")
            if skew is not None and skew <= config.skew_negative_threshold:
                confidence += 0.1
                reasons.append(f"return_skew {skew:.2f} <= {config.skew_negative_threshold:.2f} (crash-prone)")
            if corr is not None and corr >= config.correlation_high_threshold:
                confidence += 0.1
                reasons.append(f"avg pairwise corr {corr:.2f} >= {config.correlation_high_threshold:.2f} (risk-off)")
        else:
            regime = "bear_low_vol"
            confidence = 0.6
            reasons.append(
                f"trend_slope {slope:.4f}/day <= {config.bear_slope_threshold:.4f} (bearish)"
            )
            if vol is not None:
                reasons.append(f"realised_vol {vol:.1%} < {config.vol_high_threshold:.0%} (orderly)")
            if dd_ratio is not None and dd_ratio >= config.drawdown_ratio_high:
                confidence += 0.05
                reasons.append(f"drawdown/vol {dd_ratio:.2f} >= {config.drawdown_ratio_high:.2f}")
    elif is_trending:
        if is_high_vol:
            regime = "trending_high_vol"
            confidence = 0.7
            reasons.append(f"trend_r2 {r2:.2f} >= {config.trend_r2_threshold:.2f} (trending)")
            reasons.append(f"realised_vol {vol:.1%} >= {config.vol_high_threshold:.0%} (high)")
            if corr is not None and corr >= config.correlation_high_threshold:
                confidence += 0.05
                reasons.append(f"avg pairwise corr {corr:.2f} (risk-on but herded)")
        else:
            regime = "trending_low_vol"
            confidence = 0.8
            reasons.append(f"trend_r2 {r2:.2f} >= {config.trend_r2_threshold:.2f} (trending)")
            if vol is not None:
                reasons.append(f"realised_vol {vol:.1%} < {config.vol_high_threshold:.0%} (calm)")
            # Strong R^2 lifts confidence further.
            if r2 is not None and r2 >= 0.80:
                confidence += 0.1
                reasons.append(f"trend_r2 {r2:.2f} >= 0.80 (very clean)")
    else:
        # Choppy fallback. Use vol to split.
        if is_high_vol:
            regime = "choppy_high_vol"
            confidence = 0.65
            if r2 is not None:
                reasons.append(f"trend_r2 {r2:.2f} < {config.trend_r2_threshold:.2f} (choppy)")
            if vol is not None:
                reasons.append(f"realised_vol {vol:.1%} >= {config.vol_high_threshold:.0%} (high)")
        else:
            regime = "choppy_low_vol"
            confidence = 0.6
            if r2 is not None:
                reasons.append(f"trend_r2 {r2:.2f} < {config.trend_r2_threshold:.2f} (choppy)")
            if vol is not None:
                reasons.append(f"realised_vol {vol:.1%} < {config.vol_high_threshold:.0%} (calm)")

    # Confidence clamp.
    confidence = max(config.min_confidence, min(config.max_confidence, confidence))
    return regime, confidence, reasons


# ---------------------------------------------------------------------------
# Strategy recommendation map
# ---------------------------------------------------------------------------

# The mapping below is the productisation of the regime-separation
# evidence from commit ``a54b986`` plus standard portfolio risk
# practice for the bear branches:
# * trending → mean_reversion wins (a54b986 second half)
# * choppy   → rotation wins        (a54b986 first half)
# * bear     → mean_reversion with reduced gross_cap, or full cash
#
# ``config_overrides`` lines up with field names on
# :class:`src.strategy.etf_rotation_config_loader.StrategyConfig` so a
# caller can pass them straight through.

_RECOMMENDATION_TABLE: dict[str, dict[str, Any]] = {
    "trending_low_vol": {
        "strategy_name": "mean_reversion",
        "config_overrides": {"gross_cap": 1.0},
        "rationale": (
            "Trending market with calm vol — empirical (commit a54b986) shows "
            "mean_reversion captured the trending half (+6.17% vs rotation +3.85%). "
            "Run mean_reversion at full gross_cap."
        ),
        "alternatives": ["blend", "rotation"],
    },
    "trending_high_vol": {
        "strategy_name": "rotation",
        "config_overrides": {"gross_cap": 0.85},
        "rationale": (
            "Trend exists but volatility is elevated — rotation handles regime "
            "shifts better than MR's grid orders. Trim gross_cap to 0.85 "
            "to soak up the extra noise."
        ),
        "alternatives": ["blend", "mean_reversion"],
    },
    "choppy_low_vol": {
        "strategy_name": "rotation",
        "config_overrides": {"gross_cap": 1.0},
        "rationale": (
            "Choppy market with calm vol — empirical (commit a54b986) shows "
            "rotation captured the choppy half (+5.48% vs MR +2.10%). "
            "Run rotation at full gross_cap."
        ),
        "alternatives": ["blend", "mean_reversion"],
    },
    "choppy_high_vol": {
        "strategy_name": "blend",
        "config_overrides": {"gross_cap": 0.85},
        "rationale": (
            "Choppy AND volatile — single-strategy edge is small; blend rotation "
            "and MR to diversify regime risk, and shave 15% off gross_cap to "
            "respect the elevated vol."
        ),
        "alternatives": ["rotation", "mean_reversion"],
    },
    "bear_high_vol": {
        "strategy_name": "cash",
        "config_overrides": {"gross_cap": 0.20},
        "rationale": (
            "Falling market with high vol — historical evidence shows long-only "
            "systematic strategies bleed in this regime. Drop gross_cap to 0.20 "
            "(80% cash) and wait for vol to normalise."
        ),
        "alternatives": ["mean_reversion", "blend"],
    },
    "bear_low_vol": {
        "strategy_name": "mean_reversion",
        "config_overrides": {"gross_cap": 0.60},
        "rationale": (
            "Orderly bear / down-drift — MR's symmetric pull-toward-mean has a "
            "small positive edge even in declines, at reduced exposure. Run "
            "mean_reversion at gross_cap 0.60 (40% cash buffer)."
        ),
        "alternatives": ["cash", "blend"],
    },
    "unknown": {
        "strategy_name": "unchanged",
        "config_overrides": {},
        "rationale": (
            "Insufficient data to classify the regime; do not change the running "
            "strategy. Re-run once enough price history is available "
            "(>= ~60 trading days)."
        ),
        "alternatives": [],
    },
}


def _recommendation_for(regime_name: str) -> dict[str, Any]:
    """Return a *copy* of the recommendation map entry, never the singleton."""

    entry = _RECOMMENDATION_TABLE.get(regime_name, _RECOMMENDATION_TABLE["unknown"])
    return {
        "strategy_name": entry["strategy_name"],
        "config_overrides": dict(entry["config_overrides"]),
        "rationale": entry["rationale"],
        "alternatives": list(entry["alternatives"]),
    }


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class MarketRegimeClassifier:
    """Classify a multi-asset price history into a regime label.

    The class is deliberately thin — a config + a single ``classify``
    method that takes a wide-form DataFrame (date index, one column per
    asset) and returns a :class:`MarketRegime`. State is held only in
    the config; ``classify`` is referentially transparent.
    """

    def __init__(self, config: Optional[ClassifierConfig] = None) -> None:
        self.config = config or ClassifierConfig()

    def classify(
        self,
        price_history: pd.DataFrame,
        lookback_days: int = 90,
    ) -> MarketRegime:
        """Classify the current regime over the last ``lookback_days`` bars.

        Args:
            price_history: Wide-form DataFrame, date index, one column
                per asset (typically the ETF rotation universe). May be
                empty or contain NaNs; both are handled.
            lookback_days: Number of trailing rows to use for feature
                computation. Capped at the length of ``price_history``.

        Returns:
            A :class:`MarketRegime` with the regime label, confidence,
            all five features, the recommended strategy, and the
            config overrides to apply. Never raises — degenerate inputs
            return ``regime_name='unknown'`` with confidence 0.
        """

        return _classify_impl(price_history, lookback_days, self.config)


def _classify_impl(
    price_history: pd.DataFrame,
    lookback_days: int,
    config: ClassifierConfig,
) -> MarketRegime:
    if price_history is None or price_history.empty:
        return _unknown_regime(
            lookback_days=lookback_days,
            reason="price_history_empty",
            n_bars_used=0,
            n_assets_used=0,
            as_of=None,
        )

    if not isinstance(price_history, pd.DataFrame):
        # Single-series input — treat it as a one-column DataFrame so the
        # rest of the code path is uniform.
        price_history = pd.DataFrame({"series": price_history})

    # Coerce + sort + forward-fill NaNs so a single missing bar in one
    # column doesn't kill the corr matrix. Then slice the trailing window.
    frame = (
        price_history.apply(pd.to_numeric, errors="coerce")
        .sort_index()
    )
    frame = frame.ffill().dropna(how="all")

    if frame.empty:
        return _unknown_regime(
            lookback_days=lookback_days,
            reason="price_history_all_nan",
            n_bars_used=0,
            n_assets_used=0,
            as_of=None,
        )

    lookback_days = max(1, int(lookback_days))
    window = frame.iloc[-lookback_days:]
    n_bars = int(window.shape[0])
    n_assets = int(window.shape[1])
    as_of_raw = window.index[-1]
    try:
        as_of_iso: Optional[str] = pd.Timestamp(as_of_raw).date().isoformat()
    except (ValueError, TypeError):
        as_of_iso = str(as_of_raw)

    if n_bars < 10:
        return _unknown_regime(
            lookback_days=lookback_days,
            reason=f"window_too_short:{n_bars}<10",
            n_bars_used=n_bars,
            n_assets_used=n_assets,
            as_of=as_of_iso,
        )

    # Equal-weighted market proxy — normalise every ETF to 1.0 at the
    # lookback start before averaging, otherwise high-priced funds would
    # dominate the trend / vol / skew / drawdown signals.
    normalized_window = _normalize_price_window(window)
    n_assets = int(normalized_window.shape[1])
    if normalized_window.empty or n_assets == 0:
        return _unknown_regime(
            lookback_days=lookback_days,
            reason="price_window_no_valid_start_prices",
            n_bars_used=n_bars,
            n_assets_used=0,
            as_of=as_of_iso,
        )

    avg_price = normalized_window.mean(axis=1).dropna()
    if avg_price.empty or (avg_price <= 0).any():
        return _unknown_regime(
            lookback_days=lookback_days,
            reason="normalized_equal_weight_proxy_invalid",
            n_bars_used=n_bars,
            n_assets_used=n_assets,
            as_of=as_of_iso,
        )

    r2, slope = _log_price_r2_and_slope(avg_price)
    realized_vol = _realized_vol(avg_price)
    return_skew = _return_skew(avg_price)
    drawdown_ratio = _drawdown_ratio(avg_price, realized_vol)
    avg_corr = _avg_pairwise_correlation(normalized_window)

    features: dict[str, Optional[float]] = {
        "trend_r2": r2,
        "trend_slope": slope,
        "realized_vol": realized_vol,
        "return_skew": return_skew,
        "drawdown_ratio": drawdown_ratio,
        "avg_pairwise_correlation": avg_corr,
    }
    n_features_available = sum(1 for v in features.values() if v is not None)
    if n_features_available < config.min_features_required:
        return _unknown_regime(
            lookback_days=lookback_days,
            reason=(
                f"insufficient_features:{n_features_available}<"
                f"{config.min_features_required}"
            ),
            n_bars_used=n_bars,
            n_assets_used=n_assets,
            as_of=as_of_iso,
            features=features,
        )

    regime_name, confidence, reasons = _map_features_to_regime(features, config)
    recommendation = _recommendation_for(regime_name)
    return MarketRegime(
        regime_name=regime_name,
        confidence=confidence,
        features=features,
        recommended_strategy=recommendation["strategy_name"],
        recommended_config_overrides=recommendation["config_overrides"],
        reasons=reasons,
        lookback_days=lookback_days,
        n_bars_used=n_bars,
        n_assets_used=n_assets,
        as_of=as_of_iso,
    )


def _unknown_regime(
    *,
    lookback_days: int,
    reason: str,
    n_bars_used: int,
    n_assets_used: int,
    as_of: Optional[str],
    features: Optional[Mapping[str, Optional[float]]] = None,
) -> MarketRegime:
    feats: dict[str, Optional[float]] = {
        "trend_r2": None,
        "trend_slope": None,
        "realized_vol": None,
        "return_skew": None,
        "drawdown_ratio": None,
        "avg_pairwise_correlation": None,
    }
    if features:
        for k, v in features.items():
            feats[k] = v
    recommendation = _recommendation_for("unknown")
    return MarketRegime(
        regime_name="unknown",
        confidence=0.0,
        features=feats,
        recommended_strategy=recommendation["strategy_name"],
        recommended_config_overrides=recommendation["config_overrides"],
        reasons=[reason],
        lookback_days=int(lookback_days),
        n_bars_used=int(n_bars_used),
        n_assets_used=int(n_assets_used),
        as_of=as_of,
    )


__all__ = [
    "REGIME_LABELS",
    "ClassifierConfig",
    "MarketRegime",
    "MarketRegimeClassifier",
]
