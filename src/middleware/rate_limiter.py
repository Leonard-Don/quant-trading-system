"""
API请求限流中间件
实现基于令牌桶算法的速率限制
"""

import time
import logging
from typing import Dict, Optional
from collections import defaultdict
from threading import Lock
from functools import wraps
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


class TokenBucket:
    """令牌桶实现"""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: 桶的容量（最大令牌数）
            refill_rate: 令牌填充速率（令牌/秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = Lock()

    def consume(self, tokens: int = 1) -> bool:
        """
        消费令牌

        Args:
            tokens: 要消费的令牌数

        Returns:
            是否成功消费
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def _refill(self):
        """重新填充令牌"""
        now = time.time()
        elapsed = now - self.last_refill

        # 根据经过的时间计算应该添加的令牌数
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now


class RateLimiter:
    """速率限制器"""

    def __init__(self, requests_per_minute: int = 60, burst_size: Optional[int] = None):
        """
        Args:
            requests_per_minute: 每分钟允许的请求数
            burst_size: 突发请求大小（默认为requests_per_minute）
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size or requests_per_minute

        # 每秒填充速率
        self.refill_rate = requests_per_minute / 60.0

        # 客户端令牌桶映射
        self.buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(self.burst_size, self.refill_rate)
        )

        self.lock = Lock()
        logger.info(
            f"速率限制器初始化: {requests_per_minute} 请求/分钟, " f"突发大小: {self.burst_size}"
        )

    def is_allowed(self, client_id: str) -> bool:
        """
        检查是否允许请求

        Args:
            client_id: 客户端标识（通常是IP地址）

        Returns:
            是否允许请求
        """
        bucket = self.buckets[client_id]
        return bucket.consume(1)

    def get_client_id(self, request: Request) -> str:
        """
        获取客户端标识

        Args:
            request: FastAPI请求对象

        Returns:
            客户端标识
        """
        # 优先使用X-Forwarded-For，如果在代理后面
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # 使用X-Real-IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 使用直接客户端IP
        if request.client:
            return request.client.host

        return "unknown"

    async def __call__(self, request: Request):
        """
        中间件调用方法

        Args:
            request: FastAPI请求对象

        Raises:
            HTTPException: 如果超过速率限制
        """
        client_id = self.get_client_id(request)

        if not self.is_allowed(client_id):
            logger.warning(f"速率限制触发: 客户端 {client_id}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "速率限制",
                    "message": f"超过请求限制，请在 {60 / self.refill_rate:.0f} 秒后重试",
                    "limit": self.requests_per_minute,
                    "window": "1分钟",
                },
            )


# 装饰器形式的速率限制
def rate_limit(requests_per_minute: int = 60, burst_size: Optional[int] = None):
    """
    速率限制装饰器

    Args:
        requests_per_minute: 每分钟允许的请求数
        burst_size: 突发请求大小
    """
    limiter = RateLimiter(requests_per_minute, burst_size)

    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            await limiter(request)
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
