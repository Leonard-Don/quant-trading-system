import logging
from datetime import datetime

import psutil
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from backend.app.core.config import config
from backend.app.core.error_handler import AppException
from backend.app.services.runtime_state import get_data_manager
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
from src.utils.performance import performance_metrics, performance_monitor

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


def _sample_system_resources() -> dict:
    """Sample CPU/memory usage off the event loop.

    ``psutil.cpu_percent(interval=0.1)`` blocks for 100ms; gather it together
    with the virtual-memory snapshot in a worker thread so concurrent requests
    are not stalled. Returns the values consumed by ``get_system_status``.
    """
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.1)
    return {
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "memory_available_gb": round(memory.available / (1024**3), 2),
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
            system_info = await run_in_threadpool(_sample_system_resources)

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
                "system_info": system_info,
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

    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, psutil.Error) as e:
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
    except (AttributeError, OSError, RuntimeError, psutil.Error) as e:
        logger.error(f"Performance metrics error: {e}")
        raise AppException(
            message=str(e),
            error_code="PERFORMANCE_OVERVIEW_FAILED",
        ) from e


@router.get("/health-check", summary="综合健康检查", deprecated=True)
def comprehensive_health_check():
    """综合健康检查"""
    return {
        "success": True,
        "data": {"status": "healthy", "message": "Comprehensive check disabled"},
    }


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
    except (AttributeError, KeyError, RuntimeError, TypeError) as e:
        logger.error(f"获取性能指标失败: {e}")
        raise AppException(
            message=str(e),
            error_code="PERFORMANCE_METRICS_FAILED",
        ) from e


@router.get("/providers/status", summary="数据源运行状态")
async def get_provider_runtime_status():
    """Return provider registry and circuit-breaker state without probing remotes."""
    try:
        data_manager = get_data_manager()
        provider_factory = getattr(data_manager, "provider_factory", None)
        providers = (
            provider_factory.get_provider_runtime_status() if provider_factory is not None else {}
        )

        from src.data.providers.sina_ths_adapter import SinaIndustryAdapter

        providers["sina_ths"] = {
            "provider": {
                "name": "sina_ths",
                "description": "THS-first industry adapter with Sina/AKShare fallbacks",
            },
            "circuit_breakers": SinaIndustryAdapter.get_circuit_status(),
        }

        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "providers": providers,
        }
    except (AttributeError, ImportError, KeyError, RuntimeError, TypeError) as e:
        logger.error(f"Provider status error: {e}", exc_info=True)
        raise AppException(
            message=str(e),
            error_code="PROVIDER_STATUS_FAILED",
        ) from e


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
    def _probe_yfinance():
        start = time.time()
        import yfinance as yf

        ticker = yf.Ticker("AAPL")
        info = ticker.info
        elapsed = round((time.time() - start) * 1000, 2)
        return info, elapsed

    try:
        # yfinance.info 触发同步 HTTP 请求，放到线程池避免阻塞事件循环
        info, elapsed = await run_in_threadpool(_probe_yfinance)
        dependencies["yfinance_api"] = {
            "status": "healthy" if info else "degraded",
            "response_time_ms": elapsed,
            "message": "能够获取股票数据" if info else "返回数据为空",
        }
    except (
        AttributeError,
        ConnectionError,
        ImportError,
        KeyError,
        OSError,
        RuntimeError,
        TimeoutError,
        ValueError,
    ) as e:
        overall_status = "degraded"
        dependencies["yfinance_api"] = {
            "status": "unhealthy",
            "error": str(e),
            "message": "无法连接到 Yahoo Finance API",
        }

    # 2. 检查缓存系统
    try:
        dm = get_data_manager()
        cache_info = {
            "status": "healthy",
            "cache_size": len(dm.cache.cache) if hasattr(dm.cache, "cache") else 0,
            "max_size": dm.cache.max_size if hasattr(dm.cache, "max_size") else "unknown",
        }
        dependencies["cache_system"] = cache_info
    except (AttributeError, KeyError, RuntimeError, TypeError) as e:
        dependencies["cache_system"] = {"status": "degraded", "error": str(e)}

    # 3. 检查 ML 模型状态
    def _scan_ml_models():
        import os

        model_path = os.path.join(os.path.dirname(__file__), "../../../../src/analytics/model_data")
        model_path = os.path.abspath(model_path)
        if os.path.exists(model_path):
            model_files = [f for f in os.listdir(model_path) if f.endswith(".joblib")]
            return {
                "status": "healthy",
                "cached_models": len(model_files) // 2,  # 每个模型有2个文件
                "model_files": model_files[:10],  # 只显示前10个
            }
        return {
            "status": "healthy",
            "cached_models": 0,
            "message": "无缓存模型，将在首次预测时训练",
        }

    try:
        # 目录扫描属于阻塞 I/O，放到线程池执行
        dependencies["ml_models"] = await run_in_threadpool(_scan_ml_models)
    except (OSError, RuntimeError) as e:
        dependencies["ml_models"] = {"status": "degraded", "error": str(e)}

    # 4. 检查磁盘空间
    try:
        disk = await run_in_threadpool(psutil.disk_usage, "/")
        disk_status = "healthy" if disk.percent < 90 else "warning"
        if disk.percent >= 90:
            overall_status = "warning"
        dependencies["disk_space"] = {
            "status": disk_status,
            "used_percent": disk.percent,
            "free_gb": round(disk.free / (1024**3), 2),
        }
    except (ImportError, OSError, RuntimeError, psutil.Error) as e:
        dependencies["disk_space"] = {"status": "unknown", "error": str(e)}

    return {
        "overall_status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "dependencies": dependencies,
        "version": config["app_version"],
    }
