import base64
from fastapi import APIRouter, HTTPException
import asyncio
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from backend.app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    BatchBacktestRequest,
    WalkForwardRequest,
    MarketRegimeRequest,
    PortfolioStrategyRequest,
    AdvancedHistorySaveRequest,
)
from backend.app.core.task_queue import task_queue_manager
from src.backtest.history import backtest_history
from src.backtest.batch_backtester import BatchBacktester, BacktestTask, WalkForwardAnalyzer
from src.backtest.impact_model import estimate_market_impact_rate, normalize_market_impact_model
from src.data.data_manager import DataManager
from src.strategy.strategies import (
    MovingAverageCrossover,
    RSIStrategy,
    BollingerBands,
    BuyAndHold,
    TurtleTradingStrategy,
    MultiFactorStrategy,
)
from src.strategy.advanced_strategies import (
    MACDStrategy,
    MeanReversionStrategy,
    VWAPStrategy,
    MomentumStrategy,
    StochasticOscillator,
    ATRTrailingStop,
)
from src.strategy.strategy_validator import StrategyValidator
from src.backtest.backtester import Backtester
from src.backtest.portfolio_backtester import PortfolioBacktester
from src.backtest.signal_adapter import SignalAdapter
from src.analytics.dashboard import PerformanceAnalyzer
from src.analytics.portfolio_optimizer import PortfolioOptimizer as AssetPortfolioOptimizer
from src.utils.performance import timing_decorator
from src.utils.data_validation import (
    validate_and_fix_backtest_results,
    ensure_json_serializable,
    normalize_backtest_results,
)
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)
data_manager = DataManager()

# 策略映射
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
) -> Tuple[Optional[datetime], Optional[datetime]]:
    start_dt = _parse_iso_datetime(start_date, "start_date")
    end_dt = _parse_iso_datetime(end_date, "end_date")

    if start_dt and end_dt and start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    return start_dt, end_dt


def _fetch_backtest_data(
    symbol: str, start_date: Optional[str], end_date: Optional[str]
):
    start_dt, end_dt = _resolve_date_range(start_date, end_date)
    logger.info(f"Fetching data for {symbol} from {start_dt} to {end_dt}")
    data = data_manager.get_historical_data(
        symbol=symbol, start_date=start_dt, end_date=end_dt
    )
    if data.empty:
        logger.warning(f"No data found for symbol {symbol}")
        raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")
    logger.info(f"Retrieved {len(data)} data points")
    return data


def _create_strategy_instance(strategy_name: str, cleaned_params: Dict[str, Any]):
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
        raise HTTPException(
            status_code=500, detail=f"Strategy creation failed: {str(exc)}"
        ) from exc


def run_backtest_pipeline(
    *,
    symbol: str,
    strategy_name: str,
    parameters: Optional[Dict[str, Any]] = None,
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
    max_holding_days: Optional[int] = None,
    data=None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
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
            "max_holding_days": max_holding_days,
            "parameters": cleaned_params,
        }
    )
    results = normalize_backtest_results(results)
    results = ensure_json_serializable(results)
    return results, cleaned_params


def _build_comparison_entry(results: Dict[str, Any]) -> Dict[str, Any]:
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


def _strategy_factory_for_batch(strategy_name: str, parameters: Dict[str, Any]):
    is_valid, error_msg, cleaned_params = StrategyValidator.validate_strategy_params(
        strategy_name, parameters or {}
    )
    if not is_valid:
        raise ValueError(error_msg)
    return _create_strategy_instance(strategy_name, cleaned_params)


def _series_from_portfolio_history(results: Dict[str, Any]) -> pd.Series:
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


