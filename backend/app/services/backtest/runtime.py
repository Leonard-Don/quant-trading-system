"""Synchronous backtest orchestration and request models."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.app.api.v1.endpoints._backtest_impact import (
    _default_market_impact_scenarios,
    _market_impact_curve,
)
from backend.app.core.task_queue import task_queue_manager
from backend.app.schemas.backtest import BacktestRequest
from backend.app.services.runtime_state import get_data_manager
from src.analytics.dashboard import PerformanceAnalyzer
from src.backtest.backtester import Backtester
from src.backtest.batch_backtester import BatchBacktester
from src.backtest.impact_model import normalize_market_impact_model
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
from src.utils.data_validation import (
    ensure_json_serializable,
    normalize_backtest_results,
    validate_and_fix_backtest_results,
)

logger = logging.getLogger(__name__)
data_manager = get_data_manager()

STRATEGIES = {
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


def _estimate_min_history_bars(strategy_name: str, cleaned_params: dict[str, Any]) -> int:
    if strategy_name == "moving_average":
        return int(cleaned_params.get("slow_period", 50))
    if strategy_name == "rsi":
        return int(cleaned_params.get("period", 14))
    if strategy_name == "bollinger_bands":
        return int(cleaned_params.get("period", 20))
    if strategy_name == "macd":
        return int(
            max(
                cleaned_params.get("slow_period", 26),
                cleaned_params.get("signal_period", 9),
            )
        )
    if strategy_name == "mean_reversion":
        return int(cleaned_params.get("lookback_period", 20))
    if strategy_name == "vwap":
        return int(cleaned_params.get("period", 20))
    if strategy_name == "momentum":
        return int(cleaned_params.get("slow_window", 30))
    if strategy_name == "stochastic":
        return int(cleaned_params.get("k_period", 14))
    if strategy_name == "atr_trailing_stop":
        return int(cleaned_params.get("atr_period", 14))
    if strategy_name == "turtle_trading":
        return int(
            max(cleaned_params.get("entry_period", 20), cleaned_params.get("exit_period", 10))
        )
    if strategy_name == "multi_factor":
        return int(
            max(
                cleaned_params.get("momentum_window", 20),
                cleaned_params.get("mean_reversion_window", 20),
                cleaned_params.get("volume_window", 10),
                cleaned_params.get("volatility_window", 20),
            )
        )
    return 1


def _build_no_trade_diagnostics(
    *,
    strategy_name: str,
    cleaned_params: dict[str, Any],
    data: pd.DataFrame,
    strategy,
) -> dict[str, Any]:
    available_bars = len(data)
    required_bars = _estimate_min_history_bars(strategy_name, cleaned_params)
    signal_series = getattr(strategy, "signals", pd.Series(dtype="float64"))
    signal_series = (
        pd.Series(signal_series, copy=False)
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
        .astype(float)
    )
    buy_signal_count = int((signal_series > 0).sum())
    sell_signal_count = int((signal_series < 0).sum())
    signal_count = buy_signal_count + sell_signal_count

    reason_code = "no_signal_triggered"
    summary = "The selected window did not trigger any actionable signals."

    if required_bars > 1 and available_bars < required_bars:
        reason_code = "insufficient_history_window"
        summary = (
            f"Only {available_bars} bars were available, which is below the estimated "
            f"minimum lookback of {required_bars} bars for {strategy_name}."
        )
    elif signal_count == 0:
        reason_code = "no_signal_triggered"
    else:
        reason_code = "signals_not_executed"
        summary = (
            f"The strategy produced {signal_count} raw signals, but none were executed into trades."
        )

    return {
        "reason_code": reason_code,
        "summary": summary,
        "available_bars": available_bars,
        "estimated_required_bars": required_bars,
        "buy_signal_count": buy_signal_count,
        "sell_signal_count": sell_signal_count,
        "signal_count": signal_count,
        "strategy_name": strategy_name,
        "strategy_parameters": dict(cleaned_params),
    }


def _parse_iso_datetime(value: Optional[str], field_name: str) -> Optional[datetime]:
    """Parse ISO datetime strings used by the backtest API."""
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: {value}",
        ) from exc


def _resolve_date_range(
    start_date: Optional[str], end_date: Optional[str]
) -> tuple[Optional[datetime], Optional[datetime]]:
    start_dt = _parse_iso_datetime(start_date, "start_date")
    end_dt = _parse_iso_datetime(end_date, "end_date")

    if start_dt and end_dt and start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    return start_dt, end_dt


def _fetch_backtest_data(symbol: str, start_date: Optional[str], end_date: Optional[str]):
    start_dt, end_dt = _resolve_date_range(start_date, end_date)
    logger.info(f"Fetching data for {symbol} from {start_dt} to {end_dt}")
    data = data_manager.get_historical_data(symbol=symbol, start_date=start_dt, end_date=end_dt)
    if data.empty:
        logger.warning(f"No data found for symbol {symbol}")
        raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")
    logger.info(f"Retrieved {len(data)} data points")
    return data


def _create_strategy_instance(strategy_name: str, cleaned_params: dict[str, Any]):
    strategy_class = STRATEGIES[strategy_name]

    try:
        if strategy_name == "moving_average":
            return strategy_class(
                fast_period=cleaned_params["fast_period"],
                slow_period=cleaned_params["slow_period"],
            )
        if strategy_name == "rsi":
            return strategy_class(
                period=cleaned_params["period"],
                oversold=cleaned_params["oversold"],
                overbought=cleaned_params["overbought"],
            )
        if strategy_name == "bollinger_bands":
            return strategy_class(
                period=cleaned_params["period"], num_std=cleaned_params["num_std"]
            )
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
    except (ValueError, TypeError) as exc:
        logger.error(f"Failed to create strategy instance: {exc}")
        raise HTTPException(status_code=500, detail=f"Strategy creation failed: {exc!s}") from exc


def run_backtest_pipeline(
    *,
    symbol: str,
    strategy_name: str,
    parameters: Optional[dict[str, Any]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 10000,
    commission: float = 0.001,
    slippage: float = 0.001,
    fixed_commission: float = 0.0,
    min_commission: float = 0.0,
    market_impact_bps: float = 0.0,
    market_impact_model: str = "constant",
    impact_reference_notional: float = 100000.0,
    impact_coefficient: float = 1.0,
    permanent_impact_bps: float = 0.0,
    execution_lag: int = 1,
    max_holding_days: Optional[int] = None,
    data=None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the normalized backtest execution pipeline used by all endpoints."""
    logger.info(f"Starting backtest for {symbol} with strategy {strategy_name}")

    if strategy_name not in STRATEGIES:
        logger.warning(f"Unknown strategy requested: {strategy_name}")
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_name}")

    if initial_capital <= 0:
        raise HTTPException(status_code=400, detail="Initial capital must be positive")

    _resolve_date_range(start_date, end_date)

    if data is None:
        data = _fetch_backtest_data(symbol, start_date, end_date)

    is_valid, error_msg, cleaned_params = StrategyValidator.validate_strategy_params(
        strategy_name, parameters or {}
    )
    if not is_valid:
        logger.warning(f"Invalid strategy parameters: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

    strategy = _create_strategy_instance(strategy_name, cleaned_params)
    logger.info(f"Running backtest with strategy: {strategy.name}")

    backtester = Backtester(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        fixed_commission=fixed_commission,
        min_commission=min_commission,
        market_impact_bps=market_impact_bps,
        market_impact_model=market_impact_model,
        impact_reference_notional=impact_reference_notional,
        impact_coefficient=impact_coefficient,
        permanent_impact_bps=permanent_impact_bps,
        execution_lag=execution_lag,
        max_holding_days=max_holding_days,
    )
    results = backtester.run(strategy, data)
    results = validate_and_fix_backtest_results(results)

    analyzer = PerformanceAnalyzer(results)
    results.update(analyzer.calculate_metrics())
    results.update(
        {
            "symbol": symbol,
            "strategy": strategy_name,
            "start_date": start_date,
            "end_date": end_date,
            "commission": commission,
            "slippage": slippage,
            "fixed_commission": fixed_commission,
            "min_commission": min_commission,
            "market_impact_bps": market_impact_bps,
            "market_impact_model": normalize_market_impact_model(market_impact_model),
            "impact_reference_notional": impact_reference_notional,
            "impact_coefficient": impact_coefficient,
            "permanent_impact_bps": permanent_impact_bps,
            "execution_lag": execution_lag,
            "max_holding_days": max_holding_days,
            "parameters": cleaned_params,
        }
    )
    if not results.get("trades"):
        results["no_trade_diagnostics"] = _build_no_trade_diagnostics(
            strategy_name=strategy_name,
            cleaned_params=cleaned_params,
            data=data,
            strategy=strategy,
        )
    results = normalize_backtest_results(results)
    results = ensure_json_serializable(results)
    return results, cleaned_params


def _build_comparison_entry(results: dict[str, Any]) -> dict[str, Any]:
    comparison_entry = {
        "symbol": results.get("symbol"),
        "strategy": results.get("strategy"),
        "parameters": results.get("parameters", {}),
        "total_return": results.get("total_return", 0),
        "annualized_return": results.get("annualized_return", 0),
        "sharpe_ratio": results.get("sharpe_ratio", 0),
        "max_drawdown": results.get("max_drawdown", 0),
        "num_trades": results.get("num_trades", 0),
        "total_trades": results.get("total_trades", results.get("num_trades", 0)),
        "win_rate": results.get("win_rate", 0),
        "profit_factor": results.get("profit_factor", 0),
        "final_value": results.get("final_value", 0),
    }
    normalized = normalize_backtest_results(comparison_entry)
    normalized["metrics"] = {
        key: normalized.get(key)
        for key in [
            "total_return",
            "annualized_return",
            "sharpe_ratio",
            "max_drawdown",
            "num_trades",
            "total_trades",
            "win_rate",
            "profit_factor",
            "final_value",
        ]
    }
    return normalized


def _build_batch_backtester(max_workers: int, use_processes: bool = False) -> BatchBacktester:
    return BatchBacktester(max_workers=max_workers, use_processes=use_processes)


def _strategy_factory_for_batch(strategy_name: str, parameters: dict[str, Any]):
    is_valid, error_msg, cleaned_params = StrategyValidator.validate_strategy_params(
        strategy_name, parameters or {}
    )
    if not is_valid:
        raise ValueError(error_msg)
    return _create_strategy_instance(strategy_name, cleaned_params)


def _series_from_portfolio_history(results: dict[str, Any]) -> pd.Series:
    portfolio_history = results.get("portfolio_history") or results.get("portfolio") or []
    if not portfolio_history:
        return pd.Series(dtype="float64")

    frame = pd.DataFrame(portfolio_history)
    if frame.empty or "total" not in frame.columns:
        return pd.Series(dtype="float64")

    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame.get("date"), utc=True, errors="coerce")
    frame["date"] = frame["date"].dt.tz_localize(None)
    frame = frame.dropna(subset=["date"]).sort_values("date")
    if frame.empty:
        return pd.Series(dtype="float64")

    return pd.Series(frame["total"].astype(float).values, index=frame["date"])


