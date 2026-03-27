"""Execution routing helpers for cross-market baskets."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Any, Dict, Iterable, List

from .asset_universe import AssetSpec


@dataclass(frozen=True)
class ExecutionRoute:
    symbol: str
    side: str
    asset_class: str
    weight: float
    adjusted_weight: float
    capital_fraction: float
    target_notional: float
    reference_price: float
    target_quantity: float
    rounded_quantity: int
    estimated_fill_notional: float
    residual_notional: float
    residual_fraction: float
    capacity_band: str
    avg_daily_volume: float
    avg_daily_notional: float
    adv_usage: float | None
    liquidity_band: str
    margin_rate: float
    margin_requirement: float
    market: str
    venue: str
    execution_channel: str
    currency: str
    settlement: str
    lot_size: int
    preferred_provider: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "asset_class": self.asset_class,
            "weight": round(float(self.weight), 6),
            "adjusted_weight": round(float(self.adjusted_weight), 6),
            "capital_fraction": round(float(self.capital_fraction), 6),
            "target_notional": round(float(self.target_notional), 2),
            "reference_price": round(float(self.reference_price), 4),
            "target_quantity": round(float(self.target_quantity), 4),
            "rounded_quantity": int(self.rounded_quantity),
            "estimated_fill_notional": round(float(self.estimated_fill_notional), 2),
            "residual_notional": round(float(self.residual_notional), 2),
            "residual_fraction": round(float(self.residual_fraction), 6),
            "capacity_band": self.capacity_band,
            "avg_daily_volume": round(float(self.avg_daily_volume), 2),
            "avg_daily_notional": round(float(self.avg_daily_notional), 2),
            "adv_usage": round(float(self.adv_usage), 6) if self.adv_usage is not None else None,
            "liquidity_band": self.liquidity_band,
            "margin_rate": round(float(self.margin_rate), 6),
            "margin_requirement": round(float(self.margin_requirement), 2),
            "market": self.market,
            "venue": self.venue,
            "execution_channel": self.execution_channel,
            "currency": self.currency,
            "settlement": self.settlement,
            "lot_size": self.lot_size,
            "preferred_provider": self.preferred_provider,
        }


class ExecutionRouter:
    """Build research-grade execution batches for cross-market baskets."""

    def __init__(
        self,
        asset_specs: Iterable[AssetSpec],
        *,
        initial_capital: float = 100000.0,
        avg_hedge_ratio: float = 1.0,
        latest_prices: Dict[str, float] | None = None,
        liquidity_snapshots: Dict[str, Dict[str, float]] | None = None,
    ):
        self.asset_specs = list(asset_specs)
        self.initial_capital = float(initial_capital)
        self.avg_hedge_ratio = float(avg_hedge_ratio)
        self.latest_prices = latest_prices or {}
        self.liquidity_snapshots = liquidity_snapshots or {}

    def build_plan(self) -> Dict[str, Any]:
        plan = self._build_plan_core(self.initial_capital)
        plan["execution_stress"] = self._build_stress_scenarios()
        return plan

    def _build_plan_core(self, capital: float) -> Dict[str, Any]:
        effective_weights: List[float] = []
        for asset in self.asset_specs:
            multiplier = self.avg_hedge_ratio if asset.side.value == "short" else 1.0
            effective_weights.append(float(asset.weight) * multiplier)

        gross_weight = sum(abs(weight) for weight in effective_weights) or 1.0
        routes: List[ExecutionRoute] = []
        for asset, effective_weight in zip(self.asset_specs, effective_weights):
            capital_fraction = float(abs(effective_weight) / gross_weight)
            target_notional = float(capital * capital_fraction)
            reference_price = float(self.latest_prices.get(asset.symbol) or 1.0)
            lot_size = max(int(asset.lot_size), 1)
            target_quantity = target_notional / reference_price if reference_price > 0 else 0.0
            rounded_lots = max(int(round(target_quantity / lot_size)), 1) if target_quantity > 0 else 0
            rounded_quantity = rounded_lots * lot_size
            estimated_fill_notional = float(rounded_quantity * reference_price)
            residual_notional = abs(estimated_fill_notional - target_notional)
            residual_fraction = residual_notional / target_notional if target_notional > 0 else 0.0
            liquidity = self.liquidity_snapshots.get(asset.symbol, {})
            avg_daily_volume = float(liquidity.get("avg_daily_volume") or 0.0)
            avg_daily_notional = float(liquidity.get("avg_daily_notional") or 0.0)
            adv_usage = target_notional / avg_daily_notional if avg_daily_notional > 0 else None
            margin_rate = self._margin_rate(asset.execution_channel, asset.side.value)
            margin_requirement = float(target_notional * margin_rate)

            routes.append(
                ExecutionRoute(
                    symbol=asset.symbol,
                    side=asset.side.value,
                    asset_class=asset.asset_class.value,
                    weight=float(asset.weight),
                    adjusted_weight=float(effective_weight),
                    capital_fraction=capital_fraction,
                    target_notional=target_notional,
                    reference_price=reference_price,
                    target_quantity=target_quantity,
                    rounded_quantity=rounded_quantity,
                    estimated_fill_notional=estimated_fill_notional,
                    residual_notional=residual_notional,
                    residual_fraction=residual_fraction,
                    capacity_band=self._capacity_band(asset.execution_channel, target_notional),
                    avg_daily_volume=avg_daily_volume,
                    avg_daily_notional=avg_daily_notional,
                    adv_usage=adv_usage,
                    liquidity_band=self._liquidity_band(adv_usage),
                    margin_rate=margin_rate,
                    margin_requirement=margin_requirement,
                    market=asset.market,
                    venue=asset.venue,
                    execution_channel=asset.execution_channel,
                    currency=asset.currency,
                    settlement=asset.settlement,
                    lot_size=lot_size,
                    preferred_provider=asset.preferred_provider,
                )
            )

        batches = defaultdict(list)
        for route in routes:
            key = (route.execution_channel, route.venue, route.currency, route.preferred_provider)
            batches[key].append(route)

        batch_records: List[Dict[str, Any]] = []
        for (execution_channel, venue, currency, provider), batch_routes in batches.items():
            batch_records.append(
                {
                    "route_key": f"{execution_channel}:{venue}:{currency}:{provider}",
                    "execution_channel": execution_channel,
                    "venue": venue,
                    "currency": currency,
                    "preferred_provider": provider,
                    "order_count": len(batch_routes),
                    "symbols": [route.symbol for route in batch_routes],
                    "long_symbols": [route.symbol for route in batch_routes if route.side == "long"],
                    "short_symbols": [route.symbol for route in batch_routes if route.side == "short"],
                    "gross_weight": round(sum(abs(route.weight) for route in batch_routes), 6),
                    "adjusted_weight": round(sum(abs(route.adjusted_weight) for route in batch_routes), 6),
                    "capital_fraction": round(sum(route.capital_fraction for route in batch_routes), 6),
                    "target_notional": round(sum(route.target_notional for route in batch_routes), 2),
                    "estimated_fill_notional": round(sum(route.estimated_fill_notional for route in batch_routes), 2),
                    "residual_notional": round(sum(route.residual_notional for route in batch_routes), 2),
                    "capacity_band": self._batch_capacity_band(
                        execution_channel,
                        sum(route.target_notional for route in batch_routes),
                    ),
                    "avg_daily_notional": round(sum(route.avg_daily_notional for route in batch_routes), 2),
                    "adv_usage": round(
                        (
                            sum(route.target_notional for route in batch_routes)
                            / sum(route.avg_daily_notional for route in batch_routes)
                        ),
                        6,
                    ) if sum(route.avg_daily_notional for route in batch_routes) > 0 else None,
                    "liquidity_band": self._liquidity_band(
                        (
                            sum(route.target_notional for route in batch_routes)
                            / sum(route.avg_daily_notional for route in batch_routes)
                        ) if sum(route.avg_daily_notional for route in batch_routes) > 0 else None
                    ),
                    "margin_requirement": round(sum(route.margin_requirement for route in batch_routes), 2),
                }
            )

        batch_records.sort(key=lambda item: (item["execution_channel"], item["venue"], item["route_key"]))
        total_notional = sum(route.target_notional for route in routes) or 1.0
        max_route_fraction = max((route.capital_fraction for route in routes), default=0.0)
        max_batch_fraction = max(
            (batch["target_notional"] / total_notional for batch in batch_records),
            default=0.0,
        )
        concentration = self._summarize_concentration(routes, batch_records, total_notional)
        sizing_summary = self._summarize_sizing(routes)

        return {
            "route_count": len(routes),
            "initial_capital": round(capital, 2),
            "avg_hedge_ratio": round(self.avg_hedge_ratio, 6),
            "routes": [route.to_dict() for route in routes],
            "batches": batch_records,
            "by_channel": {
                channel: len([route for route in routes if route.execution_channel == channel])
                for channel in sorted({route.execution_channel for route in routes})
            },
            "by_provider": {
                provider: len([route for route in routes if route.preferred_provider == provider])
                for provider in sorted({route.preferred_provider for route in routes})
            },
            "provider_allocation": self._allocation_by(routes, "preferred_provider", total_notional),
            "venue_allocation": self._allocation_by(routes, "venue", total_notional),
            "channel_allocation": self._allocation_by(routes, "execution_channel", total_notional),
            "asset_class_allocation": self._allocation_by(routes, "asset_class", total_notional),
            "largest_route": max(
                [route.to_dict() for route in routes],
                key=lambda route: route["target_notional"],
                default=None,
            ),
            "largest_batch": max(batch_records, key=lambda batch: batch["target_notional"], default=None),
            "max_route_fraction": round(max_route_fraction, 6),
            "max_batch_fraction": round(max_batch_fraction, 6),
            "concentration": concentration,
            "sizing_summary": sizing_summary,
            "liquidity_summary": self._summarize_liquidity(routes, batch_records),
            "margin_summary": self._summarize_margin(routes, capital),
        }

    def _build_stress_scenarios(self) -> Dict[str, Any]:
        scenarios = []
        for multiplier in (0.5, 1.0, 1.5, 2.0):
            stressed_capital = self.initial_capital * multiplier
            scenario = self._build_plan_core(stressed_capital)
            scenarios.append(
                {
                    "label": f"{multiplier:.1f}x",
                    "capital_multiplier": round(multiplier, 2),
                    "initial_capital": round(stressed_capital, 2),
                    "route_count": scenario["route_count"],
                    "batch_count": len(scenario.get("batches", [])),
                    "concentration_level": scenario.get("concentration", {}).get("level", "balanced"),
                    "concentration_reason": scenario.get("concentration", {}).get("reason", ""),
                    "max_batch_fraction": scenario.get("max_batch_fraction", 0.0),
                    "max_route_fraction": scenario.get("max_route_fraction", 0.0),
                    "capacity_counts": scenario.get("sizing_summary", {}).get("capacity_counts", {}),
                    "lot_efficiency": scenario.get("sizing_summary", {}).get("lot_efficiency", 1.0),
                    "total_residual_notional": scenario.get("sizing_summary", {}).get("total_residual_notional", 0.0),
                    "largest_batch_notional": (scenario.get("largest_batch") or {}).get("target_notional", 0.0),
                    "max_adv_usage": scenario.get("liquidity_summary", {}).get("max_adv_usage", 0.0),
                    "liquidity_level": scenario.get("liquidity_summary", {}).get("level", "unknown"),
                    "liquidity_reason": scenario.get("liquidity_summary", {}).get("reason", ""),
                    "margin_utilization": scenario.get("margin_summary", {}).get("utilization", 0.0),
                    "margin_level": scenario.get("margin_summary", {}).get("level", "manageable"),
                    "margin_reason": scenario.get("margin_summary", {}).get("reason", ""),
                }
            )

        worst = max(
            scenarios,
            key=lambda item: (
                {"balanced": 0, "moderate": 1, "high": 2}.get(item["concentration_level"], 0),
                {"unknown": 0, "comfortable": 1, "watch": 2, "stretched": 3}.get(item["liquidity_level"], 0),
                {"manageable": 0, "elevated": 1, "aggressive": 2}.get(item["margin_level"], 0),
                item["largest_batch_notional"],
            ),
            default=None,
        )
        return {
            "scenarios": scenarios,
            "worst_case": worst,
        }

    @staticmethod
    def _capacity_band(execution_channel: str, target_notional: float) -> str:
        if execution_channel == "futures":
            if target_notional <= 250000:
                return "light"
            if target_notional <= 1000000:
                return "moderate"
            return "heavy"
        if target_notional <= 100000:
            return "light"
        if target_notional <= 500000:
            return "moderate"
        return "heavy"

    def _batch_capacity_band(self, execution_channel: str, target_notional: float) -> str:
        if execution_channel == "futures":
            if target_notional <= 500000:
                return "light"
            if target_notional <= 2000000:
                return "moderate"
            return "heavy"
        if target_notional <= 250000:
            return "light"
        if target_notional <= 1000000:
            return "moderate"
        return "heavy"

    @staticmethod
    def _liquidity_band(adv_usage: float | None) -> str:
        if adv_usage is None:
            return "unknown"
        if adv_usage <= 0.02:
            return "comfortable"
        if adv_usage <= 0.05:
            return "watch"
        return "stretched"

    @staticmethod
    def _margin_rate(execution_channel: str, side: str) -> float:
        if execution_channel == "futures":
            return 0.12
        if side == "short":
            return 0.5
        return 1.0

    @staticmethod
    def _allocation_by(routes: List[ExecutionRoute], field: str, total_notional: float) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}
        for route in routes:
            key = str(getattr(route, field))
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "route_count": 0,
                    "symbols": [],
                    "capital_fraction": 0.0,
                    "target_notional": 0.0,
                },
            )
            bucket["route_count"] += 1
            bucket["symbols"].append(route.symbol)
            bucket["capital_fraction"] += float(route.capital_fraction)
            bucket["target_notional"] += float(route.target_notional)

        allocations = []
        for bucket in buckets.values():
            allocations.append(
                {
                    "key": bucket["key"],
                    "route_count": bucket["route_count"],
                    "symbols": bucket["symbols"],
                    "capital_fraction": round(bucket["capital_fraction"], 6),
                    "target_notional": round(bucket["target_notional"], 2),
                    "notional_share": round(bucket["target_notional"] / total_notional, 6),
                }
            )

        allocations.sort(key=lambda item: (-item["target_notional"], item["key"]))
        return allocations

    @staticmethod
    def _summarize_sizing(routes: List[ExecutionRoute]) -> Dict[str, Any]:
        total_target = sum(route.target_notional for route in routes)
        total_fill = sum(route.estimated_fill_notional for route in routes)
        total_residual = sum(route.residual_notional for route in routes)
        lot_efficiency = (total_target - total_residual) / total_target if total_target > 0 else 1.0
        max_residual_route = max(routes, key=lambda route: route.residual_fraction, default=None)
        capacity_counts = {
            band: len([route for route in routes if route.capacity_band == band])
            for band in ("light", "moderate", "heavy")
        }
        return {
            "total_target_notional": round(total_target, 2),
            "total_estimated_fill_notional": round(total_fill, 2),
            "total_residual_notional": round(total_residual, 2),
            "lot_efficiency": round(lot_efficiency, 6),
            "capacity_counts": capacity_counts,
            "max_residual_route": max_residual_route.to_dict() if max_residual_route else None,
        }

    @staticmethod
    def _summarize_liquidity(
        routes: List[ExecutionRoute],
        batch_records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        route_adv_values = [float(route.adv_usage) for route in routes if route.adv_usage is not None]
        batch_adv_values = [
            float(batch["adv_usage"])
            for batch in batch_records
            if batch.get("adv_usage") is not None
        ]
        if not route_adv_values:
            return {
                "level": "unknown",
                "reason": "missing ADV inputs",
                "max_adv_usage": 0.0,
                "median_adv_usage": 0.0,
                "batch_max_adv_usage": 0.0,
                "stretched_route_count": 0,
                "watch_route_count": 0,
                "routes_with_liquidity": 0,
                "largest_adv_route": None,
            }

        max_adv_usage = max(route_adv_values)
        median_adv_usage = float(sorted(route_adv_values)[len(route_adv_values) // 2])
        batch_max_adv_usage = max(batch_adv_values) if batch_adv_values else 0.0
        stretched_route_count = len([value for value in route_adv_values if value > 0.05])
        watch_route_count = len([value for value in route_adv_values if value > 0.02])

        if max_adv_usage > 0.08 or batch_max_adv_usage > 0.12:
            level = "stretched"
        elif max_adv_usage > 0.04 or batch_max_adv_usage > 0.08:
            level = "watch"
        else:
            level = "comfortable"

        largest_adv_route = max(
            [route.to_dict() for route in routes if route.adv_usage is not None],
            key=lambda route: route.get("adv_usage") or 0.0,
            default=None,
        )

        reason_parts = [
            f"max ADV usage {round(max_adv_usage * 100, 2)}%",
            f"batch max {round(batch_max_adv_usage * 100, 2)}%",
        ]
        if largest_adv_route:
            reason_parts.append(f"tightest route {largest_adv_route['symbol']}")

        return {
            "level": level,
            "reason": ", ".join(reason_parts),
            "max_adv_usage": round(max_adv_usage, 6),
            "median_adv_usage": round(median_adv_usage, 6),
            "batch_max_adv_usage": round(batch_max_adv_usage, 6),
            "stretched_route_count": stretched_route_count,
            "watch_route_count": watch_route_count,
            "routes_with_liquidity": len(route_adv_values),
            "largest_adv_route": largest_adv_route,
        }

    @staticmethod
    def _summarize_margin(
        routes: List[ExecutionRoute],
        capital: float,
    ) -> Dict[str, Any]:
        total_margin_requirement = float(sum(route.margin_requirement for route in routes))
        gross_notional = float(sum(route.target_notional for route in routes))
        utilization = total_margin_requirement / capital if capital > 0 else 0.0
        leverage_ratio = gross_notional / capital if capital > 0 else 0.0
        short_notional = float(sum(route.target_notional for route in routes if route.side == "short"))
        futures_notional = float(sum(route.target_notional for route in routes if route.execution_channel == "futures"))
        max_margin_route = max(
            [route.to_dict() for route in routes],
            key=lambda route: route.get("margin_requirement") or 0.0,
            default=None,
        )

        if utilization > 1.35 or leverage_ratio > 2.0:
            level = "aggressive"
        elif utilization > 1.0 or leverage_ratio > 1.5:
            level = "elevated"
        else:
            level = "manageable"

        reason_parts = [
            f"margin {round(utilization * 100, 1)}%",
            f"gross leverage {round(leverage_ratio, 2)}x",
        ]
        if max_margin_route:
            reason_parts.append(f"largest margin route {max_margin_route['symbol']}")

        return {
            "total_margin_requirement": round(total_margin_requirement, 2),
            "utilization": round(utilization, 6),
            "gross_leverage": round(leverage_ratio, 6),
            "short_notional": round(short_notional, 2),
            "futures_notional": round(futures_notional, 2),
            "level": level,
            "reason": ", ".join(reason_parts),
            "max_margin_route": max_margin_route,
        }

    def _summarize_concentration(
        self,
        routes: List[ExecutionRoute],
        batch_records: List[Dict[str, Any]],
        total_notional: float,
    ) -> Dict[str, Any]:
        provider_allocation = self._allocation_by(routes, "preferred_provider", total_notional)
        venue_allocation = self._allocation_by(routes, "venue", total_notional)
        channel_allocation = self._allocation_by(routes, "execution_channel", total_notional)
        max_route_fraction = max((route.capital_fraction for route in routes), default=0.0)
        max_batch_fraction = max(
            (batch["target_notional"] / total_notional for batch in batch_records),
            default=0.0,
        )

        if max_batch_fraction >= 0.65 or max_route_fraction >= 0.5:
            level = "high"
        elif max_batch_fraction >= 0.45 or max_route_fraction >= 0.35:
            level = "moderate"
        else:
            level = "balanced"

        top_provider = provider_allocation[0] if provider_allocation else None
        top_venue = venue_allocation[0] if venue_allocation else None
        top_channel = channel_allocation[0] if channel_allocation else None

        reason_parts = []
        if top_provider:
            reason_parts.append(
                f"top provider {top_provider['key']} {round(top_provider['notional_share'] * 100, 1)}%"
            )
        if top_venue:
            reason_parts.append(
                f"top venue {top_venue['key']} {round(top_venue['notional_share'] * 100, 1)}%"
            )
        if max_batch_fraction:
            reason_parts.append(f"max batch {round(max_batch_fraction * 100, 1)}%")

        return {
            "level": level,
            "reason": ", ".join(reason_parts) if reason_parts else "balanced routing",
            "top_provider": top_provider,
            "top_venue": top_venue,
            "top_channel": top_channel,
        }
