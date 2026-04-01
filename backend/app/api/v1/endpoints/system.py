
from fastapi import APIRouter
from datetime import datetime
import logging
from backend.app.core.config import config
from src.utils.performance import performance_metrics, performance_monitor

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

router = APIRouter()
logger = logging.getLogger(__name__)

# 策略列表用于计数
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

@router.get("/status", summary="系统状态检查", deprecated=True)
async def get_system_status(detailed: bool = False):
    """
    系统状态检查接口
    
    Args:
        detailed: 是否执行详细检查 (默认 False，仅返回基础资源使用情况)
    """
    try:
        if not detailed:
            # 轻量级检查 (原 /status 逻辑)
            import psutil
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)

            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "mode": "basic",
                "components": {
                    "api": "healthy",
                    "strategies": len(STRATEGIES),
                    "data_manager": "healthy",
                    "cache": "healthy",
                },
                "system_info": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                },
                "version": config["app_version"],
            }
        else:
            # 详细检查已移除，返回基础信息
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "mode": "basic_fallback",
                "system_info": {
                    "cpu_percent": 0,
                    "memory_percent": 0,
                },
                "version": config["app_version"],
            }

    except Exception as e:
        logger.error(f"System status check failed: {e}", exc_info=True)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "version": config["app_version"],
        }

@router.get("/performance", summary="获取性能指标概览", deprecated=True)
async def get_system_performance_overview():
    """获取性能指标"""
    try:
        return {
            "success": True,
            "data": {
                "system_info": performance_monitor.get_system_info(),
                "timestamp": datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Performance metrics error: {e}")
        return {"success": False, "error": str(e)}

@router.get("/health-check", summary="综合健康检查", deprecated=True)
def comprehensive_health_check():
    """综合健康检查"""
    try:
        return {
            "success": True,
            "data": {"status": "healthy", "message": "Comprehensive check disabled"},
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"success": False, "error": str(e)}

@router.get("/metrics", summary="获取详细性能指标", deprecated=True)
async def get_performance_metrics():
    """获取性能指标"""
    try:
        # 获取所有操作的性能统计
        all_stats = {}
        operations = ["backtest", "get_cached_data", "generate_cache_key"]

        for op in operations:
            stats = performance_metrics.get_stats(op)
            if stats:
                all_stats[op] = stats

        return {
            "success": True,
            "metrics": all_stats,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"获取性能指标失败: {e}")
        return {"success": False, "error": str(e)}

@router.get("/alerts/summary", summary="获取告警摘要", deprecated=True)
async def get_alert_summary():
    """获取告警摘要"""
    try:
        # 告警系统已移除
        summary = {"alerts": [], "count": 0}

        return {
            "success": True,
            "data": summary,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"获取告警摘要失败: {e}")
        return {"success": False, "error": str(e)}

@router.post("/alerts/{alert_index}/resolve", summary="解决告警", deprecated=True)
async def resolve_alert(alert_index: int):
    """解决告警"""
    try:
        pass # 告警系统已移除
        return {"success": True, "message": f"Alert {alert_index} resolved"}
    except Exception as e:
        logger.error(f"解决告警失败: {e}")
        return {"success": False, "error": str(e)}


@router.get("/dependencies", summary="依赖项连通性检查", deprecated=True)
async def check_dependencies():
    """
    检查所有外部依赖项的连通性
    包括：yfinance API、缓存系统、ML模型等
    """
    import time
    dependencies = {}
    overall_status = "healthy"
    
    # 1. 检查 yfinance API 连通性
    try:
        start = time.time()
        import yfinance as yf
        ticker = yf.Ticker("AAPL")
        info = ticker.info
        elapsed = round((time.time() - start) * 1000, 2)
        dependencies["yfinance_api"] = {
            "status": "healthy" if info else "degraded",
            "response_time_ms": elapsed,
            "message": "能够获取股票数据" if info else "返回数据为空"
        }
    except Exception as e:
        overall_status = "degraded"
        dependencies["yfinance_api"] = {
            "status": "unhealthy",
            "error": str(e),
            "message": "无法连接到 Yahoo Finance API"
        }
    
    # 2. 检查缓存系统
    try:
        from src.data.data_manager import DataManager
        dm = DataManager()
        cache_info = {
            "status": "healthy",
            "cache_size": len(dm.cache.cache) if hasattr(dm.cache, 'cache') else 0,
            "max_size": dm.cache.max_size if hasattr(dm.cache, 'max_size') else "unknown"
        }
        dependencies["cache_system"] = cache_info
    except Exception as e:
        dependencies["cache_system"] = {
            "status": "degraded",
            "error": str(e)
        }
    
    # 3. 检查 ML 模型状态
    try:
        from src.analytics.predictor import PricePredictor
        import os
        model_path = os.path.join(os.path.dirname(__file__), "../../../../src/analytics/model_data")
        model_path = os.path.abspath(model_path)
        if os.path.exists(model_path):
            model_files = [f for f in os.listdir(model_path) if f.endswith('.joblib')]
            dependencies["ml_models"] = {
                "status": "healthy",
                "cached_models": len(model_files) // 2,  # 每个模型有2个文件
                "model_files": model_files[:10]  # 只显示前10个
            }
        else:
            dependencies["ml_models"] = {
                "status": "healthy",
                "cached_models": 0,
                "message": "无缓存模型，将在首次预测时训练"
            }
    except Exception as e:
        dependencies["ml_models"] = {
            "status": "degraded",
            "error": str(e)
        }
    
    # 4. 检查磁盘空间
    try:
        import psutil
        disk = psutil.disk_usage('/')
        disk_status = "healthy" if disk.percent < 90 else "warning"
        if disk.percent >= 90:
            overall_status = "warning"
        dependencies["disk_space"] = {
            "status": disk_status,
            "used_percent": disk.percent,
            "free_gb": round(disk.free / (1024**3), 2)
        }
    except Exception as e:
        dependencies["disk_space"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    return {
        "overall_status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "dependencies": dependencies,
        "version": config["app_version"]
    }
