import base64
from fastapi import APIRouter, HTTPException
import asyncio
from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    BatchBacktestRequest,
    WalkForwardRequest,
    AdvancedHistorySaveRequest,
)
from src.backtest.history import backtest_history
from src.backtest.batch_backtester import BatchBacktester, BacktestTask, WalkForwardAnalyzer
from src.data.data_manager import DataManager
from src.strategy.strategies import (
    MovingAverageCrossover,
    RSIStrategy,
    BollingerBands,
    BuyAndHold,
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
from src.analytics.dashboard import PerformanceAnalyzer
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


def _build_batch_backtester(max_workers: int) -> BatchBacktester:
    return BatchBacktester(max_workers=max_workers, use_processes=False)


def _strategy_factory_for_batch(strategy_name: str, parameters: Dict[str, Any]):
    is_valid, error_msg, cleaned_params = StrategyValidator.validate_strategy_params(
        strategy_name, parameters or {}
    )
    if not is_valid:
        raise ValueError(error_msg)
    return _create_strategy_instance(strategy_name, cleaned_params)


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


@router.post("/batch", summary="批量运行多个回测任务")
async def run_batch_backtest(request: BatchBacktestRequest):
    try:
        batch = _build_batch_backtester(request.max_workers)
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
            )
            for index, item in enumerate(request.tasks, start=1)
        ]

        results = batch.run_batch(
            tasks=tasks,
            backtester_factory=lambda initial_capital=10000, commission=0.001, slippage=0.001: Backtester(
                initial_capital=initial_capital,
                commission=commission,
                slippage=slippage,
            ),
            strategy_factory=_strategy_factory_for_batch,
            data_fetcher=_fetch_backtest_data,
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
                "results": [
                    {
                        "task_id": result.task_id,
                        "symbol": result.symbol,
                        "strategy": result.strategy_name,
                        "parameters": result.parameters,
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
                        "metrics": result.metrics,
                        "success": result.success,
                        "execution_time": result.execution_time,
                    }
                    for result in ranked_results
                ],
            },
        })
    except Exception as e:
        logger.error(f"Error running batch backtest: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/walk-forward", summary="运行 Walk-Forward 分析")
async def run_walk_forward_backtest(request: WalkForwardRequest):
    try:
        if request.train_period <= 0 or request.test_period <= 0 or request.step_size <= 0:
            raise HTTPException(status_code=400, detail="Train/test/step periods must be positive")

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
        result = analyzer.analyze(
            data=data,
            strategy_factory=lambda: _create_strategy_instance(request.strategy, cleaned_params),
            backtester_factory=lambda: Backtester(
                initial_capital=request.initial_capital,
                commission=request.commission,
                slippage=request.slippage,
            ),
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
                **result,
            },
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running walk-forward backtest: {e}", exc_info=True)
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
            data=data,
        )

        return {
            "name": strategy_name,
            "metrics": _build_comparison_entry(res),
        }

    loop = asyncio.get_event_loop()
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
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing strategies: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@router.get("/compare", summary="比较多个策略的性能")
async def compare_strategies(
    symbol: str,
    strategies: str,  # 逗号分隔的策略列表
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = 10000.0,
    commission: float = 0.001,
    slippage: float = 0.001,
):
    """
    比较多个策略的性能
    
    包含：
    1. 并发执行回测
    2. 服务端计算综合评分 (收益40%, 夏普30%, 风控30%)
    """
    try:
        return await _compare_strategies_impl(
            symbol=symbol,
            strategy_configs=_normalize_compare_configs(strategies=strategies.split(",")),
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing strategies: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ==================== 回测历史记录 ====================

@router.get("/history", summary="获取回测历史记录")
async def get_backtest_history(
    limit: int = 20,
    offset: int = 0,
    symbol: str = None,
    strategy: str = None,
    record_type: str = None,
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
