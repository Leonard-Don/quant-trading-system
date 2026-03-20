"""Cross-market hedge portfolio construction utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import pandas as pd

from .asset_universe import AssetSide, AssetSpec


@dataclass(frozen=True)
class HedgePortfolioLeg:
    side: AssetSide
    assets: List[AssetSpec]

    @property
    def total_weight(self) -> float:
        return float(sum(asset.weight for asset in self.assets))

    def weight_map(self) -> Dict[str, float]:
        return {asset.symbol: float(asset.weight) for asset in self.assets}


class HedgePortfolioBuilder:
    """Build long/short composite legs and diagnostics for cross-market baskets."""

    def __init__(self, asset_specs: Iterable[AssetSpec]):
        assets = list(asset_specs)
        self.long_leg = HedgePortfolioLeg(
            side=AssetSide.LONG,
            assets=[asset for asset in assets if asset.side == AssetSide.LONG],
        )
        self.short_leg = HedgePortfolioLeg(
            side=AssetSide.SHORT,
            assets=[asset for asset in assets if asset.side == AssetSide.SHORT],
        )

    @staticmethod
    def _weighted_returns(
        returns: pd.DataFrame,
        assets: Iterable[AssetSpec],
    ) -> pd.Series:
        series = None
        for asset in assets:
            weighted = returns[asset.symbol] * asset.weight
            series = weighted if series is None else series.add(weighted, fill_value=0.0)
        return series if series is not None else pd.Series(index=returns.index, dtype=float)

    def build_leg_returns(self, returns: pd.DataFrame) -> Dict[str, pd.Series]:
        return {
            "long": self._weighted_returns(returns, self.long_leg.assets),
            "short": self._weighted_returns(returns, self.short_leg.assets),
        }

    def build_asset_contributions(self, returns: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        contributions: Dict[str, Dict[str, Any]] = {}
        for asset in [*self.long_leg.assets, *self.short_leg.assets]:
            weighted_returns = returns[asset.symbol] * asset.weight
            contributions[asset.symbol] = {
                "symbol": asset.symbol,
                "side": asset.side.value,
                "asset_class": asset.asset_class.value,
                "weight": float(asset.weight),
                "currency": asset.currency,
                "cumulative_return": float((1 + weighted_returns).cumprod().iloc[-1] - 1),
                "mean_daily_return": float(weighted_returns.mean()),
                "volatility": float(weighted_returns.std(ddof=0)),
            }
        return contributions

    def summarize_exposures(self, hedge_ratio_series: pd.Series | None = None) -> Dict[str, Any]:
        hedge_ratio_series = (
            hedge_ratio_series
            if hedge_ratio_series is not None and not hedge_ratio_series.empty
            else pd.Series([1.0], dtype=float)
        )
        avg_hedge_ratio = float(hedge_ratio_series.mean())
        min_hedge_ratio = float(hedge_ratio_series.min())
        max_hedge_ratio = float(hedge_ratio_series.max())

        gross_exposure = float(self.long_leg.total_weight + self.short_leg.total_weight * avg_hedge_ratio)
        net_exposure = float(self.long_leg.total_weight - self.short_leg.total_weight * avg_hedge_ratio)

        return {
            "long_weight": float(self.long_leg.total_weight),
            "short_weight": float(self.short_leg.total_weight),
            "effective_short_weight": float(self.short_leg.total_weight * avg_hedge_ratio),
            "gross_exposure": gross_exposure,
            "net_exposure": net_exposure,
            "hedge_ratio": {
                "average": avg_hedge_ratio,
                "min": min_hedge_ratio,
                "max": max_hedge_ratio,
            },
            "leg_weights": {
                "long": self.long_leg.weight_map(),
                "short": self.short_leg.weight_map(),
            },
        }
