"""Cross-market backtesting engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.backtest.base_backtester import BaseBacktester
from src.backtest.metrics import (
    calculate_annualized_return,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_var,
    calculate_volatility,
)
from src.data.data_manager import DataManager
from src.trading.cross_market import (
    AssetSide,
    AssetUniverse,
    CrossMarketStrategy,
    ExecutionRouter,
    HedgePortfolioBuilder,
    SpreadZScoreStrategy,
    CointegrationReversionStrategy,
)


class CrossMarketBacktester(BaseBacktester):
    """Backtest long-short cross-market baskets on daily data."""

    STRATEGIES = {
        "spread_zscore": SpreadZScoreStrategy,
        "cointegration_reversion": CointegrationReversionStrategy,
    }

    def __init__(
        self,
        data_manager: Optional[DataManager] = None,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.001,
    ):
        super().__init__(
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        )
        self.data_manager = data_manager or DataManager()

    def run(
        self,
        assets: List[Dict[str, object]],
        strategy_name: str,
        template_context: Optional[Dict[str, Any]] = None,
        allocation_constraints: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        construction_mode: str = "equal_weight",
        min_history_days: int = 60,
        min_overlap_ratio: float = 0.7,
    ) -> Dict[str, Any]:
        if strategy_name not in self.STRATEGIES:
            raise ValueError(f"Unsupported cross-market strategy: {strategy_name}")
        if construction_mode not in {"equal_weight", "ols_hedge"}:
            raise ValueError(f"Unsupported construction_mode: {construction_mode}")
        if min_history_days < 10:
            raise ValueError("min_history_days must be at least 10")
        if not 0 < float(min_overlap_ratio) <= 1:
            raise ValueError("min_overlap_ratio must be between 0 and 1")

        base_universe = AssetUniverse(assets)
        universe, constraint_overlay = self._apply_allocation_constraints(
            base_universe,
            allocation_constraints or {},
        )
        alignment = self._build_price_matrix(
            universe=universe,
            start_date=start_date,
            end_date=end_date,
            min_history_days=min_history_days,
            min_overlap_ratio=min_overlap_ratio,
        )
        price_matrix = alignment["aligned_price_matrix"]

        strategy: CrossMarketStrategy = self.STRATEGIES[strategy_name]()
        signal_frame = strategy.generate_cross_signals(
            price_matrix=price_matrix,
            asset_specs=universe.get_assets(),
            parameters={
                **(parameters or {}),
                "construction_mode": construction_mode,
            },
        )
        results = self._build_results(
            universe=universe,
            price_matrix=price_matrix,
            signal_frame=signal_frame,
            data_alignment=alignment,
            strategy_name=strategy_name,
            parameters=parameters or {},
            construction_mode=construction_mode,
            constraint_overlay=constraint_overlay,
        )
        results["strategy"] = strategy_name
        results["parameters"] = parameters or {}
        results["asset_specs"] = universe.as_dicts()
        results["asset_universe"] = universe.summary()
        results["constraint_overlay"] = constraint_overlay
        if template_context:
            results["template_context"] = template_context
            results["allocation_overlay"] = self._build_allocation_overlay(
                template_context=template_context,
                effective_assets=universe.as_dicts(),
            )
        results["price_matrix_summary"] = {
            "asset_count": len(price_matrix.columns),
            "row_count": len(price_matrix),
            "symbols": list(price_matrix.columns),
            "start_date": price_matrix.index[0].strftime("%Y-%m-%d"),
            "end_date": price_matrix.index[-1].strftime("%Y-%m-%d"),
        }
        return results

    @staticmethod
    def _rebalance_side_weights(
        weights: np.ndarray,
        *,
        min_weight: Optional[float],
        max_weight: Optional[float],
    ) -> np.ndarray:
        size = len(weights)
        if size == 0:
            return weights
        if max_weight is not None and max_weight * size < 1 - 1e-9:
            raise ValueError(
                f"max_single_weight={max_weight:.2f} is infeasible for a basket with {size} assets"
            )
        if min_weight is not None and min_weight * size > 1 + 1e-9:
            raise ValueError(
                f"min_single_weight={min_weight:.2f} is infeasible for a basket with {size} assets"
            )

        adjusted = np.zeros(size, dtype=float)
        locked = np.zeros(size, dtype=bool)
        base_weights = np.array(weights, dtype=float)

        while not locked.all():
            remaining = 1.0 - adjusted[locked].sum()
            if remaining < -1e-9:
                raise ValueError("Allocation constraints produced negative remaining weight")

            free_idx = np.where(~locked)[0]
            if len(free_idx) == 0:
                break

            free_base = base_weights[free_idx]
            base_sum = free_base.sum()
            if base_sum <= 0:
                proposed = np.full(len(free_idx), remaining / len(free_idx))
            else:
                proposed = free_base / base_sum * remaining

            changed = False
            if min_weight is not None:
                low_mask = proposed < min_weight - 1e-9
                if low_mask.any():
                    for idx in free_idx[low_mask]:
                        adjusted[idx] = float(min_weight)
                        locked[idx] = True
                    changed = True

            if max_weight is not None:
                high_mask = proposed > max_weight + 1e-9
                if high_mask.any():
                    for idx in free_idx[high_mask]:
                        adjusted[idx] = float(max_weight)
                        locked[idx] = True
                    changed = True

            if changed:
                continue

            adjusted[free_idx] = proposed
            break

        adjusted = adjusted / adjusted.sum()
        return adjusted

    def _apply_allocation_constraints(
        self,
        universe: AssetUniverse,
        allocation_constraints: Dict[str, Any],
    ) -> tuple[AssetUniverse, Dict[str, Any]]:
        max_single_weight = allocation_constraints.get("max_single_weight")
        min_single_weight = allocation_constraints.get("min_single_weight")

        if max_single_weight is None and min_single_weight is None:
            return universe, {
                "applied": False,
                "constraints": {},
                "binding_assets": [],
                "binding_count": 0,
                "max_delta_weight": 0.0,
                "rows": [],
            }

        constrained_assets: List[Dict[str, Any]] = []
        rows: List[Dict[str, Any]] = []
        binding_assets: List[str] = []

        for side in (AssetSide.LONG, AssetSide.SHORT):
            side_assets = universe.get_assets(side)
            original_weights = np.array([float(asset.weight) for asset in side_assets], dtype=float)
            adjusted_weights = self._rebalance_side_weights(
                original_weights,
                min_weight=float(min_single_weight) if min_single_weight is not None else None,
                max_weight=float(max_single_weight) if max_single_weight is not None else None,
            )
            for asset, adjusted_weight in zip(side_assets, adjusted_weights):
                delta_weight = float(adjusted_weight - asset.weight)
                binding = None
                if max_single_weight is not None and abs(adjusted_weight - float(max_single_weight)) < 1e-6:
                    binding = "max"
                elif min_single_weight is not None and abs(adjusted_weight - float(min_single_weight)) < 1e-6:
                    binding = "min"

                if binding:
                    binding_assets.append(asset.symbol)

                constrained_assets.append(
                    {
                        "symbol": asset.symbol,
                        "asset_class": asset.asset_class.value,
                        "side": asset.side.value,
                        "weight": float(adjusted_weight),
                    }
                )
                rows.append(
                    {
                        "symbol": asset.symbol,
                        "side": asset.side.value,
                        "asset_class": asset.asset_class.value,
                        "base_weight": round(float(asset.weight), 6),
                        "constrained_weight": round(float(adjusted_weight), 6),
                        "delta_weight": round(delta_weight, 6),
                        "binding": binding or "",
                    }
                )

        constrained_universe = AssetUniverse(constrained_assets)
        max_delta = max((abs(float(item["delta_weight"])) for item in rows), default=0.0)
        rows.sort(key=lambda item: (item["side"], -abs(item["delta_weight"]), item["symbol"]))

        return constrained_universe, {
            "applied": True,
            "constraints": {
                "max_single_weight": float(max_single_weight) if max_single_weight is not None else None,
                "min_single_weight": float(min_single_weight) if min_single_weight is not None else None,
            },
            "binding_assets": sorted(set(binding_assets)),
            "binding_count": len(set(binding_assets)),
            "max_delta_weight": round(max_delta, 6),
            "rows": rows,
        }

    @staticmethod
    def _build_allocation_overlay(
        *,
        template_context: Dict[str, Any],
        effective_assets: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        base_assets = template_context.get("base_assets") or []
        raw_bias_assets = template_context.get("raw_bias_assets") or []
        base_lookup = {
            (str(asset.get("symbol", "")).upper(), str(asset.get("side", "")).lower()): asset
            for asset in base_assets
        }
        raw_bias_lookup = {
            (str(asset.get("symbol", "")).upper(), str(asset.get("side", "")).lower()): asset
            for asset in raw_bias_assets
        }
        rows: List[Dict[str, Any]] = []
        for asset in effective_assets:
            key = (str(asset.get("symbol", "")).upper(), str(asset.get("side", "")).lower())
            base_asset = base_lookup.get(key, {})
            raw_bias_asset = raw_bias_lookup.get(key, {})
            base_weight = float(base_asset.get("weight") or 0.0)
            raw_bias_weight = float(raw_bias_asset.get("weight") or base_weight)
            effective_weight = float(asset.get("weight") or 0.0)
            delta_weight = effective_weight - base_weight
            compression_delta = raw_bias_weight - effective_weight
            rows.append(
                {
                    "symbol": asset.get("symbol"),
                    "side": asset.get("side"),
                    "asset_class": asset.get("asset_class"),
                    "base_weight": round(base_weight, 6),
                    "raw_bias_weight": round(raw_bias_weight, 6),
                    "effective_weight": round(effective_weight, 6),
                    "delta_weight": round(delta_weight, 6),
                    "compression_delta": round(compression_delta, 6),
                }
            )

        rows.sort(key=lambda item: (item["side"], -abs(item["delta_weight"]), item["symbol"]))
        max_delta = max((abs(item["delta_weight"]) for item in rows), default=0.0)
        shifted_assets = [item["symbol"] for item in rows if abs(item["delta_weight"]) >= 0.02]
        compressed_rows = [
            item for item in rows if abs(float(item.get("compression_delta") or 0.0)) >= 0.005
        ]
        compressed_rows.sort(key=lambda item: -abs(float(item.get("compression_delta") or 0.0)))
        long_raw_total = sum(
            float(item["raw_bias_weight"]) for item in rows if str(item.get("side")) == "long"
        )
        long_effective_total = sum(
            float(item["effective_weight"]) for item in rows if str(item.get("side")) == "long"
        )
        short_raw_total = sum(
            float(item["raw_bias_weight"]) for item in rows if str(item.get("side")) == "short"
        )
        short_effective_total = sum(
            float(item["effective_weight"]) for item in rows if str(item.get("side")) == "short"
        )
        bias_strength_raw = float(template_context.get("bias_strength_raw") or 0.0)
        bias_strength = float(template_context.get("bias_strength") or 0.0)
        compression_effect = round(bias_strength_raw - bias_strength, 6)
        base_recommendation_score = float(template_context.get("base_recommendation_score") or 0.0)
        recommendation_score = float(
            template_context.get("recommendation_score")
            if template_context.get("recommendation_score") is not None
            else base_recommendation_score
        )
        ranking_penalty = float(template_context.get("ranking_penalty") or 0.0)
        ranking_penalty_reason = template_context.get("ranking_penalty_reason") or ""
        input_reliability_label = template_context.get("input_reliability_label") or "unknown"
        input_reliability_score = float(template_context.get("input_reliability_score") or 0.0)
        input_reliability_lead = template_context.get("input_reliability_lead") or ""
        input_reliability_posture = template_context.get("input_reliability_posture") or ""
        input_reliability_reason = template_context.get("input_reliability_reason") or ""
        input_reliability_action_hint = template_context.get("input_reliability_action_hint") or ""
        department_chaos_label = template_context.get("department_chaos_label") or "unknown"
        department_chaos_score = float(template_context.get("department_chaos_score") or 0.0)
        department_chaos_top_department = template_context.get("department_chaos_top_department") or ""
        department_chaos_reason = template_context.get("department_chaos_reason") or ""
        department_chaos_risk_budget_scale = float(
            template_context.get("department_chaos_risk_budget_scale") or 1.0
        )
        policy_execution_label = template_context.get("policy_execution_label") or "unknown"
        policy_execution_score = float(template_context.get("policy_execution_score") or 0.0)
        policy_execution_top_department = template_context.get("policy_execution_top_department") or ""
        policy_execution_reason = template_context.get("policy_execution_reason") or ""
        policy_execution_risk_budget_scale = float(
            template_context.get("policy_execution_risk_budget_scale") or 1.0
        )
        people_fragility_label = template_context.get("people_fragility_label") or "stable"
        people_fragility_score = float(template_context.get("people_fragility_score") or 0.0)
        people_fragility_focus = template_context.get("people_fragility_focus") or ""
        people_fragility_reason = template_context.get("people_fragility_reason") or ""
        people_fragility_risk_budget_scale = float(
            template_context.get("people_fragility_risk_budget_scale") or 1.0
        )
        source_mode_label = template_context.get("source_mode_label") or "mixed"
        source_mode_dominant = template_context.get("source_mode_dominant") or ""
        source_mode_reason = template_context.get("source_mode_reason") or ""
        source_mode_risk_budget_scale = float(
            template_context.get("source_mode_risk_budget_scale") or 1.0
        )
        structural_decay_radar_label = template_context.get("structural_decay_radar_label") or "stable"
        structural_decay_radar_display_label = template_context.get("structural_decay_radar_display_label") or ""
        structural_decay_radar_score = float(template_context.get("structural_decay_radar_score") or 0.0)
        structural_decay_radar_action_hint = template_context.get("structural_decay_radar_action_hint") or ""
        structural_decay_radar_risk_budget_scale = float(
            template_context.get("structural_decay_radar_risk_budget_scale") or 1.0
        )
        structural_decay_radar_top_signals = template_context.get("structural_decay_radar_top_signals") or []

        return {
            "template_id": template_context.get("template_id") or "",
            "template_name": template_context.get("template_name") or "",
            "theme": template_context.get("theme") or "",
            "allocation_mode": template_context.get("allocation_mode") or "template_base",
            "bias_summary": template_context.get("bias_summary") or "",
            "bias_strength_raw": float(template_context.get("bias_strength_raw") or 0.0),
            "bias_strength": float(template_context.get("bias_strength") or 0.0),
            "bias_scale": float(template_context.get("bias_scale") or 1.0),
            "bias_quality_label": template_context.get("bias_quality_label") or "full",
            "bias_quality_reason": template_context.get("bias_quality_reason") or "",
            "base_recommendation_score": base_recommendation_score,
            "recommendation_score": recommendation_score,
            "base_recommendation_tier": template_context.get("base_recommendation_tier") or "",
            "recommendation_tier": template_context.get("recommendation_tier") or "",
            "ranking_penalty": ranking_penalty,
            "ranking_penalty_reason": ranking_penalty_reason,
            "bias_highlights_raw": template_context.get("bias_highlights_raw") or [],
            "bias_highlights": template_context.get("bias_highlights") or [],
            "bias_actions": template_context.get("bias_actions") or [],
            "signal_attribution": template_context.get("signal_attribution") or [],
            "driver_summary": template_context.get("driver_summary") or [],
            "dominant_drivers": template_context.get("dominant_drivers") or [],
            "core_legs": template_context.get("core_legs") or [],
            "support_legs": template_context.get("support_legs") or [],
            "theme_core": template_context.get("theme_core") or "",
            "theme_support": template_context.get("theme_support") or "",
            "execution_posture": template_context.get("execution_posture") or "",
            "bias_compression_effect": compression_effect,
            "compression_summary": {
                "label": (
                    "compressed"
                    if compression_effect >= 3
                    else "cautious"
                    if compression_effect >= 1
                    else "full"
                ),
                "raw_bias_strength": bias_strength_raw,
                "effective_bias_strength": bias_strength,
                "compression_effect": compression_effect,
                "compression_ratio": round(
                    (compression_effect / bias_strength_raw) if bias_strength_raw > 0 else 0.0,
                    6,
                ),
                "quality_label": template_context.get("bias_quality_label") or "full",
                "reason": template_context.get("bias_quality_reason") or "",
            },
            "selection_quality": {
                "label": (
                    "auto_downgraded"
                    if ranking_penalty >= 0.4
                    else "softened"
                    if ranking_penalty > 0
                    else "original"
                ),
                "base_recommendation_score": base_recommendation_score,
                "effective_recommendation_score": recommendation_score,
                "base_recommendation_tier": template_context.get("base_recommendation_tier") or "",
                "effective_recommendation_tier": template_context.get("recommendation_tier") or "",
                "ranking_penalty": ranking_penalty,
                "reason": ranking_penalty_reason,
                "input_reliability_posture": input_reliability_posture,
                "input_reliability_action_hint": input_reliability_action_hint,
            },
            "input_reliability": {
                "label": input_reliability_label,
                "score": input_reliability_score,
                "lead": input_reliability_lead,
                "posture": input_reliability_posture,
                "reason": input_reliability_reason,
                "action_hint": input_reliability_action_hint,
            },
            "department_chaos": {
                "label": department_chaos_label,
                "score": department_chaos_score,
                "top_department": department_chaos_top_department,
                "reason": department_chaos_reason,
                "risk_budget_scale": department_chaos_risk_budget_scale,
                "active": department_chaos_label in {"chaotic", "chaos_guarded"}
                or department_chaos_score >= 0.58,
            },
            "policy_execution": {
                "label": policy_execution_label,
                "score": policy_execution_score,
                "top_department": policy_execution_top_department,
                "reason": policy_execution_reason,
                "risk_budget_scale": policy_execution_risk_budget_scale,
                "active": policy_execution_label in {"chaotic", "watch", "guarded"}
                or policy_execution_score >= 0.54,
            },
            "people_fragility": {
                "label": people_fragility_label,
                "score": people_fragility_score,
                "focus": people_fragility_focus,
                "reason": people_fragility_reason,
                "risk_budget_scale": people_fragility_risk_budget_scale,
                "active": people_fragility_label in {"fragile", "people_guarded"}
                or people_fragility_score >= 0.68,
            },
            "source_mode_summary": {
                "label": source_mode_label,
                "dominant": source_mode_dominant,
                "reason": source_mode_reason,
                "risk_budget_scale": source_mode_risk_budget_scale,
                "active": source_mode_label in {"fallback-heavy", "watch"}
                or source_mode_risk_budget_scale < 0.95,
            },
            "structural_decay_radar": {
                "label": structural_decay_radar_label,
                "display_label": structural_decay_radar_display_label,
                "score": structural_decay_radar_score,
                "action_hint": structural_decay_radar_action_hint,
                "risk_budget_scale": structural_decay_radar_risk_budget_scale,
                "top_signals": structural_decay_radar_top_signals,
                "active": structural_decay_radar_label in {"decay_alert", "decay_guarded"}
                or structural_decay_radar_score >= 0.68,
            },
            "side_bias_summary": {
                "long_raw_weight": round(long_raw_total, 6),
                "long_effective_weight": round(long_effective_total, 6),
                "short_raw_weight": round(short_raw_total, 6),
                "short_effective_weight": round(short_effective_total, 6),
            },
            "max_delta_weight": round(max_delta, 6),
            "shifted_asset_count": len(shifted_assets),
            "shifted_assets": shifted_assets,
            "compressed_asset_count": len(compressed_rows),
            "compressed_assets": [item["symbol"] for item in compressed_rows[:4]],
            "rows": rows,
        }

    def _build_price_matrix(
        self,
        universe: AssetUniverse,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        min_history_days: int,
        min_overlap_ratio: float,
    ) -> Dict[str, Any]:
        series_map: Dict[str, pd.Series] = {}
        symbol_alignment: List[Dict[str, Any]] = []
        liquidity_snapshot: Dict[str, Dict[str, float]] = {}
        venue_dates: Dict[str, set[pd.Timestamp]] = {}
        for asset in universe.get_assets():
            provider_name = "legacy"
            if hasattr(self.data_manager, "get_cross_market_historical_data"):
                result = self.data_manager.get_cross_market_historical_data(
                    symbol=asset.symbol,
                    asset_class=asset.asset_class.value,
                    start_date=start_date,
                    end_date=end_date,
                    interval="1d",
                )
                if isinstance(result, dict):
                    data = result.get("data", pd.DataFrame())
                    provider_name = result.get("provider") or provider_name
                else:
                    data = result
            else:
                data = self.data_manager.get_historical_data(
                    symbol=asset.symbol,
                    start_date=start_date,
                    end_date=end_date,
                    interval="1d",
                )
            if data.empty or "close" not in data.columns:
                raise ValueError(f"No daily close data found for {asset.symbol}")
            series = self._normalize_daily_close(data["close"], asset.symbol)
            if series.empty:
                raise ValueError(f"No normalized daily close data found for {asset.symbol}")
            series_map[asset.symbol] = series
            liquidity_stats = self._extract_liquidity_stats(data)
            liquidity_snapshot[asset.symbol] = liquidity_stats
            venue_dates.setdefault(asset.venue, set()).update(series.index.to_list())
            symbol_alignment.append(
                {
                    "symbol": asset.symbol,
                    "asset_class": asset.asset_class.value,
                    "market": asset.market,
                    "venue": asset.venue,
                    "execution_channel": asset.execution_channel,
                    "settlement": asset.settlement,
                    "provider": provider_name,
                    "raw_rows": int(len(data)),
                    "valid_rows": int(len(series)),
                    "first_date": series.index[0].strftime("%Y-%m-%d") if len(series) else None,
                    "last_date": series.index[-1].strftime("%Y-%m-%d") if len(series) else None,
                    "avg_daily_volume": liquidity_stats["avg_daily_volume"],
                    "avg_daily_notional": liquidity_stats["avg_daily_notional"],
                }
            )

        outer_matrix = pd.concat(series_map.values(), axis=1, join="outer").sort_index()
        outer_matrix = outer_matrix[~outer_matrix.index.duplicated(keep="last")]

        if outer_matrix.empty:
            raise ValueError("No cross-market price history found")

        tradable_mask = outer_matrix.notna().all(axis=1)
        aligned_price_matrix = outer_matrix.loc[tradable_mask].copy()
        tradable_count = int(tradable_mask.sum())
        union_count = int(len(outer_matrix))
        tradable_day_ratio = tradable_count / union_count if union_count else 0.0
        dropped_dates_count = int(union_count - tradable_count)
        common_dates = set(aligned_price_matrix.index.to_list())

        if aligned_price_matrix.empty:
            raise ValueError("No aligned cross-market price history found after tradable-day filtering")
        if tradable_count < min_history_days:
            raise ValueError(
                f"Tradable overlap history too short: {tradable_count} days, need at least {min_history_days}"
            )
        if tradable_day_ratio < min_overlap_ratio:
            raise ValueError(
                f"Tradable overlap ratio {tradable_day_ratio:.2f} below threshold {min_overlap_ratio:.2f}"
            )

        for item in symbol_alignment:
            item["coverage_ratio"] = round(
                item["valid_rows"] / union_count if union_count else 0.0,
                4,
            )

        return {
            "raw_price_matrix": outer_matrix,
            "aligned_price_matrix": aligned_price_matrix,
            "tradable_mask": tradable_mask.astype(bool),
            "data_alignment": {
                "per_symbol": symbol_alignment,
                "union_row_count": union_count,
                "aligned_row_count": tradable_count,
                "tradable_day_ratio": round(tradable_day_ratio, 4),
                "dropped_dates_count": dropped_dates_count,
                "calendar_diagnostics": self._build_calendar_diagnostics(
                    venue_dates=venue_dates,
                    common_dates=common_dates,
                    union_count=union_count,
                    tradable_day_ratio=tradable_day_ratio,
                ),
            },
            "liquidity_snapshot": liquidity_snapshot,
        }

    def _build_results(
        self,
        universe: AssetUniverse,
        price_matrix: pd.DataFrame,
        signal_frame: pd.DataFrame,
        data_alignment: Dict[str, Any],
        strategy_name: str,
        parameters: Dict[str, Any],
        construction_mode: str,
        constraint_overlay: Dict[str, Any],
    ) -> Dict[str, Any]:
        returns = price_matrix.pct_change().fillna(0.0)
        hedge_portfolio = HedgePortfolioBuilder(universe.get_assets())
        long_assets = hedge_portfolio.long_leg.assets
        short_assets = hedge_portfolio.short_leg.assets
        leg_returns = hedge_portfolio.build_leg_returns(returns)
        long_leg_returns = leg_returns["long"]
        short_leg_returns = leg_returns["short"]
        spread_return = long_leg_returns - short_leg_returns

        positions = signal_frame["position"].shift(1).fillna(0.0)
        turnover = signal_frame["position"].diff().abs().fillna(signal_frame["position"].abs())
        transaction_cost = turnover * (self.commission + self.slippage)
        portfolio_returns = positions * spread_return - transaction_cost

        portfolio = pd.DataFrame(index=price_matrix.index)
        portfolio["long_leg_return"] = long_leg_returns
        portfolio["short_leg_return"] = short_leg_returns
        portfolio["spread_return"] = spread_return
        portfolio["position"] = positions
        portfolio["transaction_cost"] = transaction_cost
        portfolio["returns"] = portfolio_returns
        portfolio["total"] = self.initial_capital * (1 + portfolio_returns).cumprod()
        portfolio["cash"] = portfolio["total"]
        portfolio["exposure"] = portfolio["position"].abs() * portfolio["total"]

        trades = self._build_trades(signal_frame, portfolio)
        total_return = (portfolio["total"].iloc[-1] - self.initial_capital) / self.initial_capital
        daily_returns = portfolio["returns"].dropna()
        closed_holds = [
            float(trade["holding_period_days"])
            for trade in trades
            if trade["type"].startswith("CLOSE") and trade.get("holding_period_days") is not None
        ]
        avg_holding_period = float(np.mean(closed_holds)) if closed_holds else 0.0

        leg_performance = {
            "long": {
                "assets": [asset.to_dict() for asset in long_assets],
                "cumulative_return": float((1 + long_leg_returns).cumprod().iloc[-1] - 1),
            },
            "short": {
                "assets": [asset.to_dict() for asset in short_assets],
                "cumulative_return": float((1 + short_leg_returns).cumprod().iloc[-1] - 1),
            },
            "spread": {
                "cumulative_return": float((1 + spread_return).cumprod().iloc[-1] - 1),
            },
        }
        asset_contributions = hedge_portfolio.build_asset_contributions(returns)
        hedge_summary = hedge_portfolio.summarize_exposures(signal_frame.get("hedge_ratio"))
        hedge_summary["beta_neutrality"] = self._build_beta_neutrality(
            long_leg_returns=long_leg_returns,
            short_leg_returns=short_leg_returns,
            hedge_ratio_series=signal_frame.get("hedge_ratio"),
        )
        execution_router = ExecutionRouter(
            universe.get_assets(),
            initial_capital=self.initial_capital,
            avg_hedge_ratio=hedge_summary["hedge_ratio"]["average"],
            latest_prices={symbol: float(price) for symbol, price in price_matrix.iloc[-1].items()},
            liquidity_snapshots=data_alignment.get("liquidity_snapshot", {}),
        )
        execution_plan = execution_router.build_plan()
        liquidity_summary = execution_plan.get("liquidity_summary", {})
        margin_summary = execution_plan.get("margin_summary", {})

        spread_series = signal_frame.copy()
        spread_series["date"] = spread_series.index.strftime("%Y-%m-%d")
        refit_interval = int(parameters.get("refit_interval", 1))

        correlation_matrix = returns[price_matrix.columns].corr().fillna(0.0)
        cointegration_diagnostics = self._build_cointegration_diagnostics(
            price_matrix=price_matrix,
            long_assets=long_assets,
            short_assets=short_assets,
        )

        execution_diagnostics = {
            "construction_mode": construction_mode,
            "turnover": float(turnover.sum()),
            "cost_drag": float(transaction_cost.sum()),
            "avg_holding_period": round(avg_holding_period, 2),
            "constraint_binding_count": int(constraint_overlay.get("binding_count", 0)),
            "route_count": execution_plan["route_count"],
            "batch_count": len(execution_plan.get("batches", [])),
            "provider_count": len(execution_plan.get("by_provider", {})),
            "venue_count": len(execution_plan.get("venue_allocation", [])),
            "max_route_fraction": float(execution_plan.get("max_route_fraction", 0.0)),
            "max_batch_fraction": float(execution_plan.get("max_batch_fraction", 0.0)),
            "concentration_level": execution_plan.get("concentration", {}).get("level", "balanced"),
            "concentration_reason": execution_plan.get("concentration", {}).get("reason", ""),
            "liquidity_level": liquidity_summary.get("level", "unknown"),
            "liquidity_reason": liquidity_summary.get("reason", ""),
            "max_adv_usage": float(liquidity_summary.get("max_adv_usage", 0.0)),
            "stretched_route_count": int(liquidity_summary.get("stretched_route_count", 0)),
            "margin_level": margin_summary.get("level", "manageable"),
            "margin_reason": margin_summary.get("reason", ""),
            "margin_utilization": float(margin_summary.get("utilization", 0.0)),
            "gross_leverage": float(margin_summary.get("gross_leverage", 0.0)),
            "beta_level": hedge_summary.get("beta_neutrality", {}).get("level", "unknown"),
            "beta_reason": hedge_summary.get("beta_neutrality", {}).get("reason", ""),
            "calendar_level": data_alignment["data_alignment"].get("calendar_diagnostics", {}).get("level", "aligned"),
            "calendar_reason": data_alignment["data_alignment"].get("calendar_diagnostics", {}).get("reason", ""),
            "lot_efficiency": float(execution_plan.get("sizing_summary", {}).get("lot_efficiency", 1.0)),
            "residual_notional": float(execution_plan.get("sizing_summary", {}).get("total_residual_notional", 0.0)),
            "suggested_rebalance": self._suggest_rebalance_cadence(
                turnover=float(turnover.sum()),
                avg_holding_period=avg_holding_period,
                construction_mode=construction_mode,
            ),
            "stress_test_flag": execution_plan.get("execution_stress", {}).get("worst_case", {}).get(
                "concentration_level",
                "balanced",
            ),
            "stress_test_reason": execution_plan.get("execution_stress", {}).get("worst_case", {}).get(
                "concentration_reason",
                "",
            ),
            "cointegration_level": cointegration_diagnostics.get("level", "unknown"),
            "cointegration_reason": cointegration_diagnostics.get("reason", ""),
        }

        results = {
            "initial_capital": self.initial_capital,
            "final_value": float(portfolio["total"].iloc[-1]),
            "total_return": float(total_return),
            "annualized_return": float(calculate_annualized_return(total_return, len(portfolio))),
            "sharpe_ratio": float(calculate_sharpe_ratio(daily_returns)) if len(daily_returns) > 1 else 0.0,
            "max_drawdown": float(calculate_max_drawdown(portfolio["total"])),
            "volatility": float(calculate_volatility(daily_returns)) if len(daily_returns) > 1 else 0.0,
            "var_95": float(calculate_var(daily_returns)) if len(daily_returns) > 0 else 0.0,
            "num_trades": len(trades),
            "portfolio": _portfolio_to_records(portfolio),
            "portfolio_curve": _portfolio_curve(portfolio),
            "trades": trades,
            "spread_series": _dataframe_to_records(
                spread_series[
                    ["date", "long_leg", "short_leg", "hedge_ratio", "spread", "z_score", "signal", "position"]
                ]
            ),
            "leg_performance": leg_performance,
            "correlation_matrix": {
                "columns": list(correlation_matrix.columns),
                "rows": [
                    {
                        "symbol": index,
                        **{column: float(value) for column, value in row.items()},
                    }
                    for index, row in correlation_matrix.iterrows()
                ],
            },
            "data_alignment": data_alignment["data_alignment"],
            "execution_diagnostics": execution_diagnostics,
            "execution_plan": execution_plan,
            "hedge_portfolio": hedge_summary,
            "asset_contributions": asset_contributions,
            "cointegration_diagnostics": cointegration_diagnostics,
            "refit_summary": {
                "refit_interval": refit_interval,
                "estimated_refits": max(1, int(np.ceil(len(price_matrix) / max(refit_interval, 1)))),
                "dynamic_hedge": construction_mode == "ols_hedge" or strategy_name == "cointegration_reversion",
            },
        }
        if construction_mode == "ols_hedge":
            results["hedge_ratio_series"] = _dataframe_to_records(
                spread_series[["date", "hedge_ratio"]]
            )
        return results

    def _build_cointegration_diagnostics(
        self,
        *,
        price_matrix: pd.DataFrame,
        long_assets: List[Any],
        short_assets: List[Any],
    ) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        long_symbols = [asset.symbol for asset in long_assets]
        short_symbols = [asset.symbol for asset in short_assets]

        for long_symbol in long_symbols:
            for short_symbol in short_symbols:
                if long_symbol not in price_matrix.columns or short_symbol not in price_matrix.columns:
                    continue
                diagnosis = self._estimate_cointegration(
                    price_matrix[long_symbol],
                    price_matrix[short_symbol],
                )
                if diagnosis is None:
                    continue
                rows.append(
                    {
                        "long_symbol": long_symbol,
                        "short_symbol": short_symbol,
                        **diagnosis,
                    }
                )

        if not rows:
            return {
                "available": False,
                "level": "unknown",
                "reason": "有效样本不足，暂时无法评估协整关系。",
                "pair_count": 0,
                "cointegrated_pair_count": 0,
                "rows": [],
                "best_pair": None,
            }

        rows.sort(key=lambda item: (item["p_value"], -item["sample_size"], item["long_symbol"], item["short_symbol"]))
        best_pair = rows[0]
        cointegrated_count = sum(1 for item in rows if item["p_value"] < 0.05)

        if best_pair["p_value"] < 0.05:
            level = "strong"
            reason = f"最佳配对 {best_pair['long_symbol']}/{best_pair['short_symbol']} 通过协整检验，p 值为 {best_pair['p_value']:.4f}。"
        elif best_pair["p_value"] < 0.15:
            level = "watch"
            reason = f"最佳配对 {best_pair['long_symbol']}/{best_pair['short_symbol']} 只有弱协整迹象，p 值为 {best_pair['p_value']:.4f}。"
        else:
            level = "weak"
            reason = f"当前多空腿之间没有明显协整关系，最佳配对 p 值为 {best_pair['p_value']:.4f}。"

        return {
            "available": True,
            "level": level,
            "reason": reason,
            "pair_count": len(rows),
            "cointegrated_pair_count": cointegrated_count,
            "rows": rows,
            "best_pair": best_pair,
        }

    @staticmethod
    def _estimate_cointegration(series_a: pd.Series, series_b: pd.Series) -> Optional[Dict[str, Any]]:
        aligned = pd.concat(
            [
                pd.to_numeric(series_a, errors="coerce"),
                pd.to_numeric(series_b, errors="coerce"),
            ],
            axis=1,
        ).dropna()
        if len(aligned) < 10:
            return None

        y1 = aligned.iloc[:, 0].astype(float).values
        y2 = aligned.iloc[:, 1].astype(float).values
        hedge_ratio = float(np.linalg.lstsq(y1.reshape(-1, 1), y2, rcond=None)[0][0]) if len(y1) else 1.0

        try:
            from statsmodels.tsa.stattools import coint

            statistic, p_value, _ = coint(y1, y2)
            method = "engle_granger"
            score = float(statistic)
        except Exception:
            spread = y2 - hedge_ratio * y1
            diff_spread = np.diff(spread)
            lagged_spread = spread[:-1]
            if len(diff_spread) < 5:
                return None
            x = np.column_stack([np.ones(len(lagged_spread)), lagged_spread])
            beta = np.linalg.lstsq(x, diff_spread, rcond=None)[0]
            residuals = diff_spread - x @ beta
            degrees_of_freedom = max(len(residuals) - 2, 1)
            residual_std = np.sqrt(np.sum(residuals ** 2) / degrees_of_freedom)
            denominator = residual_std / np.sqrt(max(np.sum(lagged_spread ** 2), 1e-9))
            test_stat = float(beta[1] / denominator) if denominator > 0 else 0.0
            try:
                from scipy import stats as scipy_stats

                p_value = float(2 * (1 - scipy_stats.t.cdf(abs(test_stat), degrees_of_freedom)))
            except Exception:
                p_value = 1.0
            method = "heuristic_adf"
            score = test_stat

        if np.isnan(p_value):
            p_value = 1.0

        return {
            "method": method,
            "test_statistic": round(float(score), 6),
            "p_value": round(float(p_value), 6),
            "sample_size": int(len(aligned)),
            "hedge_ratio": round(float(hedge_ratio), 6),
        }

    @staticmethod
    def _extract_liquidity_stats(data: pd.DataFrame) -> Dict[str, float]:
        if data.empty:
            return {"avg_daily_volume": 0.0, "avg_daily_notional": 0.0}

        close_series = pd.to_numeric(data.get("close"), errors="coerce")
        volume_series = pd.to_numeric(data.get("volume"), errors="coerce")
        if close_series is None or volume_series is None:
            return {"avg_daily_volume": 0.0, "avg_daily_notional": 0.0}

        valid = pd.DataFrame({"close": close_series, "volume": volume_series}).dropna()
        valid = valid[(valid["close"] > 0) & (valid["volume"] > 0)]
        if valid.empty:
            return {"avg_daily_volume": 0.0, "avg_daily_notional": 0.0}

        recent = valid.tail(20)
        avg_daily_volume = float(recent["volume"].mean())
        avg_daily_notional = float((recent["close"] * recent["volume"]).mean())
        return {
            "avg_daily_volume": round(avg_daily_volume, 2),
            "avg_daily_notional": round(avg_daily_notional, 2),
        }

    @staticmethod
    def _build_calendar_diagnostics(
        *,
        venue_dates: Dict[str, set[pd.Timestamp]],
        common_dates: set[pd.Timestamp],
        union_count: int,
        tradable_day_ratio: float,
    ) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        max_mismatch_ratio = 0.0
        for venue, dates in venue_dates.items():
            active_dates = len(dates)
            common_overlap = len(dates & common_dates)
            mismatch_days = len(dates - common_dates)
            mismatch_ratio = mismatch_days / active_dates if active_dates else 0.0
            max_mismatch_ratio = max(max_mismatch_ratio, mismatch_ratio)
            rows.append(
                {
                    "venue": venue,
                    "active_dates": active_dates,
                    "shared_dates": common_overlap,
                    "mismatch_days": mismatch_days,
                    "coverage_ratio": round(active_dates / union_count, 4) if union_count else 0.0,
                    "mismatch_ratio": round(mismatch_ratio, 4),
                }
            )

        rows.sort(key=lambda item: (-item["mismatch_ratio"], item["venue"]))
        if tradable_day_ratio < 0.75 or max_mismatch_ratio > 0.2:
            level = "stretched"
        elif tradable_day_ratio < 0.9 or max_mismatch_ratio > 0.08:
            level = "watch"
        else:
            level = "aligned"

        top_row = rows[0] if rows else None
        reason = (
            f"tradable {round(tradable_day_ratio * 100, 1)}%"
            + (
                f", top venue {top_row['venue']} mismatch {round(top_row['mismatch_ratio'] * 100, 1)}%"
                if top_row else ""
            )
        )
        return {
            "level": level,
            "reason": reason,
            "rows": rows,
            "max_mismatch_ratio": round(max_mismatch_ratio, 6),
        }

    @staticmethod
    def _build_beta_neutrality(
        *,
        long_leg_returns: pd.Series,
        short_leg_returns: pd.Series,
        hedge_ratio_series: Optional[pd.Series],
    ) -> Dict[str, Any]:
        paired = pd.DataFrame({"long": long_leg_returns, "short": short_leg_returns}).dropna()
        if len(paired) < 5 or float(paired["short"].var(ddof=0)) == 0:
            return {
                "level": "unknown",
                "reason": "insufficient variance",
                "beta": 1.0,
                "beta_gap": 0.0,
                "rolling_beta_last": 1.0,
                "rolling_beta_mean": 1.0,
                "hedge_ratio_average": float(hedge_ratio_series.mean()) if hedge_ratio_series is not None else 1.0,
            }

        beta = float(paired["long"].cov(paired["short"]) / paired["short"].var(ddof=0))
        rolling_window = min(20, len(paired))
        rolling_cov = paired["long"].rolling(rolling_window).cov(paired["short"])
        rolling_var = paired["short"].rolling(rolling_window).var(ddof=0).replace(0, np.nan)
        rolling_beta = (rolling_cov / rolling_var).replace([np.inf, -np.inf], np.nan).dropna()
        rolling_last = float(rolling_beta.iloc[-1]) if not rolling_beta.empty else beta
        rolling_mean = float(rolling_beta.mean()) if not rolling_beta.empty else beta
        beta_gap = abs(beta - 1.0)

        if beta_gap > 0.4:
            level = "stretched"
        elif beta_gap > 0.18:
            level = "watch"
        else:
            level = "balanced"

        return {
            "level": level,
            "reason": f"beta {beta:.2f}, gap {beta_gap:.2f}, rolling {rolling_last:.2f}",
            "beta": round(beta, 6),
            "beta_gap": round(beta_gap, 6),
            "rolling_beta_last": round(rolling_last, 6),
            "rolling_beta_mean": round(rolling_mean, 6),
            "hedge_ratio_average": round(float(hedge_ratio_series.mean()) if hedge_ratio_series is not None else 1.0, 6),
        }

    def _build_trades(self, signal_frame: pd.DataFrame, portfolio: pd.DataFrame) -> List[Dict[str, Any]]:
        trades: List[Dict[str, Any]] = []
        previous_position = 0
        entry_value: Optional[float] = None
        entry_date: Optional[str] = None
        entry_timestamp: Optional[pd.Timestamp] = None

        for idx, row in signal_frame.iterrows():
            current_position = int(row["position"])
            date_str = idx.strftime("%Y-%m-%d")
            if current_position == previous_position:
                continue

            if previous_position != 0:
                exit_value = float(portfolio.loc[idx, "total"])
                trades.append(
                    {
                        "date": date_str,
                        "type": "CLOSE_LONG_SPREAD" if previous_position == 1 else "CLOSE_SHORT_SPREAD",
                        "position": 0,
                        "spread": float(row["spread"]),
                        "z_score": float(row["z_score"]),
                        "pnl": float(exit_value - (entry_value or exit_value)),
                        "entry_date": entry_date,
                        "holding_period_days": int((idx - entry_timestamp).days) if entry_timestamp is not None else None,
                    }
                )
                entry_value = None
                entry_date = None
                entry_timestamp = None

            if current_position != 0:
                entry_value = float(portfolio.loc[idx, "total"])
                entry_date = date_str
                entry_timestamp = idx
                trades.append(
                    {
                        "date": date_str,
                        "type": "OPEN_LONG_SPREAD" if current_position == 1 else "OPEN_SHORT_SPREAD",
                        "position": current_position,
                        "spread": float(row["spread"]),
                        "z_score": float(row["z_score"]),
                        "pnl": 0.0,
                        "entry_date": date_str,
                        "holding_period_days": None,
                    }
                )

            previous_position = current_position

        return trades

    @staticmethod
    def _suggest_rebalance_cadence(
        *,
        turnover: float,
        avg_holding_period: float,
        construction_mode: str,
    ) -> str:
        if turnover >= 10 or avg_holding_period and avg_holding_period < 5:
            return "weekly"
        if construction_mode == "ols_hedge" or turnover >= 5 or avg_holding_period and avg_holding_period < 12:
            return "biweekly"
        return "monthly"

    @staticmethod
    def _normalize_daily_close(close_series: pd.Series, symbol: str) -> pd.Series:
        series = close_series.copy()
        series.index = pd.to_datetime(series.index, utc=True).tz_localize(None).normalize()
        series = series[~series.index.duplicated(keep="last")]
        series = series.sort_index().dropna().astype(float)
        series.name = symbol
        return series


def _portfolio_to_records(portfolio: pd.DataFrame) -> List[Dict[str, Any]]:
    records = []
    for idx, row in portfolio.iterrows():
        records.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "total": float(row["total"]),
                "returns": float(row["returns"]),
                "cash": float(row["cash"]),
                "exposure": float(row["exposure"]),
                "position": float(row["position"]),
            }
        )
    return records


def _portfolio_curve(portfolio: pd.DataFrame) -> List[Dict[str, Any]]:
    return [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "total": float(row["total"]),
            "returns": float(row["returns"]),
        }
        for idx, row in portfolio.iterrows()
    ]


def _dataframe_to_records(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        records.append(
            {
                key: (float(value) if key != "date" else value)
                for key, value in row.to_dict().items()
            }
        )
    return records
