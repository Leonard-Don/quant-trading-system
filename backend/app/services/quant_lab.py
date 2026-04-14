"""Unified quant feature extensions for the Quant Lab workspace."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from backend.app.services.realtime_alerts import realtime_alerts_store
from backend.app.services.realtime_preferences import realtime_preferences_store
from backend.app.services.notification_service import notification_service
from backend.app.core.persistence import persistence_manager
from backend.app.api.v1.endpoints.pricing_support import peer_candidate_pool
from src.research.workbench import research_workbench_store
from src.analytics.asset_pricing import _fetch_ff5_factors
from src.analytics.factor_expression import FactorExpressionError, factor_expression_engine
from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer
from src.backtest.backtester import Backtester
from src.backtest.batch_backtester import BayesianParameterOptimizer, WalkForwardAnalyzer
from src.backtest.industry_backtest import IndustryBacktester
from src.data.data_manager import DataManager
from src.strategy.advanced_strategies import (
    ATRTrailingStop,
    MACDStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    StochasticOscillator,
    VWAPStrategy,
)
from src.strategy.strategies import (
    BollingerBands,
    BuyAndHold,
    MovingAverageCrossover,
    MultiFactorStrategy,
    RSIStrategy,
    TurtleTradingStrategy,
)
from src.strategy.strategy_validator import StrategyValidator
from src.trading.trade_manager import trade_manager
from src.utils.config import PROJECT_ROOT
from src.utils.data_validation import normalize_backtest_results

logger = logging.getLogger(__name__)


STRATEGY_CLASSES = {
    "moving_average": MovingAverageCrossover,
    "rsi": RSIStrategy,
    "bollinger_bands": BollingerBands,
    "buy_and_hold": BuyAndHold,
    "macd": MACDStrategy,
    "mean_reversion": MeanReversionStrategy,
    "vwap": VWAPStrategy,
    "momentum": MomentumStrategy,
    "stochastic": StochasticOscillator,
    "atr_trailing_stop": ATRTrailingStop,
    "turtle_trading": TurtleTradingStrategy,
    "multi_factor": MultiFactorStrategy,
}

MODEL_Z_SCORES = {
    0.95: 1.6448536269514722,
    0.99: 2.3263478740408408,
}


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return default
        return numeric
    except (TypeError, ValueError):
        return default


def _json_ready(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Series, pd.Index)):
        return [_json_ready(item) for item in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return [_json_ready(item) for item in value.to_dict("records")]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _pick_metric(payload: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return _safe_float(payload.get(key), None)
    return None


def _normalize_ratio(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    numeric = float(value)
    if abs(numeric) > 1.5:
        numeric = numeric / 100.0
    return numeric


def _score_higher_better(value: Optional[float], floor: float = -0.2, ceiling: float = 0.4) -> Optional[float]:
    if value is None:
        return None
    clipped = min(max(value, floor), ceiling)
    return (clipped - floor) / (ceiling - floor)


def _score_lower_better(value: Optional[float], floor: float = -0.5, ceiling: float = 0.5) -> Optional[float]:
    if value is None:
        return None
    clipped = min(max(value, floor), ceiling)
    return 1.0 - ((clipped - floor) / (ceiling - floor))


class QuantLabService:
    """Backend service powering the Quant Lab workspace."""

    def __init__(self, storage_root: str | Path | None = None):
        self.data_manager = DataManager()
        self.pricing_analyzer = PricingGapAnalyzer()
        self.storage_root = Path(storage_root or (PROJECT_ROOT / "data" / "quant_lab"))
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def optimize_strategy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(payload.get("symbol") or "").strip().upper()
        strategy_name = str(payload.get("strategy") or "").strip()
        if not symbol:
            raise ValueError("symbol is required")
        if strategy_name not in STRATEGY_CLASSES:
            raise ValueError(f"unsupported strategy: {strategy_name}")

        start_date = _to_datetime(payload.get("start_date"))
        end_date = _to_datetime(payload.get("end_date"))
        initial_capital = _safe_float(payload.get("initial_capital"), 10000.0)
        commission = _safe_float(payload.get("commission"), 0.001)
        slippage = _safe_float(payload.get("slippage"), 0.001)
        density = max(2, min(int(payload.get("density") or 3), 6))
        optimization_metric = str(payload.get("optimization_metric") or "sharpe_ratio")
        optimization_method = str(payload.get("optimization_method") or "grid")
        optimization_budget = payload.get("optimization_budget")
        train_ratio = min(max(_safe_float(payload.get("train_ratio"), 0.7), 0.55), 0.9)

        data = self.data_manager.get_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if data.empty or len(data) < 80:
            raise ValueError("insufficient data for optimization")

        base_params = self._validated_parameters(strategy_name, payload.get("parameters") or {})
        parameter_grid = payload.get("parameter_grid") or self._build_parameter_grid(strategy_name, base_params, density=density)
        parameter_candidates = self._build_parameter_candidates(strategy_name, parameter_grid)
        candidate_budget = max(1, min(int(optimization_budget or len(parameter_candidates) or 1), max(len(parameter_candidates), 1)))

        split_index = max(30, min(len(data) - 20, int(len(data) * train_ratio)))
        train_data = data.iloc[:split_index].copy()
        validation_data = data.iloc[split_index:].copy()
        if validation_data.empty:
            validation_data = data.iloc[-min(30, len(data)) :].copy()

        observations: List[Dict[str, Any]] = []

        def evaluator(params: Dict[str, Any]) -> tuple[Dict[str, Any], float]:
            metrics = self._run_backtest_metrics(
                symbol=symbol,
                strategy_name=strategy_name,
                params=params,
                data=train_data,
                initial_capital=initial_capital,
                commission=commission,
                slippage=slippage,
            )
            score = _safe_float(metrics.get(optimization_metric), float("-inf"))
            observations.append({
                "parameters": dict(params),
                "metrics": metrics,
                "score": score,
            })
            return metrics, score

        if optimization_method == "bayesian" and len(parameter_candidates) > 1:
            optimizer = BayesianParameterOptimizer(
                initial_samples=min(5, candidate_budget),
                max_evaluations=candidate_budget,
            )
            optimized = optimizer.optimize(parameter_candidates, evaluator)
            best_parameters = optimized["parameters"]
            best_train_metrics = optimized["train_metrics"]
        else:
            for candidate in parameter_candidates[:candidate_budget]:
                evaluator(candidate)
            if not observations:
                raise ValueError("no optimization candidates were evaluated")
            best_observation = max(observations, key=lambda item: item["score"])
            best_parameters = best_observation["parameters"]
            best_train_metrics = best_observation["metrics"]

        validation_metrics = self._run_backtest_metrics(
            symbol=symbol,
            strategy_name=strategy_name,
            params=best_parameters,
            data=validation_data,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        )
        full_sample_metrics = self._run_backtest_metrics(
            symbol=symbol,
            strategy_name=strategy_name,
            params=best_parameters,
            data=data,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        )

        walk_forward = None
        if payload.get("run_walk_forward", True):
            analyzer = WalkForwardAnalyzer(
                train_period=max(40, int(payload.get("train_period") or 126)),
                test_period=max(10, int(payload.get("test_period") or 42)),
                step_size=max(5, int(payload.get("step_size") or 21)),
            )
            walk_forward = analyzer.analyze(
                data=data,
                strategy_factory=lambda parameters=None: self._create_strategy(strategy_name, parameters or {}),
                backtester_factory=lambda: Backtester(
                    initial_capital=initial_capital,
                    commission=commission,
                    slippage=slippage,
                ),
                parameter_grid=parameter_grid,
                optimization_metric=optimization_metric,
                optimization_method=optimization_method,
                optimization_budget=candidate_budget,
                monte_carlo_simulations=max(50, int(payload.get("monte_carlo_simulations") or 150)),
            )

        leaderboard = sorted(
            observations,
            key=lambda item: item["score"],
            reverse=True,
        )
        heatmap = self._build_heatmap(parameter_grid, leaderboard, optimization_metric)
        stability = self._build_parameter_stability(best_parameters, leaderboard)

        return _json_ready(
            {
                "symbol": symbol,
                "strategy": strategy_name,
                "optimization_metric": optimization_metric,
                "optimization_method": optimization_method,
                "candidate_count": len(parameter_candidates),
                "evaluated_candidates": len(observations),
                "generated_grid": parameter_grid,
                "best_parameters": best_parameters,
                "best_train_metrics": best_train_metrics,
                "validation_metrics": validation_metrics,
                "full_sample_metrics": full_sample_metrics,
                "parameter_stability": stability,
                "leaderboard": leaderboard[:20],
                "heatmap": heatmap,
                "walk_forward": walk_forward,
                "validation_backtest_request": {
                    "symbol": symbol,
                    "strategy": strategy_name,
                    "parameters": best_parameters,
                    "start_date": payload.get("start_date"),
                    "end_date": payload.get("end_date"),
                    "initial_capital": initial_capital,
                    "commission": commission,
                    "slippage": slippage,
                },
            }
        )

    def analyze_risk_center(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        symbols = [
            str(item or "").strip().upper()
            for item in (payload.get("symbols") or [])
            if str(item or "").strip()
        ]
        if not symbols:
            raise ValueError("symbols is required")

        period = str(payload.get("period") or "1y")
        weights = payload.get("weights")
        close_frame = self._load_close_matrix(symbols, period)
        if close_frame.empty or len(close_frame) < 40:
            raise ValueError("insufficient aligned history for risk analysis")

        returns = close_frame.pct_change().dropna(how="all").fillna(0.0)
        normalized_weights = self._normalize_weights(weights, len(symbols))
        portfolio_returns = returns.dot(np.asarray(normalized_weights, dtype=float))
        portfolio_returns.name = "portfolio"

        var_cvar = {
            "historical": self._compute_var_cvar(portfolio_returns, method="historical"),
            "parametric": self._compute_var_cvar(portfolio_returns, method="parametric"),
            "monte_carlo": self._compute_var_cvar(portfolio_returns, method="monte_carlo"),
        }
        rolling = self._build_rolling_risk(portfolio_returns)
        correlation_matrix = self._build_correlation_matrix(returns)
        factor_decomposition = self._build_factor_decomposition(portfolio_returns, period)
        stress_tests = self._build_stress_tests(portfolio_returns, factor_decomposition)
        attribution = self._build_performance_attribution(returns, normalized_weights)

        total_return = float(((1 + portfolio_returns).prod()) - 1)
        annualized_return = float((1 + total_return) ** (252 / max(len(portfolio_returns), 1)) - 1) if len(portfolio_returns) else 0.0
        volatility = float(portfolio_returns.std(ddof=0) * math.sqrt(252)) if len(portfolio_returns) else 0.0
        sharpe = float((portfolio_returns.mean() / portfolio_returns.std(ddof=0)) * math.sqrt(252)) if portfolio_returns.std(ddof=0) > 0 else 0.0

        return _json_ready(
            {
                "symbols": symbols,
                "weights": normalized_weights,
                "period": period,
                "summary": {
                    "data_points": len(portfolio_returns),
                    "total_return": round(total_return, 4),
                    "annualized_return": round(annualized_return, 4),
                    "volatility": round(volatility, 4),
                    "sharpe_ratio": round(sharpe, 4),
                    "max_drawdown": round(self._series_max_drawdown((1 + portfolio_returns).cumprod()), 4),
                },
                "var_cvar": var_cvar,
                "rolling_metrics": rolling,
                "correlation_matrix": correlation_matrix,
                "factor_decomposition": factor_decomposition,
                "stress_tests": stress_tests,
                "performance_attribution": attribution,
            }
        )

    def get_trading_journal(self, profile_id: str | None = None) -> Dict[str, Any]:
        stored = self._read_store(self._profile_file("trading_journal", profile_id), default={"notes": {}, "strategy_lifecycle": []})
        history = trade_manager.get_history(limit=500)
        notes = stored.get("notes") or {}

        trades = []
        for trade in history:
            note_payload = notes.get(trade.get("id"), {})
            pnl = trade.get("pnl")
            symbol = str(trade.get("symbol") or "").upper()
            total_amount = _safe_float(trade.get("total_amount"))
            trades.append(
                {
                    **trade,
                    "symbol": symbol,
                    "notes": note_payload.get("notes", ""),
                    "strategy_source": note_payload.get("strategy_source", "manual"),
                    "signal_strength": note_payload.get("signal_strength"),
                    "reason_category": note_payload.get("reason_category") or self._infer_trade_reason(trade),
                    "error_category": note_payload.get("error_category") or self._infer_error_category(trade),
                    "risk_bucket": "high" if total_amount >= 15000 else "medium" if total_amount >= 5000 else "low",
                    "pnl": pnl,
                }
            )

        daily_report = self._group_trade_report(trades, freq="D")
        weekly_report = self._group_trade_report(trades, freq="W")
        bias_detection = self._detect_trading_biases(trades)
        lifecycle_entries = self._normalize_strategy_lifecycle(stored.get("strategy_lifecycle") or [])

        losing_trades = [trade for trade in trades if _safe_float(trade.get("pnl")) < 0]
        source_breakdown = Counter(trade.get("strategy_source") or "manual" for trade in trades)
        risk_breakdown = Counter(trade.get("risk_bucket") or "unknown" for trade in trades)

        return _json_ready(
            {
                "profile_id": profile_id or "default",
                "summary": {
                    "total_trades": len(trades),
                    "winning_trades": sum(1 for trade in trades if _safe_float(trade.get("pnl")) > 0),
                    "losing_trades": sum(1 for trade in trades if _safe_float(trade.get("pnl")) < 0),
                    "realized_pnl": round(sum(_safe_float(trade.get("pnl")) for trade in trades), 2),
                    "win_rate": round(
                        sum(1 for trade in trades if _safe_float(trade.get("pnl")) > 0) / max(len([trade for trade in trades if trade.get("pnl") is not None]), 1),
                        4,
                    ),
                    "average_signal_strength": round(
                        np.nanmean([
                            _safe_float(trade.get("signal_strength"), np.nan)
                            for trade in trades
                            if trade.get("signal_strength") not in (None, "")
                        ]) if any(trade.get("signal_strength") not in (None, "") for trade in trades) else 0.0,
                        4,
                    ),
                },
                "trades": trades[:120],
                "daily_report": daily_report[:20],
                "weekly_report": weekly_report[:16],
                "loss_analysis": self._build_loss_analysis(losing_trades),
                "bias_detection": bias_detection,
                "source_breakdown": [
                    {"source": source, "count": count}
                    for source, count in source_breakdown.most_common()
                ],
                "risk_breakdown": [
                    {"bucket": bucket, "count": count}
                    for bucket, count in risk_breakdown.most_common()
                ],
                "strategy_lifecycle": lifecycle_entries,
                "strategy_lifecycle_summary": self._build_strategy_lifecycle_summary(lifecycle_entries),
            }
        )

    def update_trading_journal(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        filepath = self._profile_file("trading_journal", profile_id)
        with self._lock:
            current = self._read_store(filepath, default={"notes": {}, "strategy_lifecycle": []})
            next_notes = current.get("notes") or {}
            for trade_id, value in (payload.get("notes") or {}).items():
                if isinstance(value, dict):
                    next_notes[str(trade_id)] = value
            current["notes"] = next_notes
            if isinstance(payload.get("strategy_lifecycle"), list):
                current["strategy_lifecycle"] = self._normalize_strategy_lifecycle(payload["strategy_lifecycle"])
            self._write_store(filepath, current)
        return self.get_trading_journal(profile_id)

    def get_alert_orchestration(self, profile_id: str | None = None) -> Dict[str, Any]:
        filepath = self._profile_file("alert_orchestration", profile_id)
        custom_payload = self._read_store(
            filepath,
            default={"composite_rules": [], "channels": [], "history": [], "module_alerts": []},
        )
        realtime_payload = realtime_alerts_store.get_alerts(profile_id=profile_id)
        preferences = realtime_preferences_store.get_preferences(profile_id=profile_id)
        alert_history = list(realtime_payload.get("alert_hit_history") or [])
        module_alerts = list(custom_payload.get("module_alerts") or [])

        history = list(custom_payload.get("history") or [])
        merged_history = self._merge_alert_history(alert_history=alert_history, override_history=history)
        history_stats = self._build_alert_history_stats(merged_history)
        hit_rate = round(len(alert_history) / max(len(realtime_payload.get("alerts") or []), 1), 2) if realtime_payload.get("alerts") else 0.0

        return _json_ready(
            {
                "profile_id": profile_id or "default",
                "summary": {
                    "realtime_rules": len(realtime_payload.get("alerts") or []),
                    "composite_rules": len(custom_payload.get("composite_rules") or []),
                    "watchlist_symbols": len(preferences.get("symbols") or []),
                    "alert_history_events": len(merged_history),
                    "estimated_hit_rate": hit_rate,
                    "reviewed_events": history_stats["summary"]["reviewed_events"],
                    "false_positive_rate": history_stats["summary"]["false_positive_rate"],
                    "average_response_minutes": history_stats["summary"]["average_response_minutes"],
                    "cascaded_events": history_stats["summary"]["cascaded_events"],
                    "notified_events": history_stats["summary"]["notified_events"],
                    "workbench_tasks_created": history_stats["summary"]["workbench_tasks_created"],
                    "infra_tasks_created": history_stats["summary"]["infra_tasks_created"],
                    "timeseries_points_written": history_stats["summary"]["timeseries_points_written"],
                    "config_snapshots_created": history_stats["summary"]["config_snapshots_created"],
                },
                "event_bus": {
                    "modules": [
                        {"module": "realtime", "count": len(realtime_payload.get("alerts") or [])},
                        {"module": "composite", "count": len(custom_payload.get("composite_rules") or [])},
                        {"module": "custom", "count": len(module_alerts)},
                    ],
                    "history": merged_history[:80],
                },
                "history_stats": history_stats,
                "composite_rules": custom_payload.get("composite_rules") or [],
                "channels": custom_payload.get("channels") or [],
                "module_alerts": module_alerts,
            }
        )

    def update_alert_orchestration(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        filepath = self._profile_file("alert_orchestration", profile_id)
        with self._lock:
            current = self._read_store(
                filepath,
                default={"composite_rules": [], "channels": [], "history": [], "module_alerts": []},
            )
            for key in ("composite_rules", "channels", "module_alerts"):
                if isinstance(payload.get(key), list):
                    current[key] = payload[key]
            if isinstance(payload.get("history_entry"), dict):
                current["history"] = [payload["history_entry"], *(current.get("history") or [])][:80]
            if isinstance(payload.get("history_updates"), list) and payload.get("history_updates"):
                current["history"] = self._upsert_alert_history_entries(
                    current.get("history") or [],
                    payload.get("history_updates") or [],
                )[:80]
            self._write_store(filepath, current)
        return self.get_alert_orchestration(profile_id)

    def publish_alert_event(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        filepath = self._profile_file("alert_orchestration", profile_id)
        with self._lock:
            current = self._read_store(
                filepath,
                default={"composite_rules": [], "channels": [], "history": [], "module_alerts": []},
            )
            event_entry = self._normalize_alert_history_entry(
                {
                    **(payload or {}),
                    "review_status": payload.get("review_status") or "pending",
                    "trigger_time": payload.get("trigger_time") or datetime.utcnow().isoformat(),
                }
            )
            if not event_entry:
                raise ValueError("invalid alert event payload")

            matched_rules = self._match_composite_rules(
                event_entry=event_entry,
                composite_rules=current.get("composite_rules") or [],
                explicit_rule_ids=payload.get("rule_ids") or [],
            )
            cascade_actions = self._collect_cascade_actions(
                payload=payload,
                matched_rules=matched_rules,
                orchestration_channels=current.get("channels") or [],
            )
            cascade_results = self._execute_cascade_actions(event_entry, cascade_actions)
            dispatched_channels = [
                result.get("channel")
                for result in cascade_results
                if result.get("action_type") == "notify_channel" and result.get("channel")
            ]
            workbench_task_ids = [
                result.get("task_id")
                for result in cascade_results
                if result.get("action_type") == "create_workbench_task" and result.get("task_id")
            ]
            infra_task_ids = [
                result.get("task_id")
                for result in cascade_results
                if result.get("action_type") == "create_infra_task" and result.get("task_id")
            ]
            timeseries_points = [
                {
                    "id": result.get("timeseries_id"),
                    "series_name": result.get("series_name"),
                    "symbol": result.get("symbol"),
                    "timestamp": result.get("timestamp"),
                    "value": result.get("value"),
                }
                for result in cascade_results
                if result.get("action_type") == "persist_timeseries" and result.get("timeseries_id")
            ]
            config_snapshots = [
                {
                    "record_id": result.get("record_id"),
                    "config_type": result.get("config_type"),
                    "config_key": result.get("config_key"),
                    "owner_id": result.get("owner_id"),
                    "version": result.get("version"),
                }
                for result in cascade_results
                if result.get("action_type") == "save_config_version" and result.get("record_id")
            ]
            event_entry.update(
                {
                    "severity": str(payload.get("severity") or "info").lower(),
                    "condition_summary": payload.get("condition_summary") or event_entry.get("condition_summary"),
                    "matched_rule_ids": [item.get("id") for item in matched_rules if item.get("id")],
                    "matched_rule_names": [item.get("name") for item in matched_rules if item.get("name")],
                    "cascade_actions": cascade_actions,
                    "cascade_results": cascade_results,
                    "dispatched_channels": dispatched_channels,
                    "workbench_task_ids": workbench_task_ids,
                    "infra_task_ids": infra_task_ids,
                    "timeseries_points": timeseries_points,
                    "config_snapshots": config_snapshots,
                    "dispatch_status": self._resolve_dispatch_status(cascade_results),
                    "published_at": datetime.utcnow().isoformat(),
                }
            )
            current["history"] = self._upsert_alert_history_entries(
                current.get("history") or [],
                [event_entry],
            )[:120]
            self._write_store(filepath, current)

        persistence_manager.put_record(
            record_type="alert_event",
            record_key=str(event_entry.get("id") or datetime.utcnow().timestamp()),
            payload={
                "profile_id": profile_id or "default",
                "event": event_entry,
            },
        )
        return {
            "published_event": _json_ready(event_entry),
            "matched_rules": _json_ready(matched_rules),
            "cascade_results": _json_ready(cascade_results),
            "orchestration": self.get_alert_orchestration(profile_id),
        }

    def _match_composite_rules(
        self,
        *,
        event_entry: Dict[str, Any],
        composite_rules: List[Dict[str, Any]],
        explicit_rule_ids: List[str],
    ) -> List[Dict[str, Any]]:
        explicit_ids = {str(item).strip() for item in (explicit_rule_ids or []) if str(item).strip()}
        haystack = " ".join(
            str(part or "").lower()
            for part in [
                event_entry.get("rule_name"),
                event_entry.get("condition_summary"),
                event_entry.get("message"),
                event_entry.get("source_module"),
                event_entry.get("symbol"),
            ]
        )
        matched: List[Dict[str, Any]] = []
        for rule in composite_rules or []:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id") or "").strip()
            if rule_id and rule_id in explicit_ids:
                matched.append(dict(rule))
                continue
            summary = str(rule.get("condition_summary") or "").strip().lower()
            if not summary:
                continue
            tokens = [
                token.strip()
                for token in summary.replace("AND", "+").replace("and", "+").split("+")
                if token.strip()
            ]
            if tokens and all(token.lower() in haystack for token in tokens):
                matched.append(dict(rule))
        return matched

    def _collect_cascade_actions(
        self,
        *,
        payload: Dict[str, Any],
        matched_rules: List[Dict[str, Any]],
        orchestration_channels: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()

        def register(action: Dict[str, Any]) -> None:
            normalized = {
                "type": str(action.get("type") or "").strip().lower(),
                **action,
            }
            if not normalized["type"]:
                return
            key = json.dumps(
                {
                    "type": normalized.get("type"),
                    "channel": normalized.get("channel"),
                    "target": normalized.get("target"),
                    "task_type": normalized.get("task_type"),
                    "task_name": normalized.get("task_name"),
                    "backend": normalized.get("backend"),
                    "record_type": normalized.get("record_type"),
                    "series_name": normalized.get("series_name"),
                    "config_type": normalized.get("config_type"),
                    "config_key": normalized.get("config_key"),
                    "owner_id": normalized.get("owner_id"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if key in seen_keys:
                return
            seen_keys.add(key)
            actions.append(normalized)

        for raw_action in payload.get("cascade_actions") or []:
            if isinstance(raw_action, dict):
                register(raw_action)

        if payload.get("notify_channels"):
            for channel in payload.get("notify_channels") or []:
                register({"type": "notify_channel", "channel": channel})
        if payload.get("create_workbench_task"):
            register(
                {
                    "type": "create_workbench_task",
                    "task_type": payload.get("workbench_task_type") or "cross_market",
                    "status": payload.get("workbench_status") or "new",
                    "target": "research_workbench",
                }
            )
        if payload.get("persist_event_record", True):
            register({"type": "persist_record", "record_type": "alert_event_dispatch"})

        for rule in matched_rules:
            if rule.get("action") and isinstance(rule.get("action"), str) and rule.get("action").strip():
                action_text = rule.get("action").lower()
                if "workbench" in action_text:
                    register({"type": "create_workbench_task", "task_type": "cross_market", "status": "new", "target": "research_workbench"})
                if "webhook" in action_text:
                    register({"type": "notify_channel", "channel": "webhook"})
                if "wecom" in action_text:
                    register({"type": "notify_channel", "channel": "wecom"})
                if "email" in action_text:
                    register({"type": "notify_channel", "channel": "email"})
                if "timeseries" in action_text or "时序" in action_text:
                    register(
                        {
                            "type": "persist_timeseries",
                            "series_name": f"alert_bus.{payload.get('source_module') or 'manual'}",
                        }
                    )
                if "queue" in action_text or "排队" in action_text or "异步" in action_text:
                    register(
                        {
                            "type": "create_infra_task",
                            "task_name": "quant_alert_followup",
                            "backend": "auto",
                        }
                    )
                if "config" in action_text or "版本" in action_text or "snapshot" in action_text:
                    register(
                        {
                            "type": "save_config_version",
                            "config_type": "alert_playbook",
                            "config_key": payload.get("source_module") or "manual",
                            "owner_id": "default",
                        }
                    )
            for raw_action in rule.get("cascade_actions") or []:
                if isinstance(raw_action, dict):
                    register(raw_action)

        if not any(action.get("type") == "notify_channel" for action in actions):
            for channel in orchestration_channels or []:
                if not isinstance(channel, dict):
                    continue
                if channel.get("enabled", True):
                    register({"type": "notify_channel", "channel": channel.get("id")})
        return actions

    def _execute_cascade_actions(
        self,
        event_entry: Dict[str, Any],
        cascade_actions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for action in cascade_actions or []:
            action_type = str(action.get("type") or "").strip().lower()
            try:
                if action_type == "notify_channel":
                    channel = str(action.get("channel") or "dry_run").strip()
                    notification_payload = {
                        "source": event_entry.get("source_module") or "alert_bus",
                        "severity": event_entry.get("severity") or "info",
                        "title": event_entry.get("rule_name") or "Quant alert event",
                        "message": event_entry.get("message") or event_entry.get("condition_summary") or "",
                        "symbol": event_entry.get("symbol"),
                        "event_id": event_entry.get("id"),
                        "rule_name": event_entry.get("rule_name"),
                    }
                    delivery = notification_service.send(channel, notification_payload)
                    results.append(
                        {
                            "action_type": "notify_channel",
                            "channel": channel,
                            "status": delivery.get("status"),
                            "delivered": delivery.get("delivered"),
                            "details": delivery,
                        }
                    )
                elif action_type == "create_workbench_task":
                    task_type = str(action.get("task_type") or "cross_market")
                    title = (
                        action.get("title")
                        or f"[Alert] {event_entry.get('rule_name') or event_entry.get('symbol') or 'Research follow-up'}"
                    )
                    task = research_workbench_store.create_task(
                        {
                            "type": task_type if task_type in {"pricing", "cross_market", "macro_mispricing", "trade_thesis"} else "cross_market",
                            "title": title,
                            "status": str(action.get("status") or "new"),
                            "source": event_entry.get("source_module") or "alert_bus",
                            "symbol": event_entry.get("symbol") or "",
                            "note": event_entry.get("message") or event_entry.get("condition_summary") or "",
                            "context": {
                                "event_id": event_entry.get("id"),
                                "severity": event_entry.get("severity"),
                                "matched_rule_names": event_entry.get("matched_rule_names") or [],
                                "dispatched_channels": event_entry.get("dispatched_channels") or [],
                            },
                            "snapshot": {
                                "headline": event_entry.get("rule_name") or "Alert follow-up",
                                "summary": event_entry.get("message") or event_entry.get("condition_summary") or "",
                                "payload": {"alert_event": event_entry},
                                "saved_at": datetime.utcnow().isoformat(),
                            },
                        }
                    )
                    results.append(
                        {
                            "action_type": "create_workbench_task",
                            "status": "created",
                            "task_id": task.get("id"),
                            "task_title": task.get("title"),
                        }
                    )
                elif action_type == "create_infra_task":
                    from backend.app.core.task_queue import task_queue_manager

                    task_payload = dict(action.get("payload")) if isinstance(action.get("payload"), dict) else {}
                    task_payload.update(
                        {
                            "task_origin": task_payload.get("task_origin") or "alert_orchestration",
                            "source_module": event_entry.get("source_module") or "alert_bus",
                            "symbol": event_entry.get("symbol") or "",
                            "severity": event_entry.get("severity") or "info",
                            "rule_name": event_entry.get("rule_name"),
                            "condition_summary": event_entry.get("condition_summary"),
                            "trigger_value": event_entry.get("trigger_value"),
                            "event_id": event_entry.get("id"),
                        }
                    )
                    if action.get("include_event_payload", True):
                        task_payload["alert_event"] = event_entry
                    task = task_queue_manager.submit(
                        name=str(action.get("task_name") or "quant_alert_followup"),
                        payload=task_payload,
                        backend=str(action.get("backend") or "auto"),
                    )
                    results.append(
                        {
                            "action_type": "create_infra_task",
                            "status": "queued",
                            "task_id": task.get("id"),
                            "task_name": task.get("name"),
                            "execution_backend": task.get("execution_backend"),
                            "broker_task_id": task.get("broker_task_id"),
                        }
                    )
                elif action_type == "persist_record":
                    record_type = str(action.get("record_type") or "alert_event_dispatch")
                    record = persistence_manager.put_record(
                        record_type=record_type,
                        record_key=str(event_entry.get("id") or datetime.utcnow().timestamp()),
                        payload={"event": event_entry, "action": action},
                    )
                    results.append(
                        {
                            "action_type": "persist_record",
                            "status": "stored",
                            "record_id": record.get("id"),
                            "record_type": record.get("record_type"),
                        }
                    )
                elif action_type == "persist_timeseries":
                    point_value = _pick_metric(action, "value")
                    if point_value is None:
                        point_value = _pick_metric(event_entry, "trigger_value", "threshold")
                    point = persistence_manager.put_timeseries(
                        series_name=str(action.get("series_name") or f"alert_bus.{event_entry.get('source_module') or 'manual'}"),
                        symbol=str(action.get("symbol") or event_entry.get("symbol") or ""),
                        timestamp=str(action.get("timestamp") or event_entry.get("trigger_time") or event_entry.get("published_at") or datetime.utcnow().isoformat()),
                        value=point_value,
                        payload={
                            "event": event_entry,
                            "action": action,
                            **(action.get("payload") if isinstance(action.get("payload"), dict) else {}),
                        },
                    )
                    results.append(
                        {
                            "action_type": "persist_timeseries",
                            "status": "stored",
                            "timeseries_id": point.get("id"),
                            "series_name": point.get("series_name"),
                            "symbol": point.get("symbol"),
                            "timestamp": point.get("timestamp"),
                            "value": point.get("value"),
                        }
                    )
                elif action_type == "save_config_version":
                    owner_id = str(action.get("owner_id") or "default")
                    config_type = str(action.get("config_type") or "alert_playbook")
                    config_key = str(action.get("config_key") or event_entry.get("source_module") or "manual")
                    record_type = f"config:{owner_id}:{config_type}:{config_key}"
                    existing = persistence_manager.list_records(record_type=record_type, limit=200)
                    next_version = len(existing) + 1
                    snapshot_payload = (
                        action.get("payload")
                        if isinstance(action.get("payload"), dict)
                        else {
                            "event": event_entry,
                            "matched_rule_names": event_entry.get("matched_rule_names") or [],
                            "dispatch_status": event_entry.get("dispatch_status"),
                        }
                    )
                    record = persistence_manager.put_record(
                        record_type=record_type,
                        record_key=f"v{next_version}",
                        record_id=f"{record_type}:v{next_version}",
                        payload={
                            "owner_id": owner_id,
                            "config_type": config_type,
                            "config_key": config_key,
                            "version": next_version,
                            "payload": snapshot_payload,
                            "created_by": "alert_bus",
                            "source_event_id": event_entry.get("id"),
                        },
                    )
                    results.append(
                        {
                            "action_type": "save_config_version",
                            "status": "stored",
                            "record_id": record.get("id"),
                            "config_type": config_type,
                            "config_key": config_key,
                            "owner_id": owner_id,
                            "version": next_version,
                        }
                    )
                else:
                    results.append(
                        {
                            "action_type": action_type or "unknown",
                            "status": "skipped",
                            "reason": "unsupported action type",
                        }
                    )
            except Exception as exc:
                results.append(
                    {
                        "action_type": action_type or "unknown",
                        "status": "failed",
                        "reason": str(exc),
                    }
                )
        return results

    def _resolve_dispatch_status(self, cascade_results: List[Dict[str, Any]]) -> str:
        if not cascade_results:
            return "no_actions"
        if any(result.get("status") in {"failed"} for result in cascade_results):
            return "degraded"
        if any(result.get("status") in {"sent", "created", "stored", "dry_run", "queued"} for result in cascade_results):
            return "dispatched"
        return "pending"

    def _merge_alert_history(
        self,
        *,
        alert_history: List[Dict[str, Any]],
        override_history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw_entry in [*(override_history or []), *(alert_history or [])]:
            normalized = self._normalize_alert_history_entry(raw_entry)
            if not normalized:
                continue
            entry_id = str(normalized.get("id") or "")
            if entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)
            merged.append(normalized)
        merged.sort(key=lambda item: item.get("trigger_time") or "", reverse=True)
        return merged[:120]

    def _upsert_alert_history_entries(
        self,
        existing_entries: List[Dict[str, Any]],
        incoming_entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for raw_entry in existing_entries or []:
            normalized = self._normalize_alert_history_entry(raw_entry)
            if normalized:
                merged[str(normalized["id"])] = normalized
        for raw_entry in incoming_entries or []:
            normalized = self._normalize_alert_history_entry(raw_entry)
            if normalized:
                merged[str(normalized["id"])] = normalized
        return sorted(merged.values(), key=lambda item: item.get("trigger_time") or "", reverse=True)

    def _normalize_alert_history_entry(self, entry: Dict[str, Any] | None) -> Optional[Dict[str, Any]]:
        if not isinstance(entry, dict):
            return None
        trigger_time = (
            entry.get("trigger_time")
            or entry.get("triggerTime")
            or entry.get("triggered_at")
            or entry.get("timestamp")
        )
        trigger_time = str(trigger_time or datetime.utcnow().isoformat())
        symbol = str(entry.get("symbol") or "").strip().upper()
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            entry_id = f"alert_hist_{symbol or 'unknown'}_{trigger_time}"
        review_status = str(entry.get("review_status") or entry.get("reviewStatus") or "").strip().lower()
        if review_status not in {"pending", "resolved", "false_positive"}:
            review_status = "pending"
        acknowledged_at = entry.get("acknowledged_at") or entry.get("acknowledgedAt") or entry.get("resolved_at")
        acknowledged_at = str(acknowledged_at).strip() if acknowledged_at else None
        if review_status == "pending":
            acknowledged_at = None
        source_module = str(
            entry.get("source_module")
            or entry.get("sourceModule")
            or entry.get("module")
            or ("composite" if entry.get("condition_summary") else "realtime")
        ).strip().lower() or "realtime"
        rule_name = str(
            entry.get("rule_name")
            or entry.get("ruleName")
            or entry.get("name")
            or entry.get("conditionLabel")
            or entry.get("condition_summary")
            or (f"{symbol} alert" if symbol else "unnamed_rule")
        ).strip()
        response_minutes = None
        try:
            if acknowledged_at:
                response_minutes = round(
                    (
                        pd.Timestamp(acknowledged_at).tz_localize(None)
                        - pd.Timestamp(trigger_time).tz_localize(None)
                    ).total_seconds() / 60.0,
                    2,
                )
        except Exception:
            response_minutes = None

        return {
            "id": entry_id,
            "alert_id": entry.get("alert_id") or entry.get("alertId"),
            "symbol": symbol or None,
            "rule_name": rule_name,
            "source_module": source_module,
            "severity": str(entry.get("severity") or "info").lower(),
            "condition": entry.get("condition"),
            "condition_label": entry.get("condition_label") or entry.get("conditionLabel"),
            "condition_summary": entry.get("condition_summary"),
            "message": str(entry.get("message") or "").strip(),
            "trigger_time": trigger_time,
            "trigger_value": _pick_metric(entry, "trigger_value", "triggerValue"),
            "trigger_price": _pick_metric(entry, "trigger_price", "triggerPrice", "priceSnapshot"),
            "threshold": _pick_metric(entry, "threshold"),
            "review_status": review_status,
            "acknowledged_at": acknowledged_at,
            "response_minutes": response_minutes,
            "matched_rule_ids": entry.get("matched_rule_ids") or [],
            "matched_rule_names": entry.get("matched_rule_names") or [],
            "cascade_actions": entry.get("cascade_actions") or [],
            "cascade_results": entry.get("cascade_results") or [],
            "dispatched_channels": entry.get("dispatched_channels") or [],
            "workbench_task_ids": entry.get("workbench_task_ids") or [],
            "infra_task_ids": entry.get("infra_task_ids") or [],
            "timeseries_points": entry.get("timeseries_points") or [],
            "config_snapshots": entry.get("config_snapshots") or [],
            "dispatch_status": entry.get("dispatch_status") or "pending",
            "published_at": entry.get("published_at"),
        }

    def _build_alert_history_stats(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not history:
            return {
                "summary": {
                    "reviewed_events": 0,
                    "false_positive_rate": 0.0,
                    "average_response_minutes": None,
                    "pending_events": 0,
                    "cascaded_events": 0,
                    "notified_events": 0,
                    "workbench_tasks_created": 0,
                    "infra_tasks_created": 0,
                    "timeseries_points_written": 0,
                    "config_snapshots_created": 0,
                },
                "rule_stats": [],
                "module_stats": [],
                "pending_queue": [],
                "cascade_stats": [],
            }

        reviewed = [entry for entry in history if entry.get("review_status") in {"resolved", "false_positive"}]
        false_positive_count = sum(1 for entry in reviewed if entry.get("review_status") == "false_positive")
        response_values = [
            _safe_float(entry.get("response_minutes"), None)
            for entry in reviewed
            if entry.get("response_minutes") not in (None, "")
        ]
        response_values = [value for value in response_values if value is not None]
        pending_queue = [entry for entry in history if entry.get("review_status") == "pending"]
        cascaded_events = [entry for entry in history if entry.get("cascade_results")]
        notified_events = sum(1 for entry in history if entry.get("dispatched_channels"))
        workbench_tasks_created = sum(len(entry.get("workbench_task_ids") or []) for entry in history)
        infra_tasks_created = sum(len(entry.get("infra_task_ids") or []) for entry in history)
        timeseries_points_written = sum(len(entry.get("timeseries_points") or []) for entry in history)
        config_snapshots_created = sum(len(entry.get("config_snapshots") or []) for entry in history)

        rule_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        module_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        cascade_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for entry in history:
            rule_groups[str(entry.get("rule_name") or "unnamed_rule")].append(entry)
            module_groups[str(entry.get("source_module") or "unknown")].append(entry)
            for result in entry.get("cascade_results") or []:
                cascade_groups[str(result.get("action_type") or "unknown")].append(result)

        rule_stats = []
        for rule_name, entries in rule_groups.items():
            reviewed_entries = [entry for entry in entries if entry.get("review_status") in {"resolved", "false_positive"}]
            false_hits = sum(1 for entry in reviewed_entries if entry.get("review_status") == "false_positive")
            last_trigger = max((entry.get("trigger_time") or "" for entry in entries), default="")
            rule_stats.append(
                {
                    "rule_name": rule_name,
                    "source_module": entries[0].get("source_module"),
                    "hit_count": len(entries),
                    "reviewed_count": len(reviewed_entries),
                    "false_positive_rate": round(false_hits / max(len(reviewed_entries), 1), 4) if reviewed_entries else 0.0,
                    "last_trigger_time": last_trigger or None,
                    "sample_symbol": entries[0].get("symbol"),
                }
            )
        rule_stats.sort(key=lambda item: (item["hit_count"], item["reviewed_count"]), reverse=True)

        module_stats = []
        for module_name, entries in module_groups.items():
            reviewed_entries = [entry for entry in entries if entry.get("review_status") in {"resolved", "false_positive"}]
            false_hits = sum(1 for entry in reviewed_entries if entry.get("review_status") == "false_positive")
            module_stats.append(
                {
                    "module": module_name,
                    "event_count": len(entries),
                    "reviewed_count": len(reviewed_entries),
                    "pending_count": sum(1 for entry in entries if entry.get("review_status") == "pending"),
                    "false_positive_rate": round(false_hits / max(len(reviewed_entries), 1), 4) if reviewed_entries else 0.0,
                }
            )
        module_stats.sort(key=lambda item: item["event_count"], reverse=True)

        cascade_stats = []
        for action_type, results in cascade_groups.items():
            cascade_stats.append(
                {
                    "action_type": action_type,
                    "count": len(results),
                    "success_count": sum(1 for item in results if item.get("status") in {"sent", "created", "stored", "dry_run", "queued"}),
                    "failure_count": sum(1 for item in results if item.get("status") == "failed"),
                }
            )
        cascade_stats.sort(key=lambda item: item["count"], reverse=True)

        return {
            "summary": {
                "reviewed_events": len(reviewed),
                "false_positive_rate": round(false_positive_count / max(len(reviewed), 1), 4) if reviewed else 0.0,
                "average_response_minutes": round(sum(response_values) / len(response_values), 2) if response_values else None,
                "pending_events": len(pending_queue),
                "cascaded_events": len(cascaded_events),
                "notified_events": notified_events,
                "workbench_tasks_created": workbench_tasks_created,
                "infra_tasks_created": infra_tasks_created,
                "timeseries_points_written": timeseries_points_written,
                "config_snapshots_created": config_snapshots_created,
            },
            "rule_stats": rule_stats[:16],
            "module_stats": module_stats,
            "pending_queue": pending_queue[:20],
            "cascade_stats": cascade_stats,
        }

    def get_data_quality(self) -> Dict[str, Any]:
        provider_factory = self.data_manager.provider_factory
        if provider_factory is None:
            return {
                "providers": [],
                "summary": {"available": 0, "unavailable": 0},
                "failover_log": [],
                "audit_report": {"findings": [], "provider_status_mix": [], "weakest_provider": None},
                "backtest_quality_report": {"overall_score": 0.0, "risk_level": "unknown", "recommendation": "数据源未初始化"},
            }

        provider_rows = []
        failover_log = []
        probe_symbol = "SPY"
        for name, provider in provider_factory.providers.items():
            started = time.perf_counter()
            status = "available"
            error_message = ""
            freshness = None
            completeness = None
            latest_points = None
            try:
                history = provider.get_historical_data(probe_symbol)
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                if history is None or history.empty:
                    status = "degraded"
                    error_message = "empty response"
                    failover_log.append(self._failover_event(name, error_message))
                else:
                    latest_points = len(history)
                    completeness = round(min(len(history.tail(60)) / 60.0, 1.0), 2)
                    freshness = self._calculate_freshness(history.index.max())
            except Exception as exc:  # pragma: no cover - provider/network variance
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                status = "down"
                error_message = str(exc)
                failover_log.append(self._failover_event(name, error_message))

            provider_rows.append(
                {
                    "provider": name,
                    "status": status,
                    "latency_ms": latency_ms,
                    "freshness_minutes": freshness,
                    "freshness_label": self._label_freshness(freshness),
                    "completeness_score": completeness,
                    "sample_points": latest_points,
                    "error_rate_proxy": 1.0 if status == "down" else 0.35 if status == "degraded" else 0.0,
                    "quality_score": self._score_provider_quality(
                        status=status,
                        freshness_minutes=freshness,
                        completeness_score=completeness,
                        latency_ms=latency_ms,
                    ),
                    "audit_flags": self._build_provider_audit_flags(
                        status=status,
                        freshness_minutes=freshness,
                        completeness_score=completeness,
                        latency_ms=latency_ms,
                    ),
                    "last_error": error_message or None,
                }
            )

        log_path = self.storage_root / "data_quality_failover_log.json"
        historical_log = self._read_store(log_path, default=[])
        combined_log = (failover_log + historical_log)[:60]
        self._write_store(log_path, combined_log)
        audit_report = self._build_data_quality_audit(provider_rows, combined_log)
        backtest_quality_report = self._build_backtest_quality_report(provider_rows, combined_log)

        return _json_ready(
            {
                "summary": {
                    "available": sum(1 for row in provider_rows if row["status"] == "available"),
                    "degraded": sum(1 for row in provider_rows if row["status"] == "degraded"),
                    "down": sum(1 for row in provider_rows if row["status"] == "down"),
                    "stale": sum(1 for row in provider_rows if row.get("freshness_label") == "stale"),
                    "average_latency_ms": round(
                        sum(_safe_float(row.get("latency_ms")) for row in provider_rows) / max(len(provider_rows), 1),
                        2,
                    ),
                    "average_completeness": round(
                        sum(_safe_float(row.get("completeness_score")) for row in provider_rows) / max(len(provider_rows), 1),
                        4,
                    ),
                    "average_quality_score": round(
                        sum(_safe_float(row.get("quality_score")) for row in provider_rows) / max(len(provider_rows), 1),
                        4,
                    ),
                },
                "providers": provider_rows,
                "failover_log": combined_log[:24],
                "audit_report": audit_report,
                "backtest_quality_report": backtest_quality_report,
            }
        )

    def analyze_valuation_lab(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(payload.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        period = str(payload.get("period") or "1y")
        requested_peers = [
            str(item or "").strip().upper()
            for item in (payload.get("peer_symbols") or [])
            if str(item or "").strip()
        ]
        peer_limit = max(2, min(int(payload.get("peer_limit") or 6), 12))

        analysis = self.pricing_analyzer.analyze(symbol, period)
        valuation = analysis.get("valuation") or {}
        monte_carlo = valuation.get("monte_carlo") or {}
        fair_value = valuation.get("fair_value") or {}
        comparable = valuation.get("comparable") or {}
        dcf = valuation.get("dcf") or {}

        ensemble = self._build_valuation_ensemble(
            current_price=_safe_float(valuation.get("current_price")),
            dcf_value=_safe_float(dcf.get("intrinsic_value"), None),
            comparable_value=_safe_float(fair_value.get("mid"), None),
            monte_carlo=monte_carlo,
        )
        history = self._append_valuation_history(symbol, period, ensemble, analysis)
        peer_matrix = self._build_peer_matrix(symbol, requested_peers, peer_limit)

        return _json_ready(
            {
                "symbol": symbol,
                "period": period,
                "analysis": analysis,
                "ensemble_valuation": ensemble,
                "valuation_history": history,
                "peer_matrix": peer_matrix,
            }
        )

    def run_industry_rotation_lab(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        start_date = str(payload.get("start_date") or "").strip()
        end_date = str(payload.get("end_date") or "").strip()
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required")

        backtester = IndustryBacktester(
            initial_capital=_safe_float(payload.get("initial_capital"), 1_000_000),
            commission_rate=_safe_float(payload.get("commission"), 0.001),
            slippage=_safe_float(payload.get("slippage"), 0.001),
        )
        result = backtester.run_backtest(
            start_date=start_date,
            end_date=end_date,
            rebalance_freq=str(payload.get("rebalance_freq") or "monthly"),
            top_industries=max(1, int(payload.get("top_industries") or 3)),
            stocks_per_industry=max(1, int(payload.get("stocks_per_industry") or 3)),
            weight_method=str(payload.get("weight_method") or "equal"),
        )
        comparison = backtester.compare_with_benchmark(benchmark=backtester.benchmark_symbol, result=result)
        equity_series = result.equity_curve if isinstance(result.equity_curve, pd.Series) else pd.Series(dtype=float)
        equity_curve = [
            {"date": pd.Timestamp(index).strftime("%Y-%m-%d"), "value": round(float(value), 2)}
            for index, value in equity_series.items()
        ]
        return _json_ready(
            {
                "summary": {
                    "total_return": round(float(result.total_return), 4),
                    "annualized_return": round(float(result.annualized_return), 4),
                    "sharpe_ratio": round(float(result.sharpe_ratio), 4),
                    "max_drawdown": round(float(result.max_drawdown), 4),
                    "win_rate": round(float(result.win_rate), 4),
                    "trade_count": int(result.trade_count),
                    "benchmark_return": round(float(result.benchmark_return), 4),
                    "excess_return": round(float(result.excess_return), 4),
                    "sortino_ratio": round(float(result.sortino_ratio), 4),
                    "calmar_ratio": round(float(result.calmar_ratio), 4),
                    "volatility": round(float(result.volatility), 4),
                    "var_95": round(float(result.var_95), 4),
                },
                "equity_curve": equity_curve[-120:],
                "trades": backtester.get_trade_history()[-80:],
                "diagnostics": result.diagnostics or {},
                "benchmark_comparison": comparison,
            }
        )

    def evaluate_factor_expression(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(payload.get("symbol") or "").strip().upper()
        expression = str(payload.get("expression") or "").strip()
        period = str(payload.get("period") or "1y")
        preview_rows = max(5, min(int(payload.get("preview_rows") or 30), 120))
        if not symbol:
            raise ValueError("symbol is required")
        if not expression:
            raise ValueError("expression is required")

        data = self.data_manager.get_historical_data(symbol=symbol, period=period)
        if data.empty:
            raise ValueError("no market data available for factor expression")
        try:
            result = factor_expression_engine.evaluate(data, expression, preview_rows=preview_rows)
        except FactorExpressionError as exc:
            raise ValueError(str(exc)) from exc

        return _json_ready(
            {
                "symbol": symbol,
                "period": period,
                "expression": result.expression,
                "latest_value": result.latest_value,
                "preview": result.preview,
                "diagnostics": result.diagnostics,
                "supported_functions": [
                    "rank",
                    "zscore",
                    "sma",
                    "ema",
                    "rolling_mean",
                    "rolling_std",
                    "pct_change",
                    "delay",
                    "abs",
                    "min",
                    "max",
                    "clip",
                    "log",
                ],
            }
        )

    def _validated_parameters(self, strategy_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        is_valid, error_message, cleaned = StrategyValidator.validate_strategy_params(strategy_name, parameters or {})
        if not is_valid:
            raise ValueError(error_message)
        return cleaned

    def _create_strategy(self, strategy_name: str, cleaned_params: Dict[str, Any]):
        strategy_class = STRATEGY_CLASSES[strategy_name]
        if strategy_name == "moving_average":
            return strategy_class(fast_period=cleaned_params["fast_period"], slow_period=cleaned_params["slow_period"])
        if strategy_name == "rsi":
            return strategy_class(
                period=cleaned_params["period"],
                oversold=cleaned_params["oversold"],
                overbought=cleaned_params["overbought"],
            )
        if strategy_name == "bollinger_bands":
            return strategy_class(period=cleaned_params["period"], num_std=cleaned_params["num_std"])
        if strategy_name == "macd":
            return strategy_class(
                fast_period=cleaned_params["fast_period"],
                slow_period=cleaned_params["slow_period"],
                signal_period=cleaned_params["signal_period"],
            )
        if strategy_name == "mean_reversion":
            return strategy_class(
                lookback_period=cleaned_params["lookback_period"],
                entry_threshold=cleaned_params["entry_threshold"],
            )
        if strategy_name == "vwap":
            return strategy_class(period=cleaned_params["period"])
        if strategy_name == "momentum":
            return strategy_class(
                fast_window=cleaned_params["fast_window"],
                slow_window=cleaned_params["slow_window"],
            )
        if strategy_name == "stochastic":
            return strategy_class(
                k_period=cleaned_params["k_period"],
                d_period=cleaned_params["d_period"],
                oversold=cleaned_params["oversold"],
                overbought=cleaned_params["overbought"],
            )
        if strategy_name == "atr_trailing_stop":
            return strategy_class(
                atr_period=cleaned_params["atr_period"],
                atr_multiplier=cleaned_params["atr_multiplier"],
            )
        if strategy_name == "turtle_trading":
            return strategy_class(
                entry_period=cleaned_params["entry_period"],
                exit_period=cleaned_params["exit_period"],
            )
        if strategy_name == "multi_factor":
            return strategy_class(
                momentum_window=cleaned_params["momentum_window"],
                mean_reversion_window=cleaned_params["mean_reversion_window"],
                volume_window=cleaned_params["volume_window"],
                volatility_window=cleaned_params["volatility_window"],
                entry_threshold=cleaned_params["entry_threshold"],
                exit_threshold=cleaned_params["exit_threshold"],
            )
        return strategy_class()

    def _run_backtest_metrics(
        self,
        *,
        symbol: str,
        strategy_name: str,
        params: Dict[str, Any],
        data: pd.DataFrame,
        initial_capital: float,
        commission: float,
        slippage: float,
    ) -> Dict[str, Any]:
        strategy = self._create_strategy(strategy_name, self._validated_parameters(strategy_name, params))
        result = Backtester(
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        ).run(strategy, data.copy())
        result["symbol"] = symbol
        result["strategy"] = strategy_name
        result["parameters"] = params
        normalized = normalize_backtest_results(result)
        metrics = normalized.get("metrics", {})
        metrics.setdefault("final_value", normalized.get("final_value"))
        metrics.setdefault("total_return", normalized.get("total_return"))
        metrics.setdefault("sharpe_ratio", normalized.get("sharpe_ratio"))
        metrics.setdefault("max_drawdown", normalized.get("max_drawdown"))
        return metrics

    def _build_parameter_grid(
        self,
        strategy_name: str,
        base_params: Dict[str, Any],
        *,
        density: int,
    ) -> Dict[str, List[Any]]:
        rules = StrategyValidator.STRATEGY_RULES.get(strategy_name, [])
        grid: Dict[str, List[Any]] = {}
        for rule in rules:
            anchor = base_params.get(rule.name, rule.default)
            if rule.min_value is None or rule.max_value is None:
                grid[rule.name] = [anchor]
                continue
            if density <= 1:
                values = [anchor]
            elif rule.type is int:
                values = np.linspace(rule.min_value, rule.max_value, num=density)
                values = sorted({int(round(value)) for value in values} | {int(anchor)})
            else:
                values = np.linspace(rule.min_value, rule.max_value, num=density)
                values = sorted({round(float(value), 4) for value in values} | {round(float(anchor), 4)})
            grid[rule.name] = list(values)
        return grid

    def _build_parameter_candidates(self, strategy_name: str, parameter_grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        if not parameter_grid:
            return [{}]
        keys = list(parameter_grid.keys())
        raw_candidates = [dict(zip(keys, values)) for values in product(*(parameter_grid[key] for key in keys))]
        candidates = []
        for candidate in raw_candidates:
            is_valid, _, cleaned = StrategyValidator.validate_strategy_params(strategy_name, candidate)
            if is_valid:
                candidates.append(cleaned)
        if not candidates:
            return [{}]
        if len(candidates) <= 180:
            return candidates
        indices = np.linspace(0, len(candidates) - 1, num=180, dtype=int)
        return [candidates[int(index)] for index in sorted(set(indices.tolist()))]

    def _build_heatmap(
        self,
        parameter_grid: Dict[str, List[Any]],
        leaderboard: List[Dict[str, Any]],
        optimization_metric: str,
    ) -> Dict[str, Any]:
        keys = list(parameter_grid.keys())
        if not keys:
            return {"type": "scalar", "metric": optimization_metric, "cells": []}
        if len(keys) == 1:
            key = keys[0]
            return {
                "type": "line",
                "metric": optimization_metric,
                "cells": [
                    {
                        "x": row["parameters"].get(key),
                        "value": row["metrics"].get(optimization_metric),
                    }
                    for row in leaderboard
                ],
            }
        key_x, key_y = keys[:2]
        value_map = {
            (row["parameters"].get(key_x), row["parameters"].get(key_y)): row["metrics"].get(optimization_metric)
            for row in leaderboard
        }
        cells = []
        for y in parameter_grid.get(key_y, []):
            for x in parameter_grid.get(key_x, []):
                cells.append({"x": x, "y": y, "value": value_map.get((x, y))})
        return {
            "type": "matrix",
            "metric": optimization_metric,
            "x_key": key_x,
            "y_key": key_y,
            "x_values": parameter_grid.get(key_x, []),
            "y_values": parameter_grid.get(key_y, []),
            "cells": cells,
        }

    def _build_parameter_stability(
        self,
        best_parameters: Dict[str, Any],
        leaderboard: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        top_slice = leaderboard[: min(len(leaderboard), 10)]
        if not top_slice:
            return {"score": 0.0, "notes": []}
        notes = []
        dispersion_scores = []
        for key, best_value in best_parameters.items():
            values = [_safe_float(item["parameters"].get(key), _safe_float(best_value)) for item in top_slice]
            if not values:
                continue
            spread = float(np.std(values))
            mean_value = abs(float(np.mean(values))) or 1.0
            relative_spread = min(spread / mean_value, 1.0)
            dispersion_scores.append(1.0 - relative_spread)
            notes.append(
                {
                    "parameter": key,
                    "best_value": best_value,
                    "top_band_spread": round(spread, 4),
                    "stability_score": round(1.0 - relative_spread, 4),
                }
            )
        score = float(np.mean(dispersion_scores)) if dispersion_scores else 0.0
        return {"score": round(score, 4), "notes": notes}

    def _load_close_matrix(self, symbols: Iterable[str], period: str) -> pd.DataFrame:
        frames = []
        for symbol in symbols:
            data = self.data_manager.get_historical_data(symbol, period=period)
            if data.empty or "close" not in data.columns:
                continue
            frames.append(data["close"].rename(symbol))
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1).dropna(how="all")

    def _normalize_weights(self, weights: Optional[List[float]], n_assets: int) -> List[float]:
        if not weights or len(weights) != n_assets:
            return [round(1 / n_assets, 4) for _ in range(n_assets)]
        numeric = np.asarray([max(_safe_float(value), 0.0) for value in weights], dtype=float)
        total = float(numeric.sum())
        if total <= 0:
            return [round(1 / n_assets, 4) for _ in range(n_assets)]
        return [round(float(value / total), 4) for value in numeric]

    def _compute_var_cvar(self, returns: pd.Series, *, method: str) -> Dict[str, Any]:
        series = pd.Series(returns).dropna()
        if series.empty:
            return {"confidence_95": None, "confidence_99": None}

        def compute(confidence: float) -> tuple[float, float]:
            if method == "historical":
                threshold = float(series.quantile(1 - confidence))
                tail = series[series <= threshold]
            elif method == "parametric":
                mu = float(series.mean())
                sigma = float(series.std(ddof=0))
                z_score = MODEL_Z_SCORES[confidence]
                threshold = mu - (z_score * sigma)
                simulated = pd.Series(np.random.default_rng(42).normal(mu, sigma or 1e-8, size=2000))
                tail = simulated[simulated <= threshold]
            else:
                mu = float(series.mean())
                sigma = float(series.std(ddof=0))
                simulated = pd.Series(np.random.default_rng(42).normal(mu, sigma or 1e-8, size=3000))
                threshold = float(simulated.quantile(1 - confidence))
                tail = simulated[simulated <= threshold]

            var_value = max(-threshold, 0.0)
            cvar_value = max(-float(tail.mean()) if not tail.empty else var_value, 0.0)
            return round(var_value, 4), round(cvar_value, 4)

        var95, cvar95 = compute(0.95)
        var99, cvar99 = compute(0.99)
        return {
            "confidence_95": {"var": var95, "cvar": cvar95},
            "confidence_99": {"var": var99, "cvar": cvar99},
        }

    def _build_rolling_risk(self, returns: pd.Series) -> List[Dict[str, Any]]:
        series = pd.Series(returns).dropna()
        window = 21
        if len(series) < window:
            return []

        cumulative = (1 + series).cumprod()
        peak = cumulative.cummax()
        drawdown = (cumulative / peak) - 1
        rolling = pd.DataFrame(
            {
                "date": series.index,
                "rolling_return": series.rolling(window).apply(lambda values: float(np.prod(1 + values) - 1), raw=False),
                "rolling_volatility": series.rolling(window).std(ddof=0) * math.sqrt(252),
                "rolling_sharpe": series.rolling(window).apply(
                    lambda values: float(np.mean(values) / np.std(values, ddof=0) * math.sqrt(252)) if np.std(values, ddof=0) > 0 else 0.0,
                    raw=False,
                ),
                "rolling_drawdown": drawdown.rolling(window).min(),
            }
        ).dropna()
        return rolling.tail(90).to_dict("records")

    def _build_correlation_matrix(self, returns: pd.DataFrame) -> Dict[str, Any]:
        correlation = returns.corr().fillna(0.0)
        symbols = list(correlation.columns)
        cells = []
        for row_symbol in symbols:
            for col_symbol in symbols:
                cells.append(
                    {
                        "symbol1": row_symbol,
                        "symbol2": col_symbol,
                        "correlation": round(float(correlation.loc[row_symbol, col_symbol]), 4),
                    }
                )
        return {"symbols": symbols, "cells": cells}

    def _build_factor_decomposition(self, portfolio_returns: pd.Series, period: str) -> Dict[str, Any]:
        factors = _fetch_ff5_factors(period)
        if factors.empty:
            return {"error": "factor data unavailable"}

        portfolio_frame = pd.DataFrame({"portfolio": portfolio_returns.copy()})
        portfolio_frame.index = pd.to_datetime(portfolio_frame.index).tz_localize(None)
        factors = factors.copy()
        factors.index = pd.to_datetime(factors.index).tz_localize(None)
        aligned = portfolio_frame.join(factors, how="inner").dropna()
        if len(aligned) < 30:
            return {"error": "insufficient aligned factor data"}

        y = aligned["portfolio"] - aligned["RF"]
        factor_columns = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
        x = aligned[factor_columns].values
        x_with_const = np.column_stack([np.ones(len(x)), x])
        coeffs = np.linalg.lstsq(x_with_const, y.values, rcond=None)[0]
        premia = aligned[factor_columns].mean() * 252
        contributions = {
            "alpha": round(float(coeffs[0] * 252), 4),
        }
        risk_split = []
        for index, column in enumerate(factor_columns, start=1):
            contribution = float(coeffs[index] * premia[column])
            contributions[column] = round(contribution, 4)
            risk_split.append({"factor": column, "loading": round(float(coeffs[index]), 4), "annual_contribution": round(contribution, 4)})

        total_abs = sum(abs(item["annual_contribution"]) for item in risk_split) or 1.0
        for item in risk_split:
            item["risk_share"] = round(abs(item["annual_contribution"]) / total_abs, 4)

        return {
            "loadings": {
                "alpha": round(float(coeffs[0]), 6),
                "market": round(float(coeffs[1]), 4),
                "size": round(float(coeffs[2]), 4),
                "value": round(float(coeffs[3]), 4),
                "profitability": round(float(coeffs[4]), 4),
                "investment": round(float(coeffs[5]), 4),
            },
            "annualized_contributions": contributions,
            "risk_split": risk_split,
        }

    def _build_stress_tests(self, returns: pd.Series, factor_decomposition: Dict[str, Any]) -> List[Dict[str, Any]]:
        market_beta = _safe_float((factor_decomposition.get("loadings") or {}).get("market"), 1.0)
        volatility = float(pd.Series(returns).std(ddof=0))
        scenarios = [
            {"name": "2008_crisis", "label": "2008 金融危机", "market_shock": -0.28, "vol_multiplier": 2.5},
            {"name": "covid_shock", "label": "COVID 暴跌", "market_shock": -0.18, "vol_multiplier": 2.0},
            {"name": "rate_spike", "label": "利率急升", "market_shock": -0.08, "vol_multiplier": 1.4},
        ]
        results = []
        for scenario in scenarios:
            projected_return = scenario["market_shock"] * market_beta
            projected_var95 = abs(projected_return) + (1.65 * volatility * scenario["vol_multiplier"])
            results.append(
                {
                    "scenario": scenario["name"],
                    "label": scenario["label"],
                    "projected_return": round(projected_return, 4),
                    "projected_var_95": round(projected_var95, 4),
                    "severity": "high" if projected_return <= -0.15 else "medium" if projected_return <= -0.08 else "low",
                }
            )
        return results

    def _build_performance_attribution(self, returns: pd.DataFrame, weights: List[float]) -> Dict[str, Any]:
        asset_returns = ((1 + returns).prod() - 1).to_dict()
        symbols = list(returns.columns)
        benchmark_weights = np.asarray([1 / len(symbols) for _ in symbols], dtype=float)
        portfolio_weights = np.asarray(weights, dtype=float)
        benchmark_return = float(sum(asset_returns[symbol] * benchmark_weights[index] for index, symbol in enumerate(symbols)))

        rows = []
        total_allocation = 0.0
        for index, symbol in enumerate(symbols):
            asset_return = float(asset_returns[symbol])
            allocation = (portfolio_weights[index] - benchmark_weights[index]) * (asset_return - benchmark_return)
            total_allocation += allocation
            rows.append(
                {
                    "symbol": symbol,
                    "portfolio_weight": round(float(portfolio_weights[index]), 4),
                    "benchmark_weight": round(float(benchmark_weights[index]), 4),
                    "asset_return": round(asset_return, 4),
                    "allocation_effect": round(float(allocation), 4),
                    "selection_effect": 0.0,
                    "interaction_effect": 0.0,
                }
            )

        return {
            "benchmark": "equal_weight",
            "rows": rows,
            "totals": {
                "allocation_effect": round(float(total_allocation), 4),
                "selection_effect": 0.0,
                "interaction_effect": 0.0,
                "total_effect": round(float(total_allocation), 4),
            },
        }

    def _series_max_drawdown(self, series: pd.Series) -> float:
        path = pd.Series(series).dropna()
        if path.empty:
            return 0.0
        peak = path.cummax()
        drawdown = (path / peak) - 1
        return float(drawdown.min())

    def _infer_trade_reason(self, trade: Dict[str, Any]) -> str:
        pnl = trade.get("pnl")
        action = str(trade.get("action") or "").upper()
        if action == "BUY":
            return "signal_entry"
        if pnl is None:
            return "position_adjustment"
        return "profit_taking" if _safe_float(pnl) > 0 else "risk_exit"

    def _infer_error_category(self, trade: Dict[str, Any]) -> str:
        pnl = _safe_float(trade.get("pnl"))
        total_amount = _safe_float(trade.get("total_amount"))
        if pnl >= 0:
            return "none"
        if total_amount >= 15000:
            return "oversized_position"
        if total_amount <= 2000:
            return "noise_trade"
        return "timing_error"

    def _group_trade_report(self, trades: List[Dict[str, Any]], *, freq: str) -> List[Dict[str, Any]]:
        if not trades:
            return []
        frame = pd.DataFrame(trades)
        if frame.empty or "timestamp" not in frame.columns:
            return []
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        frame = frame.dropna(subset=["timestamp"])
        if frame.empty:
            return []
        frame["has_realized_pnl"] = frame["pnl"].notna()
        frame["pnl"] = frame["pnl"].fillna(0.0)
        if "signal_strength" not in frame.columns:
            frame["signal_strength"] = np.nan
        frame["signal_strength"] = pd.to_numeric(frame["signal_strength"], errors="coerce")
        grouped = frame.groupby(pd.Grouper(key="timestamp", freq=freq))
        rows = []
        for key, group in grouped:
            if group.empty:
                continue
            closed_group = group[group["has_realized_pnl"]]
            winning = int((closed_group["pnl"] > 0).sum())
            closed_count = int(len(closed_group))
            rows.append(
                {
                    "period": key.strftime("%Y-%m-%d"),
                    "trade_count": int(len(group)),
                    "realized_pnl": round(float(group["pnl"].sum()), 2),
                    "winning_trades": winning,
                    "losing_trades": int((closed_group["pnl"] < 0).sum()),
                    "win_rate": round(winning / max(closed_count, 1), 4),
                    "average_pnl": round(float(closed_group["pnl"].mean()), 2) if closed_count else 0.0,
                    "average_signal_strength": round(float(group["signal_strength"].mean()), 3) if group["signal_strength"].notna().any() else None,
                }
            )
        rows.reverse()
        return rows

    def _build_loss_analysis(self, losing_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not losing_trades:
            return []
        frame = pd.DataFrame(losing_trades)
        if frame.empty:
            return []
        frame["error_category"] = frame["error_category"].fillna("uncategorized")
        frame["risk_bucket"] = frame["risk_bucket"].fillna("unknown")
        frame["pnl"] = pd.to_numeric(frame["pnl"], errors="coerce").fillna(0.0)
        frame["total_amount"] = pd.to_numeric(frame["total_amount"], errors="coerce").fillna(0.0)
        total_abs_loss = abs(float(frame["pnl"].sum())) or 1.0
        rows = []
        for category, group in frame.groupby("error_category"):
            risk_mix = Counter(str(bucket or "unknown") for bucket in group["risk_bucket"].tolist())
            symbols = [symbol for symbol in group["symbol"].value_counts().head(3).index.tolist() if symbol]
            rows.append(
                {
                    "category": category,
                    "count": int(len(group)),
                    "realized_pnl": round(float(group["pnl"].sum()), 2),
                    "share_of_losses": round(abs(float(group["pnl"].sum())) / total_abs_loss, 4),
                    "average_loss": round(float(group["pnl"].mean()), 2),
                    "average_size": round(float(group["total_amount"].mean()), 2),
                    "top_symbols": symbols,
                    "dominant_risk_bucket": risk_mix.most_common(1)[0][0] if risk_mix else "unknown",
                }
            )
        rows.sort(key=lambda item: (item["count"], abs(item["realized_pnl"])), reverse=True)
        return rows

    def _normalize_strategy_lifecycle(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            strategy = str(entry.get("strategy") or entry.get("name") or "").strip()
            if not strategy:
                continue
            stage = str(entry.get("stage") or "discovered").strip().lower().replace(" ", "_")
            status = str(entry.get("status") or ("closed" if stage in {"retired", "archived"} else "active")).strip().lower()
            conviction = entry.get("conviction")
            conviction_value = None
            if conviction not in (None, ""):
                conviction_value = _safe_float(conviction, 0.0)
                if conviction_value > 1:
                    conviction_value = conviction_value / 100.0
                conviction_value = max(0.0, min(conviction_value, 1.0))
            updated_at = str(entry.get("updated_at") or datetime.utcnow().isoformat())
            normalized.append(
                {
                    "id": str(entry.get("id") or f"{strategy.lower().replace(' ', '_')}-{index + 1}"),
                    "strategy": strategy,
                    "stage": stage,
                    "status": status,
                    "owner": str(entry.get("owner") or "research").strip(),
                    "conviction": round(conviction_value, 4) if conviction_value is not None else None,
                    "next_action": str(entry.get("next_action") or "").strip(),
                    "notes": str(entry.get("notes") or "").strip(),
                    "created_at": str(entry.get("created_at") or updated_at),
                    "updated_at": updated_at,
                }
            )
        normalized.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return normalized

    def _build_strategy_lifecycle_summary(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not entries:
            return {
                "total": 0,
                "active": 0,
                "average_conviction": 0.0,
                "stage_breakdown": [],
                "status_breakdown": [],
            }
        stage_breakdown = Counter(str(entry.get("stage") or "unknown") for entry in entries)
        status_breakdown = Counter(str(entry.get("status") or "unknown") for entry in entries)
        convictions = [
            _safe_float(entry.get("conviction"), np.nan)
            for entry in entries
            if entry.get("conviction") not in (None, "")
        ]
        finite_convictions = [value for value in convictions if not math.isnan(value)]
        return {
            "total": len(entries),
            "active": sum(1 for entry in entries if str(entry.get("status") or "").lower() == "active"),
            "average_conviction": round(float(sum(finite_convictions) / len(finite_convictions)), 4) if finite_convictions else 0.0,
            "stage_breakdown": [{"stage": stage, "count": count} for stage, count in stage_breakdown.most_common()],
            "status_breakdown": [{"status": status, "count": count} for status, count in status_breakdown.most_common()],
        }

    def _detect_trading_biases(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not trades:
            return []
        frame = pd.DataFrame(trades)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        frame["pnl"] = frame["pnl"].fillna(0.0)
        active_days = max(frame["timestamp"].dt.date.nunique(), 1)
        trades_per_day = len(frame) / active_days
        avg_win = frame.loc[frame["pnl"] > 0, "pnl"].mean() if (frame["pnl"] > 0).any() else 0.0
        avg_loss = frame.loc[frame["pnl"] < 0, "pnl"].mean() if (frame["pnl"] < 0).any() else 0.0
        top_symbol_share = frame["symbol"].value_counts(normalize=True).max()

        findings = []
        if trades_per_day >= 3:
            findings.append({"bias": "overtrading", "severity": "high", "evidence": f"平均每日 {trades_per_day:.1f} 笔交易"})
        if avg_win and avg_loss and abs(avg_loss) > avg_win * 1.5:
            findings.append({"bias": "disposition_effect", "severity": "medium", "evidence": f"平均亏损 {abs(avg_loss):.2f} 明显大于平均盈利 {avg_win:.2f}"})
        if top_symbol_share and top_symbol_share >= 0.45:
            findings.append({"bias": "concentration_bias", "severity": "medium", "evidence": f"单一标的占交易数 {top_symbol_share:.0%}"})
        if not findings:
            findings.append({"bias": "balanced", "severity": "low", "evidence": "当前交易行为未见明显偏差模式"})
        return findings

    def _calculate_freshness(self, timestamp: Any) -> Optional[float]:
        try:
            ts = pd.Timestamp(timestamp).tz_localize(None) if pd.Timestamp(timestamp).tzinfo else pd.Timestamp(timestamp)
            delta = pd.Timestamp.utcnow().tz_localize(None) - ts
            return round(delta.total_seconds() / 60.0, 2)
        except Exception:
            return None

    def _label_freshness(self, freshness_minutes: Optional[float]) -> str:
        if freshness_minutes is None:
            return "unknown"
        if freshness_minutes <= 30:
            return "fresh"
        if freshness_minutes <= 240:
            return "recent"
        if freshness_minutes <= 1440:
            return "aging"
        return "stale"

    def _score_provider_quality(
        self,
        *,
        status: str,
        freshness_minutes: Optional[float],
        completeness_score: Optional[float],
        latency_ms: float,
    ) -> float:
        score = 1.0
        if status == "degraded":
            score -= 0.25
        elif status == "down":
            score -= 0.55
        freshness_label = self._label_freshness(freshness_minutes)
        freshness_penalty = {
            "fresh": 0.0,
            "recent": 0.08,
            "aging": 0.18,
            "stale": 0.3,
            "unknown": 0.15,
        }.get(freshness_label, 0.15)
        score -= freshness_penalty
        score -= max(0.0, 1.0 - _safe_float(completeness_score, 0.0)) * 0.25
        if latency_ms >= 5000:
            score -= 0.2
        elif latency_ms >= 2000:
            score -= 0.12
        elif latency_ms >= 1000:
            score -= 0.06
        return round(max(0.0, min(score, 1.0)), 4)

    def _build_provider_audit_flags(
        self,
        *,
        status: str,
        freshness_minutes: Optional[float],
        completeness_score: Optional[float],
        latency_ms: float,
    ) -> List[str]:
        flags: List[str] = []
        freshness_label = self._label_freshness(freshness_minutes)
        if status in {"degraded", "down"}:
            flags.append(status)
        if freshness_label in {"aging", "stale"}:
            flags.append(f"{freshness_label}_data")
        if completeness_score is not None and completeness_score < 0.85:
            flags.append("low_completeness")
        if latency_ms >= 2000:
            flags.append("high_latency")
        return flags

    def _build_data_quality_audit(
        self,
        provider_rows: List[Dict[str, Any]],
        failover_log: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        stale_providers = [row for row in provider_rows if row.get("freshness_label") == "stale"]
        degraded_providers = [row for row in provider_rows if row.get("status") in {"degraded", "down"}]
        incomplete_providers = [row for row in provider_rows if _safe_float(row.get("completeness_score"), 0.0) < 0.85]
        high_latency_providers = [row for row in provider_rows if _safe_float(row.get("latency_ms"), 0.0) >= 2000]

        if degraded_providers:
            findings.append({
                "severity": "high",
                "title": "Provider 可用性退化",
                "detail": f"{len(degraded_providers)} 个数据源处于 degraded/down，优先检查故障转移链路。",
            })
        if stale_providers:
            findings.append({
                "severity": "high",
                "title": "存在过期数据源",
                "detail": f"{', '.join(row['provider'] for row in stale_providers[:4])} 数据新鲜度已进入 stale 区间。",
            })
        if incomplete_providers:
            findings.append({
                "severity": "medium",
                "title": "数据完整性不足",
                "detail": f"{len(incomplete_providers)} 个数据源最近样本覆盖不足，可能影响回测稳定性。",
            })
        if high_latency_providers:
            findings.append({
                "severity": "medium",
                "title": "高延迟数据源",
                "detail": f"{len(high_latency_providers)} 个数据源延迟超过 2000ms，实时联动会偏慢。",
            })
        if not findings:
            findings.append({
                "severity": "low",
                "title": "数据质量稳定",
                "detail": "当前 provider 可用性、完整性和新鲜度都处在可接受范围。",
            })

        weakest_provider = None
        if provider_rows:
            weakest_provider = min(
                provider_rows,
                key=lambda item: (
                    _safe_float(item.get("quality_score"), 0.0),
                    -_safe_float(item.get("error_rate_proxy"), 0.0),
                ),
            )

        provider_status_mix = Counter(str(row.get("status") or "unknown") for row in provider_rows)
        failover_hotspots = Counter(str(item.get("provider") or "unknown") for item in failover_log or [])

        return {
            "findings": findings,
            "provider_status_mix": [{"status": status, "count": count} for status, count in provider_status_mix.most_common()],
            "weakest_provider": weakest_provider,
            "failover_hotspots": [{"provider": provider, "count": count} for provider, count in failover_hotspots.most_common(8)],
        }

    def _build_backtest_quality_report(
        self,
        provider_rows: List[Dict[str, Any]],
        failover_log: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not provider_rows:
            return {
                "overall_score": 0.0,
                "risk_level": "unknown",
                "recommendation": "暂无 provider 数据，暂不建议运行正式回测。",
                "drivers": [],
            }

        overall_score = round(
            sum(_safe_float(row.get("quality_score"), 0.0) for row in provider_rows) / max(len(provider_rows), 1),
            4,
        )
        failover_pressure = len(failover_log[:12])
        if overall_score >= 0.82 and failover_pressure <= 2:
            risk_level = "low"
            recommendation = "当前数据质量适合直接进行研究与回测。"
        elif overall_score >= 0.65:
            risk_level = "medium"
            recommendation = "建议先关注过期或高延迟 provider，再运行关键策略回测。"
        else:
            risk_level = "high"
            recommendation = "不建议把当前数据直接用于关键回测，优先处理 provider 退化与故障转移。"

        sorted_rows = sorted(provider_rows, key=lambda item: _safe_float(item.get("quality_score"), 0.0))
        drivers = [
            {
                "provider": row.get("provider"),
                "quality_score": row.get("quality_score"),
                "freshness_label": row.get("freshness_label"),
                "status": row.get("status"),
                "flags": row.get("audit_flags") or [],
            }
            for row in sorted_rows[:5]
        ]
        return {
            "overall_score": overall_score,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "drivers": drivers,
        }

    def _failover_event(self, provider_name: str, reason: str) -> Dict[str, Any]:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "provider": provider_name,
            "reason": reason,
        }

    def _build_valuation_ensemble(
        self,
        *,
        current_price: float,
        dcf_value: Optional[float],
        comparable_value: Optional[float],
        monte_carlo: Dict[str, Any],
    ) -> Dict[str, Any]:
        anchors = []
        if dcf_value:
            anchors.append(("dcf", dcf_value, 0.45))
        if comparable_value:
            anchors.append(("comparable", comparable_value, 0.35))
        monte_carlo_p50 = monte_carlo.get("p50")
        if monte_carlo_p50:
            anchors.append(("monte_carlo", _safe_float(monte_carlo_p50), 0.20))
        if not anchors:
            return {"fair_value": None, "confidence_interval": None, "gap_pct": None, "models": []}

        total_weight = sum(weight for _, _, weight in anchors) or 1.0
        fair_value = sum(value * weight for _, value, weight in anchors) / total_weight
        confidence_low = monte_carlo.get("p10") or min(value for _, value, _ in anchors)
        confidence_high = monte_carlo.get("p90") or max(value for _, value, _ in anchors)
        gap_pct = ((current_price - fair_value) / fair_value) * 100 if fair_value else None
        return {
            "fair_value": round(float(fair_value), 2),
            "confidence_interval": {
                "low": round(float(confidence_low), 2),
                "high": round(float(confidence_high), 2),
            },
            "gap_pct": round(float(gap_pct), 2) if gap_pct is not None else None,
            "models": [
                {"model": name, "value": round(float(value), 2), "weight": round(float(weight / total_weight), 4)}
                for name, value, weight in anchors
            ],
        }

    def _append_valuation_history(
        self,
        symbol: str,
        period: str,
        ensemble: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        filepath = self.storage_root / "valuation_history" / f"{symbol}.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        payload = self._read_store(filepath, default=[])
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "period": period,
            "fair_value": ensemble.get("fair_value"),
            "gap_pct": ensemble.get("gap_pct"),
            "market_price": ((analysis.get("valuation") or {}).get("current_price")),
            "confidence_interval": ensemble.get("confidence_interval"),
        }
        payload = [entry, *(payload or [])][:60]
        self._write_store(filepath, payload)
        return payload[:30]

    def _build_peer_matrix(self, symbol: str, requested_peers: List[str], peer_limit: int) -> Dict[str, Any]:
        candidate_symbols = requested_peers or list(peer_candidate_pool(symbol))
        comparison = self.pricing_analyzer.build_peer_comparison(symbol, candidate_symbols, limit=peer_limit)
        rows = [comparison.get("target"), *(comparison.get("peers") or [])]
        rows = [row for row in rows if row]
        if not rows:
            return {
                "rows": [],
                "summary": {
                    "peer_count": 0,
                    "custom_peer_count": len(requested_peers),
                    "auto_candidate_count": len(candidate_symbols),
                },
            }

        enriched_rows = []
        for row in rows:
            fundamentals = self.data_manager.get_fundamental_data(row.get("symbol")) or {}
            revenue_growth = _normalize_ratio(_pick_metric(
                fundamentals,
                "revenue_growth",
                "revenue_growth_yoy",
                "revenue_growth_rate",
            ))
            earnings_growth = _normalize_ratio(_pick_metric(
                fundamentals,
                "earnings_growth",
                "eps_growth",
                "net_income_growth",
                "profit_growth",
            ))
            roe = _normalize_ratio(_pick_metric(
                fundamentals,
                "return_on_equity",
                "roe",
            ))
            profit_margin = _normalize_ratio(_pick_metric(
                fundamentals,
                "profit_margin",
                "net_margin",
                "operating_margin",
            ))

            growth_score_components = [
                _score_higher_better(revenue_growth, -0.2, 0.35),
                _score_higher_better(earnings_growth, -0.2, 0.35),
            ]
            quality_score_components = [
                _score_higher_better(roe, -0.05, 0.35),
                _score_higher_better(profit_margin, -0.1, 0.3),
            ]
            value_score_components = [
                _score_lower_better(_normalize_ratio(_pick_metric(row, "premium_discount")), -0.5, 0.5),
                _score_lower_better(_normalize_ratio(_pick_metric(row, "pe_ratio")), 0.0, 0.6),
                _score_lower_better(_normalize_ratio(_pick_metric(row, "price_to_sales")), 0.0, 0.4),
            ]

            growth_values = [item for item in growth_score_components if item is not None]
            quality_values = [item for item in quality_score_components if item is not None]
            value_values = [item for item in value_score_components if item is not None]

            growth_score = sum(growth_values) / len(growth_values) if growth_values else None
            quality_score = sum(quality_values) / len(quality_values) if quality_values else None
            value_score = sum(value_values) / len(value_values) if value_values else None

            overall_components = [item for item in [value_score, growth_score, quality_score] if item is not None]
            overall_score = sum(overall_components) / len(overall_components) if overall_components else None
            enriched_rows.append({
                **row,
                "revenue_growth": revenue_growth,
                "earnings_growth": earnings_growth,
                "return_on_equity": roe,
                "profit_margin": profit_margin,
                "value_score": round(float(value_score), 4) if value_score is not None else None,
                "growth_score": round(float(growth_score), 4) if growth_score is not None else None,
                "quality_score": round(float(quality_score), 4) if quality_score is not None else None,
                "overall_score": round(float(overall_score), 4) if overall_score is not None else None,
                "peer_source": "custom" if row.get("symbol") in requested_peers else "auto",
            })

        ranked_rows = sorted(
            enriched_rows,
            key=lambda item: (
                int(bool(item.get("is_target"))),
                float(item.get("overall_score") or 0.0),
                -float(item.get("premium_discount") or 0.0),
            ),
            reverse=True,
        )
        for index, row in enumerate(ranked_rows, start=1):
            row["rank"] = index

        peer_rows = [row for row in ranked_rows if not row.get("is_target")]
        summary = {
            "peer_count": len(peer_rows),
            "custom_peer_count": sum(1 for row in peer_rows if row.get("peer_source") == "custom"),
            "auto_candidate_count": len(candidate_symbols),
            "median_peer_premium_discount": round(float(pd.Series([item.get("premium_discount") for item in peer_rows]).dropna().median()), 2)
            if peer_rows and pd.Series([item.get("premium_discount") for item in peer_rows]).dropna().size
            else None,
            "median_peer_value_score": round(float(pd.Series([item.get("value_score") for item in peer_rows]).dropna().median()), 4)
            if peer_rows and pd.Series([item.get("value_score") for item in peer_rows]).dropna().size
            else None,
        }
        return {
            "rows": ranked_rows,
            "summary": summary,
            "sector": comparison.get("sector"),
            "industry": comparison.get("industry"),
        }

    def _profile_file(self, name: str, profile_id: str | None) -> Path:
        normalized_profile = str(profile_id or "default").strip().lower().replace("/", "-")
        folder = self.storage_root / name
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{normalized_profile}.json"

    def _read_store(self, filepath: Path, default: Any) -> Any:
        try:
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as file:
                    return json.load(file)
        except Exception as exc:  # pragma: no cover - disk corruption edge
            logger.warning("Failed to read %s: %s", filepath, exc)
        return default

    def _write_store(self, filepath: Path, payload: Any) -> None:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(_json_ready(payload), file, ensure_ascii=False, indent=2)


quant_lab_service = QuantLabService()