def _calculate_max_drawdown_from_series(values: pd.Series) -> float:
    if values.empty:
        return 0.0

    running_max = values.cummax()
    drawdown = (values - running_max) / running_max.replace(0, np.nan)
    drawdown = drawdown.replace([np.inf, -np.inf], np.nan).fillna(0)
    return float(drawdown.min())


def _returns_from_portfolio_history(results: dict[str, Any]) -> pd.Series:
    values = _series_from_portfolio_history(results)
    if values.empty:
        return pd.Series(dtype="float64")

    returns = values.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
    returns.index = pd.to_datetime(returns.index, utc=True, errors="coerce").tz_localize(None)
    returns = returns[~returns.index.isna()]
    return returns.astype(float)


def _equity_curve_from_returns(
    returns: np.ndarray,
    initial_value: float,
) -> np.ndarray:
    return initial_value * np.cumprod(1 + returns)


def _max_drawdown_from_array(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    running_max = np.maximum.accumulate(values)
    drawdown = (values - running_max) / np.where(running_max == 0, np.nan, running_max)
    drawdown = np.nan_to_num(drawdown, nan=0.0, posinf=0.0, neginf=0.0)
    return float(np.min(drawdown))


def _simulate_monte_carlo_paths(
    returns: pd.Series,
    *,
    initial_value: float,
    simulations: int,
    horizon_days: Optional[int] = None,
    seed: Optional[int] = 42,
) -> dict[str, Any]:
    clean_returns = pd.Series(returns).replace([np.inf, -np.inf], np.nan).dropna()
    clean_returns = clean_returns[clean_returns.index.notna()]
    if clean_returns.empty:
        raise HTTPException(
            status_code=400, detail="Insufficient return series for Monte Carlo simulation"
        )

    horizon = max(5, min(int(horizon_days or len(clean_returns)), 756))
    sample_count = max(50, min(int(simulations or 1000), 10000))
    rng = np.random.default_rng(seed)
    source = clean_returns.to_numpy(dtype="float64")

    terminal_values = np.empty(sample_count, dtype="float64")
    path_returns = np.empty(sample_count, dtype="float64")
    max_drawdowns = np.empty(sample_count, dtype="float64")
    sampled_paths = []
    percentile_source = []

    for index in range(sample_count):
        sampled_returns = rng.choice(source, size=horizon, replace=True)
        equity = _equity_curve_from_returns(sampled_returns, initial_value)
        terminal_values[index] = equity[-1]
        path_returns[index] = (equity[-1] / initial_value) - 1
        max_drawdowns[index] = _max_drawdown_from_array(equity)
        if index < 40:
            sampled_paths.append([round(float(value), 2) for value in equity])
        if index < min(sample_count, 1500):
            percentile_source.append(equity)

    percentile_frame = np.vstack(percentile_source)
    fan_chart = []
    for day_index in range(horizon):
        day_values = percentile_frame[:, day_index]
        if day_index == 0 or day_index == horizon - 1 or day_index % max(1, horizon // 40) == 0:
            fan_chart.append(
                {
                    "step": day_index + 1,
                    "p10": round(float(np.percentile(day_values, 10)), 2),
                    "p50": round(float(np.percentile(day_values, 50)), 2),
                    "p90": round(float(np.percentile(day_values, 90)), 2),
                }
            )

    return {
        "simulations": sample_count,
        "horizon_days": horizon,
        "initial_value": round(float(initial_value), 2),
        "terminal_value": {
            "p05": round(float(np.percentile(terminal_values, 5)), 2),
            "p10": round(float(np.percentile(terminal_values, 10)), 2),
            "p50": round(float(np.percentile(terminal_values, 50)), 2),
            "p90": round(float(np.percentile(terminal_values, 90)), 2),
            "p95": round(float(np.percentile(terminal_values, 95)), 2),
        },
        "return_distribution": {
            "mean": round(float(np.mean(path_returns)), 6),
            "median": round(float(np.median(path_returns)), 6),
            "p05": round(float(np.percentile(path_returns, 5)), 6),
            "p95": round(float(np.percentile(path_returns, 95)), 6),
            "probability_of_loss": round(float(np.mean(path_returns < 0)), 4),
            "var_95": round(float(np.percentile(path_returns, 5)), 6),
            "cvar_95": round(
                float(path_returns[path_returns <= np.percentile(path_returns, 5)].mean()), 6
            ),
        },
        "drawdown_distribution": {
            "median": round(float(np.median(max_drawdowns)), 6),
            "p05": round(float(np.percentile(max_drawdowns, 5)), 6),
            "worst": round(float(np.min(max_drawdowns)), 6),
        },
        "fan_chart": fan_chart,
        "sample_paths": sampled_paths,
    }


def _safe_sharpe(returns: pd.Series) -> float:
    values = pd.Series(returns).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty or float(values.std(ddof=0)) == 0:
        return 0.0
    return float(values.mean() / values.std(ddof=0) * np.sqrt(252))


def _compare_return_significance(
    baseline: pd.Series,
    challenger: pd.Series,
    *,
    bootstrap_samples: int = 1000,
    seed: Optional[int] = 42,
) -> dict[str, Any]:
    aligned = pd.concat(
        [baseline.rename("baseline"), challenger.rename("challenger")], axis=1
    ).dropna()
    if aligned.empty or len(aligned) < 10:
        return {"status": "insufficient_data", "sample_size": len(aligned)}

    diff = aligned["challenger"] - aligned["baseline"]
    observed_mean_delta = float(diff.mean())
    observed_sharpe_delta = _safe_sharpe(aligned["challenger"]) - _safe_sharpe(aligned["baseline"])

    try:
        from scipy import stats

        t_stat, p_value = stats.ttest_rel(
            aligned["challenger"], aligned["baseline"], nan_policy="omit"
        )
        t_stat = float(0 if np.isnan(t_stat) else t_stat)
        p_value = float(1 if np.isnan(p_value) else p_value)
    except Exception:
        std = float(diff.std(ddof=1))
        t_stat = float(observed_mean_delta / (std / np.sqrt(len(diff)))) if std > 0 else 0.0
        p_value = 1.0

    rng = np.random.default_rng(seed)
    sample_count = max(100, min(int(bootstrap_samples or 1000), 10000))
    boot_deltas = np.empty(sample_count, dtype="float64")
    raw = diff.to_numpy(dtype="float64")
    for index in range(sample_count):
        boot_deltas[index] = float(rng.choice(raw, size=len(raw), replace=True).mean())

    if observed_mean_delta >= 0:
        bootstrap_p = float(2 * min(np.mean(boot_deltas <= 0), np.mean(boot_deltas >= 0)))
    else:
        bootstrap_p = float(2 * min(np.mean(boot_deltas >= 0), np.mean(boot_deltas <= 0)))
    bootstrap_p = min(max(bootstrap_p, 0.0), 1.0)

    return {
        "status": "ok",
        "sample_size": len(aligned),
        "observed_mean_daily_delta": round(observed_mean_delta, 8),
        "observed_annualized_delta": round(float(observed_mean_delta * 252), 6),
        "observed_sharpe_delta": round(float(observed_sharpe_delta), 6),
        "paired_t_test": {
            "t_stat": round(float(t_stat), 6),
            "p_value": round(float(p_value), 6),
            "significant_95": bool(p_value < 0.05),
        },
        "bootstrap": {
            "samples": sample_count,
            "p_value": round(float(bootstrap_p), 6),
            "ci_95": [
                round(float(np.percentile(boot_deltas, 2.5)), 8),
                round(float(np.percentile(boot_deltas, 97.5)), 8),
            ],
            "significant_95": bool(bootstrap_p < 0.05),
        },
    }


def _classify_market_regimes(
    close_prices: pd.Series,
    lookback_days: int = 20,
    trend_threshold: float = 0.03,
) -> pd.DataFrame:
    if close_prices is None or close_prices.empty:
        return pd.DataFrame(columns=["date", "regime", "market_return"])

    prices = close_prices.astype(float).dropna().copy()
    prices.index = pd.to_datetime(prices.index, utc=True, errors="coerce").tz_localize(None)
    prices = prices[~prices.index.isna()]
    if prices.empty:
        return pd.DataFrame(columns=["date", "regime", "market_return"])

    max_lookback = max(len(prices) - 1, 1)
    effective_lookback = min(max(int(lookback_days or 20), 2), max_lookback)
    vol_window = min(max(3, effective_lookback // 2), max(len(prices), 3))

    market_returns = prices.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
    trend_returns = (
        prices.pct_change(periods=effective_lookback).replace([np.inf, -np.inf], np.nan).fillna(0)
    )
    rolling_vol = (
        market_returns.rolling(vol_window, min_periods=2).std().replace([np.inf, -np.inf], np.nan)
    )

    vol_reference = (
        float(rolling_vol.dropna().median())
        if not rolling_vol.dropna().empty
        else float(abs(market_returns).median())
    )
    high_vol_threshold = (
        vol_reference * 1.15 if vol_reference > 0 else float(abs(market_returns).mean())
    )

    def _label_regime(date):
        trend_value = float(trend_returns.loc[date] or 0)
        volatility_value = (
            float(rolling_vol.loc[date] or 0) if pd.notna(rolling_vol.loc[date]) else 0.0
        )
        if trend_value >= trend_threshold:
            return "上涨趋势"
        if trend_value <= -abs(trend_threshold):
            return "下跌趋势"
        if high_vol_threshold > 0 and volatility_value >= high_vol_threshold:
            return "高波动震荡"
        return "低波动整理"

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(prices.index, utc=True, errors="coerce").tz_localize(None),
            "market_return": market_returns.values,
        }
    )
    frame["regime"] = frame["date"].apply(_label_regime)
    return frame


class CompareStrategyConfig(BaseModel):
    name: str
    parameters: dict[str, Any] = {}


class CompareRequest(BaseModel):
    symbol: str
    strategies: Optional[list[str]] = None
    strategy_configs: Optional[list[CompareStrategyConfig]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000.0
    commission: float = 0.001
    slippage: float = 0.001
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0
    execution_lag: int = 1
    max_holding_days: Optional[int] = None


class MonteCarloBacktestRequest(BacktestRequest):
    simulations: int = 1000
    horizon_days: Optional[int] = None
    seed: Optional[int] = 42


class SignificanceCompareRequest(CompareRequest):
    baseline_strategy: Optional[str] = None
    bootstrap_samples: int = 1000
    seed: Optional[int] = 42


class MultiPeriodBacktestRequest(BacktestRequest):
    intervals: list[str] = Field(default_factory=lambda: ["1d", "1wk", "1mo"])


class MarketImpactScenarioConfig(BaseModel):
    label: Optional[str] = None
    market_impact_model: str = "constant"
    market_impact_bps: float = 0.0
    impact_reference_notional: Optional[float] = None
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0


class MarketImpactAnalysisRequest(BacktestRequest):
    scenarios: Optional[list[MarketImpactScenarioConfig]] = None
    sample_trade_values: list[float] = Field(default_factory=lambda: [10000, 50000, 100000, 250000])


def _submit_async_backtest_task(task_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    task = task_queue_manager.submit(
        name=task_name,
        payload={
            **payload,
            "task_origin": "backtest",
        },
        backend="auto",
    )
    return {
        "task": task,
        "execution_backend": task.get("execution_backend"),
        "message": "backtest task queued",
    }


def run_backtest_monte_carlo_sync(
    request: MonteCarloBacktestRequest | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(request, dict):
        request = MonteCarloBacktestRequest(**request)
    results, cleaned_params = run_backtest_pipeline(
        symbol=request.symbol,
        strategy_name=request.strategy,
        parameters=request.parameters,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_capital=request.initial_capital,
        commission=request.commission,
        slippage=request.slippage,
        fixed_commission=request.fixed_commission,
        min_commission=request.min_commission,
        market_impact_bps=request.market_impact_bps,
        market_impact_model=request.market_impact_model,
        impact_reference_notional=request.impact_reference_notional,
        impact_coefficient=request.impact_coefficient,
        permanent_impact_bps=request.permanent_impact_bps,
        execution_lag=request.execution_lag,
        max_holding_days=request.max_holding_days,
    )
    returns = _returns_from_portfolio_history(results)
    simulation = _simulate_monte_carlo_paths(
        returns,
        initial_value=float(results.get("final_value") or request.initial_capital),
        simulations=request.simulations,
        horizon_days=request.horizon_days,
        seed=request.seed,
    )
    return ensure_json_serializable(
        {
            "success": True,
            "data": {
                "symbol": request.symbol,
                "strategy": request.strategy,
                "parameters": cleaned_params,
                "base_metrics": _build_comparison_entry(results),
                "monte_carlo": simulation,
            },
        }
    )


def compare_strategy_significance_sync(
    request: SignificanceCompareRequest | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(request, dict):
        request = SignificanceCompareRequest(**request)
    configs = _normalize_compare_configs(
        strategies=request.strategies,
        strategy_configs=request.strategy_configs,
    )
    if len(configs) < 2:
        raise HTTPException(
            status_code=400, detail="At least two strategies are required for significance testing"
        )

    data = _fetch_backtest_data(request.symbol, request.start_date, request.end_date)
    strategy_results = []
    for config in configs:
        result, cleaned_params = run_backtest_pipeline(
            symbol=request.symbol,
            strategy_name=config["name"],
            parameters=config.get("parameters") or {},
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            commission=request.commission,
            slippage=request.slippage,
            fixed_commission=request.fixed_commission,
            min_commission=request.min_commission,
            market_impact_bps=request.market_impact_bps,
            market_impact_model=request.market_impact_model,
            impact_reference_notional=request.impact_reference_notional,
            impact_coefficient=request.impact_coefficient,
            permanent_impact_bps=request.permanent_impact_bps,
            execution_lag=request.execution_lag,
            max_holding_days=request.max_holding_days,
            data=data,
        )
        strategy_results.append(
            {
                "name": config["name"],
                "parameters": cleaned_params,
                "metrics": _build_comparison_entry(result),
                "returns": _returns_from_portfolio_history(result),
            }
        )

    baseline_name = request.baseline_strategy or strategy_results[0]["name"]
    baseline = next(
        (item for item in strategy_results if item["name"] == baseline_name), strategy_results[0]
    )
    comparisons = []
    for item in strategy_results:
        if item["name"] == baseline["name"]:
            continue
        comparisons.append(
            {
                "baseline": baseline["name"],
                "challenger": item["name"],
                "baseline_metrics": baseline["metrics"],
                "challenger_metrics": item["metrics"],
                "significance": _compare_return_significance(
                    baseline["returns"],
                    item["returns"],
                    bootstrap_samples=request.bootstrap_samples,
                    seed=request.seed,
                ),
            }
        )

    return ensure_json_serializable(
        {
            "success": True,
            "data": {
                "symbol": request.symbol,
                "baseline_strategy": baseline["name"],
                "comparisons": comparisons,
            },
        }
    )


def run_multi_period_backtest_sync(
    request: MultiPeriodBacktestRequest | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(request, dict):
        request = MultiPeriodBacktestRequest(**request)
    allowed_intervals = {"1d", "1wk", "1mo"}
    intervals = []
    for interval in request.intervals or ["1d", "1wk", "1mo"]:
        normalized_interval = str(interval).strip()
        if normalized_interval not in allowed_intervals:
            raise HTTPException(
                status_code=400, detail=f"Unsupported interval: {normalized_interval}"
            )
        if normalized_interval not in intervals:
            intervals.append(normalized_interval)
    if not intervals:
        raise HTTPException(status_code=400, detail="At least one interval is required")

    start_dt, end_dt = _resolve_date_range(request.start_date, request.end_date)
    rows = []
    for interval in intervals:
        data = data_manager.get_historical_data(
            symbol=request.symbol,
            start_date=start_dt,
            end_date=end_dt,
            interval=interval,
        )
        if data.empty:
            rows.append({"interval": interval, "success": False, "error": "No data"})
            continue
        result, cleaned_params = run_backtest_pipeline(
            symbol=request.symbol,
            strategy_name=request.strategy,
            parameters=request.parameters,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            commission=request.commission,
            slippage=request.slippage,
            fixed_commission=request.fixed_commission,
            min_commission=request.min_commission,
            market_impact_bps=request.market_impact_bps,
            market_impact_model=request.market_impact_model,
            impact_reference_notional=request.impact_reference_notional,
            impact_coefficient=request.impact_coefficient,
            permanent_impact_bps=request.permanent_impact_bps,
            execution_lag=request.execution_lag,
            max_holding_days=request.max_holding_days,
            data=data,
        )
        entry = _build_comparison_entry(result)
        rows.append(
            {
                "interval": interval,
                "success": True,
                "data_points": len(data),
                "parameters": cleaned_params,
                "metrics": entry,
            }
        )

    successful_rows = [row for row in rows if row.get("success")]
    best = max(
        successful_rows,
        key=lambda row: float(row["metrics"].get("sharpe_ratio") or 0),
        default=None,
    )
    return ensure_json_serializable(
        {
            "success": True,
            "data": {
                "symbol": request.symbol,
                "strategy": request.strategy,
                "intervals": rows,
                "summary": {
                    "successful_intervals": len(successful_rows),
                    "best_by_sharpe": best,
                    "average_return": float(
                        np.mean([row["metrics"].get("total_return", 0) for row in successful_rows])
                    )
                    if successful_rows
                    else 0.0,
                },
            },
        }
    )


def run_market_impact_analysis_sync(
    request: MarketImpactAnalysisRequest | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(request, dict):
        request = MarketImpactAnalysisRequest(**request)
    data = _fetch_backtest_data(request.symbol, request.start_date, request.end_date)
    scenario_specs = request.scenarios or []
    scenarios = [
        {
            "label": scenario.label or f"scenario_{index}",
            "market_impact_model": normalize_market_impact_model(scenario.market_impact_model),
            "market_impact_bps": float(scenario.market_impact_bps or 0.0),
            "impact_reference_notional": float(
                scenario.impact_reference_notional or request.impact_reference_notional
            ),
            "impact_coefficient": float(scenario.impact_coefficient or 1.0),
            "permanent_impact_bps": float(scenario.permanent_impact_bps or 0.0),
        }
        for index, scenario in enumerate(scenario_specs, start=1)
    ] or _default_market_impact_scenarios(request)

    scenario_results = []
    for scenario in scenarios:
        result, cleaned_params = run_backtest_pipeline(
            symbol=request.symbol,
            strategy_name=request.strategy,
            parameters=request.parameters,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            commission=request.commission,
            slippage=request.slippage,
            fixed_commission=request.fixed_commission,
            min_commission=request.min_commission,
            market_impact_bps=scenario["market_impact_bps"],
            market_impact_model=scenario["market_impact_model"],
            impact_reference_notional=scenario["impact_reference_notional"],
            impact_coefficient=scenario["impact_coefficient"],
            permanent_impact_bps=scenario["permanent_impact_bps"],
            execution_lag=request.execution_lag,
            max_holding_days=request.max_holding_days,
            data=data,
        )
        scenario_results.append(
            {
                "label": scenario["label"],
                "scenario": scenario,
                "parameters": cleaned_params,
                "metrics": _build_comparison_entry(result),
                "execution_costs": result.get("execution_costs", {}),
                "impact_curve": _market_impact_curve(
                    scenario=scenario,
                    data=data,
                    sample_trade_values=request.sample_trade_values,
                ),
            }
        )

    baseline = scenario_results[0] if scenario_results else None
    baseline_return = float(baseline["metrics"].get("total_return", 0) or 0) if baseline else 0.0
    baseline_sharpe = float(baseline["metrics"].get("sharpe_ratio", 0) or 0) if baseline else 0.0
    baseline_cost = (
        float(baseline["execution_costs"].get("estimated_market_impact_cost", 0) or 0)
        if baseline
        else 0.0
    )
    for scenario_result in scenario_results:
        scenario_result["vs_baseline"] = {
            "return_delta": round(
                float(scenario_result["metrics"].get("total_return", 0) or 0) - baseline_return, 6
            ),
            "sharpe_delta": round(
                float(scenario_result["metrics"].get("sharpe_ratio", 0) or 0) - baseline_sharpe, 6
            ),
            "impact_cost_delta": round(
                float(
                    scenario_result["execution_costs"].get("estimated_market_impact_cost", 0) or 0
                )
                - baseline_cost,
                2,
            ),
        }

    return ensure_json_serializable(
        {
            "success": True,
            "data": {
                "symbol": request.symbol,
                "strategy": request.strategy,
                "sample_trade_values": request.sample_trade_values,
                "scenarios": scenario_results,
                "summary": {
                    "scenario_count": len(scenario_results),
                    "best_by_sharpe": max(
                        scenario_results,
                        key=lambda item: float(item["metrics"].get("sharpe_ratio", 0) or 0),
                        default=None,
                    ),
                },
            },
        }
    )


def _normalize_compare_configs(
    strategies: Optional[list[str]] = None,
    strategy_configs: Optional[list[CompareStrategyConfig]] = None,
) -> list[dict[str, Any]]:
    if strategy_configs:
        configs = [
            {
                "name": config.name.strip(),
                "parameters": config.parameters or {},
            }
            for config in strategy_configs
            if config.name and config.name.strip()
        ]
    else:
        configs = [
            {
                "name": name.strip(),
                "parameters": {},
            }
            for name in (strategies or [])
            if name and name.strip()
        ]

    if not configs:
        raise HTTPException(status_code=400, detail="At least one strategy is required")

    return configs


async def _compare_strategies_impl(
    *,
    symbol: str,
    strategy_configs: list[dict[str, Any]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_capital: float = 10000.0,
    commission: float = 0.001,
    slippage: float = 0.001,
    fixed_commission: float = 0.0,
    min_commission: float = 0.0,
    market_impact_bps: float = 0.0,
    market_impact_model: str = "constant",
    impact_reference_notional: float = 100000.0,
    impact_coefficient: float = 1.0,
    permanent_impact_bps: float = 0.0,
    execution_lag: int = 1,
    max_holding_days: Optional[int] = None,
):
    data = _fetch_backtest_data(symbol, start_date, end_date)

    def _run_single_strategy(config):
        strategy_name = config["name"]
        if strategy_name not in STRATEGIES:
            return None

        res, _ = run_backtest_pipeline(
            symbol=symbol,
            strategy_name=strategy_name,
            parameters=config.get("parameters") or {},
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
            fixed_commission=fixed_commission,
            min_commission=min_commission,
            market_impact_bps=market_impact_bps,
            market_impact_model=market_impact_model,
            impact_reference_notional=impact_reference_notional,
            impact_coefficient=impact_coefficient,
            permanent_impact_bps=permanent_impact_bps,
            execution_lag=execution_lag,
            max_holding_days=max_holding_days,
            data=data,
        )

        return {
            "name": strategy_name,
            "metrics": _build_comparison_entry(res),
        }

    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _run_single_strategy, config) for config in strategy_configs
    ]
    completed_strategies = await asyncio.gather(*tasks)
    valid_results = [r for r in completed_strategies if r is not None]

    if not valid_results:
        return {"success": True, "data": {}}

    max_return = max(r["metrics"]["total_return"] for r in valid_results)
    min_return = min(r["metrics"]["total_return"] for r in valid_results)
    max_sharpe = max(r["metrics"]["sharpe_ratio"] for r in valid_results)
    min_sharpe = min(r["metrics"]["sharpe_ratio"] for r in valid_results)
    max_dd = max(abs(r["metrics"]["max_drawdown"]) for r in valid_results)
    min_dd = min(abs(r["metrics"]["max_drawdown"]) for r in valid_results)

    def normalize(val, min_v, max_v, inverse=False):
        if max_v == min_v:
            return 50.0
        score = (val - min_v) / (max_v - min_v) * 100
        return 100 - score if inverse else score

    scored_results = []
    for item in valid_results:
        metrics = item["metrics"]

        return_score = normalize(metrics["total_return"], min_return, max_return)
        sharpe_score = normalize(metrics["sharpe_ratio"], min_sharpe, max_sharpe)
        risk_score = normalize(abs(metrics["max_drawdown"]), min_dd, max_dd, inverse=True)
        overall_score = (return_score * 0.4) + (sharpe_score * 0.3) + (risk_score * 0.3)

        metrics["scores"] = {
            "return_score": round(return_score),
            "sharpe_score": round(sharpe_score),
            "risk_score": round(risk_score),
            "overall_score": round(overall_score),
        }
        scored_results.append(item)

    scored_results.sort(key=lambda x: x["metrics"]["scores"]["overall_score"], reverse=True)

    final_data = {}
    for idx, item in enumerate(scored_results):
        metrics = item["metrics"]
        metrics["rank"] = idx + 1
        metrics["metrics"] = {
            **metrics.get("metrics", {}),
            "rank": idx + 1,
        }
        final_data[item["name"]] = metrics

    return {"success": True, "data": final_data}
