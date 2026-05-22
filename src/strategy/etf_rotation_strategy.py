"""ETF rotation target-weight strategy.

This module is intentionally pure and broker-agnostic. It converts a price
matrix into daily target weights that can be consumed by PortfolioBacktester.
Cash is implicit: ETF weights may sum to less than one.

Look-ahead semantics
--------------------
``generate_signals`` evaluates each day's score from that day's close, then
**lags the resulting weights by ``lag_days`` (default 1)** before returning.
This means the weight on row ``t`` represents the target to hold starting
day ``t``, computed from data available at end of day ``t - lag_days``. Set
``lag_days=0`` only when you explicitly want the same-day signal — usually
for live ``evaluate()``-style inspection, never for backtesting.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252

# Shared default — keeps live (``daily_etf_signal``) and backtest
# (``scripts/backtest_etf_rotation``) on the same rebalance threshold.
DEFAULT_REBALANCE_THRESHOLD = 0.03


@dataclass(frozen=True)
class EtfAssetConfig:
    """Configuration for one ETF in the rotation universe.

    Weight fields are **fractions** (``0.30`` = 30%). ``__post_init__``
    enforces the bounds: a config with ``max_weight=3.5`` or a negative
    ``base_weight`` is rejected at construction time so a malformed
    real-money config fails fast instead of silently mis-sizing positions.
    """

    symbol: str
    name: str = ""
    category: str = ""
    min_weight: float = 0.0
    max_weight: float = 0.30
    base_weight: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("min_weight", "max_weight", "base_weight"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(
                    f"EtfAssetConfig.{field_name} for {self.symbol!r} must be "
                    f"numeric, got {value!r}"
                )
            number = float(value)
            if number != number:  # NaN guard
                raise ValueError(
                    f"EtfAssetConfig.{field_name} for {self.symbol!r} is NaN"
                )
            if not 0.0 <= number <= 1.0:
                raise ValueError(
                    f"EtfAssetConfig.{field_name} for {self.symbol!r} must be a "
                    f"fraction in [0, 1], got {number}"
                )
        if self.min_weight > self.max_weight:
            raise ValueError(
                f"EtfAssetConfig for {self.symbol!r}: min_weight "
                f"({self.min_weight}) must not exceed max_weight "
                f"({self.max_weight})"
            )


@dataclass(frozen=True)
class EtfOverlay:
    """External/specialist signal overlay for an ETF.

    Example: the 512400 specialist project can set `max_weight=0.10` and
    `block_new_buys=True` when its signal says 禁止追高.
    """

    max_weight: Optional[float] = None
    block_new_buys: bool = False
    premium: Optional[float] = None
    reason: str = ""


@dataclass(frozen=True)
class EtfScoringConfig:
    """All scoring constants used by ``EtfRotationStrategy``.

    Hoisted out of the strategy body so callers can grid-search them in
    walk-forward backtests without monkeypatching. Defaults match the
    legacy hand-tuned numbers — change them through this struct, never
    by editing the strategy directly.

    Two scoring modes:

    * ``absolute`` (default): hand-tuned thresholds. Backward compatible.
    * ``cross_sectional``: same features but normalised to cross-sectional
      Z-scores across the universe daily. Multipliers below are reused as
      weights (sign matters; magnitude is comparable between features
      because Z-scores are standardised). Self-calibrating across
      regimes — when everything is in drawdown, the *relatively* best
      assets still get allocated.

    Multi-timeframe extension
    -------------------------
    On top of the legacy 20/60-day MA + 5/20/60-day momentum features,
    the scoring layer now also reads:

    * ``ma200`` — long-term trend context (skipped when history < 200 bars).
      Above-MA200 gets ``trend_above_ma200_points`` added; below subtracts
      ``trend_below_ma200_penalty`` (asymmetric: penalty by default smaller
      than the bonus so a long-term breakdown caps but doesn't dominate).
    * Short-term reversal — ``return5`` below ``short_reversal_threshold``
      (oversold) adds ``short_reversal_bonus``. Catches mean-reversion
      opportunities the pure trend-following body misses.
    """

    # Trend (above/below MA points)
    trend_above_ma20_points: float = 20.0
    trend_above_ma60_points: float = 20.0
    trend_above_ma200_points: float = 12.0
    trend_below_ma200_penalty: float = 8.0
    trend_ma20_above_ma60_points: float = 20.0
    trend_ma20_below_ma60_penalty: float = 10.0

    # Momentum
    momentum_return20_multiplier: float = 250.0
    momentum_return20_floor: float = -20.0
    momentum_return20_ceiling: float = 25.0
    momentum_return60_multiplier: float = 120.0
    momentum_return60_floor: float = -20.0
    momentum_return60_ceiling: float = 20.0
    momentum_short_spike_threshold: float = 0.08
    momentum_short_spike_penalty: float = 10.0
    momentum_short_uptrend_threshold: float = 0.0
    momentum_short_uptrend_bonus: float = 5.0
    # Short-term reversal: when return5 dips below this threshold (oversold),
    # add the bonus. Lets the strategy catch bounces in otherwise-trending
    # assets without overriding the trend gate.
    short_reversal_threshold: float = -0.04
    short_reversal_bonus: float = 4.0

    # Risk (volatility & drawdown)
    risk_baseline: float = 15.0
    risk_volatility_multiplier: float = 35.0
    risk_volatility_penalty_floor: float = 0.0
    risk_volatility_penalty_ceiling: float = 25.0
    risk_drawdown_multiplier: float = 60.0
    risk_drawdown_floor: float = -15.0
    risk_drawdown_ceiling: float = 0.0

    # Premium thresholds (overlay-driven)
    premium_hard_threshold: float = 0.05
    premium_hard_penalty: float = -30.0
    premium_soft_threshold: float = 0.02
    premium_soft_penalty: float = -18.0
    premium_discount_threshold: float = -0.01
    premium_discount_bonus: float = 5.0

    # Cross-sectional adaptive scoring (only consulted when
    # ``EtfRotationConfig.scoring_mode == 'cross_sectional'``)
    cs_score_baseline: float = 50.0
    cs_z_return20_weight: float = 12.0
    cs_z_return60_weight: float = 8.0
    cs_z_trend_strength_weight: float = 12.0
    cs_z_drawdown_weight: float = 6.0
    cs_z_volatility_weight: float = -8.0
    cs_z_clip: float = 3.0

    # MA60 hard-gate softening: when an asset dips below its 60d MA but
    # is still above the 200d MA, scale the target weight by this multiplier
    # instead of cutting to zero. Rationale: the legacy ``latest < ma60``
    # → 0 rule whipsawed strong long-term uptrends (gold +159% over 4y
    # with only ~25% drawdowns) because every normal pullback flipped
    # the gate. Setting to 1.0 disables the softening (full legacy
    # behaviour); 0.0 also disables (degenerates to legacy zero).
    long_trend_override_multiplier: float = 0.5


@dataclass(frozen=True)
class EtfRotationConfig:
    """Global strategy configuration.

    ``min_score_to_hold`` is the bottom of a smooth ramp: scores at or below
    it produce zero weight, scores at ``min_score_full_hold`` reach the full
    score-scaled cap. The two together stop the strategy from snapping
    in/out of a position when the score wobbles by 0.1 around a hard cutoff.

    Policy signal factor
    --------------------
    Optional, default-OFF integration with ``policy_radar`` industry signals.
    When ``policy_signal_factor_enabled=True``, each ETF's target weight is
    multiplied by ``(1 + bullish_boost)`` if its mapped industry signal is
    bullish or ``(1 - bearish_penalty)`` if bearish. Neutral signals
    (``policy_signal_factor_neutral_pass=True``) leave the weight unchanged.
    After adjustment the weights are re-normalised so the gross cap invariant
    is preserved. The strategy invariant — with the mild default knobs of
    ±10% — is that no position is ever zeroed or doubled by this factor
    alone; it nudges only.

    Construction:

    * Pass ``industry_signals`` to ``generate_signals`` / ``evaluate`` as a
      ``{industry_name: {"avg_impact": float, "signal": "bullish"|...}}``
      mapping (the live shape of ``policy_radar.json``'s ``industry_signals``).
    * Pass ``etf_industry_map`` as a ``{etf_code: industry_name}`` lookup so
      the strategy can resolve each ETF to a policy-radar industry. Codes
      missing from the map are silently skipped (no penalty, no boost) — so
      adding a single ETF↔industry edge gradually rolls out without forcing
      every legacy ETF to be mapped at once.
    """

    assets: list[EtfAssetConfig]
    gross_cap: float = 0.90
    warmup_days: int = 60
    annualized_vol_target: Optional[float] = 0.20
    min_score_to_hold: float = 25.0
    min_score_full_hold: float = 35.0
    enable_vol_targeting: bool = False
    scoring: EtfScoringConfig = field(default_factory=EtfScoringConfig)
    scoring_mode: str = "absolute"  # "absolute" | "cross_sectional"
    # Policy-radar opt-in nudges. All defaults reproduce legacy behaviour.
    policy_signal_factor_enabled: bool = False
    policy_signal_factor_bullish_boost: float = 0.10
    policy_signal_factor_bearish_penalty: float = 0.10
    policy_signal_factor_neutral_pass: bool = True
    # avg_impact threshold above which a signal counts as bullish (and
    # symmetrically below ``-bullish_threshold`` for bearish). Default 0.10
    # matches the dashboard's existing bullish/bearish classification.
    policy_signal_factor_bullish_threshold: float = 0.10

    def __post_init__(self) -> None:
        if self.min_score_full_hold < self.min_score_to_hold:
            raise ValueError(
                "min_score_full_hold must be >= min_score_to_hold"
            )
        if self.scoring_mode not in {"absolute", "cross_sectional"}:
            raise ValueError(
                f"scoring_mode must be 'absolute' or 'cross_sectional', got {self.scoring_mode!r}"
            )
        if self.policy_signal_factor_bullish_boost < 0.0:
            raise ValueError(
                "policy_signal_factor_bullish_boost must be >= 0"
            )
        if not 0.0 <= self.policy_signal_factor_bearish_penalty < 1.0:
            raise ValueError(
                "policy_signal_factor_bearish_penalty must be in [0, 1)"
            )
        if self.policy_signal_factor_bullish_threshold < 0.0:
            raise ValueError(
                "policy_signal_factor_bullish_threshold must be >= 0"
            )

    def asset_map(self) -> dict[str, EtfAssetConfig]:
        return {asset.symbol: asset for asset in self.assets}


@dataclass(frozen=True)
class EtfSignal:
    """Signal and feature snapshot for a single ETF on one date.

    ``ma200`` is ``None`` when the price series is shorter than 200 bars
    so consumers can distinguish "long-term trend irrelevant" from
    "long-term down-trend confirmed".
    """

    symbol: str
    latest_price: float
    ma20: float
    ma60: float
    return5: float
    return20: float
    return60: float
    drawdown60: float
    volatility60: float
    trend_score: float
    momentum_score: float
    risk_score: float
    premium_score: float
    score: float
    raw_weight: float
    target_weight: float
    reasons: list[str] = field(default_factory=list)
    # Multi-timeframe extension (added later, kept at the end for back-compat
    # with positional EtfSignal(...) constructors in existing tests).
    ma200: Optional[float] = None
    trend_long_strength: Optional[float] = None  # price / ma200 - 1
    # Policy-radar nudge metadata (set when policy_signal_factor fires).
    # ``policy_adjustment`` is None when no policy adjustment was applied
    # (factor disabled / no industry mapped / no policy data). When set,
    # carries the per-ETF context for audit + dashboard surfaces.
    policy_adjustment: Optional[dict[str, Any]] = None
    # Technical-timing indicators, surfaced for the per-position dashboard
    # panel and the audit score_breakdown so the weekly cron can compute
    # IC vs forward returns. None when the price series is shorter than
    # the indicator's required lookback (14 bars for RSI, 20 for BB).
    rsi14: Optional[float] = None
    bollinger_position: Optional[float] = None  # 0 = lower band, 1 = upper


class EtfRotationStrategy:
    """Daily ETF rotation strategy returning target-weight DataFrames."""

    def __init__(self, config: EtfRotationConfig):
        if not config.assets:
            raise ValueError("EtfRotationConfig.assets must not be empty")
        if not 0.0 < config.gross_cap <= 1.0:
            raise ValueError("gross_cap must be in (0, 1]")
        self.config = config
        self._assets = config.asset_map()

    def generate_signals(
        self,
        price_matrix: pd.DataFrame,
        *,
        overlays: Optional[Mapping[str, EtfOverlay]] = None,
        current_weights: Optional[Mapping[str, float]] = None,
        lag_days: int = 1,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> pd.DataFrame:
        """Return target weights for every date in `price_matrix`.

        Args:
            price_matrix: Wide-form close prices indexed by date.
            overlays: Per-symbol specialist signal overlay (live use only).
            current_weights: Snapshot of current portfolio weights.
            lag_days: Number of bars to lag the produced weights so signal
                at ``t`` is applied at ``t + lag_days``. Default ``1``
                eliminates the close-to-close look-ahead. Set to ``0`` only
                for diagnostic inspection — never for backtests.
            industry_signals: Optional snapshot of policy_radar industry
                signals (``{industry: {avg_impact, signal, ...}}``). Only
                consulted when ``config.policy_signal_factor_enabled``.
            etf_industry_map: Optional ``{etf_code: industry_name}`` lookup
                used to resolve each ETF to a policy_radar industry. Codes
                missing from the map (or with no matching industry signal)
                are left untouched.
        """

        if lag_days < 0:
            raise ValueError("lag_days must be >= 0")

        prices = self._prepare_prices(price_matrix)
        weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        overlays = overlays or {}
        current_weights = current_weights or {}

        for idx in range(self.config.warmup_days, len(prices)):
            window = prices.iloc[: idx + 1]
            signals = self._evaluate_prepared(
                window,
                overlays=overlays,
                current_weights=current_weights,
                industry_signals=industry_signals,
                etf_industry_map=etf_industry_map,
            )
            for signal in signals:
                if signal.symbol in weights.columns:
                    weights.iat[idx, weights.columns.get_loc(signal.symbol)] = (
                        signal.target_weight
                    )

        if lag_days > 0:
            weights = weights.shift(lag_days).fillna(0.0)
        else:
            weights = weights.fillna(0.0)
        return weights

    def evaluate(
        self,
        price_matrix: pd.DataFrame,
        *,
        overlays: Optional[Mapping[str, EtfOverlay]] = None,
        current_weights: Optional[Mapping[str, float]] = None,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> list[EtfSignal]:
        """Evaluate the latest row of a price matrix and return ETF signals.

        The returned signals reflect the same-day score (no lag). Callers
        that need a backtest-style lag should use ``generate_signals``.

        ``industry_signals`` / ``etf_industry_map`` carry the policy_radar
        opt-in. See ``generate_signals`` for the shape.
        """

        prices = self._prepare_prices(price_matrix)
        return self._evaluate_prepared(
            prices,
            overlays=overlays or {},
            current_weights=current_weights or {},
            industry_signals=industry_signals,
            etf_industry_map=etf_industry_map,
        )

    def _evaluate_prepared(
        self,
        prices: pd.DataFrame,
        *,
        overlays: Mapping[str, EtfOverlay],
        current_weights: Mapping[str, float],
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> list[EtfSignal]:
        signals: list[EtfSignal] = []
        for symbol in prices.columns:
            if symbol not in self._assets:
                continue
            series = prices[symbol].dropna()
            if len(series) < self.config.warmup_days:
                continue
            signals.append(
                self._build_signal(
                    symbol=symbol,
                    series=series,
                    overlay=overlays.get(symbol),
                    current_weight=float(current_weights.get(symbol, 0.0)),
                )
            )

        # Adaptive cross-sectional scoring rescales the composite ``score``
        # against the universe's distribution-of-the-day. The per-asset
        # ``target_weight`` is then recomputed so the rest of the pipeline
        # (gross-cap normaliser + risk rules) consumes the adaptive weights.
        if self.config.scoring_mode == "cross_sectional" and signals:
            signals = self._apply_cross_sectional_scoring(signals, overlays, current_weights)

        # Policy-radar opt-in nudge: applied AFTER scoring so it tilts the
        # final target without contaminating the score breakdown that the
        # audit log uses to back-fill the Information Coefficient. The
        # adjustment is bounded by config (default ±10%) and re-normalised
        # to preserve the gross cap invariant; see ``_apply_policy_signal_factor``.
        if (
            self.config.policy_signal_factor_enabled
            and signals
            and industry_signals
            and etf_industry_map
        ):
            signals = self._apply_policy_signal_factor(
                signals,
                industry_signals=industry_signals,
                etf_industry_map=etf_industry_map,
            )

        return self._normalize_signals(signals)

    def _apply_cross_sectional_scoring(
        self,
        signals: list[EtfSignal],
        overlays: Mapping[str, EtfOverlay],
        current_weights: Mapping[str, float],
    ) -> list[EtfSignal]:
        """Rebuild ``score`` and ``target_weight`` using cross-sectional Z-scores.

        Five features feed the rebuild: ``return20``, ``return60``,
        ``trend_strength`` (defined as ``price / ma60 - 1``), 60d drawdown
        depth (negative), and 60d annualised volatility. Each is centred
        and scaled across the universe-of-the-day; the weighted sum of
        Z-scores plus the ``cs_score_baseline`` becomes the new score.

        Falls back to single-asset universes by returning the input
        signals untouched — there is no cross-section to standardise.
        """

        if len(signals) < 2:
            return signals

        scoring = self.config.scoring
        # Pull features into parallel arrays.
        ret20 = np.array([s.return20 for s in signals], dtype=float)
        ret60 = np.array([s.return60 for s in signals], dtype=float)
        trend_strength = np.array(
            [(s.latest_price / s.ma60 - 1.0) if s.ma60 > 0 else 0.0 for s in signals],
            dtype=float,
        )
        drawdown = np.array([s.drawdown60 for s in signals], dtype=float)
        volatility = np.array([s.volatility60 for s in signals], dtype=float)

        def _z(values: np.ndarray) -> np.ndarray:
            mean = float(values.mean())
            std = float(values.std(ddof=0))
            if std < 1e-12:
                return np.zeros_like(values)
            z = (values - mean) / std
            return np.clip(z, -scoring.cs_z_clip, scoring.cs_z_clip)

        z_ret20 = _z(ret20)
        z_ret60 = _z(ret60)
        z_trend = _z(trend_strength)
        z_dd = _z(drawdown)
        z_vol = _z(volatility)

        composite = (
            scoring.cs_score_baseline
            + scoring.cs_z_return20_weight * z_ret20
            + scoring.cs_z_return60_weight * z_ret60
            + scoring.cs_z_trend_strength_weight * z_trend
            + scoring.cs_z_drawdown_weight * z_dd
            + scoring.cs_z_volatility_weight * z_vol
        )
        # Premium overlay is a hard penalty; it still maps to absolute points.
        premium = np.array([s.premium_score for s in signals], dtype=float)
        composite = composite + premium
        composite = np.clip(composite, 0.0, 100.0)

        adapted: list[EtfSignal] = []
        for i, sig in enumerate(signals):
            asset = self._assets[sig.symbol]
            new_score = float(composite[i])
            new_raw = self._score_to_weight(
                asset, new_score, sig.latest_price, sig.ma60, sig.volatility60,
                ma200=sig.ma200,
            )
            new_target = self._apply_asset_constraints(
                raw_weight=new_raw,
                asset=asset,
                overlay=overlays.get(sig.symbol),
                current_weight=float(current_weights.get(sig.symbol, 0.0)),
            )
            adapted.append(
                replace(
                    sig,
                    score=new_score,
                    raw_weight=new_raw,
                    target_weight=new_target,
                )
            )
        return adapted

    def _classify_industry_signal(
        self,
        avg_impact: float,
    ) -> str:
        """Classify a policy_radar avg_impact into bullish / bearish / neutral.

        The threshold lives in the strategy config (default ±0.10, matching
        the dashboard's existing chip colouring). Non-finite avg_impact is
        treated as neutral to keep NaN out of the multiplier path.
        """

        if not np.isfinite(avg_impact):
            return "neutral"
        threshold = float(self.config.policy_signal_factor_bullish_threshold)
        if avg_impact > threshold:
            return "bullish"
        if avg_impact < -threshold:
            return "bearish"
        return "neutral"

    def _apply_policy_signal_factor(
        self,
        signals: list[EtfSignal],
        *,
        industry_signals: Mapping[str, Mapping[str, Any]],
        etf_industry_map: Mapping[str, str],
    ) -> list[EtfSignal]:
        """Nudge per-ETF target weights by their mapped policy_radar signal.

        Strategy invariant: with default knobs (±10%) no position is ever
        zeroed or doubled by this factor alone — the adjustment is a tilt,
        not a switch. After per-ETF multipliers the weights are re-normalised
        proportionally so the gross-cap invariant is preserved (the next
        ``_normalize_signals`` pass will scale down further if a downstream
        rule changed totals).

        Each adjusted ``EtfSignal`` records the multiplier, signal classification,
        and the policy industry it was mapped to so the audit log / dashboard
        can render "ETF X: -8% policy bearish" rows after the fact.
        """

        bullish_boost = float(self.config.policy_signal_factor_bullish_boost)
        bearish_penalty = float(self.config.policy_signal_factor_bearish_penalty)
        neutral_pass = bool(self.config.policy_signal_factor_neutral_pass)

        adjusted: list[EtfSignal] = []
        boosted_count = 0
        penalised_count = 0
        for sig in signals:
            industry = etf_industry_map.get(sig.symbol)
            if not industry:
                adjusted.append(sig)
                continue
            row = industry_signals.get(industry)
            if not isinstance(row, Mapping):
                adjusted.append(sig)
                continue
            try:
                avg_impact = float(row.get("avg_impact", 0.0))
            except (TypeError, ValueError):
                avg_impact = 0.0

            classification = self._classify_industry_signal(avg_impact)
            multiplier = 1.0
            applied = False
            if classification == "bullish":
                multiplier = 1.0 + bullish_boost
                applied = bullish_boost > 0.0
            elif classification == "bearish":
                multiplier = 1.0 - bearish_penalty
                applied = bearish_penalty > 0.0
            elif classification == "neutral" and not neutral_pass:
                # Future hook: explicit neutral handling. Defaults preserve
                # neutral as a no-op so we stay backward-compatible.
                multiplier = 1.0
                applied = False

            if not applied:
                # Still attach metadata so the dashboard can show the policy
                # context even when no action was taken (e.g. neutral signal).
                policy_meta: dict[str, Any] = {
                    "industry": industry,
                    "signal": classification,
                    "avg_impact": avg_impact,
                    "multiplier": 1.0,
                    "delta_weight": 0.0,
                    "weight_before": float(sig.target_weight),
                    "weight_after": float(sig.target_weight),
                    "applied": False,
                }
                adjusted.append(replace(sig, policy_adjustment=policy_meta))
                continue

            prior = float(sig.target_weight)
            new_target = max(0.0, prior * multiplier)
            # Respect the per-ETF max_weight cap even when boosting.
            asset = self._assets.get(sig.symbol)
            if asset is not None:
                new_target = min(new_target, float(asset.max_weight))

            policy_meta = {
                "industry": industry,
                "signal": classification,
                "avg_impact": avg_impact,
                "multiplier": float(multiplier),
                "delta_weight": float(new_target - prior),
                "weight_before": prior,
                "weight_after": float(new_target),
                "applied": True,
            }
            if classification == "bullish":
                boosted_count += 1
            elif classification == "bearish":
                penalised_count += 1
            adjusted.append(
                replace(
                    sig,
                    target_weight=new_target,
                    policy_adjustment=policy_meta,
                )
            )

        # Re-normalise: if the policy tilt pushed total ETF weight above
        # ``gross_cap`` the normaliser will pull every ETF back down by the
        # same scale, preserving relative weights. Below the cap means
        # gross under-allocated — fine, cash absorbs it. We DON'T re-scale
        # up because that would defeat the bearish penalty (penalty + scale-up
        # would restore the original weight).
        gross = sum(max(s.target_weight, 0.0) for s in adjusted)
        if gross > self.config.gross_cap and gross > 0:
            scale = self.config.gross_cap / gross
            rescaled: list[EtfSignal] = []
            for sig in adjusted:
                new_w = float(sig.target_weight) * scale
                meta = sig.policy_adjustment
                if meta is not None and isinstance(meta, dict):
                    meta = dict(meta)
                    meta["weight_after"] = new_w
                    meta["delta_weight"] = new_w - meta.get("weight_before", new_w)
                rescaled.append(replace(sig, target_weight=new_w, policy_adjustment=meta))
            adjusted = rescaled

        if boosted_count or penalised_count:
            logger.info(
                "policy_signal_factor: boosted %d ETFs, penalised %d ETFs "
                "(bullish_boost=%.3f, bearish_penalty=%.3f)",
                boosted_count, penalised_count,
                bullish_boost, bearish_penalty,
            )
        return adjusted

    def _build_signal(
        self,
        *,
        symbol: str,
        series: pd.Series,
        overlay: Optional[EtfOverlay],
        current_weight: float,
    ) -> EtfSignal:
        asset = self._assets[symbol]
        latest = float(series.iloc[-1])
        ma20 = float(series.iloc[-20:].mean())
        ma60 = float(series.iloc[-60:].mean())
        ma200: Optional[float] = None
        trend_long_strength: Optional[float] = None
        if len(series) >= 200:
            ma200 = float(series.iloc[-200:].mean())
            if ma200 > 0:
                trend_long_strength = latest / ma200 - 1.0
        high60 = float(series.iloc[-60:].max())
        returns = series.pct_change().dropna()

        return5 = self._period_return(series, 5)
        return20 = self._period_return(series, 20)
        return60 = self._period_return(series, 60)
        drawdown60 = latest / high60 - 1.0 if high60 > 0 else 0.0
        volatility60 = float(returns.iloc[-60:].std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if not np.isfinite(volatility60):
            volatility60 = 0.0
        rsi14 = self._rsi(series, period=14)
        bollinger_position = self._bollinger_position(series, period=20)

        scoring = self.config.scoring
        trend_score, trend_reasons = self._score_trend(latest, ma20, ma60, scoring, ma200=ma200)
        momentum_score = self._score_momentum(return5, return20, return60, scoring)
        risk_score = self._score_risk(volatility60, drawdown60, scoring)
        premium_score = self._score_premium(overlay, scoring)
        score = float(np.clip(trend_score + momentum_score + risk_score + premium_score, 0.0, 100.0))

        raw_weight = self._score_to_weight(
            asset, score, latest, ma60, volatility60, ma200=ma200,
        )
        target_weight = self._apply_asset_constraints(
            raw_weight=raw_weight,
            asset=asset,
            overlay=overlay,
            current_weight=current_weight,
        )

        reasons = [*trend_reasons]
        if overlay and overlay.reason:
            reasons.append(overlay.reason)

        return EtfSignal(
            symbol=symbol,
            latest_price=latest,
            ma20=ma20,
            ma60=ma60,
            ma200=ma200,
            trend_long_strength=trend_long_strength,
            return5=return5,
            return20=return20,
            return60=return60,
            drawdown60=drawdown60,
            volatility60=volatility60,
            trend_score=trend_score,
            momentum_score=momentum_score,
            risk_score=risk_score,
            premium_score=premium_score,
            score=score,
            raw_weight=raw_weight,
            target_weight=target_weight,
            reasons=reasons,
            rsi14=rsi14,
            bollinger_position=bollinger_position,
        )

    def _normalize_signals(self, signals: Iterable[EtfSignal]) -> list[EtfSignal]:
        signal_list = list(signals)
        gross = sum(max(signal.target_weight, 0.0) for signal in signal_list)
        if gross <= self.config.gross_cap or gross <= 0:
            return signal_list

        scale = self.config.gross_cap / gross
        return [
            replace(signal, target_weight=signal.target_weight * scale)
            for signal in signal_list
        ]

    def _score_to_weight(
        self,
        asset: EtfAssetConfig,
        score: float,
        latest: float,
        ma60: float,
        volatility60: float,
        ma200: Optional[float] = None,
    ) -> float:
        # Trend gate with long-term context override.
        # * Above MA60 → full weight (standard path)
        # * Below MA60 but above MA200 → reduced weight via
        #   ``long_trend_override_multiplier`` (legacy pullback in a
        #   multi-year uptrend; don't blow the entire position)
        # * Below MA60 AND below MA200 (or no MA200 yet) → zero
        long_trend_intact = (
            ma200 is not None and ma200 > 0 and latest > ma200
        )
        short_trend_intact = latest >= ma60
        trend_multiplier = 1.0
        if not short_trend_intact:
            if not long_trend_intact:
                return 0.0
            trend_multiplier = float(self.config.scoring.long_trend_override_multiplier)
            if trend_multiplier <= 0.0:
                return 0.0

        # Smooth ramp on score: zero at min_score_to_hold, full at
        # min_score_full_hold. Prevents micro-thrashing across a hard cutoff.
        ramp_low = self.config.min_score_to_hold
        ramp_high = self.config.min_score_full_hold
        if score <= ramp_low:
            return 0.0
        if ramp_high <= ramp_low + 1e-9:
            ramp_weight = 1.0
        else:
            ramp_weight = float(np.clip((score - ramp_low) / (ramp_high - ramp_low), 0.0, 1.0))

        score_fraction = float(np.clip(score / 100.0, 0.0, 1.0))
        base_target = (
            max(asset.base_weight, asset.max_weight * score_fraction)
            * ramp_weight
            * trend_multiplier
        )

        cap = asset.max_weight
        if self.config.enable_vol_targeting and self.config.annualized_vol_target:
            vol = max(volatility60, 1e-4)  # guard against div-by-zero
            vol_cap = (self.config.annualized_vol_target / vol) * asset.max_weight
            cap = float(np.clip(vol_cap, 0.0, asset.max_weight))

        return float(np.clip(base_target, 0.0, cap))

    @staticmethod
    def _apply_asset_constraints(
        *,
        raw_weight: float,
        asset: EtfAssetConfig,
        overlay: Optional[EtfOverlay],
        current_weight: float,
    ) -> float:
        max_weight = asset.max_weight
        if overlay and overlay.max_weight is not None:
            max_weight = min(max_weight, max(0.0, overlay.max_weight))
        target = float(np.clip(raw_weight, asset.min_weight, max_weight))
        if overlay and overlay.block_new_buys:
            target = min(target, current_weight)
        return target

    @staticmethod
    def _score_trend(
        latest: float,
        ma20: float,
        ma60: float,
        scoring: EtfScoringConfig,
        *,
        ma200: Optional[float] = None,
    ) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 0.0
        if latest > ma20:
            score += scoring.trend_above_ma20_points
            reasons.append("price_above_ma20")
        if latest > ma60:
            score += scoring.trend_above_ma60_points
            reasons.append("price_above_ma60")
        if ma20 > ma60:
            score += scoring.trend_ma20_above_ma60_points
            reasons.append("ma20_above_ma60")
        else:
            score -= scoring.trend_ma20_below_ma60_penalty
            reasons.append("ma20_not_above_ma60")
        # Long-term trend context: rewards multi-year uptrends, penalises
        # multi-year breakdowns. Only consulted when we have 200+ bars.
        if ma200 is not None and ma200 > 0:
            if latest > ma200:
                score += scoring.trend_above_ma200_points
                reasons.append("price_above_ma200")
            else:
                score -= scoring.trend_below_ma200_penalty
                reasons.append("price_below_ma200")
        return score, reasons

    @staticmethod
    def _score_momentum(
        return5: float,
        return20: float,
        return60: float,
        scoring: EtfScoringConfig,
    ) -> float:
        score = 0.0
        score += np.clip(
            return20 * scoring.momentum_return20_multiplier,
            scoring.momentum_return20_floor,
            scoring.momentum_return20_ceiling,
        )
        score += np.clip(
            return60 * scoring.momentum_return60_multiplier,
            scoring.momentum_return60_floor,
            scoring.momentum_return60_ceiling,
        )
        # Short-term path: spike penalty (no chasing) vs mild uptrend bonus
        # vs *oversold* reversal bonus. Spike threshold takes priority; if
        # neither extreme triggers we fall back to the uptrend / reversal
        # branches. The reversal branch was added so the strategy can fade
        # short-term mean-reverting noise without override needing.
        if return5 > scoring.momentum_short_spike_threshold:
            score -= scoring.momentum_short_spike_penalty
        elif return5 > scoring.momentum_short_uptrend_threshold:
            score += scoring.momentum_short_uptrend_bonus
        elif return5 <= scoring.short_reversal_threshold:
            score += scoring.short_reversal_bonus
        return float(score)

    @staticmethod
    def _score_risk(
        volatility60: float,
        drawdown60: float,
        scoring: EtfScoringConfig,
    ) -> float:
        score = scoring.risk_baseline
        score -= np.clip(
            volatility60 * scoring.risk_volatility_multiplier,
            scoring.risk_volatility_penalty_floor,
            scoring.risk_volatility_penalty_ceiling,
        )
        score += np.clip(
            drawdown60 * scoring.risk_drawdown_multiplier,
            scoring.risk_drawdown_floor,
            scoring.risk_drawdown_ceiling,
        )
        return float(score)

    @staticmethod
    def _score_premium(
        overlay: Optional[EtfOverlay],
        scoring: EtfScoringConfig,
    ) -> float:
        if overlay is None or overlay.premium is None:
            return 0.0
        premium = overlay.premium
        if premium >= scoring.premium_hard_threshold:
            return scoring.premium_hard_penalty
        if premium >= scoring.premium_soft_threshold:
            return scoring.premium_soft_penalty
        if premium <= scoring.premium_discount_threshold:
            return scoring.premium_discount_bonus
        return 0.0

    @staticmethod
    def _period_return(series: pd.Series, days: int) -> float:
        if len(series) <= days:
            return 0.0
        previous = float(series.iloc[-days - 1])
        latest = float(series.iloc[-1])
        if previous <= 0:
            return 0.0
        return latest / previous - 1.0

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> Optional[float]:
        """Classic Wilder-style RSI on a daily close series.

        Returns ``None`` when there isn't enough history for one full
        period. Handles the no-loss edge case (RS division-by-zero) by
        returning 100.0 — anything strictly bullish over the window. A
        flat series with zero gain AND zero loss returns 50.0 (neutral).

        Used for the per-position technical-timing panel: <30 = oversold,
        >70 = overbought, by convention. Exposed via ``EtfSignal.rsi14``
        and surfaced in the audit ``score_breakdown`` so the weekly cron
        can backfill forward-return IC against it.
        """

        if series is None or len(series) < period + 1:
            return None
        delta = series.diff().iloc[-period:]
        gain = float(delta.clip(lower=0).mean())
        loss = float(-delta.clip(upper=0).mean())
        if loss <= 0:
            return 100.0 if gain > 0 else 50.0
        rs = gain / loss
        rsi = 100.0 - 100.0 / (1.0 + rs)
        if not np.isfinite(rsi):
            return None
        return float(rsi)

    @staticmethod
    def _bollinger_position(series: pd.Series, period: int = 20) -> Optional[float]:
        """Where the latest close sits between MA20 ± 2σ20.

        Returns a normalised position in [0, 1]:

        * ~0.0 → at or below the lower band (oversold relative to recent vol)
        * 0.5 → exactly on the MA20
        * ~1.0 → at or above the upper band (overbought)

        Values can clip past [0,1] when price has run beyond ±2σ. Returns
        ``None`` when the series is too short.
        """

        if series is None or len(series) < period:
            return None
        window = series.iloc[-period:]
        mean = float(window.mean())
        std = float(window.std(ddof=0))
        if std <= 0:
            return 0.5
        upper = mean + 2 * std
        lower = mean - 2 * std
        if upper == lower:
            return 0.5
        position = (float(series.iloc[-1]) - lower) / (upper - lower)
        if not np.isfinite(position):
            return None
        return float(position)

    @staticmethod
    def _prepare_prices(price_matrix: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(price_matrix, pd.DataFrame):
            raise ValueError("price_matrix must be a pandas DataFrame")
        prices = price_matrix.apply(pd.to_numeric, errors="coerce").sort_index()
        return prices.ffill().dropna(how="all")
