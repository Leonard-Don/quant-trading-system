"""
异步工具模块
"""

import asyncio
import concurrent.futures
from typing import Any, Callable, List, Optional, Union
import functools
import time
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AsyncTaskManager:
    """异步任务管理器"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.running_tasks = []
        self.completed_tasks = []
        self.failed_tasks = []

    async def run_async(self, func: Callable, *args, **kwargs) -> Any:
        """异步运行同步函数"""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                self.executor, functools.partial(func, *args, **kwargs)
            )
            return result
        except Exception as e:
            logger.error(f"Async task failed: {e}")
            raise

    async def run_parallel(self, tasks: List[tuple]) -> List[Any]:
        """并行运行多个任务"""

        async def run_single_task(task_info):
            func, args, kwargs = task_info
            task_id = f"{func.__name__}_{datetime.now().timestamp()}"

            try:
                self.running_tasks.append(task_id)
                result = await self.run_async(func, *args, **kwargs)
                self.completed_tasks.append(task_id)
                return result
            except Exception as e:
                self.failed_tasks.append((task_id, str(e)))
                raise
            finally:
                if task_id in self.running_tasks:
                    self.running_tasks.remove(task_id)

        # 创建任务
        coroutines = [run_single_task(task) for task in tasks]

        # 并行执行
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        return results

    def get_stats(self) -> dict:
        """获取任务统计"""
        return {
            "running_tasks": len(self.running_tasks),
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "max_workers": self.max_workers,
        }

    def cleanup(self):
        """清理资源"""
        self.executor.shutdown(wait=True)


# 全局任务管理器
task_manager = AsyncTaskManager()


def async_timeout(timeout: float):
    """异步超时装饰器"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"Function {func.__name__} timed out after {timeout}s")
                raise

        return wrapper

    return decorator


def retry_async(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """异步重试装饰器"""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {func.__name__}"
                        )

            raise last_exception

        return wrapper

    return decorator


class RateLimiter:
    """异步速率限制器"""

    def __init__(self, calls_per_second: float):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call_time = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """获取速率限制许可"""
        async with self._lock:
            now = time.time()
            time_since_last_call = now - self.last_call_time

            if time_since_last_call < self.min_interval:
                sleep_time = self.min_interval - time_since_last_call
                await asyncio.sleep(sleep_time)

            self.last_call_time = time.time()


def rate_limited(calls_per_second: float):
    """速率限制装饰器"""
    limiter = RateLimiter(calls_per_second)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            await limiter.acquire()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


class AsyncBatchProcessor:
    """异步批处理器"""

    def __init__(self, batch_size: int = 10, max_delay: float = 1.0):
        self.batch_size = batch_size
        self.max_delay = max_delay
        self.pending_items = []
        self.pending_futures = []
        self.last_batch_time = time.time()
        self._lock = asyncio.Lock()
        self._batch_task = None

    async def add_item(self, item: Any, processor: Callable) -> Any:
        """添加项目到批处理队列"""
        async with self._lock:
            future = asyncio.Future()
            self.pending_items.append((item, processor))
            self.pending_futures.append(future)

            # 检查是否需要处理批次
            should_process = (
                len(self.pending_items) >= self.batch_size
                or (time.time() - self.last_batch_time) > self.max_delay
            )

            if should_process and not self._batch_task:
                self._batch_task = asyncio.create_task(self._process_batch())

            return await future

    async def _process_batch(self):
        """处理当前批次"""
        async with self._lock:
            if not self.pending_items:
                self._batch_task = None
                return

            items = self.pending_items.copy()
            futures = self.pending_futures.copy()
            self.pending_items.clear()
            self.pending_futures.clear()
            self.last_batch_time = time.time()

        try:
            # 并行处理所有项目
            tasks = []
            for item, processor in items:
                task = asyncio.create_task(task_manager.run_async(processor, item))
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 设置结果
            for future, result in zip(futures, results):
                if isinstance(result, Exception):
                    future.set_exception(result)
                else:
                    future.set_result(result)

        except Exception as e:
            # 如果批处理失败，所有future都设置异常
            for future in futures:
                if not future.done():
                    future.set_exception(e)
        finally:
            self._batch_task = None


# 全局批处理器实例
batch_processor = AsyncBatchProcessor()


async def run_with_semaphore(
    semaphore: asyncio.Semaphore, func: Callable, *args, **kwargs
):
    """使用信号量限制并发执行"""
    async with semaphore:
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return await task_manager.run_async(func, *args, **kwargs)
