"""Asset universe definitions for cross-market strategies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional


class AssetClass(str, Enum):
    US_STOCK = "US_STOCK"
    ETF = "ETF"
    COMMODITY_FUTURES = "COMMODITY_FUTURES"


class AssetSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class AssetSpec:
    symbol: str
    asset_class: AssetClass
    side: AssetSide
    weight: float
    currency: str = "USD"

    def to_dict(self) -> Dict[str, object]:
        return {
            "symbol": self.symbol,
            "asset_class": self.asset_class.value,
            "side": self.side.value,
            "weight": round(float(self.weight), 6),
            "currency": self.currency,
        }


class AssetUniverse:
    """Validate and normalize cross-market asset baskets."""

    SUPPORTED_CURRENCY = "USD"

    def __init__(self, assets: Iterable[Dict[str, object]]):
        self.assets = self._build_specs(list(assets))

    def _build_specs(self, assets: List[Dict[str, object]]) -> List[AssetSpec]:
        if len(assets) < 2:
            raise ValueError("At least two assets are required for cross-market backtesting")

        parsed: List[Dict[str, object]] = []
        for item in assets:
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                raise ValueError("Asset symbol is required")

            try:
                asset_class = AssetClass(str(item.get("asset_class", "")).strip().upper())
            except ValueError as exc:
                raise ValueError(f"Unsupported asset_class for {symbol}") from exc

            try:
                side = AssetSide(str(item.get("side", "")).strip().lower())
            except ValueError as exc:
                raise ValueError(f"Unsupported side for {symbol}") from exc

            weight = item.get("weight")
            if weight is not None:
                weight = float(weight)
                if weight <= 0:
                    raise ValueError(f"Weight must be positive for {symbol}")

            parsed.append(
                {
                    "symbol": symbol,
                    "asset_class": asset_class,
                    "side": side,
                    "weight": weight,
                }
            )

        side_counts = {AssetSide.LONG: 0, AssetSide.SHORT: 0}
        for item in parsed:
            side_counts[item["side"]] += 1

        if side_counts[AssetSide.LONG] == 0 or side_counts[AssetSide.SHORT] == 0:
            raise ValueError("Cross-market basket must include both long and short assets")

        normalized: List[AssetSpec] = []
        for side in (AssetSide.LONG, AssetSide.SHORT):
            side_items = [item for item in parsed if item["side"] == side]
            weights = [item["weight"] for item in side_items]
            if all(weight is None for weight in weights):
                normalized_weights = [1.0 / len(side_items)] * len(side_items)
            else:
                provisional = [float(weight) if weight is not None else 1.0 for weight in weights]
                total = sum(provisional)
                if total <= 0:
                    raise ValueError(f"Invalid weight configuration for {side.value} basket")
                normalized_weights = [weight / total for weight in provisional]

            for item, normalized_weight in zip(side_items, normalized_weights):
                normalized.append(
                    AssetSpec(
                        symbol=item["symbol"],
                        asset_class=item["asset_class"],
                        side=item["side"],
                        weight=normalized_weight,
                        currency=self.SUPPORTED_CURRENCY,
                    )
                )

        return normalized

    def get_assets(self, side: Optional[AssetSide] = None) -> List[AssetSpec]:
        if side is None:
            return list(self.assets)
        return [asset for asset in self.assets if asset.side == side]

    def as_dicts(self) -> List[Dict[str, object]]:
        return [asset.to_dict() for asset in self.assets]
