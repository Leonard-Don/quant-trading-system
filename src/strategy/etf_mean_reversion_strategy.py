"""Mean-reversion ETF strategy — complement to ``EtfRotationStrategy``.

Where the trend-following body of ``EtfRotationStrategy`` rewards assets
above their moving averages, this strategy rewards **oversold-in-uptrend**:
the canonical "buying the dip" thesis. Combining both via
:class:`EtfStrategyBlend` produces a portfolio whose payoffs are less
correlated to a single regime — trend bleeds in chop, MR bleeds in
runaway trends, so a blended signal is more robust.

Scoring philosophy
------------------
A high MR score requires *all* of the following:

1. **Long-term trend intact** — price still above MA200 (we don't catch
   falling knives in multi-year downtrends). Asset below MA200 → score
   pinned to 0 unless ``allow_below_long_trend`` is true.
2. **Short-term capitulation** — price meaningfully below MA20 *or*
   ret5 below the reversal threshold. The more oversold, the higher
   the score.
3. **Risk acceptable** — same vol/drawdown filter as trend strategy.
   Extreme volatility kills any mean-reversion edge.
4. **Recent stabilisation** — return60 not catastrophic. If 60-day
   return < ``min_long_return``, we're in a downtrend, not a dip.

Scoring is bounded [0, 100] like the trend strategy so the blender can
do a clean linear combination without scale mismatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd

from src.strategy.etf_rotation_strategy import (
    EtfAssetConfig,
    EtfOverlay,
    EtfRotationConfig,
    EtfSignal,
    TRADING_DAYS_PER_YEAR,
)


@dataclass(frozen=True)
class EtfMeanReversionConfig:
    """All scoring constants for ``EtfMeanReversionStrategy``.

    Defaults are intentionally conservative — MR strategies degenerate
    into "catch the falling knife" if the long-trend filter is too lax.
    """

    # Long-trend filter
    require_above_ma200: bool = True
    allow_below_long_trend: bool = False
    above_ma200_baseline: float = 30.0

    # Reversal component — score peaks at "deep oversold"
    deviation_window: int = 20            # use price/MA20 - 1
    deviation_clip: float = 0.10           # 10% below MA20 = max signal
    deviation_max_points: float = 40.0     # contribution at clip

    # Short-term capitulation bonus
    short_reversal_threshold: float = -0.04
    short_reversal_bonus: float = 15.0
    deep_capitulation_threshold: float = -0.07
    deep_capitulation_bonus: float = 10.0  # stacks on short_reversal

    # Risk filter (mirrors trend strategy semantics)
    risk_baseline: float = 10.0
    risk_volatility_multiplier: float = 35.0
    risk_volatility_penalty_floor: float = 0.0
    risk_volatility_penalty_ceiling: float = 25.0
    drawdown_floor: float = -25.0
    drawdown_severe_penalty: float = 15.0

    # Anti-falling-knife: refuse score if 60d return is below this
    min_long_return: float = -0.20

    # Premium overlay (same convention as trend strategy)
    premium_hard_threshold: float = 0.05
    premium_hard_penalty: float = -30.0
    premium_soft_threshold: float = 0.02
    premium_soft_penalty: float = -15.0


@dataclass(frozen=True)
class EtfMeanReversionRotationConfig:
    """Wrapper carrying assets + MR scoring config.

    Mirrors ``EtfRotationConfig`` shape so callers can swap strategies
    without restructuring their plumbing.
    """

    assets: List[EtfAssetConfig]
    gross_cap: float = 0.90
    warmup_days: int = 60
    scoring: EtfMeanReversionConfig = field(default_factory=EtfMeanReversionConfig)
    min_score_to_hold: float = 25.0
    min_score_full_hold: float = 40.0

    def __post_init__(self) -> None:
        if self.min_score_full_hold < self.min_score_to_hold:
            raise ValueError("min_score_full_hold must be >= min_score_to_hold")

    def asset_map(self) -> Dict[str, EtfAssetConfig]:
        return {asset.symbol: asset for asset in self.assets}


class EtfMeanReversionStrategy:
    """Daily mean-reversion strategy — same interface as ``EtfRotationStrategy``.

    Exposes ``evaluate(price_matrix, overlays, current_weights)`` returning
    a list of ``EtfSignal`` objects so the blender can mix the two
    strategies' outputs without caring which produced what.
    """

    def __init__(self, config: EtfMeanReversionRotationConfig):
        if not config.assets:
            raise ValueError("EtfMeanReversionRotationConfig.assets must not be empty")
        if not 0.0 < config.gross_cap <= 1.0:
            raise ValueError("gross_cap must be in (0, 1]")
        self.config = config
        self._assets = config.asset_map()

    def evaluate(
        self,
        price_matrix: pd.DataFrame,
        *,
        overlays: Optional[Mapping[str, EtfOverlay]] = None,
        current_weights: Optional[Mapping[str, float]] = None,
    ) -> List[EtfSignal]:
        prices = self._prepare_prices(price_matrix)
        overlays = overlays or {}
        current_weights = current_weights or {}
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
        return self._normalize_signals(signals)

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _build_signal(
        self,
        *,
        symbol: str,
        series: pd.Series,
        overlay: Optional[EtfOverlay],
        current_weight: float,
    ) -> EtfSignal:
        asset = self._assets[symbol]
        scoring = self.config.scoring

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
        drawdown60 = latest / high60 - 1.0 if high60 > 0 else 0.0
        returns = series.pct_change().dropna()

        return5 = self._period_return(series, 5)
        return20 = self._period_return(series, 20)
        return60 = self._period_return(series, 60)
        volatility60 = float(returns.iloc[-60:].std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if not np.isfinite(volatility60):
            volatility60 = 0.0

        reasons: List[str] = []
        # ---- Long-trend gate ----------------------------------------------
        if scoring.require_above_ma200 and ma200 is not None and latest < ma200:
            if not scoring.allow_below_long_trend:
                score = 0.0
                reasons.append("mr_blocked_below_ma200")
                return self._signal(
                    symbol=symbol, latest=latest, ma20=ma20, ma60=ma60, ma200=ma200,
                    trend_long_strength=trend_long_strength,
                    return5=return5, return20=return20, return60=return60,
                    drawdown60=drawdown60, volatility60=volatility60,
                    trend=0.0, momentum=0.0, risk=0.0, premium=0.0,
                    score=score, asset=asset, overlay=overlay,
                    current_weight=current_weight, reasons=reasons,
                )

        # ---- Anti-falling-knife gate --------------------------------------
        if return60 <= scoring.min_long_return:
            reasons.append("mr_blocked_long_return_too_negative")
            return self._signal(
                symbol=symbol, latest=latest, ma20=ma20, ma60=ma60, ma200=ma200,
                trend_long_strength=trend_long_strength,
                return5=return5, return20=return20, return60=return60,
                drawdown60=drawdown60, volatility60=volatility60,
                trend=0.0, momentum=0.0, risk=0.0, premium=0.0,
                score=0.0, asset=asset, overlay=overlay,
                current_weight=current_weight, reasons=reasons,
            )

        # ---- Trend component (long-trend posture) -------------------------
        trend_component = 0.0
        if ma200 is not None and latest > ma200:
            trend_component = scoring.above_ma200_baseline
            reasons.append("mr_long_trend_intact")
        elif ma200 is None and scoring.allow_below_long_trend:
            # No MA200 yet → give a partial baseline so the strategy can
            # warm up before 200 bars accumulate.
            trend_component = scoring.above_ma200_baseline * 0.5

        # ---- Reversal component: deeper below MA20 = better ----------------
        if ma20 > 0:
            deviation = max(0.0, (ma20 - latest) / ma20)
            # Linear scaling up to deviation_clip
            normalised = min(deviation / max(scoring.deviation_clip, 1e-9), 1.0)
            reversal_component = normalised * scoring.deviation_max_points
            if deviation > 0.005:
                reasons.append(f"mr_below_ma20_{deviation:.2%}")
        else:
            reversal_component = 0.0

        # ---- Short-term capitulation bonus (stacking) ---------------------
        momentum_component = 0.0
        if return5 <= scoring.deep_capitulation_threshold:
            momentum_component += scoring.short_reversal_bonus + scoring.deep_capitulation_bonus
            reasons.append("mr_deep_capitulation_ret5")
        elif return5 <= scoring.short_reversal_threshold:
            momentum_component += scoring.short_reversal_bonus
            reasons.append("mr_short_reversal_ret5")

        # ---- Risk filter (penalty only — symmetric with trend strategy) ---
        risk_component = scoring.risk_baseline
        vol_penalty = float(np.clip(
            volatility60 * scoring.risk_volatility_multiplier,
            scoring.risk_volatility_penalty_floor,
            scoring.risk_volatility_penalty_ceiling,
        ))
        risk_component -= vol_penalty
        # Severe drawdown — MR doesn't want maximum drawdown territory either
        if drawdown60 <= scoring.drawdown_floor:
            risk_component -= scoring.drawdown_severe_penalty
            reasons.append("mr_drawdown_severe")

        # ---- Premium overlay (consistent with trend strategy convention) ---
        premium_component = 0.0
        if overlay is not None and overlay.premium is not None:
            premium = overlay.premium
            if premium >= scoring.premium_hard_threshold:
                premium_component = scoring.premium_hard_penalty
            elif premium >= scoring.premium_soft_threshold:
                premium_component = scoring.premium_soft_penalty

        score = float(np.clip(
            trend_component + reversal_component + momentum_component + risk_component + premium_component,
            0.0, 100.0,
        ))

        return self._signal(
            symbol=symbol, latest=latest, ma20=ma20, ma60=ma60, ma200=ma200,
            trend_long_strength=trend_long_strength,
            return5=return5, return20=return20, return60=return60,
            drawdown60=drawdown60, volatility60=volatility60,
            trend=trend_component, momentum=momentum_component + reversal_component,
            risk=risk_component, premium=premium_component,
            score=score, asset=asset, overlay=overlay,
            current_weight=current_weight, reasons=reasons,
        )

    def _signal(
        self, *,
        symbol, latest, ma20, ma60, ma200, trend_long_strength,
        return5, return20, return60, drawdown60, volatility60,
        trend, momentum, risk, premium, score,
        asset, overlay, current_weight, reasons,
    ) -> EtfSignal:
        raw_weight = self._score_to_weight(asset, score)
        target_weight = self._apply_asset_constraints(
            raw_weight=raw_weight, asset=asset, overlay=overlay,
            current_weight=current_weight,
        )
        return EtfSignal(
            symbol=symbol, latest_price=latest, ma20=ma20, ma60=ma60,
            return5=return5, return20=return20, return60=return60,
            drawdown60=drawdown60, volatility60=volatility60,
            trend_score=float(trend), momentum_score=float(momentum),
            risk_score=float(risk), premium_score=float(premium),
            score=score, raw_weight=raw_weight, target_weight=target_weight,
            reasons=reasons, ma200=ma200, trend_long_strength=trend_long_strength,
        )

    def _score_to_weight(self, asset: EtfAssetConfig, score: float) -> float:
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
        return float(np.clip(base_target, 0.0, asset.max_weight))

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

    def _normalize_signals(self, signals: Iterable[EtfSignal]) -> List[EtfSignal]:
        signal_list = list(signals)
        gross = sum(max(s.target_weight, 0.0) for s in signal_list)
        if gross <= self.config.gross_cap or gross <= 0:
            return signal_list
        scale = self.config.gross_cap / gross
        return [replace(s, target_weight=s.target_weight * scale) for s in signal_list]

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


__all__ = [
    "EtfMeanReversionConfig",
    "EtfMeanReversionRotationConfig",
    "EtfMeanReversionStrategy",
]
