from fastapi import APIRouter, HTTPException
import asyncio
from datetime import datetime
import logging
from typing import Any, Dict, Optional, Tuple

from backend.app.schemas.backtest import BacktestRequest, BacktestResponse
from src.backtest.history import backtest_history
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

@router.get("/compare", summary="比较多个策略的性能")
async def compare_strategies(
    symbol: str,
    strategies: str,  # 逗号分隔的策略列表
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = 100000.0,
):
    """
    比较多个策略的性能
    
    包含：
    1. 并发执行回测
    2. 服务端计算综合评分 (收益40%, 夏普30%, 风控30%)
    """
    try:
        strategy_list = strategies.split(",")
        results = {}

        data = _fetch_backtest_data(symbol, start_date, end_date)

        # 定义单个策略回测函数
        def _run_single_strategy(name):
            strategy_name = name.strip()
            if strategy_name not in STRATEGIES:
                return None

            res, _ = run_backtest_pipeline(
                symbol=symbol,
                strategy_name=strategy_name,
                parameters={},
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                data=data,
            )

            return {
                "name": strategy_name,
                "metrics": _build_comparison_entry(res),
            }

        # 并发执行所有策略
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, _run_single_strategy, s_name) 
            for s_name in strategy_list
        ]
        
        # 等待所有任务完成
        completed_strategies = await asyncio.gather(*tasks)
        
        # 过滤无效结果并构建基础结果集
        valid_results = [r for r in completed_strategies if r is not None]
        
        if not valid_results:
            return {"success": True, "data": {}}

        # === 计算综合评分 ===
        
        # 1. 获取极值用于归一化
        max_return = max(r["metrics"]["total_return"] for r in valid_results)
        min_return = min(r["metrics"]["total_return"] for r in valid_results)
        
        max_sharpe = max(r["metrics"]["sharpe_ratio"] for r in valid_results)
        min_sharpe = min(r["metrics"]["sharpe_ratio"] for r in valid_results)
        
        # Drawdown是负数或0，取绝对值处理，越小越好
        max_dd = max(abs(r["metrics"]["max_drawdown"]) for r in valid_results)
        min_dd = min(abs(r["metrics"]["max_drawdown"]) for r in valid_results)

        # 归一化辅助函数
        def normalize(val, min_v, max_v, inverse=False):
            if max_v == min_v:
                return 50.0
            score = (val - min_v) / (max_v - min_v) * 100
            return 100 - score if inverse else score

        # 2. 计算每个策略的分数和排名
        scored_results = []
        for item in valid_results:
            metrics = item["metrics"]
            
            # 计算分项得分
            return_score = normalize(metrics["total_return"], min_return, max_return)
            sharpe_score = normalize(metrics["sharpe_ratio"], min_sharpe, max_sharpe)
            risk_score = normalize(abs(metrics["max_drawdown"]), min_dd, max_dd, inverse=True)
            
            # 综合评分: 收益40% + 夏普30% + 风控30%
            overall_score = (return_score * 0.4) + (sharpe_score * 0.3) + (risk_score * 0.3)
            
            metrics["scores"] = {
                "return_score": round(return_score),
                "sharpe_score": round(sharpe_score),
                "risk_score": round(risk_score),
                "overall_score": round(overall_score)
            }
            scored_results.append(item)

        # 3. 按综合评分排序并添加排名
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

    except Exception as e:
        logger.error(f"Error comparing strategies: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ==================== 回测历史记录 ====================

@router.get("/history", summary="获取回测历史记录")
async def get_backtest_history(
    limit: int = 20,
    symbol: str = None,
    strategy: str = None
):
    """
    获取回测历史记录
    
    Args:
        limit: 返回记录数量限制 (默认20)
        symbol: 按股票代码过滤
        strategy: 按策略名称过滤
    """
    try:
        history = backtest_history.get_history(limit=limit, symbol=symbol, strategy=strategy)
        return ensure_json_serializable({
            "success": True,
            "data": history,
            "total": len(history)
        })
    except Exception as e:
        logger.error(f"Error fetching backtest history: {e}")
        return {"success": False, "error": str(e)}


@router.get("/history/stats", summary="获取回测历史统计")
async def get_backtest_stats():
    """获取回测历史统计信息"""
    try:
        stats = backtest_history.get_statistics()
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


@router.post("/report", summary="生成回测报告 PDF")
async def generate_report(request: ReportRequest):
    """
    生成策略回测报告 PDF
    
    如果提供了 backtest_result，则直接使用；
    否则会先运行回测再生成报告。
    """
    try:
        from src.reporting import pdf_generator
        
        backtest_result = request.backtest_result
        
        # 如果没有提供回测结果，先运行回测
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
        
        # 生成 PDF
        pdf_content = pdf_generator.generate_backtest_report(
            backtest_result=backtest_result,
            symbol=request.symbol,
            strategy=request.strategy,
            parameters=request.parameters
        )
        
        # 返回 PDF 文件
        filename = f"backtest_report_{request.symbol}_{request.strategy}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
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
        
        # 生成 Base64 编码的 PDF
        pdf_base64 = pdf_generator.get_report_base64(
            backtest_result=backtest_result,
            symbol=request.symbol,
            strategy=request.strategy,
            parameters=request.parameters
        )
        
        return {
            "success": True,
            "data": {
                "pdf_base64": pdf_base64,
                "filename": f"backtest_report_{request.symbol}_{request.strategy}_{datetime.now().strftime('%Y%m%d')}.pdf",
                "content_type": "application/pdf"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
