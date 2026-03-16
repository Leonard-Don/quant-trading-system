"""
性能优化工具
"""

import time
import functools
import logging
from typing import Callable, Any, Dict
import psutil
import os
from datetime import datetime
import asyncio
from collections import defaultdict, deque
import threading

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """性能指标收集器"""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.metrics = defaultdict(lambda: deque(maxlen=max_samples))
        self.lock = threading.RLock()

    def record_timing(self, operation: str, duration: float):
        """记录操作耗时"""
        with self.lock:
            self.metrics[f"{operation}_duration"].append(duration)

    def record_counter(self, metric: str, value: int = 1):
        """记录计数器"""
        with self.lock:
            self.metrics[f"{metric}_count"].append(value)

    def get_stats(self, operation: str) -> Dict[str, float]:
        """获取操作统计信息"""
        with self.lock:
            durations = list(self.metrics[f"{operation}_duration"])
            if not durations:
                return {}

            return {
                "count": len(durations),
                "avg": sum(durations) / len(durations),
                "min": min(durations),
                "max": max(durations),
                "p95": (
                    sorted(durations)[int(len(durations) * 0.95)]
                    if len(durations) > 20
                    else max(durations)
                ),
            }


# 全局性能指标收集器
performance_metrics = PerformanceMetrics()


def timing_decorator(func: Callable) -> Callable:
    """增强的计时装饰器，支持异步函数和性能指标收集"""

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            execution_time = time.time() - start_time
            performance_metrics.record_timing(func.__name__, execution_time)
            if execution_time > 1.0:  # 只记录慢操作
                logger.info(f"{func.__name__} 执行时间: {execution_time: .4f}秒")

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            execution_time = time.time() - start_time
            performance_metrics.record_timing(func.__name__, execution_time)
            if execution_time > 1.0:  # 只记录慢操作
                logger.info(f"{func.__name__} 执行时间: {execution_time: .4f}秒")

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def memory_usage_decorator(func: Callable) -> Callable:
    """内存使用监控装饰器"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        result = func(*args, **kwargs)

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_diff = memory_after - memory_before

        logger.info(
            f"{func.__name__} 内存使用: {memory_before: .2f}MB -> "
            f"{memory_after: .2f}MB (差异: {memory_diff: +.2f}MB)"
        )
        return result

    return wrapper


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics = {}
        self.start_time = None

    def start_monitoring(self, operation_name: str):
        """开始监控操作"""
        self.start_time = time.time()
        self.metrics[operation_name] = {
            "start_time": self.start_time,
            "start_memory": psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024,
        }

    def stop_monitoring(self, operation_name: str) -> Dict[str, Any]:
        """停止监控操作并返回指标"""
        if operation_name not in self.metrics:
            return {}

        end_time = time.time()
        end_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

        metrics = self.metrics[operation_name]
        result = {
            "operation": operation_name,
            "duration": end_time - metrics["start_time"],
            "memory_start": metrics["start_memory"],
            "memory_end": end_memory,
            "memory_diff": end_memory - metrics["start_memory"],
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            f"性能指标 - {operation_name}: {result['duration']: .4f}s, "
            f"内存: {result['memory_diff']: +.2f}MB"
        )
        return result

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_available": (
                psutil.virtual_memory().available / 1024 / 1024 / 1024
            ),  # GB
            "disk_usage": psutil.disk_usage("/").percent,
            "timestamp": datetime.now().isoformat(),
        }


# 全局性能监控器实例
performance_monitor = PerformanceMonitor()


def optimize_dataframe_operations():
    """DataFrame操作优化建议"""
    tips = [
        "使用 .loc 和 .iloc 进行索引操作",
        "避免在循环中修改DataFrame",
        "使用向量化操作替代循环",
        "合理使用 .copy() 避免不必要的数据复制",
        "使用 .query() 进行复杂条件筛选",
        "考虑使用 .eval() 进行数学表达式计算",
    ]
    return tips


def cache_performance_stats():
    """缓存性能统计"""
    return {
        "cache_hits": 0,  # 这里应该从实际缓存系统获取
        "cache_misses": 0,
        "cache_hit_rate": 0.0,
        "cache_size": 0,
    }
