from fastapi import APIRouter, HTTPException
import asyncio
from datetime import datetime
import logging
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
)

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
        # 验证策略
        if request.strategy not in STRATEGIES:
            logger.warning(f"Unknown strategy requested: {request.strategy}")
            raise HTTPException(
                status_code=400, detail=f"Unknown strategy: {request.strategy}"
            )

        # 验证参数
        if request.initial_capital <= 0:
            raise HTTPException(
                status_code=400, detail="Initial capital must be positive"
            )

        # 解析日期
        start_date = None
        end_date = None

        if request.start_date:
            start_date = datetime.fromisoformat(
                request.start_date.replace("Z", "+00:00")
            )
        if request.end_date:
            end_date = datetime.fromisoformat(request.end_date.replace("Z", "+00:00"))

        # 验证日期范围
        if start_date and end_date and start_date >= end_date:
            raise HTTPException(
                status_code=400, detail="Start date must be before end date"
            )

        logger.info(
            f"Fetching data for {request.symbol} from {start_date} to {end_date}"
        )

        # 获取数据
        data = data_manager.get_historical_data(
            symbol=request.symbol, start_date=start_date, end_date=end_date
        )

        if data.empty:
            logger.warning(f"No data found for symbol {request.symbol}")
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {request.symbol}"
            )

        logger.info(f"Retrieved {len(data)} data points")

        # 验证策略参数
        (
            is_valid,
            error_msg,
            cleaned_params,
        ) = StrategyValidator.validate_strategy_params(
            request.strategy, request.parameters
        )
        if not is_valid:
            logger.warning(f"Invalid strategy parameters: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        # 创建策略实例
        strategy_class = STRATEGIES[request.strategy]

        try:
            # 使用验证和清理后的参数创建策略
            if request.strategy == "moving_average":
                strategy = strategy_class(
                    fast_period=cleaned_params["fast_period"],
                    slow_period=cleaned_params["slow_period"],
                )
            elif request.strategy == "rsi":
                strategy = strategy_class(
                    period=cleaned_params["period"],
                    oversold=cleaned_params["oversold"],
                    overbought=cleaned_params["overbought"],
                )
            elif request.strategy == "bollinger_bands":
                strategy = strategy_class(
                    period=cleaned_params["period"], num_std=cleaned_params["num_std"]
                )
            elif request.strategy == "macd":
                strategy = strategy_class(
                    fast=cleaned_params["fast_period"],
                    slow=cleaned_params["slow_period"],
                    signal=cleaned_params["signal_period"],
                )
            elif request.strategy == "mean_reversion":
                strategy = strategy_class(
                    lookback=cleaned_params["lookback_period"],
                    z_threshold=cleaned_params["entry_threshold"],
                )
            elif request.strategy == "vwap":
                strategy = strategy_class(window=cleaned_params["period"])
            elif request.strategy == "momentum":
                strategy = strategy_class(
                    fast_window=cleaned_params["fast_window"],
                    slow_window=cleaned_params["slow_window"],
                )
            elif request.strategy == "stochastic":
                strategy = strategy_class(
                    k_period=cleaned_params["k_period"],
                    d_period=cleaned_params["d_period"],
                    oversold=cleaned_params["oversold"],
                    overbought=cleaned_params["overbought"],
                )
            elif request.strategy == "atr_trailing_stop":
                strategy = strategy_class(
                    atr_period=cleaned_params["atr_period"],
                    atr_multiplier=cleaned_params["atr_multiplier"],
                )
            else:  # buy_and_hold 或其他无参数策略
                strategy = strategy_class()
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to create strategy instance: {e}")
            raise HTTPException(
                status_code=500, detail=f"Strategy creation failed: {str(e)}"
            )

        logger.info(f"Running backtest with strategy: {strategy.name}")

        # 运行回测
        backtester = Backtester(
            initial_capital=request.initial_capital,
            commission=request.commission,
            slippage=request.slippage,
        )

        results = backtester.run(strategy, data)

        # 验证和修复数据结构
        results = validate_and_fix_backtest_results(results)

        # 计算额外的分析指标
        analyzer = PerformanceAnalyzer(results)
        metrics = analyzer.calculate_metrics()
        results.update(metrics)

        # 确保所有数据都可以JSON序列化
        results = ensure_json_serializable(results)

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
                "performance_metrics": results
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

        # 获取数据
        start_dt = (
            datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            if start_date
            else None
        )
        end_dt = (
            datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if end_date
            else None
        )

        data = data_manager.get_historical_data(symbol, start_dt, end_dt)
        if data.empty:
            raise HTTPException(
                status_code=404, detail=f"No data found for symbol {symbol}"
            )

        # 定义单个策略回测函数
        def _run_single_strategy(name):
            if name.strip() not in STRATEGIES:
                return None
            
            strategy_class = STRATEGIES[name.strip()]
            strategy_instance = strategy_class()
            
            # 使用传入的初始资金
            local_backtester = Backtester(initial_capital=initial_capital)
            res = local_backtester.run(strategy_instance, data)
            
            return {
                "name": name.strip(),
                "metrics": {
                    "total_return": res.get("total_return", 0),
                    "annualized_return": res.get("annualized_return", 0),
                    "sharpe_ratio": res.get("sharpe_ratio", 0),
                    "max_drawdown": res.get("max_drawdown", 0),
                    "num_trades": res.get("num_trades", 0),
                }
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
        return {
            "success": True,
            "data": history,
            "total": len(history)
        }
    except Exception as e:
        logger.error(f"Error fetching backtest history: {e}")
        return {"success": False, "error": str(e)}


@router.get("/history/stats", summary="获取回测历史统计")
async def get_backtest_stats():
    """获取回测历史统计信息"""
    try:
        stats = backtest_history.get_statistics()
        return {"success": True, "data": stats}
    except Exception as e:
        logger.error(f"Error fetching backtest stats: {e}")
        return {"success": False, "error": str(e)}


@router.get("/history/{record_id}", summary="获取特定回测记录")
async def get_backtest_record(record_id: str):
    """根据ID获取回测记录详情"""
    record = backtest_history.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "data": record}


@router.delete("/history/{record_id}", summary="删除回测记录")
async def delete_backtest_record(record_id: str):
    """删除特定回测记录"""
    success = backtest_history.delete(record_id)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "message": "Record deleted"}


# ==================== PDF 报告生成 ====================

from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Dict, Any

class ReportRequest(BaseModel):
    """报告生成请求"""
    symbol: str
    strategy: str
    backtest_result: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None


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
            # 获取数据
            data = data_manager.get_historical_data(symbol=request.symbol)
            if data.empty:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No data found for symbol {request.symbol}"
                )
            
            # 创建策略
            if request.strategy not in STRATEGIES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown strategy: {request.strategy}"
                )
            
            strategy_class = STRATEGIES[request.strategy]
            strategy = strategy_class()
            
            # 运行回测
            backtester = Backtester(initial_capital=100000)
            backtest_result = backtester.run(strategy, data)
            backtest_result = validate_and_fix_backtest_results(backtest_result)
        
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
            data = data_manager.get_historical_data(symbol=request.symbol)
            if data.empty:
                raise HTTPException(
                    status_code=404, 
                    detail=f"No data found for symbol {request.symbol}"
                )
            
            if request.strategy not in STRATEGIES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown strategy: {request.strategy}"
                )
            
            strategy_class = STRATEGIES[request.strategy]
            strategy = strategy_class()
            
            backtester = Backtester(initial_capital=100000)
            backtest_result = backtester.run(strategy, data)
            backtest_result = validate_and_fix_backtest_results(backtest_result)
        
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
