"""Cross-market strategy implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd

from .asset_universe import AssetSide, AssetSpec


class CrossMarketStrategy(ABC):
    """Base class for multi-asset cross-market strategies."""

    name: str = "cross_market_strategy"

    @abstractmethod
    def generate_cross_signals(
        self,
        price_matrix: pd.DataFrame,
        asset_specs: List[AssetSpec],
        parameters: Dict[str, float],
    ) -> pd.DataFrame:
        """Generate spread, z-score and target position signals."""

    @staticmethod
    def _build_leg_series(price_matrix: pd.DataFrame, assets: Iterable[AssetSpec]) -> pd.Series:
        series = None
        for asset in assets:
            normalized = price_matrix[asset.symbol] / price_matrix[asset.symbol].iloc[0]
            weighted = normalized * asset.weight
            series = weighted if series is None else series.add(weighted, fill_value=0.0)
        return series if series is not None else pd.Series(index=price_matrix.index, dtype=float)


class SpreadZScoreStrategy(CrossMarketStrategy):
    """Z-score mean reversion strategy on long-short composite spread."""

    name = "spread_zscore"

    def generate_cross_signals(
        self,
        price_matrix: pd.DataFrame,
        asset_specs: List[AssetSpec],
        parameters: Dict[str, float],
    ) -> pd.DataFrame:
        lookback = int(parameters.get("lookback", 20))
        entry_threshold = float(parameters.get("entry_threshold", 1.5))
        exit_threshold = float(parameters.get("exit_threshold", 0.5))
        construction_mode = str(parameters.get("construction_mode", "equal_weight")).strip().lower()

        if lookback < 5:
            raise ValueError("lookback must be at least 5")
        if exit_threshold >= entry_threshold:
            raise ValueError("exit_threshold must be smaller than entry_threshold")
        if construction_mode not in {"equal_weight", "ols_hedge"}:
            raise ValueError(f"Unsupported construction_mode: {construction_mode}")

        long_assets = [asset for asset in asset_specs if asset.side == AssetSide.LONG]
        short_assets = [asset for asset in asset_specs if asset.side == AssetSide.SHORT]

        long_leg = self._build_leg_series(price_matrix, long_assets)
        short_leg = self._build_leg_series(price_matrix, short_assets)
        hedge_ratio = pd.Series(index=price_matrix.index, data=1.0, dtype=float)
        if construction_mode == "ols_hedge":
            hedge_ratio = self._rolling_ols_hedge_ratio(
                long_leg=long_leg,
                short_leg=short_leg,
                lookback=lookback,
            )
        spread = long_leg - hedge_ratio * short_leg

        rolling_mean = spread.rolling(lookback).mean()
        rolling_std = spread.rolling(lookback).std().replace(0, float("nan"))
        z_score = ((spread - rolling_mean) / rolling_std).astype(float).fillna(0.0)

        signal = pd.Series(index=price_matrix.index, data=0, dtype=int)
        signal[z_score >= entry_threshold] = -1
        signal[z_score <= -entry_threshold] = 1

        position = pd.Series(index=price_matrix.index, data=0, dtype=int)
        current_position = 0
        for idx in position.index:
            z_val = float(z_score.loc[idx])
            proposed_signal = int(signal.loc[idx])
            if proposed_signal != 0:
                current_position = proposed_signal
            elif abs(z_val) <= exit_threshold:
                current_position = 0
            position.loc[idx] = current_position

        return pd.DataFrame(
            {
                "long_leg": long_leg,
                "short_leg": short_leg,
                "hedge_ratio": hedge_ratio,
                "spread": spread,
                "z_score": z_score,
                "signal": signal,
                "position": position,
            },
            index=price_matrix.index,
        )

    @staticmethod
    def _rolling_ols_hedge_ratio(
        long_leg: pd.Series,
        short_leg: pd.Series,
        lookback: int,
    ) -> pd.Series:
        ratios = []
        last_ratio = 1.0

        for idx in range(len(long_leg)):
            if idx + 1 < lookback:
                ratios.append(last_ratio)
                continue

            long_window = long_leg.iloc[idx + 1 - lookback:idx + 1]
            short_window = short_leg.iloc[idx + 1 - lookback:idx + 1]
            x = short_window.values.astype(float)
            y = long_window.values.astype(float)

            if np.std(x) == 0:
                ratios.append(last_ratio)
                continue

            design = np.column_stack([np.ones(len(x)), x])
            beta = np.linalg.lstsq(design, y, rcond=None)[0][1]
            last_ratio = float(beta) if np.isfinite(beta) and beta > 0 else last_ratio
            ratios.append(last_ratio)

        return pd.Series(ratios, index=long_leg.index, dtype=float)
