"""Broad-market regime detector for the ETF rotation strategy.

The rotation strategy reacts to *each ETF's* own trend and momentum. That
works in normal times but is too passive in macro stress — by the time a
single sleeve hits its 8% drawdown trigger the whole market is often
already down 15%. This module classifies the **broad market** (a single
proxy index, default 沪深300 510300) into a small set of regimes and
maps each regime to a multiplicative adjustment on the strategy's
``gross_cap`` plus an additive bump to ``min_score_to_hold``.

Design choices
--------------
* **Pure function**: takes a price series, returns a ``RegimeDecision``.
  No side effects, no network, easy to unit-test.
* **Sticky transitions**: a single-day move past a threshold doesn't flip
  regimes; the classifier uses a small hysteresis around each boundary
  to avoid daily regime flapping that would inject noise into the
  rotation signal.
* **Conservative defaults**: when the proxy series is too short to make
  a confident call, the classifier returns ``unknown`` and leaves the
  strategy's parameters untouched. Better to fall back to per-ETF rules
  than to dial down exposure on a false alarm.
* **Externalisable**: every threshold lives in ``RegimeDetectorConfig``
  and is read from ``strategy.json -> regime`` so you can tune without
  shipping code.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Config + decision dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeDetectorConfig:
    """Thresholds + lookbacks for :func:`classify_regime`.

    Defaults are tuned for 沪深300 daily-close data: 200-day MA defines
    the bull/bear boundary; 60-day annualised vol vs its 252-day rolling
    median defines the vol-regime; 60-day drawdown depth defines the
    correction/crisis severity.
    """

    proxy_code: str = "510300"
    ma_long_window: int = 200
    vol_window: int = 60
    vol_history_window: int = 252
    drawdown_window: int = 60

    # Vol multipliers vs historical median
    vol_elevated_multiplier: float = 1.5
    vol_crisis_multiplier: float = 2.0

    # Drawdown magnitudes (absolute fractions of the high)
    drawdown_correction: float = 0.05
    drawdown_crisis: float = 0.15

    # Hysteresis margins around MA200 (fraction of MA)
    ma_hysteresis: float = 0.01

    # Per-regime adjustments
    gross_cap_multipliers: Mapping[str, float] = field(
        default_factory=lambda: {
            "bull": 1.00,
            "correction": 0.85,
            "sideways": 0.90,
            "bear": 0.60,
            "crisis": 0.40,
            "unknown": 1.00,
        }
    )
    min_score_to_hold_offsets: Mapping[str, float] = field(
        default_factory=lambda: {
            "bull": 0.0,
            "correction": 0.0,
            "sideways": 0.0,
            "bear": 5.0,
            "crisis": 10.0,
            "unknown": 0.0,
        }
    )


@dataclass(frozen=True)
class RegimeDecision:
    """Classification outcome with full feature snapshot for transparency."""

    regime: str
    confidence: float  # in [0, 1]; 0 means "unknown"
    proxy_code: str
    proxy_price: Optional[float]
    ma_long: Optional[float]
    ma_long_window: int
    realized_vol: Optional[float]
    vol_median: Optional[float]
    vol_ratio: Optional[float]
    drawdown: Optional[float]  # negative number (0 = at high, -0.10 = 10% off high)
    reasons: list

    gross_cap_multiplier: float
    min_score_to_hold_offset: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "regime": self.regime,
            "confidence": float(self.confidence),
            "proxy_code": self.proxy_code,
            "proxy_price": (
                float(self.proxy_price) if self.proxy_price is not None else None
            ),
            "ma_long": float(self.ma_long) if self.ma_long is not None else None,
            "ma_long_window": int(self.ma_long_window),
            "realized_vol": (
                float(self.realized_vol) if self.realized_vol is not None else None
            ),
            "vol_median": (
                float(self.vol_median) if self.vol_median is not None else None
            ),
            "vol_ratio": (
                float(self.vol_ratio) if self.vol_ratio is not None else None
            ),
            "drawdown": float(self.drawdown) if self.drawdown is not None else None,
            "reasons": list(self.reasons),
            "gross_cap_multiplier": float(self.gross_cap_multiplier),
            "min_score_to_hold_offset": float(self.min_score_to_hold_offset),
        }


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def classify_regime(
    proxy_prices: pd.Series,
    *,
    config: Optional[RegimeDetectorConfig] = None,
    previous_regime: Optional[str] = None,
) -> RegimeDecision:
    """Classify the broad-market regime from a proxy index's price series.

    Args:
        proxy_prices: Daily close prices for the proxy index, indexed by
            date. Anything below the longest required window yields
            ``regime='unknown'``.
        config: Detector configuration; defaults to :class:`RegimeDetectorConfig`.
        previous_regime: Last refresh's regime label. Used for hysteresis
            around the bull/bear boundary so a single intraday touch of
            MA200 doesn't flip regimes.
    """

    cfg = config or RegimeDetectorConfig()
    reasons: list = []

    if proxy_prices is None or proxy_prices.empty:
        return _unknown_decision(cfg, "proxy_series_empty")

    series = proxy_prices.dropna().astype(float).sort_index()
    if len(series) < cfg.ma_long_window:
        return _unknown_decision(
            cfg,
            f"proxy_series_too_short:{len(series)}<{cfg.ma_long_window}",
        )

    latest = float(series.iloc[-1])
    ma_long = float(series.iloc[-cfg.ma_long_window:].mean())

    # Realized vol (60d annualised) and its 252d-rolling median.
    returns = series.pct_change().dropna()
    realized_vol: Optional[float] = None
    vol_median: Optional[float] = None
    vol_ratio: Optional[float] = None
    if len(returns) >= cfg.vol_window:
        realized_vol = float(
            returns.iloc[-cfg.vol_window:].std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)
        )
        if len(returns) >= cfg.vol_window + cfg.vol_history_window:
            rolling = (
                returns.rolling(cfg.vol_window).std(ddof=0)
                * np.sqrt(TRADING_DAYS_PER_YEAR)
            )
            vol_history = rolling.iloc[-cfg.vol_history_window:].dropna()
            if not vol_history.empty:
                vol_median = float(vol_history.median())
                if vol_median > 1e-9:
                    vol_ratio = realized_vol / vol_median

    # Drawdown over the last ``drawdown_window`` bars (negative number).
    window = series.iloc[-cfg.drawdown_window:]
    drawdown_high = float(window.max())
    drawdown = (latest / drawdown_high - 1.0) if drawdown_high > 0 else 0.0

    # ---- Classification with hysteresis around MA-long boundary --------
    ma_upper = ma_long * (1.0 + cfg.ma_hysteresis)
    ma_lower = ma_long * (1.0 - cfg.ma_hysteresis)
    if previous_regime in {"bull", "correction", "sideways"}:
        above_ma = latest >= ma_lower
    elif previous_regime in {"bear", "crisis"}:
        above_ma = latest >= ma_upper
    else:
        above_ma = latest >= ma_long

    # Crisis short-circuit: extreme vol or deep drawdown overrides everything.
    if (vol_ratio is not None and vol_ratio >= cfg.vol_crisis_multiplier) or (
        drawdown <= -cfg.drawdown_crisis
    ):
        regime = "crisis"
        if vol_ratio is not None and vol_ratio >= cfg.vol_crisis_multiplier:
            reasons.append(
                f"realised_vol {realized_vol:.1%} > {cfg.vol_crisis_multiplier:.1f}× "
                f"median {vol_median:.1%}"
            )
        if drawdown <= -cfg.drawdown_crisis:
            reasons.append(
                f"drawdown {drawdown:.1%} <= -{cfg.drawdown_crisis:.0%}"
            )
        confidence = 0.9
    elif not above_ma:
        regime = "bear"
        reasons.append(f"price {latest:.2f} below 200d MA {ma_long:.2f}")
        if vol_ratio is not None and vol_ratio >= cfg.vol_elevated_multiplier:
            reasons.append(
                f"elevated vol {realized_vol:.1%} ({vol_ratio:.1f}× median)"
            )
        confidence = 0.8
    elif drawdown <= -cfg.drawdown_correction:
        regime = "correction"
        reasons.append(
            f"price above 200d MA but drawdown {drawdown:.1%} "
            f"<= -{cfg.drawdown_correction:.0%}"
        )
        confidence = 0.7
    elif vol_ratio is not None and vol_ratio >= cfg.vol_elevated_multiplier:
        regime = "sideways"
        reasons.append(
            f"elevated vol {realized_vol:.1%} ({vol_ratio:.1f}× median) "
            "while above 200d MA"
        )
        confidence = 0.6
    else:
        regime = "bull"
        reasons.append(f"price {latest:.2f} above 200d MA {ma_long:.2f}")
        if realized_vol is not None and vol_median is not None:
            reasons.append(
                f"vol {realized_vol:.1%} near median {vol_median:.1%}"
            )
        confidence = 0.85

    gross_mult = float(cfg.gross_cap_multipliers.get(regime, 1.0))
    score_offset = float(cfg.min_score_to_hold_offsets.get(regime, 0.0))

    return RegimeDecision(
        regime=regime,
        confidence=confidence,
        proxy_code=cfg.proxy_code,
        proxy_price=latest,
        ma_long=ma_long,
        ma_long_window=cfg.ma_long_window,
        realized_vol=realized_vol,
        vol_median=vol_median,
        vol_ratio=vol_ratio,
        drawdown=drawdown,
        reasons=reasons,
        gross_cap_multiplier=gross_mult,
        min_score_to_hold_offset=score_offset,
    )


def _unknown_decision(cfg: RegimeDetectorConfig, reason: str) -> RegimeDecision:
    return RegimeDecision(
        regime="unknown",
        confidence=0.0,
        proxy_code=cfg.proxy_code,
        proxy_price=None,
        ma_long=None,
        ma_long_window=cfg.ma_long_window,
        realized_vol=None,
        vol_median=None,
        vol_ratio=None,
        drawdown=None,
        reasons=[reason],
        gross_cap_multiplier=float(cfg.gross_cap_multipliers.get("unknown", 1.0)),
        min_score_to_hold_offset=float(cfg.min_score_to_hold_offsets.get("unknown", 0.0)),
    )


def build_detector_config(
    raw: Optional[Mapping[str, object]],
) -> RegimeDetectorConfig:
    """Construct :class:`RegimeDetectorConfig` from a strategy.json fragment."""

    if not raw:
        return RegimeDetectorConfig()
    kwargs = {}
    for field_name in (
        "proxy_code",
        "ma_long_window",
        "vol_window",
        "vol_history_window",
        "drawdown_window",
        "vol_elevated_multiplier",
        "vol_crisis_multiplier",
        "drawdown_correction",
        "drawdown_crisis",
        "ma_hysteresis",
    ):
        if field_name in raw:
            kwargs[field_name] = raw[field_name]
    if "gross_cap_multipliers" in raw:
        kwargs["gross_cap_multipliers"] = dict(raw["gross_cap_multipliers"])  # type: ignore[arg-type]
    if "min_score_to_hold_offsets" in raw:
        kwargs["min_score_to_hold_offsets"] = dict(raw["min_score_to_hold_offsets"])  # type: ignore[arg-type]
    return RegimeDetectorConfig(**kwargs)


__all__ = [
    "RegimeDecision",
    "RegimeDetectorConfig",
    "build_detector_config",
    "classify_regime",
]