def _returns_from_portfolio_history(results: Dict[str, Any]) -> pd.Series:
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
) -> Dict[str, Any]:
    clean_returns = pd.Series(returns).replace([np.inf, -np.inf], np.nan).dropna()
    clean_returns = clean_returns[clean_returns.index.notna()]
    if clean_returns.empty:
        raise HTTPException(status_code=400, detail="Insufficient return series for Monte Carlo simulation")

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
            "cvar_95": round(float(path_returns[path_returns <= np.percentile(path_returns, 5)].mean()), 6),
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
) -> Dict[str, Any]:
    aligned = pd.concat([baseline.rename("baseline"), challenger.rename("challenger")], axis=1).dropna()
    if aligned.empty or len(aligned) < 10:
        return {"status": "insufficient_data", "sample_size": int(len(aligned))}

    diff = aligned["challenger"] - aligned["baseline"]
    observed_mean_delta = float(diff.mean())
    observed_sharpe_delta = _safe_sharpe(aligned["challenger"]) - _safe_sharpe(aligned["baseline"])

    try:
        from scipy import stats

        t_stat, p_value = stats.ttest_rel(aligned["challenger"], aligned["baseline"], nan_policy="omit")
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
        "sample_size": int(len(aligned)),
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
    trend_returns = prices.pct_change(periods=effective_lookback).replace([np.inf, -np.inf], np.nan).fillna(0)
    rolling_vol = market_returns.rolling(vol_window, min_periods=2).std().replace([np.inf, -np.inf], np.nan)

    vol_reference = float(rolling_vol.dropna().median()) if not rolling_vol.dropna().empty else float(abs(market_returns).median())
    high_vol_threshold = vol_reference * 1.15 if vol_reference > 0 else float(abs(market_returns).mean())

    def _label_regime(date):
        trend_value = float(trend_returns.loc[date] or 0)
        volatility_value = float(rolling_vol.loc[date] or 0) if pd.notna(rolling_vol.loc[date]) else 0.0
        if trend_value >= trend_threshold:
            return "上涨趋势"
        if trend_value <= -abs(trend_threshold):
            return "下跌趋势"
        if high_vol_threshold > 0 and volatility_value >= high_vol_threshold:
            return "高波动震荡"
        return "低波动整理"

    frame = pd.DataFrame({
        "date": pd.to_datetime(prices.index, utc=True, errors="coerce").tz_localize(None),
        "market_return": market_returns.values,
    })
    frame["regime"] = frame["date"].apply(_label_regime)
    return frame


class CompareStrategyConfig(BaseModel):
    name: str
    parameters: Dict[str, Any] = {}


class CompareRequest(BaseModel):
    symbol: str
    strategies: Optional[List[str]] = None
    strategy_configs: Optional[List[CompareStrategyConfig]] = None
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
    intervals: List[str] = ["1d", "1wk", "1mo"]


class MarketImpactScenarioConfig(BaseModel):
    label: Optional[str] = None
    market_impact_model: str = "constant"
    market_impact_bps: float = 0.0
    impact_reference_notional: Optional[float] = None
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0


class MarketImpactAnalysisRequest(BacktestRequest):
    scenarios: Optional[List[MarketImpactScenarioConfig]] = None
    sample_trade_values: List[float] = [10000, 50000, 100000, 250000]


def _submit_async_backtest_task(task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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
    request: MonteCarloBacktestRequest | Dict[str, Any],
) -> Dict[str, Any]:
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
    request: SignificanceCompareRequest | Dict[str, Any],
) -> Dict[str, Any]:
    if isinstance(request, dict):
        request = SignificanceCompareRequest(**request)
    configs = _normalize_compare_configs(
        strategies=request.strategies,
        strategy_configs=request.strategy_configs,
    )
    if len(configs) < 2:
        raise HTTPException(status_code=400, detail="At least two strategies are required for significance testing")

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
    baseline = next((item for item in strategy_results if item["name"] == baseline_name), strategy_results[0])
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
    request: MultiPeriodBacktestRequest | Dict[str, Any],
) -> Dict[str, Any]:
    if isinstance(request, dict):
        request = MultiPeriodBacktestRequest(**request)
    allowed_intervals = {"1d", "1wk", "1mo"}
    intervals = []
    for interval in request.intervals or ["1d", "1wk", "1mo"]:
        normalized_interval = str(interval).strip()
        if normalized_interval not in allowed_intervals:
            raise HTTPException(status_code=400, detail=f"Unsupported interval: {normalized_interval}")
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
            max_holding_days=request.max_holding_days,
            data=data,
        )
        entry = _build_comparison_entry(result)
        rows.append(
            {
                "interval": interval,
                "success": True,
                "data_points": int(len(data)),
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
                    "average_return": float(np.mean([row["metrics"].get("total_return", 0) for row in successful_rows])) if successful_rows else 0.0,
                },
            },
        }
    )


