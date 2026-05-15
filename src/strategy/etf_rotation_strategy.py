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

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252

# Shared default — keeps live (``daily_etf_signal``) and backtest
# (``scripts/backtest_etf_rotation``) on the same rebalance threshold.
DEFAULT_REBALANCE_THRESHOLD = 0.03


@dataclass(frozen=True)
class EtfAssetConfig:
    """Configuration for one ETF in the rotation universe."""

    symbol: str
    name: str = ""
    category: str = ""
    min_weight: float = 0.0
    max_weight: float = 0.30
    base_weight: float = 0.0


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
    """

    # Trend (above/below MA points)
    trend_above_ma20_points: float = 20.0
    trend_above_ma60_points: float = 20.0
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


@dataclass(frozen=True)
class EtfRotationConfig:
    """Global strategy configuration.

    ``min_score_to_hold`` is the bottom of a smooth ramp: scores at or below
    it produce zero weight, scores at ``min_score_full_hold`` reach the full
    score-scaled cap. The two together stop the strategy from snapping
    in/out of a position when the score wobbles by 0.1 around a hard cutoff.
    """

    assets: List[EtfAssetConfig]
    gross_cap: float = 0.90
    warmup_days: int = 60
    annualized_vol_target: Optional[float] = 0.20
    min_score_to_hold: float = 25.0
    min_score_full_hold: float = 35.0
    enable_vol_targeting: bool = False
    scoring: EtfScoringConfig = field(default_factory=EtfScoringConfig)
    scoring_mode: str = "absolute"  # "absolute" | "cross_sectional"

    def __post_init__(self) -> None:
        if self.min_score_full_hold < self.min_score_to_hold:
            raise ValueError(
                "min_score_full_hold must be >= min_score_to_hold"
            )
        if self.scoring_mode not in {"absolute", "cross_sectional"}:
            raise ValueError(
                f"scoring_mode must be 'absolute' or 'cross_sectional', got {self.scoring_mode!r}"
            )

    def asset_map(self) -> Dict[str, EtfAssetConfig]:
        return {asset.symbol: asset for asset in self.assets}


@dataclass(frozen=True)
class EtfSignal:
    """Signal and feature snapshot for a single ETF on one date."""

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
    reasons: List[str] = field(default_factory=list)


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
                window, overlays=overlays, current_weights=current_weights
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
    ) -> List[EtfSignal]:
        """Evaluate the latest row of a price matrix and return ETF signals.

        The returned signals reflect the same-day score (no lag). Callers
        that need a backtest-style lag should use ``generate_signals``.
        """

        prices = self._prepare_prices(price_matrix)
        return self._evaluate_prepared(
            prices, overlays=overlays or {}, current_weights=current_weights or {}
        )

    def _evaluate_prepared(
        self,
        prices: pd.DataFrame,
        *,
        overlays: Mapping[str, EtfOverlay],
        current_weights: Mapping[str, float],
    ) -> List[EtfSignal]:
        signals: List[EtfSignal] = []
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

        return self._normalize_signals(signals)

    def _apply_cross_sectional_scoring(
        self,
        signals: List[EtfSignal],
        overlays: Mapping[str, EtfOverlay],
        current_weights: Mapping[str, float],
    ) -> List[EtfSignal]:
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
        codes = [s.symbol for s in signals]
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

        adapted: List[EtfSignal] = []
        for i, sig in enumerate(signals):
            asset = self._assets[sig.symbol]
            new_score = float(composite[i])
            new_raw = self._score_to_weight(asset, new_score, sig.latest_price, sig.ma60, sig.volatility60)
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
        high60 = float(series.iloc[-60:].max())
        returns = series.pct_change().dropna()

        return5 = self._period_return(series, 5)
        return20 = self._period_return(series, 20)
        return60 = self._period_return(series, 60)
        drawdown60 = latest / high60 - 1.0 if high60 > 0 else 0.0
        volatility60 = float(returns.iloc[-60:].std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if not np.isfinite(volatility60):
            volatility60 = 0.0

        scoring = self.config.scoring
        trend_score, trend_reasons = self._score_trend(latest, ma20, ma60, scoring)
        momentum_score = self._score_momentum(return5, return20, return60, scoring)
        risk_score = self._score_risk(volatility60, drawdown60, scoring)
        premium_score = self._score_premium(overlay, scoring)
        score = float(np.clip(trend_score + momentum_score + risk_score + premium_score, 0.0, 100.0))

        raw_weight = self._score_to_weight(asset, score, latest, ma60, volatility60)
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
        )

    def _normalize_signals(self, signals: Iterable[EtfSignal]) -> List[EtfSignal]:
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
    ) -> float:
        if latest < ma60:
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
        base_target = max(asset.base_weight, asset.max_weight * score_fraction) * ramp_weight

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
    ) -> tuple[float, List[str]]:
        reasons: List[str] = []
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
        if return5 > scoring.momentum_short_spike_threshold:
            score -= scoring.momentum_short_spike_penalty
        elif return5 > scoring.momentum_short_uptrend_threshold:
            score += scoring.momentum_short_uptrend_bonus
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
    def _prepare_prices(price_matrix: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(price_matrix, pd.DataFrame):
            raise ValueError("price_matrix must be a pandas DataFrame")
        prices = price_matrix.apply(pd.to_numeric, errors="coerce").sort_index()
        return prices.ffill().dropna(how="all")
