"""ETF rotation target-weight strategy.

This module is intentionally pure and broker-agnostic. It converts a price
matrix into daily target weights that can be consumed by PortfolioBacktester.
Cash is implicit: ETF weights may sum to less than one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


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
class EtfRotationConfig:
    """Global strategy configuration."""

    assets: List[EtfAssetConfig]
    gross_cap: float = 0.90
    warmup_days: int = 60
    annualized_vol_target: float = 0.20
    min_score_to_hold: float = 25.0

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
    ) -> pd.DataFrame:
        """Return target weights for every date in `price_matrix`.

        The signature matches PortfolioBacktester expectations. Optional
        overlays/current weights are useful for daily live runs; backtests can
        omit them.
        """

        prices = self._prepare_prices(price_matrix)
        weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        overlays = overlays or {}
        current_weights = current_weights or {}

        for idx in range(len(prices)):
            if idx < self.config.warmup_days:
                continue
            window = prices.iloc[: idx + 1]
            signals = self.evaluate(window, overlays=overlays, current_weights=current_weights)
            row = {signal.symbol: signal.target_weight for signal in signals}
            for symbol, value in row.items():
                if symbol in weights.columns:
                    weights.iat[idx, weights.columns.get_loc(symbol)] = value

        return weights.fillna(0.0)

    def evaluate(
        self,
        price_matrix: pd.DataFrame,
        *,
        overlays: Optional[Mapping[str, EtfOverlay]] = None,
        current_weights: Optional[Mapping[str, float]] = None,
    ) -> List[EtfSignal]:
        """Evaluate the latest row of a price matrix and return ETF signals."""

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

        trend_score, trend_reasons = self._score_trend(latest, ma20, ma60)
        momentum_score = self._score_momentum(return5, return20, return60)
        risk_score = self._score_risk(volatility60, drawdown60)
        premium_score = self._score_premium(overlay)
        score = float(np.clip(trend_score + momentum_score + risk_score + premium_score, 0.0, 100.0))

        raw_weight = self._score_to_weight(asset, score, latest, ma60)
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
        normalized: List[EtfSignal] = []
        for signal in signal_list:
            normalized.append(
                EtfSignal(
                    **{
                        **signal.__dict__,
                        "target_weight": signal.target_weight * scale,
                    }
                )
            )
        return normalized

    def _score_to_weight(self, asset: EtfAssetConfig, score: float, latest: float, ma60: float) -> float:
        if score < self.config.min_score_to_hold or latest < ma60:
            return 0.0
        score_fraction = np.clip(score / 100.0, 0.0, 1.0)
        vol_scaled_cap = asset.max_weight
        return float(np.clip(max(asset.base_weight, asset.max_weight * score_fraction), 0.0, vol_scaled_cap))

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
        return float(np.clip(target, 0.0, asset.max_weight))

    @staticmethod
    def _score_trend(latest: float, ma20: float, ma60: float) -> tuple[float, List[str]]:
        reasons: List[str] = []
        score = 0.0
        if latest > ma20:
            score += 20.0
            reasons.append("price_above_ma20")
        if latest > ma60:
            score += 20.0
            reasons.append("price_above_ma60")
        if ma20 > ma60:
            score += 20.0
            reasons.append("ma20_above_ma60")
        else:
            score -= 10.0
            reasons.append("ma20_not_above_ma60")
        return score, reasons

    @staticmethod
    def _score_momentum(return5: float, return20: float, return60: float) -> float:
        score = 0.0
        score += np.clip(return20 * 250.0, -20.0, 25.0)
        score += np.clip(return60 * 120.0, -20.0, 20.0)
        if return5 > 0.08:
            score -= 10.0  # avoid chasing short-term spikes
        elif return5 > 0:
            score += 5.0
        return float(score)

    @staticmethod
    def _score_risk(volatility60: float, drawdown60: float) -> float:
        score = 15.0
        score -= np.clip(volatility60 * 35.0, 0.0, 25.0)
        score += np.clip(drawdown60 * 60.0, -15.0, 0.0)
        return float(score)

    @staticmethod
    def _score_premium(overlay: Optional[EtfOverlay]) -> float:
        if overlay is None or overlay.premium is None:
            return 0.0
        premium = overlay.premium
        if premium >= 0.05:
            return -30.0
        if premium >= 0.02:
            return -18.0
        if premium <= -0.01:
            return 5.0
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