def run_market_impact_analysis_sync(
    request: MarketImpactAnalysisRequest | Dict[str, Any],
) -> Dict[str, Any]:
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
    baseline_cost = float(baseline["execution_costs"].get("estimated_market_impact_cost", 0) or 0) if baseline else 0.0
    for scenario_result in scenario_results:
        scenario_result["vs_baseline"] = {
            "return_delta": round(float(scenario_result["metrics"].get("total_return", 0) or 0) - baseline_return, 6),
            "sharpe_delta": round(float(scenario_result["metrics"].get("sharpe_ratio", 0) or 0) - baseline_sharpe, 6),
            "impact_cost_delta": round(
                float(scenario_result["execution_costs"].get("estimated_market_impact_cost", 0) or 0) - baseline_cost,
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


def _market_impact_curve(
    *,
    scenario: Dict[str, Any],
    data: pd.DataFrame,
    sample_trade_values: List[float],
) -> List[Dict[str, Any]]:
    close_prices = pd.to_numeric(data.get("close"), errors="coerce").dropna()
    reference_price = float(close_prices.iloc[-1]) if not close_prices.empty else 100.0
    returns = close_prices.pct_change().replace([np.inf, -np.inf], np.nan)
    volatility_reference = float(returns.std()) if returns.dropna().size else 0.02
    if "volume" in data.columns:
        volumes = pd.to_numeric(data["volume"], errors="coerce").clip(lower=0)
        dollar_volume = (pd.to_numeric(data["close"], errors="coerce") * volumes).replace([np.inf, -np.inf], np.nan)
        liquidity_reference = (
            float(dollar_volume.dropna().median())
            if dollar_volume.dropna().size
            else float(scenario["impact_reference_notional"])
        )
    else:
        liquidity_reference = float(scenario["impact_reference_notional"])
    liquidity_reference = max(liquidity_reference, float(scenario["impact_reference_notional"]), 1.0)

    rows = []
    for trade_value in sample_trade_values:
        trade_notional = max(float(trade_value or 0.0), 0.0)
        impact = estimate_market_impact_rate(
            trade_notional,
            market_impact_bps=scenario["market_impact_bps"],
            model=scenario["market_impact_model"],
            avg_daily_notional=liquidity_reference,
            volatility=volatility_reference,
            impact_coefficient=scenario["impact_coefficient"],
            permanent_impact_bps=scenario["permanent_impact_bps"],
            reference_notional=scenario["impact_reference_notional"],
        )
        rows.append(
            {
                "trade_value": trade_notional,
                "reference_price": reference_price,
                "estimated_shares": round(float(trade_notional / reference_price), 4) if reference_price > 0 else 0.0,
                "market_impact_rate": round(float(impact["impact_rate"]), 6),
                "market_impact_bps": round(float(impact["impact_rate"]) * 10000, 2),
                "participation_rate": round(float(impact["participation_rate"]), 4),
                "estimated_cost": round(float(trade_notional * float(impact["impact_rate"])), 2),
            }
        )
    return rows


def _default_market_impact_scenarios(request: MarketImpactAnalysisRequest) -> List[Dict[str, Any]]:
    return [
        {
            "label": "无冲击基线",
            "market_impact_model": "constant",
            "market_impact_bps": 0.0,
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": 1.0,
            "permanent_impact_bps": 0.0,
        },
        {
            "label": "线性冲击",
            "market_impact_model": "linear",
            "market_impact_bps": max(float(request.market_impact_bps or 8.0), 8.0),
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": max(float(request.impact_coefficient or 1.0), 1.0),
            "permanent_impact_bps": 0.0,
        },
        {
            "label": "平方根冲击",
            "market_impact_model": "sqrt",
            "market_impact_bps": max(float(request.market_impact_bps or 12.0), 12.0),
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": max(float(request.impact_coefficient or 1.0), 1.15),
            "permanent_impact_bps": 0.0,
        },
        {
            "label": "Almgren-Chriss",
            "market_impact_model": "almgren_chriss",
            "market_impact_bps": max(float(request.market_impact_bps or 18.0), 18.0),
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": max(float(request.impact_coefficient or 1.0), 1.2),
            "permanent_impact_bps": max(float(request.permanent_impact_bps or 4.0), 4.0),
        },
    ]


@router.post("/batch", summary="批量运行多个回测任务")
async def run_batch_backtest(request: BatchBacktestRequest):
    try:
        batch = _build_batch_backtester(request.max_workers, request.use_processes)
        if request.timeout_seconds <= 0:
            raise HTTPException(status_code=400, detail="Timeout seconds must be positive")
        tasks = [
            BacktestTask(
                task_id=item.task_id or f"task_{index}",
                symbol=item.symbol,
                strategy_name=item.strategy,
                parameters=item.parameters,
                start_date=item.start_date,
                end_date=item.end_date,
                initial_capital=item.initial_capital,
                commission=item.commission,
                slippage=item.slippage,
                research_label=item.research_label,
            )
            for index, item in enumerate(request.tasks, start=1)
        ]

        results = await asyncio.wait_for(
            asyncio.to_thread(
                batch.run_batch,
                tasks=tasks,
                backtester_factory=Backtester,
                strategy_factory=_strategy_factory_for_batch,
                data_fetcher=_fetch_backtest_data,
            ),
            timeout=request.timeout_seconds,
        )

        ranked_results = batch.get_ranked_results(
            metric=request.ranking_metric,
            ascending=request.ascending,
            top_n=request.top_n,
        )

        return ensure_json_serializable({
            "success": True,
            "data": {
                "summary": batch.get_summary(),
                "execution": {
                    "max_workers": request.max_workers,
                    "use_processes": request.use_processes,
                    "timeout_seconds": request.timeout_seconds,
                },
                "results": [
                    {
                        "task_id": result.task_id,
                        "symbol": result.symbol,
                        "strategy": result.strategy_name,
                        "parameters": result.parameters,
                        "research_label": result.research_label,
                        "metrics": result.metrics,
                        "success": result.success,
                        "error": result.error,
                        "execution_time": result.execution_time,
                    }
                    for result in results
                ],
                "ranked_results": [
                    {
                        "task_id": result.task_id,
                        "symbol": result.symbol,
                        "strategy": result.strategy_name,
                        "parameters": result.parameters,
                        "research_label": result.research_label,
                        "metrics": result.metrics,
                        "success": result.success,
                        "execution_time": result.execution_time,
                    }
                    for result in ranked_results
                ],
            },
        })
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Batch backtest timed out") from exc
    except Exception as e:
        logger.error(f"Error running batch backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/walk-forward", summary="运行 Walk-Forward 分析")
async def run_walk_forward_backtest(request: WalkForwardRequest):
    try:
        if request.train_period <= 0 or request.test_period <= 0 or request.step_size <= 0:
            raise HTTPException(status_code=400, detail="Train/test/step periods must be positive")
        if request.monte_carlo_simulations <= 0:
            raise HTTPException(status_code=400, detail="Monte Carlo simulations must be positive")
        if request.optimization_method not in {"grid", "bayesian"}:
            raise HTTPException(status_code=400, detail="Optimization method must be grid or bayesian")
        if request.optimization_budget is not None and request.optimization_budget <= 0:
            raise HTTPException(status_code=400, detail="Optimization budget must be positive")
        if request.timeout_seconds <= 0:
            raise HTTPException(status_code=400, detail="Timeout seconds must be positive")

        data = _fetch_backtest_data(request.symbol, request.start_date, request.end_date)
        is_valid, error_msg, cleaned_params = StrategyValidator.validate_strategy_params(
            request.strategy, request.parameters or {}
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        analyzer = WalkForwardAnalyzer(
            train_period=request.train_period,
            test_period=request.test_period,
            step_size=request.step_size,
        )
        result = await asyncio.wait_for(
            asyncio.to_thread(
                analyzer.analyze,
                data=data,
                strategy_factory=lambda parameters=None: _strategy_factory_for_batch(
                    request.strategy,
                    {**cleaned_params, **(parameters or {})},
                ),
                backtester_factory=lambda: Backtester(
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
                    max_holding_days=request.max_holding_days,
                ),
                parameter_grid=request.parameter_grid,
                parameter_candidates=request.parameter_candidates,
                optimization_metric=request.optimization_metric,
                optimization_method=request.optimization_method,
                optimization_budget=request.optimization_budget,
                monte_carlo_simulations=request.monte_carlo_simulations,
            ),
            timeout=request.timeout_seconds,
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return ensure_json_serializable({
            "success": True,
            "data": {
                "symbol": request.symbol,
                "strategy": request.strategy,
                "parameters": cleaned_params,
                "train_period": request.train_period,
                "test_period": request.test_period,
                "step_size": request.step_size,
                "optimization_metric": request.optimization_metric,
                "optimization_method": request.optimization_method,
                "optimization_budget": request.optimization_budget,
                "monte_carlo_simulations": request.monte_carlo_simulations,
                "timeout_seconds": request.timeout_seconds,
                **result,
            },
        })
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Walk-forward analysis timed out") from exc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running walk-forward backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/market-regimes", summary="运行市场状态分层回测")
async def run_market_regime_backtest(request: MarketRegimeRequest):
    try:
        if request.lookback_days <= 1:
            raise HTTPException(status_code=400, detail="Lookback days must be greater than 1")
        if request.trend_threshold <= 0:
            raise HTTPException(status_code=400, detail="Trend threshold must be positive")

        data = _fetch_backtest_data(request.symbol, request.start_date, request.end_date)
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
            max_holding_days=request.max_holding_days,
            data=data,
        )

        close_column = "close" if "close" in data.columns else "Close"
        regime_frame = _classify_market_regimes(
            data[close_column],
            lookback_days=request.lookback_days,
            trend_threshold=request.trend_threshold,
        )
        strategy_returns = _returns_from_portfolio_history(results).rename("strategy_return")

        if regime_frame.empty or strategy_returns.empty:
            raise HTTPException(status_code=400, detail="Insufficient data for market regime analysis")

        aligned = regime_frame.set_index("date").join(strategy_returns, how="left")
        aligned["strategy_return"] = aligned["strategy_return"].fillna(0.0)

        regime_order = {
            "上涨趋势": 0,
            "下跌趋势": 1,
            "高波动震荡": 2,
            "低波动整理": 3,
        }
        regime_results = []
        for regime_name, group in aligned.groupby("regime"):
            strategy_curve = (1 + group["strategy_return"]).cumprod()
            market_curve = (1 + group["market_return"]).cumprod()
            strategy_total_return = float(strategy_curve.iloc[-1] - 1) if not strategy_curve.empty else 0.0
            market_total_return = float(market_curve.iloc[-1] - 1) if not market_curve.empty else 0.0
            positive_days = int((group["strategy_return"] > 0).sum())
            days = int(len(group))

            regime_results.append({
                "regime": regime_name,
                "days": days,
                "positive_days": positive_days,
                "win_rate": float(positive_days / days) if days else 0.0,
                "average_daily_return": float(group["strategy_return"].mean()) if days else 0.0,
                "strategy_total_return": strategy_total_return,
                "market_total_return": market_total_return,
                "max_drawdown": _calculate_max_drawdown_from_series(strategy_curve) if not strategy_curve.empty else 0.0,
            })

        regime_results.sort(key=lambda item: regime_order.get(item["regime"], 99))
        strongest = max(regime_results, key=lambda item: item["strategy_total_return"])
        weakest = min(regime_results, key=lambda item: item["strategy_total_return"])
        positive_regimes = sum(1 for item in regime_results if item["strategy_total_return"] > 0)

        return ensure_json_serializable({
            "success": True,
            "data": {
                "symbol": request.symbol,
                "strategy": request.strategy,
                "parameters": cleaned_params,
                "lookback_days": request.lookback_days,
                "trend_threshold": request.trend_threshold,
                "summary": {
                    "regime_count": len(regime_results),
                    "positive_regimes": positive_regimes,
                    "average_regime_return": float(np.mean([item["strategy_total_return"] for item in regime_results])) if regime_results else 0.0,
                    "strongest_regime": strongest,
                    "weakest_regime": weakest,
                },
                "regimes": regime_results,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running market regime backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/portfolio-strategy", summary="运行组合级策略回测")
async def run_portfolio_strategy_backtest(request: PortfolioStrategyRequest):
    try:
        symbols = [symbol.strip().upper() for symbol in request.symbols if symbol and symbol.strip()]
        if len(symbols) < 2:
            raise HTTPException(status_code=400, detail="Portfolio strategy backtest requires at least 2 symbols")

        if request.strategy not in STRATEGIES:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {request.strategy}")

        is_valid, error_msg, cleaned_params = StrategyValidator.validate_strategy_params(
            request.strategy, request.parameters or {}
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        objective = str(request.objective or "equal_weight").lower()
        if objective not in {"equal_weight", "max_sharpe", "min_volatility"}:
            raise HTTPException(status_code=400, detail="Objective must be one of: equal_weight, max_sharpe, min_volatility")

        weights = request.weights or []
        if weights and len(weights) != len(symbols):
            raise HTTPException(status_code=400, detail="Weights length must match symbols length")

        price_data = {}
        raw_weights = np.array(weights if weights else [1.0] * len(symbols), dtype="float64")
        if np.any(raw_weights < 0):
            raise HTTPException(status_code=400, detail="Weights must be non-negative")
        if float(raw_weights.sum()) <= 0:
            raise HTTPException(status_code=400, detail="Weights must sum to a positive value")

        component_results = []
        target_exposure_frames = []

        for index, symbol in enumerate(symbols):
            data = _fetch_backtest_data(symbol, request.start_date, request.end_date)
            close_column = "close" if "close" in data.columns else "Close"
            price_data[symbol] = data[close_column]
            result, _ = run_backtest_pipeline(
                symbol=symbol,
                strategy_name=request.strategy,
                parameters=cleaned_params,
                start_date=request.start_date,
                end_date=request.end_date,
                initial_capital=float(request.initial_capital),
                commission=request.commission,
                slippage=request.slippage,
                fixed_commission=request.fixed_commission,
                min_commission=request.min_commission,
                market_impact_bps=request.market_impact_bps,
                market_impact_model=request.market_impact_model,
                impact_reference_notional=request.impact_reference_notional,
                impact_coefficient=request.impact_coefficient,
                permanent_impact_bps=request.permanent_impact_bps,
                data=data,
            )
            strategy_instance = _create_strategy_instance(request.strategy, cleaned_params)
            target_exposure = SignalAdapter.single_asset_to_target_exposure(
                strategy_instance.generate_signals(data),
                index=data.index,
            ).rename(symbol)
            target_exposure_frames.append(target_exposure)

            component_series = _series_from_portfolio_history(result)
            if component_series.empty:
                continue

            component_results.append({
                "symbol": symbol,
                "total_return": float(result.get("total_return", 0) or 0),
                "annualized_return": float(result.get("annualized_return", 0) or 0),
                "max_drawdown": float(result.get("max_drawdown", 0) or 0),
                "final_value": float(result.get("final_value", 0) or 0),
                "num_trades": int(result.get("num_trades", 0) or 0),
            })

        if len(component_results) < 2 or not target_exposure_frames:
            raise HTTPException(status_code=400, detail="Insufficient valid component results for portfolio strategy backtest")

        price_frame = pd.DataFrame({symbol: price_data[symbol] for symbol in symbols}).dropna()
        target_exposure_frame = pd.concat(target_exposure_frames, axis=1).reindex(price_frame.index).ffill().fillna(0.0)
        ordered_symbols = list(target_exposure_frame.columns)
        if weights:
            normalized_weights = np.array(
                [raw_weights[symbols.index(symbol)] for symbol in ordered_symbols],
                dtype="float64",
            )
            normalized_weights = normalized_weights / normalized_weights.sum()
        elif objective == "equal_weight":
            normalized_weights = np.array([1.0 / len(ordered_symbols)] * len(ordered_symbols), dtype="float64")
        else:
            optimizer = AssetPortfolioOptimizer()
            optimization_result = optimizer.optimize_portfolio(
                price_frame,
                objective="max_sharpe" if objective == "max_sharpe" else "min_volatility",
            )
            if not optimization_result.get("success"):
                raise HTTPException(status_code=400, detail=optimization_result.get("error", "Portfolio optimization failed"))
            weight_map = optimization_result["optimal_portfolio"]["weights"]
            normalized_weights = np.array([float(weight_map.get(symbol, 0)) for symbol in ordered_symbols], dtype="float64")
            normalized_weights = normalized_weights / normalized_weights.sum()

        weight_map = {
            symbol: float(weight)
            for symbol, weight in zip(ordered_symbols, normalized_weights)
        }
        weighted_target_signals = target_exposure_frame.mul(
            pd.Series(weight_map),
            axis=1,
        )

        portfolio_results = PortfolioBacktester(
            initial_capital=float(request.initial_capital),
            commission=request.commission,
            slippage=request.slippage,
            allow_fractional_shares=True,
            max_gross_exposure=1.0,
            min_trade_value=request.min_trade_value,
            min_rebalance_weight_delta=request.min_rebalance_weight_delta,
            max_turnover_per_rebalance=request.max_turnover_per_rebalance,
            fixed_commission=request.fixed_commission,
            min_commission=request.min_commission,
            market_impact_bps=request.market_impact_bps,
            market_impact_model=request.market_impact_model,
            impact_reference_notional=request.impact_reference_notional,
            impact_coefficient=request.impact_coefficient,
            permanent_impact_bps=request.permanent_impact_bps,
        ).run(
            strategy=type(
                "PortfolioStrategyWrapper",
                (),
                {"generate_signals": lambda self, _: weighted_target_signals},
            )(),
            data=price_frame,
        )
        portfolio_history = portfolio_results.get("portfolio_history", [])
        positions_history = portfolio_results.get("positions_history", [])
        total_return = float(portfolio_results.get("total_return", 0) or 0)
        annualized_return = float(portfolio_results.get("annualized_return", 0) or 0)
        volatility = float(portfolio_results.get("volatility", 0) or 0)
        sharpe_ratio = float(portfolio_results.get("sharpe_ratio", 0) or 0)
        max_drawdown = float(portfolio_results.get("max_drawdown", 0) or 0)
        aggregate_trades = int(portfolio_results.get("num_trades", 0) or 0)
        final_value = float(portfolio_results.get("final_value", request.initial_capital) or request.initial_capital)

        for component in component_results:
            component["weight"] = float(normalized_weights[ordered_symbols.index(component["symbol"])])

        results = normalize_backtest_results({
            "symbol": ",".join(symbols),
            "strategy": request.strategy,
            "parameters": cleaned_params,
            "portfolio_history": portfolio_history,
            "portfolio": portfolio_history,
            "initial_capital": float(request.initial_capital),
            "final_value": final_value,
            "net_profit": float(final_value - float(request.initial_capital)),
            "total_return": total_return,
            "annualized_return": annualized_return,
            "volatility": volatility,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "num_trades": aggregate_trades,
            "trades": portfolio_results.get("trades", []),
            "has_open_position": False,
            "total_completed_trades": 0,
            "portfolio_components": component_results,
            "portfolio_objective": objective,
            "weights": weight_map,
            "positions_history": positions_history,
            "fixed_commission": request.fixed_commission,
            "min_commission": request.min_commission,
            "market_impact_bps": request.market_impact_bps,
            "market_impact_model": request.market_impact_model,
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": request.impact_coefficient,
            "permanent_impact_bps": request.permanent_impact_bps,
        })

        return ensure_json_serializable({
            "success": True,
            "data": results,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running portfolio strategy backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _normalize_compare_configs(
    strategies: Optional[List[str]] = None,
    strategy_configs: Optional[List[CompareStrategyConfig]] = None,
) -> List[Dict[str, Any]]:
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
    strategy_configs: List[Dict[str, Any]],
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
            max_holding_days=max_holding_days,
            data=data,
        )

        return {
            "name": strategy_name,
            "metrics": _build_comparison_entry(res),
        }

    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _run_single_strategy, config)
        for config in strategy_configs
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

@router.post(
    "/",
    response_model=BacktestResponse,
    summary="运行策略回测",
)
@timing_decorator
def run_backtest(request: BacktestRequest):
    """
    运行交易策略回测
    """
    logger.info(
        f"Starting backtest for {request.symbol} with strategy {request.strategy}"
    )

    try:
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
            max_holding_days=request.max_holding_days,
        )

        total_return = results.get("total_return", 0)
        logger.info(
            f"Backtest completed successfully. Total return: {total_return: .2%}"
        )

        # 保存到历史记录
        try:
            record_id = backtest_history.save({
                "symbol": request.symbol,
                "strategy": request.strategy,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "parameters": cleaned_params,
                "metrics": results,
                "performance_metrics": results,
                "result": results,
            })
            results["history_record_id"] = record_id
        except Exception as e:
            logger.warning(f"Failed to save backtest history: {e}")

        return BacktestResponse(success=True, data=results)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error running backtest: {e}", exc_info=True)
        return BacktestResponse(success=False, error=f"Internal server error: {str(e)}")


@router.post("/compare", summary="比较多个策略的性能")
async def compare_strategies_post(request: CompareRequest):
    try:
        return await _compare_strategies_impl(
            symbol=request.symbol,
            strategy_configs=_normalize_compare_configs(
                strategies=request.strategies,
                strategy_configs=request.strategy_configs,
            ),
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
            max_holding_days=request.max_holding_days,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing strategies: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/monte-carlo", summary="回测结果 Monte Carlo 路径模拟")
async def run_backtest_monte_carlo(request: MonteCarloBacktestRequest):
    try:
        return await asyncio.to_thread(run_backtest_monte_carlo_sync, request.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running Monte Carlo backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/monte-carlo/async", summary="异步提交 Monte Carlo 回测任务")
async def queue_backtest_monte_carlo(request: MonteCarloBacktestRequest):
    try:
        return _submit_async_backtest_task("backtest_monte_carlo", request.model_dump())
    except Exception as e:
        logger.error(f"Error queueing Monte Carlo backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/compare/significance", summary="策略对比显著性检验")
async def compare_strategy_significance(request: SignificanceCompareRequest):
    try:
        return await asyncio.to_thread(compare_strategy_significance_sync, request.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing strategy significance: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/compare/significance/async", summary="异步提交策略显著性检验任务")
async def queue_strategy_significance(request: SignificanceCompareRequest):
    try:
        return _submit_async_backtest_task("backtest_significance", request.model_dump())
    except Exception as e:
        logger.error(f"Error queueing strategy significance: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/multi-period", summary="多周期并行回测")
async def run_multi_period_backtest(request: MultiPeriodBacktestRequest):
    try:
        return await asyncio.to_thread(run_multi_period_backtest_sync, request.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running multi-period backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/multi-period/async", summary="异步提交多周期回测任务")
async def queue_multi_period_backtest(request: MultiPeriodBacktestRequest):
    try:
        return _submit_async_backtest_task("backtest_multi_period", request.model_dump())
    except Exception as e:
        logger.error(f"Error queueing multi-period backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/impact-analysis", summary="市场冲击敏感性分析")
async def run_market_impact_analysis(request: MarketImpactAnalysisRequest):
    try:
        return await asyncio.to_thread(run_market_impact_analysis_sync, request.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running market impact analysis: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/impact-analysis/async", summary="异步提交市场冲击分析任务")
async def queue_market_impact_analysis(request: MarketImpactAnalysisRequest):
    try:
        return _submit_async_backtest_task("backtest_impact_analysis", request.model_dump())
    except Exception as e:
        logger.error(f"Error queueing market impact analysis: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

# ==================== 回测历史记录 ====================

@router.get("/history", summary="获取回测历史记录")
async def get_backtest_history(
    limit: int = 20,
    offset: int = 0,
    symbol: str = None,
    strategy: str = None,
    record_type: str = None,
    summary_only: bool = False,
):
    """
    获取回测历史记录
    
    Args:
        limit: 返回记录数量限制 (默认20)
        symbol: 按股票代码过滤
        strategy: 按策略名称过滤
    """
    try:
        stats = backtest_history.get_statistics(symbol=symbol, strategy=strategy, record_type=record_type)
        history = backtest_history.get_history(
            limit=limit,
            offset=offset,
            symbol=symbol,
            strategy=strategy,
            record_type=record_type,
            summary_only=summary_only,
        )
        return ensure_json_serializable({
            "success": True,
            "data": history,
            "total": stats.get("total_records", len(history)),
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        logger.error(f"Error fetching backtest history: {e}")
        return {"success": False, "error": str(e)}


@router.get("/history/stats", summary="获取回测历史统计")
async def get_backtest_stats(symbol: str = None, strategy: str = None, record_type: str = None):
    """获取回测历史统计信息"""
    try:
        stats = backtest_history.get_statistics(symbol=symbol, strategy=strategy, record_type=record_type)
        return ensure_json_serializable({"success": True, "data": stats})
    except Exception as e:
        logger.error(f"Error fetching backtest stats: {e}")
        return {"success": False, "error": str(e)}


@router.get("/history/{record_id}", summary="获取特定回测记录")
async def get_backtest_record(record_id: str):
    """根据ID获取回测记录详情"""
    record = backtest_history.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return ensure_json_serializable({"success": True, "data": record})


@router.delete("/history/{record_id}", summary="删除回测记录")
async def delete_backtest_record(record_id: str):
    """删除特定回测记录"""
    success = backtest_history.delete(record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "message": "Record deleted"}


@router.post("/history/advanced", summary="保存高级实验记录到历史")
async def save_advanced_history_record(request: AdvancedHistorySaveRequest):
    try:
        record_id = backtest_history.save({
            "record_type": request.record_type,
            "title": request.title or "",
            "symbol": request.symbol,
            "strategy": request.strategy,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "parameters": request.parameters,
            "metrics": request.metrics,
            "result": request.result,
        })
        return ensure_json_serializable({
            "success": True,
            "data": {
                "record_id": record_id,
            },
        })
    except Exception as e:
        logger.error(f"Error saving advanced history record: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

class ReportRequest(BaseModel):
    """报告生成请求"""
    symbol: str
    strategy: str
    backtest_result: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001


def _build_report_pdf(request: ReportRequest) -> Tuple[bytes, str]:
    """Generate report bytes and filename through a single shared path."""
    from src.reporting import pdf_generator

    backtest_result = request.backtest_result

    if not backtest_result:
        backtest_result, _ = run_backtest_pipeline(
            symbol=request.symbol,
            strategy_name=request.strategy,
            parameters=request.parameters,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            commission=request.commission,
            slippage=request.slippage,
        )
    else:
        backtest_result = ensure_json_serializable(
            normalize_backtest_results(backtest_result)
        )

    pdf_content = pdf_generator.generate_backtest_report(
        backtest_result=backtest_result,
        symbol=request.symbol,
        strategy=request.strategy,
        parameters=request.parameters,
    )
    filename = (
        f"backtest_report_{request.symbol}_{request.strategy}_"
        f"{datetime.now().strftime('%Y%m%d')}.pdf"
    )
    return pdf_content, filename


@router.post("/report", summary="生成回测报告 PDF")
async def generate_report(request: ReportRequest):
    """
    生成策略回测报告 PDF
    
    如果提供了 backtest_result，则直接使用；
    否则会先运行回测再生成报告。
    """
    try:
        pdf_content, filename = _build_report_pdf(request)

        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/base64", summary="生成回测报告 (Base64)")
async def generate_report_base64(request: ReportRequest):
    """
    生成策略回测报告并返回 Base64 编码
    适用于前端直接下载
    """
    try:
        pdf_content, filename = _build_report_pdf(request)
        pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")

        return {
            "success": True,
            "data": {
                "pdf_base64": pdf_base64,
                "filename": filename,
                "content_type": "application/pdf"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
